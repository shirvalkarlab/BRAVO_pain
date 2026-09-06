"""Synthetic canonical-score, source reconciliation and notebook grouping contracts."""
import base64
import copy
import csv
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace as NS
import zlib

import pandas as pd
import pytest

from modules import RedcapComparisons as comparisons
from modules import RedcapComparisonSources as source
from modules.RedcapTimeline import METRICS

HASH = 'a'*64


def score(index=1, when='2025-07-16T12:00:00-07:00', **changes):
    row = {key: None for key,_,_ in METRICS}
    row.update(participant_id='RCS08', source_event='daily',source_instrument='survey',repeat_instance=str(index),
               survey_start=when,study_stage='stage_1',include_in_analysis=True,nrs_intensity=5)
    row.update(changes)
    return row


def stim(row=None, **changes):
    result = dict(row or score())
    result.update(stim_match_resolved=True,stim_json_match_same_day=True,stim_json_boundary_used='initial',
        stim_status='ON',stim_cycle_enabled=False,stim_soft_start_stop_enabled=False,
        stim_left_amplitude_mA=3,stim_right_amplitude_mA=0,stim_left_contacts='1-2',stim_right_contacts='3-4',
        stim_left_pulse_width_us=60,stim_left_rate_hz=130,stim_left_adaptive_status='DISABLED',
        stim_right_adaptive_status='DISABLED',stim_amplitude_control='Independent')
    result.update(changes)
    return result


def med(**changes):
    row=dict(generic_name='Medicine',analysis='true',pre_trial='true',ongoing='true',prn='false',
             start_date='',end_date='',dose='10 mg',timing='morning',frequency='daily',route='',
             pharmacologic_class='gabapentinoid',note='Documented regimen')
    row.update(changes)
    return row


def pack(value):
    return base64.b64encode(zlib.compress(json.dumps(value).encode())).decode()


def unpack(value):
    return json.loads(zlib.decompress(base64.b64decode(value)))


def write(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def reference_rule(program=None):
    program = stim() if program is None else program
    return {'version': 1, 'program': program, 'condition_id': source.functional(program)['id'],
            'source': {'title': 'Synthetic testing sheet', 'url': 'https://docs.google.com/spreadsheets/d/synthetic/edit',
                       'range': "'Home Programs'!A3:U6", 'verified_at': '2026-09-04T00:00:00Z'}}


def test_finalized_reference_publishes_exact_reviewed_identity_without_changing_membership(tmp_path, monkeypatch):
    monkeypatch.setenv('RCS08_PROCESSING_RULES', str(tmp_path))
    rule = reference_rule()
    path = tmp_path / 'finalized_open_loop.json'
    path.write_text(json.dumps(rule))
    reference = comparisons.finalized_reference()
    assert reference['available'] and reference['id'] == rule['condition_id']
    assert reference['label'] == 'Finalized OL' and reference['source'] == rule['source']
    assert len(reference['rule_sha256']) == 64
    assert reference == comparisons.finalized_reference(tmp_path)
    published = comparisons.stim_publication([stim()], [score()])
    assert published['finalized_open_loop'] == reference
    assert len(published['assignments']) == 1
    # A source group letter never controls membership; a different amplitude
    # remains another condition even if it is also called Group A.
    different = stim(stim_active_group_id='GROUP_A', stim_left_amplitude_mA=4)
    published = comparisons.stim_publication([different], [score()])
    assert published['assignments'][0]['condition'] != reference['id']
    assert published['finalized_open_loop'] == reference
    empty = comparisons.stim_publication([], [])
    assert not empty['assignments'] and empty['finalized_open_loop'] == reference


def test_finalized_reference_missing_or_malformed_does_not_disable_ranked_comparisons(tmp_path, monkeypatch):
    monkeypatch.setenv('RCS08_PROCESSING_RULES', str(tmp_path))
    assert not comparisons.finalized_reference()['available']
    valid = reference_rule()
    invalid = [None, [], {}, {'version': 2, **{k:v for k,v in valid.items() if k != 'version'}},
               {**valid, 'source': []}, {**valid, 'source': {**valid['source'], 'title': ''}},
               {**valid, 'source': {**valid['source'], 'url': 'javascript:alert(1)'}},
               {**valid, 'condition_id': 'another'}, {**valid, 'program': {}},
               reference_rule(stim(stim_status='OFF')),
               reference_rule(stim(stim_left_adaptive_status='RUNNING'))]
    path = tmp_path / 'finalized_open_loop.json'
    for rule in invalid:
        path.write_text(json.dumps(rule))
        assert not comparisons.finalized_reference()['available']
    path.write_text('{broken')
    published = comparisons.stim_publication([stim()], [score()])
    assert published['available'] and not published['finalized_open_loop']['available']
    assert len(published['assignments']) == 1


def home_program(threshold='166 LFP Power (LSB)'):
    return {'group': [{'label':'Group','value':'Group D'}, {'label':'Mode at observation','value':'Closed loop'}],
            'left': [{'label':'Lower LFP threshold','value':threshold}, {'label':'Frequency','value':'55 Hz'}], 'right': []}


def test_current_home_reference_matches_complete_source_boundary_and_never_backfills_new_thresholds():
    settings = home_program()
    signature = comparisons.home_signature(settings)
    event = {'time':100, 'settings':settings, 'source_url':'https://example.test/review', 'evidence':'Reviewed change'}
    context = {'home_transitions':[event], '_comparison_snapshots':[
        {'source':'source.json','phase':'Final','signature':signature}]}
    publication = {'conditions':[{'id':'a','mode':'closed_loop'}], 'assignments':[
        {'condition':'a','session_source':'source.json','boundary':'final'}]}
    reference = comparisons.current_closed_loop(publication,context,200)
    assert reference['available'] and reference['id']=='a'
    assert reference['home_settings'] == settings
    assert reference['source']['url'] == event['source_url']
    assert reference['settings'][2] == {'label':'Left Lower LFP threshold','value':'166 LFP Power (LSB)'}
    assert reference['home_time']==100
    # A newer home threshold is current even when the last exported survey
    # assignment still describes the old threshold. Do not reuse its cohort.
    newer = {'time':150, 'settings':home_program('167 LFP Power (LSB)')}
    context['home_transitions'].append(newer)
    reference = comparisons.current_closed_loop(publication,context,200)
    assert reference['id'].startswith('home-') and reference['home_time']==150
    assert reference['source']['url']=='' and 'No unique' in reference['matching_message']
    assert comparisons.current_closed_loop(publication,context,125)['id']=='a'
    # A filename alone cannot override the resolved Initial/Final boundary.
    context['home_transitions'] = [event]
    publication['assignments'][0]['boundary']='initial'
    assert comparisons.current_closed_loop(publication,context,200)['id'].startswith('home-')
    context['_comparison_snapshots'][0]['phase']='Initial'
    assert comparisons.current_closed_loop(publication,context,200)['id']=='a'
    publication['assignments'][0]['boundary']='unchanged_initial_final'
    assert comparisons.current_closed_loop(publication,context,200)['id']=='a'
    # Conflicting source snapshots, or multiple functional identities, are not pooled.
    context['_comparison_snapshots'].append({'source':'source.json','phase':'Initial','signature':'conflict'})
    assert comparisons.current_closed_loop(publication,context,200)['id'].startswith('home-')
    context['_comparison_snapshots'].pop()
    publication['conditions'].append({'id':'b','mode':'closed_loop'})
    publication['assignments'].append({**publication['assignments'][0], 'condition':'b'})
    assert comparisons.current_closed_loop(publication,context,200)['id'].startswith('home-')
    publication['conditions'][1]['mode']='open_loop'
    assert comparisons.current_closed_loop(publication,context,200)['id']=='a'


def test_current_home_reference_unknown_future_non_closed_and_conflicting_states_are_explicit():
    current = {'time':100, 'settings':home_program()}
    for context in ({}, {'home_transitions':[current]},
                    {'home_transitions':[current], 'home_unknown_intervals':[{'start':90,'end':None}]},
                    {'home_transitions':[current], 'home_unknown_intervals':[{'start':90,'end':110}]},
                    {'home_transitions':[current, {'time':100,'settings':home_program('different')}]},
                    {'home_transitions':[{'time':90,'settings':{'group':[],'left':[],'right':[]}}]}):
        now = 99 if context == {'home_transitions':[current]} else 100
        assert not comparisons.current_closed_loop({},context,now)['available']
    context = {'home_transitions':[current], 'home_unknown_intervals':[{'start':20,'end':100},{'start':200,'end':None}]}
    assert comparisons.current_closed_loop({},context,100)['available']
    # Display group/target labels and sampled currents are not program changes;
    # ordered fields, thresholds, timing and delivered settings are.
    altered = copy.deepcopy(current['settings'])
    altered['group'][0]['value']='Group A'
    altered['left'] += [{'label':'Tablet target','value':'Alias'}, {'label':'Exported contact amplitudes (snapshot)','value':'0.2 mA'}]
    altered['left'].reverse()
    assert comparisons.home_signature(altered)==comparisons.home_signature(current['settings'])


def test_functional_key_preserves_delivered_and_adaptive_differences_ignores_labels():
    baseline=source.functional(stim())
    assert baseline['mode']=='open_loop'
    assert source.functional(stim(stim_active_group_name='Different',stim_active_group_id='B'))['id']==baseline['id']
    assert source.functional(stim(stim_right_contacts='unrelated'))['id']==baseline['id']
    for key in source.SIDE_FIELDS:
        assert source.functional(stim(**{'stim_left_'+key:'different'}))['id']!=baseline['id'] if key not in ('amplitude_mA','pulse_width_us','rate_hz') else True
    assert source.functional(stim(stim_left_amplitude_mA=4))['id']!=baseline['id']
    adaptive=stim(stim_left_adaptive_status='RUNNING',stim_left_amplitude_mA=0,stim_left_upper_limit_mA=4)
    expected=source.functional(adaptive)
    assert expected['mode']=='closed_loop'
    for field in source.ADAPTIVE_FIELDS:
        altered=dict(adaptive);altered['stim_right_'+field]='changed'
        assert source.functional(altered)['id']!=expected['id']
    assert source.functional(dict(adaptive,stim_high_pass_filter_hz=1))['id']!=expected['id']
    assert source.functional(stim(stim_cycle_enabled=True,stim_cycle_on_sec=5,stim_cycle_off_sec=10))['id']!=baseline['id']
    assert source.functional(stim(stim_soft_start_stop_enabled=True,stim_soft_start_stop_sec=3))['id']!=baseline['id']


def test_functional_current_modes_fallbacks_and_unknown_not_off():
    for row in [stim(stim_status='OFF'),stim(stim_left_amplitude_mA=0),stim(stim_left_pulse_width_us=0),stim(stim_left_rate_hz=0)]:
        assert source.functional(row)['id']=='OFF'
    assert source.functional(stim(stim_right_amplitude_mA=2))['label'].startswith('OL-B')
    assert source.functional(stim(stim_left_amplitude_mA=0,stim_right_amplitude_mA=2))['label'].startswith('OL-R')
    assert source.functional(stim(stim_left_amplitude_mA=None,stim_left_runtime_average_amplitude_mA=3))['mode']=='open_loop'
    assert source.functional(stim(stim_left_amplitude_mA=None,stim_left_electrode_amplitude_max_mA=3))['mode']=='open_loop'
    assert source.functional(stim(stim_left_amplitude_mA=None,stim_left_programmed='False'))['id']=='OFF'
    for changes in [dict(stim_status=''),dict(stim_match_resolved=False),dict(stim_json_match_same_day=False),
                    dict(stim_json_boundary_used='unknown'),dict(stim_left_amplitude_mA=None),dict(stim_cycle_enabled='invalid')]:
        with pytest.raises(ValueError): source.functional(stim(**changes))
    assert source.atom(None)=='NA' and source.atom('')=='NA'
    assert source.atom(True)=='1' and source.atom(False)=='0'
    assert source.atom('3.000')=='3' and source.atom(' a  b ')=='a b'
    assert not source.flag(None) and source.flag('',blank=True)


def test_reconciliation_requires_same_patient_identity_time_all_scores_and_resolved_setting():
    canonical=[score(i) for i in range(1,7)]
    rows=[stim(canonical[0]),stim(canonical[1],vas_intensity=50),
          stim(canonical[2],survey_start='2025-07-17T12:00:00-07:00'),
          stim(canonical[3],stim_status='unknown'),stim(canonical[4],participant_id='OTHER'),
          stim(canonical[5],include_in_analysis=False),stim(score(99))]
    before=copy.deepcopy(rows)
    result=comparisons.stim_publication(rows,canonical)
    assert rows==before and result['available']
    assert result['provenance']['matched']==1
    assert result['provenance']['not_canonical']==2
    assert result['provenance']['score_or_time_mismatch']==3
    assert result['provenance']['unknown_stimulation']==1
    assert result['provenance']['unmatched_canonical']==5
    assert result['assignments'][0]['record']=='daily:survey:1'
    assert 'nrs_intensity' not in json.dumps(result)
    with pytest.raises(ValueError,match='Duplicate'):comparisons.stim_publication([rows[0],rows[0]],canonical)
    with pytest.raises(ValueError):comparisons.record_identity(score(repeat_instance='bad'))
    with pytest.raises(ValueError):comparisons.record_identity(score(repeat_instance='1.5'))
    assert not comparisons.stim_publication([],canonical)['available']


def test_medications_notebook_intervals_prn_supportive_and_unknown_dates():
    first=source.day_epoch('2025-07-16')
    rows=[med(),med(generic_name='PRN',prn='true',start_date='2025-07-17',end_date='2025-07-18',timing='pm',route=' Oral '),
          med(generic_name='Support',analysis='false',pharmacologic_class='stool_softener'),
          med(generic_name='UnknownStart',pre_trial='false',end_date='2025-07-18'),
          med(generic_name='UnknownEnd',ongoing='false'),med(generic_name='Fallback',pharmacologic_class='novel')]
    episodes,unavailable=source.medications(rows,first)
    assert len(episodes)==6 and unavailable==2
    assert episodes[0]['start']==first and episodes[0]['end'] is None and episodes[0]['ongoing']
    assert episodes[0]['route']=='oral' and episodes[0]['timing']=='08:00'
    assert episodes[0]['drug_class']=='Anticonvulsants / neuropathic agents'
    assert episodes[1]['status']=='prn_available' and episodes[1]['timing']=='19:00'
    assert episodes[2]['supportive'] and episodes[2]['drug_class']=='Gastrointestinal supportive agents'
    assert episodes[3]['start'] is None and episodes[4]['end'] is None and not episodes[4]['ongoing']
    assert episodes[5]['drug_class']=='novel' and episodes[5]['drug_class_order']==9
    canonical=[score(1),score(2,'2025-07-17T23:59:59-07:00'),score(3,'2025-07-18T00:00:00-07:00')]
    result=comparisons.med_publication(rows,canonical)
    prn=[a for a in result['assignments'] if a['condition']==episodes[1]['condition_id']]
    assert len(prn)==1 and prn[0]['record']=='daily:survey:2'
    assert not any(c['generic']=='Support' for c in result['conditions'])
    with pytest.raises(ValueError): source.medications([med(generic_name='')],first)
    with pytest.raises(ValueError): source.medications([med(start_date='2025-07-18',end_date='2025-07-17')],first)
    with pytest.raises(ValueError): source.medications([med(analysis='invalid')],first)
    with pytest.raises(ValueError,match='overlap'): comparisons.med_publication([med(),med()],canonical)
    with pytest.raises(ValueError,match='Stage 1'): comparisons.med_publication([med()],[score(study_stage='stage_2')])


def test_optional_sources_publish_hashes_and_never_change_canonical_scores(tmp_path,monkeypatch):
    canonical=pd.DataFrame([score(),score(2,include_in_analysis=False),score(3,study_stage='stage_0')])
    before=canonical.copy(deep=True)
    monkeypatch.delenv('RCS08_COMPARISON_SOURCE_DIR',raising=False)
    assert not unpack(comparisons.publish(canonical,HASH))['stimulation']['available']
    assert not unpack(comparisons.publish(canonical,HASH,tmp_path))['medications']['available']
    stim_path=tmp_path/'stim/rcs08_stage1_to_stage3_pain_stim_matches.csv'
    med_path=tmp_path/'medications/rcs08_medications.csv'
    write(stim_path,[stim()]);write(med_path,[med()])
    value=unpack(comparisons.publish(canonical,HASH,tmp_path,period_start=100))
    assert value['stimulation']['available'] and value['medications']['available']
    assert value['stimulation']['provenance']['period_start']==100
    assert value['stimulation']['provenance']['source_sha256']==source.hashlib.sha256(stim_path.read_bytes()).hexdigest()
    assert value['reviewed_sha256']==HASH
    assert value['code_sha256']==comparisons.code_identity()
    assert value['stimulation']['provenance']['grouping_code_sha256']==value['code_sha256']
    pd.testing.assert_frame_equal(canonical,before)
    med_path.write_text('a,b\n1\n')
    assert not unpack(comparisons.publish(canonical,HASH,tmp_path))['medications']['available']
    assert unpack(comparisons.publish(canonical,HASH,tmp_path))['stimulation']['available']
    med_path.write_text('a,b\n1,2,3\n')
    with pytest.raises(ValueError):comparisons.source_csv(med_path)


def test_grouping_top_three_per_metric_modes_minimum_five_off_and_compact_points():
    conditions=[];assignments=[];points=[]
    for i,(mode,n,value) in enumerate([('open_loop',5,5),('open_loop',5,2),('open_loop',5,3),
                                      ('open_loop',5,4),('open_loop',4,1),('closed_loop',5,6),('no_active_current',2,7)]):
        key=str(i);conditions.append({'id':key,'label':'program'+key,'mode':mode,'settings':[]})
        for j in range(n):
            record=f'{i}-{j}';when=100+i*10+j
            assignments.append({'condition':key,'record':record,'time':when})
            points.append({'record':record,'time':when,'value':value,'source':'Daily PRO','phase':'stage_1'})
    # A historical point with same identity must never join.
    points.append(dict(points[0],source='Stage 0 mini VAS',value=99))
    points.append(dict(points[0],phase='stage_0',value=99))
    metric={'key':'nrs_intensity','label':'NRS','range':[0,10],'points':points}
    publication={'conditions':conditions,'assignments':assignments,'provenance':{'canonical_rows':31}}
    result=comparisons.grouped([metric],publication)[0]
    assert result['top']['open_loop']==['1','2','3']
    assert result['top']['closed_loop']==['5']
    assert [c['median'] for c in result['conditions']]==[1,2,3,4,5,6]
    assert result['baseline']['count']==2 and result['baseline']['median']==7
    assert set(result['conditions'][0]['points'][0])=={'time','value','record'}
    assert not comparisons.grouped([metric],publication,True)[0]['conditions'][0]['background']
    single={'conditions':[conditions[0]],'assignments':assignments[:5],'provenance':{'canonical_rows':5}}
    assert comparisons.grouped([metric],single,True)[0]['conditions'][0]['background']


def test_read_uses_existing_points_matching_publication_and_handles_missing_stale_corrupt(tmp_path):
    canonical=pd.DataFrame([score()]);write(tmp_path/'stim/rcs08_stage1_to_stage3_pain_stim_matches.csv',[stim()])
    write(tmp_path/'medications/rcs08_medications.csv',[med(),med(generic_name='Future',start_date='2030-01-01')])
    raw=comparisons.publish(canonical,HASH,tmp_path)
    stamp=comparisons.timestamp(score()['survey_start'])
    metric={'key':'nrs_intensity','label':'NRS','range':[0,10],
            'points':[{'time':stamp,'value':9,'record':'daily:survey:1','source':'Daily PRO','phase':'stage_1'}]}
    # The score comes exclusively from current reviewed report, never CSV's stored 5.
    form=NS(record=[{'comparison_context':raw,'processing':{'reviewed_sha256':HASH}}])
    result=comparisons.read(form,[metric],stamp)
    assert result['stimulation']['metrics'][0]['conditions'][0]['median']==9
    assert len(result['medications']['episodes'])==1
    assert 'assignments' not in result['stimulation']
    assert not comparisons.read(NS(record=[{}]),[],stamp)['stimulation']['available']
    for damaged in ['bad',pack({'version':'old','reviewed_sha256':HASH}),
                    pack({'version':comparisons.VERSION,'code_sha256':comparisons.code_identity(),'reviewed_sha256':'b'*64}),
                    pack({'version':comparisons.VERSION,'code_sha256':comparisons.code_identity(),'reviewed_sha256':HASH,'stimulation':None})]:
        form.record[0]['comparison_context']=damaged
        assert not comparisons.read(form,[metric],stamp)['stimulation']['available']


def test_closed_loop_shared_settings_are_visible_without_changing_identity():
    row=stim(stim_left_adaptive_status='RUNNING',stim_high_pass_filter_hz=1.2,
             stim_sensing_blanking_duration_us=1500)
    result=source.functional(row)
    # Golden identity captured before adding display-only shared settings rows.
    assert result['id']=='821098d56d4e045bab7a'
    settings={field['label']:field['value'] for field in result['settings']}
    assert settings['High-pass filter (Hz)']=='1.2'
    assert settings['Sensing blanking duration (µs)']=='1500'
    assert settings['Amplitude control']=='Independent'
    assert settings['Active stimulation sides']=='Left'
    assert settings['Stimulation mode']=='Closed loop'
    unknown=source.functional(stim(stim_left_adaptive_status='RUNNING'))
    missing={field['label']:field['value'] for field in unknown['settings']}
    assert missing['High-pass filter (Hz)']=='NA'
    assert missing['Sensing blanking duration (µs)']=='NA'
    for key,label in [('stim_high_pass_filter_hz','High-pass filter (Hz)'),
                      ('stim_sensing_blanking_duration_us','Sensing blanking duration (µs)')]:
        changed=source.functional(dict(row,**{key:2}))
        displayed={field['label']:field['value'] for field in changed['settings']}
        assert changed['id']!=result['id'] and displayed[label]=='2'
    open_loop={field['label']:field['value'] for field in source.functional(stim())['settings']}
    assert open_loop['Stimulation mode']=='Open loop'
    assert 'High-pass filter (Hz)' not in open_loop
