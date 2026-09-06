"""Synchronize RCS08 neural, REDCap, and Oura sources."""

import json

from django.core.management.base import BaseCommand, CommandError

from modules import RCS08Sync


class Command(BaseCommand):
    help = "Idempotently synchronize RCS08 neural, REDCap, and Oura data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stream",
            action="append",
            choices=("neural", "redcap", "oura"),
            help="Stream to sync; repeat for multiple streams (default: all).",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--create-participant",
            action="store_true",
            help="Create RCS08 in the sole/configured institute if it does not exist.",
        )
        parser.add_argument("--neural-limit", type=int, default=0)
        parser.add_argument("--full-oura", action="store_true")

    def handle(self, *args, **options):
        streams = tuple(options["stream"] or ("neural", "redcap", "oura"))
        try:
            results = RCS08Sync.run_sync(
                streams=streams,
                dry_run=options["dry_run"],
                create_participant=options["create_participant"],
                neural_limit=options["neural_limit"],
                full_oura=options["full_oura"],
            )
        except RCS08Sync.SyncError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(results, sort_keys=True, default=str))
