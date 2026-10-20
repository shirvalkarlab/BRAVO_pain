"""Fixed mailbox workers reusing the retained-source and target import pipelines.

Root authority comes only from installed private host configuration. Requests
contain no commands, paths, credentials or selectable participant/stage options.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import socket
import time

try:
    from . import host, state
except ImportError:
    import host
    import state
try:
    from modules import ManualSyncProtocol as protocol
except ImportError:
    import ManualSyncProtocol as protocol

COOLDOWN = 60
MAX_REQUEST_AGE = 24 * 3600


@contextlib.contextmanager
def application_identity(uid):
    old_uid, old_gid = os.geteuid(), os.getegid()
    try:
        os.setegid(uid)
        os.seteuid(uid)
        yield
    finally:
        os.seteuid(old_uid)
        os.setegid(old_gid)


def shared(config, function, *args):
    with application_identity(config['mailbox']['owner_uid']):
        return function(config['mailbox'], *args)


def ledger_read(path):
    path = state.safe_path(path)
    if not path.exists():
        return {'format': 1, 'job_id': None, 'state': 'idle', 'requested_at': 0,
                'started_at': 0, 'last_success_at': None, 'stream_success': {name: None for name in protocol.STREAMS}, 'status': None}
    value = host.private_config(path)
    if set(value) != {'format', 'job_id', 'state', 'requested_at', 'started_at', 'last_success_at', 'stream_success', 'status'} or value['format'] != 1 or value['state'] not in {'idle', 'running', 'succeeded', 'failed'}:
        raise ValueError('Invalid private manual synchronization ledger')
    if value['job_id'] is not None:
        protocol.uid(value['job_id'])
    if set(value['stream_success']) != set(protocol.STREAMS):
        raise ValueError('Invalid private stream ledger')
    if value['status'] is not None:
        protocol.validate_status(value['status'])
    return value


def status_value(config, request, ledger, now, phase='queued', error=None):
    return {'format': 1, 'job_id': request['job_id'], 'state': phase, 'updated_at': now,
            'last_success_at': ledger['last_success_at'], 'streams': {
                name: {'state': phase, 'source_mode': config['mailbox']['source_mode'] if name in ('neural', 'clinic') else 'provider',
                       'last_success_at': ledger['stream_success'][name], 'error_code': error} for name in protocol.STREAMS}}


def publish(config, value):
    shared(config, protocol.write_status, config['role'], value)


def validate_worker(config, runtime):
    if os.geteuid() != 0 or socket.gethostname().split('.')[0] != config['hostname']:
        raise ValueError('Manual synchronization host identity differs')
    if config['role'] not in ('source', 'target') or runtime['role'] != config['role'] or runtime['hostname'] != config['hostname']:
        raise ValueError('Manual synchronization runtime role differs')
    upstream = 'upstream' in (runtime['target_config'] if config['role'] == 'target' else runtime)
    if (config['mailbox']['source_mode'] == 'upstream_files') != upstream:
        raise ValueError('Mailbox source mode differs from installed pipeline')
    shared(config, protocol.validate_config)
    # The source host never gets a selectable target or a caller-supplied source.
    if config['role'] == 'target':
        target = runtime['target_config']
        if (target['target_participant_uid'], target['target_institute_uid']) != (config['mailbox']['target_participant_uid'], config['mailbox']['target_institute_uid']):
            raise ValueError('Manual target binding differs')
    for name in ('ledger', 'worker_lock'):
        path = state.safe_path(config[name])
        if path.parent.stat().st_uid != 0:
            raise ValueError('Worker state parent must be root-owned')


def completed(config, request, ledger, value, now):
    ledger = {**ledger, 'job_id': request['job_id'], 'requested_at': request['requested_at'], 'state': value['state']}
    if config['role'] == 'target':
        for name, detail in value['streams'].items():
            if detail['state'] == 'succeeded':
                ledger['stream_success'][name] = now
                detail['last_success_at'] = now
        if value['state'] == 'succeeded':
            ledger['last_success_at'] = now
            value['last_success_at'] = now
    # Root ledger first: an interrupted status publication can be replayed
    # without silently rerunning a write job.
    ledger['status'] = value
    state.atomic_json(config['ledger'], ledger)
    publish(config, value)
    return {'state': value['state'], 'job_id': request['job_id']}


def target_result(config, request, ledger, now, result):
    value = status_value(config, request, ledger, now, 'succeeded')
    for name in protocol.STREAMS:
        stages = result.get('streams' if name in ('neural', 'clinic') else 'providers', {})
        observed = stages.get(name, {}).get('status', 'disabled')
        mapped = {'success': ('succeeded', None), 'disabled': ('not_configured', 'not_configured'),
                  'failed': ('failed', 'import_failed' if name in ('neural', 'clinic') else 'provider_failed'),
                  'blocked': ('blocked', 'source_failed')}
        if observed not in mapped:
            raise ValueError('Unexpected stream result')
        value['streams'][name]['state'], value['streams'][name]['error_code'] = mapped[observed]
        specific = stages.get(name, {}).get('error_code')
        if specific in ('unknown_device', 'changed_source') and observed == 'failed':
            value['streams'][name]['error_code'] = specific
    if not all(detail['state'] == 'succeeded' for detail in value['streams'].values()):
        value['state'] = 'failed'
    return value


def process(config, now=None):
    now = time.time() if now is None else now
    runtime = host.private_config(config['host_config'])
    validate_worker(config, runtime)
    with host.exclusive_lock(config['worker_lock']):
        request = shared(config, protocol.read_request)
        if request is None:
            return {'state': 'idle'}
        ledger = ledger_read(config['ledger'])
        if request['job_id'] == ledger['job_id']:
            if ledger['state'] == 'running':
                value = status_value(config, request, ledger, now, 'failed', 'worker_unavailable')
                return completed(config, request, ledger, value, now)
            if ledger['status'] is not None:
                publish(config, ledger['status'])
            return {'state': 'already_processed'}
        if request['requested_at'] <= ledger['requested_at'] or not now - MAX_REQUEST_AGE <= request['requested_at'] <= now + 60:
            value = status_value(config, request, ledger, now, 'failed', 'failed')
            publish(config, value)
            return {'state': 'rejected'}
        if config['role'] == 'source' and ledger['job_id'] is not None:
            previous_target = shared(config, protocol.read_status, 'target')
            if previous_target is None or previous_target['job_id'] != ledger['job_id'] or previous_target['state'] not in ('succeeded', 'failed'):
                return {'state': 'waiting_previous_target'}
            ledger['last_success_at'] = previous_target['last_success_at']
            ledger['stream_success'] = {name: previous_target['streams'][name]['last_success_at'] for name in protocol.STREAMS}
        if now - ledger['started_at'] < COOLDOWN:
            return {'state': 'cooldown'}
        source_streams = {'neural': True, 'clinic': True}
        if config['role'] == 'target':
            source = shared(config, protocol.read_status, 'source')
            if source is None or source['job_id'] != request['job_id'] or source['state'] not in ('succeeded', 'failed'):
                return {'state': 'waiting_source'}
            source_streams = {name: source['streams'][name]['state'] == 'exported' for name in ('neural', 'clinic')}
            if state.safe_path(runtime['maintenance_marker']).exists():
                publish(config, status_value(config, request, ledger, now, 'queued', 'maintenance_active'))
                return {'state': 'maintenance'}
        try:
            with host.exclusive_lock(runtime['lock']):
                ledger.update(job_id=request['job_id'], state='running', requested_at=request['requested_at'], started_at=now)
                running = status_value(config, request, ledger, now, 'running')
                if config['role'] == 'source':
                    for name in ('redcap', 'oura'):
                        running['streams'][name]['state'] = 'queued'
                ledger['status'] = running
                state.atomic_json(config['ledger'], ledger)
                publish(config, running)
                try:
                    if config['role'] == 'source':
                        result = host.source_run(runtime)
                        if set(result) != {'neural', 'clinic'}:
                            raise ValueError('Source export incomplete')
                        value = status_value(config, request, ledger, time.time(), 'succeeded')
                        for name in ('neural', 'clinic'):
                            ok = result[name].get('status') == 'success' if 'upstream' in runtime else not result[name].get('deferred', False)
                            value['streams'][name].update(state='exported' if ok else 'failed', error_code=None if ok else 'source_failed')
                            if not ok:
                                value['state'] = 'failed'
                        for name in ('redcap', 'oura'):
                            value['streams'][name]['state'] = 'queued'
                    else:
                        result = host.target_run(runtime, manual=True, source_streams=source_streams)
                        value = target_result(config, request, ledger, time.time(), result)
                except Exception:
                    value = status_value(config, request, ledger, time.time(), 'failed', 'source_failed' if config['role'] == 'source' else 'import_failed')
                    if config['role'] == 'source':
                        for name in ('redcap', 'oura'):
                            value['streams'][name].update(state='queued', error_code=None)
                return completed(config, request, ledger, value, value['updated_at'])
        except BlockingIOError:
            return {'state': 'busy'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--config', required=True); args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(process(host.private_config(args.config)), sort_keys=True))
        return 0
    except Exception:
        print('Manual synchronization worker unavailable; no diagnostic data exposed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
