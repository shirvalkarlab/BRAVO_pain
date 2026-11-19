"""The sign-off summary's caveats carry the area-under-the-curve q warning the way they carry the
correlation q warning (decision 508; the PI, 2026-11-10: "Finish all the open items"; the AUC q is
decision 500's, shown on the sign-off card since decision 504).

`bravo_service._attach_summary_family_q` puts the band's q block (`family_correction.summary_block`,
attached on read, never stored) under `evidence.family_correction`. Its correlation q warning was
listed with the caveats; its AUC q warning was on the card only. Held here, on a stood-in block:
  * an AUC q warning is appended to the caveats as "Correction across bands, area under the curve
    (warning only): <warning>", after the correlation one when both are warned;
  * no AUC warning, no line; the summary is otherwise the same, field for field;
  * the switch off (`family_correction.ENABLED` False) returns the summary as it was.

Needs Django (runs in the container)."""
import copy
import os
import sys

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))

R_WARN = ("Corrected for the 22 bands tested on L 0-3, this band's q is 0.87: it may be a chance "
          "finding")
AUC_WARN = ("Corrected for the 22 area-under-the-curve bands tested on L 0-3, this band's q is 0.73: "
            "it may be a chance finding")


def _bs():
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
        import django
        django.setup()
        from modules.Biomarkers import bravo_service as bs
        return bs
    except Exception:                                      # noqa: BLE001
        import pytest
        pytest.skip("the summary needs Django (runs in the container)")


def _summary():
    return {"available": True, "verdict": "candidate", "identity": {"contact": "ZERO_THREE_LEFT",
                                                                     "center_freq_hz": 12.5},
            "evidence": {"auc": 0.61}, "caveats": ["Selection bias: chosen from a sweep."]}


def _attach(bs, block, enabled=True):
    fc = bs.family_correction
    orig_sb, orig_en = fc.summary_block, fc.ENABLED
    fc.summary_block = lambda *a, **k: dict(block)
    fc.ENABLED = enabled
    try:
        s = _summary()
        out = bs._attach_summary_family_q(s, {"ParticipantId": "uid"})
        assert s == _summary()                             # the input is not touched
        return out
    finally:
        fc.summary_block, fc.ENABLED = orig_sb, orig_en


def test_the_auc_q_warning_is_listed_with_the_caveats_after_the_correlation_one():
    bs = _bs()
    out = _attach(bs, {"family_q": 0.87, "family_q_warning": R_WARN,
                       "family_q_auc": 0.73, "family_q_auc_warning": AUC_WARN})
    assert out["caveats"] == [
        "Selection bias: chosen from a sweep.",
        "Correction across bands (warning only): " + R_WARN,
        "Correction across bands, area under the curve (warning only): " + AUC_WARN]
    assert out["evidence"]["family_correction"]["family_q_auc_warning"] == AUC_WARN


def test_an_auc_warning_alone_is_listed_alone():
    bs = _bs()
    out = _attach(bs, {"family_q": 0.03, "family_q_warning": None,
                       "family_q_auc": 0.73, "family_q_auc_warning": AUC_WARN})
    assert out["caveats"] == [
        "Selection bias: chosen from a sweep.",
        "Correction across bands, area under the curve (warning only): " + AUC_WARN]


def test_no_auc_warning_adds_no_line_and_nothing_else_moves():
    bs = _bs()
    block = {"family_q": 0.87, "family_q_warning": R_WARN, "family_q_auc": 0.02,
             "family_q_auc_warning": None}
    out = _attach(bs, block)
    assert out["caveats"] == ["Selection bias: chosen from a sweep.",
                              "Correction across bands (warning only): " + R_WARN]
    expect = copy.deepcopy(_summary())
    expect["evidence"]["family_correction"] = block
    expect["caveats"] = out["caveats"]
    assert out == expect


def test_the_switch_off_returns_the_summary_as_it_was():
    bs = _bs()
    out = _attach(bs, {"family_q_auc_warning": AUC_WARN}, enabled=False)
    assert out == _summary()
