"""Which Google credential the sheet export signs in with (decision 181, 2026-09-16).

The service-account route hit a rule of Google's: a service account owns every file it creates
and has no Drive storage, so copying the template into the lab's My Drive folder fails with
"storage quota exceeded" however it is shared. The way round the PI chose is to act AS HIM: a
one-time consent on his Mac writes a user token (`secrets/google_oauth_token.json`); the server
uses it when present and falls back to the service-account key otherwise. Tests here build the
files by hand in a temporary directory and never touch the real `secrets/`.
"""
import json
import os

import pytest

from StimOptimizer import google_sheets_client as G


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
