"""Export current stored RCS08 data without requesting a data sync."""

import json
from django.core.management.base import BaseCommand, CommandError
from modules import RCS08Exports, RCS08Sync


class Command(BaseCommand):
    help = "Write REDCap and Oura CSVs from current stored data, without external fetching."

    def add_arguments(self, parser):
        parser.add_argument("--destination", help="Existing folder; defaults to RCS08_EXPORT_DIRECTORY")

    def handle(self, *args, **options):
        try:
            manifest = RCS08Exports.export_stored_data(
                RCS08Sync.resolve_participant(), options.get("destination"))
        except Exception as exc:
            raise CommandError(f"RCS08 CSV export failed: {type(exc).__name__}: {exc}") from exc
        self.stdout.write(json.dumps({"exported_at_utc": manifest["exported_at_utc"],
                                     "files": manifest["files"]}, sort_keys=True))
