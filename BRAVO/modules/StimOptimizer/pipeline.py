'One-patient runner for the StimOptimizer module.'
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .routines import acquisition as ACQ
from .routines import adaptive_envelope as ENV
from .routines import objective as OBJ
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

    def surface_can_resolve_its_optimum(self, k: float = 1.0):
        'True only if the candidate BEATS the incumbent by more than the uncertainty of that.'
        m = self.meta
        gain = float(m["incumbent_mu"]) - float(m["mu_star"])          # >0 means candidate is better
        # THE SHARED RULE, from routines.resolution. The propagation and the three-state answer
        # used to be spelled out here, in stage1_openloop, in bravo_service and — incorrectly — in
        # the figure headline, which compared against the candidate's SD alone. Four copies of one
        # criterion is how a figure comes to contradict the verdict printed beside it.
        from .routines import resolution as _RES

        sd_diff = _RES.sd_of_difference(m.get("sd_star"), m.get("incumbent_sd"))
        if not np.isfinite(sd_diff) or sd_diff <= 0:
            # NOT `False`. Returning False here reported "this arm's advantage is too small to
            # call" for an arm whose difference could not be FORMED at all, and those two answers
            # ask opposite things of a reader: the first says collect more exposure at that cell,
            # the second says a posterior is degenerate and no amount of exposure helps until the
            # fit is repaired. Typically it means a stratum that never delivered the incumbent's
            # rate, so there is no data anywhere near the cell being compared. The stratum-level
            # method `stage1_openloop.JointStratum.resolves_its_optimum` already returns
            # `bool | None` for exactly this reason; this one now matches it.
            return None
        return _RES.is_resolved(gain, m.get("sd_star"), m.get("incumbent_sd"), k=k)


@dataclass
class RunReport:
    arms: dict
    summary: pd.DataFrame
    manifest: dict

    def recommendation_is_supported(self) -> bool:
        # `is True` rather than a bare truthiness test, so the new `None` state cannot be read as
        # support. An arm whose difference could not be formed has not supported anything.
        return any(a.surface_can_resolve_its_optimum() is True for a in self.arms.values())


def _queue_frame(ctx, top=25, *, delivered=None, hemisphere=None,
                 amp_ceiling=OBJ.AMP_HARD_LIMIT_MA) -> pd.DataFrame:
    """The exploration queue, annotated with whether each cell is actually ELIGIBLE to test.

    WHY THE ANNOTATION EXISTS. The queue and the in-clinic testing schedule are selected by
    OPPOSITE criteria, and presenting the queue alone invited a direct contradiction between two
    outputs of the same module. ``acquisition.exploration_queue`` returns cells that have NEVER been
    tested — that is what makes them informative, because a cell with no reports is where the
    surrogate is most uncertain. The safety filter that builds the clinic schedule requires the
    opposite: a (rate, amplitude, pulse width) combination this patient has ALREADY received, so
    that tolerability is established before the setting is programmed for a 60-second step.

    A queue cell is therefore normally NOT schedulable as it stands. That is not a defect in either
    component; it is the honest statement that the most informative setting and the most clearly
    tolerated setting are different settings, and moving to a novel combination is a clinical
    decision rather than something the optimizer may take on its own. The columns below let the
    panel say which is which instead of implying every queue row can be run tomorrow.

    ``delivered`` is the per-hemisphere settings census (``routines.adapter.settings_stream``
    output). Without it the eligibility columns are omitted rather than guessed.
    """
    gx = ctx.gx
    q = ctx.queue[:top]
    out = pd.DataFrame(dict(
        rank=np.arange(1, len(q) + 1),
        freq_hz=gx[q, 0], amp_mA=gx[q, 1],
        posterior_mean=ctx.mu[q], posterior_sd=ctx.sd[q],
        optimistic_bound=ctx.mu[q] - ctx.meta["kappa"] * ctx.sd[q],
        expected_improvement=ACQ.expected_improvement(ctx.mu[q], ctx.sd[q], ctx.meta["incumbent_mu"]),
        n_reports=ctx.n_reports[q],
        safe=ctx.safe[q],
    ))
    out["within_hard_limit"] = out["amp_mA"] <= float(amp_ceiling) + 1e-9
    # Can the device's closed-loop mode use this cell at all? (review S6, 2026-09-12.) The
    # flat search is not held to the adaptive envelope -- that is the PI's call and is not made
    # here -- but a 10-40 Hz cell at rank 1 must say it is one closed loop cannot use, since two
    # cards down the two-stage plan says the same rate was ruled out. ONE definition of the
    # minimum: `routines/adaptive_envelope.MIN_RATE_HZ`.
    out["adaptive_capable"] = out["freq_hz"] >= float(ENV.MIN_RATE_HZ)
    if delivered is None or hemisphere is None:
        return out

    d = pd.DataFrame(delivered)
    d = d[d["hemi"].astype(str) == str(hemisphere)]
    amp = pd.to_numeric(d.get("amp"), errors="coerce")
    rate = pd.to_numeric(d.get("rate"), errors="coerce")
    ok = amp.notna() & (amp > 0)
    lo, hi = (float(amp[ok].min()), float(amp[ok].max())) if ok.any() else (np.nan, np.nan)
    out["inside_delivered_envelope"] = out["amp_mA"].between(lo, hi)
    # Has this (rate, amplitude) pair ever been delivered on this side? Pulse width is not a queue
    # dimension, so this is a NECESSARY condition for schedulability and not a sufficient one — the
    # full joint (rate, amplitude, pulse width) check is the clinic's, once a pulse width is chosen
    # (the module's own sheet builder, routines/schedule.py, was deleted 2026-09-12 as unreached).
    # Reported as such rather than as a green light.
    pair = []
    for _, r in out.iterrows():
        m = ok & np.isclose(rate, float(r["freq_hz"])) & (np.abs(amp - float(r["amp_mA"])) <= 0.06)
        pair.append(int(m.sum()))
    out["prior_records_at_this_rate_and_amp"] = pair
    out["schedulable_without_new_clinical_signoff"] = (
        out["within_hard_limit"] & out["inside_delivered_envelope"]
        & (out["prior_records_at_this_rate_and_amp"] > 0))
    return out


def _batch_frame(ctx) -> pd.DataFrame:
    rows = []
    for b_i, batch in enumerate(ctx.batches, start=1):
        for m in batch:
            rows.append(dict(batch=b_i, cell=int(m.index),
                             freq_hz=float(m.freq_hz), amp_mA=float(m.amp_mA),
                             posterior_mean=float(m.mu), posterior_sd=float(m.sd),
                             acquisition=float(m.acq), reason=str(m.reason),
                             exploration_fraction=float(m.exploration_fraction),
                             # review S6: whether closed loop could use this cell; see _queue_frame
                             adaptive_capable=bool(float(m.freq_hz) >= float(ENV.MIN_RATE_HZ))))
    return pd.DataFrame(rows)


def run(design_csv, *, sites=DEFAULT_SITES, hemispheres=DEFAULT_HEMISPHERES,
        delivered_census=None, safety_ceiling_by_hemisphere=None,
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
    safety_ceiling_by_hemisphere
        ``{hemisphere: (ceiling_mA, provenance)}`` from ``safety_ceiling.ceilings_by_hemisphere``
        (2026-09-12): the PI-stated current above which each side is not acceptable, the
        severity-3 seed of that side's safety model. Absent, every arm uses the module hard limit
        with a provenance that says no ceiling was stated.

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
            kw = dict(ctx_kwargs)
            if safety_ceiling_by_hemisphere and hemi in safety_ceiling_by_hemisphere:
                kw.update(safety_ceiling=safety_ceiling_by_hemisphere[hemi])
            try:
                ctx = PLT.build_context(es, hemisphere=hemi, primary_item=site,
                                        data_horizon=data_horizon, washin_min=washin_min,
                                        **kw)
            except (KeyError, ValueError) as exc:
                skipped[label] = f"{type(exc).__name__}: {exc}"
                if strict:
                    raise
                continue

            m = ctx.meta
            queue = _queue_frame(ctx, top=top_queue, delivered=delivered_census,
                                 hemisphere=hemi)
            batch = _batch_frame(ctx)
            # NO batch history (review S5, 2026-09-12): batches are proposed here, never run in
            # sequence, so the plateau condition has no history to read. The one-item history
            # this used to pass made `stop` a constant False and `stop_binding` read "plateau"
            # as if that condition had been assessed and failed; it now reads that the plateau
            # condition is not assessable, and `plateau_met` is None.
            stop = ACQ.check_stopping([], ctx.mu, ctx.sd, ctx.n_reports,
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
    #: Every cell that was built, keyed ``(channel, hemisphere, rate_hz)`` (2026-09-12, review
    #: S3), so a caller can pick one cell PER SIDE from the same build rather than rebuild.
    cells: dict | None = None

    def describe(self) -> str:
        n_ok = 0 if self.screen is None or self.screen.empty else int(self.screen.deployable.sum())
        n_cells = 0 if self.screen is None else len(self.screen)
        if self.selected is None:
            return (f"no deployable LFP evidence: {n_ok} of {n_cells} response-capable cells passed "
                    f"screening. {self.selection_note}")
        return f"using {self.selection_note} ({n_ok} of {n_cells} cells deployable)"


def live_evidence(participant, *, amp_ceiling=None,
                  channel=None, hemisphere=None, rate_hz=None, bands=None,
                  force_refresh=None, inputs=None, pain_positive_by_channel=None,
                  stim_rings_by_side=None,
                  **build_kwargs) -> LiveEvidence:
    'Implementation details are defined by the code and its regression contracts.'
    from .routines import lfp_evidence as EV, lfp_response as LR
    from . import adapter as AD

    # `inputs` is the already-built (sensed frame, epochs) pair, or None to build it here; see
    # `adapter.evidence_for_participant`.
    ev, audit = AD.evidence_for_participant(
        participant, force_refresh=force_refresh,
        rates=([rate_hz] if rate_hz is not None else None),
        channels=([channel] if channel is not None else None),
        hemispheres=((hemisphere,) if hemisphere is not None else ("Left", "Right")),
        bands=bands, inputs=inputs, **build_kwargs)

    screen, best = EV.screen_cells(ev, response_fn=LR.assess_response, amp_ceiling=amp_ceiling,
                                   pain_positive_by_channel=pain_positive_by_channel,
                                   stim_rings_by_side=stim_rings_by_side)
    if hemisphere is not None and rate_hz is not None:
        sel, note = EV.select_for(ev, rate_hz=rate_hz, hemisphere=hemisphere, channel=channel)
        key = None if sel is None else next(
            k for k in ev if k[1] == hemisphere and np.isclose(float(k[2]), float(rate_hz))
            and (channel is None or k[0] == channel))
        return LiveEvidence(selected=sel, selected_key=key,
                            selection_note=f"explicitly requested: {note}",
                            screen=screen, audit=audit, cells=ev)
    if best is None:
        why = ("no cell survived screening" if not screen.empty
               else "no cell could even be built — see the audit")
        return LiveEvidence(selected=None, selected_key=None, selection_note=why,
                            screen=screen, audit=audit, cells=ev)
    return LiveEvidence(selected=ev[best], selected_key=best,
                        selection_note=f"screened best: {best[0]} {best[1]} @{best[2]:g} Hz",
                        screen=screen, audit=audit, cells=ev)


def select_for_side(ev_: LiveEvidence, hemisphere, rate_hz, *, channel=None) -> tuple:
    """One side's cell out of a :class:`LiveEvidence`: ``(evidence or None, key or None, note)``.

    Review S3 (2026-09-12): the gate judges each frozen side on its own evidence, so the cell
    handed to it for the Right side must be a Right-side cell. The pick is the screen's own
    ranking restricted to that side and rate (``lfp_evidence.best_deployable``). When the build
    carried no cells at all (a stand-in evidence object without ``cells``), the one selected cell
    is attributed to the side its key names and to no other.
    """
    h = str(hemisphere)
    cells = getattr(ev_, "cells", None)
    screen = getattr(ev_, "screen", None)
    if cells is not None and screen is not None and len(screen) and "hemisphere" in screen.columns:
        from .routines import lfp_evidence as EV
        key = EV.best_deployable(screen, hemisphere=h, rate_hz=rate_hz, channel=channel)
        if key is not None and key in cells:
            lat = str(getattr(cells[key], "laterality", "") or "")
            # A contralateral pairing (sensing on the other side's contact, driving THIS side's
            # current) is one the screen ranks below every ipsilateral cell and selects only when
            # no ipsilateral cell passes; it needs a contralateral sensing configuration on the
            # device, so it is named rather than left to be read off the contact's name.
            side_note = (" (a CONTRALATERAL sensing contact: no contact on this side passed the "
                         "screen at this rate)" if lat == "contralateral" else "")
            return cells[key], key, (f"screened best on the {h} side: {key[0]} {key[1]} "
                                     f"@{float(key[2]):g} Hz{side_note}")
        n_side = int((screen["hemisphere"].astype(str) == h).sum())
        if n_side == 0:
            return None, None, f"no cell could be built for the {h} side at {float(rate_hz):g} Hz"
        return None, None, (f"no deployable cell on the {h} side at {float(rate_hz):g} Hz "
                            f"({n_side} screened, none passed)")
    key = getattr(ev_, "selected_key", None)
    if getattr(ev_, "selected", None) is not None and key is not None and str(key[1]) == h:
        return ev_.selected, tuple(key), str(getattr(ev_, "selection_note", ""))
    if getattr(ev_, "selected", None) is not None and key is None:
        return ev_.selected, None, (f"{getattr(ev_, 'selection_note', '')} (no side named on "
                                    f"the cell; attributed to the {h} side)")
    return None, None, (f"no cell selected for the {h} side: "
                        f"{getattr(ev_, 'selection_note', '') or 'nothing selected'}")


def run_two_stage(design_csv, *, hemispheres=DEFAULT_HEMISPHERES, primary_item="left_leg",
                  outdir=None, data_horizon=PLT.DATA_HORIZON, washin_min=PLT.WASHIN_MIN,
                  lfp=None, amp_limits=None, selected_bands=None, response_summary=None,
                  override_reason=None, override_by=None,
                  explore_outside_adaptive_reason=None, explore_outside_adaptive_by=None,
                  explore_outside_adaptive_requested=None,
                  stage1_kwargs=None, gate_kwargs=None, stage2_kwargs=None) -> TwoStageReport:
    'Implementation details are defined by the code and its regression contracts.'
    from . import stage1_openloop as S1
    from . import stage2_closedloop as S2
    from .routines import stage_gate as GATE

    s1 = S1.run_stage1(design_csv, hemispheres=hemispheres, primary_item=primary_item,
                       data_horizon=data_horizon, washin_min=washin_min,
                       explore_outside_reason=explore_outside_adaptive_reason,
                       explore_outside_by=explore_outside_adaptive_by,
                       explore_outside_requested=explore_outside_adaptive_requested,
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
    # Preserve the behavior covered by the regression tests.
    if callable(lfp):
        lfp = lfp(frozen)
    gate = GATE.evaluate_gate(frozen, lfp=lfp, amp_limits=amp_limits, **gk)
    # See the synthetic regression tests for this behavior.
    s2kw = dict(stage2_kwargs or {})
    if "ceiling_mA" in gk and "ceiling_mA" not in s2kw:
        s2kw["ceiling_mA"] = gk["ceiling_mA"]
    s2 = S2.run_stage2(frozen, gate, lfp=lfp, **s2kw)

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


def run_two_stage_live(participant, *, amp_ceiling=None, channel=None, hemisphere=None,
                       rate_hz=None, bands=None, force_refresh=None, request_data=None,
                       washin_min=1.0, design=None, stream=None, evidence_inputs=None,
                       pain_positive_by_channel=None, stim_rings_by_side=None,
                       **two_stage_kwargs) -> TwoStageReport:
    'Implementation details are defined by the code and its regression contracts.'
    from . import adapter as _AD

    gk = dict(two_stage_kwargs.pop("gate_kwargs", None) or {})
    gk.setdefault("pain_positive_by_channel", pain_positive_by_channel)
    two_stage_kwargs["gate_kwargs"] = gk
    if design is None:
        design = _AD.build_design_matrix(participant, request_data, washin_min=washin_min,
                                         stream=stream)
    box = {}

    def _select_after_freezing(frozen):
        'Implementation details are defined by the code and its regression contracts.'
        # A NaN rate is Stage 1's "no adaptive-capable setting can be recommended" (2026-09-12);
        # there is no rate to pin evidence to on that side, so it is left out here and the gate's
        # rate condition refuses on it.
        rate_by_side = {str(hs.hemisphere): float(hs.rate_hz) for hs in frozen.settings
                        if getattr(hs, "rate_hz", None) is not None
                        and np.isfinite(float(hs.rate_hz))}
        rates = sorted(set(rate_by_side.values()))
        box["frozen_rates"] = rates
        box["frozen_rates_by_side"] = dict(rate_by_side)
        if not rate_by_side:
            box["ev"] = LiveEvidence(
                selected=None, selected_key=None,
                selection_note=("Stage 1 recommended no adaptive-capable rate on any side, "
                                "so there is no rate to pin the LFP evidence to"))
            return None
        pins = {h: (float(rate_hz) if rate_hz is not None else r) for h, r in rate_by_side.items()}
        sides = [h for h in pins if hemisphere is None or str(hemisphere) == h]
        box["pinned_rate_hz_by_side"] = {h: pins[h] for h in sides}
        box["pinned_rate_hz"] = (float(pins[sides[0]])
                                 if sides and len({pins[h] for h in sides}) == 1 else None)
        # One build per distinct pinned rate, both sides' cells at once; `evidence_inputs` is
        # the (sensed frame, epochs) pair the service layer already built for the readiness
        # screen, or None to build it here (2026-09-12).
        by_rate = {}
        for r in sorted({pins[h] for h in sides}):
            by_rate[r] = live_evidence(participant, amp_ceiling=amp_ceiling, channel=channel,
                                       hemisphere=None, rate_hz=r, bands=bands,
                                       force_refresh=force_refresh, stream=stream,
                                       inputs=evidence_inputs,
                                       pain_positive_by_channel=pain_positive_by_channel,
                                       stim_rings_by_side=stim_rings_by_side)
        per, chosen = {}, {}
        for h in sides:
            sel, key, note = select_for_side(by_rate[pins[h]], h, pins[h], channel=channel)
            per[h] = dict(selected=sel is not None, selected_key=(list(key) if key else None),
                          selection_note=note, pinned_rate_hz=float(pins[h]))
            if sel is not None:
                chosen[h] = sel
        box["by_side"] = per
        # The screen and audit frames of every build, for the manifest's counts.
        screens = [e.screen for e in by_rate.values() if e.screen is not None and len(e.screen)]
        audits = [e.audit for e in by_rate.values() if e.audit is not None and len(e.audit)]
        first = next((h for h in ("Left", "Right") if h in chosen), None)
        box["ev"] = LiveEvidence(
            selected=(chosen[first] if first else None),
            selected_key=(tuple(per[first]["selected_key"]) if first else None),
            selection_note="; ".join(f"{h}: {per[h]['selection_note']}" for h in sides),
            screen=(pd.concat(screens, ignore_index=True) if screens else
                    next(iter(by_rate.values())).screen),
            audit=(pd.concat(audits, ignore_index=True) if audits else
                   next(iter(by_rate.values())).audit))
        return chosen if chosen else None

    rep = run_two_stage(design, lfp=_select_after_freezing, **two_stage_kwargs)
    ev = box.get("ev") or LiveEvidence()
    by_side = dict(box.get("by_side") or {})
    n_sides = len(by_side)
    n_selected = sum(1 for v in by_side.values() if v.get("selected"))

    # The provenance of the evidence travels with the report. Without this a reader cannot tell
    # which of the two refusals above they are looking at, and the gate's own text cannot say,
    # because the gate is handed either a cell or nothing and never learns why.
    rep.manifest["lfp_evidence"] = {
        "source": "live",
        "pinned_rate_hz": box.get("pinned_rate_hz"),
        "pinned_rate_hz_by_side": box.get("pinned_rate_hz_by_side"),
        "frozen_rates_hz": box.get("frozen_rates"),
        "frozen_rates_hz_by_side": box.get("frozen_rates_by_side"),
        "selected": ev.selected is not None,
        # The FIRST side's cell (Left before Right) under the historical keys; every side's own
        # cell is under `selected_by_side` (review S3).
        "selected_key": (list(ev.selected_key) if ev.selected_key else None),
        "selected_by_side": by_side,
        "selection_note": ev.selection_note,
        "n_cells_screened": (0 if ev.screen is None else int(len(ev.screen))),
        "n_cells_unbuildable": (0 if ev.audit is None else int(len(ev.audit))),
        # WHY the unbuildable cells could not be built, as the audit frame states it, counted by
        # distinct reason. Without this a reader of the report sees "12 could not be built" and
        # cannot tell "no recording exists at the frozen rate" from "recordings exist and are
        # unusable", which are different instructions to the clinic.
        "unbuildable_reasons": (
            {str(k): int(v) for k, v in
             ev.audit["reason_unusable"].astype(str).value_counts().items()}
            if ev.audit is not None and len(ev.audit) and "reason_unusable" in ev.audit.columns
            else {}),
        "refusal_class": (
            "evidence_selected" if (n_sides and n_selected == n_sides)
            else ("evidence_missing_on_some_sides" if n_selected
                  else ("no_adaptive_capable_rate" if not box.get("frozen_rates")
                        else ("no_cell_deployable" if (ev.screen is not None and len(ev.screen))
                              else "no_cell_buildable")))),
        "note": ("`no_cell_buildable` means no configuration had enough data to form the "
                 "measurement at all, and `no_cell_deployable` means cells were built and screened "
                 "and none passed; `evidence_missing_on_some_sides` means at least one frozen side "
                 "has a deployable cell and at least one has none, and the gate marks the side "
                 "without one NOT ASSESSED. A gate refusal reads identically in these cases, so "
                 "this field is what distinguishes absent data from a measured negative."),
    }
    return rep
