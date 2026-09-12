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


# --- the measured ramp exclusion and the peaked-response check (2026-09-06) --------------------
def test_a_peaked_response_is_reported_as_peaked_and_not_as_flat():
    """The failure this guards: a rise-then-fall reads as 'does not respond' to a linear test.

    Built to match what the harmonic-contaminated bands actually do on RCS08 -- power peaking near
    1.8 mA across a 0-3.5 mA ladder -- with the straight-line slope near zero by construction.
    """
    amp = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5] * 2, dtype=float)
    # A downward parabola centred at 1.75 mA, so the linear slope through it is ~0.
    power = 400.0 - 90.0 * (amp - 1.75) ** 2
    rng = np.random.RandomState(0)
    power = power + rng.normal(0, 4.0, size=power.size)

    lin_slope = np.polyfit(amp, power, 1)[0]
    assert abs(lin_slope) < 12.0, "fixture is wrong: the linear slope should be near zero"

    out = WV.amplitude_response_shape(amp, power)
    assert out["curves"] is True
    assert out["peaks_inside"] is True
    assert 1.5 < out["peak_mA"] < 2.0
    assert out["p_curvature"] < 0.01
    # The point of the whole function: the linear summary is bad and the peaked one is good.
    assert out["r2_linear"] < 0.15
    assert out["r2_quadratic"] > 0.85
    assert "peaking at" in out["verdict"]
    # The verdict must warn that the module's own linear tests will miss this, which is the whole
    # reason the function exists. It must NOT assert an artefact interpretation: that reading was
    # tried on 2026-09-06 and refuted, because a stimulation artefact grows monotonically with
    # current while this comes back down. See the docstring.
    assert "NO RESPONSE" in out["verdict"]
    assert "HARMONIC" not in out["verdict"]


def test_a_straight_relationship_is_not_reported_as_curved():
    amp = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5] * 2, dtype=float)
    rng = np.random.RandomState(1)
    power = 100.0 + 40.0 * amp + rng.normal(0, 5.0, size=amp.size)
    out = WV.amplitude_response_shape(amp, power)
    assert out["curves"] is False
    assert out["peaks_inside"] is False
    assert np.isnan(out["peak_mA"])
    assert out["r2_linear"] > 0.85
    assert "no curvature" in out["verdict"]


def test_too_few_points_says_not_assessed_rather_than_guessing():
    out = WV.amplitude_response_shape([0.0, 1.0, 2.0], [10.0, 20.0, 15.0])
    assert out["curves"] is False
    assert out["verdict"].startswith("not assessed")
    assert np.isnan(out["p_curvature"])
    # A constant signal has no variation to explain, and must not come back as a fitted result.
    flat = WV.amplitude_response_shape([0.0, 1.0, 2.0, 3.0] * 3, [5.0] * 12)
    assert flat["verdict"].startswith("not assessed")


def test_pooling_without_visit_adjustment_would_manufacture_a_fake_peak():
    """THE FAILURE THIS FUNCTION EXISTS TO AVOID -- decision 17's lesson, applied to pooling
    amplitude ladders across visits (PI decision 55). Three visits, each perfectly FLAT within
    itself (no real amplitude relationship at all), but at three different baseline power levels,
    and each visit happens to have tested a different slice of the current range. Pooled naively
    this traces a rise-then-fall shape purely from between-visit baseline differences lining up
    with which currents each visit tested -- exactly the shape a real physiological peak would
    leave. The cluster-robust, per-visit-intercept test must not be fooled by it.
    """
    rng = np.random.RandomState(2)
    amp_a = np.array([0.5, 1.0, 1.5] * 4)
    amp_b = np.array([1.5, 2.0, 2.5] * 4)
    amp_c = np.array([2.5, 3.0, 3.5] * 4)
    amp = np.concatenate([amp_a, amp_b, amp_c])
    power = np.concatenate([
        100.0 + rng.normal(0, 3.0, amp_a.size),
        200.0 + rng.normal(0, 3.0, amp_b.size),
        100.0 + rng.normal(0, 3.0, amp_c.size),
    ])
    visit = np.array(["A"] * amp_a.size + ["B"] * amp_b.size + ["C"] * amp_c.size)

    # Confirm the fixture actually does what it claims: naively pooled (no visit adjustment,
    # today's single-visit function applied to the concatenated points) it looks curved.
    naive = WV.amplitude_response_shape(amp, power)
    assert naive["curves"] is True, "fixture is wrong: the naive pooled fit should look curved"

    out = WV.amplitude_response_shape_pooled(amp, power, visit)
    assert out["curves"] is False, "a per-visit baseline shift must not be reported as curvature"
    assert out["n_visits"] == 3
    assert out["post_peak"] is None


def test_a_genuine_pooled_peak_is_detected_with_visit_baselines_removed():
    """A real rise-then-fall shape, the SAME shape in every visit, riding on different per-visit
    baselines -- what a genuine response pooled across real visits should look like. Must be
    detected as curved, with the baseline correctly absorbed rather than distorting the peak, and
    the post-peak line must use only the pooled points at or above the peak.
    """
    amp = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
    shape = 400.0 - 90.0 * (amp - 1.75) ** 2
    rng = np.random.RandomState(3)
    xs, ys, vs = [], [], []
    for i, baseline in enumerate([0.0, 150.0, -80.0]):
        xs.append(amp)
        ys.append(shape + baseline + rng.normal(0, 4.0, amp.size))
        vs.append([f"visit{i}"] * amp.size)
    x, y, v = np.concatenate(xs), np.concatenate(ys), np.concatenate(vs)

    out = WV.amplitude_response_shape_pooled(x, y, v)
    assert out["curves"] is True
    assert out["peaks_inside"] is True
    assert 1.5 < out["peak_mA"] < 2.0
    assert out["n_visits"] == 3
    assert out["post_peak"] is not None
    expected_post = 3 * int(np.sum(amp >= out["peak_mA"]))
    assert out["post_peak"]["n_points"] == expected_post
    assert out["post_peak"]["slope_per_mA"] < 0, "past the peak the pooled relationship must fall"


def test_pooled_too_few_points_says_not_assessed():
    out = WV.amplitude_response_shape_pooled([0.0, 1.0, 2.0], [10.0, 20.0, 15.0], ["a", "a", "a"])
    assert out["curves"] is False
    assert out["verdict"].startswith("not assessed")
    assert np.isnan(out["p_curvature"])
    assert out["pooled_direction"] == "not assessed"
    assert np.isnan(out["pooled_slope_per_mA"])


def test_pooled_direction_reads_a_clear_rising_slope_with_visit_baselines_removed():
    """The pooled straight-line slope (added for the closed-loop consistency check, PI request
    2026-09-08) must read a real rising relationship correctly even when three visits sit at very
    different baseline power levels -- the same per-visit-intercept design the curvature test
    above already uses, so a baseline difference alone must not be read as a rising slope.
    """
    amp = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    rng = np.random.RandomState(5)
    xs, ys, vs = [], [], []
    for i, baseline in enumerate([0.0, 300.0, -150.0]):
        xs.append(amp)
        ys.append(baseline + 40.0 * amp + rng.normal(0, 3.0, amp.size))
        vs.append([f"visit{i}"] * amp.size)
    x, y, v = np.concatenate(xs), np.concatenate(ys), np.concatenate(vs)

    out = WV.amplitude_response_shape_pooled(x, y, v)
    assert out["pooled_slope_per_mA"] > 0
    assert out["pooled_slope_p"] < 0.05
    assert out["pooled_direction"] == "band power rises as current rises"


def test_pooled_direction_reads_a_clear_falling_slope():
    amp = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    rng = np.random.RandomState(6)
    xs, ys, vs = [], [], []
    for i, baseline in enumerate([0.0, 300.0, -150.0]):
        xs.append(amp)
        ys.append(baseline - 40.0 * amp + rng.normal(0, 3.0, amp.size))
        vs.append([f"visit{i}"] * amp.size)
    x, y, v = np.concatenate(xs), np.concatenate(ys), np.concatenate(vs)

    out = WV.amplitude_response_shape_pooled(x, y, v)
    assert out["pooled_slope_per_mA"] < 0
    assert out["pooled_slope_p"] < 0.05
    assert out["pooled_direction"] == "band power falls as current rises"


def test_pooled_direction_says_no_movement_when_flat():
    amp = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    rng = np.random.RandomState(7)
    xs, ys, vs = [], [], []
    for i, baseline in enumerate([0.0, 300.0, -150.0]):
        xs.append(amp)
        ys.append(baseline + rng.normal(0, 3.0, amp.size))
        vs.append([f"visit{i}"] * amp.size)
    x, y, v = np.concatenate(xs), np.concatenate(ys), np.concatenate(vs)

    out = WV.amplitude_response_shape_pooled(x, y, v)
    assert out["pooled_direction"] == "no straight-line movement detected across the currents tested"


def test_pooling_across_visits_clears_the_single_visit_floor():
    """Three visits with three points each -- each one alone is far below the single-visit
    function's own eight-point floor -- combine to nine pooled points, enough to be assessed
    (PI decision 55, and the reason open item 18 is resolved by this design)."""
    one_visit_amp = np.array([1.0, 2.0, 3.0])
    one_visit_power = np.array([50.0, 80.0, 60.0])
    single = WV.amplitude_response_shape(one_visit_amp, one_visit_power)
    assert single["verdict"].startswith("not assessed"), "fixture is wrong: one visit alone must fail"

    rng = np.random.RandomState(4)
    xs, ys, vs = [], [], []
    for i in range(3):
        xs.append(one_visit_amp)
        ys.append(one_visit_power + rng.normal(0, 2.0, 3))
        vs.append([f"v{i}"] * 3)
    out = WV.amplitude_response_shape_pooled(np.concatenate(xs), np.concatenate(ys),
                                             np.concatenate(vs))
    assert out["n"] == 9
    assert out["n_visits"] == 3
    assert np.isfinite(out["p_curvature"]), "pooling should have let this be assessed at all"


def test_the_step_summary_is_the_average_and_the_middle_value_stays_available():
    """PI decision 2026-09-06: average the settled values rather than take the middle one.

    Uses a block with a few large upward excursions, which is what real 1-second epochs contain --
    the 99.5th percentile is about 7 times the median. The mean must be pulled up by them and the
    median must not, because that difference is the whole reason the choice matters.
    """
    excl = WV.RAMP_EXCLUDE_S
    t = np.arange(0.0, 200.0, 1.0)
    p = np.full((t.size, 1), 10.0)
    p[(t >= excl + 5) & (t < excl + 8), 0] = 200.0        # three big excursions inside the plateau
    window = excl + 60.0

    mean_out = WV.step_settled_stats([0.0], [window], t, p)
    med_out = WV.step_settled_medians([0.0], [window], t, p)
    assert mean_out[0][0, 0] > med_out[0][0, 0], (
        "the mean must be pulled up by the excursions and the median must not")
    assert np.isclose(med_out[0][0, 0], 10.0)
    # identical tiles behind both, so the counts cannot differ
    assert mean_out[1][0] == med_out[1][0]

    both = WV.step_settled_stats([0.0], [window], t, p, return_both=True)
    assert len(both) == 4
    assert np.isclose(both[0][0, 0], mean_out[0][0, 0])
    assert np.isclose(both[3][0, 0], med_out[0][0, 0]), "the fourth return is the other summary"
    assert WV.STEP_SUMMARY == "mean"


# Restored 2026-09-12: the audit made their deletion conditional on a design decision the PI
# has not made (the stopping rule's one-item history; the ramp clip of commit 790ed21), so
# they stay until he does.
def test_the_ramp_exclusion_covers_the_longest_ramp_actually_observed():
    """The exclusion exists to remove the ramp, so it must not be shorter than the ramp.

    Measured from the device's own 2 Hz amplitude record on RCS08's 2026-08-18 visit: 6.5 s median,
    17.5 s at most across both stimulators. This asserts the relationship rather than the numbers,
    so a future measurement can move both without the test becoming a lie.
    """
    assert WV.RAMP_EXCLUDE_S >= WV.LONGEST_OBSERVED_RAMP_S, (
        "the ramp exclusion is shorter than the longest ramp measured from the device")
    # And it must not drift back to a figure that discards most of a 57 s hold for nothing.
    assert WV.RAMP_EXCLUDE_S <= 30.0, (
        "an exclusion this long throws away most of the settled signal; see the provenance block")


def test_the_look_back_window_is_clipped_at_the_measured_end_of_the_ramp():
    """PI, 2026-09-06: render the heat maps off the measured ramp.

    The 30-second look-back assumes the setting was held longer than 30 s. Across RCS08's record
    that fails on 188 of 600 plateaus, where the look-back reaches back into the stretch in which
    the current was still moving. This pins BOTH that the clip works and that it changes nothing
    where the hold is long, because the second half is what makes it a clip and not a new rule.
    """
    tt = np.arange(0.0, 500.0, 3.0)
    tp = np.full((tt.size, 2), 100.0)
    t0 = np.array([100.0, 200.0, 300.0])
    amp = np.array([1.0, 2.0, 3.0])          # rising, so no setting is refused for direction
    t_end = np.array([200.0, 300.0, 480.0])
    # Setting 1 is held from 200 to 300 but the current is still MOVING until 285, so the last
    # 30 s (270-300) is mostly ramp. Make that stretch loud so an unclipped average must differ.
    ramp_end = np.array([115.0, 285.0, 315.0])
    tp[(tt >= 270.0) & (tt < 290.0), :] = 900.0

    unclipped, Tu = WV.mean_power_before_next_change(t0, amp, tt, tp, step_end_t=t_end)
    clipped, Tc = WV.mean_power_before_next_change(t0, amp, tt, tp, step_end_t=t_end,
                                                   ramp_end_t=ramp_end, ramp_margin_s=5.0)
    assert bool(Tu.iloc[1]["accepted"]), "the fixture must ACCEPT setting 1 unclipped, or the " \
                                        "clip is never exercised and the test proves nothing"

    # THE CLIP DID SOMETHING: either the value changed, or the setting is now refused for having
    # too little signal left once the ramp is excluded.
    row = Tc.iloc[1]
    if bool(row["accepted"]):
        assert unclipped[1, 0] != clipped[1, 0], (
            "the unclipped window averaged the loud ramp; the clipped one must not")
        assert clipped[1, 0] == pytest.approx(100.0), "only the settled level should remain"
        assert row["window_start_s"] >= 285.0 + 5.0 - 1e-9, "the window must start after the ramp"
    else:
        why = str(row["refusal_reason"])
        assert "finished moving" in why, why

    # WHERE THE HOLD IS LONG THE CLIP CHANGES NOTHING. Setting 2 runs 300 to 480 with the current
    # settled by 315, so its last 30 s is nowhere near the ramp and the two rules must agree.
    assert np.allclose(unclipped[2, :], clipped[2, :], equal_nan=True), (
        "where the hold is longer than the window the clip must change nothing")
    assert bool(Tu.iloc[2]["accepted"]) and bool(Tc.iloc[2]["accepted"])

    # PASSING None REPRODUCES THE ORIGINAL BEHAVIOUR BIT FOR BIT on every setting.
    again, _ = WV.mean_power_before_next_change(t0, amp, tt, tp, step_end_t=t_end, ramp_end_t=None)
    assert np.allclose(again, unclipped, equal_nan=True)

    # A wrong-length ramp list is refused rather than silently broadcast.
    with pytest.raises(ValueError, match="one measured ramp end per setting"):
        WV.mean_power_before_next_change(t0, amp, tt, tp, step_end_t=t_end,
                                         ramp_end_t=np.array([115.0]))
