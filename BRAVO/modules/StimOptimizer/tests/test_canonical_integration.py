"""Production settings adapter refuses ambiguity instead of treating unknown exposure as off."""
import importlib.util
import ast
from pathlib import Path
import unittest
import json
import sys
import types
from datetime import datetime
from unittest.mock import patch, Mock

import pandas as pd
import numpy as np

PATH = Path(__file__).resolve().parents[1] / "adapter.py"
spec = importlib.util.spec_from_file_location("stim_canonical_adapter", PATH)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def canonical_percept_module():
    """Execute the real canonical estimator with synthetic reports and no application runtime."""
    path = PATH.parent.parent / "MedtronicPercept" / "Percept.py"
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "estimateSessionDateTime")
    context = dict(datetime=datetime, np=np)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), context)
    module = types.ModuleType("modules.MedtronicPercept")
    module.Percept = types.SimpleNamespace(estimateSessionDateTime=context["estimateSessionDateTime"])
    return module


class SettingsTests(unittest.TestCase):
    def test_unknown_hemisphere_is_not_off(self):
        self.assertEqual(adapter._stim_state({"amp_mA_Left": 1}), "unknown")
        self.assertEqual(adapter._stim_state({"amp_mA_Left": 1, "amp_mA_Right": 0}), "right_off_left_on")

    def test_duplicate_sources_collapse_and_conflict_refuses(self):
        empty = pd.DataFrame()
        self.assertIs(adapter._reconcile_settings_rows(empty), empty)
        row = dict(t=pd.Timestamp("2025-07-20", tz="UTC"), hemi="Left", amp=1, pw=90, rate=100, cathode="0", source_uid="a")
        rows = pd.DataFrame([row, {**row, "source_uid": "b"}])
        self.assertEqual(len(adapter._reconcile_settings_rows(rows)), 1)
        rows.loc[1, "amp"] = 2
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            adapter._reconcile_settings_rows(rows)

    def test_shared_frequency_model_refuses_different_hemisphere_rates(self):
        rows = pd.DataFrame([dict(t=pd.Timestamp("2025-07-20", tz="UTC"), hemi=h, amp=1, pw=90, rate=f, cathode="0") for h, f in [("Left", 100), ("Right", 130)]])
        with self.assertRaisesRegex(ValueError, "frequencies differ"):
            adapter.exposure_epochs(rows)

    def test_settings_loader_uses_eligible_sources_and_raw_policy_then_bounds(self):
        participant = types.SimpleNamespace(name="RCS08")
        good = types.SimpleNamespace(uid="good", type="MedtronicJSON")
        bad = types.SimpleNamespace(uid="bad", type="MedtronicJSON")
        group = {"ActiveGroup": True, "GroupId": "A", "ProgramSettings": {"RateInHertz": 100, "LeftHemisphere": {"Programs": [{"AmplitudeInMilliAmps": 0, "PulseWidthInMicroSecond": 90}]}}}
        report = {"SessionDate": "2025-07-17T00:00:00Z", "BrainSenseTimeDomain": [{"FirstPacketDateTime": "2025-07-17T02:00:00.000Z"}], "Groups": {"Final": [group]}, "GroupHistory": [{"SessionDate": "2025-01-01T00:00:00Z", "Groups": [group]}, {"SessionDate": "2025-07-16T22:00:00Z", "Groups": [group]}]}
        mod = types.ModuleType("modules")
        mod.DataCurator = types.SimpleNamespace(loadCacheFile=lambda sf: json.dumps({**report, "excluded": sf.uid == "bad"}))
        analysis = types.ModuleType("modules.AnalysisData")
        analysis.eligible_source_files = lambda p: [good, bad] if p is participant else []
        policy = types.ModuleType("modules.RCS08DataPolicy")
        policy.applies_to = lambda participant: getattr(participant, "name", "") == "RCS08"
        policy.IMPLANT_DAY = pd.Timestamp("2025-07-16T07:00:00Z").timestamp()
        policy.source_exclusion = lambda r: "bad source" if r["excluded"] else None
        server = types.ModuleType("Server")
        server.models = object()
        with patch.dict(sys.modules, {"modules": mod, "modules.AnalysisData": analysis, "modules.RCS08DataPolicy": policy, "Server": server, "modules.MedtronicPercept": canonical_percept_module()}):
            stream = adapter.settings_stream(participant)
            # An eligible source may fail before raw policy can run. Do not return the readable
            # source's otherwise valid rows as if they were a complete exposure history.
            mod.DataCurator.loadCacheFile = Mock(side_effect=[json.dumps({**report, "excluded": False}), OSError("synthetic missing file")])
            with self.assertRaisesRegex(RuntimeError, "could not be read completely"):
                adapter.settings_stream(participant)
        self.assertEqual(len(stream), 2)
        self.assertEqual(stream.iloc[0]["source_uid"], "good")
        self.assertEqual(stream.iloc[0]["amp"], 0)
        self.assertGreaterEqual(stream.iloc[0]["t"].timestamp(), policy.IMPLANT_DAY)
        self.assertEqual(stream.loc[stream.src == "session", "t"].iloc[0], pd.Timestamp("2025-07-17T02:00:00Z"))
        self.assertEqual(stream.loc[stream.src == "history", "t"].iloc[0], pd.Timestamp("2025-07-16T22:00:00Z"))

    def test_session_timestamp_preserves_valid_header_and_rejects_missing(self):
        with patch.dict(sys.modules, {"modules.MedtronicPercept": canonical_percept_module()}):
            actual = adapter._session_timestamp({"SessionDate": "2025-07-17T00:00:00.125Z", "SessionEndDate": "2025-07-17T00:05:00Z"})
            self.assertEqual(actual, pd.Timestamp("2025-07-17T00:00:00.125Z"))
            self.assertTrue(pd.isna(adapter._session_timestamp({})))
        nonfinite = types.ModuleType("modules.MedtronicPercept")
        nonfinite.Percept = types.SimpleNamespace(estimateSessionDateTime=lambda report: float("nan"))
        with patch.dict(sys.modules, {"modules.MedtronicPercept": nonfinite}):
            self.assertTrue(pd.isna(adapter._session_timestamp({})))

    def test_supplied_settings_produce_identical_design_without_reload(self):
        stream = pd.DataFrame([dict(t=pd.Timestamp(t, tz="UTC"), hemi=h, amp=a, pw=90, rate=100, cathode="0")
                               for t, a in [("2025-07-20", 1), ("2025-07-22", 2)] for h in ("Left", "Right")])
        pro = pd.DataFrame({"nrs": [0, 8], "_pro_time_utc": pd.to_datetime(["2025-07-21", "2025-07-23"])})
        bs = types.SimpleNamespace(_load_pros=lambda *a: pro, _pro_times_utc_series=lambda p: p._pro_time_utc)
        biomarkers = types.ModuleType("modules.Biomarkers")
        biomarkers.bravo_service = bs
        with patch.dict(sys.modules, {"modules.Biomarkers": biomarkers}), patch.object(adapter, "settings_stream", return_value=stream) as loader:
            first = adapter.build_design_matrix(object())
            loader.assert_called_once()
            loader.reset_mock()
            second = adapter.build_design_matrix(object(), stream=stream)
            loader.assert_not_called()
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(second.n.sum(), 2)
        self.assertEqual(second.nrs.iloc[0], 0)

    def test_service_reuses_same_settings_for_design_queue_and_readiness(self):
        source = PATH.with_name("bravo_service.py")
        tree = ast.parse(source.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_for_participant")
        stream = pd.DataFrame({"synthetic": [1]})
        epochs = pd.DataFrame({"n": [2]})
        mocked_adapter = types.SimpleNamespace(settings_stream=Mock(return_value=stream), build_design_matrix=Mock(return_value=epochs))
        pipeline = types.SimpleNamespace(run=Mock(return_value=types.SimpleNamespace(arms={}, manifest={}, summary=pd.DataFrame())))
        readiness = Mock(return_value={"available": False})
        context = dict(pd=pd, adapter=mocked_adapter, pipeline=pipeline, DEFAULT_SITES=("left_leg",), DEFAULT_HEMISPHERES=("Left",),
                       _log=Mock(), design_matrix_summary=lambda es: {}, _jsonable=lambda value: value, _frame_records=lambda value: [],
                       _blockers=lambda *a: [], closed_loop_readiness=readiness)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), context)
        server = types.ModuleType("Server")
        server.models = types.SimpleNamespace(Participant=types.SimpleNamespace(find=lambda **kw: object()))
        with patch.dict(sys.modules, {"Server": server}):
            result = context["run_for_participant"]({"ParticipantId": "p", "Backend": "none"})
        self.assertTrue(result["available"])
        mocked_adapter.settings_stream.assert_called_once()
        self.assertIs(mocked_adapter.build_design_matrix.call_args.kwargs["stream"], stream)
        self.assertIs(pipeline.run.call_args.kwargs["delivered_census"], stream)
        self.assertIs(readiness.call_args.kwargs["stream"], stream)

    def test_multiplayer_program_is_not_silently_first_program(self):
        group = {"ProgramSettings": {"LeftHemisphere": {"Programs": [{}, {}]}}}
        with self.assertRaisesRegex(ValueError, "interleaved"):
            adapter._unambiguous_group_settings(group)

    def test_single_program_preserves_zero_amplitude(self):
        group = {"ProgramSettings": {"RateInHertz": 100, "LeftHemisphere": {"Programs": [{"AmplitudeInMilliAmps": 0, "PulseWidthInMicroSecond": 90}]}}}
        self.assertEqual(adapter._unambiguous_group_settings(group)["Left"]["amp"], 0)

    def test_sensing_duplicate_missing_and_nonfinite_settings_refuse(self):
        channel = {"HemisphereLocation": "HemisphereLocationDef.Left", "SuspendAmplitudeInMilliAmps": 1,
                   "PulseWidthInMicroSecond": 90, "RateInHertz": 100}
        with self.assertRaisesRegex(ValueError, "unique sensing program"):
            adapter._unambiguous_group_settings({"ProgramSettings": {"SensingChannel": [channel, dict(channel)]}})
        for amp in [None, float("nan")]:
            with self.assertRaisesRegex(ValueError, "missing"):
                adapter._unambiguous_group_settings({"ProgramSettings": {"SensingChannel": [{**channel, "SuspendAmplitudeInMilliAmps": amp}]}})
        self.assertEqual(adapter._unambiguous_group_settings({}), {})


if __name__ == "__main__":
    unittest.main()
