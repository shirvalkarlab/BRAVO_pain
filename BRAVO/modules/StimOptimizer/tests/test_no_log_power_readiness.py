"""Decision 202 (the PI, 2026-09-19): log power is used in no calculation. The Stim Optimizer's
readiness screen -- "falls with current once the time confound is removed", the current half of
decision 199's one-band rule -- fitted its era-blocked slope on np.log(power). It now fits raw device
power, and the slope is in device units per mA, the units the device thresholds in.
"""
import inspect
import numpy as np
import pytest

from StimOptimizer.routines import lfp_response as LR
from StimOptimizer.routines import lfp_evidence as LE
from StimOptimizer.routines import stage_gate as SG


def _linear_fixture(slope_per_mA=-20.0, n_per=24, noise=4.0, seed=0):
    """Two capture arms whose band power is a STRAIGHT LINE in current, in device units, with era
    crossed with current so blocking leaves the effect identifiable."""
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.5, 3.5], n_per)
    p = 200.0 + slope_per_mA * (amp - 1.5) + rng.normal(0, noise, amp.size)
    era = np.tile(np.arange(3), int(np.ceil(amp.size / 3)))[: amp.size]
    clus = np.arange(amp.size) // 4
    return p, amp, era, clus


def test_the_era_blocked_slope_is_in_device_units_per_mA_not_log_units():
    p, a, era, cl = _linear_fixture(slope_per_mA=-20.0)
    r = LR.assess_response(p, a, era=era, cluster=cl, mode_requires="suppression")
    assert r.responds is True
    # A slope of -20 device units per mA. On log power the same data give about -0.11 per mA,
    # so this bound separates the two beyond any doubt.
    assert -26.0 < r.slope_per_mA < -14.0, r.slope_per_mA
    assert r.slope_p < 0.05
    assert r.slope_ci[0] < r.slope_per_mA < r.slope_ci[1]
    assert "device units per mA" in r.describe()


def test_the_result_carries_no_log_field_at_all():
    p, a, era, cl = _linear_fixture()
    r = LR.assess_response(p, a, era=era, cluster=cl)
    for name in ("slope_log_per_mA", "separation_d_on_log"):
        assert not hasattr(r, name), name
    assert "logarithm" not in r.describe()


def test_the_readiness_source_takes_no_logarithm_of_power():
    src = inspect.getsource(LR)
    for token in ("np.log(", "np.log10(", "np.log1p(", "math.log("):
        assert token not in src, token


def test_the_serialised_band_row_and_the_one_band_rule_read_the_device_unit_slope():
    p, a, era, cl = _linear_fixture(slope_per_mA=-20.0)
    r = LR.assess_response(p, a, era=era, cluster=cl)
    row = SG.verdict_row(24.5, r)
    assert "slope_per_mA" in row and row["slope_per_mA"] == pytest.approx(r.slope_per_mA)
    assert "slope_log_per_mA" not in row and "separation_d_on_log" not in row
    assert LE.band_era_negative_significant(r) is True
    rising, *_ = _linear_fixture(slope_per_mA=+20.0)
    r2 = LR.assess_response(rising, a, era=era, cluster=cl)
    assert LE.band_era_negative_significant(r2) is False
