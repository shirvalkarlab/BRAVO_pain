# Integration runtime and fresh installation

The integration uses Python 3.12 and `uv.lock`. Run `uv sync --frozen` at the
repository root for the portable development/test environment. The `production`
extra adds MySQL and the R bridge; it requires system MySQL headers and R.
`BRAVO/requirements.txt` is an exported compatibility file, not an independent
version authority. Regenerate it with:

```sh
uv export --frozen --extra production --no-dev --format requirements-txt --no-hashes --output-file BRAVO/requirements.txt
```

Prasad's numerical versions remain pinned: NumPy 2.1.3, SciPy 1.14.1, pandas
2.2.3, scikit-learn 1.5.2, numba 0.61.2, llvmlite 0.44.0, pyarrow 17.0.0,
pymer4 0.8.2 and rpy2 3.5.15. The image retains the source R 4.3.3 and
lme4/lmerTest/emmeans package versions and fails rather than silently upgrading
those packages. `RPY2_CFFI_MODE=ABI` avoids the source image's C-extension link
failure; actual R fitting remains a container validation gate.

Django is 5.2 LTS (locked patch 5.2.18) instead of the older source 5.1.3.
Django documents Python 3.12 support and at least three years of security updates
for this line. Its MySQL driver requirement also means upgrading mysqlclient
from the source's 2.1; the lock selects 2.3.0. The retained Fixel OpenAI 3.0
package requires a newer `idna` than Fixel's direct pin, so `idna` is resolved
transitively. Installing that library does not enable an external model API.
[Release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/) and
[database requirements](https://docs.djangoproject.com/en/5.2/ref/databases/).

Node 24 builds the frontend. The existing React Scripts project is preserved;
its production build and page tests are separate acceptance gates.

## Synthetic local checks

```sh
uv run --frozen pytest tests/runtime -q
```

These tests configure temporary SQLite databases directly and do not import
production settings or load a saved `.env`/MySQL config. They test fresh schema
creation, upgrades from both source heads, preservation of each source's fields,
repeat migration, model-state consistency, and the production settings overlay.
The overlay test substitutes the source settings module: it proves the explicit
configuration policy, not a live MySQL/HTTPS deployment. Other Django test
harnesses must run in separate pytest processes to avoid global-setting overlap.
The upstream `store`/`live` suites must not run against inherited services.

## Deployment contract

`dockerfile` has `backend` and `web` targets. Both build the frontend from the
same source and carry `BUILD_REVISION` labels. The backend uses a dedicated
Gunicorn config, without Prasad's source startup warmup or saved-answer refresh
hooks. Static collection is the only startup command before the web server.
Migration, account creation, JSON ingestion, and any future scheduled refresh
remain explicit operations. There is no automatic sync job in this deployment.

The compose project is `bravo-aditya-jetstream`. MySQL and Redis have no public
ports; Caddy is the only published service (HTTP/HTTPS). The application uses
secure cookies and requires the verified HTTPS origin. Configure an actual DNS
hostname before starting Caddy; the HTTPS certificate workflow needs reachable
ports 80/443. Public-IP-only HTTPS requires a separately validated certificate
arrangement and is not claimed to work from these templates alone.

Start from `deploy/jetstream.env.example`. It deliberately leaves required
values empty and initially binds loopback. Before public certificate issuance,
verify the DNS hostname, intended interface and host/network isolation. Then
deliberately set `BRAVO_BIND_ADDRESS` to the intended reachable host interface
(or `0.0.0.0` on an appropriately isolated host), permit inbound TCP 80/443 to
Caddy, and start the proxy. Caddy obtains the certificate only after that
reachability exists; verify TLS and normal login afterward. Do not expose
MySQL, Redis or the backend port. See `docs/operations-guide.md` for operational boundaries.
Create `.env.jetstream` privately, mode 0600, with values for:

- `BUILD_REVISION`: accepted integration commit.
- `BRAVO_DOMAIN`: verified DNS hostname without a scheme or path.
- `BRAVO_DB_DIRECTORY` and `BRAVO_DATA_DIRECTORY`: separate, empty directories
  on dedicated persistent storage; never another BRAVO's active paths.
- `BRAVO_PRIVATE_DIRECTORY`: a dedicated owner-controlled directory mounted read-only
  as `/run/bravo-private`. Its expected optional inputs are `clinical.json`,
  `device-facts/`, `power-ceilings/`, `beta-peak-models/`,
  `aditya-presentation.json`, and `calibration/`. Provision only reviewed,
  participant-bound inputs according to their module contracts. Empty/missing
  inputs remain unavailable; never populate them with guessed clinical values.
  The container UID 10001 needs read/traverse access without exposing these files
  publicly. This directory and its contents never belong in Git or image layers.
- `MYSQL_ROOT_PASSWORD`, `BRAVO_DATABASE_PASSWORD`, `DJANGO_SECRET_KEY`,
  `DATASERVER_HASHKEY`, `DATASERVER_ENCRYPTION`: new independent secrets, with
  the encryption value a valid Fernet key. Do not reuse example values.
- Optional `BRAVO_WEB_WORKERS` and `BRAVO_POOL_JOBS` (both default 4): size using actual memory/load evidence,
  not the nominal 32-core count. Numerical libraries use one thread per process.
- Optional vendor OAuth settings default to empty: `FIBIT_CLIENT_ID` and
  `FIBIT_CLIENT_SECRET` (retained upstream spelling), plus
  `GoogleHealth_CLIENT_ID`, `GoogleHealth_CLIENT_SECRET` and
  `GoogleHealth_CLIENT_REDIRECT_URI`. Missing or partial configuration disables
  connection/refresh operations without preventing application startup. Supplying
  values does not schedule sync or establish live provider acceptance.

The dedicated proxy subnet defaults to `172.29.240.0/28`, with Caddy at
`172.29.240.3`. If this overlaps a host network, choose unused
`BRAVO_PROXY_SUBNET`/`BRAVO_PROXY_IP` values together. Only that single Caddy peer
is trusted for its overwritten `X-Bravo-Client-IP` header; client-provided
forwarding headers are ignored. `BRAVO_BIND_ADDRESS` defaults to all interfaces;
the synthetic CI smoke binds loopback only.

Provision the BRAVO data directory for container UID 10001. Verify the underlying
volume identity/mount first; a folder on the root disk is not proof of attachment.
MySQL owns its separate database directory. Protect and back up the private
configuration together with database and encrypted storage after ingestion.

```sh
docker compose --env-file .env.jetstream config --quiet
docker compose --env-file .env.jetstream build
docker compose --env-file .env.jetstream up -d mysql redis
docker compose --env-file .env.jetstream run --rm app python -m django migrate --noinput
docker compose --env-file .env.jetstream run --rm app python -m django check --deploy
docker compose --env-file .env.jetstream up -d app web
```

Create the initial administrator through the application's supported account
provisioning flow, using private credentials, and validate the real login before
calling the installation ready. Source JSON mounting and ingest scheduling must
be configured only after verifying the source owner/path and one ingestion owner.
This fresh installation does not recover old users or annotations from JSONs.

## Validation status

See [release status](release-status.md) for exact source/deployment acceptance.
Local tests, clean-checkout CI and a working live installation are separate
checks. An independent installation must verify its own MySQL/R runtime,
persistence, backup/restore, HTTPS, authorized account access and representative
user journeys before being declared ready.

## Portable runtime corrections

Run upstream synthetic tests through `uv run --frozen python scripts/run_portable_tests.py`.
The runner removes inherited credentials/service addresses, creates and migrates a
temporary SQLite database, and propagates its settings to spawned subprocesses.
A two-process numerical pool bounds test resource use. Live/store markers remain
excluded by their declared external-data semantics, not by test outcomes.

Refresh orchestration reads available memory and process IDs through the already
declared psutil dependency, preserving the Linux memory ratio and process-group
termination behavior on macOS. PID 0 is explicitly excluded from termination.
Apple Accelerate does not expose its thread count through threadpoolctl; local
tests verify `VECLIB_MAXIMUM_THREADS` while Linux CI measures the BLAS limit.

The source replay pool reproduced [CPython issue 115634](https://github.com/python/cpython/issues/115634):
Python 3.12 can deadlock recycling a worker while tasks are queued. The integrated
pool now counts completed tasks per process and rotates the whole pool only
between completed chunks. No worker receives more than the source task limit,
results retain request order, and a pool generation may retire earlier than the
source implementation. This is a runtime reliability change, not a numerical rule.
Gunicorn keeps signal/exit pool cleanup without automatic scientific warmup.

An explicitly requested refresh can use `sh /app/deploy/refresh-saved-answers.sh
--participant <id>` inside the application container. It has a one-hour default
limit and is never scheduled or launched by web startup. Its source ingest-marker
path still requires deliberate coordination with any new ingestion job before
refresh and ingestion are permitted to overlap.

## Linux image acceptance gate

The `linux-container` CI job builds both image targets at the same full Git SHA,
then invokes `scripts/smoke_container_deployment.py`. It uses disposable MySQL
bind mounts, empty private configuration, generated secrets, one worker, and a
process-local Caddy CA. It checks fresh MySQL migrations/model drift, exact R
4.3.3/lme4 1.1-35.1/lmerTest 3.1-3/emmeans 1.10.0, a synthetic mixed-model fit,
Python/R imports, normal login and CSRF-protected profile POST, rejection without
CSRF, compiled-asset hashes, served revision and session persistence across an
application restart. It also makes an owner-only consistent MySQL dump, encrypted
application-data archive and private environment/config backup, verifies hashes,
restores into a separate empty MySQL schema and new storage directory, decrypts a
synthetic sentinel, and verifies both restored-session access and a new login.
The helper refuses to run outside a GitHub-hosted runner. It does not ingest source files or contact clinical APIs.
Passing this job is required evidence; defining the job does not mean it passed.
Public DNS/certificate and real Jetstream storage checks remain separate.

The image build prepares the Django-served current HTML with a CSRF input and a
`bravo-build-revision` meta tag. `/static/build-identity.json` identifies the same
revision and SHA-256 of referenced assets, so stale frontend/backend mixtures can
be detected without exposing settings or secrets. Builds without a full accepted
Git commit are refused.

Ubuntu Noble package metadata currently confirms the exact pinned system
versions: [R](https://packages.ubuntu.com/cs/noble/r-base-core),
[lme4](https://packages.ubuntu.com/noble/amd64/math/r-cran-lme4),
[lmerTest](https://packages.ubuntu.com/noble/r-cran-lmertest), and
[emmeans](https://packages.ubuntu.com/noble/amd64/r-cran-emmeans).

## Backup and restore procedure for the actual installation

The Linux smoke rehearses the following sequence on synthetic data. For the
actual installation, first verify the accepted revision, volume identity and
backup destination; put the application in a maintenance window, stop writes and
all ingestion/refresh owners, and retain the original installation intact until
the restored copy passes checks. A transactional SQL dump alone cannot guarantee
consistency with files being modified by another process.

1. Save a `mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF
   --routines --triggers --events` dump of the application database. Supply its
   password privately through the container environment; never put it in logs or
   literal command arguments. Use the matching MySQL image/client.
2. Archive encrypted application storage, private participant-bound configuration,
   and the exact private environment including Fernet/hash/Django secrets. Preserve
   ownership and permissions. Keep the backup directory mode 0700 and files 0600,
   outside the checkout; encrypt and control access to any off-host copy.
3. Record image revision/digests, database version and SHA-256 for each backup file.
   Verify those hashes before restoring. A successful dump without the original
   encryption/hash keys is not a complete backup.
4. Restore SQL into a separate empty database and extract storage into a new,
   dedicated directory. Restore the same keys/configuration and grant the restored
   application access only to that new database/storage. Never point the rehearsal
   at the original paths or overwrite the only backup.
5. At the accepted image revision, verify schema, normal login, authorized record
   access, decrypted file content/provenance and representative analyses. The CI
   rehearsal proves this flow with synthetic content; actual participant checks
   must use the authorized private validation environment.
6. Switch traffic only after those checks pass; retain the untouched source and
   backup for rollback. Any schema upgrade after restoration must receive its own
   migration/validation checkpoint.

## Test scope and optional offline snapshots

The portable runner includes ClosedLoopDeployment, StimOptimizer, CacheStore,
DecodeCommon, ControlAnalyses, Biomarkers, MedtronicPercept, SurveyForms and StimRL
synthetic suites. Pytest importlib mode avoids name collisions between upstream
namespace packages named `tests`. Declared `live`/`store` cases are excluded;
the real SurveyForms export test is explicitly `live`, even if such a private
file happens to exist locally. Core integration/authorization regressions and
Aditya API/presentation tests run in their own CI processes because their Django
settings harnesses differ. Runtime/schema tests run separately too.

The development lock includes SQLAlchemy to exercise synthetic StimRL SQLite
snapshot tests. Non-development users can opt into just the snapshot reader via
`uv sync --frozen --extra offline-snapshots` (also specify `--extra production`
when preserving a production R/MySQL environment). This extra does not enable
source exports, select a participant or launch training. The `offline-training` extra declares d3rlpy 2.8.1 and Torch 2.8.0, selecting
CPU-only wheels on Linux. Its separate CI job checks synthetic snapshot/dataset
adapters with `uv sync --frozen --extra offline-training`; it does not fit deep
models or run the tournament/AgentDB training scripts. Deep StimRL/AgentDB
training remains a separate scientific validation gate and is not claimed
validated by the portable snapshot/tabular or dataset-adapter tests. No training is
started by installing or serving this application.

The dedicated R concurrency tests are explicitly skipped in portable environments
without the production bridge. Some other upstream tests exercise the supported
`available=False` response when R is absent; passing them proves that fallback
contract, not an R fit. The Linux image smoke is the separate real R-fit gate.
