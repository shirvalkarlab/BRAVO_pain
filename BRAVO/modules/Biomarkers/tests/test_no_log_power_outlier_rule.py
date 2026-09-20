"""The outlier rule and the logistic cross-check run on raw power (decision 205).

The PI's rule of 2026-09-19 (decision 202): log power enters no calculation anywhere. His item 3
is the outlier rule. The 5-MAD threshold is unchanged (``stats_utils.MAD_N_DEFAULT``, his own
consolidation of 2026-08-30); what changes is the SCALE the rule is evaluated on. Until now four
places took ``log10`` of the power before measuring the deviation -- the scalar rule and its
keep-mask twin (``stats_utils``), the vectorised rule the heat-map sweep uses as its fallback
(``analytics.mad_outlier_columns``), and the chronic detector's per-recording filter
(``adapter._concat_chronic``) -- and the heat map's logistic cross-check fitted on log band power.
Now every rule sees the raw power, the ``"log"`` option is refused rather than mapped to raw, the
page-request parameter that could ask for it falls back to raw, and the sweep's rule version is
bumped so no stored grid built under the old fallback is served.
"""
import ast
import pathlib
import sys

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.Biomarkers import adapter
from modules.Biomarkers.routines import analytics as A
from modules.Biomarkers.routines import stats_utils as SU

_PKG = pathlib.Path(__file__).resolve().parents[1]


def _raises_value_error(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except ValueError:
        return True
    return False


def test_the_threshold_is_still_five_mad_everywhere():
    assert SU.MAD_N_DEFAULT == 5.0 and A.OUTLIER_N_MAD == 5.0


def test_the_scalar_rule_flags_on_raw_power_and_refuses_the_log_scale():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 1000.0])
    # median 6, MAD 3, window 15: the 1000 is out, nothing else is
    mask, info = SU.mad_outlier_flags(x)
    assert mask.tolist() == [False] * 10 + [True] and info["n_removed"] == 1 and info["scale"] == "raw"
    keep = SU.mad_keep_mask(x)
    assert keep.tolist() == [True] * 10 + [False]
    assert _raises_value_error(SU.mad_outlier_flags, x, scale="log")
    assert _raises_value_error(SU.mad_keep_mask, x, scale="log")


def test_the_vectorised_rule_flags_on_raw_power_and_refuses_the_log_scale():
    X = np.column_stack([np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 1000.0]),
                         np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 0.001])])
    got = A.mad_outlier_columns(X)
    assert got[:, 0].tolist() == [False] * 10 + [True]
    # 0.001 sits 59.999 below the median of 60 with MAD 30: inside 5 MAD on the raw scale, so kept
    assert not got[:, 1].any(), got[:, 1]
    assert _raises_value_error(A.mad_outlier_columns, X, scale="log")


def test_the_module_default_scale_is_raw():
    assert A.OUTLIER_SCALE == "raw"


def test_the_chronic_filter_runs_on_raw_power():
    """LFP power cycling 70, 85, 100, 115, 130 (median 100, MAD 15, window 75) with one 9,000 spike
    and one reading of 30. On the raw scale the spike is dropped and the 30 is kept (70 below the
    median, inside the window); the log-scale rule would have dropped the 30 as a low extreme."""
    from modules.Biomarkers.tests.test_adapter import _MIDNIGHT_UTC
    n = 40
    lfp = np.tile([70.0, 85.0, 100.0, 115.0, 130.0], n // 5)
    lfp[5] = 9000.0
    lfp[6] = 30.0
    rec = {"Time": _MIDNIGHT_UTC + np.arange(n) * 3600.0,
           "Data": np.column_stack([lfp, np.full(n, 2.0)]), "ChannelNames": ["L LFP", "L Amplitude"]}
    kept = adapter._concat_chronic([rec])["Data"][:, 0]
    assert 9000.0 not in set(kept) and 30.0 in set(kept), sorted(set(kept))
    assert kept.size == n - 1


def test_the_page_request_cannot_ask_for_the_log_scale():
    from modules.Biomarkers import bravo_service as bs
    assert bs._outlier_scale_param({"OutlierScale": "log"}) == "raw"
    assert bs._outlier_scale_param({"OutlierScale": "raw"}) == "raw"
    assert bs._outlier_scale_param({}) == "raw"


def test_the_logistic_cross_check_fits_on_raw_power_and_refuses_the_log_scale():
    rng = np.random.default_rng(3)
    X = rng.gamma(2.0, 50.0, size=(80, 3))
    y = (X[:, 0] + rng.normal(0, 30.0, 80) > np.median(X[:, 0])).astype(float)
    got = A.logistic_auc_columns_fitted(X, y)
    assert np.isfinite(got["auc"][0])
    assert _raises_value_error(A.logistic_auc_columns_fitted, X, y, feature_scale="log")
    rows = [{"_grid_time_index": 0, "_grid_center_index": 0, "auc": float(A.rank_auc_columns(X[:, :1], y)["auc"][0])}]
    cc = A.logistic_fit_crosscheck({1.0: X}, y, rows)
    assert cc["feature_scale"] == "raw", cc


def test_the_sweep_rule_version_moved_off_the_log_fallback():
    from modules.Biomarkers import bravo_service as bs
    assert bs._BAND_SWEEP_RULE_VERSION == "v21_outlier_rule_and_crosscheck_on_raw_power", \
        bs._BAND_SWEEP_RULE_VERSION


def _log_calls(fn_node):
    return [n.lineno for n in ast.walk(fn_node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("log10", "log2", "log")]


def test_no_outlier_or_cross_check_function_takes_a_logarithm():
    want = {"stats_utils.py": {"mad_outlier_flags", "mad_keep_mask"},
            "analytics.py": {"mad_outlier_columns", "apply_outlier_exclusion",
                             "logistic_auc_columns_fitted", "logistic_fit_crosscheck"}}
    bad = {}
    for fname, names in want.items():
        tree = ast.parse((_PKG / "routines" / fname).read_text())
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in names}
        assert set(fns) == names, (fname, names - set(fns))
        for k, v in fns.items():
            if _log_calls(v):
                bad[f"{fname}:{k}"] = _log_calls(v)
    assert bad == {}, bad
    src = (_PKG / "adapter.py").read_text()
    assert 'scale="log"' not in src, "the chronic filter still asks for the log scale"
