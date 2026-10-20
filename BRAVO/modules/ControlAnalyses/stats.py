"""The statistics of the control analyses, free of the database so they are tested on constructed
records (2026-09-24). The runners feed them the modules' own matched data."""
import numpy as np


def _ranks(v):
    v = np.asarray(v, dtype=float)
    order = v.argsort(kind="stable")
    r = np.empty(v.size)
    r[order] = np.arange(v.size)
    # average ties
    _, inv, counts = np.unique(v, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=r)
    return (sums / counts)[inv]


def spearman_within(x, y, strata=None):
    """Spearman correlation; with `strata`, ranks are taken inside each stratum (as fractions of
    its size), so a shift between stretches is not read as a correlation."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if strata is None:
        rx, ry = _ranks(x), _ranks(y)
    else:
        strata = np.asarray(strata)
        rx, ry = np.empty(x.size), np.empty(y.size)
        for s in np.unique(strata):
            m = strata == s
            rx[m] = (_ranks(x[m]) + 0.5) / m.sum()
            ry[m] = (_ranks(y[m]) + 0.5) / m.sum()
    if np.std(rx) == 0 or np.std(ry) == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def day_resampled_rho(x, y, days, strata=None, *, n_boot=2000, seed=0):
    """`(rho, lo, hi, p)`: the point value and a 95% interval from resampling whole days, and the
    two-sided share of resamples on the far side of zero. Fewer than 100 usable resamples: NaNs."""
    x, y, days = np.asarray(x, float), np.asarray(y, float), np.asarray(days)
    strata = None if strata is None else np.asarray(strata)
    point = spearman_within(x, y, strata)
    rng = np.random.default_rng(seed)
    ud = np.unique(days)
    idx = {d: np.flatnonzero(days == d) for d in ud}
    bs = []
    for _ in range(int(n_boot)):
        ix = np.concatenate([idx[d] for d in rng.choice(ud, ud.size, replace=True)])
        v = spearman_within(x[ix], y[ix], None if strata is None else strata[ix])
        if np.isfinite(v):
            bs.append(v)
    bs = np.asarray(bs)
    if bs.size < 100:
        return point, float("nan"), float("nan"), float("nan")
    lo, hi = np.percentile(bs, [2.5, 97.5])
    p = min(1.0, 2 * min(np.mean(bs <= 0), np.mean(bs >= 0)))
    return point, float(lo), float(hi), float(p)


def bh_q(p):
    """Benjamini-Hochberg q values; a missing p counts as 1."""
    p = np.asarray(p, float)
    p = np.where(np.isfinite(p), p, 1.0)
    n = p.size
    if n == 0:
        return p
    o = np.argsort(p)
    q = np.empty(n)
    q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1.0)


def dose_history(times_s, step_times_s, step_amps, tau_h):
    """The current remembered with time constant `tau_h` hours at each time: an exponentially
    weighted average of the delivered current, exact for a current that changes in steps. Before
    the first step nothing was delivered. `tau_h` 0 is the current in force."""
    t = np.asarray(times_s, float)
    s = np.asarray(step_times_s, float)
    a = np.asarray(step_amps, float)
    if tau_h == 0:
        k = np.searchsorted(s, t, side="right") - 1
        return np.where(k >= 0, a[np.clip(k, 0, None)], np.nan)
    tau = float(tau_h) * 3600.0
    e = np.concatenate([s[1:], [np.inf]])
    out = np.zeros(t.size)
    for k in range(s.size):
        on = t > s[k]
        hi = np.minimum(e[k], t[on])
        out[on] += a[k] * (np.exp(-(t[on] - hi) / tau) - np.exp(-(t[on] - s[k]) / tau))
    return out


def tau_curve(times_s, y, sides, taus_h, folds, *, n_boot=2000, seed=0, days=None):
    """For each time constant: held-out R2 of pain on a squared term in each side's remembered
    current, and the change in held-out squared error against the current in force (tau 0) with a
    95% interval resampling whole days (or single rows when `days` is None). `sides` maps a side
    name to its `(step_times, step_amps)`; `folds` are `(train, test)` index pairs."""
    t, y = np.asarray(times_s, float), np.asarray(y, float)
    base = np.full(t.size, np.nan)
    for tr, te in folds:
        base[te] = np.mean(y[tr])
    err = {}
    rows = []
    for tau in taus_h:
        cols = [np.ones(t.size)]
        corr = {}
        for name, (st, sa) in sides.items():
            d = dose_history(t, st, sa, tau)
            cols += [d, d ** 2]
            corr[name] = float(np.corrcoef(np.nan_to_num(d), t)[0, 1]) if np.std(np.nan_to_num(d)) > 0 else float("nan")
        X = np.column_stack(cols)
        ok = np.isfinite(X).all(axis=1)
        pred = np.full(t.size, np.nan)
        for tr, te in folds:
            tr = tr[ok[tr]]
            beta, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
            pred[te] = X[te] @ beta
        e2 = (y - pred) ** 2
        err[tau] = e2
        r2 = 1.0 - np.nanmean(e2) / np.nanmean((y - base) ** 2)
        rows.append(dict(tau_h=tau, r2=float(r2), mse=float(np.nanmean(e2)), dose_time_corr=corr))
    rng = np.random.default_rng(seed)
    unit = np.asarray(days) if days is not None else np.arange(t.size).astype(str)
    uu = np.unique(unit)
    idx = {u: np.flatnonzero(unit == u) for u in uu}
    for row in rows:
        diff = err[row["tau_h"]] - err[taus_h[0]]
        row["change_vs_now"] = float(np.nanmean(diff))
        if row["tau_h"] == taus_h[0]:
            row["change_lo"] = row["change_hi"] = 0.0
            continue
        bs = [np.nanmean(diff[np.concatenate([idx[u] for u in rng.choice(uu, uu.size)])]) for _ in range(int(n_boot))]
        row["change_lo"], row["change_hi"] = (float(v) for v in np.percentile(bs, [2.5, 97.5]))
    return rows
