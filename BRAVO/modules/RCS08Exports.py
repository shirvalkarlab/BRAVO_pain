"""Local CSV snapshots of stored RCS08 data; never fetch or modify sources."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
from zoneinfo import ZoneInfo

from filelock import FileLock


STREAM_NAMES = {
    "DailyActivity": "daily_activity",
    "DailyReadiness": "daily_readiness",
    "DailyCardiovascularAge": "daily_cardiovascular_age",
    "DailySpo2": "daily_spo2",
    "DailyStress": "daily_stress",
    "HeartRate": "heart_rate",
    "Sleep": "sleep",
}
SAMPLE_STREAMS = {"DailyActivity", "HeartRate", "Sleep"}
IDENTITY_COLUMNS = ["record_index", "day", "start_time_utc", "start_time_local"]
README = """# RCS08 BRAVO data exports

These files contain the latest data stored by BRAVO. They are refreshed after
nightly or manual Sync Data runs. export_manifest.json records the export time,
source hashes and CSV row counts/checksums. Export time is NOT measurement time
or Oura app-sync time. Each CSV is replaced atomically; the manifest is replaced
last. If an interrupted update leaves mismatched hashes, retry the export.

REDCap/rcs08_pain_data.csv is the reviewed daily pain table. It retains ALL rows,
including exclusions, original/corrected values and processing flags. Filter
include_in_analysis for BRAVO's accepted daily observations. survey_start is the
represented survey time; timestamp_source identifies corrections. Standard MPQ
is mpq_standard_0_45, separate from the expanded REDCap 0–54 total.

REDCap/rcs08_stim_testing_dates.csv is the reviewed stimulation-testing calendar
used by BRAVO. It is a local processing source, not a newly fetched REDCap form
or a complete device stimulation-history export. These are calendar dates;
they do not establish within-day change times.

Oura/*.csv contains ALL seven decoded streams currently stored by BRAVO,
before analysis quality-control exclusions. This is not a raw export of every
Oura API endpoint. Each stream has a recording/summary table. Activity, heart
rate and sleep also have sample tables. record_index joins samples to that
stream's recording table within this snapshot (it is not a permanent ID).
Nested descriptors and metadata are flattened with dot-separated column names;
lists, including channel names and state labels, are JSON cells.

Original numeric values and __missing flags are preserved. A missing flag marks
an unavailable value; do not interpret a -1 sentinel as a measurement. The
Metadata.Score value -1 means the decoder had no score for that stream.
Heart Rate is bpm; Heart Rate Variability is ms. State codes index the recording's
Descriptor.StateLabels. Other channel labels and descriptors preserve BRAVO's
decoder naming and source units. SamplingRate is Hz and Duration is seconds.

UTC/local ISO timestamps include offsets; local time is America/Los_Angeles by
default. Numeric timestamp fields (StartTime, BedtimeStart/End and DailySummaryTimestamp)
are Unix seconds. Heart-rate sample times are stored observation timestamps;
activity/sleep sample times follow StartTime + sample_index / SamplingRate.
day is Oura's calendar-day label, which is distinct from an observation timestamp.
Daily summary timestamps are not evidence of when the Oura app synced.
"""


def _plain(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _flatten(value, prefix=""):
    result = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else key
        item = _plain(item)
        if isinstance(item, dict):
            result.update(_flatten(item, name))
        elif isinstance(item, (list, tuple)):
            result[name] = json.dumps(item, allow_nan=False)
        else:
            result[name] = item
    return result


def _iso(epoch, timezone):
    return dt.datetime.fromtimestamp(float(epoch), timezone).isoformat()


def _identity(index, record, timezone):
    return {
        "record_index": index,
        "day": record.get("Metadata", {}).get("DayLabel", ""),
        "start_time_utc": _iso(record["StartTime"], dt.timezone.utc),
        "start_time_local": _iso(record["StartTime"], timezone),
    }


def summary_rows(records, timezone):
    for index, record in enumerate(records):
        yield {
            **_identity(index, record, timezone),
            **_flatten({key: value for key, value in record.items()
                        if key not in {"Data", "Missing", "Time"}}),
        }


def sample_rows(records, timezone):
    """Preserve all stored samples and missing flags, without applying analysis QC."""
    for index, record in enumerate(records):
        channels = record["ChannelNames"]
        values = _plain(record["Data"])
        missing = _plain(record["Missing"])
        explicit_times = record.get("Time")
        if len(missing) != len(values) or (explicit_times is not None and len(explicit_times) != len(values)):
            raise ValueError("Oura sample timestamps/missing flags do not match data length")
        for sample_index, (sample, flags) in enumerate(zip(values, missing)):
            if len(sample) != len(channels) or len(flags) != len(channels):
                raise ValueError("Oura sample width does not match channel names")
            epoch = (explicit_times[sample_index] if explicit_times is not None else
                     float(record["StartTime"]) + sample_index / float(record["SamplingRate"]))
            row = {
                "record_index": index, "sample_index": sample_index,
                "day": record.get("Metadata", {}).get("DayLabel", ""),
                "timestamp_epoch_seconds": epoch,
                "timestamp_utc": _iso(epoch, dt.timezone.utc),
                "timestamp_local": _iso(epoch, timezone),
            }
            for channel, value, flag in zip(channels, sample, flags):
                row[channel] = value
                row[f"{channel}__missing"] = flag
            yield row


def _write_csv(path, rows, fieldnames):
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def _csv_count(text):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("Source CSV has no header")
    return sum(1 for _ in reader)


def write_snapshot(destination, *, reviewed_csv, stim_dates_csv, oura, provenance,
                   timezone="America/Los_Angeles"):
    """Stage a complete bundle before atomically replacing each owned file.

    The manifest is replaced last. A failed publication is raised to the sync
    caller; readers can detect an incomplete generation using manifest hashes.
    Unrelated destination files are never removed.
    """
    destination = Path(destination)
    if not destination.is_dir():
        raise FileNotFoundError("The configured RCS08 export destination must already exist")
    local_zone = ZoneInfo(timezone)
    with FileLock(str(destination / ".rcs08-export.lock"), timeout=0):
        staging = Path(tempfile.mkdtemp(prefix=".rcs08-export-", dir=destination))
        try:
            (staging / "REDCap").mkdir()
            (staging / "Oura").mkdir()
            counts = {}
            for name, content in (("rcs08_pain_data.csv", reviewed_csv),
                                  ("rcs08_stim_testing_dates.csv", stim_dates_csv)):
                relative = f"REDCap/{name}"
                counts[relative] = _csv_count(content)
                (staging / relative).write_text(content, encoding="utf-8")
            unknown = set(oura) - set(STREAM_NAMES)
            if unknown:
                raise ValueError(f"Unmapped stored Oura streams: {sorted(unknown)}")
            for kind, name in STREAM_NAMES.items():
                records = oura.get(kind, [])
                rows = list(summary_rows(records, local_zone))
                fields = IDENTITY_COLUMNS + sorted(set().union(*(row.keys() for row in rows)) - set(IDENTITY_COLUMNS))
                relative = f"Oura/oura_{name}.csv"
                counts[relative] = _write_csv(staging / relative, rows, fields)
                if kind in SAMPLE_STREAMS:
                    fields = ["record_index", "sample_index", "day", "timestamp_epoch_seconds", "timestamp_utc", "timestamp_local"]
                    channels = sorted({channel for record in records for channel in record["ChannelNames"]})
                    fields += [field for channel in channels for field in (channel, f"{channel}__missing")]
                    relative = f"Oura/oura_{name}_samples.csv"
                    counts[relative] = _write_csv(staging / relative, sample_rows(records, local_zone), fields)
            manifest = {
                "exported_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "timezone": timezone, "source": provenance,
                "files": {name: {"rows": count, "sha256": hashlib.sha256((staging / name).read_bytes()).hexdigest()}
                          for name, count in counts.items()},
                "scope": "Stored BRAVO data only; export time is not measurement or app-sync time. REDCap pain includes excluded rows with flags. Stim dates are the reviewed testing calendar. Oura contains all stored decoded streams and samples, before analysis QC; it is not a complete raw Oura API export.",
            }
            (staging / "export_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            (staging / "README.md").write_text(README, encoding="utf-8")
            for name in [*counts, "README.md", "export_manifest.json"]:
                target = destination / name
                target.parent.mkdir(exist_ok=True)
                os.replace(staging / name, target)
            return manifest
        finally:
            shutil.rmtree(staging)


def export_stored_data(participant, destination=None):
    from Server import models
    from modules import Database

    destination = destination or os.environ.get("RCS08_EXPORT_DIRECTORY")
    if not destination:
        raise ValueError("RCS08_EXPORT_DIRECTORY is not configured")
    source = models.SourceFile.objects.filter(owner=participant, type="RCS08SurveyAudit").order_by("-date", "-uid").first()
    if source is None:
        raise ValueError("No stored RCS08 survey audit is available for export")
    audit = Database.loadSourceFile(source.pointer, source.hashed)
    oura_source = models.SourceFile.find(owner=participant, type="OuraRingAPISource")
    if oura_source is None:
        raise ValueError("No stored Oura snapshot is available for export")
    calendar = Path(os.environ.get("RCS08_PROCESSING_RULES", "/run/secrets/rcs08_processing")) / "rcs08_stim_testing_dates.csv"
    return write_snapshot(
        destination, reviewed_csv=audit["reviewed_csv"],
        stim_dates_csv=calendar.read_text(encoding="utf-8-sig"),
        oura=Database.loadSourceFile(oura_source.pointer, oura_source.hashed),
        provenance={"participant": participant.uid, "redcap_audit": source.uid,
                    "redcap_source_hash": source.hashed, "oura_source_hash": oura_source.hashed,
                    "stim_dates_sha256": hashlib.sha256(calendar.read_bytes()).hexdigest()},
        timezone=os.environ.get("RCS08_TIMEZONE", "America/Los_Angeles"),
    )
