"""No column name reaches the Closed-Loop page's text (decision 314, following 313).

Decision 313 put the shared adjusted estimator's refusals into plain words ("the left stimulation
current", not "amp_mA_Left"). Three more sentences on the Closed-Loop page still printed the column
the current was read from: the E2 note on the evidence triangle ("READ AGAIN WITH amp_mA_Left TAKEN
OUT"), the exported-table route's refusal, and the caveat on the sign-off sheet ("the current in force
(amp_mA_Left)"). The column stays on the answer as `adjusted_for`, for whoever needs to find the
code; the words go on the answer as `adjusted_for_words`, from the estimator's own table of words
(`analytics._covariate_words`, one home), and every sentence uses them.
"""
import numpy as np
import pandas as pd

try:
    from modules.ClosedLoopDeployment import adapter as AD, edges as E
    from modules.Biomarkers.routines import analytics as AN
except ImportError:                                              # pragma: no cover - host spelling
    from ClosedLoopDeployment import adapter as AD, edges as E
    from Biomarkers.routines import analytics as AN

CH, FC, AMP = "ONE_THREE_LEFT", 24.5, "amp_mA_Left"


def _table(n_reports=40, per=6, seed=5):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_reports):
        pain = float(rng.integers(0, 11))
        cur = float(rng.uniform(0.0, 4.0))
        for _ in range(per):
            rows.append({"channel": CH, "center_hz": FC, "power_linear": pain + rng.normal(0, 2.0),
                         "nrs": pain, "report_id": f"r{i}", AMP: cur})
    return pd.DataFrame(rows)


def test_the_e2_note_names_the_current_in_words():
    e = E.state_edge(_table(), channel=CH, center_hz=FC, n_boot=100, adjust_for_column=AMP)
    assert e.adjusted["available"] is True
    assert e.adjusted["adjusted_for"] == AMP                      # the column stays on the answer
    assert e.adjusted["adjusted_for_words"] == "the left stimulation current"
    assert "amp_mA" not in e.note, e.note
    assert "the left stimulation current" in e.note


def test_the_exported_table_refusal_names_the_current_in_words():
    exported = pd.DataFrame([{
        "channel": CH, "band_center_hz": FC, "auc": 0.62, "auc_low": 0.55, "auc_high": 0.70,
        "answer": AN.BAND_PAIN_ESTABLISHED, "p_two_sided": 0.02, "n_spectral_samples": 900,
        "n_pain_reports": 40, "why": "", "pain_split_rule": "thirds"}])
    e = E.state_edge(exported, channel=CH, center_hz=FC, adjust_for_column=AMP)
    assert e.adjusted["available"] is False
    assert "amp_mA" not in e.adjusted["why"] and "amp_mA" not in e.note, (e.adjusted["why"], e.note)
    assert "the left stimulation current" in e.adjusted["why"]


def test_the_sign_off_caveat_names_the_current_in_words_even_on_an_older_answer():
    # an answer saved before this change carries the column and no words
    for adjusted in ({"available": True, "auc": 0.52, "auc_low": 0.44, "auc_high": 0.61,
                      "adjusted_for": AMP},
                     {"available": True, "auc": 0.52, "auc_low": 0.44, "auc_high": 0.61,
                      "adjusted_for": AMP, "adjusted_for_words": "the left stimulation current"}):
        rows = AD.caveats_for_report({"available": True, "verdict_detail": {},
                                      "edges": {"E2": {"adjusted": adjusted}}})
        text = " ".join(r["text"] for r in rows)
        assert "amp_mA" not in text, text
        assert "the left stimulation current in force" in text, text


def test_a_reading_that_was_made_names_the_current_and_the_power_in_words():
    # 2026-09-26: the refusals were plain (313, 314), but a reading that WAS made still said
    # "the band power with amp_mA_Left removed from it", and handed the estimator "power_linear
    # with amp_mA_Left removed from it" as the name of what it read. No page prints either today.
    e = E.state_edge(_table(), channel=CH, center_hz=FC, n_boot=100, adjust_for_column=AMP)
    assert e.adjusted["available"] is True
    text = " ".join(str(v) for k, v in e.adjusted.items() if k != "adjusted_for")
    assert "amp_mA" not in text and "power_linear" not in text, text
    assert "the band power with the left stimulation current removed from it" in e.adjusted["why"]
