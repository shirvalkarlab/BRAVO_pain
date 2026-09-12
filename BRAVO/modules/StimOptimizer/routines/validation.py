"""Phase 4 validation of the warm-start surrogate — one parameterised entry point.

Everything in this module is a function of a design-matrix path plus an explicit
``data_horizon``. Nothing is hard-coded to a particular vintage of the RCS08 record, so a data
refresh regenerates every number, table and figure by re-pointing :func:`run_validation` at the
new CSV. The horizon string is stamped onto every output file and into the report header, so a
stale artifact can always be told apart from a fresh one.

    from StimOptimizer.routines import validation as VAL
    res = VAL.run_validation(
        design_matrix_path="rcs08_bo_design_matrix.csv",
        per_report_path="rcs08_pro_epoch_assignment.csv",
        data_horizon="settings to 2026-06-24, PROs to 2026-06-16",
        outdir=".",
    )

Four steps, in the order the pre-registration requires:

1. :func:`calibration` — leave-one-epoch-out and leave-one-era-out prediction of held-out epoch
   mean J, against a precision-weighted-mean null. This GATES steps 2-4: per OBJECTIVE_SPEC
   section 6, a surrogate that fails held-out calibration may not select settings.
2. :func:`plateau` — posterior over the full grid, unexplored set, coverage condition (b) of the
   stopping rule, and the exploration queue under both orderings.
3. :func:`confound_audit` — era-blocked, precision-weighted re-estimation of the frequency and
   amplitude effects, plus the pseudoreplication structure of repeated PROs within an epoch.
4. :func:`replay` — retrospective sample-efficiency replay against the visited cells as a
   lookup-table simulator, versus uniform random and an equal-interval sweep.

The pass criterion in :data:`PASS_CRITERION` is pre-registered. Do not tune it to a result.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from . import acquisition as ACQ
from . import objective as OBJ
from . import surrogate as SUR

# --- canonical configuration (OBJECTIVE_SPEC section 1 + 2026-08-29 amendments) -----------
FREQ_GRID = [10, 20, 30, 40, 55, 70, 85, 110, 125, 130, 145, 165]
AMP_GRID = np.round(np.arange(0.8, 4.01, 0.1), 2)
# Frequency pinned at one octave (measured degeneracy, OBJECTIVE_SPEC amendment 2026-08-29);
# amplitude LEFT FREE so that leave-one-out folds re-estimate it on the training fold only.
# Pinning both dimensions would make every fold inherit the full-data amplitude hyperparameter,
# which leaks the held-out epoch into the fold and voids the calibration claim.
FIXED_LENGTH_SCALE = [0.823, None]
INCUMBENT_EPOCH = 50.0               # 55 Hz, 1.6 mA left / 1.2 mA right, 60 us
KAPPA = 2.0                          # optimistic bound is mu - KAPPA*sigma (J is minimised)
MIN_REPORTS_EXPLORED = 3             # UNEXPLORED = {x : n_reports(x) < 3}
DEFAULT_WASHIN_MIN = 5.0             # declared exclusion window after a setting change, minutes

#: Pre-registered pass criterion. All three must hold; see PASS_CRITERION_predeclared.md.
PASS_CRITERION = dict(
    C1_loeo_mae_ratio_max=0.90,
    C2_loera_mae_ratio_max=0.90,
    C3_coverage_min=0.85,
    C3_coverage_max=1.00,
    C3_pit_ks_alpha=0.05,
    baseline="precision-weighted mean of the training-fold J",
    consequence="any single failure -> surrogate may not select settings (OBJECTIVE_SPEC s.6)",
)


# --- loading and warm-start fit -----------------------------------------------------------
def load_design(path: str) -> pd.DataFrame:
    """Read an epoch-level design matrix and parse ``t0`` as UTC."""
    es = pd.read_csv(path)
    es["t0"] = pd.to_datetime(es["t0"], utc=True)
    return es.sort_values("t0").reset_index(drop=True)


def build_grid() -> SUR.ParameterGrid:
    return SUR.ParameterGrid(FREQ_GRID, AMP_GRID)


def fit_warm_start(es: pd.DataFrame, grid: SUR.ParameterGrid, *,
                   incumbent_epoch=INCUMBENT_EPOCH, random_state=0):
    """Build J and fit the pinned-length-scale ObjectiveGP on every epoch.

    All epochs enter the fit, including any whose amplitude lies outside the launch grid — the
    GP input space is continuous, and the spec forbids discarding history. Those epochs are
    still excluded from the *explored-cell* bookkeeping in :func:`explored_counts`, because a
    cell outside the grid cannot be a grid cell.
    """
    D = OBJ.build_objective(es, incumbent_epoch=incumbent_epoch)
    X = D[["freq_hz", "amp_mA_Left"]].to_numpy(float)
    gp = SUR.ObjectiveGP(grid, fixed_length_scale=FIXED_LENGTH_SCALE,
                         random_state=random_state).fit(
        X, D["J"].to_numpy(float), D["obs_var"].to_numpy(float))
    return D, gp


def era_labels(D: pd.DataFrame, scheme: str = "quarter") -> pd.Series:
    """Temporal blocking factor.

    ``scheme="quarter"`` is the default and the one used for the reported result: eras are
    calendar quarters of ``t0``. It is defined purely on the clock, so the blocking factor is
    independent of the predictors being adjusted. Defining eras by frequency regime instead
    (``scheme="freq_regime"``) would make the block a function of frequency and would partially
    absorb the very effect the audit is testing, so it is available for sensitivity only.
    """
    t0 = pd.to_datetime(D["t0"], utc=True)
    if scheme == "quarter":
        return t0.dt.year.astype(str) + "Q" + t0.dt.quarter.astype(str)
    if scheme == "freq_regime":
        f = D["freq_hz"].to_numpy(float)
        lab = np.where(f >= 100, "high(>=100Hz)", np.where(f >= 40, "mid(40-99Hz)", "low(<40Hz)"))
        return pd.Series(lab, index=D.index)
    raise ValueError(f"unknown era scheme {scheme!r}")


# --- step 1: held-out calibration ---------------------------------------------------------
def _weighted_mean_baseline(y, v, train, test):
    """Precision-weighted-mean null: predictive mean and variance for the held-out rows."""
    w = 1.0 / v[train]
    m = float(np.sum(w * y[train]) / np.sum(w))
    var_between = float(np.sum(w * (y[train] - m) ** 2) / np.sum(w))
    se2_mean = float(1.0 / np.sum(w))
    return m, var_between + se2_mean + v[test]


def calibration(gp, D: pd.DataFrame, eras: pd.Series, *,
                data_horizon: str) -> tuple[pd.DataFrame, dict]:
    """Leave-one-epoch-out and leave-one-era-out held-out prediction of epoch mean J.

    The predictive distribution for a held-out epoch mean is ``N(mu, sd^2 + obs_var)``: the GP's
    latent posterior SD plus the measurement variance that epoch's own report count carries.
    Coverage and PIT are computed against that total, MAE against ``mu`` alone.
    """
    y = np.asarray(gp.y_, float)
    v = np.asarray(gp.y_var_, float)
    n = len(y)
    rows = []
    for name, groups in (("loeo", np.arange(n)), ("loera", pd.factorize(eras)[0])):
        mu, sd = gp.loo_predict(groups=groups)
        for i in range(n):
            te = groups == groups[i]
            tr = ~te
            bmu, bvar = _weighted_mean_baseline(y, v, tr, np.array([i]))
            tot = float(np.sqrt(sd[i] ** 2 + v[i])) if np.isfinite(sd[i]) else np.nan
            rows.append(dict(
                fold_structure=name, epoch=float(D["epoch"].iloc[i]),
                era=str(eras.iloc[i]), fold=str(groups[i]),
                t0=str(D["t0"].iloc[i]), freq_hz=float(D["freq_hz"].iloc[i]),
                amp_mA_Left=float(D["amp_mA_Left"].iloc[i]), n_reports=int(D["n"].iloc[i]),
                J_observed=float(y[i]), obs_var=float(v[i]),
                gp_mu=float(mu[i]), gp_sd_latent=float(sd[i]), gp_sd_total=tot,
                gp_abs_err=float(abs(y[i] - mu[i])),
                gp_in_95=bool(abs(y[i] - mu[i]) <= 1.959963985 * tot) if np.isfinite(tot) else None,
                gp_pit=float(stats.norm.cdf(y[i], loc=mu[i], scale=tot)) if np.isfinite(tot) else np.nan,
                base_mu=bmu, base_sd_total=float(np.sqrt(bvar[0])),
                base_abs_err=float(abs(y[i] - bmu)),
                base_in_95=bool(abs(y[i] - bmu) <= 1.959963985 * np.sqrt(bvar[0])),
                data_horizon=data_horizon,
            ))
    per_fold = pd.DataFrame(rows)

    summary = {}
    for name, g in per_fold.groupby("fold_structure"):
        ok = g["gp_mu"].notna()
        gg = g[ok]
        pit = gg["gp_pit"].to_numpy(float)
        ks = stats.kstest(pit, "uniform")
        mae_gp = float(gg["gp_abs_err"].mean())
        mae_base = float(gg["base_abs_err"].mean())
        summary[name] = dict(
            n_predicted=int(ok.sum()), n_folds=int(g["fold"].nunique()),
            mae_gp=mae_gp, mae_baseline=mae_base, mae_ratio=mae_gp / mae_base,
            rmse_gp=float(np.sqrt((gg["gp_abs_err"] ** 2).mean())),
            coverage95_gp=float(gg["gp_in_95"].mean()),
            coverage95_baseline=float(gg["base_in_95"].mean()),
            mean_sd_total=float(gg["gp_sd_total"].mean()),
            pit_ks_stat=float(ks.statistic), pit_ks_p=float(ks.pvalue),
        )

    c = PASS_CRITERION
    checks = dict(
        C1_loeo_skill=bool(summary["loeo"]["mae_ratio"] <= c["C1_loeo_mae_ratio_max"]),
        C2_loera_skill=bool(summary["loera"]["mae_ratio"] <= c["C2_loera_mae_ratio_max"]),
        C3_calibration=bool(all(
            c["C3_coverage_min"] <= summary[k]["coverage95_gp"] <= c["C3_coverage_max"]
            and summary[k]["pit_ks_p"] >= c["C3_pit_ks_alpha"] for k in ("loeo", "loera"))),
    )
    verdict = dict(summary=summary, checks=checks, passes=bool(all(checks.values())),
                   criterion=c, data_horizon=data_horizon)
    return per_fold, verdict


# --- step 2: plateau, local or global -----------------------------------------------------
def explored_counts(D: pd.DataFrame, grid: SUR.ParameterGrid) -> tuple[np.ndarray, pd.DataFrame]:
    """Usable-report count per grid cell, and the epoch-to-cell mapping used to get it.

    Epochs whose left amplitude falls outside the grid range contribute to no cell: they are
    outside the declared search space, so counting them as coverage of the nearest edge cell
    would overstate what has been explored.
    """
    amp = D["amp_mA_Left"].to_numpy(float)
    freq = D["freq_hz"].to_numpy(float)
    inside = ((amp >= AMP_GRID.min() - 1e-9) & (amp <= AMP_GRID.max() + 1e-9)
              & (freq >= min(FREQ_GRID) - 1e-9) & (freq <= max(FREQ_GRID) + 1e-9))
    n_reports = np.zeros(len(grid), float)
    idx = np.full(len(D), -1, int)
    if inside.any():
        gi = grid.index_of(np.column_stack([freq[inside], amp[inside]]))
        idx[np.flatnonzero(inside)] = gi
        for k, cell in zip(np.flatnonzero(inside), gi):
            n_reports[cell] += float(D["n"].iloc[k])
    mapping = pd.DataFrame(dict(epoch=D["epoch"].to_numpy(float), freq_hz=freq,
                                amp_mA_Left=amp, n=D["n"].to_numpy(float),
                                in_grid=inside, grid_index=idx))
    return n_reports, mapping


def plateau(gp, grid: SUR.ParameterGrid, D: pd.DataFrame, *, data_horizon: str,
            kappa: float = KAPPA, min_reports: int = MIN_REPORTS_EXPLORED):
    """Coverage condition (b) of the stopping rule, plus the exploration queue.

    Returns ``(queue_df, decision)``. ``queue_df`` carries both orderings; membership is
    identical between them by construction and only ``rank_ei`` / ``rank_optimistic`` differ.
    """
    mu, sd = gp.predict_grid()
    gx = grid.grid_X()
    n_reports, mapping = explored_counts(D, grid)
    inc_row = D.loc[D["epoch"] == INCUMBENT_EPOCH].iloc[0]
    inc_x = np.array([[float(inc_row["freq_hz"]), float(inc_row["amp_mA_Left"])]])
    inc_mu, inc_sd = gp.predict(inc_x)
    incumbent_mu = float(inc_mu[0])

    optimistic = mu - kappa * sd
    ei = ACQ.expected_improvement(mu, sd, incumbent_mu)
    unexplored = n_reports < min_reports

    idx_ei, meta_ei = ACQ.exploration_queue(mu, sd, n_reports, incumbent_mu, kappa=kappa,
                                            min_reports=min_reports, order_by="ei")
    idx_opt, meta_opt = ACQ.exploration_queue(mu, sd, n_reports, incumbent_mu, kappa=kappa,
                                             min_reports=min_reports, order_by="optimistic")
    rank_ei = {int(c): r + 1 for r, c in enumerate(idx_ei)}
    rank_opt = {int(c): r + 1 for r, c in enumerate(idx_opt)}

    q = pd.DataFrame(dict(
        rank_ei=[rank_ei[int(c)] for c in idx_ei],
        rank_optimistic=[rank_opt[int(c)] for c in idx_ei],
        grid_index=[int(c) for c in idx_ei],
        freq_hz=gx[idx_ei, 0], amp_mA=gx[idx_ei, 1],
        mu=mu[idx_ei], sd=sd[idx_ei], optimistic_bound=optimistic[idx_ei],
        expected_improvement=ei[idx_ei], n_reports=n_reports[idx_ei],
    ))
    q["data_horizon"] = data_horizon

    best_unexplored_opt = float(optimistic[unexplored].min()) if unexplored.any() else np.nan
    decision = dict(
        data_horizon=data_horizon, kappa=kappa, min_reports=min_reports,
        n_grid_cells=int(len(grid)), n_unexplored=int(unexplored.sum()),
        n_explored=int((~unexplored).sum()),
        incumbent_mu=incumbent_mu, incumbent_sd=float(inc_sd[0]),
        grid_mu_min=float(mu.min()), grid_mu_max=float(mu.max()),
        grid_sd_min=float(sd.min()), grid_sd_max=float(sd.max()),
        best_unexplored_optimistic=best_unexplored_opt,
        coverage_condition_met=bool(best_unexplored_opt >= incumbent_mu),
        plateau_is_global=bool(best_unexplored_opt >= incumbent_mu),
        queue_size_ei=int(len(idx_ei)), queue_size_optimistic=int(len(idx_opt)),
        queue_membership_identical=bool(set(map(int, idx_ei)) == set(map(int, idx_opt))),
        n_unexplored_beating_incumbent_mu_only=int((unexplored & (mu < incumbent_mu)).sum()),
        observed_epoch_J_min=float(np.min(gp.y_)), observed_epoch_J_max=float(np.max(gp.y_)),
        observed_epoch_J_spread=float(np.ptp(gp.y_)),
        kappa_sd_vs_J_spread=float(kappa * sd.mean() / np.ptp(gp.y_)),
        epochs_outside_grid=int((~mapping["in_grid"]).sum()),
    )

    # The coverage-geometry claim, computed rather than asserted: the low-frequency /
    # above-incumbent-amplitude band is the region the record is thinnest in.
    band = (gx[:, 0] <= 55.0) & (gx[:, 1] > 1.8 + 1e-9)
    band_covered = [(float(gx[i, 0]), float(gx[i, 1]), float(n_reports[i]))
                    for i in np.flatnonzero(band & (n_reports >= min_reports))]
    lowf = (gx[:, 0] == 10.0) & (n_reports >= min_reports)
    decision.update(
        band_label="10-55 Hz and amplitude > 1.8 mA",
        band_n_cells=int(band.sum()),
        band_n_under_threshold=int((band & (n_reports < min_reports)).sum()),
        band_covered_cells=band_covered,
        low_freq_amp_span=[float(gx[lowf, 1].min()), float(gx[lowf, 1].max())]
        if lowf.any() else None,
        amp_length_scale_fitted=float(
            gp.gp_.kernel_.k1.k2.length_scale[1]),
        freq_length_scale_pinned=float(gp.gp_.kernel_.k1.k2.length_scale[0]),
    )
    top = pd.DataFrame(dict(freq=gx[idx_ei[:20], 0])) if len(idx_ei) else pd.DataFrame(
        dict(freq=[]))
    decision["top20_freq_composition"] = {
        str(int(k)): int(v) for k, v in top["freq"].value_counts().items()}
    return q, decision, mapping, dict(mu=mu, sd=sd, optimistic=optimistic, ei=ei,
                                      n_reports=n_reports, unexplored=unexplored)


# --- step 3: confound audit ---------------------------------------------------------------
def confound_audit(es: pd.DataFrame, D: pd.DataFrame, pro: pd.DataFrame | None, *,
                   data_horizon: str, era_scheme: str = "quarter") -> dict:
    """Era-blocked, precision-weighted re-estimation of the frequency and amplitude effects.

    Weighting choice, stated explicitly: **epochs are weighted by their precision**
    (``1/obs_var``, exactly the weights the surrogate uses), rather than modelling the
    per-report pseudoreplication with a mixed model. The epoch is the unit the optimizer acts
    on and ``obs_var`` already encodes report count, exposure duration and observation age, so
    weighting keeps the audit on the same footing as the surrogate it is auditing. The
    pseudoreplication is still quantified — ``icc`` below is estimated from the per-report table
    by one-way variance components — but it is reported as a design fact, not used as an
    alternative test of the same coefficients.
    """
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    d = D.copy()
    d["era"] = era_labels(d, era_scheme).to_numpy()
    d["log2_freq"] = np.log2(d["freq_hz"].astype(float))
    d["amp_L"] = d["amp_mA_Left"].astype(float)
    d["amp_R"] = d["amp_mA_Right"].astype(float)
    d["days"] = (pd.to_datetime(d["t0"], utc=True)
                 - pd.to_datetime(d["t0"], utc=True).min()).dt.total_seconds() / 86400.0
    d["w"] = 1.0 / d["obs_var"].astype(float)

    specs = {
        "M1_naive_unweighted": ("nrs ~ log2_freq + amp_L", None),
        "M2_precision_weighted": ("nrs ~ log2_freq + amp_L", "w"),
        "M3_era_blocked": ("nrs ~ log2_freq + amp_L + C(era)", "w"),
        "M4_era_blocked_plus_days": ("nrs ~ log2_freq + amp_L + C(era) + days", "w"),
        "M5_era_blocked_plus_ampR": ("nrs ~ log2_freq + amp_L + amp_R + C(era)", "w"),
    }
    models, rows = {}, []
    for name, (formula, wcol) in specs.items():
        if wcol is None:
            res = smf.ols(formula, data=d).fit()
        else:
            res = smf.wls(formula, data=d, weights=d[wcol]).fit()
        models[name] = res
        for term in ("log2_freq", "amp_L", "amp_R", "days"):
            if term in res.params.index:
                rows.append(dict(model=name, term=term, coef=float(res.params[term]),
                                 se=float(res.bse[term]), t=float(res.tvalues[term]),
                                 p=float(res.pvalues[term]),
                                 ci_lo=float(res.conf_int().loc[term, 0]),
                                 ci_hi=float(res.conf_int().loc[term, 1]),
                                 n=int(res.nobs), df_resid=float(res.df_resid),
                                 r2=float(res.rsquared)))
    coefs = pd.DataFrame(rows)
    coefs["data_horizon"] = data_horizon

    # collinearity of the historical design
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    Xv = sm.add_constant(d[["log2_freq", "amp_L", "amp_R", "days"]].astype(float))
    vif = {c: float(variance_inflation_factor(Xv.to_numpy(float), i))
           for i, c in enumerate(Xv.columns) if c != "const"}

    # marginal Spearman correlations of the historical record (epoch level)
    sp = {}
    for a, b in (("days", "nrs"), ("days", "log2_freq"), ("days", "amp_L"), ("days", "amp_R"),
                 ("log2_freq", "amp_L"), ("log2_freq", "nrs"), ("amp_L", "nrs")):
        r = stats.spearmanr(d[a].astype(float), d[b].astype(float))
        sp[f"{a}~{b}"] = dict(rho=float(r.statistic), p=float(r.pvalue))

    # joint tests of the searched dimensions after blocking
    joint = {}
    for name in ("M2_precision_weighted", "M3_era_blocked"):
        res = models[name]
        terms = [t for t in ("log2_freq", "amp_L") if t in res.params.index]
        R = np.zeros((len(terms), len(res.params)))
        for i, t in enumerate(terms):
            R[i, list(res.params.index).index(t)] = 1.0
        ft = res.f_test(R)
        joint[name] = dict(F=float(np.ravel(ft.fvalue)[0]), p=float(ft.pvalue),
                           df_num=int(len(terms)), df_denom=float(res.df_resid))

    # pseudoreplication: one-way variance components on the per-report table
    icc = None
    if pro is not None:
        p = pro.copy()
        if "usable" in p.columns:
            p = p[p["usable"].astype(bool)]
        p = p[p["epoch"].isin(set(D["epoch"]))].dropna(subset=["nrs"])
        grp = p.groupby("epoch")["nrs"]
        ni = grp.size().to_numpy(float)
        k = len(ni)
        N = float(ni.sum())
        gm = float(p["nrs"].mean())
        msb = float(np.sum(ni * (grp.mean().to_numpy(float) - gm) ** 2) / (k - 1))
        msw = float(np.sum((grp.transform("mean") - p["nrs"]) ** 2) / (N - k))
        n0 = (N - float(np.sum(ni ** 2)) / N) / (k - 1)
        var_b = max((msb - msw) / n0, 0.0)
        icc_val = var_b / (var_b + msw) if (var_b + msw) > 0 else np.nan
        nbar = N / k
        deff = 1.0 + (nbar - 1.0) * icc_val
        icc = dict(n_reports=int(N), n_epochs=int(k), mean_reports_per_epoch=float(nbar),
                   ms_between=msb, ms_within=msw, var_between=var_b, var_within=msw,
                   icc=float(icc_val), design_effect=float(deff),
                   effective_n_reports=float(N / deff))

    return dict(coefficients=coefs, vif=vif, spearman=sp, joint_tests=joint,
                icc=icc, era_scheme=era_scheme, n_eras=int(d["era"].nunique()),
                era_counts=d["era"].value_counts().sort_index().to_dict(),
                data_horizon=data_horizon)


# --- step 4: retrospective sample-efficiency replay ---------------------------------------
def _lookup_table(D: pd.DataFrame, grid: SUR.ParameterGrid):
    """Collapse the historical epochs onto their grid cells: precision-weighted J per cell."""
    _, mapping = explored_counts(D, grid)
    m = mapping[mapping["in_grid"]].copy()
    m["J"] = D["J"].to_numpy(float)[m.index]
    m["obs_var"] = D["obs_var"].to_numpy(float)[m.index]
    cells, Jc, Vc = [], [], []
    for cell, g in m.groupby("grid_index"):
        w = 1.0 / g["obs_var"].to_numpy(float)
        cells.append(int(cell))
        Jc.append(float(np.sum(w * g["J"].to_numpy(float)) / np.sum(w)))
        Vc.append(float(1.0 / np.sum(w)))
    order = np.argsort(cells)
    return (np.asarray(cells, int)[order], np.asarray(Jc, float)[order],
            np.asarray(Vc, float)[order])


def _samples_to_best(order, target_positions):
    """1-based index of the first measurement that lands on a target cell, else NaN."""
    for k, c in enumerate(order):
        if c in target_positions:
            return k + 1
    return np.nan


def _bo_replay_one(seed, cells, Jc, Vc, grid, targets, n_init, budget, random_state=0):
    rng = np.random.default_rng(seed)
    init = list(rng.choice(len(cells), size=n_init, replace=False))
    measured = list(init)
    gx = grid.grid_X()
    while len(measured) < budget:
        if any(cells[i] in targets for i in measured):
            break
        Xm = gx[cells[measured]]
        gp = SUR.ObjectiveGP(grid, fixed_length_scale=FIXED_LENGTH_SCALE,
                             n_restarts=4, random_state=random_state).fit(
            Xm, Jc[measured], Vc[measured])
        avail = np.zeros(len(grid), bool)
        avail[cells] = True
        avail[cells[measured]] = False
        if not avail.any():
            break
        b = ACQ.select_batch_within_visit(gp, grid, q=1, safe_mask=avail,
                                         incumbent_mu=0.0, exclude_tested=False)
        if not b:
            break
        pick = int(np.flatnonzero(np.asarray(cells) == b[0].index)[0])
        measured.append(pick)
    return _samples_to_best([cells[i] for i in measured], targets)


def _random_replay_one(seed, cells, targets, budget):
    rng = np.random.default_rng(seed)
    order = cells[rng.permutation(len(cells))][:budget]
    return _samples_to_best(order, targets)


def _sweep_replay_one(seed, cells, grid, targets, budget):
    """Equal-interval sweep: frequency levels in order, amplitudes coarse-to-fine within each.

    The clinical analogue of a monopolar review. The frequency starting point is rotated by the
    seed so the comparison is a distribution rather than one arbitrary schedule.
    """
    rng = np.random.default_rng(seed)
    gx = grid.grid_X()
    f = gx[cells, 0]
    a = gx[cells, 1]
    freqs = np.unique(f)
    roll = int(rng.integers(len(freqs)))
    freqs = np.roll(freqs, roll)
    order = []
    for fv in freqs:
        sel = np.flatnonzero(f == fv)
        amps = a[sel]
        # coarse-to-fine: alternate ends inward, an equal-interval bisection of the amp range
        srt = sel[np.argsort(amps)]
        picks, lo, hi = [], 0, len(srt) - 1
        while lo <= hi:
            picks.append(srt[lo])
            if hi != lo:
                picks.append(srt[hi])
            lo += 1
            hi -= 1
        order.extend(int(cells[i]) for i in picks)
    return _samples_to_best(order[:budget], targets)


def replay(D: pd.DataFrame, grid: SUR.ParameterGrid, *, data_horizon: str, n_seeds: int = 200,
           n_init: int = 3, budget: int | None = None, n_jobs: int = -1) -> dict:
    """Lookup-table replay over the historically visited cells.

    The simulator may only be queried at cells the patient actually occupied, and returns that
    cell's precision-weighted epoch mean J. Samples-to-best counts measurements, including the
    ``n_init`` random initial measurements the GP needs before it can be fitted at all, so the
    three strategies are compared on the same currency.
    """
    cells, Jc, Vc = _lookup_table(D, grid)
    best = float(np.min(Jc))
    targets = set(int(c) for c, j in zip(cells, Jc) if j <= best + 1e-12)
    n_cells = len(cells)
    budget = n_cells if budget is None else int(budget)
    seeds = list(range(n_seeds))

    def _bo_all():
        # Process-based parallelism is unavailable in some sandboxes (no POSIX semaphores), and
        # the thread backend gains little because the GP refit is Python-bound. Try joblib,
        # fall back to serial rather than failing the whole replay.
        if n_jobs in (0, 1):
            raise RuntimeError("serial requested")
        from joblib import Parallel, delayed
        return Parallel(n_jobs=n_jobs, prefer="threads")(
            delayed(_bo_replay_one)(s, cells, Jc, Vc, grid, targets, n_init, budget)
            for s in seeds)

    try:
        bo = _bo_all()
    except Exception:
        bo = [_bo_replay_one(s, cells, Jc, Vc, grid, targets, n_init, budget) for s in seeds]
    rnd = [_random_replay_one(s, cells, targets, budget) for s in seeds]
    swp = [_sweep_replay_one(s, cells, grid, targets, budget) for s in seeds]

    def stat(v):
        v = np.asarray(v, float)
        fin = v[np.isfinite(v)]
        return dict(n_seeds=int(len(v)), n_found=int(len(fin)),
                    median=float(np.median(fin)), q1=float(np.percentile(fin, 25)),
                    q3=float(np.percentile(fin, 75)), mean=float(fin.mean()),
                    min=float(fin.min()), max=float(fin.max()))

    gx = grid.grid_X()
    tgt = [dict(grid_index=int(c), freq_hz=float(gx[c, 0]), amp_mA=float(gx[c, 1]),
                J=float(j)) for c, j in zip(cells, Jc) if int(c) in targets]
    out = dict(data_horizon=data_horizon, n_visited_cells=n_cells, budget=budget,
               n_init=n_init, historical_best_J=best, targets=tgt,
               bayesopt=stat(bo), uniform_random=stat(rnd), equal_interval_sweep=stat(swp),
               raw=dict(bayesopt=[None if not np.isfinite(x) else float(x) for x in bo],
                        uniform_random=[None if not np.isfinite(x) else float(x) for x in rnd],
                        equal_interval_sweep=[None if not np.isfinite(x) else float(x) for x in swp]))
    for k in ("uniform_random", "equal_interval_sweep"):
        u = stats.mannwhitneyu(np.asarray(bo, float), np.asarray(out["raw"][k], float),
                              alternative="less")
        out[f"mwu_bo_vs_{k}"] = dict(U=float(u.statistic), p=float(u.pvalue))
    return out


# --- entry point --------------------------------------------------------------------------
def run_validation(design_matrix_path: str, *, data_horizon: str, per_report_path: str | None = None,
                   outdir: str = ".", era_scheme: str = "quarter", n_seeds: int = 200,
                   incumbent_epoch: float = INCUMBENT_EPOCH, washin_min: float = DEFAULT_WASHIN_MIN,
                   write_report: bool = True, make_figure: bool = True,
                   n_jobs: int = 1) -> dict:
    """Run all four validation steps and write the three deliverables into ``outdir``.

    ``data_horizon`` is a free-text statement of how current the input data is (e.g.
    ``"settings to 2026-06-24, PROs to 2026-06-16"``). It is stamped into every CSV, the report
    header and the figure caption, and it is required — there is no default, because an
    unlabelled vintage is how a stale number gets read as a current one. ``washin_min`` is the
    declared post-change exclusion window the design matrix was built with; it is stamped
    alongside the horizon because the same raw record yields a different design matrix under a
    different window (see the wash-in sensitivity table).
    """
    os.makedirs(outdir, exist_ok=True)
    stamp = f"{data_horizon}; wash-in {washin_min:g} min"
    es = load_design(design_matrix_path)
    pro = pd.read_csv(per_report_path) if per_report_path else None
    grid = build_grid()
    D, gp = fit_warm_start(es, grid, incumbent_epoch=incumbent_epoch)
    eras = era_labels(D, era_scheme)

    per_fold, verdict = calibration(gp, D, eras, data_horizon=stamp)
    queue, decision, mapping, surf = plateau(gp, grid, D, data_horizon=stamp)
    audit = confound_audit(es, D, pro, data_horizon=stamp, era_scheme=era_scheme)
    rep = replay(D, grid, data_horizon=stamp, n_seeds=n_seeds, n_jobs=n_jobs)

    paths = {}
    paths["loo"] = os.path.join(outdir, "rcs08_loo_calibration.csv")
    per_fold.to_csv(paths["loo"], index=False)
    paths["queue"] = os.path.join(outdir, "rcs08_exploration_queue.csv")
    queue.to_csv(paths["queue"], index=False)

    if make_figure:
        try:
            from .validation_plots import plot_pit_calibration
            paths["figure"] = plot_pit_calibration(
                per_fold, verdict, os.path.join(outdir, "rcs08_pit_calibration.png"),
                data_horizon=stamp)
        except Exception as exc:            # a figure must never take the numbers down
            paths["figure_error"] = repr(exc)

    result = dict(data_horizon=data_horizon, washin_min=float(washin_min), stamp=stamp,
                  design_matrix_path=design_matrix_path,
                  per_report_path=per_report_path, era_scheme=era_scheme,
                  fixed_length_scale=[None if v is None else float(v)
                                      for v in FIXED_LENGTH_SCALE],
                  hyperparameters=gp.hyperparameters, verdict=verdict, decision=decision,
                  audit={k: v for k, v in audit.items() if k != "coefficients"},
                  coefficients=audit["coefficients"], replay=rep, paths=paths,
                  n_epochs=int(len(D)), n_reports_total=int(D["n"].sum()),
                  n_epochs_n_ge_3=int((D["n"] >= 3).sum()))

    if write_report:
        paths["report"] = os.path.join(outdir, "PHASE4_validation_RCS08.md")
        with open(paths["report"], "w") as fh:
            fh.write(render_report(result, per_fold, queue, audit))
    paths["json"] = os.path.join(outdir, "phase4_validation_summary.json")
    with open(paths["json"], "w") as fh:
        json.dump({k: v for k, v in result.items() if k != "coefficients"}, fh,
                  indent=2, default=str)
    return result


def render_report(result: dict, per_fold: pd.DataFrame, queue: pd.DataFrame,
                  audit: dict) -> str:
    """Markdown report. Import from :func:`run_validation`; not intended to be called alone."""
    from .validation_report import render
    return render(result, per_fold, queue, audit)
