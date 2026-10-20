"""Apply an exact participant's private clinical ceiling to analysis-only plans.

Measured capture currents are preserved. Missing configuration is unavailable,
never a generic current limit. Plans carry their subject, side and config digest
so copied plans cannot silently inherit another participant's clinical bounds.
"""
from __future__ import annotations

import dataclasses
import math

try:                                                    # container: /usr/src/BRAVO on the path
    from modules.StimOptimizer import safety_ceiling as _SC
    from modules.DecodeCommon import private_clinical_config as _clinical
except ImportError:                                     # host suite: BRAVO/modules is the root
    from StimOptimizer import safety_ceiling as _SC
    from DecodeCommon import private_clinical_config as _clinical

ClinicalConfigurationUnavailable = _clinical.ClinicalConfigurationUnavailable


def ceiling_for(participant_uid, side):
    """Return the configured ceiling and provenance; raise if unavailable."""
    return _SC.ceiling_for(participant_uid, side)


def _ceiling_words(ceiling_mA, provenance):
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
    digest = _clinical.config_digest()
    ceiling_mA, provenance = ceiling_for(participant_uid, side)
    if _clinical.config_digest() != digest:
        raise ClinicalConfigurationUnavailable("Clinical configuration changed while reading the ceiling; retry.")
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
                               safety_participant_uid=str(participant_uid),
                               safety_hemisphere=str(side),
                               safety_config_digest=digest,
                               amp_limit_low_note=lo_note, amp_limit_high_note=hi_note)


def ensure_applied(plan, *, participant_uid=None, side=None):
    """Revalidate a bound plan against the current private clinical configuration.

    Explicit request identity must agree with existing metadata. An unbound plan
    requires explicit identity; a numeric ceiling alone is never sufficient.
    Reapply the current ceiling, including when the private config has changed.
    """
    if plan is None:
        return None
    bound_uid = getattr(plan, "safety_participant_uid", None)
    bound_side = getattr(plan, "safety_hemisphere", None)
    uid = str(participant_uid) if participant_uid is not None else bound_uid
    hemisphere = str(side) if side is not None else bound_side
    if not uid or not hemisphere:
        raise _clinical.ClinicalConfigurationUnavailable(
            "clinical ceiling unavailable: the plan has no exact participant and side binding")
    if ((bound_uid is not None and bound_uid != uid)
            or (bound_side is not None and bound_side != hemisphere)):
        raise _clinical.ClinicalConfigurationUnavailable(
            "clinical ceiling unavailable: the plan belongs to a different participant or side")
    return apply_to_plan(plan, uid, hemisphere)
