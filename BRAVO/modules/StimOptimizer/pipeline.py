"""One-patient runner for the StimOptimizer module.

Library mode only: no Django import, no template rendering, no kaleido. Mirrors the entry-point
shape of ``modules/Biomarkers/pipeline.py`` so the service layer can call it the same way.

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
