"""Phase 0: one joined epoch-level table that every downstream estimator reads.

This is plumbing, and the module plan calls it the highest-value item precisely because it is
plumbing: before it existed each estimator built its own near-miss of the same join, so two panels
could disagree about what the brain was doing at a given moment and neither was obviously wrong.

The table is keyed on (session, channel, setting epoch) and carries, for every scanned band, BOTH
power scales, the delivered stimulation settings per hemisphere, the stimulation era, and the
matched pain report.

THE ONE SUBTLETY WORTH READING BEFORE USING THIS. The stored spectral matrix holds LOG power per
frequency bin. Band power on the linear scale is the ARITHMETIC mean of the linear bin powers, and
the arithmetic mean of linear values is not the exponentiated mean of their logarithms — that is the
GEOMETRIC mean, which is systematically smaller and differently weighted whenever the bins are
unequal. This is not a pedantic distinction here: rule D11 records that the device computes LFP
Power as a linear sum of squared magnitude rather than a log quantity, so the linear scale is the
device-relevant one, while the biomarker pipeline validated its bands on the log scale. Both are
therefore computed and carried side by side under names that say which is which, so a downstream
estimator can never silently take the wrong one, and so the question of whether the scale changes
the winner can actually be answered rather than assumed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: The scanned band centres and width used throughout this project.
DEFAULT_BAND_CENTERS_HZ = tuple(float(x) for x in np.arange(10.5, 28.0, 1.0))
DEFAULT_BAND_WIDTH_HZ = 5.0

#: Stimulation era boundaries in mA, shared with the Biomarkers stability test so the two modules
#: cut the amplitude axis in the same place.
ERA_OFF_MAX_MA = 0.1
ERA_LOW_MAX_MA = 1.5


#: The settings columns have been spelled two ways in this codebase: ``amp_Left`` in the raw pivot
#: and ``amp_mA_Left`` in the exposure-epoch frame that callers actually receive. Accepting only one
#: of them is how the Phase 0 table silently came back with no amplitude at all — the join succeeded,
#: every downstream edge reported "no estimable band", and nothing raised. The canonical spelling
#: emitted by this module is the one with units, matching StimOptimizer.
_AMP_NAMES = ("amp_mA_{h}", "amp_{h}")
_PW_NAMES = ("pw_us_{h}", "pw_{h}")


def resolve_setting_column(columns, kind, hemisphere):
    """First matching spelling of a settings column, or None. ``kind`` is 'amp' or 'pw'."""
    names = _AMP_NAMES if kind == "amp" else _PW_NAMES
    for pat in names:
        c = pat.format(h=hemisphere)
        if c in columns:
            return c
    return None


def canonical_amp_col(hemisphere):
    return f"amp_mA_{hemisphere}"


def _era(amp):
    if amp is None or not np.isfinite(amp):
        return None
    if amp < ERA_OFF_MAX_MA:
        return "OFF"
    return "LOW" if amp <= ERA_LOW_MAX_MA else "HIGH"


def band_powers(log_psd, freqs, centers=DEFAULT_BAND_CENTERS_HZ, width=DEFAULT_BAND_WIDTH_HZ):
    """Per-band power on both scales from one row's log spectrum.

    Returns (linear, log_of_linear, mean_of_log), each a dict keyed by band centre.

    ``linear`` is the arithmetic mean of the linear bin powers and is the device-comparable
    quantity (D11). ``log_of_linear`` is its decibel expression, which is a monotone relabelling of
    the same ordering. ``mean_of_log`` is the quantity the biomarker pipeline used; it is the
    geometric mean in disguise and can rank bands differently, which is why it is returned rather
    than quietly replaced.
    """
    lp = np.asarray(log_psd, dtype=float)
    f = np.asarray(freqs, dtype=float)
    if lp.shape[0] != f.shape[0]:
        raise ValueError(f"log_psd has {lp.shape[0]} bins but freqs has {f.shape[0]}")
    lin_bins = np.power(10.0, lp / 10.0)
    out_lin, out_log, out_mol = {}, {}, {}
    half = float(width) / 2.0
    for c in centers:
        m = (f >= c - half) & (f < c + half)
        if not m.any():
            out_lin[c] = out_log[c] = out_mol[c] = np.nan
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            lin = float(np.nanmean(lin_bins[m]))
            out_lin[c] = lin
            out_log[c] = 10.0 * np.log10(lin) if lin > 0 else np.nan
            out_mol[c] = float(np.nanmean(lp[m]))
    return out_lin, out_log, out_mol


def _assign_epoch(t_epoch_s, epochs):
    """Setting-epoch index for each PSD timestamp, or -1 when it falls in no epoch.

    Half-open intervals on purpose: a sample landing exactly on a settings change belongs to the NEW
    epoch, because the change had already been programmed when it was recorded.
    """
    t = np.asarray(t_epoch_s, dtype=float)
    out = np.full(t.shape[0], -1, dtype=int)
    if epochs is None or len(epochs) == 0:
        return out
    # Cast explicitly to nanosecond resolution BEFORE taking the integer view. Under pandas 3 a
    # datetime column may carry microsecond resolution, and `.astype("int64")` returns the raw
    # integer in whatever unit the dtype happens to have — so dividing by 1e9 silently produced
    # timestamps a thousand times too small, every sample fell outside every epoch, and the joined
    # table came back empty with no error anywhere. The same resolution-independent idiom is used in
    # Biomarkers/routines/analytics.py for exactly this reason.
    starts = (pd.to_datetime(epochs["t_start"], utc=True).to_numpy()
              .astype("datetime64[ns]").astype("int64") / 1e9)
    ends = (pd.to_datetime(epochs["t_end"], utc=True).to_numpy()
            .astype("datetime64[ns]").astype("int64") / 1e9)
    for i, (a, b) in enumerate(zip(starts, ends)):
        m = (t >= a) & (t < b) if np.isfinite(b) else (t >= a)
        out[m] = i
    return out


def joined_table(psd_frame, epochs, *, centers=DEFAULT_BAND_CENTERS_HZ,
                 width=DEFAULT_BAND_WIDTH_HZ, pro_frame=None):
    """The Phase 0 table: one row per (PSD sample, band).

    Long rather than wide in the band dimension. Wide would mean 18 columns per power scale and a
    reshape inside every estimator; long lets an estimator filter to its band and keeps the three
    power scales as three columns rather than fifty-four.

    ``pro_frame``, when supplied, must carry ``epoch`` and a report identifier; the matched pain
    report is joined on the setting epoch rather than on time, because the epoch is the unit the
    exposure model already assigns reports to and re-deriving it here would let the two drift.
    """
    if psd_frame is None or len(psd_frame) == 0:
        return pd.DataFrame()
    ep_idx = _assign_epoch(psd_frame["t"].to_numpy(), epochs)

    rows = []
    have_epochs = epochs is not None and len(epochs) > 0
    for i, (_, r) in enumerate(psd_frame.iterrows()):
        lin, logl, mol = band_powers(r["log_psd"], r["freqs"], centers, width)
        e = int(ep_idx[i])
        ctx = {}
        if have_epochs and e >= 0:
            row = epochs.iloc[e]
            ctx = {c: row.get(c) for c in
                   ("freq_hz", "cathode_Left", "cathode_Right", "t_start", "t_end", "dur_h",
                    "epoch", "open_ended")
                   if c in epochs.columns}
            # Normalise the settings columns to the canonical spelling regardless of which one the
            # incoming frame used, so downstream estimators need to know only one name.
            for h in ("Left", "Right"):
                ac = resolve_setting_column(epochs.columns, "amp", h)
                pc = resolve_setting_column(epochs.columns, "pw", h)
                if ac:
                    ctx[canonical_amp_col(h)] = row.get(ac)
                if pc:
                    ctx[f"pw_us_{h}"] = row.get(pc)
        for c in centers:
            rows.append({
                "t": float(r["t"]), "channel": r["channel"], "source": r.get("source"),
                "setting_epoch": e, "center_hz": float(c), "band_width_hz": float(width),
                "power_linear": lin[c], "power_log_of_linear": logl[c],
                "power_mean_of_log": mol[c],
                **ctx,
            })
    T = pd.DataFrame(rows)
    if T.empty:
        return T
    for h in ("Left", "Right"):
        c = canonical_amp_col(h)
        if c in T.columns:
            T[f"era_{h}"] = [_era(x) for x in pd.to_numeric(T[c], errors="coerce")]
    if pro_frame is not None and len(pro_frame) and "epoch" in pro_frame.columns:
        keep = [c for c in ("epoch", "report_id", "nrs", "vas") if c in pro_frame.columns]
        T = T.merge(pro_frame[keep].rename(columns={"epoch": "setting_epoch"}),
                    on="setting_epoch", how="left")
    return T


def scale_disagreement(T):
    """How often the two power scales would pick a different winning band.

    This answers hypothesis H4 of the module plan directly. It is a diagnostic, not a verdict: a
    high disagreement rate does not say which scale is right, only that the choice is consequential
    and must therefore be made deliberately rather than inherited from whichever pipeline ran first.
    """
    if T is None or T.empty:
        return {"available": False, "reason": "empty table"}
    g = T.dropna(subset=["power_linear", "power_mean_of_log"])
    if g.empty:
        return {"available": False, "reason": "no rows with both scales"}
    win_lin = g.loc[g.groupby(["t", "channel"])["power_linear"].idxmax(), ["t", "channel", "center_hz"]]
    win_mol = g.loc[g.groupby(["t", "channel"])["power_mean_of_log"].idxmax(), ["t", "channel", "center_hz"]]
    m = win_lin.merge(win_mol, on=["t", "channel"], suffixes=("_lin", "_mol"))
    if m.empty:
        return {"available": False, "reason": "no comparable samples"}
    disagree = float((m.center_hz_lin != m.center_hz_mol).mean())
    return {"available": True, "n_samples": int(len(m)),
            "disagreement_rate": disagree,
            "median_abs_shift_hz": float((m.center_hz_lin - m.center_hz_mol).abs().median()),
            "note": ("fraction of (time, channel) samples where the linear and mean-of-log scales "
                     "pick a different peak band. The device uses the linear scale (D11); the "
                     "biomarker pipeline validated on mean-of-log.")}
