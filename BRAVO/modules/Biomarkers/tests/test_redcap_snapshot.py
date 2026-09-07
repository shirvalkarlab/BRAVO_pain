"""The pain-report snapshot: written after every fresh fetch, read by no page.

WHAT THESE TESTS HOLD. Decision 22 says the pain reports may not be served from a cache, and
`test_redcap_request_scope.py` proves a newly filed report reaches the next request. The snapshot
must not weaken that by one report. So:

  * every request still fetches, even when a snapshot of the identical table is on disk;
  * the same report set writes exactly once, and a second fetch leaves the directory byte-identical;
  * a newly filed report is returned fresh AND produces a second snapshot, with the first still on
    disk, because the point of the snapshot is that a result can name the table it used;
  * a report table handed to the request body is never snapshotted (it is the caller's data);
  * with the store turned off nothing is written and the reports are still returned;
  * the frame carries the key of its snapshot so a derived product can cite it.

No Django and no database, same stubbing as test_redcap_request_scope.py.

Run inside the container:
    python3 _agent_bridge/run_tests.py
"""
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest.mock as mock

import pandas as pd

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _import_service():
    for mod in ("Server", "Server.models", "modules.Database"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    for mod in ("modules.Biomarkers.pipeline", "modules.Biomarkers.adapter"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    import modules.Biomarkers.bravo_service as bs
    return bs


B = _import_service()
from modules.Biomarkers.routines import redcap_client as RC          # noqa: E402
from modules.CacheStore import store as st                            # noqa: E402

FIELD_MAP = {
    "pt": "RCS08",
    "instruments": ["daily_pain_survey"],
    "timestamp_label": "date_time_s1_daily",
    "metric_labels": {"nrs": "pain_nrs", "vas": "pain_vas"},
}
_ALL_COLUMNS = ["date_time_s1_daily", "pain_nrs", "pain_vas", "unrelated_one"]


def _export_frame(n_reports, columns=None, record_ids=("RCS08", "RCS09")):
    columns = list(columns or _ALL_COLUMNS)
    rows, index = [], []
    for rid in record_ids:
        for i in range(n_reports):
            index.append((rid, "visit_1", float(i + 1)))
            base = {"redcap_repeat_instrument": "daily_pain_survey",
                    "date_time_s1_daily": "2025-09-%02d 09:00" % (i + 1),
                    "pain_nrs": float(i % 9), "pain_vas": float((i % 9) * 10),
                    "unrelated_one": "x"}
            rows.append({c: base.get(c) for c in ["redcap_repeat_instrument"] + columns})
    df = pd.DataFrame(rows)
    df.index = pd.MultiIndex.from_tuples(index, names=["record_id", "redcap_event_name",
                                                       "redcap_repeat_instance"])
    return df


class _FakeRedcap:
    def __init__(self, n=4):
        self.n, self.calls = n, 0

    def pull(self, redcap_config=None, save=False, save_path=None, fields=None, records=None):
        self.calls += 1
        return _export_frame(self.n, columns=fields,
                             record_ids=tuple(records or ("RCS08", "RCS09")))


class _Bench:
    """A temporary store root for the biomarker module's shared-cache override, ledger off."""

    def __enter__(self):
        from modules.CacheStore import ledger
        self._dir = tempfile.mkdtemp(prefix="bravo_snapshot_test_")
        self._prev = (B._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED, st.ENABLED)
        B._SHARED_CACHE_DIR_OVERRIDE = self._dir
        ledger.ENABLED = False
        self._env = mock.patch.dict(os.environ, {"REDCAP_API_URL": "https://x/api/",
                                                 "REDCAP_API_TOKEN": "t"})
        self._env.start()
        return self._dir

    def __exit__(self, *exc):
        from modules.CacheStore import ledger
        self._env.stop()
        B._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED, st.ENABLED = self._prev
        shutil.rmtree(self._dir, ignore_errors=True)
        return False


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


REQ = {"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP}


def test_a_fresh_fetch_writes_one_snapshot_as_a_table_with_no_provenance():
    fake = _FakeRedcap(4)
    with _Bench() as root, mock.patch.object(RC, "pull_redcap", fake.pull):
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


def test_every_request_still_fetches_and_the_same_report_set_writes_only_once():
    """THE KEY DECIDES. Two requests, same reports: two fetches, one write, byte-identical dir."""
    fake = _FakeRedcap(4)
    with _Bench() as root, mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            B._load_pros(dict(REQ))
        before = _tree(root)
        with B.pro_request_scope():
            B._load_pros(dict(REQ))
        assert fake.calls == 2, "a snapshot on disk must never replace the fetch"
        assert _tree(root) == before, "the same report set was written twice"


def test_a_newly_filed_report_is_returned_fresh_and_the_earlier_snapshot_is_kept():
    fake = _FakeRedcap(4)
    with _Bench() as root, mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            first = B._load_pros(dict(REQ))
        fake.n = 5                                   # a patient files one more pain report
        with B.pro_request_scope():
            second = B._load_pros(dict(REQ))
        assert len(first) == 4 and len(second) == 5, \
            "a snapshot of four reports was served instead of the five now filed"
        files = _payloads(root)
        assert len(files) == 2, files
        assert first.attrs[B.PRO_STORE_KEY_ATTR] != second.attrs[B.PRO_STORE_KEY_ATTR]
        counts = sorted(len(pd.read_parquet(os.path.join(root, f))) for f in files)
        assert counts == [4, 5], "the earlier report table must survive so a result can cite it"


def test_a_report_table_in_the_request_body_is_not_snapshotted():
    rows = [{"date_time_s1_daily": "2025-09-01 09:00", "nrs": 3.0}]
    with _Bench() as root:
        with B.pro_request_scope():
            out = B._load_pros({"ParticipantId": "u", "ProcessedPRO": rows})
        assert len(out) == 1
        assert _payloads(root) == []
        assert B.PRO_STORE_KEY_ATTR not in out.attrs


def test_with_the_store_off_nothing_is_written_and_the_reports_still_come_back():
    fake = _FakeRedcap(4)
    with _Bench() as root, mock.patch.object(RC, "pull_redcap", fake.pull):
        st.ENABLED = False
        with B.pro_request_scope():
            df = B._load_pros(dict(REQ))
        assert len(df) == 4
        assert _payloads(root) == []


def test_the_remembered_copy_within_a_request_carries_the_same_key():
    fake = _FakeRedcap(4)
    with _Bench(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            a = B._load_pros(dict(REQ))
            b = B._load_pros(dict(REQ))
    assert fake.calls == 1
    assert a.attrs[B.PRO_STORE_KEY_ATTR] == b.attrs[B.PRO_STORE_KEY_ATTR]


def test_the_digest_changes_with_any_value_and_not_with_row_order_preserved_content():
    a = pd.DataFrame({"nrs": [1.0, 2.0], "vas": [10.0, 20.0]})
    b = pd.DataFrame({"nrs": [1.0, 2.0], "vas": [10.0, 21.0]})
    assert B._pro_table_digest(a) == B._pro_table_digest(a.copy())
    assert B._pro_table_digest(a) != B._pro_table_digest(b)
