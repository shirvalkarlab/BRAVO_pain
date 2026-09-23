"""Three field groups the Closed-Loop response carried and nothing read (panel D item 10, 2026-09-22).

A whole-tree search on 2026-09-23 found no reader of any of them outside this module, its tests and
its fixtures: not the page, not the Stim Optimizer, not the server. A field nobody reads is not free
-- it is a number a reader of the raw response may take as the page's own, and it has to be kept
right under every change. So they leave the SERVED response; the report object and the functions that
compute them stay, with their own tests.

  * `protocol` -- a titration-session plan built from the two capture currents. The page's
    titration plan is the Stim Optimizer's card (decisions 146, 160, 230, 236), not this one.
  * `edges_historical` -- the setting-epoch E1 that the pooled titration slope replaced (decision
    126). It stays on the report (`rep.edges_historical`) and E1 still says which estimate it is.
  * `predicted_failure_mode`, `qualified_transitions`, `unqualified_excursions` on each duty cycle.

Pinned on the keys present and absent, and on the values that stay.
"""
from types import SimpleNamespace

try:
    from modules.ClosedLoopDeployment import adapter as AD, prescription as PR
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import adapter as AD, prescription as PR

from ClosedLoopDeployment.tests.test_pooled_e1 import _run_pipeline, _row


def _with_a_prescription(rep):
    duty = PR.DutyCycle()
    duty.predicted_failure_mode = "stuck high"
    duty.qualified_transitions = 7
    duty.unqualified_excursions = 3
    duty.transitions_per_hour = 1.25
    duty.caveats = ["a caveat"]
    rx = SimpleNamespace(mode="dual", as_rows=lambda: [], not_applicable=[], couplings=[],
                         unknowns=[], note="n", duty=duty)
    rep.prescription = rx
    rep.prescriptions = {"recommended": "dual", "recommendation": {},
                         "modes": {"dual": rx}}
    rep.protocol = SimpleNamespace(steps=[{"a": 1}], n_pairs=2, alpha=0.05, power=0.8,
                                   detectable_d=1.0, duration_min=30, seed=0, note="p")
    return rep


def test_the_served_response_no_longer_carries_the_titration_protocol(monkeypatch):
    d = AD.report_to_dict(_with_a_prescription(_run_pipeline(monkeypatch, _row())))
    assert "protocol" not in d


def test_the_historical_e1_stays_on_the_report_and_leaves_the_response(monkeypatch):
    rep = _run_pipeline(monkeypatch, _row())
    assert rep.edges_historical["E1"].source == "screening_historical"
    d = AD.report_to_dict(rep)
    assert "edges_historical" not in d
    assert d["edges"]["E1"]["source"] == "pooled_titration", "E1 still says which estimate it is"


def test_the_duty_cycle_loses_the_three_unread_fields_and_keeps_the_rest(monkeypatch):
    d = AD.report_to_dict(_with_a_prescription(_run_pipeline(monkeypatch, _row())))
    for duty in (d["prescription"]["duty"], d["prescriptions"]["modes"]["dual"]["duty"]):
        for gone in ("predicted_failure_mode", "qualified_transitions", "unqualified_excursions"):
            assert gone not in duty, gone
        assert duty["transitions_per_hour"] == 1.25
        assert duty["caveats"] == ["a caveat"]
