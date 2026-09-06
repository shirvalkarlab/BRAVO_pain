"""Does the chosen frequency band predict pain the same way whatever the stimulation is doing?

WHY THE CLOSED-LOOP REPORT NEEDS THIS AND HAS NEVER HAD IT. Closed-loop stimulation works by
watching the power in one frequency band on one electrode and turning the current up or down when
that power crosses a value programmed into the stimulator. That only makes sense if the band means
the same thing about the patient's pain whatever current is being delivered at the time. If the
band predicts pain well when the stimulator is off but predicts nothing once the current is up, then
the moment closed loop starts changing the current it destroys the very signal it is steering by,
and the device will chase its own tail.

The Biomarkers module has been able to answer this question for some time. Nothing in
ClosedLoopDeployment or StimOptimizer imported the answer, so it appeared on the biomarkers page and
never reached the page where somebody decides whether to switch closed loop on. This file is the
one-way bridge: it imports from Biomarkers, and Biomarkers must never import it back, because that
would be a loop neither module could load out of.

THE ANSWER HAS FOUR POSSIBLE VALUES AND NONE OF THEM IS A YES-OR-NO. Three come from the statistics
and the fourth means the question was never asked:

  "behaves the same"      The band's relationship to pain was shown to be near enough identical
                          across the three stimulation states that any remaining difference is
                          smaller than the difference we declared in advance would matter.
  "behaves differently"   The band's relationship to pain demonstrably changes with the stimulation.
  "cannot tell"           The data cannot distinguish a band that behaves the same from one that
                          behaves differently. This is not a pass and it is not a failure. It is the
                          honest answer when there is too little data, and it is the most common
                          answer in a study this size.
  "not tested"            The test could not be run at all, because a piece it needs was missing.

WHY "CANNOT TELL" IS GIVEN A NAME OF ITS OWN, AND WHY THERE IS NO TRUE-OR-FALSE FIELD ANYWHERE IN
THIS FILE. The original way of answering this question was to run the test and call the band stable
whenever the test failed to reach significance. That reads "stable" precisely when the test had no
power to find anything, which is exactly the situation in which a false reassurance costs the most,
because a value is about to be programmed into a device that delivers current to a person's brain.
This project has been damaged more than once by that collapse, in both directions: "cannot tell"
being written up as a pass, and "cannot tell" being written up as "behaves differently".

So this file deliberately does NOT offer a boolean. There is no ``.stable``, no ``.ok``, no
``.passed``. If such a field existed, sooner or later somebody would write ``if finding.stable:``
and every "cannot tell" in the study would silently become a failure. A caller who wants a yes or a
no has to look at ``answer`` and handle all four values, which is the point. The one convenience
offered is ``answer_is("cannot tell")``, which reads the same way at the call site without hiding
anything.

WHETHER THIS SHOULD STOP A DEPLOYMENT IS NOT DECIDED HERE. It would be easy to make "behaves
differently" a blocking failure and, on the face of it, sensible. It is not this file's call to
make. The blocking rules in this module are the documented device rules, each one traceable to a
page of a Medtronic manual; this is a statistical finding about one participant's data and it has no
such warrant. So the result is reported with its blocking status recorded as undecided, and the
choice is left to the PI. Nothing here fails a report or removes a candidate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from Biomarkers.routines.analytics import (
    STABILITY_EQUIVALENCE_MARGIN_LOG_OR,
    band_stim_stability,
    stability_equivalence,
)

#: The four things this file is allowed to say. Anything else is a bug, and __post_init__ raises
#: rather than letting an unrecognised word travel to a page a clinician reads.
ANSWERS = ("behaves the same", "behaves differently", "cannot tell", "not tested")

#: Translation from the words the Biomarkers test uses to the words above. Kept as data so that a
#: reader can see the whole mapping at once, and so a new word appearing upstream turns into a loud
#: failure here instead of being quietly treated as one of the existing answers.
_FROM_BIOMARKERS = {
    "stable": "behaves the same",
    "stim-dependent": "behaves differently",
    "inconclusive": "cannot tell",
}

#: What goes in the report where a blocking decision would normally sit. A phrase rather than a
#: true-or-false value, because both true and false would be claims this file has no standing to
#: make, and false in particular would read on the page as "this was checked and it was fine".
BLOCKING_STATUS = "not decided - reported for the PI to rule on, blocks nothing today"


@dataclass(frozen=True)
class BandStabilityFinding:
    """One answer, for one electrode and one frequency band, ready to put on the report.

    Every number that went into the answer is carried alongside it, because a reader who is being
    asked to trust a four-word verdict about a device that actuates should be able to see how much
    data stood behind it and how wide the remaining uncertainty was.
    """
    #: Which electrode's signal was used, in the device's own naming, e.g. ZERO_THREE_RIGHT.
    electrode: str
    #: The middle of the frequency band, in Hz, and how wide the band is.
    band_center_hz: float
    band_width_hz: float
    #: One of ANSWERS. There is no boolean beside it, on purpose; see the note at the top of the file.
    answer: str
    #: A plain sentence saying why the answer came out that way, safe to print on the page as is.
    reason: str
    #: False when the test could not be run at all, in which case `answer` is "not tested".
    test_ran: bool
    #: How large a difference between stimulation states we declared in advance would matter. The
    #: answer "behaves the same" means the remaining difference was shown to be smaller than this,
    #: so the number is part of the claim rather than a setting.
    declared_margin: float
    #: The biggest difference actually seen between two stimulation states, and the interval around
    #: it. When that interval is wider than the declared margin the answer is "cannot tell".
    largest_difference: float | None = None
    difference_interval: tuple | None = None
    #: The chance of seeing a difference this large if the band really did behave identically. Kept
    #: because it is what the test reports, NOT because a small value here is a verdict on its own.
    p_value: float | None = None
    #: How much data the answer rests on: measurements used, independent blocks of time they came
    #: from, how many of the three stimulation states could be compared, and how many measurements
    #: sat in each state.
    n_measurements: int | None = None
    n_time_blocks: int | None = None
    n_states_compared: int | None = None
    measurements_per_state: dict = field(default_factory=dict)
    #: Two warnings that change how much the answer is worth, both from the Biomarkers test.
    #: The first is true when the stimulation rate changed at the same times as the current did, so
    #: the test is partly answering a question about rate rather than about current. The second is
    #: how far this band sits from the nearest frequency where a multiple of the stimulation rate
    #: folds back into the recording, where power is partly the stimulator's own artifact.
    rate_moved_with_current: bool | None = None
    distance_to_nearest_artifact_hz: float | None = None
    #: Recorded on the finding rather than assumed by the reader; see BLOCKING_STATUS.
    blocking_status: str = BLOCKING_STATUS

    def __post_init__(self):
        if self.answer not in ANSWERS:
            raise ValueError(f"answer must be one of {ANSWERS}, got {self.answer!r}")
        if self.answer == "not tested" and self.test_ran:
            raise ValueError('answer "not tested" cannot be paired with test_ran=True')
        if self.answer != "not tested" and not self.test_ran:
            raise ValueError(f'answer {self.answer!r} requires test_ran=True')

    def answer_is(self, what: str) -> bool:
        """Ask about one specific answer by name, e.g. ``finding.answer_is("cannot tell")``.

        Offered so that a caller reads as cleanly as it would with a boolean field without gaining
        one. Asking about a word that is not one of the four is a mistake worth hearing about, not
        something to answer False to, because ``answer_is("stable")`` returning False would look
        exactly like a band that is not stable.
        """
        if what not in ANSWERS:
            raise ValueError(f"{what!r} is not one of {ANSWERS}")
        return self.answer == what

    def headline(self) -> str:
        """One line for the top of the report, which always names the answer in full."""
        return (f"{self.electrode} at {self.band_center_hz:g} Hz "
                f"({self.band_width_hz:g} Hz wide): {self.answer} under stimulation")

    def as_payload(self) -> dict:
        """The finding as plain data for the report, with the answer spelled out in words.

        No key in here is a true-or-false summary of the answer, so a page or a downstream consumer
        cannot pick one up and lose the difference between "cannot tell" and a pass.
        """
        return {
            "electrode": self.electrode,
            "band_center_hz": self.band_center_hz,
            "band_width_hz": self.band_width_hz,
            "answer": self.answer,
            "reason": self.reason,
            "test_ran": self.test_ran,
            "declared_margin": self.declared_margin,
            "largest_difference": self.largest_difference,
            "difference_interval": (list(self.difference_interval)
                                    if self.difference_interval is not None else None),
            "p_value": self.p_value,
            "n_measurements": self.n_measurements,
            "n_time_blocks": self.n_time_blocks,
            "n_states_compared": self.n_states_compared,
            "measurements_per_state": dict(self.measurements_per_state or {}),
            "rate_moved_with_current": self.rate_moved_with_current,
            "distance_to_nearest_artifact_hz": self.distance_to_nearest_artifact_hz,
            "blocking_status": self.blocking_status,
            "answers_possible": list(ANSWERS),
        }


def _not_tested(electrode, center_hz, width_hz, why, margin):
    return BandStabilityFinding(
        electrode=str(electrode), band_center_hz=float(center_hz), band_width_hz=float(width_hz),
        answer="not tested", test_ran=False, declared_margin=float(margin),
        reason=f"the test could not be run: {why}")


def finding_from_stability_result(result, electrode, center_hz, *, band_width_hz=5.0,
                                 margin=STABILITY_EQUIVALENCE_MARGIN_LOG_OR):
    """Turn what the Biomarkers test returned into a finding for the closed-loop report.

    Split out from ``assess_band_stability`` so that a caller who already has the Biomarkers result
    in hand -- the biomarkers page computes it for its own display -- can reuse it instead of paying
    for the model fits a second time, and so that the translation can be tested without needing R
    installed.

    ``margin`` says how large a difference between stimulation states would have to be before we
    would call the band unstable. When it differs from the margin the supplied result was built
    with, the three-way answer is worked out again from the same fitted slopes by calling
    ``stability_equivalence`` directly. That re-decides the question without refitting anything,
    which is the whole reason this file imports that function as well as the test itself.
    """
    width = float(band_width_hz)
    if not isinstance(result, dict) or not result.get("available"):
        why = (result or {}).get("reason", "no reason given") if isinstance(result, dict) \
            else "the test returned nothing usable"
        return _not_tested(electrode, center_hz, width, why, margin)

    equivalence = result.get("equivalence") or {}
    p_value = result.get("lrt_p")
    # Re-decide against the caller's margin when it is not the one already used. The slopes are
    # already fitted, so this is arithmetic on numbers we have, not another pass over the data.
    if equivalence and abs(float(equivalence.get("margin_log_or", margin)) - float(margin)) > 1e-12:
        equivalence = stability_equivalence(result.get("slope_by_era") or {}, p_value, margin=margin)

    verdict = equivalence.get("verdict", result.get("stability_verdict"))
    if verdict not in _FROM_BIOMARKERS:
        # An unrecognised word upstream must not be guessed at. Saying "not tested" is the only
        # honest option: we genuinely do not know what was concluded.
        return _not_tested(electrode, center_hz, width,
                           f"the biomarkers test returned an answer this report does not "
                           f"recognise ({verdict!r})", margin)
    answer = _FROM_BIOMARKERS[verdict]

    rate = result.get("rate") or {}
    counts = result.get("era_counts") or {}
    return BandStabilityFinding(
        electrode=str(electrode),
        band_center_hz=float(center_hz),
        band_width_hz=width,
        answer=answer,
        reason=str(equivalence.get("reason", "")) or "no reason given by the test",
        test_ran=True,
        declared_margin=float(equivalence.get("margin_log_or", margin)),
        largest_difference=equivalence.get("max_abs_diff_log_or"),
        difference_interval=(tuple(equivalence["ci"]) if equivalence.get("ci") else None),
        p_value=p_value,
        n_measurements=result.get("n"),
        n_time_blocks=result.get("n_clusters"),
        n_states_compared=equivalence.get("n_eras_compared"),
        measurements_per_state={
            "stimulation off": counts.get("OFF"),
            "low current": counts.get("LOW"),
            "high current": counts.get("HIGH"),
        },
        rate_moved_with_current=(rate.get("rate_confounded_with_era")
                                 if rate.get("available") else None),
        distance_to_nearest_artifact_hz=(rate.get("band_near_harmonic_hz")
                                         if rate.get("available") else None),
    )


def assess_band_stability(td_detail, electrode, center_hz, stim_series=None, *,
                          band_width_hz=5.0, rate_series=None,
                          margin=STABILITY_EQUIVALENCE_MARGIN_LOG_OR, **kwargs):
    """Run the Biomarkers test for one electrode and band and return a finding for the report.

    Every argument is passed straight through to ``band_stim_stability``; nothing about how the test
    works is reimplemented here, so the number on the closed-loop page and the number on the
    biomarkers page can never drift apart. Supplying ``rate_series`` is worth the trouble: without
    it the test cannot see whether the stimulation rate was changing at the same moments as the
    current, and a difference caused by a rate change would be reported as a difference caused by
    the current.

    A failure inside the test is caught and returned as "not tested" rather than raised, because a
    report that lists every other check is more use to a clinician than a page that will not load.
    """
    try:
        result = band_stim_stability(
            td_detail, electrode, float(center_hz), stim_series,
            band_width_hz=float(band_width_hz), rate_series=rate_series,
            equivalence_margin_log_or=float(margin), **kwargs)
    except Exception as e:                                   # noqa: BLE001
        return _not_tested(electrode, center_hz, band_width_hz,
                           f"the test raised {type(e).__name__}: {e}", margin)
    return finding_from_stability_result(result, electrode, center_hz,
                                        band_width_hz=band_width_hz, margin=margin)


def summarise(findings) -> dict[str, Any]:
    """Count the answers across several electrode-and-band pairs, for the top of the report.

    Every one of the four answers is present in the count even when it is zero, so a page reading
    this cannot show three categories on one participant and four on another, and a reader can see
    at a glance that "cannot tell" was among the options rather than wondering whether it was.
    """
    findings = list(findings or [])
    counts = {a: 0 for a in ANSWERS}
    for f in findings:
        counts[f.answer] += 1
    return {
        "n_assessed": len(findings),
        "counts_by_answer": counts,
        "answers_possible": list(ANSWERS),
        "blocking_status": BLOCKING_STATUS,
        "note": ("\"cannot tell\" means the data could not settle the question. It is neither a "
                 "pass nor a failure, and it must not be shown as either."),
    }
