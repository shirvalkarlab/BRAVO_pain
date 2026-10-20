"""Exact raw identity and storage-only legacy proof; synthetic, no service writes."""
import ast
import copy
import json
import math
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from modules.MedtronicPercept import BrainSenseEvent as B, TabletClock, Percept

L = 'HemisphereLocationDef.Left'
R = 'HemisphereLocationDef.Right'


def raw_document(sense='ZERO_AND_TWO', power=None):
    block = {'DateTime':'2020-01-01T00:00:01Z','DateTimeBlockId':7,'DateTimeOffsetInSeconds':10,
             'Frequency':[0.,1.,2.], 'FFTBinData':power or [0.1,0.2,-1.], 'SenseID':sense}
    event = {'DateTime':'2020-01-01T00:00:01Z','DateTimeBlockId':7,'DateTimeOffsetInSeconds':10,
             'EventID':1,'EventName':'Synthetic','LfpFrequencySnapshotEvents':{L:block}}
    return {'SessionDate':'2020-01-01T00:01:00Z','SessionEndDate':'2020-01-01T00:01:10Z',
            'DeviceInformation':{'Initial':{'DeviceDateTimeOffsetInSeconds':90,'DeviceDateTimeBlockId':7},
                'Final':{'DeviceDateTimeOffsetInSeconds':100,'DeviceDateTimeBlockId':7,'NeurostimulatorSerialNumber':'SYNTHETIC'}},
            'DiagnosticData':{'LfpFrequencySnapshotEvents':[event]}}


def source_index(raw):
    table = TabletClock.AnchorTable([TabletClock.export_anchor(raw)])
    return B.sourceEventIndex(raw, table, TabletClock, Percept)


def source(uid):
    return NS(uid=uid,hashed='hash-'+uid,metadata={},device='synthetic',owner='person')


def helper_namespace():
    path=Path(__file__).parents[2]/'DataCurator.py'
    names={'_event_source_provenance','_event_source_index','_event_sql_json_value',
           '_valid_event_identity','_event_mysql_identities','_save_event_mysql_metadata','_store_patient_event'}
    nodes=[node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name in names]
    models=NS(SourceFile=NS(find=lambda **kw:None),Recording=NS(_meta=NS(db_table='synthetic_recording')))
    namespace={'json':json,'copy':copy,'OrderedDict':OrderedDict,'models':models,'TabletClock':TabletClock}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


class SQL:
    vendor='mysql'
    ops=NS(quote_name=lambda name:'`'+name+'`')
    def __init__(self, transform=lambda x:x):
        self.calls=[]; self.transform=transform; self.rowcount=1
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,query,params):
        self.calls.append((query,params))
        if query.startswith('SELECT'):
            self.answer=json.dumps(self.transform(json.loads(params[0])))
    def fetchone(self): return [self.answer]


def prepared(power=None):
    new,old=source('new'),source('old')
    raw=raw_document(power=power); index=source_index(raw)
    key=next(iter(index)); entry=index[key][0]
    event={'name':key[0],'date':key[1],'type':'PatientControllerEvent','data':{L:copy.deepcopy(entry['block'])}}
    record=NS(uid='record',source=old)
    cache={'current_key':(new.uid,new.hashed),'current_index':index,
           'legacy_indexes':OrderedDict([((old.uid,old.hashed),copy.deepcopy(index))])}
    return event,new,record,cache


def test_source_projection_exact_clock_identity_and_immutability():
    raw=raw_document(); before=copy.deepcopy(raw); index=source_index(raw)
    assert raw==before and len(index)==1
    entry=next(iter(index.values()))[0]
    assert entry['block']['DateTime']=='2019-12-31T23:59:40Z'
    assert entry['identity']['raw_event_index']==0
    assert entry['identity']['sha256']==B.rawSpectrumDigest(raw['DiagnosticData']['LfpFrequencySnapshotEvents'][0]['LfpFrequencySnapshotEvents'][L])
    changed=copy.deepcopy(raw)
    changed['DiagnosticData']['LfpFrequencySnapshotEvents'][0]['DateTime']='2020-01-02T00:00:00Z'
    assert next(iter(source_index(changed).values()))[0]['identity']==entry['identity']
    raw['DiagnosticData']['LfpFrequencySnapshotEvents'].append(copy.deepcopy(raw['DiagnosticData']['LfpFrequencySnapshotEvents'][0]))
    assert len(next(iter(source_index(raw).values())))==2


@pytest.mark.parametrize('missing',['EventID','EventName','serial','block_clock','no_spectrum','empty'])
def test_source_missing_identity_and_no_spectrum(missing):
    raw=raw_document(); ev=raw['DiagnosticData']['LfpFrequencySnapshotEvents'][0]
    if missing=='serial': del raw['DeviceInformation']['Final']['NeurostimulatorSerialNumber']
    elif missing=='block_clock':
        for k in ('DateTime','DateTimeBlockId','DateTimeOffsetInSeconds'): del ev['LfpFrequencySnapshotEvents'][L][k]
    elif missing=='no_spectrum': del ev['LfpFrequencySnapshotEvents']
    elif missing=='empty': raw['DiagnosticData']['LfpFrequencySnapshotEvents']=[]
    elif missing=='EventName': ev['EventName']=''
    else: del ev[missing]
    assert source_index(raw)=={}


def test_source_date_fallback_and_omitted_clock_block():
    raw=raw_document(); ev=raw['DiagnosticData']['LfpFrequencySnapshotEvents'][0]
    for obj in (ev,ev['LfpFrequencySnapshotEvents'][L]):
        del obj['DateTimeBlockId']; del obj['DateTimeOffsetInSeconds']
    assert source_index(raw)
    raw=raw_document(); raw['DiagnosticData']['LfpFrequencySnapshotEvents'][0]['DateTimeBlockId']=6
    assert source_index(raw)=={}


def test_projection_refuses_cardinality_and_spectrum_mutation():
    raw=raw_document(); table=TabletClock.AnchorTable([])
    with pytest.raises(ValueError,match='cardinality'):
        B.sourceEventIndex(raw,table,TabletClock,NS(extractChronicLFP=lambda *a:{}))
    def altered(raw,unused):
        result=Percept.extractChronicLFP(raw,{})
        result['PatientEventLogs'][0]['LfpFrequencySnapshotEvents'][L]['FFTBinData'][0]=10.
        return result
    with pytest.raises(ValueError,match='changed_spectrum'):
        B.sourceEventIndex(raw,table,TabletClock,NS(extractChronicLFP=altered))


@pytest.mark.parametrize('power',[[],[1.],None,[True,2.],[float('nan'),2.],['1',2.],[float('inf'),2.]])
def test_digest_refuses_invalid_arrays(power):
    with pytest.raises(ValueError): B.rawSpectrumDigest({'Frequency':[1.,2.],'FFTBinData':power})


def test_digest_distinguishes_one_ulp_and_event_identity():
    a={'Frequency':[1.],'FFTBinData':[0.1]}; b=copy.deepcopy(a); b['FFTBinData'][0]=math.nextafter(.1,math.inf)
    assert B.rawSpectrumDigest(a)!=B.rawSpectrumDigest(b)
    ids={'sha256':'a','raw_identity_sha256':'b'}
    assert not B._same_spectrum(a,a,ids,None)
    assert not B._same_spectrum(a,a,None,ids)
    assert not B._same_spectrum(a,a,ids,dict(ids,raw_identity_sha256='c'))


def test_raw_identity_merges_sql_rounded_copy_preserving_stored_arrays():
    ns=helper_namespace(); event,new,record,cache=prepared()
    stored=copy.deepcopy(event['data']); stored[L]['FFTBinData'][0]=math.nextafter(.1,math.inf)
    def projection(block):
        block['FFTBinData'][0]=math.nextafter(.1,math.inf); return block
    connection=SQL(projection)
    incoming,old,blocked=ns['_event_mysql_identities'](event,new,record,stored,connection,cache,'person')
    assert blocked=={} and old[L]['sha256']==incoming[L]['sha256']
    event['data'][L]['SenseID']='ONE_AND_THREE'
    action,result,conflicts=B.mergeEventData(stored,event['data'],stored_identities=old,incoming_identities=incoming,
        stored_source={'source_id':'old'},incoming_source={'source_id':'new'})
    assert action=='update' and conflicts==[L] and result[L]['SenseIDConflict']
    assert result[L]['FFTBinData']==stored[L]['FFTBinData']
    ns['_save_event_mysql_metadata'](record,stored,result,connection)
    sql,params=connection.calls[-1]
    assert 'JSON_SET(metadata' in sql and 'FFTBinData' not in str(params) and 'Frequency' not in str(params)
    assert params[-1]=='record' and record.metadata==result
    assert B.mergeEventData(result,event['data'],stored_identities=old,incoming_identities=incoming,
        stored_source={'source_id':'old'},incoming_source={'source_id':'new'})[0]=='keep'


def test_sql_projection_collision_never_defines_raw_identity():
    ns=helper_namespace(); event,new,record,cache=prepared()
    old_index=cache['legacy_indexes'][(record.source.uid,record.source.hashed)]
    oldentry=next(iter(old_index.values()))[0]
    oldentry['block']['FFTBinData'][0]=math.nextafter(.1,math.inf)
    oldentry['identity']['sha256']=B.rawSpectrumDigest(oldentry['block'])
    stored=copy.deepcopy(event['data'])
    def collide(block): block['FFTBinData'][0]=.1; return block
    incoming,old,blocked=ns['_event_mysql_identities'](event,new,record,stored,SQL(collide),cache,'person')
    assert not blocked and old[L]['sha256']!=incoming[L]['sha256']
    action,result,conflicts=B.mergeEventData(stored,event['data'],stored_identities=old,incoming_identities=incoming)
    assert conflicts==[L] and 'SenseIDObservations' not in result[L] and result[L]['FFTBinData']==stored[L]['FFTBinData']
    assert result[L]['SenseID']=='ZERO_AND_TWO'


@pytest.mark.parametrize('failure',['missing','duplicate','proof','load','source_missing','two_identities','incoming_missing','incoming_duplicate','incoming_mismatch'])
def test_unverified_recovery_withholds_contact_but_preserves_raw_and_claim_separation(failure):
    ns=helper_namespace(); event,new,record,cache=prepared(); stored=copy.deepcopy(event['data'])
    legacy=cache['legacy_indexes'][(record.source.uid,record.source.hashed)]; key=next(iter(legacy)); sql=SQL()
    if failure=='missing': legacy.clear()
    elif failure=='duplicate': legacy[key]*=2
    elif failure=='proof': sql=SQL(lambda b:dict(b,FFTBinData=[9.,9.,9.]))
    elif failure=='load': cache['legacy_indexes'].clear(); ns['loadCacheFile']=lambda s:(_ for _ in ()).throw(OSError())
    elif failure=='source_missing': stored[L]['SenseIDObservations']=[{'sense_id':'ZERO_AND_TWO','source':{'source_id':'missing'}}]
    elif failure=='two_identities':
        other=source('other'); ns['models'].SourceFile.find=lambda **kw:other
        stored[L]['SenseIDObservations']=[{'sense_id':'ZERO_AND_TWO','source':{'source_id':'other'}}]
        otherindex=copy.deepcopy(legacy); otherindex[key][0]['identity']['sha256']='c'*64
        cache['legacy_indexes'][(other.uid,other.hashed)]=otherindex
    elif failure=='incoming_missing': cache['current_index']={}
    elif failure=='incoming_duplicate': cache['current_index'][key]*=2
    elif failure=='incoming_mismatch': event['data'][L]['FFTBinData'][0]=5.
    incoming,old,blocked=ns['_event_mysql_identities'](event,new,record,stored,sql,cache,'person')
    assert L in blocked
    event['data'][L]['SenseID']='ONE_AND_THREE'
    _,result,conflicts=B.mergeEventData(stored,event['data'],stored_identities=old,incoming_identities=incoming,
        blocked_sides=blocked,stored_source={'source_id':'old'},incoming_source={'source_id':'new'})
    assert conflicts==[L] and result[L]['SenseID']=='' and result[L]['SenseIDStatus']=='ambiguous'
    assert result[L]['SpectrumIdentityStatus']=='unverified' and result[L]['FFTBinData']==stored[L]['FFTBinData']
    assert {r['sense_id'] for r in result[L]['SenseIDObservations']}=={'ZERO_AND_TWO'}
    assert result[L]['UnverifiedSenseIDObservations'][0]['sense_id']=='ONE_AND_THREE'
    assert B.mergeEventData(result,event['data'],stored_identities=old,incoming_identities=incoming,
        blocked_sides=blocked,stored_source={'source_id':'old'},incoming_source={'source_id':'new'})[0]=='keep'
    # Later successful unrelated observation cannot silently dismiss unresolved provenance.
    assert B.mergeEventData(result,stored)[1][L]['SenseIDStatus']=='ambiguous'


def test_trusted_persisted_identity_bypasses_legacy_sql_but_not_incoming_verification():
    ns=helper_namespace(); event,new,record,cache=prepared(); sql=SQL()
    incoming,old,blocked=ns['_event_mysql_identities'](event,new,record,None,sql,cache,'person')
    assert not blocked and old=={} and sql.calls==[]
    stored=copy.deepcopy(event['data']); stored[L]['RawSpectrumIdentity']=incoming[L]
    cache['legacy_indexes'].clear()
    ns['models'].SourceFile.find=lambda **kw:new
    incoming,old,blocked=ns['_event_mysql_identities'](event,new,record,stored,sql,cache,'person')
    assert not blocked and old[L]==incoming[L] and sql.calls==[]


@pytest.mark.parametrize('value',[None,{}, {'version':B.RAW_SPECTRUM_VERSION},
    {'version':B.RAW_SPECTRUM_VERSION,'sha256':'x'*64,'raw_identity_sha256':'b'*64},
    {'version':B.RAW_SPECTRUM_VERSION,'sha256':7,'raw_identity_sha256':'b'*64},
    {'version':B.RAW_SPECTRUM_VERSION,'sha256':'a'*64,'raw_identity_sha256':'b'*64},
    {'version':B.RAW_SPECTRUM_VERSION,'sha256':'a'*64,'raw_identity_sha256':'b'*64,'source_id':'x'}])
def test_untrusted_identity_format(value):
    assert not helper_namespace()['_valid_event_identity'](value)


def test_cache_bounded_per_export_and_sql_proof_types():
    ns=helper_namespace(); calls=[]; raw=raw_document()
    ns['loadCacheFile']=lambda s:(calls.append(s.uid) or json.dumps(raw))
    ns['clock_anchor_table']=lambda **kw:TabletClock.AnchorTable([])
    cache={}
    for i in range(6): ns['_event_source_index'](source(str(i)),cache)
    assert len(cache['legacy_indexes'])==4 and calls==list(map(str,range(6)))
    ns['_event_source_index'](source('4'),cache); assert len(calls)==6
    ns['_event_source_index'](source('0'),cache); assert len(calls)==7
    sql=SQL(); sql.fetchone=lambda:[b'{"a": 1}']; assert ns['_event_sql_json_value'](sql,{})=={'a':1}
    sql.fetchone=lambda:[{}]
    with pytest.raises(ValueError,match='unexpected_json'): ns['_event_sql_json_value'](sql,{})


def test_json_set_new_side_noop_and_no_array_rewrite():
    ns=helper_namespace(); sql=SQL(); record=NS(uid='x'); block={'Frequency':[1.],'FFTBinData':[.1]}
    ns['_save_event_mysql_metadata'](record,{L:block},{L:block,'ignored':{}},sql)
    assert sql.calls==[]
    ns['_save_event_mysql_metadata'](record,{L:block},{L:block,R:block},sql)
    assert sql.calls[-1][1][0]=='$."HemisphereLocationDef.Right"'
    with pytest.raises(ValueError,match='spectrum_rewrite'):
        ns['_save_event_mysql_metadata'](record,{L:block},{L:dict(block,FFTBinData=[.2])},sql)
    sql.rowcount=0
    with pytest.raises(ValueError,match='row_missing'):
        ns['_save_event_mysql_metadata'](record,{L:block},{L:dict(block,SenseID='new')},sql)


def test_malformed_partial_blocks_remain_unassigned_without_aborting_other_events():
    raw=raw_document(); event=raw['DiagnosticData']['LfpFrequencySnapshotEvents'][0]
    event['LfpFrequencySnapshotEvents']['note']={'description':'ignored'}
    event['LfpFrequencySnapshotEvents'][R]=copy.deepcopy(event['LfpFrequencySnapshotEvents'][L])
    event['LfpFrequencySnapshotEvents'][R]['FFTBinData']=[]
    assert set(source_index(raw))=={('Synthetic',1577836780.,L)}
    ns=helper_namespace(); event,new,record,cache=prepared()
    event['data'][L]['FFTBinData']=[]
    incoming,old,blocked=ns['_event_mysql_identities'](event,new,record,None,SQL(),cache,'person')
    assert incoming=={} and old=={} and L in blocked
    action,result,conflicts=B.mergeEventData(None,event['data'],blocked_sides=blocked,incoming_source={'source_id':'new'})
    assert action=='create' and conflicts==[L] and result[L]['SenseIDStatus']=='ambiguous'
    assert result[L]['FFTBinData']==[] and result[L]['SpectrumIdentityReason']==blocked[L]
    action,result,conflicts=B.mergeEventData({},event['data'],blocked_sides=blocked,incoming_source={'source_id':'new'})
    assert action=='update' and conflicts==[L] and result[L]['SenseIDStatus']=='ambiguous'


def test_incoming_loader_failure_and_ignored_keys():
    ns=helper_namespace(); event,new,record,cache=prepared(); event['data']['note']={}
    cache.pop('current_key'); ns['loadCacheFile']=lambda s:(_ for _ in ()).throw(OSError())
    assert L in ns['_event_mysql_identities'](event,new,record,None,SQL(),cache,'person')[2]
    raw=raw_document(); calls=[]; ns['loadCacheFile']=lambda s:(calls.append(s.uid) or json.dumps(raw))
    cache={'table':TabletClock.AnchorTable([])}
    assert ns['_event_source_index'](new,cache) and calls==['new']


def test_persisted_identity_requires_current_source_ownership_and_hash():
    ns=helper_namespace(); event,new,record,cache=prepared(); sql=SQL()
    incoming,_,_=ns['_event_mysql_identities'](event,new,record,None,sql,cache,'person')
    stored=copy.deepcopy(event['data']); stored[L]['RawSpectrumIdentity']=dict(incoming[L],source_id='old',source_hash='wrong')
    stored[L]['SenseIDObservations']=[{'sense_id':'ZERO_AND_TWO','source':{'source_id':'old'}}]
    _,old,blocked=ns['_event_mysql_identities'](event,new,record,stored,sql,cache,'person')
    assert not blocked and old[L]['source_hash']=='hash-old' and sql.calls
    # A persisted identity may come from a later same-owner source: must resolve it.
    stored[L]['RawSpectrumIdentity']=incoming[L]; ns['models'].SourceFile.find=lambda **kw:new
    sql.calls.clear()
    assert not ns['_event_mysql_identities'](event,new,record,stored,sql,cache,'person')[2] and not sql.calls
    ns['models'].SourceFile.find=lambda **kw:None
    cache['legacy_indexes'].clear(); ns['loadCacheFile']=lambda s:(_ for _ in ()).throw(OSError())
    assert L in ns['_event_mysql_identities'](event,new,record,stored,sql,cache,'person')[2]


def test_mysql_caller_first_ingest_repeat_conflict_and_identity_claim_scrubbing():
    from .test_event_copies_merge import ingestion_harness
    ns=helper_namespace(); sql=SQL(); event,new,record,cache=prepared()
    store,events,_=ingestion_harness(sql,ns)
    event['data']['note']={'kept':'original'}
    event['data'][L]['RawSpectrumIdentity']={'sha256':'attacker supplied'}
    original=copy.deepcopy(event)
    assert store(event,record.source,'person',identity_cache=cache)=='create'
    saved=events[0].data.first()
    assert saved.saves==1 and saved.metadata[L]['RawSpectrumIdentity']['source_id']=='old'
    event['data'][L]['SenseID']='ONE_AND_THREE'
    assert store(event,new,'person',identity_cache=cache)=='update'
    assert saved.saves==1 and saved.metadata[L]['SenseIDConflict']
    assert store(event,new,'person',identity_cache=cache)=='keep'
    assert len(new.metadata['IngestConflicts'])==1
    assert event['data'][L]['RawSpectrumIdentity']==original['data'][L]['RawSpectrumIdentity']


def test_unverified_contact_guard_retains_display_with_reason():
    ns=helper_namespace(); event,new,record,cache=prepared(); stored=copy.deepcopy(event['data'])
    _,data,_=B.mergeEventData(stored,event['data'],blocked_sides={L:'legacy_raw_identity_or_storage_proof_unavailable'})
    device=NS(get_info=lambda:{'Heritage':[],'Electrodes':[]})
    display=B.extractBrainSenseEventRecording({'Device':'synthetic','Metadata':data,'Date':1},NS(filter=lambda **kw:NS(first=lambda:device)))[0]
    assert display['Power']==stored[L]['FFTBinData'] and display['SenseConfig']==''
    assert display['SenseConfigConflict'] and display['SenseConfigUnavailableReason']=='legacy_raw_identity_or_storage_proof_unavailable'


def test_exact_numeric_identity_equivalence_without_float_rounding():
    assert B.RAW_SPECTRUM_VERSION == 'raw-event-spectrum-v2'
    assert B._exact_numeric_identity([1, 0, -1]) == B._exact_numeric_identity([1.0, -0.0, -1.0])
    assert B._exact_numeric_identity(0.1) == ['number', 3602879701896397, 36028797018963968]
    assert B._exact_numeric_identity('1') != B._exact_numeric_identity(1)
    enormous = 10 ** 400
    assert B._exact_numeric_identity(enormous) == ['number', enormous, 1]
    a = {'Frequency':[0, 1, 2], 'FFTBinData':[0, 1, enormous]}
    b = {'Frequency':[0.0, 1.0, 2.0], 'FFTBinData':[-0.0, 1.0, enormous]}
    assert B.rawSpectrumDigest(a) == B.rawSpectrumDigest(b)
    b['FFTBinData'][2] = enormous + 1
    assert B.rawSpectrumDigest(a) != B.rawSpectrumDigest(b)
    a['FFTBinData'][2] = 2 ** 53
    b['FFTBinData'][2] = float(2 ** 53)
    assert B.rawSpectrumDigest(a) == B.rawSpectrumDigest(b)
    a['FFTBinData'][2] += 1
    assert B.rawSpectrumDigest(a) != B.rawSpectrumDigest(b)


@pytest.mark.parametrize('bad', [True, float('inf'), float('nan'), None, {}])
def test_exact_numeric_identity_rejects_unsupported_values(bad):
    with pytest.raises(ValueError):
        B._exact_numeric_identity(bad)


def test_numeric_encoding_equivalent_event_and_spectra_surfaces_contact_conflict():
    first = raw_document(power=[0, 1, -1])
    second = copy.deepcopy(first)
    event = second['DiagnosticData']['LfpFrequencySnapshotEvents'][0]
    event['EventID'] = float(event['EventID'])
    block = event['LfpFrequencySnapshotEvents'][L]
    block['Frequency'] = list(map(int, block['Frequency']))
    block['FFTBinData'] = [-0.0, 1.0, -1.0]
    block['SenseID'] = 'ONE_AND_THREE'
    for obj in (event, block):
        obj['DateTimeBlockId'] = float(obj['DateTimeBlockId'])
        obj['DateTimeOffsetInSeconds'] = float(obj['DateTimeOffsetInSeconds'])
    a_index, b_index = source_index(first), source_index(second)
    key = next(iter(a_index))
    assert a_index.keys() == b_index.keys()
    a, b = a_index[key][0], b_index[key][0]
    assert a['identity'] == b['identity']
    outcomes = []
    for original, incoming in ((a,b), (b,a)):
        _, created, _ = B.mergeEventData(None, {L:original['block']}, incoming_identities={L:original['identity']})
        _, result, conflicts = B.mergeEventData(created, {L:incoming['block']},
            stored_identities={L:original['identity']}, incoming_identities={L:incoming['identity']})
        assert conflicts == [L] and result[L]['SenseID'] == '' and result[L]['SenseIDConflict']
        assert result[L]['FFTBinData'] == original['block']['FFTBinData']
        assert B.mergeEventData(result, {L:incoming['block']}, stored_identities={L:original['identity']},
            incoming_identities={L:incoming['identity']})[0] == 'keep'
        outcomes.append(result[L]['SenseIDObservations'])
    assert outcomes[0] == outcomes[1]
    # A numeric-looking string is not the same event identifier.
    event['EventID'] = '1'
    assert source_index(second)[key][0]['identity']['raw_identity_sha256'] != a['identity']['raw_identity_sha256']
    event['EventID'] = True
    assert source_index(second) == {}


def test_v1_receipt_recovers_v2_only_from_verified_raw_source():
    ns=helper_namespace(); event,new,record,cache=prepared(); sql=SQL()
    stored=copy.deepcopy(event['data'])
    stored[L]['RawSpectrumIdentity']={'version':'raw-event-spectrum-v1', 'sha256':'a'*64,
        'raw_identity_sha256':'b'*64, 'source_id':'old', 'source_hash':'hash-old'}
    incoming,old,blocked=ns['_event_mysql_identities'](event,new,record,stored,sql,cache,'person')
    assert not blocked and sql.calls and old[L]['version']=='raw-event-spectrum-v2'
    assert old[L]['sha256']==incoming[L]['sha256'] and old[L]['sha256']!='a'*64
    cache['legacy_indexes'].clear(); ns['loadCacheFile']=lambda s:(_ for _ in ()).throw(OSError())
    assert L in ns['_event_mysql_identities'](event,new,record,stored,SQL(),cache,'person')[2]
