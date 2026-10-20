"""Synthetic owner and explicitly bounded implant identity tests."""
import json
import pytest
from modules.DecodeCommon import implants as I
from modules.DecodeCommon.private_clinical_config import ClinicalConfigurationUnavailable


@pytest.fixture
def configured(tmp_path, monkeypatch):
    record = {'groups': [{'device_type': 'Percept RC', 'device_uids': ['a', 'b']}],
              'source_commit': 'a' * 40, 'provenance': 'Synthetic device evidence',
              'evidence_ref': 'synthetic/devices'}
    path = tmp_path / 'private.json'
    def write(section=record):
        path.write_text(json.dumps({'schema_version': 1, 'participants': {'owner': {'implant_groups': section}}}))
        path.chmod(0o600)
    write()
    monkeypatch.setenv('BRAVO_CLINICAL_CONFIG_FILE', str(path))
    return record, write


def test_same_serial_owner_and_type_guard(configured):
    assert I.same_implant('owner', 'Percept RC', 'same', 'owner', 'Percept RC', 'same')
    for oa, ob, ta, tb in [('owner', 'other', 'Percept RC', 'Percept RC'),
                          (None, None, 'Percept RC', 'Percept RC'),
                          ('owner', None, 'Percept RC', 'Percept RC'),
                          ('owner', 'owner', '', ''), ('owner', 'owner', 'A', 'B')]:
        assert not I.same_implant(oa, ta, 'same', ob, tb, 'same')
    assert not I.same_implant('owner', 'Percept RC', '', 'owner', 'Percept RC', '')
    assert not I.same_implant('owner', 'Percept RC', 's1', 'owner', 'Percept RC', 's2', device_a='a')


def test_explicit_members_only(configured):
    assert I.same_implant('owner', 'Percept RC', 's1', 'owner', 'Percept RC', 's2', device_a='a', device_b='b')
    for a, b, t in [('a', 'future', 'Percept RC'), ('future', 'b', 'Percept RC'), ('a', 'b', 'Other')]:
        assert not I.same_implant('owner', t, 's1', 'owner', t, 's2', device_a=a, device_b=b)
    assert not I.same_implant('other', 'Percept RC', 's1', 'other', 'Percept RC', 's2', device_a='a', device_b='b')


@pytest.mark.parametrize('groups', [None, [], {}, [None], [{}],
    [{'device_type': '', 'device_uids': ['a','b']}],
    [{'device_type': 1, 'device_uids': ['a','b']}],
    [{'device_type': 'T', 'device_uids': 'ab'}],
    [{'device_type': 'T', 'device_uids': ['a']}],
    [{'device_type': 'T', 'device_uids': ['a', None]}],
    [{'device_type': 'T', 'device_uids': ['a', ' ']}],
    [{'device_type': 'T', 'device_uids': ['a', 'a']}],
    [{'device_type': 'T', 'device_uids': ['a','b']}, {'device_type': 'T', 'device_uids': ['b','c']}],
    [{'device_type': 'T', 'device_uids': ['a','b'], 'extra': True}]])
def test_invalid_group_rejected(configured, groups):
    record, write = configured
    write(dict(record, groups=groups))
    with pytest.raises(ClinicalConfigurationUnavailable): I.configured_groups('owner')


def test_device_inventory_binding(configured):
    rows = [('a','serial1','owner','Percept RC'), ('b','serial2','owner','Percept RC'),
            ('c','serial2','owner','Percept RC'), ('foreign','serial1','other','Percept RC'),
            ('future','new','owner','Percept RC'), ('bench','serial1','owner','Other')]
    assert I.device_uids(rows, device_uid='a') == ['a','b','c']
    assert I.device_uids(rows, device_uid='b', owner_only='owner') == ['a','b','c']
    assert I.device_uids(rows, serial='serial2', owner_uid='owner') == ['a','b','c']
    assert I.device_uids(rows, device_uid='future') == ['future']
    assert I.device_uids(rows, device_uid='foreign') == ['foreign']
    for kw in ({}, {'serial':'serial1'}, {'owner_uid':'owner'}, {'device_uid':'missing'},
               {'device_uid':'a','owner_only':'other'}, {'device_uid':'a','owner_uid':'other'},
               {'device_uid':'a','owner_only':'owner','owner_uid':'other'}):
        assert I.device_uids(rows, **kw) == []


def test_no_configuration_no_exception(monkeypatch):
    monkeypatch.delenv('BRAVO_CLINICAL_CONFIG_FILE', raising=False)
    assert I.configured_groups('owner') == ()
    assert not I.same_implant('owner','T','x','owner','T','y',device_a='a',device_b='b')


@pytest.mark.parametrize('serial', ['', None, 3, ' ', '████', 'ab██', '***', 'MASKED', 'unknown', 'redacted'])
def test_masked_serial_not_identity_except_explicit_members(configured, serial):
    assert not I.concrete_serial(serial)
    assert not I.same_implant('owner','Percept RC',serial,'owner','Percept RC',serial,
                              device_a='a',device_b='future')
    assert I.same_implant('owner','Percept RC',serial,'owner','Percept RC',serial,
                         device_a='a',device_b='b')


def test_masked_serial_lookup_requires_exact_preverified_group(configured):
    rows = [('a','██','owner','Percept RC'), ('b','concrete','owner','Percept RC')]
    assert I.device_uids(rows, serial='██', owner_uid='owner') == ['a','b']
    assert I.device_uids(rows, device_uid='a') == ['a','b']
    assert I.device_uids(rows+[('future','██','owner','Percept RC')], serial='██', owner_uid='owner') == []
    assert I.device_uids([('bench','██','owner','Other')], serial='██', owner_uid='owner') == []
    assert I.device_uids([('unbound','██','other','Percept RC')], serial='██', owner_uid='other') == []


def test_clock_table_identity_changes_with_private_binding_but_times_do_not():
    from modules.MedtronicPercept import TabletClock
    anchor = {'block':'synthetic', 'final_offset_s':10, 'anchor_s':100}
    original = TabletClock.AnchorTable([anchor])
    first = TabletClock.AnchorTable([anchor], identity_salt='configuration-a')
    changed = TabletClock.AnchorTable([anchor], identity_salt='configuration-b')
    assert original.block_anchor('synthetic') == first.block_anchor('synthetic') == changed.block_anchor('synthetic')
    assert len({original.digest(), first.digest(), changed.digest()}) == 3
    assert first.digest_upto(anchor) != changed.digest_upto(anchor)
