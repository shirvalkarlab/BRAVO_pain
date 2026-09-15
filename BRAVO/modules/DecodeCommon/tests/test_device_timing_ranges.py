"""The device's documented timing ranges live in ONE home, `DecodeCommon.device_ranges`, so the
Biomarkers grid (which may not import StimOptimizer) and the Stim Optimizer / Closed-Loop rules read
the same numbers and the same sources. Review 2026-09-15, finding B4.

Plain asserts: this file runs on both runners.
"""
try:
    from modules.DecodeCommon import device_ranges as DR
except ImportError:                                              # pragma: no cover
    from DecodeCommon import device_ranges as DR


def test_the_averaging_range_is_the_tip_cards_0_to_30_s_and_says_where_it_comes_from():
    assert DR.AVERAGING_RANGE_MS == (0.0, 30_000.0)
    assert "Tip Cards" in DR.RANGE_SOURCE_TIP_CARD and "2020" in DR.RANGE_SOURCE_TIP_CARD


def test_the_dual_onset_range_is_the_fda_summarys_0_to_6_min():
    assert DR.ONSET_RANGE_DUAL_MS == (0.0, 360_000.0)
    assert "FDA" in DR.RANGE_SOURCE_FDA and "Table 2" in DR.RANGE_SOURCE_FDA


def test_the_page_block_carries_seconds_sources_and_the_sensing_era_caveat():
    """What the grid prints beside its length-of-signal rows. The caveat matters: the 0-30 s range
    is printed in a 2020 sensing-only tip card written before Adaptive Therapy existed on Percept,
    and no document states the adaptive-mode range; RCS08's own device has run 100 ms to 30 s."""
    b = DR.timing_ranges_for_page()
    assert b["averaging_s"] == [0.0, 30.0]
    assert b["averaging_source"] == DR.RANGE_SOURCE_TIP_CARD
    assert "sensing" in b["averaging_caveat"] and "not stated" in b["averaging_caveat"]
    assert b["onset_dual_s"] == [0.0, 360.0]
    assert b["onset_source"] == DR.RANGE_SOURCE_FDA
    # the onset holds an averaged reading past a threshold; it does not average. The page must be
    # able to say that without a reader opening the white paper.
    assert "hold" in b["onset_meaning"].lower()
