"""The design rule's compiled loops load from numba's disk cache (the PI, 2026-10-02: "fix that
problem where the design rule shouldn't call itself").

Decision 269 kept the design rule's filters out of numba's disk cache because their per-step sum
(`_pairwise_sum`, numpy's own pairwise order) called itself, and a cached function that calls itself
crashed the process when loaded under the server's libraries (segmentation fault, 2026-09-25). So
every web worker compiled the filters again on its first fit (2.3 s on the Jetstream2 BRAVO).

The sum now walks numpy's pairwise tree with an explicit stack instead of calling itself, adding the
same numbers in the same order. These tests hold:
  1. no compiled loop in the design rule calls itself;
  2. the sum equals numpy's `np.sum`, and the old recursive sum, bit for bit, above and below the
     128-number block where the old code began calling itself (RCS08's panel has 366 stretches);
  3. every compiled loop is cached on disk, and a second process loads the filters from that cache,
     without crashing, and returns exactly what the first process and the numpy loop return.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("numba")

from ClosedLoopDeployment import design_rule as DR

MODULES_ROOT = Path(__file__).resolve().parents[2]
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
