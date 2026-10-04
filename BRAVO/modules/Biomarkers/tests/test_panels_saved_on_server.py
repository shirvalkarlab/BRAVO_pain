"""The Closed-Loop page's ROC, month-by-month and band-power panels are saved on the server (the PI,
2026-10-04, decision 428; plan item 1): measured 3.9, 4.2 and 11-13 s on every request. Each is
worked out once and served for the same request and the same recordings, settings files, pain
reports and clinic sheets (`summary_input_fingerprints`, decision 423); a new pain report is worked
out again; an unknown participant is never saved."""
from modules.Biomarkers import bravo_service as B
from modules.CacheStore.tests.test_store import _Sandbox, UID

REQ = {"ParticipantId": UID, "Channel": "ZERO_TWO_LEFT", "CenterHz": 20.5, "BandWidthHz": 5.0,
       "MatchDirection": "prior", "LabelMetric": "nrs"}
PANELS = (("band_deployment_roc", "_band_deployment_roc_build"),
          ("band_deployment_roc_by_era", "_band_deployment_roc_by_era_build"),
          ("band_lsb_and_power", "_band_lsb_and_power_build"))


def _patched(build_name, pain):
    calls = []
    real = (getattr(B, build_name), B.summary_input_fingerprints)
    setattr(B, build_name, lambda rd: (calls.append(1) or {"available": True, "n": len(calls)}))
    B.summary_input_fingerprints = lambda uid, rd: {"request": rd, "pain_reports": pain[0]}

    def undo():
        setattr(B, build_name, real[0])
        B.summary_input_fingerprints = real[1]
    return calls, undo


def test_each_panel_is_worked_out_once_then_served_and_again_after_a_new_pain_report():
    for endpoint, build in PANELS:
        with _Sandbox():
            pain = ["p1"]
            calls, undo = _patched(build, pain)
            try:
                a = getattr(B, endpoint)(dict(REQ))
                b = getattr(B, endpoint)(dict(REQ))
                pain[0] = "p2"
                c = getattr(B, endpoint)(dict(REQ))
            finally:
                undo()
        assert len(calls) == 2, endpoint
        assert b["saved_answer"]["served"] is True and a["n"] == b["n"] == 1, endpoint
        assert c["saved_answer"]["served"] is False, endpoint


def test_the_three_panels_are_saved_under_their_own_kinds():
    assert {B.PANEL_KINDS[e] for e, _ in PANELS} == {"deployment_roc", "deployment_roc_by_era",
                                                      "band_lsb_power"}
