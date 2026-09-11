"""Index retained Percept clocks and exact native events without rewriting raw data.

Stored event times remain native. PerceptClock's derived view owns recovery;
this adapter retains source evidence and exact native event representations.
Physical duplicate suppression belongs to the canonical analysis view.
"""
import copy
import hashlib
import json
import io
import math
from pathlib import Path
from contextlib import nullcontext, redirect_stdout, redirect_stderr

from django.db import transaction
from Server import models
from modules import PerceptClock

KEY = "PerceptClock"
EVENT_TYPE = "PatientControllerEvent"


_NATIVE_ORIGINAL = "_BRAVO_CLOCK_ORIGINAL_START"


def _same_source_index(stored, generated):
    """Accept one binary64 storage step only in native alias time scalars.

    MySQL JSON can round these derived values to an adjacent binary64 number.
    Coordinates, anchors, versions, native hashes and all other fields remain
    exact; neither the stored index nor the newly derived index is modified.
    """
    if stored == generated:
        return True
    if not isinstance(stored, dict) or not isinstance(generated, dict):
        return False
    left, right = stored.copy(), generated.copy()
    a, b = left.pop("decoded_start_aliases", None), right.pop("decoded_start_aliases", None)
    if left != right or not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        return False
    for old, new in zip(a, b):
        if not isinstance(old, dict) or not isinstance(new, dict):
            return False
        old, new = old.copy(), new.copy()
        for key in ("decoded_raw", "original_raw", "sample_start_offset_seconds"):
            x, y = PerceptClock.number(old.pop(key, None)), PerceptClock.number(new.pop(key, None))
            if x is None or y is None or (x != y and math.nextafter(x, y) != y):
                return False
        if old != new:
            return False
    return True


def _start_alias(stream, decoded, recording_type, source_kind):
    original = PerceptClock.number(stream.get(_NATIVE_ORIGINAL))
    decoded = PerceptClock.number(decoded)
    position = PerceptClock.coordinate(stream.get("FirstPacketDateTimeBlockId"),
                                       stream.get("FirstPacketDateTimeOffsetInSeconds"))
    if original is None or decoded is None or position is None:
        return None
    return {"decoded_raw": decoded, "original_raw": original,
            "block": position[0], "counter": position[1],
            "sample_start_offset_seconds": decoded - original,
            "recording_type": recording_type, "source_kind": source_kind}


def extract_source_index(payload):
    """Derive scalar aliases with accepted native rules, keeping raw inputs intact.

    Native modality failures are explicit and isolated: no aliases from a failed
    modality are accepted, while valid programmer anchors/event evidence survive.
    Authentication and raw JSON parsing occur outside this helper and stay fatal.
    """
    index = PerceptClock.extract_source(payload)
    index["decoded_start_aliases"] = []
    index["decoded_start_diagnostics"] = []
    native_root = Path(__file__).parent / "MedtronicPercept"
    index["native_start_rule_hashes"] = {
        name: hashlib.sha256((native_root / name).read_bytes()).hexdigest()
        for name in ("Percept.py", "IndefiniteStream.py", "BrainSenseStream.py")}
    for source_kind, output_key, extractor_name, recording_type in (
        ("BrainSenseTimeDomain", "StreamingTD", "extractTimeDomainStreamingData", "MedtronicBrainSenseTimeDomain"),
        ("BrainSenseLfp", "StreamingPower", "extractPowerDomainStreamingData", "MedtronicBrainSensePowerDomain"),
        ("IndefiniteStreaming", "IndefiniteStream", "extractIndefiniteStreaming", "MedtronicIndefiniteStream"),
    ):
        if not isinstance(payload, dict) or source_kind not in payload:
            continue
        diagnostic = {"source_kind": source_kind, "recording_type": recording_type}
        log = io.StringIO()
        try:
            # Mark before native extraction; markers survive deep copies, drops,
            # tick reordering and timestamp alignment. Never pair by list index.
            streams = copy.deepcopy(payload[source_kind])
            for stream in streams:
                stream[_NATIVE_ORIGINAL] = PerceptClock.utc(stream.get("FirstPacketDateTime"))
            from modules.MedtronicPercept import Percept, IndefiniteStream
            with redirect_stdout(log), redirect_stderr(log):
                data = getattr(Percept, extractor_name)({source_kind: streams}, {})
                decoded = data.get(output_key, [])
                candidates = []
                if source_kind == "IndefiniteStreaming":
                    # The saver groups by exact native date and repeatedly sets
                    # StartTime; the last member governs its normalized tick.
                    groups = {}
                    for stream in decoded:
                        groups.setdefault(stream["FirstPacketDateTime"], []).append(stream)
                    for group in groups.values():
                        recordings = IndefiniteStream.saveIndefiniteStreams(group)
                        if len(recordings) != 1:
                            raise ValueError("Indefinite native group is not unique")
                        candidates.append(_start_alias(group[-1], recordings[0]["StartTime"],
                                                       recording_type, source_kind))
                else:
                    candidates = [_start_alias(stream, stream["FirstPacketDateTime"],
                                               recording_type, source_kind) for stream in decoded]
            aliases = [alias for alias in candidates if alias is not None]
            index["decoded_start_aliases"].extend(aliases)
            diagnostic.update(status="indexed", decoded_streams=len(decoded),
                              aliases=len(aliases), unresolved_coordinates=len(candidates) - len(aliases))
        except Exception as exc:
            # Do not retain exception text, stream data, or printed native source
            # fragments in the scalar index. No partial modality aliases survive.
            diagnostic.update(status="native_decode_failed", exception_type=type(exc).__name__, aliases=0)
        diagnostic["native_diagnostic_lines"] = len(log.getvalue().splitlines())
        index["decoded_start_diagnostics"].append(diagnostic)
    index["decoded_start_aliases"] = sorted(index["decoded_start_aliases"],
        key=lambda alias: (alias["recording_type"], alias["decoded_raw"], alias["block"],
                           alias["counter"], alias["sample_start_offset_seconds"]))
    return index


def stamp_source(source, payload):
    """Set a derived index on the source object; its caller owns persistence."""
    index = extract_source_index(payload)
    changed = not _same_source_index((source.metadata or {}).get(KEY), index)
    if changed:
        source.metadata = {**(source.metadata or {}), KEY: index}
    return changed


def _block_key(device_uid, hemisphere, block, date):
    identity = PerceptClock.snapshot_identity(device_uid, hemisphere, block)
    if identity is not None:
        return ("physical", identity)
    # Incomplete clocks do not justify collapsing unrelated snapshots. Preserve
    # the complete native metadata and date, rather than treating None as a key.
    encoded = json.dumps([str(device_uid), hemisphere, date, block], sort_keys=True,
                         separators=(",", ":"), allow_nan=True)
    return ("native", hashlib.sha256(encoded.encode()).hexdigest())


def _native_key(device_uid, name, date, metadata):
    """Retain all native metadata except separately compared spectral values."""
    fields = {hemisphere: {key: value for key, value in block.items()
                          if key not in ("Frequency", "FFTBinData")}
              if isinstance(block, dict) else block
              for hemisphere, block in metadata.items()}
    encoded = json.dumps([str(device_uid), name, date, fields], sort_keys=True,
                         separators=(",", ":"), allow_nan=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _native_equivalent(left, right):
    return (set(left) == set(right)
            and all(PerceptClock.spectra_equivalent(left[h], right[h]) for h in left))


def _remember_physical(physical, key, block, alignment=None):
    group = physical.setdefault(key, {"copies": [], "alignments": set()})
    if any(not PerceptClock.spectra_equivalent(block, other) for other in group["copies"]):
        raise ValueError("Physical PSD copies have conflicting spectral values")
    group["copies"].append(block)
    if alignment is not None:
        group["alignments"].add(alignment)
    if len(group["alignments"]) > 1:
        raise ValueError("Physical PSD copies have conflicting manual alignment")
    return group


def _native_entry(native, key, metadata):
    return next((entry for entry in native.get(key, [])
                 if all(_native_equivalent(metadata, copy) for copy in entry["copies"])), None)


def _existing_keys(participant):
    physical, native = {}, {}
    records = models.Recording.find_all(source__owner=participant, type=EVENT_TYPE)
    for record in sorted(records.select_related("source"), key=lambda row: str(row.uid)):
        source = record.source
        if (source.metadata or {}).get("AnalysisExclusion"):
            continue
        device = (source.metadata or {}).get("Device")
        if not device:
            continue
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        alignment = PerceptClock.number(getattr(record, "adjusted_alignment", 0))
        if alignment is None:
            raise ValueError("Physical PSD has invalid manual alignment")
        for hemisphere, block in metadata.items():
            if PerceptClock.valid_spectrum(block):
                _remember_physical(physical, _block_key(device, hemisphere, block, record.date),
                                   block, alignment)
        key = _native_key(device, record.name, record.date, metadata)
        entry = _native_entry(native, key, metadata)
        if entry is None:
            entry = {"record": record, "copies": []}
            native.setdefault(key, []).append(entry)
        entry["copies"].append(metadata)
    return physical, native


def _matching_annotation(source, event, device_uid, native_key, entry, annotations):
    candidates = models.DBSEvent.find_all(source__owner=source.owner,
                                          type=EVENT_TYPE, name=event["name"],
                                          date=event["date"])
    for row in candidates:
        # Reserve empty annotations during dry-run just as apply would.
        if any(key != id(entry) and state["row"] is not None
               and state["row"].uid == row.uid for key, state in annotations.items()):
            continue
        if (row.source.metadata or {}).get("AnalysisExclusion"):
            continue
        if (row.source.uid != source.uid
                and (row.source.metadata or {}).get("Device") != device_uid):
            continue
        linked = list(row.data.all())
        if all(not (record.source.metadata or {}).get("AnalysisExclusion")
               and isinstance(record.metadata, dict)
               and _native_key((record.source.metadata or {}).get("Device")
                               or (device_uid if record.source.uid == source.uid else None),
                               record.name, record.date, record.metadata) == native_key
               and all(_native_equivalent(record.metadata, other) for other in entry["copies"])
               for record in linked):
            return row, {str(record.uid) for record in linked}
    return None, set()


def _reconcile_events(source, events, device_uid, inventory, *, apply, annotations=None):
    """Preserve exact native events; physical dedup belongs to canonical analysis."""
    from modules import RCS08DataPolicy
    annotations = {} if annotations is None else annotations
    physical, native = inventory
    result = {"events_examined": len(events), "blocks_examined": 0,
              "duplicate_blocks": 0, "physical_missing_blocks": 0,
              "native_representations_created": 0, "annotations_created": 0,
              "native_representations_linked": 0, "preimplant_events_guarded": 0}
    for event in events:
        if (RCS08DataPolicy.applies_to(source.owner)
                and event["date"] < RCS08DataPolicy.IMPLANT_DAY):
            result["preimplant_events_guarded"] += 1
            continue
        metadata, groups, shifts = {}, [], set()
        for hemisphere, block in event["metadata"].items():
            if not PerceptClock.valid_spectrum(block):
                continue
            metadata[hemisphere] = copy.deepcopy(block)
            result["blocks_examined"] += 1
            key = _block_key(device_uid, hemisphere, block, event["date"])
            result["duplicate_blocks" if key in physical else "physical_missing_blocks"] += 1
            group = _remember_physical(physical, key, block)
            groups.append(group)
            shifts.update(group["alignments"])
        if not metadata:
            continue
        if len(shifts) > 1:
            raise ValueError("Native event hemispheres have conflicting manual alignment")
        alignment = next(iter(shifts), 0.0)
        for group in groups:
            group["alignments"].add(alignment)
        native_key = _native_key(device_uid, event["name"], event["date"], metadata)
        entry = _native_entry(native, native_key, metadata)
        if entry is None:
            result["native_representations_created"] += 1
            recording = object()
            if apply:
                recording = models.Recording(source=source, type=EVENT_TYPE,
                                             name=event["name"], date=event["date"],
                                             metadata=metadata, adjusted_alignment=alignment)
                recording.save()
            entry = {"record": recording, "copies": []}
            native.setdefault(native_key, []).append(entry)
        entry["copies"].append(metadata)
        recording = entry["record"]
        if id(entry) not in annotations:
            annotation, linked = _matching_annotation(source, event, device_uid,
                                                       native_key, entry, annotations)
            if annotation is None:
                result["annotations_created"] += 1
                if apply:
                    annotation = models.DBSEvent(source=source, type=EVENT_TYPE,
                                                 name=event["name"], date=event["date"])
                    annotation.save()
            annotations[id(entry)] = {"row": annotation, "linked": linked}
        state = annotations[id(entry)]
        # Admitted existing links already represent the same native payload.
        if not state["linked"]:
            state["linked"].add(str(getattr(recording, "uid", id(recording))))
            result["native_representations_linked"] += 1
            if apply:
                state["row"].data.add(recording)
    return result


def save_patient_event_psds(source, events, device_uid):
    """Future-import hook; caller supplies events extracted before JSON decoding."""
    with transaction.atomic():
        models.Participant.objects.select_for_update().get(uid=source.owner.uid)
        return _reconcile_events(source, events, device_uid,
                                 _existing_keys(source.owner), apply=True)


def index_participant(participant, *, apply=False):
    """Dry-run or atomically index only this participant's eligible retained JSON.

    Authenticate every raw file before making any mutation. A missing/corrupt
    source raises rather than becoming a partially indexed success.
    """
    from modules import AnalysisData, DataCurator, ReportCache
    sources = list(AnalysisData.eligible_source_files(participant)
                   .filter(type="MedtronicJSON").order_by("uid"))
    prepared = []
    for source in sources:
        if str(source.owner.uid) != str(participant.uid):
            raise ValueError("Clock source does not belong to the requested participant")
        device = (source.metadata or {}).get("Device")
        if not device or models.DBSDevice.find(uid=device, owner=participant) is None:
            raise ValueError("Clock source has no authorized device identity")
        payload = json.loads(DataCurator.loadCacheFile(source))
        prepared.append((source, device, source.hashed, source.pointer,
                         extract_source_index(payload),
                         PerceptClock.extract_event_recordings(payload)))
    result = {"apply": apply, "participant_uid": str(participant.uid),
              "sources_examined": len(sources), "source_indexes_changed": 0,
              "events_examined": 0, "blocks_examined": 0,
              "duplicate_blocks": 0, "physical_missing_blocks": 0,
              "native_representations_created": 0, "annotations_created": 0,
              "native_representations_linked": 0,
              "preimplant_events_guarded": 0,
              "raw_source_hashes_unchanged": True,
              "existing_recordings_unchanged": True, "clock_version": PerceptClock.VERSION}
    with transaction.atomic() if apply else nullcontext():
        if apply:
            models.Participant.objects.select_for_update().get(uid=participant.uid)
        seen, annotations = _existing_keys(participant), {}
        for source, device, expected_hash, expected_pointer, index, events in prepared:
            if apply:
                source.refresh_from_db()
                if (source.hashed != expected_hash or source.pointer != expected_pointer
                        or str(source.owner.uid) != str(participant.uid)
                        or (source.metadata or {}).get("Device") != device
                        or (source.metadata or {}).get("AnalysisExclusion")):
                    raise RuntimeError("Clock source changed during indexing; retry from current inputs")
            original_hash, original_pointer = source.hashed, source.pointer
            if not _same_source_index((source.metadata or {}).get(KEY), index):
                result["source_indexes_changed"] += 1
                if apply:
                    source.metadata = {**(source.metadata or {}), KEY: index}
                    source.save(update_fields=["metadata"])
            counts = _reconcile_events(source, events, device, seen, apply=apply,
                                       annotations=annotations)
            for key, value in counts.items():
                result[key] += value
            if source.hashed != original_hash or source.pointer != original_pointer:
                raise RuntimeError("Clock indexing changed a retained raw source identity")
        if apply and (result["source_indexes_changed"] or result["physical_missing_blocks"]
                      or result["native_representations_linked"]):
            ReportCache.invalidate(neural=True)
    return result
