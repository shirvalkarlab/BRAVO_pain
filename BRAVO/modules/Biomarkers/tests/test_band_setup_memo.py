"""The participant's band preparation, kept in a rebuild worker across bands (decision 474).

`_band_validation_setup` (pain table, matched pairs, stimulation series) is the same for every band
of a participant under one set of request settings. The rebuild's workers keep it between requests,
filed under the whole request minus the band's own fields plus the data it reads; the page's web
workers never keep it. Values: a second band reuses it; a changed setting, recording set or pain
table rebuilds it; a caller's change to its copy reaches no other caller; off by default.
Plain asserts: this file runs in the container suite."""
import contextlib
import os

from modules.Biomarkers import bravo_service as bs


@contextlib.contextmanager
def _memo(on=True):
    calls, ident = [], {"v": ("r1", "p1")}
    saved = (bs._band_validation_setup_build, bs._setup_data_identity, os.environ.get(bs.BAND_SETUP_MEMO_ENV))
    bs._band_validation_setup_build = lambda rd: calls.append(dict(rd)) or {"available": True, "pooled": {"n": [1, 2]}}
    bs._setup_data_identity = lambda rd: ident["v"]
    if on:
        os.environ[bs.BAND_SETUP_MEMO_ENV] = "1"
    else:
        os.environ.pop(bs.BAND_SETUP_MEMO_ENV, None)
    bs._BAND_SETUP_MEMO.clear()
    try:
        yield calls, ident
    finally:
        bs._band_validation_setup_build, bs._setup_data_identity = saved[0], saved[1]
        if saved[2] is None:
            os.environ.pop(bs.BAND_SETUP_MEMO_ENV, None)
        else:
            os.environ[bs.BAND_SETUP_MEMO_ENV] = saved[2]
        bs._BAND_SETUP_MEMO.clear()


def _rd(**over):
    rd = {"ParticipantId": "u1", "Channel": "ONE_THREE_LEFT", "CenterHz": 24.5, "BandWidthHz": 5,
          "LabelMetric": "nrs", "MatchToleranceMin": 15}
    rd.update(over)
    return rd


def test_a_second_band_reuses_the_preparation():
    with _memo() as (calls, _):
        bs._band_validation_setup(_rd())
        bs._band_validation_setup(_rd(Channel="ZERO_THREE_RIGHT", CenterHz=18.5, Cutpoint=0.4))
        assert len(calls) == 1


def test_a_changed_setting_recording_set_or_pain_table_rebuilds_it():
    with _memo() as (calls, ident):
        bs._band_validation_setup(_rd())
        bs._band_validation_setup(_rd(LabelMetric="vas"))
        assert len(calls) == 2
        ident["v"] = ("r2", "p1")
        bs._band_validation_setup(_rd())
        ident["v"] = ("r2", "p2")
        bs._band_validation_setup(_rd())
        assert len(calls) == 4


def test_a_callers_change_to_its_copy_reaches_no_other_caller():
    with _memo():
        first = bs._band_validation_setup(_rd())
        first["pooled"]["n"].append(3)
        assert bs._band_validation_setup(_rd(CenterHz=30.5))["pooled"]["n"] == [1, 2]


def test_off_by_default_so_the_web_workers_never_keep_it():
    with _memo(on=False) as (calls, _):
        bs._band_validation_setup(_rd())
        bs._band_validation_setup(_rd())
        assert len(calls) == 2


def test_the_rebuild_workers_switch_it_on():
    import inspect
    from modules.ClosedLoopDeployment import refresh_saved_answers as job
    assert 'os.environ[BAND_SETUP_MEMO_ENV] = "1"' in inspect.getsource(job._replay_process_init)
    # the rebuild names the switch itself, so its replay processes need not import this module
    assert job.BAND_SETUP_MEMO_ENV == bs.BAND_SETUP_MEMO_ENV


# THE CLOSED-LOOP REPORT'S RECORDING READS (decision 476): the recordings, the tile rows' digest and
# the recording signature are kept between requests in a rebuild process, under the recording set's
# identity; never in a web worker, and never anything else.

@contextlib.contextmanager
def _pass(on=True):
    ident = {"v": ("u1", 10, "d1")}
    saved = (bs._recording_set_identity, os.environ.get(bs.BAND_SETUP_MEMO_ENV))
    bs._recording_set_identity = lambda uid: ident["v"]
    if on:
        os.environ[bs.BAND_SETUP_MEMO_ENV] = "1"
    else:
        os.environ.pop(bs.BAND_SETUP_MEMO_ENV, None)
    bs._PASS_MEMO.clear()
    try:
        yield ident
    finally:
        bs._recording_set_identity = saved[0]
        if saved[1] is None:
            os.environ.pop(bs.BAND_SETUP_MEMO_ENV, None)
        else:
            os.environ[bs.BAND_SETUP_MEMO_ENV] = saved[1]
        bs._PASS_MEMO.clear()


def _read(key, calls):
    with bs.pro_request_scope():                                # one request
        return bs._request_memo(key, lambda: calls.append(key) or [{"n": len(calls)}])


def test_recording_reads_are_shared_between_requests_in_a_rebuild_process():
    calls = []
    with _pass():
        for _ in range(3):
            _read(("recordings", "u1", ("A",)), calls)
            _read(("tile_rows", "u1"), calls)
            _read(("cl_recording_set_signature", "u1"), calls)
        assert len(calls) == 3


def test_a_new_recording_set_is_read_again():
    calls = []
    with _pass() as ident:
        _read(("recordings", "u1", ("A",)), calls)
        ident["v"] = ("u1", 11, "d2")
        assert _read(("recordings", "u1", ("A",)), calls) == [{"n": 2}]
        assert len(calls) == 2


def test_web_workers_and_other_reads_are_never_shared_between_requests():
    calls = []
    with _pass(on=False):
        _read(("recordings", "u1", ("A",)), calls)
        _read(("recordings", "u1", ("A",)), calls)
        assert len(calls) == 2
    calls = []
    with _pass():
        _read(("something_else", "u1"), calls)
        _read(("something_else", "u1"), calls)
        assert len(calls) == 2


def test_the_shared_reads_are_bounded():
    calls = []
    with _pass():
        for i in range(bs._PASS_MEMO_MAX + 3):
            _read(("recordings", "u1", (str(i),)), calls)
        assert len(bs._PASS_MEMO) <= bs._PASS_MEMO_MAX


def test_a_rebuild_process_keeps_few_preparations():
    """Moved from the rebuild's own tests (decision 476), which no longer import this module."""
    assert bs._BAND_SETUP_MEMO_MAX <= 2


def test_identity_failure_never_reuses_another_requests_recordings():
    calls = []
    with _pass():
        _read(("recordings", "u1"), calls)
        def unavailable(uid):
            raise RuntimeError("synthetic unavailable identity")
        bs._recording_set_identity = unavailable
        assert _read(("recordings", "u1"), calls) == [{"n": 2}]
        assert _read(("recordings", "u1"), calls) == [{"n": 3}]


def test_empty_key_and_different_participants_do_not_share_a_recording_read():
    calls = []
    with _pass():
        _read((), calls)
        _read((), calls)
        _read(("recordings", "u1"), calls)
        _read(("recordings", "u2"), calls)
        assert len(calls) == 4
        _read(("recordings", "u1"), calls)
        assert len(calls) == 4
