"""Device-constraint tests. Values are quoted from the Percept adaptive white paper (UC202012929dEN)."""
from StimOptimizer.routines import percept_adaptive as PA


def test_adaptive_band_is_8_to_30_hz_and_sensing_only_is_wider():
    assert PA.ADAPTIVE_LFP_BAND_HZ == (8.0, 30.0)
    assert PA.SENSING_ONLY_LFP_BAND_HZ == (1.0, 96.0)


def test_dual_is_minutes_and_single_is_milliseconds():
    """The two modes differ by four orders of magnitude in reaction speed, which is the whole basis
    for choosing between them."""
    d, s = PA.MODES[PA.DUAL], PA.MODES[PA.SINGLE]
    assert d.transition_up_ms == 150_000.0 and d.transition_down_ms == 300_000.0
    assert s.transition_up_ms == 250.0 and s.transition_down_ms == 250.0
    assert d.onset_duration_ms == 1200.0 and s.onset_duration_ms == 200.0
    assert d.detection_blanking_ms == 2000.0 and s.detection_blanking_ms == 550.0
    assert d.fft_size_points == 256 and s.fft_size_points == 64
    assert d.fft_update_rate_hz == 5.0 and s.fft_update_rate_hz == 20.0

