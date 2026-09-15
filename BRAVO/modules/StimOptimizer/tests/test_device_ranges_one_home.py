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
