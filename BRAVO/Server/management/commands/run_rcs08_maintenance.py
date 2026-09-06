"""Single nightly runner's one-shot data phase after reviewed source updates."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from modules.RCS08Preparation import run_preparation


def maintenance_deadline(now, requested=None):
    local = now.astimezone(ZoneInfo("America/Los_Angeles"))
    start = local.replace(hour=3, minute=0, second=0, microsecond=0)
    end = local.replace(hour=7, minute=0, second=0, microsecond=0)
    if not start <= local < end:
        raise CommandError("Automatic maintenance runs only 03:00–07:00 America/Los_Angeles; no catch-up was started.")
    deadline = min(end.timestamp(), float(requested) if requested is not None else end.timestamp())
    if deadline - now.timestamp() <= 5:
        raise CommandError("No maintenance time remains; no worker was started.")
    return deadline


class Command(BaseCommand):
    help = "One-shot nightly sync/common-view preparation, restricted to 03:00–07:00 Pacific."

    def add_arguments(self, parser):
        parser.add_argument("--deadline-epoch", type=float,
                            help="Optional earlier deadline after source-update work; never extends past 07:00 Pacific.")

    def handle(self, *args, **options):
        deadline = maintenance_deadline(dt.datetime.now(dt.timezone.utc), options.get("deadline_epoch"))
        try:
            result = run_preparation(deadline=deadline, mode="Nightly")
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, sort_keys=True))
