"""Participant-specific clinical safety ceilings from private, provenance-bound configuration.

The search grid's hard limit is not a participant's safe ceiling. Missing clinical
evidence makes recommendations unavailable; it must never select a higher limit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .routines import objective as OBJ
try:
    from modules.DecodeCommon.private_clinical_config import (
        ClinicalConfigurationUnavailable, participant_section, config_digest)
except ImportError:
    from DecodeCommon.private_clinical_config import (
        ClinicalConfigurationUnavailable, participant_section, config_digest)

# Compatibility label for callers; this is never used to supply an amplitude.
FALLBACK_PROVENANCE = "unavailable: no participant-specific clinical ceiling"

TOLERATED_RULE = ("epochs with this side's current above 0 mA held at least min_tolerated_h hours, "
                  "and not reported moderate or severe")


def ceiling_for(participant_uid, hemisphere):
    """Return ``(ceiling_mA, provenance)`` or explicitly refuse missing evidence.

    A configured ceiling above the representable grid is conservatively clamped
    to its hard limit, with that clamp recorded in provenance.
    """
    record = participant_section(participant_uid, "safety_ceiling")
    table = record.get("values_mA")
    value = table.get(str(hemisphere)) if isinstance(table, dict) else None
    v = _validated_ceiling(value)
    hard = float(OBJ.AMP_HARD_LIMIT_MA)
    provenance = record["provenance"]
    if v > hard + 1e-9:
        return hard, (f"{provenance}; the stated {v:g} mA is above the module hard "
                      f"limit of {hard:g} mA and is clamped to it")
    return v, provenance


def _validated_ceiling(value):
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise ClinicalConfigurationUnavailable("A participant-specific ceiling is required for this side.") from exc
    if isinstance(value, bool) or not np.isfinite(v) or v <= 0:
        raise ClinicalConfigurationUnavailable("The configured ceiling must be a finite positive current in mA.")
    return v


def ceilings_by_hemisphere(participant_uid, hemispheres=("Left", "Right")):
    """``{side: (ceiling_mA, provenance)}`` for every requested side; what the service passes to
    both fitters so they seed from one source."""
    return {str(h): ceiling_for(participant_uid, h) for h in hemispheres}


def ceiling_mA_by_side(ceilings=None, sides=("Left", "Right")) -> dict:
    """Normalize explicit ceiling mappings, refusing every missing/invalid side."""
    out = {}
    src = dict(ceilings or {})
    for side in sides:
        value = src.get(str(side))
        if isinstance(value, (tuple, list)):
            value = value[0] if value else None
        out[str(side)] = min(_validated_ceiling(value), float(OBJ.AMP_HARD_LIMIT_MA))
    return out


def within_ceiling_mask(amp_left_mA, amp_right_mA, ceilings=None, *, tol_mA=1e-9) -> np.ndarray:
    """True where all supplied sides are below their explicitly configured ceilings."""
    sides = tuple(side for side, amps in (("Left", amp_left_mA), ("Right", amp_right_mA))
                  if amps is not None)
    c = ceiling_mA_by_side(ceilings, sides=sides)
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
    ceil = min(_validated_ceiling(ceiling_mA), float(OBJ.AMP_HARD_LIMIT_MA))
    out = {"current_mA": cur, "in_force_mA": cur, "ceiling_mA": ceil, "above_ceiling": False,
           "note": None, "source": source}
    if cur is None or not np.isfinite(cur) or cur <= ceil + 1e-9:
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
    c = min(_validated_ceiling(ceiling_mA), float(OBJ.AMP_HARD_LIMIT_MA))
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
    unavailable state. ``meta`` carries the ceiling, its provenance, the anchors as lists, and the counts,
    so a report can print exactly what the safety model was told.
    """
    from .routines import surrogate as SUR

    if ceiling is None:
        ceiling = ceiling_for(None, None)
    ceiling_mA = min(_validated_ceiling(ceiling[0]), float(OBJ.AMP_HARD_LIMIT_MA))
    provenance = str(ceiling[1])
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
