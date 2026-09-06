"""Synthetic adapter contracts; no database, source files, or network are read.

The service helpers are compiled from their production AST to keep this narrow test runnable
without configuring Django. Full service/API coverage is a separate integration gate.
"""
import ast
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "modules/Biomarkers/bravo_service.py"


def helpers(*names, **extra):
    tree = ast.parse(SERVICE.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = {"pd": pd, "np": np, "os": os, **extra}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SERVICE), "exec"), ns)
    return ns


class CanonicalInputTests(unittest.TestCase):
    def test_availability_has_identical_records_without_background_welch(self):
        pool = types.SimpleNamespace(submit=Mock())
        record = {"channel": "Left01", "t_start": 100., "dur_s": 5.}
        pro = pd.DataFrame({"nrs": [0]})
        availability = types.SimpleNamespace(
            extract_availability=lambda *a, **kw: [dict(record)],
            pain_series=lambda *a: {"metric": "nrs", "t": [100.], "y": [0.]},
            stim_series=lambda *a: {"t": [], "y": []},
            analytics=types.SimpleNamespace(power_center_freqs=lambda r: {}),
            lsb_series=lambda *a, **kw: {}, lsb_overview=lambda data: {},
            present_freq_bands=lambda records: [], event_markers=lambda events: {"events": [], "n": 0},
            inspector_samples=lambda *a, **kw: {})
        ns = helpers("_build_availability", "availability_for_participant", availability=availability,
                     _load_recordings=lambda *a: [], _build_sensing_config_index=lambda r: {},
                     _event_psd_index=lambda *a, **kw: [], _event_psd_lsb_blocks=lambda *a, **kw: [],
                     _pro_lsb_by_channel=lambda *a: {}, _load_patient_events=lambda p: [],
                     _load_montage_psd_events=lambda *a, **kw: [], _psd_sample_index=lambda *a, **kw: [],
                     _all_pro_times=lambda p: np.array([100.]), _PSD_WARM_POOL=pool, warm_psd_cache=Mock(),
                     _log=Mock(), AVAILABILITY_PSD_TYPES=["psd"], TIMEDOMAIN_TYPES=["td"],
                     CHRONIC_TYPES=["chronic"], POWERDOMAIN_TYPES=["power"], DISPLAY_STREAMING_EVENT="streaming",
                     models=types.SimpleNamespace(Participant=types.SimpleNamespace(find=lambda **kw: object())),
                     DEMO_MRN="DEMO", BIOMARKER_METRICS=["nrs"], _load_pros=lambda *a: pro,
                     _resolve_biomarker_metric=lambda req, data: (data, "nrs", None),
                     _derive_chan_order=lambda data: [], _recorded_powers=lambda data: [], _region_map=lambda *a: {})
        # The actual old opt-in path demonstrably submits work, so the no-dispatch assertion
        # below cannot pass merely because a mock never reached the warm branch.
        previous = ns["_build_availability"]("p", chronic_list=[], powerdomain_list=[], td_list=[],
                                              pro_df=pro, label_metric="nrs", region_map={}, warm=True)
        pool.submit.assert_called_once()
        pool.submit.reset_mock()
        actual = ns["availability_for_participant"]({"ParticipantId": "p"})
        pool.submit.assert_not_called()
        self.assertEqual(actual["availability"], previous)
        self.assertEqual(actual["availability"]["records"], [record])
        self.assertEqual(actual["availability"]["pain"]["y"], [0.])
        self.assertIsNone(actual["message"])

    def test_source_delegation_and_nonpolicy_participant_bounds(self):
        analysis = types.ModuleType("modules.AnalysisData")
        analysis.eligible_source_files = Mock(return_value=["approved"])
        policy = types.ModuleType("modules.RCS08DataPolicy")
        policy.applies_to = lambda p: False
        finder = Mock(return_value=[])
        ns = helpers("_eligible_sources", "_eligible_recordings", "_eligible_time",
                     models=types.SimpleNamespace(Recording=types.SimpleNamespace(find_all=finder)))
        participant = object()
        with patch.dict(sys.modules, {"modules.AnalysisData": analysis, "modules.RCS08DataPolicy": policy}):
            self.assertEqual(ns["_eligible_sources"](participant), ["approved"])
            analysis.eligible_source_files.assert_called_once_with(participant)
            ns["_eligible_recordings"](participant, date__gte=42)
            finder.assert_called_once_with(date__gte=42)
            self.assertTrue(ns["_eligible_time"](participant, 0))
            for bad in [None, "bad timestamp", float("inf")]:
                self.assertFalse(ns["_eligible_time"](participant, bad))

    def test_alignment_of_list_and_changed_offset_does_not_accumulate(self):
        ns = helpers("_aligned_recording_payload", "_recording_alignment", CHRONIC_TYPES=["chronic"])
        rec = types.SimpleNamespace()
        result = ns["_aligned_recording_payload"]([None, {}, {"StartTime": 100}], rec)
        self.assertIsNone(result[0])
        self.assertNotIn("StartTime", result[1])
        self.assertNotIn("RecordingType", result[1])
        self.assertEqual(result[2]["StartTime"], 100)
        rec.adjusted_alignment = 5
        first = ns["_aligned_recording_payload"](result[2], rec)
        rec.adjusted_alignment = -2
        corrected = ns["_aligned_recording_payload"](first, rec)
        self.assertEqual(corrected["StartTime"], 98)
        self.assertEqual(first["StartTime"], 105)

    def test_atomic_write_failure_retains_previous_file_and_removes_own_temp(self):
        save = helpers("_atomic_savez")["_atomic_savez"]
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "result.npz")
            save(path, value=np.array([7]))
            for dependency in ["numpy.savez", "os.replace"]:
                with patch(dependency, side_effect=OSError("synthetic write failure")):
                    with self.assertRaises(OSError):
                        save(path, value=np.array([99]))
                with np.load(path) as result:
                    self.assertEqual(result["value"].item(), 7)
                self.assertEqual(os.listdir(directory), ["result.npz"])

    def test_policy_content_fixture_identity_and_database_failure(self):
        modules = types.ModuleType("modules")
        policy = types.ModuleType("modules.RCS08DataPolicy")
        modules.RCS08DataPolicy = policy
        analysis = types.ModuleType("modules.AnalysisData")
        analysis.input_manifest = Mock()
        finder = Mock(return_value=None)
        ns = helpers("_policy_identity", "_analysis_identity", models=types.SimpleNamespace(Participant=types.SimpleNamespace(find=finder)))
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"modules": modules, "modules.AnalysisData": analysis}):
            path = Path(directory) / "policy.py"
            policy.__file__ = str(path)
            path.write_text("reviewed policy one")
            first = ns["_analysis_identity"](None)
            self.assertTrue(first.startswith("library-fixture:"))
            path.write_text("reviewed policy two")
            self.assertNotEqual(first, ns["_analysis_identity"](None))
            analysis.input_manifest.assert_not_called()
            finder.side_effect = RuntimeError("synthetic database failure")
            with self.assertRaisesRegex(RuntimeError, "database failure"):
                ns["_analysis_identity"]("real-participant")

    def test_event_manifest_failure_cannot_produce_cache_identity(self):
        routines = types.ModuleType("canonical_fixture.routines")
        routines.streaming_psd = types.SimpleNamespace(WELCH_MAX_SECONDS=60)
        ns = helpers("_psd_matrix_signature_orm", __package__="canonical_fixture",
                     _recording_rows_for_psd=lambda p: [], _CHANNEL_CANON_VERSION="fixture",
                     _TD_MISSING_VERSION="fixture", _INPUT_COMPLETENESS_VERSION="complete_inputs_v1",
                     _analysis_identity=lambda p: "reviewed-inputs", _log=Mock(),
                     models=types.SimpleNamespace(Participant=types.SimpleNamespace(find=Mock(side_effect=RuntimeError("synthetic DB failure")))))
        with patch.dict(sys.modules, {"canonical_fixture.routines": routines}):
            with self.assertRaisesRegex(RuntimeError, "event provenance could not be read completely"):
                ns["_psd_matrix_signature_orm"]("p")

    def test_recording_read_failure_never_returns_partial_cohort(self):
        recordings = [types.SimpleNamespace(pointer="valid", hashed="a"), types.SimpleNamespace(pointer="missing", hashed="b")]
        database = types.SimpleNamespace(loadSourceFile=Mock(side_effect=[{}, OSError("synthetic failure")]))
        ns = helpers("_load_recordings", models=types.SimpleNamespace(Participant=types.SimpleNamespace(find=lambda **kw: object())),
                     _eligible_sources=lambda p: [object()], _eligible_recordings=lambda *a, **kw: recordings,
                     Database=database, _aligned_recording_payload=lambda data, rec: data,
                     _loader_threads=lambda: 1, ThreadPoolExecutor=ThreadPoolExecutor, _log=Mock())
        with self.assertRaisesRegex(RuntimeError, "could not be read completely"):
            ns["_load_recordings"]("p", ["neural"])
        database.loadSourceFile.side_effect = [[], []]
        self.assertEqual(ns["_load_recordings"]("p", ["neural"]), [])

    def test_failed_decode_cannot_persist_empty_psd_and_can_retry(self):
        database = types.SimpleNamespace(loadSourceFile=Mock(side_effect=OSError("synthetic failure")))
        rec = types.SimpleNamespace(pointer="missing", hashed="a")
        save, event_rows = Mock(), Mock(return_value=[])
        ns = helpers("_assemble_psd_rows_cached", __package__="canonical_fixture",
                     _recording_rows_for_psd=lambda p: [{"rec": rec, "uid": "r", "hash": "a", "source": "TD streaming"}],
                     _recording_psd_cache_path=lambda *a: "/synthetic/absent.npz", Database=database,
                     _aligned_recording_payload=lambda data, rec: data, _loader_threads=lambda: 1,
                     ThreadPoolExecutor=ThreadPoolExecutor, _log=Mock(), _welch_rows_into=Mock(),
                     _save_recording_psd_rows=save, _build_sensing_config_index_from_rows=lambda rows: {},
                     _event_psd_rows=event_rows)
        routines = types.ModuleType("canonical_fixture.routines")
        routines.streaming_psd = Mock()
        with patch.dict(sys.modules, {"canonical_fixture.routines": routines}):
            with self.assertRaisesRegex(RuntimeError, "source data could not be read completely"):
                ns["_assemble_psd_rows_cached"]("p", force_recompute=True)
            save.assert_not_called()
            event_rows.assert_not_called()
            database.loadSourceFile.side_effect = None
            database.loadSourceFile.return_value = []
            self.assertEqual(ns["_assemble_psd_rows_cached"]("p", force_recompute=True), ([], 0, 1))
            save.assert_called_once_with("/synthetic/absent.npz", [])
            event_rows.side_effect = RuntimeError("synthetic DB failure")
            with self.assertRaisesRegex(RuntimeError, "event data could not be read completely"):
                ns["_assemble_psd_rows_cached"]("p", force_recompute=True)

    def test_production_ignores_injected_rows_and_preserves_exact_frame(self):
        frame = pd.DataFrame({"nrs": [0.0, np.nan, 8.0], "_pro_time_utc": pd.to_datetime(["2025-07-17", "2025-07-18", "2025-07-19"])})
        canonical = Mock(return_value=frame)
        module = types.ModuleType("modules.AnalysisData")
        module.canonical_pros = canonical
        with patch.dict(sys.modules, {"modules.AnalysisData": module}):
            result = helpers("_load_pros_raw")["_load_pros_raw"]({"ProcessedPRO": [{"nrs": 99}], "RedcapFieldMap": {}}, object())
        self.assertIs(result, frame)
        self.assertEqual(result.nrs.iloc[0], 0)
        self.assertTrue(pd.isna(result.nrs.iloc[1]))
        canonical.assert_called_once()

    def test_fixture_does_not_pull_even_when_credentials_exist(self):
        fn = helpers("_load_pros_raw")["_load_pros_raw"]
        with patch.dict(os.environ, {"REDCAP_API_URL": "https://invalid.test", "REDCAP_API_TOKEN": "fixture"}):
            self.assertIsNone(fn({}))
            self.assertEqual(fn({"ProcessedPRO": [{"nrs": 0}]}).nrs.iloc[0], 0)

    def test_recording_and_event_bounds_include_implant_day(self):
        policy = types.ModuleType("modules.RCS08DataPolicy")
        policy.applies_to = lambda participant: getattr(participant, "name", "") == "RCS08"
        policy.IMPLANT_DAY = 1000
        find = Mock(return_value=[])
        models = types.SimpleNamespace(Recording=types.SimpleNamespace(find_all=find))
        ns = helpers("_eligible_recordings", "_eligible_time", models=models)
        participant = types.SimpleNamespace(name="RCS08")
        with patch.dict(sys.modules, {"modules.RCS08DataPolicy": policy}):
            ns["_eligible_recordings"](participant, type="neural")
            self.assertEqual(find.call_args.kwargs, {"type": "neural", "date__gte": 1000})
            self.assertFalse(ns["_eligible_time"](participant, 999))
            self.assertTrue(ns["_eligible_time"](participant, 1000))
            self.assertFalse(ns["_eligible_time"](participant, np.nan))

    def test_concurrent_npz_writers_never_mix_arrays_or_leave_temp(self):
        save = helpers("_atomic_savez")["_atomic_savez"]
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "result.npz")
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda i: save(path, a=np.full(500, i), b=np.full(500, i)), range(40)))
            with np.load(path) as result:
                np.testing.assert_array_equal(result["a"], result["b"])
                self.assertEqual(len(set(result["a"])), 1)
            self.assertEqual(os.listdir(directory), ["result.npz"])

    def test_alignment_applies_once_to_derived_times_preserves_original_and_fs(self):
        ns = helpers("_aligned_recording_payload", "_recording_alignment", CHRONIC_TYPES=["MedtronicChronicBrainSense"])
        align = ns["_aligned_recording_payload"]
        rec = types.SimpleNamespace(uid="r", type="MedtronicBrainSenseTimeDomain", adjusted_alignment=5, fs_scaling_factor=2)
        original = {"StartTime": 100, "Time": np.array([0, 1]), "Data": np.array([[0], [3]]), "SamplingRate": 250}
        shifted = align(original, rec)
        self.assertEqual(shifted["StartTime"], 105)
        self.assertEqual(shifted["RecordingType"], rec.type)
        np.testing.assert_array_equal(shifted["Time"], [0, 1])
        self.assertEqual(align(shifted, rec)["StartTime"], 105)
        self.assertEqual(original["StartTime"], 100)
        self.assertEqual(shifted["SamplingRate"], 250)
        np.testing.assert_array_equal(shifted["Data"], original["Data"])
        rec.type = "MedtronicChronicBrainSense"
        original["Time"] = np.array([100, 110])
        shifted = align(original, rec)
        np.testing.assert_array_equal(shifted["Time"], [105, 115])
        np.testing.assert_array_equal(align(shifted, rec)["Time"], [105, 115])
        np.testing.assert_array_equal(original["Time"], [100, 110])

    def test_pro_timestamp_signature_retains_subsecond_corrections(self):
        signature = helpers("_pro_set_signature")["_pro_set_signature"]
        original = signature([1752778800.10, 1752779800.0])
        self.assertEqual(original, signature([1752779800.0, 1752778800.10, 1752778800.10]))
        self.assertNotEqual(original, signature([1752778800.20, 1752779800.0]))
        for empty in [None, [], [np.nan, np.inf]]:
            self.assertEqual(signature(empty), "")

    def test_alignment_changes_per_record_cache_identity(self):
        ns = helpers("_recording_alignment", "_recording_analysis_hash", json=json)
        rec = types.SimpleNamespace(hashed="same-data", adjusted_alignment=0, fs_scaling_factor=1)
        before = ns["_recording_analysis_hash"](rec)
        rec.adjusted_alignment = 4
        self.assertNotEqual(before, ns["_recording_analysis_hash"](rec))
        rec.adjusted_alignment = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            ns["_recording_analysis_hash"](rec)

    def test_manifest_fingerprint_drives_analysis_identity(self):
        module = types.ModuleType("modules.AnalysisData")
        module.input_manifest = Mock(return_value={"fingerprint": "first"})
        participant = object()
        models = types.SimpleNamespace(Participant=types.SimpleNamespace(find=Mock(return_value=participant)))
        identity = helpers("_analysis_identity", models=models)["_analysis_identity"]
        with patch.dict(sys.modules, {"modules.AnalysisData": module}):
            self.assertEqual(identity("p"), "first")
            module.input_manifest.return_value = {"fingerprint": "after-qc"}
            self.assertEqual(identity("p"), "after-qc")


if __name__ == "__main__":
    unittest.main()
