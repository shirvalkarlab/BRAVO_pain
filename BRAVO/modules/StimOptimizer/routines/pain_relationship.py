"""Which bands on each sensing contact RISE with pain, read off the stored Biomarkers grid.

Decision 199 (2026-09-17). The readiness screen and the two-stage gate call a (contact, side,
rate) cell responsive when at least ONE band both falls with stimulation current (the
era-blocked slope, `lfp_evidence.band_era_negative_significant`) and rises with pain. This module
supplies the second half: for every contact on the calibrated grid the Biomarkers page shows, the
band centres whose best-of-lengths correlation with the pain score is POSITIVE and ESTABLISHED
(the grid's own `answer`, the 22-band-corrected q below 0.05, decision 63).

Why positive: the device's control polarity is fixed (rule D19, decision 134) -- more current
must mean less band power, and less band power must mean less pain, so power must RISE with pain.
A band whose power falls as pain rises (L 1-3+ at 12.5 Hz on RCS08, r = -0.47, established) is a
real biomarker and the wrong sign for this controller; it is counted here as
`n_established_negative` so a reader sees it, and it never qualifies.

The grid is `ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop`'s payload, read by
the Stim Optimizer as its own consumer. Django-free so the host suite can test it on a constructed
payload.
"""
from __future__ import annotations

import numpy as np

#: The grid's own word for a correlation that clears the 22-band correction (decision 63).
ESTABLISHED = "established"

RULE = ("a band counts when its best-of-lengths Pearson correlation with the pain score on the "
        "Biomarkers grid is positive (power rises with pain) AND the grid calls it established "
        "(corrected q below 0.05 across the 22 band centres)")


def _rows(grid, channel):
    sw = ((grid or {}).get("band_time_sweep") or {}).get(channel) or {}
    return list(sw.get("best_correlation_rows") or [])


def _finite(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def pain_positive_centers_by_channel(grid):
    """``{channel: frozenset(centres)}`` for every contact on the grid, or ``None`` when there is
    no grid. A contact ON the grid with no qualifying band maps to an EMPTY set (known: none);
    a contact absent from the grid is absent here (unknown), and the screen says which."""
    if not isinstance(grid, dict) or not grid.get("available") or not grid.get("band_time_sweep"):
        return None
    out = {}
    for ch in (grid.get("band_time_sweep") or {}):
        cs = set()
        for r in _rows(grid, ch):
            c, rr = _finite(r.get("band_center_hz")), _finite(r.get("pearson_r"))
            if c is None or rr is None:
                continue
            if rr > 0 and str(r.get("answer") or "") == ESTABLISHED:
                cs.add(c)
        out[str(ch)] = frozenset(cs)
    return out


def summarise(grid) -> dict:
    """The page's own block: the score and stamp the grid was built under, the rule, and per
    contact the qualifying centres with the counts a reader needs to see why a contact has none."""
    by = pain_positive_centers_by_channel(grid)
    if by is None:
        return {"available": False,
                "reason": ((grid or {}).get("reason") if isinstance(grid, dict) else None)
                or "no stored Biomarkers grid is available for this participant",
                "rule": RULE, "by_channel": {}}
    gs = (grid.get("grid_settings") or {})
    per = {}
    for ch in by:
        rows = _rows(grid, ch)
        est_neg = sum(1 for r in rows if (_finite(r.get("pearson_r")) or 0) < 0
                      and str(r.get("answer") or "") == ESTABLISHED)
        pos_not = sum(1 for r in rows if (_finite(r.get("pearson_r")) or 0) > 0
                      and str(r.get("answer") or "") != ESTABLISHED)
        per[ch] = {"centers_hz": sorted(by[ch]), "n_established_positive": len(by[ch]),
                   "n_positive_not_established": int(pos_not),
                   "n_established_negative": int(est_neg), "n_centres_on_grid": len(rows)}
    return {"available": True, "score": gs.get("sweep_metric"),
            "score_label": gs.get("metric_label"), "stored_utc": gs.get("stored_utc"),
            "built_now": bool(gs.get("built_now")), "rule": RULE, "by_channel": per}
