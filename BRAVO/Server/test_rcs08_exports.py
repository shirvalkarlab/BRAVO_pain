"""Portable synthetic tests for the local CSV export boundary."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import numpy as np
from filelock import FileLock, Timeout
from modules import RCS08Exports as exports


def record(*, timed=False, empty=False):
    result = {
        "StartTime": 1762072200, "SamplingRate": 1 / 300, "Duration": 600,
        "ChannelNames": ["HR", "State"],
        "Data": np.array([[60, 0], [-1, 1]]) if not empty else np.zeros((0, 2)),
        "Missing": np.array([[0, 0], [1, 0]]) if not empty else np.zeros((0, 2)),
        "Metadata": {"DayLabel": "2025-11-02", "ScoreContributors": {"sleep": 10}},
        "Descriptor": {"StateLabels": ["rest", "awake"], "Absent": None},
    }
    if timed:
        result["Time"] = [1762072200, 1762075800]
    return result


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.args = {"reviewed_csv": 'survey_start,include_in_analysis,note\n2025-11-02,False,"two\nlines"\n',
                     "stim_dates_csv": "date,event_type\n2025-11-02,clinic\n",
                     "oura": {"HeartRate": [record(timed=True)], "Sleep": [record()]},
                     "provenance": {"participant": "synthetic"}}

    def test_complete_snapshot_retains_values_flags_and_source_csvs(self):
        (self.path / "unrelated.txt").write_text("retain")
        report = exports.write_snapshot(self.path, **self.args)
        self.assertEqual(len(report["files"]), 12)
        self.assertEqual(report["files"]["REDCap/rcs08_pain_data.csv"]["rows"], 1)
        self.assertEqual((self.path / "REDCap/rcs08_pain_data.csv").read_text(), self.args["reviewed_csv"])
        with (self.path / "Oura/oura_heart_rate_samples.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([r["HR"] for r in rows], ["60", "-1"])
        self.assertEqual(rows[1]["HR__missing"], "1")
        # Explicit observation times survive; these span the DST fallback hour.
        self.assertEqual(rows[0]["timestamp_local"], "2025-11-02T01:30:00-07:00")
        self.assertEqual(rows[1]["timestamp_local"], "2025-11-02T01:30:00-08:00")
        with (self.path / "Oura/oura_sleep_samples.csv").open() as handle:
            samples = list(csv.DictReader(handle))
        self.assertEqual(float(samples[1]["timestamp_epoch_seconds"]) - float(samples[0]["timestamp_epoch_seconds"]), 300)
        summary = list(csv.DictReader(io.StringIO((self.path / "Oura/oura_heart_rate.csv").read_text())))[0]
        self.assertEqual(json.loads(summary["Descriptor.StateLabels"]), ["rest", "awake"])
        self.assertEqual(summary["Metadata.ScoreContributors.sleep"], "10")
        for name, details in report["files"].items():
            self.assertEqual(hashlib.sha256((self.path / name).read_bytes()).hexdigest(), details["sha256"])
        self.assertEqual((self.path / "unrelated.txt").read_text(), "retain")
        report2 = exports.write_snapshot(self.path, **self.args)
        self.assertEqual(report["files"], report2["files"])
        self.assertFalse(list(self.path.glob(".rcs08-export-*/")))

    def test_unknown_or_malformed_data_keeps_previous_bundle(self):
        previous = exports.write_snapshot(self.path, **self.args)
        self.args["oura"]["NewStream"] = []
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            exports.write_snapshot(self.path, **self.args)
        self.assertEqual(json.loads((self.path / "export_manifest.json").read_text()), previous)
        self.args["oura"] = {}
        self.args["reviewed_csv"] = ""
        with self.assertRaisesRegex(ValueError, "header"):
            exports.write_snapshot(self.path, **self.args)
        self.assertEqual(json.loads((self.path / "export_manifest.json").read_text()), previous)

    def test_missing_destination_lock_and_write_failure_are_not_success(self):
        with self.assertRaises(FileNotFoundError):
            exports.write_snapshot(self.path / "missing", **self.args)
        with FileLock(str(self.path / ".rcs08-export.lock")):
            with self.assertRaises(Timeout):
                exports.write_snapshot(self.path, **self.args)
        with mock.patch.object(exports.os, "replace", side_effect=PermissionError("readonly")):
            with self.assertRaises(PermissionError):
                exports.write_snapshot(self.path, **self.args)
        self.assertFalse((self.path / "export_manifest.json").exists())
        self.assertFalse(list(self.path.glob(".rcs08-export-*/")))

    def test_sample_schema_failures_and_empty_samples(self):
        zone = ZoneInfo("UTC")
        bad = record()
        bad["Missing"] = []
        with self.assertRaisesRegex(ValueError, "length"):
            list(exports.sample_rows([bad], zone))
        bad = record(timed=True)
        bad["Time"] = [1]
        with self.assertRaisesRegex(ValueError, "length"):
            list(exports.sample_rows([bad], zone))
        for key in ("Data", "Missing"):
            bad = record()
            bad[key] = [[1], [1]]
            with self.assertRaisesRegex(ValueError, "width"):
                list(exports.sample_rows([bad], zone))
        self.assertEqual(list(exports.sample_rows([record(empty=True)], zone)), [])

    def test_interrupted_publication_leaves_detectable_manifest_and_retry_recovers(self):
        previous = exports.write_snapshot(self.path, **self.args)
        self.args["reviewed_csv"] += "2025-11-03,True,another observation\n"
        real_replace = os.replace

        def interrupted_replace(source, target):
            if Path(target).name == "rcs08_stim_testing_dates.csv":
                raise OSError("synthetic interruption after first CSV")
            return real_replace(source, target)

        with mock.patch.object(exports.os, "replace", side_effect=interrupted_replace):
            with self.assertRaisesRegex(OSError, "synthetic interruption"):
                exports.write_snapshot(self.path, **self.args)
        # A partial generation must never be advertised by a new manifest.
        self.assertEqual(json.loads((self.path / "export_manifest.json").read_text()), previous)
        pain_path = "REDCap/rcs08_pain_data.csv"
        self.assertNotEqual(hashlib.sha256((self.path / pain_path).read_bytes()).hexdigest(),
                            previous["files"][pain_path]["sha256"])
        self.assertFalse(list(self.path.glob(".rcs08-export-*/")))
        # The next ordinary export recovers without deleting unrelated files.
        (self.path / "lab_notes.txt").write_text("preserve")
        recovered = exports.write_snapshot(self.path, **self.args)
        self.assertEqual(recovered["files"][pain_path]["rows"], 2)
        for name, details in recovered["files"].items():
            self.assertEqual(hashlib.sha256((self.path / name).read_bytes()).hexdigest(), details["sha256"])
        self.assertEqual((self.path / "lab_notes.txt").read_text(), "preserve")

    def test_database_adapter_selects_saved_sources_and_never_fetches(self):
        source = SimpleNamespace(uid="audit", pointer="audit-file", hashed="audit-hash")
        oura = SimpleNamespace(pointer="oura-file", hashed="oura-hash")
        source_model = mock.MagicMock()
        source_model.objects.filter.return_value.order_by.return_value.first.return_value = source
        source_model.find.return_value = oura
        database = mock.MagicMock()
        database.loadSourceFile.side_effect = [{"reviewed_csv": self.args["reviewed_csv"]}, self.args["oura"]]
        server = SimpleNamespace(models=SimpleNamespace(SourceFile=source_model))
        import modules
        calendar = self.path / "rcs08_stim_testing_dates.csv"
        calendar.write_text(self.args["stim_dates_csv"])
        with mock.patch.dict("sys.modules", {"Server": server}), mock.patch.object(modules, "Database", database, create=True), \
                mock.patch.dict(os.environ, {"RCS08_EXPORT_DIRECTORY": str(self.path), "RCS08_PROCESSING_RULES": str(self.path)}):
            result = exports.export_stored_data(SimpleNamespace(uid="patient"))
            self.assertEqual(result["source"]["oura_source_hash"], "oura-hash")
            self.assertEqual(database.loadSourceFile.call_args_list,
                             [mock.call("audit-file", "audit-hash"), mock.call("oura-file", "oura-hash")])
            source_model.objects.filter.return_value.order_by.return_value.first.return_value = None
            with self.assertRaisesRegex(ValueError, "survey audit"):
                exports.export_stored_data(SimpleNamespace(uid="patient"), str(self.path))
            source_model.objects.filter.return_value.order_by.return_value.first.return_value = source
            database.loadSourceFile.side_effect = None
            database.loadSourceFile.return_value = {"reviewed_csv": self.args["reviewed_csv"]}
            source_model.find.return_value = None
            with self.assertRaisesRegex(ValueError, "Oura snapshot"):
                exports.export_stored_data(SimpleNamespace(uid="patient"))
        with mock.patch.dict("sys.modules", {"Server": server}), mock.patch.object(modules, "Database", database, create=True), \
                mock.patch.dict(os.environ, {"RCS08_EXPORT_DIRECTORY": ""}):
            with self.assertRaisesRegex(ValueError, "not configured"):
                exports.export_stored_data(SimpleNamespace(uid="patient"))


class ExportCommandTests(unittest.TestCase):
    """Exercise the supported command boundary without network or private data."""

    def test_command_passes_destination_and_only_prints_publication_result(self):
        from django.core.management import call_command
        from Server.management.commands import export_rcs08

        participant = SimpleNamespace(uid="synthetic-participant")
        manifest = {"exported_at_utc": "2026-01-02T03:04:05+00:00",
                    "files": {"REDCap/rcs08_pain_data.csv": {"rows": 3, "sha256": "synthetic-hash"}},
                    "source": {"internal_audit": "not printed"}}
        for argv, expected in (([], None), (["--destination", "/synthetic/export"], "/synthetic/export")):
            with self.subTest(destination=expected):
                output = io.StringIO()
                with mock.patch.object(export_rcs08.RCS08Sync, "resolve_participant", return_value=participant) as resolve, \
                        mock.patch.object(export_rcs08.RCS08Exports, "export_stored_data", return_value=manifest) as export:
                    call_command("export_rcs08", *argv, stdout=output)
                resolve.assert_called_once_with()
                export.assert_called_once_with(participant, expected)
                self.assertEqual(json.loads(output.getvalue()),
                                 {"exported_at_utc": manifest["exported_at_utc"], "files": manifest["files"]})

    def test_command_failure_has_no_success_output_and_preserves_cause(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from Server.management.commands import export_rcs08

        for failure_stage in ("participant", "export"):
            with self.subTest(stage=failure_stage):
                output = io.StringIO()
                failure = ValueError("synthetic unavailable input")
                with mock.patch.object(export_rcs08.RCS08Sync, "resolve_participant",
                                       side_effect=failure if failure_stage == "participant" else None,
                                       return_value=SimpleNamespace(uid="synthetic")), \
                        mock.patch.object(export_rcs08.RCS08Exports, "export_stored_data",
                                          side_effect=failure if failure_stage == "export" else None) as export:
                    with self.assertRaisesRegex(CommandError, "RCS08 CSV export failed: ValueError") as caught:
                        call_command("export_rcs08", stdout=output)
                    if failure_stage == "participant":
                        export.assert_not_called()
                    else:
                        export.assert_called_once()
                self.assertIs(caught.exception.__cause__, failure)
                self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
