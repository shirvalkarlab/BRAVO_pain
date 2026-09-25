"""The Percept RC's closed-loop timing ranges, in one home.

Moved here from `StimOptimizer/routines/percept_adaptive.py` on 2026-09-15 (review finding B4) so
the Biomarkers grid can read them: Biomarkers may not import StimOptimizer (StimOptimizer imports
Biomarkers for the tile cache, and the reverse would be a cycle), and the alternative -- typing
"30 s" into the page -- is exactly what the PI refused: "don't default to 30 s just because it's set
now". `percept_adaptive` keeps its names and binds them to these objects; a test pins the identity.

CORRECTED THE SAME EVENING AGAINST THE CLINICIAN TABLET. The PI read the Adaptive Therapy setup
screens on the A610 directly (2026-09-15) and gave this rule: where the tablet deviates from the
manual or the white paper, the manual wins. Parameter by parameter, against
`artifacts/research_2026-09-13_percept_adaptive_parameter_ranges_MANUALS.md`:

- Averaging duration: tablet 0.00 ms to 30.00 s, non-overlapping. The 2020 tip card (p. 8) prints
  0-30 s and the white paper (p. 12) says non-overlapping: AGREES. The tablet screen is the
  adaptive-mode one, which resolves the earlier caveat that the tip card was sensing-era. RCS08's
  device has run 100 ms to 30 s across 572 session reports and never longer.
- Onset duration, upper and lower, Dual Threshold: tablet 0.00 ms to 30.00 s. The white paper and
  the A610 manual print NO range; the FDA summary (P960009/S478 Table 2) prints "0 to 6 min". The
  manual is silent, so the PI's rule picks no winner, and the platform applies what can actually be
  typed: 0-30 s. The FDA figure is kept beside it as a discrepancy, never applied.
- Transition up and down: tablet 2.0 s to 30 min. The white paper's p. 16 sliders read "2.00 secs"
  to "30.00 mins": AGREES. The FDA summary's 250 ms is not on the slider; kept as the FDA figure.
- Detection blanking: tablet 0.00 ms to 30.0 s. No document printed a range; the tablet is the first.
- Sensing blanking (the per-pulse artefact blank, distinct from detection blanking): tablet 0.00 us
  to 2.28 ms; tip card p. 8 "0-2500ms", a unit the manuals report already reads as microseconds.
  They deviate by 220 us, so the manual wins (0-2500 us) and the tablet's figure is recorded.
- High-pass: tablet 1 or 10 Hz. Matches D13 (`constraints.HIGHPASS_OPTIONS_HZ`).
- Adaptive startup delay: not read off the tablet; still the one parameter with no range anywhere.

WHAT THE ONSET IS. It is counted in averaged readings that stay past a threshold (decision 150): it
HOLDS a level, it does not average over it. One device decision therefore spans at most an averaging
window (30 s) plus an onset hold (30 s) -- the hold horizon, 60 s. A grid row longer than that is
beyond anything the device can be set to; a row between 30 s and 60 s is a sustained level the device
can require, not a mean it can compute.
"""

RANGE_SOURCE_FDA = "FDA SSED P960009/S478 (20 Feb 2025), Table 2 'Key aDBS Configurable Parameters', p. 8"
RANGE_SOURCE_TIP_CARD = "Medtronic BrainSense Tip Cards (2020, FIELDPORTAL1594651482409), p. 8"
RANGE_SOURCE_WHITE_PAPER_P16 = "Medtronic BrainSense Adaptive white paper, p. 16 (Advanced Settings sliders)"
RANGE_SOURCE_TABLET = "Clinician tablet (A610), Adaptive Therapy setup screens, read by the PI on 2026-09-15"

#: Onset duration. Applied: the tablet's 0-30 s for both Dual timers (and Single). The FDA summary's
#: "Dual Threshold - 0 to 6 min" is kept beside it and never applied.
ONSET_RANGE_DUAL_MS = (0.0, 30_000.0)
ONSET_RANGE_DUAL_MS_FDA = (0.0, 6.0 * 60_000.0)
ONSET_RANGE_SINGLE_MS = (0.0, 30_000.0)
ONSET_DISCREPANCY = (
    "The FDA summary (P960009/S478, Table 2) prints a Dual Threshold onset range of 0 to 6 min; the "
    "clinician tablet offers 0.00 ms to 30.00 s on both timers, and neither the white paper nor the "
    "A610 manual prints a range. The platform applies the tablet's 30 s, which is what can be typed.")
#: Transition up and transition down: the white paper's slider, 2.00 s to 30.00 min, which the
#: tablet confirms. The FDA summary's "250ms-30 minutes" is kept as the FDA figure.
TRANSITION_RANGE_MS = (2_000.0, 30.0 * 60_000.0)
TRANSITION_RANGE_MS_FDA = (250.0, 30.0 * 60_000.0)
#: Averaging duration: 0 to 30 s, non-overlapping (tip card p. 8; WP p. 12; tablet).
AVERAGING_RANGE_MS = (0.0, 30_000.0)
#: Detection blanking: 0 to 30 s (tablet; no document prints a range).
DETECTION_BLANKING_RANGE_MS = (0.0, 30_000.0)
#: Sensing blanking, microseconds: the tip card's 0-2500 (manual wins); the tablet's 0-2280 recorded.
SENSING_BLANKING_RANGE_US = (0.0, 2_500.0)
SENSING_BLANKING_RANGE_US_TABLET = (0.0, 2_280.0)
#: The two selectable high-pass corners (D13).
HIGHPASS_OPTIONS_HZ = (1.0, 10.0)

#: Adaptive Therapy can be driven by a band inside this range only; outside it, sensing is possible
#: but a change in the signal cannot change stimulation. White paper p. 14 parameter table, "LFP
#: Frequency Range": "8-30Hz (Adaptive) / 1-96Hz (Sensing Only)" (D08; also quoted in
#: `StimOptimizer/routines/percept_adaptive.py`, decision 32). Moved here 2026-09-25 (item P-15):
#: it had been typed separately as `StimOptimizer.routines.percept_adaptive.ADAPTIVE_LFP_BAND_HZ`,
#: `Biomarkers.bravo_service.ADAPTIVE_LO_HZ`/`ADAPTIVE_HI_HZ` and
#: `Biomarkers.routines.analytics.BAND_TIME_SWEEP_CENTER_LO_HZ`/`_HI_HZ`; those names stay for
#: every existing reader and are now bound to this one tuple, pinned by
#: `StimOptimizer/tests/test_device_ranges_one_home.py`.
ADAPTIVE_LFP_BAND_HZ = (8.0, 30.0)

#: One device decision: an averaging window plus an onset hold, in milliseconds.
HOLD_HORIZON_MS = AVERAGING_RANGE_MS[1] + ONSET_RANGE_DUAL_MS[1]

AVERAGING_CAVEAT = (
    "The 0-30 s range is printed in the 2020 BrainSense tip card and was confirmed on the clinician "
    "tablet's Adaptive Therapy setup screen on 2026-09-15 (0.00 ms to 30.00 s, non-overlapping "
    "averages). This participant's device has run averaging from 100 ms to 30 s and never longer.")
ONSET_MEANING = (
    "The onset duration does not average: it holds an averaged reading past a threshold for this long "
    "before the device acts (Dual Threshold, 0 to 30 s on the tablet). A length of signal longer than "
    "the averaging range can only be approximated as a sustained level, not as a mean, and only up to "
    "one averaging window plus one onset hold.")


def timing_ranges_for_page() -> dict:
    """The block a page prints beside a length-of-signal axis: seconds, sources, the hold horizon,
    and the sentences a reader needs to interpret the tiers. JSON-able."""
    return {
        "averaging_s": [AVERAGING_RANGE_MS[0] / 1000.0, AVERAGING_RANGE_MS[1] / 1000.0],
        "averaging_source": RANGE_SOURCE_TIP_CARD,
        "averaging_caveat": AVERAGING_CAVEAT,
        "onset_dual_s": [ONSET_RANGE_DUAL_MS[0] / 1000.0, ONSET_RANGE_DUAL_MS[1] / 1000.0],
        "onset_source": RANGE_SOURCE_TABLET,
        "onset_note": ONSET_DISCREPANCY,
        "onset_meaning": ONSET_MEANING,
        "hold_horizon_s": HOLD_HORIZON_MS / 1000.0,
    }
