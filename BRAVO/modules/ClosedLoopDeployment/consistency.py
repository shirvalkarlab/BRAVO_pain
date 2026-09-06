"""Do the three edges tell one story, and how confident can we be that they do?

An edge-by-edge review is not enough. Each edge can be individually plausible while the three
together describe something impossible — for instance a band whose power RISES with amplitude, which
also predicts MORE pain, in a therapy that REDUCES pain. Any two of those are unremarkable; all
three at once mean at least one estimate is wrong, or the triangle model does not apply.

THE COHERENCE CONDITION. Writing s(E) for the sign of an edge, the indirect path through band power
is s(E1) * s(E2), and the total effect of amplitude on pain is s(E3). The triangle is coherent when
these agree. That is a necessary condition, not a sufficient one: agreement is consistent with the
band mediating the therapy, but it is also consistent with the band being a bystander correlated
with something that does. Coherence is therefore a screening gate that can REFUSE a candidate, never
a demonstration that the candidate works.

WHY A BOOTSTRAP RATHER THAN THREE SEPARATE TESTS. Each sign carries its own uncertainty, and the
signs are not independent — the same recordings and the same ratings enter more than one edge. The
probability that the PATTERN holds is therefore not the product of three individual probabilities.
Resampling the shared cluster and recomputing all three edges inside each replicate keeps that
dependence intact, which is the only way the resulting probability means what it says.
"""
from __future__ import annotations

import numpy as np

from .types import CoherenceReport


def expected_pattern_for_dual_threshold():
    """The sign pattern a deployable Dual Threshold candidate must show, and why.

    CORRECTED 2026-09-03. An earlier version of this docstring said the device ramps amplitude DOWN
    when band power rises above the upper threshold. That is backwards. The white paper (p. 13,
    quoted in ``StimOptimizer/routines/percept_adaptive.py``) states: "When the LFP passes above the
    upper threshold, the stimulation amplitude slowly ramps UP. When the LFP passes below the lower
    threshold, the stimulation amplitude slowly ramps down." The required signs below are unchanged,
    because they never depended on the erroneous sentence, but the reasoning is recorded correctly
    now so that a reader deriving the requirement afresh does not reach the opposite conclusion.

    The device's design assumption, stated in the same passage, is that "High LFP is associated with
    lower stimulation and lower LFP is associated with higher stimulation" — that is, band power
    FALLS as amplitude rises. High power is therefore read by the device as evidence that
    stimulation is currently insufficient, which is why it responds by ramping up. For that to be
    therapeutic rather than merely self-consistent, high band power must also indicate worse pain,
    and more amplitude must relieve it. Those requirements fix all three signs:

      E1 < 0   power falls as amplitude rises, which is the assumption the control law hard-codes.
               A band with E1 > 0 makes the loop POSITIVE feedback: power is high, the device ramps
               amplitude up, higher amplitude drives the power higher still, and the device ramps up
               again — bounded only by the clinician's amplitude limits rather than by the
               physiology. This is the single most important gate in the module.
      E2 > 0   higher band power indicates more pain, so crossing the upper threshold is a signal
               that the patient needs more therapy.
      E3 < 0   higher amplitude gives less pain, i.e. the therapy works at all.

    Then s(E1) * s(E2) = -1 = s(E3), which is coherent.
    """
    return {"E1": -1, "E2": +1, "E3": -1,
            "why": ("Dual Threshold ramps amplitude UP when band power rises above the upper "
                    "threshold (white paper p. 13), because the control law assumes power FALLS as "
                    "amplitude rises and therefore reads high power as insufficient stimulation. A "
                    "band whose power instead RISES with amplitude closes a positive-feedback loop: "
                    "the device ramps up, power rises further, and it ramps up again, bounded only "
                    "by the amplitude limits.")}


def signs_coherent(e1, e2, e3):
    """None when any sign is unresolved, because an unresolved edge cannot make a pattern hold.

    Returning None rather than False matters: False would say the triangle is contradictory, which
    is a finding, whereas None says it has not been established, which is the honest state of an
    interval that spans zero.
    """
    if not (e1.resolved and e2.resolved and e3.resolved):
        return None
    return (e1.sign * e2.sign) == e3.sign


def p_coherent(fit_edges, cluster_ids, *, n_boot=1000, seed=0):
    """Bootstrap probability that the sign pattern holds, resampling the shared cluster.

    ``fit_edges`` is a callable taking a list of cluster identifiers and returning
    ``(E1, E2, E3)`` re-estimated on just those clusters. It is passed in rather than imported so
    that the resampling stays honest: every replicate must refit all three edges on the SAME
    resampled clusters, and a design where each edge fetched its own data could not guarantee that.
    """
    ids = np.asarray(list(cluster_ids), dtype=object)
    if ids.size < 3:
        return CoherenceReport(None, None, n_boot=0, cluster_unit="",
                               note=f"only {ids.size} clusters; a cluster bootstrap needs at least "
                                    "three to say anything")
    rng = np.random.default_rng(seed)
    hits, usable = 0, 0
    for _ in range(int(n_boot)):
        pick = rng.choice(ids, size=ids.size, replace=True)
        try:
            a, b, c = fit_edges(list(pick))
        except Exception:
            continue
        ok = signs_coherent(a, b, c)
        if ok is None:
            usable += 1          # counted as a draw where the pattern did NOT hold
            continue
        usable += 1
        hits += int(ok)
    if usable == 0:
        return CoherenceReport(None, None, n_boot=0, note="no replicate produced three estimates")
    return CoherenceReport(coherent=None, p_coherent=hits / usable, n_boot=usable,
                           note=("replicates in which all three edges resolved AND their signs "
                                 "agreed, over replicates that produced three estimates. A "
                                 "replicate with an unresolved edge counts against coherence, "
                                 "because an unresolved edge cannot support the pattern."))


def coherence_report(e1, e2, e3, *, p=None, n_boot=0):
    exp = expected_pattern_for_dual_threshold()
    obs = {k: v.sign for k, v in (("E1", e1), ("E2", e2), ("E3", e3))}
    ok = signs_coherent(e1, e2, e3)
    matches_dual = all(obs[k] == exp[k] for k in ("E1", "E2", "E3")) if None not in obs.values() else None
    note = exp["why"]
    if ok is False:
        note += (" OBSERVED PATTERN IS CONTRADICTORY: the indirect path through band power does not "
                 "agree with the total effect, so at least one edge is wrong or the band does not "
                 "mediate the therapy.")
    elif ok is None:
        note += (" NOT ESTABLISHED: at least one edge's interval spans zero, so the pattern is "
                 "untested rather than refuted.")
    elif not matches_dual:
        note += (" Signs are internally consistent but do NOT match the pattern Dual Threshold "
                 "requires, so the candidate is coherent as physiology and still not deployable.")
    return CoherenceReport(coherent=(bool(ok) and bool(matches_dual)) if ok is not None else None,
                           p_coherent=p, n_boot=n_boot,
                           # Passed as mappings. `str(exp)` produced a Python repr that no
                           # JSON parser can read; see the note on the dataclass fields.
                           expected_pattern=dict(exp), observed_pattern=dict(obs),
                           cluster_unit=e2.cluster_unit, note=note)
