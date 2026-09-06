# Latest source dates beneath Sync Data

The local dashboard shows four RCS08 values in Pacific time: latest reviewed REDCap survey, Percept JSON session, Percept PDF session, and latest Oura measurement. Source details distinguish represented session/measurement dates from arrival, export, and BRAVO job completion. Missing values remain unavailable, and incomplete source coverage is explicit.

REDCap uses published corrected routine-survey timestamps and valid testing-day context. JSON uses validated native session boundaries in existing settings caches, including SessionDate/SessionEndDate, never the decoder's estimated file date. PDF uses the first-page Session Date, preserving minute precision. The latest real PDF header, September 4, 2026 at 16:56 Pacific, matches native JSON SessionDate 23:56:45Z; its later 16:57 export footer is excluded. All 580 local PDFs were readable. Metadata indexing does not change the original reports or ingest scientific data.

## Oura: final user decision is no hosting

The user explicitly selected **Use latest measurement; no hosting**. The displayed Oura value is the most recent valid recorded HR/HRV sample timestamp in the data already fetched through the existing Oura connection. It is not the exact Oura Last App Sync, a notification time, the BRAVO fetch time, or proof that every daily summary is current. Full-day activity arrays, daily summary midnights, absent samples, missing values and future times must not invent a later measurement.

The existing daily/manual Oura sync computes and saves this small metadata snapshot. Normal Status polling reads only saved metadata and never fetches Oura data. No extra automatic fetch, webhook subscription, receiver, public hosting or credential is required. Initial publication may index the already stored Oura data without contacting Oura or changing the stored measurements.

The existing BRAVO nightly maintenance automation was verified ACTIVE, once daily at 03:00 Pacific. The local manual worker has no separate nightly timer. This configuration does not establish that a future scheduled run has completed successfully.

An earlier webhook hosting proposal was prepared for review and then superseded by the user's no-hosting decision. It remains an unused review artifact under `integrations/oura-webhook/`. Nothing was published or connected to an external receiver. The exact website Last App Sync was independently verified as September 4, 2026 at 14:45; that observation is not hardcoded into the source-date display.

## Verification

Unit tests cover Pacific dates and DST, invalid/future/zone-free timestamps, partial and unavailable states, participant isolation, actual sample times versus fetch/day-summary times, missing observations, and dry-run behavior. Isolated browser acceptance is text-only, uses the authorized local admin account, and never presses Sync Data. It compares all four rendered values with the authenticated Status response, checks the PDF against the independently read report header, and compares Oura with the existing HR/HRV timeline source.

The backend validator now explicitly includes Django's `tests.py` filename in pytest collection, so authentication and sync endpoint regressions run in the full gate. Merely adding that child filename beside its parent directory narrowed pytest collection; the final runner instead extends `python_files` while preserving the original directory list.

See `reports/validation/data-freshness-live.json` for final deployment evidence.

## Final local deployment — September 5, 2026

- The final backend gate passed **1,602 tests, with 47 optional-dependency/private-fixture skips**. Frontend passed **574 tests across 65 suites**; validation-runner regressions passed all 7 tests. The combined gate passed against the final source fingerprints: Python critical scope **1,743/1,748 true branches (99.71%)** across 39 files; JavaScript critical scope **2,527/2,554 (98.94%)** across 48 files, with no declared critical unit below its required threshold. The Oura-measurement and PDF-metadata modules each reached 100% true branch coverage. Whole-repository legacy coverage is not claimed. The earlier frontend report was rejected after the runner/contract fingerprint changed; a fresh full frontend run resolved that provenance mismatch.
- The locked Node 22 production client build and final local image build passed. Both `bravo-server` and `bravo-sync` run `bravo-local:aditya`, exactly matching `bravo-local:measurement-candidate` at `sha256:cbd601170eb4c9adf80202b518906d25a557263a350e7755a7c6f0380bd6ef67`. Rollback `bravo-local:before-freshness` remains `sha256:19686df1dc8393f4060de5d35c47218d533cc5b750a9a7064c2751c845ef608b`. All 11 migration files match rollback byte-for-byte; only the server and sync app services were replaced. MySQL and Redis remained running.
- Immediately before replacement, the manual request status was `completed` and `is_preparing()` was false. After replacement, `index_rcs08_oura_measurement` published metadata from the existing stored snapshot: three eligible HR/HRV channel types, zero invalid records, no partial flag. This initialization performed no external fetch and changed no stored measurement samples.
- `scripts/bravo-appliance check` passed against the final deployment: actual BRAVO HTML, healthy database/storage and no Django check issues. Normal stored admin sign-in passed in isolated Chrome, verifying `UF BRAVO Platform · Aditya` at the exact final URL **http://127.0.0.1:8080/database**. All four rows matched the authenticated Status API, remained unchanged during normal polling, and generated no Start request. The Oura date also matched an independent maximum over valid actual HR/HRV observations returned by the first-party Oura timeline.
- Text-only responsive acceptance passed at viewport widths 1440, 768 and 390px, with the four-row section fully visible and no overflow or browser errors. The verifier records viewport width separately from component width. No screenshot, screen capture, tracing, GUI authentication setting change, external hosting or scientific sync was used.

The final displayed source times are all on **September 4, 2026, Pacific daylight time**:

| Row | Exact represented source time | Display and source coverage |
| --- | --- | --- |
| Latest REDCap survey | 16:45:08 PDT | 16:45 PDT; reviewed survey sources |
| Latest Percept JSON session | 16:57:16 PDT | 16:57 PDT; partial coverage notice retained |
| Latest Percept PDF session | 16:56 PDT | Minute precision; 580 of 580 reports dated |
| Latest Oura measurement | 11:47:13 PDT | 11:47 PDT; latest valid actual HR/HRV sample, not app-sync time |

JSON was independently reconciled against native `Rcs08.db-Report_Json_Session_Report_20260904T165737.json`: `SessionEndDate` is `2026-09-04T23:57:16Z`, and `SessionDate` is `2026-09-04T23:56:45Z`. The native report header supplies the PDF's 16:56 minute. Of 578 eligible cached JSON sources, 569 expose the selected settings-date evidence. The other nine cached exports were independently checked against their native files and are older (latest October 20, 2025); none displaces the displayed maximum. The general partial flag remains because the active-group settings cache is not a complete generic native-date index.

Evidence: `reports/validation/data-freshness-live.json`, `reports/validation/branch-summary.json`, and `output/playwright/freshness-verify.cjs`. Full logs are `/private/tmp/bravo-freshness-backend-final.log`, `/private/tmp/bravo-freshness-frontend-final.log`, `/private/tmp/bravo-freshness-coverage-final.log`, `/private/tmp/bravo-freshness-build-final.log`, and `/private/tmp/bravo-freshness-appliance-final.log`. These are local software/deployment checks, not GitHub CI or clinical validation. No commit or push was performed.
