"""Per-channel data-availability extraction for the Biomarker Data Timeline.

Django-free, unit-tested. Walks DECODED Percept recording dicts (already loaded by
`bravo_service._load_recordings`) and emits one availability RECORD per recording-channel:

    {channel, hemisphere, dtype, product, t_start, dur_s, meta}

`dtype` is the DENSITY-gated lane the frontend draws into (see DESIGN §8e):
    "timedomain"  -> raw 250 Hz uV   (coverage block; zoom reveals waveform)
    "bandpower"   -> LFP Power (LSB)  (inline trend, colored by sensing center freq)
    "psd"         -> 0-97 Hz spectrum (tick; hover reveals the curve)

The five Percept products collapse onto these three lanes:
    Indefinite Stream / BrainSense TimeDomain         -> timedomain
    Chronic BrainSense (Timeline) / Power-Domain      -> bandpower
    BrainSense Survey / Baseline+Stim Montages /Event -> psd

Timestamps reuse each recording's `StartTime` (epoch float or ISO) — the saver already stamps it
from the JSON `FirstPacketDateTime`, so there is NO timestamp bug in the production path (the bug
was only in the agent's raw-JSON probe, which filtered montage channels by the wrong label).
"""
import datetime
import numpy as np

from . import analytics

# Recording.type -> (dtype lane, product key). Mirrors the type strings assigned at ingestion in
# MedtronicPercept/Session.py. Several map onto the same lane (density-gated, not product-gated).
TYPE_MAP = {
    "MedtronicBrainSenseTimeDomain": ("timedomain", "streaming_td"),
    "MedtronicIndefiniteStream":     ("timedomain", "indefinite"),
    "MedtronicChronicBrainSense":    ("bandpower",  "timeline_lsb"),
    "MedtronicBrainSensePowerDomain":("bandpower",  "streaming_lsb"),
    "MedtronicBrainSenseSurvey":     ("psd",        "survey_psd"),
    "MedtronicBaselineMontages":     ("psd",        "montage_psd"),
    "MedtronicStimulationMontages":  ("psd",        "montage_psd"),
}
# Recording types to load for the availability timeline (superset of the decoder's four).
AVAILABILITY_TYPES = list(TYPE_MAP.keys())

# Percept LFP-power FFT bins (snapped sensing center freqs), matching FREQ_PALETTE on the frontend.
_FFT_BINS = np.array([3.9, 4.9, 5.9, 6.8, 7.8, 8.8, 9.8, 10.7, 11.7, 12.7, 13.7, 14.6,
                      15.6, 16.6, 17.6, 18.6, 19.5, 20.5, 21.5, 22.5, 23.4, 24.4, 25.4, 26.4])


def snap_freq(hz):
    """Snap a center frequency to the nearest Percept FFT bin (None-safe)."""
    if hz is None:
        return None
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(hz):
        return None
    return float(_FFT_BINS[int(np.argmin(np.abs(_FFT_BINS - hz)))])


def _to_epoch(value):
    """BRAVO StartTime -> Unix epoch seconds (float), or None. Accepts epoch float/int or ISO str."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if v >= 1e9 else None  # reject session-offset / 1970 values
    if isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.timestamp()
        except ValueError:
            return None
    if isinstance(value, datetime.datetime):
        return value.timestamp()
    return None


def _hemisphere(channel):
    cu = str(channel).upper()
    return "Left" if "LEFT" in cu else ("Right" if "RIGHT" in cu else "")


def _channels_of(rec):
    """The per-channel sensing names a recording carries (ChannelNames, '<x> Power' stripped)."""
    names = rec.get("ChannelNames") or []
    out = []
    for nm in names:
        s = str(nm)
        # power-domain Data columns are '<contact> Power' / '<contact> Stimulation' / '<hemi> LFP'
        if "STIMULATION" in s.upper() or s.upper().endswith(" AMPLITUDE"):
            continue
        contact = s.rsplit(" ", 1)[0] if (" " in s and s.split(" ")[-1].upper() in
                                          ("POWER", "LFP")) else s
        if contact not in out:
            out.append(contact)
    return out


def extract_availability(recordings_by_type, region_map=None):
    """Build the per-channel availability records from decoded recordings.

    Parameters
    ----------
    recordings_by_type : dict[str, list[dict]]
        {Recording.type: [decoded recording dicts]} for the AVAILABILITY_TYPES.
    region_map : dict | None
        {raw channel -> region}, for human labels (optional).

    Returns
    -------
    list[dict]  availability records (see module docstring).
    """
    region_map = region_map or {}
    records = []
    for rtype, recs in (recordings_by_type or {}).items():
        lane = TYPE_MAP.get(rtype)
        if lane is None:
            continue
        dtype, product = lane
        # center freq per contact (bandpower products only)
        cfreqs = analytics.power_center_freqs(recs) if dtype == "bandpower" else {}
        for r in recs or []:
            if not isinstance(r, dict):
                continue
            t0 = _to_epoch(r.get("StartTime"))
            if t0 is None and dtype == "bandpower":
                # chronic carries a Time array; use its first absolute sample
                tarr = r.get("Time")
                if tarr is not None and len(tarr):
                    t0 = _to_epoch(float(np.asarray(tarr, dtype=float)[0]))
            if t0 is None:
                continue
            # duration
            dur = r.get("Duration")
            if dur is None:
                tarr = r.get("Time")
                data = r.get("Data")
                if tarr is not None and len(tarr) > 1:
                    dur = float(np.asarray(tarr, float)[-1] - np.asarray(tarr, float)[0])
                elif data is not None and r.get("SamplingRate"):
                    n = np.asarray(data).shape[0]
                    sr = float(r.get("SamplingRate") or 0) or None
                    dur = (n / sr) if sr else 30.0
                else:
                    dur = 30.0
            # chronic Timeline freq is per-hemisphere on this recording's Therapy snapshot, not a
            # '<contact> Power' column — resolve a hemisphere->Hz map for the LFP-channel fallback.
            hemi_hz = {}
            if dtype == "bandpower":
                desc = r.get("Descriptor")
                therapy = desc.get("Therapy") if isinstance(desc, dict) else None
                if isinstance(therapy, dict):
                    hemi_hz = {"LEFT": analytics.sensing_center_hz(therapy.get("Left")),
                               "RIGHT": analytics.sensing_center_hz(therapy.get("Right"))}
            for ch in _channels_of(r):
                hz = cfreqs.get(ch)
                if hz is None and hemi_hz:
                    cu = ch.upper()
                    hz = hemi_hz.get("LEFT") if "LEFT" in cu else (
                         hemi_hz.get("RIGHT") if "RIGHT" in cu else None)
                fmt = analytics.format_channel(ch, region=region_map.get(ch))
                records.append({
                    "channel": ch,
                    "label": fmt.get("short", ch),
                    "hemisphere": _hemisphere(ch),
                    "dtype": dtype,
                    "product": product,
                    "t_start": float(t0),
                    "dur_s": float(dur or 0.0),
                    "meta": {"center_hz": snap_freq(hz),
                             "peak_hz": snap_freq(r.get("PeakFrequencyInHertz")),
                             "n": int(np.asarray(r.get("Data")).shape[0]) if r.get("Data") is not None else None},
                })
    records.sort(key=lambda x: (x["channel"], x["t_start"]))
    return records


def pain_series(pro_df, metric, timestamp_col="date_time_s1_daily", utc_col="_pro_time_utc"):
    """Real patient-reported pain series for the shared-axis pain row.

    Returns {"metric": metric, "t": [epoch_s...], "y": [value...]} sorted by time, dropping rows
    with a missing timestamp or metric value. `pro_df` is the REDCap PRO table already loaded by
    bravo_service._load_pros; `metric` is the resolved LabelMetric (nrs/vas/.../composite).

    PRO TIMES: prefer the canonical `_pro_time_utc` column that bravo_service._load_pros adds at
    ingestion (DST-aware CA-local -> tz-naive UTC). Epochs come from `.to_numpy().astype("datetime64[ns]").astype("int64")/1e9` — the SAME
    convention bravo_service._pro_match_arrays uses — NOT Timestamp.timestamp(), which would re-apply
    a tz interpretation to the tz-naive UTC value and reintroduce the offset. This keeps the live
    pain row bit-identical to the offline match pool. Falls back to a localize-free naive parse of
    `timestamp_col` ONLY for DataFrames built outside _load_pros (the historical 7-8 h-early path);
    production always carries the normalized column. (FIXHANDOUT_pro_timezone_mismatch)
    """
    if pro_df is None or metric is None or len(pro_df) == 0:
        return {"metric": metric, "t": [], "y": []}
    if metric not in pro_df.columns:
        return {"metric": metric, "t": [], "y": []}
    import pandas as pd
    import numpy as np
    if utc_col in pro_df.columns:
        ts = pd.to_datetime(pro_df[utc_col], errors="coerce")
    elif timestamp_col in pro_df.columns:
        ts = pd.to_datetime(pro_df[timestamp_col], errors="coerce")
    else:
        return {"metric": metric, "t": [], "y": []}
    vals = pd.to_numeric(pro_df[metric], errors="coerce")
    keep = ts.notna() & vals.notna()
    ts_k = ts[keep]
    # Resolution-independent ns epoch (Series.view is deprecated/removed in pandas 3.0; bare
    # .astype("int64") yields microseconds under pandas 3.0's datetime64[us] default).
    ep = (ts_k.to_numpy().astype("datetime64[ns]").astype("int64") / 1e9)
    vy = vals[keep].to_numpy(dtype=float)
    order = np.argsort(ep)
    return {"metric": metric,
            "t": ep[order].tolist(),
            "y": vy[order].tolist()}


def stim_series(chronic_recordings):
    """Real stimulation-amplitude-over-time (mA) for the shared-axis stim row.

    The chronic BrainSense Timeline carries per-sample stim amplitude in Data[:,1] paired with its
    absolute Time array (the same packets that carry the 10-min LFP power). Concatenate across
    chronic recordings, sort by time, drop non-finite. Returns {"t": [epoch_s...], "y": [mA...]}.
    Falls back to empty when no chronic recordings carry an amplitude column.
    """
    ts, ys = [], []
    for r in chronic_recordings or []:
        if not isinstance(r, dict):
            continue
        tarr = r.get("Time")
        data = r.get("Data")
        if tarr is None or data is None:
            continue
        tarr = np.asarray(tarr, dtype=float)
        data = np.asarray(data, dtype=float)
        if data.ndim != 2 or data.shape[1] < 2 or len(tarr) != data.shape[0]:
            continue
        amp = data[:, 1]
        finite = np.isfinite(amp) & np.isfinite(tarr) & (tarr >= 1e9)
        ts.extend(tarr[finite].tolist())
        ys.extend(amp[finite].tolist())
    order = np.argsort(ts) if ts else []
    return {"t": [ts[i] for i in order], "y": [ys[i] for i in order]}


def event_markers(events_raw, *, fmin=2.0, fmax=100.0):
    """Patient-triggered LFP snapshot events -> labeled timeline marker series.

    Each event is a PATIENT button press the patient annotated with a clinical LABEL ("Higher Pain",
    "Tingly/Burning", "Feeling Good", "Medication", "Dyskinesia", ...). The Percept stores the press
    as a `LfpFrequencySnapshotEvents` record carrying, per sensing hemisphere, the event time and a
    full-band PSD (`Frequency` + `FFTBinData`, ~0-100 Hz). These NEVER feed the decoder — they only
    corroborate (DESIGN §2/§6) — but the clinician needs to SEE when the patient flagged a moment
    AND what they called it, so we demarcate each on the timeline with its label.

    Parameters
    ----------
    events_raw : list[dict]
        Normalized events from the DB-coupled loader, each:
            {"name": str, "t": epoch_s, "psds": [(freq_array, power_array), ...]}
        (`psds` is one entry per hemisphere that carried a spectrum.)

    For each event we return its time, LABEL, and a compact spectral summary across hemispheres:
      * label: the patient-assigned event name (what the marker hover shows).
      * peak_hz: frequency of the largest spectral peak in [fmin, fmax] (averaged across hemispheres,
        snapped to the Percept FFT bin) — kept for the hover/overview, not the color.
      * peak_power: band power at that peak (raw FFT-bin units), for the hover.
      * a decimated averaged PSD ({freq, mag}) so the frontend hover-overview can draw the spectrum.

    Returns {"events": [{"t", "label", "peak_hz", "peak_power", "n_chan",
                         "psd": {"freq", "mag"} | None}, ...],
             "labels": [distinct labels, sorted], "n": int}  sorted by time.
    """
    events = []
    for e in events_raw or []:
        if not isinstance(e, dict):
            continue
        t0 = _to_epoch(e.get("t"))
        if t0 is None:
            continue
        label = str(e.get("name") or "event")
        # average the per-hemisphere PSDs onto a common frequency grid
        freq = None
        mags = []
        for item in (e.get("psds") or []):
            try:
                f = np.asarray(item[0], dtype=float)
                m = np.asarray(item[1], dtype=float)
            except (TypeError, ValueError, IndexError):
                continue
            if f.size == 0 or f.size != m.size:
                continue
            if freq is None:
                freq = f
            if f.size == freq.size:
                mags.append(m)
        peak_hz = peak_power = None
        psd = None
        if freq is not None and mags:
            avg = np.nanmean(np.vstack(mags), axis=0)
            band = (freq >= fmin) & (freq <= fmax) & np.isfinite(avg)
            if band.any():
                fb, ab = freq[band], avg[band]
                j = int(np.argmax(ab))
                peak_hz = snap_freq(float(fb[j]))
                peak_power = float(ab[j])
            keep = (np.arange(freq.size) if freq.size <= 120
                    else np.arange(0, freq.size, max(1, freq.size // 120)))
            psd = {"freq": [float(freq[k]) for k in keep],
                   "mag": [float(avg[k]) if np.isfinite(avg[k]) else None for k in keep]}
        events.append({
            "t": float(t0),
            "label": label,
            "peak_hz": peak_hz,
            "peak_power": peak_power,
            "n_chan": len(mags),
            "psd": psd,
        })
    events.sort(key=lambda e: e["t"])
    labels = sorted({e["label"] for e in events})
    return {"events": events, "labels": labels, "n": len(events)}


def _decimate(arr, n=2000):
    arr = np.asarray(arr, dtype=float)
    if len(arr) > n:
        arr = arr[:: max(1, len(arr) // n)]
    return arr.tolist()


def inspector_samples(channel, *, td_recs=None, psd_recs=None, chronic_recs=None,
                      powerdomain_recs=None):
    """Decimated real signal for ONE channel's inspector: a representative PSD curve, a raw uV
    waveform, and the LSB trend. Each block is optional (absent -> frontend shows 'n.d.').

    Returns {"psd": {"freq", "mag", "peak_hz"} | None,
             "td":  {"fs", "sample"}          | None,
             "lsb": {"t", "y", "center_hz"}   | None}
    """
    cu = str(channel).upper()
    out = {"psd": None, "td": None, "lsb": None}

    # raw TD: first recording whose channel matches (the lane's waveform)
    for r in (td_recs or []):
        if not isinstance(r, dict):
            continue
        names = [str(n).upper() for n in (r.get("ChannelNames") or [])]
        if cu in names:
            j = names.index(cu)
            data = np.asarray(r.get("Data"))
            if data.ndim == 2 and data.shape[1] > j:
                col = data[:, j]
                out["td"] = {"fs": float(r.get("SamplingRate") or 250),
                             "sample": _decimate(col[: int((r.get("SamplingRate") or 250) * 8)])}
                break

    # PSD: first montage/survey recording for this channel (freq/mag arrays)
    for r in (psd_recs or []):
        if not isinstance(r, dict):
            continue
        names = [str(n).upper() for n in (r.get("ChannelNames") or [])]
        if cu in names:
            freq = r.get("Frequency") or r.get("LFPFrequency")
            mag = r.get("Power") or r.get("LFPMagnitude")
            if freq is not None and mag is not None:
                out["psd"] = {"freq": _decimate(freq, 200), "mag": _decimate(mag, 200),
                              "peak_hz": snap_freq(r.get("PeakFrequencyInHertz"))}
                break

    # LSB trend: concatenate this channel's chronic + power-domain band power vs time
    ts, ys = [], []
    for r in (chronic_recs or []):
        if not isinstance(r, dict):
            continue
        names = [str(n).upper() for n in (r.get("ChannelNames") or [])]
        # chronic channels are '<hemi>Hemisphere LFP'; match by hemisphere token
        hemi = "LEFT" if "LEFT" in cu else ("RIGHT" if "RIGHT" in cu else "")
        if any(hemi in n and "LFP" in n for n in names):
            tarr = np.asarray(r.get("Time", []), dtype=float)
            data = np.asarray(r.get("Data"))
            if len(tarr) and data.ndim == 2 and data.shape[0] == len(tarr):
                ts.extend(tarr.tolist()); ys.extend(data[:, 0].tolist())
    if ts:
        order = np.argsort(ts)
        out["lsb"] = {"t": [ts[i] for i in order][:3000], "y": [ys[i] for i in order][:3000],
                      "center_hz": None}
    return out


_POWER_SENTINEL = 2.0 ** 31 - 1   # device missing-sample sentinel for LFP power columns


def lsb_series(chronic_recordings, powerdomain_recordings, region_map=None):
    """REAL band-power (LSB) time series per channel, for inline display on the timeline.

    Unlike `extract_availability` (which emits one metadata RECORD per recording), this returns the
    ACTUAL per-sample LFP-power values vs absolute time, so the frontend draws the true trace — not
    a placeholder. Two products feed each channel and are pooled in RAW device units (no scaling,
    same convention as the decoder):

      * Power-Domain (~2 Hz streaming): each '<contact> Power' column -> that contact's series, with
        the contact's sensing CENTER FREQUENCY (from Descriptor.Therapy) tagged on every sample.
      * Chronic Timeline (~10-min around-the-clock): Data[:,0] is the per-hemisphere LFP power,
        Time[:] is absolute epoch; the sensing center frequency comes from the recording's
        Therapy snapshot (per hemisphere).

    Returns dict keyed by RAW channel name:
        { channel: { "t":[epoch_s], "y":[lsb], "center_hz":[hz|None], "source":["streaming"|"chronic"] } }
    Sentinel/negative/non-finite samples are dropped. Samples are time-sorted; each carries its own
    center_hz so the frontend can color the trace by frequency AND honestly show when sensing moved.
    """
    region_map = region_map or {}
    out = {}

    def _push(ch, t, y, hz, src):
        d = out.setdefault(ch, {"t": [], "y": [], "center_hz": [], "source": []})
        d["t"].append(float(t)); d["y"].append(float(y))
        d["center_hz"].append(snap_freq(hz)); d["source"].append(src)

    # --- Power-Domain (~2 Hz): per-contact Power columns ---
    pd_center = analytics.power_center_freqs(powerdomain_recordings)
    for r in powerdomain_recordings or []:
        if not isinstance(r, dict) or "Data" not in r:
            continue
        names = list(r.get("ChannelNames", []) or [])
        data = np.asarray(r.get("Data"), dtype=float)
        if data.ndim != 2 or data.shape[0] == 0:
            continue
        n, ncols = data.shape
        fs = float(r.get("SamplingRate") or 2.0) or 2.0
        start = _to_epoch(r.get("StartTime"))
        if start is None:
            continue
        times = start + np.arange(n) / fs
        missing = np.asarray(r.get("Missing", np.zeros_like(data)), dtype=float)
        if missing.shape != data.shape:
            missing = np.zeros_like(data)
        for pi, nm in enumerate(names):
            if pi >= ncols or "POWER" not in str(nm).upper():
                continue
            contact = str(nm).rsplit(" ", 1)[0] if " " in str(nm) else str(nm)
            hz = pd_center.get(contact)
            col = data[:, pi]
            bad = (missing[:, pi] > 0) | (col >= _POWER_SENTINEL) | (col < 0) | ~np.isfinite(col)
            for i in np.where(~bad)[0]:
                _push(contact, times[i], col[i], hz, "streaming")

    # --- Chronic Timeline (~10-min): per-hemisphere LFP power ---
    # Chronic recordings name their channel by HEMISPHERE ('LeftHemisphere LFP'), but the timeline
    # lanes are keyed by CONTACT PAIR (e.g. 'ZERO_THREE_LEFT'). Resolve each hemisphere's chronic
    # log onto the configured sensing CONTACT for that hemisphere (the contact the power-domain
    # streaming used) so streaming + chronic for the same physical channel pool into ONE lane. Fall
    # back to the hemisphere-token channel name when no streaming contact is known for that side.
    hemi_contact = {}
    for contact in pd_center.keys():
        cu = str(contact).upper()
        side = "LEFT" if "LEFT" in cu else ("RIGHT" if "RIGHT" in cu else "")
        if side and side not in hemi_contact:
            hemi_contact[side] = contact
    for r in chronic_recordings or []:
        if not isinstance(r, dict) or "Data" not in r:
            continue
        names = list(r.get("ChannelNames", []) or [])
        data = np.asarray(r.get("Data"), dtype=float)
        tarr = np.asarray(r.get("Time", []), dtype=float)
        if data.ndim != 2 or data.shape[0] == 0 or len(tarr) != data.shape[0]:
            continue
        # chronic channel name is '<hemi>Hemisphere LFP'; derive its sensing center from Therapy
        desc = r.get("Descriptor")
        therapy = desc.get("Therapy") if isinstance(desc, dict) else None
        hemi_hz = {}
        if isinstance(therapy, dict):
            hemi_hz = {"LEFT": analytics.sensing_center_hz(therapy.get("Left")),
                       "RIGHT": analytics.sensing_center_hz(therapy.get("Right"))}
        chan = names[0] if names else "LFP"
        cu = str(chan).upper()
        hemi = "LEFT" if "LEFT" in cu else ("RIGHT" if "RIGHT" in cu else "")
        key = hemi_contact.get(hemi, chan)   # prefer the configured sensing contact for this side

        # Per-sample sensing center frequency for the chronic 24/7 trend. The band is reprogrammed
        # over the implant, so the accurate source is the dated GroupHistory schedule stamped onto
        # the recording at decode time (`FreqScheduleHz` = [[epoch_SECONDS, hz], ...]). Resolve the
        # frequency in force at each sample (last change-point at or before it). Fall back, in order,
        # to the recording's single stamped `CenterFrequencyHz`, then the Therapy snapshot — so a
        # recording with no schedule still gets a flat (but non-null) frequency rather than "?".
        sched_raw = r.get("FreqScheduleHz")
        sched = []
        if isinstance(sched_raw, (list, tuple)):
            for item in sched_raw:
                try:
                    ts, shz = float(item[0]), snap_freq(item[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if shz is not None:
                    sched.append((ts, shz))
            sched.sort(key=lambda p: p[0])
        scalar_hz = snap_freq(r.get("CenterFrequencyHz"))
        fallback_hz = scalar_hz if scalar_hz is not None else (hemi_hz.get(hemi) if hemi else None)

        def _hz_at(ts):
            cur = None
            for cms, chz in sched:
                if cms <= ts:
                    cur = chz
                else:
                    break
            if cur is not None:
                return cur
            if sched:
                return sched[0][1]   # data begins before first change-point: use earliest known
            return fallback_hz

        col = data[:, 0]
        bad = (col >= _POWER_SENTINEL) | (col < 0) | ~np.isfinite(col)
        for i in np.where(~bad)[0]:
            _push(key, float(tarr[i]), col[i], _hz_at(float(tarr[i])), "chronic")

    # time-sort each channel's pooled samples
    for ch, d in out.items():
        order = np.argsort(d["t"])
        d["t"] = [d["t"][i] for i in order]
        d["y"] = [d["y"][i] for i in order]
        d["center_hz"] = [d["center_hz"][i] for i in order]
        d["source"] = [d["source"][i] for i in order]
    return out


def lsb_overview(lsb, *, session_gap_s=1800.0, chronic_max_points=1500):
    """Compact the per-sample LSB series into RENDER-CHEAP geometry for the calendar-scale timeline.

    Drawing every 2 Hz streaming sample as its own point makes the page sluggish (tens of thousands
    of WebGL points + per-point hover tests). At year scale a 2 Hz session is an unresolvable spike
    anyway, so this collapses each series into two light-weight layers that carry the SAME
    information:

      * chronic  -> a single decimated LINE of the real ~10-min trend (continuous around-the-clock
                    band power), tagged per-sample with its sensing center frequency so the frontend
                    can colour the trend by frequency (chronic sensing freq DOES change over time).
      * streaming-> one BLOCK per session (contiguous run of samples with <= session_gap_s spacing),
                    summarizing that on-demand recording: start/end time, median LSB, 10-90 pct band,
                    sample count, and the session's sensing center frequency (for the categorical
                    color). ~one block per recording instead of hundreds of points.

    Returns {channel: {"chronic": {"t":[],"y":[]} | None,
                       "sessions": [{"t0","t1","med","lo","hi","center_hz","n"}],
                       "y_lo","y_hi"}}  where y_lo/y_hi are the robust (2-98 pct) magnitude window
    across BOTH layers, so the frontend scales the lane once and consistently.
    """
    out = {}
    for ch, d in (lsb or {}).items():
        t = np.asarray(d.get("t", []), dtype=float)
        y = np.asarray(d.get("y", []), dtype=float)
        cen = list(d.get("center_hz", []))
        src = list(d.get("source", []))
        if t.size == 0:
            continue
        # robust magnitude window across all real samples in this lane
        finite = y[np.isfinite(y)]
        y_lo = float(np.percentile(finite, 2)) if finite.size else 0.0
        y_hi = float(np.percentile(finite, 98)) if finite.size else 1.0

        chronic_mask = np.array([s == "chronic" for s in src], dtype=bool)
        # --- chronic: decimated real line, carrying its per-sample sensing center frequency ---
        # Chronic 24/7 sensing DOES change center frequency over the implant (each chronic
        # recording's Therapy snapshot sets it), so the trend is tagged per-sample with center_hz
        # and decimated on the SAME stride as t/y (index-based) so colour stays aligned to the line.
        chronic = None
        if chronic_mask.any():
            ci = np.where(chronic_mask)[0]
            ct, cy = t[ci], y[ci]
            ccen = np.array([snap_freq(cen[i]) if cen[i] is not None else np.nan
                             for i in ci], dtype=float)
            # decimate by index so t / y / center_hz stay positionally aligned (mirrors _decimate)
            keep = (np.arange(len(ci)) if len(ci) <= chronic_max_points
                    else np.arange(0, len(ci), max(1, len(ci) // chronic_max_points)))
            chronic = {"t": [float(ct[k]) for k in keep],
                       "y": [float(cy[k]) for k in keep],
                       "center_hz": [None if np.isnan(ccen[k]) else float(ccen[k]) for k in keep]}

        # --- streaming: one block per session (split on time gaps) ---
        sessions = []
        s_idx = np.where(~chronic_mask)[0]
        if s_idx.size:
            st, sy = t[s_idx], y[s_idx]
            scen = [snap_freq(cen[i]) for i in s_idx]
            # contiguous runs: a new session starts when the time gap exceeds session_gap_s OR the
            # sensing center frequency changes (a re-config is a distinct recording session).
            start = 0
            for k in range(1, len(st) + 1):
                brk = (k == len(st))
                if not brk:
                    gap = st[k] - st[k - 1] > session_gap_s
                    freq_change = scen[k] != scen[start]
                    brk = gap or freq_change
                if brk:
                    seg_y = sy[start:k]
                    seg_y = seg_y[np.isfinite(seg_y)]
                    if seg_y.size:
                        sessions.append({
                            "t0": float(st[start]), "t1": float(st[k - 1]),
                            "med": float(np.median(seg_y)),
                            "lo": float(np.percentile(seg_y, 10)),
                            "hi": float(np.percentile(seg_y, 90)),
                            "center_hz": scen[start], "n": int(seg_y.size)})
                    start = k
        out[ch] = {"chronic": chronic, "sessions": sessions, "y_lo": y_lo, "y_hi": y_hi}
    return out


def present_freq_bands(records):
    """Distinct snapped sensing center frequencies that actually appear on bandpower channels.
    Drives the categorical legend so it matches the lanes that render a trend (not all channels)."""
    bands = set()
    for r in records:
        if r["dtype"] == "bandpower" and r["meta"].get("center_hz") is not None:
            bands.add(r["meta"]["center_hz"])
    return sorted(bands)
