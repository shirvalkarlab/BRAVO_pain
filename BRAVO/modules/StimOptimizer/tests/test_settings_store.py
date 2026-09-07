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
