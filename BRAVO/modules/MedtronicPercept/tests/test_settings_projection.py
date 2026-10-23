"""Settings reads keep the canonical clock and leave stored bytes unchanged."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from modules.MedtronicPercept import TabletClock
from .test_tablet_clock import make_export, A_TABLET, A_OFF, OFFS, stamp


def loader(document, table=None):
    source = Path(__file__).resolve().parents[2] / 'DataCurator.py'
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'loadPerceptJSON')
    reads = []
    scope = {'json': json, 'TabletClock': TabletClock,
             'loadCacheFile': lambda source: reads.append(source) or json.dumps(document).encode(),
             'clock_anchor_table': lambda **kwargs: reads.append(kwargs) or table}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
    return scope['loadPerceptJSON'], reads


def document():
    raw = make_export(A_TABLET, A_OFF, 7494, OFFS)
    raw['Groups'] = {'Initial': [{'ActiveGroup': True, **stamp(1_500_000_000, A_OFF-30)}], 'Final': []}
    raw['Stimulation'] = {'InitialStimStatus': 'ON', 'FinalStimStatus': 'ON'}
    return raw


def test_projection_equals_full_retained_fields_with_first_carrier_clock():
    raw = document()
    original = copy.deepcopy(raw)
    # A distinct first-carrier anchor proves projection uses the supplied table,
    # rather than merely deriving a convenient clock from the current report.
    carried = TabletClock.convert_export(copy.deepcopy(raw), [])['first_carried']
    anchor = {**TabletClock.export_anchor(raw), 'anchor_s': TabletClock.export_anchor(raw)['anchor_s']-7, 'first_carried': carried}
    table = TabletClock.AnchorTable([anchor])
    load, reads = loader(raw)
    source = SimpleNamespace(device='synthetic-device', owner='synthetic-owner')
    full = load(source, table=table)
    projected = load(source, table=table, settings_only=True)
    keys = {'SessionDate', 'SessionEndDate', 'DeviceInformation', 'Groups', 'Stimulation', '_TabletClock'}
    assert set(projected) == keys
    for key in keys-{'_TabletClock'}:
        assert projected[key] == full[key]
    assert projected['Groups']['Initial'][0]['DateTime'] != raw['Groups']['Initial'][0]['DateTime']
    assert projected['SessionDate'] == raw['SessionDate']
    assert projected['SessionEndDate'] == raw['SessionEndDate']
    assert projected['_TabletClock']['table_digest'] == full['_TabletClock']['table_digest']
    assert raw == original and reads == [source, source]


def test_table_from_gets_original_export_before_projection():
    raw = document(); load, reads = loader(raw)
    captured = []
    def table_from(value):
        assert value == raw and 'BrainSenseTimeDomain' in value
        captured.append(True)
        return TabletClock.AnchorTable([TabletClock.export_anchor(value)])
    result = load(SimpleNamespace(), table_from=table_from, settings_only=True)
    assert captured == [True] and len(reads) == 1
    assert 'BrainSenseTimeDomain' not in result


@pytest.mark.parametrize('device,expected', [('device','device'), ('',None)])
def test_default_clock_lookup_keeps_device_or_owner_scope(device, expected):
    raw = document(); load, reads = loader(raw, TabletClock.AnchorTable([]))
    source = SimpleNamespace(device=device, owner='owner')
    load(source, settings_only=True)
    assert reads == [source, {'device_uid':expected, 'owner':None if device else 'owner'}]


@pytest.mark.parametrize('raw', [[], {}, {'SessionDate':A_TABLET}, {'DeviceInformation':{}}])
def test_projection_rejects_non_session_but_existing_default_loader_keeps_it(raw):
    load, _ = loader(raw)
    assert load(SimpleNamespace()) == raw
    with pytest.raises(ValueError, match='Percept session'):
        load(SimpleNamespace(), settings_only=True)


@pytest.mark.parametrize('value', [1, None, 'yes', []])
def test_projection_requires_boolean_before_reading_source(value):
    load, reads = loader(document())
    with pytest.raises(ValueError, match='boolean'):
        load(SimpleNamespace(), settings_only=value)
    assert not reads


def test_projection_keeps_missing_optional_fields_missing():
    raw = document(); del raw['Groups']; del raw['Stimulation']; del raw['SessionEndDate']
    load, _ = loader(raw)
    projected = load(SimpleNamespace(), table=TabletClock.AnchorTable([]), settings_only=True)
    assert 'Groups' not in projected and 'Stimulation' not in projected and 'SessionEndDate' not in projected
