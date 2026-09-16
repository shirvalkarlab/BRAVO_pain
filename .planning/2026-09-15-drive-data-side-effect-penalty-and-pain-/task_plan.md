# Task Plan: Drive data, side-effect penalty and pain scaling audit

## Goal
Audit, with reproducible proof, three things in `BRAVO/modules/StimOptimizer`:
(A) every dataset imported from Google Drive / Google Sheets (the clinic + home titration
workbooks under `BRAVO/_pro_dump/clinic_sheets/`), what was parsed, what was dropped and why;
(B) how side-effect scores (REDCap severity ladder AND the clinic sheet "SIDE EFFECT / SCORE"
column) enter the Bayesian optimizer's objective / safety model as a penalty; (C) how verbal pain
scores from the sheets and the REDCap PRO items are put on ONE common scale before they reach the
surrogate. The PI's stated premise is "scaled to 0-100, NRS x10". Confirm or correct that premise
with evidence (code lines, tests, and live numbers on RCS08), not assertion.

## Next Step
Done. Nothing open from this audit. Wednesday's sheet is the first with score-2 rows and moderate/severe possible; decisions 164-166 all bite then.

## Current Phase
Complete (7/7)

## Constraints (from the PI's house rules and the session skill)
- Audit only. No code changes unless a defect is proven; if one is, it goes through the
  normal handoff + rebuild + bridge-suite rules (bravo-session-rules).
- Every claim in the final report must cite a file:line, a test name, or a live number
  with the command that produced it (HOUSE_RULES_writing_and_claims.md).
- Numbers from the container go through `BRAVO/_agent_bridge/bridge_client.py`.

### Phase 1: Inventory the Google-Drive-imported data
- [x] List every workbook under `BRAVO/_pro_dump/clinic_sheets/` (name, sheets, row counts, dates)
- [x] Read the stored ingest manifest (`clinic_pain._manifest_counts`): steps parsed, prose unparsed, skipped-no-setting, per file
- [x] Read `clinic_pain.py` header parsing: which columns are recognised, which workbook layouts exist (the "SIDE EFFECT/SCORE" two-row header vs free-text "Side Effect?")
- [x] Record per-file: has numeric side-effect column? which pain columns present (Verbal, Head, Back, Leg, Foot, Overall)?
- **Status:** complete

### Phase 2: Side-effect score -> optimizer penalty
- [x] `routines/objective.py`: `side_effect_penalty` ladder (none/mild/moderate/severe -> NRS points; +inf?), `se_observed`, how J is composed
- [x] Trace which side-effect SOURCE feeds `build_objective` on RCS08: REDCap epochs (adapter.py) vs clinic sheet `side_effect_score` (clinic_pain.py:760 `se_severity`)
- [x] `safety_ceiling.py` / `stage1_openloop.py`: the GP over side-effect severity and the safe set; the 4.5 mA PI ceiling vs the fitted surface
- [x] `routines/stage_gate.py:69`: the "amplitude does not predict severity (rho=-0.013)" finding -- what it gates
- [x] Confirm the acquisition function sees the penalty (routines/acquisition.py, surrogate.py)
- [x] Tests that pin the ladder: test_core.py:71-81, test_core.py:257; run them in the container
- **Status:** complete

### Phase 3: Pain score scaling (REDCap PRO items and sheet verbal scores)
- [x] `objective.scale_factor` / `resolve_items` / `build_objective`: the common reference scale and per-item factors (adapter.py:115 PRO_ITEMS; adapter.py:492 "nothing is rescaled")
- [x] `clinic_pain.py:199-202` verbal-score regexes (`n/10`, `out of 10`, arrows) and `clinic_pain.py:714` "no rescaling" -- what scale the sheet scores land on
- [x] Determine whether the premise "0-100, NRS x10" or the inverse "0-10, VAS /10" is what runs; check the frontend / plots for any second rescale (double-scaling risk, test_core.py:277)
- [x] Live on RCS08 via bridge: print primary_item, primary_scale_factor, min/max of J_pain, min/max of the raw item, and of the clinic-stream verbal scores
- [x] Run test_core.py, test_clinic_pain.py in the container
- **Status:** complete

### Phase 4: Proof and report
- [x] Assemble the evidence table: claim -> file:line / test / live number
- [x] State plainly where the PI's premise is confirmed, where it is inverted-but-equivalent, and any real defect
- [x] Write the audit report to `docs/` or a handoff doc per house rules; update MEGA_HANDOFF §0 only if code changed
- **Status:** complete

### Phase 5: Fix the safety-seed leak (PI, 2026-09-15: "apply the fix now, with a test, before Wednesday")
- [x] RED: test that a moderate/severe (infeasible) epoch is NOT a tolerated anchor; run in container; watch it fail
- [x] GREEN: minimal change in safety_ceiling.tolerated_anchors; watch it pass
- [x] Full StimOptimizer suite + bridge suite PASS=N FAIL=0
- [x] Live re-check on RCS08: anchor counts unchanged (no moderate/severe on record today)
- [x] Handoff/decision entry per house rules; commit + push per bravo-session-rules Rule 4
- **Status:** complete

### Phase 6: Sheet score 2 ("mild persistent") costs 2.0 NRS points (PI, 2026-09-15: "yes score 2 cost more" / "2")
- [x] Grep every place that enumerates severity labels (objective, clinic_pain, surrogate caps, plots, service, frontend)
- [x] RED: side_effect_penalty("mild_persistent") == 2.0; clinic label map 2 -> "mild_persistent"; expansion cap accepts it; watch fail
- [x] GREEN: minimal change; whole StimOptimizer directory green
- [x] Live RCS08: J_SE distribution unchanged today (no score-2 rows on record); state it
- **Status:** complete

### Phase 7: The amplitude-vs-severity statistic is recomputed live, never hard-coded (PI, 2026-09-15: "recompute always")
- [x] Read stage_gate.py L860-890 (the runtime sentence) and stage2_closedloop._amp_windows; find the call sites and what data they can see
- [x] RED: a function computing Spearman(amp, side_effect_score) over scored clinic steps with stim on, per side + pooled, with n and "not assessable" below a floor; the gate text carries the live value or the reason
- [x] GREEN: wire through bravo_service.two_stage_block -> evaluate_gate; remove -0.013 from every runtime string; reword the two docstrings and TWO_STAGE_DESIGN.md L185
- [x] Live RCS08: print the recomputed statistic (expected: not assessable or weak, 15 scored rows) and the gate row text
- [x] Both suites, decision entries 165/166, commit + push
- **Status:** complete

## Decisions Made
| Decision | Reason |
|----------|--------|
| New plan dir rather than extending 2026-09-11-make-closed-loop-work | That plan is 22/22 complete and landed; this is an audit, not a build |
| Probe consumer name = stim_optimizer | CacheStore provenance refuses unknown consumers (SelfDerivedProduct); the service's own name is the honest one |
| mild_persistent = 2.0 NRS points, finite | PI's number ("2"); finite keeps it outbiddable, unlike moderate/severe |
| Statistic floor SEVERITY_EVIDENCE_MIN_ROWS = 10; current = max of the two sides | below 10 rows a correlation is noise; the sheet scores the patient's experience of the whole step |
| Fix keyed on reported se_severity, not `feasible` | `feasible` is also False for unrated epochs (17/92 REDCap); keying on it would change live tolerated counts beyond the defect |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| SelfDerivedProduct: 'audit_probe' not an allowed consumer | 1 | used consumer="stim_optimizer" |
