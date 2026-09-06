"""Publish PDF date metadata only; no sync, neural ingestion or analysis."""
import json
from django.core.management.base import BaseCommand, CommandError
from modules import RCS08PDFMetadata, RCS08Sync


class Command(BaseCommand):
    help = "Index local RCS08 PDF Session Date headers only; never ingest or sync scientific data."

    def handle(self, *args, **options):
        try:
            participant = RCS08Sync.resolve_participant(create=False)
            result = RCS08PDFMetadata.index_folder(RCS08Sync.NEURAL_FOLDER, participant.uid, RCS08Sync.STORAGE_PATH)
        except (ValueError, RCS08Sync.SyncError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, sort_keys=True))
