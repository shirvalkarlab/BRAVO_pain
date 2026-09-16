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

## 3. Ranked list (filled in Phase 2)
(empty until the reports are verified)
