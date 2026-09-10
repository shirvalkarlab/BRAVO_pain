"""Build and store the calibrated band-by-length grid for EVERY pain score, off the request path.

WHY THIS EXISTS (open item 7, the PI's choice: "every score, precomputed"). The grid answers one
pain score per request, because the score is part of the key -- a different score is a different
answer, not a cache miss to be avoided (decision 38). So reading a second score has always meant
paying for a whole rebuild, and the page's own background prefetch (decision 82) paid for it up to
six times over, on a gunicorn worker, on the request path, while a reader waited.

Two callers, the same two shapes the stability grid already uses (decisions 96 and 97):

  * after a grid lands, started detached for the OTHER scores under the settings actually in use,
    so the score a reader switches to is usually already built;
  * on a schedule, at least daily, at the default settings, so a first look at a participant is
    usually served rather than computed.

THE KEY DECIDES WHETHER ANY WORK HAPPENS (decision 26). A pass whose inputs and settings have not
moved loads the stored entry and stops, which is what makes running this daily, for every
participant and every score, cheap rather than wasteful.

USAGE (inside the server container, where the database and the cache files live):
    python manage.py precompute_band_sweeps --participant <uid>
    python manage.py precompute_band_sweeps --all
    python manage.py precompute_band_sweeps --participant <uid> --metrics nrs,vas
    python manage.py precompute_band_sweeps --all --json
    python manage.py precompute_band_sweeps --participant <uid> --dry-run

Exit status is 0 when every participant and score either stored an answer or had nothing to store,
and 1 when at least one COMPUTED AN ANSWER AND FAILED TO STORE IT -- the outcome nothing on any page
will ever show, because the page simply rebuilds on every load and looks entirely fine.
"""
import json
import time

from django.core.management.base import BaseCommand

from Server import models
from modules.Biomarkers import bravo_service


class Command(BaseCommand):
    help = "Build and store the band-by-length grid for every pain score, for one participant or all."

    def add_arguments(self, parser):
        parser.add_argument("--participant", dest="participant", default=None,
                            help="Participant uid. Omit and pass --all to do every participant.")
        parser.add_argument("--all", dest="do_all", action="store_true",
                            help="Every participant in the database.")
        parser.add_argument("--metrics", dest="metrics", default=None,
                            help=("Comma-separated pain-score keys. Default: every score in "
                                  "Biomarkers.bravo_service.BIOMARKER_METRICS. An unknown key is "
                                  "reported and skipped rather than silently computing the "
                                  "default score's grid under its name."))
        parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                            help="Report what would be computed; write nothing.")
        parser.add_argument("--json", dest="as_json", action="store_true",
                            help="Emit one JSON object per participant and score, for a log.")
        parser.add_argument("--request-json", dest="request_json", default=None,
                            help=("The page's own sweep settings, as a JSON object -- the sliders "
                                  "and dropdowns the grid was built under. THE SETTINGS ARE IN THE "
                                  "KEY, so a run started without them for a page sitting on moved "
                                  "sliders stores answers under keys that page never looks up. "
                                  "Only the fields in Biomarkers.bravo_service."
                                  "STABILITY_GRID_SETTING_KEYS are accepted; anything else is "
                                  "dropped, so nothing patient-identifying can arrive this way."))

    def handle(self, *args, **opts):
        request_data = self._request_data(opts)
        metrics = self._metrics(opts)
        uids = self._participants(opts)
        if not uids:
            self.stderr.write("no participants selected; pass --participant <uid> or --all")
            return
        if not metrics:
            self.stderr.write("no pain scores selected; check --metrics")
            return

        failures = 0
        for uid in uids:
            for metric in metrics:
                t0 = time.perf_counter()
                if opts["dry_run"]:
                    self._emit(opts, {"participant_uid": uid, "metric": metric, "dry_run": True,
                                      "note": "would build and store this score's grid"})
                    continue
                try:
                    result = bravo_service.compute_and_store_band_sweep(
                        uid, metric, request_data=dict(request_data))
                except Exception as exc:                         # noqa: BLE001
                    # compute_and_store_band_sweep does not raise, so reaching here means something
                    # outside it did. Counted as a failure rather than swallowed.
                    failures += 1
                    self._emit(opts, {"participant_uid": uid, "metric": metric, "stored": False,
                                      "reason": f"raised {exc!r}",
                                      "wall_seconds": round(time.perf_counter() - t0, 3)})
                    continue

                # "Nothing to store" (no recordings, no pain reports, inputs not nameable) is a
                # normal outcome and is NOT a failure. COMPUTED AND NOT STORED is, and it is the
                # case a scheduler must alert on, because the page keeps working and looks fine
                # while paying for a full rebuild on every single request.
                if (not result.get("stored") and not result.get("already_current")
                        and result.get("n_channels")):
                    failures += 1
                self._emit(opts, result)

        if failures:
            self.stderr.write(f"{failures} grid(s) were computed and could not be stored")
            raise SystemExit(1)

    def _request_data(self, opts):
        """The sweep settings this run should use, filtered to the fields the sweep actually reads.

        FILTERED RATHER THAN TRUSTED, exactly as `compute_stability_grid` filters its own: this
        value arrives on a command line, so only the known setting keys survive, which is what keeps
        a pain-report table or a REDCap field map from being carried in under some other name. A
        malformed value is reported and the run continues on the sweep's own defaults, because a
        scheduled pass that produced nothing over one mistyped argument would be worse than one that
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
        # The score is this command's own argument, never a setting carried in: taking it from here
        # would silently override --metrics and store one score's grid under another's name.
        return {k: v for k, v in parsed.items()
                if k in allowed and k not in ("SweepMetric", "LabelMetric")}

    def _metrics(self, opts):
        known = [m["key"] for m in bravo_service.BIOMARKER_METRICS]
        raw = opts.get("metrics")
        if not raw:
            return known
        asked = [m.strip() for m in str(raw).split(",") if m.strip()]
        unknown = [m for m in asked if m not in known]
        if unknown:
            self.stderr.write(f"unknown pain score(s) {unknown}; known are {known}")
        return [m for m in asked if m in known]

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
        who = f"{payload.get('participant_uid')} / {payload.get('metric')}"
        if payload.get("dry_run"):
            self.stdout.write(f"{who}: {payload['note']}")
        elif payload.get("already_current"):
            self.stdout.write(f"{who}: already current "
                              f"({payload.get('n_channels')} sensing contact pairs)")
        elif payload.get("stored"):
            self.stdout.write(f"{who}: stored {payload.get('n_channels')} sensing contact pairs "
                              f"in {payload.get('wall_seconds')} s")
        elif payload.get("n_channels"):
            self.stderr.write(f"{who}: FAILED — {payload.get('reason')}")
        else:
            self.stdout.write(f"{who}: nothing stored — {payload.get('reason')}")
