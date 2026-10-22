# Manual and direct-source synchronization deployment

This package is dormant until installed and supervised. The authenticated Admin
button submits one fixed participant-bound request; it never supplies commands,
paths, credentials, or selectable stages. See `deploy/manual-sync-app.md` for the
API's session/CSRF and role checks. The source and target workers use the same
pipeline and exclusive locks as daily jobs. Neither invokes or changes the
original Prasad ingestion scripts, schedule, database, or incoming directory.

## Fixed mailbox and worker installation

Install the reviewed `ManualSyncProtocol.py` from `BRAVO/modules` alongside
`manual_sync.py`, `host.py`, all existing helpers, and the reviewed
`upstream_source.py`, `upstream_dropbox.py`, `upstream_clinic.py`, and
`upstream_target.py` in `/opt/bravo-aditya/daily-import`, root owned and not
application writable. Hash-check every installed file against the reviewed
candidate. Keep root host configurations mode0600.

The app's `BRAVO_MANUAL_SYNC_CONFIG_FILE` points to
`/run/bravo-private/manual-sync/app-config.json`. Its exact JSON fields are:

- `request_directory`: `/data/bravo/manual-sync/request` (app writable).
- `status_directory`: `/run/bravo-private/manual-sync/status` (app read-only).
- `target_participant_uid`, `target_institute_uid`: the fixed accepted binding.
- `owner_uid`: 10001; `source_mode`: `upstream_files`;
  `upstream_available`: true only after the direct-source access checks pass.

Both directories are application UID/GID10001, mode0700; files are0600.
Host workers use the corresponding paths in the same shared NFS export, while
the app retains its existing writable data and read-only private mounts. Verify
these actual Docker mount flags: filesystem ownership alone does not make status
read-only to the app. On the target's root-squashed NFS mount, provision and check
app-owned directories under effective UID/GID10001, then restore root.

Use `manual-worker.example.json` for each host. The target version changes role,
hostname, host_config to `daily-target.json`, and its root-local ledger/worker
lock to `manual-target.json`/`bravo-aditya-manual-target.lock`. All mailbox
identities match the app. Ledger parents are root owned; workers read only the
installed host configurations. The worker verifies the role, host, target
binding and selected source mode before acting.

Install the local `bravo-manual-source` or `bravo-manual-target` service/timer,
reload systemd, and **leave timers disabled** during acceptance. The 30-second
timer checks one fixed mailbox and cannot create jobs by itself. Only one
request is active at a time; source failure still waits for target provider
completion. The root ledger prevents repeat execution after publication failure;
interrupted jobs become failed for operator reconciliation. Retries require a
new authenticated request after the prior job reaches a terminal state.

## Direct-source configuration

Keep the original retained-source configuration fields as recovery evidence.
Adding `upstream` to source host configuration chooses the independent source
pipeline. Its fields are `owner_uid`, `status_path`, `dropbox`, and `clinic`.
`status_path` is a dedicated app-readable private file, for example
`/SHARED_PRIVATE/upstream/latest-attempt.json`, outside original job paths.

The `dropbox` section contains `scope`, exact approved `remote`, absolute
`rclone_binary`, original read-only `rclone_config`, isolated `batches`, isolated
root-private `checkpoint`, and `owner_uid`. Pin these in the private installer;
never allow request payloads to override them. The fetch copies only the existing
Dropbox config section to a temporary private config and verifies the original
is unchanged. It lists the same scoped folder before and after download,
verifies provider content hashes, and publishes immutable raw-SHA batches.

The `clinic` section contains the pinned source container/workdir/client hash,
exact approved `folder_id`, original `source_participant_uid`, separate upstream
`snapshots`, accepted `baseline_manifest`, private `baseline_provenance`, separate
`provenance_directory`, and `owner_uid`. Readonly container code exports only
eligible workbooks in that folder. Stable provider IDs avoid renamed duplicates;
unchanged metadata reuses verified bytes. Accepted historical files missing from
the folder remain active input with explicit retained-not-fresh provenance.
No outside-folder download follows a moved file.

The target configuration adds `upstream` with the same `scope`, read-only
`batches`, writable `receipts`, and the exact accepted `approved_device_serials`.

An optional root-owned private `upstream.masked_device_binding` supports new
serial-masked reports from one explicitly reviewed stream and existing implant.
It contains exactly `policy` (`masked-native-continuity-v1`), `scope`,
`participant_uid`, `institute_uid`, `device_uid`, `seed_source_uid` and
`seed_raw_sha256`. The owner, institute and scope must equal the fixed target;
the seed names an authenticated, previously accepted original report. It never
adds a masked token to `approved_device_serials` or recovers a serial number.

Every new report must have matching wholly block-masked Initial/Final serials,
a unique native owner/type/exact-lead match to that existing device, an advancing
session in the same native clock block, and complete bilateral chronic and
spectral continuity with the latest trusted read. All overlapping measurements
and explicit contact claims must agree. A changed or omitted contact claim
relative to the reference cannot supply a witness. Identical contact-free
spectra can establish numerical continuity without establishing contact identity.
Canonical conversion must preserve every common native
measurement timestamp. Unknown clocks, conflicting measurements, changed
provider objects, ambiguous devices, absent meaningful overlap and new clock
blocks remain withheld. Existing array/contact preservation rules still apply.

`MaskedDeviceAdmission` records the exact source/reference raw identities,
private binding digest, native proof and clock proof. Only descendants whose
validated, domain-separated HMAC-signed receipts chain to the reviewed seed may become rolling references;
an arbitrary later masked source cannot. This lets verified imports advance
without creating permission for unrelated or unverifiable reports. The chart
refreshes from committed verified imports and continues to report uncertainty.

Hosted daily and manual runners embed installed sibling helper files into their
isolated target process. Updating an application image alone does not update
this policy: release `host.py`, `upstream_target.py`, `masked_identity.py` and
`native_continuity.py` together with the exact reviewed private binding, under
the existing maintenance/import lock and with a reversible hash-checked backup.
Preserve all unchanged helper files, services and source jobs.
It also sets `upstream_source_status` to the source status file through the
private mount, and directs `clinic.snapshots` to the separate upstream clinic
tree. Existing target identity, database, runtime revision, provider settings,
data lock, and maintenance marker remain authoritative. Provision the dedicated
upstream receipts under the existing writable data mount as UID10001/mode0700.

## Success, failure, and freshness

Source neural and clinic fetches run independently. Both are attempted before a
daily source service fails for any incomplete stream. Failed snapshots never
replace prior published data. Target neural, clinic, REDCap and Oura stages are
independent: failed/unavailable source data blocks only its corresponding
neural/clinic stage; providers are still attempted under the same data lock.
Unknown neural devices or a previously accepted provider file changing raw
content are withheld and produce explicit failed stream status, never silent
success. Existing Prasad source identities remain preserved provenance.

Manual target availability requires the matching request's source stream to
have exported successfully **and** a valid completed source receipt no older
than24 hours. The UI's per-stream success time records completed target work;
the overall success time changes only when all four stages succeed. Exported
source data alone is not imported success. The UI labels this *manual* sync
history; daily jobs do not rewrite that mailbox history.

Daily target availability uses the last valid successful source receipt within
24 hours. It is not an attestation that the immediately preceding scheduled
source attempt ran: if the source cannot even publish its initial running
receipt, its service fails while the previous receipt remains. A target can
then import that previously verified fetch within its age window. Check the
source service result and receipt timestamps to establish upstream freshness;
a successful target import alone proves neither a fresh cloud fetch nor that
all scheduled source work succeeded. Malformed, unfinished or older receipts
block affected source stages, with no automatic retained-file fallback.

## Supervised acceptance and operation

Before enabling timers, verify source original script hashes, cron content,
container identities/start times and mounts before/after the run. Verify source
config, binary, credentials and exact folder read permissions without printing
secrets. Verify sufficient isolated-volume space, all published hashes, target
NFS ownership, approved device bindings, canonical neural/clinic receipts and
actual rendered module data. Repeat the source and target jobs to verify
idempotence. Exercise a real Admin request, observe all four stream outcomes,
and confirm a second click coalesces while running. Verify failed-stream retry,
provider independence and maintenance deferral with synthetic tests, never by
breaking production credentials.

After acceptance, enable only each host's reviewed daily/manual timers.
`systemctl status bravo-manual-source.service` (or target), timer listings,
root-private ledgers and sanitized statuses provide operational evidence.
Manual execution uses `python3 /opt/bravo-aditya/daily-import/manual_sync.py
--config /etc/bravo-aditya/manual-source.json` (or target) as root on the
appropriate host. Do not delete receipts, ledgers, source rows, or a surviving
import container to force progress; reconcile interrupted writes explicitly.
