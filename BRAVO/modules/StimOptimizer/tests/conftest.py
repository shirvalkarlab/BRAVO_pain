"""Put BRAVO/modules on sys.path so `StimOptimizer` imports the same way it does in-container.

Also the one shared Stage 1 fit (2026-09-12, the PI's "fit once, assert many").

`shared_stage1` is an opt-in fixture: a test that requests it gets `stage1_openloop.run_stage1`
replaced, for that test only, by a wrapper that remembers every fit it has made IN THIS TEST MODULE
and hands the same result object back to any later call with the same design matrix and the same
arguments. A call with a different matrix or a different argument is fitted for real. The point is
the fits that sit inside `pipeline.run_two_stage` and inside the service path, which no caller can
hand a precomputed Stage 1 to: `test_stage2.py` and `test_two_stage_wiring.py` each fitted the same
hand-built table five or six times over, at 3 to 9 s a fit, to assert different things about the
gate and Stage 2 that sit AFTER the fit.

Every fit is compared on the matrix VALUES (`DataFrame.equals`) and on every keyword argument, so
two tests get one result only when they asked for exactly the same fit. A test that must fit twice
and compare the two fits with each other simply does not request this fixture.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MODULES_DIR = Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))


def _same_value(a, b):
    """Equality that is safe for the argument kinds Stage 1 takes: frames, arrays, tuples, dicts,
    scalars. Anything that cannot be compared with confidence counts as different, so the cost of a
    doubt is one extra fit, never a wrong answer."""
    try:
        if isinstance(a, pd.DataFrame) or isinstance(b, pd.DataFrame):
            return isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame) and a.equals(b)
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            return np.array_equal(np.asarray(a), np.asarray(b))
        if isinstance(a, dict) and isinstance(b, dict):
            return set(a) == set(b) and all(_same_value(a[k], b[k]) for k in a)
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return len(a) == len(b) and all(_same_value(x, y) for x, y in zip(a, b))
        if a is None or b is None:
            return a is b
        return bool(a == b)
    except Exception:
        return False


@pytest.fixture(scope="module")
def _stage1_fit_cache():
    """One list per test module: (design, args, kwargs, result) for every real fit made."""
    return []


@pytest.fixture
def shared_stage1(monkeypatch, _stage1_fit_cache):
    """Hand the same Stage 1 result to every call in this module with the same inputs."""
    from StimOptimizer import stage1_openloop as S1
    real = S1.run_stage1

    def remembered(design, *args, **kwargs):
        for entry in _stage1_fit_cache:
            if (_same_value(entry["design"], design) and _same_value(entry["args"], args)
                    and _same_value(entry["kwargs"], kwargs)):
                return entry["result"]
        key_design = design.copy() if isinstance(design, pd.DataFrame) else design
        result = real(design, *args, **kwargs)
        _stage1_fit_cache.append(dict(design=key_design, args=args, kwargs=dict(kwargs),
                                      result=result))
        return result

    monkeypatch.setattr(S1, "run_stage1", remembered)
    return _stage1_fit_cache
