"""Synthetic original-report contracts; expected values independent of production data."""
import copy
import importlib.util
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
from modules import AdityaNeuralSettings as n


def channel(side='Left', **changes):
    value={'HemisphereLocation': f'HemisphereLocationDef.{side}',
        'ElectrodeState':[{'Electrode':'ElectrodeDef.SenSight_2a','ElectrodeStateResult':'ElectrodeStateDef.Negative'},
                          {'Electrode':'ElectrodeDef.Case','ElectrodeStateResult':'ElectrodeStateDef.Positive'}],
        'PulseWidthInMicroSecond':80,'RateInHertz':60,'SuspendAmplitudeInMilliAmps':2,
        'LowerLimitInMilliAmps':0.5,'UpperLimitInMilliAmps':3,
        'Mode':'AdaptiveModeDef.DUAL_THRESHOLD_DIRECT','AdaptiveTherapyStatus':'ADBSStatusDef.RUNNING',
        'LowerLfpThreshold':100,'UpperLfpThreshold':200,'TransitionUpInMilliSeconds':20000,
        'TransitionDownInMilliSeconds':10000,
        'SensingSetup':{'FrequencyInHertz':25.04,'AveragingDurationInMilliSeconds':4000,
                        'ChannelSignalResult':{'Channel':'SensingChannelDef.ZERO_TWO_LEFT'}}}
    if side=='Right':value['GangedToHemisphere']='HemisphereLocationDef.Left'
    value.update(changes)
    return value


def group(**changes):
    value={'GroupId':'GroupIdDef.GROUP_B','ActiveGroup':True,
        'ProgramSettings':{'SensingChannel':[channel(),channel('Right')]},
        'GroupSettings':{'Cycling':{'Enabled':False}}}
    value.update(changes)
    return value


def stamp(value):
    return f'1970-01-01T00:{value//60:02}:{value%60:02}Z'


def report():
    return {'SessionDate':stamp(300),'SessionEndDate':stamp(400),
        'Groups':{'Initial':[group()],'Final':[group()]},
        'GroupHistory':[{'SessionDate':stamp(100),'Groups':[group()]},{'SessionDate':stamp(200),'Groups':[group()]}],
        'DiagnosticData':{'EventLogs':[]}}


def segment():
    return {'id':'a','start':150,'end':191,'sensing_contacts':'ZERO_TWO_LEFT','center_frequency_hz':25,
        'points':[{'time':150,'power':123,'amplitude':1.7}], 'settings':{}, 'thresholds':[],
        'mode':'unknown','evidence':'Original native log.'}


def test_source_history_recovers_configuration_with_explicit_delivery_limit():
    raw=report();before=copy.deepcopy(raw)
    result=n.source_context(raw,segment(),'original')
    assert raw==before
    assert result['status']=='source_linked'
    assert result['chronology']=={'bracketed':True,'status_changes_in_interval':0,'continuous_delivery_verified':False,'latest_prior_adaptive_status':None}
    assert [x['time'] for x in result['observations']]==[100,200]
    assert result['source_ids']==['original']
    assert result['mapping_description']=='Left sensing → Left stimulation; Left sensing → Right stimulation (source configuration)'
    assert result['mode_description']=='Dual-threshold adaptive · source configuration'
    left={r['label']:r['value'] for r in result['settings']['left']}
    assert left['Stimulation contacts (lead-local source)']=='2a− C+'
    assert left['Lower threshold (configured)']=='100 LSB'
    assert left['Upper threshold (configured)']=='200 LSB'
    assert left['Adaptive minimum (configured)']=='0.5 mA'
    assert left['Adaptive maximum (configured)']=='3 mA'
    assert left['Paused amplitude (configured)']=='2 mA'
    assert left['Pulse width']=='80 µs' and left['Frequency']=='60 Hz'
    assert left['Sensing averaging duration']=='4000 ms'
    assert 'uninterrupted' in result['message'] and 'No therapy/group' in result['message']
    assert all('_descriptors' not in o for o in result['observations'])


def test_missing_history_limits_remain_absent_and_full_snapshot_is_separately_dated():
    raw=report()
    for h in raw['GroupHistory']:
        for c in h['Groups'][0]['ProgramSettings']['SensingChannel']:
            c.pop('LowerLimitInMilliAmps');c.pop('UpperLimitInMilliAmps')
    result=n.source_context(raw,segment(),'original')
    assert result['status']=='source_linked'
    assert result['observations'][-1]['time']==300
    assert not any(r['label'].startswith('Adaptive minimum') for r in result['observations'][0]['settings']['left'])
    assert any(r['value']=='0.5 mA' for r in result['settings']['left'])


def test_conflicting_configuration_and_inside_events_are_explicit():
    raw=report();raw['GroupHistory'][1]['Groups'][0]['ProgramSettings']['SensingChannel'][0]['LowerLfpThreshold']=110
    raw['DiagnosticData']['EventLogs']=[{'DateTime':stamp(170),'AdbsStatus':'TherapyChangeStatusDef.OFF'},
        {'DateTime':stamp(170),'Other':'ignored'},{'DateTime':'invalid','TherapyStatus':'ON'},
        {'DateTime':stamp(191),'TherapyStatus':'ON'}]
    result=n.source_context(raw,segment(),'original')
    assert result['status']=='conflict' and result['chronology']['status_changes_in_interval']==1
    assert result['message'].startswith('The source settings observations differ')
    inside=segment();inside['end']=250
    result=n.source_context(raw,inside,'original')
    assert 200 in [o['time'] for o in result['observations']]


@pytest.mark.parametrize('change',[{'sensing_contacts':'ONE_THREE_LEFT'},{'center_frequency_hz':None},{'center_frequency_hz':40}])
def test_no_matching_source_configuration_does_not_guess(change):
    s=segment();s.update(change)
    result=n.source_context(report(),s,'source')
    assert result['status']=='conflict' and result['observations']
    assert 'does not match the active settings' in result['message']


def test_inactive_invalid_and_missing_snapshot_times_are_ignored():
    raw=report();raw['SessionDate']='invalid';raw['SessionEndDate']=None
    raw['GroupHistory']=[{'SessionDate':stamp(100),'Groups':[group(ActiveGroup=False)]},
                        {'SessionDate':None,'Groups':[group()]}]
    assert n.source_context(raw,segment(),'source')['status']=='unavailable'
    assert n.epoch(12) is None


def test_source_context_unbounded_does_not_backfill_activation():
    s=segment();s.update(start=20,end=30)
    result=n.source_context(report(),s,'source')
    assert result['chronology']['bracketed'] is False
    assert 'does not bracket' in result['message']
    s.update(start=500,end=550)
    assert n.source_context(report(),s,'source')['chronology']['bracketed'] is False


def test_configuration_retains_unknown_codes_and_sensing_only_semantics():
    g=group();g['ProgramSettings']['RateInHertz']=71
    c=channel();c.pop('Mode');c['AdaptiveTherapyStatus']='ADBSStatusDef.NOT_CONFIGURED'
    c['SensingSetup']={'FrequencyInHertz':None};c.pop('RateInHertz')
    c['ElectrodeState'].append({'Electrode':'unknown','ElectrodeStateResult':'disabled'})
    g['ProgramSettings']['SensingChannel']=[c,{'HemisphereLocation':'unknown'}]
    g['GroupSettings']={'Cycling':{'Enabled':True}}
    settings,descriptors=n._configuration(g)
    assert descriptors[0]['mode']=='Sensing only' and descriptors[0]['adaptive'] is False
    assert {'label':'Frequency','value':'71 Hz'} in settings['left']
    assert not any(r['label'].startswith('Lower threshold') for r in settings['left'])
    assert settings['right']==[] and settings['group'][-1]['value']=='On'
    g['GroupSettings']={}
    c['Mode']='FutureAdaptive.MODE';c['AdaptiveTherapyStatus']=None
    assert n._configuration(g)[1][0]['mode']=='FutureAdaptive.MODE'
    c['SensingSetup']['ChannelSignalResult']={'Channel':'SensingChannelDef.ZERO_TWO_RIGHT'}
    assert n._configuration(g)[1][0]['source']=='right'


def test_link_uses_earliest_contributing_source_per_side_and_preserves_all_points():
    raw=report();s=segment();original=copy.deepcopy(s)
    right=copy.deepcopy(s);right['id']='right'
    timeline={'windows':[{'panels':[{'side':'left','segments':[s]},{'side':'right','segments':[right]}]}],
        'observation_windows':[{'panels':[{'side':'left','segments':[copy.deepcopy(s)]}]}]}
    recordings=[{'SourceId':'later','RecordingId':'r2','SourceSessionEnd':600,'ChannelNames':['LEFT c'],'Time':[150]},
        {'SourceId':'first','RecordingId':'r1','SourceSessionEnd':400,'ChannelNames':['LEFT c'],'Time':[150]},
        {'SourceId':'right-only','RecordingId':'r3','SourceSessionEnd':350,'ChannelNames':['RIGHT c'],'Time':[150]},
        {'Time':[150]},{'SourceId':'bad','Time':['no',None],'ChannelNames':[]}]
    calls=[]
    result=n.link_settings(timeline,recordings,lambda uid:calls.append(uid) or copy.deepcopy(raw))
    assert calls==['first','later','right-only']
    assert s['points']==original['points'] and s['thresholds']==[]
    assert s['mode']=='Dual-threshold adaptive · source configuration'
    assert s['settings_context']['recording_ids']==['r1','r2']
    assert s['settings_context']['source_ids']==['first','later']
    assert s['threshold_status']=='source_recorded' and s['mapping_status']=='source_recorded'
    assert right['settings_context']['source_ids']==['right-only']
    assert result is timeline


def test_link_missing_origin_unavailable_conflict_and_sensing_only_are_safe():
    def run(raw, rec):
        s=segment();timeline={'windows':[{'panels':[{'side':'left','segments':[s]}]}]}
        n.link_settings(timeline,rec,lambda uid:raw)
        return s
    assert 'settings_context' not in run(report(),[])
    rec=[{'SourceId':'source','ChannelNames':['LEFT c'],'Time':[150]}]
    assert run({},rec)['settings_context']['status']=='unavailable'
    raw=report();raw['GroupHistory'][1]['Groups'][0]['ProgramSettings']['SensingChannel'][0]['LowerLfpThreshold']=110
    assert run(raw,rec)['mode']=='unknown'
    raw=report()
    for groups in [raw['Groups']['Initial'],raw['Groups']['Final']]+[h['Groups'] for h in raw['GroupHistory']]:
        for c in groups[0]['ProgramSettings']['SensingChannel']:
            c.pop('Mode');c['AdaptiveTherapyStatus']='ADBSStatusDef.NOT_CONFIGURED'
    assert run(raw,rec)['threshold_status']=='not_configured'


def test_intervening_incompatible_channel_is_a_conflict_and_naive_dates_are_rejected():
    raw=report()
    raw['GroupHistory'].append({'SessionDate':stamp(170),'Groups':[group()]})
    for c in raw['GroupHistory'][-1]['Groups'][0]['ProgramSettings']['SensingChannel']:
        c['SensingSetup']['FrequencyInHertz']=35
    context=n.source_context(raw,segment(),'source')
    assert context['status']=='conflict'
    assert 170 in [o['time'] for o in context['observations']]
    assert n.epoch('1970-01-01T00:01:00') is None


@pytest.mark.parametrize('side_available',[False,True])
def test_exact_prior_adaptive_status_gap_is_explained(side_available):
    raw=report()
    raw['DiagnosticData']['EventLogs']=[{'DateTime':stamp(90),'AdbsStatus':'TherapyChangeStatusDef.ON'},
        {'DateTime':stamp(90),'AdbsStatus':'TherapyChangeStatusDef.OFF'},
        {'DateTime':'invalid','AdbsStatus':'ignored'}]
    if side_available:
        for e in raw['DiagnosticData']['EventLogs'][:2]:e['Hemisphere']='Left'
    context=n.source_context(raw,segment(),'source')
    assert context['chronology']['latest_prior_adaptive_status']['conflict'] is True
    assert context['chronology']['latest_prior_adaptive_status']['time']==90
    assert '1970-01-01T00:01:30Z disagree (OFF/ON)' in context['message']
    assert ('do not identify the hemisphere' in context['message']) is (not side_available)


def test_all_contributing_sources_are_compared_over_only_their_carried_samples():
    s=segment();s['end']=251;s['points'].append({'time':250,'power':140,'amplitude':1.9})
    timeline={'windows':[{'panels':[{'side':'left','segments':[s]}]}]}
    recs=[{'SourceId':'first','SourceSessionEnd':400,'RecordingId':'r1','ChannelNames':['LEFT a'],'Time':[150]},
          {'SourceId':'second','SourceSessionEnd':500,'RecordingId':'r2','ChannelNames':['LEFT a'],'Time':[250]}]
    changed=report()
    for g in [changed['Groups']['Initial'][0],changed['Groups']['Final'][0]]+[h['Groups'][0] for h in changed['GroupHistory']]:
        g['ProgramSettings']['SensingChannel'][0]['LowerLfpThreshold']=120
    n.link_settings(timeline,recs,lambda uid:report() if uid=='first' else changed)
    context=s['settings_context']
    assert context['status']=='conflict' and s['mode']=='unknown'
    assert context['source_ids']==['first','second']
    assert context['source_sample_coverage']==[
        {'source_id':'first','start':150,'end':n.math.nextafter(150,n.math.inf),'samples':1},
        {'source_id':'second','start':250,'end':n.math.nextafter(250,n.math.inf),'samples':1}]
    assert context['recording_ids']==['r1','r2']


@pytest.mark.parametrize('mode',['failure','not_mapping','malformed','partial'])
def test_source_failure_and_partial_provenance_never_hide_samples(mode):
    s=segment();before=copy.deepcopy(s['points'])
    if mode=='partial':s['points'].append({'time':250,'power':3,'amplitude':0})
    timeline={'windows':[{'panels':[{'side':'left','segments':[s]}]}]}
    recs=[{'SourceId':'source','ChannelNames':['LEFT a'],'Time':[150]},
          {'SourceId':'unknown-side','ChannelNames':[],'Time':[150]}]
    def load(uid):
        if mode=='failure':raise OSError('private source path')
        if mode=='not_mapping':return []
        if mode=='malformed':return {'Groups':{'Initial':None}}
        return report()
    n.link_settings(timeline,recs,load)
    assert s['points'][0]==before[0]
    assert s['mode']=='unknown'
    assert s['settings_context']['status'] in ('unavailable','conflict')
    assert 'private' not in s['settings_context']['message']
    if mode=='partial':assert 'missing for some samples' in s['settings_context']['message']


def test_same_time_distinct_channel_band_variants_link_only_their_original_sources():
    s=segment();s['source_channel']='ZERO_TWO_LEFT'
    timeline={'windows':[{'panels':[{'side':'left','segments':[s]}]}]}
    recs=[{'SourceId':'other-band','RecordingId':'wrong','ChannelNames':['LEFT a'],'Time':[150]},
          {'SourceId':'correct','RecordingId':'right','ChannelNames':['LEFT a'],'Time':[150]}]
    def native(rows, streams):
        channel,hz=('ONE_THREE_LEFT',30) if rows[0]['SourceId']=='other-band' else ('ZERO_TWO_LEFT',25)
        return {channel:{'t':[150],'center_hz':[hz]}}
    calls=[]
    n.link_settings(timeline,recs,lambda uid:calls.append(uid) or report(),native_series=native)
    assert calls==['correct']
    assert s['settings_context']['source_ids']==['correct']
    assert s['settings_context']['recording_ids']==['right']


def test_conflicting_signal_and_ganged_controller_do_not_claim_a_verified_mapping():
    raw=report()
    for groups in [raw['Groups']['Initial'],raw['Groups']['Final']]+[h['Groups'] for h in raw['GroupHistory']]:
        for c in groups[0]['ProgramSettings']['SensingChannel']:
            c['GangedToHemisphere']='HemisphereLocationDef.Right'
    s=segment();timeline={'windows':[{'panels':[{'side':'left','segments':[s]}]}]}
    n.link_settings(timeline,[{'SourceId':'source','ChannelNames':['LEFT a'],'Time':[150]}],lambda uid:raw)
    assert s['mapping_status']=='unknown'
    assert s['control_mapping']=='Adaptive controller relationship could not be reconciled'
    assert s['settings_context']['mapping_verified'] is False


def test_history_explicit_sensing_channel_recovers_contacts_without_signal_check_arrays():
    raw=report()
    for groups in [raw['Groups']['Initial'],raw['Groups']['Final']]+[h['Groups'] for h in raw['GroupHistory']]:
        for c in groups[0]['ProgramSettings']['SensingChannel']:
            c['Channel']='SensingElectrodeConfigDef.ZERO_AND_TWO'
            c['SensingSetup'].pop('ChannelSignalResult')
    result=n.source_context(raw,segment(),'source')
    assert result['status']=='source_linked'
    assert 'Left sensing → Right stimulation' in result['mapping_description']


@pytest.mark.parametrize('status',[None,'ADBSStatusDef.FUTURE_STATE'])
def test_missing_or_future_adaptive_status_preserves_configured_mode_and_thresholds(status):
    raw=report()
    for groups in [raw['Groups']['Initial'],raw['Groups']['Final']]+[h['Groups'] for h in raw['GroupHistory']]:
        for c in groups[0]['ProgramSettings']['SensingChannel']:
            if status is None:c.pop('AdaptiveTherapyStatus')
            else:c['AdaptiveTherapyStatus']=status
    s=segment();timeline={'windows':[{'panels':[{'side':'left','segments':[s]}]}]}
    n.link_settings(timeline,[{'SourceId':'source','ChannelNames':['LEFT a'],'Time':[150]}],lambda uid:raw)
    assert s['settings_context']['status']=='source_linked'
    assert s['mode']=='Dual-threshold adaptive · source configuration'
    assert s['mapping_status']=='unknown' and s['threshold_status']=='source_recorded'
    assert s['control_mapping']=='Adaptive control state is unverified; source configuration is recorded'
    assert 'Sensing only' not in s['control_mapping']
    left={r['label']:r['value'] for r in s['settings']['left']}
    assert left['Lower threshold (configured)']=='100 LSB'
    assert left['Upper threshold (configured)']=='200 LSB'
    assert s['settings_context']['state_unverified'] is True
    assert 'missing or unrecognized' in s['settings_context']['message']
    assert s['settings_context']['mapping_verified'] is False
    if status is not None:assert left['Adaptive state at observation']==status


def test_ganged_controller_source_field_is_inspectable_including_unknown_codes():
    g=group()
    settings,_=n._configuration(g)
    assert {'label':'Recorded ganged-to hemisphere','value':'left'} in settings['right']
    g['ProgramSettings']['SensingChannel'][1]['GangedToHemisphere']='HemisphereLocationDef.FUTURE'
    settings,_=n._configuration(g)
    assert {'label':'Recorded ganged-to hemisphere','value':'HemisphereLocationDef.FUTURE'} in settings['right']


@pytest.mark.parametrize('status',[None,'ADBSStatusDef.FUTURE_STATE'])
def test_absent_mode_and_unverified_state_never_become_sensing_only(status):
    g=group()
    for c in g['ProgramSettings']['SensingChannel']:
        c.pop('Mode')
        c['AdaptiveTherapyStatus']=status
    settings,descriptors=n._configuration(g)
    assert all(d['mode']=='Mode not recorded' for d in descriptors)
    for scope in ('left','right'):
        assert {'label':'Control mode (configured)','value':'Mode not recorded'} in settings[scope]
        assert not any(r['value']=='Sensing only' for r in settings[scope])


def test_amplitude_only_unknown_band_point_retains_source_when_native_power_is_absent():
    s=segment();s.update(center_frequency_hz=None,source_channel='ZERO_TWO_LEFT')
    s['points'][0]['power']=None
    result={'windows':[{'panels':[{'side':'left','segments':[s]}]}]}
    rec=[{'SourceId':'source','RecordingId':'row','ChannelNames':['LEFT a'],'Time':[150]}]
    calls=[]
    n.link_settings(result,rec,lambda uid:calls.append(uid) or report(),native_series=lambda *args:{},
                    pair_keys=lambda *args:['ZERO_TWO_LEFT'])
    assert calls==['source']
    assert s['settings_context']['status']=='conflict'
    assert s['settings_context']['observations']
    assert s['points'][0]['power'] is None and s['points'][0]['amplitude']==1.7
