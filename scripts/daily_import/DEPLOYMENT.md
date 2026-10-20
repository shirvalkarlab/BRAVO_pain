# Daily retained-source import helpers

These helpers are a deployment package, not evidence of an enabled schedule.
The source host reads finalized existing BRAVO files through its canonical
loader. It changes only the independent application's export/checkpoint paths.
The target ingests completed batches with its normal BRAVO command and retains
verified receipts. Neither job invokes or edits the existing Dropbox job.

## Installation contract

Install `host.py`, `state.py`, `source_adapter.py`, `target_adapter.py`, and `clinic.py` under
`/opt/bravo-aditya/daily-import`, owned by root and not writable by the application.
Use the JSON examples to create private **root:root 0600** configurations at
`/etc/bravo-aditya/daily-source.json` on the source host and
`/etc/bravo-aditya/daily-target.json` on the target host. Replace all placeholders
with independently verified runtime identities; do not copy keys from the source.
The target reads its existing application environment through Compose.

Provision only these dedicated directories before running:

- Source checkpoint parent: root-owned 0700, outside the original application.
- Source batch parent: the isolated application's private NFS export tree;
  its application UID/GID must be able to traverse it. Each published batch is
  owned by the configured application UID/GID, directories 0700 and files 0600.
- Target receipts: `/data/bravo/daily-import-receipts` inside the application's
  **writable** data mount, application UID/GID 10001, mode 0700. The target
  `/run/bravo-private` mount remains read-only, including source batches.
- Existing backup/import lock and maintenance marker paths must match target
  configuration. Backups must refuse the named `bravo-aditya-source-import`
  container, including an exited container awaiting reconciliation.

Verify the target receipt directory's UID/mode and writable mount before the
first supervised import. Verify that the source baseline manifest is the exact
already-accepted initial export. The first source run reauthenticates and hashes
every baseline report before saving the initial checkpoint. It does not label
all current records as already imported.

Run one supervised source job, one target job, and repeat both to establish
idempotence before enabling timers. Execute the same entry point as the units:

```sh
sudo python3 /opt/bravo-aditya/daily-import/host.py --config /etc/bravo-aditya/daily-source.json
sudo python3 /opt/bravo-aditya/daily-import/host.py --config /etc/bravo-aditya/daily-target.json
```

The commands belong on their respective hosts. Install the matching `.service`
and `.timer` files from `systemd/`, reload systemd, then enable only the local
host's timer. The proposed source time is **23:15 UTC**, target **23:45 UTC**;
verify these follow the existing source ingestion schedule before enabling.
Timers are persistent: a missed run is attempted when the timer next starts.
A source export finishing after the target run is safely imported the following
run; the wall-clock gap is not a guarantee of same-day completion.

Status and retry use `systemctl status bravo-daily-source.service` (or target),
`systemctl list-timers`, and `journalctl -u bravo-daily-source.service` (or target).
After resolving the recorded failure, manually start the corresponding service.
A failed run emits a sanitized message. Do not echo private configuration, raw
reports, runtime environment, provider tokens, or original application logs.

## Failure and freshness contract

- New unfinished or unstable sources are deferred. A changed previously
  published source fails reconciliation; no target deletion is performed.
- Export state advances only after a complete immutable batch is durable.
  Verified batches repair a crash between publication and checkpoint update.
- The export requires free space for a bounded TAR spool and a fresh batch.
  Each container read has an internal timeout, and the Docker client's output
  file is size limited. A forced stop can leave `.pending-*` files for explicit
  operator inspection; they are never imported.
- Imports take the shared exclusive data lock and refuse active backup
  maintenance or a surviving import container. All pending batches are ingested
  together through the canonical session-ordered command.
- A target receipt requires authenticated raw identities and saved provenance
  for every alias. An interrupted decoder leaving an incomplete existing source
  fails closed and requires explicit reconciliation. Do not delete rows to
  force a retry. A completed prefix is deduplicated on a subsequent normal run.
- No per-file PSD warming is started (`BRAVO_INGEST_WARM=0`). Existing
  `DataCurator.py` otherwise starts one daemon per imported file. The canonical
  `_psd_matrix_signature_orm` in `modules/Biomarkers/bravo_service.py` includes
  recording identity/hash, patient-event metadata and applicable PRO identity;
  `_cached_psd_matrix` checks that signature and rebuilds a miss on request.
  The first visualization load can therefore be cold. A successful ingestion
  receipt is not a cache-warming or visual acceptance receipt.
- Provider data ingestion and its configuration are separate from these retained
  neural-file jobs. This package neither starts REDCap/Oura jobs nor changes
  their scientific interpretation.

The supplied tests use synthetic files and fake Docker interfaces. A passing
suite establishes the local contracts; live source permissions, NFS ownership,
real parser compatibility, schedule readback and user-facing data freshness need
separate supervised acceptance on the deployed hosts.

## Optional daily clinic workbook stage

The examples include optional `clinic` configuration. Omit it until the initial
clinic snapshot has passed supervised canonical import and module acceptance.
The source configuration supplies the exact source workbook folder, source
participant identity, snapshot directory, and the accepted initial
`clinic.manifest`. The target configuration supplies the same snapshot tree
through its existing read-only private mount and a dedicated writable
`/data/bravo/daily-clinic-receipts` directory (application UID/GID, mode0700).

With clinic configured, each existing daily service performs its neural stage
and then its clinic stage under the same host lock. Results report the two
streams separately; a clinic failure cannot create a successful clinic receipt.
Already accepted neural receipts are preserved if the later clinic stage fails.
No separate source app process, mount, credentials or Dropbox schedule is needed.

The source clinic process imports only stdlib/state/clinic helper code. It reads
regular workbook bytes twice, excludes `_Template_` workbooks exactly as the
canonical parser does, and publishes a complete stable folder snapshot.
Changed or added workbooks produce a new immutable snapshot. Missing previously
accepted filenames fail reconciliation; unstable inventories defer the whole
clinic stage. Filename hashes and size bounds are checked again during transfer.
Snapshots are bounded to 256 files, 32 MiB per workbook and 256 MiB total.

`CURRENT` is an atomic hard link to the selected snapshot's app-owned immutable
manifest. Readers derive the snapshot directory from that manifest's SHA256;
there is no partially rewritten workbook directory. Earlier snapshots remain
available. Only the source host changes `CURRENT`, after complete publication.

The target uses normal `ingest_clinic_sheets` and exact canonical DataFrame
readback (no numeric tolerance), including all unrated exposures. It checks the
newest saved product matches this signature and a repeated ingest writes
nothing. It repeats this validation even if a prior receipt exists, so a
cleared target product is rebuilt. A rollback to an old previously stored
signature that the canonical newest-product policy does not select fails
visibly; it does not silently replace that policy or report stale data current.

The main Aditya/Biomarkers, StimOptimizer and ClosedLoop consumers use the
canonical clinic-pain store; the private `CURRENT` pointer selects the importer
input. Those consumers read the newly verified product. Provider jobs remain separate; this stage does
not fetch REDCap/Oura or change missing-value/scoring rules.


## Optional target provider stage

The target example leaves both provider flags false. Enable `providers.redcap_enabled` or
`providers.oura_enabled` only after the corresponding private configuration and collection
scope have been accepted. Flags must be actual JSON booleans; no configured provider
block means no provider stage. Provision `providers.receipts` as an application-owned
mode0700 directory before running. No credentials belong in the daily-job configuration.

The provider stage runs after the existing neural/clinic imports in the same accepted
container and host data lock. REDCap reuses the canonical participant-bound fresh fetch,
processing, UTC normalization and provenance snapshot, then imports the exact metrics
into a participant-specific native survey form. It refuses an empty export or changed
field schema, verifies exact stored dates/results and a no-op repeat inside one database
transaction. Provider refresh-pass caches are refused to avoid calling a retained export
a fresh fetch. Existing native form fingerprints round timestamps; this stage additionally
compares exact timestamps before deciding whether the native no-op is safe.

Oura requires exactly one existing device explicitly configured for managed tokens; it
never creates authorization or a device. Native refresh enforces the provider account pin
and only replaces its previous snapshot after complete authenticated durable publication.

Each enabled provider writes a separate private success/failure receipt with aggregate
counts only. One provider failure does not prevent the other provider attempt, but the
overall daily job fails after both receipts are written. Review failed receipts and fix
the underlying condition; missing reports are never fabricated. Configuration installation
is distinct from activation and from actual data acceptance.
