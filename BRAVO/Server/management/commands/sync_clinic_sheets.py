"""Pull the lab's clinic-testing workbooks down from Google Drive and ingest them (decision 182).

Two steps, both idempotent: `clinic_sheet_sync.sync_folder` (a file Drive reports unchanged is
not downloaded again) and then `ingest_clinic_sheets`'s own `clinic_pain.ingest_and_store` (an
unchanged folder writes nothing). Runs on the daily pass (`stability_precompute_loop.sh`) and by
hand:

    python manage.py sync_clinic_sheets --participant <uid> [--folder /path] [--json]

Needs the signed-in Google client (`google_sheets_client.client_if_available()`); without one it
says so and exits 2 rather than pretending the folder is current.
"""
import json
import sys

from django.core.management.base import BaseCommand

from modules.StimOptimizer import clinic_pain, clinic_sheet_sync, google_sheets_client as gsc

from .ingest_clinic_sheets import DEFAULT_FOLDER


class Command(BaseCommand):
    help = "Pull the clinic-testing workbooks from Google Drive into the ingest folder, then ingest."

    def add_arguments(self, parser):
        parser.add_argument("--participant", dest="participant", required=True)
        parser.add_argument("--folder", dest="folder", default=DEFAULT_FOLDER)
        parser.add_argument("--json", dest="as_json", action="store_true")

    def handle(self, *args, **opts):
        from Server import models
        participant = models.Participant.find(uid=opts["participant"])
        if participant is None:
            self.stderr.write(f"no participant with uid {opts['participant']!r}")
            sys.exit(2)
        drive = gsc.client_if_available()
        if drive is None:
            self.stderr.write("no signed-in Google client (secrets/google_oauth_token.json); the "
                              "folder was NOT synced")
            sys.exit(2)
        sync = clinic_sheet_sync.sync_folder(drive, gsc.folder_id(), opts["folder"])
        report = clinic_pain.ingest_and_store(participant, opts["folder"])
        out = {"sync": sync, "ingest": report}
        if opts["as_json"]:
            self.stdout.write(json.dumps(out, default=str))
        else:
            self.stdout.write(f"sync: {sync['downloaded']} downloaded, {sync['skipped_unchanged']} "
                              f"unchanged, {len(sync['excluded'])} excluded, {len(sync['failed'])} "
                              f"failed; ingest: {report}")
        if sync["failed"]:
            sys.exit(1)
