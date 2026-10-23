"""Portable synthetic identity-continuity tests; no files, service or participant data."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('native_continuity', Path(__file__).parents[1]/'scripts/daily_import/native_continuity.py')
n = importlib.util.module_from_spec(spec);spec.loader.exec_module(n)


def stamp(offset):
    return (datetime(2031,1,1,tzinfo=timezone.utc)+timedelta(seconds=offset)).isoformat()


def node(offset):
    return {'DateTime':stamp(offset),'DateTimeBlockId':7,'DateTimeOffsetInSeconds':offset}


def report(count=3):
    chronic = {}
    for side in ['Left','Right']:
        rows=[{**node(100+i*600),'LFP':10+i+(1 if side=='Right' else 0),'AmplitudeInMilliAmps':1.2}for i in range(count)]
        chronic['HemisphereLocationDef.'+side]={'a date label is not identity':rows}
    psd=[]
    for i in range(count):
        payloads={'HemisphereLocationDef.'+side:{**node(190+i*600),'GroupId':'GroupIdDef.GROUP_A','SenseID':'SensingElectrodeConfigDef.ZERO_AND_THREE','Frequency':[0.0,0.98,1.95],'FFTBinData':[1.0+i,2.0+i,3.1+i+(1 if side=='Right' else 0)]}for side in ['Left','Right']}
        psd.append({**node(200+i*600),'EventID':6,'EventName':'Streaming','LFP':True,'Cycling':False,'LfpFrequencySnapshotEvents':payloads})
    return {'DiagnosticData':{'LFPTrendLogs':chronic,'LfpFrequencySnapshotEvents':psd}}


def rows(r,side='Left'):
    return r['DiagnosticData']['LFPTrendLogs']['HemisphereLocationDef.'+side]['a date label is not identity']


def events(r):return r['DiagnosticData']['LfpFrequencySnapshotEvents']
def psd(r,index=0,side='Left'):return events(r)[index]['LfpFrequencySnapshotEvents']['HemisphereLocationDef.'+side]
def rehash(proof):proof['proof_sha256']=n._digest({k:v for k,v in proof.items()if k!='proof_sha256'});return proof


def test_positive_whole_bilateral_continuity_and_no_source_mutation():
    reference=report();candidate=deepcopy(reference);before=deepcopy(candidate)
    proof=n.prove_continuity(candidate,reference)
    assert n.validate_receipt(proof) and candidate==before
    assert proof['witnesses']['chronic']['left']['count']==3
    assert proof['witnesses']['psd']['right']['count']==3
    assert proof['candidate_intrinsic_sha256']==proof['reference_intrinsic_sha256']
    assert n.validate_clock_receipt(n.verify_clock_agreement(candidate,reference))


def test_native_clock_display_drift_does_not_change_intrinsic_identity():
    reference=report();candidate=deepcopy(reference)
    def drift(value):
        if isinstance(value,dict):
            if 'DateTimeBlockId'in value:value['DateTime']=stamp(value['DateTimeOffsetInSeconds']+3600)
            for child in value.values():drift(child)
        elif isinstance(value,list):
            for child in value:drift(child)
    drift(candidate)
    proof=n.prove_continuity(candidate,reference)
    assert proof['candidate_intrinsic_sha256']==proof['reference_intrinsic_sha256']
    with pytest.raises(n.ContinuityError,match='canonical_measurement_clock_conflict'):n.verify_clock_agreement(candidate,reference)
    # The caller's canonical conversion must restore the source-owned times.
    assert n.verify_clock_agreement(reference,reference)['shared_clock_nodes']>=10


def test_new_native_samples_allowed_but_do_not_invent_witnesses():
    reference=report();candidate=report(4);proof=n.prove_continuity(candidate,reference)
    assert proof['candidate_records']['chronic']['left']==4
    assert proof['witnesses']['chronic']['left']['count']==3
    assert proof['candidate_intrinsic_sha256']!=proof['reference_intrinsic_sha256']


@pytest.mark.parametrize('where', ['chronic','psd_array','frequency','contact','group','event_context','inner_native_key','arbitrary_nested_time'])
def test_one_shared_explicit_contradiction_rejects_despite_many_other_matches(where):
    reference=report();candidate=deepcopy(reference)
    if where=='chronic':rows(candidate)[0]['LFP']=999
    if where=='psd_array':psd(candidate)['FFTBinData'][0]=999
    if where=='frequency':psd(candidate)['Frequency'][1]=1.0
    if where=='contact':psd(candidate)['SenseID']='SensingElectrodeConfigDef.ONE_AND_THREE'
    if where=='group':psd(candidate)['GroupId']='GroupIdDef.GROUP_B'
    if where=='event_context':events(candidate)[0]['Cycling']=True
    if where=='inner_native_key':psd(candidate)['DateTimeOffsetInSeconds']+=1
    if where=='arbitrary_nested_time':
        rows(reference)[0]['other']={'DateTime':'must retain this'}
        rows(candidate)[0]['other']={'DateTime':'changed non-native metadata'}
    with pytest.raises(n.ContinuityError,match='conflict'):n.prove_continuity(candidate,reference)


@pytest.mark.parametrize('side',['Left','Right'])
def test_bilateral_neural_data_required_not_event_logs_only(side):
    reference=report();candidate=deepcopy(reference)
    candidate['DiagnosticData']['LFPTrendLogs'].pop('HemisphereLocationDef.'+side)
    candidate['DiagnosticData']['EventLogs']=[{**node(10),'SessionType':'SessionStart'}]*100
    with pytest.raises(n.ContinuityError,match='insufficient_chronic'):n.prove_continuity(candidate,reference)


@pytest.mark.parametrize('condition',['one_instant','constant_lfp','zero_lfp','negative_lfp','no_overlap'])
def test_no_low_information_chronic_proof(condition):
    reference=report();candidate=deepcopy(reference)
    for doc in [reference,candidate]:
        for side in ['Left','Right']:
            if condition=='one_instant':rows(doc,side)[:]=rows(doc,side)[:1]
            if condition in ['constant_lfp','zero_lfp','negative_lfp']:
                for row in rows(doc,side):row['LFP']={'constant_lfp':2,'zero_lfp':0,'negative_lfp':-1}[condition]
    if condition=='no_overlap':
        for side in ['Left','Right']:
            for row in rows(candidate,side):row['DateTimeOffsetInSeconds']+=1
    with pytest.raises(n.ContinuityError,match='insufficient_chronic'):n.prove_continuity(candidate,reference)


@pytest.mark.parametrize('condition',['no_arrays','flat','zeros','one_instant','all_other_native_keys'])
def test_no_low_information_spectral_proof(condition):
    reference=report();candidate=deepcopy(reference)
    for doc in [reference,candidate]:
        if condition=='no_arrays':
            for e in events(doc):e.pop('LfpFrequencySnapshotEvents')
        elif condition=='one_instant':events(doc)[:]=events(doc)[:1]
        elif condition in ['flat','zeros']:
            for index in range(3):
                for side in ['Left','Right']:psd(doc,index,side)['FFTBinData']=[1,1,1]if condition=='flat'else[0,0,0]
    if condition=='all_other_native_keys':
        for e in events(candidate):
            e['DateTimeOffsetInSeconds']+=1
            for payload in e['LfpFrequencySnapshotEvents'].values():payload['DateTimeOffsetInSeconds']+=1
    with pytest.raises(n.ContinuityError,match='insufficient_psd'):n.prove_continuity(candidate,reference)


@pytest.mark.parametrize('condition',['omit_payload','omit_side','blank_contact','omit_contact','add_explicit_contact'])
def test_documented_weakening_is_not_a_positive_witness(condition):
    reference=report();candidate=deepcopy(reference)
    if condition=='omit_payload':events(candidate)[0].pop('LfpFrequencySnapshotEvents')
    if condition=='omit_side':events(candidate)[0]['LfpFrequencySnapshotEvents'].pop('HemisphereLocationDef.Left')
    if condition=='blank_contact':psd(candidate)['SenseID']=''
    if condition=='omit_contact':psd(candidate).pop('SenseID')
    if condition=='add_explicit_contact':psd(reference)['SenseID']=''
    proof=n.prove_continuity(candidate,reference)
    assert proof['witnesses']['psd']['left']['count']==2
    assert sum(proof['weakening'].values())>=1


def test_reference_missing_spectral_payload_is_addition_not_a_witness():
    reference=report();candidate=deepcopy(reference);events(reference)[0].pop('LfpFrequencySnapshotEvents')
    proof=n.prove_continuity(candidate,reference)
    assert proof['weakening']['reference_omitted_psd_sides']==2
    assert proof['witnesses']['psd']['left']['count']==2


def test_stable_blank_contact_numerical_frames_still_have_exact_fingerprints():
    reference=report()
    for index in range(3):
        for side in ['Left','Right']:psd(reference,index,side)['SenseID']=''
    proof=n.prove_continuity(deepcopy(reference),reference)
    assert proof['witnesses']['psd']['right']['count']==3 and not proof['weakening']['blank_contact_claims']


def test_identical_duplicate_measurements_count_once_and_order_is_irrelevant():
    reference=report();candidate=deepcopy(reference)
    rows(candidate).append(deepcopy(rows(candidate)[0]));events(candidate).append(deepcopy(events(candidate)[0]))
    rows(candidate).reverse();events(candidate).reverse()
    proof=n.prove_continuity(candidate,reference)
    assert proof['candidate_intrinsic_sha256']==proof['reference_intrinsic_sha256']
    assert proof['candidate_records']['chronic']['left']==3


@pytest.mark.parametrize('where',['candidate_chronic','reference_chronic','candidate_psd','reference_psd'])
def test_ambiguous_duplicate_native_records_reject(where):
    reference=report();candidate=deepcopy(reference);doc=reference if where.startswith('reference')else candidate
    if where.endswith('chronic'):
        row=deepcopy(rows(doc)[0]);row['LFP']=999;rows(doc).append(row)
    else:
        row=deepcopy(events(doc)[0]);row['EventName']='Contradictory category';events(doc).append(row)
    with pytest.raises(n.ContinuityError,match='ambiguous_native_duplicate'):n.prove_continuity(candidate,reference)


def test_different_event_ids_at_same_native_instant_are_not_ambiguous_or_extra_time():
    reference=report()
    other=deepcopy(events(reference)[0]);other['EventID']=9;other['EventName']='Different event category';events(reference).append(other)
    proof=n.prove_continuity(deepcopy(reference),reference)
    assert proof['candidate_records']['psd']==4
    for doc in [reference]:
        events(doc)[:]=[e for e in events(doc)if e['DateTimeOffsetInSeconds']==200]
    with pytest.raises(n.ContinuityError,match='insufficient_psd'):n.prove_continuity(reference,reference)


@pytest.mark.parametrize('value',[True,None,-1,1.5,'7'])
def test_invalid_native_integer_keys_reject(value):
    reference=report();candidate=deepcopy(reference);rows(candidate)[0]['DateTimeBlockId']=value
    with pytest.raises(n.ContinuityError,match='invalid_native_key'):n.prove_continuity(candidate,reference)


@pytest.mark.parametrize('value',[None,'2031-01-01','bad',1])
def test_missing_or_unzoned_native_timestamp_reject(value):
    candidate=report();rows(candidate)[0]['DateTime']=value
    with pytest.raises(n.ContinuityError,match='invalid_native_time'):n.prove_continuity(candidate,report())


@pytest.mark.parametrize('mutation,error',[
 (lambda r:r.pop('DiagnosticData'),'measurement_inventory_unavailable'),
 (lambda r:r['DiagnosticData'].update(LFPTrendLogs=[]),'invalid_chronic_inventory'),
 (lambda r:r['DiagnosticData']['LFPTrendLogs'].update(FUTURE={}), 'invalid_chronic_hemisphere'),
 (lambda r:r['DiagnosticData']['LFPTrendLogs'].update({'HemisphereLocationDef.Left':[]}), 'invalid_chronic_hemisphere'),
 (lambda r:r['DiagnosticData']['LFPTrendLogs']['HemisphereLocationDef.Left'].update({'a date label is not identity':{}}),'invalid_chronic_inventory'),
 (lambda r:rows(r)[0].pop('LFP'),'incomplete_chronic_measurement'),
 (lambda r:r['DiagnosticData'].update(LfpFrequencySnapshotEvents={}), 'invalid_psd_inventory'),
 (lambda r:events(r)[0].update(EventID=True),'invalid_psd_event_identity'),
 (lambda r:events(r)[0].update(LfpFrequencySnapshotEvents=[]),'invalid_psd_hemisphere'),
 (lambda r:events(r)[0]['LfpFrequencySnapshotEvents'].update(FUTURE={}), 'invalid_psd_hemisphere'),
 (lambda r:psd(r).update(Frequency=[0,0,1]),'invalid_spectrum'),
 (lambda r:psd(r).update(FFTBinData=[0]),'invalid_spectrum'),
 (lambda r:psd(r).update(Frequency=[-1,0,1]),'invalid_spectrum'),
 (lambda r:psd(r).update(SenseID=None),'invalid_contact_claim'),
 (lambda r:rows(r)[0].update(other=float('nan')),'nonfinite_measurement'),
 (lambda r:psd(r).update(FFTBinData=[1,float('inf'),3]),'invalid_spectrum'),
 (lambda r:rows(r)[0].update(other={4:1}),'invalid_json_key'),
 (lambda r:rows(r)[0].update(other=set()),'invalid_measurement_type'),
])
def test_malformed_unknown_or_nonfinite_payloads_fail_closed(mutation,error):
    candidate=report();mutation(candidate)
    with pytest.raises(n.ContinuityError,match=error):n.prove_continuity(candidate,report())


def test_numeric_json_types_match_but_native_clock_keys_must_stay_integers():
    reference=report();candidate=deepcopy(reference);rows(candidate)[0]['LFP']=10.0
    assert n.prove_continuity(candidate,reference)['candidate_intrinsic_sha256']==n.prove_continuity(reference,reference)['candidate_intrinsic_sha256']
    rows(candidate)[0]['DateTimeOffsetInSeconds']=100.0
    with pytest.raises(n.ContinuityError,match='invalid_native_key'):n.prove_continuity(candidate,reference)


@pytest.mark.parametrize('where', ['chronic', 'spectrum'])
def test_large_integer_measurement_conflicts_cannot_round_to_same_float(where):
    reference=report();candidate=deepcopy(reference)
    if where=='chronic':
        rows(reference)[0]['LFP']=2**53
        rows(candidate)[0]['LFP']=2**53+1
    else:
        psd(reference)['FFTBinData'][0]=2**53
        psd(candidate)['FFTBinData'][0]=2**53+1
    with pytest.raises(n.ContinuityError,match='conflict'):n.prove_continuity(candidate,reference)


@pytest.mark.parametrize('where', ['chronic', 'spectrum', 'event'])
def test_explicit_boolean_and_number_are_different_intrinsic_claims(where):
    reference=report();candidate=deepcopy(reference)
    pick={'chronic':lambda r:rows(r)[0], 'spectrum':psd, 'event':lambda r:events(r)[0]}[where]
    pick(reference)['ExtraFlag']=True
    pick(candidate)['ExtraFlag']=1
    with pytest.raises(n.ContinuityError,match='conflict'):n.prove_continuity(candidate,reference)


def test_differing_boolean_numeric_duplicate_is_ambiguous():
    reference=report();candidate=deepcopy(reference)
    rows(candidate)[0]['ExtraFlag']=True
    duplicate=deepcopy(rows(candidate)[0]);duplicate['ExtraFlag']=1
    rows(candidate).append(duplicate)
    with pytest.raises(n.ContinuityError,match='ambiguous_native_duplicate'):n.prove_continuity(candidate,reference)


def log_report():
    result=report()
    result['DiagnosticData']['EventLogs']=[
        {**node(150),'ParameterTrendId':'ParameterTrendIdDef.AdbsEnable','AdbsStatus':state}
        for state in ['TherapyChangeStatusDef.ON','TherapyChangeStatusDef.OFF']]
    result['DiagnosticData']['EventLogs'] += [{**node(150),'SessionType':value} for value in ['start','end']]
    return result


def test_simultaneous_event_states_preserved_without_becoming_neural_witnesses():
    reference=log_report();candidate=deepcopy(reference)
    candidate['DiagnosticData']['EventLogs'].append(deepcopy(candidate['DiagnosticData']['EventLogs'][0]))
    candidate['DiagnosticData']['EventLogs'].reverse()
    proof=n.prove_continuity(candidate,reference)
    assert proof['candidate_intrinsic_sha256']==proof['reference_intrinsic_sha256']
    assert proof['witnesses']['chronic']['left']['count']==3
    assert n.verify_clock_agreement(candidate,reference)['shared_clock_nodes']==n.verify_clock_agreement(report(),report())['shared_clock_nodes']+4


@pytest.mark.parametrize('where',['chronic','psd_event','psd_measurement','event_log'])
def test_canonical_duplicate_times_must_agree_before_deduplication(where):
    reference=log_report();candidate=deepcopy(reference)
    if where=='chronic':
        duplicate=deepcopy(rows(candidate)[0]);rows(candidate).insert(0,duplicate)
    elif where in ['psd_event','psd_measurement']:
        duplicate=deepcopy(events(candidate)[0])
        events(candidate).insert(0,duplicate)
        if where=='psd_measurement':
            duplicate['EventID']=99
            duplicate=duplicate['LfpFrequencySnapshotEvents']['HemisphereLocationDef.Left']
    else:
        duplicate=deepcopy(candidate['DiagnosticData']['EventLogs'][0]);candidate['DiagnosticData']['EventLogs'].insert(0,duplicate)
    duplicate['DateTime']=stamp(9999)
    assert n.prove_continuity(candidate,reference)
    with pytest.raises(n.ContinuityError,match='canonical_duplicate_clock_conflict'):n.verify_clock_agreement(candidate,reference)


@pytest.mark.parametrize('change', ['state','numeric','omit_one_simultaneous','boolean'])
def test_shared_event_log_contradictions_veto_otherwise_complete_neural_proof(change):
    reference=log_report();candidate=deepcopy(reference);rows_=candidate['DiagnosticData']['EventLogs']
    if change=='state':rows_[0]['AdbsStatus']='unknown future state'
    if change=='numeric':rows_[0]['Amplitude']=99
    if change=='omit_one_simultaneous':rows_.pop(0)
    if change=='boolean':
        reference['DiagnosticData']['EventLogs'][0]['Flag']=True;rows_[0]['Flag']=1
    with pytest.raises(n.ContinuityError,match='shared_event_log_conflict'):n.prove_continuity(candidate,reference)


def test_event_log_omission_or_new_native_group_is_not_an_identity_witness():
    reference=log_report();candidate=report()
    proof=n.prove_continuity(candidate,reference)
    assert proof['witnesses']['psd']['left']['count']==3
    candidate['DiagnosticData']['EventLogs']=[{**node(999),'RechargeSessionType':'start'},{**node(888),'MriType':'MRI'}]
    assert n.prove_continuity(candidate,reference)['witnesses']['psd']['left']['count']==3


@pytest.mark.parametrize('value', [None, {}, [{**node(150),'UnknownCategory':'x'}], [{**node(150),'SessionType':False}], [{**node(150),'SessionType':''}], [{**node(150),'SessionType':'x','MriType':'y'}]])
def test_malformed_or_unknown_event_inventory_withholds(value):
    candidate=report();candidate['DiagnosticData']['EventLogs']=value
    with pytest.raises(n.ContinuityError,match='event_log'):n.prove_continuity(candidate,report())


def test_shared_event_log_canonical_clock_disagreement_rejects():
    reference=log_report();candidate=deepcopy(reference)
    candidate['DiagnosticData']['EventLogs'][0]['DateTime']=stamp(151)
    assert n.prove_continuity(candidate,reference)
    with pytest.raises(n.ContinuityError,match='canonical_measurement_clock_conflict'):n.verify_clock_agreement(candidate,reference)


@pytest.mark.parametrize('mutation',[
 lambda p:p.update(policy_version='future'),lambda p:p.update(extra=1),lambda p:p.update(candidate_intrinsic_sha256='bad'),
 lambda p:p['witnesses']['chronic'].pop('right'),lambda p:p['witnesses']['psd']['left'].update(count=1),
 lambda p:p['witnesses']['psd']['left'].update(first_offset=9999),lambda p:p['witnesses']['psd']['left'].update(block=True),
 lambda p:p['witnesses']['psd']['left'].update(payloads_sha256='bad'),lambda p:p['candidate_records'].update(psd=0),
 lambda p:p['candidate_records']['chronic'].update(left=-1),lambda p:p['reference_records'].update(extra=0),
 lambda p:p['weakening'].update(blank_contact_claims=-1),lambda p:p['weakening'].update(extra=1),
])
def test_descendant_proof_cannot_be_empty_forged_shape_or_counts(mutation):
    proof=n.prove_continuity(report(),report());mutation(proof);rehash(proof)
    with pytest.raises(n.ContinuityError,match='invalid_continuity_receipt'):n.validate_receipt(proof)


def test_invalid_proof_hash_missing_shape_and_clock_receipts_rejected():
    proof=n.prove_continuity(report(),report());proof['proof_sha256']='0'*64
    with pytest.raises(n.ContinuityError,match='invalid_continuity_receipt'):n.validate_receipt(proof)
    for bad in [None,{},[],{'policy_version':n.POLICY_VERSION}]:
        with pytest.raises(n.ContinuityError,match='invalid_continuity_receipt'):n.validate_receipt(bad)
    clock=n.verify_clock_agreement(report(),report())
    for mutation in [lambda p:p.update(policy_version='future'),lambda p:p.update(shared_clock_nodes=1),lambda p:p.update(shared_clock_nodes=True),lambda p:p.update(clock_observations_sha256='bad'),lambda p:p.update(extra=1)]:
        bad=deepcopy(clock);mutation(bad);rehash(bad)
        with pytest.raises(n.ContinuityError,match='invalid_canonical_clock_receipt'):n.validate_clock_receipt(bad)
    clock['proof_sha256']='0'*64
    with pytest.raises(n.ContinuityError,match='invalid_canonical_clock_receipt'):n.validate_clock_receipt(clock)


def test_no_clock_overlap_and_bad_payload_clock_not_certified():
    a=report();b=report()
    for side in ['Left','Right']:
        for row in rows(a,side):row['DateTimeOffsetInSeconds']+=1
    for e in events(a):
        e['DateTimeOffsetInSeconds']+=1
        for payload in e['LfpFrequencySnapshotEvents'].values():payload['DateTimeOffsetInSeconds']+=1
    with pytest.raises(n.ContinuityError,match='canonical_clock_overlap_unavailable'):n.verify_clock_agreement(a,b)
    with pytest.raises(n.ContinuityError,match='invalid_canonical_clock_receipt'):n.validate_clock_receipt(None)


def test_nontriviality_overflow_and_empty_sides_are_safe_failures():
    assert not n._numeric(10**1000)
    with pytest.raises(n.ContinuityError,match='invalid_native_key'):n._key([])
    with pytest.raises(n.ContinuityError,match='insufficient_chronic'):n.prove_continuity({'DiagnosticData':{}},report())
    with pytest.raises(n.ContinuityError,match='invalid_native_key'):n._intrinsic({'DateTimeBlockId':7})


def test_reattaching_one_spectrum_cannot_invent_distinct_measurement_times():
    reference=report()
    for index in [1,2]:
        for side in ['Left','Right']:events(reference)[index]['LfpFrequencySnapshotEvents']['HemisphereLocationDef.'+side]=deepcopy(psd(reference,0,side))
    with pytest.raises(n.ContinuityError,match='insufficient_psd'):n.prove_continuity(deepcopy(reference),reference)


def test_inner_native_conflict_not_hidden_by_different_outer_event():
    reference=report();candidate=deepcopy(reference)
    events(candidate)[0]['EventID']=99;events(candidate)[0]['DateTimeOffsetInSeconds']+=5
    psd(candidate)['FFTBinData'][0]=99
    with pytest.raises(n.ContinuityError,match='shared_psd_measurement_conflict'):n.prove_continuity(candidate,reference)


def test_duplicate_inner_native_measurement_conflicts_across_event_categories():
    reference=report();candidate=deepcopy(reference);extra=deepcopy(events(candidate)[0]);extra['EventID']=99;extra['DateTimeOffsetInSeconds']+=5
    extra['LfpFrequencySnapshotEvents']['HemisphereLocationDef.Left']['FFTBinData'][0]=99;events(candidate).append(extra)
    with pytest.raises(n.ContinuityError,match='ambiguous_native_duplicate'):n.prove_continuity(candidate,reference)


def test_actual_measurement_continuity_survives_unshared_outer_event_labels():
    reference=report();candidate=deepcopy(reference)
    for event in events(candidate):event['EventID']=99;event['DateTimeOffsetInSeconds']+=5;event['EventName']='New event label'
    proof=n.prove_continuity(candidate,reference)
    assert proof['witnesses']['psd']['left']['count']==3
    assert n.verify_clock_agreement(candidate,reference)['shared_clock_nodes']==12
    psd(candidate)['DateTime']=stamp(99999)
    with pytest.raises(n.ContinuityError,match='canonical_measurement_clock_conflict'):n.verify_clock_agreement(candidate,reference)


def test_unpaired_nested_time_is_preserved_context_not_a_native_clock():
    reference=report();rows(reference)[0]['metadata']={'DateTime':'opaque non-native field','values':[1,2]}
    candidate=deepcopy(reference)
    assert n.prove_continuity(candidate,reference)
    assert n.verify_clock_agreement(candidate,reference)['shared_clock_nodes']>=10
