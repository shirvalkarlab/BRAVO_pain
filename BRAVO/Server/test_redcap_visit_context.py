"""Testing-day context preserves reviewed QC and stays outside routine analysis."""
import copy
import base64
import json
import zlib
import datetime as dt
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from modules import RedcapVisitContext as visits
from modules import RCS08SurveyProcessing as daily
from modules.RedcapTimeline import METRICS, TimelineNotReady
from Server.test_qc_runtime import rules, row, replace_rule

DIGEST = 'a' * 64


def canonical_row(**changes):
    value = dict(stim_testing_date=True, include_in_analysis=False,
                 exclusion_reason=visits.REASON, survey_start='2026-01-01T10:00:00-08:00',
                 study_stage='stage_2', source_event='visit', source_instrument='daily',
                 repeat_instance='12', nrs_intensity=0)
    value.update(changes)
    return value


def form(publication):
    return NS(record=[{'processing': {'reviewed_sha256': DIGEST}, 'visit_context': publication}])


def publication(**changes):
    return visits.publish(pd.DataFrame([canonical_row(**changes)]), DIGEST)


def test_publication_only_relaxes_exact_testing_day_exclusion_and_does_not_mutate():
    canonical = pd.DataFrame([
        canonical_row(),
        canonical_row(repeat_instance='13', include_in_analysis=True),
        canonical_row(repeat_instance='14', stim_testing_date=False),
        canonical_row(repeat_instance='15', exclusion_reason='survey incomplete; ' + visits.REASON),
        canonical_row(repeat_instance='16', exclusion_reason='reviewed bad survey; ' + visits.REASON),
        canonical_row(repeat_instance='17', exclusion_reason='outside Stage 1-3; ' + visits.REASON),
        canonical_row(repeat_instance='18', exclusion_reason='missing survey start; ' + visits.REASON),
        canonical_row(repeat_instance='19', exclusion_reason=''),
        canonical_row(repeat_instance='20', exclusion_reason=None),
    ])
    before = canonical.copy(deep=True)
    routine_before = canonical.loc[canonical.include_in_analysis].copy(deep=True)
    result = visits.publish(canonical, DIGEST)
    pd.testing.assert_frame_equal(canonical, before)
    pd.testing.assert_frame_equal(canonical.loc[canonical.include_in_analysis], routine_before)
    assert result['eligible_surveys'] == 1
    assert set(result['metrics']) == {key for key, _, _ in METRICS}
    assert result['metrics']['nrs_intensity'] == [{
        'time': dt.datetime.fromisoformat('2026-01-01T10:00:00-08:00').timestamp(),
        'value': 0, 'record': 'visit:daily:12', 'source': 'Daily PRO · stimulation-testing day', 'phase':'stage_2'}]
    assert result['reviewed_sha256'] == DIGEST
    assert result['metrics']['mpq_standard_0_45'] == []


def test_missing_invalid_scores_never_filled_and_bounds_preserved():
    result = publication(mood_vas=None, vas_intensity=float('nan'), left_leg_vas_intensity=-1,
                         back_vas_intensity=101, mpq_standard_0_45=45, mpq_sens=33,
                         mpq_aff=12, relief_vas=100, mpq_throbbing=3, firey=False, tingly='bad')
    for key in ['mood_vas','vas_intensity','left_leg_vas_intensity','back_vas_intensity','firey','tingly']:
        assert result['metrics'][key] == []
    for key, value in [('mpq_standard_0_45',45),('mpq_sens',33),('mpq_aff',12),('relief_vas',100),('mpq_throbbing',3)]:
        assert result['metrics'][key][0]['value'] == value
    empty = visits.publish(pd.DataFrame([canonical_row(stim_testing_date=False)]), DIGEST)
    assert empty['eligible_surveys'] == 0
    assert all(not points for points in empty['metrics'].values())


def test_actual_qc_pipeline_reuses_corrected_time_and_exclusion_priority(rules):
    samples = [row(1, '2025-07-02 12:00:00', pain_nrs_s1_daily='7', pain_vas_s1_daily='0'),
               row(2, '2025-07-03 12:00:00'), row(3,'2025-07-03 13:00:00'),
               row(4,'2025-07-03 14:00:00'), row(5,'2025-07-05 12:00:00')]
    samples[1][daily.SURVEY_COMPLETE_COLUMN] = '1'
    replace_rule(rules, 'timestamp_corrections', [dict(repeat_instance=1,
        entered_survey_start='2025-07-02 12:00:00', corrected_survey_start='2025-07-03 10:30:00',
        correction_reason='synthetic verified time')])
    replace_rule(rules, 'survey_exclusions', [dict(repeat_instance=3,
        survey_start='2025-07-03 13:00:00', exclusion_reason='reviewed bad survey')])
    canonical = daily.canonicalize_rows(samples, rules)
    before = canonical.copy(deep=True)
    result = visits.publish(canonical, DIGEST)
    assert result['eligible_surveys'] == 2
    points = result['metrics']['nrs_intensity']
    assert [p['record'].split(':')[-1] for p in points] == ['1','4']
    assert points[0]['time'] == dt.datetime.fromisoformat('2025-07-03T10:30:00-07:00').timestamp()
    # Suspect default VAS zero remains absent, even on the relaxed testing day.
    assert len(result['metrics']['vas_intensity']) == 1
    assert result['metrics']['mpq_standard_0_45'] == []
    pd.testing.assert_frame_equal(canonical, before)
    assert canonical.loc[canonical.include_in_analysis, 'repeat_instance'].tolist() == [5]


def test_read_hash_compatibility_future_cutoff_and_no_source_mutation():
    result = publication()
    before = copy.deepcopy(result)
    when = result['metrics']['nrs_intensity'][0]['time']
    assert visits.read(form(result), when-1)['metrics']['nrs_intensity'] == []
    actual = visits.read(form(result), when)
    assert actual['available'] is True
    assert actual['metrics']['nrs_intensity'][0]['value'] == 0
    assert 'included in the display median; routine analysis exclusions are unchanged' in actual['message']
    assert result == before
    assert visits.read(NS(record=[{}]), when)['available'] is False


@pytest.mark.parametrize('change', [
    {'version':'old'}, {'reviewed_sha256':'b'*64}, {'exclusion_reason':'different'},
    {'metrics':{}},
])
def test_read_rejects_mismatched_publication(change):
    result = publication(); result.update(change)
    with pytest.raises(TimelineNotReady): visits.read(form(result), 1e12)


@pytest.mark.parametrize('field,value', [
    ('time',None),('time',float('nan')),('time','not-time'),
    ('value',None),('value',float('inf')),('value',True),('value',-1),('value',11),
])
def test_read_rejects_invalid_observations(field, value):
    result = publication(); result['metrics']['nrs_intensity'][0][field] = value
    with pytest.raises(TimelineNotReady): visits.read(form(result), 1e12)


@pytest.mark.parametrize('payload', [[], 'bad', 1])
def test_read_malformed_publication_fails_closed(payload):
    with pytest.raises(TimelineNotReady): visits.read(form(payload), 1e12)


@pytest.mark.parametrize('points', [None, {}, 'bad', [None], ['bad'], [[]]])
def test_read_malformed_points_fail_closed(points):
    result = publication(); result['metrics']['nrs_intensity'] = points
    with pytest.raises(TimelineNotReady): visits.read(form(result), 1e12)


def test_packed_publication_roundtrip_is_lossless_and_preserves_cutoff():
    original = publication(mood_vas=73.25, mpq_standard_0_45=31)
    before = copy.deepcopy(original)
    packed = visits.pack(original)
    assert isinstance(packed, str)
    assert len(packed) < len(json.dumps(original))
    assert json.loads(zlib.decompress(base64.b64decode(packed))) == original
    when = original['metrics']['nrs_intensity'][0]['time']
    assert visits.read(form(packed), when) == visits.read(form(original), when)
    assert visits.read(form(packed), when-1)['metrics']['nrs_intensity'] == []
    assert original == before
    with pytest.raises(ValueError): visits.pack({'value':float('nan')})


@pytest.mark.parametrize('packed', [
    '!not base64!',
    base64.b64encode(b'not zlib').decode(),
    base64.b64encode(zlib.compress(b'not json')).decode(),
    base64.b64encode(zlib.compress(b'\xff')).decode(),
    base64.b64encode(zlib.compress(b'[]')).decode(),
])
def test_damaged_or_wrong_packed_publication_fails_closed(packed):
    with pytest.raises(TimelineNotReady): visits.read(form(packed), 1e12)
