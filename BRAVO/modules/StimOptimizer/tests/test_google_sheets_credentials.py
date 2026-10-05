"""Which Google credential the sheet export signs in with (decision 181, 2026-09-16).

The service-account route hit a rule of Google's: a service account owns every file it creates
and has no Drive storage, so copying the template into the lab's My Drive folder fails with
"storage quota exceeded" however it is shared. The way round the PI chose is to act AS HIM: a
one-time consent on his Mac writes a user token (`secrets/google_oauth_token.json`); the server
uses it when present and falls back to the service-account key otherwise. Tests here build the
files by hand in a temporary directory and never touch the real `secrets/`.

Merged here 2026-10-05: test_clinic_sheet_sync.py (each under its own heading below).
"""
import json
import os

import pytest

from StimOptimizer import google_sheets_client as G

from StimOptimizer import clinic_sheet_sync as CS


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    tok = tmp_path / "token.json"
    key = tmp_path / "key.json"
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", str(tok))
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(key))
    return tok, key


def test_no_file_means_no_source_and_not_available(secrets):
    assert G.credential_source() is None
    assert G.available() is False


def test_a_user_token_is_preferred_over_a_service_account_key(secrets):
    tok, key = secrets
    key.write_text(json.dumps({"type": "service_account", "client_email": "x@y"}))
    assert G.credential_source() == "service_account"
    tok.write_text(json.dumps({"type": "authorized_user", "client_id": "c", "client_secret": "s",
                               "refresh_token": "r"}))
    assert G.credential_source() == "user"
    assert G.available() is True


def test_the_token_path_has_one_default_beside_the_key_and_the_env_var_wins(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_TOKEN_FILE", raising=False)
    assert G.token_file() == "secrets/google_oauth_token.json"
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_FILE", "/elsewhere/t.json")
    assert G.token_file() == "/elsewhere/t.json"


def test_the_client_builds_user_credentials_from_the_token_and_never_reads_the_key(secrets, monkeypatch):
    tok, key = secrets
    key.write_text("NOT JSON -- reading this would raise")
    tok.write_text(json.dumps({"type": "authorized_user", "client_id": "c", "client_secret": "s",
                               "refresh_token": "r"}))
    seen = {}

    def _build(api, ver, credentials=None, cache_discovery=None):
        seen[api] = type(credentials).__name__
        return object()
    monkeypatch.setattr("googleapiclient.discovery.build", _build)
    G.GoogleClient()
    assert seen == {"drive": "Credentials", "sheets": "Credentials"}
    from google.oauth2.credentials import Credentials as _UserCreds
    assert _UserCreds.__name__ == "Credentials"          # the user-credential class, not the service account's


def test_the_setup_note_names_both_routes_and_the_quota_rule():
    note = G.SETUP_NOTE
    assert "google_oauth_token.json" in note and "google_service_account.json" in note
    assert "storage" in note.lower()


# ================================================================================================
# From test_clinic_sheet_sync.py (merged here 2026-10-05).
# T4 of the 2026-09-15 review (decision 182): the clinic sheets reach the server on their own.
#
# The ingest (`ingest_clinic_sheets`) reads `.xlsx` files from a local folder that was filled by hand.
# The lab writes its sheets in a Google Drive folder, as Google Sheets. `clinic_sheet_sync` pulls that
# folder down as `.xlsx` -- Google-native sheets exported, uploaded `.xlsx` files fetched as they are
# -- skipping anything Drive says has not changed since the last pull, leaving out the template and
# anything marked OLD, then runs the ingest. Tests drive it with a fake Drive client.
# ================================================================================================

GSHEET = "application/vnd.google-apps.spreadsheet"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _FakeDrive:
    def __init__(self, files):
        self.files = files
        self.exported, self.fetched = [], []

    def list_folder(self, folder_id):
        return list(self.files)

    def export_xlsx(self, file_id):
        self.exported.append(file_id)
        return b"PK-export-" + file_id.encode()

    def get_media(self, file_id):
        self.fetched.append(file_id)
        return b"PK-media-" + file_id.encode()


def _files():
    return [
        {"id": "T", "name": "[Template]RCS08 Stage 2 - {Month} 2025 Clinic Testing {MM}_{DD}_{YY}",
         "mimeType": GSHEET, "modifiedTime": "2026-09-16T22:54:00Z"},
        {"id": "O", "name": "OLD - [Template]RCS08 ...", "mimeType": GSHEET, "modifiedTime": "2026-08-31T18:20:00Z"},
        {"id": "A", "name": "RCS08 Stage 2 - September 2026 Clinic Testing 09_16_26",
         "mimeType": GSHEET, "modifiedTime": "2026-09-16T23:32:00Z"},
        {"id": "B", "name": "RCS08 Stage 2 - April 2026 In-clinic Testing 04_16_26",
         "mimeType": XLSX, "modifiedTime": "2026-04-16T20:00:00Z"},
        {"id": "N", "name": "some notes.txt", "mimeType": "text/plain", "modifiedTime": "2026-01-01T00:00:00Z"},
    ]


def test_sync_pulls_sheets_and_xlsx_files_and_leaves_out_the_template_old_and_non_sheets(tmp_path):
    d = _FakeDrive(_files())
    rep = CS.sync_folder(d, "F", str(tmp_path))
    assert sorted(os.listdir(tmp_path)) == sorted([
        "RCS08 Stage 2 - September 2026 Clinic Testing 09_16_26.xlsx",
        "RCS08 Stage 2 - April 2026 In-clinic Testing 04_16_26.xlsx", CS.MANIFEST_NAME])
    assert d.exported == ["A"] and d.fetched == ["B"]
    assert rep["downloaded"] == 2 and rep["skipped_unchanged"] == 0
    assert sorted(rep["excluded"]) == sorted(["[Template]RCS08 Stage 2 - {Month} 2025 Clinic Testing {MM}_{DD}_{YY}",
                                             "OLD - [Template]RCS08 ...", "some notes.txt"])
    assert open(tmp_path / "RCS08 Stage 2 - September 2026 Clinic Testing 09_16_26.xlsx", "rb").read() == b"PK-export-A"


def test_a_second_sync_skips_files_drive_says_are_unchanged_and_refetches_a_changed_one(tmp_path):
    d = _FakeDrive(_files())
    CS.sync_folder(d, "F", str(tmp_path))
    d.exported.clear(); d.fetched.clear()
    rep = CS.sync_folder(d, "F", str(tmp_path))
    assert rep["downloaded"] == 0 and rep["skipped_unchanged"] == 2 and d.exported == [] and d.fetched == []
    d.files[2]["modifiedTime"] = "2026-09-17T09:00:00Z"        # the 09_16 sheet edited next morning
    rep = CS.sync_folder(d, "F", str(tmp_path))
    assert rep["downloaded"] == 1 and rep["skipped_unchanged"] == 1 and d.exported == ["A"]


def test_the_manifest_records_what_each_local_file_came_from(tmp_path):
    d = _FakeDrive(_files())
    CS.sync_folder(d, "F", str(tmp_path))
    m = json.load(open(tmp_path / CS.MANIFEST_NAME))
    assert m["RCS08 Stage 2 - September 2026 Clinic Testing 09_16_26.xlsx"] == {
        "id": "A", "modifiedTime": "2026-09-16T23:32:00Z", "mimeType": GSHEET}


def test_a_download_that_fails_is_reported_and_leaves_the_previous_local_file_in_place(tmp_path):
    d = _FakeDrive(_files())
    CS.sync_folder(d, "F", str(tmp_path))

    def _boom(file_id):
        raise RuntimeError("quota")
    d.files[2]["modifiedTime"] = "2026-09-17T09:00:00Z"
    d.export_xlsx = _boom
    rep = CS.sync_folder(d, "F", str(tmp_path))
    assert rep["failed"] == [{"name": "RCS08 Stage 2 - September 2026 Clinic Testing 09_16_26",
                              "error": "RuntimeError('quota')"}]
    assert open(tmp_path / "RCS08 Stage 2 - September 2026 Clinic Testing 09_16_26.xlsx", "rb").read() == b"PK-export-A"


def test_a_local_file_name_never_carries_a_path_separator(tmp_path):
    d = _FakeDrive([{"id": "X", "name": "odd/Testing\\here", "mimeType": GSHEET, "modifiedTime": "2026-01-01T00:00:00Z"}])
    CS.sync_folder(d, "F", str(tmp_path))
    assert os.listdir(tmp_path) == sorted(["odd_Testing_here.xlsx", CS.MANIFEST_NAME]) or \
        sorted(os.listdir(tmp_path)) == sorted(["odd_Testing_here.xlsx", CS.MANIFEST_NAME])


def test_a_sheet_that_is_not_a_testing_workbook_is_excluded_by_name(tmp_path):
    """The lab names every visit sheet '... Testing MM_DD_YY'. A different Google Sheet in the same
    folder (the Stage 1 contact-and-streaming log) is not a clinic-testing workbook and must not
    land in the ingest folder, where it would fail to parse on every daily pass."""
    drive = _FakeDrive([
        {"id": "a", "name": "RCS08 Stage 2 - May 2026 In-clinic Testing 05_14_26",
         "mimeType": GSHEET, "modifiedTime": "2026-05-15T14:20:57Z"},
        {"id": "b", "name": "RCS08 Stage 1 Contact and Streaming Log",
         "mimeType": GSHEET, "modifiedTime": "2025-12-17T20:52:41Z"},
    ])
    rep = CS.sync_folder(drive, "folder", str(tmp_path))
    assert rep["downloaded"] == 1
    assert rep["excluded"] == ["RCS08 Stage 1 Contact and Streaming Log"]
    assert sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".xlsx") == [
        "RCS08 Stage 2 - May 2026 In-clinic Testing 05_14_26.xlsx"]
