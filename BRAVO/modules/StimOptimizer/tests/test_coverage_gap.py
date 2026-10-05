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

Merged here 2026-10-05: test_coverage_counts_occasions.py, test_coverage_days_from_the_store.py, test_next_session_coverage.py (each under its own heading below).
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1

from StimOptimizer import adapter as AD
from StimOptimizer import clinic_pain as CP
from StimOptimizer import current_map_schedule as CMS


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


# -------------------------------------------------------------------------------------------------
# On the response (2026-09-23). Until now `coverage_gap` was built, tested and reached by nothing:
# no response carried it and no card printed it. Each per-rate row whose coverage fails now carries
# the gap beside the coverage numbers the current-map card already prints, with the PI-stated safe
# ceiling and the other side held at its setting in force.
# -------------------------------------------------------------------------------------------------

def _row_for(cov, **kw):
    rs = S1.RateStratum(pw_us_left=100.0, pw_us_right=150.0, rate_hz=55.0, n_epochs=12, fitted=True,
                        x_star=(3.0, 2.5), mu_star=5.0, sd_star=0.5, n_reports_total=40.0,
                        coverage=cov, resolution={"resolved": False, "coverage": cov,
                                                  "flat": {}, "gain": {}, "sentence": "s"})
    return S1._rate_row_numbers(rs, **kw)


def test_a_row_whose_coverage_fails_carries_what_the_next_visit_must_deliver():
    # the two qualifying pairs span only 0.5 mA on the left, so the left is the side to step
    cov = S1.current_coverage(_epochs([(0.0, 2.5, 6, 2), (0.5, 2.5, 6, 2), (3.0, 2.5, 4, 1)]))
    assert cov["passes"] is False
    row = _row_for(cov, ceiling_mA={"Left": 4.5, "Right": 4.5}, held_mA={"Left": 3.0, "Right": 2.5})
    gap = row["coverage_gap"]
    assert gap["stepped_side"] == "Left"
    assert gap["n_pairs_missing"] == cov["n_pairs_required"] - cov["n_pairs"]
    assert gap["cheapest_way"].startswith("repeat L3/R2.5")          # the near-miss, topped up
    assert gap["ceiling_mA"] == {"Left": 4.5, "Right": 4.5}
    assert gap["held_side_mA"] == 2.5, "the held side stays at its setting in force"
    for p in gap["pairs_to_add"]:
        assert p["amp_mA_Left"] <= 4.5 and p["amp_mA_Right"] <= 4.5


def test_when_the_left_already_spans_enough_the_right_is_stepped_and_the_left_held():
    cov = S1.current_coverage(_epochs([(0.0, 2.5, 6, 2), (1.0, 2.5, 6, 2)]))
    gap = _row_for(cov, ceiling_mA={"Left": 4.5, "Right": 4.5},
                   held_mA={"Left": 3.0, "Right": 2.5})["coverage_gap"]
    assert gap["stepped_side"] == "Right"
    assert gap["held_side_mA"] == 3.0


def test_the_ceiling_passed_in_is_the_one_obeyed():
    cov = S1.current_coverage(_epochs([(0.0, 2.5, 6, 2), (1.0, 2.5, 6, 2)]))
    row = _row_for(cov, ceiling_mA={"Left": 2.0, "Right": 4.5}, held_mA={"Left": 1.0, "Right": 2.5})
    for p in row["coverage_gap"]["pairs_to_add"]:
        assert p["amp_mA_Left"] <= 2.0


def test_a_row_that_passes_or_was_not_fitted_carries_no_gap():
    rows = []
    for d in range(6):
        rows.append((float(d) * 0.5, 1.0 + (d % 3) * 0.75, 6, 2))
    cov = S1.current_coverage(_epochs(rows))
    assert cov["passes"] is True, cov
    assert _row_for(cov)["coverage_gap"] is None
    unfitted = S1.RateStratum(pw_us_left=100.0, pw_us_right=150.0, rate_hz=55.0, n_epochs=2,
                              fitted=False, reason="too few epochs")
    assert S1._rate_row_numbers(unfitted)["coverage_gap"] is None


# ================================================================================================
# From test_coverage_counts_occasions.py (merged here 2026-10-05).
# S4 of the 2026-09-15 review (decision 184): the coverage half of the honest-current check counts
# OCCASIONS -- distinct California calendar days with a rating -- for every (left, right) current
# pair, not only ratings. Decision 111 measured that two ratings an hour apart differ by 0.37 points:
# they are close to one observation. Five ratings filed in one afternoon used to satisfy the
# five-report floor exactly as five ratings on five days did.
# ================================================================================================


def _eight_pairs(days_per_pair):
    L = [0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 4.0, 4.0]
    R = [0.0, 4.0, 1.0, 3.0, 0.0, 4.0, 0.0, 4.0]
    days = [tuple(f"2026-01-{d + 1:02d}" for d in range(days_per_pair)) for _ in L]
    return pd.DataFrame({"amp_mA_Left": L, "amp_mA_Right": R, "n": [8] * 8, "rating_days": days})


def test_five_ratings_on_one_day_do_not_make_a_covered_pair():
    one_day = S1.current_coverage(_eight_pairs(1))
    assert one_day["n_pairs"] == 0
    assert one_day["passes"] is False
    assert one_day["days_per_pair_required"] == S1.CURRENT_COVERAGE_MIN_DAYS_PER_PAIR == 2
    two_days = S1.current_coverage(_eight_pairs(2))
    assert two_days["n_pairs"] == 8
    assert two_days["passes"] is True
    assert two_days["min_days_over_pairs"] == 2


def test_two_stretches_at_one_pair_sharing_a_day_count_that_day_once():
    d = pd.DataFrame({"amp_mA_Left": [1.0, 1.0], "amp_mA_Right": [2.0, 2.0], "n": [3, 3],
                      "rating_days": [("2026-01-01", "2026-01-02"), ("2026-01-02",)]})
    cov = S1.current_coverage(d, min_pairs=1, min_span_mA=0.0)
    assert cov["min_days_over_pairs"] == 2      # the union, not 3


def test_a_frame_that_carries_no_days_cannot_pass():
    bare = pd.DataFrame({"amp_mA_Left": [0.0, 4.0, 0.0, 4.0, 2.0, 2.0],
                         "amp_mA_Right": [0.0, 4.0, 4.0, 0.0, 0.0, 4.0], "n": [8] * 6})
    cov = S1.current_coverage(bare)
    assert cov["passes"] is False and cov["days_known"] is False


def test_planned_steps_are_credited_their_hold_days():
    steps = [dict(amp_left_mA=l, amp_right_mA=r, planned_days=5)
             for l in (0.0, 1.0, 2.5, 4.0) for r in (0.0, 1.0, 2.5, 4.0)]
    wtb = CMS.what_this_buys(None, steps, target_reports=5)
    assert wtb["resolution_coverage_would_pass"] is True
    assert wtb["coverage_after_schedule"]["min_days_over_pairs"] == 5
    one_day = [dict(s, planned_days=1) for s in steps]
    assert CMS.what_this_buys(None, one_day, target_reports=5)["resolution_coverage_would_pass"] is False


def test_the_redcap_epochs_carry_their_california_rating_days():
    epochs = pd.DataFrame({"epoch": [0.0], "t_start": [pd.Timestamp("2026-01-01T00:00Z")],
                           "t_end": [pd.Timestamp("2026-01-10T00:00Z")], "dur_h": [216.0],
                           "amp_mA_Left": [1.0], "amp_mA_Right": [1.0], "freq_hz": [55.0],
                           "pw_us_Left": [60.0], "pw_us_Right": [60.0], "open_ended": [True]})
    # 03:00Z on the 2nd is still the 1st in California; 20:00Z on the 2nd is the 2nd
    times = ["2026-01-02T03:00:00Z", "2026-01-02T20:00:00Z", "2026-01-02T21:00:00Z"]
    pro = pd.DataFrame({"nrs": [5.0, 6.0, 7.0]})
    out = AD.attach_pros(epochs, pro, times, items=("nrs",))
    assert int(out["n"].iloc[0]) == 3
    assert tuple(out["rating_days"].iloc[0]) == ("2026-01-01", "2026-01-02")
    assert int(out["n_rating_days"].iloc[0]) == 2


def test_the_clinic_epochs_carry_their_rating_days():
    rows = []
    for i, day in enumerate(("2026-03-04", "2026-03-04", "2026-03-19")):
        rows.append(dict(visit_date=day, setting="clinic", file="f", sha256="x", t_local=None,
                         t_utc=pd.Timestamp(day + "T18:00", tz="UTC") + pd.Timedelta(minutes=i),
                         amp_mA_Left=1.0, amp_mA_Right=0.0, freq_hz=55.0, pw_us_Left=60.0,
                         pw_us_Right=60.0, contacts_raw="c", duration_s=60.0,
                         side_effect_score=0.0, overall=np.nan, head=np.nan, back=np.nan,
                         left_leg=5.0, left_foot=np.nan, right_leg=np.nan, right_foot=np.nan,
                         notes=None, row_index=i))
    ep = CP.epoch_frame_from_steps(pd.DataFrame(rows))
    assert len(ep) == 1
    assert tuple(ep["rating_days"].iloc[0]) == ("2026-03-04", "2026-03-19")
    assert int(ep["n_rating_days"].iloc[0]) == 2


# ================================================================================================
# From test_coverage_days_from_the_store.py (merged here 2026-10-05).
# The coverage check counts the same days whether the matched table was just built or read back
# from the store (found 2026-09-24 while proving the implant-date cutoff).
#
# The table keeps each epoch's rating days as a tuple when built, and Parquet hands them back as a
# numpy array. The check recognised only tuples, lists and sets, so a served table's days read as
# unknown: the observed-days path fell back to adding up per-epoch day counts (a day shared by two
# epochs counted twice: 81 days where the union is 78 on RCS08's L1.6/R1.2) or, on the schedule card,
# to nothing at all (0 days, "does not qualify", for pairs with 16 and 19 real days).
# ================================================================================================


def _frame(as_array):
    days = [("2026-01-01", "2026-01-02"), ("2026-01-02", "2026-01-03")]
    conv = (lambda d: np.array(d, dtype=object)) if as_array else tuple
    return pd.DataFrame(dict(amp_mA_Left=[1.6, 1.6], amp_mA_Right=[1.2, 1.2], n=[5.0, 5.0],
                             rating_days=[conv(d) for d in days], n_rating_days=[2, 2]))


def test_days_read_back_as_arrays_are_the_union_not_a_sum():
    built = S1.current_coverage(_frame(False))
    served = S1.current_coverage(_frame(True))
    assert [p["n_days"] for p in built["pairs"]] == [3.0]
    assert [p["n_days"] for p in served["pairs"]] == [3.0]


def test_served_days_are_not_lost_when_no_count_column_comes_with_them():
    f = _frame(True).drop(columns=["n_rating_days"])
    assert [p["n_days"] for p in S1.current_coverage(f)["pairs"]] == [3.0]


# ================================================================================================
# From test_next_session_coverage.py (merged here 2026-10-05).
# What the next clinic session must deliver, on the PI's ruling 5 (decision 233; built 2026-09-23).
#
# Ruling 5: the next titration session runs at the rate in force (55 Hz on RCS08) at the pulse-width
# pairing IN FORCE, and its ratings are MERGED with the earlier clinic record for the analysis -- the
# 60/160 us record, the pairing the earlier sessions used. Decision 239 measured that merge live (5 of
# 6 qualifying current pairs, one more rating at L3/R3 closes it), and no response carried it: the
# clinic stream is fitted with the pairings separate, and the page's pooling toggle pools EVERY
# pairing at a speed, which is wider than the ruling.
#
# The record pairing is the one holding the most clinic epochs at the rate in force, other than the
# pairing in force itself; the answer names it, so a reader can see which record was merged.
# ================================================================================================

IN_FORCE = {"Left": {"rate_hz": 55.0, "pulse_width_us": 100.0, "amplitude_mA": 3.0},
            "Right": {"rate_hz": 55.0, "pulse_width_us": 150.0, "amplitude_mA": 2.5}}


def _ep(rows):
    out = []
    for i, (rate, pwl, pwr, al, ar, n, days) in enumerate(rows):
        out.append(dict(epoch=float(i), freq_hz=rate, pw_us_Left=pwl, pw_us_Right=pwr,
                        amp_mA_Left=al, amp_mA_Right=ar, n=float(n),
                        rating_days=tuple(f"2026-0{1 + d // 28}-{1 + d % 28:02d}" for d in range(days)),
                        n_rating_days=days))
    return pd.DataFrame(out)


EP = _ep([
    (55.0, 60.0, 160.0, 0.0, 2.5, 6, 2), (55.0, 60.0, 160.0, 1.0, 2.5, 6, 2),     # the record
    (55.0, 60.0, 160.0, 2.0, 3.5, 6, 2), (55.0, 60.0, 160.0, 3.0, 2.5, 4, 1),
    (55.0, 100.0, 150.0, 3.0, 2.5, 3, 1), (55.0, 100.0, 150.0, 2.0, 1.5, 6, 2),   # in force
    (55.0, 140.0, 180.0, 4.0, 4.0, 9, 3),                                          # another pairing
    (110.0, 60.0, 160.0, 1.0, 1.0, 9, 3),                                          # another rate
])


def test_the_merge_is_the_pairing_in_force_and_the_record_pairing_at_the_rate_in_force():
    out = CP.next_session_coverage(EP, IN_FORCE, ceiling_mA={"Left": 4.5, "Right": 4.5})
    assert out["available"] is True
    assert out["rate_hz"] == 55.0
    merged = {(p["pw_us_left"], p["pw_us_right"]) for p in out["pairings_merged"]}
    assert merged == {(100.0, 150.0), (60.0, 160.0)}, "never the third pairing, never another rate"
    assert out["n_epochs"] == 6


def test_it_carries_the_coverage_and_what_the_session_must_deliver():
    out = CP.next_session_coverage(EP, IN_FORCE, ceiling_mA={"Left": 4.5, "Right": 4.5})
    cov = out["coverage"]
    assert cov["passes"] is False
    assert out["gap"]["n_pairs_missing"] == cov["n_pairs_required"] - cov["n_pairs"]
    # L3/R2.5 appears in both pairings (4 + 3 ratings, 1 day): merged, it is one pair short a day
    assert out["gap"]["cheapest_way"].startswith("repeat L3/R2.5")
    assert "ruling 5" in out["sentence"] and "60/160" in out["sentence"]


def test_with_no_other_pairing_at_the_rate_it_says_so_and_uses_the_one_in_force():
    ep = EP[EP["pw_us_Left"] == 100.0].reset_index(drop=True)
    out = CP.next_session_coverage(ep, IN_FORCE, ceiling_mA=None)
    assert [(p["pw_us_left"], p["pw_us_right"]) for p in out["pairings_merged"]] == [(100.0, 150.0)]
    assert "no earlier record" in out["sentence"]


def test_without_a_setting_in_force_it_is_not_available_rather_than_guessed():
    out = CP.next_session_coverage(EP, None, ceiling_mA=None)
    assert out["available"] is False and out["reason"]
