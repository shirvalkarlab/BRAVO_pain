"""An optional, thin wrapper around the Google Drive and Sheets APIs for the "Make Google sheet"
export (`sheet_export.py`). Used by NOTHING ELSE in this repository.

WHY OPTIONAL. This server has no Google credentials today. `available()` is False whenever the key
file is absent or the client libraries fail to import, and NEVER raises -- `sheet_export.export`
reads it to decide between writing a real Google Sheet and filling a local `.xlsx` for download.

NEVER LOGS OR RETURNS THE KEY. `GoogleClient` reads the key file once, to build credentials, and
holds nothing from it afterward; no function here prints, logs, or serialises the file's contents.

TURNING THIS ON, IN PLAIN WORDS (also returned to the page as `setup`, xlsx mode):
  1. Create a Google Cloud service account and download its JSON key file.
  2. Put that file on this server at `secrets/google_service_account.json` (or point the
     `GOOGLE_SERVICE_ACCOUNT_FILE` environment variable at wherever it actually is).
  3. In Google Drive, share BOTH the "Clinic Testing" folder and the template workbook with the
     service account's own e-mail address (it is inside the key file), giving it Editor access.
  4. Restart the server's worker processes so they pick up the key file.
Until then, pressing "Make Google sheet" downloads a filled `.xlsx` file instead.
"""
from __future__ import annotations

import os

SETUP_NOTE = (
    "To let this server write directly to Google Sheets: (1) create a Google Cloud service "
    "account and download its JSON key file; (2) put that file on this server at "
    "secrets/google_service_account.json (or point the GOOGLE_SERVICE_ACCOUNT_FILE environment "
    "variable at it); (3) in Google Drive, share BOTH the \"Clinic Testing\" folder and the "
    "template workbook with the service account's own e-mail address, giving it Editor access; "
    "(4) restart the server's worker processes. Until then, this button downloads a filled "
    ".xlsx file instead."
)

#: Default key-file location, relative to wherever the server process's current directory is
#: (the container runs from the repository root, so this resolves to `secrets/...` there).
DEFAULT_KEY_FILE = "secrets/google_service_account.json"

#: Google Drive folder id of "Pain Neuromodulation Lab Master Folder > RCS08 > Stage 2 >
#: Clinic Testing" (read directly from the folder's own share link, 2026-09-14).
DEFAULT_FOLDER_ID = "10uYVdcj_NGtepeiDF2qHn2bb-fwHqQcv"

#: Google Drive file id of the lab's template workbook, "[Template]RCS08 Stage 2 - {Month} 2025
#: Clinic Testing {MM}_{DD}_{YY}" (same source).
DEFAULT_TEMPLATE_ID = "1q1kNwrzDA6MZBGNEk0dzyT7MEyL6X1sivrgmT7XyTag"

SCOPES = ("https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/spreadsheets")


def key_file() -> str:
    return os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", DEFAULT_KEY_FILE)


def folder_id() -> str:
    return os.environ.get("CLINIC_SHEETS_DRIVE_FOLDER_ID", DEFAULT_FOLDER_ID)


def template_id() -> str:
    return os.environ.get("CLINIC_SHEETS_TEMPLATE_ID", DEFAULT_TEMPLATE_ID)


def available() -> bool:
    """True only when a readable key file exists on disk AND the google-api client libraries
    import cleanly. Never raises."""
    path = key_file()
    if not path or not os.path.isfile(path):
        return False
    try:
        import google.oauth2.service_account  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
    except ImportError:
        return False
    return True


class GoogleClient:
    """Exposes only the four operations `sheet_export.export` needs: find a file by name inside a
    folder, copy a source file (the template) into a folder under a new name, clear a value
    range, write a value range. Every write goes to the file id the caller supplies -- this class
    never remembers or re-uses the template's own id for anything but `copy_file`'s SOURCE."""

    def __init__(self, key_file_path=None):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        path = key_file_path or key_file()
        creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
        self._drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    def find_file_in_folder(self, folder_id_, name):
        """The id of the first non-trashed file named exactly `name` directly inside
        `folder_id_`, or `None`."""
        safe_name = name.replace("'", "\\'")
        q = f"'{folder_id_}' in parents and name = '{safe_name}' and trashed = false"
        resp = self._drive.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
        files = resp.get("files") or []
        return files[0]["id"] if files else None

    def copy_file(self, source_id, folder_id_, name):
        """Drive's own `files.copy`: makes a NEW file from `source_id` (the template) inside
        `folder_id_`, named `name`. The template itself is never modified by this call -- it is
        only ever the copy's source. Returns the new file's id."""
        body = {"name": name, "parents": [folder_id_]}
        resp = self._drive.files().copy(fileId=source_id, body=body, fields="id").execute()
        return resp["id"]

    def clear_values(self, file_id, range_a1):
        (self._sheets.spreadsheets().values()
         .clear(spreadsheetId=file_id, range=range_a1, body={}).execute())

    def update_values(self, file_id, range_a1, values):
        body = {"values": values}
        (self._sheets.spreadsheets().values()
         .update(spreadsheetId=file_id, range=range_a1, valueInputOption="USER_ENTERED", body=body)
         .execute())

    def file_url(self, file_id):
        return f"https://docs.google.com/spreadsheets/d/{file_id}/edit"


def client_if_available():
    """A ready `GoogleClient`, or `None` when `available()` is False. Never raises: a
    construction failure (a malformed key file, an unreachable API) is treated the same as no
    credentials at all, so the export falls back to the xlsx download rather than 500ing."""
    if not available():
        return None
    try:
        return GoogleClient()
    except Exception:
        return None
