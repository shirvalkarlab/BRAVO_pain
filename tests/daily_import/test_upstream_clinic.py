import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/daily_import'))
import upstream_clinic as m
import clinic
import state

MIME='application/vnd.google-apps.spreadsheet'
UID='a'*32


def row(ident='one',name='Clinic Testing 01_01_26',version='1',modified='2026-01-01T00:00:00Z',mime=MIME):
    return {'id':ident,'name':name,'version':version,'modifiedTime':modified,'mimeType':mime}


def metadata(rows):return {'folder_id':'folder','rows':rows,'credential_unchanged':True}


def tar_bytes(files,kind=None):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as archive:
        for name,raw in files:
            info=tarfile.TarInfo(name)
            if kind:
                info.type=kind;info.linkname='other';archive.addfile(info)
            else:
                info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
    return stream.getvalue()


@pytest.fixture
def environment(tmp_path,monkeypatch):
    monkeypatch.setattr(clinic.os,'chown',Mock())
    parent=tmp_path/'accepted';parent.mkdir();out=tmp_path/'upstream';out.mkdir();provenance=tmp_path/'provenance';provenance.mkdir()
    rows=[row(),row('missing','Clinic Testing 01_02_26')]
    files=[{'file':r['name']+'.xlsx','bytes':len(b'PKoriginal'),'sha256':state.sha(b'PKoriginal')} for r in rows]
    manifest={'format':1,'source_participant_uid':UID,'count':len(files),'total_bytes':sum(x['bytes'] for x in files),'files':files}
    archive=tmp_path/'baseline.tar';archive.write_bytes(tar_bytes([(f'workbooks/{x["file"]}',b'PKoriginal') for x in files]+[('clinic.manifest',state.encoded(manifest))]))
    snapshot=clinic.receive(archive,parent,manifest);clinic.publish_current(parent,snapshot)
    record={'format':1,'folder_id':'folder','source_participant_uid':UID,'files':[{**r,**x} for r,x in zip(rows,files)]}
    baseline=tmp_path/'baseline.json';baseline.write_bytes(state.encoded(record))
    config={'enabled':True,'source_container':'synthetic-server','workdir':'/usr/src/BRAVO','folder_id':'folder','client_sha256':'b'*64,'source_participant_uid':UID,'owner_uid':10001,'snapshots':str(out),'provenance_directory':str(provenance),'baseline_manifest':str(parent/'CURRENT'),'baseline_provenance':str(baseline)}
    calls=[]
    def call(request,output=None):
        calls.append(request)
        if request['mode']=='metadata':return metadata([rows[0]])
        output.write(tar_bytes([('workbooks/'+x['file'],b'PKdownload') for x in request['files']]))
    return SimpleNamespace(config=config,rows=rows,manifest=manifest,record=record,parent=parent,out=out,provenance=provenance,baseline=baseline,snapshot=snapshot,calls=calls,call=call)


def test_current_plus_retained_history_and_idempotent_metadata_check(environment):
    e=environment;result=m.refresh(e.config,e.call)
    assert result['status']=='success' and result['fresh_files']==1 and result['retained_files']==1 and result['downloaded_files']==0
    current=json.loads((e.out/'CURRENT').read_bytes());assert current==e.manifest
    record=json.loads((e.provenance/'CURRENT.json').read_bytes())
    assert {x['id']:x['status'] for x in record['files']}=={'one':'cloud_current','missing':'retained_not_fresh'}
    assert len([r for r in e.calls if r['mode']=='metadata'])==2
    again=m.refresh(e.config,e.call)
    assert again['manifest_sha256']==result['manifest_sha256'] and again['downloaded_files']==0
    assert (e.parent/'CURRENT').read_bytes()==state.encoded(e.manifest)


def test_unknown_baseline_version_downloads_current_only(environment):
    e=environment
    for x in e.record['files']:x.pop('version')
    e.baseline.write_bytes(state.encoded(e.record))
    result=m.refresh(e.config,e.call)
    assert result['status']=='success' and result['downloaded_files']==1 and result['retained_files']==1
    requests=[r for r in e.calls if r['mode']=='export']
    assert [x['id'] for x in requests[0]['files']]==['one']
    record=json.loads((e.provenance/'CURRENT.json').read_bytes())
    assert next(x for x in record['files'] if x['id']=='missing')['sha256']==state.sha(b'PKoriginal')


def test_rename_replaces_old_name_once_and_new_id_same_name_is_refused(environment):
    e=environment;renamed=row(name='Renamed Testing 01_01_26')
    result=m.refresh(e.config,lambda request,output=None: metadata([renamed]))
    assert result['status']=='success'
    names={x['file'] for x in json.loads((e.out/'CURRENT').read_bytes())['files']}
    assert renamed['name']+'.xlsx' in names and e.rows[0]['name']+'.xlsx' not in names and len(names)==2
    previous,_=m.previous_state(e.config)
    with pytest.raises(ValueError,match='collision'):m.plan_files(previous,{'replacement':{**renamed,'id':'replacement','file':renamed['name']+'.xlsx'}})


def test_changed_version_downloads_and_rechecks(environment):
    e=environment;live=row(version='2')
    def call(request,output=None):
        if request['mode']=='metadata':return metadata([live])
        output.write(tar_bytes([('workbooks/'+live['name']+'.xlsx',b'PKchanged')]))
    result=m.refresh(e.config,call)
    assert result['status']=='success' and result['downloaded_files']==1
    assert next(x for x in json.loads((e.out/'CURRENT').read_bytes())['files'] if x['file']==live['name']+'.xlsx')['sha256']==state.sha(b'PKchanged')


def test_cloud_drift_defers_without_publishing_even_when_no_download(environment):
    e=environment;count=[0]
    def call(request,output=None):
        count[0]+=1;return metadata([row(version=str(count[0]))])
    result=m.refresh(e.config,call)
    assert result['status']=='failed' and result['deferred'] is True
    assert not (e.out/'CURRENT').exists() and not (e.provenance/'CURRENT.json').exists()


def test_interrupted_current_publication_repairs_from_verified_snapshot(environment,monkeypatch):
    e=environment;real=clinic.publish_current
    monkeypatch.setattr(clinic,'publish_current',lambda *args:(_ for _ in ()).throw(OSError('synthetic publish failure')))
    assert m.refresh(e.config,e.call)['status']=='failed'
    assert (e.provenance/'CURRENT.json').exists() and not (e.out/'CURRENT').exists()
    monkeypatch.setattr(clinic,'publish_current',real)
    assert m.refresh(e.config,e.call)['status']=='success' and (e.out/'CURRENT').exists()


def test_missing_retained_bytes_fails_before_cloud_access(environment):
    e=environment;(e.snapshot/'workbooks'/e.record['files'][1]['file']).unlink()
    assert m.refresh(e.config,e.call)['status']=='failed' and not e.calls


@pytest.mark.parametrize('change',[
    lambda c:c.update(enabled=False),lambda c:c.update(source_container='bad/name'),lambda c:c.update(workdir='/other'),lambda c:c.update(folder_id="bad'query"),lambda c:c.update(client_sha256='bad'),lambda c:c.update(owner_uid=0),lambda c:c.update(source_participant_uid='bad'),lambda c:c.update(provenance_directory=c['snapshots']),lambda c:c.update(snapshots='/missing-upstream-test-dir'),
])
def test_bad_configuration_refused(environment,change):
    e=environment;change(e.config)
    assert m.refresh(e.config,e.call)['status']=='failed' and not e.calls


@pytest.mark.parametrize('response',[
    {'folder_id':'other','rows':[],'credential_unchanged':True},metadata([row(),row()]),metadata([row(name='../Testing')]),metadata([row(version='bad')]),metadata([row(modified='')]),metadata([row('one'),row('two')]),metadata([]),metadata('invalid'),metadata([row()]*401),
])
def test_cloud_inventory_rejects_ambiguous_or_unbounded_metadata(response):
    with pytest.raises((ValueError,TypeError)):m.cloud_inventory(response,'folder')


def test_cloud_filter_excludes_templates_old_non_testing_and_other_mime():
    accepted=m.cloud_inventory(metadata([row(),row('template','[Template] Clinic Testing'),row('old','OLD - Clinic Testing'),row('log','Stage1 Log'),row('text','Clinic Testing',mime='text/plain')]),'folder')
    assert set(accepted)=={'one'}


@pytest.mark.parametrize('change',[
    lambda p:p.update(format=2),lambda p:p.update(folder_id='other'),lambda p:p['files'].append(p['files'][0]),lambda p:p['files'][0].update(id='bad/id'),lambda p:p['files'][0].update(sha256='c'*64),lambda p:p['files'][0].update(mimeType='text/plain'),lambda p:p['files'].pop(),
])
def test_provenance_must_bind_exact_prior_bytes(environment,change):
    e=environment;change(e.record)
    with pytest.raises(ValueError):m.validate_provenance(e.record,e.manifest,e.config)


@pytest.mark.parametrize('payload',[
    tar_bytes([('workbooks/a.xlsx',b'PKok')],kind=tarfile.SYMTYPE),tar_bytes([('../outside',b'PKbad')]),tar_bytes([('workbooks/a.xlsx',b'bad')]),tar_bytes([('workbooks/a.xlsx',b'PKok'),('workbooks/a.xlsx',b'PKok')]),tar_bytes([('workbooks/b.xlsx',b'PKunexpected')]),tar_bytes([]),
])
def test_download_archive_is_exact_bounded_and_no_links(payload):
    with pytest.raises(ValueError):m.read_downloads(io.BytesIO(payload),{'a.xlsx'})


def test_download_total_bound_and_manifest_bounds(environment,monkeypatch):
    e=environment;monkeypatch.setattr(clinic,'MAX_TOTAL',1)
    with pytest.raises(ValueError):m.read_downloads(io.BytesIO(tar_bytes([('workbooks/a.xlsx',b'PKok')])),{'a.xlsx'})
    assert m.refresh(e.config,e.call)['status']=='failed'


def test_no_space_never_publishes(environment,monkeypatch):
    monkeypatch.setattr(m.shutil,'disk_usage',lambda p:SimpleNamespace(free=0))
    assert m.refresh(environment.config,environment.call)['status']=='failed'
    assert not (environment.out/'CURRENT').exists()


def test_transport_failure_never_publishes(environment):
    def call(*args):raise subprocess.TimeoutExpired('synthetic',1)
    assert m.refresh(environment.config,call)['status']=='failed'


def source_fixture(tmp_path,*,drift=False,mutate_credential=False,name='Clinic Testing 01_01_26'):
    credential=tmp_path/'synthetic-credential.json';credential.write_text('synthetic token bytes')
    rows=[row(name=name)]
    code=f'''from pathlib import Path
from types import SimpleNamespace
DEFAULT_FOLDER_ID='folder'
def folder_id():return DEFAULT_FOLDER_ID
def credential_source():return 'user'
def token_file():return {str(credential)!r}
ROWS={rows!r}
class Request:
 def __init__(self,fn):self.fn=fn
 def execute(self,num_retries=0):
  assert num_retries==0
  return self.fn()
class Drive:
 def __init__(self):self.calls=0;self._http=SimpleNamespace(http=SimpleNamespace(timeout=None))
 def files(self):return self
 def list(self,**kwargs):
  assert kwargs['q']=="'folder' in parents and trashed=false"
  assert kwargs['pageSize']==100 and kwargs['pageToken'] is None
  self.calls+=1
  rows=[dict(x) for x in ROWS]
  if {drift!r} and self.calls>1:rows[0]['version']='2'
  return Request(lambda:{{'files':rows}})
 def export(self,fileId,mimeType):
  assert fileId=='one' and mimeType=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  def execute():
   if {mutate_credential!r}:Path(token_file()).write_text('changed synthetic token')
   return b'PKsynthetic actual source transport payload'
  return Request(execute)
class GoogleClient:
 def __init__(self):self._drive=Drive()
'''
    module=tmp_path/'google_sheets_client.py';module.write_text(code)
    request={'mode':'metadata','folder_id':'folder','client_sha256':hashlib.sha256(module.read_bytes()).hexdigest()}
    return module,credential,request,rows


def run_source(module,request):
    # macOS rejects Linux's address-space limit; exercise the rest of the exact
    # embedded program while leaving its production Linux limit call unchanged.
    prefix="import resource; resource.setrlimit=lambda kind,bounds: None\n" if sys.platform=='darwin' else ''
    code=prefix+'request='+repr(request)+'\n'+m.SOURCE_CODE.replace('/usr/src/BRAVO/modules/StimOptimizer/google_sheets_client.py',str(module))
    return subprocess.run([sys.executable,'-B','-c',code],capture_output=True,timeout=20)


def test_embedded_source_executes_real_metadata_and_tar_contract(tmp_path):
    module,credential,request,rows=source_fixture(tmp_path)
    result=run_source(module,request)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==metadata(rows)
    request.update(mode='export',observed_rows=rows,files=[{'id':'one','file':rows[0]['name']+'.xlsx'}])
    result=run_source(module,request)
    assert result.returncode==0,result.stderr
    payload=m.read_downloads(io.BytesIO(result.stdout),{rows[0]['name']+'.xlsx'})
    assert next(iter(payload.values()))==b'PKsynthetic actual source transport payload'
    assert credential.read_text()=='synthetic token bytes'
    assert not (tmp_path/'__pycache__').exists()


@pytest.mark.parametrize('problem',['drift','credential','wrong_hash','wrong_folder','wrong_id','duplicate_id','filename_change','observed_change','bad_mode','backslash','nul'])
def test_embedded_source_fails_closed_without_exporting_payload(tmp_path,problem):
    module,credential,request,rows=source_fixture(tmp_path,drift=problem=='drift',mutate_credential=problem=='credential',name=('Clinic Testing'+chr(92)+'evil' if problem=='backslash' else 'Clinic Testing'+chr(0)+'evil' if problem=='nul' else 'Clinic Testing 01_01_26'))
    request.update(mode='export',observed_rows=rows,files=[{'id':'one','file':rows[0]['name']+'.xlsx'}])
    if problem=='wrong_hash':request['client_sha256']='0'*64
    if problem=='wrong_folder':request['folder_id']='other'
    if problem=='wrong_id':request['files'][0]['id']='outside'
    if problem=='duplicate_id':request['files']*=2
    if problem=='filename_change':request['files'][0]['file']='different.xlsx'
    if problem=='observed_change':request['observed_rows']=[]
    if problem=='bad_mode':request['mode']='other'
    result=run_source(module,request)
    assert result.returncode!=0 and result.stdout==b''
    assert b'current limit exceeds maximum' not in result.stderr
    assert b'AssertionError' in result.stderr or b'KeyError' in result.stderr or b'invalid upstream mode' in result.stderr


def test_host_transport_uses_fixed_container_without_env_file_and_bounds(environment,monkeypatch):
    e=environment;calls=[]
    monkeypatch.setattr(m.resource,'setrlimit',Mock())
    def run(args,**kwargs):
        kwargs['preexec_fn']()
        calls.append((args,kwargs));kwargs['stdout'].write(json.dumps(metadata(e.rows)).encode());return SimpleNamespace(returncode=0)
    monkeypatch.setattr(m.subprocess,'run',run)
    assert m.source_call(e.config,{'mode':'metadata'})==metadata(e.rows)
    args,kwargs=calls[0]
    assert args[:6]==['docker','exec','-i','-w','/usr/src/BRAVO','-e']
    assert '--env-file' not in args and e.config['source_container'] in args and kwargs['timeout']==620
    output=io.BytesIO();m.source_call(e.config,{'mode':'export'},output);assert output.getvalue()
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1))
    with pytest.raises(ValueError,match='read failed'):m.source_call(e.config,{'mode':'metadata'})


def test_metadata_and_request_limits(environment,monkeypatch):
    e=environment;monkeypatch.setattr(m,'META_MAX',10000)
    with pytest.raises(ValueError,match='request'):m.source_call(e.config,{'mode':'metadata','extra':'x'*10001})
    def run(*args,**kwargs):kwargs['stdout'].write(b'x'*10001);return SimpleNamespace(returncode=0)
    monkeypatch.setattr(m.subprocess,'run',run)
    with pytest.raises(ValueError,match='metadata exceeds'):m.source_call(e.config,{'mode':'metadata'})


def test_linux_source_transport_retains_real_memory_and_cpu_limits():
    assert 'resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))' in m.SOURCE_CODE
    assert 'resource.setrlimit(resource.RLIMIT_CPU,(120,120))' in m.SOURCE_CODE


def test_combined_history_file_limit():
    previous={'one':{'file':'one.xlsx'},'two':{'file':'two.xlsx'}}
    old=clinic.MAX_FILES
    try:
        clinic.MAX_FILES=1
        with pytest.raises(ValueError,match='history exceeds'):m.plan_files(previous,{})
    finally:clinic.MAX_FILES=old


def test_export_stream_and_combined_payload_bounds(environment,monkeypatch):
    e=environment
    for entry in e.record['files']:entry.pop('version')
    e.baseline.write_bytes(state.encoded(e.record))
    monkeypatch.setattr(m,'TRANSPORT_MAX',10)
    assert m.refresh(e.config,e.call)['status']=='failed' and not (e.out/'CURRENT').exists()
    monkeypatch.setattr(m,'TRANSPORT_MAX',1024*1024)
    monkeypatch.setattr(clinic,'MAX_TOTAL',25)
    def call(request,output=None):
        if request['mode']=='metadata':return metadata([e.rows[0]])
        output.write(tar_bytes([('workbooks/'+e.rows[0]['name']+'.xlsx',b'PK'+b'x'*18)]))
    assert m.refresh(e.config,call)['status']=='failed' and not (e.out/'CURRENT').exists()
