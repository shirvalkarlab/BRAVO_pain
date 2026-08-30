"""Build the StimOptimizer epoch-level design matrix from the running platform's own data.

WHY THIS READS THE STORED JSON RATHER THAN THE THERAPY TABLES
-------------------------------------------------------------
BRAVO normalizes stimulation settings into ``Therapy`` -> ``ElectricalTherapy`` ->
``ElectricalStimulation``. Those rows are dated and carry amplitude, pulse width, frequency and a
bare ``contact`` index list — but **they do not carry the hemisphere**. Recovering it means mapping
contact indices through the device's lead ``Target``/``CustomName`` definitions, and at the same
timestamp there are several rows differing by GROUP rather than by side. Getting that mapping subtly
wrong would silently swap the two hemispheres, which is a wrong-science failure, not a crash.

So this adapter reads the participant's stored session-report JSON through
``DataCurator.loadCacheFile`` and reuses the SAME dual-schema active-group parser that was validated
against the RCS08 file census, where the hemisphere is stated explicitly by the device
(``LeftHemisphere``/``RightHemisphere`` keys, or ``SensingChannel[].HemisphereLocation``). The
platform already stores every byte it needs; nothing is re-fetched from disk outside BRAVO.

THE TWO SCHEMAS (this is the trap that produced an incomplete record once already)
---------------------------------------------------------------------------------
Amplitude lives in one of two places depending on how a group is configured:

* **Legacy.** ``ProgramSettings.{LeftHemisphere,RightHemisphere}.Programs[]`` with the delivered
  amplitude in ``AmplitudeInMilliAmps`` and the rate at group level in ``ProgramSettings.RateInHertz``.
* **BrainSense.** A sensing-configured group has **no hemisphere keys at all**. The per-hemisphere
  program moves to ``ProgramSettings.SensingChannel[]``, one entry per hemisphere identified by
  ``HemisphereLocation``, with the delivered amplitude in ``SuspendAmplitudeInMilliAmps``.

A parser that reads only the first silently returns an incomplete history. Both are handled here.

TIME BASE
---------
Session-report filenames carry a LOCAL wall-clock stamp while the JSON's ``SessionDate`` field is
UTC — a seven-hour offset for this site that silently reduced a naive join to a handful of rows once.
This adapter uses ``SessionDate`` (already UTC) throughout and never parses the filename, so there is
no timezone arithmetic to get wrong. ``GroupHistory`` snapshots carry their own UTC ``SessionDate``.

VALIDATION (2026-08-30, against the file-based census this replaces)
-------------------------------------------------------------------
On the 1,239 shared (timestamp, hemisphere) keys — all of them ``GroupHistory`` rows, which use the
same UTC field in both reconstructions — amplitude, pulse width, rate, cathode label and schema tag
are **identical at 100%**. The ``session`` rows do not share keys because the census keyed them off
the FILENAME stamp while this adapter uses ``SessionDate``; measured on twelve August files the two
differ by a median of **1.4 minutes** (range 0.8 to 65.1 minutes, the outlier being 2026-08-06).
``SessionDate`` is the device's own timestamp and is preferred. Note the interaction with the
1-minute wash-in default: a shift of that size can move a report across the wash-in boundary, so it
is a real if small difference, not a rounding artefact.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)

# Percept session-report SourceFile types that carry Groups/GroupHistory.
_JSON_SOURCE_TYPES = ("MedtronicJSON", "DefaultType")

# Chronic REDCap item columns the optimizer can target, and the site each belongs to. Keep in step
# with StimOptimizer.routines.objective.ITEM_COLUMNS.
PRO_ITEMS = ("left_leg_vas", "back_vas", "nrs", "vas", "mpq_sum", "relief")

# Parameters whose change opens a new exposure epoch. Anything the patient could feel.
_EPOCH_KEYS = ("freq_hz", "amp_mA_Left", "amp_mA_Right", "pw_us_Left", "pw_us_Right",
               "cathode_Left", "cathode_Right")


# --------------------------------------------------------------------------------------------------
# device JSON -> dated per-hemisphere settings
# --------------------------------------------------------------------------------------------------
def contact_label(estates):
    """Cathode/anode label from an ``ElectrodeState`` list. Verbatim from the validated census."""
    neg, pos = [], []
    for e in (estates or []):
        nm = (e.get("Electrode", "") or "").replace("ElectrodeDef.", "") \
            .replace("SenSight_", "").replace("Sensight_", "")
        st = (e.get("ElectrodeStateResult", "") or "").split(".")[-1]
        if st == "Negative":
            neg.append(nm)
        elif st == "Positive":
            pos.append(nm)
    return ("-".join(sorted(neg)) or "none", "+".join(sorted(pos)) or "case")


def group_settings(g):
    """Amplitude / pulse width / rate / contacts per hemisphere, handling BOTH schemas.

    Legacy hemisphere keys win when present; the sensing channel fills any side they did not cover
    (``setdefault``), so a group carrying both never double-counts.
    """
    ps = g.get("ProgramSettings") or {}
    out = {}
    for hemi, tag in (("LeftHemisphere", "Left"), ("RightHemisphere", "Right")):
        h = ps.get(hemi)
        if isinstance(h, dict) and (h.get("Programs") or []):
            pr = h["Programs"][0]
            cath, _ = contact_label(pr.get("ElectrodeState"))
            out[tag] = dict(amp=pr.get("AmplitudeInMilliAmps"),
                            pw=pr.get("PulseWidthInMicroSecond"),
                            rate=ps.get("RateInHertz"),
                            upper=pr.get("UpperLimitInMilliAmps"),
                            cathode=cath, schema="hemisphere")
    for ch in (ps.get("SensingChannel") or []):
        tag = ((ch.get("HemisphereLocation") or "").split(".")[-1])
        if tag not in ("Left", "Right"):
            continue
        cath, _ = contact_label(ch.get("ElectrodeState"))
        out.setdefault(tag, dict(amp=ch.get("SuspendAmplitudeInMilliAmps"),
                                 pw=ch.get("PulseWidthInMicroSecond"),
                                 rate=ch.get("RateInHertz") or ps.get("RateInHertz"),
                                 upper=ch.get("UpperLimitInMilliAmps"),
                                 cathode=cath, schema="sensing"))
    return out


def settings_stream(participant, *, source_types=_JSON_SOURCE_TYPES) -> pd.DataFrame:
    """Every dated ACTIVE-group setting for a participant, one row per (timestamp, hemisphere).

    Reads both the end-of-session state (``Groups.Final``) and the dated between-session snapshots
    (``GroupHistory``). The snapshots matter: a session-only reconstruction loses the resolution that
    makes short exposures visible at all.
    """
    from Server import models
    from modules import DataCurator

    sfs = list(models.SourceFile.objects.filter(owner=participant))
    recs, n_read, n_failed = [], 0, 0
    for sf in sfs:
        if source_types and getattr(sf, "type", None) not in source_types:
            continue
        try:
            d = json.loads(DataCurator.loadCacheFile(sf))
            n_read += 1
        except Exception as e:                      # encrypted-cache miss, non-JSON, pointer moved
            n_failed += 1
            _log.debug("StimOptimizer: could not read SourceFile %s (%s)", getattr(sf, "uid", "?"), e)
            continue
        t_session = pd.to_datetime(d.get("SessionDate"), errors="coerce", utc=True)
        for g in ((d.get("Groups") or {}).get("Final") or []):
            if not g.get("ActiveGroup"):
                continue
            for tag, s in group_settings(g).items():
                recs.append(dict(t=t_session, src="session", hemi=tag, **s))
        for snap in (d.get("GroupHistory") or []):
            ts = pd.to_datetime(snap.get("SessionDate"), errors="coerce", utc=True)
            for g in (snap.get("Groups") or []):
                if not g.get("ActiveGroup"):
                    continue
                for tag, s in group_settings(g).items():
                    recs.append(dict(t=ts, src="history", hemi=tag, **s))
    if n_failed:
        _log.info("StimOptimizer: read %d source files, %d unreadable", n_read, n_failed)
    if not recs:
        return pd.DataFrame(columns=["t", "src", "hemi", "amp", "pw", "rate", "upper",
                                     "cathode", "schema"])
    out = pd.DataFrame(recs).dropna(subset=["t", "amp", "rate"])
    return out.sort_values("t").reset_index(drop=True)


def exposure_epochs(stream: pd.DataFrame) -> pd.DataFrame:
    """Collapse the settings stream into exposure epochs, opening a new one on ANY change.

    Returns one row per epoch with ``t_start``, ``t_end``, ``dur_h`` and the wide per-hemisphere
    settings. The final epoch is left open-ended at the last observation, so its ``dur_h`` is a
    lower bound rather than a measured duration — callers that weight by exposure must treat it so.
    """
    if stream.empty:
        return pd.DataFrame()
    wide = stream.pivot_table(index="t", columns="hemi",
                             values=["amp", "pw", "rate", "cathode"],
                             aggfunc="first")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.sort_index()
    # One shared frequency: the device runs both sides at the same rate. Prefer the left, fall back
    # to the right so a unilateral record still yields a frequency.
    freq = None
    for c in ("rate_Left", "rate_Right"):
        if c in wide.columns:
            freq = wide[c] if freq is None else freq.fillna(wide[c])
    wide["freq_hz"] = freq
    ren = {"amp_Left": "amp_mA_Left", "amp_Right": "amp_mA_Right",
           "pw_Left": "pw_us_Left", "pw_Right": "pw_us_Right",
           "cathode_Left": "cathode_Left", "cathode_Right": "cathode_Right"}
    wide = wide.rename(columns=ren)
    keys = [k for k in _EPOCH_KEYS if k in wide.columns]
    if not keys:
        return pd.DataFrame()
    sig = wide[keys].astype(object).where(pd.notna(wide[keys]), "NA").astype(str).agg("|".join, axis=1)
    wide["epoch"] = (sig != sig.shift()).cumsum().astype(float)
    ep = (wide.reset_index().groupby("epoch", as_index=False)
          .agg(t_start=("t", "min"), **{k: (k, "first") for k in keys}))
    ep["t_end"] = ep["t_start"].shift(-1)
    ep.loc[ep.index[-1], "t_end"] = wide.index.max()
    ep["dur_h"] = (ep["t_end"] - ep["t_start"]).dt.total_seconds() / 3600.0
    ep["open_ended"] = False
    ep.loc[ep.index[-1], "open_ended"] = True
    return ep


# --------------------------------------------------------------------------------------------------
# pain reports -> epoch-level design matrix
# --------------------------------------------------------------------------------------------------
def _stim_state(row) -> str:
    """Classify the therapeutic state. A hemisphere at 0 mA is a DIFFERENT state, not a low dose —
    mixing the two inflates any apparent amplitude gradient (documented in OBJECTIVE_SPEC)."""
    l = row.get("amp_mA_Left")
    r = row.get("amp_mA_Right")
    l0 = (l == 0) or pd.isna(l)
    r0 = (r == 0) or pd.isna(r)
    if l0 and r0:
        return "both_off"
    if l0:
        return "left_off_right_on"
    if r0:
        return "right_off_left_on"
    return "bilateral_active"


def attach_pros(epochs: pd.DataFrame, pro_df: pd.DataFrame, pro_times_utc,
                *, washin_min=1.0, items=PRO_ITEMS) -> pd.DataFrame:
    """Aggregate pain reports onto epochs, excluding reports inside the wash-in window.

    ``washin_min`` is a PROTOCOL parameter, not a modelling one: RCS08 is a rapid responder with a
    demonstrated response under a minute, so the default is 1 minute rather than the 24 h that an
    earlier pass assumed. Each item gets a mean, an SD and a count, because the optimizer weights an
    epoch by its own within-epoch dispersion and replicate count.
    """
    if epochs.empty or pro_df is None or len(pro_df) == 0:
        return pd.DataFrame()
    t = pd.to_datetime(pd.Series(pro_times_utc), utc=True, errors="coerce")
    keep = t.notna().to_numpy()
    p = pro_df.loc[keep].copy()
    p["_t"] = t[keep].to_numpy()
    ep = epochs.sort_values("t_start").reset_index(drop=True)
    idx = np.searchsorted(ep["t_start"].to_numpy(), p["_t"].to_numpy(), side="right") - 1
    p["epoch"] = np.where(idx >= 0, ep["epoch"].to_numpy()[np.clip(idx, 0, None)], np.nan)
    p = p.merge(ep[["epoch", "t_start", "t_end"]], on="epoch", how="left")
    p["h_since_change"] = (p["_t"] - p["t_start"]).dt.total_seconds() / 3600.0
    # The FINAL epoch is open-ended: its `t_end` is merely the last settings observation, not the
    # moment the setting stopped being in force. Testing `_t < t_end` therefore silently DROPS every
    # pain report collected after the last device export — which is the same silent-truncation
    # failure that made the Biomarkers timeline look frozen. A report after the last settings
    # observation belongs to the setting still in force, so the open epoch extends to +inf.
    # Its `dur_h` remains a lower bound; `open_ended` marks it for anything weighting by exposure.
    if "open_ended" in ep.columns:
        p = p.merge(ep[["epoch", "open_ended"]], on="epoch", how="left")
        p["open_ended"] = p["open_ended"].fillna(False).astype(bool)
    else:
        p["open_ended"] = False
    p["in_epoch"] = (p["_t"] < p["t_end"]) | p["open_ended"]
    p["usable"] = p["in_epoch"] & (p["h_since_change"] >= float(washin_min) / 60.0)

    have = [c for c in items if c in p.columns]
    if not have:
        raise KeyError(f"pain-report frame carries none of {list(items)}; "
                       f"has {sorted(p.columns)[:15]}")
    u = p.loc[p["usable"]]
    agg = {}
    for c in have:
        agg[c] = (c, "mean")
        agg[f"{c}_sd"] = (c, "std")
        agg[f"{c}_n"] = (c, "count")
    cell = u.groupby("epoch", as_index=False).agg(n=("_t", "size"), **agg)
    out = ep.merge(cell, on="epoch", how="inner")
    out["t0"] = out["t_start"]
    out["state"] = out.apply(_stim_state, axis=1)
    return out


def build_design_matrix(participant, request_data=None, *, washin_min=1.0,
                        items=PRO_ITEMS) -> pd.DataFrame:
    """End-to-end: platform data -> the epoch matrix ``StimOptimizer.pipeline.run`` consumes.

    Reuses Biomarkers' own pain-report loader and UTC normalization so there is ONE definition of a
    rating timestamp across the two modules.
    """
    from modules.Biomarkers import bravo_service as _bs

    stream = settings_stream(participant)
    if stream.empty:
        return pd.DataFrame()
    ep = exposure_epochs(stream)
    if ep.empty:
        return pd.DataFrame()
    pro_df = _bs._load_pros(request_data or {}, participant)
    times = _bs._pro_times_utc_series(pro_df)
    return attach_pros(ep, pro_df, times, washin_min=washin_min, items=items)
