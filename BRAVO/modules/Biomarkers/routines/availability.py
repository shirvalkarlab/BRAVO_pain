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


def _canon_channel(name):
    """Normalize a Medtronic channel name to the canonical bipolar form (ring/sweep -> short).

    `ZERO_AND_THREE_LEFT_RING` -> `ZERO_THREE_LEFT`; already-short names are unchanged (idempotent).
    Mirrors bravo_service._canon_channel; kept module-local to avoid a routines->service import.
    """
    u = str(name).upper().replace("_AND_", "_")
    if u.endswith("_RING"):
        u = u[:-len("_RING")]
    return u


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
                n_samp = (int(np.asarray(r.get("Data")).shape[0])
                          if r.get("Data") is not None else None)
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
                             "n": n_samp},
                })
                # MONTAGE-TD COVERAGE TWIN: the survey/montage products (psd lane) carry raw 250 Hz
                # time-domain in Recording["Data"] just like indefinite streaming, but were only ever
                # surfaced as PSD ticks. Emit a PARALLEL timedomain coverage record so montage TD
                # draws the SAME raw-coverage block as BrainSense/Indefinite streaming (zoom → the
                # waveform), in addition to its PSD tick + modeled-LSB diamond. Frontend collapses the
                # (possibly ring-named) channel onto the canonical lane via normalizeChannel. Only when
                # the record actually carries a real 2-D TD array — a PSD-only montage has nothing to
                # show as coverage. This is DISPLAY-ONLY: av.records feeds the timeline, never the
                # pooled-PSD scan or the deployment path.
                _td_data = r.get("Data")
                if dtype == "psd" and _td_data is not None and np.asarray(_td_data).ndim == 2:
                    records.append({
                        "channel": ch,
                        "label": fmt.get("short", ch),
                        "hemisphere": _hemisphere(ch),
                        "dtype": "timedomain",
                        "product": "montage_td",
                        "t_start": float(t0),
                        "dur_s": float(dur or 0.0),
                        "meta": {"center_hz": snap_freq(hz),
                                 "peak_hz": snap_freq(r.get("PeakFrequencyInHertz")),
                                 "n": n_samp, "from_product": product},
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

    Each event also carries a `category` (DISPLAY_STREAMING_EVENT / DISPLAY_PATIENT_EVENT /
    DISPLAY_MONTAGE_SNAPSHOT) from the loader, so the frontend can render the three PSD-event sources
    on distinct rows/glyphs. The auto-fired "Streaming" snapshots are now included (no longer dropped)
    under DISPLAY_STREAMING_EVENT.

    Returns {"events": [{"t", "label", "category", "peak_hz", "peak_power", "n_chan",
                         "psd": {"freq", "mag"} | None}, ...],
             "labels": [distinct labels, sorted],
             "categories": [distinct categories, sorted], "n": int}  sorted by time.
    """
    events = []
    for e in events_raw or []:
        if not isinstance(e, dict):
            continue
        t0 = _to_epoch(e.get("t"))
        if t0 is None:
            continue
        label = str(e.get("name") or "event")
        # display category (DISPLAY_STREAMING_EVENT vs DISPLAY_PATIENT_EVENT vs DISPLAY_MONTAGE_SNAPSHOT)
        # carried from the loader so the frontend can render each source on its own row/glyph. Falls
        # back to the label when a caller didn't tag one. (Both event loaders tag `category` explicitly
        # now; the montage loader's marker name == DISPLAY_MONTAGE_SNAPSHOT, so even an untagged montage
        # marker would fall back to the correct category — intentional belt-and-suspenders, not luck.)
        category = str(e.get("category") or label)
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
            "category": category,
            "peak_hz": peak_hz,
            "peak_power": peak_power,
            "n_chan": len(mags),
            "psd": psd,
        })
    events.sort(key=lambda e: e["t"])
    labels = sorted({e["label"] for e in events})
    categories = sorted({e["category"] for e in events})
    return {"events": events, "labels": labels, "categories": categories, "n": len(events)}


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


def lsb_series(chronic_recordings, powerdomain_recordings, region_map=None,
               montage_td_recordings=None, sensing_hz_by_channel=None,
               event_psd_recordings=None):
    """REAL band-power (LSB) time series per channel, for inline display on the timeline.

    Unlike `extract_availability` (which emits one metadata RECORD per recording), this returns the
    ACTUAL per-sample LFP-power values vs absolute time, so the frontend draws the true trace — not
    a placeholder. Three sources feed each channel:

      * NATIVE device LSB (preferred — the band was actually sensed):
        - Power-Domain (~2 Hz streaming): each '<contact> Power' column -> that contact's series, with
          the contact's sensing CENTER FREQUENCY (from Descriptor.Therapy) tagged on every sample.
        - Chronic Timeline (~10-min around-the-clock): Data[:,0] is the per-hemisphere LFP power,
          Time[:] is absolute epoch; the sensing center frequency comes from the recording's
          Therapy snapshot (per hemisphere).
        Both pooled in RAW device units (no scaling, same convention as the decoder).
      * MODELED LSB (fallback — the band has a spectrum but NO native device LSB):
        - Montage survey TD (`montage_td_recordings`, stim-off, all contacts): the timeline's
          ``psd_modeled`` tier. Convert the 250 Hz TD to LSB via the PRIMARY transform route
          (analytics.td_to_lsb = transform DSP x LSB_PER_UV2_TRANSFORM=352.62; PI 2026-06-27,
          superseding the old welch256 x269 path) so survey contacts that the device never produced an
          LSB scalar for still get a calibrated LSB point on the trace. NEVER preferred over native
          LSB; the tier enum stays source="psd_modeled" (downstream native-preferred masking keys on
          it) so the frontend draws it with a distinct hollow marker; the DSP route is in `method`.

        - Patient-triggered snapshot events (`event_psd_recordings`, PSD-ONLY — no TD): the CS-3
          PSD->LSB BRIDGE. These device onboard-FFT snapshots (FFTBinData) have a spectrum but NO time
          domain, so the direct transform cannot run; convert the device-PSD band power to LSB via
          analytics.device_psd_to_lsb (LSB_PER_DEVICE_PSD ~= 73.63 = k=352.62 / the montage TD<->PSD
          ratio 4.79). Same psd_modeled tier + modeled=True flag (never preferred over native, never
          deployable); the DSP route is recorded in `method` as event_psd_bridge_x_k=73.63. Restricted
          to [LSB_VALIDATED_HZ_LO, LSB_DEPLOYABLE_HZ_HI] -- the bridge is only honored where a deployable
          band can sit. Montage/survey products are NOT routed here (they carry TD -> the modeled tier
          above); the bridge is for the PSD-only events that are otherwise LSB-less.

    `sensing_hz_by_channel` maps a raw channel -> its configured sensing center (Hz); the psd_modeled
    tier converts at that center when known, else the montage record's own peak frequency.

    `event_psd_recordings` is a list of PSD-only event blocks already assigned to a canonical channel:
        [{ "channel": canon_ch, "t": epoch_s, "freq": [Hz], "power": [FFTBinData], "center_hz": hz }]
    (center_hz optional; falls back to sensing_hz_by_channel[channel]).

    Returns dict keyed by RAW channel name:
        { channel: { "t":[epoch_s], "y":[lsb], "center_hz":[hz|None],
                     "source":["streaming"|"chronic"|"psd_modeled"],
                     "modeled":[bool], "method":[str|None] } }
    Sentinel/negative/non-finite samples are dropped. Samples are time-sorted; each carries its own
    center_hz so the frontend can color the trace by frequency AND honestly show when sensing moved.
    """
    region_map = region_map or {}
    sensing_hz_by_channel = sensing_hz_by_channel or {}
    out = {}

    def _push(ch, t, y, hz, src, *, modeled=False, method=None):
        d = out.setdefault(ch, {"t": [], "y": [], "center_hz": [], "source": [],
                                "modeled": [], "method": []})
        d["t"].append(float(t)); d["y"].append(float(y))
        d["center_hz"].append(snap_freq(hz)); d["source"].append(src)
        d["modeled"].append(bool(modeled)); d["method"].append(method)

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

    # --- MODELED tier (fallback): montage survey TD -> transform DSP -> td_to_lsb (k=352.62) ---
    # Survey contacts carry a full-spectrum TD but NO native device LSB scalar, so without this they
    # would have no LSB point at all. We convert via the PRIMARY TD->LSB route (the percept-spectral-
    # repro transform x LSB_PER_UV2_TRANSFORM=352.62; PI 2026-06-27) so the timeline can show a
    # calibrated (modeled) LSB for every sensed band, distinctly marked. Only contacts that already
    # have NO native LSB sample get a modeled point per record (native is always preferred): if a
    # contact has any streaming/chronic LSB we still ADD the modeled survey point (different time), but
    # tag it modeled so the frontend renders it hollow — it never overrides a sensed value at its time.
    for r in (montage_td_recordings or []):
        if not isinstance(r, dict):
            continue
        names = list(r.get("ChannelNames", []) or [])
        data = np.asarray(r.get("Data"), dtype=float)
        if data.ndim != 2 or data.shape[0] == 0:
            continue
        fs = float(r.get("SamplingRate") or 250.0) or 250.0
        t0 = _to_epoch(r.get("StartTime"))
        if t0 is None:
            continue
        # montage TD is (n_samples, n_channels); guard either orientation
        if data.shape[0] == len(names) and data.shape[1] != len(names):
            data = data.T
        # device-blessed per-contact peak frequency, when the survey attached its PSD descriptor.
        # `Descriptor.MedtronicPSD` is positionally aligned to ChannelNames (one entry per stream);
        # each entry carries PeakFrequencyInHertz. Falls back to a record-level peak, then None.
        desc = r.get("Descriptor") if isinstance(r.get("Descriptor"), dict) else {}
        med_psd = desc.get("MedtronicPSD") if isinstance(desc.get("MedtronicPSD"), list) else []
        rec_peak = snap_freq(r.get("PeakFrequencyInHertz"))
        for ci, nm in enumerate(names):
            if ci >= data.shape[1]:
                continue
            col = data[:, ci]
            col = col[np.isfinite(col)]
            # transform minimum = one 1 s (round(fs)) rcs-Hann window; td_to_lsb returns NaN below this
            if col.size < int(round(fs * analytics.TRANSFORM_WIN_SECONDS)):
                continue
            # land the modeled sample on the SAME lane key as native LSB: canonicalize the ring/sweep
            # name (e.g. ZERO_AND_THREE_LEFT_RING -> ZERO_THREE_LEFT). _canon_channel-equivalent.
            key = _canon_channel(nm)
            # center: configured sensing band for this contact (preferred, so timeline & deployment
            # agree on WHICH band), else this contact's device peak, else the record peak.
            contact_peak = None
            if ci < len(med_psd) and isinstance(med_psd[ci], dict):
                contact_peak = snap_freq(med_psd[ci].get("PeakFrequencyInHertz"))
            center = (sensing_hz_by_channel.get(key) or sensing_hz_by_channel.get(nm)
                      or sensing_hz_by_channel.get(str(nm)) or contact_peak or rec_peak)
            if center is None or not np.isfinite(center) or float(center) <= 0:
                continue
            # PRIMARY TD->LSB: transform DSP (median over 1 s rcs-Hann/256-pt windows across the whole
            # survey) x k=352.62. The survey is stamped at one StartTime (no PRO centering here), so the
            # whole column is the analysis extent — the direct transform analog of the old whole-column
            # Welch. Range/fft guards live downstream on the deployable threshold, not on this display
            # point (the exploration timeline is not band-restricted; k cancels in r/AUC).
            lsb = analytics.td_to_lsb(col, fs, float(center))
            if lsb is None or not np.isfinite(lsb) or lsb <= 0:
                continue
            # source stays the "psd_modeled" TIER enum (the native-preferred masking at the y-window
            # scaler + the deployment threshold + the frontend all key on it); the DSP ROUTE that
            # produced the value is recorded in `method` (now transform x352.62, was welch256 x269).
            _push(key, t0, lsb, center, "psd_modeled",
                  modeled=True, method=f"td_transform_x_k={analytics.LSB_PER_UV2_TRANSFORM:.2f}")

    # --- MODELED tier (CS-3 PSD->LSB BRIDGE): PSD-ONLY patient-triggered snapshot events ---
    # These events carry a device onboard-FFT spectrum (FFTBinData) but NO time domain, so they cannot
    # use the direct transform. Convert the device-PSD band power to LSB via the bridge constant
    # (device_psd_to_lsb, k ~= 73.63). Same psd_modeled tier + modeled=True (never preferred over native,
    # never deployable). Restricted to [LSB_VALIDATED_HZ_LO, LSB_DEPLOYABLE_HZ_HI]: outside that band a
    # deployable adaptive band cannot sit, and the bridge has no calibrated meaning there, so we drop the
    # point rather than show an LSB the device could never act on. Montage/survey products are NOT here —
    # they carry TD and went through the modeled tier above; this tier is exclusively for the PSD-only
    # events that would otherwise have no LSB at all.
    for ev in (event_psd_recordings or []):
        if not isinstance(ev, dict):
            continue
        key = ev.get("channel")
        t0 = _to_epoch(ev.get("t"))
        freq = ev.get("freq"); power = ev.get("power")
        if key is None or t0 is None or freq is None or power is None:
            continue
        center = ev.get("center_hz") or sensing_hz_by_channel.get(key) \
            or sensing_hz_by_channel.get(str(key))
        if center is None or not np.isfinite(center) or float(center) <= 0:
            continue
        # honor the bridge only inside the deployable band — outside it the conversion is uncalibrated
        if not (analytics.LSB_VALIDATED_HZ_LO <= float(center) <= analytics.LSB_DEPLOYABLE_HZ_HI):
            continue
        # scalar center -> device_psd_to_lsb returns a float (never None/ndarray); NaN if the band power
        # is non-positive (e.g. an all-sub-floor band clamped to 0).
        lsb = analytics.device_psd_to_lsb(freq, power, float(center))
        if not np.isfinite(lsb) or lsb <= 0:
            continue
        _push(key, t0, lsb, center, "psd_modeled",
              modeled=True, method=f"event_psd_bridge_x_k={analytics.LSB_PER_DEVICE_PSD:.2f}")

    # time-sort each channel's pooled samples
    for ch, d in out.items():
        order = np.argsort(d["t"])
        for k_ in ("t", "y", "center_hz", "source", "modeled", "method"):
            d[k_] = [d[k_][i] for i in order]
    return out


def _missing_per_sample(missing, nsamp):
    """Collapse a recording's `Missing` field to a per-sample (n_samples,) 0/1 flag, or None — the
    any-channel-missing rule (FixBreaking/dropped-packet zero-fill spans all channels). Mirrors
    bravo_service._missing_time_vector; kept local so availability has no upward import."""
    if missing is None:
        return None
    m = np.asarray(missing)
    if m.size == 0:
        return None
    if m.ndim == 2:
        axis = 1 if m.shape[0] == nsamp else (0 if m.shape[1] == nsamp else 1)
        m = (m > 0).any(axis=axis)
    return np.asarray(m).ravel()


# Per-PRO LSB selection tiers (in strict precedence order). The frontend keys on these to colour /
# annotate each PRO's biomarker point by how trustworthy its LSB is.
PRO_LSB_TIER_NATIVE = "native"        # device actually sensed this band near the rating (preferred)
PRO_LSB_TIER_TD = "td_transform"      # a TD-bearing recording overlapped the rating -> direct k=352.62
PRO_LSB_TIER_BRIDGE = "psd_bridge"    # PSD-only patient event coincided -> CS-3 bridge (last resort)

# ADC rail for the Percept TD (±, in µV). A 1 s window whose samples touch the rail is saturated /
# clipped — its transform band power is unreliable. Wide bound (the device's full-scale input range);
# real LFP rarely exceeds a few hundred µV, so touching this is a hardware-limit artifact, not signal.
PRO_LSB_SATURATION_UV = 4000.0


def per_pro_lsb(pro_times, native_lsb_series, channel, center_hz, *, band_half_hz=2.5,
                td_recordings=None, event_psd_recordings=None,
                native_tol_s=120.0, extent_s=None, max_missing_frac=0.10,
                saturation_uv=PRO_LSB_SATURATION_UV):
    """One LSB value per PRO for THIS channel/band, chosen by a strict source precedence (CS-4).

    For each PRO timestamp, walk the precedence and stop at the first tier that yields a value:
      (1) NATIVE device LSB  — if `native_lsb_series` (a channel's lsb_series entry, NATIVE samples
          only) has a sensed in-band sample within `native_tol_s` of the rating. The band was actually
          measured; nothing models better than that.
      (2) DIRECT TD->LSB transform (k=352.62) — if ANY TD-bearing recording in `td_recordings`
          (streaming / montage / survey / snapshot — all carry 250 Hz TD) overlaps the rating: cut the
          rating-centered 30 s extent (analytics.transform_centered_window: clip-don't-slide, 1 s-min,
          fail-closed >`max_missing_frac` Missing) and run analytics.td_to_lsb at 50 % overlap. A
          saturated window (samples at the ADC rail) is flagged and skipped.
      (3) PSD->LSB BRIDGE (CS-3) — ONLY if the coincident record is a PSD-only patient-triggered
          snapshot event (`event_psd_recordings`, no TD): analytics.device_psd_to_lsb (k~=73.63).

    Montage/survey TD NEVER uses the bridge — it carries TD and is served by tier 2 (the bridge is for
    PSD-only events alone; montage/survey are the bridge's calibration source). The PSD bridge is honored
    only inside [LSB_VALIDATED_HZ_LO, LSB_DEPLOYABLE_HZ_HI] (same gate as lsb_series' bridge tier).

    Returns a list (PRO order) of dicts:
        {"t": pro_epoch_s, "lsb": float|None, "tier": one of PRO_LSB_TIER_*|None,
         "center_hz": hz, "used_s": float, "saturated": bool, "reason": str}
    A PRO with no source in any tier returns lsb=None, tier=None (honestly unmatched).
    """
    if extent_s is None:
        extent_s = analytics.TRANSFORM_CENTERED_EXTENT_SECONDS
    half = float(band_half_hz)
    lo_hz = float(analytics.LSB_VALIDATED_HZ_LO)
    hi_hz = float(analytics.LSB_DEPLOYABLE_HZ_HI)

    # --- pre-index NATIVE in-band sensed samples for this channel (tier 1) ---
    nat_t = np.empty(0); nat_y = np.empty(0)
    if native_lsb_series is not None:
        y = np.asarray(native_lsb_series.get("y"), dtype=float)
        hz = np.asarray(native_lsb_series.get("center_hz"), dtype=float)
        modeled = native_lsb_series.get("modeled") or []
        is_modeled = (np.array([bool(m) for m in modeled], dtype=bool)
                      if len(modeled) == y.size else np.zeros(y.size, bool))
        t = np.asarray(native_lsb_series.get("t"), dtype=float)
        band = (np.isfinite(y) & np.isfinite(hz) & ~is_modeled
                & (hz >= center_hz - half) & (hz < center_hz + half))
        nat_t = t[band]; nat_y = y[band]

    out = []
    for tp in np.asarray(pro_times, dtype=float):
        rec = {"t": float(tp), "lsb": None, "tier": None, "center_hz": float(center_hz),
               "used_s": 0.0, "saturated": False, "reason": ""}

        # (1) NATIVE
        if nat_t.size:
            d = np.abs(nat_t - tp)
            j = int(np.argmin(d))
            if d[j] <= native_tol_s:
                rec.update(lsb=float(nat_y[j]), tier=PRO_LSB_TIER_NATIVE, reason="device-sensed in band")
                out.append(rec); continue

        # (2) DIRECT TD->LSB — the rating must fall inside a TD recording's real coverage
        matched_td = False
        for r in (td_recordings or []):
            if not isinstance(r, dict):
                continue
            names = list(r.get("ChannelNames") or [])
            ci = next((i for i, n in enumerate(names) if _canon_channel(n) == channel), None)
            if ci is None:
                continue
            data = np.asarray(r.get("Data"), dtype=float)
            if data.ndim != 2:
                continue
            if data.shape[0] == len(names) and data.shape[1] != len(names):
                data = data.T  # -> (n_samples, n_ch)
            fs = float(r.get("SamplingRate") or 250.0) or 250.0
            t0 = _to_epoch(r.get("StartTime"))
            if t0 is None or ci >= data.shape[1]:
                continue
            nsamp = data.shape[0]
            dur_s = nsamp / fs if fs > 0 else 0.0
            if not (t0 <= tp <= t0 + dur_s):
                continue
            col = data[:, ci]
            miss = _missing_per_sample(r.get("Missing"), nsamp)
            slice_uv, used_s = analytics.transform_centered_window(
                col, fs, tp - t0, extent_s=extent_s, missing=miss, max_missing_frac=max_missing_frac)
            if slice_uv is None:
                continue
            # saturation QC: any sample at/over the ADC rail -> clipped window, skip (flag it)
            if np.nanmax(np.abs(slice_uv)) >= saturation_uv:
                rec["saturated"] = True
                rec["reason"] = "TD window saturated (ADC rail)"
                continue
            step_samples = int(round(fs * analytics.TRANSFORM_STEP_SECONDS))
            lsb = analytics.td_to_lsb(slice_uv, fs, float(center_hz), half_hz=half,
                                      step_samples=step_samples)
            if lsb is None or not np.isfinite(lsb) or lsb <= 0:
                continue
            rec.update(lsb=float(lsb), tier=PRO_LSB_TIER_TD, used_s=float(used_s),
                       reason="direct TD->LSB transform (k=%.2f)" % analytics.LSB_PER_UV2_TRANSFORM)
            matched_td = True
            break
        if matched_td:
            out.append(rec); continue

        # (3) PSD->LSB BRIDGE — only a PSD-only patient event, only inside the deployable band
        if lo_hz <= float(center_hz) <= hi_hz:
            best = None
            for ev in (event_psd_recordings or []):
                if not isinstance(ev, dict) or ev.get("channel") != channel:
                    continue
                te = _to_epoch(ev.get("t"))
                if te is None or abs(te - tp) > native_tol_s:
                    continue
                if best is None or abs(te - tp) < abs(best[0] - tp):
                    best = (te, ev)
            if best is not None:
                ev = best[1]
                lsb = analytics.device_psd_to_lsb(ev.get("freq"), ev.get("power"), float(center_hz),
                                                  half_hz=half)
                if lsb is not None and np.isfinite(lsb) and lsb > 0:
                    rec.update(lsb=float(lsb), tier=PRO_LSB_TIER_BRIDGE,
                               reason="PSD-only event bridge (k=%.2f)" % analytics.LSB_PER_DEVICE_PSD)
                    out.append(rec); continue

        rec["reason"] = rec["reason"] or "no source in any tier"
        out.append(rec)
    return out


def per_pro_lsb_overlay(samples_uv, fs, center_offset_s, center_hz, *, band_half_hz=2.5,
                        extent_s=None, missing=None, max_missing_frac=0.10,
                        saturation_uv=PRO_LSB_SATURATION_UV):
    """The 50%-overlap sliding-window LSB trace WITHIN one PRO's rating-centered TD extent (CS-4).

    Where per_pro_lsb returns the single median LSB the device would act on, this returns the full
    per-window series so the timeline can OVERLAY how the band power moved across the ~30 s around the
    rating (and show the spread the median collapses). Same window geometry as the deployed sweep:
    1 s rcs-Hann window, 50 % overlap (step = TRANSFORM_STEP_SECONDS), median is `np.nanmedian` of the
    returned `lsb`. Per-window QC: a window touching the ADC rail is flagged saturated; the >max_missing
    rejection is applied to the whole extent up front (same as per_pro_lsb's tier 2).

    Returns dict:
        {"t_offset_s": [win-start offsets within the extent],
         "lsb": [per-window LSB], "median_lsb": float|None, "used_s": float,
         "n_windows": int, "n_saturated": int, "saturated": bool, "ok": bool, "reason": str}
    `ok=False` (with reason) when the extent is below one window or >max_missing Missing.
    """
    if extent_s is None:
        extent_s = analytics.TRANSFORM_CENTERED_EXTENT_SECONDS
    fs = float(fs)
    half = float(band_half_hz)
    slice_uv, used_s = analytics.transform_centered_window(
        samples_uv, fs, center_offset_s, extent_s=extent_s, missing=missing,
        max_missing_frac=max_missing_frac)
    if slice_uv is None:
        return {"t_offset_s": [], "lsb": [], "median_lsb": None, "used_s": 0.0,
                "n_windows": 0, "n_saturated": 0, "saturated": False, "ok": False,
                "reason": "extent below one window or >max_missing Missing"}
    win = int(round(fs * analytics.TRANSFORM_WIN_SECONDS))
    step = int(round(fs * analytics.TRANSFORM_STEP_SECONDS))
    sl = np.asarray(slice_uv, dtype=float)
    # per-window band power (no aggregation) -> LSB
    pw = analytics.td_transform_band_power(sl, fs, float(center_hz), half_hz=half,
                                           step_samples=step, agg="none")
    pw = np.asarray(pw, dtype=float).ravel()
    lsb = np.where(np.isfinite(pw) & (pw > 0), analytics.LSB_PER_UV2_TRANSFORM * pw, np.nan)
    starts = np.arange(0, sl.size - win + 1, step)
    # per-window saturation: does any sample in the window touch the rail?
    sat = np.zeros(starts.size, dtype=bool)
    for i, s0 in enumerate(starts):
        seg = sl[s0:s0 + win]
        if seg.size and np.nanmax(np.abs(seg)) >= saturation_uv:
            sat[i] = True
    med = float(np.nanmedian(lsb)) if np.isfinite(lsb).any() else None
    return {"t_offset_s": [float(s / fs) for s in starts],
            "lsb": [float(x) for x in lsb],
            "median_lsb": med, "used_s": float(used_s),
            "n_windows": int(starts.size), "n_saturated": int(sat.sum()),
            "saturated": bool(sat.any()), "ok": True,
            "reason": ("ok" if not sat.any() else "%d/%d windows saturated"
                       % (int(sat.sum()), int(starts.size)))}


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

    A third, MODELED layer carries the psd_modeled tier (survey-TD -> transform DSP -> k=352.62) as discrete
    points the frontend draws with a DISTINCT HOLLOW marker — never as a native session block, so a
    calibrated estimate is never read as a sensed LSB. Modeled points are excluded from the streaming
    session blocks and from the chronic line.

    Returns {channel: {"chronic": {"t":[],"y":[]} | None,
                       "sessions": [{"t0","t1","med","lo","hi","center_hz","n"}],
                       "modeled": [{"t","y","center_hz","method"}],
                       "y_lo","y_hi"}}  where y_lo/y_hi are the robust (2-98 pct) magnitude window
    across the NATIVE layers (chronic+streaming) only, so a modeled outlier never rescales the
    sensed trace; the modeled overlay rides the same axis.
    """
    out = {}
    for ch, d in (lsb or {}).items():
        t = np.asarray(d.get("t", []), dtype=float)
        y = np.asarray(d.get("y", []), dtype=float)
        cen = list(d.get("center_hz", []))
        src = list(d.get("source", []))
        meth = list(d.get("method", [None] * int(t.size)))
        if t.size == 0:
            continue
        modeled_mask = np.array([s == "psd_modeled" for s in src], dtype=bool)
        # robust magnitude window across NATIVE (sensed) samples only — the modeled overlay rides this
        # scale but does not set it (a modeled outlier shouldn't rescale the sensed trace).
        native_y = y[(~modeled_mask) & np.isfinite(y)] if y.size else y
        finite = native_y if native_y.size else y[np.isfinite(y)]
        y_lo = float(np.percentile(finite, 2)) if finite.size else 0.0
        y_hi = float(np.percentile(finite, 98)) if finite.size else 1.0

        # modeled tier: discrete hollow-marker points, kept OUT of the native session/chronic layers
        modeled = []
        for i in np.where(modeled_mask)[0]:
            if np.isfinite(y[i]):
                modeled.append({"t": float(t[i]), "y": float(y[i]),
                                "center_hz": snap_freq(cen[i]) if cen[i] is not None else None,
                                "method": meth[i] if i < len(meth) else None})

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

        # --- streaming: one block per session (split on time gaps); NATIVE only (exclude modeled) ---
        sessions = []
        s_idx = np.where(~chronic_mask & ~modeled_mask)[0]
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
        out[ch] = {"chronic": chronic, "sessions": sessions, "modeled": modeled,
                   "y_lo": y_lo, "y_hi": y_hi}
    return out


def present_freq_bands(records):
    """Distinct snapped sensing center frequencies that actually appear on bandpower channels.
    Drives the categorical legend so it matches the lanes that render a trend (not all channels)."""
    bands = set()
    for r in records:
        if r["dtype"] == "bandpower" and r["meta"].get("center_hz") is not None:
            bands.add(r["meta"]["center_hz"])
    return sorted(bands)
