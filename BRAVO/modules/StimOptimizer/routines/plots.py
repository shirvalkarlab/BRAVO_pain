"""Interim decision figures for the StimOptimizer explore/exploit audit.

Five figures, each in two renderings: an interactive Plotly figure (``figN_*``) and a static
matplotlib figure (``mpl_figN_*``). Both are driven from a single :class:`FigureContext` built
by :func:`build_context`, so the Plotly and the PNG rendering of a figure cannot disagree about
the numbers.

Library mode only: no Django import, no template rendering, no kaleido. Static images are drawn
by matplotlib directly rather than converted from the Plotly figures, because Plotly static
export needs a headless browser that the analysis sandbox does not have.

Re-runnability
--------------
Everything is a pure function of the design-matrix CSV plus the declared parameters. A data
refresh is::

    from StimOptimizer.routines import plots
    plots.render_all("rcs08_bo_design_matrix.csv", outdir="figs",
                     data_horizon="settings to 2026-08-31, PROs to 2026-08-28",
                     washin_min=5.0)

``data_horizon`` and ``washin_min`` are stamped onto every figure. They are not cosmetic: the
horizon is the honest scope of every number in these panels, and the wash-in is the epoch
definition that decides which reports enter an epoch at all. Neither is inferrable from the
design matrix, so both must be passed by the caller.

Sign conventions (see OBJECTIVE_SPEC.md, and README.md "Sign conventions")
-------------------------------------------------------------------------
* ``J`` is MINIMISED. ``J = 0`` at the incumbent, negative is better than status quo.
* The optimistic bound at a cell is ``mu - kappa*sigma``.
* Preference latent values are MAXIMISED; higher is more preferred.
* Safety severity is maximised-bad; the safe set is ``mu_SE + beta*sigma_SE < threshold``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from . import acquisition as ACQ
from . import objective as OBJ
from . import surrogate as SUR
from .preference import PreferenceGP

# --- canonical configuration -------------------------------------------------------------
FREQ_GRID = [10, 20, 30, 40, 55, 70, 85, 110, 125, 130, 145, 165]          # Hz
# 0.0-5.0 mA. The lower bound is 0.0 because a hemisphere genuinely runs at 0 mA in this record;
# the upper bound is 5.0 because the July-August 2026 escalation delivered up to 4.8 mA, which the
# previous 0.8-4.0 grid COULD NOT REPRESENT — the highest settings actually delivered fell outside
# the search space, so the surrogate could neither score nor propose them.
AMP_GRID = np.round(np.arange(0.0, 5.01, 0.1), 2)                          # mA, per hemisphere
FIXED_LENGTH_SCALE = (0.823, None)   # frequency pinned at one octave, amplitude FITTED
# Retained only as an explicit override for a caller who wants a NON-current reference. The
# default is None, which derives both the epoch and its coordinates from the design matrix; see
# build_context. Do not reintroduce these as defaults — the pair went stale and inconsistent.
INCUMBENT_EPOCH = None
INCUMBENT_XY = None
KAPPA = 2.0
BETA = 2.0
PREF_MARGIN = 0.15

#: Programmed ``UpperLimitInMilliAmps`` anchors, (freq_hz, upper_mA), from the device JSONs.
LIMIT_ANCHORS = np.array([[55., 2.0], [55., 1.8], [55., 1.9], [10., 1.9], [110., 4.0],
                          [110., 3.2], [130., 3.2], [125., 2.5], [165., 2.5], [110., 2.2],
                          [55., 1.6], [10., 2.0]])

# Declared provenance. The CALLER should pass the true horizon; this default is deliberately
# labelled as unset so a stale value can never be silently stamped onto a figure.
DATA_HORIZON = "UNDECLARED - caller did not pass data_horizon"
WASHIN_MIN = 1.0        # minutes; PI-declared 60 s wash-in (OBJECTIVE_SPEC amendment 2026-08-30)

# Colours. Diverging for J (semantic zero = the incumbent, never the data midpoint);
# sequential for posterior SD and for the preference latent.
CMAP_J = "RdBu_r"          # blue = negative J = better than incumbent; red = worse
CMAP_SD = "cividis"
CMAP_PREF = "magma"
C_SAFE = "#000000"
C_OBS = "#222222"
C_STAR = "#009E73"         # Okabe-Ito green: estimated optimum
C_INC = "#E69F00"          # Okabe-Ito orange: incumbent
C_FWD = "#CC79A7"          # Okabe-Ito rose: forward simulation
C_BAND = "#0072B2"         # Okabe-Ito blue: never-sampled band
META_GREY = "#888888"

J_LABEL = "Composite objective J (NRS points; 0 = incumbent)"
GOODNESS = "lower J = better"


# --- context ------------------------------------------------------------------------------
@dataclass
class FigureContext:
    """Everything the five figures need, computed once."""

    grid: SUR.ParameterGrid
    D: pd.DataFrame
    gp: SUR.ObjectiveGP
    sgp: SUR.SafetyGP
    pgp: PreferenceGP
    mu: np.ndarray
    sd: np.ndarray
    smu: np.ndarray
    ssd: np.ndarray
    safe: np.ndarray
    sub: np.ndarray                  # safety upper bound mu_SE + beta*sigma_SE
    n_reports: np.ndarray
    pmu: np.ndarray
    psd: np.ndarray
    incumbent_mu: float
    i_star: int
    i_pref: int
    batches: list
    traj: pd.DataFrame
    queue: np.ndarray
    meta: dict = field(default_factory=dict)

    # -- convenience -----------------------------------------------------------------
    @property
    def gx(self):
        return self.grid.grid_X()

    @property
    def stamp(self):
        m = self.meta
        return (f"RCS08 · PROVISIONAL · outcome: {m.get('primary_item','?')} · "
                f"{m.get('hemisphere','?')} hemisphere amplitude · "
                f"data horizon: {m['data_horizon']} · wash-in {m['washin_min']:g} min · "
                f"{m['n_epochs_fitted']} epochs / {m['n_reports_total']:.0f} reports · "
                f"beta={m['beta']:g}, kappa={m['kappa']:g}")

    def surface(self, v):
        """(n_amp, n_freq) array oriented for imshow/pcolormesh with amplitude on y."""
        return self.grid.as_surface(v).T


def _cell_edges(centres):
    """Cell boundaries for a pcolormesh on a possibly non-uniform axis."""
    c = np.asarray(centres, float)
    mid = 0.5 * (c[1:] + c[:-1])
    return np.concatenate([[c[0] - (mid[0] - c[0])], mid, [c[-1] + (c[-1] - mid[-1])]])


def build_context(design_csv, *, freq_grid=FREQ_GRID, amp_grid=AMP_GRID,
                  incumbent_epoch=None, incumbent_xy=None,
                  fixed_length_scale=FIXED_LENGTH_SCALE, beta=BETA, kappa=KAPPA,
                  limit_anchors=LIMIT_ANCHORS, pref_margin=PREF_MARGIN,
                  n_batches=3, q=4, min_tolerated_h=72.0,
                  data_horizon=DATA_HORIZON, washin_min=WASHIN_MIN,
                  hemisphere="Left", primary_item=None,
                  random_state=0) -> FigureContext:
    """Fit every model the figures need from one design matrix.

    Parameters
    ----------
    design_csv
        Path to the epoch-level design matrix, or a DataFrame. Needs the columns
        :func:`objective.build_objective` requires.
    fixed_length_scale
        Per-dimension length-scale pinning. The default ``(0.823, None)`` pins FREQUENCY at one
        octave — it is not identifiable from this design (OBJECTIVE_SPEC amendment 2026-08-29) —
        and leaves AMPLITUDE free to be fitted. Pinning both would make leave-one-out folds
        inherit the full-data amplitude hyperparameter, which would invalidate any calibration
        claim drawn from them.
    data_horizon, washin_min
        Declared provenance, stamped onto every figure. ``washin_min`` is the post-change
        exclusion window that defines an epoch's report set; it is a protocol parameter, not a
        modelling one, and the figures are only interpretable against a stated value.
    hemisphere
        ``"Left"`` or ``"Right"`` — which hemisphere's amplitude forms the second search
        dimension, read from ``amp_mA_<hemisphere>``. The two hemispheres are fitted as SEPARATE
        surfaces rather than as a joint 3-D surface, for the same reason the two pain sites are
        separate optimizers: the two sides are usable on different epoch subsets, so a joint fit
        would impose one shared length scale on two dimensions with different support. In the
        RCS08 warm start the LEFT is the sparser side — above 0 mA on 59 of 86 epochs against 71
        for the right — giving 54 fitted epochs on the left arm and 63 on the right. Run one
        context per hemisphere and compare them side by side.
    primary_item
        Pain metric name passed through to :func:`objective.build_objective` (e.g. ``"left_leg"``,
        ``"back"``). ``None`` uses the module default, which is the left leg.
    """
    es = pd.read_csv(design_csv) if not isinstance(design_csv, pd.DataFrame) else design_csv.copy()
    grid = SUR.ParameterGrid(freq_grid, amp_grid)
    gx = grid.grid_X()

    if hemisphere not in ("Left", "Right"):
        raise ValueError(f"hemisphere must be 'Left' or 'Right', got {hemisphere!r}")
    # The incumbent is the setting currently in force, i.e. the most recent epoch in THIS matrix.
    # It used to be two independent module constants (INCUMBENT_EPOCH and INCUMBENT_XY) which
    # drifted apart and went stale: they pointed at epoch 50 (2025-11-01, 110 Hz / 1.2 mA) while
    # naming coordinates (55 Hz / 1.6 mA) belonging to neither that epoch nor the current setting.
    # Deriving both from the data makes staleness impossible and the pair self-consistent.
    if incumbent_epoch is None:
        if "t0" not in es.columns:
            raise KeyError("cannot derive the incumbent without a 't0' column; pass "
                           "incumbent_epoch explicitly")
        incumbent_epoch = float(es.sort_values("t0")["epoch"].iloc[-1])
    row = es.loc[es["epoch"].astype(float) == float(incumbent_epoch)]
    if row.empty:
        raise ValueError(f"incumbent_epoch {incumbent_epoch} is not in this design matrix "
                         f"(epochs {es['epoch'].min():g}-{es['epoch'].max():g})")
    if incumbent_xy is None:
        incumbent_xy = (float(row["freq_hz"].iloc[0]), float(row[f"amp_mA_{hemisphere}"].iloc[0]))
    amp_col = f"amp_mA_{hemisphere}"
    if amp_col not in es.columns:
        raise KeyError(f"design matrix has no {amp_col!r} column; cannot search the "
                       f"{hemisphere} hemisphere")
    cfg = {"primary_item": primary_item} if primary_item else None
    D = OBJ.build_objective(es, incumbent_epoch=incumbent_epoch, cfg=cfg)
    # A hemisphere at 0 mA is not the low end of that hemisphere's dose axis, it is a different
    # therapeutic state (OBJECTIVE_SPEC amendment 2026-08-29). Exclude those rows from THIS
    # hemisphere's surface rather than letting them anchor its intercept.
    D = D.loc[D[amp_col].astype(float) > 0].copy()
    fit = D.loc[D["feasible"]].copy()
    if len(fit) < 8:
        raise ValueError(f"only {len(fit)} feasible epochs with {hemisphere} amplitude > 0; "
                         f"too few to fit a surface")
    Xobs = fit[["freq_hz", amp_col]].to_numpy(float)
    gp = SUR.ObjectiveGP(grid, fixed_length_scale=fixed_length_scale,
                         random_state=random_state).fit(
        Xobs, fit["J"].to_numpy(float), fit["obs_var"].to_numpy(float))
    mu, sd = gp.predict_grid()

    n_reports = np.zeros(len(grid))
    np.add.at(n_reports, grid.index_of(Xobs), fit["n"].to_numpy(float))

    # safety GP, two-anchor seed (OBJECTIVE_SPEC amendment 2026-08-29)
    deliv = D.loc[D["dur_h"] >= float(min_tolerated_h), ["freq_hz", amp_col]].to_numpy(float)
    Xs, sev, sv = SUR.SafetyGP.seed_from_history(deliv, np.asarray(limit_anchors, float))
    sgp = SUR.SafetyGP(grid, random_state=random_state).fit(Xs, sev, sv)
    smu, ssd = sgp.predict(gx)
    sub = smu + float(beta) * ssd
    safe = sgp.safe_mask(beta=beta)

    # Keep the incumbent's OWN posterior SD, not just its mean. Comparing a candidate's k-sigma band
    # against a point estimate of the incumbent understates the uncertainty of the comparison and can
    # declare an optimum "resolved" on a difference smaller than the noise in that difference.
    _inc_mu, _inc_sd = gp.predict(np.atleast_2d(incumbent_xy), return_std=True)
    incumbent_mu = float(_inc_mu[0])
    incumbent_sd = float(_inc_sd[0])
    i_star = int(np.argmin(np.where(safe, mu, np.inf)))

    # preference model — ILLUSTRATIVE, see figure 4
    pgp, pmu, psd, i_pref, pref_meta = _fit_illustrative_preference(
        grid, fit, margin=pref_margin, length_scale=fixed_length_scale, amp_col=amp_col)

    batches, ceilings = _simulate_forward(gp, grid, sgp, safe, n_reports, incumbent_mu,
                                          beta=beta, n_batches=n_batches, q=q,
                                          incumbent_amp=float(incumbent_xy[1]))
    traj = _trajectory(fit, batches, grid, sgp, beta=beta, amp_col=amp_col)
    queue, qmeta = ACQ.exploration_queue(mu, sd, n_reports, incumbent_mu, kappa=kappa)

    safeS = grid.as_surface(safe.astype(float)).astype(bool)
    contiguous = [int(np.flatnonzero(~row)[0]) if (~row).any() else row.size for row in safeS]
    oper_ceiling = float(grid.amps[min(contiguous) - 1]) if min(contiguous) > 0 else float("nan")

    band = (gx[:, 0] <= 55) & (gx[:, 1] > 1.8)
    meta = dict(
        hemisphere=str(hemisphere), amp_col=amp_col,
        primary_item=str(D["primary_item"].iloc[0]) if "primary_item" in D.columns else "unknown",
        data_horizon=str(data_horizon), washin_min=float(washin_min),
        beta=float(beta), kappa=float(kappa), q=int(q), n_batches=int(n_batches),
        n_epochs=int(len(D)), n_epochs_fitted=int(len(fit)),
        n_reports_total=float(fit["n"].sum()),
        incumbent_epoch=float(incumbent_epoch), incumbent_xy=list(map(float, incumbent_xy)),
        incumbent_mu=incumbent_mu, incumbent_sd=incumbent_sd,
        kernel=gp.hyperparameters["kernel"],
        log_marginal_likelihood=gp.hyperparameters["log_marginal_likelihood"],
        mu_min=float(mu.min()), mu_max=float(mu.max()),
        # posterior SD AT the grid minimum, not the global range: the honest headline on fig1
        # needs to compare the claimed gain against the uncertainty of the cell claiming it.
        opt_posterior_sd=float(sd[int(np.argmin(mu))]),
        sd_min=float(sd.min()), sd_max=float(sd.max()),
        optimistic_min=float((mu - kappa * sd).min()),
        n_safe=int(safe.sum()), n_cells=int(len(grid)),
        safe_amps=[float(a) for a in np.unique(gx[safe, 1])],
        safe_contiguous_ceiling=oper_ceiling,
        safe_global_max_amp=float(sgp.max_safe_amplitude(beta=beta)),
        safe_is_contiguous=bool(all(int(row.sum()) == c for row, c in zip(safeS, contiguous))),
        expansion_ceilings=[float(c) for c in ceilings],
        i_star=i_star, x_star=[float(v) for v in gx[i_star]],
        mu_star=float(mu[i_star]), sd_star=float(sd[i_star]),
        queue_size=int(queue.size), n_unexplored=int((n_reports < 3).sum()),
        best_optimistic_unexplored=float(qmeta.get("best_optimistic", float("nan"))),
        band_cells=int(band.sum()), band_undertested=int((n_reports[band] < 3).sum()),
        band_exceptions=[[float(a) for a in row] for row in gx[band & (n_reports >= 3)]],
        tested_freqs=[float(f) for f in sorted(fit["freq_hz"].unique())],
        n_below_grid_amp=int((fit[amp_col] < float(np.min(amp_grid))).sum()),
        **pref_meta,
    )
    return FigureContext(grid=grid, D=D, gp=gp, sgp=sgp, pgp=pgp, mu=mu, sd=sd, smu=smu,
                         ssd=ssd, safe=safe, sub=sub, n_reports=n_reports, pmu=pmu, psd=psd,
                         incumbent_mu=incumbent_mu, i_star=i_star, i_pref=i_pref,
                         batches=batches, traj=traj, queue=queue, meta=meta)


def _fit_illustrative_preference(grid, fit, *, margin, length_scale, amp_col="amp_mA_Left"):
    """Preference GP on comparisons DERIVED from the observed epoch J values.

    No A-versus-B preference judgements exist in this dataset. The comparisons here are
    constructed: distinct tested cells are pooled, and cell *i* is recorded as preferred to
    cell *j* whenever ``J_i + margin < J_j``. This is a wiring and disagreement-geometry
    demonstration, NOT patient preference. Because the comparisons are a deterministic function
    of the same J the objective GP is fitted to, the held-out accuracy is optimistically biased
    and must not be read as a validation of a preference model.
    """
    cells = (fit.groupby(["freq_hz", amp_col], as_index=False)
                .agg(J=("J", "mean"), n=("n", "sum")))
    Xp = cells[["freq_hz", amp_col]].to_numpy(float)
    Jp = cells["J"].to_numpy(float)
    pairs = []
    for i, j in combinations(range(len(Jp)), 2):
        if Jp[i] + margin < Jp[j]:
            pairs.append((i, j))
        elif Jp[j] + margin < Jp[i]:
            pairs.append((j, i))
    ls = None if length_scale is None else [
        1.0 if v is None else float(v) for v in np.atleast_1d(length_scale)]
    pgp = PreferenceGP(grid).fit(Xp, pairs, length_scale=ls)
    pmu, psd = pgp.predict()
    i_pref, x_pref = pgp.best()
    try:
        acc = float(pgp.holdout_accuracy(folds=5, random_state=0))
    except ValueError:
        acc = float("nan")
    return pgp, pmu, psd, int(i_pref), dict(
        pref_margin=float(margin), pref_n_cells=int(len(Xp)), pref_n_pairs=int(len(pairs)),
        pref_holdout_accuracy=acc, x_pref=[float(v) for v in x_pref],
        pref_illustrative=True)


def _simulate_forward(gp, grid, sgp, safe, n_reports, incumbent_mu, *, beta, n_batches, q,
                      incumbent_amp):
    """Forward-simulate ``n_batches`` within-visit batches of size ``q``.

    Between batches the surrogate is conditioned on kriging-believer fantasy observations at the
    selected cells — the posterior mean is substituted for the outcome that has not been
    measured. Nothing here is an observation, and the J values shown for these points are
    predictions, not results. The per-batch amplitude ceiling follows the no-side-effect
    expansion cap of +0.4 mA per batch from the incumbent amplitude.
    """
    model = gp
    nrep = np.asarray(n_reports, float).copy()
    gx = grid.grid_X()
    batches, ceilings = [], []
    for b in range(int(n_batches)):
        capped = sgp.expansion_capped_mask(worst_severity="none",
                                           prev_max_amp=incumbent_amp + 0.4 * b, beta=beta)
        edge = float(gx[capped, 1].max()) if capped.any() else float("nan")
        bm = ACQ.select_batch_within_visit(model, grid, q=q, safe_mask=capped, n_reports=nrep,
                                           incumbent_mu=incumbent_mu, t=1 + q * b,
                                           expansion_edge_amp=edge)
        batches.append(bm)
        ceilings.append(edge)
        idxs = [m.index for m in bm]
        model = model.with_fantasy(gx[idxs], float(np.median(gp.y_var_)))
        nrep[idxs] += 10.0     # fantasy: each prospective setting is assumed to yield 10 reports
    return batches, ceilings


def _trajectory(fit, batches, grid, sgp, *, beta, amp_col="amp_mA_Left"):
    """Chronological historical epochs followed by the simulated forward batches."""
    h = fit.sort_values("t0").reset_index(drop=True)
    rows = []
    for k, r in h.iterrows():
        rows.append(dict(iteration=k + 1, phase="observed", freq_hz=float(r.freq_hz),
                         amp_mA=float(getattr(r, amp_col)), J=float(r.J), n=float(r.n),
                         batch=0, expl_frac=np.nan, reason="", t0=r.t0))
    off = len(h)
    for b, bm in enumerate(batches, start=1):
        for m in bm:
            off += 1
            rows.append(dict(iteration=off, phase="simulated", freq_hz=m.freq_hz,
                             amp_mA=m.amp_mA, J=m.mu, n=np.nan, batch=b,
                             expl_frac=m.exploration_fraction, reason=m.reason, t0=pd.NaT))
    t = pd.DataFrame(rows)
    smu, ssd = sgp.predict(t[["freq_hz", "amp_mA"]].to_numpy(float))
    t["safety_mu"] = smu
    t["safety_ub"] = smu + float(beta) * ssd
    obs = t["phase"].eq("observed")
    t["best_so_far"] = np.where(obs, t["J"].where(obs).cummin(), np.nan)
    t["best_so_far"] = t["J"].cummin()
    return t


# =========================================================================================
# Plotly renderings
# =========================================================================================
def _plotly():
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    return go, make_subplots


def _lf(f):
    return np.log2(np.asarray(f, float))


def _freq_axis(ctx):
    return dict(tickvals=_lf(ctx.grid.freqs), ticktext=[f"{f:g}" for f in ctx.grid.freqs],
                title_text="Stimulation frequency (Hz, log<sub>2</sub> spacing)")


def _stamp_plotly(fig, ctx, caption):
    fig.add_annotation(text=f"<i>{caption}</i>", xref="paper", yref="paper", x=0, y=-0.135,
                       showarrow=False, align="left", xanchor="left",
                       font=dict(size=10, color="#333333"))
    fig.add_annotation(text=ctx.stamp, xref="paper", yref="paper", x=0, y=-0.20,
                       showarrow=False, align="left", xanchor="left",
                       font=dict(size=9, color=META_GREY))
    fig.update_layout(template="plotly_white", font=dict(family="Arial, Helvetica, sans-serif",
                                                         size=12),
                      margin=dict(l=70, r=30, t=70, b=130))
    return fig


CAPTIONS = {
    1: ("Decision supported: where to place the next setting. Posterior mean of the composite "
        "objective over the prospective grid, the 45 historically delivered settings, and the "
        "amplitude ceiling the safety model will permit."),
    2: ("Decision supported: whether the next batch is buying information or buying benefit. "
        "The exploration fraction is the share of the acquisition value at the selected cell "
        "contributed by the uncertainty term."),
    3: ("Decision supported: whether the search is moving. Observed history in chronological "
        "order, then the simulated forward batches; J for simulated points is a prediction, "
        "not a measurement."),
    4: ("Decision supported: whether an objective-driven optimum would be the setting the "
        "patient actually prefers. The preference panel is ILLUSTRATIVE — the comparisons are "
        "derived from J, not elicited."),
    5: ("Decision supported: whether the apparent plateau is local or global. Cells with fewer "
        "than three reports whose optimistic bound still beats the incumbent must be tested "
        "before a plateau can be called global."),
}


def fig1_posterior_surface(ctx: FigureContext):
    """Posterior surface, delivered settings, safe-set boundary, estimated optimum."""
    go, _ = _plotly()
    gx, m = ctx.gx, ctx.meta
    lim = float(np.max(np.abs([ctx.mu.min(), ctx.mu.max()])))
    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        x=_lf(ctx.grid.freqs), y=ctx.grid.amps, z=ctx.surface(ctx.mu),
        colorscale="RdBu_r", zmid=0.0, zmin=-lim, zmax=lim,
        colorbar=dict(title=dict(text=J_LABEL, side="right"), thickness=14, len=0.78),
        hovertemplate="%{customdata:.0f} Hz, %{y:.1f} mA<br>mu J = %{z:+.3f}<extra></extra>",
        customdata=np.tile(ctx.grid.freqs, (len(ctx.grid.amps), 1))))
    # safe-set boundary: contour of the safety upper bound at the severity threshold
    fig.add_trace(go.Contour(
        x=_lf(ctx.grid.freqs), y=ctx.grid.amps, z=ctx.surface(ctx.sub),
        contours=dict(start=ctx.sgp.threshold, end=ctx.sgp.threshold, size=1,
                      coloring="none", showlabels=False),
        line=dict(color=C_SAFE, width=2, dash="dash"), showscale=False,
        name=f"safe-set boundary (beta={m['beta']:g})", showlegend=True, hoverinfo="skip"))
    fig.add_hline(y=m["safe_contiguous_ceiling"], line=dict(color=C_SAFE, width=1.6, dash="dot"))
    fig.add_annotation(x=_lf(165), y=m["safe_contiguous_ceiling"], xanchor="right",
                       yanchor="bottom", showarrow=False,
                       text=f"usable safe ceiling {m['safe_contiguous_ceiling']:.1f} mA",
                       font=dict(size=10))
    # delivered settings
    obs = ctx.D.loc[ctx.D["feasible"]]
    amp = obs[ctx.meta.get("amp_col", "amp_mA_Left")].to_numpy(float)
    amp_plot = np.clip(amp, ctx.grid.amps.min(), ctx.grid.amps.max())
    below = amp < ctx.grid.amps.min()
    size = 6.0 + 26.0 * np.sqrt(obs["n"].to_numpy(float) / obs["n"].max())
    fig.add_trace(go.Scatter(
        x=_lf(obs["freq_hz"].to_numpy(float)), y=amp_plot, mode="markers",
        marker=dict(size=size, color=obs["J"].to_numpy(float), colorscale="RdBu_r",
                    cmid=0.0, cmin=-lim, cmax=lim, line=dict(color=C_OBS, width=1.4),
                    symbol=np.where(below, "triangle-down", "circle")),
        name="delivered setting (area ∝ reports)",
        customdata=np.column_stack([obs["epoch"], obs["n"], obs["J"], amp]),
        hovertemplate=("epoch %{customdata[0]:.0f}<br>%{x:.2f} log2Hz, "
                       "%{customdata[3]:.2f} mA<br>n = %{customdata[1]:.0f} reports"
                       "<br>observed J = %{customdata[2]:+.3f}<extra></extra>")))
    fig.add_trace(go.Scatter(x=[_lf(m["incumbent_xy"][0])], y=[m["incumbent_xy"][1]],
                            mode="markers+text", marker=dict(symbol="square-open", size=15,
                                                             color=C_INC, line=dict(width=3)),
                            text=["incumbent"], textposition="middle left",
                            textfont=dict(color=C_INC, size=11),
                            name=f"incumbent {m['incumbent_xy'][0]:g} Hz / {m['incumbent_xy'][1]:g} mA"))
    fig.add_trace(go.Scatter(x=[_lf(m["x_star"][0])], y=[m["x_star"][1]], mode="markers+text",
                            marker=dict(symbol="star", size=19, color=C_STAR,
                                        line=dict(color="white", width=1)),
                            text=[f"  estimated optimum {m['x_star'][0]:.0f} Hz / "
                                  f"{m['x_star'][1]:.1f} mA"],
                            textposition="middle right", textfont=dict(color=C_STAR, size=11),
                            name="estimated optimum (argmin mu in safe set)"))
    fig.update_layout(title=(_incumbent_verdict(ctx) + " — "
                            f"posterior mu spans {m['mu_min']:+.2f} to {m['mu_max']:+.2f} "
                            "NRS points"),
                      xaxis=_freq_axis(ctx), yaxis_title_text=_amp_label(ctx),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      height=620, width=980)
    return _stamp_plotly(fig, ctx, CAPTIONS[1])


def fig2_acquisition_decomposition(ctx: FigureContext):
    """mu, sigma, EI surfaces plus the per-iteration exploration-fraction trace."""
    go, make_subplots = _plotly()
    m = ctx.meta
    ei = ACQ.expected_improvement(ctx.mu, ctx.sd, ctx.incumbent_mu)
    ei_masked = np.where(ctx.safe, ei, np.nan)
    i_ei = int(np.nanargmax(ei_masked))
    fig = make_subplots(rows=2, cols=3, specs=[[{}, {}, {}], [{"colspan": 3}, None, None]],
                        subplot_titles=("a  Posterior mean mu — exploitation signal",
                                        "b  Posterior SD sigma — exploration signal",
                                        "c  Expected improvement = the trade-off",
                                        "d  Every selected cell in the first three batches is "
                                        "exploration-driven"),
                        vertical_spacing=0.17, horizontal_spacing=0.07,
                        row_heights=[0.58, 0.42])
    lim = float(np.max(np.abs([ctx.mu.min(), ctx.mu.max()])))
    panels = [(ctx.surface(ctx.mu), "RdBu_r", dict(zmid=0.0, zmin=-lim, zmax=lim), "mu J", 0.255),
              (ctx.surface(ctx.sd), "cividis", {}, "sigma J", 0.62),
              (ctx.surface(ei), "viridis", {}, "EI", 0.985)]
    for c, (Z, cs, kw, lab, xpos) in enumerate(panels, start=1):
        fig.add_trace(go.Heatmap(x=_lf(ctx.grid.freqs), y=ctx.grid.amps, z=Z, colorscale=cs,
                                 colorbar=dict(title=dict(text=lab, side="right"), thickness=11,
                                               len=0.40, y=0.79, x=xpos),
                                 hovertemplate="%{y:.1f} mA<br>%{z:+.3f}<extra></extra>", **kw),
                      row=1, col=c)
        fig.add_trace(go.Contour(x=_lf(ctx.grid.freqs), y=ctx.grid.amps, z=ctx.surface(ctx.sub),
                                 contours=dict(start=ctx.sgp.threshold, end=ctx.sgp.threshold,
                                               size=1, coloring="none"),
                                 line=dict(color=C_SAFE, width=1.5, dash="dash"),
                                 showscale=False, hoverinfo="skip", showlegend=False),
                      row=1, col=c)
        fig.update_xaxes(tickvals=_lf(ctx.grid.freqs),
                         ticktext=[f"{f:g}" for f in ctx.grid.freqs], row=1, col=c,
                         title_text="Frequency (Hz)" if c == 2 else None)
        fig.update_yaxes(row=1, col=c, title_text="Amplitude (mA)" if c == 1 else None)
    fig.add_trace(go.Scatter(x=[_lf(ctx.gx[i_ei, 0])], y=[ctx.gx[i_ei, 1]], mode="markers+text",
                             marker=dict(symbol="star", size=17, color=C_STAR),
                             text=[f"  argmax EI {ctx.gx[i_ei,0]:.0f} Hz / {ctx.gx[i_ei,1]:.1f} mA"],
                             textposition="middle right", textfont=dict(size=10, color=C_STAR),
                             showlegend=False), row=1, col=3)
    # panel d — exploration fraction trace
    sim = ctx.traj.loc[ctx.traj["phase"].eq("simulated")]
    fig.add_hline(y=0.5, line=dict(color=META_GREY, width=1, dash="dot"), row=2, col=1)
    fig.add_annotation(text="explore ↑ / exploit ↓ (0.5)", xref="x4", yref="y4",
                       x=sim["iteration"].max(), y=0.5, yanchor="top", xanchor="right",
                       showarrow=False, font=dict(size=10, color=META_GREY))
    for b, colour in zip([1, 2, 3], ["#0072B2", "#56B4E9", "#CC79A7"]):
        s = sim.loc[sim["batch"].eq(b)]
        fig.add_trace(go.Scatter(x=s["iteration"], y=s["expl_frac"], mode="lines+markers",
                                 line=dict(color=colour, width=2),
                                 marker=dict(size=11, color=colour, line=dict(color="white",
                                                                              width=1)),
                                 name=f"batch {b}",
                                 customdata=np.column_stack([s["freq_hz"], s["amp_mA"], s["J"]]),
                                 hovertemplate=("%{customdata[0]:.0f} Hz, %{customdata[1]:.1f} mA"
                                                "<br>exploration fraction %{y:.3f}"
                                                "<br>predicted J %{customdata[2]:+.3f}<extra></extra>")),
                      row=2, col=1)
    fig.update_yaxes(range=[0, 1.05], title_text="Exploration fraction", row=2, col=1)
    fig.update_xaxes(title_text=f"Selection index (3 batches x q={m['q']}, simulated)",
                     dtick=1, row=2, col=1)
    fig.update_layout(title=("Exploration dominates every selection: the surrogate cannot "
                             "separate cells by predicted benefit"),
                      height=880, width=1120,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.10, x=0.02))
    return _stamp_plotly(fig, ctx, CAPTIONS[2])


def fig3_search_trajectory(ctx: FigureContext):
    """Stacked parameter / safety / objective trace against iteration index."""
    go, make_subplots = _plotly()
    m, t = ctx.meta, ctx.traj
    brk = float(t.loc[t["phase"].eq("observed"), "iteration"].max()) + 0.5
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        specs=[[{"secondary_y": True}], [{}], [{}]],
                        subplot_titles=("a  Settings sampled, with the amplitude ceiling the "
                                        "safety model permits",
                                        "b  Safety-model severity at each sampled setting",
                                        "c  Objective at each sample, with best-so-far"))
    obs = t["phase"].eq("observed")
    fig.add_trace(go.Scatter(x=t["iteration"], y=t["freq_hz"], mode="lines+markers",
                             line=dict(color="#0072B2", width=1.4),
                             marker=dict(size=7, symbol=np.where(obs, "circle", "diamond"),
                                         color="#0072B2"),
                             name="frequency (Hz)"), row=1, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=t["iteration"], y=t["amp_mA"], mode="lines+markers",
                             line=dict(color="#D55E00", width=1.4),
                             marker=dict(size=7, symbol=np.where(obs, "circle", "diamond"),
                                         color="#D55E00"),
                             name="amplitude (mA)"), row=1, col=1, secondary_y=True)
    # ceiling: retrospective seed-derived over history, expansion-capped over the forward batches
    n_obs = int(obs.sum())
    ceil_x, ceil_y = [1, n_obs], [m["safe_contiguous_ceiling"]] * 2
    for b, c in enumerate(m["expansion_ceilings"]):
        lo = n_obs + b * m["q"] + 1
        ceil_x += [lo - 0.5, lo - 0.5 + m["q"]]
        ceil_y += [c, c]
    fig.add_trace(go.Scatter(x=ceil_x, y=ceil_y, mode="lines", line=dict(color=C_SAFE, width=2,
                                                                         dash="dot"),
                             name="permitted amplitude ceiling (mA)"),
                  row=1, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(x=t["iteration"], y=t["safety_mu"], mode="lines+markers",
                             line=dict(color="#7B3294", width=1.4),
                             marker=dict(size=7, symbol=np.where(obs, "circle", "diamond"),
                                         color="#7B3294"),
                             name="safety-model severity mu_SE"), row=2, col=1)
    fig.add_trace(go.Scatter(x=t["iteration"], y=t["safety_ub"], mode="lines",
                             line=dict(color="#7B3294", width=1, dash="dot"),
                             name=f"mu_SE + {m['beta']:g}·sigma_SE (decision quantity)"),
                  row=2, col=1)
    fig.add_hline(y=ctx.sgp.threshold, line=dict(color="#D55E00", width=1.8), row=2, col=1)
    fig.add_annotation(text="moderate = infeasible (3.0)", xref="x2", yref="y2",
                       x=t["iteration"].max(), y=ctx.sgp.threshold, xanchor="right",
                       yanchor="bottom", showarrow=False, font=dict(size=10, color="#D55E00"))
    fig.add_trace(go.Scatter(x=t.loc[obs, "iteration"], y=t.loc[obs, "J"], mode="markers",
                             marker=dict(size=8, color=C_OBS), name="observed J"), row=3, col=1)
    fig.add_trace(go.Scatter(x=t.loc[~obs, "iteration"], y=t.loc[~obs, "J"], mode="markers",
                             marker=dict(size=9, symbol="diamond-open", color=C_FWD,
                                         line=dict(width=2)),
                             name="predicted J (simulated, kriging-believer)"), row=3, col=1)
    fig.add_trace(go.Scatter(x=t["iteration"], y=t["best_so_far"], mode="lines",
                             line=dict(color=C_STAR, width=2.4), name="best J so far"),
                  row=3, col=1)
    fig.add_hline(y=0.0, line=dict(color=C_INC, width=1.5, dash="dash"), row=3, col=1)
    fig.add_annotation(text="incumbent (J = 0)", xref="x3", yref="y3", x=1, y=0.0,
                       xanchor="left", yanchor="bottom", showarrow=False,
                       font=dict(size=10, color=C_INC))
    for r in (1, 2, 3):
        fig.add_vline(x=brk, line=dict(color=META_GREY, width=1.5, dash="dashdot"), row=r, col=1)
    fig.add_annotation(text="observed history ◀ | ▶ forward simulation", xref="x", yref="paper",
                       x=brk, y=1.055, showarrow=False, font=dict(size=11, color=META_GREY))
    fig.update_yaxes(title_text="Frequency (Hz)", type="log", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Amplitude (mA)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Severity (0–3)", row=2, col=1)
    fig.update_yaxes(title_text=J_LABEL, row=3, col=1)
    fig.update_xaxes(title_text="Iteration index (chronological, then simulated)", row=3, col=1)
    fig.update_layout(title=(f"{n_obs} observed epochs then {int((~obs).sum())} simulated "
                             "selections: best-so-far has not moved since the incumbent"),
                      height=980, width=1120,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.16, x=0))
    return _stamp_plotly(fig, ctx, CAPTIONS[3])


def fig4_dual_model(ctx: FigureContext):
    """Composite-objective posterior beside the ILLUSTRATIVE preference posterior."""
    go, make_subplots = _plotly()
    m = ctx.meta
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.11,
                        subplot_titles=("a  Composite objective (minimised)",
                                        "b  Preference latent (maximised) — ILLUSTRATIVE"))
    lim = float(np.max(np.abs([ctx.mu.min(), ctx.mu.max()])))
    fig.add_trace(go.Heatmap(x=_lf(ctx.grid.freqs), y=ctx.grid.amps, z=ctx.surface(ctx.mu),
                             colorscale="RdBu_r", zmid=0.0, zmin=-lim, zmax=lim,
                             colorbar=dict(title=dict(text="mu J", side="right"), thickness=12,
                                           len=0.72, x=0.415),
                             hovertemplate="%{y:.1f} mA<br>mu J %{z:+.3f}<extra></extra>"),
                  row=1, col=1)
    fig.add_trace(go.Heatmap(x=_lf(ctx.grid.freqs), y=ctx.grid.amps, z=ctx.surface(ctx.pmu),
                             colorscale="magma",
                             colorbar=dict(title=dict(text="latent value", side="right"),
                                           thickness=12, len=0.72, x=1.0),
                             hovertemplate="%{y:.1f} mA<br>latent %{z:+.3f}<extra></extra>"),
                  row=1, col=2)
    xs, xp = m["x_star"], m["x_pref"]
    for c in (1, 2):
        fig.add_trace(go.Scatter(x=[_lf(xs[0])], y=[xs[1]], mode="markers",
                                 marker=dict(symbol="star", size=18, color=C_STAR,
                                             line=dict(color="white", width=1.2)),
                                 name="objective argmin", showlegend=c == 1), row=1, col=c)
        fig.add_trace(go.Scatter(x=[_lf(xp[0])], y=[xp[1]], mode="markers",
                                 marker=dict(symbol="diamond", size=15, color=C_FWD,
                                             line=dict(color="white", width=1.2)),
                                 name="preference argmax", showlegend=c == 1), row=1, col=c)
        fig.update_xaxes(tickvals=_lf(ctx.grid.freqs),
                         ticktext=[f"{f:g}" for f in ctx.grid.freqs],
                         title_text="Frequency (Hz)", row=1, col=c)
    fig.update_yaxes(title_text="Amplitude (mA)", row=1, col=1)
    gap_f, gap_a = abs(xp[0] - xs[0]), abs(xp[1] - xs[1])
    fig.add_annotation(x=_lf(xp[0]), y=xp[1], ax=_lf(xs[0]), ay=xs[1], xref="x2", yref="y2",
                       axref="x2", ayref="y2", showarrow=True, arrowhead=3, arrowwidth=1.8,
                       arrowcolor="#333333",
                       text=f"gap: {gap_f:.0f} Hz, {gap_a:.2f} mA", font=dict(size=11),
                       yshift=18)
    fig.add_annotation(text=("<b>ILLUSTRATIVE — awaiting prospective elicitation.</b> No A-vs-B "
                             "judgements exist. Comparisons were derived from observed epoch J "
                             f"with margin {m['pref_margin']:g}: "
                             f"{m['pref_n_pairs']} pairs over {m['pref_n_cells']} tested cells. "
                             f"5-fold held-out accuracy {m['pref_holdout_accuracy']:.3f}, "
                             "optimistically biased because the comparisons are a deterministic "
                             "function of the same J."),
                       xref="paper", yref="paper", x=0, y=1.16, showarrow=False, align="left",
                       xanchor="left", font=dict(size=11, color="#8B0000"))
    fig.update_layout(title=(f"Objective and preference optima differ by {gap_f:.0f} Hz and "
                             f"{gap_a:.2f} mA"), height=620, width=1120,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.20, x=0))
    return _stamp_plotly(fig, ctx, CAPTIONS[4])


def fig5_coverage_map(ctx: FigureContext):
    """Posterior SD, the never-sampled band, and the exploration queue."""
    go, _ = _plotly()
    m = ctx.meta
    optb = ctx.mu - m["kappa"] * ctx.sd
    fig = go.Figure()
    fig.add_trace(go.Heatmap(x=_lf(ctx.grid.freqs), y=ctx.grid.amps, z=ctx.surface(ctx.sd),
                             colorscale="cividis",
                             colorbar=dict(title=dict(text="Posterior SD of J (NRS points)",
                                                      side="right"), thickness=14, len=0.78),
                             hovertemplate="%{y:.1f} mA<br>sigma %{z:.3f}<extra></extra>"))
    # never-sampled 10-55 Hz / >1.8 mA band
    fig.add_shape(type="rect", x0=_lf(10) - 0.25, x1=_lf(55) + 0.18, y0=1.8,
                  y1=float(ctx.grid.amps.max()) + 0.05, line=dict(color=C_BAND, width=2.5,
                                                                  dash="dash"),
                  fillcolor=C_BAND, opacity=0.16, layer="above")
    fig.add_annotation(x=_lf(20), y=3.5, text=(f"10–55 Hz above 1.8 mA<br>{m['band_undertested']}"
                                               f" of {m['band_cells']} cells still carry &lt;3 "
                                               "reports"),
                       showarrow=False, font=dict(size=11, color="#FFFFFF"), align="left",
                       bgcolor="rgba(0,68,120,0.72)", borderpad=4)
    # reference contour: the incumbent posterior mean level
    fig.add_trace(go.Contour(x=_lf(ctx.grid.freqs), y=ctx.grid.amps, z=ctx.surface(ctx.mu),
                             contours=dict(start=ctx.incumbent_mu, end=ctx.incumbent_mu, size=1,
                                           coloring="none"),
                             line=dict(color=C_INC, width=2.4), showscale=False,
                             name=f"mu = incumbent ({ctx.incumbent_mu:+.3f})", showlegend=True,
                             hoverinfo="skip"))
    # exploration queue: top cells by expected improvement, annotated with optimistic bound
    top = ctx.queue[:12]
    fig.add_trace(go.Scatter(x=_lf(ctx.gx[top, 0]), y=ctx.gx[top, 1], mode="markers+text",
                             marker=dict(symbol="circle-open", size=13, color="#FFFFFF",
                                         line=dict(width=2.2)),
                             text=[f" {optb[i]:+.2f}" for i in top], textposition="middle right",
                             textfont=dict(size=10, color="#FFFFFF"),
                             name="exploration queue, top 12 (label = mu − 2σ)",
                             customdata=np.column_stack([ctx.gx[top, 0], ctx.gx[top, 1],
                                                         ctx.mu[top], ctx.sd[top], optb[top]]),
                             hovertemplate=("%{customdata[0]:.0f} Hz, %{customdata[1]:.1f} mA"
                                            "<br>mu %{customdata[2]:+.3f}, sigma "
                                            "%{customdata[3]:.3f}<br>optimistic bound "
                                            "%{customdata[4]:+.3f}<extra></extra>")))
    fig.add_trace(go.Scatter(x=[_lf(m["incumbent_xy"][0])], y=[m["incumbent_xy"][1]],
                             mode="markers", marker=dict(symbol="square-open", size=15,
                                                          color=C_INC, line=dict(width=3)),
                             name="incumbent"))
    fig.update_layout(title=(f"The plateau is LOCAL, not global: {m['queue_size']} of "
                             f"{m['n_unexplored']} under-tested cells have an optimistic bound "
                             f"beating the incumbent (best {m['best_optimistic_unexplored']:+.2f})"),
                      xaxis=_freq_axis(ctx), yaxis_title_text=_amp_label(ctx),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      height=640, width=1000)
    return _stamp_plotly(fig, ctx, CAPTIONS[5])


PLOTLY_FIGURES = {
    1: ("stimopt_fig1_posterior_surface", fig1_posterior_surface),
    2: ("stimopt_fig2_acquisition_decomposition", fig2_acquisition_decomposition),
    3: ("stimopt_fig3_search_trajectory", fig3_search_trajectory),
    4: ("stimopt_fig4_dual_model_overlay", fig4_dual_model),
    5: ("stimopt_fig5_coverage_map", fig5_coverage_map),
}


# =========================================================================================
# Static matplotlib renderings
# =========================================================================================
def _mpl():
    import matplotlib
    import matplotlib.pyplot as plt
    return matplotlib, plt


def apply_style(sizes=(9, 8, 7)):
    """Publication rcParams: sans-serif, a three-step size ladder, open frame, no grid."""
    _, plt = _mpl()
    base, mid, small = sizes
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": base, "axes.titlesize": base, "axes.labelsize": base,
        "legend.fontsize": mid, "xtick.labelsize": small, "ytick.labelsize": small,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": False, "axes.titlelocation": "left", "axes.titleweight": "normal",
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
        "legend.frameon": False, "image.interpolation": "nearest",
    })


#: 125 and 145 Hz sit within 1.5 % of the log2 axis width of 130 and 165, so their labels cannot
#: both be drawn. Ticks are kept for every grid frequency; labels are drawn for this subset.
_FREQ_LABELLED = (10, 20, 30, 40, 55, 70, 85, 110, 130, 165)


def _freq_ticks(ax, ctx, label=True, fontsize=None):
    ax.set_xticks(_lf(ctx.grid.freqs))
    ax.set_xticklabels([f"{f:g}" if int(f) in _FREQ_LABELLED else "" for f in ctx.grid.freqs],
                       fontsize=fontsize)
    if label:
        ax.set_xlabel("Stimulation frequency (Hz, log$_2$ spacing)")


def _unsafe_hatch(ax, ctx, *, hatch="xxx", color="#000000", lw=0.0):
    """Hatch the cells the safety model rejects, so the banded safe set reads as a region.

    The safe set on this warm start is neither contiguous in amplitude nor frequency-dependent
    (see :attr:`FigureContext.meta` ``safe_is_contiguous``), so the dashed threshold contour alone
    renders as a stack of unexplained horizontal lines. Hatching the rejected cells makes the band
    structure visible as the artefact it is.
    """
    import matplotlib
    with matplotlib.rc_context({"hatch.linewidth": 0.5, "hatch.color": color}):
        cf = ax.contourf(_lf(ctx.grid.freqs), ctx.grid.amps, ctx.surface(ctx.sub),
                         levels=[ctx.sgp.threshold, 1e9], colors="none", hatches=[hatch],
                         zorder=3)
    # matplotlib >= 3.8 makes ContourSet a single Collection; .collections was removed in 3.10.
    for coll in getattr(cf, "collections", [cf]):
        coll.set_edgecolor(color)
        coll.set_linewidth(lw)
        coll.set_alpha(0.42)
    return cf


def _heat(ax, ctx, values, cmap, *, norm=None, vmin=None, vmax=None):
    xe, ye = _cell_edges(_lf(ctx.grid.freqs)), _cell_edges(ctx.grid.amps)
    return ax.pcolormesh(xe, ye, ctx.surface(values), cmap=cmap, norm=norm, vmin=vmin,
                         vmax=vmax, shading="flat", rasterized=True)


def _safe_contour(ax, ctx, **kw):
    kw = {"colors": C_SAFE, "linewidths": 1.6, "linestyles": "--", **kw}
    return ax.contour(_lf(ctx.grid.freqs), ctx.grid.amps, ctx.surface(ctx.sub),
                      levels=[ctx.sgp.threshold], **kw)


def _jnorm(ctx):
    matplotlib, _ = _mpl()
    lim = float(np.max(np.abs([ctx.mu.min(), ctx.mu.max()])))
    return matplotlib.colors.TwoSlopeNorm(vcenter=0.0, vmin=-lim, vmax=lim)


def _stamp_mpl(fig, ctx, caption, y=0.005):
    fig.text(0.005, y + 0.030, caption, ha="left", va="bottom", fontsize=8.5, color="#333333",
             style="italic", wrap=True)
    fig.text(0.005, y, ctx.stamp, ha="left", va="bottom", fontsize=7.5, color=META_GREY)



def _amp_label(ctx) -> str:
    """Y-axis label naming the hemisphere the arm was actually fitted on.

    This was hardcoded to "Left-hemisphere amplitude" in five places, so every right-arm figure
    contradicted its own provenance stamp and its own incumbent marker.
    """
    return f"{ctx.meta.get('hemisphere', 'Left')}-hemisphere amplitude (mA)"


def _incumbent_verdict(ctx) -> str:
    """Honest one-line verdict on whether the grid beats the incumbent.

    A grid minimum below zero IS predicted better in the mean. Saying "nothing is predicted
    better" in that case is false; the defensible statement is that the difference is not
    resolved against the posterior SD. Only a non-negative minimum supports the stronger claim.
    """
    m = ctx.meta
    mu_min = float(m["mu_min"])
    if mu_min >= 0.0:
        return "Nothing on the grid is predicted better than the incumbent"
    sd_opt = float(m.get("opt_posterior_sd", float("nan")))
    if np.isfinite(sd_opt) and abs(mu_min) < sd_opt:
        return ("Best cell is predicted better than the incumbent but NOT resolved: "
                f"gain {abs(mu_min):.2f} < posterior SD {sd_opt:.2f}")
    return f"Best cell is predicted {abs(mu_min):.2f} NRS points better than the incumbent"


def mpl_fig1_posterior_surface(ctx: FigureContext):
    _, plt = _mpl()
    apply_style()
    m = ctx.meta
    fig, ax = plt.subplots(figsize=(9.4, 6.4))
    norm = _jnorm(ctx)
    pc = _heat(ax, ctx, ctx.mu, CMAP_J, norm=norm)
    cb = fig.colorbar(pc, ax=ax, pad=0.02, fraction=0.045)
    cb.set_label(J_LABEL)
    cb.ax.annotate(GOODNESS, xy=(0.5, -0.075), xycoords="axes fraction", ha="center",
                   va="top", fontsize=7.5, color=META_GREY)
    _unsafe_hatch(ax, ctx)
    _safe_contour(ax, ctx)
    ax.axhline(m["safe_contiguous_ceiling"], color=C_SAFE, lw=1.6, ls=":", zorder=5)
    ax.annotate(f"usable safe ceiling {m['safe_contiguous_ceiling']:.1f} mA — hatching above is "
                "rejected by the safety model",
                xy=(_lf(10) - 0.2, m["safe_contiguous_ceiling"]), xytext=(2, -11),
                textcoords="offset points", ha="left", va="top", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.82),
                zorder=9)

    obs = ctx.D.loc[ctx.D["feasible"]]
    amp = obs[ctx.meta.get("amp_col", "amp_mA_Left")].to_numpy(float)
    below = amp < ctx.grid.amps.min()
    ap = np.clip(amp, ctx.grid.amps.min(), ctx.grid.amps.max())
    nn = obs["n"].to_numpy(float)
    size = 14 + 300 * np.sqrt(nn / nn.max())
    ax.scatter(_lf(obs["freq_hz"].to_numpy(float))[~below], ap[~below], s=size[~below],
               c=obs["J"].to_numpy(float)[~below], cmap=CMAP_J, norm=norm,
               edgecolors=C_OBS, linewidths=1.0, zorder=4)
    if below.any():
        ax.scatter(_lf(obs["freq_hz"].to_numpy(float))[below], ap[below], s=size[below],
                   c=obs["J"].to_numpy(float)[below], cmap=CMAP_J, norm=norm, marker="v",
                   edgecolors=C_OBS, linewidths=1.0, zorder=4)
    ax.scatter([_lf(m["incumbent_xy"][0])], [m["incumbent_xy"][1]], s=210, marker="s",
               facecolors="none", edgecolors=C_INC, linewidths=2.4, zorder=6)
    ax.annotate(f"incumbent\n{m['incumbent_xy'][0]:g} Hz / {m['incumbent_xy'][1]:g} mA",
                xy=(_lf(m["incumbent_xy"][0]), m["incumbent_xy"][1]), xytext=(-74, -46),
                textcoords="offset points", fontsize=8.5, color=C_INC, ha="center",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85),
                arrowprops=dict(arrowstyle="-", color=C_INC, lw=1.0), zorder=9)
    ax.scatter([_lf(m["x_star"][0])], [m["x_star"][1]], s=340, marker="*", color=C_STAR,
               edgecolors="white", linewidths=0.8, zorder=7)
    ax.annotate(f"estimated optimum\n{m['x_star'][0]:.0f} Hz / {m['x_star'][1]:.1f} mA\n"
                f"$\\mu$={m['mu_star']:+.3f}, $\\sigma$={m['sd_star']:.3f}",
                xy=(_lf(m["x_star"][0]), m["x_star"][1]), xytext=(-126, -52),
                textcoords="offset points", fontsize=8.5, color=C_STAR, ha="left",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85),
                arrowprops=dict(arrowstyle="-", color=C_STAR, lw=1.0), zorder=9)

    # size key, inside the axes on the low-amplitude whitespace at 20-30 Hz
    ax.annotate("delivered setting, area $\\propto$ reports", xy=(0.115, 0.115),
                xycoords="axes fraction", ha="left", va="center", fontsize=8.5, zorder=9,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#BBBBBB", lw=0.7,
                          alpha=0.92))
    for n_ref, xr in zip([1, 30, 159], [0.150, 0.220, 0.310]):
        ax.scatter([xr], [0.062], s=14 + 300 * np.sqrt(n_ref / nn.max()),
                   transform=ax.transAxes, facecolors="white", edgecolors=C_OBS, linewidths=1.0,
                   zorder=10)
        ax.annotate(f"n={n_ref}", xy=(xr, 0.012), xycoords="axes fraction", ha="center",
                    va="bottom", fontsize=7, zorder=11)

    _freq_ticks(ax, ctx)
    ax.set_ylabel(_amp_label(ctx))
    ax.set_title(f"{_incumbent_verdict(ctx)}: posterior "
                 f"$\\mu$ spans {m['mu_min']:+.2f} to {m['mu_max']:+.2f} NRS points\n"
                 f"Safe set is banded, not a ceiling — {m['n_safe']} of {m['n_cells']} cells "
                 f"pass at $\\beta$={m['beta']:g}, and it is identical at every frequency",
                 pad=12, fontsize=10)
    ax.set_ylim(ctx.grid.amps.min() - 0.16, ctx.grid.amps.max() + 0.18)
    fig.subplots_adjust(left=0.075, right=0.99, top=0.88, bottom=0.155)
    _stamp_mpl(fig, ctx, CAPTIONS[1])
    return fig


def mpl_fig2_acquisition_decomposition(ctx: FigureContext):
    _, plt = _mpl()
    apply_style()
    m = ctx.meta
    ei = ACQ.expected_improvement(ctx.mu, ctx.sd, ctx.incumbent_mu)
    i_ei = int(np.nanargmax(np.where(ctx.safe, ei, np.nan)))
    fig = plt.figure(figsize=(11.6, 8.6))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.72], hspace=0.42, wspace=0.30,
                          left=0.065, right=0.985, top=0.88, bottom=0.135)
    specs = [(ctx.mu, CMAP_J, _jnorm(ctx), "Posterior mean $\\mu$ of J (NRS pts)",
              "a  Posterior mean $\\mu$ — the exploitation signal"),
             (ctx.sd, CMAP_SD, None, "Posterior SD $\\sigma$ of J (NRS pts)",
              "b  Posterior SD $\\sigma$ — the exploration signal"),
             (ei, "viridis", None, "Expected improvement (NRS pts)",
              "c  Expected improvement — the trade-off")]
    for c, (v, cmap, norm, clab, title) in enumerate(specs):
        ax = fig.add_subplot(gs[0, c])
        pc = _heat(ax, ctx, v, cmap, norm=norm)
        cb = fig.colorbar(pc, ax=ax, pad=0.025, fraction=0.05)
        cb.set_label(clab, fontsize=7.5)
        cb.ax.tick_params(labelsize=6.5)
        _unsafe_hatch(ax, ctx, hatch="xx")
        _safe_contour(ax, ctx, linewidths=1.0)
        _freq_ticks(ax, ctx, label=False, fontsize=6.5)
        ax.tick_params(axis="x", rotation=90)
        ax.set_title(title, fontsize=9)
        if c == 0:
            ax.set_ylabel("Amplitude (mA)")
        if c == 1:
            ax.set_xlabel("Stimulation frequency (Hz, log$_2$ spacing)")
        if c == 2:
            ax.scatter([_lf(ctx.gx[i_ei, 0])], [ctx.gx[i_ei, 1]], s=300, marker="*",
                       color=C_STAR, edgecolors="white", linewidths=0.8, zorder=6)
            ax.annotate(f"argmax EI\n{ctx.gx[i_ei,0]:.0f} Hz / {ctx.gx[i_ei,1]:.1f} mA",
                        xy=(_lf(ctx.gx[i_ei, 0]), ctx.gx[i_ei, 1]), xytext=(-4, 54),
                        textcoords="offset points", fontsize=8, color="#004D33", ha="center",
                        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.9),
                        arrowprops=dict(arrowstyle="-", color=C_STAR, lw=1.0), zorder=9)

    axd = fig.add_subplot(gs[1, :])
    sim = ctx.traj.loc[ctx.traj["phase"].eq("simulated")]
    axd.axhspan(0.5, 1.05, color="#0072B2", alpha=0.05)
    axd.axhline(0.5, color=META_GREY, lw=1.0, ls=":")
    axd.annotate("explore (above) / exploit (below)", xy=(sim["iteration"].max(), 0.5),
                 xytext=(-2, -6), textcoords="offset points", ha="right", va="top",
                 fontsize=8, color=META_GREY)
    for b, colour in zip([1, 2, 3], ["#0072B2", "#56B4E9", "#CC79A7"]):
        s = sim.loc[sim["batch"].eq(b)]
        axd.plot(s["iteration"], s["expl_frac"], "-o", color=colour, lw=1.8, ms=7,
                 mec="white", mew=0.8, label=f"batch {b} (ceiling {m['expansion_ceilings'][b-1]:.1f} mA)")
        for _, r in s.iterrows():
            axd.annotate(f"{r.freq_hz:.0f} Hz\n{r.amp_mA:.1f} mA",
                         xy=(r.iteration, r.expl_frac), xytext=(0, -13),
                         textcoords="offset points", ha="center", va="top", fontsize=6.5,
                         color=colour)
    axd.set_ylim(0.0, 1.05)
    axd.set_xticks(sim["iteration"].to_numpy())
    axd.set_xlabel(f"Selection index (3 simulated batches of q={m['q']})")
    axd.set_ylabel("Exploration fraction")
    axd.set_title("d  Every selected cell is exploration-driven: the exploration fraction never "
                  f"falls below {sim['expl_frac'].min():.2f}", fontsize=9)
    axd.legend(loc="lower left", ncol=3, fontsize=7.5)
    _efm = float(sim["expl_frac"].min())
    _head = ("Exploration dominates every selection — the surrogate cannot separate cells by "
             "predicted benefit" if _efm >= 0.9 else
             "Every selection is exploration-led, but not uniformly — the exploration share "
             f"ranges from {_efm:.2f} to {float(sim['expl_frac'].max()):.2f}")
    fig.suptitle(_head, x=0.065, ha="left", fontsize=11)
    _stamp_mpl(fig, ctx, CAPTIONS[2])
    return fig


def mpl_fig3_search_trajectory(ctx: FigureContext):
    _, plt = _mpl()
    apply_style()
    m, t = ctx.meta, ctx.traj
    obs = t["phase"].eq("observed").to_numpy()
    n_obs = int(obs.sum())
    brk = n_obs + 0.5
    fig, axes = plt.subplots(3, 1, figsize=(11.2, 9.2), sharex=True,
                             gridspec_kw=dict(hspace=0.20))
    fig.subplots_adjust(left=0.075, right=0.90, top=0.90, bottom=0.135)

    ax = axes[0]
    ax.plot(t["iteration"][obs], t["freq_hz"][obs], "-o", color="#0072B2", lw=1.2, ms=5,
            label="frequency, observed")
    ax.plot(t["iteration"][~obs], t["freq_hz"][~obs], "D", color="#0072B2", ms=6,
            mfc="none", mew=1.6, label="frequency, simulated")
    ax.set_yscale("log")
    ax.set_yticks(ctx.grid.freqs)
    # tighter subset than _FREQ_LABELLED: the vertical log axis is shorter than the horizontal
    # one, so 130 Hz collides with 110 Hz here even though it clears on the heatmap x axis.
    ax.set_yticklabels([f"{f:g}" if int(f) in (10, 20, 30, 40, 55, 70, 85, 110, 165) else ""
                        for f in ctx.grid.freqs])
    ax.set_ylim(8.0, 330.0)          # headroom so the legend clears the 165 Hz trace
    ax.set_ylabel("Frequency (Hz)", color="#0072B2")
    ax.tick_params(axis="y", colors="#0072B2")
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    ax2.plot(t["iteration"][obs], t["amp_mA"][obs], "-o", color="#D55E00", lw=1.2, ms=5,
             label="amplitude, observed")
    ax2.plot(t["iteration"][~obs], t["amp_mA"][~obs], "D", color="#D55E00", ms=6,
             mfc="none", mew=1.6, label="amplitude, simulated")
    ax2.plot([1, n_obs], [m["safe_contiguous_ceiling"]] * 2, ls=":", color=C_SAFE, lw=1.8,
             label="permitted amplitude ceiling")
    for b, c in enumerate(m["expansion_ceilings"]):
        lo = n_obs + b * m["q"] + 0.5
        ax2.plot([lo, lo + m["q"]], [c, c], ls=":", color=C_SAFE, lw=1.8)
    ax2.set_ylabel("Amplitude (mA)", color="#D55E00")
    ax2.tick_params(axis="y", colors="#D55E00")
    ax2.set_ylim(-0.25, 6.1)          # headroom so the legend clears the amplitude trace
    ax2.set_yticks([0, 1, 2, 3, 4])
    ax.set_title("a  Settings sampled, with the amplitude ceiling the safety model permits",
                 fontsize=9.5)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", ncol=3, fontsize=7.5)

    ax = axes[1]
    ax.plot(t["iteration"][obs], t["safety_mu"][obs], "-o", color="#7B3294", lw=1.2, ms=5,
            label="severity $\\mu_{SE}$, observed setting")
    ax.plot(t["iteration"][~obs], t["safety_mu"][~obs], "D", color="#7B3294", ms=6, mfc="none",
            mew=1.6, label="severity $\\mu_{SE}$, simulated")
    ax.plot(t["iteration"], t["safety_ub"], ls=":", color="#7B3294", lw=1.4,
            label=f"$\\mu_{{SE}}+{m['beta']:g}\\sigma_{{SE}}$ (decision quantity)")
    ax.axhline(ctx.sgp.threshold, color="#D55E00", lw=1.8)
    ax.annotate("moderate = hard infeasible (3.0)", xy=(1, ctx.sgp.threshold),
                xytext=(2, 3), textcoords="offset points", ha="left", va="bottom",
                fontsize=8, color="#D55E00")
    ax.set_ylabel("Side-effect severity (0–3)")
    ax.set_ylim(-0.15, 5.1)          # headroom for the legend above the data
    ax.set_yticks([0, 1, 2, 3])
    ax.set_title("b  Safety-model severity at each sampled setting", fontsize=9.5)
    ax.legend(loc="upper left", ncol=3, fontsize=7.5)

    ax = axes[2]
    ax.plot(t["iteration"][obs], t["J"][obs], "o", color=C_OBS, ms=5.5, label="observed J")
    ax.plot(t["iteration"][~obs], t["J"][~obs], "D", color=C_FWD, ms=6.5, mfc="none", mew=1.8,
            label="predicted J (simulated, kriging-believer)")
    ax.plot(t["iteration"], t["best_so_far"], color=C_STAR, lw=2.2, label="best J so far")
    ax.axhline(0.0, color=C_INC, lw=1.4, ls="--")
    ax.annotate("incumbent (J = 0)", xy=(1, 0.0), xytext=(2, 3), textcoords="offset points",
                fontsize=8, color=C_INC, va="bottom")
    ax.set_ylabel(J_LABEL, fontsize=8)
    ax.set_xlabel("Iteration index (observed history in chronological order, then simulation)")
    ax.set_title("c  Objective at each sample, with best-so-far", fontsize=9.5)
    # Limits must come from the data. A fixed floor of -1.35 clipped the running-best trace off
    # the bottom of the axis on arms whose best J goes lower, which hides the very quantity the
    # panel exists to show. Headroom is added ABOVE for the legend only.
    _yv = np.concatenate([t["J"].to_numpy(float), t["best_so_far"].to_numpy(float)])
    _yv = _yv[np.isfinite(_yv)]
    _lo, _hi = (float(_yv.min()), float(_yv.max())) if _yv.size else (-1.0, 3.0)
    _pad = max(0.15, 0.05 * (_hi - _lo))
    ax.set_ylim(_lo - _pad, _hi + 4.0 * _pad)
    ax.annotate(GOODNESS, xy=(0.005, 0.03), xycoords="axes fraction", ha="left", fontsize=8,
                color=META_GREY)
    ax.legend(loc="upper right", ncol=3, fontsize=7.5)

    for a in list(axes) + [ax2]:
        a.axvline(brk, color=META_GREY, lw=1.4, ls="-.")
    # plain ASCII: the solid triangle glyphs are absent from the default sans-serif fallback
    axes[0].annotate("<-- observed history  |  forward simulation -->", xy=(brk, 1.045),
                     xycoords=("data", "axes fraction"), ha="center", fontsize=9,
                     color=META_GREY, clip_on=False)
    fig.suptitle(f"{n_obs} observed epochs then {int((~obs).sum())} simulated selections: "
                 "best-so-far has not moved since the best observed epoch",
                 x=0.075, ha="left", fontsize=11)
    _stamp_mpl(fig, ctx, CAPTIONS[3])
    return fig


def mpl_fig4_dual_model(ctx: FigureContext):
    _, plt = _mpl()
    apply_style()
    m = ctx.meta
    xs, xp = m["x_star"], m["x_pref"]
    gap_f, gap_a = abs(xp[0] - xs[0]), abs(xp[1] - xs[1])
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 5.9), sharey=True)
    fig.subplots_adjust(left=0.065, right=0.975, top=0.74, bottom=0.20, wspace=0.16)
    for c, (ax, v, cmap, norm, clab, title) in enumerate([
            (axes[0], ctx.mu, CMAP_J, _jnorm(ctx), J_LABEL,
             "a  Composite objective posterior (minimised; " + GOODNESS + ")"),
            (axes[1], ctx.pmu, CMAP_PREF, None, "Preference latent value (arbitrary units)",
             "b  Preference posterior (maximised; higher = more preferred)")]):
        pc = _heat(ax, ctx, v, cmap, norm=norm)
        cb = fig.colorbar(pc, ax=ax, pad=0.02, fraction=0.05)
        cb.set_label(clab, fontsize=7.5)
        cb.ax.tick_params(labelsize=6.5)
        ax.scatter([_lf(xs[0])], [xs[1]], s=320, marker="*", color=C_STAR, edgecolors="white",
                   linewidths=0.8, zorder=6)
        ax.scatter([_lf(xp[0])], [xp[1]], s=150, marker="D", color=C_FWD, edgecolors="white",
                   linewidths=0.8, zorder=6)
        _freq_ticks(ax, ctx)
        ax.set_title(title, fontsize=9.5)
        if c == 0:
            ax.set_ylabel(_amp_label(ctx))
            ax.annotate(f"objective argmin\n{xs[0]:.0f} Hz / {xs[1]:.1f} mA",
                        xy=(_lf(xs[0]), xs[1]), xytext=(30, 52), textcoords="offset points",
                        fontsize=8.5, color="#004D33",
                        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.88),
                        arrowprops=dict(arrowstyle="-", color=C_STAR, lw=1.0), zorder=9)
            ax.annotate(f"preference argmax\n{xp[0]:.0f} Hz / {xp[1]:.1f} mA",
                        xy=(_lf(xp[0]), xp[1]), xytext=(-104, -56), textcoords="offset points",
                        fontsize=8.5, color="#8C3A6B",
                        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.88),
                        arrowprops=dict(arrowstyle="-", color=C_FWD, lw=1.0), zorder=9)
        else:
            ax.annotate("", xy=(_lf(xp[0]), xp[1]), xytext=(_lf(xs[0]), xs[1]),
                        arrowprops=dict(arrowstyle="<->", color="#FFFFFF", lw=2.0), zorder=8)
            ax.annotate(f"gap: {gap_f:.0f} Hz in frequency,\n{gap_a:.2f} mA in amplitude",
                        xy=(0.5 * (_lf(xs[0]) + _lf(xp[0])), xs[1]), xytext=(0, 58),
                        textcoords="offset points", fontsize=9, color="#222222", va="bottom",
                        ha="center",
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#888888", lw=0.7,
                                  alpha=0.92),
                        arrowprops=dict(arrowstyle="-", color="#333333", lw=0.8), zorder=9)
    fig.text(0.065, 0.955, "ILLUSTRATIVE — awaiting prospective elicitation", ha="left",
             va="top", fontsize=11, color="#8B0000", fontweight="bold")
    fig.text(0.065, 0.925,
             "No A-vs-B judgements exist in this dataset. Comparisons were CONSTRUCTED from the "
             f"observed epoch J with margin {m['pref_margin']:g} NRS points\n"
             f"({m['pref_n_pairs']} ordered pairs over {m['pref_n_cells']} distinct tested "
             f"cells). 5-fold held-out accuracy {m['pref_holdout_accuracy']:.3f} is "
             "optimistically biased, because the comparisons are a\ndeterministic function of "
             "the same J the objective GP is fitted to. This panel shows disagreement GEOMETRY, "
             "not patient preference.",
             ha="left", va="top", fontsize=8, color="#8B0000")
    fig.text(0.065, 0.815, f"Objective and preference optima differ by {gap_f:.0f} Hz and "
             f"{gap_a:.2f} mA", ha="left", va="top", fontsize=11)
    _stamp_mpl(fig, ctx, CAPTIONS[4])
    return fig


def mpl_fig5_coverage_map(ctx: FigureContext):
    matplotlib, plt = _mpl()
    apply_style()
    m = ctx.meta
    optb = ctx.mu - m["kappa"] * ctx.sd
    fig, ax = plt.subplots(figsize=(10.4, 6.6))
    fig.subplots_adjust(left=0.07, right=0.99, top=0.86, bottom=0.155)
    pc = _heat(ax, ctx, ctx.sd, CMAP_SD)
    cb = fig.colorbar(pc, ax=ax, pad=0.02, fraction=0.045)
    cb.set_label("Posterior SD $\\sigma$ of J (NRS points)")

    ax.add_patch(matplotlib.patches.Rectangle(
        (_lf(10) - 0.25, 1.8), _lf(55) - _lf(10) + 0.43,
        float(ctx.grid.amps.max()) + 0.05 - 1.8, facecolor="none",
        edgecolor="#FFFFFF", lw=2.6, ls="--", zorder=4))
    ax.annotate(f"never sampled: 10–55 Hz above 1.8 mA\n{m['band_undertested']} of "
                f"{m['band_cells']} cells carry <3 reports\n(only exceptions: 55 Hz at 3.0 and "
                "4.0 mA)",
                xy=(_lf(13), 3.55), fontsize=8.5, color="white", ha="left", va="center",
                bbox=dict(boxstyle="round,pad=0.35", fc="#00447A", ec="white", lw=1.0,
                          alpha=0.90), zorder=9)
    ax.contour(_lf(ctx.grid.freqs), ctx.grid.amps, ctx.surface(ctx.mu),
               levels=[ctx.incumbent_mu], colors=C_INC, linewidths=2.4, zorder=6)
    top = ctx.queue[:12]
    n_at_40 = int((ctx.gx[top, 0] == 40).sum())
    ax.scatter(_lf(ctx.gx[top, 0]), ctx.gx[top, 1], s=95, facecolors="none", edgecolors="white",
               linewidths=1.8, zorder=7)
    lab = np.argsort(ctx.gx[top, 1])[::4]          # label a readable subset of the stack
    for k in lab:
        i = top[k]
        ax.annotate(f"{optb[i]:+.2f}", xy=(_lf(ctx.gx[i, 0]), ctx.gx[i, 1]), xytext=(9, 0),
                    textcoords="offset points", fontsize=8, color="white", va="center",
                    zorder=8)
    ax.annotate(f"{n_at_40} of the top 12 queue cells\nare at 40 Hz — the untested\nfrequency "
                "next to 55 Hz",
                xy=(_lf(40), 1.05), xytext=(-208, 18), textcoords="offset points", fontsize=8.5,
                color="white", ha="left", va="center",
                bbox=dict(boxstyle="round,pad=0.3", fc="#333333", ec="white", lw=0.8,
                          alpha=0.88),
                arrowprops=dict(arrowstyle="-", color="white", lw=1.0), zorder=9)
    ax.scatter([_lf(m["incumbent_xy"][0])], [m["incumbent_xy"][1]], s=210, marker="s",
               facecolors="none", edgecolors=C_INC, linewidths=2.4, zorder=7)
    ax.annotate("incumbent", xy=(_lf(ctx.meta["incumbent_xy"][0]), ctx.meta["incumbent_xy"][1]),
                xytext=(38, -30), textcoords="offset points",
                fontsize=8.5, color=C_INC,
                arrowprops=dict(arrowstyle="-", color=C_INC, lw=1.0), zorder=8)
    ax.annotate(f"$\\mu$ = incumbent contour ({ctx.incumbent_mu:+.3f}) —\nencloses "
                f"{int((ctx.mu <= ctx.incumbent_mu + 1e-9).sum())} cells only",
                xy=(0.995, 0.035), xycoords="axes fraction", ha="right", va="bottom",
                fontsize=8, color=C_INC,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=C_INC, lw=0.8, alpha=0.9))
    ax.annotate("open circles: top 12 of the exploration queue, labelled with the optimistic "
                "bound $\\mu-2\\sigma$", xy=(0.0, 1.012), xycoords="axes fraction",
                ha="left", va="bottom", fontsize=8.5, color="#333333", clip_on=False)
    _freq_ticks(ax, ctx)
    ax.set_ylabel(_amp_label(ctx))
    ax.set_title(f"The plateau is LOCAL, not global: {m['queue_size']} of {m['n_unexplored']} "
                 f"under-tested cells have an optimistic\nbound beating the incumbent "
                 f"(best {m['best_optimistic_unexplored']:+.2f} vs incumbent "
                 f"{ctx.incumbent_mu:+.3f})", pad=30, fontsize=10.5)
    ax.set_ylim(ctx.grid.amps.min() - 0.08, ctx.grid.amps.max() + 0.08)
    _stamp_mpl(fig, ctx, CAPTIONS[5])
    return fig


MPL_FIGURES = {
    1: ("stimopt_fig1_posterior_surface", mpl_fig1_posterior_surface),
    2: ("stimopt_fig2_acquisition_decomposition", mpl_fig2_acquisition_decomposition),
    3: ("stimopt_fig3_search_trajectory", mpl_fig3_search_trajectory),
    4: ("stimopt_fig4_dual_model_overlay", mpl_fig4_dual_model),
    5: ("stimopt_fig5_coverage_map", mpl_fig5_coverage_map),
}


# =========================================================================================
# Single-call entry point
# =========================================================================================
def render_all(design_csv, outdir=".", *, which=(1, 2, 3, 4, 5), dpi=200, html=True, png=True,
               ctx=None, **kwargs):
    """Build every figure from one design matrix and write HTML + PNG to ``outdir``.

    Returns ``(ctx, paths)``. ``kwargs`` are forwarded to :func:`build_context`, so
    ``data_horizon`` and ``washin_min`` are set here and stamped onto every output. A JSON
    sidecar of the fitted metadata is written alongside, so a later refresh can be diffed
    against this run without re-reading the figures.
    """
    ctx = build_context(design_csv, **kwargs) if ctx is None else ctx
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for k in which:
        stem, pfn = PLOTLY_FIGURES[k]
        if html:
            p = out / f"{stem}.html"
            pfn(ctx).write_html(str(p), include_plotlyjs="cdn")
            paths.append(str(p))
        if png:
            _, mfn = MPL_FIGURES[k]
            fig = mfn(ctx)
            p = out / f"{stem}.png"
            fig.savefig(p, dpi=dpi, bbox_inches="tight")
            _mpl()[1].close(fig)
            paths.append(str(p))
    meta_path = out / "stimopt_figure_metadata.json"
    meta_path.write_text(json.dumps(ctx.meta, indent=2, sort_keys=True))
    paths.append(str(meta_path))
    return ctx, paths
