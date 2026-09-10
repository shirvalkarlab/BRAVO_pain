"""Compute and store the cross-setting-stability grid for the calibrated heat map.

WHY THIS IS A MANAGEMENT COMMAND RATHER THAN A THREAD. `bravo_service.stability_grid_for_participant`
parallelises across cores by forking, and forking is only safe from a process that has not yet
started rpy2's embedded R. A gunicorn worker that has already answered a single-candidate request
HAS started it, so a background thread inside that worker would silently fall back to the serial
path. Measured on RCS08: 8.2 s forked against 78.3 s serial, for the identical answers. A separate
process is what makes the fast path reachable, so both callers go through this command:

  * after the Biomarkers page's own grid lands, launched detached so the page is never held up;
  * on a schedule, at least daily, so the answer is usually already there before anyone opens
    anything.

THE KEY DECIDES WHETHER ANY WORK HAPPENS (decision 26). A run whose inputs and settings have not
moved since the last one loads the stored entry and stops -- which is what makes running this daily,
for every participant, cheap rather than wasteful. `--force` overrides that for a deliberate rebuild.

USAGE (inside the server container, where the database and the cache files live):
    python manage.py compute_stability_grid --participant <uid>
    python manage.py compute_stability_grid --all
    python manage.py compute_stability_grid --all --force        # rebuild even if current
    python manage.py compute_stability_grid --all --workers 4    # cap the process pool
    python manage.py compute_stability_grid --participant <uid> --dry-run

Exit status is 0 when every participant either stored an answer or had nothing to store, and 1 when
at least one FAILED -- so a scheduler can alert on a real failure without alerting on a participant
who simply has no recordings yet.
"""
import json
import time

from django.core.management.base import BaseCommand

from Server import models
from modules.Biomarkers import bravo_service


class Command(BaseCommand):
    help = "Compute and store the cross-setting-stability grid for one participant or for all."

    def add_arguments(self, parser):
        parser.add_argument("--participant", dest="participant", default=None,
                            help="Participant uid. Omit and pass --all to do every participant.")
        parser.add_argument("--all", dest="do_all", action="store_true",
                            help="Every participant in the database.")
        parser.add_argument("--force", dest="force", action="store_true",
                            help="Recompute even when the stored entry is already current.")
        parser.add_argument("--workers", dest="workers", type=int, default=None,
                            help="Processes to use. Default: this machine's usable core count.")
        parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                            help="Report what would be computed; write nothing.")
        parser.add_argument("--json", dest="as_json", action="store_true",
                            help="Emit one JSON object per participant, for a scheduler's log.")
        parser.add_argument("--request-json", dest="request_json", default=None,
                            help=("The page's own sweep settings, as a JSON object -- the sliders "
                                  "and dropdowns the grid was built under. THE SETTINGS ARE IN THE "
                                  "KEY, so a run started without them for a page sitting on moved "
                                  "sliders stores an answer under a key that page never looks up. "
                                  "Only the fields in Biomarkers.bravo_service."
                                  "STABILITY_GRID_SETTING_KEYS are accepted; anything else is "
                                  "dropped, so nothing patient-identifying can arrive this way."))

    def handle(self, *args, **opts):
        request_data = self._request_data(opts)
        uids = self._participants(opts)
        if not uids:
            self.stderr.write("no participants selected; pass --participant <uid> or --all")
            return

        failures = 0
        for uid in uids:
            t0 = time.perf_counter()
            if opts["dry_run"]:
                self._emit(opts, {"participant_uid": uid, "dry_run": True,
                                  "note": "would compute and store the stability grid"})
                continue
            try:
                result = bravo_service.compute_and_store_stability_grid(
                    uid, request_data=dict(request_data), workers=opts["workers"],
                    force=opts["force"])
            except Exception as exc:                             # noqa: BLE001
                # compute_and_store_stability_grid does not raise, so reaching here means something
                # outside it did. Counted as a failure rather than swallowed.
                failures += 1
                self._emit(opts, {"participant_uid": uid, "stored": False,
                                  "reason": f"raised {exc!r}",
                                  "wall_seconds": round(time.perf_counter() - t0, 3)})
                continue

            # "Nothing to store" is a normal outcome (no recordings, inputs not nameable) and is
            # NOT a failure. A computed-but-unstored answer is, and so is a run that stopped early
            # and therefore kept the previous answer instead of replacing it -- that one is exactly
            # the case a scheduler must be able to alert on, because nothing on any page will show
            # it: the page keeps serving the older answer, correctly, and looks fine.
            if not result.get("stored") and (
                    "not stored" in str(result.get("reason") or "") or result.get("stopped_early")):
                failures += 1
            self._emit(opts, result)

        if failures:
            self.stderr.write(f"{failures} participant(s) failed to store a computed grid")
            raise SystemExit(1)

    def _request_data(self, opts):
        """The sweep settings this run should use, filtered to the fields the sweep actually reads.

        FILTERED RATHER THAN TRUSTED. This value arrives on a command line, so it is treated as
        input: only the known setting keys survive, which is what keeps a pain-report table or a
        REDCap field map from being carried in under some other name. A malformed value is reported
        and the run continues on the sweep's own defaults rather than failing -- a scheduled run
        that produced nothing because one argument was mistyped would be worse than one that
        produced the default answer.
        """
        raw = opts.get("request_json")
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception as exc:                                 # noqa: BLE001
            self.stderr.write(f"--request-json could not be read ({exc!r}); using defaults")
            return {}
        if not isinstance(parsed, dict):
            self.stderr.write("--request-json is not a JSON object; using defaults")
            return {}
        allowed = set(bravo_service.STABILITY_GRID_SETTING_KEYS)
        dropped = sorted(k for k in parsed if k not in allowed)
        if dropped:
            self.stderr.write(f"--request-json: ignoring unknown field(s) {dropped}")
        return {k: v for k, v in parsed.items() if k in allowed}

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
        if payload.get("dry_run"):
            self.stdout.write(f"{payload['participant_uid']}: {payload['note']}")
            return
        if payload.get("already_current"):
            self.stdout.write(
                f"{payload['participant_uid']}: already current "
                f"({payload.get('n_available')} of {payload.get('n_points')} points answered)")
        elif payload.get("stored"):
            self.stdout.write(
                f"{payload['participant_uid']}: stored {payload.get('n_available')} of "
                f"{payload.get('n_points')} points in {payload.get('wall_seconds')} s")
        elif payload.get("stopped_early"):
            self.stderr.write(f"{payload['participant_uid']}: FAILED — {payload.get('reason')}")
        else:
            self.stdout.write(f"{payload['participant_uid']}: nothing stored — "
                              f"{payload.get('reason')}")
