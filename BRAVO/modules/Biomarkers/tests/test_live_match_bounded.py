"""Large-request fallback retains matching values without padded allocations."""
import copy
import numpy as np
import pytest
from ..routines import availability as av
from .test_live_match_vectorised import _cache, T0


@pytest.mark.parametrize('reuse', [False, True])
@pytest.mark.parametrize('arrays', [False, True])
def test_scalar_fallback_matches_vectorized_without_padded_allocations(monkeypatch, reuse, arrays):
    cache = _cache()
    pro = [T0 + 9, T0 + 70, T0 + 200, T0 + 800]
    if arrays:
        for family in ('td', 'psd'):
            cache[family]['lsb'] = av._lsb_rows_to_mat(cache[family]['lsb'], len(cache['centers_hz']))
    options = dict(tol_s=30, td_quantity_s=18, allow_window_reuse=reuse)
    expected = av.live_lsb_spectrum_match(pro, copy.deepcopy(cache), **options)
    monkeypatch.setattr(av, '_LIVE_MATCH_TEMP_BUDGET', 0)
    def no_padding(*args, **kwargs):
        raise AssertionError('large request allocated a padded selection')
    monkeypatch.setattr(av, '_pad_windows_in_extent', no_padding)
    monkeypatch.setattr(av, '_pad_owned_windows', no_padding)
    actual = av.live_lsb_spectrum_match(pro, cache, **options)
    assert actual == expected


@pytest.mark.parametrize('reuse', [False, True])
@pytest.mark.parametrize('families', [(), ('td',), ('psd',), ('td', 'psd')])
def test_empty_family_and_default_argument_equivalence(monkeypatch, reuse, families):
    cache = _cache()
    for family in families:
        cache[family] = {}
    for pro in ([], [T0 - 10000], [T0 + 9, T0 + 70]):
        for options in ({}, {'extent_s': 15}, {'psd_tol_s': 20}, {'tol_s': 2, 'td_quantity_s': 0}):
            monkeypatch.setattr(av, '_LIVE_MATCH_TEMP_BUDGET', 2**60)
            expected = av.live_lsb_spectrum_match(pro, copy.deepcopy(cache), allow_window_reuse=reuse, **options)
            monkeypatch.setattr(av, '_LIVE_MATCH_TEMP_BUDGET', -1)
            assert av.live_lsb_spectrum_match(pro, copy.deepcopy(cache), allow_window_reuse=reuse, **options) == expected


def test_matrix_shapes_and_missing_family_cache():
    assert av._lsb_rows_to_mat(np.zeros((1, 2, 3)), 2).shape == (0, 2)
    assert av._lsb_rows_to_mat(np.array([]), 2).shape == (0, 2)
    assert av._lsb_rows_to_mat(np.array([1, 2]), 2).shape == (1, 2)
    assert av._lsb_rows_to_mat(np.array([[1, 2]]), 3).shape == (1, 3)
    assert av._lsb_family_mat({}, 2).shape == (0, 2)


def test_all_invalid_windows_leave_no_selection():
    selected, counts = av._pad_windows_in_extent(
        np.array([1., 2.]), np.array([False, False]), np.array([1.]), 10., 1)
    assert selected.shape == (1, 0)
    np.testing.assert_array_equal(counts, [0])


@pytest.mark.parametrize('shape,index_shape', [((0, 2), (1, 3)), ((2, 2), (0, 3)), ((2, 2), (3, 0))])
def test_empty_median_has_expected_missing_values(shape, index_shape):
    result = av._padded_nanmedian(np.empty(shape), np.full(index_shape, -1))
    assert result.shape == (index_shape[0], shape[1])
    assert np.isnan(result).all()


@pytest.mark.parametrize('reuse', [False, True])
def test_scalar_psd_fallback_uses_all_events_when_td_is_invalid(monkeypatch, reuse):
    monkeypatch.setattr(av, '_LIVE_MATCH_TEMP_BUDGET', -1)
    cache = {'centers_hz': [10.], 'window_s': 3,
             'td': {'t': [10.], 'ok': [False], 'lsb': [[99.]]},
             'psd': {'t': [9., 11.], 'lsb': [[2.], [4.]]}}
    rows, stats = av.live_lsb_spectrum_match([10.], cache, tol_s=5,
                                            allow_window_reuse=reuse)
    assert rows[0]['lsb'] == [3.]
    assert rows[0]['tier'] == av.PRO_LSB_TIER_BRIDGE
    assert rows[0]['n_psd_used'] == 2
    assert stats['n_pro_td'] == 0
