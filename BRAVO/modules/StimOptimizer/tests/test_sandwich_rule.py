"""The sensing pair must be the two contacts IMMEDIATELY flanking the stimulating contact on its
own lead (decision 217, the PI, 2026-09-20: "in monopolar stimulation mode such as Left C+2-,
sensing contact pair must be the adjacent contacts immediately above and below the active cathode
... for L C+1-2-, we have to use L 0-3+").

The device offers exactly three sensing/stimulation configurations per lead (Medtronic BrainSense
tip card p. 8: "Unipolar Stimulation Only; Two Sensing contacts on lead are needed; Cannot
stimulate on sensing contacts; Stimulation contacts must be between sensing contacts; Results in 3
Possible Sensing/Stimulation Configurations Per Lead", and the three lead pictograms on its p. 7
and the white paper p. 8, "3 possibilities"): stimulate on 1 and sense 0-2; stimulate on 2 and
sense 1-3; stimulate on 1 and 2 and sense 0-3. Stimulating on 0 or 3 leaves no flanking pair (A610
p. 36 sends such a lead to contralateral sensing). The readiness screen judged every pair on its
evidence alone and so offered L 0-2+ while the left stimulates on contact 2. Now the screen is told
which rings each lead stimulates on (the cathode in force) and a cell whose sensing pair is not the
flanking pair is refused with a plain reason. A lead with no stimulation in force applies no rule.

Merged here 2026-10-05: test_sensing_rule_first.py, test_sensing_rule_one_home.py (each under its own heading below).
"""
import numpy as np
import pytest

from StimOptimizer.routines import lfp_evidence as EV
from StimOptimizer import bravo_service as BS
from StimOptimizer.tests import _helpers as H
from DecodeCommon import sensing_rule as SR
from StimOptimizer import titration_plan as TP

CENTRES = H.CENTRES


_Res = H.stub_result


_Ev = H.BandStubEvidence


_fn_negative_at = H.fn_negative_at


@pytest.mark.parametrize("pair,rings,ok", [
    ("ONE_THREE_LEFT", {2}, True),     # stimulate on 2: the flanking pair is 1-3
    ("ZERO_TWO_LEFT", {2}, False),     # contains the stimulating contact
    ("ZERO_THREE_LEFT", {2}, False),   # brackets it but is not the flanking pair
    ("ZERO_ONE_LEFT", {2}, False),
    ("TWO_THREE_LEFT", {2}, False),
    ("ZERO_TWO_LEFT", {1}, True),      # stimulate on 1: the flanking pair is 0-2
    ("ONE_THREE_LEFT", {1}, False),
    ("ZERO_THREE_LEFT", {1}, False),
    ("ZERO_THREE_LEFT", {1, 2}, True),   # stimulate on 1 and 2 (double monopolar): 0-3
    ("ONE_THREE_LEFT", {1, 2}, False),
    ("ZERO_TWO_LEFT", {1, 2}, False),
    ("ONE_THREE_LEFT", {0}, False),    # stimulating on 0: no pair flanks it
    ("ZERO_TWO_LEFT", {3}, False),     # stimulating on 3: no pair flanks it
])
def test_the_sensing_pair_must_be_the_contacts_immediately_flanking_the_stimulating_contact(pair, rings, ok):
    assert EV.pair_flanks_stimulation(pair, rings) is ok


@pytest.mark.parametrize("rings,expected", [({2}, (1, 3)), ({1}, (0, 2)), ({1, 2}, (0, 3)), ({0}, None), ({3}, None), ({2, 3}, None), (set(), None)])
def test_the_one_allowed_pair_for_a_stimulating_contact(rings, expected):
    assert EV.flanking_pair(rings) == expected


def test_a_pair_containing_the_stimulating_contact_is_refused_on_the_screen_with_the_reason():
    ev = {("ZERO_TWO_LEFT", "Left", 55.0): _Ev(), ("ONE_THREE_LEFT", "Left", 55.0): _Ev()}
    pain = {"ZERO_TWO_LEFT": {24.0}, "ONE_THREE_LEFT": {24.0}}
    screen, best = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]), pain_positive_by_channel=pain,
                                   stim_rings_by_side={"Left": {2}, "Right": {2}})
    rows = {r.channel: r for _, r in screen.iterrows()}
    assert bool(rows["ONE_THREE_LEFT"].deployable) is True and rows["ONE_THREE_LEFT"].blocking_reasons == ""
    assert bool(rows["ZERO_TWO_LEFT"].deployable) is False
    assert "stimulating on contact 2" in rows["ZERO_TWO_LEFT"].blocking_reasons
    assert "the only sensing pair the device allows is 1-3" in rows["ZERO_TWO_LEFT"].blocking_reasons
    assert bool(rows["ZERO_TWO_LEFT"].sensing_pair_flanks_stimulation) is False
    assert bool(rows["ONE_THREE_LEFT"].sensing_pair_flanks_stimulation) is True
    assert best == ("ONE_THREE_LEFT", "Left", 55.0)


def test_the_rule_reads_the_sensing_leads_own_stimulating_contact_not_the_cells_side():
    """A contralateral cell (sensing on the right, driving the left) is judged against the RIGHT
    lead's stimulating contact, because that is the lead the pair sits on."""
    ev = {("ZERO_TWO_RIGHT", "Left", 55.0): _Ev()}
    screen, _ = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                pain_positive_by_channel={"ZERO_TWO_RIGHT": {24.0}},
                                stim_rings_by_side={"Left": {2}, "Right": {1}})
    assert bool(screen.iloc[0].sensing_pair_flanks_stimulation) is True     # 0-2 flanks 1
    assert bool(screen.iloc[0].deployable) is True


def test_no_stimulation_in_force_on_a_lead_applies_no_rule_and_says_it_was_not_checked():
    ev = {("ZERO_TWO_LEFT", "Left", 55.0): _Ev()}
    screen, _ = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                pain_positive_by_channel={"ZERO_TWO_LEFT": {24.0}})
    assert screen.iloc[0].sensing_pair_flanks_stimulation is None
    assert bool(screen.iloc[0].deployable) is True
    screen2, _ = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                 pain_positive_by_channel={"ZERO_TWO_LEFT": {24.0}},
                                 stim_rings_by_side={"Left": set(), "Right": {2}})
    assert screen2.iloc[0].sensing_pair_flanks_stimulation is None


def test_stimulating_on_contact_0_or_3_refuses_every_pair_on_that_lead_and_says_why():
    ev = {("ONE_THREE_LEFT", "Left", 55.0): _Ev()}
    screen, _ = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                pain_positive_by_channel={"ONE_THREE_LEFT": {24.0}},
                                stim_rings_by_side={"Left": {3}, "Right": {2}})
    assert bool(screen.iloc[0].deployable) is False
    assert "no sensing pair flanks" in screen.iloc[0].blocking_reasons


def test_the_stimulating_rings_are_read_from_the_cathode_in_force():
    assert BS.stim_rings("2a-2b-2c") == {2}
    assert BS.stim_rings("1a-1b-1c-2a-2b-2c") == {1, 2}
    assert BS.stim_rings("1a-1b") == {1}
    assert BS.stim_rings(None) == set() and BS.stim_rings("none") == set()
    assert BS.stim_rings_by_side({"Left": {"contacts_raw": "2a-2b-2c"}, "Right": {"contacts_raw": "1a-1b-1c-2a-2b-2c"}}) \
        == {"Left": {2}, "Right": {1, 2}}


# ================================================================================================
# From test_sensing_rule_first.py (merged here 2026-10-05).
# The readiness card's first sentence says which sensing pair the device allows today, and why a
# count that may have read differently before now reads what it does (panel C item 5; report C §5.3).
#
# WHY. Decision 217 applies the device's sensing rule: while a lead stimulates on a contact, the
# only sensing pair it allows is the two contacts immediately flanking it. On RCS08 (left C+2-,
# right C+1-2-) that leaves L 1-3+ and R 0-3+, and neither has a band that rises with pain, so the
# screen reads 0 of 50. The reason applied to every row at once and was printed only row by row,
# under "why not". It now travels once, on the screen, with the count it explains.
#
# Pinned on the values.
# ================================================================================================


def _cell(ch, hemi, rate, deployable):
    return {"channel": ch, "hemisphere": hemi, "rate_hz": rate, "deployable": deployable}


def test_the_allowed_pair_per_lead_is_named_from_the_rings_in_force():
    blk = BS.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=[], n_screened=50,
                                 n_usable=0)
    assert blk["by_side"]["Left"]["allowed_pair"] == [1, 3]
    assert blk["by_side"]["Right"]["allowed_pair"] == [0, 3]
    assert blk["by_side"]["Left"]["allowed_channel"] == "ONE_THREE_LEFT"
    assert blk["by_side"]["Right"]["allowed_channel"] == "ZERO_THREE_RIGHT"


def test_the_sentence_names_both_pairs_and_the_count_it_explains():
    cells = [_cell("ONE_THREE_LEFT", "Left", 55.0, False),
             _cell("ZERO_THREE_RIGHT", "Right", 55.0, False),
             _cell("ZERO_THREE_LEFT", "Left", 125.0, False)]
    blk = BS.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                 n_usable=0)
    s = blk["sentence"]
    assert "one sensing pair per lead" in s
    assert "0 of 50" in s
    assert "neither" in s.lower()
    assert blk["by_side"]["Left"]["n_usable_on_allowed_pair"] == 0


def test_a_lead_on_an_end_contact_allows_no_pair_and_says_so():
    blk = BS.sensing_rule_block({"Left": {0}, "Right": {1, 2}}, cells=[], n_screened=50,
                                 n_usable=0)
    assert blk["by_side"]["Left"]["allowed_pair"] is None
    assert "nothing flanks" in blk["by_side"]["Left"]["why"]


def test_a_lead_with_no_setting_in_force_applies_no_rule_and_says_so():
    blk = BS.sensing_rule_block({"Left": set(), "Right": {2}}, cells=[], n_screened=10,
                                 n_usable=0)
    assert blk["by_side"]["Left"]["allowed_pair"] is None
    assert blk["by_side"]["Left"]["rule_applied"] is False


def test_a_usable_allowed_pair_is_counted():
    cells = [_cell("ONE_THREE_LEFT", "Left", 55.0, True),
             _cell("ONE_THREE_LEFT", "Left", 110.0, True)]
    blk = BS.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                 n_usable=2)
    assert blk["by_side"]["Left"]["n_usable_on_allowed_pair"] == 2
    assert "2 of 50" in blk["sentence"]


# ================================================================================================
# From test_sensing_rule_one_home.py (merged here 2026-10-05).
# The Stim Optimizer's names for the device's sensing rule are delegations to its one home,
# `DecodeCommon.sensing_rule` (moved there 2026-09-26 so the Biomarkers heat maps, which may not
# import the Stim Optimizer, state the same rule). Every existing caller keeps its import; the
# answer is the DecodeCommon function's, the same object where the signature is unchanged.
# ================================================================================================


def test_the_old_names_are_the_one_homes_functions():
    assert BS.stim_rings is SR.stim_rings
    assert EV.flanking_pair is SR.flanking_pair
    assert EV.pair_flanks_stimulation is SR.pair_flanks_stimulation
    assert EV.sensing_pair_rings is SR.sensing_pair_rings
    assert TP.stim_rings_for_sensing_pair is SR.stim_rings_for_sensing_pair


def test_the_readiness_block_is_the_one_homes_block_with_the_pages_labels():
    cells = [{"channel": "ONE_THREE_LEFT", "deployable": True}]
    got = BS.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                n_usable=1)
    want = SR.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                 n_usable=1,
                                 display_of=lambda ch: BS.sensing_display(ch).get("display_short"))
    assert got == want
    assert got["by_side"]["Left"]["allowed_display"] == "L 1⁻3⁺"
