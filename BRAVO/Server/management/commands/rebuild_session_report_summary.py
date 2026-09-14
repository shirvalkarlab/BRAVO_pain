"""Rebuild the per-participant session-report summary from the INGESTED reports, and store it.

WHY THIS EXISTS. The Closed-Loop Deployment device rules read several facts (capture amplitudes,
adaptive limits and status, the device's own artefact verdict, the D32 group shape, the D09
per-bin signal) from a summary of the Medtronic session reports. Until 2026-09-12 that summary was
a file committed next to the module, scanned once on 2026-09-05 from a shared-drive folder and
refreshed by nothing -- so it said 110 Hz and adaptive NOT_CONFIGURED where the device's newest
report says 55 Hz and RUNNING. This command scans the reports the server itself ingested (572
files, 4,079 MB for RCS08, decrypted one at a time) and stores the result in the one cache store
as the raw kind ``session_report_summary``, keyed on the participant's session-report file set.

WHY A COMMAND AND NOT THE REQUEST. The whole-record scan takes minutes; a page request never runs
it. Two callers reach this command: ``ClosedLoopDeployment.device_facts`` starts it detached when a
request finds the stored summary missing or behind its file set, and the daily precompute loop
runs it for every participant.

THE KEY DECIDES WHETHER ANY WORK HAPPENS (decision 26). The file-set signature is one database
query; when the store already holds an entry under it the scan is not paid and the run reports
``already_current``. ``--force`` rebuilds anyway.

USAGE (inside the server container, where the database and the cache files live):
    python manage.py rebuild_session_report_summary --participant <uid>
    python manage.py rebuild_session_report_summary --all
    python manage.py rebuild_session_report_summary --all --json
    python manage.py rebuild_session_report_summary --participant <uid> --force

Exit status is 0 when every participant either stored a summary, was already current, or had no
session reports; 1 when at least one summary was computed and could not be stored or the rebuild
raised -- so a scheduler can alert on a real failure without alerting on a participant with no
reports yet.
"""
import json
import time

from django.core.management.base import BaseCommand

from Server import models
from modules.ClosedLoopDeployment import session_report_facts


class Command(BaseCommand):
    help = "Rebuild and store the session-report summary for one participant or for all."

    def add_arguments(self, parser):
        parser.add_argument("--participant", dest="participant", default=None,
                            help="Participant uid. Omit and pass --all to do every participant.")
        parser.add_argument("--all", dest="do_all", action="store_true",
                            help="Every participant in the database.")
        parser.add_argument("--force", dest="force", action="store_true",
                            help="Rebuild even when the stored summary is already current.")
        parser.add_argument("--json", dest="as_json", action="store_true",
                            help="Emit one JSON object per participant, for a scheduler's log.")

    def handle(self, *args, **opts):
        uids = self._participants(opts)
        if not uids:
            self.stderr.write("no participants selected; pass --participant <uid> or --all")
            return
        failures = 0
        for uid in uids:
            t0 = time.perf_counter()
            result = session_report_facts.rebuild_and_store(uid, force=opts["force"])
            result.setdefault("wall_seconds", round(time.perf_counter() - t0, 3))
            # "No session reports" is a normal outcome and NOT a failure. A summary computed and
            # not stored IS, and so is a raise: both leave every page on the stale copy with
            # nothing on the page to show it.
            if not result.get("stored") and not result.get("already_current") and (
                    "NOT stored" in str(result.get("reason") or "")
                    or str(result.get("reason") or "").startswith("raised")):
                failures += 1
            self._emit(opts, result)
        if failures:
            self.stderr.write(f"{failures} participant(s) failed to store a summary")
            raise SystemExit(1)

    def _participants(self, opts):
        if opts["participant"]:
            return [opts["participant"]]
        if not opts["do_all"]:
            return []
        try:
            return [str(p.uid) for p in models.Participant.objects.all()]
        except Exception as exc:                                 # noqa: BLE001
            self.stderr.write(f"could not list participants: {exc!r}")
            return []

    def _emit(self, opts, payload):
        if opts["as_json"]:
            self.stdout.write(json.dumps(payload, default=str))
            return
        uid = payload.get("participant_uid")
        if payload.get("already_current"):
            self.stdout.write(f"{uid}: already current ({payload.get('n_files')} session reports, "
                              f"newest {payload.get('newest_stamp')}, {payload.get('wall_seconds')} s)")
        elif payload.get("stored"):
            self.stdout.write(f"{uid}: stored a summary of {payload.get('n_files')} session reports "
                              f"(newest {payload.get('newest_stamp')}, "
                              f"{payload.get('n_unreadable')} unreadable) in "
                              f"{payload.get('wall_seconds')} s")
        else:
            self.stdout.write(f"{uid}: nothing stored — {payload.get('reason')}")
