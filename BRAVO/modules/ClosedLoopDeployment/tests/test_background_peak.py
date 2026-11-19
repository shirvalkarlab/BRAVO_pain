"""The band's peak above the smooth background of the device's own PSDs (item 7b, the PI,
2026-10-18): measured, reported beside the chosen band, and used only to break ties.

Pinned on values: a synthetic PSD built as a known background ``a*f**-b + c`` gives a ratio of
1.000 away from an added peak and the peak's own factor inside it; a device-flagged PSD is left
out and counted; two contact pairs are never pooled; the chosen band's entry is the median over
its own pair; and the tie-break can reorder only candidates that are equal on every other key, so
it never moves a refused band above an allowed one.
"""
from __future__ import annotations

import numpy as np

from ClosedLoopDeployment import background_peak as BP

F = np.round(np.arange(0.98, 96.7, 0.9766), 4)          # the device's bins, about 0.98 Hz apart


def _psd(a=40.0, b=1.0, c=0.3, peak_at=None, factor=1.0, width=2.5):
    p = BP.background(F, a, b, c)
    if peak_at is not None:
        m = np.abs(F - peak_at) <= width
        p = p.copy()
        p[m] *= factor
    return p


def test_a_flat_background_reads_one_and_a_known_peak_reads_its_own_factor():
    p = _psd(peak_at=25.5, factor=1.6)
    prm = BP.fit_background(F, p)
    assert prm is not None
    assert abs(prm[1] - 1.0) < 1e-3                       # the background was recovered, not the peak
    assert abs(BP.band_ratio(F, p, prm, 12.5) - 1.0) < 1e-3
    assert abs(BP.band_ratio(F, p, prm, 25.5) - 1.6) < 1e-3


def test_a_peak_below_the_refit_factor_stays_in_the_fit_and_reads_a_little_low():
    """A bin under 1.5 times the fit is kept in it, so a small peak pulls the background up a
    little: a 1.25 peak reads below 1.25 (the method's own property, stated, not hidden)."""
    p = _psd(peak_at=15.5, factor=1.25)
    r = BP.band_ratio(F, p, BP.fit_background(F, p), 15.5)
    assert 1.15 < r < 1.25


def test_the_device_band_is_centre_plus_minus_2_5_hz_edges_included():
    f = np.array([20.0, 22.5, 25.0, 27.5, 30.0])
    p = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    flat = (1.0, 0.0, 0.0)                                 # background 1 everywhere
    assert BP.band_ratio(f, p, flat, 25.0) == 3.0          # 22.5, 25.0 and 27.5 are inside


def test_device_flagged_psds_are_left_out_and_pairs_are_never_pooled():
    psds = [
        {"channel": "SensingElectrodeConfigDef.ZERO_AND_THREE", "hemisphere": "HemisphereLocationDef.Left",
         "f": F, "p": _psd(peak_at=25.5, factor=1.9), "status": "ArtifactStatusDef.ARTIFACT_NOT_PRESENT"},
        {"channel": "SensingElectrodeConfigDef.ZERO_AND_THREE", "hemisphere": "HemisphereLocationDef.Left",
         "f": F, "p": _psd(peak_at=25.5, factor=1.7), "status": None},
        {"channel": "SensingElectrodeConfigDef.ZERO_AND_THREE", "hemisphere": "HemisphereLocationDef.Left",
         "f": F, "p": _psd(peak_at=25.5, factor=9.0), "status": "ArtifactStatusDef.SQC_ARTIFACT_PRESENT"},
        {"channel": "ZERO_THREE_RIGHT", "hemisphere": None, "f": F, "p": _psd(), "status": None},
    ]
    tab = BP.ratios_from_psds(psds)
    assert tab["counts"] == {"psds": 4, "flagged_by_device": 1, "no_fit": 0, "no_pair": 0, "used": 3}
    left = BP.for_band(tab, "ZERO_THREE_LEFT", 25.5)
    right = BP.for_band(tab, "ZERO_THREE_RIGHT", 25.5)
    assert left["available"] and left["n_psds"] == 2
    assert abs(left["median_ratio"] - 1.8) < 1e-3          # median of 1.9 and 1.7; the 9.0 is out
    assert right["available"] and right["n_psds"] == 1 and abs(right["median_ratio"] - 1.0) < 1e-3
    assert BP.for_band(tab, "ONE_THREE_LEFT", 25.5)["available"] is False


def test_the_tie_break_reorders_only_candidates_equal_on_every_other_key():
    cands = [
        {"name": "refused, large peak", "refused": 1, "q": 0.01, "peak_ratio": 1.9},
        {"name": "allowed, small peak", "refused": 0, "q": 0.01, "peak_ratio": 1.05},
        {"name": "allowed, large peak", "refused": 0, "q": 0.01, "peak_ratio": 1.40},
        {"name": "allowed, no ratio", "refused": 0, "q": 0.01, "peak_ratio": None},
        {"name": "allowed, worse q", "refused": 0, "q": 0.20, "peak_ratio": 2.50},
    ]
    order = [c["name"] for c in sorted(cands, key=lambda c: BP.tie_break_key(c, equal_on=("refused", "q")))]
    assert order == ["allowed, large peak", "allowed, small peak", "allowed, no ratio",
                     "allowed, worse q", "refused, large peak"]


def test_the_chosen_band_reaches_the_report_payload(monkeypatch):
    from ClosedLoopDeployment import adapter as AD
    tab = BP.ratios_from_psds([{"channel": "ZERO_THREE_LEFT", "hemisphere": None, "f": F,
                                "p": _psd(peak_at=15.5, factor=1.6), "status": None}])
    monkeypatch.setattr(AD, "peak_above_background_table", lambda participant: tab)
    got = AD.peak_above_background_for("uid", {"channel": "ZERO_THREE_LEFT", "center_hz": 15.5})
    assert got["available"] is True and abs(got["median_ratio"] - 1.6) < 1e-3
    assert "tie-break" in got["use"]
    src = open(AD.__file__).read()
    assert 'out["peak_above_background"] = peak_above_background_for(' in src
