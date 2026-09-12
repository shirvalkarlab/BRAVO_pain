# Progress — Closed-Loop Deployment page redesign

## 2026-09-11
- Session opened from the sweep handoff (commit 3cfa4c73, tree clean). New plan directory created,
  `.active_plan` moved here, `.mode` = inject-smart as the project convention. The PI's brief copied
  into findings §1 so this plan stands alone. Rules read: CLAUDE.md, HOUSE_RULES, bravo-session-rules.
- Phase 1 discovery: read index.js (render order, 14 sections), BandSweepGridPanel.js,
  ThreeSourceResponsePanel.js, three_source_plots.py (headings/captions are SERVER text),
  three_source_response.py build_for_participant (one tab per run, page slice = 4 runs),
  amplitude_effect.py (decision 55 pooling, time-domain route only), BiomarkerHeatmapGrids.js
  (PlotlyHeatmap + ContactStrip ordering + Medtronic labels from the server), stateTracks.js
  ("Sign coherence" track), DeviceRuleLedger.js header. Findings §2.1–2.8 written.
- Found: OrbStack is down (docker daemon unreachable; bridge job no result in 30 s). Live checks
  and the container suite wait on it; design work does not.
- Phase 2: loaded ps-scientific-visualization and artifact-design; built the mock-up
  (scratchpad/cl_redesign_mockup.html, ~330 lines, placeholder numbers labelled as such), published
  as an artifact and sent to the PI as a file. Seven questions recorded in findings §3. The in-app
  browser cannot open local files and is not signed in to claude.ai, so the one pre-publish look
  was not possible; the live artifact is the review surface. Waiting on the PI.
- PI answered all seven questions; recorded as decisions 1–7 (+4b). Plan restructured: Phase 3
  heat map, 4 text/labels, 5 pooled three-source (backend option B), 6 amplitude-vs-power research
  (swarm + descriptive analysis), 7 prove/land, 8 simulation design last. OrbStack is up again
  (containers "Up 7 minutes" at check).
- /swarm-research invoked by the PI for Q6: four worker-research agents dispatched in the
  background (A empirical shape, B fitting/peak methods, C artifact vs physiology, D pain targets),
  outputs to artifacts/research_2026-09-11_amp_power_{A,B,C,D}_*.md. RCS08 capture probe run in
  the container: 11 runs, 3.7 s, 3,001 rows; findings §5. Live grid payload checked
  (probe_grid_fields.py): full grids + Medtronic labels + 264 stored stability answers present.
- Phase 3 built: BandSweepGridPanel.js rewritten as the heat map (22 band rows; r and AUC colour
  columns that stretch to the card's width; correction and stability symbols; one radio per row;
  tabs L-then-R in Medtronic notation from the server's display_short). Shared helpers moved out:
  binarizationModel.diverging/divergingRgb and contactOrder.contactSortKey/orderContacts (one
  definition for both pages). index.js passes `committed` (contact + centre) instead of the old
  hemisphere. Build logs /tmp/claude-502/build_phase3.log (1 warning, fixed) and build_phase3b.log
  (0 warnings in touched files). Served chunk 703.192fc0a4.chunk.js carries "Choose a band" and
  "Stable across"; "Browse the calibrated grid" absent from every chunk. NOT yet watched live.
- Worker B (fitting methods) finished: artifacts/research_2026-09-11_amp_power_B_fitting_methods.md
  (32 sources). A, C, D still running.
- Phase 4 built. New Fold.js (one reveal/hide control for the page). Folded: evidence triangle's
  reading conventions, per-edge estimator notes and sign-agreement method; band-stability "what the
  answer rests on"; reliable-change method; prescription's read-back rationale; identity badge
  note; three-source whole-range row + footer (mounted on first reveal, Plotly zero-width trap).
  Ledger: "Device rules" with a counts strip + violated rows visible + "Show all N rules" fold.
  Renames: Sign agreement / SIGNS AGREE / SIGNS DISAGREE; Full parameter recommendation; the
  three-source title; backend three_source_plots._short -> Time domain derived LSB / PSD derived
  LSB / Direct LSB recording; subtitle, per-column captions and footer compressed (no number
  dropped; the tests' phrases kept). Host suite in the container: **1019 passed, 42 skipped, 0
  failed** (/tmp/claude-502/host_phase4.log). Build: strings in 494.0a9b80d1.chunk.js; old
  strings absent (build_phase4.log); one unused-import warning removed, rebuilt (build_phase4b.log).
  NOT yet watched live; workers not yet HUP'd for the backend caption change.
- All four literature workers finished (A 18 sources, B 32, C ~12 primary, D 18). RCS08 shape
  analysis run (probe_amp_power_shape.py, 14.7 s): findings §6.
- Phase 6: synthesis written (artifacts/research_2026-09-11_stim_amplitude_vs_lfp_power.md) with
  the recommendation: no peak into the triangle; pooled slope + curvature caveat. Gunicorn workers
  HUP'd after the backend caption change. Container suite started in the background
  (/tmp/claude-502/container_phase4.log). Nothing committed yet: waiting on the PI's answers and
  a live look. Uncommitted: 14 source files + rebuilt bundle + planning + 5 research artifacts.
- Container suite finished: **PASS=626 FAIL=0** (/tmp/claude-502/container_phase4.log). Both
  gates green after the last code change; bundle rebuilt; workers HUP'd. Holding the commit until
  the PI has answered the three questions and looked at the page live.
- Live look with the PI signed in (his Chrome): heat map, folds, renames, counts strip, three-source
  panel all render; whole-range figures draw at 1,550 px on reveal (Plotly trap handled). Four
  things found and fixed from the look: "coherence test" wording in two blurbs -> "sign-agreement
  test"; duty-cycle caveats folded (count kept visible); prescription note + precision paragraph
  folded; triangle edge label "direction not established" -> "not established" (the two were
  overlapping). Rebuilt three times (build_phase4c/d.log, 0 warnings in touched files); the last
  bundle main.936bfb2f.js / 494.8634baee.chunk.js watched loading; "coherence test" absent from
  every chunk and from the live page. No Python changed after the suites ran.
- Decisions 122–124 and open item 30 written to DECISIONS_and_open_items.md.

## HANDOFF — where things stand at the end of the 2026-09-11 session (read this first next time)
**Branch `PS_closedloop_deployment`.** Phases 1–4 and 6 of this plan are done and committed (the
commit hash is in `git log -1`); Phase 5 is next, Phase 7 (prove/land the rest) and Phase 8 (the
simulation design, last by the PI's order) follow.

**What landed:** the Closed-Loop page's grid as a heat map with symbols and one radio per row
(decision 122); every explanatory paragraph folded through `Fold.js`, the ledger as a counts strip
with violated rows visible, and the five renames including the three server-side column headings
(decision 123); the Q6 research — four worker reports and a synthesis in `artifacts/` — with the
PI's answer: the triangle's current→power edge stays the pooled slope, and he expects to have to
model the peak and the descent past it once the data allow (decision 124, open item 30).

**Open on the PI, nothing blocked:** the titration protocol in open item 30 (a clinic decision);
the 2025 UCSF closed-loop preprint needs institutional access before its amplitude data can be
used (synthesis §9).

**Phase 5 facts already measured (findings §5):** 11 runs on RCS08, all built in 3.7 s warm; the
device's own FFT route has 0 settled points in every run; the programmed centre differs run to
run, so only the time-domain route pools across visits at one band; the left side has TWO sensing
contacts with runs (L 1⁻3⁺, L 0⁻2⁺), the right side one (R 0⁻3⁺). The pooled table is per
(contact, centre) and never across contacts (decision 74). Option (b) stands (decision 10).

**Operational notes:** the bravo-session-rules skill names `SESSION_HANDOFF_*.md` and
`MEGA_HANDOFF.md`, neither of which exists at the repo root — the record is
`DECISIONS_and_open_items.md` + this plan's three files, as CLAUDE.md §6 says. The in-app browser
pane cannot open local files and is not signed in; the PI's own Chrome (claude-in-chrome tools) is
where the live page is watched. After a backend edit: `docker exec bravo_pain-bravo-server-1 kill
-HUP 1`. Suite logs are in /tmp/claude-502/.
- Landed: commit 590b9ffa pushed to origin/PS_closedloop_deployment (40 files, +1853/-402); tree clean.
- Phase 5 backend: run_points.py (stored kind three_source_run_points, pooled_view_payload, the
  anchor = mean of per-run centroids in LINEAR device units, decision 12), adapter write/read + a
  pooled-only request path (`ThreeSourcePooled: 1`), the full-build rule extended so a missing
  points table forces every run to be built (the first live run refused to write in the steady
  state — found and fixed). Live on RCS08: table written, 3,017 rows / 11 runs; the pooled-only
  request answers in 0.62 s, 241 KB; **stored points vs a fresh in-memory build: 63,357 fields
  compared, 0 differing**; the pooled table's entry was NOT rewritten (sidecar still 2026-09-10
  19:17). Two earlier non-zero counts (475/2,910 and 325/4,410) were my CSV round-trip losing
  float digits, not the data — retracted. Logs /tmp/claude-502/pooled_view_probe*.log.
- PI (asleep): implement everything myself; prefetch the pooled data after the first figures
  load (done: the hook fires once the report's data arrives, own slot CL.pooled); keep going for
  six hours on timers; hand anything stuck >30 s to agents.
- Phase 5 frontend: ThreeSourceResponsePanel.js rewritten as the pooled view (side tabs, contact
  chips within a side, drawn at the committed centre, one marker per run, pooled dashed line
  through the anchor; fold = pooled slope at every band ±2 SE with striped bands); the hook
  useThreeSourcePooled fires after the report's data arrives (slot CL.pooled); index.js wired.
  Watched live on RCS08 in the PI's Chrome: both tabs, "L 1⁻3⁺ · 4 runs / L 0⁻2⁺ · 1 run" chips,
  13 points across 4 visits, pooled slope −3.62 ± 9.97 (p = 0.7258); three requests to the
  endpoint (grid, report, pooled); the fold figure draws at 910 px.
- E1 = pooled slope (decision 9): edges.pooled_actuation_edge, pipeline.run(pooled_e1=…),
  adapter reads the stored row for the first candidate and serialises edges_historical; six
  tests in test_pooled_e1.py. Before/after measured: findings §7. Host suite before the E1
  change: 1032 passed / 42 skipped / 1 failed (my own new test's monkeypatch target; fixed);
  container suite 626/0 (/tmp/claude-502/{host,container}_phase5.log).
- Full host suite after the E1 change: **1039 passed, 42 skipped, 0 failed** (host_phase5b.log).
  Bundle main.505c09b9.js / 334.44a5aaa5.chunk.js; triangle caption follows the new unit; watched
  live. Phase 8 design written (artifacts/design_2026-09-11_closed_loop_simulation_module.md): the
  existing replay becomes model M0; M1 feeds the pooled slope back with a settling time; M2 is the
  peaked case (decision 11's pivot, "not assessable" on RCS08 today); M3 resamples runs for
  intervals; stored as its own kind refused to stim_optimizer; five questions for the PI.
- Landing Phase 5 + the design as one commit.

## HANDOFF — end of the 2026-09-11 overnight session (read this first next time)
**Everything the PI asked for in the redesign brief is built, proven and pushed** (commits
590b9ffa and the Phase 5 commit named in `git log -2`). Gates after the last change: host 1039
passed / 42 skipped / 0 failed; container 626 passed / 0 failed; bundle rebuilt and watched live.
**Open on the PI:** the simulation design's five questions (§7) and its go-ahead; open item 30 (the
titration protocol); the 2025 UCSF preprint access. **Nothing is blocked and nothing is queued.**
Decisions 122–126 carry every change with its measurement. Probes for this session are in
`_agent_bridge/_probe_tl/probe_{amp_power_*,pooled_*,points_equal,e1_before_after,grid_fields}.py`
(disposable). The stored kinds added: `three_source_run_points` (decision 125). The page's report
now carries `edges_historical` beside `edges` (decision 126).

## 2026-09-11, Phase 8 build (the PI answered the design's §7 and gave the go-ahead)
- Steps 1-7 built: within_visit returns the quadratic's coefficients; POOLED_FIELDS + v2 rule
  version (+ pooled_shape_stored_for_current_key in the full-build gate, else the v2 table would
  never be written in the steady state); StimOptimizer/routines/amplitude_response.py
  (ResponseCurve); pipeline keeps replay_input; ClosedLoopDeployment/simulation.py (M0/M1/M2 one
  vectorised loop, M3 run-resampled, device-clock regridding of the 3 s pieces); adapter
  simulation_inputs/write/read/serve; bravo_service ClosedLoopSimulation: 1; provenance kind.
- tests/test_simulation.py: 13 passed (container run 13:17). Test 6 as FIRST written called
  store.clear() after restoring the override -> wiped the production closed-loop store (the
  decision-116 slip, mine); reordered; the report rebuilt the entries.
- Live probe 1 (13:06): report 119.7 s cold; simulation 2.8 s over 49,267 pieces; read-back
  0.53 s / 6.9 KB; M1 active; tau measured 3.0 s (4 of 11 runs; at the 3 s floor). Found: 103 of
  119 stretches refused by the 5 % uniformity rule (tile jitter), nothing drawn -> regridding
  added. M0 vs replay per stretch on uniform stretches: 5 of 5 fields equal.
- Frontend: useClosedLoopSimulation.js, ClosedLoopSimulationPanel.js (figures A/B/C, derived
  headline, folded method), CL.simulation slot, index.js (cl-duty removed, cl-simulation after
  cl-signoff), header nav, snapshot section; DutyCyclePanel.js deleted and its jest block removed.
- Regridding (regrid_stretches): pieces on the device's 3 s clock per stretch (cumulative
  rounding of each gap, no drift). Live: 114 of 119 stretches run (was 16), 36,244 steps = 30.2 h
  of streaming; 25 cells without a piece, 3 merging two; longest stretch (75 min, 2025-07-27)
  drawn with the M3 band. RULE_VERSION bumped twice (v2 clock, v3 windows from the stored runs)
  because the numbers changed and the key had not.
- Probe 4 (13:24, ONE_THREE_LEFT 20.5 Hz): report 31.6 s; simulation 5.5 s; read-back 0.42 s,
  87 KB; M0 vs replay.dual_threshold on the same 114 regridded stretches: 5 fields, 0 differing
  (0.264651 / 0.278612 / 13,364 / 1359 s / 1143 s). M1: upper-limit time 26.5 % -> 23.8 %
  (M3 18.9-65.5 %), transitions 442 -> 446 /h, mean amplitude 3.05 -> 2.98 mA; tau 3.0 s
  measured on 4 of 4 runs, at the 3 s resolution floor (said so). v1-vs-v2 pooled comparison NOT
  measured: the v1 entry was lost to my own wipe before it could be read (test 8 + unchanged
  within_visit tests cover the additive change).
- Host suite (b) 2 failed / 1050 passed: test_one_store (my load_newest line named the module
  and DIR on one line -> split) and test_core (replay_input, the unused step-4 field -> removed).
  test 5 was order-dependent (two within_visit module objects) -> patches S._wv.
- Live in the PI's Chrome (13:31+): card present, cl-duty gone, 3 Plotly figures at 1348 px,
  captions from the numbers; the page's committed band is L 0-2+ 24.5 Hz (1 run) -> "no response
  curve" headline is the honest three-state answer; found the eviction/read-by-newest defect
  (decision 24) -> KEEP 6 + candidate-tag match + the page sends its candidate; headline says the
  fit's own reason.
- Final gates on the settled code (13:44-13:46): host 1053 passed / 42 skipped / 0 failed
  (/tmp/claude-502/host_phase8f.log); container PASS=626 FAIL=0 (container_phase8f.log).
- Grids my wipe destroyed restored by hand: precompute_band_sweeps (6 scores stored, 8-11 s each)
  and compute_stability_grid (132 of 132 points) for RCS08.
- Live (13:48, main.8a55..): card renders on L 0-2+ 24.5 Hz with the fit's own reason in the
  headline, 3 figures, 26.0 h in 83 stretches; the sim fetch now keys on the report's computedAt
  so a recompute refetches it (it did not before: watched "no simulation stored yet" beside a
  report that had just stored one).

## HANDOFF — end of the 2026-09-11 Phase 8 session (read this first next time)
**Every phase of the redesign is built, proven and pushed.** Phase 8 = the "CL-DBS simulations"
card (decision 128) with the response-curve plant (decision 21 here), the device-clock regridding,
the per-candidate stored entries (decision 24), and the wipe incident (decision 129). Gates after
the last backend change: host 1053 / 42 skipped / 0 failed; container 626 / 0. **Open on the PI:**
look at the card (both bands); open items 29 and 30. **Watch for**: any test touching the store
must clear only while its own override is set (decision 129, third time); the simulation's key
carries the candidate and the rule version -- bump RULE_VERSION whenever the stored numbers would
change (v4 today). Probes: `_agent_bridge/_probe_tl/probe_simulation_{live,diag}.py`.
