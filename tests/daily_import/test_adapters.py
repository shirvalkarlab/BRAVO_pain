"""Synthetic adapter contracts: no providers, real source or live databases."""
import contextlib
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts' / 'daily_import'
sys.path.insert(0, str(SCRIPTS))
import state
import source_adapter as source
import target_adapter as target

A, B, C, D = (x * 32 for x in 'abcd')
REV = 'e' * 40
RAW = b'{"SessionDate":"2026-01-01T00:00:00Z","DeviceInformation":{}}'
SHA = hashlib.sha256(RAW).hexdigest()


@pytest.fixture(autouse=True)
def private_test_hash_key(monkeypatch):
    monkeypatch.setenv('DATASERVER_HASHKEY', 'synthetic-key')


def entry(uid=A):
    return {'source_uid': uid, 'path': 'sources/' + uid + '.json', 'bytes': len(RAW), 'sha256': SHA}


def batch(tmp_path, aliases=(A, B)):
    root = tmp_path / 'batches'
    root.mkdir(exist_ok=True)
    chosen = {uid: {'source_uid': uid, 'stored_hash': 'f' * 64} for uid in aliases}
    return state.publish(root, C, chosen, lambda uid: RAW, lambda uid: chosen[uid])


def stored(path, raw=RAW):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'HEAD' + struct.pack('<III', 100, 0, 16))
    return NS(pointer=str(path), uid=A, owner_id=C, type='MedtronicJSON', hashed=hmac.new(b'synthetic-key', path.read_bytes(), hashlib.sha256).hexdigest(),
              metadata={'UploadType': 'MedtronicJSON', 'ChronicScheduleRestamp': {'status': 'complete', 'exports_without_record': 0, 'rule_version': 'complete-owner-bound-schedule-v1', 'configuration_digest': 'clinical-config-unavailable-v1', 'inventory_digest': 'a'*64}})


def test_bounded_load(tmp_path):
    row = stored(tmp_path / 'raw')
    assert source.bounded_load(row, lambda r: RAW) == RAW
    for token, length in [(99, 16), (100, 17), (state.MAX_FILE * 4, 16)]:
        Path(row.pointer).write_bytes(b'HEAD' + struct.pack('<III', token, 0, length))
        row.hashed = hmac.new(b'synthetic-key', Path(row.pointer).read_bytes(), hashlib.sha256).hexdigest()
        with pytest.raises(ValueError):
            source.bounded_load(row, lambda r: RAW)


def test_source_reader(tmp_path, monkeypatch):
    row = stored(tmp_path / C / (A + '.json'))
    query = Mock()
    query.order_by.return_value = [row]
    manager = NS(get=Mock(return_value=row), filter=Mock(return_value=query))
    reader = source.SourceReader(NS(SourceFile=NS(objects=manager)), lambda r: RAW, C, tmp_path)
    assert reader.inventory()[A] == reader.reobserve(A)
    assert reader.load(A) == RAW
    assert manager.get.call_args.kwargs == {'uid': A, 'owner_id': C, 'type': 'MedtronicJSON'}
    row.pointer = str(tmp_path / 'cache')
    with pytest.raises(ValueError, match='no longer finalized'):
        reader.load(A)
    monkeypatch.setattr(state, 'MAX_FILES', 0)
    with pytest.raises(ValueError, match='inventory'):
        reader.inventory()


def test_refresh_baseline_incremental_replay(tmp_path):
    batches = tmp_path / 'batches'; batches.mkdir()
    initial = {'format': 1, 'source_participant_uid': C, 'count': 1, 'total_bytes': len(RAW), 'files': [entry()]}
    baseline = tmp_path / 'baseline'; baseline.write_text(json.dumps(initial))
    observation = {'source_uid': A, 'stored_hash': 'f' * 64}
    inventory = {A: observation}
    reader = NS(inventory=lambda: inventory.copy(), load=lambda uid: RAW, reobserve=lambda uid: inventory[uid])
    config = {'source_participant_uid': C, 'checkpoint': str(tmp_path / 'checkpoint'),
              'batches': str(batches), 'baseline_manifest': str(baseline)}
    assert source.refresh(config, reader, lambda n: None)['initialized']
    inventory[B] = {'source_uid': B, 'stored_hash': 'e' * 64}
    result = source.refresh(config, reader, lambda n: None)
    assert result['exported'] == 1
    (batches / '.pending-abandoned').mkdir()
    assert source.refresh(config, reader, lambda n: None)['exported'] == 0
    for value in [0, 301, '5']:
        with pytest.raises(ValueError, match='interval'):
            source.refresh({**config, 'observation_seconds': value}, reader)


@pytest.mark.parametrize('prior', [None, {'participant_uid': C, 'source_uid': D, 'raw_sha256': SHA},
    {'participant_uid': C, 'source_uids': [D], 'raw_sha256': SHA}])
def test_provenance(prior):
    result = target.merge_provenance(prior, C, [entry(B), entry(A)])
    assert set(result['source_uids']) == ({A, B, D} if prior else {A, B})


@pytest.mark.parametrize('prior', [
    {'participant_uid': A, 'raw_sha256': SHA}, {'participant_uid': C, 'raw_sha256': '0' * 64},
    {'participant_uid': C, 'raw_sha256': SHA, 'source_uids': []},
    {'participant_uid': C, 'raw_sha256': SHA, 'source_uids': 'invalid'},
    {'participant_uid': C, 'raw_sha256': SHA, 'source_uids': ['invalid']}])
def test_bad_provenance(prior):
    with pytest.raises(ValueError): target.merge_provenance(prior, C, [entry()])


class Runtime:
    def __init__(self):
        self.person = NS(uid=D)
        self.rows = {}
        self.fail_ingest = self.fail_save = False
    def existing(self, digest): return self.rows.get(digest)
    def verify(self, row, item):
        if row.bad: raise ValueError('raw corrupt')
    def ingest(self, root, groups):
        for digest in groups:
            if not self.fail_ingest: self.rows.setdefault(digest, NS(metadata={}, bad=False))
    def save_provenance(self, updates):
        if not self.fail_save:
            for row, prov in updates: row.metadata['MigrationSource'] = prov


def test_apply_retry_and_aliases(tmp_path):
    path = batch(tmp_path)
    runtime = Runtime()
    receipt = target.apply_batch(path, C, D, REV, b'key', runtime)
    assert receipt['source_files'] == 2 and receipt['unique_raw_reports'] == 1
    assert target.apply_batch(path, C, D, REV, b'key', runtime) == receipt
    assert next(iter(runtime.rows.values())).metadata['MigrationSource']['source_uids'] == [A, B]
    next(iter(runtime.rows.values())).bad = True
    with pytest.raises(ValueError, match='corrupt'):
        target.apply_batch(path, C, D, REV, b'key', runtime)


def test_apply_fails_without_receipt(tmp_path):
    path = batch(tmp_path)
    runtime = Runtime(); runtime.fail_ingest = True
    with pytest.raises(ValueError, match='every source'): target.apply_batch(path, C, D, REV, b'key', runtime)
    runtime.fail_ingest = False; runtime.fail_save = True
    with pytest.raises(ValueError, match='readback'): target.apply_batch(path, C, D, REV, b'key', runtime)
    with pytest.raises(ValueError, match='participant'): target.apply_batch(path, C, B, REV, b'key', runtime)


def test_target_runtime(tmp_path, monkeypatch):
    app = Path(__file__).resolve().parents[2] / "BRAVO"
    monkeypatch.syspath_prepend(str(app))
    row = stored(tmp_path / D / (A + '.json')); row.owner_id = D
    row.save = Mock()
    query = Mock(); query.exclude.return_value.exists.return_value = False
    query.count.return_value = 1; query.first.return_value = row
    model = NS(SourceFile=NS(objects=NS(filter=Mock(return_value=query))))
    calls = []
    def command(name, **kwargs):
        paths = list(Path(kwargs['folder']).glob('*.json'))
        assert len(paths) == 1 and paths[0].read_bytes() == RAW
        calls.append((name, kwargs['participant'], kwargs['dry_run']))
    runtime = target.TargetRuntime(model, lambda r: RAW, command, contextlib.nullcontext,
                                   NS(uid=D, institute_id=C), tmp_path)
    runtime.schedule_inventory_digest = lambda row: "a"*64
    assert runtime.existing('x') is row
    runtime.verify(row, entry())
    path = batch(tmp_path)
    groups = target.group_sources(path, state.validate_batch(path, C), b'key')
    runtime.ingest(path, groups)
    assert calls == [('ingest_percept_folder', D, False)]
    runtime.save_provenance([(row, {'test': True})]); row.save.assert_called_once_with(update_fields=['metadata'])
    query.count.return_value = 2
    with pytest.raises(ValueError, match='ambiguous'): runtime.existing('x')
    query.exclude.return_value.exists.return_value = True
    with pytest.raises(ValueError, match='another'): runtime.existing('x')
    row.type = 'Other'
    with pytest.raises(ValueError, match='incomplete'): runtime.verify(row, entry())
    row.type = 'MedtronicJSON'; row.pointer = str(tmp_path / 'cache')
    with pytest.raises(ValueError, match='incomplete'): runtime.verify(row, entry())


def test_run_receipt_skip_and_failure(tmp_path):
    path = batch(tmp_path)
    receipts = tmp_path / 'receipts'; receipts.mkdir(mode=0o700)
    (path.parent / '.pending-test').mkdir()
    config = {'source_participant_uid': C, 'target_participant_uid': D, 'runtime_revision': REV,
              'batches': str(path.parent), 'receipts': str(receipts)}
    runtime = Runtime()
    assert target.run(config, runtime, b'key', REV)['applied_batches'] == 1
    assert target.run(config, runtime, b'key', REV)['already_applied_batches'] == 1
    with pytest.raises(ValueError, match='revision'): target.run(config, runtime, b'key', '0' * 40)


def test_digest_collision_refused(tmp_path, monkeypatch):
    path = batch(tmp_path)
    manifest = state.validate_batch(path, C)
    manifest['files'][1]['sha256'] = '0' * 64
    monkeypatch.setattr(state, 'verified_raw', lambda *a: None)
    with pytest.raises(ValueError, match='raw identity'): target.group_sources(path, manifest, b'key')


def configure_main(monkeypatch, tmp_path, adapter, override=None):
    import types
    config = {'source_participant_uid': C, 'target_participant_uid': D,
        'target_institute_uid': B, 'participant_name': 'Synthetic',
        'database_name': 'isolated', 'database_user': 'isolated',
        'raw_root': str(tmp_path / 'raws')}
    config.update(override or {})
    file = tmp_path / 'config'; file.write_text(json.dumps(config))
    person = NS(uid=C if adapter is source else D, name='Synthetic', institute_id=B)
    model = NS(Participant=NS(objects=NS(get=lambda **kwargs: person)))
    monkeypatch.setitem(sys.modules, 'django', NS(setup=lambda: None))
    monkeypatch.setitem(sys.modules, 'django.conf', NS(settings=NS(DATABASES={'default': {'NAME': 'isolated', 'USER': 'isolated'}})))
    monkeypatch.setitem(sys.modules, 'django.core.management', NS(call_command=Mock()))
    monkeypatch.setitem(sys.modules, 'django.db', NS(transaction=NS(atomic=contextlib.nullcontext)))
    monkeypatch.setitem(sys.modules, 'Server', NS(models=model))
    monkeypatch.setitem(sys.modules, 'modules', NS(DataCurator=NS(loadCacheFile=lambda row: RAW)))
    monkeypatch.setenv('DATASERVER_PATH', str(tmp_path))
    monkeypatch.setenv('DATASERVER_HASHKEY', 'synthetic-key')
    monkeypatch.setenv('BRAVO_BUILD_REVISION', REV)
    monkeypatch.setattr(sys, 'argv', ['adapter', '--config', str(file)])
    return config, person


def test_main_source(monkeypatch, tmp_path, capsys):
    config, person = configure_main(monkeypatch, tmp_path, source)
    monkeypatch.setattr(source, 'refresh', lambda *a: {'exported': 0})
    source.main()
    assert json.loads(capsys.readouterr().out) == {'exported': 0}
    person.name = 'Wrong'
    with pytest.raises(ValueError, match='identity'): source.main()
    person.name = 'Synthetic'; monkeypatch.setenv('DATASERVER_PATH', str(tmp_path / 'other'))
    with pytest.raises(ValueError, match='root'): source.main()


def test_main_target(monkeypatch, tmp_path, capsys):
    configure_main(monkeypatch, tmp_path, target)
    monkeypatch.setattr(target, 'run', lambda *a: {'applied_batches': 0})
    target.main()
    assert json.loads(capsys.readouterr().out) == {'applied_batches': 0}
    monkeypatch.setenv('DATASERVER_PATH', str(tmp_path / 'other'))
    with pytest.raises(ValueError, match='root'): target.main()
    configure_main(monkeypatch, tmp_path, target, {'database_name': 'wrong'})
    with pytest.raises(ValueError, match='database'): target.main()


def test_batch_name_binding(tmp_path):
    path = batch(tmp_path)
    path.rename(path.parent / ('0' * 64))
    config = {'source_participant_uid': C, 'target_participant_uid': D, 'runtime_revision': REV,
              'batches': str(path.parent), 'receipts': str(tmp_path)}
    with pytest.raises(ValueError, match='directory identity'): target.run(config, Runtime(), b'key', REV)
    config.update(checkpoint=str(tmp_path / 'checkpoint'))
    state.atomic_json(config['checkpoint'], {'format': 1, 'source_participant_uid': C, 'sources': {}})
    reader = NS(inventory=lambda: {})
    with pytest.raises(ValueError, match='directory identity'): source.refresh(config, reader, lambda n: None)


def test_entrypoints_fail_sanitized(monkeypatch, tmp_path, capsys):
    import runpy
    monkeypatch.setattr(sys, 'argv', ['adapter', '--config', str(tmp_path / 'missing')])
    for name in ['source_adapter.py', 'target_adapter.py']:
        with pytest.raises(SystemExit) as error: runpy.run_path(str(SCRIPTS / name), run_name='__main__')
        assert error.value.code == 1
    out = capsys.readouterr()
    assert 'failed' in out.err and str(tmp_path) not in out.err


def test_normal_command_canonical_order(tmp_path, monkeypatch):
    """Execute the actual management command's classification/order/ingest loop."""
    import types
    app = Path(__file__).resolve().parents[2] / 'BRAVO'
    loaded = []
    raws = {
        A: b'{"SessionDate":"2026-02-01T00:00:00Z","DeviceInformation":{}}',
        B: RAW,
    }
    root = tmp_path / 'input'
    groups = {}
    for uid, raw in raws.items():
        batch_root = root / uid
        (batch_root / 'sources').mkdir(parents=True)
        (batch_root / 'sources' / (uid + '.json')).write_bytes(raw)
        groups[uid] = [{'source_uid': uid, 'path': 'sources/' + uid + '.json', '_root': str(batch_root)}]
    person = NS(uid=D, institute=NS(pk=C))
    def save(name, metadata, raw):
        loaded.append(json.loads(raw)['SessionDate'])
        return NS(save=lambda: None)
    models = NS(Participant=NS(find=lambda uid: person),
                SourceFile=NS(objects=NS(filter=lambda **kw: NS(exists=lambda: False))))
    monkeypatch.setitem(sys.modules, 'Server', NS(models=models))
    monkeypatch.setitem(sys.modules, 'modules', NS(DataCurator=NS(saveCacheFile=save, MedtronicPerceptJSONDecoder=lambda *a, **kw: None)))
    spec = importlib.util.spec_from_file_location('modules.MedtronicPercept.session_order', app / 'modules/MedtronicPercept/session_order.py')
    ordering = importlib.util.module_from_spec(spec); spec.loader.exec_module(ordering)
    monkeypatch.setitem(sys.modules, 'modules.MedtronicPercept.session_order', ordering)
    spec = importlib.util.spec_from_file_location('modules.MedtronicPercept.ingest_batch', app / 'modules/MedtronicPercept/ingest_batch.py')
    batching = importlib.util.module_from_spec(spec); spec.loader.exec_module(batching)
    monkeypatch.setitem(sys.modules, 'modules.MedtronicPercept.ingest_batch', batching)
    monkeypatch.setenv('DATASERVER_HASHKEY', 'synthetic')
    spec = importlib.util.spec_from_file_location('actual_daily_ingestion_command', app / 'Server/management/commands/ingest_percept_folder.py')
    command = importlib.util.module_from_spec(spec); spec.loader.exec_module(command)
    def invoke(name, **kwargs): command.Command().handle(**kwargs, limit=0, continue_on_error=False)
    runtime = target.TargetRuntime(models, None, invoke, contextlib.nullcontext, person, tmp_path)
    runtime.ingest(root, groups)
    assert loaded == ['2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z']


def test_source_transport(tmp_path, monkeypatch):
    import io
    import tarfile
    observed = {'source_uid': A, 'stored_hash': 'f' * 64}
    reader = NS(participant=C, inventory=lambda: {A: observed}, reobserve=lambda uid: observed, load=lambda uid: RAW)
    output = io.BytesIO(); source.transport({'mode': 'inventory'}, reader, output)
    assert json.loads(output.getvalue()) == {A: observed}
    manifest = {'format': 1, 'source_participant_uid': C, 'count': 1, 'total_bytes': len(RAW), 'files': [entry()]}
    output = io.BytesIO(); source.transport({'mode': 'baseline', 'manifest': manifest, 'before': {A: observed}, 'after': {A: observed}}, reader, output)
    assert json.loads(output.getvalue())['sources'][A]['sha256'] == SHA
    output = io.BytesIO(); source.transport({'mode': 'export', 'chosen': {A: observed}}, reader, output)
    with tarfile.open(fileobj=io.BytesIO(output.getvalue())) as archive:
        assert archive.extractfile('sources/' + A + '.json').read() == RAW
        exported = json.load(archive.extractfile('export.manifest'))
        assert exported['fingerprints'] == {A: 'f' * 64}
    for req in [{'mode': 'other'}, {'mode': 'export', 'chosen': {}}, {'mode': 'export', 'chosen': []}]:
        with pytest.raises(ValueError): source.transport(req, reader, io.BytesIO())
    reader.reobserve = lambda uid: None
    with pytest.raises(ValueError, match='before'): source.transport({'mode': 'export', 'chosen': {A: observed}}, reader, io.BytesIO())
    sequence = iter([observed, None]); reader.reobserve = lambda uid: next(sequence)
    with pytest.raises(ValueError, match='during'): source.transport({'mode': 'export', 'chosen': {A: observed}}, reader, io.BytesIO())
    reader.reobserve = lambda uid: observed
    monkeypatch.setattr(state, 'MAX_TOTAL', 1)
    with pytest.raises(ValueError, match='total'): source.transport({'mode': 'export', 'chosen': {A: observed}}, reader, io.BytesIO())


def test_transport_main(monkeypatch, tmp_path, capsys):
    import io
    config, _ = configure_main(monkeypatch, tmp_path, source)
    monkeypatch.setattr(sys, 'argv', ['adapter', '--transport'])
    monkeypatch.setattr(sys, 'stdin', NS(buffer=io.BytesIO(json.dumps({'config': config, 'mode': 'inventory'}).encode())))
    monkeypatch.setattr(source.SourceReader, 'inventory', lambda self: {})
    source.main()
    assert json.loads(capsys.readouterr().out) == {}
    monkeypatch.setattr(sys, 'stdin', NS(buffer=io.BytesIO(b' ' * (16 * 1024 * 1024 + 1))))
    with pytest.raises(ValueError, match='request'): source.main()


def test_combined_pending_batches_one_ingest_and_receipts(tmp_path):
    parent = tmp_path / 'batches'; parent.mkdir()
    paths = []
    for uid, raw in [(A, RAW), (B, RAW.replace(b'01-01', b'02-01')), (D, RAW)]:
        observed = {'source_uid': uid, 'stored_hash': 'f' * 64}
        paths.append(state.publish(parent, C, {uid: observed}, lambda _: raw, lambda _: observed))
    receipts = tmp_path / 'receipts'; receipts.mkdir(mode=0o700)
    config = {'source_participant_uid': C, 'target_participant_uid': D, 'runtime_revision': REV,
              'batches': str(parent), 'receipts': str(receipts)}
    runtime = Runtime()
    runtime.ingest = Mock(wraps=runtime.ingest)
    result = target.run(config, runtime, b'key', REV)
    assert result == {'applied_batches': 3, 'already_applied_batches': 0}
    assert runtime.ingest.call_count == 1
    combined = runtime.ingest.call_args.args[1]
    assert len(combined) == 2  # identical bytes across batches deduplicated
    assert {entry['_root'] for entries in combined.values() for entry in entries} == set(map(str, paths))
    assert len(list(receipts.iterdir())) == 3
    assert {alias for row in runtime.rows.values() for alias in row.metadata['MigrationSource']['source_uids']} == {A, B, D}
    # Simulate a crash after one atomic per-batch receipt was written. Replaying
    # the remaining batches is safe and preserves aliases from all three.
    for file in list(receipts.iterdir())[1:]: file.unlink()
    assert target.run(config, runtime, b'key', REV) == {'applied_batches': 2, 'already_applied_batches': 1}
    assert len(runtime.rows) == 2


def test_combined_failure_does_not_receipt_any_batch(tmp_path):
    parent = tmp_path / 'batches'; parent.mkdir()
    for uid in [A, B]:
        observed = {'source_uid': uid, 'stored_hash': 'f' * 64}
        state.publish(parent, C, {uid: observed}, lambda _: RAW, lambda _: observed)
    receipts = tmp_path / 'receipts'; receipts.mkdir(mode=0o700)
    config = {'source_participant_uid': C, 'target_participant_uid': D, 'runtime_revision': REV,
              'batches': str(parent), 'receipts': str(receipts)}
    runtime = Runtime(); runtime.fail_ingest = True
    with pytest.raises(ValueError, match='every source'): target.run(config, runtime, b'key', REV)
    assert list(receipts.iterdir()) == []


def test_conflicting_alias_across_batches_rejected(tmp_path):
    parent = tmp_path / 'batches'; parent.mkdir()
    paths = []
    for raw in [RAW, RAW.replace(b'01-01', b'02-01')]:
        observed = {'source_uid': A, 'stored_hash': 'f' * 64}
        paths.append(state.publish(parent, C, {A: observed}, lambda _: raw, lambda _: observed))
    runtime = Runtime(); runtime.ingest = Mock()
    with pytest.raises(ValueError, match='alias conflicts'):
        target.apply_batches(paths, C, D, REV, b'key', runtime)
    runtime.ingest.assert_not_called()


def test_cross_batch_digest_collision(tmp_path, monkeypatch):
    parent = tmp_path / 'batches'; parent.mkdir()
    paths = []
    for uid, raw in [(A, RAW), (B, RAW.replace(b'01-01', b'02-01'))]:
        observed = {'source_uid': uid, 'stored_hash': 'f' * 64}
        paths.append(state.publish(parent, C, {uid: observed}, lambda _: raw, lambda _: observed))
    original = target.group_sources
    def collision(*args): return {'fake': next(iter(original(*args).values()))}
    monkeypatch.setattr(target, 'group_sources', collision)
    with pytest.raises(ValueError, match='raw identity conflicts'):
        target.apply_batches(paths, C, D, REV, b'key', Runtime())


def canonical_storage(tmp_path):
    """Execute current production storage/loader definitions, not a facsimile."""
    import ast
    import blosc2
    from cryptography.fernet import Fernet
    from filelock import FileLock, Timeout
    import numpy as np
    import os
    import pickle
    import shutil
    import zlib
    app = Path(__file__).resolve().parents[2] / 'BRAVO'
    database_source = ast.parse((app / 'modules/Database.py').read_text())
    functions = [node for node in database_source.body if isinstance(node, ast.FunctionDef) and node.name in {'saveSourceFile', 'loadSourceFile'}]
    env = dict(DATABASE_PATH=str(tmp_path) + '/', HASH_KEY='synthetic-key',
        FALLBACK_COMPRESSION_MAGIC=b'BRAVO_ZLIB_v1\0', blosc2=blosc2, np=np,
        os=os, pickle=pickle, shutil=shutil, zlib=zlib, hmac=hmac, hashlib=hashlib,
        FileLock=FileLock, Timeout=Timeout)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(app / 'modules/Database.py'), 'exec'), env)
    encoder = Fernet(Fernet.generate_key())
    curator_source = ast.parse((app / 'modules/DataCurator.py').read_text())
    functions = [node for node in curator_source.body if isinstance(node, ast.FunctionDef) and node.name == 'loadCacheFile']
    loader_env = {'Database': NS(loadSourceFile=env['loadSourceFile']), 'secureEncoder': encoder}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(app / 'modules/DataCurator.py'), 'exec'), loader_env)
    return env['saveSourceFile'], loader_env['loadCacheFile'], encoder


@pytest.mark.parametrize('format', ['frame', 'legacy', 'fallback'])
def test_real_authenticated_storage_roundtrip(tmp_path, format):
    import blosc2
    import zlib
    save, load, encoder = canonical_storage(tmp_path)
    path = tmp_path / 'raw.json'
    token = encoder.encrypt(RAW)
    hashed = save(token, str(path), bytes=True)
    assert b'b2frame' in path.read_bytes()[:16]
    if format != 'frame':
        packed = blosc2.compress2(token, typesize=1) if format == 'legacy' else b'BRAVO_ZLIB_v1\0' + zlib.compress(token)
        path.write_bytes(packed)
        hashed = hmac.new(b'synthetic-key', packed, hashlib.sha256).hexdigest()
    row = NS(pointer=str(path), hashed=hashed)
    assert source.bounded_load(row, load) == RAW
    path.write_bytes(path.read_bytes()[:-1] + bytes([path.read_bytes()[-1] ^ 1]))
    with pytest.raises(ValueError, match='authentication'):
        source.bounded_load(row, load)


def test_frame_allocations_bounded_before_loader(tmp_path, monkeypatch):
    import blosc2
    import numpy as np
    _, _, encoder = canonical_storage(tmp_path)
    packed = blosc2.pack_tensor(np.frombuffer(encoder.encrypt(RAW), dtype=np.uint8))
    path = tmp_path / 'raw'; row = NS(pointer=str(path))
    loader = Mock(side_effect=AssertionError('must reject before loader'))
    def reject(data, match):
        path.write_bytes(data)
        row.hashed = hmac.new(b'synthetic-key', data, hashlib.sha256).hexdigest()
        with pytest.raises(ValueError, match=match): source.bounded_load(row, loader)
    inflated = bytearray(packed); inflated[30:38] = (2**50).to_bytes(8, 'big')
    reject(inflated, 'frame size')
    wrong_length = bytearray(packed); wrong_length[16:24] = (9999999).to_bytes(8, 'big')
    reject(wrong_length, 'frame size')
    reject(b'xxb2frame\0xxxxxx', 'frame header')
    frame = blosc2.schunk_from_cframe(packed, copy=True)
    frame.vlmeta['__pack_tensor__'] = ('numpy', (2**50,), '|u1')
    reject(frame.to_cframe(), 'tensor metadata')
    loader.assert_not_called()


def test_fallback_truncation_tail_and_bomb_bounded(tmp_path, monkeypatch):
    import zlib
    path = tmp_path / 'raw'; row = NS(pointer=str(path))
    monkeypatch.setattr(state, 'MAX_FILE', 16)
    for token in [zlib.compress(b'x' * 10000), zlib.compress(b'x' * 100)[:-1], zlib.compress(b'x' * 100) + b'extra']:
        data = b'BRAVO_ZLIB_v1\0' + token
        path.write_bytes(data)
        row.hashed = hmac.new(b'synthetic-key', data, hashlib.sha256).hexdigest()
        with pytest.raises(ValueError, match='fallback'): source.bounded_load(row, Mock())


def test_prior_alias_loss_after_save_fails_receipt(tmp_path):
    path = batch(tmp_path, aliases=(B,))
    runtime = Runtime()
    digest = next(iter(target.group_sources(path, state.validate_batch(path, C), b'key')))
    runtime.rows[digest] = NS(metadata={'MigrationSource': target.merge_provenance(None, C, [entry(A)])}, bad=False)
    def lose_old_alias(updates):
        for row, provenance in updates:
            row.metadata['MigrationSource'] = target.merge_provenance(None, C, [entry(B)])
    runtime.save_provenance = lose_old_alias
    with pytest.raises(ValueError, match='readback'):
        target.apply_batch(path, C, D, REV, b'key', runtime)


def test_receipts_mount_preflight_before_ingestion(tmp_path, monkeypatch):
    import errno
    path = batch(tmp_path)
    receipts = tmp_path / 'receipts'; receipts.mkdir(mode=0o700)
    config = {'source_participant_uid': C, 'target_participant_uid': D, 'runtime_revision': REV,
              'batches': str(path.parent), 'receipts': str(receipts)}
    runtime = Runtime(); runtime.ingest = Mock()
    original = target.tempfile.mkstemp
    def readonly(*args, **kwargs):
        assert Path(kwargs['dir']) == receipts
        raise OSError(errno.EROFS, 'modeled read-only bind mount')
    monkeypatch.setattr(target.tempfile, 'mkstemp', readonly)
    with pytest.raises(OSError): target.run(config, runtime, b'key', REV)
    runtime.ingest.assert_not_called()
    monkeypatch.setattr(target.tempfile, 'mkstemp', original)
    receipts.chmod(0o755)
    with pytest.raises(ValueError, match='private'): target.run(config, runtime, b'key', REV)
    runtime.ingest.assert_not_called()
    receipts.chmod(0o700)
    monkeypatch.setattr(target.os, 'geteuid', lambda: receipts.stat().st_uid + 1)
    with pytest.raises(ValueError, match='owned'): target.run(config, runtime, b'key', REV)
    runtime.ingest.assert_not_called()


def test_receipt_preflight_cleanup_and_invalid_path(tmp_path, monkeypatch):
    receipts = tmp_path / 'receipts'; receipts.mkdir(mode=0o700)
    existing = receipts / 'saved.json'; existing.write_bytes(b'untouched')
    target.verify_receipt_directory(receipts)
    assert list(receipts.iterdir()) == [existing] and existing.read_bytes() == b'untouched'
    def bad_sync(directory): raise OSError('filesystem durability unavailable')
    monkeypatch.setattr(state, 'sync_directory', bad_sync)
    with pytest.raises(OSError): target.verify_receipt_directory(receipts)
    assert list(receipts.iterdir()) == [existing]
    with pytest.raises(FileNotFoundError): target.verify_receipt_directory(tmp_path / 'missing')
    existing.chmod(0o700)
    with pytest.raises(ValueError, match='directory'): target.verify_receipt_directory(existing)
    link = tmp_path / 'link'; link.symlink_to(receipts)
    with pytest.raises(ValueError, match='unsafe'): target.verify_receipt_directory(link)


@pytest.mark.parametrize("receipt", [None, {}, {"status": "complete"},
    {"status": "failed", "exports_without_record": 0},
    {"status": "complete", "exports_without_record": 1},
    {"status": "complete", "exports_without_record": False},
    {"status": "complete", "exports_without_record": 0, "failed": "save error"}])
def test_target_rejects_incomplete_chronic_schedule(receipt):
    with pytest.raises(target.IncompleteSource, match="chronic schedule"):
        target.verify_chronic_restamp(NS(metadata={"ChronicScheduleRestamp": receipt}), "rule", "config")


def test_target_schedule_receipt_requires_metadata_mapping():
    with pytest.raises(target.IncompleteSource):
        target.verify_chronic_restamp(NS(metadata=None), "rule", "config")
    target.verify_chronic_restamp(NS(metadata={"ChronicScheduleRestamp": {
        "status": "complete", "exports_without_record": 0, "rule_version": "rule",
        "configuration_digest": "config", "inventory_digest": "a"*64}}), "rule", "config")


@pytest.mark.parametrize("field,value", [("rule_version", "old"), ("configuration_digest", "old"),
    ("inventory_digest", None), ("inventory_digest", "a"), ("inventory_digest", "z"*64)])
def test_restamp_receipt_must_match_current_rule_and_configuration(field, value):
    receipt = {"status":"complete", "exports_without_record":0, "rule_version":"rule",
               "configuration_digest":"config", "inventory_digest":"a"*64}
    receipt[field] = value
    with pytest.raises(target.IncompleteSource):
        target.verify_chronic_restamp(NS(metadata={"ChronicScheduleRestamp":receipt}), "rule", "config")


def test_final_inventory_recheck_rejects_changed_retained_settings(tmp_path, monkeypatch):
    app = Path(__file__).resolve().parents[2] / 'BRAVO'
    monkeypatch.syspath_prepend(str(app))
    import modules
    from modules.MedtronicPercept import chronic_schedule
    from modules.DecodeCommon import private_clinical_config
    monkeypatch.setattr(private_clinical_config, 'config_digest', lambda: 'fixed-config')
    monkeypatch.setattr(modules, 'DataCurator', NS(implant_device_uids=lambda *a, **k: ['device']), raising=False)
    empty = {'starts': [], 'ends': [], 'switches': []}
    rows = [NS(uid=A, hashed='raw-hash', device='device', metadata={'SensingSettingsRecord': empty})]
    digest = hashlib.sha256(json.dumps([(A,'raw-hash',empty)], sort_keys=True, separators=(',',':')).encode()).hexdigest()
    rows[0].metadata['ChronicScheduleRestamp'] = {'status':'complete', 'exports_without_record':0,
        'rule_version':chronic_schedule.RULE_VERSION, 'configuration_digest':'fixed-config', 'inventory_digest':digest}
    locks = []
    class Query(list):
        def select_for_update(self):
            locks.append(True)
            return self
    runtime = target.TargetRuntime(NS(SourceFile=NS(objects=NS(filter=lambda **kw: Query(rows)))), None,
        Mock(), contextlib.nullcontext, NS(uid=D), tmp_path)
    assert runtime.schedule_inventory_digest(rows[0]) == digest
    runtime.verify_final_schedules()
    assert locks == [True]
    # Mutating an old retained source after initial validation invalidates final acceptance.
    rows.append(NS(uid=B, hashed='second', device='device', metadata={'SensingSettingsRecord':empty,
        'ChronicScheduleRestamp':dict(rows[0].metadata['ChronicScheduleRestamp'])}))
    assert runtime.schedule_inventory_digest(rows[0]) == digest  # bounded invocation cache
    with pytest.raises(target.IncompleteSource): runtime.verify_final_schedules()
    rows.pop()
    rows[0].metadata['SensingSettingsRecord'] = None
    with pytest.raises(ValueError): runtime.verify_final_schedules()
    rows.clear()
    with pytest.raises(target.IncompleteSource, match='empty'): runtime.verify_final_schedules()
    monkeypatch.setattr(modules, 'DataCurator', NS(implant_device_uids=lambda *a, **k: []))
    with pytest.raises(target.IncompleteSource, match='device'): runtime.verify_final_schedules()


def test_inventory_acceptance_rejects_config_change_during_read(tmp_path, monkeypatch):
    app = Path(__file__).resolve().parents[2] / 'BRAVO'
    monkeypatch.syspath_prepend(str(app))
    import modules
    from modules.MedtronicPercept import chronic_schedule
    from modules.DecodeCommon import private_clinical_config
    versions = iter(['old-config','changed-config'])
    monkeypatch.setattr(private_clinical_config, 'config_digest', lambda: next(versions))
    monkeypatch.setattr(modules, 'DataCurator', NS(implant_device_uids=lambda *a, **k: ['device']), raising=False)
    empty = {'starts':[], 'ends':[], 'switches':[]}
    digest = hashlib.sha256(json.dumps([(A,'h',empty)], sort_keys=True, separators=(',',':')).encode()).hexdigest()
    row = NS(uid=A, hashed='h', device='device', metadata={'SensingSettingsRecord':empty,
        'ChronicScheduleRestamp':{'status':'complete','exports_without_record':0,'rule_version':chronic_schedule.RULE_VERSION,
            'configuration_digest':'old-config','inventory_digest':digest}})
    runtime = target.TargetRuntime(NS(SourceFile=NS(objects=NS(filter=lambda **kw: [row]))), None,
        Mock(), contextlib.nullcontext, NS(uid=D), tmp_path)
    with pytest.raises(target.IncompleteSource, match='changed'): runtime.schedule_inventory_digest(row)
