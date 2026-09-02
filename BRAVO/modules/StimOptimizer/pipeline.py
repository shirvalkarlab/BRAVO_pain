"""One-patient runner for the StimOptimizer module.

Library mode only: no Django import, no template rendering, no kaleido. Mirrors the entry-point
shape of ``modules/Biomarkers/pipeline.py`` so the service layer can call it the same way.

TWO ENTRY POINTS, AND WHICH ONE TO USE
--------------------------------------
:func:`run`
    The ORIGINAL flat entry point, unchanged. It fits one (frequency, amplitude) surface per arm,
    where an arm is one pain site crossed with one hemisphere's amplitude, and emits the table and
    figure set the existing callers and the service layer expect. Its behaviour, its arguments and
    its return type are exactly what they were; nothing below alters it. Use it for the surface
    fitting, the figures, and the acquisition proposals.

:func:`run_two_stage`
    The STAGED entry point, added because the device's own constraints force a sequence the flat
    search cannot represent. Rate and pulse width freeze the moment BrainSense is configured
    (A610 Clinician Programming Guide pp. 34-35), so closed-loop therapy adapts amplitude only and
    the open-loop search over rate and pulse width is a PREREQUISITE stage rather than one option
    among several. ``run_two_stage`` runs Stage 1 (``stage1_openloop``), evaluates the stage gate
    (``routines/stage_gate``) on the configuration Stage 1 freezes, and runs Stage 2
    (``stage2_closedloop``) only if the gate licenses it. Use it for any question about closed-loop
    deployment.

    ``run`` is not a subset of ``run_two_stage`` and neither replaces the other. ``run`` searches
    frequency and amplitude jointly over the whole record; Stage 1 searches rate and amplitude
    within pulse-width strata against a single common incumbent so the strata are comparable. They
    answer different questions and can legitimately disagree about which cell is best. Read
    ``TWO_STAGE_DESIGN.md`` before treating either as the other's cross-check.

The unit of work is an **arm**: one pain site crossed with one hemisphere's amplitude. Arms are
fitted independently and never blended. Two reasons, both empirical and both recorded in
OBJECTIVE_SPEC:

* **Sites.** On the RCS08 warm start the left-leg and back objectives rank the same 71 epochs at
  Spearman 0.48 and select different best epochs. Averaging them would report false agreement.
* **Hemispheres.** The two sides are usable on DIFFERENT epoch subsets, and the left is the
  sparser one. In the RCS08 warm start (86 epochs) both amplitudes are recorded on every epoch,
  but the left is above 0 mA on 59 and the right on 71; 21 epochs run the left off with the right
  active against 9 the other way. So the left arm fits 54 epochs and the right 63. A joint 3-D
  surface would have to drop every epoch where either side is off, or impute it, and a shared
  kernel would smooth two dimensions whose support differs by roughly 15%.

Typical use::

    from StimOptimizer import pipeline
    rep = pipeline.run("rcs08_bo_design_matrix.csv", outdir="out/", data_horizon="2026-08-28")
    print(rep.summary.to_string())

Every output carries the declared ``data_horizon`` and ``washin_min`` so a refresh regenerates
rather than invalidates. Nothing here recommends a setting on its own: ``run`` reports the
acquisition proposal alongside the uncertainty and the stopping decision, and
:meth:`RunReport.recommendation_is_supported` states plainly whether the surface can distinguish
its own optimum from no effect.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .routines import acquisition as ACQ
from .routines import plots as PLT

DEFAULT_SITES = ("left_leg", "back")
DEFAULT_HEMISPHERES = ("Left", "Right")


@dataclass
class ArmResult:
    """One (site, hemisphere) fit and everything derived from it."""
    site: str
    hemisphere: str
    ctx: object
    batch: pd.DataFrame
    queue: pd.DataFrame
    stopping: object
    meta: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.site}__{self.hemisphere}"

    def surface_can_resolve_its_optimum(self, k: float = 1.0) -> bool:
        """True only if the candidate BEATS the incumbent by more than the uncertainty of that
        difference.

        This is the honest gate on a recommendation, and the comparison has to be on the DIFFERENCE.
        An earlier version tested ``mu_star + k*sd_star < incumbent_mu``, which rearranges to
        ``gain > k*sd_star``: it required the gain to clear the CANDIDATE's SD but ignored the
        incumbent's own posterior SD, and so overstated how well the two cells are separated.
        Worked example from the RCS08 run of 2026-08-30, arm ``left_leg__Right``: incumbent
        mu = +0.4285, candidate mu = -0.6881, so the gain is 1.117; the candidate SD is 0.989 and the
        incumbent SD is 0.923. The old gate passed (1.117 > 0.989) and reported the optimum as
        resolved. Propagating both SDs gives sd_diff = sqrt(0.989^2 + 0.923^2) = 1.353, and
        1.117 < 1.353, so the difference is NOT resolved. That arm was the only one the old gate
        passed, and it is the reason this module reported "recommendation supported" at all.

        The variance of the difference between two GP predictions is
        ``var1 + var2 - 2*cov``. We do not currently carry the joint covariance between the two
        cells, so we use ``var1 + var2``. Because nearby cells on a smooth kernel are POSITIVELY
        correlated, dropping ``-2*cov`` OVERSTATES the variance, which makes this gate strictly
        conservative: it can withhold a recommendation it might have supported, but it cannot
        manufacture one. Tightening it requires predicting both cells jointly with the full
        covariance (``return_cov=True``) and is a documented next step, not a silent approximation.
        """
        m = self.meta
        gain = float(m["incumbent_mu"]) - float(m["mu_star"])          # >0 means candidate is better
        sd_inc = float(m.get("incumbent_sd") or 0.0)
        sd_diff = float(np.sqrt(float(m["sd_star"]) ** 2 + sd_inc ** 2))
        if not np.isfinite(sd_diff) or sd_diff <= 0:
            return False
        return bool(gain > k * sd_diff)


@dataclass
class RunReport:
    arms: dict
    summary: pd.DataFrame
    manifest: dict

    def recommendation_is_supported(self) -> bool:
        return any(a.surface_can_resolve_its_optimum() for a in self.arms.values())


def _queue_frame(ctx, top=25) -> pd.DataFrame:
    gx = ctx.gx
    q = ctx.queue[:top]
    return pd.DataFrame(dict(
        rank=np.arange(1, len(q) + 1),
        freq_hz=gx[q, 0], amp_mA=gx[q, 1],
        posterior_mean=ctx.mu[q], posterior_sd=ctx.sd[q],
        optimistic_bound=ctx.mu[q] - ctx.meta["kappa"] * ctx.sd[q],
        expected_improvement=ACQ.expected_improvement(ctx.mu[q], ctx.sd[q], ctx.meta["incumbent_mu"]),
        n_reports=ctx.n_reports[q],
        safe=ctx.safe[q],
    ))


def _batch_frame(ctx) -> pd.DataFrame:
    rows = []
    for b_i, batch in enumerate(ctx.batches, start=1):
        for m in batch:
            rows.append(dict(batch=b_i, cell=int(m.index),
                             freq_hz=float(m.freq_hz), amp_mA=float(m.amp_mA),
                             posterior_mean=float(m.mu), posterior_sd=float(m.sd),
                             acquisition=float(m.acq), reason=str(m.reason),
                             exploration_fraction=float(m.exploration_fraction)))
    return pd.DataFrame(rows)


def run(design_csv, *, sites=DEFAULT_SITES, hemispheres=DEFAULT_HEMISPHERES,
        outdir=".", data_horizon=PLT.DATA_HORIZON, washin_min=PLT.WASHIN_MIN,
        render_figures=True, figure_backend="mpl", dpi=200, top_queue=25,
        strict=False, **ctx_kwargs) -> RunReport:
    """Fit every arm, emit tables and figures, and return a comparison summary.

    Parameters
    ----------
    design_csv
        Epoch-level design matrix (path or DataFrame) with ``amp_mA_Left`` / ``amp_mA_Right``
        and the primary-item columns each requested site needs.
    sites, hemispheres
        The cross product defines the arms. An arm whose columns are absent, or which has too
        few epochs to fit, is SKIPPED with its reason recorded in the manifest — unless
        ``strict``, in which case the error propagates.
    render_figures, figure_backend
        ``"mpl"`` writes PNG via matplotlib; ``"plotly"`` writes interactive HTML. Static export
        never goes through kaleido in this environment.

    Returns
    -------
    RunReport
        ``.arms`` maps arm label to :class:`ArmResult`; ``.summary`` is one row per arm;
        ``.manifest`` records the declared provenance, per-arm status and written files.
    """
    # `outdir=None` means IN-MEMORY ONLY: fit every arm and return the report without touching the
    # filesystem. The service layer (bravo_service.run_for_participant) needs exactly this — it
    # serializes the report to JSON for the browser, so writing CSVs and PNGs into the container
    # would be dead weight and would need cleaning up. Every write below is guarded on `outdir`.
    write_files = outdir is not None
    if write_files:
        os.makedirs(outdir, exist_ok=True)
    es = pd.read_csv(design_csv) if not isinstance(design_csv, pd.DataFrame) else design_csv.copy()
    arms, rows, skipped, written = {}, [], {}, []

    for site in sites:
        for hemi in hemispheres:
            label = f"{site}__{hemi}"
            try:
                ctx = PLT.build_context(es, hemisphere=hemi, primary_item=site,
                                        data_horizon=data_horizon, washin_min=washin_min,
                                        **ctx_kwargs)
            except (KeyError, ValueError) as exc:
                skipped[label] = f"{type(exc).__name__}: {exc}"
                if strict:
                    raise
                continue

            m = ctx.meta
            queue = _queue_frame(ctx, top=top_queue)
            batch = _batch_frame(ctx)
            stop = ACQ.check_stopping([m["mu_star"]], ctx.mu, ctx.sd, ctx.n_reports,
                                      incumbent_mu=m["incumbent_mu"])
            arm = ArmResult(site=site, hemisphere=hemi, ctx=ctx, batch=batch, queue=queue,
                            stopping=stop, meta=m)
            arms[label] = arm

            if write_files:
                for nm, df in (("queue", queue), ("batch", batch)):
                    p = os.path.join(outdir, f"stimopt_{nm}_{label}.csv")
                    df.to_csv(p, index=False)
                    written.append(p)
            if render_figures and write_files:
                written += _render(ctx, label, outdir, figure_backend, dpi)

            rows.append(dict(
                arm=label, site=site, hemisphere=hemi,
                n_epochs_fitted=m["n_epochs_fitted"], n_reports=m["n_reports_total"],
                incumbent_mu=m["incumbent_mu"],
                opt_freq_hz=m["x_star"][0], opt_amp_mA=m["x_star"][1],
                opt_posterior_mean=m["mu_star"], opt_posterior_sd=m["sd_star"],
                mu_span=m["mu_max"] - m["mu_min"], sd_median=float(np.median(ctx.sd)),
                # the decisive ratio: signal span relative to typical uncertainty
                signal_to_uncertainty=(m["mu_max"] - m["mu_min"]) / float(np.median(ctx.sd)),
                optimum_resolved=arm.surface_can_resolve_its_optimum(),
                safe_cells=m["n_safe"], safe_contiguous=m["safe_is_contiguous"],
                queue_size=m["queue_size"], stop=bool(stop.stop), stop_binding=stop.binding,
                kernel=m["kernel"],
            ))

    summary = pd.DataFrame(rows)
    if not summary.empty and write_files:
        p = os.path.join(outdir, "stimopt_arm_summary.csv")
        summary.to_csv(p, index=False)
        written.append(p)

    manifest = dict(data_horizon=str(data_horizon), washin_min=float(washin_min),
                    sites=list(sites), hemispheres=list(hemispheres),
                    n_arms_fitted=len(arms), skipped=skipped,
                    any_optimum_resolved=bool(summary["optimum_resolved"].any())
                    if not summary.empty else False,
                    files=[os.path.basename(f) for f in written])
    if not write_files:
        return RunReport(arms=arms, summary=summary, manifest=manifest)
    p = os.path.join(outdir, "stimopt_manifest.json")
    with open(p, "w") as fh:
        json.dump(manifest, fh, indent=2)
    return RunReport(arms=arms, summary=summary, manifest=manifest)


@dataclass
class TwoStageReport:
    """Result of a staged run: Stage 1, the gate, and Stage 2 if the gate licensed it."""

    stage1: object
    gate: object
    stage2: object
    manifest: dict = field(default_factory=dict)

    @property
    def frozen(self):
        return self.stage1.frozen

    def can_deploy_closed_loop(self) -> bool:
        """Did the gate license closed-loop configuration? ``False`` is a legitimate answer."""
        return bool(self.gate.passed)

    def describe(self) -> str:
        return "\n\n".join([self.stage1.frozen.describe(), self.gate.describe(),
                            self.stage2.describe()])


@dataclass
class LiveEvidence:
    """LFP evidence sourced from the platform, with everything needed to defend the choice.

    ``selected`` is the one cell handed to the gate. ``screen`` is every cell that was considered
    with its blocking reasons, and ``audit`` is every cell that could not even be built. Both
    non-selected frames are part of the result rather than debug output: a gate refusal caused by
    absent data and one caused by a real negative response are clinically different conclusions,
    and only these frames distinguish them.
    """

    selected: object = None
    selected_key: tuple | None = None
    selection_note: str = ""
    screen: object = None
    audit: object = None

    def describe(self) -> str:
        n_ok = 0 if self.screen is None or self.screen.empty else int(self.screen.deployable.sum())
        n_cells = 0 if self.screen is None else len(self.screen)
        if self.selected is None:
            return (f"no deployable LFP evidence: {n_ok} of {n_cells} response-capable cells passed "
                    f"screening. {self.selection_note}")
        return f"using {self.selection_note} ({n_ok} of {n_cells} cells deployable)"


def live_evidence(participant, *, energy_budget=None, pw_lookup=None, amp_ceiling=None,
                  channel=None, hemisphere=None, rate_hz=None, bands=None,
                  force_refresh=None, **build_kwargs) -> LiveEvidence:
    """Build, screen and select LFP evidence for a participant from platform data.

    This is the seam that lets the gate be evaluated against real recordings instead of against
    ``None``. Selection is either EXPLICIT — pass ``hemisphere`` and ``rate_hz`` (and ``channel``
    when several sensing channels exist) to demand the cell matching a specific configuration — or
    SCREENED, which ranks the deployable cells and takes the best. Explicit selection still reports
    the screen, so a caller pinning a cell can see whether it would have survived screening.

    ``energy_budget`` and ``pw_lookup`` are what make screening meaningful rather than cosmetic; see
    :func:`routines.lfp_evidence.screen_cells`. Without them the energy condition is skipped and the
    screen says so by leaving ``energy_cap_mA`` empty.
    """
    from .routines import lfp_evidence as EV, lfp_response as LR
    from . import adapter as AD

    ev, audit = AD.evidence_for_participant(
        participant, force_refresh=force_refresh,
        rates=([rate_hz] if rate_hz is not None else None),
        channels=([channel] if channel is not None else None),
        hemispheres=((hemisphere,) if hemisphere is not None else ("Left", "Right")),
        bands=bands, **build_kwargs)

    screen, best = EV.screen_cells(ev, response_fn=LR.assess_response,
                                   energy_budget=energy_budget, pw_lookup=pw_lookup,
                                   amp_ceiling=amp_ceiling)
    if hemisphere is not None and rate_hz is not None:
        sel, note = EV.select_for(ev, rate_hz=rate_hz, hemisphere=hemisphere, channel=channel)
        key = None if sel is None else next(
            k for k in ev if k[1] == hemisphere and np.isclose(float(k[2]), float(rate_hz))
            and (channel is None or k[0] == channel))
        return LiveEvidence(selected=sel, selected_key=key,
                            selection_note=f"explicitly requested: {note}",
                            screen=screen, audit=audit)
    if best is None:
        why = ("no cell survived screening" if not screen.empty
               else "no cell could even be built — see the audit")
        return LiveEvidence(selected=None, selected_key=None, selection_note=why,
                            screen=screen, audit=audit)
    return LiveEvidence(selected=ev[best], selected_key=best,
                        selection_note=f"screened best: {best[0]} {best[1]} @{best[2]:g} Hz",
                        screen=screen, audit=audit)


def run_two_stage(design_csv, *, hemispheres=DEFAULT_HEMISPHERES, primary_item="left_leg",
                  outdir=None, data_horizon=PLT.DATA_HORIZON, washin_min=PLT.WASHIN_MIN,
                  lfp=None, amp_limits=None, selected_bands=None, response_summary=None,
                  override_reason=None, override_by=None,
                  stage1_kwargs=None, gate_kwargs=None, stage2_kwargs=None) -> TwoStageReport:
    """Run the open-loop stage, the gate, and the closed-loop stage in that order.

    This is the entry point that honours the device's sequencing. It does not replace :func:`run`;
    see the module docstring for which to use.

    Parameters
    ----------
    design_csv
        Epoch-level design matrix (path or DataFrame), as :func:`run` takes.
    lfp
        A :class:`~StimOptimizer.routines.stage_gate.LfpEvidence`, or ``None``. Without it the
        gate's LFP-response condition is NOT ASSESSED and therefore blocks, because Adaptive
        Therapy relies on a control signal that moves with stimulation amplitude and that is a
        different question from whether the band tracks pain.
    amp_limits
        ``{hemisphere: (min_mA, max_mA)}`` proposed adaptive amplitude limits, checked by the gate
        against the delivered envelope and the declared ceiling. Omitted means the delivered
        envelope is used, which the gate reports as defaulted rather than checked.
    selected_bands
        Selected biomarker bands with their selection-corrected statistics, as
        ``routines/stage_gate.SelectedBand``. Supplying them adds two separately-reported gate
        conditions: whether any selected band lies inside the 8-30 Hz adaptive window (a DEVICE
        question) and whether an adaptive-capable one is statistically supported (a STATISTICAL
        question). They are kept apart because a band can fail either alone.
        ``stage_gate.RCS08_SELECTED_BANDS`` holds the current reconciled plate for this patient.
    response_summary
        An LFP-response verdict established outside this module, as
        ``routines/stage_gate.ResponseSummary``; ``stage_gate.RCS08_RESPONSE_SUMMARY`` holds the one
        computed on the real record. It takes precedence over any row-level test and is reported
        with its source.
    override_reason, override_by
        Record a clinician override of the gate's resolution condition. The reason is mandatory if
        an override is wanted at all; an override without a stated reason is indistinguishable from
        disabling the check and is refused by ``stage1_openloop.clinician_override``.
    outdir
        When given, Stage 1's slice summary and the gate's condition table are written there.
        ``None`` means in-memory only, the same convention :func:`run` uses.

    Returns
    -------
    TwoStageReport
        ``.can_deploy_closed_loop()`` is the headline. On this project's current data it is
        expected to be ``False``, and the reasons in ``.gate.refusals()`` are the useful output.
    """
    from . import stage1_openloop as S1
    from . import stage2_closedloop as S2
    from .routines import stage_gate as GATE

    s1 = S1.run_stage1(design_csv, hemispheres=hemispheres, primary_item=primary_item,
                       data_horizon=data_horizon, washin_min=washin_min,
                       **(stage1_kwargs or {}))
    frozen = s1.frozen
    if override_reason is not None:
        frozen = S1.clinician_override(frozen, reason=override_reason, by=override_by)
    # `selected_bands` and `response_summary` are named parameters here AND were reachable through
    # `gate_kwargs` before they were promoted, so both invocation styles exist in the wild and both
    # have to keep working. Splatting `gate_kwargs` alongside the explicit keywords raises
    # "got multiple values for keyword argument", so the two are merged instead. A caller that
    # supplies the same key by both routes gets an explicit error rather than a silent precedence
    # rule, because which value won would otherwise depend on an implementation detail.
    gk = dict(gate_kwargs or {})
    for name, value in (("selected_bands", selected_bands),
                        ("response_summary", response_summary)):
        if value is None:
            continue
        if name in gk:
            raise ValueError(
                f"{name} was supplied both as a run_two_stage argument and inside gate_kwargs. "
                "Pass it once; the named argument is the documented route.")
        gk[name] = value
    gate = GATE.evaluate_gate(frozen, lfp=lfp, amp_limits=amp_limits, **gk)
    s2 = S2.run_stage2(frozen, gate, lfp=lfp, **(stage2_kwargs or {}))

    written = []
    if outdir is not None:
        os.makedirs(outdir, exist_ok=True)
        if not s1.summary.empty:
            p = os.path.join(outdir, "stage1_slice_summary.csv")
            s1.summary.to_csv(p, index=False)
            written.append(p)
        p = os.path.join(outdir, "stage_gate_conditions.csv")
        pd.DataFrame([dict(condition=c.name, verdict=c.verdict, passed=c.passed,
                           overridden=c.overridden, detail=c.detail)
                      for c in gate.conditions]).to_csv(p, index=False)
        written.append(p)
        if not s2.policies.empty:
            p = os.path.join(outdir, "stage2_valid_policies.csv")
            s2.policies.to_csv(p, index=False)
            written.append(p)

    manifest = dict(
        data_horizon=str(data_horizon), washin_min=float(washin_min),
        primary_item=str(frozen.primary_item), hemispheres=list(hemispheres),
        incumbent_epoch=float(frozen.incumbent_epoch),
        incumbent_rate_hz=float(frozen.incumbent_rate_hz),
        incumbent_pw_us=frozen.incumbent_pw_us,
        n_slices_fitted=len(s1.slices), slices_skipped=dict(s1.skipped),
        frozen_resolved=bool(frozen.resolved), frozen_overridden=bool(frozen.overridden),
        gate_passed=bool(gate.passed),
        gate_conditions={c.name: c.verdict for c in gate.conditions},
        gate_failed=gate.failed_names(), gate_not_assessed=gate.not_assessed_names(),
        stage2_started=bool(s2.started), stage2_n_valid_policies=int(s2.n_valid),
        stage2_ranking_assessed=s2.ranking_assessed,
        files=[os.path.basename(f) for f in written])
    if outdir is not None:
        p = os.path.join(outdir, "two_stage_manifest.json")
        with open(p, "w") as fh:
            json.dump(manifest, fh, indent=2, default=str)
        manifest["files"].append(os.path.basename(p))
    return TwoStageReport(stage1=s1, gate=gate, stage2=s2, manifest=manifest)


def _render(ctx, label, outdir, backend, dpi):
    """Write the figure set for one arm. Returns the paths written."""
    out = []
    builders = ((1, PLT.mpl_fig1_posterior_surface), (2, PLT.mpl_fig2_acquisition_decomposition),
                (3, PLT.mpl_fig3_search_trajectory), (4, PLT.mpl_fig4_dual_model),
                (5, PLT.mpl_fig5_coverage_map)) if backend == "mpl" else \
               ((1, PLT.fig1_posterior_surface), (2, PLT.fig2_acquisition_decomposition),
                (3, PLT.fig3_search_trajectory), (4, PLT.fig4_dual_model),
                (5, PLT.fig5_coverage_map))
    PLT.apply_style()
    for n, fn in builders:
        try:
            fig = fn(ctx)
        except Exception as exc:                      # a broken panel must not lose the whole arm
            out.append(f"FAILED fig{n}_{label}: {type(exc).__name__}: {exc}")
            continue
        if backend == "mpl":
            p = os.path.join(outdir, f"stimopt_fig{n}_{label}.png")
            fig.savefig(p, dpi=dpi)
        else:
            p = os.path.join(outdir, f"stimopt_fig{n}_{label}.html")
            fig.write_html(p, include_plotlyjs="cdn")
        out.append(p)
    return out
