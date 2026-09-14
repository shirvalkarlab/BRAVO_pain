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
only ceiling he has stated is the 5.0 mA hard limit of 2026-09-02 (``objective.AMP_HARD_LIMIT_MA``),
confirmed as the safety ceiling on 2026-09-12; whether a lower per-side value is wanted is being
put to him, so the number lives in ONE place -- the table below -- and nowhere else.

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
    # RCS08
    "2e3c75c00d7f4f37b53a048d195f11da": {"Left": 5.0, "Right": 5.0},
}

#: What the table's numbers rest on, printed beside every ceiling the page shows.
PI_STATED_PROVENANCE = ("stated by PI (2026-09-02 hard limit, objective.AMP_HARD_LIMIT_MA; "
                        "confirmed as the safety ceiling 2026-09-12)")
FALLBACK_PROVENANCE = "module hard limit, no PI-stated ceiling for this participant"

#: An epoch counts as TOLERATED (severity 0 at its setting) when this side's current was above zero
#: and the setting was held at least this long. Shared by the flat fit and Stage 1 so the two
#: fitters read one rule (until 2026-09-12 Stage 1 also counted epochs at 0 mA on this side as
#: tolerated anchors at zero current, and the flat fit did not; the two safe sets therefore
#: differed for the same side under the same anchors). Zero current on a side is a different
#: therapeutic state, not the low end of that side's dose axis (OBJECTIVE_SPEC amendment
#: 2026-08-29), so it says nothing about what that side tolerates.
TOLERATED_RULE = "epochs with this side's current above 0 mA held at least min_tolerated_h hours"


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


def tolerated_anchors(D, amp_col, *, min_tolerated_h):
    """The severity-0 seed: every ``(rate, current)`` this side sustained, under ``TOLERATED_RULE``."""
    d = pd.DataFrame(D)
    amp = pd.to_numeric(d[amp_col], errors="coerce")
    dur = pd.to_numeric(d["dur_h"], errors="coerce")
    keep = (amp > 0) & (dur >= float(min_tolerated_h))
    return d.loc[keep, ["freq_hz", amp_col]].to_numpy(float).reshape(-1, 2)


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
        tolerated_rule=TOLERATED_RULE,
        min_tolerated_h=float(min_tolerated_h),
    )
    return X, sev, var, meta
