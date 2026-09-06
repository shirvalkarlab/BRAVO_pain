import json
from django.core.management.base import BaseCommand
from modules import ReportCache, RCS08Sync

class Command(BaseCommand):
    help = "Prepare existing RCS08 reports without fetching external data."
    def handle(self, *args, **options):
        self.stdout.write(json.dumps(ReportCache.prewarm_participant(RCS08Sync.resolve_participant())))
