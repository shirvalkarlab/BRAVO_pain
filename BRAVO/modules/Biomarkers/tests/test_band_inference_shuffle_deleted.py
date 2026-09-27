"""The old time-domain branch's 1,000-shuffle band inference is deleted (the PI, 2026-09-27,
answering open item N-12: "see if ok to delete old one including shuffles").

Checked first, before deleting anything: `_band_inference` (the per-band Fisher-z CI, partial
correlation and the family-max block-permutation null, `n_perm=1000`) is computed on every
Compute for the time-domain branch, but nothing on any page reads any of its fields --
`perm_p`, `r_ci`, `stim_adjusted_r`, `outlier_sensitivity`, and the rest are all absent from
every Client/src file except this one's own tests. The consolidation audit timed a repeated
1,000-shuffle test at 34-37% of Recompute; this is that computation.

What is NOT deleted, because it IS read: `report_sharing_for_summary` (the "claimed by more than
one recording session" note `ReportSharingNote.js` shows on screen today) and `select_biomarker_band`
plus the plain `band` tuple (`BiomarkerTimeline.js` reads `band[4]`, the frequency, for its title --
the fallback timeline shown to a participant with no availability data yet). Those stay exactly as
they were; only the shuffle-test inference layered on top of the selected band is gone.
`_autocorr_adjusted_pgrid`, `partial_corr`, `effective_n` and `mad_outlier_mask` are shared with
`select_biomarker_band` and other live callers and are untouched. `fisher_z_ci` had exactly one
caller (`_band_inference`) and is deleted with it.
"""
import ast
import os

_PIPELINE_SRC = os.path.join(os.path.dirname(__file__), "..", "pipeline.py")
_STATS_SRC = os.path.join(os.path.dirname(__file__), "..", "routines", "stats_utils.py")


def _function_names(path):
    tree = ast.parse(open(path).read())
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


def test_the_shuffle_inference_and_its_private_helper_are_gone():
    names = _function_names(_PIPELINE_SRC)
    for gone in ("_band_inference", "_block_perm_maxcorr_pvalue"):
        assert gone not in names, f"{gone} is still defined"


def test_fisher_z_ci_had_no_other_caller_and_is_gone():
    names = _function_names(_STATS_SRC)
    assert "fisher_z_ci" not in names, "fisher_z_ci is still defined but had exactly one caller"


def test_the_shared_helpers_the_kept_callers_need_are_untouched():
    names = _function_names(_PIPELINE_SRC)
    for kept in ("select_biomarker_band", "_autocorr_adjusted_pgrid", "run_timedomain_branch",
                "report_sharing_for_summary"):
        assert kept in names, f"{kept} was deleted but something else still calls it"


def test_run_timedomain_branch_no_longer_calls_the_deleted_function():
    src = open(_PIPELINE_SRC).read()
    tree = ast.parse(src)
    body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_timedomain_branch":
            body = ast.get_source_segment(src, node)
            break
    assert body is not None, "run_timedomain_branch not found"
    assert "_band_inference(" not in body
    # the band tuple and the sharing note are exactly what the fallback timeline and the
    # on-screen note still read -- both must still be built
    assert '"band": band' in body
    assert "report_sharing_for_summary(session_df)" in body


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
