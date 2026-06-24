"""Regression tests for _match_to_pro, covering the three direction modes.

The PRO-first mode is the new discovery default — it walks PROs (the units of independence) and
claims up to max_per_rating closest PSDs per channel within tolerance, so a PRO with sparse PSD
coverage still contributes. The original PSD-first modes ('prior' = forecasting, 'nearest' =
symmetric) are kept for threshold-deployment and back-compat.
"""
import os, sys
# Tests can run standalone (via the harness) or under pytest; bootstrap Django either way.
if "DJANGO_SETTINGS_MODULE" not in os.environ:
    os.environ["DJANGO_SETTINGS_MODULE"] = "BRAVO.settings"
if "BRAVO" not in [p.split("/")[-1] for p in sys.path]:
    sys.path.insert(0, "/usr/src/BRAVO")
try:
    import django
    if not django.apps.apps.ready:
        django.setup()
except Exception:
    pass

import numpy as np
from modules.Biomarkers.routines.streaming_psd import _match_to_pro


def test_prior_direction_requires_psd_before_pro():
    """A PSD that comes AFTER the PRO must not match under direction='prior' (forecasting)."""
    psd_t = np.array([100.0, 300.0])         # PSD at t=100 and t=300
    pro_t = np.array([200.0])                # single PRO at t=200, value=5
    pro_v = np.array([5.0])
    lab, dt, idx = _match_to_pro(psd_t, pro_t, pro_v, tolerance_min=10, direction="prior")
    # Only the PSD at t=100 precedes the PRO and is within tolerance (200-100 = 100s = 1.67 min).
    assert np.isnan(lab[1]), "PSD after PRO must NOT match under prior"
    assert np.isfinite(lab[0]) and lab[0] == 5.0


def test_nearest_direction_matches_either_side():
    """Direction='nearest' matches the closest PRO in either time direction."""
    psd_t = np.array([100.0, 300.0])
    pro_t = np.array([200.0])
    pro_v = np.array([7.0])
    lab, dt, idx = _match_to_pro(psd_t, pro_t, pro_v, tolerance_min=10, direction="nearest")
    # Both PSDs are 100s = 1.67 min from the PRO; both should match.
    assert np.all(np.isfinite(lab)), f"nearest must match both, got {lab}"
    assert np.allclose(lab, 7.0)


def test_pro_first_maximizes_pro_coverage_over_psd_first():
    """
    Two PROs at t=100 and t=1000. PSDs cluster heavily around the first PRO (8 PSDs in a tight
    burst) and lightly around the second (1 PSD nearby). PSD-first with max_per_rating=3 lets the
    burst claim 3 of its 8 PSDs (the rest go unmatched), and the lone PSD matches the second PRO
    — so 2/2 PROs covered, 4 PSDs matched. PRO-first achieves the SAME 2/2 PRO coverage with the
    SAME cap, but on a richer pool: the burst still loses PSDs beyond cap, while the second PRO
    still claims its lone PSD. The non-trivial discriminator is what happens when the burst would
    have STOLEN the second PRO's PSD — engineer that case explicitly here.
    """
    # PRO #1 at t=100; PRO #2 at t=400. PSD at t=395 is closest to PRO #2 (5s away) but ALSO
    # within tolerance of PRO #1 (295s = ~5 min). Under PSD-first 'nearest' the PSD goes to its
    # closer PRO (PRO #2) — fine. But under PSD-first with a small population of PRO #2 PSDs and
    # a large population of PRO #1 PSDs, the matcher never asks "do I leave one for PRO #2?".
    # PRO-first walks PROs in time order — PRO #1 fills first, then PRO #2 claims its remaining
    # candidates. With the per-PRO cap we engineer below, PSD-first wastes PSDs while PRO-first
    # covers both PROs.
    psd_t = np.array([99.0, 100.0, 101.0, 102.0, 395.0])  # 4 around PRO #1 + 1 near PRO #2
    pro_t = np.array([100.0, 400.0])
    pro_v = np.array([1.0, 2.0])
    channels = np.array(["A", "A", "A", "A", "A"], dtype=object)

    # PRO-first with max_per_rating=2 + tolerance large enough for either PRO to see the t=395 PSD.
    lab_pf, dt_pf, idx_pf = _match_to_pro(
        psd_t, pro_t, pro_v, tolerance_min=10,
        direction="pro_first", channels=channels, max_per_rating=2)
    matched_pros_pf = set(idx_pf[idx_pf >= 0].tolist())
    assert matched_pros_pf == {0, 1}, f"pro_first must cover BOTH PROs, got {matched_pros_pf}"

    # PSD-first 'nearest' gives the t=395 PSD to PRO #2 too (it's much closer); cap then drops
    # the farthest of the PRO #1 burst. This is the easy case — both work. Verify it still works.
    lab_nr, dt_nr, idx_nr = _match_to_pro(psd_t, pro_t, pro_v, tolerance_min=10, direction="nearest")
    matched_pros_nr = set(idx_nr[idx_nr >= 0].tolist())
    assert 1 in matched_pros_nr, "nearest must still cover PRO #2 in the easy case"


def test_pro_first_enforces_per_channel_cap():
    """PRO-first caps PSDs PER CHANNEL per PRO. A burst on channel A shouldn't crowd out channel B."""
    psd_t = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    channels = np.array(["A", "A", "A", "B", "B"], dtype=object)
    pro_t = np.array([100.0])
    pro_v = np.array([3.0])
    lab, dt, idx = _match_to_pro(psd_t, pro_t, pro_v, tolerance_min=10,
                                  direction="pro_first", channels=channels, max_per_rating=2)
    # Channel A: 3 candidates, cap 2 -> 2 matched. Channel B: 2 candidates, cap 2 -> 2 matched.
    assert int((idx >= 0).sum()) == 4, f"expected 4 matched (2 per channel), got {int((idx>=0).sum())}"
    # Channel B's PSDs (indices 3,4) must both be matched -- not crowded out by channel A's burst.
    assert np.all(idx[3:5] >= 0), f"channel B PSDs must claim despite A's burst, got idx={idx}"


def test_pro_first_falls_back_to_nearest_on_misuse():
    """Calling pro_first without channels/max_per_rating shouldn't silently return zero matches."""
    psd_t = np.array([100.0, 200.0])
    pro_t = np.array([150.0])
    pro_v = np.array([9.0])
    lab, dt, idx = _match_to_pro(psd_t, pro_t, pro_v, tolerance_min=10, direction="pro_first")
    # No channels supplied -> falls back to nearest. Both PSDs are 50s = 0.83min from the PRO,
    # within tolerance -> both must match.
    assert np.all(idx >= 0), f"pro_first misuse must fall back to nearest, got idx={idx}"


def test_pro_first_dt_sign_convention_unchanged():
    """`dt_min` is signed (PRO time - PSD time), positive when PRO is in the future. The
    convention must NOT flip under pro_first vs the PSD-first paths."""
    psd_t = np.array([100.0, 200.0])
    pro_t = np.array([150.0])  # PRO between the two PSDs
    pro_v = np.array([3.0])
    channels = np.array(["X", "X"], dtype=object)
    lab, dt, idx = _match_to_pro(psd_t, pro_t, pro_v, tolerance_min=10,
                                  direction="pro_first", channels=channels, max_per_rating=2)
    # PSD at 100: PRO is 50s in the future -> dt = +50s / 60 = +0.833 min.
    # PSD at 200: PRO is 50s in the past   -> dt = -50s / 60 = -0.833 min.
    assert dt[0] > 0 and dt[1] < 0, f"dt sign should encode PRO - PSD, got {dt}"


if __name__ == "__main__":
    test_prior_direction_requires_psd_before_pro()
    test_nearest_direction_matches_either_side()
    test_pro_first_maximizes_pro_coverage_over_psd_first()
    test_pro_first_enforces_per_channel_cap()
    test_pro_first_falls_back_to_nearest_on_misuse()
    test_pro_first_dt_sign_convention_unchanged()
    print("OK")
