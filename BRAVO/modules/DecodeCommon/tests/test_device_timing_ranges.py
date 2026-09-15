"""The device's documented timing ranges live in ONE home, `DecodeCommon.device_ranges`, so the
Biomarkers grid (which may not import StimOptimizer) and the Stim Optimizer / Closed-Loop rules read
the same numbers and the same sources. Review 2026-09-15, finding B4; corrected the same evening
against the clinician tablet, which the PI read directly.

THE PI'S RULE (2026-09-15): where the tablet deviates from the manual or the white paper, the manual
wins. Where the manual and the white paper are silent, the tablet is the only statement of what can
be entered.

Plain asserts: this file runs on both runners.
"""
try:
    from modules.DecodeCommon import device_ranges as DR
except ImportError:                                              # pragma: no cover
    from DecodeCommon import device_ranges as DR


def test_the_averaging_range_is_0_to_30_s_confirmed_on_the_adaptive_tablet():
    assert DR.AVERAGING_RANGE_MS == (0.0, 30_000.0)
    assert "Tip Cards" in DR.RANGE_SOURCE_TIP_CARD and "2020" in DR.RANGE_SOURCE_TIP_CARD
    assert "tablet" in DR.RANGE_SOURCE_TABLET.lower() and "2026-09-15" in DR.RANGE_SOURCE_TABLET


def test_the_dual_onset_range_is_the_tablets_0_to_30_s_and_the_fda_figure_is_kept_beside_it():
    """The tablet's Dual onset (upper and lower) reads 0.00 ms to 30.00 s; the FDA summary prints
    0 to 6 min; the white paper and the A610 manual print no range, so the PI's rule picks no
    winner and what can actually be typed is what the platform applies."""
    assert DR.ONSET_RANGE_DUAL_MS == (0.0, 30_000.0)
    assert DR.ONSET_RANGE_DUAL_MS_FDA == (0.0, 360_000.0)
    assert DR.ONSET_RANGE_SINGLE_MS == (0.0, 30_000.0)
    assert "6 min" in DR.ONSET_DISCREPANCY and "FDA" in DR.ONSET_DISCREPANCY


def test_the_transition_range_is_the_white_papers_2_s_to_30_min_which_the_tablet_confirms():
    assert DR.TRANSITION_RANGE_MS == (2_000.0, 1_800_000.0)
    assert DR.TRANSITION_RANGE_MS_FDA == (250.0, 1_800_000.0)
    assert "p. 16" in DR.RANGE_SOURCE_WHITE_PAPER_P16


def test_detection_blanking_has_a_range_now_from_the_tablet():
    assert DR.DETECTION_BLANKING_RANGE_MS == (0.0, 30_000.0)


def test_sensing_blanking_keeps_the_tip_cards_figure_and_records_the_tablets():
    """Tip card: 0-2500 (printed as ms, read as microseconds); tablet: 0.00 us to 2.28 ms. They
    deviate, so the manual wins and the tablet's value is recorded beside it."""
    assert DR.SENSING_BLANKING_RANGE_US == (0.0, 2_500.0)
    assert DR.SENSING_BLANKING_RANGE_US_TABLET == (0.0, 2_280.0)
    assert DR.HIGHPASS_OPTIONS_HZ == (1.0, 10.0)


def test_the_page_block_carries_the_hold_horizon_and_the_resolved_caveat():
    """What the grid prints beside its length-of-signal rows. One device decision spans at most an
    averaging window (30 s) plus an onset hold (30 s): the hold horizon. The sensing-era caveat on
    the averaging range is resolved: the tablet's adaptive setup screen shows the same 0-30 s."""
    b = DR.timing_ranges_for_page()
    assert b["averaging_s"] == [0.0, 30.0]
    assert "confirmed" in b["averaging_caveat"] and "tablet" in b["averaging_caveat"]
    assert b["onset_dual_s"] == [0.0, 30.0]
    assert b["onset_source"] == DR.RANGE_SOURCE_TABLET
    assert "6 min" in b["onset_note"] and "FDA" in b["onset_note"]
    assert b["hold_horizon_s"] == 60.0
    assert "hold" in b["onset_meaning"].lower()
