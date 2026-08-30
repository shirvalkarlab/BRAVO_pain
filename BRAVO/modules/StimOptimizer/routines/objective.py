"""Composite objective construction for stimulation-parameter optimization.

Implements section 2 of OBJECTIVE_SPEC.md. Nothing here fits a model; this module turns
epoch-level pain reports plus side-effect severity into the scalar J the surrogate regresses,
together with the per-observation variance that carries the warm-start weighting.

The sign convention is fixed throughout the module: **J is minimised, lower is better.**
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

# --- section 2.3: the side-effect ladder, in NRS points ---------------------------------
# Calibration statement (OBJECTIVE_SPEC 2.3): one mild side effect cancels exactly 1.0 NRS
# point of benefit. Moderate and severe are HARD INFEASIBLE, not large finite penalties.
#
# Sarikhani et al. could use a finite penalty of 4 to mean "always rejected" because their
# tremor term was bounded to [-4, 4], so no efficacy gain could outweigh it. J_pain here is
# baseline-subtracted NRS referenced to an incumbent at 7.28, so it is bounded below by -7.28:
# a finite penalty of 4.0 would be beaten by any cell showing more than 4 NRS points of
# improvement (7.3 -> 3.3, which is clinically conceivable). Encoding the trade-off as +inf is
# the only way the stated guarantee is actually true.
SE_LADDER = {"none": 0.0, "mild": 1.0, "moderate": np.inf, "severe": np.inf}

# Severity labels that make a cell ineligible for selection outright. Infeasible cells are NOT
# discarded: they are excluded from the objective surrogate's argmin (an intolerable setting
# carries no useful information about where the pain optimum is) while still informing the
# safety GP, which is how a constrained Bayesian optimizer is supposed to treat them.
SE_HARD_REJECT = frozenset({"moderate", "severe"})
SE_SEVERITY_RANK = {"none": 0, "mild": 1, "moderate": 2, "severe": 3}
SE_THRESHOLD = 3.0  # severity scale value that defines the unsafe boundary

# --- section 2.2: the pain metric is a CHOICE, and it is now an explicit one -------------
#
# Which pain report the optimizer treats as its outcome is a scientific decision, not an
# implementation detail, so it is a named, registered object rather than a hard-coded column.
#
# Empirical basis for the default (acute clinic-testing set, 2025-07 to 2026-08, n = 442 steps
# at or above the 60 s threshold across 24 visits, visit fixed effects, cluster-robust by visit):
# the site-specific reports detect a stimulation on/off effect of roughly 1.2-1.3 NRS points at
# the left leg (p = 0.016) and the back (p = 0.020), while the single "Overall" rating does not
# detect it at all (+0.27, p = 0.25). The Overall rating correlates 0.84 with the back score but
# only 0.71 with the left leg, i.e. when this participant reports one global number she is
# largely reporting her back, which is why a left-leg-specific effect is invisible in it.
# Optimising the Overall score would therefore optimise the wrong quantity.
#
# Canonical item name -> the column names it may appear under. The chronic REDCap epoch frame
# and the acute clinic-testing frame use different names for the same construct; resolution
# tries each candidate in order and fails loudly if none is present.
ITEM_COLUMNS = {
    "left_leg":   ("left_leg_vas", "pain_Left_Leg"),
    "left_foot":  ("left_foot_vas", "pain_Left_Foot"),
    "back":       ("back_vas", "pain_Back"),
    "right_leg":  ("right_leg_vas", "pain_Right_Leg"),
    "right_foot": ("right_foot_vas", "pain_Right_Foot"),
    "overall":    ("nrs", "pain_Overall"),
    "vas":        ("vas",),
    "mpq_sum":    ("mpq_sum",),
    "relief":     ("relief",),
}


# The same construct is recorded on DIFFERENT SCALES in the two frames: the chronic REDCap items
# ending in `_vas` are 0-100 visual analogue scales, while the acute clinic-testing items are 0-10
# numeric rating scales. Without an explicit declaration a metric resolving to `left_leg_vas` in one
# frame and `pain_Left_Leg` in the other would silently differ by a factor of ten, and the
# side-effect ladder in section 2.3 — calibrated so one mild side effect cancels 1.0 NRS point —
# would be ten times too weak against a 0-100 objective. Everything is therefore rescaled to a
# common 0-10 reference before J_pain is formed.
TARGET_SCALE = 10.0
NATIVE_SCALE = {
    "nrs": 10.0, "pain_Overall": 10.0,
    "left_leg_vas": 100.0, "pain_Left_Leg": 10.0,
    "left_foot_vas": 100.0, "pain_Left_Foot": 10.0,
    "back_vas": 100.0, "pain_Back": 10.0,
    "right_leg_vas": 100.0, "pain_Right_Leg": 10.0,
    "right_foot_vas": 100.0, "pain_Right_Foot": 10.0,
    "vas": 100.0, "relief": 100.0, "mpq_sum": 45.0,
}


def scale_factor(col: str) -> float:
    """Multiplier putting ``col`` on the common 0-10 reference. Unknown columns are assumed to be
    already on that scale, which is the safe default for a hand-built frame."""
    return TARGET_SCALE / NATIVE_SCALE.get(col, TARGET_SCALE)


@dataclass(frozen=True)
class PainMetric:
    """A named outcome for the optimizer. ``items`` maps canonical item -> sign, where +1 means
    'higher is worse'. ``standardize`` z-scores each item before averaging, which is required
    whenever items are on different scales and must be OFF for a single-item metric so the units
    stay interpretable as NRS points."""
    name: str
    items: Mapping[str, float]
    description: str = ""
    standardize: bool = True


PAIN_METRICS: dict[str, PainMetric] = {
    "left_leg": PainMetric(
        "left_leg", {"left_leg": +1.0}, standardize=False,
        description="DEFAULT. PI-designated primary site. Single item, so J_pain is in NRS points."),
    "back": PainMetric(
        "back", {"back": +1.0}, standardize=False,
        description="Second target, intended for a PARALLEL optimizer rather than a blend: the "
                    "left-leg and back scores correlate only 0.67, so ~55% of their variance is "
                    "site-specific and averaging them discards the distinction."),
    "overall": PainMetric(
        "overall", {"overall": +1.0}, standardize=False,
        description="NOT recommended as the objective. Retained for comparison and for "
                    "backwards compatibility with the chronic warm start."),
    "legs": PainMetric(
        "legs", {"left_leg": +1.0, "left_foot": +1.0}, standardize=False,
        description="Left lower limb, leg and foot averaged. Both are NRS/10 so no z-scoring."),
    "legacy_composite": PainMetric(
        "legacy_composite", {"overall": +1.0, "vas": +1.0, "mpq_sum": +1.0, "relief": -1.0},
        description="The original chronic composite. Mixed scales, so z-scored; J_pain is then "
                    "in pooled SD units, NOT NRS points."),
}

# Backwards-compatible alias for the original hard-coded composite.
COMPOSITE_ITEMS = {"nrs": +1.0, "vas": +1.0, "mpq_sum": +1.0, "relief": -1.0}

# Items deliberately excluded, with the reason, so the choice is auditable rather than tacit.
EXCLUDED_ITEMS = {
    "head": "PI direction: not a target site. Also unusable — only 19 scored acute steps across "
            "7 visits, versus 126 for the left leg.",
    "tingly": "28% complete; a McGill pain-quality descriptor, not an adverse-event report",
    "electrocuting": "a McGill pain-quality descriptor, not an adverse-event report",
    "mpq_sen": "subscale of mpq_sum; would double-count",
    "mpq_aff": "subscale of mpq_sum; would double-count",
}

# left_leg_vas and back_vas were previously excluded here for 74% completeness. That exclusion is
# WITHDRAWN by PI direction: the left leg is the designated primary site and the back is a
# parallel target. The missingness is real and is now handled as a weighting problem rather than
# by dropping the item — epochs scored on fewer reports get a larger observation variance through
# `observation_variance`, which is the same mechanism that handles short exposures. Any analysis
# using these items must report how many epochs carry them.
PARTIAL_COMPLETENESS = {
    "left_leg": "74% complete in the chronic frame; 126 of 442 acute steps scored",
    "back": "74% complete in the chronic frame; 135 of 442 acute steps scored",
}


def resolve_items(frame, metric) -> dict:
    """Map a PainMetric's canonical items onto the actual columns of ``frame``.

    Raises KeyError naming the metric and the missing item, rather than silently averaging over
    whichever items happen to be present, because a silently-narrowed objective is a wrong
    objective that still runs.
    """
    metric = PAIN_METRICS[metric] if isinstance(metric, str) else metric
    out = {}
    for item, sign in metric.items.items():
        candidates = ITEM_COLUMNS.get(item, (item,))
        found = next((c for c in candidates if c in frame.columns), None)
        if found is None:
            raise KeyError(
                f"pain metric {metric.name!r} needs item {item!r}, tried columns {candidates}, "
                f"none present in frame with columns {sorted(frame.columns)[:12]}...")
        out[found] = sign
    return out


def resolve_primary(frame, name) -> str:
    """Resolve a canonical primary-item name to the column present in ``frame``.

    Requires BOTH the item column and its ``<col>_sd`` companion, because ``build_objective``
    needs the within-epoch SD to weight the observation. Falls back to treating ``name`` as a
    literal column so existing callers passing e.g. ``"nrs"`` keep working. Raises rather than
    silently substituting a different pain site.
    """
    for c in tuple(ITEM_COLUMNS.get(name, ())) + (name,):
        if c in frame.columns and f"{c}_sd" in frame.columns:
            return c
    tried = tuple(ITEM_COLUMNS.get(name, ())) + (name,)
    raise KeyError(
        f"primary item {name!r}: tried columns {tried}, none present with a matching '_sd' "
        f"companion. Frame has: {sorted(frame.columns)[:15]}")


DEFAULTS = dict(
    primary_item="left_leg",
    metric="left_leg",
    washin_h=60.0 / 3600.0,   # 60 s: PI reports a rapid responder; see OBJECTIVE_SPEC amendments
    c_dur=0.25,        # variance inflation scale for short exposures
    c_age=0.25,        # variance inflation scale for observation age
    dur_ref_h=168.0,   # one week: exposures shorter than this have not reached steady state
    w_energy=0.0,      # energy penalty OFF by default (section 2.4)
    min_var=1e-3,      # numerical floor on observation variance
)


def side_effect_penalty(severity) -> float:
    """Map a reported severity label (or NaN / None for unreported) to its NRS-point penalty."""
    if severity is None or (isinstance(severity, float) and np.isnan(severity)):
        return 0.0
    key = str(severity).strip().lower()
    if key not in SE_LADDER:
        raise ValueError(
            f"unknown side-effect severity {severity!r}; expected one of {sorted(SE_LADDER)}"
        )
    return SE_LADDER[key]


#: Reference point for the energy normaliser: the most expensive cell of the declared SEARCH
#: GRID (OBJECTIVE_SPEC section 1), not the most expensive observed epoch. Fixing it here is
#: what makes w_energy mean the same thing across runs — normalising by the max of whatever
#: epoch table happens to be passed in would rescale the weight every time the data changed.
#: Pulse width is 60 us because OBJECTIVE_SPEC section 1 PINS it at 60 us for the prospective
#: phase. Using an historical maximum (140-180 us) here would inflate the divisor and leave
#: w_energy uninterpretable at the grid maximum. TEED at this cell is 247500.
ENERGY_REF = {"freq_hz": 165.0, "amp_mA": 5.0, "pw_us": 60.0}


def energy_reference(ref: dict | None = None) -> float:
    """TEED at the grid's most expensive cell, in raw (unnormalised) units."""
    r = ref or ENERGY_REF
    return float(r["amp_mA"]) ** 2 * float(r["pw_us"]) * float(r["freq_hz"])


def energy_penalty(freq_hz, amp_ma, pulse_width_us, *, ref=None) -> np.ndarray:
    """Total electrical energy delivered, up to the impedance constant, normalised to [0, 1].

    TEED ~ amplitude^2 * pulse_width * frequency, divided by its value at the most expensive
    cell of the declared search grid (:data:`ENERGY_REF`). The divisor is a fixed constant, so
    ``w_energy`` is interpretable in NRS points at that reference cell and does not move when
    the epoch table changes. Values above 1.0 are possible and left unclipped: they mean the
    setting is outside the declared grid, which is worth seeing rather than hiding.
    """
    raw = (np.asarray(amp_ma, float) ** 2 * np.asarray(pulse_width_us, float)
           * np.asarray(freq_hz, float))
    return raw / energy_reference(ref)


def composite_z(pro: pd.DataFrame, items: dict | None = None, *, metric=None) -> pd.Series:
    """Per-report pain score for a chosen metric (section 2.2).

    Pass ``metric`` as a registered name (e.g. ``"left_leg"``, ``"back"``) or a PainMetric.
    A metric with ``standardize=False`` returns the item on its native NRS scale, sign-corrected,
    so downstream J_pain is in NRS points; with ``standardize=True`` each item is z-scored over
    the whole usable pool before averaging, which is required for mixed scales but means J_pain
    is then in pooled SD units.

    ``items`` remains supported as a raw column->sign mapping for backwards compatibility.
    Reports missing an item are averaged over the items present; for a single-item metric that
    simply propagates the missingness, which is the honest behaviour — see PARTIAL_COMPLETENESS.
    """
    if metric is not None:
        m = PAIN_METRICS[metric] if isinstance(metric, str) else metric
        items, standardize = resolve_items(pro, m), m.standardize
    else:
        items, standardize = (items or COMPOSITE_ITEMS), True
    parts = []
    for col, sign in items.items():
        if col not in pro.columns:
            raise KeyError(f"composite item {col!r} missing from PRO frame")
        v = pd.to_numeric(pro[col], errors="coerce")
        if not standardize:
            # rescale to the common 0-10 reference so units are comparable across source frames
            parts.append(sign * v * scale_factor(col))
            continue
        sd = v.std(ddof=1)
        if not np.isfinite(sd) or sd == 0:
            raise ValueError(f"composite item {col!r} has zero or undefined SD; cannot z-score")
        parts.append(sign * (v - v.mean()) / sd)
    return pd.concat(parts, axis=1).mean(axis=1, skipna=True)


def pooled_within_epoch_var(epoch_stats: pd.DataFrame, sd_col: str, n_col: str,
                            min_n: int = 3) -> float:
    """Pooled within-epoch variance from epochs with enough reports to estimate one.

    Used to impute s^2 for single-report epochs (section 3), which otherwise have no
    within-cell variance estimate at all. Refusing to impute would mean discarding them,
    which the spec forbids.
    """
    ok = epoch_stats[(epoch_stats[n_col] >= min_n) & epoch_stats[sd_col].notna()]
    if ok.empty:
        raise ValueError(f"no epochs with n >= {min_n} and a defined SD; cannot pool")
    dof = (ok[n_col] - 1).to_numpy(float)
    return float(np.sum(dof * ok[sd_col].to_numpy(float) ** 2) / np.sum(dof))


def observation_variance(n, sd, dur_h, age_days, *, pooled_var, cfg=None) -> np.ndarray:
    """Per-observation variance for the warm start (section 3).

        sigma^2 = s^2/n + c_dur * max(0, 1 - dur/dur_ref)^2 + c_age * (age/365)^2

    This is the whole mechanism by which "use all the data" is made safe: a 155-report,
    85-day epoch and a 1-report, 26-hour epoch both enter the fit, weighted by how much
    they can actually support.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    n = np.asarray(n, float)
    sd = np.asarray(sd, float)
    s2 = np.where(np.isfinite(sd) & (n >= 2), sd ** 2, pooled_var)
    sem2 = s2 / np.maximum(n, 1.0)
    short = np.maximum(0.0, 1.0 - np.asarray(dur_h, float) / cfg["dur_ref_h"]) ** 2
    aged = (np.asarray(age_days, float) / 365.0) ** 2
    return np.maximum(sem2 + cfg["c_dur"] * short + cfg["c_age"] * aged, cfg["min_var"])


def build_objective(epoch_stats: pd.DataFrame, *, incumbent_epoch, cfg=None,
                    reference_time=None) -> pd.DataFrame:
    """Assemble the epoch-level design table the surrogate consumes.

    Parameters
    ----------
    epoch_stats
        One row per exposure epoch. Required columns: ``epoch``, ``freq_hz``,
        ``amp_mA_Left``, ``pw_us_Left``, ``n``, ``t0``, ``dur_h``, the primary pain item
        (default ``nrs``) and its SD as ``<item>_sd``. Optional: ``se_severity``,
        ``composite``.
    incumbent_epoch
        Epoch id of the current chronic setting. J_pain is referenced to its mean, so
        J = 0 at the incumbent by construction and negative means better than status quo.
    reference_time
        Timestamp against which observation age is measured; defaults to the latest ``t0``.

    Returns
    -------
    DataFrame with ``J``, ``J_pain``, ``J_SE``, ``J_energy``, ``obs_var``, ``se_observed``.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    item = resolve_primary(epoch_stats, cfg["primary_item"])
    sd_col = f"{item}_sd"
    need = {"epoch", "freq_hz", "amp_mA_Left", "pw_us_Left", "n", "t0", "dur_h", item, sd_col}
    missing = need - set(epoch_stats.columns)
    if missing:
        raise KeyError(f"epoch_stats missing required columns: {sorted(missing)}")

    d = epoch_stats.copy()
    if incumbent_epoch not in set(d["epoch"]):
        raise ValueError(f"incumbent epoch {incumbent_epoch!r} not present in epoch_stats")
    # Put the primary item on the common 0-10 reference BEFORE anything is differenced or
    # weighted, so J_pain is in NRS points whichever frame supplied it and the side-effect ladder
    # stays correctly calibrated against it. The SD is rescaled by the same factor.
    sf = scale_factor(item)
    if sf != 1.0:
        d[item] = d[item].astype(float) * sf
        d[sd_col] = d[sd_col].astype(float) * sf
    # The rescale is IN PLACE, so on the returned frame a column named e.g. `left_leg_vas` holds
    # 0-10 values, not the 0-100 values its name implies. Record what happened so the output is
    # self-describing and a later reader cannot rescale a second time.
    d["primary_item"] = item
    d["primary_scale_factor"] = sf
    ref = float(d.loc[d["epoch"] == incumbent_epoch, item].iloc[0])

    d["J_pain"] = d[item].astype(float) - ref

    if "se_severity" in d.columns:
        d["se_observed"] = d["se_severity"].notna()
        d["J_SE"] = d["se_severity"].map(side_effect_penalty).astype(float)
    else:
        # Phase 1: no structured severity field exists. Zero penalty, flagged as unobserved
        # so downstream code cannot mistake absence of a report for absence of a side effect.
        d["se_observed"] = False
        d["J_SE"] = 0.0

    d["J_energy"] = energy_penalty(d["freq_hz"], d["amp_mA_Left"], d["pw_us_Left"])
    d["J"] = d["J_pain"] + d["J_SE"] + cfg["w_energy"] * d["J_energy"]
    # Hard infeasibility, not a large finite penalty — see SE_LADDER. A cell flagged
    # infeasible may never be selected, however large its apparent pain benefit.
    d["feasible"] = np.isfinite(d["J"])

    t0 = pd.to_datetime(d["t0"], utc=True)
    ref_t = pd.to_datetime(reference_time, utc=True) if reference_time is not None else t0.max()
    d["age_days"] = (ref_t - t0).dt.total_seconds() / 86400.0

    pooled = pooled_within_epoch_var(d, sd_col, "n")
    d["pooled_within_var"] = pooled
    d["obs_var"] = observation_variance(d["n"], d[sd_col], d["dur_h"], d["age_days"],
                                        pooled_var=pooled, cfg=cfg)
    return d
