"""Portable synthetic tests: no files, providers, database, cache or participant data."""
from copy import deepcopy
from datetime import datetime
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('program_comparisons', Path(__file__).parents[1]/'BRAVO/modules/AdityaProgramComparisons.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def ts(value='2030-01-02T20:00:00Z'):
    return p.epoch(value)


def channel(side='Left', status='RUNNING', amp=2):
    return {'HemisphereLocation':'HemisphereLocationDef.'+side, 'AdaptiveTherapyStatus':'ADBSStatusDef.'+status,
        'SuspendAmplitudeInMilliAmps':amp, 'PulseWidthInMicroSecond':100, 'RateInHertz':55,
        'ElectrodeState':[{'Electrode':'ElectrodeDef.SenSight_1a','ElectrodeStateResult':'ElectrodeStateDef.Negative','ElectrodeFractionOf64':-64},
                          {'Electrode':'ElectrodeDef.Case','ElectrodeStateResult':'ElectrodeStateDef.Positive'}],
        'Channel':'SensingElectrodeConfigDef.ZERO_AND_THREE','Mode':'AdaptiveModeDef.DUAL_THRESHOLD_DIRECT','LowerLimitInMilliAmps':1,'UpperLimitInMilliAmps':3,
        'LowerLfpThreshold':10,'UpperLfpThreshold':20,'SensingSetup':{'FrequencyInHertz':12,'ChannelSignalResult':{'Channel':'ZERO_THREE_'+side.upper()}},'AdaptiveTherapy':{}}


def group(status='RUNNING',amp=2, name='Unrelated name'):
    return {'ActiveGroup':True,'GroupId':'GroupIdDef.GROUP_B','GroupName':name,
        'ProgramSettings':{'AmplitudeControl':'CURRENT','SensingChannel':[channel(status=status,amp=amp),channel('Right',status,amp)]},
        'GroupSettings':{'Cycling':{'Enabled':False}}}


def source(uid='s', start='2030-01-02T20:00:00Z',end='2030-01-02T20:10:00Z', status='RUNNING',amp=2):
    return {'id':uid,'hash':'digest-'+uid,'report':{'SessionDate':start,'SessionEndDate':end,
        'Stimulation':{'InitialStimStatus':'ON','FinalStimStatus':'ON'},'Groups':{'Initial':[group(status,amp)],'Final':[group(status,amp)]}}}

METRICS=[{'key':key,'label':key,'range':[0,100],'direction':'higher' if key=='relief' else 'lower'} for key in ('nrs','relief')]
def row(uid='r', when=None, **values):
    return {'id':uid,'time':ts() if when is None else when,'values':values or {'nrs':5,'relief':40}}
def build(rows=None,sources=None,**kwargs):
    return p.build_comparisons(rows or [], METRICS, sources or [], kwargs.pop('testing_days',[]),calendar_verified=kwargs.pop('calendar_verified',True),**kwargs)


@pytest.mark.parametrize('value,expected', [(True,None),(None,None),('x',None),(float('nan'),None),(float('inf'),None),('2.5',2.5),(0,0)])
def test_finite(value,expected): assert p.finite(value)==expected
@pytest.mark.parametrize('value', [None,True,'2030-01-01','wrong',4])
def test_epoch_rejects_unzoned(value): assert p.epoch(value) is None


def test_contacts_exact_fraction_polarity_and_known_right_offset():
    s=source(); c,e=p.phase_condition(s['report'],'Final'); assert e is None
    assert any(r['label']=='Right contacts' and r['value']=='9a- C+' for r in c['settings'])
    t=deepcopy(s);t['report']['Groups']['Final'][0]['ProgramSettings']['SensingChannel'][0]['ElectrodeState'][0]['ElectrodeFractionOf64']=-32
    assert p.phase_condition(t['report'],'Final')[0]['id'] != c['id']
    assert c['mode']=='closed_loop'


@pytest.mark.parametrize('status,expected', [('RUNNING','closed_loop'),('SUSPENDED','open_loop'),('NOT_CONFIGURED','open_loop')])
def test_explicit_adaptive_status(status,expected): assert p.phase_condition(source(status=status)['report'],'Initial')[0]['mode']==expected
@pytest.mark.parametrize('status',[None,'FUTURE'])
def test_missing_future_status_never_becomes_ol(status):
    s=source();s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0]['AdaptiveTherapyStatus']=status
    assert p.phase_condition(s['report'],'Initial')==(None,'unknown_adaptive_status')


def test_names_and_inactive_thresholds_do_not_split_functional_identity():
    s=source(status='SUSPENDED'); before=p.phase_condition(s['report'],'Initial')[0]
    g=s['report']['Groups']['Initial'][0];g['GroupName']='new name';g['GroupSettings']['GroupDisplayName']='incidental';g['ProgramSettings']['SensingChannel'][0]['UpperLfpThreshold']=999
    assert p.phase_condition(s['report'],'Initial')[0]['id']==before['id']
    g['GroupSettings']['Cycling']={'Enabled':True,'OnDurationInMilliSeconds':1000,'OffDurationInMilliSeconds':2000}
    after=p.phase_condition(s['report'],'Initial')[0]
    assert before['id']!=after['id'];assert {'label':'cycle off sec','value':'2.0'} in after['settings']


def test_legacy_multiple_programs_and_zero_current():
    s=source();g=s['report']['Groups']['Initial'][0];g['ProgramSettings'].pop('SensingChannel')
    c=channel(); program={'AmplitudeInMilliAmps':2,'PulseWidthInMicroSecond':80,'RateInHertz':20,'ElectrodeState':c['ElectrodeState']}
    g['ProgramSettings']['LeftHemisphere']={'Programs':[program,dict(program,AmplitudeInMilliAmps=1),{'Enabled':False}]}
    condition,error=p.phase_condition(s['report'],'Initial');assert error is None;assert condition['mode']=='open_loop'
    assert any(r['label']=='Left program 2 amplitude mA' and r['value']=='1.0' for r in condition['settings'])
    for v in g['ProgramSettings']['LeftHemisphere']['Programs'][:2]:v['AmplitudeInMilliAmps']=0
    assert p.phase_condition(s['report'],'Initial')[0]['id']=='OFF'
    g['ProgramSettings']['LeftHemisphere']['Programs']=[]
    assert p.phase_condition(s['report'],'Initial')[1]=='unknown_programs'


@pytest.mark.parametrize('mutation,error', [
 (lambda r:r['Stimulation'].update(InitialStimStatus=None),'unknown_stimulation_status'),
 (lambda r:r['Groups'].update(Initial=[]),'unknown_active_group'),
 (lambda r:r['Groups']['Initial'].append(group()),'unknown_active_group'),
 (lambda r:r['Groups']['Initial'][0].update(GroupId=None),'unknown_group_id'),
 (lambda r:r['Groups']['Initial'][0]['GroupSettings'].update(Cycling={}),'unknown_cycling'),
 (lambda r:r['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'].append(channel()),'ambiguous_side_program'),
 (lambda r:r['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0].update(SuspendAmplitudeInMilliAmps=-1),'unknown_amplitude'),
 (lambda r:r['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0].update(LowerLimitInMilliAmps=8),'invalid_adaptive_limits'),
 (lambda r:r['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0].update(ElectrodeState=[]),'unknown_contacts'),
 (lambda r:r['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0].update(ElectrodeState=[{'ElectrodeStateResult':'Negative','Electrode':None}]),'unknown_contacts'),
 (lambda r:r['Groups'].update(Initial=['malformed']),'invalid_source_settings'),
])
def test_unverified_settings_withheld(mutation,error):
    s=source();mutation(s['report']);assert p.phase_condition(s['report'],'Initial')==(None,error)


def test_explicit_off_does_not_require_settings():
    assert p.phase_condition({'Stimulation':{'InitialStimStatus':'OFF'}},'Initial')[0]['id']=='OFF'
    assert p.phase_condition(source(amp=0,status='SUSPENDED')['report'],'Initial')[0]['id']=='OFF'


def test_preparation_private_projection_and_boundary_validation():
    s=source();s['report']['PatientInformation']={'secret':'not retained'}
    f=p.prepare_source(s);assert f['start_valid'] and f['end_valid'];assert p.prepare_source(f)==f
    assert 'PatientInformation' not in str(f)
    assert not p.prepare_source({'id':'s'})['start_valid']
    for start,end in [('2030-01-02T21:00:00Z','2030-01-02T20:00:00Z'),('2030-01-02T01:00:00Z','2030-01-02T20:00:00Z')]:
        f=p.prepare_source(source(start=start,end=end));assert not f['start_valid'] and not f['end_valid']
    f=p.prepare_source(source(end=None));assert f['start_valid'] and not f['end_valid']
    f=p.prepare_source(source(start=None));assert not f['start_valid'] and f['end_valid']


@pytest.mark.parametrize('when,boundary',[('2030-01-02T19:00:00Z','initial'),('2030-01-02T21:00:00Z','final'),('2030-01-02T20:05:00Z','unchanged_initial_final')])
def test_same_pacific_day_boundaries(when,boundary):
    result=build([row(when=ts(when))],[source()]);assert result['audit'][0]['boundary']==boundary;assert result['provenance']['counts']=={'assigned':1}
    assert result['metrics'][0]['conditions'][0]['points'][0]['value']==5


def test_change_within_session_and_missing_boundary_fail_closed():
    s=source();s['report']['Groups']['Final'][0]['ProgramSettings']['SensingChannel'][0]['SuspendAmplitudeInMilliAmps']=4
    assert build([row(when=ts('2030-01-02T20:05:00Z'))],[s])['audit'][0]['reason']=='changed_during_session'
    assert build([row(when=ts('2030-01-02T20:05:00Z'))],[source(end=None)])['audit'][0]['reason']=='missing_required_boundary'
    assert build([row(when=ts('2030-01-02T19:00:00Z'))],[source(start=None)])['audit'][0]['reason']=='missing_required_boundary'


def test_nearest_ambiguous_not_bypassed_and_ties_stable():
    bad=source('b');bad['report']['Stimulation']['InitialStimStatus']='unknown'
    old=source('a',start='2030-01-02T18:00:00Z',end='2030-01-02T18:10:00Z')
    assert build([row(when=ts('2030-01-02T19:59:00Z'))],[old,bad])['audit'][0]['reason']=='unknown_stimulation_status'
    a,b=source('a'),source('b');r=build([row()],[a,b]);assert r['audit'][0]['source_ids']==['a','b']
    b['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0]['SuspendAmplitudeInMilliAmps']=3
    assert build([row(when=ts('2030-01-02T19:59:00Z'))],[a,b])['audit'][0]['reason']=='conflicting_source_boundaries'


def test_overlapping_contradictory_session_not_silently_crossed():
    outer=source('outer',start='2030-01-02T18:00:00Z',end='2030-01-02T23:00:00Z')
    inner=source('inner',amp=4)
    r=build([row(when=ts('2030-01-02T21:00:00Z'))],[outer,inner])
    assert r['audit'][0]['reason']=='conflicting_source_boundaries';assert not r['available']


def test_all_testing_days_and_full_pacific_day_gate():
    rows=[row('a',ts('2030-01-03T07:59:59Z')),row('b',ts('2030-01-03T08:00:00Z'))]
    r=build(rows,[source()],testing_days=['2030-01-02']);assert [a['reason'] for a in r['audit']]==['testing_day','no_same_day_source']
    assert r['metrics'][0]['provenance']['excluded_testing']==1
    r=build([row()],[source()],preserved_testing_days=['2030-01-02']);assert not r['available']


@pytest.mark.parametrize('kwargs',[{'calendar_verified':False},{'testing_days':['invalid']},{'preserved_testing_days':[4]}])
def test_invalid_calendar_withholds_all_including_historical(kwargs):
    r=build([row()],[source()],**kwargs);assert not r['available'];assert r['audit'][0]['reason']=='calendar_unverified'


def test_period_and_duplicate_invalid_rows():
    rows=[row('dup'),row('dup'),{'id':'bad','time':None,'values':{'nrs':2}},row('early',ts()-1)]
    r=build(rows,[source()],period_start=ts());assert [a['reason']for a in r['audit']]==['duplicate_survey_id','duplicate_survey_id','invalid_survey_time','before_period']
    assert r['metrics'][0]['provenance']['excluded_period']==1


def test_historical_requires_exact_current_identity_full_values_and_no_nearer_source():
    survey=row();c=p.phase_condition(source()['report'],'Initial')[0]
    h={'record':'r','time':survey['time'],'values':survey['values'],'source_ids':['reviewed'],'condition':c,'verified':True}
    assert build([survey],historical_assignments=[h])['audit'][0]['boundary']=='reviewed_historical'
    assert build([dict(survey,values={'nrs':5})],historical_assignments=[h])['audit'][0]['reason']=='no_same_day_source'
    bad=source();bad['report']['Stimulation']['InitialStimStatus']='bad'
    assert build([row(when=ts()-1)],[bad],historical_assignments=[dict(h,time=ts()-1)])['audit'][0]['reason']=='unknown_stimulation_status'
    h2=deepcopy(h);h2['condition']['id']='conflict'
    assert not build([survey],historical_assignments=[h,h2])['available']


def test_metric_specific_n_finite_missingness_ranking_direction_and_off():
    sources=[];rows=[]
    for number in range(5):
        day=number+2; start=f'2030-01-{day:02}T20:00:00Z';end=f'2030-01-{day:02}T20:10:00Z'
        sources.append(source(str(number),start,end,status='SUSPENDED',amp=number+1))
        for i in range(6):rows.append(row(f'{number}-{i}',ts(start)+i,nrs=number if i<5 else None,relief=number*10 if i<5 else float('nan')))
    off=source('off','2030-01-07T20:00:00Z','2030-01-07T20:10:00Z',status='SUSPENDED',amp=0);sources.append(off);rows.append(row('off',ts('2030-01-07T20:00:00Z')))
    result=build(rows,sources);nrs,relief=result['metrics']
    assert [c['median']for c in nrs['conditions']]==[0,1,2,3,4]
    assert [c['median']for c in relief['conditions']]==[40,30,20,10,0]
    assert len(nrs['top']['open_loop'])==3 and not nrs['top']['closed_loop']
    assert nrs['baseline']['count']==1;assert nrs['provenance']['missing_value']==5
    assert nrs['provenance']['assigned']==26 and nrs['provenance']['eligible']==26
    assert result['provenance']['latest_assigned']==ts('2030-01-07T20:00:00Z')
    assert build([row()],[source()])['metrics'][0]['top']['closed_loop']==[]


def test_equal_medians_stable_ids_and_explicit_direction():
    a=source('a');b=source('b','2030-01-03T20:00:00Z','2030-01-03T20:10:00Z',amp=3)
    rows=[row(str(i),ts()+i)for i in range(5)]+[row(str(i+5),ts('2030-01-03T20:00:00Z')+i)for i in range(5)]
    first=build(rows,[a,b]);second=build(rows[::-1],[b,a]);assert first['metrics']==second['metrics'];assert first['provenance']==second['provenance']
    assert first['metrics'][0]['top']['closed_loop']==sorted(first['metrics'][0]['top']['closed_loop'])
    with pytest.raises(ValueError,match='Explicit'):p.build_comparisons([], [{'direction':'guess'}],[],[],calendar_verified=True)


def test_metric_specific_latest_stored_timestamp_ignores_missing_values():
    result=build([row('one',nrs=4,relief=None),row('two',ts()+100,nrs=None,relief=40)],[source()])
    assert result['metrics'][0]['provenance']['latest_survey']==ts()
    assert result['metrics'][1]['provenance']['latest_survey']==ts()+100


def test_unprogrammed_contact_states_ignored_and_valid_word_tokens():
    states=[{'Electrode':'ONE','ElectrodeStateResult':'Negative'},{'Electrode':'CASE','ElectrodeStateResult':'Positive'}, {'Electrode':'TWO','ElectrodeStateResult':'None'}]
    assert p._contacts(states,'left')[0]['contact']=='1'


def test_both_sided_boundaries_agree_unknown_or_different_withhold():
    prior=source('prior','2030-01-02T17:00:00Z','2030-01-02T17:10:00Z')
    after=source('after','2030-01-02T23:00:00Z','2030-01-02T23:10:00Z')
    r=build([row()],[prior,after]);assert r['audit'][0]['boundary']=='reconciled_initial_final'
    after['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0]['SuspendAmplitudeInMilliAmps']=8
    assert build([row()],[prior,after])['audit'][0]['reason']=='conflicting_source_boundaries'
    after['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0]['AdaptiveTherapyStatus']=None
    assert build([row()],[prior,after])['audit'][0]['reason']=='unknown_adaptive_status'


def test_intervening_boundaries_hide_farther_conflicts():
    prior=source('prior','2030-01-02T17:00:00Z','2030-01-02T17:10:00Z')
    after=source('after','2030-01-02T23:00:00Z','2030-01-02T23:10:00Z')
    old=source('old','2030-01-02T15:00:00Z','2030-01-02T15:10:00Z',amp=8)
    future=source('future','2030-01-02T23:30:00Z','2030-01-02T23:40:00Z',amp=8)
    assert build([row()],[prior,after,old,future])['audit'][0]['reason'] is None


def test_verified_pdf_sensing_only_mode_requires_every_exact_binding():
    s=source();s['raw_sha256']='a'*64
    for phase in ('Initial','Final'):
        for c in s['report']['Groups'][phase][0]['ProgramSettings']['SensingChannel']:
            c.pop('AdaptiveTherapyStatus');c.pop('Mode')
    proof={'reviewed':True,'source_id':'s','source_hash':'digest-s','raw_sha256':'a'*64,'pdf_sha256':'b'*64,'phase':'Initial','side':'left','mode':'SENSING_ONLY'}
    s['mode_evidence']=[dict(proof,phase=phase,side=side)for phase in ('Initial','Final')for side in ('left','right')]
    assert p.prepare_source(s)['initial']['mode']=='open_loop'
    for key,value in [('reviewed',False),('source_id','other'),('source_hash','other'),('raw_sha256','c'*64),('pdf_sha256','bad'),('phase','other'),('side','other'),('mode','guess')]:
        bad=deepcopy(s);bad['mode_evidence'][0][key]=value
        assert p.prepare_source(bad)['initial_error']=='unknown_adaptive_status'
    bad=deepcopy(s);bad['raw_sha256']='g'*64
    assert p.prepare_source(bad)['initial_error']=='unknown_adaptive_status'
    s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0]['AdaptiveTherapyStatus']='FUTURE'
    assert p.prepare_source(s)['initial_error']=='unknown_adaptive_status'


@pytest.mark.parametrize('field,value,error', [
 ('Mode',None,'unknown_adaptive_mode'),('Mode','AdaptiveModeDef.FUTURE','unknown_adaptive_mode'),
 ('LowerLfpThreshold',None,'unknown_adaptive_thresholds'),('UpperLfpThreshold',float('inf'),'unknown_adaptive_thresholds'),
 ('LowerLfpThreshold',30,'invalid_adaptive_thresholds'),('Channel',None,'unknown_sensing_identity'),
 ('SensingSetup',{},'unknown_sensing_identity'),
])
def test_incomplete_active_adaptive_configuration_withheld(field,value,error):
    s=source();s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0][field]=value
    assert p.phase_condition(s['report'],'Initial')==(None,error)


def test_running_zero_range_is_no_active_current_even_with_pause_amplitude():
    s=source()
    for c in s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel']:
        c.update(LowerLimitInMilliAmps=0,UpperLimitInMilliAmps=0)
    assert p.phase_condition(s['report'],'Initial')[0]['id']=='OFF'


def test_containing_unchanged_session_wins_over_outside_prior_future_config():
    window=source('window',start='2030-01-02T18:00:00Z',end='2030-01-02T23:00:00Z')
    older=source('older','2030-01-02T17:00:00Z','2030-01-02T17:10:00Z',amp=8)
    later=source('later','2030-01-02T23:30:00Z','2030-01-02T23:40:00Z',amp=8)
    result=build([row()],[window,older,later]);assert result['audit'][0]['source_ids']==['window'];assert result['available']


def test_numeric_json_encoding_and_enum_prefix_are_functionally_equal():
    s=source();before=p.phase_condition(s['report'],'Initial')[0]
    g=s['report']['Groups']['Initial'][0];g['ProgramSettings']['SensingChannel'][0]['LowerLfpThreshold']=10.0
    g['ProgramSettings']['SensingChannel'][0]['Mode']='DUAL_THRESHOLD_DIRECT'
    assert p.phase_condition(s['report'],'Initial')[0]['id']==before['id']


def test_pdf_evidence_visible_and_not_part_of_functional_identity():
    s=source(status='NOT_CONFIGURED');plain=p.prepare_source(s)['initial'];s['raw_sha256']='a'*64
    s['mode_evidence']=[{'reviewed':True,'source_id':'s','source_hash':'digest-s','raw_sha256':'a'*64,'pdf_sha256':'b'*64,'phase':phase,'side':side,'mode':'SENSING_ONLY'}for phase in ['Initial','Final']for side in ['left','right']]
    for phase in ['Initial','Final']:
        for c in s['report']['Groups'][phase][0]['ProgramSettings']['SensingChannel']:
            c.pop('AdaptiveTherapyStatus');c.pop('Mode')
    f=p.prepare_source(s);assert f['initial']['id']==plain['id']
    assert {'label':'Left adaptive evidence','value':'Device report: Sensing Only (JSON adaptive state absent)'}in f['initial']['settings']
    result=build([row()],[s]);assert 'Device report' in str(result['metrics'][0]['conditions'][0]['settings'])
    # A later raw-JSON observation must not erase the earlier positive PDF origin.
    second=source('second','2030-01-03T20:00:00Z','2030-01-03T20:10:00Z',status='NOT_CONFIGURED')
    result=build([row(),row('second',ts('2030-01-03T20:00:00Z'))],[s,second])
    assert 'Device report' in str(result['metrics'][0]['conditions'][0]['settings'])


def test_unknown_contact_enum_is_not_assumed_numeric_contact():
    with pytest.raises(ValueError,match='unknown_contacts'):
        p._contacts([{'Electrode':'FUTURE','ElectrodeStateResult':'Negative'}], 'right')


@pytest.mark.parametrize('status,mode,error', [(None,'open_loop',None),('DISABLED','open_loop',None),('FUTURE',None,'unknown_adaptive_status'),('RUNNING',None,'conflicting_mode_evidence')])
def test_pdf_positive_known_configured_inactive_and_raw_conflict(status,mode,error):
    s=source();s['raw_sha256']='a'*64
    s['mode_evidence']=[{'reviewed':True,'source_id':'s','source_hash':'digest-s','raw_sha256':'a'*64,'pdf_sha256':'b'*64,'phase':'Initial','side':side,'mode':'SENSING_ONLY'}for side in ['left','right']]
    for c in s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel']:c['AdaptiveTherapyStatus']=status
    f=p.prepare_source(s)
    if error: assert f['initial_error']==error
    else:
        assert f['initial']['mode']==mode
        assert {'label':'Left configured controller mode (inactive)','value':'DUAL_THRESHOLD_DIRECT'}in f['initial']['settings']
        assert 'Device report' in str(f['initial']['settings'])


def test_patient_adjustment_bounds_and_functional_group_controls_retained():
    s=source();g=s['report']['Groups']['Initial'][0];ch=g['ProgramSettings'].pop('SensingChannel')[0]
    program={'ProgramId':'FIRST_LEFT','AmplitudeInMilliAmps':2,'PulseWidthInMicroSecond':100,'RateInHertz':55,'ElectrodeState':ch['ElectrodeState'],'LowerLimitInMilliAmps':1,'UpperLimitInMilliAmps':3}
    g['ProgramSettings']['LeftHemisphere']={'Programs':[program]}
    g['GroupSettings'].update(SoftStartStop={'Enabled':True,'DurationInSeconds':4},HighPassFilterInHertz=1,SensingBlankingDurationInMicroseconds=1500)
    before=p.phase_condition(s['report'],'Initial')[0]
    assert {'label':'Left patient adjustment upper limit mA','value':'3.0'}in before['settings']
    assert {'label':'Sensing blanking duration us','value':'1500'}in before['settings']
    program['UpperLimitInMilliAmps']=4
    assert p.phase_condition(s['report'],'Initial')[0]['id']!=before['id']


def test_numeric_string_thresholds_preserve_value_and_match_numeric_encodings():
    s=source();initial=p.phase_condition(s['report'],'Initial')[0]['id']
    c=s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0]
    c['LowerLfpThreshold']='10.0';same=p.phase_condition(s['report'],'Initial')[0]['id'];assert same==initial
    c['LowerLfpThreshold']='12.0';assert p.phase_condition(s['report'],'Initial')[0]['id']!=initial


@pytest.mark.parametrize('polarity',[None,'ElectrodeStateDef.FUTURE'])
def test_unknown_contact_polarity_is_not_assumed_inactive(polarity):
    s=source();c=s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0]
    c['ElectrodeState'].append({'Electrode':'SenSight_2','ElectrodeStateResult':polarity})
    assert p.phase_condition(s['report'],'Initial')==(None,'unknown_contact_polarity')


def test_unknown_additional_hemisphere_does_not_silently_disappear():
    s=source();s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'].append(channel('FUTURE'))
    assert p.phase_condition(s['report'],'Initial')==(None,'unknown_sensing_hemisphere')


def test_unknown_legacy_enabled_flag_withheld():
    s=source();g=s['report']['Groups']['Initial'][0];g['ProgramSettings'].pop('SensingChannel')
    g['ProgramSettings']['LeftHemisphere']={'Programs':[{'Enabled':'FUTURE'}]}
    assert p.phase_condition(s['report'],'Initial')==(None,'unknown_program_enabled')


def test_unknown_in_session_boundary_does_not_claim_verified_change():
    s=source();s['report']['Groups']['Initial'][0]['ProgramSettings']['SensingChannel'][0]['AdaptiveTherapyStatus']=None
    result=build([row(when=ts('2030-01-02T20:05:00Z'))],[s])
    assert result['audit'][0]['reason']=='unknown_adaptive_status'


@pytest.mark.parametrize('start,end,one,two',[
 ('2030-03-10T09:00:00Z','2030-03-10T11:00:00Z','2030-03-10T09:30:00Z','2030-03-10T10:30:00Z'),
 ('2030-11-03T08:00:00Z','2030-11-03T10:00:00Z','2030-11-03T08:30:00Z','2030-11-03T09:30:00Z'),
])
def test_pacific_dst_crossings_keep_utc_rows_and_same_local_day(start,end,one,two):
    rows=[row('a',ts(one)),row('b',ts(two))];result=build(rows,[source(start=start,end=end)])
    points=result['metrics'][0]['conditions'][0]['points']
    assert [(p['record'],p['time'])for p in points]==[('a',ts(one)),('b',ts(two))]
    assert result['metrics'][0]['provenance']['assigned']==2
    day=datetime.fromtimestamp(ts(one),p.PACIFIC).date().isoformat()
    assert build(rows,[source(start=start,end=end)],testing_days=[day])['metrics'][0]['provenance']['excluded_testing']==2


def test_distinct_native_rows_same_time_preserve_multiplicity_and_input_values():
    rows=[row(str(index),nrs=index,relief=40)for index in range(5)];before=deepcopy(rows)
    result=build(rows,[source()]);condition=result['metrics'][0]['conditions'][0]
    assert condition['count']==5 and condition['median']==2 and len({x['record']for x in condition['points']})==5
    assert result['metrics'][0]['top']['closed_loop']==[condition['id']]
    assert rows==before
