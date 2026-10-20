"""The canonical form: one lookup, built once per request, holding what every reader used to re-derive.

CANONICAL REPRESENTATION REUSED WITHIN A REQUEST
Channel names and parsed timestamps are properties of records, not of the pain
reports matched against them. Recomputing them for each report repeats the same
work. `availability.channel_index` constructs the representation once per request
and shares it with both readers.

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
CHANNEL_INDEX_VERSION = 5      # 2: traces carry `seq` (recording order) and `product`
                                # 3: native_lsb_by_channel added (Power-Domain + Chronic Timeline,
                                #    values unconverted -- the "one decoding step" for every
                                #    stream `availability.lsb_series` reads, per its own tiers)
                                # 4: each streaming run's own band; chronic samples filed under the
                                #    contact pair in force (decision 461, `run_band_hz`, `chronic_pair_keys`)
                                # 5: a streaming run reading 0 throughout left out (decision 462)


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

    A value with NO timezone attached -- a naive string or a naive `datetime` -- names a moment
    in Universal Time (UTC), on every machine this code runs on. THIS RULE WAS ONCE MIRRORED
    KNOWINGLY RATHER THAN CORRECTED: an earlier version of this function read a naive value as
    universal time while the platform read the identical string in the process's own local zone,
    and the two agreed only because the container happens to run in universal time -- they would
    have disagreed by eight hours on an analysis host that does not. Both functions were changed
    together, in the same step, so they cannot drift back apart (open item 19,
    `DECISIONS_and_open_items.md`). No naive start time has ever been seen in the live record, so
    this changes no number the platform has produced; it only fixes what a future naive value
    would mean.
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


#: Contact numbers within one lead, as the chronic record's contact schedule writes them ("0-3").
_PAIR_WORDS = ("ZERO", "ONE", "TWO", "THREE")


def run_band_hz(rec, contact, pd_center):
    """The band ONE BrainSense streaming run sensed on `contact`: that run's own sensing setup for
    the contact's side (decision 461), else the pair-level value `pd_center` holds (the last run's,
    `power_center_freqs`) when the run carries none. Not snapped."""
    desc = rec.get("Descriptor") if isinstance(rec, dict) else None
    therapy = desc.get("Therapy") if isinstance(desc, dict) else None
    cu = str(contact).upper()
    side = "Left" if "LEFT" in cu else ("Right" if "RIGHT" in cu else None)
    if isinstance(therapy, dict) and side:
        hz = sensing_center_hz(therapy.get(side))
        if hz is not None:
            return hz
    return pd_center.get(contact)


def is_zero_run(kept):
    """A BrainSense streaming run whose retained band-power samples are all exactly zero
is excluded from band-power series under decision 462, while the run remains stored
and is counted by `zero_runs`. A run with only some zeros is retained in full.
This avoids treating an entirely zero run as a usable threshold measurement."""
    kept = np.asarray(kept, dtype=float)
    return kept.size > 0 and not np.any(kept != 0.0)


def zero_runs(powerdomain_recordings):
    """Every streaming run column `is_zero_run` leaves out: [{pair, t0, n, center_hz}], in recording
    order, the pair canonical and the band the run's own (`run_band_hz`, snapped)."""
    pd_center = power_center_freqs(powerdomain_recordings)
    out = []
    for r in powerdomain_recordings or []:
        if not isinstance(r, dict) or "Data" not in r:
            continue
        data = np.asarray(r.get("Data"), dtype=float)
        start = to_epoch(r.get("StartTime"))
        if data.ndim != 2 or data.shape[0] == 0 or start is None:
            continue
        missing = np.asarray(r.get("Missing", np.zeros_like(data)), dtype=float)
        if missing.shape != data.shape:
            missing = np.zeros_like(data)
        for pi, nm in enumerate(list(r.get("ChannelNames", []) or [])):
            if pi >= data.shape[1] or "POWER" not in str(nm).upper():
                continue
            contact = str(nm).rsplit(" ", 1)[0] if " " in str(nm) else str(nm)
            col = data[:, pi]
            bad = (missing[:, pi] > 0) | (col >= _POWER_SENTINEL) | (col < 0) | ~np.isfinite(col)
            if is_zero_run(col[~bad]):
                out.append({"pair": canon_channel(contact), "t0": float(start), "n": int((~bad).sum()),
                            "center_hz": snap_freq(run_band_hz(r, contact, pd_center))})
    return out


def chronic_pair_keys(rec, times, hemi, fallback_key):
    """The contact pair each chronic sample was recorded on (decision 461): the chronic record's
    own contact schedule entry in force at the sample's time (the last at or before it, else the
    first), named as the streaming pairs are ("ONE_THREE_LEFT"). Every sample gets `fallback_key`
    (the old filing: the first streaming pair on that side) when the record has no usable schedule
    or the side is unknown. Returns a list, one key per time."""
    times = np.asarray(times, dtype=float)
    sched = []
    for item in (rec.get("ContactSchedule") or []) if isinstance(rec, dict) else []:
        try:
            ts = float(item[0])
            a, b = sorted(int(x) for x in str(item[1]).split("-"))
        except (TypeError, ValueError, IndexError):
            continue
        if 0 <= a < b <= 3:
            sched.append((ts, f"{_PAIR_WORDS[a]}_{_PAIR_WORDS[b]}_{hemi}"))
    if not sched or hemi not in ("LEFT", "RIGHT"):
        return [fallback_key] * times.size
    sched.sort(key=lambda p: p[0])
    starts = np.asarray([t for t, _ in sched], dtype=float)
    idx = np.searchsorted(starts, times, side="right") - 1
    idx[idx < 0] = 0
    return [sched[i][1] for i in idx.tolist()]


#: Prasad's chronic invalid-code analysis threshold (decision 487). This is an
#: upstream empirical policy for averaged device codes, not a vendor guarantee.
CHRONIC_INVALID_LSB = (2 ** 32 - 1) / 60.0
_CHRONIC_NAN = float("nan")


def chronic_band_tags(rec, times, hemi):
    """The band (snapped Hz, or None) each chronic sample was sensed in: the recording's own
    frequency schedule (the last change at or before the sample, else the first), else its stamped
    `CenterFrequencyHz`, else the therapy snapshot's sensing band for the side -- the rule
    `native_lsb_by_channel` files chronic samples by."""
    times = np.asarray(times, dtype=float)
    sched = []
    sched_raw = rec.get("FreqScheduleHz")
    if isinstance(sched_raw, (list, tuple)):
        for item in sched_raw:
            try:
                ts, shz = float(item[0]), snap_freq(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            if shz is not None:
                sched.append((ts, shz))
        sched.sort(key=lambda p: p[0])
    if sched:
        starts = np.asarray([c for c, _ in sched], dtype=float)
        idx = np.searchsorted(starts, times, side="right") - 1
        idx[idx < 0] = 0
        return [sched[i][1] for i in idx.tolist()]
    hz = snap_freq(rec.get("CenterFrequencyHz"))
    if hz is None and hemi:
        desc = rec.get("Descriptor")
        therapy = desc.get("Therapy") if isinstance(desc, dict) else None
        if isinstance(therapy, dict):
            hz = snap_freq(sensing_center_hz(therapy.get("Left" if hemi == "LEFT" else "Right")))
    return [hz] * times.size


def _chronic_order_key(rec):
    """Where a chronic recording sits when repeats are merged: by its content alone (first and last
    sample time, sample count, side, then a digest of its samples and settings), never by the order
    the exports arrived or the database returned them."""
    import hashlib
    t = np.asarray(rec.get("Time", []), dtype=float)
    d = np.ascontiguousarray(np.asarray(rec.get("Data"), dtype=float))
    h = hashlib.blake2b(digest_size=16)
    h.update(np.ascontiguousarray(t).tobytes())
    h.update(d.tobytes())
    h.update(repr((rec.get("ChannelNames"), rec.get("FreqScheduleHz"), rec.get("ContactSchedule"),
                   rec.get("CenterFrequencyHz"))).encode("utf8"))
    if rec.get("SignalLeadSchedule") is not None:
        h.update(repr(rec.get("SignalLeadSchedule")).encode("utf8"))
    return (float(t[0]) if t.size else float("inf"), float(t[-1]) if t.size else float("inf"),
            int(t.size), str((rec.get("ChannelNames") or [""])[0]), h.hexdigest())


def chronic_signal_leads(rec, times, hemi):
    """The lead ("LEFT"/"RIGHT") each chronic sample's signal came from (decision 488): the
    recording's `SignalLeadSchedule` entry in force at the sample's time (the last at or before it,
    else the first), written by the one schedule from the device settings
    (`MedtronicPercept/chronic_schedule.py`); `hemi`, the lead whose log holds the sample, when the
    recording has none."""
    times = np.asarray(times, dtype=float)
    sched = []
    for item in (rec.get("SignalLeadSchedule") or []) if isinstance(rec, dict) else []:
        try:
            ts, lead = float(item[0]), str(item[1]).upper()
        except (TypeError, ValueError, IndexError):
            continue
        if lead in ("LEFT", "RIGHT"):
            sched.append((ts, lead))
    if not sched or hemi not in ("LEFT", "RIGHT"):
        return [hemi] * times.size
    sched.sort(key=lambda p: p[0])
    starts = np.asarray([t for t, _ in sched], dtype=float)
    idx = np.searchsorted(starts, times, side="right") - 1
    idx[idx < 0] = 0
    return [sched[i][1] for i in idx.tolist()]


def _pair_on_lead(pair_key, lead):
    """A contact-pair key ("ONE_THREE_RIGHT", or "SIDE_RIGHT") named on another lead."""
    return pair_key.rsplit("_", 1)[0] + "_" + lead


def _same_power(a, b):
    return a == b or (a != a and b != b)


def _chronic_rows(r, keep, counts):
    """One chronic recording with only the rows in `keep`, the invalid code and exact zeros blanked
    (band power NaN, current kept) and counted. `r` itself when nothing changes."""
    d = np.asarray(r.get("Data"), dtype=float)
    n = keep.shape[0]
    invalid = keep & (d[:, 0] >= CHRONIC_INVALID_LSB) if n else np.zeros(0, dtype=bool)
    counts["invalid_code_values"] += int(invalid.sum())
    zero = keep & (d[:, 0] == 0) if n else np.zeros(0, dtype=bool)
    counts["zero_values"] += int(zero.sum())
    invalid = invalid | zero
    if keep.all() and not invalid.any():
        return r
    c = dict(r)
    for k_, v in r.items():
        if k_ in {"ChannelNames", "ContactSchedule", "FreqScheduleHz", "SignalLeadSchedule",
                   "ScheduleFlagged", "ScheduleNoRecord"} or not isinstance(v, (list, np.ndarray)) or len(v) != n:
            continue
        c[k_] = v[keep] if isinstance(v, np.ndarray) else [value for j, value in enumerate(v) if keep[j]]
    if invalid.any():
        nd = np.array(d[keep], dtype=float)
        nd[invalid[keep], 0] = np.nan
        c["Data"] = nd
    return c


def _with_other_currents(result, original, keep, observed):
    """Preserve every distinct other-lead current without selecting one arbitrarily."""
    if not observed:
        return result
    n = len(keep)
    previous = original.get("OtherLeadCurrentValuesMilliAmps")
    all_values = [list(v) for v in previous] if isinstance(previous, list) and len(previous) == n else [[] for _ in range(n)]
    for k, values in observed.items():
        for value in values:
            if not any(_same_power(value, held) for held in all_values[k]):
                all_values[k].append(value)
    col = np.full(n, np.nan)
    for k, values in enumerate(all_values):
        values.sort(key=lambda value: (not np.isfinite(value), value if np.isfinite(value) else 0))
        if len(values) == 1:
            col[k] = values[0]
    result = dict(result)
    result["OtherLeadCurrentMilliAmps"] = col[keep]
    result["OtherLeadCurrentValuesMilliAmps"] = [v for k, v in enumerate(all_values) if keep[k]]
    result["OtherLeadCurrentAmbiguous"] = np.asarray([len(v) > 1 for v in all_values])[keep]
    return result


def merge_chronic_repeats(chronic_recordings):
    """The chronic (10-minute) log with every reading once (the PI, 2026-10-18, items 6a and 6b).

    Each export carries the device's whole chronic log, so one reading is stored in every export
    made while it was in the log. A reading is identified by its side, the contact
    pair and band its own recording files it under (`chronic_pair_keys`, `chronic_band_tags`), and
    its time; copies with identical values (band power and current) collapse to one. Copies that
    differ in value are BOTH kept and counted (CLAUDE.md section 11: merged, never first copy
    wins). Recordings are walked in an order set by their content (`_chronic_order_key`), so the
    result -- which samples, and which recording holds each -- does not depend on the order the
    exports arrived. Every recording is kept, emptied if all its readings were repeats, so the
    settings it carries (its band and contact schedules) still reach their readers.

    A band-power value at or above `CHRONIC_INVALID_LSB` is the device's invalid code averaged into
    the reading: set to NaN, which every reader already leaves out; the current at that time is
    kept. Exact zero is excluded under Prasad's analysis policy (decision 487),
    not a claim of physiological invalidity: NaN with current kept, counted in
    ``zero_values``. Both stay stored unchanged.

    Never changes its input: a recording that changes is a shallow copy with new arrays. Returns
    ``(recordings, counts)``; ``counts`` holds ``repeats_removed``, ``conflicting_kept`` (copies
    kept because their values differ), ``readings_under_two_labels`` (side-and-time readings still
    filed under more than one contact pair or band, because two exports' own settings history
    disagree), ``invalid_code_values`` and ``zero_values``.

    THE LEAD THE SIGNAL CAME FROM (the PI, 2026-10-19; decision 488). A reading whose recording's
    `SignalLeadSchedule` names the other lead (`chronic_signal_leads`: the device settings had both
    leads' entries sense that lead) is a copy of that lead's reading, filed under the wrong lead.
    It is filed under the lead it came from (same contact pair and band) and, when its band power
    equals that lead's reading at that time, merged into it: counted once, that lead's current
    kept, the copy's current recorded beside it in ``OtherLeadCurrentMilliAmps`` (NaN elsewhere).
    Equal power alone never moves a reading. Counted: ``other_lead_copies_merged``,
    ``other_lead_current_differs`` (merged copies whose current differs), ``other_lead_power_differs``
    (kept beside that lead's reading under its lead) and ``other_lead_moved_alone`` (no reading of
    that lead at that time: kept under it with own-lead current unknown). A moved-only
    sample retains its source-log currents in the OtherLeadCurrent fields; target-lead
    current is NaN because changing a label does not measure that current.
    Copies kept are handed on in recordings APPENDED after
    the input's, named on the lead they came from (``MovedFromLead`` says which log held them);
    the first ``len(input)`` outputs stay aligned with the input.
    """
    recs = [r for r in (chronic_recordings or [])]
    counts = {"repeats_removed": 0, "conflicting_kept": 0, "readings_under_two_labels": 0,
              "invalid_code_values": 0, "zero_values": 0, "other_lead_copies_merged": 0,
              "other_lead_current_differs": 0, "other_lead_power_differs": 0,
              "other_lead_moved_alone": 0}
    usable = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict) or "Time" not in r or "Data" not in r:
            continue
        t = np.asarray(r.get("Time"), dtype=float)
        d = np.asarray(r.get("Data"), dtype=float)
        if t.ndim != 1 or d.ndim != 2 or d.shape[0] != t.shape[0] or d.shape[1] == 0:
            continue
        usable.append(i)
    order = sorted(usable, key=lambda i: _chronic_order_key(recs[i]))
    seen = {}                 # (hemi, pair, band, t) -> {value row: (recording, row) holding it}
    labels = {}               # (hemi, t) -> set of (pair, band) it is filed under
    keeps, moved = {}, []     # recording -> rows kept in it; copies of the other lead's signal
    for pos, i in enumerate(order):
        r = recs[i]
        t = np.asarray(r.get("Time"), dtype=float)
        d = np.asarray(r.get("Data"), dtype=float)
        n = t.shape[0]
        names = list(r.get("ChannelNames", []) or [])
        cu = str(names[0]).upper() if names else ""
        hemi = "LEFT" if "LEFT" in cu else ("RIGHT" if "RIGHT" in cu else "")
        pairs = chronic_pair_keys(r, t, hemi, "SIDE_" + (hemi or "UNKNOWN"))
        bands = chronic_band_tags(r, t, hemi)
        sigs = chronic_signal_leads(r, t, hemi)
        keep = np.ones(n, dtype=bool)
        for k in range(n):
            val = tuple(_CHRONIC_NAN if np.isnan(value) else value for value in d[k].tolist())
            if sigs[k] != hemi:
                # the other lead's signal filed under this lead (decision 488): handled below
                keep[k] = False
                key = (sigs[k], _pair_on_lead(pairs[k], sigs[k]), bands[k], float(t[k]))
                moved.append((key, val, pos, k, i))
                continue
            key = (hemi, pairs[k], bands[k], float(t[k]))
            got = seen.get(key)
            if got is None:
                seen[key] = {val: (i, k)}
            elif val in got:
                keep[k] = False
                counts["repeats_removed"] += 1
            else:
                got[val] = (i, k)
                counts["conflicting_kept"] += 1
            labels.setdefault((hemi, float(t[k])), set()).add((pairs[k], bands[k]))
        keeps[i] = keep
    # Copies of the other lead's signal, in an order set by content. A copy whose band power equals
    # a reading of the lead it came from is that reading: merged into it, that lead's current kept,
    # the copy's current recorded beside it (`OtherLeadCurrentMilliAmps`) and counted when the two
    # differ. A copy with other band power is kept under its lead and counted; so is a copy with
    # no reading of its lead at that time.
    other_cur = {}            # recording -> {row: the other lead's current}
    extra = {}                # recording -> rows moved to the lead the signal came from
    moved_seen = {}
    for key, val, pos, k, i in sorted(moved, key=lambda m: (m[0], m[1], m[2], m[3])):
        mk = moved_seen.setdefault(key, set())
        if val in mk:
            counts["repeats_removed"] += 1
            continue
        mk.add(val)
        own = seen.get(key) or {}
        same_power = [v for v in own if _same_power(v[0], val[0])]
        if same_power:
            counts["other_lead_copies_merged"] += 1
            if not any(v[1:] == val[1:] for v in same_power):
                counts["other_lead_current_differs"] += 1
            holder = own[min(same_power, key=repr)]
            if len(val) > 1:
                values = other_cur.setdefault(holder[0], {}).setdefault(holder[1], [])
                if not any(_same_power(value, val[1]) for value in values):
                    values.append(val[1])
            continue
        if own:
            counts["other_lead_power_differs"] += 1
        else:
            counts["other_lead_moved_alone"] += 1
        own_key = seen.setdefault(key, {})
        own_key[val] = (i, k)
        if len(val) > 1:
            other_cur.setdefault(i, {}).setdefault(k, []).append(val[1])
        extra.setdefault(i, []).append(k)
        labels.setdefault((key[0], key[3]), set()).add((key[1], key[2]))
    out = list(recs)
    for i in order:
        r = recs[i]
        keep = keeps[i]
        n = keep.shape[0]
        d = np.asarray(r.get("Data"), dtype=float)
        c = _chronic_rows(r, keep, counts)
        c = _with_other_currents(c, r, keep, other_cur.get(i) or {})
        if c is not r:
            out[i] = c
        if extra.get(i):
            rows = np.zeros(n, dtype=bool)
            rows[sorted(extra[i])] = True
            mv = _chronic_rows(r, rows, counts)
            mv = dict(mv) if mv is r else mv
            mv = _with_other_currents(mv, r, rows, other_cur.get(i) or {})
            if d.shape[1] > 1:
                mv["Data"] = np.array(mv["Data"], dtype=float, copy=True)
                mv["Data"][:, 1] = np.nan
            names = list(r.get("ChannelNames", []) or [])
            cu = str(names[0]).upper() if names else ""
            frm, to = ("Left", "Right") if "LEFT" in cu else ("Right", "Left")
            mv["ChannelNames"] = [str(x).replace(frm + "Hemisphere", to + "Hemisphere") for x in names]
            mv["SignalLeadSchedule"] = []
            mv["MovedFromLead"] = frm.upper()
            out.append(mv)
    counts["readings_under_two_labels"] = sum(1 for v in labels.values() if len(v) > 1)
    return out, counts


def native_lsb_by_channel(chronic_recordings, powerdomain_recordings):
    """The device's own Power-Domain streaming and Chronic Timeline band-power series,
grouped by canonical channel, with values unconverted. This vectorises the reference
loop without changing field order. A Power-Domain column has a fixed band centre;
a Chronic recording uses the frequency schedule as a step function. Snap each
distinct centre once. See `_native_lsb_by_channel_loop` for the full contract.
    """
    out = {}

    def _extend(ch, t, y, hz_list, src):
        if not hz_list:
            return                                 # the loop makes no entry for a column with no sample
        d = out.setdefault(ch, {"t": [], "y": [], "center_hz": [], "source": []})
        d["t"].extend(np.asarray(t, dtype=float).tolist())
        d["y"].extend(np.asarray(y, dtype=float).tolist())
        d["center_hz"].extend(hz_list)
        d["source"].extend([src] * len(hz_list))

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
            hz = snap_freq(run_band_hz(r, contact, pd_center))
            col = data[:, pi]
            bad = (missing[:, pi] > 0) | (col >= _POWER_SENTINEL) | (col < 0) | ~np.isfinite(col)
            keep = np.where(~bad)[0]
            if is_zero_run(col[keep]):
                continue                           # not a reading (decision 462)
            _extend(contact, times[keep], col[keep], [hz] * keep.size, "streaming")

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

        col = data[:, 0]
        bad = (col >= _POWER_SENTINEL) | (col < 0) | ~np.isfinite(col)
        keep = np.where(~bad)[0]
        tk = tarr[keep]
        if sched:
            # the loop's `_hz_at`: the last change at or before the sample, else the first change
            starts = np.asarray([c for c, _ in sched], dtype=float)
            idx = np.searchsorted(starts, tk, side="right") - 1
            idx[idx < 0] = 0
            snapped = [snap_freq(h) for _, h in sched]
            hz_list = [snapped[i] for i in idx.tolist()]
        else:
            hz_list = [snap_freq(fallback_hz)] * keep.size
        keys = chronic_pair_keys(r, tk, hemi, key)
        yk = col[keep]
        for k_ in dict.fromkeys(keys):          # first-seen order, as the loop meets them
            sel = [i for i, kk in enumerate(keys) if kk == k_]
            _extend(k_, tk[sel], yk[sel], [hz_list[i] for i in sel], "chronic")

    return out


def _native_lsb_by_channel_loop(chronic_recordings, powerdomain_recordings):
    """THE REFERENCE, one sample at a time: `native_lsb_by_channel` before decision 429, kept so
    the column-at-a-time version is tested against it (DecodeCommon/tests/test_native_lsb_vectorised.py).

    The device's OWN sensed band-power series (Power-Domain streaming + Chronic Timeline),
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
            hz = run_band_hz(r, contact, pd_center)
            col = data[:, pi]
            bad = (missing[:, pi] > 0) | (col >= _POWER_SENTINEL) | (col < 0) | ~np.isfinite(col)
            if is_zero_run(col[~bad]):
                continue                           # not a reading (decision 462)
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
            pair = chronic_pair_keys(r, [float(tarr[i])], hemi, key)[0]
            _push(pair, float(tarr[i]), col[i], _hz_at(float(tarr[i])), "chronic")

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
