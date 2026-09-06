# Deploy the Aditya BRAVO appliance locally

Use this guide for this computer or a replacement research laptop. Commands run
from the **Aditya BRAVO checkout root**, containing `docker-compose.yml` and
`scripts/bravo-appliance`. The combined image builds the current backend and
React source. `Docker/` uses different published images and is not this setup.

The application listens at **http://127.0.0.1:8080/index** by default. This is
reachable on the computer running Docker only. A different laptop or phone
cannot reach it through its own `localhost`, including on the same Wi-Fi or VPN.
Network sharing is a separate deployment change; this guide does not expose a
public port, install Tailscale, or create a tunnel.

## Choose the right starting point

| Situation | Follow |
| --- | --- |
| Aditya already runs here and `.env.appliance` exists | [Update an existing appliance](#update-an-existing-appliance) |
| Move the existing accounts, approved data and settings to another computer | [Move the existing appliance](#move-the-existing-appliance) |
| Deliberately create a new empty database and new encryption keys | [New empty installation](#new-empty-installation) |

Do not run `init` as part of a migration. Restored data needs its original keys.
Do not run Prasad's source branch as another application stack. The local source
tracking branches are references; application work and deployment use `aditya`.

## Prerequisites and source identity

Use a local Docker installation with Compose v2 and Linux-container support,
plus a Bash environment, Python 3, Git, `curl`, `tar` and `shasum` for the helper
scripts. The current validation target is this Mac's Docker environment; other
operating systems and CPU architectures require the same checks on the actual
destination. The image supplies Python/R and Node build dependencies, so a host
Python scientific environment or host R installation is unnecessary.

Docker must be running. The neural source directory must exist locally, with
the required JSON files downloaded rather than cloud-only placeholders. The
first image build needs network access for package downloads. Allow disk space
for the image, database, storage, backup and temporary restore-check copies.

Use the reviewed `aditya` release from the owner's private BRAVO repository.
GitHub access is required; sign in through your own GitHub credential manager.
The public lab branch is a separate publication destination and may lag behind.
For a new checkout, keep the publication remote separate from upstream sources:

```bash
git clone --origin aditya-private --branch aditya https://github.com/ABehal2020/BRAVO.git BRAVO
cd BRAVO
git remote add origin https://github.com/Fixel-Institute/BRAVO.git
git remote add -t PS_closedloop_deployment shirvalkar https://github.com/shirvalkarlab/BRAVO_pain.git
git fetch origin --prune
git fetch shirvalkar --prune
git branch --track development origin/development
git branch --track PS_closedloop_deployment shirvalkar/PS_closedloop_deployment
git rev-parse HEAD
```

Run those clone/setup commands only for a new installation. Existing workspaces
must preserve their remotes, dirty work and divergent branches. Record the exact
published commit and compare it with the owner's accepted release receipt before
restoring data. Fixel `development` and Prasad's source branch do not contain the
complete Aditya integration.

The initial publication uses a reviewed complete source tree on clean upstream
history. It deliberately excludes private files from the maintainer's older local
history. Do not push an older local `aditya` history over it, force it, or treat
its different ancestry as a reason to discard local work. Future releases must
retain the accepted private publication as an ancestor. The appliance backup
contains sensitive data and configuration, not the source repository or image.

Participant-specific conversion models and processing policies travel privately
in `secrets/runtime_assets/`, **not** in Git or the Docker image. Before the first
build after this change, run `python3 scripts/prepare_private_runtime.py`.
The `up` and `restore` commands also run this check. It preserves existing legacy
assets byte-for-byte, refuses conflicting copies, and writes a private SHA-256
manifest. Compose mounts these assets read-only at the same application paths.
See [private runtime assets](workflow/private-runtime-assets.md).

The bundled beta-peak pickle files under
`BRAVO/modules/AIModels/BetaPeakDetection/` remain application assets; record their
hashes separately in the release manifest. Missing optional models must remain
clearly unavailable rather than silently replaced with different weights.

An accepted **built image** is another useful transfer/recovery artifact: it
contains the compiled frontend, backend dependencies and bundled generic model files.
Participant-specific models require the separate private runtime assets.
After confirming that the image tag identifies the accepted build, it can be
exported privately without publishing to a registry:

```bash
set -o pipefail
umask 077
docker image inspect bravo-local:aditya --format '{{.Id}} {{.Os}}/{{.Architecture}}'
docker image save bravo-local:aditya | gzip > /approved/transfer/bravo-aditya-image.tar.gz
shasum -a 256 /approved/transfer/bravo-aditya-image.tar.gz
```

On a compatible destination architecture, compare the archive checksum, then:

```bash
gunzip -c /approved/transfer/bravo-aditya-image.tar.gz | docker image load
docker image inspect bravo-local:aditya --format '{{.Id}} {{.Os}}/{{.Architecture}}'
```

The image does not contain database/storage volumes, runtime secrets, original
neural folders or Codex automation. It also does not replace the source/history
needed for future Git integration. The supplied `up` and `restore` helpers
rebuild source, so an image-only package is **not** a drop-in replacement for the
source-based migration below; it requires matching runtime configuration and a
separately reviewed no-build data-restore procedure. That image-only restore
entrypoint is not currently implemented. Rebuild and verify on a different CPU
architecture instead of assuming this Mac's saved image will run natively there.

For future source updates, retain these remotes and pristine tracking branches:

| Remote | URL | Source branch |
| --- | --- | --- |
| `origin` | `https://github.com/Fixel-Institute/BRAVO.git` | `development` |
| `shirvalkar` | `https://github.com/shirvalkarlab/BRAVO_pain.git` | `PS_closedloop_deployment` |

Agents must read the repository's `AGENTS.md` and any parent instructions. Run
this checkout's `scripts/session_bootstrap.sh` once per session, unless a parent
workspace bootstrap already ran in this session. The standalone clone includes
everything required for this bootstrap; it does not require a sibling directory.
Preserve dirty work and divergence: with a dirty worktree fetch only, leaving
every local branch unchanged. Never stash, reset, switch branches or force a
source update to make deployment convenient. An
archive without Git history can build an image, but cannot support the managed
upstream-update workflow until its correct repository history is restored.

## Update an existing appliance

Keep `.env.appliance`, `secrets/` and the existing volumes. Confirm the checkout
is the intended Aditya source, then run the local acceptance gate described in
[contributor validation](workflow/validation.md). Record the candidate source
fingerprint, test evidence and current running image ID before replacement.

```bash
git branch --show-current
git status --short
scripts/bravo-appliance status
docker compose --env-file .env.appliance images
scripts/bravo-appliance backup
```

Backup stops application writes briefly, then attempts to restart the previously
running application and sync worker. Follow it with `scripts/bravo-appliance check`;
do not assume the cleanup restart succeeded merely because a bundle was created.
Retain the previous image and matching deployment configuration for rollback.
Coordinate with the single maintenance owner so no promotion or fresh manual
sync starts during backup or restore.

After the candidate is accepted and replacement is authorized:

```bash
scripts/bravo-appliance up
scripts/bravo-appliance check
```

`up` builds the current source, recreates services as needed, waits for health,
and calls `check`. Application startup runs database migrations. It is a real
deployment operation, not a harmless browser-opening command. Complete the
[verification](#verify-the-delivered-application) below before reporting readiness.

## Move the existing appliance

Transfer these things through the approved private transfer path:

1. The exact reviewed Aditya source snapshot and repository history described above.
2. A newly created appliance backup whose checksum/restore check passes.
3. The destination's local, readable copy of the original neural JSON directory.
4. The single nightly Codex automation's setup, reviewed for the destination's
   actual paths and host. Automation state is not in the appliance backup.
5. A separately inventoried private operational context package: relevant
   `output/weekly-reviews/` visit, question, confirmation and delivery ledgers;
   nightly notification/deduplication records and upstream observed-head history;
   approved slide specifications, construction helpers, source/readback manifests
   and latest review findings under `output/slides/`. These are ignored and are
   **not** in the source clone or appliance backup. Preserve hashes and identify
   the current authoritative version; do not indiscriminately transfer temporary
   outputs. If upstream observation continuity cannot be verified, start a fresh
   48-hour observation window instead of inventing history.

On the source computer:

```bash
scripts/bravo-appliance backup
scripts/bravo-appliance restore-check /absolute/path/to/bravo-appliance-TIMESTAMP.tar.gz
scripts/bravo-appliance check
```

Use the actual bundle path printed by `backup`. Its contents are:

| Included | Notes |
| --- | --- |
| MySQL dump | Includes accounts, permissions, participant records and stored survey rows. |
| `BRAVOStorage` archive | Includes stored source/recording files, audits and persistent results. |
| `appliance.env` | Includes database credentials, `DATASERVER_ENCRYPTION`, `DATASERVER_HASHKEY`, `DJANGO_SECRET_KEY` and host configuration. |
| Entire `secrets/` directory | Includes API credentials and the private reviewed processing tables when present. |
| Manifest and checksums | Manifest records the base Git commit, not the full dirty source tree. |

The archive is mode `0600`, but it is not itself encrypted by the backup script.
It contains both research data and the keys needed to read it. Keep it in the
approved protected transfer/storage location. Preserve the encryption and hash
keys together with the database/storage; never regenerate them for restored data.

On a clean destination, obtain the source snapshot, install/start Docker and
place the neural folder locally. Resolve the actual readable comparison folder
and writable Dropbox export folder too. Download cloud-only inputs. Make these
directories accessible to the destination Docker VM with the required read/write
permissions; host existence alone does not prove the VM can mount them.
Leave `.env.appliance` absent; **skip `init`**.
Build the expected local image before restoration so storage operations do not
depend on a pre-existing image tag:

```bash
docker build -t bravo-local:aditya .
scripts/bravo-appliance restore-check /absolute/path/to/bravo-appliance-TIMESTAMP.tar.gz
RCS08_NEURAL_SOURCE="/absolute/destination/neural/folder" \
  RCS08_EXPORT_SOURCE="/absolute/destination/Dropbox/BRAVO Data" \
  RCS08_COMPARISON_SOURCE="/absolute/destination/comparison/folder" \
  scripts/bravo-appliance restore /absolute/path/to/bravo-appliance-TIMESTAMP.tar.gz --replace-existing-data
scripts/bravo-appliance sync-source "/absolute/destination/neural/folder"
```

Replace every example path above with the verified destination. If comparisons
are stored in `secrets/rcs08_comparisons`, use that restored directory's absolute
destination path. All three temporary overrides are necessary because `restore`
starts services while the copied `.env.appliance` still contains source-host
paths. The existing `sync-source` helper persists **only** the neural path.
Immediately afterward, privately edit only `RCS08_EXPORT_SOURCE` and
`RCS08_COMPARISON_SOURCE` in `.env.appliance` to the same verified destination
paths. Preserve every credential and encryption value. Do not print the file.
The current restore helper has no general host-path rewrite option.

Only after all three paths are persisted, run:

```bash
scripts/bravo-appliance up
scripts/bravo-appliance check
```

Confirm the actual container mounts and a successful export manifest at the
intended Dropbox destination. Do not create empty input folders merely to make
incorrect source paths appear valid. The export bind explicitly refuses to
create a missing host path.

`restore` replaces the configured database and storage. The explicit
`--replace-existing-data` flag is mandatory. If destination data already exists,
preserve it first and obtain authorization to replace it. If `.env.appliance`
already exists, restoration requires it to match the bundle **byte for byte**;
even a different neural path, port or comment can trigger refusal. This is
stricter than comparing encryption keys alone. Do not delete/regenerate the file
to force a mismatch through; reconcile the intended destination and configuration
with the maintainer.

The Compose volume names are fixed: `bravo_platform_sqldata` and
`bravo_platform_storage`. Changing the project directory or Compose project name
does not create isolated copies of these volumes. Stop any other stack using
them. Do not use `docker compose down -v`; ordinary
`scripts/bravo-appliance down` preserves the data volumes.

`restore-check` checks checksums, credential-file shape, SQL import into disposable
MySQL, and storage extraction. It does not prove decrypted application reads,
correct QC tables, account access, or usable charts. It also accepts older bundles
without a sync-secret archive. Complete the asset and application checks below.

## Private assets required for synchronization

The destination needs `secrets/rcs08_redcap.json` with nonempty `api_url` and
`api_key`, and `secrets/rcs08_oura.json` with nonempty `access_token`. These files
must be mode `0600`. The sync container mounts them read-only; do not add values
to Git, documentation, Compose or shell history.

Preserve the complete reviewed `secrets/rcs08_processing/` directory, including
its `manifest.json` and these input tables:

```text
rcs08_study_stages.csv
rcs08_stim_testing_dates.csv
rcs08_stage1_daily_timestamp_corrections.csv
rcs08_stage1_daily_survey_value_corrections.csv
rcs08_stage1_daily_survey_exclusions.csv
rcs08_fluctuation_redcap.csv
rcs08_stage0_redcap.csv
```

The daily pipeline requires all five daily rule tables. Historical instruments
require the two fixed REDCap tables. `backup` includes this directory if present,
but `restore-check` does not validate its completeness or its scientific content.
Verify it against the approved source manifest. Missing rules must remain an
explicit sync failure; do not replace them with empty files or change exclusions
to get a successful import. Oura/neural QC code and configuration travel in the
reviewed source snapshot; they are not reconstructed from the token files.

## New empty installation

This creates different keys and an empty database. It is not the migration path
for existing RCS08 accounts or records. First obtain the reviewed source, local
neural directory, private credential files and approved processing directory.
Then:

```bash
scripts/bravo-appliance init "/absolute/local/neural/folder"
scripts/bravo-appliance up
scripts/bravo-appliance check
```

`init` creates only `.env.appliance`; it does not create API credentials, approved
processing tables or an administrator account. Public self-registration stays
disabled. The repository has no dedicated idempotent initial-admin provisioning
command. A maintainer can use the existing model API in an interactive Django
shell without placing the password in a command or file:

```bash
docker compose --env-file .env.appliance exec bravo-server python3 manage.py shell
```

```python
from getpass import getpass
from Server.models import PlatformUser
login = input("New administrator login: ").strip()
if PlatformUser.find(email=login):
    raise ValueError("Account already exists; do not recreate it")

user = PlatformUser.create(login, getpass("New password: "), input("Display name: ").strip())
```

`PlatformUser.create` creates the account and its institute with the Admin
membership role. Verify login and institute access before importing anything.
For the configured RCS08 installation, the existing CLI supports an intentional
initial import after these assets/account prerequisites are confirmed:

```bash
docker compose --env-file .env.appliance exec -T bravo-sync \
  python3 manage.py sync_rcs08 --create-participant
```

This command makes real API calls and writes data. Do not run it merely as a
readiness probe. The Dashboard manual-sync control is the usual later workflow.
An empty-install onboarding run has not been established by a restored-database
test; validate the actual new account, sources and charts separately.

## Move the single nightly automation

Follow [nightly maintenance](automatic-updates.md). The current orchestrator is
the Codex heartbeat `bravo-nightly-maintenance`, scheduled at 03:00 Pacific with
a 07:00 cutoff (four hours maximum). It checks Fixel first, then Prasad, then data synchronization and
cache preparation; the source branches have independent 48-hour quiet periods.

Docker does not migrate or create this Codex automation. Move/reconfigure it
for the destination only after source paths, Git remotes, credentials, runtime
and acceptance checks work there. Disable the old host's automatic run before
enabling the destination's; do not leave two hosts refreshing the same sources
or independently promoting code. Verify the actual destination schedule and
record its first completed run. A configured timer is not proof that it ran.

Also verify the destination's BRAVO Codex project, required workflow skills,
authenticated Google Drive/Slides and Slack capabilities, Monday 09:00 Pacific
weekly review, and GPT-6 Astra / High nightly configuration. Restore the private
operational ledgers before any notification-producing run so retries do not send
duplicates. A CLI installation alone does not establish these desktop capabilities.
Use the supported automation tools to transfer/reconfigure schedules, never raw
file copies that could leave both hosts active. Read back both hosts' ownership
state and retain a dated handoff receipt with source SHA, image identity, backup
and private-manifest hashes, resolved paths, acceptance results and scheduler owner.

The `bravo-sync` container now runs
`run_rcs08_scheduler --external-maintenance` and handles manual requests only.
It has no separate automatic nightly timer. If the Codex automation is absent,
the application and manual sync can still run, but automatic nightly updates
will not happen. Keep the laptop awake, Docker running and the host automation
available during its window. Do not add another cron/launchd/app timer beside it.

## Verify the delivered application

After every build/replacement/restore:

1. Run `scripts/bravo-appliance check`. It verifies loopback binding, application
   identity, database/storage health and Django checks. Inspect Compose status
   so the manual sync worker is running too.
2. Confirm the deployed image corresponds to the accepted Aditya source snapshot,
   not just the branch name or mutable `bravo-local:aditya` tag. Record image ID,
   source fingerprint/base commit and test evidence.
3. Open Chrome at `http://127.0.0.1:8080/index` and inspect its actual loaded URL
   and visible Aditya branding. Log in using the provisioned/restored account. Opening a tab
   or obtaining HTTP 200 is not proof of a working browser page.
4. Verify representative REDCap, Oura and neural pages, date ranges, exclusions,
   disabled-feature reasons and the source/overlay toggles. Compare canonical
   input identities/counts with the source appliance when migrating. Verify
   persistent results and authentication after a restart.
5. Check manual sync status and the destination's one automation. Review failures
   and skipped stages; do not treat an interrupted preparation as completed.

Use text-only browser inspection. Do not enable screenshots, screen sharing,
capture helpers or Chrome's AppleScript JavaScript setting. If browser inspection
is blocked, state that limit instead of claiming browser success from server
health alone. Performance on this Mac is not a guarantee on another laptop;
measure common cold/warm pages and representative simultaneous readers there.

## Rollback and recovery

Before replacement, retain the previous image **and its matching Compose/source
configuration**, plus a verified data backup when data/schema changes are possible.
The backup script records a base commit but does not save the dirty working tree,
Compose revision or Docker image for you.

For the September 3, 2026 integration, the designated prior-image tag is
`bravo-local:pre-integration-20260903`; the recorded prior image ID is
`sha256:2d970046afb0b35b2c04143dec7b3f5d4d04687b005dbf35d8adccfab492d86b`.
Verify the retained tag exists and matches that record before relying on it.

For a code-only change with confirmed compatible schema and startup commands,
the maintainer can restore the retained image tag and recreate services with
`docker compose --env-file .env.appliance up --detach --no-build --force-recreate --wait`.
Do not run `bravo-appliance up` for an image-only rollback: it rebuilds from the
current source. Repeat all readiness/browser checks after recovery.

This integration changes the sync worker's startup option. An older image may
not understand `--external-maintenance`, so an image-only rollback with today's
Compose file is not automatically valid. Restore the compatible deployment
configuration deliberately and keep only one nightly orchestrator enabled.

If a migration or data transformation prevents image-only rollback, stop and use
the reviewed recovery plan. Restoring an older data bundle can remove newer
records; obtain explicit authorization rather than silently rolling patient data
back. The restore helper's replacement flag and environment equality check remain
required. Never delete the volumes or generate new encryption keys as a repair.

## Optional REDCap comparison sources

The stimulation-program and medication views reuse two reviewed Percept CSVs
through a read-only sync mount. See [source provisioning and refresh](redcap-comparisons.md#private-source-provisioning-and-refresh).
External source directories are not automatically archived by the appliance
backup; provision them on a replacement laptop before refreshing comparisons.
