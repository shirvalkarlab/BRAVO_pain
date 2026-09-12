"""The closed-loop simulation (Phase 8 of the 2026-09-11 redesign; design §6's seven tests, plus
the coefficient pass-through the response curve depends on).

Every test checks VALUES: arrays compared element for element with a difference count, never a
tolerance on a shape.
"""
import math

import numpy as np
import pandas as pd
import pytest

try:
    from modules.ClosedLoopDeployment import simulation as S, replay as R, types as T
    from modules.ClosedLoopDeployment import amplitude_effect as AE
    from modules.StimOptimizer.routines import amplitude_response as AR, within_visit as WV
    from modules.CacheStore import store as st, provenance as prov
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import simulation as S, replay as R, types as T
    from ClosedLoopDeployment import amplitude_effect as AE
    from StimOptimizer.routines import amplitude_response as AR, within_visit as WV
    from CacheStore import store as st, provenance as prov


# --------------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------------
def _plan(upper=120.0, lower=80.0, lo=1.0, hi=3.0):
    return T.ThresholdPlan(upper=upper, lower=lower, scale="linear",
                           capture_amp_low=lo, capture_amp_high=hi)


def _series(n=900, dt=1.2, seed=0, amp_obs=2.0):
    """A uniformly sampled band-power series that visits all three states: a slow random walk
    around 100 device units crossing 80 and 120 repeatedly, recorded at a constant amplitude."""
    rng = np.random.default_rng(seed)
    p = 100.0 + np.cumsum(rng.normal(0, 4.0, n))
    p = 100.0 + 35.0 * np.sin(np.linspace(0, 6 * np.pi, n)) + (p - p.mean()) * 0.3
    t = np.arange(n) * dt
    a = np.full(n, float(amp_obs))
    return t, p, a


def _fields(res, k):
    return {"amp": res["amp"][k], "state": res["state"][k],
            "frac_at_upper": res["frac_at_upper"][k], "frac_at_lower": res["frac_at_lower"][k],
            "longest_up": res["longest_at_upper_s"][k], "longest_lo": res["longest_at_lower_s"][k],
            "n_transitions": res["n_transitions"][k], "mean_amp": res["mean_amp"][k]}


# --------------------------------------------------------------------------------------------
# 1. the zero curve IS the replay
# --------------------------------------------------------------------------------------------
def test_1_zero_curve_reproduces_the_replay_field_for_field():
    t, p, a = _series()
    plan = _plan()
    ref = R.dual_threshold({"t_s": t, "power": p}, plan)
    res = S.simulate_series(t, p, a, plan, [AR.ResponseCurve.zero()], tau_s=30.0)
    got = _fields(res, 0)
    compared = differing = 0
    ref_amp = np.asarray(ref.amplitude_mA)
    compared += ref_amp.size
    differing += int(np.sum(ref_amp != got["amp"]))
    code = {"above": 1, "between": 0, "below": -1}
    ref_state = np.array([code[s] for s in ref.state])
    compared += ref_state.size
    differing += int(np.sum(ref_state != got["state"]))
    for name, rv in (("frac_at_upper", ref.frac_time_at_upper), ("frac_at_lower", ref.frac_time_at_lower),
                     ("longest_up", ref.longest_run_at_upper_s), ("longest_lo", ref.longest_run_at_lower_s),
                     ("n_transitions", ref.n_transitions),
                     ("mean_amp", ref.params["mean_amplitude_mA"])):
        compared += 1
        differing += int(float(rv) != float(got[name]))
    assert ref.n_transitions > 3, "the fixture must exercise the control law"
    assert compared > 1800 and differing == 0, (compared, differing)
    # and the simulated power IS the recorded power, to the last bit
    assert int(np.sum(res["p_sim"][0] != res["p_obs"])) == 0


def test_1b_the_segment_wise_run_matches_the_replay_segment_wise_run():
    t, p, a = _series(n=600)
    # two contiguous stretches separated by a day, like a chronic record of streaming bursts
    t2 = np.concatenate([t, t + 86400.0])
    p2 = np.concatenate([p, p[::-1]])
    a2 = np.concatenate([a, a])
    plan = _plan()
    ref = R.dual_threshold_segments(t2, p2, plan)
    res = S.simulate_segments(t2, p2, a2, plan, [AR.ResponseCurve.zero()], tau_s=30.0)
    assert res["refused"] is False and res["n_segments_used"] == 2 == ref.params["n_segments_used"]
    assert float(res["frac_at_upper"][0]) == float(ref.frac_time_at_upper)
    assert float(res["frac_at_lower"][0]) == float(ref.frac_time_at_lower)
    assert int(res["n_transitions"][0]) == int(ref.n_transitions)
    assert float(res["longest_at_upper_s"][0]) == float(ref.longest_run_at_upper_s)


# --------------------------------------------------------------------------------------------
# 2 and 3. the sign of the response
# --------------------------------------------------------------------------------------------
def test_2_a_negative_slope_retreats_from_the_upper_limit_no_later_than_the_replay():
    t, p, a = _series()
    plan = _plan()
    curves = [AR.ResponseCurve.zero(), AR.ResponseCurve.linear(-40.0)]
    res = S.simulate_series(t, p, a, plan, curves, tau_s=10.0)
    assert res["frac_at_upper"][1] <= res["frac_at_upper"][0]
    assert res["longest_at_upper_s"][1] <= res["longest_at_upper_s"][0]
    # and the loop actually moved the power: the simulated series differs from the recording
    assert int(np.sum(res["p_sim"][1] != res["p_obs"])) > 0
    assert float(res["frac_wrong_side"][1]) == 0.0


def test_3_a_positive_slope_is_positive_feedback_and_pins_at_a_limit():
    t, p, a = _series()
    plan = _plan()
    res = S.simulate_series(t, p, a, plan, [AR.ResponseCurve.zero(), AR.ResponseCurve.linear(+60.0)],
                            tau_s=5.0)
    assert bool(res["saturated"][1]) is True
    assert res["frac_at_upper"][1] > res["frac_at_upper"][0]
    assert float(res["frac_wrong_side"][1]) == 1.0, "every step sits where power rises with current"
    c = AR.ResponseCurve.linear(+60.0)
    assert c.positive_feedback_range(1.0, 3.0) == (1.0, 3.0)


# --------------------------------------------------------------------------------------------
# 4. the peaked curve
# --------------------------------------------------------------------------------------------
def _peaked_row(a=-30.0, peak=2.0, post=-25.0):
    b = -2.0 * a * peak
    return {"pooled_direction": "band power falls as current rises", "pooled_slope_per_mA": -20.0,
            "pooled_slope_stderr": 4.0, "pooled_slope_p": 0.001, "n": 20, "n_visits": 4,
            "verdict": "rises then falls, peaking at 2.00 mA", "curves": True, "peaks_inside": True,
            "peak_mA": peak, "p_curvature": 0.004, "r2_linear": 0.4, "r2_quadratic": 0.8,
            "quad_coef_per_mA2": a, "quad_lin_coef_per_mA": b, "quad_coef_stderr": 5.0,
            "post_peak_slope_per_mA": post, "post_peak_intercept": 0.0, "post_peak_n_points": 8}


def test_4_m2_reports_the_wrong_side_time_and_the_flip_at_the_peak():
    c = AR.ResponseCurve.from_pooled_row(_peaked_row())
    assert c.kind == AR.QUADRATIC and c.peak_mA == 2.0
    lo, hi = c.positive_feedback_range(1.0, 3.0)
    assert lo == 1.0 and abs(hi - 2.0) < 0.011, (lo, hi)
    # the curve is unbroken at the peak and falls past it along the post-peak line
    gp = c.g(2.0)
    assert abs(float(c.g(2.0 + 1e-9)) - float(gp)) < 1e-6
    assert float(c.g(2.5)) == pytest.approx(float(gp) + (-25.0) * 0.5)
    t, p, a = _series()
    out = S.run_models(t, p, a, _plan(), _peaked_row(), n_resample=0)
    assert out["active_model"] == "M2" and out["models"]["M2"] is not None
    assert out["wrong_side"]["range_mA"][0] == 1.0 and abs(out["wrong_side"]["range_mA"][1] - 2.0) < 0.011
    assert out["models"]["M2"]["frac_time_wrong_side"] > 0.0
    assert out["wrong_side"]["gates_nothing"] is True and out["wrong_side"]["warning"]


def test_4b_without_an_established_bend_m2_is_absent_and_m1_is_active():
    row = dict(_peaked_row(), curves=False, peaks_inside=False, p_curvature=0.4)
    t, p, a = _series()
    out = S.run_models(t, p, a, _plan(), row, n_resample=0)
    assert out["active_model"] == "M1" and out["curves"]["M2"] is None
    assert "not assessable" in out["m2_absent_reason"]


# --------------------------------------------------------------------------------------------
# 5. resampling runs, never points
# --------------------------------------------------------------------------------------------
def test_5_resampling_draws_runs_with_equal_weight_whatever_their_point_count(monkeypatch):
    seen = []

    def _fake_fit(x, y, v, **kw):
        seen.append(set(str(s).split("#")[0] for s in v))
        return {"pooled_slope_per_mA": -1.0, "pooled_slope_stderr": 0.1, "pooled_slope_p": 0.01,
                "n": int(x.size), "n_visits": len(set(v)), "curves": False, "peaks_inside": False,
                "peak_mA": float("nan"), "p_curvature": 0.5, "verdict": "ok"}
    # patch the exact module object the function uses (`S._wv`), not a spelling of its name: the
    # two import spellings are two module objects on the container runner
    monkeypatch.setattr(S._wv, "amplitude_response_shape_pooled", _fake_fit)
    x = np.concatenate([np.linspace(1, 3, 6), [1.0, 3.0], np.linspace(1, 3, 3)])
    y = -x + 10
    lab = ["A"] * 6 + ["B"] * 2 + ["C"] * 3
    rs = S.resampled_curves(x, y, lab, n_resample=600, seed=1)
    assert rs["n_fitted"] == 600 and len(seen) == 600
    fa = np.mean([("A" in s) for s in seen]); fb = np.mean([("B" in s) for s in seen])
    # each run is included with probability 1 - (2/3)^3 = 0.704, independent of its point count
    assert abs(fa - fb) < 0.08 and abs(fa - 0.704) < 0.08, (fa, fb)


def test_5b_fewer_than_three_runs_gives_no_interval_and_says_why():
    rs = S.resampled_curves([1, 2, 3, 1, 2], [3, 2, 1, 3, 2], ["A"] * 3 + ["B"] * 2, n_resample=10)
    assert rs["curves"] == [] and "at least 3" in rs["reason"]


# --------------------------------------------------------------------------------------------
# 6. a stored simulation is refused to Stim Optimizer
# --------------------------------------------------------------------------------------------
def test_6_the_stored_kind_cites_only_raw_roots_and_is_refused_where_a_ladder_is_in_its_chain(tmp_path):
    """The refusal (decision 31) fires when a product's chain contains the CONSUMER's own output.
    The simulation, like the pooled table it reads, cites its raw roots (the tiles), so every
    module may read it -- including closed_loop, which could not read a chain naming its own
    pooled table. The control: a chain that names Stim Optimizer's exploration ladder IS refused
    to Stim Optimizer, which is the loop the rule exists for."""
    try:
        from modules.CacheStore import ledger as _ledger
    except ImportError:                                          # pragma: no cover
        from CacheStore import ledger as _ledger
    uid = "p-sim"
    prev = st.DIR_OVERRIDE, _ledger.ENABLED
    st.DIR_OVERRIDE, _ledger.ENABLED = str(tmp_path), False
    st.clear()
    try:
        tiles_sig = ("tiles", 1)
        st.store("raw_lsb_tiles", uid, tiles_sig, {"tiles": np.zeros((2, 2))}, writer="biomarkers")
        tiles_key = st.product_key("raw_lsb_tiles", uid, tiles_sig)
        pooled_sig = ("pooled", 1)
        st.store(AE.POOLED_KIND, uid, pooled_sig, pd.DataFrame({"a": [1]}), writer="closed_loop",
                 trigger="deployment_report",
                 provenance=prov.flatten([prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")]))
        # the simulation cites what the pooled table cites: its flattened chain, i.e. the tiles
        pooled_chain = st.read_stamp(AE.POOLED_KIND, uid, pooled_sig)["provenance"]
        assert [c["kind"] for c in pooled_chain] == ["raw_lsb_tiles"]
        sig = (S.KIND, S.RULE_VERSION, "x")
        st.store(S.KIND, uid, sig, {"models": {}}, writer="closed_loop", trigger="deployment_report",
                 provenance=prov.flatten([prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")]
                                         + list(pooled_chain)))
        assert st.load(S.KIND, uid, sig, consumer="closed_loop") == {"models": {}}
        assert st.load(S.KIND, uid, sig, consumer="stim_optimizer") == {"models": {}}
        assert st.read_stamp(S.KIND, uid, sig)["writer"] == "closed_loop"
        assert prov.module_of(S.KIND) == "closed_loop"
        # the control: a simulation whose chain names the exploration ladder is refused to
        # Stim Optimizer, because a simulation built on recordings its own policy chose must not
        # feed that policy
        ladder_sig = ("ladder", 1)
        st.store("exploration_ladder", uid, ladder_sig, {"rank": [1]}, writer="stim_optimizer",
                 trigger="x", provenance=[])
        sig2 = (S.KIND, S.RULE_VERSION, "y")
        st.store(S.KIND, uid, sig2, {"models": {}}, writer="closed_loop", trigger="deployment_report",
                 provenance=prov.flatten([
                     prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers"),
                     prov.entry(st.product_key("exploration_ladder", uid, ladder_sig),
                                kind="exploration_ladder", writer="stim_optimizer")]))
        with pytest.raises(prov.SelfDerivedProduct):
            st.load(S.KIND, uid, sig2, consumer="stim_optimizer")
        assert st.load(S.KIND, uid, sig2, consumer="closed_loop") == {"models": {}}
    finally:
        # Clear while the override still points at the temporary directory. Clearing AFTER
        # restoring it would clear whatever the store resolves without an override -- on the
        # container that is the production root, the exact wipe decision 116 records.
        st.clear()
        st.DIR_OVERRIDE, _ledger.ENABLED = prev


# --------------------------------------------------------------------------------------------
# 7. the caveat travels and nothing reads like a verdict
# --------------------------------------------------------------------------------------------
def _keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}"
            yield from _keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v, path)


def test_7_every_payload_carries_the_caveat_and_no_field_named_like_a_verdict():
    t, p, a = _series()
    row = dict(_peaked_row(), curves=False, peaks_inside=False)
    x = np.concatenate([np.linspace(1, 3, 5)] * 4); y = 10 - 2 * x
    lab = sum([[r] * 5 for r in "ABCD"], [])
    out = S.run_models(t, p, a, _plan(), row, run_points=(x, y, lab), n_resample=12)
    assert out["gates_nothing"] is True and "not been observed under closed-loop control" in out["caveat"]
    assert "20 settled points across 4 runs" in out["caveat"]
    bad = [k for k in _keys(out) if any(w in k.lower() for w in ("verdict", "licensed", "deployable", "gate_"))]
    assert bad == [], bad
    # the refused path carries it too
    t_coarse = np.arange(40) * 230.0
    out2 = S.run_models(t_coarse, p[:40], a[:40], _plan(), row, n_resample=0)
    assert out2["refused"] is True and "not resolvable" in out2["absent_reason"]
    assert out2["gates_nothing"] is True and out2["caveat"]


def test_7b_run_models_end_to_end_gives_m0_m1_m3_and_the_difference():
    t, p, a = _series()
    row = dict(_peaked_row(), curves=False, peaks_inside=False)
    x = np.concatenate([np.linspace(1, 3, 5)] * 4); y = 10 - 2 * x + np.tile([0, 1, -1, 0.5], 5)[:20]
    lab = sum([[r] * 5 for r in "ABCD"], [])
    out = S.run_models(t, p, a, _plan(), row, run_points=(x, y, lab), n_resample=25, seed=3)
    assert set(out["models"]) == {"M0", "M1", "M3"} and out["active_model"] == "M1"
    m3 = out["models"]["M3"]
    assert m3["n_replicates"] == 25 and m3["intervals"]["frac_time_at_upper"] is not None
    d = out["closed_loop_difference"]
    assert d["frac_time_at_upper"] == pytest.approx(
        out["models"]["M1"]["frac_time_at_upper"] - out["models"]["M0"]["frac_time_at_upper"])
    assert out["settling"]["tau_s"] == S.DEFAULT_TAU_S and "default" in out["settling"]["source"]
    assert len(out["drawn"]) == 1 and out["drawn"][0]["m3_amp_band"] is not None
    assert len(out["drawn"][0]["models"]["M1"]["amp"]) == len(out["drawn"][0]["t_s"])
    assert sum(out["models"]["M0"]["amp_hist"]) == out["record"]["steps_used"]


# --------------------------------------------------------------------------------------------
# 8. the coefficients the curve rests on come out of the pooled fit and into the stored table
# --------------------------------------------------------------------------------------------
def test_8_the_pooled_fit_returns_the_quadratic_coefficients_and_the_table_carries_them():
    rng = np.random.default_rng(0)
    xs, ys, vs = [], [], []
    for k, base in enumerate([100.0, 110.0, 95.0, 105.0]):
        x = np.linspace(0.5, 3.5, 7)
        y = base - 30.0 * (x - 2.0) ** 2 + rng.normal(0, 1.0, x.size)
        xs.append(x); ys.append(y); vs.append(np.full(x.size, f"run{k}"))
    out = WV.amplitude_response_shape_pooled(np.concatenate(xs), np.concatenate(ys), np.concatenate(vs))
    assert out["curves"] and out["peaks_inside"]
    assert out["quad_coef_per_mA2"] == pytest.approx(-30.0, abs=1.5)
    assert out["quad_lin_coef_per_mA"] == pytest.approx(120.0, abs=6.0)
    assert np.isfinite(out["quad_coef_stderr"])
    for name in ("quad_coef_per_mA2", "quad_lin_coef_per_mA", "quad_coef_stderr",
                 "post_peak_slope_per_mA", "post_peak_intercept", "post_peak_n_points"):
        assert name in AE.POOLED_FIELDS
    assert AE.POOLED_RULE_VERSION != "v1_pooled_shape", "the stored table changed shape; the old entry must not be served"
    row = dict(out, post_peak_slope_per_mA=out["post_peak"]["slope_per_mA"])
    c = AR.ResponseCurve.from_pooled_row(row)
    assert c.kind == AR.QUADRATIC and abs(c.peak_mA - 2.0) < 0.1
    # a row that predates v2 (no coefficients) still gives the straight line, never a crash
    old = {k: v for k, v in row.items() if not k.startswith("quad_")}
    assert AR.ResponseCurve.from_pooled_row(old).kind == AR.LINEAR


def test_1c_jittered_pieces_are_put_on_the_device_clock_not_refused():
    """Inside one recording the 3 s pieces jitter (RCS08: 2.5 s, 1.75 s, 7 s between neighbours),
    and the controller refuses anything 5 % off the median. The segment runner regrids each
    stretch to the median interval first: a cell with two pieces averages them, a cell with none
    is a missing estimate the controller holds across. A uniform series is unchanged by it."""
    t, p, a = _series(n=400, dt=3.0)
    rng = np.random.default_rng(4)
    tj = t + rng.uniform(-0.3, 0.3, t.size)            # up to 10 % jitter, twice the 5 % refusal
    tj[100] = tj[99] + 0.3                               # two pieces in one 3 s cell
    keep = np.ones(t.size, dtype=bool); keep[200] = False       # one cell with no piece (a 6 s hole, not a gap)
    plan = _plan()
    with pytest.raises(ValueError):
        R.dual_threshold({"t_s": tj[keep], "power": p[keep]}, plan)
    res = S.simulate_segments(tj[keep], p[keep], a[keep], plan, [AR.ResponseCurve.zero()], tau_s=3.0)
    assert res["refused"] is False and res["n_segments_used"] == 1 and res["n_segments_skipped"] == 0
    # the removed piece leaves one empty cell; the piece moved into its neighbour's cell leaves
    # its own cell empty and makes that neighbour a merged cell
    assert res["n_cells_without_a_piece"] == 2 and res["n_cells_merging_pieces"] == 1
    assert res["n_missing_steps"] == 2 and res["steps_used"] == 400
    # the same stretch, uniform: identical to running the controller on it directly
    ref = R.dual_threshold({"t_s": t, "power": p}, plan)
    res_u = S.simulate_segments(t, p, a, plan, [AR.ResponseCurve.zero()], tau_s=3.0)
    assert res_u["n_cells_without_a_piece"] == 0 and res_u["n_cells_merging_pieces"] == 0
    assert float(res_u["frac_at_upper"][0]) == float(ref.frac_time_at_upper)
    assert int(res_u["n_transitions"][0]) == int(ref.n_transitions)


def test_9_each_candidate_keeps_its_own_stored_simulation_and_is_read_back_by_candidate(tmp_path):
    """Met live on 2026-09-11: the page's own report wrote a simulation for the band committed on
    the page and the store, keeping one entry per kind, evicted the one for the other band; the
    read path then served the newest entry whatever band it was for. The store now keeps several
    (KEEP_NEWEST_BY_KIND) and the read matches the sidecar's candidate tag."""
    try:
        from modules.CacheStore import ledger as _ledger
        from modules.ClosedLoopDeployment import adapter as AD
    except ImportError:                                          # pragma: no cover
        from CacheStore import ledger as _ledger
        from ClosedLoopDeployment import adapter as AD
    assert st.KEEP_NEWEST_BY_KIND.get(S.KIND, 1) >= 2
    uid = "p-sim-cands"
    prev = st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE
    st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE = str(tmp_path), False, str(tmp_path)
    st.clear()
    try:
        for i, (ch, fc) in enumerate((("ONE_THREE_LEFT", 20.5), ("ZERO_THREE_RIGHT", 17.5))):
            st.store(S.KIND, uid, (S.KIND, S.RULE_VERSION, ch, fc), {"active_model": "M1", "for": ch},
                     writer="closed_loop", trigger="deployment_report", provenance=[],
                     extra={"candidate": AD._simulation_candidate_tag(ch, fc, "Left")})
        got_l = AD.simulation_if_stored(uid, {"channel": "ONE_THREE_LEFT", "center_hz": 20.5}, hemisphere="Left")
        got_r = AD.simulation_if_stored(uid, {"channel": "ZERO_THREE_RIGHT", "center_hz": 17.5}, hemisphere="Left")
        assert got_l == {"active_model": "M1", "for": "ONE_THREE_LEFT"}, "both entries survive and each is found"
        assert got_r == {"active_model": "M1", "for": "ZERO_THREE_RIGHT"}
        assert AD.simulation_if_stored(uid, {"channel": "ONE_THREE_LEFT", "center_hz": 12.5}) is None
        out = AD.closed_loop_simulation_for_participant(uid, {"channel": "ONE_THREE_LEFT", "center_hz": 12.5})
        assert out["refused"] is True and "this configuration" in out["absent_reason"]
    finally:
        st.clear()
        st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE = prev
