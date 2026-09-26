"""Every chance test that shuffles the pain ratings uses the exact rotation test (decision 315).

WHY. To judge whether a band's link with pain is more than chance, the heat-map grid, the older
full-spectrum search, the power-over-time area test and the check before any decoder all moved the
pain ratings and recomputed the link many times. They shared one helper, which, once pain resembled
its neighbours, cut the rating series into short chunks and reordered the chunks. That keeps each
chunk together but throws away pain's slower rises and falls, and with a band that also drifts
slowly the shuffled links come out narrower than chance really is, so p comes out too small: on
RCS08's own layout, an unrelated made-up band read p <= 0.05 in 10.7% of records instead of 5%
(`artifacts/analysis_2026-09-26_exact_null_on_the_heat_maps.md`, section 5). The PI, 2026-09-26:
"yes switch".

THE REPLACEMENT slides the whole pain series along in time, once by every possible number of
ratings, wrapping the end round to the start, and counts the observed order once: the exact
rotation p, whose smallest value is 1/n. It was the band detector's since decision 314; it now has
one home, `stats_utils.rotations`, and every caller uses it.

Run inside the container:
    python3 -m pytest modules/Biomarkers/tests/test_exact_rotation_null.py -q
"""
import inspect
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import stats_utils as SU
    from modules.Biomarkers.routines import analytics as A
    from modules.Biomarkers.routines import confound_diagnostic as CD
    from modules.Biomarkers import pipeline as PL
except ImportError:                                            # pragma: no cover - host spelling
    from Biomarkers.routines import stats_utils as SU
    from Biomarkers.routines import analytics as A
    from Biomarkers.routines import confound_diagnostic as CD
    from Biomarkers import pipeline as PL


def _ar(rng, n, r):
    e = rng.normal(size=n)
    x = np.zeros(n)
    x[0] = e[0]
    for t in range(1, n):
        x[t] = r * x[t - 1] + np.sqrt(1 - r * r) * e[t]
    return x


def test_every_other_rotation_once_lives_in_stats_utils():
    rot = SU.rotations(120, 1000, np.random.default_rng(0))       # 1000 asked; only 119 exist
    assert rot.shape == (119, 120)
    assert sorted(int(r[0]) for r in rot) == list(range(1, 120))  # each shift exactly once
    assert all(np.array_equal(r, np.roll(np.arange(120), -int(r[0]))) for r in rot)
    assert not any(np.array_equal(r, np.arange(120)) for r in rot)  # the observed order is the +1


def test_above_the_limit_the_rotations_are_distinct_draws():
    n = SU.EXACT_ROTATIONS_MAX + 7
    rot = SU.rotations(n, 50, np.random.default_rng(1))
    shifts = [int(r[0]) for r in rot]
    assert rot.shape == (50, n) and len(set(shifts)) == 50 and 0 not in shifts
    assert SU.rotation_null_words(n, 50) == f"50 of the {n - 1} other rotations, drawn without replacement"
    assert SU.rotation_null_words(120, 119) == "exact: every other rotation once"


def test_the_block_shuffle_is_gone():
    for name in ("circular_block_perm_matrix", "circular_block_indices", "block_perm_pvalue",
                 "permutation_null_resolution"):
        assert not hasattr(SU, name), name
    for mod in (A, CD, PL):
        assert "circular_block_perm_matrix" not in inspect.getsource(mod), mod.__name__


def test_the_grids_null_is_every_other_rotation_once():
    rng = np.random.default_rng(2)
    n = 90
    pain = rng.normal(size=n)
    X = rng.normal(size=(2, n, 3))                                  # two lengths, three bands
    got = A._best_of_windows_null_correlation(X, pain, n_perm=1000, rng=np.random.default_rng(0))
    assert got["n_used"] == n - 1
    # each shuffle's best is the largest |r| over the two lengths at that rotation, and the rows are
    # the rotations in order
    for k in (0, 17, n - 2):
        yk = np.roll(pain, -(k + 1))
        want = [max(abs(np.corrcoef(X[t, :, c], yk)[0, 1]) for t in range(2)) for c in range(3)]
        assert np.allclose(got["best_by_shuffle"][k], want, atol=1e-12), k
    assert abs(got["p_resolution"] - 1.0 / n) < 1e-15


def test_the_grids_smallest_p_is_one_over_n():
    rng = np.random.default_rng(5)
    n = 60
    pain = np.clip(np.round(rng.normal(6, 2, n)), 0, 10)
    x1 = 100 - 6 * pain + rng.normal(0, 1, n)                      # beats every rotation
    x2 = rng.normal(100, 15, n)
    power = {1.0: np.column_stack([x1, x2]), 5.0: np.column_stack([x2, x1])}
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=[12.5, 20.5], n_perm=1000, n_boot=50)
    row = next(r for r in sw["best_correlation_rows"] if r["band_center_hz"] == 12.5)
    assert row["p_selection_aware"] == 1.0 / n, row["p_selection_aware"]
    assert sw["n_shuffles"] == n - 1


def test_the_grids_null_reads_p_at_its_level_when_pain_and_the_band_drift_slowly():
    """A made-up band with no link to pain, both drifting slowly (lag-1 correlation 0.75, 200
    ratings). The chunk shuffle read p <= 0.05 in about 10% of such records; every rotation reads it
    near 5% (decision 314 measured 4.7-5.3% on the band detector's own records)."""
    n, sims = 200, 1200
    rng = np.random.default_rng(315)
    small = 0
    for _ in range(sims):
        pain, x = _ar(rng, n, 0.75), _ar(rng, n, 0.75)
        got = A._best_of_windows_null_correlation(x[None, :, None], pain, n_perm=1000,
                                                  rng=np.random.default_rng(0))
        obs = abs(np.corrcoef(x, pain)[0, 1])
        col = got["best_by_shuffle"][:, 0]
        p = (int((col >= obs).sum()) + 1) / (col.size + 1)
        small += p <= 0.05
    assert small / sims <= 0.07, small / sims


def test_the_grids_resampled_intervals_draw_the_same_numbers_as_before():
    """The rotations use no random numbers. The grid still takes the draws the chunk shuffle took,
    so every resampled interval drawn after the null is the same draw as before the switch and does
    not move (the measurement the PI saw kept them identical). Pinned, not RED."""
    rng = np.random.default_rng(7)
    n = 150
    pain = _ar(rng, n, 0.8)                                         # chunk length above 1
    block = SU.block_length_for(pain, n)
    assert block > 1
    g_new = np.random.default_rng(11)
    A._best_of_windows_null_correlation(rng.normal(size=(1, n, 2)), pain, n_perm=1000, rng=g_new)
    g_old = np.random.default_rng(11)
    g_old.integers(0, n, size=1000)
    g_old.random((1000, int(np.ceil(n / block))))
    assert g_new.bit_generator.state == g_old.bit_generator.state


def test_the_area_null_is_the_exact_rotation_test():
    rng = np.random.default_rng(3)
    n = 60
    labels = np.repeat([0.0, 1.0, 0.0, 1.0], [10, 20, 15, 15])    # persistent, and no shift maps
    #                                                                 them onto themselves
    score = labels * 10 + rng.normal(size=n)                       # separates perfectly
    got = SU.auc_block_perm_null(score, labels, n_perm=1000, seed=0)
    assert got["n_perm"] == n - 1 and got["block"] == 1
    assert got["p_value"] == 1.0 / n, got["p_value"]


def test_the_full_spectrum_search_rotates_the_ratings():
    rng = np.random.default_rng(4)
    g = np.repeat(np.arange(40), 3)                                 # 40 ratings, 3 epochs each
    y = np.repeat(_ar(rng, 40, 0.8), 3)
    Yp, info = PL._rating_level_perm_matrix(y, g, 1000, np.random.default_rng(0))
    assert Yp.shape == (39, 120) and info["block"] == 1
    per_rating = Yp[:, ::3]
    for k in range(39):                          # one value per rating is a mean of its 3 epochs
        assert np.allclose(per_rating[k], np.roll(y[::3], -(k + 1)), rtol=0, atol=1e-12), k


def test_the_check_before_any_decoder_uses_every_rotation():
    rng = np.random.default_rng(6)
    n = 60
    y = (_ar(rng, n, 0.6) > 0).astype(float)
    X = rng.normal(size=(n, 3))
    c = np.repeat([0.0, 1.0, 2.0, 3.0], 15)
    got = CD.pre_build_diagnostic(X, y, c, n_perm=200, seed=0)
    assert got["null"]["n_perm"] == n - 1                          # 200 asked; 59 exist
    assert got["null"]["block"] == 1


def test_the_grid_rule_version_moved_so_no_grid_judged_by_the_chunk_shuffle_is_served():
    try:
        from modules.Biomarkers import bravo_service as BS
    except ImportError:                                        # pragma: no cover - host spelling
        from Biomarkers import bravo_service as BS
    assert int(BS._BAND_SWEEP_RULE_VERSION.split("_")[0][1:]) >= 24, BS._BAND_SWEEP_RULE_VERSION


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
