"""`percept_adaptive` keeps its range names (constraints.py, prescription.py, timing_plan read them),
but the OBJECTS are DecodeCommon's: one home, so the Biomarkers grid cannot drift from the rules.
Review 2026-09-15, finding B4.

Also the device-constraint values themselves, quoted from the Percept adaptive white paper
(UC202012929dEN).

Merged here 2026-10-05: test_percept_adaptive.py.
"""
try:
    from modules.StimOptimizer.routines import percept_adaptive as PA
    from modules.DecodeCommon import device_ranges as DR
except ImportError:                                              # pragma: no cover
    from StimOptimizer.routines import percept_adaptive as PA
    from DecodeCommon import device_ranges as DR


def test_percept_adaptive_ranges_are_the_decodecommon_objects_not_copies():
    assert PA.AVERAGING_RANGE_MS is DR.AVERAGING_RANGE_MS
    assert PA.ONSET_RANGE_DUAL_MS is DR.ONSET_RANGE_DUAL_MS
    assert PA.ONSET_RANGE_SINGLE_MS is DR.ONSET_RANGE_SINGLE_MS
    assert PA.TRANSITION_RANGE_MS is DR.TRANSITION_RANGE_MS
    assert PA.RANGE_SOURCE_FDA is DR.RANGE_SOURCE_FDA
    assert PA.RANGE_SOURCE_TIP_CARD is DR.RANGE_SOURCE_TIP_CARD
    assert PA.DETECTION_BLANKING_RANGE_MS is DR.DETECTION_BLANKING_RANGE_MS
    assert PA.ONSET_RANGE_DUAL_MS_FDA is DR.ONSET_RANGE_DUAL_MS_FDA
    assert PA.RANGE_SOURCE_TABLET is DR.RANGE_SOURCE_TABLET


def test_adaptive_lfp_band_is_the_decodecommon_object_not_a_copy():
    # Item P-15 (2026-09-25): the 8-30 Hz adaptive-sensing range was typed separately here, in
    # Biomarkers.bravo_service (ADAPTIVE_LO_HZ/ADAPTIVE_HI_HZ) and in
    # Biomarkers.routines.analytics (BAND_TIME_SWEEP_CENTER_LO_HZ/_HI_HZ); all three now bind to
    # this one tuple. The Biomarkers side is pinned separately (Biomarkers may not import
    # StimOptimizer): Biomarkers/tests/test_adaptive_band_range_one_home.py.
    assert PA.ADAPTIVE_LFP_BAND_HZ is DR.ADAPTIVE_LFP_BAND_HZ


# ================================================================================================
# From test_percept_adaptive.py (merged here 2026-10-05): device-constraint values, quoted from the
# Percept adaptive white paper (UC202012929dEN).
# ================================================================================================
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
