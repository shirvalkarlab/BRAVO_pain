"""Track A step 5: the settings stream and the therapy-and-pain matched table go through the store.

WHAT THESE TESTS HOLD.

  * The settings stream is parsed from the stored Percept files once per file set and read back
    from the store after that, and the frame that comes back is the frame that was built, value
    for value. A changed file set is a rebuild. An empty stream, or one with unreadable files, is
    handed back but never stored. With no database, or with the store off, nothing changes.
  * The matched table is stored only when both of its inputs can be named by a store key, its
    sidecar cites both, and a new pain-report key is a new entry: a stale rating can never be
    served from it.

Every test points the store at a directory of its own and turns the ledger off, so no test touches
the server's real cache root. The database and the file parser are stood in for, because the point
here is the wiring, not the parsing, which `test_adapter.py` covers.

Merged here 2026-10-05: test_settings_by_file.py (each under its own heading below).
"""
import json
import os
import shutil
import sys
import tempfile
import types

import pandas as pd
import pytest

import importlib

from StimOptimizer import adapter as AD
import hashlib

# THE SAME MODULE OBJECTS THE ADAPTER USES. The store can be imported under two names
# (`modules.CacheStore.store` in the container, `CacheStore.store` on the host), and once the
# CacheStore tests have put the BRAVO root on the path both spellings resolve in one process to
# two different module objects. A sandbox applied to the copy this file imported would leave the
# copy the adapter holds untouched, and the outcome would then depend on test order.
st = AD._cache_store
_ledger = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".ledger")

UID = "PARTICIPANT"


def _stream_frame(n_moments=3):
    rows = []
    for i, (amp, pw) in enumerate(((2.0, 60.0), (3.0, 60.0), (3.0, 90.0))[:n_moments]):
        t = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=6 * i)
        for hemi in ("Left", "Right"):
            rows.append({"t": t, "src": "history", "hemi": hemi, "amp": amp, "pw": pw,
                         "rate": 150.0, "upper": 5.0, "cathode": "1-2", "schema": "hemisphere"})
    return pd.DataFrame(rows)


def _empty_stream():
    return pd.DataFrame(columns=["t", "src", "hemi", "amp", "pw", "rate", "upper",
                                 "cathode", "schema"])


def _reports(n=6, key="redcap_reports/PARTICIPANT/abc"):
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    rows = [{"t_utc": t0 + pd.Timedelta(hours=h), "nrs": v, "vas": v * 10.0}
            for h, v in ((1.0, 7.0), (2.0, 6.0), (7.0, 4.0), (8.0, 5.0), (13.0, 3.0), (14.0, 2.0))]
    df = pd.DataFrame(rows[:n])
    if key:
        df.attrs[AD.STORE_KEY_ATTR] = key
    return df


class _Counting:
    def __init__(self, frame, unreadable=0):
        self.frame, self.unreadable, self.calls = frame, unreadable, 0

    def __call__(self, participant, *, source_types=None):
        self.calls += 1
        out = self.frame.copy()
        out.attrs[AD.UNREADABLE_ATTR] = self.unreadable
        return out


@pytest.fixture
def sandbox(monkeypatch):
    """A store root of this test's own, the ledger off, and a fixed file-set signature."""
    root = tempfile.mkdtemp(prefix="bravo_settings_store_")
    monkeypatch.setattr(AD, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(_ledger, "ENABLED", False)
    monkeypatch.setattr(st, "ENABLED", True)
    monkeypatch.setattr(AD, "source_file_signature",
                        lambda participant, source_types=None: ("therapy_settings", "v", UID,
                                                                tuple(source_types or ()), 3, "d1"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def fake_biomarkers(monkeypatch):
    bravo_service = types.ModuleType("modules.Biomarkers.bravo_service")
    bravo_service.reports = _reports()
    bravo_service._load_pros = lambda request_data, participant: bravo_service.reports
    bravo_service._pro_times_utc_series = lambda df: df["t_utc"]
    pkg_biomarkers = types.ModuleType("modules.Biomarkers")
    pkg_biomarkers.bravo_service = bravo_service
    pkg_modules = types.ModuleType("modules")
    pkg_modules.Biomarkers = pkg_biomarkers
    monkeypatch.setitem(sys.modules, "modules", pkg_modules)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers", pkg_biomarkers)
    monkeypatch.setitem(sys.modules, "modules.Biomarkers.bravo_service", bravo_service)
    return bravo_service


def _payloads(root, kind):
    d = os.path.join(root, kind)
    return sorted(f for f in os.listdir(d)) if os.path.isdir(d) else []


def _sidecar(root, kind):
    d = os.path.join(root, kind)
    metas = [f for f in os.listdir(d) if f.endswith(".meta.json")]
    assert len(metas) == 1, metas
    with open(os.path.join(d, metas[0])) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------------------------
# the settings stream
# ---------------------------------------------------------------------------------------------

def test_the_stream_is_parsed_once_and_read_back_identical(sandbox, monkeypatch):
    builder = _Counting(_stream_frame())
    monkeypatch.setattr(AD, "_build_settings_stream", builder)
    first = AD.settings_stream(UID)
    second = AD.settings_stream(UID)
    assert builder.calls == 1, "the second call parsed the files again"
    pd.testing.assert_frame_equal(first, second)
    assert first.attrs[AD.STORE_KEY_ATTR] == second.attrs[AD.STORE_KEY_ATTR]
    assert first.attrs[AD.STORE_KEY_ATTR].startswith("therapy_settings/PARTICIPANT/")
    files = _payloads(sandbox, "therapy_settings")
    assert [f for f in files if f.endswith(".parquet")], files
    meta = _sidecar(sandbox, "therapy_settings")
    assert meta["writer"] == "stim_optimizer" and meta["provenance"] == []
    assert meta["n_recordings"] == 3
    # the timezone survives the round trip: this is why the table is Parquet. The resolution is
    # not asserted, because pandas 2 and 3 default to different ones and the equality above
    # already requires the round trip to keep whichever the builder used.
    assert isinstance(second["t"].dtype, pd.DatetimeTZDtype)
    assert str(second["t"].dt.tz) == "UTC"


def test_a_changed_file_set_rebuilds(sandbox, monkeypatch):
    builder = _Counting(_stream_frame())
    monkeypatch.setattr(AD, "_build_settings_stream", builder)
    AD.settings_stream(UID)
    monkeypatch.setattr(AD, "source_file_signature",
                        lambda participant, source_types=None: ("therapy_settings", "v", UID,
                                                                (), 4, "d2"))
    AD.settings_stream(UID)
    assert builder.calls == 2


def test_an_empty_stream_is_returned_but_never_stored(sandbox, monkeypatch):
    builder = _Counting(_empty_stream())
    monkeypatch.setattr(AD, "_build_settings_stream", builder)
    out = AD.settings_stream(UID)
    AD.settings_stream(UID)
    assert out.empty and list(out.columns) == list(_empty_stream().columns)
    assert builder.calls == 2
    assert _payloads(sandbox, "therapy_settings") == []
    assert AD.STORE_KEY_ATTR not in out.attrs


def test_a_stream_with_unreadable_files_is_returned_but_never_stored(sandbox, monkeypatch):
    """The file set that keys the stream has not changed, so a stored copy would carry the gap
    until the next upload. Hand it back, do not remember it."""
    builder = _Counting(_stream_frame(), unreadable=2)
    monkeypatch.setattr(AD, "_build_settings_stream", builder)
    out = AD.settings_stream(UID)
    AD.settings_stream(UID)
    assert len(out) == 6 and builder.calls == 2
    assert _payloads(sandbox, "therapy_settings") == []


def test_with_the_store_off_every_call_parses_and_nothing_is_written(sandbox, monkeypatch):
    builder = _Counting(_stream_frame())
    monkeypatch.setattr(AD, "_build_settings_stream", builder)
    monkeypatch.setattr(st, "ENABLED", False)
    a = AD.settings_stream(UID)
    b = AD.settings_stream(UID)
    assert builder.calls == 2
    pd.testing.assert_frame_equal(a, b)
    assert _payloads(sandbox, "therapy_settings") == []


def test_with_no_database_the_stream_is_built_plainly(sandbox, monkeypatch):
    builder = _Counting(_stream_frame())
    monkeypatch.setattr(AD, "_build_settings_stream", builder)

    def no_db(participant, source_types=None):
        raise RuntimeError("no database here")
    monkeypatch.setattr(AD, "source_file_signature", no_db)
    out = AD.settings_stream(UID)
    assert len(out) == 6 and builder.calls == 1
    assert _payloads(sandbox, "therapy_settings") == []


def test_the_signature_never_carries_a_file_name(monkeypatch):
    """The export file names on this platform can carry a patient's name."""
    class _SF:
        def __init__(self, uid, hashed, type_, name):
            self.uid, self.hashed, self.type, self.name = uid, hashed, type_, name

    class _Q:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, owner=None):
            return self.rows

    rows = [_SF("u1", "h1", "MedtronicJSON", "Patient Real Name - report.json"),
            _SF("u2", "h2", "DefaultType", "x"), _SF("u3", "h3", "Other", "y")]
    models = types.ModuleType("Server.models")
    models.SourceFile = types.SimpleNamespace(objects=_Q(rows))
    pkg = types.ModuleType("Server")
    pkg.models = models
    monkeypatch.setitem(sys.modules, "Server", pkg)
    monkeypatch.setitem(sys.modules, "Server.models", models)
    sig = AD.source_file_signature(UID)
    assert sig[4] == 2, "only the two session-report types count"
    assert "Real Name" not in repr(sig)
    # renaming a file changes nothing; replacing its content changes the digest
    rows[0].name = "renamed"
    assert AD.source_file_signature(UID) == sig
    rows[0].hashed = "h1-changed"
    assert AD.source_file_signature(UID) != sig


# ---------------------------------------------------------------------------------------------
# the matched table
# ---------------------------------------------------------------------------------------------

def _stream_with_key():
    s = _stream_frame()
    s.attrs[AD.STORE_KEY_ATTR] = "therapy_settings/PARTICIPANT/k1"
    return s


def test_the_matched_table_is_stored_with_both_inputs_in_its_provenance(sandbox, fake_biomarkers,
                                                                        monkeypatch):
    calls = []
    real = AD.attach_pros

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(AD, "attach_pros", counting)
    first = AD.build_design_matrix(UID, stream=_stream_with_key())
    second = AD.build_design_matrix(UID, stream=_stream_with_key())
    assert len(calls) == 1, "the matched table was rebuilt although its key matched"
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 3
    assert first.attrs[AD.STORE_KEY_ATTR].startswith("therapy_pain_matched/PARTICIPANT/")
    meta = _sidecar(sandbox, "therapy_pain_matched")
    assert meta["writer"] == "stim_optimizer"
    keys = {c["key"] for c in meta["provenance"]}
    assert keys == {"therapy_settings/PARTICIPANT/k1", "redcap_reports/PARTICIPANT/abc"}
    kinds = {c["kind"] for c in meta["provenance"]}
    assert kinds == {"therapy_settings", "redcap_reports"}


def test_a_newly_filed_report_is_a_new_key_so_a_stale_rating_is_never_served(sandbox,
                                                                              fake_biomarkers):
    before = AD.build_design_matrix(UID, stream=_stream_with_key())
    fake_biomarkers.reports = _reports(key="redcap_reports/PARTICIPANT/def")
    fake_biomarkers.reports.loc[0, "nrs"] = 9.0                # the new report set differs
    after = AD.build_design_matrix(UID, stream=_stream_with_key())
    assert before.attrs[AD.STORE_KEY_ATTR] != after.attrs[AD.STORE_KEY_ATTR]
    assert float(after.loc[0, "nrs"]) != float(before.loc[0, "nrs"])
    parquet = [f for f in _payloads(sandbox, "therapy_pain_matched") if f.endswith(".parquet")]
    assert len(parquet) == 1, "the older matched table is swept, as every non-history kind is"


def test_without_a_report_key_the_table_is_computed_but_not_stored(sandbox, fake_biomarkers):
    fake_biomarkers.reports = _reports(key=None)
    out = AD.build_design_matrix(UID, stream=_stream_with_key())
    assert len(out) == 3
    assert AD.STORE_KEY_ATTR not in out.attrs
    assert _payloads(sandbox, "therapy_pain_matched") == []


def test_without_a_settings_key_the_table_is_computed_but_not_stored(sandbox, fake_biomarkers):
    out = AD.build_design_matrix(UID, stream=_stream_frame())
    assert len(out) == 3
    assert _payloads(sandbox, "therapy_pain_matched") == []


def test_the_wash_in_and_the_items_are_part_of_the_key(sandbox, fake_biomarkers):
    a = AD.build_design_matrix(UID, stream=_stream_with_key(), washin_min=1.0)
    b = AD.build_design_matrix(UID, stream=_stream_with_key(), washin_min=30.0)
    assert a.attrs[AD.STORE_KEY_ATTR] != b.attrs[AD.STORE_KEY_ATTR]


# ---------------------------------------------------------------------------------------------
# the real parser's unreadable-file path, and the refusal propagating out of the matched table
# ---------------------------------------------------------------------------------------------

def test_the_real_parser_counts_an_unreadable_file_and_the_stream_is_then_not_stored(sandbox,
                                                                                    monkeypatch):
    """One stored file parses, one raises inside the loader: the stream carries the readable
    file's rows and an unreadable count of one, and `settings_stream` hands it back unstored."""
    import json as _json

    class _SF:
        def __init__(self, uid, ok):
            self.uid, self.type, self.ok = uid, "MedtronicJSON", ok

    good = {"SessionDate": "2026-01-01T00:00:00Z",
            "Groups": {"Final": [{"ActiveGroup": True, "ProgramSettings": {
                "RateInHertz": 150.0,
                "LeftHemisphere": {"Programs": [{"AmplitudeInMilliAmps": 2.0,
                                                "PulseWidthInMicroSecond": 60.0,
                                                "ElectrodeState": []}]}}}]},
            "GroupHistory": []}
    rows = [_SF("a", True), _SF("b", False)]

    class _Q:
        def filter(self, owner=None):
            return rows
    models = types.ModuleType("Server.models")
    models.SourceFile = types.SimpleNamespace(objects=_Q())
    server = types.ModuleType("Server"); server.models = models
    curator = types.ModuleType("modules.DataCurator")

    def load(sf):
        if not sf.ok:
            raise OSError("cannot decrypt")
        return _json.dumps(good)
    curator.loadCacheFile = load
    # the converting loader and its anchor tables (2026-09-26); these fake exports carry no device clock
    curator.loadPerceptJSON = lambda sf, table=None: _json.loads(load(sf))
    curator.clock_anchor_tables = lambda owner: {}
    modules_pkg = sys.modules.get("modules") or types.ModuleType("modules")
    modules_pkg.DataCurator = curator
    monkeypatch.setitem(sys.modules, "Server", server)
    monkeypatch.setitem(sys.modules, "Server.models", models)
    monkeypatch.setitem(sys.modules, "modules", modules_pkg)
    monkeypatch.setitem(sys.modules, "modules.DataCurator", curator)

    out = AD._build_settings_stream(UID)
    assert out.attrs[AD.UNREADABLE_ATTR] == 1
    assert len(out) == 1 and out.loc[0, "hemi"] == "Left" and out.loc[0, "amp"] == 2.0

    stream = AD.settings_stream(UID)               # through the store-backed entry point
    assert len(stream) == 1
    assert AD.STORE_KEY_ATTR not in stream.attrs
    assert _payloads(sandbox, "therapy_settings") == []


def test_a_tampered_matched_table_that_derives_from_the_ladder_is_refused_and_the_refusal_propagates(
        sandbox, fake_biomarkers):
    """The matched table's real chain is raw, so the refusal cannot fire on it honestly. If a
    sidecar were edited to make the table derive from the ladder Stim Optimizer chose, the
    store must refuse it to Stim Optimizer, and `build_design_matrix` lets that refusal out
    rather than turning it into a silent recompute — a refusal is a decision, not a miss."""
    prov = importlib.import_module(st.__name__.rsplit('.', 1)[0] + '.provenance')
    first = AD.build_design_matrix(UID, stream=_stream_with_key())
    kind, uid, _h = first.attrs[AD.STORE_KEY_ATTR].split("/")
    d = os.path.join(sandbox, kind)
    meta_path = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".meta.json")][0]
    with open(meta_path) as fh:
        meta = json.load(fh)
    meta["provenance"].append({"key": "exploration_ladder/PARTICIPANT/x",
                               "kind": "exploration_ladder", "writer": "stim_optimizer"})
    with open(meta_path, "w") as fh:
        json.dump(meta, fh)
    with pytest.raises(prov.SelfDerivedProduct):
        AD.build_design_matrix(UID, stream=_stream_with_key())


# ================================================================================================
# From test_settings_by_file.py (merged here 2026-10-05).
# The per-file settings history (the PI's yes of 2026-09-25, answer 10 of the revised plan).
#
# The settings stream is built by decrypting and parsing every stored Percept session file. Before
# this change every new file meant parsing all of them again. Now the rows each file contributed are
# kept in the one store, filed under the identity of the file set, and a rebuild parses only the files
# it has not seen, reusing the rows of every file whose uid and content hash it has seen.
#
# WHAT THESE TESTS HOLD.
#
#   * A new file is the only file parsed, and the frame is the frame a from-scratch build gives,
#     value for value and attribute for attribute.
#   * A file whose content hash changed is parsed again; a changed parsing rule parses everything.
#   * An unreadable file is never saved as "no rows": nothing is written, and the next build tries it
#     again. A file that parses to zero rows is remembered as zero rows.
#   * A half-written or unreadable saved entry is not trusted: the build parses everything.
#   * The same file set writes nothing (the key decides); the kind is raw and carries no pain column.
#   * The implant-date cut is applied after the rows are assembled, exactly as before.
#
# The database and the file loader are stood in for; every test has a store root of its own and the
# ledger off, so no test reaches the server's real cache root.
# ================================================================================================

_prov = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".provenance")

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
    # the converting loader and its anchor tables (2026-09-26); these fake exports carry no device clock
    curator.loadPerceptJSON = lambda sf, table=None: __import__('json').loads(w.load(sf))
    curator.clock_anchor_tables = lambda owner: {}
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
