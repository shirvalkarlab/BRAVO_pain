"""The two tidy tables copied from the band-by-length sweep (Track A step 6).

The tables must be the response's numbers, value for value, with the best row per centre flagged and
carrying its evidence, and the no-relationship reference stated on every row. Nothing here runs the
sweep itself; a small synthetic sweep response in the real shape stands in for it, so the test is
about copying faithfully, not about the statistics.
"""
import os
import sys

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
