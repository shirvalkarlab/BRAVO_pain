"""The deployment summary's area under the curve, read again with the stimulation current taken out.

WHAT THIS IS FOR (the PI, 2026-09-25, answer 6 of the revised plan): "keep the clinic-sheet ratings
off by default in the deployment summary, and build the same number with the current taken out
beside it". The deployment summary on the Closed-Loop page prints one area under the curve for the
chosen band: how well the band's power tells this patient's high-pain moments from the low-pain
ones. On RCS08's left lead the band power and the pain both move with the stimulation current, so
that number can partly be the current speaking. This reads the same band again with the part of its
power that the current explains subtracted, and prints the result beside the plain number.

DESCRIPTIVE ONLY. The plain reading still sets every gate and the verdict; nothing here refuses,
selects or moves anything (the PI, 2026-09-22, decision 233 answer 2).

THE SAME ROWS AND THE SAME MACHINERY AS E2. The spectral samples, their pain scores, the pain report
each belongs to and the high-or-low split are exactly the ones the summary's own curve is drawn from
(the pooled detail `_band_validation_setup` builds, the clinic-sheet ratings included when the
button is on). The second reading is made by the estimator decision 242 built for E2 on the same
page (`analytics.band_pain_auc_from_table(covariate_column=)`), with its refusals, its shared rule
for a band that is almost entirely the current (`stats_utils.NEARLY_THE_COVARIATE_R2`) and its
interval that resamples whole pain reports.

WHICH CURRENT. The milliamps programmed on the band's own side at the moment each spectral sample
was recorded, from the device's own dated settings (`stim_current.current_in_force_at`, the one
place Biomarkers reads the current, decision 234). Per sample, as E2 takes it, not per pain report.

WHICH SHAPE, AND WHY. A straight line (one degree of freedom), because E2's adjusted reading on the
same page is made with a straight line (decision 242) and two adjusted readings a reader will set
side by side must be made the same way; decision 241 keeps the straight line for every published
adjusted number and the spline only for the two offline guards.

WHY TWO FURTHER NUMBERS TRAVEL WITH IT. The plain curve's number reports the larger of the value and
one minus the value, so it never falls below 0.5; the estimator used here fixes the direction in
advance (more power against more pain). So the adjusted reading is also given in the plain number's
own direction, which is the one printed beside it, and a value below 0.5 there means the direction
reversed once the current was out. And because a sample recorded before the first dated setting has
no current, the adjusted reading can rest on fewer samples than the plain one; the same estimator's
plain reading on exactly those samples travels with it, so a reader can tell how much of any change
is the change of samples and how much is the current coming out.
"""
import numpy as np
import pandas as pd

from . import analytics
from . import stim_current

#: What the page prints beside the plain number.
LABEL = "with the stimulation current taken out"

#: The shape the current is allowed to act in, and what that cost. See the module docstring.
SHAPE = "line"
SHAPE_WORDS = "a straight line"
WHY_THIS_SHAPE = ("a straight line, as E2's adjusted reading on this page is made (decision 242), "
                  "so the two adjusted readings a reader sets side by side are made the same way; "
                  "decision 241 keeps the straight line for every published adjusted number")
DESCRIPTIVE_ONLY = ("Descriptive only: the plain reading sets every gate and the verdict; this "
                    "one moves none of them (the PI, 2026-09-22).")
INTERVAL_METHOD = ("the 2.5th and 97.5th percentiles over resamples of whole pain reports; the "
                   "plain curve's own interval is additionally bias-corrected, so the like-for-like "
                   "comparison is with the plain reading on the same samples, made this same way")


def _jsonable(o):
    """Plain Python numbers all the way down, so the endpoint's JSON never meets a numpy scalar;
    a non-finite number becomes None, which the page prints as a dash rather than "NaN"."""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    return o


def _refused(why, **extra):
    out = {"available": False, "label": LABEL, "adjusted_for": stim_current.CURRENT_LABEL,
           "shape": SHAPE, "shape_words": SHAPE_WORDS, "flexibility_spent": 1,
           "why_this_shape": WHY_THIS_SHAPE, "auc": None, "auc_low": None, "auc_high": None,
           "auc_more_power_more_pain": None, "auc_more_power_more_pain_low": None,
           "auc_more_power_more_pain_high": None, "p_two_sided": None,
           "partial_r": None, "partial_r_low": None, "partial_r_high": None,
           "r_power_vs_current": None, "nearly_the_current": False,
           "plain_on_same_samples": None, "n_spectral_samples": 0, "n_pain_reports": 0,
           "why": why, "descriptive_only": DESCRIPTIVE_ONLY}
    out.update(extra)
    return _jsonable(out)


def _orient(value, flip):
    if value is None:
        return None
    return float(1.0 - float(value)) if flip else float(value)


def _oriented_interval(lo, hi, flip):
    if lo is None or hi is None:
        return None, None
    return ((float(1.0 - float(hi)), float(1.0 - float(lo))) if flip
            else (float(lo), float(hi)))


def epoch_seconds(time_strings):
    """Epoch seconds for the detail's per-sample time strings; NaN where one will not parse.
    A time with no zone is UTC, as on every machine this project runs on (decision 102)."""
    t = pd.to_datetime(pd.Series([str(s) for s in time_strings]), errors="coerce", utc=True)
    out = np.full(len(t), np.nan)
    ok = t.notna().to_numpy()
    if ok.any():
        # by subtraction, not by `astype("int64")`: the integer is in the series' own unit, which
        # is nanoseconds under the container's pandas 2 and microseconds under pandas 3
        out[ok] = ((t[ok] - pd.Timestamp(0, tz="UTC")) / pd.Timedelta(seconds=1)).to_numpy(float)
    return out


def auc_with_current_taken_out(td_detail, channel, center_hz, *, band_width_hz, strategy,
                               low_pct, high_pct, settings_stream, plain_roc, n_boot=300,
                               seed=0, pain_cutoff=None, settings_store_key=None):
    """The adjusted reading for the summary's band, or a refusal that says why in words.

    ``plain_roc`` is the summary's own `analytics.deployment_roc` answer: its direction (`flip`) is
    the one the adjusted reading is given in, and when it could not be formed there is nothing to
    read again. ``settings_stream`` is `stim_current.settings_stream_for(participant)` (None when
    no dated settings are filed). Never raises on the data; every refusal is an answer.
    """
    if not (plain_roc or {}).get("available"):
        return _refused("the plain reading could not be formed on these samples, so there is "
                        "nothing to read again with the current taken out")
    flip = bool(plain_roc.get("flip"))
    side = stim_current.hemisphere_of_channel(channel)
    if side is None:
        return _refused(f"the sensing contact pair {channel!r} does not name a side, so the "
                        "current on its side cannot be looked up")
    feat = analytics._band_feature_from_detail(td_detail, channel, center_hz, band_width_hz)
    if feat is None:
        return _refused("the band was not found in the matched samples")
    bp, labels, groups, times = feat
    n_total = int(np.sum(np.isfinite(bp) & np.isfinite(labels)))
    if settings_stream is None:
        return _refused("there is no current per sample: no dated stimulation settings have been "
                        "filed for this participant, so the current in force cannot be looked up. "
                        "That is an absent measurement, not a finding",
                        hemisphere=side, n_samples_total=n_total)
    current = stim_current.current_in_force_at(epoch_seconds(times), settings_stream,
                                               hemisphere=side)
    has = np.isfinite(current)
    if not has.any():
        return _refused(f"there is no current per sample: every sample predates the first "
                        f"{side} setting on record", hemisphere=side, n_samples_total=n_total)
    # THE PLAIN CURVE'S OWN HIGH-OR-LOW SPLIT, made exactly as `deployment_roc` makes it: on every
    # matched sample of the detail, the samples of other contact pairs included (their pain reports
    # set where the thirds fall). Handing the estimator the continuous scores would let it draw the
    # line again on this band's own rows, which on RCS08 moved it enough to change which reports
    # count as high or low (39 against 39 reports but 0.608 against 0.617 on one reading, 84
    # against 80 reports on the other). So the split is made once, here, and handed over as 0 and
    # 1 with a cut at 0.5, which reproduces it; the same estimator's plain reading on the same
    # samples then equals the printed number exactly. The partial correlation beside it is
    # therefore with that high-or-low label, not with the continuous score.
    y_all = analytics._binarize_labels(np.asarray(labels, dtype=float), strategy=strategy,
                                       low_pct=low_pct, high_pct=high_pct, pain_cutoff=pain_cutoff,
                                       rating_group=np.asarray(groups))
    n_total = int(np.sum(np.isfinite(bp) & np.isfinite(y_all)))
    keep = has & np.isfinite(bp) & np.isfinite(y_all)
    table = pd.DataFrame({
        "channel": channel, "center_hz": float(center_hz),
        "power": np.asarray(bp, dtype=float)[keep], "pain_high": y_all[keep].astype(float),
        "report_id": np.asarray(groups)[keep], "t": np.asarray(times)[keep],
        "current_mA": current[keep]})
    out = analytics.band_pain_auc_from_table(
        table, channel=channel, center_hz=float(center_hz), pain_column="pain_high",
        power_column="power", group_column="report_id", time_column="t", strategy="cutoff",
        pain_cutoff=0.5, n_boot=int(n_boot), seed=int(seed), covariate_column="current_mA",
        covariate_shape=SHAPE)
    adj = dict(out.get("covariate_adjusted") or {})
    counts = {
        "hemisphere": side,
        "n_samples_total": n_total,
        "n_samples_without_current": int(n_total - int(keep.sum())),
        "n_distinct_currents": int(np.unique(np.round(current[keep], 3)).size),
        "settings_store_key": settings_store_key,
        "plain_direction": ("more power goes with less pain" if flip
                            else "more power goes with more pain"),
    }
    p_lo, p_hi = _oriented_interval(out.get("auc_low"), out.get("auc_high"), flip)
    same = ({"auc": _orient(out.get("auc"), flip), "auc_low": p_lo, "auc_high": p_hi,
             "n_spectral_samples": int(out.get("n_spectral_samples") or 0),
             "n_pain_reports": int(out.get("n_pain_reports") or 0)}
            if out.get("auc") is not None else None)
    if not adj.get("available") or adj.get("auc") is None:
        return _refused(adj.get("why") or out.get("why") or "the adjusted reading was not formed",
                        r_power_vs_current=adj.get("r_power_vs_covariate"),
                        nearly_the_current=bool(adj.get("nearly_the_covariate")),
                        plain_on_same_samples=same,
                        n_spectral_samples=int(adj.get("n_spectral_samples") or 0),
                        n_pain_reports=int(adj.get("n_pain_reports") or 0), **counts)
    a_lo, a_hi = _oriented_interval(adj.get("auc_low"), adj.get("auc_high"), flip)
    auc = _orient(adj.get("auc"), flip)
    reversed_ = bool(auc is not None and a_hi is not None and a_hi < 0.5)
    why = (f"The band power with the {side} current in force at each sample taken out as "
           f"{SHAPE_WORDS}, the pain scores and the high-or-low split untouched, given in the "
           f"plain reading's own direction ({counts['plain_direction']}); 0.5 is what coin "
           f"flipping gives, and a value below 0.5 means the direction reversed once the current "
           f"was out.")
    if reversed_:
        why += " Here the whole interval sits below 0.5: with the current out, the direction reversed."
    return _jsonable({
        "available": True, "label": LABEL, "adjusted_for": stim_current.CURRENT_LABEL,
        "shape": SHAPE, "shape_words": SHAPE_WORDS,
        "flexibility_spent": adj.get("flexibility_spent", 1), "why_this_shape": WHY_THIS_SHAPE,
        "auc": auc, "auc_low": a_lo, "auc_high": a_hi,
        "auc_more_power_more_pain": adj.get("auc"),
        "auc_more_power_more_pain_low": adj.get("auc_low"),
        "auc_more_power_more_pain_high": adj.get("auc_high"),
        "p_two_sided": adj.get("p_two_sided"),
        # with the high-or-low label (1 high, 0 low), the middle third left out; see the split
        "partial_r": adj.get("partial_r"), "partial_r_low": adj.get("partial_r_low"),
        "partial_r_high": adj.get("partial_r_high"),
        "partial_r_with": "the high-or-low pain label (1 high, 0 low), the middle third left out",
        "r_power_vs_current": adj.get("r_power_vs_covariate"), "nearly_the_current": False,
        "plain_on_same_samples": same,
        "n_spectral_samples": int(adj.get("n_spectral_samples") or 0),
        "n_pain_reports": int(adj.get("n_pain_reports") or 0),
        "interval_method": INTERVAL_METHOD, "why": why, "descriptive_only": DESCRIPTIVE_ONLY,
        **counts,
    })
