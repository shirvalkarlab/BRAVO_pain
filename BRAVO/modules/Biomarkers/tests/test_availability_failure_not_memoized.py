"""Review B2 (2026-09-12): a FAILED availability build is not memoized as "no recordings".

`_build_availability` answers any exception with an empty payload. Until this fix that payload was
put into the endpoint's result memo under the request key like a real answer, so every later
request with the same key was handed "No Percept recordings decoded" without rebuilding -- for
hours on a participant who keeps rating, and until the worker restarted on one who does not. A
right-shaped empty answer, indistinguishable from "no data" (CLAUDE.md rule 11).

Pinned here on VALUES: the first response carries `failed == True` and an empty `records`; the
second response, with the identical request, carries the records the build then produced -- which
it can only do if the failure was not memoized. The endpoint is called for real; everything below
it (the participant, the pain table, the recording loaders, the build itself) is a stand-in, so
no database is needed. Plain asserts; the container runner has no pytest.
"""
import os
import sys

import pandas as pd

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402

UID = "availability-failure-test-participant"
_REAL_BUILD = bs._build_availability     # bound before any stub, so the catch-all below is the real one


class _Participant:
    uid = UID
    name = "stand-in"


class _Stubs:
    """Replace everything `availability_for_participant` reaches below itself; restore on exit."""

    def __init__(self, build_fn):
        self.build_fn = build_fn
        self.n_builds = 0

    def __enter__(self):
        self._saved = {n: getattr(bs, n) for n in (
            "_load_pros", "_resolve_biomarker_metric", "_recording_set_identity",
            "_availability_recordings_cached", "_derive_chan_order", "_recorded_powers",
            "_region_map", "_build_availability")}
        self._saved_find = bs.models.Participant.find
        bs.models.Participant.find = staticmethod(lambda **k: _Participant())
        pro = pd.DataFrame({"date_time_s1_daily": ["2025-07-21 18:00:00"], "nrs": [7.0],
                            "_pro_time_utc": pd.to_datetime(["2025-07-22 01:00:00"])})
        bs._load_pros = lambda request_data, participant=None: pro
        bs._resolve_biomarker_metric = lambda request_data, df: (df, "nrs", None)
        bs._recording_set_identity = lambda uid: (uid, 3, "abc")
        bs._availability_recordings_cached = lambda uid, recording_set=None: ([], [], [])
        bs._derive_chan_order = lambda td: []
        bs._recorded_powers = lambda pd_list, region_map=None: []
        bs._region_map = lambda participant, chans: {}

        def _build(*a, **k):
            self.n_builds += 1
            return self.build_fn(self.n_builds)
        bs._build_availability = _build
        bs._AVAILABILITY_RESULT_MEMO.clear()
        return self

    def __exit__(self, *exc):
        for n, v in self._saved.items():
            setattr(bs, n, v)
        bs.models.Participant.find = self._saved_find
        bs._AVAILABILITY_RESULT_MEMO.clear()
        return False


def _real_catch_all_payload(exc):
    """What `_build_availability`'s own catch-all returns: run the real function with a loader
    that raises, so the test pins the real failure payload rather than a hand-made one."""
    saved = bs._build_sensing_config_index     # called inside the build's own try block
    try:
        def _boom(recs):
            raise exc
        bs._build_sensing_config_index = _boom
        return _REAL_BUILD(UID, chronic_list=[], powerdomain_list=[], td_list=[],
                           pro_df=pd.DataFrame(), label_metric="nrs", region_map={}, psd_list=[])
    finally:
        bs._build_sensing_config_index = saved


def test_the_real_catch_all_marks_its_payload_as_failed():
    out = _real_catch_all_payload(RuntimeError("database connection dropped"))
    assert out["failed"] is True
    assert "database connection dropped" in out["failure"], out["failure"]
    assert out["records"] == []


def test_a_build_that_fails_once_is_rebuilt_on_the_next_identical_request():
    """First call: the failure payload, with the failure named. Second call, same request: the
    records the build produced -- so the failure was NOT held in the memo."""
    good = {"records": [{"channel": "ZERO_TWO_LEFT"}], "pain": {"metric": "nrs", "t": [], "y": []}}

    def build(n):
        if n == 1:
            return _real_catch_all_payload(ValueError("one malformed patient-event row"))
        return dict(good)

    req = {"ParticipantId": UID}
    with _Stubs(build) as st:
        first = bs.availability_for_participant(req)
        assert first["availability"]["failed"] is True
        assert first["availability"]["records"] == []
        assert "could not be built" in first["message"], first["message"]
        assert "one malformed patient-event row" in first["message"], first["message"]
        assert "not an empty record" in first["message"]
        second = bs.availability_for_participant(req)
        assert st.n_builds == 2, "the second call must rebuild, not serve the failed answer"
        assert second["availability"]["records"] == good["records"], second["availability"]
        assert not second["availability"].get("failed")
        assert second["message"] is None, second["message"]
        # And the GOOD answer is memoized: a third call performs no build.
        third = bs.availability_for_participant(req)
        assert st.n_builds == 2, st.n_builds
        assert third["availability"]["records"] == good["records"]


def test_a_genuinely_empty_record_still_says_upload_sessions_and_is_memoized():
    """The other branch is unchanged: no failure and no records is the empty-record message, and
    that answer is held like before."""
    empty = {"records": [], "pain": {"metric": "nrs", "t": [], "y": []}}
    with _Stubs(lambda n: dict(empty)) as st:
        first = bs.availability_for_participant({"ParticipantId": UID})
        assert "No Percept recordings decoded" in first["message"]
        assert not first["availability"].get("failed")
        bs.availability_for_participant({"ParticipantId": UID})
        assert st.n_builds == 1, st.n_builds


def test_the_memo_refuses_only_a_failed_result():
    key = ("availability_v2", "k")
    bs._AVAILABILITY_RESULT_MEMO.pop(key, None)
    got = bs._availability_result_cached(key, lambda: {"records": [], "failed": True, "failure": "x"})
    assert got["failed"] is True
    assert key not in bs._AVAILABILITY_RESULT_MEMO
    got = bs._availability_result_cached(key, lambda: {"records": [1]})
    assert got == {"records": [1]}
    assert bs._AVAILABILITY_RESULT_MEMO[key] == {"records": [1]}
    bs._AVAILABILITY_RESULT_MEMO.pop(key, None)


if __name__ == "__main__":
    test_the_real_catch_all_marks_its_payload_as_failed()
    test_a_build_that_fails_once_is_rebuilt_on_the_next_identical_request()
    test_a_genuinely_empty_record_still_says_upload_sessions_and_is_memoized()
    test_the_memo_refuses_only_a_failed_result()
    print("All availability-failure tests passed.")
