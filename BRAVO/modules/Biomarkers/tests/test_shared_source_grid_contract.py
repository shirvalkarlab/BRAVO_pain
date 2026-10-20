"""Boundary failures and source-specific current provenance stay explicit."""
import numpy as np
from modules.Biomarkers import bravo_service as service


def setup(monkeypatch, fail_source=False):
    monkeypatch.setattr(service.analytics, 'BAND_TIME_SWEEP_SECONDS', [3])
    monkeypatch.setattr(service.sweep_settings, 'SOURCE_GRIDS', True)
    def matched(*args, **kwargs):
        source = kwargs.get('sources', 'both')
        return ({3: np.array([[1.0], [2.0]])}, {}, np.array([10.0]), np.array([0]), {},
                [source == 'psd'] * 2, [[100], [200]])
    monkeypatch.setattr(service, '_band_time_sweep_power_by_seconds', matched)
    monkeypatch.setattr(service.stim_current, 'covariate_for_reports',
                        lambda *a, **k: (np.array([0., 1.]), {'read_at': 'recording'}))
    def computed(jobs):
        out = []
        for i, (_, _, kw) in enumerate(jobs):
            if fail_source and i % 3 == 2:
                out.append(('error', 'synthetic PSD failure'))
            else:
                out.append(('ok', {'available': True, 'n_grid': [[2]],
                    'best_correlation_rows': [{}, None], 'best_auc_rows': [{}]}))
        return out
    monkeypatch.setattr(service, '_sweep_statistics', computed)


def run(caches):
    return service._band_time_sweep_channels(caches, [100, 200], tol_s=900,
        allow_window_reuse=False, pain_values=[1, 2], label_strategy='tertile',
        low_pct=30, high_pct=70, outlier_n_mad=0, outlier_scale='raw',
        metric_key='nrs', metric_label='NRS', adjust_for_stim_current=True)


def test_each_source_has_current_provenance_and_only_td_can_choose(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setenv('BIOMARKER_SWEEP_THREADS', 'invalid')
    result = run({'ZERO_THREE_LEFT': {'synthetic': True}})['ZERO_THREE_LEFT']
    assert result['stim_current_covariate']['read_at'] == 'recording'
    for source, expected in [('td', True), ('psd', False)]:
        grid = result['by_source_grid'][source]
        assert grid['stim_current_covariate']['read_at'] == 'recording'
        assert grid['best_correlation_rows'][0]['can_choose_band'] is expected


def test_failed_psd_grid_does_not_relabel_or_erase_td_result(monkeypatch):
    setup(monkeypatch, fail_source=True)
    result = run({'ZERO_THREE_LEFT': {'synthetic': True}})['ZERO_THREE_LEFT']
    assert result['by_source_grid']['td']['best_correlation_rows'][0]['can_choose_band']
    assert result['by_source_grid']['psd']['n_grid'] == []
    assert 'synthetic PSD failure' in str(result['by_source_grid']['psd'])
    assert result['by_source_grid']['counting']['n_cells_adding_up'] == 1


def test_malformed_grid_counts_remain_failed_reconciliation_not_invented_counts(monkeypatch):
    setup(monkeypatch)
    original = service._sweep_statistics
    def bad_count(jobs):
        rows = original(jobs)
        rows[1][1]['n_grid'] = []
        return rows
    monkeypatch.setattr(service, '_sweep_statistics', bad_count)
    result = run({'ZERO_THREE_LEFT': {'synthetic': True}})['ZERO_THREE_LEFT']
    assert result['by_source_grid']['counting']['n_cells'] == 1
    assert result['by_source_grid']['counting']['n_cells_adding_up'] == 0
