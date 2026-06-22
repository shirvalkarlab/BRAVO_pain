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


def pain_series(pro_df, metric, timestamp_col="date_time_s1_daily"):
    """Real patient-reported pain series for the shared-axis pain row.

    Returns {"metric": metric, "t": [epoch_s...], "y": [value...]} sorted by time, dropping rows
    with a missing timestamp or metric value. `pro_df` is the REDCap PRO table already loaded by
    bravo_service._load_pros; `metric` is the resolved LabelMetric (nrs/vas/.../composite).
    """
    if pro_df is None or metric is None or len(pro_df) == 0:
        return {"metric": metric, "t": [], "y": []}
    if timestamp_col not in pro_df.columns or metric not in pro_df.columns:
        return {"metric": metric, "t": [], "y": []}
    import pandas as pd
    ts = pd.to_datetime(pro_df[timestamp_col], errors="coerce")
    vals = pd.to_numeric(pro_df[metric], errors="coerce")
    keep = ts.notna() & vals.notna()
    pairs = sorted(zip(ts[keep], vals[keep]), key=lambda p: p[0])
    return {"metric": metric,
            "t": [p[0].timestamp() for p in pairs],
            "y": [float(p[1]) for p in pairs]}


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
        hz = hemi_hz.get(hemi) if hemi else None
        key = hemi_contact.get(hemi, chan)   # prefer the configured sensing contact for this side
        col = data[:, 0]
        bad = (col >= _POWER_SENTINEL) | (col < 0) | ~np.isfinite(col)
        for i in np.where(~bad)[0]:
            _push(key, float(tarr[i]), col[i], hz, "chronic")

    # time-sort each channel's pooled samples
    for ch, d in out.items():
        order = np.argsort(d["t"])
        d["t"] = [d["t"][i] for i in order]
        d["y"] = [d["y"][i] for i in order]
        d["center_hz"] = [d["center_hz"][i] for i in order]
        d["source"] = [d["source"][i] for i in order]
    return out


def present_freq_bands(records):
    """Distinct snapped sensing center frequencies that actually appear on bandpower channels.
    Drives the categorical legend so it matches the lanes that render a trend (not all channels)."""
    bands = set()
    for r in records:
        if r["dtype"] == "bandpower" and r["meta"].get("center_hz") is not None:
            bands.add(r["meta"]["center_hz"])
    return sorted(bands)
