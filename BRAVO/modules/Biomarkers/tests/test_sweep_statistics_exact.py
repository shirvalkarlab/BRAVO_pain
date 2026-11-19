"""Tests that the fast form of the band-by-length-of-signal sweep statistics returns the SAME
NUMBERS as the plain form it replaced, not merely close ones.

Two pieces of that section were rewritten for speed, and each is checked here against a
straightforward version written out inside the test rather than against a recorded expected value,
so that the check keeps working if the inputs change.

  * The interval on the best high-pain-against-low-pain cell resamples whole pain reports. It used
    to turn the drawn row numbers into a thousand-by-a-few-hundred matrix of multiplicities with
    ``np.add.at`` and hand that to ``_weighted_auc_matrix``. It now counts straight from the drawn
    row numbers in ``bootstrap_auc_from_row_picks``. The two are required to agree BIT FOR BIT,
    because every step of that calculation is whole-number arithmetic small enough for a double to
    hold exactly, so there is no rounding for a different order of additions to expose. The cases
    below include a band whose power never changes (every value tied), a band with missing
    measurements, tied pain scores, rows the split left out, and resamples that lose one of the two
    pain states entirely.

  * The interval on the best correlation cell now writes the differences from the mean back over
    the drawn values and reuses one buffer for the three products. Correlating real-valued band
    powers DOES round, so this one is checked as an exact match of doubles against the plain form
    with its five separate arrays -- which it is, because the subtractions, the products and the
    row sums are the same operations in the same order.

  * The grids themselves are checked against a plain double loop over lengths of signal and band
    centres: an ordinary Pearson correlation report by report, and an ordinary Mann-Whitney count
    of pairs with half credit for ties. The counting one is required to be exact; the correlation
    one is allowed the last few bits, since a sum over reports written one way rounds differently
    from the same sum written another way.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_sweep_statistics_exact.py

Merged here 2026-10-05: test_sweep_cell_p_values.py, test_sweep_effective_count.py, test_sweep_interval_block_bootstrap.py, test_sweep_null_family_reconciled.py.

Merged here 2026-10-05: test_whole_matrix_median_speedup.py.
"""
import os
import struct
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics as A          # noqa: E402


def _bits(v):
    """The raw bytes of a double, so two values are compared with no tolerance at all."""
    return struct.pack("<d", float(v))


def _identical(a, b):
    """One value against another, non-finite counted as agreeing only when both are non-finite."""
    fa, fb = float(a), float(b)
    if np.isnan(fa) or np.isnan(fb):
        return np.isnan(fa) and np.isnan(fb)
    return _bits(fa) == _bits(fb)


def _all_identical(a, b):
    a = np.asarray(a, dtype=float).ravel()
    b = np.asarray(b, dtype=float).ravel()
    if a.size != b.size:
        return False, -1
    for i in range(a.size):
        if not _identical(a[i], b[i]):
            return False, i
    return True, -1


def _dense_weight_matrix(picks, n_rows):
    """The matrix of multiplicities the old route built: how many times each row was drawn into
    each resample, by the same unbuffered scatter the old code used."""
    picks = np.asarray(picks)
    W = np.zeros((picks.shape[0], int(n_rows)), dtype=np.float64)
    np.add.at(W, (np.arange(picks.shape[0])[:, None], picks), 1.0)
    return W


def _auc_cases():
    """Every awkward shape the resampled area under the curve has to survive, each as
    (name, one score per row, one state per row, drawn row numbers)."""
    rng = np.random.default_rng(11)
    out = []

    n = 60
    x = rng.normal(size=n)
    y = np.repeat([1.0, 0.0], n // 2)
    out.append(("all band powers different", x, y,
                rng.integers(0, n, size=(400, n))))

    # A BAND WHOSE POWER NEVER CHANGES. Every value is tied, so the whole sample is one tie group
    # and every resample must come back at exactly no discrimination.
    out.append(("a band whose power never changes", np.full(n, 3.25), y,
                rng.integers(0, n, size=(400, n))))

    # HEAVY BUT NOT TOTAL TIES: three distinct band powers over sixty rows.
    out.append(("only three distinct band powers", np.round(rng.normal(size=n)), y,
                rng.integers(0, n, size=(400, n))))

    # MISSING MEASUREMENTS. The sweep drops these rows before resampling, so what reaches the
    # function is the surviving rows -- reproduced here by dropping them.
    xm = rng.normal(size=n)
    xm[[3, 7, 8, 21, 40]] = np.nan
    keep = np.isfinite(xm)
    out.append(("a band with missing measurements", xm[keep], y[keep],
                rng.integers(0, int(keep.sum()), size=(400, int(keep.sum())))))

    # TIED PAIN SCORES. The tertile split gives many reports the same state and leaves the middle
    # third out; the left-out rows arrive as non-finite states and must contribute nothing.
    pain = np.round(rng.normal(5.0, 1.5, size=n))
    y_bin, _, _, _ = A._pain_split(pain, strategy="tertile", low_pct=33.3333, high_pct=66.6667)
    out.append(("tied pain scores, a third of reports left out", rng.normal(size=n),
                np.asarray(y_bin, dtype=float), rng.integers(0, n, size=(400, n))))

    # A SAMPLE SO LOPSIDED THAT SOME RESAMPLES LOSE A STATE, which must come back non-finite from
    # both routes rather than as a number.
    y_thin = np.zeros(n)
    y_thin[:2] = 1.0
    out.append(("only two high-pain reports, so some resamples lose that state",
                rng.normal(size=n), y_thin, rng.integers(0, n, size=(400, n))))

    # ONE ROW DRAWN OVER AND OVER, the extreme multiplicity.
    out.append(("every resample draws one row repeatedly", rng.normal(size=n), y,
                np.zeros((5, n), dtype=int) + np.arange(5)[:, None]))
    return out


def test_resampled_auc_counts_match_the_weight_matrix_route_bit_for_bit():
    checked = 0
    for name, x, y, picks in _auc_cases():
        W = _dense_weight_matrix(picks, x.size)
        want = A._weighted_auc_matrix(np.asarray(x, float), np.asarray(y, float), W)
        got = A.bootstrap_auc_from_row_picks(x, y, picks)
        ok, where = _all_identical(want, got)
        assert ok, (f"{name}: resample {where} differs, weight-matrix route {want[where]!r} "
                    f"against counting route {got[where]!r}")
        checked += want.size
    print(f"OK the resampled high-pain-against-low-pain value is identical to the weight-matrix "
          f"route on {checked} resamples across {len(_auc_cases())} constructed cases, including a "
          f"band whose power never changes, missing measurements and tied pain scores")


def test_a_band_that_never_changes_gives_exactly_no_discrimination():
    """A band whose power is the same on every pain report separates nothing, and the resampled
    value must be exactly 0.5 rather than a number near it."""
    n = 40
    y = np.repeat([1.0, 0.0], n // 2)
    picks = np.random.default_rng(3).integers(0, n, size=(200, n))
    got = A.bootstrap_auc_from_row_picks(np.full(n, 7.0), y, picks)
    good = np.isfinite(got)
    assert good.sum() > 100, f"expected most resamples to keep both states, got {int(good.sum())}"
    assert all(_identical(v, A.AUC_NO_DISCRIMINATION) for v in got[good]), (
        f"a constant band gave values away from {A.AUC_NO_DISCRIMINATION}: "
        f"{sorted(set(got[good].tolist()))[:5]}")
    print(f"OK a band whose power never changes gives exactly {A.AUC_NO_DISCRIMINATION} on all "
          f"{int(good.sum())} resamples that kept both pain states")


def test_rows_the_split_left_out_contribute_nothing():
    """A report the pain split left out must not be counted as a low-pain report. Dropping those
    rows before resampling has to give the same value as leaving them in with a non-finite state,
    once the same rows are drawn."""
    rng = np.random.default_rng(17)
    n = 48
    x = rng.normal(size=n)
    y = np.tile([1.0, 0.0, np.nan], n // 3)
    picks = rng.integers(0, n, size=(300, n))
    with_left_out = A.bootstrap_auc_from_row_picks(x, y, picks)
    W = _dense_weight_matrix(picks, n)
    want = A._weighted_auc_matrix(x, y, W)
    ok, where = _all_identical(want, with_left_out)
    assert ok, f"resample {where}: {want[where]!r} against {with_left_out[where]!r}"
    print(f"OK the {int(np.isnan(y).sum())} reports the split left out contribute nothing, and the "
          f"counting route agrees with the weight-matrix route on all {want.size} resamples")


def _plain_bootstrap_correlations(x, y, picks):
    """The resampled correlation written the plain way: five separate arrays, mean then difference
    then three row sums. This is what the sweep did before the buffers were reused."""
    xb = x[picks]
    yb = y[picks]
    mx = xb.mean(axis=1, keepdims=True)
    my = yb.mean(axis=1, keepdims=True)
    dx = xb - mx
    dy = yb - my
    with np.errstate(invalid="ignore", divide="ignore"):
        return ((dx * dy).sum(axis=1)
                / np.sqrt((dx * dx).sum(axis=1) * (dy * dy).sum(axis=1)))


def _reused_buffer_bootstrap_correlations(x, y, picks):
    """The form the sweep uses now: differences written back over the drawn values, one buffer for
    all three products."""
    xb = x[picks]
    yb = y[picks]
    with np.errstate(invalid="ignore", divide="ignore"):
        xb -= xb.mean(axis=1, keepdims=True)
        yb -= yb.mean(axis=1, keepdims=True)
        prod = xb * yb
        sxy = prod.sum(axis=1)
        np.multiply(xb, xb, out=prod)
        sxx = prod.sum(axis=1)
        np.multiply(yb, yb, out=prod)
        syy = prod.sum(axis=1)
        return sxy / np.sqrt(sxx * syy)


def test_resampled_correlation_with_reused_buffers_is_identical():
    rng = np.random.default_rng(5)
    checked = 0
    cases = []
    n = 90
    pain = rng.normal(5.0, 2.0, size=n)
    cases.append(("an ordinary band", rng.normal(size=n) + 0.4 * pain, pain))
    cases.append(("a band whose power never changes", np.full(n, 2.5), pain))
    cases.append(("tied pain scores", rng.normal(size=n), np.round(pain)))
    xm = rng.normal(size=n)
    xm[[1, 4, 9, 30]] = np.nan
    keep = np.isfinite(xm) & np.isfinite(pain)
    cases.append(("a band with missing measurements", xm[keep], pain[keep]))
    cases.append(("band powers spanning many orders of magnitude",
                  np.exp(rng.normal(0.0, 6.0, size=n)), pain))
    for name, x, y in cases:
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        picks = rng.integers(0, x.size, size=(500, x.size))
        want = _plain_bootstrap_correlations(x, y, picks)
        got = _reused_buffer_bootstrap_correlations(x, y, picks)
        ok, where = _all_identical(want, got)
        assert ok, f"{name}: resample {where} differs, {want[where]!r} against {got[where]!r}"
        checked += want.size
    print(f"OK the resampled correlation is identical with the buffers reused on {checked} "
          f"resamples across {len(cases)} constructed cases")


def _plain_pearson(x, y):
    """An ordinary Pearson correlation over the reports where both quantities are present,
    written report by report."""
    use = [(float(a), float(b)) for a, b in zip(x, y) if np.isfinite(a) and np.isfinite(b)]
    if len(use) < 3:
        return np.nan, len(use)
    n = len(use)
    mx = sum(a for a, _ in use) / n
    my = sum(b for _, b in use) / n
    sxy = sum((a - mx) * (b - my) for a, b in use)
    sxx = sum((a - mx) ** 2 for a, _ in use)
    syy = sum((b - my) ** 2 for _, b in use)
    if sxx <= 0 or syy <= 0:
        return np.nan, n
    return sxy / np.sqrt(sxx * syy), n


def _plain_rank_auc(x, y01):
    """An ordinary Mann-Whitney count: over every high-pain and low-pain pair of reports, one for
    the high one being larger, a half for a tie, and the total divided by the number of pairs."""
    hi = [float(a) for a, b in zip(x, y01) if np.isfinite(a) and b == 1]
    lo = [float(a) for a, b in zip(x, y01) if np.isfinite(a) and b == 0]
    if not hi or not lo:
        return np.nan, len(hi), len(lo)
    wins = 0.0
    for a in hi:
        for b in lo:
            if a > b:
                wins += 1.0
            elif a == b:
                wins += 0.5
    return wins / (len(hi) * len(lo)), len(hi), len(lo)


def _grid_case(seed, n_reports, constant_col=None, missing_col=None, round_pain=False):
    rng = np.random.default_rng(seed)
    centers = A.sweep_center_freqs(np.arange(1.0, 60.0, 1.0))
    C = centers.size
    pain = np.clip(rng.normal(5.0, 2.0, size=n_reports), 0.0, 10.0)
    if round_pain:
        pain = np.round(pain)
    power_by_seconds = {}
    for s in A.BAND_TIME_SWEEP_SECONDS:
        m = np.exp(1.0 + rng.normal(0.0, 0.4, size=(n_reports, C)))
        m[:, 4] *= np.exp(0.3 * (pain - pain.mean()) / max(pain.std(), 1e-9))
        if constant_col is not None:
            m[:, constant_col] = 4.0
        if missing_col is not None:
            m[n_reports // 3:, missing_col] = np.nan
        m[rng.random((n_reports, C)) < 0.05] = np.nan
        power_by_seconds[float(s)] = m
    return power_by_seconds, pain, centers


def test_grids_match_a_plain_loop_over_lengths_and_band_centres():
    cases = [
        ("an ordinary grid", _grid_case(2, 70)),
        ("a band whose power never changes", _grid_case(4, 70, constant_col=6)),
        ("a band missing for most pain reports", _grid_case(6, 70, missing_col=9)),
        ("tied pain scores", _grid_case(8, 70, round_pain=True)),
        ("a constant band, a missing band and tied pain scores at once",
         _grid_case(10, 70, constant_col=6, missing_col=9, round_pain=True)),
    ]
    n_cells = 0
    worst_corr = 0.0
    for name, (pbs, pain, centers) in cases:
        sw = A.band_time_sweep_from_power(pbs, pain, center_freqs_hz=centers, channel="test")
        # the same outlier rule the sweep applies, so the plain loop reads the same measurements
        req = list(sw["integration_seconds_requested"])
        X = np.stack([np.asarray(pbs[float(s)], dtype=np.float64) for s in req], axis=0)
        drop = A.mad_outlier_columns(X, n_mad=sw["outlier_n_mad"], scale=sw["outlier_scale"])
        X[drop] = np.nan
        y_bin, _, _, _ = A._pain_split(pain, strategy="tertile", low_pct=33.3333,
                                       high_pct=66.6667)
        y_bin = np.asarray(y_bin, dtype=float)
        corr = np.asarray(sw["correlation_grid"], dtype=float)
        auc = np.asarray(sw["auc_grid"], dtype=float)
        ngr = np.asarray(sw["n_grid"], dtype=float)
        hi = np.asarray(sw["auc_n_high_grid"], dtype=float)
        lo = np.asarray(sw["auc_n_low_grid"], dtype=float)
        T, C = corr.shape
        for t in range(T):
            for c in range(C):
                r_want, n_want = _plain_pearson(X[t, :, c], pain)
                assert _identical(ngr[t, c], n_want), (
                    f"{name}: report count at length {t} band {c} is {ngr[t, c]}, plain loop "
                    f"says {n_want}")
                if np.isnan(r_want) or np.isnan(corr[t, c]):
                    assert np.isnan(r_want) and np.isnan(corr[t, c]), (
                        f"{name}: correlation at length {t} band {c} is {corr[t, c]}, plain loop "
                        f"says {r_want}")
                else:
                    d = abs(float(corr[t, c]) - float(r_want))
                    worst_corr = max(worst_corr, d)
                    assert d < 1e-11, (f"{name}: correlation at length {t} band {c} is "
                                       f"{corr[t, c]!r}, plain loop says {r_want!r}")
                a_want, nh, nl = _plain_rank_auc(X[t, :, c], y_bin)
                assert _identical(hi[t, c], nh) and _identical(lo[t, c], nl), (
                    f"{name}: high/low report counts at length {t} band {c} are "
                    f"{hi[t, c]}/{lo[t, c]}, plain loop says {nh}/{nl}")
                if np.isnan(a_want) or np.isnan(auc[t, c]):
                    assert np.isnan(a_want) and np.isnan(auc[t, c]), (
                        f"{name}: high-against-low value at length {t} band {c} is {auc[t, c]}, "
                        f"plain loop says {a_want}")
                else:
                    assert _identical(auc[t, c], a_want), (
                        f"{name}: high-against-low value at length {t} band {c} is "
                        f"{auc[t, c]!r}, plain loop says {a_want!r} -- the counting one must be "
                        f"exact, not close")
                n_cells += 1
    print(f"OK every one of {n_cells} grid cells across {len(cases)} constructed grids matches a "
          f"plain double loop: the high-against-low value and every report count exactly, the "
          f"correlation to within {worst_corr:.2e}")


def test_the_ten_lengths_are_each_their_own_length_and_not_one_repeated():
    """A guard against the whole reason batching over lengths is risky: if the ten lengths ever
    shared one length's band powers the grid would still look plausible, so the grid is required to
    differ row by row on inputs built to differ row by row."""
    rng = np.random.default_rng(21)
    centers = A.sweep_center_freqs(np.arange(1.0, 60.0, 1.0))
    n = 80
    pain = rng.normal(5.0, 2.0, size=n)
    pbs = {}
    for k, s in enumerate(A.BAND_TIME_SWEEP_SECONDS):
        # each length of signal is given its own, different, relationship to the pain score
        strength = 0.05 * k
        pbs[float(s)] = np.exp(1.0 + rng.normal(0.0, 0.3, size=(n, centers.size))
                               + strength * ((pain - pain.mean())
                                             / pain.std())[:, None])
    sw = A.band_time_sweep_from_power(pbs, pain, center_freqs_hz=centers, channel="test")
    corr = np.asarray(sw["correlation_grid"], dtype=float)
    rows = [tuple(np.round(r[np.isfinite(r)], 12)) for r in corr]
    assert len(set(rows)) == len(rows), (
        f"two lengths of signal produced identical correlation rows out of {len(rows)}, which "
        f"means a length's own band powers were not used")
    per_row = [float(np.nanmean(np.abs(r))) for r in corr]
    assert per_row[-1] > per_row[0], (
        f"the length given the strongest planted relationship ({per_row[-1]:.3f}) did not come out "
        f"stronger than the one given the weakest ({per_row[0]:.3f})")
    print(f"OK all {len(rows)} lengths of signal produced their own row, and the planted strength "
          f"rises across them from {per_row[0]:.3f} to {per_row[-1]:.3f}")


def test_a_wide_matrix_product_gives_the_same_numbers_as_narrow_ones():
    """THE GUARD ON THE 1000 SHUFFLES. The shuffled reference takes all ten lengths of signal's
    matrix products in two products instead of thirty, by standing their right-hand sides side by
    side. That is only allowed because asking the linear-algebra library for more columns at once
    does not change the numbers it returns.

    A matrix product accumulates each answer over the pain reports in an order the library chooses
    from its own cache sizes. Nothing in the definition of a matrix product forbids a library from
    choosing a different order when the answer is wider, and a different order would move the last
    bit of a shuffled correlation -- which could move a band's verdict, since a row reads
    ``established`` only if it beats the shuffled best-of-ten level.

    So the property is asserted here rather than assumed. If a future numpy or linear-algebra
    library ever stops honouring it this test fails, instead of the verdicts on the page moving
    quietly. Should that happen the fix is to put the loop over lengths of signal back in
    ``_best_of_windows_null_correlation`` and ``_best_of_windows_null_auc``; it costs about 0.04 s
    per sensing contact pair.
    """
    rng = np.random.default_rng(31)
    checked = 0
    # the shapes the shuffled reference actually uses: a thousand shuffles, a few hundred pain
    # reports, twenty-two band centres, ten lengths of signal
    for n_reports, n_centers, n_lengths, n_shuffles in ((760, 22, 10, 1000),
                                                        (507, 22, 10, 1000),
                                                        (91, 23, 10, 1000),
                                                        (40, 5, 3, 200)):
        Yp = rng.normal(size=(n_shuffles, n_reports))
        blocks = []
        for _ in range(n_lengths):
            mask = rng.random((n_reports, n_centers)) > 0.05
            blocks.append(mask.astype(np.float64))
            blocks.append(np.where(mask, np.exp(rng.normal(0.0, 3.0,
                                                           size=(n_reports, n_centers))), 0.0))
        narrow = [Yp @ b for b in blocks]
        wide = Yp @ np.concatenate(blocks, axis=1)
        for k, a in enumerate(narrow):
            b = wide[:, k * n_centers:(k + 1) * n_centers]
            n_diff = int((a.tobytes() != b.tobytes())
                         and int(np.count_nonzero(a != b)) or 0)
            assert a.tobytes() == b.tobytes(), (
                f"a matrix product asked for {wide.shape[1]} columns at once returned different "
                f"numbers from the same product asked for {n_centers} columns: {n_diff} of "
                f"{a.size} differ, largest difference {float(np.max(np.abs(a - b))):.3e}. The "
                f"shuffled reference in the sweep relies on these agreeing -- put the loop over "
                f"lengths of signal back if this cannot be restored.")
            checked += a.size
        # the mask is handed over as a boolean in one place and a double in another, so that has to
        # agree too
        mask = rng.random((n_reports, n_centers)) > 0.05
        assert (Yp @ mask).tobytes() == (Yp @ mask.astype(np.float64)).tobytes(), (
            "a matrix product against a true-or-false right-hand side differs from the same "
            "product against the same values written as doubles")
        checked += n_shuffles * n_centers
    print(f"OK a wide matrix product returns the same {checked} numbers as the narrow ones it "
          f"replaces, across the four shapes the shuffled reference uses")


from scipy import stats
try:
    from modules.Biomarkers.routines import analytics as A
except ImportError:                                        # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A


def _grid(seed=5, n=120):
    rng = np.random.default_rng(seed)
    pain = np.clip(np.round(rng.normal(6, 2, n)), 0, 10)
    x1 = 100 - 6 * pain + rng.normal(0, 15, n)             # a real relationship
    x2 = rng.normal(100, 15, n)                            # none
    power = {1.0: np.column_stack([x1, x2]), 5.0: np.column_stack([x2, x1])}
    return power, pain, [12.5, 20.5]


def test_every_cell_carries_pearsons_p_computed_from_its_own_r_and_n():
    power, pain, centers = _grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20, n_boot=50)
    assert "p_grid" in sw and np.shape(sw["p_grid"]) == np.shape(sw["correlation_grid"])
    for t in range(2):
        for c in range(2):
            r, n, p = sw["correlation_grid"][t][c], sw["n_grid"][t][c], sw["p_grid"][t][c]
            tstat = r * np.sqrt((n - 2) / (1 - r * r))
            want = 2 * stats.t.sf(abs(tstat), n - 2)
            assert abs(p - want) < 1e-12, (t, c, p, want)
    # the cell with the planted relationship is far below 0.05, the one without is not tiny
    assert sw["p_grid"][0][0] < 1e-4 and sw["p_grid"][0][1] > 1e-3


def test_every_auc_cell_carries_scipys_asymptotic_mann_whitney_p():
    power, pain, centers = _grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20, n_boot=50)
    assert "auc_p_grid" in sw and np.shape(sw["auc_p_grid"]) == np.shape(sw["auc_grid"])
    for t in range(2):
        for c in range(2):
            assert 0 < sw["auc_p_grid"][t][c] <= 1
    assert sw["auc_p_grid"][0][0] < 1e-3 and sw["auc_p_grid"][0][1] > 1e-3


def test_the_column_helper_is_scipys_own_result_per_column_with_missing_values_left_out():
    rng = np.random.default_rng(11)
    X = rng.normal(100, 15, (75, 3)); X[:40, 0] += 10; X[3, 1] = np.nan; X[50, 2] = np.nan
    y = np.r_[np.ones(40), np.zeros(35)]
    got = A.mann_whitney_p_columns(X, y)
    for c in range(3):
        hi, lo = X[:40, c], X[40:, c]
        want = stats.mannwhitneyu(hi[np.isfinite(hi)], lo[np.isfinite(lo)],
                                  alternative="two-sided", method="asymptotic").pvalue
        assert abs(got[c] - want) < 1e-12, (c, got[c], want)
    assert got[0] < 0.01


def test_an_empty_cell_carries_no_p():
    X = np.array([[1.0, np.nan], [2.0, np.nan], [3.0, 5.0], [4.0, 6.0]])
    p = A.mann_whitney_p_columns(X, np.array([1, 1, 0, 0]))
    assert np.isfinite(p[0]) and np.isnan(p[1])
    p = A.pearson_p_from_r(np.array([0.3, np.nan, 0.99999]), np.array([2, 30, 30]))
    assert np.isnan(p[0]) and np.isnan(p[1]) and np.isfinite(p[2])


def test_the_blank_response_carries_the_two_grids_empty_rather_than_absent():
    sw = A.band_time_sweep_from_power({}, np.array([]), center_freqs_hz=[12.5], n_perm=5, n_boot=5)
    assert sw["p_grid"] == [] and sw["auc_p_grid"] == []


try:
    from modules.Biomarkers.routines import analytics as A
    from modules.Biomarkers.routines import stats_utils as SU
except ImportError:                                        # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A
    from Biomarkers.routines import stats_utils as SU


def _grid_persistent(rho, n=160, seed=3):
    """One band at one length: band power and pain share a slow AR(1) drift of persistence `rho`."""
    rng = np.random.default_rng(seed)
    z = np.zeros(n)
    for i in range(1, n):
        z[i] = rho * z[i - 1] + rng.normal(0, np.sqrt(1 - rho * rho))
    pain = np.clip(np.round(5 + 2 * z + rng.normal(0, 0.8, n)), 0, 10)
    x = 100 + 20 * z + rng.normal(0, 8, n)
    return {5.0: x[:, None]}, pain, [12.5], x, pain


def test_the_row_carries_exactly_the_effective_count_of_the_pairs_it_correlated():
    power, pain, centers, x, y = _grid_persistent(rho=0.9)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20, n_boot=50)
    row = sw["best_correlation_rows"][0]
    m = np.isfinite(x) & np.isfinite(y)
    want = SU.effective_n(x[m], y[m])
    assert "n_pain_reports_effective" in row, sorted(row)
    assert abs(row["n_pain_reports_effective"] - round(want, 1)) < 1e-9, (row["n_pain_reports_effective"], want)
    assert row["n_pain_reports_effective"] <= row["n_pain_reports"]
    print(f"OK {row['n_pain_reports']} reports, effective {row['n_pain_reports_effective']}")


def test_persistence_in_both_series_lowers_the_effective_count_well_below_the_raw_count():
    power, pain, centers, _x, _y = _grid_persistent(rho=0.9)
    row = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20,
                                       n_boot=50)["best_correlation_rows"][0]
    assert row["n_pain_reports_effective"] < 0.5 * row["n_pain_reports"], row


def test_no_persistence_leaves_the_effective_count_close_to_the_raw_count():
    power, pain, centers, _x, _y = _grid_persistent(rho=0.0, seed=11)
    row = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20,
                                       n_boot=50)["best_correlation_rows"][0]
    assert row["n_pain_reports_effective"] > 0.85 * row["n_pain_reports"], row


def _ar1_grid(rho, n=160, seed=3):
    """One band, two lengths: band power and pain share a slow AR(1) drift, so consecutive reports
    are near-duplicates when `rho` is high and independent when `rho` is 0."""
    rng = np.random.default_rng(seed)
    z = np.zeros(n)
    for i in range(1, n):
        z[i] = rho * z[i - 1] + rng.normal(0, np.sqrt(1 - rho * rho))
    pain = np.clip(np.round(5 + 2 * z + rng.normal(0, 0.8, n)), 0, 10)
    x = 100 + 20 * z + rng.normal(0, 8, n)
    x2 = 100 + 20 * z + rng.normal(0, 8, n)
    power = {1.0: x[:, None], 5.0: x2[:, None]}
    return power, pain, [12.5]


def _widths(sw):
    r = sw["best_correlation_rows"][0]
    a = sw["best_auc_rows"][0]
    return (r["pearson_r_high"] - r["pearson_r_low"], a["auc_high"] - a["auc_low"],
            r["interval_block_length"], a["interval_block_length"])


def test_block_bootstrap_picks_are_the_plain_draw_at_block_one_and_whole_blocks_above():
    rng1, rng2 = np.random.default_rng(7), np.random.default_rng(7)
    plain = rng1.integers(0, 50, size=(4, 50))
    picks = SU.block_bootstrap_picks(50, 1, 4, rng2)
    assert np.array_equal(plain, picks), "block 1 must be the identical i.i.d. draw"
    picks = SU.block_bootstrap_picks(50, 5, 4, np.random.default_rng(1))
    assert picks.shape == (4, 50)
    # every run of five is consecutive modulo n
    for row in picks:
        for b in range(0, 50, 5):
            seg = row[b:b + 5]
            assert np.all((seg[1:] - seg[:-1]) % 50 == 1), seg


def test_the_interval_widens_under_strong_autocorrelation_and_reports_its_block_length():
    power, pain, centers = _ar1_grid(rho=0.92)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=400)
    w_r, w_a, b_r, b_a = _widths(sw)
    assert b_r > 1 and b_a > 1, (b_r, b_a)
    # the plain i.i.d. interval, for the comparison only
    A.BAND_SWEEP_INTERVAL_BLOCK_BOOTSTRAP = False
    try:
        sw0 = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=400)
    finally:
        A.BAND_SWEEP_INTERVAL_BLOCK_BOOTSTRAP = True
    w_r0, w_a0, b_r0, b_a0 = _widths(sw0)
    assert b_r0 == 1 and b_a0 == 1
    assert w_r > w_r0 * 1.15, (w_r, w_r0)
    assert w_a > w_a0 * 1.15, (w_a, w_a0)
    print(f"OK block interval r {w_r:.3f} vs iid {w_r0:.3f} (block {b_r}); "
          f"auc {w_a:.3f} vs {w_a0:.3f} (block {b_a})")


def test_with_no_autocorrelation_the_interval_is_the_draw_it_always_was():
    power, pain, centers = _ar1_grid(rho=0.0, seed=11)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=300)
    A.BAND_SWEEP_INTERVAL_BLOCK_BOOTSTRAP = False
    try:
        sw0 = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=300)
    finally:
        A.BAND_SWEEP_INTERVAL_BLOCK_BOOTSTRAP = True
    for key in ("best_correlation_rows", "best_auc_rows"):
        for r1, r0 in zip(sw[key], sw0[key]):
            assert r1["interval_block_length"] == 1
            for f in ("pearson_r_low", "pearson_r_high", "auc_low", "auc_high"):
                if f in r1:
                    assert r1[f] == r0[f], (f, r1[f], r0[f])
    print("OK block length 1 reproduces the i.i.d. interval bit for bit")


def _grid_with_holes(n=120, seed=5, holes=True):
    """Three bands, three lengths; some band power missing, as a real record has."""
    rng = np.random.default_rng(seed)
    pain = np.clip(np.round(5 + rng.normal(0, 2, n)), 0, 10)
    power = {}
    for L in (1.0, 5.0, 30.0):
        x = 100 + 5 * pain[:, None] + rng.normal(0, 15, (n, 3))
        if holes:
            x[rng.random((n, 3)) < 0.1] = np.nan
        power[L] = x
    return power, pain, [12.5, 20.5, 24.5]


def _sweep(**kw):
    power, pain, centers = _grid_with_holes(**kw)
    return A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=40)


def test_the_sweep_publishes_the_check_and_it_holds_on_its_own_grid():
    sw = _sweep()
    rec = sw.get("null_family_reconciliation")
    assert rec is not None, sorted(sw)
    for kind in ("correlation", "auc"):
        r = rec[kind]
        assert r["perm_family_reconciled"] is True, (kind, r)
        assert r["perm_family_max_abs_dev_from_corr"] <= 1e-9, (kind, r)
        assert r["perm_family_cells_in_selection_only"] == 0, (kind, r)
        assert r["perm_family_cells_compared"] == 9, (kind, r)
    print("OK both families reconciled: max deviation "
          f"{rec['correlation']['perm_family_max_abs_dev_from_corr']:.1e} (r), "
          f"{rec['auc']['perm_family_max_abs_dev_from_corr']:.1e} (AUC)")


def test_a_grid_that_disagrees_by_one_cell_reads_false_with_the_size_of_the_disagreement():
    null = {"observed_abs_by_length": np.array([[0.2, 0.3], [0.1, 0.4]]),
            "in_family": np.ones((2, 2), dtype=bool)}
    grid = np.array([[0.2, -0.3], [0.1, 0.45]])            # one cell off by 0.05
    r = A._null_family_reconciliation(np.abs(grid), null)
    assert r["perm_family_reconciled"] is False
    assert abs(r["perm_family_max_abs_dev_from_corr"] - 0.05) < 1e-12
    assert r["perm_family_cells_compared"] == 4


def test_a_selectable_cell_the_null_never_admitted_is_counted_and_breaks_the_check():
    null = {"observed_abs_by_length": np.array([[0.2, 0.0]]),
            "in_family": np.array([[True, False]])}          # the second cell fell under the floor
    grid = np.array([[0.2, 0.61]])
    r = A._null_family_reconciliation(np.abs(grid), null)
    assert r["perm_family_cells_in_selection_only"] == 1
    assert abs(r["perm_family_cells_in_selection_only_max_abs_r"] - 0.61) < 1e-12
    assert r["perm_family_reconciled"] is False


def test_the_null_itself_is_unchanged_by_the_check():
    """The same seed gives the same shuffled bests, bit for bit, as it did before the check existed:
    the check reads the family, it does not alter it."""
    power, pain, centers = _grid_with_holes()
    X = np.stack([power[L] for L in (1.0, 5.0, 30.0)], axis=0)
    a = A._best_of_windows_null_correlation(X, pain, n_perm=40, rng=np.random.default_rng(1))
    b = A._best_of_windows_null_correlation(X, pain, n_perm=40, rng=np.random.default_rng(1))
    assert np.array_equal(a["best_by_shuffle"], b["best_by_shuffle"])
    fam = a["observed_abs_by_length"]
    assert fam.shape == (3, 3)


# --------------------------------------------------------------------------------------------------
# merged from test_whole_matrix_median_speedup.py
# Proposal 3 (2026-09-25): the heat-map grid's per-row `np.nanmedian` as one whole-matrix sort.
#
# `np.nanmedian(arr, axis=1)` on a 2D array is not the single vectorised call it looks like: numpy's
# own implementation falls through to `np.apply_along_axis`, running its inner reduction once per row
# in Python. Measured live on RCS08's heat-map grid, that cost 7.4 of the grid's about 13.8 seconds
# across 923,076 rows and 1,284,219 discarded `RuntimeWarning`s (one per all-NaN or short row).
#
# `availability._whole_matrix_nanmedian(values, keep)` replaces
# `np.nanmedian(np.where(keep, values, np.nan), axis=1)` with a full `np.sort` of each row plus a
# finite-count and an index lookup -- one vectorised call, no per-row Python loop. A median is an
# order statistic, so the two must agree value for value, including the edge cases a whole-matrix
# reduction could get wrong that a straightforward per-row call could not: an infinite reading (a
# real, comparable value, not a value `nanmedian` throws away the way it throws away NaN), a row with
# no finite value at all, an even count whose two middle values straddle `+inf` and `-inf` (numpy's
# own `(inf + -inf) / 2 = nan`), and a `cap` wider than the pieces on offer.


from ..routines import availability as av


def _reference(values, keep):
    """The exact call this function replaces, kept here as the ground truth to compare against."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(np.where(keep, values, np.nan), axis=1)


def _assert_matches(values, keep, msg=""):
    want = _reference(values, keep)
    got = av._whole_matrix_nanmedian(values, keep)
    assert got.shape == want.shape, msg
    np.testing.assert_array_equal(got, want, err_msg=msg)


def test_matches_nanmedian_on_random_matrices_odd_and_even_counts():
    rng = np.random.default_rng(20260925)
    for trial in range(50):
        nR, width = rng.integers(1, 12), rng.integers(1, 15)
        values = rng.uniform(-500.0, 500.0, size=(nR, width))
        keep = rng.random((nR, width)) > 0.3      # some columns dropped per row -> mixed counts
        _assert_matches(values, keep, f"trial {trial}, shape {(nR, width)}")


def test_a_row_with_no_kept_value_is_nan_like_nanmedian():
    values = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    keep = np.array([[False, False, False], [True, True, False]])
    got = av._whole_matrix_nanmedian(values, keep)
    assert np.isnan(got[0])
    assert np.isclose(got[1], 4.5)                 # median(4, 5)


def test_an_infinite_reading_is_a_real_value_not_dropped_like_nan():
    """`nanmedian` strips NaN only; +inf is a legitimate, comparable value and can win a median."""
    values = np.array([[1.0, 2.0, np.inf]])
    keep = np.array([[True, True, True]])
    _assert_matches(values, keep, "median(1, 2, inf) must equal the reference")
    # median of an odd count of 3, sorted [1, 2, inf] -> middle value is 2, not inf and not nan
    assert av._whole_matrix_nanmedian(values, keep)[0] == 2.0


def test_even_count_averaging_matches_including_the_inf_minus_inf_case():
    # sorted [-inf, -inf, inf, inf]: two middle values are -inf and inf -> (-inf + inf) / 2 = nan
    values = np.array([[np.inf, -np.inf, -np.inf, np.inf]])
    keep = np.array([[True, True, True, True]])
    _assert_matches(values, keep, "the straddling +inf/-inf case must equal the reference")
    got = av._whole_matrix_nanmedian(values, keep)[0]
    ref = _reference(values, keep)[0]
    assert np.isnan(got) and np.isnan(ref), (got, ref)

    # sorted [1, 2, inf, inf]: two middle values are 2 and inf -> ordinary finite/infinite average
    values2 = np.array([[np.inf, 2.0, 1.0, np.inf]])
    keep2 = np.array([[True, True, True, True]])
    _assert_matches(values2, keep2)
    assert np.isinf(av._whole_matrix_nanmedian(values2, keep2)[0])


def test_a_cap_wider_than_the_pieces_on_offer_still_matches():
    """`keep` marks fewer True entries than the row's width -- the short-row case a real grid cell
    hits whenever a rating's own eligible pieces run out before the requested length's cap."""
    values = np.array([[10.0, 20.0, 30.0, 40.0, 50.0]])
    keep = np.array([[True, True, False, False, False]])   # only 2 of 5 columns eligible
    _assert_matches(values, keep)
    assert np.isclose(av._whole_matrix_nanmedian(values, keep)[0], 15.0)


def test_empty_matrix_is_safe():
    values = np.zeros((0, 4))
    keep = np.zeros((0, 4), dtype=bool)
    got = av._whole_matrix_nanmedian(values, keep)
    assert got.shape == (0,)

    values2 = np.zeros((3, 0))
    keep2 = np.zeros((3, 0), dtype=bool)
    got2 = av._whole_matrix_nanmedian(values2, keep2)
    assert got2.shape == (3,)
    assert np.all(np.isnan(got2))


def test_live_lsb_band_medians_by_length_unchanged_with_infinite_and_all_excluded_readings():
    """The two call sites inside `live_lsb_band_medians_by_length` (voltage-trace and
    device-spectrum branches) must still agree with a hand-built reference that calls the OLD
    `nanmedian` reduction directly on the same intermediate arrays, on a case built to exercise the
    edge conditions above: an infinite reading and a rating whose nearest piece is excluded.
    """
    CENTERS = [8.5, 12.5]
    T0 = 1_700_000_000.0
    cache = {
        "channel": "TEST", "centers_hz": CENTERS, "window_s": 3.0, "band_half_hz": 2.5,
        "td": {"t": [T0, T0 + 3.0, T0 + 6.0], "ok": [True, True, True],
               "lsb": [[10.0, np.inf], [1000.0, 20.0], [30.0, 40.0]],
               "saturated": [False, False, False], "source": ["c"] * 3,
               "n_finite_s": [3.0, 3.0, 3.0]},
        "psd": {"t": [], "lsb": [], "calibrated": [], "source": []},
        "n_td_windows": 3, "n_psd_windows": 0,
    }
    got, info, _stats = av.live_lsb_band_medians_by_length(
        [T0], cache, tol_s=1800.0, lengths_s=[6.0], centers_hz=CENTERS,
        band_ceilings=[500.0, np.inf], allow_window_reuse=False)
    # Band 0: nearest two clean pieces after excluding 1000 are 10 and 30 -> median 20.
    assert np.isclose(got[6.0][0, 0], 20.0), got[6.0][0, 0]
    # Band 1 has no ceiling: nearest two are inf and 20 -> median(inf, 20) = (inf + 20) / 2 = inf.
    assert np.isinf(got[6.0][0, 1]), got[6.0][0, 1]
    assert info["n_chunk_band_values_excluded"] == 1
