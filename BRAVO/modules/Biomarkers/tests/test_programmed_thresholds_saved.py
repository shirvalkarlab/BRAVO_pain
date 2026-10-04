"""The device's programmed adaptive thresholds, saved per participant (the PI, 2026-10-04, decision
429, plan item 2): about 2.3 s of every band-power request walked all 10,421 therapy groups. The
answer depends only on the therapy history, so it is saved under the participant's source files
(ids, content hashes) and the therapy rows' count and highest id; any change there works it out
again. An empty answer is not saved."""
from modules.Biomarkers import bravo_service as B
from modules.CacheStore.tests.test_store import _Sandbox

ANSWER = {"Left": {"lower": 192.0, "upper": 242.0, "status": "RUNNING", "date": 1.0}}


def _patched(label, answer):
    calls = []
    real = (B._programmed_adaptive_thresholds_build, B._therapy_history_label)
    B._programmed_adaptive_thresholds_build = lambda p: (calls.append(1) or dict(answer))
    B._therapy_history_label = lambda p: label[0]

    def undo():
        B._programmed_adaptive_thresholds_build, B._therapy_history_label = real
    return calls, undo


def test_worked_out_once_then_read_back_and_again_when_the_history_changes():
    with _Sandbox():
        label = [("files-1", 10421, 99)]
        calls, undo = _patched(label, ANSWER)
        try:
            a = B._programmed_adaptive_thresholds("P")
            b = B._programmed_adaptive_thresholds("P")
            label[0] = ("files-1", 10422, 100)
            c = B._programmed_adaptive_thresholds("P")
        finally:
            undo()
    assert a == b == c == ANSWER and len(calls) == 2


def test_an_empty_answer_is_not_saved():
    with _Sandbox():
        calls, undo = _patched([("files-1", 1, 1)], {})
        try:
            B._programmed_adaptive_thresholds("P")
            B._programmed_adaptive_thresholds("P")
        finally:
            undo()
    assert len(calls) == 2
