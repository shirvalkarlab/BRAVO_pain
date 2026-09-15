"""The band-by-length sweep response carries the device's documented timing ranges, from the one
home, so the page can say which lengths of signal are an averaging window the device can be set to
and which are only reachable as a held onset. Review 2026-09-15, finding B4.

Plain asserts; runs in the container. No database: the block is a module-level helper and the
wiring is read off the request function's own source, the way this suite already pins other
response fields.
"""
import inspect

try:
    from modules.Biomarkers import bravo_service as BS
    from modules.DecodeCommon import device_ranges as DR
except ImportError:                                              # pragma: no cover
    from Biomarkers import bravo_service as BS
    from DecodeCommon import device_ranges as DR


def test_the_sweep_response_block_is_decodecommons_block_field_for_field():
    assert BS._device_timing_ranges() == DR.timing_ranges_for_page()


def test_the_request_function_attaches_the_block_under_device_timing_ranges():
    src = inspect.getsource(BS.band_time_sweep_for_participant)
    assert '"device_timing_ranges": _device_timing_ranges()' in src


def test_the_rule_version_moved_so_a_stored_grid_without_the_block_is_never_served():
    assert BS._BAND_SWEEP_RULE_VERSION == "v14_sweep_ends_at_one_minute"
