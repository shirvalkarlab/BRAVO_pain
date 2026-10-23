"""Exercise the prospective runtime boundary without Django/services/providers."""
import contextlib
from copy import deepcopy
import hashlib
import hmac
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/daily_import'))
import upstream_target as u
import masked_identity as policy

P, I, D, S = ('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32)
KEY, SERIAL = b'synthetic-key', 'SYNTHETIC-CONCRETE'


def report(offset=2, day=2):
    return {'SessionDate': f'2026-01-{day:02}T00:00:00Z', 'SessionEndDate': f'2026-01-{day:02}T00:01:00Z',
            'DeviceInformation': {phase: {'NeurostimulatorSerialNumber': '███',
                'DeviceDateTimeBlockId': 7, 'DeviceDateTimeOffsetInSeconds': offset}
                for phase in ('Initial', 'Final')},
            'LeadConfiguration': {phase:[{'type':'synthetic-lead','name':'Left target',
                'channel_count':2,'channel_names':['0','1']}] for phase in ('Initial','Final')}}


def anchor(report):
    return dict(block=7, final_offset_s=report['DeviceInformation']['Final']['DeviceDateTimeOffsetInSeconds'],
                anchor_s=1, rule='SessionEndDate-Final', session_date_s=report['DeviceInformation']['Final']['DeviceDateTimeOffsetInSeconds'])


@pytest.fixture
def case(tmp_path, monkeypatch):
    raw = json.dumps(report(1, 1)).encode(); digest = hashlib.sha256(raw).hexdigest()
    root = tmp_path / 'raws'; (root / P).mkdir(parents=True)
    path = root / P / (S + '.json'); path.write_bytes(raw)
    row = NS(uid=S, device=D, owner_id=P, institute=I, type='MedtronicJSON', pointer=str(path),
             metadata={'Device': D, 'ClockAnchor': anchor(report(1, 1))}, save=Mock())
    lead=NS(type='synthetic-lead',target='Left target',channel_count=2,channel_names=['0','1'])
    device = NS(uid=D, owner_id=P, serial_number=SERIAL,electrodes=NS(all=lambda:[lead]))
    models = NS(DBSDevice=NS(objects=NS(filter=Mock(return_value=[device]))),matchDevice=Mock(return_value=True))
    runtime = u.Runtime(models, Mock(return_value=raw), Mock(), contextlib.nullcontext,
                        NS(uid=P, institute_id=I), root)
    runtime.existing = Mock(return_value=row); runtime.verify = Mock()
    # Stored compression/HMAC allocation bounds have their own actual-byte
    # adapter suite; this boundary suite controls only the already bounded load.
    monkeypatch.setattr(u.target_adapter, 'bounded_load', lambda row, loader: loader(row))
    dc = NS(implant_device_uids=Mock(return_value=[D]), _masked_ingest_device_uid=Mock(return_value=D))
    table = NS(digest=lambda: 'a' * 16)
    dc._ingest_clock_table = Mock(return_value=(anchor(report()), table))
    tc = NS(export_anchor=Mock(side_effect=anchor),
            convert_export=Mock(return_value={'left_out': {}, 'left_unconverted': {}}))
    modules = ModuleType('modules'); modules.__path__ = []; modules.DataCurator = dc
    med = ModuleType('modules.MedtronicPercept'); med.TabletClock = tc
    med.Session=NS(extractPatientInformation=lambda report:{'Device':{'Type':'Synthetic Percept','ConnectedLeads':report['LeadConfiguration']['Final']}})
    common = ModuleType('modules.DecodeCommon'); common.__path__ = []
    clinical = ModuleType('modules.DecodeCommon.private_clinical_config'); clinical.config_digest = lambda: 'b' * 64
    for name, module in [('modules', modules), ('modules.MedtronicPercept', med),
                         ('modules.DecodeCommon', common), ('modules.DecodeCommon.private_clinical_config', clinical)]:
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(u.native_continuity, 'prove_continuity', Mock(return_value={'proof': 'synthetic'}))
    monkeypatch.setattr(u.native_continuity, 'verify_clock_agreement', Mock(return_value={'clock': 'synthetic'}))
    binding = dict(policy=policy.POLICY_VERSION, scope='synthetic', participant_uid=P, institute_uid=I,
                   device_uid=D, seed_source_uid=S, seed_raw_sha256=digest)
    return NS(runtime=runtime, row=row, raw=raw, digest=digest, binding=binding, index={digest: row},
              dc=dc, tc=tc, device=device, root=root, clinical=clinical,lead=lead,models=models)


def prepare(c):
    c.runtime.prepare_masked(c.binding, c.index, KEY, [SERIAL])


def test_end_to_end_boundary_proof_and_metadata_atomic_readback(case):
    c = case; prepare(c)
    raw = json.dumps(report()).encode(); sha = hashlib.sha256(raw).hexdigest()
    assert c.runtime.admit_masked(raw, {'sha256': sha}) is True
    assert c.dc._masked_ingest_device_uid.call_count == 2
    assert c.dc._masked_ingest_device_uid.call_args_list[0].args[0]['DeviceInformation']['Final'] == report()['DeviceInformation']['Initial']
    out = NS(uid='f'*32, device=D, owner_id=P, institute=I, metadata={'Device': D}, save=Mock())
    c.runtime.save_upstream([(out, {'raw_sha256': sha})])
    saved = out.metadata['MaskedDeviceAdmission']
    assert saved['source_uid'] == 'f'*32 and saved['raw_sha256'] == sha
    assert saved['reference_source_uid'] == S and saved['binding_sha256'] == policy.digest(c.binding)
    assert out.metadata['UpstreamSource'] == {'raw_sha256': sha}
    c.runtime.verify_masked_admission(out,sha)
    out.save.assert_called_once_with(update_fields=['metadata'])
    assert len(c.runtime._masked_raw_cache) == 1


@pytest.mark.parametrize('change', [
    lambda c: setattr(c.runtime.person, 'institute_id', '0'*32),
    lambda c: setattr(c.clinical, 'config_digest', lambda:'clinical-config-unavailable-v1'),
    lambda c: c.dc.implant_device_uids.configure_mock(return_value=[]),
    lambda c: setattr(c.device, 'owner_id', '0'*32),
    lambda c: setattr(c.device, 'serial_number', 'UNAPPROVED'),
    lambda c: setattr(c.device, 'uid', '0'*32),
    lambda c: setattr(c.device.electrodes, 'all', lambda:[]),
    lambda c: setattr(c.row, 'device', '0'*32),
    lambda c: setattr(c.row, 'owner_id', '0'*32),
    lambda c: setattr(c.row, 'institute', '0'*32),
    lambda c: setattr(c.row, 'type', 'DefaultType'),
    lambda c: setattr(c.row, 'pointer', '/wrong/path'),
    lambda c: c.row.metadata.update(Device='0'*32),
    lambda c: c.runtime.existing.configure_mock(return_value=None),
    lambda c: c.row.metadata.update(ClockAnchor=None),
    lambda c: c.row.metadata['ClockAnchor'].update(anchor_s=99),
    lambda c: c.tc.export_anchor.configure_mock(side_effect=None, return_value=None),
    lambda c: c.row.metadata['ClockAnchor'].update(final_offset_s='bad'),
    lambda c: c.row.metadata['ClockAnchor'].update(final_offset_s=float('nan')),
    lambda c: c.row.metadata['ClockAnchor'].update(session_date_s='bad'),
    lambda c: c.row.metadata['ClockAnchor'].update(session_date_s=float('inf')),
    lambda c: c.row.metadata['ClockAnchor'].update(block=9),
])
def test_scope_reference_or_native_binding_fail_closed(case, change):
    change(case)
    with pytest.raises((ValueError, KeyError)): prepare(case)
    case.runtime.command.assert_not_called()


@pytest.mark.parametrize('change', [
    lambda c: c.dc._masked_ingest_device_uid.configure_mock(return_value=None),
    lambda c: c.dc._masked_ingest_device_uid.configure_mock(side_effect=[D, '0'*32]),
    lambda c: c.dc._ingest_clock_table.configure_mock(return_value=(None, None)),
    lambda c: c.tc.convert_export.configure_mock(return_value={'left_out': {'missing': 1}, 'left_unconverted': {}}),
    lambda c: c.tc.convert_export.configure_mock(return_value={'left_out': {}, 'left_unconverted': {'missing': 1}}),
    lambda c: c.tc.convert_export.configure_mock(side_effect=[{'left_out': {}, 'left_unconverted': {}}, {'left_out': {'missing':1}, 'left_unconverted': {}}]),
    lambda c: c.tc.convert_export.configure_mock(side_effect=[{'left_out': {}, 'left_unconverted': {}}, {'left_out': {}, 'left_unconverted': {'missing':1}}]),
])
def test_admission_requires_both_native_phases_and_complete_clocks(case, change):
    prepare(case); change(case)
    with pytest.raises(ValueError): case.runtime.admit_masked(json.dumps(report()).encode(), {'sha256':'f'*64})
    assert not case.runtime._masked_admissions
    case.runtime.command.assert_not_called()


@pytest.mark.parametrize('name', ['prove_continuity', 'verify_clock_agreement'])
def test_proof_failure_never_falls_back(case, monkeypatch, name):
    prepare(case)
    monkeypatch.setattr(u.native_continuity, name, Mock(side_effect=ValueError('conflict')))
    with pytest.raises(ValueError): case.runtime.admit_masked(json.dumps(report()).encode(), {'sha256':'f'*64})
    assert not case.runtime._masked_admissions


def test_configuration_change_during_proof_or_before_save_is_rejected(case):
    c=case;prepare(c)
    c.clinical.config_digest=lambda:'0'*64
    with pytest.raises(ValueError,match='configuration changed'):
        c.runtime.admit_masked(json.dumps(report()).encode(),{'sha256':'f'*64})
    assert not c.runtime._masked_admissions
    c.clinical.config_digest=lambda:'b'*64
    c.runtime.admit_masked(json.dumps(report()).encode(),{'sha256':'f'*64})
    c.clinical.config_digest=lambda:'0'*64
    with pytest.raises(ValueError,match='configuration changed'):
        c.runtime.save_upstream([(c.row,{'raw_sha256':'f'*64})])
    c.row.save.assert_not_called()


@pytest.mark.parametrize('phase,field,value', [('Initial','channel_count',4),('Final','channel_names',['1','0']),
    ('Initial','type','other-lead'),('Final','name','Other target')])
def test_full_canonical_lead_geometry_is_checked_not_model_target_only(case,phase,field,value):
    c=case;prepare(c);r=report();r['LeadConfiguration'][phase][0][field]=value
    with pytest.raises(ValueError,match='canonical lead descriptors'):
        c.runtime.admit_masked(json.dumps(r).encode(),{'sha256':'f'*64})
    assert not c.runtime._masked_admissions


@pytest.mark.parametrize('condition',['foreign_owner','multiple','no_match','wrong_device','not_matching'])
def test_normal_decoder_institute_scope_cannot_choose_another_device(case,condition):
    c=case;prepare(c)
    other=NS(uid='0'*32,owner_id='1'*32)
    choices={'foreign_owner':[NS(uid=D,owner_id='1'*32)], 'multiple':[c.device,other], 'no_match':[],
             'wrong_device':[NS(uid='0'*32,owner_id=P)], 'not_matching':[c.device]}[condition]
    c.models.DBSDevice.objects.filter.return_value=choices
    if condition=='not_matching':c.models.matchDevice.return_value=False
    with pytest.raises(ValueError,match='decoder device selection'):
        c.runtime.admit_masked(json.dumps(report()).encode(),{'sha256':'f'*64})
    c.runtime.command.assert_not_called()
    assert not c.runtime._masked_admissions


@pytest.mark.parametrize('raw', [b'{"SessionDate":"x","DeviceInformation":{},"DeviceInformation":{}}',
    b'{"SessionDate":"x","DeviceInformation":{},"extra":NaN}',
    json.dumps(report(1,1)).encode()])
def test_strict_json_and_advancing_session(case, raw):
    prepare(case)
    with pytest.raises(ValueError): case.runtime.admit_masked(raw, {'sha256':'f'*64})
    assert not case.runtime._masked_admissions


@pytest.mark.parametrize('field', ['device', 'owner_id', 'institute', 'metadata'])
def test_post_decode_exact_binding_required_before_provenance_commit(case, field):
    c=case; prepare(c); sha='f'*64
    c.runtime.admit_masked(json.dumps(report()).encode(), {'sha256':sha})
    out=NS(uid='f'*32,device=D,owner_id=P,institute=I,metadata={'Device':D},save=Mock())
    setattr(out,field,{} if field=='metadata' else '0'*32)
    with pytest.raises(ValueError): c.runtime.save_upstream([(out, {'raw_sha256':sha})])
    out.save.assert_not_called()


def test_default_save_does_not_need_opt_in(case):
    case.runtime.save_upstream([(case.row, {'raw_sha256': case.digest})])
    assert 'MaskedDeviceAdmission' not in case.row.metadata


@pytest.mark.parametrize('change', [lambda row:row.metadata.pop('MaskedDeviceAdmission'),
    lambda row:row.metadata['MaskedDeviceAdmission'].update(admission_hmac_sha256='0'*64),
    lambda row:row.metadata['MaskedDeviceAdmission'].update(admission_hmac_sha256=None),
    lambda row:row.metadata['MaskedDeviceAdmission'].update(extra=True),
    lambda row:setattr(row,'device','0'*32)])
def test_success_receipt_requires_exact_signed_admission_readback(case,change):
    c=case;prepare(c);sha='f'*64
    c.runtime.admit_masked(json.dumps(report()).encode(),{'sha256':sha})
    out=NS(uid='f'*32,device=D,owner_id=P,institute=I,metadata={'Device':D},save=Mock())
    c.runtime.save_upstream([(out,{'raw_sha256':sha})]);change(out)
    with pytest.raises(ValueError):c.runtime.verify_masked_admission(out,sha)


def test_unrelated_known_source_needs_no_new_certificate(case):
    prepare(case)
    case.runtime.verify_masked_admission(case.row,case.digest)


def test_latest_rooted_reference_only_and_bounded_raw_memory(case, monkeypatch):
    c=case
    second=deepcopy(c.row); second.uid='f'*32; second.metadata={'Device':D,'ClockAnchor':anchor(report())}
    second.pointer=str(c.root/P/(second.uid+'.json')); raw=json.dumps(report()).encode(); Path(second.pointer).write_bytes(raw)
    sha=hashlib.sha256(raw).hexdigest()
    cert=policy.record(c.binding,second.uid,sha,S,c.digest,{'proof':True},dict(agreement={'clock':True},table_digest='a'*16,configuration_digest='b'*64),KEY)
    second.metadata['MaskedDeviceAdmission']=cert; c.index[sha]=second
    c.runtime.loader.side_effect=lambda row: raw if row.uid==second.uid else c.raw
    c.runtime.existing.side_effect=lambda hashed: second if hashed==hmac.new(KEY,raw,hashlib.sha256).hexdigest() else c.row
    monkeypatch.setattr(u.native_continuity,'validate_receipt',lambda value:True)
    monkeypatch.setattr(u.native_continuity,'validate_clock_receipt',lambda value:True)
    prepare(c)
    assert c.runtime._masked_reference_item['source_uid']==second.uid
    assert c.runtime.admit_masked(json.dumps(report(3,3)).encode(),{'sha256':'0'*64})
    assert len(c.runtime._masked_raw_cache)==2
    assert c.runtime._masked_admissions['0'*64][0]['source_uid']==second.uid


def test_ambiguous_latest_reference_rejected(case, monkeypatch):
    c=case
    monkeypatch.setattr(policy,'trusted_references',lambda *args:[
        {'anchor':anchor(report()),'source_uid':S,'raw_sha256':c.digest},
        {'anchor':anchor(report()),'source_uid':'f'*32,'raw_sha256':'0'*64}])
    with pytest.raises(ValueError,match='ambiguous'):prepare(c)
