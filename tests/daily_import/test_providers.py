"""Synthetic provider-stage boundaries; no provider network or live database."""
import contextlib
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/daily_import'))
import providers as m

@pytest.fixture
def setup(monkeypatch):
    person=NS(uid='a'*32,institute_id='b'*32,institute=NS(),name='Synthetic')
    frame=pd.DataFrame({'nrs':[0.,float('nan')], 'date_time_s1_daily':['local','local'],
        '_pro_time_utc':pd.to_datetime(['2020-01-01T00:00:00Z','2020-01-02T00:00:00Z'])})
    records=[{'Date':1.,'Result':[[0.]]},{'Date':2.,'Result':[[None]]}]
    parsed={'records':records,'FieldMapping':[{'synthetic':'mapping'}],'skipped':0}
    form=NS(uid='c'*32,record=parsed['FieldMapping'])
    rows=[NS(date=x['Date'],record=x['Result']) for x in records]
    models=NS(Participant=NS(objects=Mock()),ScaleForms=NS(find=Mock(return_value=None),objects=Mock()),
        ScaleRecord=NS(objects=Mock()),ParticipantLinkRel=NS(include=Mock(return_value=True)))
    models.ScaleForms.objects.get.return_value=form
    models.ScaleRecord.objects.filter.return_value=rows
    service=NS(import_export=Mock(side_effect=lambda *a,**k:[{'FormId':form.uid,'Unchanged':True}]))
    parser=NS(parse_export=Mock(return_value=[parsed]),RECORD_TYPE='synthetic')
    tx=NS(atomic=contextlib.nullcontext)
    return NS(person=person,frame=frame,records=records,parsed=parsed,form=form,rows=rows,models=models,service=service,parser=parser,tx=tx,mapping={'pt':'Synthetic','metric_labels':{'nrs':'source'}})

def persist(s):
    return m.persist_redcap(s.person,s.frame,s.mapping,s.models,s.service,s.parser,s.tx)

def test_exact_native_handoff_zero_missing_and_repeat(setup):
    s=setup
    assert persist(s)=={'records':2,'metrics':1,'skipped_timestamps':0,'unchanged':False}
    assert s.service.import_export.call_args_list[0].kwargs['timestamp_col']=='_pro_time_utc'
    assert s.service.import_export.call_args_list[0].kwargs['metric_cols']==['nrs']
    assert s.service.import_export.call_args_list[0].kwargs['skip_if_unchanged'] is False
    s.models.ScaleForms.find.return_value=s.form
    assert persist(s)['unchanged'] is True
    s.rows[0].date=1.001
    s.service.import_export.side_effect=lambda *a,**k:(setattr(s.rows[0],'date',1.) or [{'FormId':s.form.uid,'Unchanged':True}])
    assert persist(s)['unchanged'] is False

@pytest.mark.parametrize('case',['metrics','empty','timestamp','naive','helper','infinite','no_records','schema','results','mapping','stored','link','repeat_count','repeat_flag','repeat_id','repeat_stored'])
def test_fail_closed(setup,case):
    s=setup
    if case=='metrics':s.mapping['metric_labels']={}
    if case=='empty':s.frame=s.frame.iloc[:0]
    if case=='timestamp':s.frame=s.frame.drop(columns='_pro_time_utc')
    if case=='naive':s.frame['_pro_time_utc']=s.frame['_pro_time_utc'].astype(str)
    if case=='helper':s.mapping['metric_labels']={'date_time_s1_daily':'source'}
    if case=='infinite':s.frame.loc[0,'nrs']=float('inf')
    if case=='no_records':s.parsed['records']=[]
    if case=='schema':s.models.ScaleForms.find.return_value=NS(record=[])
    if case=='results':s.service.import_export.side_effect=lambda *a,**k:[]
    if case=='mapping':s.form.record=[]
    if case=='stored':s.rows[0].date=1.5
    if case=='link':s.models.ParticipantLinkRel.include.return_value=False
    if case.startswith('repeat_'):
        result={'FormId':s.form.uid,'Unchanged':True}
        other=copy.deepcopy(result)
        if case=='repeat_flag':other['Unchanged']=False
        if case=='repeat_id':other['FormId']='wrong'
        if case=='repeat_stored':
            def run(*args,**kwargs):
                if s.service.import_export.call_count==2:s.rows[0].date=1.9
                return [result]
            s.service.import_export.side_effect=run
        else:s.service.import_export.side_effect=[[result],[] if case=='repeat_count' else [other]]
    with pytest.raises(ValueError):persist(s)

@pytest.fixture
def modules(setup,monkeypatch):
    s=setup
    bravo=NS(_load_pt_config=Mock(return_value=s.mapping),pro_request_scope=contextlib.nullcontext,
        _load_pros=Mock(return_value=s.frame),_REDCAP_SNAPSHOT_KIND='reports',_REDCAP_SNAPSHOT_RULE_VERSION='1',
        _pro_table_digest=lambda df:'digest',PRO_STORE_KEY_ATTR='provenance',_SHARED_CACHE_DIR_OVERRIDE=None,
        _cache_store=NS(product_key=Mock(return_value='key'),load=Mock(return_value=s.frame.copy())))
    s.frame.attrs['provenance']='key'
    monkeypatch.setitem(sys.modules,'django.db',NS(transaction=s.tx))
    monkeypatch.setitem(sys.modules,'Server',NS(models=s.models))
    monkeypatch.setitem(sys.modules,'modules.Biomarkers',NS(bravo_service=bravo))
    monkeypatch.setitem(sys.modules,'modules.SurveyForms',NS(RedcapImport=s.parser,RedcapImportService=s.service))
    monkeypatch.delenv('BRAVO_REDCAP_PASS_DIR',raising=False)
    s.bravo=bravo
    return s

def test_redcap_canonical_fresh_provenance(modules):
    assert m.redcap(modules.person)['records']==2

@pytest.mark.parametrize('case',['pass','mapping','wrong_person','none','empty','key','snapshot','changed'])
def test_redcap_freshness_failures(modules,monkeypatch,case):
    s=modules
    if case=='pass':monkeypatch.setenv('BRAVO_REDCAP_PASS_DIR','synthetic')
    if case=='mapping':s.bravo._load_pt_config.return_value=None
    if case=='wrong_person':s.mapping['pt']='Other'
    if case=='none':s.bravo._load_pros.return_value=None
    if case=='empty':s.bravo._load_pros.return_value=s.frame.iloc[:0]
    if case=='key':s.frame.attrs.clear()
    if case=='snapshot':s.bravo._cache_store.load.return_value=None
    if case=='changed':s.bravo._cache_store.load.return_value=s.frame.assign(nrs=5.)
    with pytest.raises((ValueError,AssertionError)):m.redcap(s.person)
    assert not s.service.import_export.called

def test_oura_requires_explicit_existing_managed_device(modules,monkeypatch):
    s=modules;device=NS(auth={'managed_token_file':True})
    s.models.OuraRingDevice=NS(objects=Mock());s.models.OuraRingDevice.objects.filter.return_value=[device]
    manager=NS(refreshOuraRingData=Mock(return_value={'counts':{'Sleep':2},'unchanged':True}))
    monkeypatch.setitem(sys.modules,'modules.OURA',NS(DataManager=manager))
    assert m.oura(s.person)=={'counts':{'Sleep':2},'unchanged':True}
    for devices in ([],[device,device],[NS(auth={})]):
        s.models.OuraRingDevice.objects.filter.return_value=devices
        with pytest.raises(ValueError):m.oura(s.person)
    s.models.OuraRingDevice.objects.filter.return_value=[device]
    for counts in (None,{'Sleep':-1},{'Sleep':True}):
        manager.refreshOuraRingData.return_value={'counts':counts}
        with pytest.raises(ValueError):m.oura(s.person)

def test_stage_disabled_and_independent_receipts(tmp_path,setup):
    tmp_path.chmod(0o700)
    cfg={'providers':{'receipts':str(tmp_path)},'runtime_revision':'r'}
    funcs={'redcap':Mock(return_value={'records':2}),'oura':Mock(side_effect=RuntimeError('secret'))}
    assert m.run_stages(cfg,setup.person,funcs)=={'failed':False,'redcap':{'status':'disabled'},'oura':{'status':'disabled'}}
    assert not funcs['redcap'].called and not funcs['oura'].called
    cfg['providers'].update(redcap_enabled=True,oura_enabled=True)
    result=m.run_stages(cfg,setup.person,funcs)
    assert result['failed'] is True and result['redcap']['records']==2 and result['oura']=={'status':'failed'}
    files=list(tmp_path.glob('*.json'));assert len(files)==2
    assert all('secret' not in p.read_text() for p in files)
    cfg['providers']['oura_enabled']='true'
    with pytest.raises(ValueError):m.run_stages(cfg,setup.person,funcs)

def test_runtime_binding(modules,monkeypatch):
    s=modules
    monkeypatch.setitem(sys.modules,'django',NS(setup=Mock()))
    monkeypatch.setitem(sys.modules,'django.conf',NS(settings=NS(DATABASES={'default':{'NAME':'db','USER':'user'}})))
    monkeypatch.setenv('BRAVO_BUILD_REVISION','r')
    cfg={'database_name':'db','database_user':'user','runtime_revision':'r','target_participant_uid':s.person.uid,'target_institute_uid':s.person.institute_id,'participant_name':s.person.name,'source_participant_uid':'d'*32}
    s.models.Participant.objects.get.return_value=s.person
    monkeypatch.setattr(m,'run_stages',Mock(return_value={'failed':False}))
    assert m.refresh_target(cfg)=={'failed':False}
    cfg['source_participant_uid']=s.person.uid
    with pytest.raises(ValueError):m.refresh_target(cfg)
    cfg['database_name']='wrong'
    with pytest.raises(ValueError):m.refresh_target(cfg)
