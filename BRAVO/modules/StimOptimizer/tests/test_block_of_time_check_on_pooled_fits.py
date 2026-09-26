"""Decision 253's block-of-time check on the fits POOLED ACROSS PULSE WIDTHS (the PI, 2026-09-25:
"deal with the Q4 edge cases").

The Stim Optimizer page marks a recommended current with a dagger when the pain map it is read
from "moves between blocks of time" (decision 253's own label, the PI's answer 4 of 2026-09-25).
Every per-pairing map carried the check; the maps pooled across pulse widths (decision 222 for the
REDCap stream, decision 255 for the clinic stream, and the back site's copies of both) were never
put through it, so a current recommended from one of them could only say "not checked". Here the
SAME check (`stage1_openloop.stratum_calibration`, with its diagnosis) runs where each pooled map is
fitted, travels on the fitted object, and is attached where the response rows are built -- the
lesson of decision 238, where a check was computed and reached no field.
Its leave-one-epoch-out fold was first left out on the pooled maps for its cost (it refits the map
once per epoch); since its folds are refitted in worker processes it is computed on them too.

Pinned: the pooled map carries the check and the response row carries it; an unfitted pooled rate
carries none; the check is off when asked; "the setting delivered most often" on a pooled map is a
setting, pulse widths included, never two pairings run together under one current pair; and adding
the check moves no recommendation, verdict or value, pooled or separate.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import bravo_service as BS
from StimOptimizer import stage1_openloop as S1


def _matrix_two_pairings():
    """The pooling tests' own matrix: 55 Hz at two pulse-width pairings (5 and 7 epochs, each below
    the per-rate floor alone, 12 together) and 10 Hz at one (9 epochs)."""
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


@pytest.fixture(scope="module")
def s1_unchecked():
    return S1.run_stage1(_matrix_two_pairings(), data_horizon="test", washin_min=1.0,
                         calibration_check=False)


def test_every_fitted_pooled_map_carries_the_check_and_its_diagnosis(s1):
    fitted = [rs for rs in s1.pooled_rate_strata.values() if rs.fitted]
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


def test_the_response_row_carries_the_check_where_the_rows_are_built(s1):
    """Decision 238's lesson: the rows are built from the summary FRAME, so a check left on the
    fitted object reaches no field unless the serialiser copies it."""
    rows = BS._pulse_width_pooling_block(s1)["rate_strata_pooled"]
    for r in rows:
        assert r["fitted"]
        assert "calibration" in r and r["calibration"]["diagnosis"]["n_blocks"] == 3
        assert r["calibration"] == BS._two_stage_jsonable(s1.pooled_rate_strata[r["rate_hz"]].meta["calibration"])


def test_an_unfitted_pooled_rate_carries_no_check():
    d = _matrix_two_pairings()
    d = d.loc[~((d["freq_hz"] == 10.0) & (d["epoch"] > 3))]         # 10 Hz left with 3 epochs
    r = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    rs10 = r.pooled_rate_strata[10.0]
    assert rs10.fitted is False and "calibration" not in (rs10.meta or {})
    row10 = next(x for x in BS._pulse_width_pooling_block(r)["rate_strata_pooled"] if x["rate_hz"] == 10.0)
    assert "calibration" not in row10


def test_the_check_is_off_when_the_run_asks_for_it_off(s1_unchecked):
    for rs in s1_unchecked.pooled_rate_strata.values():
        assert "calibration" not in (rs.meta or {})
    assert all("calibration" not in r
               for r in BS._pulse_width_pooling_block(s1_unchecked)["rate_strata_pooled"])


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


def test_the_pooled_maps_check_names_the_pulse_widths_of_its_reference_setting(s1):
    ref = s1.pooled_rate_strata[55.0].meta["calibration"]["diagnosis"]["reference_setting"]
    assert set(ref["setting"]) == {"amp_mA_Left", "amp_mA_Right", "pw_us_Left", "pw_us_Right"}


def test_adding_the_check_moves_no_recommendation_verdict_or_value(s1, s1_unchecked):
    """A warning only (the PI, 2026-09-22, ruling 6): with the check on, every pooled and separate
    row, the frozen configuration and the per-pairing strata are value-for-value what they are
    with it off; the only difference is the added `calibration` block."""
    pd.testing.assert_frame_equal(s1.pooled_rate_summary, s1_unchecked.pooled_rate_summary)
    pd.testing.assert_frame_equal(s1.rate_summary, s1_unchecked.rate_summary)
    pd.testing.assert_frame_equal(s1.summary, s1_unchecked.summary)
    assert s1.frozen.describe() == s1_unchecked.frozen.describe()
    on = BS._pulse_width_pooling_block(s1)["rate_strata_pooled"]
    off = BS._pulse_width_pooling_block(s1_unchecked)["rate_strata_pooled"]
    for a, b in zip(on, off):
        a = {k: v for k, v in a.items() if k != "calibration"}
        assert a == b


def test_the_per_pairing_maps_check_is_unchanged_by_the_pooled_one():
    on = S1.run_stage1(_matrix_two_pairings(), data_horizon="test", washin_min=1.0)
    off = S1.run_stage1(_matrix_two_pairings(), data_horizon="test", washin_min=1.0,
                        pool_pulse_widths=False)
    for key, sl in on.slices.items():
        for rate, rs in (sl.rate_strata or {}).items():
            if rs.fitted:
                assert rs.meta["calibration"] == off.slices[key].rate_strata[rate].meta["calibration"]


def test_the_pooled_map_carries_the_whole_check_its_epoch_fold_included(s1):
    """The leave-one-epoch-out fold was left out on the pooled maps for its cost (it refits the map
    once per epoch); since its folds are refitted in worker processes, bit for bit the serial
    answer (`tests/test_loo_parallel_folds.py`), it costs under a second on RCS08's largest pooled
    map and is computed like every per-pairing map's: nothing is named as not computed, and every
    epoch is predicted by the maps fitted without it."""
    for rs in s1.pooled_rate_strata.values():
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
    for sl in s1.slices.values():
        for rs in (sl.rate_strata or {}).values():
            if rs.fitted:
                assert "not_computed" not in rs.meta["calibration"]
                assert rs.meta["calibration"]["summary"]["loeo"]["n_predicted"] > 0
