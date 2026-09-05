"""The clinic-step exposure window and the per-rate artifact band mask."""
import numpy as np
import pytest

from ClosedLoopDeployment import clinic_steps as CS


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
