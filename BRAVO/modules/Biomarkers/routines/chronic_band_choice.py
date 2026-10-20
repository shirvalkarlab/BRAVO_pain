"""The chronic log as the main source of band choice (wave 2, C5; the PI, 2026-10-18: "the chronic
log may choose").

WHAT THE CHRONIC LOG IS. The device's own band power, one reading every 10 minutes, all day, at
home, on the contact pair and at the frequency its chronic sensing was set to (the "chronic log",
`MedtronicChronicBrainSense`). Each reading is the device's value at face value (raw LSB, never
rescaled, never logged; CLAUDE.md rule 13).

WHAT THIS DOES. For each sensing contact pair and each chronic sensing frequency the log was set
to on that pair, every pain report is given the ONE chronic reading whose 10-minute average covers
the time it was filed (the PI, 2026-10-19; `covering_reports`, `CHRONIC_MATCH_DEFAULT`); a report
in a gap of the log has none and is counted. The page may switch to the heat map's own matching
window (the median of the readings in it), and the answer then carries a warning that the covering
10-minute average is the recommended default (`CHRONIC_MATCH_WINDOW`, `NON_DEFAULT_WARNING`).
Then:
  * Pearson r between that value and the pain score, over the reports that have one;
  * its interval, by the heat map's own method (`analytics._block_boot_r_interval`: whole reports
    resampled in blocks sized by the pain series' own persistence, decision 183);
  * its rotation p (the exact rotation of the pain series against the band power, decision 315);
  * the current-removed check (decision 484): a WARNING ONLY. It moves no answer, no choice and no
    verdict (the PI, 2026-10-18).
Each chronic frequency is put on the heat map's nearest band centre when it is less than 0.5 Hz
away (24.41 Hz, snapped by the device's FFT bins to 24.4, goes to the 24.5 Hz centre); a frequency
with no centre that close is reported and put on no band.

WHERE EACH READING'S PAIR, BAND AND CURRENT COME FROM. Never derived here. The pair and band are
the ones the chronic log's own schedule files the reading under (decision 461, `representation.
chronic_pair_keys`/`chronic_band_tags`), after the merge of copies and the filing of each reading
under the lead its signal came from (decisions 480, 487, 488: `representation.
merge_chronic_repeats`, which the Biomarkers loader applies), read through `representation.
native_lsb_by_channel`, chronic source only. A reading on another contact pair never counts for
this pair (rule 13: never pool across electrodes). The current is the reading's OWN lead's: the
lead's chronic current series (`availability.stim_series(hemisphere=)`, which reads back
`OtherLeadCurrentMilliAmps` so a lead keeps its own current when its log held the other lead's
signal, decision 488), at the reading's time.

THE DEPARTURE FROM CLAUDE.md SECTION 10. Section 10 says clinic ratings choose and home ratings
confirm. Here the home log, matched to the same pain series the heat map uses, may choose a band:
the PI's ruling of 2026-10-18 ("the chronic log may choose"). With the default settings that pain
series is the participant's REDCap surveys; the clinic sheets' ratings join it only when the
clinic-sheet switch is on (decision 186), exactly as for the heat map.

HOW CHRONIC DECIDES. A band is "covered" on a pair when a chronic frequency maps to its centre AND
the chronic log gives an assessable answer there (at least `MIN_REPORTS` reports matched). On a
covered band the TD-only grid's row says `choice_source: "chronic"`, and every reader that chooses
a band (through `sweep_settings.choosing_sweep`) reads the chronic correlation, interval and answer
in place of TD's, with TD's own kept beside them (`td_values`). Elsewhere `choice_source` is "TD".
PSD-only rows never choose (the PI, 2026-10-18). The chronic log answers the correlation only: the
high-versus-low area under the curve stays TD's.

No Django: the caller hands in the loaded recordings and the pain series.
"""
from __future__ import annotations

import zlib

import numpy as np

from . import analytics
from .stats_utils import rotations

try:                                                     # the container's spelling, then the host's
    from modules.DecodeCommon import representation as _repr
except ImportError:                                      # pragma: no cover
    from DecodeCommon import representation as _repr

#: HOW A PAIN REPORT MEETS THE CHRONIC LOG (the PI, 2026-10-19: "Make it the 10 min average covering
#: it, but the page setting can change it with a warning that these are recommended default
#: settings"). "covering", the default: the ONE chronic reading whose 10-minute average contains the
#: report's time; the heat map's window does not change it. "window": every chronic reading within
#: the heat map's matching window, their median (the first C5 build), carrying `NON_DEFAULT_WARNING`.
CHRONIC_MATCH_COVERING = "covering"
CHRONIC_MATCH_WINDOW = "window"
CHRONIC_MATCH_DEFAULT = CHRONIC_MATCH_COVERING
CHRONIC_MATCH_CHOICES = (CHRONIC_MATCH_COVERING, CHRONIC_MATCH_WINDOW)
#: The chronic log's averaging period, in seconds (Medtronic: "the average value measured over a 10
#: minute interval", not configurable; DEVICE_percept_rc.md).
CHRONIC_PERIOD_S = 600.0
#: Source interpretation: each chronic timestamp starts its ten-minute average,
#: so a reading stamped s covers [s, s + 600 s). This is Prasad's empirical
#: interpretation, not a manufacturer-certified timing guarantee. Participant
#: measurements supporting it remain in private source provenance. Do not treat
#: this import or its synthetic tests as independent device validation.
#: The next reading owns the exact upper boundary; overlapping intervals use
#: the latest start, as documented in covering_reports.
NON_DEFAULT_WARNING = (
    "Not the recommended default: this home-record answer pairs each pain report with the chronic "
    "readings within the page's matching window ({window}). The recommended default pairs each "
    "report with the one 10-minute chronic average that covers the time it was filed.")


def non_default_warning(chronic_match, tol_s):
    """The warning a non-default chronic match carries, or None for the default."""
    if chronic_match == CHRONIC_MATCH_DEFAULT:
        return None
    return NON_DEFAULT_WARNING.format(window=f"{float(tol_s) / 60.0:g} minutes either side")


def covering_reports(report_t, sample_t, period_s=CHRONIC_PERIOD_S):
    """``(owned, in_gap)``: for each report, ``[j]`` for the one reading whose averaging period
    ``[s_j, s_j + period_s)`` contains the report's time (the latest-starting one, should two
    overlap), else ``[]``; and per report whether it falls inside the readings' span
    (first start to last start + period) with no covering reading among these readings.
    `chronic_band_choice` splits those into a gap in the log (no reading of the lead, on any
    contact pair or frequency, covers it: ``n_reports_in_gap``) and the log sensing another pair or
    frequency at the time (``n_reports_log_elsewhere``)."""
    rt = np.asarray(report_t, dtype=float)
    st = np.asarray(sample_t, dtype=float)
    owned = [[] for _ in range(rt.size)]
    in_gap = np.zeros(rt.size, dtype=bool)
    if rt.size == 0 or st.size == 0:
        return owned, in_gap
    order = np.argsort(st, kind="stable")
    ss = st[order]
    k = np.searchsorted(ss, rt, side="right") - 1          # latest start at or before the report
    for i in range(rt.size):
        if k[i] >= 0 and rt[i] < ss[k[i]] + float(period_s):
            owned[i] = [int(order[k[i]])]
        elif ss[0] <= rt[i] < ss[-1] + float(period_s):
            in_gap[i] = True
    return owned, in_gap


#: A chronic frequency goes on a band centre only when it is LESS than this far from it, in Hz.
MAX_CENTRE_GAP_HZ = 0.5
#: Reports with a chronic value needed before the chronic log gives an answer at a band (the same
#: minimum the heat map's own interval needs, `_best_rows_correlation`).
MIN_REPORTS = 8
#: Words on a row whose band the chronic log does not reach.
NO_HOME_RECORD = "no home record at this band"
CHOICE_CHRONIC = "chronic"
CHOICE_TD = "TD"
CHOICE_NONE = "none"
#: How the chronic answer is formed, stated on every block, per way of matching.
METHOD_COVERING = (
    "each pain report takes the one chronic (10-minute) band-power reading whose 10 minutes cover "
    "the time it was filed (a reading's time is the start of its 10 minutes), on this contact pair "
    "and frequency, the device's value at face value; a report in a gap of the log has none and is "
    "counted; Pearson r against the pain score; interval: whole reports resampled in blocks (the "
    "heat map's method); p: every other rotation of the pain series once; the current-removed check "
    "is a warning only")
METHOD = (
    "each pain report takes the median of the chronic (10-minute) band-power readings in its "
    "matching window on this contact pair and frequency, the device's values at face value; "
    "Pearson r against the pain score; interval: whole reports resampled in blocks (the heat map's "
    "method); p: every other rotation of the pain series once; the current-removed check is a "
    "warning only")
METHOD_FOR = {"covering": METHOD_COVERING, "window": METHOD}


def _canon(name):
    u = str(name).upper().replace("_AND_", "_")
    return u[:-len("_RING")] if u.endswith("_RING") else u


def side_of_pair(pair):
    """"Left" / "Right" for a pair key like ``ONE_THREE_LEFT``, else None."""
    u = str(pair or "").upper()
    if u.endswith("LEFT"):
        return "Left"
    if u.endswith("RIGHT"):
        return "Right"
    return None


def grid_centre_for(freq_hz, centres, max_gap_hz=MAX_CENTRE_GAP_HZ):
    """The band centre nearest ``freq_hz`` when it is less than ``max_gap_hz`` away, else None."""
    try:
        f = float(freq_hz)
    except (TypeError, ValueError):
        return None
    c = np.asarray([float(x) for x in (centres or [])], dtype=float)
    if not np.isfinite(f) or c.size == 0:
        return None
    i = int(np.argmin(np.abs(c - f)))
    return float(c[i]) if abs(float(c[i]) - f) < float(max_gap_hz) else None


def chronic_samples_by_pair(chronic_recordings, powerdomain_recordings=None):
    """``{pair: {"t", "y", "freq_hz"}}``: the chronic readings as `representation.
    native_lsb_by_channel` files them (its contact pair and band, its order), chronic source only,
    finite values only (the merge's blanked zeros and invalid codes are NaN and left out)."""
    native = _repr.native_lsb_by_channel(list(chronic_recordings or []),
                                         list(powerdomain_recordings or []))
    out = {}
    for ch, d in (native or {}).items():
        src = np.asarray(d.get("source") or [], dtype=object)
        keep = src == "chronic"
        if not keep.any():
            continue
        t = np.asarray(d["t"], dtype=float)[keep]
        y = np.asarray(d["y"], dtype=float)[keep]
        hz = np.asarray([np.nan if h is None else float(h) for h in
                         np.asarray(d["center_hz"], dtype=object)[keep]], dtype=float)
        ok = np.isfinite(t) & np.isfinite(y)
        key = _canon(ch)
        prev = out.get(key)
        if prev is not None:                       # two spellings of one pair: one entry
            t = np.concatenate([prev["t"], t[ok]]); y = np.concatenate([prev["y"], y[ok]])
            hz = np.concatenate([prev["freq_hz"], hz[ok]])
            out[key] = {"t": t, "y": y, "freq_hz": hz}
        else:
            out[key] = {"t": t[ok], "y": y[ok], "freq_hz": hz[ok]}
    return out


def lead_currents(chronic_recordings):
    """``{"Left": {"t", "y"}, "Right": {...}}``: each lead's own chronic current series
    (`availability.stim_series(hemisphere=)`, decision 488)."""
    from . import availability
    return {side: availability.stim_series(chronic_recordings, hemisphere=side)
            for side in ("Left", "Right")}


def current_at_times(times, series):
    """The lead's current at each of ``times``: the median of its values recorded at exactly that
    time when there are any, else the last at or before it, else NaN (before the first, unknown,
    never zero). Returns ``(values, n_times_with_two_currents)``."""
    times = np.asarray(times, dtype=float)
    out = np.full(times.shape, np.nan)
    st = np.asarray((series or {}).get("t") or [], dtype=float)
    sy = np.asarray((series or {}).get("y") or [], dtype=float)
    if times.size == 0 or st.size == 0:
        return out, 0
    order = np.argsort(st, kind="stable")
    st, sy = st[order], sy[order]
    lo = np.searchsorted(st, times, side="left")
    hi = np.searchsorted(st, times, side="right")
    n_two = 0
    for i in range(times.size):
        if hi[i] > lo[i]:
            vals = sy[lo[i]:hi[i]]
            out[i] = float(np.median(vals))
            n_two += int(np.unique(np.round(vals, 6)).size > 1)
        elif hi[i] > 0:
            out[i] = float(sy[hi[i] - 1])
    return out, n_two


def match_reports(report_t, sample_t, *, tol_s, match_direction="nearest", allow_window_reuse=False):
    """For each report, the indices of the chronic readings it owns: those within ``tol_s`` of it
    (at or before it only under "prior"). Without window reuse a reading belongs to the one report
    nearest it (the earlier on a tie), as the heat map's matcher counts one stretch of recording for
    one report (`sweep_settings.DEFAULT_ALLOW_WINDOW_REUSE`)."""
    rt = np.asarray(report_t, dtype=float)
    stt = np.asarray(sample_t, dtype=float)
    owned = [[] for _ in range(rt.size)]
    if rt.size == 0 or stt.size == 0:
        return owned
    prior = str(match_direction).lower() == "prior"
    r_order = np.argsort(rt, kind="stable")
    rs = rt[r_order]
    for j in np.argsort(stt, kind="stable"):
        s = stt[j]
        # reports within the window of this reading
        lo = np.searchsorted(rs, s - (0.0 if prior else tol_s), side="left")
        hi = np.searchsorted(rs, s + tol_s, side="right")
        cand = [k for k in range(lo, hi) if (rs[k] - s) <= tol_s and (s - rs[k]) <= tol_s
                and (not prior or s <= rs[k])]
        if not cand:
            continue
        if allow_window_reuse:
            for k in cand:
                owned[int(r_order[k])].append(int(j))
        else:
            k = min(cand, key=lambda k: (abs(rs[k] - s), rs[k], k))
            owned[int(r_order[k])].append(int(j))
    return owned


def _rotation_p(x, y, rng):
    """Two-sided exact rotation p of r(x, y), y slid along x by every other shift once."""
    n = x.size
    R = rotations(n, n - 1, rng)
    if R.shape[0] == 0:
        return None, 0
    xc = x - x.mean()
    Yr = y[R]
    Yc = Yr - Yr.mean(axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        rk = (Yc @ xc) / np.sqrt((Yc * Yc).sum(axis=1) * float((xc * xc).sum()))
        yc = y - y.mean()
        r0 = float((xc * yc).sum() / np.sqrt((xc * xc).sum() * (yc * yc).sum()))
    if not np.isfinite(r0):
        return None, int(R.shape[0])
    return float((int(np.sum(np.abs(rk) >= abs(r0))) + 1) / (R.shape[0] + 1)), int(R.shape[0])


def answer_for(x, y, cov, *, n_boot, seed, key):
    """The chronic answer on one (pair, frequency): r, interval, rotation p, the answer word and the
    current-removed check (warning only). ``x`` the report's chronic value, ``y`` its pain score,
    ``cov`` its current, in time order. Its own generators, from ``seed`` and ``key``."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    cov = np.asarray(cov, float) if cov is not None else np.full(x.size, np.nan)
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    out = {"n_reports": n, "pearson_r": None, "pearson_r_low": None, "pearson_r_high": None,
           "p_rotation": None, "n_rotations": 0, "answer": analytics.BAND_PAIN_NOT_ASSESSED,
           "current_removed_check": None}
    if n < MIN_REPORTS:
        out["why"] = f"{n} pain reports have a chronic reading in their window, fewer than {MIN_REPORTS}"
        return out
    xm, ym = x[m], y[m]
    if np.ptp(xm) == 0 or np.ptp(ym) == 0:
        out["why"] = "band power or pain does not vary over the matched reports"
        return out
    r = float(np.corrcoef(xm, ym)[0, 1])
    lo, hi = analytics._block_boot_r_interval(
        xm.copy(), ym.copy(), n_boot=int(n_boot),
        rng=np.random.default_rng([int(seed), 5, *key, 1]))
    p, n_rot = _rotation_p(xm, ym, np.random.default_rng([int(seed), 5, *key, 2]))
    resolved = (lo is not None and hi is not None and (lo > 0 or hi < 0)
                and p is not None and p <= 0.05)
    out.update({"pearson_r": r, "pearson_r_low": lo, "pearson_r_high": hi, "p_rotation": p,
                "n_rotations": n_rot,
                "answer": (analytics.BAND_PAIN_ESTABLISHED if resolved
                           else (analytics.BAND_PAIN_NOT_RESOLVED if lo is not None
                                 else analytics.BAND_PAIN_NOT_ASSESSED)),
                "direction": ("band power rises as pain rises" if r > 0
                              else "band power falls as pain rises")})
    # A WARNING ONLY (decision 484; the PI, 2026-10-18): computed and shown, never read by the answer.
    out["current_removed_check"] = analytics._current_removed_check(
        x[m], y[m], cov[m], r_plain=r, n_boot=int(n_boot),
        rng=np.random.default_rng([int(seed), 5, *key, 3]))
    # The shared check also serves TD grids, whose candidate-piece scope differs.
    # Describe this caller's actual covariate rather than inheriting that TD caption.
    out["current_removed_check"]["current_scope"] = (
        "own-lead current at the matched chronic readings; median within a non-default window; "
        "last prior current only when an exact-time value is absent; missing stays unknown")
    out["current_removed_check"]["what"] = analytics.CURRENT_REMOVED_CHECK_WHAT
    return out


def chronic_band_choice(samples_by_pair, currents_by_side, report_t, pain, *, centres, tol_s,
                        match_direction="nearest", allow_window_reuse=False, n_boot=None, seed=0,
                        pairs=None, chronic_match=CHRONIC_MATCH_DEFAULT, daily_swing=False):
    """``{pair: block}`` for every pair in ``pairs`` (default: every pair the chronic log holds).

    ``block``: ``{"frequencies": [one entry per chronic frequency on the pair], "by_centre":
    {centre: the entry put on that centre}, ...}``. Each entry: the frequency, its band centre (or
    None), the readings on the pair at that frequency (count, first and last time), the reports
    matched, and `answer_for`'s fields; ``covered`` says whether it may decide its band.

    ``chronic_match`` "covering" (the default) pairs each report with the one reading whose 10
    minutes cover it (`covering_reports`; ``tol_s``, ``match_direction`` and ``allow_window_reuse``
    are not read); "window" with the median of the readings in the heat map's window
    (`match_reports`), and every block and entry then carries the non-default warning.

    ``daily_swing`` (wave 2, C6; a warning only): each entry also carries `daily_swing.swing_block`,
    the hourly profile of ALL the readings at that frequency on the pair and the hours of day of
    the reports its answer used. It reads nothing the answer reads and moves no number. False (the
    neutral setting) skips it."""
    if chronic_match not in CHRONIC_MATCH_CHOICES:
        raise ValueError(f"chronic_match must be one of {CHRONIC_MATCH_CHOICES}, got {chronic_match!r}")
    warning = non_default_warning(chronic_match, tol_s)
    n_boot = analytics.BAND_TIME_SWEEP_N_BOOT if n_boot is None else int(n_boot)
    rt_all = np.asarray(report_t, dtype=float)
    pain_all = np.asarray(pain, dtype=float)
    order = np.argsort(rt_all, kind="stable")        # time order, for the rotation and the blocks
    rt, py = rt_all[order], pain_all[order]
    has_pain = np.isfinite(py) & np.isfinite(rt)
    rt, py = rt[has_pain], py[has_pain]
    centres = [float(c) for c in (centres or [])]
    want = list(samples_by_pair) if pairs is None else [_canon(p) for p in pairs]
    out = {}
    for pair in want:
        d = samples_by_pair.get(pair)
        side = side_of_pair(pair)
        block = {"pair": pair, "side": side, "frequencies": [], "by_centre": {},
                 "n_readings": 0, "chronic_match": chronic_match,
                 "method": METHOD_FOR[chronic_match]}
        if warning:
            block["warning"] = warning
        if not d or not np.asarray(d["t"]).size:
            block["why"] = "the chronic log holds no reading on this contact pair"
            out[pair] = block
            continue
        t, y, hz = (np.asarray(d[k], dtype=float) for k in ("t", "y", "freq_hz"))
        block["n_readings"] = int(t.size)
        # which reports this LEAD's log covers at all (any contact pair, any frequency): a report
        # inside one frequency's span with no reading of its own is in a gap of the log only when
        # no reading of this lead covers it; otherwise the log was sensing another pair or frequency
        lead_t = np.concatenate([np.asarray(v["t"], dtype=float) for k, v in samples_by_pair.items()
                                 if side_of_pair(k) == side and np.asarray(v["t"]).size] or [t])
        covered_any = np.asarray([bool(o) for o in covering_reports(rt, lead_t)[0]], dtype=bool)
        series = (currents_by_side or {}).get(side) if side else None
        for f in sorted({float(v) for v in hz[np.isfinite(hz)]}):
            sel = hz == f
            ts, ys = t[sel], y[sel]
            centre = grid_centre_for(f, centres)
            if chronic_match == CHRONIC_MATCH_COVERING:
                owned, in_gap = covering_reports(rt, ts)
            else:
                owned = match_reports(rt, ts, tol_s=float(tol_s), match_direction=match_direction,
                                      allow_window_reuse=allow_window_reuse)
                in_gap = None
            cur_s, n_two = current_at_times(ts, series)
            xv = np.full(rt.size, np.nan)
            cv = np.full(rt.size, np.nan)
            n_span = 0
            for i, js in enumerate(owned):
                if js:
                    xv[i] = float(np.median(ys[js]))
                    c = cur_s[js]
                    c = c[np.isfinite(c)]
                    if c.size:
                        cv[i] = float(np.median(c))
                        n_span += int(np.unique(np.round(c, 6)).size > 1)
            # its own generators, from the pair's name and the frequency: no answer depends on
            # which other pairs or frequencies were worked out, or in what order
            key = (zlib.crc32(pair.encode("utf8")) & 0x7FFFFFFF, int(round(f * 100)))
            ans = answer_for(xv, py, cv, n_boot=n_boot, seed=seed, key=key)
            used = sorted({j for js in owned for j in js})
            entry = {"freq_hz": f, "grid_centre_hz": centre,
                     "centre_gap_hz": (None if centre is None else round(abs(centre - f), 6)),
                     "n_readings": int(ts.size),
                     "first_reading_s": float(ts.min()), "last_reading_s": float(ts.max()),
                     "n_readings_matched": int(len(used)),
                     "first_matched_report_s": (float(rt[np.isfinite(xv)].min())
                                                if np.isfinite(xv).any() else None),
                     "last_matched_report_s": (float(rt[np.isfinite(xv)].max())
                                               if np.isfinite(xv).any() else None),
                     "n_reports_in_gap": (None if in_gap is None
                                          else int((in_gap & ~covered_any).sum())),
                     "n_reports_log_elsewhere": (None if in_gap is None
                                                 else int((in_gap & covered_any).sum())),
                     "chronic_match": chronic_match,
                     **({"warning": warning} if warning else {}),
                     "n_reports_spanning_two_currents": int(n_span),
                     "n_readings_with_two_currents": int(n_two),
                     "n_readings_without_current": int(np.sum(~np.isfinite(cur_s))),
                     "current_from": (f"the {side} lead's own chronic current series"
                                      if side else None),
                     **ans}
            entry["covered"] = bool(centre is not None and ans["n_reports"] >= MIN_REPORTS
                                    and ans["pearson_r"] is not None)
            if daily_swing:
                from . import daily_swing as _ds
                used_r = np.isfinite(xv) & np.isfinite(py)
                entry["daily_swing"] = _ds.swing_block(_ds.hourly_profile(ts, ys),
                                                       _ds.report_hours(rt[used_r]), freq_hz=f)
            block["frequencies"].append(entry)
            if centre is not None:
                prev = block["by_centre"].get(centre)
                # two chronic frequencies on one centre: the nearer, then the one with more reports
                if prev is None or (entry["centre_gap_hz"], -entry["n_reports"]) < (
                        prev["centre_gap_hz"], -prev["n_reports"]):
                    block["by_centre"][centre] = entry
        out[pair] = block
    return out


def row_block(pair_block, centre):
    """The ``chronic`` block one grid row carries, for its band ``centre``."""
    if (pair_block or {}).get("status") == "read_failed":
        return {"covered": False, "n_reports": None, "status": "read_failed",
                "words": "chronic recordings could not be read completely; band selection unavailable"}
    entry = ((pair_block or {}).get("by_centre") or {}).get(float(centre)) if centre is not None \
        else None
    if entry is None:
        return {"covered": False, "n_reports": 0, "words": NO_HOME_RECORD}
    keep = ("freq_hz", "grid_centre_hz", "centre_gap_hz", "n_readings", "n_readings_matched",
            "first_reading_s", "last_reading_s", "first_matched_report_s", "last_matched_report_s",
            "n_reports", "pearson_r", "pearson_r_low", "pearson_r_high", "p_rotation",
            "n_rotations", "answer", "direction", "current_removed_check", "covered", "why",
            "n_reports_in_gap", "n_reports_log_elsewhere", "chronic_match", "warning",
            "daily_swing")
    out = {k: entry.get(k) for k in keep if k in entry}
    if not out["covered"]:
        out["words"] = (f"home record at this band too thin to decide: {out.get('why')}"
                        if out.get("why") else "home record at this band gives no answer")
    else:
        out["words"] = "decided by the home record (chronic log)"
    return out


#: Why an area-under-the-curve row stays TD's where the chronic log covers its band.
AUC_STAYS_TD = ("the home record (chronic log) answers the correlation only; the high-versus-low "
                "area under the curve stays TD's")


def label_rows(rows, pair_block, grid_source, *, correlation=True):
    """Put ``chronic`` and ``choice_source`` on each best row of one grid, in place. TD correlation
    rows: "chronic" where the chronic log covers the band, else "TD"; TD area-under-the-curve rows:
    "TD" (the chronic log gives no such value); mixed and PSD-only rows: "none" (they never choose)."""
    from . import sweep_settings as _sw
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        r["chronic"] = row_block(pair_block, r.get("band_center_hz"))
        if r["chronic"].get("status") == "read_failed":
            r["choice_source"] = CHOICE_NONE
            r["can_choose_band"] = False
            r["choice_source_why"] = r["chronic"]["words"]
        elif grid_source != _sw.GRID_SOURCE_TD:
            r["choice_source"] = CHOICE_NONE
        elif not correlation:
            r["choice_source"] = CHOICE_TD
            if r["chronic"]["covered"]:
                r["choice_source_why"] = AUC_STAYS_TD
        else:
            r["choice_source"] = CHOICE_CHRONIC if r["chronic"]["covered"] else CHOICE_TD
    return rows


def attach_daily_swing(rows, pair_block):
    """Complete ``daily_swing`` on each best correlation row of one grid, in place (wave 2, C6; a
    warning only). The row already holds the hours of day of its own reports (`analytics.
    _attach_report_hours`); this adds the chronic log's daily profile on the row's contact pair at
    the chronic frequency put on the row's band centre (the same mapping that decides which chronic
    answer a band carries, `by_centre`), the status, and the warning, appended to the row's `why`.
    No profile there: "no home record at this band", the profile and ratio None, the report hours
    kept. Reads and changes nothing else on the row."""
    from . import daily_swing as _ds
    by_centre = (pair_block or {}).get("by_centre") or {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        hours = (r.get("daily_swing") or {}).get("report_hours")
        c = r.get("band_center_hz")
        entry = by_centre.get(float(c)) if c is not None else None
        ent_ds = (entry or {}).get("daily_swing")
        if ent_ds is None or ent_ds.get("status") != _ds.STATUS_MEASURED:
            r["daily_swing"] = _ds.swing_block(None, hours)
        else:
            profile = {k: ent_ds.get(k) for k in ("hourly_median", "n_readings_by_hour", "ratio",
                                                  "hour_high", "hour_low", "n_readings", "n_days")}
            r["daily_swing"] = _ds.swing_block(profile, hours, freq_hz=ent_ds.get("chronic_freq_hz"))
        if r["daily_swing"].get("warning"):
            r["why"] = _ds.append_warning(r.get("why"), r["daily_swing"]["warning"])
    return rows
