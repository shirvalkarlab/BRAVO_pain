"""Synthetic tests of raw home observations, routing, visit windows and access."""
import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
from rest_framework.test import APIRequestFactory, force_authenticate
from modules import HomeNeuralTimeline as h
from Server.APIs import HomeNeuralTimeline as api
from Server.test_redcap_stimulation import report as raw_report

DAYS = {'2026-08-01', '2026-08-04', '2026-08-08'}
NOW = h.midnight('2026-08-06')
HASH = 'a'*64


def record(stamp, power=20, amp=2, right_power=40, right_amp=3):
    return {'Time': [stamp], 'ChannelNames': ['LeftHemisphere LFP', 'LeftHemisphere Amplitude', 'RightHemisphere LFP', 'RightHemisphere Amplitude'],
            'Data': [[power, amp, right_power, right_amp]]}


def events(day=1, adaptive=True, ganged=False):
    payload = raw_report(day, adaptive)
    if ganged:
        payload['Groups']['Final'][0]['ProgramSettings']['SensingChannel'][1]['GangedToHemisphere'] = 'HemisphereLocationDef.Left'
    return h.snapshots(payload, f'source{day}')


def make(records=None, observed=None, days=DAYS):
    if records is None:
        records = [('device', record(h.midnight('2026-08-05')+3600))]
    return h.build_report(records, {'device': events(1)+events(4) if observed is None else observed}, days, HASH, NOW)


def populated(result, window=0, side=0):
    return next(segment for segment in result['windows'][window]['panels'][side]['segments'] if segment['points'])


class HomeTimelineTests(unittest.TestCase):
    def test_past28_uses_local_calendar_through_now_across_dst(self):
        for date, elapsed_hours in [('2026-03-20', 27*24-1), ('2026-11-20', 27*24+1)]:
            now = h.midnight(date)
            result = h.windows(DAYS, now, 'past28')
            self.assertEqual(len(result), 1)
            window = result[0]
            self.assertEqual(window['id'], 'past28')
            self.assertEqual(window['end'], now)
            self.assertEqual((now-window['start'])/3600, elapsed_hours)
            self.assertEqual(h.dt.datetime.fromtimestamp(window['start'], h.ZONE).hour, 0)
            self.assertEqual((h.dt.date.fromisoformat(date)-h.dt.date.fromisoformat(window['start_date'])).days, 27)
            self.assertEqual(window['end_date'], date)
            self.assertIn(window['start_date'], window['label'])
        # UTC has advanced to August 7 while Pacific is still August 6.
        now = h.midnight('2026-08-06')+23*3600
        self.assertEqual(h.windows((), now, 'past28')[0]['end_date'], '2026-08-06')
        self.assertEqual(h.windows((), now, 'past28')[0]['start_date'], '2026-07-10')

    def test_custom_inclusive_dates_dst_and_today_clamped(self):
        for date, hours in [('2026-03-08', 23), ('2026-11-01', 25)]:
            window = h.windows((), h.midnight('2026-12-01'), 'custom', date, date)[0]
            self.assertEqual((window['end']-window['start'])/3600, hours)
            self.assertEqual(window['start_date'], window['end_date'])
            self.assertEqual(window['id'], 'custom')
        now = NOW+3600
        window = h.windows((), now, 'custom', '2026-08-01', '2026-08-06')[0]
        self.assertEqual(window['end'], now)
        for first, last in [(None, '2026-08-06'), ('2026-08-01', None), (123, '2026-08-06'),
                            ('20260801', '2026-08-06'), ('2026-08-01', '20260806'),
                            ('2026-02-30', '2026-08-06'), ('2026-08-07', '2026-08-06'),
                            ('2026-08-01', '2026-08-07')]:
            with self.assertRaises(ValueError):
                h.windows((), now, 'custom', first, last)
        for window, first, last in [('bogus', None, None), ('past28', '2026-08-01', None),
                                    (None, None, '2026-08-01')]:
            with self.assertRaises(ValueError):
                h.windows((), now, window, first, last)

    def test_summary_extends_before_previous_visit_keeps_boundaries_and_clinic_gaps(self):
        start = h.midnight('2026-07-10')
        stamps = [start-1, start, h.midnight('2026-07-20'), h.midnight('2026-08-04'), NOW-1, NOW]
        records = [('device', record(stamp)) for stamp in stamps]
        result = h.build_report(records, {'device': events(4)}, DAYS, HASH, NOW, window='past28')
        points = [point for segment in result['windows'][0]['panels'][0]['segments'] for point in segment['points']]
        self.assertEqual([point['time'] for point in points], [start, h.midnight('2026-07-20'), NOW-1])
        self.assertIsNone(points[0]['power'])  # No future settings backfill.
        self.assertEqual(points[-1]['power'], 20)
        self.assertEqual(result['provenance']['excluded_clinic_rows'], 1)
        self.assertEqual(result['visit_days'], ['2026-08-01', '2026-08-04'])
        self.assertEqual(len(h.build_report([], {}, (), HASH, NOW, window='past28')['windows']), 1)
        legacy = h.build_report(records, {'device': events(4)}, DAYS, HASH, NOW)
        explicit_default = h.build_report(records, {'device': events(4)}, DAYS, HASH, NOW, window=None)
        self.assertEqual(legacy, explicit_default)
        self.assertEqual([window['id'] for window in legacy['windows']], ['current', 'previous'])

    def test_custom_output_excludes_points_at_next_midnight_and_audit_outside_range(self):
        start, end = h.midnight('2026-08-02'), h.midnight('2026-08-03')
        records = [('device', record(stamp)) for stamp in [start-1, start, end-1, end, h.midnight('2026-08-04')]]
        result = h.build_report(records, {'device': events(1)}, DAYS, HASH, NOW,
                                window='custom', start_date='2026-08-02', end_date='2026-08-02')
        points = [point for segment in result['windows'][0]['panels'][0]['segments'] for point in segment['points']]
        # First ten minutes still overlap the August 1 clinic date.
        self.assertEqual([point['time'] for point in points], [end-1])
        self.assertEqual(result['provenance']['excluded_clinic_rows'], 1)

    def test_real_numeric_only_no_null_to_zero(self):
        for value in [None, True, False, '2', np.nan, np.inf, [], {}, np.bool_(True)]:
            self.assertIsNone(h.finite(value))
        self.assertEqual(h.finite(np.float64(0)), 0)
        self.assertEqual(h.finite(-3), -3)

    def test_windows_use_all_visits_even_if_program_unchanged_future_ignored(self):
        result = make()
        self.assertEqual([window['visit_date'] for window in result['windows']], ['2026-08-04','2026-08-01'])
        self.assertEqual(result['windows'][0]['end'], NOW)
        self.assertEqual(result['windows'][1]['end'], h.midnight('2026-08-04'))
        self.assertEqual(h.windows(set(), NOW), [])
        self.assertEqual(len(h.windows({'2026-08-04'}, NOW)), 1)
        self.assertEqual(make(days=set())['windows'], [])

    def test_contralateral_routes_power_but_retains_target_amplitude(self):
        result = make(observed=events(1)+events(4, ganged=True))
        left, right = populated(result), populated(result, side=1)
        self.assertEqual(left['points'][0]['power'], 20)
        self.assertEqual(right['points'][0]['power'], 20)
        self.assertEqual(right['points'][0]['amplitude'], 3)
        self.assertEqual(right['sensing_side'], 'left')
        self.assertEqual(right['mapping_status'], 'contralateral')
        self.assertEqual(right['sensing_contacts'], '1–3')
        self.assertEqual(right['center_frequency_hz'], 23.44)
        self.assertIn('23.44 Hz center',right['power_band_label'])
        self.assertEqual([item['value'] for item in right['thresholds']], [1, 167])
        json.dumps(result, allow_nan=False)

    def test_unknown_mapping_never_assumes_ipsilateral_adaptive_controller(self):
        value = events(4)
        for event in value:
            event['controllers']['right']['sensing_side'] = None
            event['controllers']['right']['mapping_status'] = 'unknown'
        right = populated(make(observed=value), side=1)
        self.assertIsNone(right['points'][0]['power'])
        self.assertEqual(right['points'][0]['amplitude'], 3)
        self.assertEqual(right['thresholds'], [])
        self.assertEqual(h.controller_metadata({})['left']['mapping_status'], 'unknown')
        payload = raw_report()
        group = payload['Groups']['Final'][0]
        channel = group['ProgramSettings']['SensingChannel'][1]
        channel['GangedToHemisphere'] = 'bad'
        self.assertIsNone(h.controller_metadata(group)['right']['sensing_side'])
        channel['GangedToHemisphere'] = 'HemisphereLocationDef.Left'
        group['ProgramSettings']['SensingChannel'] = [channel]
        self.assertIsNone(h.controller_metadata(group)['right']['sensing_side'])
        group['ProgramSettings']['SensingChannel'] = [channel, copy.deepcopy(channel)]
        self.assertEqual(h.controller_metadata(group)['right']['mapping_status'], 'unknown')

    def test_sensing_only_paused_single_dual_threshold_modes(self):
        event = events(4)[-1]
        self.assertEqual(len(h.metadata(event, 'left')['thresholds']), 2)
        event['controllers']['left']['threshold_mode'] = 'SINGLE_THRESHOLD_DIRECT'
        self.assertEqual(h.metadata(event,'left')['thresholds'], [])
        for row in event['settings']['left']:
            if row['label'] in ('Lower LFP threshold','Upper LFP threshold'):
                row['value'] = '0 LFP Power (LSB)'
        self.assertEqual(h.metadata(event,'left')['thresholds'], [{'label':'Single LFP threshold','value':0}])
        event['controllers']['left']['adaptive_state'] = 'NOT_CONFIGURED'
        self.assertEqual(h.metadata(event,'left')['mode'], 'Sensing only')
        self.assertEqual(h.metadata(event,'left')['thresholds'], [])
        event['controllers']['left']['adaptive_state'] = 'SUSPENDED'
        self.assertIn('paused', h.metadata(event,'left')['mode'])
        event['controllers']['left']['sensing_status'] = 'OFF'
        self.assertIn('not recorded', h.metadata(event,'left')['mode'])
        event['controllers']['left']['adaptive_state'] = 'RUNNING'
        event['controllers']['left']['threshold_mode'] = ''
        self.assertIn('unknown', h.metadata(event,'left')['mode'])
        event['settings']['left'] = [{'label':'Lower LFP threshold','value':'damaged LFP Power (LSB)'}]
        self.assertEqual(h.metadata(event,'left')['thresholds'], [])
        self.assertIsNone(h.metadata(event,'left')['center_frequency_hz'])
        self.assertEqual(h.metadata(None,'left')['settings'], {})
        self.assertEqual(h.metadata(None,'left')['threshold_status'], 'Threshold configuration/control state not recorded')

    def test_raw_high_values_preserved_and_duplicate_conflicts_explicit(self):
        stamp = h.midnight('2026-08-05')+3600
        raw = record(stamp, 999999, 0)
        raw['ChannelNames'].append('Unknown'); raw['Data'][0].append(3)
        normalized, audit = h.observations([('d',raw),('d',copy.deepcopy(raw))],DAYS,0,NOW)
        self.assertEqual(normalized['d'][stamp][('left','power')]['value'],999999)
        self.assertEqual(normalized['d'][stamp][('left','amplitude')]['value'],0)
        conflicting = record(stamp, 10, 0)
        normalized, audit = h.observations([('d',raw),('d',conflicting)],DAYS,0,NOW)
        self.assertTrue(normalized['d'][stamp][('left','power')]['conflict'])
        self.assertIsNone(normalized['d'][stamp][('left','power')]['value'])
        self.assertEqual(audit['conflicting_values'],1)
        missing = record(stamp,None,np.nan)
        normalized,_ = h.observations([('d',missing),('d',record(stamp,22))],DAYS,0,NOW)
        self.assertEqual(normalized['d'][stamp][('left','power')]['value'],22)
        self.assertFalse(normalized['d'][stamp][('left','power')]['conflict'])
        normalized,_ = h.observations([('d',missing)],DAYS,0,NOW)
        self.assertIsNone(normalized['d'][stamp][('left','power')]['value'])
        value = populated(make(records=[('device',raw),('device',conflicting)]))
        self.assertTrue(value['points'][0]['power_conflict'])
        self.assertEqual(value['points'][0]['amplitude'],0)

    def test_testing_days_and_overlapping_bins_and_invalid_times_excluded(self):
        boundary = h.midnight('2026-08-04')
        values = [record(boundary-601),record(boundary-600),record(boundary),record(boundary+86400+600),record(boundary+86400+601),record(None),record(NOW),record(-1)]
        normalized,audit = h.observations([('d',row) for row in values],DAYS,0,NOW)
        self.assertEqual(sorted(normalized['d']),[boundary-601,boundary+86400+601])
        self.assertEqual(audit['excluded_clinic_rows'],3)
        self.assertEqual(audit['invalid_rows'],1)

    def test_no_settings_backfill_missing_latest_visit_and_logged_changes(self):
        latest_missing = populated(make(observed=events(1)))
        self.assertIsNone(latest_missing['settings_observed_at'])
        self.assertIsNone(latest_missing['points'][0]['power'])
        self.assertEqual(latest_missing['points'][0]['amplitude'],2)
        stamp = h.midnight('2026-08-05')
        observed = events(4)+[{'kind':'group_change','time':stamp,'id':'log','source_ids':['source4']}]
        self.assertIsNone(populated(make(observed=observed))['settings_observed_at'])
        self.assertIsNone(populated(make(observed=[]))['settings_observed_at'])
        before = record(h.midnight('2026-08-02')+3600)
        self.assertIsNone(populated(make(records=[('device',before)],observed=events(4)),window=1)['settings_observed_at'])

    def test_unchanged_final_restores_context_after_log_and_controller_conflicts_fail_closed(self):
        original = events(1)
        log = {'kind':'group_change','time':h.midnight('2026-08-02'), 'id':'log','source_ids':['source1']}
        result = make(observed=original+[log]+events(4))
        self.assertEqual(populated(result)['points'][0]['power'],20)
        self.assertEqual(populated(result)['settings_observed_at'],events(4)[-1]['time'])
        same = events(4)[-1]
        other = copy.deepcopy(same);other['id']='other';other['controllers']['right']['mapping_status']='unknown'
        self.assertIsNone(populated(make(observed=original+[same,other]))['settings_observed_at'])
        other=copy.deepcopy(same);other['id']='other';other['settings']['left'][0]['value']='conflict'
        self.assertIsNone(populated(make(observed=original+[same,other]))['settings_observed_at'])
        only_initial=[events(4)[0]]
        self.assertEqual(h.home_observations(only_initial,DAYS,HASH)['home_transitions'],[])
        non_visit=events(3)
        self.assertEqual(len(h.home_observations(non_visit,DAYS,HASH)['home_transitions']),2)

    def test_multiple_devices_independent_and_empty_points(self):
        stamp = h.midnight('2026-08-05')+3600
        result = h.build_report([('a',record(stamp)),('b',record(stamp,90))], {'a':events(4),'b':events(4)},DAYS,HASH,NOW)
        found = {segment['device_id']:segment['points'][0]['power'] for segment in result['windows'][0]['panels'][0]['segments'] if segment['points']}
        self.assertEqual(found,{'a':20,'b':90})
        raw = {'Time':[stamp], 'ChannelNames':['LeftHemisphere LFP'], 'Data':[[20]]}
        result = make(records=[('device',raw)])
        self.assertTrue(all(not segment['points'] for segment in result['windows'][0]['panels'][1]['segments']))
        self.assertTrue(make(records=[])['windows'][0]['panels'])

    def test_snapshot_log_events_keep_ids(self):
        payload=raw_report(); payload['DiagnosticData']={'EventLogs':[{'DateTime':'2026-08-01T15:00:00Z','ParameterTrendId':1,'TherapyStatus':'TherapyStatusDef.OFF'}]}
        value=h.snapshots(payload,'source')
        self.assertEqual(value[-1]['kind'],'stimulation_status')
        self.assertEqual(value[-1]['source_ids'],['source'])
        self.assertNotIn('controllers',value[-1])
        self.assertEqual(h.snapshots({},'source'),[])

    def test_read_hydrates_preceding_snapshot_for_requested_range_only(self):
        participant = NS(institute='lab')
        sources = [NS(uid=f's{day}', metadata={'Device': 'device'}) for day in (1, 4, 20)]
        payloads = {source.uid: raw_report(day) for source, day in zip(sources, (1, 4, 20))}
        now = h.midnight('2026-09-01')+3600
        days = {'2026-08-30', '2026-08-31'}
        observed = h.midnight('2026-08-10')+3600
        native = NS(source=sources[1], pointer='raw', hashed='hash')
        def context(source, *_):
            return ({'events': h.RedcapStimulation.extract(payloads[source.uid])['events'], 'excluded': None}, True)
        with patch.object(h.RedcapHomePrograms, 'calendar', return_value=(days, HASH)), \
                patch.object(h.RCS08DataPolicy, 'applies_to', return_value=True), \
                patch.object(h.models.SourceFile, 'find_all', return_value=NS(order_by=lambda: sources)), \
                patch.object(h.RedcapStimulation, 'source_context', side_effect=context), \
                patch.object(h.DataCurator, 'loadCacheFile', side_effect=lambda source: json.dumps(payloads[source.uid])) as cache, \
                patch.object(h.models.Recording, 'find_all', return_value=[native]), \
                patch.object(h.Database, 'loadSourceFile', return_value=record(observed)), \
                patch.object(h.models.ScaleForms, 'find', return_value=NS(record=[{'processing': {}}])):
            default = h.read(participant, now)
            self.assertEqual([call.args[0].uid for call in cache.call_args_list], ['s20'])
            self.assertEqual(default['provenance']['point_count'], 0)
            cache.reset_mock()
            summary = h.read(participant, now, window='past28')
            self.assertEqual([call.args[0].uid for call in cache.call_args_list], ['s4', 's20'])
            self.assertEqual(populated(summary)['points'][0]['power'], 20)
            self.assertEqual(summary['windows'][0]['start_date'], '2026-08-05')
            cache.reset_mock()
            custom = h.read(participant, now, window='custom', start_date='2026-08-09', end_date='2026-08-10')
            self.assertEqual(populated(custom)['points'][0]['time'], observed)
            self.assertEqual(custom['windows'][0]['end'], h.midnight('2026-08-11'))

    def test_read_filters_excluded_sources_and_only_raw_chronic_recordings(self):
        participant=NS(institute='lab')
        good=NS(uid='good', metadata={'Device':'device'})
        excluded=NS(uid='excluded',metadata={'AnalysisExclusion':'bad'})
        bad=NS(uid='bad',metadata={'Device':'other'})
        missing=NS(uid='missing',metadata={})
        rec=NS(source=good,pointer='raw',hashed='hash')
        bad_rec=NS(source=bad,pointer='bad',hashed='hash')
        inventory=NS(order_by=lambda:[good,excluded,bad,missing])
        with patch.object(h.RedcapHomePrograms,'calendar',return_value=(DAYS,HASH)), patch.object(h.RCS08DataPolicy,'applies_to',return_value=True), patch.object(h.RedcapStimulation,'source_context',side_effect=[({'events':h.RedcapStimulation.extract(raw_report(4))['events'], 'excluded':None},True), ({'events':[], 'excluded':'bad'},True)]), patch.object(h.models.SourceFile,'find_all',return_value=inventory), patch.object(h.DataCurator,'loadCacheFile',return_value=json.dumps(raw_report(4))), patch.object(h.models.Recording,'find_all',return_value=[rec,bad_rec]) as recording_query, patch.object(h.Database,'loadSourceFile',return_value=record(h.midnight('2026-08-05')+3600)) as load, patch.object(h.models.ScaleForms,'find',return_value=NS(record=[{'processing':{}}])):
            result=h.read(participant,NOW)
        recording_query.assert_called_once_with(source__owner=participant,type='MedtronicChronicBrainSense')
        load.assert_called_once_with('raw','hash')
        self.assertEqual(populated(result)['points'][0]['power'],20)


class HomeTimelineAPITests(unittest.TestCase):
    def request(self,body,authenticated=True):
        request=APIRequestFactory().post('/api/queryHomeNeuralTimeline',body,format='json')
        if authenticated:
            force_authenticate(request,user=NS(is_authenticated=True,configuration={'ActiveStudy':'study'}))
        return api.QueryHomeNeuralTimeline.as_view()(request)

    def test_auth_malformed_and_permission_boundaries(self):
        with patch.object(api.Database,'checkAccessPermission',return_value=False) as permission, patch.object(api.models.Participant,'find') as find, patch.object(api.HomeNeuralTimeline,'read') as read:
            self.assertIn(self.request({'ParticipantId':'x'},False).status_code,[401,403])
            for body in [[],{}, {'ParticipantId':None},{'ParticipantId':3},{'ParticipantId':''},{'ParticipantId':'a'*129},{'ParticipantId':'x','other':1}]:
                self.assertEqual(self.request(body).status_code,400)
            permission.assert_not_called()
            self.assertEqual(self.request({'ParticipantId':'x'}).status_code,403)
            find.assert_not_called();read.assert_not_called()

    def test_missing_unmapped_errors_and_success_no_store(self):
        with patch.object(api.Database,'checkAccessPermission',return_value={'view':True}), patch.object(api.models.Participant,'find',return_value=None) as find, patch.object(api,'applies_to',return_value=False) as applies, patch.object(api.HomeNeuralTimeline,'read') as read:
            self.assertEqual(self.request({'ParticipantId':'x'}).status_code,403)
            find.return_value=NS(uid='x')
            self.assertEqual(self.request({'ParticipantId':'x'}).status_code,404)
            read.assert_not_called()
            applies.return_value=True
            for error in [ValueError('secret'),OSError('secret'),IndexError('secret')]:
                read.side_effect=error
                response=self.request({'ParticipantId':'x'})
                self.assertEqual(response.status_code,503)
                self.assertNotIn('secret',str(response.data))
            read.side_effect=None;read.return_value={'status':'ready'}
            response=self.request({'ParticipantId':'x'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response['Cache-Control'],'no-store')

    def test_endpoint_viewer_allowlist_and_url(self):
        from Server.Middlewares.ReadOnlyAccount import READ_ONLY_POST_PATHS
        from django.urls import resolve
        self.assertIn('/api/queryHomeNeuralTimeline',READ_ONLY_POST_PATHS)
        self.assertIs(resolve('/api/queryHomeNeuralTimeline').func.cls,api.QueryHomeNeuralTimeline)

    def test_window_schema_rejects_invalid_requests_before_access(self):
        with patch.object(api.Database, 'checkAccessPermission') as permission, patch.object(api.time, 'time', return_value=NOW):
            for extra in [{'window': None}, {'window': 'current'}, {'window': []},
                          {'window': 'past28', 'start_date': None, 'end_date': None},
                          {'window': 'custom'}, {'window': 'custom', 'start_date': '2026-08-01'},
                          {'window': 'custom', 'start_date': '2026-08-01', 'end_date': '2026-08-07'},
                          {'window': 'custom', 'start_date': 1, 'end_date': '2026-08-01'},
                          {'start_date': '2026-08-01', 'end_date': '2026-08-01'}]:
                self.assertEqual(self.request({'ParticipantId': 'x', **extra}).status_code, 400)
            permission.assert_not_called()

    def test_window_options_forwarded_without_cached_response_or_default_change(self):
        participant = NS(uid='x')
        with patch.object(api.Database, 'checkAccessPermission', return_value={'view': True}), \
                patch.object(api.models.Participant, 'find', return_value=participant), \
                patch.object(api, 'applies_to', return_value=True), \
                patch.object(api.time, 'time', return_value=NOW), \
                patch.object(api.HomeNeuralTimeline, 'read', return_value={'status': 'ready'}) as read:
            for options in [{}, {'window': 'past28'},
                            {'window': 'custom', 'start_date': '2026-08-01', 'end_date': '2026-08-05'}]:
                response = self.request({'ParticipantId': 'x', **options})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Cache-Control'], 'no-store')
                read.assert_called_with(participant, NOW, **options)
