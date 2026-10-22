"""The Closed-Loop reader and the sign-off summary carry each band's q across the band choices
(wave 2, C9; a label and warning only; `Biomarkers/routines/family_correction.py`).

`adapter.band_sweep_grid_for_closed_loop` serves each pair's choosing grid (TD-only, the chronic
answer where it decides) and now puts the q on it, with the family's pairs read from the sensing
rule with today's contacts; the summary's band q comes from the same stored grid. Nothing that
decides moves: the rows are the same as with the switch off, apart from the new fields and the
appended warning.
"""
import copy
import pathlib
import sys

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from CacheStore import provenance as prov
from CacheStore import store as st
from ClosedLoopDeployment import adapter
from Biomarkers.routines import family_correction as FC
from Biomarkers.routines import sweep_settings
from DecodeCommon import sensing_rule as SR

UID = "2e3c75c00d7f4f37b53a048d195f11da"
CENTRES = [8.5 + k for k in range(22)]


def _grid(ch, p0):
    rows = [{"channel": ch, "band_center_hz": c, "pearson_r": 0.4, "pearson_r_low": 0.1,
             "pearson_r_high": 0.6, "answer": "not_resolved", "p_selection_aware": p0 + 0.01 * i,
             "why": "td why", "choice_source": "TD", "chronic": {"covered": False}}
            for i, c in enumerate(CENTRES)]
    return {"band_width_hz": 5.0, "center_freqs_hz": CENTRES, "best_correlation_rows": rows,
            "best_auc_rows": [dict(r) for r in rows]}


def _payload():
    out = {}
    for ch, disp, p0 in (("ZERO_THREE_LEFT", "L 0⁻3⁺", 0.02), ("ZERO_THREE_RIGHT", "R 0⁻3⁺", 0.03),
                         ("ONE_THREE_LEFT", "L 1⁻3⁺", 0.001)):
        mixed = _grid(ch, 0.5)
        mixed["display_short"] = disp
        mixed["by_source_grid"] = {"td": _grid(ch, p0), "psd": _grid(ch, 0.9)}
        out[ch] = mixed
    return {"band_time_sweep": out}


def _write(payload):
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


def _rule(_uid):
    return SR.sensing_rule_block({"Left": {1, 2}, "Right": {1, 2}})


def _strip_rows(rows):
    out = []
    for r in rows:
        r = {k: v for k, v in r.items() if k not in FC.ROW_FIELDS + FC.AUC_ROW_FIELDS}
        if FC.WARNING_HEAD in str(r.get("why")):
            r["why"] = r["why"][:r["why"].index(". " + FC.WARNING_HEAD)]
        out.append(r)
    return out


def test_the_closed_loop_grid_carries_q_from_the_allowed_pairs(grid_sandbox, monkeypatch):
    _write(_payload())
    monkeypatch.setattr(FC, "rule_block_for_participant", _rule)
    got = adapter.band_sweep_grid_for_closed_loop(UID)
    blk = got["family_correction"]
    assert blk["allowed_pairs"] == ["ZERO_THREE_LEFT", "ZERO_THREE_RIGHT"]
    assert blk["n_in_family"] == 44 and blk["n_built"] == 66
    assert blk["words"].startswith("corrected within each pair separately: L 0⁻3⁺ across 22 bands; "
                                    "R 0⁻3⁺ across 22 bands (66 built")
    assert {k: v["n_in_family"] for k, v in blk["per_pair"].items()} == {
        "ZERO_THREE_LEFT": 22, "ZERO_THREE_RIGHT": 22}
    left = got["band_time_sweep"]["ZERO_THREE_LEFT"]["best_correlation_rows"]
    assert all(r["family_q_status"] == FC.STATUS_IN for r in left)
    assert all(isinstance(r["family_q"], float) for r in left)
    # supported (rises, interval above zero) with q above 0.05: warned, on the choosing view
    assert all(r["family_q"] > 0.05 for r in left[5:])
    assert all(r["why"] == "td why. " + r["family_q_warning"] for r in left[5:])
    outside = got["band_time_sweep"]["ONE_THREE_LEFT"]["best_correlation_rows"]
    assert all(r["family_q"] is None and r["family_q_status"] == FC.STATUS_NOT_ALLOWED
               for r in outside)
    # the separate area-under-the-curve family on the choosing view: its own q, its own block
    lauc = got["band_time_sweep"]["ZERO_THREE_LEFT"]["best_auc_rows"]
    assert all(r["family_q_auc_status"] == FC.STATUS_AUC_IN and r["family_n_auc"] == 22
               and r["family_q"] is None for r in lauc)
    assert {k: v["n_in_family"] for k, v in blk["per_pair_auc"].items()} == {
        "ZERO_THREE_LEFT": 22, "ZERO_THREE_RIGHT": 22}
    assert all(r["family_q_auc"] is None for r in
               got["band_time_sweep"]["ONE_THREE_LEFT"]["best_auc_rows"])
    # with the switch off the rows are the same apart from the new fields and the warning
    monkeypatch.setattr(FC, "ENABLED", False)
    off = adapter.band_sweep_grid_for_closed_loop(UID)
    assert "family_correction" not in off
    for ch in ("ZERO_THREE_LEFT", "ZERO_THREE_RIGHT", "ONE_THREE_LEFT"):
        for key in ("best_correlation_rows", "best_auc_rows"):
            assert _strip_rows(got["band_time_sweep"][ch][key]) == off["band_time_sweep"][ch][key]
            assert not any(k in r for r in off["band_time_sweep"][ch][key]
                           for k in FC.ROW_FIELDS + FC.AUC_ROW_FIELDS)


def test_the_summary_reads_its_band_q_from_the_stored_grid_and_never_builds_one(monkeypatch):
    payload = _payload()
    kept = copy.deepcopy(payload)
    calls = []

    def _load(kind, uid, *, consumer=None, match=None, **kw):
        calls.append(kind)
        meta = {"extra": {"sweep_settings": sweep_settings.sweep_settings_tag_from_request({}),
                          "rule_version": sweep_settings.GRID_RULE_VERSION}}
        return (payload, meta) if match(meta) else (None, None)

    monkeypatch.setattr(FC, "rule_block_for_participant", _rule)
    b = FC.summary_block(UID, {}, "ZERO_THREE_LEFT", 12.5, load_newest=_load)
    assert calls == [sweep_settings.GRID_KIND]          # found at its own direction, one read
    assert b["family_q_status"] == FC.STATUS_IN and isinstance(b["family_q"], float)
    assert b["family_p"] == 0.02 + 0.01 * 4
    assert b["words"].startswith("corrected within each pair separately")
    assert payload == kept                                   # the stored grid is not changed
    assert b["grid_match_direction"] == sweep_settings.sweep_settings_tag_from_request({})["match_direction"]
    # the summary's own "prior" direction: the grid at the page's direction is read, and named
    pb = FC.summary_block(UID, {"MatchDirection": "prior"}, "ZERO_THREE_LEFT", 12.5, load_newest=_load)
    assert pb["family_q"] == b["family_q"] and pb["grid_match_direction"] != "prior"
    # another score's settings: no stored grid, so no q (and nothing is built)
    nb = FC.summary_block(UID, {"LabelMetric": "vas"}, "ZERO_THREE_LEFT", 12.5, load_newest=_load)
    assert nb["family_q"] is None and "no stored grid" in nb["family_q_status"]
