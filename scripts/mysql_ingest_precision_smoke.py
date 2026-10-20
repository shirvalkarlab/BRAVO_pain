#!/usr/bin/env python3
"""Synthetic raw-spectrum identity checks against the disposable CI MySQL server.

This is invoked only by smoke_container_deployment.py after empty-schema migration.
The synthetic exports use the real encrypted source loader and MySQL JSON column.
No participant-origin values, external integrations or restored databases are used.
"""
import copy
import json
import math
import os
from pathlib import Path

SIDE = "HemisphereLocationDef.Left"


def synthetic_document(value, sense="ZERO_AND_TWO", alternate_numeric_encoding=False):
    block = {"DateTime": "2020-01-01T00:00:01Z", "DateTimeBlockId": 7,
             "DateTimeOffsetInSeconds": 10, "Frequency": [0.0, 1.0, 2.0],
             "FFTBinData": [value, 0.0, -1.0], "SenseID": sense}
    document = {
        "SessionDate": "2020-01-01T00:01:00Z", "SessionEndDate": "2020-01-01T00:01:10Z",
        "DeviceInformation": {
            "Initial": {"DeviceDateTimeOffsetInSeconds": 90, "DeviceDateTimeBlockId": 7},
            "Final": {"DeviceDateTimeOffsetInSeconds": 100, "DeviceDateTimeBlockId": 7,
                      "NeurostimulatorSerialNumber": "SYNTHETIC-MYSQL-SMOKE"}},
        "DiagnosticData": {"LfpFrequencySnapshotEvents": [{
            "DateTime": "2020-01-01T00:00:01Z", "DateTimeBlockId": 7,
            "DateTimeOffsetInSeconds": 10, "EventID": 1, "EventName": "Synthetic SQL precision",
            "LfpFrequencySnapshotEvents": {SIDE: block}}]},
    }
    if alternate_numeric_encoding:
        # Exactly equal values with different JSON numeric encodings. Signed zero
        # is equal too; neighboring nonintegral doubles above remain distinct.
        block["Frequency"] = [0, 1, 2]
        block["FFTBinData"] = [value, -0.0, -1]
        event = document["DiagnosticData"]["LfpFrequencySnapshotEvents"][0]
        event["EventID"] = 1.0
        for item in (event, block):
            item["DateTimeBlockId"] = 7.0
            item["DateTimeOffsetInSeconds"] = 10.0
        for endpoint in ("Initial", "Final"):
            info = document["DeviceInformation"][endpoint]
            info["DeviceDateTimeBlockId"] = 7.0
            info["DeviceDateTimeOffsetInSeconds"] = float(info["DeviceDateTimeOffsetInSeconds"])
    return document


def synthetic_collision(connection):
    """Find a bounded, independently generated counterexample in this pinned DB.

    Neighboring doubles of simple rational numbers provide synthetic candidates.
    SQL is only the storage-projection oracle, never the source identity oracle.
    A missing counterexample fails this gate instead of silently skipping it.
    """
    candidates = set()
    for denominator in (3, 7, 10, 11, 13):
        for numerator in range(1, 13):
            center = numerator / denominator
            candidates.add(center)
            for direction in (-math.inf, math.inf):
                value = center
                for _ in range(8):
                    value = math.nextafter(value, direction)
                    candidates.add(value)
    candidates = sorted(candidates)
    with connection.cursor() as cursor:
        cursor.execute("SELECT JSON_EXTRACT(%s, '$')", [json.dumps(candidates, allow_nan=False)])
        projected = json.loads(cursor.fetchone()[0])
    assert len(projected) == len(candidates)
    groups = {}
    for raw, stored in zip(candidates, projected):
        groups.setdefault(float(stored).hex(), []).append((raw, stored))
    for members in groups.values():
        if len(members) > 1:
            first = next((pair for pair in members if pair[0] != pair[1]), None)
            if first is not None:
                second = next(pair for pair in members if pair[0] != first[0])
                assert first[0] != second[0] and first[1] == second[1]
                return first[0], second[0], first[1]
    raise AssertionError("Pinned MySQL did not reproduce synthetic numeric projection collision")


def main():
    if (os.environ.get("BRAVO_SYNTHETIC_INGEST_SMOKE") != "1" or
            os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise SystemExit("MySQL ingest smoke requires the disposable hosted CI harness")
    import django
    django.setup()
    from django.db import connection, transaction
    from Server import models
    from modules import DataCurator
    from modules.MedtronicPercept import BrainSenseEvent as events, TabletClock, Percept

    assert connection.vendor == "mysql" and connection.settings_dict["NAME"] == "bravo_aditya"
    assert connection.settings_dict["HOST"] == "mysql"
    for model in (models.Participant, models.SourceFile, models.Recording, models.DBSEvent):
        assert not model.objects.exists(), "Ingest smoke refuses any existing source/participant data"
    raw_a, raw_b, projected = synthetic_collision(connection)
    assert raw_a != projected and raw_a != raw_b
    paths = []
    table_name = connection.ops.quote_name(models.Recording._meta.db_table)
    snapshot_name = "bravo_synthetic_ingest_snapshot"
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE TEMPORARY TABLE {snapshot_name} (uid VARCHAR(32) PRIMARY KEY, metadata JSON NOT NULL)")

    def make_source(person, value, sense, alternate_numeric_encoding=False):
        raw = synthetic_document(value, sense, alternate_numeric_encoding)
        original = copy.deepcopy(raw)
        anchor = TabletClock.export_anchor(raw)
        table = TabletClock.AnchorTable([anchor])
        source = DataCurator.saveCacheFile("synthetic-mysql.json", {
            "UploadType": "MedtronicJSON", "ClockAnchor": anchor}, json.dumps(raw).encode())
        paths.append(Path(source.pointer))
        source.owner = person
        source.save(update_fields=["owner"])
        index = events.sourceEventIndex(raw, table, TabletClock, Percept)
        assert raw == original and len(index) == 1
        key, entries = next(iter(index.items()))
        assert len(entries) == 1
        event = {"name": key[0], "date": key[1], "type": "PatientControllerEvent",
                 "data": {SIDE: copy.deepcopy(entries[0]["block"])}}
        cache = {"current_key": (source.uid, source.hashed), "current_index": index, "table": table}
        return source, event, cache, entries[0]["identity"]

    def recording(person):
        assert models.Recording.objects.filter(source__owner=person).count() == 1
        assert models.DBSEvent.objects.filter(source__owner=person).count() == 1
        return models.Recording.objects.get(source__owner=person)

    def save_baseline(record):
        with connection.cursor() as cursor:
            cursor.execute(f"INSERT INTO {snapshot_name} SELECT uid, metadata FROM {table_name} WHERE uid=%s", [record.uid])

    def unchanged_spectra(record):
        # Compare original/current JSON values inside MySQL, without a Python
        # decode/re-encode cycle that could itself change their representation.
        with connection.cursor() as cursor:
            for field in ("Frequency", "FFTBinData"):
                path = '$."' + SIDE + '"."' + field + '"'
                cursor.execute(f"SELECT JSON_EXTRACT(r.metadata,%s)=JSON_EXTRACT(b.metadata,%s) "
                               f"FROM {table_name} r JOIN {snapshot_name} b ON r.uid=b.uid WHERE r.uid=%s",
                               [path, path, record.uid])
                assert cursor.fetchone()[0] == 1, field

    def legacy(person, source, event):
        record = models.Recording.objects.create(name=event["name"], type=event["type"],
            date=event["date"], source=source, metadata=event["data"])
        row = models.DBSEvent.objects.create(name=event["name"], type=event["type"],
            date=event["date"], source=source)
        row.data.add(record)
        record.refresh_from_db()
        assert "RawSpectrumIdentity" not in record.metadata[SIDE]
        return record

    try:
        with transaction.atomic():
            for is_legacy in (False, True):
                for incoming_kind in ("same", "different", "numeric_encoding"):
                    different_raw = incoming_kind == "different"
                    person = models.Participant.objects.create(name="Synthetic MySQL ingest")
                    source, event, cache, identity = make_source(person, raw_a, "ZERO_AND_TWO")
                    if is_legacy:
                        record = legacy(person, source, event)
                    else:
                        assert DataCurator._store_patient_event(event, source, person, cache) == "create"
                        record = recording(person)
                        assert record.metadata[SIDE]["RawSpectrumIdentity"]["sha256"] == identity["sha256"]
                    assert record.metadata[SIDE]["FFTBinData"][0] == projected
                    save_baseline(record)
                    incoming, new_event, new_cache, new_identity = make_source(
                        person, raw_b if different_raw else raw_a, "ONE_AND_THREE",
                        alternate_numeric_encoding=incoming_kind == "numeric_encoding")
                    assert (new_identity["sha256"] != identity["sha256"]) == different_raw, incoming_kind
                    assert new_identity["raw_identity_sha256"] == identity["raw_identity_sha256"], incoming_kind
                    # Legacy identities deliberately recover through encrypted
                    # source/HMAC verification; no pre-populated legacy cache.
                    DataCurator._store_patient_event(new_event, incoming, person, new_cache)
                    record = recording(person)
                    unchanged_spectra(record)
                    block = record.metadata[SIDE]
                    if different_raw:
                        assert block["SenseID"] == "ZERO_AND_TWO"
                        assert not block.get("SenseIDConflict", False)
                        assert incoming.metadata["IngestConflicts"][0]["sides"] == [SIDE]
                        assert len(block.get("SenseIDObservations", [])) <= 1
                    else:
                        assert block["SenseID"] == "" and block["SenseIDConflict"] is True
                        assert {entry["sense_id"] for entry in block["SenseIDObservations"]} == {"ZERO_AND_TWO", "ONE_AND_THREE"}
                        assert block["RawSpectrumIdentity"]["sha256"] == identity["sha256"]
                        before = copy.deepcopy(block)
                        assert DataCurator._store_patient_event(new_event, incoming, person, new_cache) == "keep"
                        assert recording(person).metadata[SIDE] == before
                        unchanged_spectra(record)
            transaction.set_rollback(True)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TEMPORARY TABLE IF EXISTS {snapshot_name}")
        for path in paths:
            path.unlink(missing_ok=True)
            Path(str(path) + ".lock").unlink(missing_ok=True)
    assert not models.Participant.objects.exists()
    assert not models.SourceFile.objects.exists()
    print("MySQL ingest precision smoke passed: exact raw identity, legacy encrypted-source recovery, "
          "different-raw/same-SQL rejection, equivalent numeric encodings, spectral JSON preservation and idempotent re-import")
    print("Synthetic projection counterexample (hex):", raw_a.hex(), raw_b.hex(), float(projected).hex())


if __name__ == "__main__":
    main()
