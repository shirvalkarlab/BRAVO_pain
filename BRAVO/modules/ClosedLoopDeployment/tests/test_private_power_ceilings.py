"""Synthetic configuration isolation; no participant-derived thresholds are fixtures."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from ClosedLoopDeployment import ceiling_thresholds as CT
from ClosedLoopDeployment import three_source_response as T3


def document(uid='synthetic-a'):
    return {'schema_version': 1, 'participant_uid': uid, 'percentile': 99.5,
            'provenance': {'source_sha': 'synthetic', 'computed_at': '2000-01-01', 'method': 'synthetic fixture'},
            'tables': {'POWER_DOMAIN_CEILINGS': [{'electrode': 'TEST', 'centre_hz': 12.5, 'ceiling': 1000}]}}


def write_config(tmp_path, monkeypatch, doc=None, uid='synthetic-a'):
    monkeypatch.setenv('BRAVO_POWER_CEILING_CONFIG_DIR', str(tmp_path))
    path = tmp_path / (hashlib.sha256(uid.encode()).hexdigest() + '.json')
    path.write_text(json.dumps(document(uid) if doc is None else doc))
    return path


def test_missing_and_unreadable_config(tmp_path, monkeypatch):
    monkeypatch.delenv('BRAVO_POWER_CEILING_CONFIG_DIR', raising=False)
    assert CT.load_configuration(None).status == 'missing_participant'
    assert CT.load_configuration('').status == 'missing_participant'
    assert CT.load_configuration('synthetic-a').status == 'not_configured'
    monkeypatch.setenv('BRAVO_POWER_CEILING_CONFIG_DIR', str(tmp_path))
    assert CT.load_configuration('synthetic-a').status == 'missing'
    def unreadable(_):
        raise PermissionError('synthetic denial')
    monkeypatch.setattr(Path, 'read_bytes', unreadable)
    assert CT.load_configuration('synthetic-a').status == 'unreadable'


def test_configuration_content_and_participant_binding(tmp_path, monkeypatch):
    path = write_config(tmp_path, monkeypatch)
    config = CT.load_configuration('synthetic-a')
    assert config.available and config.reason == ''
    assert config.power_ceiling('TEST', 12.51) == 1000
    assert config.power_ceiling('UNKNOWN', 12.5) is None
    for contact, centre in [(None, 12.5), ('TEST', None), ('TEST', 'bad'), ('TEST', []), ('TEST', float('nan'))]:
        assert config.power_ceiling(contact, centre) is None
    assert CT.load_configuration('synthetic-b').status == 'missing'
    write_config(tmp_path, monkeypatch, document('synthetic-b'))
    mismatched = CT.load_configuration('synthetic-a')
    assert mismatched.status == 'participant_mismatch'
    assert mismatched.power_ceiling('TEST', 12.5) is None
    assert 'unavailable' in mismatched.reason
    assert mismatched.digest != config.digest
    path.write_bytes(b'\xff')
    assert CT.load_configuration('synthetic-a').status == 'invalid'
    path.write_text('not JSON')
    assert CT.load_configuration('synthetic-a').status == 'invalid'
    path.write_text('[]')
    assert CT.load_configuration('synthetic-a').status == 'invalid'


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(schema_version=True), lambda d: d.update(schema_version=2), lambda d: d.update(percentile=50),
    lambda d: d.update(provenance=[]), lambda d: d['provenance'].update(source_sha=''),
    lambda d: d['provenance'].pop('method'), lambda d: d.update(tables=[]),
    lambda d: d.update(tables={}), lambda d: d['tables'].update(UNKNOWN=[]),
    lambda d: d['tables'].update(POWER_DOMAIN_CEILINGS={}),
    lambda d: d['tables'].update(POWER_DOMAIN_CEILINGS=[[]]),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'][0].update(electrode=''),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'][0].update(electrode=1),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'][0].update(centre_hz='12.5'),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'][0].update(ceiling=True),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'][0].update(centre_hz=float('inf')),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'][0].update(ceiling=float('inf')),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'][0].update(centre_hz=-1),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'][0].update(ceiling=0),
    lambda d: d['tables']['POWER_DOMAIN_CEILINGS'].append(copy.deepcopy(d['tables']['POWER_DOMAIN_CEILINGS'][0])),
])
def test_invalid_configuration_fails_closed(tmp_path, monkeypatch, mutate):
    doc = document(); mutate(doc)
    write_config(tmp_path, monkeypatch, doc)
    assert CT.load_configuration('synthetic-a').status == 'invalid'


def test_all_tables_are_validated_and_digest_tracks_revision(tmp_path, monkeypatch):
    doc = document(); doc['tables']['TIME_DOMAIN_CEILINGS'] = []; doc['tables']['RAW_LSB_CEILINGS'] = []
    write_config(tmp_path, monkeypatch, doc)
    first = CT.configuration_identity('synthetic-a')
    assert first[0:2] == (1, 'available')
    doc['tables']['POWER_DOMAIN_CEILINGS'][0]['ceiling'] = 2000
    write_config(tmp_path, monkeypatch, doc)
    assert CT.configuration_identity('synthetic-a') != first
    assert CT.load_configuration('synthetic-a').power_ceiling('TEST', 12.5) == 2000


def settled(uid, config=None):
    t = np.arange(180., step=.5)
    power = np.full(t.size, 200.); power[t == 160.] = 50000.
    current = np.where(t < 90, 1., 2.)
    original = power.copy()
    result = T3.settled_device_band_power([0, 90], [90, 180], [1, 2], t, power, current,
                                        participant_uid=uid, ceiling_configuration=config,
                                        sensing_contact='TEST', centre_hz=12.5)
    np.testing.assert_array_equal(original, power)
    return result


def test_missing_and_cross_participant_fail_closed_without_altering_raw(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch)
    config = CT.load_configuration('synthetic-a')
    assert T3.device_power_ceiling('TEST', 12.5, participant_uid='synthetic-a') == 1000
    assert T3.device_power_ceiling('TEST', 12.5, participant_uid='synthetic-b', configuration=config) is None
    for uid, supplied in [('synthetic-b', None), ('synthetic-b', config), (None, None)]:
        power, rows = settled(uid, supplied)
        assert np.isnan(power).all()
        assert (rows.ceiling_check_status == 'unavailable').all()
        assert rows.why_not_used.str.contains('unavailable').all()
        assert (rows.n_spikes_excluded == 0).all()
    power, rows = settled('synthetic-a', config)
    assert power[1] == 200 and rows.loc[1, 'n_spikes_excluded'] == 1
    assert rows.loc[1, 'ceiling_check_status'] == 'applied'
    assert rows.loc[1, 'ceiling_configuration_digest'] == config.digest


def test_valid_configuration_without_pair_preserves_source_no_ceiling_rule(tmp_path, monkeypatch):
    doc = document(); doc['tables']['POWER_DOMAIN_CEILINGS'] = []
    write_config(tmp_path, monkeypatch, doc)
    power, rows = settled('synthetic-a')
    # 59 ordinary samples and one spike; unknown pair is left unfiltered by the source policy.
    assert power[1] == (59 * 200 + 50000) / 60
    assert rows.loc[1, 'ceiling_check_status'] == 'no_historical_pair'
    assert rows.loc[1, 'n_spikes_excluded'] == 0


def test_comparison_serializes_qualified_status_and_refusal(tmp_path, monkeypatch):
    from ClosedLoopDeployment.tests.test_three_source_response import _build, _panel
    write_config(tmp_path, monkeypatch)
    good = _build(participant_uid='synthetic-a', ceiling_configuration=CT.load_configuration('synthetic-a'))
    panel = _panel(good, T3.SOURCE_DEVICE_BAND_POWER)
    assert panel.ceiling_quality['ceiling_check_status'] == 'no_historical_pair'
    assert panel.to_dict()['ceiling_quality'] == panel.ceiling_quality
    rows = [r for r in T3.comparison_rows(good) if r['source'] == T3.SOURCE_DEVICE_BAND_POWER]
    assert rows and all(r['ceiling_configuration_status'] == 'available' for r in rows)
    bad = _build(participant_uid='synthetic-b', ceiling_configuration=None)
    panel = _panel(bad, T3.SOURCE_DEVICE_BAND_POWER)
    assert panel.n_settings_used == 0 and 'unavailable' in panel.absent_reason
    assert panel.ceiling_quality['ceiling_check_status'] == 'unavailable'
    assert T3.comparison_rows(bad)[-1]['ceiling_configuration_status'] == 'missing'


def test_participant_build_passes_bound_configuration_to_comparison(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from Biomarkers import routines
    from ClosedLoopDeployment.tests.test_three_source_response import _steps, _device
    write_config(tmp_path, monkeypatch)
    contact = 'TEST_LEFT'
    steps = _steps([0., 1., 2., 3.])
    device = _device(currents=[0., 1., 2., 3.])
    bs = SimpleNamespace(
        POWERDOMAIN_TYPES='power', TIMEDOMAIN_TYPES='td', AVAILABILITY_PSD_TYPES='psd',
        _load_recordings=lambda *args: ['synthetic-recording'],
        _derive_chan_order=lambda _: [contact],
        _raw_lsb_cache_cached=lambda *args, **kw: {contact: {}},
        _event_psd_lsb_blocks=lambda *args, **kw: [],
        _build_sensing_config_index=lambda _: {},
        _montage_psd_lsb_blocks=lambda *args, **kw: [],
    )
    monkeypatch.setitem(sys.modules, 'Biomarkers.bravo_service', bs)
    import Biomarkers
    monkeypatch.setattr(Biomarkers, 'bravo_service', bs, raising=False)
    availability = SimpleNamespace(_canon_channel=lambda channel: channel)
    monkeypatch.setitem(sys.modules, 'Biomarkers.routines.availability', availability)
    monkeypatch.setattr(routines, 'availability', availability, raising=False)
    monkeypatch.setattr(T3, 'read_device_current', lambda _: {})
    monkeypatch.setattr(T3, 'find_single_side_runs_from_device', lambda *args, **kw: [{'steps': steps, 'side': 'Left'}])
    monkeypatch.setattr(T3, 'read_device_band_power', lambda _: {contact: device})
    captured = []
    monkeypatch.setattr(T3, 'build_comparison', lambda **kw: captured.append(kw) or 'synthetic-comparison')
    payload = T3.build_for_participant('synthetic-a')
    assert payload['comparisons'] == ['synthetic-comparison']
    assert captured[0]['participant_uid'] == 'synthetic-a'
    assert captured[0]['ceiling_configuration'].participant_uid == 'synthetic-a'
    assert captured[0]['ceiling_configuration'].digest == payload['ceiling_configuration']['digest']
