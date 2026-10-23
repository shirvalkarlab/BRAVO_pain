"""The correction across the band choices: a Benjamini-Hochberg q beside each band, a LABEL AND
WARNING ONLY (wave 2, C9; the PI, 2026-10-18 and 2026-10-21; `routines/family_correction.py`).

One family PER CONTACT PAIR (the PI, 2026-10-21: each bipolar pair corrected separately, the left
independently of the right). Each family (the PI): one sensing pair the device's rule allows with the contacts in force
(decision 217, read at the time, never typed in), x the 22 band centres, x the sources that choose
a band (the TD-only grid's correlation rows, and the chronic log's answer where it decides the
band), for the one pain score the request asks for. Each band is counted once, by the rotation p of
the source that decides it. Held here, on values:
  * the family counts only what was built; a missing pair, grid or p lowers N and no p is made up;
  * q matches a Benjamini-Hochberg written out by hand, within each pair, and one pair's p values
    never move another pair's q;
  * the pairs come from the rule, so other contacts give other pairs;
  * rows on pairs outside the family, and rows that never choose, get `family_q: None` and why;
  * the chronic answer's p is used where it decides the band;
  * a warning is appended to `why` only on an established or supported band with q above 0.05;
  * answers, statuses, intervals and p are the same with and without it, field for field, and the
    input is never changed in place;
  * the Biomarkers view and the Closed-Loop (choosing) view give the same q;
  * the neutral setting (`BRAVO_FAMILY_CORRECTION=0`) skips the path and changes no grid key.

Run inside the container: python3 run_tests.py (or pytest this file)."""
import copy
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers.routines import family_correction as FC         # noqa: E402
from modules.Biomarkers.routines import sweep_settings as SW            # noqa: E402
from modules.DecodeCommon import sensing_rule as SR                      # noqa: E402

CENTRES = [8.5 + k for k in range(22)]
NEW_ROW_FIELDS = set(FC.ROW_FIELDS) | set(FC.AUC_ROW_FIELDS)


def _row(ch, c, p, *, r=0.1, lo=-0.1, hi=0.3, answer="not_resolved", choice="TD", chronic=None):
    row = {"channel": ch, "band_center_hz": float(c), "pearson_r": r, "pearson_r_low": lo,
           "pearson_r_high": hi, "answer": answer, "p_selection_aware": p,
           "n_pain_reports": 40, "why": "td why", "choice_source": choice,
           "chronic": chronic or {"covered": False, "n_reports": 0}}
    return row


def _grid(ch, ps, **kw):
    rows = [_row(ch, c, p, **kw) for c, p in zip(CENTRES, ps)]
    auc = [{"channel": ch, "band_center_hz": float(c), "auc": 0.5, "answer": "not_resolved",
            "why": "auc why", "choice_source": "TD"} for c in CENTRES[:len(ps)]]
    return {"center_freqs_hz": CENTRES[:len(ps)], "best_correlation_rows": rows,
            "best_auc_rows": auc}


def _sweep(ch, ps, display, **kw):
    td = _grid(ch, ps, **kw)
    mixed = _grid(ch, [0.001] * len(ps))
    for r in mixed["best_correlation_rows"]:
        r["choice_source"] = "none"
    psd = _grid(ch, [0.002] * len(ps))
    for r in psd["best_correlation_rows"]:
        r["choice_source"] = "none"
    out = dict(mixed)
    out["display_short"] = display
    out["by_source_grid"] = {"td": td, "psd": psd}
    return out


def _rule(left_rings, right_rings):
    return SR.sensing_rule_block({"Left": set(left_rings), "Right": set(right_rings)})


def _resp(sweeps, rule):
    return {"band_time_sweep": sweeps, "label_metric": "nrs", "metric_label": "NRS (0–10)",
            "sensing_rule": rule}


def _ps(seed, n=22):
    return list(np.random.default_rng(seed).uniform(0.001, 1.0, n))


def _three_pairs():
    return {"ZERO_THREE_LEFT": _sweep("ZERO_THREE_LEFT", _ps(1), "L 0⁻3⁺"),
            "ZERO_THREE_RIGHT": _sweep("ZERO_THREE_RIGHT", _ps(2), "R 0⁻3⁺"),
            "ONE_THREE_LEFT": _sweep("ONE_THREE_LEFT", _ps(3), "L 1⁻3⁺")}


def _bh_by_hand(p):
    """Benjamini-Hochberg written out: sort, p_(i) m / i, the running minimum from the largest
    down, capped at 1, put back in the original order."""
    m = len(p)
    order = sorted(range(m), key=lambda i: p[i])
    q_sorted = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, p[i] * m / rank)
        q_sorted[rank - 1] = min(running, 1.0)
    q = [0.0] * m
    for rank, i in enumerate(order, start=1):
        q[i] = q_sorted[rank - 1]
    return q


def _td_rows(resp, ch):
    return resp["band_time_sweep"][ch]["by_source_grid"]["td"]["best_correlation_rows"]


def _strip(obj):
    """The response with C9's fields and appended texts taken out."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in NEW_ROW_FIELDS or k == "family_correction":
                continue
            if k == "why" and isinstance(v, str) and FC.WARNING_HEAD in v:
                v = v[:v.index(". " + FC.WARNING_HEAD)]
            out[k] = _strip(v)
        return out
    if isinstance(obj, list):
        return [_strip(x) for x in obj]
    return obj


# ---- the family ----------------------------------------------------------------------------------
def test_the_allowed_pairs_are_read_from_the_rule_not_typed_in():
    assert FC.allowed_pairs(_rule({1, 2}, {1, 2})) == {"ZERO_THREE_LEFT": "Left",
                                                       "ZERO_THREE_RIGHT": "Right"}
    assert FC.allowed_pairs(_rule({2}, {1, 2})) == {"ONE_THREE_LEFT": "Left",
                                                    "ZERO_THREE_RIGHT": "Right"}
    assert FC.allowed_pairs(_rule({1}, {0})) == {"ZERO_TWO_LEFT": "Left"}   # contact 0: no pair
    assert FC.allowed_pairs(_rule(set(), set())) == {}
    assert FC.allowed_pairs(None) == {}


def test_the_family_counts_only_what_was_built():
    sweeps = _three_pairs()
    # the right pair built only 10 of its 22 bands
    td = sweeps["ZERO_THREE_RIGHT"]["by_source_grid"]["td"]
    td["best_correlation_rows"] = td["best_correlation_rows"][:10]
    out = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    blk = out["family_correction"]
    assert blk["n_in_family"] == 22 + 10
    assert blk["n_built"] == 22 + 10 + 22                    # every pair's choosing p, built
    assert blk["words"].startswith("corrected within each pair separately: L 0⁻3⁺ across 22 bands; "
                                    "R 0⁻3⁺ across 10 bands (54 built")
    assert {k: v["n_in_family"] for k, v in blk["per_pair"].items()} == {
        "ZERO_THREE_LEFT": 22, "ZERO_THREE_RIGHT": 10}
    assert all(r["family_n"] == 10 for r in _td_rows(out, "ZERO_THREE_RIGHT"))
    assert blk["allowed_pairs"] == ["ZERO_THREE_LEFT", "ZERO_THREE_RIGHT"]


def test_a_missing_pair_or_source_lowers_n_and_makes_up_no_p():
    sweeps = _three_pairs()
    del sweeps["ZERO_THREE_RIGHT"]["by_source_grid"]["td"]   # no TD-only grid on the right pair
    # one left band decided by the chronic log, whose answer has no p: not replaced by TD's p
    row = sweeps["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_correlation_rows"][3]
    row["choice_source"] = "chronic"
    row["chronic"] = {"covered": True, "p_rotation": None, "pearson_r": 0.3, "answer": "not_resolved",
                      "pearson_r_low": -0.1, "pearson_r_high": 0.5, "n_reports": 30}
    out = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    blk = out["family_correction"]
    assert blk["n_in_family"] == 21
    assert [m["channel"] for m in blk["missing"]] == ["ZERO_THREE_RIGHT"]
    got = _td_rows(out, "ZERO_THREE_LEFT")[3]
    assert got["family_q"] is None and got["family_p"] is None
    assert got["family_p_source"] == "chronic"
    assert got["family_q_status"] == FC.STATUS_NO_P
    # the right pair's other rows (mixed, PSD) never choose and carry no q
    for r in out["band_time_sweep"]["ZERO_THREE_RIGHT"]["best_correlation_rows"]:
        assert r["family_q"] is None and r["family_q_status"] == FC.STATUS_NEVER_CHOOSES
    # a pair the rule allows that is not on the grid at all
    sweeps2 = _three_pairs()
    del sweeps2["ZERO_THREE_RIGHT"]
    blk2 = FC.attach(_resp(sweeps2, _rule({1, 2}, {1, 2})))["family_correction"]
    assert blk2["n_in_family"] == 22
    assert [m["channel"] for m in blk2["missing"]] == ["ZERO_THREE_RIGHT"]


def test_q_matches_a_benjamini_hochberg_written_out_within_each_pair():
    sweeps = _three_pairs()
    out = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    all_p, all_q = [], []
    for ch in ("ZERO_THREE_LEFT", "ZERO_THREE_RIGHT"):
        rows = _td_rows(out, ch)
        p = [r["p_selection_aware"] for r in rows]
        want = _bh_by_hand(p)                                # this pair's 22 bands only
        assert [r["family_q"] for r in rows] == want        # no tolerance
        assert [r["family_p"] for r in rows] == p
        assert all(r["family_q_status"] == FC.STATUS_IN and r["family_n"] == 22 for r in rows)
        assert out["family_correction"]["per_pair"][ch]["smallest_q"] == min(want)
        all_p += p
        all_q += want
    blk = out["family_correction"]
    assert blk["smallest_p"] == min(all_p) and blk["smallest_q"] == min(all_q)
    assert blk["corrected_per_pair"] is True


def test_one_pairs_p_values_never_move_the_other_pairs_q():
    a = FC.attach(_resp(_three_pairs(), _rule({1, 2}, {1, 2})))
    sweeps = _three_pairs()
    for r in sweeps["ZERO_THREE_RIGHT"]["by_source_grid"]["td"]["best_correlation_rows"]:
        r["p_selection_aware"] = 1e-4                         # the right pair all very small
    b = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    assert ([r["family_q"] for r in _td_rows(a, "ZERO_THREE_LEFT")]
            == [r["family_q"] for r in _td_rows(b, "ZERO_THREE_LEFT")])
    assert [r["family_q"] for r in _td_rows(b, "ZERO_THREE_RIGHT")] == [1e-4] * 22


def test_pairs_outside_the_family_get_null_and_say_why():
    out = FC.attach(_resp(_three_pairs(), _rule({1, 2}, {1, 2})))
    for r in _td_rows(out, "ONE_THREE_LEFT"):
        assert r["family_q"] is None and r["family_q_status"] == FC.STATUS_NOT_ALLOWED
        assert r["why"] == "td why"                          # no warning off the family
    for key in ("best_correlation_rows", "best_auc_rows"):
        for r in out["band_time_sweep"]["ONE_THREE_LEFT"][key]:
            assert r["family_q"] is None
    # the area-under-the-curve rows of an allowed pair are not in the family (each band once)
    for r in out["band_time_sweep"]["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_auc_rows"]:
        assert r["family_q"] is None and r["family_q_status"] == FC.STATUS_AUC
    # no rule on record: no family, nothing given a q
    out2 = FC.attach(_resp(_three_pairs(), {"available": False, "by_side": {}}))
    assert out2["family_correction"]["available"] is False
    assert all(r["family_q"] is None for r in _td_rows(out2, "ZERO_THREE_LEFT"))


def test_the_chronic_answer_p_is_used_where_it_decides_the_band():
    sweeps = _three_pairs()
    row = sweeps["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_correlation_rows"][4]
    row["choice_source"] = "chronic"
    row["chronic"] = {"covered": True, "p_rotation": 0.0123, "pearson_r": 0.6, "answer": "established",
                      "pearson_r_low": 0.2, "pearson_r_high": 0.9, "n_reports": 13}
    out = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    got = _td_rows(out, "ZERO_THREE_LEFT")[4]
    assert got["family_p"] == 0.0123 and got["family_p_source"] == "chronic"
    assert got["p_selection_aware"] == row["p_selection_aware"]   # TD's own p untouched


def test_the_warning_goes_only_on_established_or_supported_bands_above_005():
    sweeps = _three_pairs()
    rows = sweeps["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_correlation_rows"]
    rows[0].update(answer="established", pearson_r=0.5, pearson_r_low=0.2, p_selection_aware=0.04)
    rows[1].update(answer="not_resolved", pearson_r=0.4, pearson_r_low=0.05, p_selection_aware=0.03)
    rows[2].update(answer="not_resolved", pearson_r=0.4, pearson_r_low=-0.05, p_selection_aware=0.03)
    out = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    got = _td_rows(out, "ZERO_THREE_LEFT")
    assert got[0]["family_q"] > 0.05 and got[1]["family_q"] > 0.05
    for r in got[:2]:                                        # established; supported (decision 210)
        assert r["family_q_warning"] and r["why"] == "td why. " + r["family_q_warning"]
        assert "22 bands tested on L 0⁻3⁺," in r["family_q_warning"]
        assert "R 0" not in r["family_q_warning"]
        assert ("q is %.2f" % r["family_q"]) in r["family_q_warning"]
    assert got[2]["family_q_warning"] is None and got[2]["why"] == "td why"
    assert out["family_correction"]["n_warned"] == 2
    # a band whose q clears 0.05 gets no warning
    sw2 = {"ZERO_THREE_LEFT": _sweep("ZERO_THREE_LEFT", [1e-4] * 22, "L 0⁻3⁺",
                                     answer="established", r=0.5, lo=0.2)}
    out2 = FC.attach(_resp(sw2, _rule({1, 2}, set())))
    assert all(r["family_q"] <= 0.05 and r["family_q_warning"] is None and r["why"] == "td why"
               for r in _td_rows(out2, "ZERO_THREE_LEFT"))


def test_answers_status_and_p_are_identical_with_and_without_and_the_input_is_untouched():
    sweeps = _three_pairs()
    sweeps["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_correlation_rows"][0].update(
        answer="established", pearson_r=0.5, pearson_r_low=0.2)
    resp = _resp(sweeps, _rule({1, 2}, {1, 2}))
    before = copy.deepcopy(resp)
    out = FC.attach(resp)
    assert resp == before                                    # nothing changed in place
    assert out is not resp
    assert _strip(out) == before                             # only the new fields and texts
    assert any(r.get("family_q_warning") for r in _td_rows(out, "ZERO_THREE_LEFT"))


def test_the_choosing_view_gives_the_same_q_as_the_biomarkers_view():
    sweeps = _three_pairs()
    row = sweeps["ZERO_THREE_RIGHT"]["by_source_grid"]["td"]["best_correlation_rows"][7]
    row["choice_source"] = "chronic"
    row["chronic"] = {"covered": True, "p_rotation": 0.02, "pearson_r": 0.6, "answer": "established",
                      "pearson_r_low": 0.2, "pearson_r_high": 0.9, "n_reports": 13}
    resp = _resp(sweeps, _rule({1, 2}, {1, 2}))
    raw = FC.attach(resp)
    choosing = SW.choosing_grid(resp)["band_time_sweep"]
    got, blk = FC.correct(choosing, resp["sensing_rule"], label_metric="nrs")
    assert blk["n_in_family"] == raw["family_correction"]["n_in_family"]
    for ch in ("ZERO_THREE_LEFT", "ZERO_THREE_RIGHT", "ONE_THREE_LEFT"):
        a = [r["family_q"] for r in _td_rows(raw, ch)]
        b = [r["family_q"] for r in got[ch]["best_correlation_rows"]]
        assert a == b, ch
    # the chronic-decided row in the choosing view: chronic's why plus the warning
    r = got["ZERO_THREE_RIGHT"]["best_correlation_rows"][7]
    assert r["decided_by"] == "chronic" and r["family_p_source"] == "chronic"
    if r["family_q_warning"]:
        assert r["why"].startswith("decided by the home record") and r["why"].endswith(
            ". " + r["family_q_warning"])


def test_band_lookup_returns_the_row_block_for_one_band():
    out = FC.attach(_resp(_three_pairs(), _rule({1, 2}, {1, 2})))
    sweeps = out["band_time_sweep"]
    b = FC.band_block(sweeps, out["family_correction"], "ZERO_THREE_LEFT", 12.5)
    row = _td_rows(out, "ZERO_THREE_LEFT")[4]
    assert b["family_q"] == row["family_q"] and b["family_p"] == row["family_p"]
    assert b["words"] == out["family_correction"]["words"]
    nb = FC.band_block(sweeps, out["family_correction"], "ONE_THREE_LEFT", 12.5)
    assert nb["family_q"] is None and nb["family_q_status"] == FC.STATUS_NOT_ALLOWED


def test_the_neutral_setting_skips_the_path_and_moves_no_grid_key():
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    code = ("import sys; sys.path.insert(0, %r);"
            "from modules.Biomarkers.routines import family_correction as F, sweep_settings as S,"
            " band_results_tables as T;"
            "print(F.ENABLED, S.GRID_RULE_VERSION, T.RULE_VERSION)" % here)
    env = dict(os.environ)
    env.pop("BRAVO_FAMILY_CORRECTION", None)
    on = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                        timeout=120).stdout.split()
    env["BRAVO_FAMILY_CORRECTION"] = "0"
    off = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         timeout=120).stdout.split()
    assert on[0] == "True" and off[0] == "False", (on, off)
    assert on[1:] == off[1:]                                 # no grid or table version moves
    # and with the switch off in this process, attach returns the very response it was given
    prev = FC.ENABLED
    try:
        FC.ENABLED = False
        resp = _resp(_three_pairs(), _rule({1, 2}, {1, 2}))
        before = copy.deepcopy(resp)
        assert FC.attach(resp) is resp and resp == before
    finally:
        FC.ENABLED = prev


# ---- the separate area-under-the-curve family (open item of decision 497) -------------------------
def _with_auc_p(sweeps, seed0=10):
    """Give every grid's area-under-the-curve rows a p of their own (the TD-only rows distinct per
    pair; the mixed and PSD-only rows small, so a leak into the family would show)."""
    for k, (ch, sw) in enumerate(sorted(sweeps.items())):
        for r in sw.get("best_auc_rows") or []:
            r["p_selection_aware"] = 0.0005
        for name, g in (sw.get("by_source_grid") or {}).items():
            ps = _ps(seed0 + k) if name == "td" else [0.0005] * 22
            for r, p in zip(g.get("best_auc_rows") or [], ps):
                r["p_selection_aware"] = p
    return sweeps


def _td_auc(resp, ch):
    return resp["band_time_sweep"][ch]["by_source_grid"]["td"]["best_auc_rows"]


def test_auc_q_matches_a_benjamini_hochberg_written_out_within_each_pair():
    out = FC.attach(_resp(_with_auc_p(_three_pairs()), _rule({1, 2}, {1, 2})))
    blk = out["family_correction"]
    for ch in ("ZERO_THREE_LEFT", "ZERO_THREE_RIGHT"):
        rows = _td_auc(out, ch)
        p = [r["p_selection_aware"] for r in rows]
        want = _bh_by_hand(p)                                 # this pair's 22 AUC rows only
        assert [r["family_q_auc"] for r in rows] == want      # no tolerance
        assert [r["family_p_auc"] for r in rows] == p
        assert all(r["family_q_auc_status"] == FC.STATUS_AUC_IN and r["family_n_auc"] == 22
                   and r["family_p_auc_source"] == "TD" for r in rows)
        assert blk["per_pair_auc"][ch]["smallest_q"] == min(want)
        assert blk["per_pair_auc"][ch]["n_in_family"] == 22
        # the correlation q stays on the AUC rows as it was: not in that family
        assert all(r["family_q"] is None and r["family_q_status"] == FC.STATUS_AUC for r in rows)
    assert blk["auc_family"]["n_in_family"] == 44 and blk["auc_family"]["n_built"] == 66
    assert blk["auc_family"]["words"].startswith(
        "area under the curve, corrected within each pair separately: L 0⁻3⁺ across 22 bands; "
        "R 0⁻3⁺ across 22 bands")
    # outside the family: a pair the rule does not allow, and rows that never choose
    for r in _td_auc(out, "ONE_THREE_LEFT"):
        assert r["family_q_auc"] is None and r["family_q_auc_status"] == FC.STATUS_NOT_ALLOWED
    for ch in out["band_time_sweep"]:
        sw = out["band_time_sweep"][ch]
        for r in sw["best_auc_rows"] + sw["by_source_grid"]["psd"]["best_auc_rows"]:
            assert r["family_q_auc"] is None and r["family_q_auc_status"] == FC.STATUS_NEVER_CHOOSES
        for g in [sw, sw["by_source_grid"]["td"], sw["by_source_grid"]["psd"]]:
            for r in g["best_correlation_rows"]:              # correlation rows gain no AUC field
                assert not set(FC.AUC_ROW_FIELDS) & set(r)


def test_one_pairs_auc_p_values_never_move_the_other_pairs_auc_q():
    a = FC.attach(_resp(_with_auc_p(_three_pairs()), _rule({1, 2}, {1, 2})))
    sweeps = _with_auc_p(_three_pairs())
    for r in sweeps["ZERO_THREE_RIGHT"]["by_source_grid"]["td"]["best_auc_rows"]:
        r["p_selection_aware"] = 1e-4
    b = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    assert ([r["family_q_auc"] for r in _td_auc(a, "ZERO_THREE_LEFT")]
            == [r["family_q_auc"] for r in _td_auc(b, "ZERO_THREE_LEFT")])
    assert [r["family_q_auc"] for r in _td_auc(b, "ZERO_THREE_RIGHT")] == [1e-4] * 22


def test_the_correlation_q_is_unchanged_by_the_auc_family():
    """Every correlation field and the correlation block's own keys are the same whatever the AUC
    rows hold: no AUC p, ordinary AUC p, or every AUC p tiny."""
    def corr_view(out):
        rows = {}
        for ch, sw in out["band_time_sweep"].items():
            for name, g in [("mixed", sw)] + list(sw["by_source_grid"].items()):
                rows[(ch, name)] = [{k: r.get(k) for k in FC.ROW_FIELDS + ("why",)}
                                    for r in g["best_correlation_rows"]]
                rows[(ch, name, "auc")] = [{k: r.get(k) for k in FC.ROW_FIELDS}
                                           for r in g["best_auc_rows"]]
        blk = {k: v for k, v in out["family_correction"].items()
               if k not in ("auc_family", "per_pair_auc")}
        return rows, blk

    base = _three_pairs()
    base["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_correlation_rows"][0].update(
        answer="established", pearson_r=0.5, pearson_r_low=0.2)
    none_ = FC.attach(_resp(copy.deepcopy(base), _rule({1, 2}, {1, 2})))
    some = FC.attach(_resp(_with_auc_p(copy.deepcopy(base)), _rule({1, 2}, {1, 2})))
    tiny = _with_auc_p(copy.deepcopy(base))
    for sw in tiny.values():
        for r in sw["by_source_grid"]["td"]["best_auc_rows"]:
            r["p_selection_aware"] = 1e-6
    tiny = FC.attach(_resp(tiny, _rule({1, 2}, {1, 2})))
    assert corr_view(none_) == corr_view(some) == corr_view(tiny)
    # and the correlation q is still a BH written out by hand over the correlation p
    rows = _td_rows(some, "ZERO_THREE_LEFT")
    assert [r["family_q"] for r in rows] == _bh_by_hand([r["p_selection_aware"] for r in rows])
    # no AUC p anywhere: every allowed AUC row says so, none gets a q
    for r in _td_auc(none_, "ZERO_THREE_LEFT"):
        assert r["family_q_auc"] is None and r["family_q_auc_status"] == FC.STATUS_AUC_NO_P
    assert none_["family_correction"]["auc_family"]["n_in_family"] == 0


def test_the_auc_warning_goes_only_on_established_auc_rows_above_005():
    sweeps = _with_auc_p(_three_pairs())
    rows = sweeps["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_auc_rows"]
    rows[0].update(answer="established", p_selection_aware=0.04)
    rows[1].update(answer="not_resolved", p_selection_aware=0.03)
    out = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    got = _td_auc(out, "ZERO_THREE_LEFT")
    assert got[0]["family_q_auc"] > 0.05
    w = got[0]["family_q_auc_warning"]
    assert w == ("After correcting for the 22 area-under-the-curve bands tested on L 0⁻3⁺, this "
                 "band's q is %.2f: it may be a chance finding" % got[0]["family_q_auc"])
    assert got[0]["why"] == "auc why. " + w
    assert got[1]["family_q_auc_warning"] is None and got[1]["why"] == "auc why"
    assert out["family_correction"]["auc_family"]["n_warned"] == 1
    assert out["family_correction"]["per_pair_auc"]["ZERO_THREE_LEFT"]["n_warned"] == 1
    # an established AUC row whose q clears 0.05: no warning
    sw2 = {"ZERO_THREE_LEFT": _sweep("ZERO_THREE_LEFT", _ps(1), "L 0⁻3⁺")}
    for r in sw2["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_auc_rows"]:
        r.update(answer="established", p_selection_aware=1e-4)
    out2 = FC.attach(_resp(sw2, _rule({1, 2}, set())))
    assert all(r["family_q_auc"] <= 0.05 and r["family_q_auc_warning"] is None
               and r["why"] == "auc why" for r in _td_auc(out2, "ZERO_THREE_LEFT"))


def test_answers_status_and_p_are_identical_with_and_without_the_auc_q():
    sweeps = _with_auc_p(_three_pairs())
    sweeps["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_auc_rows"][0].update(
        answer="established", p_selection_aware=0.04)
    resp = _resp(sweeps, _rule({1, 2}, {1, 2}))
    before = copy.deepcopy(resp)
    out = FC.attach(resp)
    assert resp == before
    assert _strip(out) == before                              # only the new fields and texts
    assert _td_auc(out, "ZERO_THREE_LEFT")[0]["family_q_auc_warning"]


def test_the_choosing_view_gives_the_same_auc_q_as_the_biomarkers_view():
    resp = _resp(_with_auc_p(_three_pairs()), _rule({1, 2}, {1, 2}))
    raw = FC.attach(resp)
    got, blk = FC.correct(SW.choosing_grid(resp)["band_time_sweep"], resp["sensing_rule"],
                          label_metric="nrs")
    assert blk["per_pair_auc"] == raw["family_correction"]["per_pair_auc"]
    for ch in ("ZERO_THREE_LEFT", "ZERO_THREE_RIGHT", "ONE_THREE_LEFT"):
        assert ([r["family_q_auc"] for r in _td_auc(raw, ch)]
                == [r["family_q_auc"] for r in got[ch]["best_auc_rows"]]), ch


# ---- the sign-off's band lookup carries the AUC q too (the open item of decision 500) ------------
def test_band_lookup_carries_the_bands_auc_q_from_its_grid_row_and_keeps_its_correlation_q():
    sweeps = _with_auc_p(_three_pairs())
    sweeps["ZERO_THREE_LEFT"]["by_source_grid"]["td"]["best_auc_rows"][4].update(
        answer="established", p_selection_aware=0.04)
    out = FC.attach(_resp(sweeps, _rule({1, 2}, {1, 2})))
    blk = out["family_correction"]
    b = FC.band_block(out["band_time_sweep"], blk, "ZERO_THREE_LEFT", 12.5)
    arow = _td_auc(out, "ZERO_THREE_LEFT")[4]
    for k in FC.AUC_ROW_FIELDS:                               # each equal to its grid row's value
        assert b[k] == arow[k], k
    assert b["family_q_auc_status"] == FC.STATUS_AUC_IN and b["family_n_auc"] == 22
    assert b["family_q_auc_warning"] and b["family_q_auc_warning"] == arow["family_q_auc_warning"]
    assert b["auc_words"] == blk["auc_family"]["words"]
    assert b["auc_n_in_family"] == 44 and b["auc_n_built"] == 66
    # the correlation q is the correlation row's, unchanged by the AUC fields beside it
    crow = _td_rows(out, "ZERO_THREE_LEFT")[4]
    for k in FC.ROW_FIELDS:
        assert b[k] == crow[k], k
    plain = FC.attach(_resp(_three_pairs(), _rule({1, 2}, {1, 2})))
    pb = FC.band_block(plain["band_time_sweep"], plain["family_correction"], "ZERO_THREE_LEFT", 12.5)
    assert {k: b[k] for k in FC.ROW_FIELDS} == {k: pb[k] for k in FC.ROW_FIELDS}
    # a pair outside the family: no AUC q, and why
    nb = FC.band_block(out["band_time_sweep"], blk, "ONE_THREE_LEFT", 12.5)
    assert nb["family_q_auc"] is None and nb["family_q_auc_status"] == FC.STATUS_NOT_ALLOWED
    # a centre with no row: no AUC q, and why
    xb = FC.band_block(out["band_time_sweep"], blk, "ZERO_THREE_LEFT", 99.5)
    assert xb["family_q_auc"] is None and "no area-under-the-curve row" in xb["family_q_auc_status"]
