"""FDA SSED P960009/S478 Table 2 ranges, independently expressed in seconds here."""
import pytest

from ClosedLoopDeployment import constraints as C


@pytest.mark.parametrize('mode,maximum_s', [('dual', 360), ('single', 30)])
@pytest.mark.parametrize('fraction,expected', [(-.01, False), (0, True), (.5, True), (1, True), (1.01, False)])
def test_onset_selection_limits_not_trial_settings(mode, maximum_s, fraction, expected):
    onset_ms = maximum_s * fraction * 1000
    candidate = {'threshold_mode': mode, 'onset_duration_ms': onset_ms,
                 'declared_mode_timing': {'onset_ms_adaptive': onset_ms}}
    assert C._p_d20(candidate, {}) is expected
    assert C._p_d21(candidate, {}) is expected


@pytest.mark.parametrize('key', ['transition_up_s', 'transition_down_s'])
@pytest.mark.parametrize('value,expected', [(0, False), (.249, False), (.25, True), (4, True), (1800, True), (1800.001, False)])
@pytest.mark.parametrize('mode', ['dual', 'single'])
def test_both_transition_durations_use_seconds(key, value, expected, mode):
    assert C._p_d20({'threshold_mode': mode, 'declared_mode_timing': {key: value}}, {}) is expected


@pytest.mark.parametrize('value', [None, True, False, 'invalid', {}, [], float('nan'), float('inf'), -float('inf'), 10**400])
def test_invalid_or_missing_timing_remains_unknown(value):
    c = {'threshold_mode': 'dual', 'onset_duration_ms': value,
         'declared_mode_timing': {'onset_ms_adaptive': value}}
    assert C._p_d20(c, {}) is None
    assert C._p_d21(c, {}) is None


@pytest.mark.parametrize('candidate', [None, {}, {'threshold_mode': 'invalid'}, {'threshold_mode': 'single_inverse'},
                                     {'threshold_mode': 'dual'}, {'threshold_mode': 'dual', 'declared_mode_timing': []},
                                     {'threshold_mode': 'dual', 'declared_mode_timing': {}}])
def test_missing_mode_or_declarations_do_not_pass(candidate):
    assert C._p_d20(candidate, {}) is None
    assert C._p_d21(candidate, {}) is None


def test_sensing_only_inverse_has_no_therapy_onset_range():
    c = {'threshold_mode': 'single_inverse', 'onset_duration_ms': 200,
         'declared_mode_timing': {'onset_ms_adaptive': 200}}
    assert C._p_d20(c, {}) is None
    assert C._p_d21(c, {}) is None


@pytest.mark.parametrize('key', ['averaging_ms_adaptive', 'detection_blanking_ms_adaptive', 'adaptive_startup_delay', 'fft_points', 'unrecognized'])
def test_unverified_keys_never_turn_a_partial_check_into_a_pass(key):
    for declared in ({key: 30}, {'transition_up_s': 4, key: 30}, {key: 30, 'transition_up_s': 4}):
        assert C._p_d20({'threshold_mode': 'dual', 'declared_mode_timing': declared}, {}) is None
    for declared in ({key: 30, 'transition_down_s': 2000}, {'transition_down_s': 2000, key: 30}):
        assert C._p_d20({'threshold_mode': 'dual', 'declared_mode_timing': declared}, {}) is False


def test_supported_adjusted_values_and_input_aliases():
    c = {'threshold_mode': 'Dual Threshold', 'onset_duration_ms': '30000',
         'declared_mode_timing': {'onset_ms_adaptive': '30000', 'transition_up_s': 4, 'transition_down_s': 4}}
    assert C._p_d20(c, {}) is True
    assert C._p_d21(c, {}) is True
    assert C.ONSET_DURATION_RANGE_MS_ADAPT_PD == {'dual': (1200., 2000.), 'single': (200., 500.)}
    assert C.THRESHOLD_MODE_TABLE['dual']['onset_ms_adaptive'] == 1200


def test_evaluator_retains_advisory_severity_and_source_provenance():
    rules = [r for r in C.RULES if r.rule_id in ('D20', 'D21')]
    assert len(rules) == 2
    assert all(r.severity == 'advisory' and 'FDA' in r.source and 'Table 2 p. 8' in r.page for r in rules)
    c = {'threshold_mode': 'dual', 'onset_duration_ms': 30_000, 'declared_mode_timing': {'transition_up_s': 4}}
    report = C.check_eligibility(c, {}, rules=rules)
    assert report.eligible and report.checked == 2 and not report.failures and not report.unknowns
    c.update(onset_duration_ms=400_000, declared_mode_timing={'transition_up_s': 2000})
    report = C.check_eligibility(c, {}, rules=rules)
    assert report.eligible and {x['rule_id'] for x in report.advisories} == {'D20', 'D21'}
    assert all(x['kind'] == 'advisory_failed' for x in report.advisories)
