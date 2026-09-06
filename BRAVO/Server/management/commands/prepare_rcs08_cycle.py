"""Internal child worker; run_rcs08_scheduler owns its deadline supervision."""
import json
import os
from pathlib import Path
import time

from django.core.management.base import BaseCommand, CommandError
from modules import RCS08Sync, ReportCache, ResearchPrewarm
from modules.RCS08Preparation import start_deadline_watchdog


class Command(BaseCommand):
    help = "Internal bounded RCS08 sync and common-report preparation worker."

    def add_arguments(self, parser):
        parser.add_argument("--deadline", type=float, required=True)
        parser.add_argument("--result", required=True)

    def handle(self, *args, **options):
        deadline = options["deadline"]
        start_deadline_watchdog(deadline)
        def require_time(stage):
            if time.time() >= deadline - 5:
                raise CommandError(f"Preparation window ended before {stage}.")
            self.stdout.write(f"Preparing {stage}")
            self.stdout.flush()
        require_time("source sync")
        results = RCS08Sync.run_sync(create_participant=True)
        participant = RCS08Sync.resolve_participant()
        require_time("standard reports")
        results["reports"] = ReportCache.prewarm_participant(participant)
        self.stdout.write("Preparing optional pain scores and data availability if budget remains")
        results["research"] = ResearchPrewarm.queue_defaults(participant, deadline=deadline - 5)
        while results["research"].get("status") == "pending":
            require_time("queued common research views")
            time.sleep(min(ResearchPrewarm.POLL_SECONDS, max(0, deadline - time.time() - 5)))
            ResearchPrewarm.poll_pending()
            results["research"] = ResearchPrewarm._summary(ResearchPrewarm._read(ResearchPrewarm._path(participant.uid)))
        output = Path(options["result"])
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(results, sort_keys=True))
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
        self.stdout.write("Preparation complete")
