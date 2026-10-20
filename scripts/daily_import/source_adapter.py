"""Read-only source ORM/loader adapter; private state and batches are additive.

Run inside the source application's existing environment. Host wrappers provide
an exclusive lock and private writable export directory, never the source tree.
"""
import argparse
import hashlib
import hmac
import zlib
import contextlib
import json
import io
import tarfile
import os
from pathlib import Path
import struct
import sys
import time

try:
    from . import state
except ImportError:  # direct script in the existing application container
    import state


def bounded_load(row, loader):
    """Authenticate and bound every canonical compressed form before allocation.

    CFrame offsets follow https://blosc.org/c-blosc2/format/cframe_format.html;
    legacy chunk lengths follow the companion chunk_format.html specification.
    The canonical loader still authenticates/decrypts; no source key is exported.
    """
    identity = state.file_identity(row.pointer)
    compressed = state.read_bounded(row.pointer, 384 * 1024 * 1024)
    expected = hmac.new(os.environ['DATASERVER_HASHKEY'].encode(), compressed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, row.hashed):
        raise ValueError('stored payload authentication failed')
    maximum = 4 * ((57 + 16 * (state.MAX_FILE // 16 + 1) + 2) // 3)
    if compressed.startswith(b'BRAVO_ZLIB_v1\0'):
        decoder = zlib.decompressobj()
        token = decoder.decompress(compressed[len(b'BRAVO_ZLIB_v1\0'):], maximum + 1)
        token_size = len(token)
        if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
            raise ValueError('invalid or oversized fallback payload')
        del token
    elif b'b2frame' in compressed[:16]:
        # Check fixed header lengths BEFORE constructing any decompression view.
        if len(compressed) < 87 or compressed[2:10] != b'b2frame\0':
            raise ValueError('invalid frame header')
        token_size = int.from_bytes(compressed[30:38], 'big', signed=True)
        if int.from_bytes(compressed[16:24], 'big') != identity[2] or not 100 <= token_size <= maximum:
            raise ValueError('frame size bound exceeded')
        import blosc2
        frame = blosc2.schunk_from_cframe(compressed, copy=False)
        kind, shape, dtype = frame.vlmeta['__pack_tensor__']
        if frame.nbytes != token_size or kind != 'numpy' or tuple(shape) != (token_size,) or dtype != '|u1':
            raise ValueError('noncanonical or oversized tensor metadata')
        del frame
    else:
        token_size, _, stored_size = struct.unpack('<III', compressed[4:16])
        if stored_size != identity[2]:
            raise ValueError('stored payload size mismatch')
    if not 100 <= token_size <= maximum:
        raise ValueError('declared plaintext size bound exceeded')
    del compressed
    raw = loader(row)
    state.verified_raw(raw)
    return raw


class SourceReader:
    """Only SELECT queries and authenticated file reads against the source."""
    def __init__(self, models, loader, participant, raw_root):
        self.models, self.loader = models, loader
        self.participant, self.raw_root = state.uid(participant), Path(raw_root)

    def row(self, source):
        return self.models.SourceFile.objects.get(uid=state.uid(source), owner_id=self.participant, type='MedtronicJSON')

    def observe_row(self, row):
        return state.observation({'uid': str(row.uid), 'owner': str(row.owner_id),
            'type': row.type, 'upload_type': (row.metadata or {}).get('UploadType'),
            'pointer': row.pointer, 'stored_hash': row.hashed}, self.participant, self.raw_root)

    def inventory(self):
        rows = list(self.models.SourceFile.objects.filter(owner_id=self.participant,
            type='MedtronicJSON').order_by('uid')[:state.MAX_FILES + 1])
        if len(rows) > state.MAX_FILES:
            raise ValueError('source inventory exceeds bound')
        return {str(row.uid): self.observe_row(row) for row in rows}

    def reobserve(self, source):
        return self.observe_row(self.row(source))

    def load(self, source):
        row = self.row(source)
        if self.observe_row(row) is None:
            raise ValueError('source no longer finalized')
        return bounded_load(row, self.loader)


def refresh(config, reader, sleep=time.sleep):
    """Reconcile baseline once, then publish additions without deleting history."""
    participant = state.uid(config['source_participant_uid'])
    interval = config.get('observation_seconds', 5)
    if not isinstance(interval, (int, float)) or not 1 <= interval <= 300:
        raise ValueError('invalid observation interval')
    checkpoint_path, batches = Path(config['checkpoint']), Path(config['batches'])
    before = reader.inventory()
    sleep(interval)
    after = reader.inventory()
    initialized = not checkpoint_path.exists()
    if initialized:
        manifest = json.loads(state.read_bounded(config['baseline_manifest'], 16 * 1024 * 1024))
        checkpoint = state.baseline(manifest, participant, before, after, reader.load, reader.reobserve)
        state.atomic_json(checkpoint_path, checkpoint)
    else:
        checkpoint = json.loads(state.read_bounded(checkpoint_path, 16 * 1024 * 1024))
    # A crash after atomic batch publication but before checkpoint update is
    # recovered from verified immutable batches, never by trusting filenames.
    for path in sorted(batches.iterdir()):
        if path.name.startswith('.pending-'):
            continue
        state.digest(path.name)
        manifest = state.validate_batch(path, participant)
        if path.name != state.sha(state.encoded(manifest)):
            raise ValueError('batch directory identity mismatch')
        checkpoint = state.acknowledge_export(checkpoint, manifest)
    chosen, deferred = state.select(checkpoint, participant, before, after)
    batch = state.publish(batches, participant, chosen, reader.load, reader.reobserve)
    if batch is not None:
        checkpoint = state.acknowledge_export(checkpoint, state.validate_batch(batch, participant))
    state.atomic_json(checkpoint_path, checkpoint)
    return {'initialized': initialized, 'inventory': len(after), 'exported': len(chosen),
            'deferred': len(deferred), 'published_batch': batch.name if batch else None}


def configure_reader(config):
    """Initialize read-only interfaces without copying original credentials."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BRAVO.settings')
    import django
    django.setup()
    from Server import models
    from modules import DataCurator
    person = models.Participant.objects.get(uid=state.uid(config['source_participant_uid']))
    if person.name != config['participant_name']:
        raise ValueError('source identity mismatch')
    root = Path(os.environ['DATASERVER_PATH']) / 'raws'
    if root != Path(config['raw_root']):
        raise ValueError('source root mismatch')
    return SourceReader(models, DataCurator.loadCacheFile, person.uid, root)


def transport(request, reader, output):
    """Stream private results to host; never create files inside source container.

    inventory: JSON observation map. baseline: takes manifest,before,after and
    returns authenticated checkpoint JSON. export: takes chosen observation map,
    returns TAR sources + export.manifest. A failed stream has no valid manifest;
    host must validate the entire archive before atomic publication/checkpoint.
    """
    mode = request['mode']
    if mode == 'inventory':
        output.write(state.encoded(reader.inventory()))
        return
    if mode == 'baseline':
        result = state.baseline(request['manifest'], reader.participant,
            request['before'], request['after'], reader.load, reader.reobserve)
        output.write(state.encoded(result))
        return
    if mode != 'export':
        raise ValueError('unknown transport mode')
    chosen = request['chosen']
    if not isinstance(chosen, dict) or not 0 < len(chosen) <= state.MAX_FILES:
        raise ValueError('invalid export inventory')
    entries, fingerprints, total = [], {}, 0
    with tarfile.open(fileobj=output, mode='w|') as archive:
        for source, observed in sorted(chosen.items()):
            state.uid(source)
            if reader.reobserve(source) != observed:
                raise ValueError('source changed before export')
            raw = reader.load(source)
            raw_sha = state.verified_raw(raw)
            if reader.reobserve(source) != observed:
                raise ValueError('source changed during export')
            total += len(raw)
            if total > state.MAX_TOTAL:
                raise ValueError('export exceeds total bound')
            name = 'sources/' + source + '.json'
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = len(raw), 0o600, 0
            archive.addfile(member, io.BytesIO(raw))
            entries.append({'source_uid': source, 'path': name, 'bytes': len(raw), 'sha256': raw_sha})
            fingerprints[source] = state.digest(observed['stored_hash'])
        manifest = {'format': 1, 'source_participant_uid': reader.participant,
            'count': len(entries), 'total_bytes': total, 'files': entries, 'fingerprints': fingerprints}
        payload = state.encoded(manifest)
        member = tarfile.TarInfo('export.manifest')
        member.size, member.mode, member.mtime = len(payload), 0o600, 0
        archive.addfile(member, io.BytesIO(payload))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--transport', action='store_true', help='Read private request/config JSON from stdin; no source writes')
    args = parser.parse_args()
    output = sys.stdout.buffer
    if args.transport:
        payload = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        if len(payload) > 16 * 1024 * 1024:
            raise ValueError('transport request exceeds bound')
        request = json.loads(payload)
        config = request['config']
    else:
        config = json.loads(state.read_bounded(args.config, 65536))
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        reader = configure_reader(config)
        if args.transport:
            transport(request, reader, output)
        else:
            output.write(state.encoded(refresh(config, reader)))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        sys.stderr.write('Daily source export failed; checkpoint and immutable batches retained.\n')
        sys.exit(1)
