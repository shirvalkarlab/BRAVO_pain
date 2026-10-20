"""Manual worker tests use real mailbox/ledger files and fake ingestion only."""
import contextlib
import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'BRAVO'))
sys.path.insert(0,str(REPO/'scripts/daily_import'))
import manual_sync as m

A,B,C,D=(x*32 for x in 'abcd')


@pytest.fixture
def pair(tmp_path,monkeypatch):
    requests=tmp_path/'requests';statuses=tmp_path/'statuses'
    requests.mkdir(mode=0o700);statuses.mkdir(mode=0o700)
    mailbox={'request_directory':str(requests),'status_directory':str(statuses),'target_participant_uid':A,'target_institute_uid':B,'owner_uid':10001,'source_mode':'retained_files','upstream_available':False}
    original=Path.stat
    def stat(path,*args,**kwargs):
        result=original(path,*args,**kwargs);fields={key:getattr(result,key) for key in dir(result) if key.startswith('st_')}
        fields['st_uid']=fields['st_gid']=10001 if path in (requests,statuses) or requests in path.parents or statuses in path.parents else 0
        return SimpleNamespace(**fields)
    monkeypatch.setattr(Path,'stat',stat)
    ids={'uid':0,'gid':0}
    monkeypatch.setattr(m.os,'geteuid',lambda:ids['uid']);monkeypatch.setattr(m.os,'getegid',lambda:ids['gid'])
    monkeypatch.setattr(m.os,'seteuid',lambda uid:ids.update(uid=uid));monkeypatch.setattr(m.os,'setegid',lambda gid:ids.update(gid=gid))
    real_fstat=m.os.fstat
    def fstat(fd):
        result=real_fstat(fd);fields={key:getattr(result,key) for key in dir(result) if key.startswith('st_')}
        fields['st_uid']=fields['st_gid']=ids['uid']
        return SimpleNamespace(**fields)
    monkeypatch.setattr(m.os,'fstat',fstat)
    monkeypatch.setattr(m.socket,'gethostname',lambda:'synthetic')
    monkeypatch.setattr(m.time,'time',lambda:1000.)
    configs={}
    for role in ('source','target'):
        runtime={'role':role,'hostname':'synthetic','lock':str(tmp_path/(role+'.lock')),'maintenance_marker':str(tmp_path/'maintenance'),'target_config':{'target_participant_uid':A,'target_institute_uid':B}}
        path=tmp_path/(role+'-config.json');m.state.atomic_json(path,runtime)
        configs[role]={'role':role,'hostname':'synthetic','host_config':str(path),'worker_lock':str(tmp_path/(role+'-worker.lock')),'ledger':str(tmp_path/(role+'-ledger.json')),'mailbox':mailbox}
    source=Mock(return_value={'neural':{'deferred':0},'clinic':{'published':False}})
    target=Mock(return_value={'streams':{'neural':{'status':'success'},'clinic':{'status':'success'}},'providers':{'redcap':{'status':'success'},'oura':{'status':'success'}}})
    monkeypatch.setattr(m.host,'source_run',source);monkeypatch.setattr(m.host,'target_run',target)
    return configs,source,target


def submit(config,when=1000,job=C):
    request={'format':1,'job_id':job,'participant_uid':A,'institute_uid':B,'requester_uid':D,'requested_at':when}
    with m.application_identity(10001):m.protocol.atomic_json(Path(config['mailbox']['request_directory'])/'request.json',request,10001)
    return request


def test_full_ordered_sync_real_mailbox_no_duplicate(pair):
    configs,source,target=pair;s,t=configs.values()
    assert m.process(s)['state']=='idle'
    submit(s)
    assert m.process(t)['state']=='waiting_source';target.assert_not_called()
    assert m.process(s)['state']=='succeeded'
    assert m.shared(s,m.protocol.status)['state']=='queued'
    assert m.process(t)['state']=='succeeded'
    status=m.shared(t,m.protocol.status)
    assert all(v['last_success_at']==1000 for v in status['streams'].values())
    assert status['last_success_at']==1000
    assert m.process(s)['state']==m.process(t)['state']=='already_processed'
    assert source.call_count==target.call_count==1
    assert target.call_args.kwargs=={'manual':True,'source_streams':{'neural':True,'clinic':True}}


def test_source_failure_still_runs_providers_and_keeps_success_times(pair):
    configs,source,target=pair;s,t=configs.values();submit(s)
    source.side_effect=ValueError('private error must not escape')
    assert m.process(s)['state']=='failed'
    assert m.shared(s,m.protocol.status)['state']=='queued'
    target.return_value['streams']={name:{'status':'blocked'} for name in ('neural','clinic')}
    assert m.process(t)['state']=='failed'
    target.assert_called_once();assert target.call_args.kwargs['source_streams']=={'neural':False,'clinic':False}
    status=m.shared(t,m.protocol.status)
    assert status['streams']['neural']['last_success_at'] is None
    assert status['streams']['redcap']['last_success_at']==1000
    assert 'private error' not in json.dumps(status)


def test_stream_failure_preserves_prior_success(pair,monkeypatch):
    configs,source,target=pair;s,t=configs.values();submit(s);m.process(s);m.process(t)
    submit(s,1100,A);monkeypatch.setattr(m.time,'time',lambda:1100.)
    assert m.process(s)['state']=='succeeded'
    assert m.shared(s,m.protocol.status)['last_success_at']==1000
    target.return_value['streams']['clinic']={'status':'failed'};target.return_value['providers']['oura']={'status':'disabled'}
    assert m.process(t)['state']=='failed'
    status=m.shared(t,m.protocol.status)
    assert status['streams']['clinic']['last_success_at']==1000 and status['streams']['redcap']['last_success_at']==1100
    assert status['streams']['oura']['state']=='not_configured' and status['last_success_at']==1000


def test_busy_maintenance_and_previous_target(pair,monkeypatch):
    configs,source,target=pair;s,t=configs.values();submit(s)
    runtime=m.host.private_config(s['host_config'])
    with m.host.exclusive_lock(runtime['lock']):assert m.process(s)['state']=='busy'
    assert not Path(s['ledger']).exists();source.assert_not_called()
    m.process(s);marker=Path(m.host.private_config(t['host_config'])['maintenance_marker']);marker.touch()
    assert m.process(t)['state']=='maintenance';target.assert_not_called()
    marker.unlink()
    submit(s,1100,A)
    assert m.process(s,1100)['state']=='waiting_previous_target'


def test_replay_cooldown_stale_and_future(pair):
    configs,source,target=pair;s,t=configs.values();submit(s);m.process(s);m.process(t)
    submit(s,1000,A);assert m.process(s)['state']=='rejected'
    submit(s,1001,A);assert m.process(s,1001)['state']=='cooldown'
    submit(s,3000,A);assert m.process(s,1100)['state']=='rejected'
    submit(s,1001,A);assert m.process(s,100000)['state']=='rejected'


def test_incomplete_export_and_unknown_stage(pair):
    configs,source,target=pair;s,t=configs.values();request=submit(s)
    source.return_value={'neural':{'deferred':1},'clinic':{}}
    assert m.process(s)['state']=='failed'
    target.return_value['providers']['oura']={'status':'unexpected'}
    assert m.process(t)['state']=='failed'
    value=m.shared(t,m.protocol.status)
    assert all(v['error_code']=='import_failed' for v in value['streams'].values())


def test_interrupted_and_unpublished_status_recovery(pair,monkeypatch):
    configs,source,target=pair;s,t=configs.values();request=submit(s)
    ledger=m.ledger_read(s['ledger']);ledger.update(job_id=C,state='running',requested_at=1000,started_at=1000)
    m.state.atomic_json(s['ledger'],ledger)
    assert m.process(s)['state']=='failed';source.assert_not_called()
    assert m.shared(s,m.protocol.read_status,'source')['streams']['neural']['error_code']=='worker_unavailable'
    Path(s['mailbox']['status_directory'],'source-status.json').unlink()
    assert m.process(s)['state']=='already_processed'
    assert m.shared(s,m.protocol.read_status,'source')['state']=='failed'
    ledger['state']='succeeded';ledger['status']=None;m.state.atomic_json(s['ledger'],ledger)
    assert m.process(s)['state']=='already_processed'


@pytest.mark.parametrize('failure',['host','role','upstream','target_binding','state_owner'])
def test_worker_guards(pair,monkeypatch,failure):
    configs,source,target=pair;config=copy.deepcopy(configs['target']);runtime=m.host.private_config(config['host_config'])
    if failure=='host':config['hostname']='wrong'
    if failure=='role':config['role']='other'
    if failure=='upstream':config['mailbox'].update(source_mode='upstream_files',upstream_available=True)
    if failure=='target_binding':runtime['target_config']['target_participant_uid']=C
    if failure=='state_owner':
        config['ledger']=str(Path(config['mailbox']['request_directory'])/'ledger')
    with pytest.raises(ValueError):m.validate_worker(config,runtime)


def test_ledger_guards(pair):
    configs,_,_=pair;path=configs['source']['ledger']
    value=m.ledger_read(path);value['state']='invalid';m.state.atomic_json(path,value)
    with pytest.raises(ValueError):m.ledger_read(path)
    value['state']='idle';value['stream_success']={};m.state.atomic_json(path,value)
    with pytest.raises(ValueError):m.ledger_read(path)


def test_identity_restoration_on_switch_failure(pair,monkeypatch):
    original=m.os.seteuid
    def refused(uid):
        if uid==10001:raise OSError('switch failed')
        original(uid)
    monkeypatch.setattr(m.os,'seteuid',refused)
    with pytest.raises(OSError):
        with m.application_identity(10001):pytest.fail('not reached')
    assert (m.os.geteuid(),m.os.getegid())==(0,0)


def test_main_sanitized_result_and_exception(pair,monkeypatch,capsys):
    config=pair[0]['source'];monkeypatch.setattr(sys,'argv',['worker','--config','synthetic'])
    monkeypatch.setattr(m.host,'private_config',lambda path:config)
    monkeypatch.setattr(m,'process',lambda config:{'state':'idle'})
    assert m.main()==0;assert json.loads(capsys.readouterr().out)=={'state':'idle'}
    monkeypatch.setattr(m,'process',Mock(side_effect=ValueError('private secret')))
    assert m.main()==1;assert 'private secret' not in capsys.readouterr().out


def test_direct_source_partial_success_keeps_providers_independent(pair):
    configs,source,target=pair;s,t=configs.values()
    for config in configs.values():
        config['mailbox'].update(source_mode='upstream_files',upstream_available=True)
        runtime=json.loads(Path(config['host_config']).read_text())
        (runtime['target_config'] if config['role']=='target' else runtime)['upstream']={}
        m.state.atomic_json(config['host_config'],runtime)
    source.return_value={'neural':{'status':'failed'},'clinic':{'status':'success'}}
    target.return_value['streams']['neural']={'status':'blocked'}
    submit(s)
    assert m.process(s)['state']=='failed'
    assert m.process(t)['state']=='failed'
    assert target.call_args.kwargs['source_streams']=={'neural':False,'clinic':True}
    result=m.shared(t,m.protocol.status)
    assert result['streams']['clinic']['last_success_at']==1000
    assert result['streams']['neural']['last_success_at'] is None
    assert result['streams']['oura']['last_success_at']==1000


@pytest.mark.parametrize('error',['unknown_device','changed_source'])
def test_target_withheld_error_is_sanitized_explicitly(pair,error):
    configs,source,target=pair;s,t=configs.values()
    target.return_value['streams']['neural']={'status':'failed','error_code':error}
    submit(s);m.process(s);m.process(t)
    assert m.shared(t,m.protocol.status)['streams']['neural']['error_code']==error
