"""Independent synthetic contracts for the first-party Oura timeline."""
import copy
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from rest_framework.test import APIRequestFactory, force_authenticate

from modules.OURA.Timeline import CATALOG, build_report, finite, sample_mean, sleep_bounds, sample_metric, total_sleep_rows
from Server.APIs import OuraTimeline as api


def row(day='2026-06-01', start=1780293600., descriptor=None, included=True):
    data = np.array([[60, 20], [70, 30], [80, 40]], dtype=float)
    return {'Metadata': {'DayLabel': day, 'Score': 80, 'QualityControl': {'summary_included': included, 'version': 'test'}},
            'StartTime': start, 'SamplingRate': 1/300, 'Data': data,
            'ChannelNames': ['Heart Rate', 'Heart Rate Variability'], 'Missing': np.zeros_like(data),
            'Descriptor': descriptor if descriptor is not None else {'BedtimeStart': start, 'BedtimeEnd': start + 900,
                'TotalSleepDuration': 600, 'Efficiency': 75}}


def metrics(data):
    return {metric['key']: metric for metric in build_report(data)['metrics']}


class TimelineTests(unittest.TestCase):
    def test_complete_catalog_and_no_fake_observations(self):
        result = build_report({})
        self.assertEqual(len(result['metrics']), len(CATALOG))
        self.assertEqual(len({m['key'] for m in result['metrics']}), len(CATALOG))
        self.assertTrue(all(m['points'] == [] and not m['available'] for m in result['metrics']))
        self.assertEqual({m['key'] for m in result['metrics'] if m['default']}, set(result['defaults']))
        self.assertEqual(result['defaults'], ['steps', 'heart_rate', 'hrv', 'total_calories', 'sleep_duration', 'sleep_total'])
        self.assertNotIn('average_met', [m['key'] for m in result['metrics']])
        self.assertEqual(result['provenance']['main_sleep_days'], 0)
        value = row(descriptor={'Steps': 0, 'TotalCalories': -1, 'MetersToTarget': -100})
        value['Metadata']['Score'] = -1
        value['Metadata']['ScoreContributors'] = {'a': 100, 'b': 100}
        result = metrics({'DailyActivity': [value]})
        self.assertEqual(result['steps']['points'], [{'day': '2026-06-01', 'value': 0}])
        self.assertEqual(result['meters_to_target']['points'][0]['value'], -100)
        self.assertEqual(result['activity']['points'], [])
        self.assertEqual(result['total_calories']['points'], [])
        self.assertEqual(result['sleep_score']['points'], [])

    def test_every_descriptor_conversion_and_genuine_scores(self):
        data = {}
        for _, _, _, _, stream, descriptor, divisor in CATALOG:
            if stream in {'@sample', 'SleepTotal'}:
                continue
            if stream not in data:
                data[stream] = [row()]
            if descriptor and not descriptor.startswith('@'):
                data[stream][0]['Descriptor'][descriptor] = divisor * 2
        result = metrics(data)
        for key, _, _, _, stream, descriptor, _ in CATALOG:
            if stream in {'@sample', 'SleepTotal'}:
                continue
            self.assertEqual(result[key]['points'][0]['value'], 80 if descriptor is None else
                             70 if descriptor == '@Heart Rate' else 30 if descriptor == '@Heart Rate Variability' else 2)
        json.dumps(build_report(data), allow_nan=False)
        for value in [None, False, True, '3', [], {}, np.nan, np.inf, np.bool_(True)]:
            self.assertIsNone(finite(value))
        self.assertEqual(finite(np.int64(0)), 0)

    def test_day_identity_qc_gaps_latest_duplicate_and_no_mutation(self):
        first = row(descriptor={'Steps': 1})
        latest = row(descriptor={'Steps': 2}); latest['Metadata']['DailySummaryTimestamp'] = first['StartTime'] + 1
        older = row(descriptor={'Steps': 3}); older['StartTime'] -= 100
        no_timestamp = row(day='2026-06-03', descriptor={'Steps': 4}); no_timestamp.pop('StartTime')
        no_timestamp['Metadata'].pop('QualityControl')
        no_timestamp.update(Data=np.empty((0, 0)), Missing=np.empty((0, 0)), ChannelNames=[])
        data = {'DailyActivity': [latest, first, older, no_timestamp, row(day='bad'), row(day='2026-06-02', included=False)]}
        before = copy.deepcopy(data)
        result = metrics(data)['steps']['points']
        self.assertEqual(result, [{'day': '2026-06-01', 'value': 2}, {'day': '2026-06-03', 'value': 4}])
        np.testing.assert_equal(data['DailyActivity'][0]['Data'], before['DailyActivity'][0]['Data'])
        self.assertEqual(data['DailyActivity'][0]['Descriptor'], before['DailyActivity'][0]['Descriptor'])
        equal = row(descriptor={'Steps': 9})
        self.assertEqual(metrics({'DailyActivity': [first, equal]})['steps']['points'][0]['value'], 9)
        ready = row(descriptor={'TemperatureDeviation': -.5, 'TemperatureTrendDeviation': -.2})
        self.assertEqual(metrics({'DailyReadiness': [ready]})['temperature']['points'][0]['value'], -.5)

    def test_main_sleep_duplicates_naps_masked_samples(self):
        night = row(); night['Missing'][1, 0] = 1; night['Data'][2, 1] = np.nan; night['Data'][0, 1] = 0
        nap = row(start=night['StartTime'] - 10000, descriptor={'BedtimeStart': 1, 'BedtimeEnd': 300, 'TotalSleepDuration': 100})
        report = build_report({'Sleep': [nap, night, night]})
        result = {m['key']: m['points'] for m in report['metrics']}
        self.assertEqual(result['sleep_duration'][0]['value'], 1/6)
        self.assertEqual(result['sleep_hr'][0]['value'], 70)
        self.assertEqual(result['sleep_hrv'][0]['value'], 15)
        self.assertEqual(report['provenance']['sleep_sessions'], 2)
        # Put shorter session later to exercise the nonreplacement decision.
        nap['Descriptor']['BedtimeStart'] = night['StartTime'] + 10000
        nap['Descriptor']['BedtimeEnd'] = night['StartTime'] + 10300
        self.assertEqual(metrics({'Sleep': [night, nap]})['sleep_duration']['points'][0]['value'], 1/6)
        self.assertEqual(metrics({'Sleep': [row(included=False), row(day='bad')]})['sleep_hr']['points'], [])

    def test_sample_shapes_missing_channels_duplicates_invalids(self):
        value = row(); value['Time'] = [1, 1, np.nan]
        self.assertEqual(sample_mean(value, 'Heart Rate'), 70)
        self.assertIsNone(sample_mean(value, 'absent'))
        value['Missing'][1, 0] = 1
        self.assertIsNone(sample_mean(value, 'Heart Rate'))
        value = row(); value['Data'][:, 0] = 0; value['Data'][:, 1] = -1
        self.assertIsNone(sample_mean(value, 'Heart Rate'))
        self.assertIsNone(sample_mean(value, 'Heart Rate Variability'))
        value['ChannelNames'] = ['Heart Rate']
        with self.assertRaises(ValueError): sample_mean(value, 'Heart Rate')
        value = row(); value['Missing'] = np.zeros((1, 1))
        with self.assertRaises(ValueError): sample_mean(value, 'Heart Rate')
        value = row(); value.pop('Missing')
        self.assertEqual(sample_mean(value, 'Heart Rate'), 70)

    def test_bounds_fallbacks_invalid_and_summary_only(self):
        value = row(descriptor={})
        self.assertEqual(sleep_bounds(value), (value['StartTime'], value['StartTime'] + 900))
        value['Descriptor']['BedtimeStart'] = value['StartTime'] + 10
        self.assertEqual(sleep_bounds(value)[0], value['StartTime'] + 10)
        value['Descriptor'] = {'BedtimeEnd': value['StartTime'] + 500}
        self.assertEqual(sleep_bounds(value)[1], value['StartTime'] + 500)
        value['Time'] = [1, 2, 3]; value['SamplingRate'] = -1
        self.assertIsNone(sleep_bounds(value))
        value['SamplingRate'] = None
        self.assertIsNone(sleep_bounds(value))
        value['Data'] = np.empty((0, 2)); value['Time'] = []; value['Missing'] = np.empty((0, 2))
        self.assertIsNone(sleep_bounds(value))
        value['Descriptor'] = {'BedtimeStart': 10, 'BedtimeEnd': 2}
        self.assertIsNone(sleep_bounds(value))
        self.assertEqual(metrics({'Sleep': [value]})['sleep_duration']['points'], [])
        value['Descriptor'] = {'BedtimeStart': 1, 'BedtimeEnd': 2, 'Efficiency': 80}
        value['Missing'] = np.empty((0, 2))
        self.assertEqual(metrics({'Sleep': [value]})['sleep_efficiency']['points'][0]['value'], 80)

    def test_all_timestamp_samples_not_sleep_only_and_null_gaps(self):
        awake = row(day='wrong'); awake['Time'] = [100, 400, 700]; awake['SamplingRate'] = -1
        awake['Missing'][1, 0] = 1; awake['Data'][2, 0] = 0
        night = row(start=1000); night['ChannelNames'] = ['Heart Rate', 'HRV']
        daytime_hrv = row(start=2000)
        duplicated = copy.deepcopy(awake); duplicated['Data'][0, 0] = 65
        data = {'HeartRate': [awake, duplicated], 'Sleep': [night], 'Daytime': [daytime_hrv],
                'Empty': [{'ChannelNames': []}]}
        result = metrics(data)
        heart = result['heart_rate']
        self.assertEqual([p['time'] for p in heart['points']], [100, 400, 700, 1000, 1300, 1600, 2000, 2300, 2600])
        self.assertEqual([p['value'] for p in heart['points'][:3]], [65, None, None])
        self.assertEqual(heart['points'][0]['day'], '1969-12-31')
        self.assertEqual(heart['points'][0]['source'], 'HeartRate')
        self.assertEqual(heart['source_streams'], ['Daytime', 'HeartRate', 'Sleep'])
        self.assertEqual(heart['coverage']['observed_points'], 7)
        self.assertEqual(heart['resolution'], 'sample')
        self.assertEqual(heart['max_gap_seconds'], 900)
        hrv = result['hrv']
        self.assertEqual(hrv['source_streams'], ['Daytime', 'HeartRate', 'Sleep'])
        self.assertIn(2000, [p['time'] for p in hrv['points']])
        self.assertEqual(hrv['source_interval_seconds'], [300])
        self.assertFalse(metrics({})['heart_rate']['available'])
        json.dumps(build_report(data), allow_nan=False)

    def test_complementary_hr_streams_and_finite_duplicate_priority(self):
        source = row(); source['Time'] = [1, 2, 3]
        source['Data'][:, 0] = [65, 0, 75]
        supplement = row(); supplement['Time'] = [1, 2, 4]
        supplement['Data'][:, 0] = [55, 60, 80]
        supplement['Missing'][0, 1] = 1
        source['Missing'][1, 1] = 1
        for data in [{'HeartRate': [source], 'Sleep': [supplement]},
                     {'Sleep': [supplement], 'HeartRate': [source]}]:
            result = sample_metric(data, 'Heart Rate')
            self.assertEqual([p['value'] for p in result['points']], [65, 60, 75, 80])
            self.assertEqual([p['source'] for p in result['points']], ['HeartRate', 'Sleep', 'HeartRate', 'Sleep'])
            hrv = sample_metric(data, 'Heart Rate Variability')
            self.assertEqual([p['value'] for p in hrv['points']], [20, 30, 40, 40])
        # An overlapping masked cell must not erase an eligible observation.
        masked = copy.deepcopy(supplement); masked['Missing'][:, 0] = 1
        self.assertEqual(sample_metric({'Sleep': [supplement, masked]}, 'Heart Rate')['coverage']['observed_points'], 3)

    def test_sample_invalid_times_values_masks_and_shapes(self):
        value = row(); value['Time'] = [np.nan, 1, 2]
        value['Data'][1, 1] = -1; value['Data'][2, 1] = 0
        result = sample_metric({'Sleep': [value]}, 'Heart Rate Variability')
        self.assertEqual([p['value'] for p in result['points']], [None, 0])
        value['Missing'][2, 1] = 1
        self.assertFalse(sample_metric({'Sleep': [value]}, 'Heart Rate Variability')['available'])
        value['ChannelNames'] = ['HRV']
        with self.assertRaises(ValueError): sample_metric({'Sleep': [value]}, 'Heart Rate Variability')
        value = row(); value['Missing'] = np.zeros((1, 1))
        with self.assertRaises(ValueError): sample_metric({'HeartRate': [value]}, 'Heart Rate')
        value = row(); value.pop('Missing'); value.pop('SamplingRate'); value['Time'] = [1, 2, 3]
        self.assertEqual(sample_metric({'HeartRate': [value]}, 'Heart Rate')['coverage']['observed_points'], 3)

    def test_total_sleep_naps_dedup_overlap_and_unknown_not_zero(self):
        night = row()
        nap = row(start=night['StartTime'] + 10000)
        nap['Descriptor']['TotalSleepDuration'] = 300
        result = metrics({'Sleep': [night, nap, nap]})
        self.assertEqual(result['sleep_duration']['points'][0]['value'], 600/3600)
        self.assertEqual(result['sleep_total']['points'][0]['value'], 900/3600)
        nap['Descriptor'].pop('TotalSleepDuration')
        self.assertEqual(metrics({'Sleep': [night, nap]})['sleep_total']['points'], [])
        nap['Descriptor']['TotalSleepDuration'] = -1
        self.assertEqual(metrics({'Sleep': [night, nap]})['sleep_total']['points'], [])
        nap['Descriptor']['TotalSleepDuration'] = 10000
        self.assertEqual(metrics({'Sleep': [night, nap]})['sleep_total']['points'], [])
        nap['Descriptor']['TotalSleepDuration'] = 0
        self.assertEqual(metrics({'Sleep': [night, nap]})['sleep_total']['points'][0]['value'], 600/3600)
        overlap = row(start=night['StartTime'] + 300)
        report = build_report({'Sleep': [night, overlap]})
        self.assertEqual(report['provenance']['incomplete_sleep_total_days'], ['2026-06-01'])
        self.assertEqual(next(m for m in report['metrics'] if m['key'] == 'sleep_total')['points'], [])
        invalid = row(); invalid['Descriptor']['BedtimeEnd'] = 0
        self.assertEqual(total_sleep_rows([night, invalid])[0], {})
        self.assertEqual(total_sleep_rows([row(included=False), row(day='invalid')]), ({}, []))



class ApiTests(unittest.TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, configuration={'ReadOnly': True})
        self.storage = tempfile.TemporaryDirectory()
        patch.dict('os.environ', {'DATASERVER_PATH': self.storage.name + '/'}).start()
        self.permission = patch('modules.Database.checkAccessPermission', return_value={'View': True}).start()
        self.participant = patch.object(api.models.Participant, 'find', return_value=SimpleNamespace(uid='participant')).start()
        patch('modules.Database.retrieveProcessingSettings', return_value=({}, None)).start()
        self.loader = patch('modules.OURA.DataManager.loadOuraRingData', return_value={'Sleep': [row()]}).start()

    def tearDown(self):
        patch.stopall(); self.storage.cleanup()

    def request(self, body, authenticated=True):
        request = self.factory.post('/api/queryOuraTimeline', body, format='json')
        if authenticated:
            force_authenticate(request, user=self.user)
        return api.QueryOuraTimeline.as_view()(request)

    def test_auth_strict_input_and_permission_before_loading(self):
        self.assertIn(self.request({'ParticipantId': 'participant'}, False).status_code, [401, 403])
        for body in [[], {}, {'ParticipantId': None}, {'ParticipantId': ''}, {'ParticipantId': 3},
                     {'ParticipantId': 'a' * 129}, {'ParticipantId': 'participant', 'Raw': True}]:
            self.assertEqual(self.request(body).status_code, 400)
        self.loader.assert_not_called()
        self.permission.return_value = None
        self.assertEqual(self.request({'ParticipantId': 'participant'}).status_code, 403)
        self.permission.return_value = {'View': True}; self.participant.return_value = None
        self.assertEqual(self.request({'ParticipantId': 'participant'}).status_code, 403)
        self.loader.assert_not_called()

    def test_viewer_loads_cached_report_permission_rechecked_and_failure_private(self):
        from Server.Middlewares.ReadOnlyAccount import ReadOnlyAccountMiddleware
        from modules.ReportCache import invalidate
        request = self.factory.post('/api/queryOuraTimeline', {'ParticipantId': 'participant'}, format='json')
        request.user = self.user; force_authenticate(request, user=self.user)
        first = ReadOnlyAccountMiddleware(api.QueryOuraTimeline.as_view())(request)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first['Cache-Control'], 'no-store')
        self.assertEqual(first['X-BRAVO-Report-Cache'], 'MISS')
        self.assertEqual(len(json.loads(first.content)['metrics']), len(CATALOG))
        self.assertEqual(self.request({'ParticipantId': 'participant'})['X-BRAVO-Report-Cache'], 'HIT')
        self.assertEqual(self.loader.call_count, 1)
        self.permission.return_value = None
        self.assertEqual(self.request({'ParticipantId': 'participant'}).status_code, 403)
        self.permission.return_value = {'View': True}
        invalidate()
        for error in [ValueError, KeyError, TypeError, OverflowError]:
            self.loader.side_effect = error('private source')
            result = self.request({'ParticipantId': 'participant'})
            self.assertEqual(result.status_code, 503)
            self.assertNotIn('private', str(result.data))
        self.loader.assert_called_with(self.participant.return_value)
