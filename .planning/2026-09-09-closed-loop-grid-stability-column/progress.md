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

### Next session starts here
Phase 4: run the grid in the background after the page's own grid lands, and store the result with
`writer=` and `provenance=`. **It must run in its own process** — a process that has already fitted
anything cannot fork, and the guard will silently fall back to serial (findings §13c).
