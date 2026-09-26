"""P-03 (June audit items [0] and [22], approved by the PI 2026-09-25): the stability answer on the
Closed-Loop report carries the odds ratio in each stimulation state WITH its interval, and says how
many pain reports had samples under two states before each was counted in one.

The Biomarkers test computes both (`band_stim_stability`: `or_by_era`, `or_by_era_ci`,
`one_block_per_report`); until now the translation into the report dropped them, so the per-state
odds ratios reached no page for a band chosen on the grid. No R needed: these feed the translation
the shapes the Biomarkers test returns.
"""

from ClosedLoopDeployment import stability as ST


def _raw(**extra):
    slopes = {"OFF": {"slope_log_or": 0.2, "se": 0.3, "n": 60},
              "LOW": {"slope_log_or": -0.1, "se": 0.25, "n": 80},
              "HIGH": None}
    eq = ST.stability_equivalence(slopes, 0.4)
    out = {"available": True, "lrt_p": 0.4, "slope_by_era": slopes, "equivalence": eq,
           "stability_verdict": eq["verdict"], "n": 140, "n_clusters": 9,
           "era_counts": {"OFF": 60, "LOW": 80, "HIGH": 0},
           "rate": {"available": False},
           "or_by_era": {"OFF": 1.2214, "LOW": 0.9048, "HIGH": None}}
    out.update(extra)
    return out


def test_each_state_carries_its_odds_ratio_interval_and_count():
    raw = _raw(or_by_era_ci={"OFF": [0.679, 2.199], "LOW": [0.554, 1.477], "HIGH": None},
               or_by_era_interval="95% Wald interval from each state's own logistic fit",
               one_block_per_report={"n_reports_split_across_states": 3,
                                     "n_reports_split_across_weeks": 0})
    p = ST.finding_from_stability_result(raw, "ONE_THREE_LEFT", 24.5).as_payload()
    per = p["odds_ratio_per_state"]
    assert list(per) == ["stimulation off", "low current", "high current"], list(per)
    assert per["stimulation off"] == {"odds_ratio": 1.2214, "low": 0.679, "high": 2.199, "n": 60,
                                         "n_reports": None}
    assert per["low current"] == {"odds_ratio": 0.9048, "low": 0.554, "high": 1.477, "n": 80,
                                     "n_reports": None}
    assert per["high current"] == {"odds_ratio": None, "low": None, "high": None, "n": 0,
                                      "n_reports": None}
    assert p["odds_ratio_interval_method"].startswith("95% Wald"), p["odds_ratio_interval_method"]
    assert p["n_reports_split_across_states"] == 3
    assert p["n_reports_split_across_weeks"] == 0


def test_a_stored_answer_from_before_the_interval_says_none_rather_than_inventing_one():
    """Answers stored before this change carry odds ratios but no interval and no split count."""
    p = ST.finding_from_stability_result(_raw(), "ONE_THREE_LEFT", 24.5).as_payload()
    assert p["odds_ratio_per_state"]["stimulation off"] == {
        "odds_ratio": 1.2214, "low": None, "high": None, "n": 60, "n_reports": None}
    assert p["odds_ratio_interval_method"] is None
    assert p["n_reports_split_across_states"] is None


def test_a_test_that_did_not_run_carries_no_odds_ratios():
    p = ST.finding_from_stability_result({"available": False, "reason": "no stim series"},
                                         "ONE_THREE_LEFT", 24.5).as_payload()
    assert p["odds_ratio_per_state"] == {}
    assert p["n_reports_split_across_states"] is None


def test_the_payload_still_has_no_true_or_false_summary():
    raw = _raw(or_by_era_ci={"OFF": [0.679, 2.199], "LOW": [0.554, 1.477], "HIGH": None})
    p = ST.finding_from_stability_result(raw, "ONE_THREE_LEFT", 24.5).as_payload()
    assert [k for k, v in p.items() if isinstance(v, bool)] == ["test_ran"]
