"""Step B of the contact-aware Stim Optimizer: how much do the Left contacts differ? (the PI's
go-ahead of 2026-10-01; plan `.planning/2026-09-30-contact-aware-stim-optimizer/`).

WHAT IT FITS. One Gaussian process over the stretches of unchanged settings, with the pain score
J (NRS points against the setting in force, lower is better) as

    J(contact, x) = shared(x) + deviation_contact(x) + noise,      x = (rate, L current, R current)

`shared` is one surface for every Left contact; `deviation_contact` is a separate surface for each
Left contact, and its SIZE (the variance s1^2, against the shared surface's s0^2) is estimated
from the data. The contact share, s1^2 / (s0^2 + s1^2), answers "do the Left contacts differ?":
near 0 they behave alike and their data pool; near 1 each contact stands on its own. Sarikhani
et al. 2022 (one GP with contact as a discrete input) is the case where the two terms are tied.

A STRETCH WITH LEFT AT 0 mA CARRIES NO DEVIATION: with no current the contact makes no difference
(the PI's ruling of 2026-10-01), so such a stretch informs the shared surface only.

SAME CONVENTIONS AS THE LIVE FIT (`surrogate.ObjectiveGP`): a Matern 3/2 kernel; rate on a log2
axis with its length scale PINNED at one octave (OBJECTIVE_SPEC.md, 2026-09-23: the profiled
likelihood is bimodal, so the value is a stated assumption); current length scales fitted; each
stretch's own observation variance on the diagonal (`obs_var`, from `objective.build_objective`);
J standardised before fitting. Time is modelled nowhere (decisions 193/196).

HOW IT IS JUDGED (the module's own rule, README: "if it cannot predict a held-out era better ... it
has not earned its extra parameters"). `compare` leaves out one calendar day at a time, refits
every model on the rest, and predicts the held-out stretches with three models: `pooled` (the old
model: contact ignored), `separate` (step A: one surface per contact, Left-off stretches in each)
and `partial` (this one). The mean absolute error is in NRS points; the difference between two
models carries a bootstrap interval over the held-out days.

NOT REACHED BY ANY PAGE. Offline analysis; nothing in the request path calls it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize, stats

LEFT_OFF = "off (Left 0 mA)"           # the same label stage1_openloop uses
RATE_LENGTH_SCALE_OCTAVES = 1.0       # pinned, OBJECTIVE_SPEC.md (2026-09-23)
AMP_LS_BOUNDS = (0.3, 20.0)           # mA
VAR_BOUNDS = (1e-6, 1e2)              # on the standardised J scale
NUGGET_BOUNDS = (1e-6, 1.0)
N_BOOT = 2000


def _matern32(A, B, ls):
    d = (A[:, None, :] - B[None, :, :]) / np.asarray(ls, float)[None, None, :]
    r = np.sqrt(np.maximum((d ** 2).sum(-1), 0.0))
    s = np.sqrt(3.0) * r
    return (1.0 + s) * np.exp(-s)


def _inputs(d):
    return np.column_stack([np.log2(d["freq_hz"].to_numpy(float)),
                            d["amp_mA_Left"].to_numpy(float),
                            d["amp_mA_Right"].to_numpy(float)])


def _labels(d):
    lab = d["left_contact"].astype(object).to_numpy()
    off = d["amp_mA_Left"].to_numpy(float) <= 0.0
    lab = np.where(off, LEFT_OFF, lab)
    return lab


def _same(a, b):
    """1 where two stretches share a Left contact that is carrying current, else 0."""
    a = np.asarray(a, object)[:, None]
    b = np.asarray(b, object)[None, :]
    return ((a == b) & (a != LEFT_OFF) & (b != LEFT_OFF)).astype(float)


class PartialPoolingGP:
    """The fit described in the module docstring. `contact_term=False` gives the pooled model
    (the deviation's size fixed at zero), which is the null for the likelihood-ratio test."""

    def __init__(self, *, contact_term=True, n_restarts=6, random_state=0):
        self.contact_term = bool(contact_term)
        self.n_restarts = int(n_restarts)
        self.random_state = random_state

    # parameter vector (logs): s0^2, [s1^2], ls_L, ls_R, nugget
    def _unpack(self, th):
        th = np.exp(th)
        if self.contact_term:
            s0, s1, lL, lR, nug = th
        else:
            s0, lL, lR, nug = th
            s1 = 0.0
        return s0, s1, lL, lR, nug

    def _K(self, th, X, lab, alpha):
        s0, s1, lL, lR, nug = self._unpack(th)
        M = _matern32(X, X, [RATE_LENGTH_SCALE_OCTAVES, lL, lR])
        K = s0 * M + s1 * M * _same(lab, lab)
        K[np.diag_indices_from(K)] += alpha + nug
        return K

    def _nlml(self, th, X, lab, y, alpha):
        K = self._K(th, X, lab, alpha)
        try:
            L = np.linalg.cholesky(K)
        except np.linalg.LinAlgError:
            return 1e10
        a = np.linalg.solve(L.T, np.linalg.solve(L, y))
        return float(0.5 * y @ a + np.log(np.diag(L)).sum() + 0.5 * len(y) * np.log(2 * np.pi))

    def fit(self, d: pd.DataFrame):
        d = d.reset_index(drop=True)
        X, lab = _inputs(d), _labels(d)
        y = d["J"].to_numpy(float)
        self._loc, self._scale = float(y.mean()), float(max(y.std(ddof=0), 1e-9))
        yz = (y - self._loc) / self._scale
        alpha = d["obs_var"].to_numpy(float) / self._scale ** 2
        b = [VAR_BOUNDS] + ([VAR_BOUNDS] if self.contact_term else []) + [AMP_LS_BOUNDS, AMP_LS_BOUNDS, NUGGET_BOUNDS]
        lb = np.log([x[0] for x in b]); ub = np.log([x[1] for x in b])
        rng = np.random.default_rng(self.random_state)
        starts = [np.log([0.5] + ([0.5] if self.contact_term else []) + [2.0, 2.0, 1e-2])]
        starts += [rng.uniform(lb, ub) for _ in range(self.n_restarts)]
        best = None
        for th0 in starts:
            r = optimize.minimize(self._nlml, th0, args=(X, lab, yz, alpha), method="L-BFGS-B",
                                  bounds=list(zip(lb, ub)))
            if best is None or r.fun < best.fun:
                best = r
        self.theta_, self.lml_ = best.x, -float(best.fun)
        self.X_, self.lab_, self.yz_, self.alpha_ = X, lab, yz, alpha
        K = self._K(self.theta_, X, lab, alpha)
        self.L_ = np.linalg.cholesky(K)
        self.a_ = np.linalg.solve(self.L_.T, np.linalg.solve(self.L_, yz))
        return self

    @property
    def contact_share(self) -> float:
        s0, s1, *_ = self._unpack(self.theta_)
        return float(s1 / (s0 + s1)) if (s0 + s1) > 0 else float("nan")

    @property
    def hyperparameters(self) -> dict:
        s0, s1, lL, lR, nug = self._unpack(self.theta_)
        return dict(shared_variance=float(s0), contact_variance=float(s1),
                    length_scale_left_mA=float(lL), length_scale_right_mA=float(lR),
                    length_scale_rate_octaves=RATE_LENGTH_SCALE_OCTAVES, nugget=float(nug),
                    log_marginal_likelihood=float(self.lml_))

    def predict(self, d: pd.DataFrame) -> np.ndarray:
        s0, s1, lL, lR, _ = self._unpack(self.theta_)
        Xs, labs = _inputs(d), _labels(d)
        M = _matern32(Xs, self.X_, [RATE_LENGTH_SCALE_OCTAVES, lL, lR])
        ks = s0 * M + s1 * M * _same(labs, self.lab_)
        return ks @ self.a_ * self._scale + self._loc


def _separate_predict(train, test):
    """Step A's model: one surface per Left contact, the Left-off stretches in each; a held-out
    Left-off stretch is predicted from all the training stretches (it belongs to every group)."""
    out = np.empty(len(test))
    tlab = _labels(test)
    trlab = _labels(train)
    for i, c in enumerate(tlab):
        rows = train if c == LEFT_OFF else train[(trlab == c) | (trlab == LEFT_OFF)]
        if len(rows) < 3 or c not in set(trlab) and c != LEFT_OFF:
            rows = train                     # a contact unseen in training: nothing of its own
        m = PartialPoolingGP(contact_term=False, n_restarts=2).fit(rows)
        out[i] = m.predict(test.iloc[[i]])[0]
    return out


def _day(t0):
    t = pd.to_datetime(t0, utc=True)
    return t.dt.tz_convert("America/Los_Angeles").dt.date.astype(str)


def compare(d: pd.DataFrame, *, n_restarts=6, n_boot=N_BOOT, seed=0) -> dict:
    """The contact share, the likelihood-ratio test of "no contact effect", and the
    leave-one-day-out comparison of pooled / separate / partial. Never raises on thin data:
    ``available`` False with a reason."""
    d = d.dropna(subset=["freq_hz", "amp_mA_Left", "amp_mA_Right", "J", "obs_var"]).reset_index(drop=True)
    lab = _labels(d)
    active = sorted({c for c in lab if c != LEFT_OFF and c is not None})
    counts = {str(c): int((lab == c).sum()) for c in list(active) + [LEFT_OFF]}
    if len(active) < 2:
        return {"available": False, "n": int(len(d)), "stretches_per_contact": counts,
                "reason": "only one Left contact carries current here, so there is nothing to compare"}

    part = PartialPoolingGP(contact_term=True, n_restarts=n_restarts, random_state=seed).fit(d)
    pool = PartialPoolingGP(contact_term=False, n_restarts=n_restarts, random_state=seed).fit(d)
    lr = max(0.0, 2.0 * (part.lml_ - pool.lml_))
    p = float(0.5 * stats.chi2.sf(lr, 1)) if lr > 0 else 1.0     # boundary: 50:50 mixture

    days = _day(d["t0"]).to_numpy()
    per_fold, errs = [], {"pooled": [], "separate": [], "partial": []}
    for day in sorted(set(days)):
        te, tr = d[days == day], d[days != day]
        if len(tr) < 5:
            continue
        y = te["J"].to_numpy(float)
        pred = {
            "pooled": PartialPoolingGP(contact_term=False, n_restarts=2, random_state=seed).fit(tr).predict(te),
            "partial": PartialPoolingGP(contact_term=True, n_restarts=2, random_state=seed).fit(tr).predict(te),
            "separate": _separate_predict(tr, te),
        }
        e = {k: float(np.mean(np.abs(v - y))) for k, v in pred.items()}
        for k in errs:
            errs[k].append(e[k])
        per_fold.append({"day": str(day), "n": int(len(te)), "error": e})

    E = {k: np.asarray(v) for k, v in errs.items()}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(per_fold), size=(int(n_boot), len(per_fold)))

    def _ci(a, b):
        diff = E[a] - E[b]
        boot = diff[idx].mean(axis=1)
        return [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]

    return {
        "available": True, "n": int(len(d)), "stretches_per_contact": counts,
        "contact_share": part.contact_share,
        "partial": part.hyperparameters, "pooled": pool.hyperparameters,
        "likelihood_ratio": float(lr), "no_contact_effect_p": p,
        "held_out": {
            "unit": "NRS points (J, against the setting in force)",
            "n_folds": len(per_fold),
            "mae": {k: float(v.mean()) for k, v in E.items()},
            "mae_difference_ci": {"partial_minus_pooled": _ci("partial", "pooled"),
                                  "partial_minus_separate": _ci("partial", "separate")},
            "per_fold": per_fold,
        },
    }
