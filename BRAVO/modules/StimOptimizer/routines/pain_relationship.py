"""Which bands on each sensing contact RISE with pain, read off the stored Biomarkers grid.

Decision 199 (2026-09-17). The readiness screen and the two-stage gate call a (contact, side,
rate) cell responsive when at least ONE band both falls with stimulation current (the
era-blocked slope, `lfp_evidence.band_era_negative_significant`) and rises with pain. This module
supplies the second half: for every contact on the calibrated grid the Biomarkers page shows, the
band centres whose best-of-lengths correlation with the pain score is POSITIVE and SUPPORTED.

Decision 210 (2026-09-20), the PI: "loosen the rule ... so at least some bands pass". Until then
the leg required the grid's own "established" answer, which asks two things of a band: that its
block-bootstrap interval on the correlation lie wholly off zero (decision 183), AND that the value
beat what the same best-of-nine-lengths choice reaches on shuffled pain scores (the selection-aware
bar). Ten pain reports on 2026-09-20 took R 1-3+'s best band from r 0.44 (established) to 0.23 --
interval still wholly above zero, but under the shuffle bar of 0.28 -- and the readiness screen went
from six usable cells to none. The pain leg now counts a band as SUPPORTED when its correlation is
positive and its own interval lies wholly above zero; the selection-aware bar is reported beside it
(`n_established_positive`, `supported_not_established_hz`) rather than required. This is the
classical criterion at a fixed length, and the joint rule still demands the SAME band fall with
current on an independent era-blocked test, so the conjunction stays conservative. A positive point
value whose interval includes zero does not count, and a row with no interval can only count by
being established.

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

#: The grid's own word for a correlation that clears the 22-band correction AND the selection-aware
#: shuffle bar (decisions 63, 183).
ESTABLISHED = "established"
#: The pain leg's own level (decision 210): positive, with the block-bootstrap interval wholly above zero.
SUPPORTED = "supported"

RULE = ("a band counts when its best-of-lengths Pearson correlation with the pain score on the "
        "Biomarkers grid is positive (power rises with pain) AND its block-bootstrap interval lies "
        "wholly above zero (supported); whether it also clears the grid's selection-aware bar "
        "(established) is reported beside it, not required (decision 210)")


def _rows(grid, channel):
    sw = ((grid or {}).get("band_time_sweep") or {}).get(channel) or {}
    return list(sw.get("best_correlation_rows") or [])


def _finite(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _is_established(r):
    rr = _finite(r.get("pearson_r"))
    return rr is not None and rr > 0 and str(r.get("answer") or "") == ESTABLISHED


def _is_supported(r):
    """Positive, with the row's own block-bootstrap interval wholly above zero. An established row
    is supported by construction (its interval is off zero on the positive side)."""
    if _is_established(r):
        return True
    rr, lo = _finite(r.get("pearson_r")), _finite(r.get("pearson_r_low"))
    return rr is not None and lo is not None and rr > 0 and lo > 0


def pain_positive_centers_by_channel(grid, *, level=SUPPORTED):
    """``{channel: frozenset(centres)}`` for every contact on the grid, or ``None`` when there is
    no grid. A contact ON the grid with no qualifying band maps to an EMPTY set (known: none);
    a contact absent from the grid is absent here (unknown), and the screen says which.
    ``level`` is SUPPORTED (the rule, decision 210) or ESTABLISHED (the stricter reading)."""
    if not isinstance(grid, dict) or not grid.get("available") or not grid.get("band_time_sweep"):
        return None
    if level not in (SUPPORTED, ESTABLISHED):
        raise ValueError(f"level must be {SUPPORTED!r} or {ESTABLISHED!r}, got {level!r}")
    test = _is_established if level == ESTABLISHED else _is_supported
    out = {}
    for ch in (grid.get("band_time_sweep") or {}):
        cs = set()
        for r in _rows(grid, ch):
            c = _finite(r.get("band_center_hz"))
            if c is not None and test(r):
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
        est = {_finite(r.get("band_center_hz")) for r in rows if _is_established(r)}
        est_neg = sum(1 for r in rows if (_finite(r.get("pearson_r")) or 0) < 0
                      and str(r.get("answer") or "") == ESTABLISHED)
        pos_not = sum(1 for r in rows if (_finite(r.get("pearson_r")) or 0) > 0 and not _is_supported(r))
        per[ch] = {"centers_hz": sorted(by[ch]),
                   "n_supported_positive": len(by[ch]), "n_established_positive": len(est),
                   "supported_not_established_hz": sorted(by[ch] - est),
                   "n_positive_not_supported": int(pos_not),
                   "n_established_negative": int(est_neg), "n_centres_on_grid": len(rows)}
    return {"available": True, "score": gs.get("sweep_metric"),
            "score_label": gs.get("metric_label"), "stored_utc": gs.get("stored_utc"),
            "built_now": bool(gs.get("built_now")), "rule": RULE, "by_channel": per}
