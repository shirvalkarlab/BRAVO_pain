"""Track D, task D2(b): the cross-setting-stability column on the calibrated grid -- the Biomarkers
side, which computes and attaches the RAW (untranslated) stability result only.

WHY THIS FILE DOES NOT IMPORT `ClosedLoopDeployment.stability`. That module's own docstring states
the dependency direction as a hard rule: "it imports from Biomarkers, and Biomarkers must never
import it back, because that would be a loop neither module could load out of." An earlier draft of
`bravo_service.band_stability_finding_for_point` broke that rule by importing
`ClosedLoopDeployment.stability` from inside Biomarkers -- caught when the container (which loads
`Biomarkers.bravo_service` but never `ClosedLoopDeployment`) could not import it. The honest
four-valued TRANSLATION now lives entirely on the Closed-Loop Deployment side
(`ClosedLoopDeployment/tests/test_track_d_grid_stability_translation.py` proves that half, against
`adapter.py`'s own inline computation), and this file proves only that the RAW result Biomarkers
attaches to the grid is identical to what `_validate_band_core` itself already returns -- no new
statistics, no new import direction.

No pytest here (container plain-assert convention); every `test_*` function is a bare function
`_agent_bridge/run_tests.py` calls directly.
"""
import sys
import pathlib

_HERE = pathlib.Path(__file__).resolve().parents[1]
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from Biomarkers import bravo_service as _bsvc


class _PatchValidateBandCore:
    """Swap `bravo_service._validate_band_core` for a stub, and put the original back on exit --
    this suite has no pytest monkeypatch fixture available."""

    def __init__(self, stim_result, available=True, reason=None, requests=None):
        self._stim = stim_result
        self._available = available
        self._reason = reason
        self._requests = requests if requests is not None else []

    def __enter__(self):
        self._orig = _bsvc._validate_band_core

        def _stub(request_data):
            self._requests.append(dict(request_data))
            if not self._available:
                return {"available": False, "reason": self._reason}
            return {"available": True, "stim": self._stim}

        _bsvc._validate_band_core = _stub
        return self

    def __exit__(self, *exc):
        _bsvc._validate_band_core = self._orig
        return False


# --------------------------------------------------------------------------------------------
# `raw_stability_result_for_point` is a thin, literal pass-through of `_validate_band_core`'s own
# "stim" field -- no new statistics, so this is an equality proof against `_validate_band_core`
# itself, called directly, on the same inputs.
# --------------------------------------------------------------------------------------------

def test_raw_result_is_identical_to_validate_band_cores_own_stim_field():
    stim = {"available": True, "lrt_p": 0.72,
            "equivalence": {"verdict": "stable", "margin_log_or": 0.6931471805599453}}
    with _PatchValidateBandCore(stim):
        got = _bsvc.raw_stability_result_for_point("uid", "ZERO_TWO_LEFT", 18.5, 5.0)
        want = _bsvc._validate_band_core({
            "ParticipantId": "uid", "Channel": "ZERO_TWO_LEFT",
            "CenterHz": 18.5, "BandWidthHz": 5.0})["stim"]
    assert got == want, f"the grid's raw field diverged from _validate_band_core's own stim: {got} != {want}"


def test_raw_result_reports_the_reason_when_validate_band_core_is_unavailable():
    with _PatchValidateBandCore(None, available=False, reason="no PSD samples for this participant"):
        got = _bsvc.raw_stability_result_for_point("uid", "ZERO_THREE_RIGHT", 26.5, 5.0)
    assert got == {"available": False, "reason": "no PSD samples for this participant"}


def test_raw_result_falls_back_to_a_reason_when_validate_band_core_gives_no_reason():
    with _PatchValidateBandCore(None, available=False, reason=None):
        got = _bsvc.raw_stability_result_for_point("uid", "ZERO_THREE_RIGHT", 26.5, 5.0)
    assert got["available"] is False
    assert got["reason"]                                          # never blank


def test_a_raising_validate_band_core_is_caught_and_reported_never_raised():
    def _boom(request_data):
        raise RuntimeError("simulated failure")
    orig = _bsvc._validate_band_core
    _bsvc._validate_band_core = _boom
    try:
        got = _bsvc.raw_stability_result_for_point("uid", "ZERO_TWO_LEFT", 8.5, 5.0)
    finally:
        _bsvc._validate_band_core = orig
    assert got["available"] is False
    assert "simulated failure" in got["reason"]


def test_the_point_asked_for_is_the_point_validate_band_core_is_called_with():
    """Confirms the channel/centre/width actually reach `_validate_band_core` unchanged -- this is
    the whole reason this is an equality proof and not a fresh implementation: the point identity
    must travel through untouched."""
    stim = {"available": True, "lrt_p": 0.5}
    seen = []
    with _PatchValidateBandCore(stim, requests=seen):
        _bsvc.raw_stability_result_for_point("RCS08uid", "ONE_THREE_LEFT", 12.5, 5.0)
    assert len(seen) == 1
    assert seen[0]["ParticipantId"] == "RCS08uid"
    assert seen[0]["Channel"] == "ONE_THREE_LEFT"
    assert seen[0]["CenterHz"] == 12.5
    assert seen[0]["BandWidthHz"] == 5.0


# --------------------------------------------------------------------------------------------
# `_attach_grid_export_columns`: one lookup per unique (channel, centre), never once per row
# --------------------------------------------------------------------------------------------

def test_attach_grid_export_columns_fills_both_new_fields_on_every_row_once_per_centre():
    """The correlation and AUC grids name the same 22 centres, so a naive per-row implementation
    would pay for the stability lookup twice at every centre. This must not happen."""
    calls = []
    orig = _bsvc.raw_stability_result_for_point

    def _counting(participant_uid, channel, center_hz, band_width_hz=5.0):
        calls.append((channel, center_hz))
        return {"available": False, "reason": "stub"}

    _bsvc.raw_stability_result_for_point = _counting
    try:
        sweeps = {
            "ZERO_TWO_LEFT": {
                "best_correlation_rows": [{"band_center_hz": 8.5}, {"band_center_hz": 13.5}],
                "best_auc_rows": [{"band_center_hz": 8.5}, {"band_center_hz": 13.5}],
            }
        }
        _bsvc._attach_grid_export_columns("uid", sweeps, band_width_hz=5.0)
    finally:
        _bsvc.raw_stability_result_for_point = orig

    assert len(calls) == 2, f"expected exactly one lookup per unique centre, got {calls}"
    for row in (sweeps["ZERO_TWO_LEFT"]["best_correlation_rows"]
                + sweeps["ZERO_TWO_LEFT"]["best_auc_rows"]):
        assert row["cross_setting_stability_raw"] == {"available": False, "reason": "stub"}
        assert row["device_rules_status"] == _bsvc.DEVICE_RULES_STATUS_NOTE


def test_attach_grid_export_columns_keeps_channels_independent():
    """A stability lookup is per (channel, centre), never shared ACROSS channels -- the same centre
    on two different sensing contact pairs is two different measurements."""
    calls = []
    orig = _bsvc.raw_stability_result_for_point

    def _counting(participant_uid, channel, center_hz, band_width_hz=5.0):
        calls.append((channel, center_hz))
        return {"available": False, "reason": f"{channel}@{center_hz}"}

    _bsvc.raw_stability_result_for_point = _counting
    try:
        sweeps = {
            "ZERO_TWO_LEFT": {"best_correlation_rows": [{"band_center_hz": 8.5}], "best_auc_rows": []},
            "ONE_THREE_LEFT": {"best_correlation_rows": [{"band_center_hz": 8.5}], "best_auc_rows": []},
        }
        _bsvc._attach_grid_export_columns("uid", sweeps, band_width_hz=5.0)
    finally:
        _bsvc.raw_stability_result_for_point = orig

    assert set(calls) == {("ZERO_TWO_LEFT", 8.5), ("ONE_THREE_LEFT", 8.5)}
    assert sweeps["ZERO_TWO_LEFT"]["best_correlation_rows"][0]["cross_setting_stability_raw"][
        "reason"] == "ZERO_TWO_LEFT@8.5"
    assert sweeps["ONE_THREE_LEFT"]["best_correlation_rows"][0]["cross_setting_stability_raw"][
        "reason"] == "ONE_THREE_LEFT@8.5"


# --------------------------------------------------------------------------------------------
# D2(a): confirm the honest note is what is attached, never a fabricated pass/fail
# --------------------------------------------------------------------------------------------

def test_device_rules_status_states_the_limitation_rather_than_a_verdict():
    note = _bsvc.DEVICE_RULES_STATUS_NOTE
    assert "not assessable" in note
    for word in ("blocked", "forbidden", "eligible", "pass", "fail"):
        assert word not in note.lower(), (
            f"DEVICE_RULES_STATUS_NOTE must not read as a verdict; found {word!r} in it")
