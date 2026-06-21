"""
Adapter layer: maps BRAVO decoded-recording dicts onto the dbs_stage2 biomarker routines,
and aligns REDCap PROs to the stim/LFP timeline.

This is the ONLY new glue in the integration. The biomarker science lives untouched in
`routines/streaming_psd.py`; the REDCap pull is vendored unchanged in
`routines/redcap_client.py`. Everything here is shape/timestamp bookkeeping.

BRAVO recording contract (from modules/MedtronicPercept/BrainSenseStream.py &
ChronicBrainSense.py):
  TimeDomain recording (250 Hz):  {SamplingRate, ChannelNames:[...], Data: (N, n_ch),
                                   Missing, StartTime, Duration, [Descriptor:{Therapy}]}
  PowerDomain recording (~2 Hz):  + carries Stimulation amplitude in its packets
  Chronic recording:              {SamplingRate:-1, Time:(N,), Data:(N,2) [LFP, Amp],
                                   ChannelNames, StartTime, Duration}

Routine input contract (what streaming_psd expects per epoch; identical to dbs_io.Stream):
  {"stream_data": [<per-group (n_ch, n_samples) array>, ...],
   "channel_names": [[name, ...], ...],
   "sample_rate": float}
"""

import datetime

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


# ---------------------------------------------------------------------------
# 1) Recording reshape: BRAVO TimeDomain dict -> Stream-like epoch dict
# ---------------------------------------------------------------------------
def bravo_timedomain_to_streamdata(recording):
    """
    Convert one BRAVO TimeDomain recording dict into the per-epoch dict the streaming
    routine consumes. BRAVO stores `Data` as (N_samples, N_channels); the routine
    (mirroring dbs_io.Stream) wants per-group arrays shaped (N_channels, N_samples).

    Returns a dict:
      {"stream_data": [ (n_ch, n_samples) ],     # single group per recording
       "channel_names": [ [ch0, ch1, ...] ],
       "sample_rate": float,
       "start_time": float or None}
    """
    data = np.asarray(recording["Data"], dtype=float)
    if data.ndim == 1:
        data = data[:, None]
    group = data.T  # (n_ch, n_samples)
    return {
        "stream_data": [group],
        "channel_names": [list(recording["ChannelNames"])],
        "sample_rate": float(recording["SamplingRate"]),
        "start_time": recording.get("StartTime"),
    }


def bravo_timedomain_recordings_to_streams(recordings):
    """Vectorized helper: list of BRAVO TimeDomain recordings -> list of epoch dicts."""
    return [bravo_timedomain_to_streamdata(r) for r in recordings]


# ---------------------------------------------------------------------------
# 2) Timestamp helpers
# ---------------------------------------------------------------------------
def _to_datetime(value):
    """Best-effort convert a BRAVO StartTime/Time value to a pandas Timestamp.

    BRAVO emits StartTime either as an epoch float (FirstPacketDateTime) or an ISO string.
    """
    if value is None:
        return pd.NaT
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Heuristic: a real Percept Unix timestamp is ~1.6e9 (year 2020+). A missing/zero/relative
        # StartTime (e.g. 0, or a few seconds of session offset) is NOT an absolute time — mapping it
        # through utcfromtimestamp yields 1969/1970, which then stretches the timeline back five
        # decades. Treat anything below this floor as unusable rather than fabricating a 1969 date.
        # 1e9 s = 2001-09-09; no Percept device predates that, so it is a safe lower bound.
        if float(value) < 1e9:
            return pd.NaT
        try:
            return pd.Timestamp(datetime.datetime.utcfromtimestamp(float(value)))
        except (OverflowError, OSError, ValueError):
            return pd.NaT
    return pd.to_datetime(value, errors="coerce")


# ---------------------------------------------------------------------------
# 3) PRO alignment to the stim/LFP timeline
# ---------------------------------------------------------------------------
def align_pros(pro_df, *, target, recordings=None, chronic=None,
               metrics=("nrs", "vas", "mpq_sum"),
               timestamp_col="date_time_s1_daily",
               stim_amplitudes=None):
    """
    Align REDCap PRO rows to the decoded timeline.

    Parameters
    ----------
    pro_df : pandas.DataFrame
        Processed PRO table (e.g. from redcap_client.load_processed_pro_csv / pull_redcap).
        Must contain `timestamp_col` and the requested `metrics` columns.
    target : {"session", "chronic"}
        "session": one output row per streaming session (mirrors notebook cell 7 -- PRO
                   metrics aggregated by the session's calendar date: mean & min).
        "chronic": one output row per chronic 10-min sample, with the nearest-date PRO
                   joined and the stim amplitude taken from the chronic packet itself.
    recordings : list[dict], required for target="session"
        BRAVO TimeDomain (or PowerDomain) recordings; their `StartTime` sets the session date.
    chronic : dict, required for target="chronic"
        A BRAVO Chronic recording: {Time:(N,), Data:(N,2) [LFP, Amp], ...}.
    metrics : tuple[str]
        PRO metric columns to carry through.
    timestamp_col : str
        PRO timestamp column (default matches the dbs_stage2 processed CSV).
    stim_amplitudes : list[float] | None
        Optional per-session stim amplitude (mA) for target="session", aligned to
        `recordings`. For target="chronic" the amplitude comes from `chronic["Data"][:,1]`.

    Returns
    -------
    pandas.DataFrame  (the combined aligned timeline)
    """
    df = pro_df.copy()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
    df["_date"] = df[timestamp_col].dt.date

    if target == "session":
        if recordings is None:
            raise ValueError('target="session" requires `recordings`.')
        rows = []
        for i, rec in enumerate(recordings):
            ts = _to_datetime(rec.get("StartTime"))
            sess_date = ts.date() if not pd.isna(ts) else None
            same_day = df[df["_date"] == sess_date] if sess_date is not None else df.iloc[0:0]
            row = {"session_index": i, "session_start": ts, "session_date": sess_date}
            for m in metrics:
                if m in same_day.columns and len(same_day) > 0:
                    row[f"{m}_mean"] = same_day[m].mean()
                    row[f"{m}_min"] = same_day[m].min()
                else:
                    row[f"{m}_mean"] = np.nan
                    row[f"{m}_min"] = np.nan
            if stim_amplitudes is not None and i < len(stim_amplitudes):
                row["stim_amplitude"] = stim_amplitudes[i]
            else:
                row["stim_amplitude"] = _session_stim_amplitude(rec)
            rows.append(row)
        return pd.DataFrame(rows)

    elif target == "chronic":
        if chronic is None:
            raise ValueError('target="chronic" requires `chronic`.')
        time = np.asarray(chronic["Time"], dtype=float)
        cdata = np.asarray(chronic["Data"], dtype=float)
        lfp = cdata[:, 0]
        amp = cdata[:, 1] if cdata.shape[1] > 1 else np.full(len(time), np.nan)
        chronic_ts = [_to_datetime(t) for t in time]

        # Nearest-date PRO join (PROs are daily; chronic samples are ~10 min).
        pro_by_date = {d: g for d, g in df.groupby("_date")}
        out_rows = []
        for k, ts in enumerate(chronic_ts):
            d = ts.date() if not pd.isna(ts) else None
            g = pro_by_date.get(d)
            row = {"time": ts, "lfp": lfp[k], "stim_amplitude": amp[k]}
            for m in metrics:
                row[m] = (g[m].mean() if (g is not None and m in g.columns) else np.nan)
            out_rows.append(row)
        return pd.DataFrame(out_rows)

    else:
        raise ValueError('target must be "session" or "chronic"')


def _session_stim_amplitude(recording):
    """Pull a representative stim amplitude (mA) from a recording's Therapy descriptor,
    if present (BrainSenseStream PowerDomain recordings carry Descriptor.Therapy)."""
    desc = recording.get("Descriptor") or {}
    therapy = desc.get("Therapy") or {}
    for key in ("Amplitude", "amplitude", "LeftHemisphere", "RightHemisphere"):
        val = therapy.get(key)
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict) and isinstance(val.get("Amplitude"), (int, float)):
            return float(val["Amplitude"])
    return np.nan


# ---------------------------------------------------------------------------
# 4) Chronic (10-min trend) glue for the threshold biomarker
# ---------------------------------------------------------------------------
def mad_outlier_mask(x, k=3.0):
    """Boolean KEEP-mask: True for samples within k median-absolute-deviations of the median.
    Excludes artifact spikes where |x - median| > k*MAD (NaN/non-finite are excluded). Returns the
    finite mask when MAD==0 (all equal) or fewer than 3 finite points (MAD undefined/unstable).
    Robust (median/MAD), so a few extreme values don't move the threshold like mean/SD would.
    """
    x = np.asarray(x, dtype=float)
    finite = np.isfinite(x)
    if finite.sum() < 3:
        return finite
    med = np.median(x[finite])
    mad = np.median(np.abs(x[finite] - med))
    if mad <= 0:
        return finite
    return finite & (np.abs(x - med) <= k * mad)


def _concat_chronic(chronic, mad_k=3.0):
    """Accept one Chronic recording dict OR a list of them, returning a single dict with a
    time-sorted, concatenated Time/Data. The threshold detector needs many days of trend
    (train+gap+test, default ~10 days); a single Chronic recording spans only minutes, so
    multiple visits must be concatenated into one long trend before detection.

    `mad_k`: per-recording MAD outlier rejection on the LFP-power column (Data[:,0]) BEFORE
    concatenation. Applied PER RECORDING (each recording is one homogeneous-scale source —
    Chronic ~10-min LFP vs per-session Power-Domain band power differ ~8x), so a global MAD
    wouldn't wrongly flag an entire lower-scale source. Set mad_k=None to disable.
    """
    if isinstance(chronic, dict):
        chronic = [chronic]
    chronic = [c for c in chronic if c is not None]
    if not chronic:
        raise ValueError("chronic must be a recording dict or a non-empty list of them.")
    times_list, datas_list, src_list, freq_list = [], [], [], []
    for c in chronic:
        t = np.asarray(c["Time"], dtype=float)
        d = np.asarray(c["Data"], dtype=float)
        # Sensing-modality tag per recording, repeated per sample so it survives the merge+sort and
        # downstream can diagnose the two-source batch/scale confound. Default "chronic".
        src = str(c.get("Source", "chronic"))
        # Sensing CENTER FREQUENCY (Hz) of THIS recording, repeated per sample (parallel to Source).
        # The programmed band can change between recordings of the same contact, so the frequency is
        # a per-recording property — carrying it per sample lets the decoding path filter to one
        # (channel, frequency) combo without a separate timestamp-to-schedule join. Snapped to the
        # Percept FFT bin (~250/256 Hz); NaN when the recording carries no CenterFrequencyHz.
        fhz = _snap_freq_local(c.get("CenterFrequencyHz"))
        if mad_k and d.ndim == 2 and d.shape[0] == t.shape[0] and t.shape[0] >= 3:
            keep = mad_outlier_mask(d[:, 0], k=mad_k)   # per-recording (homogeneous scale)
            t, d = t[keep], d[keep]
        if t.size:
            times_list.append(t)
            datas_list.append(d)
            src_list.append(np.full(t.shape[0], src, dtype=object))
            freq_list.append(np.full(t.shape[0], fhz, dtype=float))
    if not times_list:
        raise ValueError("no chronic samples survived outlier rejection.")
    times = np.concatenate(times_list)
    datas = np.concatenate(datas_list, axis=0)
    sources = np.concatenate(src_list)
    freqs = np.concatenate(freq_list)
    order = np.argsort(times)
    return {
        "SamplingRate": -1,
        "Time": times[order],
        "Data": datas[order],
        "Source": sources[order],
        "FrequencyHz": freqs[order],
        "ChannelNames": chronic[0].get("ChannelNames"),
    }


# Percept sensing-frequency bin width (FFT bin spacing ~250/256 Hz). Defined locally in adapter to
# avoid a circular import with pipeline (which imports adapter); mirrors pipeline._snap_freq.
_PERCEPT_FREQ_BIN_HZ = 250.0 / 256.0


def _snap_freq_local(hz):
    """Snap a programmed center frequency to the nearest Percept FFT bin; NaN when missing/invalid."""
    try:
        v = float(hz)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(v) or v <= 0:
        return float("nan")
    return round(round(v / _PERCEPT_FREQ_BIN_HZ) * _PERCEPT_FREQ_BIN_HZ, 1)


# Medtronic power-domain packets flag a missing sample with a ~2^32 sentinel (uint32 max).
_POWER_SENTINEL = 4.0e9


def bravo_powerdomain_to_chronic_like(recordings):
    """Convert BrainSense Power-Domain recordings (per-session band power, ~2 Hz) into
    chronic-shaped power dicts so they concatenate with the ~10-min Chronic timeline through the
    SAME `_concat_chronic` + `bravo_chronic_to_lfp_df` path — i.e. one merged power-domain series.

    A power-domain recording has no `Time` array (it carries `StartTime` + `SamplingRate`), and its
    `Data` columns are per-contact band power + stimulation (e.g. ['ZERO_THREE_LEFT Power',
    'ZERO_THREE_RIGHT Power', 'ZERO_THREE_LEFT Stimulation', 'ZERO_THREE_RIGHT Stimulation']).
    Each '<contact> Power' column becomes its own chronic-shaped series, paired with the matching
    '<contact> Stimulation' column when present; missing/sentinel samples are dropped.

    Output dicts match the Chronic shape: {SamplingRate:-1, Time:(M,), Data:(M,2) [power, stim],
    ChannelNames:['<hemi> LFP', '<hemi> Amplitude']}.

    SCALE NOTE: power-domain band power and the chronic ~10-min LFP power are on different scales
    (different sensing band/averaging). By design these are concatenated in RAW device units (no
    normalization), so the merged series mixes scales — interpret the combined threshold with that
    in mind.
    """
    out = []
    for r in recordings or []:
        if not isinstance(r, dict) or "Data" not in r:
            continue
        names = list(r.get("ChannelNames", []) or [])
        data = np.asarray(r["Data"], dtype=float)
        if data.ndim != 2 or data.shape[0] == 0:
            continue
        n = data.shape[0]
        fs = float(r.get("SamplingRate") or 2.0) or 2.0
        # StartTime must be a real absolute Unix time (~1.6e9). A missing/zero StartTime would make
        # `time` start at epoch 0 (1970) and the whole series would plot back in 1969/1970 — skip the
        # recording instead of fabricating a 1969 timeline (1e9 s = 2001; no Percept predates that).
        start = float(r.get("StartTime") or 0.0)
        if start < 1e9:
            continue
        time = start + np.arange(n) / fs
        missing = np.asarray(r.get("Missing", np.zeros_like(data)), dtype=float)
        if missing.shape != data.shape:
            missing = np.zeros_like(data)

        ncols = data.shape[1]
        # Guard against ChannelNames longer than Data columns (malformed packet) -> only index
        # columns that actually exist.
        power_cols = [i for i, nm in enumerate(names) if "POWER" in nm.upper() and i < ncols]
        for pi in power_cols:
            nm_up = names[pi].upper()
            hemi = "LEFT" if "LEFT" in nm_up else ("RIGHT" if "RIGHT" in nm_up else "")
            pw = data[:, pi].copy()
            bad = (missing[:, pi] > 0) | (pw >= _POWER_SENTINEL) | (pw < 0) | ~np.isfinite(pw)
            pw[bad] = np.nan
            # Stimulation column for the same hemisphere, else any stim column, else NaN.
            si = next((i for i, s in enumerate(names)
                       if "STIM" in s.upper() and hemi and hemi in s.upper() and i < ncols), None)
            if si is None:
                si = next((i for i, s in enumerate(names) if "STIM" in s.upper() and i < ncols), None)
            stim = data[:, si] if si is not None else np.full(n, np.nan)
            valid = np.isfinite(pw)
            if not valid.any():
                continue
            # Build a real bipolar-contact label (e.g. "L 0⁻3⁺") from the power column name
            # instead of the uninformative "Left LFP" / "Right LFP". The Medtronic export names
            # the column "<CONTACT> Power" (e.g. "ZERO_THREE_LEFT Power"); strip " Power" and let
            # format_channel decode it. Fall back to the hemisphere when no contact is encoded.
            from .routines.analytics import format_channel
            contact_raw = names[pi]
            for suffix in (" POWER", " Power", " power"):
                if contact_raw.upper().endswith(suffix.upper()):
                    contact_raw = contact_raw[: -len(suffix)]
                    break
            fmt = format_channel(contact_raw, region="")
            short = fmt.get("short") or ""
            # format_channel returns a decoded bipolar label like "L 0⁻3⁺" when the column name
            # encodes a contact (digits appear in the formatted short, e.g. "0⁻3⁺"). If it could
            # not decode one, fall back to a clean "<L/R> LFP" rather than a raw token.
            if any(ch.isdigit() for ch in short):
                label = short
            else:
                label = ("L" if hemi == "LEFT" else "R" if hemi == "RIGHT" else "") + " LFP"
                label = label.strip() or "PowerDomain LFP"
            out.append({
                "SamplingRate": -1,
                "Time": time[valid],
                "Data": np.column_stack([pw[valid], np.asarray(stim, dtype=float)[valid]]),
                "ChannelNames": [label, f"{label} Amplitude"],
                # Sensing-modality tag so the merged-series batch/scale confound can be diagnosed
                # downstream (per-session Power-Domain band power vs the ~10-min Chronic LFP power).
                "Source": "powerdomain",
                # Sensing center frequency of this streaming session (carried per sample by
                # _concat_chronic), so the decoding path can filter to one (channel, frequency).
                "CenterFrequencyHz": r.get("CenterFrequencyHz"),
            })
    return out


def _threshold_pain_level(df, label_metric, *, strategy="median", pain_cutoff=None,
                          low_pct=33.3333, high_pct=66.6667, daily_broadcast=True):
    """Binary pain_level (0/1, with NaN for the excluded middle) from a single metric column.

    The decision boundary is derived from the DAILY metric distribution (one value per calendar
    day) when `daily_broadcast` is True, then applied to every per-sample row — this prevents
    over-recorded days from dominating the cut (see bravo_chronic_to_lfp_df docstring). Strategies:
      * "cutoff"            : pain_level = metric >= pain_cutoff (default = daily median).
      * "median"            : pain_level = metric >= daily median.
      * "tertile"/"percentile": metric <= low_pct-quantile -> 0, >= high_pct-quantile -> 1,
                               middle -> NaN. "tertile" uses 33.33/66.67; "percentile" uses the args.
    Returns an ndarray aligned to df rows.
    """
    metric_vals = df[label_metric].to_numpy(dtype=float)

    # Build the distribution the thresholds are computed on.
    if daily_broadcast and "timestamp" in df.columns:
        day = pd.to_datetime(df["timestamp"], errors="coerce").dt.floor("D")
        # one value per day: mean of that day's (already nearest-date-aligned) metric values
        daily = pd.Series(metric_vals, index=day).groupby(level=0).mean()
        ref = daily.to_numpy(dtype=float)
    else:
        ref = metric_vals
    ref = ref[np.isfinite(ref)]
    if ref.size == 0:
        return np.full(len(df), np.nan)

    if strategy in ("tertile", "percentile"):
        lo_q = 33.3333 if strategy == "tertile" else float(low_pct)
        hi_q = 66.6667 if strategy == "tertile" else float(high_pct)
        lo = float(np.percentile(ref, lo_q))
        hi = float(np.percentile(ref, hi_q))
        pl = np.full(len(df), np.nan)
        with np.errstate(invalid="ignore"):
            pl[metric_vals <= lo] = 0.0
            pl[metric_vals >= hi] = 1.0
        return pl

    # median / cutoff: single threshold
    cutoff = float(np.median(ref)) if pain_cutoff is None else float(pain_cutoff)
    with np.errstate(invalid="ignore"):
        return np.where(np.isnan(metric_vals), np.nan, (metric_vals >= cutoff).astype(float))


def bravo_chronic_to_lfp_df(chronic, pro_df, *, label_metric="nrs", pain_cutoff=None,
                            label_strategy="kmeans", kmeans_features=("left_leg_vas", "mpq_sum"),
                            low_pct=33.3333, high_pct=66.6667, daily_broadcast=True,
                            timestamp_col="date_time_s1_daily", smooth_window=7):
    """
    Build the tidy `cv_df` the chronic threshold detector consumes from a BRAVO Chronic
    recording (or list of them) + REDCap PROs.

    Returns DataFrame with columns:
        timestamp        : tz-naive pd.Timestamp (per ~10-min chronic sample)
        LFP              : raw chronic LFP power (Data[:,0], device units)
        LFP_smoothed     : Savitzky-Golay smoothed LFP (window=`smooth_window`, polyorder=2)
        stim_amplitude   : mA (Data[:,1])
        pain_level       : binary 0/1 pain label (1 = higher pain)
        <label_metric>   : the carried PRO metric value (nearest-date)

    `label_strategy` selects how `pain_level` is built:
      * "kmeans" (default, matches the source notebook): 2-cluster KMeans on
        `kmeans_features` = [left_leg_vas, mpq_sum] via
        threshold_biomarker.kmeans_pain_level -- the VERBATIM notebook labeler
        (threshold_biomarker.ipynb cell 10). Requires those columns in `pro_df`. If they are
        absent, this falls back to "cutoff" and emits a warning so a missing-column run never
        silently produces garbage labels.
      * "cutoff": transparent single-metric threshold `pain_level = label_metric >= pain_cutoff`
        (default `pain_cutoff` = the metric's median). Simpler; use when you don't have the
        two cluster features or want an explicit cutoff.
      * "median": single-metric split at the metric's median (keeps every day; balanced ~50/50).
      * "tertile" / "percentile": two-threshold split — days at/below `low_pct` -> 0 (low),
        at/above `high_pct` -> 1 (high), the ambiguous middle -> NaN (excluded from training).
        "tertile" defaults to 33.33/66.67; "percentile" uses the supplied `low_pct`/`high_pct`.
        Dropping the middle gives the detector its cleanest target (best LFP separability in the
        RCS08 study) at the cost of labeling fewer days. See docs/binarization_recommendation_RCS08.md.

    For every threshold labeler (`median`/`tertile`/`percentile`/`cutoff`) the boundary is computed
    on the DAILY metric distribution and broadcast to each sample (`daily_broadcast=True`), so the
    cut reflects pain across days rather than recording density. Set `daily_broadcast=False` to fit
    the cut on the raw per-sample array (legacy behavior).
    """
    import warnings

    chronic = _concat_chronic(chronic)

    # Carry the columns we need onto each chronic sample: the label metric, plus (for KMeans)
    # the two cluster features. align_pros adds a NaN column for any metric absent from pro_df.
    carry = [label_metric]
    _THRESHOLD_STRATS = ("cutoff", "median", "tertile", "percentile")
    if label_strategy not in ("kmeans",) + _THRESHOLD_STRATS:
        warnings.warn(
            f"unknown label_strategy={label_strategy!r}; falling back to 'kmeans'.", RuntimeWarning)
        label_strategy = "kmeans"
    use_kmeans = label_strategy == "kmeans"
    if use_kmeans:
        missing = [f for f in kmeans_features if f not in pro_df.columns]
        if missing:
            warnings.warn(
                f"label_strategy='kmeans' needs columns {list(kmeans_features)} in pro_df; "
                f"missing {missing}. Falling back to label_strategy='cutoff' on '{label_metric}'.",
                RuntimeWarning,
            )
            use_kmeans = False
        else:
            carry += [f for f in kmeans_features if f not in carry]

    df = align_pros(pro_df, target="chronic", chronic=chronic,
                    metrics=tuple(carry), timestamp_col=timestamp_col)
    df = df.rename(columns={"time": "timestamp", "lfp": "LFP"})
    df["timestamp"] = _as_naive(df["timestamp"])
    # align_pros emits one row per chronic sample in Time order, so the per-sample Source array maps
    # 1:1 onto these rows — carry it through for the downstream two-source batch-confound diagnostic.
    src = chronic.get("Source")
    if src is not None and len(src) == len(df):
        df["source"] = np.asarray(src, dtype=object)
    # Per-sample sensing frequency (Hz), parallel to source: lets the decoding path filter the cv_df
    # to a single (channel, frequency) combo so chronic + streaming at the SAME band are pooled but
    # different bands are never mixed. NaN where the recording carried no CenterFrequencyHz.
    fhz = chronic.get("FrequencyHz")
    if fhz is not None and len(fhz) == len(df):
        df["frequency_hz"] = np.asarray(fhz, dtype=float)

    lfp = df["LFP"].to_numpy(dtype=float)
    n = len(lfp)
    if n >= 5:
        # Savitzky-Golay needs an ODD window length. An EVEN smooth_window must be rounded down to
        # the nearest odd value FIRST — the old expression fell through to the series-length branch
        # for any even smooth_window, silently setting wl≈n (over-smoothing LFP into a flatline).
        sw = int(smooth_window)
        if sw % 2 == 0:
            sw -= 1
        wl = sw if (n >= sw and sw >= 3) else (n if n % 2 == 1 else n - 1)
        wl = max(wl, 3)
        poly = min(2, wl - 1)
        df["LFP_smoothed"] = savgol_filter(lfp, window_length=wl, polyorder=poly)
    else:
        df["LFP_smoothed"] = lfp

    if use_kmeans:
        # KMeans pain labeler on the cluster features. Z-SCORE each feature first so a larger-scale
        # feature (e.g. left_leg_vas 0–100 vs mpq_sum 0–72) doesn't dominate the Euclidean cluster
        # distance — otherwise the "pain_level" split is effectively driven by one metric. (Rigor
        # fix; the verbatim kmeans_pain_level itself is unchanged.)
        from .routines.threshold_biomarker import kmeans_pain_level
        feats = df[list(kmeans_features)].to_numpy(dtype=float)
        mu = np.nanmean(feats, axis=0)
        sd = np.nanstd(feats, axis=0)
        sd[~np.isfinite(sd) | (sd == 0)] = 1.0
        feats_z = (feats - mu) / sd
        df["pain_level"] = kmeans_pain_level(feats_z)
    else:
        # Threshold labelers (median / tertile / percentile / cutoff). The decision boundary is
        # derived from the DAILY metric distribution (one value per calendar day), NOT the
        # per-sample array — chronic recording density varies wildly per day (6..70k samples),
        # so a per-sample quantile lets a few over-recorded days set the cut. We compute the
        # threshold(s) on the deduplicated daily series, then broadcast the label to every sample.
        df["pain_level"] = _threshold_pain_level(
            df, label_metric, strategy=label_strategy, pain_cutoff=pain_cutoff,
            low_pct=low_pct, high_pct=high_pct, daily_broadcast=daily_broadcast)

    out_cols = ["timestamp", "LFP", "LFP_smoothed", "stim_amplitude", "pain_level", label_metric]
    if "source" in df.columns:
        out_cols.append("source")
    if "frequency_hz" in df.columns:
        out_cols.append("frequency_hz")
    for f in kmeans_features:
        if f in df.columns and f not in out_cols:
            out_cols.append(f)
    return df[out_cols]


def decimate_for_plot(df, max_points):
    """Stride-thin a timeline DataFrame to <= `max_points` rows, FOR PLOTTING/TRANSPORT ONLY.

    Pure: returns a row-subset (no interpolation, columns and value scale unchanged); the original
    is never mutated. This must NEVER feed a calculation — every biomarker / threshold / AUC /
    frequency value is computed upstream on the FULL-resolution frames (run_biomarker,
    _compute_analytics) and only the display timeline is thinned here. Keeping this a named, pure
    function makes that invariant explicit and testable.
    """
    if df is None or not hasattr(df, "__len__") or max_points <= 0 or len(df) <= max_points:
        return df
    stride = int(np.ceil(len(df) / max_points))
    return df.iloc[::stride].reset_index(drop=True)


def _as_naive(series):
    """Return a tz-naive datetime Series (no-op if already naive)."""
    s = pd.to_datetime(series, errors="coerce")
    try:
        return s.dt.tz_localize(None)
    except (TypeError, AttributeError):
        return s


def merge_timelines(td_timeline, chronic_timeline):
    """
    Merge the time-domain and chronic source timelines onto ONE frame for the "same page" view.

    Both single-source cases are degenerate (return the present frame, NaN-tolerant). When both
    are present, the dense chronic (~10-min) frame is the spine and each chronic row gets the
    nearest-date session's `td_*` columns attached via merge_asof (tolerance 1 day). Upsampling
    sparse sessions onto the dense spine preserves every chronic sample; a chronic sample with
    no session within a day keeps NaN `td_*` (render as a gap, do not interpolate).
    """
    if td_timeline is None and chronic_timeline is None:
        return pd.DataFrame()
    if chronic_timeline is None:
        return td_timeline.reset_index(drop=True)
    if td_timeline is None:
        return chronic_timeline.reset_index(drop=True)

    left = chronic_timeline.copy()
    right = td_timeline.copy()
    left["time"] = _as_naive(left["time"])
    right["time"] = _as_naive(right["time"])
    # Avoid a duplicate shared 'date' column collision in the merge output.
    if "date" in right.columns:
        right = right.drop(columns=["date"])
    # Drop rows with NaT time (e.g. a session lacking a usable StartTime) before merge_asof,
    # which raises ValueError on null merge keys. Dropping degrades gracefully vs crashing.
    left = left.dropna(subset=["time"]).sort_values("time")
    right = right.dropna(subset=["time"]).sort_values("time")
    merged = pd.merge_asof(left, right, on="time", direction="nearest",
                           tolerance=pd.Timedelta("1D"))
    return merged.reset_index(drop=True)
