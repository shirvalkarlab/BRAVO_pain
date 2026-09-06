# Prasad closed-loop frontend integration — 2026-09-04

Reviewed source delta: `d7ea9795..d745360d898647048213c561d18e30e3064ad8e7`.
Applied as selective file edits on the existing dirty `aditya` checkout, preserving
local target naming, responsive layouts, approved-data provenance, and canonical
research-only API behavior. No branch/index/commit/push operation was performed.

## Behavior

- Added the latest decision header, three evidence/state tracks, device-rule
  ledger (including deferred/advisory rules), evidence triangle, mode controls,
  parameter-plan panel, duty-cycle panel, and research-next-step explanation.
- The canonical `/api/queryClosedLoopResearch` result remains research-only.
  Planning fields absent under `include_planning=False` are explicitly shown as
  unavailable. No numeric programming defaults, readback authorization, or
  clinical readiness is inferred from missing fields.
- Analytic panels use the existing canonical polling client, so HTTP 202 jobs
  resolve to completed responses before entering the result cache. Every heavy
  panel starts only from an explicit Run/Recompute action; saved candidate
  revalidation also requires its explicit button. Merely mounting a page does
  not start scientific analysis.
- Panel caches retain marked stale displays where appropriate, but stale ROC or
  LSB results immediately clear their downstream threshold callbacks. A stale
  ROC result cannot acquire the current matching label. Current ROC and LSB
  controls override overlapping saved request fields.
- The primary research report clears prior evidence for a changed participant,
  band, approved-input identity, or scientific request rather than showing an
  old report as current. The cache implementation separately enforces account,
  participant, approved-data and session boundaries.
- Missing numerical estimates/intervals remain unavailable. In particular,
  serialized null confidence bounds are not zero or evidence of an unbounded
  confidence interval. Incomplete sign comparisons cannot pass the control-law
  evidence track.

## Deliberate deviations from upstream

The upstream clinical-oriented route and unsupported deployment request schema
were not imported wholesale. The existing canonical route, selection validation,
research export, and detailed numeric evidence view were retained. The older
verdict strip is no longer rendered; the new research-aware header replaces it.
The upstream participant-specific demonstration JSON fixture was not imported;
all new regression fixtures are synthetic. The current fluid analytic-panel
layout was retained rather than replacing it with the upstream entire-page
layout.

## Frontend file scope

Under `Client/src/views/Reports/ClosedLoopSim/`, added/imported:
`DeploymentDecisionHeader.js`, `DeviceRuleLedger.js`, `DutyCyclePanel.js`,
`EvidenceTrianglePanel.js`, `PanelStaleNote.js`, `PrescriptionPanel.js`,
`StateTrack.js`, `WhatWouldChangeThis.js`, `deployFormat.js`, `stateTracks.js`,
`ResearchDeploymentPanels.js`, and `useDeploymentReport.js`.

Adapted existing local files: `index.js`, `ResearchEvidencePanel.js`,
`ConversionModelPanel.js`, `DeploymentRocPanel.js`, `EraRefitPanel.js`,
`LsbPowerPanel.js`, `PsdLsbPanel.js`, `useDeploymentSummary.js`, `palette.js`, and
`deployPrint.css`.

Tests added/extended: `ResearchEvidencePanel.test.js`, `researchPayload.test.js`,
`cachedPanels.test.js`; existing `candidateRequest.test.js` remains included in
verification. Shared cache infrastructure is documented/tested separately in
`Client/src/database/resultCache*`, `useCachedResult*`, and
`Client/src/views/Reports/{RecomputeBar,moduleCacheKeys}*`.

## Verification

Offline cached Docker image `bravo-ui-client:audit`, network disabled, synthetic
request/response data only: 29 tests across 4 suites passed. No participant
analysis, scientific endpoint calls, browser interaction, or deployment was
performed for this integration subtask.

Whole-file true-branch coverage:

| File | Branch coverage |
| --- | ---: |
| ResearchEvidencePanel.js | 100% |
| candidateRequest.js | 100% |
| deployFormat.js | 100% |
| useDeploymentReport.js | 100% |
| stateTracks.js | 96.82% |

Combined coverage for that scope is 99.23% branches and 100% statements/functions.
The result is not a claim of complete coverage of every visual panel. Full
frontend tests, production build, backend gates, and live application checks are
coordinated separately by the parent integration task.
