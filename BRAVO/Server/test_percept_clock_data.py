"""Execute the real clock adapter against a synthetic ORM; never open a database."""
import argparse
import ast
import copy
from contextlib import nullcontext
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Rows(list):
    def select_related(self, *args):
        return self

    def filter(self, **kwargs):
        return Rows(r for r in self if all(getattr(r, k) == v for k, v in kwargs.items()))

    def order_by(self, key):
        return Rows(sorted(self, key=lambda r: getattr(r, key)))


class Repository:
    def __init__(self):
        self.rows = Rows()

    def __call__(self, **kwargs):
        row = NS(**kwargs)
        row.uid = kwargs.get("uid", "new-" + str(len(self.rows)))
        row.metadata = kwargs.get("metadata", {})
        row.save = Mock(side_effect=lambda: self.rows.append(row))
        related = []
        row.data = NS(add=Mock(side_effect=related.append), all=lambda: related)
        return row

    def find_all(self, **kwargs):
        def value(row, key):
            for field in key.split("__"):
                row = getattr(row, field)
            return row
        return Rows(r for r in self.rows if all(value(r, k) == v for k, v in kwargs.items()))

    def find(self, **kwargs):
        return next(iter(self.find_all(**kwargs)), None)

    def include(self, **kwargs):
        return self.find(**kwargs) is not None


class ClockDataTests(unittest.TestCase):
    def setUp(self):
        self.person = NS(uid="synthetic-participant")
        self.records, self.events = Repository(), Repository()
        self.source = self.new_source("source-a")
        self.sources = Rows([self.source])
        self.payloads = {self.source.uid: self.payload()}
        self.clock = load("clock_data_pure", ROOT / "modules/PerceptClock.py")
        modules = ModuleType("modules")
        modules.PerceptClock = self.clock
        modules.RCS08DataPolicy = NS(applies_to=lambda p: False, IMPLANT_DAY=1600000000)
        modules.AnalysisData = NS(eligible_source_files=lambda p: Rows(
            s for s in self.sources if s.owner == p and not s.metadata.get("AnalysisExclusion")))
        modules.DataCurator = NS(loadCacheFile=Mock(side_effect=lambda s: json.dumps(self.payloads[s.uid])))
        modules.ReportCache = NS(invalidate=Mock())
        self.dependencies = modules
        self.participants = NS(objects=NS(select_for_update=Mock(return_value=NS(get=Mock()))),
                               find=Mock(return_value=self.person))
        self.models = NS(Recording=self.records, DBSEvent=self.events,
                         Participant=self.participants,
                         DBSDevice=NS(find=Mock(return_value=NS(uid="device-a"))))
        server, db = ModuleType("Server"), ModuleType("django.db")
        server.models = self.models
        db.transaction = NS(atomic=Mock(side_effect=nullcontext))
        self.modules_patch = patch.dict(sys.modules, {"modules": modules, "Server": server,
                                                     "django.db": db})
        self.modules_patch.start()
        self.addCleanup(self.modules_patch.stop)
        self.adapter = load("clock_data_adapter", ROOT / "modules/PerceptClockData.py")

    def new_source(self, uid, **metadata):
        return NS(uid=uid, owner=self.person, type="MedtronicJSON",
                  metadata={"Device": "device-a", **metadata}, hashed="raw-" + uid,
                  pointer="/synthetic/" + uid, save=Mock(), refresh_from_db=Mock())

    def block(self, counter=100, **kwargs):
        return {"DateTime": "2026-09-11T01:00:00Z", "DateTimeBlockId": 4,
                "DateTimeOffsetInSeconds": counter, "Frequency": [1, 2],
                "FFTBinData": [3, 4], **kwargs}

    def event(self, **kwargs):
        return {"name": "Streaming", "date": 1789088400.0,
                "metadata": {"Left": self.block()}, **kwargs}

    def payload(self):
        return {"SessionDate": "2026-09-11T00:00:00Z",
                "SessionEndDate": "2026-09-11T00:01:00Z",
                "DeviceInformation": {"Initial": {"DeviceDateTime": "2026-09-11T02:00:00Z",
                    "DeviceDateTimeBlockId": 4, "DeviceDateTimeOffsetInSeconds": 200}},
                "DiagnosticData": {"LfpFrequencySnapshotEvents": [
                    {"EventName": "Streaming", "DateTime": "2026-09-11T01:00:00Z",
                     "LfpFrequencySnapshotEvents": {"Left": self.block()}}]}}

    def existing(self, source=None, **kwargs):
        event = self.event(**kwargs)
        record = NS(uid="old", source=source or self.source, type="PatientControllerEvent",
                    adjusted_alignment=5.0, save=Mock(), **event)
        self.records.rows.append(record)
        return record

    def test_stamp_preserves_source_identity_and_is_idempotent(self):
        original = (self.source.hashed, self.source.pointer)
        payload = self.payload()
        untouched = copy.deepcopy(payload)
        self.assertTrue(self.adapter.stamp_source(self.source, payload))
        self.assertFalse(self.adapter.stamp_source(self.source, payload))
        self.assertEqual(original, (self.source.hashed, self.source.pointer))
        self.assertEqual(payload, untouched)
        self.source.save.assert_not_called()

    def test_native_alias_json_roundtrip_is_idempotent_without_changing_values(self):
        index = self.clock.extract_source(self.payload())
        index['decoded_start_aliases'] = [{
            'decoded_raw':1773950280.8999999, 'original_raw':1773950280.,
            'sample_start_offset_seconds':.40000009536743164,
            'block':7, 'counter':200, 'recording_type':'MedtronicBrainSenseTimeDomain',
            'source_kind':'BrainSenseTimeDomain'}]
        stored = copy.deepcopy(index)
        for key in ('decoded_raw','original_raw','sample_start_offset_seconds'):
            stored['decoded_start_aliases'][0][key] = math.nextafter(index['decoded_start_aliases'][0][key], math.inf)
        before = copy.deepcopy(stored)
        self.assertTrue(self.adapter._same_source_index(stored,index))
        self.assertEqual(stored,before)
        self.source.metadata[self.adapter.KEY] = stored
        with patch.object(self.adapter,'extract_source_index',return_value=index):
            self.assertFalse(self.adapter.stamp_source(self.source,self.payload()))
        self.assertEqual(self.source.metadata[self.adapter.KEY],before)
        for field in ('decoded_raw','original_raw','sample_start_offset_seconds'):
            bad=copy.deepcopy(stored)
            bad['decoded_start_aliases'][0][field]=math.nextafter(bad['decoded_start_aliases'][0][field],math.inf)
            self.assertFalse(self.adapter._same_source_index(bad,index))
        for field,value in [('counter',201),('block',8),('source_kind','other')]:
            bad=copy.deepcopy(stored);bad['decoded_start_aliases'][0][field]=value
            self.assertFalse(self.adapter._same_source_index(bad,index))
        for field,value in [('version','old'),('anchors',[])]:
            bad=copy.deepcopy(stored);bad[field]=value
            self.assertFalse(self.adapter._same_source_index(bad,index))
        for value in (None,{},[],[None],stored['decoded_start_aliases']*2):
            bad=copy.deepcopy(stored);bad['decoded_start_aliases']=value
            self.assertFalse(self.adapter._same_source_index(bad,index))
            self.assertFalse(self.adapter._same_source_index(index,bad))
        for value in (None,[],1):
            self.assertFalse(self.adapter._same_source_index(value,index))
            self.assertFalse(self.adapter._same_source_index(index,value))
        for value in (None,float('inf'),True):
            bad=copy.deepcopy(stored);bad['decoded_start_aliases'][0]['decoded_raw']=value
            self.assertFalse(self.adapter._same_source_index(bad,index))
            self.assertFalse(self.adapter._same_source_index(index,bad))

    def test_default_dry_run_makes_no_changes_and_reports_missing_psd(self):
        result = self.adapter.index_participant(self.person)
        self.assertFalse(result["apply"])
        self.assertEqual(result["source_indexes_changed"], 1)
        self.assertEqual(result["physical_missing_blocks"], 1)
        self.assertNotIn("PerceptClock", self.source.metadata)
        self.source.save.assert_not_called()
        self.assertFalse(self.records.rows)
        self.assertFalse(self.events.rows)
        self.participants.objects.select_for_update.assert_not_called()
        self.dependencies.ReportCache.invalidate.assert_not_called()

    def test_apply_then_repeat_is_idempotent_without_raw_or_alignment_edits(self):
        old = self.existing(metadata={"Right": self.block()})
        original = copy.deepcopy(old.metadata)
        result = self.adapter.index_participant(self.person, apply=True)
        self.assertEqual(result["physical_missing_blocks"], 1)
        self.assertEqual(len(self.records.rows), 2)
        self.assertEqual(self.source.hashed, "raw-source-a")
        self.assertEqual(self.source.pointer, "/synthetic/source-a")
        self.assertEqual(old.metadata, original)
        self.assertEqual(old.adjusted_alignment, 5.0)
        old.save.assert_not_called()
        again = self.adapter.index_participant(self.person, apply=True)
        self.assertEqual(again["physical_missing_blocks"], 0)
        self.assertEqual(again["source_indexes_changed"], 0)
        self.assertEqual(len(self.records.rows), 2)
        self.dependencies.ReportCache.invalidate.assert_called_once_with(neural=True)

    def test_changed_export_time_preserves_native_payload_without_new_physical_psd(self):
        old = self.existing()
        event = self.event(name="Another label", date=self.event()["date"] + 7200,
                           metadata={"Left": self.block(DateTime="2026-09-11T03:00:00Z")})
        result = self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(result["duplicate_blocks"], 1)
        self.assertEqual(result["native_representations_created"], 1)
        self.assertEqual(result["physical_missing_blocks"], 0)
        self.assertEqual(len(self.records.rows), 2)
        self.assertEqual(self.records.rows[-1].metadata, event["metadata"])
        self.assertEqual(self.records.rows[-1].date, event["date"])
        self.assertEqual(self.records.rows[-1].name, event["name"])
        self.assertEqual(result["native_representations_linked"], 1)
        self.events.rows[-1].data.add.assert_called_once_with(self.records.rows[-1])
        old.save.assert_not_called()
        repeated = self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(repeated["annotations_created"], 0)
        self.assertEqual(repeated["native_representations_linked"], 0)

    def test_existing_annotation_does_not_suppress_new_physical_psd_or_hemisphere(self):
        self.existing()
        annotation = self.events(source=self.source, type="PatientControllerEvent",
                                 name="Streaming", date=self.event()["date"])
        annotation.save()
        event = self.event(metadata={"Left": self.block(101), "Right": self.block()})
        result = self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(result["physical_missing_blocks"], 2)
        self.assertEqual(result["annotations_created"], 0)
        self.assertEqual(len(self.events.rows), 1)
        self.assertEqual(len(self.records.rows), 2)
        annotation.data.add.assert_called_once_with(self.records.rows[-1])

    def test_missing_psd_is_not_attached_to_excluded_or_other_device_annotation(self):
        for source in [self.new_source("excluded", AnalysisExclusion="reviewed"),
                       self.new_source("other", Device="device-b")]:
            annotation = self.events(source=source, type="PatientControllerEvent",
                                     name="Streaming", date=self.event()["date"])
            annotation.save()
        result = self.adapter.save_patient_event_psds(self.source, [self.event()], "device-a")
        self.assertEqual(result["annotations_created"], 1)
        self.assertEqual(self.events.rows[-1].source, self.source)
        for annotation in self.events.rows[:-1]:
            annotation.data.add.assert_not_called()

    def test_same_device_annotation_in_another_eligible_source_is_reused(self):
        annotation = self.events(source=self.new_source("same-device"),
                                 type="PatientControllerEvent", name="Streaming",
                                 date=self.event()["date"])
        annotation.save()
        result = self.adapter.save_patient_event_psds(self.source, [self.event()], "device-a")
        self.assertEqual(result["annotations_created"], 0)
        annotation.data.add.assert_called_once()

    def test_two_devices_with_same_annotation_time_get_separate_annotations(self):
        other = self.new_source("source-b", Device="device-b")
        self.sources.append(other)
        self.payloads[other.uid] = self.payload()
        dry = self.adapter.index_participant(self.person)
        self.assertEqual(dry["annotations_created"], 2)
        applied = self.adapter.index_participant(self.person, apply=True)
        self.assertEqual(applied["annotations_created"], 2)
        self.assertEqual(applied["native_representations_created"], 2)
        self.assertEqual(applied["native_representations_linked"], 2)
        self.assertEqual({event.source.metadata["Device"] for event in self.events.rows},
                         {"device-a", "device-b"})

    def test_backfill_repairs_empty_annotation_link_without_new_psd(self):
        old = self.existing()
        self.adapter.stamp_source(self.source, self.payload())
        annotation = self.events(source=self.source, type="PatientControllerEvent",
                                 name="Streaming", date=self.event()["date"])
        annotation.save()
        result = self.adapter.index_participant(self.person, apply=True)
        self.assertEqual(result["source_indexes_changed"], 0)
        self.assertEqual(result["physical_missing_blocks"], 0)
        self.assertEqual(result["native_representations_linked"], 1)
        annotation.data.add.assert_called_once_with(old)
        self.dependencies.ReportCache.invalidate.assert_called_once_with(neural=True)

    def test_two_hemispheres_in_one_existing_recording_create_one_annotation_link(self):
        old = self.existing(metadata={"Left": self.block(), "Right": self.block()})
        result = self.adapter.save_patient_event_psds(self.source, [self.event(
            metadata=copy.deepcopy(old.metadata))], "device-a")
        self.assertEqual(result["duplicate_blocks"], 2)
        self.assertEqual(result["native_representations_linked"], 1)
        self.events.rows[-1].data.add.assert_called_once_with(old)

    def test_left_only_reexport_never_links_unrelated_right_spectrum(self):
        old = self.existing(metadata={"Left": self.block(), "Right": self.block()})
        annotation = self.events(source=self.source, type="PatientControllerEvent",
                                 name="Streaming", date=self.event()["date"])
        annotation.save()
        annotation.data.add(old)
        event = self.event()
        result = self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(result["physical_missing_blocks"], 0)
        self.assertEqual(result["native_representations_created"], 1)
        self.assertEqual(result["annotations_created"], 1)
        self.assertEqual(annotation.data.all(), [old])
        new = self.records.rows[-1]
        self.assertEqual(new.metadata, event["metadata"])
        self.assertEqual(set(new.metadata), {"Left"})
        self.assertEqual(self.events.rows[-1].data.all(), [new])
        again = self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(again["native_representations_created"], 0)
        self.assertEqual(again["native_representations_linked"], 0)

    def test_duplicate_left_and_novel_right_preserve_exact_bilateral_event(self):
        old = self.existing(metadata={"Left": self.block(), "Right": self.block()})
        original = copy.deepcopy(old.metadata)
        event = self.event(metadata={"Left": self.block(), "Right": self.block(101)})
        result = self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(result["physical_missing_blocks"], 1)
        self.assertEqual(result["duplicate_blocks"], 1)
        self.assertEqual(result["native_representations_created"], 1)
        new = self.records.rows[-1]
        self.assertEqual(new.metadata, event["metadata"])
        self.assertEqual(self.events.rows[-1].data.all(), [new])
        self.assertEqual(old.metadata, original)
        self.assertEqual(old.adjusted_alignment, 5.0)

    def test_identical_native_payload_from_another_export_reuses_exact_row(self):
        old = self.existing(source=self.new_source("earlier-export"))
        result = self.adapter.save_patient_event_psds(self.source, [self.event()], "device-a")
        self.assertEqual(result["physical_missing_blocks"], 0)
        self.assertEqual(result["native_representations_created"], 0)
        self.assertEqual(self.events.rows[-1].data.all(), [old])
        old.save.assert_not_called()

    def test_existing_equivalent_link_does_not_gain_second_legacy_record(self):
        first = self.existing()
        first.uid = "a"
        second = self.existing()
        second.uid = "b"
        annotation = self.events(source=self.source, type="PatientControllerEvent",
                                 name="Streaming", date=self.event()["date"])
        annotation.save()
        annotation.data.add(second)
        result = self.adapter.save_patient_event_psds(self.source, [self.event()], "device-a")
        self.assertEqual(result["native_representations_created"], 0)
        self.assertEqual(result["native_representations_linked"], 0)
        self.assertEqual(annotation.data.all(), [second])

    def test_no_valid_spectrum_creates_no_native_representation(self):
        result = self.adapter.save_patient_event_psds(self.source,
            [self.event(metadata={"Left": None})], "device-a")
        self.assertEqual(result["native_representations_created"], 0)
        self.assertFalse(self.records.rows)
        self.assertFalse(self.events.rows)

    def test_missing_coordinate_fallback_uses_exact_metadata_and_date(self):
        block = self.block()
        del block["DateTimeBlockId"]
        a = self.event(metadata={"Left": block})
        b = self.event(metadata={"Left": block}, date=a["date"] + 1)
        c = self.event(metadata={"Left": {**block, "FFTBinData": [3, 5]}})
        result = self.adapter.save_patient_event_psds(self.source, [a, a, b, c], "device-a")
        self.assertEqual(result["physical_missing_blocks"], 3)
        self.assertEqual(result["duplicate_blocks"], 1)

    def test_invalid_metadata_and_excluded_or_unidentified_existing_sources_do_not_dedup(self):
        self.existing(metadata={"invalid": None, "bad": {"Frequency": [1], "FFTBinData": []}})
        self.existing(source=self.new_source("excluded", AnalysisExclusion="reviewed"))
        self.existing(source=self.new_source("unidentified", Device=""))
        self.existing(metadata=[])
        result = self.adapter.save_patient_event_psds(self.source,
            [self.event(metadata={"Left": self.block(), "bad": None})], "device-a")
        self.assertEqual(result["physical_missing_blocks"], 1)
        self.assertEqual(result["blocks_examined"], 1)

    def test_other_device_and_changed_coordinate_are_distinct(self):
        self.existing(source=self.new_source("other", Device="device-b"))
        result = self.adapter.save_patient_event_psds(self.source, [self.event(),
            self.event(metadata={"Left": self.block(101, FFTBinData=[3, 5])})], "device-a")
        self.assertEqual(result["physical_missing_blocks"], 2)

    def test_json_float_roundtrip_reuses_native_representation_and_original_values(self):
        value = 3.6904201006916604
        old = self.existing(metadata={"Left": self.block(FFTBinData=[3.690420100691661, 4])})
        original = copy.deepcopy(old.metadata)
        event = self.event(metadata={"Left": self.block(FFTBinData=[value, 4])})
        result = self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(result["physical_missing_blocks"], 0)
        self.assertEqual(result["native_representations_created"], 0)
        self.assertEqual(self.events.rows[-1].data.all(), [old])
        self.assertEqual(old.metadata, original)
        self.assertEqual(event["metadata"]["Left"]["FFTBinData"][0], value)

    def test_same_coordinate_material_spectrum_conflict_fails_before_record_creation(self):
        self.existing()
        event = self.event(metadata={"Left": self.block(FFTBinData=[3, 5])})
        with self.assertRaisesRegex(ValueError, "spectral"):
            self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(len(self.records.rows), 1)
        self.assertFalse(self.events.rows)

    def test_pairwise_comparison_rejects_nontransitive_ulp_chain(self):
        values = [3.0]
        for unused in range(6):
            values.append(math.nextafter(values[-1], math.inf))
        a = self.existing(metadata={"Left": self.block(FFTBinData=[values[0], 4])})
        a.uid = "a"
        b = self.existing(metadata={"Left": self.block(FFTBinData=[values[3], 4])})
        b.uid = "b"
        event = self.event(metadata={"Left": self.block(FFTBinData=[values[6], 4])})
        with self.assertRaisesRegex(ValueError, "spectral"):
            self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(len(self.records.rows), 2)
        self.assertFalse(self.events.rows)

    def test_reexport_inherits_unanimous_existing_manual_alignment(self):
        old = self.existing()
        event = self.event(date=self.event()["date"] + 60)
        result = self.adapter.save_patient_event_psds(self.source, [event], "device-a")
        self.assertEqual(result["native_representations_created"], 1)
        self.assertEqual(self.records.rows[-1].adjusted_alignment, 5.0)
        self.assertEqual(old.adjusted_alignment, 5.0)
        old.save.assert_not_called()

    def test_mixed_hemisphere_manual_shifts_fail_before_record_creation(self):
        left = self.existing()
        left.uid = "left"
        right = self.existing(metadata={"Right": self.block()})
        right.uid = "right"
        right.adjusted_alignment = 7.0
        with self.assertRaisesRegex(ValueError, "hemispheres"):
            self.adapter.save_patient_event_psds(self.source, [self.event(
                metadata={"Left": self.block(), "Right": self.block()})], "device-a")
        self.assertEqual(len(self.records.rows), 2)
        self.assertFalse(self.events.rows)

    def test_existing_physical_alignment_conflict_and_invalid_shift_fail_closed(self):
        a = self.existing()
        a.uid = "a"
        b = self.existing()
        b.uid = "b"
        b.adjusted_alignment = 7.0
        with self.assertRaisesRegex(ValueError, "conflicting manual"):
            self.adapter.index_participant(self.person)
        b.adjusted_alignment = float("nan")
        with self.assertRaisesRegex(ValueError, "invalid manual"):
            self.adapter.index_participant(self.person)

    def test_equal_nonfinite_spectrum_values_are_retained_without_serialization_failure(self):
        event = self.event(metadata={"Left": self.block(FFTBinData=[float("nan"), float("inf")])})
        result = self.adapter.save_patient_event_psds(self.source, [event, event], "device-a")
        self.assertEqual(result["native_representations_created"], 1)
        self.assertTrue(math.isnan(self.records.rows[0].metadata["Left"]["FFTBinData"][0]))

    def test_policy_preimplant_guard_is_retained_and_counted(self):
        self.dependencies.RCS08DataPolicy.applies_to = lambda p: True
        events = [self.event(date=1599999999), self.event(date=1600000000)]
        result = self.adapter.save_patient_event_psds(self.source, events, "device-a")
        self.assertEqual(result["preimplant_events_guarded"], 1)
        self.assertEqual(result["physical_missing_blocks"], 1)
        self.assertEqual(self.records.rows[0].date, 1600000000)

    def test_exclusions_and_non_json_sources_are_not_opened(self):
        excluded = self.new_source("excluded", AnalysisExclusion="reviewed")
        other = self.new_source("other")
        other.type = "Other"
        self.sources.extend([excluded, other])
        result = self.adapter.index_participant(self.person)
        self.assertEqual(result["sources_examined"], 1)
        self.dependencies.DataCurator.loadCacheFile.assert_called_once_with(self.source)

    def test_missing_raw_fails_before_any_apply(self):
        second = self.new_source("source-b")
        self.sources.append(second)
        self.dependencies.DataCurator.loadCacheFile.side_effect = [json.dumps(self.payload()),
                                                                  OSError("missing synthetic raw")]
        with self.assertRaises(OSError):
            self.adapter.index_participant(self.person, apply=True)
        self.source.save.assert_not_called()
        self.assertFalse(self.records.rows)

    def test_foreign_or_unidentified_source_is_rejected(self):
        self.dependencies.AnalysisData.eligible_source_files = lambda p: Rows([self.source])
        self.source.owner = NS(uid="other")
        with self.assertRaisesRegex(ValueError, "belong"):
            self.adapter.index_participant(self.person)
        self.source.owner = self.person
        self.source.metadata["Device"] = ""
        with self.assertRaisesRegex(ValueError, "device"):
            self.adapter.index_participant(self.person)
        self.source.metadata["Device"] = "device-a"
        self.models.DBSDevice.find.return_value = None
        with self.assertRaisesRegex(ValueError, "device"):
            self.adapter.index_participant(self.person)

    def test_source_change_during_preparation_fails_closed(self):
        self.source.refresh_from_db.side_effect = lambda: setattr(self.source, "hashed", "changed")
        with self.assertRaisesRegex(RuntimeError, "changed during"):
            self.adapter.index_participant(self.person, apply=True)
        self.source.save.assert_not_called()
        self.assertFalse(self.records.rows)

    def test_unexpected_hash_mutation_during_metadata_save_is_rejected(self):
        self.source.save.side_effect = lambda **kw: setattr(self.source, "hashed", "changed")
        with self.assertRaisesRegex(RuntimeError, "raw source identity"):
            self.adapter.index_participant(self.person, apply=True)

    def test_same_name_time_different_native_payloads_have_distinct_annotations(self):
        other = self.new_source("source-b")
        self.sources.append(other)
        payload = self.payload()
        payload["DiagnosticData"]["LfpFrequencySnapshotEvents"][0]["LfpFrequencySnapshotEvents"]["Left"]["DateTimeOffsetInSeconds"] = 101
        self.payloads[other.uid] = payload
        result = self.adapter.index_participant(self.person)
        self.assertEqual(result["physical_missing_blocks"], 2)
        self.assertEqual(result["annotations_created"], 2)
        applied = self.adapter.index_participant(self.person, apply=True)
        self.assertEqual(applied["annotations_created"], 2)
        repeated = self.adapter.index_participant(self.person, apply=True)
        self.assertEqual(repeated["native_representations_created"], 0)
        self.assertEqual(repeated["native_representations_linked"], 0)

    def test_dry_run_reserves_empty_annotation_for_only_one_native_payload(self):
        annotation = self.events(source=self.source, type="PatientControllerEvent",
                                 name="Streaming", date=self.event()["date"])
        annotation.save()
        events = [self.event(), self.event(metadata={"Left": self.block(101)})]
        dry = self.adapter._reconcile_events(self.source, events, "device-a",
            self.adapter._existing_keys(self.person), apply=False)
        self.assertEqual(dry["annotations_created"], 1)
        self.assertEqual(annotation.data.all(), [])
        applied = self.adapter.save_patient_event_psds(self.source, events, "device-a")
        self.assertEqual(applied, dry)
        self.assertEqual(len(self.events.rows), 2)
        for row in self.events.rows:
            self.assertEqual(len(row.data.all()), 1)

    def test_no_eligible_sources_is_clean_noop(self):
        self.sources.clear()
        result = self.adapter.index_participant(self.person, apply=True)
        self.assertEqual(result["sources_examined"], 0)
        self.dependencies.ReportCache.invalidate.assert_not_called()

    def test_real_import_hook_extracts_before_decoder_mutates_json(self):
        tree = ast.parse((ROOT / "modules/DataCurator.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "MedtronicPerceptJSONDecoder")
        self.dependencies.PerceptClockData = self.adapter
        self.source.metadata["automatic_concatenation"] = False
        class ReachedDecoder(Exception):
            pass
        def decoder(payload):
            self.assertIn("PerceptClock", self.source.metadata)
            self.assertEqual(self.source.metadata["PerceptClock"]["anchors"][0]["counter"], 200)
            payload["DeviceInformation"] = {}
            raise ReachedDecoder()
        namespace = {"json": json, "loadCacheFile": self.dependencies.DataCurator.loadCacheFile,
                     "decodeMedtronicJSON": decoder}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "modules/DataCurator.py"), "exec"), namespace)
        with self.assertRaises(ReachedDecoder):
            namespace[function.name](self.source, person=self.person)
        self.source.save.assert_not_called()
        self.assertEqual(self.source.hashed, "raw-source-a")

    def test_real_import_event_boundary_keeps_annotations_and_novel_psds(self):
        tree = ast.parse((ROOT / "modules/DataCurator.py").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "MedtronicPerceptJSONDecoder")
        start = next(i for i, n in enumerate(function.body) if isinstance(n, ast.Assign)
                     and isinstance(n.value, ast.Call)
                     and isinstance(n.value.func, ast.Attribute)
                     and n.value.func.attr == "save_patient_event_psds")
        nodes = function.body[start:start + 2]
        self.assertIsInstance(nodes[-1], ast.For)
        self.existing()
        old_annotation = self.events(source=self.source, type="PatientControllerEvent",
                                     name="Streaming", date=self.event()["date"])
        old_annotation.save()
        novel = self.event(metadata={"Left": self.block(101)})
        duplicate = self.event(date=self.event()["date"] + 60)
        ordinary = {"name": "Status", "type": "TherapyStatus", "date": 300}
        invalid = {"name": "Invalid PSD", "type": "PatientControllerEvent", "date": 301,
                   "data": {"Left": {"Frequency": [], "FFTBinData": []}}}
        entries = [{"name": e["name"], "date": e["date"], "type": "PatientControllerEvent",
                    "data": e["metadata"]} for e in [novel, duplicate]] + [ordinary, invalid]
        namespace = dict(PerceptClockData=self.adapter, PerceptClock=self.clock, models=self.models,
                         source_file=self.source, patient_event_psds=[novel, duplicate],
                         device=NS(uid="device-a"), person=self.person,
                         DatabaseEntries={"EventRecordings": entries})
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "modules/DataCurator.py"), "exec"), namespace)
        self.assertEqual(self.source.metadata["PerceptClockReconciliation"]["physical_missing_blocks"], 1)
        self.assertEqual(len(self.records.rows), 4)  # old, novel, re-export representation, legacy invalid-data
        self.assertEqual(len(self.events.rows), 4)  # old, duplicate-time annotation, status, invalid
        old_annotation.data.add.assert_called_once_with(self.records.rows[1])


    def command(self):
        module = ModuleType("django.core.management.base")
        module.BaseCommand = object
        module.CommandError = type("CommandError", (Exception,), {})
        self.dependencies.PerceptClockData = self.adapter
        with patch.dict(sys.modules, {"django.core.management.base": module}):
            return load("clock_data_command", ROOT / "Server/management/commands/index_percept_clock.py")

    def test_command_defaults_dry_and_requires_exact_participant(self):
        module = self.command()
        command = module.Command()
        parser = argparse.ArgumentParser()
        command.add_arguments(parser)
        args = vars(parser.parse_args(["--participant-uid", "synthetic-participant"]))
        self.assertFalse(args["apply"])
        command.stdout = NS(write=Mock())
        command.handle(**args)
        result = json.loads(command.stdout.write.call_args.args[0])
        self.assertFalse(result["apply"])
        self.participants.find.assert_called_once_with(uid="synthetic-participant")

    def test_command_missing_participant_and_private_failure(self):
        module = self.command()
        command = module.Command()
        self.participants.find.return_value = None
        with self.assertRaisesRegex(module.CommandError, "not found"):
            command.handle(participant_uid="missing", apply=False)
        self.participants.find.return_value = self.person
        self.dependencies.DataCurator.loadCacheFile.side_effect = OSError("PRIVATE PATH")
        with self.assertRaises(module.CommandError) as caught:
            command.handle(participant_uid="synthetic-participant", apply=True)
        self.assertNotIn("PRIVATE", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
