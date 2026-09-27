# Stim Optimizer page: a redesign proposal, with the code for each phase

**Written 2026-09-12. Nothing in this document has been built.** Every screen described here is a
proposal; the page a reader opens today is the one in §1. The code for each phase sits under
`artifacts/design_2026-09-12_stim_optimizer_page_redesign/` as patch files and full component
files, checked to apply cleanly in order, and none of it has been applied to `Client/src` or to
`BRAVO/`.

**Where this lives.** The Stim Optimizer module; the page at `/reports/stim-optimizer/<participant>`
(`Client/src/views/Reports/StimOptimizer/index.js`), fed by `/api/queryStimOptimizer`
(`BRAVO/modules/StimOptimizer/bravo_service.py`, `run_for_participant`). The two-stage plan is the
card at the foot of that page (`TwoStagePlanCard.js`, added earlier the same day), fed by a second
request to the same endpoint with `TwoStage: true`.

**The brief, verbatim (PI, 2026-09-12):** "look over the whole stim optimizer module and suggest
significant frontend redesign, to improve readability, prioritize display of actionable items and
use visuals instead of text when possible to communicate outcomes. Make sure to replace any text
words like 'zero' with numbers especially using standard medtronic nomenclature for contacts like
Left 0-3+". His follow-up: use the existing "L 0⁻2⁺" convention, and deliver every code edit as a
patch the orchestrator can apply once he approves a phase.

**The mock-ups** are a design canvas, saved as an artifact:
https://claude.ai/code/artifact/af01c390-9ace-463d-a7e8-bee167546df2 — three boards: the page as
it is (to scale), the proposed page with RCS08's real numbers, and the notation rule. The same
three boards are plain HTML files he can open from disk:
`artifacts/design_2026-09-12_stim_optimizer_page_redesign/mockups/{Today,Main,Notation}.dc.html`
(and `stim-optimizer-redesign.html`, the whole canvas in one file).

**Every number in the mock-ups is RCS08's, read on 2026-09-12** by sending the page's own request
through the bridge (`BRAVO/_agent_bridge/_probe_tl/probe_page_redesign_print.py`; request
56.32 s without the two-stage block, 66.44 s with it, of which the block took 12.04 s). The
programmed contacts and each side's own pulse width come from a second probe
(`probe_contacts_in_force.py`). Nothing is a placeholder.

---

## 1. What the page shows today, section by section

Counted from the strings in the two source files (comments stripped) and the strings the RCS08
response puts on the page (`count_words.py`, method: every string literal and JSX text node with
at least two words; server strings of 6 words or more). **3,095 words in the strings the page
renders for RCS08 with its one fold closed: 1,496 written into the source, 1,599 sent by the
server.** Of the 1,496 in the source about 280 sit in branches that do not render for RCS08 today
(the loading state, the two unused verdict-banner variants, three hover tooltips, the
figure-failure box), so a reader sees roughly 2,800.

| # | Section (its title on screen) | What it is | Verdict | Words |
|---|---|---|---|---|
| 1 | Recompute bar and "last built" line | shared controls; unchanged by this proposal | supporting | shared |
| 2 | Blue banner: "The data do not yet support a stimulation parameter recommendation" | the verdict, then 6 bullet sentences from the model (34 to 80 words each) | **supporting, wrongly placed first**: the verdict is right but the reader gets 472 words and no number to act on | 155 + 317 = 472 |
| 3 | "Closed-loop readiness (Adaptive Therapy)" | a badge "12 of 50 cells deployable", a 45-word caption, a 20-row table whose first column is the raw key `ONE_THREE_LEFT`, 8 rows carrying a 21- to 55-word sentence, and a 110-word footer | **actionable content in a supporting form**: the answer (12 of 50, best `ONE_THREE_LEFT` at 165 Hz) is there, but the contacts spell their numbers as words and the reasons sit in the table | 47 + 14 + 338 = 399 plus the table |
| 4 | "Evidence base" | 6 counts and 4 state chips | supporting | 62 |
| 5 | "Arms" | a 7-column table of the 4 arms, one arm per row, and 2 explanatory paragraphs (150 words) | **actionable** (the gain column is the one number the verdict rests on) but read as text: "+0.32 (−1.13 to +1.77)" | 205 plus the table |
| 6 | "left_leg · Left" (the selected arm) | provenance and kernel lines, 5 server-drawn figures (620 px + 4 × 380 px = 2,140 px of chart), then "Where the model is most uncertain" with 2 paragraphs (200 words) and a 10-row table to 3 decimals | **noise on first read**: the figures are the model's working, correct and kept, but they are on screen before the reader has a single decision in hand; the queue is actionable | 149 plus the figures and table |
| 7 | "Two-stage plan: open loop, then the gate, then closed loop" | the frozen setting per side as sentences with 4 and 5 reasons each, the range adaptive mode can use as a sentence, 2 exclusions as sentences, the check's verdict "Stage 2 MUST NOT START: 1 of 4 conditions block" with 4 condition sentences (19 to 70 words), the evidence sentence, then closed loop's refusal repeated | **the most actionable content on the page, and the most prose**: 1,465 words in one card, the 4 checks two thirds of the way down | 535 + 930 = 1,465 |

**Ratio of prose to values.** Sections 2, 3 and 7 carry 2,336 of the 3,095 words. The four numbers
a clinician would decide on (what is programmed, what the search prefers, whether the difference is
resolved, whether closed loop may start) appear in sections 5 and 7, after 872 words of sections 2
to 4.

---

## 2. The five biggest readability problems, with the evidence

1. **The decision is not on the page as a decision.** "What is programmed now" appears nowhere as
   numbers except inside the two-stage card's sentence "Setting in force today: 55 Hz at 100 µs",
   which names no current and no contacts and is the same for both sides. The current in force is
   in the "In force ± SD" column of the arms table only as a pain value (0.48 ± 0.99), never as
   milliamps; the 3.0 mA (Left) and 2.5 mA (Right) in force are printed nowhere. The preferred
   setting per side is a sentence: "Left: the open-loop search freezes 55 Hz at 100 µs, preferred
   4.5 mA (currents delivered so far 1.0–4.8 mA; fitted on 11 stretches of unchanged settings) —
   not yet resolved: the chosen rate 55 Hz is the rate already in force. Retaining the setting in
   force is not the same as having resolved it…" (50 words before the first number a reader can
   act on).

2. **Contacts spell their numbers as words, and no stimulation contact is shown at all.** The
   readiness table's first column is `ONE_THREE_LEFT`, `ZERO_THREE_RIGHT`; the two-stage card prints
   the sensing contact as `(ZERO_TWO_LEFT, Left, 55)`. The response carries `contacts: null` with a
   note that Stage 1 does not choose contacts, so the contacts the device is programmed to (ring 2
   on the left, rings 1 and 2 on the right, read from the settings stream on 2026-09-12) reach no
   page. This is the PI's own complaint.

3. **The one check that blocks closed loop is a 70-word sentence printed 3 times.** "the frozen
   rate and/or pulse width are NOT resolved against their uncertainty on Left (rate resolved:
   False, pulse width resolved: False); Right (…)…" appears under the check, under "Closed loop
   did not start", and inside the folded provenance. The 4 checks are 212 words of sentences with
   a ✓/✗ beside each; the numbers the sentences carry (55 Hz, 12 of 18 bands, d = 1.83,
   229.7 → 137.1 device units at 1.5 → 4.5 mA, 1.0–4.8 mA) are inside the sentences and not beside
   the symbols.

4. **The gain against its uncertainty, which the whole verdict rests on, is a text range.** The arms
   table prints "+0.32 (−1.13 to +1.77)"; that the band straddles 0 is what "not resolved" means,
   and a reader has to compute it. The 2 paragraphs under the table (150 words) explain the rule
   in prose on every load.

5. **Sentences stand in for numbers throughout.** "no deployable control signal — 0 of 50
   screened cells qualified" for a count; "Stage 2 MUST NOT START" for a verdict ("Stage 2" is a
   code name); "Left amplitude levels 22" for a fact no decision uses; the queue table prints
   40.000 Hz and 5.000 mA; the excluded settings are 82 words of sentence for what is two points
   on a rate axis (40 Hz at 4.5 mA, predicted −0.13 points, ruled out; 55 Hz at 4.5 mA, +0.07
   points, chosen).

**A backend finding met on the way, for the PI rather than fixed here.** The two-stage card prints
"Setting in force today: 55 Hz at 100 µs" for both sides. The design matrix carries each side's own
pulse width, and on the incumbent epoch (epoch 123, from 2026-09-03 20:07 UTC) it reads **100 µs on
the Left and 150 µs on the Right**. Stage 1 reads the Left column for both sides
(`stage1_openloop.run_stage1`, `pw_col="pw_us_Left"`; its docstring says "This record carries
`pw_us_Left` only", which is no longer true). So the Right side's "the best slice IS the pulse
width in force (100 us)" is a statement about the left side's pulse width, and the frozen Right
setting of 55 Hz · 100 µs · 4.9 mA would, if programmed, change the right pulse width by −50 µs
without the search having modelled that. The proposal does not change Stage 1; it shows each
side's own programmed value (phase 3) and marks the −50 µs with an amber symbol so the discrepancy
is visible rather than hidden. Whether Stage 1 should form its pulse-width groups per side is his
decision.

---

## 3. The redesign

### 3.1 What a clinician needs to decide from this page

1. **Which setting to program next, per side** — and whether the evidence has earned it.
2. **Whether closed loop may start** on that setting — and if not, which of the 4 checks blocks.
3. **What to test at the next visit** — the settings ruled out, the untested cells, the unresolved
   sides.

The proposed page puts those three first, as values and symbols, and moves every sentence that
explains how a value was arrived at behind a reveal control (the `Fold` the Closed-Loop page
already uses; decision 123: values, verdicts and reasons never inside a fold, only the method).

### 3.2 The page, top to bottom (the "Proposed" board on the canvas)

**A. The decision strip** (new `DecisionStrip.js`). One row per side. Columns: programmed now →
search prefers (held to what adaptive mode can use) → the change → the gain drawn against 1 SD of
its own difference → the verdict symbol.

RCS08 today:

| side | programmed now | search prefers | change | gain ± 1 SD | verdict |
|---|---|---|---|---|---|
| Left | 55 Hz · 100 µs · 3.0 mA · contacts L 2⁻ | 55 Hz · 100 µs · 4.5 mA (delivered 1.0–4.8 mA, 11 stretches) | 0 Hz · 0 µs · +1.5 mA | +0.00 pts ± 0.85 | not resolved (amber) |
| Right | 55 Hz · 150 µs · 2.5 mA · contacts R 1⁻2⁻ | 55 Hz · 100 µs · 4.9 mA (delivered 1.0–4.5 mA, 15 stretches) | 0 Hz · −50 µs (amber) · +2.4 mA (amber: above the 4.5 mA ever delivered) | +0.00 pts ± 0.51 | not resolved (amber) |

The gain here is the Stage 1 group's own (`stage1.strata`, the row for that side and pulse width),
the same `gain` and `sd_of_difference` the verdict used. It is 0.00 on both sides because the
chosen rate is the rate already in force, which the search says in its first reason; the strip
shows the number and the reason is one click away ("Why each side reads as it does (9 reasons from
the search)"). The 6 model blockers fold under "Why no setting is recommended (6 reasons from the
model)". Headline above the strip, computed from the counts: "No setting is recommended today:
0 of 4 arms resolve a gain larger than its own uncertainty".

Until phase 3 lands the strip cannot show the contacts or the Right side's own pulse width (the
response does not carry them); it prints "contacts: not in the response" and "— µs" rather than the
left side's value.

**B. Closed loop: may it start?** (`ClosedLoopChecks.js` + `ExcludedSettingsChart.js`, replacing
the two-stage card's body). Headline with the symbol: "Closed loop may not start: 1 of 4 checks
block". Then 4 rows, symbol · plain name · the numbers:

- ✓ Rate at or above the adaptive minimum — `L 55 Hz · R 55 Hz (minimum 55 Hz)`
- ✗ Rate and pulse width resolved against their own uncertainty — `L ● rate ● pulse width  R ● rate ● pulse width` (amber = not resolved)
- ✓ A sensed band inside 8–30 Hz responds to stimulation current — `12 of 18 bands respond · 17 not measurable`, then a strip of 18 bars, one per band centre 10.5–27.5 Hz, height = the separation between the two captured power readings in units of their scatter (d), the required minimum 0.50 as a dashed line, pass ink for the 12 that respond, fail ink for the 6 that do not, and the best band labelled: "best 23.5 Hz · d 1.83 · 229.7 → 137.1 units at 1.5 → 4.5 mA"; below it "read on L 0⁻2⁺ at 55 Hz · 12 contact-and-rate combinations screened, 12 could not be built".
- ✓ Closed-loop current limits inside the delivered range and under the ceiling — `L 1.0–4.8 mA · R 1.0–4.5 mA (ceiling 5.0 mA) · limits defaulted to the delivered range`

Each row's server sentence is behind "▶ Sentence". Then **"What adaptive mode ruled out"**: two
small panels, one per side, rate on a log2 axis (the optimiser's own axis), predicted pain against
the setting in force on the vertical axis, the region below the 55 Hz minimum shaded, the ruled-out
cell as an open vermillion circle (Left: 40 Hz · 4.5 mA · −0.13 pts; Right: 40 Hz · 4.9 mA ·
+0.15 pts), the chosen cell as a filled blue disc (55 Hz · 4.5 mA · +0.07; 55 Hz · 4.9 mA · +0.18),
an arrow between them, and each pulse-width group's own best cell as a grey dot (60 µs at 55 Hz,
140 µs at 165 Hz). Direct labels, no legend. Then "If closed loop could start: Nothing was drawn
up: 1 check above blocks (…)". The per-pulse-width fit table, the skipped groups and the
provenance sentences stay, folded.

**C. The sensing evidence** (`SensingEvidenceTable.js`, replacing the readiness card). Headline
with symbol: "✓ 12 of 50 contact-and-rate combinations usable for closed loop · best L 1⁻3⁺ at
165 Hz (Left stimulation)". A 9-column grid, one row per responding combination, in the project's
contact order (left before right, then contact number): sensing contact in Medtronic form · stim
side · rate · bands responding as a small bar with the 50 % requirement line and "14 of 18" ·
bands still falling after the time confound is removed, the same way · currents tested "1.6–4.2
mA" · separation "d 1.43" · usable ✓/✗ · "▶ Reason" for the 8 rows that carry one. The 110-word
footer folds under "What 'usable' requires, and why the current limit is flat".

**D. Evidence base**: one row of labelled numbers (92 stretches · 765 reports · 2025-07-18 →
2026-09-03 · wash-in 1 min · left 0.0–4.8 mA · right 0.0–4.5 mA · states 57/20/9/6). "Left
amplitude levels 22" is dropped: no decision reads it.

**E. Arms as small multiples** (`ArmGainStrip.js`, replacing the 7-column table): pain sites as
rows, sides as columns, 4 cells on one shared gain axis (−3 to +3 pts), each with "in force 55 Hz ·
3.0 mA → candidate 55 Hz · 4.7 mA", the gain dot with its 1 SD band, the verdict symbol, and "61
stretches · safe ceiling 5.0 mA". An amber symbol marks a candidate above the reachable safe
ceiling (both Right cells: 4.0 and 4.9 mA against 1.9 mA). Click a cell to select the arm. The two
paragraphs fold under "How the gain and its uncertainty are computed, and what the 3 verdicts
mean". The unit stays the arm and the 4 are never pooled (figure conventions, rule 2).

**F. The selected arm**: title "left leg · Left side: model surfaces and what to test next" with the
arm dropdown; the 5 server-drawn figures unchanged, in their order, behind one fold ("Show the 5
model surfaces …"), mounted on first reveal so Plotly measures a real width (the skill's own
warning; `Fold` gains an `onChange` callback for this). Then "What to test at the next visit": a
one-line caption computed from the rows ("cells never tested, ranked by expected improvement ·
0 of 10 eligible without new sign-off · currents capped at 5.0 mA") and a compact 8-column grid
with digits and units (40 Hz · 5.0 mA · +0.22 pts · ±1.22 pts · 0.628 · 0 prior records · eligible
symbol). The 200 words on why the list and the clinic schedule disagree fold.

### 3.3 What the numbers say about the change

After all four phases, the same counter on the new source gives **1,500 static words in the open
and 457 inside closed folds; of the server's 1,599 words, about 330 remain in the open (digits and
labels: chart labels, the check numbers, the table values) and 1,480 sit inside folds.** The 1,500
static figure over-counts what a reader sees: it includes the 5 figure titles and blurbs (303
words, now behind the surfaces fold), the loading state, tooltip text and the legacy explanations
kept for older responses. Counted by hand from the "Proposed" board with folds closed, RCS08's page
shows about 620 static words and about 330 server words, **about 950 in all against 3,095**. The
method is stated so he can weigh it; the exact rendered count would come from the browser once a
phase is built.

### 3.4 The drawing rules followed (Tufte, the dataviz skill, the figure conventions)

- **Every headline is computed from the numbers in the same render** (figure conventions, rule 1):
  "0 of 4 arms", "1 of 4 checks", "12 of 50 combinations", "0 of 10 eligible" are counts, never
  strings.
- **Three states, never two** (rule 5): resolved = tick, not resolved = amber disc, not
  determinable = open dashed circle, with the words beside them; "not resolved" is never in the
  failure ink. The symbols are the four the Closed-Loop page approved (decision 122), lifted into
  one shared file so the two pages cannot drift.
- **Small multiples over one big figure**: the 4 arms on a shared axis; the 2 sides of the
  excluded-settings chart; the 18 band bars.
- **Direct labels, no legends**: every point on the excluded-settings chart carries its rate,
  current and predicted value; the best band carries its numbers.
- **Every number with its unit, and its uncertainty where one exists**: "+0.32 pts ± 1.45", "d 1.83",
  "1.0–4.8 mA".
- **High data-ink**: the gain bar is a line, a zero mark, a band and a dot; the count bars are one
  filled rectangle and the 50 % requirement line.
- **The palette is the project's Okabe–Ito set** (`ClosedLoopSim/palette.js`). The dataviz
  validator was run on the three series inks used (#0072B2, #D55E00, #009E73): lightness band,
  chroma floor, colour-vision separation (worst adjacent pair ΔE 11.0 deutan) and contrast all pass
  in light and dark. The grey (#6C757D) is used only for "not tested / not determinable" with its own
  dashed shape, never as a series; the orange (#E69F00) only as a fill with the shape carrying the
  meaning, never as text (the palette's own `warnText` rule).

---

## 4. The notation rule, applied everywhere

**Contacts print in the form the Closed-Loop and Biomarkers pages already print**: the side as one
letter, the contact numbers as digits, each contact's polarity as a superscript, no dash —
`L 0⁻2⁺`, `L 1⁻3⁺`, `R 0⁻3⁺`. The label is the server's (`analytics.format_channel`,
`display_short`, decision 131: one definition, on the writer); the page reads it and never derives
it, and a response from before phase 3 prints the raw key marked "(unformatted)" rather than a
label invented on the page.

The brief wrote "Left 0-3+". The page keeps `L 0⁻3⁺`: the same three facts, in the form every other
page of this family prints, so a contact reads the same wherever it appears.

**Stimulation contacts** are a different quantity and the response carries none today. The settings
stream keeps the cathode segments only ("2a-2b-2c"), never the anode. Phase 3 prints them as the
side letter and the cathode contacts with a superscript minus, a whole ring collapsed to its digit:
`L 2⁻` for 2a-2b-2c on the left, `R 1⁻2⁻` for 1a-1b-1c-2a-2b-2c on the right, `L 1a⁻2a⁻` for a
ring used in part; no anode is printed because none is recorded, and the raw segment list travels
beside the label (`contacts_raw`). Every cathode label in RCS08's stream was run through the rule
and is listed in §6.

**Numbers**: digits only, never "zero", "two", "three of four"; a unit on every number; the pain
objective as signed points ("+0.32 pts"); a difference as a signed value in one unit ("+1.5 mA",
"0 Hz"); counts as "12 of 18".

---

## 5. What must NOT change

- **The five server-drawn figures and everything the figure-conventions skill fixes**: the order
  (posterior surface first and largest), the arm as the unit, the one `FigureContext` behind both
  renderings, the headline helpers, the three-state `optimum_resolved`, the safety surface kept
  apart. The proposal moves the figures behind a fold and mounts them on first reveal; it does not
  touch `routines/plots.py`. (Noted, not changed: `fig2`, `fig3` and `fig5` carry headlines written
  as fixed strings — "Exploration dominates every selection", "best-so-far has not moved since the
  incumbent", "The plateau is LOCAL, not global" — which the skill's rule 1 says to derive; a
  backend matter for a separate decision.)
- **The request and response contract.** The page's request (`OPTIMIZER_REQUEST`, the six
  parameters) and the two-stage request are unchanged. Phase 3 ADDS fields to the response
  (`in_force_by_side`, `display_short` and its two siblings on the responding cells and the
  selected cell, `selected_display_short`, `verdict_rows` / `min_sep_d` / `best_center_hz` and
  `defaulted` inside two check evidence blocks); it removes or renames nothing. The response key
  already includes a digest of the module's own code (`_code_digest`), so the stored copies are
  rebuilt on deployment without any rule-version change.
- **The cache slots** (`STIM.result`, `STIM.twoStage` in `moduleCacheKeys.js`) and the order of the
  two requests (the plan only after the page's own response).
- **Rule 7's three files** (`resultCache.js`, `useCachedResult.js`, `RecomputeBar.js`): untouched.
- **The two files the PI approved on the Closed-Loop page** are touched only to lift the four
  symbols into `glyphs.js` (`BandSweepGridPanel.js` imports them; nothing drawn changes) and to
  give `Fold.js` an optional callback (default `null`; every existing caller behaves as before).

---

## 6. The build plan, one phase at a time

Each phase is one patch, generated against the working tree as it stood at 12:11 on 2026-09-12 and
checked to apply in order on a copy of that tree (`git apply --check`, then applied; the result of
all four is byte-identical to the working copies the patches were cut from). Phase 1 was also
checked against the real tree. The JavaScript of every phase parses with the project's own Babel
(`Client/node_modules/@babel/parser`, with JSX). **No frontend build was run and nothing was watched
in a browser**, because that needs the files applied to `Client/src`; after a phase is applied, the
build and a browser check are the verification, as always here. The full component files sit beside
each patch for reading.

### Phase 1 — the decision strip and the headline (frontend only)
`phase1_decision_strip/phase1.patch` (5 files, 380 added, 70 removed): new `ClosedLoopSim/glyphs.js`,
`StimOptimizer/stimFormat.js`, `StimOptimizer/DecisionStrip.js`; `BandSweepGridPanel.js` imports the
symbols; `index.js` replaces the blue banner with the headline, the strip and the folded blockers.

**What he would see:** the top of the page is the table in §3.2 A, with the 6 blockers one click
away. Contacts read "not in the response" and the Right pulse width "—" until phase 3. Everything
below is as today.

**Backend fields needed:** none.

### Phase 2 — the closed-loop checks as symbols, the ruled-out settings as a chart (frontend only)
`phase2_closed_loop_checks/phase2.patch` (3 files, 388 added, 295 removed): new `ClosedLoopChecks.js`
and `ExcludedSettingsChart.js`; `TwoStagePlanCard.js` rewritten around them (the frozen-setting
sentences and reasons leave the card, since the strip shows them; the fit table, skipped groups and
provenance stay folded).

**What he would see:** §3.2 B, except that the band row shows a tick-and-cross row (from the
verdict sentences' first word) rather than the bars, and "limits defaulted" is read from the
sentence; both upgrade in phase 3.

**Backend fields needed:** none.

### Phase 3 — the backend fields, the sensing-evidence table, contacts everywhere
`phase3_backend_fields_and_sensing_table/phase3.patch` (9 files, backend and frontend):

- `bravo_service.py`: `sensing_display(channel)` (calls the Biomarkers formatter; the module already
  imports from Biomarkers in two places), `stim_contacts_short(cathode, side)`,
  `in_force_by_side(es)`; the response gains `in_force_by_side`, the responding cells and the
  selected cell gain `display_short` / `display_hemisphere` / `display_contacts`, the two-stage block
  gains `frozen_configuration.in_force_by_side` and `lfp_evidence.selected_display_short`.
- `routines/stage_gate.py`: the band-response check's evidence gains `verdict_rows` (the 18
  results as numbers: centre, responds, separation, the two power readings, the two currents, the
  slope and its p), `min_sep_d` and `best_center_hz`; the current-limits check's evidence gains
  `defaulted`. The sentences stay as they are.
- `tests/test_page_display_fields.py` (new, 15 tests) and one-line updates to the two tests that
  pin the response's exact key list (`test_two_stage_wiring.py`, `test_two_stage_adaptive_envelope.py`).
- new `SensingEvidenceTable.js`, `BandResponseStrip.js`; `ClosedLoopChecks.js` reads the rows;
  `index.js` mounts the table in place of the readiness card.

**Verified, on a scratch copy of the patched package inside the container (the repository
untouched):** the whole StimOptimizer suite, **472 passed, 42 skipped, 0 failed**, 15 of the passes being
the new file (the unpatched suite was not run separately this session, so no before-count is quoted). Read back live on RCS08 through
the patched copy: Left 55 Hz · 100 µs · 3.0 mA · `2a-2b-2c` → `L 2⁻`; Right 55 Hz · 150 µs · 2.5 mA ·
`1a-1b-1c-2a-2b-2c` → `R 1⁻2⁻`; both from epoch 123 since 2026-09-03 20:07 UTC; the six sensing
pairs → `L 0⁻2⁺`, `L 0⁻3⁺`, `L 1⁻3⁺`, `R 0⁻2⁺`, `R 0⁻3⁺`, `R 1⁻3⁺`; every cathode label in the
stream: `1a-1b-1c` → `1⁻`, `1a-1b-1c-2a-2b-2c` → `1⁻2⁻`, `1a-2a` → `1a⁻2a⁻`, `2a` → `2a⁻`,
`2a-2b-2c` → `2⁻`, `3` → `3⁻`.

**What he would see:** §3.2 A with the contacts and the Right side's own 150 µs (and the −50 µs
amber mark that follows from §2's finding); §3.2 B with the 18 bars; §3.2 C.

**A hazard to know before applying:** another session was editing the StimOptimizer tests while this
was written (uncommitted changes to `conftest.py`, `test_stage1.py`, `test_stage2.py` and the two
two-stage test files, 12:08). The two test hunks in this patch are one line each and were cut
against the 12:11 working tree; if that session's later edits move those lines, the hunks are: add
`"in_force_by_side"` to the sorted key list in the flag-off test of each file, and pass
`in_force=BS.in_force_by_side(bench.es)` to the direct `_two_stage_payload` call in
`test_the_block_equals_a_direct_call_of_run_two_stage_live_field_for_field`.

### Phase 4 — arms as small multiples, evidence base compacted, surfaces and queue folded
`phase4_arms_surfaces_queue/phase4.patch` (5 files): new `GainBar.js` (the one drawing of gain
against uncertainty, lifted out of the strip) and `ArmGainStrip.js`; `Fold.js` gains `onChange`;
`index.js` gets §3.2 D, E and F. `index.after_all_phases.js` beside it is the whole page file as it
reads after the four patches.

**What he would see:** the "Proposed" board in full.

**Backend fields needed:** none.

### Not in any phase, named for his decision
- Stage 1 forming its pulse-width groups per side (the 150 µs finding in §2).
- The anode of the stimulation contacts: the settings stream never records it
  (`adapter.group_settings` keeps the cathode only); carrying it would change a stored raw kind.
- The three fixed figure headlines in `routines/plots.py` (§5).
- An override control on the page (the endpoint accepts one; the card still says there is none).

---

## 7. What was and was not verified, plainly

- **Run:** the page's own request for RCS08 twice (with and without the two-stage block), the
  contacts probe, the dataviz palette validator, a Babel parse of every JavaScript file in every
  phase, `git apply --check` of all four patches in order on a copy of the tree, the whole
  StimOptimizer test suite on the patched scratch copy in the container (472 passed, 42 skipped),
  and a live read-back of the new fields on RCS08 through that copy.
- **Not run:** `npm run build` against `Client/src` (the patches are not applied), any browser check
  of a built page, the container Biomarkers suite (nothing in it is touched). The mock-ups were
  looked at in the browser pane as static files; one small overlap of two labels in the
  excluded-settings chart ("chosen: …" against "0 = setting in force") was seen and is a matter for
  the built component, where the label positions are computed from the data.
- **Nothing was built.** No file under `Client/src` or `BRAVO/` was changed; the gitignored scratch
  copy under `BRAVO/_agent_bridge/_probe_tl/_snap3/` is disposable.
