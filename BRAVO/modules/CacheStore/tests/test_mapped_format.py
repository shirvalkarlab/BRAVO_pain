"""The store's "mapped" format: one saved copy read by every worker through the disk cache.

WHY (the PI, 2026-10-04: "go ahead and implement shared memory scheme"; measured 2026-10-04 in
decision 414). Each of the 16 web workers held its own decoded copy of RCS08's recordings, about
6.7 GB a worker. Mapped, the arrays are read from one file on the volume: every worker's pages come
from the same disk-cache pages, so the copy is held once (measured: 6,621 MB shared and 129 MB
private per process, against 6,733 MB private for a process holding its own copy).

WHAT IS PINNED HERE, each on the values it produces:

  * a nested payload (dicts, lists, arrays of several types, a table, strings) comes back equal,
    every array with its own type and shape;
  * the arrays come back BACKED BY THE FILE, not copied into the process;
  * each read is its own copy-on-write view: writing into an array one read returned changes
    neither the file nor any other read (the loaders change recordings in place, and today every
    caller gets a deep copy for exactly that reason);
  * a damaged file or a sidecar for another signature is a miss, never an error or a wrong answer;
  * the format is used only when a caller asks for it; every other payload is stored as before.

Plain `assert` throughout, for the container's runner.
"""
import mmap
import os

import numpy as np
import pandas as pd

from modules.CacheStore import store as st
from modules.CacheStore.tests.test_store import _Sandbox, UID

KIND = "therapy_settings"            # a raw kind: needs no writer, so the tests stay about the format
SIG = ("mapped-test", 1)


def _payload():
    rng = np.random.default_rng(0)
    return {
        "recordings": [
            {"Data": rng.normal(size=(3, 5000)).astype(np.float32), "Time": np.arange(5000.0),
             "Channel": "ZERO_TWO_LEFT", "SamplingRate": 250, "Missing": None},
            {"Data": rng.integers(0, 9, size=1234, dtype=np.int16), "Flags": np.zeros(7, bool),
             "Nested": {"deep": [np.linspace(0, 1, 11), "text", 3.5]}},
        ],
        "table": pd.DataFrame({"t": np.arange(4.0), "power": [1.0, 2.0, np.nan, 4.0]}),
        "empty": np.zeros((0, 3)),
        "strided": np.arange(20.0)[::2],
    }


def _same(a, b):
    if isinstance(a, np.ndarray):
        return (isinstance(b, np.ndarray) and a.dtype == b.dtype and a.shape == b.shape
                and np.array_equal(a, b, equal_nan=a.dtype.kind == "f"))
    if isinstance(a, pd.DataFrame):
        return isinstance(b, pd.DataFrame) and a.equals(b)
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _backed_by_a_map(a):
    base = a
    while getattr(base, "base", None) is not None:
        base = base.base
        if isinstance(base, mmap.mmap):
            return True
        if isinstance(base, memoryview) and isinstance(base.obj, mmap.mmap):
            return True
    return False


def test_a_nested_payload_round_trips_exactly():
    with _Sandbox():
        p = _payload()
        assert st.store(KIND, UID, SIG, p, fmt="mapped") is True
        got = st.load(KIND, UID, SIG)
        assert got is not None and _same(p, got)
        assert st.read_stamp(KIND, UID, SIG)["format"] == "mapped"


def test_the_arrays_are_read_from_the_file_not_copied():
    with _Sandbox():
        st.store(KIND, UID, SIG, _payload(), fmt="mapped")
        got = st.load(KIND, UID, SIG)
        assert _backed_by_a_map(got["recordings"][0]["Data"])
        assert _backed_by_a_map(got["recordings"][1]["Nested"]["deep"][0])


def test_each_read_is_its_own_copy_and_the_file_is_never_written():
    with _Sandbox():
        st.store(KIND, UID, SIG, _payload(), fmt="mapped")
        path = st._existing_payload_path(st._stem(KIND, UID, SIG))
        before = open(path, "rb").read()
        a = st.load(KIND, UID, SIG)
        b = st.load(KIND, UID, SIG)
        a["recordings"][0]["Data"][:] = -1.0                      # in place, as a loader may do
        a["recordings"][0]["Channel"] = "CHANGED"
        assert float(b["recordings"][0]["Data"][0, 0]) != -1.0
        assert b["recordings"][0]["Channel"] == "ZERO_TWO_LEFT"
        c = st.load(KIND, UID, SIG)
        assert _same(_payload(), c), "a later read sees the stored values"
        assert open(path, "rb").read() == before


def test_every_array_starts_on_a_64_byte_boundary():
    with _Sandbox():
        st.store(KIND, UID, SIG, _payload(), fmt="mapped")
        got = st.load(KIND, UID, SIG)
        for arr in (got["recordings"][0]["Data"], got["recordings"][0]["Time"],
                    got["recordings"][1]["Data"]):
            assert arr.__array_interface__["data"][0] % 64 == 0


def test_a_damaged_file_is_a_miss_and_is_removed():
    with _Sandbox():
        st.store(KIND, UID, SIG, _payload(), fmt="mapped")
        path = st._existing_payload_path(st._stem(KIND, UID, SIG))
        with open(path, "r+b") as fh:
            fh.truncate(100)
        assert st.load(KIND, UID, SIG) is None
        assert not os.path.exists(path)


def test_another_signature_is_a_miss():
    with _Sandbox():
        st.store(KIND, UID, SIG, _payload(), fmt="mapped")
        assert st.load(KIND, UID, ("mapped-test", 2)) is None


def test_the_format_is_used_only_when_asked_for():
    assert st.choose_format(_payload()) == "pickle"
    assert st.choose_format({"a": np.zeros(3)}) == "npz"
    with _Sandbox():
        st.store(KIND, UID, SIG, _payload())
        assert st.read_stamp(KIND, UID, SIG)["format"] == "pickle"


def test_the_newest_entry_is_read_mapped_too():
    with _Sandbox():
        st.store(KIND, UID, SIG, _payload(), fmt="mapped")
        got, stamp = st.load_newest(KIND, UID)
        assert stamp["format"] == "mapped" and _same(_payload(), got)


def test_a_file_that_cannot_be_mapped_is_a_miss_and_is_kept():
    """Running out of file handles is not a damaged entry: the file stays for the next read."""
    import mmap as _mmap_mod
    with _Sandbox():
        st.store(KIND, UID, SIG, _payload(), fmt="mapped")
        path = st._existing_payload_path(st._stem(KIND, UID, SIG))
        real = _mmap_mod.mmap

        def refuse(*a, **k):
            raise OSError(24, "Too many open files")
        _mmap_mod.mmap = refuse
        try:
            assert st.load(KIND, UID, SIG) is None
            assert st.load_newest(KIND, UID)[0] is None
        finally:
            _mmap_mod.mmap = real
        assert os.path.exists(path)
        assert st.load(KIND, UID, SIG) is not None
