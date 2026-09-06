import copy
import datetime as dt
import unittest
import numpy as np
import pytest
from modules.OURA.QualityControl import apply_quality_control, policy, timeline_series, PACIFIC

pytestmark = pytest.mark.usefixtures("synthetic_oura_policy")


def record(day, times, values, kind='HeartRate'):
    data = np.asarray(values, dtype=float).reshape((-1, 1))
    return {'Metadata': {'DayLabel': day}, 'StartTime': times[0] if times else 0,
            'Time': times, 'SamplingRate': -1, 'ChannelNames': ['Heart Rate Variability'],
            'Data': data, 'Missing': np.zeros_like(data),
            'Descriptor': {'AverageHRV': 0} if kind != 'HeartRate' else {}}


class OuraQCTests(unittest.TestCase):
    def test_exact_timestamp_boundaries_and_original_preserved(self):
        _, rule = policy()
        start = dt.datetime.fromisoformat(rule['start_inclusive']).timestamp()
        end = dt.datetime.fromisoformat(rule['end_exclusive']).timestamp()
        raw = {'HeartRate': [record('2026-04-01', [start-.001,start,end-.001,end], [0,99,98,4])]}
        before = copy.deepcopy(raw)
        clean, audit = apply_quality_control(raw)
        np.testing.assert_array_equal(raw['HeartRate'][0]['Data'], before['HeartRate'][0]['Data'])
        np.testing.assert_equal(clean['HeartRate'][0]['Data'][:,0], [0,np.nan,np.nan,4])
        self.assertEqual(audit[0]['window_excluded_samples'], 2)
        self.assertEqual(timeline_series(clean)[0]['Data'][0], [0,None,None,4])

    def test_partial_handoff_day_keeps_samples_but_not_summary(self):
        t=dt.datetime(2026,5,27,14,tzinfo=PACIFIC).timestamp()
        clean,audit=apply_quality_control({'Sleep':[record('2026-05-27',[t],[0],'Sleep')]})
        self.assertFalse(audit[0]['summary_included'])
        self.assertEqual(clean['Sleep'][0]['Descriptor'], {})
        self.assertEqual(timeline_series(clean)[0]['Data'], [[0]])

    def test_day_boundaries_and_calendar_labels(self):
        rows=[record(day,[],[],'Sleep') for day in ['2026-04-29','2026-04-30','2026-05-27','2026-05-28']]
        clean,audit=apply_quality_control({'Sleep':rows})
        self.assertEqual([r['summary_included'] for r in audit],[True,False,False,True])
        actual=[dt.datetime.fromtimestamp(t,PACIFIC).date().isoformat() for t in timeline_series(clean)[0]['Time']]
        self.assertEqual(actual,['2026-04-29','2026-04-30','2026-05-28'])
        self.assertEqual(timeline_series(clean)[0]['Data'],[[0,None,0]])

    def test_missing_mask_and_zero_kept_distinct(self):
        t=dt.datetime(2026,6,1,tzinfo=PACIFIC).timestamp()
        row=record('2026-06-01',[t,t+1,t+2],[0,-1,50],'Sleep')
        row['Missing'][1,0]=1
        clean,_=apply_quality_control({'Sleep':[row]})
        self.assertEqual(timeline_series(clean)[1]['Data'],[[0,None,50]])

    def test_missing_sleep_phase_does_not_drop_or_shift_samples(self):
        t=dt.datetime(2026,6,1,tzinfo=PACIFIC).timestamp()
        row=record('2026-06-01',[t,t+1,t+2],[1,-1,4],'Sleep')
        row['ChannelNames']=['Sleep Phase']; row['Missing'][1,0]=1
        clean,_=apply_quality_control({'Sleep':[row]})
        plot=timeline_series(clean)[1]
        self.assertEqual(plot['Data'],[['deep',None,'awake']])
        self.assertEqual(plot['Time'],[t,t+1,t+2])

    def test_missing_day_not_inferred_from_chunk_time(self):
        row=record('not-a-day',[],[],'Sleep')
        clean,audit=apply_quality_control({'Sleep':[row]})
        self.assertEqual(clean['Sleep'],[])
        self.assertEqual(audit[0]['summary_reason'],'Missing/invalid Oura day')

    def test_invalid_time_masked_and_shape_mismatch_rejected(self):
        row=record('2026-06-01',[float('nan')],[60])
        clean,audit=apply_quality_control({'HeartRate':[row]})
        self.assertEqual(clean['HeartRate'],[])
        self.assertEqual(audit[0]['invalid_time_samples'],1)
        row['Time']=[]
        with self.assertRaises(ValueError): apply_quality_control({'HeartRate':[row]})
