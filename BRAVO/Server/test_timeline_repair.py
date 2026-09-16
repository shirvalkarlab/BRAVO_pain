import copy
from django.test import SimpleTestCase
from modules.Therapy import sameElectrodeSide, createTherapyTimeline
from modules.MedtronicPercept.ChronicBrainSense import channelTherapyNote


class TherapyTimelineSessionTests(SimpleTestCase):
    @staticmethod
    def history_at(*dates):
        electrode = {'Id': 'synthetic-left', 'Hemisphere': 'Left', 'Target': 'Left STN'}
        device = {'Id': 'synthetic-device', 'Date': dates[0], 'Electrodes': [electrode]}
        history = [
            {'Id': f'therapy-{i}', 'SourceId': f'source-{i}', 'Date': date,
             'GroupId': 'A', 'GroupType': 'Standard', 'Type': 'Post-visit Therapy',
             'Label': '',
             'StimulationSettings': [{'Electrode': electrode, 'Amplitude': 1.5 + i,
                                      'Frequency': 130, 'PulseWidth': 60,
                                      'Contacts': [{'Contact': 1, 'Polarity': 'Cathode'}]}],
             'AdaptiveSettings': [{'Mode': 'Dual threshold', 'Thresholds': [10, 20]}]}
            for i, date in enumerate(dates)
        ]
        return {'TherapyConfiguration': [{'Device': device, 'History': history}],
                'TherapyDevices': [device], 'TherapyModification': []}

    def test_single_session_retains_processed_stimulation_and_adaptive_settings(self):
        history = self.history_at(1700000000)
        original = copy.deepcopy(history)

        timeline = createTherapyTimeline(history)

        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0]['Date'], 1700000000)
        group = timeline[0]['Therapies'][0]
        self.assertEqual(group['GroupId'], 'A')
        self.assertEqual(len(group['Processed']), 1)
        therapy = group['Processed'][0]
        self.assertEqual(therapy['SourceId'], 'source-0')
        self.assertEqual(therapy['TherapyIds'], ['therapy-0'])
        self.assertEqual(therapy['Device']['Id'], 'synthetic-device')
        stimulation = therapy['Stimulation'][0][0]
        self.assertEqual(stimulation['Amplitude'], 1.5)
        self.assertEqual(stimulation['Frequency'], 130)
        self.assertEqual(stimulation['PulseWidth'], 60)
        self.assertEqual(stimulation['Contacts'], [{'Contact': 1, 'Polarity': 'Cathode'}])
        self.assertEqual(stimulation['Electrode']['Target'], 'Left STN')
        self.assertEqual(therapy['Adaptive'][0][0]['Thresholds'], [10, 20])
        self.assertEqual(timeline[0]['DefinedTherapies'][0]['Post'], ['therapy-0'])
        self.assertEqual(history, original)

    def test_single_device_date_without_therapy_returns_one_empty_entry(self):
        history = {'TherapyConfiguration': [],
                   'TherapyDevices': [{'Id': 'synthetic-device', 'Date': 1700000000,
                                       'Electrodes': []}],
                   'TherapyModification': []}
        self.assertEqual(createTherapyTimeline(history), [
            {'Date': 1700000000, 'Therapies': [], 'DefinedTherapies': []}])

    def test_close_final_session_keeps_existing_deep_copy_behavior(self):
        start = 1700000000
        history = self.history_at(start, start + 24 * 3600, start + 25 * 3600)
        original = copy.deepcopy(history)

        timeline = createTherapyTimeline(history)

        # The legacy final-copy rule carries the preceding entry, including its date.
        self.assertEqual([entry['Date'] for entry in timeline],
                         [start, start + 24 * 3600, start + 24 * 3600])
        self.assertEqual(timeline[-1], timeline[-2])
        self.assertIsNot(timeline[-1], timeline[-2])
        last = timeline[-1]['Therapies'][0]['Processed'][0]
        preceding = timeline[-2]['Therapies'][0]['Processed'][0]
        last['Stimulation'][0][0]['Contacts'][0]['Contact'] = 9
        last['Adaptive'][0][0]['Thresholds'][0] = 99
        self.assertEqual(preceding['Stimulation'][0][0]['Contacts'][0]['Contact'], 1)
        self.assertEqual(preceding['Adaptive'][0][0]['Thresholds'], [10, 20])
        self.assertEqual(history, original)

    def test_final_sessions_at_or_above_twelve_hours_remain_distinct(self):
        start = 1700000000
        for separation in (12 * 3600, 12 * 3600 + 1):
            with self.subTest(separation=separation):
                history = self.history_at(start, start + separation)
                timeline = createTherapyTimeline(history)
                self.assertEqual([entry['Date'] for entry in timeline],
                                 [start, start + separation])
                self.assertEqual([entry['DefinedTherapies'][0]['Post'] for entry in timeline],
                                 [['therapy-0'], ['therapy-1']])
                self.assertEqual([
                    entry['Therapies'][0]['Processed'][0]['Stimulation'][0][0]['Amplitude']
                    for entry in timeline], [1.5, 2.5])


class TherapyLateralityTests(SimpleTestCase):
    def test_blank_hemispheres_do_not_mix_left_and_right(self):
        self.assertFalse(sameElectrodeSide({'Hemisphere':'','Target':'Left GPi'},{'Hemisphere':'','Target':'Right VIM'}))
        self.assertTrue(sameElectrodeSide({'Hemisphere':'','Target':'Left GPi'},{'Hemisphere':'','Target':'Left STN'}))
        self.assertFalse(sameElectrodeSide({'Hemisphere':''},{'Hemisphere':''}))
        self.assertEqual(createTherapyTimeline({'TherapyConfiguration':[],'TherapyDevices':[]}),[])

    def test_channel_notes_keep_pairing_without_mutating_shared_history(self):
        left={'TherapyId':'left','Electrode':{'Target':'Left GPi','Hemisphere':''}}
        right={'TherapyId':'right','Electrode':{'Target':'Right VIM','Hemisphere':''}}
        note={'Stimulation':[[left,right],[left,right]],'Adaptive':[[{'side':'left'},{'side':'right'}],[{'side':'left'},{'side':'right'}]]}
        before=copy.deepcopy(note)
        l=channelTherapyNote(note,'LeftHemisphere LFP')
        r=channelTherapyNote(note,'RightHemisphere Amplitude')
        self.assertEqual(l,{'Stimulation':[left],'Adaptive':{'side':'left'}})
        self.assertEqual(r,{'Stimulation':[right],'Adaptive':{'side':'right'}})
        l['Stimulation'][0]['Electrode']['Target']='Changed'
        self.assertEqual(note,before)
        self.assertEqual(channelTherapyNote(None,'LeftHemisphere LFP'),{'Stimulation':{},'Adaptive':{}})

class ImplantBoundaryTests(SimpleTestCase):
    def test_rejects_benchtop_and_accepts_only_reviewed_leads(self):
        from modules.RCS08DataPolicy import source_exclusion
        leads=[{'Hemisphere':'HemisphereLocationDef.Left','LeadLocation':'LeadLocationDef.Gpi','Model':'LeadModelDef.LEAD_B33015'},
               {'Hemisphere':'HemisphereLocationDef.Right','LeadLocation':'LeadLocationDef.Vim','Model':'LeadModelDef.LEAD_B33015'}]
        report={'LeadConfiguration':{'Final':leads}}
        self.assertIsNone(source_exclusion(report))
        report['DeviceInformation']={'Final':{'DeviceName':'Percept benchtop'}}
        self.assertIn('Benchtop',source_exclusion(report))
        self.assertIsNotNone(source_exclusion({}))

    def test_trims_only_preimplant_samples_and_preserves_valid_zero(self):
        import numpy as np
        from modules.RCS08DataPolicy import IMPLANT_DAY, filter_decoded_entries
        recording={'Time':np.array([IMPLANT_DAY-1,IMPLANT_DAY,IMPLANT_DAY+1]),'Data':np.array([[99,8],[0,0],[3,4]])}
        entries={'ChronicRecordings':[{'recording':recording,'date':IMPLANT_DAY-1,'metadata':{}}],
                 'TherapyChangeHistory':[{'date':IMPLANT_DAY-10},{'date':IMPLANT_DAY+2}]}
        removed=filter_decoded_entries(entries)
        np.testing.assert_array_equal(recording['Data'],[[0,0],[3,4]])
        np.testing.assert_array_equal(recording['Time'],[IMPLANT_DAY,IMPLANT_DAY+1])
        self.assertEqual(removed,{'TherapyChangeHistory':1,'ChronicSamples':1})

class NeuralExportTests(SimpleTestCase):
    def test_bilateral_channels_keep_separate_times_power_and_amplitude(self):
        from unittest.mock import patch
        from modules.DataAnalysis import downloadChronicNeuralActivity
        segment={'Time':[10,20], 'ChannelNames':['Right VIM LFP','Right VIM Amplitude','Left GPi LFP','Left GPi Amplitude'],
                 'Data':[[1,2],[0,3],[4,5],[6,7]],'Device':{'Heritage':'Right IPG'},'TherapyString':'Reviewed','RecordingString':'Recorded'}
        with patch('modules.DataAnalysis.queryChronicNeuralActivity',return_value={'ChronicNeuralActivity':[segment]}):
            rows=downloadChronicNeuralActivity('participant',{}).to_dict('records')
        self.assertEqual([r['Time'] for r in rows],[10,20,10,20])
        self.assertEqual([r['Power'] for r in rows],[1,2,4,5])
        self.assertEqual([r['Amplitude'] for r in rows],[0,3,6,7])
        self.assertTrue(all('Right VIM' in r['ChannelName'] for r in rows[:2]))
        self.assertTrue(all('Left GPi' in r['ChannelName'] for r in rows[2:]))

class OuraSleepBoundaryTests(SimpleTestCase):
    def test_last_sleep_phase_and_zero_hrv_are_preserved(self):
        from unittest.mock import patch
        from modules.OURA.DataManager import OuraRingAPI
        item={key:None for key in ('average_breath','average_heart_rate','average_hrv','awake_time','time_in_bed','total_sleep_duration','deep_sleep_duration','light_sleep_duration','rem_sleep_duration','restless_periods','efficiency','latency')}
        item.update(day='2025-07-20',bedtime_start='2025-07-20T00:00:00-07:00',bedtime_end='2025-07-20T00:10:00-07:00',
                    heart_rate={'timestamp':'2025-07-20T00:00:00-07:00','items':[60,None]},hrv={'items':[0,None]},
                    movement_30_sec='0'*20,sleep_phase_5_min='12')
        api=OuraRingAPI('dummy')
        with patch.object(api,'query',return_value={'data':[item]}): rows=api.getSleep('2025-07-20','2025-07-21')
        self.assertEqual(rows[0]['Data'].tolist(),[[60,0,1,0],[-1,-1,2,0]])
        self.assertEqual(rows[0]['Missing'].tolist(),[[0,0,0,0],[1,1,0,0]])
