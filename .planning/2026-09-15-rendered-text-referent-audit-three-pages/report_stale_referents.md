# Stale-Referent Review: Biomarkers, Stim Optimizer, Closed-Loop Deployment

**Method.** Grepped the live component source for the retired items named in the brief, then confirmed each hit against how the field is actually consumed (a comment is not a display; a field nobody reads is not a display). Where the source alone was ambiguous, I ran the three modules' real service functions for RCS08 through the bridge (`band_time_sweep_for_participant`, `run_for_participant` with `TwoStage: True`, and `run_for_participant` with the `ZERO_TWO_LEFT`/24.5 Hz candidate) and searched every string value the live response actually carries. Every item below states whether it is on screen today, and in which panel.

## Ranked findings

### 1. Closed-Loop Deployment — "Choose a band" panel — ON SCREEN (always visible, a hover tooltip on every AUC cell)

**Text, verbatim, `Client/src/views/Reports/ClosedLoopSim/BandSweepGridPanel.js:276`:**
```js
+ (row.auc_seconds != null ? `, best of 10 lengths at ${fmtNum(row.auc_seconds, 0)} s` : "")
```
Hovering any AUC cell in the "Choose a band" grid on the Closed-Loop Deployment page reads, for example, "AUC = 0.24 (95% interval 0.18 to 0.36), best of 10 lengths at 60 s, 42 pain reports."

**What it refers to:** the number of lengths of signal the band-by-length sweep tries before picking the strongest one for that column. **Decision 170** (2026-09-15) dropped the 300 s row, so the sweep now tries **nine** lengths, not ten. The backend already sends the true count on every row, as `chosen_as_best_of_n_windows` (confirmed live: this field is present and equals 9). The correlation tooltip two lines above (`corrTip`, line 270) correctly reads that field — `${row.chosen_as_best_of_n_windows || 10} lengths` — but the AUC tooltip never reads it at all; "10" is a bare literal with no fallback logic, so it is wrong on every single hover regardless of the underlying data.

**Fix:** frontend. Change line 276 to read `row.chosen_as_best_of_n_windows || 9` (and, for consistency, change line 270's fallback from `|| 10` to `|| 9`, since the fallback is dead today but would silently repeat this exact bug if the field ever went missing).

### 2. Closed-Loop Deployment — "Choose a band" panel — in a fold ("How to read this, and what it cannot tell you")

**Text, verbatim, `Client/src/views/Reports/ClosedLoopSim/BandSweepGridPanel.js:377-378`:**
```
Each colour cell is the strongest of ten lengths of signal for that band, so it is
optimistic by construction; ...
```

**What it refers to:** the same nine-vs-ten fact as item 1. **Decision 170** retired the tenth length. This sentence is the Closed-Loop page's own copy of the same claim the Biomarkers page already corrected (**decision 172**, "circled cell in each column is the LARGEST of the nine lengths tried") — but this one was never updated, and it lives in a different file (`BandSweepGridPanel.js` is a hand-written string, not fed from the backend's own `_N_LENGTHS_WORD`-driven note).

**Fix:** frontend. Change "ten" to "nine," or better, read the number out of the response the panel already has (`grid.band_time_sweep[channel].best_correlation_rows[0].chosen_as_best_of_n_windows`) so a future change to the sweep length cannot silently desynchronize the two pages again.

### 3. Backend — `Biomarkers/routines/analytics.py` — payload-only field, confirmed NOT rendered by any live card today

**Text, verbatim, generating function `BRAVO/modules/Biomarkers/routines/analytics.py:6752-6755` (`_corr_row_sentence`) and `:6774-6778` (`_auc_row_sentence`), field `best_correlation_rows[i].why` / `best_auc_rows[i].why`:**
```
"...the strongest of 9 lengths of signal for this band..." ... "which is what the SAME
best-of-ten choice reaches on shuffled pain scores, so once that choice is accounted for
nothing was SETTLED here"
```
Confirmed live for RCS08 on both the Biomarkers sweep and the Closed-Loop `band_sweep_grid` (same underlying sweep): the sentence names the correct count once ("9 lengths"/"nine lengths tried") and then, two clauses later in the same sentence, calls the identical choice "best-of-ten." This is an internal self-contradiction inside one generating function; `_verdict_against`'s own docstring makes the same "best-of-ten" claim.

**What it refers to:** the same nine-length sweep. **Decision 170** is the retiring event; the sibling note `BEST_OF_WINDOWS_OPTIMISM_NOTE` (line 6384) was correctly parameterized off `_N_LENGTHS_WORD` in decision 172, but `_corr_row_sentence`/`_auc_row_sentence` (which build the per-row `why` text) were not touched.

**Is it on screen today?** **No.** I checked every consumer of `best_correlation_rows`/`best_auc_rows` in both live pages (`BiomarkerHeatmapGrids.js`, `gridReadouts.js`, `BandSweepGridPanel.js`) and none of them reads `.why`; the only component that ever printed `row.why` is `BandTimeSweepPanel.js`, which is imported by nothing (confirmed: only reference outside its own file is a comment in `Biomarkers/index.js:23`). I am flagging it because it is a live inconsistency in a backend generating function that a card could easily be pointed at again (it is exactly the field a future "why does this cell say what it says" feature would reach for), and because the brief asks for backend sentences a card prints — this one currently is not printed, which is itself worth recording plainly rather than silently.

**Fix:** backend, low urgency since invisible today. Replace the hardcoded "best-of-ten" in both functions with `_N_LENGTHS_WORD` (or the numeral `n_windows`), matching what was already done for `BEST_OF_WINDOWS_OPTIMISM_NOTE`.

## Words that look stale but are correct

- **"the adaptive rate and pulse-width ceilings are not published and are not enforced"** — appears live and repeatedly in the Stim Optimizer two-stage response (`adaptive_envelope.statement`, `.source`, and inside `describe`/`provenance.stage1`, which are internal debug text, not rendered by any component — confirmed no frontend file reads `.describe` or `.provenance.stage1`). This is a *different* fact from the detection-blanking range that decision 169 resolved: the adaptive rate/pulse-width ceilings genuinely remain undocumented today (`StimOptimizer/routines/percept_adaptive.py:163`, `:245`, `:283`). Do not "fix" this — it is still true.
- **"range NOT published ... read off Advanced Settings," `BRAVO/modules/ClosedLoopDeployment/prescription.py:691-703`** — this now applies to exactly one field, the Adaptive Startup Delay, per decision 169's explicit statement that `UNPUBLISHED_RANGES` now names the startup delay alone. Detection blanking was correctly moved to its own sourced range (`prescription.py:649`, "selection range … tablet") in the same decision. Leave both as they are.
- **"5.0 mA," `StimOptimizer` provenance strings** (`safety_ceiling.py:19,22,49,55`, and the live `safety_ceiling_provenance`/`ceiling_by_side.*.provenance` fields) — these are historical-provenance sentences that correctly say "was 5.0 mA … now 4.5 mA" (decision 160). They are not a stale current value; they are the record of what changed and when, and the current ceiling shown everywhere else on the page (`CurrentMapCard`, `TitrationSessionCard`, `ClosedLoopChecks`) is read live from `plan.ceiling_mA`/`cl.safe_ceiling_mA_by_side`, never hardcoded.
- **`SensingEvidenceTable.js:139`, "the flat `${cl.amp_hard_limit_mA}` limit"** — this reads the *module's own hard limit* (5.0 mA, `objective.AMP_HARD_LIMIT_MA`), which decision 160's own text explicitly distinguishes from "a participant's stated ceiling" (4.5 mA). Both numbers are legitimately different things and both are still 5.0/4.5 respectively; this is not a stale referent.
- **`gridReadouts.js:16-19`, the doc-comment "On RCS08 the strongest cells sit at 5 min, which is beyond"** — this is a JS docstring above the file, not rendered text. It is now factually stale (decision 170 moved the strongest cell to the 60 s row on RCS08), but since it never reaches the page I am not ranking it as a clinician-visible item — worth a one-line comment fix in passing, nothing more.
- **`stateTracks.js` "Sign agreement" / "SIGNS AGREE" / "SIGNS DISAGREE"** — already correctly renamed per decision 123; the internal field name `coherence.coherent` is unchanged on purpose (decision 123 explicitly says only the on-screen words changed), so grepping for "coherence" in the source is expected and is not a defect.
- **`EvidenceTrianglePanel.js`, `isScreening`/E1 source label** — already correctly wired to `edges.E1.source === "screening_historical"` per decision 168; the "screening statistic, not a measurement" label only fires when the field says so, confirmed against the live response's `edges.E1.source` on RCS08.
- **"strongest of ten lengths" appears 60+ times in the live Closed-Loop and Biomarkers responses' `.why` fields** — all traced to the single generating-function bug in item 3 above, not 60 independent defects.

## What I checked and found clean (no stale text)

- Per-cell dash markers (decision 121): removed from both heat maps; confirmed by comment at `BiomarkerHeatmapGrids.js:323` and by the absence of any dash-drawing code tied to `n_pain_reports_from_device_spectrum`.
- Dual onset "6 min," transition "250 ms," and detection-blanking "range NOT published" (decision 169): all three are now correctly sourced through `DecodeCommon/device_ranges.py` and printed with their real provenance (tablet vs. FDA discrepancy stated plainly); confirmed live in `device_timing_ranges.onset_note`.
- "Export full grid to Closed-Loop" (decision 95): no occurrence anywhere in the three page directories; the live button reads "Open this grid in Closed-Loop."
- Arm strip and per-side "what to test next" tables (decision 157): no live component renders them; only a removal comment remains in `StimOptimizer/index.js:9-15`.
- "Device parameters to transcribe" / "NOT COHERENT" (decision 123): both renamed; only comments recording the old names remain.
- "Table"/"row" describing the heat map (decision 172): the two notes the PI flagged are fixed and test-pinned; no other place in `BiomarkerHeatmapGrids.js` uses "table" loosely.
- "rho = -0.013"/"n = 417" (decision 166): absent from the live Closed-Loop response; the gate now recomputes and quotes a live number ("rho = -0.04, p = 0.895, 0 above 4 mA" was the value found by the earlier session, not hardcoded here).
- "Timeline's own match window" slider (decision 120): only a removal comment remains at `Biomarkers/index.js:370`.
- Demo participant (decision 110): `DEMO_BIOMARKER` does not appear anywhere in the three page directories.
- "12 of 12 hemispheres"/per-side model wording: not found anywhere in the current frontend or backend source for these three modules; likely a pre-decision-157 artifact that was fully removed with the old arm-strip code, not a surviving fragment.

## File paths referenced

- `/Users/pshirvalkar/dev/BRAVO_pain/Client/src/views/Reports/ClosedLoopSim/BandSweepGridPanel.js` (items 1 and 2)
- `/Users/pshirvalkar/dev/BRAVO_pain/BRAVO/modules/Biomarkers/routines/analytics.py` (item 3, and the correctly-fixed `BEST_OF_WINDOWS_OPTIMISM_NOTE` at line 6384 for contrast)
- `/Users/pshirvalkar/dev/BRAVO_pain/Client/src/views/Reports/Biomarkers/gridReadouts.js` (stale internal comment, not user-facing)
- `/Users/pshirvalkar/dev/BRAVO_pain/BRAVO/modules/ClosedLoopDeployment/prescription.py` (confirmed clean)
- `/Users/pshirvalkar/dev/BRAVO_pain/BRAVO/modules/StimOptimizer/routines/percept_adaptive.py` (confirmed clean — genuinely-unpublished fact)

No repository file besides the three disposable, now-deleted probe scripts (`BRAVO/_agent_bridge/_referent_stale_probe{1,2,3}.py`, already removed) was written or modified during this review.