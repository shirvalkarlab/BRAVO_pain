"""Host orchestration contracts using synthetic files and fake Docker only."""
import copy
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'daily_import'))
import host
import state

A, B, C = (x * 32 for x in 'abc')
REV = 'e' * 40
RAW = b'{"SessionDate":"2026-01-01T00:00:00Z","DeviceInformation":{}}'
OBS = {'source_uid': A, 'stored_hash': 'f' * 64, 'pointer': '/raws/' + A, 'stat': [1, 2, 16, 3, 4]}
ENTRY = {'source_uid': A, 'path': 'sources/' + A + '.json', 'bytes': len(RAW), 'sha256': state.sha(RAW)}
MANIFEST = {'format': 1, 'source_participant_uid': C, 'count': 1, 'total_bytes': len(RAW),
            'files': [ENTRY], 'fingerprints': {A: 'f' * 64}}
CHECKPOINT = {'format': 1, 'source_participant_uid': C, 'sources': {}}


def tar_bytes(members=None):
    output = io.BytesIO()
    if members is None:
        members = [(ENTRY['path'], RAW), ('export.manifest', state.encoded(MANIFEST))]
    with tarfile.open(fileobj=output, mode='w') as archive:
        for name, raw in members:
            member = tarfile.TarInfo(name)
            if raw is None:
                member.type = tarfile.SYMTYPE
                member.linkname = '/private/file'
                archive.addfile(member)
            else:
                member.size = len(raw)
                archive.addfile(member, io.BytesIO(raw))
    return output.getvalue()


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setattr(host.os, 'chown', Mock())
    batches = tmp_path / 'batches'
    batches.mkdir()
    archive = tmp_path / 'archive.tar'
    archive.write_bytes(tar_bytes())
    return archive, batches


def test_receive_publishes_and_replays(tree):
    archive, batches = tree
    assert host.receive(archive, batches, C, {A: OBS}, 10001, 10001) == MANIFEST
    batch = batches / state.sha(state.encoded(MANIFEST))
    assert state.validate_batch(batch, C) == MANIFEST
    assert host.receive(archive, batches, C, {A: OBS}, 10001, 10001) == MANIFEST
    assert list(batches.iterdir()) == [batch]
    assert host.os.chown.call_count == 10


@pytest.mark.parametrize('members', [
    [('bad/path', RAW)], [('sources/' + A + '.json', None)],
    [(ENTRY['path'], b'')], [(ENTRY['path'], RAW), (ENTRY['path'], RAW)],
    [(ENTRY['path'], RAW)], [('export.manifest', b'{}'), ('export.manifest', b'{}')],
    [(ENTRY['path'], RAW), ('export.manifest', state.encoded({**MANIFEST, 'files': [{**ENTRY, 'sha256': '1' * 64}]}))],
    [(ENTRY['path'], RAW), ('export.manifest', state.encoded({**MANIFEST, 'fingerprints': {A: '1' * 64}}))],
])
def test_bad_archives_never_publish(tree, members):
    archive, batches = tree
    archive.write_bytes(tar_bytes(members))
    with pytest.raises(ValueError):
        host.receive(archive, batches, C, {A: OBS}, 10001, 10001)
    assert list(batches.iterdir()) == []


def test_receiver_bounds_and_collision(tree, monkeypatch):
    archive, batches = tree
    for name, value in [('MAX_FILE', 1), ('MAX_FILES', 0), ('MAX_TOTAL', 1)]:
        with monkeypatch.context() as patch:
            patch.setattr(state, name, value)
            with pytest.raises(ValueError):
                host.receive(archive, batches, C, {A: OBS}, 1, 1)
    with monkeypatch.context() as patch:
        patch.setattr(host, 'META_LIMIT', 1)
        with pytest.raises(ValueError):
            host.receive(archive, batches, C, {A: OBS}, 1, 1)
    batch = batches / state.sha(state.encoded(MANIFEST))
    batch.mkdir()
    monkeypatch.setattr(state, 'validate_batch', lambda *args: {'wrong': True})
    with pytest.raises(ValueError, match='conflicts'):
        host.receive(archive, batches, C, {A: OBS}, 1, 1)


def source_config(tmp_path):
    batches = tmp_path / 'batches'
    batches.mkdir(exist_ok=True)
    baseline = tmp_path / 'baseline.json'
    baseline.write_bytes(state.encoded(MANIFEST))
    return {'checkpoint': str(tmp_path / 'checkpoint.json'), 'batches': str(batches),
        'baseline_manifest': str(baseline), 'source_config': {'source_participant_uid': C},
        'owner_uid': 10001, 'owner_gid': 10001, 'observation_seconds': 1}


def test_source_complete_replay_noop_and_defer(tmp_path, monkeypatch):
    config = source_config(tmp_path)
    monkeypatch.setattr(host.os, 'chown', Mock())
    monkeypatch.setattr(host.shutil, 'disk_usage', lambda path: NS(free=10**12))
    events = []
    def transport(config, request, output=None):
        events.append(request['mode'])
        if request['mode'] == 'inventory':
            return {A: OBS, B: None}
        if request['mode'] == 'baseline':
            return CHECKPOINT
        output.write(tar_bytes())
    first = host.source_run(config, transport, lambda seconds: None)
    assert first == {'initialized': True, 'inventory': 2, 'exported': 1, 'deferred': 1}
    assert events == ['inventory', 'inventory', 'baseline', 'export']
    # Simulate crash after publishing, before checkpoint acknowledgement.
    state.atomic_json(config['checkpoint'], CHECKPOINT)
    (Path(config['batches']) / '.pending-orphan').mkdir()
    assert host.source_run(config, transport, lambda seconds: None)['exported'] == 0
    checkpoint = json.loads(Path(config['checkpoint']).read_text())
    assert checkpoint['sources'][A]['sha256'] == state.sha(RAW)


@pytest.mark.parametrize('interval', [True, 0, 301, '5'])
def test_source_bad_interval(tmp_path, interval):
    config = {**source_config(tmp_path), 'observation_seconds': interval}
    with pytest.raises(ValueError, match='interval'):
        host.source_run(config, Mock())


def test_source_disk_failure_and_export_failure(tmp_path, monkeypatch):
    config = source_config(tmp_path)
    state.atomic_json(config['checkpoint'], CHECKPOINT)
    def transport(config, request, output=None):
        if request['mode'] == 'inventory':
            return {A: OBS}
        output.write(b'partial')
        raise RuntimeError('source interrupted')
    monkeypatch.setattr(host.shutil, 'disk_usage', lambda path: NS(free=0))
    with pytest.raises(ValueError, match='space'):
        host.source_run(config, transport, lambda seconds: None)
    monkeypatch.setattr(host.shutil, 'disk_usage', lambda path: NS(free=10**12))
    with pytest.raises(RuntimeError):
        host.source_run(config, transport, lambda seconds: None)
    assert json.loads(Path(config['checkpoint']).read_text()) == CHECKPOINT
    assert list(Path(config['batches']).iterdir()) == []


def test_source_wrong_batch_identity(tmp_path, monkeypatch):
    config = source_config(tmp_path)
    state.atomic_json(config['checkpoint'], CHECKPOINT)
    (Path(config['batches']) / ('1' * 64)).mkdir()
    monkeypatch.setattr(state, 'validate_batch', lambda *args: MANIFEST)
    with pytest.raises(ValueError, match='directory identity'):
        host.source_run(config, lambda *args: {}, lambda seconds: None)


def test_source_spool_bound(tmp_path, monkeypatch):
    config = source_config(tmp_path)
    state.atomic_json(config['checkpoint'], CHECKPOINT)
    monkeypatch.setattr(host.shutil, 'disk_usage', lambda path: NS(free=10**12))
    monkeypatch.setattr(state, 'MAX_TOTAL', 1)
    monkeypatch.setattr(state, 'MAX_FILES', 1)
    monkeypatch.setattr(host, 'META_LIMIT', 1024)
    def transport(config, request, output=None):
        if output is None:
            return {A: OBS}
        output.write(b'x' * 3000)
    with pytest.raises(ValueError, match='archive size'):
        host.source_run(config, transport, lambda seconds: None)


def test_lock_exclusion_and_release(tmp_path):
    path = tmp_path / 'lock'
    with host.exclusive_lock(path):
        with pytest.raises(BlockingIOError):
            with host.exclusive_lock(path):
                pytest.fail('competing holder entered')
    with host.exclusive_lock(path):
        pass


def test_private_config(tmp_path, monkeypatch):
    path = tmp_path / 'config'
    path.write_text('{}')
    with pytest.raises(ValueError):
        host.private_config(path)
    real_stat = Path.stat
    def root_stat(self, *args, **kwargs):
        result = real_stat(self, *args, **kwargs)
        if self == path:
            return NS(st_uid=0, st_mode=stat.S_IFREG | 0o600)
        return result
    monkeypatch.setattr(Path, 'stat', root_stat)
    monkeypatch.setattr(state, 'read_bounded', lambda *args: b'{"test":true}')
    assert host.private_config(path) == {'test': True}


def test_bootstrap_embeds_modules_no_paths_or_writes():
    for target in (True, False):
        code = host.bootstrap({'test': 'sentinel'}, target)
        compile(code, '<bootstrap>', 'exec')
        assert b"'test': 'sentinel'" in code
        assert b'resource.setrlimit' in code
        assert (b"sys.modules['target_adapter'].execute(request)" in code) == target


def test_checked_success_and_error():
    assert host.checked([sys.executable, '-c', 'print("ok")']) == b'ok\n'
    with pytest.raises(subprocess.CalledProcessError):
        host.checked([sys.executable, '-c', 'raise SystemExit(3)'])


def test_source_transport(tmp_path, monkeypatch):
    config = {'source_workdir': '/app', 'source_container': 'source', 'source_config': {}}
    calls = []
    def checked(command, **kwargs):
        calls.append((command, kwargs))
        kwargs['output'].write(b'{"inventory":1}')
    monkeypatch.setattr(host, 'checked', checked)
    assert host.source_transport(config, {'mode': 'inventory'}) == {'inventory': 1}
    assert calls[0][0][-6:] == ['timeout', '--signal=TERM', '--kill-after=30', '1800', 'python3', '-']
    output = io.BytesIO()
    assert host.source_transport(config, {'mode': 'export'}, output) is None
    monkeypatch.setattr(host, 'META_LIMIT', 1)
    with pytest.raises(ValueError, match='metadata'):
        host.source_transport(config, {'mode': 'inventory'})
    for seconds in [False, 0, 7201]:
        with pytest.raises(ValueError, match='timeout'):
            host.source_transport({**config, 'source_timeout_seconds': seconds}, {})


def target_config(tmp_path, monkeypatch):
    path = tmp_path / 'app.env'
    path.write_text('PRIVATE=never-read-in-test')
    real_stat = Path.stat
    def root_stat(self, *args, **kwargs):
        result = real_stat(self, *args, **kwargs)
        if self == path:
            return NS(st_uid=0, st_mode=stat.S_IFREG | 0o600)
        return result
    monkeypatch.setattr(Path, 'stat', root_stat)
    return {'maintenance_marker': str(tmp_path / 'maintenance'), 'env_file': str(path),
        'compose_file': str(tmp_path / 'compose.yml'), 'image': 'app:test',
        'target_config': {'runtime_revision': REV}}


def docker_fake(overrides=None):
    calls = []
    overrides = overrides or {}
    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[:3] == ['docker', 'container', 'ls']:
            return overrides.get('containers', b'other-app\n')
        if command[:3] == ['docker', 'image', 'inspect']:
            return overrides.get('label', REV.encode()) if 'revision' in command[-2] else b'sha256:image'
        if 'ps' in command:
            return overrides.get('live', b'container')
        if command[:2] == ['docker', 'inspect']:
            return overrides.get('live_image', b'sha256:image')
        if 'run' in command:
            return overrides.get('result', b'{"applied_batches":1}')
        return b''
    return run, calls


def test_target_command_contract(tmp_path, monkeypatch):
    config = target_config(tmp_path, monkeypatch)
    run, calls = docker_fake()
    assert host.target_run(config, run) == {'applied_batches': 1}
    command, kwargs = calls[-1]
    assert command[-3:] == ['app', 'python', '-']
    assert IMPORT_CONTAINER_IN(command)
    assert kwargs['timeout'] is None
    assert b"'runtime_revision': '" + REV.encode() in kwargs['payload']


def IMPORT_CONTAINER_IN(command):
    return command[command.index('--name') + 1] == 'bravo-aditya-source-import'


@pytest.mark.parametrize('override,match', [
    ({'containers': b'bravo-aditya-source-import\n'}, 'reconciliation'),
    ({'label': b'wrong'}, 'revision'), ({'live': b''}, 'identity'),
    ({'live': b'a\nb'}, 'identity'), ({'live_image': b'wrong'}, 'image'),
])
def test_target_preflight_refuses(tmp_path, monkeypatch, override, match):
    config = target_config(tmp_path, monkeypatch)
    run, calls = docker_fake(override)
    with pytest.raises(ValueError, match=match):
        host.target_run(config, run)
    assert not any('run' in command for command, kwargs in calls)


def test_target_marker_bad_revision_output(tmp_path, monkeypatch):
    config = target_config(tmp_path, monkeypatch)
    marker = Path(config['maintenance_marker'])
    marker.touch()
    with pytest.raises(ValueError, match='maintenance'):
        host.target_run(config, Mock())
    marker.unlink()
    config['target_config']['runtime_revision'] = 'wrong'
    run, _ = docker_fake()
    with pytest.raises(ValueError, match='revision'):
        host.target_run(config, run)
    config['target_config']['runtime_revision'] = REV
    monkeypatch.setattr(host, 'META_LIMIT', 1)
    with pytest.raises(ValueError, match='response'):
        host.target_run(config, run)


def test_target_bad_env(tmp_path):
    env = tmp_path / 'app.env'
    env.write_text('')
    with pytest.raises(ValueError, match='environment'):
        host.target_run({'maintenance_marker': str(tmp_path / 'missing'), 'env_file': str(env)}, Mock())


def test_run_host_roles_identity_and_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(host.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(host.socket, 'gethostname', lambda: 'test.example')
    config = {'hostname': 'test', 'role': 'source', 'lock': str(tmp_path / 'lock')}
    monkeypatch.setattr(host, 'source_run', lambda config: 'source')
    monkeypatch.setattr(host, 'target_run', lambda config: 'target')
    assert host.run_host(config) == 'source'
    assert host.run_host({**config, 'role': 'target'}) == 'target'
    with pytest.raises(ValueError, match='role'):
        host.run_host({**config, 'role': 'invalid'})
    with pytest.raises(ValueError, match='identity'):
        host.run_host({**config, 'hostname': 'wrong'})
    monkeypatch.setattr(host.os, 'geteuid', lambda: 1000)
    with pytest.raises(ValueError, match='identity'):
        host.run_host(config)


def test_main_success_and_sanitized_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['host.py', '--config', '/private/test'])
    monkeypatch.setattr(host, 'private_config', lambda path: {})
    monkeypatch.setattr(host.os, 'umask', Mock())
    monkeypatch.setattr(host, 'run_host', lambda config: {'exported': 3})
    assert host.main() == 0
    assert json.loads(capsys.readouterr().out) == {'exported': 3}
    monkeypatch.setattr(host, 'run_host', Mock(side_effect=ValueError('SECRET')))
    assert host.main() == 1
    assert 'SECRET' not in capsys.readouterr().err


def test_checked_os_output_bound(tmp_path):
    # Actual child process bound: a compromised/malformed stream cannot fill
    # the export disk before the parent gets a chance to inspect its length.
    path = tmp_path / 'bounded-output'
    with open(path, 'wb') as output:
        with pytest.raises(subprocess.CalledProcessError):
            host.checked(['/bin/sh', '-c', 'printf %0100d 0; printf %0100d 0'],
                output=output, file_limit=32)
    assert path.stat().st_size <= 32


def test_optional_clinic_source_hook(tmp_path,monkeypatch):
    config=source_config(tmp_path)
    config['clinic']={'snapshots':'/synthetic'}
    state.atomic_json(config['checkpoint'],CHECKPOINT)
    calls=[]
    def transport(config,request,output=None):
        calls.append(request)
        return {'clinic_inventory':True} if request.get('kind')=='clinic' else {}
    def refresh(private,call,sleep):
        assert private==config['clinic']
        assert call({'mode':'inventory'})=={'clinic_inventory':True}
        return {'published':False}
    monkeypatch.setattr(host.clinic,'refresh_source',refresh)
    report=host.source_run(config,transport,lambda seconds:None)
    assert report['neural']['exported']==0
    assert report['clinic']=={'published':False}
    assert calls[-1]=={'mode':'inventory','kind':'clinic'}


def test_clinic_transport_injects_only_readonly_modules(tmp_path,monkeypatch):
    config={'source_workdir':'/app','source_container':'source','source_config':{},
            'clinic':{'source_folder':'/workbooks','source_participant_uid':C}}
    checked=Mock()
    monkeypatch.setattr(host,'checked',checked)
    output=io.BytesIO()
    host.source_transport(config,{'mode':'export','kind':'clinic'},output)
    kwargs=checked.call_args.kwargs
    assert kwargs['file_limit']==host.clinic.MAX_TOTAL+host.clinic.MAX_FILES*1024+host.clinic.META_LIMIT
    assert b"sys.modules['clinic'].transport(request,output)" in kwargs['payload']
    assert b'configure_reader' not in kwargs['payload']
    compiled=host.bootstrap({'clinic':{}},target=True)
    compile(compiled,'<target-clinic>','exec')
    assert b"sys.modules['clinic'].refresh_target(request)" in compiled


def test_actual_clinic_source_bootstrap_without_django(tmp_path,monkeypatch):
    import resource
    source=tmp_path/'workbooks';source.mkdir()
    (source/'2026_Jan1_clinic.xlsx').write_bytes(b'synthetic-workbook')
    request={'mode':'inventory','config':{'source_folder':str(source),'source_participant_uid':C}}
    payload=host.bootstrap(request,clinic_source=True)
    output=io.BytesIO()
    # Execute the complete generated bootstrap with its actual module imports.
    # Only process resource limits and output are replaced in this local test.
    previous={name:sys.modules.get(name) for name in ('state','clinic')}
    with monkeypatch.context() as patch:
        patch.setattr(resource,'setrlimit',Mock())
        patch.setattr(sys,'stdout',NS(buffer=output))
        exec(compile(payload,'<actual-clinic-bootstrap>','exec'),{})
    for name,value in previous.items():
        if value is None:sys.modules.pop(name,None)
        else:sys.modules[name]=value
    assert json.loads(output.getvalue())['manifest']['count']==1


def test_provider_bootstrap_and_failed_job_receipts_contract(tmp_path, monkeypatch):
    code=host.bootstrap({'providers':{'redcap_enabled':True,'oura_enabled':False}},target=True)
    compile(code,'<provider-bootstrap>','exec')
    assert b"sys.modules['providers'].refresh_target(request)" in code
    config=target_config(tmp_path,monkeypatch)
    run,_=docker_fake({'result':b'{"imports":{"applied_batches":1},"providers":{"failed":true,"redcap":{"status":"success"},"oura":{"status":"failed"}}}'})
    with pytest.raises(ValueError,match='separate private provider receipts'):
        host.target_run(config,run)


@pytest.mark.parametrize('neural_fail,clinic_fail,provider_fail,providers_only,configured',[
    (False,False,False,False,True),(True,False,False,False,True),
    (False,True,False,False,True),(False,False,True,False,True),
    (False,False,False,True,True),(False,False,False,False,False),
])
def test_manual_bootstrap_stream_independence(neural_fail,clinic_fail,provider_fail,providers_only,configured):
    neural=Mock(side_effect=ValueError('private') if neural_fail else None)
    clinic=Mock(side_effect=ValueError('private') if clinic_fail else None)
    providers=Mock(side_effect=ValueError('private') if provider_fail else None,
                   return_value={'redcap':{'status':'success'},'oura':{'status':'success'}})
    modules={'state':state,'target_adapter':NS(execute=neural),'clinic':NS(refresh_target=clinic),'providers':NS(refresh_target=providers)}
    output=io.BytesIO();request={'clinic':{},'providers':{}} if configured else {}
    exec(compile('if True:\n'+host.manual_target_script(providers_only),'<manual-target>','exec'),
         {'sys':NS(modules=modules),'output':output,'request':request})
    result=json.loads(output.getvalue())
    assert b'private' not in output.getvalue()
    if providers_only:
        neural.assert_not_called();clinic.assert_not_called()
        assert result['streams']['neural']['status']=='blocked'
    else:
        assert result['streams']['neural']['status']==('failed' if neural_fail else 'success')
        assert result['streams']['clinic']['status']==('disabled' if not configured else 'failed' if clinic_fail else 'success')
    assert result['providers']['redcap']['status']==('disabled' if not configured else 'failed' if provider_fail else 'success')
    assert providers.call_count==int(configured)
    compile(host.bootstrap(request,target=True,manual=True,providers_only=providers_only),'<full-manual>','exec')


def test_manual_target_preserves_provider_failure_result(tmp_path,monkeypatch):
    config=target_config(tmp_path,monkeypatch)
    run,calls=docker_fake({'result':b'{"streams":{"neural":{"status":"success"}},"providers":{"failed":true}}'})
    result=host.target_run(config,run,manual=True)
    assert result['providers']['failed'] is True

@pytest.mark.parametrize('flags', [{'neural':True}, {'neural':1,'clinic':True}])
def test_manual_source_flags_strict(flags):
    with pytest.raises(ValueError): host.manual_target_script(source_streams=flags)

@pytest.mark.parametrize('available,withheld,broken', [(True,False,False),(True,True,False),(False,False,False),(True,False,True)])
def test_upstream_target_freshness_withholding_and_provider_independence(available,withheld,broken):
    neural=Mock(return_value={'withheld_files':int(withheld),'error_code':'unknown_device'})
    clinic=Mock(return_value={})
    providers=Mock(return_value={'redcap':{'status':'success'},'oura':{'status':'success'}})
    availability=Mock(return_value={'neural':available,'clinic':available},side_effect=ValueError('private') if broken else None)
    modules={'state':state,'upstream_target':NS(execute=neural),'upstream_source':NS(availability=availability),'clinic':NS(refresh_target=clinic),'providers':NS(refresh_target=providers)}
    output=io.BytesIO();request={'upstream':{},'upstream_source_status':'/synthetic','clinic':{},'providers':{}}
    exec(compile('if True:\n'+host.manual_target_script(),'<upstream>','exec'),{'sys':NS(modules=modules),'output':output,'request':request})
    result=json.loads(output.getvalue())
    assert result['streams']['neural']['status']==('blocked' if broken or not available else 'failed' if withheld else 'success')
    assert result['providers']['oura']['status']=='success'
    assert neural.call_count==int(available and not broken)
    compile(host.bootstrap(request,target=True,manual=True),'<upstream-bootstrap>','exec')

@pytest.mark.parametrize('failure', [None,'neural','clinic','both'])
def test_daily_upstream_source_exit_status_after_independent_attempts(tmp_path,monkeypatch,capsys,failure):
    import upstream_source
    monkeypatch.setattr(host.os,'geteuid',lambda:0)
    monkeypatch.setattr(host.socket,'gethostname',lambda:'test')
    monkeypatch.setattr(host.os,'umask',Mock())
    config={'hostname':'test','role':'source','lock':str(tmp_path/'lock'),'upstream':{'owner_uid':10001,'status_path':str(tmp_path/'status'),'dropbox':{},'clinic':{}}}
    monkeypatch.setattr(upstream_source,'write_status',Mock())
    import upstream_dropbox,upstream_clinic
    neural=Mock(return_value={'status':'failed' if failure in ('neural','both') else 'success','manifest_sha256':'a'*64})
    clinic=Mock(return_value={'status':'failed' if failure in ('clinic','both') else 'success','manifest_sha256':'a'*64})
    monkeypatch.setattr(upstream_dropbox,'run',neural);monkeypatch.setattr(upstream_clinic,'refresh',clinic)
    monkeypatch.setattr(host,'private_config',lambda p:config)
    monkeypatch.setattr(sys,'argv',['host.py','--config','/synthetic'])
    assert host.main()==int(failure is not None)
    neural.assert_called_once();clinic.assert_called_once()
    assert 'manifest_sha256' not in capsys.readouterr().err

@pytest.mark.parametrize('stream_status,provider_status', [('success','success'),('blocked','success'),('success','failed')])
def test_daily_upstream_target_status(tmp_path,monkeypatch,stream_status,provider_status):
    config=target_config(tmp_path,monkeypatch);config['target_config']['upstream']={}
    result={'streams':{n:{'status':stream_status} for n in ('neural','clinic')},'providers':{n:{'status':provider_status} for n in ('redcap','oura')}}
    run,_=docker_fake({'result':state.encoded(result)})
    if stream_status==provider_status=='success': assert host.target_run(config,run)==result
    else:
        with pytest.raises(ValueError,match='Upstream stream'): host.target_run(config,run)
