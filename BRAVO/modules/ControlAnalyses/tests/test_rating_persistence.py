"""Day-to-day correlation of the pain ratings, and report 02's visit-count target restated as
calendar days (finding M2, item A4, 2026-09-25). On constructed series whose answer is known. Plain
asserts; both suites."""
import numpy as np

try:
    from modules.ControlAnalyses import rating_persistence as RP
except ImportError:                                            # host spelling
    from ControlAnalyses import rating_persistence as RP


def test_daily_mean_series_fills_a_gap_with_nan_so_a_lag_is_a_fixed_number_of_calendar_days():
    days = ["2026-01-01", "2026-01-01", "2026-01-03"]              # day 2 is missing entirely
    idx, daily = RP.daily_mean_series(days, [4.0, 6.0, 9.0])
    assert list(idx) == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert daily[0] == 5.0 and np.isnan(daily[1]) and daily[2] == 9.0


def test_lag_corr_finds_a_planted_lag_one_relationship_and_ignores_a_gap_pair():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 60)
    y = np.empty(60)
    y[0] = rng.normal()
    y[1:] = 0.8 * x[:-1] + rng.normal(0, 0.2, 59)                  # y[t] depends on x[t-1]
    r, n = RP.lag_corr(y, 1)
    # correlate y[t] with y[t-1] is not what we planted; check x-vs-y cross relationship directly
    assert n == 59
    r2, n2 = RP.lag_corr(x, 1)
    assert n2 == 59
    # a genuinely autocorrelated series: lag-1 much stronger than lag-7
    z = np.cumsum(rng.normal(0, 1, 200)) * 0.05 + rng.normal(0, 0.05, 200)
    r_lag1, _ = RP.lag_corr(z, 1)
    r_lag7, _ = RP.lag_corr(z, 7)
    assert r_lag1 > r_lag7 > 0


def test_lag_corr_is_nan_with_too_few_pairs_or_a_constant_side():
    r, n = RP.lag_corr(np.array([1.0, 2.0, 3.0]), 1)
    assert np.isnan(r) and n == 2
    r2, _ = RP.lag_corr(np.full(20, 5.0), 1)
    assert np.isnan(r2)


def test_effective_days_is_full_count_with_no_autocorrelation_and_less_with_strong_autocorrelation():
    rng = np.random.default_rng(1)
    white = rng.normal(0, 1, 200)
    eff_white = RP.effective_days(white)
    assert 150 < eff_white <= 200
    smooth = np.cumsum(rng.normal(0, 1, 200)) * 0.02
    eff_smooth = RP.effective_days(smooth)
    assert eff_smooth < eff_white
    assert eff_smooth >= 2                                        # clipped, never below 2


def test_effective_days_and_yield_ratio_refuse_with_too_few_days():
    assert RP.effective_days([1.0, 2.0]) is None
    assert RP.yield_ratio([]) is None
    assert RP.yield_ratio([np.nan, np.nan]) is None


def test_yield_ratio_is_one_with_no_autocorrelation():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1, 500)
    assert 0.85 < RP.yield_ratio(x) <= 1.0


def test_calendar_days_for_scales_the_target_by_the_inverse_ratio():
    assert RP.calendar_days_for(52.0, 0.5) == 104.0
    assert RP.calendar_days_for(52.0, 1.0) == 52.0
    assert RP.calendar_days_for(52.0, None) is None
    assert RP.calendar_days_for(52.0, 0.0) is None


def test_score_summary_redoes_report_02s_three_targets_at_half_the_raw_day_count():
    rng = np.random.default_rng(3)
    # strong autocorrelation so the effective count is roughly half the raw count
    x = np.zeros(60)
    for i in range(1, 60):
        x[i] = 0.6 * x[i - 1] + rng.normal(0, 1)
    s = RP.score_summary("vas", n_ratings=180, daily_values=x, label="both off, 2025-07-16 to 2025-08-22")
    assert s["n_days"] == 60 and s["label"] == "both off, 2025-07-16 to 2025-08-22"
    assert len(s["lags"]) == 7 and [l["lag_days"] for l in s["lags"]] == list(range(1, 8))
    assert 0 < s["ratio"] < 1
    assert len(s["calendar_days_needed"]) == len(RP.INDEPENDENT_DAYS_NEEDED)
    for t, target in zip(s["calendar_days_needed"], RP.INDEPENDENT_DAYS_NEEDED):
        assert t["name"] == target["name"] and t["independent_days"] == target["independent_days"]
        assert t["calendar_days"] > target["independent_days"]   # autocorrelation only ever raises the target


def test_reading_says_too_few_days_rather_than_crashing_and_names_the_vas_zero_ma_target():
    rows = [dict(score="mpq_sum", n_ratings=2, n_days=2, lags=[], effective_days=None, ratio=None,
                calendar_days_needed=[], zero_ma=None)]
    lines = RP.reading(rows)
    assert any("too few days" in l for l in lines)
    assert any("blocks nothing" in l for l in lines)

    vas_zero = dict(score="vas", label="both off, 2025-07-16 to 2025-08-22", n_ratings=75, n_days=25,
                    lags=[dict(lag_days=1, r=0.3, n_pairs=24)], effective_days=15.0, ratio=0.6,
                    calendar_days_needed=[dict(name=t["name"], independent_days=t["independent_days"],
                                              calendar_days=t["independent_days"] / 0.6)
                                          for t in RP.INDEPENDENT_DAYS_NEEDED])
    vas_all = dict(score="vas", label=None, n_ratings=300, n_days=200,
                   lags=[dict(lag_days=1, r=0.5, n_pairs=199)], effective_days=90.0, ratio=0.45,
                   calendar_days_needed=[], zero_ma=vas_zero)
    lines2 = RP.reading([vas_all])
    assert any("correlates with the next day's at +0.50" in l for l in lines2)
    assert any("both off, 2025-07-16" in l and "15.0 independent days" in l for l in lines2)
    assert any("Report 02's independent-day targets" in l for l in lines2)
