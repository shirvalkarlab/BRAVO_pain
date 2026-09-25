"""Decision 246's clock-and-weekend check, now one copy in the package (2026-09-24): a planted daily
cycle is found where it was planted and nowhere else; a planted weekend step in pain is found within
weeks. Plain asserts; both suites."""
from datetime import datetime, timezone

import numpy as np

try:
    from modules.ControlAnalyses import time_of_day as TD
except ImportError:
    from ControlAnalyses import time_of_day as TD


def test_a_planted_1500_cycle_is_found_at_its_band_and_not_elsewhere():
    rng = np.random.default_rng(0)
    n = 600
    t0 = datetime(2026, 1, 5, tzinfo=TD.CA).timestamp()
    t = np.sort(t0 + rng.uniform(0, 60 * 86400, n))
    hour = np.array([d.hour + d.minute / 60.0 for d in (datetime.fromtimestamp(v, tz=timezone.utc).astimezone(TD.CA) for v in t)])
    f_set = np.arange(5.0, 35.0, 1.0)
    X = rng.normal(100, 10, (n, f_set.size))
    X[:, (f_set >= 18) & (f_set <= 22)] += (30 * np.cos(2 * np.pi * (hour - 15.0) / 24.0))[:, None]
    rows = TD.rows_for(X, t, ["ONE_THREE_LEFT"] * n, f_set, rng=np.random.default_rng(1), n_boot=300, n_shuffle=100)
    b = {r["centre_hz"]: r for r in rows}
    assert b[20.5]["R_daily_ci"][0] > b[20.5]["R_daily_shuffle_p95"]
    assert abs(b[20.5]["R_daily_peak_hour"] - 15.0) < 1.0
    assert b[10.5]["R_daily_ci"][0] <= b[10.5]["R_daily_shuffle_p95"]


def test_a_weekend_step_in_pain_is_found_within_weeks_and_a_drift_is_not():
    rng = np.random.default_rng(3)
    t0 = datetime(2026, 1, 5, 12, tzinfo=TD.CA).timestamp()          # a Monday
    t = t0 + np.arange(0, 70) * 86400.0
    wk = np.array([datetime.fromtimestamp(x, tz=timezone.utc).astimezone(TD.CA).weekday() >= 5 for x in t])
    drift = np.linspace(8, 5, t.size)                                # slow fall over ten weeks
    got = TD.weekend_pain(t, drift + 0.8 * wk + rng.normal(0, 0.1, t.size), rng=np.random.default_rng(0), n_boot=500)
    assert 0.6 < got["within_week"] < 1.0 and got["p"] < 0.01
    none = TD.weekend_pain(t, drift + rng.normal(0, 0.1, t.size), rng=np.random.default_rng(0), n_boot=500)
    assert abs(none["within_week"]) < 0.2                            # the drift alone leaks under 0.2
