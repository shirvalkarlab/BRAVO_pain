"""The device's ranges have one home, `DecodeCommon.device_ranges`, and Biomarkers reads them there.

- The 8-30 Hz adaptive-sensing band range, `ADAPTIVE_LFP_BAND_HZ` (item P-15, 2026-09-25). It had
  been typed three times: `bravo_service.ADAPTIVE_LO_HZ`/`ADAPTIVE_HI_HZ`,
  `analytics.BAND_TIME_SWEEP_CENTER_LO_HZ`/`_HI_HZ`, and StimOptimizer's own copy (pinned by
  `StimOptimizer/tests/test_device_ranges_one_home.py`; Biomarkers may not import StimOptimizer,
  decision 168).
- The device's documented timing ranges on the band-by-length sweep response, so the page can say
  which lengths of signal are an averaging window the device can be set to and which are only
  reachable as a held onset (review 2026-09-15, finding B4). The wiring is read off the request
  function's own source; no database.

Merged here 2026-10-05: test_adaptive_band_range_one_home.py, test_band_sweep_device_timing_ranges.py.
"""
import inspect

try:
    from modules.Biomarkers import bravo_service as BS
    from modules.Biomarkers.routines import analytics
    from modules.DecodeCommon import device_ranges as DR
except ImportError:                                              # pragma: no cover
    from Biomarkers import bravo_service as BS
    from Biomarkers.routines import analytics
    from DecodeCommon import device_ranges as DR


def test_the_service_and_the_sweep_adaptive_band_equal_the_decodecommon_tuple():
    for where, got in (("bravo_service", (BS.ADAPTIVE_LO_HZ, BS.ADAPTIVE_HI_HZ)),
                       ("analytics sweep", (analytics.BAND_TIME_SWEEP_CENTER_LO_HZ,
                                            analytics.BAND_TIME_SWEEP_CENTER_HI_HZ))):
        assert got == DR.ADAPTIVE_LFP_BAND_HZ, where
        assert got == (8.0, 30.0), where


def test_the_sweep_response_carries_decodecommons_timing_block_under_device_timing_ranges():
    assert BS._device_timing_ranges() == DR.timing_ranges_for_page()
    src = inspect.getsource(BS.band_time_sweep_for_participant)
    assert '"device_timing_ranges": _device_timing_ranges()' in src
