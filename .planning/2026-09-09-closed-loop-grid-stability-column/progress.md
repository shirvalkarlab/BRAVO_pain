# Progress: Closed-Loop grid stability column

## Session 1 — 2026-09-09

### How this task was arrived at
Started from a different question: why the Biomarkers page's "Export full grid to Closed-Loop"
button could not be clicked, and what the "Waiting on the Closed-Loop export field" note under it
was waiting for. Tracing that answered itself — the three response fields the button's gate watched
for are written by nothing in the repository, and Track D had already shipped the capability in a
different shape (a reader, not an export). That work landed as commit `da8b074f`.

Tracing it also surfaced this task, which is separate and still open: the grid the button now opens
shows "stability: not yet computed" on every row, and always has, because nothing sets the flag
that computes it.

### What was read (all read directly this session, not recalled)
- `Client/src/views/Reports/Biomarkers/BiomarkerHeatmapGrids.js` — the export gate and its comment.
- `Client/src/views/Reports/Biomarkers/index.js` — the placeholder click handler.
- `Client/src/views/Reports/ClosedLoopSim/index.js` — the grid panel's placement and its `cl-grid`
  anchor.
- `Client/src/views/Reports/ClosedLoopSim/BandSweepGridPanel.js` — `StabilityChip` and its
  "not yet computed" branch.
- `Client/src/views/Reports/ClosedLoopSim/useBandSweepGrid.js` — the request body, which sets no
  stability flag.
- `BRAVO/modules/Biomarkers/bravo_service.py` — `_attach_grid_export_columns`, the
  `include_stability` read, the store call site and its `sweep_sig is not None` condition.
- `BRAVO/modules/ClosedLoopDeployment/adapter.py` — `band_sweep_grid_for_closed_loop`.
- `artifacts/adr_2026-09-08_biomarkers_closedloop_matrix_export.md`, and decisions 67 and 68.

### Searches run and what they returned
| Search | Result |
|---|---|
| `closed_loop_export_key` / `exported_to_closed_loop` / `closed_loop_export_ready` in source | One hit each, all on the single line that reads them. Nothing writes any of them. |
| `IncludeCrossSettingStability` across the repository | `bravo_service.py` (the read), two `BandSweepGridPanel.js` lines that are a comment and a tooltip, and documentation. No client sets it. |
| `band_sweep_grid` across source | The Closed-Loop reader, its response key, and the panel that renders it — the pull path is real and wired. |

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Container suite after the button change | Unchanged from the prior session's count | `PASS=590 FAIL=0`, re-run fresh | Pass |
| New button label reaches the served bundle | Present in a chunk | Present in `806.ca7d0c28.chunk.js` | Pass |
| Old label and old note gone from the bundle | Absent everywhere | Both absent from every chunk | Pass |
| `cl-grid` anchor reaches both chunks | Present in Biomarkers and Closed-Loop chunks | Present in both | Pass |
| Button clicked in a real browser | Would confirm the navigation and the scroll | Not done — no signed-in session, credentials are a hard limit | Not confirmed |
| Flag-off vs flag-on grid cost, re-measured | Phase 1's first task | Superseded: measured the per-point split instead (findings §8-§9) | Pass |
| pymer4 vs lme4 split, 5 rounds | Unknown share | 60.2% lme4 (0.216 s), 40% pymer4 (0.143 s), marshalling only 0.002 s | Pass |
| 132-point grid, serial, 2 rounds | ~86 s predicted | 78.27 s / 78.25 s | Pass |
| 132-point grid, 16 workers, 2 rounds | Faster | 9.75 s / 9.81 s (8.0x) | Pass |
| Parallel answers equal serial answers | Identical | Same lrt_p checksum 52.212424853 across all 4 runs, 132/132 points | Pass |
| R not initialised in parent before fork | Must be false | `r_loaded_in_parent_before_run: false` every run | Pass |

### Errors
| Error | Attempt | Resolution |
|-------|---------|------------|
| Reported "no warnings in any touched file" from a build log my own reporting command had truncated with `tail`/`head`. | 1 | Wrong conclusion. Re-ran the build capturing the whole log: `Biomarkers/index.js` does carry three warnings, at lines 100, 276 and 519, all outside this change's single hunk at line 1147, so all three are pre-existing. Corrected in the decision-log entry rather than fixed silently. |
| Ran the container suite through `\| tail -5`, which discarded the `PASS=`/`FAIL=` line the run existed to produce. | 1 | Re-ran filtering for the count line instead of the tail. Lesson: filter for the line you need, do not trim to the end of the output. |
| Wrote a code comment claiming a grid on screen is always a grid in the store. | 1 | Checked the store call site: it is conditional on `sweep_sig is not None`. Softened the comment to say the ordinary case rather than promising a guarantee the code does not make. |

### Session 2 additions — the fast path is built
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Direct glmer == pymer4, all 132 points | 0 differences | 5,148 fields compared, 0 differing, 0 dropped/added | Pass |
| Direct glmer speed, alternating rounds | Faster | 77.80/77.03 s -> 36.97/34.85 s (2.15x) | Pass |
| Auto worker count from cores, not hardcoded | Detected | `auto_workers: 16` via `sched_getaffinity` | Pass |
| Parallel == serial through the public function | 0 differences | 5,148 fields compared, 0 differing, 0 missing | Pass |
| `on_point` progress callback fires per point | 132 | 132 | Pass |
| Failure policy stops after 3 consecutive raises | 3 attempted | 3 attempted, 129 never attempted, all reasons recorded | Pass |
| Fork guard falls back when R already started | Falls back | 2nd parallel run 35.84 s vs 1st 8.23 s — guard fired | Pass |
| Container suite | 590/0 | 590 passed, 0 failed (after fixing the guard test) | Pass |
| Host suite | Baseline + known 1 | 992 passed, 42 skipped, 1 failed (known, decisions 84/85) | Pass |

### Errors (session 2)
| Error | Attempt | Resolution |
|-------|---------|------------|
| Broke `test_run_for_participant_and_validate_band_core_both_use_the_shared_forecast_helper` (590 -> 589/1). | 1 | Real regression caught by a guard test doing its job: extracting `_band_validation_setup` moved the MatchDirection parse out of `_validate_band_core`. Fixed by pointing the guard at the function that now owns the parse AND adding a third assertion that `_validate_band_core` really delegates to it — strengthened, not weakened. |
| Filtered the suite output through `grep`/`tail` three separate times and discarded the very line I was running the command to get (PASS=/FAIL=, the failing test name, the pytest summary). | 3 | Stopped filtering at collection time: write the full output to a file, then grep the file. Logged as a repeated mistake rather than three separate ones — the pattern is the lesson. |

### Session 2, Phase 4
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Management command stores the grid | Stores | 132 of 132 points, 23.6 s, key recorded | Pass |
| Second run does no fitting (key decides) | already_current | `already_current: true`, 4.5 s | Pass |
| Stored grid reads back exactly | Same values | 132 points; ONE_THREE_LEFT@12.5 lrt_p 0.032285156521398184, identical to pre-storage | Pass |
| Closed-Loop reader picks up the stored grid | Shows answers | **Cannot be verified — the module will not import in the Django app (findings §14)** | Blocked |
| Container suite | 590/0 | 590 passed, 0 failed | Pass |
| Host suite | 992 + known 1 | 993 passed (+1 new guard test), 42 skipped, 1 failed (known) | Pass |

### Errors (session 2, Phase 4)
| Error | Attempt | Resolution |
|-------|---------|------------|
| Importing `bravo_service` from `adapter.py` broke 5 host tests with `AppRegistryNotReady` — my `except ImportError` did not catch it. | 1 | `bravo_service` imports `Server.models`, which needs Django's app registry; the host suite does not configure Django. Rewrote to read the store directly in `adapter.py`, which is far lighter and needs no Django. The duplicated kind constant is pinned by a new test that reads the writer's SOURCE rather than importing it. |

### Next session starts here
**Settle findings §14 first** — the ClosedLoopDeployment module does not import in the Django app,
so nothing built here can reach the page until it does. Then wire the sweep to launch
`compute_stability_grid` after the page's grid lands, and add the daily schedule (Phase 5).

### Session 3 — the background trigger wired, and two defects found by proving it
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| The sweep starts a run once its grid lands | Starts | `launched: true` on both the fresh and the served path | Pass |
| The run's answer lands under the key the page asked for | Same key | **Failed first** (`dc6cec1b` asked, `c02e9aca` written); after the fix `a2954bda` both | Pass after fix |
| A second request starts nothing | already stored | "the answer for this key is already stored", 3.758 s | Pass |
| Closed-Loop reader carries the answers | Rows answered | 264 rows, all from the store; 50 / 204 / 10 | Pass |
| Known case reproduces | 0.032285156521398184 | 0.032285156521398184 | Pass |
| Container suite | 590 + new | **605 passed, 0 failed** (+15) | Pass |
| Host suite | 993 + known 1 | 993 passed, 42 skipped, 1 failed (known, decisions 84/85) | Pass |

### Errors (session 3)
| Error | Attempt | Resolution |
|-------|---------|------------|
| The page and the background run named two different keys for one grid. | 1 | The computation re-derived the sweep's key from the echoed settings block, which is a different set of fields. The response now carries the sweep's own key and the re-derivation is deleted. Findings §16a. |
| Container suite 603/1: a served response stopped matching a fresh one. | 1 | The symptom. The cause was the launcher being reachable from the unit tests and starting real processes for a made-up participant. Guarded on the production store root. Findings §16b. |
| My own new assertion was a false positive on the payload's `rule_version` field. | 1 | Tightened to the key tuple's actual opening rather than a mention of the constant. |
| The Closed-Loop reader came back empty. | 1 | My probe passed a request dict where the function takes the participant uid. Not a code fault. |

### Next session starts here
**Phase 5, the daily schedule, needs the PI's call before anything is installed** — it changes how
his server runs. The command is built, tested and safe to run repeatedly (a run whose inputs have not
moved does no fitting). What is undecided is what starts it daily: a cron entry inside the container,
a service in the dev compose override, or an entry the PI installs himself. The shared
`docker-compose.yml` has deliberately not been touched.

### Session 3, Phase 5 — the daily pass
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| A full pass over every participant | Runs, exit 0 | 2 participants; one "no points" (not a failure), RCS08 already current 3.425 s | Pass |
| The loop runs a pass on its own | Logs a finished pass | `pass finished, every participant either stored an answer or had nothing to store` | Pass |
| A second loop refuses | Refuses | `another loop is already running (pid 2050348)` | Pass |
| The off switch | Does not start | `switched off by STABILITY_PRECOMPUTE=0; not starting` | Pass |
| A stopped-early run keeps the previous answer | Keeps it | Refused to store, previous 4-point answer intact; a complete run still replaces it | Pass |
| Container suite | 605 + 1 | **606 passed, 0 failed** | Pass |
| Host suite | 993 + known 1 | 993 passed, 42 skipped, 1 failed (known) | Pass |

### Next session starts here
Phase 6: the field-count and difference-count proof on RCS08 that turning the stability column on
ADDS fields and moves no existing scientific value, with timings in alternating rounds in the same
report. Most of the live evidence is already in findings §16c and §17c; the formal before-and-after
field comparison is what is missing.

**The daily loop takes effect on the next container start** — `boot.sh` runs once when the container
boots, so it is not running yet in the currently-running container.

### Session 3, Phase 6 — the equality proof and the 12.5 Hz resolution
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Inline answers vs background-stored answers | Identical | 5,148 fields compared, **0 differing**, 0 one-sided | Pass |
| Column off vs on: nothing existing moves | Only additions | 6,336 added (all `cross_setting_stability`), 0 dropped, 2 moved (both the column's own bookkeeping) | Pass |
| Timings, alternating rounds | Old slower | inline 292.70 / 289.87 s; page 10.60 / 10.64 s; background 15.93 / 13.56 s | Pass |
| 12.5 Hz: is it a code change? | — | Track D's own code gives 0.032285156521398184, identical to 12 s.f., matrix cached AND rebuilt | Ruled out |
| 12.5 Hz: is it the pain reports? | — | Truncating to 2026-09-07/08/09 changes nothing; same 421 rows, 37 groups | Ruled out |
| 12.5 Hz: is it new recordings? | — | 386 time-domain recordings, the same number decision 59 cites | Ruled out |
| 12.5 Hz: what IS it sensitive to? | — | Band width: p = 0.286 at 1 Hz, 0.032 at 5 Hz. Binarisation: 0.199 under a median split | Found |
| Re-anchored example passes | Passes | `test_track_d_grid_stability_translation.py` 7 passed | Pass |
| Container suite | 606 | **606 passed, 0 failed** | Pass |
| Host suite | 993 + known 1 | 993 passed, 42 skipped, 1 failed (known) | Pass |

### Errors (session 3, Phase 6)
| Error | Attempt | Resolution |
|-------|---------|------------|
| My §15 hypothesis (commit `46670ce7`'s chunk rule) was wrong. | 1 | That rule feeds the band-by-length sweep, not the stability fit, which reads the assembled spectrum matrix instead. Withdrawn in findings §19a rather than quietly dropped. |
| Filtered probe output through `grep`/`json.tool` three more times and lost the result entirely. | 3 | The same repeated mistake logged in session 1. Fixed the same way: write the whole output to a file, then read the file. Logged again because the repetition is the lesson. |
| Probe called `band_sweep_grid_for_closed_loop` with a request dict; it takes the participant uid. | 1 | My probe's fault, not the code's. Called correctly it returns 264 rows. |
| Probe called `finding_from_stability_result` with one argument and then treated its return as a dict. | 2 | It takes (raw, electrode, centre) and returns a `BandStabilityFinding` dataclass. |

### Next session starts here
Phase 7: land it. Nothing under `Client/src` changed, so no frontend rebuild applies.
