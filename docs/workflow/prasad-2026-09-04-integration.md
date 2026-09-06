# Prasad closed-loop integration — 2026-09-04

User-authorized addition to the active responsive-visualization goal. Source: `shirvalkar/PS_closedloop_deployment`, fetched successfully at head `d745360d898647048213c561d18e30e3064ad8e7` (September 4, 18:09 PDT). Imported baseline: `d7ea979552944eff2f6ea0ebebc0208bc47ed683`.

The active `aditya` checkout already contains extensive uncommitted work and selectively adapted Prasad modules. Git ancestry alone overstates missing functionality. Integration applies the reviewed ten-commit net delta to those current files; no branch switch, stash, reset, index rewrite, commit or push. The 35 existing affected files were copied with hashes to `/private/tmp/bravo-prasad-integration-before/manifest.json` before edits. The incoming delta spans 64 paths; 42 original patches applied cleanly in the preflight check and 22 required adaptation or replacement of redundant upstream changes.

## Incoming commits

| Commit | Change |
| --- | --- |
| `27a58068` | Mode-aware prescriptions, duty cycle, replay, threshold wiring |
| `f7a1e9dd` | Withhold programmer values for prohibited configurations |
| `9e07ce8d` | Correct historical handoff claim |
| `e24dd273` | Threshold modes, field provenance and parameter couplings |
| `293a1c98` | Closed-loop presentation and scientific/serialization corrections |
| `362622ae` | Shared result caching and server identity |
| `bba7e5ac` | Server Plotly dependency |
| `8e4ee180` | Cache wiring and cache-correctness fixes |
| `142d382e` | Unified optimum-resolution rule and explicit figure failures |
| `d745360d` | Updated handoff and unresolved-evidence record |

## Aditya adaptations

- Preserve canonical approved-input/QC manifests, access/deidentification checks, async job polling and input-change detection. Do not import source-branch request-supplied observations or programmer settings.
- Keep `/api/queryClosedLoopResearch` and `include_planning=False`. Port supported evidence, mode, rule and provenance displays. Planning/prescription/duty-cycle/titration sections explicitly explain unavailable evidence; no default programmer values, readiness claim, or transcription action is enabled by a retrospective result.
- Keep missing evidence distinct from observed failure; null numerical values must not become zero.
- Cache only completed payloads in memory. Revalidate participant access and server/input/QC/user/session/processing identity before reuse. An identity failure clears the prior result. `202` job-status responses are not analysis results.
- Adapt `queryServerIdentity` to return an opaque HMAC-bound identity after authorization, rather than exposing server-only freshness that could retain a result across account or input changes. It reads metadata and never starts a scientific job.
- Preserve the responsive plot renderers, full local keys, target-display adapters and scientific data/scales. Import binarization/stability and optimizer comparison/error-state improvements on top of them.
- Keep canonical input/model failures as failed jobs. Individual plot-render failures receive explicit sanitized per-figure messages while retaining valid scientific results; raw exceptions stay in server logs.
- The appliance already includes Plotly 5.24.1. Validate the new builders against that installed runtime; do not silently require upstream's uninstalled 7.0.0 pin or claim a clean dependency rebuild.
- Upstream handoffs are frozen under `docs/third-party/prasad/d745360d/` with an explicit historical-evidence disclaimer. Their numerical results are not current local recomputations.

## Validation and deployment

Completed locally on September 4, 2026. Remote freshness was rechecked after integration; Prasad's head remains `d745360d898647048213c561d18e30e3064ad8e7`.

- Full portable backend: **1,426 passed, 47 skipped**. Skips concern optional Torch/GPyTorch/BoTorch and unavailable private-data fixtures; these are not real-participant scientific acceptance results.
- Full frontend: **488 passed across 57 suites**, including the final dropdown-label corrections. Validation-helper regressions: 7 passed.
- The unchanged 95% true-branch requirement passes for every declared critical unit: Python **1,345/1,348 (99.78%)**; JavaScript **2,014/2,036 (98.92%)**. Legacy remainder exceptions stay explicit in `scripts/validation/contract.json`; these are not whole-repository coverage percentages.
- Independent review findings about Start/Recompute, explicit compute intent during identity validation, account/study transport scope, and stale downstream threshold callbacks were resolved and regression-tested.
- Offline cached Node 22 frontend build and Python appliance packaging passed. Runtime Plotly 5.24.1 passed the new builders' tests; a clean dependency download/rebuild and optional Torch model acceptance remain unverified.
- Only the web container was replaced. Final running image and `bravo-local:aditya` both identify `sha256:d1f831d89571e6372ab3a328a93e3cb95e81b37755bb4c0e013bbab507740eb2`. Database, Redis, sync service and volumes were retained.
- `bravo-appliance check` passed database/storage, Django and exact BRAVO URL checks. All **53 manifest JavaScript/CSS assets** served by `http://127.0.0.1:8080` match the final local build. Entry bundle: `/static/js/main.17e41d49.js`.
- Authenticated Chrome verified the Aditya marker, explicit analysis-start states, the empty-candidate research guard, and real biomarker availability timeline/histogram. Existing viewer restrictions for scientific-analysis endpoints remain intact; admin sign-in was used for these routes.
- Responsive optimizer acceptance uses all 20 stored-result Plotly fixtures in Chrome at desktop and 390px width; no new optimizer fit or participant clinical recommendation was generated. New closed-loop evidence panels were exercised with synthetic canonical payloads; no claim is made that a new real-participant closed-loop result was validated.

No participant analysis, sync, device programming, Git commit or push was performed solely for this UI/integration acceptance. Detailed responsive-route evidence is in `responsive-scientific-visualizations.md`. Local validation records are under ignored `reports/validation/`; final deployment/asset checks are `/private/tmp/bravo-final-appliance-check.log` and `/private/tmp/bravo-final-served-assets.json`.
