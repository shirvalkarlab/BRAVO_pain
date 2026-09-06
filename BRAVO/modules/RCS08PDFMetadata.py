"""Index PDF Session Date headers without ingesting or modifying scientific data.

The sync worker owns the source-folder mount. The web status route reads only
its small, participant-scoped publication in shared storage. Filename, mtime,
PDF creation date and export footer never become represented-data timestamps.
"""
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

VERSION = "rcs08-pdf-session-date-1"
ZONE = "America/Los_Angeles"


def parse_session_date(text):
    # PDF glyph spacing can extract October as "O ct". Normalize whitespace
    # inside the three-letter month only, without joining unrelated date fields.
    fields = re.findall(r"Session Date:\s*([A-Za-z]\s*[A-Za-z]\s*[A-Za-z])\s+(\d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)\b", text)
    matches = [re.sub(r"\s", "", month) + " " + rest for month, rest in fields]
    if len(set(matches)) != 1:
        raise ValueError("Missing or ambiguous PDF Session Date header")
    local = dt.datetime.strptime(matches[0], "%b %d, %Y %I:%M %p")
    zoned = local.replace(tzinfo=ZoneInfo(ZONE))
    # A zone-free PDF header cannot resolve the repeated autumn hour or a
    # nonexistent spring clock time. Do not invent an offset for either.
    if (zoned.utcoffset() != local.replace(tzinfo=ZoneInfo(ZONE), fold=1).utcoffset()
            or zoned.astimezone(dt.timezone.utc).astimezone(ZoneInfo(ZONE)).replace(tzinfo=None) != local):
        raise ValueError("PDF Session Date has an ambiguous local clock time")
    return zoned.isoformat()


def read_header(raw):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    return parse_session_date(reader.pages[0].extract_text())


def cache_path(storage, participant_uid):
    key = hashlib.sha256(str(participant_uid).encode()).hexdigest()
    return Path(storage) / "sync-state" / ("rcs08-pdf-" + key + ".json")


def read_index(storage, participant_uid):
    try:
        value = json.loads(cache_path(storage, participant_uid).read_text())
    except (OSError, ValueError):
        return None
    if (not isinstance(value, dict) or value.get("version") != VERSION
            or value.get("participant_id") != str(participant_uid)
            or not isinstance(value.get("files"), dict)):
        return None
    return value


def index_folder(folder, participant_uid, storage, *, now=None):
    """Incrementally parse first-page headers; write metadata only, never originals."""
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError("The designated neural source folder is unavailable")
    root_id = hashlib.sha256(str(root).encode()).hexdigest()
    previous = read_index(storage, participant_uid) or {}
    old = previous.get("files", {}) if previous.get("source_folder_id") == root_id else {}
    files = {}
    for path in sorted(root.rglob("*.pdf")):
        # A symlink must not silently bring another folder's reports into scope.
        if not path.resolve().is_relative_to(root):
            continue
        relative = str(path.relative_to(root))
        stat = path.stat()
        identity = [stat.st_size, stat.st_mtime_ns]
        prior = old.get(relative, {})
        if prior.get("identity") == identity and prior.get("session_date"):
            files[relative] = prior
            continue
        try:
            raw = path.read_bytes()
            value = read_header(raw)
            digest = hashlib.sha256(raw).hexdigest()
            files[relative] = {"identity": identity, "sha256": digest, "session_date": value}
        except Exception as exc:
            files[relative] = {"identity": identity, "session_date": None,
                               "error": type(exc).__name__}
    payload = {"version": VERSION, "participant_id": str(participant_uid), "source_folder_id": root_id,
               "indexed_at": time.time() if now is None else now, "files": files,
               "timezone": ZONE, "precision": "minute",
               "timezone_evidence": "Pacific local Session Date; verified against the 2026-09-04 paired native JSON SessionDate 2026-09-04T23:56:45Z and PDF header 4:56 PM. PDF does not record seconds."}
    target = cache_path(storage, participant_uid)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix("." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True))
        temporary.chmod(0o600)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"pdf_files": len(files), "dated": sum(bool(row["session_date"]) for row in files.values()),
            "unavailable": sum(not row["session_date"] for row in files.values())}


def freshness(storage, participant_uid, *, now):
    entry = {"available": False, "value": None, "precision": "minute", "timezone": ZONE,
             "source": "Local RCS08 session-report PDF · first-page Session Date",
             "semantics": "Latest represented PDF session date; PDF export footer, filename and arrival times are not used.",
             "reason": "PDF session metadata has not been indexed for this participant.", "partial": False}
    index = read_index(storage, participant_uid)
    if index is None:
        return entry
    valid = []
    for name, row in index["files"].items():
        try:
            stamp = dt.datetime.fromisoformat(row["session_date"])
            if stamp.tzinfo is not None and 0 < stamp.timestamp() <= now:
                valid.append((stamp.timestamp(), stamp.isoformat(), name, row["sha256"]))
        except (ValueError, TypeError, KeyError):
            continue
    entry["coverage"] = {"indexed_files": len(index["files"]), "dated_files": len(valid)}
    if valid:
        _, value, name, digest = max(valid)
        entry.update(available=True, value=value, reason=None,
                     evidence={"file": name, "sha256": digest, "field": "Session Date"})
    else:
        entry["reason"] = "No valid PDF Session Date is available in the index."
    if len(valid) < len(index["files"]):
        entry.update(partial=True, reason="Some indexed PDFs have no valid Session Date; a later session may be unindexed.")
    return entry
