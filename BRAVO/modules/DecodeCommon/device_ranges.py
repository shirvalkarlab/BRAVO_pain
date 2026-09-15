"""The Percept RC's DOCUMENTED closed-loop timing ranges, in one home.

Moved here from `StimOptimizer/routines/percept_adaptive.py` on 2026-09-15 (review finding B4) so
the Biomarkers grid can read them: Biomarkers may not import StimOptimizer (StimOptimizer imports
Biomarkers for the tile cache, and the reverse would be a cycle), and the alternative -- typing
"30 s" into the page -- is exactly what the PI refused: "don't default to 30 s just because it's set
now". `percept_adaptive` keeps its names and binds them to these objects; a test pins the identity.

WHAT THE SOURCES ACTUALLY SAY, checked 2026-09-15 against
`artifacts/research_2026-09-13_percept_adaptive_parameter_ranges_MANUALS.md` §1.6 and the synthesis:

- Averaging duration: 0 to 30 s. Printed ONCE, in the 2020 BrainSense tip card (p. 8), a
  sensing-era document written before Adaptive Therapy existed on Percept. The FDA summary gives no
  averaging range; the A610 programming guide (2025-02-14) confirms it is adjustable and states no
  range. Whether the adaptive-mode averaging shares the sensing range is not stated anywhere.
  RCS08's own device has run averaging from 100 ms to 30 s across 572 session reports and never
  above -- so 30 s is programmable, and nothing longer has ever been accepted.
- Onset duration: Dual Threshold 0 to 6 min, Single 0 to 30 s (FDA SSED Table 2). The onset is
  counted in averaged readings that stay past a threshold (decision 150): it HOLDS a level, it does
  not average over it. A grid row longer than the averaging range is therefore not an averaging
  window the device can be set to, but a sustained level the device can require through the onset.
- Transitions: 250 ms to 30 min each (FDA SSED Table 2).
"""

RANGE_SOURCE_FDA = "FDA SSED P960009/S478 (20 Feb 2025), Table 2 'Key aDBS Configurable Parameters', p. 8"
RANGE_SOURCE_TIP_CARD = "Medtronic BrainSense Tip Cards (2020, FIELDPORTAL1594651482409), p. 8"

#: Onset duration: "Dual Threshold - 0 to 6 min"; "Single Threshold - 0 to 30 seconds".
ONSET_RANGE_DUAL_MS = (0.0, 6.0 * 60_000.0)
ONSET_RANGE_SINGLE_MS = (0.0, 30_000.0)
#: Transition up and transition down ("Stimulation Ramp Up/Down Duration"): "250ms-30 minutes", each.
TRANSITION_RANGE_MS = (250.0, 30.0 * 60_000.0)
#: Averaging duration: 0 to 30 s (tip card, sensing era). See the module docstring for the caveat.
AVERAGING_RANGE_MS = (0.0, 30_000.0)

AVERAGING_CAVEAT = (
    "The 0-30 s range is printed in a 2020 sensing-era tip card, written before Adaptive Therapy "
    "existed on Percept; whether the adaptive-mode averaging shares it is not stated in any document, "
    "and the FDA summary and the 2025 programming guide give no averaging range at all. This "
    "participant's device has run averaging from 100 ms to 30 s and never longer.")
ONSET_MEANING = (
    "The onset duration does not average: it holds an averaged reading past a threshold for this long "
    "before the device acts (Dual Threshold, 0 to 6 min). A length of signal longer than the averaging "
    "range can only be approximated as a sustained level, not as a mean.")


def timing_ranges_for_page() -> dict:
    """The block a page prints beside a length-of-signal axis: seconds, sources, and the two
    sentences a reader needs to interpret the tiers. JSON-able."""
    return {
        "averaging_s": [AVERAGING_RANGE_MS[0] / 1000.0, AVERAGING_RANGE_MS[1] / 1000.0],
        "averaging_source": RANGE_SOURCE_TIP_CARD,
        "averaging_caveat": AVERAGING_CAVEAT,
        "onset_dual_s": [ONSET_RANGE_DUAL_MS[0] / 1000.0, ONSET_RANGE_DUAL_MS[1] / 1000.0],
        "onset_source": RANGE_SOURCE_FDA,
        "onset_meaning": ONSET_MEANING,
    }
