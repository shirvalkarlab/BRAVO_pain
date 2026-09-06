"""Synthetic, real-import tests of reviewed QC boundaries and source identities.

No private rules, patient files, networking, or persistent database are used.
"""
import copy
import csv
import datetime as dt
import hashlib
from contextlib import nullcontext
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from modules import RCS08SurveyProcessing as daily
from modules import RCS08HistoricalSurveys as historical
from modules.OURA import QualityControl as oura


def write_csv(path, fields, rows=()):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def rules(tmp_path):
    definitions = {
        'rcs08_study_stages.csv': (['stage', 'start_date', 'end_date'], [dict(stage='stage_1', start_date='2025-07-01', end_date='2025-07-31'), dict(stage='stage_2', start_date='2025-08-01', end_date='')]),
        'rcs08_stim_testing_dates.csv': (['date', 'stage', 'event_type', 'other_notes', 'location'], [dict(date='2025-07-03', stage='stage_1', event_type='testing', other_notes='', location='lab'), dict(date='2025-07-04', stage='screening', event_type='visit', other_notes='', location='lab')]),
        'rcs08_stage1_daily_timestamp_corrections.csv': (['repeat_instance', 'entered_survey_start', 'corrected_survey_start', 'correction_reason'], []),
        'rcs08_stage1_daily_survey_value_corrections.csv': (['repeat_instance', 'survey_start', 'canonical_column', 'entered_value', 'corrected_value', 'correction_reason'], []),
        'rcs08_stage1_daily_survey_exclusions.csv': (['repeat_instance', 'survey_start', 'exclusion_reason'], []),
    }
    for name, (fields, rows) in definitions.items():
        write_csv(tmp_path / name, fields, rows)
    return tmp_path


def row(instance=1, start='2025-07-02 12:00:00', **changes):
    result = dict.fromkeys(daily.DAILY_COLUMNS, '')
    result.update(record_id='RCS08', redcap_event_name='daily_arm_1', redcap_repeat_instrument=daily.DAILY_INSTRUMENT,
                  redcap_repeat_instance=str(instance), date_time_s1_daily=start, pain_nrs_s1_daily='0', pain_vas_s1_daily='0')
    result[daily.SURVEY_END_COLUMN] = str(pd.Timestamp(start) + pd.Timedelta(minutes=5)) if start else ''
    result[daily.SURVEY_COMPLETE_COLUMN] = '2'
    result.update(changes)
    return result


def replace_rule(rules, suffix, rows):
    path = rules / ('rcs08_stage1_daily_' + suffix + '.csv')
    fields = next(csv.reader(path.open()))
    write_csv(path, fields, rows)


def test_daily_source_selection_scores_missing_and_zero(rules):
    complete = row(1, **{name + '_s1_daily': '3' for name in daily.STANDARD_MPQ + daily.EXTRA_MPQ}, mpq_s1_daily='54')
    partial = row(2, throbbing_s1_daily='1', pain_nrs_s1_daily='7', pain_vas_s1_daily='0')
    missing = row(3, pain_nrs_s1_daily='6', pain_vas_s1_daily='0')
    root = row(4, redcap_repeat_instrument='', pain_nrs_s1_daily='10', pain_vas_s1_daily='100')
    other = row(5, record_id='OTHER')
    ignored = dict.fromkeys(daily.DAILY_COLUMNS, '')
    ignored['record_id'] = 'RCS08'
    original = copy.deepcopy([complete, partial, missing, root, other, ignored])
    result = daily.canonicalize_rows(original, rules).set_index('repeat_instance')
    assert len(result) == 4 and result.attrs['ignored_non_survey_rows'] == 1
    assert result.loc[1, ['mpq_sens', 'mpq_aff', 'mpq_standard_0_45', 'mpq_redcap_expanded_0_54']].tolist() == [33, 12, 45, 54]
    assert result.loc[2, 'mpq_standard_0_45'] == 1 and result.loc[2, 'mpq_shooting'] == 0
    assert pd.isna(result.loc[2, 'vas_intensity']) and result.loc[2, 'vas_default_zero_suspect']
    assert result.loc[3, 'vas_intensity'] == 0 and result.loc[3, 'mpq_block_missing']
    assert pd.isna(result.loc[3, 'mpq_standard_0_45'])
    assert result.loc[4, 'nrs_intensity'] == 10 and result.loc[4, 'vas_intensity'] == 100
    assert result.loc[1, 'source_event'] == 'daily_arm_1'
    assert result.loc[1, 'source_instrument'] == daily.DAILY_INSTRUMENT
    assert original == [complete, partial, missing, root, other, ignored]


def test_daily_date_stages_and_exclusion_reasons(rules):
    samples = [row(1, '2025-07-03 12:00:00'), row(2, '2025-07-04 12:00:00'), row(3, '2025-08-01 12:00:00'), row(4, '2025-06-30 12:00:00'), row(5, ''), row(6)]
    samples[-1][daily.SURVEY_COMPLETE_COLUMN] = '1'
    replace_rule(rules, 'survey_exclusions', [dict(repeat_instance=1, survey_start='2025-07-03 12:00:00', exclusion_reason='reviewed synthetic exclusion')])
    result = daily.canonicalize_rows(samples, rules).set_index('repeat_instance')
    assert result.loc[1, 'exclusion_reason'] == 'reviewed synthetic exclusion; intentional stimulation-testing day'
    assert result.loc[2, 'include_in_analysis'] and result.loc[3, 'study_stage'] == 'stage_2'
    assert result.loc[4, 'exclusion_reason'] == 'outside Stage 1-3'
    assert result.loc[5, 'exclusion_reason'] == 'missing survey start; outside Stage 1-3'
    assert result.loc[6, 'exclusion_reason'] == 'survey incomplete'


def test_reviewed_corrections_require_identity_and_recompute(rules):
    replace_rule(rules, 'timestamp_corrections', [dict(repeat_instance=1, entered_survey_start='2025-07-02 12:00:00', corrected_survey_start='2025-08-02 13:00:00', correction_reason='synthetic reference')])
    replace_rule(rules, 'survey_value_corrections', [dict(repeat_instance=1, survey_start='2025-08-02 13:00:00', canonical_column='mpq_throbbing', entered_value=3, corrected_value=0, correction_reason='synthetic review')])
    result = daily.canonicalize_rows([row(throbbing_s1_daily='3', mpq_s1_daily='3')], rules).iloc[0]
    assert result.survey_start == pd.Timestamp('2025-08-02 13:00:00')
    assert pd.isna(result.survey_end) and pd.isna(result.survey_duration_min)
    assert result.timestamp_source == 'qualtrics_correction' and result.study_stage == 'stage_2'
    assert result.mpq_sens == result.mpq_standard_0_45 == result.mpq_redcap_expanded_0_54 == 0
    assert result.repeat_instance == 1 and result.source_event == 'daily_arm_1'


@pytest.mark.parametrize('field,value,message', [
    ('pain_nrs_s1_daily', '-1', 'outside 0-10'), ('pain_nrs_s1_daily', '11', 'outside 0-10'),
    ('pain_vas_s1_daily', '101', 'outside 0-100'), ('left_leg_vas_s1_daily', '-1', 'outside 0-100'),
    ('back_vas_s1_daily', '101', 'outside 0-100'), ('relief_vas_s1_daily', '-1', 'outside 0-100'),
    ('mood_vas_s1_daily', '101', 'outside 0-100'), (daily.SURVEY_COMPLETE_COLUMN, '3', 'unexpected status'),
    ('throbbing_s1_daily', '0', 'standard MPQ'), ('firey_s1_daily', '4', 'extra MPQ'),
    (daily.SURVEY_END_COLUMN, '2025-07-02 11:59:00', 'ending before'),
])
def test_daily_invalid_scores_fail_before_publication(rules, field, value, message):
    with pytest.raises(ValueError, match=message):
        daily.canonicalize_rows([row(**{field: value})], rules)


def test_expanded_total_must_match(rules):
    with pytest.raises(ValueError, match='do not match'):
        daily.canonicalize_rows([row(throbbing_s1_daily='3', mpq_s1_daily='2')], rules)


@pytest.mark.parametrize('case,message', [('unexpected', 'unexpected REDCap instruments'), ('none', 'No stage_1'), ('duplicate', 'identity is not unique'), ('columns', 'missing daily survey columns'), ('rules', 'Required reviewed')])
def test_daily_export_contract_rejects_ambiguous_inputs(rules, case, message):
    samples = [row()]
    if case == 'unexpected': samples[0]['redcap_repeat_instrument'] = 'another_form'
    if case == 'none': samples[0]['record_id'] = 'OTHER'
    if case == 'duplicate': samples.append(row())
    if case == 'columns': del samples[0]['mood_vas_s1_daily']
    if case == 'rules': (rules / 'rcs08_study_stages.csv').unlink()
    with pytest.raises(ValueError, match=message): daily.canonicalize_rows(samples, rules)


@pytest.mark.parametrize('suffix,entry,message', [
    ('timestamp_corrections', dict(repeat_instance=99, entered_survey_start='2025-07-02 12:00:00', corrected_survey_start='2025-07-02 13:00:00', correction_reason='test'), 'exactly one survey for timestamp'),
    ('survey_exclusions', dict(repeat_instance=99, survey_start='2025-07-02 12:00:00', exclusion_reason='test'), 'exactly one survey for reviewed exclusion'),
    ('survey_value_corrections', dict(repeat_instance=99, survey_start='2025-07-02 12:00:00', canonical_column='mpq_throbbing', entered_value=3, corrected_value=0, correction_reason='test'), 'exactly one survey for value'),
    ('survey_value_corrections', dict(repeat_instance=1, survey_start='2025-07-02 12:00:00', canonical_column='nrs_intensity', entered_value=3, corrected_value=0, correction_reason='test'), 'not supported'),
    ('survey_value_corrections', dict(repeat_instance=1, survey_start='2025-07-02 12:00:00', canonical_column='mpq_throbbing', entered_value=3, corrected_value=4, correction_reason='test'), 'outside 0-3'),
    ('survey_value_corrections', dict(repeat_instance=1, survey_start='2025-07-02 12:00:00', canonical_column='mpq_throbbing', entered_value=2, corrected_value=0, correction_reason='test'), 'expected mpq_throbbing'),
])
def test_correction_identity_and_value_guards(rules, suffix, entry, message):
    replace_rule(rules, suffix, [entry])
    with pytest.raises(ValueError, match=message): daily.canonicalize_rows([row(throbbing_s1_daily='3')], rules)


@pytest.mark.parametrize('suffix', ['timestamp_corrections', 'survey_value_corrections', 'survey_exclusions'])
def test_rule_missing_columns_and_duplicates(rules, suffix):
    path = rules / ('rcs08_stage1_daily_' + suffix + '.csv')
    fields = next(csv.reader(path.open()))
    write_csv(path, ['wrong'])
    with pytest.raises(ValueError, match='missing columns'): daily.canonicalize_rows([row()], rules)
    entry = dict.fromkeys(fields, 'test')
    write_csv(path, fields, [entry, entry])
    with pytest.raises(ValueError, match='duplicate'): daily.canonicalize_rows([row()], rules)


def test_stage_and_calendar_validation_and_optional_low_level_paths(rules, monkeypatch):
    monkeypatch.setenv('RCS08_PROCESSING_RULES', str(rules))
    assert len(daily.canonicalize_rows([row()])) == 1
    paths = dict(study_stages_path=rules / 'rcs08_study_stages.csv', testing_dates_path=rules / 'rcs08_stim_testing_dates.csv', corrections_path=rules / 'absent', exclusions_path=rules / 'absent')
    frame = pd.DataFrame([row()]).replace('', pd.NA)
    assert daily._canonicalize_daily_surveys(frame, **paths).iloc[0].survey_duration_min == 5
    write_csv(paths['study_stages_path'], ['stage'])
    with pytest.raises(ValueError, match='Study-stage table'): daily._load_study_stages(paths['study_stages_path'])
    write_csv(paths['testing_dates_path'], ['date'])
    with pytest.raises(ValueError, match='Stim-testing calendar is missing'): daily._load_testing_dates(paths['testing_dates_path'])
    fields = ['date', 'stage', 'event_type', 'other_notes', 'location']
    item = dict(zip(fields, ['2025-07-01', 'stage_1', '', '', '']))
    write_csv(paths['testing_dates_path'], fields, [item, item])
    with pytest.raises(ValueError, match='duplicate dates'): daily._load_testing_dates(paths['testing_dates_path'])


def oura_row(times, values, day='2026-06-01', channel='Heart Rate'):
    data = np.asarray(values, dtype=float).reshape((-1, 1))
    return dict(Time=times, Data=data, StartTime=0, SamplingRate=1, Missing=np.zeros_like(data), ChannelNames=[channel], Metadata={'DayLabel': day}, Descriptor={})


def test_oura_rejects_invalid_policy_and_sample_contract(tmp_path, monkeypatch):
    path = write_csv(tmp_path / 'policy.csv', ['target_time_basis', 'participant_id', 'action'], [dict(target_time_basis='Oura day', participant_id='OTHER', action='exclude')])
    monkeypatch.setattr(oura, 'POLICY_PATH', path)
    with pytest.raises(ValueError, match='Invalid RCS08'): oura.policy()
    sample = oura_row([], [1, 2]); del sample['Time']; sample['StartTime'] = 10; sample['SamplingRate'] = 2
    assert oura.sample_times(sample).tolist() == [10, 10.5]
    sample['SamplingRate'] = 0
    with pytest.raises(ValueError, match='positive sampling rate'): oura.sample_times(sample)
    sample['Data'] = []
    assert len(oura.sample_times(sample)) == 0


def test_oura_mask_shape_and_missing_metadata_identity():
    sample = oura_row([1], [1]); sample['Missing'] = np.zeros((2, 1))
    with pytest.raises(ValueError, match='mask shapes'): oura.apply_quality_control({'HeartRate': [sample]})
    assert oura.day_label({}) is None
    sample = oura_row([1, float('nan')], [0, 50], day='bad')
    clean, audit = oura.apply_quality_control({'Sleep': [sample]})
    assert clean['Sleep'][0]['Descriptor'] == {} and audit[0]['eligible_observed_cells'] == 1
    assert audit[0]['summary_reason'] == 'Missing/invalid Oura day'
    assert oura.timeline_series(clean)[0]['Time'] == [1]


def test_oura_empty_invalid_times_and_nonnumeric_descriptors():
    sample = oura_row([float('nan')], [1], channel='Sleep Phase')
    sample['Descriptor'] = {'score': None, 'text': 'excluded', 'nonfinite': float('inf')}
    plots = oura.timeline_series({'Sleep': [sample]})
    assert plots[0]['Data'] == [[None], [None]] and plots[0]['ChannelNames'] == ['[OURA] Sleep nonfinite', '[OURA] Sleep score']
    assert plots[1]['Time'] == plots[1]['Duration'] == [] and plots[1]['Data'] == [[]]
    sample['Time'] = [1, 2, 3, 4, 5]; sample['Data'] = np.array([[1], [2], [3], [4], [99]]); sample.pop('Missing')
    assert oura.timeline_series({'Sleep': [sample]})[1]['Data'] == [['deep', 'light', 'rem', 'awake', None]]


def historical_files(tmp_path, changes=None):
    for filename, identity, defs in [('rcs08_fluctuation_redcap.csv', 'participant_id', historical.FLUCTUATION), ('rcs08_stage0_redcap.csv', 'record_id', historical.STAGE0)]:
        fields = [identity, 'source_record_id', 'source_event', 'redcap_event_name', 'redcap_repeat_instrument', 'redcap_repeat_instance']
        family = 'Stage 0' if identity == 'record_id' else 'Fluctuation'
        for _, stamp, complete, metrics in defs:
            fields += [stamp, complete] + [column for key, _, _ in metrics for column in historical.source_columns(family, key)]
        fields = list(dict.fromkeys(fields))
        base = dict.fromkeys(fields, '')
        base.update({identity: 'RCS08', 'source_record_id': 'synthetic', 'source_event': 'visit', 'redcap_event_name': 'event', 'redcap_repeat_instrument': 'form', 'redcap_repeat_instance': '2'})
        for _, stamp, complete, metrics in defs:
            base[stamp] = '2025-01-02T08:00:00-08:00'; base[complete] = '2'
            base.update({column: '0' for key, _, _ in metrics for column in historical.source_columns(family, key)})
        records = [base, dict(base, **{identity: 'OTHER'})]
        if changes: changes(filename, records, defs)
        write_csv(tmp_path / filename, fields, records)
    return tmp_path


def test_historical_true_time_zero_ranges_identity_and_audit(tmp_path, monkeypatch):
    def changes(filename, records, defs):
        incomplete = dict(records[0]); invalid = dict(records[0]); empty = dict(records[0])
        for _, stamp, complete, metrics in defs:
            incomplete[complete] = '1'; invalid[stamp] = 'not a time'
            for key, _, _ in metrics:
                family = 'Stage 0' if filename.startswith('rcs08_stage0') else 'Fluctuation'
                for column in historical.source_columns(family, key): empty[column] = ''
        records += [incomplete, invalid, empty]
        if filename.startswith('rcs08_stage0'):
            records[0]['hamd_score'] = '999'  # Stored scale has no asserted upper bound.
    historical_files(tmp_path, changes)
    monkeypatch.setenv('RCS08_PROCESSING_RULES', str(tmp_path))
    forms = historical.prepare_forms()
    assert len(forms) == 10
    for name, mapping, records in forms:
        assert len(records) == 1 and records[0]['name'] == 'synthetic:visit:event:form:2'
        assert records[0]['date'] == dt.datetime(2025, 1, 2, 16, tzinfo=dt.timezone.utc).timestamp()
        assert records[0]['record'][0][-1] == '2025-01-02T08:00:00-08:00'
        audit = mapping[0]['processing']
        assert audit['patient_rows'] == 4 and audit['invalid_completed_timestamps'] == 1 and audit['included'] == 1
        assert audit['source_sha256'] == hashlib.sha256((tmp_path / audit['source_file']).read_bytes()).hexdigest()
    assert forms[0][2][0]['record'][0][0] == 0
    assert forms[-1][2][0]['record'][0][0] == 999
    assert 'max' not in forms[-1][1][0]['questions'][0]


@pytest.mark.parametrize('value', ['-1', '11'])
def test_historical_documented_range_rejected(tmp_path, value):
    def changes(filename, records, defs):
        if filename.startswith('rcs08_fluctuation'): records[0]['nrs_intensity'] = value
    historical_files(tmp_path, changes)
    with pytest.raises(ValueError, match='outside documented range'): historical.prepare_forms(tmp_path)


def test_historical_empty_invalid_schema_and_no_completed_data(tmp_path):
    historical_files(tmp_path, lambda filename, records, defs: [r.update({complete: '0' for _, _, complete, _ in defs}) for r in records])
    assert historical.prepare_forms(tmp_path) == []
    write_csv(tmp_path / 'rcs08_fluctuation_redcap.csv', ['participant_id'])
    with pytest.raises(ValueError, match='missing columns'): historical.prepare_forms(tmp_path)


@pytest.mark.parametrize('existing,changed,dry_run,linked', [(False, True, False, False), (True, True, False, True), (True, False, False, True), (False, True, True, False), (True, True, True, True)])
def test_historical_sync_idempotence_and_dry_run(existing, changed, dry_run, linked):
    participant = NS(institute='synthetic-institute')
    records = [{'date': 123.0, 'name': 'source:event:form:2', 'record': [[0, None, 'iso']]}]
    mapping = [{'header': 'synthetic', 'questions': []}]
    form = Mock(record=copy.deepcopy(mapping)) if existing else None
    stored = [NS(**copy.deepcopy(records[0]))]
    if changed and form is not None: stored[0].record = [[1, None, 'iso']]
    with patch.object(historical, 'prepare_forms', return_value=[('Synthetic historical', mapping, records)]), patch.object(historical.transaction, 'atomic', return_value=nullcontext()), patch.object(historical.models, 'ScaleForms') as forms, patch.object(historical.models, 'ScaleRecord') as scales, patch.object(historical.models, 'ParticipantLinkRel') as links, patch('modules.ReportCache.invalidate') as invalidate:
        forms.find.return_value = form
        scales.find_all.return_value = stored
        links.include.return_value = linked
        result = historical.sync_historical_surveys(participant, dry_run=dry_run)
        assert result == [{'form': 'Synthetic historical', 'records': 1, 'changed': changed, 'written': int(changed and not dry_run)}]
        assert invalidate.call_count == int(changed and not dry_run)
        assert scales.objects.bulk_create.call_count == int(changed and not dry_run)
        assert links.create.call_count == int(changed and not dry_run and not linked)
        if changed and not dry_run:
            scales.objects.filter.assert_called_once_with(source=form if existing else forms.return_value, participant=participant)
            scales.assert_called_once_with(participant=participant, source=form if existing else forms.return_value, **records[0])


def test_testing_calendar_publication_includes_dates_without_surveys(rules):
    samples = [row(1, '2025-07-02 12:00:00'), row(2, '2025-07-03 12:00:00')]
    before = daily.canonicalize_rows(samples, rules)
    path = rules / 'rcs08_stim_testing_dates.csv'
    with path.open(newline='') as handle:
        existing = list(csv.DictReader(handle))
    extra = [dict(date='2025-08-14', stage='stage_2', event_type='testing', other_notes='No daily survey', location='clinic'),
             dict(date='2025-08-15', stage='screening', event_type='visit', other_notes='', location='clinic')]
    write_csv(path, list(existing[0]), existing + extra)
    after = daily.canonicalize_rows(samples, rules)
    assert after.attrs['timeline_testing_days'] == ['2025-07-03', '2025-08-14']
    assert after.attrs['timeline_testing_days_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert not after.survey_start.dt.date.astype(str).eq('2025-08-14').any()
    assert before.to_csv(index=False) == after.to_csv(index=False)
    assert before.include_in_analysis.tolist() == after.include_in_analysis.tolist() == [True, False]
    assert before.stim_testing_date.tolist() == after.stim_testing_date.tolist() == [False, True]
    assert before.attrs['timeline_testing_days_sha256'] != after.attrs['timeline_testing_days_sha256']
