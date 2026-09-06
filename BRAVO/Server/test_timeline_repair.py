import copy
from django.test import SimpleTestCase
from modules.Therapy import sameElectrodeSide, createTherapyTimeline
from modules.MedtronicPercept.ChronicBrainSense import channelTherapyNote

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
