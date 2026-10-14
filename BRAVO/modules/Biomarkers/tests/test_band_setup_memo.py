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
    assert "BAND_SETUP_MEMO_ENV" in inspect.getsource(job._replay_process_init)
