"""The titration session the Stim Optimizer page recommends for the next visit, designed from THIS
participant's own record (open item 30, decision 124's protocol; the PI's decision of 2026-09-12
evening: "make #4 a feature of next stim opt recommendation combined with 30").

WHAT THIS IS FOR. Two things wait on the same session. (1) The pooled current-to-power slope
that the Closed-Loop page's D19 rule and its evidence triangle read rests on 11-13 settled points
across 3-4 runs of rising current on RCS08, at most 6 currents per run; a straight line through
that few points can be flipped by removing two of them, which is exactly what the 20 s post-ramp
margin did (decision 144), so the margin ships OFF (`ClosedLoopDeployment/post_ramp.py`). (2) No
run in the record has the 8 settled settings the curvature test needs (decision 55,
`amplitude_effect.MIN_POINTS_CURVATURE`), so whether the response has a peak is not answerable.
One titration session designed as below gives 21 settled points on its own, 11 of them distinct
currents on the rising leg, and once such a run exists the margin has enough points that no two
of them can flip a verdict -- that is the condition under which the margin is switched on.

WHERE IT IS ON SCREEN. Stim Optimizer page, the card "Titration session to run next", directly
under "What to test at the next visit". The response carries it under `titration_plan`
(`bravo_service.titration_plan_block` assembles the inputs; everything here is pure arithmetic on
values the request already holds). NOTHING HERE WRITES TO THE DEVICE: it is a sheet a clinician
reads at the visit.

EVERY NUMBER CARRIES WHERE IT CAME FROM: each side's block has a `sources` mapping, one entry per
field, so the page can print the origin beside the value and a reader can check it.

NO DJANGO, NO STORE, NO RECORDINGS ARE READ HERE. The service reads the two stored tables (the
pooled current-to-power table and the per-run points table) once and hands their frames in.
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

#: The current step of the ladder (mA). The research synthesis §1 and open item 30: 0.5 mA steps
#: from 0 mA to the ceiling, up and then down.
STEP_MA = 0.5

#: Ten seconds of slack on top of the settled window and the margin, so a step that starts a
#: little late still holds the full window.
SLACK_S = 10.0

#: The settled window (30 s), the piece length (3 s) and the minimum pieces per settled setting
#: (10) are the analysis's own constants, read from `within_visit` rather than typed again.
SETTLED_WINDOW_S = float(WV.PRE_CHANGE_WINDOW_S)
PIECE_S = float(WV.CHUNK_S)
MIN_PIECES_PER_SETTING = int(WV.MIN_CHUNKS_PRE_CHANGE)
POST_RAMP_MARGIN_S = float(WV.RAMP_EXCLUDE_S)

PROTOCOL_SOURCE = ("artifacts/research_2026-09-11_stim_amplitude_vs_lfp_power.md §1 'What would "
                   "let a peak be estimated'; open item 30; decision 144 (the margin is switched on "
                   "once such a session exists)")


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
def ladder(ceiling_mA, *, step_mA=STEP_MA) -> dict:
    """0 mA to the ceiling in `step_mA` steps, UP and then DOWN, the top step held once. The top
    step never exceeds the ceiling: a ceiling that is not a multiple of the step is rounded DOWN
    to the last step below it, never up."""
    c = _f(ceiling_mA)
    if c is None or c <= 0:
        return {"step_mA": float(step_mA), "top_mA": None, "steps_mA": [], "n_steps": 0,
                "n_distinct_currents": 0, "compact": "—",
                "why": "no ceiling is stated for this side, so no ladder can be written"}
    s = float(step_mA)
    n_up = int(math.floor(c / s + 1e-9))            # steps above 0, never past the ceiling
    up = [round(i * s, 3) for i in range(0, n_up + 1)]
    down = list(reversed(up[:-1]))
    steps = up + down
    top = up[-1]
    compact = (f"0 → {s:.1f} → … → {top:.1f} → … → 0 mA" if len(up) > 3
               else " → ".join(f"{v:.1f}" for v in steps) + " mA")
    return {"step_mA": s, "top_mA": top, "steps_mA": steps, "n_steps": len(steps),
            "n_distinct_currents": len(up), "compact": compact,
            "why": (f"0 mA to {top:g} mA in {s:g} mA steps and back down: {len(up)} distinct "
                    f"currents on the way up, {len(steps)} steps in all, the top step held once"
                    + ("" if abs(top - c) < 1e-9 else
                       f"; the stated ceiling of {c:g} mA is not a multiple of {s:g} mA, so the top "
                       f"step is the last one below it"))}


# ---------------------------------------------------------------------------------------------
# the hold per step
# ---------------------------------------------------------------------------------------------
def hold_per_step(*, settled_window_s=SETTLED_WINDOW_S, margin_s=POST_RAMP_MARGIN_S,
                  slack_s=SLACK_S, piece_s=PIECE_S, min_pieces=MIN_PIECES_PER_SETTING) -> dict:
    """At least 60 s per step: the 30 s settled window the analysis averages, the 20 s after a
    current move the post-ramp margin will discard once it is switched on, and 10 s of slack."""
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
# one side's plan
# ---------------------------------------------------------------------------------------------
def side_plan(side, *, rate_in_force_hz, rate_source, pulse_width_us, pulse_width_source,
              ceiling_mA, ceiling_source, contact, contact_source, record_today, margin,
              candidate_center_hz=None, min_rate_hz=PA.MIN_ADAPTIVE_RATE_HZ) -> dict:
    """The whole plan for one side, every field beside its source.

    `contact` is a dict from the readiness screen (`channel`, `display_short`, `n_responding`,
    `n_bands`, `laterality`, `deployable`, `rate_hz`, `note`) or None; `record_today` is
    :func:`record_today_for_contact`'s output; `margin` is
    `ClosedLoopDeployment.post_ramp.margin_becomes_available`'s output.
    """
    rate = rate_to_hold(rate_in_force_hz, min_rate_hz=min_rate_hz)
    lad = ladder(ceiling_mA)
    hold = hold_per_step()
    bands = harmonic_avoidance(rate["rate_hz"], candidate_center_hz=candidate_center_hz)
    n_points = int(lad["n_steps"])
    n_up = int(lad["n_distinct_currents"])
    need = int((margin or {}).get("min_settled_settings") or 0) or None
    rec = dict(record_today or {})
    pw = _f(pulse_width_us)

    contact_block = None
    if contact:
        contact_block = {k: contact.get(k) for k in ("channel", "display_short", "display_hemisphere",
                                                      "display_contacts", "n_responding", "n_bands",
                                                      "laterality", "deployable", "rate_hz",
                                                      "responding_fraction", "median_separation_d",
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
                    "responding bands)"))
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
        "streaming on for the whole session, so the voltage trace exists for every step",
        "an off-stimulation baseline before the first step and after the last",
        ("an impedance test before and after, at a FIXED measurement current, not the device's "
         "automatic low-current mode, which reads spuriously high (decision 133)"),
        (f"every step held {hold['seconds']:g} s or longer; note the wall-clock time of each "
         f"current change on the clinic sheet"),
    ]
    sources = {
        "rate_hz": (f"{rate_source}; lifted to the adaptive minimum ({min_rate_hz:g} Hz, "
                    f"percept_adaptive.MIN_ADAPTIVE_RATE_HZ, decision 138)" if rate["lifted"]
                    else rate_source),
        "pulse_width_us": pulse_width_source,
        "ceiling_mA": ceiling_source,
        "sensing_contact": contact_source,
        "ladder": (f"0 mA to the stated ceiling in {STEP_MA:g} mA steps, up then down "
                   f"(research synthesis §1; open item 30)"),
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
        "conditions": "research synthesis §1; decision 133 (impedance)",
    }
    return {
        "side": str(side),
        "rate_hz": rate["rate_hz"], "rate_in_force_hz": rate["rate_in_force_hz"],
        "rate_lifted": rate["lifted"], "rate_why": rate["why"],
        "pulse_width_us": pw,
        "pulse_width_note": (None if pw is not None else
                             "no pulse width is on record for this side; hold the one programmed at the visit"),
        "ceiling_mA": _f(ceiling_mA),
        "sensing_contact": contact_block,
        "sensing_contact_note": (None if contact_block else
                                 f"the readiness screen has no cell for {side} stimulation, so no "
                                 f"sensing contact is named; record from the contact the Closed-Loop "
                                 f"page's committed band sits on"),
        "ladder": lad, "hold": hold, "bands": bands, "conditions": conditions,
        "yield": yield_block, "sources": sources,
    }


def _yield_sentence(n_points, n_up, rec, margin) -> str:
    have = rec.get("points")
    runs = rec.get("runs")
    per_run = rec.get("max_settled_settings_in_one_run")
    need = (margin or {}).get("min_settled_settings")
    exists = (margin or {}).get("available")
    on = (margin or {}).get("switch_on")
    today = (f"today this contact holds {_n(have, 'settled point')} across {_n(runs or 0, 'run')}"
             + (f", at most {per_run} currents in any one run" if per_run is not None else "")
             if have is not None else
             ("today no pooled points are stored for this contact"
              + (f" (at most {per_run} currents in any one run)" if per_run is not None else "")))
    session = (f"this session yields {n_points} settled points, {n_up} distinct currents on the "
               f"way up")
    if need:
        if exists:
            m = (f"a run with at least {need} settled settings already exists, so the 20 s post-ramp "
                 f"margin (decision 144) " + ("is switched on" if on else
                                              "can be switched on (it is off today)"))
        else:
            m = (f"no run in the record has the {need} settled settings the margin needs, so the "
                 f"20 s post-ramp margin (decision 144) stays off until this session is recorded; "
                 f"its rising leg alone gives {n_up}")
    else:
        m = "whether the 20 s post-ramp margin can be switched on could not be judged (no per-run table)"
    return f"{today}; {session}; {m}."


def plan_for_sides(sides_inputs, *, margin) -> dict:
    """`{side: side_plan(...)}` for every side in `sides_inputs` (a mapping side -> kwargs for
    :func:`side_plan` minus `side` and `margin`), plus the shared margin block and the protocol
    source."""
    out = {"available": True, "sides": {}, "margin": dict(margin or {}),
           "protocol_source": PROTOCOL_SOURCE,
           "hold_s": hold_per_step()["seconds"], "step_mA": STEP_MA}
    for side, kw in sides_inputs.items():
        out["sides"][str(side)] = side_plan(side, margin=margin, **kw)
    return out
