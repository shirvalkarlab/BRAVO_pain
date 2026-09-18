"""The four words the cross-setting stability check may answer with, in one home.

Moved here from `ClosedLoopDeployment/stability.py` on 2026-09-16 (review finding B3, decision 185)
so the Biomarkers grid can print the same answer the Closed-Loop card prints: Biomarkers may not
import ClosedLoopDeployment (that module imports Biomarkers for the test itself, and the reverse
would be a cycle), and typing the words a second time in Biomarkers is how two pages come to
disagree. `ClosedLoopDeployment.stability` keeps its names and binds them to these objects; a test
pins the identity.

The words, and why there are four rather than a yes/no (the full reasoning is on
`ClosedLoopDeployment.stability`):

  "behaves the same"      the band's relationship to pain was shown to be near enough identical
                          across stimulation settings (inside a declared margin)
  "behaves differently"   it demonstrably changes with the stimulation
  "cannot tell"           the data cannot distinguish the two -- the interval is wider than the
                          margin; NOT a pass and NOT a failure
  "not tested"            the test could not be run at all
"""

#: The four things a stability answer may say. Anything else is a bug.
ANSWERS = ("behaves the same", "behaves differently", "cannot tell", "not tested")

#: Translation from the words the Biomarkers test uses (`analytics.stability_equivalence`'s
#: `verdict`) to the words above. Kept as data so a reader sees the whole mapping at once, and so
#: a new word upstream fails loudly (`answer_for_verdict` returns None) instead of being quietly
#: treated as one of the existing answers.
FROM_BIOMARKERS_VERDICT = {
    "stable": "behaves the same",
    "stim-dependent": "behaves differently",
    "inconclusive": "cannot tell",
}


def answer_for_verdict(verdict):
    """The answer word for a Biomarkers verdict word, or None for a word this table does not know."""
    return FROM_BIOMARKERS_VERDICT.get(str(verdict)) if verdict is not None else None
