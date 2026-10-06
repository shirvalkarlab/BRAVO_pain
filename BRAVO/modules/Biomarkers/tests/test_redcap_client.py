"""The pain reports from REDCap: the tidy table, the narrowed request, the within-request scope, the
snapshot written after each fresh fetch, and the kept project connection.

The point is not the speed. It is that NO PAIN REPORT CAN GO MISSING (decision 22: the pain reports
may not be served from a cache):

  * `test_new_report_appears_in_the_next_request_with_no_refresh...` files a brand new pain report
    between two requests and requires the second request to return it (the fake REDCap gains a row);
  * `test_the_scope_does_not_outlive_the_request...` requires the remembered answer to be dropped
    when the request ends, which is what makes the test above pass by construction;
  * `test_narrow_and_full_requests_give_the_same_reports` requires the narrowed request (fewer
    columns over the wire) to produce exactly the report table the full export produces.

The snapshot (written after every fresh fetch, read by no page) must not weaken that by one report:
every request still fetches; the same report set writes once (byte-identical directory); a newly
filed report is returned fresh and produces a second snapshot with the first kept; a report table in
the request body is never snapshotted; with the store off nothing is written; the frame carries the
key of its snapshot so a derived product can cite it.

The project connection is kept for up to an hour per process (the PI, 2026-10-04, decision 432):
its data dictionary and form-event map describe the project's design; the reports themselves are
still fetched on every call, so no answer can be a report short.

No Django and no database: `bravo_service` is imported with its server modules stubbed.

Merged here 2026-10-05: test_redcap_request_scope.py, test_redcap_snapshot.py,
test_redcap_project_kept.py, test_process_redcap.py (whose checks lived in a `main()` that no
runner called; now a test).
"""
import contextlib
import hashlib
import json
import math
import os
import pathlib
import shutil
import sys
import tempfile
import types
import unittest.mock as mock

import numpy as np
import pandas as pd

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _import_service():
    """Import `bravo_service` without Django, keeping the REAL `redcap_client`."""
    for mod in ("Server", "Server.models", "modules.Database"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    for mod in ("modules.Biomarkers.pipeline", "modules.Biomarkers.adapter"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    import modules.Biomarkers.bravo_service as bs
    return bs


B = _import_service()
from modules.Biomarkers.routines import redcap_client as RC  # noqa: E402
from modules.CacheStore import store as st                    # noqa: E402

FIELD_MAP = {
    "pt": "RCS08",
    "instruments": ["daily_pain_survey"],
    "timestamp_label": "date_time_s1_daily",
    "metric_labels": {
        "nrs": "pain_nrs",
        "vas": "pain_vas",
        # a list-valued entry: both components must be requested from REDCap
        "mpq_sum": ["mpq_a", "mpq_b"],
        # a repeat of an already-listed column: must not be requested twice
        "nrs_again": "pain_nrs",
    },
}
REQ = {"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP}

# Every column the full export carries, in the order PyCap hands them back. Only the ones named in
# FIELD_MAP are consumed; the rest stand in for the 613 columns the live project carries and the
# narrowed request does not ask for.
_ALL_COLUMNS = ["date_time_s1_daily", "pain_nrs", "pain_vas", "mpq_a", "mpq_b",
                "unrelated_one", "unrelated_two"]


def _export_frame(n_reports, columns=None, record_ids=("RCS08", "RCS09")):
    """A frame shaped like PyCap's `export_records(format_type='df')` answer."""
    columns = list(columns or _ALL_COLUMNS)
    rows, index = [], []
    for rid in record_ids:
        for i in range(n_reports):
            index.append((rid, "visit_1", float(i + 1)))
            base = {
                "redcap_repeat_instrument": "daily_pain_survey",
                "date_time_s1_daily": "2025-09-%02d 09:00" % (i + 1),
                "pain_nrs": float(i % 9),
                "pain_vas": float((i % 9) * 10),
                "mpq_a": float(i % 4),
                "mpq_b": float(i % 3),
                "unrelated_one": 999.0,
                "unrelated_two": 999.0,
            }
            rows.append({k: base[k] for k in ["redcap_repeat_instrument"] + columns})
    df = pd.DataFrame(rows)
    df.index = pd.MultiIndex.from_tuples(
        index, names=["record_id", "redcap_event_name", "redcap_repeat_instance"])
    return df


# ------------------------------------------------------------------ the tidy table (process_redcap)

def _raw_frame():
    rows = [
        # record_id, event, instrument, instance, ts, nrs, vas, mpq_a1, mpq_a2, other_field
        ("RCS08", "visit_1", "daily_pain_survey", 1, "2025-09-02 09:00", 8, 80, 5, 6, 999),
        ("RCS08", "visit_1", "daily_pain_survey", 2, "2025-09-01 09:00", 2, 20, 1, 1, 999),  # earlier -> sorts first
        ("RCS08", "visit_1", "daily_pain_survey", 3, "2025-09-03 09:00", np.nan, 50, np.nan, 2, 999),  # missing NRS
        ("RCS08", "visit_1", "other_instrument", 1, "2025-09-04 09:00", 1, 1, 1, 1, 1),  # wrong instrument -> dropped
        ("RCS09", "visit_1", "daily_pain_survey", 1, "2025-09-02 09:00", 9, 90, 7, 7, 7),  # other patient -> dropped
    ]
    cols = ["record_id", "redcap_event_name", "redcap_repeat_instrument", "redcap_repeat_instance",
            "date_time_s1_daily", "nrs", "vas", "mpq_item1_aff", "mpq_item2_aff", "unused"]
    df = pd.DataFrame(rows, columns=cols)
    return df.set_index(["record_id", "redcap_event_name", "redcap_repeat_instance"])


def test_process_redcap_keeps_one_patients_instrument_sums_list_scores_and_sorts_by_time():
    """A raw PyCap export -> the tidy pain-report table: filter, rename/sum, sort; a missing report
    stays NaN (never fabricated as 0)."""
    field_map = {"pt": "RCS08", "instruments": ["daily_pain_survey"],
                 "timestamp_label": "date_time_s1_daily",
                 "metric_labels": {"nrs": "nrs", "vas": "vas",
                                   "mpq_aff": ["mpq_item1_aff", "mpq_item2_aff"]}}
    out = RC.process_redcap(_raw_frame(), field_map)
    assert len(out) == 3, f"other instrument and other patient filtered out; got {len(out)} rows"
    ts = list(out["date_time_s1_daily"])
    assert ts == sorted(ts) and ts[0] == "2025-09-01 09:00", ts
    nrs = list(out["nrs"])
    assert nrs[0] == 2 and nrs[1] == 8 and math.isnan(nrs[2]), nrs
    # a list mapping is summed row-wise with min_count=1: present values summed, all missing -> NaN
    assert list(out["mpq_aff"]) == [2, 11, 2], list(out["mpq_aff"])
    assert set(out.columns) == {"nrs", "vas", "mpq_aff", "date_time_s1_daily"}, list(out.columns)


# ---------------------------------------------------------------- the field list we ask REDCap for

def test_field_list_covers_every_consumed_column_once_and_declines_an_unusable_field_map():
    fields, records = RC.redcap_fields_for_field_map(FIELD_MAP)
    assert fields == ["date_time_s1_daily", "pain_nrs", "pain_vas", "mpq_a", "mpq_b"], fields
    assert records == ["RCS08"], records
    # every column process_redcap will read is in the list
    consumed = {FIELD_MAP["timestamp_label"]}
    for v in FIELD_MAP["metric_labels"].values():
        consumed.update(v if isinstance(v, list) else [v])
    assert consumed <= set(fields)
    for unusable in (None, {}, {"timestamp_label": "t"}):
        assert RC.redcap_fields_for_field_map(unusable) == (None, None), unusable


def _fake_pycap(seen):
    """A stand-in `redcap` module that records the keyword arguments of each export request."""
    class Project:
        def __init__(self, url, token):
            pass

        def export_records(self, **kwargs):
            seen.append(kwargs)
            cols = kwargs.get("fields")
            return _export_frame(3, columns=cols,
                                 record_ids=tuple(kwargs.get("records") or ("RCS08", "RCS09")))
    mod = types.ModuleType("redcap")
    mod.Project = Project
    return mod


def _pull_seen(**kw):
    """One `pull_redcap` against a fresh fake PyCap; the kept project connection (decision 432) is
    forgotten first and after, so an earlier fake's connection is never reused."""
    seen = []
    RC.forget_projects()
    try:
        with mock.patch.dict(os.environ, {"REDCAP_API_URL": "https://x/api/",
                                          "REDCAP_API_TOKEN": "t"}), \
                mock.patch.dict(sys.modules, {"redcap": _fake_pycap(seen)}):
            RC.pull_redcap(**kw)
    finally:
        RC.forget_projects()
    return seen


def test_pull_sends_the_unchanged_export_request_and_a_field_list_asks_for_those_columns_only():
    seen = _pull_seen()
    assert len(seen) == 1
    assert "fields" not in seen[0] and "records" not in seen[0], seen[0]
    assert seen[0] == {"format_type": "df", "export_checkbox_labels": True,
                       "export_survey_fields": True}, seen[0]
    fields, records = RC.redcap_fields_for_field_map(FIELD_MAP)
    seen = _pull_seen(fields=fields, records=records)
    assert seen[0]["fields"] == fields
    assert seen[0]["records"] == ["RCS08"]


def test_narrow_and_full_requests_give_the_same_reports():
    """Fewer columns over the wire, identical pain-report table."""
    full = RC.process_redcap(_export_frame(5), FIELD_MAP)
    fields, records = RC.redcap_fields_for_field_map(FIELD_MAP)
    narrow = RC.process_redcap(_export_frame(5, columns=fields, record_ids=("RCS08",)), FIELD_MAP)
    assert len(full) == len(narrow) == 5
    assert list(full.columns) == list(narrow.columns)
    assert len(full.compare(narrow)) == 0


# ------------------------------------------- the within-request scope, freshness, and the snapshot

@contextlib.contextmanager
def _service_env():
    """REDCap credentials in the environment, AND the store pointed at a directory of its own
    (every fresh fetch writes a pain-report snapshot; without the override these tests wrote their
    fake tables into the server's real cache root, where the first live check found them). The
    ledger is off; the store's on/off switch is restored afterwards."""
    from modules.CacheStore import ledger
    tmp = tempfile.mkdtemp(prefix="bravo_scope_test_")
    prev = (B._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED, st.ENABLED)
    B._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED = tmp, False
    try:
        with mock.patch.dict(os.environ, {"REDCAP_API_URL": "https://x/api/",
                                          "REDCAP_API_TOKEN": "t"}):
            yield tmp
    finally:
        B._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED, st.ENABLED = prev
        shutil.rmtree(tmp, ignore_errors=True)


class _FakeRedcap:
    """A REDCap that starts with `n` filed pain reports and can gain more."""

    def __init__(self, n=4):
        self.n = n
        self.calls = 0

    def pull(self, redcap_config=None, save=False, save_path=None, fields=None, records=None):
        self.calls += 1
        return _export_frame(self.n, columns=fields,
                             record_ids=tuple(records or ("RCS08", "RCS09")))


def _tree(root):
    out = {}
    for dirpath, _dirs, names in os.walk(root):
        for n in sorted(names):
            p = os.path.join(dirpath, n)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def _payloads(root):
    return sorted(k for k in _tree(root) if not k.endswith(".meta.json"))


def test_a_fresh_fetch_writes_one_snapshot_as_a_table_with_no_provenance():
    fake = _FakeRedcap(4)
    with _service_env() as root, mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            df = B._load_pros(dict(REQ))
        files = _payloads(root)
        assert len(files) == 1, files
        assert files[0].startswith("redcap_reports/redcap_reports.v") \
            and files[0].endswith(".parquet")
        with open(os.path.join(root, files[0].replace(".parquet", ".meta.json"))) as fh:
            meta = json.load(fh)
        assert meta["writer"] == "biomarkers"
        assert meta["trigger"] == "fresh_fetch"
        assert meta["provenance"] == [], "the reports are a raw input and derive from nothing"
        assert meta["extra"]["n_reports"] == 4
        # the frame carries the key of the entry it was written as, so a derived product can cite it
        assert df.attrs[B.PRO_STORE_KEY_ATTR].startswith("redcap_reports/u/")
        # the stored table is the table the request got, value for value, including the UTC column
        stored = pd.read_parquet(os.path.join(root, files[0]))
        assert list(stored.columns) == list(df.columns)
        assert len(stored.compare(df)) == 0


def test_reads_inside_one_request_and_in_nested_scopes_fetch_once_and_carry_one_snapshot_key():
    fake = _FakeRedcap(4)
    with _service_env(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            first = B._load_pros(dict(REQ))
            second = B._load_pros(dict(REQ))
            with B.pro_request_scope():
                third = B._load_pros(dict(REQ))
    assert fake.calls == 1, fake.calls
    assert len(first) == len(second) == len(third) == 4
    assert len(first.compare(second)) == 0
    assert first.attrs[B.PRO_STORE_KEY_ATTR] == second.attrs[B.PRO_STORE_KEY_ATTR]


def test_the_scope_does_not_outlive_the_request_and_the_same_report_set_is_snapshotted_once():
    """THE KEY DECIDES. Two requests, same reports: two fetches, one write, byte-identical dir."""
    fake = _FakeRedcap(4)
    with _service_env() as root, mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            B._load_pros(dict(REQ))
        before = _tree(root)
        with B.pro_request_scope():
            B._load_pros(dict(REQ))
        assert fake.calls == 2, "a remembered answer or a snapshot on disk must never replace the fetch"
        assert B._PRO_REQUEST_CACHE.get() is None
        assert _tree(root) == before, "the same report set was written twice"


def test_new_report_appears_in_the_next_request_with_no_refresh_and_the_earlier_snapshot_is_kept():
    """THE FRESHNESS TEST. A pain report is filed between two requests; the second request must
    return it, with nobody clearing anything by hand; the earlier report table survives on disk so
    a result can cite it."""
    fake = _FakeRedcap(4)
    with _service_env() as root, mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            before = B._load_pros(dict(REQ))
        fake.n = 5  # a patient files one more pain report
        with B.pro_request_scope():
            after = B._load_pros(dict(REQ))
        # and with no scope open at all (the plain call path)
        plain = B._load_pros(dict(REQ))
        files = _payloads(root)
        counts = sorted(len(pd.read_parquet(os.path.join(root, f))) for f in files)
    assert len(before) == 4
    assert len(after) == 5, "a newly filed pain report did not reach the next request"
    assert len(plain) == 5
    assert fake.calls == 3
    assert before.attrs[B.PRO_STORE_KEY_ATTR] != after.attrs[B.PRO_STORE_KEY_ATTR]
    assert len(files) == 2 and counts == [4, 5], (files, counts)


def test_reads_with_different_field_maps_are_not_confused():
    fake = _FakeRedcap(4)
    other = dict(FIELD_MAP, metric_labels={"nrs": "pain_nrs"})
    with _service_env(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            a = B._load_pros({"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP})
            b = B._load_pros({"ParticipantId": "u", "RedcapFieldMap": other})
    assert fake.calls == 2, fake.calls
    assert "vas" in a.columns and "vas" not in b.columns


def test_a_remembered_answer_is_handed_out_as_its_own_copy():
    fake = _FakeRedcap(4)
    with _service_env(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            first = B._load_pros(dict(REQ))
            first["nrs"] = -1.0            # one panel scribbles on its copy
            first.drop(index=first.index[0], inplace=True)
            second = B._load_pros(dict(REQ))
    assert len(second) == 4
    assert not (second["nrs"] == -1.0).any()


def test_a_report_table_in_the_request_body_is_never_remembered_or_snapshotted():
    rows = [{"date_time_s1_daily": "2025-09-01 09:00", "nrs": 3.0}]
    with _service_env() as root:
        with B.pro_request_scope():
            out = B._load_pros({"ParticipantId": "u", "ProcessedPRO": rows})
            assert len(out) == 1
            assert B._PRO_REQUEST_CACHE.get() == {}
        assert _payloads(root) == []
        assert B.PRO_STORE_KEY_ATTR not in out.attrs


def test_with_the_store_off_nothing_is_written_and_the_reports_still_come_back():
    fake = _FakeRedcap(4)
    with _service_env() as root, mock.patch.object(RC, "pull_redcap", fake.pull):
        st.ENABLED = False
        with B.pro_request_scope():
            df = B._load_pros(dict(REQ))
        assert len(df) == 4
        assert _payloads(root) == []


def test_an_identical_report_table_has_the_same_digest():
    a = pd.DataFrame({"nrs": [1.0, 2.0], "vas": [10.0, 20.0]})
    assert B._pro_table_digest(a) == B._pro_table_digest(a.copy())


def test_the_digest_changes_with_any_value():
    a = pd.DataFrame({"nrs": [1.0, 2.0], "vas": [10.0, 20.0]})
    b = pd.DataFrame({"nrs": [1.0, 2.0], "vas": [10.0, 21.0]})
    assert B._pro_table_digest(a) != B._pro_table_digest(b)



def test_the_report_table_and_its_digest_do_not_depend_on_the_order_redcap_returns_rows():
    """Two reports filed at the same time with different values must come out in one order whatever
    order REDCap sends them in; otherwise the digest moves and every saved answer is rebuilt for
    nothing (the time sort alone left such ties in arrival order)."""
    field_map = {"pt": "RCS08", "instruments": ["daily_pain_survey"],
                 "timestamp_label": "date_time_s1_daily",
                 "metric_labels": {"nrs": "nrs", "vas": "vas"}}
    rows = [("RCS08", "v1", "daily_pain_survey", i, ts, n, v, np.nan, np.nan, 0) for i, (ts, n, v) in enumerate([
        ("2025-09-01 09:00", 2, 20), ("2025-09-02 09:00", 8, 80), ("2025-09-02 09:00", 3, 30),
        ("2025-09-02 09:00", 8, 80), ("2025-09-03 09:00", 5, 50)], 1)]
    cols = ["record_id", "redcap_event_name", "redcap_repeat_instrument", "redcap_repeat_instance",
            "date_time_s1_daily", "nrs", "vas", "mpq_item1_aff", "mpq_item2_aff", "unused"]
    outs = []
    for order in ([0, 1, 2, 3, 4], [4, 3, 2, 1, 0], [2, 0, 3, 4, 1]):
        raw = pd.DataFrame([rows[i] for i in order], columns=cols).set_index(
            ["record_id", "redcap_event_name", "redcap_repeat_instance"])
        outs.append(RC.process_redcap(raw, field_map))
    for o in outs[1:]:
        pd.testing.assert_frame_equal(o, outs[0])
        assert B._pro_table_digest(o) == B._pro_table_digest(outs[0])
    assert len(outs[0]) == 5                                   # identical reports both kept

# ------------------------------------------------------------------- the fall-back safety net

def _full_export_calls(pull, extra_env=None, request=None, patches=()):
    calls = []
    with _service_env(), mock.patch.dict(os.environ, extra_env or {}), \
            mock.patch.object(RC, "pull_redcap", lambda **kw: pull(calls, **kw)), \
            contextlib.ExitStack() as stack:
        for obj, name, value in patches:
            stack.enter_context(mock.patch.object(obj, name, value))
        out = B._load_pros(request or dict(REQ))
    return calls, out


def test_a_narrow_request_missing_the_timestamp_or_failing_falls_back_to_the_full_export():
    """A field map whose report timestamp is a survey-generated column cannot be requested by
    name. The narrowed answer then lacks it, and the full export must be used instead of the
    pain reports coming out short; a narrow request REDCap rejects falls back the same way."""
    def drops_timestamp(calls, redcap_config=None, save=False, save_path=None, fields=None, records=None):
        calls.append(fields)
        if fields:  # pretend REDCap dropped the timestamp column
            return _export_frame(4, columns=[f for f in fields if f != "date_time_s1_daily"],
                                 record_ids=("RCS08",))
        return _export_frame(4)

    def rejects(calls, redcap_config=None, save=False, save_path=None, fields=None, records=None):
        calls.append(fields)
        if fields:
            raise RuntimeError("REDCap rejected the field list")
        return _export_frame(4)

    for name, pull in (("missing timestamp", drops_timestamp), ("rejected", rejects)):
        calls, out = _full_export_calls(pull)
        assert len(calls) == 2 and calls[0] and calls[1] is None, (name, calls)
        assert len(out) == 4, name


def test_the_full_export_is_used_with_the_narrowing_switched_off_or_no_field_map():
    def pull(calls, redcap_config=None, save=False, save_path=None, fields=None, records=None):
        calls.append(fields)
        return _export_frame(4)

    calls, out = _full_export_calls(pull, extra_env={"BRAVO_REDCAP_NARROW_PULL": "0"})
    assert calls == [None] and len(out) == 4, ("switched off without a code change", calls)
    calls, out = _full_export_calls(pull, request={"ParticipantId": "u", "RedcapRecordId": "RCS08"},
                                    patches=[(B, "_load_pt_config", lambda *a, **k: None)])
    assert calls == [None], ("no field map", calls)
    assert len(out) == 4 and "pain_nrs" in out.columns


# --------------------------------------------------------- the project connection, kept an hour

class _FakeProject:
    made = []
    exports = []

    def __init__(self, url, key):
        _FakeProject.made.append((url, key))

    def export_records(self, **kw):
        _FakeProject.exports.append(kw)
        return pd.DataFrame({"record_id": [1], "n": [len(_FakeProject.exports)]})


def _with_fake_project(fn):
    real_mod = sys.modules.get("redcap")
    sys.modules["redcap"] = types.SimpleNamespace(Project=_FakeProject)
    real_env = {k: RC.os.environ.get(k) for k in ("REDCAP_API_URL", "REDCAP_API_TOKEN")}
    RC.os.environ["REDCAP_API_URL"], RC.os.environ["REDCAP_API_TOKEN"] = "u", "k"
    _FakeProject.made, _FakeProject.exports = [], []
    RC.forget_projects()
    try:
        fn()
    finally:
        RC.forget_projects()
        if real_mod is None:
            sys.modules.pop("redcap", None)
        else:
            sys.modules["redcap"] = real_mod
        for k, v in real_env.items():
            if v is None:
                RC.os.environ.pop(k, None)
            else:
                RC.os.environ[k] = v


def test_the_project_connection_is_kept_an_hour_per_credentials_and_the_reports_fetched_every_call():
    def within_the_hour():
        a = RC.pull_redcap(fields=["x"])
        b = RC.pull_redcap(fields=["x"])
        assert len(_FakeProject.made) == 1 and len(_FakeProject.exports) == 2
        assert int(a["n"].iloc[0]) == 1 and int(b["n"].iloc[0]) == 2

    def after_the_hour():
        clock = [1000.0]
        real = RC._now
        RC._now = lambda: clock[0]
        try:
            RC.pull_redcap()
            clock[0] += RC.PROJECT_KEEP_SECONDS + 1
            RC.pull_redcap()
        finally:
            RC._now = real
        assert len(_FakeProject.made) == 2, "after the hour a new connection is made"

    def other_credentials():
        RC.pull_redcap()
        RC.os.environ["REDCAP_API_TOKEN"] = "another"
        RC.pull_redcap()
        assert [k for _, k in _FakeProject.made] == ["k", "another"]

    for case in (within_the_hour, after_the_hour, other_credentials):
        _with_fake_project(case)
