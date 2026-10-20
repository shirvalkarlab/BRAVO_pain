"""Two readings of one titration session: the ramp with the current taken out, and the blind holds.

A titration session asks the same question twice, in two conditions that are not equivalent.

**The ramp.** The ladder steps the current on purpose. On this participant's record band power and
pain both move with the current, so a correlation between them across the ramp is partly the current
itself (measured 2026-09-22, decisions 232 and 234). The ramp is therefore read with the current
taken out of both quantities -- and the plain value is kept beside it, because a reader who is shown
only an adjusted number cannot see how much the adjustment did.

**The holds.** Three five-minute blocks, off / on / off, at one current, the patient not told which
(decision 230, part B). Nothing is being stepped, so a pain difference across the blocks is a pain
difference and not a dose axis in disguise. Its weakness is the opposite one: three blocks in one
afternoon, a handful of ratings each.

**Which is the reading.** The PI, 2026-09-22 (ruling 1 of decision 233): the current-stepped ramp
WITH the current term is the reading, and he wants the holds' reading computed beside it so the two
can be compared before he settles it for good. So both are produced, both are reported, and this
module says plainly which is which rather than quietly choosing.

Nothing here decides anything: no verdict, no gate, no band selection. It reads one visit.
"""
import numpy as np

try:                                                     # the two import spellings, one module
    from modules.Biomarkers.routines import stats_utils as _su
except ImportError:                                      # pragma: no cover - host spelling
    from Biomarkers.routines import stats_utils as _su

#: How many ladder steps before a correlation across them is worth printing at all. Below this the
#: answer is "too few steps", which is an answer; a correlation on four points is not.
MIN_RAMP_STEPS = 6

#: When this much of a band's movement across the ladder is the current itself, taking the current
#: out leaves almost nothing to correlate and the adjusted value is noise dressed as a number. Say
#: so instead: "this band is nearly the current itself here" is the finding, and it is a strong one.
#: Read from ``stats_utils`` rather than retyped, because the Closed-Loop page's band-power-to-pain
#: reading applies the same rule and two copies of one number drift apart (this project's cache had
#: two copies of one size limit that differed by a factor of four).
NEARLY_THE_CURRENT_R2 = _su.NEARLY_THE_COVARIATE_R2

#: Resamples behind every interval here. The unit resampled is the STEP for the ramp and the RATING
#: for the holds, because those are what the visit actually delivered independently of each other.
N_BOOT = 2000

#: WHAT ONE SESSION CAN AND CANNOT SETTLE. A ladder is about fifteen settled steps, and on fifteen
#: points a band carrying no pain relationship at all still lands beyond |r| 0.4 after the current is
#: taken out about one time in eight, with an interval that excludes zero about one time in fourteen
#: (measured on constructed ladders of this shape, 120 draws, 2026-09-22). So a ramp reading is a
#: reading of one visit, never a result established on its own -- the project's own rule from
#: `METHODS_measurement_and_findings.md` §7, said here because this is where it would be broken.
ONE_SESSION_CAVEAT = (
    "one visit: about fifteen settled steps, on which a band with no pain relationship still reads "
    "beyond 0.4 after the current is taken out roughly one time in eight, and clears zero roughly "
    "one time in fourteen, by chance alone. Read this as a lead to repeat, never as established")

#: The ruling this module implements, quoted where the answer is printed rather than paraphrased.
READING_WHY = ("the current-stepped ramp with the current term is the reading, and the fixed-current "
               "holds are computed beside it for comparison (the PI, 2026-09-22)")


def _f(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _arrays(steps, band):
    """(current, pain, power) for one band across the steps that carry all three."""
    cur, pain, pw = [], [], []
    for s in steps or ():
        c, p = _f((s or {}).get("current_mA")), _f((s or {}).get("pain"))
        v = _f(((s or {}).get("power_by_band") or {}).get(band))
        if v is None:                                    # tolerate a string key for the same centre
            v = _f(((s or {}).get("power_by_band") or {}).get(str(band)))
        if c is None or p is None or v is None:
            continue
        cur.append(c); pain.append(p); pw.append(v)
    return np.asarray(cur, float), np.asarray(pain, float), np.asarray(pw, float)


def _pearson(x, y):
    if x.size < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None
    r = float(np.corrcoef(x, y)[0, 1])
    return r if np.isfinite(r) else None


def _boot_ci(fn, n, rng, *, lo=2.5, hi=97.5):
    """A percentile interval from resampling the unit of observation with replacement.

    The steps of one ladder are not independent of each other -- neighbouring steps share minutes of
    the same visit -- so this interval is read as a spread, not as a coverage guarantee.
    """
    vals = []
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, size=n)
        v = fn(idx)
        if v is not None and np.isfinite(v):
            vals.append(float(v))
    if len(vals) < N_BOOT // 10:
        return (None, None)
    return (float(np.percentile(vals, lo)), float(np.percentile(vals, hi)))


def ramp_reading(steps, *, bands_hz, seed=0):
    """Per band across one ladder's steps: band power against pain, with and without the current.

    Returns ``{"bands": {centre: {...}}, "n_steps", "currents_mA", "reading", "why"}``. Each band
    carries ``r`` (plain), ``r_adjusted`` (the current taken out of both quantities), an interval on
    each, the counts, and a reason wherever a number could not be produced.
    """
    rng = np.random.default_rng(int(seed))
    steps = list(steps or ())
    out_bands = {}
    for band in bands_hz or ():
        b = float(band)
        cur, pain, pw = _arrays(steps, b)
        row = {"band_hz": b, "n_steps": int(cur.size), "r": None, "r_ci": (None, None),
               "r_adjusted": None, "r_adjusted_ci": (None, None), "slope_per_mA": None,
               "r_band_vs_current": None, "nearly_the_current": False,
               "reason": None, "adjustment_reason": None}
        if cur.size < MIN_RAMP_STEPS:
            row["reason"] = (f"too few ladder steps carry a current, a pain score and this band's "
                             f"power together ({cur.size} of the {len(steps)} steps)")
            out_bands[b] = row
            continue
        row["r"] = _pearson(pw, pain)
        row["r_ci"] = _boot_ci(lambda i: _pearson(pw[i], pain[i]), cur.size, rng)
        r_band_current = _pearson(pw, cur)
        row["r_band_vs_current"] = r_band_current
        if np.std(cur) == 0:
            row["adjustment_reason"] = ("the current is constant across these steps, so there is "
                                        "nothing to take out")
        elif r_band_current is not None and r_band_current ** 2 >= NEARLY_THE_CURRENT_R2:
            row["nearly_the_current"] = True
            row["adjustment_reason"] = (
                f"this band moves almost exactly with the current across these steps "
                f"(r {r_band_current:+.3f}, {100 * r_band_current ** 2:.0f}% of its movement), so "
                f"taking the current out leaves too little to correlate with anything; read that "
                f"as the finding rather than reading the adjusted number")
        else:
            adj = _su.partial_corr(pw, pain, cur)
            row["r_adjusted"] = float(adj) if adj is not None and np.isfinite(adj) else None
            if row["r_adjusted"] is None:
                row["adjustment_reason"] = "the adjustment is degenerate on these steps"
            else:
                row["r_adjusted_ci"] = _boot_ci(
                    lambda i: _su.partial_corr(pw[i], pain[i], cur[i]), cur.size, rng)
            fit = np.polyfit(cur, pw, 1)
            row["slope_per_mA"] = float(fit[0])
        out_bands[b] = row
    return {"bands": out_bands, "n_steps": len(steps),
            "currents_mA": sorted({_f(s.get("current_mA")) for s in steps} - {None}),
            "reading": "adjusted", "caveat": ONE_SESSION_CAVEAT,
            "why": ("the ladder steps the current on purpose, so a correlation across it is partly "
                    "the current; the adjusted value is the reading and the plain one is kept beside "
                    "it to show how much the adjustment did")}


def _block_values(holds, key, band=None):
    """(on values, off values) for pain or for one band's power across the three blocks."""
    on, off = [], []
    for h in holds or ():
        blk = str((h or {}).get("block") or "").lower()
        if key == "pain":
            vals = [_f(v) for v in ((h or {}).get("ratings") or [])]
        else:
            series = ((h or {}).get("power_by_band") or {}).get(band)
            if series is None:
                series = ((h or {}).get("power_by_band") or {}).get(str(band))
            vals = [_f(v) for v in (series or [])]
        vals = [v for v in vals if v is not None]
        (on if blk == "on" else off).extend(vals)
    return np.asarray(on, float), np.asarray(off, float)


def _one_hold_comparison(on, off, rng, *, what):
    row = {"n_on": int(on.size), "n_off": int(off.size), "on_mean": None, "off_mean": None,
           "on_minus_off": None, "ci": (None, None), "reason": None,
           "why": (f"the {what} during the ON hold against the two OFF holds either side of it, at "
                   "one current, the patient not told which block is which")}
    if on.size == 0 or off.size == 0:
        row["reason"] = ("no ratings in one of the blocks" if "rating" in what
                         else "no measurements in one of the blocks")
        return row
    row["on_mean"], row["off_mean"] = float(on.mean()), float(off.mean())
    row["on_minus_off"] = float(on.mean() - off.mean())
    vals = []
    for _ in range(N_BOOT):
        a = on[rng.integers(0, on.size, size=on.size)]
        b = off[rng.integers(0, off.size, size=off.size)]
        vals.append(float(a.mean() - b.mean()))
    row["ci"] = (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))
    return row


def holds_reading(holds, *, bands_hz, seed=0):
    """The three blind holds: pain, and each watched band's power, on against the two offs."""
    rng = np.random.default_rng(int(seed))
    holds = list(holds or ())
    if not holds:
        blank = {"n_on": 0, "n_off": 0, "on_mean": None, "off_mean": None, "on_minus_off": None,
                 "ci": (None, None), "reason": "no holds were run in this session",
                 "why": "the three fixed-current holds of the session plan (decision 230, part B)"}
        return {"pain": dict(blank), "bands": {float(b): dict(blank) for b in (bands_hz or ())},
                "n_blocks": 0}
    on, off = _block_values(holds, "pain")
    out = {"pain": _one_hold_comparison(on, off, rng, what="pain rating"),
           "bands": {}, "n_blocks": len(holds),
           "blocks": [{"block": str((h or {}).get("block")), "current_mA": _f((h or {}).get("current_mA")),
                       "n_ratings": len([v for v in ((h or {}).get("ratings") or []) if _f(v) is not None])}
                      for h in holds]}
    for band in bands_hz or ():
        b = float(band)
        bon, boff = _block_values(holds, "band", band=b)
        out["bands"][b] = _one_hold_comparison(bon, boff, rng, what="band power")
    return out


def session_reading(*, ramp_steps, holds, bands_hz, seed=0):
    """Both readings of one session, side by side, with the PI's ruling named on the answer."""
    ramp = ramp_reading(ramp_steps, bands_hz=bands_hz, seed=seed)
    hold = holds_reading(holds, bands_hz=bands_hz, seed=seed)
    compare = {}
    for band in bands_hz or ():
        b = float(band)
        rb = ramp["bands"].get(b) or {}
        hb = (hold.get("bands") or {}).get(b) or {}
        compare[b] = {
            "ramp_r": rb.get("r"), "ramp_r_adjusted": rb.get("r_adjusted"),
            "ramp_r_adjusted_ci": rb.get("r_adjusted_ci"), "ramp_n_steps": rb.get("n_steps"),
            "holds_on_minus_off": hb.get("on_minus_off"), "holds_ci": hb.get("ci"),
            "holds_n_on": hb.get("n_on"), "holds_n_off": hb.get("n_off"),
            "note": ("the ramp's adjusted value and the holds' difference answer the same question "
                     "under different conditions; they are not expected to be equal, and where they "
                     "disagree the disagreement is the finding"),
        }
    return {"ramp": ramp, "holds": hold, "compare": compare, "caveat": ONE_SESSION_CAVEAT,
            "pain_on_minus_off": (hold.get("pain") or {}).get("on_minus_off"),
            "reading": "ramp_adjusted", "why": READING_WHY}
