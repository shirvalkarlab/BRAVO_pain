"""StimOptimizer — Bayesian optimization of DBS stimulation parameters against pain outcomes.

Searches (frequency, amplitude) on a discrete grid using a Gaussian-process surrogate over a
composite pain objective, under a separately modelled safety constraint, with a parallel
preference model fitted from forced binary comparisons. Batch designs for both within-visit and
between-visit evaluation.

Layout, following the Biomarkers module precedent:

    OBJECTIVE_SPEC.md         pre-registered objective, stopping rule and safety thresholds
    routines/objective.py     composite J, side-effect ladder, warm-start observation variance
    routines/surrogate.py     ParameterGrid, ObjectiveGP (fixed-noise), SafetyGP (monotone mean)
    routines/preference.py    PreferenceGP (pairwise probit, Laplace)
    routines/acquisition.py   EI / UCB, safe set, batch selection, dual stopping rule
    routines/design.py        exposure-epoch construction from device JSONs and PROs
    routines/plots.py         posterior surface, explore/exploit, trajectory, dual-model, coverage
    adapter.py                BRAVO Therapy/PRO records -> epoch design matrix
    pipeline.py               one-patient, one-batch-decision runner

Library mode only for now: no Django endpoint and no React view, same staging the Biomarkers
module used. Read OBJECTIVE_SPEC.md before changing any threshold — the thresholds are
pre-registered and amendments are logged there.

Deferred, and deliberately so: nonstationarity. The surrogate inflates observation variance with
age as an interim mitigation, but the time-varying formulation (TV-BayesOpt style forgetting
kernel, Fleming et al. 2023 doi:10.1371/journal.pcbi.1011674; adaptive recalibration, Aiello
et al. 2023 doi:10.1088/1741-2552/acc975) is not implemented. Neither has prospective chronic
human validation in the literature either.
"""

# ONE MODULE OBJECT UNDER BOTH IMPORT SPELLINGS (`modules.StimOptimizer` in the container, `StimOptimizer` on the
# host suite). Without this, a process with both roots on the path -- every gunicorn worker --
# loads two copies of every submodule: two sets of in-process memos and two copies of every
# module-level switch (review C4, 2026-09-12; decision 143). `DecodeCommon.import_alias` says how.
try:
    from modules.DecodeCommon.import_alias import alias_both_spellings as _alias_both_spellings
except ImportError:                                   # the host suite's root
    from DecodeCommon.import_alias import alias_both_spellings as _alias_both_spellings
_alias_both_spellings(__name__)
del _alias_both_spellings
