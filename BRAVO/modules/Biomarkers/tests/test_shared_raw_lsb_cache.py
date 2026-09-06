"""Synthetic storage, invalidation and concurrency tests for Aditya's raw tile cache."""
import ast
import hashlib
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
import pickle
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

SOURCE = Path(__file__).parents[1] / "bravo_service.py"
NAMES = ("_raw_lsb_signature", "_raw_lsb_shared_path", "_raw_lsb_shared_load",
         "_raw_lsb_shared_store", "_raw_lsb_cache_cached")


@pytest.fixture
def cache(tmp_path):
    # Compile actual production bodies with original source locations; only the
    # ORM and expensive DSP boundary are replaced. No Django/private input access.
    analytics = SimpleNamespace(__file__=str(SOURCE), RAW_LSB_WINDOW_SECONDS=3.,
                                LSB_PER_UV2_TRANSFORM=352.62, LSB_PER_DEVICE_PSD=73.63)
    availability = SimpleNamespace(__file__=str(SOURCE), PRO_LSB_SATURATION_UV=1000.,
                                   _canon_channel=lambda ch: ch,
                                   raw_lsb_spectrum_cache=Mock(return_value={"td": {"lsb": [[1., None]]}, "psd": {}, "centers_hz": [12.5], "window_s": 3.}))
    ns = dict(__file__=str(SOURCE), np=np, os=os, analytics=analytics,
              availability=availability, _log=logging.getLogger(__name__),
              _RAW_LSB_SHARED_FORMAT=2, _RAW_LSB_SHARED_MAX_BYTES=1024 * 1024,
              _RAW_LSB_CACHE_MEMO={}, _RAW_LSB_CACHE_MEMO_MAX=2,
              _RAW_LSB_CACHE_MEMO_LOCK=threading.Lock(), _LSB_SPECTRUM_CENTERS=(12.5,),
              _psd_cache_dir=lambda: str(tmp_path / "psd"),
              _analysis_identity=Mock(return_value="canonical-A"))
    tree = ast.parse(SOURCE.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
    assert len(nodes) == len(NAMES)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


def run(c, **kwargs):
    return c["_raw_lsb_cache_cached"]("synthetic", ["Left"], [{"Data": np.array([1., np.nan])}], [], **kwargs)


def test_roundtrip_memo_and_cross_worker_identity(cache):
    first = run(cache)
    assert run(cache) is first
    cache["_RAW_LSB_CACHE_MEMO"].clear()
    loaded = run(cache)
    assert loaded == first
    cache["availability"].raw_lsb_spectrum_cache.assert_called_once()
    path = cache["_raw_lsb_shared_path"]("synthetic")
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_signature_and_store_stream_without_whole_payload_buffer(cache, monkeypatch):
    td = [{'Data': np.arange(100000, dtype=float)}]
    expected = hashlib.sha256(pickle.dumps((td, [], None), protocol=5)).hexdigest()
    monkeypatch.setattr(pickle, 'dumps', Mock(side_effect=AssertionError('whole payload copied')))
    signature = cache['_raw_lsb_signature']('synthetic', ['Left'], td, [], None, (12.5,), 'canonical-A')
    assert signature[4] == expected
    assert cache['_raw_lsb_shared_store']('synthetic', signature, {'value': np.arange(10000)})
    loaded = cache['_raw_lsb_shared_load']('synthetic', signature)
    np.testing.assert_array_equal(loaded['value'], np.arange(10000))


@pytest.mark.parametrize("change", ["policy", "decoded", "calibration", "code", "centers", "channel", "metadata", "participant"])
def test_every_dependency_invalidates(cache, tmp_path, change):
    args = ["synthetic", ["Left"], [{"Data": np.array([1., np.nan])}], [], None, (12.5,), "canonical-A"]
    before = cache["_raw_lsb_signature"](*args)
    if change == "policy": args[6] = "canonical-B"
    elif change == "decoded": args[2][0]["Data"][0] = 9.
    elif change == "calibration": cache["analytics"].LSB_PER_UV2_TRANSFORM += 1
    elif change == "code":
        other = tmp_path / "producer.py"; other.write_text("changed")
        cache["availability"].__file__ = str(other)
    elif change == "centers": args[5] = (17.5,)
    elif change == "channel": args[1] = ["Right"]
    elif change == "metadata": args[2][0]["adjusted_alignment"] = 5.
    else: args[0] = "other"
    assert cache["_raw_lsb_signature"](*args) != before


def test_canonical_change_rebuilds_disk_and_memory(cache):
    run(cache)
    cache["_analysis_identity"].return_value = "canonical-B"
    run(cache)
    assert cache["availability"].raw_lsb_spectrum_cache.call_count == 2
    assert len(list(Path(cache["_raw_lsb_shared_path"]("synthetic")).parent.glob("*.pkl"))) == 1


@pytest.mark.parametrize("hit", ["build", "memo", "disk"])
def test_canonical_race_never_returns_or_publishes_mixed_inputs(cache, hit):
    if hit != "build": run(cache)
    if hit == "disk": cache["_RAW_LSB_CACHE_MEMO"].clear()
    cache["_analysis_identity"].side_effect = ["canonical-A", "canonical-B"]
    with pytest.raises(RuntimeError, match="inputs changed"):
        run(cache)
    if hit == "build":
        assert not cache["_RAW_LSB_CACHE_MEMO"]
        assert not Path(cache["_raw_lsb_shared_path"]("synthetic")).exists()


def test_channel_failure_is_not_cached(cache):
    cache["availability"].raw_lsb_spectrum_cache.side_effect = RuntimeError("unreadable source")
    with pytest.raises(RuntimeError): run(cache)
    assert not cache["_RAW_LSB_CACHE_MEMO"]


def test_disabled_disk_and_empty_channels(cache):
    cache["_raw_lsb_shared_load"] = Mock(side_effect=AssertionError("disk touched"))
    cache["_raw_lsb_shared_store"] = Mock(side_effect=AssertionError("disk touched"))
    run(cache, use_shared_cache=False)
    assert cache["_raw_lsb_cache_cached"]("synthetic", [], [], []) == {}


def test_partial_and_nondict_disk_entries_rebuild(cache):
    for bad in ({"Right": {}}, ["Left"], {"Left": None}, {"Left": {}}):
        cache["_RAW_LSB_CACHE_MEMO"].clear()
        cache["_raw_lsb_shared_load"] = lambda *args: bad
        assert "Left" in run(cache)
    assert cache["availability"].raw_lsb_spectrum_cache.call_count == 4


def test_memo_bound(cache):
    for identity in ("A", "B", "C"):
        cache["_analysis_identity"].return_value = identity
        run(cache, use_shared_cache=False)
    assert len(cache["_RAW_LSB_CACHE_MEMO"]) == 2


def test_corruption_missing_signature_and_size_refusal(cache):
    load = cache["_raw_lsb_shared_load"]
    path = Path(cache["_raw_lsb_shared_path"]("synthetic"))
    assert load("synthetic", "sig") is None
    for contents in (b"broken", pickle.dumps({}), pickle.dumps({"signature": "other"})):
        path.write_bytes(contents)
        assert load("synthetic", "sig") is None
    cache["_RAW_LSB_SHARED_MAX_BYTES"] = 1
    assert load("synthetic", "sig") is None
    assert not cache["_raw_lsb_shared_store"]("synthetic", "sig", {})


def test_write_failure_cleanup_and_unavailable_directory(cache, monkeypatch):
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("denied")))
    assert not cache["_raw_lsb_shared_store"]("synthetic", "sig", {})
    assert not list(Path(cache["_raw_lsb_shared_path"]("synthetic")).parent.glob(".raw-lsb-*"))
    cache["_psd_cache_dir"] = Mock(side_effect=OSError("not configured"))
    assert cache["_raw_lsb_shared_load"]("synthetic", "sig") is None
    assert not cache["_raw_lsb_shared_store"]("synthetic", "sig", {})


def test_concurrent_writers_use_unique_temporary_files(cache):
    store = cache["_raw_lsb_shared_store"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(lambda i: store("synthetic", "sig", {"value": i}), range(24)))
    assert cache["_raw_lsb_shared_load"]("synthetic", "sig")["value"] in range(24)
    assert not list(Path(cache["_raw_lsb_shared_path"]("synthetic")).parent.glob(".raw-lsb-*"))
