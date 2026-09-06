"""Tests for the narrowed REDCap request and the within-request pain-report scope.

The point of these tests is not the speed. It is that NO PAIN REPORT CAN GO MISSING:

  * `test_new_report_appears_in_the_next_request_with_no_refresh` files a brand new pain report
    between two requests and requires the second request to return it. This is simulated for real
    (the fake REDCap gains a row), not argued about.
  * `test_scope_does_not_outlive_the_request` requires the remembered answer to be dropped when
    the request ends, which is what makes the test above pass by construction rather than by luck.
  * `test_narrow_and_full_requests_give_the_same_reports` requires the narrowed request (fewer
    columns over the wire) to produce exactly the report table the full export produces.

Run inside the container:

    docker compose exec -w /usr/src/BRAVO bravo-server python3 -W ignore -m pytest \
        modules/Biomarkers/tests/test_redcap_request_scope.py -q
"""
import os
import pathlib
import sys
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


# ---------------------------------------------------------------- the field list we ask REDCap for

def test_field_list_covers_every_consumed_column_once():
    fields, records = RC.redcap_fields_for_field_map(FIELD_MAP)
    assert fields == ["date_time_s1_daily", "pain_nrs", "pain_vas", "mpq_a", "mpq_b"], fields
    assert records == ["RCS08"], records
    # every column process_redcap will read is in the list
    consumed = {FIELD_MAP["timestamp_label"]}
    for v in FIELD_MAP["metric_labels"].values():
        consumed.update(v if isinstance(v, list) else [v])
    assert consumed <= set(fields)


def test_field_list_declines_an_unusable_field_map():
    assert RC.redcap_fields_for_field_map(None) == (None, None)
    assert RC.redcap_fields_for_field_map({}) == (None, None)
    assert RC.redcap_fields_for_field_map({"timestamp_label": "t"}) == (None, None)


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


def test_pull_without_arguments_sends_the_unchanged_export_request():
    seen = []
    with mock.patch.dict(os.environ, {"REDCAP_API_URL": "https://x/api/",
                                      "REDCAP_API_TOKEN": "t"}), \
            mock.patch.dict(sys.modules, {"redcap": _fake_pycap(seen)}):
        RC.pull_redcap()
    assert len(seen) == 1
    assert "fields" not in seen[0] and "records" not in seen[0], seen[0]
    assert seen[0] == {"format_type": "df", "export_checkbox_labels": True,
                       "export_survey_fields": True}, seen[0]


def test_pull_with_a_field_list_asks_for_those_columns_only():
    seen = []
    fields, records = RC.redcap_fields_for_field_map(FIELD_MAP)
    with mock.patch.dict(os.environ, {"REDCAP_API_URL": "https://x/api/",
                                      "REDCAP_API_TOKEN": "t"}), \
            mock.patch.dict(sys.modules, {"redcap": _fake_pycap(seen)}):
        RC.pull_redcap(fields=fields, records=records)
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


# ------------------------------------------------------- the within-request scope, and freshness

def _service_env():
    return mock.patch.dict(os.environ, {"REDCAP_API_URL": "https://x/api/",
                                        "REDCAP_API_TOKEN": "t"})


class _FakeRedcap:
    """A REDCap that starts with `n` filed pain reports and can gain more."""

    def __init__(self, n=4):
        self.n = n
        self.calls = 0

    def pull(self, redcap_config=None, save=False, save_path=None, fields=None, records=None):
        self.calls += 1
        return _export_frame(self.n, columns=fields,
                             record_ids=tuple(records or ("RCS08", "RCS09")))


def test_two_reads_in_one_request_fetch_once():
    fake = _FakeRedcap(4)
    req = {"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP}
    with _service_env(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            first = B._load_pros(dict(req))
            second = B._load_pros(dict(req))
    assert fake.calls == 1, fake.calls
    assert len(first) == len(second) == 4
    assert len(first.compare(second)) == 0


def test_scope_does_not_outlive_the_request():
    fake = _FakeRedcap(4)
    req = {"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP}
    with _service_env(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            B._load_pros(dict(req))
        with B.pro_request_scope():
            B._load_pros(dict(req))
    assert fake.calls == 2, fake.calls
    assert B._PRO_REQUEST_CACHE.get() is None


def test_new_report_appears_in_the_next_request_with_no_refresh():
    """THE FRESHNESS TEST. A pain report is filed between two requests; the second request must
    return it, with nobody clearing anything by hand."""
    fake = _FakeRedcap(4)
    req = {"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP}
    with _service_env(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            before = B._load_pros(dict(req))
        fake.n = 5  # a patient files one more pain report
        with B.pro_request_scope():
            after = B._load_pros(dict(req))
        # and with no scope open at all (the plain call path)
        plain = B._load_pros(dict(req))
    assert len(before) == 4
    assert len(after) == 5, "a newly filed pain report did not reach the next request"
    assert len(plain) == 5
    assert fake.calls == 3


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
    req = {"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP}
    with _service_env(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            first = B._load_pros(dict(req))
            first["nrs"] = -1.0            # one panel scribbles on its copy
            first.drop(index=first.index[0], inplace=True)
            second = B._load_pros(dict(req))
    assert len(second) == 4
    assert not (second["nrs"] == -1.0).any()


def test_nested_scopes_share_one_fetch():
    fake = _FakeRedcap(4)
    req = {"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP}
    with _service_env(), mock.patch.object(RC, "pull_redcap", fake.pull):
        with B.pro_request_scope():
            B._load_pros(dict(req))
            with B.pro_request_scope():
                B._load_pros(dict(req))
    assert fake.calls == 1, fake.calls


def test_inline_reports_in_the_request_body_are_never_remembered():
    rows = [{"date_time_s1_daily": "2025-09-01 09:00", "nrs": 3.0}]
    with B.pro_request_scope():
        out = B._load_pros({"ParticipantId": "u", "ProcessedPRO": rows})
        assert len(out) == 1
        assert B._PRO_REQUEST_CACHE.get() == {}


# ------------------------------------------------------------------- the fall-back safety net

def test_a_narrow_request_missing_the_timestamp_falls_back_to_the_full_export():
    """A field map whose report timestamp is a survey-generated column cannot be requested by
    name. The narrowed answer then lacks it, and the full export must be used instead of the
    pain reports coming out short."""
    calls = []

    def pull(redcap_config=None, save=False, save_path=None, fields=None, records=None):
        calls.append({"fields": fields, "records": records})
        if fields:  # pretend REDCap dropped the timestamp column
            return _export_frame(4, columns=[f for f in fields
                                             if f != "date_time_s1_daily"],
                                 record_ids=("RCS08",))
        return _export_frame(4)

    with _service_env(), mock.patch.object(RC, "pull_redcap", pull):
        out = B._load_pros({"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP})
    assert len(calls) == 2, calls
    assert calls[0]["fields"] and calls[1]["fields"] is None
    assert len(out) == 4


def test_a_failing_narrow_request_falls_back_to_the_full_export():
    calls = []

    def pull(redcap_config=None, save=False, save_path=None, fields=None, records=None):
        calls.append(fields)
        if fields:
            raise RuntimeError("REDCap rejected the field list")
        return _export_frame(4)

    with _service_env(), mock.patch.object(RC, "pull_redcap", pull):
        out = B._load_pros({"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP})
    assert len(calls) == 2 and calls[1] is None, calls
    assert len(out) == 4


def test_the_narrowing_can_be_switched_off_without_a_code_change():
    calls = []

    def pull(redcap_config=None, save=False, save_path=None, fields=None, records=None):
        calls.append(fields)
        return _export_frame(4)

    with _service_env(), mock.patch.dict(os.environ, {"BRAVO_REDCAP_NARROW_PULL": "0"}), \
            mock.patch.object(RC, "pull_redcap", pull):
        out = B._load_pros({"ParticipantId": "u", "RedcapFieldMap": FIELD_MAP})
    assert calls == [None], calls
    assert len(out) == 4


def test_no_field_map_still_uses_the_full_export():
    calls = []

    def pull(redcap_config=None, save=False, save_path=None, fields=None, records=None):
        calls.append(fields)
        return _export_frame(4)

    with _service_env(), mock.patch.object(RC, "pull_redcap", pull), \
            mock.patch.object(B, "_load_pt_config", lambda *a, **k: None):
        out = B._load_pros({"ParticipantId": "u", "RedcapRecordId": "RCS08"})
    assert calls == [None], calls
    assert len(out) == 4 and "pain_nrs" in out.columns


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception:
                fails += 1
                print("FAIL", name)
                traceback.print_exc()
    print("FAILURES=%d" % fails)
    sys.exit(1 if fails else 0)
