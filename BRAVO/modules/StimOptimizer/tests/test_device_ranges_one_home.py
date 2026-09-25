"""`percept_adaptive` keeps its range names (constraints.py, prescription.py, timing_plan read them),
but the OBJECTS are DecodeCommon's: one home, so the Biomarkers grid cannot drift from the rules.
Review 2026-09-15, finding B4."""
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
    assert PA.ADAPTIVE_LFP_BAND_HZ == (8.0, 30.0)
