"""The per-state odds-ratio intervals, and the "behaves the same" check that reads the same standard
error, count each pain report once (the PI, 2026-09-25 night, the P-03 follow-up).

Several neural samples are matched to one pain report, and every one of them carries that report's
rating. The per-state logistic fit behind the odds ratio treated every sample as independent, so a
report matched to ten samples counted ten times and the interval came out narrower than the data
justify. The standard error is now CLUSTERED ON THE PAIN REPORT: the CR1 sandwich (the fit's own
information matrix either side of the summed per-report score products, times the small-sample
factor G/(G-1) * (N-1)/(N-K), G reports, N samples, K = 2 coefficients) -- statsmodels'
`cov_type="cluster"` with its default correction, which is Stata's. The odds ratio itself does not
move; only its standard error does.

The first two tests need no R and run under both runners; the third needs the mixed model and is
skipped (as a plain return) where R is absent.
"""
import datetime as _dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics  # noqa: E402

Z975 = 1.959963984540054


def _frame(n_reports=40, per_report=1, seed=3):
    """One stimulation state, `n_reports` reports each matched to `per_report` IDENTICAL samples."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n_reports)
    p = 1 / (1 + np.exp(-(0.2 + 0.9 * x)))
    y = (rng.uniform(size=n_reports) < p).astype(int)
    rep = np.repeat(np.arange(n_reports), per_report)
    return pd.DataFrame({"pain_high": y[rep], "band_power": x[rep],
                         "stim_era": pd.Categorical(["OFF"] * rep.size,
                                                    categories=["OFF", "LOW", "HIGH"]),
                         "report": rep})


def _cr1_by_hand(df):
    """The CR1 sandwich for the slope, written out, so the test names the estimator exactly."""
    import statsmodels.api as sm
    X = sm.add_constant(df["band_power"].to_numpy())
    y = df["pain_high"].to_numpy()
    fit = sm.GLM(y, X, family=sm.families.Binomial()).fit()
    mu = fit.fittedvalues
    bread = np.linalg.inv((X * (mu * (1 - mu))[:, None]).T @ X)
    scores = X * (y - mu)[:, None]
    g = df["report"].to_numpy()
    meat = np.zeros((2, 2))
    for k in np.unique(g):
        s = scores[g == k].sum(axis=0)
        meat += np.outer(s, s)
    G, N, K = np.unique(g).size, len(y), 2
    cov = (G / (G - 1)) * ((N - 1) / (N - K)) * bread @ meat @ bread
    return float(fit.params[1]), float(np.sqrt(cov[1, 1])), float(fit.bse[1])


def test_the_state_slope_carries_the_cr1_standard_error_clustered_on_the_pain_report():
    df = _frame(n_reports=40, per_report=3)
    df.loc[df.index % 3 == 1, "band_power"] += 0.05       # samples of one report need not be identical
    tbl = analytics._era_slope_table(df, group_col="report")
    b, se_cr1, se_plain = _cr1_by_hand(df)
    got = tbl["OFF"]
    assert abs(got["slope_log_or"] - b) <= 1e-12, (got, b)
    assert abs(got["se"] - se_cr1) <= 1e-9 * se_cr1, (got["se"], se_cr1)
    assert abs(got["se_unclustered"] - se_plain) <= 1e-12, (got["se_unclustered"], se_plain)
    assert got["n"] == 120 and got["n_reports"] == 40, got
    assert "CR1" in got["se_method"] and "pain report" in got["se_method"], got["se_method"]
    assert tbl["LOW"] is None and tbl["HIGH"] is None


def test_each_rating_counts_once_however_many_samples_it_matched():
    """The point of the change. Copy every report's one sample six times: the unclustered standard
    error shrinks by the square root of six (the fit thinks it has six times the data); the one
    clustered on the report stays where the one-sample-per-report fit put it."""
    one = analytics._era_slope_table(_frame(per_report=1), group_col="report")["OFF"]
    six = analytics._era_slope_table(_frame(per_report=6), group_col="report")["OFF"]
    assert abs(six["slope_log_or"] - one["slope_log_or"]) <= 1e-6
    assert abs(six["se_unclustered"] * np.sqrt(6) - one["se_unclustered"]) <= 1e-4 * one["se_unclustered"]  # the fit stops at its own tolerance
    ratio = six["se"] / one["se_unclustered"]
    assert 0.75 < ratio < 1.35, ratio
    assert six["se"] > 2.0 * six["se_unclustered"], (six["se"], six["se_unclustered"])


def test_a_state_resting_on_one_pain_report_has_no_standard_error():
    df = _frame(n_reports=1, per_report=8)
    df["pain_high"] = [0, 1] * 4                          # both classes, one report
    assert analytics._era_slope_table(df, group_col="report")["OFF"] is None


def test_without_a_report_column_the_fit_says_it_counted_samples():
    tbl = analytics._era_slope_table(_frame(per_report=2))
    got = tbl["OFF"]
    assert got["se"] == got["se_unclustered"]
    assert "not clustered" in got["se_method"], got["se_method"]


# --- the stability test itself (needs R for its mixed-model comparison) ----------------------
_T0 = 1_750_000_000.0
_H, _M = 3600.0, 60.0


def _iso(ep):
    return _dt.datetime.utcfromtimestamp(ep).isoformat(sep=" ")


def _detail(seed=0, per_report=4):
    rng = np.random.default_rng(seed)
    n = 90
    t, rg = [], []
    for r in range(n):
        for k in range(per_report):
            t.append(_T0 + r * 6 * _H + (k - per_report / 2) * 10 * _M)
            rg.append(r)
    t, rg = np.asarray(t), np.asarray(rg)
    pain = rng.normal(5, 2, n)
    F = 60
    f = np.linspace(0.95, 100, F)
    psd = np.abs(rng.normal(1, 0.2, (t.size, 1, F)))
    band = (f >= 17.5) & (f <= 22.5)
    psd[:, 0, band] *= (1 + 0.15 * (pain[rg] - pain.mean()))[:, None]
    detail = {"f_set": f, "psd": psd, "labels": pain[rg], "rating_group": rg,
              "chan_order": ["ZERO_TWO_LEFT"], "times": [_iso(x) for x in t]}
    # the current steps three hours before reports 30 and 60, so no report straddles a step
    stim = {"t": [_T0 - 10 * _H, _T0 + (30 * 6 - 3) * _H, _T0 + (60 * 6 - 3) * _H],
            "y": [0.0, 0.7, 2.5]}
    return detail, stim


def test_the_stability_test_reads_the_clustered_error_for_intervals_and_the_verdict():
    detail, stim = _detail()
    out = analytics.band_stim_stability(detail, "ZERO_TWO_LEFT", 20.0, stim_series=stim,
                                        strategy="median")
    if not out.get("available"):
        assert "unavailable" in out.get("reason", ""), out
        return
    assert "clustered on the pain report" in out["or_by_era_interval"], out["or_by_era_interval"]
    for tag in ("OFF", "LOW", "HIGH"):
        sl, ci = out["slope_by_era"][tag], out["or_by_era_ci"][tag]
        assert sl["n_reports"] == 30 and sl["n"] == 120, (tag, sl)
        assert sl["se"] != sl["se_unclustered"], (tag, sl)
        assert abs(ci[0] - np.exp(sl["slope_log_or"] - Z975 * sl["se"])) <= 1e-12 * ci[0]
        assert abs(ci[1] - np.exp(sl["slope_log_or"] + Z975 * sl["se"])) <= 1e-12 * ci[1]
        assert out["or_by_era_n_reports"][tag] == 30
    eq = out["equivalence"]
    a, b = eq["pair"].split(" vs ")
    se = np.sqrt(out["slope_by_era"][a]["se"] ** 2 + out["slope_by_era"][b]["se"] ** 2)
    half = (eq["ci"][1] - eq["ci"][0]) / 2.0
    assert abs(half - 1.6448536269514722 * se) <= 1e-9, (half, se)
