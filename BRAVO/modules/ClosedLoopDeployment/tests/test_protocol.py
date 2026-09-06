"""Tests for the titration session generator and its power calculation.

Two things are load-bearing and both are tested directly rather than through the plan's summary
fields: that the randomisation actually happens and is reproducible from the recorded seed, because
the randomisation is the whole reason the session is worth running; and that the power calculation
reproduces the plan's stated target, because that number is what a clinician will use to decide
whether the visit is worth booking.
"""
import numpy as np
import pytest
from scipy import stats

from ClosedLoopDeployment import protocol, types
from StimOptimizer.routines import percept_adaptive


FOUR = [
    {"label": "ONE_THREE_LEFT@165", "test_amp_mA": 4.8, "ref_amp_mA": 2.4},
    {"label": "ZERO_THREE_RIGHT@110", "test_amp_mA": 2.0, "ref_amp_mA": 1.1},
    {"label": "ZERO_TWO_LEFT@55", "test_amp_mA": 3.0, "ref_amp_mA": 1.5},
    {"label": "ONE_THREE_LEFT@110", "test_amp_mA": 4.0, "ref_amp_mA": 2.4},
]


# --------------------------------------------------------------------------------------------
# The power calculation
# --------------------------------------------------------------------------------------------
def test_the_stated_target_is_reproduced_eighty_percent_at_d_1_28_across_four_configurations():
    """The plan's stated target: 80 percent power for a paired d of 1.28 with the alpha divided
    across four Bonferroni-corrected configurations. Ten pairs reproduces it to within a third of a
    percentage point at 0.797, which is what the design was sized against, but it is BELOW the
    target and not at it. Eleven is the smallest number of blocks that actually reaches 80 percent,
    which is why DEFAULT_N_PAIRS is eleven; the near miss at ten is asserted here so nobody
    reinstates the round number on the strength of it looking close enough."""
    at_ten = protocol.paired_power(10, 1.28, alpha=0.05, n_comparisons=4)
    assert at_ten == pytest.approx(0.797, abs=0.002)
    assert at_ten < 0.80
    assert protocol.paired_power(9, 1.28, alpha=0.05, n_comparisons=4) == pytest.approx(0.719,
                                                                                        abs=0.002)
    assert protocol.paired_power(11, 1.28, alpha=0.05, n_comparisons=4) == pytest.approx(0.856,
                                                                                         abs=0.002)
    smallest = min(n for n in range(2, 40)
                   if protocol.paired_power(n, 1.28, alpha=0.05, n_comparisons=4) >= 0.80)
    assert smallest == 11
    assert protocol.DEFAULT_N_PAIRS == 11
    assert protocol.DEFAULT_D_TARGET == 1.28


def test_the_default_session_meets_the_target_rather_than_approaching_it():
    """The default plan must not state a power below the target it is sized for."""
    p = protocol.titration_plan(FOUR, seed=99)
    assert p.n_pairs == 11
    assert p.power >= 0.80


def test_the_noncentral_t_is_used_and_the_normal_approximation_would_have_overstated_the_power():
    """Not a stylistic preference. At ten degrees of freedom under a fourfold Bonferroni
    correction, treating the statistic as normal reports 96 percent power where the exact
    calculation gives 86, which is the difference between a session a reader would call comfortably
    powered and one that is adequately powered."""
    n, d, a, k = 11, 1.28, 0.05, 4
    exact = protocol.paired_power(n, d, alpha=a, n_comparisons=k)
    z = stats.norm.ppf(1.0 - (a / k) / 2.0)
    normal_approx = float(stats.norm.sf(z - d * np.sqrt(n)) + stats.norm.cdf(-z - d * np.sqrt(n)))
    assert normal_approx > exact + 0.05
    assert stats.t.ppf(1.0 - (a / k) / 2.0, n - 1) > z      # the critical value is the reason


def test_power_rises_with_pairs_and_with_effect_size_and_falls_with_correction():
    assert (protocol.paired_power(6, 1.28, n_comparisons=4)
            < protocol.paired_power(10, 1.28, n_comparisons=4)
            < protocol.paired_power(20, 1.28, n_comparisons=4))
    assert (protocol.paired_power(10, 0.5, n_comparisons=4)
            < protocol.paired_power(10, 1.28, n_comparisons=4)
            < protocol.paired_power(10, 2.0, n_comparisons=4))
    assert (protocol.paired_power(10, 1.28, n_comparisons=8)
            < protocol.paired_power(10, 1.28, n_comparisons=4)
            < protocol.paired_power(10, 1.28, n_comparisons=1))


def test_a_null_effect_gives_back_the_corrected_alpha():
    """Both tails are counted, so power at d = 0 must equal the corrected significance level. If it
    returned zero instead, the function would be dropping a tail somewhere."""
    assert protocol.paired_power(10, 0.0, alpha=0.05, n_comparisons=4) == pytest.approx(0.05 / 4)
    assert protocol.paired_power(10, 0.0, alpha=0.05, n_comparisons=1) == pytest.approx(0.05)


def test_the_power_function_refuses_inputs_that_have_no_answer():
    with pytest.raises(ValueError, match="n_pairs must be at least 2"):
        protocol.paired_power(1, 1.28)
    with pytest.raises(ValueError, match="alpha must lie strictly between"):
        protocol.paired_power(10, 1.28, alpha=1.0)
    with pytest.raises(ValueError, match="n_comparisons must be at least 1"):
        protocol.paired_power(10, 1.28, n_comparisons=0)


def test_detectable_d_inverts_the_power_function():
    """Reported on the plan so a session that misses its target still says what it CAN detect."""
    for n, k in ((10, 4), (6, 4), (20, 1)):
        d = protocol.detectable_d(n, 0.80, alpha=0.05, n_comparisons=k)
        assert d is not None
        assert protocol.paired_power(n, d, alpha=0.05, n_comparisons=k) == pytest.approx(0.80,
                                                                                        abs=1e-4)
    # More pairs must be able to detect a smaller effect.
    assert protocol.detectable_d(20, 0.80, n_comparisons=4) < protocol.detectable_d(
        10, 0.80, n_comparisons=4)


# --------------------------------------------------------------------------------------------
# Reproducibility of the randomisation
# --------------------------------------------------------------------------------------------
def test_a_fixed_seed_reproduces_the_session_exactly():
    """An unauditable allocation would undermine the only thing this session buys over the
    historical record, so the plan must be reconstructible from its recorded seed."""
    a = protocol.titration_plan(FOUR, n_pairs=10, seed=20260904)
    b = protocol.titration_plan(FOUR, n_pairs=10, seed=20260904)
    assert a.seed == b.seed == 20260904
    assert a.steps == b.steps
    assert a.duration_min == b.duration_min and a.power == b.power


def test_a_seed_is_drawn_and_recorded_when_none_is_given():
    """A plan generated without a seed is still reproducible after the fact; an unrecorded seed
    would make the randomisation unauditable."""
    p = protocol.titration_plan(FOUR, n_pairs=4, seed=None)
    assert isinstance(p.seed, int)
    again = protocol.titration_plan(FOUR, n_pairs=4, seed=p.seed)
    assert again.steps == p.steps


def test_different_seeds_give_different_orders():
    orders = set()
    for s in range(12):
        p = protocol.titration_plan(FOUR, n_pairs=3, seed=s)
        orders.add(tuple(st["candidate"] for st in p.steps if st["role"] == "test"))
    assert len(orders) > 1


def test_the_candidate_order_actually_varies_between_blocks():
    """This is the confound break. If every block ran the configurations in the same order, the
    session would reproduce the historical record's association between the configuration tested
    and the time it was tested, which is the thing the design exists to remove."""
    p = protocol.titration_plan(FOUR, n_pairs=10, seed=7)
    per_block = {}
    for st in p.steps:
        if st["role"] == "test":
            per_block.setdefault(st["block"], []).append(st["candidate"])
    assert len(per_block) == 10
    assert all(sorted(v) == sorted(c["label"] for c in FOUR) for v in per_block.values())
    assert len({tuple(v) for v in per_block.values()}) > 1


def test_the_within_pair_order_is_randomised_by_default_and_can_be_switched_off():
    """Randomising which arm is measured first spreads any carryover from the preceding amplitude
    across both arms. With it off, the reference always goes first and carryover lands on it."""
    p = protocol.titration_plan(FOUR, n_pairs=10, seed=11)
    first = [st["role"] for st in p.steps if st["role"] in ("reference", "test")][0::2]
    assert set(first) == {"reference", "test"}

    q = protocol.titration_plan(FOUR, n_pairs=10, seed=11, randomise_within_pair=False)
    roles = [st["role"] for st in q.steps if st["role"] in ("reference", "test")]
    assert roles[0::2] == ["reference"] * 40 and roles[1::2] == ["test"] * 40
    assert "carryover" in q.note


# --------------------------------------------------------------------------------------------
# Session structure
# --------------------------------------------------------------------------------------------
def test_the_session_has_one_pair_per_candidate_per_block_plus_a_baseline_per_block():
    p = protocol.titration_plan(FOUR, n_pairs=10, seed=1)
    roles = [st["role"] for st in p.steps]
    assert roles.count("reference") == roles.count("test") == 10 * len(FOUR)
    assert roles.count("baseline") == 10
    assert roles[-1] == "restore"
    for c in FOUR:
        tests = [st for st in p.steps if st["role"] == "test" and st["candidate"] == c["label"]]
        refs = [st for st in p.steps if st["role"] == "reference" and st["candidate"] == c["label"]]
        assert len(tests) == len(refs) == 10
        assert {st["amplitude_mA"] for st in tests} == {c["test_amp_mA"]}
        assert {st["amplitude_mA"] for st in refs} == {c["ref_amp_mA"]}
    assert len({st["pair"] for st in p.steps if st["pair"]}) == 10 * len(FOUR)


def test_the_step_clock_is_contiguous_and_the_duration_is_its_total():
    """A clinician reads the duration to decide whether the session fits a visit, so it has to be
    the sum of the steps actually listed rather than an estimate alongside them."""
    p = protocol.titration_plan(FOUR, n_pairs=10, seed=2)
    t = 0.0
    for st in p.steps:
        assert st["t_start_s"] == pytest.approx(t, abs=0.01)
        assert st["t_end_s"] == pytest.approx(t + st["dwell_s"], abs=0.01)
        t += st["dwell_s"]
    assert p.duration_min == pytest.approx(t / 60.0, abs=0.01)
    assert p.duration_min > 45          # eighty measurements at 45 s cannot fit a short visit
    assert "minutes" in p.note


def test_ramp_steps_are_excluded_from_analysis_and_follow_the_d50_increment_timing():
    """Rule D50 (A610 p. 45): increments of 0.1 to 0.5 mA at intervals of 0.5 to 10 s. A power
    estimate spanning an amplitude change contains signal from both amplitudes, so the ramp cannot
    be analysed."""
    p = protocol.titration_plan([{"label": "c", "test_amp_mA": 2.5, "ref_amp_mA": 0.5}],
                                n_pairs=2, seed=3, step_mA=0.5, ramp_interval_s=2.0)
    ramps = [st for st in p.steps if st["role"] == "ramp"]
    assert ramps and all(st["analysis"] is False for st in ramps)
    assert all("n_integration_windows" not in st for st in ramps)
    # 0.0 -> 2.5 mA is five 0.5 mA increments at 2 s each.
    long_ramp = [st for st in ramps if st["amplitude_mA"] == 2.5 and st["t_start_s"] < 200]
    assert long_ramp and long_ramp[0]["dwell_s"] == pytest.approx(10.0)


def test_measurement_steps_report_their_usable_time_in_integration_windows():
    """Seconds alone hide the difference between a dwell that yields five of the biomarker's own
    integration windows and one that yields eight, and that difference matters more to the estimate
    than the raw seconds suggest."""
    p = protocol.titration_plan(FOUR, n_pairs=2, seed=4, dwell_s=45.0)
    m = next(st for st in p.steps if st["role"] == "test")
    assert m["settle_exclude_s"] == pytest.approx(2.0 * percept_adaptive.BIOMARKER_INTEGRATION_S,
                                                  abs=0.001)
    assert m["usable_s"] == pytest.approx(45.0 - 8.192, abs=0.001)
    assert m["n_integration_windows"] == 8

    short = protocol.titration_plan(FOUR, n_pairs=2, seed=4, dwell_s=30.0)
    assert next(st for st in short.steps
                if st["role"] == "test")["n_integration_windows"] == 5
    assert short.duration_min < p.duration_min


def test_every_step_carries_a_purpose_in_full_sentences():
    p = protocol.titration_plan(FOUR, n_pairs=2, seed=5)
    for st in p.steps:
        assert st["purpose"].strip().endswith(".") and len(st["purpose"]) > 40


def test_the_session_does_not_end_at_a_probe_amplitude():
    p = protocol.titration_plan(FOUR, n_pairs=2, seed=6, return_amp_mA=2.4)
    assert p.steps[-1]["role"] == "restore" and p.steps[-1]["amplitude_mA"] == pytest.approx(2.4)
    q = protocol.titration_plan(FOUR, n_pairs=2, seed=6)
    assert q.steps[-1]["amplitude_mA"] == pytest.approx(FOUR[0]["ref_amp_mA"])
    assert "pass return_amp_mA" in q.steps[-1]["purpose"]


# --------------------------------------------------------------------------------------------
# Device ranges are enforced, not clipped
# --------------------------------------------------------------------------------------------
def test_the_manufacturer_ranges_are_imported_rather_than_retyped():
    assert protocol.RAMP_RANGE_S == percept_adaptive.TITRATION_RAMP_RANGE_S == (0.5, 10.0)
    assert protocol.SETTLE_RANGE_S == percept_adaptive.TITRATION_SETTLE_RANGE_S == (30.0, 45.0)
    assert protocol.INTEGRATION_S == percept_adaptive.BIOMARKER_INTEGRATION_S
    assert protocol.SETTLE_WINDOWS == percept_adaptive.SETTLE_WINDOWS


@pytest.mark.parametrize("kw", [
    {"dwell_s": 20.0},            # below the 30-45 s streaming range
    {"dwell_s": 60.0},            # above it
    {"step_mA": 0.9},             # above the 0.1-0.5 mA increment range
    {"ramp_interval_s": 20.0},    # above the 0.5-10 s ramp interval range
    {"baseline_s": 10.0},         # below the 45-60 s baseline
])
def test_a_parameter_outside_the_d50_range_is_refused_rather_than_clipped(kw):
    """The returned plan is something a clinician may follow at the programmer, so a step list
    containing a value the device does not permit is worse than no plan."""
    with pytest.raises(ValueError, match="outside the manufacturer's permitted range"):
        protocol.titration_plan(FOUR, n_pairs=2, seed=8, **kw)


def test_n_pairs_below_two_is_refused():
    with pytest.raises(ValueError, match="n_pairs must be at least 2"):
        protocol.titration_plan(FOUR, n_pairs=1, seed=8)


# --------------------------------------------------------------------------------------------
# Candidate handling
# --------------------------------------------------------------------------------------------
def test_candidates_may_be_bare_amplitudes_mappings_or_objects():
    class Cand:
        label = "obj"
        amp_mA = 3.3
        ref_amp_mA = 1.1

    p = protocol.titration_plan([2.0, {"name": "m", "amplitude_mA": 1.5, "ref_amp_mA": 0.6},
                                 Cand()], n_pairs=2, seed=9)
    labels = {st["candidate"] for st in p.steps if st["role"] == "test"}
    assert labels == {"cfg1", "m", "obj"}
    # A bare amplitude gets the manufacturer's 0.0 mA baseline as its reference, and the plan says
    # so, because that makes the contrast test-against-off rather than test-against-clinical.
    assert "against stimulation OFF" in p.note.replace("\n", " ")


def test_a_session_level_reference_overrides_the_per_candidate_one():
    p = protocol.titration_plan(FOUR, n_pairs=2, seed=10, reference_amp_mA=1.8)
    refs = {st["amplitude_mA"] for st in p.steps if st["role"] == "reference"}
    assert refs == {1.8}
    # A session-level reference that coincides with any candidate's test amplitude is still
    # refused, because that pair would contrast a setting with itself.
    with pytest.raises(ValueError, match="equal to its test amplitude"):
        protocol.titration_plan(FOUR, n_pairs=2, seed=10, reference_amp_mA=2.0)


def test_candidate_problems_are_refused_with_the_reason():
    with pytest.raises(ValueError, match="nothing to titrate"):
        protocol.titration_plan(None)
    with pytest.raises(ValueError, match="empty"):
        protocol.titration_plan([])
    with pytest.raises(ValueError, match="no test amplitude"):
        protocol.titration_plan([{"label": "x"}], n_pairs=2, seed=1)
    with pytest.raises(ValueError, match="labels are not unique"):
        protocol.titration_plan([{"label": "x", "amp_mA": 1.0}, {"label": "x", "amp_mA": 2.0}],
                                n_pairs=2, seed=1)
    with pytest.raises(ValueError, match="reference amplitude equal to its test amplitude"):
        protocol.titration_plan([{"label": "x", "amp_mA": 1.0, "ref_amp_mA": 1.0}],
                                n_pairs=2, seed=1)
    with pytest.raises(ValueError, match="negative"):
        protocol.titration_plan([-1.0], n_pairs=2, seed=1)


# --------------------------------------------------------------------------------------------
# What the plan says about itself
# --------------------------------------------------------------------------------------------
def test_the_plans_power_matches_the_power_function_at_its_own_candidate_count():
    """The Bonferroni divisor is the number of candidates, because each contributes one comparison
    and the session would otherwise buy significance by testing several at the nominal level."""
    p = protocol.titration_plan(FOUR, n_pairs=11, alpha=0.05, seed=12)
    assert isinstance(p, types.Protocol)
    assert p.power == pytest.approx(protocol.paired_power(11, 1.28, 0.05, n_comparisons=4))
    assert p.power >= 0.80
    assert p.detectable_d == pytest.approx(
        protocol.detectable_d(11, 0.80, 0.05, n_comparisons=4))
    assert "per-comparison alpha of 0.0125" in p.note

    two = protocol.titration_plan(FOUR[:2], n_pairs=11, alpha=0.05, seed=12)
    assert two.power > p.power          # a lighter correction with the same number of blocks


def test_the_note_states_what_the_plan_does_not_establish():
    """A plan that reads like a result is the failure mode here: the power figure is a property of
    the design under its assumptions and is not evidence about this participant."""
    p = protocol.titration_plan(FOUR, n_pairs=10, seed=13)
    note = p.note
    assert "randomisation is the point" in note
    assert "ASSUMPTION" in note and "two eras" in note
    assert "upper bound" in note                    # blocks are not fully independent
    assert "plan and not a result" in note
    assert "no clinical safety review" in note
    assert f"Seed {p.seed}" in note


def test_a_small_session_reports_the_effect_it_can_detect_rather_than_only_missing_the_target():
    p = protocol.titration_plan(FOUR, n_pairs=4, seed=14)
    assert p.power < 0.5
    assert p.detectable_d > protocol.DEFAULT_D_TARGET
    assert "smallest effect this session reaches" in p.note


def test_a_session_too_long_for_a_visit_says_so_instead_of_being_trimmed():
    """The trade between blocks, configurations and dwell belongs to the clinician, so the length is
    reported rather than silently reduced."""
    p = protocol.titration_plan(FOUR, n_pairs=20, seed=15)
    assert p.duration_min > 90
    assert "DOES NOT FIT A ROUTINE VISIT" in p.note
