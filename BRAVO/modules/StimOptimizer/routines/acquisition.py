"""Acquisition functions, batch selection and the dual stopping rule.

Sign convention throughout: **J is minimised**, so "better" means smaller and the optimistic
(best-case) bound at a cell is ``mu - kappa*sigma``.

Two batch designs, because a pain score integrates over hours to days and that latency is the
dominant cost of a sample:

``select_batch_within_visit``
    q settings evaluated inside one clinic session. Sequential-greedy expected improvement under
    the safety constraint, with rank-and-select to avoid re-proposing an already-tested cell —
    the discrete-space failure mode Sarikhani et al. had to patch, since maximising the
    acquisition on a grid repeatedly returns the incumbent.

``select_batch_between_visit``
    q settings programmed as selectable home groups over a follow-up interval, with a minimum
    grid-separation constraint so the batch spans the space instead of clustering. Kaplan et al.
    2021 (doi:10.1111/biom.13313) formulate this as choosing a group of configurations per
    follow-up interval under a spatially autoregressive prior over neighbouring settings; here
    the GP kernel already carries the neighbour correlation, so the separation constraint is what
    remains to be added.

The stopping rule requires BOTH a plateau condition and a coverage condition
(OBJECTIVE_SPEC section 4). The coverage condition is what makes "we have plateaued" an auditable
claim rather than an impression: while any never-tested cell's optimistic bound still beats the
incumbent, the plateau is not established as global.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm


# --- acquisition functions ---------------------------------------------------------------
def expected_improvement(mu, sd, best, xi=0.0):
    """EI for MINIMISATION. ``best`` is the incumbent posterior mean (smaller is better)."""
    mu = np.asarray(mu, float)
    sd = np.maximum(np.asarray(sd, float), 1e-12)
    z = (best - xi - mu) / sd
    return (best - xi - mu) * norm.cdf(z) + sd * norm.pdf(z)


def ucb_kappa(t):
    """Cole et al.'s GP-UCB schedule, ``kappa_t = 2*log(t^2*pi^2/6)``, floored at zero.

    The raw expression is negative for t = 1 (log of 1.64 is 0.5, so kappa_1 = 0.99 — fine) but
    goes negative for no t >= 1; the floor is defensive only.
    """
    t = np.maximum(np.asarray(t, float), 1.0)
    return np.maximum(2.0 * np.log(t ** 2 * np.pi ** 2 / 6.0), 0.0)


def lower_confidence_bound(mu, sd, t=1, eta=1.0):
    """GP-UCB adapted to minimisation: ``mu - sqrt(eta*kappa_t)*sigma``.

    ``eta`` is the exploration weight. Cole et al.'s configuration sweep found it did *not*
    significantly predict unsafe overshoot — only the safety conservatism beta did — so it is a
    genuine tuning knob rather than a safety-critical one.
    """
    return np.asarray(mu, float) - np.sqrt(float(eta) * ucb_kappa(t)) * np.asarray(sd, float)


def exploration_fraction(sd, t=1, eta=1.0, mu=None):
    """Share of the acquisition value at a cell that comes from the exploration term.

    ``sqrt(eta*kappa_t)*sigma / (|mu| + sqrt(eta*kappa_t)*sigma)``. This is the scalar that
    answers "did this iteration explore or exploit" directly, and it is what the per-iteration
    trace in the explore/exploit figure plots. Returns values in [0, 1]; near 1 means the choice
    was driven by uncertainty, near 0 by predicted benefit.
    """
    sd = np.asarray(sd, float)
    expl = np.sqrt(float(eta) * ucb_kappa(t)) * sd
    denom = expl + (np.abs(np.asarray(mu, float)) if mu is not None else 0.0)
    return np.divide(expl, denom, out=np.ones_like(expl), where=denom > 0)


# --- candidate filtering -----------------------------------------------------------------
def candidate_mask(grid, *, safe_mask=None, tested_idx=None, n_reports=None,
                   exclude_tested=True, min_reports_to_count=3):
    """Cells eligible for selection: safe, and not already adequately tested.

    ``exclude_tested`` implements rank-and-select. Without it, argmax of the acquisition on a
    discrete grid keeps returning the best-sampled cell and the batch collapses to q copies of
    the incumbent.
    """
    m = np.ones(len(grid), bool) if safe_mask is None else np.asarray(safe_mask, bool).copy()
    if exclude_tested:
        if n_reports is not None:
            m &= np.asarray(n_reports, float) < min_reports_to_count
        elif tested_idx is not None:
            m[np.asarray(tested_idx, int)] = False
    return m


# --- batch selection ---------------------------------------------------------------------
@dataclass
class BatchMember:
    index: int
    freq_hz: float
    amp_mA: float
    mu: float
    sd: float
    acq: float
    reason: str
    exploration_fraction: float


def _reason(mu, sd, incumbent_mu, expl_frac, expansion_edge):
    if expansion_edge:
        return "safe-set expansion"
    return "explore" if expl_frac >= 0.5 else "exploit"


def select_batch_within_visit(gp, grid, *, q, safe_mask=None, n_reports=None,
                              incumbent_mu=None, fantasy_var=None, t=1, eta=1.0,
                              exclude_tested=True, expansion_edge_amp=None):
    """q settings for one in-clinic session, by sequential-greedy expected improvement.

    Each selection conditions the surrogate on a fantasy observation at the previously chosen
    cell, so the batch does not pile up on one mode. ``fantasy_var`` should be the observation
    variance a single in-session measurement would actually carry; defaulting it to the median of
    the fitted data's variances is a reasonable stand-in but understates the noise of a
    single-report evaluation.
    """
    q = int(q)
    if q < 1:
        raise ValueError("q must be at least 1")
    cand = candidate_mask(grid, safe_mask=safe_mask, n_reports=n_reports,
                          exclude_tested=exclude_tested)
    if not cand.any():
        raise ValueError(
            "no eligible candidates: the safe set and the already-tested exclusion together "
            "leave nothing. Loosen beta, raise the expansion cap, or allow re-testing.")
    fv = float(np.median(gp.y_var_)) if fantasy_var is None else float(fantasy_var)
    gx = grid.grid_X()
    model = gp
    chosen, out = [], []
    for k in range(q):
        mu, sd = model.predict_grid()
        best = float(np.min(mu)) if incumbent_mu is None else float(incumbent_mu)
        acq = expected_improvement(mu, sd, best)
        avail = cand.copy()
        avail[chosen] = False
        if not avail.any():
            break
        idx = int(np.flatnonzero(avail)[np.argmax(acq[avail])])
        ef = float(exploration_fraction(sd[idx], t=t + k, eta=eta, mu=mu[idx] - best))
        edge = (expansion_edge_amp is not None
                and gx[idx, 1] > float(expansion_edge_amp) - 1e-9)
        out.append(BatchMember(idx, float(gx[idx, 0]), float(gx[idx, 1]), float(mu[idx]),
                               float(sd[idx]), float(acq[idx]),
                               _reason(mu[idx], sd[idx], best, ef, edge), ef))
        chosen.append(idx)
        model = model.with_fantasy(gx[[idx]], fv)
    return out


def select_batch_between_visit(gp, grid, *, q, min_separation, safe_mask=None, n_reports=None,
                               incumbent_mu=None, fantasy_var=None, t=1, eta=1.0,
                               exclude_tested=True, expansion_edge_amp=None):
    """q settings to be programmed as home groups over a follow-up interval.

    Same sequential-greedy machinery, plus a hard minimum separation in *standardised grid
    units* between batch members. Between visits each setting is evaluated over days, so a batch
    that clusters wastes the whole interval confirming one region; the separation constraint buys
    coverage at some cost in expected improvement.

    ``min_separation`` is measured on the same standardised (log2-frequency, amplitude) axes the
    kernel uses, so a value near the fitted amplitude length scale means "batch members should
    not be within one correlation length of each other".
    """
    if float(min_separation) <= 0:
        raise ValueError("min_separation must be positive; use the within-visit selector for 0")
    q = int(q)
    cand = candidate_mask(grid, safe_mask=safe_mask, n_reports=n_reports,
                          exclude_tested=exclude_tested)
    if not cand.any():
        raise ValueError("no eligible candidates for a between-visit batch")
    fv = float(np.median(gp.y_var_)) if fantasy_var is None else float(fantasy_var)
    gx = grid.grid_X()
    Z = grid.transform(gx)
    model = gp
    chosen, out = [], []
    for k in range(q):
        mu, sd = model.predict_grid()
        best = float(np.min(mu)) if incumbent_mu is None else float(incumbent_mu)
        acq = expected_improvement(mu, sd, best)
        avail = cand.copy()
        avail[chosen] = False
        for c in chosen:
            avail &= np.linalg.norm(Z - Z[c], axis=1) >= float(min_separation)
        if not avail.any():
            break                     # separation exhausted the space; short batch is correct
        idx = int(np.flatnonzero(avail)[np.argmax(acq[avail])])
        ef = float(exploration_fraction(sd[idx], t=t + k, eta=eta, mu=mu[idx] - best))
        edge = (expansion_edge_amp is not None
                and gx[idx, 1] > float(expansion_edge_amp) - 1e-9)
        out.append(BatchMember(idx, float(gx[idx, 0]), float(gx[idx, 1]), float(mu[idx]),
                               float(sd[idx]), float(acq[idx]),
                               _reason(mu[idx], sd[idx], best, ef, edge), ef))
        chosen.append(idx)
        model = model.with_fantasy(gx[[idx]], fv)
    return out


# --- exploration queue and stopping ------------------------------------------------------
def exploration_queue(mu, sd, n_reports, incumbent_mu, *, kappa=2.0,
                      min_reports=3, order_by="ei", limit=None):
    """Never-tested cells whose optimistic bound still beats the incumbent.

    This is the operational answer to "is the plateau local?" — not an opinion, a list of
    settings that must be tested before the question can be closed.

    ``order_by``
        ``"ei"`` (default) ranks by expected improvement against the incumbent; ``"optimistic"``
        ranks by the raw optimistic bound ``mu - kappa*sigma``. The distinction matters in
        practice: with a sparse warm start the off-sample posterior SD is large and roughly
        uniform, so the optimistic bound ranks cells by *ignorance* rather than by *promise* and
        the ordering becomes nearly arbitrary. EI ranks by promise while still rewarding
        uncertainty. Membership of the queue is identical either way — only the order changes —
        so the stopping decision itself does not depend on this choice.
    """
    mu = np.asarray(mu, float)
    sd = np.asarray(sd, float)
    unexplored = np.asarray(n_reports, float) < float(min_reports)
    optimistic = mu - float(kappa) * sd
    beats = unexplored & (optimistic < float(incumbent_mu))
    idx = np.flatnonzero(beats)
    if idx.size == 0:
        return idx, dict(order_by=order_by, n_unexplored=int(unexplored.sum()))
    if order_by == "ei":
        score = -expected_improvement(mu[idx], sd[idx], float(incumbent_mu))
    elif order_by == "optimistic":
        score = optimistic[idx]
    else:
        raise ValueError(f"order_by must be 'ei' or 'optimistic', got {order_by!r}")
    idx = idx[np.argsort(score)]
    if limit is not None:
        idx = idx[:int(limit)]
    return idx, dict(order_by=order_by, n_unexplored=int(unexplored.sum()),
                     best_optimistic=float(optimistic[beats].min()))


@dataclass
class StoppingConfig:
    delta: float = 1.0          # NRS points; per-batch increment, deliberately below the MCID
    k: int = 3                  # consecutive batches without improvement
    kappa: float = 2.0          # optimism multiplier for the coverage condition
    min_reports: int = 3        # a cell with fewer reports counts as unexplored
    max_batches: int = 8        # hard ceiling; reaching it means TRUNCATED, not converged


@dataclass
class StoppingDecision:
    stop: bool
    binding: str
    plateau_met: bool
    coverage_met: bool
    truncated: bool
    n_batches: int
    best_history: list = field(default_factory=list)
    queue_size: int = 0
    best_optimistic_unexplored: float = float("nan")
    incumbent_mu: float = float("nan")

    def describe(self):
        if self.truncated:
            return (f"TRUNCATED at the {self.n_batches}-batch ceiling with the coverage "
                    f"condition still violated ({self.queue_size} cells outstanding). "
                    f"This run has NOT found the optimum.")
        if self.stop:
            return f"STOP — both conditions met (binding: {self.binding})."
        return (f"CONTINUE — {self.binding} not met "
                f"(plateau={self.plateau_met}, coverage={self.coverage_met}, "
                f"{self.queue_size} cells outstanding).")


def check_stopping(best_history, mu, sd, n_reports, incumbent_mu, cfg=None):
    """Evaluate both stopping conditions and report which one binds.

    ``best_history`` is the sequence of posterior-best J values, one per completed batch.
    """
    cfg = cfg or StoppingConfig()
    h = [float(v) for v in best_history]
    n = len(h)

    plateau = False
    if n >= cfg.k + 1:
        recent = h[-(cfg.k + 1):]
        gains = [recent[i] - recent[i + 1] for i in range(cfg.k)]   # positive = improvement
        plateau = all(g < cfg.delta for g in gains)

    idx, meta = exploration_queue(mu, sd, n_reports, incumbent_mu, kappa=cfg.kappa,
                                  min_reports=cfg.min_reports)
    coverage = idx.size == 0
    truncated = (n >= cfg.max_batches) and not coverage

    if truncated:
        binding = "hard ceiling"
    elif plateau and coverage:
        binding = "plateau and coverage"
    elif not coverage:
        binding = "coverage"
    else:
        binding = "plateau"

    return StoppingDecision(
        stop=bool(plateau and coverage), binding=binding, plateau_met=bool(plateau),
        coverage_met=bool(coverage), truncated=bool(truncated), n_batches=n,
        best_history=h, queue_size=int(idx.size),
        best_optimistic_unexplored=float(meta.get("best_optimistic", float("nan"))),
        incumbent_mu=float(incumbent_mu))
