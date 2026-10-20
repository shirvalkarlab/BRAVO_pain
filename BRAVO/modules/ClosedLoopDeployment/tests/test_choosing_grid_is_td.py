"""The band is chosen from the TD-only grid; a PSD-only row can never be the chosen band (C4; the PI,
2026-10-18: "PSD-only results shown, cannot choose").

Every reader that chooses or judges a band off the heat-map grid reads it through
`adapter.band_sweep_grid_for_closed_loop` (the Closed-Loop page's "Choose a band" panel and its
prefetch, the Stim Optimizer's pain-relationship half of its readiness rule, the Closed-Loop
report's direction-consistency check) or `adapter.stored_current_adjusted_grid` (the Stim
Optimizer's "still positive without the current" table). Both now serve each pair's TD-only grid
(`by_source_grid.td`) in place of the mixed one ("TD, PSD where no TD").

The fixture puts three different rows at one band: the mixed grid's row and the PSD-only grid's row
both rise with pain with an interval wholly above zero ("supported"), the TD-only row does not. On
the code before C4 the readers served the mixed row, so the band counted as rising with pain.
"""
import pathlib
import sys

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from CacheStore import provenance as prov
from CacheStore import store as st
from ClosedLoopDeployment import adapter
from ClosedLoopDeployment import direction_consistency as dc
from Biomarkers.routines import sweep_settings
from StimOptimizer.routines import pain_relationship as pr

UID = "synthetic-choosing-grid"
CH = "ONE_THREE_LEFT"


def _row(r, lo, hi, source):
    return {"band_center_hz": 12.5, "pearson_r": r, "pearson_r_low": lo, "pearson_r_high": hi,
            "answer": "not_resolved", "auc": 0.5 + r / 2, "source_tag": source}


def _grid(r, lo, hi, source):
    return {"band_width_hz": 5.0, "center_freqs_hz": [12.5],
            "integration_seconds_delivered": [3.0], "n_pain_reports": 40,
            "correlation_grid": [[r]],
            "best_correlation_rows": [_row(r, lo, hi, source)],
            "best_auc_rows": [_row(r, lo, hi, source)]}


def _write(payload, *, adjusted=False):
    tiles_key = st.product_key("raw_lsb_tiles", UID, ("tiles", 1))
    st.store("raw_lsb_tiles", UID, ("tiles", 1), {"tiles": [[0.0]]}, writer="biomarkers")
    report_key = st.product_key("redcap_reports", UID, ("reports", 1))
    st.store("redcap_reports", UID, ("reports", 1), {"pain": [1.0]},
             writer="biomarkers", trigger="fresh_fetch", provenance=[])
    chain = prov.flatten([
        prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers"),
        prov.entry(report_key, kind="redcap_reports", writer="biomarkers")])
    extra = {"sweep_settings": sweep_settings.sweep_settings_tag_from_request({}),
             "metric_label": "NRS (0–10)", "rule_version": sweep_settings.GRID_RULE_VERSION,
             "adjust_for_stim_current": True}
    st.store("biomarker_band_sweep", UID, ("sweep", 1), payload, writer="biomarkers",
             trigger="band_time_sweep", provenance=chain, fmt="pickle", extra=extra)


def _payload():
    mixed = _grid(0.5, 0.2, 0.7, "mixed")
    mixed["display_short"] = "L 1⁻3⁺"
    mixed["by_source_grid"] = {"td": _grid(0.1, -0.2, 0.35, "td"),
                               "psd": _grid(0.6, 0.3, 0.8, "psd")}
    return {"band_time_sweep": {CH: mixed}}


def test_the_closed_loop_grid_serves_the_td_only_rows(grid_sandbox):
    _write(_payload())
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    sw = got["band_time_sweep"][CH]
    assert [r["source_tag"] for r in sw["best_correlation_rows"]] == ["td"]
    assert [r["source_tag"] for r in sw["best_auc_rows"]] == ["td"]
    assert sw["correlation_grid"] == [[0.1]]
    assert sw["choosing_grid"] == "td"
    # the pair's labels stay; the other two grids are not carried to the choosing pages
    assert sw["display_short"] == "L 1⁻3⁺"
    assert "by_source_grid" not in sw


def test_a_psd_only_row_cannot_be_the_chosen_band(grid_sandbox):
    """The mixed and PSD-only rows at 12.5 Hz are "supported"; the TD-only row is not. The Stim
    Optimizer's pain relationship and the Closed-Loop direction check must not count the band."""
    _write(_payload())
    grid = adapter.band_sweep_grid_for_closed_loop(UID)
    assert pr.pain_positive_centers_by_channel(grid) == {CH: frozenset()}
    row = dc.correlation_row_for_band(grid, CH, 12.5)
    assert row["source_tag"] == "td" and row["pearson_r"] == 0.1


def test_the_stored_current_adjusted_grid_serves_the_td_only_rows_too(grid_sandbox):
    _write(_payload())
    adj = adapter.stored_current_adjusted_grid(UID)
    assert adj["available"] is True
    assert [r["source_tag"] for r in adj["band_time_sweep"][CH]["best_correlation_rows"]] == ["td"]


def test_a_pair_with_no_td_only_grid_chooses_nothing(grid_sandbox):
    """A pair whose sweep carries no TD-only grid (its statistics failed, say) offers no band to
    choose, rather than falling back to the mixed rows, which hold PSD-only reports."""
    p = _payload()
    del p["band_time_sweep"][CH]["by_source_grid"]["td"]
    _write(p)
    sw = adapter.band_sweep_grid_for_closed_loop(UID)["band_time_sweep"][CH]
    assert sw["best_correlation_rows"] == [] and sw["best_auc_rows"] == []
    assert sw["choosing_grid"] == "none"
    assert sw["choosing_grid_reason"]


def test_the_neutral_setting_serves_the_mixed_rows(grid_sandbox, monkeypatch):
    monkeypatch.setattr(sweep_settings, "CHOOSING_GRID", "mixed")
    _write(_payload())
    sw = adapter.band_sweep_grid_for_closed_loop(UID)["band_time_sweep"][CH]
    assert [r["source_tag"] for r in sw["best_correlation_rows"]] == ["mixed"]
