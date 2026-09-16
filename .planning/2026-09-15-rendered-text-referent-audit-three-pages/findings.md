# Findings: Rendered-text and referent audit of the three pages

(Observations and the two briefs. Agent reports are untrusted until each item is re-checked against
the served page or the component source.)

## 0. Context carried in
- Decision 172: note 1 of the Biomarkers "how to read this" drawer said "each row's value is the largest" --
  written for the retired table (`BandTimeSweepPanel.js`, one row per band, imported nowhere since decision
  66); on the heat map a row is a length of signal. The direction note's "the table's logistic fit" was the
  same class. Both live on the BACKEND (`analytics.BEST_OF_WINDOWS_OPTIMISM_NOTE`, `AUC_DIRECTION_NOTE`) and
  travel as data, so no frontend test could see the mismatch.
- Decision 173: the corrected line beside the scatter repeated "N ratings" that the plain line above already
  carried; the violin panel lacked the line the scatter had.
- Decision 171: "⏵ onset" appended to axis labels and hover; "corrected statistics are computed for this
  column's best cell only (1m, circled)" with no circle drawn.
- Decision 167 §5, Five Whys: no fixture-driven render test; `ClosedLoopSim/__fixtures__/rcs08_deployment_payload.json`
  exists and asserts nothing about what a clinician sees; the Biomarkers and Stim Optimizer pages have no fixture.
- Today's retirements whose words may still be on a page: the 300 s / 5 min length (decision 170); "ten
  lengths" / "best-of-ten"; the per-cell dash markers (decision 121); "6 min" onset, "250 ms" transitions,
  "range NOT published" for detection blanking (decision 169); "Export full grid" (decision 95); the arm strip
  and per-side tables (decision 157); "Device parameters to transcribe", "NOT COHERENT" (decision 123).
- The text surfaces: 57 page components under `Client/src/views/Reports/{Biomarkers,StimOptimizer,ClosedLoopSim}`
  (tests excluded), 24 `Fold`/drawer sites among them; plus every response sentence the pages print --
  `notes`, `why`, `human_text`, `detail`, `*_note`, `sentence`, `describe`, `reason`, `range_source`.
- Ready fixture: `ClosedLoopSim/__fixtures__/rcs08_deployment_payload.json` (2026-09-04 response; some fields
  have moved since, e.g. `edges.E1.source` added 2026-09-15). Missing: a Biomarkers sweep fixture and a
  Stim Optimizer two-stage fixture; `_agent_bridge/_review_fix_capture.py` already captures all three
  responses on RCS08 and can write them out.
- Jest harness works: `cd Client && CI=true npx react-scripts test --watchAll=false <pattern>`; two
  pre-existing failures in `panels.payload.test.js` (decision 147) are known and untouched.

## 1. The /swarm-review brief (paste this)

```
/swarm-review Referent audit of the three pages, read as a stranger. Scope: every string a clinician can see on the
Biomarkers, Stim Optimizer and Closed-Loop Deployment pages -- JSX literals under Client/src/views/Reports/{Biomarkers,
StimOptimizer,ClosedLoopSim}, AND every sentence the backend puts in the response that a card prints (fields named notes,
why, human_text, detail, *_note, sentence, describe, reason, range_source, in BRAVO/modules/{Biomarkers,StimOptimizer,
ClosedLoopDeployment}). Do NOT judge the science; today's question is only whether each string points at something that is
on the page today and is said once.

Four reviewers, read-only, one per perspective:
1. INVENTORY (per page): a table with one row per rendered string -- the text, the component and panel that draws it, the
   element it sits beside, and its REFERENT (what it points at: a row, a table, a circle, a dash, a length, a range, a
   button, a rule). Live probes allowed under BRAVO/_agent_bridge/_referent_*.py to read the served response for RCS08
   (2e3c75c00d7f4f37b53a048d195f11da).
2. STALE REFERENTS: every string whose referent is not on the page today, with the decision that retired it (start from
   findings.md §0 of the active plan: the 300 s length, "ten lengths", dash markers, "6 min", "250 ms", "NOT published",
   "Export full grid", the arm strip, "Device parameters to transcribe", "NOT COHERENT", "table", "row") and any others.
3. ADJACENT DUPLICATES: inside one visual block (a card, a caption plus its drawer, two lines above one plot), any fact,
   number or caveat printed more than once; name both places.
4. BACKEND-NOTE-VS-DISPLAY: every response sentence printed by a card, checked against the card that prints it -- does
   the sentence describe THIS display (a heat map, a triangle, a table row) or another one (the retired table, a figure
   that moved, a fold that no longer exists)? Include the module docstrings those sentences are generated from.

Every finding: file:line (or the response field and the generating function), the offending text verbatim, what it
should point at, and the fix labelled frontend / backend / both. 1500-2500 words each. House rules apply: plain
language; which module, which page, which panel, and whether it is on screen; no claim without its evidence in the same
paragraph. The orchestrator will re-check every item against the served page before keeping it.
```

## 2. The /swarm-execute brief (paste this once Phase 2 has produced the ranked list)

```
/swarm-execute Fix the ranked referent list in .planning/2026-09-15-rendered-text-referent-audit-three-pages/findings.md §3,
test-first. Workers: (a) QA -- capture two fixtures from the live RCS08 responses (Biomarkers sweep, Stim Optimizer
two-stage) via BRAVO/_agent_bridge/_review_fix_capture.py, then one jest render test per card on all three pages that
asserts the strings a clinician must read and asserts the retired words are absent (watch each fail first); (b) frontend
builder -- the JSX fixes; (c) backend builder -- the response-sentence fixes, each with a container or host test
(ps-scientific-writing 6a: compress tokens, keep every statistic, and check the referent before touching a sentence);
(d) verifier -- both suites, the live field-count and difference-count proof on RCS08 before/after (never a tolerance),
the frontend rebuild with the new strings found in the served chunks, the decision-log entry, push. A browser walk with
one screenshot per card is done only if a signed-in session exists, and is otherwise reported as not done.
```

## 3. Ranked list (Phase 2, verified 2026-09-15 evening)

Every item below was re-checked by the orchestrator against the component source or the served RCS08
response before being kept. Rank = how likely a clinician is to read it. "Test" names the fixture render
test (jest, `Client/src/views/Reports/<page>/*.referent.test.js`) or container/host test that pins the fix.
Kept 12; dropped 0; 2 reclassified (BND-5 is the duplicates reviewer's, not a referent; BND-1 already fixed).

| # | Id | Page · panel | On screen | Offending text (verbatim) | Referent today | Fix | Test |
|---|---|---|---|---|---|---|---|
| 1 | STALE-1 | Closed-Loop · "Choose a band" grid, AUC hover | always, every AUC cell | `BandSweepGridPanel.js:276` `, best of 10 lengths at ${...} s` (line 270 reads `chosen_as_best_of_n_windows`, 276 types 10) | the sweep tries 9 lengths since decision 170 | frontend: read the field on 276; fallback 9 on both lines | CL grid test: hover text says "best of 9 lengths"; string "10 lengths" absent |
| 2 | DUP-4 | Closed-Loop · "Full parameter recommendation", onset rows, "Why this value" fold | fold | `timing_recommendation.py:64` "A block bootstrap over the recordings puts 36-90 s in the same recommendation." | the live `robustness_note` on the same row says 27-30 s (committed band); the typed number is one contact's 2026-09-13 value | backend: drop the typed interval from the static `why`; the number belongs to `robustness_note` only | host test on `timing_recommendation.for_participant`: no digits-dash-digits " s" in the onset `why` |
| 3 | DUP-1 / BND-3 | Biomarkers · heat-map card, orange caption AND "how to read this" drawer | caption always; drawer folded | `analytics.py:6141-6146` appends "N of this contact pair's matched pain reports were answered from the device's own FFT snapshots ... most affected cell drew P% ..." to `notes`; `gridReadouts.deviceSpectrumBullets` prints the same 358 / 79% / ceil(N/30) in the caption | same fact twice in one card, two code paths that can drift | backend: stop appending to `notes` (the counts stay on the response); `bulletsFor` comment at `BiomarkerHeatmapGrids.js:117` is then true | container test: no `notes` entry contains "FFT snapshots"; BM fixture render: the drawer has no "answered from" bullet |
| 4 | DUP-2 | Closed-Loop · sticky verdict header | always, top of page | `DeploymentDecisionHeader.js:112-116` headline "(provisional: N of 3 intervals span zero)" + two `ProvisionalNote` boxes (lines 157-158) carrying "PROVISIONAL -- POINT SIGNS ONLY; 2 OF 3 INTERVALS SPAN ZERO" | the count printed three times in one glance; the two boxes are deliberate (ProvisionalNote.js:13-17) | frontend, narrow: headline says "(provisional -- see below)"; keep both boxes | CL header render: the string "of 3 intervals span zero" appears at most twice |
| 5 | STALE-2 | Closed-Loop · "Choose a band", fold "How to read this, and what it cannot tell you" | fold | `BandSweepGridPanel.js:377` "Each colour cell is the strongest of ten lengths of signal for that band" | nine lengths; the Biomarkers copy was fixed at decision 172, this copy was not | frontend: read the count from the row (`chosen_as_best_of_n_windows`) or `device_timing_ranges`; never a literal | CL grid test: fold text has no "ten lengths" |
| 6 | DUP-3 | Closed-Loop · parameter card, Upper/Lower LFP threshold rows | always | `design_rule_note` "... needs +-5 at this timing (3 s averaging / 30 s onset)" directly above `occupancy_note` "At the 3 s averaging duration in force, ..." | the timing stated twice in two stacked lines under one field | backend, small: `design_rule_note` says "at the timing shown on this card" when `exact_match`; occupancy keeps the number (its percentages depend on it) | host test on `prescription.design_rule_note`: exact-match case carries no "s averaging /" |
| 7 | INV-1 | Biomarkers · "Matched samples per channel" block under the summary | NEVER drawn since decision 77 | `Biomarkers/index.js:985-1003` reads `data.analytics.timedomain.spectral_feature_importance`, which the backend no longer computes (0 hits in `bravo_service.py`) | nothing | frontend: delete the block (~40 lines) and the comment at line 526 that points at it | BM page render: no "Matched samples per channel" string in the bundle |
| 8 | INV-2 | Biomarkers · older full-spectrum panel | NEVER drawn | `BiomarkerAnalytics.js:482-1083` builds `chPanels` (six panels with real titles) and returns only `tdPanels` (line 1195) | nothing; ~600 lines of display code | frontend: delete `chPanels` and its six builders after `grep` confirms no other reader (CLAUDE.md §2 principle 4: check decisions 66/77/80 first) | build clean; the six panel titles absent from every chunk |
| 9 | BND-2 | Closed-Loop · "Stimulation amplitude effects on band power, measured three ways" | NOT drawn (only `footer` and `absent_reason` are read, `ThreeSourceResponsePanel.js:280-288`) | `three_source_plots.py` per-comparison `headline`, `caption`, `label`, `subtitle`, `amp_axis_label`, `notes[]` -- e.g. "Right stimulator turned up 0.5 to 2 mA with the other side at zero ..." | a single-run chart decision 125 replaced with the pooled view | backend: stop building the five unread text fields (keep `footer`), or mark them unused in the builder; computing prose nobody prints is the hazard decision 172 came from | host test: the comparison dict carries `footer` and not `headline` |
| 10 | STALE-3 | Biomarkers/Closed-Loop · per-row `why` on `best_correlation_rows` / `best_auc_rows` | NOT drawn (no live reader of `.why`) | `analytics.py:6754` "... the strongest of 9 lengths ... which is what the SAME best-of-ten choice reaches ..." | one sentence contradicts itself; `_N_LENGTHS_WORD` exists two hundred lines up | backend: use `_N_LENGTHS_WORD` in `_corr_row_sentence`, `_auc_row_sentence` and `_verdict_against`'s docstring | container test: no row `why` contains "best-of-ten" |
| 11 | BND-4 | Closed-Loop · reliable-change panel | prose is hard-coded in the component; the backend's `what_it_means` is unread | `ReliableChangePanel.js:114-121` own fold text vs `reliable_change.what_it_means` | two copies of one explanation, compatible today | frontend: print `rc.what_it_means` in the fold and delete the hard-coded copy | CL fixture render: the fold text equals the fixture's `what_it_means` |
| 12 | DUP-5 / DUP-6 | Stim Optimizer · closed-loop checks (rate row) and sensing-evidence fold | folds | `stage_gate.py:387-391` detail restates the rates the open Numbers line shows; `SensingEvidenceTable.js:190-192` fold restates the cap the caption shows | the fold's job is to restate in prose (the file's own design) | leave both; record as deliberate | none |

Reclassified / not kept: BND-1 (the two notes decision 172 already fixed -- confirmed live, closed); BND-5
(the D26 sentence under three response keys -- the three consumers are different panels by design, and it is
a referent-correct sentence; not a duplicate within one block). Unread-but-harmless response fields the
reviewers listed (`two_stage.describe`, `device_timing_ranges.*_note`, `closedloop.protocol.*`,
`logistic_fit_crosscheck`, `length_rounding`, the `*_auc` device-spectrum grids) are recorded here and left:
they are data for a reader of the response, not text a card prints, and `length_rounding` was moved there on
purpose (decision 171).

Deliberate repeats, do not remove: the two `ProvisionalNote` boxes; the parameter card's two-mode view; the
four threshold-row notes as four separate checks; the DecisionStrip vs the two-stage fold's strata table.

## 4. Fixtures captured for Phase 3 (2026-09-15 19:00, live RCS08, serialised through `json_compliant_handler`)
- `Client/src/views/Reports/Biomarkers/__fixtures__/rcs08_band_sweep.json` (716,889 bytes): 9 lengths 3-60 s; L 1-3+ 12.5 Hz
  best r -0.473, n 166, at 60 s; `notes[0]` starts "The circled cell in each column is the LARGEST of the nine"; the
  backend snapshot note IS present in `notes` (item 3's RED assertion targets it).
- `Client/src/views/Reports/StimOptimizer/__fixtures__/rcs08_stim_optimizer_two_stage.json` (477,708 bytes): gate
  "Stage 2 MUST NOT START: 2 of 4 conditions block"; the amplitude condition `passed: null` with
  `history_above_ceiling.Left = {4.8, 4.5}`.
- `Client/src/views/Reports/ClosedLoopSim/__fixtures__/rcs08_deployment_payload_2026-09-15.json` (1,436,191 bytes):
  verdict "supported (point signs only; 2 of 3 intervals span zero)", `edges.E1.source = screening_historical`, onset
  range [0, 30000], robustness note 27-30 s. The 2026-09-04 fixture stays for the existing `panels.payload.test.js`
  (its 2 known failures are staleness, decision 147); new tests read the dated file.
- Captured by `BRAVO/_agent_bridge/_referent_fixtures_capture.py` (gitignored); no patient name in any file, the
  participant appears as the uid only.
