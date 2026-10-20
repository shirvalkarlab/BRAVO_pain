"""Independent upstream fetch coordination and bounded source-freshness evidence.

The original ingest job is never invoked. Only complete successful stream outputs
are published by their adapters; a failed attempt cannot label retained data fresh.
"""
import json
import os
from pathlib import Path
import tempfile
import time

try:
    from . import state
except ImportError:
    import state

STREAMS = ('neural', 'clinic')
MAX_AGE = 24 * 3600


def write_status(path, value, owner):
    path = state.safe_path(path)
    fd, temporary = tempfile.mkstemp(prefix='.pending-upstream-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            os.fchown(stream.fileno(), owner, owner)
            stream.write(state.encoded(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        state.sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def execute(config, functions=None, clock=time.time):
    """Both streams are attempted independently under the existing source lock."""
    if os.geteuid() != 0 or type(config['owner_uid']) is not int or config['owner_uid'] <= 0:
        raise ValueError('Root source coordinator and explicit application owner required')
    if functions is None:
        try:
            from . import upstream_dropbox, upstream_clinic
        except ImportError:
            import upstream_dropbox
            import upstream_clinic
        functions = {'neural': upstream_dropbox.run, 'clinic': upstream_clinic.refresh}
    started = clock()
    report = {'format': 1, 'started_at': started, 'finished_at': None,
              'streams': {name: {'status': 'running'} for name in STREAMS}}
    write_status(config['status_path'], report, config['owner_uid'])
    for name, section in (('neural', 'dropbox'), ('clinic', 'clinic')):
        try:
            result = functions[name](config[section])
            if result.get('status') != 'success' or result.get('deferred') is True:
                raise ValueError('Upstream source incomplete')
            state.digest(result['manifest_sha256'])
            # Private evidence contains only numeric counts, booleans and digests.
            detail = {'status': 'success', 'manifest_sha256': result['manifest_sha256']}
            for key in ('files', 'fresh_files', 'retained_files', 'downloaded_files'):
                if key in result:
                    if type(result[key]) is not int or result[key] < 0:
                        raise ValueError('Invalid upstream counts')
                    detail[key] = result[key]
            report['streams'][name] = detail
        except Exception:
            report['streams'][name] = {'status': 'failed', 'error_code': 'source_failed'}
        write_status(config['status_path'], report, config['owner_uid'])
    report['finished_at'] = clock()
    write_status(config['status_path'], report, config['owner_uid'])
    return report['streams']


def availability(path, now=None):
    """Target-only read: malformed, interrupted or stale fetches are unavailable."""
    now = time.time() if now is None else now
    unavailable = {name: False for name in STREAMS}
    try:
        report = json.loads(state.read_bounded(path, 16384))
        if set(report) != {'format', 'started_at', 'finished_at', 'streams'} or type(report['format']) is not int or report['format'] != 1:
            return unavailable
        start, end = report['started_at'], report['finished_at']
        if type(start) not in (int, float) or type(end) not in (int, float) or not now - MAX_AGE <= start <= end <= now + 60:
            return unavailable
        if set(report['streams']) != set(STREAMS):
            return unavailable
        flags = {}
        for name, detail in report['streams'].items():
            flags[name] = detail.get('status') == 'success'
            if flags[name]:
                state.digest(detail['manifest_sha256'])
        return flags
    except Exception:
        return unavailable
