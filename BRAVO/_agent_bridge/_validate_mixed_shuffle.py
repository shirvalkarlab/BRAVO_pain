"""Live check of the mixed model's chance test (decision 477) on RCS08's band of decision 475.
1. The new score statistic against lme4's Wald z, refitted at every rotation.
2. How often each p reads <= 0.05 for an unrelated made-up band on RCS08's own samples and weeks."""
import os, sys, json, time, warnings, logging
warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)
import numpy as np, pandas as pd
from scipy.stats import norm
from modules.Biomarkers import bravo_service as bs
from modules.Biomarkers.routines import analytics as an, mixed_model_shuffle as M
from modules.CacheStore import request_memory as rm
import pymer4.models as pm
P = "2e3c75c00d7f4f37b53a048d195f11da"
body = next(r["body"] for r in rm.recent(P) if r["kind"] == "deployment_summary")
cap = {}; Real = pm.Lmer
import sys as _sys
class _PdProxy:                       # catches the model's own data frame AND the rows it kept (m)
    def __getattr__(self, name): return getattr(pd, name)
    def DataFrame(self, *a, **k):
        d = a[0] if a else k.get("data")
        if isinstance(d, dict) and "pain_high" in d:
            f = _sys._getframe(1).f_locals
            cap["t"] = an._times_epoch_s(f["times"])[f["m"]]
        return pd.DataFrame(*a, **k)
an.pd = _PdProxy()
class Capture(Real):
    def __init__(self, formula, data=None, family="gaussian", **k):
        cap["df"] = data.copy(); super().__init__(formula, data=data, family=family, **k)
pm.Lmer = Capture
with bs.pro_request_scope():
    setup = bs._band_validation_setup(dict(body))
    page = an.band_mixedmodel_inference(setup["pooled"], body["Channel"], float(body["CenterHz"]),
           band_width_hz=float(body.get("BandWidthHz", 5)), strategy=setup["label_strategy"],
           low_pct=setup["low_pct"], high_pct=setup["high_pct"])
pm.Lmer = Real; an.pd = pd
df = cap["df"].reset_index(drop=True)
tt = np.asarray(cap["t"], float); srt = np.argsort(tt, kind="stable")
df = df.iloc[srt].reset_index(drop=True); tt = tt[srt]   # rows in time order from here on
t_all = an._times_epoch_s(setup["pooled"]["times"])
mono = bool(np.all(np.diff(t_all[np.isfinite(t_all)]) >= 0)); assert np.all(np.diff(tt) >= 0)
y = df.pain_high.to_numpy(float); x = df.band_power.to_numpy(float); cl = df.cluster.to_numpy()
n = len(y)
print(json.dumps({"band": [body["Channel"], body["CenterHz"]], "n": n, "weeks": int(len(set(cl))),
                  "high": int(y.sum()), "pooled_rows_in_time_order": mono, "time_span_days": round(float(tt[-1]-tt[0])/86400, 1), "same_time_rows": int(np.sum(np.diff(tt) == 0)),
                  "weeks_never_decrease": bool(np.all(np.diff(cl) >= 0)),
                  "page_z": page.get("z"), "page_p": page.get("p")}), flush=True)

null, conv, warn = M.null_fit_lme4(y, cl)
print("null fit: converged", conv, "tau", round(null.tau, 4), "warnings", warn[:2], flush=True)

# 1. every rotation, lme4 refit against the score statistic
def wald(xcol):
    d = df.copy(); d["band_power"] = xcol
    with an._rpy2_converter_ctx():
        m = Real("pain_high ~ band_power + (1|cluster)", data=d, family="binomial"); m.fit(summarize=False)
    w = [str(v) for v in (getattr(m, "warnings", None) or [])]
    return float(m.coefs.loc["band_power"]["Z-stat"]), bool(w)
R = M.rotation_matrix(x)
t = time.perf_counter(); zs = null.score_z(R); t_score = time.perf_counter() - t
t = time.perf_counter(); W = [wald(R[:, k]) for k in range(n)]; t_lme4 = time.perf_counter() - t
zw = np.array([a for a, _ in W]); warned = np.array([b for _, b in W])
ok = np.isfinite(zw) & ~warned
diff = np.abs(zw - zs)
print(json.dumps({
    "rotations": n, "lme4_seconds": round(t_lme4, 1), "score_ms": round(t_score * 1000, 2),
    "observed": {"lme4_wald_z": round(zw[0], 4), "score_z": round(zs[0], 4)},
    "lme4_fits_with_warning": int(warned.sum()),
    "clean": {"n": int(ok.sum()), "correlation": round(float(np.corrcoef(zw[ok], zs[ok])[0, 1]), 5),
              "median_abs_diff": round(float(np.median(diff[ok])), 4), "max_abs_diff": round(float(np.max(diff[ok])), 4)},
    "rotation_p": {"score": M.shuffle_p(zs), "lme4_clean": M.shuffle_p(np.r_[zw[0], zw[1:][ok[1:]]]),
                   "floor": 1 / n},
    "within_week_p_score_10000": M.shuffle_test(null, x, scheme="within_cluster", n_shuffles=10000,
                                                rng=np.random.default_rng(477))["p"],
    "asymptotic_p_score": float(2 * norm.sf(abs(zs[0]))),
}), flush=True)

# 2. false p <= 0.05 for an unrelated made-up band, RCS08's pain, samples and weeks kept
rng = np.random.default_rng(4770)
lag1 = float(np.corrcoef(x[:-1], x[1:])[0, 1])
def ar(phi):
    e = rng.normal(size=n); out = np.empty(n); out[0] = e[0] / np.sqrt(1 - phi ** 2)
    for i in range(1, n): out[i] = phi * out[i - 1] + e[i]
    return (out - out.mean()) / out.std(ddof=1)
N_REC = int(os.environ.get("N_REC", "2000"))
res = {}
for phi in (round(lag1, 3), 0.5, 0.9, 0.97):
    hit = {"rotation": 0, "within_week_1000": 0, "score_normal": 0}
    bands = []
    for _ in range(N_REC):
        xb = ar(phi); bands.append(xb)
        hit["rotation"] += M.shuffle_test(null, xb)["p"] <= 0.05
        hit["within_week_1000"] += M.shuffle_test(null, xb, scheme="within_cluster", n_shuffles=1000, rng=rng)["p"] <= 0.05
        hit["score_normal"] += 2 * norm.sf(abs(null.score_z(xb))) <= 0.05
    res[str(phi)] = {k: round(v / N_REC, 4) for k, v in hit.items()}
    np.save(f"/usr/src/BRAVO/_agent_bridge/_mm_bands_{phi}.npy", np.array(bands))
    print(json.dumps({"lag1": phi, "records": N_REC, "false_p_le_0.05": res[str(phi)]}), flush=True)
df.to_pickle("/usr/src/BRAVO/_agent_bridge/_mm_df.pkl")
print(json.dumps({"real_band_lag1": round(lag1, 3)}))
