"""Decision 194 (the PI, 2026-09-17: "drop the age term and add time as fitted input to model").

The noise model's age penalty (0.25 x years²) was a placeholder that a hold-out fit showed to be
inert (decision 193). It is gone. In its place the objective model takes TIME as a fourth input --
months since the record began -- with its own fitted length scale, and every surface on the current
map is the prediction AT THE PRESENT (the end of the newest epoch). A rating that has been falling
for a year then pulls the map toward today's level instead of the year's average.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import objective as OBJ
from StimOptimizer.routines import surrogate as SUR
from StimOptimizer import stage1_openloop as S1


def _two_epochs_a_year_apart():
    return pd.DataFrame({
        "epoch": [1, 2], "freq_hz": [55.0, 55.0], "amp_mA_Left": [1.6, 1.6], "amp_mA_Right": [1.2, 1.2],
        "pw_us_Left": [60.0, 60.0], "pw_us_Right": [160.0, 160.0], "n": [20, 20],
        "t0": pd.to_datetime(["2026-06-01", "2025-06-01"], utc=True), "dur_h": [200.0, 200.0],
        "left_leg_vas": [60.0, 60.0], "left_leg_vas_sd": [10.0, 10.0]})


def test_the_age_penalty_is_gone_two_identical_epochs_a_year_apart_weigh_the_same():
    d = OBJ.build_objective(_two_epochs_a_year_apart(), incumbent_epoch=1).set_index("epoch")
    assert d.loc[1, "obs_var"] == d.loc[2, "obs_var"]
    assert "c_age" not in OBJ.DEFAULTS


def test_the_time_aware_grid_appends_now_when_no_time_is_given_and_keeps_an_explicit_one():
    base = SUR.JointParameterGrid([55.0], [1.0, 2.0], [1.0, 2.0])
    g = SUR.TimeAwareGrid(base, t_obs_months=[0.0, 6.0, 12.0], t_now_months=12.0)
    z_now = g.transform([[55.0, 1.0, 1.0]])
    z_12 = g.transform([[55.0, 1.0, 1.0, 12.0]])
    z_0 = g.transform([[55.0, 1.0, 1.0, 0.0]])
    assert z_now.shape == (1, 4) and np.allclose(z_now, z_12) and not np.allclose(z_now, z_0)
    # the settings axes are the base grid's own, untouched
    assert np.allclose(z_now[:, :3], base.transform([[55.0, 1.0, 1.0]]))
    # the search grid itself carries no time column; a prediction on it is a prediction at now
    assert g.grid_X().shape[1] == 3 and len(g) == len(base) and g.shape == base.shape
    assert list(g.index_of([[55.0, 2.0, 1.0, 3.0]])) == list(base.index_of([[55.0, 2.0, 1.0]]))


def test_a_pure_time_trend_is_fitted_and_the_grid_is_predicted_at_now():
    rng = np.random.default_rng(0)
    base = SUR.JointParameterGrid([55.0], np.arange(0, 5.01, 0.5), np.arange(0, 5.01, 0.5))
    t = np.linspace(0.0, 12.0, 40)
    X = np.column_stack([np.full(40, 55.0), rng.uniform(0.5, 4.5, 40), rng.uniform(0.5, 4.5, 40), t])
    y = 0.3 * t + rng.normal(0, 0.05, 40)               # the settings do nothing; time does
    g = SUR.TimeAwareGrid(base, t_obs_months=t, t_now_months=12.0)
    gp = SUR.ObjectiveGP(g, fixed_length_scale=(0.823, None, None), random_state=0).fit(X, y, np.full(40, 0.05 ** 2))
    mu_now, _ = gp.predict_grid()
    assert abs(float(np.median(mu_now)) - 0.3 * 12.0) < 0.3, float(np.median(mu_now))
    mu_start, _ = gp.predict([[55.0, 2.0, 2.0, 0.0]])
    assert abs(float(mu_start[0])) < 0.3, float(mu_start[0])
    assert 0 < gp.time_length_scale_months < 1000


def test_the_time_length_scale_cannot_fall_below_the_floor_so_time_cannot_absorb_epoch_noise():
    """Epochs three days apart with independent noise: without a floor the likelihood drives the
    time scale down to the epoch spacing and the settings surface goes flat (measured, decision
    194). With it, the fitted scale is at least the floor and the settings still carry the effect."""
    rng = np.random.default_rng(3)
    base = SUR.JointParameterGrid([55.0], np.arange(0, 5.01, 0.5), np.arange(0, 5.01, 0.5))
    t = np.arange(30) * 0.1                                    # 3 days apart, three months in all
    aL = rng.uniform(0.5, 4.5, 30); aR = rng.uniform(0.5, 4.5, 30)
    X = np.column_stack([np.full(30, 55.0), aL, aR, t])
    y = -0.4 * aL + rng.normal(0, 0.3, 30)                     # a real left-current effect, noise, no drift
    g = SUR.TimeAwareGrid(base, t_obs_months=t, t_now_months=3.0)
    gp = SUR.ObjectiveGP(g, fixed_length_scale=(0.823, None, None), random_state=0).fit(X, y, np.full(30, 0.3 ** 2))
    assert gp.time_length_scale_months >= SUR.TIME_LENGTH_SCALE_FLOOR_MONTHS - 1e-9
    mu, _ = gp.predict_grid()
    surf = g.as_surface(mu)[0]                                 # (left, right)
    assert surf[-1].mean() < surf[0].mean() - 0.5, "the left-current effect must survive on the surface"


def _falling_record(n_months=14, seed=1):
    """One pulse-width pairing, 55 Hz, currents wandering, the rating falling 0.15 points a month
    on the 0-10 scale with the settings doing nothing. The incumbent is the newest epoch."""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_months * 2):
        month = k / 2.0
        rows.append(dict(epoch=float(k + 1), freq_hz=55.0, pw_us_Left=60.0, pw_us_Right=160.0,
                         amp_mA_Left=float(rng.choice([1.0, 1.5, 2.0, 2.5, 3.0, 3.5])),
                         amp_mA_Right=float(rng.choice([1.0, 1.5, 2.0, 2.5, 3.0, 3.5])),
                         n=12.0, dur_h=300.0,
                         t0=pd.Timestamp("2025-07-01", tz="UTC") + pd.Timedelta(days=30.44 * month),
                         left_leg_vas=float(10 * (6.0 - 0.15 * month + rng.normal(0, 0.15))),
                         left_leg_vas_sd=12.0))
    return pd.DataFrame(rows)


def test_stage_one_follows_a_falling_rating_to_the_present_and_reports_the_fitted_time_scale():
    d = _falling_record()
    on = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    off = S1.run_stage1(d, data_horizon="test", washin_min=1.0, time_input=False)
    sl_on = on.slices[(60.0, 160.0)]; sl_off = off.slices[(60.0, 160.0)]
    # J is relative to the newest epoch. Without time, the surface sits at the year's average,
    # about +1 point above today; with time, the surface at the present sits near today.
    assert sl_off.incumbent_mu > 0.6, sl_off.incumbent_mu
    assert abs(sl_on.incumbent_mu) < 0.4, sl_on.incumbent_mu
    row = on.rate_summary.iloc[0]
    assert np.isfinite(row["time_length_scale_months"]) and bool(row["time_input"]) is True
    assert on.rate_strata_time["enabled"] is True and on.rate_strata_time["reference_time_utc"]
    assert bool(off.rate_summary.iloc[0]["time_input"]) is False
