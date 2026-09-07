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
CHANNEL_INDEX_VERSION = 1


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

    __slots__ = ("td_by_channel", "psd_by_channel", "version", "step_seconds",
                 "n_td_recordings", "n_psd_records", "channels")

    def __init__(self, td_by_channel, psd_by_channel, step_seconds,
                 n_td_recordings, n_psd_records):
        self.td_by_channel = td_by_channel
        self.psd_by_channel = psd_by_channel
        self.step_seconds = float(step_seconds)
        self.n_td_recordings = int(n_td_recordings)
        self.n_psd_records = int(n_psd_records)
        self.version = CHANNEL_INDEX_VERSION
        self.channels = sorted(set(td_by_channel) | set(psd_by_channel))

    def td(self, channel):
        """Prepared voltage traces carrying this channel, earliest first. Never None."""
        return self.td_by_channel.get(canon_channel(channel), _EMPTY_TD)

    def psd(self, channel):
        """The device-spectrum records for this channel, in their original order."""
        return self.psd_by_channel.get(canon_channel(channel), _EMPTY_PSD)

    def summary(self):
        return {
            "version": self.version,
            "n_channels": len(self.channels),
            "n_td_recordings_offered": self.n_td_recordings,
            "n_td_traces_kept": sum(len(v["traces"]) for v in self.td_by_channel.values()),
            "n_psd_records_offered": self.n_psd_records,
            "n_psd_records_kept": sum(int(v["t"].size) for v in self.psd_by_channel.values()),
            "channels": list(self.channels),
        }


_EMPTY_TD = {"traces": [], "t0": np.empty(0, dtype=float)}
_EMPTY_PSD = {"t": np.empty(0, dtype=float), "records": []}


def build_channel_index(td_recordings=None, psd_records=None, *, step_seconds):
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

    return ChannelIndex(td_by_channel, psd_by_channel, step_seconds, n_td, n_psd)
