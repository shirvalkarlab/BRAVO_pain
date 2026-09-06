"""Supplied settings retain canonical results and fail visibly when malformed."""
import sys
import types
from unittest.mock import Mock

import pandas as pd
import pytest

from StimOptimizer import adapter


@pytest.fixture
def stream():
    frame = pd.DataFrame([
        dict(t=pd.Timestamp(day, tz="UTC"), src="history", hemi=hemi,
             amp=amp, pw=90, rate=100, cathode="0", schema="legacy")
        for day, amp in [("2025-07-20", 1), ("2025-07-22", 2)]
        for hemi in ("Left", "Right")
    ])
    frame.attrs["provenance"] = {"source_ids": ["synthetic-source"]}
    return frame


@pytest.fixture
def biomarkers(monkeypatch):
    reports = pd.DataFrame({
        "nrs": [0, 8],
        "t_utc": pd.to_datetime(["2025-07-21", "2025-07-23"]),
    })
    service = types.SimpleNamespace(
        _load_pros=Mock(return_value=reports),
        _pro_times_utc_series=lambda frame: frame.t_utc,
        _cached_psd_matrix=Mock(return_value=None),
    )
    module = types.ModuleType("modules.Biomarkers")
    module.bravo_service = service
    monkeypatch.setitem(sys.modules, "modules.Biomarkers", module)
    return service


def test_none_builds_once_and_supplied_frame_is_reused(monkeypatch, stream):
    participant = object()
    loader = Mock(return_value=stream)
    monkeypatch.setattr(adapter, "settings_stream", loader)
    assert adapter._use_stream_or_build_one(participant, None) is stream
    loader.assert_called_once_with(participant)
    assert adapter._use_stream_or_build_one(participant, stream) is stream
    loader.assert_called_once_with(participant)


@pytest.mark.parametrize("consumer", ["build_design_matrix", "evidence_inputs"])
def test_empty_frame_is_valid_but_unlabelled_empty_is_rejected(
        monkeypatch, stream, biomarkers, consumer):
    empty = stream.iloc[:0].copy()
    loader = Mock(side_effect=AssertionError("supplied stream must not reload"))
    monkeypatch.setattr(adapter, "settings_stream", loader)
    function = getattr(adapter, consumer)
    result = function("synthetic", stream=empty)
    if consumer == "build_design_matrix":
        assert result.empty
    else:
        assert result[0] is None
        assert result[1].empty
    with pytest.raises(KeyError, match="missing the columns"):
        function("synthetic", stream=pd.DataFrame())
    loader.assert_not_called()


@pytest.mark.parametrize("consumer", ["build_design_matrix", "evidence_inputs"])
@pytest.mark.parametrize("bad", [{"t": [1]}, [1, 2], "stream", 7])
def test_nonframe_is_rejected_before_data_loading(
        monkeypatch, biomarkers, consumer, bad):
    loader = Mock()
    monkeypatch.setattr(adapter, "settings_stream", loader)
    with pytest.raises(TypeError, match="pandas frame"):
        getattr(adapter, consumer)("synthetic", stream=bad)
    loader.assert_not_called()
    biomarkers._load_pros.assert_not_called()
    biomarkers._cached_psd_matrix.assert_not_called()


@pytest.mark.parametrize("consumer", ["build_design_matrix", "evidence_inputs"])
@pytest.mark.parametrize("missing", ["t", "src", "hemi", "amp", "pw", "rate", "cathode", "schema"])
def test_missing_column_is_named_before_data_loading(
        monkeypatch, stream, biomarkers, consumer, missing):
    loader = Mock()
    monkeypatch.setattr(adapter, "settings_stream", loader)
    with pytest.raises(KeyError, match=missing):
        getattr(adapter, consumer)("synthetic", stream=stream.drop(columns=missing))
    loader.assert_not_called()
    biomarkers._load_pros.assert_not_called()
    biomarkers._cached_psd_matrix.assert_not_called()


def test_shared_frame_keeps_epochs_ratings_and_provenance(monkeypatch, stream, biomarkers):
    loader = Mock(return_value=stream)
    monkeypatch.setattr(adapter, "settings_stream", loader)
    before = stream.copy(deep=True)
    built = adapter.build_design_matrix("synthetic")
    _, built_epochs = adapter.evidence_inputs("synthetic")
    assert loader.call_count == 2
    supplied = adapter.build_design_matrix("synthetic", stream=stream)
    psd, supplied_epochs = adapter.evidence_inputs("synthetic", stream=stream)
    assert loader.call_count == 2
    pd.testing.assert_frame_equal(built, supplied)
    pd.testing.assert_frame_equal(built_epochs, supplied_epochs)
    pd.testing.assert_frame_equal(stream, before)
    assert stream.attrs == before.attrs
    assert psd is None
    assert supplied.n.tolist() == [1, 1]
    assert supplied.nrs.tolist() == [0, 8]
    assert supplied.amp_mA_Left.tolist() == [1, 2]
    assert supplied.amp_mA_Right.tolist() == [1, 2]


def test_supplied_frame_keeps_washin_items_and_cached_psd_path(monkeypatch, stream, biomarkers):
    from StimOptimizer.routines import lfp_evidence

    participant = types.SimpleNamespace(uid="synthetic")
    request = {"ParticipantId": "synthetic", "Selection": "preserved"}
    loader = Mock(side_effect=AssertionError("supplied stream must not reload"))
    monkeypatch.setattr(adapter, "settings_stream", loader)
    result = adapter.build_design_matrix(participant, request, stream=stream,
                                          washin_min=60 * 24 * 30, items=("nrs",))
    assert result.empty
    biomarkers._load_pros.assert_called_once_with(request, participant)
    matrix = object()
    psd = pd.DataFrame({"synthetic": [1]})
    biomarkers._cached_psd_matrix.return_value = matrix
    converter = Mock(return_value=psd)
    monkeypatch.setattr(lfp_evidence, "frame_from_matrix", converter)
    sources = ["synthetic-source"]
    result_psd, epochs = adapter.evidence_inputs(
        participant, force_refresh=True, sources=sources, stream=stream)
    assert result_psd is psd
    assert len(epochs) == 2
    biomarkers._cached_psd_matrix.assert_called_once_with("synthetic", force_refresh=True)
    converter.assert_called_once_with(matrix, sources=sources)
    loader.assert_not_called()


@pytest.mark.parametrize("consumer", ["build_design_matrix", "evidence_inputs"])
def test_canonical_loader_failure_is_not_replaced_or_swallowed(monkeypatch, biomarkers, consumer):
    failure = RuntimeError("synthetic unreadable eligible source")
    loader = Mock(side_effect=failure)
    monkeypatch.setattr(adapter, "settings_stream", loader)
    with pytest.raises(RuntimeError) as caught:
        getattr(adapter, consumer)("synthetic")
    assert caught.value is failure
    loader.assert_called_once_with("synthetic")
    biomarkers._load_pros.assert_not_called()
    biomarkers._cached_psd_matrix.assert_not_called()
