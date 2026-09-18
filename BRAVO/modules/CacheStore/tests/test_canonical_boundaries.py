"""Canonical cache identity and parallel writer regressions, using disposable storage only."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from modules.CacheStore import store, locks, ledger
from modules.CacheStore.tests.test_locks import _FakeRedis


def test_scope_isolates_inputs_and_code_and_restores_after_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DIR_OVERRIDE', None)
    monkeypatch.setattr(ledger, 'ENABLED', False)
    from django.conf import settings
    monkeypatch.setattr(settings, 'DATASERVER_PATH', str(tmp_path))
    base = store.root_dir()
    with store.canonical_scope(('p', 'source-a', 'code-a')):
        a = store.root_dir()
        assert a != base
        assert store.store('synthetic', 'p', ('v1',), {'value': 42}, writer='biomarkers')
        assert store.load('synthetic', 'p', ('v1',)) == {'value': 42}
        with store.canonical_scope(('p', 'source-b', 'code-a')):
            assert store.root_dir() != a
            assert store.load('synthetic', 'p', ('v1',)) is None
        assert store.root_dir() == a
        with pytest.raises(ValueError):
            with store.canonical_scope(('p', 'source-a', 'code-b')):
                assert store.root_dir() != a
                raise ValueError('synthetic')
        assert store.root_dir() == a
    assert store.root_dir() == base
    assert store.load('synthetic', 'p', ('v1',)) is None


def test_cache_root_disabled_override_environment_and_absent(monkeypatch, tmp_path):
    from django.conf import settings
    monkeypatch.setattr(store, 'ENABLED', False)
    assert store.root_dir(tmp_path) is None
    monkeypatch.setattr(store, 'ENABLED', True)
    assert store.root_dir(tmp_path) == str(tmp_path)
    monkeypatch.setattr(store, 'DIR_OVERRIDE', str(tmp_path))
    assert store.root_dir() == str(tmp_path)
    monkeypatch.setattr(store, 'DIR_OVERRIDE', None)
    monkeypatch.setattr(settings, 'DATASERVER_PATH', None)
    monkeypatch.delenv('DATASERVER_PATH', raising=False)
    assert store.root_dir() is None
    monkeypatch.setenv('DATASERVER_PATH', str(tmp_path))
    assert store.root_dir() == str(tmp_path / 'cache')


def test_same_process_writers_have_unique_temporary_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, 'ENABLED', False)
    paths = []
    original = store._write_payload
    def write(path, *args):
        paths.append(path)
        return original(path, *args)
    monkeypatch.setattr(store, '_write_payload', write)
    for value in (1, 2):
        assert store.store('synthetic', 'p', ('v1',), {'v': value}, writer='biomarkers', root=tmp_path)
    assert len(paths) == len(set(paths)) == 2
    assert store.load('synthetic', 'p', ('v1',), root=tmp_path) == {'v': 2}
    assert not list(tmp_path.rglob('*.tmp'))


@pytest.mark.parametrize('served', [False, True])
def test_waiter_propagates_caller_exception_without_second_yield(monkeypatch, served):
    fake = _FakeRedis({'key': 'other'})
    if not served:
        original = fake.set
        n = [0]
        def acquire(*args, **kwargs):
            n[0] += 1
            if n[0] == 2:
                fake.store.clear()
            return original(*args, **kwargs)
        fake.set = acquire
    monkeypatch.setattr(locks, 'CLIENT_FACTORY', lambda: fake)
    with pytest.raises(ValueError, match='caller failed'):
        with locks.build_lock('key', ready=lambda: served, wait_s=0):
            raise ValueError('caller failed')
    assert (fake.store == {'key': 'other'}) if served else not fake.store


def test_failed_write_removes_partial_temporary_file_and_preserves_committed_value(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, 'ENABLED', False)
    assert store.store('synthetic', 'p', ('v1',), {'value': 'accepted'}, writer='biomarkers', root=tmp_path)
    def interrupted(path, *args):
        from pathlib import Path
        Path(path).write_bytes(b'partial')
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(store, '_write_payload', interrupted)
    assert not store.store('synthetic', 'p', ('v1',), {'value': 'incomplete'}, writer='biomarkers', root=tmp_path)
    assert store.load('synthetic', 'p', ('v1',), root=tmp_path) == {'value': 'accepted'}
    assert not list(tmp_path.rglob('*.tmp'))


def test_disabled_cache_sweep_never_touches_disk(monkeypatch):
    monkeypatch.setattr(store, 'ENABLED', False)
    assert store._sweep_superseded('synthetic', 'p', 'unused') == 0


def test_waiter_redis_failure_yields_one_fallback_and_preserves_other_owners_lock(monkeypatch):
    fake = _FakeRedis({'key': 'other'})
    original = fake.set
    calls = []
    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) > 1:
            raise ConnectionError('synthetic unavailable Redis')
        return original(*args, **kwargs)
    monkeypatch.setattr(fake, 'set', flaky)
    monkeypatch.setattr(locks, 'CLIENT_FACTORY', lambda: fake)
    with pytest.raises(ValueError, match='caller error'):
        with locks.build_lock('key', wait_s=0) as outcome:
            assert outcome.role == 'fallback'
            assert 'redis failed while waiting' in outcome.reason
            raise ValueError('caller error')
    assert fake.store == {'key': 'other'}
