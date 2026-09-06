import datetime as dt
import csv
import os
import tempfile
from pathlib import Path
from unittest import mock
from concurrent.futures import ThreadPoolExecutor

from django.test import SimpleTestCase, TestCase
from django.core.management.base import CommandError
from filelock import FileLock

from modules import RCS08ManualSync, RCS08Sync
from modules import DataCurator, Database
from Server import models
from Server.management.commands.run_rcs08_scheduler import Command as Scheduler


class RCS08SyncHelperTests(SimpleTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        patch = mock.patch.object(RCS08Sync, "STORAGE_PATH", Path(temporary.name))
        patch.start()
        self.addCleanup(patch.stop)

    def test_redcap_timestamp_is_pacific_and_dst_aware(self):
        epoch, rendered = RCS08Sync._redcap_timestamp("2026-07-01 03:00:00")
        parsed = dt.datetime.fromtimestamp(epoch, RCS08Sync.LOCAL_TIMEZONE)
        self.assertEqual(parsed.hour, 3)
        self.assertTrue(rendered.endswith("-07:00"))

    def test_redcap_normalization_sums_present_mpq_items_without_fabricating_zero(self):
        row = {
            "record_id": "RCS08",
            "redcap_repeat_instrument": RCS08Sync.REDCAP_INSTRUMENT,
            "redcap_repeat_instance": "7",
            RCS08Sync.REDCAP_TIMESTAMP: "2026-07-01 03:00:00",
            "tiring_exhausting_s1_daily": "2",
            "sickening_s1_daily": "",
            "fearful_s1_daily": "1",
            "cruel_punishing_s1_daily": "",
        }
        records = RCS08Sync._normalized_records([row])
        metrics = list(RCS08Sync.REDCAP_METRICS)
        values = records[0]["record"][0]
        self.assertEqual(values[metrics.index("mpq_aff")], 3.0)
        self.assertIsNone(values[metrics.index("mpq_sen")])
        self.assertEqual(records[0]["name"], "7")

    def test_reviewed_timestamp_corrections_match_fail_closed_keys(self):
        # Invented identities and times exercise exact matching without shipping
        # or reading the participant's reviewed correction table.
        corrections = [dict(
            record_id="SYNTHETIC08", redcap_event_name="synthetic_arm_1",
            redcap_repeat_instrument="synthetic_daily", redcap_repeat_instance=str(i),
            original_redcap_timestamp=f"2020-01-0{i} 10:00:00",
            corrected_survey_start=f"2020-01-0{i} 11:00:00",
        ) for i in range(1, 4)]
        path = RCS08Sync.STORAGE_PATH / "synthetic_timestamp_corrections.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(corrections[0]))
            writer.writeheader()
            writer.writerows(corrections)
        live_rows = [
            {
                "record_id": correction["record_id"],
                "redcap_event_name": correction["redcap_event_name"],
                "redcap_repeat_instrument": correction["redcap_repeat_instrument"],
                "redcap_repeat_instance": correction["redcap_repeat_instance"],
                RCS08Sync.REDCAP_TIMESTAMP: correction["original_redcap_timestamp"],
            }
            for correction in corrections
        ]
        with mock.patch.object(RCS08Sync, "TIMESTAMP_CORRECTIONS_FILE", path):
            corrected, count = RCS08Sync._apply_timestamp_corrections(live_rows)
            for field in live_rows[0]:
                mismatched = [dict(row) for row in live_rows]
                mismatched[0][field] = "nonmatching"
                with self.subTest(field=field), self.assertRaisesRegex(RCS08Sync.SyncError, "exactly one"):
                    RCS08Sync._apply_timestamp_corrections(mismatched)
            with self.assertRaisesRegex(RCS08Sync.SyncError, "exactly one"):
                RCS08Sync._apply_timestamp_corrections(live_rows + [dict(live_rows[0])])
        self.assertEqual(count, 3)
        self.assertEqual(corrected[0][RCS08Sync.REDCAP_TIMESTAMP], corrections[0]["corrected_survey_start"])
        self.assertEqual(live_rows[0][RCS08Sync.REDCAP_TIMESTAMP], corrections[0]["original_redcap_timestamp"])

    def test_oura_merge_replaces_a_refetched_day(self):
        old = {
            key: [] for key in RCS08Sync.OURA_KEYS
        }
        old["DailyReadiness"] = [
            {"StartTime": 10, "Metadata": {"DayLabel": "2026-08-31"}, "value": "old"}
        ]
        incoming = {
            key: [] for key in RCS08Sync.OURA_KEYS
        }
        incoming["DailyReadiness"] = [
            {"StartTime": 10, "Metadata": {"DayLabel": "2026-08-31"}, "value": "new"}
        ]
        merged = RCS08Sync._merge_oura(old, incoming)
        self.assertEqual(len(merged["DailyReadiness"]), 1)
        self.assertEqual(merged["DailyReadiness"][0]["value"], "new")

    def test_fixed_oura_chunks_never_exceed_28_days(self):
        chunks = list(
            RCS08Sync._fixed_chunks(dt.date(2026, 1, 1), dt.date(2026, 3, 1))
        )
        self.assertEqual(chunks[0], (dt.date(2026, 1, 1), dt.date(2026, 1, 28)))
        self.assertTrue(all((end - start).days <= 27 for start, end in chunks))

    def test_one_failed_stream_does_not_starve_the_other_streams(self):
        participant = object()
        with (
            mock.patch.object(RCS08Sync, "resolve_participant", return_value=participant),
            mock.patch.object(RCS08Sync, "sync_redcap", side_effect=RCS08Sync.SyncError("failed")),
            mock.patch.object(RCS08Sync, "sync_oura", return_value={"written": True}) as oura,
            mock.patch.object(RCS08Sync, "sync_neural", return_value={"ingested": 1}) as neural,
        ):
            with self.assertRaises(RCS08Sync.SyncError):
                RCS08Sync.run_sync()
        oura.assert_called_once()
        neural.assert_called_once()

    def test_overlapping_sync_cannot_touch_the_database(self):
        lock_path = RCS08Sync.STORAGE_PATH / "sync-state" / "rcs08-execution.lock"
        lock_path.parent.mkdir(parents=True)
        with FileLock(str(lock_path)), mock.patch.object(RCS08Sync, "resolve_participant") as resolve:
            with self.assertRaisesRegex(RCS08Sync.SyncError, "already running"):
                RCS08Sync.run_sync()
            resolve.assert_not_called()
        with mock.patch.object(RCS08Sync, "resolve_participant"):
            self.assertEqual(RCS08Sync.run_sync(streams=()), {})

    def test_stored_export_runs_after_sync_and_failure_is_visible(self):
        participant = object()
        exported = {"exported_at_utc": "2026-09-05T00:00:00Z", "files": {"test.csv": {"rows": 2}}}
        with (
            mock.patch.dict(os.environ, {"RCS08_EXPORT_DIRECTORY": "/synthetic/exports"}),
            mock.patch.object(RCS08Sync, "resolve_participant", return_value=participant),
            mock.patch.object(RCS08Sync, "sync_oura", return_value={"written": True}) as sync,
            mock.patch("modules.RCS08Exports.export_stored_data", return_value=exported) as export,
        ):
            result = RCS08Sync.run_sync(streams=("oura",))
            self.assertEqual(result["csv_exports"], exported)
            export.assert_called_once_with(participant)
            export.reset_mock()
            RCS08Sync.run_sync(streams=("oura",), dry_run=True)
            RCS08Sync.run_sync(streams=())
            export.assert_not_called()
            export.side_effect = PermissionError("read-only")
            with self.assertRaisesRegex(RCS08Sync.SyncError, "csv_exports: CSV export failed: PermissionError"):
                RCS08Sync.run_sync(streams=("oura",))
            export.side_effect = None
            export.reset_mock()
            sync.side_effect = RCS08Sync.SyncError("API failed")
            with self.assertRaisesRegex(RCS08Sync.SyncError, "oura: API failed"):
                RCS08Sync.run_sync(streams=("oura",))
            export.assert_called_once_with(participant)
            sync.side_effect = None
            export.reset_mock()
            with mock.patch.dict(os.environ, {"RCS08_EXPORT_DIRECTORY": ""}):
                RCS08Sync.run_sync(streams=("oura",))
            export.assert_not_called()


class RCS08ManualSyncStateTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage_patch = mock.patch.object(
            RCS08ManualSync, "STORAGE_PATH", Path(self.temporary.name)
        )
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.temporary.cleanup()

    def test_request_lifecycle_preserves_results(self):
        queued = RCS08ManualSync.queue_request("admin-user")
        claimed = RCS08ManualSync.claim_request()
        self.assertEqual(claimed["request_id"], queued["request_id"])
        self.assertEqual(RCS08ManualSync.get_state()["status"], "running")

        results = {"redcap": {"records": 4}, "neural": {"ingested": 0}}
        RCS08ManualSync.complete_request(queued["request_id"], results)
        completed = RCS08ManualSync.get_state()
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["results"], results)

    def test_scheduler_restart_releases_running_request(self):
        RCS08ManualSync.queue_request("admin-user")
        RCS08ManualSync.claim_request()
        RCS08ManualSync.fail_interrupted_request()
        self.assertEqual(RCS08ManualSync.get_state()["status"], "failed")
        retried = RCS08ManualSync.queue_request("admin-user")
        self.assertEqual(retried["status"], "queued")

    def test_concurrent_clicks_queue_only_one_request(self):
        def queue(user):
            try:
                return RCS08ManualSync.queue_request(str(user))
            except RCS08ManualSync.ManualSyncAlreadyActive:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(queue, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)
        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda _: RCS08ManualSync.claim_request(), range(8)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)

    def test_second_scheduler_cannot_mark_a_live_job_interrupted(self):
        RCS08ManualSync.queue_request("admin-user")
        RCS08ManualSync.claim_request()
        with RCS08ManualSync.scheduler_lock():
            with self.assertRaisesRegex(CommandError, "already running"):
                Scheduler().handle()
        self.assertEqual(RCS08ManualSync.get_state()["status"], "running")

    def test_late_completion_cannot_overwrite_a_new_request(self):
        old = RCS08ManualSync.queue_request("admin-user")
        RCS08ManualSync.claim_request()
        RCS08ManualSync.fail_interrupted_request()
        new = RCS08ManualSync.queue_request("admin-user")
        RCS08ManualSync.complete_request(old["request_id"], {})
        self.assertEqual(RCS08ManualSync.get_state()["request_id"], new["request_id"])
        self.assertEqual(RCS08ManualSync.get_state()["status"], "queued")


class RCS08SyncWriteTests(TestCase):
    """Synthetic writes in a disposable database and directory, never live data."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        for module, name, value in (
            (RCS08Sync, "STORAGE_PATH", self.storage),
            (RCS08Sync, "NEURAL_FOLDER", str(self.storage / "neural")),
            (DataCurator, "DATABASE_PATH", str(self.storage) + "/"),
            (Database, "DATABASE_PATH", str(self.storage) + "/"),
        ):
            patch = mock.patch.object(module, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        (self.storage / "cache").mkdir()
        (self.storage / "neural").mkdir()
        institute = models.Institute.objects.create(name="Synthetic test")
        self.participant = models.Participant.objects.create(name="Synthetic RCS08", institute=institute)

    def test_interrupted_neural_import_rolls_back_marker_and_retries(self):
        (self.storage / "neural" / "sample.json").write_text('{"synthetic": true}')

        def interrupted(source, person):
            models.Recording.objects.create(source=source, name="partial synthetic recording")
            raise KeyboardInterrupt("simulate worker interruption")

        with mock.patch.object(DataCurator, "MedtronicPerceptJSONDecoder", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                RCS08Sync.sync_neural(self.participant)
        self.assertFalse(models.SourceFile.objects.exists())
        self.assertFalse(models.Recording.objects.exists())
        with mock.patch.object(DataCurator, "MedtronicPerceptJSONDecoder") as decoder:
            self.assertEqual(RCS08Sync.sync_neural(self.participant)["ingested"], 1)
            self.assertEqual(RCS08Sync.sync_neural(self.participant)["ingested"], 0)
            decoder.assert_called_once()

    def test_identical_neural_files_in_one_scan_are_imported_once(self):
        for name in ("first.json", "duplicate.json"):
            (self.storage / "neural" / name).write_text('{"synthetic": true}')
        with mock.patch.object(DataCurator, "MedtronicPerceptJSONDecoder") as decoder:
            result = RCS08Sync.sync_neural(self.participant)
        self.assertEqual(result["ingested"], 1)
        decoder.assert_called_once()

    def test_oura_interruption_preserves_previous_file_and_database_hash(self):
        old = RCS08Sync._save_oura_snapshot(self.participant, {"synthetic": "old"})
        pointer, hashed = old.pointer, old.hashed
        with mock.patch.object(models.SourceFile, "save", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                RCS08Sync._save_oura_snapshot(self.participant, {"synthetic": "new"})
        old.refresh_from_db()
        self.assertEqual((old.pointer, old.hashed), (pointer, hashed))
        self.assertEqual(Database.loadSourceFile(pointer, hashed), {"synthetic": "old"})
        new = RCS08Sync._save_oura_snapshot(self.participant, {"synthetic": "new"})
        self.assertNotEqual(new.pointer, pointer)
        self.assertEqual(Database.loadSourceFile(new.pointer, new.hashed), {"synthetic": "new"})
        self.assertEqual(Database.loadSourceFile(pointer, hashed), {"synthetic": "old"})

    def test_failed_oura_file_write_cannot_publish_an_invalid_hash(self):
        with mock.patch.object(Database, "saveSourceFile", return_value=False):
            with self.assertRaises(RCS08Sync.SyncError):
                RCS08Sync._save_oura_snapshot(self.participant, {})
        self.assertFalse(models.SourceFile.objects.exists())
