"""The Closed-Loop sign-off printed `OR CI [0.45738925624915433, 1.545551646406637]` and
`band×era LRT p=0.31974358451988527` (page review 2026-10-02): the gate details carry three
significant digits."""
import os
import re
import sys
import pathlib

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django
    django.setup()
except Exception:
    pass

from modules.Biomarkers import bravo_service as BS


def test_the_stability_gate_detail_prints_the_p_value_to_three_digits():
    state, detail = BS._deployment_summary_stim_stable_gate(
        {"available": True, "stability_verdict": "stable", "lrt_p": 0.31974358451988527})
    assert state == "pass"
    assert "p=0.32 " in detail or "p=0.320 " in detail or re.search(r"p=0\.3\d\d? ", detail)
    assert "0.31974358451988527" not in detail


def test_short_keeps_three_significant_digits_and_passes_a_non_number_through():
    assert BS._short(0.45738925624915433) == "0.457"
    assert BS._short(1.545551646406637) == "1.55"
    assert BS._short(None) == "None"
