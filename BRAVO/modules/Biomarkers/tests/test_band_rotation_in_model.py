"""The band's mixed model carries its exact rotation test beside its own p (decision 477; the PI,
2026-10-16: "show both"), and since decision 482 the verdict reads the rotation p. Needs R (lme4):
runs in the container suite.

Run:  python3 modules/Biomarkers/tests/test_band_rotation_in_model.py   (in the container)
"""
import inspect
import os
import sys

import numpy as np
import pandas as pd
import pytest

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
    pytest.importorskip("pymer4", reason="Requires production pymer4/rpy2/R stack")
    pytest.importorskip("rpy2", reason="Requires production pymer4/rpy2/R stack")
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


def test_every_fitted_answer_carries_it():
    src = inspect.getsource(A.band_mixedmodel_inference)
    assert src.count('"rotation": rotation') == 3                # separated, not converged, fitted


# ---- THE VERDICT READS THE ROTATION p (decision 482; the PI, 2026-10-18: "do all", change 4) ----
# Preserve the model p as descriptive evidence; the verdict reads the rotation p.


def _bs():
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    for p in (_root, os.path.join(_root, "modules")):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    try:
        from modules.Biomarkers import bravo_service as bs
    except ImportError:                                        # pragma: no cover - host spelling
        from Biomarkers import bravo_service as bs
    return bs


def _fit(p, rotation):
    return {"available": True, "separation": False, "singular": False, "converged": True,
            "p": p, "rotation": rotation}


_STABLE = {"available": True, "stim_stable": True, "stability_verdict": "equivalent"}


def test_model_p_small_rotation_p_large_is_a_candidate():
    bs = _bs()
    assert bs.VERDICT_P_SOURCE == "rotation"
    v = bs._band_decide_verdict(_fit(0.01, {"available": True, "p": 0.2, "n_orders": 120}), _STABLE)
    assert v == "candidate (rotation test n.s.)", v


def test_model_p_large_rotation_p_small_is_validated():
    bs = _bs()
    v = bs._band_decide_verdict(_fit(0.2, {"available": True, "p": 0.01, "n_orders": 120}), _STABLE)
    assert v == "VALIDATED (stim-stable)", v


def test_a_missing_rotation_test_never_validates():
    bs = _bs()
    for rot in (None, {}, {"available": False, "reason": "every sample is in one week"},
                {"available": True, "p": None}, {"available": True, "p": float("nan")}):
        v = bs._band_decide_verdict(_fit(0.001, rot), _STABLE)
        assert v == "candidate (rotation test unavailable)", (rot, v)
        assert "VALIDATED" not in v


def test_the_fit_failures_still_come_first():
    bs = _bs()
    rot = {"available": True, "p": 0.001}
    assert bs._band_decide_verdict(dict(_fit(0.001, rot), separation=True), _STABLE) == "failed (separation)"
    assert bs._band_decide_verdict(dict(_fit(0.001, rot), converged=False), _STABLE) == "failed (did not converge)"


def test_the_neutral_setting_gives_the_old_answer():
    bs = _bs()
    keep = bs.VERDICT_P_SOURCE
    try:
        bs.VERDICT_P_SOURCE = "glmer"
        assert bs._band_decide_verdict(_fit(0.01, {"available": True, "p": 0.2}), _STABLE) == "VALIDATED (stim-stable)"
        assert bs._band_decide_verdict(_fit(0.2, {"available": True, "p": 0.01}), _STABLE) == "candidate (mixed-effects n.s.)"
        assert bs._band_decide_verdict(_fit(0.001, None), _STABLE) == "VALIDATED (stim-stable)"
    finally:
        bs.VERDICT_P_SOURCE = keep


def test_the_sign_off_gate_names_the_rotation_test():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bravo_service.py")
    src = open(path).read()
    # the gate's label names the p that decides; the model's name only under the neutral setting
    assert 'else "Band validated (rotation test)")' in src
    assert src.count('"Band validated (mixed-effects)"') == 1
    assert 'if VERDICT_P_SOURCE == "glmer"\n' in src.split('"Band validated (mixed-effects)"')[1][:40]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                            # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc))
    sys.exit(1 if fails else 0)
