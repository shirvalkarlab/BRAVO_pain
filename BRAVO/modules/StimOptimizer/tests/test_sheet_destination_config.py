"""External export has no inherited destination and refuses missing configuration."""
import pytest
from modules.StimOptimizer import google_sheets_client as client
from modules.StimOptimizer import sheet_export


@pytest.mark.parametrize("getter,key", [
    (client.folder_id, "CLINIC_SHEETS_DRIVE_FOLDER_ID"),
    (client.template_id, "CLINIC_SHEETS_TEMPLATE_ID"),
])
def test_destination_must_be_explicit(monkeypatch, getter, key):
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match=key):
        getter()
    monkeypatch.setenv(key, "  ")
    with pytest.raises(ValueError, match=key):
        getter()
    monkeypatch.setenv(key, "  synthetic-owned-destination  ")
    assert getter() == "synthetic-owned-destination"


def test_missing_destination_precedes_client_import_or_network(monkeypatch):
    monkeypatch.delenv("CLINIC_SHEETS_DRIVE_FOLDER_ID", raising=False)
    with pytest.raises(ValueError, match="CLINIC_SHEETS_DRIVE_FOLDER_ID"):
        client.GoogleClient()
    # An injected client must not receive even a read request without configuration.
    class NoNetwork:
        def __getattr__(self, name):
            raise AssertionError("network operation attempted: " + name)
    with pytest.raises(ValueError, match="CLINIC_SHEETS_DRIVE_FOLDER_ID"):
        sheet_export.export({"sheet_rows": [[1]], "sheet_columns": ["value"]},
                            "synthetic", "2026-01-01", drive=NoNetwork())
