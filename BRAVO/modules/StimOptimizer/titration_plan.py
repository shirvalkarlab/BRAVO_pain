"""The titration session the Stim Optimizer page recommends for the next visit, designed from THIS
participant's own record (open item 30, decision 124's protocol; the PI's decision of 2026-09-12
evening: "make #4 a feature of next stim opt recommendation combined with 30").

WHAT THIS IS FOR. Two things wait on the same session. (1) The pooled current-to-power slope
that the Closed-Loop page's D19 rule and its evidence triangle read rests on 11-13 settled points
across 3-4 runs of stepped current on RCS08, at most 6 currents per run; a straight line through
that few points can be flipped by removing two of them, which is exactly what the 20 s post-ramp
margin did (decision 144), so the margin ships OFF (`ClosedLoopDeployment/post_ramp.py`). (2) No
run in the record has the 8 settled settings the curvature test needs (decision 55,
`amplitude_effect.MIN_POINTS_CURVATURE`), so whether the response has a peak is not answerable.
One titration session designed as below gives 21 settled points on its own, 11 of them distinct
currents on the rising leg, and once such a run exists the margin has enough points that no two
of them can flip a verdict -- that is the condition under which the margin is switched on.

WHERE IT IS ON SCREEN. Stim Optimizer page, the card "Titration session to run next," directly
under "What to test at the next visit." The response carries it under `titration_plan`
(`bravo_service.titration_plan_block` assembles the inputs; everything here is pure arithmetic on
values the request already holds). NOTHING HERE WRITES TO THE DEVICE: it is a sheet a clinician
reads at the visit.

EVERY NUMBER CARRIES WHERE IT CAME FROM: each side's block has a `sources` mapping, one entry per
field, so the page can print the origin beside the value and a reader can check it.

NO DJANGO, NO STORE, NO RECORDINGS ARE READ HERE. The service reads the two stored tables (the
pooled current-to-power table and the per-run points table) once and hands their frames in.

REVISED 2026-09-14, the PI's ruling on the design of the session itself (two changes from the
2026-09-12 design). (1) Each step is now TWO clinic-sheet rows -- a 60 s ramp row, then a 60 s
test row, 2 min a step -- rather than one 60 s row; the reason the TEST row is 60 s is unchanged
(`hold_per_step`, below), the ramp row is new. (2) The ladder goes UP in 0.5 mA steps to the
ceiling as before, but now comes back DOWN in 1.0 mA drops rather than the same 0.5 mA steps (his
words: "keep the 1.0 mA down legs"). Also new: each side's ladder holds the OTHER side at its own
current in force, rather than at 0 mA or unstated; an optional third block, "joint corners," gives
the pain surface's off-diagonal points a one-side ladder cannot; and every plan carries a flat
`sheet_rows` list laid out exactly like the clinic sheet's own "Stim Testing" tab.

THE SHEET LAYOUT SOURCE, READ DIRECTLY RATHER THAN ASSUMED. The column list below is row 11 of
the "Stim Testing" tab of the lab's own TEMPLATE workbook, `[Template]RCS08 Stage 2 - {Month} 2025
Clinic Testing {MM}_{DD}_{YY}` (local copy under `BRAVO/_pro_dump/clinic_sheets/RCS08/`), read
with openpyxl on 2026-09-14. The template is the file the "Make Google sheet" export copies, so
its header is the one these rows must match cell for cell. Filled-in visit sheets add two hand-made
columns the template does not have -- "Stim Set" in column A and "SIDE EFFECT SCORE" in column K of
the 2026-09-02 sheet -- so the step number and the block travel as separate `step` / `block`
fields on each row rather than as sheet columns. A first draft of this list, made with a raw
zip/XML read of the workbook instead of openpyxl, dropped four real columns ("sEEG Contacts",
"Side Effect?", "Right Leg", "Right Foot") and swapped Group and Contacts; that draft was wrong and
is replaced here.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .routines import percept_adaptive as PA
from .routines import within_visit as WV

#: The 22 band centres the calibrated grid and every stored table use, 8.5 to 29.5 Hz in 1 Hz
#: steps (decision 32: "all the bands that this week already covers").
CENTRES_HZ = tuple(float(c) for c in np.arange(8.5, 30.0, 1.0))
CENTRES_SOURCE = "the 22 calibrated-grid centres, 8.5-29.5 Hz (decision 32)"

#: A band centre this close to a harmonic of the stimulation rate carries a folded multiple of the
#: stimulation rate -- ADVISORY, not a refusal (the PI, 2026-09-06 correction, kept verbatim in
#: `Biomarkers.routines.analytics.harmonic_landings_hz`'s own docstring): that does NOT mean the
#: band is measuring the stimulator rather than the brain, only that its response to current needs
#: care. 2.5 Hz is half the 5 Hz band width the stored tables use (`clinic_steps.BAND_HALF_HZ`), so
#: a centre inside this distance has the harmonic inside its own band.
HARMONIC_HALF_WIDTH_HZ = 2.5

#: The current step of the ladder GOING UP (mA). Research synthesis §1 / open item 30.
STEP_MA = 0.5

#: The current step of the ladder COMING DOWN (mA). The PI's ruling, 2026-09-14: "keep the 1.0 mA
#: down legs" -- the down leg is coarser than the up leg on purpose, since its job is to check for
#: hysteresis at a few currents, not to re-walk every 0.5 mA point a second time. The down leg
#: always ends at 0 mA even when the last drop from the top would overshoot it: the step to 0 is
#: then whatever current is left, not a full 1.0 mA drop.
DOWN_STEP_MA = 1.0

#: Ten seconds of slack on top of the settled window and the margin, so a step that starts a
#: little late still holds the full window.
SLACK_S = 10.0

#: The settled window (30 s), the piece length (3 s) and the minimum pieces per settled setting
#: (10) are the analysis's own constants, read from `within_visit` rather than typed again.
SETTLED_WINDOW_S = float(WV.PRE_CHANGE_WINDOW_S)
PIECE_S = float(WV.CHUNK_S)
MIN_PIECES_PER_SETTING = int(WV.MIN_CHUNKS_PRE_CHANGE)
POST_RAMP_MARGIN_S = float(WV.RAMP_EXCLUDE_S)

#: The ramp row's length (s). The sheets' own note is that stimulation takes 30-45 s to ramp up
#: (`ClosedLoopDeployment.clinic_steps.RAMP_WARNING_S`, 45.0 s); the PI's ruling of 2026-09-14
#: rounds that up to a full 60 s clinic-sheet row so a step is a clean 2 min (ramp row + test row)
#: rather than an uneven 105 s.
RAMP_ROW_S = 60.0

PROTOCOL_SOURCE = ("artifacts/research_2026-09-11_stim_amplitude_vs_lfp_power.md §1 'What would "
                   "let a peak be estimated'; open item 30; decision 144 (the margin is switched on "
                   "once such a session exists); the PI's ruling of 2026-09-14 on the ladder's down "
                   "leg, the two-row step, the held other side and the joint corners")

#: THE "STIM TESTING" TAB COLUMN ORDER, verbatim from row 11 of the lab's template workbook, the
#: file the Google Sheet export copies (see the module docstring). Columns A..S in that order.
SHEET_COLUMNS = ("Group", "Contacts", "sEEG Contacts", "Amp (mA)", "Rate (Hz)", "PW (µs)",
                 "Threshold", "Duration (s)", "Side Effect?", "Timestamp",
                 "Movement/Change point", "General Notes / Pt Verbal Notes", "Overall", "Head",
                 "Back", "Left Leg", "Left Foot", "Right Leg", "Right Foot")
SHEET_SOURCE = ('BRAVO/_pro_dump/clinic_sheets/RCS08/[Template]RCS08 Stage 2 - {Month} 2025 Clinic '
                'Testing {MM}_{DD}_{YY}.xlsx, tab "Stim Testing," row 11, columns A-S')

#: One off-stimulation baseline and one impedance test before the first step and after the last
#: (decision 133: impedance at a FIXED measurement current, not the device's automatic low-current
#: mode). Minutes, each occurrence -- there are two of each in a session.
BASELINE_MINUTES_EACH = 2.0
IMPEDANCE_MINUTES_EACH = 1.0

#: The two current levels the joint-corners block is built from before any ceiling or safety
#: restriction is applied (the PI's ruling, 2026-09-14).
JOINT_CORNER_LEVELS_MA = (1.0, 4.0)
JOINT_CORNERS_WHY = "the pain surface's off-diagonal points, which no one-side ladder supplies"


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


_ORDINAL_WORDS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
                  7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth"}


def _ordinal(k) -> str:
    """1 -> "first", ..., 8 -> "eighth" (harmonic_avoidance's own `max_harmonic` default); a k
    outside the named range falls back to "12th" rather than raising."""
    k = int(k)
    return _ORDINAL_WORDS.get(k, f"{k}th")


def _n(count, noun):
    """"1 run" / "4 runs"."""
    c = int(count)
    return f"{c} {noun}" if c == 1 else f"{c} {noun}s"


def _bilateral(left_val, right_val) -> str:
    """"L x / R y", left before the slash. `clinic_steps.py` trap 4, the PI's ruling of
    2026-09-05: for a bilateral cell, the value before the separator is the left hemisphere."""
    l = "?" if left_val is None else f"{float(left_val):g}"
    r = "?" if right_val is None else f"{float(right_val):g}"
    return f"L {l} / R {r}"


def _bilateral_str(left_val, right_val) -> str:
    """The same "L x / R y" convention for a string value -- the contacts cell, as the lab's own
    2026-09-16 visit sheet writes it: "L C+2- / R C+1-2-"."""
    l = left_val if left_val else "?"
    r = right_val if right_val else "?"
    return f"L {l} / R {r}"


def _strip_side_prefix(s):
    """"L C+2-" -> "C+2-"; anything without a leading "L "/"R " is returned unchanged."""
    if not s:
        return s
    s = str(s)
    return s[2:] if s[:2] in ("L ", "R ") else s


# ---------------------------------------------------------------------------------------------
# the rate to hold
# ---------------------------------------------------------------------------------------------
def rate_to_hold(rate_in_force_hz, *, min_rate_hz=PA.MIN_ADAPTIVE_RATE_HZ) -> dict:
    """ONE stimulation rate for the whole session: the rate in force on that side today, lifted to
    the adaptive minimum (55 Hz, decision 138) when it is below it, because a session run at a
    rate the device's closed-loop mode cannot use would measure a response closed loop can never
    act on. `lifted` says which happened; `why` says it in a sentence."""
    r = _f(rate_in_force_hz)
    m = float(min_rate_hz)
    if r is None:
        return {"rate_hz": m, "rate_in_force_hz": None, "lifted": True,
                "why": (f"no stimulation rate is on record for this side, so the session runs at the "
                        f"{m:g} Hz adaptive minimum (decision 138)")}
    if r < m - 1e-9:
        return {"rate_hz": m, "rate_in_force_hz": r, "lifted": True,
                "why": (f"the rate in force, {r:g} Hz, is below the {m:g} Hz minimum the device's "
                        f"closed-loop mode accepts (decision 138); the session runs at {m:g} Hz so "
                        f"the response it measures is one closed loop can use")}
    return {"rate_hz": r, "rate_in_force_hz": r, "lifted": False,
            "why": f"the rate in force on this side today, {r:g} Hz, held for the whole session"}


# ---------------------------------------------------------------------------------------------
# the current ladder
# ---------------------------------------------------------------------------------------------
def ladder(ceiling_mA, *, step_mA=STEP_MA, down_step_mA=DOWN_STEP_MA) -> dict:
    """0 mA UP to the ceiling in `step_mA` (0.5 mA) steps, the top step held once, then back DOWN
    to 0 mA in `down_step_mA` (1.0 mA) drops -- the PI's ruling, 2026-09-14: "keep the 1.0 mA down
    legs." The top step never exceeds the ceiling: a ceiling that is not a multiple of `step_mA`
    is rounded DOWN to the last step below it, never up. The down leg always ends at 0 mA even
    when the top is not itself a multiple of `down_step_mA`: the last drop is whatever current is
    left, not a full `down_step_mA`."""
    c = _f(ceiling_mA)
    if c is None or c <= 0:
        return {"step_mA": float(step_mA), "down_step_mA": float(down_step_mA), "top_mA": None,
                "steps_mA": [], "n_steps": 0, "n_distinct_currents": 0,
                "n_distinct_currents_up": 0, "n_down": 0, "compact": "—",
                "why": "no ceiling is stated for this side, so no ladder can be written"}
    s = float(step_mA)
    ds = float(down_step_mA)
    n_up = int(math.floor(c / s + 1e-9))            # steps above 0, never past the ceiling
    up = [round(i * s, 3) for i in range(0, n_up + 1)]
    top = up[-1]
    down = []
    cursor = top - ds
    while cursor > 1e-9:
        down.append(round(cursor, 3))
        cursor -= ds
    if not down or down[-1] != 0.0:
        down.append(0.0)
    steps = up + down
    compact = (f"0 → {s:.1f} → … → {top:.1f} → … → 0 mA" if len(steps) > 6
               else " → ".join(f"{v:.1f}" for v in steps) + " mA")
    return {"step_mA": s, "down_step_mA": ds, "top_mA": top, "steps_mA": steps,
            "n_steps": len(steps), "n_distinct_currents": len(up),
            "n_distinct_currents_up": len(up), "n_down": len(down), "compact": compact,
            "why": (f"0 mA to {top:g} mA in {s:g} mA steps ({len(up)} distinct currents on the "
                    f"way up, the top held once), then back down to 0 mA in {ds:g} mA drops "
                    f"({len(down)} steps): {len(steps)} steps in all"
                    + ("" if abs(top - c) < 1e-9 else
                       f"; the stated ceiling of {c:g} mA is not a multiple of {s:g} mA, so the top "
                       f"step is the last one below it"))}


# ---------------------------------------------------------------------------------------------
# the hold per step -- now split into a ramp row and a test row (2026-09-14)
# ---------------------------------------------------------------------------------------------
def hold_per_step(*, settled_window_s=SETTLED_WINDOW_S, margin_s=POST_RAMP_MARGIN_S,
                  slack_s=SLACK_S, piece_s=PIECE_S, min_pieces=MIN_PIECES_PER_SETTING) -> dict:
    """The TEST row: at least 60 s, unchanged reasoning. the 30 s settled window the analysis
    averages, the 20 s after a current move the post-ramp margin will discard once it is switched
    on, and 10 s of slack. `step_timing` adds the separate 60 s ramp row on top of this."""
    hold = float(settled_window_s) + float(margin_s) + float(slack_s)
    usable = int(math.floor((hold - float(margin_s)) / float(piece_s) + 1e-9))
    return {"seconds": hold, "settled_window_s": float(settled_window_s),
            "post_ramp_margin_s": float(margin_s), "slack_s": float(slack_s),
            "piece_s": float(piece_s), "usable_pieces_after_margin": usable,
            "min_pieces_required": int(min_pieces),
            "why": (f"the analysis averages a {settled_window_s:g} s settled window at each current, "
                    f"the {margin_s:g} s post-ramp margin it will apply discards the first "
                    f"{margin_s:g} s after every current move, and {slack_s:g} s of slack covers a "
                    f"late start; {hold:g} s leaves {usable} usable {piece_s:g} s pieces after the "
                    f"margin, against the {min_pieces} a settled setting needs")}


def step_timing(*, ramp_s=RAMP_ROW_S, test=None) -> dict:
    """Every step is now TWO clinic-sheet rows (the PI's ruling, 2026-09-14, verbatim:
    "test-period hold time = 60 s, not 120 s; 2 min per step"): a `ramp_s` (60 s) ramp row, then
    the TEST row from :func:`hold_per_step` (also 60 s; the reason it is 60 s is unchanged), 2 min
    a step in total."""
    t = test if test is not None else hold_per_step()
    total = float(ramp_s) + float(t["seconds"])
    return {"ramp_s": float(ramp_s), "test_s": float(t["seconds"]), "total_s": total,
            "why": (f"each step is two clinic-sheet rows: a {ramp_s:g} s ramp row (the sheets' own "
                    f"note is that stimulation takes 30-45 s to ramp up, "
                    f"ClosedLoopDeployment.clinic_steps.RAMP_WARNING_S) and a {t['seconds']:g} s "
                    f"test row ({t['why']}); {total:g} s (2 min) a step, the PI's ruling of "
                    f"2026-09-14")}


def session_time_estimate(n_steps_total, *, step_minutes=2.0,
                          baseline_minutes_each=BASELINE_MINUTES_EACH,
                          impedance_minutes_each=IMPEDANCE_MINUTES_EACH) -> dict:
    """The whole session's length, honestly: `n_steps_total` steps at `step_minutes` (2 min) each,
    plus an off-stimulation baseline and an impedance test, each taken once before the first step
    and once after the last."""
    n = int(n_steps_total)
    steps_min = float(n) * float(step_minutes)
    overhead_min = 2.0 * (float(baseline_minutes_each) + float(impedance_minutes_each))
    total_min = steps_min + overhead_min
    return {"n_steps_total": n, "step_minutes": float(step_minutes), "steps_minutes": steps_min,
            "baseline_minutes_each": float(baseline_minutes_each),
            "impedance_minutes_each": float(impedance_minutes_each),
            "overhead_minutes": overhead_min, "total_minutes": total_min,
            "why": (f"{n} steps at {step_minutes:g} min each is {steps_min:g} min, plus an "
                    f"off-stimulation baseline before and after ({baseline_minutes_each:g} min "
                    f"each) and an impedance test before and after ({impedance_minutes_each:g} "
                    f"min each, at a fixed measurement current, decision 133): {total_min:g} min "
                    f"in all")}


# ---------------------------------------------------------------------------------------------
# the band centres to analyse, and which of them carry a stimulator harmonic (advisory: every
# centre below is still analysed; a flagged one is never dropped, decision 220)
# ---------------------------------------------------------------------------------------------
#: How many whole multiples of the rate `harmonic_avoidance` folds through the device's 250 Hz
#: sampling before it stops looking. 8 covers every multiple that can land inside or near the
#: 8.5-29.5 Hz grid for every rate the device accepts (55-160 Hz); found 2026-09-25 (this module's
#: own default before that day folded no multiple at all, see `harmonic_avoidance`'s docstring).
MAX_HARMONIC_MULTIPLE = 8


def harmonic_avoidance(rate_hz, *, centres_hz=CENTRES_HZ, half_width_hz=HARMONIC_HALF_WIDTH_HZ,
                       candidate_center_hz=None, max_harmonic=MAX_HARMONIC_MULTIPLE) -> dict:
    """Which of the 22 centres carry a folded multiple of the stimulation rate at `rate_hz`, and
    which are clear. ADVISORY, NEVER A REFUSAL, and the sense is the PI's own correction of
    2026-09-06 (kept verbatim in `Biomarkers.routines.analytics.harmonic_landings_hz`'s docstring):
    a band that carries a folded multiple of the stimulation rate is NOT thereby measuring the
    stimulator rather than the brain. What it means is narrower: take care reading that band's
    response to current, because a stimulation artefact could in principle land there too.

    THE LANDINGS COME FROM ONE HOME, `analytics.harmonic_landings_hz` -- found 2026-09-25: this
    function used to fold only |250 - rate| itself (the rate's own first image about the device's
    250 Hz sampling), missing every higher multiple. At 55 Hz the fifth multiple, 275 Hz, folds to
    25 Hz and the fourth, 220 Hz, folds to 30 Hz; neither was caught before, and 25 Hz sits close
    enough to pull 24.5 Hz -- the band decision 236 called "the one clean band to watch" -- onto a
    harmonic too. Every whole multiple of the rate up to `max_harmonic` is folded here, over a
    window widened by `half_width_hz` on each side of `centres_hz` so a landing just outside the
    grid still catches an edge centre (55 Hz's 30 Hz landing sits half a Hz past the grid's own
    29.5 Hz top and still reaches it). Each landing is named by what it is: "the fifth multiple of
    the rate folded by the device's 250 Hz sampling."

    THE SUB-HARMONICS ARE KEPT AS BEFORE: half, a quarter and three quarters of the rate (research
    synthesis §1; decision 124). They are not folded multiples of the rate, so
    `harmonic_landings_hz` does not compute them; this function adds them itself, unconditionally,
    as it always has.

    `candidate_center_hz`, when known, is judged the same way and reported on its own.
    """
    try:
        from modules.Biomarkers.routines import analytics as _an
    except ImportError:
        from Biomarkers.routines import analytics as _an
    r = float(rate_hz)
    hw = float(half_width_hz)
    cs = [float(c) for c in centres_hz]
    lo = (min(cs) - hw) if cs else -hw
    hi = (max(cs) + hw) if cs else hw
    landings = _an.harmonic_landings_hz(r, lo, hi, max_harmonic=int(max_harmonic))
    harmonics, names = {}, {}
    for land in landings:
        k = int(land["harmonic"])
        key = f"multiple_{k}"
        harmonics[key] = float(land["lands_at_hz"])
        names[key] = f"the {_ordinal(k)} multiple of the rate folded by the device's 250 Hz sampling"
    harmonics["half_rate"], names["half_rate"] = r / 2.0, "half the rate"
    harmonics["quarter_rate"], names["quarter_rate"] = r / 4.0, "a quarter of the rate"
    harmonics["three_quarters_rate"], names["three_quarters_rate"] = 3.0 * r / 4.0, "three quarters of the rate"
    clear, avoid, reasons = [], [], {}
    for c in cs:
        hits = [(k, h) for k, h in harmonics.items() if abs(c - h) <= hw + 1e-9]
        if hits:
            avoid.append(c)
            reasons[f"{c:g}"] = "; ".join(
                f"within {hw:g} Hz of {h:g} Hz ({names[k]})" for k, h in hits)
        else:
            clear.append(c)
    landing_desc = _and_list([f"{h:g} Hz ({names[k]})"
                             for k, h in sorted(harmonics.items(), key=lambda kv: kv[1])])
    out = {"rate_hz": r, "harmonics_hz": harmonics, "harmonic_names": names, "half_width_hz": hw,
           "centres_hz": cs, "clear_hz": clear, "avoid_hz": avoid,
           "avoid_reasons": reasons, "n_clear": len(clear), "n_avoid": len(avoid),
           "why": (f"at {r:g} Hz the stimulation rate lands at " + landing_desc + f"; a band centre "
                   f"within {hw:g} Hz of one of those carries a folded multiple of the stimulation "
                   f"rate. That is advisory, not a refusal (the PI, 2026-09-06): it does not mean "
                   f"the band measures the stimulator rather than the brain, only that its response "
                   f"to current needs care")}
    cc = _f(candidate_center_hz)
    if cc is not None:
        hits = [(k, h) for k, h in harmonics.items() if abs(cc - h) <= hw + 1e-9]
        out["candidate_center_hz"] = cc
        out["candidate_clear"] = not hits
        out["candidate_note"] = (f"{cc:g} Hz is clear of every harmonic" if not hits else
                                 f"{cc:g} Hz is " + "; ".join(
                                     f"within {hw:g} Hz of {h:g} Hz ({names[k]})"
                                     for k, h in hits))
    return out


# ---------------------------------------------------------------------------------------------
# what the record holds today on a contact, from the two stored tables
# ---------------------------------------------------------------------------------------------

def harmonic_warning(rate_hz, qualifying_centers_hz, *, usable) -> dict:
    """The harmonic rule on the readiness screen as a WARNING, never a refusal (the PI,
    2026-09-21: "put a warning for the harmonic rule, but don't make it blocking").

    A qualifying band (falls with current, rises with pain; decision 199) that sits within
    `HARMONIC_HALF_WIDTH_HZ` of a stimulator harmonic at this rate may be measuring the
    stimulator rather than the brain. When a usable cell qualifies ONLY through such bands the
    warning fires; when at least one qualifying band is clear of every harmonic it is a note;
    a cell that is not usable gets the information and no warning. `usable` is read, never
    returned: the caller's `deployable` is untouched by design.
    """
    q = [float(x) for x in (qualifying_centers_hz or [])]
    if not q:
        return {"near_hz": [], "clear_hz": [], "notes": {}, "only_through_harmonics": False,
                "warning": None, "note": None}
    h = harmonic_avoidance(float(rate_hz), centres_hz=q)
    near, clear, notes = list(h["avoid_hz"]), list(h["clear_hz"]), dict(h["avoid_reasons"])
    only = bool(usable) and bool(near) and not clear
    fmt = lambda xs: ", ".join(f"{x:g}" for x in xs)  # noqa: E731
    warning = note = None
    if only:
        warning = (f"Warning: this combination qualifies only through bands on a stimulator "
                   f"harmonic at {float(rate_hz):g} Hz ({fmt(near)} Hz: "
                   + "; ".join(notes[f"{x:g}"] for x in near)
                   + "). A fall there with current may be the stimulator, not the brain. It stays "
                   f"usable: by the PI's ruling of 2026-09-21 this is a warning, not a refusal.")
    elif near and clear:
        note = (f"{fmt(near)} Hz sits on a stimulator harmonic at {float(rate_hz):g} Hz; "
                f"{fmt(clear)} Hz is clear, so the combination does not rest on the harmonic band alone.")
    elif near:
        # every qualifying band on a harmonic, but the cell is not usable for another reason
        note = (f"every qualifying band ({fmt(near)} Hz) sits on a stimulator harmonic at "
                f"{float(rate_hz):g} Hz; the combination is not usable for the reason given, so the "
                f"harmonic warning does not apply to it today.")
    return {"near_hz": near, "clear_hz": clear, "notes": notes, "only_through_harmonics": only,
            "warning": warning, "note": note}

def record_today_for_contact(pooled, run_points, channel, *, lo_hz=None, hi_hz=None) -> dict:
    """What the stored tables say the record holds for one sensing contact: the pooled table's
    largest point count over the band centres inside [lo_hz, hi_hz] with its run count and the
    centre it was read at, and the per-run points table's largest number of distinct settled
    currents in any ONE run on that contact. `None` frames mean the table is not stored; each
    half says so rather than reporting 0 as if it had been counted."""
    out = {"channel": (None if channel is None else str(channel)),
           "points": None, "runs": None, "band_center_hz": None, "n_centres_at_max": None,
           "n_centres_in_window": None,
           "max_settled_settings_in_one_run": None, "n_runs_on_contact": None,
           "pooled_table_stored": pooled is not None, "run_points_table_stored": run_points is not None}
    lo = -math.inf if lo_hz is None else float(lo_hz)
    hi = math.inf if hi_hz is None else float(hi_hz)
    if channel is None:
        out["note"] = "no sensing contact is chosen for this side, so nothing is counted"
        return out
    ch = str(channel)
    if pooled is not None and len(pooled) and "sensing_contact" in pooled.columns:
        p = pooled[pooled["sensing_contact"].astype(str) == ch]
        if "band_center_hz" in p.columns:
            centres = pd.to_numeric(p["band_center_hz"], errors="coerce")
            p = p[(centres >= lo - 1e-9) & (centres <= hi + 1e-9)]
        if len(p) and "n" in p.columns:
            n = pd.to_numeric(p["n"], errors="coerce")
            out["n_centres_in_window"] = int(len(p))
            if n.notna().any():
                i = n.idxmax()
                out["points"] = int(n.loc[i])
                out["runs"] = (int(pd.to_numeric(p.loc[i, "n_visits"], errors="coerce"))
                               if "n_visits" in p.columns and pd.notna(p.loc[i, "n_visits"]) else None)
                out["band_center_hz"] = _f(p.loc[i, "band_center_hz"]) if "band_center_hz" in p.columns else None
                out["n_centres_at_max"] = int((n == n.loc[i]).sum())
    if run_points is not None and len(run_points) and "sensing_contact" in run_points.columns:
        per = settled_settings_per_run(run_points)
        per = per[per["sensing_contact"].astype(str) == ch]
        if len(per):
            out["n_runs_on_contact"] = int(per["run"].nunique())
            out["max_settled_settings_in_one_run"] = int(per["n_settled_settings"].max())
    parts = []
    if out["points"] is not None:
        parts.append(f"{_n(out['points'], 'settled point')} across {_n(out['runs'] or 0, 'run')} of rising "
                     f"current, the most at any centre in the pooled table ({out['n_centres_at_max']} of "
                     f"{out['n_centres_in_window']} centres hold that many; {out['band_center_hz']:g} Hz "
                     f"is the first)")
    elif pooled is None:
        parts.append("the pooled current-to-power table is not stored yet (the Closed-Loop page writes it)")
    else:
        parts.append("the pooled current-to-power table has no row for this contact")
    if out["max_settled_settings_in_one_run"] is not None:
        parts.append(f"at most {out['max_settled_settings_in_one_run']} settled currents in any one "
                     f"run ({_n(out['n_runs_on_contact'], 'run')} on this contact)")
    elif run_points is None:
        parts.append("the per-run points table is not stored yet")
    else:
        parts.append("the per-run points table has no run on this contact")
    out["note"] = "; ".join(parts)
    return out


def settled_settings_per_run(run_points) -> pd.DataFrame:
    """One row per (run, sensing contact): how many DISTINCT currents carry a settled band-power
    value on the voltage-trace route. The rule `post_ramp.margin_becomes_available` counts by."""
    df = pd.DataFrame(run_points)
    need = {"run", "sensing_contact", "current_mA", "settled_band_power_device_units"}
    if df.empty or not need.issubset(df.columns):
        return pd.DataFrame(columns=["run", "sensing_contact", "n_settled_settings"])
    if "source" in df.columns:
        td = df["source"].astype(str) == "time domain voltage trace"
        if td.any():
            df = df[td]
    df = df[pd.to_numeric(df["settled_band_power_device_units"], errors="coerce").notna()]
    df = df[pd.to_numeric(df["current_mA"], errors="coerce").notna()]
    if df.empty:
        return pd.DataFrame(columns=["run", "sensing_contact", "n_settled_settings"])
    g = (df.assign(current_mA=pd.to_numeric(df["current_mA"], errors="coerce").round(3))
           .groupby(["run", "sensing_contact"])["current_mA"].nunique()
           .reset_index().rename(columns={"current_mA": "n_settled_settings"}))
    return g


# ---------------------------------------------------------------------------------------------
# the joint corners (optional): the pain surface's off-diagonal points
# ---------------------------------------------------------------------------------------------
def joint_corners(ceiling_left_mA, ceiling_right_mA, *, levels_mA=JOINT_CORNER_LEVELS_MA,
                  is_safe=None) -> dict:
    """The four corners of the (left current, right current) grid at `levels_mA` -- by default
    (1.0, 4.0) mA on each side -- each capped at that side's own stated ceiling and, when
    `is_safe` is given, restricted to the joint safe set. Optional: the PI's ruling, 2026-09-14,
    "a third block, optional, for the pain surface only." A point `is_safe` refuses is EXCLUDED
    and named, never silently dropped. Two corners collapsing to the same capped point (a low
    ceiling on one side) are kept once."""
    cl, cr = _f(ceiling_left_mA), _f(ceiling_right_mA)
    lo, hi = float(min(levels_mA)), float(max(levels_mA))
    raw = [(lo, lo), (hi, lo), (lo, hi), (hi, hi)]
    points, seen = [], set()
    for l, r in raw:
        cl_v = min(l, cl) if cl is not None else l
        cr_v = min(r, cr) if cr is not None else r
        key = (round(cl_v, 3), round(cr_v, 3))
        if key in seen:
            continue
        seen.add(key)
        points.append({"amp_left_mA": round(cl_v, 3), "amp_right_mA": round(cr_v, 3),
                       "requested_left_mA": l, "requested_right_mA": r})
    kept, excluded = [], []
    for p in points:
        if is_safe is not None and not bool(is_safe(p["amp_left_mA"], p["amp_right_mA"])):
            excluded.append(dict(p, reason="outside the joint safe set fitted from this "
                                          "participant's own tolerated settings and the "
                                          "PI-stated ceiling"))
        else:
            kept.append(p)
    return {"points": kept, "excluded": excluded, "optional": True, "why": JOINT_CORNERS_WHY,
           "levels_mA": [lo, hi], "ceiling_left_mA": cl, "ceiling_right_mA": cr,
           "n_points": len(kept), "n_excluded": len(excluded)}


# ---------------------------------------------------------------------------------------------
# the flat clinic-sheet rows
# ---------------------------------------------------------------------------------------------
def _sheet_row_pair(step, block, *, contacts, amp, rate_hz, pw, timing) -> list:
    """One step's two clinic-sheet rows: the ramp row carries Contacts/Amp/Rate/PW and the ramp
    duration; the test row carries only the test duration (the PI's ruling, 2026-09-14 -- that is
    how the real sheet is filled today, see the September 2026 workbook's own two-row steps)."""
    ramp = {c: None for c in SHEET_COLUMNS}
    ramp.update({"Contacts": contacts, "Amp (mA)": amp,
                "Rate (Hz)": (None if rate_hz is None else round(float(rate_hz), 3)),
                "PW (µs)": pw, "Duration (s)": float(timing["ramp_s"])})
    ramp["block"] = str(block)
    ramp["step"] = int(step)
    ramp["row_kind"] = "ramp"
    test = {c: None for c in SHEET_COLUMNS}
    test["Duration (s)"] = float(timing["test_s"])
    test["block"] = str(block)
    test["step"] = int(step)
    test["row_kind"] = "test"
    return [ramp, test]


def _emit_ladder_rows(rows, currents_mA, *, block, rate_hz, pw_left, pw_right, contacts_left,
                      contacts_right, varying, held_mA, timing, start) -> int:
    step = int(start)
    contacts = _bilateral_str(contacts_left, contacts_right)
    pw = _bilateral(pw_left, pw_right)
    for cur in currents_mA:
        amp_left = cur if varying == "Left" else held_mA
        amp_right = cur if varying == "Right" else held_mA
        rows.extend(_sheet_row_pair(step, block, contacts=contacts,
                                    amp=_bilateral(amp_left, amp_right), rate_hz=rate_hz, pw=pw,
                                    timing=timing))
        step += 1
    return step


def _emit_joint_rows(rows, points, *, rate_hz, pw_left, pw_right, contacts_left, contacts_right,
                     timing, start) -> int:
    step = int(start)
    contacts = _bilateral_str(contacts_left, contacts_right)
    pw = _bilateral(pw_left, pw_right)
    for p in points:
        rows.extend(_sheet_row_pair(step, "joint_corners", contacts=contacts,
                                    amp=_bilateral(p["amp_left_mA"], p["amp_right_mA"]),
                                    rate_hz=rate_hz, pw=pw, timing=timing))
        step += 1
    return step


def build_sheet_rows(sides, joint_corners_block, *, in_force, timing) -> list:
    """The whole clinic sheet, one flat list of dict rows in `SHEET_COLUMNS` order plus `block`
    (`left_ladder` / `right_ladder` / `joint_corners`), `step` (the block-local step number) and
    `row_kind` (`ramp` / `test`). `sides` is `plan_for_sides`'s own `sides` mapping (each side's
    `ladder` and `held_other_side` blocks); `in_force` is the request's `in_force_by_side` output,
    the source of each side's programmed contacts and pulse width."""
    rows = []
    left, right = sides.get("Left"), sides.get("Right")
    lf = dict((in_force or {}).get("Left") or {})
    rf = dict((in_force or {}).get("Right") or {})
    contacts_l = _strip_side_prefix(lf.get("contacts_short"))
    contacts_r = _strip_side_prefix(rf.get("contacts_short"))
    pw_l, pw_r = lf.get("pulse_width_us"), rf.get("pulse_width_us")
    gstep = 1
    if left is not None:
        held = (left.get("held_other_side") or {}).get("current_mA")
        gstep = _emit_ladder_rows(rows, left["ladder"]["steps_mA"], block="left_ladder",
                                  rate_hz=left.get("rate_hz"), pw_left=pw_l, pw_right=pw_r,
                                  contacts_left=contacts_l, contacts_right=contacts_r,
                                  varying="Left", held_mA=held, timing=timing, start=gstep)
    if right is not None:
        held = (right.get("held_other_side") or {}).get("current_mA")
        gstep = _emit_ladder_rows(rows, right["ladder"]["steps_mA"], block="right_ladder",
                                  rate_hz=right.get("rate_hz"), pw_left=pw_l, pw_right=pw_r,
                                  contacts_left=contacts_l, contacts_right=contacts_r,
                                  varying="Right", held_mA=held, timing=timing, start=gstep)
    jc = joint_corners_block or {}
    if jc.get("points"):
        lr = _f(left.get("rate_hz")) if left is not None else None
        rr = _f(right.get("rate_hz")) if right is not None else None
        rate_hz = (max(lr, rr) if (lr is not None and rr is not None) else (lr if lr is not None else rr))
        gstep = _emit_joint_rows(rows, jc["points"], rate_hz=rate_hz, pw_left=pw_l, pw_right=pw_r,
                                 contacts_left=contacts_l, contacts_right=contacts_r,
                                 timing=timing, start=gstep)
    return rows


# ---------------------------------------------------------------------------------------------
# one side's plan
# ---------------------------------------------------------------------------------------------
def side_plan(side, *, rate_in_force_hz, rate_source, pulse_width_us, pulse_width_source,
              ceiling_mA, ceiling_source, contact, contact_source, record_today, margin,
              candidate_center_hz=None, min_rate_hz=PA.MIN_ADAPTIVE_RATE_HZ,
              held_other_side_mA=None, held_other_side_source=None) -> dict:
    """The whole plan for one side, every field beside its source.

    `contact` is a dict from the readiness screen (`channel`, `display_short`, `n_responding`,
    `n_bands`, `laterality`, `deployable`, `rate_hz`, `note`) or None; `record_today` is
    :func:`record_today_for_contact`'s output; `margin` is
    `ClosedLoopDeployment.post_ramp.margin_becomes_available`'s output. `held_other_side_mA` and
    `held_other_side_source` (2026-09-14) are the OTHER side's own current in force and where it
    came from: while this side's ladder runs, the other side is held there, not at 0 mA.
    """
    rate = rate_to_hold(rate_in_force_hz, min_rate_hz=min_rate_hz)
    lad = ladder(ceiling_mA)
    hold = hold_per_step()
    timing = step_timing(test=hold)
    bands = harmonic_avoidance(rate["rate_hz"], candidate_center_hz=candidate_center_hz)
    n_points = int(lad["n_steps"])
    n_up = int(lad["n_distinct_currents"])
    need = int((margin or {}).get("min_settled_settings") or 0) or None
    rec = dict(record_today or {})
    pw = _f(pulse_width_us)
    held_mA = _f(held_other_side_mA)
    held_src = str(held_other_side_source) if held_other_side_source else \
        "no reading for the other side"
    held_block = {"current_mA": held_mA, "source": held_src}

    contact_block = None
    if contact:
        contact_block = {k: contact.get(k) for k in ("channel", "display_short", "display_hemisphere",
                                                      "display_contacts", "n_responding", "n_bands",
                                                      "laterality", "deployable", "rate_hz",
                                                      "responding_fraction", "median_separation_d",
                                                      "n_era_negative_significant", "n_pain_positive",
                                                      "n_qualifying", "qualifying_centers_hz",
                                                      "ipsilateral_alternative")}
        lat = str(contact.get("laterality") or "")
        sensing_side = str(contact.get("sensing_side") or "")
        contact_block["on_other_side"] = (lat == "contralateral")
        contact_block["note"] = (
            f"the best evidence for {side} stimulation is on a contact on the OTHER side "
            f"({sensing_side or 'unknown'}); the device needs a contralateral sensing configuration "
            f"for it (decision 143, S3)" if lat == "contralateral"
            else f"the contact the readiness screen ranks best for {side} stimulation"
                 + ("" if contact.get("deployable") else
                    " (no contact on this side passed the screen; this is the one with the most "
                    "bands falling with current)"))
    yield_block = {
        "settled_points_from_session": n_points,
        "distinct_currents_up_leg": n_up,
        "record_today": rec,
        "min_settled_settings_for_margin": need,
        "session_clears_margin_floor": (bool(n_up >= need) if need else None),
        "run_with_enough_settings_exists_today": (margin or {}).get("available"),
        "margin_switched_on_today": (margin or {}).get("switch_on"),
        "sentence": _yield_sentence(n_points, n_up, rec, margin),
    }
    conditions = [
        "each step is two clinic-sheet rows: a ramp row then a test row, 2 min a step "
        f"({timing['total_s']:g} s)",
        "streaming on for the whole session, so the voltage trace exists for every step",
        "an off-stimulation baseline before the first step and after the last",
        ("an impedance test before and after, at a FIXED measurement current, not the device's "
         "automatic low-current mode, which reads spuriously high (decision 133)"),
        (f"the other side is HELD at its own current in force while this side's ladder runs "
         f"({held_src})"),
        "note the wall-clock time of each current change on the clinic sheet",
    ]
    sources = {
        "rate_hz": (f"{rate_source}; lifted to the adaptive minimum ({min_rate_hz:g} Hz, "
                    f"percept_adaptive.MIN_ADAPTIVE_RATE_HZ, decision 138)" if rate["lifted"]
                    else rate_source),
        "pulse_width_us": pulse_width_source,
        "ceiling_mA": ceiling_source,
        "sensing_contact": contact_source,
        "held_other_side": held_src,
        "ladder": (f"0 mA up to the stated ceiling in {STEP_MA:g} mA steps, held once, then back "
                   f"down to 0 mA in {DOWN_STEP_MA:g} mA drops (the PI's ruling, 2026-09-14; "
                   f"research synthesis §1; open item 30)"),
        "step_timing": (f"a {RAMP_ROW_S:g} s ramp row then a {hold['seconds']:g} s test row, "
                        f"{timing['total_s']:g} s (2 min) a step (the PI's ruling, 2026-09-14)"),
        "hold": (f"within_visit.PRE_CHANGE_WINDOW_S ({SETTLED_WINDOW_S:g} s) + within_visit.RAMP_EXCLUDE_S "
                 f"({POST_RAMP_MARGIN_S:g} s, decisions 141 and 144) + {SLACK_S:g} s slack; pieces of "
                 f"within_visit.CHUNK_S ({PIECE_S:g} s), within_visit.MIN_CHUNKS_PRE_CHANGE "
                 f"({MIN_PIECES_PER_SETTING}) required"),
        "bands": (f"{CENTRES_SOURCE}; harmonics from every whole multiple of the rate folded by the "
                  f"device's 250 Hz sampling (Biomarkers.routines.analytics.harmonic_landings_hz), "
                  f"plus rate/2, rate/4 and 3·rate/4 (research synthesis §1; decision 124); "
                  f"±{HARMONIC_HALF_WIDTH_HZ:g} Hz, advisory (the PI, 2026-09-06)"),
        "yield.settled_points_from_session": "the ladder's step count (one settled point per step)",
        "yield.record_today": ("the stored pooled current-to-power table (within_visit_pooled_shape) and "
                               "the stored per-run points table (three_source_run_points), both "
                               "written by the Closed-Loop page, read as stim_optimizer"),
        "yield.margin": ("ClosedLoopDeployment.post_ramp.margin_becomes_available over the stored "
                         "per-run points table; the floor is amplitude_effect.MIN_POINTS_CURVATURE"),
        "conditions": "research synthesis §1; decision 133 (impedance); the PI's ruling of 2026-09-14",
    }
    return {
        "side": str(side),
        "rate_hz": rate["rate_hz"], "rate_in_force_hz": rate["rate_in_force_hz"],
        "rate_lifted": rate["lifted"], "rate_why": rate["why"],
        "pulse_width_us": pw,
        "pulse_width_note": (None if pw is not None else
                             "no pulse width is on record for this side; hold the one programmed at the visit"),
        "ceiling_mA": _f(ceiling_mA),
        "held_other_side": held_block,
        "sensing_contact": contact_block,
        "sensing_contact_note": (None if contact_block else
                                 f"the readiness screen has no cell for {side} stimulation, so no "
                                 f"sensing contact is named; record from the contact the Closed-Loop "
                                 f"page's committed band sits on"),
        "ladder": lad, "hold": hold, "step_timing": timing, "bands": bands,
        "conditions": conditions, "yield": yield_block, "sources": sources,
    }


def _yield_sentence(n_points, n_up, rec, margin) -> str:
    have = rec.get("points")
    runs = rec.get("runs")
    per_run = rec.get("max_settled_settings_in_one_run")
    need = (margin or {}).get("min_settled_settings")
    today = (f"today this contact holds {_n(have, 'settled point')} across {_n(runs or 0, 'run')}"
             + (f", at most {per_run} currents in any one run" if per_run is not None else "")
             if have is not None else
             ("today no pooled points are stored for this contact"
              + (f" (at most {per_run} currents in any one run)" if per_run is not None else "")))
    session = (f"this session yields {n_points} settled points, {n_up} distinct currents on the "
               f"way up")
    # S7 SETTLED (decision 196, 2026-09-17): the post-move exclusion margin is 0 s by measurement.
    # On the 2026-09-16 titration session at 55 Hz (31 settings held 107-168 s on L 1-3+) the
    # first 3 s after a current move read 1.000 of the same setting's own last-30 s level (95 %
    # 0.86-1.16), and every earlier window on the record's 58 long holds read 0.98-1.02. Nothing
    # is excluded; the switch in `post_ramp` stays off and this sentence no longer waits on it.
    m = ("the post-move margin is 0 s, measured on the 2026-09-16 session (the first 3 s after a "
         "move read 1.00 of the settled level), so no piece of recording is excluded")
    return f"{today}; {session}; {m}."



# ---------------------------------------------------------------------------------------------
# THE EXPLORATORY LADDER for a stimulation configuration the sensing rule requires and the
# record has never powered (the PI, 2026-09-21: "create the titration ladder (left C positive,
# one minus, two minus) in a way that will be very helpful for deciding how the biomarker moves
# and its acute effect on pain"). The readiness screen's best left sensing pair is L 0-3+, which
# the device allows only while contacts 1 and 2 stimulate together (decision 217); on RCS08 that
# configuration was programmed for three months of 2025 at 0.0 mA and never carried current.
# Two things the session has to answer, in two parts: (A) how the band power on the sensing pair
# moves with current -- the same 0.5 mA up / 1.0 mA down ladder as the ordinary session, at the
# RATE of the cell where the pain-positive bands were found, with the first-exposure stop rule;
# (B) what the current does to pain over minutes -- three timed holds, off / on / off, a rating
# every minute, the patient not told the current, the biomarker still streaming.
# ---------------------------------------------------------------------------------------------
#: The three holds of part B: minutes each, and how often a rating is taken.
HOLD_MINUTES_EACH = 5.0
HOLD_RATING_EVERY_MIN = 1.0
#: The first-exposure stop rule (decision 165: a side-effect score of 2 is its own rung, cost 2.0;
#: decision 164: moderate or severe steps never seed "tolerated").
FIRST_EXPOSURE_STOP_RULE = ("stop the up leg at the first step with a side-effect score of 2 or "
                            "more (decision 165); the last step below it is the top current the "
                            "patient tolerated, and the down leg and the holds start from there")


def stim_rings_for_sensing_pair(channel):
    """The stimulating rings a sensing pair REQUIRES: the inverse of the flanking rule
    (`lfp_evidence.flanking_pair`, decision 217). (0, 3) needs {1, 2}; (0, 2) needs {1}; (1, 3)
    needs {2}; a pair with nothing between its contacts, or a name that is not a pair, gives None."""
    from .routines.lfp_evidence import sensing_pair_rings
    pair = sensing_pair_rings(channel)
    if pair is None:
        return None
    lo, hi = pair
    inner = set(range(lo + 1, hi))
    return inner or None


def _rings_label(side, rings) -> str:
    s = "L" if str(side) == "Left" else "R"
    return f"{s} C+" + "".join(f"{r}-" for r in sorted(int(r) for r in rings or ()))


def configuration_exposure(es, side, rings) -> dict:
    """What the record holds for THIS stimulation configuration on THIS side, read from the
    epoch table (`adapter.build_design_matrix`'s frame: one row per unbroken setting, its cathode
    per side, its hours and the pain reports inside it): epochs, hours, the currents it carried,
    the reports, and whether it ever carried current at all."""
    from .bravo_service import stim_rings
    want = {int(r) for r in (rings or ())}
    col_c, col_a = f"cathode_{side}", f"amp_mA_{side}"
    out = {"side": str(side), "rings": sorted(want), "epochs": 0, "hours": 0.0, "reports": 0,
           "amp_min_mA": None, "amp_max_mA": None, "first": None, "last": None, "ever_powered": None,
           "sentence": ""}
    label = _rings_label(side, want)
    if es is None or len(es) == 0 or col_c not in getattr(es, "columns", []):
        out["sentence"] = f"no epoch table was supplied, so the record for {label} is unknown"
        return out
    from .bravo_service import stim_contacts_short
    mask = np.array([stim_rings(c) == want for c in es[col_c]], dtype=bool)
    sub = es.loc[mask]
    out["epochs"] = int(len(sub))
    if not len(sub):
        out["ever_powered"] = False
        out["sentence"] = f"{label} has never been programmed on this side: no epoch in the record"
        return out
    # an epoch on a PART of a ring (one segment, "1a-2a") stimulates the same rings but not the
    # whole contact; it is counted, and said separately, so a one-day segment trial does not
    # read as the full configuration having carried current
    labels = [stim_contacts_short(c, side) for c in sub[col_c]]
    partial = np.array([any(ch.isalpha() for ch in (l or "").split("C+")[-1]) for l in labels], dtype=bool)
    amps = pd.to_numeric(sub[col_a], errors="coerce")
    full_amps = amps[~partial]
    out["epochs_full_rings"] = int((~partial).sum()); out["epochs_partial_rings"] = int(partial.sum())
    out["amp_max_full_rings_mA"] = _f(np.nanmax(full_amps)) if full_amps.notna().any() else None
    out["partial_sentence"] = None
    if partial.any():
        ps = sub.loc[partial]
        out["partial_sentence"] = (f"{_n(int(partial.sum()), 'epoch')} on part of a ring only ({', '.join(sorted(set(l for l, q in zip(labels, partial) if q)))}) "
                                   f"carried up to {np.nanmax(amps[partial]):g} mA for "
                                   f"{float(np.nansum(pd.to_numeric(ps.get('dur_h'), errors='coerce'))):.0f} h with "
                                   f"{int(np.nansum(pd.to_numeric(ps.get('n'), errors='coerce')))} report(s)")
    out["hours"] = float(np.nansum(pd.to_numeric(sub.get("dur_h"), errors="coerce"))) if "dur_h" in sub else 0.0
    out["reports"] = int(np.nansum(pd.to_numeric(sub.get("n"), errors="coerce"))) if "n" in sub else 0
    out["amp_min_mA"] = _f(np.nanmin(amps)) if amps.notna().any() else None
    out["amp_max_mA"] = _f(np.nanmax(amps)) if amps.notna().any() else None
    t0 = pd.to_datetime(sub["t0"], utc=True, errors="coerce") if "t0" in sub else None
    if t0 is not None and t0.notna().any():
        out["first"] = str(t0.min().date()); out["last"] = str(t0.max().date())
    # "ever powered" means the FULL rings carried current; a segment trial is said beside it
    out["ever_powered"] = bool(out["amp_max_full_rings_mA"] is not None and out["amp_max_full_rings_mA"] > 0)
    span = f"{out['first']} to {out['last']}" if out["first"] else "undated"
    if out["ever_powered"]:
        out["sentence"] = (f"{label} carried up to {out['amp_max_full_rings_mA']:g} mA over "
                           f"{_n(out['epochs_full_rings'], 'epoch')}, {out['hours']:.0f} h, {span}, with "
                           f"{_n(out['reports'], 'pain report')} inside")
    else:
        out["sentence"] = (f"{label} was programmed for {_n(out['epochs_full_rings'], 'epoch')}, "
                           f"{span}, at 0.0 mA only: the full rings have never carried current, so nothing in the "
                           f"record says what this configuration does to the band power or to pain")
    if out["partial_sentence"]:
        out["sentence"] += f"; {out['partial_sentence']}"
    return out


def acute_pain_holds(top_mA, *, minutes_each=HOLD_MINUTES_EACH,
                     rating_every_min=HOLD_RATING_EVERY_MIN) -> dict:
    """Part B: three timed holds, off / on / off, at the top current the patient tolerated on the
    day (planned here as the ladder's top; the sheet is corrected on the day), a pain rating every
    minute, the patient not told the current. The biomarker reads in a 60 s test row; a change in
    pain needs minutes, and a washout after it is what makes the change believable."""
    top = _f(top_mA)
    if top is None or top <= 0:
        return {"holds": [], "minutes_each": float(minutes_each), "rating_every_minutes": float(rating_every_min),
                "ratings_per_hold": 0, "total_minutes": 0.0, "blind": True,
                "why": "no top current, so no holds can be written"}
    per = int(round(float(minutes_each) / float(rating_every_min)))
    holds = [{"order": 1, "state": "off", "current_mA": 0.0, "minutes": float(minutes_each)},
             {"order": 2, "state": "on", "current_mA": top, "minutes": float(minutes_each)},
             {"order": 3, "state": "off", "current_mA": 0.0, "minutes": float(minutes_each)}]
    return {"holds": holds, "minutes_each": float(minutes_each),
            "rating_every_minutes": float(rating_every_min), "ratings_per_hold": per,
            "total_minutes": float(minutes_each) * 3.0, "blind": True,
            "why": (f"three holds of {minutes_each:g} min, off then on then off, the on hold at the "
                    f"top current the patient tolerated on the day (planned at {top:g} mA, the "
                    f"ladder's top); a rating every {rating_every_min:g} min ({per} per hold, {3 * per} "
                    f"in all); the patient is kept blind to the current so the ratings answer the "
                    f"current and not the announcement; streaming stays on, so the band power on "
                    f"the sensing pair is read through every hold")}


def _hold_row(step, block, *, contacts, amp, rate_hz, pw, minutes, note) -> dict:
    row = {c: None for c in SHEET_COLUMNS}
    row.update({"Contacts": contacts, "Amp (mA)": amp,
                "Rate (Hz)": (None if rate_hz is None else round(float(rate_hz), 3)),
                "PW (µs)": pw, "Duration (s)": float(minutes) * 60.0,
                "General Notes / Pt Verbal Notes": note})
    row["block"] = str(block); row["step"] = int(step); row["row_kind"] = "hold"
    return row


def _and_list(items) -> str:
    """"a", "a and b", "a, b and c" -- so a sentence naming bands reads as a sentence."""
    xs = [str(x) for x in items]
    if not xs:
        return ""
    if len(xs) == 1:
        return xs[0]
    return ", ".join(xs[:-1]) + " and " + xs[-1]


def configuration_plan(side, *, rings, contact, rate_source, pulse_width_us, pulse_width_source,
                       ceiling_mA, ceiling_source, exposure, held_other_side_mA,
                       held_other_side_source, in_force_rings=None, other_side_contacts=None,
                       other_side_pw=None, rate_in_force_hz=None, min_rate_hz=PA.MIN_ADAPTIVE_RATE_HZ,
                       start_step=1) -> dict:
    """The exploratory ladder for one side at a stimulation configuration (`rings`) other than the
    one in force, built for the sensing pair `contact` (a readiness-screen cell: `channel`,
    `rate_hz`, `qualifying_centers_hz`, ...). Every field beside its source, as in `side_plan`."""
    side = str(side)
    rings = {int(r) for r in (rings or ())}
    in_force_rings = {int(r) for r in (in_force_rings or ())}
    contacts_short = _rings_label(side, rings)
    c = dict(contact or {})
    # THE SESSION RUNS AT THE RATE IN FORCE (the PI, 2026-09-22, ruling 3; decision 233), not at the
    # rate of the cell where the pain-positive bands were found. Until that ruling the cell's rate
    # was held, because at 55 Hz the half-rate harmonic lands on one of the watched bands; his call
    # is to stimulate at 55 Hz and read that band with the harmonic stated. The cell's own rate is
    # reported beside it (`cell_rate_hz`) so the difference is never silent.
    rate = rate_to_hold(rate_in_force_hz, min_rate_hz=min_rate_hz)
    rate["cell_rate_hz"] = _f(c.get("rate_hz"))
    if rate["cell_rate_hz"] is not None and abs(rate["cell_rate_hz"] - rate["rate_hz"]) > 1e-9:
        rate["why"] += (f"; the bands this session watches were found at {rate['cell_rate_hz']:g} Hz "
                        f"on the stored grid, and the session runs at {rate['rate_hz']:g} Hz by the "
                        f"PI's ruling of 2026-09-22")
    lad = ladder(ceiling_mA)
    hold = hold_per_step()
    timing = step_timing(test=hold)
    watch = sorted(float(v) for v in (c.get("qualifying_centers_hz") or []) if _f(v) is not None)
    bands = harmonic_avoidance(rate["rate_hz"])
    clear = {float(v) for v in bands.get("clear_hz") or []}
    bands["watch_hz"] = watch
    bands["watch_clear"] = bool(watch) and all(v in clear for v in watch)
    # WHICH of the watched bands sits on a harmonic, not merely that one does: the clinician needs to
    # know which reading to discount at the ladder, and at the rate in force that is the whole point
    # of the ruling. Named, never refused (decision 220).
    on_harm = [v for v in watch if v not in clear]
    bands["watch_on_harmonic_hz"] = on_harm
    bands["watch_clear_hz"] = [v for v in watch if v in clear]
    _harms = bands.get("harmonics_hz") or {}
    _names_map = bands.get("harmonic_names") or {}
    def _nearest_harmonic(v):
        if not _harms:
            return None, None
        k = min(_harms, key=lambda kk: abs(float(_harms[kk]) - v))
        return k, float(_harms[k])
    _pieces = []
    for _k in sorted({_nearest_harmonic(v)[0] for v in on_harm if _nearest_harmonic(v)[0]}):
        _hz = _harms.get(_k)
        _label = _names_map.get(_k, _k.replace("_", "-"))
        _members = [v for v in on_harm if _nearest_harmonic(v)[0] == _k]
        _pieces.append(f"{_hz:g} Hz ({_label}) lies inside the {2 * HARMONIC_HALF_WIDTH_HZ:g} Hz "
                       f"width of " + _and_list([f"{v:g}" for v in _members]) + " Hz")
    bands["watch_why"] = (
        f"the {len(watch)} band centre(s) that rise with pain on "
        f"{c.get('display_short') or c.get('channel')} on the stored grid"
        + (f" (found at {rate['cell_rate_hz']:g} Hz)" if _f(rate.get("cell_rate_hz")) is not None else "")
        + f", the ones this session watches for a fall with current at {rate['rate_hz']:g} Hz")
    bands["watch_why"] += (
        "; all of them clear of the stimulation rate's folded landings at this rate" if bands["watch_clear"]
        else (f"; at {rate['rate_hz']:g} Hz " + "; ".join(_pieces)
              + ", so those bands carry a folded multiple of the stimulation rate -- advisory, not a "
                "refusal (the PI, 2026-09-06): take care with their response to current, it does not "
                "mean they measure the stimulator rather than the brain"
              + (", and " + _and_list([f"{v:g}" for v in bands["watch_clear_hz"]]) + " Hz as clear"
                 if bands["watch_clear_hz"] else ", and none of the watched bands is clear")))
    ex = dict(exposure or {})
    first = {"ever_powered": ex.get("ever_powered"), "sentence": ex.get("sentence"),
             "stop_rule": FIRST_EXPOSURE_STOP_RULE,
             "why": ("this configuration has never carried current on this side, so the up leg is a "
                     "first exposure: every step is a side-effect check before it is a measurement"
                     if ex.get("ever_powered") is False else
                     "this configuration has carried current before; the stop rule still applies")}
    holds = acute_pain_holds(lad.get("top_mA"))
    held_mA = _f(held_other_side_mA)
    held_src = str(held_other_side_source) if held_other_side_source else "no reading for the other side"
    other = "Right" if side == "Left" else "Left"
    pw = _f(pulse_width_us)
    # the sheet rows: part A, two rows a step; part B, one row a hold
    rows = []
    contacts_pair = _bilateral_str(_strip_side_prefix(contacts_short) if side == "Left" else _strip_side_prefix(other_side_contacts),
                                   _strip_side_prefix(other_side_contacts) if side == "Left" else _strip_side_prefix(contacts_short))
    pw_pair = _bilateral(pw if side == "Left" else other_side_pw, other_side_pw if side == "Left" else pw)
    step = int(start_step)
    block_l = f"exploratory_{side.lower()}_ladder"; block_h = f"exploratory_{side.lower()}_holds"
    for cur in lad["steps_mA"]:
        amp = _bilateral(cur if side == "Left" else held_mA, held_mA if side == "Left" else cur)
        rows.extend(_sheet_row_pair(step, block_l, contacts=contacts_pair, amp=amp, rate_hz=rate["rate_hz"],
                                    pw=pw_pair, timing=timing))
        step += 1
    for h in holds["holds"]:
        amp = _bilateral(h["current_mA"] if side == "Left" else held_mA, held_mA if side == "Left" else h["current_mA"])
        every = ("every minute" if float(holds["rating_every_minutes"]) == 1.0
                 else f"every {holds['rating_every_minutes']:g} min")
        note = (f"hold {h['order']} of 3, stimulation {h['state']}: a pain rating {every} "
                f"({holds['ratings_per_hold']} in all), the patient "
                f"not told the current" + ("; the on hold is at the top current tolerated on the day"
                                            if h["state"] == "on" else ""))
        rows.append(_hold_row(step, block_h, contacts=contacts_pair, amp=amp, rate_hz=rate["rate_hz"],
                              pw=pw_pair, minutes=h["minutes"], note=note))
        step += 1
    sess = session_time_estimate(int(lad["n_steps"]))
    sess["holds_minutes"] = holds["total_minutes"]
    sess["total_minutes"] = float(sess["total_minutes"]) + float(holds["total_minutes"])
    sess["why"] = sess["why"] + f"; plus the three holds, {holds['total_minutes']:g} min"
    conditions = [
        f"stimulate on {contacts_short}: the device allows sensing on {c.get('display_short') or c.get('channel')} "
        f"only while the contacts it flanks stimulate together (decision 217)",
        f"rate {rate['rate_hz']:g} Hz, the rate in force on this side today (the PI, 2026-09-22)"
        + (f"; the bands it watches were found at {rate['cell_rate_hz']:g} Hz on the stored grid"
           if _f(rate.get("cell_rate_hz")) not in (None, rate["rate_hz"]) else "")
        + (f", and at {rate['rate_hz']:g} Hz the stimulator's own harmonics fall inside "
           + _and_list([f"{v:g}" for v in (bands.get("watch_on_harmonic_hz") or [])]) + " Hz"
           + (", leaving " + _and_list([f"{v:g}" for v in (bands.get("watch_clear_hz") or [])])
              + " Hz clear" if (bands.get("watch_clear_hz") or []) else ", leaving none of them clear")
           if (bands.get("watch_on_harmonic_hz") or []) else ""),
        "streaming on for the whole session on the sensing pair, so the voltage trace exists for every step and every hold",
        FIRST_EXPOSURE_STOP_RULE,
        "each ladder step is two clinic-sheet rows: a ramp row then a test row, 2 min a step; a pain rating at the end of every test row",
        f"then three {holds['minutes_each']:g}-minute holds, off / on / off, a rating every {holds['rating_every_minutes']:g} min, the patient blind to the current",
        f"the {other} side is HELD at its own current in force ({held_src})",
        "an off-stimulation baseline before the first step and after the last hold; an impedance test before and after at a fixed measurement current (decision 133)",
        "note the wall-clock time of each change on the clinic sheet",
    ]
    sources = {
        "stimulation": (f"the inverse of the sensing rule (decision 217): {c.get('display_short') or c.get('channel')} "
                        f"needs stimulation on rings {sorted(rings)}; in force today: rings {sorted(in_force_rings) or 'none'}"),
        "sensing_pair": "the readiness screen's best cell for this side (bravo_service._best_contact_for_side)",
        "rate_hz": ("the rate in force on this side today (the PI, 2026-09-22), "
                    + (f"lifted to the adaptive minimum ({min_rate_hz:g} Hz)" if rate["lifted"]
                       else f"held for the whole session; the watched bands come from {rate_source}")),
        "pulse_width_us": str(pulse_width_source),
        "ceiling_mA": str(ceiling_source),
        "first_exposure": "the epoch table (adapter.build_design_matrix), cathode per side per epoch; decisions 164 and 165 for the stop rule",
        "ladder": (f"0 mA up to the ceiling in {STEP_MA:g} mA steps, then down in {DOWN_STEP_MA:g} mA drops "
                   f"(the PI's ruling, 2026-09-14), stopped early by the first-exposure rule"),
        "hold": (f"within_visit.PRE_CHANGE_WINDOW_S ({SETTLED_WINDOW_S:g} s) + RAMP_EXCLUDE_S ({POST_RAMP_MARGIN_S:g} s) + {SLACK_S:g} s slack"),
        "acute_pain_holds": (f"{HOLD_MINUTES_EACH:g} min each, a rating every {HOLD_RATING_EVERY_MIN:g} min, off / on / off "
                             f"(the PI's ask of 2026-09-21: the acute effect on pain)"),
        "bands": f"{CENTRES_SOURCE}; the cell's own bands that rise with pain; harmonics of {rate['rate_hz']:g} Hz ±{HARMONIC_HALF_WIDTH_HZ:g} Hz",
        "held_other_side": held_src,
        "conditions": "decisions 133, 164, 165, 217; the PI's ruling of 2026-09-14 on the two-row step; the PI's ask of 2026-09-21",
    }
    return {
        "side": side,
        "stimulation": {"contacts_short": contacts_short, "rings": sorted(rings),
                        "in_force_rings": sorted(in_force_rings),
                        "differs_from_in_force": rings != in_force_rings},
        "sensing_pair": {"channel": c.get("channel"), "display_short": c.get("display_short"),
                         "why": (f"the device allows this pair only while the contacts it flanks "
                                 f"({', '.join(str(r) for r in sorted(rings))}) stimulate together")},
        "contact": {k: c.get(k) for k in ("channel", "display_short", "rate_hz", "n_qualifying", "n_bands",
                                          "n_responding", "n_pain_positive", "qualifying_centers_hz", "deployable")},
        "rate_hz": rate["rate_hz"], "rate_in_force_hz": rate["rate_in_force_hz"],
        # the rate of the cell where the watched bands were found, beside the rate the session runs
        # at, so a reader never has to assume they are the same (decision 233, ruling 3)
        "cell_rate_hz": rate.get("cell_rate_hz"), "rate_lifted": rate["lifted"],
        "rate_why": rate["why"], "pulse_width_us": pw, "ceiling_mA": _f(ceiling_mA),
        "held_other_side": {"current_mA": held_mA, "source": held_src},
        "first_exposure": first, "ladder": lad, "hold": hold, "step_timing": timing, "bands": bands,
        "acute_pain_holds": holds, "conditions": conditions, "sheet_rows": rows,
        "session_time": sess, "sources": sources,
        "purpose": (f"Two answers from one visit: (A) how the band power on {c.get('display_short') or c.get('channel')} "
                    f"at {', '.join(f'{v:g}' for v in watch) or 'the watched centres'} Hz moves with current on "
                    f"{contacts_short}, from the ladder's settled steps; (B) whether pain changes over minutes "
                    f"when that current is switched on and off, from the three blind holds."),
    }


def plan_for_sides(sides_inputs, *, margin, in_force=None, joint_is_safe=None, proposed=None) -> dict:
    """`{side: side_plan(...)}` for every side in `sides_inputs` (a mapping side -> kwargs for
    :func:`side_plan` minus `side`, `margin`, `held_other_side_mA`, `held_other_side_source`),
    plus the shared margin block, the optional joint-corners block, and the flat `sheet_rows`
    list. `in_force` (`bravo_service.in_force_by_side`'s output) supplies each side's current in
    force -- used to hold the OTHER side steady during a ladder (2026-09-14) and to read each
    side's programmed contacts and pulse width for the sheet."""
    in_force = dict(in_force or {})
    other_side = {"Left": "Right", "Right": "Left"}
    out = {"available": True, "sides": {}, "margin": dict(margin or {}),
           "protocol_source": PROTOCOL_SOURCE,
           "hold_s": hold_per_step()["seconds"], "step_mA": STEP_MA,
           "down_step_mA": DOWN_STEP_MA, "step_timing": step_timing(),
           "sheet_columns": list(SHEET_COLUMNS), "sheet_source": SHEET_SOURCE}
    for side, kw in sides_inputs.items():
        side = str(side)
        o = other_side.get(side)
        held_mA, held_src = None, "no reading for the other side"
        if o and isinstance(in_force.get(o), dict) and in_force[o].get("amplitude_mA") is not None:
            held_mA = in_force[o]["amplitude_mA"]
            held_src = (f"the {o} side's own setting in force today "
                        f"({in_force[o].get('source') or 'the settings stream'})")
        out["sides"][side] = side_plan(side, margin=margin, held_other_side_mA=held_mA,
                                       held_other_side_source=held_src, **kw)

    cl = (sides_inputs.get("Left") or {}).get("ceiling_mA")
    cr = (sides_inputs.get("Right") or {}).get("ceiling_mA")
    if "Left" in out["sides"] and "Right" in out["sides"]:
        out["joint_corners"] = joint_corners(cl, cr, is_safe=joint_is_safe)
    else:
        # Only one side was requested: the joint block asks about BOTH sides at once, and
        # offering it off a single side's plan would report points for a side that has no plan
        # to explain them, so it is left empty and says why rather than silently built anyway.
        out["joint_corners"] = dict(joint_corners(cl, cr, is_safe=lambda l, r: False),
                                    note="only one side was requested (Hemispheres), so no "
                                         "joint corners are offered")

    out["sheet_rows"] = build_sheet_rows(out["sides"], out["joint_corners"], in_force=in_force,
                                         timing=out["step_timing"])
    n_steps_total = sum(1 for r in out["sheet_rows"] if r.get("row_kind") == "ramp")
    out["session_time"] = session_time_estimate(n_steps_total)
    # THE EXPLORATORY LADDER(S) (2026-09-21): one per side whose best sensing pair needs a
    # stimulation configuration other than the one in force; its rows go after the others.
    out["proposed"] = {}
    for side, kw in (proposed or {}).items():
        side = str(side)
        o = other_side.get(side)
        of = dict(in_force.get(o) or {}) if o else {}
        last_step = max([int(r.get("step") or 0) for r in out["sheet_rows"]] + [0])
        p = configuration_plan(side, other_side_contacts=of.get("contacts_short"),
                               other_side_pw=of.get("pulse_width_us"), start_step=last_step + 1, **kw)
        out["proposed"][side] = p
        out["sheet_rows"].extend(p["sheet_rows"])
    return out
