# Pending items from the old handoff documents, checked against the record (2026-09-25)

**What was read.** Every handoff this project ever had: the 34 handoff, session and audit-triage files
archived in `docs/archive/2026-09-07/` (the old single handoff, `MEGA_HANDOFF.md`, read in full
including its session narrative and its open-item list); the two dated handoffs deleted on
2026-09-19 (read from git at `b1ef6047^`); the bridge handoff still in `BRAVO/_agent_bridge/`; and
seven copies that were never committed to git but sit in the PI's science workspace (two June
biomarker handoffs, two June session handoffs, a 2026-09-05 closed-loop succession handoff, a
2026-09-05 visit plan and a 2026-09-04 open-items sheet). Every item a document called pending,
next, open, deferred, waiting, not built, not run or not watched live was checked against the
decision digest (decisions 1-272), the full decision log, the git log, the consolidation's findings
and the current code.

**What was not done.** Nothing was run, no page was watched and no file other than this one was
written. "Read today" means the current source file was opened and read, not executed. Decisions
1-202 were checked against their full rows; 203-272 against their one-line digest rows.

**Counts, after merging items that several documents repeat:**

| Status | Items | Meaning |
|---|---|---|
| STILL PENDING | 21 | an action with no sign it was done or made moot, needing no ruling |
| NEEDS THE PI | 20 | needs his ruling, a clinical action or a records answer |
| SUPERSEDED | 53 | a later decision or redesign made it moot; what replaced it is named |
| DONE | 93 | built, run or resolved; the decision or commit is named |

The two to-do lists come first. The one item to settle before the next titration session is
**P-01**: the two harmonic checks disagree about whether 24.5 Hz is clear at 55 Hz.

**Source key.** "HANDOFF 06-21" is `HANDOFF.md`; "psd-cache 06-22" `HANDOFF_session_psd-cache_ui-fixes.md`;
"taskB 06-22" `HANDOFF_taskB_spectral_exploration.md`; "biomarker 06-23 hhmm" the four
`HANDOFF_biomarker_20260623_*.md`; "session 06-24 hh:mm" / "06-25 hh:mm" the timestamped
`SESSION_HANDOFF_2026062*T*.md` (08:22 and 23:12 are the science-workspace copies); "NEXT 06-25"
`SESSION_HANDOFF_NEXT.md`; "triage" the three `AUDIT_TRIAGE_*.md` (v2 and v3 are identical); "session
06-27" and "TD-LSB 06-27" the two 2026-06-27 files; "06-28 name" the six `SESSION_HANDOFF_2026-06-28_*.md`;
"09-02 wiring", "09-02 two-stage", "09-05 clinic", "09-05 four-rule", "09-05 result-cache", "09-06 sweep"
and "takeover 09-07" the September `SESSION_HANDOFF_*.md`; "succession 09-05" the science-workspace
closed-loop succession handoff; "to-CC 09-07" and "grids 09-08" the two handoffs deleted on 2026-09-19;
"bridge" `BRAVO/_agent_bridge/HANDOFF_agent_bridge.md`; "visit plan 09-05" and "open-items sheet 09-04"
the two science-workspace RCS08 files; "MEGA date" an entry of the old single handoff's session
narrative, "MEGA §4 n" an item of its open-item list.

---

## STILL PENDING (to-do, no ruling needed)

| ID | Source | Item | Evidence |
|---|---|---|---|
| P-01 | 09-05 four-rule; succession 09-05 | The Stim Optimizer's check of which bands sit on a stimulator harmonic does not fold whole multiples of the rate back down by the device's 250 Hz sampling. So at 55 Hz it misses five times the rate landing at 25 Hz, inside the 24.5 Hz band that decision 236 calls "the one clean band to watch". The Biomarkers check does fold them. | Read today: the Stim Optimizer check (`titration_plan.harmonic_avoidance`) looks only at 250 minus the rate and at half, a quarter and three quarters of the rate; the Biomarkers check (`analytics.harmonic_landings_hz`) puts landings at 25 and 30 Hz for 55 Hz. No decision reconciles them. It changes what the next session's plan tells the clinician to watch. |
| P-02 | triage 06-25 and 06-27 (audit [28]) | The Closed-Loop page's ROC panel still labels its cut-point in "oriented log-power units", but since decisions 202 and 204 the feature is raw power. | Read today in the ROC panel (`DeploymentRocPanel.js`). A one-line text fix; the label contradicts decision 202. |
| P-03 | triage 06-25 and 06-27 (audit [0], [15], [22]) | Three small audit items on the Closed-Loop page were never done: the odds ratio per time block is printed without an interval, the stability result does not say when it was measured, and one rating can be split across two time blocks. | Page code read today. The digest counts audit item 15 closed by decision 244, but 244 fixed only the jump links and checked the print layout (see Part 2 below). |
| P-04 | 09-05 clinic | The page does not say that the mixed-effects result leaves out the first three weeks of data. | The server returns the count (`n_excluded_burn_in`); nothing under `Client/src` reads it (grep today). On 2026-09-05 it changed nothing on RCS08. |
| P-05 | 09-06 sweep (decode review D3) | The saved per-recording PSD files are filed under a hand-written version name, not under the 10% missing-sample limit itself, so changing the limit without renaming would serve old files. | Read today: `_TD_MISSING_VERSION = "v1_missing_aware"` in `Biomarkers/bravo_service.py`. |
| P-06 | 09-06 sweep (D6); cache-store plan Track D step 2, named in to-CC 09-07 | A 29-line PSD-row builder that nothing calls still looks as if it is in use. | Grep today: `_assemble_psd_rows` is defined and mentioned only in comments. It is not on CLAUDE.md's list of things kept on purpose. |
| P-07 | 09-06 sweep (D9) | Per-recording PSD files saved under earlier naming rules are never deleted. | Probably still true: decision 142 added a clean-up for the newest naming only; `ARCHITECTURE_modules_and_store.md` still says "no sweeper". Not measured on disk. |
| P-08 | 09-06 sweep (D10) | Reading the device's programmed switching values runs one database query per therapy group (5.55 s, 9% of the Biomarkers page on 2026-09-06). | Probably still true: `_programmed_adaptive_thresholds` is unchanged since 2026-06-24 and still called. Not re-measured. |
| P-09 | session 06-24 22:09; 06-25 01:19 | The analytics test file's run-as-a-script block calls a test before it is defined, and calls one deleted with the June conversion model. | Still in `Biomarkers/tests/test_analytics.py`. Neither test runner uses that block, so no suite is affected. |
| P-10 | session 06-24 05:38 | Guard against the recording-joining repair moving a recording's start time (stamp the fallback PSD at the recording's midpoint, or keep the original segment boundaries). | Not built and never carried into the record. The handoff itself said it was not needed for RCS08's data. Conditional. |
| P-11 | NEXT 06-25 | Optional: add indefinite-streaming voltage traces as a source of modelled device units on the Biomarkers top timeline. | The agent found the timeline models only from contact surveys and the device's own FFT snapshots. Check against decision 216's acquisition timeline before building. |
| P-12 | MEGA 09-04 (inference) | Explain why two ways of computing uncertainty disagree strongly with 40 or more groups, where they should agree: one allows for repeated measurements within a group, the other resamples whole groups. | Probably still open: no record explains it, and the switch between them is live code (`edges.py`). |
| P-13 | MEGA 09-02 (evening) | A clinic-sheet cell carrying a written correction (for example "L 100 (did 110 accidentally) / R 150") must keep what was actually delivered. | Probably still open, read not run: the sheet reader (`clinic_pain._split_bilateral`, `_assign_pw_sides`) cannot read such a cell and carries the previous step's pulse width. One test on that cell would settle it. |
| P-14 | MEGA 08-30 (the honest-current check) | The "proven better than today" check adds the two uncertainties without the term for how the candidate's and today's estimates vary together; it errs toward refusing. | `stage1_openloop.py` read today; `StimOptimizer/pipeline.py` still calls it "a documented next step". |
| P-15 | MEGA 09-02 (the two paths) | The 8-30 Hz range the device can act on is typed out in three places with no shared import. | Biomarkers (`analytics.THRESHOLD_MODES`), Closed-Loop (`constraints.THRESHOLD_MODE_TABLE`) and `percept_adaptive.ADAPTIVE_LFP_BAND_HZ`. Decision 168 gave the timing ranges one home, not this range. |
| P-16 | MEGA 09-02 (flat limit) | Optional: rename the Stim Optimizer package and its web address to match the sidebar's "Open-Loop Stim Optimizer". | No decision mentions it; the handoff said to do it as its own deliberate pass. |
| P-17 | taskB 06-22 | The Docker image does not install R, lme4 or rpy2, so rebuilding the image would lose the mixed-effects fits and the heat maps' stability test. | Read today: neither `dockerfile` nor `dockerfile.dev` installs R; `requirements.txt` says R is "installed at the OS level". |
| P-18 | psd-cache 06-22; science workspace 06-22 | The timeline's right-hand detail panel (the chosen pair's PSD, raw trace and band-power trend) and zoom-to-waveform were never built. | The timeline file (`BiomarkerDataTimeline.js`) has no click handler or panel, yet its header comment describes the panel as if it existed. |
| P-19 | biomarker 06-23 1300 | Check whether recordings the patient triggered (made because something happened) create a false pain signal, by splitting the result by recording source. | Probably still open: the per-cell share of each source is counted (decision 106) and the timing histogram is drawn per source (224), but no result split by source was found. |
| P-20 | bridge | The beta-peak detector's classifier files were saved under scikit-learn 1.6.1 and load under 1.5.2, so they may mispredict; pin the version or refit them. | `requirements.txt` still pins 1.5.2; `OPERATIONS_runbook.md` §8 still warns. These files are the platform's beta-peak detector, not the pain analysis. |
| P-21 | bridge | Django's settings name a static-files folder that does not exist (a harmless warning). | Read today: `STATICFILES_DIRS` points at `BRAVO/static`, which is absent. |

## NEEDS THE PI

| ID | Source | Item | Evidence |
|---|---|---|---|
| N-01 | MEGA 09-03 (rate as a covariate); MEGA 09-05 (within-visit entries); 09-05 clinic; 09-06 sweep; visit plan 09-05 | Is the change on the left 1-3 contact pair near 25-27.5 Hz coming from the brain, or from the stimulator? Answering it needs that pair recorded at a rate whose harmonics avoid 22-28 Hz (a 60 Hz control session was proposed). | Ruling 233(3) and decision 236 keep the next session at 55 Hz, with the half-rate harmonic named; P-01 adds the folded fifth multiple at 25 Hz. No such recording exists, so the question stays open. |
| N-02 | MEGA 09-06 (three lanes; sweep) | Step the current at two rates in one visit, so rate can be told apart from 13 months of elapsed time on the right 0-3 pair. | No visit or ruling found. Rulings 233(3) and (5) set the next session at 55 Hz only. |
| N-03 | MEGA 09-06 (three lanes) | Should "this band behaves differently at another setting" block a closed-loop band? | Read today: `stability.py` says "not decided - reported for the PI to rule on, blocks nothing today". Decision 242(b) only ranks it. |
| N-04 | MEGA 09-05 (mixed model) | Does the validation mixed model's three-week exclusion count from implant or from the first usable rating? It also needs a guard against a model that cannot be estimated. | Read today: the comment in `analytics.py` still says it "needs the PI's decision and a degeneracy guard". |
| N-05 | 09-02 wiring; 09-02 two-stage; MEGA 09-02 (overnight) | The shuffle test that keeps the ratings' own persistence reaches "rotate the whole series" by rounding, not by choice. Choose it on purpose? Doing so moves published p-values. | Read today: `stats_utils.block_length_for` says "OPEN DESIGN QUESTION, deliberately not resolved here". Decision 240's newer check chose rotation explicitly; the older routines still reach it by rounding. |
| N-06 | MEGA 09-03 (later still) | The visits after titration: programming closed loop and testing whether it helps. | The titration session ran 2026-09-16 (213). No sensing pair has a usable band today (0 of 50, decisions 217 and 247), and the sign-off card waits on his signature (258). |
| N-07 | MEGA 09-02 (evening) | Score every pain site, above all the left leg, at every clinic step. | Decision 255: 36 of 70 clinic stretches at 55 Hz "carry no Left Leg rating at all". A clinic protocol choice. |
| N-08 | MEGA 09-02 (evening) | Confirm prospectively the two mild side effects seen at 110 Hz, left 2.5 / right 2.0 mA. | No follow-up in the record. Low priority while the next session is at 55 Hz (233). |
| N-09 | 09-05 clinic | Four rates in the clinic sheets (25, 85, 100 and 180 Hz) never appear in the device's record. Were they delivered and missed by the export, or planned and never given? | `clinic_steps.py` still says "UNRESOLVED". A records question. |
| N-10 | succession 09-05 | A July 2025 clinic step at 6.0 mA for 144 s is above the 5.0 mA limit stated at the time. Was the limit raised, is it a planned value, or a typing error? | Nothing in the record. The ceiling is now 4.5 mA (160). A records question. |
| N-11 | grids 09-08 §6.1 | The sliding-window setting is fixed off on the page but still sent with every request, and the server defaults to on when it is missing. Remove it? | Read today: `const slidingWindow = false` in the page; no ruling found. The handoff called removal a behaviour decision. |
| N-12 | grids 09-08 §6.2; HANDOFF 06-21 (found while checking) | Every Compute still builds a full correlation grid of the PSD computed from the voltage trace against pain, and the old pooled detector with a 1,000-shuffle test per channel, but only the fallback timeline reads them. Keep or remove? | `run_timedomain_branch` still runs. Its summary now carries the on-screen report-sharing note (221), so it cannot simply be deleted. The consolidation timed a repeated 1,000-shuffle test at 34-37% of Recompute; this may be it. |
| N-13 | grids 09-08 §5 | One table joining the voltage trace, PSD, band power, times and the matched pain report, which he floated and left as his call. | No ruling or build found. |
| N-14 | session 06-24 06:40 | Build a net-benefit decision curve across cut-points, or drop the idea. | Never built; the page code still calls it "a Phase-2 panel". It matters less since device switching values are placed from the record (180). |
| N-15 | MEGA 08-30 (housekeeping) | Delete the loose copies of device session files staged in the bridge's incoming folder ("deleting inside the repo is the user's call"). | Still on disk and outside git; the folder is 4.7 GB, including a subfolder written on 2026-09-24 that looks in use. |
| N-16 | HANDOFF 06-21 §7-B; biomarker 06-23 1615 and 2058 | Show the trial stages on the Pain Scores page. The dates must come from him. | The participant file's program dates are empty and the page sends no stages. |
| N-17 | psd-cache 06-22 (R1, R4, R5, R6) | Confirm four timeline display choices: the slate pain line, hiding unmatched PSD marks in the split view, hiding the frequency legend there, and the stimulation row's height. | All four are as built; no ruling found, though he has used the page many times since. |
| N-18 | HANDOFF 06-21 (TODO 4) | Build live job-progress messages (the server side of the notification socket), if he wants them. | No server endpoint exists; the page fails quietly. |
| N-19 | HANDOFF 06-21 (TODO 4, §7-D) | Re-run the CodeRabbit review, which sends the code to an outside service and needs his consent. | No record of consent or of a run. |
| N-20 | taskB 06-22; biomarker 06-23 2058 | Keep, archive or delete the June mock-up images and review pages at the repository root. | 20 are tracked (commit `39b265b1`) and 37 are present. The markdown was archived (34); these were not. |

## SUPERSEDED

| ID | Source | Item | What replaced it |
|---|---|---|---|
| S-01 | takeover 09-07; MEGA 09-07 | Delete the 6,309 per-recording PSD files that no page read. | Decision 51 kept them behind a quick up-to-date check (0.35 s against 3.1 s); 50 struck. |
| S-02 | takeover 09-07; 09-06 sweep | Move the "when was this built" check into Redis, and point Django's own cache there. | Plan Track F steps 3-4: the small stamp file beside each saved answer is as fast (0.012 against 0.017 ms), and nothing reads Django's cache. |
| S-03 | grids 09-08 §4 | Move the heat map's rating-to-recording selector onto the shared matching code. | Decision 118: it selects, it does not match. |
| S-04 | grids 09-08 §4 | Move the per-report band-power reader onto the shared matching code. | Decision 118, then 225 deleted the reader. |
| S-05 | MEGA §4 6; MEGA 09-02 and 09-05 entries; 09-05 clinic; 09-06 sweep; visit plan 09-05 | The 110 Hz heat map, the pre-registered 110 Hz session, the 165 Hz lead and a 110 Hz range of currents as the visit's priority. | Decision 109 (no such figure; pre-registration unrun), 182 (110 Hz set aside at his instruction), 233 rulings 3 and 5 (55 Hz); the energy cap retracted (`c826706d`). |
| S-06 | MEGA 09-06 (later) | Does the harmonic inside 22.5-27.5 Hz rule out the pre-registered 24.5 Hz band? | Pre-registration unrun (109); a harmonic is a warning, never a refusal (220); named in 236. See P-01 and N-01. |
| S-07 | TD-LSB 06-27; 06-28 audit_5_42; MEGA §4 3 | Draw each rating's 30-second trace of 1-second values with a clipping flag. | Decision 110: the PI did not want it; code deleted (225). |
| S-08 | MEGA §4 7; MEGA 09-06 (sweep) | Speed up reading recordings off disk. | Measured at 4.8% of the page; the real cost was fixed by decision 43. |
| S-09 | MEGA §4 9; 09-06 sweep | Edit and reconcile the old biomarkers-and-deployment README. | Archived and absorbed in the consolidation (34). |
| S-10 | MEGA 09-06 (three lanes) | Connect the power-against-current routine keyed on the clinic sheets. | The current is read from the device's own record (40, 125, 126, 213). The routine (`amplitude_response_cached`) still exists with no caller. |
| S-11 | MEGA 09-06 (three lanes) | A strip beside the band-against-current heat maps saying whether power rises or falls with current. | Probably: those were one-off figures; the three-source panel and the change in power per milliamp carry it (125, 126, 198). |
| S-12 | MEGA 09-04 (prescription) | Find out whether the device counts onset time in averaging windows or in its own FFT updates. | Averaging 3 s and onset 30 s (150, 169), so onset spans many windows either way. The device fact itself is still unknown. |
| S-13 | MEGA 09-04 (D09) | Move the band into 8-12 Hz before capturing the device's switching settings. | Probably: never discussed again; bands are chosen by the one-band rule over 8.5-29.5 Hz (199, 210, 217). |
| S-14 | MEGA header and §5 | Re-check the test counts of the optional PyTorch version. | No suite counts in documents (34); the PyTorch version deleted (145). |
| S-15 | session 06-24 08:22, 06-25 01:19, 02:06, 07:06; NEXT 06-25; 06-28 universal_tier1 and all_TD_modeled | Extend the work beyond RCS08: other participants' conversion models, the 269 constant, FFT snapshots for participants with no voltage trace. | Full log Part 2: "Dropped by the PI ... generalising beyond RCS08". The June model deleted (218). |
| S-16 | session 06-25 07:06 | Clean up the patient-named file names in the shared-drive device folder. | Dropped as a work item in the same Part 2 line; kept as a rule (OPERATIONS_runbook §9). |
| S-17 | session 06-24 23:12 | Choose which conversion factor turns the analysis cut-point into a device switching value. | Decision 21 (never convert the switching value), 180 (placed from the record). |
| S-18 | session 06-24 22:09 | A contact-pair selector and a 1 h / 2 h choice on the conversion panel. | Panel deleted (227 B1); the calibration-in-effect panel replaced it (212). |
| S-19 | NEXT 06-25 | Make the plots below the Biomarkers timeline redraw when the pain split changes. | Probably: the heat maps replaced them (62, 87, 91, 107). |
| S-20 | TD-LSB 06-27 | A Welch-256 × 269 backup conversion for reports matched only to an FFT snapshot. | Removed 2026-06-27 (`184ea74`, `fa2c416`); replaced by the composed conversion of the device's own FFT snapshot (now 72.16, decision 211). |
| S-21 | TD-LSB 06-27 | Flag, without dropping, the ~1% of device readings that spike far above the voltage trace. | He chose exclude-and-count: decisions 33, 47, 52, 94. |
| S-22 | 06-28 phase1_3_4a | The per-report cap as the reason the old full-range scan over-reported bands. | That scan deleted (`0316abad`); the heat maps carry their own correction (63, 183, 246). |
| S-23 | 09-02 two-stage; MEGA 09-02 and 08-30 | The 402 never-reviewed "no side effect" labels, the missing right-side side-effect model, two unchecked PyTorch parts, the gap in the 55 Hz safe range and the "above 4 mA is unknown" rule. | Side-effect model and PyTorch code deleted (145); the PI states the ceiling, 4.5 mA (160); side-effect rules 164-166. |
| S-24 | MEGA 09-02 (harness) | The Bayesian-optimisation refactor parked on installing PyTorch. | Report written (`ef6a996f`); the code deleted (145). |
| S-25 | 09-05 clinic | Drop bands at the stimulator's harmonics per rate. | Ruled in the same document: report, never act; decision 220 makes it a warning. |
| S-26 | 09-05 four-rule; succession 09-05 | Device rule D19 as the only blocker. | Decision 134 (passes on observed directions); today's refusals come from the sensing-pair rule (217; D52, 247). |
| S-27 | succession 09-05 | The two sides point opposite ways against left-leg pain (right +0.82 per mA). | Left and right fitted together (157); no current recommended unless three checks pass (158); the current-pain link does not hold out of sample (235(b)). Nobody re-examined the +0.82. |
| S-28 | 09-06 sweep (D2, D4, D7) | A significance helper that returned blank on failure; a contact vanishing from the per-report answer; 386 PSDs recomputed per request. | Helper and its caller deleted (79, 227); the per-report reader deleted (225); the older routine kept separate by ruling (61, 72). |
| S-29 | MEGA 09-02 (the two paths) | The two modules rank bands by different measures, so two pages could name two bands. | The Closed-Loop card reads the Biomarkers grid (131); one-band rule (199); the chosen band held on the server (249). |
| S-30 | MEGA 08-31 | The correlation-by-frequency curve fix was correct but not visible. | The curve deleted (145). |
| S-31 | MEGA 08-30 | Decide panel by panel whether the outlier rule applies to six chronic-recording panels. | Four of those routines deleted (219), two more with the curve (145); effect measured (205). Whether the histogram panel should show its outliers was never ruled on explicitly. |
| S-32 | MEGA 06-28 (remediation) | Items R5-R14: a coverage document, a label, a bridge probe, band-grid settings, a guard, settings for fixed numbers, a band check, a per-participant constant. | Probably: the scan they targeted was deleted (`0316abad`); constant refit (208, 211); band grid fixed (32, 170). The plan itself is not in the repository. |
| S-33 | MEGA 06-28 | Trace why the default pain score escaped the `vas_min` crash. | Matching by rating value deleted; ratings grouped by report (`cf7c429e`). |
| S-34 | MEGA 09-03 (rate as a covariate) | The ramp time was not grounded until a titration was run. | Probably: transitions set to 30 s from the design rule and the tablet's ranges (150, 169); undecidable values named (200, 242(c)). |
| S-35 | psd-cache 06-22; science workspace 06-22 | A scan sliding a 5 Hz band across the PSD, plotted against pain. | Built, then removed (77); the heat maps replaced it (62, 87). |
| S-36 | taskB 06-22; biomarker 06-23 0135 and 1300 | Show the mixed-effects odds ratio when a band is clicked. | Readout removed (`57c65d1b`); both routes deleted (145). |
| S-37 | HANDOFF 06-21 §7-C | Stop pooling the two brain targets and the two recording kinds into one switching value. | Heat maps per sensing pair and side; a page judges a band on its own side (141); pooled analytics deleted (187). |
| S-38 | HANDOFF 06-21 §7-C | Refit the k-means pain labels inside each training part. | K-means replaced by the three-way split; validation is forward-chaining out of sample (12). |
| S-39 | HANDOFF 06-21 §7-C | Choose one band in advance to avoid testing ~600 combinations. | Probably: 22 centres 8.5-29.5 Hz (32), corrected per grid (63). |
| S-40 | HANDOFF 06-21 | Restart the server so the power-domain shuffle result appears. | The power-domain panels left the page on 2026-06-28. |
| S-41 | biomarker 06-23 (all four) | Rule out stimulation artefact in the 54-87 Hz candidate bands. | Bands limited to 8.5-29.5 Hz (32); harmonic warning (220). |
| S-42 | biomarker 06-23 1300, 1615, 2058 | Re-check five suspiciously narrow mixed-effects intervals. | That candidate list feeds nothing; cell intervals resample blocks of time (183). |
| S-43 | biomarker 06-23 0135, 1300, 2058 | Find out why the composite score produced no validated bands. | The candidate pipeline replaced by the heat maps; every score precomputed (107). |
| S-44 | biomarker 06-23 0135, 1300 | A methods note on live against offline false-discovery counts; confirm the scan sends raw channel names. | The scan and the click check deleted (77, 145); correction over 22 bands per grid (63). |
| S-45 | biomarker 06-23 0135, 1300 | A hook that sends the setting to the Percept RC. | Nothing writes to the device, by design (consolidation findings §1 row 24). |
| S-46 | biomarker 06-23 1300 | Decide whether the deployment ROC matches only data recorded before each report. | The summary takes the direction from the chosen cut-point (254). |
| S-47 | HANDOFF 06-21 | Feed pain reports into the Predict Therapy page's contact choice. | The Stim Optimizer recommends settings from pain ratings (138, 158, 222). |
| S-48 | psd-cache 06-22 | Record which kind of stream each number in the band hand-off came from. | Hand-off deleted (145); each row names its source (33, 47, 52, 106). |
| S-49 | psd-cache 06-22 | A gallery comparing high-pain and low-pain PSDs; a gallery of every montage and event PSD. | Replaced by the scatter and violin opened from a heat-map cell (66, 87, 91, 228); the platform's own snapshot and events pages draw the curves (probably). |
| S-50 | psd-cache 06-22 | Check that low-pain and high-pain days are balanced before placing switching values. | Probably: the split balances by construction; the headline correlates the continuous score (62); switching values placed from the record (180). |
| S-51 | psd-cache 06-22 | Pre-load recordings in the background. | The saved 3-second chunks of recording are read from disk (23, 44, 46, 266); daily precompute (97, 107). |
| S-52 | science workspace 06-22 | Draw the band-power lines green like their legend symbols. | The green symbol removed (`53bdb06a`). |
| S-53 | biomarker 06-23 1300, 1615, 2058 | Confirm in the browser the corrected count of matched pain reports (~290 of 682). | Matching rebuilt on 3-second chunks (23, 94); new count watched live (224). |

## DONE

| ID | Source | Item | Evidence |
|---|---|---|---|
| D-01 | MEGA 09-07; takeover 09-07 §2, §7.1; to-CC 09-07 | Let the three modules save their answers on disk and read each other's, with each answer's inputs recorded and a proven refusal to read one's own output; one implementation instead of two; six new saved tables; his go-ahead first. | Decisions 30, 31, 35, 37-41, 47; `fa14edd`; full log Part 2 item 2. |
| D-02 | takeover 09-07 | Save the pain-report table but fetch it fresh on every build. | Decisions 35, 78. |
| D-03 | takeover 09-07 | Install the compressed-table library (pyarrow). | `fa14edd`; pinned in `requirements.txt`. |
| D-04 | takeover 09-07; 09-06 sweep | Stop four web workers building the same slow answer at once. | Decision 46 (one build, 41 s against 368 s). |
| D-05 | MEGA 09-07; takeover 09-07 | Find out why the Closed-Loop evidence triangle was not showing. | Decision 45 (the report failed on the calibrated input). |
| D-06 | MEGA 09-07; takeover 09-07 | Agree which band-power source counts as ground truth. | Decisions 33, 47, 52. |
| D-07 | to-CC 09-07 | Replace the provisional saturation ceiling on device readings. | Decision 52 (99.5th-percentile table per contact pair and centre). |
| D-08 | MEGA 09-07; to-CC 09-07 | Reconcile the reference documents once the saved-answer work was built. | Decisions 34, 203. |
| D-09 | takeover 09-07; to-CC 09-07 | Copy the design ledger, drawings and four-lens audit onto disk; carry over the figure and timeline conventions. | `fa14edd`; `docs/exported_artifacts/`; the two project skills (CLAUDE.md §7). |
| D-10 | to-CC 09-07; takeover 09-07 | Decide what to do with the two folders of saved PSDs. | Decisions 51, 53 (61, 72 on merging). |
| D-11 | MEGA 09-06; 09-06 sweep | Stop rebuilding the therapy-settings history more than once per request (65.71 s). | `97c96640`; decision 37; full log item 8. |
| D-12 | MEGA 09-06; 09-06 sweep | Restructure how recordings are decoded; one shared decoding path. | Decisions 42-44, 61. |
| D-13 | MEGA §4 4; 09-05 result-cache | Fix the page-memory faults: two requests per Recompute, a count limit, a lost error; commit the wiring. | Decisions 54, 60; `8e4ee180`. |
| D-14 | MEGA 09-04 (later) | Stop the Closed-Loop page rebuilding its joined table on every request (73 s). | 70.55 s to 0.45 s (MEGA 09-04); decisions 37, 45. |
| D-15 | 09-06 sweep | Finish the two speed-up jobs (the sweep's statistics, the REDCap pull). | `c70e0b04`, `2a4d063e`. |
| D-16 | 09-06 sweep (D1, D8) | Log recordings whose PSD failed; stop decoding surveys and montages twice. | Decisions 142, 79, 267. |
| D-17 | TD-LSB 06-27 | Make the transform route from the voltage trace the one conversion, with its helpers. | `7ea8f6df`; now 345.59 (211). |
| D-18 | TD-LSB 06-27 | A test reproducing the lab's reference (352.62, r 0.9927, 131 blocks). | `7ea8f6df`; decision 208 (`1914a9d8`). |
| D-19 | TD-LSB 06-27 | Prove that changing the constant leaves every correlation and area under the curve unchanged. | Test in `7ea8f6df`; 211 ("verdicts unchanged"). |
| D-20 | MEGA 09-06 (later); psd-cache 06-22; taskB 06-22 | Check the conversion factor on simultaneous recordings; check µV² per device unit. | Decisions 208, 211, 214 (1/352.7, 0.98 of the constant in effect). |
| D-21 | TD-LSB 06-27 | Prefer an unused voltage trace over an FFT snapshot; one report per recording by default. | `beb2c97e`, `ed1b9a01`, `b6f660f7`; 118. |
| D-22 | TD-LSB 06-27 | Put FFT-snapshot values on the transform's scale rather than mixing scales. | `f4d821a7`; 33, 208 (composed values tagged). |
| D-23 | TD-LSB 06-27 | Keep the device's own reading first; a modelled value never sets the switching value when a device reading exists. | Two tests in the Closed-Loop suite; decision 33. |
| D-24 | TD-LSB 06-27 | Write "median fold error" in full everywhere; label each constant with its recipe. | Grep today: 0 short uses; decision 208 (recipe in the repository). |
| D-25 | TD-LSB 06-27 | Offer a modelled switching value only for bands 7.8-30 Hz. | Probably: `7ea8f6df`; bands chosen from 8.5-29.5 Hz (32); device rules D08, D12, D13. |
| D-26 | TD-LSB 06-27 | Confirm the cited commits before relying on them. | All three exist, with the PR #8 merge `a191b758`. |
| D-27 | session 06-24 23:12; 06-25 01:19 | Frequency-dependent device gain as code for every pair. | `771f3c2`, decision 11; later deleted (218). |
| D-28 | session 06-24 23:12 to 06-25 07:06 | Explain the 8.8 Hz shift on R 0-3; decide the impedance gain term; calibrate 55.5 Hz. | Decisions 16, 17; `90fd5c3`. |
| D-29 | MEGA 09-06 (later) | Stop computing the band-power-to-pain correlation on log power. | Decision 204. |
| D-30 | session 06-24 06:40, 08:22 | Four Closed-Loop figure upgrades (histogram, per-block AUC, power curve, palette). | `e32828f`, PR #4 `52010ec`. |
| D-31 | session 06-24 08:22, 21:00; science workspace 06-22 | Replace the pandas and numpy calls newer versions removed. | `b0597f8`. |
| D-32 | session 06-24 21:00 (audit C9, C10) | The ROC cut-point trace number in one place; recommended against programmed; ramp advice. | `b0597f8`; decision 10. |
| D-33 | session 06-24 21:00, 22:09; triage; session 06-27; 06-28 audit_5_42; MEGA §4 1 | Pictures of the page's figures in the exported and printed sign-off record (audit C10, [49]). | Decision 113, watched live. |
| D-34 | session 06-24 21:00 to 06-25 02:06 | Test each band on later weeks its model never saw (audit C2), and draw the per-week score. | Decision 12; `b2e01f10`, PR #7. |
| D-35 | session 06-25 07:06; NEXT 06-25; triage; session 06-27; 06-28 audit_5_42 | Triage the 28 medium and 24 low audit findings: nine judgment calls, the interval changes, the server-side cut-point [5] and the operating-point chip [42]. | `c48efbf`, `ff65277`, `8c8f976f`; decision 19. |
| D-36 | triage; session 06-27; 06-28 audit_5_42; MEGA §4 1 | Reconcile the two "how many independent things" counts (audit [14]). | Full log item 15, "his choice: relabel" (`707a20ef`). |
| D-37 | triage | Badge colour and the "credible" note (audit [25], [1]). | Shared palette; decision 174. |
| D-38 | triage (audit [39], [43], [48]) | Jump links; figures drawn at zero width in a closed section; the verdict beside its figure. | Decision 244; `8e4ee180`; read today. |
| D-39 | session 06-24 08:22 | Clinician feedback on the new figures. | Probably: decision 167 (19 findings); his own rulings 171, 247, 258. |
| D-40 | HANDOFF 06-21; NEXT 06-25; to-CC 09-07 | Push the branch. | PR #9 `39dfb2f`; standing go-ahead of 2026-09-07. |
| D-41 | NEXT 06-25; full log Part 2 "Then" | Design the closed-loop simulation around the committed-band format. | Decision 128 (M0-M3). |
| D-42 | takeover 09-07; to-CC 09-07; 09-06 sweep; MEGA §4 5 | Whose name goes on commits. | Decision 49. |
| D-43 | HANDOFF 06-21; biomarker 06-23 1615, 2058 | Map REDCap columns to the page's pain-score columns; check the other timestamp columns for the 7-8 h error. | `8a4c33b1`, `c70e0b04`; decision 2 (the second probably). |
| D-44 | HANDOFF 06-21 | Watch the data-availability timeline live. | Decisions 216, 260. |
| D-45 | HANDOFF 06-21 | Check uploads, decoding and migrations on the real container. | Probably: the platform has run live since (3, 263, 264). |
| D-46 | HANDOFF 06-21 §7-C | Block-resampled intervals on accuracy; explain the ~170 of 284 sessions with zero PSD. | Decisions 19, 183; 4, 57-59 (the second probably). |
| D-47 | HANDOFF 06-21 | Remove the unused backend list of sensing-setting changes. | `7097b5d8` (187). |
| D-48 | taskB 06-22 | Four page requests (split preview, dropdown label, grey unmatched data, titles); say when the split has no middle group. | `ade2595`, `3106012`. |
| D-49 | taskB 06-22 | Bring the device's own FFT snapshots from patient events into the band search. | `f6849c44` (3,119 of 3,119 routed); 106. |
| D-50 | psd-cache 06-22; science workspace 06-22 | Patient events on the timeline; merge the two sections and remove the sliding-window switch from the page. | `124cc772`; `a4159e78` (see N-11 for the leftover setting). |
| D-51 | biomarker 06-23 0135, 1300; psd-cache; taskB | Build the Closed-Loop Deployment page (ROC with intervals, cut-point search, device units, sample size, per-period refit, sign-off). | Ten commits on 2026-06-23 (`f9632974` to `a6b6eb49`). |
| D-52 | psd-cache 06-22; taskB 06-22; MEGA 09-06 | Test whether the band-to-pain link differs between stimulation periods, and show that answer on the Closed-Loop page. | `aba58f7`; decisions 96-98, 131, 185, 248. |
| D-53 | psd-cache 06-22; MEGA 09-03 | Confirm the adjustable ranges of the device's closed-loop settings, including the averaging time. | Decisions 148, 149, 168, 169. |
| D-54 | psd-cache 06-22 | Decide the headline statistic of the band search. | Open item 5 (2026-09-08); decisions 62, 63. |
| D-55 | science workspace 06-21 | Model the whole device setting and simulate it against pain; choose pair and band first. | Decisions 128, 148-152, 169, 180; 62, 131, 199, 217. |
| D-56 | science workspace 06-21 | Decide whether voltage-trace and device band-power recordings share one analysis. | Calibrated and pooled with a trust order (18, 33, 211); builders kept separate (72). |
| D-57 | biomarker 06-23 2058 | The R conversion error; whether decoding joins separate streaming sessions; commit the rating-centred PSDs and timeline fixes. | Decisions 1, 3, 4; `aa116cc0`, `11b8a09b`, `857bd40b`. |
| D-58 | science workspace 06-22 | Before-only matching covered 59 of 682 reports: widen it or show both rules. | `e6cca9f`, `856c44c`; 224. |
| D-59 | biomarker 06-23 | Keep the bridge's one-off scripts out of git. | `c46efd8`; 102. |
| D-60 | psd-cache 06-22 (R2, R3, R7) | Keep the darker greys; decide whether the old timeline and panels stay mounted. | Both colours kept; decisions 77, 80, 174. |
| D-61 | 06-28 bug_fixes; all_TD_modeled; phase1_3_4a; MEGA 06-28 | Land the uncommitted changesets and phase 1, 3, 4a. | `f6849c44`, `ed1b9a01`. |
| D-62 | 06-28 biomarker_count_ux; MEGA 06-28 | Match reports to the saved 3-second chunks, each chunk once; redo the histogram hover; stamp each recording's product type. | `ed1b9a01`, `edfd0b57`; 224. |
| D-63 | 06-28 audit_5_42; MEGA §4 2 | A live test that the timeline circle equals the per-report value. | Decision 114 (240 of 240). |
| D-64 | 09-02 wiring; 09-05 clinic; MEGA 09-02 and 09-05 | Pass live closed-loop evidence into the two-step plan and connect it to a page; say which path is the main one. | `b6f22ecb`; decisions 137, 157. |
| D-65 | 09-02 wiring; 09-02 two-stage | Check the pain maps' stated uncertainty on held-out data. | Decisions 238(c), 253. |
| D-66 | 09-02 wiring; 09-02 two-stage | The data cannot pin down how smoothly pain changes with rate. | Stated as an assumption, never moving a recommended current (243(e)). |
| D-67 | 09-02 two-stage | Do not install PyTorch; remove two stray files. | Decision 145; both files gone. |
| D-68 | 09-05 clinic; MEGA 09-02 | The best rate found (40 Hz) is below the 55 Hz minimum; the Closed-Loop page did not know the minimum. | Decisions 138, 141. |
| D-69 | 09-05 four-rule; succession; open-items sheet 09-04; MEGA 09-03 to 09-05 | Settle the device rules that could not be evaluated (D29-D32, D16, D19, D30). | `e41613ff`; decisions 133-136. D31's own text still suggests reading the limits off the programmer. |
| D-70 | 09-05 four-rule; succession; MEGA 09-05 | Re-run everything at 55 Hz instead of relabelling 165 Hz results. | `90eb109`; 132, 199, 217. |
| D-71 | 09-05 four-rule; succession | The left side had no active sensing group since 2026-03-31. | Probably: decision 135 ("sensing on both sides"); 252. |
| D-72 | 09-05 four-rule; succession; takeover 09-07; MEGA 09-05, 09-07 | Get the clinic sheets and their steps onto the server. | `2389878e`; decisions 161, 181, 182. |
| D-73 | 09-05 four-rule; succession | Measure power against current within a visit. | Decisions 126, 197, 213. |
| D-74 | 09-05 four-rule; succession | A saved table of surviving bands for every pain score. | Probably: built as the precomputed heat maps (107). |
| D-75 | 09-06 sweep; takeover 09-07; to-CC 09-07; MEGA §4 8; visit plan 09-05 | Decide how to handle a band that rises then falls with current; design and run the titration session (step size, 2 min steps, one side at a time). | Decisions 55, 56, 124, 146, 160; run 2026-09-16 (213). |
| D-76 | 09-06 sweep | Two pain reports filed at the same second. | Recorded in METHODS; behaviour kept on purpose. |
| D-77 | takeover 09-07 | Reword the stability panel ("behaves differently than what?"). | Probably: the panel now names what it compares; decision 185. |
| D-78 | grids 09-08 | Look at the heat maps in a logged-in browser; switch on the export button; rule on the device-rules note; decide where the stability check's cost lands; move the pooled-PSD matcher. | Decisions 86-90, 95, 108, 96-98, 117. |
| D-79 | MEGA 09-06 (later) | Does more power going with less pain rule a pair out for closed loop? | Decisions 199, 210, 217. |
| D-80 | MEGA 09-05, 09-04 | Measure time at the upper current limit with finer data. | Decisions 128, 151. |
| D-81 | MEGA 09-04 (safety), 09-03 | Hidden rule values, the page's own copy of the minimum count, the unused "not applicable" status. | `293a1c98`; read today. |
| D-82 | MEGA 09-04 | Device facts from the ingested reports; readable impedance recordings. | Decisions 136, 133. |
| D-83 | MEGA 09-05 | Is 0.5 the right minimum gap between the device's two measurements? | Settled in the pre-registration entry the same day. |
| D-84 | MEGA 09-03; 06-28 | Re-run the container tests once the container is reachable. | Run many times since (e.g. 270). |
| D-85 | MEGA 09-03, 09-02, 08-30 | A randomised visit at one rate. | Run 2026-09-02 (22 steps). |
| D-86 | MEGA 09-03 (knobs) | Place the Dual Threshold switching values; recommend the two measurement currents; the current while closed loop is paused. | Decision 180; the paused current stated by the PI (`device_facts.py`, rule D34). |
| D-87 | MEGA 09-03, 09-02 | Build the closed-loop deployment module and objective. | Built next (121 tests); `ba089e2d`. |
| D-88 | MEGA 09-03 | Prefer the three-way stability verdict over the old yes/no flag. | Decision 83. |
| D-89 | MEGA 09-02 (F8) | Run the shuffle test on the same rows as the chosen band. | `6001e00f`; 246(c). |
| D-90 | MEGA 08-30 | The 13-item statistics audit. | `2fdf2ee8`, `1878707d`. |
| D-91 | MEGA 08-30 | Re-provide and ingest the July and August device files. | 57 files ingested. |
| D-92 | MEGA 08-30 | Outlier cut at 5 median absolute deviations, per contact pair and band; values the device runs on set on all the data. | Decisions 94, 205; 180, 208. |
| D-93 | MEGA 08-30 | Put the Stim Optimizer on the sidebar. | Reachable since 2026-08-30. |

---

## Part 2 entries already resolved

The digest's Part 2 ("Open items") holds no item that is still open. What is there:

1. **"30. Titration session"** sits under "On the PI" but says itself "RUN on 2026-09-16 ... Closed" (decision 213; the margin ruling in 217). It can leave Part 2.
2. **"Ruled 2026-09-21 and built (218-222) ... nothing of that list remains open"**: every ruling it names was built (218-222, then 223-227). It can leave Part 2.
3. **"Item 15 remainder: closed by 244. One layout question is left for the PI: the sign-off card sits ABOVE the CL-DBS simulations card"**: the layout question was answered by decision 258(a), "THE SIGN-OFF CARD IS THE LAST CARD", with the jump links following. **But "closed by 244" overstates it**: 244 fixed the link order and checked the print layout, while four of the seven June audit items in that batch are still open in today's code (P-02: the "log-power" label; P-03: intervals on the odds ratio per time block, when the stability result was measured, one rating split across two blocks).
4. **"10. The 110 Hz heat map ... Rewritten, not open"**: not open by its own words; 182 (110 Hz set aside at his instruction) and 233 rulings 3 and 5 (55 Hz) make reopening unlikely.
5. **The full log's Part 2 closing line, "Then: design the closed-loop simulation module against the BandCandidate contract"**, was done by decision 128.

Also stale, in Part 1 of the digest (the one-band rule paragraph): "On RCS08 every qualifying band sits on a stimulator harmonic and L 1-3+ / L 0-2+ have no positive band — his to weigh" predates decision 217, after which 0 of 50 combinations are usable.

## Rows never proved live

Decision rows that say "not yet watched live", "NOT RUN", "waits on" or similar, and whether a later row closes them:

| Row | What it said | Closed later? |
|---|---|---|
| 156 | The gain wiring (the simulation's M1 run differing from M0 on a titration run's data) was proved on constructed data only; "waits on the titration session". | **Not closed.** The session ran on 2026-09-16 (213), but no row reports running this check on it. After 213 the left change in power per milliamp is unresolved (p 0.72), so M1 may still equal M0 on today's data. |
| 235 | The three interim caveats "not yet watched live". | **Partly.** (a) the triangle sentence was replaced by 242(e), which was proved live. (b) the current-map sentence and (c) the heat maps' six lines: later rows watched both pages (243, 245, 247, 251) without saying these sentences were seen. |
| 237 | The two readings of one titration session: "the card's wiring waits on the visit's own data". | **Not closed.** The routine is built and reached by no page; it waits on the exploratory session with fixed-current holds (230, 233), which has not been run. |
| 244 | Jump-link order "NOT watched on screen". | **Partly.** 258 re-ordered the cards and links, extended the order test and measured the live page for text size, but no row says the links were watched. |
| 263 | "NOT PROVED LIVE": the participant-context service and the custom-analysis trim. | **Partly.** 270 proved the service live. The custom-analysis trim cannot be proved on RCS08, which has no custom analyses. |
| 238, 253 | The pain maps' calibration check and its diagnosis are on the response and "on no page". | **Not closed.** No later row puts them on a page (CLAUDE.md rule 13: built and reached by nothing). |
| 243(c) | "Still positive with the current taken out" reads "not assessed" for every band because no current-adjusted grid is saved under the daily settings. | **Not closed.** It will show nothing until someone builds that grid with decision 234's switch on. |
| 230 | The exploratory session's card "waits on a live watch". | Closed by 248 ("watched 2026-09-22"). |
| 246(f) | The time-of-day check "NOT RUN on the record". | Closed within 246 (run on his machine), corrected by 265. |
| 251, 240 | Coverage gap "reached by nothing"; the confound check "on no page". | Closed: 251 wired the gap onto the page; 264 put control analyses on both pages, reproducing 262's corrected numbers. |
| 271 | CI installs numba (no run cited in the row). | Closed by CI: the run on `a42d4517` passed (checked with `gh run list`). |
| 272 | Carry-over cannot be told from drift, because every step down came after its step up. | Not a code gap: it needs a visit whose currents are stepped down first, beside one stepped up first. A design choice for him. |

## Found in passing (stale text, nothing changed)

- `DEVICE_percept_rc.md` (the recipe table and the line after it) still calls 73.63 the live composed constant; it has been 72.16 since decision 211.
- The comment above the conversion constants in `Biomarkers/routines/analytics.py` still says the deployment fallback goes through the frozen model, which decision 21 replaced and 218 deleted.
- The header comment of `BiomarkerDataTimeline.js` describes a detail panel that does not exist (P-18).
- `ARCHITECTURE_modules_and_store.md` says "four superseded key generations ... and no sweeper"; decision 142 added a clean-up for the newest naming.
- The power-against-current routine keyed on the clinic sheets (`amplitude_response_cached`) exists with no caller (S-10).
