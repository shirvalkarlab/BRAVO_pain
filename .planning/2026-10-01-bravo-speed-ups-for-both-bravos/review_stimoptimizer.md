# Stim Optimizer page review (RCS08), read-only, tab-2, viewport 1280x900

Not done: no clicks on Make Google sheet; no .xlsx download. No .xlsx button exists on the page (only "Make Google sheet"). The zoom action is not supported in this browser pane, so plot detail was judged from full screenshots. Time cap (15 min) was passed because the first load took about 3 min, so hover/zoom on plots was not tested. Folds were opened by script and by click.

## Broken or doubtful items

- [ ] **First load is about 3 min** (high). Did: opened the URL. Saw: "Loading the settings history and the readiness check, about 10 s" for roughly 2.5 min, then "plan is still being computed" for about 1 more min. Two queryStimOptimizer POSTs stayed pending throughout. Expected: under 10 s, or an honest message. Other agents were using the server at the same time, so part of this may be contention. Fix idea: show the real elapsed time and a stage label; fix the stale "about 10 s" text.
- [ ] **12+ updateSessions POSTs on load** (low). Network list shows 17 near-identical POSTs to /api/updateSessions before the page renders. Fix idea: batch or skip.
- [ ] **Recompute anyway gave a 502** (med). Did: clicked Recompute anyway. Saw: the whole page was replaced by "No parameter surface could be built. Request failed with status code 502" (one of three queryStimOptimizer calls returned 502); about 3 s later the full page came back by itself (the other two calls returned 200). Expected: a retry or a small inline error, not the whole page blanked. Fix idea: keep the old result on screen while recomputing, and show errors inline.
- [ ] **Console error** (low): "WebSocket connection to ws://localhost/socket/notification failed". It is the only console error.
- [ ] **Contradiction in the next-visit card** (high, wrong numbers). Text says "30 blocks tie at the top with the same plausible improvement (3.09 NRS points)". The ranked table directly under it shows every row's "Best plausible" as WORSE (0.89 worse to 1.78 worse). No row has any improvement. The 3.09 figure is not on any row.
- [ ] **Contradiction in the readiness card** (med). "12 contact-and-rate combinations screened, 12 could not be built" and "not assessed, no evidence for this side", while the rows above show assessed counts like "13 of 18 bands fall with current", "0 of 18 rises with pain". Fix idea: say what was not built (the stimulation-current-removed grid), not the whole screen.
- [ ] **Exploratory ladder card gives odd record dates** (med). "L C+1- carried up to 3.5 mA over 23 stretches, 3738 h, 2025-10-11 to 2026-06-24, 274 pain reports". Evidence base elsewhere runs to 2026-09-02. Other counts for the same contact: 31 stretches (ranked table), 24 stretches (clinic map), 11 stretches (home map). "3738 h" is a bare number. Needs checking against live data.
- [ ] **Left ladder "Record from L 0-2+: 6 of 18 bands ... at 125 Hz" while the session is at 55 Hz** (low). Confusing. Right ladder says best contact on its own side is R 1-3+, but the readiness card names R 0-3+ as the allowed pair.
- [ ] **Clipped text in the dot strip "Analyse at"** (med). Left and Right ladder columns (Next-visit card): the band-centre axis is cut off at the right edge. Labels read "rate ×5 → 25 Hz", "rate ÷2 → 27" (cut), "rate ‹" (cut), and the "30" tick is missing. Fix idea: wrap the strip to its column width or give it a viewBox.
- [ ] **"safe ceiling 4.5 mA" label on the right edge of every pain map** is rotated and clipped or overlapped by the dashed line (all 10 maps). Low to med.
- [ ] **Jargon and code names in page text** (med; breaks house rules 1 and 15). In the Basis fold and the "Hide why this design" fold:
  - "stim1_openloop.clinician_override", "resolved: False / None", "PI's ruling 5", "A610 manual p. 35", "LfpEvidence".
  - "within_visit.PRE_CHANGE_WINDOW_S", "Biomarkers.routines.analytics.harmonic_landings_hz", "within_visit_pooled_shape", "three_source_run_points", "stim_optimizer", "ClosedLoopDeployment.post_ramp.margin_becomes_available", "amplitude_effect.MIN_POINTS_CURVATURE".
  - "the floor is ..." (the word "floor" is banned for this use).
  - "decision 143, S3", "open item 30", "decision 253", "research synthesis §1".
  - raw ISO time "2026-09-02T19:15:43+00:00".
  - Offline checks use raw labels "nrs", "left_leg_vas", "R2", "us".
  - "rings 2", "(< 0.0001998 is the smallest this can read)".
  Fix idea: move these to a hover or a bracket only where needed, and say what the thing does in plain words.
- [ ] **Titles that are not short noun phrases** (low to med). "From the clinic testing sheets (separate from the home pain surveys)" (10 words); "Exploratory ladder for the pair the readiness check prefers" (10); "Home programming schedule to map the two currents" (8); "Closed loop at frozen rate and pulse width" (8); sub-labels "Hold per step, why", "Analyse at, the harmonics", "Record from, why", "Left: stimulate L C+1-".
- [ ] **Open folds lose their title** (low). "Superiority and stopping rule" becomes just "Hide"; there are 45 bare "Hide" buttons. Hard to tell which fold a Hide closes. Fix idea: keep the title and flip only the arrow.
- [ ] **Pain maps use only about 170 px of a 600 px card** (low). Each map sits in its own row with a long empty space to its right; the page scrolls 12,000 to 19,000 px with every fold open.
- [ ] **Pooled maps at 55 and 165 Hz (separate view, "Pooled across rates (reference)") are a solid single orange** (low to med). No gradient visible, so the map carries no information at that colour scale. The pooled-pulse-width view does show a gradient at 55 Hz.
- [ ] **Date input is not blue** (low). The Visit date field has a grey outline (rgb 138,138,138). It is a date picker, not a dropdown; only mention if the rule covers it.
- [ ] **Titration session card not found** (med, if it was expected here). No text containing "titration" exists on this page. Closest are "Exploratory ladder ..." and "Home programming schedule ...". Confirm whether it belongs to the Closed-Loop page.
- [ ] **Date formats differ** (low): "Oct 2, 2026, 6:47 AM" (build times), "10/2/2026, 5:46:48 AM" (grid), "2026-09-02T..." (ISO), "10/07/2026" (date input).
- [ ] **Screenshots lag the click** (info): the first screenshot after opening a fold sometimes shows the mid-animation, overlapped state (Superiority fold). It settled within about 1 s. Not a defect.

## Verified working

- Page loads and renders: headline "Keep today's setting on both sides; closed loop cannot start.", five verdict chips with the legend, Basis fold (opens and closes), jump links (Proven better? / Currents tried / Closed loop / Next visit), "Up to date" bar, Recompute anyway (it fires and the page recovers).
- Stored-result build times fold opens (one line: last built Oct 2, 2026, 6:47 AM).
- Candidate vs. current setting: Left and Right tables, deltas, "+0.00 pts ± 1.24" gauges. NOTE the same ±1.24 and +0.00 on both sides; worth confirming it is not a copied value. Superiority fold and "Why each side reads as it does (8 reasons)" open with text.
- Sampled currents card: opens. 10 Plotly maps in separate mode, 5 in pooled mode; matches the "10 pain maps" and "5 pain maps" headlines. Separate/pooled toggle works. Show/Hide explanations toggle works (text length changes). Numbers fold opens (AUC 0.41 / 0.49 vs 0.57 shuffled). "Three checks", "Why; alternatives" and "Pooled across rates" folds open.
- Closed-loop readiness card opens: 6 listed "not usable" rows with band counts, "19 other combinations" fold, Usability criteria, the four checks, "What closed loop ruled out" (1 setting at 10, 20, 30, 40 Hz).
- Next-visit card: Visit date input (2026-10-07), Make Google sheet button renders (not clicked), both ladder step plots with safe-ceiling line (4.5 mA), 15 steps, about 74 min total, "Hide why this design" fold, home schedule table of 11 steps over 77 days (arithmetic checks: 11 x 7 d).
- Chance and current checks (offline): the dropdown has a blue 1.5 px outline (rgb 11,92,173); all 6 options switch with content and plots, no error text.
- Plot text sizes: svg text is 12 px (236 items) and 14 px (2). The only sub-11.5 px text is "Visit date" (10 px label).
- Network: all other calls returned 200 (querySessions, queryParticipantInformation, queryServerIdentity, queryStimOptimizer apart from the one 502).
- No login page hit; the browser was logged in throughout.
