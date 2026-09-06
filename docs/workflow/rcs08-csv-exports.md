# RCS08 local CSV exports

The user-authorized Dropbox `RCS08/BRAVO Data` directory receives current stored
data after both nightly synchronization and the red **Sync Data** button. Both
entry points call `RCS08Sync.run_sync`; the export runs there after ingestion.
Dry runs do not write exports. A failed upstream fetch remains a failed sync,
even if export of the latest stored snapshot succeeds. A failed export is also
reported as a sync failure, so it cannot silently claim complete success.

Set `RCS08_EXPORT_SOURCE` in the ignored `.env.appliance` to the existing local
destination. The sync container alone mounts that exact folder read/write at
`/data/rcs08-exports`; neural and processing inputs remain read-only. Compose
refuses to silently create a missing host destination. `scripts/bravo-appliance
init` creates the default local `output/rcs08-exports` directory. For an existing
non-Dropbox setup, create that directory and use the example configuration. The management
command supports another explicit, existing destination.

Initialize or retry from existing stored data, without external fetching:

```sh
docker compose --env-file .env.appliance exec -T bravo-sync python3 manage.py export_rcs08
```

## Files and source meaning

| File | Source / row level |
| --- | --- |
| `REDCap/rcs08_pain_data.csv` | Latest encrypted survey audit's exact reviewed daily pain CSV; includes excluded rows and correction/analysis flags |
| `REDCap/rcs08_stim_testing_dates.csv` | Exact reviewed local testing calendar used by BRAVO's processing rules; dates, not inferred within-day transitions |
| `Oura/oura_daily_activity.csv` | Stored activity recording summaries/descriptors |
| `Oura/oura_daily_activity_samples.csv` | Every decoded activity sample and missing flag |
| `Oura/oura_daily_readiness.csv` | Stored daily readiness summaries |
| `Oura/oura_daily_cardiovascular_age.csv` | Stored daily cardiovascular-age summaries |
| `Oura/oura_daily_spo2.csv` | Stored daily oxygen-saturation summaries |
| `Oura/oura_daily_stress.csv` | Stored daily stress summaries |
| `Oura/oura_heart_rate.csv` | Heart-rate recording blocks and state-label mappings |
| `Oura/oura_heart_rate_samples.csv` | Every stored heart-rate observation and state code |
| `Oura/oura_sleep.csv` | Stored sleep-period summaries/descriptors |
| `Oura/oura_sleep_samples.csv` | Every decoded sleep sample and missing flag |

Oura uses the selected stored `OuraRingAPISource` pointer and hash directly,
without applying analysis QC. It represents all seven streams BRAVO currently
stores, not every endpoint available from Oura. Newly introduced stored stream
names fail explicitly until the mapping is updated. No source data is changed.

Each folder snapshot also contains a readable `README.md` and
`export_manifest.json`. The latter records source identifiers/hashes, CSV row
counts and hashes, and the export time. Export time is explicitly distinct from
represented measurement time and Oura app-sync time. UTC/local observation
timestamps have offsets; REDCap's source timestamp strings remain unchanged.

Generation is serialized, staged completely, and each owned file is atomically
replaced. The manifest is replaced last. This is per-file atomicity, not a
filesystem-wide transaction: an interruption during publication may leave an
older manifest with mismatching file hashes. Retrying replaces the complete
bundle. Unrelated files are never removed. Private generated snapshots are
Git-ignored.

## Focused acceptance

Synthetic export tests cover DST ambiguity, explicit versus regular sample
times, raw values and missing flags, source CSV fidelity, malformed schemas,
unknown streams, unavailable destinations, concurrent export rejection,
publication failure, idempotent file content, and stored-source selection.
`Server/test_rcs08_sync.py` additionally checks exports on the shared sync path,
dry-run/no-op behavior, upstream failures and downstream write failures.

Local validation uses the existing `bravo-local:validation-tests` image without
network or patient-data mounts. No dependency changes are needed. The exporter
uses the standard library and the existing filelock dependency; it does not
depend on pandas or the removed pandas 3 APIs.

2026-09-05 initialization was from the existing stored sources, with no data
sync: all 12 destination CSV hashes and row counts matched the staged manifest.
Private evidence is in ignored `output/rcs08-export-initialize/validation.json`.
The installed management command and exact write mount were subsequently verified, with all 12 destination hashes/counts matching. Both live services now run Aditya image `sha256:00df7e2f73f0eb971543a327dd25dea4aa335955aee4192774aaa05afa5cfa67`; appliance health and authenticated text-only Chrome checks passed. See `output/rcs08-export-initialize/deployed-verification.json`.
