"""The resolution rule, in one place, because four copies of it had already drifted apart.

WHAT THE RULE IS. A recommendation is only honest if the candidate cell beats the setting currently
in force by more than the uncertainty OF THAT DIFFERENCE. Writing ``gain`` for the predicted
improvement and ``sd_diff`` for the standard deviation of the difference, the optimum is resolved
when ``gain > k * sd_diff``.

WHY IT LIVES IN A LEAF MODULE. As of 2026-09-04 this arithmetic appeared in four places and one of
them was wrong in a way that mattered:

  * ``stage1_openloop.SliceResult.sd_of_difference`` — correct.
  * ``pipeline.ArmResult.surface_can_resolve_its_optimum`` — correct since 2026-08-30.
  * ``bravo_service._arm_comparison`` — correct, and serialised for the interface.
  * ``routines.plots._incumbent_verdict`` — WRONG. It compared the gain against
    ``opt_posterior_sd``, the CANDIDATE's posterior standard deviation at the grid minimum, and
    ignored the incumbent's own. That is precisely the criterion the gate was corrected away from
    on 2026-08-30, so the figure headline could print the strong claim on an arm whose optimum the
    module itself reported as unresolved.

    The worked example is the arm that motivated the original fix, ``left_leg__Right``: gain 1.117,
    candidate SD 0.989, incumbent SD 0.923. Against the candidate's SD alone, 1.117 > 0.989 and the
    headline read "predicted 1.12 NRS points better than the incumbent" with no caveat. Against the
    propagated SD of 1.353 the difference is not resolved, which is what the verdict said. A figure
    that overstates what the module's own gate concluded is worse than no figure.

This module has no internal dependencies, so every one of those callers can import it. That matters
because ``stage1_openloop`` imports ``routines.plots``, so the shared arithmetic could not live in
either of them without a cycle.

THE COVARIANCE TERM IS DELIBERATELY OMITTED. The variance of a difference between two Gaussian
process predictions is ``var1 + var2 - 2*cov``, and the joint covariance between the two cells is
not carried. Because nearby cells on a smooth kernel are POSITIVELY correlated, dropping ``-2*cov``
OVERSTATES the variance, which makes the rule conservative: it can withhold a recommendation it
might have supported, but it cannot manufacture one. Tightening it needs ``return_cov=True`` on a
joint prediction.
"""
from __future__ import annotations

import math

#: How many standard deviations of the difference the gain must clear. One is not a significance
#: threshold and is not presented as one; it is a declared, deliberately modest bar, and every
#: figure and payload that applies it reports the multiple alongside the verdict so a reader can
#: disagree with the choice rather than having to infer it.
RESOLUTION_K = 1.0


def sd_of_difference(sd_candidate, sd_incumbent) -> float:
    """Propagated standard deviation of (candidate - incumbent).

    A missing incumbent standard deviation degrades to the candidate's alone rather than raising,
    because some historical payloads predate its being carried; that is strictly less conservative,
    so callers should prefer supplying both.
    """
    try:
        a = float(sd_candidate)
    except (TypeError, ValueError):
        return float("nan")
    try:
        b = float(0.0 if sd_incumbent is None else sd_incumbent)
    except (TypeError, ValueError):
        b = 0.0
    if not math.isfinite(a) or not math.isfinite(b):
        return float("nan")
    return math.sqrt(a * a + b * b)


def is_resolved(gain, sd_candidate, sd_incumbent, k: float = RESOLUTION_K):
    """``True`` / ``False`` / ``None`` — and the three are different answers.

    ``True`` means the gain exceeds ``k`` standard deviations of the difference. ``False`` means it
    was measured and does not, which more exposure at that cell could change. ``None`` means the
    difference could not be FORMED at all, because a propagated standard deviation is zero or
    non-finite — typically a stratum with no data anywhere near the cell being compared. That needs
    the fit repaired rather than more exposure, so collapsing it into ``False`` sends a reader to
    gather data that could not have resolved anything.
    """
    sd_diff = sd_of_difference(sd_candidate, sd_incumbent)
    if not math.isfinite(sd_diff) or sd_diff <= 0:
        return None
    try:
        g = float(gain)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(g):
        return None
    return bool(g > k * sd_diff)


def exposure(n_tests: int, k: float = RESOLUTION_K) -> dict:
    """How often the gain test would pass BY LUCK, given how many times it ran (panel C item 4).

    On a comparison where the candidate is truly no better than the setting in force, the gain
    exceeds ``k`` standard deviations of the difference with the upper-tail probability of a normal
    curve beyond ``k`` -- 0.159 at ``k = 1``. Over ``n_tests`` such comparisons, the chance that at
    least one passes by luck is ``1 - (1 - p) ** n_tests`` if they were independent.

    Both numbers are UPPER BOUNDS on a false recommendation, and the sentence says so: a rate is
    recommended only when the surface is also not flat and the current coverage also passes, and
    comparisons that share data are positively dependent, which lowers the chance of at least one
    false pass below the independent figure. Visibility only: nothing here changes the rule.

    ``n_tests`` counts only comparisons that could be FORMED (a gain check that returned True or
    False). A stratum whose comparison could not be formed was not a test and cannot pass by luck.
    """
    n = int(max(0, n_tests))
    p = 0.5 * math.erfc(float(k) / math.sqrt(2.0))
    if n == 0:
        return {"n_tests": 0, "k": float(k), "false_pass_rate_per_test": p,
                "chance_of_at_least_one_false_pass": None,
                "sentence": ("No comparison against the setting in force could be formed on this "
                             "record, so the rule has not yet been exposed to a chance pass.")}
    fam = 1.0 - (1.0 - p) ** n
    return {"n_tests": n, "k": float(k), "false_pass_rate_per_test": p,
            "chance_of_at_least_one_false_pass": fam,
            "sentence": (f"The \"proven better than today's setting\" comparison ran {n} "
                         f"time{'s' if n != 1 else ''} on this record, once per rate and pulse-width "
                         f"pairing it could be formed for. At {float(k):g} standard deviation, one "
                         f"comparison where nothing is truly better passes by luck about "
                         f"{100 * p:.0f}% of the time, so across all {n} the chance of at least one "
                         f"lucky pass is at most about {100 * fam:.0f}%. That is an upper bound -- a "
                         f"current also needs a surface that is not flat and enough current "
                         f"combinations tried -- and this number changes nothing: it is reported, "
                         f"not corrected for.")}
