# Closed-Loop Deployment: backend-to-frontend integration and readability review

> Research report
> Researcher: worker-research | Date: 2026-09-22
> Confidence: MIXED — the code-side claims are HIGH (read directly, cross-checked against tests and
> decision log); the literature claims are MEDIUM (secondary summaries of paywalled papers, not the
> full PDFs); a few frontend/backend field-name claims are dated from a 2026-09-12 review and
> re-verified against the current working tree where cited.

---

## One-page summary

The module computes a genuine, well-designed decision (device rules, then physiological evidence,
then a threshold and timing plan, then a duty-cycle simulation) but the page assembles it from **two
separate backend endpoints that answer two different questions** — `/api/queryClosedLoopDeployment`
(device rules + physiology, the pipeline in `ClosedLoopDeployment/pipeline.py`) and
`/api/queryDeploymentSummary` (an older, still-live statistical-gate/ROC endpoint) — and the work of
reconciling them into one verdict is done **in the frontend**
(`DeploymentDecisionHeader.js`'s `reconcile()` function), not in the backend. That reconciliation is
now done well: one sticky header, three side-by-side sub-answers (device / evidence / transcription),
the losing endpoint's gate counts demoted to a labelled footnote. The page's reading order after the
2026-09-04 rebuild does follow the logic of the decision (verdict, then what would change it, then
device rules, then evidence, then the parameters, then the simulation, then the sign-off), which is a
real improvement documented in the file's own comments. The main remaining problems are: (1) the
`report_for_participant` response is built by calling `report_to_dict()` on the pipeline's
`DeploymentReport` and then **bolting on roughly a dozen more keys by direct dictionary assignment**
(`band_stability`, `reliable_change`, `three_source_response`, `band_sweep_grid`, `device_facts`,
`impedance_status`, …) in a 700-line function, so the "one response" a clinician reads is actually
built in two structurally different ways in two different files; (2) two cards — Band Stability and
Reliable Change — carry real safety-relevant findings but sit **below** the parameter table a
clinician transcribes from, when both should sit inside "what would change this answer"; (3) the
handoff of which band is being evaluated at all rides in browser `localStorage`
(`bandCandidateStore.js`), not on the server, so nothing about "which band, chosen when, by what
settings" is part of the report the sign-off card prints; (4) a documented, still-open hazard (2026-09-12
review, item C1) that a right-hemisphere candidate could be silently evaluated against the left
lead's current, impedance and captures has apparently been fixed in the pipeline (its own comments cite
"review C1, 2026-09-12" as resolved) but no live before/after proof for a right-side candidate was found
in this pass — flagged as unverified, not as still-broken.

---

## 1. What the module decides, and the evidence it weighs

The clinician's question, stated in the page's own subtitle (`index.js`, the title card): *"May this
configuration be programmed onto the Percept, and if so what should be entered?"* Two conjuncts,
answered by one pipeline (`ClosedLoopDeployment/pipeline.py:run`) called once per request from
`adapter.report_for_participant` (`ClosedLoopDeployment/adapter.py:2827`).

| Evidence | What it answers | Function | Card |
|---|---|---|---|
| Device rule ledger | Does the Percept firmware/manual permit this exact configuration (contact pair, band, rate, pulse width, amplitude range)? 51 encoded rules from `constraints.py` (`D01`-`D30`+), each with its manual page citation | `constraints.check_eligibility`, called from `pipeline.run` (`pipeline.py:346-359`) | **Device rules** (`DeviceRuleLedger.js`) |
| The band's grid verdict (discovery-stage) | Did this band, at commit time, show a statistically credible odds ratio linking it to pain (mixed-effects model, stim-stability likelihood-ratio test)? This is a **different, older** verdict than anything computed on this page | Computed on the Biomarkers page; carried on the committed `BandCandidate.verdict` and `BandCandidate.evidence` | **Committed configuration identity** card (`BandCandidateIdentity`, inline in `index.js`) |
| Band stability across time blocks | Does this band mean the same thing about pain at every stimulation current, or could closing the loop damage the very signal it steers by? Four-valued answer ("behaves the same" / "behaves differently" / "cannot tell" / "not tested"), deliberately not collapsed to a pass/fail | `stability.finding_from_stability_result`, translating a result already computed by `Biomarkers.bravo_service._validate_band_core`, wired in per `WIRING_stability_into_the_report.md` | **Does this band mean the same thing…?** (`BandStabilityPanel.js`) |
| Current-to-power slope (E1) | Can the device's amplitude actually move this band? Pooled titration slope across every run of stepped current, one baseline per run (decisions 55, 124, 126, 197, 213), replacing an older "screening" slope confounded with time | `edges.pooled_actuation_edge`, called from `pipeline.run` (`pipeline.py:225-239`) | **The evidence triangle** (`EvidenceTrianglePanel.js`, edge E1) |
| Power-to-pain slope (E2) and current-to-pain slope (E3) | Does the band track the patient (E2), and does stimulation itself relieve pain (E3)? | `edges.state_edge`, `edges.therapy_edge` (`pipeline.py:240-249`) | Same panel, edges E2/E3 |
| Sign coherence | Do the three edges compose into one consistent story, and does that story match what the selected control law (Dual Threshold ramps stimulation **up** when power rises) needs? Three-valued: agree-and-matches / disagree-with-law / not-established | `consistency.coherence_report` (`pipeline.py:251`) | Same panel, "Sign agreement" state track |
| Threshold placement | Where do the two switching values go, and is the separation between them large enough (relative to the signal's own noise) to avoid chattering? Centred on the participant's own median averaged reading, separated by a fitted noise-only design rule's minimum (decision 180; T3 of the 2026-09-13 method contest) | `authority.threshold_placement`, then re-placed by `_place_thresholds_from_record` (decision 180) | **Full parameter recommendation** (`PrescriptionPanel.js`), the two threshold rows |
| Timing recommendation | What averaging, onset, blanking, transition and startup-delay values does this participant's own record argue for? A six-method contest (`artifacts/contest_2026-09-13_SYNTHESIS.md`) picked a Kalman/local-level design rule; the table lives per-participant in `timing_recommendation.RECORD_DERIVED_TIMING_MS` | `timing_recommendation.for_participant`, folded into `prescription.prescribe_all_modes` (`pipeline.py:407-417`) | Same panel, the timing rows, with the design-rule/occupancy/startup/robustness notes attached per row |
| Controller replay | What would the Dual Threshold controller actually have done, run over this participant's own recorded power? Fraction of time at the upper/lower limit, the **longest single stretch** at a limit (not just the total, decision: a clinician consents to a stretch, not an average) | `replay.dual_threshold_segments` (`pipeline.py:368-382`) | Feeds the duty-cycle numbers on the **Full parameter recommendation** card and the **CL-DBS simulations** card |
| Simulation (M0/M1/M3) | Replay the recorded power as-is (M0), close the loop through a fitted response curve if one exists (M1), and bootstrap that fit (M3) for an interval | `simulation.py`, built by `adapter.write_simulation`, drawn client-side | **CL-DBS simulations** (`ClosedLoopSimulationPanel.js`) |
| Reliable-change floor | How big a swing in this patient's own pain rating could not have been produced by their own rating noise alone (Jacobson & Truax reliable-change index measured on this patient, decision 111)? Warns; blocks nothing | `reliable_change.reliable_change_verdict`, wired directly into `bravo_service`'s response-building step (see §2) | **How big a change…** (`ReliableChangePanel.js`) |
| Titration protocol | If more data is needed, what session would supply it (arm labels, pair count, seed)? | `protocol.titration_plan` (`pipeline.py:429-451`) | Not rendered on this route (see §2, "computed and shown nowhere") |

## 2. End-to-end data-flow map

### 2a. The two backend paths that build one page

There are **two live endpoints**, computed by two structurally different code paths, and the page
calls both:

1. **`/api/queryClosedLoopDeployment`** → `ClosedLoopDeployment.bravo_service.run_for_participant`
   (`bravo_service.py:79`) → `adapter.report_for_participant` (`adapter.py:2827`). This function (i)
   runs `pipeline.run` and serialises its `DeploymentReport` via `adapter.report_to_dict`
   (`adapter.py:1320`), then (ii) **merges roughly a dozen more top-level keys onto the same dict by
   plain assignment** before returning it: `out.update(_pre)` (the three-source comparison and two
   written-back tables, `adapter.py:3127`), `out["device_facts"]`, `out["device_facts_provenance"]`,
   `out["impedance_status"]`, `out["impedance_status_counts"]` (`adapter.py:3128-3131`),
   `out["band_stability"]` / `out["band_stability_summary"]` (`adapter.py:3191-3192`, wired per
   `WIRING_stability_into_the_report.md`), `out["reliable_change"]` (`adapter.py:3289-3311`), and
   `out["band_sweep_grid"]` (`adapter.py:3208`, computed even earlier, unconditionally, before either
   early return). None of these keys exists on the `DeploymentReport` dataclass in `types.py`; they
   are attached only in `adapter.report_for_participant`, so a reader of `types.py` alone would not
   know the response carries them.
2. **`/api/queryDeploymentSummary`** → `Server/APIs/DataAnalysis.py:QueryDeploymentSummary`
   (`DataAnalysis.py:995`), a separate, older Phase-E endpoint (per its own docstring,
   `DESIGN_biomarker_pipeline_v2` Phase E) that computes AUC/odds-ratio statistical gates and a
   percentile-anchored LSB threshold **independently of the pipeline above**. The frontend calls it
   through `useDeploymentSummary.js`.

The page's own comments say plainly why this is a problem and how it is currently patched: `index.js`
records that "the page this replaces … stated its verdict three times, from two endpoints that answer
different questions," and `DeploymentDecisionHeader.js` now computes **one** reconciled sentence from
both endpoints in its `reconcile()` function, demoting the summary endpoint's gate counts to a labelled
footnote ("STATISTICAL GATES, FROM THE SEPARATE DEPLOYMENT SUMMARY — EVIDENCE, NOT PERMISSION"). This
is a real fix at the presentation layer, but the two computations still run on the server as two
unrelated code paths that can time out, error, or go stale independently (`RecomputeBar` pools their
`staleReasons` and takes the *older* of their two timestamps precisely because they can disagree about
freshness).

### 2b. Field → component → sentence

| Response field | Built by | Component | Sentence the clinician reads |
|---|---|---|---|
| `verdict_detail.device_eligible` | `constraints.check_eligibility` via `report_to_dict` | `stateTracks.js` `TRACKS.device`, drawn by `DeploymentDecisionHeader` and `WhatWouldChangeThis` | "PERMITTED" / "NOT PERMITTED" / "NOT EVALUATED" |
| `eligibility.failures[]`, `.unknowns[]`, `.deferred[]`, `.advisories[]` | `constraints.check_eligibility` | `DeviceRuleLedger.js` | Per-row: rule id, title, manual page, and (for unevaluable rows) who can resolve it |
| `edges.E1/E2/E3` | `edges.py` via `pipeline.run` | `EvidenceTrianglePanel.js` | The signed axis readout ("sign −, interval spans zero") and the triangle graph |
| `coherence.*` | `consistency.coherence_report` | Same panel, `CoherenceReading` | "Do the three edges agree with each other?" / "…match the control law?" |
| `threshold.upper/lower`, `.placement_rule`, `.placement_note` | `authority.threshold_placement`, re-placed by decision-180 record-based rule | `PrescriptionPanel.js` field rows | The two LFP threshold values, to 4 decimal places, with `design_rule_note` / `occupancy_note` beside them |
| `prescriptions.modes.<mode>.fields[]` | `prescription.prescribe_all_modes` | `PrescriptionPanel.js` | Each transcribable row: value, units, "ENTER THIS VALUE" / "CHECK ON THE DEVICE" / "YOU MUST CHOOSE THIS" |
| `replay.frac_time_at_upper/lower`, `.longest_run_at_upper_s` | `replay.dual_threshold_segments` | Folded into `prescription.duty` fields shown on `PrescriptionPanel.js`, and into `ClosedLoopSimulationPanel.js`'s M0 model | "time at the upper amplitude limit," "the longest continuous stretch" |
| `band_stability` (bolted on in `bravo_service`, §2a) | `stability.finding_from_stability_result` | `BandStabilityPanel.js` | "behaves the same" / "behaves differently" / "cannot tell" / "not tested," with the effect size and its interval |
| `reliable_change` (bolted on, §2a) | `reliable_change.reliable_change_verdict` | `ReliableChangePanel.js` | "Smallest change this patient's own noise cannot explain," in points |
| `three_source_response`, `three_source_pooled` (bolted on) | `three_source_response.py`, `run_points.py` | `ThreeSourceResponsePanel.js` | The three-route comparison of current vs. band power; explicitly "gates nothing" |
| `band_sweep_grid` (bolted on) | `band_sweep_grid_for_closed_loop`, reading the Biomarkers page's own stored grid by settings tag (decision 131) | `BandSweepGridPanel.js` ("Choose a band") | The per-contact heat-map grid a clinician can click to commit a new candidate |
| (separate endpoint) `n_gates_passed`, `n_necessary`, `verdict` | `QueryDeploymentSummary` | `DeploymentDecisionHeader.js`'s footnote, `DeploySignoffCard.js` | "X of Y required gates passed… These gates ask whether the band discriminates, which is a different question from whether the device will accept the configuration" |
| `protocol.*` | `protocol.titration_plan` (`pipeline.py`) | **No component on this route reads it** | *(nothing — see below)* |

### 2c. Computed and shown nowhere

- **`rep.protocol` / `out["protocol"]`** — the titration-session plan (`protocol.titration_plan`,
  arm labels, pair count, seed, detectable effect size) is computed on **every** request whenever
  `protocol.py` is importable and serialised at `adapter.py:1447-1457`, but no component under
  `Client/src/views/Reports/ClosedLoopSim/` reads `data.protocol`. It is real, tested
  (`tests/test_protocol.py`), and reached by no page on this route.
- **`edges_historical`** — the E1 estimate the pooled titration slope replaced (the older,
  time-confounded "screening" slope) is serialised (`adapter.py:1411-1421`) but no panel reads
  `data.edges_historical`; only `edges.E1.source == "screening_historical"` (a flag on the *live*
  edge, drawn dotted in the triangle) is used, for the case where no pooled slope is stored yet.
- **`ground_truth` verdict table** (`ground_truth.py`, written by `write_ground_truth`) — written to
  the shared cache store for Stim Optimizer to consume (decision 33's ground-truth rule); no card on
  this page renders it directly; it surfaces only indirectly through the three-source comparison's
  per-route agreement notes.
- **`amplitude_effect` table** beyond the 4 newest runs — the full table (`THREE_SOURCE_RUNS_ON_PAGE
  = 4`, `adapter.py:1565`) is written for Stim Optimizer's own "which bands are still unresolved
  anywhere in the record" question; the page draws only the newest 4 runs.
- **`prescription.duty.predicted_failure_mode`, `.qualified_transitions`,
  `.unqualified_excursions`** — serialised on every mode (`adapter.py:1499-1501`) but not read by
  `PrescriptionPanel.js`'s `CouplingBanner` or `ModeBanner`; only `onset_windows_upper/lower` is used
  there.

### 2d. Shown with no backend source (browser-side arithmetic)

- **`PrescriptionPanel.js`'s `CouplingBanner`** recomputes `ceil(vA / vB)` (the number of controller
  confirmations) *client-side* from the two field values already on the payload, explicitly so it can
  be checked against the module's own count (`duty.onset_windows_upper`) and a disagreement surfaced
  rather than hidden — the component's own comment names this design choice, and it is a defensible
  one (arithmetic transparency), not a hidden computation.
- **`stateTracks.js`'s `coherenceReading()`** recomputes whether `sign(E1) × sign(E2) == sign(E3)`
  client-side from the three edges' own signs, again explicitly so the two questions ("do the edges
  agree with each other" vs. "do they match the control law") can be split into two sentences the
  backend's single `coherence.coherent` boolean cannot express on its own. The backend does compute
  and serialise its own `coherent`/`p_coherent` (`consistency.coherence_report`), so this is a
  **derived restatement of a server answer**, not an independent client-side verdict — but it means
  the two-statement breakdown a clinician reads in `EvidenceTrianglePanel.js` (`CoherenceReading`) is
  frontend logic, unverified by any backend test against the same inputs.
- **`verdictColor()` / `verdictTextColor()`** (`index.js`) recolour the *discovery-stage* badge on
  `BandCandidateIdentity` from a string match on `bc.verdict` (`/VALIDATED \(stim-stable\)/` etc.) —
  cosmetic, not a computation, but a string-matching dependency on wording chosen upstream on a
  different page.

## 3. Readability audit, card by card

Evaluated against the PI's stated goal (simple, human-readable, clearly separated ideas in logical
order, HOUSE_RULES_writing_and_claims.md vocabulary) and against the referent test
(`ClosedLoopSim.referent.test.js`), which pins several exact wording requirements.

**DeploymentDecisionHeader ("the sticky verdict").** Purpose stated in the first sentence: yes — the
headline is a single, action-oriented sentence per branch of `reconcile()` (e.g. "This configuration
cannot be programmed: the device refuses it"). Mixes ideas: no — it deliberately keeps three
sub-answers as three visually separate cells rather than one collapsed word, which is the fix for a
documented past failure (three disagreeing verdicts). Numbers without meaning: the footnote line
("X of Y required gates passed…") is a number with meaning attached in the same sentence, but it is
demoted below a divider specifically because a bare gate count invites over-reading; this is handled
well. Vocabulary: mostly plain ("the device refuses it," "a measurement problem rather than a
programming one"); "provisional" is used as a defined term with its own note component
(`ProvisionalNote.js`) rather than a bare jargon word, which satisfies house rule §1's "define on
first use." One residual jargon risk: "point sign" and "interval spans zero" appear verbatim in
`stateTracks.js`'s blurb text and are not translated into the house-rules replacement register (no
entry for "sign" or "interval" in the replacement table, but house rule §1 would want a gloss such as
"whether the estimate could plausibly be zero" rather than the statistical phrase).

**WhatWouldChangeThis.** First sentence states purpose directly. Genuinely well-ordered: violated
device rules first (nothing else can clear them), then rules a clinician can resolve at the
programmer, then rules needing an analysis change, then the evidence findings, ranked by "how much of
the verdict clears." This is the one card that most closely matches the assignment's requested
argument shape (§4 below). No number appears without an actor and a "why it matters" sentence.

**DeviceRuleLedger.** First sentence ("Device rules") is a label, not a purpose sentence — the
subtitle (`el.summary`) supplies the "why" only after a reader has already parsed the counts strip.
The card mixes two different ideas by design (violated rules vs. advisory shortfalls vs. "pinned
because the value is load-bearing") but keeps them in clearly labelled, separately-glyphed buckets,
which satisfies "clearly separated ideas" even though it is dense (51 rules). Vocabulary: "advisory,"
"deferred," "unevaluable" are defined inline per bucket, which matches house rule §1's "define on
first use... in every response." This card is the longest and most technical on the page; it is
correctly folded by default except for violated rows, which is the right compromise between
completeness and the "shorter beats longer" anti-pattern rule.

**EvidenceTrianglePanel.** First sentence states the three questions the graph answers. The card mixes
a genuinely hard multi-part idea (three edges, three axes, two coherence questions) but separates them
into a graph, three signed axes, and a two-statement coherence reading — this is real information
architecture, not verbal padding. Vocabulary risk: "cluster-robust," "wild cluster bootstrap-t,"
"Rademacher weights" appear only inside a folded "How this edge was estimated" note copied verbatim
from the backend's `note` field — correctly folded away from the main reading path, but the backend
`note` string itself is written for an analyst, not for the plain-language register HOUSE_RULES
requires "in every response" (house rule §1 says "define anything technical on first use... in every
response," and a folded note is still a response). This is the report's clearest single instance of
vocabulary not matching HOUSE_RULES.

**PrescriptionPanel ("Full parameter recommendation").** First sentence is an instruction ("Enter each
value on the A610, read it back, tick the box"), which is exactly the right register for the card a
patient can be harmed from. The withholding behaviour (no numbers rendered at all when the device
refuses, per §"THE WHOLE TABLE IS WITHHELD…") is the strongest single safety design decision on the
page. Numbers never appear without units in an adjacent (not concatenated) column, matching the
milliamp-transcription safeguard documented in `deployFormat.js`. One readability problem: this card
carries **five different provenance/explanation systems** stacked per row — `design_rule_note`,
`occupancy_note`, `startup_bias_note`, `robustness_note`, and the generic `why` fold — each a
one-off paragraph from a different backend module (`design_rule.py`, `occupancy.py`,
`startup_bias.py`, `robustness.py`). A clinician reading the onset row sees four short, differently-
sourced paragraphs in sequence with no shared heading explaining that they are four independent checks
on the same number; this is the page's clearest instance of "ideas not clearly separated" even though
each individual sentence is plain.

**BandCandidateIdentity.** Mixes two genuinely different questions under one card without saying so
until a fold: "what band is this" (device identity) and "was this band worth committing at all"
(discovery-stage statistics, a *different verdict computed on a different page*). The card's own
comment concedes the risk ("a different quantity from the reconciled verdict at the top") and folds
the explanation, but the badge colour and the discovery-stage statistics are shown **unfolded and
first** (per the PI's 2026-09-10 rule "there's no point in hiding it ever"), while the explanation of
why it is a different verdict from the header above is folded. This inverts the safer order: the
distinguishing sentence should be visible before the numbers it distinguishes, not after.

**BandStabilityPanel.** Exemplary structure: first sentence is the question in plain words ("Does this
band mean the same thing about pain at every stimulation current?"), all four possible answers are
always drawn (so "cannot tell" is never silently read as a pass), and the card explicitly refuses to
print a pass/fail badge because "whether this finding should stop a deployment has not been decided."
This is the strongest single card on the page for honest three/four-state reporting. Its position,
however — after the evidence triangle and prescription-adjacent, but visually and causally
**subordinate** to both — under-states its own importance: the card's own docstring calls it "really
important" (quoting the PI verbatim) and it directly qualifies whether the E2 edge one card above means
anything at all, yet nothing on the evidence-triangle panel cross-references it.

**ReliableChangePanel.** First sentence in plain English. Correctly labelled "warns; blocks nothing."
Vocabulary is fully translated ("noise floor," "smallest change this patient's own noise cannot
explain") rather than "reliable change index," which is exemplary house-rules compliance. Position is
the weakest part: it sits below Band Stability, both below the evidence triangle and above the
parameter table, but nothing in `PrescriptionPanel.js` or `WhatWouldChangeThis.js` references it, so a
reader who transcribes a threshold derived partly from pain-report thresholds (D26 warnings) has no
prompt to check whether the pain swings behind that derivation clear this patient's own noise floor.

**ThreeSourceResponsePanel, EraRefitPanel, LsbPowerPanel, DeploymentRocPanel.** Correctly demoted below
a fold or to the foot of the page as "evidence for the analyst, before the visit," with an explicit
label that they gate nothing. This matches the assignment's request that the order follow the
decision's logic: these are pre-visit methods artefacts, not programming-visit content, and the page
says so.

**DeploySignoffCard.** Correctly a "summary, not a new analysis" per its own docstring, but it is the
**one card that still independently prints an evidence verdict line** sourced from `summary.verdict`
(the separate `/api/queryDeploymentSummary` endpoint) rather than the reconciled header's own verdict —
`EvidenceVerdictLine` reads `rep.verdict`, i.e., the *device-rule pipeline's* verdict string, which is
good, but the card also receives and can display `summary` (the statistical-gate endpoint) for its gate
checklist, so the signed paper record still assembles from two sources at the point where a printed
record is least able to show a footnote correcting itself.

**ClosedLoopSimulationPanel ("CL-DBS simulations").** The headline sentence is built from the numbers
at render time (never hardcoded), and three states (a number / an interval / "not assessable") are
never collapsed — this matches the anti-pattern rule against silent zeros. Correctly labelled
"dashed... because everything in it is modelled." Good placement at the very end: it is explicitly the
"what happens next" projection, appropriately last in the argument.

## 4. Proposed page order, as a numbered argument

The assignment's requested shape: the question, the answer, the three pieces of evidence, the
prescription, the caveats, what would change it. The current order already approximates this well
(§3); the changes below are mostly *regrouping* rather than *reordering* the major bands, because the
2026-09-04 rebuild already got the top-level sequence right. Each row below states whether it is
wording-only, needs a component moved, or needs a new/merged backend field.

1. **The question** — *(unchanged; wording-only)*. Headline: "May this configuration be programmed,
   and if so what should be entered?" Already the page's own H6 subtitle in `index.js`. No change.

2. **The answer** — *(unchanged; wording-only)*. `DeploymentDecisionHeader`'s reconciled sentence.
   One addition, wording-only: fold the statistical-gate footnote's jargon ("gates," "necessary")
   through the house-rules replacement ("gate" → "a check that can refuse"); currently the footnote
   uses "gates" bare four times in one paragraph.

3. **What would change it** — *(unchanged position; needs a backend field)*. Keep
   `WhatWouldChangeThis` second, exactly as now. Add one field: `band_stability.blocking_status` and
   `reliable_change`'s worst-case verdict should be **read into this ranked list** as two new items
   (rank between the device-rule items and the coherence items), each with an `actor` and a `clears`
   sentence in the same shape as the existing items — today these two findings are separate cards
   five and six positions later and never appear in the one list whose whole job is "what would
   change the answer." This needs a backend field only in the sense that `buildItems()` (frontend)
   would read two already-serialised objects (`data.band_stability`, `data.reliable_change`) that the
   backend already produces; no new backend computation, just a new consumer of an existing field.

4. **Evidence, piece one: is this permitted at all (device rules)** — *(unchanged; wording-only)*.
   `DeviceRuleLedger` stays third. Wording-only fix: the card's first sentence should state its
   purpose ("Whether the Percept firmware and manual permit this exact configuration") before the
   bare label "Device rules," matching the pattern `BandStabilityPanel` already uses correctly.

5. **Evidence, piece two: does the physiology support it (the triangle + stability)** — *(needs a
   component moved)*. Move `BandStabilityPanel` to sit **immediately inside**
   `EvidenceTrianglePanel`, directly beneath the E2 axis (band power → pain), rather than as a
   separate card two positions later. The stability answer is specifically a qualifier on E2 ("does
   the signal track the patient the same way at every current"), and reading it apart from E2 is why
   the panel's own docstring has to argue for its own relevance. This is a component move, not a
   backend change — `BandStabilityPanel` already accepts `stability` as a prop and needs no new data.

6. **Evidence, piece three: would a change be detectable at all (reliable change)** — *(needs a
   component moved)*. Move `ReliableChangePanel` to sit beside the D26 capture-verdict warnings on
   `DeploymentDecisionHeader` or immediately after the coherence reading, since the D26 warnings
   ("thresholds too close," "inverted capture") are themselves judged against pain-report-derived
   quantities that this card qualifies. Component move only.

7. **The prescription** — *(unchanged; one wording-only fix, one backend field)*. Keep
   `PrescriptionPanel` fourth-from-the-evidence, as now. Wording-only: give the four per-row
   provenance notes (`design_rule_note`, `occupancy_note`, `startup_bias_note`, `robustness_note`) a
   single shared heading such as "Four independent checks on this number" before the first one, so a
   reader knows they are reading four short verdicts and not four fragments of one paragraph.
   Backend field: add one boolean `any_check_failed` per timing field so the frontend can order the
   four notes by severity instead of by which module happened to run first (today they are printed in
   a fixed code order regardless of which, if any, actually flags a problem).

8. **The caveats** — *(needs a backend field)*. Today the caveats are scattered: `ProvisionalNote`
   (evidence triangle and prescription), the D26 warnings (header), the "things the record cannot
   settle" block (prescription footer), and the three-source panel's "gates nothing" note. Add one
   serialised list, `out["caveats"]` — a flat array of `{severity, text, card}` built once in
   `report_to_dict` from `warnings`, `provisional`, and the D26 `capture_verdicts`, so a single
   component (or the sign-off card) can print "N caveats" as one countable, ranked list rather than a
   reader having to notice each one is a caveat by finding it in five different visual styles across
   the page. This is a genuine new backend field (a small aggregation, not a new computation).

9. **The projection** — *(unchanged; wording-only)*. `ClosedLoopSimulationPanel` stays last before
   the sign-off, as now; no change needed.

10. **The record** — *(unchanged)*. `DeploySignoffCard` stays last. One fix, needs a backend field:
    the card should print `rep.verdict` (the device-rule pipeline's reconciled string) as its **only**
    verdict line and drop its separate read of the statistical-gate endpoint's `verdict` field for the
    headline, keeping that endpoint only for its gate checklist rows (which it already labels
    correctly as a checklist, not a verdict). This needs no new backend computation, only a frontend
    change to which existing field feeds which line — listed here as a caveat because the current
    code reads `summary.data.verdict` in at least one place on this card (per its own component
    comments) even though `EvidenceVerdictLine` correctly reads the pipeline's verdict elsewhere on
    the same card, which is the sign-off card literally holding two different verdict strings at once.

**Demoted panels, unchanged position (already correctly placed):** `BandSweepGridPanel` ("Choose a
band") stays first/unconditional — correct, since it is the only way to reach the page with no
candidate yet. `BandCandidateIdentity`, the analyst fold (`DeploymentRocPanel`, `LsbPowerPanel`,
`EraRefitPanel`), and `ThreeSourceResponsePanel` stay below the prescription — correct, per the page's
own documented rationale that they are pre-visit methods evidence.

## 5. Integration gaps with the Biomarkers grid and Stim Optimizer

**With the Biomarkers grid (decision 131).** The "Choose a band" card
(`BandSweepGridPanel`, fed by `band_sweep_grid_for_closed_loop`, `adapter.py:548`) does not compute
its own grid; it reads the **newest grid the Biomarkers page has already stored**, matched by a
settings tag built from the pain score, matching rule and split
(`Biomarkers.bravo_service.sweep_settings_tag_from_request`, decision 131's mechanism, confirmed at
`adapter.py:556-583`). Two consequences worth naming to the PI:

- **Settings-tag mismatch is possible and silent to a first-time visitor.** If a clinician has never
  opened the Biomarkers page with a given pain score/matching/split combination, `want` (the requested
  tag) matches no stored grid and the card returns `{"available": False, ...}` — a plain "not
  available" message, not an explanation that the fix is to visit the Biomarkers page first under
  those settings. `DeviceRuleLedger`-style actor labelling ("who resolves this") does not extend to
  this card.
- **Staleness is bounded, not eliminated.** `band_sweep_grid_for_closed_loop`'s own comment states it
  matches "the newest entry whose sidecar tag equals the tag of the settings in the request," so a
  grid the Biomarkers page rebuilt for a new pain report supersedes the older one here too — this is a
  correct fix for the historical decision-107 class of defect (stale grid served as current), but it
  means the Closed-Loop page's "Choose a band" card can change **underneath a clinician mid-session**
  if the Biomarkers page is recomputed in another tab, with no visible notification on this page beyond
  the shared `RecomputeBar`'s staleness flag (which does not distinguish "this page's own data changed"
  from "the grid it borrows changed").
- **Provenance**: the grid entry is a raw/derived kind read via `load_newest`-style matching (decision
  103's pattern per the 2026-09-12 review's "Checked and NOT flagged" list), not carried with an
  explicit provenance chain into this page's own response — the ledger describes it as "checked and
  not flagged," i.e., an accepted risk rather than a defect.

**With Stim Optimizer (decisions 31, 41).** This module is a **producer**, not a consumer, of the
provenance-chained cache-store products Stim Optimizer reads:

- `write_ground_truth` (`adapter.py:1613`) writes the ground-truth verdict table
  (`ground_truth.KIND`) with the tile-cache entry's key flattened into its provenance
  (`_prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")`), so a later refusal (Stim
  Optimizer reading its own output back as independent evidence, decision 31's constructed-cycle
  guard) can fire correctly.
- `write_pooled_shape` and `write_run_points` (`adapter.py:3075-3100`) write the pooled
  within-visit table and per-run points Stim Optimizer's own acquisition logic and this page's E1 both
  read, under the refusal rule that "a refused entry is replaced, not skipped" (decision 41).
- **The one documented staleness risk in this direction**, from the 2026-09-12 review (C6, "CONFIRMED
  by reading"): the pooled table used to be **read** (for E1 and the two D26 capture verdicts) before
  it was **rewritten** in the same request, so the first request after a new titration run landed
  could show a triangle and D26 warnings from the *previous* table while the simulation card on the
  same page used the *new* one. The current `pipeline.py` and `adapter.py` comments ("THE THREE-SOURCE
  COMPARISON AND THE TWO TABLES IT WRITES COME BEFORE THE PIPELINE (review C6, 2026-09-12)") state this
  was reordered so the pipeline now reads what the same request just wrote. This was **read as fixed**
  in the current working tree (the write block precedes `_pl.run` at `adapter.py:3001-3122`), but no
  live before/after field-count proof for this specific fix was located in this pass — flagged as an
  unverified-but-plausible fix rather than a confirmed live proof (CLAUDE.md §8 rule 3: never quote a
  proof that was not re-run).

## 6. Literature: how other groups present aDBS readiness and threshold choice

**Medtronic's own clinician workflow (Stanslaski et al. 2024, *npj Parkinson's Disease* 10:174,
doi:10.1038/s41531-024-00772-5; describing the ADAPT-PD trial, NCT04547712).** Confidence MEDIUM (read
via a secondary fetch, not the full PDF). The clinician-facing workflow they describe is procedural
rather than a computed "verdict": a clinician uses the device's own **Signal Test** and **Survey**
tools to find the largest LFP peak in the 8–30 Hz range and picks a 5 Hz band around it (no statistical
threshold for "good enough" is reported at this stage); Dual Threshold's upper value is the 30-second
averaged LFP power measured while stimulation sits at the **lower** amplitude limit, and the lower
threshold is measured the same way at the **upper** amplitude limit (i.e., thresholds are captured
directly from the two amplitude extremes, the same two-point capture logic this module's `authority.py`
and `D24`/`D26` rules encode); Single Threshold is set at 75% of the distance between the two captured
values (matching this module's D20 "device computes this" rule, confirmed in `PrescriptionPanel.js`'s
`deviceComputesThisField`). Readiness to move from setup to formal evaluation is judged by a
**clinician-reported Global Impression of Change score**, not by a machine-computed statistical gate —
i.e., ADAPT-PD's own clinician-facing summary is closer to a checklist-plus-judgment than to this
module's multi-edge statistical triangle. This is a genuinely different design philosophy: Medtronic's
own workflow trusts a clinician's real-time observation of the LFP-vs-stimulation relationship during a
programming visit, whereas this module tries to encode that judgment as a testable E1/E2/E3 triangle
computed from the ambulatory record in advance of the visit. Neither the ADAPT-PD paper nor the
Medtronic scientific compendium (fetched title only, PDF not text-extractable in this pass) was found
to describe a formal "sign coherence" check comparable to this module's E1×E2=E3 composition test —
that check, and the explicit distinction between "edges disagree with each other" versus "edges agree
but disagree with the control law," appears to be original to this platform, not adapted from a
published aDBS workflow.

**Oehrn et al. 2024, *Nature Medicine* (chronic adaptive DBS vs. conventional DBS, blinded randomized
feasibility trial), and the related case report (Cernera et al., *Movement Disorders* 2024,
doi:10.1002/mds.30076).** Confidence MEDIUM (both fetched via secondary summaries; the Nature Medicine
full text redirected to a login wall and was not read directly). Their published workflow selects a
**stimulation-entrained gamma** biomarker via an automated, data-driven analysis "without a priori
assumptions on optimal frequency bands or recording locations" (i.e., closer to this platform's
Biomarkers-page grid search than to Medtronic's own peak-picking) and then sets thresholds so that
falling below the lower threshold raises current (to control bradykinesia) and rising above the upper
threshold lowers it (to control dyskinesia) — the opposite polarity relationship from a pain biomarker
whose power is expected to *fall* with effective stimulation, which is precisely the sign-coherence
question `EvidenceTrianglePanel.js` exists to check for this participant's own band. Neither paper's
available summary describes a published, clinician-facing "is this configuration deployable" report
comparable in structure to this module's page; the closest published analogue to a machine-readable
readiness report is the Stanslaski et al. methodology paper's description of clinician judgment
criteria (GIC score) rather than a computed statistical or rule-based verdict.

**FDA approval and clinician programming guide (A610).** Already the primary source for this module's
device-rule table (`DEVICE_percept_rc.md` §2, §13); no new information was found beyond what that
document and `constraints.py`'s 51 encoded rules already carry. The absence of a published numeric
criterion for "too-close" or "inverted" captures (D26) is corroborated by `authority.py`'s own comment
that Medtronic's alert trigger is documented only in words ("minimally responsive"), which this module
resolves with its own declared, labelled threshold (`MIN_CAPTURE_SEPARATION_D`) rather than a
manufacturer number — consistent with house rule §2.4 and decision log's treatment of composed vs.
measured constants.

**Summary judgment on the literature comparison.** Published aDBS workflows (Medtronic's own and the
two academic groups surveyed) lean on **real-time clinician observation during a programming visit**
plus a simple capture-and-compute rule for the threshold value itself, and do not appear to publish a
structured, multi-edge, sign-coherence pre-visit report of the kind this module builds. This module's
approach — estimate the causal triangle from the ambulatory record before the visit, and refuse to
license a configuration whose signs contradict the selected control law — is more conservative and
more automated than any workflow found in this search, and no counter-example (a published pain-aDBS
readiness report to benchmark against) was found; pain is not an FDA-labelled indication for adaptive
DBS on this device, so no directly comparable clinical workflow was expected to exist.

## 7. Gaps and what I could not verify

- **The 2026-09-12 review's C1 hemisphere bug** (a right-hemisphere candidate silently judged against
  the left lead's impedance, captures and current) — the current `pipeline.py` and `adapter.py`
  contain comments citing "review C1, 2026-09-12" as the reason for the side-resolution logic now in
  place, and the logic read (deriving `_sens_hemi`/`_act_hemi` from the candidate first) matches the
  review's own recommended fix. I did not find or run a live before/after proof for a right-side
  candidate in this pass (that would require the bridge and a right-side `BandCandidate`, out of scope
  for a read-only pass), so I report this as **apparently fixed by reading, not confirmed live**.
- **Whether `report_for_participant`'s dozen bolted-on keys have ever caused a field to disagree with
  the pipeline's own report** (e.g., a stale `band_stability` served alongside a fresh `edges`) was not
  tested; each bolt-on has its own try/except and its own staleness story, and I did not find a single
  shared cache key or timestamp that would let a reader confirm all dozen keys came from the same
  build. This is a structural risk (§2a) rather than an observed failure.
- **The sign-off card's dual verdict source** (§4, item 10): I read `DeploySignoffCard.js`'s first ~90
  lines and its `EvidenceVerdictLine` (reads the pipeline's `rep.verdict`); I did not fully trace every
  remaining line of that ~300+-line file to confirm whether `summary.data.verdict` is printed anywhere
  else on the same card. Flagged as a likely but not fully confirmed duplication.
- **Whether the referent test (`ClosedLoopSim.referent.test.js`) currently passes** was not run (no
  suite was executed in this read-only pass, per CLAUDE.md §8 rule 3 and this assignment's read-only
  constraint); its assertions were read as a specification of pinned wording, not as a live pass/fail
  result.
- **The literature section rests on secondary summaries** of paywalled papers (Nature Medicine, npj
  Parkinson's Disease full texts redirected to login walls); the Medtronic scientific-compendium PDF
  could not be text-extracted by the fetch tool. Confidence on every literature claim is MEDIUM for
  this reason, and would rise to HIGH with direct access to the full texts or institutional login.
- **The StimOptimizer and Biomarkers grid statistics themselves are out of scope** per the task
  assignment and were not audited beyond the interfaces named (settings-tag matching, provenance
  chains); their own correctness is another worker's remit.

## 8. Source index

**Codebase (read directly, HIGH confidence unless noted):**
1. `BRAVO/modules/ClosedLoopDeployment/pipeline.py` — the one-entry-point pipeline, phase ordering, E1/E2/E3 construction.
2. `BRAVO/modules/ClosedLoopDeployment/types.py` — `DeviceConstraint`, `EligibilityReport`, `EdgeEstimate` (incl. `resolved`/`statistically_established` history), `ThresholdPlan`, `ReplayResult`, `DeploymentReport`.
3. `BRAVO/modules/ClosedLoopDeployment/adapter.py` — `report_to_dict` (:1320), `report_for_participant` (:2827), `band_sweep_grid_for_closed_loop` (:548), `write_ground_truth` (:1613), `THREE_SOURCE_RUNS_ON_PAGE`.
4. `BRAVO/modules/ClosedLoopDeployment/authority.py` — control authority, D26 capture verdicts, `MIN_CAPTURE_SEPARATION_D`.
5. `BRAVO/modules/ClosedLoopDeployment/timing_recommendation.py` — `RECORD_DERIVED_TIMING_MS`, provenance of the six-method contest's timing values.
6. `BRAVO/modules/ClosedLoopDeployment/WIRING_stability_into_the_report.md` — the exact wiring of `band_stability` into `report_for_participant`, and the RCS08 `stim_stable`-vs-honest-answer example.
7. `Client/src/views/Reports/ClosedLoopSim/index.js` — page structure, band ordering, the two-endpoint fetch orchestration, `VIEW_STATE`.
8. `Client/src/views/Reports/ClosedLoopSim/DeploymentDecisionHeader.js` — `reconcile()`, the three-cell sub-answer layout, the statistical-gate footnote.
9. `Client/src/views/Reports/ClosedLoopSim/DeviceRuleLedger.js` — the nine-outcome-kind ledger, actor labelling.
10. `Client/src/views/Reports/ClosedLoopSim/WhatWouldChangeThis.js` — the ranked "what would change this" list and its ordering rule.
11. `Client/src/views/Reports/ClosedLoopSim/EvidenceTrianglePanel.js` — the triangle graph, signed axes, coherence reading.
12. `Client/src/views/Reports/ClosedLoopSim/PrescriptionPanel.js` — the transcription table, withholding logic, per-field provenance notes.
13. `Client/src/views/Reports/ClosedLoopSim/BandStabilityPanel.js` — the four-valued stability answer.
14. `Client/src/views/Reports/ClosedLoopSim/ReliableChangePanel.js` — the reliable-change floor card.
15. `Client/src/views/Reports/ClosedLoopSim/ThreeSourceResponsePanel.js`, `ClosedLoopSimulationPanel.js`, `DeploySignoffCard.js` — read for headline logic and data sourcing (partial reads, noted in §7).
16. `Client/src/views/Reports/ClosedLoopSim/stateTracks.js`, `deployFormat.js`, `bandCandidateStore.js` — the N-valued state-track registry, formatting/vocabulary rules, the localStorage handoff.
17. `Client/src/views/Reports/ClosedLoopSim/ClosedLoopSim.referent.test.js` (grepped for pinned assertions, not executed).
18. `BRAVO/Server/APIs/DataAnalysis.py:995` `QueryDeploymentSummary` — the second, statistical-gate endpoint's own docstring.
19. `Client/src/views/Reports/ClosedLoopSim/useDeploymentSummary.js` — confirms the two-endpoint split from the frontend side.
20. `DEVICE_percept_rc.md` (project reference document) — device facts, threshold-mode timing table, calibration recipe.
21. `artifacts/contest_2026-09-13_SYNTHESIS.md` — the six-method timing contest and its adopted design rule (T1–T7 implementation plan).
22. `artifacts/review_2026-09-12_ClosedLoopDeployment.md` — the source of the C1 (hemisphere), C2 (D26 never fed), C6 (stale pooled table) findings discussed in §5 and §7; line numbers in this document are dated 2026-09-12 and were not re-trusted for the current tree.
23. `DECISIONS_and_open_items.md` (project reference document, Part 1 and Part 3) — decisions 9-12, 31, 41, 55-56, 82a-83, 100-101, 122-128, 131-139, 141, 144, 147-160, 164-166, 167-180, 185, 199, 210, 213-217, 220.
24. `HOUSE_RULES_writing_and_claims.md` (project reference document) — the vocabulary rules applied in §3.

**Literature (secondary-source confidence, MEDIUM):**
25. Stanslaski, S. et al. (2024). "Sensing data and methodology from the Adaptive DBS Algorithm for Personalized Therapy in Parkinson's Disease (ADAPT-PD) clinical trial." *npj Parkinson's Disease* 10:174. doi:10.1038/s41531-024-00772-5. https://pmc.ncbi.nlm.nih.gov/articles/PMC11408616/
26. Oehrn, C.R. et al. (2024). "Chronic adaptive deep brain stimulation versus conventional stimulation in Parkinson's disease: a blinded randomized feasibility trial." *Nature Medicine*. https://www.nature.com/articles/s41591-024-03196-z (full text behind a login wall in this pass; read via secondary search summary only).
27. Cernera, S. et al. (2024). Case report on unilateral gamma-based adaptive DBS. *Movement Disorders*. doi:10.1002/mds.30076. https://pmc.ncbi.nlm.nih.gov/articles/PMC11835528/
28. Medtronic. "BrainSense™ Adaptive DBS (aDBS) — ADAPT-PD clinical trial overview." https://www.medtronic.com/content/dam/medtronic-wide/public/western-europe/products/neurological/deep-brain-stimulation/adbs-clinical-trial-overview.pdf (PDF not text-extractable by the fetch tool; title and metadata only).
29. Medtronic. "Scientific compendium, BrainSense™ Adaptive Deep Brain Stimulation (aDBS)." https://www.medtronic.com/content/dam/medtronic-wide/public/western-europe/products/neurological/deep-brain-stimulation/adbs-scientific-compendium.pdf (not fetched in this pass; listed for completeness).
30. NeurologyLive. "FDA Approves Medtronic's Adaptive Deep Brain Stimulation for Parkinson Disease" (February 2025 approval, world-first commercial aDBS system). https://www.neurologylive.com/view/fda-approves-medtronic-adaptive-deep-brain-stimulation-parkinson-disease
