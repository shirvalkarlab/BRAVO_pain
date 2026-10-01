"""The design rule's two-component filter skips the padding at the end of each stretch, and every
number stays the same to the last binary digit (2026-10-02, the PI: faster requests on the
Jetstream2 BRAVO, every number unchanged).

The fit's panel holds every stretch of recording as one row, padded with missing readings to the
length of the longest. On RCS08 that is 366 rows x 1,499 steps = 548,634 cells, of which 42,684 hold
a reading: the committed compiled loop (`_filter_2comp_kernel`, decision 269) did the arithmetic for
every cell, padding included, about 1,600 times a fit. After a stretch's last reading its terms are
exact zeros and nothing it carries forward is read again, so the new loop stops visiting it there;
the per-step sum still runs over the whole row, in numpy's own pairwise order, with the finished
stretches' zeros in their places. The facts about the panel that no parameter changes (which cells
hold a reading, where each stretch ends) are worked out once per fit instead of once per call.

These tests hold the new loop to the committed one bit for bit, on panels whose row counts hit every
branch of the pairwise sum (under 8, exactly 8, up to 128, over 128) and whose stretches end at
different places, including rows with no reading after the first and a missing first reading; and
the whole fit to the committed loop's fit. Skipped where numba is not installed (CI).
"""
import numpy as np
import pytest

pytest.importorskip("numba")

from ClosedLoopDeployment import design_rule as DR


def _same(a, b):
    """Bit-identical, or both not-a-number."""
    if np.isnan(a) and np.isnan(b):
        return True
    return np.float64(a).tobytes() == np.float64(b).tobytes()


def _panel(seed, s, l):
    rng = np.random.default_rng(seed)
    Y = np.full((s, l), np.nan)
    for i in range(s):
        n = min(l, int(rng.choice([1, 2, 3, max(1, l // 7), max(1, l // 2), l])))
        y = 100 + np.cumsum(rng.normal(0, 3, n)) + rng.normal(0, 5, n)
        gaps = rng.random(n) < 0.15
        gaps[0] = False
        y[gaps] = np.nan
        Y[i, :n] = y
    if s > 1:
        Y[1, 0] = np.nan                                       # a stretch whose first reading is missing
    return Y


# Row counts chosen for the pairwise sum's branches: under 8, exactly 8, up to 128, over 128 (one
# and two levels of halving); RCS08's own 366 rows; and a panel of only its first column.
_SHAPES = [(1, 1), (1, 2), (1, 50), (3, 40), (7, 30), (8, 30), (9, 25), (60, 300), (129, 80),
           (300, 120), (366, 200), (5, 1)]


def _draws(Y, seed, n):
    v = Y[np.isfinite(Y)]
    mbar = float(np.median(v)) if v.size else 100.0
    var = float(np.var(v)) if v.size > 1 else 1.0
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        phi_s = float(rng.uniform(0.3, 0.999))
        out.append(dict(phi_s=phi_s, phi_f=float(rng.uniform(0.0, phi_s)),
                        q_s=float(rng.uniform(0.001, 3) * var), q_f=float(rng.uniform(0.001, 3) * var),
                        m=mbar + float(rng.normal(0, 3)), r0=float(rng.uniform(0.01, 3) * var)))
    # the edges: a slow component that barely decays, vanishing and huge variances
    out.append(dict(phi_s=1.0 - 1e-13, phi_f=0.5, q_s=1e-300, q_f=1e-300, m=mbar, r0=1e-300))
    out.append(dict(phi_s=0.999999, phi_f=0.999998, q_s=1e300, q_f=1e300, m=mbar, r0=1e300))
    return out


def _committed(Y, kw):
    """The committed compiled loop, called exactly as `filter_2comp` called it before this change."""
    Yc = np.ascontiguousarray(Y, dtype=float)
    vs = kw["q_s"] / max(1e-12, 1.0 - kw["phi_s"] * kw["phi_s"])
    vf = kw["q_f"] / max(1e-12, 1.0 - kw["phi_f"] * kw["phi_f"])
    ll, n = DR._filter_2comp_kernel(Yc, np.isfinite(Yc), float(kw["phi_s"]), float(kw["phi_f"]),
                                    float(kw["q_s"]), float(kw["q_f"]), float(kw["m"]),
                                    float(kw["r0"]), float(vs), float(vf), DR.LOG2PI)
    return float(ll), int(n)


def test_the_padding_skipping_filter_returns_exactly_the_committed_loops_answer():
    assert DR.COMPILED_FILTER, "numba is installed, so the compiled loop must be the one used"
    for k, (s, l) in enumerate(_SHAPES):
        Y = _panel(k, s, l)
        prep = DR._prepare_2comp_panel(Y)
        for kw in _draws(Y, 500 + k, 25):
            ll0, n0 = _committed(Y, kw)
            once = DR._filter_2comp_prepared(prep, **kw)          # the fit's path: prepared once
            each = DR.filter_2comp(Y, **kw)                       # the public path: prepared per call
            assert _same(once["loglik"], ll0) and once["n"] == n0, ((s, l), kw, once, ll0, n0)
            assert _same(each["loglik"], ll0) and each["n"] == n0, ((s, l), kw, each, ll0, n0)


def test_the_prepared_panel_lists_each_stretchs_end_correctly():
    for k, (s, l) in enumerate(_SHAPES):
        Y = _panel(100 + k, s, l)
        prep = DR._prepare_2comp_panel(Y)
        ok = np.isfinite(Y)
        last = np.array([max([t for t in range(1, l) if ok[i, t]], default=0) for i in range(s)])
        assert prep["n"] == int(ok[:, 1:].sum())
        assert [int((last >= t).sum()) for t in range(l)] == prep["n_active"].tolist()
        # the stretches still running at step t are exactly the first n_active[t] in the order kept
        for t in range(l):
            assert set(prep["pos"][:prep["n_active"][t]].tolist()) == set(np.flatnonzero(last >= t).tolist())
        assert np.array_equal(prep["Yp"], Y[prep["pos"]].T, equal_nan=True)


def test_the_whole_fit_is_the_same_as_with_the_committed_loop(monkeypatch):
    Y = _panel(7, 60, 150)
    new = DR.fit_two_component(Y, maxfev=300, restarts=1)
    monkeypatch.setattr(DR, "_two_component_runner",
                        lambda Y_: (lambda **kw: dict(zip(("loglik", "n"), _committed(Y_, kw)))))
    old = DR.fit_two_component(Y, maxfev=300, restarts=1)
    assert repr(new) == repr(old)


def test_one_fit_prepares_its_panel_once(monkeypatch):
    calls = []
    real = DR._prepare_2comp_panel
    monkeypatch.setattr(DR, "_prepare_2comp_panel", lambda Y_: calls.append(1) or real(Y_))
    DR.fit_two_component(_panel(3, 20, 60), maxfev=120, restarts=2)
    assert len(calls) == 1
