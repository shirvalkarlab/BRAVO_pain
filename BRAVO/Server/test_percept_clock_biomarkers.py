"""Real Django/biomarker-loader boundary with synthetic spectra and clock anchors."""
from copy import deepcopy
from unittest.mock import patch

from django.test import TestCase
import numpy as np
from Server import models
from modules import PerceptClock
from modules.Biomarkers import bravo_service as service

BASE = 1700000000.0


class ClockBiomarkerTests(TestCase):
    def setUp(self):
        self.person = models.Participant.objects.create(name="Synthetic clock participant")
        self.sources = []
        for i in range(2):
            metadata = {"Device": "synthetic-device", "PerceptClock": {
                "version": PerceptClock.VERSION,
                "anchors": [{"phase": "Final", "block": 43, "counter": 1000 + i * 1000,
                             "utc": BASE + i * 1000, "ins_utc": BASE + i * 1000 + 7200}],
                "starts": [{"raw": BASE + 7500 - i * 200, "block": 43, "counter": 1500}]}}
            self.sources.append(models.SourceFile.objects.create(owner=self.person, type="MedtronicJSON", metadata=metadata))
        self.spectrum = {"DateTimeBlockId": 43, "DateTimeOffsetInSeconds": 1500,
                         "DateTime": "2023-11-15T00:18:20Z", "Frequency": [1, 2], "FFTBinData": [3, 4]}

    def event(self, source=0, spectrum=None, **kw):
        return models.Recording.objects.create(source=self.sources[source], type="PatientControllerEvent",
              date=BASE+7200, name="Streaming", metadata={"HemisphereLocationDef.Left": deepcopy(spectrum or self.spectrum)}, **kw)

    def test_real_orm_all_event_consumers_share_recovered_unique_time(self):
        self.event()
        other = deepcopy(self.spectrum); other["DateTime"] = "2023-11-15T02:18:20Z"
        self.event(1, other)
        rows, counts = service._canonical_event_psds(self.person, with_counts=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["t"], BASE+500)
        self.assertEqual(counts["duplicate_export_copies"], 1)
        self.assertEqual(counts["eligible_physical_psds"], 1)
        with patch.object(service, "_resolve_event_channel", return_value="ONE_THREE_LEFT") as resolve:
            matrix = service._event_psd_rows(self.person.uid)
            preview = service._event_psd_index(self.person.uid)
            timeline = service._load_patient_events(self.person.uid)
        self.assertEqual([r["t"] for r in matrix], [BASE+500])
        self.assertEqual(preview[0]["t"], timeline[0]["t"])
        self.assertEqual(resolve.call_args.kwargs["t_event"], BASE+500)
        self.assertEqual(models.Recording.objects.count(), 2)
        self.assertEqual(models.Recording.objects.first().date, BASE+7200)
        with patch.object(service, "_resolve_event_channel", return_value=None):
            self.assertEqual(service._event_psd_rows(self.person.uid), [])
        for function in (service._event_psd_rows, service._event_psd_index, service._load_patient_events):
            self.assertEqual(function("absent"), [])

    def test_unresolved_and_post_recovery_eligibility(self):
        self.event()
        with patch.object(service, "_eligible_time", return_value=False):
            rows, counts = service._canonical_event_psds(self.person, with_counts=True)
        self.assertEqual(rows, [])
        self.assertEqual(counts["outside_eligible_time"], 1)
        self.sources[1].delete()
        self.assertEqual(service._canonical_event_psds(self.person), [])

    def test_missing_stale_source_index_fails_and_excluded_source_stays_out(self):
        source = self.sources[0]
        for clock in (None, {}, {"version": "old"}):
            source.metadata["PerceptClock"] = clock; source.save()
            with self.assertRaisesRegex(RuntimeError, "clock index"):
                service._clock_sources(self.person)
        source.metadata["AnalysisExclusion"] = "synthetic exclusion"; source.save()
        sources, _ = service._clock_sources(self.person)
        self.assertEqual([s.uid for s in sources], [self.sources[1].uid])

    def test_clock_corrects_start_once_and_preserves_sample_arrays(self):
        rec = models.Recording.objects.create(source=self.sources[0], type="MedtronicBrainSenseTimeDomain", adjusted_alignment=7)
        data = {"StartTime": BASE+7500, "SamplingRate": 250, "Time": np.array([0., .004]), "Data": np.array([[1], [2]])}
        _, sources = service._clock_sources(self.person)
        context = PerceptClock.build_index(sources), sources[0]
        # Query ordering is not assumed; choose the actual source explicitly.
        context = context[0], next(s for s in sources if s["uid"] == rec.source_id)
        actual = service._aligned_recording_payload(data, rec, context)
        twice = service._aligned_recording_payload(actual, rec, context)
        self.assertEqual(actual["StartTime"], BASE+507)
        self.assertEqual(twice["StartTime"], BASE+507)
        self.assertEqual(data["StartTime"], BASE+7500)
        np.testing.assert_array_equal(actual["Time"], data["Time"])
        self.assertEqual(actual["SamplingRate"], 250)
        self.assertIsNone(service._aligned_recording_payload({**data, "StartTime": BASE-1}, rec, context))
        result = service._aligned_recording_payload([data, None], rec, context)
        self.assertEqual(result[0]["StartTime"], BASE+507); self.assertIsNone(result[1])

    def test_real_loader_recovers_deduplicates_and_rejects_unreadable_partial_pool(self):
        recs=[]
        for i, source in enumerate(self.sources):
            recs.append(models.Recording.objects.create(source=source, type="MedtronicBrainSenseTimeDomain", pointer=str(i), hashed=str(i)))
        def payload(pointer, hashed):
            return {"StartTime": BASE+7500-int(pointer)*200, "SamplingRate": 250,
                    "ChannelNames": ["ONE_THREE_LEFT"], "Data": np.array([[1.], [2.]]), "Missing": np.array([[0], [0]])}
        with patch.object(service.Database, "loadSourceFile", side_effect=payload):
            audit = {}
            rows = service._load_recordings(self.person.uid, service.TIMEDOMAIN_TYPES, audit=audit)
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["StartTime"], BASE+500)
        self.assertEqual(audit["duplicate_blocks_removed"], 1)
        self.assertEqual(audit["clock_status_counts"], {"interpolated": 2})
        self.assertEqual(service._load_recordings("absent", service.TIMEDOMAIN_TYPES), [])
        self.assertEqual(service._load_recordings(self.person.uid, ["absent"]), [])
        with patch.object(service.Database, "loadSourceFile", side_effect=OSError("synthetic unreadable")):
            with self.assertRaisesRegex(RuntimeError, "could not be read completely"):
                service._load_recordings(self.person.uid, service.TIMEDOMAIN_TYPES)
        with patch.object(service.Database, "loadSourceFile", return_value=[None, {"StartTime": BASE-1}]):
            self.assertEqual(service._load_recordings(self.person.uid, service.TIMEDOMAIN_TYPES), [])

    def test_sample_dedup_preserves_distinct_data_and_refuses_alignment_conflict(self):
        provenance={"alignment_seconds": 0,"clock":{"device":"d","block":43,"counter":123}}
        data={"AnalysisTimeProvenance":provenance,"Data":np.array([1]),"Descriptor":{"values":np.array([2])}}
        distinct={**data,"Data":np.array([3])}
        self.assertEqual(len(service._deduplicate_clock_recordings([{},data,deepcopy(data),distinct])),3)
        conflict=deepcopy(data);conflict["AnalysisTimeProvenance"]["alignment_seconds"]=1
        with self.assertRaisesRegex(ValueError,"conflicting manual alignment"):
            service._deduplicate_clock_recordings([data,conflict])

    def test_matrix_assembler_uses_recovered_inputs_even_with_old_row_cache_present(self):
        self.event()
        rec = models.Recording.objects.create(source=self.sources[0], type="MedtronicBrainSenseTimeDomain", pointer="0")
        payload = {"StartTime": BASE+7500, "SamplingRate": 250, "ChannelNames": ["ONE_THREE_LEFT"], "Data": np.ones((250,1))}
        calls=[]
        def welch(rows, inputs, source, sp, pro_times=None):
            calls.extend((source, block["StartTime"]) for block in inputs)
        with patch.object(service.Database,"loadSourceFile",return_value=payload), patch.object(service,"_welch_rows_into",side_effect=welch), patch.object(service,"_event_psd_rows",return_value=[{"t":BASE+500}]), patch.object(service,"_load_recording_psd_rows",side_effect=AssertionError("stale row cache used")):
            rows, cached, computed=service._assemble_psd_rows_cached(self.person.uid,pro_times=np.array([BASE+500]))
        self.assertEqual(calls,[("TD streaming",BASE+500)])
        self.assertEqual(rows,[{"t":BASE+500}]);self.assertEqual((cached,computed),(0,1))
        with patch.object(service,"_cached_psd_matrix",side_effect=RuntimeError("event failure")):
            with self.assertRaisesRegex(RuntimeError,"event failure"):
                service._warm_centered_matrix_from_decoded(self.person.uid,[payload],[],[BASE+500])
        rec.delete(); self.sources[0].delete(); self.sources[1].delete()
        self.assertEqual(service._load_recordings(self.person.uid, service.TIMEDOMAIN_TYPES), [])
        with patch.object(service,"_aligned_recording_payload",return_value=None), patch.object(service.Database,"loadSourceFile",return_value=None):
            self.sources[0].pk=None; self.sources[0].save()
            models.Recording.objects.create(source=self.sources[0],type="MedtronicBrainSenseTimeDomain")
            self.assertEqual(service._load_recordings(self.person.uid,service.TIMEDOMAIN_TYPES),[])

    def test_chronic_metadata_is_preserved_without_claiming_clock_recovery(self):
        for metadata in ({"CenterFrequencyHz": 20}, {"FreqScheduleHz": [20, 30]}, {"ContactSchedule": ["Left01"]}):
            rec=models.Recording.objects.create(source=self.sources[0],type="MedtronicChronicBrainSense",metadata=metadata)
            payload={"StartTime":BASE,"SamplingRate":-1,"Time":np.array([BASE]),"Data":np.array([[1,2]])}
            with patch.object(service.Database,"loadSourceFile",return_value=[None,payload]):
                result=service._load_recordings(self.person.uid,service.CHRONIC_TYPES)
            self.assertEqual(len(result),1)
            for key,value in metadata.items():self.assertEqual(result[0][key],value)
            self.assertNotIn("clock",result[0]["AnalysisTimeProvenance"])
            rec.delete()

    def test_derived_montage_retains_psds_at_recovered_source_start(self):
        models.Recording.objects.create(source=self.sources[0], type="NeuralActivitySnapshot")
        payload={"StartTime":BASE+7500,"SamplingRate":250,"Data":np.ones((2,1)),
                 "PSD":[{"Frequency":[1,2],"Power":[3,4]}]}
        with patch.object(service.Database,"loadSourceFile",return_value=payload):
            rows=service._load_recordings(self.person.uid,["NeuralActivitySnapshot"])
        self.assertEqual(rows[0]["StartTime"],BASE+500)
        self.assertEqual(rows[0]["PSD"],payload["PSD"])
        different=deepcopy(rows[0]);different["PSD"][0]["Power"][0]=5
        self.assertEqual(len(service._deduplicate_clock_recordings([rows[0],deepcopy(rows[0]),different])),2)
