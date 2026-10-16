"""The band's mixed model carries its exact rotation test beside its own p (decision 477; the PI,
2026-10-16: "show both"). Needs R (lme4): runs in the container suite.

Run:  python3 modules/Biomarkers/tests/test_band_rotation_in_model.py   (in the container)
"""
import inspect
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import analytics as A
    from modules.Biomarkers.routines import mixed_model_shuffle as M
except ImportError:                                            # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A
    from Biomarkers.routines import mixed_model_shuffle as M


def _frame(seed=0, n_weeks=12, per_week=6):
    rng = np.random.default_rng(seed)
    cl = np.repeat(np.arange(n_weeks), per_week)
    b = rng.normal(0, 0.7, n_weeks)
    y = (rng.random(len(cl)) < 1 / (1 + np.exp(-b[cl]))).astype(int)
    x = rng.normal(size=len(cl))
    t = np.arange(len(cl)) * 3600.0 + cl * 7 * 86400.0
    return pd.DataFrame({"pain_high": y, "band_power": x, "cluster": cl}), t


def test_every_rotation_once_and_the_same_p_as_the_module():
    df, t = _frame()
    out = A._band_rotation_test(df, t)
    assert out["available"] is True, out
    n = len(df)
    assert out["n_orders"] == n and abs(out["p_floor"] - 1 / n) < 1e-12
    null, ok, _ = M.null_fit_lme4(df.pain_high.to_numpy(float), df.cluster.to_numpy())
    assert ok and out["p"] == M.shuffle_test(null, df.band_power.to_numpy(float), order=t)["p"]


def test_reported_not_raised_when_it_cannot_run():
    df, t = _frame()
    one_week = df.assign(cluster=0)
    assert A._band_rotation_test(one_week, t)["available"] is False
    t_bad = t.copy(); t_bad[3] = np.nan
    assert "no time" in A._band_rotation_test(df, t_bad)["reason"]


def test_every_fitted_answer_carries_it_and_the_verdict_does_not_read_it():
    src = inspect.getsource(A.band_mixedmodel_inference)
    assert src.count('"rotation": rotation') == 3                # separated, not converged, fitted
    import ast
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bravo_service.py")
    src_bs = open(path).read()
    fn = next(n for n in ast.walk(ast.parse(src_bs))
              if isinstance(n, ast.FunctionDef) and n.name == "_band_decide_verdict")
    assert "rotation" not in ast.get_source_segment(src_bs, fn)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                            # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc))
    sys.exit(1 if fails else 0)
