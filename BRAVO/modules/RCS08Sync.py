"""Idempotent RCS08 ingestion for the local BRAVO appliance.

The module deliberately keeps host credentials outside the database and source
tree.  A management command supplies read-only credential-file paths and a
read-only Dropbox mount through environment variables.
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import hashlib
import hmac
import io
import json
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import uuid4

import requests
from django.db import transaction
from filelock import FileLock, Timeout

from Server import models
from modules import DataCurator, Database
from modules.OURA import DataManager as OuraDataManager


STORAGE_PATH = Path(os.environ.get("DATASERVER_PATH", "/usr/src/BRAVO/BRAVOStorage"))
PARTICIPANT_NAME = os.environ.get("RCS08_PARTICIPANT", "RCS08")
NEURAL_FOLDER = os.environ.get("RCS08_NEURAL_FOLDER", "/data/rcs08-neural")
REDCAP_SECRET_FILE = os.environ.get(
    "RCS08_REDCAP_CREDENTIALS_FILE", "/run/secrets/rcs08_redcap.json"
)
OURA_SECRET_FILE = os.environ.get(
    "RCS08_OURA_CREDENTIALS_FILE", "/run/secrets/rcs08_oura.json"
)
OURA_START_DATE = os.environ.get("RCS08_OURA_START_DATE", "2025-01-01")
LOCAL_TIMEZONE = ZoneInfo(os.environ.get("RCS08_TIMEZONE", "America/Los_Angeles"))
HASH_KEY = os.environ.get("DATASERVER_HASHKEY", "")
TIMESTAMP_CORRECTIONS_FILE = os.environ.get(
    "RCS08_TIMESTAMP_CORRECTIONS_FILE",
    str(Path(__file__).resolve().parents[1] / "config" / "rcs08_timestamp_corrections.csv"),
)

REDCAP_INSTRUMENT = "stage_1_daily_surveys_vasnrsmpq"
REDCAP_TIMESTAMP = "date_time_s1_daily"
REDCAP_FORM_NAME = "RCS08 Daily PRO (REDCap)"
REDCAP_RECORD_TYPE = "REDCap API Sync"
REDCAP_METRICS = {
    "nrs": "pain_nrs_s1_daily",
    "vas": "pain_vas_s1_daily",
    "left_leg_vas": "left_leg_vas_s1_daily",
    "back_vas": "back_vas_s1_daily",
    "relief": "relief_vas_s1_daily",
    "mpq_aff": [
        "tiring_exhausting_s1_daily",
        "sickening_s1_daily",
        "fearful_s1_daily",
        "cruel_punishing_s1_daily",
    ],
    "mpq_sen": [
        "throbbing_s1_daily",
        "shooting_s1_daily",
        "stabbing_s1_daily",
        "sharp_s1_daily",
        "cramping_s1_daily",
        "gnawing_s1_daily",
        "hot_burning_s1_daily",
        "aching_s1_daily",
        "heavy_s1_daily",
        "tender_s1_daily",
        "splitting_s1_daily",
    ],
    "firey": "firey_s1_daily",
    "tingly": "tingly_s1_daily",
    "electrocuting": "electrocuting_s1_daily",
    "mpq_sum": "mpq_s1_daily",
}
REDCAP_LABELS = {
    "nrs": "NRS (0-10)",
    "vas": "VAS Pain Intensity (0-100)",
    "left_leg_vas": "Left Leg VAS (0-100)",
    "back_vas": "Back VAS (0-100)",
    "relief": "Pain Relief VAS (0-100)",
    "mpq_aff": "MPQ Affective",
    "mpq_sen": "MPQ Sensory",
    "firey": "Fiery",
    "tingly": "Tingly",
    "electrocuting": "Electrocuting",
    "mpq_sum": "MPQ Expanded 18-item Total",
}
REDCAP_RANGES = {
    "nrs": (0, 10),
    "vas": (0, 100),
    "left_leg_vas": (0, 100),
    "back_vas": (0, 100),
    "relief": (0, 100),
    "mpq_aff": (0, 12),
    "mpq_sen": (0, 33),
    "firey": (0, 3),
    "tingly": (0, 3),
    "electrocuting": (0, 3),
    "mpq_sum": (0, 54),
}

OURA_KEYS = (
    "DailyActivity",
    "DailyReadiness",
    "DailyCardiovascularAge",
    "DailySpo2",
    "DailyStress",
    "HeartRate",
    "Sleep",
)


class SyncError(RuntimeError):
    """An expected, user-actionable sync failure."""


def _load_secret(path: str, required_keys: tuple[str, ...]) -> dict:
    secret_path = Path(path)
    if not secret_path.is_file():
        raise SyncError(f"credential file is missing: {secret_path}")
    try:
        payload = json.loads(secret_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"credential file is unreadable: {secret_path}") from exc
    missing = [key for key in required_keys if not payload.get(key)]
    if missing:
        raise SyncError(f"credential file {secret_path} is missing keys: {', '.join(missing)}")
    return payload


def resolve_participant(*, create: bool = False):
    participant = models.Participant.find(name=PARTICIPANT_NAME)
    if participant:
        return participant
    # Published audit sources preserve the association when a display name changes.
    owners = list(models.SourceFile.objects.filter(type="RCS08SurveyAudit", owner__isnull=False)
                  .values_list("owner_id", flat=True).distinct()[:2])
    if len(owners) > 1:
        raise SyncError("Multiple participants own RCS08 survey audits; resolve the association before syncing")
    if owners:
        participant = models.Participant.find(uid=owners[0])
        if participant:
            return participant
        raise SyncError("The RCS08 survey audit owner could not be resolved")
    if not create:
        raise SyncError(f"participant {PARTICIPANT_NAME!r} does not exist")

    institute_name = os.environ.get("RCS08_INSTITUTE_NAME", "")
    if institute_name:
        institute = models.Institute.find(name=institute_name)
        if not institute:
            raise SyncError(f"configured institute {institute_name!r} does not exist")
    else:
        institutes = list(models.Institute.find_all())
        if len(institutes) != 1:
            raise SyncError(
                "RCS08_INSTITUTE_NAME is required unless the database has exactly one institute"
            )
        institute = institutes[0]

    participant = models.Participant(
        name=PARTICIPANT_NAME,
        mrn=PARTICIPANT_NAME,
        institute=institute,
        diagnosis="Chronic Pain",
    )
    participant.save()
    return participant


def sync_neural(participant, *, dry_run: bool = False, limit: int = 0) -> dict:
    """Ingest new Percept JSON exports using the browser upload's decoder chain."""
    if not HASH_KEY:
        raise SyncError("DATASERVER_HASHKEY is not configured")
    if not os.path.isdir(NEURAL_FOLDER):
        raise SyncError(f"neural source folder is missing: {NEURAL_FOLDER}")

    files = sorted(glob.glob(os.path.join(NEURAL_FOLDER, "**", "*.json"), recursive=True))
    if not files:
        raise SyncError(f"no JSON files found under neural source folder: {NEURAL_FOLDER}")

    new_files = []
    duplicate_count = 0
    for filename in files:
        try:
            raw = Path(filename).read_bytes()
        except OSError as exc:
            raise SyncError("a neural source file could not be read") from exc
        unique_hash = hmac.new(HASH_KEY.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        duplicate = models.SourceFile.objects.filter(
            metadata__UniqueHashed=unique_hash,
            metadata__Institute=participant.institute.pk,
        ).exists()
        if duplicate:
            duplicate_count += 1
        else:
            new_files.append((filename, unique_hash))

    if limit:
        new_files = new_files[:limit]
    if dry_run:
        return {
            "found": len(files),
            "existing": duplicate_count,
            "new": len(new_files),
            "ingested": 0,
            "failed": 0,
        }

    ingested = 0
    failures = []
    for filename, unique_hash in new_files:
        source_file = None
        try:
            raw = Path(filename).read_bytes()
            metadata = {
                "UploadType": "MedtronicJSON",
                "Institute": participant.institute.pk,
                "Uploader": participant.institute.pk,
                "UniqueHashed": unique_hash,
                "device_location": "",
                "automatic_deidentification": False,
                "infer_from_device": True,
                "automatic_concatenation": False,
            }
            # Dropbox may replace a file after the initial scan. Never associate
            # its old hash with different bytes, and recheck duplicates per file.
            current_hash = hmac.new(HASH_KEY.encode("utf-8"), raw, hashlib.sha256).hexdigest()
            if current_hash != unique_hash:
                raise SyncError("A neural source file changed during sync; retry after Dropbox finishes.")
            if models.SourceFile.objects.filter(
                metadata__UniqueHashed=unique_hash,
                metadata__Institute=participant.institute.pk,
            ).exists():
                duplicate_count += 1
                continue
            # The deduplication marker becomes visible only after decoding succeeds.
            # A killed worker rolls back the database import so retry can finish it.
            with transaction.atomic():
                from modules.PerceptPresentationPrivacy import sanitize_patient_identifiers
                sanitized, removed_fields = sanitize_patient_identifiers(raw, PARTICIPANT_NAME)
                metadata["DirectIdentifierPolicy"] = 1
                metadata["DirectIdentifierFieldsRemoved"] = removed_fields
                source_file = DataCurator.saveCacheFile(Path(filename).name, metadata, sanitized)
                source_file.owner = participant
                source_file.save()
                DataCurator.MedtronicPerceptJSONDecoder(source_file, person=participant)
            ingested += 1
        except Exception as exc:  # decoder exceptions need per-file cleanup and continuation
            failures.append(type(exc).__name__)
            if source_file is not None:
                try:
                    Database.deleteSourceFile(source_file.pointer)
                except Exception:
                    pass

    if failures:
        raise SyncError(
            f"neural ingestion completed with {len(failures)} failed file(s); "
            f"{ingested} file(s) succeeded and retries remain safe"
        )
    from modules import RCS08PDFMetadata
    pdf_dates = RCS08PDFMetadata.index_folder(NEURAL_FOLDER, participant.uid, STORAGE_PATH)
    return {
        "found": len(files),
        "existing": duplicate_count,
        "new": len(new_files),
        "ingested": ingested,
        "failed": 0,
        "pdf_dates": pdf_dates,
    }


def _redcap_fields() -> list[str]:
    # REDCap returns repeat instrument/instance metadata automatically and
    # rejects those reserved names when they are supplied in fields[].
    fields = {"record_id", REDCAP_TIMESTAMP}
    for source in REDCAP_METRICS.values():
        fields.update(source if isinstance(source, list) else [source])
    return sorted(fields)


def fetch_redcap_rows() -> list[dict]:
    credentials = _load_secret(REDCAP_SECRET_FILE, ("api_url", "api_key"))
    request_data = {
        "token": credentials["api_key"],
        "content": "record",
        "action": "export",
        "format": "json",
        "type": "flat",
        "rawOrLabel": "raw",
        "rawOrLabelHeaders": "raw",
        "exportCheckboxLabel": "false",
        "exportSurveyFields": "true",
        "returnFormat": "json",
        "records[0]": PARTICIPANT_NAME,
    }
    try:
        response = requests.post(credentials["api_url"], data=request_data, timeout=120)
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SyncError("REDCap API request failed") from exc
    if not isinstance(rows, list):
        raise SyncError("REDCap API returned an unexpected payload")
    rows = [
        row
        for row in rows
        if str(row.get("record_id", "")) == PARTICIPANT_NAME
    ]
    if not rows:
        raise SyncError("REDCap returned no matching RCS08 daily survey rows")
    return rows


def _number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(number) else number


def _metric_value(row: dict, source):
    if isinstance(source, list):
        values = [_number(row.get(field)) for field in source]
        present = [value for value in values if value is not None]
        return sum(present) if present else None
    return _number(row.get(source))


def _redcap_timestamp(value: str) -> tuple[float, str]:
    try:
        parsed = dt.datetime.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise SyncError("REDCap contains an invalid daily-survey timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
    else:
        parsed = parsed.astimezone(LOCAL_TIMEZONE)
    return parsed.timestamp(), parsed.isoformat()


def _timestamp_correction_key(row: dict, timestamp_field: str) -> tuple[str, ...]:
    return (
        str(row.get("record_id", "")).strip(),
        str(row.get("redcap_event_name", "")).strip(),
        str(row.get("redcap_repeat_instrument", "")).strip(),
        str(row.get("redcap_repeat_instance", "")).strip(),
        str(row.get(timestamp_field, "")).strip(),
    )


def _apply_timestamp_corrections(rows: list[dict]) -> tuple[list[dict], int]:
    path = Path(TIMESTAMP_CORRECTIONS_FILE)
    if not path.is_file():
        raise SyncError(f"reviewed REDCap timestamp correction table is missing: {path}")
    with path.open(newline="", encoding="utf-8") as source:
        corrections = list(csv.DictReader(source))
    if not corrections:
        raise SyncError("reviewed REDCap timestamp correction table is empty")

    by_key = {}
    for correction in corrections:
        key = _timestamp_correction_key(correction, "original_redcap_timestamp")
        if not all(key):
            raise SyncError("reviewed REDCap timestamp correction has a blank match field")
        if key in by_key:
            raise SyncError("reviewed REDCap timestamp correction table has a duplicate match key")
        corrected_time = str(correction.get("corrected_survey_start", "")).strip()
        if not corrected_time:
            raise SyncError("reviewed REDCap timestamp correction has no corrected time")
        by_key[key] = corrected_time

    matched = {key: 0 for key in by_key}
    corrected_rows = []
    for original in rows:
        row = dict(original)
        key = _timestamp_correction_key(row, REDCAP_TIMESTAMP)
        if key in by_key:
            row[REDCAP_TIMESTAMP] = by_key[key]
            matched[key] += 1
        corrected_rows.append(row)
    invalid = [count for count in matched.values() if count != 1]
    if invalid:
        raise SyncError(
            "each reviewed REDCap timestamp correction must match exactly one live API row"
        )
    return corrected_rows, len(matched)


def _redcap_form_mapping() -> list[dict]:
    questions = []
    for metric in REDCAP_METRICS:
        minimum, maximum = REDCAP_RANGES[metric]
        questions.append(
            {
                "variableName": metric,
                "text": REDCAP_LABELS[metric],
                "type": "score",
                "min": minimum,
                "max": maximum,
                "step": 1,
                "value": 0,
                "default": 0,
                "activeView": metric in {"nrs", "vas", "mpq_sum"},
                "show": True,
            }
        )
    questions.append(
        {
            "variableName": REDCAP_TIMESTAMP,
            "text": "Time",
            "type": "redcapForm",
            "value": REDCAP_TIMESTAMP,
            "default": "",
            "validation": "variable",
            "activeView": False,
            "show": False,
        }
    )
    return [{"header": REDCAP_FORM_NAME, "questions": questions}]


def _normalized_records(rows: list[dict]) -> list[dict]:
    records = []
    seen = set()
    for row in rows:
        timestamp_text = row.get(REDCAP_TIMESTAMP)
        if not timestamp_text:
            continue
        epoch, iso = _redcap_timestamp(timestamp_text)
        result = [_metric_value(row, source) for source in REDCAP_METRICS.values()]
        result.append(iso)
        repeat = str(row.get("redcap_repeat_instance", ""))
        identity = (round(epoch, 6), repeat)
        if identity in seen:
            continue
        seen.add(identity)
        records.append({"date": epoch, "name": repeat, "record": [result]})
    records.sort(key=lambda item: (item["date"], item["name"]))
    if not records:
        raise SyncError("no timestamped RCS08 daily surveys could be parsed")
    return records


def _records_signature(records: list[dict]) -> str:
    canonical = [
        [round(float(record["date"]), 6), record.get("name", ""), record["record"]]
        for record in records
    ]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def sync_redcap(participant, *, dry_run: bool = False) -> dict:
    from modules.RCS08SurveyProcessing import canonicalize_rows, STANDARD_MPQ
    rows = fetch_redcap_rows()
    canonical = canonicalize_rows(rows)
    metrics = {
        "nrs": "nrs_intensity", "vas": "vas_intensity", "left_leg_vas": "left_leg_vas_intensity",
        "back_vas": "back_vas_intensity", "relief": "relief_vas", "mpq_aff": "mpq_aff",
        "mpq_sen": "mpq_sens", "firey": "firey", "tingly": "tingly", "electrocuting": "electrocuting",
        "mpq_sum": "mpq_redcap_expanded_0_54", "mood": "mood_vas", "mpq_standard": "mpq_standard_0_45",
    }
    metrics.update({f"mpq_{name}": f"mpq_{name}" for name in STANDARD_MPQ})
    records = []
    for row in canonical.loc[canonical.include_in_analysis].to_dict("records"):
        epoch, iso = _redcap_timestamp(str(row["survey_start"]))
        result = [_number(row.get(column)) for column in metrics.values()] + [iso]
        identity = ":".join(str(row.get(key, "")) for key in ("source_event", "source_instrument", "repeat_instance"))
        records.append({"date": epoch, "name": identity, "record": [result]})
    records.sort(key=lambda item: (item["date"], item["name"]))
    if not records:
        raise SyncError("No daily surveys passed the reviewed Percept analysis rules; existing data retained")
    mapping = _redcap_form_mapping()
    questions = mapping[0]["questions"]
    questions[-1:-1] = [
        {"variableName": "mood", "text": "Mood VAS (0-100)", "type": "score", "min": 0, "max": 100, "step": 1, "show": True},
        {"variableName": "mpq_standard", "text": "Standard MPQ (0-45)", "type": "score", "min": 0, "max": 45, "step": 1, "show": True},
    ]
    questions[-1:-1] = [
        {"variableName": f"mpq_{name}", "text": name.replace("_", " ").capitalize(),
         "type": "score", "min": 0, "max": 3, "step": 1, "show": True}
        for name in STANDARD_MPQ
    ]
    from modules.RedcapTimeline import phase_table
    timeline_phases, timeline_stage_hash = phase_table()
    adjustments_path = Path(os.environ.get("RCS08_PROCESSING_RULES", "/run/secrets/rcs08_processing")) / "rcs08_home_program_adjustments.csv"
    adjustments_bytes = adjustments_path.read_bytes() if adjustments_path.is_file() else b""
    home_adjustments = list(csv.DictReader(io.StringIO(adjustments_bytes.decode("utf-8-sig"))))
    audit = {
        "timeline_phases": timeline_phases, "timeline_stage_sha256": timeline_stage_hash,
        "timeline_testing_days": canonical.attrs["timeline_testing_days"],
        "timeline_testing_days_sha256": canonical.attrs["timeline_testing_days_sha256"],
        "timeline_home_adjustments": home_adjustments,
        "timeline_home_adjustments_sha256": hashlib.sha256(adjustments_bytes).hexdigest(),
        "timeline_schema": "redcap-pretrial-1",
        "pipeline": "percept_analysis daily survey rules",
        "source_rows": len(canonical), "included": len(records),
        "excluded": int((~canonical.include_in_analysis).sum()),
        "timestamp_corrections": int(canonical.timestamp_source.ne("redcap").sum()),
        "stim_testing_rows": int(canonical.stim_testing_date.sum()),
        "suspect_vas_zeros": int(canonical.vas_default_zero_suspect.sum()),
    }
    reviewed_csv = canonical.to_csv(index=False)
    audit["reviewed_sha256"] = hashlib.sha256(reviewed_csv.encode()).hexdigest()
    mapping[0]["processing"] = audit
    from modules.RedcapVisitContext import pack, publish
    mapping[0]["visit_context"] = pack(publish(canonical, audit["reviewed_sha256"]))
    from modules.RedcapComparisons import publish as publish_comparisons
    mapping[0]["comparison_context"] = publish_comparisons(canonical, audit["reviewed_sha256"], period_start=timeline_phases[3]["start"])
    form = models.ScaleForms.find(institute=participant.institute, name=REDCAP_FORM_NAME)
    stored = [] if form is None else [
        {"date": item.date, "name": item.name, "record": item.record}
        for item in models.ScaleRecord.find_all(source=form, participant=participant)]
    stored.sort(key=lambda item: (item["date"], item["name"]))
    unchanged = bool(form) and form.record == mapping and _records_signature(stored) == _records_signature(records)
    result = {"api_rows": len(rows), "records": len(records), **audit, "changed": not unchanged, "written": 0}
    if dry_run or unchanged:
        return result
    with transaction.atomic():
        # Original rows and every exclusion remain recoverable in encrypted storage.
        audit_source = models.SourceFile(name="RCS08 daily survey processing audit", type="RCS08SurveyAudit", owner=participant,
                                        metadata={"Processing": audit})
        audit_source.pointer = str(Path(os.environ["DATASERVER_PATH"]) / "recordings" / participant.uid / (audit_source.uid + ".bdat"))
        audit_source.hashed = Database.saveSourceFile({"raw_rows": rows, "reviewed_csv": reviewed_csv}, audit_source.pointer)
        audit_source.save()
        if form is None:
            form = models.ScaleForms(institute=participant.institute, name=REDCAP_FORM_NAME, record_type=REDCAP_RECORD_TYPE, record_version=1)
        form.record_type = REDCAP_RECORD_TYPE
        form.record = mapping
        form.save()
        if not models.ParticipantLinkRel.include(participant=participant, record=form):
            models.ParticipantLinkRel.create(participant, form)
        models.ScaleRecord.objects.filter(source=form, participant=participant).delete()
        models.ScaleRecord.objects.bulk_create([
            models.ScaleRecord(participant=participant, source=form, **record) for record in records])
    from modules.ReportCache import invalidate
    invalidate()
    return {**result, "written": len(records)}


def _fixed_chunks(start: dt.date, end: dt.date, days: int = 28):
    current = start
    while current <= end:
        chunk_end = min(current + dt.timedelta(days=days - 1), end)
        yield current, chunk_end
        current += dt.timedelta(days=days)


def _fetch_oura_chunk(requester, start: dt.date, end: dt.date) -> dict[str, list]:
    start_text, end_text = start.isoformat(), end.isoformat()
    return {
        "DailyActivity": requester.getDailyActivity(start_text, end_text),
        "DailyReadiness": requester.getDailyReadiness(start_text, end_text),
        "DailyCardiovascularAge": requester.getDailyCardiovascularAge(start_text, end_text),
        "DailySpo2": requester.getDailySpo2(start_text, end_text),
        "DailyStress": requester.getDailyStress(start_text, end_text),
        "HeartRate": requester.getHeartRate(start_text, end_text),
        "Sleep": requester.getSleep(start_text, end_text),
    }


def _oura_identity(kind: str, record: dict):
    metadata = record.get("Metadata", {})
    if kind == "HeartRate":
        return metadata.get("DayLabel") or record.get("StartTime")
    if kind == "Sleep":
        return record.get("Descriptor", {}).get("BedtimeStart") or record.get("StartTime")
    return metadata.get("DayLabel") or record.get("StartTime")


def _merge_oura(existing: dict, incoming: dict) -> dict:
    merged = {key: list(existing.get(key, [])) for key in OURA_KEYS}
    for kind in OURA_KEYS:
        by_identity = {
            _oura_identity(kind, record): record
            for record in merged[kind]
            if _oura_identity(kind, record) is not None
        }
        for record in incoming.get(kind, []):
            identity = _oura_identity(kind, record)
            if identity is not None:
                by_identity[identity] = record
        merged[kind] = sorted(
            by_identity.values(), key=lambda item: float(item.get("StartTime", 0) or 0)
        )
    return merged


def _save_oura_snapshot(participant, data):
    """Publish a complete file and its hash together; keep older files for readers."""
    source = models.SourceFile.find(owner=participant, type="OuraRingAPISource")
    if source is None:
        source = models.SourceFile(name="OuraRingAPISource", type="OuraRingAPISource", owner=participant)
    directory = STORAGE_PATH / "recordings" / participant.uid
    directory.mkdir(parents=True, exist_ok=True)
    pointer = directory / f"rcs08-oura-{uuid4().hex}.bdat"
    hashed = Database.saveSourceFile(data, str(pointer))
    if not hashed:
        raise SyncError("Oura data could not be saved; the previous snapshot is unchanged.")
    if source.hashed == hashed:
        pointer.unlink()
        return source
    # Replacing the old file before updating its stored hash can break concurrent
    # readers or leave it unreadable after a crash. Publish a new path instead.
    with transaction.atomic():
        source.pointer = str(pointer)
        source.hashed = hashed
        source.save()
    return source


def sync_oura(participant, *, dry_run: bool = False, full: bool = False) -> dict:
    credentials = _load_secret(OURA_SECRET_FILE, ("access_token",))
    token = credentials["access_token"]
    requester = OuraDataManager.OuraRingAPI(token, "")
    try:
        requester.verifyToken()
    except Exception as exc:
        raise SyncError("Oura token verification failed") from exc

    today = dt.datetime.now(LOCAL_TIMEZONE).date()
    configured_start = dt.date.fromisoformat(OURA_START_DATE)
    existing = OuraDataManager.loadOuraRingData(participant, raw=True)
    source = models.SourceFile.find(owner=participant, type="OuraRingAPISource")
    run_full = full or not source or not existing
    if run_full:
        fetch_start = configured_start
    else:
        elapsed = max((today - configured_start).days, 0)
        current_chunk = configured_start + dt.timedelta(days=(elapsed // 28) * 28)
        fetch_start = max(configured_start, current_chunk - dt.timedelta(days=28))

    incoming = {key: [] for key in OURA_KEYS}
    for start, end in _fixed_chunks(fetch_start, today):
        chunk = _fetch_oura_chunk(requester, start, end)
        for key in OURA_KEYS:
            incoming[key].extend(chunk[key])
    # Repair the historical sleep decoder once, without discarding stored days
    # or refetching unrelated historical streams.
    sleep_backfill = bool(source and source.metadata.get("SleepProcessingVersion", 1) < 2 and not run_full)
    if sleep_backfill and fetch_start > configured_start:
        for start, end in _fixed_chunks(configured_start, fetch_start - dt.timedelta(days=1)):
            incoming["Sleep"].extend(requester.getSleep(start.isoformat(), end.isoformat()))
    merged = _merge_oura({} if run_full else existing, incoming)
    counts = {key: len(merged[key]) for key in OURA_KEYS}
    if dry_run:
        return {
            "mode": "full" if run_full else "incremental",
            "fetch_start": fetch_start.isoformat(),
            "fetch_end": today.isoformat(),
            "written": False,
            "counts": counts,
        }

    source = _save_oura_snapshot(participant, merged)
    from modules import RCS08OuraFreshness
    source.metadata = {
        **source.metadata,
        "ManagedSync": "RCS08",
        "SyncStartDate": configured_start.isoformat(),
        "LastSuccessfulSync": dt.datetime.now(dt.timezone.utc).isoformat(),
        "SleepProcessingVersion": 2,
        RCS08OuraFreshness.KEY: RCS08OuraFreshness.summarize(merged, participant.uid, source.hashed),
    }
    source.save()
    device = models.OuraRingDevice.find(owner=participant)
    if not device:
        device = models.OuraRingDevice.create(owner=participant)
    device.auth = {"managed_sync": True}
    device.date_periods = [[
        dt.datetime.combine(configured_start, dt.time.min, tzinfo=LOCAL_TIMEZONE).timestamp(),
        dt.datetime.combine(today, dt.time.max, tzinfo=LOCAL_TIMEZONE).timestamp(),
    ]]
    device.save()
    return {
        "mode": "full" if run_full else "incremental",
        "fetch_start": fetch_start.isoformat(),
        "fetch_end": today.isoformat(),
        "written": True,
        "sleep_history_reprocessed": sleep_backfill,
        "counts": counts,
    }


def run_sync(
    *,
    streams: tuple[str, ...] = ("neural", "redcap", "oura"),
    dry_run: bool = False,
    create_participant: bool = False,
    neural_limit: int = 0,
    full_oura: bool = False,
) -> dict:
    lock_path = STORAGE_PATH / "sync-state" / "rcs08-execution.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path), timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise SyncError("Another RCS08 sync is already running. Please retry after it finishes.") from exc
    try:
        participant = resolve_participant(create=create_participant)
        results = {}
        failures = {}
        operations = (
            ("redcap", lambda: sync_redcap(participant, dry_run=dry_run)),
            ("oura", lambda: sync_oura(participant, dry_run=dry_run, full=full_oura)),
            ("neural", lambda: sync_neural(participant, dry_run=dry_run, limit=neural_limit)),
        )
        for stream, operation in operations:
            if stream not in streams:
                continue
            try:
                results[stream] = operation()
                if stream == "redcap":
                    from modules.RCS08HistoricalSurveys import sync_historical_surveys
                    results[stream]["historical_forms"] = sync_historical_surveys(participant, dry_run=dry_run)
            except Exception as exc:
                failures[stream] = str(exc) if isinstance(exc, SyncError) else type(exc).__name__
        # Both the nightly scheduler and the red Sync Data button use this path.
        # Even if one fetch failed, export the latest successfully stored data;
        # the fetch failure remains visible and is never replaced by success.
        if not dry_run and streams and os.environ.get("RCS08_EXPORT_DIRECTORY"):
            try:
                from modules.RCS08Exports import export_stored_data
                exported = export_stored_data(participant)
                results["csv_exports"] = {"exported_at_utc": exported["exported_at_utc"],
                                          "files": exported["files"]}
            except Exception as exc:
                failures["csv_exports"] = f"CSV export failed: {type(exc).__name__}"
        if failures:
            failure_summary = "; ".join(
                f"{stream}: {failures[stream]}" for stream in sorted(failures)
            )
            successful_names = ", ".join(sorted(results)) or "none"
            raise SyncError(
                f"sync failed ({failure_summary}); successful stream(s): {successful_names}; "
                "automatic retry remains safe"
            )
        return results
    finally:
        lock.release()
