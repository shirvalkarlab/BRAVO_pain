"""Fixed private mailbox protocol. No commands, credentials, or application imports."""
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from uuid import uuid4

STREAMS = ('neural', 'clinic', 'redcap', 'oura')
STATES = {'queued', 'running', 'exported', 'succeeded', 'failed', 'blocked', 'not_configured'}
ERRORS = {'failed', 'maintenance_active', 'not_configured', 'source_failed', 'import_failed',
          'provider_failed', 'worker_unavailable', 'busy', 'deferred', 'unknown_device', 'changed_source'}
MODES = {'retained_files', 'upstream_files', 'provider'}
LIMIT = 16384

class ProtocolError(ValueError):
    pass


def uid(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ProtocolError('Invalid fixed identity')
    return value


def timestamp(value, nullable=False):
    if nullable and value is None:
        return value
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ProtocolError('Invalid status time')
    return value


def private_path(path, owner, directory=False):
    if not isinstance(path, (str, Path)):
        raise ProtocolError('Invalid private path')
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ProtocolError('Private absolute non-linked paths required')
    info = path.stat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    if not valid or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600) or info.st_uid != owner:
        raise ProtocolError('Unexpected mailbox permissions or owner')
    return path


def validate_config(config):
    required = {'request_directory', 'status_directory', 'target_participant_uid', 'target_institute_uid', 'owner_uid', 'source_mode', 'upstream_available'}
    if not isinstance(config, dict) or set(config) != required:
        raise ProtocolError('Unexpected mailbox configuration')
    uid(config['target_participant_uid']); uid(config['target_institute_uid'])
    if type(config['owner_uid']) is not int or config['owner_uid'] < 0 or not isinstance(config['source_mode'], str) or config['source_mode'] not in {'retained_files', 'upstream_files'} or type(config['upstream_available']) is not bool:
        raise ProtocolError('Invalid mailbox configuration')
    if config['source_mode'] == 'upstream_files' and not config['upstream_available']:
        raise ProtocolError('Upstream mode is not configured')
    for name in ('request_directory', 'status_directory'):
        private_path(config[name], config['owner_uid'], directory=True)
    if Path(config['request_directory']) == Path(config['status_directory']):
        raise ProtocolError('Request and read-only status directories must differ')
    return config


def read_json(path, owner, optional=False):
    if optional and not path.exists() and not path.is_symlink():
        return None
    path = private_path(path, owner)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            raise ProtocolError('Mailbox changed during read')
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ProtocolError('Mailbox payload exceeds bound')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ProtocolError('Malformed mailbox JSON') from None
    if not isinstance(value, dict):
        raise ProtocolError('Mailbox payload must be an object')
    return value


def load_config():
    path = os.environ.get('BRAVO_MANUAL_SYNC_CONFIG_FILE')
    if not path:
        raise ProtocolError('Manual synchronization is not configured')
    path = Path(path)
    owner = path.lstat().st_uid
    if owner not in (0, os.geteuid()):
        raise ProtocolError('Unexpected configuration owner')
    return validate_config(read_json(path, owner))


def validate_request(value, config):
    if not isinstance(value, dict) or set(value) != {'format', 'job_id', 'participant_uid', 'institute_uid', 'requester_uid', 'requested_at'} or type(value['format']) is not int or value['format'] != 1:
        raise ProtocolError('Unexpected sync request')
    for field in ('job_id', 'participant_uid', 'institute_uid', 'requester_uid'):
        uid(value[field])
    timestamp(value['requested_at'])
    if value['participant_uid'] != config['target_participant_uid'] or value['institute_uid'] != config['target_institute_uid']:
        raise ProtocolError('Sync request binding differs')
    return value


def validate_status(value):
    if not isinstance(value, dict) or set(value) != {'format', 'job_id', 'state', 'updated_at', 'last_success_at', 'streams'} or type(value['format']) is not int or value['format'] != 1:
        raise ProtocolError('Unexpected sync status')
    uid(value['job_id']); timestamp(value['updated_at']); timestamp(value['last_success_at'], True)
    if not isinstance(value['state'], str) or value['state'] not in {'queued', 'running', 'succeeded', 'failed'} or not isinstance(value['streams'], dict) or set(value['streams']) != set(STREAMS):
        raise ProtocolError('Invalid synchronization state')
    for stream in value['streams'].values():
        if not isinstance(stream, dict) or set(stream) != {'state', 'source_mode', 'last_success_at', 'error_code'}:
            raise ProtocolError('Unexpected stream status')
        if not isinstance(stream['state'], str) or stream['state'] not in STATES or not isinstance(stream['source_mode'], str) or stream['source_mode'] not in MODES or not (stream['error_code'] is None or isinstance(stream['error_code'], str) and stream['error_code'] in ERRORS):
            raise ProtocolError('Invalid stream status')
        timestamp(stream['last_success_at'], True)
    if value['state'] == 'succeeded' and any(s['state'] not in {'succeeded', 'exported'} for s in value['streams'].values()):
        # Source completion only means exports; its remaining streams may be queued.
        if not (all(value['streams'][s]['state'] == 'exported' for s in ('neural', 'clinic')) and all(value['streams'][s]['state'] == 'queued' for s in ('redcap', 'oura'))):
            raise ProtocolError('Success has incomplete streams')
    return value


def read_request(config):
    validate_config(config)
    value = read_json(Path(config['request_directory']) / 'request.json', config['owner_uid'], True)
    return validate_request(value, config) if value is not None else None


def read_status(config, role):
    if role not in ('source', 'target'):
        raise ProtocolError('Invalid worker role')
    validate_config(config)
    value = read_json(Path(config['status_directory']) / (role + '-status.json'), config['owner_uid'], True)
    return validate_status(value) if value is not None else None


def atomic_json(path, value, owner):
    private_path(path.parent, owner, directory=True)
    if os.geteuid() != owner:
        raise ProtocolError('Mailbox write requires its application identity')
    if path.exists() or path.is_symlink():
        private_path(path, owner)
    raw = (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()
    if len(raw) > LIMIT:
        raise ProtocolError('Mailbox payload exceeds bound')
    fd, tmp = tempfile.mkstemp(prefix='.pending-sync-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(raw); output.flush(); os.fsync(output.fileno())
        os.replace(tmp, path)
        folder = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_status(config, role, value):
    if role not in ('source', 'target'):
        raise ProtocolError('Invalid worker role')
    validate_config(config); validate_status(value)
    atomic_json(Path(config['status_directory']) / (role + '-status.json'), value, config['owner_uid'])


def status(config):
    request = read_request(config)
    if request is None:
        return None
    source, target = (read_status(config, role) for role in ('source', 'target'))
    matching = lambda value: value is not None and value['job_id'] == request['job_id']
    if matching(target):
        if target['state'] == 'succeeded' and any(s['state'] != 'succeeded' for s in target['streams'].values()):
            raise ProtocolError('Target completion requires every imported stream')
        return target
    if matching(source):
        result = json.loads(json.dumps(source))
        if result['state'] in ('succeeded', 'failed'):
            # Source failure still waits for independent target provider attempts.
            result['state'] = 'queued'
            for name in ('redcap', 'oura'):
                result['streams'][name].update(state='queued', error_code=None)
        return result
    return {'format': 1, 'job_id': request['job_id'], 'state': 'queued', 'updated_at': request['requested_at'], 'last_success_at': None,
            'streams': {name: {'state': 'queued', 'source_mode': config['source_mode'] if name in ('neural', 'clinic') else 'provider', 'last_success_at': None, 'error_code': None} for name in STREAMS}}


def submit(config, requester_uid):
    validate_config(config); uid(requester_uid)
    lock = Path(config['request_directory']) / '.request.lock'
    if os.geteuid() != config['owner_uid']:
        raise ProtocolError('Mailbox request requires its application identity')
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        private_path(lock, config['owner_uid'])
        fcntl.flock(fd, fcntl.LOCK_EX)
        current = status(config)
        if current is not None and current['state'] not in ('succeeded', 'failed'):
            return current, False
        request = {'format': 1, 'job_id': uuid4().hex, 'participant_uid': config['target_participant_uid'],
                   'institute_uid': config['target_institute_uid'], 'requester_uid': requester_uid, 'requested_at': time.time()}
        validate_request(request, config)
        atomic_json(Path(config['request_directory']) / 'request.json', request, config['owner_uid'])
        return status(config), True
    finally:
        os.close(fd)
