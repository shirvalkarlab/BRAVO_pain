"""The canonical form: one lookup, built once per request, holding what every reader used to re-derive.

WHAT PROBLEM THIS ADDRESSES, MEASURED RATHER THAN ASSUMED
---------------------------------------------------------
Before Track B, during one Biomarker page request for participant 2e3c75c0 the channel-name
canonicaliser `availability._canon_channel` was called **72,425,865 times**, and **72,332,380
of those (99.87 percent) came from a single line**, the spectrum-event scan inside what is now
`availability._per_pro_lsb_scan`. That line walked the whole list of spectrum-bearing patient
records once for every pain report, and re-canonicalised each record's channel name on every
pass. The canonical name is a property of the record, so every pass after the first computed
a value the request already had. The same line also re-parsed each record's timestamp on
every pass. Since Track B steps 2 and 3, `availability.channel_index` builds this form once
per request and both readers use it.

The cost is therefore NOT in turning bytes on disk into recordings. Reading and un-pickling
every stored file for this participant costs 3.15 s of wall clock, because that work is
already spread over sixteen threads. The cost is in re-deriving small facts about recordings
that were already decoded.

WHAT THIS FORM HOLDS
--------------------
One `ChannelIndex` per (set of recordings, set of spectrum records). Two groupings, both
keyed on the CANONICAL channel name so a reader never canonicalises again:

  * `td_by_channel[channel]`  -> the voltage-trace route. A list of prepared traces, each
    holding the channel's own column of samples, the recording's start and end on the wall
    clock, its sampling rate, its per-sample dropped-packet flag, and the sample step the
    band-power recipe advances by. Sorted by start time so a reader can bisect.
  * `psd_by_channel[channel]` -> the device-spectrum route. The record list for that channel
    in ITS ORIGINAL ORDER, with the timestamps already parsed into one array of epoch
    seconds. Records whose timestamp will not parse are dropped here, exactly as the current
    code drops them per pass.

UNITS. THIS FORM CONVERTS NOTHING.
----------------------------------
Every array is stored in the units it was decoded in and no calibration constant appears
anywhere in this file:

  * `td_by_channel[...]["col"]` is microvolts, 250 samples per second, as the device wrote it.
  * `psd_by_channel[...]["freq"]` is hertz and `["power"]` is the device's own spectral
    magnitude, both untouched.
  * `["t0"]`, `["t1"]` and `["t"]` are Unix epoch seconds.

The two calibrated constants that carry these into device band-power units --
`LSB_PER_UV2_TRANSFORM` for the voltage-trace route and `LSB_PER_DEVICE_PSD` for the
device-spectrum route -- stay where they are, inside `analytics.td_to_lsb` and
`analytics.device_psd_to_lsb`. A reader of this form calls those same functions. That is
deliberate: the constants are the lab's fitted values and a shared decode layer must not
become a second place where a unit conversion can drift.

THE TWO ROUTES ARE HELD SEPARATELY, WITH THEIR SOURCE ATTACHED.
---------------------------------------------------------------
They do not cover the same recordings -- the device computes its own spectrum only on a
patient button press or a stimulation-off contact survey -- so merging them into one array
would invent coverage. Each grouping is its own dictionary, and each prepared entry carries
the `source` string its record arrived with, so a reader can always say which route a number
came from.

WHAT IS DELIBERATELY ABSENT
---------------------------
No pain report, no REDCap column, and nothing derived from either. Pain reports are filed
continuously and a stored copy that outlived one request would eventually serve an analysis
missing the newest reports. Recordings have a cheap content key and reports do not, so
recordings can be keyed and cached and reports cannot. This form is built from recordings
alone and therefore never needs a freshness check.
"""
import numpy as np

# Bump when the FIELDS or the GROUPING RULE below change, so a stored copy built by older
# code is a miss rather than a wrong answer. This is not the canonicalisation rule's own
# version -- that is `_CHANNEL_CANON_VERSION` in bravo_service, and a change there must also
# bump this.
CHANNEL_INDEX_VERSION = 3      # 2: traces carry `seq` (recording order) and `product`
                                # 3: native_lsb_by_channel added (Power-Domain + Chronic Timeline,
                                #    values unconverted -- the "one decoding step" for every
                                #    stream `availability.lsb_series` reads, per its own tiers)


def canon_channel(name):
    """A Medtronic channel name in its canonical bipolar form.

    Byte-for-byte the rule in `availability._canon_channel`: upper case, the ring spelling
    `_AND_` collapsed, and a trailing `_RING` removed. Duplicated here rather than imported
    so this package can be exercised without the Biomarkers routines on the path; the test
    file asserts the two agree on every channel name in the live record, so a change to
    either without the other is caught.
    """
    u = str(name).upper().replace("_AND_", "_")
    if u.endswith("_RING"):
        u = u[:-len("_RING")]
    return u


def to_epoch(value):
    """A recording start time as Unix epoch seconds, or None.

    Mirrors `availability._to_epoch` exactly: an epoch number is taken as-is once it is past 1e9
    (which rejects a session-relative offset that would otherwise read as 1970); a string is
    parsed as ISO 8601 with a trailing Z accepted; a datetime is taken as-is.

    ONE RULE IS MIRRORED KNOWINGLY RATHER THAN CORRECTED. A string with no timezone is read in
    the process's LOCAL zone, because that is what the platform does. The first version of this
    function read it as universal time instead; the two agreed in the container, which runs in
    universal time, and disagreed by eight hours on the analysis host. The form exists to give
    the same answer as the platform, so it follows the platform here and the disagreement is
    recorded as a finding rather than fixed in one place only.
    """
    import datetime
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        return v if v >= 1e9 else None
    if isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.timestamp()
        except ValueError:
            return None
    if isinstance(value, datetime.datetime):
        return value.timestamp()
    return None


#: The device's own FFT bin centers, byte-for-byte `availability._FFT_BINS`. Duplicated here for
#: the same reason `canon_channel` is duplicated above -- this package must be exercisable with no
#: import of the Biomarkers routines, and a test asserts the two arrays agree.
_FFT_BINS = np.array([3.9, 4.9, 5.9, 6.8, 7.8, 8.8, 9.8, 10.7, 11.7, 12.7, 13.7, 14.6,
                      15.6, 16.6, 17.6, 18.6, 19.5, 20.5, 21.5, 22.5, 23.4, 24.4, 25.4, 26.4])

#: The device's missing-sample sentinel for LFP power columns, byte-for-byte
#: `availability._POWER_SENTINEL`.
_POWER_SENTINEL = 2.0 ** 31 - 1


def snap_freq(hz):
    """Snap a center frequency to the nearest Percept FFT bin (None-safe).

    Byte-for-byte `availability.snap_freq`, duplicated for the same reason as `canon_channel`.
    """
    if hz is None:
        return None
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(hz):
        return None
    return float(_FFT_BINS[int(np.argmin(np.abs(_FFT_BINS - hz)))])


def sensing_center_hz(therapy_hemi):
    """Pull the BrainSense sensing-band CENTER FREQUENCY (Hz) from one hemisphere's Therapy
    snapshot. Byte-for-byte `analytics.sensing_center_hz`, duplicated for the same reason as
    `canon_channel` -- this reads frequency METADATA, not a calibration constant, so it does not
    violate this file's own "no calibration constant" rule (see the module docstring), but it
    still must not import from Biomarkers/analytics, so it is copied rather than imported.
    """
    if not isinstance(therapy_hemi, dict):
        return None
    setups = []
    setups.append(therapy_hemi)
    ss = therapy_hemi.get("SensingSetup")
    if isinstance(ss, dict):
        setups.append(ss)
    sensing = therapy_hemi.get("sensing")
    if isinstance(sensing, dict) and isinstance(sensing.get("SensingSetup"), dict):
        setups.append(sensing["SensingSetup"])
    rc = therapy_hemi.get("RecordingConfiguration")
    if isinstance(rc, dict):
        cfg = rc.get("Config")
        if isinstance(cfg, dict) and isinstance(cfg.get("SensingSetup"), dict):
            setups.append(cfg["SensingSetup"])
    for ss in setups:
        for key in ("FrequencyInHertz", "Frequency", "CenterFrequency", "CenterFrequencyInHertz"):
            v = ss.get(key)
            try:
                fv = float(v)
                if np.isfinite(fv) and fv > 0:
                    return round(fv, 2)
            except (TypeError, ValueError):
                continue
    return None


def power_center_freqs(powerdomain_list):
    """Map each power CONTACT to its sensing-band center frequency (Hz). Byte-for-byte
    `analytics.power_center_freqs`."""
    freqs = {}
    for r in powerdomain_list or []:
        if not isinstance(r, dict):
            continue
        desc = r.get("Descriptor")
        therapy = desc.get("Therapy") if isinstance(desc, dict) else None
        if not isinstance(therapy, dict):
            continue
        hemi_hz = {"LEFT": sensing_center_hz(therapy.get("Left")),
                   "RIGHT": sensing_center_hz(therapy.get("Right"))}
        for nm in r.get("ChannelNames", []) or []:
            s = str(nm)
            if "POWER" not in s.upper():
                continue
            contact = s.rsplit(" ", 1)[0] if " " in s else s
            cu = contact.upper()
            hz = hemi_hz["LEFT"] if "LEFT" in cu else (hemi_hz["RIGHT"] if "RIGHT" in cu else None)
            if hz is not None:
                freqs[contact] = hz
    return freqs


def native_lsb_by_channel(chronic_recordings, powerdomain_recordings):
    """The device's OWN sensed band-power series (Power-Domain streaming + Chronic Timeline),
    grouped by canonical channel, values UNCONVERTED.

    THIS IS THE "ADDED AS-IS" TIER. Unlike the montage/event-PSD modeled tiers in
    `availability.lsb_series` (which need a calibrated conversion -- `analytics.td_to_lsb` or
    `analytics.device_psd_to_lsb` -- to turn a voltage trace or device spectrum into an LSB
    value), the device's own Power-Domain and Chronic Timeline products already ARE the LSB
    quantity: the device sensed the band and reported its power directly, in its own units.
    Nothing here converts anything -- this function only resolves WHICH canonical channel each
    sample belongs to and WHAT sensing frequency was active when it was taken, which is exactly
    the kind of repeated small derivation this form exists to do once. The values themselves pass
    through unchanged, matching this file's own rule that no calibration constant appears here.

    Byte-for-byte the algorithm in `availability.lsb_series`'s Power-Domain and Chronic Timeline
    tiers (the montage-TD and event-PSD MODELED tiers are NOT here -- they need a calibration
    constant and stay in `lsb_series` itself, reader-side, per this file's stated design).

    Returns dict keyed by RAW channel name (not yet canonicalized -- `lsb_series` canonicalizes
    on push, same as before; kept this way so the output shape matches `lsb_series`'s existing
    `_push`-built dict exactly, field for field):
        { channel: { "t":[epoch_s], "y":[lsb, unconverted], "center_hz":[hz|None],
                     "source":["streaming"|"chronic"] } }
    Samples are NOT time-sorted here -- `lsb_series` sorts the pooled result (native + modeled
    tiers together) once, at the end, exactly as it does today.
    """
    out = {}

    def _push(ch, t, y, hz, src):
        d = out.setdefault(ch, {"t": [], "y": [], "center_hz": [], "source": []})
        d["t"].append(float(t)); d["y"].append(float(y))
        d["center_hz"].append(snap_freq(hz)); d["source"].append(src)

    # --- Power-Domain (~2 Hz): per-contact Power columns ---
    pd_center = power_center_freqs(powerdomain_recordings)
    for r in powerdomain_recordings or []:
        if not isinstance(r, dict) or "Data" not in r:
            continue
        names = list(r.get("ChannelNames", []) or [])
        data = np.asarray(r.get("Data"), dtype=float)
        if data.ndim != 2 or data.shape[0] == 0:
            continue
        n, ncols = data.shape
        fs = float(r.get("SamplingRate") or 2.0) or 2.0
        start = to_epoch(r.get("StartTime"))
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
        desc = r.get("Descriptor")
        therapy = desc.get("Therapy") if isinstance(desc, dict) else None
        hemi_hz = {}
        if isinstance(therapy, dict):
            hemi_hz = {"LEFT": sensing_center_hz(therapy.get("Left")),
                       "RIGHT": sensing_center_hz(therapy.get("Right"))}
        chan = names[0] if names else "LFP"
        cu = str(chan).upper()
        hemi = "LEFT" if "LEFT" in cu else ("RIGHT" if "RIGHT" in cu else "")
        key = hemi_contact.get(hemi, chan)

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

        def _hz_at(ts, _sched=sched, _fallback_hz=fallback_hz):
            cur = None
            for cms, chz in _sched:
                if cms <= ts:
                    cur = chz
                else:
                    break
            if cur is not None:
                return cur
            if _sched:
                return _sched[0][1]
            return _fallback_hz

        col = data[:, 0]
        bad = (col >= _POWER_SENTINEL) | (col < 0) | ~np.isfinite(col)
        for i in np.where(~bad)[0]:
            _push(key, float(tarr[i]), col[i], _hz_at(float(tarr[i])), "chronic")

    return out


def missing_per_sample(missing, nsamp):
    """A recording's dropped-packet field as one flag per sample, or None.

    Mirrors `availability._missing_per_sample`, including the any-channel rule: a dropped
    packet is zero-filled across every channel, so a two-dimensional field collapses with
    `any` along the channel axis.
    """
    if missing is None:
        return None
    m = np.asarray(missing)
    if m.size == 0:
        return None
    if m.ndim == 2:
        axis = 1 if m.shape[0] == nsamp else (0 if m.shape[1] == nsamp else 1)
        m = (m > 0).any(axis=axis)
    return np.asarray(m).ravel()


class ChannelIndex(object):
    """The built form. Read-only by contract; nothing here copies on read.

    A reader must not mutate `col`, `miss`, `freq`, `power` or `t`. They are views onto the
    decoded recordings, shared by every reader of one index, and a writer would corrupt every
    other reader. The current code has the same property and the same unwritten rule; stating
    it here is the only change.
    """

    __slots__ = ("td_by_channel", "psd_by_channel", "native_lsb_by_channel", "version",
                 "step_seconds", "n_td_recordings", "n_psd_records", "n_native_lsb_recordings",
                 "channels")

    def __init__(self, td_by_channel, psd_by_channel, native_lsb_by_channel, step_seconds,
                 n_td_recordings, n_psd_records, n_native_lsb_recordings):
        self.td_by_channel = td_by_channel
        self.psd_by_channel = psd_by_channel
        self.native_lsb_by_channel = native_lsb_by_channel
        self.step_seconds = float(step_seconds)
        self.n_td_recordings = int(n_td_recordings)
        self.n_psd_records = int(n_psd_records)
        self.n_native_lsb_recordings = int(n_native_lsb_recordings)
        self.version = CHANNEL_INDEX_VERSION
        self.channels = sorted(set(td_by_channel) | set(psd_by_channel)
                               | set(native_lsb_by_channel))

    def td(self, channel):
        """Prepared voltage traces carrying this channel, earliest first. Never None."""
        return self.td_by_channel.get(canon_channel(channel), _EMPTY_TD)

    def psd(self, channel):
        """The device-spectrum records for this channel, in their original order."""
        return self.psd_by_channel.get(canon_channel(channel), _EMPTY_PSD)

    # No `.native_lsb(channel)` per-channel accessor, unlike `.td()`/`.psd()` above.
    # `native_lsb_by_channel` is kept in whatever key spelling the recordings arrived in (see
    # `build_channel_index`'s own note on this), so a canonical-key lookup here would silently
    # miss entries a canonicalizing caller expects to find. The one reader of this grouping,
    # `availability.lsb_series`, reads the whole dict directly for exactly this reason.

    def summary(self):
        return {
            "version": self.version,
            "n_channels": len(self.channels),
            "n_td_recordings_offered": self.n_td_recordings,
            "n_td_traces_kept": sum(len(v["traces"]) for v in self.td_by_channel.values()),
            "n_psd_records_offered": self.n_psd_records,
            "n_psd_records_kept": sum(int(v["t"].size) for v in self.psd_by_channel.values()),
            "n_native_lsb_recordings_offered": self.n_native_lsb_recordings,
            "n_native_lsb_samples_kept": sum(len(v["t"])
                                             for v in self.native_lsb_by_channel.values()),
            "channels": list(self.channels),
        }


_EMPTY_TD = {"traces": [], "t0": np.empty(0, dtype=float)}
_EMPTY_PSD = {"t": np.empty(0, dtype=float), "records": []}


def build_channel_index(td_recordings=None, psd_records=None, *, step_seconds,
                        chronic_recordings=None, powerdomain_recordings=None):
    """Group decoded recordings by canonical channel, once.

    `td_recordings` are decoded recording dictionaries carrying a 250-samples-per-second
    voltage trace (`ChannelNames`, `Data`, `SamplingRate`, `StartTime`, optionally `Missing`).
    `psd_records` are the flat spectrum blocks the service already assembles, each
    `{channel, t, freq, power, source}`.

    `step_seconds` is the hop the band-power recipe advances by between windows
    (`analytics.TRANSFORM_STEP_SECONDS`). It is a required argument rather than a default
    read from `analytics`, so this file cannot quietly disagree with the recipe.

    A recording is dropped for exactly the reasons the current per-pass code drops it: not a
    dictionary, a `Data` field that is not two-dimensional, an unparseable start time, or a
    channel column that is not present. Nothing is dropped silently -- `summary()` reports how
    many were offered against how many were kept, so a systematic loss shows up as a count
    rather than as an empty panel.
    """
    td_by_channel = {}
    n_td = 0
    for r in (td_recordings or []):
        n_td += 1
        if not isinstance(r, dict):
            continue
        names = list(r.get("ChannelNames") or [])
        if not names:
            continue
        data = np.asarray(r.get("Data"), dtype=float)
        if data.ndim != 2:
            continue
        if data.shape[0] == len(names) and data.shape[1] != len(names):
            data = data.T                      # -> (n_samples, n_channels)
        fs = float(r.get("SamplingRate") or 250.0) or 250.0
        t0 = to_epoch(r.get("StartTime"))
        if t0 is None:
            continue
        nsamp = data.shape[0]
        dur_s = nsamp / fs if fs > 0 else 0.0
        miss = missing_per_sample(r.get("Missing"), nsamp)
        step = int(round(fs * float(step_seconds)))
        # ONE canonicalisation per (recording, channel name) for the whole request. The
        # current code repeats this per consumer and, on the spectrum route, per pain report.
        # FIRST occurrence only: the current code resolves a channel to a column with
        # `next(i for i, n in enumerate(names) if canon(n) == channel)`, so if a recording
        # somehow lists one canonical channel twice, only its first column is ever read.
        # Adding the second here would give this channel a trace the current code cannot see.
        seen_in_this_recording = set()
        for ci, raw_name in enumerate(names):
            if ci >= data.shape[1]:
                continue
            ch = canon_channel(raw_name)
            if ch in seen_in_this_recording:
                continue
            seen_in_this_recording.add(ch)
            bucket = td_by_channel.setdefault(ch, {"traces": [], "t0": None})
            bucket["traces"].append({
                "t0": t0, "t1": t0 + dur_s, "fs": fs,
                "col": data[:, ci], "miss": miss, "step": step,
                "raw_channel": str(raw_name),
                "source": r.get("RecordingType") or r.get("Source") or "",
                # the recording's position in the list it arrived in, so a reader that must
                # keep the caller's order (the tile builder) can sort the bucket back
                "seq": n_td - 1,
                # the ingest product label the tile builder turns into a source label
                "product": r.get("product"),
            })

    for ch, bucket in td_by_channel.items():
        # Earliest first, so a reader can bisect on start time and stop early. `sort` is
        # stable, so two traces starting at the same instant keep the order they were
        # decoded in -- which is the order the current code would have walked them in.
        bucket["traces"].sort(key=lambda d: d["t0"])
        bucket["t0"] = np.array([d["t0"] for d in bucket["traces"]], dtype=float)

    psd_by_channel = {}
    n_psd = 0
    for ev in (psd_records or []):
        n_psd += 1
        if not isinstance(ev, dict):
            continue
        te = to_epoch(ev.get("t"))
        if te is None:
            continue
        ch = canon_channel(ev.get("channel"))
        bucket = psd_by_channel.setdefault(ch, {"t": [], "records": []})
        bucket["t"].append(float(te))
        bucket["records"].append(ev)

    for ch, bucket in psd_by_channel.items():
        # NOT SORTED. The reader picks the record nearest a pain report and breaks a tie by
        # taking the FIRST, which is what the current linear scan does with its strictly-less
        # -than comparison. Sorting here would change which of two equidistant records wins.
        bucket["t"] = np.asarray(bucket["t"], dtype=float)

    # NOT re-keyed to the canonical form here. `lsb_series`'s own `_push` never canonicalized its
    # output keys either (a power-domain contact string and a chronic hemisphere-resolved key are
    # used exactly as they arrive), so this dict is kept in that same, already-established key
    # space -- re-keying here would silently MERGE two entries that `lsb_series` has always kept
    # separate whenever two recordings spell the same physical contact two different ways.
    # `.native_lsb(channel)` below canonicalizes for lookup; the raw dict itself does not.
    native_lsb = native_lsb_by_channel(chronic_recordings, powerdomain_recordings)
    n_native = len(chronic_recordings or []) + len(powerdomain_recordings or [])

    return ChannelIndex(td_by_channel, psd_by_channel, native_lsb, step_seconds,
                        n_td, n_psd, n_native)
