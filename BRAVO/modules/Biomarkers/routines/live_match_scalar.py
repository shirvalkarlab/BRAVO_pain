"""Original scalar LSB matcher retained for bounded-memory large requests.

Selection and summary logic moved from accepted Aditya046e0f63; matrix decoding
uses the shared NumPy-compatible conversion. Selection and summary semantics
are shared with the vectorized matcher through differential regression tests.
"""
import numpy as np
from . import analytics
from .availability import PRO_LSB_TIER_TD, PRO_LSB_TIER_BRIDGE, _lsb_family_mat

def live_lsb_spectrum_match(pro_times, raw_cache, *, tol_s=None, td_quantity_s=None,
                            allow_window_reuse=False, extent_s=None, psd_tol_s=None):
    """LIVE per-PRO LSB spectrum by matching PROs against the match-AGNOSTIC raw cache.

    Consumes one channel's `raw_lsb_spectrum_cache(...)` output and produces the SAME per-PRO
    record list `per_pro_lsb_spectrum` returns (drop-in for the spectral scan), but with the
    matching done at request time over the pre-computed 3 s LSB tiles.

    TWO-WINDOW MATCHING (PI 2026-06-28 — the modality split):
      The matching uses TWO independent time controls with DIFFERENT jobs:

      * `tol_s` (the MAIN match-tolerance slider, MatchToleranceMin × 60) is the ELIGIBILITY radius
        for BOTH modalities — a raw window (TD tile OR PSD event) is eligible for a PRO only if it
        falls within ±tol_s of the rating. This is the only PSD control: a PRO's PSD-bridge LSB is the
        nan-median over EVERY eligible PSD event within ±tol_s (no quantity cap on PSD).

      * `td_quantity_s` (the SEPARATE "rating-centered extent" slider) is NOT a ± tolerance — it is a
        QUANTITY OF TD SIGNAL. After TD eligibility is decided by `tol_s`, a PRO keeps only the
        `n_epochs = round(td_quantity_s / window_s)` TD tiles CLOSEST to the rating (window_s = 3 s
        non-overlapping tiles, so 30 s → nearest 10 tiles), ranked by |tile_t − rating_t| regardless
        of whether they fall before or after the rating, then takes their per-band nan-median. So the
        slider dictates "how many seconds of the nearest TD signal to aggregate," not a search radius.

    REUSE flag (per modality, independent of the two windows above):
      * STRICT (allow_window_reuse=False, default): each eligible window is assigned to its single
        NEAREST PRO within ±tol_s (searchsorted, ties → earlier PRO), so no TD tile or PSD event is
        reused across >1 PRO. The TD nearest-N cap is then applied within each PRO's owned tiles.
      * REUSE (allow_window_reuse=True): each PRO independently gathers EVERY eligible window within
        ±tol_s (TD then capped to nearest-N), so one window may serve several overlapping PROs.
      The per-modality non-reuse property is independent of this flag: TD and PSD are matched in
      separate passes, so a montage's TD tile and its co-timestamped device-PSD window can serve two
      different PROs in BOTH modes — the flag only governs reuse of the SAME window+modality.

      TD is PREFERRED over PSD within a PRO: a PRO that owns ≥1 ok TD tile is td_transform tier (its
      spectrum = the nan-median over its nearest-N TD tiles); only a PRO with zero eligible TD tiles
      falls to psd_bridge. A PSD event whose nearest PRO turned out TD-tier is left unused (reported).

    Returns (records, stats):
      records : list in pro_times order, each {"t","tier","lsb"[C linear|None],"calibrated"[C bool],
                "center_hz"[C],"used_s","saturated","reason","n_td_used","n_psd_used"}.
      stats   : {"n_pro","n_pro_td","n_pro_psd","n_pro_unmatched","n_td_windows","n_psd_windows",
                 "n_td_assigned","n_td_used","n_psd_assigned","n_psd_used","tol_s","td_quantity_s",
                 "td_n_epochs_cap","extent_s","psd_tol_s","allow_window_reuse"}.
                — n_td_assigned (eligible TD tiles owned within ±tol_s) minus n_td_used (after the
                nearest-N quantity cap) is the count of eligible TD tiles dropped by the slider cap.
    """
    # Back-compat: the old API passed extent_s (a ±half-window) and psd_tol_s. The new API passes
    # tol_s (main eligibility) + td_quantity_s (TD quantity). If only the legacy args arrived, map
    # them so old callers keep working: extent_s → both tol_s (its full width) and td_quantity_s.
    if tol_s is None:
        tol_s = (psd_tol_s if psd_tol_s is not None
                 else (float(extent_s) if extent_s is not None
                       else analytics.TRANSFORM_CENTERED_EXTENT_SECONDS))
    if td_quantity_s is None:
        td_quantity_s = (float(extent_s) if extent_s is not None
                         else analytics.TRANSFORM_CENTERED_EXTENT_SECONDS)
    tol_s = float(tol_s)
    td_quantity_s = float(td_quantity_s)
    centers = np.atleast_1d(np.asarray(raw_cache.get("centers_hz"), dtype=float))
    nC = centers.size
    window_s = float(raw_cache.get("window_s") or analytics.RAW_LSB_WINDOW_SECONDS)
    # TD quantity cap: how many nearest 3 s tiles to aggregate. round(quantity / window_s), >=1 so a
    # sub-tile quantity still keeps the single closest tile. PSD has no quantity cap (median over all
    # eligible events within tol_s).
    td_n_epochs_cap = max(1, int(round(td_quantity_s / window_s))) if window_s > 0 else 1
    lo_hz = float(analytics.LSB_VALIDATED_HZ_LO)
    hi_hz = float(analytics.LSB_DEPLOYABLE_HZ_HI)
    cal_band = (centers >= lo_hz - 1e-9) & (centers <= hi_hz + 1e-9)

    pro = np.atleast_1d(np.asarray(pro_times, dtype=float))
    nP = pro.size
    order = np.argsort(pro, kind="stable")
    pro_sorted = pro[order]

    none_vec = [None] * nC
    recs = [{"t": float(tp), "tier": None, "lsb": list(none_vec),
             "calibrated": [False] * nC, "center_hz": [float(c) for c in centers],
             "used_s": 0.0, "saturated": False, "reason": "", "n_td_used": 0, "n_psd_used": 0}
            for tp in pro]

    def _nearest_pro(win_t, tol):
        """Vectorized nearest-PRO index (orig order) per window time, -1 if beyond tol."""
        if win_t.size == 0 or nP == 0:
            return np.full(win_t.size, -1, dtype=int)
        pos = np.searchsorted(pro_sorted, win_t)
        left = np.clip(pos - 1, 0, nP - 1)
        right = np.clip(pos, 0, nP - 1)
        dl = np.abs(win_t - pro_sorted[left])
        dr = np.abs(win_t - pro_sorted[right])
        take_left = dl <= dr                       # tie -> earlier PRO (deterministic)
        nn_sorted = np.where(take_left, left, right)
        dist = np.where(take_left, dl, dr)
        nn = order[nn_sorted]
        nn[dist > tol] = -1
        return nn

    def _windows_in_extent(win_t, valid_mask, tol):
        """REUSE mode: per-PRO list of window indices whose |t - pro_t| <= tol (a window may appear
        under several PROs). Vectorized via searchsorted bounds on the sorted window times — O(W log W
        + total matches), not the O(P·W) full outer product. Returns a list-of-arrays indexed by ORIG
        PRO order, each holding ORIG window indices."""
        out = [np.empty(0, dtype=int) for _ in range(nP)]
        if nP == 0 or win_t.size == 0:
            return out
        vi = np.where(valid_mask)[0]                  # orig window indices that are valid
        if vi.size == 0:
            return out
        wt = win_t[vi]
        wo = np.argsort(wt, kind="stable")
        wt_sorted = wt[wo]
        vi_sorted = vi[wo]
        lo_idx = np.searchsorted(wt_sorted, pro - tol, side="left")
        hi_idx = np.searchsorted(wt_sorted, pro + tol, side="right")
        for p in range(nP):
            a, b = int(lo_idx[p]), int(hi_idx[p])
            if b > a:
                out[p] = vi_sorted[a:b]
        return out

    # ---- TD assignment ---------------------------------------------------------------------------
    td = raw_cache.get("td") or {}
    td_t = np.atleast_1d(np.asarray(td.get("t") or [], dtype=float))
    td_ok = np.atleast_1d(np.asarray(td.get("ok") or [], dtype=bool))
    td_mat = _lsb_family_mat(td, nC)
    n_td_windows = int(td_t.size)
    td_valid = (td_ok if td_ok.size == td_t.size else np.zeros(td_t.size, bool)) & np.isfinite(td_t)
    # TD ELIGIBILITY uses tol_s (the main slider), NOT the quantity slider. STRICT: each eligible tile
    # -> its single nearest PRO within +/-tol_s (nn_td). REUSE: each PRO -> every eligible tile within
    # +/-tol_s (td_sel_by_pro); a tile may then appear under multiple PROs. The QUANTITY cap
    # (td_n_epochs_cap = nearest-N tiles by |dt|) is applied per-PRO below, AFTER eligibility.
    if allow_window_reuse:
        td_sel_by_pro = _windows_in_extent(td_t, td_valid, tol_s)
        n_td_assigned = int(sum(s.size for s in td_sel_by_pro))
    else:
        nn_td = np.full(td_t.size, -1, dtype=int)
        if td_valid.any():
            nn_td[td_valid] = _nearest_pro(td_t[td_valid], tol_s)
        n_td_assigned = int((nn_td >= 0).sum())

    n_td_used = 0
    td_tier_pro = np.zeros(nP, dtype=bool)
    for p in range(nP):
        sel = td_sel_by_pro[p] if allow_window_reuse else np.where(nn_td == p)[0]
        if sel.size == 0:
            continue
        # QUANTITY CAP: of this PRO's eligible tiles, keep only the td_n_epochs_cap CLOSEST to the
        # rating (by |tile_t - pro_t|, before/after agnostic). This is the "how much TD signal to use"
        # slider: 30 s -> nearest 10 non-overlapping 3 s tiles -> their median. Ties on |dt| break to
        # the earlier tile (stable argsort) so the choice is deterministic.
        if sel.size > td_n_epochs_cap:
            dt = np.abs(td_t[sel] - pro[p])
            keep = np.argsort(dt, kind="stable")[:td_n_epochs_cap]
            sel = sel[np.sort(keep)]                  # keep original tile order for a stable median
        med = np.nanmedian(td_mat[sel], axis=0)
        rec = recs[p]
        rec["tier"] = PRO_LSB_TIER_TD
        rec["lsb"] = [float(v) if np.isfinite(v) else None for v in med]
        rec["calibrated"] = [bool(np.isfinite(v)) for v in med]   # TD k is band-agnostic-calibrated
        rec["n_td_used"] = int(sel.size)
        rec["used_s"] = float(sel.size * window_s)
        rec["reason"] = ("live TD->LSB median over nearest %d of %d eligible tile(s) "
                         "(<=%.0fs signal within +/-%.0fs tol, k=%.2f)"
                         % (sel.size, (td_sel_by_pro[p].size if allow_window_reuse
                                       else int((nn_td == p).sum())),
                            td_quantity_s, tol_s, analytics.LSB_PER_UV2_TRANSFORM))
        td_tier_pro[p] = True
        n_td_used += int(sel.size)

    # ---- PSD assignment (only PROs with no TD become psd_bridge) ----------------------------------
    psd = raw_cache.get("psd") or {}
    psd_t = np.atleast_1d(np.asarray(psd.get("t") or [], dtype=float))
    psd_mat = _lsb_family_mat(psd, nC)
    n_psd_windows = int(psd_t.size)
    psd_valid = np.isfinite(psd_t)
    # PSD ELIGIBILITY also uses tol_s (the main slider) — the ONLY PSD control. No quantity cap: a
    # PRO's PSD-bridge LSB is the nan-median over EVERY eligible PSD event within +/-tol_s.
    if allow_window_reuse:
        psd_sel_by_pro = _windows_in_extent(psd_t, psd_valid, tol_s)
        n_psd_assigned = int(sum(s.size for s in psd_sel_by_pro))
    else:
        nn_psd = np.full(psd_t.size, -1, dtype=int)
        if psd_valid.any():
            nn_psd[psd_valid] = _nearest_pro(psd_t[psd_valid], tol_s)
        n_psd_assigned = int((nn_psd >= 0).sum())

    n_psd_used = 0
    for p in range(nP):
        if td_tier_pro[p]:
            continue                                  # TD preferred — PSD here stays unused
        sel = psd_sel_by_pro[p] if allow_window_reuse else np.where(nn_psd == p)[0]
        if sel.size == 0:
            continue
        med = np.nanmedian(psd_mat[sel], axis=0)
        rec = recs[p]
        rec["tier"] = PRO_LSB_TIER_BRIDGE
        rec["lsb"] = [float(v) if np.isfinite(v) else None for v in med]
        rec["calibrated"] = [bool(np.isfinite(v) and cal_band[i]) for i, v in enumerate(med)]
        rec["n_psd_used"] = int(sel.size)
        rec["reason"] = ("live PSD->LSB median over %d event(s) within +/-%.0fs (k=%.2f); "
                         "calibrated only in [%.1f,%.1f] Hz"
                         % (sel.size, tol_s, analytics.LSB_PER_DEVICE_PSD, lo_hz, hi_hz))
        n_psd_used += int(sel.size)

    n_pro_td = int(td_tier_pro.sum())
    n_pro_psd = int(sum(1 for r in recs if r["tier"] == PRO_LSB_TIER_BRIDGE))
    stats = {"n_pro": int(nP), "n_pro_td": n_pro_td, "n_pro_psd": n_pro_psd,
             "n_pro_unmatched": int(nP - n_pro_td - n_pro_psd),
             "n_td_windows": n_td_windows, "n_psd_windows": n_psd_windows,
             "n_td_assigned": n_td_assigned, "n_td_used": n_td_used,
             "n_psd_assigned": n_psd_assigned, "n_psd_used": n_psd_used,
             "tol_s": tol_s, "td_quantity_s": td_quantity_s, "td_n_epochs_cap": int(td_n_epochs_cap),
             # legacy aliases kept so existing UI/echo readers don't KeyError:
             "extent_s": td_quantity_s, "psd_tol_s": tol_s,
             "allow_window_reuse": bool(allow_window_reuse)}
    return recs, stats
