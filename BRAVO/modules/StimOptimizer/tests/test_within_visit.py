"""The within-visit evidence builder, and the claim that the existing screen consumes it unchanged."""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import within_visit as WV
from StimOptimizer.routines import lfp_evidence as EV
from StimOptimizer.routines import lfp_response as LR

CEN = np.arange(10.5, 27.6, 1.0)


def _steps(n_visits=6, per_visit=8, rate=55.0, amps=(1.0, 3.5), tile_dt=3.0, win=120.0):
    """Clinic steps: each visit walks the amplitude ladder, which is the design's whole premise."""
    rows = []
    t = 1_700_000_000.0
    for v in range(n_visits):
        for k in range(per_visit):
            rows.append(dict(t0=t, window_s=win, rate_hz=rate,
                             amp_mA_Left=amps[k % len(amps)],
                             amp_mA_Right=amps[k % len(amps)],
                             visit=f"2026-0{v + 1}-01"))
            t += win + 60.0
        t += 86400.0
    return pd.DataFrame(rows)


def _tiles(steps, *, slope_per_mA=-0.2, seed=0, tile_dt=3.0, ramp_s=WV.RAMP_EXCLUDE_S):
    """Tiles spanning each step, carrying a real amplitude effect plus a per-visit offset."""
    rng = np.random.default_rng(seed)
    ts, ps = [], []
    voff = {v: rng.normal(0, 0.4) for v in steps.visit.unique()}
    for _, r in steps.iterrows():
        n = int(r.window_s // tile_dt)
        for j in range(n):
            ts.append(r.t0 + j * tile_dt)
            base = 5.0 + slope_per_mA * r.amp_mA_Left + voff[r.visit]
            ps.append(base + rng.normal(0, 0.05, CEN.size))
    o = np.argsort(np.asarray(ts))
    return np.asarray(ts)[o], np.vstack(ps)[o]


def test_within_visit_import_does_not_pull_in_biomarkers():
    """The dependency direction is load-bearing: ClosedLoopDeployment imports StimOptimizer, never
    the reverse, so a builder here cannot reach into ClosedLoopDeployment.clinic_steps. The
    harmonic-landing flag needs Biomarkers and therefore stays on that side; this asserts the split
    actually holds rather than being described in a comment.
    """
    import subprocess, sys, os
    code = ("import sys;"
            "from StimOptimizer.routines import within_visit;"
            "print([m for m in sys.modules if m.startswith('Biomarkers')])")
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(WV.__file__)))))
    r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr[-400:]
    assert r.stdout.strip().endswith("[]"), r.stdout


def test_builder_returns_the_same_shape_build_all_does_and_screen_cells_eats_it():
    """The load-bearing interoperability claim. If the mapping shape drifts, the whole gate
    downstream -- the majority-of-bands rule, the era-significance condition, the amplitude
    ceiling -- silently stops applying to within-visit evidence.
    """
    S = _steps()
    tt, tp = _tiles(S)
    ev, audit = WV.build_all_within_visit(
        S, centers_hz=CEN, tiles_by_channel={"ZERO_TWO_LEFT": (tt, tp)},
        hemispheres=("Left",), rates=(55.0,))
    assert isinstance(ev, dict) and isinstance(audit, pd.DataFrame)
    assert list(ev) == [("ZERO_TWO_LEFT", "Left", 55.0)]
    e = ev[("ZERO_TWO_LEFT", "Left", 55.0)]
    assert e.amplitude_mA.size == e.era.size == e.cluster.size
    assert len(e.band_power) == CEN.size

    # screen_cells returns (frame, selected_key) -- the selection is part of its contract, so a
    # test that unpacked only the frame would not notice the key going missing.
    scr, selected = EV.screen_cells(ev, response_fn=LR.assess_response)
    assert isinstance(scr, pd.DataFrame) and len(scr) == 1
    for col in ("channel", "hemisphere", "rate_hz", "n_bands", "n_responding",
                "deployable", "blocking_reasons"):
        assert col in scr.columns, (col, list(scr.columns))
    assert int(scr.n_bands.iloc[0]) == CEN.size

    # and the GATE really applies: a clean within-visit design with a genuine negative slope
    # reaches deployable, which is what proves the downstream rules were not bypassed.
    assert bool(scr.deployable.iloc[0]) is True, scr.blocking_reasons.iloc[0]
    assert selected == ("ZERO_TWO_LEFT", "Left", 55.0), selected


def test_the_visit_supplies_era_and_cluster_and_amplitude_varies_inside_it():
    """The property the chronic epochs lacked. There, each era carried ONE amplitude, so its dummy
    absorbed the era entirely and contributed no within-era contrast -- which is why restricting to
    five recent eras left the blocked slope identical to four decimals. Here every visit contains
    both arms, so blocking removes calendar time WITHOUT absorbing the effect.
    """
    S = _steps()
    tt, tp = _tiles(S)
    e, aud = WV.build_within_visit_evidence(
        S, channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=55.0,
        centers_hz=CEN, tile_t=tt, tile_power=tp)
    assert e is not None, aud.reason_unusable
    assert np.array_equal(e.era, e.cluster)
    df = pd.DataFrame({"era": e.era, "amp": e.amplitude_mA})
    per_era = df.groupby("era").amp.nunique()
    assert (per_era >= 2).all(), per_era.to_dict()
    assert aud.n_eras >= 2 and len(aud.amplitudes) >= 2


def test_a_real_negative_slope_survives_the_builder():
    S = _steps()
    tt, tp = _tiles(S, slope_per_mA=-0.30)
    e, _ = WV.build_within_visit_evidence(
        S, channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=55.0,
        centers_hz=CEN, tile_t=tt, tile_power=tp)
    r = LR.assess_response(e.power_for(20.5, 5.0), e.amplitude_mA, era=e.era, cluster=e.cluster)
    assert r.slope_log_per_mA < 0, r.slope_log_per_mA
    assert r.direction_ok is True
    assert r.slope_p < 0.05


def test_unusable_cells_are_audited_with_a_reason_never_silently_absent():
    S = _steps(amps=(2.0,))                      # one amplitude only -> no capture contrast
    tt, tp = _tiles(S)
    e, aud = WV.build_within_visit_evidence(
        S, channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=55.0,
        centers_hz=CEN, tile_t=tt, tile_power=tp)
    assert e is None and "one binned amplitude" in (aud.reason_unusable or "")

    # a rate with no steps at all
    e2, aud2 = WV.build_within_visit_evidence(
        _steps(), channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=999.0,
        centers_hz=CEN, tile_t=tt, tile_power=tp)
    assert e2 is None and aud2.reason_unusable
    assert aud2.n_dropped_other_rate > 0

    # tiles that do not overlap the steps
    e3, aud3 = WV.build_within_visit_evidence(
        _steps(), channel="ZERO_TWO_LEFT", hemisphere="Left", rate_hz=55.0,
        centers_hz=CEN, tile_t=tt + 5e6, tile_power=tp)
    assert e3 is None and "settled window" in (aud3.reason_unusable or "")


def test_centre_count_mismatch_raises_rather_than_mislabelling_bands():
    """Silent misalignment here would attribute one band's power to another's centre, which is the
    single worst failure available in this module -- it would be invisible and wrong.
    """
    S = _steps()
    tt, tp = _tiles(S)
    with pytest.raises(ValueError, match="centers_hz"):
        WV.build_within_visit_evidence(S, channel="ZERO_TWO_LEFT", hemisphere="Left",
                                       rate_hz=55.0, centers_hz=CEN[:-3],
                                       tile_t=tt, tile_power=tp)


# --- the band-axis cluster permutation test (2026-09-05) -----------------------------------------
def _panel(n_visits=8, per_visit=12, amps=(1.0, 2.0, 3.0, 4.0), seed=0,
           effect_bands=(), slope=-0.30, noise=0.25, visit_sd=0.5):
    """Within-visit panel: a per-visit offset plus an amplitude effect in `effect_bands` only."""
    rng = np.random.default_rng(seed)
    vis, amp = [], []
    for v in range(n_visits):
        for k in range(per_visit):
            vis.append(f"v{v}")
            amp.append(amps[k % len(amps)])
    vis = np.asarray(vis); amp = np.asarray(amp, dtype=float)
    off = {v: rng.normal(0, visit_sd) for v in set(vis)}
    base = np.array([off[v] for v in vis])
    power = {}
    for c in CEN:
        y = 5.0 + base + rng.normal(0, noise, amp.size)
        if any(abs(c - e) < 1e-9 for e in effect_bands):
            y = y + slope * amp
        power[float(c)] = y
    return power, amp, vis


def test_the_fast_estimator_matches_the_gates_statsmodels_fit():
    """The consistency claim. A fast reimplementation that silently disagreed with
    `assess_response`'s estimator would make the SEARCH and the VERDICT answer different questions,
    and the discrepancy would be invisible because both look reasonable in isolation.

    The raw CR0 sandwich differed from statsmodels by exactly sqrt(G/(G-1) * (N-1)/(N-K)) -- the
    standard finite-sample correction -- measured at a ratio of 1.134349 against a predicted
    1.134349 on a 90-row, 6-cluster construction. That identified it as the correction rather than a
    modelling difference, and it is now applied.
    """
    import statsmodels.formula.api as smf
    rng = np.random.default_rng(7)
    n, nv = 90, 6
    vis = np.array([f"v{i % nv}" for i in range(n)])
    amp = rng.choice([1.0, 2.0, 3.0, 4.0], n)
    off = {v: rng.normal(0, 0.5) for v in set(vis)}
    y = np.array([5 - 0.25 * a + off[v] + rng.normal(0, 0.3) for a, v in zip(amp, vis)])

    mine = WV._band_t_cluster_robust(y, amp, vis, vis)
    df = pd.DataFrame({"logp": y, "amp": amp, "era": vis, "clus": vis})
    res = smf.ols("logp ~ amp + C(era)", data=df).fit(
        cov_type="cluster", cov_kwds={"groups": df["clus"]})
    assert abs(mine - float(res.params["amp"] / res.bse["amp"])) < 1e-8


def test_clusters_are_runs_of_adjacent_same_signed_bands():
    t = np.array([0.1, 2.5, 3.0, 2.2, 0.4, -2.1, -2.9, 0.2, 2.4])
    got = WV._clusters_along_axis(t, 2.0)
    assert got == [(1, 4, 7.7), (5, 7, -5.0), (8, 9, 2.4)], got
    # a sign change BREAKS a run even with both sides supra-threshold
    t2 = np.array([2.5, -2.5, 2.5])
    assert len(WV._clusters_along_axis(t2, 2.0)) == 3
    # and nothing supra-threshold gives no clusters
    assert WV._clusters_along_axis(np.array([0.5, 1.0, -1.2]), 2.0) == []


def test_a_localised_effect_is_detected_where_the_majority_rule_cannot_be_satisfied():
    """The whole reason this test exists. Four adjacent bands of eighteen carry a real effect --
    22% of the grid, so the 50% majority rule refuses it by construction however strong it is.
    """
    eff = tuple(CEN[14:18])                       # 24.5-27.5 Hz, four adjacent centres
    power, amp, vis = _panel(effect_bands=eff, slope=-0.30, seed=1)
    r = WV.band_cluster_permutation(power, amp, vis, n_perm=300, seed=0)
    assert r["available"] is True
    assert r["n_clusters"] >= 1
    L = r["largest_cluster"]
    assert L["sign"] == "negative", L
    assert r["p_fwer"] <= 0.05, r["p_fwer"]
    # the effect occupies well under the majority the gate requires
    assert len(eff) / len(CEN) < 0.5


def test_a_flat_panel_is_not_significant():
    """Size. No amplitude effect in any band; the largest noise cluster must not be rejected."""
    power, amp, vis = _panel(effect_bands=(), seed=2)
    r = WV.band_cluster_permutation(power, amp, vis, n_perm=300, seed=0)
    assert r["available"] is True
    if r.get("p_fwer") is not None:
        assert r["p_fwer"] > 0.05, (r["p_fwer"], r["largest_cluster"])


def test_the_p_value_can_never_beat_its_own_resolution():
    power, amp, vis = _panel(effect_bands=tuple(CEN[14:18]), slope=-0.60, seed=3)
    r = WV.band_cluster_permutation(power, amp, vis, n_perm=99, seed=0)
    if r.get("p_fwer") is not None:
        assert r["p_fwer"] >= r["p_resolution"] - 1e-12
        assert abs(r["p_resolution"] - 1.0 / 100) < 1e-12


def test_it_refuses_rather_than_returning_a_meaningless_number():
    power, amp, vis = _panel(n_visits=1, seed=4)
    r = WV.band_cluster_permutation(power, amp, vis, n_perm=50, seed=0)
    assert r["available"] is False and "within visits" in r["reason"].lower()

    # a panel where every visit holds ONE amplitude: permuting within visit changes nothing
    power2, amp2, vis2 = _panel(n_visits=6, per_visit=6, amps=(2.0,), seed=5)
    r2 = WV.band_cluster_permutation(power2, amp2, vis2, n_perm=50, seed=0)
    assert r2["available"] is False and "two amplitudes" in r2["reason"].lower()

    # too few centres to have an axis to cluster along
    r3 = WV.band_cluster_permutation({10.5: np.zeros(20), 11.5: np.zeros(20)},
                                     np.ones(20), np.array(["a"] * 10 + ["b"] * 10),
                                     n_perm=50, seed=0)
    assert r3["available"] is False and "three centres" in r3["reason"].lower()


def test_the_result_states_that_it_cannot_locate_the_effect():
    """Guards a real hazard rather than prose. This test's whole point is that a reader must not be
    able to take the cluster's frequency limits as a band to program: cluster-sum inference gives
    weak family-wise control and does not establish location (Sassenhagen & Draschkow 2019). If
    this warning is ever edited away, the next reader may hand those limits to a clinician.
    """
    power, amp, vis = _panel(effect_bands=tuple(CEN[14:18]), slope=-0.30, seed=6)
    r = WV.band_cluster_permutation(power, amp, vis, n_perm=100, seed=0)
    note = (r.get("note") or "").lower()
    assert "not its location" in note or "not location" in note, r.get("note")
    assert "must not be used to choose a band" in note, r.get("note")
    # and the flat-panel branch must carry the weak-evidence-of-absence caveat
    p2, a2, v2 = _panel(effect_bands=(), noise=1.5, seed=7)
    r2 = WV.band_cluster_permutation(p2, a2, v2, n_perm=50, seed=0)
    if r2.get("n_clusters") == 0:
        assert "weak evidence of absence" in (r2.get("note") or "")


def test_the_threshold_sweep_comes_from_one_permutation_loop_and_matches_separate_runs():
    """The sweep exists because the cluster-forming threshold is a free parameter, and the honest
    way to handle that is to show the whole sweep rather than one chosen value. It must therefore be
    identical to running the test separately at each threshold with the same seed -- otherwise the
    sweep would be a different, cheaper thing wearing the same name.
    """
    power, amp, vis = _panel(effect_bands=tuple(CEN[14:18]), slope=-0.30, seed=11)
    swept = WV.band_cluster_permutation(power, amp, vis, n_perm=200, seed=3,
                                        t_threshold=2.0, extra_thresholds=(1.5, 3.0))
    assert set(swept["threshold_sweep"]) == {1.5, 2.0, 3.0}
    for th in (1.5, 2.0, 3.0):
        alone = WV.band_cluster_permutation(power, amp, vis, n_perm=200, seed=3, t_threshold=th)
        got, want = swept["threshold_sweep"][th]["p_fwer"], alone.get("p_fwer")
        assert got == want, (th, got, want)


def test_a_higher_threshold_never_grows_a_cluster():
    """A sanity property of cluster formation that a bug in the grouping would break: raising the
    threshold can only remove bands from a run, never add them.
    """
    power, amp, vis = _panel(effect_bands=tuple(CEN[12:18]), slope=-0.35, seed=12)
    r = WV.band_cluster_permutation(power, amp, vis, n_perm=100, seed=0,
                                    t_threshold=1.5, extra_thresholds=(2.0, 2.5, 3.0))
    sizes = {th: d["largest_n_bands"] for th, d in r["threshold_sweep"].items()
             if d["largest_n_bands"] is not None}
    ordered = [sizes[th] for th in sorted(sizes)]
    assert ordered == sorted(ordered, reverse=True), sizes


def test_the_primary_threshold_is_always_present_in_the_sweep():
    power, amp, vis = _panel(effect_bands=tuple(CEN[14:18]), slope=-0.30, seed=13)
    r = WV.band_cluster_permutation(power, amp, vis, n_perm=100, seed=0, t_threshold=2.0,
                                    extra_thresholds=(2.0, 2.0))     # duplicates collapse
    assert list(r["threshold_sweep"]) == [2.0]
    assert r["threshold_sweep"][2.0]["p_fwer"] == r["p_fwer"]


# =================================================================================================
# AVERAGING THE LAST 30 SECONDS BEFORE THE CURRENT IS CHANGED AGAIN
# =================================================================================================
# These tests are about a rule the PI stated in words, so each one is named after the sentence of
# his it is checking. Every band power here is a plain number of order a hundred, the way the
# device reports it, and no test takes a logarithm of anything.

LADDER_BANDS = 4


def _ladder(currents, *, hold_s=60.0, t_start=1_700_000_000.0, rate=55.0):
    """One setting per current, each held ``hold_s`` seconds, the next starting when the last ends."""
    t = float(t_start)
    t0, rows = [], []
    for c in currents:
        t0.append(t)
        rows.append(rate)
        t += float(hold_s)
    return np.asarray(t0), np.asarray(currents, dtype=float), np.asarray(rows, dtype=float)


def _pieces(t0, currents, hold_s=60.0, *, per_mA=10.0, base=100.0, piece_s=3.0, gap_from=None):
    """Three second pieces covering every setting, band power rising 10 device units per milliamp.

    ``gap_from`` optionally starves ONE setting, given by its index, of all but two of its pieces,
    which is how the fewer-than-ten-pieces case is built.
    """
    ts, ps = [], []
    for i, (a, c) in enumerate(zip(t0, currents)):
        n = int(hold_s // piece_s)
        keep = range(n) if gap_from != i else range(2)
        for j in keep:
            ts.append(a + j * piece_s)
            ps.append(np.full(LADDER_BANDS, base + per_mA * c))
    o = np.argsort(np.asarray(ts, dtype=float))
    return np.asarray(ts, dtype=float)[o], np.vstack(ps)[o]


def test_the_number_is_the_mean_of_the_ten_pieces_in_the_last_thirty_seconds():
    t0, amp, rate = _ladder([1.0, 1.1, 1.2, 1.3])
    tt, tp = _pieces(t0, amp)
    P, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    acc = T[T.accepted]
    # The first setting of the block has nothing before it to rise from; the last has no next
    # change. The two in the middle are measured.
    assert list(acc.current_mA) == [1.1, 1.2]
    assert list(acc.n_chunks_found) == [10, 10]
    # 100 + 10 per mA, and the window sits inside the setting it is describing, so 1.1 mA reads 111.
    assert np.allclose(P[1, :], 111.0)
    assert np.allclose(P[2, :], 112.0)
    assert np.all(~np.isfinite(P[0, :])) and np.all(~np.isfinite(P[3, :]))


def test_the_window_ends_where_the_next_setting_starts_and_never_reaches_past_it():
    t0, amp, rate = _ladder([1.0, 2.0, 3.0, 4.0])
    tt, tp = _pieces(t0, amp)
    _, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    r = T.iloc[1]
    assert r.t_next_change_s == t0[2]
    assert r.window_start_s == t0[2] - WV.PRE_CHANGE_WINDOW_S
    assert r.window_start_s >= t0[1]           # inside its own setting, not the one before it
    assert not r.window_shortened_by_setting_start


def test_a_current_that_drops_to_zero_and_climbs_again_does_not_carry_the_earlier_ladder_across():
    # The PI's own example: 1, 2, 3, then 0, then 0.5 and 1.0 again. The 0 breaks the ladder, and
    # the settings on either side of the break must not be measured as if the ladder continued.
    t0, amp, rate = _ladder([1.0, 2.0, 3.0, 0.0, 0.5, 1.0, 1.5])
    tt, tp = _pieces(t0, amp)
    _, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    got = dict(zip(T.setting_index, T.accepted))
    assert got[2] is True or bool(got[2])       # 3.0 mA was reached by a rise from 2.0
    assert not bool(got[3])                     # 0.0 mA was reached by the current being switched off
    assert bool(T.iloc[2].next_change_is_a_further_rise) is False   # what follows 3.0 is the drop
    # 0.5 mA sits after the break. It is reached by a rise from zero, so the rule measures it, but
    # the number describes 0.5 mA and NOT the 3.0 mA that ran before the break, because the window
    # lies inside the 0.5 mA setting.
    assert bool(got[4])
    assert np.isclose(T.iloc[4].window_start_s, t0[5] - WV.PRE_CHANGE_WINDOW_S)
    assert T.iloc[4].window_start_s > t0[3]


def test_a_setting_reached_by_turning_the_current_down_is_refused_with_a_reason():
    t0, amp, rate = _ladder([1.0, 3.0, 2.0, 2.5])
    tt, tp = _pieces(t0, amp)
    _, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    row = T.iloc[2]                              # 2.0 mA, arrived at by dropping from 3.0
    assert not row.accepted
    assert "did not go up" in row.refusal_reason
    loose = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate,
                                             require_rise_into_setting=False)[1]
    assert bool(loose.iloc[2].accepted)          # the looser rule lets it through, on request


def test_fewer_than_ten_pieces_gets_no_number_and_reports_the_count_it_actually_found():
    t0, amp, rate = _ladder([1.0, 2.0, 3.0, 4.0])
    tt, tp = _pieces(t0, amp, gap_from=2)        # setting 2 keeps only its first two pieces
    P, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    row = T.iloc[2]
    assert row.n_chunks_found == 0               # the two it kept are at the START, not the last 30 s
    assert not row.accepted
    assert "three second pieces" in row.refusal_reason
    assert np.all(~np.isfinite(P[2, :]))         # nothing to colour, so nothing is returned
    assert bool(T.iloc[1].accepted)              # its neighbour is unaffected


def test_a_setting_held_briefly_has_its_window_cut_at_its_own_start_not_topped_up():
    # The middle setting is held only 12 seconds, so a full 30 second window would reach back into
    # the setting before it and average two different currents together. It must be cut instead.
    t0 = np.array([0.0, 100.0, 112.0, 200.0]) + 1_700_000_000.0
    amp = np.array([1.0, 2.0, 3.0, 4.0])
    rate = np.full(4, 55.0)
    ends = np.r_[t0[1:], t0[-1] + 100.0]
    ts, ps = [], []
    for a, e, c in zip(t0, ends, amp):
        j = 0
        while a + j * 3.0 < e:                   # pieces never spill into the next setting
            ts.append(a + j * 3.0)
            ps.append(np.full(LADDER_BANDS, 100.0 + 10.0 * c))
            j += 1
    o = np.argsort(np.asarray(ts))
    tt, tp = np.asarray(ts)[o], np.vstack(ps)[o]
    _, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    row = T.iloc[1]                              # 2.0 mA, held 100 s to 112 s
    assert row.window_shortened_by_setting_start
    assert row.window_start_s == t0[1]
    assert row.n_chunks_found == 4                # 12 s of a 3 s grid, not the ten a full window has
    assert not row.accepted
    assert bool(T.iloc[2].accepted)              # the long setting after it is unaffected
    assert int(T.iloc[2].n_chunks_found) == 10


def test_two_stimulation_rates_are_never_treated_as_one_ladder():
    t0, amp, _ = _ladder([1.0, 2.0, 3.0, 1.0, 2.0, 3.0])
    block = np.array([55.0, 55.0, 55.0, 10.0, 10.0, 10.0])
    tt, tp = _pieces(t0, amp)
    _, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=block)
    assert not bool(T.iloc[3].accepted)          # 1.0 mA at 10 Hz does not rise from 3.0 mA at 55 Hz
    assert "did not go up" in T.iloc[3].refusal_reason
    assert not bool(T.iloc[2].accepted)          # 3.0 mA at 55 Hz has no next change at 55 Hz
    assert "not known" in T.iloc[2].refusal_reason


def test_the_average_is_in_the_units_it_was_given_and_takes_no_logarithm():
    t0, amp, rate = _ladder([1.0, 2.0, 3.0, 4.0])
    tt, tp = _pieces(t0, amp, base=150.0, per_mA=25.0)
    P, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    assert np.allclose(P[1, :], 200.0)           # 150 + 25 x 2, in the device's own numbers
    assert np.allclose(P[2, :], 225.0)
    assert P[1, 0] > 10.0                         # a logarithm of 200 would be about 2.3


def test_it_complains_rather_than_guessing_when_the_pieces_do_not_line_up():
    t0, amp, rate = _ladder([1.0, 2.0, 3.0])
    tt, tp = _pieces(t0, amp)
    with pytest.raises(ValueError, match="current_mA"):
        WV.mean_power_before_next_change(t0, amp[:2], tt, tp, block=rate)
    with pytest.raises(ValueError, match="sorted ascending"):
        WV.mean_power_before_next_change(t0, amp, tt[::-1], tp, block=rate)
    with pytest.raises(ValueError, match="n_bands"):
        WV.mean_power_before_next_change(t0, amp, tt, tp[:5, :], block=rate)


def test_the_older_median_rule_is_still_there_and_still_does_its_own_thing():
    # Other code calls step_settled_medians, so adding the new rule must not have moved it.
    assert hasattr(WV, "step_settled_medians") and hasattr(WV, "mean_power_before_next_change")
    t0, amp, rate = _ladder([1.0, 2.0, 3.0, 4.0], hold_s=120.0)
    tt, tp = _pieces(t0, amp, hold_s=120.0)
    med, cnt, kept = WV.step_settled_medians(t0, np.full(4, 120.0), tt, tp)
    assert len(kept) == 4                        # the old rule measures every setting
    P, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    assert int(T.accepted.sum()) == 2            # the new rule measures only the middle two
