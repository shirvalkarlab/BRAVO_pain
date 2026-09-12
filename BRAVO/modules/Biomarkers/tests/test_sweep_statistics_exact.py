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
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_sweep_statistics_exact.py
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


# ---------------------------------------------------------------------------------------------
# the resampled high-pain-against-low-pain value
# ---------------------------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------------------------
# the resampled correlation
# ---------------------------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------------------------
# the grids, against a plain loop over lengths of signal and band centres
# ---------------------------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------------------------
# the one place exactness rests on the linear-algebra library rather than on arithmetic that
# cannot round
# ---------------------------------------------------------------------------------------------

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


if __name__ == "__main__":
    test_a_wide_matrix_product_gives_the_same_numbers_as_narrow_ones()
    test_resampled_auc_counts_match_the_weight_matrix_route_bit_for_bit()
    test_a_band_that_never_changes_gives_exactly_no_discrimination()
    test_rows_the_split_left_out_contribute_nothing()
    test_resampled_correlation_with_reused_buffers_is_identical()
    test_grids_match_a_plain_loop_over_lengths_and_band_centres()
    test_the_ten_lengths_are_each_their_own_length_and_not_one_repeated()
    print("All sweep-statistics exactness tests passed.")
