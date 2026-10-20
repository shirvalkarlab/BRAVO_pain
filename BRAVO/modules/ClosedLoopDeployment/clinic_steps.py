"""Parse clinic and at-home testing sheets for within-visit stimulation exposure.

Device session-boundary snapshots do not resolve changes inside a clinic visit. Testing sheets
provide the finer-grained record, but their observed timestamps and nominal durations must both
be considered. A flat reconstructed exposure epoch does not prove that no within-visit changes
occurred.

Parsing rules retained from the source review:
* Read the workbook and named tab, not a flattened text rendering.
* Support row-oriented and transposed layouts; bound blocks using populated rate cells.
* Tolerate the timestamp header typo "Timastamp" and verify pulse-width units.
* In bilateral slash or ampersand pairs, the first value is Left (PI rule 2026-09-05).
* Some workbooks place timed amplitude/contact observations in a Notes tab.
* Planned settings and delivered settings are different; missing device coverage cannot
  establish whether a worksheet step occurred.

Participant-specific audit measurements are retained only in private provenance.
"""
import numpy as np

from Biomarkers.routines.analytics import harmonic_landings_hz, DEVICE_TD_FS_HZ

# -------------------------------------------------------------------------------------------------
# THE EXPOSURE WINDOW
# -------------------------------------------------------------------------------------------------
#: Nominal duration and the observed interval to the next step can differ. Neither alone is a
#: safe exposure window, so the operative rule uses their intersection.
USE_INTERSECTION_OF_NOMINAL_AND_OBSERVED = True

#: The sheets' own warning, printed in the Stim Testing tab: "*NOTE STIM TAKES 30-45 s TO RAMP UP".
#:
#: THIS IS A RECORD OF WHAT THE SHEET CLAIMS, NOT A SETTING. It is kept because the claim is on the
#: sheet and a reader needs to be able to see it, and because parsing code may want to compare a
#: step's duration against it. Nothing should use it as an exclusion window.
#:
#: This worksheet warning is not a measured exclusion interval. The operative exclusion is
#: `StimOptimizer.routines.within_visit.RAMP_EXCLUDE_S`; its policy provenance is separate.
RAMP_WARNING_S = 45.0



def settled_window(t0, nominal_s=None, observed_s=None, ramp_s=RAMP_WARNING_S):
    """The interval during which a step's programmed amplitude can be treated as delivered.

    Returns (lo, hi) in the same units as ``t0`` (Unix epoch seconds), or None when the step has no
    settled time. ``hi`` is ``t0 + min(nominal_s, observed_s)`` for the reason recorded at
    USE_INTERSECTION_OF_NOMINAL_AND_OBSERVED, and ``lo`` is ``t0 + ramp_s``.

    The ramp exclusion is a floor, not a guarantee. For any estimate
    that touches the stimulation frequency or its aliases, drop those bands with
    ``amplitude_response_band_mask`` instead of relying on this window.
    """
    cands = [c for c in (nominal_s, observed_s) if c is not None and np.isfinite(c) and c > 0]
    if not cands:
        return None
    hi = float(t0) + min(cands)
    lo = float(t0) + float(ramp_s)
    return (lo, hi) if hi > lo else None


#: Half-width of a scanned band, so a landing within this distance of a centre falls INSIDE the band.
BAND_HALF_HZ = 2.5


def amplitude_response_band_mask(rate_hz, centers_hz, *, tol_hz=BAND_HALF_HZ,
                                 fs=DEVICE_TD_FS_HZ):
    """Boolean mask over ``centers_hz``: True for bands USABLE for amplitude-response work.

    A band is dropped when a harmonic of ``rate_hz`` folds to within ``tol_hz`` of its centre, i.e.
    lands inside the band. Landings come from
    ``Biomarkers.routines.analytics.harmonic_landings_hz`` — deliberately NOT reimplemented here,
    because this project has already had one criterion drift into four copies (see
    StimOptimizer/routines/resolution.py for what that costs).

    WHY THIS IS EXCLUSIONARY HERE WHILE THE SAME LANDINGS ARE ONLY ADVISORY IN THE BIOMARKER SCAN.
    The two modules ask different questions of the same frequencies and the evidence points opposite
    ways, so the difference is deliberate rather than an inconsistency:

      * For the PAIN-biomarker question landings are advisory: flag them for review rather
        than treating proximity alone as proof that an association is an artifact.
      * For the AMPLITUDE-RESPONSE question they are exclusionary: stimulation artifact can
        scale with the current being estimated and contaminate the dose-response slope.

    Build the mask PER RATE. Pooling landings across rates can cover the whole frequency axis
    and remove the specificity of this screen.
    """
    c = np.asarray(centers_hz, dtype=float)
    if rate_hz is None or not np.isfinite(rate_hz) or rate_hz <= 0:
        return np.ones(c.shape, dtype=bool)
    lo, hi = float(np.nanmin(c)) - tol_hz, float(np.nanmax(c)) + tol_hz
    land = [d["lands_at_hz"] for d in harmonic_landings_hz(float(rate_hz), lo, hi, fs=fs)]
    if not land:
        return np.ones(c.shape, dtype=bool)
    d = np.abs(c[:, None] - np.asarray(land, dtype=float)[None, :]).min(axis=1)
    return d > float(tol_hz)


#: The join to spectral tiles was VALIDATED by that same artifact rather than asserted. The sheet
#: clock is clinic wall time and must be localised to America/Los_Angeles before conversion to the
#: Unix epoch seconds the tile cache uses. Two independent checks:
#:
#:   * Coverage against a deliberate clock offset. Clinic steps are minutes long, so a wrong offset
#:     shows up: 22.8% of steps contain at least one tile at zero shift, 4.8% at +1 h, 3.7% at -1 h
#:     and 0.0% at +/-7 h. This is a real test, unlike the same check against the chronic exposure
#:     epochs, which tile the record end to end and therefore return 1.0000 at every shift.
#:   * The artifact as a positive control. An artifact that appears at exactly the stimulation
#:     frequency, at exactly the moment the clinician logged the change, in the direction the change
#:     went, cannot arise from a mis-aligned clock.
JOIN_VALIDATED_BY_ARTIFACT_POSITIVE_CONTROL = True


# -------------------------------------------------------------------------------------------------
# THE WITHIN-VISIT AMPLITUDE-RESPONSE DESIGN, AND WHAT IT RETURNED
# -------------------------------------------------------------------------------------------------
#: WHY A WITHIN-VISIT DESIGN AT ALL. On the chronic record amplitude and calendar time are
#: entangled — amplitude rose over the year while pain fell — so a slope estimated across epochs
#: cannot be read causally, and the module's own actuation_edge says as much in its note
#: ("SCREENING STATISTIC ONLY ... confounded_by = [time, impedance drift, concurrent rate changes]").
#: Inside a single visit that confounding largely disappears: the amplitude is stepped deliberately
#: over minutes, on the same lead, at the same impedance, with the patient in one state.
#:
#: THE DESIGN, run 2026-09-05.
#:   * Unit of observation: the STEP. Tiles inside a step's settled window are reduced to one
#:     median log10 power per band, which makes the step the observation and removes the
#:     within-step autocorrelation that inflated significance earlier in this project.
#:   * Blocking: amplitude and power are de-meaned WITHIN VISIT, so the estimate is a within-visit
#:     contrast and the year-long drift cannot contribute.
#:   * Clustering: on VISIT, the repeated-measures unit.
#:   * Stratification: channel x rate x source label, never pooled — a slope on the device's own
#:     onboard spectrum and a slope on our Welch transform are estimates of different quantities.
#:   * Bands: those within BAND_HALF_HZ of a landing for THAT rate are dropped, per
#:     amplitude_response_band_mask.
#:
#: Participant-specific yield, fitted slopes and configuration observations are private.
#: Interpret sparse-cluster confidence intervals cautiously: when cluster counts barely exceed
#: the fitted parameter count, robust variance can collapse. A visit-level wild cluster
#: bootstrap is a possible remedy and must be reported explicitly when actually performed.
#: Results at one stimulation rate do not license a candidate at a different rate.
#: 3. MULTIPLICITY IS UNCORRECTED AND THE BANDS OVERLAP. 98 centres at 1 Hz spacing with 5 Hz wide
#:    bands share 80% of their content, so the six negative cells are nearer two or three
#:    relationships (a 23.5-26.5 Hz cluster on ONE_THREE_LEFT, a 14.5-15.5 Hz cluster on each
#:    channel) than six independent findings.
MIN_VISITS_FOR_CLUSTER_ROBUST = 8
#: Above which a cluster-robust interval at the visit level starts to be worth quoting. The run
#: described above used 4 and should not have; it is recorded here so the next run does not repeat
#: it. Cells whose interval is narrower than this are degenerate rather than precise:
DEGENERATE_CI_WIDTH_LOG10 = 0.005
# `within_visit_band_scores` WAS HERE AND WAS DELETED ON 2026-09-10, BY THE PI'S DECISION AFTER
# SEEING WHAT IT ACTUALLY SAID. It scored every band across within-visit amplitude steps using the
# visit as both era and cluster -- a third grouping of the same raw pairs the per-run amplitude table
# and the pooled-across-visits table already treat two other ways. Everything it computed existed in
# wired code: the harmonic-landing flag through `three_source_response` and `analytics`, the slope
# and separation through `lfp_response`. Only its grouping was its own.
#
# The historical audit results remain private. This grouping had no production caller and no
# decision protecting it; its removal preserves the wired amplitude and pooled response paths.
#
# The lesson kept rather than the code: a third statistical grouping is only worth its maintenance
# if somebody reads it. This one was written, tested, proven, and reached by nothing for months.

