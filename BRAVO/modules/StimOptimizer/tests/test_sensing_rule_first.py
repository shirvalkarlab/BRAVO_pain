"""The readiness card's first sentence says which sensing pair the device allows today, and why a
count that may have read differently before now reads what it does (panel C item 5; report C §5.3).

WHY. Decision 217 applies the device's sensing rule: while a lead stimulates on a contact, the
only sensing pair it allows is the two contacts immediately flanking it. On RCS08 (left C+2-,
right C+1-2-) that leaves L 1-3+ and R 0-3+, and neither has a band that rises with pain, so the
screen reads 0 of 50. The reason applied to every row at once and was printed only row by row,
under "why not". It now travels once, on the screen, with the count it explains.

Pinned on the values.
"""
from StimOptimizer import bravo_service as SVC


def _cell(ch, hemi, rate, deployable):
    return {"channel": ch, "hemisphere": hemi, "rate_hz": rate, "deployable": deployable}


def test_the_allowed_pair_per_lead_is_named_from_the_rings_in_force():
    blk = SVC.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=[], n_screened=50,
                                 n_usable=0)
    assert blk["by_side"]["Left"]["allowed_pair"] == [1, 3]
    assert blk["by_side"]["Right"]["allowed_pair"] == [0, 3]
    assert blk["by_side"]["Left"]["allowed_channel"] == "ONE_THREE_LEFT"
    assert blk["by_side"]["Right"]["allowed_channel"] == "ZERO_THREE_RIGHT"


def test_the_sentence_names_both_pairs_and_the_count_it_explains():
    cells = [_cell("ONE_THREE_LEFT", "Left", 55.0, False),
             _cell("ZERO_THREE_RIGHT", "Right", 55.0, False),
             _cell("ZERO_THREE_LEFT", "Left", 125.0, False)]
    blk = SVC.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                 n_usable=0)
    s = blk["sentence"]
    assert "one sensing pair per lead" in s
    assert "0 of 50" in s
    assert "neither" in s.lower()
    assert blk["by_side"]["Left"]["n_usable_on_allowed_pair"] == 0


def test_a_lead_on_an_end_contact_allows_no_pair_and_says_so():
    blk = SVC.sensing_rule_block({"Left": {0}, "Right": {1, 2}}, cells=[], n_screened=50,
                                 n_usable=0)
    assert blk["by_side"]["Left"]["allowed_pair"] is None
    assert "nothing flanks" in blk["by_side"]["Left"]["why"]


def test_a_lead_with_no_setting_in_force_applies_no_rule_and_says_so():
    blk = SVC.sensing_rule_block({"Left": set(), "Right": {2}}, cells=[], n_screened=10,
                                 n_usable=0)
    assert blk["by_side"]["Left"]["allowed_pair"] is None
    assert blk["by_side"]["Left"]["rule_applied"] is False


def test_a_usable_allowed_pair_is_counted():
    cells = [_cell("ONE_THREE_LEFT", "Left", 55.0, True),
             _cell("ONE_THREE_LEFT", "Left", 110.0, True)]
    blk = SVC.sensing_rule_block({"Left": {2}, "Right": {1, 2}}, cells=cells, n_screened=50,
                                 n_usable=2)
    assert blk["by_side"]["Left"]["n_usable_on_allowed_pair"] == 2
    assert "2 of 50" in blk["sentence"]
