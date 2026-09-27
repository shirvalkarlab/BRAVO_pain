"""The server's own default for the sliding-window request field now matches what every live
request has actually meant for a long time (the PI, 2026-09-27, tidying open item N-11).

The page hardcoded its own `SlidingWindow` field off years ago (`Client/src/views/Reports/
Biomarkers/index.js`'s own comment: "sliding-window analysis removed -- always all-data, one
threshold"), but until now the server still defaulted to ON (`True`) when the field was missing.
Nothing exercised that mismatch because the page always sent an explicit `false` -- but the
default was still wrong, and a future caller that forgot to send the field (an offline script, a
different client) would have silently gotten the old train/test detector instead of the one every
report on screen has actually been computed by. The field is no longer sent by the page at all
(it was pure noise on every request); the server's default now carries the real behaviour.

The detector itself (`threshold_biomarker.run_chronic_threshold(..., sliding=True)`) is NOT
deleted: it is the verbatim train/test cross-validation from the original science notebook, kept
reachable on purpose (see the module's own docstring, and `test_adapter.py`'s
`test_run_chronic_threshold_no_sliding`, which already protects the `sliding=False` path this
default now always takes). Only the request-field default changed.

Runs in the container (Django): python3 Biomarkers/tests/test_sliding_window_default_matches_page.py
"""
import os
import sys

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402


def test_a_request_with_no_sliding_window_field_defaults_off():
    _train_days, _step_days, sliding, _window_months, _window_step_months = bs._window_params({})
    assert sliding is False


def test_an_explicit_true_still_reaches_the_kept_detector():
    _train_days, _step_days, sliding, _window_months, _window_step_months = bs._window_params(
        {"SlidingWindow": True})
    assert sliding is True


def test_an_explicit_string_false_still_parses_off():
    _train_days, _step_days, sliding, _window_months, _window_step_months = bs._window_params(
        {"SlidingWindow": "false"})
    assert sliding is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
