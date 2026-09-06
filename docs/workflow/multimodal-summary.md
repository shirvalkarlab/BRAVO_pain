# Multimodal Summary and visible sensing intervals

Requested September 5, 2026. Active checkout remains dirty `aditya`; no stash, reset, switch, or bulk source-line merge is authorized. The task's later explicit override authorizes reviewed upstream adaptation now, in Fixel then Prasad order (see `upstream-2026-09-05.md`).

## Implemented contract

- Multimodal Summary is the first, leftmost and initially selected tab in All Data Streams. Specialized tabs retain their selected metrics and visit-window behavior.
- Default window is 28 inclusive Pacific calendar dates, from midnight 27 dates before today through request time. The backend request is `window: past28`; omitted window retains current/previous visits. Optional `window: custom` uses strict inclusive `start_date`/`end_date` and excludes future observations.
- One global bar controls centered five-observation medians, past-28 dates, stimulation context and shared zoom. All three toggles start enabled. Manual dates select a shared custom window; past-28 restores the current calendar window.
- REDCap uses reviewed Left-leg VAS (left axis 0–100) and standard MPQ total (right 0–45), including separate QC-valid visit-survey X markers. Oura uses first-party `steps` and `sleep_total` (already converted to hours, including naps). Oura X markers use the authoritative reviewed visit calendar even when that date has no valid survey.
- Raw points and X markers stay visible when median/context overlays are hidden. Centered medians use up to five observations from the complete reviewed series before date filtering; missing daily dates break plotted lines. This is a display helper, not a new analysis preprocessing policy.
- Neural panels share Neural Data legends, axis formatting, configured threshold traces, point-to-settings selection, complete settings selectors, and latest-record timestamps. Sensing-only intervals still omit control thresholds; thresholds remain configuration guides, not inferred crossings.
- Oura daily and sampled raw observations are unconnected markers in both Summary and the dedicated Oura tab. The enabled median is a separate line overlay.
- Both neural panels reuse source-level home settings/sensing mappings and native ten-minute averages. Summary guide lines break beyond ten minutes; the specialized Neural Data tab retains its established 20-minute guide rule. No data are interpolated. Reviewed clinic dates and overlapping averaging bins remain excluded.
- Every neural interval containing a plotted observation has an open, responsive label card with its Pacific start/end, clinical sensing source, discrete contact pair (e.g. `1 and 3`), and explicit center frequency. Empty settings boundaries remain available in the full settings selector. Machine-readable contact values are unchanged.
- Drag zoom and reset affect all summary plots. Actual hover points show their source tooltips and a shared date guide. Oura daily values are placed at display noon; this is not a measured timestamp.
- REDCap, Oura, and neural hooks isolate pending/results by current account and study scope.

## Acceptance status

Implementation, local gates, deployed image identity and authenticated Chrome verification are complete. No new scientific data sync or model fitting is part of opening the view. Synthetic portable tests and source-to-render comparisons establish software behavior, not clinical validity of upstream research methods.


## Live acceptance evidence (September 5)

The first deployed pass verified four plot ranges, exact first-party Oura values, global controls, real drag zoom/reset, actual point hover, custom calendar dates, restored past-28 window and the unchanged specialized Neural Data current/previous response. Desktop 1440px, tablet 768px and phone 390px all had zero page overflow or axis-text clipping and no browser errors.

Live data exposed 155 generated settings boundaries per side, only 24 of which contain observations. The final display key therefore omits empty boundaries, leaving every recorded interval visible. Backend source, interval timing, all plot values and the full settings selector are unchanged. A regression checks empty, wholly unknown, conflicting, zero-valued power and zero-valued amplitude cases. Final deployment/source reconciliation below supersedes the first pass.


## Final result

- Backend: **1,538 passed, 47 skipped** (optional dependency/private-fixture skips); frontend: **557 passed across 64 suites**. Validation-helper regressions: 7 passed. The stable combined branch gate passed for all declared critical units; new summary helpers/chart reached 100%, summary component 98.28%. Whole-repository legacy coverage is not claimed.
- Production Node 22 client build passed. Workstation node_modules had an incompatible MUI-utils export; the established locked Docker runtime was used instead. Build output was copied back to `Client/build`.
- Both live `bravo-server` and `bravo-sync` run `bravo-local:aditya`, matching candidate image `sha256:da9dde16b14e99da67f798b62acb0b390bcf1f34a201a051f09512c198cc1b0d`. Rollback image is `bravo-local:before-multimodal`. All 11 migration files match the prior image.
- `scripts/bravo-appliance check` passed: database/storage healthy, actual BRAVO HTML returned, Django check clear. Final check log: `/private/tmp/bravo-multimodal-appliance-check.log`.
- Normal stored viewer sign-in succeeded. Real Chrome source-to-render comparisons matched **58 REDCap raw survey points**, **51 Oura daily points**, and **4,852 power/amplitude values per neural panel** exactly. The range was August 9 through September 5, with August 18 and September 2 visit-day markers. The final summary has 48 visible recorded interval cards; specialized current/previous Neural Data has 30.
- Real mouse drag zoom/reset and actual point hover passed across all four charts; toggles preserved all raw/X points; custom dates queried the backend and restored past-28 mode. All four plots had matching widths 1070/672/342px at viewports 1440/768/390px, zero page overflow, zero axis-text clipping, zero interval overflow, and no browser errors.
- Authenticated verification URL: `http://127.0.0.1:8080/reports/redcap-pretrial/81b245ec31594d9894f1dfc9438b6348`. The existing native Chrome report tab was refreshed/focused at the equivalent localhost route, but its expired session redirected to `/index`. Normal sign-in was attempted at `http://127.0.0.1:8080/login`; native accessibility traversal failed with AppleEvent handler errors and the GUI session was not restored. The user explicitly instructed the task to finish after one final non-capture check. Authenticated isolated Chrome verification remains the functional browser acceptance; no successful native GUI sign-in is claimed. No capture or Chrome AppleScript JavaScript setting change was used.
- Text-only browser verifier: `output/playwright/multimodal-verify.cjs`; compact evidence: `reports/validation/multimodal-live.json`. No passwords, session cookies or full source records are written into those files.
- Last upstream fetch matched reviewed heads `ef7234db` and `6f66905a`. The dirty active `aditya` branch remains intact; no Git commit, push, branch switch, stash/reset, scientific-data sync request or live model fit was performed. This is local deployment evidence, not GitHub CI or clinical validation. Existing specialized timeline layouts and Neural Data's 20-minute guide rule remain legacy behaviors outside this summary refinement.

Final handoff: implementation, reviewed upstream adaptation, stable local gates, deployed appliance health/image identity, and authenticated isolated Chrome acceptance are complete. Native GUI sign-in restoration is the sole browser handoff limitation. No further Chrome retry is pending.


### Native browser handoff resolved

The user subsequently signed into the existing Chrome session. Native tab inspection confirmed two existing BRAVO database tabs. One was navigated in the background to the All Data Streams report at `http://127.0.0.1:8080/reports/redcap-pretrial/81b245ec31594d9894f1dfc9438b6348`; subsequent inspection confirmed it remained on that route with title `UF BRAVO Platform` rather than redirecting to login. Appliance health passed again. The native login limitation above is resolved by the user's sign-in. No replacement session, login helper, capture, or authentication setting change was introduced.


## Follow-up revision — September 5

User requested participant/device-scoped historical configuration evidence, summary first/default, neural formatting and threshold/detail parity, and unconnected Oura observations with optional median overlay. Frontend implementation, production build and final-image live browser checks passed. The summary now opens first and retains all ten configured threshold segments per neural side, matching the exact API values and interval boundaries. Both sides expose the same complete-settings panel as Neural Data; real point clicks open the correct interval. Oura daily and sampled points remain unconnected, with a separate median overlay when enabled.

The final image is `sha256:19686df1dc8393f4060de5d35c47218d533cc5b750a9a7064c2751c845ef608b`, running in both app services as `bravo-local:aditya`; rollback is `bravo-local:before-summary-revision`. All 11 migration files are unchanged. Live source reconciliation retained 58 survey values, 51 daily Oura values and 4,852 native values per neural panel. At 1440/768/390px all four plots and interval cards fit without page overflow or clipped axis labels; no browser errors occurred. Verification was text-only, with no screen capture. Final evidence is `reports/validation/multimodal-revision-live.json` and `output/playwright/multimodal-revision-verify.cjs`.

The first full backend pass exposed an outdated synthetic participant fixture; a separate fresh Django import probe exposed an upstream absolute-package import in `authority.py` masked by test path setup. The fixture and import were fixed. A fresh-process regression now imports the service through the same `modules.ClosedLoopDeployment` namespace used by the API, without the standalone test alias. The deployed fresh-process probe passed. Final full-gate results follow below.

The follow-up revision's final portable gate completed before the later source-freshness work: **1,557 backend tests passed, 47 skipped; 560 frontend tests passed**. The stable combined critical-branch gate passed. That gate, the unchanged migration hashes, deployed image identity and `multimodal-revision-live.json` complete acceptance of the follow-up revision above. The subsequent four-row source-freshness deployment and its superseding full-gate results are recorded in `data-freshness.md`.
