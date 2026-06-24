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
