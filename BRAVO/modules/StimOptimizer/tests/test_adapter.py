"""Does handing in an already-built settings stream give the same answer as letting it be built?

WHY THESE TESTS EXIST. Reading, decrypting and parsing a participant's stored Percept files is the
most expensive thing this module does. On participant RCS08 it takes about 34 seconds for 1,136
files. Two functions here each needed that same frame and each built its own copy, so the closed-loop
deployment page paid for it twice on a genuinely cold build. Both functions now take an optional
``stream`` argument so a caller that wants both can build the frame once and hand it to both.

That optimisation is only worth having if it cannot change an answer. A page that got faster while
quietly reporting a different estimate would be far worse than a page that stayed slow. So the tests
below check three separate things. First, that passing a stream gives a result identical to not
passing one. Second, that passing None reproduces the old behaviour exactly, which is what every
caller written before this argument existed relies on. Third, that the two functions really do build
that frame the same way when left to themselves, because if one of them built it with different
arguments then a single shared frame would silently change what that function saw.

There is also a check that a frame missing a column raises. This codebase has already been bitten
once by a place that named columns which were not on the real frame and then carried on as though
everything were fine, producing a wrong answer with no error anywhere. A frame handed in here is
checked, and a missing column stops the call.
"""
import inspect
import sys
import types

import numpy as np
import pandas as pd
import pytest

from StimOptimizer import adapter as AD


# ---------------------------------------------------------------------------------------------
# fixtures in the real shapes
# ---------------------------------------------------------------------------------------------
def _stream_frame():
    """A settings stream in exactly the columns ``settings_stream`` returns.

    Three moments in time, both hemispheres at each, with the delivered current rising at the second
    moment and the pulse width rising at the third. That gives three exposure epochs rather than one,
    so a test can tell an answer built from this frame apart from an empty answer.
    """
    rows = []
    for hours, amp, pw in ((0.0, 2.0, 60.0), (6.0, 3.0, 60.0), (12.0, 3.0, 90.0)):
        t = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=hours)
        for hemi in ("Left", "Right"):
            rows.append({"t": t, "src": "history", "hemi": hemi, "amp": amp, "pw": pw,
                         "rate": 150.0, "upper": 5.0, "cathode": "1-2", "schema": "hemisphere"})
    return pd.DataFrame(rows)


def _empty_stream_frame():
    """Zero rows but the full set of column names, which is what a participant with no readable
    Percept files gets back from ``settings_stream``."""
    return pd.DataFrame(columns=["t", "src", "hemi", "amp", "pw", "rate", "upper",
                                 "cathode", "schema"])


def _pain_reports():
    """Pain ratings placed inside the epochs the stream above produces, in the columns the real
    loader hands over. Two ratings per epoch so the within-epoch scatter is defined."""
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    rows = []
    for hours, nrs in ((1.0, 7.0), (2.0, 6.0), (7.0, 4.0), (8.0, 5.0), (13.0, 3.0), (14.0, 2.0)):
        rows.append({"t_utc": t0 + pd.Timedelta(hours=hours), "nrs": nrs, "vas": nrs * 10.0})
    return pd.DataFrame(rows)


class _CountingStreamBuilder:
    """Stands in for ``settings_stream`` and remembers every call made to it.

    Counting the calls is the only way to show that the duplicate parse is gone, because the frame
    that comes back is identical either way. Remembering the arguments is how the test checks that
    the two functions ask for the same frame.
    """

    def __init__(self, frame):
        self.frame = frame
        self.calls = []

    def __call__(self, participant, **kwargs):
        self.calls.append((participant, dict(kwargs)))
        return self.frame

    @property
    def n_calls(self):
        return len(self.calls)


@pytest.fixture
def fake_biomarkers(monkeypatch):
    """Put a stand-in Biomarkers service where the two functions look for it.

    Both functions reach for ``modules.Biomarkers.bravo_service`` from inside the function body. The
    test suite runs with BRAVO/modules on the path, where the top-level name is ``Biomarkers`` and
    there is no ``modules`` package at all, so that import cannot succeed here and there is no
    database behind it either. This fixture installs a small stand-in under the name the functions
    use, holding just the three things they call: the assembled spectra lookup, the pain-report
    loader, and the timestamp normaliser.

    Returns the stand-in module so a test can change what it hands back.
    """
    reports = _pain_reports()

    bravo_service = types.ModuleType("modules.Biomarkers.bravo_service")
    bravo_service.psd_matrix = {}
    bravo_service.reports = reports
    bravo_service._cached_psd_matrix = lambda uid, force_refresh=None: bravo_service.psd_matrix
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


# ---------------------------------------------------------------------------------------------
# the optional argument itself
# ---------------------------------------------------------------------------------------------
def test_passing_no_stream_reads_the_files_exactly_once(monkeypatch):
    """Leaving the argument as None must do exactly what the code did before it existed: build the
    frame from the participant's stored files, with no extra arguments."""
    builder = _CountingStreamBuilder(_stream_frame())
    monkeypatch.setattr(AD, "settings_stream", builder)
    got = AD._use_stream_or_build_one("PARTICIPANT", None)
    assert builder.n_calls == 1
    assert builder.calls[0] == ("PARTICIPANT", {})
    assert got is builder.frame


def test_passing_a_stream_does_not_read_the_files(monkeypatch):
    """The whole point of the argument. Hand in a frame and nothing gets read."""
    builder = _CountingStreamBuilder(_stream_frame())
    monkeypatch.setattr(AD, "settings_stream", builder)
    mine = _stream_frame()
    got = AD._use_stream_or_build_one("PARTICIPANT", mine)
    assert builder.n_calls == 0
    assert got is mine


def test_an_empty_stream_is_accepted(monkeypatch):
    """A participant with no readable Percept files gets zero rows with the full column names, and
    that is a legitimate answer rather than a mistake, so it must not raise."""
    builder = _CountingStreamBuilder(_stream_frame())
    monkeypatch.setattr(AD, "settings_stream", builder)
    empty = _empty_stream_frame()
    got = AD._use_stream_or_build_one("PARTICIPANT", empty)
    assert builder.n_calls == 0
    assert got is empty
    assert len(got) == 0


def test_a_stream_missing_a_column_raises():
    """The trap this project has already fallen into once. A frame that does not carry a column the
    settings stream is defined to carry must stop the call and name what is missing, rather than
    being accepted and producing an answer built on nothing.
    """
    bad = _stream_frame().drop(columns=["rate", "cathode"])
    with pytest.raises(KeyError) as e:
        AD._use_stream_or_build_one("PARTICIPANT", bad)
    msg = str(e.value)
    assert "rate" in msg and "cathode" in msg


def test_something_that_is_not_a_frame_raises():
    for bad in ({"t": [1]}, [1, 2, 3], "a stream", 7):
        with pytest.raises(TypeError):
            AD._use_stream_or_build_one("PARTICIPANT", bad)


def test_both_functions_take_the_argument_and_default_it_to_none():
    """An existing caller passing only the arguments it always passed must keep working, which means
    the new argument has to be optional and has to be keyword-only so no positional call shifts."""
    for fn in (AD.evidence_inputs, AD.build_design_matrix):
        p = inspect.signature(fn).parameters["stream"]
        assert p.default is None, f"{fn.__name__} must default stream to None"
        assert p.kind is inspect.Parameter.KEYWORD_ONLY, f"{fn.__name__} stream must be keyword-only"


# ---------------------------------------------------------------------------------------------
# same answer either way
# ---------------------------------------------------------------------------------------------
def test_design_matrix_is_identical_whether_or_not_a_stream_is_passed(monkeypatch,
                                                                     fake_biomarkers):
    """The claim that matters. Passing the frame in and letting it be built must produce the same
    numbers, column for column and row for row."""
    builder = _CountingStreamBuilder(_stream_frame())
    monkeypatch.setattr(AD, "settings_stream", builder)

    built_inside = AD.build_design_matrix("PARTICIPANT")
    assert builder.n_calls == 1
    handed_in = AD.build_design_matrix("PARTICIPANT", stream=_stream_frame())
    assert builder.n_calls == 1, "passing a stream must not read the files again"

    assert len(built_inside) > 0, "the fixture should produce a non-empty design matrix"
    pd.testing.assert_frame_equal(built_inside, handed_in)


def test_evidence_inputs_epochs_are_identical_whether_or_not_a_stream_is_passed(monkeypatch,
                                                                               fake_biomarkers):
    builder = _CountingStreamBuilder(_stream_frame())
    monkeypatch.setattr(AD, "settings_stream", builder)

    psd_inside, ep_inside = AD.evidence_inputs("PARTICIPANT")
    assert builder.n_calls == 1
    psd_handed, ep_handed = AD.evidence_inputs("PARTICIPANT", stream=_stream_frame())
    assert builder.n_calls == 1, "passing a stream must not read the files again"

    assert len(ep_inside) == 3, f"expected three exposure epochs, got {len(ep_inside)}"
    pd.testing.assert_frame_equal(ep_inside, ep_handed)
    # No assembled spectra in the stand-in, so both must report that the same way.
    assert psd_inside is None and psd_handed is None


def test_the_two_functions_ask_for_the_same_frame(monkeypatch, fake_biomarkers):
    """Requirement that makes sharing one frame safe at all.

    If one function built the settings stream with different arguments from the other, then handing
    both the same object would silently change what one of them saw. This asks each of them to build
    its own and compares the calls they made. They must be the same call.
    """
    builder = _CountingStreamBuilder(_stream_frame())
    monkeypatch.setattr(AD, "settings_stream", builder)

    AD.evidence_inputs("PARTICIPANT")
    AD.build_design_matrix("PARTICIPANT")
    assert builder.n_calls == 2
    assert builder.calls[0] == builder.calls[1], (
        "the two functions build the settings stream with different arguments, so one shared frame "
        f"would not be what both would have built: {builder.calls}")


def test_neither_function_alters_the_frame_it_was_given(monkeypatch, fake_biomarkers):
    """Sharing one object is only safe if neither function writes to it. Compare the frame before
    and after both calls."""
    shared = _stream_frame()
    before = shared.copy(deep=True)
    monkeypatch.setattr(AD, "settings_stream",
                        _CountingStreamBuilder(pd.DataFrame(columns=shared.columns)))

    AD.evidence_inputs("PARTICIPANT", stream=shared)
    AD.build_design_matrix("PARTICIPANT", stream=shared)
    pd.testing.assert_frame_equal(shared, before)


def test_an_empty_stream_gives_an_empty_design_matrix(monkeypatch, fake_biomarkers):
    """A participant with no readable Percept files must come back with nothing rather than raise,
    both when the empty frame is built inside and when it is handed in."""
    builder = _CountingStreamBuilder(_empty_stream_frame())
    monkeypatch.setattr(AD, "settings_stream", builder)
    assert len(AD.build_design_matrix("PARTICIPANT")) == 0
    assert len(AD.build_design_matrix("PARTICIPANT", stream=_empty_stream_frame())) == 0


def test_washin_and_items_still_apply_when_a_stream_is_passed(monkeypatch, fake_biomarkers):
    """The new argument must not shadow the arguments that were already there. A wash-in long enough
    to exclude every rating must still empty the matrix when a stream is handed in."""
    monkeypatch.setattr(AD, "settings_stream", _CountingStreamBuilder(_stream_frame()))
    kept = AD.build_design_matrix("PARTICIPANT", stream=_stream_frame(), washin_min=1.0)
    dropped = AD.build_design_matrix("PARTICIPANT", stream=_stream_frame(),
                                     washin_min=60.0 * 24.0 * 30.0)
    assert len(kept) > 0
    assert len(dropped) == 0

    with pytest.raises(KeyError):
        AD.build_design_matrix("PARTICIPANT", stream=_stream_frame(),
                               items=("a_column_that_is_not_there",))


# ---------------------------------------------------------------------------------------------
# the callers that were already there
# ---------------------------------------------------------------------------------------------
def test_the_call_shapes_the_other_modules_use_still_bind():
    """Adding an argument must not break a caller that never heard of it.

    These are the exact shapes the shipping callers use, written out so that a future change to
    either signature has to notice them. ``StimOptimizer.bravo_service`` and
    ``StimOptimizer.pipeline`` both pass the request data positionally and the wash-in by keyword,
    and ``evidence_for_participant`` in this file passes two keywords and nothing else.
    """
    sig_dm = inspect.signature(AD.build_design_matrix)
    sig_dm.bind("PARTICIPANT", {"ParticipantId": "x"}, washin_min=1.0)   # bravo_service, pipeline
    sig_dm.bind("PARTICIPANT")                                            # the plain form
    sig_dm.bind("PARTICIPANT", None)                                      # a couple of scripts

    sig_ev = inspect.signature(AD.evidence_inputs)
    sig_ev.bind("PARTICIPANT", force_refresh=None, sources=None)          # evidence_for_participant
    sig_ev.bind("PARTICIPANT")


def test_evidence_for_participant_still_works_and_does_not_pass_a_stream(monkeypatch,
                                                                        fake_biomarkers):
    """The one caller of ``evidence_inputs`` inside this file. It asks for one participant's usable
    findings and does not have a settings stream of its own to hand over, so it must still cause the
    files to be read exactly once."""
    builder = _CountingStreamBuilder(_stream_frame())
    monkeypatch.setattr(AD, "settings_stream", builder)
    evidence, audit = AD.evidence_for_participant("PARTICIPANT")
    assert builder.n_calls == 1
    assert evidence == {}, "with no assembled spectra there is nothing to build"
    assert len(audit) == 1 and bool(audit["usable"].iloc[0]) is False


def test_the_numbers_in_the_design_matrix_are_the_ones_the_fixture_put_in(monkeypatch,
                                                                         fake_biomarkers):
    """A guard against the two paths agreeing on a wrong answer. Both could match while both being
    empty or both being nonsense, so this pins the actual values.
    """
    monkeypatch.setattr(AD, "settings_stream", _CountingStreamBuilder(_stream_frame()))
    dm = AD.build_design_matrix("PARTICIPANT", stream=_stream_frame()).sort_values("t_start")
    assert list(np.round(dm["amp_mA_Left"].to_numpy(), 6)) == [2.0, 3.0, 3.0]
    assert list(np.round(dm["pw_us_Left"].to_numpy(), 6)) == [60.0, 60.0, 90.0]
    # Two ratings landed in each of the three epochs: 7 and 6, then 4 and 5, then 3 and 2.
    assert list(dm["nrs_n"].to_numpy()) == [2, 2, 2]
    assert list(np.round(dm["nrs"].to_numpy(), 6)) == [6.5, 4.5, 2.5]
