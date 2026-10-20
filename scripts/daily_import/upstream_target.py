"""Fixed-scope direct Dropbox Percept import; separate from retained-source UIDs.

Host wrappers own fetch credentials, shared data lock, maintenance checks and
immutable publication. Incoming JSON never chooses a participant or device.
"""
import contextlib
from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile

try:
    from . import state, target_adapter
except ImportError:
    import state
    import target_adapter

KIND = 'bravo-upstream-percept'


def text(value, maximum=512):
    if not isinstance(value, str) or not 0 < len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise ValueError('invalid upstream identity')
    return value


def file_identity(entry):
    return {key: entry[key] for key in ('provider_id', 'revision', 'provider_modified_at', 'sha256')}


def validate_batch(directory, scope, verify_payloads=True):
    directory = state.safe_path(directory)
    payload = state.read_bounded(directory / 'upstream.manifest', 16 * 1024 * 1024)
    manifest = json.loads(payload)
    digest = state.sha(payload)
    if payload != state.encoded(manifest) or directory.name != digest or state.read_bounded(directory / 'COMPLETE', 128).decode().strip() != digest:
        raise ValueError('upstream publication identity mismatch')
    if set(manifest) != {'format', 'kind', 'provider', 'scope', 'count', 'total_bytes', 'files'} or manifest['format'] != 1 or manifest['kind'] != KIND or manifest['provider'] != 'dropbox' or manifest['scope'] != text(scope):
        raise ValueError('upstream scope mismatch')
    entries = manifest['files']
    if not isinstance(entries, list) or not 0 < len(entries) <= state.MAX_FILES:
        raise ValueError('upstream manifest count invalid')
    identities, paths, total = set(), set(), 0
    for entry in entries:
        if set(entry) != {'provider_id', 'revision', 'provider_modified_at', 'path', 'sha256', 'bytes'}:
            raise ValueError('upstream entry schema mismatch')
        identity = text(entry['provider_id'])
        if identity in identities:
            raise ValueError('repeated upstream provider identity')
        identities.add(identity)
        if entry['revision'] is not None:
            text(entry['revision'], 256)
        stamp = datetime.fromisoformat(text(entry['provider_modified_at']).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('upstream modification timezone missing')
        digest = state.digest(entry['sha256'])
        if entry['path'] != 'sources/' + digest + '.json' or type(entry['bytes']) is not int or not 0 < entry['bytes'] <= state.MAX_FILE:
            raise ValueError('upstream payload bounds invalid')
        if verify_payloads:
            state.verified_raw(state.read_bounded(directory / entry['path'], state.MAX_FILE), entry)
        paths.add(entry['path'])
        total += entry['bytes']
    if type(manifest['count']) is not int or manifest['count'] != len(entries) or type(manifest['total_bytes']) is not int or manifest['total_bytes'] != total or total > state.MAX_TOTAL:
        raise ValueError('upstream total bounds mismatch')
    if {str(path.relative_to(directory)) for path in (directory / 'sources').iterdir()} != paths:
        raise ValueError('unexpected upstream payload')
    return manifest


def merge_provenance(previous, scope, digest, entries):
    files = {}
    if previous:
        if set(previous) != {'provider', 'scope', 'raw_sha256', 'files'} or previous['provider'] != 'dropbox' or previous['scope'] != scope or previous['raw_sha256'] != digest:
            raise ValueError('upstream provenance conflicts')
        for entry in previous['files']:
            if set(entry) != {'provider_id', 'revision', 'provider_modified_at', 'sha256'} or entry['sha256'] != digest:
                raise ValueError('upstream prior file identity invalid')
            files[state.sha(state.encoded(entry))] = entry
    for entry in entries:
        identity = file_identity(entry)
        files[state.sha(state.encoded(identity))] = identity
    return {'provider': 'dropbox', 'scope': scope, 'raw_sha256': digest,
            'files': [files[key] for key in sorted(files)]}


class Runtime(target_adapter.TargetRuntime):
    def device_binding(self, approved):
        found = set()
        for device in self.models.DBSDevice.objects.filter(serial_number__in=approved):
            if str(device.owner_id) != self.person.uid:
                raise ValueError('approved device belongs to another participant')
            found.add(device.serial_number)
        if found != set(approved):
            raise ValueError('approved device binding unavailable')

    def source_index(self):
        result = {}
        for row in self.models.SourceFile.objects.filter(owner_id=self.person.uid, type='MedtronicJSON'):
            for namespace in ('MigrationSource', 'UpstreamSource'):
                provenance = (row.metadata or {}).get(namespace)
                if provenance:
                    digest = state.digest(provenance['raw_sha256'])
                    if digest in result and result[digest].uid != row.uid:
                        raise ValueError('raw SHA maps to multiple target sources')
                    result[digest] = row
        return result

    def ingest_upstream(self, groups):
        with tempfile.TemporaryDirectory(prefix='bravo-upstream-ingest-') as directory:
            for digest, group in groups.items():
                entry = group['entries'][0]
                (Path(directory) / (digest + '.json')).symlink_to(group['root'] / entry['path'])
            self.command('ingest_percept_folder', participant=self.person.uid, folder=directory, dry_run=False)
        self._schedule_checks.clear()

    def save_upstream(self, updates):
        with self.atomic():
            for row, provenance in updates:
                row.metadata = {**(row.metadata or {}), 'UpstreamSource': provenance}
                row.save(update_fields=['metadata'])


def receipt(manifest, target, revision, accepted, withheld, restorations=None):
    result = {'format': 1, 'kind': KIND + '-receipt', 'manifest_sha256': state.sha(state.encoded(manifest)),
        'target_participant_uid': target, 'runtime_revision': revision, 'accepted': accepted, 'withheld': withheld}
    if restorations:
        result['serial_restorations'] = restorations
    return result


def provider_bindings(index, scope):
    bindings = {}
    for row in index.values():
        prior = (row.metadata or {}).get('UpstreamSource')
        if not prior or prior['scope'] != scope:
            continue
        for entry in prior['files']:
            if entry['sha256'] != prior['raw_sha256']:
                raise ValueError('existing provider digest conflicts')
            bindings.setdefault(text(entry['provider_id']), set()).add(state.digest(entry['sha256']))
    return bindings



def restoration_approvals(upstream):
    records = upstream.get('serial_restorations', [])
    if not isinstance(records, list) or len(records) > 32:
        raise ValueError('serial restoration approvals invalid')
    result = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {'provider_id', 'old_sha256', 'new_sha256', 'target_source_uid', 'old_batch_sha256'}:
            raise ValueError('serial restoration approval schema invalid')
        provider = text(record['provider_id'])
        for field in ('old_sha256', 'new_sha256', 'old_batch_sha256'):
            state.digest(record[field])
        state.uid(record['target_source_uid'])
        if provider in result or record['old_sha256'] == record['new_sha256']:
            raise ValueError('serial restoration approval conflicts')
        result[provider] = record
    return result


def strict_report(raw):
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise ValueError('ambiguous serial restoration JSON')
            result[name] = value
        return result
    def constant(value):
        raise ValueError('nonfinite serial restoration JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def canonical_digest(value):
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True, separators=(',', ':'), allow_nan=False).iterencode(value):
        digest.update(chunk.encode())
    return digest.hexdigest()


def verify_restoration(root, entry, record, upstream, runtime, index, key, approved):
    old_root = state.safe_path(Path(upstream['batches']) / record['old_batch_sha256'])
    manifest = validate_batch(old_root, upstream['scope'], verify_payloads=False)
    candidates = [item for item in manifest['files'] if item['provider_id'] == record['provider_id'] and item['sha256'] == record['old_sha256']]
    if len(candidates) != 1 or entry['sha256'] != record['new_sha256']:
        raise ValueError('serial restoration retained identity mismatch')
    old_entry = candidates[0]
    old_raw = state.read_bounded(old_root / old_entry['path'], state.MAX_FILE)
    state.verified_raw(old_raw, old_entry)
    row = runtime.existing(hmac.new(key, old_raw, hashlib.sha256).hexdigest())
    indexed = index.get(record['old_sha256'])
    if row is None or indexed is None or row.uid != indexed.uid or row.uid != record['target_source_uid']:
        raise ValueError('serial restoration target binding mismatch')
    prior = (row.metadata or {}).get('UpstreamSource')
    if not prior or prior['scope'] != upstream['scope'] or prior['raw_sha256'] != record['old_sha256'] or not any(item['provider_id'] == record['provider_id'] and item['sha256'] == record['old_sha256'] for item in prior['files']):
        raise ValueError('serial restoration prior provider binding unavailable')
    runtime.verify(row, old_entry)
    new_raw = state.read_bounded(root / entry['path'], state.MAX_FILE)
    state.verified_raw(new_raw, entry)
    old, new = strict_report(old_raw), strict_report(new_raw)
    del old_raw, new_raw
    serials = []
    for phase in ('Initial', 'Final'):
        try:
            before, after = old['DeviceInformation'][phase], new['DeviceInformation'][phase]
            old_serial, new_serial = before['NeurostimulatorSerialNumber'], after['NeurostimulatorSerialNumber']
        except (KeyError, TypeError):
            raise ValueError('serial restoration fields unavailable') from None
        if not isinstance(old_serial, str) or not old_serial or not all(0x2580 <= ord(c) <= 0x259f for c in old_serial) or not isinstance(new_serial, str) or new_serial not in approved or any(0x2580 <= ord(c) <= 0x259f for c in new_serial):
            raise ValueError('serial restoration device transition invalid')
        serials.append(new_serial)
        del before['NeurostimulatorSerialNumber'], after['NeurostimulatorSerialNumber']
    if serials[0] != serials[1] or canonical_digest(old) != canonical_digest(new):
        raise ValueError('serial restoration changes other report content')
    return {**record, 'new_file': file_identity(entry)}


def validate_runtime(config, runtime, revision):
    target = state.uid(config['target_participant_uid'])
    upstream = config['upstream']
    approved = upstream['approved_device_serials']
    if not isinstance(approved, list) or not approved or len(set(approved)) != len(approved):
        raise ValueError('approved device list invalid')
    approved = [text(serial, 256) for serial in approved]
    if runtime.person.uid != target or revision != config['runtime_revision'] or len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('upstream target runtime mismatch')
    runtime.device_binding(approved)
    return target, approved


def apply(roots, config, runtime, key, revision):
    target, approved = validate_runtime(config, runtime, revision)
    upstream = config['upstream']
    index = runtime.source_index()
    approvals = restoration_approvals(upstream)
    groups, batches, imported, duplicate = {}, [], 0, 0
    validated = [(Path(root), validate_batch(root, upstream['scope'])) for root in roots]
    bindings = provider_bindings(index, upstream['scope'])
    for _, manifest in validated:
        for entry in manifest['files']:
            bindings.setdefault(entry['provider_id'], set()).add(entry['sha256'])
    for root, manifest in validated:
        accepted, withheld, restored = [], [], []
        for entry in manifest['files']:
            binding = bindings[entry['provider_id']]
            approval = approvals.get(entry['provider_id'])
            if approval and entry['sha256'] == approval['new_sha256'] and binding == {approval['old_sha256'], approval['new_sha256']}:
                restored.append(verify_restoration(root, entry, approval, upstream, runtime, index, key, approved))
                accepted.append(file_identity(entry))
                continue
            if (len(binding) > 1 or (approval and entry['sha256'] != approval['old_sha256'])) and not (approval and entry['sha256'] == approval['old_sha256'] and binding == {approval['old_sha256'], approval['new_sha256']}):
                withheld.append({'provider_id': entry['provider_id'], 'sha256': entry['sha256'], 'reason': 'changed_source'})
                continue
            raw = state.read_bounded(root / entry['path'], state.MAX_FILE)
            state.verified_raw(raw, entry)
            digest = entry['sha256']
            hashed = hmac.new(key, raw, hashlib.sha256).hexdigest()
            by_hash, by_sha = runtime.existing(hashed), index.get(digest)
            if by_sha is not None and (by_hash is None or by_sha.uid != by_hash.uid):
                raise ValueError('upstream digest/provenance mismatch')
            if by_hash is not None:
                runtime.verify(by_hash, entry)
            parsed = json.loads(raw)
            serial = parsed.get('DeviceInformation', {}).get('Final', {}).get('NeurostimulatorSerialNumber')
            # Previously accepted, authenticated target bytes need no new device
            # assignment. Unknown NEW bytes still require explicit device approval.
            if (not isinstance(serial, str) or serial not in approved) and by_sha is None:
                withheld.append({'provider_id': entry['provider_id'], 'sha256': entry['sha256'], 'reason': 'unknown_device'})
                continue
            group = groups.setdefault(digest, {'hashed': hashed, 'root': root, 'entries': []})
            if group['hashed'] != hashed:
                raise ValueError('upstream raw identity collision')
            group['entries'].append(entry)
            accepted.append(file_identity(entry))
        batches.append((root, manifest, accepted, withheld, restored))
    new_groups = {}
    for digest, group in groups.items():
        by_hash, by_sha = runtime.existing(group['hashed']), index.get(digest)
        if by_sha is not None and (by_hash is None or by_sha.uid != by_hash.uid):
            raise ValueError('upstream digest/provenance mismatch')
        if by_hash is not None:
            runtime.verify(by_hash, group['entries'][0])
            merge_provenance((by_hash.metadata or {}).get('UpstreamSource'), upstream['scope'], digest, group['entries'])
            duplicate += 1
        else:
            imported += 1
            new_groups[digest] = group
    if new_groups:
        runtime.ingest_upstream(new_groups)
    updates, expected = [], {}
    for digest, group in groups.items():
        row = runtime.existing(group['hashed'])
        if row is None:
            raise ValueError('upstream ingestion incomplete')
        runtime.verify(row, group['entries'][0])
        expected[digest] = merge_provenance((row.metadata or {}).get('UpstreamSource'), upstream['scope'], digest, group['entries'])
        updates.append((row, expected[digest]))
    if updates:
        runtime.save_upstream(updates)
    for digest, group in groups.items():
        if runtime.existing(group['hashed']).metadata.get('UpstreamSource') != expected[digest]:
            raise ValueError('upstream provenance readback mismatch')
    if isinstance(runtime, target_adapter.TargetRuntime):
        runtime.verify_final_schedules()
    receipts = [(root, receipt(manifest, target, revision, accepted, withheld, restored)) for root, manifest, accepted, withheld, restored in batches]
    return receipts, imported, duplicate



def saved_receipt_matches(saved, manifest, root, config, runtime, key, revision):
    identities = [file_identity(entry) for entry in manifest['files']]
    approvals = restoration_approvals(config['upstream'])
    revised = [(entry, approvals[entry['provider_id']]) for entry in manifest['files']
               if entry['provider_id'] in approvals and entry['sha256'] == approvals[entry['provider_id']]['new_sha256']]
    relationships = [{**record, 'new_file': file_identity(entry)} for entry, record in revised]
    expected = receipt(manifest, config['target_participant_uid'], saved['runtime_revision'], identities, [], relationships)
    if saved != expected:
        return False
    if not relationships:
        return True
    _, approved = validate_runtime(config, runtime, revision)
    index = runtime.source_index()
    for entry, record in revised:
        verify_restoration(root, entry, record, config['upstream'], runtime, index, key, approved)
    return True


def run(config, runtime, key, revision):
    upstream = config['upstream']
    target_adapter.verify_receipt_directory(upstream['receipts'])
    pending, skipped = [], 0
    for path in sorted(state.safe_path(upstream['batches']).iterdir()):
        if path.name.startswith('.pending-'):
            continue
        manifest = validate_batch(path, upstream['scope'])
        destination = Path(upstream['receipts']) / (path.name + '.json')
        if destination.exists():
            saved = json.loads(state.read_bounded(destination, 16 * 1024 * 1024))
            if saved_receipt_matches(saved, manifest, path, config, runtime, key, revision):
                skipped += 1
                continue
        pending.append(path)
    receipts, imported, duplicate = apply(pending, config, runtime, key, revision)
    for path, value in receipts:
        state.atomic_json(Path(upstream['receipts']) / (path.name + '.json'), value)
    accepted = sum(len(value['accepted']) for _, value in receipts)
    withheld = sum(len(value['withheld']) for _, value in receipts)
    changed = any(item['reason'] == 'changed_source' for _, value in receipts for item in value['withheld'])
    return {'applied_batches': len(receipts), 'already_applied_batches': skipped,
        'imported_unique_reports': imported, 'duplicate_unique_reports': duplicate,
        'accepted_files': accepted, 'withheld_files': withheld,
        'accepted_revision_files': sum(len(value.get('serial_restorations', [])) for _, value in receipts),
        'error_code': 'changed_source' if changed else ('unknown_device' if withheld else None)}


def execute(config):
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
            raise ValueError('upstream database mismatch')
        person = models.Participant.objects.get(uid=state.uid(config['target_participant_uid']),
            institute_id=state.uid(config['target_institute_uid']), name=config['participant_name'])
        root = Path(os.environ['DATASERVER_PATH']) / 'raws'
        if root != Path(config['raw_root']):
            raise ValueError('upstream raw root mismatch')
        runtime = Runtime(models, DataCurator.loadCacheFile, call_command, transaction.atomic, person, root)
        return run(config, runtime, os.environ['DATASERVER_HASHKEY'].encode(), os.environ['BRAVO_BUILD_REVISION'])
