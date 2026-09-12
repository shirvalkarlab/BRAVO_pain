"""The clinic-step exposure window and the per-rate artifact band mask."""
import numpy as np
import pytest

# `step_settled_medians` and `amplitude_arm_bins` are read from `within_visit`, which DEFINES
# them, rather than through `clinic_steps`, which used to re-export them. That re-export
# existed only to serve `within_visit_band_scores`, deleted on 2026-09-10; no production code
# ever read those names through `clinic_steps`, checked by grep before the re-export went.
# The behaviour under test is unchanged -- only the module these tests ask for it by.
from ClosedLoopDeployment import clinic_steps as CS
from StimOptimizer.routines import within_visit as WV
# The response function is INJECTED rather than imported by clinic_steps itself, so the
# module does not depend on the scorer and a caller can screen against a different one.
from StimOptimizer.routines import lfp_response as LR


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


# --- the within-visit amplitude-response screen (2026-09-05) ------------------------------------
def _tiles(t_start=0.0, n=400, step=3.0, n_cen=4, seed=0):
    """Evenly spaced tiles, one row per tile, distinct value per centre."""
    rng = np.random.default_rng(seed)
    t = t_start + np.arange(n) * step
    p = rng.normal(10.0, 0.5, size=(n, n_cen))
    return t, p


def test_settled_medians_exclude_the_ramp_and_stop_at_the_window_end():
    """The ramp exclusion has to bite at both ends, or a step's summary silently includes the
    transient.

    KEYED OFF THE OPERATIVE CONSTANT, NOT A LITERAL. This test hardcoded 45 until 2026-09-06, when
    the exclusion was changed to the measured 20 s and the test failed for the right reason -- it
    was pinning the number rather than the behaviour. ``CS.RAMP_WARNING_S`` is NOT the right constant
    to key off either: that records what the clinic sheet claims, which the device's own amplitude
    record shows is three to five times too long.
    """
    excl = WV.RAMP_EXCLUDE_S
    window = excl + 55.0
    t, p = _tiles(n=200, step=1.0)
    p[:] = 1.0
    p[(t >= 0) & (t < excl), :] = 99.0        # inside the exclusion, must be dropped
    p[(t >= window), :] = 77.0                # past the window, must be dropped
    med, cnt, kept = WV.step_settled_medians([0.0], [window], t, p)
    assert kept.tolist() == [0]
    assert cnt[0] == 55, cnt[0]               # excl .. window-1 inclusive at 1 s spacing
    assert np.allclose(med, 1.0), med


def test_a_step_with_too_few_settled_tiles_is_dropped_not_imputed():
    t, p = _tiles(n=200, step=1.0)
    # window only 1 s past the ramp -> a single settled tile, below MIN_SETTLED_TILES
    med, cnt, kept = WV.step_settled_medians([0.0], [WV.RAMP_EXCLUDE_S + 1.0], t, p)
    assert kept.size == 0 and med.shape[0] == 0
    # and a window entirely inside the exclusion is dropped too
    med2, _, kept2 = WV.step_settled_medians([0.0], [WV.RAMP_EXCLUDE_S - 1.0], t, p)
    assert kept2.size == 0 and med2.shape[0] == 0




def test_arm_bins_round_to_the_declared_width():
    got = WV.amplitude_arm_bins([1.0, 1.2, 1.3, 1.7, 3.4, 3.6], bin_mA=0.5)
    assert np.allclose(got, [1.0, 1.0, 1.5, 1.5, 3.5, 3.5]), got
    with pytest.raises(ValueError):
        WV.amplitude_arm_bins([1.0], bin_mA=0.0)




