"""Real raw-series API serializes missing streaming readings as JSON null."""
from copy import deepcopy
from types import SimpleNamespace
import json

import numpy as np
import pytest
from rest_framework.renderers import JSONRenderer

from Server.APIs import DataHandler as API


@pytest.mark.parametrize("channel", [None, "0"])
def test_actual_raw_api_renders_missing_power_and_reading_time_as_null(monkeypatch, channel):
    payload = {"Data": np.array([[1.0, 2.0], [np.nan, np.nan], [3.0, np.inf]]),
               "Missing": np.array([[0, 0], [1, 1], [0, 1]]), "SamplingRate": 2,
               "ReadingTime": np.array([0.0, np.nan, 1.1])}
    stored = deepcopy(payload)
    row = SimpleNamespace(source=SimpleNamespace(owner=SimpleNamespace(uid="synthetic-owner")),
                          pointer="synthetic", hashed="synthetic", adjusted_alignment=0)
    monkeypatch.setattr(API.Database, "checkAccessPermission", lambda *a, **k: True)
    monkeypatch.setattr(API.models.Recording, "find", lambda **k: row)
    monkeypatch.setattr(API.Database, "loadSourceFile", lambda *a: deepcopy(stored))
    req = SimpleNamespace(data={"ParticipantId": "synthetic-owner", "RequestType": "RawTimeseries",
                                "RecordingId": "synthetic-row"}, user=SimpleNamespace(configuration={}))
    if channel is not None:
        req.data["ChannelIndex"] = channel
    response = API.TimeSeriesRecordingHandler.post.__wrapped__(API.TimeSeriesRecordingHandler(), req)
    assert response.status_code == 200
    result = json.loads(JSONRenderer().render(response.data))
    assert result["Data"] == ([1, None, 3] if channel else [[1, 2], [None, None], [3, None]])
    assert result["ReadingTime"] == [0, None, 1.1]
    assert result["Time"] == [0, 0.5, 1]
    assert np.isnan(stored["Data"][1]).all()


def test_integer_legacy_array_without_reading_time_remains_unchanged(monkeypatch):
    row = SimpleNamespace(source=SimpleNamespace(owner=SimpleNamespace(uid="synthetic-owner")),
                          pointer="synthetic", hashed="synthetic", adjusted_alignment=0)
    monkeypatch.setattr(API.Database, "checkAccessPermission", lambda *a, **k: True)
    monkeypatch.setattr(API.models.Recording, "find", lambda **k: row)
    monkeypatch.setattr(API.Database, "loadSourceFile", lambda *a: {"Data": np.array([[0], [7]]),
        "Time": np.array([0, 1]), "SamplingRate": 1})
    req = SimpleNamespace(data={"ParticipantId": "synthetic-owner", "RequestType": "RawTimeseries",
                                "RecordingId": "synthetic-row"}, user=SimpleNamespace(configuration={}))
    response = API.TimeSeriesRecordingHandler.post.__wrapped__(API.TimeSeriesRecordingHandler(), req)
    result = json.loads(JSONRenderer().render(response.data))
    assert result["Data"] == [[0], [7]] and "ReadingTime" not in result
