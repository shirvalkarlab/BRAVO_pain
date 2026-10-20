"""Private retained-source batch state; callers own locks and normal ingestion.

No database/provider access, source writes, deletion, or scientific calculations.
All state belongs in an owner-only, explicitly provisioned directory. An export
checkpoint means published, not imported; the target has separate receipts.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

MAX_FILE = 256 * 1024 * 1024
MAX_FILES = 10000
MAX_TOTAL = 20 * 1024 * 1024 * 1024


def uid(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('invalid identity')
    return value


def digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('invalid digest')
    return value


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path, value):
    """Replace owned state only; fsync file and containing directory."""
    path = safe_path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.state-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def safe_path(path):
    """Require a lexical absolute path without links or parent traversal."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('unsafe retained path')
    return path


def read_bounded(path, limit):
    """Read one immutable regular file with bounded allocation and race checks."""
    path = safe_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    first = os.fstat(descriptor)
    if not stat.S_ISREG(first.st_mode) or not 0 < first.st_size <= limit:
        os.close(descriptor)
        raise ValueError('invalid file bounds')
    with os.fdopen(descriptor, 'rb') as stream:
        raw = stream.read(limit + 1)
        last = os.fstat(stream.fileno())
        current = path.stat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if len(raw) != first.st_size or identity(first) != identity(last) or identity(last) != identity(current):
            raise ValueError('file changed during read')
        return raw


def file_identity(path):
    """No symlink component is allowed, including a substituted parent."""
    path = safe_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 16 <= info.st_size <= 384 * 1024 * 1024:
        raise ValueError('invalid retained file')
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def observation(row, participant, raw_root):
    """Return None for an unfinished row, fail on malformed finalized originals.

    ``row`` is a plain private ORM projection. The adapter must limit the query to
    the explicitly verified source owner and perform no source database writes.
    """
    source = uid(row['uid'])
    if row['owner'] != uid(participant):
        raise ValueError('source owner mismatch')
    if row['type'] != 'MedtronicJSON' or row['upload_type'] != 'MedtronicJSON':
        raise ValueError('unexpected source type')
    expected = safe_path(raw_root) / participant / (source + '.json')
    if Path(row['pointer']) != expected:
        return None
    return {'source_uid': source, 'stored_hash': digest(row['stored_hash']),
            'pointer': str(expected), 'stat': file_identity(expected)}


def manifest_files(manifest, participant):
    if type(manifest['format']) is not int or manifest['format'] != 1 or manifest['source_participant_uid'] != uid(participant):
        raise ValueError('manifest source identity mismatch')
    entries = {}
    for entry in manifest['files']:
        source = uid(entry['source_uid'])
        digest(entry['sha256'])
        if source in entries or entry['path'] != 'sources/' + source + '.json':
            raise ValueError('invalid source provenance')
        if type(entry['bytes']) is not int or not 0 < entry['bytes'] <= MAX_FILE:
            raise ValueError('invalid raw size')
        entries[source] = entry
    total = sum(entry['bytes'] for entry in entries.values())
    if type(manifest['count']) is not int or type(manifest['total_bytes']) is not int or not entries or len(entries) > MAX_FILES or len(entries) != manifest['count'] or total != manifest['total_bytes'] or total > MAX_TOTAL:
        raise ValueError('invalid manifest bounds')
    return entries


def verified_raw(raw, expected=None):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_FILE:
        raise ValueError('invalid raw payload')
    parsed = json.loads(raw)
    if not isinstance(parsed, dict) or not all(k in parsed for k in ('SessionDate', 'DeviceInformation')):
        raise ValueError('not a Percept report')
    if expected is not None and (len(raw), sha(raw)) != (expected['bytes'], expected['sha256']):
        raise ValueError('raw baseline changed')
    return sha(raw)


def baseline(manifest, participant, before, after, load, reobserve):
    """Reauthenticate every baseline payload; never label current inventory seen."""
    entries = manifest_files(manifest, participant)
    result = {}
    for source, entry in entries.items():
        first, second = before.get(source), after.get(source)
        if first is None or first != second:
            raise ValueError('baseline source missing or unstable')
        if second['source_uid'] != source:
            raise ValueError('baseline inventory identity mismatch')
        digest(second['stored_hash'])
        raw_sha = verified_raw(load(source), entry)
        if reobserve(source) != second:
            raise ValueError('baseline source changed during load')
        result[source] = {'stored_hash': second['stored_hash'], 'sha256': raw_sha}
    return {'format': 1, 'source_participant_uid': participant, 'sources': result}


def validate_checkpoint(checkpoint, participant):
    if type(checkpoint['format']) is not int or checkpoint['format'] != 1 or checkpoint['source_participant_uid'] != uid(participant):
        raise ValueError('checkpoint identity mismatch')
    for source, record in checkpoint['sources'].items():
        uid(source)
        digest(record['stored_hash'])
        digest(record['sha256'])


def select(checkpoint, participant, before, after):
    validate_checkpoint(checkpoint, participant)
    chosen, deferred = {}, []
    # Disappearing rows are deferred, never interpreted as deletion requests.
    for source in sorted(set(before) | set(after)):
        uid(source)
        current = after.get(source)
        prior = checkpoint['sources'].get(source)
        for sample in (before.get(source), current):
            if sample is not None:
                if sample['source_uid'] != source:
                    raise ValueError('inventory identity mismatch')
                digest(sample['stored_hash'])
                if prior is not None and prior['stored_hash'] != sample['stored_hash']:
                    raise ValueError('previously published source changed; reconciliation required')
        if current is None or before.get(source) != current:
            deferred.append(source)
        elif prior is None:
            chosen[source] = current
    return chosen, deferred


def validate_batch(directory, participant):
    directory = safe_path(directory)
    payload = read_bounded(directory / 'export.manifest', 16 * 1024 * 1024)
    if read_bounded(directory / 'COMPLETE', 65).decode().strip() != sha(payload):
        raise ValueError('batch completion mismatch')
    manifest = json.loads(payload)
    entries = manifest_files(manifest, participant)
    if set(manifest['fingerprints']) != set(entries):
        raise ValueError('fingerprint inventory mismatch')
    if {p.name for p in directory.iterdir()} != {'export.manifest', 'COMPLETE', 'sources'}:
        raise ValueError('unexpected batch files')
    for source, entry in entries.items():
        digest(manifest['fingerprints'][source])
        path = directory / entry['path']
        verified_raw(read_bounded(path, MAX_FILE), entry)
    if {p.name for p in (directory / 'sources').iterdir()} != {s + '.json' for s in entries}:
        raise ValueError('unexpected batch sources')
    return manifest


def publish(parent, participant, chosen, load, reobserve):
    """Publish atomically; failure leaves no completed batch or advanced state."""
    if not chosen:
        return None
    if len(chosen) > MAX_FILES:
        raise ValueError('batch count exceeds bound')
    parent = safe_path(parent)
    uid(participant)
    stage = Path(tempfile.mkdtemp(prefix='.pending-', dir=parent))
    try:
        (stage / 'sources').mkdir(mode=0o700)
        entries, fingerprints = [], {}
        total = 0
        for source, observed in sorted(chosen.items()):
            uid(source)
            if observed['source_uid'] != source:
                raise ValueError('inventory identity mismatch')
            raw = load(source)
            raw_sha = verified_raw(raw)
            if reobserve(source) != observed:
                raise ValueError('source changed during export')
            total += len(raw)
            if total > MAX_TOTAL:
                raise ValueError('batch size exceeds bound')
            relative = 'sources/' + source + '.json'
            descriptor = os.open(stage / relative, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            entries.append({'source_uid': source, 'path': relative, 'bytes': len(raw), 'sha256': raw_sha})
            fingerprints[source] = digest(observed['stored_hash'])
        manifest = {'format': 1, 'source_participant_uid': uid(participant),
                    'count': len(entries), 'total_bytes': total, 'files': entries,
                    'fingerprints': fingerprints}
        atomic_json(stage / 'export.manifest', manifest)
        # COMPLETE is intentionally the same plain hexadecimal format as the
        # existing reviewed receiver/importer, not a new application protocol.
        with open(stage / 'COMPLETE', 'x') as stream:
            os.chmod(stream.name, 0o600)
            stream.write(sha(encoded(manifest)) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(stage / 'sources')
        sync_directory(stage)
        destination = parent / sha(encoded(manifest))
        if destination.exists():
            if validate_batch(destination, participant) != manifest:
                raise ValueError('published batch conflict')
        else:
            os.rename(stage, destination)
            sync_directory(parent)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def acknowledge_export(checkpoint, manifest):
    """Replay completed batches after crash between publish and checkpoint write."""
    participant = checkpoint['source_participant_uid']
    validate_checkpoint(checkpoint, participant)
    entries = manifest_files(manifest, participant)
    if set(manifest['fingerprints']) != set(entries):
        raise ValueError('fingerprint inventory mismatch')
    updated = json.loads(json.dumps(checkpoint))
    for source, entry in entries.items():
        record = {'stored_hash': digest(manifest['fingerprints'][source]), 'sha256': entry['sha256']}
        prior = updated['sources'].get(source)
        if prior is not None and prior != record:
            raise ValueError('export checkpoint conflicts')
        updated['sources'][source] = record
    return updated


def import_receipt(manifest, source, target, verified, revision):
    """Call only after normal ingest AND authenticated target/provenance checks.

    verified maps every source UID (including aliases) to the raw SHA actually
    decrypted from its target SourceFile and verified saved MigrationSource.
    """
    entries = manifest_files(manifest, source)
    if uid(source) == uid(target) or not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('invalid target identity or runtime')
    expected = {key: value['sha256'] for key, value in entries.items()}
    if verified != expected:
        raise ValueError('incomplete destination acceptance')
    return {'format': 1, 'manifest_sha256': sha(encoded(manifest)),
            'source_participant_uid': source, 'target_participant_uid': target,
            'source_files': len(entries), 'unique_raw_reports': len(set(expected.values())),
            'runtime_revision': revision, 'authenticated_aliases': expected}


def receipt_matches(receipt, manifest, source, target):
    expected = import_receipt(manifest, source, target, receipt['authenticated_aliases'], receipt['runtime_revision'])
    if receipt != expected:
        raise ValueError('applied receipt mismatch')
    return True
