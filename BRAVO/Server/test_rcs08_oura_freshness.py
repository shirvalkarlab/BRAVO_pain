import datetime as dt
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from django.core.management.base import CommandError
from modules import RCS08OuraFreshness as fresh
from modules import Database, RCS08Sync
from Server.management.commands.index_rcs08_oura_measurement import Command

pytestmark = pytest.mark.usefixtures("synthetic_oura_policy")

NOW = dt.datetime(2026, 9, 5, 12, tzinfo=dt.timezone.utc).timestamp()


def row(times=None, values=None, names=None):
    values = values if values is not None else [[70., 1.]]
    return {"Time": times if times is not None else [NOW - 600], "StartTime": NOW - 600,
            "SamplingRate": 1 / 60, "Data": values, "Missing": [[0] * len(v) for v in values],
            "ChannelNames": names or ["Heart Rate", "Heart Rate State"], "Descriptor": {},
            "Metadata": {"DayLabel": "2026-09-05"}}


def test_only_native_observed_hr_hrv_samples_count_after_qc():
    hr = row([NOW - 300, NOW - 1, NOW + 1, NOW - 2], [[70, 1], [0, 1], [99, 1], [80, 1]])
    hr["Missing"][-1][0] = 1
    sleep = row(values=[[0, 30], [float("nan"), 40]], names=["Heart Rate", "Heart Rate Variability"])
    sleep.pop("Time")
    sleep["StartTime"] = NOW - 120
    padded = row([NOW - 1])
    data = {"HeartRate": [hr], "Sleep": [sleep], "DailyActivity": [padded]}
    result = fresh.summarize(data, "p", "h", now=NOW)
    assert result["value"] == dt.datetime.fromtimestamp(NOW - 60, dt.timezone.utc).isoformat()
    assert result["coverage"]["channels"] == ["HeartRate: Heart Rate", "Sleep: Heart Rate Variability"]
    assert hr["Data"][0][0] == 70 and hr["Missing"][-1][0] == 1
    assert not result["partial"]
    staff = row([dt.datetime(2026, 5, 26, 12, tzinfo=dt.timezone.utc).timestamp()])
    assert not fresh.summarize({"HeartRate": [staff]}, "p", "h", now=NOW)["available"]


def test_unknown_missing_mask_bad_clock_shape_and_channels_remain_partial(monkeypatch):
    no_mask = row(); no_mask.pop("Missing")
    no_time = row(); no_time.pop("Time")
    bad_shape = row(); bad_shape["ChannelNames"] = ["Heart Rate"]
    bad_clock = row(); bad_clock["Time"] = [NOW, NOW + 1]
    unknown = row(names=["State", "Movement"])
    zero_hrv = row(names=["HRV"], values=[[0.]])
    monkeypatch.setattr(fresh.time, "time", lambda: NOW)
    result = fresh.summarize({"HeartRate": [no_mask, no_time, bad_shape, bad_clock, unknown],
                              "Sleep": [zero_hrv]}, "p", "h")
    assert result["available"] and result["partial"]
    assert result["coverage"]["invalid_records"] == 4
    assert result["coverage"]["channels"] == ["Sleep: HRV"]
    assert not fresh.summarize({}, "p", "h", now=NOW)["available"]


def test_cached_status_is_owner_hash_policy_scoped_and_never_reads_samples(monkeypatch):
    person = NS(uid="p")
    snapshot = fresh.summarize({"HeartRate": [row()]}, "p", "h", now=NOW)
    source = NS(owner_id="p", hashed="h", metadata={fresh.KEY: snapshot})
    monkeypatch.setattr(fresh.models.SourceFile, "find", lambda **kwargs: source)
    loader = Mock(side_effect=AssertionError("no arrays/network during status"))
    monkeypatch.setattr(Database, "loadSourceFile", loader)
    assert fresh.read_cached(person, NOW)["value"] == snapshot["value"]
    for field, value in [("participant_id", "other"), ("source_hash", "wrong"), ("qc_version", "old"),
                          ("qc_sha256", "wrong"), ("version", "old")]:
        source.metadata[fresh.KEY] = {**snapshot, field: value}
        assert not fresh.read_cached(person, NOW)["available"]
    source.metadata[fresh.KEY] = snapshot
    source.owner_id = "other"
    assert not fresh.read_cached(person, NOW)["available"]
    source.owner_id = "p"
    for value in ["bad", None, "2030-01-01T00:00:00+00:00", "2026-01-01T00:00:00"]:
        source.metadata[fresh.KEY] = {**snapshot, "value": value}
        assert not fresh.read_cached(person, NOW)["available"]
    source.metadata[fresh.KEY] = {**snapshot, "available": False}
    assert not fresh.read_cached(person, NOW)["available"]
    source.metadata = {}
    assert not fresh.read_cached(person, NOW)["available"]
    monkeypatch.setattr(fresh.models.SourceFile, "find", lambda **kwargs: None)
    assert not fresh.read_cached(person, NOW)["available"]
    loader.assert_not_called()


def test_index_command_reads_existing_snapshot_and_updates_metadata_only(monkeypatch):
    person = NS(uid="p")
    source = NS(owner_id="p", pointer="stored", hashed="h", metadata={"keep": 1}, save=Mock())
    monkeypatch.setattr(fresh.models.SourceFile, "find", lambda **kwargs: source)
    monkeypatch.setattr(Database, "loadSourceFile", lambda pointer, digest: {"HeartRate": [row()]})
    monkeypatch.setattr(fresh.time, "time", lambda: NOW)
    resolve = Mock(return_value=person)
    monkeypatch.setattr(RCS08Sync, "resolve_participant", resolve)
    monkeypatch.setattr(RCS08Sync, "run_sync", Mock(side_effect=AssertionError("no sync")))
    cmd = Command(); cmd.stdout = Mock(); cmd.handle()
    resolve.assert_called_once_with(create=False)
    source.save.assert_called_once_with(update_fields=["metadata"])
    assert source.metadata["keep"] == 1 and source.hashed == "h" and source.pointer == "stored"
    assert fresh.read_cached(person, NOW)["available"]
    monkeypatch.setattr(fresh.models.SourceFile, "find", lambda **kwargs: None)
    with pytest.raises(CommandError, match="existing Oura"):
        cmd.handle()


def test_existing_sync_publishes_measurement_metadata_but_dry_run_does_not(monkeypatch):
    person = NS(uid="p")
    source = NS(owner_id="p", hashed="h", metadata={"SleepProcessingVersion": 2}, save=Mock())
    data = {key: [] for key in RCS08Sync.OURA_KEYS}
    data["HeartRate"] = [row()]
    monkeypatch.setattr(fresh.time, "time", lambda: NOW)
    monkeypatch.setattr(RCS08Sync, "_load_secret", lambda *args: {"access_token": "synthetic"})
    monkeypatch.setattr(RCS08Sync.OuraDataManager, "OuraRingAPI", lambda *args: NS(verifyToken=lambda: None))
    monkeypatch.setattr(RCS08Sync.OuraDataManager, "loadOuraRingData", lambda *args, **kwargs: data)
    monkeypatch.setattr(RCS08Sync.models.SourceFile, "find", lambda **kwargs: source)
    monkeypatch.setattr(RCS08Sync, "_fetch_oura_chunk", lambda *args: data)
    monkeypatch.setattr(RCS08Sync, "OURA_START_DATE", "2026-09-01")
    save_snapshot = Mock(return_value=source)
    monkeypatch.setattr(RCS08Sync, "_save_oura_snapshot", save_snapshot)
    monkeypatch.setattr(RCS08Sync.models.OuraRingDevice, "find", lambda **kwargs: NS(save=lambda: None))
    RCS08Sync.sync_oura(person, dry_run=True)
    source.save.assert_not_called()
    save_snapshot.assert_not_called()
    assert fresh.KEY not in source.metadata
    RCS08Sync.sync_oura(person)
    source.save.assert_called_once()
    save_snapshot.assert_called_once()
    snapshot = source.metadata[fresh.KEY]
    assert snapshot["value"] == dt.datetime.fromtimestamp(NOW - 600, dt.timezone.utc).isoformat()
    assert snapshot["value"] != source.metadata["LastSuccessfulSync"]
