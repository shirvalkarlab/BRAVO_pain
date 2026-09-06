"""Latest eligible observed HR/HRV time, computed only when publishing a snapshot."""
import datetime as dt
import hashlib
import math
import time

import numpy as np
from Server import models
from modules.OURA import QualityControl

KEY = "OuraMeasurementFreshness"
VERSION = "oura-measurement-freshness-1"
SOURCE = "Oura timed heart-rate / HRV measurements"
SEMANTICS = "Latest valid observed HR or HRV sample after the existing Oura QC rules; not app-sync time, BRAVO fetch time or a daily-summary date."


def unavailable(reason):
    return {"available": False, "value": None, "precision": None, "timezone": "America/Los_Angeles",
            "source": SOURCE, "semantics": SEMANTICS, "reason": reason, "partial": False}


def policy_hash():
    return hashlib.sha256(QualityControl.POLICY_PATH.read_bytes()).hexdigest()


def summarize(data, participant_uid, source_hash, *, now=None):
    """Read merged raw data already in memory, preserving mask and native clocks."""
    now = time.time() if now is None else now
    latest, channels, invalid = [], set(), 0
    for stream in ("HeartRate", "Sleep"):
        for row in data.get(stream, []):
            try:
                if "Missing" not in row or (stream == "HeartRate" and "Time" not in row):
                    raise ValueError("Missing mask or exact heart-rate timestamps")
                cleaned, _ = QualityControl.apply_quality_control({stream: [row]})
                for observed in cleaned[stream]:
                    names = observed["ChannelNames"]
                    stamps = QualityControl.sample_times(observed)
                    values = np.asarray(observed["Data"], dtype=float)
                    missing = np.asarray(observed["Missing"], dtype=bool)
                    if values.shape != (len(stamps), len(names)) or missing.shape != values.shape:
                        raise ValueError("Mismatched sample/channel/mask shape")
                    for column, name in enumerate(names):
                        if name not in ("Heart Rate", "Heart Rate Variability", "HRV"):
                            continue
                        valid = (np.isfinite(stamps) & (stamps > 0) & (stamps <= now)
                                 & ~missing[:, column] & np.isfinite(values[:, column])
                                 & (values[:, column] >= (1 if name == "Heart Rate" else 0)))
                        if valid.any():
                            latest.append(float(stamps[valid].max()))
                            channels.add(stream + ": " + name)
            except (ValueError, TypeError, KeyError, IndexError):
                invalid += 1
    result = {**unavailable("No eligible timed HR or HRV measurement is present in the stored snapshot."),
              "version": VERSION, "participant_id": str(participant_uid), "source_hash": source_hash,
              "qc_version": QualityControl.VERSION,
              "qc_sha256": policy_hash(),
              "coverage": {"channels": sorted(channels), "invalid_records": invalid}}
    if latest:
        result.update(available=True, value=dt.datetime.fromtimestamp(max(latest), dt.timezone.utc).isoformat(),
                      precision="second", reason=None)
    if invalid:
        result.update(partial=True, reason="Some HR/HRV records have invalid clocks, channels or missing masks; the latest valid measurement is shown when available.")
    return result


def read_cached(participant, now):
    """Status reads one metadata field; no snapshot arrays or network access."""
    source = models.SourceFile.find(owner=participant, type="OuraRingAPISource")
    snapshot = source.metadata.get(KEY) if source else None
    if (source is None or str(source.owner_id) != str(participant.uid) or not isinstance(snapshot, dict)
            or snapshot.get("version") != VERSION or snapshot.get("participant_id") != str(participant.uid)
            or snapshot.get("source_hash") != source.hashed or snapshot.get("qc_version") != QualityControl.VERSION
            or snapshot.get("qc_sha256") != policy_hash()):
        return unavailable("Latest measurement metadata is not yet published for the current Oura snapshot.")
    result = {**unavailable(snapshot.get("reason")), "partial": bool(snapshot.get("partial")),
              "coverage": snapshot.get("coverage", {})}
    if snapshot.get("available") is not True:
        return result
    try:
        stamp = dt.datetime.fromisoformat(snapshot["value"])
        if stamp.tzinfo is None or not math.isfinite(stamp.timestamp()) or not 0 < stamp.timestamp() <= now:
            raise ValueError("Invalid measurement time")
    except (ValueError, TypeError, KeyError, OverflowError):
        return unavailable("The saved measurement timestamp is invalid.")
    return {**result, "available": True, "value": stamp.isoformat(), "precision": "second"}


def initialize_metadata(participant, *, now=None):
    """Index the existing snapshot once without fetching or changing any samples."""
    from modules import Database
    source = models.SourceFile.find(owner=participant, type="OuraRingAPISource")
    if source is None or str(source.owner_id) != str(participant.uid):
        raise ValueError("No existing Oura snapshot is available")
    data = Database.loadSourceFile(source.pointer, source.hashed)
    snapshot = summarize(data, participant.uid, source.hashed, now=now)
    source.metadata = {**source.metadata, KEY: snapshot}
    source.save(update_fields=["metadata"])
    return snapshot
