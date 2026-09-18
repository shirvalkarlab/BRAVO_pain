"""Synthetic upstream amplitude-window and response-shape regression tests."""
import numpy as np
import pytest
from StimOptimizer.routines import within_visit as WV
LADDER_BANDS = 4

def _ladder(currents, *, hold_s=60.0, t_start=1700000000.0, rate=55.0):
    t = float(t_start)
    (t0, rows) = ([], [])
    for c in currents:
        t0.append(t)
        rows.append(rate)
        t += float(hold_s)
    return (np.asarray(t0), np.asarray(currents, dtype=float), np.asarray(rows, dtype=float))

def _pieces(t0, currents, hold_s=60.0, *, per_mA=10.0, base=100.0, piece_s=3.0, gap_from=None):
    (ts, ps) = ([], [])
    for (i, (a, c)) in enumerate(zip(t0, currents)):
        n = int(hold_s // piece_s)
        keep = range(n) if gap_from != i else range(2)
        for j in keep:
            ts.append(a + j * piece_s)
            ps.append(np.full(LADDER_BANDS, base + per_mA * c))
    o = np.argsort(np.asarray(ts, dtype=float))
    return (np.asarray(ts, dtype=float)[o], np.vstack(ps)[o])

def test_the_number_is_the_mean_of_the_ten_pieces_in_the_last_thirty_seconds():
    (t0, amp, rate) = _ladder([1.0, 1.1, 1.2, 1.3])
    (tt, tp) = _pieces(t0, amp)
    (P, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    acc = T[T.accepted]
    assert list(acc.current_mA) == [1.1, 1.2]
    assert list(acc.n_chunks_found) == [10, 10]
    assert np.allclose(P[1, :], 111.0)
    assert np.allclose(P[2, :], 112.0)
    assert np.all(~np.isfinite(P[0, :])) and np.all(~np.isfinite(P[3, :]))

def test_the_window_ends_where_the_next_setting_starts_and_never_reaches_past_it():
    (t0, amp, rate) = _ladder([1.0, 2.0, 3.0, 4.0])
    (tt, tp) = _pieces(t0, amp)
    (_, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    r = T.iloc[1]
    assert r.t_next_change_s == t0[2]
    assert r.window_start_s == t0[2] - WV.PRE_CHANGE_WINDOW_S
    assert r.window_start_s >= t0[1]
    assert not r.window_shortened_by_setting_start

def test_a_current_that_drops_to_zero_and_climbs_again_does_not_carry_the_earlier_ladder_across():
    (t0, amp, rate) = _ladder([1.0, 2.0, 3.0, 0.0, 0.5, 1.0, 1.5])
    (tt, tp) = _pieces(t0, amp)
    (_, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    got = dict(zip(T.setting_index, T.accepted))
    assert got[2] is True or bool(got[2])
    assert not bool(got[3])
    assert bool(T.iloc[2].next_change_is_a_further_rise) is False
    assert bool(got[4])
    assert np.isclose(T.iloc[4].window_start_s, t0[5] - WV.PRE_CHANGE_WINDOW_S)
    assert T.iloc[4].window_start_s > t0[3]

def test_a_setting_reached_by_turning_the_current_down_is_refused_with_a_reason():
    (t0, amp, rate) = _ladder([1.0, 3.0, 2.0, 2.5])
    (tt, tp) = _pieces(t0, amp)
    (_, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    row = T.iloc[2]
    assert not row.accepted
    assert 'did not go up' in row.refusal_reason
    loose = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate, require_rise_into_setting=False)[1]
    assert bool(loose.iloc[2].accepted)

def test_fewer_than_ten_pieces_gets_no_number_and_reports_the_count_it_actually_found():
    (t0, amp, rate) = _ladder([1.0, 2.0, 3.0, 4.0])
    (tt, tp) = _pieces(t0, amp, gap_from=2)
    (P, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    row = T.iloc[2]
    assert row.n_chunks_found == 0
    assert not row.accepted
    assert 'three second pieces' in row.refusal_reason
    assert np.all(~np.isfinite(P[2, :]))
    assert bool(T.iloc[1].accepted)

def test_a_setting_held_briefly_has_its_window_cut_at_its_own_start_not_topped_up():
    t0 = np.array([0.0, 100.0, 112.0, 200.0]) + 1700000000.0
    amp = np.array([1.0, 2.0, 3.0, 4.0])
    rate = np.full(4, 55.0)
    ends = np.r_[t0[1:], t0[-1] + 100.0]
    (ts, ps) = ([], [])
    for (a, e, c) in zip(t0, ends, amp):
        j = 0
        while a + j * 3.0 < e:
            ts.append(a + j * 3.0)
            ps.append(np.full(LADDER_BANDS, 100.0 + 10.0 * c))
            j += 1
    o = np.argsort(np.asarray(ts))
    (tt, tp) = (np.asarray(ts)[o], np.vstack(ps)[o])
    (_, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    row = T.iloc[1]
    assert row.window_shortened_by_setting_start
    assert row.window_start_s == t0[1]
    assert row.n_chunks_found == 4
    assert not row.accepted
    assert bool(T.iloc[2].accepted)
    assert int(T.iloc[2].n_chunks_found) == 10

def test_two_stimulation_rates_are_never_treated_as_one_ladder():
    (t0, amp, _) = _ladder([1.0, 2.0, 3.0, 1.0, 2.0, 3.0])
    block = np.array([55.0, 55.0, 55.0, 10.0, 10.0, 10.0])
    (tt, tp) = _pieces(t0, amp)
    (_, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=block)
    assert not bool(T.iloc[3].accepted)
    assert 'did not go up' in T.iloc[3].refusal_reason
    assert not bool(T.iloc[2].accepted)
    assert 'not known' in T.iloc[2].refusal_reason

def test_the_average_is_in_the_units_it_was_given_and_takes_no_logarithm():
    (t0, amp, rate) = _ladder([1.0, 2.0, 3.0, 4.0])
    (tt, tp) = _pieces(t0, amp, base=150.0, per_mA=25.0)
    (P, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    assert np.allclose(P[1, :], 200.0)
    assert np.allclose(P[2, :], 225.0)
    assert P[1, 0] > 10.0

def test_it_complains_rather_than_guessing_when_the_pieces_do_not_line_up():
    (t0, amp, rate) = _ladder([1.0, 2.0, 3.0])
    (tt, tp) = _pieces(t0, amp)
    with pytest.raises(ValueError, match='current_mA'):
        WV.mean_power_before_next_change(t0, amp[:2], tt, tp, block=rate)
    with pytest.raises(ValueError, match='sorted ascending'):
        WV.mean_power_before_next_change(t0, amp, tt[::-1], tp, block=rate)
    with pytest.raises(ValueError, match='n_bands'):
        WV.mean_power_before_next_change(t0, amp, tt, tp[:5, :], block=rate)

def test_the_older_median_rule_is_still_there_and_still_does_its_own_thing():
    assert hasattr(WV, 'step_settled_medians') and hasattr(WV, 'mean_power_before_next_change')
    (t0, amp, rate) = _ladder([1.0, 2.0, 3.0, 4.0], hold_s=120.0)
    (tt, tp) = _pieces(t0, amp, hold_s=120.0)
    (med, cnt, kept) = WV.step_settled_medians(t0, np.full(4, 120.0), tt, tp)
    assert len(kept) == 4
    (P, T) = WV.mean_power_before_next_change(t0, amp, tt, tp, block=rate)
    assert int(T.accepted.sum()) == 2

def test_a_peaked_response_is_reported_as_peaked_and_not_as_flat():
    amp = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5] * 2, dtype=float)
    power = 400.0 - 90.0 * (amp - 1.75) ** 2
    rng = np.random.RandomState(0)
    power = power + rng.normal(0, 4.0, size=power.size)
    lin_slope = np.polyfit(amp, power, 1)[0]
    assert abs(lin_slope) < 12.0, 'fixture is wrong: the linear slope should be near zero'
    out = WV.amplitude_response_shape(amp, power)
    assert out['curves'] is True
    assert out['peaks_inside'] is True
    assert 1.5 < out['peak_mA'] < 2.0
    assert out['p_curvature'] < 0.01
    assert out['r2_linear'] < 0.15
    assert out['r2_quadratic'] > 0.85
    assert 'peaking at' in out['verdict']
    assert 'NO RESPONSE' in out['verdict']
    assert 'HARMONIC' not in out['verdict']

def test_a_straight_relationship_is_not_reported_as_curved():
    amp = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5] * 2, dtype=float)
    rng = np.random.RandomState(1)
    power = 100.0 + 40.0 * amp + rng.normal(0, 5.0, size=amp.size)
    out = WV.amplitude_response_shape(amp, power)
    assert out['curves'] is False
    assert out['peaks_inside'] is False
    assert np.isnan(out['peak_mA'])
    assert out['r2_linear'] > 0.85
    assert 'no curvature' in out['verdict']

def test_too_few_points_says_not_assessed_rather_than_guessing():
    out = WV.amplitude_response_shape([0.0, 1.0, 2.0], [10.0, 20.0, 15.0])
    assert out['curves'] is False
    assert out['verdict'].startswith('not assessed')
    assert np.isnan(out['p_curvature'])
    flat = WV.amplitude_response_shape([0.0, 1.0, 2.0, 3.0] * 3, [5.0] * 12)
    assert flat['verdict'].startswith('not assessed')

def test_pooling_without_visit_adjustment_would_manufacture_a_fake_peak():
    rng = np.random.RandomState(2)
    amp_a = np.array([0.5, 1.0, 1.5] * 4)
    amp_b = np.array([1.5, 2.0, 2.5] * 4)
    amp_c = np.array([2.5, 3.0, 3.5] * 4)
    amp = np.concatenate([amp_a, amp_b, amp_c])
    power = np.concatenate([100.0 + rng.normal(0, 3.0, amp_a.size), 200.0 + rng.normal(0, 3.0, amp_b.size), 100.0 + rng.normal(0, 3.0, amp_c.size)])
    visit = np.array(['A'] * amp_a.size + ['B'] * amp_b.size + ['C'] * amp_c.size)
    naive = WV.amplitude_response_shape(amp, power)
    assert naive['curves'] is True, 'fixture is wrong: the naive pooled fit should look curved'
    out = WV.amplitude_response_shape_pooled(amp, power, visit)
    assert out['curves'] is False, 'a per-visit baseline shift must not be reported as curvature'
    assert out['n_visits'] == 3
    assert out['post_peak'] is None

def test_a_genuine_pooled_peak_is_detected_with_visit_baselines_removed():
    amp = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
    shape = 400.0 - 90.0 * (amp - 1.75) ** 2
    rng = np.random.RandomState(3)
    (xs, ys, vs) = ([], [], [])
    for (i, baseline) in enumerate([0.0, 150.0, -80.0]):
        xs.append(amp)
        ys.append(shape + baseline + rng.normal(0, 4.0, amp.size))
        vs.append([f'visit{i}'] * amp.size)
    (x, y, v) = (np.concatenate(xs), np.concatenate(ys), np.concatenate(vs))
    out = WV.amplitude_response_shape_pooled(x, y, v)
    assert out['curves'] is True
    assert out['peaks_inside'] is True
    assert 1.5 < out['peak_mA'] < 2.0
    assert out['n_visits'] == 3
    assert out['post_peak'] is not None
    expected_post = 3 * int(np.sum(amp >= out['peak_mA']))
    assert out['post_peak']['n_points'] == expected_post
    assert out['post_peak']['slope_per_mA'] < 0, 'past the peak the pooled relationship must fall'

def test_pooled_too_few_points_says_not_assessed():
    out = WV.amplitude_response_shape_pooled([0.0, 1.0, 2.0], [10.0, 20.0, 15.0], ['a', 'a', 'a'])
    assert out['curves'] is False
    assert out['verdict'].startswith('not assessed')
    assert np.isnan(out['p_curvature'])
    assert out['pooled_direction'] == 'not assessed'
    assert np.isnan(out['pooled_slope_per_mA'])

def test_pooled_direction_reads_a_clear_rising_slope_with_visit_baselines_removed():
    amp = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    rng = np.random.RandomState(5)
    (xs, ys, vs) = ([], [], [])
    for (i, baseline) in enumerate([0.0, 300.0, -150.0]):
        xs.append(amp)
        ys.append(baseline + 40.0 * amp + rng.normal(0, 3.0, amp.size))
        vs.append([f'visit{i}'] * amp.size)
    (x, y, v) = (np.concatenate(xs), np.concatenate(ys), np.concatenate(vs))
    out = WV.amplitude_response_shape_pooled(x, y, v)
    assert out['pooled_slope_per_mA'] > 0
    assert out['pooled_slope_p'] < 0.05
    assert out['pooled_direction'] == 'band power rises as current rises'

def test_pooled_direction_reads_a_clear_falling_slope():
    amp = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    rng = np.random.RandomState(6)
    (xs, ys, vs) = ([], [], [])
    for (i, baseline) in enumerate([0.0, 300.0, -150.0]):
        xs.append(amp)
        ys.append(baseline - 40.0 * amp + rng.normal(0, 3.0, amp.size))
        vs.append([f'visit{i}'] * amp.size)
    (x, y, v) = (np.concatenate(xs), np.concatenate(ys), np.concatenate(vs))
    out = WV.amplitude_response_shape_pooled(x, y, v)
    assert out['pooled_slope_per_mA'] < 0
    assert out['pooled_slope_p'] < 0.05
    assert out['pooled_direction'] == 'band power falls as current rises'

def test_pooled_direction_says_no_movement_when_flat():
    amp = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    rng = np.random.RandomState(7)
    (xs, ys, vs) = ([], [], [])
    for (i, baseline) in enumerate([0.0, 300.0, -150.0]):
        xs.append(amp)
        ys.append(baseline + rng.normal(0, 3.0, amp.size))
        vs.append([f'visit{i}'] * amp.size)
    (x, y, v) = (np.concatenate(xs), np.concatenate(ys), np.concatenate(vs))
    out = WV.amplitude_response_shape_pooled(x, y, v)
    assert out['pooled_direction'] == 'no straight-line movement detected across the currents tested'

def test_pooling_across_visits_clears_the_single_visit_floor():
    one_visit_amp = np.array([1.0, 2.0, 3.0])
    one_visit_power = np.array([50.0, 80.0, 60.0])
    single = WV.amplitude_response_shape(one_visit_amp, one_visit_power)
    assert single['verdict'].startswith('not assessed'), 'fixture is wrong: one visit alone must fail'
    rng = np.random.RandomState(4)
    (xs, ys, vs) = ([], [], [])
    for i in range(3):
        xs.append(one_visit_amp)
        ys.append(one_visit_power + rng.normal(0, 2.0, 3))
        vs.append([f'v{i}'] * 3)
    out = WV.amplitude_response_shape_pooled(np.concatenate(xs), np.concatenate(ys), np.concatenate(vs))
    assert out['n'] == 9
    assert out['n_visits'] == 3
    assert np.isfinite(out['p_curvature']), 'pooling should have let this be assessed at all'

def test_the_step_summary_is_the_average_and_the_middle_value_stays_available():
    excl = WV.RAMP_EXCLUDE_S
    t = np.arange(0.0, 200.0, 1.0)
    p = np.full((t.size, 1), 10.0)
    p[(t >= excl + 5) & (t < excl + 8), 0] = 200.0
    window = excl + 60.0
    mean_out = WV.step_settled_stats([0.0], [window], t, p)
    med_out = WV.step_settled_medians([0.0], [window], t, p)
    assert mean_out[0][0, 0] > med_out[0][0, 0], 'the mean must be pulled up by the excursions and the median must not'
    assert np.isclose(med_out[0][0, 0], 10.0)
    assert mean_out[1][0] == med_out[1][0]
    both = WV.step_settled_stats([0.0], [window], t, p, return_both=True)
    assert len(both) == 4
    assert np.isclose(both[0][0, 0], mean_out[0][0, 0])
    assert np.isclose(both[3][0, 0], med_out[0][0, 0]), 'the fourth return is the other summary'
    assert WV.STEP_SUMMARY == 'mean'


def test_measured_ramps_group_increments_and_keep_only_long_holds():
    # Two close increments form one ramp; a late short hold is not a plateau.
    out = WV.ramp_windows_from_amplitude([90, 0, 5, 8, 50, 85, np.nan],
                                          [3, 1, 1.5, 2, 2.5, 3, 4])
    assert out.n_increments.tolist() == [2, 1]
    assert out.ramp_end.tolist() == [8, 50]
    assert out.hold_s.tolist() == [42, 35]
    assert out.mA_from.tolist() == [1, 2]
    assert out.mA_to.tolist() == [2, 2.5]
    assert WV.ramp_windows_from_amplitude([0, 10, 30], [2, 2, 2]).empty
    assert WV.ramp_windows_from_amplitude([0, np.nan], [1, 2]).empty
    with pytest.raises(ValueError, match='must match'):
        WV.ramp_windows_from_amplitude([0, 1], [1])
    n = WV.MAX_INCREMENTS_PER_RAMP + 2
    with pytest.raises(WV.ContinuousAmplitudeError, match='never holds still'):
        WV.ramp_windows_from_amplitude(np.arange(n), np.arange(n))


def test_current_rise_requires_finite_neighbor_in_same_block():
    into, following = WV.rising_current_settings([1, 2, 2, np.nan, 3, 4, 5],
                                                 ['a', 'a', 'a', 'a', 'a', 'b', 'b'])
    assert into.tolist() == [False, True, False, False, False, False, True]
    assert following.tolist() == [True, False, False, False, False, True, False]
    with pytest.raises(ValueError, match='block has'):
        WV.rising_current_settings([1, 2], ['a'])


@pytest.mark.parametrize('override,error', [
    ({'step_end_t': [120]}, 'one entry'),
    ({'window_s': 0}, 'positive and finite'),
    ({'window_s': np.nan}, 'positive and finite'),
    ({'ramp_end_t': [20]}, 'one measured ramp'),
    ({'ramp_end_t': [20, 80], 'ramp_margin_s': -1}, 'not negative'),
    ({'ramp_end_t': [20, 80], 'ramp_margin_s': np.inf}, 'not negative'),
])
def test_prechange_window_rejects_invalid_controls(override, error):
    with pytest.raises(ValueError, match=error):
        WV.mean_power_before_next_change([0, 60], [1, 2], np.arange(0, 120, 3),
                                         np.ones((40, 2)), **override)


def test_measured_ramp_clips_window_and_refuses_insufficient_settled_chunks():
    tt = np.arange(0, 180, 3)
    power = np.column_stack([tt, tt * 2])
    p, table = WV.mean_power_before_next_change([0, 60, 120], [1, 2, 3], tt, power,
        step_end_t=[60, 120, 180], ramp_end_t=[0, 105, np.nan], ramp_margin_s=5)
    assert table.iloc[1].window_start_s == 110
    assert table.iloc[1].n_chunks_found == 3
    assert 'finished moving' in table.iloc[1].refusal_reason
    assert np.isnan(p[1]).all()
    assert table.iloc[2].accepted
    np.testing.assert_allclose(p[2], power[(tt >= 150) & (tt < 180)].mean(axis=0))


def test_missing_tiles_do_not_count_towards_required_chunks_and_empty_settings_work():
    tt = np.arange(0, 120, 3)
    power = np.ones((40, 2)); power[31] = np.nan
    p, table = WV.mean_power_before_next_change([0, 60], [1, 2], tt, power,
                                              step_end_t=[60, 120])
    assert table.iloc[1].n_chunks_found == 9
    assert not table.iloc[1].accepted and np.isnan(p[1]).all()
    p, table = WV.mean_power_before_next_change([], [], [], np.empty((0, 2)))
    assert p.shape == (0, 2) and table.empty


def test_shape_validation_does_not_infer_curvature_from_constant_or_confounded_data():
    x = np.tile([1., 2., 3.], 4)
    with pytest.raises(ValueError, match='must match'):
        WV.amplitude_response_shape(x, x[:-1])
    assert 'does not vary' in WV.amplitude_response_shape(x, np.ones(12))['verdict']
    with pytest.raises(ValueError, match='must'):
        WV.amplitude_response_shape_pooled(x, x[:-1], np.zeros(12))
    assert 'does not vary' in WV.amplitude_response_shape_pooled(x, np.ones(12), np.zeros(12))['verdict']
    confounded = WV.amplitude_response_shape_pooled(np.repeat([1., 2., 3.], 4),
                        np.arange(12.), np.repeat(['a', 'b', 'c'], 4))
    assert 'not enough independent' in confounded['verdict']
    with pytest.raises(ValueError, match='summary'):
        WV.step_settled_stats([0], [120], [30, 60], np.ones((2, 1)), summary='unsupported')
