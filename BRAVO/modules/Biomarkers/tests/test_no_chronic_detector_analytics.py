"""Decision 187 (2026-09-16): the leftover chronic-detector analytics are gone from the module compute.

`_compute_analytics` used to fill `analytics.powerdomain` -- ROC curve, threshold, sliding-window AUC,
scatter and cluster plots, a binarization block, per-contact copies, sensing-centre changes -- on every
Recompute, 89,085 response fields on RCS08, read by no panel since decision 174. The timeline's "Power"
lane and the one-line summary come from `pipeline.run_powerdomain_branch` and are untouched.

This test reads the source rather than importing the module, so it runs on both runners.
"""
import ast
import os
import re

_SRC = os.path.join(os.path.dirname(__file__), "..", "bravo_service.py")


def _compute_analytics_body():
    src = open(_SRC).read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_compute_analytics":
            return ast.get_source_segment(src, node)
    raise AssertionError("_compute_analytics not found")


def test_compute_analytics_no_longer_builds_a_powerdomain_block():
    body = _compute_analytics_body()
    code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    assert 'result["powerdomain"]' not in code, "the chronic-detector analytics block is back"
    assert '"powerdomain": None' not in code, "the response still carries an empty analytics.powerdomain key"
    for name in ("sliding_window_analytics", "roc_analysis", "lfp_distribution",
                 "power_pain_scatter", "cluster_scatter", "pain_binarization"):
        assert not re.search(r"\b%s\s*\(" % name, code), f"{name} is called again inside _compute_analytics"


def test_the_four_zero_caller_routines_are_deleted():
    """The PI, 2026-09-21: the chronic-detector routines with no caller are deleted. After decision
    187 four of the six had no production caller (`sliding_window_analytics` and its only helper
    `_all_data_window`, `power_pain_scatter`, `cluster_scatter`, `pain_binarization`); `roc_analysis`
    and `lfp_distribution` keep one caller each in the pipeline and stay."""
    asrc = open(os.path.join(os.path.dirname(__file__), "..", "routines", "analytics.py")).read()
    tree = ast.parse(asrc)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for gone in ("sliding_window_analytics", "_all_data_window", "power_pain_scatter",
                 "cluster_scatter", "pain_binarization"):
        assert gone not in names, f"{gone} is still defined"
    for kept in ("roc_analysis", "lfp_distribution"):
        assert kept in names, f"{kept} was deleted but the pipeline calls it"


def test_the_timeline_power_lane_still_has_its_own_source():
    """The deletion must not have taken the pipeline branch the timeline's Power lane reads."""
    src = open(_SRC).read()
    assert "run_powerdomain_branch" in src
