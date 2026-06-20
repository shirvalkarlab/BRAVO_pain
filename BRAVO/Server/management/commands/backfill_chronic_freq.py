"""Backfill the chronic-trend sensing CENTER FREQUENCY onto already-stored recordings.

WHY: The Biomarkers timeline draws a per-channel frequency ribbon from each chronic recording's
metadata["CenterFrequencyHz"]. That field is stamped at DECODE time (Session.decodeMedtronicJSON,
from the GROUP-level Groups.Final[].ProgramSettings.SensingChannel[].SensingSetup.FrequencyInHertz).
Recordings ingested BEFORE that stamping existed have no CenterFrequencyHz, so their real
session-to-session frequency history is missing even though the value is present in the stored
source JSON. Re-uploading does NOT fix this: the upload API rejects duplicate content (HTTP 301)
before doing any work.

WHAT THIS DOES: re-reads each stored source file IN PLACE, extracts the per-hemisphere center
frequency with the SAME helper the decoder uses (_chronic_center_freqs -> guaranteed identical
result), and patches metadata["CenterFrequencyHz"] onto the matching chronic Recording rows. No
re-upload, no source bytes rewritten, nothing deleted. Idempotent: a recording that already has the
field is skipped unless --force.

USAGE (inside the server container, where the DB + cache files live):
    python manage.py backfill_chronic_freq --dry-run     # report what WOULD change, write nothing
    python manage.py backfill_chronic_freq               # apply
    python manage.py backfill_chronic_freq --participant <uid>   # limit to one participant
    python manage.py backfill_chronic_freq --force       # overwrite even if a value is already set
"""
import json
import traceback

from django.core.management.base import BaseCommand

from modules import DataCurator
from modules.MedtronicPercept.Session import _chronic_center_freqs
import Server.models as models

CHRONIC_TYPE = "MedtronicChronicBrainSense"


class Command(BaseCommand):
    help = "Backfill metadata['CenterFrequencyHz'] onto stored chronic BrainSense recordings."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change; write nothing.")
        parser.add_argument("--force", action="store_true",
                            help="Overwrite CenterFrequencyHz even when one is already present.")
        parser.add_argument("--participant", default=None,
                            help="Limit to chronic recordings owned by this participant uid.")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        force = opts["force"]
        part = opts["participant"]

        qs = models.Recording.objects.select_related("source").filter(type=CHRONIC_TYPE)
        if part:
            qs = qs.filter(source__owner__uid=part)
        recs = list(qs)
        self.stdout.write(f"Found {len(recs)} chronic recording(s)"
                          + (f" for participant {part}" if part else "") + ".")

        # Group by source file so each JSON is decrypted + parsed ONCE (decode is the expensive step).
        by_source = {}
        for r in recs:
            by_source.setdefault(r.source_id, []).append(r)

        n_sources = len(by_source)
        n_patched = n_skipped_present = n_no_freq = n_no_match = n_src_err = 0

        for si, (source_id, rlist) in enumerate(by_source.items(), 1):
            source_file = rlist[0].source
            # Decode the group-level frequency map ONCE per source from the stored bytes.
            try:
                rawBytes = DataCurator.loadCacheFile(source_file)
                JSON = json.loads(rawBytes)
                hz_map = _chronic_center_freqs(JSON.get("Groups"))
            except Exception:
                n_src_err += 1
                self.stderr.write(f"  [{si}/{n_sources}] source {source_id}: decode FAILED, skipping")
                self.stderr.write(traceback.format_exc())
                continue

            if not hz_map:
                # Source genuinely carries no group-level sensing frequency -> nothing to stamp.
                n_no_freq += len(rlist)
                continue

            for r in rlist:
                md = dict(r.metadata or {})
                if md.get("CenterFrequencyHz") is not None and not force:
                    n_skipped_present += 1
                    continue
                chans = md.get("ChannelNames") or []
                hemi_token = str(chans[0]).split(" ")[0] if chans else ""
                hz = hz_map.get(hemi_token)
                if hz is None:
                    n_no_match += 1
                    continue
                old = md.get("CenterFrequencyHz")
                md["CenterFrequencyHz"] = hz
                n_patched += 1
                if dry:
                    self.stdout.write(f"  would set {r.uid} [{hemi_token}] "
                                      f"{old!r} -> {hz} Hz")
                else:
                    r.metadata = md
                    r.save(update_fields=["metadata"])

        verb = "WOULD patch" if dry else "Patched"
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb} {n_patched} recording(s) across {n_sources} source file(s)."))
        self.stdout.write(
            f"  skipped (already set): {n_skipped_present}\n"
            f"  no group-level frequency in source: {n_no_freq}\n"
            f"  no hemisphere match: {n_no_match}\n"
            f"  source decode errors: {n_src_err}")
        if dry:
            self.stdout.write(self.style.WARNING("Dry run — nothing was written. Re-run without --dry-run to apply."))