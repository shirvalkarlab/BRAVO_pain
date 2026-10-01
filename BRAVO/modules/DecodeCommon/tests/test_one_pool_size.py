"""Every BRAVO worker pool asks for ONE size (2026-10-02, the Jetstream2 BRAVO): joblib keeps a
single process pool per web worker and shuts it down and rebuilds it whenever a call asks for a
different size, which cost 1.3-1.5 s per switch there (the Closed-Loop simulation asked for 64,
the Stim Optimizer's held-out folds and band checks for 15). The size is the core count less one
(BRAVO_POOL_JOBS overrides it); each use keeps its own variable to set it apart.

Values, not shapes: with no variable set, the three uses report the same number, and it is the
core count less one; the shared variable moves all three; a use's own variable moves only it.
"""
import os

try:
    from modules.DecodeCommon import parallel as P
    from modules.StimOptimizer.routines import surrogate as SUR, band_checks as BC
    from modules.ClosedLoopDeployment import simulation as SIM
except ImportError:                                              # the host runner's spelling
    from DecodeCommon import parallel as P
    from StimOptimizer.routines import surrogate as SUR, band_checks as BC
    from ClosedLoopDeployment import simulation as SIM

_VARS = (P.POOL_JOBS_ENV, SUR.LOO_JOBS_ENV, BC.JOBS_ENV, SIM.SEGMENT_JOBS_ENV)


def _with_env(env, fn):
    old = {k: os.environ.get(k) for k in _VARS}
    for k in _VARS:
        os.environ.pop(k, None)
    os.environ.update(env)
    try:
        return fn()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _three():
    return (SUR._loo_n_jobs(), BC.n_jobs(), SIM._segment_n_jobs())


def test_the_three_pools_default_to_one_size_the_cores_less_one():
    got = _with_env({}, _three)
    assert got == (P.pool_jobs(),) * 3 == (max(1, (os.cpu_count() or 2) - 1),) * 3


def test_the_shared_variable_moves_all_three_and_a_use_s_own_moves_only_it():
    assert _with_env({P.POOL_JOBS_ENV: "7"}, _three) == (7, 7, 7)
    assert _with_env({P.POOL_JOBS_ENV: "7", SIM.SEGMENT_JOBS_ENV: "1"}, _three) == (7, 7, 1)
