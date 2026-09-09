# Findings & Decisions

## Requirements
- Audit ClosedLoopDeployment against the documented DBS deployment gates; fix confirmed defects
  only with explicit go-ahead, given the safety stakes of a clinician-facing programming page.

## Research Findings

### Audit agent (Phase 1) — 13 criteria, 10 enforced, 1 confirmed defect, 2 unwired
The Closed-Loop Deployment page is served by two independent verdict systems: `ClosedLoopDeployment
.pipeline.run()` (device eligibility, edge-sign coherence, threshold placement) and `Biomarkers.
bravo_service.deployment_summary()` (an older "Deploy sign-off card" with its own `gates` list,
built entirely from `Biomarkers.routines.analytics`). Confirmed defect: `deployment_summary()`'s
`stim_stable` gate (`bravo_service.py:6063`, pre-fix) read `st.get("stim_stable")` — the retired
boolean `analytics.py:5436` sets to `p_lrt >= 0.05`, a failure to reject rather than evidence of
stability — instead of the three-way `stability_verdict` the same function already returns
alongside it. Verified directly by reading both exact lines before reporting as confirmed (not
taken on the audit agent's word). Two correctly-built checks, `direction_consistency.
implied_control_direction` (decision 74) and `reliable_change.reliable_change_verdict` (decision
75), have zero production callers anywhere — confirmed by grep.

### Scoping agent (Phase 2) — the two verdict systems already stopped fighting on 2026-09-04
Both `deployment_summary()` and `pipeline.run()` already run on the SAME committed `BandCandidate`,
on the same page (`ClosedLoopSim/index.js`), gated by the same commit step — the task's original
premise (one runs pre-commit, one post-commit) did not hold. `DeploymentEvidencePanel.js` and
`DeploymentVerdictStrip.js` are confirmed dead: not rendered anywhere on the live page, and the
current code's own comments (dated 2026-09-04) already say both were superseded. `DeploySignoffCard
.js`'s headline pass/fail is already read from `pipeline.run()`'s `deploymentReport.verdict_detail
.device_eligible` — the card's own `gates` list is explicitly demoted to "evidence, not permission"
underneath it. Of the sign-off card's 7 gates: only `stim_stable` is a genuine duplicate with an
existing, tested, correct translation to redirect to (`ClosedLoopDeployment/stability.py`'s
`finding_from_stability_result`, not importable due to the one-way `ClosedLoopDeployment` ->
`Biomarkers` import rule stated in `edges.py`); `adaptive_band` duplicates D08's INTENT
(`constraints.py`) but checks the band's centre instead of its edges, a real, separately-flagged
correctness gap; the other five (`validated`, `credible_ci`, `powered`, `forward_validated`,
`deployable_threshold`) are exploration-time statistical checks (mixed-effects significance, power,
forward-chaining CV) with no equivalent anywhere in `ClosedLoopDeployment` and must not be merged.
`deployment_summary()` has ZERO device-rule (51-rule) checking today — nothing to redirect there;
adding a fresh device-rule check into its own payload would recreate the two-verdicts problem the
2026-09-04 rebuild already fixed at the frontend layer.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Fixed `stim_stable` and `adaptive_band` in the same pass, after user confirmation on both. | Both are genuine correctness gaps with existing correct references to check against (D08's own edge rule; the ClosedLoopDeployment side's own three-way mapping); the user explicitly approved fixing `adaptive_band` too once shown the edge-vs-centre discrepancy. |
| Did NOT touch `validated`/`credible_ci`/`powered`/`forward_validated`/`deployable_threshold`. | Confirmed by direct code reading (not assumption) that these serve a different statistical purpose (exploration-time evidence quality) with no equivalent in ClosedLoopDeployment; merging would risk a scientific error of exactly the kind this project's decision log is full of prior corrections for. |
| Did NOT add device-rule detail into `deployment_summary()`'s own response. | User confirmed the pipeline already driving the card's headline is sufficient; a backend duplicate would recreate the fixed two-verdicts problem. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Host suite (pytest-based) unreachable from this session — no pytest on the sandbox Python interpreters or inside the live container. | Ran a substitute cross-module import check confirming `ClosedLoopDeployment.adapter`/`stability` and the edited `Biomarkers.bravo_service` still import together; disclosed the gap rather than claiming the suite ran. |

## Resources
- `DECISIONS_and_open_items.md` decisions 82 (audit) and 83 (fix).
