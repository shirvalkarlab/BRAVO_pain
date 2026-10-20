# Operating an independent BRAVO installation

Use the [lab user guide](user-guide.md) for navigation and [release status](release-status.md)
for the shared site's accepted version. This public repository contains code and
synthetic tests, not an installation backup or working provider credentials.

## Shared viewer operation

The shared read-only account is configured by the administrator, with its password
distributed privately. Keep the server-owned `SharedReadOnly` flag and Viewer
membership; never grant Admin to reveal a blocked control. Individual authorized
accounts retain their existing editing and import permissions.

Viewers can use **Refresh view** to read saved updates. **Sync all streams** remains
administrator-only, and normal daily jobs remain responsible for scheduled imports.
Canonical analytical readers may populate derived caches and make their existing
read-only provider requests. Read-only does not imply that sessions, caches or
access logs never change.

The deployed release passed a bounded check with 20 independent sessions and 40
concurrent lightweight reads, with no failed requests and isolated logout. A
separate check of twenty concurrent full-chart reads (ten REDCap and ten Oura) also
succeeded; the slowest response took about a minute. Full charts are not instant
under load, and this is not a guarantee for twenty fresh heavy computations. Monitor actual demand
before changing workers or resource limits. Rotate shared credentials privately
when withdrawing access; keep them out of repositories, issues and public receipts.
See the [shared viewer guide](shared-viewer.md) and [release status](release-status.md).

## Storage and configuration

Use separate database, cache and file locations for each installation. Never point
a development checkout at the shared site's writable storage. Keep database ports
and Redis private; only the HTTPS proxy should be public. The provided
`docker-compose.yml` and `deploy/jetstream.env.example` are templates, not active
configuration. Do not use the historical Docker image instructions as the shared
site's configuration.

Supply encryption/hash keys, database credentials, provider tokens and clinical
configuration privately. Preserve original keys with restored encrypted data.
Validate actual mount ownership, free space, TLS, normal login and application
revision before declaring a deployment ready. See [runtime](runtime-and-deployment.md)
and [clinical configuration](private-clinical-configuration.md).

## Data flows and freshness

Neural files and clinic workbooks are validated source inputs. REDCap and Oura use
separately authorized provider access and participant bindings. The daily and
manual pipelines publish receipts; their exact service configuration and schedule
are private deployment state. A copied source file is not a successful import.
Failures and identity withholding must remain visible; never guess device identity
or silently assign data to a participant.

Manual synchronization uses an idempotent coordinated job with separate per-stream
status. Source and target workers must share the expected private mailbox and
locking contract. Read [daily deployment](../scripts/daily_import/DEPLOYMENT.md),
[manual sync](../scripts/daily_import/MANUAL_SYNC.md) and
[application integration](../deploy/manual-sync-app.md) before enabling these jobs.
Do not change another installation's source-copy job to operate this one.

A failed provider or source refresh does not erase previously accepted data. It
also does not establish fresh coverage. Keep recording date, import date and
application deployment date distinct. Check the latest attempt and latest success,
not merely a historical green receipt.

## Release and recovery

1. Review a coherent code-only candidate, synthetic tests and exact-candidate CI.
2. Keep a verified backup and the previous images/configuration for rollback.
3. Verify source/image identities and available storage before building.
4. Quiesce owned jobs using the deployment's locks and maintenance contract;
   preserve pending requests and unrelated services.
5. Apply the reviewed release, then check HTTPS, normal account access, exact
   backend/frontend identity, representative APIs and the affected user journeys.
6. Resume only previously active jobs after acceptance and verify their status.

Do not perform production-writing tests or provider fetches just to generate a
release receipt. A restored isolated database is the proper place for migrations
and destructive rehearsal. Use actual evidence for acceptance; a successful
build alone does not establish live readiness.

The public snapshot deliberately omits installation-specific anatomy overrides,
private clinical evidence and historical operational measurements. Reintroducing
such inputs requires an authenticated, reviewed configuration path; do not encode
a participant-to-anatomy or safety-limit lookup in public source.
