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
| Flag-off vs flag-on grid cost, re-measured | Phase 1's first task | Not started | Not started |

### Errors
| Error | Attempt | Resolution |
|-------|---------|------------|
| Reported "no warnings in any touched file" from a build log my own reporting command had truncated with `tail`/`head`. | 1 | Wrong conclusion. Re-ran the build capturing the whole log: `Biomarkers/index.js` does carry three warnings, at lines 100, 276 and 519, all outside this change's single hunk at line 1147, so all three are pre-existing. Corrected in the decision-log entry rather than fixed silently. |
| Ran the container suite through `\| tail -5`, which discarded the `PASS=`/`FAIL=` line the run existed to produce. | 1 | Re-ran filtering for the count line instead of the tail. Lesson: filter for the line you need, do not trim to the end of the output. |
| Wrote a code comment claiming a grid on screen is always a grid in the store. | 1 | Checked the store call site: it is conditional on `sweep_sig is not None`. Softened the comment to say the ordinary case rather than promising a guarantee the code does not make. |

### Next session starts here
Phase 1, first task: re-measure the flag-off and flag-on full grid build on RCS08 through the
bridge, in alternating rounds. Do not carry decision 68's 5.85 s / 326.7 s pair forward as fact.
