"""Synthetic Dropbox snapshots: no provider calls or real credentials."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2] / 'scripts/daily_import'
for name in ('state', 'upstream_dropbox'):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
u = sys.modules['upstream_dropbox']
s = u.state
RAW = b'{"SessionDate":"2026-01-01T00:00:00Z","DeviceInformation":{}}'


def row(identity='id:synthetic', path='report.json', raw=RAW):
    return {'ID': identity, 'Path': path, 'Size': len(raw), 'IsDir': False,
        'ModTime': '2026-01-02T00:00:00Z', 'Hashes': {'DropboxHash': u.content_hash(raw)}}


class Client:
    def __init__(self, rows=None, raws=None):
        self.rows = rows or [row()]
        self.raws = raws or {'report.json': RAW}
        self.downloaded = []
        self.calls = 0
        self.after = None

    def inventory(self):
        self.calls += 1
        return u.inventory(self.after if self.calls % 2 == 0 and self.after is not None else self.rows)

    def download(self, metadata):
        self.downloaded.append(metadata['path'])
        return self.raws[metadata['path']]


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(u.os, 'chown', lambda *a, **kw: None)
    monkeypatch.setattr(u.shutil, 'disk_usage', lambda _: SimpleNamespace(free=100*1024**3))
    batches = tmp_path / 'batches'
    batches.mkdir()
    original = tmp_path / 'rclone.conf'
    original.write_text('[dropbox]\ntype = dropbox\ntoken = SYNTHETIC\n[unrelated]\ntype = other\ntoken = OTHER_SYNTHETIC\n')
    return {'scope': 'synthetic-scope', 'remote': 'dropbox:synthetic-scope',
        'rclone_config': str(original), 'rclone_binary': '/usr/bin/rclone',
        'batches': str(batches), 'checkpoint': str(tmp_path / 'checkpoint.json'),
        'owner_uid': 10001}


@pytest.mark.parametrize('value', [None, '', 'a\n', 1, 'x'*4097])
def test_bad_text(value):
    with pytest.raises(ValueError):
        u.text(value)


@pytest.mark.parametrize('value', ['/absolute', '../escape', 'a/../escape', 'a\\b', 'a//b', 'a/./b'])
def test_bad_paths(value):
    with pytest.raises(ValueError):
        u.relative(value)


def test_content_hash_independent_known_algorithm():
    import hashlib
    raw = b'x' * (u.BLOCK_SIZE + 1)
    expected = hashlib.sha256(hashlib.sha256(b'x'*u.BLOCK_SIZE).digest() + hashlib.sha256(b'x').digest()).hexdigest()
    assert u.content_hash(raw) == expected
    assert u.content_hash(b'') == hashlib.sha256(b'').hexdigest()


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(ID=''), lambda r: r.update(Path='../x.json'),
    lambda r: r.update(Size=0), lambda r: r.update(Size=True),
    lambda r: r.update(Size=s.MAX_FILE+1), lambda r: r.update(IsDir=True),
    lambda r: r.update(Path='other.csv'), lambda r: r.update(ModTime='2026-01-01'),
    lambda r: r.update(Hashes={}), lambda r: r.update(Hashes={'DropboxHash':'bad'}),
    lambda r: r.update(Hashes={'DropboxHash':'a'*64,'dropbox':'b'*64}),
    lambda r: r.update(Revision=''),
])
def test_inventory_invalid(mutate):
    item = row()
    mutate(item)
    with pytest.raises(ValueError):
        u.inventory([item])


def test_inventory_identity_limits(monkeypatch):
    for invalid in (None, {}, []):
        with pytest.raises(ValueError):
            u.inventory(invalid)
    with pytest.raises(ValueError, match='repeated'):
        u.inventory([row(), row()])
    with pytest.raises(ValueError, match='repeated'):
        u.inventory([row(), row(identity='id:other')])
    item = row()
    item['Revision'] = 'actual-revision'
    assert u.inventory([item])[item['ID']]['revision'] == 'actual-revision'
    monkeypatch.setattr(s, 'MAX_FILES', 1)
    with pytest.raises(ValueError):
        u.inventory([row(), row(identity='id:other', path='other.json')])
    monkeypatch.setattr(s, 'MAX_TOTAL', 1)
    with pytest.raises(ValueError, match='total'):
        u.inventory([row()])


def test_snapshot_retry_and_aliases(config):
    client = Client([row(), row('id:alias', 'alias.json')], {'report.json':RAW, 'alias.json':RAW})
    first = u.snapshot(config, client)
    assert first['files'] == 2 and first['downloaded_files'] == 2 and not first['unchanged']
    batch = Path(config['batches']) / first['manifest_sha256']
    assert len(list((batch / 'sources').iterdir())) == 1
    manifest = json.loads((batch / 'upstream.manifest').read_bytes())
    assert manifest['count'] == 2 and manifest['total_bytes'] == 2*len(RAW)
    assert manifest['files'][0]['revision'] is None
    assert set(manifest) == {'format','kind','provider','scope','count','total_bytes','files'}
    assert {e['provider_id'] for e in manifest['files']} == {'id:synthetic','id:alias'}
    second = u.snapshot(config, client)
    assert second['unchanged'] and second['downloaded_files'] == 0
    assert client.downloaded == ['alias.json', 'report.json']
    assert len(list(Path(config['batches']).iterdir())) == 1
    for path in batch.rglob('*'):
        assert path.stat().st_mode & 0o077 == 0
    assert Path(config['checkpoint']).stat().st_mode & 0o777 == 0o600


def test_changed_provider_preserves_original_snapshot(config):
    first = u.snapshot(config, Client())
    changed_raw = RAW + b' '
    client = Client([row(raw=changed_raw)], {'report.json':changed_raw})
    second = u.snapshot(config, client)
    assert second['downloaded_files'] == 1 and second['manifest_sha256'] != first['manifest_sha256']
    assert len(list(Path(config['batches']).iterdir())) == 2
    # Removed files never delete their previously published immutable snapshots.
    third = u.snapshot(config, Client([row('id:other','other.json')], {'other.json':RAW}))
    assert third['files'] == 1 and len(list(Path(config['batches']).iterdir())) == 3


@pytest.mark.parametrize('failure', ['unstable', 'hash', 'size', 'invalidjson', 'read'])
def test_failed_snapshot_preserves_checkpoint(config, failure):
    u.snapshot(config, Client())
    previous = Path(config['checkpoint']).read_bytes()
    raw = RAW + b' '
    client = Client([row('id:new', 'new.json', raw)], {'new.json':raw})
    if failure == 'unstable':
        client.after = [row('id:new', 'new.json', RAW)]
    elif failure == 'hash':
        client.raws['new.json'] = RAW + b'\n'
    elif failure == 'size':
        client.raws['new.json'] = RAW
    elif failure == 'invalidjson':
        client.raws['new.json'] = b'{}'
    else:
        client.raws.clear()
    with pytest.raises((ValueError, KeyError)):
        u.snapshot(config, client)
    assert Path(config['checkpoint']).read_bytes() == previous
    assert len(list(Path(config['batches']).iterdir())) == 1


def test_cached_payload_corruption_rejected(config):
    result = u.snapshot(config, Client())
    raw_path = next((Path(config['batches']) / result['manifest_sha256'] / 'sources').iterdir())
    raw_path.write_bytes(RAW + b' ')
    with pytest.raises(ValueError, match='cached'):
        u.snapshot(config, Client())


@pytest.mark.parametrize('kind', ['extra', 'complete', 'manifest', 'extra_source', 'payload'])
def test_existing_snapshot_conflict(config, kind):
    result = u.snapshot(config, Client())
    batch = Path(config['batches']) / result['manifest_sha256']
    # Force authenticated downloads on retry so corruption is checked at publication.
    Path(config['checkpoint']).unlink()
    if kind == 'extra':
        (batch/'extra').touch()
    elif kind == 'complete':
        (batch/'COMPLETE').write_text('f'*64+'\n')
    elif kind == 'manifest':
        (batch/'upstream.manifest').write_text('{}')
    elif kind == 'extra_source':
        (batch/'sources'/'extra').touch()
    else:
        next((batch/'sources').iterdir()).write_bytes(RAW + b' ')
    with pytest.raises(ValueError):
        u.snapshot(config, Client())
    assert not Path(config['checkpoint']).exists()
    assert not list(Path(config['batches']).glob('.pending-*'))


@pytest.mark.parametrize('owner', [0, -1, True, '10001'])
def test_owner_guard(config, owner):
    config['owner_uid'] = owner
    with pytest.raises(ValueError):
        u.snapshot(config, Client())


def test_checkpoint_schema(config):
    path = Path(config['checkpoint'])
    for item in ({'format':True,'scope':config['scope'],'files':{}}, {'format':1,'scope':'wrong','files':{}}, {'format':1,'scope':config['scope'],'files':[]}, {'format':1,'scope':config['scope'],'files':{'id':{'metadata':{'provider_id':'wrong'},'batch':'a'*64,'sha256':'b'*64}}}):
        s.atomic_json(path, item)
        with pytest.raises(ValueError):
            u.read_checkpoint(path, config['scope'])


def test_checkpoint_commit_crash_recovers_published_batch(config, monkeypatch):
    original = s.atomic_json
    def fail(*args):
        raise OSError('synthetic checkpoint write failure')
    monkeypatch.setattr(s, 'atomic_json', fail)
    with pytest.raises(OSError):
        u.snapshot(config, Client())
    assert not Path(config['checkpoint']).exists()
    assert len(list(Path(config['batches']).iterdir())) == 1
    monkeypatch.setattr(s, 'atomic_json', original)
    assert u.snapshot(config, Client())['unchanged']


def test_isolated_credentials_scoped_and_removed(config):
    original = Path(config['rclone_config']).read_bytes()
    with u.isolated_client(config) as client:
        copy_path = Path(client.config)
        assert copy_path.stat().st_mode & 0o777 == 0o600
        contents = copy_path.read_text()
        assert 'SYNTHETIC' in contents and 'unrelated' not in contents and 'OTHER_SYNTHETIC' not in contents
        copy_path.write_text('refreshed-copy-only')
    assert not copy_path.exists()
    assert Path(config['rclone_config']).read_bytes() == original


def test_original_config_change_detected(config):
    with pytest.raises(ValueError, match='original Dropbox'):
        with u.isolated_client(config):
            Path(config['rclone_config']).write_text('[dropbox]\ntype=dropbox\ntoken=changed-synthetic\n')


def test_wrong_config_type(config):
    Path(config['rclone_config']).write_text('[dropbox]\ntype=other\n')
    with pytest.raises(ValueError):
        with u.isolated_client(config):
            pass


def test_rclone_command_boundaries(config, monkeypatch):
    with u.isolated_client(config) as client:
        assert client.command('cat', 'sub/report.json')[2] == config['remote'] + '/sub/report.json'
        assert '--config' in client.command('lsjson')
        seen = []
        def run(command, **kwargs):
            seen.append((command, kwargs))
            kwargs['preexec_fn']()
            kwargs['stdout'].write(json.dumps([row()]).encode() if command[1] == 'lsjson' else RAW)
        monkeypatch.setattr(u.subprocess, 'run', run)
        bounds = []
        monkeypatch.setattr(u.resource, 'setrlimit', lambda *args: bounds.append(args))
        assert client.inventory() == u.inventory([row()])
        assert client.download(u.inventory([row()])['id:synthetic']) == RAW
        assert '--hash' in seen[0][0] and '--recursive' in seen[0][0]
        assert seen[0][1]['timeout'] == 180 and seen[1][1]['timeout'] == 600
        assert seen[0][1]['stderr'] == subprocess.DEVNULL and bounds
        assert set(seen[0][1]['env']) == {'PATH', 'HOME', 'LANG'}
        assert seen[0][1]['env']['HOME'] == str(Path(client.config).parent)
        with pytest.raises(ValueError):
            client.execute(client.command('cat', 'report.json'), 1, 10)
    with pytest.raises(ValueError):
        u.Rclone('/usr/bin/rclone', 'other:scope', '/tmp/config')


def test_run_wrapper(config, monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def fake(_):
        yield Client()
    monkeypatch.setattr(u, 'isolated_client', fake)
    assert u.run(config)['status'] == 'success'


def test_insufficient_space_preserves_state(config, monkeypatch):
    u.snapshot(config, Client())
    prior = Path(config['checkpoint']).read_bytes()
    monkeypatch.setattr(u.shutil, 'disk_usage', lambda _: SimpleNamespace(free=1))
    client = Client()
    with pytest.raises(ValueError, match='staging reserve'):
        u.snapshot(config, client)
    assert client.calls == 0
    assert Path(config['checkpoint']).read_bytes() == prior
    assert len(list(Path(config['batches']).iterdir())) == 1
