"""A newly filed pain report reaches the Closed-Loop report even when no recording has changed
(2026-09-25; CLAUDE.md §7 rule 5: no pain rating in the payload of a recording-derived
product, because a saved file then serves a stale rating with no visible symptom).

Two places held ratings under a label that did not include them: the saved `inputs` bundle (the
evidence frame, the exposure epochs AND the design matrix, whose `nrs` and `vas` columns are the
ratings), keyed on the recording set, the constants and a rule version; and the joined table's
in-process memo, keyed on the evidence frame and the epochs while the pain frame it merges in was
left out. Both would keep serving yesterday's ratings until a recording arrived.
"""
import pandas as pd

from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment.tests.test_adapter_caching import (  # noqa: F401  (fixtures)
    _epoch_frame, _isolate_caches, _pain_report_frame, _psd_frame, live_inputs)


def test_a_new_pain_report_reaches_the_design_matrix_with_the_recordings_unchanged(live_inputs, monkeypatch):
    import sys
    _psd, _eps, dm1 = AD.evidence_inputs_cached("PARTICIPANT")
    before = dm1["nrs"].to_list()

    corrected = _pain_report_frame()
    corrected.loc[0, "nrs"] = 0.0                      # a rating filed or corrected since
    monkeypatch.setattr(sys.modules["modules.Biomarkers.bravo_service"], "_load_pros",
                        lambda request_data, participant: corrected)
    _psd, _eps, dm2 = AD.evidence_inputs_cached("PARTICIPANT")
    assert dm2["nrs"].to_list() != before, "the saved inputs served the old rating"
    assert len(live_inputs) == 1, "the settings (recording-derived) must still be read only once"


def test_the_joined_table_memo_tells_two_pain_frames_apart():
    psd, eps = _psd_frame(), _epoch_frame()
    p1 = pd.DataFrame({"epoch": [1.0], "report_id": ["1"], "nrs": [7.0], "vas": [70.0]})
    p2 = p1.assign(nrs=[2.0])
    t1 = AD.joined_table_cached(psd, eps, pro_frame=p1)
    t2 = AD.joined_table_cached(psd, eps, pro_frame=p2)
    assert t1 is not t2
    assert set(t2["nrs"].dropna()) == {2.0}
