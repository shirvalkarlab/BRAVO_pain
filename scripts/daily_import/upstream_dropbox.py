"""Bounded read-only Dropbox snapshots using an isolated credential copy.

The root-owned host configuration fixes the remote scope. This producer never
runs or edits the original Dropbox job. Complete snapshots and their cache are
published only after two identical provider inventories and raw content checks.
"""
import configparser
import contextlib
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import resource
import shutil
import subprocess
import tempfile

try:
    from . import state
except ImportError:
    import state

META_LIMIT = 16 * 1024 * 1024
BLOCK_SIZE = 4 * 1024 * 1024
KIND = 'bravo-upstream-percept'


def text(value, maximum=512):
    if not isinstance(value, str) or not 0 < len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise ValueError('invalid upstream metadata')
    return value


def relative(value):
    value = text(value, 4096)
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or value != str(path) or '\\' in value:
        raise ValueError('invalid upstream relative path')
    return value


def content_hash(raw):
    """Dropbox's hash: SHA256 of concatenated 4MiB-block SHA256 digests."""
    return hashlib.sha256(b''.join(hashlib.sha256(raw[i:i + BLOCK_SIZE]).digest()
                                  for i in range(0, len(raw), BLOCK_SIZE))).hexdigest()


def inventory(rows):
    if not isinstance(rows, list) or not 0 < len(rows) <= state.MAX_FILES:
        raise ValueError('upstream inventory count invalid')
    result, paths, total = {}, set(), 0
    for row in rows:
        identity = text(row['ID'])
        path = relative(row['Path'])
        size = row['Size']
        modified = text(row['ModTime'])
        stamp = datetime.fromisoformat(modified.replace('Z', '+00:00'))
        hashes = [value for name, value in row.get('Hashes', {}).items()
                  if name.lower().replace('-', '') in ('dropbox', 'dropboxhash')]
        if row['IsDir'] is not False or not path.lower().endswith('.json') or type(size) is not int or not 0 < size <= state.MAX_FILE or stamp.tzinfo is None or len(hashes) != 1:
            raise ValueError('upstream metadata bounds invalid')
        revision = row.get('Revision', row.get('Rev'))
        if revision is not None:
            text(revision, 256)
        if identity in result or path in paths:
            raise ValueError('repeated upstream identity or path')
        total += size
        if total > state.MAX_TOTAL:
            raise ValueError('upstream inventory total exceeds bound')
        result[identity] = {'provider_id': identity, 'path': path, 'bytes': size,
            'modified': modified, 'revision': revision, 'content_hash': state.digest(hashes[0])}
        paths.add(path)
    return result


class Rclone:
    def __init__(self, binary, remote, isolated_config):
        if not text(remote).startswith('dropbox:'):
            raise ValueError('only the configured Dropbox remote is supported')
        relative(remote.split(':', 1)[1])
        self.binary, self.remote, self.config = str(state.safe_path(binary)), remote, str(isolated_config)

    def command(self, operation, suffix=None):
        remote = self.remote if suffix is None else self.remote + '/' + relative(suffix)
        return [self.binary, operation, remote, '--config', self.config,
            '--contimeout', '15s', '--timeout', '60s', '--retries', '1', '--low-level-retries', '1']

    def execute(self, command, limit, timeout):
        def bound():
            resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
        with tempfile.TemporaryFile() as output:
            subprocess.run(command, stdout=output, stderr=subprocess.DEVNULL,
                           timeout=timeout, check=True, preexec_fn=bound,
                           env={'PATH': os.defpath, 'HOME': str(Path(self.config).parent), 'LANG': 'C.UTF-8'})
            if output.tell() > limit:
                raise ValueError('upstream command output exceeds bound')
            output.seek(0)
            return output.read(limit + 1)

    def inventory(self):
        command = self.command('lsjson') + ['--recursive', '--files-only', '--hash', '--include', '*.json']
        return inventory(json.loads(self.execute(command, META_LIMIT, 180)))

    def download(self, metadata):
        return self.execute(self.command('cat', metadata['path']), metadata['bytes'], 600)


@contextlib.contextmanager
def isolated_client(config):
    original = state.safe_path(config['rclone_config'])
    original_raw = state.read_bounded(original, 1024 * 1024)
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(original_raw.decode())
    if parser.get('dropbox', 'type') != 'dropbox':
        raise ValueError('configured remote is not Dropbox')
    scoped = configparser.ConfigParser(interpolation=None)
    scoped['dropbox'] = dict(parser['dropbox'])
    try:
        with tempfile.TemporaryDirectory(prefix='bravo-dropbox-') as directory:
            isolated = Path(directory) / 'rclone.conf'
            with isolated.open('x') as output:
                os.fchmod(output.fileno(), 0o600)
                scoped.write(output)
            yield Rclone(config['rclone_binary'], config['remote'], isolated)
    finally:
        if state.read_bounded(original, 1024 * 1024) != original_raw:
            raise ValueError('original Dropbox configuration changed')


def read_checkpoint(path, scope):
    path = state.safe_path(path)
    if not path.exists():
        return {}
    saved = json.loads(state.read_bounded(path, META_LIMIT))
    if set(saved) != {'format', 'scope', 'files'} or type(saved['format']) is not int or saved['format'] != 1 or saved['scope'] != scope or not isinstance(saved['files'], dict) or len(saved['files']) > state.MAX_FILES:
        raise ValueError('upstream checkpoint identity mismatch')
    for identity, entry in saved['files'].items():
        if set(entry) != {'metadata', 'batch', 'sha256'} or entry['metadata']['provider_id'] != identity:
            raise ValueError('upstream checkpoint entry mismatch')
        text(identity)
        state.digest(entry['batch'])
        state.digest(entry['sha256'])
    return saved['files']


def write_payload(path, raw):
    with path.open('xb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def snapshot(config, client):
    """Caller owns the non-overlap lock; failures preserve prior checkpoints."""
    scope = text(config['scope'])
    parent = state.safe_path(config['batches'])
    owner = config['owner_uid']
    if type(owner) is not int or owner <= 0:
        raise ValueError('published batch owner must be a non-root UID')
    if shutil.disk_usage(parent).free < 2 * state.MAX_TOTAL + META_LIMIT:
        raise ValueError('insufficient private staging reserve')
    before = client.inventory()
    cache = read_checkpoint(config['checkpoint'], scope)
    stage = Path(tempfile.mkdtemp(prefix='.pending-', dir=parent))
    entries, pending_cache, written, downloaded = [], {}, set(), 0
    try:
        (stage / 'sources').mkdir(mode=0o700)
        for identity, metadata in sorted(before.items()):
            prior = cache.get(identity)
            if prior is not None and prior['metadata'] == metadata:
                source = parent / prior['batch'] / 'sources' / (prior['sha256'] + '.json')
                raw = state.read_bounded(source, state.MAX_FILE)
                if state.sha(raw) != prior['sha256']:
                    raise ValueError('cached upstream payload changed')
            else:
                raw = client.download(metadata)
                downloaded += 1
            digest = state.verified_raw(raw)
            if len(raw) != metadata['bytes'] or content_hash(raw) != metadata['content_hash']:
                raise ValueError('upstream download identity mismatch')
            relative_path = 'sources/' + digest + '.json'
            if digest not in written:
                write_payload(stage / relative_path, raw)
                written.add(digest)
            entries.append({'provider_id': identity, 'revision': metadata['revision'],
                'provider_modified_at': metadata['modified'], 'path': relative_path,
                'sha256': digest, 'bytes': len(raw)})
            pending_cache[identity] = {'metadata': metadata, 'sha256': digest}
        if client.inventory() != before:
            raise ValueError('upstream inventory changed during snapshot; retry required')
        manifest = {'format': 1, 'kind': KIND, 'provider': 'dropbox', 'scope': scope,
            'count': len(entries), 'total_bytes': sum(e['bytes'] for e in entries), 'files': entries}
        payload = state.encoded(manifest)
        digest = state.sha(payload)
        write_payload(stage / 'upstream.manifest', payload)
        write_payload(stage / 'COMPLETE', (digest + '\n').encode())
        for path in [*(stage / 'sources').iterdir(), stage / 'sources', stage / 'upstream.manifest', stage / 'COMPLETE', stage]:
            os.chown(path, owner, owner, follow_symlinks=False)
        state.sync_directory(stage / 'sources')
        state.sync_directory(stage)
        destination = parent / digest
        unchanged = destination.exists()
        if unchanged:
            # Match all payloads, not merely a forged completion marker.
            state.safe_path(destination)
            if {p.name for p in destination.iterdir()} != {'sources', 'upstream.manifest', 'COMPLETE'} or state.read_bounded(destination / 'upstream.manifest', META_LIMIT) != payload or state.read_bounded(destination / 'COMPLETE', 65) != (digest + '\n').encode() or {p.name for p in (destination / 'sources').iterdir()} != {d + '.json' for d in written}:
                raise ValueError('upstream published snapshot conflicts')
            for entry in entries:
                state.verified_raw(state.read_bounded(destination / entry['path'], state.MAX_FILE), entry)
        else:
            os.rename(stage, destination)
            state.sync_directory(parent)
        checkpoint = {'format': 1, 'scope': scope, 'files': {
            identity: dict(value, batch=digest) for identity, value in pending_cache.items()}}
        state.atomic_json(config['checkpoint'], checkpoint)
        return {'status': 'success', 'manifest_sha256': digest, 'files': len(entries),
                'downloaded_files': downloaded, 'unchanged': unchanged}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def run(config):
    with isolated_client(config) as client:
        return snapshot(config, client)
