import contextlib
import hashlib
import hmac
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts' / 'daily_import'
sys.path.insert(0, str(SCRIPTS))
import state
import upstream_target as u

P, I, REV = 'a' * 32, 'b' * 32, 'c' * 40
SCOPE, SERIAL = 'synthetic-approved-folder', 'SYNTHETIC-DEVICE'
RAW = json.dumps({'SessionDate': '2026-01-01T00:00:00Z', 'DeviceInformation': {'Final': {'NeurostimulatorSerialNumber': SERIAL}}}).encode()
KEY = b'synthetic-key'


def publish(parent, items=None, change=None):
    items = items or [('id:first', RAW)]
    entries = []
    for identity, raw in items:
        sha = state.sha(raw)
        entries.append(dict(provider_id=identity, revision=None, provider_modified_at='2026-01-02T00:00:00Z',
                            path='sources/' + sha + '.json', sha256=sha, bytes=len(raw)))
    manifest = dict(format=1, kind=u.KIND, provider='dropbox', scope=SCOPE, count=len(entries),
                    total_bytes=sum(e['bytes'] for e in entries), files=entries)
    if change: change(manifest)
    payload = state.encoded(manifest)
    directory = parent / state.sha(payload); directory.mkdir(parents=True, exist_ok=True)
    (directory / 'sources').mkdir(exist_ok=True)
    for _, raw in items: (directory / 'sources' / (state.sha(raw) + '.json')).write_bytes(raw)
    (directory / 'upstream.manifest').write_bytes(payload)
    (directory / 'COMPLETE').write_text(state.sha(payload) + '\n')
    return directory, manifest


def config(tmp_path):
    batches = tmp_path / 'batches'; batches.mkdir()
    receipts = tmp_path / 'receipts'; receipts.mkdir(mode=0o700)
    return dict(target_participant_uid=P, runtime_revision=REV,
                upstream=dict(scope=SCOPE, batches=str(batches), receipts=str(receipts), approved_device_serials=[SERIAL]))


class Runtime:
    def __init__(self):
        self.person = NS(uid=P)
        self.rows, self.index = {}, {}
        self.fail_ingest = self.fail_save = False
        self.calls = 0
    def device_binding(self, approved): assert approved == [SERIAL]
    def source_index(self): return self.index
    def existing(self, digest): return self.rows.get(digest)
    def verify(self, row, entry):
        if row.bad: raise ValueError('corrupt raw')
    def ingest_upstream(self, groups):
        self.calls += 1
        if not self.fail_ingest:
            for digest, group in groups.items(): self.rows.setdefault(group['hashed'], NS(uid=digest, metadata={}, bad=False))
    def save_upstream(self, updates):
        if not self.fail_save:
            for row, prov in updates: row.metadata['UpstreamSource'] = prov


def test_new_duplicate_aliases_migration_preserved_and_retry(tmp_path):
    cfg = config(tmp_path)
    root, manifest = publish(Path(cfg['upstream']['batches']), [('id:first', RAW), ('id:alias', RAW)])
    runtime = Runtime()
    digest = hmac.new(KEY, RAW, hashlib.sha256).hexdigest()
    old = NS(uid='d' * 32, metadata={'MigrationSource': {'raw_sha256': state.sha(RAW), 'source_uid': 'e' * 32}}, bad=False)
    runtime.rows[digest] = old; runtime.index[state.sha(RAW)] = old
    result = u.run(cfg, runtime, KEY, REV)
    assert result['duplicate_unique_reports'] == 1 and result['imported_unique_reports'] == 0
    assert result['accepted_files'] == 2 and result['withheld_files'] == 0
    assert old.metadata['MigrationSource']['source_uid'] == 'e' * 32
    assert len(old.metadata['UpstreamSource']['files']) == 2
    assert 'source_uid' not in json.dumps(old.metadata['UpstreamSource'])
    assert u.run(cfg, runtime, KEY, REV)['already_applied_batches'] == 1
    # A new revision alias under identical raw bytes preserves both previous ones.
    publish(Path(cfg['upstream']['batches']), [('id:later', RAW)], lambda m: m['files'][0].update(revision='actual-revision'))
    assert u.run(cfg, runtime, KEY, REV)['accepted_files'] == 1
    assert len(old.metadata['UpstreamSource']['files']) == 3


def test_unknown_device_withheld_and_retried(tmp_path):
    cfg = config(tmp_path)
    wrong = RAW.replace(SERIAL.encode(), b'UNAPPROVED-DEVICE')
    publish(Path(cfg['upstream']['batches']), [('id:allowed', RAW), ('id:wrong', wrong)])
    runtime = Runtime()
    result = u.run(cfg, runtime, KEY, REV)
    assert result['withheld_files'] == 1 and result['error_code'] == 'unknown_device'
    assert result['imported_unique_reports'] == 1
    assert u.run(cfg, runtime, KEY, REV)['already_applied_batches'] == 0
    assert len(runtime.rows) == 1


def test_all_unknown_no_ingest(tmp_path):
    cfg = config(tmp_path)
    root, _ = publish(Path(cfg['upstream']['batches']), [('id:missing', b'{"SessionDate":"2026-01-01","DeviceInformation":{}}')])
    runtime = Runtime()
    receipts, new, duplicate = u.apply([root], cfg, runtime, KEY, REV)
    assert len(receipts[0][1]['withheld']) == 1 and runtime.calls == new == duplicate == 0


@pytest.mark.parametrize('change', [
    lambda m: m.update(scope='wrong'), lambda m: m.update(extra=True),
    lambda m: m.update(files=[]), lambda m: m.update(count=4), lambda m: m.update(total_bytes=1),
    lambda m: m['files'][0].update(extra=1), lambda m: m['files'][0].update(path='../wrong'),
    lambda m: m['files'][0].update(bytes=0), lambda m: m['files'][0].update(provider_id=''),
    lambda m: m['files'][0].update(provider_modified_at='2026-01-01'),
    lambda m: m['files'][0].update(revision='bad\nrevision'),
])
def test_invalid_manifest(tmp_path, change):
    root, _ = publish(tmp_path, change=change)
    with pytest.raises((ValueError, FileNotFoundError)): u.validate_batch(root, SCOPE)


def test_duplicate_provider_extra_file_and_completion(tmp_path):
    root, _ = publish(tmp_path / 'one', [('id:same', RAW), ('id:same', RAW)])
    with pytest.raises(ValueError, match='repeated'): u.validate_batch(root, SCOPE)
    root, _ = publish(tmp_path / 'two')
    (root / 'sources' / 'extra.json').write_bytes(RAW)
    with pytest.raises(ValueError, match='unexpected'): u.validate_batch(root, SCOPE)
    (root / 'COMPLETE').write_text('bad')
    with pytest.raises(ValueError, match='publication'): u.validate_batch(root, SCOPE)


def test_provenance_conflicts(tmp_path):
    _, manifest = publish(tmp_path)
    entry = manifest['files'][0]
    previous = u.merge_provenance(None, SCOPE, entry['sha256'], [entry])
    assert u.merge_provenance(previous, SCOPE, entry['sha256'], [entry]) == previous
    with pytest.raises(ValueError, match='conflicts'):
        u.merge_provenance(previous, 'different', entry['sha256'], [entry])
    previous['files'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='prior'):
        u.merge_provenance(previous, SCOPE, entry['sha256'], [entry])


@pytest.mark.parametrize('approved', [[], [SERIAL, SERIAL], 'bad'])
def test_invalid_device_config(tmp_path, approved):
    cfg = config(tmp_path); cfg['upstream']['approved_device_serials'] = approved
    with pytest.raises(ValueError, match='device list'): u.apply([], cfg, Runtime(), KEY, REV)


def test_runtime_mismatch_and_failed_ingest_receipt(tmp_path):
    cfg = config(tmp_path); root, _ = publish(Path(cfg['upstream']['batches']))
    runtime = Runtime()
    with pytest.raises(ValueError, match='runtime'): u.apply([root], cfg, runtime, KEY, '0' * 40)
    runtime.fail_ingest = True
    with pytest.raises(ValueError, match='incomplete'): u.run(cfg, runtime, KEY, REV)
    assert list(Path(cfg['upstream']['receipts']).iterdir()) == []
    runtime.fail_ingest = False; runtime.fail_save = True
    with pytest.raises(ValueError, match='readback'): u.run(cfg, runtime, KEY, REV)
    runtime.index[state.sha(RAW)] = NS(uid='unmatched', metadata={})
    with pytest.raises(ValueError, match='provenance mismatch'): u.run(cfg, runtime, KEY, REV)


def test_actual_runtime_bindings_index_and_staged_input(tmp_path):
    person = NS(uid=P, institute_id=I)
    rows = [NS(uid='row', metadata={'MigrationSource': {'raw_sha256': state.sha(RAW)}})]
    devices = [NS(owner_id=P, serial_number=SERIAL)]
    models = NS(DBSDevice=NS(objects=NS(filter=lambda **kw: devices)),
                SourceFile=NS(objects=NS(filter=lambda **kw: rows)))
    calls = []
    def command(name, **kw):
        assert name == 'ingest_percept_folder' and kw['participant'] == P and not kw['dry_run']
        calls.append([p.read_bytes() for p in Path(kw['folder']).iterdir()])
    runtime = u.Runtime(models, None, command, contextlib.nullcontext, person, tmp_path)
    runtime.device_binding([SERIAL])
    assert runtime.source_index()[state.sha(RAW)] is rows[0]
    rows[0].save = Mock(); runtime.save_upstream([(rows[0], {'test': True})])
    rows[0].save.assert_called_once_with(update_fields=['metadata'])
    rows[0].metadata.pop('UpstreamSource')
    root, m = publish(tmp_path / 'batch')
    runtime.ingest_upstream({state.sha(RAW): {'root': root, 'entries': m['files']}})
    assert calls == [[RAW]]
    devices[0].owner_id = I
    with pytest.raises(ValueError, match='another'): runtime.device_binding([SERIAL])
    devices.clear()
    with pytest.raises(ValueError, match='unavailable'): runtime.device_binding([SERIAL])
    rows.append(NS(uid='other', metadata={'UpstreamSource': {'raw_sha256': state.sha(RAW)}}))
    with pytest.raises(ValueError, match='multiple'): runtime.source_index()


def test_empty_run_pending_ignored_and_text_validation(tmp_path):
    cfg = config(tmp_path)
    (Path(cfg['upstream']['batches']) / '.pending-test').mkdir()
    assert u.run(cfg, Runtime(), KEY, REV)['applied_batches'] == 0
    for bad in [None, '', 'x\n']:
        with pytest.raises(ValueError): u.text(bad)


def test_execute_binding(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    cfg.update(database_name='isolated', database_user='isolated', target_institute_uid=I,
               participant_name='Synthetic', raw_root=str(tmp_path / 'raws'))
    monkeypatch.setitem(sys.modules, 'django', NS(setup=lambda: None))
    monkeypatch.setitem(sys.modules, 'django.conf', NS(settings=NS(DATABASES={'default': {'NAME': 'isolated', 'USER': 'isolated'}})))
    monkeypatch.setitem(sys.modules, 'django.core.management', NS(call_command=Mock()))
    monkeypatch.setitem(sys.modules, 'django.db', NS(transaction=NS(atomic=contextlib.nullcontext)))
    monkeypatch.setitem(sys.modules, 'Server', NS(models=NS(Participant=NS(objects=NS(get=lambda **kw: NS(uid=P))))))
    monkeypatch.setitem(sys.modules, 'modules', NS(DataCurator=NS(loadCacheFile=Mock())))
    monkeypatch.setenv('DATASERVER_PATH', str(tmp_path)); monkeypatch.setenv('DATASERVER_HASHKEY', 'synthetic-key')
    monkeypatch.setenv('BRAVO_BUILD_REVISION', REV)
    monkeypatch.setattr(u, 'run', lambda *a: {'accepted_files': 0})
    assert u.execute(cfg) == {'accepted_files': 0}
    cfg['raw_root'] = str(tmp_path / 'wrong')
    with pytest.raises(ValueError, match='raw root'): u.execute(cfg)
    cfg['database_name'] = 'wrong'
    with pytest.raises(ValueError, match='database'): u.execute(cfg)


def test_changed_existing_provider_withheld_but_same_raw_revision_allowed(tmp_path):
    cfg = config(tmp_path)
    root, manifest = publish(Path(cfg['upstream']['batches']))
    runtime = Runtime()
    assert u.run(cfg, runtime, KEY, REV)['accepted_files'] == 1
    row = next(iter(runtime.rows.values()))
    runtime.index[state.sha(RAW)] = row
    changed = RAW.replace(b'01-01', b'02-01')
    publish(Path(cfg['upstream']['batches']), [('id:first', changed)])
    result = u.run(cfg, runtime, KEY, REV)
    assert result['error_code'] == 'changed_source' and result['withheld_files'] == 1
    assert len(runtime.rows) == 1
    assert row.metadata['UpstreamSource']['raw_sha256'] == state.sha(RAW)


def test_conflicting_pending_provider_all_withheld_and_bad_prior_rejected(tmp_path):
    cfg = config(tmp_path)
    for raw in [RAW, RAW.replace(b'01-01', b'02-01')]:
        publish(Path(cfg['upstream']['batches']), [('id:first', raw)])
    runtime = Runtime()
    result = u.run(cfg, runtime, KEY, REV)
    assert result['withheld_files'] == 2 and runtime.calls == 0
    assert result['error_code'] == 'changed_source'
    invalid = NS(metadata={'UpstreamSource': {'scope': SCOPE, 'raw_sha256': state.sha(RAW),
                      'files': [{'provider_id': 'id:bad', 'sha256': '0' * 64}]}})
    with pytest.raises(ValueError, match='existing provider'): u.provider_bindings({'x': invalid}, SCOPE)
    assert u.provider_bindings({'x': invalid}, 'other-scope') == {}


def test_existing_redacted_raw_is_metadata_only_with_new_unknown_withheld(tmp_path):
    cfg = config(tmp_path)
    redacted = RAW.replace(SERIAL.encode(), '\u2588'.encode() * 7)
    new_unknown = redacted.replace(b'01-01', b'01-03')
    publish(Path(cfg['upstream']['batches']), [('id:old', redacted), ('id:new-unknown', new_unknown), ('id:new-approved', RAW)])
    runtime = Runtime()
    old = NS(uid='d' * 32, metadata={'MigrationSource': {'raw_sha256': state.sha(redacted)}}, bad=False)
    runtime.rows[hmac.new(KEY, redacted, hashlib.sha256).hexdigest()] = old
    runtime.index[state.sha(redacted)] = old
    original_ingest = runtime.ingest_upstream
    def ingest(groups):
        assert set(groups) == {state.sha(RAW)}
        original_ingest(groups)
    runtime.ingest_upstream = ingest
    result = u.run(cfg, runtime, KEY, REV)
    assert result['duplicate_unique_reports'] == result['imported_unique_reports'] == result['withheld_files'] == 1
    assert result['error_code'] == 'unknown_device' and len(runtime.rows) == 2
    assert old.metadata['UpstreamSource']['raw_sha256'] == state.sha(redacted)
    assert old.metadata['MigrationSource'] == {'raw_sha256': state.sha(redacted)}


@pytest.mark.parametrize('failure', ['none', 'missing-provenance', 'sha-mismatch', 'missing-hmac', 'wrong-owner', 'raw-tamper', 'incomplete'])
def test_redacted_duplicate_requires_actual_runtime_identity_and_raw_verification(tmp_path, monkeypatch, failure):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "BRAVO"))
    cfg = config(tmp_path)
    raw = RAW.replace(SERIAL.encode(), b'REDACTED')
    root, manifest = publish(Path(cfg['upstream']['batches']), [('id:old', raw)])
    person = NS(uid=P, institute_id=I)
    raw_root = tmp_path / 'raws'; (raw_root / P).mkdir(parents=True)
    source_uid = 'd' * 32
    pointer = raw_root / P / (source_uid + '.json'); pointer.write_bytes(b'authenticated-storage-placeholder')
    row = NS(uid=source_uid, type='MedtronicJSON', pointer=str(pointer),
             metadata={'MigrationSource': {'raw_sha256': state.sha(raw)},
                  'ChronicScheduleRestamp': {'status':'complete', 'exports_without_record':0,
                      'rule_version':'complete-owner-bound-schedule-v1',
                      'configuration_digest':'clinical-config-unavailable-v1', 'inventory_digest':'a'*64}}, save=Mock())
    expected_hmac = hmac.new(KEY, raw, hashlib.sha256).hexdigest()
    matches = NS(exclude=lambda **kw: NS(exists=lambda: failure == 'wrong-owner'), count=lambda: 1,
                 first=lambda: None if failure == 'missing-hmac' else row)
    def query(**kw):
        assert kw == {'unique_hashed': expected_hmac, 'institute': I}
        return matches
    models = NS(SourceFile=NS(objects=NS(filter=query)))
    runtime = u.Runtime(models, None, Mock(), contextlib.nullcontext, person, raw_root)
    runtime.device_binding = Mock()
    runtime.schedule_inventory_digest = lambda row: "a"*64
    index = {} if failure == 'missing-provenance' else {state.sha(raw): row}
    if failure == 'sha-mismatch': index[state.sha(raw)] = NS(uid='e' * 32, metadata={})
    runtime.source_index = lambda: index
    runtime.ingest_upstream = Mock(side_effect=AssertionError('duplicates must never invoke decoder'))
    monkeypatch.setattr(u.target_adapter, 'bounded_load', lambda *a: raw + b' ' if failure == 'raw-tamper' else raw)
    if failure == 'incomplete': row.pointer = str(raw_root / 'unfinished.json')
    if failure in ['none', 'missing-provenance']:
        result = u.run(cfg, runtime, KEY, REV)
        assert result['duplicate_unique_reports'] == (failure == 'none')
        assert result['withheld_files'] == (failure == 'missing-provenance')
        assert row.save.call_count == (failure == 'none')
    else:
        with pytest.raises(ValueError): u.run(cfg, runtime, KEY, REV)
        assert row.save.call_count == 0 and list(Path(cfg['upstream']['receipts']).iterdir()) == []
    runtime.ingest_upstream.assert_not_called()


def restoration_case(tmp_path, old_change=None, new_change=None):
    cfg = config(tmp_path)
    before = {'SessionDate': '2026-01-01T00:00:00Z', 'DeviceInformation': {
        phase: {'NeurostimulatorSerialNumber': '\u2588' * 7} for phase in ('Initial', 'Final')},
        'Observation': [1, None, {'value': 2}]}
    after = json.loads(json.dumps(before))
    for phase in ('Initial', 'Final'): after['DeviceInformation'][phase]['NeurostimulatorSerialNumber'] = SERIAL
    if old_change: old_change(before)
    if new_change: new_change(after)
    old_raw, new_raw = json.dumps(before).encode(), json.dumps(after).encode()
    batches = Path(cfg['upstream']['batches'])
    old_root, old_manifest = publish(batches, [('id:restored', old_raw)])
    new_root, new_manifest = publish(batches, [('id:restored', new_raw)])
    record = dict(provider_id='id:restored', old_sha256=state.sha(old_raw), new_sha256=state.sha(new_raw),
                  target_source_uid='d' * 32, old_batch_sha256=old_root.name)
    cfg['upstream']['serial_restorations'] = [record]
    runtime = Runtime()
    row = NS(uid=record['target_source_uid'], bad=False, metadata={'MigrationSource': {'raw_sha256':state.sha(old_raw)},
        'UpstreamSource': u.merge_provenance(None, SCOPE, state.sha(old_raw), old_manifest['files'])})
    runtime.rows[hmac.new(KEY, old_raw, hashlib.sha256).hexdigest()] = row
    runtime.index[state.sha(old_raw)] = row
    runtime.verify = Mock(side_effect=runtime.verify)
    runtime.ingest_upstream = Mock(side_effect=AssertionError('serial restoration must not decode'))
    runtime.save_upstream = Mock(side_effect=AssertionError('serial restoration must not update source metadata'))
    state.atomic_json(Path(cfg['upstream']['receipts']) / (old_root.name + '.json'),
                     u.receipt(old_manifest, P, REV, [u.file_identity(old_manifest['files'][0])], []))
    return cfg, runtime, row, old_root, new_root, old_raw, new_raw


def test_exact_serial_restoration_receipt_replay_and_future_revision(tmp_path):
    cfg, runtime, row, old_root, new_root, old_raw, new_raw = restoration_case(tmp_path)
    original = json.loads(json.dumps(row.metadata))
    result = u.run(cfg, runtime, KEY, REV)
    assert result['accepted_revision_files'] == result['accepted_files'] == 1
    assert result['imported_unique_reports'] == result['duplicate_unique_reports'] == result['withheld_files'] == 0
    assert row.metadata == original and len(runtime.rows) == 1
    saved = json.loads((Path(cfg['upstream']['receipts']) / (new_root.name + '.json')).read_text())
    assert saved['serial_restorations'][0]['target_source_uid'] == row.uid
    assert saved['serial_restorations'][0]['old_sha256'] == state.sha(old_raw)
    count = runtime.verify.call_count
    replay = u.run(cfg, runtime, KEY, REV)
    assert replay['applied_batches'] == replay['accepted_revision_files'] == 0
    assert replay['already_applied_batches'] == 2
    assert runtime.verify.call_count > count
    assert json.loads((Path(cfg['upstream']['receipts']) / (new_root.name + '.json')).read_text()) == saved
    publish(Path(cfg['upstream']['batches']), [('id:restored', new_raw.replace(b'01-01', b'01-02'))])
    result = u.run(cfg, runtime, KEY, REV)
    assert result['accepted_revision_files'] == 0 and result['withheld_files'] == 1 and result['error_code'] == 'changed_source'
    runtime.ingest_upstream.assert_not_called(); runtime.save_upstream.assert_not_called()
    assert row.metadata == original
    assert (old_root / 'sources' / (state.sha(old_raw) + '.json')).read_bytes() == old_raw
    assert (new_root / 'sources' / (state.sha(new_raw) + '.json')).read_bytes() == new_raw


@pytest.mark.parametrize('mutate', [
    lambda v: v['Observation'].append(3),
    lambda v: v['Observation'].__setitem__(0, 1.0),
    lambda v: v['DeviceInformation'].pop('Initial'),
    lambda v: v['DeviceInformation']['Final'].__setitem__('NeurostimulatorSerialNumber', 'UNAPPROVED'),
    lambda v: v['DeviceInformation']['Initial'].__setitem__('NeurostimulatorSerialNumber', None),
])
def test_serial_restoration_rejects_other_changes_or_missing_device(tmp_path, mutate):
    cfg, runtime, row, old, new, *_ = restoration_case(tmp_path, new_change=mutate)
    with pytest.raises(ValueError): u.run(cfg, runtime, KEY, REV)
    assert not (Path(cfg['upstream']['receipts']) / (new.name + '.json')).exists()
    runtime.ingest_upstream.assert_not_called(); runtime.save_upstream.assert_not_called()


@pytest.mark.parametrize('old_serial', ['', 'PARTIALLY\u2588', 123, 'OTHER-CONCRETE'])
def test_serial_restoration_requires_fully_redacted_previous_serial(tmp_path, old_serial):
    cfg, runtime, row, old, new, *_ = restoration_case(tmp_path,
        old_change=lambda v: v['DeviceInformation']['Initial'].__setitem__('NeurostimulatorSerialNumber', old_serial))
    with pytest.raises(ValueError, match='transition'): u.run(cfg, runtime, KEY, REV)
    runtime.ingest_upstream.assert_not_called(); runtime.save_upstream.assert_not_called()


@pytest.mark.parametrize('failure', ['target-uid', 'target-missing', 'index-missing', 'wrong-index', 'prior-missing', 'prior-scope', 'prior-sha', 'prior-id', 'corrupt-target', 'old-provider', 'missing-old-binding'])
def test_serial_restoration_exact_original_binding(tmp_path, failure):
    cfg, runtime, row, old, new, old_raw, new_raw = restoration_case(tmp_path)
    record = cfg['upstream']['serial_restorations'][0]
    if failure == 'target-uid': record['target_source_uid'] = 'e' * 32
    if failure == 'target-missing': runtime.rows.clear()
    if failure == 'index-missing': runtime.index.clear()
    if failure == 'wrong-index': runtime.index[state.sha(old_raw)] = NS(uid='e' * 32, metadata=row.metadata)
    if failure == 'prior-missing': row.metadata.pop('UpstreamSource')
    if failure == 'prior-scope': row.metadata['UpstreamSource']['scope'] = 'other-scope'
    if failure == 'prior-sha': row.metadata['UpstreamSource']['raw_sha256'] = 'e' * 64
    if failure == 'prior-id': row.metadata['UpstreamSource']['files'][0]['provider_id'] = 'id:unrelated'
    if failure == 'corrupt-target': row.bad = True
    if failure == 'old-provider':
        replacement, _ = publish(Path(cfg['upstream']['batches']), [('id:unrelated', old_raw)])
        record['old_batch_sha256'] = replacement.name
    if failure == 'missing-old-binding':
        row.metadata.pop('UpstreamSource'); runtime.index.clear()
    if failure in ('index-missing', 'prior-missing', 'prior-scope', 'prior-id', 'missing-old-binding'):
        result = u.run(cfg, runtime, KEY, REV)
        assert result['withheld_files'] == 1 and result['accepted_revision_files'] == 0
    else:
        with pytest.raises(ValueError): u.run(cfg, runtime, KEY, REV)
    runtime.ingest_upstream.assert_not_called(); runtime.save_upstream.assert_not_called()


def test_serial_restoration_approval_schema_and_strict_json(tmp_path):
    cfg, runtime, row, old, new, *_ = restoration_case(tmp_path)
    valid = cfg['upstream']['serial_restorations'][0]
    for records in [None, [valid] * 33, [dict(valid, extra=1)], [valid, valid], [dict(valid, old_sha256=valid['new_sha256'])]]:
        with pytest.raises(ValueError): u.restoration_approvals({'serial_restorations': records})
    for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}']:
        with pytest.raises(ValueError): u.strict_report(raw)
    assert u.strict_report(b'{"x":1}') == {'x': 1}
    assert u.canonical_digest({'x': 1}) != u.canonical_digest({'x': 1.0})


def test_restoration_receipt_needs_current_approval_and_reauthenticates(tmp_path):
    cfg, runtime, row, old, new, *_ = restoration_case(tmp_path)
    u.run(cfg, runtime, KEY, REV)
    row.bad = True
    with pytest.raises(ValueError, match='corrupt'): u.run(cfg, runtime, KEY, REV)
    row.bad = False
    cfg['upstream']['serial_restorations'] = []
    result = u.run(cfg, runtime, KEY, REV)
    assert result['withheld_files'] == 1 and result['accepted_revision_files'] == 0
    runtime.ingest_upstream.assert_not_called(); runtime.save_upstream.assert_not_called()


def test_serial_restoration_rejects_two_different_approved_serials(tmp_path):
    cfg, runtime, row, old, new, *_ = restoration_case(tmp_path,
        new_change=lambda v: v['DeviceInformation']['Initial'].__setitem__('NeurostimulatorSerialNumber', 'OTHER-APPROVED'))
    cfg['upstream']['approved_device_serials'].append('OTHER-APPROVED')
    runtime.device_binding = Mock()
    with pytest.raises(ValueError, match='other report content'): u.run(cfg, runtime, KEY, REV)


def test_serial_restoration_actual_duplicate_key_payload_rejected(tmp_path):
    cfg, runtime, row, old, new, old_raw, new_raw = restoration_case(tmp_path)
    raw = new_raw.replace(b'"Observation":', b'"ambiguous":1,"ambiguous":2,"Observation":')
    duplicate, _ = publish(Path(cfg['upstream']['batches']), [('id:restored', raw)])
    cfg['upstream']['serial_restorations'][0]['new_sha256'] = state.sha(raw)
    with pytest.raises(ValueError, match='ambiguous'): u.apply([duplicate], cfg, runtime, KEY, REV)
    runtime.ingest_upstream.assert_not_called(); runtime.save_upstream.assert_not_called()


def test_serial_restoration_new_serial_must_be_concrete_even_if_configured(tmp_path):
    serial = '\u2588' * 6
    def change(value):
        for phase in ('Initial', 'Final'):
            value['DeviceInformation'][phase]['NeurostimulatorSerialNumber'] = serial
    cfg, runtime, row, old, new, *_ = restoration_case(tmp_path, new_change=change)
    cfg['upstream']['approved_device_serials'].append(serial)
    runtime.device_binding = Mock()
    with pytest.raises(ValueError, match='transition'): u.run(cfg, runtime, KEY, REV)


def test_restoration_receipt_cannot_omit_current_required_relationship(tmp_path):
    cfg, runtime, row, old, new, *_ = restoration_case(tmp_path)
    u.run(cfg, runtime, KEY, REV)
    path = Path(cfg['upstream']['receipts']) / (new.name + '.json')
    saved = json.loads(path.read_text()); saved.pop('serial_restorations')
    state.atomic_json(path, saved)
    count = runtime.verify.call_count
    result = u.run(cfg, runtime, KEY, REV)
    assert result['accepted_revision_files'] == 1 and runtime.verify.call_count > count
    assert len(json.loads(path.read_text())['serial_restorations']) == 1
