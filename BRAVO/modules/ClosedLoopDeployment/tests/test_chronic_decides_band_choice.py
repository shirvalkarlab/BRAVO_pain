"""Where the chronic log covers a band, its answer decides the band's choice; where the chronic log and
TD disagree, the chronic log wins (wave 2, C5; the PI, 2026-10-18: "the chronic log may choose").

Every reader that chooses or judges a band off the heat-map grid reads it through
`sweep_settings.choosing_sweep` (the Closed-Loop page's "Choose a band" panel and its prefetch, the
Closed-Loop report's direction check, the Stim Optimizer's pain relationship and its "still positive
without the current" table). A TD-only row whose band the chronic log covers carries
`choice_source: "chronic"` and the chronic answer (`chronic`); the choosing view puts the chronic
correlation, interval and answer in the row's own fields and keeps TD's under `td_values`.

The fixture puts two rows on one pair that disagree in opposite ways:
  * 12.5 Hz: TD not supported (interval spans zero), chronic established and rising with pain;
  * 24.5 Hz: TD supported and rising, chronic falling with pain (established).
On the code before C5 the readers saw TD's answers (12.5 not counted, 24.5 counted).
"""
import pathlib
import sys

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from ClosedLoopDeployment import direction_consistency as dc
from Biomarkers.routines import sweep_settings
from StimOptimizer.routines import pain_relationship as pr

CH = "ONE_THREE_LEFT"


def _chronic(r, lo, hi, answer):
    return {"covered": True, "n_reports": 120, "freq_hz": 24.4, "pearson_r": r,
            "pearson_r_low": lo, "pearson_r_high": hi, "p_rotation": 0.004, "answer": answer,
            "direction": ("band power rises as pain rises" if r > 0 else
                          "band power falls as pain rises"),
            "current_removed_check": {"status": "holds", "partial_r": r * 0.9, "n_pain_reports": 118},
            "words": "decided by the home record (chronic log)"}


def _sweep():
    rows = [
        {"band_center_hz": 12.5, "pearson_r": 0.05, "pearson_r_low": -0.10, "pearson_r_high": 0.20,
         "answer": "not_resolved", "n_pain_reports": 40, "grid_source": "td", "can_choose_band": True,
         "choice_source": "chronic", "chronic": _chronic(0.42, 0.21, 0.60, "established")},
        {"band_center_hz": 24.5, "pearson_r": 0.30, "pearson_r_low": 0.08, "pearson_r_high": 0.50,
         "answer": "established", "n_pain_reports": 40, "grid_source": "td", "can_choose_band": True,
         "choice_source": "chronic", "chronic": _chronic(-0.35, -0.52, -0.15, "established")},
        {"band_center_hz": 15.5, "pearson_r": 0.33, "pearson_r_low": 0.10, "pearson_r_high": 0.52,
         "answer": "established", "n_pain_reports": 40, "grid_source": "td", "can_choose_band": True,
         "choice_source": "TD", "chronic": {"covered": False, "n_reports": 0,
                                            "words": "no home record at this band"}},
    ]
    td = {"center_freqs_hz": [12.5, 15.5, 24.5], "best_correlation_rows": rows,
          "best_auc_rows": []}
    return {"display_short": "L 1-3", "best_correlation_rows": [], "best_auc_rows": [],
            "by_source_grid": {"td": td, "psd": {}}}


def _grid():
    return {"available": True,
            "band_time_sweep": {CH: sweep_settings.choosing_sweep(_sweep())}}


def test_where_chronic_and_td_disagree_chronic_decides():
    rows = {r["band_center_hz"]: r for r in _grid()["band_time_sweep"][CH]["best_correlation_rows"]}
    assert rows[12.5]["pearson_r"] == 0.42 and rows[12.5]["answer"] == "established"
    assert rows[12.5]["td_values"]["pearson_r"] == 0.05            # TD's own kept beside it
    assert rows[24.5]["pearson_r"] == -0.35
    assert rows[24.5]["can_choose_band"] is True
    assert rows[15.5]["pearson_r"] == 0.33 and "td_values" not in rows[15.5]   # not covered: TD
    # the Stim Optimizer's pain relationship (bands whose power rises with pain, supported)
    by = pr.pain_positive_centers_by_channel(_grid())
    assert by[CH] == frozenset({12.5, 15.5}), by
    # the Closed-Loop report's direction check reads the chronic sign
    assert dc.correlation_row_for_band(_grid(), CH, 24.5)["pearson_r"] == -0.35


def test_the_choosing_view_never_changes_the_stored_rows():
    sw = _sweep()
    sweep_settings.choosing_sweep(sw)
    assert sw["by_source_grid"]["td"]["best_correlation_rows"][0]["pearson_r"] == 0.05


def test_the_neutral_setting_reads_td_as_before():
    saved = sweep_settings.CHRONIC_CHOICE
    try:
        sweep_settings.CHRONIC_CHOICE = False
        rows = {r["band_center_hz"]: r
                for r in _grid()["band_time_sweep"][CH]["best_correlation_rows"]}
        assert rows[12.5]["pearson_r"] == 0.05 and "td_values" not in rows[12.5]
        assert pr.pain_positive_centers_by_channel(_grid())[CH] == frozenset({15.5, 24.5})
    finally:
        sweep_settings.CHRONIC_CHOICE = saved


def test_a_constant_current_leaves_the_chronic_answer_as_its_own_current_removed_value():
    """Decision 484: one current on every report leaves nothing to take out, so the plain chronic r
    stands as the value with the current taken out (the Stim Optimizer's 'still positive' table)."""
    sw = _sweep()
    row = sw["by_source_grid"]["td"]["best_correlation_rows"][0]
    row["chronic"]["current_removed_check"] = {"status": "constant current", "partial_r": None,
                                               "n_pain_reports": 120}
    seen = sweep_settings.chronic_decides(row)
    assert seen["pearson_r_adjusted"] == seen["pearson_r"] == 0.42
