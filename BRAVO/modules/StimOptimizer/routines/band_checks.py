"""The readiness screen's band checks, run in worker processes (2026-10-02, the PI: use the
Jetstream2 BRAVO's 64 cores).

`lfp_evidence.screen_cells` asks its band check (`response_fn`, in the request
`lfp_response.assess_response`: two regression fits) once for every band of every cell. A
two-stage Stim Optimizer request on RCS08 makes 1,080 of these checks, one after another on one
core. Each check depends only on its own band's power and on its cell's currents, visit labels and
repeat units, so whole cells are handed to joblib's reusable worker processes in chunks and the
results are put back in the cells' original order; the rest of the screen then runs in the calling
process, exactly as before. Whole cells, because a cell's eighteen checks share one regression
design, built once per process (`lfp_response._ols_fit`). Each worker runs its linear-algebra
libraries at the calling process's thread counts (one each, in a request), so every number is the
one the calling process would have produced (tests/test_screen_band_checks_parallel.py).

`STIM_OPTIMIZER_SCREEN_JOBS` sets the worker count; "1" (or "0") runs every check in the calling
process, as before. Unset, it is the held-out folds' count (`surrogate._loo_n_jobs`): joblib keeps
ONE pool of worker processes and shuts it down and starts a new one whenever a different count is
asked for, and the folds run in the same request. A screen of fewer than
`MIN_CHECKS_FOR_WORKERS` checks (about a second of work) runs in the calling process, since handing
it out would cost more than it saves. Where no process pool can start (a sandbox without POSIX
semaphores, a daemon process), the checks run in the calling process and the answer is the same.

This lives in its own file because `lfp_evidence` may hold no new plain number
(`tests/test_lfp_evidence.py::test_no_new_scale_constant_exists_in_either_file`).
"""
from __future__ import annotations

import contextlib
import logging
import os

import numpy as np

_log = logging.getLogger(__name__)

JOBS_ENV = "STIM_OPTIMIZER_SCREEN_JOBS"
MIN_CHECKS_FOR_WORKERS = 100


def n_jobs() -> int:
    """How many worker processes the band checks run in (1: all in the calling process)."""
    raw = os.environ.get(JOBS_ENV, "").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        from . import surrogate as _SUR
        return _SUR._loo_n_jobs()


def _blas_threads_now() -> dict:
    """The calling process's linear-algebra libraries, each with the thread count it runs at."""
    try:
        from threadpoolctl import threadpool_info
        return {d["filepath"]: int(d["num_threads"]) for d in threadpool_info()
                if d.get("user_api") == "blas"}
    except Exception:                                 # noqa: BLE001 -- no threadpoolctl: as it is
        return {}


@contextlib.contextmanager
def _blas_threads_as(threads):
    """Each linear-algebra library named in `threads` held at its count for the duration."""
    with contextlib.ExitStack() as stack:
        if threads:
            try:
                from threadpoolctl import ThreadpoolController
                ctl = ThreadpoolController()
                for path, n in threads.items():
                    lib = ctl.select(filepath=path)
                    if lib.lib_controllers:
                        stack.enter_context(lib.limit(limits=n))
            except Exception as exc:                  # noqa: BLE001 -- reported in the log only
                _log.warning("band checks: linear-algebra thread count not set (%r)", exc)
        yield


def _check_cells(response_fn, cells, blas_threads=None):
    """One chunk of cells, each ``(amplitude, era, cluster, [(centre, power), ...])``: every
    band's check, in order. Runs in a worker process, or in the calling process."""
    with _blas_threads_as(blas_threads):
        return [[response_fn(power, amp, era=era, cluster=cluster) for _c, power in bands]
                for amp, era, cluster, bands in cells]


def check_all(evidence, response_fn):
    """``{cell key: {band centre: response_fn result}}`` for every cell of ``evidence``, in its
    order: in worker processes when the screen is large enough, else in the calling process."""
    keys = list((evidence or {}).keys())
    cells = []
    for key in keys:
        ev = evidence[key]
        cells.append((ev.amplitude_mA, ev.era, ev.cluster,
                      [(float(c), ev.power_for(c, w)) for (c, w) in ev.band_power.keys()]))
    n_checks = sum(len(cell[3]) for cell in cells)
    k = n_jobs()
    out = None
    if k > 1 and len(cells) > 1 and n_checks >= MIN_CHECKS_FOR_WORKERS:
        n_chunks = min(len(cells), 4 * k)
        bounds = np.linspace(0, len(cells), n_chunks + 1).astype(int)
        threads = _blas_threads_now()
        try:
            import joblib
            # n_jobs is the pool's count however few chunks there are, and nothing else is passed:
            # any other count or argument makes joblib replace the pool the folds are using.
            parts = joblib.Parallel(n_jobs=k, backend="loky")(
                joblib.delayed(_check_cells)(response_fn, cells[bounds[i]:bounds[i + 1]], threads)
                for i in range(n_chunks))
            out = [r for part in parts for r in part]
        except Exception as exc:                      # noqa: BLE001 -- no pool: run them here
            _log.warning("band checks run one at a time: the worker processes failed (%s: %s)",
                         type(exc).__name__, exc)
    if out is None:
        out = _check_cells(response_fn, cells)
    return {key: {c: r for (c, _p), r in zip(cell[3], results)}
            for key, cell, results in zip(keys, cells, out)}
