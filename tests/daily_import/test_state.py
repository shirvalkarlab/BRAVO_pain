"""Synthetic lifecycle and failure tests; no provider or application DB access."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

MODULE = Path(__file__).resolve().parents[2] / 'scripts/daily_import/state.py'
spec = importlib.util.spec_from_file_location('daily_state', MODULE)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
P, T, A, B = ('1' * 32, '2' * 32, 'a' * 32, 'b' * 32)
H, REV = 'c' * 64, 'd' * 40
RAW = b'{"SessionDate":"2026-01-01T00:00:00Z","DeviceInformation":{}}'


def observation(source=A, fingerprint=H):
    return {'source_uid': source, 'stored_hash': fingerprint, 'pointer': '/retained/' + source, 'stat': [1, 2, 64, 3, 4]}


def checkpoint():
    return {'format': 1, 'source_participant_uid': P, 'sources': {}}


def manifest(aliases=(A,)):
    return {'format': 1, 'source_participant_uid': P, 'count': len(aliases),
            'total_bytes': len(RAW) * len(aliases), 'fingerprints': {a: H for a in aliases},
            'files': [{'source_uid': a, 'path': 'sources/' + a + '.json', 'bytes': len(RAW), 'sha256': s.sha(RAW)} for a in aliases]}


def publish(tmp_path, aliases=(A,)):
    chosen = {a: observation(a) for a in aliases}
    return s.publish(tmp_path, P, chosen, lambda _: RAW, chosen.get)


@pytest.mark.parametrize('value', [None, '', 'a' * 31, '../' + A, A.upper(), 1])
def test_invalid_identity(value):
    with pytest.raises(ValueError):
        s.uid(value)


@pytest.mark.parametrize('value', [None, '', 'a' * 63, H.upper(), 1])
def test_invalid_digest(value):
    with pytest.raises(ValueError):
        s.digest(value)


def test_atomic_json(tmp_path):
    target = tmp_path / 'checkpoint.json'
    s.atomic_json(target, checkpoint())
    assert json.loads(target.read_text()) == checkpoint()
    assert target.stat().st_mode & 0o777 == 0o600
    newer = dict(checkpoint(), marker='new')
    s.atomic_json(target, newer)
    assert json.loads(target.read_text()) == newer
    assert not list(tmp_path.glob('.state-*'))


def test_atomic_write_failure_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / 'checkpoint.json'
    s.atomic_json(target, checkpoint())
    def fail(*args):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(s.os, 'replace', fail)
    with pytest.raises(OSError):
        s.atomic_json(target, {})
    assert json.loads(target.read_text()) == checkpoint()
    assert not list(tmp_path.glob('.state-*'))


@pytest.mark.parametrize('kind', ['relative', 'parent', 'symlink', 'parentlink'])
def test_unsafe_paths(tmp_path, kind):
    target = tmp_path / 'file'
    target.write_bytes(RAW)
    if kind == 'relative':
        path = Path('relative')
    elif kind == 'parent':
        path = tmp_path / '..' / 'file'
    elif kind == 'symlink':
        path = tmp_path / 'link'
        path.symlink_to(target)
    else:
        link = tmp_path / 'link'
        link.symlink_to(tmp_path, target_is_directory=True)
        path = link / 'file'
    with pytest.raises(ValueError):
        s.safe_path(path)


def test_retained_identity(tmp_path):
    path = tmp_path / 'original'
    path.write_bytes(RAW)
    assert len(s.file_identity(path)) == 5
    assert s.read_bounded(path, 100) == RAW
    for invalid in (tmp_path, tmp_path / 'empty'):
        if invalid != tmp_path:
            invalid.touch()
        with pytest.raises(ValueError):
            s.file_identity(invalid)
        with pytest.raises(ValueError):
            s.read_bounded(invalid, 100)
    with pytest.raises(ValueError):
        s.read_bounded(path, 1)


def test_read_detects_replaced_path(tmp_path, monkeypatch):
    path = tmp_path / 'data'
    path.write_bytes(RAW)
    original = s.os.fstat
    calls = 0
    def replace_on_second(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.unlink()
            path.write_bytes(RAW)
        return original(fd)
    monkeypatch.setattr(s.os, 'fstat', replace_on_second)
    with pytest.raises(ValueError, match='changed'):
        s.read_bounded(path, 100)


def test_source_projection(tmp_path):
    retained = tmp_path / P
    retained.mkdir()
    path = retained / (A + '.json')
    path.write_bytes(RAW)
    row = dict(uid=A, owner=P, type='MedtronicJSON', upload_type='MedtronicJSON', pointer=str(path), stored_hash=H)
    observed = s.observation(row, P, tmp_path)
    assert observed['source_uid'] == A and observed['stat'][2] == len(RAW)
    assert s.observation(dict(row, pointer='/cache/inflight.tmp'), P, tmp_path) is None
    for field, value in [('owner', T), ('type', 'Other'), ('upload_type', 'Other'), ('stored_hash', 'broken')]:
        with pytest.raises(ValueError):
            s.observation(dict(row, **{field: value}), P, tmp_path)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        s.observation(row, P, tmp_path)


@pytest.mark.parametrize('mutation', [
    lambda m: m.update(format=2), lambda m: m.update(format=True),
    lambda m: m.update(source_participant_uid=T), lambda m: m.update(count=0),
    lambda m: m.update(count=True), lambda m: m.update(total_bytes=True),
    lambda m: m.update(total_bytes=3), lambda m: m.update(files=[]),
    lambda m: m['files'].append(dict(m['files'][0])),
    lambda m: m['files'][0].update(path='../source'),
    lambda m: m['files'][0].update(bytes=0),
    lambda m: m['files'][0].update(bytes=True),
    lambda m: m['files'][0].update(bytes=s.MAX_FILE+1),
    lambda m: m['files'][0].update(sha256='bad'),
])
def test_manifest_invalid(mutation):
    item = manifest()
    mutation(item)
    with pytest.raises(ValueError):
        s.manifest_files(item, P)


def test_manifest_aggregate_bounds(monkeypatch):
    monkeypatch.setattr(s, 'MAX_FILES', 1)
    with pytest.raises(ValueError):
        s.manifest_files(manifest((A, B)), P)
    monkeypatch.setattr(s, 'MAX_TOTAL', 1)
    with pytest.raises(ValueError):
        s.manifest_files(manifest(), P)


@pytest.mark.parametrize('raw', [None, b'', b'[]', b'{}', b'{"SessionDate":0}', b'notjson'])
def test_bad_raw(raw):
    with pytest.raises((ValueError, TypeError)):
        s.verified_raw(raw)


def test_raw_bounds_and_baseline_digest(monkeypatch):
    assert s.verified_raw(RAW) == s.sha(RAW)
    assert s.verified_raw(RAW, manifest()['files'][0]) == s.sha(RAW)
    with pytest.raises(ValueError):
        s.verified_raw(RAW + b' ', manifest()['files'][0])
    monkeypatch.setattr(s, 'MAX_FILE', 1)
    with pytest.raises(ValueError):
        s.verified_raw(RAW)


def test_baseline_authenticates_every_alias():
    obs = {a: observation(a) for a in (A, B)}
    loaded = []
    def load(a):
        loaded.append(a)
        return RAW
    baseline = s.baseline(manifest((A, B)), P, obs, obs, load, obs.get)
    assert loaded == [A, B]
    assert baseline['sources'] == {a: {'stored_hash': H, 'sha256': s.sha(RAW)} for a in (A, B)}


@pytest.mark.parametrize('failure', ['missing', 'unstable', 'during', 'hash'])
def test_baseline_refuses_unproved_fingerprints(failure):
    before = {A: observation()}
    after = copy.deepcopy(before)
    raw = RAW
    reobserve = after.get
    if failure == 'missing':
        before = {}
    elif failure == 'unstable':
        after[A]['stat'][2] += 1
    elif failure == 'during':
        reobserve = lambda _: None
    else:
        raw += b' '
    with pytest.raises(ValueError):
        s.baseline(manifest(), P, before, after, lambda _: raw, reobserve)


def test_selection_noop_new_and_disappeared():
    cp = checkpoint()
    obs = {A: observation()}
    assert s.select(cp, P, obs, obs) == (obs, [])
    published = s.acknowledge_export(cp, manifest())
    assert s.select(published, P, obs, obs) == ({}, [])
    assert cp == checkpoint()  # acknowledgment does not mutate old state
    assert s.select(published, P, {}, {}) == ({}, [])
    assert s.select(cp, P, obs, {}) == ({}, [A])
    assert s.select(cp, P, {}, obs) == ({}, [A])
    assert s.select(cp, P, {A: None}, {A: None}) == ({}, [A])


def test_known_change_fails_even_when_unstable():
    cp = s.acknowledge_export(checkpoint(), manifest())
    original, changed = {A: observation()}, {A: observation(fingerprint='f'*64)}
    for before, after in [(changed, changed), (original, changed), (changed, original), (changed, {})]:
        with pytest.raises(ValueError, match='published source changed'):
            s.select(cp, P, before, after)


def test_inventory_wrong_identity():
    with pytest.raises(ValueError, match='inventory identity'):
        s.select(checkpoint(), P, {}, {A: observation(B)})


@pytest.mark.parametrize('mutation', [lambda c: c.update(format=2), lambda c: c.update(format=True), lambda c: c.update(source_participant_uid=T), lambda c: c['sources'].update({'bad': {'stored_hash':H, 'sha256':H}}), lambda c: c['sources'].update({A: {'stored_hash':'bad','sha256':H}}), lambda c: c['sources'].update({A: {'stored_hash':H,'sha256':'bad'}})])
def test_checkpoint_invalid(mutation):
    cp = checkpoint()
    mutation(cp)
    with pytest.raises(ValueError):
        s.select(cp, P, {}, {})


def test_complete_batch_and_publish_retry(tmp_path):
    batch = publish(tmp_path, (A, B))
    expected = manifest((A, B))
    assert s.validate_batch(batch, P) == expected
    assert batch.name == s.sha(s.encoded(expected))
    assert publish(tmp_path, (A, B)) == batch
    assert len(list(tmp_path.iterdir())) == 1
    recovered = s.acknowledge_export(checkpoint(), expected)
    assert s.acknowledge_export(recovered, expected) == recovered
    assert set(recovered['sources']) == {A, B}
    assert all(p.stat().st_mode & 0o077 == 0 for p in batch.rglob('*'))
    assert s.publish(tmp_path, P, {}, None, None) is None


@pytest.mark.parametrize('failure', ['load', 'race', 'total', 'count', 'identity'])
def test_export_failure_no_checkpoint_or_published_batch(tmp_path, monkeypatch, failure):
    obs = {A: observation()}
    def load(_):
        if failure == 'load':
            raise OSError('synthetic read failure')
        return RAW
    if failure == 'total':
        monkeypatch.setattr(s, 'MAX_TOTAL', 1)
    if failure == 'count':
        monkeypatch.setattr(s, 'MAX_FILES', 0)
    if failure == 'identity':
        obs[A]['source_uid'] = B
    with pytest.raises((ValueError, OSError)):
        s.publish(tmp_path, P, obs, load, (lambda _: None) if failure == 'race' else obs.get)
    assert list(tmp_path.iterdir()) == []


def rewrite_manifest(batch, mutate):
    item = json.loads((batch / 'export.manifest').read_bytes())
    mutate(item)
    (batch / 'export.manifest').write_bytes(s.encoded(item))
    (batch / 'COMPLETE').write_text(s.sha(s.encoded(item)) + '\n')


@pytest.mark.parametrize('failure', ['complete', 'fingerprints', 'fingerprintdigest', 'extra', 'extra_source', 'changed_raw', 'sourcelink', 'parentlink', 'batchlink'])
def test_batch_validation_fails_closed(tmp_path, failure):
    batch = publish(tmp_path)
    if failure == 'complete':
        (batch / 'COMPLETE').write_text('f' * 64)
    elif failure == 'fingerprints':
        rewrite_manifest(batch, lambda m: m.update(fingerprints={}))
    elif failure == 'fingerprintdigest':
        rewrite_manifest(batch, lambda m: m.update(fingerprints={A:'bad'}))
    elif failure == 'extra':
        (batch / 'extra').touch()
    elif failure == 'extra_source':
        (batch / 'sources' / 'extra').touch()
    elif failure == 'changed_raw':
        (batch / 'sources' / (A + '.json')).write_bytes(RAW + b' ')
    elif failure == 'sourcelink':
        path = batch / 'sources' / (A + '.json')
        path.unlink()
        path.symlink_to(batch / 'COMPLETE')
    elif failure == 'parentlink':
        sources = batch / 'sources'
        sources.rename(tmp_path / 'saved')
        sources.symlink_to(tmp_path / 'saved', target_is_directory=True)
    else:
        link = tmp_path / 'link'
        link.symlink_to(batch, target_is_directory=True)
        batch = link
    with pytest.raises(ValueError):
        s.validate_batch(batch, P)


def test_existing_corrupt_batch_refuses_republish(tmp_path):
    batch = publish(tmp_path)
    (batch / 'COMPLETE').write_text('f'*64)
    with pytest.raises(ValueError):
        publish(tmp_path)
    assert not list(tmp_path.glob('.pending-*'))


def test_checkpoint_conflict_and_extra_fingerprint():
    cp = s.acknowledge_export(checkpoint(), manifest())
    cp['sources'][A]['sha256'] = 'f'*64
    with pytest.raises(ValueError, match='checkpoint conflicts'):
        s.acknowledge_export(cp, manifest())
    item = manifest()
    item['fingerprints'][B] = H
    with pytest.raises(ValueError, match='fingerprint inventory'):
        s.acknowledge_export(checkpoint(), item)


def test_import_requires_authenticated_aliases_and_retries():
    item = manifest((A, B))
    verified = {A: s.sha(RAW), B: s.sha(RAW)}
    receipt = s.import_receipt(item, P, T, verified, REV)
    assert receipt['source_files'] == 2
    assert receipt['unique_raw_reports'] == 1
    assert s.receipt_matches(receipt, item, P, T)
    for incomplete in ({}, {A:s.sha(RAW)}, dict(verified, **{'e'*32:s.sha(RAW)}), dict(verified, **{B:'f'*64})):
        with pytest.raises(ValueError, match='incomplete'):
            s.import_receipt(item, P, T, incomplete, REV)
    for target, revision in [(P, REV), (T, 'bad'), (T, None)]:
        with pytest.raises(ValueError):
            s.import_receipt(item, P, target, verified, revision)
    with pytest.raises(ValueError):
        s.receipt_matches(dict(receipt, source_files=1), item, P, T)
    # An interrupted importer has no receipt; retrying authenticated acceptance
    # deterministically produces the same immutable acknowledgment.
    assert s.import_receipt(item, P, T, verified, REV) == receipt


def test_baseline_rejects_wrong_projection():
    observed = {A: observation(B)}
    with pytest.raises(ValueError, match='baseline inventory identity'):
        s.baseline(manifest(), P, observed, observed, lambda _: RAW, observed.get)


def test_existing_valid_but_different_batch_refused(tmp_path):
    batch = publish(tmp_path)
    rewrite_manifest(batch, lambda m: m['fingerprints'].update({A:'f'*64}))
    with pytest.raises(ValueError, match='published batch conflict'):
        publish(tmp_path)


@pytest.mark.parametrize('after_publish', [False, True])
def test_publication_crash_recovery(tmp_path, monkeypatch, after_publish):
    before = checkpoint()
    if after_publish:
        sync = s.sync_directory
        def fail_parent(path):
            if Path(path) == tmp_path:
                raise OSError('synthetic durability acknowledgment failure')
            sync(path)
        monkeypatch.setattr(s, 'sync_directory', fail_parent)
    else:
        def fail(*_):
            raise OSError('synthetic rename failure')
        monkeypatch.setattr(s.os, 'rename', fail)
    with pytest.raises(OSError):
        publish(tmp_path)
    assert before == checkpoint()
    completed = list(tmp_path.iterdir())
    if after_publish:
        assert len(completed) == 1
        item = s.validate_batch(completed[0], P)
        recovered = s.acknowledge_export(before, item)
        assert recovered['sources'][A]['sha256'] == s.sha(RAW)
    else:
        assert completed == []
