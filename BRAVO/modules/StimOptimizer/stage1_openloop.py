"""Stage 1 of the two-stage architecture: the OPEN-LOOP search, whose product is a frozen
configuration.

WHY THIS IS A SEPARATE STAGE AND NOT ONE DIMENSION OF A FLAT SEARCH
-------------------------------------------------------------------
The device decides the shape of this problem, not the statistics. ``routines/percept_adaptive.py``
records the constraint verbatim from the A610 Clinician Programming Guide (pp. 34-35): "Pulse width
and rate cannot be adjusted once BrainSense has been set up for either hemisphere." To change either
one afterwards, BrainSense has to be removed from the group, which discards the closed-loop
configuration. Closed-loop therapy therefore adapts AMPLITUDE ONLY, with rate and pulse width held
at whatever values were in force when sensing was configured.

That makes the open-loop search a PREREQUISITE rather than an alternative. A single flat optimizer
over rate and amplitude, which is what ``pipeline.run`` implements, models a decision the hardware
will not let a clinician make: it can propose moving the rate at a point in the programme where the
rate is already frozen. Stage 1 exists to finish that decision and hand on a configuration that
cannot be revisited, and to state plainly whether the configuration it hands on was chosen on
evidence or merely inherited.

WHAT STAGE 1 SEARCHES
---------------------
Rate x pulse width x amplitude, per hemisphere. The existing surrogate
(``routines/surrogate.ParameterGrid``) is a two-dimensional (rate, amplitude) grid, and this module
is not permitted to change it, so the third dimension is represented as a set of PULSE-WIDTH
STRATA: one (rate, amplitude) surface per pulse-width level that has enough epochs to fit, all
referenced to the same incumbent so their posterior means are on one common scale. The surrogate
(``ObjectiveGP``, ``SafetyGP``), the acquisition functions and the stopping rule are called as they
stand; nothing here re-implements them.

Stratifying rather than fitting a single three-dimensional kernel is a real modelling choice with a
real cost, and the cost is that no information is borrowed BETWEEN pulse-width levels. That is the
conservative direction: a shared length scale across pulse width would smooth the strata towards
each other and make a pulse-width difference look better determined than the design supports. In
this record the design gives an independent reason to prefer no borrowing, which
:func:`pulse_width_design_audit` measures rather than assumes: rate and pulse width were changed
together, so most (rate, pulse width) combinations were never delivered at all.

WHY THE COMMON INCUMBENT MATTERS, AND WHY ``build_context`` IS NOT USED PER STRATUM
----------------------------------------------------------------------------------
``routines/objective.build_objective`` defines ``J_pain`` as the primary pain item minus its value
at the incumbent epoch, so ``J`` is only comparable between two fits that used the SAME incumbent.
``routines/plots.build_context`` derives the incumbent from the most recent epoch of whatever frame
it is handed, which is exactly the right behaviour for a single whole-record fit and exactly the
wrong behaviour here: handed one pulse-width stratum at a time it would reference each stratum to
its own most recent epoch, and the resulting posterior means could not be compared across strata at
all. So this module calls ``build_objective`` ONCE on the whole matrix with the globally most recent
epoch as incumbent, and then fits the surrogate per stratum on that single shared ``J`` column.
``pipeline.run`` and the figure set continue to use ``build_context`` unchanged.

THE TERMINAL OUTPUT
-------------------
:class:`FrozenConfiguration`. It is a frozen dataclass, so Stage 2 cannot write to it — an attempt
raises ``dataclasses.FrozenInstanceError`` rather than silently succeeding. It carries, per
hemisphere, the chosen rate and pulse width, the amplitude the surface prefers at that
configuration, the delivered amplitude envelope, and — the field that decides whether Stage 2 is
allowed to begin — an explicit statement of whether the choice is RESOLVED against its own
uncertainty, with the reasons written out.

Resolution uses the module's existing criterion, the one recorded in
``pipeline.ArmResult.surface_can_resolve_its_optimum``: a candidate counts as resolved only when it
beats the comparison cell by more than ``k`` times the standard deviation OF THE DIFFERENCE, with
both posterior standard deviations propagated. Two consequences are worth stating because they look
like bugs and are not. First, a configuration identical to the setting already in force can never
be "resolved": the gain is zero, so retaining the incumbent is reported as an unresolved default
rather than as a positive finding. Second, because the joint posterior covariance between two cells
is not carried, ``var1 + var2`` is used in place of ``var1 + var2 - 2*cov``; nearby cells on a
smooth kernel are positively correlated, so this overstates the variance of the difference and the
criterion is strictly conservative. It can withhold a recommendation it might have supported; it
cannot manufacture one.

Typical use::

    from StimOptimizer import stage1_openloop as S1
    res = S1.run_stage1("rcs08_bo_design_matrix.csv", data_horizon="2026-08-28")
    print(res.summary.to_string())
    print(res.frozen.describe())
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .routines import acquisition as ACQ
from .routines import objective as OBJ
from .routines import plots as PLT
from .routines import surrogate as SUR
from .routines import validation as VAL

#: Minimum epochs in a pulse-width stratum before a surface is fitted for it. Matched to the floor
#: ``routines/plots.build_context`` already applies to a whole-record fit, so a stratum is not held
#: to a laxer standard than the pooled fit it is a slice of. ``ObjectiveGP`` itself only needs three
#: observations to fit hyperparameters, which is far too few to say anything about a two-dimensional
#: surface; this floor is the module's judgement, not a device or statistical constant.
PW_STRATUM_MIN_EPOCHS = 8

#: Multiplier on the standard deviation of the difference in the resolution criterion. ``1.0`` means
#: a gain must exceed one SD of its own difference. This is the same value
#: ``pipeline.ArmResult.surface_can_resolve_its_optimum`` uses by default, kept identical so the two
#: entry points cannot disagree about whether the same surface resolves its own optimum.
RESOLUTION_K = 1.0

#: Amplitude ceiling the search may propose, in mA. PI-declared (2026-08-30) and identical to the
#: top of ``routines/plots.AMP_GRID``; restated here as a named constant because Stage 2 and the
#: gate both need it and neither should reach into a plotting module for a safety limit.
AMP_CEILING_MA = 4.9

#: Exposure duration, in hours, above which a delivered setting is treated as tolerated for the
#: purposes of seeding the safety model. Same default ``build_context`` uses.
MIN_TOLERATED_H = 72.0


# ---------------------------------------------------------------------------------------------
# The frozen configuration
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class HemisphereSetting:
    """The rate and pulse width Stage 1 hands on for one hemisphere, and the evidence for them.

    ``rate_resolved`` and ``pw_resolved`` are three-valued. ``True`` means the choice beat its
    comparison by more than the standard deviation of the difference. ``False`` means it did not.
    ``None`` means NOT ASSESSED — the question could not be put to the data at all, which is a
    different statement from a negative answer and must not be collapsed into one.
    """

    hemisphere: str
    rate_hz: float
    pw_us: float | None
    amp_star_mA: float
    amp_delivered_min_mA: float
    amp_delivered_max_mA: float
    #: Epochs on the ONE stratum that produced this choice — not the hemisphere's total. The
    #: hemisphere-level counts live in the audit as ``n_epochs_eligible`` (everything surviving the
    #: amplitude and feasibility filters) and ``n_epochs_in_fitted_strata`` (what reached a surface
    #: after undersampled strata were skipped). The three are different numbers and reporting one
    #: under another's name once produced a summary that contradicted its own per-stratum table.
    n_epochs_fitted: int
    rate_resolved: bool | None
    pw_resolved: bool | None
    reasons: tuple = ()
    detail: dict = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        """Both the rate and the pulse width resolved. ``None`` on either counts as NOT resolved.

        A gate that treated "not assessed" as a pass would license closed-loop configuration on the
        strength of a question nobody asked, so the collapse is deliberately one-directional.
        """
        return self.rate_resolved is True and self.pw_resolved is True


@dataclass(frozen=True)
class FrozenConfiguration:
    """Stage 1's terminal product: what Stage 2 must treat as immovable.

    Frozen in two senses that happen to coincide. Clinically, rate and pulse width freeze in the
    device the moment BrainSense is configured. Programmatically, this is a frozen dataclass, so
    ``cfg.rate_hz = 130`` raises ``FrozenInstanceError`` instead of quietly changing the plan. The
    coincidence is the point: the type system is made to enforce the device constraint.

    ``override`` records a clinician's explicit decision to proceed on an unresolved configuration.
    It is a mapping and it must carry a non-empty ``reason``; see :func:`clinician_override`.
    """

    settings: tuple                        # tuple[HemisphereSetting, ...]
    primary_item: str
    incumbent_epoch: float
    incumbent_rate_hz: float
    incumbent_pw_us: float | None
    data_horizon: str
    washin_min: float
    n_epochs_total: int
    override: dict | None = None
    audit: dict = field(default_factory=dict)

    def setting(self, hemisphere: str) -> HemisphereSetting:
        for s in self.settings:
            if s.hemisphere == hemisphere:
                return s
        raise KeyError(f"no setting for hemisphere {hemisphere!r}; have "
                       f"{[s.hemisphere for s in self.settings]}")

    @property
    def hemispheres(self) -> tuple:
        return tuple(s.hemisphere for s in self.settings)

    @property
    def resolved(self) -> bool:
        """Every hemisphere's rate and pulse width resolved against its own uncertainty."""
        return bool(self.settings) and all(s.resolved for s in self.settings)

    @property
    def overridden(self) -> bool:
        return bool(self.override) and bool(str(self.override.get("reason", "")).strip())

    def describe(self) -> str:
        lines = [f"FROZEN CONFIGURATION (primary outcome: {self.primary_item}; "
                 f"data horizon {self.data_horizon}; wash-in {self.washin_min:g} min)"]
        for s in self.settings:
            pw = "NOT OBSERVED" if s.pw_us is None else f"{s.pw_us:g} us"
            lines.append(
                f"  {s.hemisphere:5s}: rate {s.rate_hz:g} Hz, pulse width {pw}, "
                f"amplitude preferred {s.amp_star_mA:.2f} mA "
                f"(delivered {s.amp_delivered_min_mA:.2f}-{s.amp_delivered_max_mA:.2f} mA, "
                f"{s.n_epochs_fitted} epochs) | rate resolved: {s.rate_resolved}, "
                f"pulse width resolved: {s.pw_resolved}")
            for r in s.reasons:
                lines.append(f"         - {r}")
        lines.append(f"  overall resolved: {self.resolved}"
                     + (f" | CLINICIAN OVERRIDE: {self.override.get('reason')}"
                        if self.overridden else ""))
        return "\n".join(lines)


def clinician_override(cfg: FrozenConfiguration, *, reason: str, by: str | None = None,
                       at: str | None = None) -> FrozenConfiguration:
    """Return a copy of ``cfg`` carrying a recorded clinician override of the resolution
    requirement.

    This does NOT change any setting and it does not make anything resolved. It records that a named
    person decided, for a stated reason, to freeze a configuration whose advantage over the setting
    in force is smaller than the uncertainty in that advantage. The gate reads it as satisfying the
    resolution condition and reports it as an override rather than as a pass, so the distinction
    survives into the report.

    An empty or whitespace reason is refused. An override with no reason is indistinguishable from
    disabling the check, and the whole purpose of this module is that a refusal names its cause.
    """
    if not str(reason).strip():
        raise ValueError(
            "a clinician override requires a non-empty reason. Recording who decided and why is "
            "what separates an override from silently disabling the resolution requirement.")
    return replace(cfg, override=dict(reason=str(reason).strip(), by=by, at=at))


# ---------------------------------------------------------------------------------------------
# Design audits over the third dimension
# ---------------------------------------------------------------------------------------------
def pulse_width_design_audit(fit: pd.DataFrame, *, pw_col="pw_us_Left",
                             min_epochs=PW_STRATUM_MIN_EPOCHS) -> dict:
    """How much of the rate x pulse-width plane was actually delivered?

    This is pure counting, with no test statistic and no model. It exists because a frozen
    configuration names a pulse width, and a reader is entitled to know whether that pulse width
    could have been chosen on evidence or was simply whatever accompanied the chosen rate. The
    decisive quantity is ``n_rates_with_two_pw_levels``: a pulse-width effect can only be separated
    from a rate effect at a rate where more than one pulse width was delivered. If no rate carries
    two adequately-sampled pulse-width levels, the two factors are aliased in this design and no
    amount of modelling will unalias them.
    """
    tab = pd.crosstab(fit["freq_hz"].astype(float), fit[pw_col].astype(float))
    per_rate = {float(r): int((row >= min_epochs).sum()) for r, row in tab.iterrows()}
    per_rate_any = {float(r): int((row > 0).sum()) for r, row in tab.iterrows()}
    counts = {float(c): int(tab[c].sum()) for c in tab.columns}
    n_cells = int(tab.size)
    n_delivered = int((tab.to_numpy() > 0).sum())
    return dict(
        crosstab=tab,
        pw_levels=[float(c) for c in tab.columns],
        n_pw_levels=int(tab.shape[1]),
        epochs_per_pw=counts,
        fittable_pw_levels=[float(c) for c, n in counts.items() if n >= int(min_epochs)],
        n_rate_pw_cells=n_cells,
        n_rate_pw_cells_delivered=n_delivered,
        rate_pw_coverage=float(n_delivered) / n_cells if n_cells else float("nan"),
        pw_levels_per_rate_any=per_rate_any,
        pw_levels_per_rate_fittable=per_rate,
        n_rates_with_two_pw_levels=int(sum(1 for v in per_rate_any.values() if v >= 2)),
        n_rates_with_two_fittable_pw_levels=int(sum(1 for v in per_rate.values() if v >= 2)),
        min_epochs=int(min_epochs),
    )


def pulse_width_contrast(fit: pd.DataFrame, *, pw_col="pw_us_Left", reference_pw=None,
                         era_scheme="quarter", min_epochs=PW_STRATUM_MIN_EPOCHS) -> dict:
    """Precision-weighted, rate-blocked and era-blocked estimate of the pulse-width effect on J.

    The surrogate answers "which cell has the lowest posterior mean" but not "is pulse width doing
    anything at all", and those are different questions. This is the second one, asked with the
    project's standard adjustments: rate enters as a factor because rate and pulse width were moved
    together in this record, era enters as a factor because pain ratings drift over the programme,
    and rows are weighted by ``1/obs_var`` so a sparsely-rated epoch does not carry the same weight
    as a densely-rated one. The weighting matches how the surrogate treats the same rows, which is
    why weighted least squares is used rather than ordinary least squares.

    The estimable-or-not check is not decoration. With rate as a factor, a pulse-width level
    delivered at only one rate is collinear with that rate's indicator, and the design matrix loses
    rank. Reporting a coefficient from a rank-deficient fit would be reporting an arbitrary point
    from a flat ridge, so the function returns ``estimable=False`` and no coefficients instead.

    ``min_epochs`` drops pulse-width levels with fewer rows than the stratum floor, and this is a
    DELIBERATE DATA-SCOPE REDUCTION that has to be declared rather than buried. Two reasons. The
    fit is meant to be a second view of the same rows the stratified surrogate comparison uses, and
    the surrogate only fits levels that clear the floor, so including a level the surrogate ignored
    would make the two views answer slightly different questions. And on the real RCS08 record a
    single two-epoch level, 120 us delivered at 145 Hz only, is the entire cause of the rank
    deficiency: with it in, nothing is estimable; with it out, every remaining coefficient is. The
    excluded levels are reported in ``excluded_levels`` so the reduction is visible in the output.

    Returns a mapping. ``estimable`` is ``False`` when the design cannot support the model at all.
    """
    out = dict(estimable=False, reason="", reference_pw=reference_pw, n=int(len(fit)),
               coefficients={}, era_scheme=str(era_scheme), n_eras=0, notes=[],
               excluded_levels={}, min_epochs=int(min_epochs))
    d = fit.copy()
    d["pw"] = d[pw_col].astype(float)
    counts = d["pw"].value_counts().to_dict()
    thin = {float(k): int(v) for k, v in counts.items() if int(v) < int(min_epochs)}
    if thin:
        out["excluded_levels"] = thin
        out["notes"].append(
            "pulse-width levels excluded for having fewer rows than the "
            f"{int(min_epochs)}-epoch stratum floor: "
            + ", ".join(f"{k:g} us (n={v})" for k, v in sorted(thin.items()))
            + ". These are the same levels the stratified surrogate comparison omits, so the two "
              "views are fitted on the same rows")
        d = d.loc[~d["pw"].isin(list(thin))].copy()
        out["n"] = int(len(d))
    d["rate"] = d["freq_hz"].astype(float)
    levels = sorted(d["pw"].unique())
    if len(levels) < 2:
        out["reason"] = (f"pulse width never varied among the fitted epochs (single level "
                         f"{levels[0]:g} us if any); the effect is unidentifiable")
        return out

    ref = float(levels[0] if reference_pw is None else reference_pw)
    if ref not in set(levels):
        out["reason"] = (f"reference pulse width {ref:g} us is not among the fitted levels "
                         f"{[f'{v:g}' for v in levels]}")
        return out
    out["reference_pw"] = ref

    try:
        import statsmodels.formula.api as smf
    except Exception as exc:                                       # pragma: no cover - defensive
        out["reason"] = f"statsmodels unavailable ({type(exc).__name__}: {exc})"
        return out

    d["era"] = VAL.era_labels(d, scheme=era_scheme).astype(str).values
    out["n_eras"] = int(pd.Series(d["era"]).nunique())
    terms = [f"C(pw, Treatment(reference={ref}))", "C(rate)"]
    if out["n_eras"] > 1:
        terms.append("C(era)")
    else:
        out["notes"].append(
            "era NOT blocked: the fitted epochs fall in a single calendar quarter, so the "
            "pulse-width effect is not separated from time here")
    amp_cols = [c for c in ("amp_mA_Left", "amp_mA_Right") if c in d.columns]
    formula = "J ~ " + " + ".join(terms + amp_cols)

    w = 1.0 / d["obs_var"].astype(float).to_numpy()
    res = smf.wls(formula, data=d, weights=w).fit()
    # Rank deficiency is what aliasing looks like numerically, and statsmodels will return a
    # pseudo-inverse solution rather than complain, so the check has to be explicit: a coefficient
    # read off a rank-deficient fit is an arbitrary point on a flat ridge.
    #
    # Attributing the deficiency matters as much as detecting it, because the two causes call for
    # different responses. If the PULSE-WIDTH columns are the dependent ones, the pulse-width effect
    # is aliased with rate and the answer is more data. If the deficiency is elsewhere — collinear
    # amplitude columns, an era perfectly nested in a rate — the pulse-width effect might well be
    # estimable once that other term is dealt with, and saying "pulse width is aliased" would be a
    # false diagnosis. So the attribution is COMPUTED rather than assumed: drop the pulse-width
    # columns and see how much rank goes with them. If they contribute fewer independent directions
    # than they have columns, they are the dependent ones.
    exog = np.asarray(res.model.exog, float)
    names = list(res.model.exog_names)
    n_par = exog.shape[1]
    rank_full = int(np.linalg.matrix_rank(exog))
    if rank_full < n_par:
        pw_idx = [i for i, nm in enumerate(names) if nm.startswith("C(pw")]
        other = [i for i in range(n_par) if i not in pw_idx]
        rank_other = int(np.linalg.matrix_rank(exog[:, other])) if other else 0
        pw_aliased = bool(pw_idx) and (rank_full - rank_other) < len(pw_idx)
        out["rank"] = rank_full
        out["n_parameters"] = n_par
        out["pw_columns_aliased"] = pw_aliased
        if pw_aliased:
            out["reason"] = (
                f"the design matrix is rank deficient ({rank_full} of {n_par} columns independent) "
                f"and the PULSE-WIDTH columns are the dependent ones: they add only "
                f"{rank_full - rank_other} independent direction(s) for {len(pw_idx)} column(s), so "
                "at least one pulse-width level was delivered at a single rate and its effect is "
                "collinear with that rate's indicator. No amount of modelling separates them; only "
                "delivering a pulse width at a second rate does.")
        else:
            out["reason"] = (
                f"the design matrix is rank deficient ({rank_full} of {n_par} columns independent), "
                "but NOT because of pulse width — the pulse-width columns contribute their full "
                f"{len(pw_idx)} independent direction(s). The dependency lies among the other terms "
                f"({', '.join(nm for i, nm in enumerate(names) if i in other and nm != 'Intercept')}"
                "), for example two perfectly correlated amplitude columns or an era nested inside "
                "a rate. The fit is not identified as specified, so no coefficient is reported; "
                "removing the offending term may make the pulse-width effect estimable.")
        return out

    ci = res.conf_int()
    for name in res.params.index:
        if not name.startswith("C(pw"):
            continue
        lvl = name.split("[T.")[-1].rstrip("]")
        out["coefficients"][lvl] = dict(
            estimate=float(res.params[name]),
            ci=(float(ci.loc[name, 0]), float(ci.loc[name, 1])),
            p=float(res.pvalues[name]),
            resolved=bool(abs(float(res.params[name])) > float(res.bse[name])),
        )
    out.update(estimable=True, reason="fitted", formula=formula,
               df_resid=float(res.df_resid), r2=float(res.rsquared))
    return out


# ---------------------------------------------------------------------------------------------
# One pulse-width stratum
# ---------------------------------------------------------------------------------------------
@dataclass
class Stage1Slice:
    """One (rate, amplitude) surface, fitted at a single pulse-width level."""

    hemisphere: str
    pw_us: float
    n_epochs: int
    grid: object
    gp: object
    mu: np.ndarray
    sd: np.ndarray
    safe: np.ndarray
    i_star: int
    x_star: tuple
    mu_star: float
    sd_star: float
    incumbent_mu: float
    incumbent_sd: float
    n_reports: np.ndarray
    queue: np.ndarray
    stopping: object
    incumbent_rate_supported: bool = True
    optimum_rate_supported: bool = True
    batch: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def gain_over_incumbent(self) -> float:
        """Positive means the slice optimum is better (lower J) than the setting in force."""
        return float(self.incumbent_mu) - float(self.mu_star)

    def sd_of_difference(self) -> float:
        return float(np.sqrt(float(self.sd_star) ** 2 + float(self.incumbent_sd) ** 2))

    def resolves_its_optimum(self, k: float = RESOLUTION_K) -> bool | None:
        """Does this slice's optimum beat the setting in force by more than the uncertainty in
        that difference? ``None`` means the question cannot be put to this slice.

        The ``None`` case is not defensive padding — it is the single most important correction in
        this module, and it was found by running the real matrix. ``J`` is defined as the primary
        pain item minus its value at the incumbent epoch, so ``J`` at the incumbent is ZERO BY
        CONSTRUCTION. A pulse-width stratum that never delivered the incumbent's RATE has no data
        anywhere near that cell, so its posterior there reverts towards the stratum's own mean. On
        the RCS08 matrix the 140 us stratum, which contains no 55 Hz epoch on either hemisphere,
        predicted J = +1.66 at the incumbent cell with a posterior SD of 1.60 — a definitional zero
        reported as 1.66 points worse than it is. Compared against that fictitious baseline the
        stratum's own optimum showed a gain of 2.28 points and the resolution criterion returned
        True. The finding was entirely an artefact of extrapolating into a rate the stratum never
        ran.

        Support is defined on the RATE axis specifically, and the reason is that the frequency
        length scale is PINNED rather than fitted (``routines/surrogate._make_kernel``, pinned
        because the marginal likelihood is essentially flat in it on this design). Borrowing across
        rates therefore rests on a stated assumption rather than on anything the data determined,
        and a comparison that depends entirely on that borrowing is not a measurement. Amplitude,
        whose length scale IS fitted, is not treated this way.
        """
        if not self.incumbent_rate_supported:
            return None
        sd_diff = self.sd_of_difference()
        if not np.isfinite(sd_diff) or sd_diff <= 0:
            return False
        return bool(self.gain_over_incumbent() > float(k) * sd_diff)


def _fit_slice(hemi, pw, sub, *, grid, sgp, safe, incumbent_xy, amp_col, fixed_length_scale,
               kappa, q, eta) -> Stage1Slice:
    """Fit the existing surrogate to one pulse-width stratum and derive everything downstream.

    ``sgp``/``safe`` are the SHARED safety model, fitted once on the whole record. Sharing it is a
    limitation worth stating rather than hiding: charge per pulse rises with pulse width, so at a
    fixed amplitude a 180 us pulse delivers more charge than a 60 us pulse, and one safe set across
    all strata is therefore OPTIMISTIC at the wider pulse widths. It is shared because the safety
    seed is built from the programmed ``UpperLimitInMilliAmps`` anchors, which carry a frequency and
    an amplitude and no pulse width at all, so there is nothing in the record to stratify it by.
    """
    Xobs = sub[["freq_hz", amp_col]].to_numpy(float)
    gp = SUR.ObjectiveGP(grid, fixed_length_scale=fixed_length_scale, random_state=0).fit(
        Xobs, sub["J"].to_numpy(float), sub["obs_var"].to_numpy(float))
    mu, sd = gp.predict_grid()

    n_reports = np.zeros(len(grid))
    np.add.at(n_reports, grid.index_of(Xobs), sub["n"].to_numpy(float))

    inc_mu, inc_sd = gp.predict(np.atleast_2d(incumbent_xy), return_std=True)
    incumbent_mu, incumbent_sd = float(inc_mu[0]), float(inc_sd[0])
    i_star = int(np.argmin(np.where(safe, mu, np.inf)))
    gx = grid.grid_X()

    queue, qmeta = ACQ.exploration_queue(mu, sd, n_reports, incumbent_mu, kappa=kappa)
    stopping = ACQ.check_stopping([float(mu[i_star])], mu, sd, n_reports,
                                  incumbent_mu=incumbent_mu)
    try:
        batch = ACQ.select_batch_within_visit(gp, grid, q=int(q), safe_mask=safe,
                                              n_reports=n_reports, incumbent_mu=incumbent_mu,
                                              eta=eta)
    except ValueError as exc:
        # An empty candidate set is a legitimate state (everything safe has been tested, or nothing
        # is provably safe). It must be recorded, not raised past the caller as a fit failure.
        batch = []
        batch_note = f"no within-visit batch available: {exc}"
    else:
        batch_note = ""

    rates = set(np.round(sub["freq_hz"].astype(float).to_numpy(), 6))
    inc_supported = bool(round(float(incumbent_xy[0]), 6) in rates)
    opt_supported = bool(round(float(gx[i_star, 0]), 6) in rates)

    return Stage1Slice(
        hemisphere=hemi, pw_us=float(pw), n_epochs=int(len(sub)), grid=grid, gp=gp,
        mu=mu, sd=sd, safe=safe, i_star=i_star,
        x_star=(float(gx[i_star, 0]), float(gx[i_star, 1])),
        mu_star=float(mu[i_star]), sd_star=float(sd[i_star]),
        incumbent_mu=incumbent_mu, incumbent_sd=incumbent_sd,
        n_reports=n_reports, queue=queue, stopping=stopping, batch=batch,
        incumbent_rate_supported=inc_supported, optimum_rate_supported=opt_supported,
        meta=dict(kernel=gp.hyperparameters["kernel"],
                  log_marginal_likelihood=gp.hyperparameters["log_marginal_likelihood"],
                  n_reports_total=float(sub["n"].sum()),
                  rates_delivered=[float(v) for v in sorted(sub["freq_hz"].unique())],
                  amp_min=float(sub[amp_col].min()), amp_max=float(sub[amp_col].max()),
                  n_safe=int(safe.sum()), queue_size=int(queue.size),
                  best_optimistic_unexplored=float(qmeta.get("best_optimistic", float("nan"))),
                  batch_note=batch_note))


# ---------------------------------------------------------------------------------------------
# The stage runner
# ---------------------------------------------------------------------------------------------
@dataclass
class Stage1Result:
    """Everything Stage 1 produced, plus the frozen configuration it hands to the gate."""

    frozen: FrozenConfiguration
    slices: dict                           # dict[(hemisphere, pw_us)] -> Stage1Slice
    summary: pd.DataFrame
    audit: dict
    D: pd.DataFrame
    skipped: dict = field(default_factory=dict)

    def slices_for(self, hemisphere: str) -> list:
        return [s for (h, _pw), s in self.slices.items() if h == hemisphere]


def run_stage1(design_csv, *, hemispheres=("Left", "Right"), primary_item="left_leg",
               pw_col="pw_us_Left", freq_grid=PLT.FREQ_GRID, amp_grid=PLT.AMP_GRID,
               fixed_length_scale=PLT.FIXED_LENGTH_SCALE, beta=PLT.BETA, kappa=PLT.KAPPA,
               limit_anchors=PLT.LIMIT_ANCHORS, min_tolerated_h=MIN_TOLERATED_H,
               min_stratum_epochs=PW_STRATUM_MIN_EPOCHS, q=4, eta=1.0,
               incumbent_epoch=None, data_horizon=PLT.DATA_HORIZON, washin_min=PLT.WASHIN_MIN,
               resolution_k=RESOLUTION_K, era_scheme="quarter") -> Stage1Result:
    """Run the open-loop search and freeze a configuration.

    Parameters
    ----------
    design_csv
        Epoch-level design matrix (path or DataFrame), as ``routines/objective.build_objective``
        requires, plus ``amp_mA_<hemisphere>`` for each requested hemisphere and ``pw_col``.
    hemispheres
        Fitted independently and never blended, for the reason ``pipeline`` records: the two sides
        are usable on different epoch subsets, so a joint surface would either drop every epoch
        where one side is off or impose one shared length scale on two dimensions with different
        support.
    pw_col
        Column holding pulse width. This record carries ``pw_us_Left`` only, so the right
        hemisphere's pulse width is NOT OBSERVED and is reported as such rather than assumed equal
        to the left.
    min_stratum_epochs
        A pulse-width level with fewer fitted epochs than this is SKIPPED, with its reason recorded
        in ``.skipped``, never silently pooled into a neighbouring level.
    incumbent_epoch
        Defaults to the most recent epoch in the matrix, which is the setting currently in force.
        ``J`` is referenced to it, so every stratum shares one scale.

    Returns
    -------
    Stage1Result
        ``.frozen`` is the :class:`FrozenConfiguration` the gate reads; ``.slices`` holds one
        :class:`Stage1Slice` per fitted (hemisphere, pulse width); ``.summary`` is one row per
        slice; ``.audit`` carries the pulse-width design audit and contrast.
    """
    es = pd.read_csv(design_csv) if not isinstance(design_csv, pd.DataFrame) else design_csv.copy()
    if incumbent_epoch is None:
        if "t0" not in es.columns:
            raise KeyError("cannot derive the incumbent without a 't0' column; pass "
                           "incumbent_epoch explicitly")
        incumbent_epoch = float(es.sort_values("t0")["epoch"].iloc[-1])
    if float(incumbent_epoch) not in set(es["epoch"].astype(float)):
        raise ValueError(f"incumbent_epoch {incumbent_epoch} is not in this design matrix "
                         f"(epochs {es['epoch'].min():g}-{es['epoch'].max():g})")

    # ONE objective build, ONE incumbent, so J is on a single scale across every stratum below.
    D = OBJ.build_objective(es, incumbent_epoch=float(incumbent_epoch),
                            cfg={"primary_item": primary_item} if primary_item else None)
    inc_row = D.loc[D["epoch"].astype(float) == float(incumbent_epoch)].iloc[0]
    inc_rate = float(inc_row["freq_hz"])
    inc_pw = float(inc_row[pw_col]) if pw_col in D.columns else None
    resolved_item = str(D["primary_item"].iloc[0]) if "primary_item" in D.columns else primary_item

    grid = SUR.ParameterGrid(freq_grid, amp_grid)
    gx = grid.grid_X()

    slices, rows, skipped, settings = {}, [], {}, []
    audit = dict(incumbent_epoch=float(incumbent_epoch), incumbent_rate_hz=inc_rate,
                 incumbent_pw_us=inc_pw, pw_col=str(pw_col), per_hemisphere={})

    for hemi in hemispheres:
        amp_col = f"amp_mA_{hemi}"
        if amp_col not in D.columns:
            raise KeyError(f"design matrix has no {amp_col!r} column; cannot search the "
                           f"{hemi} hemisphere")
        # A hemisphere at 0 mA is a different therapeutic state, not the low end of its own dose
        # axis (OBJECTIVE_SPEC amendment 2026-08-29), so those epochs are excluded from this
        # hemisphere's surface rather than left to anchor its intercept.
        fit = D.loc[(D[amp_col].astype(float) > 0) & D["feasible"]].copy()
        inc_amp = float(inc_row[amp_col])
        incumbent_xy = (inc_rate, inc_amp)

        # Shared safety model, fitted once on the whole record for this hemisphere.
        deliv = D.loc[D["dur_h"].astype(float) >= float(min_tolerated_h),
                      ["freq_hz", amp_col]].to_numpy(float)
        Xs, sev, sv = SUR.SafetyGP.seed_from_history(deliv, np.asarray(limit_anchors, float))
        sgp = SUR.SafetyGP(grid, random_state=0).fit(Xs, sev, sv)
        safe = sgp.safe_mask(beta=beta)

        pw_present = pw_col in fit.columns and fit[pw_col].notna().any()
        # `n_epochs_eligible` counts every epoch that survives the amplitude>0 and feasibility
        # filters. It is NOT the number of epochs that end up on a fitted surface, because a
        # pulse-width stratum below the 8-epoch floor is skipped after this point. The two differ by
        # the size of the skipped strata, and calling this "fitted" once produced a report whose
        # per-stratum counts did not sum to its own stated total.
        h_audit = dict(n_epochs_eligible=int(len(fit)),
                       amp_delivered_min=float(fit[amp_col].min()) if len(fit) else float("nan"),
                       amp_delivered_max=float(fit[amp_col].max()) if len(fit) else float("nan"),
                       pw_observed=bool(pw_present))
        if pw_present:
            h_audit["design"] = pulse_width_design_audit(fit, pw_col=pw_col,
                                                         min_epochs=min_stratum_epochs)
            h_audit["contrast"] = pulse_width_contrast(fit, pw_col=pw_col, reference_pw=inc_pw,
                                                       era_scheme=era_scheme,
                                                       min_epochs=min_stratum_epochs)
        audit["per_hemisphere"][hemi] = h_audit

        # --- fit one surface per adequately-sampled pulse-width level -------------------------
        if pw_present:
            groups = [(float(pw), sub) for pw, sub in fit.groupby(fit[pw_col].astype(float))]
        else:
            groups = [(float("nan"), fit)]
        for pw, sub in groups:
            key = (hemi, pw)
            if len(sub) < int(min_stratum_epochs):
                skipped[f"{hemi}__pw{pw:g}"] = (
                    f"{len(sub)} fitted epochs at {pw:g} us, below the {int(min_stratum_epochs)}-"
                    "epoch floor for a two-dimensional surface")
                continue
            try:
                sl = _fit_slice(hemi, pw, sub, grid=grid, sgp=sgp, safe=safe,
                                incumbent_xy=incumbent_xy, amp_col=amp_col,
                                fixed_length_scale=fixed_length_scale, kappa=kappa, q=q, eta=eta)
            except (ValueError, RuntimeError) as exc:
                skipped[f"{hemi}__pw{pw:g}"] = f"{type(exc).__name__}: {exc}"
                continue
            slices[key] = sl
            rows.append(dict(
                hemisphere=hemi, pw_us=pw, n_epochs=sl.n_epochs,
                n_reports=sl.meta["n_reports_total"],
                opt_rate_hz=sl.x_star[0], opt_amp_mA=sl.x_star[1],
                opt_posterior_mean=sl.mu_star, opt_posterior_sd=sl.sd_star,
                incumbent_mu=sl.incumbent_mu, incumbent_sd=sl.incumbent_sd,
                gain=sl.gain_over_incumbent(), sd_of_difference=sl.sd_of_difference(),
                optimum_resolved=sl.resolves_its_optimum(resolution_k),
                incumbent_rate_supported=sl.incumbent_rate_supported,
                optimum_rate_supported=sl.optimum_rate_supported,
                n_safe=sl.meta["n_safe"], queue_size=sl.meta["queue_size"],
                stop=bool(sl.stopping.stop), stop_binding=sl.stopping.binding,
                kernel=sl.meta["kernel"]))

        # Now that the strata are known, record how many epochs actually reached a fitted surface.
        h_audit["n_epochs_in_fitted_strata"] = int(
            sum(s.n_epochs for (h, _p), s in slices.items() if h == hemi))

        # --- choose the configuration for this hemisphere -------------------------------------
        settings.append(_freeze_hemisphere(
            hemi, [s for (h, _p), s in slices.items() if h == hemi], inc_rate, inc_pw,
            fit=fit, amp_col=amp_col, h_audit=h_audit, grid=grid, gx=gx,
            resolution_k=resolution_k, pw_observed=pw_present))

    frozen = FrozenConfiguration(
        settings=tuple(settings), primary_item=resolved_item,
        incumbent_epoch=float(incumbent_epoch), incumbent_rate_hz=inc_rate, incumbent_pw_us=inc_pw,
        data_horizon=str(data_horizon), washin_min=float(washin_min),
        n_epochs_total=int(len(D)), audit=audit)
    return Stage1Result(frozen=frozen, slices=slices, summary=pd.DataFrame(rows), audit=audit,
                        D=D, skipped=skipped)


def _freeze_hemisphere(hemi, hslices, inc_rate, inc_pw, *, fit, amp_col, h_audit, grid, gx,
                       resolution_k, pw_observed) -> HemisphereSetting:
    """Pick the rate and pulse width for one hemisphere and state whether either is resolved.

    The rate comes from the best slice's own optimum and is tested against the setting in force
    within that slice, so both posterior means are on the same surface. The pulse width is tested
    across slices, comparing the best slice's optimum against the posterior at THE SAME (rate,
    amplitude) CELL in the incumbent pulse width's slice. Holding the cell fixed is what makes the
    comparison a pulse-width contrast rather than a mixture of a pulse-width move and a rate move.
    """
    reasons = []
    if not hslices:
        return HemisphereSetting(
            hemisphere=hemi, rate_hz=inc_rate, pw_us=inc_pw if pw_observed else None,
            amp_star_mA=float("nan"),
            amp_delivered_min_mA=h_audit["amp_delivered_min"],
            amp_delivered_max_mA=h_audit["amp_delivered_max"],
            n_epochs_fitted=int(h_audit.get("n_epochs_in_fitted_strata", 0)),
            rate_resolved=None, pw_resolved=None,
            reasons=("no pulse-width stratum had enough fitted epochs to support a surface, so "
                     "neither the rate nor the pulse width was searched at all; the setting in "
                     "force is carried forward as a default, not as a choice",),
            detail=dict(n_slices=0))

    best = min(hslices, key=lambda s: s.mu_star)
    rate_resolved = best.resolves_its_optimum(resolution_k)
    if rate_resolved is None:
        reasons.append(
            f"the rate choice is NOT ASSESSED, not refused: the chosen pulse-width stratum "
            f"({best.pw_us:g} us) never delivered the rate in force ({inc_rate:g} Hz) — it ran "
            f"{', '.join(f'{r:g}' for r in best.meta['rates_delivered'])} Hz — so its posterior at "
            f"the incumbent cell ({best.incumbent_mu:+.4f}, SD {best.incumbent_sd:.4f}) is an "
            "extrapolation across a PINNED frequency length scale, not a measurement. J is zero at "
            "the incumbent by construction, so any gain computed against that extrapolation is an "
            "artefact of the stratification and is discarded rather than reported")
    elif not rate_resolved:
        if abs(best.x_star[0] - inc_rate) < 1e-9:
            reasons.append(
                f"the chosen rate {best.x_star[0]:g} Hz is the rate already in force. Retaining "
                "the setting in force is not the same as having resolved it: the gain over the "
                "incumbent is zero by construction, so the resolution criterion cannot be met and "
                "the rate is carried forward as an unresolved default")
        else:
            reasons.append(
                f"the rate move {inc_rate:g} -> {best.x_star[0]:g} Hz is NOT resolved: the "
                f"posterior gain over the setting in force is {best.gain_over_incumbent():+.4f} "
                f"NRS points against a standard deviation of that difference of "
                f"{best.sd_of_difference():.4f}, so the difference is smaller than the "
                "uncertainty in the difference")
    else:
        reasons.append(
            f"the rate move {inc_rate:g} -> {best.x_star[0]:g} Hz IS resolved: gain "
            f"{best.gain_over_incumbent():+.4f} NRS points against difference SD "
            f"{best.sd_of_difference():.4f}")

    if not best.optimum_rate_supported:
        reasons.append(
            f"the chosen rate {best.x_star[0]:g} Hz was never delivered at {best.pw_us:g} us in "
            f"this record (that stratum ran "
            f"{', '.join(f'{r:g}' for r in best.meta['rates_delivered'])} Hz), so the proposal is "
            "an interpolation across the PINNED frequency length scale rather than a rate the "
            "surface has observed at this pulse width")
    if best.x_star[1] > float(h_audit["amp_delivered_max"]) + 1e-9:
        reasons.append(
            f"the preferred amplitude {best.x_star[1]:.2f} mA exceeds the highest amplitude ever "
            f"delivered on this hemisphere ({h_audit['amp_delivered_max']:.2f} mA), so it sits "
            "outside the delivered envelope and is an extrapolation on the amplitude axis too")

    # --- pulse width --------------------------------------------------------------------------
    detail = dict(n_slices=len(hslices), best_pw_us=float(best.pw_us),
                  pw_levels_fitted=[float(s.pw_us) for s in hslices])
    if not pw_observed:
        pw_resolved = None
        pw_us = None
        reasons.append(
            "pulse width is NOT OBSERVED for this hemisphere in this design matrix (the matrix "
            "carries a left-hemisphere pulse-width column only), so it can be neither searched nor "
            "resolved here. It is reported as unknown rather than assumed equal to the other side")
    elif len(hslices) < 2:
        pw_resolved = False
        pw_us = float(best.pw_us)
        reasons.append(
            f"only one pulse-width level ({best.pw_us:g} us) had enough fitted epochs to support a "
            f"surface, out of {h_audit['design']['n_pw_levels']} levels delivered, so no "
            "pulse-width comparison was possible and the pulse width is carried forward unresolved")
    else:
        pw_us = float(best.pw_us)
        ref = [s for s in hslices if inc_pw is not None and abs(s.pw_us - inc_pw) < 1e-9]
        alt = ref[0] if ref else min((s for s in hslices if s is not best),
                                     key=lambda s: s.mu_star)
        if alt is best:
            pw_resolved = False
            reasons.append(
                f"the best slice IS the pulse width in force ({best.pw_us:g} us); there is nothing "
                "to resolve against and it is carried forward as an unresolved default")
        elif round(float(best.x_star[0]), 6) not in set(
                np.round(np.asarray(alt.meta["rates_delivered"], float), 6)):
            # The reference stratum has to be able to speak about the cell being compared. If it
            # never delivered that rate, its posterior there is an extrapolation across the pinned
            # frequency length scale and the "pulse-width contrast" would in fact be measuring the
            # reference stratum's ignorance. Same failure mode as the rate comparison above.
            pw_resolved = None
            detail.update(pw_reference_us=float(alt.pw_us))
            reasons.append(
                f"the pulse-width contrast {alt.pw_us:g} -> {best.pw_us:g} us is NOT ASSESSED: the "
                f"reference stratum ({alt.pw_us:g} us) never delivered the chosen rate "
                f"{best.x_star[0]:g} Hz — it ran "
                f"{', '.join(f'{r:g}' for r in alt.meta['rates_delivered'])} Hz — so a contrast at "
                "that cell would compare a measurement against an extrapolation")
        else:
            # Same cell, different pulse width: an honest pulse-width contrast.
            cell = np.atleast_2d(np.asarray(best.x_star, float))
            a_mu, a_sd = alt.gp.predict(cell, return_std=True)
            gain = float(a_mu[0]) - float(best.mu_star)
            sd_diff = float(np.sqrt(float(best.sd_star) ** 2 + float(a_sd[0]) ** 2))
            pw_resolved = bool(np.isfinite(sd_diff) and sd_diff > 0
                               and gain > float(resolution_k) * sd_diff)
            detail.update(pw_reference_us=float(alt.pw_us), pw_gain=gain,
                          pw_sd_of_difference=sd_diff)
            verdict = "IS" if pw_resolved else "is NOT"
            reasons.append(
                f"the pulse-width move {alt.pw_us:g} -> {best.pw_us:g} us {verdict} resolved at "
                f"the chosen cell ({best.x_star[0]:g} Hz, {best.x_star[1]:.2f} mA): posterior gain "
                f"{gain:+.4f} NRS points against difference SD {sd_diff:.4f}")
        d = h_audit["design"]
        if d["n_rates_with_two_fittable_pw_levels"] == 0:
            reasons.append(
                f"NOTE ON THE DESIGN: no rate in this record was delivered at two pulse-width "
                f"levels that both clear the {d['min_epochs']}-epoch stratum floor "
                f"({d['n_rates_with_two_pw_levels']} rates carry two levels if thin cells are "
                f"counted, and only {d['n_rate_pw_cells_delivered']} of {d['n_rate_pw_cells']} "
                "rate x pulse-width combinations were delivered at all). Rate and pulse width were "
                "moved together, so a pulse-width contrast in this record is partly a rate "
                "contrast and cannot be fully unaliased by any model")
        c = h_audit.get("contrast", {})
        if not c.get("estimable", False):
            reasons.append(f"the regression check on the pulse-width effect was not estimable: "
                           f"{c.get('reason', 'not run')}")
        else:
            # Two views of the same rows: the stratified surrogate and a rate-blocked, era-blocked,
            # precision-weighted regression. When they disagree about the SIGN of the pulse-width
            # effect, that disagreement is itself the finding, and it is a stronger argument
            # against freezing a pulse width than either view is on its own. Reporting only the
            # view that happens to favour the proposal is the failure mode this note prevents.
            key = f"{best.pw_us:g}"
            coef = c["coefficients"].get(key) or c["coefficients"].get(f"{best.pw_us:.1f}")
            if coef is not None and float(coef["estimate"]) > 0:
                reasons.append(
                    f"DISAGREEMENT BETWEEN TWO VIEWS: the stratified surrogate prefers "
                    f"{best.pw_us:g} us, but the rate-blocked, era-blocked, precision-weighted "
                    f"regression on the same rows estimates {best.pw_us:g} us to be "
                    f"{float(coef['estimate']):+.4f} NRS points WORSE than the reference "
                    f"{c['reference_pw']:g} us (95% CI {coef['ci'][0]:+.4f} to "
                    f"{coef['ci'][1]:+.4f}, p = {coef['p']:.4g}). The two methods differ in what "
                    "they adjust for, and a pulse width the two disagree about the sign of is not "
                    "a pulse width to freeze")

    return HemisphereSetting(
        hemisphere=hemi, rate_hz=float(best.x_star[0]), pw_us=pw_us,
        amp_star_mA=float(best.x_star[1]),
        amp_delivered_min_mA=h_audit["amp_delivered_min"],
        amp_delivered_max_mA=h_audit["amp_delivered_max"],
        n_epochs_fitted=int(best.n_epochs),
        rate_resolved=rate_resolved, pw_resolved=pw_resolved,
        reasons=tuple(reasons), detail=detail)
