"""Execute the real ingestion module so AST test namespaces cannot hide dependencies."""
from test_optional_oauth_startup import isolated


def test_actual_module_event_ingestion_preserves_spectrum_and_marks_conflict(tmp_path):
    isolated(tmp_path, '''
        from django.core.management import call_command
        from Server import models
        from modules import DataCurator
        from modules.MedtronicPercept import BrainSenseEvent, TabletClock, Percept
        import json

        call_command("migrate", verbosity=0, interactive=False)
        person = models.Participant.objects.create(name="Synthetic module regression")
        side = "HemisphereLocationDef.Left"
        raw = {
            "SessionDate": "2020-01-01T00:01:00Z", "SessionEndDate": "2020-01-01T00:01:10Z",
            "DeviceInformation": {
                "Initial": {"DeviceDateTimeOffsetInSeconds": 90, "DeviceDateTimeBlockId": 7},
                "Final": {"DeviceDateTimeOffsetInSeconds": 100, "DeviceDateTimeBlockId": 7,
                          "NeurostimulatorSerialNumber": "SYNTHETIC-MODULE"}},
            "DiagnosticData": {"LfpFrequencySnapshotEvents": [{
                "DateTime": "2020-01-01T00:00:01Z", "DateTimeBlockId": 7,
                "DateTimeOffsetInSeconds": 10, "EventID": 1, "EventName": "Synthetic event",
                "LfpFrequencySnapshotEvents": {side: {
                    "DateTime": "2020-01-01T00:00:01Z", "DateTimeBlockId": 7,
                    "DateTimeOffsetInSeconds": 10, "SenseID": "ZERO_AND_TWO",
                    "Frequency": [0.0, 1.0, 2.0], "FFTBinData": [0.1, 0.0, -1.0]}}}]}}
        source = DataCurator.saveCacheFile("synthetic.json", {"UploadType": "MedtronicJSON"}, json.dumps(raw).encode())
        source.owner = person
        source.save(update_fields=["owner"])
        table = TabletClock.AnchorTable([TabletClock.export_anchor(raw)])
        # Real encrypted loader, real compact cache, real canonical projection.
        index = DataCurator._event_source_index(source, {"table": table})
        (name, timestamp, hemisphere), entries = next(iter(index.items()))
        assert timestamp == 1577836780.0 and hemisphere == side
        event = {"name": name, "date": timestamp, "type": "PatientControllerEvent",
                 "data": {side: entries[0]["block"]}}
        assert DataCurator._store_patient_event(event, source, person) == "create"
        assert DataCurator._store_patient_event(event, source, person) == "keep"
        event["data"][side]["SenseID"] = "ONE_AND_THREE"
        assert DataCurator._store_patient_event(event, source, person) == "update"
        assert DataCurator._store_patient_event(event, source, person) == "keep"
        record = models.Recording.objects.get(source=source)
        assert record.metadata[side]["FFTBinData"] == [0.1, 0.0, -1.0]
        assert record.metadata[side]["SenseID"] == ""
        assert record.metadata[side]["SenseIDConflict"] is True
        assert len(record.metadata[side]["SenseIDObservations"]) == 2
        assert len(source.metadata["IngestConflicts"]) == 1
    ''')
