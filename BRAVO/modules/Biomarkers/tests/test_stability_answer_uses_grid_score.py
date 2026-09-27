"""A grid's stability answer is computed on the grid's own pain score (found 2026-09-26, decision 331).

The daily precompute asks for a grid with `SweepMetric` only. The stability run passed that request
on unchanged, and the per-point setup reads `LabelMetric`, which then fell back to NRS: on RCS08 the
daily Left Leg VAS grid carried NRS stability answers (100 "cannot tell", 32 "behaves differently",
identical to the NRS grid's). This pins that the run hands the per-point setup the grid's own score.

Run inside the container:
    python3 -W ignore modules/Biomarkers/tests/test_stability_answer_uses_grid_score.py
"""
import os
import sys

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402


def _capture_setup_request(request_data):
    seen = {}
    saved = (bs.band_time_sweep_for_participant, bs.stability_grid_points, bs.stability_grid_for_participant)
    try:
        bs.band_time_sweep_for_participant = lambda req: {"band_time_sweep": {"X": {}}, "band_width_hz": 5.0,
                                                            "sweep_key": {"signature_key": "k", "provenance": []}}
        bs.stability_grid_points = lambda sweeps: [("X", 20.5)]

        def fake_grid(uid, points, **kw):
            seen.update(kw.get("request_data") or {})
            return None                                   # stop before anything is stored
        bs.stability_grid_for_participant = fake_grid
        bs.compute_and_store_stability_grid("participant-under-test", request_data=request_data, force=True)
    finally:
        (bs.band_time_sweep_for_participant, bs.stability_grid_points,
         bs.stability_grid_for_participant) = saved
    return seen


def test_a_sweep_metric_only_request_is_answered_on_that_score():
    seen = _capture_setup_request({"SweepMetric": "left_leg_vas"})
    assert seen.get("LabelMetric") == "left_leg_vas", seen


def test_an_explicit_label_metric_agrees_with_the_grid_score():
    seen = _capture_setup_request({"SweepMetric": "back_vas", "LabelMetric": "nrs"})
    assert seen.get("LabelMetric") == "back_vas", seen


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
