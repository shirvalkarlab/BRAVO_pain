"""The clinic and at-home testing sheets: the finest stimulation record this study has.

WHY THIS FILE EXISTS. Every amplitude-response estimate in this project was built on the Percept
JSON settings reconstruction, and that reconstruction is blind to what happens inside a session.
The device writes a settings snapshot at session boundaries, not when a clinician turns a knob, so
its 6,605 rows for RCS08 collapse to 1,189 distinct timestamps and 123 exposure epochs whose median
duration is 27.5 hours — 75 of the 123 run longer than a day and the longest spans 89 days. Inside
those epochs the stream shows zero amplitude variation, which looks reassuring until you notice the
reasoning is circular: the epochs are BUILT by detecting changes in that same stream, so they cannot
contain one. What the flatness actually demonstrates is that a 27-hour epoch can sit on top of a
clinic visit in which the amplitude was stepped thirty times, and the device export records none of
it.

The lab's own testing sheets do record it, at one-second resolution. They are therefore the
canonical source for within-visit amplitude, in the same way that the JSON — not the printed session
report — turned out to be canonical for chronic amplitude (see MEGA_HANDOFF on the dual-schema
gotcha). This module holds the provenance, the parsing traps, and the exposure-window rule.

WHAT WAS PARSED (2026-09-05). Google Drive folder "Pain Neuromodulation Lab Master Folder > RCS08 >
Stage 2 > Clinic Testing": 32 files, of which 29 are testing workbooks and 3 are templates plus a
Stage 1 streaming log. All 29 carry a "Stim Testing" tab. Result: 820 timestamped steps over 29
visit dates from 2025-07-30 to 2026-09-02, 624 in clinic and 196 at home, with 40 distinct left and
42 distinct right amplitude levels spanning 0.0-6.0 mA and ten stimulation rates. Against the
chronic stream's 29 levels and 7 rates, that is a different order of resolution.

FIVE PARSING TRAPS, every one of which has already produced a wrong number in this project.

1. Read the WORKBOOK, not a text rendering. The Drive connector's `read_file_content` flattens all
   tabs into one document WITHOUT naming them, silently omits the Stim Testing tab on some sheets,
   and rounds timestamps to the second. Downloading the .xlsx and opening the tab by name gives
   genuine Excel time values at sub-second precision (12:19:06.627000). An early parse of this data
   locked onto whichever table appeared first in the flattened text — the clinical observation
   table on two sheets — and reported 746 steps of unprovable provenance.

2. Orientation is not uniform. Twenty-eight sheets put a header row at row index 10 with columns
   Amp (mA) / Rate (Hz) / PW (us) / Duration (s) / Timestamp. July 2025 is TRANSPOSED: field names
   run down column 0 (AmpInmA, RateInHz, PulseWidthInMicroSeconds, TimeToRunInSeconds) with steps
   across columns, in eight blocks (Left GPi A-D, Right Med Thal A-D).

3. Two header typos that must be tolerated rather than corrected upstream. The 2025-09-04 sheet
   spells its timestamp column "Timastamp", and labels pulse width "PW (ms)" while the values are
   microseconds. Keying on names with a typo-tolerant match recovered 38 steps that were otherwise
   invisible.

4. A bilateral cell means LEFT then RIGHT. Only 22 of 449 amplitude cells carry explicit "L x / R y"
   labels; the rest are bare pairs like "0.0/2.5" or "0.5&2.5". PI ruling 2026-09-05: for BOTH the
   slash and the ampersand form, the value before the separator is the left hemisphere. This is not
   cosmetic — 199 of the 673 steps with both sides populated are asymmetric (29.6%), and the two
   hemispheres have been found to move in opposite directions against left-leg pain, so reversing
   the convention would invert a conclusion rather than blur one. Note also that an inequality
   computed over the raw columns counts NaN != NaN as True and inflates this figure; restrict to
   rows where both values are present.

5. July 2025 keeps its step times in the NOTES tab, not the Stim Testing tab. The Activity column
   holds free text of the form "1.5mA c+2-": the amplitude precedes "mA" and the contacts follow,
   with "OFF" meaning zero. Hemisphere comes from two markers in the same column, "starting on L
   side" at 12:59:49 and "switching over to R side now" at 13:50:24. Its transposed Stim Testing
   rows also run PAST the end of each real block into unrelated content — one continues into a cell
   holding "13:20:02.326000", from which a naive numeric extraction yields an amplitude of 13.0 mA,
   above the device ceiling. Requiring the rate cell to be populated for the same column bounds each
   block correctly.

FOUR RATES APPEAR IN THE SHEETS THAT THE DEVICE EXPORT NEVER RECORDED: 25, 85, 100 and 180 Hz,
against the chronic stream's 10, 55, 110, 125, 130, 145 and 165. The 100 Hz case is in the sheet
itself, not a parser fault (July 2025 records 100.0 Hz for Right Groups C and D at 1.0 and 1.5 mA).
UNRESOLVED and consequential: either those settings were delivered and the export missed them, or
the sheets carry planned values that were never delivered. It cannot be settled from the sheets.
"""
import numpy as np

from Biomarkers.routines.analytics import harmonic_landings_hz, DEVICE_TD_FS_HZ

# -------------------------------------------------------------------------------------------------
# THE EXPOSURE WINDOW
# -------------------------------------------------------------------------------------------------
#: Nominal step duration is NOT what happened. Across 637 comparable step pairs the sheets' own
#: Duration (s) column has a median of 60 s while the observed interval between consecutive
#: timestamps has a median of 98 s; the ratio's median is 1.12 but its 90th percentile is 4.25. In
#: 23% of steps the observed interval is SHORTER than the nominal duration and in 24% it is more
#: than twice as long. Neither number alone is a safe exposure window, so take the intersection.
USE_INTERSECTION_OF_NOMINAL_AND_OBSERVED = True

#: The sheets' own warning, printed in the Stim Testing tab: "*NOTE STIM TAKES 30-45 s TO RAMP UP".
RAMP_WARNING_S = 45.0

#: MEASURED, 2026-09-05, and it contradicts the warning above for artifact-sensitive work. Aligning
#: 13,102 three-second tiles to their step onset across 370 steps and all six sensing channels, then
#: normalising each step to its own first nine seconds:
#:
#:   * At the stimulation frequency (52.5-57.5 Hz bands during 55 Hz stimulation) power tracks
#:     amplitude with the right sign and timing — up on an increase, DOWN within 9-18 s on a
#:     decrease (-0.26 log10), and flat to within 0.016 log10 when the amplitude did not change.
#:   * That rise is a spike CONFINED to the stimulation frequency: peak slope 0.81 log10 per 100 s
#:     at 57.5 Hz against a median of -0.003 in bands away from the harmonic landings.
#:   * It is still climbing at 150 s, reaching +1.16 log10 (a 14-fold rise). Checked against the
#:     obvious composition confound — contributing steps fall from 24 to 6 across the time bins
#:     while the mean increment rises from 1.27 to 2.87 mA — and restricted to the same six steps
#:     present in every bin the curve is still monotone: +0.07, +0.04, +0.10, +0.09, +0.16, +0.48,
#:     +0.92, +1.16.
#:
#: So a 45 s exclusion is sufficient for bands away from the stimulation harmonics and is NOT
#: sufficient for bands near them. Whether the cause is a slower device ramp than documented, a
#: clinician stepping the amplitude up manually over minutes while logging only the final value, or
#: electrode polarisation settling is NOT established, and six steps on two channels cannot settle
#: it. The policy below therefore excludes the affected BANDS rather than extending the time window,
#: because extending the window far enough would discard almost every step.
ARTIFACT_STILL_RISING_AT_S = 150.0

#: Which steps survive. Using min(nominal, observed) minus a 45 s ramp: 563 of 820 steps (69%)
#: retain any settled time at all; EVERY 30 s step is lost (all 169 of them) along with the 10 s and
#: 15 s steps; 60 s steps survive with a median of only 15 s, which is five 3 s tiles; and the total
#: usable settled signal is 16.2 hours, or 19,325 tiles. PRACTICAL CONSEQUENCE for protocol design:
#: a future session that wants amplitude-response data must use 120 s steps or longer, because a
#: 30 s step contributes nothing once the ramp is removed.
TOTAL_SETTLED_HOURS_AT_45S_RAMP = 16.2


def settled_window(t0, nominal_s=None, observed_s=None, ramp_s=RAMP_WARNING_S):
    """The interval during which a step's programmed amplitude can be treated as delivered.

    Returns (lo, hi) in the same units as ``t0`` (Unix epoch seconds), or None when the step has no
    settled time. ``hi`` is ``t0 + min(nominal_s, observed_s)`` for the reason recorded at
    USE_INTERSECTION_OF_NOMINAL_AND_OBSERVED, and ``lo`` is ``t0 + ramp_s``.

    The ramp exclusion is a floor, not a guarantee: see ARTIFACT_STILL_RISING_AT_S. For any estimate
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

      * For the PAIN-biomarker question the landings are advisory. Tested on the RCS08 record
        (2026-09-03), responding bands were not closer to the landings than non-responding ones — at
        110 Hz, 4.52 Hz mean distance for responding against 3.90 Hz for non-responding, i.e.
        slightly FARTHER — so aliasing did not explain the pain associations and bands are flagged
        for review rather than removed.
      * For the AMPLITUDE-RESPONSE question they are exclusionary. Measured 2026-09-05, during an
        amplitude change the power rise is concentrated at the landings by a factor of roughly fifty
        (0.81 log10 per 100 s at the stimulation frequency against -0.003 away from it), because the
        stimulation artifact scales with the current being asked about. A slope estimated at a
        landing is measuring the stimulator, not the brain.

    IMPORTANT: this mask must be built PER RATE. Pooling rates defeats it — RCS08's ten rates put
    landings roughly every 5 Hz across the 2.5-99.5 Hz axis, and with a 2.5 Hz tolerance that covers
    the entire axis and discriminates nothing. Per rate the landings are sparse and specific:
    55 Hz lands at 25, 30, 55 and 85 Hz; 110 Hz at 30, 50, 60 and 80 Hz; 165 Hz at 5, 75, 80, 85
    and 90 Hz.
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
#: YIELD, and it is thin. 563 steps carry a settled window across 28 visits (16.2 h), but only 248
#: of them contain any tiles, giving 446 step-level observations over 20 visits, and the median
#: observation rests on just 5 tiles — a direct consequence of 60 s steps retaining only ~15 s after
#: the ramp. Just 4 strata cleared the minimum: ONE_THREE_LEFT and ZERO_THREE_RIGHT, at 55 and
#: 110 Hz, time-domain source only. Montage-PSD observations existed but no montage stratum had
#: enough visits.
#:
#: RESULT. Inside 7.8-30 Hz and away from the harmonic landings there are 54 cells, of which 20 are
#: resolved and, after removing the degenerate intervals described below, 6 are resolved NEGATIVE
#: and 12 resolved POSITIVE. The negative cells — the direction the Dual Threshold control law
#: requires — are:
#:
#:     ONE_THREE_LEFT   110 Hz  26.5 Hz  beta -0.0656  CI [-0.0754, -0.0558]  16 steps,  5 visits
#:     ONE_THREE_LEFT   110 Hz  24.5 Hz  beta -0.0527  CI [-0.0724, -0.0330]  16 steps,  5 visits
#:     ONE_THREE_LEFT   110 Hz  23.5 Hz  beta -0.0354  CI [-0.0465, -0.0242]  16 steps,  5 visits
#:     ZERO_THREE_RIGHT 110 Hz  14.5 Hz  beta -0.0265  CI [-0.0483, -0.0046]  35 steps,  6 visits
#:     ZERO_THREE_RIGHT 110 Hz  15.5 Hz  beta -0.0198  CI [-0.0340, -0.0055]  35 steps,  6 visits
#:     ONE_THREE_LEFT   110 Hz  14.5 Hz  beta -0.0041  CI [-0.0078, -0.0005]  16 steps,  5 visits
#:
#: units are log10 LSB power per mA. This MATTERS because the earlier between-epoch screen of all
#: 108 channel-by-band cells found the amplitude slope resolved-positive in every one of the 36
#: cells where it resolved and negative in none — so the within-visit design reverses the sign for
#: the candidate band on the candidate channel. It is the design difference that did it, not new
#: data.
#:
#: THREE LIMITS, all of which bound the claim rather than decorate it.
#:
#: 1. THE INTERVALS ARE NOT TRUSTWORTHY AT THESE CLUSTER COUNTS. Every stratum produced at least
#:    one interval of exactly zero width, and 6 of 116 resolved cells have intervals narrower than
#:    0.005 log10 — including two of the eight raw negatives (15.5 Hz at width 0.00024, 25.5 Hz at
#:    0.00418), which are excluded above. This is the same collapse the inference lane documented on
#:    2026-09-04: when clusters barely exceed parameters the cluster-robust variance tends to zero
#:    and manufactures certainty. With 5 to 12 visits per stratum the POINT ESTIMATES are the
#:    finding here and the intervals are indicative only. A wild cluster bootstrap at the visit
#:    level is the correct remedy and has not been run.
#: 2. THE RATE IS WRONG FOR THE CANDIDATE. Every negative cell is at 110 Hz. The candidate
#:    configuration is programmed at 165 Hz, which appears in NO fitted stratum, and rate freezes
#:    once BrainSense sensing is configured. So nothing here licenses 165 Hz, and a D19 decision for
#:    the candidate cannot be taken from these numbers.
#: 3. MULTIPLICITY IS UNCORRECTED AND THE BANDS OVERLAP. 98 centres at 1 Hz spacing with 5 Hz wide
#:    bands share 80% of their content, so the six negative cells are nearer two or three
#:    relationships (a 23.5-26.5 Hz cluster on ONE_THREE_LEFT, a 14.5-15.5 Hz cluster on each
#:    channel) than six independent findings.
MIN_VISITS_FOR_CLUSTER_ROBUST = 8
#: Above which a cluster-robust interval at the visit level starts to be worth quoting. The run
#: described above used 4 and should not have; it is recorded here so the next run does not repeat
#: it. Cells whose interval is narrower than this are degenerate rather than precise:
DEGENERATE_CI_WIDTH_LOG10 = 0.005


# =================================================================================================
# THE WITHIN-VISIT AMPLITUDE-RESPONSE SCREEN
# =================================================================================================
# Promoted out of a scratch script on 2026-09-05, because it is the best-identified design in the
# project and it existed only as a bridge file that the workspace sweep would have removed.
#
# WHY IT IS A DIFFERENT DESIGN RATHER THAN A RE-RUN. The chronic screen reads exposure epochs whose
# amplitude is entangled with calendar time, so era blocking is the only defence against the
# confound, and on RCS08 that defence fails in both directions: the full-record window fails on
# capture DIRECTION in all 18 bands (the arms straddle two programming regimes, so power rises
# across them) and the five-era window fails on capture SEPARATION in 14 of 18 (the amplitude range
# collapses to 1.0 mA). Inside one clinic visit the rate, pulse width and contacts are fixed and the
# whole ladder happens within hours, so there is no time confound to adjust for -- and the measured
# within-visit amplitude span reaches 3.5 mA.
#
# Measured on RCS08 at 55 Hz: 229 steps with a settled window over 19 visits, of which 120 carried
# streaming tiles, giving arms at 1.0 and 3.5 mA and median separation 0.53 to 0.89 per cell. So
# separation stops being the binding constraint, which is what the design was for.

#: Amplitude bin width for forming capture arms, in mA.
#:
#: A JUDGEMENT, and it exists because the programmer steps finely while a capture arm needs rows.
#: On RCS08 a single visit carried 29 distinct amplitude levels across 36 steps, so grouping on the
#: raw level leaves roughly one step per level and no arm reaches MIN_ROWS_PER_ARM. Binning to
#: 0.5 mA is the coarsest grouping that still separates clinically distinct settings, and it is
#: declared rather than buried because it changes which steps are contrasted.
AMP_ARM_BIN_MA = 0.5

#: Minimum settled tiles a step must contribute before its median is used.
#:
#: Two is the arithmetic minimum for a median to mean anything. It is deliberately low: on RCS08 the
#: median step yields only about five settled tiles (roughly fifteen seconds after the ramp
#: exclusion), so a stricter floor discards most of the record. The thinness is a real limitation of
#: the present data and is reported per step as ``n_tiles`` rather than hidden.
MIN_SETTLED_TILES = 2


def step_settled_medians(step_t0, step_window_s, tile_t, tile_power, *,
                         ramp_s=RAMP_WARNING_S, min_tiles=MIN_SETTLED_TILES):
    """One power vector per step: the median across that step's SETTLED tiles.

    THE UNIT IS THE STEP, NOT THE TILE, and this is the load-bearing choice in the whole screen.
    A device capture is a short recording summarised to one number, so the step median is its
    analogue, and a median rather than a mean because a capture window can contain a transient.

    WHAT THE CHOICE ACTUALLY PROTECTS, corrected 2026-09-05 after a test falsified my first
    explanation. I had claimed that tile-level scoring inflates the standardised SEPARATION,
    because the within-arm variance becomes a within-step variance. It does not: measured on a
    construction with a large between-step spread and a small within-step one, separation came out
    2.54 at step level and 2.64 at tile level, a ratio of 1.04, and the slope was identical to four
    decimals at -0.2072. The reason is that a Cohen-style d divides by the pooled within-ARM
    spread, and an arm contains many different steps whichever unit is used, so between-step
    variation dominates the denominator either way.

    What tiles inflate is the INFERENCE. On the same construction the slope p-value went from
    4.7e-54 at step level to 1.7e-63 at tile level — ten orders of magnitude — on an n inflated
    twentyfold from 24 to 480, with the same four visits as clusters. Cluster-robust standard
    errors do not rescue it, because the cluster count is unchanged while the rows inside each
    cluster multiply. So the step median is what keeps the p-value honest, and the separation
    figure would have been trustworthy under either unit.

    ``tile_t`` must be sorted ascending. Returns ``(medians, n_tiles, kept)`` where ``medians`` is
    (n_kept, n_centres), ``n_tiles`` the settled count per kept step, and ``kept`` the indices of
    the steps that contributed.
    """
    t0 = np.asarray(step_t0, dtype=float)
    win = np.asarray(step_window_s, dtype=float)
    tt = np.asarray(tile_t, dtype=float)
    tp = np.asarray(tile_power, dtype=float)
    if t0.shape != win.shape:
        raise ValueError(f"step_t0 {t0.shape} and step_window_s {win.shape} must match")
    if tp.ndim != 2 or tp.shape[0] != tt.size:
        raise ValueError(f"tile_power must be (n_tiles, n_centres) aligned to tile_t "
                         f"({tt.size}); got {tp.shape}")
    if tt.size and np.any(np.diff(tt) < 0):
        raise ValueError("tile_t must be sorted ascending")

    meds, counts, kept = [], [], []
    for i, (a, w) in enumerate(zip(t0, win)):
        if not np.isfinite(a) or not np.isfinite(w) or w <= ramp_s:
            continue
        i0 = int(np.searchsorted(tt, a + ramp_s))
        i1 = int(np.searchsorted(tt, a + w))
        if i1 - i0 < int(min_tiles):
            continue
        meds.append(np.nanmedian(tp[i0:i1, :], axis=0))
        counts.append(i1 - i0)
        kept.append(i)
    if not meds:
        return (np.empty((0, tp.shape[1] if tp.ndim == 2 else 0)),
                np.empty(0, dtype=int), np.empty(0, dtype=int))
    return np.vstack(meds), np.asarray(counts, dtype=int), np.asarray(kept, dtype=int)


def amplitude_arm_bins(amp_mA, bin_mA=AMP_ARM_BIN_MA):
    """Amplitudes rounded to the declared arm bin. See AMP_ARM_BIN_MA for why this is needed."""
    a = np.asarray(amp_mA, dtype=float)
    if not np.isfinite(bin_mA) or bin_mA <= 0:
        raise ValueError(f"bin_mA must be positive and finite, got {bin_mA}")
    return np.round(a / float(bin_mA)) * float(bin_mA)


def within_visit_band_scores(power_by_center, amp_mA, visits, *, response_fn,
                             rate_hz=None, bin_mA=AMP_ARM_BIN_MA):
    """Score every band's amplitude response on within-visit steps.

    ``power_by_center`` maps a band centre in Hz to one power value per step, ``visits`` supplies
    the era AND the cluster — the visit is the repeat unit here, because amplitude varies WITHIN a
    visit, which is precisely what the chronic epochs could not offer and what makes era blocking
    informative rather than absorptive.

    ``rate_hz``, when given, flags each band that contains a folded stimulation harmonic. The flag
    is REPORTED AND NOT ACTED ON. Co-location with a landing is a coincidence until tested: on
    RCS08 the two channels carrying responses at the 25 Hz landing move in OPPOSITE directions with
    p below 1e-3, which an aliased harmonic cannot produce, since the landing is a property of the
    stimulation and the sampling rate and is therefore identical on every sensing channel.
    """
    amp = amplitude_arm_bins(amp_mA, bin_mA)
    vis = np.asarray(visits)
    landings = ([float(d["lands_at_hz"]) for d in harmonic_landings_hz(float(rate_hz), 5.0, 32.5)]
                if rate_hz is not None else [])
    rows = []
    for c in sorted(power_by_center):
        p = np.asarray(power_by_center[c], dtype=float)
        if p.shape != amp.shape:
            raise ValueError(f"band {c}: power {p.shape} does not match amplitude {amp.shape}")
        r = response_fn(p, amp, era=vis, cluster=vis)
        rows.append({
            "center_hz": float(c),
            "on_harmonic_landing": bool([x for x in landings if abs(x - float(c)) <= BAND_HALF_HZ]),
            "responds": r.responds, "direction_ok": r.direction_ok,
            "separation_d": r.separation_d,
            "slope_log_per_mA": r.slope_log_per_mA, "slope_p": r.slope_p,
            "slope_unadjusted": r.slope_unadjusted,
            "amp_low_mA": r.amp_low_mA, "amp_high_mA": r.amp_high_mA,
            "n_low": r.n_low, "n_high": r.n_high, "n_eras": r.n_eras,
            "n_steps": int(amp.size),
        })
    return rows
