"""Pooling across pulse widths, decision 189's option A, built behind a toggle (the PI, 2026-09-21:
"we want to pool across pulse widths, so I'll put that toggle into the third decision").

Today each (pulse-width-Left, pulse-width-Right) pairing is its own stratum, and a rate inside it
with fewer than `RATE_STRATUM_MIN_EPOCHS` epochs is not fitted. Option A fits ONE surface per
rate over EVERY pairing, with the two pulse widths as two more inputs to the model, and reads
the (left current, right current) surface at the pairing in force. More epochs per fit, at the
cost of assuming the current-to-pain shape is shared across pairings. Both fits are computed in
one Stage 1 run and reported side by side; the page draws the separate fit unless the reader
toggles to the pooled one. The default stays separate.

Merged here 2026-10-05: test_block_of_time_check_on_pooled_fits.py (each under its own heading below).
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


# Stage 1 runs here without its calibration check (`calibration_check=False`, 2026-10-02): a
# warning that changes no recommendation (decision 233, ruling 6), read by no test in this file,
# and held by `test_stratum_calibration.py`; its leave-one-out refits were most of each fit's time.
@pytest.fixture(scope="module")
def s1():
    return S1.run_stage1(_matrix_two_pairings(), data_horizon="test", washin_min=1.0,
                         calibration_check=False)


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
                        pool_pulse_widths=False, calibration_check=False)
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
    r = S1.run_stage1(d, data_horizon="test", washin_min=1.0, calibration_check=False)
    # the Right column falls back to the Left one (existing behaviour); pooling still runs
    assert r.audit["pulse_width_pooling"]["computed"] is True
    d2 = _matrix_two_pairings()
    d2.loc[d2["epoch"] == d2["epoch"].max(), "pw_us_Left"] = np.nan
    r2 = S1.run_stage1(d2, data_horizon="test", washin_min=1.0, calibration_check=False)
    a = r2.audit["pulse_width_pooling"]
    assert a["computed"] is False and "in force" in a["reason"]
    assert BS._pulse_width_pooling_block(r2)["available"] is False


# ================================================================================================
# From test_block_of_time_check_on_pooled_fits.py (merged here 2026-10-05).
# Decision 253's block-of-time check on the fits POOLED ACROSS PULSE WIDTHS (the PI, 2026-09-25:
# "deal with the Q4 edge cases").
#
# The Stim Optimizer page marks a recommended current with a dagger when the pain map it is read
# from "moves between blocks of time" (decision 253's own label, the PI's answer 4 of 2026-09-25).
# Every per-pairing map carried the check; the maps pooled across pulse widths (decision 222 for the
# REDCap stream, decision 255 for the clinic stream, and the back site's copies of both) were never
# put through it, so a current recommended from one of them could only say "not checked". Here the
# SAME check (`stage1_openloop.stratum_calibration`, with its diagnosis) runs where each pooled map is
# fitted, travels on the fitted object, and is attached where the response rows are built -- the
# lesson of decision 238, where a check was computed and reached no field.
# Its leave-one-epoch-out fold was first left out on the pooled maps for its cost (it refits the map
# once per epoch); since its folds are refitted in worker processes it is computed on them too.
#
# Pinned: the pooled map carries the check and the response row carries it; an unfitted pooled rate
# carries none; the check is off when asked; "the setting delivered most often" on a pooled map is a
# setting, pulse widths included, never two pairings run together under one current pair; and adding
# the check moves no recommendation, verdict or value, pooled or separate.
# ================================================================================================


@pytest.fixture(scope="module")
def s1_checked():
    """The pooling tests' own matrix (`_matrix_two_pairings`) fitted with the calibration check ON;
    `s1` is the same fit with it off."""
    return S1.run_stage1(_matrix_two_pairings(), data_horizon="test", washin_min=1.0)


def test_every_fitted_pooled_map_carries_the_check_and_its_diagnosis(s1_checked):
    fitted = [rs for rs in s1_checked.pooled_rate_strata.values() if rs.fitted]
    assert len(fitted) == 2
    for rs in fitted:
        cal = rs.meta.get("calibration")
        assert cal is not None, f"{rs.rate_hz} Hz pooled map carries no block-of-time check"
        assert cal["blocking"] is False
        d = cal["diagnosis"]
        assert d["verdict"] in ("calibrated", "honest but uninformative: thin data",
                                "moves between blocks of time",
                                "too confident within blocks: the shape or the noise model", None)
        assert d["n_blocks"] == 3


def test_the_response_row_carries_the_check_where_the_rows_are_built(s1_checked):
    """Decision 238's lesson: the rows are built from the summary FRAME, so a check left on the
    fitted object reaches no field unless the serialiser copies it."""
    rows = BS._pulse_width_pooling_block(s1_checked)["rate_strata_pooled"]
    for r in rows:
        assert r["fitted"]
        assert "calibration" in r and r["calibration"]["diagnosis"]["n_blocks"] == 3
        assert r["calibration"] == BS._two_stage_jsonable(s1_checked.pooled_rate_strata[r["rate_hz"]].meta["calibration"])


def test_an_unfitted_pooled_rate_carries_no_check():
    d = _matrix_two_pairings()
    d = d.loc[~((d["freq_hz"] == 10.0) & (d["epoch"] > 3))]         # 10 Hz left with 3 epochs
    r = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    rs10 = r.pooled_rate_strata[10.0]
    assert rs10.fitted is False and "calibration" not in (rs10.meta or {})
    row10 = next(x for x in BS._pulse_width_pooling_block(r)["rate_strata_pooled"] if x["rate_hz"] == 10.0)
    assert "calibration" not in row10


def test_the_check_is_off_when_the_run_asks_for_it_off(s1):
    for rs in s1.pooled_rate_strata.values():
        assert "calibration" not in (rs.meta or {})
    assert all("calibration" not in r
               for r in BS._pulse_width_pooling_block(s1)["rate_strata_pooled"])


def test_the_setting_delivered_most_often_on_a_pooled_map_is_a_whole_setting():
    """On a map pooled across pulse widths one current pair can be delivered at two pairings; those
    are two settings, and "pain at the setting delivered most often" must not run them together.
    Six epochs at 2.0/2.5 mA split 3 + 3 over two pairings lose to four at 1.0/1.0 mA on one."""
    n = 10
    amps = [(2.0, 2.5)] * 6 + [(1.0, 1.0)] * 4
    pwl = [60.0, 100.0] * 3 + [60.0] * 4
    sub = pd.DataFrame(dict(t0=pd.date_range("2026-01-01", periods=n, freq="7D", tz="UTC"),
                            amp_mA_Left=[a for a, _ in amps], amp_mA_Right=[b for _, b in amps],
                            pw_us_Left=pwl, pw_us_Right=160.0, J=np.zeros(n), obs_var=np.ones(n),
                            n=5.0))
    blocks = S1._fold_labels_by_time(sub)
    whole = S1._reference_setting(sub, blocks, setting_cols=("amp_mA_Left", "amp_mA_Right",
                                                             "pw_us_Left", "pw_us_Right"))
    assert whole["setting"] == {"amp_mA_Left": 1.0, "amp_mA_Right": 1.0,
                                "pw_us_Left": 60.0, "pw_us_Right": 160.0}
    assert whole["n_epochs"] == 4
    # the per-pairing maps keep the two-current key, and their answer is unchanged by the option
    assert S1._reference_setting(sub, blocks) == S1._reference_setting(
        sub, blocks, setting_cols=("amp_mA_Left", "amp_mA_Right"))
    assert S1._reference_setting(sub, blocks)["setting"] == {"amp_mA_Left": 2.0, "amp_mA_Right": 2.5}


def test_the_pooled_maps_check_names_the_pulse_widths_of_its_reference_setting(s1_checked):
    ref = s1_checked.pooled_rate_strata[55.0].meta["calibration"]["diagnosis"]["reference_setting"]
    assert set(ref["setting"]) == {"amp_mA_Left", "amp_mA_Right", "pw_us_Left", "pw_us_Right"}


def test_adding_the_check_moves_no_recommendation_verdict_or_value(s1_checked, s1):
    """A warning only (the PI, 2026-09-22, ruling 6): with the check on, every pooled and separate
    row, the frozen configuration and the per-pairing strata are value-for-value what they are
    with it off; the only difference is the added `calibration` block."""
    pd.testing.assert_frame_equal(s1_checked.pooled_rate_summary, s1.pooled_rate_summary)
    pd.testing.assert_frame_equal(s1_checked.rate_summary, s1.rate_summary)
    pd.testing.assert_frame_equal(s1_checked.summary, s1.summary)
    assert s1_checked.frozen.describe() == s1.frozen.describe()
    on = BS._pulse_width_pooling_block(s1_checked)["rate_strata_pooled"]
    off = BS._pulse_width_pooling_block(s1)["rate_strata_pooled"]
    for a, b in zip(on, off):
        a = {k: v for k, v in a.items() if k != "calibration"}
        assert a == b


def test_the_per_pairing_maps_check_is_unchanged_by_the_pooled_one(s1_checked):
    on = s1_checked                                   # the same fit, with pooling and the check on
    off = S1.run_stage1(_matrix_two_pairings(), data_horizon="test", washin_min=1.0,
                        pool_pulse_widths=False)
    for key, sl in on.slices.items():
        for rate, rs in (sl.rate_strata or {}).items():
            if rs.fitted:
                assert rs.meta["calibration"] == off.slices[key].rate_strata[rate].meta["calibration"]


def test_the_pooled_map_carries_the_whole_check_its_epoch_fold_included(s1_checked):
    """The leave-one-epoch-out fold was left out on the pooled maps for its cost (it refits the map
    once per epoch); since its folds are refitted in worker processes, bit for bit the serial
    answer (`tests/test_loo_parallel_folds.py`), it costs under a second on RCS08's largest pooled
    map and is computed like every per-pairing map's: nothing is named as not computed, and every
    epoch is predicted by the maps fitted without it."""
    for rs in s1_checked.pooled_rate_strata.values():
        if not rs.fitted:
            continue
        cal = rs.meta["calibration"]
        assert "not_computed" not in cal
        assert not hasattr(S1, "EPOCH_FOLD_SKIPPED_REASON")
        loeo = cal["summary"]["loeo"]
        assert loeo["n_folds"] == rs.n_epochs
        assert loeo["n_predicted"] == rs.n_epochs and loeo["reason"] is None
        assert loeo["coverage95"] is not None and loeo["mae_ratio"] is not None
        assert cal["checks"]["C1_loeo_skill"] == bool(loeo["mae_ratio"] <= 0.90)
        assert cal["summary"]["loera"]["n_predicted"] > 0
        assert cal["summary"]["loera"]["coverage95"] == cal["diagnosis"]["coverage95"]
    # the per-pairing maps keep the whole check
    for sl in s1_checked.slices.values():
        for rs in (sl.rate_strata or {}).values():
            if rs.fitted:
                assert "not_computed" not in rs.meta["calibration"]
                assert rs.meta["calibration"]["summary"]["loeo"]["n_predicted"] > 0
