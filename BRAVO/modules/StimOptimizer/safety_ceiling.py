"""The safety model's amplitude ceiling: a value the PI states, per participant and per side.

WHAT THIS REPLACES (2026-09-12, the PI's decision on item 3 of the "Make Closed-Loop Work"
session). The safety model -- the Gaussian process over side-effect severity whose safe set decides
the reachable ceiling, the queue's ``safe`` column, the batches and the in-envelope optimum -- needs
one kind of pseudo-observation it cannot get from the pain reports: settings a clinician judged to
be the EDGE of acceptable, encoded as severity 3 (``objective.SE_THRESHOLD``). Until today those
came from ``UpperLimitInMilliAmps`` in the device's own files: first a hard-coded snapshot of
twelve (rate, current) pairs read off RCS08's record in 2026-08 (``plots.LIMIT_ANCHORS``), then,
behind a switch shipped off, every such limit in the participant's settings stream (review S8,
decision 143). Both were wrong in kind. A programmed upper limit is the range the clinician let
the patient adjust within, or the range the device's own adaptive controller moves in (decision
136); it is not a statement that side effects begin there. Measured on RCS08 with the stream's
limits on, the Left side's reachable ceiling fell from 5.0 to 0.1 mA on a record where 4.5-4.8 mA
had been delivered and tolerated for weeks.

WHAT IT IS NOW. The severity-3 seed is ONE current per side, stated by the PI, placed at every
stimulation rate on the search grid: "above this current, on this side, is not acceptable". The
first ceiling he stated was the 5.0 mA hard limit of 2026-09-02
(``objective.AMP_HARD_LIMIT_MA``), confirmed as the safety ceiling on 2026-09-12. **He lowered it
on 2026-09-14**, his instruction verbatim: "make max safe amp on each side 4.5 mA, PI decided" --
RCS08's own ceiling is now 4.5 mA on both sides, still below the 5.0 mA module hard limit
(``AMP_HARD_LIMIT_MA``, which is a different thing: the highest amplitude the search grid can
represent at all, not a participant's own stated ceiling -- see ``routines/plots.py``'s
``AMP_GRID``). The number lives in ONE place -- the table below -- and nowhere else.

WHERE IT REACHES THE PAGE. Stim Optimizer page: the per-arm cards ("safe ceiling N mA", the amber
"above the reachable safe ceiling" mark), the queue table's ``safe`` column, the blockers list,
and, under "Two-stage plan", each side's safe-cell count and the gate's "under the ceiling" check.
The ceiling and its provenance are in the response under ``arms.<arm>.safety_anchors`` and
``two_stage.stage1.audit.per_hemisphere.<side>.safety_ceiling``.

THE RESPONSE KEY. ``bravo_service._code_digest`` hashes every ``.py`` file in this package, this
one included, so changing a number in the table changes the key and every stored response
rebuilds once. That is deliberate: a ceiling edited here must never be served from a copy computed
under the old one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .routines import objective as OBJ

#: THE ONE PLACE TO CHANGE A PARTICIPANT'S CEILING. Participant uid -> side -> current in mA.
#: A side that is absent, or a participant that is absent, falls back to the module hard limit
#: with a provenance that says so; nothing is invented.
PI_STATED_CEILING_MA = {
    # RCS08 -- 4.5 mA on both sides, lowered from 5.0 mA on 2026-09-14 (his words, verbatim:
    # "make max safe amp on each side 4.5 mA, PI decided").
    "2e3c75c00d7f4f37b53a048d195f11da": {"Left": 4.5, "Right": 4.5},
}

#: What the table's numbers rest on, printed beside every ceiling the page shows.
PI_STATED_PROVENANCE = ("stated by PI, 2026-09-14 (was 5.0 mA, stated 2026-09-02 as the hard "
                        "limit and confirmed as the safety ceiling 2026-09-12)")
FALLBACK_PROVENANCE = "module hard limit, no PI-stated ceiling for this participant"

#: An epoch counts as TOLERATED (severity 0 at its setting) when this side's current was above zero
#: and the setting was held at least this long. Shared by the flat fit and Stage 1 so the two
#: fitters read one rule (until 2026-09-12 Stage 1 also counted epochs at 0 mA on this side as
#: tolerated anchors at zero current, and the flat fit did not; the two safe sets therefore
#: differed for the same side under the same anchors). Zero current on a side is a different
#: therapeutic state, not the low end of that side's dose axis (OBJECTIVE_SPEC amendment
#: 2026-08-29), so it says nothing about what that side tolerates.
TOLERATED_RULE = ("epochs with this side's current above 0 mA held at least min_tolerated_h hours, "
                  "and not reported moderate or severe")


def ceiling_for(participant_uid, hemisphere):
    """``(ceiling_mA, provenance)`` for one side of one participant.

    A stated ceiling above the module hard limit is clamped to it, because the search grid stops
    there (``plots.AMP_GRID``) and a cell above the grid cannot be scored; the provenance says the
    clamp happened. ``None`` for the participant or the side means the fallback.
    """
    hard = float(OBJ.AMP_HARD_LIMIT_MA)
    table = PI_STATED_CEILING_MA.get(str(participant_uid)) if participant_uid is not None else None
    value = table.get(str(hemisphere)) if isinstance(table, dict) else None
    if value is None:
        return hard, FALLBACK_PROVENANCE
    v = float(value)
    if not np.isfinite(v) or v <= 0:
        raise ValueError(f"a stated ceiling must be a positive current in mA, got {value!r} "
                         f"for {participant_uid} {hemisphere}")
    if v > hard + 1e-9:
        return hard, (f"{PI_STATED_PROVENANCE}; the stated {v:g} mA is above the module hard "
                      f"limit of {hard:g} mA and is clamped to it")
    return v, PI_STATED_PROVENANCE


def ceilings_by_hemisphere(participant_uid, hemispheres=("Left", "Right")):
    """``{side: (ceiling_mA, provenance)}`` for every requested side; what the service passes to
    both fitters so they seed from one source."""
    return {str(h): ceiling_for(participant_uid, h) for h in hemispheres}


def ceiling_mA_by_side(ceilings=None, sides=("Left", "Right")) -> dict:
    """``{side: ceiling_mA}`` from whatever form a caller holds -- ``{side: (mA, provenance)}``
    (``ceilings_by_hemisphere``'s own output), ``{side: mA}``, or ``None`` -- with every side in
    ``sides`` present. A side the mapping does not name gets THIS module's own fallback
    (``ceiling_for(None, side)``, the module hard limit), never a number typed where it is read
    (decision 308: a typed 4.5 mA fallback in the next-visit list was RCS08's ceiling written into
    code that serves every participant)."""
    out = {}
    src = dict(ceilings or {})
    for side in sides:
        v = src.get(str(side))
        if isinstance(v, (tuple, list)):
            v = v[0] if len(v) else None
        try:
            v = None if v is None else float(v)
        except (TypeError, ValueError):
            v = None
        if v is None or not np.isfinite(v):
            v = float(ceiling_for(None, side)[0])
        out[str(side)] = v
    return out


def within_ceiling_mask(amp_left_mA, amp_right_mA, ceilings=None, *, tol_mA=1e-9) -> np.ndarray:
    """True where a (left current, right current) cell is at or below BOTH sides' ceilings.

    The HARD bound every proposal is clipped to (decision 308). The safety model's safe set is a
    soft bound -- a Gaussian process seeded at the ceiling -- and on a record where currents above
    today's ceiling were delivered and tolerated before it was lowered (RCS08: 4.8 mA on the left,
    ceiling 4.5 mA since 2026-09-14) nothing in the model itself guarantees a safe cell sits at or
    below the stated current. ``amp_right_mA`` may be ``None`` for a one-side grid (the per-side
    fit), and ``amp_left_mA`` ``None`` likewise."""
    c = ceiling_mA_by_side(ceilings)
    keep = None
    for side, amps in (("Left", amp_left_mA), ("Right", amp_right_mA)):
        if amps is None:
            continue
        m = np.asarray(amps, dtype=float) <= c[side] + float(tol_mA)
        keep = m if keep is None else (keep & m)
    return np.asarray(True if keep is None else keep, dtype=bool)


def held_at_or_below_ceiling(current_mA, ceiling_mA, *, side, source=None) -> dict:
    """The current a side is HELD at while the other side's ladder runs, never above its ceiling.

    The held side's current in force is copied into every ladder row and the clinic sheet; until
    decision 308 it was copied as it stood. When it is above today's ceiling -- a setting programmed
    before the ceiling was lowered -- it is held AT the ceiling instead, and the returned ``note``
    says so in plain words for the card, the sheet caption and the conditions list. Holding at the
    ceiling rather than refusing the ladder: the ladder measures the OTHER side, which only needs
    this side held constant, and the ceiling is the nearest current to the one in force that the
    page may propose. ``current_mA`` None means no reading, returned as such."""
    cur = None if current_mA is None else float(current_mA)
    ceil = None if ceiling_mA is None else float(ceiling_mA)
    out = {"current_mA": cur, "in_force_mA": cur, "ceiling_mA": ceil, "above_ceiling": False,
           "note": None, "source": source}
    if cur is None or ceil is None or not np.isfinite(cur) or cur <= ceil + 1e-9:
        return out
    out["current_mA"] = ceil
    out["above_ceiling"] = True
    out["note"] = (f"the {side} side's current in force, {cur:g} mA, is above today's safe ceiling "
                   f"for that side, {ceil:g} mA; "
                   f"it is held at {ceil:g} mA for this ladder, not at the current in force -- set "
                   f"it to {ceil:g} mA before the first step")
    return out


def ceiling_anchors(ceiling_mA, freq_grid):
    """The severity-3 seed: one ``(rate_hz, ceiling_mA)`` pair per stimulation rate on the grid.

    The shape the safety model already expects from ``SafetyGP.seed_from_history`` -- an
    ``(n, 2)`` array of (frequency, current) pairs -- so the model's own code is untouched. One
    anchor per rate makes the ceiling a flat line across the rate axis, which is what a stated
    "not above N mA on this side" means; a single anchor at one rate would let the GP's length
    scale in frequency decide how far the statement reaches.
    """
    c = float(ceiling_mA)
    return np.array([[float(f), c] for f in freq_grid], dtype=float).reshape(-1, 2)


def _intolerable_mask(d) -> pd.Series:
    """True where the epoch carries a REPORTED severity in ``objective.SE_HARD_REJECT``. Absent
    column, None or NaN is False: an unreported side effect is not a reported one (the same
    distinction ``objective.build_objective`` keeps with ``se_observed``)."""
    if "se_severity" not in d.columns:
        return pd.Series(False, index=d.index)
    sev = d["se_severity"].map(lambda v: str(v).strip().lower() if isinstance(v, str) else None)
    return sev.isin(OBJ.SE_HARD_REJECT).fillna(False).astype(bool)


def tolerated_anchors(D, amp_col, *, min_tolerated_h):
    """The severity-0 seed: every ``(rate, current)`` this side sustained, under ``TOLERATED_RULE``.

    2026-09-15 (audit finding 5a): an epoch the clinic sheet scored moderate or severe is barred
    from the pain fit (``objective.SE_HARD_REJECT``, J = +inf) and until today was STILL handed
    here as a severity-0 anchor because only current and hold time were checked -- telling the
    safety model the opposite of what was reported. A reported intolerable severity now excludes
    the epoch. Nothing else changed: a frame without the column, an unreported epoch and a mild
    one are tolerated exactly as before.
    """
    d = pd.DataFrame(D)
    amp = pd.to_numeric(d[amp_col], errors="coerce")
    dur = pd.to_numeric(d["dur_h"], errors="coerce")
    keep = (amp > 0) & (dur >= float(min_tolerated_h)) & ~_intolerable_mask(d)
    return d.loc[keep, ["freq_hz", amp_col]].to_numpy(float).reshape(-1, 2)


def n_intolerable_excluded(D, amp_col, *, min_tolerated_h) -> int:
    """How many epochs would have been tolerated anchors on current and hold time alone but were
    kept out because their reported severity is moderate or severe -- for the report."""
    d = pd.DataFrame(D)
    amp = pd.to_numeric(d[amp_col], errors="coerce")
    dur = pd.to_numeric(d["dur_h"], errors="coerce")
    return int(((amp > 0) & (dur >= float(min_tolerated_h)) & _intolerable_mask(d)).sum())


def safety_seed(D, amp_col, *, freq_grid, ceiling=None, min_tolerated_h=72.0):
    """``(X, severity, severity_var, meta)`` for ``SafetyGP.fit``, the one call both fitters make.

    ``ceiling`` is ``(ceiling_mA, provenance)`` from :func:`ceiling_for`; ``None`` means the
    fallback. ``meta`` carries the ceiling, its provenance, the anchors as lists, and the counts,
    so a report can print exactly what the safety model was told.
    """
    from .routines import surrogate as SUR

    if ceiling is None:
        ceiling = ceiling_for(None, None)
    ceiling_mA, provenance = float(ceiling[0]), str(ceiling[1])
    limits = ceiling_anchors(ceiling_mA, freq_grid)
    deliv = tolerated_anchors(D, amp_col, min_tolerated_h=min_tolerated_h)
    X, sev, var = SUR.SafetyGP.seed_from_history(deliv, limits)
    meta = dict(
        safety_ceiling_mA=ceiling_mA,
        safety_ceiling_provenance=provenance,
        safety_ceiling_anchors=[[float(a), float(b)] for a, b in limits],
        n_safety_ceiling_anchors=int(len(limits)),
        n_tolerated_anchors=int(len(deliv)),
        n_intolerable_excluded=n_intolerable_excluded(D, amp_col, min_tolerated_h=min_tolerated_h),
        tolerated_rule=TOLERATED_RULE,
        min_tolerated_h=float(min_tolerated_h),
    )
    return X, sev, var, meta
