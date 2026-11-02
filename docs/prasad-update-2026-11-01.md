# Prasad update — November 1, 2026

Status: integrated and deployed; hosted acceptance passed November 2, 2026 UTC.
Public publication and final checks are tracked in [PR #23](https://github.com/shirvalkarlab/BRAVO_pain/pull/23).

This update takes Prasad’s intended behavior at face value. The reviewed source
interval is `9d6cafe483349139b5f9a36b30846307d21bf6f5` through
`de7ea132be815384fafae6bee6fa4476395cf4ab` on the lab’s
`ps_closedloop_deployment-5qfvvu` branch (ten commits, latest October 27).
The integration applies source changes on the existing destination history;
it does not merge private or upstream historical ancestry into the lab branch.
Generated bundles, empirical fixtures and private operational material are excluded.

The Biomarkers and Closed-loop pages now show source-specific maps, per-pair
corrected correlation and AUC evidence, recent-report warnings, the home-record
matching control, programmed versus proposed thresholds, and threshold warnings.
The device frequency labels now extend through 125 Hz. Home daily swing and
below-zero threshold warnings retain Prasad’s warning-only behavior: they change
no threshold, current, timing, selection or verdict. Clinic-derived proposed
thresholds remain distinct from settings observed in device reports.

Destination safeguards remain: strict source loading, contact adjudication,
participant-scoped private configuration, read-only viewing, per-window numerical
products, saved-data refresh, and all seven Aditya All Data Streams tabs. The
Aditya program comparisons continue to exclude whole Pacific clinic and home
stimulation-testing days. Ordinary eligible home surveys retain their existing
rules. This update changes neither the testing calendar nor recorded settings.

The combined acquisition identity is `v9_event_contact_adjudication_bins_to_125hz`.
All grid warning modes use distinct `v37` identities so a prior frequency-label
grid cannot cross into a current page even with a warning feature disabled.
No migration, dependency change, provider fetch or original source-job change is
part of this update.

Validation uses isolated databases/cache/storage and independently invented
fixtures. The focused Aditya backend suite passes 400 tests; all five declared
critical modules exceed 95% actual branch coverage. Cache cross-page/feature-mode
regressions and recent-report tests pass 42 cases. Independent source review
confirmed all 78 newly added backend production functions/classes retain canonical method
ASTs (excluding prose), and scoped static review found no remaining actionable integration regression.

Coverage adoption is scoped: new frontend controls and changed readout helpers
exceed 95% branch coverage. Inherited report components retain a disclosed
73–89% whole-module baseline. The owner is the BRAVO integration maintainer;
independent review accepts source parity plus full report/page regressions as
alternative evidence for this bounded upstream import. This is not a claim of
95% coverage across the repository. Revisit each inherited component when its
decision behavior is next changed locally or a regression exposes a gap.
The consolidated frontend suite passes all 185 suites / 1,978 tests, and the
production bundle builds successfully. The complete portable backend CI suite
passes 3,700 tests (14 skipped, 8 deselected). An expanded 131-test synthetic gate
checks actual branch coverage separately for chronic band choice (100/100), daily
swing (28/28), family correction (132/136), recent time split (33/34), threshold
comparison (120/124) and threshold placement (50/52); CI enforces at least 95% in
each. A stale cache-version test expectation was corrected. An earlier local
worker timeout did not recur in its focused rerun; complete Linux CI passed.

Live acceptance verified normal owner/viewer access, identical saved presentation
responses, all seven tabs, sampled tooltips, controls and source-qualified settings.
Native Closed-loop verification used the guarded saved-result reader, with no
fresh model computation; the full native page was not rendered. Existing jobs,
private configuration and data were preserved, target timers restored and
maintenance cleared. These checks do not certify upstream completeness or every
optional analysis.
