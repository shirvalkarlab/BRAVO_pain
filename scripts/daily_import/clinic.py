"""Bounded full-folder clinic snapshots; never deserialize a source cache.

Source uses only stdlib filesystem reads. Target parses the received workbooks
with its installed canonical Prasad importer. The caller owns host locks, image
identity, maintenance guards and private output capture.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tarfile
import tempfile
import time
import uuid

try:
    from . import state
except ImportError:
    import state

encoded = state.encoded
digest = state.sha
safe = state.safe_path
fsync_dir = state.sync_directory

MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILES = 256
META_LIMIT = 1024 * 1024


def read(path, limit=MAX_FILE):
    return state.read_bounded(path, limit)


def filename(name):
    if not isinstance(name, str) or '/' in name or '\\' in name or '\x00' in name or not name.endswith('.xlsx') or '_Template_' in name:
        raise ValueError('invalid clinic filename')
    return name


def identity(path):
    info = safe(path).stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE:
        raise ValueError('invalid clinic file size/type')
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def validate_manifest(manifest):
    if type(manifest['format']) is not int or manifest['format'] != 1 or not re.fullmatch('[0-9a-f]{32}', manifest['source_participant_uid']):
        raise ValueError('invalid clinic manifest identity')
    entries = {}
    for item in manifest['files']:
        name = filename(item['file'])
        if name in entries or not re.fullmatch('[0-9a-f]{64}', item['sha256']) or type(item['bytes']) is not int or not 0 < item['bytes'] <= MAX_FILE:
            raise ValueError('invalid clinic manifest entry')
        entries[name] = item
    total = sum(item['bytes'] for item in entries.values())
    if type(manifest['count']) is not int or type(manifest['total_bytes']) is not int or not 0 < len(entries) <= MAX_FILES or manifest['count'] != len(entries) or manifest['total_bytes'] != total or total > MAX_TOTAL:
        raise ValueError('invalid clinic manifest bounds')
    return entries


def folder_files(folder):
    return {filename(path.name) for path in safe(folder).glob('*.xlsx') if '_Template_' not in path.name}


def verify_raw(raw, entry):
    if len(raw) != entry['bytes'] or digest(raw) != entry['sha256']:
        raise ValueError('clinic payload differs from pinned inventory')


def export(config, output):
    manifest = config['manifest']
    entries = validate_manifest(manifest)
    folder = safe(config['source_folder'])
    if folder_files(folder) != set(entries):
        raise ValueError('clinic folder inventory changed')
    before = {name: identity(folder / name) for name in entries}
    with tarfile.open(fileobj=output, mode='w|') as archive:
        for name in sorted(entries):
            raw = read(folder / name)
            verify_raw(raw, entries[name])
            info = tarfile.TarInfo('workbooks/' + name)
            info.size, info.mode, info.mtime = len(raw), 0o600, 0
            archive.addfile(info, io.BytesIO(raw))
        if folder_files(folder) != set(entries) or {name: identity(folder / name) for name in entries} != before:
            raise ValueError('clinic folder changed during export')
        raw = encoded(manifest)
        info = tarfile.TarInfo('clinic.manifest')
        info.size, info.mode, info.mtime = len(raw), 0o600, 0
        archive.addfile(info, io.BytesIO(raw))


def write(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def verify_snapshot(folder, expected):
    entries = validate_manifest(expected)
    folder = safe(folder)
    raw = read(folder / 'clinic.manifest', META_LIMIT)
    if raw != encoded(expected) or read(folder / 'COMPLETE', 65).decode().strip() != digest(raw):
        raise ValueError('clinic snapshot manifest mismatch')
    if {p.name for p in folder.iterdir()} != {'clinic.manifest', 'COMPLETE', 'workbooks'} or {p.name for p in (folder / 'workbooks').iterdir()} != set(entries):
        raise ValueError('clinic snapshot extra/missing files')
    for name, entry in entries.items():
        verify_raw(read(folder / 'workbooks' / name), entry)
    return folder / 'workbooks'


def receive(archive_path, parent, manifest, owner=10001):
    entries = validate_manifest(manifest)
    parent = safe(parent)
    stage = Path(tempfile.mkdtemp(prefix='.pending-clinic-', dir=parent))
    try:
        (stage / 'workbooks').mkdir(mode=0o700)
        seen, received_manifest, total = set(), None, 0
        with tarfile.open(archive_path, 'r|') as archive:
            for info in archive:
                if not info.isfile() or not 0 < info.size <= MAX_FILE:
                    raise ValueError('invalid clinic archive member')
                if info.name == 'clinic.manifest':
                    if received_manifest is not None or info.size > META_LIMIT:
                        raise ValueError('invalid clinic archive manifest')
                    received_manifest = archive.extractfile(info).read()
                    continue
                if not info.name.startswith('workbooks/'):
                    raise ValueError('invalid clinic archive path')
                name = filename(info.name[len('workbooks/'):])
                if name not in entries or name in seen or info.size != entries[name]['bytes']:
                    raise ValueError('unexpected clinic archive file')
                raw = archive.extractfile(info).read()
                total += len(raw)
                if total > MAX_TOTAL:
                    raise ValueError('clinic archive exceeds total bound')
                verify_raw(raw, entries[name])
                write(stage / 'workbooks' / name, raw)
                seen.add(name)
        if seen != set(entries) or received_manifest != encoded(manifest):
            raise ValueError('incomplete clinic archive')
        write(stage / 'clinic.manifest', received_manifest)
        write(stage / 'COMPLETE', (digest(received_manifest) + '\n').encode())
        for path in [*(stage / 'workbooks').iterdir(), stage / 'workbooks', stage / 'clinic.manifest', stage / 'COMPLETE', stage]:
            os.chown(path, owner, owner, follow_symlinks=False)
        fsync_dir(stage / 'workbooks')
        fsync_dir(stage)
        destination = parent / digest(encoded(manifest))
        if destination.exists():
            verify_snapshot(destination, manifest)
        else:
            os.rename(stage, destination)
            fsync_dir(parent)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def accept_canonical(person, workbooks, manifest, clinic, command, assert_frame_equal):
    """Canonical target parse -> command -> exact target-store readback/no-op."""
    expected_steps, expected_manifest = clinic.parse_folder(workbooks, keep_unrated=True)
    entries = validate_manifest(manifest)
    if len(expected_steps) == 0 or set(expected_manifest['file']) != set(entries):
        raise ValueError('clinic parse missing input files or steps')
    if any(bool(value) for value in expected_manifest['error'].fillna('')):
        raise ValueError('clinic parser reported errors')
    for name, rows in expected_steps.groupby('file'):
        if name not in entries or set(rows['sha256']) != {entries[name]['sha256']}:
            raise ValueError('clinic parsed source provenance differs')
    signature = clinic.folder_signature(workbooks)
    command('ingest_clinic_sheets', participant=person.uid, folder=str(workbooks))
    store = clinic._cache_store
    saved = store.load(clinic.CLINIC_PAIN_KIND, person.uid, signature)
    if saved is None:
        raise ValueError('canonical clinic store entry missing')
    assert_frame_equal(saved['steps'], expected_steps, check_exact=True, rtol=0, atol=0)
    assert_frame_equal(saved['manifest'], expected_manifest, check_exact=True, rtol=0, atol=0)
    newest, stamp = store.load_newest(clinic.CLINIC_PAIN_KIND, person.uid)
    expected_key = store.product_key(clinic.CLINIC_PAIN_KIND, person.uid, signature)
    if newest is None or stamp['signature_key'] != store.signature_key(signature):
        raise ValueError('newest clinic product differs')
    assert_frame_equal(newest['steps'], expected_steps, check_exact=True, rtol=0, atol=0)
    before = store.read_stamp(clinic.CLINIC_PAIN_KIND, person.uid, signature)
    repeated = clinic.ingest_and_store(person, workbooks)
    if repeated['written'] is not False or repeated['store_key'] != expected_key or store.read_stamp(clinic.CLINIC_PAIN_KIND, person.uid, signature) != before:
        raise ValueError('canonical clinic retry not idempotent')
    return {'workbook_files': len(entries), 'parsed_steps': len(expected_steps),
        'rated_steps': len(clinic.rated_steps(expected_steps)),
        'clinic_steps': int((expected_steps['setting'] == 'clinic').sum()),
        'home_steps': int((expected_steps['setting'] == 'home').sum()),
        'unparsed_prose': int(expected_manifest['n_unparsed_prose'].sum()),
        'skipped_no_setting': int(expected_manifest['n_skipped_no_setting'].sum()),
        'canonical_store_key': expected_key, 'repeat_wrote': False}


def accept_target(config):
    """Only call inside the isolated accepted target image, under host data lock."""
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from pandas.testing import assert_frame_equal
        from Server import models
        from modules.StimOptimizer import clinic_pain
        database = settings.DATABASES['default']
        if (database['NAME'], database['USER']) != (config['database_name'], config['database_user']) or os.environ['BRAVO_BUILD_REVISION'] != config['runtime_revision']:
            raise ValueError('target clinic runtime mismatch')
        person = models.Participant.objects.get(uid=config['target_participant_uid'], institute_id=config['target_institute_uid'], name=config['participant_name'])
        if person.uid == config['manifest']['source_participant_uid']:
            raise ValueError('source/target participant must be independent')
        workbooks = verify_snapshot(config['snapshot'], config['manifest'])
        report = accept_canonical(person, workbooks, config['manifest'], clinic_pain, call_command, assert_frame_equal)
        verify_snapshot(config['snapshot'], config['manifest'])
        return {**report, 'manifest_sha256': digest(encoded(config['manifest'])), 'runtime_revision': config['runtime_revision']}


def inventory(config):
    """Read only regular XLSX bytes; no Django, parser or cache access."""
    folder = safe(config['source_folder'])
    names = sorted(folder_files(folder))
    if not 0 < len(names) <= MAX_FILES:
        raise ValueError('clinic inventory exceeds bounds')
    first = {name: identity(folder / name) for name in names}
    files = []
    for name in names:
        raw = read(folder / name)
        files.append({'file': name, 'bytes': len(raw), 'sha256': digest(raw)})
    if folder_files(folder) != set(names) or {name: identity(folder / name) for name in names} != first:
        raise ValueError('clinic inventory changed while reading')
    manifest = {'format': 1, 'source_participant_uid': state.uid(config['source_participant_uid']),
                'count': len(files), 'total_bytes': sum(item['bytes'] for item in files), 'files': files}
    validate_manifest(manifest)
    return {'manifest': manifest, 'identities': {name: list(value) for name, value in first.items()}}


def transport(request, output):
    if request['mode'] == 'inventory':
        output.write(encoded(inventory(request['config'])))
    elif request['mode'] == 'export':
        export({**request['config'], 'manifest': request['manifest']}, output)
    else:
        raise ValueError('invalid clinic transport mode')


def current_manifest(config):
    """Source alone may initialize from a separately accepted initial snapshot."""
    parent = safe(config['snapshots'])
    current = parent / 'CURRENT'
    path = current if current.exists() else safe(config['baseline_manifest'])
    manifest = json.loads(read(path, META_LIMIT))
    validate_manifest(manifest)
    if manifest['source_participant_uid'] != state.uid(config['source_participant_uid']):
        raise ValueError('clinic source identity differs')
    verify_snapshot(parent / digest(encoded(manifest)), manifest)
    return manifest


def publish_current(parent, snapshot):
    """Atomically link the app-owned immutable manifest; no unreadable interval."""
    parent = safe(parent)
    current = safe(parent / 'CURRENT')
    temporary = parent / ('.pending-current-' + uuid.uuid4().hex)
    try:
        os.link(safe(snapshot) / 'clinic.manifest', temporary, follow_symlinks=False)
        os.replace(temporary, current)
        fsync_dir(parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def refresh_source(config, call, sleep=time.sleep):
    """Publish complete stable folders; retain history and refuse deletions."""
    interval = config.get('observation_seconds', 5)
    if type(interval) not in (int, float) or not 1 <= interval <= 300:
        raise ValueError('invalid clinic observation interval')
    previous = current_manifest(config)
    before = call({'mode': 'inventory'})
    sleep(interval)
    after = call({'mode': 'inventory'})
    manifest = after['manifest']
    entries = validate_manifest(manifest)
    if manifest['source_participant_uid'] != config['source_participant_uid']:
        raise ValueError('clinic observed source identity differs')
    if not set(validate_manifest(previous)).issubset(entries):
        raise ValueError('clinic files disappeared; reconciliation required')
    if before != after:
        return {'deferred': True, 'published': False, 'workbook_files': len(entries)}
    parent = safe(config['snapshots'])
    snapshot = parent / digest(encoded(manifest))
    published = not snapshot.exists()
    if published:
        if shutil.disk_usage(parent).free < 2 * MAX_TOTAL + META_LIMIT:
            raise ValueError('insufficient clinic snapshot space')
        with tempfile.NamedTemporaryFile(prefix='.pending-clinic-stream-', dir=parent) as stream:
            call({'mode': 'export', 'manifest': manifest}, stream)
            if stream.tell() > MAX_TOTAL + MAX_FILES * 1024 + META_LIMIT:
                raise ValueError('clinic archive stream exceeds bound')
            stream.flush()
            snapshot = receive(stream.name, parent, manifest, config['owner_uid'])
    else:
        verify_snapshot(snapshot, manifest)
    publish_current(parent, snapshot)
    return {'deferred': False, 'published': published, 'workbook_files': len(entries),
            'manifest_sha256': snapshot.name}


def refresh_target(config):
    """Revalidate even on a receipt hit, so lost target products are repaired."""
    from target_adapter import verify_receipt_directory
    private = config['clinic']
    verify_receipt_directory(private['receipts'])
    parent = safe(private['snapshots'])
    manifest = json.loads(read(parent / 'CURRENT', META_LIMIT))
    validate_manifest(manifest)
    if manifest['source_participant_uid'] != state.uid(config['source_participant_uid']):
        raise ValueError('clinic target source identity differs')
    snapshot = parent / digest(encoded(manifest))
    report = accept_target({**config, 'manifest': manifest, 'snapshot': str(snapshot)})
    receipt = {'format': 1, 'source_participant_uid': config['source_participant_uid'],
               'target_participant_uid': config['target_participant_uid'], **report}
    state.atomic_json(safe(private['receipts']) / (snapshot.name + '.json'), receipt)
    return report
