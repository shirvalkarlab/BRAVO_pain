"""Keep the Sync Data button working; the single external runner owns nightly work."""
import datetime as dt
import time

from django.core.management.base import BaseCommand, CommandError
from filelock import Timeout
from modules import RCS08ManualSync
from modules.RCS08Preparation import run_preparation, is_preparing


class Command(BaseCommand):
    help = "Process manual RCS08 sync requests; no independent nightly timer."

    def add_arguments(self, parser):
        parser.add_argument("--external-maintenance", action="store_true", default=True,
                            help="Compatibility flag: automatic maintenance is always externally orchestrated.")
        parser.add_argument("--poll-seconds", type=int, default=10)

    def handle(self, *args, **options):
        lock = RCS08ManualSync.scheduler_lock()
        try:
            lock.acquire()
        except Timeout as exc:
            raise CommandError("The RCS08 manual request worker is already running.") from exc
        try:
            self.run_scheduler(**options)
        finally:
            lock.release()

    def run_scheduler(self, **options):
        RCS08ManualSync.fail_interrupted_request()
        while True:
            # Leave an explicit request queued while nightly maintenance holds the
            # shared preparation lock. There is never a second concurrent cycle.
            request = None if is_preparing() else RCS08ManualSync.claim_request()
            if request:
                request_id = request["request_id"]
                self.stdout.write(f"Manual RCS08 sync {request_id} starting at {dt.datetime.now(dt.timezone.utc).isoformat()}")
                try:
                    results = run_preparation(deadline=time.time() + 7200, mode="Manual")
                except Exception as exc:
                    RCS08ManualSync.fail_request(request_id, str(exc))
                    self.stderr.write(f"Manual RCS08 sync {request_id} failed ({type(exc).__name__}: {exc})")
                else:
                    RCS08ManualSync.complete_request(request_id, results)
                    self.stdout.write(f"Manual RCS08 sync {request_id} completed at {dt.datetime.now(dt.timezone.utc).isoformat()}")
            time.sleep(max(options["poll_seconds"], 10))
