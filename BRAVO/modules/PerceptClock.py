"""Recover derived Percept times from programmer anchors and device counters.

Raw exported wall times are not stable identifiers. This module never edits them,
uses no outcomes, and never extrapolates across an unobserved clock boundary.
Only derived start/event coordinates are mapped; samples are not resampled.
"""
from bisect import bisect_left
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from itertools import combinations
import hashlib
import json
import math
import struct

VERSION = "percept-programmer-clock-v1"
MAX_INTERCEPT_CHANGE_SECONDS = 120.0
MIN_UTC = 1420070400.0  # Same valid-era convention as programmer session extraction.


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        result = parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None
    return result if result is not None and result >= MIN_UTC else None


def coordinate(block, counter):
    block, counter = number(block), number(counter)
    if block is None or counter is None or block <= 0 or counter < 0 or not block.is_integer():
        return None
    return int(block), counter


def extract_source(payload):
    """Compact derived index; caller persists it beside the authenticated raw hash."""
    result = {"version": VERSION, "anchors": [], "starts": []}
    if not isinstance(payload, dict):
        return result
    start, end = utc(payload.get("SessionDate")), utc(payload.get("SessionEndDate"))
    # Contradictory root bounds cannot establish programmer clock anchors.
    if start is not None and end is not None and not 0 <= end - start < 8 * 3600:
        start = end = None
    device = payload.get("DeviceInformation")
    if isinstance(device, dict):
        for phase, programmer in (("Initial", start), ("Final", end)):
            info = device.get(phase)
            if not isinstance(info, dict):
                continue
            pos = coordinate(info.get("DeviceDateTimeBlockId"), info.get("DeviceDateTimeOffsetInSeconds"))
            ins = utc(info.get("DeviceDateTime"))
            if pos is not None and programmer is not None and ins is not None:
                result["anchors"].append({"phase": phase, "block": pos[0], "counter": pos[1],
                                          "utc": programmer, "ins_utc": ins})
    starts = set()
    pending = [payload]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            raw = utc(item.get("FirstPacketDateTime"))
            pos = coordinate(item.get("FirstPacketDateTimeBlockId"), item.get("FirstPacketDateTimeOffsetInSeconds"))
            if raw is not None and pos is not None:
                starts.add((raw, *pos))
            pending.extend(value for value in item.values() if isinstance(value, (dict, list)))
        elif isinstance(item, list):
            pending.extend(value for value in item if isinstance(value, (dict, list)))
    result["starts"] = [{"raw": raw, "block": block, "counter": counter}
                         for raw, block, counter in sorted(starts)]
    return result


def valid_spectrum(block):
    """Validate structure without replacing the downstream per-bin PSD quality filter."""
    if not isinstance(block, dict):
        return False
    freq, power = block.get("Frequency"), block.get("FFTBinData")
    if not (isinstance(freq, (list, tuple)) and isinstance(power, (list, tuple))
            and len(freq) > 0 and len(freq) == len(power)):
        return False
    for value in (*freq, *power):
        if isinstance(value, bool):
            return False
        try:
            float(value)
        except (ValueError, TypeError, OverflowError):
            return False
    return True


def snapshot_identity(device, hemisphere, block):
    """Physical coordinates; callers must verify spectra before merging copies.

    Export/storage JSON round trips can change spectral values by a few binary64
    steps. Payloads therefore do not define identity; spectra_equivalent is the
    mandatory compatibility check for records with the same coordinates.
    """
    if not device or not valid_spectrum(block):
        return None
    pos = coordinate(block.get("DateTimeBlockId"), block.get("DateTimeOffsetInSeconds"))
    if pos is None:
        return None
    values = [str(device), str(hemisphere), *pos]
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def spectra_equivalent(left_block, right_block):
    """Allow at most four representable binary64 steps per bin, without rounding.

    This is storage-representation tolerance, not signal smoothing. NaNs match
    NaNs, infinities match only the same sign, and signed zeros are equivalent.
    Nonfinite bins remain intact for the existing downstream per-bin PSD QC.
    """
    if not valid_spectrum(left_block) or not valid_spectrum(right_block):
        return False
    sign = 1 << 63

    def ordered(value):
        bits = struct.unpack(">Q", struct.pack(">d", value))[0]
        return sign - (bits & (sign - 1)) if bits & sign else sign + bits

    for key in ("Frequency", "FFTBinData"):
        if len(left_block[key]) != len(right_block[key]):
            return False
        for left, right in zip(left_block[key], right_block[key]):
            left, right = float(left), float(right)
            if left == right or (math.isnan(left) and math.isnan(right)):
                continue
            if not math.isfinite(left) or not math.isfinite(right):
                return False
            if abs(ordered(left) - ordered(right)) > 4:
                return False
    return True


def extract_event_recordings(payload):
    """Preserve original PSD metadata for import/reconciliation, never re-date it."""
    if not isinstance(payload, dict):
        return []
    diagnostic = payload.get("DiagnosticData", {})
    if not isinstance(diagnostic, dict):
        return []
    events = diagnostic.get("LfpFrequencySnapshotEvents", [])
    if not isinstance(events, list):
        return []
    result = []
    for event in events:
        if not isinstance(event, dict):
            continue
        date = utc(event.get("DateTime"))
        snapshots = event.get("LfpFrequencySnapshotEvents")
        if date is None or not isinstance(snapshots, dict):
            continue
        metadata = {key: deepcopy(value) for key, value in snapshots.items() if valid_spectrum(value)}
        if metadata:
            result.append({"name": str(event.get("EventName") or "Event"), "date": date,
                           "metadata": metadata})
    return result


def build_index(sources):
    """Build participant-scoped clock maps, preferring Final over Initial per source.

    Sources are {uid, device, index}. Device identity is the application's scoped
    device UID, never a patient identifier. A nonmonotonic counter makes its block
    ambiguous; such blocks cannot be corrected by this model.
    """
    groups = defaultdict(list)
    continuity = defaultdict(list)
    for source in sources:
        device, data = source.get("device"), source.get("index")
        if not device or not isinstance(data, dict) or data.get("version") != VERSION:
            continue
        valid = []
        for anchor in data.get("anchors", []):
            if not isinstance(anchor, dict):
                continue
            pos = coordinate(anchor.get("block"), anchor.get("counter"))
            when = number(anchor.get("utc"))
            if pos is not None and when is not None and when >= MIN_UTC and anchor.get("phase") in ("Initial", "Final"):
                valid.append({**anchor, "block": pos[0], "counter": pos[1], "utc": when,
                              "source_uid": str(source.get("uid", ""))})
        for anchor in valid:
            continuity[(str(device), anchor["block"])].append(anchor)
        finals = [anchor for anchor in valid if anchor["phase"] == "Final"]
        for anchor in finals or valid:
            groups[(str(device), anchor["block"])].append(anchor)
    result = {"groups": {}, "invalid": set()}
    for key, anchors in groups.items():
        unique = {}
        for anchor in sorted(anchors, key=lambda a: (a["utc"], a["source_uid"])):
            unique.setdefault((anchor["counter"], anchor["utc"]), anchor)
        ordered = sorted(unique.values(), key=lambda a: a["utc"])
        all_anchors = sorted(continuity[key], key=lambda a: (a["utc"], a["counter"]))
        if any(b["counter"] < a["counter"] or (b["counter"] == a["counter"] and b["utc"] != a["utc"])
               for a, b in zip(all_anchors, all_anchors[1:])) or any(
                b["counter"] == a["counter"] and b["utc"] != a["utc"]
                for a, b in zip(ordered, ordered[1:])):
            result["invalid"].add(key)
        result["groups"][key] = sorted(ordered, key=lambda a: a["counter"])
    return result


def recover(index, device, block, counter):
    """Piecewise clock mapping; unresolved values are excluded, not guessed.

    The 120-second discontinuity guard is a conservative consistency check, not a
    confidence interval. It exceeds observed session acquisition skew, while
    rejecting material clock jumps. No extrapolation outside observed anchors.
    """
    pos = coordinate(block, counter)
    base = {"method": VERSION, "t": None}
    if not device or pos is None:
        return {**base, "status": "missing_clock_coordinates"}
    key = str(device), pos[0]
    if key in index["invalid"]:
        return {**base, "status": "nonmonotonic_clock_block"}
    anchors = index["groups"].get(key, [])
    if not anchors:
        return {**base, "status": "missing_programmer_anchor"}
    i = bisect_left([a["counter"] for a in anchors], pos[1])
    if i < len(anchors) and anchors[i]["counter"] == pos[1]:
        a = anchors[i]
        return {**base, "status": "anchored", "t": a["utc"], "anchor_sources": [a["source_uid"]],
                "anchor_span_seconds": 0.0, "intercept_change_seconds": 0.0}
    if i == 0 or i == len(anchors):
        return {**base, "status": "outside_observed_clock_range"}
    a, b = anchors[i - 1], anchors[i]
    span = b["counter"] - a["counter"]
    change = (b["utc"] - b["counter"]) - (a["utc"] - a["counter"])
    if abs(change) > MAX_INTERCEPT_CHANGE_SECONDS:
        return {**base, "status": "clock_anchor_discontinuity", "intercept_change_seconds": change}
    t = a["utc"] + (pos[1] - a["counter"]) / span * (b["utc"] - a["utc"])
    return {**base, "status": "interpolated", "t": t,
            "anchor_sources": [a["source_uid"], b["source_uid"]],
            "anchor_span_seconds": span, "intercept_change_seconds": change}


def recover_start(index, source, raw_time):
    """Locate decoded StartTime's source coordinate without guessing a wall offset."""
    data = source.get("index") or {}
    positions = {(entry["block"], entry["counter"]) for entry in data.get("starts", [])
                 if abs(entry["raw"] - raw_time) < 0.001}
    if not positions:
        return {"method": VERSION, "status": "missing_start_coordinates", "t": None}
    if len(positions) != 1:
        return {"method": VERSION, "status": "conflicting_start_coordinates", "t": None}
    block, counter = positions.pop()
    return {**recover(index, source.get("device"), block, counter), "block": block, "counter": counter}


def canonical_snapshots(records, sources):
    """One physical PSD, one clock decision; manual shifts are applied exactly once.

    Input records are plain dictionaries; this is shared by ORM-backed consumers
    and portable tests. Duplicate records with incompatible manual shifts or
    explicit SenseIDs are an error, never an order-dependent scientific choice.
    """
    source_map = {str(source["uid"]): source for source in sources}
    index = build_index(sources)
    grouped = defaultdict(list)
    counts = defaultdict(int)
    for record in records:
        source = source_map.get(str(record.get("source_uid")), {})
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            counts["invalid_metadata"] += 1
            continue
        for hemisphere, spectrum in metadata.items():
            if not valid_spectrum(spectrum):
                continue
            counts["exported_psd_copies"] += 1
            identity = snapshot_identity(source.get("device"), hemisphere, spectrum)
            if identity is None:
                counts["missing_clock_coordinates"] += 1
                continue
            grouped[identity].append((record, source, hemisphere, spectrum))
    rows = []
    counts["physical_psds"] = len(grouped)
    counts["duplicate_export_copies"] = sum(len(group) - 1 for group in grouped.values())
    for identity, group in sorted(grouped.items()):
        # A tolerance relation is not transitive: checking only a representative
        # could merge endpoints eight steps apart through a four-step midpoint.
        if any(not spectra_equivalent(left[3], right[3]) for left, right in combinations(group, 2)):
            raise ValueError("Physical PSD copies have conflicting spectral payloads")
        shifts = {number(item[0].get("alignment", 0)) for item in group}
        sense_ids = {str(item[3]["SenseID"]) for item in group if item[3].get("SenseID")}
        if None in shifts or len(shifts) != 1 or len(sense_ids) > 1:
            raise ValueError("Physical PSD copies have conflicting alignment or sensing metadata")
        record, source, hemisphere, spectrum = min(group, key=lambda item: str(item[0].get("uid", "")))
        timing = recover(index, source.get("device"), spectrum["DateTimeBlockId"], spectrum["DateTimeOffsetInSeconds"])
        counts[timing["status"]] += 1
        if timing["t"] is None:
            continue
        labels = sorted({str(item[0].get("name") or "Event") for item in group})
        names = [name for name in labels if name.lower() != "streaming"] or labels
        rows.append({"t": timing["t"] + next(iter(shifts)), "name": names[0], "names": labels,
                     "hemisphere": hemisphere, "spectrum": spectrum,
                     "sense_id": next(iter(sense_ids), None), "identity": identity,
                     "provenance": {**timing, "manual_alignment_seconds": next(iter(shifts)),
                                    "raw_times": sorted({str(item[3].get("DateTime")) for item in group}),
                                    "source_uids": sorted({str(item[1]["uid"]) for item in group}),
                                    "recording_uids": sorted({str(item[0].get("uid")) for item in group})}})
    counts["recovered_physical_psds"] = len(rows)
    return rows, dict(counts)
