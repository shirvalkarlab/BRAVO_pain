"""Pooling across pulse widths, decision 189's option A, built behind a toggle (the PI, 2026-09-21:
"we want to pool across pulse widths, so I'll put that toggle into the third decision").

Today each (pulse-width-Left, pulse-width-Right) pairing is its own stratum, and a rate inside it
with fewer than `RATE_STRATUM_MIN_EPOCHS` epochs is not fitted. Option A fits ONE surface per
rate over EVERY pairing, with the two pulse widths as two more inputs to the model, and reads
the (left current, right current) surface at the pairing in force. More epochs per fit, at the
cost of assuming the current-to-pain shape is shared across pairings. Both fits are computed in
one Stage 1 run and reported side by side; the page draws the separate fit unless the reader
toggles to the pooled one. The default stays separate.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import bravo_service as BS
from StimOptimizer import stage1_openloop as S1
from StimOptimizer.routines import surrogate as SUR


def _matrix_two_pairings():
    """55 Hz at two pulse-width pairings: (60, 160) with 5 epochs (below the 8-epoch floor on its
    own) and (100, 100) with 7 (also below on its own); together 12, which clears it. 10 Hz at
    (60, 160) with 9 epochs, which clears the floor alone. The incumbent is the last epoch, at
    55 Hz and (60, 160)."""
    rng = np.random.default_rng(1)
    rows, ep = [], 0
    for rate, pwl, pwr, n in ((10.0, 60.0, 160.0, 9), (55.0, 100.0, 100.0, 7), (55.0, 60.0, 160.0, 5)):
        for k in range(n):
            ep += 1
            rows.append(dict(
                epoch=float(ep), freq_hz=rate, pw_us_Left=pwl, pw_us_Right=pwr,
                amp_mA_Left=1.0 + 0.5 * (k % 5), amp_mA_Right=1.0 + 0.5 * ((k + 2) % 5), n=6.0,
                dur_h=180.0, left_leg_vas=float(50.0 - 2.0 * (k % 5) + 3.0 * rng.standard_normal()),
                left_leg_vas_sd=7.5))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


@pytest.fixture(scope="module")
def s1():
    return S1.run_stage1(_matrix_two_pairings(), data_horizon="test", washin_min=1.0)


def test_the_pooled_grid_standardises_the_two_pulse_width_inputs_and_reads_at_the_pairing_in_force():
    g = SUR.PooledPulseWidthGrid(55.0, [1.0, 2.0, 3.0], [1.0, 2.0, 3.0],
                                 pw_left_levels=[60.0, 100.0], pw_right_levels=[100.0, 160.0],
                                 pw_left_at=60.0, pw_right_at=160.0)
    X = g.grid_X()
    assert X.shape == (9, 5) and g.shape == (1, 3, 3)
    assert set(X[:, 0]) == {55.0} and set(X[:, 3]) == {60.0} and set(X[:, 4]) == {160.0}
    Z = g.transform([[55.0, 2.0, 2.0, 60.0, 160.0], [55.0, 2.0, 2.0, 100.0, 100.0]])
    assert Z.shape == (2, 5)
    assert Z[0, 0] == 0.0 and Z[0, 1] == 0.0 and Z[0, 2] == 0.0      # the rate and the mid currents sit at 0
    assert Z[0, 3] == -Z[1, 3] and Z[0, 4] == -Z[1, 4]                 # the two levels are mirror images
    # a side with ONE observed level is not blown up by a zero scatter
    g1 = SUR.PooledPulseWidthGrid(55.0, [1.0, 2.0], [1.0, 2.0], pw_left_levels=[60.0],
                                  pw_right_levels=[160.0], pw_left_at=60.0, pw_right_at=160.0)
    assert np.all(np.isfinite(g1.transform([[55.0, 1.0, 1.0, 60.0, 160.0]])))
    with pytest.raises(ValueError):
        g.transform([[55.0, 1.0, 1.0]])


def test_the_pooled_rate_stratum_fits_where_the_separate_ones_cannot(s1):
    # separate: 55 Hz is below the floor in BOTH pairings, so neither pairing has a fitted 55 Hz
    sep = s1.rate_summary
    sep55 = sep.loc[sep["rate_hz"] == 55.0]
    assert len(sep55) >= 1 and not bool(sep55["fitted"].any())
    # pooled: one row per rate, at the pairing in force, 55 Hz fitted on 12 epochs over 2 pairings
    pooled = s1.pooled_rate_summary
    assert list(pooled["rate_hz"]) == sorted(pooled["rate_hz"])
    p55 = pooled.loc[pooled["rate_hz"] == 55.0].iloc[0]
    assert bool(p55["fitted"]) and int(p55["n_epochs"]) == 12
    assert p55["pw_us_left"] == 60.0 and p55["pw_us_right"] == 160.0     # the pairing in force
    assert int(p55["n_pairings_pooled"]) == 2
    assert bool(p55["pooled_pulse_widths"]) is True
    rs = s1.pooled_rate_strata[55.0]
    assert rs.fitted and rs.mu.shape == rs.sd.shape == rs.safe.shape
    assert rs.meta["pooled_pulse_widths"] is True
    assert sorted((p["pw_us_left"], p["pw_us_right"], p["n_epochs"]) for p in rs.meta["pairings"]) == \
        [(60.0, 160.0, 5), (100.0, 100.0, 7)]
    assert all("pw_us_left" in p and "pw_us_right" in p for p in rs.meta["points"])
    assert len(rs.meta["points"]) == 12
    # 10 Hz: one pairing only, fitted on its 9 epochs; the pooled and separate fits see the same rows
    p10 = pooled.loc[pooled["rate_hz"] == 10.0].iloc[0]
    assert bool(p10["fitted"]) and int(p10["n_epochs"]) == 9 and int(p10["n_pairings_pooled"]) == 1


def test_the_separate_fit_is_untouched_by_the_pooled_one(s1):
    """The pooled fit is ADDED; nothing about the per-pairing strata, the frozen configuration or
    the rate summary moves. Proved by refitting with pooling off and comparing value for value."""
    off = S1.run_stage1(_matrix_two_pairings(), data_horizon="test", washin_min=1.0,
                        pool_pulse_widths=False)
    assert off.pooled_rate_strata == {} and off.pooled_rate_summary.empty
    pd.testing.assert_frame_equal(off.rate_summary, s1.rate_summary)
    pd.testing.assert_frame_equal(off.summary, s1.summary)
    assert off.frozen.describe() == s1.frozen.describe()
    assert set(off.slices) == set(s1.slices)
    assert off.audit["pulse_width_pooling"]["computed"] is False
    assert s1.audit["pulse_width_pooling"]["computed"] is True
    assert s1.audit["pulse_width_pooling"]["default"] == "separate"


def test_the_pooled_three_checks_count_current_pairs_across_pairings(s1):
    """Coverage under option A counts (left, right) current pairs over every pairing -- the honest
    reason A resolves more often (decision 189) -- and the row says so."""
    p55 = s1.pooled_rate_summary.loc[s1.pooled_rate_summary["rate_hz"] == 55.0].iloc[0]
    rs = s1.pooled_rate_strata[55.0]
    cov = rs.coverage
    # every distinct (left, right) pair over the 12 epochs, not only the in-force pairing's 5
    all_pairs = _matrix_two_pairings().query("freq_hz == 55").groupby(["amp_mA_Left", "amp_mA_Right"]).ngroups
    assert cov["n_pairs_enough_reports"] == all_pairs
    assert p55["coverage_n_pairs"] == cov["n_pairs"]
    for k in ("flat_passes", "gain_passes", "coverage_passes", "resolved", "sentence"):
        assert k in p55.index
    # the gain check compares against the setting in force at ITS rate (55 Hz is the incumbent's)
    assert p55["gain_passes"] in (True, False)
    assert np.isfinite(p55["gain"])
    # at 10 Hz, which is not the rate in force, the pooled fit has nothing to compare a gain against
    p10 = s1.pooled_rate_summary.loc[s1.pooled_rate_summary["rate_hz"] == 10.0].iloc[0]
    assert p10["gain_passes"] is None or pd.isna(p10["gain_passes"])
    assert "rate in force" in str(p10["sentence"])


def test_the_response_carries_both_fits_and_names_the_default(s1):
    block = BS._pulse_width_pooling_block(s1)
    assert block["default"] == "separate"
    assert block["available"] is True
    assert block["in_force_pairing"] == {"pw_us_left": 60.0, "pw_us_right": 160.0}
    rows = block["rate_strata_pooled"]
    assert [r["rate_hz"] for r in rows] == [10.0, 55.0]
    r55 = next(r for r in rows if r["rate_hz"] == 55.0)
    assert r55["fitted"] and "surface" in r55 and r55["surface"]["mu"]
    assert len(r55["surface"]["points"]) == 12
    assert all("pw_us_left" in p for p in r55["surface"]["points"])
    assert r55["pairings"] == sorted(r55["pairings"], key=lambda p: (p["pw_us_left"], p["pw_us_right"]))
    assert "assumes" in block["note"] and "separate" in block["note"]


def test_pooling_is_skipped_with_a_reason_when_the_pairing_in_force_is_unknown():
    d = _matrix_two_pairings().drop(columns=["pw_us_Right"])
    r = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    # the Right column falls back to the Left one (existing behaviour); pooling still runs
    assert r.audit["pulse_width_pooling"]["computed"] is True
    d2 = _matrix_two_pairings()
    d2.loc[d2["epoch"] == d2["epoch"].max(), "pw_us_Left"] = np.nan
    r2 = S1.run_stage1(d2, data_horizon="test", washin_min=1.0)
    a = r2.audit["pulse_width_pooling"]
    assert a["computed"] is False and "in force" in a["reason"]
    assert BS._pulse_width_pooling_block(r2)["available"] is False
