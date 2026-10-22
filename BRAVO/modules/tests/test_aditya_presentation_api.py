"""Endpoint contract/authorization checks with synthetic service doubles only."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest
from django.conf import settings

if not settings.configured:
    settings.configure(USE_I18N=False,DEBUG=True, SECRET_KEY="synthetic-only", REST_FRAMEWORK={"UNAUTHENTICATED_USER":None,"DEFAULT_AUTHENTICATION_CLASSES":[]}, INSTALLED_APPS=[])

from rest_framework.test import APIRequestFactory, force_authenticate


@pytest.fixture
def api(monkeypatch):
    root=Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(root))
    import modules
    from modules.Biomarkers.routines import availability
    database=ModuleType("modules.Database")
    database.checkAccessPermission=lambda *a,**k: True
    monkeypatch.setitem(sys.modules,"modules.Database",database)
    monkeypatch.setattr(modules,"Database",database,raising=False)
    path=root/"Server"/"APIs"/"AdityaPresentation.py"
    spec=importlib.util.spec_from_file_location("aditya_api_under_test",path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._test_stim_series = availability.stim_series
    module._actual_home_revision = module._home_revision
    module._actual_timeline_revision = module._timeline_revision
    module._actual_program_comparisons = module._program_comparisons
    module._actual_program_revision = module._program_revision
    module._actual_program_period_start = module._program_period_start
    monkeypatch.setattr(module,"_home_revision",lambda *args:"synthetic-revision")
    monkeypatch.setattr(module,"_timeline_revision",lambda *args:"a"*64)
    monkeypatch.setattr(module,"_program_revision",lambda *args: ["synthetic-program-inputs"])
    monkeypatch.setattr(module,"_program_comparisons",lambda *args: {"available":False,"metrics":[]})
    monkeypatch.setattr(module,"_program_period_start",lambda *args: None)
    return module


def call(cls,data,authenticated=True):
    request=APIRequestFactory().post("/api/presentation",data,format="json")
    if authenticated:
        force_authenticate(request,user=SimpleNamespace(is_authenticated=True,configuration={"ActiveStudy":"study-a"}))
    return cls.as_view()(request)


def test_authentication_and_study_scope(api,monkeypatch):
    assert call(api.QueryRedcapTimeline,{"ParticipantId":"p"},False).status_code in (401,403)
    seen=[]
    monkeypatch.setattr(api.Database,"checkAccessPermission",lambda user,uid,**kw: seen.append((uid,kw)) or False)
    monkeypatch.setattr(api,"_pain",lambda *a: pytest.fail("denied access must not read data"))
    assert call(api.QueryRedcapTimeline,{"ParticipantId":"p"}).status_code == 403
    assert seen == [("p",{"study_uid":"study-a"})]


@pytest.mark.parametrize("data",[{},[],{"ParticipantId":None},{"ParticipantId":5},{"ParticipantId":" "},{"ParticipantId":"p","ProcessedPRO":[]},{"ParticipantId":"p","ActiveStudy":"other"},{"ParticipantId":"p","IncludeClinicSheetRatings":False},{"ParticipantId":"p","program_mode_evidence":[]}])
def test_malformed_and_scientific_override_rejected(api,data):
    assert call(api.QueryRedcapTimeline,data).status_code == 400


@pytest.mark.parametrize("data",[{"ParticipantId":"p","window":"bad"},{"ParticipantId":"p","window":"custom"},{"ParticipantId":"p","window":"custom","start_date":"bad","end_date":"bad"}])
def test_bad_window(api,data):
    assert call(api.QueryHomeNeuralTimeline,data).status_code == 400


@pytest.mark.parametrize("kind,klass,helper",[("pain","QueryRedcapTimeline","_pain"),("home","QueryHomeNeuralTimeline","_home"),("oura","QueryOuraTimeline","_oura")])
def test_routes_real_payload_and_operational_failure(api,monkeypatch,kind,klass,helper):
    monkeypatch.setattr(api.presentation,"read_context",lambda uid:{"revision":"synthetic"})
    seen=[]
    monkeypatch.setattr(api,helper,lambda *args: seen.append(args) or {"message":"canonical result"})
    response=call(getattr(api,klass),{"ParticipantId":"p"})
    assert response.status_code==200
    assert response.data==({"message":"canonical result"} if kind=="home" else {"message":"canonical result","revision":"a"*64})
    assert seen[0][0]=="p"
    def fail(*args): raise OSError("private/local/source/path")
    monkeypatch.setattr(api,helper,fail)
    response=call(getattr(api,klass),{"ParticipantId":"p"})
    assert response.status_code==503
    assert "private" not in str(response.data)


def test_service_wiring_is_canonical_readonly(api,monkeypatch):
    import modules
    from modules.Biomarkers.routines import availability
    models=SimpleNamespace(Participant=SimpleNamespace(find=lambda **k:SimpleNamespace(uid=k["uid"])),SourceFile=SimpleNamespace(find_all=lambda **k:["source"]),
        ElectricalTherapy=SimpleNamespace(find_all=lambda **k:[SimpleNamespace(get_info=lambda:{"Date":100,"Id":"snapshot"})]))
    server=ModuleType("Server"); server.models=models
    monkeypatch.setitem(sys.modules,"Server",server)
    biomarkers=ModuleType("modules.Biomarkers")
    service=SimpleNamespace(_load_pt_config=lambda *a:{"pt":"synthetic-record"},pain_scores_for_participant=lambda data,**kwargs:{"metrics":[]},_load_recordings=lambda *a:[],CHRONIC_TYPES=["MedtronicChronicBrainSense"])
    biomarkers.bravo_service=service
    monkeypatch.setitem(sys.modules,"modules.Biomarkers",biomarkers)
    therapy=SimpleNamespace(therapy_from_data_start=lambda snapshots,changes,start:(snapshots,changes))
    monkeypatch.setattr(modules,"Therapy",therapy,raising=False)
    decode=ModuleType("modules.DecodeCommon")
    decode.data_start=SimpleNamespace(data_start_s=lambda participant:100)
    decode.representation=SimpleNamespace(native_lsb_by_channel=lambda *a:{},chronic_pair_keys=lambda *a:[])
    monkeypatch.setitem(sys.modules,"modules.DecodeCommon",decode)
    calls=[]
    def canonical_read(request, **kwargs):
        assert kwargs == {"discard_invalid_clinic":False}
        calls.append(request)
        # Duplicate REDCap points and a sheet observation at the same instant must stay distinct.
        points = [{"t_epoch":101,"v":4}, {"t_epoch":101,"v":4}]
        if request.get("IncludeClinicSheetRatings"):
            points += [{"t_epoch":101,"v":8,"sheet":True}]
        return {"metrics":[{"key":"nrs","label":"NRS (0–10)","range":[0,10],"points":points}]}
    service.pain_scores_for_participant=canonical_read
    records={"participant-a":"record-a","participant-b":"record-b"}
    service._load_pt_config=lambda participant,request:{"pt":records[participant.uid]}
    monkeypatch.setattr(api,"_stored_redcap",lambda participant:None)
    reports=[{"_pro_time_utc":"synthetic","nrs":4}]
    monkeypatch.setattr(api,"_processed_redcap",lambda snapshot:reports)
    for uid in records:
        result = api._pain(uid,{})
        assert result["stimulation"]["settings_observations"][0]["id"]=="snapshot"
        metric = result["metrics"][0]
        assert (metric["key"],metric["label"],metric["range"]) == ("nrs_intensity","NRS (0–10)",[0,10])
        assert [(p["time"],p["value"],p["source"]) for p in metric["points"]] == [(101,4,"REDCap"),(101,4,"REDCap")]
        assert result["visits"]["available"] is True
        assert [(p["time"],p["value"],p["source"]) for p in result["visits"]["metrics"]["nrs_intensity"]] == [(101,8,"clinic-sheet")]
    assert calls == [{"ParticipantId":"participant-a","RedcapRecordId":"record-a","IncludeClinicSheetRatings":True,"ProcessedPRO":reports},{"ParticipantId":"participant-b","RedcapRecordId":"record-b","IncludeClinicSheetRatings":True,"ProcessedPRO":reports}]
    reports.clear()
    assert "Stored REDCap surveys are unavailable" in api._pain("participant-a",{})["message"]
    for binding in (None,{}, {"pt":None},{"pt":"record-a","record_id":"record-b"}):
        service._load_pt_config=lambda participant,request,b=binding:b
        assert "no surveys were requested" in api._pain("p",{})["message"]
    assert len(calls)==2
    assert api._home("p",{},{} )["status"]=="unavailable"
    assert api._home("p",{"home_intervals":[{"start":1,"end":2}]},{"window":"past28"})["status"]=="available"
    oura=ModuleType("modules.OURA"); oura.DataManager=SimpleNamespace(loadOuraRingData=lambda participant:{})
    monkeypatch.setitem(sys.modules,"modules.OURA",oura)
    assert api._oura("p")["defaults"]==[]


def test_access_service_failure_is_closed(api,monkeypatch):
    def fail(*args,**kwargs): raise OSError("private path")
    monkeypatch.setattr(api.Database,"checkAccessPermission",fail)
    monkeypatch.setattr(api,"_pain",lambda *a: pytest.fail("must not read if authorization is unavailable"))
    response=call(api.QueryRedcapTimeline,{"ParticipantId":"p"})
    assert response.status_code==503 and "private" not in str(response.data)


@pytest.mark.parametrize("binding",[None,{},[],{"pt":None},{"pt":True},{"pt":[]},{"pt":" "},{"pt":"a","record_id":"b"}])
def test_unbound_redcap_rejected_before_fetch(api,binding):
    assert api._bound_record(binding) is None


@pytest.mark.parametrize("binding,expected",[({"pt":"a"},"a"),({"record_id":123},"123"),({"pt":"a","record_id":"a"},"a")])
def test_only_explicit_consistent_redcap_binding(api,binding,expected):
    assert api._bound_record(binding)==expected


@pytest.mark.parametrize('field', ['neural_observation_scope', 'observation_scope', 'home_intervals', 'visit_days', 'home_continuity'])
def test_observational_scope_cannot_be_selected_by_client(api, monkeypatch, field):
    monkeypatch.setattr(api.presentation, 'read_context', lambda *args: pytest.fail('unsupported client scope must fail before context read'))
    response = call(api.QueryHomeNeuralTimeline, {'ParticipantId':'p', field: {'start':1,'end':2,'description':'injected'}})
    assert response.status_code == 400


def test_server_observations_use_one_canonical_read_and_keep_home_contract(api, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    low = datetime(2026, 10, 8, tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
    context = {'neural_scope':{'coverage_start':low-86400,'coverage_end':low,'description':'Reviewed'},
        'home_intervals':[{'start':low-86400,'end':low}], 'visit_days':['2026-10-07'],
        'neural_observation_scope':{'start':low,'end':low+86400*20,'description':'Observations only'}}
    rows=[{'ChannelNames':['LEFT synthetic'],'Time':[low+1200], 'Data':[[0,0]]}]
    calls=[]
    service=SimpleNamespace(CHRONIC_TYPES=['native-chronic'], _load_recordings=lambda *args: calls.append(args) or rows)
    biomarkers=ModuleType('modules.Biomarkers'); biomarkers.bravo_service=service
    monkeypatch.setitem(sys.modules,'modules.Biomarkers',biomarkers)
    representation=SimpleNamespace(native_lsb_by_channel=lambda *args:{'LEFT_0-2':{'t':[low+1200],'y':[0],'center_hz':[20]}},
        chronic_pair_keys=lambda *args:['LEFT_0-2'])
    decode=ModuleType('modules.DecodeCommon'); decode.representation=representation
    monkeypatch.setitem(sys.modules,'modules.DecodeCommon',decode)
    monkeypatch.setattr(api.presentation,'read_context',lambda uid:context)
    data={'ParticipantId':'p','window':'custom','start_date':'2026-10-07','end_date':'2026-10-08'}
    result=call(api.QueryHomeNeuralTimeline,data)
    assert result.status_code==200 and calls==[('p',['native-chronic'])]
    historical=api.presentation.home_timeline(data,context,rows,representation.native_lsb_by_channel,representation.chronic_pair_keys,stim_series=api._test_stim_series)
    assert {key:result.data[key] for key in historical}==historical
    assert result.data['observation_windows'][0]['panels'][0]['segments'][0]['points'][0]['power']==0
    context['neural_observation_scope']['start']=low-1
    calls.clear()
    assert call(api.QueryHomeNeuralTimeline,data).status_code==503 and calls==[]
    monkeypatch.setattr(api.Database,'checkAccessPermission',lambda *args,**kwargs:False)
    monkeypatch.setattr(api.presentation,'read_context',lambda *args:pytest.fail('denied access must not inspect server scope'))
    assert call(api.QueryHomeNeuralTimeline,data).status_code==403 and calls==[]


def test_revision_request_is_read_only_authorized_and_no_decode(api,monkeypatch):
    service=SimpleNamespace(CHRONIC_TYPES=['chronic'],_load_recordings=lambda *args:pytest.fail('revision must not decode'))
    bio=ModuleType('modules.Biomarkers');bio.bravo_service=service
    monkeypatch.setitem(sys.modules,'modules.Biomarkers',bio)
    decode=ModuleType('modules.DecodeCommon');decode.representation=SimpleNamespace()
    monkeypatch.setitem(sys.modules,'modules.DecodeCommon',decode)
    monkeypatch.setattr(api.presentation,'read_context',lambda uid:{})
    result=call(api.QueryHomeNeuralTimeline,{'ParticipantId':'p','RequestType':'Revision','window':'past28'})
    assert result.status_code==200 and result.data=={'revision':'synthetic-revision'}
    assert call(api.QueryHomeNeuralTimeline,{'ParticipantId':'p','RequestType':'other'}).status_code==400
    monkeypatch.setattr(api.Database,'checkAccessPermission',lambda *a,**k:False)
    assert call(api.QueryHomeNeuralTimeline,{'ParticipantId':'p','RequestType':'Revision'}).status_code==403


def test_revision_hash_covers_same_count_mutations_context_calendar_and_windows(api,monkeypatch):
    import copy
    rows=[SimpleNamespace(uid='private-uid',hashed='first',type='chronic',pointer='/private/path',metadata={'ContactSchedule':[1]})]
    sources=[SimpleNamespace(uid='source',hashed='source-hash',metadata={'SessionEndTimestamp':200})];person=object()
    models=SimpleNamespace(Participant=SimpleNamespace(find=lambda **kw:person),
        SourceFile=SimpleNamespace(find_all=lambda **kw:sources),Recording=SimpleNamespace(find_all=lambda **kw:rows))
    server=ModuleType('Server');server.models=models;monkeypatch.setitem(sys.modules,'Server',server)
    service=SimpleNamespace(CHRONIC_TYPES=['chronic'],_recording_set_identity=lambda uid:('implant',1))
    bio=ModuleType('modules.Biomarkers');bio.bravo_service=service;monkeypatch.setitem(sys.modules,'modules.Biomarkers',bio)
    monkeypatch.setattr(api.presentation,'date_windows',lambda request,context:request)
    get=lambda context={},request={},calendar=None:api._actual_home_revision('p',context,request,calendar)
    baseline=get();assert len(baseline)==64 and 'private' not in baseline
    for attr,new in [('hashed','second'),('metadata',{'ContactSchedule':[2]}),('metadata',{'ScheduleFlagged':[[1,None]]}),('metadata',{'ScheduleNoRecord':[[1,2]]}),('uid','replacement'),('pointer','/other')]:
        old=getattr(rows[0],attr);setattr(rows[0],attr,new);assert get()!=baseline;setattr(rows[0],attr,old)
    assert get(context={'revision':'changed'})!=baseline
    assert get(request={'start':2})!=baseline
    assert get(calendar={'receipt':'new'})!=baseline
    sources[0].metadata['SessionEndTimestamp']=201
    assert get()!=baseline
    sources[0].metadata['SessionEndTimestamp']=200
    service._recording_set_identity=lambda uid:('implant',2)
    assert get()!=baseline
    previous=get()
    monkeypatch.setattr(api.presentation,'VERSION','synthetic-next-presentation')
    assert get()!=previous
    models.Participant.find=lambda **kw:None
    with pytest.raises(ValueError):get()


def install_clinic_double(api,monkeypatch,tmp_path):
    import pandas as pd
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    day=datetime(2026,1,1,tzinfo=ZoneInfo('America/Los_Angeles'))
    payload={'manifest':pd.DataFrame([{'file':'01_01_26.xlsx','setting':'clinic','error':None}]),
             'steps':pd.DataFrame([{'file':'01_01_26.xlsx','setting':'clinic','visit_date_ts':day,'sha256':'a'*64}])}
    stamp={'kind':'clinic_pain_steps','participant_uid':'p','signature_key':'a'*40,'written_utc':'2026-01-02T00:00:00+00:00'}
    receipt={'format':1,'target_participant_uid':'p','canonical_store_key':'clinic_pain_steps/p/'+'a'*40,
             'repeat_wrote':False,'workbook_files':1,'parsed_steps':1}
    clinic=SimpleNamespace(CLINIC_PAIN_KIND='clinic_pain_steps',_cache_store=SimpleNamespace(load_newest=lambda *args,**kwargs:(payload,stamp)),
        _visit_date_from_title=lambda name:day,_infer_setting=lambda name:'clinic')
    optimizer=ModuleType('modules.StimOptimizer');optimizer.clinic_pain=clinic
    monkeypatch.setitem(sys.modules,'modules.StimOptimizer',optimizer)
    monkeypatch.setenv('DATASERVER_PATH',str(tmp_path))
    root=tmp_path/'daily-clinic-receipts';root.mkdir()
    path=root/'accepted.json';path.write_text(json.dumps(receipt))
    return clinic,payload,stamp,receipt,path


def test_clinic_reader_exact_accepted_product_and_private_failure_messages(api,monkeypatch,tmp_path):
    import json
    clinic,payload,stamp,receipt,path=install_clinic_double(api,monkeypatch,tmp_path)
    result,identity=api._clinic_snapshot('p')
    assert result['status']=='stored_snapshot' and result['days']==['2026-01-01']
    assert 'private' not in str(result) and identity['receipt']==receipt
    receipt['target_participant_uid']='other';path.write_text(json.dumps(receipt))
    assert api._clinic_snapshot('p')[0]['status']=='unavailable'
    receipt['target_participant_uid']='p';receipt['canonical_store_key']='different';path.write_text(json.dumps(receipt))
    assert api._clinic_snapshot('p')[0]['status']=='unavailable'
    path.write_text('{bad')
    assert api._clinic_snapshot('p')==({'status':'invalid'},None)
    clinic._cache_store.load_newest=lambda *args,**kwargs:(None,None)
    assert api._clinic_snapshot('p')==({'status':'unavailable'},None)


@pytest.mark.parametrize('mode',['symlink','directory','large','many','missing_env','invalid_calendar'])
def test_clinic_reader_bounded_fail_closed(api,monkeypatch,tmp_path,mode):
    clinic,payload,stamp,receipt,path=install_clinic_double(api,monkeypatch,tmp_path)
    if mode=='symlink':path.unlink();path.symlink_to(tmp_path/'missing')
    if mode=='directory':path.unlink();path.mkdir()
    if mode=='large':path.write_bytes(b'x'*(1024*1024+1))
    if mode=='many':monkeypatch.setattr(api.Path,'glob',lambda *args:[path]*10001)
    if mode=='missing_env':monkeypatch.delenv('DATASERVER_PATH')
    if mode=='invalid_calendar':payload['manifest'].loc[0,'error']='invalid'
    assert api._clinic_snapshot('p')==({'status':'invalid'},None)


def test_automatic_home_calls_calendar_once_revision_and_data_are_separate(api,monkeypatch):
    context={'neural_scope':{'coverage_start':1,'coverage_end':2,'description':'Reviewed'},
        'home_intervals':[{'start':1,'end':2}], 'neural_observation_scope':{'mode':'automatic','description':'Unverified'}}
    seen=[]
    monkeypatch.setattr(api,'_clinic_snapshot',lambda uid:seen.append(uid) or ({'status':'unavailable'},'identity'))
    bio=ModuleType('modules.Biomarkers');bio.bravo_service=SimpleNamespace(CHRONIC_TYPES=['chronic'],_load_recordings=lambda *a:[])
    monkeypatch.setitem(sys.modules,'modules.Biomarkers',bio)
    decode=ModuleType('modules.DecodeCommon');decode.representation=SimpleNamespace(native_lsb_by_channel=None,chronic_pair_keys=None)
    monkeypatch.setitem(sys.modules,'modules.DecodeCommon',decode)
    result=api._home('p',context,{'window':'past28'})
    assert seen==['p','p'] and result['observation_windows']==[] and result['revision']=='synthetic-revision'


def test_calendar_change_during_decode_withholds_observations_only_and_keeps_preload_token(api,monkeypatch):
    from datetime import datetime
    low=datetime(2026,1,5,tzinfo=api.presentation.PACIFIC).timestamp()
    context={'neural_scope':{'coverage_start':low-86400,'coverage_end':low,'description':'Reviewed'},
        'home_intervals':[{'start':low-86400,'end':low}],
        'neural_observation_scope':{'mode':'automatic','description':'Unverified'}}
    calendar={'status':'stored_snapshot','days':[],'clinic_days':[]}
    identity={'key':'first'}
    reads=[]
    def snapshot(uid):
        reads.append(uid)
        return calendar, dict(identity)
    monkeypatch.setattr(api,'_clinic_snapshot',snapshot)
    rows=[{'ChannelNames':['LEFT synthetic'],'Time':[low-1200,low+1200],'Data':[[3,0],[5,0]]}]
    def load(*args):
        identity['key']='changed'
        return rows
    bio=ModuleType('modules.Biomarkers');bio.bravo_service=SimpleNamespace(CHRONIC_TYPES=['chronic'],_load_recordings=load)
    monkeypatch.setitem(sys.modules,'modules.Biomarkers',bio)
    representation=SimpleNamespace(native_lsb_by_channel=lambda *args:{'LEFT_0-2':{'t':rows[0]['Time'],'y':[3,5],'center_hz':[20,20]}},
        chronic_pair_keys=lambda *args:['LEFT_0-2','LEFT_0-2'])
    decode=ModuleType('modules.DecodeCommon');decode.representation=representation
    monkeypatch.setitem(sys.modules,'modules.DecodeCommon',decode)
    monkeypatch.setattr(api,'_home_revision',lambda uid,context,request,identity:identity[1]['key'])
    request={'window':'custom','start_date':'2026-01-04','end_date':'2026-01-05'}
    result=api._home('p',context,request)
    historical=api.presentation.home_timeline(request,context,rows,representation.native_lsb_by_channel,representation.chronic_pair_keys,stim_series=api._test_stim_series)
    assert {key:result[key] for key in historical}==historical
    assert result['observation_windows']==[] and result['revision']=='first'
    assert 'changed while loading' in result['observation_provenance']['message']
    assert reads==['p','p']
    assert api._home('p',context,{**request,'RequestType':'Revision'})=={'revision':'changed'}


@pytest.mark.parametrize('klass,helper', [('QueryRedcapTimeline','_pain'),('QueryOuraTimeline','_oura')])
def test_other_revision_requests_are_scoped_readonly_and_strict(api, monkeypatch, klass, helper):
    monkeypatch.setattr(api.presentation,'read_context',lambda uid:{'revision':'context'})
    monkeypatch.setattr(api,helper,lambda *args:pytest.fail('revision must not read or fetch full data'))
    seen=[]
    monkeypatch.setattr(api,'_timeline_revision',lambda *args:seen.append(args) or 'b'*64)
    view=getattr(api,klass)
    request={'ParticipantId':'p','RequestType':'Revision'}
    assert call(view,request,False).status_code in (401,403)
    result=call(view,request)
    assert result.status_code==200 and result.data=={'revision':'b'*64}
    assert seen==[('pain' if helper=='_pain' else 'oura','p',{'revision':'context'} if helper=='_pain' else {})]
    for value in ('revision','Full','',None,1,[],{}):
        assert call(view,dict(request,RequestType=value)).status_code==400
    for field in ('window','ProcessedPRO','RedcapRecordId','filesystem','ActiveStudy'):
        assert call(view,dict(request,**{field:'untrusted'})).status_code==400
    monkeypatch.setattr(api.Database,'checkAccessPermission',lambda *args,**kwargs:False)
    assert call(view,request).status_code==403 and len(seen)==1


@pytest.mark.parametrize('klass,helper', [('QueryRedcapTimeline','_pain'),('QueryOuraTimeline','_oura')])
def test_full_revision_is_preload_and_concurrent_source_update_stays_detectable(api,monkeypatch,klass,helper):
    monkeypatch.setattr(api.presentation,'read_context',lambda uid:{})
    current=['a'*64]
    monkeypatch.setattr(api,'_timeline_revision',lambda *args:current[0])
    def load(*args):
        current[0]='b'*64
        return {'values':['stored-data']}
    monkeypatch.setattr(api,helper,load)
    view=getattr(api,klass)
    result=call(view,{'ParticipantId':'p'})
    if helper == '_pain':
        assert result.status_code == 503  # A mixed comparison snapshot is withheld.
    else:
        assert result.status_code==200 and result.data['revision']=='a'*64
    assert call(view,{'ParticipantId':'p','RequestType':'Revision'}).data['revision']=='b'*64
    def fail(*args):raise ValueError('/private/identity')
    monkeypatch.setattr(api,'_timeline_revision',fail)
    assert call(view,{'ParticipantId':'p','RequestType':'Revision'}).status_code==503


def install_stored_surveys(monkeypatch):
    import pandas as pd
    from modules.SurveyForms import RedcapImport
    # Exact importer: duplicate instants, missingness, measured zero, fractional UTC.
    frame=pd.DataFrame({'_pro_time_utc':pd.to_datetime(['2026-03-08T09:59:59.125','2026-03-08T10:00:00.000','2026-03-08T10:00:00.000']),
                        'nrs':[0.,None,7.], 'mpq_sum':[52.,41.,None]})
    parsed,=RedcapImport.parse_export(frame,instrument_name='Daily REDCap p',layout='wide',
        timestamp_col='_pro_time_utc',metric_cols=['nrs','mpq_sum'])
    person=SimpleNamespace(uid='p',institute=object())
    form=SimpleNamespace(uid='form',record_version=1,record=parsed['FieldMapping'])
    rows=[('uid-'+str(i),row['Date'],row['Result']) for i,row in enumerate(parsed['records'])]
    seen=[]
    def find_form(**kw):seen.append(('form',kw));return form
    def filter_rows(**kw):
        seen.append(('rows',kw));return SimpleNamespace(values_list=lambda *args:list(rows))
    models=SimpleNamespace(Participant=SimpleNamespace(find=lambda **kw:person),
        ScaleForms=SimpleNamespace(find=find_form),ScaleRecord=SimpleNamespace(objects=SimpleNamespace(filter=filter_rows)),
        ParticipantLinkRel=SimpleNamespace(include=lambda **kw:True))
    server=ModuleType('Server');server.models=models;monkeypatch.setitem(sys.modules,'Server',server)
    return person,form,rows,models,seen,frame


def test_stored_surveys_reverse_actual_importer_losslessly_and_scope(api,monkeypatch):
    import pandas as pd
    from pandas.testing import assert_frame_equal
    person,form,rows,models,seen,frame=install_stored_surveys(monkeypatch)
    restored=pd.DataFrame(api._processed_redcap(api._stored_redcap(person)))[frame.columns]
    assert_frame_equal(restored,frame,check_exact=True)
    assert seen==[('form',{'institute':person.institute,'name':'Daily REDCap p','record_type':'Redcap CSV Import'}),
                  ('rows',{'source':form,'participant':person})]
    rows.clear();assert api._processed_redcap(api._stored_redcap(person))==[]
    models.ParticipantLinkRel.include=lambda **kw:False
    assert api._stored_redcap(person) is None
    models.ScaleForms.find=lambda **kw:None
    assert api._stored_redcap(person) is None
    assert api._processed_redcap(None)==[]


@pytest.mark.parametrize('change', [
    lambda s:s.update(mapping={}),lambda s:s.update(mapping=[]),
    lambda s:s['mapping'][0].update(questions={}),lambda s:s['mapping'][0].update(questions=[]),
    lambda s:s['mapping'][0]['questions'][-1].update(variableName='local-time'),
    lambda s:s['mapping'][0]['questions'][-1].update(text='not-time'),
    lambda s:s['mapping'][0]['questions'][0].update(variableName=None),
    lambda s:s['mapping'][0]['questions'][0].update(variableName=''),
    lambda s:s['mapping'][0]['questions'][0].update(variableName='_pro_time_utc'),
    lambda s:s['mapping'][0]['questions'][0].update(variableName='mpq_sum'),
    lambda s:s['mapping'][0]['questions'][0].update(type='text'),
    lambda s:s['rows'].__setitem__(0,('x',True,[[0,1,'x']])),
    lambda s:s['rows'].__setitem__(0,('x',float('nan'),[[0,1,'x']])),
    lambda s:s['rows'].__setitem__(0,('x',1,{})),lambda s:s['rows'].__setitem__(0,('x',1,[])),
    lambda s:s['rows'].__setitem__(0,('x',1,[{}])),lambda s:s['rows'].__setitem__(0,('x',1,[[0,1]])),
    lambda s:s['rows'].__setitem__(0,('x',1,[[True,1,'x']])),
    lambda s:s['rows'].__setitem__(0,('x',1,[[float('inf'),1,'x']])),
])
def test_invalid_stored_redcap_fails_closed(api,monkeypatch,change):
    import copy
    person,*_=install_stored_surveys(monkeypatch)
    snapshot=copy.deepcopy(api._stored_redcap(person));change(snapshot)
    with pytest.raises(ValueError):api._processed_redcap(snapshot)


def test_stored_revision_covers_exact_corrections_binding_clinic_therapy_and_oura(api,monkeypatch):
    import copy
    person,form,rows,models,seen,frame=install_stored_surveys(monkeypatch)
    source=SimpleNamespace(uid='private-source',hashed='a',pointer='/private/path')
    models.SourceFile=SimpleNamespace(find=lambda **kw:source,find_all=lambda **kw:['source'])
    therapy={'Id':'t','StimulationSettings':[{'Amplitude':1.}]}
    models.ElectricalTherapy=SimpleNamespace(find_all=lambda **kw:[SimpleNamespace(get_info=lambda:therapy)])
    stamps={'redcap':{'signature_key':'saved-A'},'clinic':{'signature_key':'clinic-A'}}
    binding={'pt':'record-p'};field_map={'metric_labels':{'nrs':'raw-nrs'}};start=[100.]
    service=SimpleNamespace(_load_pt_config=lambda *args:binding,_resolve_field_map=lambda *args:field_map,
        _cache_store=SimpleNamespace(newest_stamp=lambda kind,uid,**kw:stamps[kind]),
        _SHARED_CACHE_DIR_OVERRIDE=None,_REDCAP_SNAPSHOT_KIND='redcap',CLINIC_SHEET_STEPS_KIND='clinic')
    bio=ModuleType('modules.Biomarkers');bio.bravo_service=service;monkeypatch.setitem(sys.modules,'modules.Biomarkers',bio)
    decode=ModuleType('modules.DecodeCommon');decode.data_start=SimpleNamespace(data_start_s=lambda person:start[0])
    monkeypatch.setitem(sys.modules,'modules.DecodeCommon',decode)
    get=lambda kind='pain',uid='p',context={}:api._actual_timeline_revision(kind,uid,context)
    original=get();assert len(original)==64 and 'private' not in original
    rows.reverse();assert get()==original
    # A -> B -> A -> B with unchanged snapshot stamp and row count.
    before=copy.deepcopy(rows)
    rows[0][2][0][0]=9;changed=get();assert changed!=original
    rows[:]=copy.deepcopy(before);assert get()==original
    rows[0][2][0][0]=9;assert get()==changed
    rows[:]=copy.deepcopy(before)
    for target,key,value in [(binding,'pt','record-corrected'),(field_map,'metric_labels',{'vas':'raw-vas'}),
                             (therapy,'StimulationSettings',[{'Amplitude':2.}]),(stamps,'redcap',{'signature_key':'saved-B'}),
                             (stamps,'clinic',{'signature_key':'clinic-B'})]:
        old=target[key];target[key]=value;assert get()!=original;target[key]=old
    form.record_version=2;assert get()!=original;form.record_version=1
    form.record[0]['questions'][0]['text']='Corrected label';assert get()!=original
    form.record[0]['questions'][0]['text']='NRS (0-10)';assert get()==original
    start[0]=200.;assert get()!=original;start[0]=100.
    assert get(context={'revision':'new'})!=original and get(uid='other')!=original
    original_oura=get('oura')
    adapter_version = api.presentation.VERSION
    monkeypatch.setattr(api.presentation, 'VERSION', adapter_version + '-new-scoring')
    assert get() != original and get('oura') != original_oura
    monkeypatch.setattr(api.presentation, 'VERSION', adapter_version)
    assert get() == original and get('oura') == original_oura
    for attr in ('uid','hashed','pointer'):
        old=getattr(source,attr);setattr(source,attr,'changed');assert get('oura')!=original_oura;setattr(source,attr,old)
    models.SourceFile.find=lambda **kw:None
    assert get('oura')!=original_oura
    models.Participant.find=lambda **kw:None
    with pytest.raises(ValueError):get('oura')


@pytest.mark.parametrize('standard_mapping', [False, True])
def test_full_stored_surveys_use_real_canonical_formatter_without_network_or_writes(api,monkeypatch,standard_mapping,tmp_path):
    import modules
    from modules.Biomarkers.routines import availability
    import modules.Biomarkers as biomarkers
    from unittest.mock import Mock
    person,form,rows,models,seen,frame=install_stored_surveys(monkeypatch)
    from modules.SurveyForms import RedcapImport, StandardMPQ
    if standard_mapping:
        frame['mpq_sen'] = [33., None, 2.]
        frame['mpq_aff'] = [12., 3., 1.]
        parsed, = RedcapImport.parse_export(frame,instrument_name='Daily REDCap p',layout='wide',
            timestamp_col='_pro_time_utc',metric_cols=['nrs','mpq_sum','mpq_sen','mpq_aff'])
        form.record = parsed['FieldMapping']
        rows[:] = [('uid-'+str(i),row['Date'],row['Result']) for i,row in enumerate(parsed['records'])]
    models.SourceFile=SimpleNamespace(find_all=lambda **kw:[])
    models.ElectricalTherapy=SimpleNamespace(find_all=lambda **kw:[])
    # Only database/runtime scaffolding is doubled; load the actual canonical
    # formatter, ProcessedPRO path and UTC conversion from the shipped module.
    helper=ModuleType('modules.HelperFunctions');helper.json_compliant_handler=lambda x:x
    monkeypatch.setitem(sys.modules,'modules.HelperFunctions',helper)
    for name in ('pipeline','adapter'):
        monkeypatch.setitem(sys.modules,'modules.Biomarkers.'+name,ModuleType(name))
    path=Path(__file__).parents[1]/'Biomarkers'/'bravo_service.py'
    spec=importlib.util.spec_from_file_location('modules.Biomarkers.presentation_service_under_test',path)
    service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
    monkeypatch.setattr(biomarkers,'bravo_service',service,raising=False)
    binding = {'pt':'p','metric_labels':{'nrs':'raw-nrs','mpq_sum':'raw-mpq'}}
    if standard_mapping:
        binding.update(instruments=['stage_1_daily_surveys_vasnrsmpq'],timestamp_label='date_time_s1_daily')
        binding['metric_labels'].update(mpq_sum='mpq_s1_daily',mpq_sen=list(StandardMPQ.SENSORY),mpq_aff=list(StandardMPQ.AFFECTIVE))
    monkeypatch.setattr(service,'_load_pt_config',lambda *args:binding)
    monkeypatch.setattr(service.redcap_client,'pull_redcap',Mock(side_effect=AssertionError('display must not fetch')))
    monkeypatch.setattr(service,'_snapshot_pain_reports',Mock(side_effect=AssertionError('display must not write')))
    from modules.CacheStore import ledger
    monkeypatch.setattr(ledger,'ENABLED',False)
    monkeypatch.setattr(service,'_SHARED_CACHE_DIR_OVERRIDE',str(tmp_path))
    service._cache_store.store(service.CLINIC_SHEET_STEPS_KIND,'p',('synthetic',),{'steps':[]},writer='synthetic',provenance=[],root=str(tmp_path))
    directory=Path(service._cache_store.kind_dir(service.CLINIC_SHEET_STEPS_KIND,create=False,root=str(tmp_path)))
    payload=next(path for path in directory.iterdir() if not path.name.endswith('.meta.json'))
    payload.write_bytes(b'corrupt-test-payload')
    before={path.name:path.read_bytes()for path in directory.iterdir()}
    discard=Mock(side_effect=AssertionError('canonical display cannot discard cache'))
    monkeypatch.setattr(service._cache_store,'_discard_entry',discard)
    monkeypatch.setattr(modules,'Therapy',SimpleNamespace(therapy_from_data_start=lambda a,b,c:(a,b)),raising=False)
    from modules.DecodeCommon import data_start
    monkeypatch.setattr(data_start,'data_start_s',lambda person:0.)
    result=api._pain('p',{})
    bykey={metric['key']:metric for metric in result['metrics']}
    times=[row[1] for row in rows]
    assert [(p['time'],p['value']) for p in bykey['nrs_intensity']['points']]==[(times[0],0.),(times[2],7.)]
    assert [(p['time'],p['value']) for p in bykey['mpq_sum']['points']]==[(times[0],52.),(times[1],41.)]
    assert bykey['mpq_sum']['range']==([0,54] if standard_mapping else [0,72])
    assert result['provenance']['standard_mpq']['mapping_verified'] == standard_mapping
    if standard_mapping:
        standard = bykey['mpq_standard_0_45']
        assert standard['range'] == [0,45]
        assert [(p['time'],p['value']) for p in standard['points']] == [(times[0],45.),(times[1],3.),(times[2],3.)]
        assert bykey['mpq_standard_sensory_0_33']['range'] == [0,33]
        assert bykey['mpq_standard_affective_0_12']['range'] == [0,12]
        assert [p['value'] for p in bykey['mpq_sen']['points']] == [33.,2.]
        assert [p['value'] for p in bykey['mpq_aff']['points']] == [12.,3.,1.]
    else:
        assert 'mpq_standard_0_45' not in bykey
    assert 'Stored REDCap surveys' in result['message']
    discard.assert_not_called()
    assert {path.name:path.read_bytes()for path in directory.iterdir()}==before
    # A same-count replacement is read immediately, without any cross-request memo.
    rows[0][2][0][0]=3.
    assert api._pain('p',{})['metrics'][0]['points'][0]['value']==3.
    rows.clear()
    assert api._pain('p',{})['metrics']==[]
    service.redcap_client.pull_redcap.assert_not_called()
    service._snapshot_pain_reports.assert_not_called()


def test_home_links_only_owned_original_sources_and_uses_canonical_batch_clock(api,monkeypatch):
    import copy
    import modules
    from modules.tests.test_aditya_neural_settings import report, segment
    source=SimpleNamespace(uid='source-a',hashed='hash',metadata={},device='device-a')
    person=SimpleNamespace(uid='person-a')
    reads=[]
    server=ModuleType('Server');server.models=SimpleNamespace(Participant=SimpleNamespace(find=lambda **kw:person),
        SourceFile=SimpleNamespace(find_all=lambda **kw:reads.append(('scope',kw)) or [source]))
    monkeypatch.setitem(sys.modules,'Server',server)
    rows=[{'SourceId':'source-a','RecordingId':'row-a','SourceSessionEnd':400,'ChannelNames':['LEFT a'],'Time':[150]}]
    bio=ModuleType('modules.Biomarkers');bio.bravo_service=SimpleNamespace(CHRONIC_TYPES=['chronic'],_load_recordings=lambda *args:rows)
    monkeypatch.setitem(sys.modules,'modules.Biomarkers',bio)
    decode=ModuleType('modules.DecodeCommon');decode.representation=SimpleNamespace(native_lsb_by_channel=None,chronic_pair_keys=None)
    monkeypatch.setitem(sys.modules,'modules.DecodeCommon',decode)
    curator=SimpleNamespace(clock_anchor_tables=lambda owner:reads.append(('anchors',owner)) or {'device-a':'canonical-table'},
        loadPerceptJSON=lambda original,table:reads.append(('raw',original,table)) or report())
    monkeypatch.setattr(modules,'DataCurator',curator,raising=False)
    timeline={'windows':[{'panels':[{'side':'left','segments':[segment()]}]}]}
    monkeypatch.setattr(api.presentation,'neural_timeline',lambda *args,**kwargs:copy.deepcopy(timeline))
    result=api._home('person-a',{'home_intervals':[{'start':1,'end':500}]},{'window':'past28'})
    assert reads==[('scope',{'owner':person}),('anchors',person),('raw',source,'canonical-table')]
    assert result['windows'][0]['panels'][0]['segments'][0]['settings_context']['source_ids']==['source-a']


def install_program_double(monkeypatch):
    import modules
    program = ModuleType('modules.AdityaProgramComparisons')
    program.POLICY_VERSION = 'synthetic-program-policy'
    program.prepare_source = lambda source: {'id':source['id'],'hash':source['hash'],'prepared':program.POLICY_VERSION}
    def build(surveys,metrics,sources,days,**kwargs):
        return {'available':kwargs['calendar_verified'], 'metrics':[dict(metric) for metric in metrics],
                'provenance':{},'inputs':{'surveys':surveys,'sources':sources,'days':days,**kwargs}}
    program.build_comparisons = build
    monkeypatch.setitem(sys.modules,'modules.AdityaProgramComparisons',program)
    monkeypatch.setattr(modules,'AdityaProgramComparisons',program,raising=False)
    return program


def test_program_envelope_keeps_duplicate_times_all_metrics_and_relief_direction(api,monkeypatch):
    from modules.SurveyForms import StandardMPQ
    install_program_double(monkeypatch)
    monkeypatch.setattr(api,'_clinic_snapshot',lambda uid:({'status':'stored_snapshot','days':['2026-01-02']},'receipt'))
    monkeypatch.setattr(api,'_program_inputs',lambda person:([],{},'source-identity'))
    monkeypatch.setattr(api,'_prepared_program_sources',lambda *args:[])
    keys=['nrs','vas','left_leg_vas','back_vas','relief','mpq_sum','mpq_sen','mpq_aff',
          *[m[0] for m in StandardMPQ.METRICS],'electrocuting','tingly']
    metrics=[{'key':key,'label':key,'range':[0,100],'points':[]} for key in keys]
    reports=[{key:0 for key in keys},{key:None for key in keys}]
    snapshot={'rows':[('first',101,[]),('second',101,[])]}
    result=api._actual_program_comparisons(SimpleNamespace(uid='p'),snapshot,reports,{'metrics':metrics},{'visit_days':['2026-01-01']})
    assert len(result['metrics'])==13
    assert [s['id'] for s in result['inputs']['surveys']]==['first','second']
    assert [s['time'] for s in result['inputs']['surveys']]==[101,101]
    assert result['inputs']['surveys'][0]['values']['nrs']==0
    assert result['inputs']['surveys'][1]['values']['nrs'] is None
    assert result['inputs']['preserved_testing_days']==['2026-01-01']
    assert result['inputs']['days']==['2026-01-02']
    assert next(m for m in result['metrics']if m['key']=='relief')['direction']=='higher'
    assert next(m for m in result['metrics']if m['key']=='nrs_intensity')['direction']=='lower'
    with pytest.raises(ValueError,match='correspondence'):
        api._actual_program_comparisons(SimpleNamespace(uid='p'),snapshot,reports[:1],{'metrics':metrics},{})


@pytest.mark.parametrize('status',['invalid','unavailable'])
def test_bad_program_calendar_never_decodes_sources_or_uses_stale_rankings(api,monkeypatch,status):
    install_program_double(monkeypatch)
    monkeypatch.setattr(api,'_clinic_snapshot',lambda uid:({'status':status},None))
    monkeypatch.setattr(api,'_program_inputs',lambda *args:pytest.fail('invalid calendar must stop source reads'))
    result=api._actual_program_comparisons(SimpleNamespace(uid='p'),None,[],{'metrics':[]},{'comparisons':{'stimulation':{'available':True}}})
    assert result['available'] is False and not result['inputs']['sources']


def test_bad_program_report_withholds_only_comparisons_and_keeps_calendar_status(api,monkeypatch):
    install_program_double(monkeypatch)
    monkeypatch.setattr(api,'_clinic_snapshot',lambda uid:({'status':'stored_snapshot','days':[]},None))
    def unreadable(*args):raise OSError('/private/raw/path')
    monkeypatch.setattr(api,'_program_inputs',unreadable)
    result=api._actual_program_comparisons(SimpleNamespace(uid='p'),None,[],{'metrics':[]},{})
    assert result['available'] is False and result['provenance']['calendar_verified'] is True
    assert result['provenance']['source_validation_failed'] is True and '/private' not in str(result)


def test_compact_program_memo_invalidates_source_clock_policy_and_is_bounded(api,monkeypatch):
    import modules
    program=install_program_double(monkeypatch)
    api._PROGRAM_FACTS.clear();monkeypatch.setattr(api,'_PROGRAM_FACTS_LIMIT',2)
    calls=[];curator=ModuleType('modules.DataCurator')
    curator.loadPerceptJSON=lambda source,**kw:calls.append((source.uid,kw)) or {'synthetic':'raw-array-not-retained'}
    monkeypatch.setitem(sys.modules,'modules.DataCurator',curator)
    monkeypatch.setattr(modules,'DataCurator',curator,raising=False)
    source=SimpleNamespace(uid='s',hashed='h',type='MedtronicJSON',pointer='synthetic-path',metadata={},device='d')
    person=SimpleNamespace(uid='p');table=object();identity=[[],[['d','clock-a']],'config-a']
    load=lambda:api._prepared_program_sources(person,[source],{'d':table},identity)
    first=load();assert calls==[('s',{'table':table,'settings_only':True})]
    first[0]['id']='caller-mutation';assert load()[0]['id']=='s' and len(calls)==1
    source.hashed='changed';load();assert len(calls)==2
    identity[1]=[['d','clock-b']];load();assert len(calls)==3 and len(api._PROGRAM_FACTS)==2
    program.POLICY_VERSION='changed-policy';load();assert len(calls)==4
    person.uid='another-participant';load();assert len(calls)==5
    assert 'raw-array' not in str(api._PROGRAM_FACTS)
    def fail(*args,**kwargs):raise ValueError('bad-source')
    curator.loadPerceptJSON=fail;source.hashed='broken'
    for _ in range(2):
        with pytest.raises(ValueError,match='bad-source'):load()
    assert len(api._PROGRAM_FACTS)==2


def test_program_dependency_identity_is_db_clock_only_and_covers_corrections(api,monkeypatch):
    import modules
    source=SimpleNamespace(uid='s',hashed='h',type='MedtronicJSON',pointer='synthetic-path',metadata={'ClockAnchor':{}},device='d')
    models=SimpleNamespace(SourceFile=SimpleNamespace(find_all=lambda **kwargs:[SimpleNamespace(type='OuraRingAPISource'),source]))
    server=ModuleType('Server');server.models=models;monkeypatch.setitem(sys.modules,'Server',server)
    clock=['a'];config=['cfg'];curator=ModuleType('modules.DataCurator')
    curator.clock_anchor_tables=lambda person:{'d':SimpleNamespace(digest=lambda:clock[0])}
    curator.loadPerceptJSON=lambda *a,**kw:pytest.fail('revision cannot parse original reports')
    monkeypatch.setitem(sys.modules,'modules.DataCurator',curator);monkeypatch.setattr(modules,'DataCurator',curator,raising=False)
    decode=ModuleType('modules.DecodeCommon');decode.private_clinical_config=SimpleNamespace(config_digest=lambda:config[0])
    monkeypatch.setitem(sys.modules,'modules.DecodeCommon',decode)
    person=SimpleNamespace(uid='p');sources,tables,identity=api._program_inputs(person)
    assert sources==[source] and tables['d'].digest()=='a'
    source.metadata['ClockAnchor']['correction']=1;assert api._program_inputs(person)[2]!=identity
    source.metadata['ClockAnchor'].clear();clock[0]='b';assert api._program_inputs(person)[2]!=identity
    clock[0]='a';config[0]='changed';assert api._program_inputs(person)[2]!=identity


def test_real_program_builder_thirteen_metric_envelope_and_native_epoch_gate(api,monkeypatch):
    from modules import AdityaProgramComparisons as programs
    from datetime import datetime,timezone
    t=datetime(2026,6,2,19,tzinfo=timezone.utc).timestamp()
    states=[{'Electrode':'ElectrodeDef.ONE','ElectrodeStateResult':'ElectrodeStateDef.Negative'},
            {'Electrode':'ElectrodeDef.CASE','ElectrodeStateResult':'ElectrodeStateDef.Positive'}]
    setting={'Programs':[{'AmplitudeInMilliAmps':1,'PulseWidthInMicroSecond':60,'RateInHertz':130,'ElectrodeState':states}]}
    group={'GroupId':'GroupIdDef.GROUP_A','ActiveGroup':True,'GroupSettings':{'Cycling':{'Enabled':False}},
           'ProgramSettings':{'LeftHemisphere':setting,'RightHemisphere':setting}}
    report={'SessionDate':datetime.fromtimestamp(t,timezone.utc).isoformat(),
            'SessionEndDate':datetime.fromtimestamp(t+60,timezone.utc).isoformat(),
            'Stimulation':{'InitialStimStatus':'StimStateDef.ON','FinalStimStatus':'StimStateDef.ON'},'Groups':{'Initial':[group],'Final':[group]}}
    facts=programs.prepare_sources([{'id':'synthetic-source','hash':'synthetic-hash','report':report}])
    monkeypatch.setattr(api,'_clinic_snapshot',lambda uid:({'status':'stored_snapshot','days':['2026-06-01']},None))
    monkeypatch.setattr(api,'_program_inputs',lambda person:([],{},[]))
    monkeypatch.setattr(api,'_prepared_program_sources',lambda *args:facts)
    monkeypatch.setattr(api,'_program_period_start',lambda person:t-600)
    keys=['nrs','vas','left_leg_vas','back_vas','relief','mpq_sum','mpq_sen','mpq_aff',
          'mpq_standard_sensory_0_33','mpq_standard_affective_0_12','mpq_standard_0_45','electrocuting','tingly']
    metrics=[{'key':key,'label':key,'range':[0,100]}for key in keys]
    rows=[(str(i),t-300,[])for i in range(6)]+[('before-implant',t-900,[])]
    reports=[{key:i for key in keys}for i in range(7)]
    result=api._actual_program_comparisons(SimpleNamespace(uid='p'),{'rows':rows},reports,{'metrics':metrics},
        {'visit_days':[],'neural_scope':{'coverage_start':t+10000}})
    assert result['available'] and len(result['metrics'])==13
    nrs=next(m for m in result['metrics']if m['key']=='nrs_intensity')
    assert nrs['conditions'][0]['count']==6 and nrs['conditions'][0]['median']==2.5
    assert nrs['provenance']['excluded_period']==1
    assert len(nrs['top']['open_loop'])==1 and not nrs['top']['closed_loop']
    assert len({p['record']for p in nrs['conditions'][0]['points']})==6


def test_program_revision_binds_policy_and_calendar_without_source_decode(api,monkeypatch):
    program=install_program_double(monkeypatch)
    identity=[[],[],[]];calendar={'status':'stored_snapshot','days':['2026-01-01']}
    monkeypatch.setattr(api,'_program_inputs',lambda person:([],{},identity))
    monkeypatch.setattr(api,'_clinic_snapshot',lambda uid:(calendar,{'receipt':'one'}))
    person=SimpleNamespace(uid='p');before=api._actual_program_revision(person)
    import copy
    before=copy.deepcopy(before)
    calendar['days']=['2026-01-02'];assert api._actual_program_revision(person)!=before
    calendar['days']=['2026-01-01'];program.POLICY_VERSION='changed';assert api._actual_program_revision(person)!=before


@pytest.mark.parametrize('value,expected',[(None,None),(0,None),(-1,None),(float('nan'),None),(100,100.)])
def test_program_native_period_start_is_not_neural_coverage(api,monkeypatch,value,expected):
    decode=ModuleType('modules.DecodeCommon');decode.data_start=SimpleNamespace(data_start_s=lambda person:value)
    monkeypatch.setitem(sys.modules,'modules.DecodeCommon',decode)
    assert api._actual_program_period_start(SimpleNamespace(uid='p'))==expected


@pytest.mark.parametrize('metadata', [None, [], {}, {'ClockAnchor':[]}, {'ClockAnchor':{'rule':'unknown'}},
    {'ClockAnchor':{'rule':'SessionEndDate-Final'}},
    {'ClockAnchor':{'rule':'SessionEndDate-Final','session_date_s':True,'anchor_s':1,'final_offset_s':1}},
    {'ClockAnchor':{'rule':'SessionEndDate-Final','session_date_s':2,'anchor_s':1,'final_offset_s':0}},
    {'ClockAnchor':{'rule':'SessionEndDate-Final','session_date_s':1,'anchor_s':1,'final_offset_s':40000}},
    {'ClockAnchor':{'rule':'SessionEndDate-Final','session_date_s':1,'anchor_s':float('inf'),'final_offset_s':0}},
    {'ClockAnchor':{'rule':'SessionEndDate-Final','session_date_s':1e100,'anchor_s':1e100,'final_offset_s':0}},
])
def test_program_prefilter_unknown_metadata_conservatively_keeps_source(api,metadata):
    source=SimpleNamespace(metadata=metadata)
    assert api._source_may_match(source,{'2026-01-01'}) is True
    assert api._source_may_match(source,set()) is False


@pytest.mark.parametrize('start,end,day,expected',[
    ('2026-07-02T05:00:00+00:00','2026-07-02T06:00:00+00:00','2026-07-01',True),
    ('2026-07-02T05:00:00+00:00','2026-07-02T06:00:00+00:00','2026-07-02',False),
    ('2026-07-02T06:30:00+00:00','2026-07-02T07:30:00+00:00','2026-07-02',True),
    ('2026-03-08T08:00:00+00:00','2026-03-08T14:00:00+00:00','2026-03-08',True),
    ('2026-11-01T08:30:00+00:00','2026-11-01T09:30:00+00:00','2026-11-01',True),
])
def test_program_prefilter_uses_both_pacific_boundaries_and_real_dst(api,start,end,day,expected):
    from datetime import datetime
    low=datetime.fromisoformat(start).timestamp();high=datetime.fromisoformat(end).timestamp()
    source=SimpleNamespace(metadata={'ClockAnchor':{'rule':'SessionEndDate-Final','session_date_s':low,
        'anchor_s':high-100,'final_offset_s':100}})
    assert api._source_may_match(source,{day}) is expected


def test_exact_pdf_annotation_is_passed_and_invalidates_only_compact_source_fact(api,monkeypatch):
    import modules,copy
    program=install_program_double(monkeypatch);seen=[]
    def prepare(source):
        seen.append(copy.deepcopy(source));return {'id':source['id'],'hash':source['hash'],'prepared':program.POLICY_VERSION}
    program.prepare_source=prepare
    curator=ModuleType('modules.DataCurator');curator.loadPerceptJSON=lambda *args,**kw:{'Groups':{}}
    monkeypatch.setitem(sys.modules,'modules.DataCurator',curator);monkeypatch.setattr(modules,'DataCurator',curator,raising=False)
    source=SimpleNamespace(uid='source',hashed='h'*64,type='MedtronicJSON',pointer='synthetic',device='d',metadata={'UpstreamSource':{'raw_sha256':'a'*64}})
    evidence={'reviewed':True,'source_id':'source','source_hash':'h'*64,'raw_sha256':'a'*64,'pdf_sha256':'b'*64,'phase':'Initial','side':'left','mode':'SENSING_ONLY'}
    unrelated=[None,{**evidence,'reviewed':False},{**evidence,'source_id':'other'},{**evidence,'source_hash':'other'},{**evidence,'raw_sha256':'other'}]
    api._PROGRAM_FACTS.clear()
    load=lambda:api._prepared_program_sources(SimpleNamespace(uid='p'),[source],{},[[],[]],[evidence,*unrelated])
    load();assert seen[0]['raw_sha256']=='a'*64 and seen[0]['mode_evidence']==[evidence]
    load();assert len(seen)==1
    evidence['pdf_sha256']='c'*64;load();assert len(seen)==2
    source.metadata=None
    api._prepared_program_sources(SimpleNamespace(uid='p'),[source],{},[[],[]],[evidence])
    assert seen[-1]['raw_sha256'] is None and seen[-1]['mode_evidence']==[]
