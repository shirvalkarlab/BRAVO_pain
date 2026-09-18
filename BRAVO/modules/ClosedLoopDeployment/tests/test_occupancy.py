"""Synthetic regression fixtures adapted from Prasad8146f069 for occupancy."""
import numpy as np
import pytest

try:
    from modules.ClosedLoopDeployment import occupancy as OC
    from modules.ClosedLoopDeployment import prescription as PR, types as TY
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import occupancy as OC
    from ClosedLoopDeployment import prescription as PR, types as TY

PA = pytest.importorskip("StimOptimizer.routines.percept_adaptive")


# --------------------------------------------------------------------------------------------
# averaged_readings: a known-by-construction re-averaging onto the device clock
# --------------------------------------------------------------------------------------------
def test_averaged_readings_at_native_clock_is_unchanged():
    """When the requested averaging duration equals the tile clock, re-averaging is a no-op:
    every finite reading passes through unchanged."""
    t = np.arange(10) * 3.0
    p = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    out = OC.averaged_readings(t, p, averaging_s=3.0)
    assert out.size == 10
    assert np.allclose(np.sort(out), p)


def test_averaged_readings_averages_two_native_readings_into_one():
    """Two 3 s readings requested onto a 6 s window average to their mean, by construction."""
    t = np.arange(6) * 3.0
    p = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    out = OC.averaged_readings(t, p, averaging_s=6.0)
    assert out.size == 3
    assert np.allclose(out, [15.0, 35.0, 55.0])


def test_averaged_readings_never_averages_across_a_gap():
    """A gap much larger than the median interval starts a new stretch (regrid_stretches' own
    rule); the reading just before the gap and the reading just after it must never land in the
    same averaging window, so a huge single outlier on one side of the gap cannot leak into the
    other side's mean."""
    t1 = np.arange(4) * 3.0                    # 0, 3, 6, 9
    p1 = np.array([100.0, 100.0, 100.0, 100.0])
    t2 = t1[-1] + 3600.0 + np.arange(4) * 3.0   # an hour later: a new stretch
    p2 = np.array([100.0, 100.0, 100.0, 100.0])
    t = np.concatenate([t1, t2])
    p = np.concatenate([p1, p2])
    out = OC.averaged_readings(t, p, averaging_s=12.0)
    # each 4-reading stretch is one 12 s window (4 * 3 s); two stretches, two windows -- not one
    # 8-reading window, which is what averaging across the gap would have produced.
    assert out.size == 2
    assert np.allclose(out, [100.0, 100.0])


def test_averaged_readings_drops_an_all_missing_window():
    """A device-clock cell nothing touches is NaN after regridding; a window built entirely from
    such cells is dropped rather than reported as a reading of zero."""
    t = np.array([0.0, 3.0, 30.0, 33.0])        # a real gap in the middle of one 12 s window
    p = np.array([50.0, 50.0, 50.0, 50.0])
    out = OC.averaged_readings(t, p, averaging_s=12.0)
    # both readings land in windows that also contain missing cells; their means still come
    # through because each window has at least one finite reading.
    assert out.size >= 1
    assert np.all(np.isfinite(out))


# --------------------------------------------------------------------------------------------
# threshold_occupancy: fractions, median, centre, half-width, distance -- all by construction
# --------------------------------------------------------------------------------------------
def test_occupancy_partitions_readings_by_construction():
    """Ten readings built to land exactly 3 above, 5 between, 2 below a known pair."""
    t = np.arange(10) * 3.0
    above = np.array([210.0, 220.0, 230.0])
    between = np.array([150.0, 155.0, 160.0, 165.0, 170.0])
    below = np.array([90.0, 95.0])
    p = np.concatenate([above, between, below])
    out = OC.threshold_occupancy(t, p, upper=200.0, lower=100.0, averaging_s=3.0)
    assert out["available"] is True
    assert out["n_readings"] == 10
    assert out["frac_above"] == pytest.approx(0.3)
    assert out["frac_between"] == pytest.approx(0.5)
    assert out["frac_below"] == pytest.approx(0.2)
    assert out["centre"] == pytest.approx(150.0)
    assert out["half_width"] == pytest.approx(50.0)
    assert out["median_level"] == pytest.approx(np.median(p))
    assert out["distance_from_median"] == pytest.approx(150.0 - np.median(p))


def test_occupancy_upper_and_lower_may_be_given_either_order():
    t = np.arange(6) * 3.0
    p = np.array([50.0, 60.0, 150.0, 155.0, 250.0, 260.0])
    a = OC.threshold_occupancy(t, p, upper=200.0, lower=100.0, averaging_s=3.0)
    b = OC.threshold_occupancy(t, p, upper=100.0, lower=200.0, averaging_s=3.0)
    for key in ("frac_above", "frac_between", "frac_below", "centre", "half_width"):
        assert a[key] == pytest.approx(b[key])


def test_occupancy_flags_a_pair_that_is_a_single_threshold_in_all_but_name():
    """The device's actual programmed pair, 167 / 166 -- a gap of 1 device unit on noise with a
    standard deviation of 30, so essentially none of the readings land between them (this is the
    exact case the synthesis's acceptance text names: 0.3% between and flagged)."""
    rng = np.random.default_rng(2026_09_13)
    t = np.arange(4000) * 3.0
    p = 186.0 + rng.normal(0.0, 30.0, 4000)
    out = OC.threshold_occupancy(t, p, upper=167.0, lower=166.0, averaging_s=3.0)
    assert out["available"] is True
    assert out["frac_between"] < 0.02
    assert out["warning"] is True
    assert "single threshold in all but name" in out["why"]


def test_occupancy_flags_a_pair_centred_well_off_the_median():
    """A pair whose centre sits many half-widths from where the signal actually is: almost every
    reading is on one side, and the centring warning fires even with a fairly wide pair."""
    rng = np.random.default_rng(11)
    t = np.arange(2000) * 3.0
    p = 250.0 + rng.normal(0.0, 20.0, 2000)     # the signal actually sits around 250
    out = OC.threshold_occupancy(t, p, upper=210.0, lower=160.0, averaging_s=3.0)
    # centre = 185, half_width = 25; median ~= 250, so |distance| ~= 65 > 25
    assert out["available"] is True
    assert abs(out["distance_from_median"]) > out["half_width"]
    assert out["warning"] is True
    assert "half-width" in out["why"]


def test_occupancy_names_the_correct_side_when_the_centre_sits_above_the_median():
    """centre (185) > median (~100): the pair's centre is ABOVE the level the signal actually
    occupies, and the sentence must say so, not the opposite."""
    rng = np.random.default_rng(5)
    t = np.arange(2000) * 3.0
    p = 100.0 + rng.normal(0.0, 5.0, 2000)
    out = OC.threshold_occupancy(t, p, upper=210.0, lower=160.0, averaging_s=3.0)
    assert out["distance_from_median"] > 0
    assert "above" in out["why"]
    assert " below the participant" not in out["why"]


def test_occupancy_names_the_correct_side_when_the_centre_sits_below_the_median():
    """centre (185) < median (~250): the pair's centre is BELOW the level the signal actually
    occupies -- the case measured live on the stored L 1-3+ pair at 30 s averaging."""
    rng = np.random.default_rng(6)
    t = np.arange(2000) * 3.0
    p = 250.0 + rng.normal(0.0, 5.0, 2000)
    out = OC.threshold_occupancy(t, p, upper=210.0, lower=160.0, averaging_s=3.0)
    assert out["distance_from_median"] < 0
    assert "below" in out["why"]
    assert " above the participant" not in out["why"]


def test_occupancy_does_not_warn_when_well_placed_and_wide_enough():
    rng = np.random.default_rng(3)
    t = np.arange(2000) * 3.0
    p = 150.0 + rng.normal(0.0, 20.0, 2000)
    out = OC.threshold_occupancy(t, p, upper=200.0, lower=100.0, averaging_s=3.0)
    assert out["available"] is True
    assert out["frac_between"] > 0.6
    assert out["warning"] is False


def test_occupancy_reports_unavailable_with_no_thresholds():
    out = OC.threshold_occupancy(np.arange(5) * 3.0, np.ones(5), upper=None, lower=100.0,
                                 averaging_s=3.0)
    assert out["available"] is False
    assert "no thresholds" in out["reason"]


def test_occupancy_reports_unavailable_with_no_averaging_duration():
    out = OC.threshold_occupancy(np.arange(5) * 3.0, np.ones(5), upper=200.0, lower=100.0,
                                 averaging_s=None)
    assert out["available"] is False
    assert "averaging duration" in out["reason"]


def test_occupancy_reports_unavailable_with_too_few_readings():
    out = OC.threshold_occupancy(np.array([0.0, 3.0]), np.array([150.0, 155.0]), upper=200.0,
                                 lower=100.0, averaging_s=3.0)
    assert out["available"] is False
    assert out["n_readings"] == 2


# --------------------------------------------------------------------------------------------
# occupancy_note / attach_occupancy: the prescription-card wiring, mirroring design_rule_note
# --------------------------------------------------------------------------------------------
def test_occupancy_note_is_none_when_unavailable():
    assert PR.occupancy_note({"available": False, "reason": "x"}) is None
    assert PR.occupancy_note(None) is None


def test_occupancy_note_states_the_payloads_own_sentence():
    payload = OC.threshold_occupancy(np.arange(2000) * 3.0,
                                     167.0 + np.random.default_rng(1).normal(0, 1, 2000),
                                     upper=167.0, lower=166.0, averaging_s=3.0)
    note = PR.occupancy_note(payload)
    assert note == payload["why"]


def test_attach_occupancy_only_touches_the_two_threshold_fields():
    plan = TY.ThresholdPlan(upper=210.579, lower=161.903, capture_amp_low=1.4, capture_amp_high=4.8)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    rng = np.random.default_rng(4)
    t = np.arange(3000) * 3.0
    p = 150.0 + rng.normal(0.0, 60.0, 3000)
    payload = OC.threshold_occupancy(t, p, upper=210.579, lower=161.903, averaging_s=3.0)
    out = PR.attach_occupancy(prescriptions, payload)
    dual = out["modes"][PR.PA.DUAL]
    touched = {f.name for f in dual.fields if f.occupancy_note is not None}
    assert touched == {"Upper LFP threshold", "Lower LFP threshold"}
    for f in dual.fields:
        if f.name not in touched:
            assert f.occupancy_note is None
    single = out["modes"][PR.PA.SINGLE]
    assert all(f.occupancy_note is None for f in single.fields)


def test_attach_occupancy_is_a_no_op_when_nothing_is_available():
    plan = TY.ThresholdPlan(upper=210.579, lower=161.903, capture_amp_low=1.4, capture_amp_high=4.8)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    out = PR.attach_occupancy(prescriptions, {"available": False, "reason": "x"})
    dual = out["modes"][PR.PA.DUAL]
    assert all(f.occupancy_note is None for f in dual.fields)


def test_as_rows_carries_the_occupancy_note_key():
    plan = TY.ThresholdPlan(upper=210.579, lower=161.903, capture_amp_low=1.4, capture_amp_high=4.8)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    dual = prescriptions["modes"][PR.PA.DUAL]
    rows = dual.as_rows()
    assert all("occupancy_note" in r for r in rows)
    assert all(r["occupancy_note"] is None for r in rows)      # nothing attached yet


# Participant-specific provenance and examples are maintained outside source control.
def test_acceptance_device_pair_167_166_is_flagged_near_zero_between():
    rng = np.random.default_rng(20260913)
    t = np.arange(6000) * 3.0
    p = 196.05 + rng.normal(0.0, 76.6, 6000)    # the participant's own measured level and scatter
    out = OC.threshold_occupancy(t, p, upper=167.0, lower=166.0, averaging_s=3.0)
    assert out["frac_between"] < 0.01
    assert out["warning"] is True
