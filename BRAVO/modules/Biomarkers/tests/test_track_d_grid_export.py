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

Merged here 2026-10-05: test_band_results_tables.py.
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


def test_device_rules_status_states_the_limitation_rather_than_a_verdict():
    note = _bsvc.DEVICE_RULES_STATUS_NOTE
    assert "more stimulation settings needed" in note
    for word in ("blocked", "forbidden", "eligible", "pass", "fail"):
        assert word not in note.lower(), (
            f"DEVICE_RULES_STATUS_NOTE must not read as a verdict; found {word!r} in it")


# --------------------------------------------------------------------------------------------------
# merged from test_band_results_tables.py
# The two tidy tables copied from the band-by-length sweep (Track A step 6).
#
# The tables must be the response's numbers, value for value, with the best row per centre flagged and
# carrying its evidence, and the no-relationship reference stated on every row. Nothing here runs the
# sweep itself; a small synthetic sweep response in the real shape stands in for it, so the test is
# about copying faithfully, not about the statistics.


import os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import band_results_tables as BT      # noqa: E402


def _sweep(channel="ZERO_THREE_RIGHT", seed=0):
    rng = np.random.default_rng(seed)
    centres = [8.5, 9.5, 10.5]
    seconds = [1.0, 5.0, 10.0]
    corr = rng.uniform(-0.5, 0.5, (3, 3)).round(4)
    auc = rng.uniform(0.3, 0.7, (3, 3)).round(4)
    corr[1][2] = np.nan                                     # one cell the sweep could not fill
    n = rng.integers(20, 40, (3, 3))
    best_corr, best_auc = [], []
    for c, centre in enumerate(centres):
        t = int(np.nanargmax(np.abs(np.nan_to_num(corr[:, c]))))
        best_corr.append({"channel": channel, "brain_side": "right", "contacts": "0-3",
                          "band_center_hz": centre, "integration_seconds_requested": seconds[t],
                          "pearson_r": float(corr[t][c]), "pearson_r_low": -0.1,
                          "pearson_r_high": 0.4, "n_resamples_used": 1000, "answer": "not_resolved",
                          "chosen_as_best_of_n_windows": 3, "shuffled_best_of_windows_p95": 0.3,
                          "shuffled_best_of_windows_p99": 0.4, "p_selection_aware": 0.2,
                          "beats_shuffled_best_of_windows_p95": False})
        t = int(np.argmax(np.abs(auc[:, c] - 0.5)))
        best_auc.append({"channel": channel, "brain_side": "right", "contacts": "0-3",
                         "band_center_hz": centre, "integration_seconds_requested": seconds[t],
                         "auc": float(auc[t][c]), "auc_low": 0.45, "auc_high": 0.7,
                         "n_resamples_used": 1000, "answer": "established" if c == 1 else "not_resolved",
                         "interval_spans_no_discrimination": c != 1,
                         "chosen_as_best_of_n_windows": 3, "shuffled_best_of_windows_p95": 0.6,
                         "shuffled_best_of_windows_p99": 0.65, "p_selection_aware": 0.01,
                         "beats_shuffled_best_of_windows_p95": c == 1})
    return {
        "center_freqs_hz": centres, "band_width_hz": 5.0,
        "band_fully_inside_8_to_30_hz": [False, False, True],
        "integration_seconds_requested": seconds, "integration_seconds_delivered": [3.0, 6.0, 9.0],
        "integration_tiles": [1, 2, 3],
        "correlation_grid": [[None if np.isnan(v) else float(v) for v in row] for row in corr],
        "auc_grid": [[float(v) for v in row] for row in auc],
        "auc_direction_folded_grid": [[float(max(v, 1 - v)) for v in row] for row in auc],
        "n_grid": [[int(v) for v in row] for row in n],
        "auc_n_high_grid": [[int(v) // 2 for v in row] for row in n],
        "auc_n_low_grid": [[int(v) - int(v) // 2 for v in row] for row in n],
        "best_correlation_rows": best_corr, "best_auc_rows": best_auc,
        "pain_split_rule": "median split", "pain_low_cut": 4.0, "pain_high_cut": 4.0,
    }


def test_every_grid_cell_becomes_one_row_and_copies_its_value_exactly():
    sweeps = {"ZERO_THREE_RIGHT": _sweep(), "ONE_THREE_LEFT": _sweep("ONE_THREE_LEFT", seed=1)}
    corr = BT.correlation_table(sweeps, metric_key="nrs")
    disc = BT.discrimination_table(sweeps, metric_key="nrs")
    assert len(corr) == 2 * 3 * 3 and len(disc) == 2 * 3 * 3
    assert BT.count_matches(corr, sweeps, "pearson_r", "correlation_grid") == (18, 0)
    assert BT.count_matches(disc, sweeps, "auc", "auc_grid") == (18, 0)
    assert BT.count_matches(disc, sweeps, "auc_direction_folded",
                            "auc_direction_folded_grid") == (18, 0)
    # the cell the sweep could not fill is a missing value, not a zero and not a row dropped
    missing = corr[corr["pearson_r"].isna()]
    assert len(missing) == 2 and set(missing["band_center_hz"]) == {10.5}
    assert set(missing["integration_seconds_requested"]) == {5.0}


def test_the_best_row_per_centre_is_flagged_once_and_carries_its_evidence():
    sweeps = {"ZERO_THREE_RIGHT": _sweep()}
    disc = BT.discrimination_table(sweeps)
    best = disc[disc["is_best_for_centre"]]
    assert len(best) == 3 and sorted(best["band_center_hz"]) == [8.5, 9.5, 10.5]
    row = best[best["band_center_hz"] == 9.5].iloc[0]
    assert row["answer"] == "established" and bool(row["beats_shuffled_best_of_windows_p95"])
    assert row["auc_low"] == 0.45 and row["auc_high"] == 0.7 and row["n_resamples_used"] == 1000
    # the best row's value equals the best row the sweep reported, not a recomputation
    reported = {r["band_center_hz"]: r["auc"] for r in sweeps["ZERO_THREE_RIGHT"]["best_auc_rows"]}
    for _, r in best.iterrows():
        assert r["auc"] == reported[r["band_center_hz"]]
    # every other row leaves the evidence columns empty
    rest = disc[~disc["is_best_for_centre"]]
    assert rest["answer"].isna().all() and rest["auc_low"].isna().all()
    assert (rest["n_resamples_used"] == -1).all()


def test_the_no_relationship_reference_is_on_every_row_and_is_one_half_for_the_auc():
    sweeps = {"ZERO_THREE_RIGHT": _sweep()}
    corr = BT.correlation_table(sweeps)
    disc = BT.discrimination_table(sweeps)
    assert (corr["no_relationship_value"] == 0.0).all()
    assert (disc["no_relationship_value"] == 0.5).all()
    assert (disc["pain_split_rule"] == "median split").all()
    assert (disc["n_high_pain_reports"] + disc["n_low_pain_reports"] == disc["n_pain_reports"]).all()


def test_the_brain_side_and_contacts_are_spelled_out_on_every_row():
    disc = BT.discrimination_table({"ZERO_THREE_RIGHT": _sweep()})
    assert (disc["brain_side"] == "right").all() and (disc["contacts"] == "0-3").all()
    assert (disc["band_low_hz"] == disc["band_center_hz"] - 2.5).all()


def test_a_contact_pair_whose_sweep_could_not_run_contributes_no_rows():
    sweeps = {"ZERO_THREE_RIGHT": _sweep(),
              "ONE_THREE_LEFT": {"answer": "not_assessed", "center_freqs_hz": [],
                                 "correlation_grid": [], "best_auc_rows": []}}
    corr = BT.correlation_table(sweeps)
    assert set(corr["channel"]) == {"ZERO_THREE_RIGHT"}
    assert len(BT.correlation_table({})) == 0
