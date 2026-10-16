"""Code the PI had deleted stays deleted, and what it shared with live callers stays. These guards
read the modules' syntax trees or source rather than importing them where they can, so they run on
both runners and cannot be satisfied by a stub.

- The old time-domain branch's 1,000-shuffle band inference (`_band_inference`, the PI, 2026-09-27,
  open item N-12): read by no page, 34-37% of Recompute. `fisher_z_ci` had exactly one caller (it)
  and went with it. Kept, because pages read them: `report_sharing_for_summary` (the on-screen
  `ReportSharingNote.js`), `select_biomarker_band` and the plain `band` tuple (`BiomarkerTimeline.js`
  reads `band[4]`); `_autocorr_adjusted_pgrid` is shared with live callers.
- The aperiodic (1/f) fit, `remove_aperiodic` (decision 206): its only caller was the pain
  correlation's `transform="fooof"`, which only the unused command-line runner could select; log
  power enters no calculation (decision 202), and the device thresholds raw band power.
- The chronic-detector analytics in `_compute_analytics` (decision 187, 2026-09-16): 89,085 response
  fields on RCS08 read by no panel since decision 174; the four zero-caller routines deleted on
  2026-09-21. The timeline's Power lane comes from `pipeline.run_powerdomain_branch`, untouched.
- The sweep's two figure-headline builders (decisions 145, 170, 174; deleted 2026-09-15), and with
  them the last runtime wording that called the sweep's choice "best-of-ten" (it tries nine lengths).
- Review B10 (2026-09-12): no function in `bravo_service` imports a sibling by the bare
  container-only spelling `from modules.Biomarkers...`.

Merged here 2026-10-05: test_band_inference_shuffle_deleted.py, test_no_aperiodic_fit.py,
test_no_chronic_detector_analytics.py, test_no_dead_sweep_headline_builders.py, test_import_spelling.py.
"""
import ast
import inspect
import os
import pathlib
import re
import sys

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.Biomarkers.routines import streaming_psd       # noqa: E402
from modules.Biomarkers import pipeline                     # noqa: E402
from modules.Biomarkers import bravo_service as B           # noqa: E402

_HERE = os.path.dirname(__file__)
_PIPELINE_SRC = os.path.join(_HERE, "..", "pipeline.py")
_STATS_SRC = os.path.join(_HERE, "..", "routines", "stats_utils.py")
_SERVICE_SRC = os.path.join(_HERE, "..", "bravo_service.py")
_ANALYTICS_SRC = pathlib.Path(_HERE).resolve().parent / "routines" / "analytics.py"


def _function_names(path):
    tree = ast.parse(open(path).read())
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


def _function_source(path, name):
    src = open(path).read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{name} not found")


# ---- the 1,000-shuffle band inference ----------------------------------------------------------

def test_the_shuffle_inference_and_fisher_z_ci_are_gone_and_the_helpers_kept_callers_need_stay():
    names = _function_names(_PIPELINE_SRC)
    for gone in ("_band_inference", "_block_perm_maxcorr_pvalue"):
        assert gone not in names, f"{gone} is still defined"
    assert "fisher_z_ci" not in _function_names(_STATS_SRC), \
        "fisher_z_ci is still defined but had exactly one caller"
    for kept in ("select_biomarker_band", "_autocorr_adjusted_pgrid", "run_timedomain_branch",
                 "report_sharing_for_summary"):
        assert kept in names, f"{kept} was deleted but something else still calls it"


def test_run_timedomain_branch_no_longer_calls_the_deleted_function():
    body = _function_source(_PIPELINE_SRC, "run_timedomain_branch")
    assert "_band_inference(" not in body
    # the band tuple and the sharing note are exactly what the fallback timeline and the
    # on-screen note still read -- both must still be built
    assert '"band": band' in body
    assert "report_sharing_for_summary(session_df)" in body


# ---- the aperiodic (1/f) fit -------------------------------------------------------------------

def test_the_aperiodic_fit_and_the_fooof_choice_no_longer_exist():
    assert not hasattr(streaming_psd, "remove_aperiodic")
    src_path = pathlib.Path(streaming_psd.__file__)
    tree = ast.parse(src_path.read_text())
    names = sorted(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                   and "aperiodic" in n.name.lower())
    assert names == [], names
    src = src_path.read_text()
    assert "specparam" not in src and 'transform == "fooof"' not in src   # history may name it
    assert "fooof" not in pathlib.Path(pipeline.__file__).read_text().lower(), \
        "pipeline.py (the command-line runner) still names the fooof transform"


def test_the_pain_correlation_refuses_the_fooof_transform():
    from modules.Biomarkers import adapter
    fs = 250.0
    recs = []
    for k in range(5):
        rng = np.random.default_rng(k)
        n = int(8 * fs)
        t = np.arange(n) / fs
        data = np.column_stack([np.sin(2 * np.pi * 20 * t) + 0.3 * rng.standard_normal(n),
                                np.sin(2 * np.pi * 30 * t) + 0.3 * rng.standard_normal(n)])
        recs.append({"SamplingRate": fs, "ChannelNames": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"],
                     "Data": data, "Missing": np.zeros_like(data),
                     "StartTime": 1_700_000_000.0 + 600.0 * k, "Duration": n / fs})
    streams = adapter.bravo_timedomain_recordings_to_streams(recs)
    try:
        streaming_psd.compute_psd_pain_correlation(
            streams, np.array([2.0, 4.0, 6.0, 8.0, 9.0]), ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"],
            transform="fooof")
    except ValueError:
        return
    raise AssertionError("transform='fooof' was accepted")


# ---- the chronic-detector analytics ------------------------------------------------------------

def test_compute_analytics_no_longer_builds_a_powerdomain_block():
    body = _function_source(_SERVICE_SRC, "_compute_analytics")
    code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    assert 'result["powerdomain"]' not in code, "the chronic-detector analytics block is back"
    assert '"powerdomain": None' not in code, "the response still carries an empty analytics.powerdomain key"
    for name in ("sliding_window_analytics", "roc_analysis", "lfp_distribution",
                 "power_pain_scatter", "cluster_scatter", "pain_binarization"):
        assert not re.search(r"\b%s\s*\(" % name, code), f"{name} is called again inside _compute_analytics"


def test_the_four_zero_caller_routines_are_deleted_and_the_power_lane_keeps_its_source():
    """`sliding_window_analytics` and its only helper `_all_data_window`, `power_pain_scatter`,
    `cluster_scatter`, `pain_binarization` are gone; `roc_analysis` and `lfp_distribution` keep one
    caller each in the pipeline and stay; the timeline's Power lane still has its pipeline branch."""
    names = _function_names(_ANALYTICS_SRC)
    for gone in ("sliding_window_analytics", "_all_data_window", "power_pain_scatter",
                 "cluster_scatter", "pain_binarization"):
        assert gone not in names, f"{gone} is still defined"
    for kept in ("roc_analysis", "lfp_distribution"):
        assert kept in names, f"{kept} was deleted but the pipeline calls it"
    assert "run_powerdomain_branch" in open(_SERVICE_SRC).read()


# ---- the sweep's headline builders -------------------------------------------------------------

def _runtime_strings(tree):
    """Every string constant a running function could hand back: literals and f-string parts,
    with docstrings left out (a docstring may quote the retired wording as history)."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node.value


def test_the_sweep_headline_builders_are_gone_and_no_runtime_string_says_best_of_ten():
    tree = ast.parse(_ANALYTICS_SRC.read_text())
    names = sorted(n.name for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and "sweep_headline" in n.name)
    assert names == [], f"dead headline builders still defined: {names}"
    bad = sorted({s for s in _runtime_strings(tree)
                  if "best-of-ten" in s.lower() or "best of ten" in s.lower()})
    assert bad == [], f"runtime strings still say best-of-ten: {bad}"


# ---- import spelling ---------------------------------------------------------------------------

def test_no_bare_container_only_import_in_the_service():
    src = inspect.getsource(B)
    offenders = [ln.strip() for ln in src.splitlines()
                 if ln.strip().startswith("from modules.Biomarkers")]
    assert offenders == [], offenders
