"""The design rule's compiled loops (numba): every one returns exactly what the plain numpy loop
returns, and loads from numba's disk cache. Skipped where numba is not installed (CI); the container
has it (decision 271).

Merged here 2026-10-05: test_design_rule_active_filter.py, test_design_rule_disk_cache.py; the three
"compiling logs nothing below a warning" tests from this file, test_robustness_compiled_replay.py and
test_simulation_compiled_controller.py are one test here, run per module in a fresh interpreter.

1. The two filters, compiled (speed-up items 3 and 6; the PI, 2026-09-25: "add numba and do option
   1"; DRNUMBA, `artifacts/research_2026-09-25_options/06_remaining_speed_ups.md` proposal 6): the
   two-component filter (L4) and the plain local level (L1, `filter_1state`). The numpy loop does
   about 30 small array operations per time step over 349 stretches x 1,499 steps on RCS08, and the
   fit calls it about 1,600 times: 29 ms a call, the time spent in dispatch rather than arithmetic.
   The compiled loop mirrors every operation in the same order, sums each step's terms in numpy's
   own pairwise order, and takes the log from the same library; held equal on constructed panels
   with gaps, short and long stretches and a missing first reading, over many parameter draws, and
   the whole fit equal too.
2. The padding-skipping filter (2026-10-02, the PI: faster requests on the Jetstream2 BRAVO, every
   number unchanged). The panel holds every stretch as one row, padded with missing readings to the
   longest: on RCS08 366 rows x 1,499 steps = 548,634 cells, of which 42,684 hold a reading. After a
   stretch's last reading its terms are exact zeros, so the new loop stops visiting it there; the
   per-step sum still runs over the whole row in numpy's pairwise order. The facts about the panel
   no parameter changes are worked out once per fit. Held to the committed loop (decision 269) bit
   for bit, on row counts that hit every branch of the pairwise sum (under 8, exactly 8, up to 128,
   over 128).
3. The disk cache (the PI, 2026-10-02: "fix that problem where the design rule shouldn't call
   itself"). Decision 269 kept the filters out of numba's disk cache because the per-step sum
   (`_pairwise_sum`) called itself, and a cached function that calls itself crashed the process when
   loaded under the server's libraries (segmentation fault, 2026-09-25); every web worker compiled
   the filters again (2.3 s on the Jetstream2 BRAVO). The sum now walks numpy's pairwise tree with
   an explicit stack. Held: no compiled loop calls itself; the sum equals `np.sum` and the old
   recursive sum bit for bit, above and below the 128-number block; every compiled loop is cached
   on disk, and a second process loads the filters from it with identical answers.
"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("numba")

from ClosedLoopDeployment import design_rule as DR

MODULES_ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------------------------------------
# 1. the compiled filters against the numpy filters
# ------------------------------------------------------------------------------------------------
def _panel(seed, s=60, l=300):
    rng = np.random.default_rng(seed)
    Y = np.full((s, l), np.nan)
    for i in range(s):
        n = int(rng.choice([3, 7, 12, 40, l]))
        y = 100 + np.cumsum(rng.normal(0, 3, n)) + rng.normal(0, 5, n)
        Y[i, :n] = y
        gaps = rng.random(n) < 0.15
        Y[i, :n][gaps] = np.nan
    Y[0, 0] = np.nan                                           # a stretch whose first reading is missing
    return Y


def _draw_2comp(rng, sc):
    return dict(phi_s=rng.uniform(0.3, 0.999), phi_f=rng.uniform(0.0, 0.95),
                q_s=rng.uniform(0.01, 3) * sc["var_rob"], q_f=rng.uniform(0.01, 3) * sc["var_rob"],
                m=sc["mbar"] + rng.normal(0, 3), r0=rng.uniform(0.05, 3) * sc["var_rob"])


def _draw_1state(rng, sc):
    return dict(phi=1.0, q=rng.uniform(0.001, 3) * sc["var_rob"],
                r0=rng.uniform(0.05, 3) * sc["var_rob"], m=sc["mbar"] + rng.normal(0, 3))


def _draw_1state_any_phi(rng, sc):
    """`fit_local_level` always fits ``phi=1.0``, but the filter itself takes an arbitrary phi;
    checked so the compiled kernel is not proved only at the one value the fit happens to use."""
    return dict(phi=rng.uniform(0.2, 1.0), q=rng.uniform(0.001, 3) * sc["var_rob"],
                r0=rng.uniform(0.05, 3) * sc["var_rob"], m=sc["mbar"] + rng.normal(0, 3))


# (numpy loop, compiled entry point, parameter draw, panel seeds, generator seed, draws per panel)
_FILTERS = {
    "two_component": ("_filter_2comp_numpy", "filter_2comp", _draw_2comp, range(4), 100, 40),
    "local_level": ("_filter_1state_numpy", "filter_1state", _draw_1state, range(4), 200, 40),
    "local_level_any_phi": ("_filter_1state_numpy", "filter_1state", _draw_1state_any_phi, (9,), 321, 20),
}


@pytest.mark.parametrize("which", list(_FILTERS))
def test_the_compiled_filter_returns_exactly_the_numpy_filters_answer(which):
    numpy_name, compiled_name, draw, seeds, rng_seed, n_draws = _FILTERS[which]
    assert DR.COMPILED_FILTER, "numba is installed, so the compiled loop must be the one used"
    for seed in seeds:
        Y = _panel(seed)
        sc = DR._scales(Y)
        rng = np.random.default_rng(rng_seed + seed if len(seeds) > 1 else rng_seed)
        for _ in range(n_draws):
            kw = draw(rng, sc)
            a = getattr(DR, numpy_name)(Y, **kw)
            b = getattr(DR, compiled_name)(Y, **kw)
            assert (a["loglik"] == b["loglik"] or (np.isnan(a["loglik"]) and np.isnan(b["loglik"]))) and a["n"] == b["n"], (kw, a, b)


@pytest.mark.parametrize("fit,seed,maxfev", [("fit_two_component", 7, 300), ("fit_local_level", 11, 200)])
def test_the_whole_fit_is_the_same_with_the_compiled_filter(fit, seed, maxfev):
    Y = _panel(seed, s=30, l=120)
    fast = getattr(DR, fit)(Y, maxfev=maxfev, restarts=1)
    saved = DR.COMPILED_FILTER
    try:
        DR.COMPILED_FILTER = False
        slow = getattr(DR, fit)(Y, maxfev=maxfev, restarts=1)
    finally:
        DR.COMPILED_FILTER = saved
    assert repr(fast) == repr(slow)


@pytest.mark.parametrize("module", ["design_rule", "simulation", "robustness"])
def test_compiling_a_loop_logs_nothing_below_a_warning(module):
    """numba logs its own type checking at DEBUG (38,760 lines on the first fit, 2026-09-25), and the
    server logs at DEBUG, so every worker's first fit flooded its log. Each module with a compiled
    loop quiets numba itself: checked in a fresh interpreter that imports that module alone, with
    the root logger at DEBUG as the server sets it. (`robustness` imports `simulation`, so its case
    cannot tell which of the two set the level.)"""
    code = ("import logging, sys\n"
            "sys.path.insert(0, %r)\n"
            "logging.getLogger().setLevel(logging.DEBUG)\n"
            "import ClosedLoopDeployment.%s\n"
            "print(logging.getLogger('numba').getEffectiveLevel())\n") % (str(MODULES_ROOT), module)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300,
                         cwd=str(MODULES_ROOT))
    assert out.returncode == 0, out.stderr[-3000:]
    assert int(out.stdout.strip().splitlines()[-1]) >= logging.WARNING


# ------------------------------------------------------------------------------------------------
# 2. the padding-skipping two-component filter against the committed loop
# ------------------------------------------------------------------------------------------------
def _bit_same(a, b):
    """Bit-identical, or both not-a-number."""
    if np.isnan(a) and np.isnan(b):
        return True
    return np.float64(a).tobytes() == np.float64(b).tobytes()


def _padded_panel(seed, s, l):
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
        Y = _padded_panel(k, s, l)
        prep = DR._prepare_2comp_panel(Y)
        for kw in _draws(Y, 500 + k, 25):
            ll0, n0 = _committed(Y, kw)
            once = DR._filter_2comp_prepared(prep, **kw)          # the fit's path: prepared once
            each = DR.filter_2comp(Y, **kw)                       # the public path: prepared per call
            assert _bit_same(once["loglik"], ll0) and once["n"] == n0, ((s, l), kw, once, ll0, n0)
            assert _bit_same(each["loglik"], ll0) and each["n"] == n0, ((s, l), kw, each, ll0, n0)


def test_the_prepared_panel_lists_each_stretchs_end_correctly():
    for k, (s, l) in enumerate(_SHAPES):
        Y = _padded_panel(100 + k, s, l)
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
    Y = _padded_panel(7, 60, 150)
    new = DR.fit_two_component(Y, maxfev=300, restarts=1)
    monkeypatch.setattr(DR, "_two_component_runner",
                        lambda Y_: (lambda **kw: dict(zip(("loglik", "n"), _committed(Y_, kw)))))
    old = DR.fit_two_component(Y, maxfev=300, restarts=1)
    assert repr(new) == repr(old)


def test_one_fit_prepares_its_panel_once(monkeypatch):
    calls = []
    real = DR._prepare_2comp_panel
    monkeypatch.setattr(DR, "_prepare_2comp_panel", lambda Y_: calls.append(1) or real(Y_))
    DR.fit_two_component(_padded_panel(3, 20, 60), maxfev=120, restarts=2)
    assert len(calls) == 1


# ------------------------------------------------------------------------------------------------
# 3. the per-step sum, and the disk cache
# ------------------------------------------------------------------------------------------------
KERNELS = ("_pairwise_sum", "_filter_2comp_kernel", "_filter_2comp_active_kernel",
           "_filter_1state_kernel")


def _old_recursive_pairwise_sum(a, lo, n):
    """The sum as it stood before 2026-10-02, in plain Python: the reference for bit equality."""
    if n < 8:
        res = 0.0
        for i in range(n):
            res += a[lo + i]
        return res
    elif n <= 128:
        r = [a[lo + k] for k in range(8)]
        i = 8
        while i < n - (n % 8):
            for k in range(8):
                r[k] += a[lo + i + k]
            i += 8
        res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
        while i < n:
            res += a[lo + i]
            i += 1
        return res
    n2 = n // 2
    n2 -= n2 % 8
    return _old_recursive_pairwise_sum(a, lo, n2) + _old_recursive_pairwise_sum(a, lo + n2, n - n2)


def test_no_compiled_loop_in_the_design_rule_calls_itself():
    calls_itself = [name for name in KERNELS
                    if name in getattr(DR, name).py_func.__code__.co_names]
    assert calls_itself == []


LENGTHS = (0, 1, 7, 8, 9, 15, 16, 127, 128, 129, 135, 136, 137, 255, 256, 257, 349, 366, 511, 1000,
           1023, 1024, 1025, 1499, 4099, 8192)


def test_the_sum_is_numpys_and_the_old_sums_bit_for_bit_at_every_length():
    rng = np.random.default_rng(20261002)
    differing = []
    for n in LENGTHS:
        for trial in range(6):
            a = rng.normal(0.0, 1.0, n + 40) * 10.0 ** rng.integers(-6, 7, n + 40)
            lo = int(rng.integers(0, 40))
            got = DR._pairwise_sum(a, lo, n)
            want_numpy = float(np.sum(np.ascontiguousarray(a[lo:lo + n])))
            want_old = _old_recursive_pairwise_sum(a, lo, n)
            if not (got == want_numpy == want_old):
                differing.append((n, trial, got, want_numpy, want_old))
    assert differing == []


def test_the_sum_matches_the_old_sum_far_above_numpys_buffer():
    # Past 8,192 numbers numpy may sum in buffered pieces, so the old recursive sum is the reference.
    rng = np.random.default_rng(7)
    for n in (8193, 20011, 65536):
        a = rng.normal(0.0, 1.0, n)
        assert DR._pairwise_sum(a, 0, n) == _old_recursive_pairwise_sum(a, 0, n), n


def test_every_compiled_loop_in_the_design_rule_is_cached_on_disk():
    not_cached = [name for name in KERNELS
                  if type(getattr(DR, name)._cache).__name__ == "NullCache"]
    assert not_cached == []


CACHED_RUN = r"""
import hashlib, json, sys
import numpy as np
sys.path.insert(0, %r)
from ClosedLoopDeployment import design_rule as DR
rng = np.random.default_rng(366)
s, l = 366, 400                                   # more stretches than one 128-number block
Y = np.full((s, l), np.nan)
for i in range(s):
    n = int(rng.integers(3, l))
    Y[i, :n] = 100 + np.cumsum(rng.normal(0, 3, n)) + rng.normal(0, 5, n)
    gaps = rng.random(n) < 0.15
    gaps[0] = False                                # a first reading, so the answer is a number
    Y[i, :n][gaps] = np.nan
kw2 = dict(phi_s=0.97, phi_f=0.4, q_s=0.8, q_f=3.0, m=100.0, r0=20.0)
kw1 = dict(phi=0.99, m=100.0, q=1.2, r0=20.0)
out = {"two": DR.filter_2comp(Y, **kw2), "one": DR.filter_1state(Y, **kw1)}
DR.COMPILED_FILTER = False
ref = {"two": DR.filter_2comp(Y, **kw2), "one": DR.filter_1state(Y, **kw1)}
# The two loops the filters call; the sum is compiled into each of them, not loaded on its own.
st = {k: getattr(DR, k).stats for k in ("_filter_2comp_active_kernel", "_filter_1state_kernel")}
print(json.dumps({"out": {k: [float(v["loglik"]).hex(), v["n"]] for k, v in out.items()},
                  "ref": {k: [float(v["loglik"]).hex(), v["n"]] for k, v in ref.items()},
                  "hits": {k: sum(v.cache_hits.values()) for k, v in st.items()},
                  "misses": {k: sum(v.cache_misses.values()) for k, v in st.items()}}))
""" % (str(MODULES_ROOT),)


def _run(code, cache_dir):
    env = dict(os.environ, NUMBA_CACHE_DIR=str(cache_dir))
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         timeout=300, cwd=str(MODULES_ROOT))
    assert out.returncode == 0, (out.returncode, out.stdout[-3000:], out.stderr[-3000:])
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_a_second_process_loads_the_filters_from_the_disk_cache_with_identical_answers(tmp_path):
    first = _run(CACHED_RUN, tmp_path)
    second = _run(CACHED_RUN, tmp_path)
    assert all(v >= 1 for v in first["misses"].values()), first          # compiled and saved
    assert all(v == 0 for v in second["misses"].values()), second        # loaded, not compiled
    assert all(v >= 1 for v in second["hits"].values()), second
    assert second["out"] == first["out"] == first["ref"]
    assert "nan" not in json.dumps(first["out"])
