import time, json
import numpy as np, pandas as pd
from modules.Biomarkers import bravo_service as bs
from modules.Biomarkers.routines import analytics as an
from modules.CacheStore import request_memory as rm
import pymer4.models as pm
P = "2e3c75c00d7f4f37b53a048d195f11da"
body = next(r["body"] for r in rm.recent(P) if r["kind"] == "deployment_summary")
cap = {}
Real = pm.Lmer
class Capture(Real):
    def __init__(self, formula, data=None, family="gaussian", **k):
        cap["df"] = data.copy(); cap["formula"] = formula
        super().__init__(formula, data=data, family=family, **k)
pm.Lmer = Capture
with bs.pro_request_scope():
    setup = bs._band_validation_setup(dict(body))
    out = an.band_mixedmodel_inference(setup["pooled"], body["Channel"], float(body["CenterHz"]),
          band_width_hz=float(body.get("BandWidthHz", 5)), strategy=setup["label_strategy"],
          low_pct=setup["low_pct"], high_pct=setup["high_pct"])
pm.Lmer = Real
df = cap["df"].reset_index(drop=True)
print("band", body["Channel"], body["CenterHz"], "| n", len(df), "clusters", df.cluster.nunique(),
      "high", int(df.pain_high.sum()), "| page fit: z", out.get("z"), "p", out.get("p"), flush=True)

y = df.pain_high.to_numpy(float); x = df.band_power.to_numpy(float)
codes, cl = np.unique(df.cluster.to_numpy(), return_inverse=True); G = len(codes)
rng = np.random.default_rng(474)
B = 1000
idx = np.arange(len(x))
order = np.argsort(cl, kind="stable"); starts = np.r_[0, np.flatnonzero(np.diff(cl[order])) + 1, len(x)]
def shuffle_within():
    perm = idx.copy()
    for a, b in zip(starts[:-1], starts[1:]):
        g = order[a:b]; perm[g] = rng.permutation(g)
    return perm
X = np.empty((len(x), B + 1)); X[:, 0] = x
for k in range(1, B + 1):
    X[:, k] = x[shuffle_within()]

from modules.Biomarkers.routines.analytics import _rpy2_converter_ctx
def glmer_z(xcol):
    d = df.copy(); d["band_power"] = xcol
    with _rpy2_converter_ctx():
        m = Real("pain_high ~ band_power + (1|cluster)", data=d, family="binomial"); m.fit(summarize=False)
    W.append([str(w) for w in (getattr(m, "warnings", None) or [])])
    return float(m.coefs.loc["band_power"]["Z-stat"])

W = []
# --- A: lme4 loop
K = 200
t = time.perf_counter(); zA = [glmer_z(X[:, k]) for k in range(K + 1)]; tA = time.perf_counter() - t
print(f"A lme4 loop: {K+1} fits in {tA:.1f} s = {tA/(K+1)*1000:.0f} ms per fit", flush=True)

# --- B: score test, null fitted once
t0 = time.perf_counter()
with _rpy2_converter_ctx():
    m0 = Real("pain_high ~ 1 + (1|cluster)", data=df, family="binomial"); m0.fit(summarize=False)
b0 = float(m0.coefs["Estimate"].iloc[0]); tau = float(m0.ranef_var["Var"].iloc[0])
re = m0.ranef; re = re.iloc[:, 0] if hasattr(re, "iloc") and re.ndim == 2 else re
blup = np.array([float(re.loc[str(c)]) if str(c) in re.index.astype(str) else float(re.loc[c]) for c in codes])
t_null = time.perf_counter() - t0
def score_z(X):
    mu = 1 / (1 + np.exp(-(b0 + blup[cl]))); w = mu * (1 - mu); r = y - mu
    U = X.T @ r
    def sinv(M):                                   # Sigma^-1 M, Sigma_j = diag(1/w) + tau 11', Sherman-Morrison per week
        wM = w[:, None] * M
        gs = np.zeros((G, M.shape[1])); np.add.at(gs, cl, wM)
        sw = np.bincount(cl, weights=w, minlength=G)
        return wM - (tau * w[:, None]) * (gs / (1 + tau * sw)[:, None])[cl]
    one = np.ones((len(y), 1)); S1 = sinv(one); SX = sinv(X)
    PX = SX - S1 * ((one.T @ SX) / (one.T @ S1))
    return U / np.sqrt(np.sum(X * PX, axis=0))
t1 = time.perf_counter(); zB = score_z(X); t_vec = time.perf_counter() - t1
Xbig = np.repeat(X[:, 1:], 10, axis=1)
t2 = time.perf_counter(); score_z(Xbig); t_vec10k = time.perf_counter() - t2
print(f"B score test: null fit once {t_null:.2f} s; {B+1} shuffles in {t_vec*1000:.1f} ms; 10,000 in {t_vec10k*1000:.0f} ms", flush=True)

zA = np.array(zA); zb = zB[:K + 1]
ok = np.isfinite(zA)
print(f"observed: lme4 Wald z {zA[0]:.3f}, score z {zB[0]:.3f}")
print(f"per shuffle (n={ok.sum()}): correlation {np.corrcoef(zA[ok], zb[ok])[0,1]:.4f}, "
      f"median |diff| {np.median(np.abs(zA[ok]-zb[ok])):.3f}, max |diff| {np.max(np.abs(zA[ok]-zb[ok])):.3f}")
pA = (1 + np.sum(np.abs(zA[1:]) >= abs(zA[0]))) / (K + 1)
pB_K = (1 + np.sum(np.abs(zB[1:K+1]) >= abs(zB[0]))) / (K + 1)
pB = (1 + np.sum(np.abs(zB[1:]) >= abs(zB[0]))) / (B + 1)
print(f"shuffle p, two-sided: lme4 {K} shuffles {pA:.4f}; score same {K} {pB_K:.4f}; score {B} {pB:.4f}")

warned = np.array([bool(w) for w in W])
big = np.abs(zA - zb) > 1
print(f"lme4 fits with a warning: {warned.sum()} of {len(W)}; shuffles differing by more than 1: {big.sum()}, of which warned: {(big & warned).sum()}")
c = ok & ~warned
print(f"clean lme4 fits (n={c.sum()}): correlation {np.corrcoef(zA[c], zb[c])[0,1]:.4f}, median |diff| {np.median(np.abs(zA[c]-zb[c])):.3f}, max |diff| {np.max(np.abs(zA[c]-zb[c])):.3f}")
from scipy.stats import spearmanr
print(f"rank correlation, all {ok.sum()}: {spearmanr(zA[ok], zb[ok]).correlation:.4f}")
print("largest differences (lme4 z, score z, warned):", [(round(zA[i],2), round(zb[i],2), bool(warned[i])) for i in np.argsort(-np.abs(zA-zb))[:5]])
