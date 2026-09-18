"""The closed-loop timing values the participant's OWN record argues for, per participant.

WHAT THE RECORD CANNOT DECIDE, and every entry said so: the two ramp durations and the blanking
(no measurement separates 4 s from 60 s once the onset filters), and the response of the band to
the stimulation current at all -- every replay runs the controller over the recorded power with a
zero response curve. The titration session (open item 30) is what would supply the gain.

WHERE IT REACHES THE PAGE. Closed-Loop Deployment page, the "Full parameter recommendation" card:
the onset, averaging, transition, blanking and startup-delay rows carry these values with the
sentence below as their reason and the confidence beside it."""
from __future__ import annotations

#: Bumped whenever a value in `RECORD_DERIVED_TIMING_MS` changes for any participant -- folded into
#: `simulation.simulation_signature` (T2, 2026-09-13) so a table edit invalidates the stored
#: closed-loop simulation rather than serving a replay built under the old recommendation.
TABLE_VERSION = "v1_decision150"

#: THE ONE PLACE TO CHANGE A PARTICIPANT'S RECORD-DERIVED TIMING. Participant uid -> field -> ms.
RECORD_DERIVED_TIMING_MS = {}  # Participant-specific values remain in private reviewed storage.

#: One sentence of reason and a confidence per field, from the contest judgement, printed on the card.
RECORD_DERIVED_WHY = {}  # Participant-specific values remain in private reviewed storage.

RECORD_DERIVED_PROVENANCE = ("measured on this participant's own record: six-method contest, "
                             "held-out replay (decision 150, "
                             "artifacts/contest_2026-09-13_SYNTHESIS.md section 3)")



# Aditya canonical compatibility imports/constants.

def for_participant(participant_uid):
    """The record-derived timing for one participant, or ``{}`` when none has been measured.

    Returns a dict of field -> {"value_ms", "why", "confidence", "provenance"}; the caller decides
    what to do with an absent participant (the card falls back to its older derivation and says
    so). Nothing is invented for a participant not in the table.
    """
    table = RECORD_DERIVED_TIMING_MS.get(str(participant_uid) if participant_uid is not None else "")
    if not table:
        return {}
    out = {}
    for k, v in table.items():
        why, conf = RECORD_DERIVED_WHY.get(k, ("", "Low"))
        out[k] = {"value_ms": float(v), "why": why, "confidence": conf,
                  "provenance": RECORD_DERIVED_PROVENANCE}
    return out


# Retained active Aditya interfaces.
