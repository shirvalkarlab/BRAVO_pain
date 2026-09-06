# UF Brain Recording Analysis and Visualization Online Platform (UF BRAVO Platform)

## Start here: access, data locations and nightly operation

- **View the shared site:** obtain the current HTTPS link and your individual
  viewer credentials privately from the owner. See [lab access](docs/workflow/lab-access.md).
  Viewers cannot modify the shared dataset; local installations use separate accounts.
- **Source release:** the reviewed `aditya` branch in the owner's private BRAVO
  repository; see [clone and setup](docs/local-deployment.md#prerequisites-and-source-identity).
  Public lab publication is separately approved. Keep credentials and participant
  models in private runtime storage, never in Git.
- **Local app:** `http://127.0.0.1:8080`; verify with `scripts/bravo-appliance check`.
- **Nightly exports:** the host's ignored `.env.appliance` sets `RCS08_EXPORT_SOURCE`.
  The intended shared Dropbox destination is
  `<Dropbox root>/PainNeuromodulationLab/PATIENT DATA/RCS08/BRAVO Data/`.
  It contains `REDCap/rcs08_pain_data.csv`, `REDCap/rcs08_stim_testing_dates.csv`,
  and `Oura/oura_*.csv` (including sample-level tables).
  These update after nightly or manual sync; inspect the export manifest for success.
- **Neural input:** `RCS08_NEURAL_SOURCE` in that same local configuration points to
  the host's read-only Percept source folder. It is a separate path from CSV exports.
- **Credentials and reviewed processing rules:** owner-only files under `secrets/`,
  supplied privately. Git contains no usable sign-in or API credentials.
- **Nightly owner:** one Codex maintenance task, 03:00–07:00 Pacific. The sync
  container uses `--external-maintenance` so it does not create a second daily timer.
  See [automatic updates](docs/automatic-updates.md).
- **Moving computers:** resolve the new computer's actual Dropbox root and update
  `.env.appliance` before starting. Do not copy another user's absolute paths.
  The new host must pass login, source-path, export and scheduler-ownership checks
  before it takes over. Until the dated handoff says otherwise, migration is pending.


## Overview

University of Florida Brain Recording Analysis and Visualization Online (BRAVO) Platform is a Python-based data analysis tool for processing and analyzing session data collected with sensing-enabled neurostimulators such as Medtronic Percept neurostimulator.

The BRAVO Repository is an updated version when compared to the original BRAVO_SSR Repository, where developmental features are actively updated. 

The original BRAVO_SSR will be kept alive because it offers capabilities that might be desirable by others, such as Server-side Rendererd Figure Div using Django Template. However, future updates will be primarily focused on the React version for better code organization and figure templating. 

## Repository layout

| Path | Purpose |
| --- | --- |
| `BRAVO/` | Django server, API routes, database models, signal-processing modules, and Python requirements. |
| `Client/` | React frontend source. The combined Docker image compiles this source during its build; the checked-in `Client/build/` directory may lag behind it. |
| `Docker/` | Alternative deployment using separately published server and client images. It does not build the current checkout. |
| `docs/` | Sphinx documentation and longer installation guides. |
| `dockerfile` | Combined local image: current Django source plus a freshly compiled React frontend, served through nginx. |
| `docker-compose.yml` | Local MySQL, Redis, and combined BRAVO application stack. |

## Contributor workflow

Use the `aditya` branch for maintained application work. The local acceptance
entry point is `scripts/bravo-validate check`; setup, precise coverage scope,
source-to-output checks and remaining legacy gaps are in the
[contributor validation guide](docs/workflow/validation.md). This gate runs
synthetic tests and creates a candidate image without replacing the live app.
Private-data reconciliation and actual Chrome journeys remain separate required
acceptance checks. No clean-checkout CI run or release-readiness claim follows
from a local pass.

Keep participant data, credentials, private verification logs and generated
results outside Git. `reports/` and `outputs/` are ignored local evidence
directories; reusable tests and validation tooling belong in the source tree.

## Local performance and restored functionality

The Aditya appliance defaults to four web workers (`BRAVO_WEB_WORKERS`), with
single-threaded numerical libraries per worker. Large read-only reports share
compressed results across workers after rechecking participant access. Source,
survey, annotation, device and raw-recording changes invalidate results; clearing
a report cache invalidates the shared copy too. Concurrent requests reuse one
calculation. No additional GPU service is required.

Managed REDCap score fields appear in the existing multimodal timeline. Missing
responses stay missing and zero scores remain visible. Oura's managed refresh
uses the existing server-owned sync workflow; leaving the page does not cancel it.
Adjacent equal Oura category intervals are drawn as one bar, retaining their exact
start/end boundaries and gaps. Dense numeric channels use accelerated traces with
all points retained and explicit recording separators. Unavailable Lavu/Wong model assets are reported
explicitly; the existing peak-beta analysis remains available.

Local restoration evidence is in the ignored
`reports/restoration-2026-09-03/REPORT.md`, including cold/warm performance,
twenty-reader checks and deployment verification. Timings on this Mac are not a
guarantee for another laptop; a clean checkout does not contain private evidence.

## Git remotes and branch workflow

This checkout combines the branches needed for local Shirvalkar Lab development while preserving their upstream provenance:

| Name | Source | Local use |
| --- | --- | --- |
| `origin` | [Fixel Institute BRAVO](https://github.com/Fixel-Institute/BRAVO) | Fetches all upstream branches. |
| `shirvalkar` | [Shirvalkar Lab BRAVO_pain](https://github.com/shirvalkarlab/BRAVO_pain) | Fetches only `PS_closedloop_deployment`. |
| `development` | `origin/development` | Clean local copy of Fixel development. Do not add project-specific commits here. |
| `PS_closedloop_deployment` | `shirvalkar/PS_closedloop_deployment` | Clean local copy of Prasad's closed-loop work. |
| `aditya` | Initially copied from `development` | Working branch for local integrations and custom development. |

Use `aditya` for ordinary work. Read the repository's [agent instructions](AGENTS.md)
and run `scripts/session_bootstrap.sh` once at session start from this checkout.
It verifies source remote URLs, fetches both sources and reports branch state.
If a parent workspace bootstrap already ran in this session, do not run another.
If the working tree is dirty, keep every local branch and file intact: fetch only;
do not switch, stash, reset, merge, rebase or update another local branch automatically.
Review incoming changes before an explicitly authorized integration on a clean
working tree:

```bash
git fetch origin --prune
git log --oneline aditya..origin/development
# After review, on a clean aditya working tree:
git merge origin/development
```

Fetch Prasad's branch separately and prefer cherry-picking the specific commits needed by `aditya`:

```bash
git fetch shirvalkar --prune
git log --oneline aditya..shirvalkar/PS_closedloop_deployment
# After review, on a clean aditya working tree:
git cherry-pick <commit>
```

Automatic maintenance reviews current Fixel updates first, then selectively adapts
Prasad updates, without a 48-hour observation hold. Aditya's September 6 standing
authorization covers routine execution at 03:00 without manual approval. Source
review, conflict handling, exact-candidate tests/CI and deployed verification
remain required. See [automatic updates](docs/automatic-updates.md) for ownership,
schedule and execution order.

## Local Docker setup

See [local deployment and laptop migration](docs/local-deployment.md) for the
complete human/agent procedure, exact private assets, source-transfer limitations,
single-automation migration, verification and rollback. Restoring an existing
appliance and creating a new empty installation use different steps.

Run the `aditya` checkout with Docker Desktop or a verified Colima Docker runtime and open
[http://localhost:8080](http://localhost:8080) in Chrome. The application is
published only on `127.0.0.1:8080`; MySQL, Redis, and the Django ASGI port stay
inside Docker. Production login protection remains enabled, with debug mode
and public account registration disabled.

For a deliberately empty installation, provision the required private API files
and reviewed processing directory as described in the deployment guide, then
initialize the ignored environment once and start the stack. `init` does not
create those private input files or an administrator account:

```bash
git switch aditya
scripts/bravo-appliance init "/path/to/Dropbox/RCS08/Stage 1"
scripts/bravo-appliance up
scripts/bravo-appliance check
```

`up` waits for service health and runs the localhost check before reporting success.
`check` verifies the loopback binding, database/storage health, HTTP response and
BRAVO application identity. Before handing the app back, also confirm the actual
Chrome tab loaded BRAVO. If Chrome upgrades `localhost` to HTTPS, use and verify
[http://127.0.0.1:8080/index](http://127.0.0.1:8080/index).

For an existing installation, keep `.env.appliance` and skip `init`.
The `init` command creates this file with mode `0600` and refuses to overwrite
it. When migrating a running legacy database it also rotates its former fixed
MySQL credentials in place. The encryption and hash keys must remain paired
with the stored data.

Useful operations are:

```bash
scripts/bravo-appliance status
docker compose --env-file .env.appliance logs -f bravo-server
scripts/bravo-appliance down       # preserves database and storage volumes
scripts/bravo-appliance up
```

This checkout uses the dedicated Docker volumes `bravo_platform_sqldata` and
`bravo_platform_storage`. They do not reuse the legacy global `sqldata` or
`bravo_BRAVOStorage` volumes from older BRAVO checkouts. Docker restarts the
services with its `unless-stopped` policy; the Docker runtime must be running.

### Appliance accounts

Public account registration is disabled in both the user interface and the
server API. Appliance accounts are provisioned directly by an administrator;
plaintext passwords are never stored in this repository. A `Viewer` account
may query and visualize accessible data and change its own display settings,
but the server rejects uploads, downloads/exports, annotations, labeling,
participant or study changes, source-file changes, and other unapproved API
operations. The restriction is enforced server-side even if an older browser
bundle still displays an editing control.

### Automatic RCS08 data synchronization

One nightly maintenance runner owns the **03:00–07:00 America/Los_Angeles** window.
After reviewed Fixel and Prasad source updates, it invokes the one-shot data and
report preparation command in `bravo-sync`. That container separately processes
explicit Sync Data button requests; it has no independent automatic timer.
The nightly data phase updates these streams:

| Stream | Source | BRAVO destination |
| --- | --- | --- |
| Neural | Read-only Dropbox bind mount containing Medtronic Percept session-report JSONs | Native `SourceFile`, device, therapy, and recording tables/files through the same decoder used by browser uploads |
| REDCap | RCS08 project API | Native `ScaleForms` and `ScaleRecord` rows for the daily survey |
| Oura | RCS08 personal access token and Oura API v2 | Native `OuraRingAPISource` data referenced by the BRAVO database |

The sync is idempotent: neural JSONs are deduplicated by their keyed content
hash, REDCap records are replaced only after a complete successful pull, and
Oura refetches and replaces the current and preceding 28-day windows to capture
late updates. The first Oura run performs the historical backfill from
`RCS08_OURA_START_DATE`; later runs are incremental. REDCap wall-clock survey
times are interpreted explicitly in Pacific time, including daylight-saving
changes. The daily survey uses the reviewed Percept processing rules in
`secrets/rcs08_processing/`: timestamp/value corrections, completion checks,
standard MPQ scoring, suspect VAS zeros, reviewed exclusions and stimulation-testing
dates. Original rows and the complete inclusion/exclusion table are retained in
encrypted audit storage. Fixed fluctuation and Stage 0 instruments remain separate
forms with their own timestamps. The rule files and fixed tables are required
read-only inputs and travel with the appliance backup.

After sync, preparation covers existing neural, multimodal, snapshot and therapy
reports, then default pain-score and data-availability views if at least 90 seconds
remain. It never precomputes full biomarkers, optimizers, closed-loop analyses or
parameter grids. Those run on demand. Saved results survive restarts and are
invalidated by input or processing changes. While preparation runs, existing cached
views remain available. Each cycle runs in a supervised worker process; at its
deadline the whole worker process group is stopped and report revisions invalidated.
Committed streams remain available and incomplete work can be retried safely.

Host-only configuration is intentionally excluded from Git:

- `.env.appliance` defines `RCS08_NEURAL_SOURCE`, the absolute Dropbox folder
  on this Mac, and optional `RCS08_OURA_START_DATE`.
- `secrets/rcs08_redcap.json` and `secrets/rcs08_oura.json` contain the API
  credentials, are mounted read-only, and must have mode `0600`.

Automatic maintenance never starts or catches up outside 03:00–07:00 Pacific.
A 04:30 start has only 30 minutes left; source-update time counts against the same
window. The one-shot entry point enforces this even if invoked late:

```bash
docker compose --env-file .env.appliance exec -T bravo-sync python3 manage.py run_rcs08_maintenance
```

An optional `--deadline-epoch` can shorten the window, never extend it. Explicit
manual sync may run outside the nightly window, with its own two-hour maximum.
A shared lock prevents concurrent manual and nightly cycles. A child-side watchdog
enforces the cutoff even if its invoking supervisor disappears. Timeouts and failed
views are reported rather than marked ready. The runner must inspect returned
`research.status` as well as process exit status: source/standard-report preparation
can succeed while an optional common research view reports `failed` or `skipped_budget`. Private logs and status live in the
persistent `BRAVOStorage/sync-state` directory. Inspect count-only summaries and
failures without exposing credentials or participant data:

```bash
docker compose --env-file .env.appliance logs --tail 100 bravo-sync
docker compose --env-file .env.appliance exec -T bravo-sync \
  python3 manage.py sync_rcs08 --dry-run
```

An administrator can also run the same three-stream workflow from the Dashboard
with the red `SYNC DATA FROM REDCAP, DROPBOX, AND OURA` button. The web server
queues the request through shared appliance storage, and the credential-bearing
`bravo-sync` container normally claims it within about 10 seconds (or after an
ongoing scheduled sync finishes). Navigating away or closing the tab does not
cancel the request. On return, the page retrieves the saved status and resumes
monitoring. Another tab/user's active request is followed rather than started
again. A temporary connection failure disables new submissions until status can
be checked; a long-running sync is not reported as failed merely because time
has elapsed. Completion and failure summaries remain visible on return. Viewer
accounts cannot see or invoke this control.

Only one scheduler can own the queue, and manual, scheduled, and command-line
sync execution share a storage lock. A restarted scheduler marks an interrupted
manual request as failed so it can be retried. Each neural file's database import
and duplicate marker commit together; interrupted files can be retried. REDCap
replacement is transactional. Oura publishes a new file path and hash together
instead of overwriting the file still used by readers. Previous Oura snapshots
are retained for recovery, so storage usage grows with changed snapshots. A
hard interruption can also leave unreferenced import files on disk; these are
not exposed as successful database imports. Successful streams remain available
if another stream fails; a failure summary does not mean everything was rolled
back. Source data stays read-only.

On a replacement laptop, restore the BRAVO backup, run `sync-source` with that
laptop's Dropbox folder, and start the appliance. The mode-`0600` sensitive
backup carries the two API credential files; no manual data pull is part of
ordinary operation.

### Backup and restore

Create a consistent portable bundle with:

```bash
scripts/bravo-appliance backup
scripts/bravo-appliance restore-check backups/bravo-appliance-<timestamp>.tar.gz
```

Backup briefly stops the application and sync containers to prevent writes while
it captures MySQL and `BRAVOStorage`, then restarts them. The archive is mode `0600`
and contains database data, stored files, the appliance encryption secrets, and
the ignored RCS08 REDCap/Oura credential files.
Treat it as sensitive research data and transfer it only through an approved
encrypted channel.

On a replacement laptop, obtain the exact reviewed Aditya source snapshot and
install Docker Desktop. The current uncommitted integration cannot be obtained
by cloning an upstream branch. Skip `init` when restoring existing data.
Run the restore command only after confirming that existing appliance data
may be replaced:

```bash
docker build -t bravo-local:aditya .
scripts/bravo-appliance restore-check /path/to/backup.tar.gz
RCS08_NEURAL_SOURCE="/path/to/Dropbox/RCS08/Stage 1" \
  scripts/bravo-appliance restore /path/to/backup.tar.gz --replace-existing-data
scripts/bravo-appliance sync-source "/path/to/Dropbox/RCS08/Stage 1"
scripts/bravo-appliance up
scripts/bravo-appliance check
```

Restore requires an existing `.env.appliance` to match the bundle byte for byte,
including host configuration. Its encryption keys must stay paired with the
stored data. The temporary source-path override handles the destination folder
while restore starts services; `sync-source` then persists that path. See the
deployment guide for mismatch handling, automation migration and rollback limits.

### Frontend build

The Docker image automatically compiles `Client/src/` from the checked-out branch. For a standalone frontend build outside Docker, use the Node 22 LTS line declared by `Client/package.json`:

```bash
cd Client
npm ci
npm run build
```

Optional Fitbit and Google Health credentials remain blank. RCS08 Oura uses the
ignored, read-only credential file described above rather than Compose values or
committed configuration.

## Validation guardrails

Run the appliance checks and bundled-model contract test from the rebuilt application container:

```bash
scripts/bravo-appliance check
docker compose --env-file .env.appliance exec -T bravo-server python3 tests/test_beta_peak_models.py
```

The two beta-peak classifiers in `BRAVO/modules/AIModels/BetaPeakDetection/` were serialized with scikit-learn 1.6.1. `BRAVO/requirements.txt` preserves that runtime version, while `BRAVO/tests/test_beta_peak_models.py` verifies artifact hashes, estimator contracts, deterministic prediction hashes, and warning-free loading. Treat changes to the model files, scikit-learn version, or expected prediction hashes as scientific-model changes that require explicit review.

The frontend still uses the legacy Create React App toolchain and has a substantial warning and dependency-audit backlog. Do not use `npm audit fix --force` as a routine repair: the reported fixes include breaking React Router and build-tool migrations. Modernize those packages as a separately tested change set.

## Documentation

Currently, the active documentation generated by docs folder will be published at [https://bravo-documentation.jcagle.solutions/](https://bravo-documentation.jcagle.solutions/). 
The documentation written using Sphinx with Read-the-docs theme for both Python and Javascript libraries. More information will be described inside the documentation page.

## Front-end Host

Frontend webpage is designed to work with user's local database if the user only installed the Server without frontend. Check out the hosted page at [https://uf-bravo.jcagle.solutions/](https://uf-bravo.jcagle.solutions/) where you simply adjust the Server Host IP to your localhost to use your local database.

## Feature Requests and BUG Report

Please use Github's "Issues" feature to request features or report BUGs. This is an ongoing project and your support in identifying issues in the project will be significantly important for future users. 

## Citation

Cagle, J. N., Johnson, K. A., Almeida, L., Wong, J. K., Ramirez-Zamora, A., Okun, M. S., ... & de Hemptinne, C. (2023). Brain Recording Analysis and Visualization Online (BRAVO): An open-source visualization tool for deep brain stimulation data. Brain Stimulation, 16(3), 793-797.

### Oura – FreeReps

Customized Analysis includes native Oura overview, sleep detail, trends and paired-metric exploration. See [the integration guide](docs/oura-freereps.md) for QC semantics, upstream attribution and validation.

REDCap pre-trial interactive timelines: [metrics, data contract and operation](docs/redcap-pretrial.md).
