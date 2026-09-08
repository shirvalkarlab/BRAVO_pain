"""Tests for `bravo_service._sweep_match_direction`, the request-level MatchDirection parsing
the band-by-length sweep and its per-cell drill-down both read from (Track B).

WHY THIS TEST EXISTS. `test_match_direction.py` in this same directory covers the matching
routine itself, `availability.live_lsb_spectrum_match`'s own `match_direction` argument -- but
nothing tested whether the value typed into the page's MatchDirection control actually reaches
that argument. Before this test, the only evidence the wiring worked was a single live bridge
call against RCS08 in an earlier session, which is not repeatable and leaves no record in either
test suite. This closes that gap directly, at the level this container suite can run without a
database: the request-dict parsing function itself, and the fact that both of the sweep's two
request-handling entry points call the one shared helper rather than re-implementing it.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_sweep_match_direction.py
"""
import inspect
import os
import sys

# bravo_service imports `from Server import models` at module load, so /usr/src/BRAVO (the dir
# that contains both Server/ and modules/) must be on the path AND Django must be set up. The
# run_tests.py harness already does django.setup(); when run standalone we replicate it (the same
# pattern test_band_candidate.py already uses).
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


def test_default_with_no_match_direction_key_is_pro_first():
    assert bs._sweep_match_direction({}) == "pro_first"


def test_prior_is_recognised():
    assert bs._sweep_match_direction({"MatchDirection": "prior"}) == "prior"


def test_nearest_is_recognised():
    assert bs._sweep_match_direction({"MatchDirection": "nearest"}) == "nearest"


def test_recognition_is_case_insensitive():
    assert bs._sweep_match_direction({"MatchDirection": "PRIOR"}) == "prior"
    assert bs._sweep_match_direction({"MatchDirection": "Nearest"}) == "nearest"


def test_an_unrecognised_value_falls_back_to_pro_first_not_prior():
    """The sweep's own fallback is pro_first, deliberately different from the older three-way
    parse near line 3915 (which falls back to "prior"). A typo or an unexpected value here must
    not silently switch the sweep to the OTHER function's default.
    """
    assert bs._sweep_match_direction({"MatchDirection": "sideways"}) == "pro_first"
    assert bs._sweep_match_direction({"MatchDirection": ""}) == "pro_first"
    assert bs._sweep_match_direction({"MatchDirection": "pro_first"}) == "pro_first"


def test_the_grid_endpoint_and_the_cell_endpoint_call_the_one_shared_helper():
    """Both `band_time_sweep_for_participant` and `band_time_sweep_cell_for_participant` must read
    `_sweep_match_direction` rather than each re-parsing MatchDirection inline -- which is exactly
    the duplication this fix removed. Checked by reading each function's own source rather than by
    running the full request pipeline, so this test does not need a database or a participant.
    """
    for fn in (bs.band_time_sweep_for_participant, bs.band_time_sweep_cell_for_participant):
        src = inspect.getsource(fn)
        assert "_sweep_match_direction(request_data)" in src, (
            f"{fn.__name__} no longer calls the shared MatchDirection helper -- "
            f"has its parsing been re-duplicated inline?")
        assert 'request_data.get("MatchDirection"' not in src, (
            f"{fn.__name__} parses MatchDirection inline again, alongside the shared helper -- "
            f"that reintroduces the duplication this fix removed.")


if __name__ == "__main__":
    _fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    _passed = _failed = 0
    for _fn in _fns:
        try:
            _fn()
            _passed += 1
            print(f"PASS {_fn.__name__}")
        except Exception as exc:                                  # noqa: BLE001
            _failed += 1
            print(f"FAIL {_fn.__name__}: {exc!r}")
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)
