"""Review of 2026-09-12, findings S5, S6, S7, S9, S10, S11 and S12, each pinned on the VALUE it
produces: the stopping rule's label with no history, the queue's adaptive-capable marker, the
setting in force read from an unrated newest epoch, the stream's rate-agreement audit, the
objective's refusal of an unrated incumbent, the response key naming the two override names and
the band range, and the adapter's double-spelled imports.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import adapter as AD
from StimOptimizer import bravo_service as BS
from StimOptimizer import pipeline as PL
from StimOptimizer.routines import acquisition as ACQ
from StimOptimizer.routines import adaptive_envelope as ENV
from StimOptimizer.routines import objective as OBJ
from StimOptimizer.routines import plots as PLT


# ---------------------------------------------------------------------------------------------
# S5: the stopping rule with no batch history
# ---------------------------------------------------------------------------------------------
def _grid_state():
    mu = np.array([0.5, -0.2, 0.1, 0.3])
    sd = np.array([0.1, 0.3, 0.2, 0.1])
    n_rep = np.array([5, 0, 1, 6])
    return mu, sd, n_rep


def test_no_batch_history_is_labelled_not_assessable_never_plateau():
    mu, sd, n_rep = _grid_state()
    d = ACQ.check_stopping([], mu, sd, n_rep, incumbent_mu=0.0)
    assert d.binding == "not assessable: no batch history"
    assert d.plateau_met is None
    assert d.stop is False and d.truncated is False and d.n_batches == 0
    assert "not assessable: no batch history" in d.describe()
    # with everything explored the label is still about the missing history, not "plateau"
    d2 = ACQ.check_stopping([], mu, sd, np.array([5, 5, 5, 5]), incumbent_mu=0.0)
    assert d2.coverage_met is True and d2.binding == "not assessable: no batch history"


def test_a_real_history_still_reads_plateau_or_coverage():
    mu, sd, n_rep = _grid_state()
    d = ACQ.check_stopping([5.0, 3.0, 1.0, -1.0], mu, sd, n_rep, incumbent_mu=0.0)
    assert d.binding == "coverage" and d.plateau_met is False


def test_the_flat_pipeline_and_stage_1_hand_the_rule_no_history():
    """The summary rows now carry the not-assessable label in `stop_binding`."""
    d = _design()
    rep = PL.run(d, hemispheres=("Left",), sites=("left_leg",), outdir=None, render_figures=False,
                 data_horizon="t", washin_min=1.0)
    assert list(rep.summary["stop_binding"]) == ["not assessable: no batch history"]
    assert list(rep.summary["stop"]) == [False]
    from StimOptimizer import stage1_openloop as S1
    s1 = S1.run_stage1(d, hemispheres=("Left",), data_horizon="t", washin_min=1.0)
    assert set(s1.summary["stop_binding"]) == {"not assessable: no batch history"}


# ---------------------------------------------------------------------------------------------
# S6: the queue and the batches say which cells closed loop cannot use
# ---------------------------------------------------------------------------------------------
def _design(n=12, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for ep in range(1, n + 1):
        rows.append(dict(epoch=float(ep), freq_hz=float([55.0, 110.0, 10.0][ep % 3]),
                         pw_us_Left=60.0, pw_us_Right=150.0,
                         amp_mA_Left=float(1.0 + 0.3 * (ep % 4)),
                         amp_mA_Right=float(1.2 + 0.3 * (ep % 3)),
                         n=8.0, dur_h=200.0,
                         left_leg_vas=float(50.0 + 3.0 * rng.standard_normal()),
                         left_leg_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


def test_queue_rows_below_the_adaptive_minimum_are_marked_and_the_others_are_not():
    ctx = PLT.build_context(_design(), hemisphere="Left", primary_item="left_leg",
                            data_horizon="t", washin_min=1.0)
    q = PL._queue_frame(ctx, top=25)
    assert "adaptive_capable" in q.columns
    for _, r in q.iterrows():
        assert bool(r["adaptive_capable"]) is bool(float(r["freq_hz"]) >= ENV.MIN_RATE_HZ)
    assert ENV.MIN_RATE_HZ == 55.0
    below = q[q["freq_hz"] < 55.0]
    assert len(below) and not below["adaptive_capable"].any()
    b = PL._batch_frame(ctx)
    for _, r in b.iterrows():
        assert bool(r["adaptive_capable"]) is bool(float(r["freq_hz"]) >= ENV.MIN_RATE_HZ)


def test_the_marker_adds_a_column_and_changes_no_existing_queue_value():
    ctx = PLT.build_context(_design(), hemisphere="Left", primary_item="left_leg",
                            data_horizon="t", washin_min=1.0)
    q = PL._queue_frame(ctx, top=25)
    without = q.drop(columns=["adaptive_capable"])
    gx = ctx.gx
    idx = ctx.queue[:25]
    np.testing.assert_array_equal(without["freq_hz"].to_numpy(), gx[idx, 0])
    np.testing.assert_array_equal(without["amp_mA"].to_numpy(), gx[idx, 1])
    np.testing.assert_array_equal(without["posterior_mean"].to_numpy(), ctx.mu[idx])


# ---------------------------------------------------------------------------------------------
# S7: the setting in force is the newest DEVICE setting, rated or not
# ---------------------------------------------------------------------------------------------
def _stream_with_an_unrated_newest_epoch():
    t = pd.to_datetime(["2026-01-01", "2026-01-01", "2026-02-01", "2026-02-01",
                        "2026-03-01", "2026-03-01"], utc=True)
    return pd.DataFrame(dict(
        t=t, src="history",
        hemi=["Left", "Right"] * 3,
        amp=[2.0, 2.5, 3.0, 2.5, 3.5, 2.5],
        pw=[100.0, 150.0, 100.0, 150.0, 100.0, 160.0],
        rate=[55.0] * 6, upper=[np.nan] * 6,
        cathode=["2a-2b-2c", "1a-1b-1c"] * 3, schema=["sensing"] * 6))


def test_in_force_names_the_unrated_newest_epoch_and_says_the_fit_uses_the_older_one():
    ep = AD.exposure_epochs(_stream_with_an_unrated_newest_epoch())
    assert list(ep["epoch"]) == [1.0, 2.0, 3.0]
    # the matched table holds ratings for epochs 1 and 2 only
    es = ep[ep["epoch"] <= 2.0].copy()
    es["t0"] = es["t_start"]
    inf = BS.in_force_by_side(es, epochs=ep)
    assert inf["Right"]["epoch"] == 3.0 and inf["Right"]["pulse_width_us"] == 160.0
    assert inf["Left"]["epoch"] == 3.0 and inf["Left"]["amplitude_mA"] == 3.5
    assert inf["Right"]["has_ratings_yet"] is False
    assert inf["Right"]["fitted_incumbent_epoch"] == 2.0
    assert inf["Right"]["differs_from_fitted_incumbent"] is True
    assert "epoch 3 since" in inf["Right"]["note"] and "against epoch 2" in inf["Right"]["note"]
    assert inf["Left"]["source"].startswith("full settings history")


def test_in_force_agrees_when_the_newest_epoch_is_rated():
    ep = AD.exposure_epochs(_stream_with_an_unrated_newest_epoch())
    es = ep.copy()
    es["t0"] = es["t_start"]
    inf = BS.in_force_by_side(es, epochs=ep)
    assert inf["Right"]["has_ratings_yet"] is True
    assert inf["Right"]["differs_from_fitted_incumbent"] is False and inf["Right"]["note"] is None


def test_in_force_without_the_full_table_reads_the_matched_table_as_before():
    ep = AD.exposure_epochs(_stream_with_an_unrated_newest_epoch())
    es = ep[ep["epoch"] <= 2.0].copy()
    es["t0"] = es["t_start"]
    inf = BS.in_force_by_side(es)
    assert inf["Right"]["epoch"] == 2.0 and inf["Right"]["pulse_width_us"] == 150.0
    assert inf["Right"]["source"].startswith("matched table")


# ---------------------------------------------------------------------------------------------
# S9: the epochs open on the Left rate, and the stream's audit checks the two sides agree
# ---------------------------------------------------------------------------------------------
def test_the_epoch_table_reports_whether_the_two_sides_rates_agree():
    ep = AD.exposure_epochs(_stream_with_an_unrated_newest_epoch())
    assert ep.attrs["n_timestamps_rates_differ"] == 0
    assert ep.attrs["rates_agree_across_sides"] is True
    s = _stream_with_an_unrated_newest_epoch()
    s.loc[(s["hemi"] == "Right") & (s["t"] == s["t"].max()), "rate"] = 110.0
    ep2 = AD.exposure_epochs(s)
    assert ep2.attrs["n_timestamps_rates_differ"] == 1
    assert ep2.attrs["rates_agree_across_sides"] is False
    assert list(ep2["freq_hz"]) == [55.0, 55.0, 55.0]        # still the Left's, and said so


# ---------------------------------------------------------------------------------------------
# S10: an incumbent with no rating on the item is refused by name
# ---------------------------------------------------------------------------------------------
def test_an_unrated_incumbent_raises_with_the_item_named_and_the_arm_records_it():
    d = _design()
    d.loc[d["epoch"] == d["epoch"].max(), "left_leg_vas"] = np.nan
    inc = float(d["epoch"].max())
    with pytest.raises(ValueError, match="carries no left_leg_vas rating"):
        OBJ.build_objective(d, incumbent_epoch=inc, cfg={"primary_item": "left_leg"})
    rep = PL.run(d, hemispheres=("Left",), sites=("left_leg",), outdir=None,
                 render_figures=False, data_horizon="t", washin_min=1.0)
    assert "left_leg__Left" in rep.manifest["skipped"]
    assert "carries no left_leg_vas rating" in rep.manifest["skipped"]["left_leg__Left"]
    assert "too few to fit a surface" not in rep.manifest["skipped"]["left_leg__Left"]


# ---------------------------------------------------------------------------------------------
# S11: the response key names the override names and the band range; ClosedLoop is in the tail
# ---------------------------------------------------------------------------------------------
def test_the_two_override_names_are_in_the_response_key_and_not_in_the_tables_key():
    args = ("u", "m", "t", "a", "g")
    tail = (("left_leg",), ("Left",), 1.0, "none")
    base = {"TwoStage": True, "TwoStageOverrideReason": "r", "TwoStageExploreOutsideAdaptive": "x"}
    a = BS._response_signature(*args, base, *tail)
    b = BS._response_signature(*args, dict(base, TwoStageOverrideBy="Dr A"), *tail)
    c = BS._response_signature(*args, dict(base, TwoStageExploreOutsideAdaptiveBy="Dr B"), *tail)
    assert len({a, b, c}) == 3
    assert BS._products_signature(a) == BS._products_signature(b) == BS._products_signature(c)


def test_the_closed_loop_flag_is_in_the_tail_so_the_tables_key_ignores_it():
    args = ("u", "m", "t", "a", "g")
    tail = (("left_leg",), ("Left",), 1.0, "none")
    on = BS._response_signature(*args, {"ClosedLoop": True}, *tail)
    off = BS._response_signature(*args, {"ClosedLoop": False}, *tail)
    assert on != off
    assert BS._products_signature(on) == BS._products_signature(off)


def test_the_band_range_is_a_key_element_read_from_the_biomarkers_constants(monkeypatch):
    args = ("u", "m", "t", "a", "g")
    tail = (("left_leg",), ("Left",), 1.0, "none")
    k1 = BS._response_signature(*args, {}, *tail)
    monkeypatch.setattr(AD, "deployable_band_span", lambda: (7.8, 40.0))
    k2 = BS._response_signature(*args, {}, *tail)
    assert k1 != k2
    assert (7.8, 40.0) in k2
    assert BS._products_signature(k1) == BS._products_signature(k2)


# ---------------------------------------------------------------------------------------------
# S12: the band span raises rather than widening the evidence when it cannot be read
# ---------------------------------------------------------------------------------------------
def test_the_band_span_is_read_from_both_spellings_and_raises_rather_than_returning_none():
    lo, hi = AD.deployable_band_span()
    assert (lo, hi) == (7.8, 30.0)
    import inspect
    src = inspect.getsource(AD)
    assert "from Biomarkers.routines import analytics as _an" in src
    assert src.count("from Biomarkers import bravo_service as _bs") == 2
    assert "return None" not in inspect.getsource(AD._deployable_band_span)
