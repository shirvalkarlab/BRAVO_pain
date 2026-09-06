"""Synthetic FreeReps adapter contracts; no private data or remote requests."""
import copy
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from rest_framework.test import APIRequestFactory, force_authenticate

from modules.OURA.FreeReps import build_report, finite, samples, sleep_record
from Server.APIs.OuraFreeReps import QueryOuraFreeReps
from Server.APIs import OuraFreeReps as api


def row(day='2026-06-01', start=1780293600., data=None, descriptor=None, included=True):
    data = np.array(data if data is not None else [[60, 20, 1], [70, 30, 2], [80, 40, 3], [90, 50, 4]], dtype=float)
    return {'Metadata': {'DayLabel': day, 'Score': 80, 'QualityControl': {'summary_included': included, 'version': 'test-qc'}},
            'StartTime': start, 'SamplingRate': 1/300, 'Data': data,
            'ChannelNames': ['Heart Rate', 'Heart Rate Variability', 'Sleep Phase'], 'Missing': np.zeros_like(data),
            'Descriptor': descriptor if descriptor is not None else {'BedtimeStart': start, 'BedtimeEnd': start+1200,
                                                                  'TotalSleepDuration': 900, 'Efficiency': 75}}


class AdapterTests(unittest.TestCase):
    def test_metrics_units_real_scores_zeros_and_days(self):
        activity = row(descriptor={'Steps': 0, 'HighActivityTime': 120, 'SedentaryActivityTime': 7200})
        ready = row(descriptor={'TemperatureDeviation': -.5})
        bad = row(day='2026-05-01', included=False)
        absent = row(); absent['Metadata']['Score'] = -1
        data = {'DailyActivity': [activity], 'DailyReadiness': [ready, bad], 'DailySleep': [absent],
                'DailyStress': [row(descriptor={'StressHigh': 0, 'RecoveryHigh': 600})]}
        result = build_report(data)
        metrics = {m['key']: m for m in result['metrics']}
        self.assertNotIn('sleep_score', metrics)
        self.assertEqual(metrics['readiness']['points'], [{'day':'2026-06-01', 'value':80}])
        for key, value in [('steps',0),('activity_high',2),('sedentary',2),('temperature',-.5),('stress',0),('recovery',10)]:
            self.assertEqual(metrics[key]['points'][0]['value'], value)
        data['DailySleep'] = [row()]
        self.assertIn('sleep_score', [m['key'] for m in build_report(data)['metrics']])
        json.dumps(result, allow_nan=False)

    def test_sleep_main_nap_duplicates_masks_and_original_unchanged(self):
        night = row(); night['Missing'][1,0] = 1; night['Data'][2,1] = np.nan
        night['Data'][0,1] = 0
        night['Data'][1,2] = 1
        nap = row(start=night['StartTime']+10000, descriptor={'BedtimeStart':night['StartTime']+10000,
                  'BedtimeEnd':night['StartTime']+10300, 'TotalSleepDuration':200})
        before = copy.deepcopy(night)
        result = build_report({'Sleep':[nap,night,night]})
        self.assertEqual(len(result['sleep']),2)
        metrics={m['key']:m['points'][0]['value'] for m in result['metrics']}
        self.assertEqual(metrics['sleep_duration'],.25)
        self.assertEqual(metrics['sleep_hr'], (60+80+90)/3)
        self.assertEqual(metrics['sleep_hrv'], (0+30+50)/3)
        detail=build_report({'Sleep':[night]}, result['sleep'][0]['id'])['sleep']
        self.assertEqual(detail['heart_rate'][1]['value'],None)
        self.assertEqual(detail['stages'][0],{'start':night['StartTime'],'end':night['StartTime']+600,'stage':'Deep'})
        self.assertEqual([v['stage'] for v in detail['stages']],['Deep','REM','Awake'])
        np.testing.assert_equal(night['Data'],before['Data'])
        json.dumps(detail,allow_nan=False)

    def test_missing_gaps_stage_bounds_and_longer_replaces_main(self):
        short=row(descriptor={'BedtimeStart':1780293600.,'BedtimeEnd':1780293900.,'TotalSleepDuration':100})
        longer=row(start=1780294000.)
        longer['Missing'][1,2]=1
        longer['Data'][2,2]=1
        report=build_report({'Sleep':[short,longer]})
        self.assertEqual(next(m for m in report['metrics'] if m['key']=='sleep_duration')['points'][0]['value'],.25)
        detail=sleep_record(longer,True)
        self.assertEqual(len(detail['stages']),3)
        self.assertNotEqual(detail['stages'][0]['end'],detail['stages'][1]['start'])
        short['Descriptor']['BedtimeStart']+=1000
        self.assertIsNone(sleep_record(short))
        past=row(); past['Descriptor']['BedtimeStart']+=600
        self.assertEqual(sleep_record(past,True)['stages'][0]['stage'],'REM')

    def test_partial_day_samples_no_daily_summary_and_missing_day(self):
        partial=row(included=False)
        report=build_report({'Sleep':[partial,row(day='invalid')]})
        self.assertEqual(len(report['sleep']),1)
        self.assertEqual(report['metrics'],[])
        self.assertIsNone(report['sleep'][0]['duration_hours'])
        self.assertEqual(report['provenance']['main_sleep_days'],0)
        self.assertEqual(len(sleep_record(partial,True)['stages']),4)

    def test_canonical_loader_applies_staff_testing_policy(self):
        from modules.OURA.DataManager import loadOuraRingData
        from modules.OURA.QualityControl import policy
        import datetime as dt
        _, timed = policy()
        blocked_start = dt.datetime.fromisoformat(timed['start_inclusive']).timestamp()
        excluded = row(day='2026-04-30', start=blocked_start + 3600)
        with patch.object(api.models.SourceFile, 'find', return_value=SimpleNamespace(pointer='synthetic', hashed='hash')), \
             patch('modules.Database.loadSourceFile', return_value={'Sleep': [excluded, row()]}), \
             patch('modules.RCS08DataPolicy.applies_to', return_value=True):
            report = build_report(loadOuraRingData(SimpleNamespace(uid='test')))
        self.assertEqual([sleep['day'] for sleep in report['sleep']], ['2026-06-01'])
        self.assertEqual(report['provenance']['qc_versions'], ['rcs08-oura-qc-1'])

    def test_empty_missing_channels_and_invalid_bounds(self):
        self.assertEqual(build_report({})['metrics'],[])
        with self.assertRaises(KeyError): build_report({},'missing')
        empty=row(data=np.empty((0,3))); empty['Descriptor']={}
        self.assertIsNone(sleep_record(empty))
        empty['Descriptor']={'BedtimeStart':1,'BedtimeEnd':2}
        self.assertEqual(sleep_record(empty,True)['heart_rate'],[])
        empty['ChannelNames']=[]
        self.assertEqual(sleep_record(empty,True)['stages'],[])
        all_missing=row(); all_missing['Missing'][:,:]=1
        self.assertIsNone(sleep_record(all_missing)['hr'])
        neg=row(); neg['Descriptor']['TotalSleepDuration']=-1
        self.assertIsNone(sleep_record(neg)['duration_hours'])
        neg['Data'][:,0]=0; neg['Data'][:,1]=-1
        self.assertIsNone(sleep_record(neg)['hr'])

    def test_explicit_times_invalid_cells_validation_and_no_rate(self):
        value=row(); value['Time']=[value['StartTime']+600, np.nan, value['StartTime'], value['StartTime']+900]
        times,values,names=samples(value)
        self.assertEqual(len(times),3)
        self.assertEqual(values[0,0],80)
        value['SamplingRate']=-1
        value['Descriptor']={}
        self.assertEqual(sleep_record(value,True)['stages'],[])
        value['Missing']=np.zeros((1,1))
        with self.assertRaises(ValueError): samples(value)
        value=row(); value['ChannelNames']=['Heart Rate']
        with self.assertRaises(ValueError): samples(value)
        for raw in [None,True,'3',np.nan,np.inf]: self.assertIsNone(finite(raw))
        self.assertEqual(finite(np.int64(0)),0)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.factory=APIRequestFactory()
        self.user=SimpleNamespace(is_authenticated=True,configuration={})
        self.storage=tempfile.TemporaryDirectory()
        self.env=patch.dict('os.environ',{'DATASERVER_PATH':self.storage.name+'/'})
        self.env.start()
        self.permission=patch('modules.Database.checkAccessPermission',return_value={'View':True}).start()
        self.participant=patch.object(api.models.Participant,'find',return_value=SimpleNamespace(uid='participant')).start()
        patch('modules.Database.retrieveProcessingSettings',return_value=({},None)).start()
        self.loader=patch('modules.OURA.DataManager.loadOuraRingData',return_value={'Sleep':[row()]}).start()

    def tearDown(self):
        patch.stopall(); self.env.stop(); self.storage.cleanup()

    def request(self,body,authenticated=True):
        request=self.factory.post('/api/queryOuraFreeReps',body,format='json')
        if authenticated: force_authenticate(request,user=self.user)
        return QueryOuraFreeReps.as_view()(request)

    def test_auth_and_strict_input_before_source(self):
        self.assertIn(self.request({'ParticipantId':'participant'},False).status_code,[401,403])
        for body in [[],{}, {'ParticipantId':None},{'ParticipantId':''},{'ParticipantId':3},
                     {'ParticipantId':'a'*129},{'ParticipantId':'participant','Raw':True},
                     {'ParticipantId':'participant','SleepId':3},{'ParticipantId':'participant','SleepId':'bad'}]:
            self.assertEqual(self.request(body).status_code,400)
        self.loader.assert_not_called()
        self.permission.return_value=None
        self.assertEqual(self.request({'ParticipantId':'participant'}).status_code,403)
        self.permission.return_value={'View':True}; self.participant.return_value=None
        self.assertEqual(self.request({'ParticipantId':'participant'}).status_code,403)

    def test_read_only_viewer_can_load_both_views(self):
        from Server.Middlewares.ReadOnlyAccount import ReadOnlyAccountMiddleware
        self.user.configuration['ReadOnly'] = True
        for body in [{'ParticipantId': 'participant'},
                     {'ParticipantId': 'participant', 'SleepId': sleep_record(row())['id']}]:
            request = self.factory.post('/api/queryOuraFreeReps', body, format='json')
            request.user = self.user
            force_authenticate(request, user=self.user)
            response = ReadOnlyAccountMiddleware(QueryOuraFreeReps.as_view())(request)
            self.assertEqual(response.status_code, 200)

    def test_cached_permission_invalidation_details_and_failures(self):
        body={'ParticipantId':'participant'}
        first=self.request(body)
        self.assertEqual(first.status_code,200)
        self.assertEqual(first['X-BRAVO-Report-Cache'],'MISS')
        result=json.loads(first.content)
        self.assertEqual(self.request(body)['X-BRAVO-Report-Cache'],'HIT')
        self.assertEqual(self.loader.call_count,1)
        self.permission.return_value=None
        self.assertEqual(self.request(body).status_code,403)
        self.assertEqual(self.loader.call_count,1)
        self.permission.return_value={'View':True}
        detail=self.request({**body,'SleepId':result['sleep'][0]['id']})
        self.assertEqual(len(json.loads(detail.content)['sleep']['stages']),4)
        self.assertEqual(self.request({**body,'SleepId':'0'*24}).status_code,404)
        from modules.ReportCache import invalidate
        invalidate()
        self.loader.return_value={}
        self.assertEqual(json.loads(self.request(body).content)['sleep'],[])
        self.loader.assert_called_with(self.participant.return_value)
        invalidate(); self.loader.side_effect=ValueError('private source details')
        failed=self.request(body)
        self.assertEqual(failed.status_code,503)
        self.assertNotIn('private',str(failed.data))
        self.loader.side_effect = TypeError('private malformed value')
        self.assertEqual(self.request(body).status_code,503)
        self.loader.side_effect = KeyError('private malformed record')
        self.assertEqual(self.request(body).status_code,503)
        self.loader.side_effect = OverflowError('private out of range')
        self.assertEqual(self.request(body).status_code,503)
