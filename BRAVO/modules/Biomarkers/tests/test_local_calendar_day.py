"""Pacific daily grouping without changing absolute-time report matching."""
import datetime

import numpy as np
import pandas as pd
import pytest

from modules.Biomarkers import adapter, pipeline
from modules.Biomarkers.routines.local_time import PRO_LOCAL_TZ, local_calendar_day


@pytest.mark.parametrize('utc,expected', [
    ('2025-07-22 06:59:59', '2025-07-21'), ('2025-07-22 07:00:00', '2025-07-22'),
    ('2025-01-22 07:59:59', '2025-01-21'), ('2025-01-22 08:00:00', '2025-01-22'),
    ('2025-03-09 09:59:59', '2025-03-09'), ('2025-03-09 10:00:00', '2025-03-09'),
    ('2025-11-02 08:30:00', '2025-11-02'), ('2025-11-02 09:30:00', '2025-11-02'),
])
def test_utc_day_boundaries_and_both_dst_transitions(utc, expected):
    assert local_calendar_day(pd.Timestamp(utc)) == datetime.date.fromisoformat(expected)


@pytest.mark.parametrize('as_local', [False, True])
def test_scalar_aware_and_missing_inputs(as_local):
    assert local_calendar_day(pd.Timestamp('2025-07-22 01:00', tz='UTC'),
                              naive_is_local=as_local) == datetime.date(2025, 7, 21)
    for missing in (None, pd.NaT, 'not a timestamp'):
        assert local_calendar_day(missing, naive_is_local=as_local) is None


@pytest.mark.parametrize('factory', [pd.Series, pd.Index, list, tuple, np.asarray])
@pytest.mark.parametrize('as_local', [False, True])
def test_collections_preserve_missing_and_explicit_naive_semantics(factory, as_local):
    values = factory([pd.Timestamp('2025-07-22 01:00'), pd.NaT])
    actual = local_calendar_day(values, naive_is_local=as_local)
    assert actual[0] == datetime.date(2025, 7, 22 if as_local else 21)
    assert pd.isna(actual[1])
    assert len(local_calendar_day(factory([]), naive_is_local=as_local)) == 0


def test_series_index_and_aware_local_wall_date_are_preserved():
    values = pd.Series([pd.Timestamp('2025-07-22 01:00', tz='UTC')], index=['report'])
    for as_local in (False, True):
        out = local_calendar_day(values, naive_is_local=as_local)
        assert list(out.index) == ['report']
        assert out['report'] == datetime.date(2025, 7, 21)
    assert values['report'] == pd.Timestamp('2025-07-22 01:00', tz='UTC')


def _epoch(value):
    return pd.Timestamp(value, tz='UTC').timestamp()


def _pro(canonical=True):
    data = {'date_time_s1_daily': ['2025-07-21 18:00'], 'nrs': [7.]}
    if canonical:
        data['_pro_time_utc'] = pd.to_datetime(['2025-07-22 01:00'])
    return pd.DataFrame(data)


def _chronic():
    return {'Time': np.array([_epoch('2025-07-21 19:00'), _epoch('2025-07-22 19:00')]),
            'Data': np.array([[100., 2.], [110., 2.]])}


def test_canonical_evening_report_joins_its_local_chronic_day_only():
    pro = _pro()
    before = pro.copy(deep=True)
    out = adapter.align_pros(pro, target='chronic', chronic=_chronic(), metrics=('nrs',))
    assert out.nrs.iloc[0] == 7 and np.isnan(out.nrs.iloc[1])
    pd.testing.assert_frame_equal(pro, before)


@pytest.mark.parametrize('raw', ['2025-07-21 01:00', '2025-07-21 18:00'])
def test_legacy_raw_naive_reports_keep_their_wall_date(raw):
    pro = pd.DataFrame({'date_time_s1_daily': [raw], 'nrs': [7.]})
    out = adapter.align_pros(pro, target='chronic', chronic=_chronic(), metrics=('nrs',))
    assert out.nrs.iloc[0] == 7 and np.isnan(out.nrs.iloc[1])


def test_raw_aware_report_uses_its_explicit_instant():
    pro = pd.DataFrame({'date_time_s1_daily': [pd.Timestamp('2025-07-22 01:00', tz='UTC')],
                        'nrs': [7.]})
    out = adapter.align_pros(pro, target='chronic', chronic=_chronic(), metrics=('nrs',))
    assert out.nrs.iloc[0] == 7 and np.isnan(out.nrs.iloc[1])


def test_legacy_session_join_uses_local_date_and_daily_rating_identity():
    recs = [{'StartTime': value} for value in _chronic()['Time']]
    out = adapter.align_pros(_pro(), target='session', recordings=recs, metrics=('nrs',))
    assert list(out.matched) == [True, False]
    assert list(out.session_date) == [datetime.date(2025, 7, 21), datetime.date(2025, 7, 22)]
    assert out.matched_pro_time.iloc[0] == pd.Timestamp('2025-07-21')
    assert out.nrs_mean.iloc[0] == 7 and np.isnan(out.nrs_mean.iloc[1])


def test_positive_tolerance_retains_absolute_match_values_offsets_and_identity():
    # A session before local midnight still matches a report after it by exact time.
    pro = pd.DataFrame({'date_time_s1_daily': ['2025-07-22 00:05'],
                        '_pro_time_utc': pd.to_datetime(['2025-07-22 07:05']), 'nrs': [8.]})
    recs = [{'StartTime': _epoch('2025-07-22 06:55')},
            {'StartTime': _epoch('2025-07-23 06:55')}]
    out = adapter.align_pros(pro, target='session', recordings=recs, metrics=('nrs',),
                             match_tolerance_min=15)
    assert list(out.matched) == [True, False]
    assert out.session_start.iloc[0] == pd.Timestamp('2025-07-22 06:55')
    assert out.session_date.iloc[0] == datetime.date(2025, 7, 21)
    assert out.matched_pro_time.iloc[0] == pd.Timestamp('2025-07-22 07:05')
    assert out.match_dt_min.iloc[0] == 10
    assert out.nrs_mean.iloc[0] == out.nrs_min.iloc[0] == 8
    assert np.isnan(out.nrs_mean.iloc[1])


def _daily_frame():
    return pd.DataFrame({'timestamp': pd.to_datetime(['2025-07-22 06:00', '2025-07-22 19:00',
                                                     '2025-07-23 19:00']),
                         'nrs': [9., 1., 3.], 'pain_level': [1., 0., 1.],
                         'LFP_smoothed': [10., 20., 30.], 'frequency_hz': [20.5]*3})


def test_daily_cut_and_frequency_preview_count_the_same_local_days():
    frame = _daily_frame()
    labels = adapter._threshold_pain_level(frame, 'nrs', strategy='median', daily_broadcast=True)
    assert labels.tolist() == [1., 0., 1.]
    counts = pipeline._available_frequencies(frame)
    assert counts[0]['n_days'] == counts[0]['n_days_labeled'] == 3
    preview = pipeline._decode_by_frequency(frame, 'nrs', min_labeled=10)['20.5']['binarization']
    assert [row['day'] for row in preview['daily']] == ['2025-07-21','2025-07-22','2025-07-23']
    assert [row['mean'] for row in preview['daily']] == [9., 1., 3.]


def test_active_chronic_branch_passes_local_labels_and_exports_local_dates(monkeypatch):
    # Exercise actual chronic preparation; only the scientific fit is replaced.
    samples = ['2025-07-21 19:00', '2025-07-22 06:00', '2025-07-22 19:00', '2025-07-23 19:00']
    chronic = {'Time': np.array([_epoch(s) for s in samples]),
               'Data': np.array([[100.,2.],[110.,2.],[120.,2.],[130.,2.]])}
    pro = pd.DataFrame({'date_time_s1_daily': ['unused']*3,
                        '_pro_time_utc': pd.to_datetime(['2025-07-22 01:00','2025-07-22 20:00',
                                                        '2025-07-23 20:00']),
                        'nrs': [9.,1.,3.]})
    captured = {}
    def no_fit(frame, **kwargs):
        captured['frame'] = frame.copy()
        return {'n_windows': 0}
    monkeypatch.setattr(pipeline.threshold_biomarker, 'run_chronic_threshold', no_fit)
    run = pipeline.run_powerdomain_branch(pro, chronic=chronic, label_strategy='median')
    assert captured['frame'].nrs.tolist() == [9.,9.,1.,3.]
    assert captured['frame'].pain_level.tolist() == [1.,1.,0.,1.]
    assert list(run['timeline'].date) == [datetime.date(2025,7,21),datetime.date(2025,7,21),
                                         datetime.date(2025,7,22),datetime.date(2025,7,23)]
    assert list(run['timeline'].time) == list(pd.to_datetime(samples))


def test_service_reuses_existing_timezone_constant():
    from modules.Biomarkers import bravo_service
    assert bravo_service._PRO_LOCAL_TZ == PRO_LOCAL_TZ == 'America/Los_Angeles'


@pytest.mark.parametrize('target,kwargs', [('session', {}), ('chronic', {}), ('other', {})])
def test_missing_inputs_remain_explicit_errors(target, kwargs):
    with pytest.raises(ValueError):
        adapter.align_pros(_pro(), target=target, **kwargs)


@pytest.mark.parametrize('tolerance', [None, 15])
def test_missing_session_time_remains_unmatched_and_stim_values_are_retained(tolerance):
    out = adapter.align_pros(_pro(), target='session', recordings=[{'StartTime': None}],
                             metrics=('nrs',), stim_amplitudes=[2.5],
                             match_tolerance_min=tolerance)
    assert out.session_date.iloc[0] is None
    assert not out.matched.iloc[0]
    assert np.isnan(out.nrs_mean.iloc[0])
    assert out.stim_amplitude.iloc[0] == 2.5


def test_frequency_preview_missing_dates_and_labels_are_not_fabricated():
    frame = _daily_frame()
    frame.loc[0, 'timestamp'] = pd.NaT
    frame.loc[1:, 'nrs'] = np.nan
    out = pipeline._decode_by_frequency(frame, 'nrs', min_labeled=10)['20.5']
    assert out['binarization']['daily'] == []
    assert out['n_days'] == 2
    frame['frequency_hz'] = np.nan
    assert pipeline._decode_by_frequency(frame, 'nrs') == {}


def test_chronic_missing_source_is_rejected_before_fit():
    with pytest.raises(ValueError, match='requires'):
        pipeline.run_powerdomain_branch(_pro(), chronic=None)


@pytest.mark.parametrize('sources,pain,expect_warning', [
    (['chronic']*2 + ['powerdomain']*2, [0.,0.,1.,1.], True),
    (['chronic']*2 + ['powerdomain']*2, [0.,1.,0.,1.], False),
    (['chronic']*4, [0.,0.,1.,1.], False),
    (None, [0.,0.,1.,1.], False),
])
def test_calendar_change_retains_source_confound_diagnostics(monkeypatch, sources, pain, expect_warning):
    frame = pd.DataFrame({'timestamp':pd.to_datetime(['2025-07-22 06:00','2025-07-22 19:00',
                                                     '2025-07-23 06:00','2025-07-23 19:00']),
                          'LFP':[1.,2.,3.,4.], 'LFP_smoothed':[1.,2.,3.,4.],
                          'stim_amplitude':[2.]*4, 'pain_level':pain, 'nrs':pain, 'source':sources})
    if sources is None:
        frame = frame.drop(columns='source')
    monkeypatch.setattr(adapter, 'bravo_chronic_to_lfp_df', lambda *a, **kw: frame.copy())
    monkeypatch.setattr(pipeline.threshold_biomarker, 'run_chronic_threshold', lambda *a, **kw: {})
    monkeypatch.setattr(pipeline.stats_utils, 'auc_block_perm_null', lambda *a, **kw: {'observed':None})
    out = pipeline.run_powerdomain_branch(_pro(), chronic=_chronic())
    assert bool(out['summary']['batch_confound_warning']) is expect_warning
    assert list(out['timeline'].date) == [datetime.date(2025,7,21),datetime.date(2025,7,22),
                                         datetime.date(2025,7,22),datetime.date(2025,7,23)]
    assert list(out['timeline'].time) == list(frame.timestamp)
    if sources is not None and len(set(sources)) == 2:
        assert out['summary']['sources'] == ['chronic','powerdomain']
        assert out['summary']['source_vs_pain_separation'] == (1. if expect_warning else .5)


def test_calendar_change_retains_sparse_channel_and_fit_failure_outputs(monkeypatch):
    pro = _pro()
    valid = {'Time': np.array([_epoch('2025-07-21 19:00'),_epoch('2025-07-22 01:00')]),
             'Data': np.array([[100.,2.],[110.,2.]]),
             'ChannelNames':['LeftHemisphere LFP','L Amplitude'], 'CenterFrequencyHz':20.5}
    failed = {**valid, 'Data':np.array([[200.,2.],[210.,2.]]),
               'ChannelNames':['RightHemisphere LFP','R Amplitude']}
    def fit(frame, **kw):
        if len(frame)==2 and frame.LFP.iloc[0]==200:
            raise ValueError('synthetic channel fit unavailable')
        return {}
    monkeypatch.setattr(pipeline.threshold_biomarker, 'run_chronic_threshold', fit)
    monkeypatch.setattr(pipeline.stats_utils, 'auc_block_perm_null', lambda *a, **kw: {'observed':None})
    out = pipeline.run_powerdomain_branch(pro, chronic=[valid,failed], label_strategy='median')
    left = out['per_channel']['LeftHemisphere LFP']
    right = out['per_channel']['RightHemisphere LFP']
    assert left['summary']['hemisphere'] == 'Left' and left['summary']['kind'] == 'aggregate'
    assert left['summary']['center_hz'] == 20.5
    assert left['cv_df'].nrs.tolist() == [7.,7.]
    assert right['cv_df'] is None and 'unavailable' in right['summary']['error']
    sparse = pipeline.run_powerdomain_branch(pro, chronic=valid, label_strategy='median')
    assert sparse['summary']['lfp_vs_continuous_pain_spearman'] is None
    same_group = pipeline.run_powerdomain_branch(pro, chronic=[valid,valid], label_strategy='median')
    assert same_group['per_channel'] == {}
