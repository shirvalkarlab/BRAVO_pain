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
import warnings

import numpy as np

from . import analytics

# THE CANONICAL DECODED FORM (Track B). Both spellings on purpose: the container's path root makes
# the package `modules.DecodeCommon`, the host suite's root makes it `DecodeCommon`.
try:
    from modules.DecodeCommon import (build_channel_index as _build_channel_index,
                                      per_pro_lsb_indexed as _per_pro_lsb_indexed)
except ImportError:
    from DecodeCommon import (build_channel_index as _build_channel_index,
                              per_pro_lsb_indexed as _per_pro_lsb_indexed)

#: THE SWITCH BETWEEN THE INDEXED READER AND THE REFERENCE SCAN. `per_pro_lsb` reads from a
#: `ChannelIndex` prepared once per request when this is True, and runs its original per-call
#: scan (`_per_pro_lsb_scan`) when it is False. The scans are kept, not deleted: they are the reference the indexed readers are
#: proven equal to (DecodeCommon/tests), and flipping this in one process is how the equality proof
#: on the live record alternates rounds honestly. If a served number is ever suspected, set this
#: False and the page recomputes the old way with no deployment.
USE_CHANNEL_INDEX = True

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
    """BRAVO StartTime -> Unix epoch seconds (float), or None. Accepts epoch float/int or ISO str.

    A value with no timezone attached -- a naive string or a naive `datetime` -- names a moment
    in Universal Time (UTC), on every machine this code runs on, never the process's own local
    zone. This mirrors `DecodeCommon.representation.to_epoch` exactly; the two were changed
    together (open item 19, `DECISIONS_and_open_items.md`) because a naive value used to be read
    in the server's local zone here and in Universal Time there, which agreed only because the
    container happens to run in Universal Time. No naive start time has ever been seen in the
    live record, so this changes no number the platform has produced.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if v >= 1e9 else None  # reject session-offset / 1970 values
    if isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    if isinstance(value, datetime.datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
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
               event_psd_recordings=None, index=None):
    """REAL band-power (LSB) time series per channel, for inline display on the timeline.

    Same contract, same four sources, same output shape as `_lsb_series_scan`, whose docstring
    is the specification. Pass `index=` (from `channel_index`, built with `chronic_recordings=`
    and `powerdomain_recordings=`) when the caller already has one; without it, an index is built
    here from the two native-tier arguments. With `USE_CHANNEL_INDEX` False and no `index`, the
    reference scan runs instead -- same rule as `per_pro_lsb`.
    """
    if index is None and not USE_CHANNEL_INDEX:
        return _lsb_series_scan(chronic_recordings, powerdomain_recordings, region_map=region_map,
                                montage_td_recordings=montage_td_recordings,
                                sensing_hz_by_channel=sensing_hz_by_channel,
                                event_psd_recordings=event_psd_recordings)
    if index is None:
        index = channel_index(chronic_recordings=chronic_recordings,
                              powerdomain_recordings=powerdomain_recordings)
    region_map = region_map or {}
    sensing_hz_by_channel = sensing_hz_by_channel or {}
    # The native tier: the device's own sensed band power, read from the index exactly as
    # `native_lsb_by_channel` built it -- unconverted, per `DecodeCommon`'s own docstring on why
    # this tier needs no calibration constant. Copied per channel (never the index's own lists,
    # which a reader must not mutate) so this function's own time-sort below can reorder freely.
    out = {}
    for ch, d in index.native_lsb_by_channel.items():
        out[ch] = {"t": list(d["t"]), "y": list(d["y"]), "center_hz": list(d["center_hz"]),
                  "source": list(d["source"]), "modeled": [False] * len(d["t"]),
                  "method": [None] * len(d["t"])}
    _lsb_series_modeled_tiers(out, montage_td_recordings, event_psd_recordings,
                              sensing_hz_by_channel)
    for ch, d in out.items():
        order = np.argsort(d["t"])
        for k_ in ("t", "y", "center_hz", "source", "modeled", "method"):
            d[k_] = [d[k_][i] for i in order]
    return out


def _lsb_series_modeled_tiers(out, montage_td_recordings, event_psd_recordings,
                              sensing_hz_by_channel):
    """The two MODELED tiers of `lsb_series` -- montage survey TD (transform DSP) and PSD-only
    event snapshots (the bridge) -- shared, byte-for-byte, between `lsb_series`'s indexed path
    and `_lsb_series_scan`'s own inline copy of the same logic. Mutates `out` in place, the same
    dict shape `_push` builds in `_lsb_series_scan`. These two tiers stay OUT of the canonical
    decoded form on purpose: each needs a calibrated conversion (`analytics.td_to_lsb` or
    `analytics.device_psd_to_lsb`), and `DecodeCommon`'s own docstring is explicit that a shared
    decode layer must never become a second place a unit conversion can drift.
    """
    def _push(ch, t, y, hz, src, *, modeled=False, method=None):
        d = out.setdefault(ch, {"t": [], "y": [], "center_hz": [], "source": [],
                                "modeled": [], "method": []})
        d["t"].append(float(t)); d["y"].append(float(y))
        d["center_hz"].append(snap_freq(hz)); d["source"].append(src)
        d["modeled"].append(bool(modeled)); d["method"].append(method)

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
        if data.shape[0] == len(names) and data.shape[1] != len(names):
            data = data.T
        desc = r.get("Descriptor") if isinstance(r.get("Descriptor"), dict) else {}
        med_psd = desc.get("MedtronicPSD") if isinstance(desc.get("MedtronicPSD"), list) else []
        rec_peak = snap_freq(r.get("PeakFrequencyInHertz"))
        for ci, nm in enumerate(names):
            if ci >= data.shape[1]:
                continue
            col = data[:, ci]
            col = col[np.isfinite(col)]
            if col.size < int(round(fs * analytics.TRANSFORM_WIN_SECONDS)):
                continue
            key = _canon_channel(nm)
            contact_peak = None
            if ci < len(med_psd) and isinstance(med_psd[ci], dict):
                contact_peak = snap_freq(med_psd[ci].get("PeakFrequencyInHertz"))
            center = (sensing_hz_by_channel.get(key) or sensing_hz_by_channel.get(nm)
                      or sensing_hz_by_channel.get(str(nm)) or contact_peak or rec_peak)
            if center is None or not np.isfinite(center) or float(center) <= 0:
                continue
            lsb = analytics.td_to_lsb(col, fs, float(center))
            if lsb is None or not np.isfinite(lsb) or lsb <= 0:
                continue
            _push(key, t0, lsb, center, "psd_modeled",
                  modeled=True, method=f"td_transform_x_k={analytics.LSB_PER_UV2_TRANSFORM:.2f}")

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
        if not (analytics.LSB_VALIDATED_HZ_LO <= float(center) <= analytics.LSB_DEPLOYABLE_HZ_HI):
            continue
        lsb = analytics.device_psd_to_lsb(freq, power, float(center))
        if not np.isfinite(lsb) or lsb <= 0:
            continue
        _push(key, t0, lsb, center, "psd_modeled",
              modeled=True, method=f"event_psd_bridge_x_k={analytics.LSB_PER_DEVICE_PSD:.2f}")


def _lsb_series_scan(chronic_recordings, powerdomain_recordings, region_map=None,
                     montage_td_recordings=None, sensing_hz_by_channel=None,
                     event_psd_recordings=None):
    """REAL band-power (LSB) time series per channel, for inline display on the timeline.

    THE REFERENCE IMPLEMENTATION -- `lsb_series` above is proven equal to this on the live
    record; this docstring is the specification either path must match.

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


def modeled_lsb_at_center(channel, center_hz, *, td_recordings=None, psd_recordings=None,
                          half_hz=2.5, index=None):
    """DEPLOYMENT-ONLY: modeled device-LSB samples for ONE (channel, band center). Same contract
    as `_modeled_lsb_at_center_scan`, whose docstring is the specification.

    The TD tier (Track D step 1) reads from `channel_index` when `index=` is given or
    `USE_CHANNEL_INDEX` is True -- `td_recordings` is exactly the superset `channel_index` already
    groups by channel for `per_pro_lsb`, so this tier reuses that grouping instead of its own
    column scan. The PSD-only tier stays a direct scan of `psd_recordings` on BOTH paths: its
    record shape (`PSD`/`Frequencies` arrays keyed by `ChannelNames` row) does not match
    `channel_index.psd_by_channel`'s shape (flat per-event blocks the service assembles
    elsewhere), and both live call sites pass `psd_recordings=None` today, so there is no live
    data to prove a translation correct against -- left unchanged rather than guessed at.
    """
    if index is None and not USE_CHANNEL_INDEX:
        return _modeled_lsb_at_center_scan(channel, center_hz, td_recordings=td_recordings,
                                           psd_recordings=psd_recordings, half_hz=half_hz)
    try:
        cz = float(center_hz)
    except (TypeError, ValueError):
        return np.asarray([], dtype=float)
    if not np.isfinite(cz) or cz <= 0:
        return np.asarray([], dtype=float)
    if index is None:
        index = channel_index(td_recordings=td_recordings)
    vals = []
    for trace in index.td(channel)["traces"]:
        fs = trace["fs"]
        if not np.isfinite(fs) or fs <= 0:
            continue
        col = np.asarray(trace["col"], dtype=float)
        col = col[np.isfinite(col)]
        min_n = int(round(fs * analytics.TRANSFORM_WIN_SECONDS))
        if col.size < min_n:
            continue
        lsb = analytics.td_to_lsb(col, fs, cz, half_hz=half_hz)
        if lsb is not None and np.isfinite(lsb) and lsb > 0:
            vals.append(float(lsb))
    if analytics.LSB_VALIDATED_HZ_LO <= cz <= analytics.LSB_DEPLOYABLE_HZ_HI:
        target = _canon_channel(channel)
        for r in (psd_recordings or []):
            if not isinstance(r, dict):
                continue
            names = list(r.get("ChannelNames", []) or [])
            if not names:
                continue
            psd = r.get("PSD") if r.get("PSD") is not None else r.get("Data")
            freqs = r.get("Frequencies")
            if freqs is None:
                freqs = r.get("FrequenciesInHertz")
            if psd is None or freqs is None:
                continue
            psd = np.asarray(psd, dtype=float)
            freqs = np.asarray(freqs, dtype=float)
            if psd.ndim == 1:
                psd = psd[None, :]
            for ci, nm in enumerate(names):
                if ci >= psd.shape[0]:
                    continue
                if _canon_channel(nm) != target:
                    continue
                row = np.asarray(psd[ci], dtype=float)
                if row.shape != freqs.shape:
                    continue
                lsb = analytics.device_psd_to_lsb(freqs, row, cz, half_hz=half_hz)
                if lsb is not None and np.isfinite(lsb) and lsb > 0:
                    vals.append(float(lsb))
    return np.asarray(vals, dtype=float)


def _modeled_lsb_at_center_scan(channel, center_hz, *, td_recordings=None, psd_recordings=None,
                                half_hz=2.5):
    """DEPLOYMENT-ONLY: modeled device-LSB samples for ONE (channel, band center), via the SAME
    primary routes the exploration timeline uses — applied at an ARBITRARY center the deployment ROC
    chose, not only the montage's configured sensing bands.

    THE REFERENCE IMPLEMENTATION -- `modeled_lsb_at_center` above is proven equal to this on the
    live record; this docstring is the specification either path must match.

    Units-consistent replacement for the retired µV²-cut-point fallback (the old TIER-2
    estimate_lsb(cutpoint) path, removed 2026-06-28): instead of pushing a z-scored ROC cut-point
    through a µV²-expecting converter, model the LSB line off the RAW µV TD the ROC was built from, at
    the ROC's own band, then anchor a threshold by RANK (percentile) exactly like the native and
    montage-modeled tiers. Both inputs feed shared primitives exploration already calls — this
    function only CALLS them, so lsb_series and the exploration timeline are untouched.

      * td_recordings  — raw-µV TD-bearing recordings: BrainSense streaming TD + IndefiniteStream AND
        the montage/survey sweeps (all 250 Hz TD), the same superset the exploration timeline pools.
        ONLY columns whose ChannelName
        canonicalizes to `channel` are converted, via the PRIMARY transform route
        analytics.td_to_lsb(col, fs, center_hz) (×LSB_PER_UV2_TRANSFORM = 352.62). Power-domain records
        (SamplingRate ≤ 0, e.g. ChronicBrainSense) and unnamed/extra columns are skipped — they are not
        raw TD. Because the center is the deployment band (not the montage's configured sensing band),
        this yields a modeled point at ANY band the ROC can score, including bands the montage never
        swept (8.8/40/55 Hz).
      * psd_recordings  — PSD-only events (onboard FFT, no TD). The matching channel's spectrum is
        converted with the bridge route analytics.device_psd_to_lsb (×LSB_PER_DEVICE_PSD ≈ 73.63),
        gated to the deployable band like the timeline's bridge tier.

    Returns a 1-D float array of in-band modeled LSB values for `channel` (may be empty). The caller
    reads a threshold off it at the cut-point's percentile — no µV²↔LSB conversion of the cut-point,
    which is the units bug this removes.
    """
    # Honor the deployment ROC's CHOSEN band center exactly — do NOT snap to a device FFT bin. The
    # transform DSP (td_to_lsb) and the bridge (device_psd_to_lsb) integrate band power at any center
    # via the PSD, so a high-gamma ROC winner (e.g. 55 Hz) must be converted at 55 Hz, not clamped to
    # the 26.4 Hz top of the sensing-bin table (snap_freq is for timeline-display bin alignment only).
    try:
        cz = float(center_hz)
    except (TypeError, ValueError):
        return np.asarray([], dtype=float)
    if not np.isfinite(cz) or cz <= 0:
        return np.asarray([], dtype=float)
    target = _canon_channel(channel)
    vals = []

    # --- TD tier: transform route (×352.62) at the deployment center, off montage/survey TD ---
    # Convert ONLY columns whose ChannelName canonicalizes to `target`, mirroring the reference
    # lsb_series montage tier (iterate over names; ignore extra/unnamed columns). An unnamed column is
    # NEVER converted as `target` — that would let a malformed packet (Data columns > ChannelNames) or a
    # foreign/power-domain column leak into the percentile-anchored DEPLOYABLE threshold. fs is sanity-
    # guarded so a power-domain record (SamplingRate=-1, e.g. ChronicBrainSense) can never reach td_to_lsb.
    for r in (td_recordings or []):
        if not isinstance(r, dict):
            continue
        names = list(r.get("ChannelNames", []) or [])
        if not names:
            continue                         # no channel labels -> can't scope to `target`; skip
        data = r.get("Data")
        if data is None:
            continue
        data = np.asarray(data, dtype=float)
        if data.ndim == 1:
            data = data[:, None]
        if data.ndim != 2 or data.shape[0] == 0:
            continue
        fs = float(r.get("SamplingRate") or r.get("SampleRateInHz") or 250.0) or 250.0
        if not np.isfinite(fs) or fs <= 0:
            continue                         # power-domain / malformed cadence (e.g. -1) -> not raw TD
        # TD is (n_samples, n_channels); guard either orientation against the ChannelNames length.
        if data.shape[0] == len(names) and data.shape[1] != len(names):
            data = data.T
        min_n = int(round(fs * analytics.TRANSFORM_WIN_SECONDS))
        for ci, nm in enumerate(names):
            if ci >= data.shape[1]:
                continue                     # more names than columns (malformed packet) -> ignore
            if _canon_channel(nm) != target:
                continue                     # only the requested channel's column is converted
            col = data[:, ci]
            col = col[np.isfinite(col)]
            if col.size < min_n:
                continue
            lsb = analytics.td_to_lsb(col, fs, float(cz), half_hz=half_hz)
            if lsb is not None and np.isfinite(lsb) and lsb > 0:
                vals.append(float(lsb))

    # --- PSD-only tier: bridge route (≈73.63), deployable-band gated, for events with no TD ---
    if analytics.LSB_VALIDATED_HZ_LO <= float(cz) <= analytics.LSB_DEPLOYABLE_HZ_HI:
        for r in (psd_recordings or []):
            if not isinstance(r, dict):
                continue
            names = list(r.get("ChannelNames", []) or [])
            if not names:
                continue                     # no labels -> can't scope to `target`; skip
            psd = r.get("PSD") if r.get("PSD") is not None else r.get("Data")
            freqs = r.get("Frequencies")
            if freqs is None:
                freqs = r.get("FrequenciesInHertz")
            if psd is None or freqs is None:
                continue
            psd = np.asarray(psd, dtype=float)
            freqs = np.asarray(freqs, dtype=float)
            if psd.ndim == 1:
                psd = psd[None, :]
            for ci, nm in enumerate(names):
                if ci >= psd.shape[0]:
                    continue
                if _canon_channel(nm) != target:
                    continue                 # only the requested channel's spectrum is converted
                row = np.asarray(psd[ci], dtype=float)
                if row.shape != freqs.shape:
                    continue
                lsb = analytics.device_psd_to_lsb(freqs, row, float(cz), half_hz=half_hz)
                if lsb is not None and np.isfinite(lsb) and lsb > 0:
                    vals.append(float(lsb))

    return np.asarray(vals, dtype=float)


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

#: How much signal one of the device's own FFT snapshots covers. From `DEVICE_percept_rc.md`: the
#: patient-event snapshot is "30 s, beginning 30 s after the button press". The calibrated grid's
#: length-of-signal axis counts snapshots by this (decision 121): a row of N seconds needs
#: ceil(N / 30) of them.
PSD_SNAPSHOT_SECONDS = 30.0


def _per_pro_lsb_scan(pro_times, native_lsb_series, channel, center_hz, *, band_half_hz=2.5,
                td_recordings=None, event_psd_recordings=None,
                native_tol_s=120.0, extent_s=None, max_missing_frac=0.10,
                saturation_uv=PRO_LSB_SATURATION_UV):
    """REFERENCE IMPLEMENTATION, kept for the equality check; `per_pro_lsb` is the entry point.

    One LSB value per PRO for THIS channel/band, chosen by a strict source precedence (CS-4).

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
    # Canonicalize the target channel ONCE so all three tiers match on the same key: tier 2 already
    # canonicalizes each recording's raw ring/sweep name (_canon_channel below), so the native series,
    # the TD recordings, and the event records are all compared in canonical form regardless of whether
    # the caller passed a raw ring name or a canonical one.
    channel = _canon_channel(channel)

    # --- pre-index NATIVE in-band sensed samples for this channel (tier 1) ---
    nat_t = np.empty(0); nat_y = np.empty(0)
    if native_lsb_series is not None:
        y = np.asarray(native_lsb_series.get("y"), dtype=float)
        hz = np.asarray(native_lsb_series.get("center_hz"), dtype=float)
        modeled = native_lsb_series.get("modeled") or []
        # FAIL CLOSED: the native tier must NEVER promote a CS-1/CS-3 modeled ESTIMATE to a measured
        # value. If the `modeled` array is missing or misaligned we cannot certify any point native, so
        # treat every point as modeled (is_modeled=True) and let the lower tiers serve the PRO instead.
        is_modeled = (np.array([bool(m) for m in modeled], dtype=bool)
                      if len(modeled) == y.size else np.ones(y.size, bool))
        t = np.asarray(native_lsb_series.get("t"), dtype=float)
        # band edges INCLUSIVE on both sides, matching the DSP band-power mask (a native sample exactly
        # at center+half is in-band on the modeling side, so it must be in-band for selection too).
        band = (np.isfinite(y) & np.isfinite(hz) & ~is_modeled
                & (hz >= center_hz - half) & (hz <= center_hz + half))
        nat_t = t[band]; nat_y = y[band]

    # --- prep TD recordings ONCE for tier 2 (PERF): a recording's Data->float column, t0, dur, fs, and
    # missing vector are PRO-independent, so materialize them a single time here instead of re-converting
    # per PRO. Keep ONLY recordings that carry this channel; sort by t0 so the PRO scan can stop early.
    td_prepped = []   # [{t0, t1, fs, col, miss, step}]
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
        td_prepped.append({
            "t0": t0, "t1": t0 + dur_s, "fs": fs,
            "col": data[:, ci], "miss": _missing_per_sample(r.get("Missing"), nsamp),
            "step": int(round(fs * analytics.TRANSFORM_STEP_SECONDS))})
    td_prepped.sort(key=lambda d: d["t0"])
    td_t0 = np.array([d["t0"] for d in td_prepped], dtype=float)   # sorted; for searchsorted

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

        # (2) DIRECT TD->LSB — the rating must fall inside a TD recording's real coverage. Only
        # recordings with t0 <= tp can cover the PRO; searchsorted skips the rest (sorted by t0).
        matched_td = False
        hi = int(np.searchsorted(td_t0, tp, side="right")) if td_t0.size else 0
        for pr in td_prepped[:hi]:
            if not (pr["t0"] <= tp <= pr["t1"]):
                continue
            fs = pr["fs"]
            slice_uv, used_s = analytics.transform_centered_window(
                pr["col"], fs, tp - pr["t0"], extent_s=extent_s, missing=pr["miss"],
                max_missing_frac=max_missing_frac)
            if slice_uv is None:
                continue
            # saturation QC: any sample at/over the ADC rail -> clipped window, skip (flag it)
            if np.nanmax(np.abs(slice_uv)) >= saturation_uv:
                rec["saturated"] = True
                rec["reason"] = "TD window saturated (ADC rail)"
                continue
            lsb = analytics.td_to_lsb(slice_uv, fs, float(center_hz), half_hz=half,
                                      step_samples=pr["step"])
            if lsb is None or not np.isfinite(lsb) or lsb <= 0:
                continue
            # A clean conversion here OVERRIDES any saturated flag a PRIOR overlapping recording's
            # railed window may have set — the PRO is served by THIS recording, so its trust label
            # must reflect THIS recording, not a discarded earlier one.
            rec.update(lsb=float(lsb), tier=PRO_LSB_TIER_TD, used_s=float(used_s), saturated=False,
                       reason="direct TD->LSB transform (k=%.2f)" % analytics.LSB_PER_UV2_TRANSFORM)
            matched_td = True
            break
        if matched_td:
            out.append(rec); continue

        # (3) PSD->LSB BRIDGE — only a PSD-only patient event, only inside the deployable band.
        # NOTE: if tier 2 matched a TD recording but every overlapping window was SATURATED (matched_td
        # stayed False, rec["saturated"]=True), we DO fall through to the bridge here. A clean coincident
        # device-FFT reading is a better estimate than a clipped TD window (whose band power is
        # harmonic-contaminated and was discarded). The saturated flag stays set, so the frontend can
        # still annotate that the rating's TD was clipped even though a bridge value was used.
        if lo_hz <= float(center_hz) <= hi_hz:
            best = None
            for ev in (event_psd_recordings or []):
                if not isinstance(ev, dict) or _canon_channel(ev.get("channel")) != channel:
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


# `_per_pro_lsb_spectrum_scan` and `per_pro_lsb_spectrum` -- the SAME rule as `_per_pro_lsb_scan` /
# `per_pro_lsb` evaluated at MANY band centres for one pain rating, returning one list of LSB
# band-power values per rating -- were DELETED on 2026-09-10 at the PI's direction (decision 115).
# Nothing on any page had read them since 2026-06-28, when matching against the 3 s tile cache
# (`live_lsb_spectrum_match`) replaced the live per-rating computation; their only callers were
# tests. Measured before deletion on RCS08: for every rating served from the voltage trace or the
# PSD bridge, the many-centre list's entry at the contact's own centre equalled the timeline
# circle bit for bit, 240 of 240 -- so nothing that is drawn depended on them.


def channel_index(td_recordings=None, event_psd_recordings=None, *,
                  chronic_recordings=None, powerdomain_recordings=None):
    """The canonical decoded form for one request's recordings, built once and read many times.

    Group every voltage trace and every device-spectrum record by canonical channel name ONCE,
    with the band-power recipe's own step, so no reader canonicalises a name or parses a start
    time again. On the live record the per-report scan this replaces made 72,332,380 channel-name
    canonicalisations in one page request (99.87 percent of all of them); through the index the
    same work is one per (recording, channel).

    `chronic_recordings`/`powerdomain_recordings` are optional (Track D step 1): when given, the
    same one call also groups the device's own sensed band-power products (Power-Domain streaming
    + Chronic Timeline), unconverted, for `lsb_series` to read instead of its own inline scan --
    every stream now goes through this one decode step, each handled per its own kind, with the
    native tier passed through as-is because it is already in the device units the platform cares
    about (no calibration constant applies to it the way one does to the montage-TD and
    event-PSD MODELED tiers, which stay reader-side; see `native_lsb_by_channel`'s own docstring).
    """
    return _build_channel_index(td_recordings, event_psd_recordings,
                                step_seconds=analytics.TRANSFORM_STEP_SECONDS,
                                chronic_recordings=chronic_recordings,
                                powerdomain_recordings=powerdomain_recordings)


def per_pro_lsb(pro_times, native_lsb_series, channel, center_hz, *, band_half_hz=2.5,
                td_recordings=None, event_psd_recordings=None,
                native_tol_s=120.0, extent_s=None, max_missing_frac=0.10,
                saturation_uv=PRO_LSB_SATURATION_UV, index=None):
    """One LSB value per PRO for THIS channel/band, chosen by a strict source precedence (CS-4).

    Same contract, same rule, same record fields as `_per_pro_lsb_scan`, whose docstring is the
    specification. Pass `index=` (from `channel_index`) when the caller serves several channels
    from the same recordings, so the form is built once rather than once per channel; without
    it the form is built here from `td_recordings` and `event_psd_recordings`. With
    `USE_CHANNEL_INDEX` False and no `index`, the reference scan runs instead.
    """
    if index is None and not USE_CHANNEL_INDEX:
        return _per_pro_lsb_scan(pro_times, native_lsb_series, channel, center_hz,
                                 band_half_hz=band_half_hz, td_recordings=td_recordings,
                                 event_psd_recordings=event_psd_recordings,
                                 native_tol_s=native_tol_s, extent_s=extent_s,
                                 max_missing_frac=max_missing_frac, saturation_uv=saturation_uv)
    if index is None:
        index = channel_index(td_recordings, event_psd_recordings)
    return _per_pro_lsb_indexed(pro_times, native_lsb_series, channel, center_hz,
                                index=index, analytics=analytics, band_half_hz=band_half_hz,
                                native_tol_s=native_tol_s, extent_s=extent_s,
                                max_missing_frac=max_missing_frac, saturation_uv=saturation_uv,
                                tier_native=PRO_LSB_TIER_NATIVE, tier_td=PRO_LSB_TIER_TD,
                                tier_bridge=PRO_LSB_TIER_BRIDGE)


# Map a TD recording's `product` key (TYPE_MAP, e.g. "streaming_td"/"indefinite"/"montage_td") to the
# human source-subtype label the binarization-hover breakdown wants. PSD events carry their own
# `source` string already. Kept here so the cache tags each window's provenance once, at build time.
TD_PRODUCT_SOURCE_LABEL = {
    "streaming_td": "BrainSense streaming",
    "indefinite":   "Indefinite stream",
    "montage_td":   "Montage",
}


def raw_lsb_spectrum_cache(channel, centers_hz, *, band_half_hz=2.5,
                           td_recordings=None, event_psd_recordings=None,
                           montage_psd_recordings=None,
                           window_s=None, max_missing_frac=0.10,
                           saturation_uv=PRO_LSB_SATURATION_UV, index=None):
    """Match-AGNOSTIC raw LSB spectrum cache for ONE channel — the decoupled source of truth.

    `index=` (Track B step 4): a `ChannelIndex` from `channel_index`, whose prepared traces replace
    the per-channel re-resolution of the column and re-conversion of every recording's samples to
    float. The traces are walked in the recording list's own order, so the tile arrays come out
    in the same order as without the index. Without `index`, the recordings are prepared here.

    Tiles the ENTIRE recording history into fixed `window_s` (default RAW_LSB_WINDOW_SECONDS = 3 s)
    NON-OVERLAPPING windows and computes the full 0–100 Hz LSB vector for every window, INDEPENDENT of
    any pain rating / PRO. Matching (which window or windows serve which rating, with the median-over-
    extent aggregation) is performed LIVE downstream — NOT baked in here. Because nothing about a PRO
    set enters this function, the cache key is purely (channel, recordings, centers): the SAME cache
    serves every metric / strategy / match policy, and no LSB vector is pre-assigned to any rating.

    Two window families, kept SEPARATE by source so a downstream matcher can prefer TD over PSD inside
    a match window and so the no-reuse-across-PROs rule can be applied per individual vector:

      * TD-derived (tier td_transform, k=LSB_PER_UV2_TRANSFORM=352.62): each TD recording is cut into
        consecutive `window_s` tiles indexed by WALL-CLOCK SAMPLE position (so a tile's timestamp is
        correct even when the trace has dropped/NaN samples — unlike the finite-sample-space window
        axis of td_transform_band_power(agg="none")). Within each tile the VALIDATED transform runs at
        its native 1 s rcs-Hann / 256-FFT, 50 % overlap, median across the (~5 for a 3 s tile) internal
        sub-windows, × 352.62. A tile with < 1 s finite signal, or more than `max_missing_frac` non-
        finite samples, or any sample at the ADC rail (≥ saturation_uv), emits an all-NaN row flagged
        (`saturated` / insufficient) rather than a misleading value.

      * PSD-derived (tier psd_bridge, k=LSB_PER_DEVICE_PSD≈73.63): each PSD-only event is ONE window at
        its own onboard-FFT timestamp, device_psd_band_power over all centers × 73.63. Per-band
        `calibrated` is True only inside [LSB_VALIDATED_HZ_LO, LSB_DEPLOYABLE_HZ_HI]; outside is
        exploratory (computed and flagged), the bridge contract the per-rating readers use.

    Parameters mirror per_pro_lsb (same recording dict schema, same constants) MINUS pro_times
    and extent_s — there is no rating and no extent at cache-build time.

    Returns a dict (zero-length axes, never None, when a family is empty so the [W × C] shape holds):
        {"channel": canon, "centers_hz": [C floats], "window_s": float, "band_half_hz": float,
         "td":  {"t": [Wt window-CENTER epoch_s], "lsb": [[C] × Wt], "saturated": [Wt bool],
                 "source": [Wt label], "n_finite_s": [Wt float], "ok": [Wt bool]},
         "psd": {"t": [Wp epoch_s], "lsb": [[C] × Wp], "calibrated": [[C bool] × Wp],
                 "source": [Wp label]},
         "n_td_windows": Wt, "n_psd_windows": Wp}
    """
    if window_s is None:
        window_s = analytics.RAW_LSB_WINDOW_SECONDS
    window_s = float(window_s)
    half = float(band_half_hz)
    lo_hz = float(analytics.LSB_VALIDATED_HZ_LO)
    hi_hz = float(analytics.LSB_DEPLOYABLE_HZ_HI)
    channel = _canon_channel(channel)
    centers = np.atleast_1d(np.asarray(centers_hz, dtype=float))
    nC = centers.size
    cal_band = (centers >= lo_hz - 1e-9) & (centers <= hi_hz + 1e-9)

    td_out = {"t": [], "lsb": [], "saturated": [], "source": [], "n_finite_s": [], "ok": []}
    psd_out = {"t": [], "lsb": [], "calibrated": [], "source": []}

    # ---- TD-derived tiles -------------------------------------------------------------------------
    def _prepared_traces():
        """(col, miss, fs, t0, product) per recording carrying this channel, in list order."""
        if index is not None:
            for pr in sorted(index.td(channel)["traces"], key=lambda d: d["seq"]):
                if pr["fs"] <= 0:
                    continue
                yield pr["col"], pr["miss"], pr["fs"], pr["t0"], pr.get("product")
            return
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
                data = data.T
            fs = float(r.get("SamplingRate") or 250.0) or 250.0
            t0 = _to_epoch(r.get("StartTime"))
            if t0 is None or ci >= data.shape[1] or fs <= 0:
                continue
            col = data[:, ci]
            yield col, _missing_per_sample(r.get("Missing"), col.shape[0]), fs, t0, r.get("product")

    for col, miss, fs, t0, product in _prepared_traces():
        nsamp = col.shape[0]
        src = TD_PRODUCT_SOURCE_LABEL.get(product, product or "time-domain")
        win_tile = int(round(fs * window_s))
        step_sub = int(round(fs * analytics.TRANSFORM_STEP_SECONDS))   # 50% overlap sub-window hop
        min_finite = int(round(fs * analytics.TRANSFORM_WIN_SECONDS))  # ≥1 sub-window (1 s) to score
        if win_tile <= 0:
            continue
        # Non-overlapping tiles by RAW sample index. A trailing partial tile is kept only if it can
        # still hold ≥1 transform sub-window; shorter remainders are dropped (no valid LSB).
        for start in range(0, nsamp, win_tile):
            end = min(start + win_tile, nsamp)
            seg = col[start:end]
            seg_miss = miss[start:end] if miss is not None else None
            fin = np.isfinite(seg)
            n_fin = int(fin.sum())
            t_center = t0 + ((start + end) / 2.0) / fs
            # Default: a NaN row we will overwrite on success. Keeps Wt aligned with the tile grid.
            row = [None] * nC
            saturated = False
            ok = False
            if n_fin >= min_finite:
                miss_frac = (float(np.mean(seg_miss)) if seg_miss is not None and seg_miss.size
                             else 1.0 - n_fin / max(seg.size, 1))
                if np.nanmax(np.abs(seg)) >= saturation_uv:
                    saturated = True
                elif miss_frac <= max_missing_frac:
                    bp = np.atleast_1d(analytics.td_transform_band_power(
                        seg, fs, centers, half_hz=half, step_samples=step_sub, agg="median"))
                    lsb = np.where(np.isfinite(bp) & (bp > 0),
                                   analytics.LSB_PER_UV2_TRANSFORM * bp, np.nan)
                    row = [float(v) if np.isfinite(v) else None for v in lsb]
                    ok = any(v is not None for v in row)
            td_out["t"].append(float(t_center))
            td_out["lsb"].append(row)
            td_out["saturated"].append(bool(saturated))
            td_out["source"].append(src)
            td_out["n_finite_s"].append(round(n_fin / fs, 3))
            td_out["ok"].append(bool(ok))

    # ---- PSD-derived windows (one per event) ------------------------------------------------------
    for ev in (event_psd_recordings or []):
        if not isinstance(ev, dict) or _canon_channel(ev.get("channel")) != channel:
            continue
        te = _to_epoch(ev.get("t"))
        if te is None:
            continue
        bp = np.atleast_1d(analytics.device_psd_band_power(
            ev.get("freq"), ev.get("power"), centers, half_hz=half))
        lsb = np.where(np.isfinite(bp) & (bp > 0), analytics.LSB_PER_DEVICE_PSD * bp, np.nan)
        psd_out["t"].append(float(te))
        psd_out["lsb"].append([float(v) if np.isfinite(v) else None for v in lsb])
        psd_out["calibrated"].append([bool(np.isfinite(v) and cal_band[i]) for i, v in enumerate(lsb)])
        psd_out["source"].append(str(ev.get("source") or "PSD event"))

    # ---- Montage/survey device-PSD windows (one per MedtronicPSD snapshot) ------------------------
    # Same device-onboard-FFT unit and bridge constant (k=LSB_PER_DEVICE_PSD≈73.63) as the patient-
    # event PSD above — validated paired same-recording vs the TD transform (ratio ≈0.99 in 8–30 Hz).
    # Folded into the SAME psd family so a montage whose TD tile fails the quality gate still emits a
    # bridge LSB window. Kept here (not merged into event_psd_recordings) only so the caller can pass
    # the two sources independently; cache-side they are identical schema {channel, t, freq, power}.
    for ev in (montage_psd_recordings or []):
        if not isinstance(ev, dict) or _canon_channel(ev.get("channel")) != channel:
            continue
        te = _to_epoch(ev.get("t"))
        if te is None:
            continue
        bp = np.atleast_1d(analytics.device_psd_band_power(
            ev.get("freq"), ev.get("power"), centers, half_hz=half))
        lsb = np.where(np.isfinite(bp) & (bp > 0), analytics.LSB_PER_DEVICE_PSD * bp, np.nan)
        psd_out["t"].append(float(te))
        psd_out["lsb"].append([float(v) if np.isfinite(v) else None for v in lsb])
        psd_out["calibrated"].append([bool(np.isfinite(v) and cal_band[i]) for i, v in enumerate(lsb)])
        psd_out["source"].append(str(ev.get("source") or "Montage PSD"))

    # time-sort each family (tiles are already roughly ordered, but recordings may interleave)
    def _sort_family(fam, keys):
        if not fam["t"]:
            return
        order = np.argsort(np.asarray(fam["t"], dtype=float), kind="stable")
        for k in keys:
            fam[k] = [fam[k][i] for i in order]
    _sort_family(td_out, ["t", "lsb", "saturated", "source", "n_finite_s", "ok"])
    _sort_family(psd_out, ["t", "lsb", "calibrated", "source"])

    return {"channel": channel, "centers_hz": [float(c) for c in centers],
            "window_s": window_s, "band_half_hz": half,
            "td": td_out, "psd": psd_out,
            "n_td_windows": len(td_out["t"]), "n_psd_windows": len(psd_out["t"])}


#: Key under which a window family's converted float matrix is parked inside the family dict itself
#: (see `_lsb_rows_to_mat`). Private to this module; nothing reads the cache by key set, and the
#: cache never leaves the server, so an extra private key is invisible to every consumer.
_LSB_MAT_MEMO_KEY = "_lsb_mat_memo"


def _lsb_family_mat(family, nC):
    """The float [W x C] matrix for one window family of a raw cache, converted AT MOST ONCE.

    The conversion depends only on the cache, never on the match settings, but the band-by-length
    sweep calls the matcher TEN times per sensing contact pair with the same cache, so converting
    every time was the single largest remaining cost (measured: 1.19 s of 1.53 s per pair). The
    matrix is therefore parked back inside the family dict.

    The memo holds a REFERENCE to the exact row list it was built from and is only accepted when
    that identical object comes back (`is`, not equality), so replacing the list invalidates the
    memo and holding the reference stops the row list's identity from ever being recycled under it.
    Rows are never edited in place after `raw_lsb_spectrum_cache` returns; the matrix is marked
    non-writeable so an accidental attempt to edit it fails loudly rather than silently corrupting
    a cache other panels share.
    """
    rows = family.get("lsb")
    if rows is None:
        rows = []
    # `family.get("lsb") or []` was what stood here, and it cannot stay: a family restored from the
    # shared tile-cache file holds its spectra as one float array, and asking a two-dimensional
    # array whether it is truthy raises rather than answering. Taking the value and replacing only
    # a missing one keeps every other case identical, and has the incidental benefit that an empty
    # family now hits its own memo instead of building a fresh empty list on every call.
    memo = family.get(_LSB_MAT_MEMO_KEY)
    if memo is not None and memo[0] is rows and memo[1] == nC:
        return memo[2]
    mat = _lsb_rows_to_mat(rows, nC)
    mat.flags.writeable = False
    try:
        family[_LSB_MAT_MEMO_KEY] = (rows, nC, mat)
    except Exception:                                   # a read-only mapping: convert every time
        pass
    return mat


def _lsb_rows_to_mat(rows, nC):
    """[W][C] list-of-lists-with-None -> float [W x C] with NaN; empty -> (0, nC).

    FAST PATH: `raw_lsb_spectrum_cache` always emits each window as a list of exactly nC entries
    holding a float or None, and numpy coerces None to NaN under a float dtype, so a whole window
    family converts in ONE C-level call instead of W x C Python assignments. Anything ragged, short
    or None-valued falls back to the explicit element-by-element fill, which is what the
    pre-vectorised code did unconditionally, so the result is identical either way.

    ALREADY A MATRIX: a window family restored from the shared tile-cache file
    (`bravo_service._raw_lsb_unpack`) holds its per-window spectra as one float array rather than
    as a list of lists, because turning 29 million numbers back into Python floats on every worker
    would cost most of what the file saves. Such an array is exactly what this function builds from
    the equivalent list of lists — the two are compared value by value in
    tests/test_shared_raw_lsb_cache.py — so it is handed straight back. A width that does not match
    the band-centre count is padded or trimmed the same way the element-by-element path would.
    """
    if isinstance(rows, np.ndarray):
        m = np.asarray(rows, dtype=float)
        if m.ndim == 1:
            m = m.reshape((0, nC)) if m.size == 0 else m.reshape((1, m.size))
        if m.ndim != 2:
            return np.empty((0, nC), dtype=float)
        if m.shape[1] == nC:
            return m
        out = np.full((m.shape[0], nC), np.nan, dtype=float)
        w = min(nC, m.shape[1])
        out[:, :w] = m[:, :w]
        return out
    if not rows:
        return np.empty((0, nC), dtype=float)
    if all(type(r) is list and len(r) == nC for r in rows):
        try:
            return np.asarray(rows, dtype=float)
        except (TypeError, ValueError):
            pass
    m = np.full((len(rows), nC), np.nan, dtype=float)
    for i, row in enumerate(rows):
        if row is None:
            continue
        for j, v in enumerate(row[:nC]):
            if v is not None:
                m[i, j] = v
    return m


def _pad_owned_windows(owners, nP):
    """STRICT match: per-window owner rating index (-1 = unowned) -> ONE padded index matrix.

    Returns (idx_pad, counts). `idx_pad` is (nP, max_count) int64 with -1 in every padding slot;
    row p lists the ORIGINAL window indices owned by rating p in ASCENDING WINDOW ORDER -- exactly
    the array `np.where(owners == p)[0]` returned for that rating one at a time. `counts[p]` is how
    many of row p's entries are real.
    """
    counts = np.zeros(nP, dtype=np.int64)
    empty = np.empty((nP, 0), dtype=np.int64)
    if nP == 0 or owners.size == 0:
        return empty, counts
    keep = np.where(owners >= 0)[0]                     # ascending original window index
    if keep.size == 0:
        return empty, counts
    own = owners[keep]
    counts = np.bincount(own, minlength=nP).astype(np.int64)
    srt = np.argsort(own, kind="stable")                # group by owner, keep ascending within group
    flat = keep[srt]
    rows = np.repeat(np.arange(nP, dtype=np.int64), counts)
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    cols = np.arange(flat.size, dtype=np.int64) - np.repeat(starts, counts)
    idx_pad = np.full((nP, int(counts.max())), -1, dtype=np.int64)
    idx_pad[rows, cols] = flat
    return idx_pad, counts


def _pad_windows_in_extent(win_t, valid_mask, pro, tol, nP, direction="nearest"):
    """REUSE match: every eligible window within +/-tol of each rating -> ONE padded index matrix.

    Identical searchsorted-bounds logic to the per-rating list-of-arrays version it replaces
    (O(W log W + total matches), never the P x W outer product) -- it writes each rating's
    contiguous slice straight into a padded matrix instead of into its own array. Row p lists the
    ORIGINAL window indices in ASCENDING WINDOW TIME, which is the order the slice `vi_sorted[a:b]`
    carried, so the stable tie-breaking in the nearest-N cap below sees the same ordering.

    `direction="prior"` restricts eligibility to windows AT OR BEFORE the rating (the
    forecasting-safe direction: every window used to answer a rating already existed when that
    rating was filed) by narrowing the upper bound from `pro + tol` to `pro`. Everything else about
    the eligibility test (the lower bound, the +/-tol radius itself) is unchanged.
    """
    counts = np.zeros(nP, dtype=np.int64)
    empty = np.empty((nP, 0), dtype=np.int64)
    if nP == 0 or win_t.size == 0:
        return empty, counts
    vi = np.where(valid_mask)[0]                        # original indices that are valid
    if vi.size == 0:
        return empty, counts
    wt = win_t[vi]
    wo = np.argsort(wt, kind="stable")
    wt_sorted = wt[wo]
    vi_sorted = vi[wo]
    hi_bound = pro if direction == "prior" else pro + tol
    lo_idx = np.searchsorted(wt_sorted, pro - tol, side="left")
    hi_idx = np.searchsorted(wt_sorted, hi_bound, side="right")
    counts = np.maximum(hi_idx - lo_idx, 0).astype(np.int64)
    total = int(counts.sum())
    if total == 0:
        return empty, counts
    rows = np.repeat(np.arange(nP, dtype=np.int64), counts)
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    cols = np.arange(total, dtype=np.int64) - np.repeat(starts, counts)
    idx_pad = np.full((nP, int(counts.max())), -1, dtype=np.int64)
    idx_pad[rows, cols] = vi_sorted[np.repeat(lo_idx, counts) + cols]
    return idx_pad, counts


def _cap_nearest_windows(idx_pad, win_t, pro, cap):
    """Keep only the `cap` windows closest in time to each rating, for all ratings at once.

    Reproduces the old per-rating branch exactly. That branch, for a rating owning MORE than `cap`
    windows, did `keep = np.argsort(|win_t[sel] - pro_t|, kind="stable")[:cap]` then
    `sel = sel[np.sort(keep)]` so the surviving windows stayed in their original order for a stable
    median. Here the same STABLE argsort runs along axis 1 for every rating simultaneously. Padding
    slots are handed an INFINITE distance so they always sort last, which means a row holding <=cap
    real windows keeps every one of them and merely carries padding forward -- the identical set the
    old code left untouched when it skipped the branch.
    """
    if idx_pad.shape[1] <= cap:
        return idx_pad
    safe = np.maximum(idx_pad, 0)
    dist = np.where(idx_pad >= 0, np.abs(win_t[safe] - pro[:, None]), np.inf)
    rank = np.argsort(dist, axis=1, kind="stable")[:, :cap]
    rank.sort(axis=1)                                   # back to ascending row position
    return np.take_along_axis(idx_pad, rank, axis=1)


def _padded_nanmedian(mat, idx_pad):
    """Per-rating nan-median over each rating's selected windows as ONE numpy reduction.

    `idx_pad` is (nR, K) with -1 padding. The gather writes NaN into every padding slot, so
    `np.nanmedian(..., axis=1)` over the resulting (nR, K, nC) block equals the old per-rating
    `np.nanmedian(mat[sel], axis=0)` row by row: NaN skips padding exactly as the shorter selection
    simply had nothing there. A row that is entirely NaN yields NaN and a RuntimeWarning, which the
    old per-rating call did too, so the warning is silenced instead of being left to flood the log.
    """
    nR, K = idx_pad.shape
    nC = mat.shape[1]
    if nR == 0 or K == 0 or mat.shape[0] == 0:
        return np.full((nR, nC), np.nan, dtype=float)
    safe = np.maximum(idx_pad, 0)
    block = np.where((idx_pad >= 0)[:, :, None], mat[safe], np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(block, axis=1)


def _lsb_none_lists(med):
    """(nR, nC) float -> (list-of-lists with None where non-finite, list-of-lists of finite flags).

    Replaces the per-rating per-band comprehensions `[float(v) if np.isfinite(v) else None ...]` and
    `[bool(np.isfinite(v)) ...]`. `astype(object)` yields real Python floats, so the emitted values
    are the same objects `float(v)` produced, and `.tolist()` on the boolean mask yields real Python
    bools.
    """
    finite = np.isfinite(med)
    obj = med.astype(object)
    obj[~finite] = None
    return obj.tolist(), finite


def _nearest_pro_idx(win_t, pro_sorted, order, nP, tol, prior=False):
    """Vectorized nearest-PRO index (orig order) per window time, -1 if beyond tol.

    `prior=True` restricts a window to a PRO at or AFTER it (the window must precede the rating,
    dt = pro_time - win_time >= 0) instead of whichever PRO is symmetrically closest -- the same
    forecasting-safe restriction `streaming_psd._match_to_pro`'s "prior" mode applies, adapted to
    this module's window-first (rather than PRO-first) search.

    Lifted out of `live_lsb_spectrum_match` unchanged so the per-band exclusion path below decides
    which rating owns a chunk by the identical rule rather than a second copy of it.
    """
    if win_t.size == 0 or nP == 0:
        return np.full(win_t.size, -1, dtype=int)
    pos = np.searchsorted(pro_sorted, win_t)
    if prior:
        right = np.clip(pos, 0, nP - 1)
        dr = pro_sorted[right] - win_t
        nn = order[right]
        nn[(dr < 0) | (dr > tol) | (pos >= nP)] = -1
        return nn
    left = np.clip(pos - 1, 0, nP - 1)
    right = np.clip(pos, 0, nP - 1)
    dl = np.abs(win_t - pro_sorted[left])
    dr = np.abs(win_t - pro_sorted[right])
    take_left = dl <= dr                       # tie -> earlier PRO (deterministic)
    nn_sorted = np.where(take_left, left, right)
    dist = np.where(take_left, dl, dr)
    nn = order[nn_sorted]
    nn[dist > tol] = -1
    return nn


def live_lsb_band_medians_by_length(pro_times, raw_cache, *, tol_s, lengths_s, centers_hz,
                                    band_ceilings, allow_window_reuse=False,
                                    match_direction="nearest"):
    """Band power per pain report and per length of signal, excluding contaminated 3 s chunks
    BEFORE they are averaged, and taking the next-nearest clean chunk in place of each one dropped.

    WHY THIS EXISTS, AND WHY IT IS NOT THE SAME AS EXCLUDING AFTERWARDS (PI, 2026-09-09).
    The ceilings in `analytics.BAND_SWEEP_LSB_CEILINGS` are the 99.5th percentile of this
    participant's INDIVIDUAL 3 s chunk values. Comparing them against a cell that already averaged
    up to 100 chunks compares a threshold against a different, much narrower distribution: measured
    on RCS08, that discarded 0.708 percent of the 1 s row but only 0.300 percent from the 20 s row
    up, so "the top 0.5 percent" meant ten different things down one column. Excluding here, before
    any averaging, compares each value against the population the ceiling was actually built from,
    so one chunk gets one verdict at a given band in every row of the grid.

    IT EXCLUDES PER BAND, NOT PER WHOLE CHUNK, and that was measured rather than assumed. Of
    296,157 chunks on RCS08, 11,208 (3.78 percent) sit above the ceiling in at least one band but
    only 4 (0.001 percent) do in all 22, and a third of them are over in exactly one band -- so
    dropping a whole chunk for one bad band would discard 3.78 percent of the record, almost all of
    it good data. A chunk therefore drops out at 8.5 Hz and stays in at 20 Hz.

    BACKFILL, the PI's own choice over simply dropping. Each rating's eligible chunks are put in
    one fixed order, nearest in time first; the value for length N at band c is the median of the
    first N chunks of that order that are CLEAN AT BAND c. So a cell keeps the sample count its row
    asks for and the length-of-signal axis stays comparable across the grid, instead of a cell
    quietly averaging 97 chunks where its neighbour averaged 100.

    Which chunks are eligible, and which rating owns each one, are decided by the SAME two helpers
    `live_lsb_spectrum_match` uses (`_pad_windows_in_extent` / `_pad_owned_windows` over
    `_nearest_pro_idx`), so only the surviving-chunk step differs between the two paths.

    `band_ceilings` is one ceiling per entry of `centers_hz`, `np.inf` where that centre has none
    (that band then keeps every chunk). Nothing is written back into `raw_cache`.

    Returns `(power_by_length, info, stats_by_length)`. `power_by_length` maps each requested length
    in seconds to an (n_ratings x n_centres) array of linear device-LSB band power, NaN where a
    rating has no surviving measurement. `info` carries the exclusion counts for the page's own
    notes. `stats_by_length` is the same per-length matching summary `live_lsb_spectrum_match`
    reports, and carries the same numbers: eligibility, ownership and the quantity cap are what
    those fields describe, and this function changes none of them. `n_td_used` counts the pieces a
    rating's cell averages, which backfill holds at the requested count except where a rating's own
    eligible pieces run out -- `info["n_cells_short_of_requested"]` counts exactly those cells.
    """
    centers_cache = np.atleast_1d(np.asarray(raw_cache.get("centers_hz") or [], dtype=float))
    sweep_c = np.atleast_1d(np.asarray(centers_hz, dtype=float))
    nCc, nCs = centers_cache.size, sweep_c.size
    window_s = float(raw_cache.get("window_s") or analytics.RAW_LSB_WINDOW_SECONDS)
    pro = np.atleast_1d(np.asarray(pro_times, dtype=float))
    nP = pro.size
    lengths = [float(s) for s in lengths_s]
    out = {s: np.full((nP, nCs), np.nan, dtype=float) for s in lengths}
    info = {"n_chunk_band_values_excluded": 0, "n_chunks_eligible": 0,
            "n_cells_short_of_requested": 0, "tol_s": float(tol_s),
            "allow_window_reuse": bool(allow_window_reuse),
            # WHICH RATINGS THE LENGTH-OF-SIGNAL AXIS DOES NOT APPLY TO (open item 26). One entry
            # per rating, True where its value came from the device's own spectrum. That branch
            # never reads a length of signal -- it has no quantity cap, so it writes the SAME
            # number into every row of the grid -- and nothing downstream could tell, because the
            # number is perfectly ordinary. Carried out of here rather than re-derived later so
            # the flag and the value it describes are produced by one pass over one rule.
            "from_device_spectrum": []}
    stats_by_length = {}
    if nP == 0 or nCs == 0 or nCc == 0 or window_s <= 0:
        return out, info, stats_by_length

    col = np.asarray([int(np.argmin(np.abs(centers_cache - c))) for c in sweep_c], dtype=int)
    ceil = np.asarray(band_ceilings, dtype=float)
    caps = [max(1, int(round(s / window_s))) for s in lengths]
    cap_max = max(caps) if caps else 1

    prior = str(match_direction or "nearest").lower() == "prior"
    order = np.argsort(pro, kind="stable")
    pro_sorted = pro[order]

    td = raw_cache.get("td") or {}
    td_t = np.atleast_1d(np.asarray(td.get("t") or [], dtype=float))
    td_ok = np.atleast_1d(np.asarray(td.get("ok") or [], dtype=bool))
    td_mat = _lsb_family_mat(td, nCc)
    td_valid = (td_ok if td_ok.size == td_t.size else np.zeros(td_t.size, bool)) & np.isfinite(td_t)

    if allow_window_reuse:
        idx, cnt = _pad_windows_in_extent(td_t, td_valid, pro, tol_s, nP, direction=match_direction)
    else:
        nn = np.full(td_t.size, -1, dtype=int)
        if td_valid.any():
            nn[td_valid] = _nearest_pro_idx(td_t[td_valid], pro_sorted, order, nP, tol_s,
                                            prior=prior)
        idx, cnt = _pad_owned_windows(nn, nP)
    td_tier = cnt > 0
    info["n_chunks_eligible"] = int(cnt.sum())

    if idx.shape[1] > 0:
        # One fixed order per rating, closest in time first, so "the nearest N that survive at this
        # band" is a prefix of it. Padding sorts last on an infinite distance.
        safe = np.maximum(idx, 0)
        dist = np.where(idx >= 0, np.abs(td_t[safe] - pro[:, None]), np.inf)
        S = np.take_along_axis(idx, np.argsort(dist, axis=1, kind="stable"), axis=1)
        real = S >= 0
        Ssafe = np.maximum(S, 0)

        for j in range(nCs):
            vals = np.where(real, td_mat[Ssafe, col[j]], np.nan)
            bad = real & np.isfinite(vals) & (vals > ceil[j])
            good = real & ~bad
            info["n_chunk_band_values_excluded"] += int(bad.sum())
            rank = np.cumsum(good, axis=1)
            # Columns past the point where every rating already has cap_max clean chunks can never
            # change any length's answer, so the per-length reduction below runs on a narrow slice
            # rather than the full eligible width.
            over = rank > cap_max
            any_over = over.any(axis=1)
            last = np.where(any_over, np.argmax(over, axis=1), rank.shape[1] - 1)
            width = int(last.max()) + 1
            g, r, v = good[:, :width], rank[:, :width], vals[:, :width]
            for s, cap in zip(lengths, caps):
                keep = g & (r <= cap)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    out[s][:, j] = np.where(td_tier, np.nanmedian(np.where(keep, v, np.nan), axis=1),
                                            np.nan)
                # Only cells the EXCLUSION left short, never cells that were always going to be
                # short because the rating has little recording near it -- that is pre-existing and
                # counting it here would blame this rule for it. The comparison is therefore
                # against what this rating would have averaged with nothing excluded at all.
                would_have = np.minimum(cap, cnt)
                info["n_cells_short_of_requested"] += int(
                    (td_tier & (keep.sum(axis=1) < would_have)).sum())

    # ---- PSD bridge, for ratings with no eligible chunk of voltage trace at all -------------------
    # Same eligibility rule as `live_lsb_spectrum_match`: the voltage trace is preferred, and a rating
    # only falls here when it owns none.
    #
    # THE LENGTH-OF-SIGNAL AXIS APPLIES HERE TOO, since 2026-09-10 (the PI's rule, decision 121).
    # Each of the device's own FFT snapshots covers 30 s of signal (DEVICE_percept_rc.md: "30 s,
    # beginning 30 s after the button press"), so a row asking for N seconds takes the nearest
    # ceil(N / 30) snapshots -- one for every row up to 30 s, two for 45 s and 60 s, ten for 5 min --
    # and a rating that does not have that many clean snapshots within the match window contributes
    # NOTHING to that row. Before this, the bridge had no quantity cap at all: it took the median of
    # every snapshot in the window and wrote the same number into every row, so for a rating served
    # this way the length axis was a constant dressed as a trend (open item 26, decision 106). The
    # per-band clean-prefix rule is the same one the voltage-trace block above uses, so a snapshot
    # contaminated at one band drops out at that band only.
    psd = raw_cache.get("psd") or {}
    psd_t = np.atleast_1d(np.asarray(psd.get("t") or [], dtype=float))
    psd_mat = _lsb_family_mat(psd, nCc)
    psd_valid = np.isfinite(psd_t)
    pcnt = np.zeros(nP, dtype=np.int64)
    take = np.zeros(nP, dtype=bool)
    psd_caps = [max(1, int(np.ceil(s / PSD_SNAPSHOT_SECONDS))) for s in lengths]
    info["psd_snapshot_s"] = float(PSD_SNAPSHOT_SECONDS)
    info["psd_snapshots_needed_by_length"] = {float(s): int(k) for s, k in zip(lengths, psd_caps)}
    info["n_psd_ratings_short_by_length"] = {float(s): 0 for s in lengths}
    psd_filled = {s: np.zeros(nP, dtype=bool) for s in lengths}
    if psd_t.size and (~td_tier).any():
        if allow_window_reuse:
            pidx, pcnt = _pad_windows_in_extent(psd_t, psd_valid, pro, tol_s, nP,
                                                direction=match_direction)
        else:
            pnn = np.full(psd_t.size, -1, dtype=int)
            if psd_valid.any():
                pnn[psd_valid] = _nearest_pro_idx(psd_t[psd_valid], pro_sorted, order, nP, tol_s,
                                                  prior=prior)
            pidx, pcnt = _pad_owned_windows(pnn, nP)
        take = (~td_tier) & (pcnt > 0)
        if take.any() and pidx.shape[1] > 0:
            psafe = np.maximum(pidx, 0)
            pdist = np.where(pidx >= 0, np.abs(psd_t[psafe] - pro[:, None]), np.inf)
            PS = np.take_along_axis(pidx, np.argsort(pdist, axis=1, kind="stable"), axis=1)
            preal = PS >= 0
            PSsafe = np.maximum(PS, 0)
            for j in range(nCs):
                pv = np.where(preal, psd_mat[PSsafe, col[j]], np.nan)
                pbad = preal & np.isfinite(pv) & (pv > ceil[j])
                pgood = preal & ~pbad
                info["n_chunk_band_values_excluded"] += int(pbad.sum())
                prank = np.cumsum(pgood, axis=1)
                for s, need in zip(lengths, psd_caps):
                    keep = pgood & (prank <= need)
                    enough = keep.sum(axis=1) >= need
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        pmed = np.nanmedian(np.where(keep, pv, np.nan), axis=1)
                    row_take = take & enough
                    out[s][row_take, j] = pmed[row_take]
                    psd_filled[s] |= row_take
            for s, need in zip(lengths, psd_caps):
                info["n_psd_ratings_short_by_length"][float(s)] = int((take & (pcnt < need)).sum())

    # `take` is exactly the ratings whose value came from the device's own spectrum, and it is what
    # the loop above wrote into EVERY length. Reported per rating so a cell can later count only
    # the ratings it actually used, rather than a whole contact's average pasted onto every cell.
    info["from_device_spectrum"] = [bool(v) for v in take.tolist()]

    # The same per-length matching summary the established matcher reports, built from the same
    # quantities: which pieces were eligible, which rating owns each, and the quantity cap. Those
    # are the three things this path does NOT change, so these fields keep their meaning exactly.
    n_pro_td = int(td_tier.sum())
    for s, cap, need in zip(lengths, caps, psd_caps):
        # A snapshot-served rating counts for a row only when it could fill it (decision 121), so
        # `n_pro_psd` and `n_psd_used` are per length now, where they used to be one number.
        n_pro_psd = int(psd_filled[s].sum())
        stats_by_length[s] = {
            "n_pro": int(nP), "n_pro_td": n_pro_td, "n_pro_psd": n_pro_psd,
            "n_pro_unmatched": int(nP - n_pro_td - n_pro_psd),
            "n_td_windows": int(td_t.size), "n_psd_windows": int(psd_t.size),
            "n_td_assigned": int(cnt.sum()),
            "n_td_used": int(np.minimum(cnt, cap)[td_tier].sum()),
            "n_psd_assigned": int(pcnt.sum()),
            "n_psd_used": int(np.minimum(pcnt, need)[psd_filled[s]].sum()),
            "psd_n_snapshots_cap": int(need), "psd_snapshot_s": float(PSD_SNAPSHOT_SECONDS),
            "tol_s": float(tol_s), "td_quantity_s": float(s), "td_n_epochs_cap": int(cap),
            "extent_s": float(s), "psd_tol_s": float(tol_s),
            "allow_window_reuse": bool(allow_window_reuse),
            "match_direction": "prior" if prior else "prospective"}
    return out, info, stats_by_length


def live_lsb_spectrum_match(pro_times, raw_cache, *, tol_s=None, td_quantity_s=None,
                            allow_window_reuse=False, extent_s=None, psd_tol_s=None,
                            match_direction="nearest", want_records=True):
    """LIVE per-PRO LSB spectrum by matching PROs against the match-AGNOSTIC raw cache.

    `want_records=False` skips building the per-PRO record list entirely (the `recs` return is
    `None`) and returns only `stats`. Every stats field is already computed from counts/booleans
    that exist before the per-tier median-and-record-building blocks below run, so this changes
    no number in `stats` — it only skips work whose sole purpose is populating `recs`. Default
    True preserves the return contract for every existing caller.

    Consumes one channel's `raw_lsb_spectrum_cache(...)` output and produces the SAME per-PRO
    record list the retired per-rating many-centre reader returned (one list of LSB band-power values
    per rating; deleted 2026-09-10, decision 115), but with the
    matching done at request time over the pre-computed 3 s LSB tiles.

    TWO-WINDOW MATCHING (PI 2026-06-28 — the modality split):
      The matching uses TWO independent time controls with DIFFERENT jobs:

      * `tol_s` (the MAIN match-tolerance slider, MatchToleranceMin × 60) is the ELIGIBILITY radius
        for BOTH modalities — a raw window (TD tile OR PSD event) is eligible for a PRO only if it
        falls within ±tol_s of the rating. This is the only PSD control: a PRO's PSD-bridge LSB is the
        nan-median over EVERY eligible PSD event within ±tol_s (no quantity cap on PSD).

      * `td_quantity_s` (the SEPARATE "rating-centered extent" slider) is NOT a ± tolerance — it is a
        QUANTITY OF TD SIGNAL. After TD eligibility is decided by `tol_s`, a PRO keeps only the
        `n_epochs = round(td_quantity_s / window_s)` TD tiles CLOSEST to the rating (window_s = 3 s
        non-overlapping tiles, so 30 s → nearest 10 tiles), ranked by |tile_t − rating_t| regardless
        of whether they fall before or after the rating, then takes their per-band nan-median. So the
        slider dictates "how many seconds of the nearest TD signal to aggregate," not a search radius.

    REUSE flag (per modality, independent of the two windows above):
      * STRICT (allow_window_reuse=False, default): each eligible window is assigned to its single
        NEAREST PRO within ±tol_s (searchsorted, ties → earlier PRO), so no TD tile or PSD event is
        reused across >1 PRO. The TD nearest-N cap is then applied within each PRO's owned tiles.
      * REUSE (allow_window_reuse=True): each PRO independently gathers EVERY eligible window within
        ±tol_s (TD then capped to nearest-N), so one window may serve several overlapping PROs.
      The per-modality non-reuse property is independent of this flag: TD and PSD are matched in
      separate passes, so a montage's TD tile and its co-timestamped device-PSD window can serve two
      different PROs in BOTH modes — the flag only governs reuse of the SAME window+modality.

      TD is PREFERRED over PSD within a PRO: a PRO that owns ≥1 ok TD tile is td_transform tier (its
      spectrum = the nan-median over its nearest-N TD tiles); only a PRO with zero eligible TD tiles
      falls to psd_bridge. A PSD event whose nearest PRO turned out TD-tier is left unused (reported).

    Returns (records, stats):
      records : list in pro_times order, each {"t","tier","lsb"[C linear|None],"calibrated"[C bool],
                "center_hz"[C],"used_s","saturated","reason","n_td_used","n_psd_used"}.
      stats   : {"n_pro","n_pro_td","n_pro_psd","n_pro_unmatched","n_td_windows","n_psd_windows",
                 "n_td_assigned","n_td_used","n_psd_assigned","n_psd_used","tol_s","td_quantity_s",
                 "td_n_epochs_cap","extent_s","psd_tol_s","allow_window_reuse"}.
                — n_td_assigned (eligible TD tiles owned within ±tol_s) minus n_td_used (after the
                nearest-N quantity cap) is the count of eligible TD tiles dropped by the slider cap.

    VECTORISED 2026-09-06: the two per-rating Python loops (one nan-median per rating per
    modality, plus per-band list comprehensions) were replaced by a padded
    (n_ratings x max_windows x n_bands) gather collapsed with a SINGLE np.nanmedian per
    modality. The eligibility test and the nearest-rating assignment are untouched. Output
    values are unchanged; see tests/test_live_match_vectorised.py.
    """
    # Back-compat: the old API passed extent_s (a ±half-window) and psd_tol_s. The new API passes
    # tol_s (main eligibility) + td_quantity_s (TD quantity). If only the legacy args arrived, map
    # them so old callers keep working: extent_s → both tol_s (its full width) and td_quantity_s.
    if tol_s is None:
        tol_s = (psd_tol_s if psd_tol_s is not None
                 else (float(extent_s) if extent_s is not None
                       else analytics.TRANSFORM_CENTERED_EXTENT_SECONDS))
    if td_quantity_s is None:
        td_quantity_s = (float(extent_s) if extent_s is not None
                         else analytics.TRANSFORM_CENTERED_EXTENT_SECONDS)
    tol_s = float(tol_s)
    td_quantity_s = float(td_quantity_s)
    centers = np.atleast_1d(np.asarray(raw_cache.get("centers_hz"), dtype=float))
    nC = centers.size
    window_s = float(raw_cache.get("window_s") or analytics.RAW_LSB_WINDOW_SECONDS)
    # TD quantity cap: how many nearest 3 s tiles to aggregate. round(quantity / window_s), >=1 so a
    # sub-tile quantity still keeps the single closest tile. PSD has no quantity cap (median over all
    # eligible events within tol_s).
    td_n_epochs_cap = max(1, int(round(td_quantity_s / window_s))) if window_s > 0 else 1
    lo_hz = float(analytics.LSB_VALIDATED_HZ_LO)
    hi_hz = float(analytics.LSB_DEPLOYABLE_HZ_HI)
    cal_band = (centers >= lo_hz - 1e-9) & (centers <= hi_hz + 1e-9)

    pro = np.atleast_1d(np.asarray(pro_times, dtype=float))
    nP = pro.size
    order = np.argsort(pro, kind="stable")
    pro_sorted = pro[order]

    if want_records:
        none_vec = [None] * nC
        center_vec = [float(c) for c in centers]
        recs = [{"t": float(tp), "tier": None, "lsb": list(none_vec),
                 "calibrated": [False] * nC, "center_hz": list(center_vec),
                 "used_s": 0.0, "saturated": False, "reason": "", "n_td_used": 0, "n_psd_used": 0}
                for tp in pro]
    else:
        recs = None

    # Only "prior" changes behaviour here: this matcher is window-first (it asks "which PRO owns
    # this window"), so the older routine's PRO-first FRAMING has no equivalent to switch to — every
    # other UI value ("nearest", "pro_first") matches symmetrically, in either time direction.
    _prior_mode = str(match_direction or "nearest").lower() == "prior"

    def _nearest_pro(win_t, tol, prior=False):
        """This function's own bindings applied to the module-level search (`_nearest_pro_idx`),
        which was lifted out of here so `live_lsb_band_medians_by_length` decides ownership by the
        identical rule rather than a second copy of it."""
        return _nearest_pro_idx(win_t, pro_sorted, order, nP, tol, prior=prior)

    # ---- TD assignment ---------------------------------------------------------------------------
    td = raw_cache.get("td") or {}
    td_t = np.atleast_1d(np.asarray(td.get("t") or [], dtype=float))
    td_ok = np.atleast_1d(np.asarray(td.get("ok") or [], dtype=bool))
    td_mat = _lsb_family_mat(td, nC)
    n_td_windows = int(td_t.size)
    td_valid = (td_ok if td_ok.size == td_t.size else np.zeros(td_t.size, bool)) & np.isfinite(td_t)
    # TD ELIGIBILITY uses tol_s (the main slider), NOT the quantity slider. STRICT: each eligible tile
    # -> its single nearest PRO within +/-tol_s (nn_td). REUSE: each PRO -> every eligible tile within
    # +/-tol_s; a tile may then appear under multiple PROs. The QUANTITY cap
    # (td_n_epochs_cap = nearest-N tiles by |dt|) is applied below, AFTER eligibility, for all PROs at
    # once. Both branches now hand back ONE padded (nP x max_tiles) index matrix plus a per-PRO real
    # count, so the collapse below is a single reduction rather than nP small ones.
    if allow_window_reuse:
        td_idx, td_cnt = _pad_windows_in_extent(td_t, td_valid, pro, tol_s, nP,
                                                direction=match_direction)
    else:
        nn_td = np.full(td_t.size, -1, dtype=int)
        if td_valid.any():
            nn_td[td_valid] = _nearest_pro(td_t[td_valid], tol_s, prior=_prior_mode)
        td_idx, td_cnt = _pad_owned_windows(nn_td, nP)
    n_td_assigned = int(td_cnt.sum())

    # QUANTITY CAP: of each PRO's eligible tiles, keep only the td_n_epochs_cap CLOSEST to the rating
    # (by |tile_t - pro_t|, before/after agnostic). This is the "how much TD signal to use" slider:
    # 30 s -> nearest 10 non-overlapping 3 s tiles -> their median. Ties on |dt| break to the earlier
    # tile (stable argsort) so the choice is deterministic.
    td_idx = _cap_nearest_windows(td_idx, td_t, pro, td_n_epochs_cap)
    td_use = np.minimum(td_cnt, td_n_epochs_cap)
    td_tier_pro = td_cnt > 0
    n_td_used = int(td_use[td_tier_pro].sum())

    if want_records and td_tier_pro.any():
        td_rows = np.where(td_tier_pro)[0]
        td_med = _padded_nanmedian(td_mat, td_idx[td_rows])
        td_lsb, td_fin = _lsb_none_lists(td_med)
        td_cal = td_fin.tolist()                       # TD k is band-agnostic-calibrated
        td_used_s = (td_use[td_rows] * window_s).astype(float).tolist()
        td_use_l = td_use[td_rows].tolist()
        td_cnt_l = td_cnt[td_rows].tolist()
        td_reason_tail = ("(<=%.0fs signal within +/-%.0fs tol, k=%.2f)"
                          % (td_quantity_s, tol_s, analytics.LSB_PER_UV2_TRANSFORM))
        for i, p in enumerate(td_rows.tolist()):
            rec = recs[p]
            rec["tier"] = PRO_LSB_TIER_TD
            rec["lsb"] = td_lsb[i]
            rec["calibrated"] = td_cal[i]
            rec["n_td_used"] = int(td_use_l[i])
            rec["used_s"] = td_used_s[i]
            rec["reason"] = ("live TD->LSB median over nearest %d of %d eligible tile(s) %s"
                             % (td_use_l[i], td_cnt_l[i], td_reason_tail))

    # ---- PSD assignment (only PROs with no TD become psd_bridge) ----------------------------------
    psd = raw_cache.get("psd") or {}
    psd_t = np.atleast_1d(np.asarray(psd.get("t") or [], dtype=float))
    psd_mat = _lsb_family_mat(psd, nC)
    n_psd_windows = int(psd_t.size)
    psd_valid = np.isfinite(psd_t)
    # PSD ELIGIBILITY also uses tol_s (the main slider) — the ONLY PSD control. No quantity cap: a
    # PRO's PSD-bridge LSB is the nan-median over EVERY eligible PSD event within +/-tol_s.
    if allow_window_reuse:
        psd_idx, psd_cnt = _pad_windows_in_extent(psd_t, psd_valid, pro, tol_s, nP,
                                                  direction=match_direction)
    else:
        nn_psd = np.full(psd_t.size, -1, dtype=int)
        if psd_valid.any():
            nn_psd[psd_valid] = _nearest_pro(psd_t[psd_valid], tol_s, prior=_prior_mode)
        psd_idx, psd_cnt = _pad_owned_windows(nn_psd, nP)
    n_psd_assigned = int(psd_cnt.sum())

    # TD is PREFERRED: a PSD event whose nearest PRO turned out TD-tier is left unused (reported).
    psd_take = (~td_tier_pro) & (psd_cnt > 0)
    n_psd_used = int(psd_cnt[psd_take].sum())

    if want_records and psd_take.any():
        psd_rows = np.where(psd_take)[0]
        keep_cols = int(psd_cnt[psd_rows].max())
        psd_med = _padded_nanmedian(psd_mat, psd_idx[psd_rows][:, :keep_cols])
        psd_lsb, psd_fin = _lsb_none_lists(psd_med)
        psd_cal = (psd_fin & cal_band[None, :]).tolist()
        psd_cnt_l = psd_cnt[psd_rows].tolist()
        psd_reason_tail = ("within +/-%.0fs (k=%.2f); calibrated only in [%.1f,%.1f] Hz"
                           % (tol_s, analytics.LSB_PER_DEVICE_PSD, lo_hz, hi_hz))
        for i, p in enumerate(psd_rows.tolist()):
            rec = recs[p]
            rec["tier"] = PRO_LSB_TIER_BRIDGE
            rec["lsb"] = psd_lsb[i]
            rec["calibrated"] = psd_cal[i]
            rec["n_psd_used"] = int(psd_cnt_l[i])
            rec["reason"] = ("live PSD->LSB median over %d event(s) %s"
                             % (psd_cnt_l[i], psd_reason_tail))

    n_pro_td = int(td_tier_pro.sum())
    n_pro_psd = int(psd_take.sum())
    stats = {"n_pro": int(nP), "n_pro_td": n_pro_td, "n_pro_psd": n_pro_psd,
             "n_pro_unmatched": int(nP - n_pro_td - n_pro_psd),
             "n_td_windows": n_td_windows, "n_psd_windows": n_psd_windows,
             "n_td_assigned": n_td_assigned, "n_td_used": n_td_used,
             "n_psd_assigned": n_psd_assigned, "n_psd_used": n_psd_used,
             "tol_s": tol_s, "td_quantity_s": td_quantity_s, "td_n_epochs_cap": int(td_n_epochs_cap),
             # legacy aliases kept so existing UI/echo readers don't KeyError:
             "extent_s": td_quantity_s, "psd_tol_s": tol_s,
             "allow_window_reuse": bool(allow_window_reuse),
             "match_direction": "prior" if _prior_mode else "prospective"}
    return recs, stats


# THE PER-RATING SLIDING-WINDOW TRACE WAS HERE, AND IS DELETED (PI, 2026-09-10).
#
# It returned all ~60 of the 1 s half-overlapping windows inside one pain rating's 30 s of voltage
# trace, plus a per-window saturation flag, so a page could have drawn how the band power moved
# across that half minute instead of the single median `per_pro_lsb` returns. It was built, tested
# and correct, and NO PAGE EVER DREW IT -- its only callers were its own tests.
#
# His decision, in his words: "for the data availability timeline, we don't need those 60 slices.
# You can discard them after they're calculated. The median is just for visualization to get an
# idea." That is exactly what the wired path already does, so the trace had no destination.
#
# Nothing else used it: the only production call of `td_transform_band_power(agg="none")` -- the
# per-window mode -- was inside this function, and that mode itself stays, since it is a general
# capability of the transform rather than part of this display.

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
