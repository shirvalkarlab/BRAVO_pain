"""Backfill the chronic-trend sensing CONFIG (center frequency + dated frequency & contact
schedules) onto already-stored recordings.

WHY: The Biomarkers timeline draws each chronic channel from three fields stamped at DECODE time
(Session.decodeMedtronicJSON) onto the chronic Recording's metadata:
  * CenterFrequencyHz  — the latest group-level sensing band (Groups.Final[].ProgramSettings.
                         SensingChannel[].SensingSetup.FrequencyInHertz).
  * FreqScheduleHz     — the DATED per-hemisphere frequency schedule from GroupHistory (records WHEN
                         the band changed), which drives the frequency RIBBON's real switches.
  * ContactSchedule    — the DATED per-hemisphere bipolar-CONTACT schedule from GroupHistory, which
                         drives the per-CONTACT row split (each chronic point lands in the row of the
                         contact it was actually recorded from).
Recordings ingested BEFORE a given field's stamping existed are missing it even though the value is
present in the stored source JSON. Re-uploading does NOT fix this: the upload API rejects duplicate
content (HTTP 301) before doing any work.

WHAT THIS DOES: re-reads each stored source file IN PLACE and re-runs the SAME extractors the decoder
uses (_chronic_center_freqs / _chronic_freq_schedule / _chronic_contact_schedule -> guaranteed
identical result), patching the three fields onto the matching chronic Recording rows. No re-upload,
no source bytes rewritten, nothing deleted. Idempotent: a recording that already has ALL present
fields is skipped unless --force (a recording missing ANY field is patched so older backfills are
upgraded to the full config).

USAGE (inside the server container, where the DB + cache files live):
    python manage.py backfill_chronic_freq --dry-run     # report what WOULD change, write nothing
    python manage.py backfill_chronic_freq               # apply
    python manage.py backfill_chronic_freq --participant <uid>   # limit to one participant
    python manage.py backfill_chronic_freq --force       # overwrite even if values are already set
"""
import json
import traceback

from django.core.management.base import BaseCommand

from modules import DataCurator
from modules.MedtronicPercept.Session import (
    _chronic_center_freqs, _chronic_freq_schedule, _chronic_contact_schedule,
)
import Server.models as models

CHRONIC_TYPE = "MedtronicChronicBrainSense"


class Command(BaseCommand):
    help = ("Backfill chronic sensing config (CenterFrequencyHz + FreqScheduleHz + ContactSchedule) "
            "onto stored chronic BrainSense recordings.")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change; write nothing.")
        parser.add_argument("--force", action="store_true",
                            help="Overwrite the fields even when values are already present.")
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
        n_patched = n_skipped_present = n_no_data = n_no_match = n_src_err = 0
        n_freq = n_fsched = n_csched = 0   # how many recordings gained each field

        for si, (source_id, rlist) in enumerate(by_source.items(), 1):
            source_file = rlist[0].source
            # Re-run the THREE chronic-config extractors ONCE per source from the stored bytes.
            # hz_map keyed by hemi_token; the two schedules also keyed by hemi_token (they walk
            # GroupHistory, so they need the whole JSON, not just JSON["Groups"]).
            try:
                rawBytes = DataCurator.loadCacheFile(source_file)
                JSON = json.loads(rawBytes)
                hz_map = _chronic_center_freqs(JSON.get("Groups"))
                freq_sched = _chronic_freq_schedule(JSON)
                contact_sched = _chronic_contact_schedule(JSON)
            except Exception:
                n_src_err += 1
                self.stderr.write(f"  [{si}/{n_sources}] source {source_id}: decode FAILED, skipping")
                self.stderr.write(traceback.format_exc())
                continue

            if not hz_map and not freq_sched and not contact_sched:
                # Source genuinely carries no group-level sensing config -> nothing to stamp.
                n_no_data += len(rlist)
                continue

            for r in rlist:
                md = dict(r.metadata or {})
                chans = md.get("ChannelNames") or []
                hemi_token = str(chans[0]).split(" ")[0] if chans else ""
                hz = hz_map.get(hemi_token)
                fsched = freq_sched.get(hemi_token)
                csched = contact_sched.get(hemi_token)
                if hz is None and not fsched and not csched:
                    n_no_match += 1
                    continue
                # Skip only when every available field is ALREADY present (older backfills that have
                # CenterFrequencyHz but not the schedules are NOT skipped — they get upgraded).
                have_all = (
                    (hz is None or md.get("CenterFrequencyHz") is not None)
                    and (not fsched or md.get("FreqScheduleHz") is not None)
                    and (not csched or md.get("ContactSchedule") is not None))
                if have_all and not force:
                    n_skipped_present += 1
                    continue

                changes = []
                if hz is not None and (md.get("CenterFrequencyHz") is None or force):
                    if md.get("CenterFrequencyHz") != hz:
                        changes.append(f"CenterFrequencyHz {md.get('CenterFrequencyHz')!r}->{hz}")
                        md["CenterFrequencyHz"] = hz
                        n_freq += 1
                if fsched and (md.get("FreqScheduleHz") is None or force):
                    md["FreqScheduleHz"] = fsched
                    changes.append(f"FreqScheduleHz[{len(fsched)} cp]")
                    n_fsched += 1
                if csched and (md.get("ContactSchedule") is None or force):
                    md["ContactSchedule"] = csched
                    changes.append(f"ContactSchedule[{len(csched)} cp]")
                    n_csched += 1
                if not changes:
                    n_skipped_present += 1
                    continue
                n_patched += 1
                if dry:
                    self.stdout.write(f"  would patch {r.uid} [{hemi_token}]: " + ", ".join(changes))
                else:
                    r.metadata = md
                    r.save(update_fields=["metadata"])

        verb = "WOULD patch" if dry else "Patched"
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb} {n_patched} recording(s) across {n_sources} source file(s)."))
        self.stdout.write(
            f"  fields set — CenterFrequencyHz: {n_freq}, FreqScheduleHz: {n_fsched}, "
            f"ContactSchedule: {n_csched}\n"
            f"  skipped (already complete): {n_skipped_present}\n"
            f"  no group-level config in source: {n_no_data}\n"
            f"  no hemisphere match: {n_no_match}\n"
            f"  source decode errors: {n_src_err}")
        if dry:
            self.stdout.write(self.style.WARNING("Dry run — nothing was written. Re-run without --dry-run to apply."))