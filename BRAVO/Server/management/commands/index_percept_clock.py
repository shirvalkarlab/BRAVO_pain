"""Preview or apply derived clocks and missing exact native event representations."""
import json
from django.core.management.base import BaseCommand, CommandError
from Server import models
from modules import PerceptClockData


class Command(BaseCommand):
    help = "Index retained Percept clocks and native event representations; dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--participant-uid", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        participant = models.Participant.find(uid=options["participant_uid"])
        if participant is None:
            raise CommandError("Requested participant was not found")
        try:
            result = PerceptClockData.index_participant(participant, apply=options["apply"])
        except Exception as exc:
            # Raw paths and parser fragments may contain private source content.
            raise CommandError("Clock indexing failed; no complete result is available ("
                               + type(exc).__name__ + ")") from exc
        self.stdout.write(json.dumps(result))
