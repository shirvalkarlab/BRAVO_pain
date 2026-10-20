"""Source attempt evidence and independent stream failures use synthetic files."""
import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'daily_import'))
import upstream_source as source
import state

SHA = 'a' * 64

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(source.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(source.os, 'fchown', Mock())
    return {'owner_uid': 10001, 'status_path': str(tmp_path / 'attempt.json'), 'dropbox': {}, 'clinic': {}}


def test_independent_success_and_status_publication(setup):
    values = iter([100, 110])
    result = source.execute(setup, {'neural': lambda c: {'status':'success','manifest_sha256':SHA,'files':2,'downloaded_files':1},
                                   'clinic': lambda c: {'status':'success','manifest_sha256':SHA,'fresh_files':32,'retained_files':1}}, lambda:next(values))
    assert result['clinic']['retained_files'] == 1
    assert source.availability(setup['status_path'], 115) == {'neural':True,'clinic':True}
    assert Path(setup['status_path']).stat().st_mode & 0o777 == 0o600
    assert not list(Path(setup['status_path']).parent.glob('.pending-*'))


@pytest.mark.parametrize('result', [{}, {'status':'success','deferred':True}, {'status':'success','manifest_sha256':'bad'},
    {'status':'success','manifest_sha256':SHA,'files':True}, {'status':'success','manifest_sha256':SHA,'files':-1}, None])
def test_partial_failure_still_fetches_other_stream(setup, result):
    clinic = Mock(return_value={'status':'success','manifest_sha256':SHA})
    observed=source.execute(setup, {'neural':lambda c:result,'clinic':clinic}, lambda:100)
    assert observed['neural']=={'status':'failed','error_code':'source_failed'}
    clinic.assert_called_once()
    assert source.availability(setup['status_path'],110)=={'neural':False,'clinic':True}


def test_default_adapter_dispatch(setup, monkeypatch):
    import upstream_dropbox, upstream_clinic
    for module, name in [(upstream_dropbox,'run'),(upstream_clinic,'refresh')]:
        monkeypatch.setattr(module,name,Mock(return_value={'status':'success','manifest_sha256':SHA}))
    assert source.execute(setup,clock=lambda:100)['neural']['status']=='success'


@pytest.mark.parametrize('owner,uid', [(0,0),(True,0),(10001,10001)])
def test_root_owner_guard(setup,monkeypatch,owner,uid):
    setup['owner_uid']=owner
    monkeypatch.setattr(source.os,'geteuid',lambda:uid)
    with pytest.raises(ValueError): source.execute(setup,{})


def test_write_failure_removes_temporary(setup,monkeypatch):
    monkeypatch.setattr(source.os,'replace',Mock(side_effect=OSError('synthetic')))
    with pytest.raises(OSError): source.write_status(setup['status_path'],{},10001)
    assert not list(Path(setup['status_path']).parent.iterdir())


@pytest.mark.parametrize('alter', [
    lambda r:r.update(extra=True),lambda r:r.update(format=True),lambda r:r.update(format=2),
    lambda r:r.update(started_at=True),lambda r:r.update(finished_at=None),lambda r:r.update(started_at=-100000),
    lambda r:r.update(started_at=112),lambda r:r.update(finished_at=200),lambda r:r.update(started_at=float('nan')),
    lambda r:r.update(streams={}),lambda r:r['streams']['neural'].update(manifest_sha256='bad'),
    lambda r:r['streams'].update(neural=None),
])
def test_malformed_stale_or_interrupted_evidence_unavailable(setup,alter):
    report={'format':1,'started_at':100,'finished_at':110,'streams':{n:{'status':'success','manifest_sha256':SHA} for n in source.STREAMS}}
    alter(report)
    Path(setup['status_path']).write_text(json.dumps(report))
    assert source.availability(setup['status_path'],115)=={'neural':False,'clinic':False}


def test_missing_bounded_and_current_clock(setup,monkeypatch):
    assert not any(source.availability(setup['status_path']).values())
    Path(setup['status_path']).write_bytes(b'x'*17000)
    assert not any(source.availability(setup['status_path']).values())
    source.execute(setup,{n:lambda c:{'status':'success','manifest_sha256':SHA} for n in source.STREAMS},lambda:100)
    monkeypatch.setattr(source.time,'time',lambda:110)
    assert all(source.availability(setup['status_path']).values())


def test_initial_status_write_failure_is_not_new_fetch_attestation(setup,monkeypatch):
    functions={n:Mock(return_value={'status':'success','manifest_sha256':SHA}) for n in source.STREAMS}
    source.execute(setup,functions,lambda:100)
    prior=Path(setup['status_path']).read_bytes()
    for callback in functions.values():callback.reset_mock()
    monkeypatch.setattr(source,'write_status',Mock(side_effect=OSError('read-only')))
    with pytest.raises(OSError):source.execute(setup,functions,lambda:120)
    assert Path(setup['status_path']).read_bytes()==prior
    for callback in functions.values():callback.assert_not_called()
    # Daily policy is last verified fetch <24h, never current-attempt attestation.
    assert all(source.availability(setup['status_path'],130).values())
