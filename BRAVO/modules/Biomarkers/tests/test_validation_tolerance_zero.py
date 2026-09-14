"""Review B11 (2026-09-12): a typed match tolerance of 0 no longer crashes the sign-off endpoints.

`_match_tolerance_param` reads an explicit 0 or negative `MatchToleranceMin` as "time-matching
off" (None). The discovery sweep answers None with its longest length of signal; the sign-off
path (`_band_validation_setup`, behind the four Closed-Loop endpoints) answered it with
`float(None)` -- a TypeError the page showed as an error. It now takes the sweep's fallback.
"""
import inspect

from .. import bravo_service as B
from ..routines import analytics as A


def test_zero_and_negative_tolerances_fall_back_to_the_longest_length_of_signal():
    expect = float(max(A.BAND_TIME_SWEEP_SECONDS)) / 60.0        # 300 s -> 5.0 min
    assert expect == 5.0
    for raw in ({"MatchToleranceMin": 0}, {"MatchToleranceMin": -3}, {"MatchToleranceMin": "0"}):
        tol = B._match_tolerance_param(raw)
        assert tol is None, (raw, tol)
        assert B._validation_tolerance_min(tol) == expect
    # a real value passes through unchanged, and the default is the default
    assert B._validation_tolerance_min(15) == 15.0
    assert B._validation_tolerance_min(B._match_tolerance_param({})) == float(
        B._match_tolerance_param({}))


def test_the_sign_off_setup_uses_the_guarded_value():
    src = inspect.getsource(B._band_validation_setup)
    assert "tolerance_min=_validation_tolerance_min(match_tol_min)" in src
    assert "float(match_tol_min)" not in src


if __name__ == "__main__":
    test_zero_and_negative_tolerances_fall_back_to_the_longest_length_of_signal()
    test_the_sign_off_setup_uses_the_guarded_value()
    print("All zero-tolerance tests passed.")
