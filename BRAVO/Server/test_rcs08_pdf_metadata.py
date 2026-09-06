"""PDF header provenance, incremental indexing and participant-scoped publication."""
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from django.core.management.base import CommandError

from modules import RCS08PDFMetadata as pdf
from Server.management.commands.index_rcs08_pdf_dates import Command

NOW = dt.datetime(2026, 9, 5, tzinfo=dt.timezone.utc).timestamp()


def test_session_header_wins_over_export_footer_and_matches_paired_json_minute():
    text = "Session Report\nSession Date: Sep 4, 2026 4:56 PM\nExported: Sep 4, 2026 4:57 PM"
    assert pdf.parse_session_date(text) == "2026-09-04T16:56:00-07:00"
    native = dt.datetime.fromisoformat("2026-09-04T23:56:45+00:00")
    parsed = dt.datetime.fromisoformat(pdf.parse_session_date(text))
    assert native.timestamp() - parsed.timestamp() == 45
    assert pdf.parse_session_date("Session Date: Jan 4, 2026 4:56 PM") == "2026-01-04T16:56:00-08:00"
    assert pdf.parse_session_date("Session Date: O ct 2, 2025 11:09 AM") == "2025-10-02T11:09:00-07:00"


@pytest.mark.parametrize("text", ["Exported: Sep 4, 2026 4:57 PM", "Session Date: bad",
    "Session Date: Sep 4, 2026 4:56 PM\nSession Date: Sep 3, 2026 4:56 PM",
    "Session Date: Nov 1, 2026 1:30 AM", "Session Date: Mar 8, 2026 2:30 AM",
    "Session Date: Sep 44, 2026 4:56 PM"])
def test_invalid_or_ambiguous_header_is_not_guessed(text):
    with pytest.raises(ValueError):
        pdf.parse_session_date(text)


def test_reader_extracts_only_first_page(monkeypatch):
    import sys
    reader = Mock(return_value=NS(pages=[NS(extract_text=lambda: "Session Date: Sep 4, 2026 4:56 PM")]))
    monkeypatch.setitem(sys.modules, "pypdf", NS(PdfReader=reader))
    assert pdf.read_header(b"synthetic PDF") == "2026-09-04T16:56:00-07:00"
    assert reader.call_args.args[0].getvalue() == b"synthetic PDF"


def test_index_is_metadata_only_incremental_and_never_uses_filename_or_mtime(monkeypatch, tmp_path):
    source = tmp_path / "originals"
    source.mkdir()
    document = source / "20300101-future-arrival.pdf"
    document.write_bytes(b"synthetic original")
    before = document.read_bytes()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"not in reviewed folder")
    (source / "link.pdf").symlink_to(outside)
    bad = source / "bad.pdf"
    bad.write_bytes(b"unreadable")
    reader = Mock(side_effect=lambda raw: "2026-09-04T16:56:00-07:00" if raw == before else (_ for _ in ()).throw(ValueError("bad PDF")))
    monkeypatch.setattr(pdf, "read_header", reader)
    storage = tmp_path / "storage"
    result = pdf.index_folder(source, "p", storage, now=NOW)
    assert result == {"pdf_files": 2, "dated": 1, "unavailable": 1}
    assert document.read_bytes() == before
    assert pdf.cache_path(storage, "p").stat().st_mode & 0o777 == 0o600
    value = pdf.freshness(storage, "p", now=NOW)
    assert value["available"] and value["partial"] and value["precision"] == "minute"
    assert value["value"] == "2026-09-04T16:56:00-07:00"
    assert value["evidence"]["file"] == document.name
    assert not pdf.freshness(storage, "someone-else", now=NOW)["available"]
    reader.reset_mock()
    pdf.index_folder(source, "p", storage)
    reader.assert_called_once_with(b"unreadable")
    bad.unlink()
    reader.reset_mock()
    pdf.index_folder(source, "p", storage, now=NOW)
    reader.assert_not_called()
    assert not pdf.freshness(storage, "p", now=NOW)["partial"]
    second = tmp_path / "different-folder"
    second.mkdir()
    (second / document.name).write_bytes(before)
    reader.side_effect = None
    reader.return_value = "2026-09-03T16:56:00-07:00"
    pdf.index_folder(second, "p", storage, now=NOW)
    assert pdf.freshness(storage, "p", now=NOW)["value"] == reader.return_value


def test_missing_corrupt_wrong_owner_and_undated_cache_stay_unavailable(tmp_path):
    assert pdf.read_index(tmp_path, "p") is None
    assert not list(tmp_path.iterdir()), "Status reads must not create cache directories"
    path = pdf.cache_path(tmp_path, "p")
    path.parent.mkdir()
    for raw in ["broken", "[]", json.dumps({"version": "old"}),
                json.dumps({"version": pdf.VERSION, "participant_id": "other", "files": {}}),
                json.dumps({"version": pdf.VERSION, "participant_id": "p", "files": []})]:
        path.write_text(raw)
        assert pdf.read_index(tmp_path, "p") is None
    path.write_text(json.dumps({"version": pdf.VERSION, "participant_id": "p", "files": {
        "bad": {"session_date": "bad"}, "missing": {}, "none": {"session_date": None},
        "unaware": {"session_date": "2026-01-01T10:00:00"},
        "future": {"session_date": "2030-01-01T10:00:00-08:00"}}}))
    result = pdf.freshness(tmp_path, "p", now=NOW)
    assert not result["available"] and result["partial"]
    with pytest.raises(ValueError, match="unavailable"):
        pdf.index_folder(tmp_path / "missing", "p", tmp_path)


def test_index_command_never_creates_participant_or_runs_a_sync(monkeypatch):
    from modules import RCS08Sync
    participant = NS(uid="p")
    resolve = Mock(return_value=participant)
    index = Mock(return_value={"pdf_files": 2, "dated": 2, "unavailable": 0})
    sync = Mock(side_effect=AssertionError("must not sync"))
    monkeypatch.setattr(RCS08Sync, "resolve_participant", resolve)
    monkeypatch.setattr(RCS08Sync, "run_sync", sync)
    monkeypatch.setattr(pdf, "index_folder", index)
    cmd = Command()
    cmd.stdout = Mock()
    cmd.handle()
    resolve.assert_called_once_with(create=False)
    index.assert_called_once_with(RCS08Sync.NEURAL_FOLDER, "p", RCS08Sync.STORAGE_PATH)
    sync.assert_not_called()
    index.side_effect = ValueError("missing source")
    with pytest.raises(CommandError, match="missing source"):
        cmd.handle()
