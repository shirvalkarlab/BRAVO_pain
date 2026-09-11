"""Exercise exact native decoder/saver starts with synthetic packets and clocks."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from modules import PerceptClock as clock, PerceptClockData as adapter
from modules.MedtronicPercept import Percept, IndefiniteStream, BrainSenseStream

T = 1577836800.0
TD = 'MedtronicBrainSenseTimeDomain'
POWER = 'MedtronicBrainSensePowerDomain'
INDEF = 'MedtronicIndefiniteStream'


def td(seconds=10800, tick=1250, counter=200, count=3, **extra):
    return {'FirstPacketDateTime': datetime.fromtimestamp(T+seconds, timezone.utc).isoformat(),
            'FirstPacketDateTimeBlockId': 7, 'FirstPacketDateTimeOffsetInSeconds':counter,
            'GlobalSequences': ','.join(str(i+1) for i in range(count)),
            'GlobalPacketSizes': ','.join('2' for _ in range(count)),
            'TicksInMses': ','.join(str(tick+i*250) for i in range(count)),
            'TimeDomainData':list(range(count*2)), 'SampleRateInHz':'250',
            'Channel':'ONE_THREE_LEFT', **extra}


def power(seconds=10800, tick=1250, counter=200):
    stream = td(seconds,tick,counter)
    stream.update(SampleRateInHz='4', TherapySnapshot={'Left':{}},
                  LfpData=[{'Left':{'LFP':i,'mA':0}, 'Right':{'LFP':0,'mA':0},
                            'Seq':i+1,'TicksInMs':tick+i*250} for i in range(4)])
    return stream


def payload(**streams):
    return {'SessionDate':'2020-01-01T00:01:40Z','SessionEndDate':'2020-01-01T00:05:20Z',
            'DeviceInformation':{'Initial':{'DeviceDateTime':'2020-01-01T03:00:00Z','DeviceDateTimeBlockId':7,'DeviceDateTimeOffsetInSeconds':100},
                                 'Final':{'DeviceDateTime':'2020-01-01T03:03:20Z','DeviceDateTimeBlockId':7,'DeviceDateTimeOffsetInSeconds':300}}, **streams}


class NativeClockBoundaryTests(unittest.TestCase):
    def index(self, raw):
        before=json.dumps(raw,sort_keys=True)
        index=adapter.extract_source_index(raw)
        self.assertEqual(before,json.dumps(raw,sort_keys=True))
        self.assertEqual(set(index['native_start_rule_hashes']),{'Percept.py','IndefiniteStream.py','BrainSenseStream.py'})
        source={'device':'synthetic','index':index,'uid':'synthetic'}
        earlier={'device':'synthetic','uid':'earlier','index':{'version':clock.VERSION,
            'anchors':[{'phase':'Final','block':7,'counter':100,'utc':T+100}]}}
        return index,source,clock.build_index([earlier,source])

    def test_td_and_power_fraction_and_alignment_follow_actual_decoder_and_saver(self):
        raw=payload(BrainSenseTimeDomain=[td(),td(10802,2250,201),td(10850,3250,250)],
                    BrainSenseLfp=[power(),power(10802,2250,201),power(10850,3250,250)])
        index,source,anchors=self.index(raw)
        aliases=index['decoded_start_aliases']
        self.assertEqual(len(aliases),6)
        for kind in (TD,POWER):
            self.assertEqual([a['sample_start_offset_seconds'] for a in aliases if a['recording_type']==kind],
                             [.25,-.75,0.])
        for fix in (False,True):
            actual_td=Percept.extractTimeDomainStreamingData(deepcopy(raw),{})['StreamingTD']
            actual_power=Percept.extractPowerDomainStreamingData(deepcopy(raw),{})['StreamingPower']
            td_records,power_records=BrainSenseStream.saveBrainSenseStreams(actual_td,actual_power,FixBreaking=fix)
            for kind,rows in [(TD,td_records),(POWER,power_records)]:
                for row in rows:
                    got=clock.recover_start(anchors,source,row['StartTime'],kind)
                    self.assertIsNotNone(got['t'])
                    self.assertEqual(got['t'],T+100+(got['counter']-100)*1.1+got['sample_start_offset_seconds'])

    def test_td_marker_survives_dropped_stream_outlier_and_tick_reordering(self):
        raw=payload(BrainSenseTimeDomain=[td(counter=199,count=1),
                    td(GlobalSequences='5,1,2',TicksInMses='1250,1500,1750'),
                    td(10802,2250,202,TicksInMses='2500,2250,2750')])
        index,_,_=self.index(raw)
        aliases=index['decoded_start_aliases']
        self.assertEqual([(a['counter'],a['sample_start_offset_seconds']) for a in aliases],[(200,.5),(202,-.75)])
        self.assertGreater(index['decoded_start_diagnostics'][0]['native_diagnostic_lines'],0)

    def test_tick_rollover_retains_original_coordinate(self):
        raw=payload(BrainSenseTimeDomain=[td(tick=3276250),td(10801,450,201)])
        index,source,anchors=self.index(raw)
        aliases=index['decoded_start_aliases']
        self.assertEqual(aliases[1]['sample_start_offset_seconds'],.25)
        self.assertEqual(clock.recover_start(anchors,source,aliases[1]['decoded_raw'],TD)['t'],T+211.35)

    def test_indefinite_last_channel_and_normalized_tick_define_saved_start(self):
        for count in (3,4):
            raw=payload(IndefiniteStreaming=[td(tick=1250),td(tick=3277250,count=count,Channel='ONE_THREE_RIGHT')])
            index,source,anchors=self.index(raw)
            aliases=index['decoded_start_aliases']
            self.assertEqual(len(aliases),1)
            self.assertAlmostEqual(aliases[0]['sample_start_offset_seconds'],.45,places=6)
            decoded=Percept.extractIndefiniteStreaming(deepcopy(raw),{})['IndefiniteStream']
            actual=IndefiniteStream.saveIndefiniteStreams(decoded)[0]
            self.assertAlmostEqual(clock.recover_start(anchors,source,actual['StartTime'],INDEF)['t'],T+210.45)

    def test_missing_coordinates_failure_isolation_and_absent_modalities(self):
        raw=payload(BrainSenseTimeDomain=[td(FirstPacketDateTimeBlockId=0)],BrainSenseLfp=[{}])
        index,_,_=self.index(raw)
        self.assertEqual(index['decoded_start_aliases'],[])
        self.assertEqual(index['decoded_start_diagnostics'][0]['unresolved_coordinates'],1)
        self.assertEqual(index['decoded_start_diagnostics'][1]['status'],'native_decode_failed')
        self.assertEqual(len(index['anchors']),2)
        for raw in (None,{},payload(IndefiniteStreaming=[]),payload(BrainSenseTimeDomain=None)):
            self.assertEqual(adapter.extract_source_index(raw)['decoded_start_aliases'],[])
        with patch.object(IndefiniteStream,'saveIndefiniteStreams',return_value=[]):
            index=adapter.extract_source_index(payload(IndefiniteStreaming=[td()]))
        self.assertEqual(index['decoded_start_diagnostics'][0]['exception_type'],'ValueError')
        for original,decoded in [(None,T),(T,None),(float('inf'),T)]:
            stream=td();stream[adapter._NATIVE_ORIGINAL]=original
            self.assertIsNone(adapter._start_alias(stream,decoded,TD,'BrainSenseTimeDomain'))
