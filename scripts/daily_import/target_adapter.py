"""Normal BRAVO ingestion adapter with authenticated all-alias acceptance.

Host wrapper supplies the shared backup/import lock and maintenance checks. No
receipt is published on an incomplete decode or unauthenticated destination.
"""
import argparse
import contextlib
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import stat
import tempfile

try:
    from . import state
    from .source_adapter import bounded_load
except ImportError:  # direct script in the target application container
    import state
    from source_adapter import bounded_load


class IncompleteSource(ValueError):
    """A prior decoder was interrupted; retained batch requires reconciliation."""


def verify_chronic_restamp(row, rule_version, configuration_digest, inventory_digest=None):
    """A raw round trip alone cannot certify the derived chronic schedule."""
    metadata = getattr(row, 'metadata', None)
    receipt = metadata.get('ChronicScheduleRestamp') if isinstance(metadata, dict) else None
    if (not isinstance(receipt, dict) or receipt.get('status') != 'complete'
            or type(receipt.get('exports_without_record')) is not int
            or receipt['exports_without_record'] != 0 or 'failed' in receipt
            or receipt.get('rule_version') != rule_version
            or receipt.get('configuration_digest') != configuration_digest
            or not isinstance(receipt.get('inventory_digest'), str)
            or len(receipt['inventory_digest']) != 64
            or any(c not in '0123456789abcdef' for c in receipt['inventory_digest'])
            or (inventory_digest is not None and receipt['inventory_digest'] != inventory_digest)):
        raise IncompleteSource('chronic schedule incomplete; verified preparation required')


def merge_provenance(previous, source, entries):
    aliases = {state.uid(entry['source_uid']) for entry in entries}
    raw_sha = state.digest(entries[0]['sha256'])
    if previous:
        if previous.get('participant_uid') != source or previous.get('raw_sha256') != raw_sha:
            raise ValueError('previous migration provenance conflicts')
        prior = previous.get('source_uids', [previous.get('source_uid')])
        if not isinstance(prior, list) or not prior:
            raise ValueError('previous migration aliases invalid')
        aliases.update(state.uid(value) for value in prior)
    ordered = sorted(aliases)
    return {'participant_uid': source, 'source_uid': ordered[0],
            'source_uids': ordered, 'raw_sha256': raw_sha}


def group_sources(root, manifest, key):
    groups = {}
    for entry in manifest['files']:
        raw = state.read_bounded(Path(root) / entry['path'], state.MAX_FILE)
        state.verified_raw(raw, entry)
        digest = hmac.new(key, raw, hashlib.sha256).hexdigest()
        group = groups.setdefault(digest, [])
        if group and (entry['sha256'], entry['bytes']) != (group[0]['sha256'], group[0]['bytes']):
            raise ValueError('inconsistent raw identity')
        group.append(entry)
    for entries in groups.values():
        entries.sort(key=lambda entry: entry['source_uid'])
    return groups


class TargetRuntime:
    def __init__(self, models, loader, call_command, atomic, person, raw_root):
        self.models, self.loader, self.command, self.atomic = models, loader, call_command, atomic
        self.person, self.raw_root = person, Path(raw_root)
        self._schedule_checks = {}
        self._schedule_seeds = set()

    def existing(self, digest):
        matches = self.models.SourceFile.objects.filter(unique_hashed=digest, institute=str(self.person.institute_id))
        if matches.exclude(owner_id=self.person.uid).exists() or matches.count() > 1:
            raise ValueError('source digest maps to another or ambiguous participant')
        return matches.first()

    def verify(self, row, entry):
        expected = self.raw_root / self.person.uid / (str(row.uid) + '.json')
        if row.type != 'MedtronicJSON' or Path(row.pointer) != expected:
            raise IncompleteSource('target source incomplete; explicit reconciliation required')
        # Checks every path component and stored-size bound before loader access.
        state.file_identity(expected)
        raw = bounded_load(row, self.loader)
        state.verified_raw(raw, entry)
        from modules.MedtronicPercept.chronic_schedule import RULE_VERSION
        from modules.DecodeCommon.private_clinical_config import config_digest
        verify_chronic_restamp(row, RULE_VERSION, config_digest(), self.schedule_inventory_digest(row))

    def schedule_inventory_digest(self, row, fresh=False):
        from modules import DataCurator
        from modules.MedtronicPercept import chronic_schedule
        from modules.DecodeCommon.private_clinical_config import config_digest
        seed = str(row.device)
        self._schedule_seeds.add(seed)
        config = config_digest()
        key = (seed, config)
        if not fresh and key in self._schedule_checks:
            return self._schedule_checks[key]
        uids = DataCurator.implant_device_uids(seed, owner_only=self.person.uid)
        if not uids:
            raise IncompleteSource('chronic schedule has no owner-bound device inventory')
        query = self.models.SourceFile.objects.filter(owner_id=self.person.uid, device__in=uids, type='MedtronicJSON')
        if fresh:
            query = query.select_for_update()
        rows = list(query)
        if not rows:
            raise IncompleteSource('chronic schedule source inventory is empty')
        inventory = []
        for source in rows:
            settings = (source.metadata or {}).get('SensingSettingsRecord')
            chronic_schedule.validate_settings_record(settings)
            inventory.append((str(source.uid), str(source.hashed), settings))
        digest = hashlib.sha256(json.dumps(sorted(inventory), sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        # Validate every source in the group, not merely this batch's duplicate.
        for source in rows:
            verify_chronic_restamp(source, chronic_schedule.RULE_VERSION, config, digest)
        if config_digest() != config:
            raise IncompleteSource('private implant configuration changed during verification')
        for uid in uids:
            self._schedule_checks[(str(uid), config)] = digest
        return digest

    def verify_final_schedules(self):
        # The outer host lock excludes other imports. Row locks make the final
        # receipt describe one complete accepted inventory, including retained rows.
        with self.atomic():
            for seed in sorted(self._schedule_seeds):
                self.schedule_inventory_digest(type('Seed', (), {'device': seed})(), fresh=True)


    def ingest(self, root, groups):
        # Canonical command sorts by SessionDate internally. One representative
        # per digest avoids its classify-before-write duplicate-batch limitation.
        with tempfile.TemporaryDirectory(prefix='bravo-daily-ingest-') as directory:
            for entries in groups.values():
                entry = entries[0]
                (Path(directory) / (entry['source_uid'] + '.json')).symlink_to((Path(entry.get('_root', root)) / entry['path']).resolve())
            self.command('ingest_percept_folder', participant=self.person.uid, folder=directory, dry_run=False)
        self._schedule_checks.clear()

    def save_provenance(self, updates):
        with self.atomic():
            for row, provenance in updates:
                row.metadata = {**(row.metadata or {}), 'MigrationSource': provenance}
                row.save(update_fields=['metadata'])


def apply_batches(roots, source, target, revision, key, runtime):
    """Ingest all pending batches in ONE canonical session-ordered command.

    Only small manifests/provenance are accumulated; raw reports are read one at
    a time and the temporary command input is a symlink view. No receipt becomes
    eligible until every pending payload and saved alias has been verified.
    """
    if runtime.person.uid != target:
        raise ValueError('runtime participant mismatch')
    batches, groups, aliases = [], {}, {}
    for root in roots:
        manifest = state.validate_batch(root, source)
        state.import_receipt(manifest, source, target,
            {e['source_uid']: e['sha256'] for e in manifest['files']}, revision)
        batches.append((Path(root), manifest))
        for digest, entries in group_sources(root, manifest, key).items():
            for entry in entries:
                identity = (entry['sha256'], manifest['fingerprints'][entry['source_uid']])
                previous = aliases.setdefault(entry['source_uid'], identity)
                if previous != identity:
                    raise ValueError('source alias conflicts across pending batches')
                group = groups.setdefault(digest, [])
                if group and (group[0]['sha256'], group[0]['bytes']) != (entry['sha256'], entry['bytes']):
                    raise ValueError('raw identity conflicts across pending batches')
                group.append({**entry, '_root': str(root)})
    if not batches:
        return []
    for digest, entries in groups.items():
        existing = runtime.existing(digest)
        if existing is not None:
            runtime.verify(existing, entries[0])
            merge_provenance((existing.metadata or {}).get('MigrationSource'), source, entries)
    runtime.ingest(None, groups)
    updates, verified, accepted_provenance = [], {}, {}
    for digest, entries in groups.items():
        row = runtime.existing(digest)
        if row is None:
            raise ValueError('ingestion did not create every source')
        runtime.verify(row, entries[0])
        provenance = merge_provenance((row.metadata or {}).get('MigrationSource'), source, entries)
        updates.append((row, provenance))
        accepted_provenance[digest] = provenance
    runtime.save_provenance(updates)
    # Requery rather than trusting save() completion or the in-memory object.
    for digest, entries in groups.items():
        row = runtime.existing(digest)
        if (row.metadata or {}).get('MigrationSource') != accepted_provenance[digest]:
            raise ValueError('provenance readback mismatch')
        verified.update({entry['source_uid']: entry['sha256'] for entry in entries})
    if isinstance(runtime, TargetRuntime):
        runtime.verify_final_schedules()
    return [(root, state.import_receipt(manifest, source, target,
        {e['source_uid']: verified[e['source_uid']] for e in manifest['files']}, revision))
        for root, manifest in batches]


def apply_batch(root, source, target, revision, key, runtime):
    return apply_batches([root], source, target, revision, key, runtime)[0][1]


def verify_receipt_directory(directory):
    """Prove durable receipt writes on the actual mount before ingestion."""
    directory = state.safe_path(directory)
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
        raise ValueError('receipt directory must be private and owned by runtime user')
    descriptor, temporary = tempfile.mkstemp(prefix='.receipt-probe-', dir=directory)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(b'receipt durability probe\n')
            stream.flush()
            os.fsync(stream.fileno())
        state.sync_directory(directory)
    finally:
        os.unlink(temporary)
        state.sync_directory(directory)


def run(config, runtime, key, revision):
    source, target = state.uid(config['source_participant_uid']), state.uid(config['target_participant_uid'])
    if revision != config['runtime_revision']:
        raise ValueError('runtime revision mismatch')
    verify_receipt_directory(config['receipts'])
    pending, skipped = [], 0
    for path in sorted(Path(config['batches']).iterdir()):
        if path.name.startswith('.pending-'):
            continue
        state.digest(path.name)
        manifest = state.validate_batch(path, source)
        if path.name != state.sha(state.encoded(manifest)):
            raise ValueError('batch directory identity mismatch')
        receipt_path = Path(config['receipts']) / (path.name + '.json')
        if receipt_path.exists():
            receipt = json.loads(state.read_bounded(receipt_path, 16 * 1024 * 1024))
            state.receipt_matches(receipt, manifest, source, target)
            skipped += 1
            continue
        pending.append(path)
    receipts = apply_batches(pending, source, target, revision, key, runtime)
    for path, receipt in receipts:
        state.atomic_json(Path(config['receipts']) / (path.name + '.json'), receipt)
    return {'applied_batches': len(receipts), 'already_applied_batches': skipped}


def execute(config):
    """Run from an injected in-memory private configuration; no config mount needed."""
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BRAVO.settings')
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.db import transaction
        from Server import models
        from modules import DataCurator
        database = settings.DATABASES['default']
        if (database['NAME'], database['USER']) != (config['database_name'], config['database_user']):
            raise ValueError('target database mismatch')
        person = models.Participant.objects.get(uid=state.uid(config['target_participant_uid']),
            institute_id=state.uid(config['target_institute_uid']), name=config['participant_name'])
        root = Path(os.environ['DATASERVER_PATH']) / 'raws'
        if root != Path(config['raw_root']):
            raise ValueError('target root mismatch')
        runtime = TargetRuntime(models, DataCurator.loadCacheFile, call_command, transaction.atomic, person, root)
        result = run(config, runtime, os.environ['DATASERVER_HASHKEY'].encode(), os.environ['BRAVO_BUILD_REVISION'])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(state.read_bounded(args.config, 65536))
    print(json.dumps(execute(config), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except IncompleteSource:
        sys.stderr.write('Daily target import blocked: incomplete-source; batch retained for reconciliation.\n')
        sys.exit(2)
    except Exception:
        sys.stderr.write('Daily target import failed; no receipt accepts an incomplete batch.\n')
        sys.exit(1)
