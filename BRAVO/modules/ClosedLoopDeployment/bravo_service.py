"""Service layer: the single entry point the BRAVO API calls for Closed-Loop Deployment.

Mirrors `modules/Biomarkers/bravo_service.run_for_participant` and
`modules/StimOptimizer/bravo_service.run_for_participant` — takes the request dict, pulls what it
needs from the platform database, runs the module, and returns a JSON-able dict. This module is the
one place in the package that resolves a participant from the ORM; `adapter.py` and everything under
it stay callable from a plain interpreter with frames in hand.

WHY THIS FILE EXISTS AT ALL, WRITTEN 2026-09-10. The other two analysis modules each had a
`bravo_service.py` and this one did not: the view resolved the participant itself and called
`adapter.report_for_participant` directly. That is not a naming quibble. It meant the module had no
single door, so the two things a door is for — saying what the module promises to return, and
noticing when it cannot — lived in the view instead, mixed in with permission checks.

AND THE NOTICING WAS THE PART THAT FAILED. The view wrapped the whole call in one
`except Exception` and answered HTTP 200 with `{"available": False, "reason": "deployment report
error: " + str(e)}`. That is a reasonable thing for a page to show. It is a terrible thing to be the
ONLY record, and on 2026-09-04 it became exactly that: a module-level import broke the entire
package, every request returned that HTTP 200, and nothing logged it. **It stayed broken for five
days and was found by reading code, not by anything reporting it.**

So the contract here is deliberately two-sided:

  * THE PAGE gets a plain sentence it can render, always, whatever happened.
  * THE LOG gets the exception with its traceback, always, whatever happened.

Neither substitutes for the other. A reason the page shows is seen by whoever is looking at that one
participant; a log line is seen by whoever is asking why something is wrong at all, and those are
rarely the same person at the same moment.

HONESTY CONTRACT. `run_for_participant` never raises. Every return carries `available`, and a False
answer carries a `reason` saying which step could not be taken -- never an empty payload that a
reader has to interpret as either "nothing applies here" or "something broke", which are different
conclusions.
"""
import logging as _logging

_log = _logging.getLogger(__name__)

try:                                                   # container path root
    from modules.ClosedLoopDeployment import adapter as _adapter
except ImportError:                                    # host test-suite path root
    from ClosedLoopDeployment import adapter as _adapter


#: What the view passes through, with the defaults the endpoint documents.
DEFAULT_HEMISPHERE = "Left"
DEFAULT_POWER_SCALE = "power_linear"                   # the device-parity scale of rule D11


def _participant_or_none(participant_uid):
    """Resolve the participant. The ORM import is deferred to call time for the same reason
    `adapter.report_for_participant` defers its sibling-module imports: at module import time the
    Django app registry may not be populated, and the host test suite has no Django at all."""
    from Server import models
    return models.Participant.find(uid=participant_uid)


def run_for_participant(request_data):
    """Build the Closed-Loop Deployment report for one participant. Never raises.

    Inputs, from `request_data`: `ParticipantId` (required), `Candidates` (list of dicts carrying at
    least `channel` and `center_hz`), optional `Hemisphere` and `PowerScale`.

    Output: the adapter's report dict, which always carries `available` and, when that is False, a
    `reason`. A report built for a real participant also carries `cache_status`, so the page can
    state when the data behind it were last assembled.
    """
    participant_uid = (request_data or {}).get("ParticipantId")
    if not participant_uid:
        return {"available": False, "reason": "ParticipantId is required"}

    try:
        participant = _participant_or_none(participant_uid)
    except Exception as exc:                           # noqa: BLE001
        _log.exception("closed-loop: could not resolve participant %s", participant_uid)
        return {"available": False,
                "reason": f"the participant could not be looked up: {exc!r}"}

    if participant is None:
        # Not an error and not logged as one: asking about a participant who is not there is an
        # ordinary thing for a client to do, and it is already visible in the response.
        return {"available": False, "reason": "participant not found"}

    # THE POOLED THREE-SOURCE VIEW ON ITS OWN. The page asks for this AFTER its first figures are
    # up (the PI, 2026-09-11: "prefetch the data after the first figures load"), so it must not
    # rebuild the report: it reads the two stored tables the last full report wrote and groups
    # them. Cheap, and never something the verdict waits for.
    if (request_data or {}).get("ThreeSourcePooled"):
        try:
            return _adapter.three_source_pooled_for_participant(participant)
        except Exception as exc:                       # noqa: BLE001
            _log.exception("closed-loop: the pooled three-source view failed for %s",
                           participant_uid)
            return {"available": False,
                    "reason": f"the pooled three-source view could not be built: {exc!r}"}

    # THE STORED SIMULATION ON ITS OWN (Phase 8): read back after the first figures, never built here.
    if (request_data or {}).get("ClosedLoopSimulation"):
        try:
            _cands = (request_data or {}).get("Candidates") or []
            return _adapter.closed_loop_simulation_for_participant(
                participant, _cands[0] if _cands else None,
                hemisphere=(request_data or {}).get("Hemisphere", DEFAULT_HEMISPHERE))
        except Exception as exc:                       # noqa: BLE001
            _log.exception("closed-loop: the stored simulation could not be read for %s", participant_uid)
            return {"available": False,
                    "reason": f"the stored simulation could not be read: {exc!r}"}

    try:
        return _adapter.report_for_participant(
            participant, request_data,
            candidates=(request_data or {}).get("Candidates"),
            hemisphere=(request_data or {}).get("Hemisphere", DEFAULT_HEMISPHERE),
            power_scale=(request_data or {}).get("PowerScale", DEFAULT_POWER_SCALE))
    except Exception as exc:                           # noqa: BLE001
        # THE LINE THAT WAS MISSING FOR FIVE DAYS. `exception` rather than `warning`, so the
        # traceback goes with it: the failure this replaces was an ImportError raised at module
        # scope, and the name of the module that would not import is only in the traceback.
        _log.exception("closed-loop: the deployment report failed for %s", participant_uid)
        return {"available": False,
                "reason": f"the deployment report could not be built: {exc!r}"}
