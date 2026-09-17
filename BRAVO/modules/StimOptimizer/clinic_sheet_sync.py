"""Pull the lab's clinic-testing workbooks from the Google Drive folder into the local folder the
ingest reads (T4 of the 2026-09-15 review; decision 182).

WHY. `ingest_clinic_sheets` (decision 161) reads `.xlsx` files from a local folder that was filled by
hand once. The lab writes each visit's sheet in Google Drive ("Clinic Testing"), as a Google Sheet,
so a new visit reached the Stim Optimizer only when somebody remembered to download it. This module
lists that folder through the same signed-in client the sheet export uses (decision 181), exports
every Google Sheet as `.xlsx`, fetches every uploaded `.xlsx` as it is, and writes them under the
Drive file's own name -- the names the local folder already carries -- so the ingest's key
(`clinic_pain.folder_signature`, name and content hash per file) is unchanged for a file that did
not change.

WHAT IS SKIPPED, AND WHY. The template (`[Template]...`) and anything marked `OLD - ` are never
sheets of a visit, nor is a sheet whose name lacks the word "Testing" (the Stage 1 log); anything that is neither a Google Sheet nor an `.xlsx` is not a workbook; a
file whose Drive `modifiedTime` equals the one in the last pull's manifest is not downloaded again
(a fresh export of an unchanged sheet is not byte-identical, and re-downloading it would change the
ingest key for nothing). Trashed files are not listed. A download that fails is reported and the
previous local copy stays, so one bad day never empties the folder.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any, Dict, List

MANIFEST_NAME = ".drive_sync_manifest.json"
GSHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXCLUDE_PREFIXES = ("[Template]", "OLD - ")
# The lab names every visit sheet "... Testing MM_DD_YY" (31 of 31 on 2026-09-16). A sheet without
# the word is something else kept in the same folder -- the Stage 1 contact-and-streaming log --
# and is not a clinic-testing workbook.
REQUIRED_WORD = "Testing"


def _local_name(drive_name: str) -> str:
    safe = re.sub(r"[/\\\x00]", "_", str(drive_name)).strip()
    return safe if safe.lower().endswith(".xlsx") else safe + ".xlsx"


def _load_manifest(dest: str) -> Dict[str, Any]:
    p = os.path.join(dest, MANIFEST_NAME)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p) as fh:
            return json.load(fh)
    except Exception:                                  # noqa: BLE001 - a bad manifest means re-pull
        return {}


def _write_atomic(path: str, data: bytes) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".sync-", dir=d)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def sync_folder(drive, folder_id: str, dest: str) -> Dict[str, Any]:
    """Bring `dest` up to date with the Drive folder. Returns counts and names: ``downloaded``,
    ``skipped_unchanged``, ``excluded`` (names left out on purpose), ``failed`` (name and error).
    Never raises for one file's failure."""
    os.makedirs(dest, exist_ok=True)
    manifest = _load_manifest(dest)
    rep: Dict[str, Any] = {"downloaded": 0, "skipped_unchanged": 0, "excluded": [], "failed": [],
                           "files": []}
    for f in drive.list_folder(folder_id):
        name, mime = str(f.get("name", "")), str(f.get("mimeType", ""))
        if (name.startswith(EXCLUDE_PREFIXES) or REQUIRED_WORD not in name
                or mime not in (GSHEET_MIME, XLSX_MIME)):
            rep["excluded"].append(name)
            continue
        local = _local_name(name)
        path = os.path.join(dest, local)
        prior = manifest.get(local) or {}
        if (os.path.isfile(path) and prior.get("id") == f.get("id")
                and prior.get("modifiedTime") == f.get("modifiedTime")):
            rep["skipped_unchanged"] += 1
            rep["files"].append(local)
            continue
        try:
            data = drive.export_xlsx(f["id"]) if mime == GSHEET_MIME else drive.get_media(f["id"])
            _write_atomic(path, data)
        except Exception as exc:                       # noqa: BLE001 - reported, previous copy kept
            rep["failed"].append({"name": name, "error": repr(exc)})
            continue
        manifest[local] = {"id": f.get("id"), "modifiedTime": f.get("modifiedTime"), "mimeType": mime}
        rep["downloaded"] += 1
        rep["files"].append(local)
    _write_atomic(os.path.join(dest, MANIFEST_NAME), json.dumps(manifest, indent=1).encode())
    return rep
