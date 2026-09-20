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

#: A band centre this close to a harmonic of the stimulation rate is not analysed: the band is
#: measuring the stimulator, not the brain. 2.5 Hz is half the 5 Hz band width the stored tables
#: use (`clinic_steps.BAND_HALF_HZ`), so a centre inside this distance has the harmonic inside its
#: own band.
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
# the band centres to analyse and to avoid
# ---------------------------------------------------------------------------------------------
def harmonic_avoidance(rate_hz, *, centres_hz=CENTRES_HZ, half_width_hz=HARMONIC_HALF_WIDTH_HZ,
                       candidate_center_hz=None) -> dict:
    """Which of the 22 centres are clear of the stimulation rate's harmonics at `rate_hz`, and
    which are within `half_width_hz` of one. The harmonics: |250 - rate| (the rate folded about
    the device's 250 Hz sampling rate), and the rate's 1/2, 1/4 and 3/4 sub-harmonics (research
    synthesis §1; decision 124). `candidate_center_hz`, when known, is judged the same way and
    reported on its own."""
    r = float(rate_hz)
    harmonics = {"folded_about_250_hz": abs(250.0 - r), "half_rate": r / 2.0,
                 "quarter_rate": r / 4.0, "three_quarters_rate": 3.0 * r / 4.0}
    names = {"folded_about_250_hz": "|250 − rate|", "half_rate": "half the rate",
             "quarter_rate": "a quarter of the rate", "three_quarters_rate": "three quarters of the rate"}
    clear, avoid, reasons = [], [], {}
    for c in centres_hz:
        hits = [(k, h) for k, h in harmonics.items() if abs(float(c) - h) <= float(half_width_hz) + 1e-9]
        if hits:
            avoid.append(float(c))
            reasons[f"{float(c):g}"] = "; ".join(
                f"within {half_width_hz:g} Hz of {h:g} Hz ({names[k]})" for k, h in hits)
        else:
            clear.append(float(c))
    out = {"rate_hz": r, "harmonics_hz": harmonics, "half_width_hz": float(half_width_hz),
           "centres_hz": [float(c) for c in centres_hz], "clear_hz": clear, "avoid_hz": avoid,
           "avoid_reasons": reasons, "n_clear": len(clear), "n_avoid": len(avoid),
           "why": (f"at {r:g} Hz the stimulator shows up at {harmonics['folded_about_250_hz']:g}, "
                   f"{harmonics['half_rate']:g}, {harmonics['quarter_rate']:g} and "
                   f"{harmonics['three_quarters_rate']:g} Hz; a band centre within "
                   f"{half_width_hz:g} Hz of one of those measures the stimulator, not the brain")}
    cc = _f(candidate_center_hz)
    if cc is not None:
        hits = [(k, h) for k, h in harmonics.items() if abs(cc - h) <= float(half_width_hz) + 1e-9]
        out["candidate_center_hz"] = cc
        out["candidate_clear"] = not hits
        out["candidate_note"] = (f"{cc:g} Hz is clear of every harmonic" if not hits else
                                 f"{cc:g} Hz is " + "; ".join(
                                     f"within {half_width_hz:g} Hz of {h:g} Hz ({names[k]})"
                                     for k, h in hits))
    return out


# ---------------------------------------------------------------------------------------------
# what the record holds today on a contact, from the two stored tables
# ---------------------------------------------------------------------------------------------
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
        "bands": (f"{CENTRES_SOURCE}; harmonics |250 − rate|, rate/2, rate/4, 3·rate/4 (research "
                  f"synthesis §1); ±{HARMONIC_HALF_WIDTH_HZ:g} Hz"),
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


def plan_for_sides(sides_inputs, *, margin, in_force=None, joint_is_safe=None) -> dict:
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
    return out
