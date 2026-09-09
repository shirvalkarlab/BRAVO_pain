"""Unit tests for the BandCandidate emission helpers (DESIGN_biomarker_pipeline_v2 sec.6).

These target the pure schema-assembly helpers and the device-control mapping logic, which do not
need Django/DB. The end-to-end build_band_candidate path (DB + glmer) is exercised live via the
/emitBandCandidate endpoint, not here.

Run inside the container:
    python3 -W ignore modules/Biomarkers/tests/test_band_candidate.py
"""
import os
import sys

# bravo_service imports `from Server import models` at module load, so /usr/src/BRAVO (the dir
# that contains both Server/ and modules/) must be on the path AND Django must be set up. The
# run_tests.py harness already does django.setup(); when run standalone we replicate it.
_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)                       # /usr/src/BRAVO (has Server/ and modules/)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402


def test_credible_ci_rule():
    # Wide CI -> credible; narrow saturated-Wald CI -> not credible (the 5 v2 narrow-CI cases).
    credible, w = bs._band_credible_ci(0.28, 0.58)
    assert credible is True and abs(w - 0.30) < 1e-9
    credible, w = bs._band_credible_ci(0.3780, 0.3795)   # CI width ~0.0015
    assert credible is False and w < 0.01
    # Missing bounds -> (None, None)
    assert bs._band_credible_ci(None, 0.5) == (None, None)
    assert bs._band_credible_ci(0.5, None) == (None, None)


def test_adaptive_gate_constants():
    assert bs.ADAPTIVE_LO_HZ == 8.0 and bs.ADAPTIVE_HI_HZ == 30.0


def test_suggested_mode_positive_inband():
    # Positive-direction biomarker inside 8-30 Hz -> Dual adaptive, no inversion.
    mode, reason = bs._suggested_percept_mode("positive", True)
    assert mode == "Dual" and "ramps up" in reason


def test_suggested_mode_negative_inband():
    # Negative-direction biomarker (higher power -> lower pain) needs the inverse law -> no stock
    # adaptive mode (Percept inverse is sensing-only). suggested_mode is None with an explainer.
    mode, reason = bs._suggested_percept_mode("negative", True)
    assert mode is None and "inverse" in reason.lower()


def test_suggested_mode_out_of_band():
    # Off-band (e.g. 84.5 Hz NRS anchor) -> not adaptive-valid regardless of polarity.
    mode, reason = bs._suggested_percept_mode("negative", False)
    assert mode is None and "adaptive sensing range" in reason


def test_decide_verdict_branches():
    # unavailable glmer
    assert bs._band_decide_verdict({"available": False}, {}) == "unavailable"
    # separation / singular guards
    assert bs._band_decide_verdict({"available": True, "separation": True}, {}) == "failed (separation)"
    assert bs._band_decide_verdict(
        {"available": True, "separation": False, "singular": True}, {}) == "failed (singular random effect)"
    # n.s. p
    assert bs._band_decide_verdict(
        {"available": True, "separation": False, "singular": False, "p": 0.2}, {}
    ) == "candidate (mixed-effects n.s.)"
    # validated stim-stable vs stim-dependent
    g = {"available": True, "separation": False, "singular": False, "p": 0.001}
    assert bs._band_decide_verdict(g, {"available": True, "stim_stable": True}) == "VALIDATED (stim-stable)"
    assert bs._band_decide_verdict(g, {"available": True, "stim_stable": False}) == "VALIDATED (stim-dependent)"

    # The third and fourth labels, added 2026-09-04. This function used to fall through to
    # "(stim-stable)" whenever `stim_stable` was not explicitly False, which includes the case
    # where the equivalence test RAN and could not decide — the interaction test failed to reject
    # while the interval on the largest between-era slope difference was wider than the declared
    # margin. A failure to reject is not evidence of equivalence, so the old label asserted in the
    # badge exactly what the test had declined to grant.
    assert bs._band_decide_verdict(
        g, {"available": True, "stim_stable": None, "stability_verdict": "inconclusive"}
    ) == "VALIDATED (stim stability not determinable)"
    # an inconclusive verdict wins even if the legacy flag was left permissive, because the
    # three-way verdict is the authority and the boolean is the thing being deprecated
    assert bs._band_decide_verdict(
        g, {"available": True, "stim_stable": True, "stability_verdict": "inconclusive"}
    ) == "VALIDATED (stim stability not determinable)"
    # nothing tested at all is its own state and must not read as either answer
    assert bs._band_decide_verdict(
        g, {"available": True, "stim_stable": None}
    ) == "VALIDATED (stim stability not tested)"
    # and a payload predating the equivalence test, with a positive legacy flag, is unchanged
    assert bs._band_decide_verdict(
        g, {"available": True, "stim_stable": True, "stability_verdict": "equivalent"}
    ) == "VALIDATED (stim-stable)"


def test_deployment_summary_stim_stable_gate_reads_three_way_verdict():
    """Decision 82 fix: deployment_summary's sign-off card must key its stim-stability GATE off
    `stability_verdict`, never the retired `stim_stable` boolean (`p_lrt >= 0.05`, a failure to
    reject rather than evidence of stability). The bug this pins: a band whose interaction test ran
    but was too underpowered to tell stable from unstable ("inconclusive") used to render as a
    green "pass" on the clinician-facing card, because the retired flag is True whenever the LRT
    simply fails to reject -- exactly the "inconclusive" case too."""
    # Genuinely shown stable -> pass. stim_stable also True here, but that's not why it passes.
    state, detail = bs._deployment_summary_stim_stable_gate(
        {"available": True, "lrt_p": 0.6, "stim_stable": True, "stability_verdict": "stable"})
    assert state == "pass" and "stable" in detail

    # Interaction test rejects -> fail, regardless of the retired flag.
    state, _ = bs._deployment_summary_stim_stable_gate(
        {"available": True, "lrt_p": 0.01, "stim_stable": False, "stability_verdict": "stim-dependent"})
    assert state == "fail"

    # THE BUG: the LRT did not reject (stim_stable=True under the retired rule) but the interval on
    # the largest between-era difference is wider than the declared margin -- inconclusive, not
    # stable. Must render as indeterminate, never pass.
    state, detail = bs._deployment_summary_stim_stable_gate(
        {"available": True, "lrt_p": 0.29, "stim_stable": True, "stability_verdict": "inconclusive"})
    assert state == "indeterminate", (
        f"stim_stable=True with an inconclusive equivalence verdict must render indeterminate, "
        f"not {state!r} -- this is the exact false-reassurance decision 82 found")
    assert "cannot tell" in detail

    # LRT never converged at all (no stability_verdict key exists on the payload) -> indeterminate.
    state, _ = bs._deployment_summary_stim_stable_gate({"available": False})
    assert state == "indeterminate"

    # A payload predating the equivalence test (stability_verdict absent, available True) must also
    # abstain rather than trust the bare boolean.
    state, _ = bs._deployment_summary_stim_stable_gate({"available": True, "lrt_p": 0.6, "stim_stable": True})
    assert state == "indeterminate"


def test_deployment_summary_adaptive_band_gate_checks_edges_not_centre():
    """Decision 82 fix: the sign-off card's adaptive-range gate must check the band EDGES against
    8-30 Hz, matching ClosedLoopDeployment/constraints.py's D08 rule -- not merely the centre. Cases
    mirror D08's own docstring examples so the two rules agree."""
    # D08's own documented disqualifying case: a 5 Hz band centred at 3.92 Hz runs 1.42-6.42 Hz,
    # entirely below the 8 Hz floor.
    state, detail, lo, hi = bs._deployment_summary_adaptive_band_gate(3.92, 5.0)
    assert state == "fail" and abs(lo - 1.42) < 1e-9 and abs(hi - 6.42) < 1e-9

    # D08's own second documented case: centre 10 Hz is inside 8-30, but a 5 Hz band's lower edge
    # (7.5 Hz) is not. The OLD centre-only gate would have shown "pass" here.
    state, detail, lo, hi = bs._deployment_summary_adaptive_band_gate(10.0, 5.0)
    assert state == "fail", "band edge (7.5 Hz) sits below the adaptive floor even though the centre is inside it"
    assert abs(lo - 7.5) < 1e-9

    # Comfortably inside on both edges -> pass.
    state, _, lo, hi = bs._deployment_summary_adaptive_band_gate(20.0, 5.0)
    assert state == "pass" and lo == 17.5 and hi == 22.5

    # Exactly at the boundary on both ends -> pass (D08 uses >= / <=, not strict inequality).
    state, _, lo, hi = bs._deployment_summary_adaptive_band_gate(19.0, 22.0)  # edges 8.0, 30.0
    assert state == "pass" and lo == 8.0 and hi == 30.0


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    npass = nfail = 0
    for fn in fns:
        try:
            fn(); npass += 1; print("PASS", fn.__name__)
        except Exception as e:
            nfail += 1; print("FAIL", fn.__name__, repr(e)); traceback.print_exc()
    print(f"PASS={npass} FAIL={nfail}")
