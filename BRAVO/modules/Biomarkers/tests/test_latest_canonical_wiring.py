"""Latest Prasad controls continue through the canonical input boundary."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from modules.Biomarkers import bravo_service as service
from modules.ClosedLoopDeployment import adapter as closed_adapter, bravo_service as closed_service


def test_conversion_consumes_the_canonical_three_part_psd_assembly(monkeypatch):
    monkeypatch.setattr(service.models.Participant, 'find', lambda **kw: SimpleNamespace(uid='p'))
    monkeypatch.setattr(service, '_assemble_psd_rows_cached', lambda uid: ([], 0, 0))
    result = service.band_psd_lsb_conversion({'ParticipantId': 'p', 'Channel': 'ONE_THREE_LEFT'})
    assert result['available'] is False
    assert result['reason'].startswith('only 0 offline PSD epochs')


def test_drilldown_cache_invalidates_with_canonical_inputs(monkeypatch):
    monkeypatch.setattr(service, '_analysis_identity', lambda uid: 'revision-a')
    p = SimpleNamespace(uid='p')
    first = service._pro_build_cache_key({}, p)
    monkeypatch.setattr(service, '_analysis_identity', lambda uid: 'revision-b')
    assert service._pro_build_cache_key({}, p) != first
    assert service._pro_build_cache_key({'ProcessedPRO': [1]}, p) is None


def test_recording_signature_tracks_all_canonical_inputs(monkeypatch):
    from modules import AnalysisData
    manifest = {'source_count': 2, 'recordings': 3, 'fingerprint': 'a'}
    monkeypatch.setattr(AnalysisData, 'input_manifest', lambda p: manifest)
    p = SimpleNamespace(uid='p')
    first = closed_adapter.recording_set_signature(p)
    manifest['fingerprint'] = 'changed-pro-or-clock'
    assert closed_adapter.recording_set_signature(p) != first


def test_current_report_selects_server_owned_band_and_preserves_full_research_payload(monkeypatch):
    from Server import models
    from modules import AnalysisData
    p = SimpleNamespace(uid='p')
    calls = {}
    monkeypatch.setattr(models.Participant, 'find', lambda **kw: p)
    monkeypatch.setattr(AnalysisData, 'input_manifest', lambda p: {'fingerprint': 'approved'})
    monkeypatch.setattr(closed_service, 'participant_context', lambda p: {'programming_mode': 'parkinsons'})
    def report(participant, request, **kwargs):
        calls.update(kwargs)
        assert participant is p and request['LabelMetric'] == 'left_leg_vas'
        return {'available': True, 'manifest': {}, 'prescription': {'research': True}}
    monkeypatch.setattr(closed_adapter, 'report_for_participant', report)
    monkeypatch.setattr(closed_adapter, 'closed_loop_simulation_for_participant', lambda *a, **k: {'available': True})
    monkeypatch.setattr(closed_adapter, 'three_source_pooled_for_participant', lambda *a: {'available': True})
    result = closed_service.run_for_participant({'ParticipantId': 'p', 'Channel': 'ONE_THREE_RIGHT',
                                                'CenterHz': 20, 'LabelMetric': 'left_leg_vas'})
    assert calls['hemisphere'] == 'Right'
    assert calls['candidates'][0]['actuated_hemisphere'] == 'Right'
    assert result['prescription'] == {'research': True}
    assert result['manifest']['InputManifest']['fingerprint'] == 'approved'
    assert result['readiness']['ready'] is False


@pytest.mark.parametrize('center', [0, float('nan'), float('inf')])
def test_report_rejects_invalid_band_without_computing(monkeypatch, center):
    from Server import models
    monkeypatch.setattr(models.Participant, 'find', lambda **kw: SimpleNamespace(uid='p'))
    monkeypatch.setattr(closed_adapter, 'report_for_participant', lambda *a, **k: pytest.fail('computed invalid band'))
    assert closed_service.run_for_participant({'ParticipantId': 'p', 'Channel': 'ONE_THREE_RIGHT', 'CenterHz': center})['available'] is False


def test_service_error_is_sanitized_not_cached_as_empty_success(monkeypatch):
    def fail(request): raise ValueError('private diagnostic')
    monkeypatch.setattr(closed_service, '_current_report_for_participant', fail)
    with pytest.raises(RuntimeError, match='could not be computed') as exc:
        closed_service.run_for_participant({})
    assert 'private diagnostic' not in str(exc.value)
