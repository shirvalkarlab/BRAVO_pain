"""The module's service entry point: what it promises the API, and what it writes to the log.

WHY THIS FILE EXISTS. Until 2026-09-10 this module had no `bravo_service.py`, while Biomarkers and
StimOptimizer each had one. The view resolved the participant itself and called
`adapter.report_for_participant` directly, wrapping the whole thing in one `except Exception` that
answered HTTP 200 with a readable sentence and wrote nothing anywhere.

That is a fine thing for a page to show and was catastrophic as the only record. On 2026-09-04 a
module-level import broke the entire package; every request came back through that handler with
`{"available": False, "reason": "deployment report error: No module named 'ClosedLoopDeployment'"}`;
and it stayed broken for five days until somebody read the code. Nothing was ever logged.

So the contract these tests hold is two-sided, and both sides matter:
  * the caller always gets `available`, and a False answer always carries a `reason`;
  * a failure ALWAYS reaches the log, with its traceback.
"""
import logging

import pytest

try:
    from modules.ClosedLoopDeployment import bravo_service as svc
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import bravo_service as svc


class _FakeAdapter:
    """Stands in for `adapter`, so these tests need no database and no participant."""

    def __init__(self, result=None, raises=None):
        self.result, self.raises, self.calls = result, raises, []

    def report_for_participant(self, participant, request_data, **kw):
        self.calls.append({"participant": participant, "request_data": request_data, **kw})
        if self.raises is not None:
            raise self.raises
        return self.result

    def three_source_pooled_for_participant(self, participant):
        self.calls.append({"participant": participant, "pooled_only": True})
        if self.raises is not None:
            raise self.raises
        return self.result


@pytest.fixture
def fake(monkeypatch):
    def _install(result=None, raises=None, participant=object()):
        a = _FakeAdapter(result=result, raises=raises)
        monkeypatch.setattr(svc, "_adapter", a)
        monkeypatch.setattr(svc, "_participant_or_none", lambda uid: participant)
        return a
    return _install


def test_a_request_with_no_participant_id_is_refused_with_a_reason():
    got = svc.run_for_participant({})
    assert got["available"] is False
    assert "ParticipantId" in got["reason"]


def test_a_participant_that_does_not_exist_is_an_ordinary_answer_not_an_error(fake, caplog):
    fake(participant=None)
    with caplog.at_level(logging.WARNING, logger=svc._log.name):
        got = svc.run_for_participant({"ParticipantId": "nobody"})
    assert got == {"available": False, "reason": "participant not found"}
    assert not caplog.records, (
        "asking about a participant who is not there is a normal thing for a client to do and is "
        "already visible in the response; logging it would train a reader to ignore the log")


def test_the_endpoints_documented_defaults_are_what_reaches_the_adapter(fake):
    a = fake(result={"available": True})
    svc.run_for_participant({"ParticipantId": "p1", "Candidates": [{"channel": "L", "center_hz": 9}]})
    call = a.calls[0]
    assert call["hemisphere"] == svc.DEFAULT_HEMISPHERE == "Left"
    assert call["power_scale"] == svc.DEFAULT_POWER_SCALE == "power_linear"
    assert call["candidates"] == [{"channel": "L", "center_hz": 9}]


def test_a_caller_supplied_hemisphere_and_scale_win_over_the_defaults(fake):
    a = fake(result={"available": True})
    svc.run_for_participant({"ParticipantId": "p1", "Hemisphere": "Right",
                             "PowerScale": "power_mean_of_log"})
    call = a.calls[0]
    assert call["hemisphere"] == "Right"
    assert call["power_scale"] == "power_mean_of_log"


def test_the_report_is_returned_untouched_when_it_succeeds(fake):
    payload = {"available": True, "verdict": "blocked", "cache_status": {"exists": True}}
    fake(result=payload)
    assert svc.run_for_participant({"ParticipantId": "p1"}) is payload


def test_a_failing_report_never_raises_and_always_reaches_the_log(fake, caplog):
    """THE LINE THAT WAS MISSING FOR FIVE DAYS. Both halves are asserted: the caller gets a sentence
    it can render, and the log gets the exception."""
    fake(raises=ImportError("No module named 'ClosedLoopDeployment'"))
    with caplog.at_level(logging.ERROR, logger=svc._log.name):
        got = svc.run_for_participant({"ParticipantId": "p1"})

    assert got["available"] is False
    assert "could not be built" in got["reason"]
    assert "No module named" in got["reason"], "the real cause was swallowed"

    assert caplog.records, "the failure reached the caller but not the log, which is the 2026-09-04 bug"
    rec = caplog.records[-1]
    assert rec.levelno >= logging.ERROR
    assert rec.exc_info is not None, (
        "logged without the traceback; the name of the module that would not import lives only "
        "there, which is exactly what made the original outage so hard to find")
    assert "p1" in rec.getMessage()


def test_a_participant_lookup_that_raises_is_also_caught_and_logged(fake, caplog):
    import unittest.mock as mock
    with mock.patch.object(svc, "_participant_or_none",
                           side_effect=RuntimeError("the database is not there")):
        with caplog.at_level(logging.ERROR, logger=svc._log.name):
            got = svc.run_for_participant({"ParticipantId": "p1"})
    assert got["available"] is False
    assert "could not be looked up" in got["reason"]
    assert caplog.records and caplog.records[-1].exc_info is not None


def test_the_view_calls_this_module_and_not_the_adapter_directly():
    """Pins the wiring. The point of a service layer is that it is the ONE door; a view reaching
    past it into `adapter` puts the failure contract back where it was."""
    import pathlib
    view = pathlib.Path(__file__).resolve().parents[3] / "Server" / "APIs" / "DataAnalysis.py"
    src = view.read_text()
    assert "from modules.ClosedLoopDeployment import bravo_service" in src, (
        "the view no longer routes through the module's service entry point")
    assert "cld_adapter.report_for_participant" not in src, (
        "the view reaches past bravo_service into adapter again")
    assert "_log.exception(\"closed-loop deployment report failed" in src, (
        "the view's catch-all no longer logs, which is the 2026-09-04 outage's own root cause")


# --------------------------------------------------------------------------------------------
# The pooled three-source view on its own (redesign decisions 5 and 10, 2026-09-11): the page asks
# for it AFTER the report has answered, and it must never rebuild the report.
# --------------------------------------------------------------------------------------------

def test_a_pooled_only_request_reads_the_stored_view_and_never_builds_the_report(fake):
    payload = {"available": True, "gates_nothing": True, "sides": []}
    a = fake(result=payload)
    got = svc.run_for_participant({"ParticipantId": "p1", "ThreeSourcePooled": 1})
    assert got is payload
    assert a.calls == [{"participant": a.calls[0]["participant"], "pooled_only": True}], (
        "the pooled-only request must not reach report_for_participant")


def test_a_failing_pooled_view_never_raises_and_reaches_the_log(fake, caplog):
    fake(raises=RuntimeError("the stored table is unreadable"))
    with caplog.at_level(logging.ERROR, logger=svc._log.name):
        got = svc.run_for_participant({"ParticipantId": "p1", "ThreeSourcePooled": 1})
    assert got["available"] is False
    assert "pooled three-source view" in got["reason"] and "unreadable" in got["reason"]
    assert caplog.records and caplog.records[-1].exc_info is not None
