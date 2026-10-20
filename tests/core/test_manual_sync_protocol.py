import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import Mock
import pytest

PATH=Path(__file__).resolve().parents[2]/'BRAVO/modules/ManualSyncProtocol.py'
spec=importlib.util.spec_from_file_location('manual_sync_protocol',PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@pytest.fixture
def config(tmp_path):
    request=tmp_path/'request';status=tmp_path/'status'
    request.mkdir(mode=0o700);status.mkdir(mode=0o700)
    return {'request_directory':str(request),'status_directory':str(status),'target_participant_uid':'a'*32,
        'target_institute_uid':'b'*32,'owner_uid':os.geteuid(),'source_mode':'retained_files','upstream_available':False}

def status(job,state='running'):
    return {'format':1,'job_id':job,'state':state,'updated_at':10.,'last_success_at':None,
        'streams':{s:{'state':'succeeded' if state=='succeeded' else 'queued','source_mode':'retained_files' if s in ('neural','clinic') else 'provider','last_success_at':None,'error_code':None} for s in m.STREAMS}}

def test_real_concurrent_requests_coalesce_and_terminal_allows_new(config):
    assert m.status(config) is None
    with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(lambda _:m.submit(config,'c'*32),range(8)))
    assert sum(created for _,created in results)==1
    assert len({job['job_id'] for job,_ in results})==1
    first=results[0][0]['job_id']
    m.write_status(config,'target',status(first,'succeeded'))
    second,created=m.submit(config,'c'*32)
    assert created and second['job_id']!=first and second['state']=='queued'

def test_source_progress_is_not_import_success(config):
    job,_=m.submit(config,'c'*32);key=job['job_id']
    source=status(key);source['streams']['neural']['state']='running'
    m.write_status(config,'source',source)
    assert m.status(config)['state']=='running'
    source['state']='succeeded'
    for s in ('neural','clinic'):source['streams'][s]['state']='exported'
    m.write_status(config,'source',source)
    assert m.status(config)['state']=='queued' and m.status(config)['streams']['neural']['state']=='exported'
    source['state']='failed';m.write_status(config,'source',source)
    assert m.status(config)['state']=='queued' and m.status(config)['streams']['oura']['state']=='queued'
    assert m.submit(config,'c'*32)[1] is False
    target=status(key);m.write_status(config,'target',target)
    assert m.status(config)['state']=='running'
    bad=status(key,'succeeded');bad['streams']['neural']['state']='exported'
    m.write_status(config,'target',bad)
    with pytest.raises(m.ProtocolError):m.status(config)

def test_stale_source_and_target_ignored(config):
    job,_=m.submit(config,'c'*32)
    for role in ('source','target'):m.write_status(config,role,status('d'*32,'succeeded'))
    assert m.status(config)['job_id']==job['job_id'] and m.status(config)['state']=='queued'

@pytest.mark.parametrize('value',[None,True,'a',-1,0,float('inf'),float('nan')])
def test_bad_timestamp(value):
    with pytest.raises(m.ProtocolError):m.timestamp(value)

@pytest.mark.parametrize('value',[None,True,'wrong','g'*32])
def test_bad_identity(value):
    with pytest.raises(m.ProtocolError):m.uid(value)

@pytest.mark.parametrize('change',[{'extra':1},{'owner_uid':-1},{'owner_uid':True},{'source_mode':'wrong'},{'upstream_available':'yes'},{'source_mode':'upstream_files'}])
def test_bad_configuration(config,change):
    config.update(change)
    with pytest.raises(m.ProtocolError):m.validate_config(config)

def test_configuration_paths_and_loading(config,tmp_path,monkeypatch):
    assert m.validate_config({**config,'source_mode':'upstream_files','upstream_available':True})
    with pytest.raises(m.ProtocolError):m.validate_config({**config,'status_directory':config['request_directory']})
    monkeypatch.delenv('BRAVO_MANUAL_SYNC_CONFIG_FILE',raising=False)
    with pytest.raises(m.ProtocolError):m.load_config()
    p=tmp_path/'config';p.write_text(json.dumps(config));p.chmod(0o600)
    monkeypatch.setenv('BRAVO_MANUAL_SYNC_CONFIG_FILE',str(p));assert m.load_config()==config
    real=Path.lstat
    with monkeypatch.context() as scoped:
        scoped.setattr(Path,'lstat',lambda path,*a,**k:type('Info',(),{'st_uid':987654})() if path==p else real(path,*a,**k))
        with pytest.raises(m.ProtocolError):m.load_config()

def test_files_fail_closed(config,tmp_path):
    p=tmp_path/'file';p.write_bytes(b'{}');p.chmod(0o600)
    with pytest.raises(m.ProtocolError):m.private_path(Path('relative'),os.geteuid())
    link=tmp_path/'link';link.symlink_to(p)
    with pytest.raises(m.ProtocolError):m.read_json(link,os.geteuid())
    with pytest.raises(m.ProtocolError):m.private_path(p,os.geteuid(),True)
    with pytest.raises(m.ProtocolError):m.private_path(p,os.geteuid()+1)
    p.chmod(0o644)
    with pytest.raises(m.ProtocolError):m.read_json(p,os.geteuid())
    p.chmod(0o600)
    for raw in (b'[]',b'{broken',b'x'*(m.LIMIT+1)):
        p.write_bytes(raw)
        with pytest.raises(m.ProtocolError):m.read_json(p,os.geteuid())
    p.write_bytes(b'{}');os.link(p,tmp_path/'hardlink')
    with pytest.raises(m.ProtocolError):m.private_path(p,os.geteuid())

def test_request_and_status_validation(config):
    m.submit(config,'c'*32);req=m.read_request(config)
    for change in ({'extra':1},{'format':True},{'participant_uid':'d'*32},{'institute_uid':'d'*32}):
        with pytest.raises(m.ProtocolError):m.validate_request({**req,**change},config)
    good=status(req['job_id'])
    for change in ({'extra':1},{'format':True},{'state':'wrong'},{'streams':{}},{'streams':[]}):
        with pytest.raises(m.ProtocolError):m.validate_status({**good,**change})
    for change in ({'extra':1},{'state':'wrong'},{'source_mode':'wrong'},{'error_code':'secret detail'}):
        bad=copy.deepcopy(good);bad['streams']['neural'].update(change)
        with pytest.raises(m.ProtocolError):m.validate_status(bad)
    bad=copy.deepcopy(good);bad['state']='succeeded'
    with pytest.raises(m.ProtocolError):m.validate_status(bad)
    assert m.timestamp(2.)==2. and m.timestamp(None,True) is None
    for fn in (m.read_status,m.write_status):
        with pytest.raises(m.ProtocolError):fn(config,'wrong',*([good] if fn==m.write_status else []))

def test_atomic_failure_and_owner_guards(config,monkeypatch):
    path=Path(config['request_directory'])/'test.json'
    m.atomic_json(path,{'x':1},os.geteuid())
    before=path.read_bytes()
    with monkeypatch.context() as scoped:
        scoped.setattr(m.os,'replace',Mock(side_effect=OSError('synthetic')))
        with pytest.raises(OSError):m.atomic_json(path,{'x':2},os.geteuid())
    assert path.read_bytes()==before and not list(path.parent.glob('.pending-sync-*'))
    with pytest.raises(m.ProtocolError):m.atomic_json(path,{'x':'a'*(m.LIMIT+1)},os.geteuid())
    monkeypatch.setattr(m.os,'geteuid',lambda:999999)
    with pytest.raises(m.ProtocolError):m.atomic_json(path,{},config['owner_uid'])
    with pytest.raises(m.ProtocolError):m.submit(config,'c'*32)


def test_changed_descriptor_and_invalid_path(config,tmp_path,monkeypatch):
    from types import SimpleNamespace as NS
    with pytest.raises(m.ProtocolError):m.private_path(None,os.geteuid())
    path=tmp_path/'data';path.write_text('{}');path.chmod(0o600)
    monkeypatch.setattr(m.os,'fstat',lambda fd:NS(st_mode=0o100600,st_uid=os.geteuid()+1,st_nlink=1))
    with pytest.raises(m.ProtocolError):m.read_json(path,os.geteuid())
