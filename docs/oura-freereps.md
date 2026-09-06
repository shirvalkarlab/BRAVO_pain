# Oura – FreeReps in BRAVO

Open a participant, then **Customized Analysis → Oura – FreeReps**.
This is a selective adaptation of FreeReps visualization workflows inside the
Aditya application. BRAVO remains the owner of data ingestion, QC, permissions,
storage and scheduling. No separate FreeReps server, database, Tailscale, AI
connection or background synchronization is installed.

## Views

- **Overview:** latest eligible value and observed-day count per available metric.
- **Sleep:** select a session, inspect five-minute stages and HR/HRV samples.
- **Trends:** select a metric; view daily values or weekly/monthly observed-day means.
- **Compare:** select two metrics; inspect same-Oura-day pairs, Pearson r and paired-day count.

The initial date range ends at the latest stored measurement and spans 90 days.
Date fields and All history can change it. Refresh view reads the current local
store; it does not start another Oura sync. The shared timeline remains available
for Oura/neural/survey overlays.

## Data contract

`POST /api/queryOuraFreeReps` accepts `ParticipantId`, and optionally `SleepId`.
The endpoint authenticates and checks participant access before using the shared
report cache. It reads `loadOuraRingData(participant)` with the standard QC path.
It never exposes raw-source or credential controls.

Overview contains daily metrics and compact sleep-session summaries. Detailed
samples are fetched only for the selected session. Missing/masked sample values
remain null; stage gaps are not joined or stretched. Oura day labels are retained
as dates. Sleep boundaries display Pacific time; HR/HRV axes show elapsed hours
from the session start, including any gaps and daylight-saving changes correctly.

Daily sleep metrics use the longest eligible session by time in bed per Oura
day; naps are not added. All eligible sessions remain selectable. Main sleep
HR/HRV are arithmetic means of the available QC-eligible samples, explicitly
distinct from proprietary Oura summary algorithms. Daily scores appear only
where that actual score was imported; readiness is never substituted for sleep.
Partially eligible sessions may expose remaining samples while their daily
summary stays excluded. Missing values are not converted to zero.

Weekly/monthly points average only observed days in the selected date range;
the hover count exposes partial periods. Correlations pair daily observations by
exact Oura day and require at least three pairs with variation in both variables.
They are exploratory associations, with no p-value, causal or clinical claim.

The existing nightly/manual preparation cycle also warms the compact overview.
Sleep details remain on demand. Cache identity includes participant, access,
source revision, QC identity and adapter version. Increment
`modules/OURA/FreeReps.py:VERSION` whenever adapter semantics change.

## Upstream provenance

- Repository: https://github.com/meltforce/FreeReps
- Reviewed revision: `d50316d835f84f263c81f4a7fb7268ae26bfe11f`
- License: MIT, copyright 2025–2026 meltforce;
  [retained license](third-party/FreeReps-LICENSE.txt).
- Adapted code: `server/web/src/components/sleep/Hypnogram.tsx`,
  `server/web/src/utils/stageColors.ts`, and Pearson logic from
  `server/web/src/utils/stats.ts`.
- Adapted workflows: dashboard metric cards, sleep selection, trends and
  correlation exploration. BRAVO uses its existing MUI and Plotly dependencies.

Changes from upstream include the Oura **Light** label instead of Apple **Core**,
exact-duration stage widths, explicit session bounds, preserved QC gaps, and
centered Pearson sums. BRAVO's adapter, API, date aggregation and participant
integration are first-party code; this is not the complete FreeReps application.

## Validation and deployment

Run `scripts/bravo-validate check` for the portable backend/frontend/coverage/build
gate. New critical scope includes the Oura adapter, API, date/statistic helpers
and request lifecycle hook. Real-data source reconciliation and actual Chrome
checks are separate. Acceptance evidence is recorded under
`reports/oura-freereps/` (local, ignored). Deployment follows
[local-deployment.md](local-deployment.md).
