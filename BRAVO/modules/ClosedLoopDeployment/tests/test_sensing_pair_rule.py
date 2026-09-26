"""The Closed-Loop page checks the device's sensing-pair rule, and its caveats print readable numbers.

WHY (the PI, 2026-09-22, after watching the page). The page said "The device permits this
configuration" for L 0-2+ at 24.5 Hz while the patient's left lead stimulates on contact 2 -- and
with contact 2 stimulating the device allows sensing on L 1-3+ only. The Stim Optimizer's readiness
card already said so (decision 217); the Closed-Loop page's 51 device rules never looked at which
contacts stimulate, so it could not.

The rule is a device fact, so it becomes a row of the device-rule table (D52), read from the same
three documents decision 217 cites, with the stimulating contacts read off the settings row in force
for the sensing lead -- the row that already supplies the rate and pulse width the other rules check
(decision 132). The rule's arithmetic has ONE home, the Stim Optimizer's `lfp_evidence` helpers that
the readiness card uses; this file tests that the Closed-Loop page reaches it, not a second copy.

Also here: the sign-off sheet's caveat about the two switching values printed them to thirteen
decimal places ("172.2737406083742"); it now prints them exactly as the parameter card does.

Run on the host:
    cd BRAVO/modules && PYTHONPATH=. python -B -m pytest ClosedLoopDeployment/tests/test_sensing_pair_rule.py -q
"""
import re

import pandas as pd
import pytest

from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment import constraints


def _epochs(cathode_left="2a-2b-2c", cathode_right="1a-1b-1c-2a-2b-2c"):
    """Two settings rows; the newer (open-ended) one is in force."""
    return pd.DataFrame([
        {"epoch": 1.0, "t_start": pd.Timestamp("2026-08-01", tz="UTC"), "open_ended": False,
         "freq_hz": 55.0, "pw_us_Left": 60.0, "pw_us_Right": 160.0,
         "cathode_Left": "1a-1b-1c", "cathode_Right": "2a-2b-2c"},
        {"epoch": 2.0, "t_start": pd.Timestamp("2026-09-08", tz="UTC"), "open_ended": True,
         "freq_hz": 55.0, "pw_us_Left": 100.0, "pw_us_Right": 150.0,
         "cathode_Left": cathode_left, "cathode_Right": cathode_right},
    ])


def _candidate(channel):
    side = "Left" if channel.endswith("LEFT") else "Right"
    return {"channel": channel, "center_hz": 24.5, "band_width_hz": 5.0,
            "sensing_hemisphere": side, "actuated_hemisphere": side}


def _d52():
    rows = [r for r in constraints.RULES if r.rule_id == "D52"]
    assert rows, "the device-rule table carries the sensing-pair rule as D52"
    return rows[0]


# ---------------------------------------------------------------------------------------------
# 1. the stimulating contacts reach the rules, from the settings row in force
# ---------------------------------------------------------------------------------------------

def test_the_settings_in_force_carry_the_sensing_leads_stimulating_contacts():
    got = AD.programmed_settings_from_epochs(_epochs(), "Left")
    assert got["stim_rings_on_sensing_lead"] == [2], "the newest row: the left lead stimulates on 2"
    assert got["stim_contacts_on_sensing_lead"] == "2a-2b-2c"
    right = AD.programmed_settings_from_epochs(_epochs(), "Right")
    assert right["stim_rings_on_sensing_lead"] == [1, 2]
    # the rate and pulse width the other rules read are unchanged
    assert got["rate_hz"] == 55.0 and got["pulse_width_us"] == 100.0


def test_a_row_with_no_cathode_gives_no_contacts_rather_than_a_guess():
    eps = _epochs(cathode_left=None)
    got = AD.programmed_settings_from_epochs(eps, "Left")
    assert "stim_rings_on_sensing_lead" not in got
    assert got["rate_hz"] == 55.0


# ---------------------------------------------------------------------------------------------
# 2. the rule itself
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("channel, rings, expected", [
    ("ONE_THREE_LEFT", [2], True),        # stimulate on 2 -> sense 1-3
    ("ZERO_TWO_LEFT", [2], False),        # the page's case: 0-2 needs stimulation on 1
    ("ZERO_TWO_LEFT", [1], True),
    ("ZERO_THREE_RIGHT", [1, 2], True),   # stimulate on 1 and 2 -> sense 0-3
    ("ZERO_THREE_LEFT", [2], False),
    ("ONE_THREE_LEFT", [3], False),       # an end contact allows no pair at all
])
def test_the_rule_passes_only_the_pair_that_flanks_the_stimulating_contacts(channel, rings, expected):
    assert _d52().predicate(_candidate(channel), {"stim_rings_on_sensing_lead": rings}) is expected


def test_the_rule_is_not_determinable_without_the_contacts_or_a_readable_pair():
    rule = _d52()
    assert rule.predicate(_candidate("ONE_THREE_LEFT"), {}) is None
    assert rule.predicate(_candidate("ONE_THREE_LEFT"), {"stim_rings_on_sensing_lead": []}) is None
    assert rule.predicate({"channel": "SOMETHING_ODD", "sensing_hemisphere": "Left"},
                          {"stim_rings_on_sensing_lead": [2]}) is None


def test_the_rule_blocks_and_cites_its_documents():
    rule = _d52()
    assert rule.severity == "blocking"
    for doc in ("A610", "WP"):
        assert doc in rule.source
    assert "flank" in rule.human_text.lower()


def test_a_failure_names_the_allowed_pair_and_the_contacts_the_chosen_pair_needs():
    rep = constraints.check_eligibility(_candidate("ZERO_TWO_LEFT"),
                                        {"stim_rings_on_sensing_lead": [2],
                                         "stim_contacts_on_sensing_lead": "2a-2b-2c"},
                                        rules=[_d52()])
    assert rep.eligible is False
    fail = [f for f in rep.failures if f["rule_id"] == "D52"]
    assert fail, "D52 is charged against the verdict"
    text = " ".join(str(v) for v in fail[0].values())
    assert "1-3" in text, "names the one pair the device allows with contact 2 stimulating"
    assert "contact 1" in text or "contacts 1" in text, "names what 0-2 would need"


def test_a_pass_records_what_it_was_checked_against():
    """The pass is derived from the device's programmed contacts, so like D30 it must show which --
    otherwise a reader cannot tell a checked pass from a rule that had nothing to read."""
    assert "D52" in constraints._RECORD_VALUE_ON_PASS
    obs = constraints._OBSERVED["D52"](_candidate("ONE_THREE_LEFT"),
                                        {"stim_rings_on_sensing_lead": [2],
                                         "stim_contacts_on_sensing_lead": "2a-2b-2c"})
    assert "1-3" in obs and "2" in obs


# ---------------------------------------------------------------------------------------------
# 3. the caveat prints the switching values as the parameter card does
# ---------------------------------------------------------------------------------------------

def test_the_switching_values_caveat_prints_four_decimals_like_the_parameter_card():
    """The parameter card formats these two values with `fmtPower` (four decimals); the caveat said
    "172.2737406083742". One number, printed the same way in both places."""
    # A permitted configuration: the values are printed only then since decision 302.
    payload = {"available": True, "verdict_detail": {"device_eligible": True},
               "threshold": {"upper": 182.2737406083742, "lower": 172.2737406083742}}
    rows = [r for r in AD.caveats_for_report(payload) if "switching values" in r["text"]]
    assert rows, "the caveat about the two switching values is present"
    assert "172.2737 and 182.2737" in rows[0]["text"]
    assert "172.2737406083742" not in rows[0]["text"]


def test_no_caveat_prints_a_number_to_more_than_four_decimals():
    payload = {"available": True,
               "verdict_detail": {"provisional": True, "n_edges_unestablished": 2, "n_edges": 3,
                                  "unestablished_edges": ["E1", "E2"]},
               "edges": {"E2": {"adjusted": {"available": True, "auc": 0.504123456789,
                                             "auc_low": 0.41712345678, "auc_high": 0.5901234567,
                                             "adjusted_for": "amp_mA_Left"}}},
               "threshold": {"upper": 240.53991352296697, "lower": 190.53991352296697}}
    for r in AD.caveats_for_report(payload):
        assert not re.search(r"\d\.\d{5,}", r["text"]), r["text"]


# ---------------------------------------------------------------------------------------------
# 4. the contacts reach the rule through the pipeline's own routing, not a hand-built dict
# ---------------------------------------------------------------------------------------------

def test_the_contacts_reach_d52_through_the_pipelines_own_fact_routing():
    """Found only by the live run (2026-09-22): the tests above hand D52 a participant dict they
    built themselves, so they passed while the page reported D52 "not determinable" on every
    candidate -- and, D52 being blocking, turned L 1-3+ from "supported" to "blocked". The pipeline
    passes a device fact to the rules only if `PARTICIPANT_KEYS` lists it, and the two new facts
    were not listed. This test goes through that routing, from the facts the adapter builds."""
    from ClosedLoopDeployment import pipeline
    dev = dict(AD.programmed_settings_from_epochs(_epochs(), "Left"))
    dev.pop("_provenance", None)
    part = pipeline._participant_facts("uid-x", device_facts=dev, constraints_module=constraints)
    assert part.get("stim_rings_on_sensing_lead") == [2]
    assert part.get("stim_contacts_on_sensing_lead") == "2a-2b-2c"
    assert _d52().predicate(_candidate("ONE_THREE_LEFT"), part) is True
    assert _d52().predicate(_candidate("ZERO_TWO_LEFT"), part) is False
