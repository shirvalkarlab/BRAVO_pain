"""P-03 (June audit items [0] and [22], approved by the PI 2026-09-25).

(b) ONE PAIN REPORT, ONE BLOCK. Several neural samples are matched to one pain report. Each sample
used to be given its own stimulation state (off / low / high current, from the current in force when
it was recorded) and its own elapsed week, so a report whose samples straddled a change of current,
or a week boundary, was counted in two blocks at once. Every sample of one report now takes the
block of the report's EARLIEST matched sample -- the rule `deployment_forward_chaining` already used
for weeks ("Assign each rating cluster to ONE week (its earliest)"), now one helper for every reader
that groups by week or stimulation state.

(a) THE ODDS RATIO IN EACH STIMULATION STATE CARRIES AN INTERVAL, from the same logistic fit that
gives the odds ratio: exp(coefficient +/- 1.96 standard errors), the Wald interval.

The constructed record: 90 reports six hours apart, two samples each (20 minutes either side), and
report 0's samples at -5 and +35 minutes so that the first sample, which fixes where the elapsed
weeks start, puts a week boundary INSIDE reports 28, 56 and 84. The current steps from 0 to 0.7 mA at
report 29's own time and to 2.5 mA at report 59's, so those two reports straddle a change of state.
Plain asserts: runs under the container runner and under pytest.
"""
import datetime as _dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics  # noqa: E402

_T0 = 1_750_000_000.0          # an arbitrary UTC instant; nothing here is a real recording
_H, _M = 3600.0, 60.0
N_REPORTS = 90
Z975 = 1.959963984540054


def _iso(ep):
    return _dt.datetime.utcfromtimestamp(ep).isoformat(sep=" ")


def _report_time(r):
    return _T0 + r * 6 * _H


def _constructed(seed=0):
    rng = np.random.default_rng(seed)
    t, rg = [], []
    for r in range(N_REPORTS):
        offs = (-5 * _M, 35 * _M) if r == 0 else (-20 * _M, 20 * _M)
        for o in offs:
            t.append(_report_time(r) + o)
            rg.append(r)
    t = np.asarray(t); rg = np.asarray(rg)
    pain = rng.normal(5, 2, N_REPORTS)
    labels = pain[rg]
    F = 60
    f = np.linspace(0.95, 100, F)
    psd = np.abs(rng.normal(1, 0.2, (t.size, 2, F)))
    band = (f >= 17.5) & (f <= 22.5)
    psd[:, 0, band] *= (1 + 0.15 * (labels - labels.mean()))[:, None]
    detail = {"f_set": f, "psd": psd, "labels": labels, "rating_group": rg,
              "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "times": [_iso(x) for x in t]}
    stim = {"t": [_T0 - 10 * _H, _report_time(29), _report_time(59)], "y": [0.0, 0.7, 2.5]}
    return detail, stim, t, rg


def test_the_constructed_record_really_splits_five_reports():
    """The control: under the per-sample rules the record does split reports 28, 56, 84 across
    weeks and 29, 59 across states. Without this the tests below could pass on a record that never
    split anything."""
    detail, stim, t, rg = _constructed()
    wk = analytics._elapsed_week_cluster(detail["times"], t.size)
    era = analytics._assign_stim_eras(detail["times"], stim)
    split_wk = sorted(int(r) for r in np.unique(rg) if len(set(wk[rg == r])) > 1)
    split_era = sorted(int(r) for r in np.unique(rg) if len(set(era[rg == r])) > 1)
    assert split_wk == [28, 56, 84], split_wk
    assert split_era == [29, 59], split_era


def test_one_block_per_report_takes_the_earliest_samples_block():
    blocks = np.array(["OFF", "LOW", "LOW", "LOW", "HIGH", "OFF", None], dtype=object)
    rg = np.array([7, 7, 3, 3, 9, -1, 9])
    t = np.array([10.0, 20.0, 5.0, 6.0, 30.0, 1.0, 25.0])
    out, info = analytics._one_block_per_report(blocks, rg, t)
    # report 7 straddled OFF/LOW and its earliest sample was OFF; report 3 never straddled; the
    # unmatched row (-1) and the row with no block are left exactly as they were
    assert list(out) == ["OFF", "OFF", "LOW", "LOW", "HIGH", "OFF", None], list(out)
    assert info == {"n_reports": 3, "n_reports_split": 1, "n_samples_moved": 1}, info
    # earliest by TIME, not by row order
    out2, _ = analytics._one_block_per_report(np.array([2, 1]), np.array([4, 4]), np.array([9.0, 3.0]))
    assert list(out2) == [1, 1], list(out2)
    # integer week blocks: -1 means "no parseable time" and is never a block to copy
    out3, info3 = analytics._one_block_per_report(np.array([-1, 0, 1]), np.array([5, 5, 5]),
                                                   np.array([1.0, 2.0, 3.0]), invalid=-1)
    assert list(out3) == [-1, 0, 0] and info3["n_reports_split"] == 1, (out3, info3)


def test_stability_test_counts_each_report_in_one_state_and_one_week():
    detail, stim, _, _ = _constructed()
    out = analytics.band_stim_stability(detail, "ZERO_TWO_LEFT", 20.0, stim_series=stim,
                                        strategy="median")
    if not out.get("available"):
        assert "reason" in out, out
        assert "unavailable" in out["reason"], out     # no R here: nothing else may fail
        return
    ob = out["one_block_per_report"]
    assert ob["n_reports_split_across_states"] == 2, ob
    assert ob["n_reports_split_across_weeks"] == 3, ob
    # per sample: 59 OFF / 60 LOW / 61 HIGH; one state per report: 60 / 60 / 60
    assert out["era_counts"] == {"OFF": 60, "LOW": 60, "HIGH": 60}, out["era_counts"]


def test_the_odds_ratio_in_each_state_carries_its_interval_from_the_same_fit():
    detail, stim, _, _ = _constructed()
    out = analytics.band_stim_stability(detail, "ZERO_TWO_LEFT", 20.0, stim_series=stim,
                                        strategy="median")
    if not out.get("available"):
        return                                          # no R: the fit cannot run here
    assert "Wald" in out["or_by_era_interval"], out.get("or_by_era_interval")
    for tag in ("OFF", "LOW", "HIGH"):
        orv, ci, sl = out["or_by_era"][tag], out["or_by_era_ci"][tag], out["slope_by_era"][tag]
        assert orv is not None and ci is not None and sl is not None, (tag, orv, ci, sl)
        b, se = sl["slope_log_or"], sl["se"]
        # the same fit: the odds ratio is exp(b); the interval is exp(b -/+ 1.96 se)
        assert abs(orv - np.exp(b)) <= 1e-12 * max(1.0, orv), (tag, orv, b)
        assert abs(ci[0] - np.exp(b - Z975 * se)) <= 1e-12 * max(1.0, ci[0]), (tag, ci, b, se)
        assert abs(ci[1] - np.exp(b + Z975 * se)) <= 1e-12 * max(1.0, ci[1]), (tag, ci, b, se)
        assert ci[0] < orv < ci[1], (tag, ci, orv)


def test_per_state_roc_counts_each_report_in_one_state():
    detail, stim, _, _ = _constructed()
    out = analytics.deployment_roc_by_era(detail, "ZERO_TWO_LEFT", 20.0, stim, strategy="median",
                                          n_boot=20)
    assert out.get("available"), out
    assert out["era_counts"] == {"OFF": 60, "LOW": 60, "HIGH": 60}, out["era_counts"]
    assert out["one_block_per_report"]["n_reports_split_across_states"] == 2, out["one_block_per_report"]


def test_mixed_model_puts_each_report_in_one_week():
    detail, _, _, _ = _constructed()
    out = analytics.band_mixedmodel_inference(detail, "ZERO_TWO_LEFT", 20.0, strategy="median",
                                              exclude_first_weeks=0)
    if not out.get("available"):
        assert "unavailable" in out.get("reason", ""), out
        return
    assert out["one_block_per_report"]["n_reports_split_across_weeks"] == 3, out["one_block_per_report"]
    assert out["one_block_per_report"]["n_samples_moved"] == 3, out["one_block_per_report"]


def test_weekly_cut_point_check_puts_each_report_in_one_week():
    detail, _, _, _ = _constructed()
    out = analytics.threshold_drift_by_week(detail, "ZERO_TWO_LEFT", 20.0, strategy="median")
    assert out.get("available"), out
    n_by_week = {d["week"]: d["n"] for d in out["weekly"]}
    # weeks start at report 0's first sample (-5 min): per sample, week 0 held reports 0-27 and the
    # first sample of report 28 (57 samples); one week per report, the earliest: 58
    assert n_by_week.get(0) == 58, n_by_week
    assert out["one_block_per_report"]["n_reports_split_across_weeks"] == 3, out["one_block_per_report"]
