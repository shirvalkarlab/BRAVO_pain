"""Tests for the (left current, right current) surface `bravo_service.py` attaches to every
FITTED row of `two_stage.stage1.rate_strata`, and the pooled 3-input reference slices it attaches
once per joint stratum (2026-09-14, alongside decision 158's honest-current rule) -- the data the
Stim Optimizer page's new `CurrentMapCard` draws.

Built self-contained, with its own thin-and-fat rate mix at ONE pulse-width pair, rather than
reusing `test_stage1.py`'s `rcs08_like` fixture: that fixture aliases pulse width to rate one-to-
one, so every joint stratum it fits has exactly one rate and never exercises the "some rates in a
stratum fit, some do not" case this file's own second test needs.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import bravo_service as BS
from StimOptimizer import stage1_openloop as S1


def _matrix_two_rates_one_pw():
    """One (pulse-width-Left, pulse-width-Right) pair, two rates inside it: 55 Hz with 12 epochs
    (clears ``RATE_STRATUM_MIN_EPOCHS`` = 8) and 10 Hz with 3 (does not)."""
    rng = np.random.default_rng(0)
    rows = []
    ep = 0
    for rate, n in ((55.0, 12), (10.0, 3)):
        for k in range(n):
            ep += 1
            amp_left = 1.0 + 0.25 * (k % 6)
            amp_right = 1.2 + 0.25 * (k % 5)
            rows.append(dict(
                epoch=float(ep), freq_hz=float(rate), pw_us_Left=100.0, pw_us_Right=150.0,
                amp_mA_Left=float(amp_left), amp_mA_Right=float(amp_right), n=6.0, dur_h=180.0,
                left_leg_vas=float(50.0 + 3.0 * rng.standard_normal()), left_leg_vas_sd=7.5))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


@pytest.fixture(scope="module")
def stage1_two_rates():
    d = _matrix_two_rates_one_pw()
    return S1.run_stage1(d, data_horizon="test", washin_min=1.0)


def _rate_strata_records(s1):
    records = BS._frame_records(s1.rate_summary)
    return BS._attach_rate_stratum_surfaces(records, s1)


def test_a_fitted_rows_surface_matches_the_raw_rate_stratum_value_for_value(stage1_two_rates):
    records = _rate_strata_records(stage1_two_rates)
    fitted = [r for r in records if r["fitted"]]
    assert fitted, "the 55 Hz stratum should have fitted"
    row = fitted[0]
    assert "surface" in row
    surface = row["surface"]

    # The raw object the response was built from.
    key = (round(float(row["pw_us_left"]), 6), round(float(row["pw_us_right"]), 6),
          round(float(row["rate_hz"]), 6))
    rs = BS._rate_stratum_lookup(stage1_two_rates)[key]

    assert len(surface["amps_mA"]) == 21
    assert len(surface["mu"]) == 21
    assert len(surface["mu"][0]) == 21
    assert len(surface["sd"]) == 21
    assert len(surface["safe"]) == 21

    # Every finite cell of the serialised grid equals the raw RateStratum's own surface, to the
    # rounding the response applies (4 decimals) -- never a tolerance beyond that stated rounding.
    raw_mu = np.asarray(rs.mu, float)
    raw_sd = np.asarray(rs.sd, float)
    raw_safe = np.asarray(rs.safe, bool)
    n_compared, n_differing = 0, 0
    for i in range(21):
        for j in range(21):
            n_compared += 1
            expect_mu = None if not np.isfinite(raw_mu[i, j]) else round(float(raw_mu[i, j]), 4)
            expect_sd = None if not np.isfinite(raw_sd[i, j]) else round(float(raw_sd[i, j]), 4)
            if surface["mu"][i][j] != expect_mu:
                n_differing += 1
            if surface["sd"][i][j] != expect_sd:
                n_differing += 1
            if surface["safe"][i][j] != bool(raw_safe[i, j]):
                n_differing += 1
    assert n_compared == 441
    assert n_differing == 0

    # amps_mA is the grid's own amplitude axis (identical for left and right: both sides share
    # stage1_openloop.JOINT_AMP_GRID).
    assert surface["amps_mA"] == [round(float(v), 4) for v in np.asarray(rs.grid.amps_left, float)]
    assert surface["amps_mA"][0] == 0.0
    assert surface["amps_mA"][-1] == pytest.approx(5.0)

    # The observed points are the individual epochs the fit regressed, not a grid cell.
    assert len(surface["points"]) == int(row["n_epochs"]) == 12
    for p in surface["points"]:
        for k in ("amp_left_mA", "amp_right_mA", "n_reports", "J", "epoch"):
            assert k in p


def test_b_an_unfitted_row_carries_no_surface_key(stage1_two_rates):
    records = _rate_strata_records(stage1_two_rates)
    unfitted = [r for r in records if not r["fitted"]]
    assert unfitted, "the 3-epoch 10 Hz stratum should not have fitted"
    row = unfitted[0]
    assert row["rate_hz"] == 10.0
    assert "surface" not in row
    assert row["reason"]


def test_c_pooled_surfaces_carry_every_delivered_rate_once_per_stratum(stage1_two_rates):
    pooled = BS._joint_pooled_surfaces(stage1_two_rates)
    assert len(pooled) == 1
    key = "100_150"
    assert key in pooled
    strat = pooled[key]
    assert strat["pw_us_left"] == 100.0
    assert strat["pw_us_right"] == 150.0
    rates = strat["surface_at_rate"]
    # Both rates the stratum delivered are present, fitted or not -- the pooled surface has an
    # opinion at every rate it was ever asked about, which is exactly why it is reference-only.
    assert set(rates.keys()) == {"55", "10"}
    for rate_key, surf in rates.items():
        assert len(surf["amps_mA"]) == 21
        assert len(surf["mu"]) == 21
        assert len(surf["mu"][0]) == 21
        assert len(surf["safe"]) == 21


def test_d_the_full_two_stage_payload_carries_both_new_fields(stage1_two_rates):
    """`_two_stage_payload` (the function that actually serves the response) attaches `surface` to
    the fitted rate-strata row and a `pooled_surfaces` block, reached through the real code path
    rather than only through the two helpers tested directly above."""
    class _FakeReport:
        pass

    # `_two_stage_payload` needs a `pipeline.TwoStageReport`-shaped object; build the minimum it
    # reads (`.stage1`, `.gate`, `.stage2`, `.manifest`, `.can_deploy_closed_loop()`, `.describe()`)
    # rather than importing the whole gate/Stage 2 machinery, which is exercised by other tests.
    class _FakeGate:
        conditions = []
        passed = False
        headline = "Stage 2 MUST NOT START: 0 of 0 conditions block"   # GateResult.headline, 2026-09-15

        @staticmethod
        def refusals():
            return []

        @staticmethod
        def failed_names():
            return []

        @staticmethod
        def not_assessed_names():
            return []

        @staticmethod
        def describe():
            return ""

    class _FakeStage2:
        started = False
        notes = []
        refusal_reasons = []

        @staticmethod
        def describe():
            return ""

    rep = _FakeReport()
    rep.stage1 = stage1_two_rates
    rep.gate = _FakeGate()
    rep.stage2 = _FakeStage2()
    rep.manifest = {}
    rep.can_deploy_closed_loop = lambda: False
    rep.describe = lambda: ""

    out = BS._two_stage_payload(rep, inputs={}, seconds=0.0)
    rate_strata = out["stage1"]["rate_strata"]
    fitted = [r for r in rate_strata if r["fitted"]]
    assert fitted and "surface" in fitted[0]
    assert "pooled_surfaces" in out["stage1"]
    assert out["stage1"]["pooled_surfaces"]


# ---- the PI, 2026-09-17: absolute numbers on the current map, colour centred on today ----------
def test_e_every_surface_carries_the_pain_rating_at_the_setting_in_force_so_the_page_can_print_absolute_values(stage1_two_rates):
    """`mu` is the score RELATIVE to the setting in force (J = rating - rating at the incumbent +
    side-effect cost). The page adds `pain_reference` back to print the predicted rating in the
    participant's own 0-10 units and centres its colour scale on it; the fit itself is unchanged."""
    s1 = stage1_two_rates
    records = _rate_strata_records(s1)
    fitted = [r for r in records if r["fitted"]]
    surface = fitted[0]["surface"]
    assert "pain_reference" in surface and "pain_item" in surface
    D = s1.D
    item = str(D["primary_item"].iloc[0])
    inc = D.loc[D["epoch"].astype(float) == float(s1.frozen.incumbent_epoch)]
    assert len(inc) == 1
    assert surface["pain_item"] == item
    assert surface["pain_reference"] == float(inc[item].iloc[0])
    # and J_pain is exactly the rating minus that reference on every row
    assert np.allclose(D[item].astype(float) - D["J_pain"].astype(float), surface["pain_reference"])
    # the pooled reference surfaces carry the same number
    pooled = BS._joint_pooled_surfaces(s1)
    for stratum in pooled.values():
        for rate_surface in stratum["surface_at_rate"].values():
            assert rate_surface["pain_reference"] == surface["pain_reference"]
