# Findings: Clinician adversarial review of the three modules

(Observations only. Agent reports are untrusted until each Critical/High is re-checked against code or a live number.)

## Context carried in
- Today's audit (decisions 164-166): pain scale 0-10; ladder none/mild=1/mild_persistent=2/moderate,severe=inf; SafetyGP seeded
  from the PI's 4.5 mA ceiling + "held long enough" anchors only; rho(amp, severity) recomputed live: -0.04, p=0.895, n=15.
- Contest synthesis 2026-09-13: 3-s readings near-memoryless; current has no measurable effect on the next reading; programmed
  threshold pair (167/166) behaves as one threshold (0.3% between); recommended averaging 3 s vs programmed 30 s.
- Decision 147: verdict on RCS08 flipped unsupported -> "supported (point signs only; 2 of 3 intervals span zero)".
- Decision 142: California-day join moved chronic AUC 0.591 -> 0.571, p 0.035 -> 0.102.

## Phase 2 — verification of every Critical/High (2026-09-15, 15:05-15:35)

Each reviewer claim below was re-checked by me against the code (grep/sed on the working tree) or a live number
(bridge probe output in `BRAVO/_agent_bridge/outbox/`). KEEP / SOFTEN / DROP.

| # | Claim (reviewer, severity) | Check | Verdict |
|---|---|---|---|
| BM-C1 | Corrected stats (n, CI, q) never reach the screen; `BandTimeSweepPanel.js` imported nowhere | `grep BandTimeSweepPanel Client/src` -> only a comment in `Biomarkers/index.js:23`. `BiomarkerHeatmapGrids.js:263-306` reads `best_*_rows` ONLY for `family_wise_significant_8_to_30hz` (the circle); hover template line 299 prints `r = %{z:.3f}` alone. Live (outbox 145037): ONE_THREE_LEFT 12.5 Hz r=-0.534, CI [-0.656,-0.402], n=117, q=0.0022, 300 s. | KEEP Critical |
| BM-C2 | No forward-chaining / reliable-change on the Biomarkers page | grep: `forward_valid|reliable_change|useDeploymentSummary` appears only under `ClosedLoopSim/` | KEEP Critical |
| BM-C3 | Cross-setting stability deliberately absent from Biomarkers request | `Biomarkers/bravo_service.py:5552` comment; `BiomarkerHeatmapGrids.js` has no "stability" string | KEEP Critical |
| BM-H1 | Best cells at 300 s; device averaging range 0-30 s; page says nothing | Live: 12.5 Hz (L 1-3+) and 15.5 Hz (R 0-3+) both `integration_seconds_delivered: 300.0`; AUC 13.5 Hz at 15 s q=0.029. `percept_adaptive.py:178` averaging range from the tip card (0-30 s). | KEEP High |
| BM-H2 | Clinic sheets invisible to Biomarkers | grep `clinic_pain|clinic_steps` under Biomarkers: only a comment in analytics.py; no frontend hit | KEEP High |
| BM-M / XC-H2 | CI is a plain row bootstrap while p is block-permuted | `analytics.py:6552` `rng.integers(0, idx.size, ...)`; `:6247-6248` `block_length_for` + `circular_block_perm_matrix` for the null | KEEP High (two reviewers, same code) |
| SO-C1 | Gate FAILs on the Left's historical 4.8 mA vs 4.5 ceiling, defaulted limits | `stage_gate.py:858-885`: `amp_limits is None` -> `lo, hi = envelope`, `defaulted.append`; live (outbox 144940): "Left: upper limit 4.8 mA exceeds the declared ceiling of 4.5 mA ... DEFAULTED to the delivered envelope" | KEEP Critical |
| SO-H1 | side_effect_vs_current never printed by `ClosedLoopChecks.js` | `ClosedLoopChecks.js:214-240` Numbers() reads `checked`, `ceiling_by_side`, `defaulted`; no `side_effect_vs_current`. Live: rho=-0.037, p=0.895, n=15, 0 above 4 mA | KEEP High |
| SO-H2 | Unscored clinic step counts as "tolerated" | By construction of today's own fix (decision 164): `_intolerable_mask` is False when severity is absent; 15 of 816 steps scored | KEEP High (and note it is a data-collection fact as much as a code one) |
| XC-C1 | Three (four) rating-matching rules, never cross-checked | `local_time.py:33` (California day), `availability.py:1946` (window), `adapter.py:437-469` (epoch + 1-min wash-in), clinic stream by step. Decision 118 measured up to 24 sessions per report at 60 min. | KEEP High (downgraded from Critical: it is a disclosure gap, not a wrong number) |
| XC-H3 | `current_coverage` counts reports, not occasions | `stage1_openloop.py:486-517`: `groupby([L,R])["n"].sum() >= 5`, no time term | KEEP High |
| XC-H4 | Pooled table carries no per-visit estimate | `amplitude_effect.py:267` columns include `n_visits` only; `within_visit.py:342-469` pooled fit, no per-visit slope | KEEP Medium (design gap, no wrong number) |
| XC-L7 | Clinic ingest not scheduled | `~/dev/bravo_daily_ingest.sh` lines 148/168 run `ingest_percept_folder` only; `ingest_clinic_sheets` appears in no script | KEEP Medium (raised: it decides whether Wednesday's scores reach the page) |
| CL-C1 | E1 on the committed band is the screening statistic, drawn like a measured edge, no source flag | Service path (outbox 145626): E1 estimate -4.445, p=0.539, n=32466, 59 clusters, `resolved: true`, note "SCREENING STATISTIC ONLY..."; `edges_historical` = {} (no swap). `EvidenceTrianglePanel.js:138-146`: solid line + arrowhead when `resolved`; the hollow marker (line 29) marks "interval spans zero", nothing marks "screening". `EdgeEstimate` keys: no `source`. | KEEP Critical, reworded: the hollow marker exists; what is missing is the screening-vs-titration distinction |
| CL-H1 | Simulation headline carries no "Low confidence" qualifier | `ClosedLoopSimulationPanel.js:58-80` headline() reads only sim numbers; card rows do show confidence | KEEP Medium (the qualifier is on the same card, one row up) |
| CL-H2 | Occupancy warning "buried in grey prose" | REFUTED as stated: `PrescriptionPanel.js:257-260` draws `occupancy_note` in `PAL.warnText` (amber). True residue: all four notes are amber regardless of `warning`, so amber carries no signal. Live: frac_between 0.0200, warning true, centre 12.39 above median, half-width 2.62. | SOFTEN to Low |
| CL-H3 | "supported" printed before "provisional" | LIVE, not hypothetical: service path verdict = "supported (point signs only; 2 of 3 intervals span zero)", licensed true, "eligible (51 rules checked, 30 advisory)". The reviewer's "blocked" came from its own probe omitting `sensing_hemisphere`/`actuated_hemisphere`. | KEEP High, and correct the reviewer's "blocked" |
| CL-M (reliable change dates) | Pairs' date range not shown | items carry `n_pairs, n_epochs, pooled_sd, df` and no dates (outbox 145626 item keys) | KEEP Medium |
| CL-M (off-label banner) | No standing off-label line on the sign-off card | not re-checked in code this pass; D01/D02 are deferred advisories by decision 148 | KEEP Low, mark as unverified in the frontend |

Dropped: nothing outright; two softened (CL-H2, XC-C1), one corrected (CL "blocked").

## Phase 2 — what recurs, and the Five Whys

Three patterns account for 15 of the 19 kept findings.

**Pattern A — computed, stored, tested, and not on the page** (BM-C1, BM-C2, BM-C3, SO-H1, CL-C1's missing
source flag, XC-H4, the reliable-change dates). Rule 13 in CLAUDE.md exists because of this and it keeps
recurring.
- Why 1: each page prints what its first design asked for (a colour, a circle, a sentence); later backend
  additions were proved by field counts on the response and declared done.
- Why 2: the project's proof standard (field count + difference count on the response) stops at the JSON.
  Nothing asserts that a field becomes a rendered element.
- Why 3: "reached the screen" is verified by string-searching the built chunk (CLAUDE.md §8), which proves
  the code shipped, not that it renders for this payload.
- Why 4: browser verification needs a login that most sessions do not have -- decisions 60, 66, 67, 95,
  106, 159, 162, 163 each end with "not watched in a browser".
- Why 5: there is no fixture-driven render test. `ClosedLoopSim/__fixtures__/rcs08_deployment_payload.json`
  exists and is used by nothing that asserts what a clinician sees; two pre-existing jest failures are
  noted in decision 147 and left.
- Systemic fix: one jest test per card that renders it against the committed RCS08 fixture and asserts the
  exact strings a clinician must be able to read (the n and interval behind a circled cell, the word
  "screening" beside E1, "historical, not proposed" on the gate). Run it in the same quality-gates step as
  the frontend build.

**Pattern B — a floor written as a count, on a record whose independence is in time** (XC-H3 coverage,
SO-H2 tolerated anchors, XC-C1 four matching rules, reliable-change pairs). Root: every minimum was written
as "at least N rows" because rows were what the data had; on a single patient rating twice a day the thing
that decides whether N rows are N pieces of evidence is how far apart in time they were, and no shared
helper answers "how many distinct occasions". Fix: one `distinct_occasions(times, min_gap)` helper in
DecodeCommon, read by coverage, the tolerated anchors and the reliable-change pairs.

**Pattern C — the analysis grain is not the device grain** (BM-H1 300 s cells vs the 0-30 s averaging range;
occupancy at 3 s vs 30 s; the design rule "at this timing"). Root: the Biomarkers grid was designed for
discovery (up to 5 min) before the device's documented ranges were pinned into one home on 2026-09-13
(`percept_adaptive.DOCUMENTED_RANGES`, decision 148/149); no Biomarkers cell reads that table. Fix: the grid
reads `DOCUMENTED_RANGES["averaging duration"]` and marks the rows the device can run.
