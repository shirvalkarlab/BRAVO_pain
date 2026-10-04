"""The summary and the three Closed-Loop panels remember the requests they answer (decision 435), so
the server can work them out again when the data change; a request whose label cannot be built
(no participant, an unknown one) is not remembered."""
import os

from modules.CacheStore import locks, request_memory as rm, saved_answers
from modules.CacheStore.tests.test_request_memory import FakeRedis


def _run(fingerprints):
    from modules.Biomarkers import bravo_service as bs
    fake = FakeRedis()
    saved = (locks.CLIENT_FACTORY, os.environ.get(rm.OFF_ENV), bs.summary_input_fingerprints,
             saved_answers.serve_or_build)
    locks.CLIENT_FACTORY, os.environ[rm.OFF_ENV] = (lambda: fake), "1"
    bs.summary_input_fingerprints = fingerprints
    saved_answers.serve_or_build = lambda kind, uid, inputs, build, **k: build()
    try:
        out = bs._serve_saved_band_answer("deployment_summary", {"ParticipantId": "u1", "CenterHz": 23.5},
                                          lambda rd: {"available": True, "rd": rd})
        return out, rm.recent("u1")
    finally:
        locks.CLIENT_FACTORY, env, bs.summary_input_fingerprints, saved_answers.serve_or_build = saved
        if env is None:
            os.environ.pop(rm.OFF_ENV, None)
        else:
            os.environ[rm.OFF_ENV] = env


def test_an_answered_request_is_remembered():
    out, got = _run(lambda uid, rd: {"x": 1})
    assert out["available"] is True
    assert [(g["kind"], g["body"]) for g in got] == [
        ("deployment_summary", {"ParticipantId": "u1", "CenterHz": 23.5})]


def test_a_request_without_a_label_is_not_remembered():
    def no_label(uid, rd):
        raise LookupError("no participant")
    out, got = _run(no_label)
    assert out["available"] is True and got == []
