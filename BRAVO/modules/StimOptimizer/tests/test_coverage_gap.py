"""Which (left, right) current pairs the next session has to deliver, named rather than implied.

WHY. The honest-current rule refuses a milliamp number until three checks pass, and on RCS08 the one
stratum that has come close fails only the third: the clinic stream at 55 Hz passes "not flat" and
"beats today's setting", and is short on COVERAGE -- distinct current pairs, each carrying enough
ratings on enough separate days, spanning enough milliamps (decisions 158, 184). The card has been
saying "coverage fails" without saying what would fix it, while `current_coverage` grouped the
epochs by current pair internally and threw that table away.

THE PI'S RULING (2026-09-22, ruling 5 of decision 233): the next session runs at 55 Hz at the
pulse-width pairing IN FORCE, and its data are merged with the 60/160 us record for the analysis
rather than fitted apart. So the gap is computed on the MERGED stratum and the pairs are named for
the pairing that will actually be delivered.

WHAT IS ASSERTED: the per-pair table comes back; a pair short on ratings and a pair short on days are
told apart, because they need different things from a visit; the pairs to add are named, respect the
span the rule needs, and are capped by the safety ceiling; and merging two pulse-width pairings
changes the answer, since that is the whole point of the ruling.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1


def _epochs(rows):
    """(left mA, right mA, reports, days) -> the frame `current_coverage` reads."""
    out = []
    for i, (al, ar, n, days) in enumerate(rows):
        out.append(dict(epoch=float(i), amp_mA_Left=float(al), amp_mA_Right=float(ar), n=float(n),
                        rating_days=tuple(f"2026-01-{d + 1:02d}" for d in range(int(days))),
                        freq_hz=55.0, pw_us_Left=60.0, pw_us_Right=160.0))
    return pd.DataFrame(out)


def test_the_coverage_check_returns_the_pair_table_it_already_builds():
    cov = S1.current_coverage(_epochs([(0.0, 2.5, 6, 2), (1.0, 2.5, 6, 2), (2.0, 2.5, 3, 2),
                                       (3.0, 2.5, 6, 1)]))
    pairs = cov["pairs"]
    assert len(pairs) == 4
    by = {(p["amp_mA_Left"], p["amp_mA_Right"]): p for p in pairs}
    # a pair that qualifies, one short on ratings, one short on days -- told apart, because a visit
    # fixes them differently: more ratings at the same setting, or the same setting on another day
    assert by[(0.0, 2.5)]["qualifies"] is True
    assert by[(2.0, 2.5)]["qualifies"] is False and by[(2.0, 2.5)]["short_of"] == ["ratings"]
    assert by[(3.0, 2.5)]["qualifies"] is False and by[(3.0, 2.5)]["short_of"] == ["days"]
    assert cov["n_pairs"] == 2


def test_the_gap_names_the_pairs_to_add_and_how_many_are_still_needed():
    cov = S1.current_coverage(_epochs([(0.0, 2.5, 6, 2), (1.0, 2.5, 6, 2)]))
    gap = S1.coverage_gap(cov, ceiling_mA={"Left": 4.5, "Right": 4.5}, held_right_mA=2.5)
    assert gap["n_pairs_missing"] == cov["n_pairs_required"] - cov["n_pairs"] == 4
    add = gap["pairs_to_add"]
    have = {(0.0, 2.5), (1.0, 2.5)}
    assert len(add) >= 4
    for p in add:
        assert (p["amp_mA_Left"], p["amp_mA_Right"]) not in have
        assert 0.0 <= p["amp_mA_Left"] <= 4.5 and 0.0 <= p["amp_mA_Right"] <= 4.5
    # together with what the record has, the left side reaches the span the rule needs
    lefts = [p["amp_mA_Left"] for p in add] + [0.0, 1.0]
    assert max(lefts) - min(lefts) >= cov["span_required_mA"]
    # AND, because the right side has never moved here, some pairs move it -- a ladder that holds
    # the other side still can never pass this rule on its own
    assert gap["span_short_on"] == ["Right"]
    assert any(p["amp_mA_Right"] != 2.5 for p in add)
    assert "joint corners" in gap["why"]
    assert "5 ratings" in gap["what_each_pair_needs"] and "2" in gap["what_each_pair_needs"]


def test_the_cheapest_way_is_to_top_up_a_pair_the_record_already_has():
    """Found on the live record, which the constructed fixtures had not shown: at 55 Hz nearly every
    (left, right) pair at the held current HAS been delivered, once, on one day. So the sixth
    qualifying pair comes from repeating a near-miss, not from a setting nobody has tried -- and the
    first version of this module proposed new settings and came back with an empty list."""
    rows = [(0.0, 2.5, 6, 2), (1.6, 1.2, 23, 7)]
    rows += [(x, 2.5, 3, 1) for x in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)]
    cov = S1.current_coverage(_epochs(rows))
    gap = S1.coverage_gap(cov, ceiling_mA={"Left": 4.5, "Right": 4.5}, held_right_mA=2.5)
    assert gap["n_pairs_missing"] >= 1
    ups = gap["pairs_to_top_up"]
    assert ups, "a near-miss on the record is cheaper than a new setting"
    first = ups[0]
    assert first["needs_more_ratings"] == 2 and first["needs_more_days"] == 1
    assert "repeat" in gap["cheapest_way"] and "2 more ratings" in gap["cheapest_way"]
    assert "already has" in gap["cheapest_way"]
    # and nothing proposed is above the ceiling
    assert all(p["amp_mA_Left"] <= 4.5 and p["amp_mA_Right"] <= 4.5 for p in ups)


def test_a_stratum_that_already_passes_asks_for_nothing():
    # Both sides have to move: six pairs that only step the left leave the right's span at zero and
    # the rule still refuses, which is exactly why the session plan carries joint corners.
    rows = [(float(i), 2.5, 6, 2) for i in range(6)] + [(0.0, 3.5, 6, 2), (2.0, 3.5, 6, 2)]
    cov = S1.current_coverage(_epochs(rows))
    assert cov["passes"] is True
    gap = S1.coverage_gap(cov, ceiling_mA={"Left": 4.5, "Right": 4.5}, held_right_mA=2.5)
    assert gap["n_pairs_missing"] == 0 and gap["pairs_to_add"] == []
    assert gap["pairs_to_top_up"] == [] and "already passes" in gap["cheapest_way"]
    assert "already" in gap["why"].lower()


def test_merging_two_pulse_width_pairings_changes_the_gap():
    """The PI's ruling 5: the next session runs at the pairing in force and its data are merged with
    the 60/160 record. Merging is not cosmetic -- it is what decides how many pairs are still
    missing, so the gap must be computed on the merged set and not on either half."""
    at_60_160 = _epochs([(0.0, 2.5, 6, 2), (1.0, 2.5, 6, 2)])
    at_100_150 = _epochs([(2.0, 2.5, 6, 2), (3.0, 2.5, 6, 2)]).assign(pw_us_Left=100.0,
                                                                      pw_us_Right=150.0)
    apart = S1.current_coverage(at_60_160)
    merged = S1.current_coverage(pd.concat([at_60_160, at_100_150], ignore_index=True))
    assert apart["n_pairs"] == 2 and merged["n_pairs"] == 4
    gap_apart = S1.coverage_gap(apart, ceiling_mA={"Left": 4.5, "Right": 4.5}, held_right_mA=2.5)
    gap_merged = S1.coverage_gap(merged, ceiling_mA={"Left": 4.5, "Right": 4.5}, held_right_mA=2.5)
    assert gap_apart["n_pairs_missing"] == 4 and gap_merged["n_pairs_missing"] == 2
    assert len(gap_merged["pairs_to_add"]) >= 2


def test_the_gap_never_proposes_a_current_above_the_ceiling():
    cov = S1.current_coverage(_epochs([(0.0, 1.0, 6, 2)]))
    gap = S1.coverage_gap(cov, ceiling_mA={"Left": 2.0, "Right": 2.0}, held_right_mA=1.0)
    assert all(p["amp_mA_Left"] <= 2.0 for p in gap["pairs_to_add"])
    assert gap["ceiling_mA"]["Left"] == 2.0
    # the ceiling can make the gap unclosable in one session, and that is said rather than hidden
    assert gap["n_pairs_missing"] >= len(gap["pairs_to_add"])
    if len(gap["pairs_to_add"]) < gap["n_pairs_missing"]:
        assert "ceiling" in gap["why"].lower()


if __name__ == "__main__":                              # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
