"""Exercise all seven real native parsers with synthetic provider responses."""
import importlib.util
from pathlib import Path
import sys
import types
from datetime import date
import numpy as np
from test_managed_oura import m, DIGEST, Session, Response


def test_real_native_parsers_paginated_and_atomic_collection(monkeypatch):
    monkeypatch.setitem(sys.modules,'Server',types.SimpleNamespace(models=None))
    monkeypatch.setitem(sys.modules,'modules',types.SimpleNamespace(Database=None))
    path=Path(__file__).resolve().parents[2]/'BRAVO/modules/OURA/DataManager.py'
    spec=importlib.util.spec_from_file_location('native_oura_parsers',path)
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    stamp='2025-01-01T00:00:00+00:00'
    common={'id':'synthetic','day':'2025-01-01','timestamp':stamp,'score':90,'contributors':{}}
    activity=dict(common,class_5_min='1'*288,met={'interval':60,'timestamp':stamp,'items':[1]*1440})
    for key in ('active_calories','average_met_minutes','high_activity_met_minutes','medium_activity_met_minutes',
                'low_activity_met_minutes','sedentary_met_minutes','high_activity_time','medium_activity_time',
                'low_activity_time','sedentary_time','resting_time','inactivity_alerts','meters_to_target',
                'target_meters','total_calories','steps','non_wear_time','equivalent_walking_distance'):
        activity[key]=0
    ready=dict(common,temperature_deviation=0,temperature_trend_deviation=None)
    cardio=dict(common,vascular_age=50)
    spo2=dict(common,spo2_percentage={'average':97},breathing_disturbance_index=0)
    stress=dict(common,stress_high=0,recovery_high=0,day_summary='normal')
    heart={'timestamp':stamp,'source':'rest','bpm':60}
    sleep=dict(common,heart_rate={'timestamp':stamp,'items':[60,None]},hrv={'items':[20,None]},
               sleep_phase_5_min='12',movement_30_sec='1'*20,bedtime_start=stamp,bedtime_end='2025-01-01T00:10:00+00:00')
    for key in ('average_breath','average_heart_rate','average_hrv','awake_time','time_in_bed',
                'total_sleep_duration','deep_sleep_duration','light_sleep_duration','rem_sleep_duration',
                'restless_periods','efficiency','latency'):
        sleep[key]=0
    responses=[Response({'id':'account'})]
    for item in (activity,ready,cardio,spo2,stress):responses.append(Response({'data':[item]}))
    # Duplicate heartbeat across pages is retained once, with native zero/missing behavior unchanged.
    responses.extend([Response({'data':[heart],'next_token':'second'}),Response({'data':[heart]}),Response({'data':[sleep]})])
    session=Session(*responses)
    data,receipt=m.collect(native.OuraRingAPI,'synthetic',{'account_id_sha256':DIGEST,'start_date':'2025-01-01','timezone':'UTC'},today=date(2025,1,1),session=session)
    assert receipt['counts']=={stream:1 for stream in m.STREAMS}
    assert len(session.calls)==9
    assert data['DailyActivity'][0]['Data'].shape==(1440,2)
    assert data['DailyActivity'][0]['Descriptor']['Steps']==0
    assert data['DailyReadiness'][0]['Descriptor']['TemperatureTrendDeviation'] is None
    assert data['Sleep'][0]['Data'].shape==(2,4)
    assert np.array_equal(data['Sleep'][0]['Missing'][:,:2],[[0,0],[1,1]])
    assert data['HeartRate'][0]['Data'][0,0]==60
