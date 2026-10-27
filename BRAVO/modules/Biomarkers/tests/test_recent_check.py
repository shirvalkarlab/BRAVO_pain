"""The recent-reports check, a WARNING beside each band's link with pain (wave 2, C8; the PI,
2026-10-21: "Recent-reports check, warn"; `routines/time_split.py`).

Band choice stays on all the data. The check re-reads each band's link on the reports filed after
the 70% cut (by time, on the pain series the grid and the sign-off both build) and warns when it
does not keep the same clear sign. Held here, on values:
  * the cut is the time of the report at the 70% mark, whatever order the times arrive in, and
    moves when a report is added (it is rolling);
  * one cut on every grid (mixed, TD-only, PSD-only) and every chronic answer of a request; the
    grid and the sign-off take it from the same function on the same series;
  * a band whose sign flips on the recent reports gets the warning, appended to `why`; a consistent
    band gets none;
  * fewer than `RECENT_MIN_REPORTS` recent reports, and none at all, give their short notes;
  * every answer, status, interval and p is the same with and without the check, field for field,
    on the grid and on the chronic answer (the neutral setting skips it);
  * the neutral setting (`BRAVO_RECENT_CHECK=0`) files grids under the rule before C8;
  * live (RCS08): the Biomarkers grid and the Closed-Loop sign-off print the same cut date.

Run inside the container: python3 run_tests.py (or pytest this file)."""
import datetime as dt
import os
import subprocess
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers.routines import analytics as A                  # noqa: E402
from modules.Biomarkers.routines import chronic_band_choice as CBC      # noqa: E402
from modules.Biomarkers.routines import daily_swing as DS                # noqa: E402
from modules.Biomarkers.routines import sweep_settings as SW            # noqa: E402
from modules.Biomarkers.routines import time_split as TS                # noqa: E402
from modules.DecodeCommon import representation as R                     # noqa: E402

LA = ZoneInfo("America/Los_Angeles")
CENTRES = [8.5 + k for k in range(22)]
TIMINGS = {"seconds", "wall_seconds", "total_seconds", "matched_seconds"}


def _local(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=LA).timestamp()


def _same(a, b, path=""):
    """Field for field, no tolerance; NaN equals NaN."""
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), (path, sorted(set(a) ^ set(b)))
        for k in a:
            if k in TIMINGS:
                continue
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)):
        assert isinstance(b, (list, tuple)) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{i}]")
    elif isinstance(a, np.ndarray):
        assert np.array_equal(a, b, equal_nan=True), path
    elif isinstance(a, float) and a != a:
        assert isinstance(b, float) and b != b, (path, b)
    else:
        assert a == b, (path, a, b)


def _strip(obj):
    """The object with every `recent_check` and `recent_check_cut` removed, and `why` put back as it
    was before the check's text was appended (read from the check itself)."""
    if isinstance(obj, dict):
        out = {k: _strip(v) for k, v in obj.items() if k not in ("recent_check", "recent_check_cut")}
        rc = obj.get("recent_check") if isinstance(obj.get("recent_check"), dict) else None
        txt = TS.appended_text(rc) if rc else None
        if txt and isinstance(out.get("why"), str):
            assert out["why"].endswith(". " + txt), out["why"]
            out["why"] = out["why"][: -len(". " + txt)]
        return out
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


# ---- the cut -----------------------------------------------------------------------------------

def test_the_cut_is_the_report_at_the_70_percent_mark_in_time_order():
    t = _local(2026, 1, 1, 9) + 86400.0 * np.arange(10)
    rng = np.random.default_rng(0)
    shuffled = rng.permutation(t)
    with_gaps = np.concatenate([shuffled, [np.nan, np.inf]])
    assert TS.choice_cut(t) == t[6]                         # 7 of 10 reports at or before it
    assert TS.choice_cut(shuffled) == t[6] == TS.choice_cut(with_gaps)
    assert TS.choice_cut(t, share=0.5) == t[4]
    assert TS.choice_cut(t, share=1.0) is None              # the neutral share: no cut
    assert TS.choice_cut([]) is None and TS.choice_cut([t[0]]) is None
    blk = TS.cut_block(shuffled, np.ones(10))
    assert blk["choice_cut_s"] == t[6] and blk["n_before"] == 7 and blk["n_after"] == 3
    assert blk["choice_cut_date"] == "2026-01-07" and blk["share"] == 0.70 and blk["rolling"]
    # a report with no pain score is not on the series and does not count
    pain = np.ones(10); pain[9] = np.nan
    blk2 = TS.cut_block(t, pain)
    assert blk2["n_reports"] == 9 and blk2["choice_cut_s"] == t[5]


def test_the_cut_date_is_the_california_calendar_day():
    # 2026-04-03 01:30 UTC is 2026-04-02 18:30 in California
    t = dt.datetime(2026, 4, 3, 1, 30, tzinfo=dt.timezone.utc).timestamp()
    assert TS.cut_date(t) == "2026-04-02"
    assert TS.cut_date(None) is None


def test_the_cut_moves_when_a_report_is_added():
    t = list(_local(2026, 1, 1, 9) + 86400.0 * np.arange(10))
    before = TS.choice_cut(t)
    t2 = t + [t[-1] + 86400.0, t[-1] + 2 * 86400.0, t[-1] + 3 * 86400.0, t[-1] + 4 * 86400.0]
    after = TS.choice_cut(t2)
    assert after > before                                   # rolling: 14 reports, the 9th
    assert after == sorted(t2)[int(np.floor(0.7 * 14)) - 1]


# ---- the check on one band ---------------------------------------------------------------------

def _series(n=60, r_old=0.8, r_new=0.8, seed=1):
    """``n`` reports a day apart; band power follows pain with strength ``r_old`` before the 70% mark
    and ``r_new`` after it."""
    rng = np.random.default_rng(seed)
    t = _local(2026, 1, 1, 9) + 86400.0 * np.arange(n)
    y = rng.normal(5.0, 2.0, n)
    k = int(np.floor(0.7 * n))
    x = np.empty(n)
    for sl, rr in ((slice(0, k), r_old), (slice(k, n), r_new)):
        z = rng.normal(0, 1, y[sl].size)
        yy = (y[sl] - y[sl].mean()) / y[sl].std()
        x[sl] = 100 + 10 * (rr * yy + np.sqrt(max(0.0, 1 - rr * rr)) * z)
    return x, y, t


def test_a_sign_flip_on_the_recent_reports_gives_the_warning():
    x, y, t = _series(r_old=0.9, r_new=-0.8)
    cut = TS.cut_block(t, y)
    r_all = float(np.corrcoef(x, y)[0, 1])
    assert r_all > 0
    rc = TS.recent_check(x, y, t, cut, r_all=r_all, n_boot=300, rng=np.random.default_rng(4))
    assert rc["status"] == TS.STATUS_CHECKED == "checked"
    assert rc["n_after"] == 18 and rc["n_before"] == 42 and rc["choice_cut_date"] == cut["choice_cut_date"]
    assert rc["pearson_r"] < 0 and rc["consistent"] is False
    assert rc["warning"] == (
        "On the 18 reports after %s, r is %+.2f [%+.2f, %+.2f]: not the same clear sign as on all "
        "reports. These recent reports were also used in choosing, so this checks consistency over "
        "time, not an independent test" % (cut["choice_cut_date"], rc["pearson_r"],
                                           rc["pearson_r_low"], rc["pearson_r_high"]))
    assert rc["note"] is None and TS.appended_text(rc) == rc["warning"]
    rows = [{"why": "the interval ...", "recent_check": rc}]
    TS.append_to_rows(rows)
    assert rows[0]["why"] == "the interval ..." + ". " + rc["warning"]
    # its interval is the row's own method on the recent reports alone, in time order
    after = t > cut["choice_cut_s"]
    lo, hi = A._block_boot_r_interval(x[after].copy(), y[after].copy(), n_boot=300,
                                      rng=np.random.default_rng(4))
    assert (rc["pearson_r_low"], rc["pearson_r_high"]) == (lo, hi)


def test_a_consistent_band_gets_no_warning():
    x, y, t = _series(r_old=0.9, r_new=0.95)
    cut = TS.cut_block(t, y)
    r_all = float(np.corrcoef(x, y)[0, 1])
    rc = TS.recent_check(x, y, t, cut, r_all=r_all, n_boot=300, rng=np.random.default_rng(4))
    assert rc["status"] == "checked" and rc["consistent"] is True
    assert rc["pearson_r_low"] > 0
    assert rc["warning"] is None and rc["note"] is None and TS.appended_text(rc) is None
    rows = [{"why": "w", "recent_check": rc}]
    TS.append_to_rows(rows)
    assert rows[0]["why"] == "w"
    assert rc["words"].startswith("On the 18 reports after ")
    # an interval reaching across zero, same sign: a warning too
    x2, y2, t2 = _series(n=40, r_old=0.9, r_new=0.15, seed=3)
    rc2 = TS.recent_check(x2, y2, t2, TS.cut_block(t2, y2), r_all=float(np.corrcoef(x2, y2)[0, 1]),
                          n_boot=300, rng=np.random.default_rng(4))
    assert rc2["status"] == "checked"
    if rc2["pearson_r_low"] <= 0 <= rc2["pearson_r_high"]:
        assert rc2["consistent"] is False and rc2["warning"]


def test_too_few_and_no_recent_reports_give_their_notes():
    x, y, t = _series(n=40)
    cut = TS.cut_block(t, y)
    date = cut["choice_cut_date"]
    # only 9 recent reports have a band-power value (the row's own matched reports)
    x9 = x.copy(); x9[28 + 9:] = np.nan
    rc = TS.recent_check(x9, y, t, cut, r_all=0.5, n_boot=100, rng=np.random.default_rng(0))
    assert TS.RECENT_MIN_REPORTS == 10
    assert rc["status"] == TS.STATUS_TOO_FEW == "too few recent reports"
    assert rc["n_after"] == 9 and rc["n_before"] == 28
    assert rc["pearson_r"] is None and rc["warning"] is None
    assert rc["note"] == ("Recent-reports check: only 9 reports after %s (fewer than 10), not "
                          "checked" % date)
    # none at all: the band's data ended before the cut
    x0 = x.copy(); x0[28:] = np.nan
    rc0 = TS.recent_check(x0, y, t, cut, r_all=0.5, n_boot=100, rng=np.random.default_rng(0))
    assert rc0["status"] == TS.STATUS_NONE == "no reports after the cut"
    assert rc0["n_after"] == 0 and rc0["n_before"] == 28
    assert rc0["note"] == "Recent-reports check: no reports after %s at this band" % date
    rows = [{"why": "w", "recent_check": rc0}, {"recent_check": rc}]
    TS.append_to_rows(rows)
    assert rows[0]["why"] == "w. " + rc0["note"] and rows[1]["why"] == rc["note"]
    # no cut at all (too few reports on the series): nothing is checked, and it says so
    rcn = TS.recent_check(x, y, t, TS.cut_block(t[:1], y[:1]), r_all=0.5, n_boot=100,
                          rng=np.random.default_rng(0))
    assert rcn["status"] == TS.STATUS_NONE and rcn["choice_cut_date"] is None


# ---- on the grid and the chronic answer ---------------------------------------------------------

def _grid(n=120, seed=5, flip=False):
    rng = np.random.default_rng(seed)
    pain = np.clip(np.round(5 + rng.normal(0, 2, n)), 0, 10)
    sign = np.where(np.arange(n) >= int(0.7 * n), -1.0, 1.0) if flip else np.ones(n)
    power = {}
    for L in (1.0, 5.0, 30.0):
        x = 200 + 6 * (sign * (pain - 5.0))[:, None] + rng.normal(0, 12, (n, 3))
        x[rng.random(x.shape) < 0.1] = np.nan
        power[L] = x
    rt = _local(2026, 9, 1, 7, 0) + 86400.0 * np.arange(n)
    return power, pain, rt


def test_the_grid_is_the_same_field_for_field_with_or_without_the_check():
    power, pain, rt = _grid()
    kw = dict(center_freqs_hz=[12.5, 20.5, 24.5], n_perm=60, n_boot=200, seed=3,
              requested_seconds=(1.0, 5.0, 30.0), current_removed_check=True,
              covariate=np.where(np.arange(pain.size) % 2 == 0, 1.0, 2.0), report_times_s=rt)
    cut = TS.cut_block(rt, pain)
    neutral = A.band_time_sweep_from_power(power, pain, **kw)
    checked = A.band_time_sweep_from_power(power, pain, recent_check={"cut": cut,
                                                                      "report_times_s": rt}, **kw)
    TS.append_to_rows(checked["best_correlation_rows"])
    _same(neutral, _strip(checked))                     # every answer, status, p, interval
    assert not any("recent_check" in r for r in neutral["best_correlation_rows"])
    assert not any("recent_check" in r for r in checked["best_auc_rows"])
    for c, row in enumerate(checked["best_correlation_rows"]):
        rc = row["recent_check"]
        x = np.asarray(power[float(row["integration_seconds_requested"])], float)[:, c]
        m = np.isfinite(x) & np.isfinite(pain)
        # the row's own matched reports, split at the one cut
        assert rc["n_after"] == int((m & (rt > cut["choice_cut_s"])).sum())
        assert rc["n_before"] == int((m & (rt <= cut["choice_cut_s"])).sum())
        assert rc["n_after"] + rc["n_before"] == row["n_pain_reports"]
        assert rc["choice_cut_date"] == cut["choice_cut_date"]


def test_a_band_that_flips_after_the_cut_is_warned_on_the_grid():
    power, pain, rt = _grid(n=150, flip=True)
    cut = TS.cut_block(rt, pain)
    g = A.band_time_sweep_from_power(power, pain, center_freqs_hz=[12.5, 20.5, 24.5], n_perm=60,
                                     n_boot=200, seed=3, requested_seconds=(1.0, 5.0, 30.0),
                                     recent_check={"cut": cut, "report_times_s": rt})
    TS.append_to_rows(g["best_correlation_rows"])
    for row in g["best_correlation_rows"]:
        rc = row["recent_check"]
        assert rc["status"] == "checked" and row["pearson_r"] > 0 and rc["pearson_r"] < 0
        assert rc["consistent"] is False and row["why"].endswith(". " + rc["warning"])


def _chronic_block(rt, pain, freq=24.41, flip_after=None):
    """Left 1-3 chronic readings every 10 minutes over the reports' span, following pain at each
    report (the reading covering it); with ``flip_after`` the link reverses after that time."""
    t = np.arange(rt.min() - 86400.0, rt.max() + 86400.0, 600.0)
    y = np.full(t.size, 150.0)
    k = np.searchsorted(t, rt, side="right") - 1
    sign = np.ones(rt.size) if flip_after is None else np.where(rt > flip_after, -1.0, 1.0)
    y[k] = y[k] + 10.0 * sign * pain
    rec = {"ChannelNames": ["LeftHemisphere LFP", "LeftHemisphere Amplitude"],
           "Data": np.column_stack([y, np.ones(t.size)]), "Time": t, "SamplingRate": -1,
           "RecordingType": "MedtronicChronicBrainSense", "FreqScheduleHz": [[t[0] - 1.0, freq]],
           "ContactSchedule": [[t[0] - 1.0, "1-3"]]}
    merged, _ = R.merge_chronic_repeats([rec])
    return CBC.chronic_samples_by_pair(merged)


def _reports(n=60, seed=1):
    rng = np.random.default_rng(seed)
    base = _local(2026, 10, 20, 8, 0)
    rt = base + 86400.0 * (np.arange(n) // 3) + 3600.0 * 4 * (np.arange(n) % 3) + 900.0
    return rt.astype(float), rng.normal(5.0, 2.0, n)


def test_the_chronic_answer_is_unchanged_by_the_check_and_carries_its_own():
    rt, pain = _reports()
    cut = TS.cut_block(rt, pain)
    S = _chronic_block(rt, pain, flip_after=cut["choice_cut_s"])
    off = CBC.chronic_band_choice(S, {}, rt, pain, centres=CENTRES, tol_s=900.0, n_boot=100)
    on = CBC.chronic_band_choice(S, {}, rt, pain, centres=CENTRES, tol_s=900.0, n_boot=100,
                                 recent_cut=cut)
    _same(off, _strip(on))
    e = on["ONE_THREE_LEFT"]["by_centre"][24.5]
    rc = e["recent_check"]
    assert rc["choice_cut_date"] == cut["choice_cut_date"]          # the request's one cut
    assert rc["n_after"] + rc["n_before"] == e["n_reports"]
    assert rc["status"] == "checked" and rc["pearson_r"] < 0 < e["pearson_r"]
    assert rc["consistent"] is False and rc["warning"]
    # where the chronic log decides the band, the choosing view carries the chronic answer's own
    # check and appends its text to the chronic `why`; TD's own is kept in td_values
    td_rc = {"status": TS.STATUS_TOO_FEW, "note": "td note", "warning": None}
    row = {"band_center_hz": 24.5, "pearson_r": 0.1, "why": "td why", "recent_check": td_rc}
    CBC.label_rows([row], on["ONE_THREE_LEFT"], SW.GRID_SOURCE_TD)
    assert row["choice_source"] == "chronic" and row["chronic"]["recent_check"] is rc
    seen = SW.chronic_decides(row)
    assert seen["recent_check"] is rc and seen["why"].endswith(". " + rc["warning"])
    assert seen["td_values"]["recent_check"] is td_rc
    assert seen["answer"] == e["answer"] and seen["pearson_r"] == e["pearson_r"]


def test_every_source_grid_and_chronic_answer_carry_the_one_cut_they_are_given():
    """Given one cut block, the statistics of every source grid and every chronic answer print that
    cut and no other (the request builds the block once, `bravo_service._recent_cut`; the live test
    below checks the grid and the sign-off build the same one)."""
    rt, pain = _reports(n=90)
    cut = TS.cut_block(rt, pain)
    power, _p, _t = _grid(n=90)
    rows_by_source = {}
    for name in (SW.GRID_SOURCE_MIXED, SW.GRID_SOURCE_TD, SW.GRID_SOURCE_PSD):
        g = A.band_time_sweep_from_power(power, pain, center_freqs_hz=[12.5, 20.5, 24.5],
                                         n_perm=30, n_boot=100, seed=3,
                                         requested_seconds=(1.0, 5.0, 30.0),
                                         recent_check={"cut": cut, "report_times_s": rt})
        rows_by_source[name] = g["best_correlation_rows"]
    ch = CBC.chronic_band_choice(_chronic_block(rt, pain), {}, rt, pain, centres=CENTRES,
                                 tol_s=900.0, n_boot=100, recent_cut=cut)["ONE_THREE_LEFT"]
    dates = {r["recent_check"]["choice_cut_date"] for rows in rows_by_source.values() for r in rows}
    dates |= {e["recent_check"]["choice_cut_date"] for e in ch["frequencies"]}
    assert dates == {cut["choice_cut_date"]}
    secs = {r["recent_check"]["choice_cut_s"] for rows in rows_by_source.values() for r in rows}
    assert secs == {cut["choice_cut_s"]}


def test_the_neutral_setting_files_grids_under_the_rule_before_c8():
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    code = ("import sys; sys.path.insert(0, %r);"
            "from modules.Biomarkers.routines import sweep_settings as S, band_results_tables as T;"
            "print(S.RECENT_CHECK, S.GRID_RULE_VERSION, T.RULE_VERSION)" % here)
    env = dict(os.environ)
    for k in ("BRAVO_RECENT_CHECK", "BRAVO_DAILY_SWING", "BRAVO_CHRONIC_CHOICE", "BRAVO_SOURCE_GRIDS"):
        env.pop(k, None)
    on = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                        timeout=120).stdout.split()
    env["BRAVO_RECENT_CHECK"] = "0"
    off = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         timeout=120).stdout.split()
    assert on == ["True", "v35_bins_to_125hz", "v8_recent_check"], on
    assert off == ["False", "v33_daily_swing", "v7_daily_swing"], off


def test_the_band_tables_carry_the_recent_columns():
    from modules.Biomarkers.routines import band_results_tables as T
    power, pain, rt = _grid()
    cut = TS.cut_block(rt, pain)
    g = A.band_time_sweep_from_power(power, pain, center_freqs_hz=[12.5, 20.5, 24.5], n_perm=30,
                                     n_boot=100, seed=3, requested_seconds=(1.0, 5.0, 30.0),
                                     recent_check={"cut": cut, "report_times_s": rt})
    df = T.correlation_table({"ONE_THREE_LEFT": g})
    best = df[df["is_best_for_centre"]]
    other = df[~df["is_best_for_centre"]]
    assert len(best) == 3
    for _, r in best.iterrows():
        row = next(b for b in g["best_correlation_rows"] if b["band_center_hz"] == r["band_center_hz"])
        rc = row["recent_check"]
        assert r["recent_status"] == rc["status"] and r["recent_n_after"] == rc["n_after"]
        assert r["recent_n_before"] == rc["n_before"]
        assert (r["recent_r"] == rc["pearson_r"]) or (rc["pearson_r"] is None and r["recent_r"] != r["recent_r"])
    assert other["recent_status"].isna().all() and other["recent_r"].isna().all()


# ---- live: the two pages print one cut ----------------------------------------------------------
live = pytest.mark.live


@live
def test_the_grid_and_the_sign_off_print_the_same_cut_on_rcs08():
    try:
        from Server import models
        from modules.Biomarkers import bravo_service as bs
    except Exception:
        return
    uid = "2e3c75c00d7f4f37b53a048d195f11da"
    try:
        if models.Participant.find(uid=uid) is None:
            return
    except Exception:
        return
    if not SW.RECENT_CHECK:
        return
    # the series both pages build: the pain reports, then the clinic-sheet merge (same helper)
    req = {"ParticipantId": uid, "LabelMetric": "nrs"}
    with bs.pro_request_scope():
        pro = bs._load_pros(req, models.Participant.find(uid=uid))
        pro, metric, _ = bs._resolve_biomarker_metric(req, pro)
        t, v = bs._pro_match_arrays(pro, metric)
        t, v, _f, _b = bs._merge_clinic_sheet_ratings(uid, metric, metric, t, v, req)
        grid_cut = bs._recent_cut(t, v)
        setup = bs._band_validation_setup(req)
    signoff_cut = bs._recent_cut(*setup["pm"])
    assert grid_cut["choice_cut_date"] == signoff_cut["choice_cut_date"]
    assert grid_cut["choice_cut_s"] == signoff_cut["choice_cut_s"]
    assert grid_cut["n_reports"] == signoff_cut["n_reports"] > 100
