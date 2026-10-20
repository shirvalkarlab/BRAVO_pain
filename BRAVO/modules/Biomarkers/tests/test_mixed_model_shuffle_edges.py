"""Synthetic failure boundaries and lme4 interface checks, without provider or service access."""
import contextlib
import sys
import types

import numpy as np
import pandas as pd
import pytest

from modules.Biomarkers.routines import mixed_model_shuffle as M
from modules.Biomarkers.routines import analytics as A


def _null(**over):
    kw = dict(y=[0, 1, 0, 1], eta=[0., 0., 0., 0.], tau=.25, cluster=[0, 0, 1, 1])
    kw.update(over)
    return M.NullModel(**kw)


@pytest.mark.parametrize('over,match', [
    ({'eta': [0.]}, 'one value'), ({'cluster': [0]}, 'one value'),
    ({'y': [0, np.nan, 0, 1]}, 'finite'), ({'eta': [0, np.inf, 0, 0]}, 'finite'),
    ({'family': 'gaussian'}, 'residual variance'),
    ({'family': 'gaussian', 'residual_var': 0}, 'residual variance'),
    ({'eta': [1000., 1000., 1000., 1000.]}, 'positive'),
])
def test_bad_null_inputs_refused(over, match):
    with pytest.raises(ValueError, match=match):
        with np.errstate(divide='ignore', invalid='ignore'):
            _null(**over)


def test_bad_options_are_explicit_and_degenerate_scores_are_unavailable():
    with pytest.raises(ValueError, match='alternative'):
        M.shuffle_p([1., 0.], 'invalid')
    with pytest.raises(ValueError, match='scheme'):
        M.shuffle_test(_null(), [0., 1., 2., 3.], scheme='invalid')
    assert np.isnan(_null().score_z(np.zeros(4)))
    out = M.shuffle_test(_null(), [0., 1., 2., 3.], scheme='within_cluster', n_shuffles=8)
    assert out['n_orders'] == 9 and 1 / 9 <= out['p'] <= 1
    out = M.shuffle_test(_null(), [0., 1., 2., 3.], scheme='within_cluster', n_shuffles=8,
                         rng=np.random.default_rng(23), keep_null=True)
    assert len(out['z_all']) == 9
    assert M.shuffle_p([1., np.nan, 0.]) == .5


def _fake_lmer(monkeypatch, *, family='binomial', warnings=()):
    seen = {}
    class Lmer:
        def __init__(self, formula, data, family):
            seen.update(formula=formula, frame=data.copy(), family=family)
            self.fits = np.array([.2, .8, .3, .7]) if family == 'binomial' else np.arange(4.)
            self.ranef_var = pd.DataFrame({'Var': [.25, 1.5]}, index=['cluster', 'Residual'])
            self.warnings = warnings
        def fit(self, summarize):
            assert summarize is False
    monkeypatch.setitem(sys.modules, 'pymer4.models', types.SimpleNamespace(Lmer=Lmer))
    monkeypatch.setattr(A, '_rpy2_converter_ctx', contextlib.nullcontext)
    return seen


@pytest.mark.parametrize('family,warnings,converged', [
    ('binomial', (), True), ('gaussian', ['failed to converge'], False),
    ('binomial', ['unidentifiable'], False), ('binomial', ['boundary singular fit'], True),
])
def test_lme4_interface_retains_fixed_effects_variance_and_warnings(monkeypatch, family, warnings, converged):
    seen = _fake_lmer(monkeypatch, family=family, warnings=warnings)
    X = np.column_stack([np.ones(4), np.arange(4.)])
    null, ok, got = M.null_fit_lme4([0., 1., 0., 1.], [0, 0, 1, 1], X, family=family,
                                  names=['constant', 'trend'])
    assert ok is converged and got == list(warnings)
    assert seen['formula'] == 'y ~ trend + (1|cluster)'
    assert np.array_equal(null.X0, X) and null.tau == .25
    if family == 'gaussian':
        assert np.allclose(null.w, 1 / 1.5)
    else:
        assert np.allclose(null.mu, [.2, .8, .3, .7])


def test_lme4_intercept_only_and_default_covariate_names(monkeypatch):
    seen = _fake_lmer(monkeypatch)
    M.null_fit_lme4([0., 1., 0., 1.], [0, 0, 1, 1])
    assert seen['formula'] == 'y ~ 1 + (1|cluster)'
    M.null_fit_lme4([0., 1., 0., 1.], [0, 0, 1, 1], np.arange(4.).reshape(4, 1))
    assert seen['formula'] == 'y ~ c0 + (1|cluster)'


def test_rotation_wrapper_reports_nonconvergence_or_fit_exception(monkeypatch):
    frame = pd.DataFrame({'pain_high': [0, 1, 0, 1], 'band_power': [0., 1., 2., 3.],
                          'cluster': [0, 0, 1, 1]})
    monkeypatch.setattr(M, 'null_fit_lme4', lambda *a: (None, False, ['failed to converge']))
    out = A._band_rotation_test(frame, np.arange(4.))
    assert out['available'] is False and out['fit_warnings'] == ['failed to converge']
    def fail(*args):
        raise RuntimeError('synthetic numerical failure')
    monkeypatch.setattr(M, 'null_fit_lme4', fail)
    out = A._band_rotation_test(frame, np.arange(4.))
    assert out['available'] is False and 'synthetic numerical failure' in out['reason']


@pytest.mark.parametrize('result', [
    {'p': np.nan, 'z': 0., 'n_unusable': 0},
    {'p': .5, 'z': np.inf, 'n_unusable': 0},
    {'p': .5, 'z': .3, 'n_unusable': 1},
])
def test_rotation_wrapper_never_advertises_incomplete_orders_as_exact(monkeypatch, result):
    frame = pd.DataFrame({'pain_high': [0, 1, 0, 1], 'band_power': [0., 1., 2., 3.],
                          'cluster': [0, 0, 1, 1]})
    monkeypatch.setattr(M, 'null_fit_lme4', lambda *a: (_null(), True, []))
    monkeypatch.setattr(M, 'shuffle_test', lambda *a, **kw: result)
    out = A._band_rotation_test(frame, np.arange(4.))
    assert out['available'] is False and 'no exact p' in out['reason']


def test_rotation_wrapper_returns_the_full_finite_order_set(monkeypatch):
    frame = pd.DataFrame({'pain_high': [0, 1, 0, 1], 'band_power': [0., 1., 2., 3.],
                          'cluster': [0, 0, 1, 1]})
    monkeypatch.setattr(M, 'null_fit_lme4', lambda *a: (_null(), True, []))
    out = A._band_rotation_test(frame, np.arange(4.))
    assert out['available'] is True and out['n_orders'] == 4
    assert out['p_floor'] == .25 and .25 <= out['p'] <= 1


@pytest.mark.parametrize('times', [None, [], ["2026-01-01"], ["2026-01-01"] * 31])
def test_missing_or_mismatched_rotation_times_preserve_the_existing_model(monkeypatch, times):
    class FittedModel:
        def __init__(self, formula, data, family):
            self.formula = formula
            self.coefs = pd.DataFrame({"Estimate": [.2], "P-val": [.4], "Z-stat": [.8],
                                       "OR": [1.22], "2.5_ci": [-.3], "97.5_ci": [.7]},
                                      index=["band_power"])
            self.ranef_var = pd.DataFrame({"Var": [.25]})
            self.warnings = []
        def fit(self, summarize):
            assert summarize is False
    monkeypatch.setitem(sys.modules, 'pymer4.models', types.SimpleNamespace(Lmer=FittedModel))
    monkeypatch.setattr(A, '_rpy2_converter_ctx', contextlib.nullcontext)
    monkeypatch.setattr(A, '_band_feature_from_detail', lambda *a: (np.linspace(1., 4., 30),))
    detail = {'labels': np.r_[np.zeros(15), np.ones(15)], 'times': times}
    out = A.band_mixedmodel_inference(detail, 'SYNTHETIC_LEFT', 20., strategy='fixed',
                                     pain_cutoff=.5, exclude_first_weeks=0)
    assert out['available'] is True and out['converged'] is True
    assert out['formula'] == 'pain_high ~ band_power'
    assert out['p'] == .4 and out['odds_ratio'] == 1.22
    assert out['rotation']['available'] is False


@pytest.mark.parametrize('times', [None, [], [[1., 2.], [3., 4.]], [1., 2., 3.]])
def test_multicluster_rotation_rejects_misaligned_time_vectors(monkeypatch, times):
    frame = pd.DataFrame({'pain_high': [0, 1, 0, 1], 'band_power': [0., 1., 2., 3.],
                          'cluster': [0, 0, 1, 1]})
    def forbidden(*args):
        pytest.fail('misaligned times must be refused before an R fit')
    monkeypatch.setattr(M, 'null_fit_lme4', forbidden)
    out = A._band_rotation_test(frame, times, row_mask=np.ones(4, dtype=bool))
    assert out['available'] is False and 'do not match' in out['reason']
    direct = A._band_rotation_test(frame, times)
    assert direct['available'] is False and 'do not match' in direct['reason']


def test_rotation_timestamp_conversion_and_mask_preserve_fitted_row_order(monkeypatch):
    frame = pd.DataFrame({'pain_high': [0, 1, 0, 1], 'band_power': [0., 1., 2., 3.],
                          'cluster': [0, 0, 1, 1]})
    times = ['2026-01-04', '2026-01-03', '2026-01-02', '2026-01-01', '2026-01-05']
    mask = np.array([True, False, True, True, True])
    monkeypatch.setattr(M, 'null_fit_lme4', lambda *args: (_null(), True, []))
    observed = {}
    def score(null, x, *, order):
        observed['order'] = order
        return {'p': .5, 'z': .2, 'n_orders': 4, 'p_floor': .25, 'n_unusable': 0}
    monkeypatch.setattr(M, 'shuffle_test', score)
    out = A._band_rotation_test(frame, times, row_mask=mask)
    expected = np.array([1767484800., 1767312000., 1767225600., 1767571200.])
    assert out['available'] is True
    assert np.array_equal(observed['order'], expected)
    monkeypatch.setattr(A, '_times_epoch_s', lambda value: (_ for _ in ()).throw(ValueError('conversion')))
    failed = A._band_rotation_test(frame, times, row_mask=mask)
    assert failed['available'] is False and 'conversion' in failed['reason']
