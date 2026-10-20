"""Canonical lead-set matching seeds masked-device clocks without widening implant identity."""
from copy import deepcopy
import hashlib
import hmac
from types import SimpleNamespace as N

import pytest

from modules import DataCurator as DC
from modules.DecodeCommon import implants
from modules.DecodeCommon.private_clinical_config import ClinicalConfigurationUnavailable
from modules.MedtronicPercept import Session

OWNER = 'synthetic-owner'
MASK = '***'
TYPE = 'Percept RC'


class QS(list):
    def values_list(self, *fields, flat=False):
        return [getattr(r, fields[0]) for r in self] if flat else [tuple(getattr(r, f) for f in fields) for r in self]
    def filter(self, **kw):
        def ok(row, key, value):
            if key == 'metadata__SerialIdentityMasked': return row.metadata.get('SerialIdentityMasked') == value
            if key.endswith('__in'): return getattr(row, key[:-4]) in value
            return getattr(row, key) == value
        return QS(r for r in self if all(ok(r, k, v) for k, v in kw.items()))
    def count(self): return len(self)
    def all(self): return self


def raw(serial=MASK):
    return {'SessionDate': '2001-01-01T00:00:00Z', 'SessionEndDate': '2001-01-01T00:01:00Z',
        'ProgrammerUtcOffset': '+00:00',
        'PatientInformation': {'Final': {'PatientFirstName': 'Synthetic', 'PatientLastName': 'Example',
            'PatientId': 'TEST', 'Diagnosis': 'DiagnosisTypeDef.Other', 'PatientGender': 'PatientGenderDef.UNKNOWN'}},
        'DeviceInformation': {'Final': {'Neurostimulator': TYPE, 'NeurostimulatorSerialNumber': serial,
            'NeurostimulatorLocation': 'InsLocation.CHEST_LEFT', 'ImplantDate': '2000-01-01T00:00:00Z'}},
        'LeadConfiguration': {'Final': [{'Hemisphere': 'HemisphereLocationDef.Left',
            'LeadLocation': 'LeadLocationDef.Gpi', 'ElectrodeNumber': 'InsPort.ZERO_SEVEN',
            'Model': 'LeadModelDef.LEAD_B33015'}]}}


@pytest.fixture
def population(monkeypatch):
    actual_match = DC.models.matchDevice
    def dev(uid, serial, owner, target='Left GPi', kind='SenSight B33015', dtype=TYPE):
        return N(uid=uid, serial_number=serial, owner_id=owner, type=dtype,
                 electrodes=QS([N(type=kind, target=target)]))
    devices = QS([dev('main', MASK, OWNER), dev('restored', 'CONCRETE', OWNER),
                  dev('singleton-right', MASK, OWNER, target='Right GPi'),
                  dev('singleton-other', MASK, OWNER, target='Left STN', kind='Medtronic 3389'),
                  dev('other-owner', MASK, 'someone-else')])
    sources = QS([N(device=d.uid, owner_id=d.owner_id, type='MedtronicJSON',
                    metadata={'ClockAnchor': {'n': i + 1}}) for i, d in enumerate(devices)])
    monkeypatch.setattr(DC, 'models', N(DBSDevice=N(objects=devices), SourceFile=N(objects=sources), matchDevice=actual_match))
    monkeypatch.setattr(DC.TabletClock, 'export_anchor', lambda payload: {'n': 99})
    monkeypatch.setattr(DC.TabletClock, 'AnchorTable', lambda anchors, **kw: sorted(a['n'] for a in anchors))
    monkeypatch.setattr(DC, '_clinical_config_digest', lambda: 'synthetic-config')
    monkeypatch.setattr(DC, 'HASH_KEY', 'synthetic-hash-key')
    def section(owner, name):
        if owner != OWNER: raise ClinicalConfigurationUnavailable('No synthetic private evidence')
        assert name == 'implant_groups'
        return {'groups': [{'device_type': TYPE, 'device_uids': ['main', 'restored']}]}
    monkeypatch.setattr(implants, 'participant_section', section)
    return N(devices=devices, sources=sources)


def source(deid=False, owner=OWNER):
    return N(owner_id=owner, metadata={'automatic_deidentification': deid})


def test_unique_canonical_lead_set_seeds_verified_group_only(population):
    payload, sf = raw(), source()
    before = deepcopy(payload)
    assert DC._ingest_clock_table(payload, sf)[1] == [1, 2, 99]
    assert sf.metadata['SerialIdentityMasked'] is True and payload == before
    assert Session.extractPatientInformation(payload)['Device']['ConnectedLeads'][0]['name'] == 'Left GPi'


def test_ambiguous_canonical_lead_matches_do_not_guess_a_device(population):
    population.devices[2].electrodes = deepcopy(population.devices[0].electrodes)
    assert DC._ingest_clock_table(raw(), source())[1] == [99]


def test_unknown_or_mismatched_leads_do_not_join_same_type(population):
    payload = raw(); payload['LeadConfiguration']['Final'][0]['LeadLocation'] = 'LeadLocationDef.Vim'
    assert DC._ingest_clock_table(payload, source())[1] == [99]
    payload['LeadConfiguration']['Final'] = []
    assert DC._ingest_clock_table(payload, source())[1] == [99]


def test_other_owner_cannot_seed_or_expand_this_owner_group(population):
    assert DC._ingest_clock_table(raw(), source(owner='missing-owner'))[1] == [99]
    assert DC._ingest_clock_table(raw(), source(), device=population.devices[-1])[1] == [99]
    assert DC._ingest_clock_table(raw(), source(owner='someone-else'))[1] == [5, 99]


def test_explicit_device_respects_owner_and_can_resolve_without_implicit_guessing(population):
    assert DC._ingest_clock_table(raw(), source(), device=population.devices[0])[1] == [1, 2, 99]
    assert DC._ingest_clock_table(raw(), source(owner=None), device=population.devices[0])[1] == [1, 2, 99]


def test_raw_mask_classification_survives_hmac_and_prevents_unbound_hash_aliases(population):
    token = hmac.new(DC.HASH_KEY.encode(), MASK.encode(), hashlib.sha256).hexdigest()
    for d in population.devices:
        if d.serial_number == MASK: d.serial_number = token
    sf = source(deid=True)
    assert DC._ingest_clock_table(raw(), sf)[1] == [1, 2, 99]
    assert sf.metadata['SerialIdentityMasked'] is True
    # Once the normal import persists the flag, all later readers/restamps are safe too.
    population.sources[0].metadata['SerialIdentityMasked'] = True
    assert DC.implant_device_uids('main', owner_only=OWNER) == ['main', 'restored']
    assert DC.implant_device_uids('singleton-right', owner_only=OWNER) == ['singleton-right']
    assert DC.implant_device_uids(serial=token, owner_uid=OWNER) == []


@pytest.mark.parametrize('flag', [None, False, 'true', 1, {}, []])
def test_missing_or_malformed_mask_flag_cannot_reclassify_real_serial(population, flag):
    population.devices[0].serial_number = population.devices[2].serial_number = 'REAL-SHARED'
    population.sources[0].metadata['SerialIdentityMasked'] = flag
    assert 'singleton-right' in DC.implant_device_uids('main', owner_only=OWNER)


def test_valid_mask_flag_is_limited_to_exact_owner_and_type(population):
    population.devices[-1].serial_number = MASK
    population.sources[-1].metadata['SerialIdentityMasked'] = True
    # The other owner flag never changes the verified owner group or plain concrete joining.
    population.devices[0].serial_number = population.devices[2].serial_number = 'REAL-SHARED'
    assert 'singleton-right' in DC.implant_device_uids('main', owner_only=OWNER)
    population.devices[3].serial_number = 'REAL-SHARED'; population.devices[3].type = 'Another Type'
    population.sources[3].metadata['SerialIdentityMasked'] = True
    assert 'singleton-right' in DC.implant_device_uids('main', owner_only=OWNER)


def test_missing_owner_or_malformed_raw_has_no_guessed_clock(population):
    assert DC._ingest_clock_table(raw(), source(owner=None))[1] == [99]
    assert DC._ingest_clock_table({}, source())[1] == [99]
    assert DC._ingest_clock_table(raw(serial=None), source())[1] == [99]
    payload = raw(); del payload['LeadConfiguration']
    assert DC._ingest_clock_table(payload, source())[1] == [99]


def test_concrete_serial_compatibility_and_deid_flag_false(population):
    sf = source(); sf.metadata['SerialIdentityMasked'] = 'invalid'
    assert DC._ingest_clock_table(raw(serial='CONCRETE'), sf)[1] == [1, 2, 99]
    assert sf.metadata['SerialIdentityMasked'] is False
    token = hmac.new(DC.HASH_KEY.encode(), b'CONCRETE', hashlib.sha256).hexdigest()
    population.devices[1].serial_number = token
    sf = source(deid=True)
    assert DC._ingest_clock_table(raw(serial='CONCRETE'), sf)[1] == [1, 2, 99]
    assert sf.metadata['SerialIdentityMasked'] is False


def test_duplicate_lead_descriptors_cannot_pass_non_bijective_legacy_match(population):
    payload = raw()
    payload['LeadConfiguration']['Final'].append(deepcopy(payload['LeadConfiguration']['Final'][0]))
    population.devices[0].electrodes.append(N(type='SenSight B33015', target='Right GPi'))
    assert DC._ingest_clock_table(payload, source())[1] == [99]
