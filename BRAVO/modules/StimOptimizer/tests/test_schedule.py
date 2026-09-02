"""Tests for the in-clinic randomised block schedule."""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import schedule as SCHED

CAND = pd.DataFrame({
    "id": list("ABCDEF"),
    "freq": [55.0, 55.0, 55.0, 165.0, 110.0, 40.0],
    "ampL": [3.5, 4.5, 3.5, 3.5, 3.5, 3.5],
    "ampR": [3.0, 3.0, 1.9, 1.9, 3.0, 3.2],
})


def test_every_setting_appears_exactly_once_per_block():
    """The defining property. If it fails, drift is confounded with setting and the session is
    not analysable as designed."""
    s, spec = SCHED.randomized_block_schedule(CAND, seed=1, n_blocks=3)
    assert len(s) == 18 and spec.n_steps == 18
    for b, g in s.groupby("block"):
        assert sorted(g.setting) == sorted(CAND.id), (b, list(g.setting))


def test_no_setting_on_adjacent_steps():
    """An immediate repeat wastes a wash-in and lets carry-over masquerade as a within-setting
    effect. Checked across block boundaries too, which is where a naive per-block shuffle fails."""
    for seed in range(40):
        s, _ = SCHED.randomized_block_schedule(CAND, seed=seed, n_blocks=3)
        v = list(s.setting)
        assert all(v[i] != v[i + 1] for i in range(len(v) - 1)), (seed, v)


def test_schedule_is_reproducible_from_the_seed_alone():
    """A schedule handed to a clinic must be regenerable exactly, or the session cannot be audited."""
    a, _ = SCHED.randomized_block_schedule(CAND, seed=20260902, n_blocks=3)
    b, _ = SCHED.randomized_block_schedule(CAND, seed=20260902, n_blocks=3)
    assert list(a.setting) == list(b.setting)
    c, _ = SCHED.randomized_block_schedule(CAND, seed=20260903, n_blocks=3)
    assert list(a.setting) != list(c.setting), "different seeds must give different orders"


def test_balance_is_reported_and_near_the_session_midpoint():
    s, spec = SCHED.randomized_block_schedule(CAND, seed=7, n_blocks=3)
    tgt = spec.balance["target"]
    assert tgt == (len(s) + 1) / 2.0
    means = np.array(list(spec.balance["mean_step_index"].values()))
    # With one appearance per block the mean index cannot drift far; a wide spread would mean the
    # blocking failed. Bound is generous but would catch a broken design.
    assert np.abs(means - tgt).max() <= len(CAND) / 2.0 + 1e-9, spec.balance
    assert set(spec.balance["appearances"].values()) == {3}


def test_fill_in_columns_are_present_and_blank():
    """The sheet is filled in by hand; a pre-populated rating column would be a data-integrity
    hazard."""
    s, _ = SCHED.randomized_block_schedule(CAND, seed=2, n_blocks=2)
    for c in ("actual_time_programmed", "nrs_left_leg", "side_effect_none_mild_mod_severe"):
        assert c in s.columns and (s[c] == "").all()


def test_candidate_metadata_is_carried_through():
    s, _ = SCHED.randomized_block_schedule(CAND, seed=3, n_blocks=1)
    row = s[s.setting == "D"].iloc[0]
    assert row.freq == 165.0 and row.ampR == 1.9


def test_single_setting_is_refused_rather_than_silently_degenerate():
    with pytest.raises(ValueError, match="at least 2"):
        SCHED.randomized_block_schedule(CAND.iloc[:1], seed=1)


def test_duplicate_ids_are_refused():
    bad = pd.concat([CAND.iloc[:2], CAND.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        SCHED.randomized_block_schedule(bad, seed=1)


def test_one_block_is_still_a_valid_schedule():
    """Explicitly supported: if a session runs short, whole blocks are dropped and even one
    complete block is analysable."""
    s, spec = SCHED.randomized_block_schedule(CAND, seed=5, n_blocks=1)
    assert len(s) == 6 and spec.n_blocks == 1
    assert sorted(s.setting) == sorted(CAND.id)


# --- safety filter -------------------------------------------------------------------------
ENV = {"Left": (0.0, 4.8), "Right": (0.0, 4.5)}


def test_safety_filter_rejects_above_ceiling_with_a_reason():
    c = CAND.copy()
    c.loc[c.id == "B", "ampL"] = 5.2
    kept, rej = SCHED.safety_filter(c, delivered_envelope=ENV, amp_ceiling=4.9)
    assert list(rej.id) == ["B"] and "ceiling" in rej.iloc[0].reject_reason
    assert "B" not in list(kept.id)


def test_safety_filter_rejects_beyond_what_was_ever_delivered():
    c = CAND.copy()
    c.loc[c.id == "F", "ampR"] = 4.7          # under the 4.9 ceiling but above the 4.5 R envelope
    kept, rej = SCHED.safety_filter(c, delivered_envelope=ENV, amp_ceiling=4.9)
    assert list(rej.id) == ["F"] and "ever delivered" in rej.iloc[0].reject_reason


def test_safety_filter_keeps_everything_inside_both_bounds():
    kept, rej = SCHED.safety_filter(CAND, delivered_envelope=ENV, amp_ceiling=4.9)
    assert len(kept) == len(CAND) and len(rej) == 0
