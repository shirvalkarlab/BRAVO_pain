"""Synthetic policy/graph tests. No app, provider or existing storage access."""
from copy import deepcopy
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/daily_import'))
import masked_identity as m

P, I, D, S = ('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32)
H = 'e' * 64
KEY = b'synthetic-key'


def scope():
    return dict(policy=m.POLICY_VERSION, scope='synthetic-scope', participant_uid=P,
                institute_uid=I, device_uid=D, seed_source_uid=S, seed_raw_sha256=H)


def config():
    return dict(target_participant_uid=P, target_institute_uid=I,
                upstream=dict(scope='synthetic-scope', masked_device_binding=scope()))


def report(offset=2, day=2):
    return {'SessionDate': f'2026-01-{day:02}T00:00:00Z',
            'SessionEndDate': f'2026-01-{day:02}T00:01:00Z',
            'DeviceInformation': {phase: dict(NeurostimulatorSerialNumber='███',
                DeviceDateTimeBlockId=7, DeviceDateTimeOffsetInSeconds=offset)
                for phase in ('Initial', 'Final')}}


def clock():
    return dict(agreement={'synthetic': True}, table_digest='a' * 16, configuration_digest='b' * 64)


def receipt(uid='f' * 32, sha='1' * 64, parent=S, parent_sha=H):
    return m.record(scope(), uid, sha, parent, parent_sha, {'synthetic': True}, clock(), KEY)


def trusted(scope, rows):
    return m.trusted_references(scope, rows, KEY)


def row(uid=S, sha=H, admission=None):
    return dict(source_uid=uid, raw_sha256=sha, admission=admission)


@pytest.fixture
def validators(monkeypatch):
    monkeypatch.setattr(m.native_continuity, 'validate_receipt', lambda proof: True)
    monkeypatch.setattr(m.native_continuity, 'validate_clock_receipt', lambda proof: True)


def test_binding_absent_and_exact():
    assert m.binding({'upstream': {}}) is None
    assert m.binding(config()) == scope()
    assert m.binding(config()) is not config()['upstream']['masked_device_binding']


@pytest.mark.parametrize('field,value', [('policy', 'future'), ('scope', 'other'),
    ('participant_uid', '1' * 32), ('institute_uid', '1' * 32),
    ('device_uid', 'bad'), ('seed_source_uid', 'bad'), ('seed_raw_sha256', 'bad')])
def test_binding_invalid(field, value):
    cfg = config(); cfg['upstream']['masked_device_binding'][field] = value
    with pytest.raises(ValueError): m.binding(cfg)


@pytest.mark.parametrize('value', [False, [], {}, {**scope(), 'extra': True}])
def test_binding_shape(value):
    cfg = config(); cfg['upstream']['masked_device_binding'] = value
    with pytest.raises(ValueError): m.binding(cfg)


def test_masked_serial_and_advancing():
    assert m.masked_serial(report()) == '███'
    assert m.advancing_session(report(), report(1, 1)) is None


@pytest.mark.parametrize('change', [
    lambda r: r.clear(), lambda r: r.update(DeviceInformation=[]),
    lambda r: r['DeviceInformation']['Initial'].update(NeurostimulatorSerialNumber=None),
    lambda r: r['DeviceInformation']['Initial'].update(NeurostimulatorSerialNumber=''),
    lambda r: r['DeviceInformation']['Initial'].update(NeurostimulatorSerialNumber='██'),
    lambda r: [r['DeviceInformation'][p].update(NeurostimulatorSerialNumber='UNKNOWN') for p in ('Initial', 'Final')],
    lambda r: [r['DeviceInformation'][p].update(NeurostimulatorSerialNumber='ABC█') for p in ('Initial', 'Final')],
])
def test_masked_serial_invalid(change):
    r = report(); change(r)
    with pytest.raises(ValueError): m.masked_serial(r)


@pytest.mark.parametrize('change', [
    lambda r: r.update(SessionDate='2026-01-02T00:02:00Z'),
    lambda r: r.update(SessionEndDate='2026-01-02T00:01:00'),
    lambda r: r.update(SessionDate=None),
    lambda r: r['DeviceInformation']['Initial'].update(DeviceDateTimeBlockId=True),
    lambda r: r['DeviceInformation']['Final'].update(DeviceDateTimeBlockId=True),
    lambda r: r['DeviceInformation']['Initial'].update(DeviceDateTimeBlockId=-1),
    lambda r: r['DeviceInformation']['Initial'].update(DeviceDateTimeBlockId=8),
    lambda r: r['DeviceInformation']['Initial'].update(DeviceDateTimeOffsetInSeconds=3),
    lambda r: r['DeviceInformation']['Initial'].update(DeviceDateTimeOffsetInSeconds=-1),
    lambda r: r['DeviceInformation']['Initial'].update(DeviceDateTimeOffsetInSeconds=float('nan')),
    lambda r: r['DeviceInformation']['Initial'].update(DeviceDateTimeOffsetInSeconds='2'),
    lambda r: r['DeviceInformation']['Initial'].update(DeviceDateTimeOffsetInSeconds=10**400),
])
def test_session_invalid(change):
    r = report(); change(r)
    with pytest.raises(ValueError): m.advancing_session(r, report(1, 1))


@pytest.mark.parametrize('candidate,reference', [(report(1), report(2, 1)),
    (report(2, 1), report(1, 2)), (report(2), report(2, 1)),
    ({**report(), 'DeviceInformation': {p: {**report()['DeviceInformation'][p], 'DeviceDateTimeBlockId': 8} for p in ('Initial','Final')}}, report(1, 1))])
def test_old_or_changed_block(candidate, reference):
    with pytest.raises(ValueError): m.advancing_session(candidate, reference)


def test_both_authoritative_tablet_session_bounds_must_advance():
    candidate=report(3,3);reference=report(1,1)
    candidate['SessionDate']=reference['SessionDate']
    with pytest.raises(ValueError):m.advancing_session(candidate,reference)
    candidate=report(3,3);reference=report(1,1)
    reference['SessionEndDate']='2026-01-04T00:00:00Z'
    with pytest.raises(ValueError):m.advancing_session(candidate,reference)


def test_rooted_graph_and_rolling_reference(validators):
    first = row('f' * 32, '1' * 64, receipt())
    second = row('2' * 32, '3' * 64, receipt('2' * 32, '3' * 64, 'f' * 32, '1' * 64))
    unrelated = row('4' * 32, '5' * 64, receipt('4' * 32, '5' * 64, '6' * 32, '7' * 64))
    result = trusted(scope(), [second, unrelated, first, row()])
    assert {(r['source_uid'], r['raw_sha256']) for r in result} == {(S, H), ('f' * 32, '1' * 64), ('2' * 32, '3' * 64)}
    # A cycle unrelated to the seed supplies no permission.
    a = row('8'*32, '9'*64, receipt('8'*32, '9'*64, 'a'*32, 'b'*64))
    b = row('a'*32, 'b'*64, receipt('a'*32, 'b'*64, '8'*32, '9'*64))
    assert trusted(scope(), [a, b, row()]) == [row()]


@pytest.mark.parametrize('change', [
    lambda r: r.update(policy='future'), lambda r: r.update(binding_sha256='0'*64),
    lambda r: r.update(source_uid='0'*32), lambda r: r.update(raw_sha256='0'*64),
    lambda r: r.update(continuity={}), lambda r: r.update(continuity=[]),
    lambda r: r.update(clock={}), lambda r: r.update(clock=[]),
    lambda r: r.update(extra=True), lambda r: r['clock'].update(extra=True),
    lambda r: r['clock'].update(table_digest='z'*16),
    lambda r: r['clock'].update(table_digest=[]),
    lambda r: r['clock'].update(table_digest='a'),
    lambda r: r['clock'].update(configuration_digest='wrong'),
])
def test_bad_descendants_do_not_extend_trust(validators, change):
    cert = receipt(); change(cert)
    assert trusted(scope(), [row(), row('f'*32, '1'*64, cert)]) == [row()]


@pytest.mark.parametrize('field', ['validate_receipt', 'validate_clock_receipt'])
def test_tampered_proof_rejected(validators, monkeypatch, field):
    def invalid(value): raise ValueError('tampered')
    monkeypatch.setattr(m.native_continuity, field, invalid)
    assert trusted(scope(), [row(), row('f'*32, '1'*64, receipt())]) == [row()]


def test_missing_or_duplicate_seed():
    with pytest.raises(ValueError, match='seed unavailable'): trusted(scope(), [])
    with pytest.raises(ValueError, match='ambiguous'): trusted(scope(), [row(), row()])
    assert trusted(scope(), [row(), row('f'*32, '1'*64, [])]) == [row()]


@pytest.mark.parametrize('key', [None, '', b'', bytearray(b'synthetic')])
def test_signing_key_must_be_existing_nonempty_bytes(key):
    with pytest.raises(ValueError):m.validate_key(key)
    with pytest.raises(ValueError):m.trusted_references(scope(),[row()],key)
    with pytest.raises(ValueError):m.record(scope(),'f'*32,'1'*64,S,H,{'proof':True},clock(),key)


@pytest.mark.parametrize('change', [
    lambda cert:cert.update(admission_hmac_sha256='0'*64),
    lambda cert:cert.update(admission_hmac_sha256='bad'),
    lambda cert:cert['continuity'].update(unreviewed=True),
    lambda cert:cert['clock'].update(configuration_digest='0'*64),
    lambda cert:cert.update(reference_source_uid='0'*32),
    lambda cert:cert.update(reference_source_uid=[]),
    lambda cert:cert.update(reference_raw_sha256='0'*64),
])
def test_tampering_cannot_manufacture_an_adapter_issued_reference(validators, change):
    cert=receipt();change(cert)
    assert trusted(scope(),[row(),row('f'*32,'1'*64,cert)])==[row()]


@pytest.mark.parametrize('key,domain', [(b'other-target-key',m.SIGNING_DOMAIN),(KEY,b'other-purpose\0'),(KEY,b'')])
def test_cross_key_and_cross_protocol_signatures_do_not_authorize(validators,key,domain):
    cert=receipt();payload={k:v for k,v in cert.items() if k!='admission_hmac_sha256'}
    cert['admission_hmac_sha256']=hmac.new(key,domain+json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode(),hashlib.sha256).hexdigest()
    assert trusted(scope(),[row(),row('f'*32,'1'*64,cert)])==[row()]


def test_domain_and_entire_record_are_signed_independently():
    cert=receipt();payload={k:v for k,v in cert.items() if k!='admission_hmac_sha256'}
    expected=hmac.new(KEY,b'BRAVO/masked-native-admission/v1\0'+json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode(),hashlib.sha256).hexdigest()
    assert cert['admission_hmac_sha256']==expected


def test_real_measurement_and_clock_proofs_form_repeated_signed_descendants():
    # Reuse the independently constructed synthetic native measurement fixture;
    # unlike graph-unit doubles above, both production proof validators run here.
    spec=importlib.util.spec_from_file_location('synthetic_native_fixture',
        Path(__file__).resolve().parents[1]/'test_daily_import_native_continuity.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    docs=[fixture.report(count) for count in (3,4,5)]
    hashes=[hashlib.sha256(json.dumps(doc,sort_keys=True).encode()).hexdigest() for doc in docs]
    bind=scope();bind['seed_raw_sha256']=hashes[0]
    ids=[S,'1'*32,'2'*32]
    records=[row(ids[0],hashes[0])]
    for index in (1,2):
        proof=m.native_continuity.prove_continuity(docs[index],docs[index-1])
        dates=m.native_continuity.verify_clock_agreement(docs[index],docs[index-1])
        evidence=dict(agreement=dates,table_digest='a'*16,configuration_digest='b'*64)
        cert=m.record(bind,ids[index],hashes[index],ids[index-1],hashes[index-1],proof,evidence,KEY)
        records.append(row(ids[index],hashes[index],cert))
    assert len(m.trusted_references(bind,list(reversed(records)),KEY))==3
    # A caller can edit source metadata and recompute a public self-hash, but
    # cannot transfer this certificate to different raw bytes/source identity.
    copied=deepcopy(records[-1]);copied['source_uid']='3'*32
    copied['raw_sha256']='4'*64
    copied['admission']['source_uid']=copied['source_uid']
    copied['admission']['raw_sha256']=copied['raw_sha256']
    assert len(m.trusted_references(bind,records+[copied],KEY))==3
    # Replacing one otherwise well-formed cryptographic proof, then rehashing it,
    # still invalidates the adapter signature over the complete certificate.
    copied=deepcopy(records[-1]);copied['admission']['continuity']['candidate_intrinsic_sha256']='5'*64
    fixture.rehash(copied['admission']['continuity'])
    assert len(m.trusted_references(bind,records[:-1]+[copied],KEY))==2
