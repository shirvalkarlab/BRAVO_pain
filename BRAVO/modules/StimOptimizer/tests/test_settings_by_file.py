"""The per-file settings history (the PI's yes of 2026-09-25, answer 10 of the revised plan).

The settings stream is built by decrypting and parsing every stored Percept session file. Before
this change every new file meant parsing all of them again. Now the rows each file contributed are
kept in the one store, filed under the identity of the file set, and a rebuild parses only the files
it has not seen, reusing the rows of every file whose uid and content hash it has seen.

WHAT THESE TESTS HOLD.

  * A new file is the only file parsed, and the frame is the frame a from-scratch build gives,
    value for value and attribute for attribute.
  * A file whose content hash changed is parsed again; a changed parsing rule parses everything.
  * An unreadable file is never saved as "no rows": nothing is written, and the next build tries it
    again. A file that parses to zero rows is remembered as zero rows.
  * A half-written or unreadable saved entry is not trusted: the build parses everything.
  * The same file set writes nothing (the key decides); the kind is raw and carries no pain column.
  * The implant-date cut is applied after the rows are assembled, exactly as before.

The database and the file loader are stood in for; every test has a store root of its own and the
ledger off, so no test reaches the server's real cache root.
"""
import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
import types

import pandas as pd
import pytest

from StimOptimizer import adapter as AD

st = AD._cache_store
_ledger = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".ledger")
_prov = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".provenance")

UID = "PARTICIPANT"
KIND = getattr(AD, "THERAPY_SETTINGS_BY_FILE_KIND", "therapy_settings_by_file")


def _session(day, amp_left, amp_right=None, *, history=()):
    """A session file's JSON: one active group at `day`, plus dated history snapshots."""
    def group(al, ar):
        ps = {"RateInHertz": 55.0,
              "LeftHemisphere": {"Programs": [{"AmplitudeInMilliAmps": al,
                                              "PulseWidthInMicroSecond": 60.0,
                                              "ElectrodeState": [
                                                  {"Electrode": "ElectrodeDef.SenSight_02",
                                                   "ElectrodeStateResult": "Negative"}]}]}}
        if ar is not None:
            ps["RightHemisphere"] = {"Programs": [{"AmplitudeInMilliAmps": ar,
                                                  "PulseWidthInMicroSecond": 90.0,
                                                  "UpperLimitInMilliAmps": 4.5,
                                                  "ElectrodeState": []}]}
        return {"ActiveGroup": True, "ProgramSettings": ps}
    return {"SessionDate": f"2026-01-{day:02d}T12:00:00Z",
            "Groups": {"Final": [group(amp_left, amp_right),
                                 {"ActiveGroup": False, "ProgramSettings": {"RateInHertz": 130.0}}]},
            "GroupHistory": [{"SessionDate": f"2026-01-{d:02d}T08:00:00Z",
                              "Groups": [group(a, None)]} for d, a in history]}


class _SF:
    def __init__(self, uid, content, type_="MedtronicJSON", ok=True):
        self.uid, self.type, self.ok = uid, type_, ok
        self.set_content(content)

    def set_content(self, content):
        self.content = content
        self.hashed = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


class _World:
    """A stand-in database (SourceFile rows) and file loader that counts what it decrypts."""

    def __init__(self, files):
        self.files, self.loaded = list(files), []

    def load(self, sf):
        self.loaded.append(sf.uid)
        if not sf.ok:
            raise OSError("cannot decrypt")
        return json.dumps(sf.content)


@pytest.fixture
def world(monkeypatch):
    w = _World([_SF("f1", _session(3, 1.0, 2.0, history=[(1, 0.5), (2, 0.8)])),
                _SF("f2", _session(9, 1.5, 2.0, history=[(5, 1.2)])),
                _SF("f3", _session(5, 1.5, None)),                  # interleaved in time on purpose
                _SF("x0", {"not": "a session"}, type_="Eventlog")])  # not a settings file type

    class _Q:
        def filter(self, owner=None):
            return list(w.files)
    models = types.ModuleType("Server.models")
    models.SourceFile = types.SimpleNamespace(objects=_Q())
    server = types.ModuleType("Server")
    server.models = models
    curator = types.ModuleType("modules.DataCurator")
    curator.loadCacheFile = w.load
    modules_pkg = types.ModuleType("modules")
    modules_pkg.DataCurator = curator
    monkeypatch.setitem(sys.modules, "Server", server)
    monkeypatch.setitem(sys.modules, "Server.models", models)
    monkeypatch.setitem(sys.modules, "modules", modules_pkg)
    monkeypatch.setitem(sys.modules, "modules.DataCurator", curator)
    root = tempfile.mkdtemp(prefix="bravo_settings_by_file_")
    monkeypatch.setattr(AD, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(_ledger, "ENABLED", False)
    monkeypatch.setattr(st, "ENABLED", True)
    monkeypatch.setattr(AD._data_start, "data_start_s", lambda participant: 0.0)
    w.root = root
    yield w
    shutil.rmtree(root, ignore_errors=True)


def _scratch_build(monkeypatch):
    """The stream parsed from every file with the store switched off: the reference."""
    monkeypatch.setattr(st, "ENABLED", False)
    try:
        return AD._build_settings_stream(UID)
    finally:
        monkeypatch.setattr(st, "ENABLED", True)


def _same(a, b):
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert a.attrs == b.attrs
    assert [str(x) for x in a["t"]] == [str(x) for x in b["t"]]


def _entry_files(root):
    d = os.path.join(root, KIND)
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def _digest_dir(root):
    out = {}
    d = os.path.join(root, KIND)
    for f in sorted(os.listdir(d)):
        with open(os.path.join(d, f), "rb") as fh:
            out[f] = hashlib.sha256(fh.read()).hexdigest()
    return out


# ---------------------------------------------------------------------------------------------

def test_a_new_file_is_the_only_file_parsed_and_the_frame_is_unchanged(world, monkeypatch):
    first = AD._build_settings_stream(UID)
    assert sorted(world.loaded) == ["f1", "f2", "f3"]
    _same(first, _scratch_build(monkeypatch))

    world.files.insert(1, _SF("f4", _session(7, 2.5, 3.0, history=[(6, 2.0)])))
    world.loaded.clear()
    second = AD._build_settings_stream(UID)
    assert world.loaded == ["f4"], "only the new file is decrypted and parsed"
    world.loaded.clear()
    _same(second, _scratch_build(monkeypatch))
    assert len(second) > len(first)


def test_a_file_whose_content_changed_is_parsed_again(world, monkeypatch):
    AD._build_settings_stream(UID)
    world.files[1].set_content(_session(9, 3.5, 2.0, history=[(5, 1.2)]))
    world.loaded.clear()
    out = AD._build_settings_stream(UID)
    assert world.loaded == ["f2"]
    world.loaded.clear()
    _same(out, _scratch_build(monkeypatch))
    assert 3.5 in set(out["amp"])


def test_a_changed_parsing_rule_reuses_nothing(world, monkeypatch):
    AD._build_settings_stream(UID)
    monkeypatch.setattr(AD, "_settings_parse_digest", lambda: "a different parser")
    world.files.append(_SF("f5", _session(11, 1.0, 1.0)))
    world.loaded.clear()
    AD._build_settings_stream(UID)
    assert sorted(world.loaded) == ["f1", "f2", "f3", "f5"]


def test_an_unreadable_file_is_never_saved_as_no_rows(world, monkeypatch):
    world.files[2].ok = False
    out = AD._build_settings_stream(UID)
    assert out.attrs[AD.UNREADABLE_ATTR] == 1
    assert _entry_files(world.root) == [], "a build with an unreadable file writes no per-file entry"
    world.files[2].ok = True
    world.loaded.clear()
    AD._build_settings_stream(UID)
    assert sorted(world.loaded) == ["f1", "f2", "f3"], "nothing was saved, so everything is parsed"


def test_a_file_that_parses_to_no_rows_is_remembered_as_no_rows(world, monkeypatch):
    world.files.append(_SF("f6", {"SessionDate": "2026-01-12T00:00:00Z", "Groups": {"Final": []}}))
    AD._build_settings_stream(UID)
    world.files.append(_SF("f7", _session(13, 1.0, 1.0)))
    world.loaded.clear()
    out = AD._build_settings_stream(UID)
    assert world.loaded == ["f7"]
    world.loaded.clear()
    _same(out, _scratch_build(monkeypatch))


def test_a_half_written_or_unreadable_entry_is_not_trusted(world, monkeypatch):
    """A crash mid-write leaves a temporary file and no sidecar; a damaged payload has a sidecar
    and cannot be unpickled. Neither may be read as a donor: the build parses every file."""
    AD._build_settings_stream(UID)
    d = os.path.join(world.root, KIND)
    payload = [f for f in os.listdir(d) if f.endswith(".pkl")][0]
    with open(os.path.join(d, payload), "r+b") as fh:
        fh.truncate(40)
    with open(os.path.join(d, payload + ".999.tmp"), "wb") as fh:
        fh.write(b"\x80\x05partial")
    world.files.append(_SF("f8", _session(14, 2.0, 2.0)))
    world.loaded.clear()
    out = AD._build_settings_stream(UID)
    assert sorted(world.loaded) == ["f1", "f2", "f3", "f8"]
    world.loaded.clear()
    _same(out, _scratch_build(monkeypatch))


def test_the_same_file_set_writes_nothing(world):
    AD._build_settings_stream(UID)
    before = _digest_dir(world.root)
    assert any(f.endswith(".meta.json") for f in before), "the entry carries its sidecar"
    world.loaded.clear()
    AD._build_settings_stream(UID)
    assert world.loaded == []
    assert _digest_dir(world.root) == before, "a matching key leaves the directory byte-identical"


def test_one_entry_per_participant_is_kept(world):
    AD._build_settings_stream(UID)
    world.files.append(_SF("f9", _session(15, 2.0, 2.0)))
    AD._build_settings_stream(UID)
    metas = [f for f in _entry_files(world.root) if f.endswith(".meta.json")]
    assert len(metas) == 1


def test_the_kind_is_raw_and_carries_no_pain_rating(world):
    assert KIND in _prov.RAW_KINDS
    AD._build_settings_stream(UID)
    got, stamp = st.load_newest(KIND, UID, root=world.root)
    assert isinstance(got, dict) and got
    cols = {k for rows in got.values() for r in rows for k in r}
    assert not cols & set(AD.PRO_ITEMS)
    assert stamp["writer"] == "stim_optimizer" and stamp["provenance"] == []
    # the key and the payload carry the file's uid and content hash, never its name
    assert all("~" in k for k in got)


def test_the_implant_date_cut_is_applied_after_assembly(world, monkeypatch):
    start = pd.Timestamp("2026-01-04T00:00:00Z").timestamp()
    monkeypatch.setattr(AD._data_start, "data_start_s", lambda participant: start)
    AD._build_settings_stream(UID)
    world.files.append(_SF("f10", _session(16, 2.0, 2.0)))
    out = AD._build_settings_stream(UID)
    _same(out, _scratch_build(monkeypatch))
    assert pd.to_datetime(out["t"], utc=True).min() == pd.Timestamp(start, unit="s", tz="UTC")


def test_with_the_store_off_everything_is_parsed_every_time(world, monkeypatch):
    monkeypatch.setattr(st, "ENABLED", False)
    AD._build_settings_stream(UID)
    world.loaded.clear()
    AD._build_settings_stream(UID)
    assert sorted(world.loaded) == ["f1", "f2", "f3"]
    assert _entry_files(world.root) == []
