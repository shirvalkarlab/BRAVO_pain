'Ingest a FOLDER of Medtronic Percept session-report JSONs for one participant.'
import os
import glob
import hmac
import time
import hashlib
import traceback

from django.core.management.base import BaseCommand, CommandError

from Server import models
from modules import DataCurator

HASH_KEY = os.environ.get("DATASERVER_HASHKEY")


class Command(BaseCommand):
    help = "Batch-ingest Medtronic Percept session-report JSONs from a folder for one participant."

    def add_arguments(self, parser):
        parser.add_argument("--folder", required=True,
                            help="Directory containing *.json session reports (searched recursively).")
        parser.add_argument("--participant", required=True,
                            help="Participant name or uid (e.g. SYNTHETIC01).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report new vs duplicate counts and exit without writing.")
        parser.add_argument("--limit", type=int, default=0,
                            help="Ingest at most N new files (0 = no limit). Useful for a first trial.")
        parser.add_argument("--continue-on-error", action="store_true",
                            help="Keep going when a single file fails to decode (default: keep going "
                                 "and report; set this off only if you want a hard stop).")

    def handle(self, *args, **opt):
        if not HASH_KEY:
            raise CommandError("DATASERVER_HASHKEY is not set; run this inside the BRAVO container.")

        folder = opt["folder"]
        if not os.path.isdir(folder):
            raise CommandError(f"folder not found: {folder}")

        person = models.Participant.find(uid=opt["participant"])
        if not person:
            matches = [p for p in models.Participant.objects.all()
                       if getattr(p, "name", None) == opt["participant"]]
            if len(matches) > 1:
                raise CommandError(f"{opt['participant']!r} matches {len(matches)} participants; pass a uid.")
            person = matches[0] if matches else None
        if not person:
            have = ", ".join(sorted(str(getattr(p, "name", "?")) for p in models.Participant.objects.all()))
            raise CommandError(f"participant {opt['participant']!r} not found. Known: {have}")

        institute = person.institute
        files = sorted(glob.glob(os.path.join(folder, "**", "*.json"), recursive=True))
        if not files:
            raise CommandError(f"no *.json under {folder}")

        self.stdout.write(f"participant {getattr(person, 'name', '?')} ({person.uid[:12]})  "
                          f"institute {institute.pk}")
        self.stdout.write(f"found {len(files)} JSON files under {folder}")

        # --- classify BEFORE writing anything, so --dry-run is genuinely read-only -------------
        hashed, unreadable = [], []
        for f in files:
            try:
                with open(f, "rb") as fh:
                    raw = fh.read()
            except Exception as e:
                unreadable.append((f, str(e)))
                continue
            hashed.append((f, hmac.new(HASH_KEY.encode("utf8"), raw, hashlib.sha256).hexdigest()))
        # a copy repeated within this folder counts as held too, not only one already stored
        from modules.MedtronicPercept.ingest_batch import split_new_and_held
        new_files, dupes = split_new_and_held(hashed, lambda uh: models.SourceFile.objects.filter(
            unique_hashed=uh, institute=str(institute.pk)).exists())

        # One export at a time, oldest session first by its own SessionDate (CLAUDE.md section 11);
        # file-name order need not follow the session.
        from modules.MedtronicPercept.session_order import in_session_order
        hashes = dict(new_files)
        new_files = [(f, hashes[f]) for f in in_session_order(list(hashes))]

        self.stdout.write(f"  already in BRAVO : {len(dupes)}")
        self.stdout.write(f"  NEW to ingest    : {len(new_files)}")
        if unreadable:
            self.stdout.write(self.style.WARNING(f"  unreadable       : {len(unreadable)}"))
            for f, e in unreadable[:5]:
                self.stdout.write(f"      {os.path.basename(f)}: {e}")

        if opt["dry_run"]:
            self.stdout.write(self.style.SUCCESS("dry run — nothing written"))
            for f, _ in new_files[:15]:
                self.stdout.write(f"      would ingest {os.path.basename(f)}")
            if len(new_files) > 15:
                self.stdout.write(f"      ... and {len(new_files) - 15} more")
            return

        if opt["limit"]:
            new_files = new_files[:opt["limit"]]
            self.stdout.write(f"  --limit applied: ingesting {len(new_files)}")

        ok, failed = 0, []
        t0 = time.time()
        for i, (f, uh) in enumerate(new_files, 1):
            name = os.path.basename(f)
            # Bind per iteration. Without this, a failure BEFORE saveCacheFile (a read error, or
            # saveCacheFile itself raising) would leave `sf` pointing at the PREVIOUS iteration's
            # successfully ingested row, and the cleanup below would delete that record and cascade
            # to its Recordings — destroying good data instead of the failed attempt.
            sf = None
            try:
                with open(f, "rb") as fh:
                    raw = fh.read()
                metadata = {
                    "UploadType": "MedtronicJSON",
                    "Institute": institute.pk,
                    "Uploader": institute.pk,
                    "UniqueHashed": uh,
                    # Same defaults the DefaultType browser path stamps on a .json upload.
                    "device_location": "",
                    "automatic_deidentification": False,
                    "infer_from_device": True,
                    "automatic_concatenation": False,
                }
                sf = DataCurator.saveCacheFile(name, metadata, raw)
                sf.owner = person
                sf.save()
                DataCurator.MedtronicPerceptJSONDecoder(sf, person=person)
                ok += 1
            except Exception as e:
                failed.append((name, str(e)))
                self.stdout.write(self.style.ERROR(f"  [{i}/{len(new_files)}] FAILED {name}: {e}"))
                self.stdout.write(traceback.format_exc(limit=3))
                # A single malformed export must not abandon the rest of the batch. Remove ONLY a
                # row created by THIS iteration, so a retry is clean rather than colliding on the
                # dedup hash. `sf is None` means we never got as far as creating one.
                if sf is not None:
                    try:
                        sf.delete()
                    except Exception:
                        pass
                if not opt["continue_on_error"]:
                    continue
            if i % 25 == 0:
                self.stdout.write(f"  [{i}/{len(new_files)}] {ok} ok, {len(failed)} failed "
                                  f"({time.time() - t0:.0f}s)")

        self.stdout.write(self.style.SUCCESS(
            f"ingested {ok} of {len(new_files)} new files in {time.time() - t0:.0f}s"))
        if failed:
            self.stdout.write(self.style.WARNING(f"{len(failed)} failed:"))
            for n, e in failed[:20]:
                self.stdout.write(f"    {n}: {e}")

        self.stdout.write("\nNEXT: the Biomarkers assembled-matrix cache keys on the recording set, so "
                          "the next request for this participant recomputes automatically. Reload the "
                          "Biomarker view; the first load after an ingest is the slow one.")
