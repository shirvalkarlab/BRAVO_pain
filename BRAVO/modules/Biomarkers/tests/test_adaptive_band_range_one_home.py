"""The device's 8-30 Hz adaptive-sensing band range has one home, `DecodeCommon.device_ranges.
ADAPTIVE_LFP_BAND_HZ` (item P-15, 2026-09-25). It had been typed three times: here in
`bravo_service.ADAPTIVE_LO_HZ`/`ADAPTIVE_HI_HZ`, in `analytics.BAND_TIME_SWEEP_CENTER_LO_HZ`/
`_HI_HZ`, and in `StimOptimizer.routines.percept_adaptive.ADAPTIVE_LFP_BAND_HZ` (pinned separately
by `StimOptimizer/tests/test_device_ranges_one_home.py`, since StimOptimizer is not importable
here: Biomarkers may not import StimOptimizer, decision 168's own rule for `device_ranges.py`).

Plain asserts; runs in the container.
"""
try:
    from modules.Biomarkers import bravo_service as BS
    from modules.Biomarkers.routines import analytics
    from modules.DecodeCommon import device_ranges as DR
except ImportError:                                              # pragma: no cover
    from Biomarkers import bravo_service as BS
    from Biomarkers.routines import analytics
    from DecodeCommon import device_ranges as DR


def test_bravo_service_adaptive_band_equals_the_decodecommon_tuple():
    assert (BS.ADAPTIVE_LO_HZ, BS.ADAPTIVE_HI_HZ) == DR.ADAPTIVE_LFP_BAND_HZ
    assert (BS.ADAPTIVE_LO_HZ, BS.ADAPTIVE_HI_HZ) == (8.0, 30.0)


def test_analytics_band_time_sweep_range_equals_the_decodecommon_tuple():
    got = (analytics.BAND_TIME_SWEEP_CENTER_LO_HZ, analytics.BAND_TIME_SWEEP_CENTER_HI_HZ)
    assert got == DR.ADAPTIVE_LFP_BAND_HZ
    assert got == (8.0, 30.0)
