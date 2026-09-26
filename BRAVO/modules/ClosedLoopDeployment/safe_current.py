"""The PI-stated safe current ceiling, applied to every current the Closed-Loop page recommends.

WHY THIS FILE EXISTS (decision 306, found live 2026-09-26). The decision card's "Values to enter on
the A610" read "Adaptive amplitude limit, upper 4.80 mA" for RCS08 (L 1-3+ at 24.5 Hz), above the
4.5 mA per side the PI stated on 2026-09-14 ("make max safe amp on each side 4.5 mA, PI decided";
decisions 145, 160). The upper limit inherits the upper capture current (D28), which this module
takes as the highest therapeutic current on record for the cell -- 4.8 mA, delivered before the
ceiling was stated -- and nothing here read the ceiling; only the Stim Optimizer did. The CL-DBS
simulation ran its controller between the same limits and so commanded 4.8 mA as well.

THE ONE HOME of the number stays ``StimOptimizer/safety_ceiling.py`` (``PI_STATED_CEILING_MA``,
``ceiling_for``). It is imported, not copied, in the same two spellings ``device_facts`` uses for its
Stim Optimizer import, so the container and the host suite each read the one module object their
runner already holds. Moving the table to DecodeCommon was considered and not done: the Stim
Optimizer's response key hashes its own package's code (decision 41), so a move would rebuild every
stored Stim Optimizer answer for no change in any number.

CAP, NOT REFUSE. A limit above the ceiling is lowered to the ceiling and the row says so in one
sentence. It is not a device-rule refusal because the rule table holds only rules traceable to a
Medtronic document (the ceiling is the PI's statement about one participant), and because a refusal
withholds the whole table for a value that has an obvious safe replacement: the ceiling itself, a
current the record shows was delivered. The thresholds are NOT moved: they were read at the measured
currents, which the plan keeps as ``capture_amp_low``/``capture_amp_high``.
"""
from __future__ import annotations

import dataclasses
import math

try:                                                    # container: /usr/src/BRAVO on the path
    from modules.StimOptimizer import safety_ceiling as _SC
except ImportError:                                     # host suite: BRAVO/modules is the root
    from StimOptimizer import safety_ceiling as _SC

#: Printed where the ceiling in force is the module hard limit because none was stated.
_HARD_LIMIT_WORDS = "module hard limit (no safe ceiling is stated for this participant)"


def ceiling_for(participant_uid, side):
    """``(ceiling_mA, provenance)`` for one side, from the one home; the module hard limit (5.0 mA)
    with a provenance saying so when the participant or the side has no stated ceiling."""
    return _SC.ceiling_for(participant_uid, side)


def _ceiling_words(ceiling_mA, provenance):
    if provenance == _SC.FALLBACK_PROVENANCE:
        return f"{ceiling_mA:g} mA {_HARD_LIMIT_WORDS}"
    return f"{ceiling_mA:g} mA safe ceiling"


def cap(value, ceiling_mA, provenance, *, was):
    """``(value_to_recommend, note)``. ``note`` is one plain sentence when the ceiling lowered the
    value, naming what it was (``was``, e.g. "the highest current measured"), else None. A missing
    or non-numeric value passes through untouched."""
    if value is None:
        return None, None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return value, None
    if not math.isfinite(v) or v <= float(ceiling_mA) + 1e-9:
        return value, None
    return float(ceiling_mA), (f"Capped at the {_ceiling_words(float(ceiling_mA), provenance)}; "
                               f"{was} was {v:g} mA.")


def apply_to_plan(plan, participant_uid, side):
    """A copy of ``plan`` whose adaptive amplitude limits sit at or below the ceiling for ``side``.

    The measured capture currents are kept. When the capped lower limit would reach the capped
    upper one (both measured currents above the ceiling) no range is left for the controller to
    move in; the limits are still capped, the note says so, and the replay refuses the degenerate
    pair as it refuses any other."""
    if plan is None:
        return None
    ceiling_mA, provenance = ceiling_for(participant_uid, side)
    lo, lo_note = cap(plan.capture_amp_low, ceiling_mA, provenance,
                      was="the lowest current measured")
    hi, hi_note = cap(plan.capture_amp_high, ceiling_mA, provenance,
                      was="the highest current measured")
    if lo is not None and hi is not None and not (float(hi) > float(lo)):
        lo_note = ((lo_note or "") + " No range is left below the ceiling for the controller to "
                   "move in.").strip()
    return dataclasses.replace(plan, amp_limit_low=lo, amp_limit_high=hi,
                               safety_ceiling_mA=float(ceiling_mA),
                               safety_ceiling_provenance=str(provenance),
                               amp_limit_low_note=lo_note, amp_limit_high_note=hi_note)


def ensure_applied(plan):
    """``plan`` itself when a ceiling was applied; otherwise a copy held to the module hard limit, so
    a caller that skipped the pipeline still cannot print or replay a limit above 5.0 mA."""
    if plan is None or getattr(plan, "safety_ceiling_mA", None) is not None:
        return plan
    return apply_to_plan(plan, None, None)
