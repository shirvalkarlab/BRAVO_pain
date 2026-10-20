"""Synthetic failure and missing-data boundaries for the integrated scientific rules."""
from contextlib import nullcontext
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from modules.Biomarkers.routines import analytics as A, availability as AV
from modules.Biomarkers.routines import band_results_tables as BT, streaming_psd as PSD
from modules.Biomarkers.routines import sweep_settings as SW


def test_stimulation_eras_need_times_and_more_than_one_observation():
    assert A._assign_stim_eras(None, {'t': [1, 2], 'y': [0, 1]}) is None
    assert A._assign_stim_eras(['2020-01-01'], {'t': [1], 'y': [0]}) is None


def test_matcher_empty_reports_and_unusable_psd_timestamps_are_missing():
    cache = {'centers_hz': [10.0], 'window_s': 3.0,
             'td': {'t': [], 'lsb': [], 'ok': []},
             'psd': {'t': [np.nan], 'lsb': [[2.0]], 'calibrated': [[True]]}}
    def match(reports):
        return AV.live_lsb_band_medians_by_length(reports, cache, tol_s=30,
               lengths_s=[3.0], centers_hz=[10.0], band_ceilings=[np.inf])
    empty, info, stats = match([])
    assert empty[3.0].shape == (0, 1) and stats == {}
    assert info['recording_times_s'] == []
    values, info, _ = match([1_600_000_000.0])
    assert np.isnan(values[3.0]).all()
    assert info['recording_times_s'] == [[]]


def test_sweep_drops_malformed_window_and_refuses_misaligned_covariate():
    pain = np.arange(12.0)
    power = {3.0: pain[:, None] + 10, 30.0: np.ones((11, 1))}
    result = A.band_time_sweep_from_power(power, pain, center_freqs_hz=[10.0],
              requested_seconds=[3.0, 30.0], n_perm=12, n_boot=20,
              outlier_n_mad=0, covariate=np.array([1, 2, 3]))
    assert result['integration_seconds_requested'] == [3.0]
    assert result['n_grid'] == [[12]]
    assert result['covariate_adjustment']['applied'] is False
    assert '3 values for 12' in result['covariate_adjustment']['reason']


@pytest.mark.parametrize('null', [{}, {'best_by_shuffle': np.empty((0, 1))},
                                  {'best_by_shuffle': np.ones((2, 2))}])
def test_short_report_series_and_absent_null_never_invent_intervals(null):
    rows = A._best_rows_correlation(np.array([[1.0]]), np.array([[3]]),
              np.array([[[1.0], [2.0], [3.0]]]), np.array([2.0, 4.0, 6.0]),
              np.array([10.0]), [3.0], [3.0], [1], null, band_width_hz=5,
              n_boot=20, rng=np.random.default_rng(0), power_feature='synthetic', channel='ONE_THREE_LEFT')
    row = rows[0]
    assert row['pearson_r'] == 1 and row['n_resamples_used'] == 0
    assert row['shuffled_best_of_windows_p95'] is None and row['p_selection_aware'] is None


def test_welch_short_missing_mask_does_not_masquerade_as_complete_mask():
    data = np.random.default_rng(0).normal(size=(2, 4000))
    base = PSD.welch_psd_for_instance(data, ['A', 'ignored'], 250, ['A'])
    short = PSD.welch_psd_for_instance(data, ['A', 'ignored'], 250, ['A'], missing=[1])
    np.testing.assert_array_equal(short, base)
    base = PSD.welch_rating_centered(data, ['A', 'ignored'], 250, ['A'], [8.0])
    short = PSD.welch_rating_centered(data, ['A', 'ignored'], 250, ['A'], [8.0], missing=[1])
    for got, want in zip(short, base):
        np.testing.assert_array_equal(got, want)


def test_nondefault_tags_and_missing_discrimination_grids_are_not_retained():
    assert SW.default_settings_keep_group(None) is None
    assert SW.default_settings_keep_group({}) is None
    assert BT.discrimination_table({'absent': {}}).empty


def test_source_table_comparison_detects_missing_duplicate_and_changed_cells():
    sweep = {'center_freqs_hz': [10.0], 'integration_seconds_requested': [3.0],
             'correlation_grid': [[0.5]]}
    table = pd.DataFrame({'channel': ['pair'], 'integration_seconds_requested': [3.0],
                          'band_center_hz': [10.0], 'pearson_r': [0.5]})
    def count(t):
        return BT.count_matches(t, {'pair': sweep}, 'pearson_r', 'correlation_grid')
    assert count(table) == (1, 0)  # older tables did not carry grid_source
    assert count(table.iloc[:0]) == (1, 1)
    assert count(pd.concat([table, table])) == (1, 1)
    assert count(table.assign(pearson_r=0.6)) == (1, 1)


@pytest.fixture
def fitted_boundary(monkeypatch):
    """Exercise wrapper decisions without substituting for the separate production-R gate."""
    settings = {'estimate': 0.2, 'warnings': [], 'variance': [0.5]}
    class Model:
        def __init__(self, *args, **kwargs):
            self.coefs = pd.DataFrame({'Estimate': [settings['estimate']], 'P-val': [0.3],
                                      'Z-stat': [1.0]}, index=['band_power'])
            self.ranef_var = pd.DataFrame({'Var': settings['variance']})
            self.warnings = settings['warnings']
        def fit(self, **kwargs):
            pass
    monkeypatch.setitem(sys.modules, 'pymer4.models', SimpleNamespace(Lmer=Model))
    monkeypatch.setattr(A, '_rpy2_converter_ctx', nullcontext)
    monkeypatch.setattr(A, '_band_feature_from_detail', lambda d, *a: (np.arange(len(d['labels']), dtype=float),))
    monkeypatch.setattr(A, '_band_rotation_test', lambda *a, **k: {'available': False})
    detail = {'labels': np.arange(40.0), 'times': pd.date_range('2020-01-01', periods=40, freq='D').astype(str).tolist()}
    return settings, detail


def test_model_missing_detail_and_feature_are_unavailable(fitted_boundary, monkeypatch):
    _, detail = fitted_boundary
    assert A.band_mixedmodel_inference(None, 'pair', 10)['reason'] == 'no detail'
    monkeypatch.setattr(A, '_band_feature_from_detail', lambda *a: None)
    assert not A.band_mixedmodel_inference(detail, 'pair', 10)['available']


def test_model_burnin_and_rating_groups_keep_window_contract(fitted_boundary):
    _, detail = fitted_boundary
    detail['rating_group'] = np.arange(40)
    out = A.band_mixedmodel_inference(detail, 'pair', 10, exclude_first_weeks=1)
    assert out['available'] and out['n_excluded_burn_in'] == 7 and out['excluded_first_weeks'] == 1
    removed = A.band_mixedmodel_inference(detail, 'pair', 10, exclude_first_weeks=100)
    assert not removed['available'] and 'removed every sample' in removed['reason']
    too_few = dict(detail, labels=np.arange(3.0), times=detail['times'][:3], rating_group=np.arange(3))
    assert not A.band_mixedmodel_inference(too_few, 'pair', 10)['available']


def test_model_separation_nonconvergence_and_empty_variance_remain_explicit(fitted_boundary):
    settings, detail = fitted_boundary
    settings['estimate'] = 60
    assert A.band_mixedmodel_inference(detail, 'pair', 10)['separation'] is True
    settings['estimate'] = 0.2
    settings['warnings'] = ['model failed to converge']
    out = A.band_mixedmodel_inference(detail, 'pair', 10)
    assert not out['converged'] and out['p'] is None and out['odds_ratio'] is None
    settings['warnings'] = []
    settings['variance'] = []
    out = A.band_mixedmodel_inference(detail, 'pair', 10)
    assert out['converged'] and out['singular'] is False


def test_real_r_main_model_preserves_answer_when_current_warning_is_added():
    """Production acceptance: actual feature extraction, lme4 fit and both rotation tests."""
    pytest.importorskip('pymer4', reason='Requires production pymer4/rpy2/R stack')
    pytest.importorskip('rpy2', reason='Requires production pymer4/rpy2/R stack')
    rng = np.random.default_rng(37)
    n = 96
    labels = rng.normal(size=n)
    frequencies = np.linspace(8, 30, 24)
    psd = np.exp(rng.normal(0, 0.15, (n, 1, len(frequencies))) + labels[:, None, None] * 0.1)
    times = pd.date_range('2020-01-01', periods=n, freq='D')
    detail = {'labels': labels, 'times': times.astype(str).tolist(), 'psd': psd,
              'f_set': frequencies, 'chan_order': ['ZERO_TWO_LEFT']}
    current = {'t_s': times.astype('int64').to_numpy() / 1e9,
               'hemi': np.repeat('Left', n), 'amp_mA': 1 + (np.arange(n) // 8) % 3}
    plain = A.band_mixedmodel_inference(detail, 'ZERO_TWO_LEFT', 15.0)
    adjusted = A.band_mixedmodel_inference(detail, 'ZERO_TWO_LEFT', 15.0,
                  current_removed={'stream': current, 'hemisphere': 'Left'})
    assert plain['available'] and plain['converged'], plain
    assert plain['rotation']['available'], plain['rotation']
    warning = adjusted.pop('rotation_current_removed')
    assert warning['available'] and warning['p'] is not None, warning
    assert plain == adjusted
