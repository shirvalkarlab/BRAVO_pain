"""The daily swing of a band's power, a WARNING beside its link with pain (wave 2, C6; the PI,
2026-10-19: "Drop blocks, warn"; `routines/daily_swing.py`).

Held here, on values:
  * a flat daily profile gives no warning (ratio 1.0, status "measured");
  * a 2-fold profile gives the warning with the right hours (lowest 03:00, highest 10:00, reports
    07:00-20:00), on California local time across a daylight-saving change;
  * a band with no chronic frequency on its centre says "no home record at this band", with the
    profile and ratio None and the report hours still given;
  * the hours of day on a heat-map row are those of the reports its chosen cell used;
  * attaching the warning moves nothing that decides: every field of the grid but `daily_swing`
    is the same with and without it (the neutral setting), field for field, no tolerance; on the
    chronic answer too; the warning is only appended to `why`;
  * the chronic log's answer, where it decides a band, carries its own daily swing and its warning;
  * the neutral setting (`BRAVO_DAILY_SWING=0`) files grids under the rule before C6.

Run inside the container: python3 _agent_bridge/_snr6_run.py Biomarkers/tests/test_daily_swing.py
"""
import datetime as dt
import os
import subprocess
import sys
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers.routines import analytics as A                  # noqa: E402
from modules.Biomarkers.routines import chronic_band_choice as CBC      # noqa: E402
from modules.Biomarkers.routines import daily_swing as DS                # noqa: E402
from modules.Biomarkers.routines import sweep_settings as SW            # noqa: E402
from modules.DecodeCommon import representation as R                     # noqa: E402

LA = ZoneInfo("America/Los_Angeles")
CENTRES = [8.5 + k for k in range(22)]
#: the fields that only record how long something took
TIMINGS = {"seconds", "wall_seconds", "total_seconds", "matched_seconds"}


def _local(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=LA).timestamp()


def _readings(level_by_hour, days=10, start=(2026, 10, 27)):
    """One reading every 10 minutes for ``days`` days, across the daylight-saving end of
    2026-11-01, valued by the LOCAL hour of day."""
    t0 = _local(*start, 0)
    t = t0 + 600.0 * np.arange(days * 24 * 6)
    hours = np.asarray([dt.datetime.fromtimestamp(x, tz=LA).hour for x in t])
    return t, np.asarray([level_by_hour(h) for h in hours], dtype=float)


def _same(a, b, path=""):
    """Field for field, no tolerance; NaN equals NaN."""
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), (path, sorted(set(a) ^ set(b)))
        for k in a:
            if k in TIMINGS:                     # computing time only
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
    """The object with every `daily_swing` removed (and `why` put back as it was before the
    warning was appended, read from the warning itself)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "daily_swing":
                continue
            out[k] = _strip(v)
        w = ((obj.get("daily_swing") or {}).get("warning")) if isinstance(obj, dict) else None
        if w and isinstance(out.get("why"), str):
            assert out["why"].endswith(". " + w), out["why"]
            out["why"] = out["why"][: -len(". " + w)]
        return out
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def test_a_flat_profile_gives_no_warning():
    t, y = _readings(lambda h: 300.0)
    prof = DS.hourly_profile(t, y)
    assert prof["ratio"] == 1.0 and prof["n_readings"] == t.size
    assert prof["n_readings_by_hour"].count(0) == 0
    hours = DS.report_hours([_local(2026, 10, 28, 9, 0), _local(2026, 10, 29, 17, 30)])
    blk = DS.swing_block(prof, hours, freq_hz=24.4)
    assert blk["status"] == DS.STATUS_MEASURED and blk["warning"] is None
    assert DS.append_warning("the interval ...", blk["warning"]) == "the interval ..."
    # just under the limit: still no warning; at it: a warning
    t2, y2 = _readings(lambda h: 100.0 * DS.SWING_WARN_RATIO * 0.999 if h == 12 else 100.0)
    assert DS.warning_sentence(DS.hourly_profile(t2, y2), hours) is None
    t3, y3 = _readings(lambda h: 100.0 * DS.SWING_WARN_RATIO if h == 12 else 100.0)
    assert DS.warning_sentence(DS.hourly_profile(t3, y3), hours) is not None


def test_a_two_fold_profile_gives_the_warning_with_the_right_hours():
    # lowest at local 03:00, highest at local 10:00, across the 2026-11-01 daylight-saving end
    t, y = _readings(lambda h: 100.0 if h == 3 else (200.0 if h == 10 else 150.0))
    prof = DS.hourly_profile(t, y)
    assert prof["ratio"] == 2.0, prof["ratio"]
    assert prof["hour_low"] == 3 and prof["hour_high"] == 10
    assert prof["hourly_median"][3] == 100.0 and prof["hourly_median"][10] == 200.0
    assert prof["n_days"] == 10, prof["n_days"]
    # reports filed 07:15 (before the change, UTC-7) and 19:40 (after it, UTC-8), local time
    rt = [_local(2026, 10, 30, 7, 15), _local(2026, 11, 3, 12, 0), _local(2026, 11, 4, 19, 40)]
    hours = DS.report_hours(rt)
    assert hours["earliest"] == "07:15" and hours["latest"] == "19:40" and hours["median"] == "12:00"
    assert hours["counts_by_hour"][7] == 1 and hours["counts_by_hour"][19] == 1
    assert sum(hours["counts_by_hour"]) == 3
    blk = DS.swing_block(prof, hours, freq_hz=9.8)
    assert blk["warning"] == (
        "Band power at this band swings 2.0-fold across the day (lowest 03:00, highest 10:00); its "
        "pain reports were filed 07:00-20:00, so part of a link with pain may be the time of day")
    assert DS.append_warning("why", blk["warning"]) == "why. " + blk["warning"]


def _chronic_block(rt, pain, freq=24.41, level_by_hour=None):
    """Left 1-3 chronic readings every 10 minutes over the reports' span, following pain at each
    report (the reading covering it) and otherwise the given daily profile."""
    lvl = level_by_hour or (lambda h: 100.0 if h == 3 else (200.0 if h == 10 else 150.0))
    t = np.arange(rt.min() - 86400.0, rt.max() + 86400.0, 600.0)
    hours = np.asarray([dt.datetime.fromtimestamp(x, tz=LA).hour for x in t])
    y = np.asarray([lvl(h) for h in hours], dtype=float)
    k = np.searchsorted(t, rt, side="right") - 1
    y[k] = y[k] + 10.0 * pain
    rec = {"ChannelNames": ["LeftHemisphere LFP", "LeftHemisphere Amplitude"],
           "Data": np.column_stack([y, np.ones(t.size)]), "Time": t, "SamplingRate": -1,
           "RecordingType": "MedtronicChronicBrainSense", "FreqScheduleHz": [[t[0] - 1.0, freq]],
           "ContactSchedule": [[t[0] - 1.0, "1-3"]]}
    merged, _ = R.merge_chronic_repeats([rec])
    return CBC.chronic_samples_by_pair(merged)


def _reports(n=40, seed=1):
    rng = np.random.default_rng(seed)
    base = _local(2026, 10, 20, 8, 0)
    rt = base + 86400.0 * (np.arange(n) // 3) + 3600.0 * 4 * (np.arange(n) % 3) + 900.0
    return rt.astype(float), rng.normal(5.0, 2.0, n)


def test_no_chronic_coverage_gives_no_home_record_and_keeps_the_report_hours():
    rt, pain = _reports()
    blk = CBC.chronic_band_choice(_chronic_block(rt, pain), {}, rt, pain, centres=CENTRES,
                                  tol_s=900.0, n_boot=100, daily_swing=True)["ONE_THREE_LEFT"]
    hours = DS.report_hours(rt[:5])
    rows = [{"band_center_hz": 12.5, "why": "w", "daily_swing": {"report_hours": hours}},
            {"band_center_hz": 24.5, "why": "w", "daily_swing": {"report_hours": hours}}]
    CBC.attach_daily_swing(rows, blk)
    a, b = rows[0]["daily_swing"], rows[1]["daily_swing"]
    assert a["status"] == DS.STATUS_NO_HOME_RECORD == "no home record at this band"
    assert a["hourly_median"] is None and a["ratio"] is None and a["warning"] is None
    assert a["report_hours"] == hours and rows[0]["why"] == "w"
    assert b["status"] == DS.STATUS_MEASURED
    assert b["chronic_freq_hz"] == blk["by_centre"][24.5]["freq_hz"]
    assert b["ratio"] is not None and b["ratio"] >= DS.SWING_WARN_RATIO
    assert b["report_hours"] == hours                       # the row's own reports, not the log's
    assert rows[1]["why"] == "w. " + b["warning"]
    # a pair with no chronic log at all: every row "no home record"
    rows2 = [{"band_center_hz": 24.5, "daily_swing": {"report_hours": hours}}]
    CBC.attach_daily_swing(rows2, {"by_centre": {}})
    assert rows2[0]["daily_swing"]["status"] == DS.STATUS_NO_HOME_RECORD
    assert "why" not in rows2[0]


def test_the_chronic_answer_is_unchanged_by_the_daily_swing_and_carries_its_own():
    rt, pain = _reports()
    S = _chronic_block(rt, pain)
    off = CBC.chronic_band_choice(S, {}, rt, pain, centres=CENTRES, tol_s=900.0, n_boot=100)
    on = CBC.chronic_band_choice(S, {}, rt, pain, centres=CENTRES, tol_s=900.0, n_boot=100,
                                 daily_swing=True)
    _same(off, _strip(on))
    e = on["ONE_THREE_LEFT"]["by_centre"][24.5]
    ds = e["daily_swing"]
    assert ds["status"] == "measured" and ds["hour_low"] == 3 and ds["hour_high"] == 10
    assert ds["report_hours"]["n_reports"] == e["n_reports"] == rt.size
    # where the chronic log decides the band, the choosing view carries the chronic answer's own
    # daily swing and appends its warning to the chronic `why`; TD's own is kept in td_values
    row = {"band_center_hz": 24.5, "pearson_r": 0.1, "why": "td why",
           "daily_swing": {"report_hours": DS.report_hours(rt[:3])}}
    CBC.label_rows([row], on["ONE_THREE_LEFT"], SW.GRID_SOURCE_TD)
    CBC.attach_daily_swing([row], on["ONE_THREE_LEFT"])
    assert row["choice_source"] == "chronic"
    seen = SW.chronic_decides(row)
    assert seen["daily_swing"] is row["chronic"]["daily_swing"]
    assert seen["daily_swing"]["report_hours"]["n_reports"] == rt.size
    assert seen["why"].endswith(". " + ds["warning"])
    assert seen["td_values"]["daily_swing"]["report_hours"]["n_reports"] == 3
    assert seen["answer"] == e["answer"] and seen["pearson_r"] == e["pearson_r"]


def _grid(n=120, seed=5):
    rng = np.random.default_rng(seed)
    pain = np.clip(np.round(5 + rng.normal(0, 2, n)), 0, 10)
    power = {}
    for L in (1.0, 5.0, 30.0):
        x = 200 + 6 * pain[:, None] + rng.normal(0, 12, (n, 3))
        x[rng.random(x.shape) < 0.1] = np.nan
        power[L] = x
    rt = _local(2026, 9, 1, 7, 0) + 5400.0 * np.arange(n) % (13 * 3600.0) \
        + 86400.0 * np.arange(n)
    return power, pain, rt


def test_the_grid_is_the_same_field_for_field_with_or_without_the_report_hours():
    power, pain, rt = _grid()
    kw = dict(center_freqs_hz=[12.5, 20.5, 24.5], n_perm=60, n_boot=200, seed=3,
              requested_seconds=(1.0, 5.0, 30.0), current_removed_check=True,
              covariate=np.where(np.arange(pain.size) % 2 == 0, 1.0, 2.0))
    neutral = A.band_time_sweep_from_power(power, pain, **kw)
    with_hours = A.band_time_sweep_from_power(power, pain, report_times_s=rt, **kw)
    _same(neutral, _strip(with_hours))                   # every answer, status, p, interval
    assert not any("daily_swing" in r for r in neutral["best_correlation_rows"])
    for c, row in enumerate(with_hours["best_correlation_rows"]):
        # the hours of day of exactly the reports the chosen cell used
        x = np.asarray(power[float(row["integration_seconds_requested"])], float)[:, c]
        m = np.isfinite(x) & np.isfinite(pain)
        assert row["daily_swing"]["report_hours"] == DS.report_hours(rt[m])
        assert row["daily_swing"]["report_hours"]["n_reports"] == row["n_pain_reports"]
    assert not any("daily_swing" in r for r in with_hours["best_auc_rows"])


def test_the_neutral_setting_files_grids_under_the_rule_before_c6():
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    code = ("import sys; sys.path.insert(0, %r);"
            "from modules.Biomarkers.routines import sweep_settings as S, band_results_tables as T;"
            "print(S.DAILY_SWING, S.GRID_RULE_VERSION, T.RULE_VERSION)" % here)
    env = dict(os.environ)
    env.pop("BRAVO_DAILY_SWING", None)
    env["BRAVO_RECENT_CHECK"] = "0"          # C8 off, so the rule in force is C6's own (v33)
    on = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                        timeout=120).stdout.split()
    env["BRAVO_DAILY_SWING"] = "0"
    off = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         timeout=120).stdout.split()
    assert on == ["True", "v33_daily_swing", "v7_daily_swing"], on
    assert off == ["False", "v32_chronic_covering", "v6_chronic_covering"], off
