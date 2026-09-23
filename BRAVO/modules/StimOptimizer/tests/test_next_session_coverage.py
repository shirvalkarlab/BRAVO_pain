"""What the next clinic session must deliver, on the PI's ruling 5 (decision 233; built 2026-09-23).

Ruling 5: the next titration session runs at the rate in force (55 Hz on RCS08) at the pulse-width
pairing IN FORCE, and its ratings are MERGED with the earlier clinic record for the analysis -- the
60/160 us record, the pairing the earlier sessions used. Decision 239 measured that merge live (5 of
6 qualifying current pairs, one more rating at L3/R3 closes it), and no response carried it: the
clinic stream is fitted with the pairings separate, and the page's pooling toggle pools EVERY
pairing at a speed, which is wider than the ruling.

The record pairing is the one holding the most clinic epochs at the rate in force, other than the
pairing in force itself; the answer names it, so a reader can see which record was merged.
"""
import pandas as pd

from StimOptimizer import clinic_pain as CP

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
