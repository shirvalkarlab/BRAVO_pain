"""An optional, thin wrapper around the Google Drive and Sheets APIs for the "Make Google sheet"
export (`sheet_export.py`). Used by NOTHING ELSE in this repository.

WHY OPTIONAL. `available()` is False whenever no credential file is on disk or the client
libraries fail to import, and NEVER raises -- `sheet_export.export` reads it to decide between
writing a real Google Sheet and filling a local `.xlsx` for download.

TWO CREDENTIALS, ONE PREFERRED (decision 181, 2026-09-16). The server signs in either
  (a) AS THE PI, with a user token (`secrets/google_oauth_token.json`) written once by a consent
      step on his Mac (`google_oauth_consent.py`) -- preferred whenever the file exists; or
  (b) as a service account (`secrets/google_service_account.json`).
The service-account route cannot create sheets in a My Drive folder however it is shared: a
service account OWNS every file it creates and has no Drive storage of its own, so Drive's
`files.copy` refuses with "storage quota exceeded" (measured 2026-09-16). It stays as the
fallback for reading, and would work in a Shared Drive. The user route makes the PI the owner of
every exported sheet, under his own quota.

NEVER LOGS OR RETURNS EITHER FILE. `GoogleClient` reads the credential file once, to build
credentials, and holds nothing from it afterward.
"""
from __future__ import annotations

import os

SETUP_NOTE = (
    "To let this server write directly to Google Sheets, sign it in as yourself: (1) in Google "
    "Cloud, create an OAuth client (Desktop app) and put its JSON at "
    "secrets/google_oauth_client.json; (2) on a machine with a browser, run "
    "google_oauth_consent.py once and click Allow -- it writes secrets/google_oauth_token.json "
    "(or point GOOGLE_OAUTH_TOKEN_FILE at it); (3) restart the server's worker processes. A "
    "service-account key at secrets/google_service_account.json is used only when no user token "
    "exists, and cannot CREATE sheets in a My Drive folder: a service account owns what it "
    "creates and has no Drive storage, so the copy is refused for quota. Until one of these is "
    "in place, this button downloads a filled .xlsx file instead."
)

#: Default credential locations, relative to wherever the server process's current directory is
#: (the container runs from `BRAVO/`, so these resolve to `BRAVO/secrets/...` on the host).
DEFAULT_KEY_FILE = "secrets/google_service_account.json"
DEFAULT_TOKEN_FILE = "secrets/google_oauth_token.json"
DEFAULT_CLIENT_FILE = "secrets/google_oauth_client.json"

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


def token_file() -> str:
    return os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", DEFAULT_TOKEN_FILE)


def client_file() -> str:
    return os.environ.get("GOOGLE_OAUTH_CLIENT_FILE", DEFAULT_CLIENT_FILE)


def credential_source():
    """"user" when a user token file exists (preferred), "service_account" when only the key
    does, None when neither is on disk. Reads nothing but the files' existence."""
    tok = token_file()
    if tok and os.path.isfile(tok):
        return "user"
    key = key_file()
    if key and os.path.isfile(key):
        return "service_account"
    return None


def folder_id() -> str:
    return os.environ.get("CLINIC_SHEETS_DRIVE_FOLDER_ID", DEFAULT_FOLDER_ID)


def template_id() -> str:
    return os.environ.get("CLINIC_SHEETS_TEMPLATE_ID", DEFAULT_TEMPLATE_ID)


def available() -> bool:
    """True only when a credential file exists on disk (user token or service-account key) AND
    the google-api client libraries import cleanly. Never raises."""
    if credential_source() is None:
        return False
    try:
        import google.oauth2.credentials  # noqa: F401
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
        """Signs in as the PI when a user token exists (decision 181), else with the service
        account. `key_file_path` forces the service-account route for a caller that has one."""
        from googleapiclient.discovery import build

        if key_file_path is None and credential_source() == "user":
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(token_file(), scopes=SCOPES)
            self.source = "user"
        else:
            from google.oauth2 import service_account
            path = key_file_path or key_file()
            creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
            self.source = "service_account"
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

    def center_cells(self, file_id, sheet_tab, first_row, n_rows, n_cols):
        """Centre-justify exactly the block this export wrote (1-based `first_row`, `n_rows` down,
        `n_cols` across, on the tab named `sheet_tab`) and nothing else on the sheet."""
        if n_rows <= 0 or n_cols <= 0:
            return
        meta = self._sheets.spreadsheets().get(spreadsheetId=file_id,
                                               fields="sheets(properties(sheetId,title))").execute()
        sheet_id = next((sh["properties"]["sheetId"] for sh in meta.get("sheets", [])
                         if sh["properties"].get("title") == sheet_tab), None)
        if sheet_id is None:
            sheet_id = meta["sheets"][0]["properties"]["sheetId"]
        req = {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": int(first_row) - 1,
                      "endRowIndex": int(first_row) - 1 + int(n_rows),
                      "startColumnIndex": 0, "endColumnIndex": int(n_cols)},
            "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.horizontalAlignment"}}
        self._sheets.spreadsheets().batchUpdate(spreadsheetId=file_id,
                                                body={"requests": [req]}).execute()

    def file_url(self, file_id):
        return f"https://docs.google.com/spreadsheets/d/{file_id}/edit"

    # --- reads for the clinic-sheet sync (decision 182) -------------------------------------
    def list_folder(self, folder_id_):
        """Every non-trashed file directly inside `folder_id_`: id, name, mimeType, modifiedTime."""
        out, token = [], None
        while True:
            resp = self._drive.files().list(
                q=f"'{folder_id_}' in parents and trashed = false",
                fields="nextPageToken,files(id,name,mimeType,modifiedTime)", pageSize=200,
                pageToken=token).execute()
            out.extend(resp.get("files") or [])
            token = resp.get("nextPageToken")
            if not token:
                return out

    def export_xlsx(self, file_id):
        """A Google Sheet, exported as an .xlsx workbook (bytes)."""
        return self._drive.files().export(
            fileId=file_id,
            mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet").execute()

    def get_media(self, file_id):
        """An uploaded (non-Google) file's own bytes."""
        return self._drive.files().get_media(fileId=file_id).execute()


def client_if_available():
    """A ready `GoogleClient`, or `None` when `available()` is False. Never raises: a
    construction failure (a malformed file, an unreachable API) is treated the same as no
    credentials at all, so the export falls back to the xlsx download rather than 500ing."""
    if not available():
        return None
    try:
        return GoogleClient()
    except Exception:
        return None
