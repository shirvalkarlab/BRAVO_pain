"""Synthetic runtime coverage of the sync publication and retry boundaries.

These tests import the real module, use disposable ORM/storage, and replace only
external API/decoder/canonicalization boundaries. No deployment data is needed.
"""
import pytest
import csv
import datetime as dt
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pandas as pd
import requests
from django.test import TestCase

from Server import models
from modules import Database, DataCurator, RCS08Sync


@pytest.mark.usefixtures("synthetic_oura_policy")
class SyncRuntimeTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)
        (self.storage / "rcs08_study_stages.csv").write_text("stage,start_date,end_date\nstage_0,2025-05-27,2025-06-06\nstage_1,2025-07-16,2025-07-29\nstage_2,2025-07-30,\n")
        self.neural = self.storage / "neural"
        self.neural.mkdir()
        (self.storage / "cache").mkdir()
        for module, key, value in (
            (RCS08Sync, "STORAGE_PATH", self.storage),
            (RCS08Sync, "NEURAL_FOLDER", str(self.neural)),
            (RCS08Sync, "PARTICIPANT_NAME", "Synthetic RCS08"),
            (RCS08Sync, "HASH_KEY", "synthetic-only"),
            (Database, "DATABASE_PATH", str(self.storage) + "/"),
            (DataCurator, "DATABASE_PATH", str(self.storage) + "/"),
        ):
            patch = mock.patch.object(module, key, value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.dict(os.environ, {"DATASERVER_PATH": str(self.storage) + "/", "RCS08_INSTITUTE_NAME": "", "RCS08_PROCESSING_RULES": str(self.storage)})
        patch.start()
        self.addCleanup(patch.stop)
        self.institute = models.Institute.objects.create(name="Synthetic institute")
        self.participant = models.Participant.objects.create(name="Synthetic RCS08", institute=self.institute)
        (self.storage / "recordings" / self.participant.uid).mkdir(parents=True)

    def test_secret_validation_does_not_need_real_credentials(self):
        path = self.storage / "credentials.json"
        with self.assertRaisesRegex(RCS08Sync.SyncError, "missing"):
            RCS08Sync._load_secret(str(path), ("token",))
        path.write_text("not-json")
        with self.assertRaisesRegex(RCS08Sync.SyncError, "unreadable"):
            RCS08Sync._load_secret(str(path), ("token",))
        path.write_text('{"token": ""}')
        with self.assertRaisesRegex(RCS08Sync.SyncError, "missing keys"):
            RCS08Sync._load_secret(str(path), ("token",))
        path.write_text('{"token": "synthetic-only"}')
        self.assertEqual(RCS08Sync._load_secret(str(path), ("token",))["token"], "synthetic-only")

    def test_resolve_existing_and_renamed_audit_owner(self):
        self.assertEqual(RCS08Sync.resolve_participant(), self.participant)
        self.participant.name = "Renamed synthetic participant"
        self.participant.save()
        models.SourceFile.objects.create(type="RCS08SurveyAudit", owner=self.participant)
        self.assertEqual(RCS08Sync.resolve_participant(create=True), self.participant)
        other = models.Participant.objects.create(name="Other", institute=self.institute)
        models.SourceFile.objects.create(type="RCS08SurveyAudit", owner=other)
        with self.assertRaisesRegex(RCS08Sync.SyncError, "Multiple participants"):
            RCS08Sync.resolve_participant(create=True)
        self.assertEqual(models.Participant.objects.count(), 2)

    def test_resolve_creation_requires_an_unambiguous_institute(self):
        self.participant.delete()
        with self.assertRaisesRegex(RCS08Sync.SyncError, "does not exist"):
            RCS08Sync.resolve_participant()
        other = models.Institute.objects.create(name="Second institute")
        with self.assertRaisesRegex(RCS08Sync.SyncError, "exactly one"):
            RCS08Sync.resolve_participant(create=True)
        with mock.patch.dict(os.environ, {"RCS08_INSTITUTE_NAME": "Missing institute"}):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "configured institute"):
                RCS08Sync.resolve_participant(create=True)
        with mock.patch.dict(os.environ, {"RCS08_INSTITUTE_NAME": other.name}):
            created = RCS08Sync.resolve_participant(create=True)
        self.assertEqual(created.institute, other)
        self.assertEqual(created.diagnosis, "Chronic Pain")
        created.delete()
        other.delete()
        self.assertEqual(RCS08Sync.resolve_participant(create=True).institute, self.institute)

    def test_orphaned_audit_resolution_is_explicit(self):
        self.participant.name = "Renamed"
        self.participant.save()
        models.SourceFile.objects.create(type="RCS08SurveyAudit", owner=self.participant)
        with mock.patch.object(models.Participant, "find", return_value=None):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "could not be resolved"):
                RCS08Sync.resolve_participant()

    def test_neural_prerequisites_and_dry_run_limit(self):
        with mock.patch.object(RCS08Sync, "HASH_KEY", ""):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "HASHKEY"):
                RCS08Sync.sync_neural(self.participant)
        with mock.patch.object(RCS08Sync, "NEURAL_FOLDER", str(self.storage / "missing")):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "folder is missing"):
                RCS08Sync.sync_neural(self.participant)
        with self.assertRaisesRegex(RCS08Sync.SyncError, "no JSON"):
            RCS08Sync.sync_neural(self.participant)
        for name in ("one", "two"):
            (self.neural / (name + ".json")).write_text(name)
        with mock.patch.object(DataCurator, "MedtronicPerceptJSONDecoder") as decoder:
            result = RCS08Sync.sync_neural(self.participant, dry_run=True, limit=1)
        self.assertEqual(result, {"found": 2, "existing": 0, "new": 1, "ingested": 0, "failed": 0})
        decoder.assert_not_called()
        self.assertFalse(models.SourceFile.objects.exists())

    def test_unreadable_neural_scan_is_actionable(self):
        (self.neural / "one.json").write_text("one")
        with mock.patch.object(Path, "read_bytes", side_effect=OSError("synthetic")):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "could not be read"):
                RCS08Sync.sync_neural(self.participant)

    def test_neural_file_changed_after_scan_is_not_published(self):
        (self.neural / "one.json").write_text("one")
        with mock.patch.object(Path, "read_bytes", side_effect=[b"one", b"changed"]):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "1 failed file"):
                RCS08Sync.sync_neural(self.participant)
        self.assertFalse(models.SourceFile.objects.exists())

    def test_decoder_failure_rolls_back_and_later_files_continue(self):
        for name in ("bad", "good"):
            (self.neural / (name + ".json")).write_text(json.dumps({"fixture": name}))
        with mock.patch.object(DataCurator, "MedtronicPerceptJSONDecoder", side_effect=[ValueError("synthetic"), None]):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "1 file\\(s\\) succeeded"):
                RCS08Sync.sync_neural(self.participant)
        self.assertEqual(models.SourceFile.objects.count(), 1)
        with mock.patch.object(DataCurator, "MedtronicPerceptJSONDecoder"):
            retry = RCS08Sync.sync_neural(self.participant)
        self.assertEqual((retry["existing"], retry["ingested"]), (1, 1))

    def test_failed_cleanup_does_not_hide_decoder_failure(self):
        (self.neural / "bad.json").write_text(json.dumps({"fixture": "bad"}))
        with mock.patch.object(DataCurator, "MedtronicPerceptJSONDecoder", side_effect=ValueError), mock.patch.object(Database, "deleteSourceFile", side_effect=OSError):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "retries remain safe"):
                RCS08Sync.sync_neural(self.participant)
        self.assertFalse(models.SourceFile.objects.exists())

    def test_neural_privacy_preserves_original_and_deduplication(self):
        report = {
            "PatientInformation": {"Initial": {
                "PatientFirstName": "SYNTHETIC_FIRST", "PatientLastName": "SYNTHETIC_LAST",
                "PatientId": "SYNTHETIC_IDENTIFIER", "PatientDateOfBirth": "1900-01-01"}},
            "SessionDate": "2026-01-02T03:04:05Z", "samples": [1, 4, 2],
        }
        original = json.dumps(report).encode()
        path = self.neural / "synthetic.json"
        path.write_bytes(original)
        observed = []
        def decode(source, **kwargs):
            observed.append(json.loads(DataCurator.loadCacheFile(source)))
        with mock.patch.object(DataCurator, "MedtronicPerceptJSONDecoder", side_effect=decode):
            first = RCS08Sync.sync_neural(self.participant)
            second = RCS08Sync.sync_neural(self.participant)
        self.assertEqual((first["ingested"], second["existing"]), (1, 1))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["SessionDate"], report["SessionDate"])
        self.assertEqual(observed[0]["samples"], report["samples"])
        self.assertEqual(observed[0]["PatientInformation"]["Initial"], {
            "PatientFirstName": "", "PatientLastName": "", "PatientId": "Synthetic RCS08",
            "PatientDateOfBirth": ""})
        self.assertEqual(models.SourceFile.objects.count(), 1)

    def test_redcap_transport_and_payload_validation(self):
        with mock.patch.object(RCS08Sync, "_load_secret", return_value={"api_url": "https://example.invalid/api", "api_key": "synthetic"}), mock.patch.object(RCS08Sync.requests, "post") as post:
            post.side_effect = requests.RequestException("synthetic")
            with self.assertRaisesRegex(RCS08Sync.SyncError, "request failed"):
                RCS08Sync.fetch_redcap_rows()
            post.side_effect = None
            post.return_value.json.return_value = {"error": "synthetic"}
            with self.assertRaisesRegex(RCS08Sync.SyncError, "unexpected payload"):
                RCS08Sync.fetch_redcap_rows()
            post.return_value.json.return_value = [{"record_id": "other"}]
            with self.assertRaisesRegex(RCS08Sync.SyncError, "no matching"):
                RCS08Sync.fetch_redcap_rows()
            wanted = {"record_id": "Synthetic RCS08", "value": "retained"}
            post.return_value.json.return_value = [{"record_id": "other"}, wanted]
            self.assertEqual(RCS08Sync.fetch_redcap_rows(), [wanted])
            self.assertEqual(post.call_args.kwargs["data"]["records[0]"], "Synthetic RCS08")
            self.assertEqual(post.call_args.kwargs["timeout"], 120)

    def test_legacy_normalization_keeps_zero_and_distinct_repeat_instances(self):
        rows = [{}, {RCS08Sync.REDCAP_TIMESTAMP: "2026-01-02T11:00:00+00:00", "redcap_repeat_instance": "1", "pain_nrs_s1_daily": "0"}]
        rows += [dict(rows[1]), {**rows[1], "redcap_repeat_instance": "2"}]
        result = RCS08Sync._normalized_records(rows)
        self.assertEqual([r["name"] for r in result], ["1", "2"])
        self.assertEqual(result[0]["record"][0][0], 0)
        for value in ("nonsense", "nan", "inf", [], None, ""):
            self.assertIsNone(RCS08Sync._number(value))
        with self.assertRaises(RCS08Sync.SyncError):
            RCS08Sync._redcap_timestamp("invalid")
        with self.assertRaises(RCS08Sync.SyncError):
            RCS08Sync._normalized_records([{}])
        fields = RCS08Sync._redcap_fields()
        self.assertIn("pain_nrs_s1_daily", fields)
        self.assertNotIn("redcap_repeat_instance", fields)

    def test_timestamp_correction_table_fails_closed(self):
        path = self.storage / "corrections.csv"
        row = {"record_id": "Synthetic RCS08", "redcap_event_name": "visit", "redcap_repeat_instrument": "daily", "redcap_repeat_instance": "1", "original_redcap_timestamp": "2026-01-02 03:00:00", "corrected_survey_start": "2026-01-02 02:00:00"}
        def write(rows):
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                writer.writerows(rows)
        with mock.patch.object(RCS08Sync, "TIMESTAMP_CORRECTIONS_FILE", str(path)):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "missing"):
                RCS08Sync._apply_timestamp_corrections([])
            for rows, message in (([], "empty"), ([{**row, "record_id": ""}], "blank match"), ([row, row], "duplicate match"), ([{**row, "corrected_survey_start": ""}], "no corrected time"), ([row], "exactly one")):
                write(rows)
                with self.assertRaisesRegex(RCS08Sync.SyncError, message):
                    RCS08Sync._apply_timestamp_corrections([])
            live = {**row, RCS08Sync.REDCAP_TIMESTAMP: row["original_redcap_timestamp"]}
            corrected, count = RCS08Sync._apply_timestamp_corrections([{}, live])
            self.assertEqual(count, 1)
            self.assertEqual(corrected[1][RCS08Sync.REDCAP_TIMESTAMP], row["corrected_survey_start"])
            self.assertEqual(live[RCS08Sync.REDCAP_TIMESTAMP], row["original_redcap_timestamp"])
            with self.assertRaisesRegex(RCS08Sync.SyncError, "exactly one"):
                RCS08Sync._apply_timestamp_corrections([live, live])

    def canonical_frame(self):
        frame = pd.DataFrame([
            dict(include_in_analysis=True, exclusion_reason="", study_stage="stage_2", survey_start="2026-01-02T03:00:00-08:00", nrs_intensity=0, vas_intensity=float("nan"), timestamp_source="redcap", stim_testing_date=False, vas_default_zero_suspect=True, source_event="visit", source_instrument="daily", repeat_instance="1"),
            dict(include_in_analysis=False, exclusion_reason="intentional stimulation-testing day", study_stage="stage_2", survey_start="2026-01-03T03:00:00-08:00", nrs_intensity=8, timestamp_source="corrected", stim_testing_date=True, vas_default_zero_suspect=False, source_event="visit", source_instrument="daily", repeat_instance="2"),
        ])
        frame.attrs["timeline_testing_days"] = ["2026-01-03", "2026-01-07"]
        frame.attrs["timeline_testing_days_sha256"] = "b" * 64
        return frame

    def test_canonical_redcap_publication_preserves_audit_and_is_idempotent(self):
        frame = self.canonical_frame()
        from modules.RCS08SurveyProcessing import STANDARD_MPQ
        for index, name in enumerate(STANDARD_MPQ):
            frame[f"mpq_{name}"] = index % 4
        with mock.patch.object(RCS08Sync, "fetch_redcap_rows", return_value=[{"synthetic_raw": True}]), mock.patch("modules.RCS08SurveyProcessing.canonicalize_rows", return_value=frame), mock.patch("modules.ReportCache.invalidate") as invalidate:
            preview = RCS08Sync.sync_redcap(self.participant, dry_run=True)
            self.assertEqual((preview["included"], preview["excluded"], preview["written"]), (1, 1, 0))
            self.assertFalse(models.ScaleForms.objects.exists())
            result = RCS08Sync.sync_redcap(self.participant)
            self.assertEqual(result["written"], 1)
            record = models.ScaleRecord.objects.get(participant=self.participant)
            self.assertEqual(record.name, "visit:daily:1")
            self.assertEqual(record.record[0][:2], [0, None])
            self.assertEqual(len(record.record[0]), 29)
            self.assertEqual(record.record[0][13:28], [index % 4 for index in range(15)])
            form = models.ScaleForms.objects.get(name=RCS08Sync.REDCAP_FORM_NAME)
            self.assertEqual([q["variableName"] for q in form.record[0]["questions"]][13:28],
                             [f"mpq_{name}" for name in STANDARD_MPQ])
            self.assertEqual(form.record[0]["processing"]["timeline_schema"], "redcap-pretrial-1")
            self.assertEqual(len(form.record[0]["processing"]["timeline_phases"]), 5)
            self.assertEqual(form.record[0]["processing"]["timeline_testing_days"], ["2026-01-03", "2026-01-07"])
            self.assertEqual(form.record[0]["processing"]["timeline_testing_days_sha256"], "b" * 64)
            from modules.RedcapVisitContext import read
            self.assertIsInstance(form.record[0]['visit_context'], str)
            context = read(form, float('inf'))
            self.assertEqual(context['reviewed_sha256'], form.record[0]['processing']['reviewed_sha256'])
            self.assertTrue(context['available'])
            self.assertEqual(context['metrics']['nrs_intensity'][0]['value'], 8)
            self.assertEqual(context['metrics']['nrs_intensity'][0]['record'], 'visit:daily:2')
            self.assertEqual(context['metrics']['nrs_intensity'][0]['time'],
                             dt.datetime.fromisoformat('2026-01-03T03:00:00-08:00').timestamp())
            self.assertEqual(models.ScaleRecord.objects.filter(participant=self.participant).count(), 1)
            audit = models.SourceFile.objects.get(type="RCS08SurveyAudit")
            payload = Database.loadSourceFile(audit.pointer, audit.hashed)
            self.assertEqual(payload["raw_rows"], [{"synthetic_raw": True}])
            self.assertIn("False", payload["reviewed_csv"])
            published_invalidations = invalidate.call_count
            self.assertGreater(published_invalidations, 0)
            self.assertFalse(RCS08Sync.sync_redcap(self.participant)["changed"])
            self.assertEqual(invalidate.call_count, published_invalidations)
            self.assertEqual(models.SourceFile.objects.count(), 1)
            frame.loc[0, "nrs_intensity"] = 2
            self.assertEqual(RCS08Sync.sync_redcap(self.participant)["written"], 1)
            self.assertEqual(models.ScaleRecord.objects.get(participant=self.participant).record[0][0], 2)
            self.assertEqual(models.ParticipantLinkRel.objects.count(), 1)
            self.assertGreater(invalidate.call_count, published_invalidations)

    def test_optional_home_adjustments_preserve_exact_source_cells_and_routine_scores(self):
        frame = self.canonical_frame()
        expected_hash = hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()
        path = self.storage / 'rcs08_home_program_adjustments.csv'
        fields = ['date', 'time', 'group', 'amplitude_mA', 'notes', 'source']
        cells = [dict(date='2026-01-04', time='', group='A', amplitude_mA='2.00',
                      notes='First line, with comma\nSecond line', source='reviewed note'),
                 dict(date='2026-01-05', time='10:30', group='B', amplitude_mA='',
                      notes='', source='another note')]
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader(); writer.writerows(cells)
        exact_bytes = ('\ufeff' + output.getvalue()).encode('utf-8')
        baseline_records = None
        with mock.patch.object(RCS08Sync, 'fetch_redcap_rows', return_value=[{'synthetic_raw': True}]), \
             mock.patch('modules.RCS08SurveyProcessing.canonicalize_rows', return_value=frame), \
             mock.patch('modules.ReportCache.invalidate'):
            for raw in [None, b'', b'date,time,group,amplitude_mA,notes,source\n', exact_bytes]:
                with self.subTest(source_state='missing' if raw is None else len(raw)):
                    if raw is not None:
                        path.write_bytes(raw)
                    result = RCS08Sync.sync_redcap(self.participant)
                    stored = models.ScaleForms.objects.get(name=RCS08Sync.REDCAP_FORM_NAME)
                    audit = stored.record[0]['processing']
                    self.assertEqual(audit['timeline_home_adjustments_sha256'],
                                     hashlib.sha256(raw or b'').hexdigest())
                    self.assertEqual(audit['timeline_home_adjustments'], cells if raw == exact_bytes else [])
                    self.assertEqual(audit['reviewed_sha256'], expected_hash)
                    self.assertEqual(audit['timeline_testing_days'], frame.attrs['timeline_testing_days'])
                    self.assertEqual(result['included'], 1)
                    rows = list(models.ScaleRecord.objects.filter(participant=self.participant)
                                .values_list('name', 'date', 'record'))
                    if baseline_records is None:
                        baseline_records = rows
                    self.assertEqual(rows, baseline_records)
                    for source in models.SourceFile.objects.filter(type='RCS08SurveyAudit'):
                        payload = Database.loadSourceFile(source.pointer, source.hashed)
                        self.assertEqual(hashlib.sha256(payload['reviewed_csv'].encode()).hexdigest(), expected_hash)
            self.assertFalse(RCS08Sync.sync_redcap(self.participant)['changed'])

    def test_no_approved_surveys_cannot_replace_existing_data(self):
        frame = self.canonical_frame()
        frame["include_in_analysis"] = False
        with mock.patch.object(RCS08Sync, "fetch_redcap_rows", return_value=[]), mock.patch("modules.RCS08SurveyProcessing.canonicalize_rows", return_value=frame):
            with self.assertRaisesRegex(RCS08Sync.SyncError, "existing data retained"):
                RCS08Sync.sync_redcap(self.participant)
        self.assertFalse(models.ScaleForms.objects.exists())

    def test_oura_identity_merge_retains_gaps_and_discards_unidentifiable_records(self):
        old = {"HeartRate": [{"StartTime": 20, "value": None}, {}], "Sleep": [{"StartTime": 10, "Descriptor": {"BedtimeStart": "bedtime"}}]}
        incoming = {"HeartRate": [{"StartTime": 20, "value": 60}, {}], "Sleep": [{"StartTime": 11, "Descriptor": {"BedtimeStart": "bedtime"}}]}
        merged = RCS08Sync._merge_oura(old, incoming)
        self.assertEqual(merged["HeartRate"], [{"StartTime": 20, "value": 60}])
        self.assertEqual(merged["Sleep"][0]["StartTime"], 11)
        self.assertEqual(old["HeartRate"][0]["value"], None)
        self.assertEqual(RCS08Sync._oura_identity("Sleep", {"StartTime": 2}), 2)
        self.assertEqual(RCS08Sync._oura_identity("HeartRate", {"Metadata": {"DayLabel": "day"}}), "day")

    def test_identical_oura_snapshot_does_not_change_published_pointer(self):
        source = RCS08Sync._save_oura_snapshot(self.participant, {"DailyActivity": []})
        repeated = RCS08Sync._save_oura_snapshot(self.participant, {"DailyActivity": []})
        self.assertEqual(source.pointer, repeated.pointer)
        self.assertEqual(len(list(Path(source.pointer).parent.glob("*.bdat"))), 1)

    def test_oura_full_then_incremental_and_sleep_backfill(self):
        today = dt.datetime.now(RCS08Sync.LOCAL_TIMEZONE).date()
        start = today - dt.timedelta(days=90)
        api = mock.Mock()
        for kind in RCS08Sync.OURA_KEYS:
            getattr(api, "get" + kind).return_value = []
        api.getDailyActivity.return_value = [{"StartTime": 100, "Metadata": {"DayLabel": "synthetic-day"}}]
        with mock.patch.object(RCS08Sync, "_load_secret", return_value={"access_token": "synthetic-only"}), mock.patch.object(RCS08Sync.OuraDataManager, "OuraRingAPI", return_value=api), mock.patch.object(RCS08Sync, "OURA_START_DATE", start.isoformat()), mock.patch.object(RCS08Sync.OuraDataManager, "loadOuraRingData", return_value={}) as load:
            preview = RCS08Sync.sync_oura(self.participant, dry_run=True)
            self.assertEqual(preview["mode"], "full")
            self.assertFalse(models.SourceFile.objects.exists())
            full = RCS08Sync.sync_oura(self.participant)
            self.assertEqual(full["counts"]["DailyActivity"], 1)
            source = models.SourceFile.objects.get(type="OuraRingAPISource")
            source.metadata["SleepProcessingVersion"] = 1
            source.save()
            load.return_value = {"DailyActivity": [{"StartTime": 50, "Metadata": {"DayLabel": "historical-day"}}]}
            api.reset_mock()
            incremental = RCS08Sync.sync_oura(self.participant)
            self.assertEqual(incremental["mode"], "incremental")
            self.assertTrue(incremental["sleep_history_reprocessed"])
            self.assertEqual(incremental["counts"]["DailyActivity"], 2)
            self.assertGreater(api.getSleep.call_count, api.getDailyActivity.call_count)
            self.assertEqual(models.OuraRingDevice.objects.count(), 1)
            self.assertEqual(models.OuraRingDevice.objects.get().auth, {"managed_sync": True})
            self.assertFalse(RCS08Sync.sync_oura(self.participant)["sleep_history_reprocessed"])
            self.assertEqual(RCS08Sync.sync_oura(self.participant, full=True)["counts"]["DailyActivity"], 1)
            load.assert_called_with(self.participant, raw=True)

    def test_oura_token_error_cannot_touch_existing_snapshot(self):
        with mock.patch.object(RCS08Sync, "_load_secret", return_value={"access_token": "synthetic"}), mock.patch.object(RCS08Sync.OuraDataManager, "OuraRingAPI") as factory, mock.patch.object(RCS08Sync.OuraDataManager, "loadOuraRingData") as load:
            factory.return_value.verifyToken.side_effect = ValueError("synthetic")
            with self.assertRaisesRegex(RCS08Sync.SyncError, "verification failed"):
                RCS08Sync.sync_oura(self.participant)
            load.assert_not_called()

    def test_selected_streams_include_historical_forms_and_forward_flags(self):
        with mock.patch.object(RCS08Sync, "resolve_participant", return_value=self.participant), mock.patch.object(RCS08Sync, "sync_redcap", return_value={"written": 1}), mock.patch("modules.RCS08HistoricalSurveys.sync_historical_surveys", return_value={"forms": 2}) as historical, mock.patch.object(RCS08Sync, "sync_oura") as oura:
            result = RCS08Sync.run_sync(streams=("redcap",), dry_run=True)
            self.assertEqual(result["redcap"]["historical_forms"], {"forms": 2})
            historical.assert_called_once_with(self.participant, dry_run=True)
            oura.assert_not_called()

    def test_unexpected_stream_error_is_redacted_and_lock_released(self):
        with mock.patch.object(RCS08Sync, "resolve_participant", return_value=self.participant), mock.patch.object(RCS08Sync, "sync_neural", side_effect=ValueError("synthetic-sensitive-detail")):
            with self.assertRaises(RCS08Sync.SyncError) as error:
                RCS08Sync.run_sync(streams=("neural",))
            self.assertIn("ValueError", str(error.exception))
            self.assertIn("successful stream(s): none", str(error.exception))
            self.assertNotIn("synthetic-sensitive-detail", str(error.exception))
            self.assertEqual(RCS08Sync.run_sync(streams=()), {})
