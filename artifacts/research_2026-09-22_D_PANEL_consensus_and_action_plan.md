# Panel D — consensus and action plan on the Closed-Loop Deployment page

Report reviewed: `artifacts/research_2026-09-22_D_closed_loop_deployment_integration.md`.
Panel: three reviewers (biostatistician, engineer, pain neurologist standing in for the PI), a shared message board, discussion and voting until consensus, at most five rounds. Consensus reached in round 3 (three "yes"). Board and votes in the session scratchpad (`debate/D_board.md`, `D_*_r1..r3.md`). Measurements by the orchestrator on the live record, store writes off (`_d231_after.pkl` read by `_d_edges_probe.py`; `_d_right_candidate_probe.py`).

"P": the panel's elicited probability that the action changes or materially strengthens RCS08's programming decision (median of the final votes; range from the lowest low to the highest high of the 90% ranges); elicitation, not measurement. "Measured": the statistic on the live record.

## 1. The headline the panel agreed on

**The page's argument is in the right order; its evidence is weaker than its verdict word, and the page does not yet say why.** The live report for L 1-3+ at 24.5 Hz reads "supported (point signs only; 2 of 3 intervals span zero)", licensed: E1 (current to power) -7.31 device units per mA with an interval from -47.3 to +32.6 (p 0.72, 33 settled points over 5 runs); E2 (power to pain) an area-under-curve of 0.559 with an interval from 0.42 to 0.70 (p 0.45, 32,069 samples); E3 (the control law) p 0.008; the pattern of signs matches and the coherence itself is not bootstrapped (`n_boot` 0). The thresholds (190.5 and 240.5 device units) are a median 3 s reading ± a deterministic minimum and carry no interval; the timing table carries a confidence word, not a number; band stability reads "cannot tell" (underpowered) and blocks nothing. The estimator behind E2 (`edges.state_edge` → `analytics.band_pain_auc`) carries no term for the current in force, and panel A showed the same band family's pain relationship on the grid loses its wholly-positive interval once that current is partialled out; the page says nothing about it. Two verdict strings are printed on the sign-off card. The right-lead check the report could not run was run: a right candidate reads the right lead's own runs and readings (45 points over 9 runs, median 116.3 on 64,721 readings), slope +29.3 per mA (power rises with current, which the Dual Threshold law cannot use), verdict "blocked"; the clinician notes the two leads are "blocked" for different reasons and the page should not describe them alike.

## 2. Adopted actions, in build order

| # | Action | Files | Acceptance test | Cost | Decision touched | P (range) | Measured |
|---|---|---|---|---|---|---|---|
| 9 | Before item 4 lands: un-fold the E2 provisional sentence `consistency.coherence_report` already writes (it names E2's interval and p when it spans zero) so it reads without opening a fold, and one interim static sentence on the E2 axis for a Left candidate in 21.5-26.5 Hz naming panel A's finding (this band family's pain relationship loses its positive interval once the current in force is partialled out). | `EvidenceTrianglePanel.js` | Fixture test: present for Left 24.5 Hz, absent for Right or out of family. | under 2 h | none (a caveat) | 10% (0-40) | yes (panel A) |
| 1 | One verdict on the sign-off card: keep the pipeline's (`EvidenceVerdictLine`, `rep.verdict`), delete the older statistical-gate endpoint's "Summary verdict: ..." sentence (~line 347), keep that endpoint's gate rows as a checklist. | `DeploySignoffCard.js` | Jest first: `queryByText(/Summary verdict:/)` null, RED then GREEN; live: one sentence gone. | 1-4 h | none | 15% (0-35) | the two strings confirmed in the file |
| 2 | "What would change this" (`buildItems()`) reads `data.band_stability` and adds one ranked item between the device-rule and coherence items, an actor ("measurement: more stimulation states") and a "clears" sentence, in the stability card's own wording. | `WhatWouldChangeThis.js` | Fixture tests for "cannot tell" and "behaves differently"; live: one row gained, verdict unchanged. | 2-5 h | none | 15% (0-55) | stability "cannot tell" today |
| 3 | `out["caveats"]`: one flat list of {severity, text, card} built in `adapter.report_for_participant` after `report_to_dict(rep)` from `rep.warnings`, `rep.provisional` and the D26 capture verdicts, naming every page number that carries no interval today (the thresholds, the design rule's minimum separation, the timing table's values, the M0/M1 replay fractions; only M3 is bootstrapped); shown on the sign-off card as the printed record and counted in the header, not as another live stage. | `adapter.py`, `DeploySignoffCard.js`, `DeploymentDecisionHeader.js` | Host test on a constructed report; live field/difference proof: N entries added, 0 removed, 0 differing elsewhere. | 3-4 h + 2 h | none (assembled per request, not stored) | 18% (0-40) | the no-interval fields listed in §1 |
| 5 | The stability finding printed inside `coherence.note` (`consistency.coherence_report`, `pipeline.py`), and `BandStabilityPanel` moved to sit directly after the evidence triangle as its own full-width card (not nested: a nested card loses its weight). The referent test pins no card order. | `consistency.py`, `pipeline.py`, `index.js` | Fixture: "cannot tell" and "behaves differently" appear in the note; render order test. | 3-4 h + 1 h | none | 25% (0-50) | — |
| 4 | E2 re-measured with the left current in force partialled out, for the committed band and its family: the per-sample current already on the joined table (`canonical_amp_col(hemisphere)`, the column E1 and E3 read) becomes one optional argument of `band_pain_auc_from_table`, default off (the Biomarkers grid calls the same function); the adjustment is the linear residualisation `partial_corr` uses (`_residualize` on [1, current]) applied to the per-sample power before the AUC, the label unchanged, and the partial correlation beside it; both with block-bootstrap intervals; reported beside E2 on the triangle. | `Biomarkers/routines/analytics.py`, `ClosedLoopDeployment/edges.py`, `EvidenceTrianglePanel.js` | Synthetic test: current driving both series collapses the adjusted AUC toward 0.5, RED then GREEN; live: the pair with intervals on the report. | 1-2 days (after panel A's item 1) | 147 in wording ("point signs only" gains "and rests on the current in force" when true) | 30% (5-70) | the grid's version (panel A): r 0.33 -> 0.17 |
| 8 | The sign-off card prints the candidate's identity and the grid's settings tag from the response it already holds (the chosen band rides in browser storage by design, `DESIGN_biomarker_pipeline_v2.md` §6; a server record is a separate decision). | `DeploySignoffCard.js` | Fixture render test. | 2 h | none | 8% (0-25) | — |
| 7 | The prescription panel's four provenance notes under one shared heading ("Four independent checks on this number"); wording only, no backend boolean, no severity ordering (the report's `any_check_failed` dropped by all three as cost without value). | `PrescriptionPanel.js` | Render test. | 1 h | none | 5% (0-15) | — |
| 10 | Delete the three unread field groups from the served response (`protocol`, the titration-session plan computed on every request; `edges_historical`; the duty-cycle `predicted_failure_mode` / `qualified_transitions` / `unqualified_excursions`), keeping the functions and their own tests. A whole-tree search finds no reader outside the module, its tests and fixtures. | `adapter.py` | Live proof: N fields removed, 0 differing elsewhere. | about 2 h | none | 3% (0-15) | no reader found |

Resolved without a build:
- **6. The right-hemisphere check (review C1).** Run live: the right candidate reads the right lead's own record (§1). Recorded here; no defect.

Not adopted: the report's proposal to move the reliable-change card (the index was deleted by the PI tonight, decision 231); nesting band stability inside the evidence triangle (moved beside it instead); a server-side record of the chosen band (a separate decision).

## 3. Open questions for the PI

1. Whether E2's wording (decision 147, "established means the point sign") should also say when the sign rests on the current in force (item 4's wording change).
2. Whether the closed-loop page should describe the right lead's block (power rises with current, the control law cannot use it) differently from the left's (point signs only).
3. Whether the chosen band should be recorded on the server (provenance, when, under which settings) rather than in the browser.

## 4. Where the panel disagreed, and how it resolved

- The report's `caveats` list: the methodologist widened it to name every number without an interval; the clinician narrowed where it shows (the printed record, not another live stage); merged.
- The severity boolean for the prescription notes: dropped by all three as cost without value; heading only.
- Item 4's method: the engineer withheld consensus until the adjustment was named; named in round 3 and accepted, with his data-source detail (the joined table's current column) folded in.
- The methodologist lowered item 4's expected payoff after seeing E2's weak raw baseline (an AUC of 0.559 with an interval spanning 0.5): the adjusted version will most likely confirm the existing caveat rather than change the verdict.

## Correction, 2026-09-26 (decision 290)

The E2 baseline this panel quoted -- "an area-under-curve of 0.559 with an interval from 0.42 to 0.70
(p 0.45, 32,069 samples)" -- was computed on the pain ratings of the settings period BEFORE each
3 s piece's own (the Closed-Loop joined table's off-by-one join, 2026-09-03 to 2026-09-25). Run on
2026-09-26 on the full saved tiles, the old join still gives 0.562 on today's record; the fixed join
gives 0.564 (0.438 to 0.678), p 0.29, 43 pain reports, 39,953 samples, and with the current in force
taken out 0.553 (0.441 to 0.673). The methodologist's reading stands: the baseline is weak, its
interval spans 0.5, and the adjusted reading confirms the caveat rather than changing the verdict.
See decision 290.
