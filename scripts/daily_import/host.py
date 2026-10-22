"""Thin isolated-host runner. Source application receives code only over stdin.

Install helpers root-owned/read-only and private config root:root 0600. Invoke
under systemd; import and backups must share the configured exclusive data lock.
No Dropbox job, original container configuration or source key is modified.
"""
import argparse
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import re
import resource
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

try:
    from . import state, clinic
except ImportError:
    import state
    import clinic

META_LIMIT = 16 * 1024 * 1024
IMPORT_CONTAINER = 'bravo-aditya-source-import'


def private_config(path):
    path = state.safe_path(path)
    info = path.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('configuration must be root-owned mode 0600')
    return json.loads(state.read_bounded(path, 65536))


@contextlib.contextmanager
def exclusive_lock(path):
    path = state.safe_path(path)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def bootstrap(request, target=False, clinic_source=False, manual=False, providers_only=False, source_streams=None):
    """Embed trusted installed modules; never persist scripts inside container."""
    names = ['state', 'clinic'] if clinic_source else ['state', 'source_adapter'] + (['target_adapter'] if target else [])
    if target and 'clinic' in request:
        names.append('clinic')
    if target and 'providers' in request:
        names.append('providers')
    if target and 'upstream' in request:
        names.extend(['native_continuity', 'masked_identity', 'upstream_target', 'upstream_source'])
    modules = {name: state.read_bounded(Path(__file__).resolve().parent / (name + '.py'), 256 * 1024).decode() for name in names}
    return ("import contextlib,os,resource,sys,types\n"
        "resource.setrlimit(resource.RLIMIT_AS,(24*1024**3,24*1024**3))\n"
        "resource.setrlimit(resource.RLIMIT_CPU,(7200,7200))\n"
        "output=sys.stdout.buffer\n"
        "with open(os.devnull,'w') as quiet,contextlib.redirect_stdout(quiet),contextlib.redirect_stderr(quiet):\n"
        " for name,code in " + repr(modules) + ".items():\n"
        "  module=types.ModuleType(name);sys.modules[name]=module;exec(compile(code,name+'.py','exec'),module.__dict__)\n"
        " request=" + repr(request) + "\n" +
        (manual_target_script(providers_only, source_streams) if target and manual else
         " result=sys.modules['target_adapter'].execute(request)\n if 'clinic' in request: result={'neural':result,'clinic':sys.modules['clinic'].refresh_target(request)}\n if 'providers' in request: result={'imports':result,'providers':sys.modules['providers'].refresh_target(request)}\n output.write(sys.modules['state'].encoded(result))\n" if target else
         " sys.modules['clinic'].transport(request,output)\n" if clinic_source else
         " adapter=sys.modules['source_adapter'];adapter.transport(request,adapter.configure_reader(request['config']),output)\n")).encode()


def manual_target_script(providers_only=False, source_streams=None):
    """Isolate upstream/manual stream failures; retained daily defaults stay intact."""
    allowed = {'neural': not providers_only, 'clinic': not providers_only} if source_streams is None else source_streams
    if set(allowed) != {'neural', 'clinic'} or any(type(value) is not bool for value in allowed.values()):
        raise ValueError('Invalid fixed source availability')
    return (" result={'streams':{}}\n source_flags=" + repr(allowed) + "\n"
        " if 'upstream' in request:\n"
        "  try: fresh=sys.modules['upstream_source'].availability(request['upstream_source_status'])\n"
        "  except Exception: fresh={'neural':False,'clinic':False}\n"
        "  source_flags={name:source_flags[name] and fresh[name] for name in source_flags}\n"
        " neural_module='upstream_target' if 'upstream' in request else 'target_adapter'\n"
        " for name,module,function in [('neural',neural_module,'execute'),('clinic','clinic','refresh_target')]:\n"
        "  if not source_flags[name]:\n"
        "   result['streams'][name]={'status':'blocked'};continue\n"
        "  if name=='clinic' and 'clinic' not in request:\n"
        "   result['streams'][name]={'status':'disabled'};continue\n"
        "  try:\n"
        "   report=getattr(sys.modules[module],function)(request)\n"
        "   if name=='neural' and 'upstream' in request and report.get('withheld_files',0):\n"
        "    result['streams'][name]={'status':'failed','error_code':report['error_code']}\n"
        "   else: result['streams'][name]={'status':'success'}\n"
        "  except Exception: result['streams'][name]={'status':'failed'}\n"
        " if 'providers' in request:\n"
        "  try: result['providers']=sys.modules['providers'].refresh_target(request)\n"
        "  except Exception: result['providers']={name:{'status':'failed'} for name in ('redcap','oura')}\n"
        " else: result['providers']={name:{'status':'disabled'} for name in ('redcap','oura')}\n"
        " output.write(sys.modules['state'].encoded(result))\n")


def checked(command, *, payload=None, output=None, timeout=1860, file_limit=None):
    """Suppress runtime diagnostics (which may include private paths/data)."""
    def bound_output():
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
    result = subprocess.run(command, input=payload, stdout=output or subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=timeout, check=True,
        preexec_fn=bound_output if file_limit is not None else None)
    return result.stdout


def source_transport(config, request, output=None):
    # timeout runs inside the existing container, so killing a disconnected
    # docker client cannot leave an unlimited read-only Python process behind.
    seconds = config.get('source_timeout_seconds', 1800)
    if type(seconds) is not int or not 60 <= seconds <= 7200:
        raise ValueError('invalid source timeout')
    command = ['docker', 'exec', '-i', '-w', config['source_workdir'],
        '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'OPENBLAS_NUM_THREADS=1',
        '-e', 'OMP_NUM_THREADS=1', config['source_container'], 'timeout',
        '--signal=TERM', '--kill-after=30', str(seconds), 'python3', '-']
    is_clinic = request.get('kind') == 'clinic'
    payload = bootstrap({**request, 'config': config['clinic'] if is_clinic else config['source_config']}, clinic_source=is_clinic)
    stream_limit = clinic.MAX_TOTAL + clinic.MAX_FILES * 1024 + clinic.META_LIMIT if is_clinic else state.MAX_TOTAL + state.MAX_FILES * 1024 + META_LIMIT
    if output is not None:
        checked(command, payload=payload, output=output, timeout=seconds + 60,
            file_limit=stream_limit)
        return None
    # Inventory/checkpoint responses have a fixed bound, unlike source TARs.
    with tempfile.TemporaryFile() as stream:
        checked(command, payload=payload, output=stream, timeout=seconds + 60, file_limit=META_LIMIT)
        if stream.tell() > META_LIMIT:
            raise ValueError('source metadata exceeds bound')
        stream.seek(0)
        return json.load(stream)


def receive(archive_path, parent, participant, chosen, owner_uid, owner_gid):
    """Strict bounded TAR receiver; publish only validated complete responses."""
    parent = state.safe_path(parent)
    stage = Path(tempfile.mkdtemp(prefix='.pending-', dir=parent))
    try:
        (stage / 'sources').mkdir(mode=0o700)
        seen, manifest, total = {}, None, 0
        with tarfile.open(archive_path, 'r|') as archive:
            for member in archive:
                if not member.isfile() or not 0 < member.size <= state.MAX_FILE:
                    raise ValueError('invalid archive member')
                if member.name == 'export.manifest':
                    if manifest is not None or member.size > META_LIMIT:
                        raise ValueError('invalid archive manifest')
                    manifest = json.load(archive.extractfile(member))
                    continue
                match = re.fullmatch(r'sources/([0-9a-f]{32})\.json', member.name)
                if match is None or member.name in seen or len(seen) >= state.MAX_FILES:
                    raise ValueError('invalid archive source')
                raw = archive.extractfile(member).read()
                total += len(raw)
                if total > state.MAX_TOTAL:
                    raise ValueError('archive total exceeds bound')
                raw_sha = state.verified_raw(raw)
                with open(stage / member.name, 'xb') as stream:
                    os.chmod(stream.name, 0o600)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                seen[member.name] = {'source_uid': match[1], 'path': member.name,
                    'bytes': len(raw), 'sha256': raw_sha}
        if manifest is None:
            raise ValueError('archive manifest missing')
        entries = state.manifest_files(manifest, participant)
        if sorted(manifest['files'], key=lambda e: e['path']) != sorted(seen.values(), key=lambda e: e['path']):
            raise ValueError('archive payload mismatch')
        expected = {uid: state.digest(observed['stored_hash']) for uid, observed in chosen.items()}
        if set(entries) != set(chosen) or manifest['fingerprints'] != expected:
            raise ValueError('archive selection mismatch')
        state.atomic_json(stage / 'export.manifest', manifest)
        with open(stage / 'COMPLETE', 'x') as stream:
            os.chmod(stream.name, 0o600)
            stream.write(state.sha(state.encoded(manifest)) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        # Chown only files created in this fresh stage, before publication. The
        # NFS target's existing application UID can read them immediately.
        for path in [*(stage / 'sources').iterdir(), stage / 'sources',
                     stage / 'export.manifest', stage / 'COMPLETE', stage]:
            os.chown(path, owner_uid, owner_gid, follow_symlinks=False)
        state.sync_directory(stage / 'sources')
        state.sync_directory(stage)
        destination = parent / state.sha(state.encoded(manifest))
        if destination.exists():
            if state.validate_batch(destination, participant) != manifest:
                raise ValueError('published archive conflicts')
        else:
            os.rename(stage, destination)
            state.sync_directory(parent)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def source_run(config, transport=source_transport, sleep=time.sleep):
    if 'upstream' in config:
        try:
            from . import upstream_source
        except ImportError:
            import upstream_source
        return upstream_source.execute(config['upstream'])
    participant = state.uid(config['source_config']['source_participant_uid'])
    checkpoint_path = state.safe_path(config['checkpoint'])
    batches = state.safe_path(config['batches'])
    interval = config.get('observation_seconds', 5)
    if type(interval) not in (int, float) or not 1 <= interval <= 300:
        raise ValueError('invalid observation interval')
    before = transport(config, {'mode': 'inventory'})
    sleep(interval)
    after = transport(config, {'mode': 'inventory'})
    initialized = not checkpoint_path.exists()
    if initialized:
        manifest = json.loads(state.read_bounded(config['baseline_manifest'], META_LIMIT))
        checkpoint = transport(config, {'mode': 'baseline', 'manifest': manifest, 'before': before, 'after': after})
        state.validate_checkpoint(checkpoint, participant)
        state.atomic_json(checkpoint_path, checkpoint)
    else:
        checkpoint = json.loads(state.read_bounded(checkpoint_path, META_LIMIT))
    for batch in sorted(batches.iterdir()):
        if batch.name.startswith('.pending-'):
            continue
        state.digest(batch.name)
        manifest = state.validate_batch(batch, participant)
        if batch.name != state.sha(state.encoded(manifest)):
            raise ValueError('batch directory identity mismatch')
        checkpoint = state.acknowledge_export(checkpoint, manifest)
    chosen, deferred = state.select(checkpoint, participant, before, after)
    if chosen:
        # TAR spool plus fresh publication can each reach MAX_TOTAL. Refuse
        # before reading originals if this dedicated volume cannot hold both.
        if shutil.disk_usage(batches).free < 2 * state.MAX_TOTAL + META_LIMIT:
            raise ValueError('insufficient export space')
        with tempfile.NamedTemporaryFile(prefix='.pending-stream-', dir=batches) as stream:
            transport(config, {'mode': 'export', 'chosen': chosen}, stream)
            if stream.tell() > state.MAX_TOTAL + state.MAX_FILES * 1024 + META_LIMIT:
                raise ValueError('archive size exceeds bound')
            stream.flush()
            manifest = receive(stream.name, batches, participant, chosen, config['owner_uid'], config['owner_gid'])
        checkpoint = state.acknowledge_export(checkpoint, manifest)
    state.atomic_json(checkpoint_path, checkpoint)
    result = {'initialized': initialized, 'inventory': len(after), 'exported': len(chosen), 'deferred': len(deferred)}
    if 'clinic' in config:
        def clinic_call(request, output=None):
            return transport(config, {**request, 'kind': 'clinic'}, output)
        return {'neural': result, 'clinic': clinic.refresh_source(config['clinic'], clinic_call, sleep)}
    return result


def target_run(config, run=checked, manual=False, providers_only=False, source_streams=None):
    marker = state.safe_path(config['maintenance_marker'])
    if marker.exists():
        raise ValueError('backup maintenance active')
    env = state.safe_path(config['env_file'])
    info = env.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('application environment must be root-owned mode 0600')
    # A surviving container means an interrupted invocation still needs review.
    containers = run(['docker', 'container', 'ls', '-a', '--format', '{{.Names}}']).decode().splitlines()
    if IMPORT_CONTAINER in containers:
        raise ValueError('prior import container requires reconciliation')
    revision = config['target_config']['runtime_revision']
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('invalid runtime revision')
    image = config['image']
    label = run(['docker', 'image', 'inspect', '--format', '{{index .Config.Labels "org.opencontainers.image.revision"}}', image]).decode().strip()
    if label != revision:
        raise ValueError('image revision mismatch')
    compose = ['docker', 'compose', '--env-file', str(env), '-f', str(state.safe_path(config['compose_file']))]
    run(compose + ['config', '--quiet'])
    live = run(compose + ['ps', '-q', 'app']).decode().strip()
    if not live or len(live.splitlines()) != 1:
        raise ValueError('live application identity missing')
    live_image = run(['docker', 'inspect', '--format', '{{.Image}}', live]).strip()
    expected_image = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image]).strip()
    if live_image != expected_image:
        raise ValueError('live application image mismatch')
    # No host subprocess timeout: abandoning a live write process would release
    # the shared lock. systemd gives a long grace period and retained container
    # presence blocks subsequent jobs after a forced stop.
    stream_mode = manual or 'upstream' in config['target_config']
    payload = bootstrap(config['target_config'], target=True, manual=stream_mode, providers_only=providers_only, source_streams=source_streams)
    raw = run(compose + ['run', '--rm', '--no-deps', '-T', '--name', IMPORT_CONTAINER,
        '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'BRAVO_INGEST_WARM=0',
        '-e', 'OPENBLAS_NUM_THREADS=1', '-e', 'OMP_NUM_THREADS=1',
        'app', 'python', '-'], payload=payload, timeout=None)
    if len(raw) > META_LIMIT:
        raise ValueError('target response exceeds bound')
    result = json.loads(raw)
    if not manual:
        if result.get('providers', {}).get('failed') is True:
            raise ValueError('Provider stage failed; inspect separate private provider receipts')
        if stream_mode and (any(value.get('status') != 'success' for value in result.get('streams', {}).values()) or any(result.get('providers', {}).get(name, {}).get('status') != 'success' for name in ('redcap', 'oura'))):
            raise ValueError('Upstream stream failed or unavailable; previous data retained')
    return result


def run_host(config):
    if os.geteuid() != 0 or socket.gethostname().split('.')[0] != config['hostname']:
        raise ValueError('host identity mismatch')
    if config['role'] not in ('source', 'target'):
        raise ValueError('invalid role')
    with exclusive_lock(config['lock']):
        result = source_run(config) if config['role'] == 'source' else target_run(config)
        if config['role'] == 'source' and 'upstream' in config and any(
                result.get(name, {}).get('status') != 'success' for name in ('neural', 'clinic')):
            raise ValueError('Upstream source stage failed; inspect separate stream status')
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = run_host(private_config(args.config))
        print(json.dumps(result, sort_keys=True))
    except Exception:
        print('Daily import failed or deferred; retained batches and receipts are unchanged unless fully verified.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
