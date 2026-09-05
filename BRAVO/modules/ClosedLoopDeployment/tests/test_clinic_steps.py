"""The clinic-step exposure window and the per-rate artifact band mask."""
import numpy as np
import pytest

from ClosedLoopDeployment import clinic_steps as CS
# The response function is INJECTED rather than imported by clinic_steps itself, so the
# module does not depend on the scorer and a caller can screen against a different one.
from StimOptimizer.routines import lfp_response as LR


def test_settled_window_takes_the_intersection_of_nominal_and_observed():
    """Neither number alone is safe: across 637 comparable step pairs the sheets' nominal duration
    had a median of 60 s against an observed interval of 98 s, with the observed one SHORTER in 23%
    of steps and more than twice as long in 24%. min() is the only value defensible as delivered."""
    assert CS.settled_window(1000.0, 60.0, 98.0) == (1045.0, 1060.0)
    assert CS.settled_window(1000.0, 98.0, 60.0) == (1045.0, 1060.0)


def test_a_thirty_second_step_has_no_settled_time_at_all():
    """The consequence that drives protocol design: a 30 s step is entirely ramp, so all 169 of
    RCS08's 30 s steps contribute nothing. Returns None rather than an inverted window."""
    assert CS.settled_window(1000.0, 30.0, 200.0) is None
    assert CS.settled_window(1000.0, 45.0, 45.0) is None


def test_one_missing_duration_does_not_void_the_step():
    assert CS.settled_window(1000.0, None, 120.0) == (1045.0, 1120.0)
    assert CS.settled_window(1000.0, 120.0, None) == (1045.0, 1120.0)
    assert CS.settled_window(1000.0, None, None) is None


def test_band_mask_drops_the_stimulation_frequency_and_its_aliases():
    """At 55 Hz the landings are 25, 30, 55, 60, 80 and 85 Hz after folding about Nyquist, so the
    mask must remove bands centred within one band half-width of each."""
    cen = np.arange(2.5, 100.0, 1.0)
    m = CS.amplitude_response_band_mask(55.0, cen)
    for f in (55.5, 54.5, 25.5, 30.5, 85.5):
        assert not m[np.argmin(np.abs(cen - f))], f"{f} Hz should be dropped at 55 Hz"
    for f in (8.5, 10.5, 15.5, 40.5):
        assert m[np.argmin(np.abs(cen - f))], f"{f} Hz should survive at 55 Hz"


def test_the_mask_must_be_built_per_rate_because_pooling_destroys_it():
    """RCS08's ten rates put landings roughly every 5 Hz across the axis. With a 2.5 Hz tolerance
    the union covers essentially everything, which is why this is applied per rate: pooling leaves
    almost nothing and would silently discard the whole analysis."""
    cen = np.arange(2.5, 100.0, 1.0)
    per_rate = CS.amplitude_response_band_mask(55.0, cen).sum()
    pooled = np.logical_and.reduce(
        [CS.amplitude_response_band_mask(r, cen)
         for r in (10., 25., 55., 85., 110., 125., 145., 165., 180.)]).sum()
    # MEASURED, not assumed: 8 of the 98 bands survive the union of all nine rates, against 65 for
    # 55 Hz alone. An earlier draft of this test asserted <= 5 because I had quoted a DIFFERENT
    # statistic in prose (the minimum number of rates keeping any single band, which is 1) as though
    # it were a band count. The test caught it, which is the point of pinning measured values.
    assert per_rate > 60, per_rate
    assert pooled == 8, f"pooling left {pooled} bands; the measured value was 8"
    assert pooled < per_rate / 5


def test_a_missing_or_absurd_rate_disables_the_mask_rather_than_dropping_everything():
    cen = np.arange(2.5, 100.0, 1.0)
    for bad in (None, np.nan, 0.0, -55.0):
        assert CS.amplitude_response_band_mask(bad, cen).all()


def test_the_mask_reuses_the_biomarker_helper_rather_than_reimplementing_it():
    """This project has already had one criterion drift into four copies. Assert the dependency so a
    later refactor that inlines the arithmetic here fails loudly."""
    import inspect
    src = inspect.getsource(CS)
    assert "from Biomarkers.routines.analytics import harmonic_landings_hz" in src
    assert "round(raw / fs)" not in src, "the folding arithmetic has been re-inlined"


def test_the_degeneracy_guard_records_a_stricter_cluster_floor_than_the_run_used():
    """The 2026-09-05 run clustered on 4+ visits and produced zero-width intervals. The constants
    exist so the next run does not repeat it."""
    assert CS.MIN_VISITS_FOR_CLUSTER_ROBUST >= 8
    assert 0 < CS.DEGENERATE_CI_WIDTH_LOG10 < 0.01


# --- the within-visit amplitude-response screen (2026-09-05) ------------------------------------
def _tiles(t_start=0.0, n=400, step=3.0, n_cen=4, seed=0):
    """Evenly spaced tiles, one row per tile, distinct value per centre."""
    rng = np.random.default_rng(seed)
    t = t_start + np.arange(n) * step
    p = rng.normal(10.0, 0.5, size=(n, n_cen))
    return t, p


def test_settled_medians_exclude_the_ramp_and_stop_at_the_window_end():
    """The ramp exclusion has to bite at both ends, or a step's median silently includes the
    transient the sheets warn about (and which the ramp analysis measured still rising at 150 s).
    """
    t, p = _tiles(n=200, step=1.0)
    # one step starting at t=0 with a 100 s window: settled tiles are 45 <= dt < 100
    p[:] = 1.0
    p[(t >= 0) & (t < 45), :] = 99.0          # ramp tiles, must be excluded
    p[(t >= 100), :] = 77.0                   # past the window, must be excluded
    med, cnt, kept = CS.step_settled_medians([0.0], [100.0], t, p)
    assert kept.tolist() == [0]
    assert cnt[0] == 55, cnt[0]               # 45..99 inclusive at 1 s spacing
    assert np.allclose(med, 1.0), med


def test_a_step_with_too_few_settled_tiles_is_dropped_not_imputed():
    t, p = _tiles(n=200, step=1.0)
    # window only 1 s past the ramp -> a single settled tile, below MIN_SETTLED_TILES
    med, cnt, kept = CS.step_settled_medians([0.0], [CS.RAMP_WARNING_S + 1.0], t, p)
    assert kept.size == 0 and med.shape[0] == 0
    # and a window entirely inside the ramp is dropped too
    med2, _, kept2 = CS.step_settled_medians([0.0], [CS.RAMP_WARNING_S - 1.0], t, p)
    assert kept2.size == 0 and med2.shape[0] == 0


def test_tiles_inflate_the_p_value_by_orders_of_magnitude_but_not_the_separation():
    """The real reason the unit is the step, after this test falsified the first one I wrote.

    I originally asserted that tile-level scoring inflates the standardised SEPARATION. It does
    not — a Cohen-style d divides by the pooled within-ARM spread, and an arm contains many steps
    whichever unit is used, so between-step variation dominates the denominator either way. What
    pseudoreplication inflates is the INFERENCE: the same slope, estimated on twenty times as many
    rows with the same clusters, acquires a p-value orders of magnitude smaller.

    Kept as a test rather than deleted because it pins WHICH quantity is at risk. A future reader
    tempted to score tiles directly would otherwise have to rediscover that the separation looks
    fine while the p-value does not.
    """
    rng = np.random.default_rng(1)
    per_step, n_tiles = 12, 20
    rows_t, rows_p, amps, steps = [], [], [], []
    for k in range(2 * per_step):
        amp = 1.0 if k < per_step else 4.0
        level = (2.0 if amp == 1.0 else 1.0) + rng.normal(0, 0.35)   # BETWEEN-step spread
        for j in range(n_tiles):
            rows_t.append(k * 1000.0 + CS.RAMP_WARNING_S + j)
            rows_p.append(level + rng.normal(0, 0.01))               # tiny WITHIN-step spread
            amps.append(amp); steps.append(k)
    tt = np.asarray(rows_t); tp = np.asarray(rows_p)[:, None]
    amp_tile = np.asarray(amps); step_tile = np.asarray(steps)

    med, cnt, kept = CS.step_settled_medians(
        [k * 1000.0 for k in range(2 * per_step)],
        [float(n_tiles + CS.RAMP_WARNING_S + 5)] * (2 * per_step), tt, tp)
    amp_step = np.array([1.0 if k < per_step else 4.0 for k in kept])
    vis_step = np.array([f"v{k % 4}" for k in kept])

    step_rows = CS.within_visit_band_scores({20.0: med[:, 0]}, amp_step, vis_step,
                                            response_fn=LR.assess_response)
    tile_rows = CS.within_visit_band_scores({20.0: tp[:, 0]}, amp_tile,
                                            np.array([f"v{s % 4}" for s in step_tile]),
                                            response_fn=LR.assess_response)
    st, ti = step_rows[0], tile_rows[0]
    assert np.isfinite(st["separation_d"]) and np.isfinite(ti["separation_d"])

    # separation is essentially the same -- within 25% -- so it is NOT the quantity at risk
    ratio = ti["separation_d"] / st["separation_d"]
    assert 0.75 < ratio < 1.25, ("separation should be robust to the unit", ratio)

    # the point estimate is the same too, to the precision the docstring claims (four decimals).
    # Not tighter: the two fits differ at the fifth decimal because the median of an even number of
    # tiles interpolates, so the step-level values are not a strict subset of the tile-level ones.
    assert abs(ti["slope_log_per_mA"] - st["slope_log_per_mA"]) < 1e-4

    # but the tile-level p-value is far smaller on a twentyfold inflated n
    assert ti["n_steps"] == 20 * st["n_steps"], (ti["n_steps"], st["n_steps"])
    assert ti["n_eras"] == st["n_eras"], "the CLUSTER count is unchanged, which is the point"
    assert ti["slope_p"] < st["slope_p"] / 100.0, (ti["slope_p"], st["slope_p"])


def test_arm_bins_round_to_the_declared_width():
    got = CS.amplitude_arm_bins([1.0, 1.2, 1.3, 1.7, 3.4, 3.6], bin_mA=0.5)
    assert np.allclose(got, [1.0, 1.0, 1.5, 1.5, 3.5, 3.5]), got
    with pytest.raises(ValueError):
        CS.amplitude_arm_bins([1.0], bin_mA=0.0)


def test_harmonic_landing_is_reported_but_never_acted_on():
    """The PI's instruction, encoded: proximity to a folded harmonic is a flag on the row, not a
    filter. On RCS08 the two channels responding at the 25 Hz landing move in OPPOSITE directions,
    which an alias cannot produce, so a screen that dropped those bands would have discarded the
    only coherent candidate in the record.
    """
    rng = np.random.default_rng(2)
    n = 60
    amp = np.repeat([1.0, 3.5], n // 2)
    vis = np.array([f"v{i % 5}" for i in range(n)])
    power = {24.5: rng.normal(5.0, 0.3, n), 14.5: rng.normal(5.0, 0.3, n)}
    rows = CS.within_visit_band_scores(power, amp, vis, response_fn=LR.assess_response,
                                       rate_hz=55.0)
    by_c = {r["center_hz"]: r for r in rows}
    assert by_c[24.5]["on_harmonic_landing"] is True      # 5th harmonic folds to 25 Hz
    assert by_c[14.5]["on_harmonic_landing"] is False
    # both bands are still SCORED -- the flag did not remove either
    assert len(rows) == 2
    assert all("slope_log_per_mA" in r for r in rows)


def test_scores_carry_both_the_adjusted_and_unadjusted_slope():
    """Both are reported so the size of the time confound is visible rather than asserted away --
    and because on the chronic record the two disagreed in SIGN, which is how that design was
    caught.
    """
    rng = np.random.default_rng(3)
    n = 80
    amp = np.repeat([1.0, 2.0, 3.0, 4.0], n // 4)
    vis = np.array([f"v{i % 6}" for i in range(n)])
    power = {20.5: np.exp(-0.2 * amp + rng.normal(0, 0.1, n))}
    r = CS.within_visit_band_scores(power, amp, vis, response_fn=LR.assess_response)[0]
    assert np.isfinite(r["slope_log_per_mA"]) and np.isfinite(r["slope_unadjusted"])
    assert r["slope_log_per_mA"] < 0
    assert r["n_eras"] >= 2
