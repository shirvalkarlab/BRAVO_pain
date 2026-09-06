"""Publish latest measurement metadata from existing stored Oura samples only."""
import json
from django.core.management.base import BaseCommand, CommandError
from modules import RCS08OuraFreshness, RCS08Sync


class Command(BaseCommand):
    help = "Index latest eligible Oura HR/HRV measurement; no network, sync or sample changes."

    def handle(self, *args, **options):
        try:
            participant = RCS08Sync.resolve_participant(create=False)
            result = RCS08OuraFreshness.initialize_metadata(participant)
        except (ValueError, RCS08Sync.SyncError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({"available": result["available"], "value": result["value"],
                                     "partial": result["partial"], "coverage": result["coverage"]}))
