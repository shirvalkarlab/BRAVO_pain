"""Synthetic calibration algorithm and source-contract checks.

Empirical participant acceptance evidence is kept outside Git and is never inferred
from these tests. Private parity checks require an explicitly provisioned evidence set.
"""
import ast
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics as A
from Biomarkers.routines import calibration as C

def test_the_recipe_takes_no_logarithm_and_uses_the_platforms_one_outlier_rule():
    src = open(C.__file__).read()
    tree = ast.parse(src)
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("log10", "log", "log2", "exp", "power")]
    assert hits == [], hits
    assert "mad_outlier_flags" in src, "the recipe must call stats_utils.mad_outlier_flags, not its own rule"
    # the median fold error is a ratio statistic and is computed as one: max(pred/obs, obs/pred)
    assert "np.maximum" in src


def test_the_frozen_june_model_is_gone():
    import importlib
    import os
    root = os.path.join(os.path.dirname(__file__), "..")
    assert not os.path.exists(os.path.join(root, "routines", "psd_lsb" + "_model.py"))
    assert not os.path.exists(os.path.join(root, "data", "psd_lsb" + "_models"))
    assert not os.path.exists(os.path.join(root, "tests", "test_psd_lsb" + "_model.py"))
    try:
        importlib.import_module("Biomarkers.routines.psd_lsb" + "_model")
    except ImportError:
        pass
    else:
        raise AssertionError("the frozen model module still imports")
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".py"):
                src = open(os.path.join(dirpath, f)).read()
                assert ("psd_lsb" + "_model") not in src, os.path.join(dirpath, f)


def test_the_committed_band_refit_and_its_log_log_fit_are_gone():
    import os as _os
    assert not hasattr(A, "psd_lsb_conversion")
    root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    svc = open(_os.path.join(root, "Biomarkers", "bravo_service.py")).read()
    assert "def band_psd_lsb_conversion" not in svc
    urls = open(_os.path.join(_os.path.dirname(root), "Server", "APIs", "urls.py")).read()
    assert "'queryPsdLsbConversion'" not in urls


def test_the_recipe_reports_a_raw_interval_a_raw_scatter_band_and_a_raw_proportionality_check():
    rng = np.random.default_rng(3)
    P = rng.gamma(2.0, 0.5, 120)
    L = 300.0 * P * (1.0 + 0.05 * rng.standard_normal(120))
    rows = [dict(existing_uv2=float(p), target_lsb_all=float(l), n_td_samples=2500.0, sample_rate_hz=250.0,
                 n_lfp_points_all=10.0, n_lfp_points_off=10.0) for p, l in zip(P, L)]
    fit = C.transform_k(rows, target="all")
    lo, hi = fit["k_interval"]
    assert lo < 300.0 < hi and hi - lo < 30.0, fit["k_interval"]
    assert fit["k_interval_method"].startswith("bootstrap")
    assert 0.0 < fit["scatter_mad"] < 0.10 * fit["k"]              # 1 MAD of the raw ratio, in LSB per uV^2
    assert 0.0 < fit["scatter_mad_frac"] < 0.10
    pr = fit["proportionality"]
    assert set(pr) >= {"spearman_rho", "p", "n", "holds", "sentence"}
    assert abs(pr["spearman_rho"]) < 0.25 and pr["p"] > 0.01 and pr["holds"] is True
    assert "does not change with the power level" in pr["sentence"]
    bent = [dict(r, target_lsb_all=float(300.0 * np.sqrt(r["existing_uv2"]))) for r in rows]
    fb = C.transform_k(bent, target="all")
    assert fb["proportionality"]["holds"] is False and fb["proportionality"]["p"] < 1e-6
    assert "changes with the power level" in fb["proportionality"]["sentence"]
    # too few blocks: the fields exist and say so, nothing raises
    few = C.transform_k(rows[:2], target="all")
    assert few["k_interval"] is None and few["proportionality"] is None


