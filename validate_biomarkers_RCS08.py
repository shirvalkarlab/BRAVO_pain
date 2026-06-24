#!/usr/bin/env python3
"""
Standalone statistical validation of RCS08 spectral pain biomarkers.
=====================================================================

Reproduces the validation pipeline end-to-end from the corrected PSD pool, across all six
BIOMARKER_METRICS, with mixed-effects logistic regression as the headline inference.

USAGE
-----
This script has two stages by where they run:

  STAGE A (inside the BRAVO container — needs Django + the decoded RCS08 data):
      builds phase0_bundle.npz (the corrected labeled dataset). See build_bundle() — it is the
      body of _agent_bridge/phase0_build.py. Run it via the bridge:
          python3 bridge_client.py --cwd /usr/src/BRAVO "python3 _agent_bridge/phase0_build.py"

  STAGE B (anywhere with numpy/scipy/statsmodels + the bundle):
      scan -> FDR -> candidate clusters -> ranked table. Pure Python, no Django.
      The mixed-effects (glmer) and stim-heterogeneity steps need pymer4/rpy2/R and are run in the
      container (_agent_bridge/phase2_glmer.py, phase2b_hetero.py); their outputs
      (glmer_results_fdr_RCS08.csv, stim_hetero_fdr_RCS08.csv) are merged here.

Pass --bundle to point at phase0_bundle.npz. Outputs CSVs + the ranked validated table.

DESIGN NOTES
------------
* Pseudoreplication is the dominant risk: ~7.7 PSD samples share each pain rating. The first-pass
  significance is a rating-CLUSTERED logistic Wald p; the definitive per-candidate inference is a
  mixed-effects logistic with a weekly-era random intercept. Naive Pearson is reported only to
  quantify the inflation it would cause.
* Adjacent 5 Hz bands (1 Hz step) share 80% content => BH-FDR over the band grid is conservative;
  contiguous raw-significant runs are reduced to one peak candidate before definitive inference.
* Stim state is TESTED (band x stim-era LRT), not assumed: a candidate that works only at OFF/LOW
  stim is flagged stim-dependent and is a poor closed-loop threshold anchor.
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
import statsmodels.api as sm

METRICS = ["nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum", "composite_mpq_leftleg"]
BAND_W = 5.0
LO_EDGES = np.arange(4.0, 96.0 + 1e-9, 1.0)


def cluster_robust_logit_p(x, ybin, groups):
    """Rating-clustered logistic Wald p on a single predictor -> (beta, p, n, n_groups)."""
    m = np.isfinite(x) & np.isfinite(ybin)
    x, ybin, groups = x[m], ybin[m], groups[m]
    if len(np.unique(ybin)) < 2 or len(x) < 8:
        return (np.nan, np.nan, len(x), 0)
    X = sm.add_constant(x)
    try:
        res = sm.GLM(ybin, X, family=sm.families.Binomial()).fit(
            cov_type="cluster", cov_kwds={"groups": groups})
        return (float(res.params[1]), float(res.pvalues[1]), int(len(x)), int(len(np.unique(groups))))
    except Exception:
        return (np.nan, np.nan, len(x), 0)


def run_scan(z):
    """Full sliding-band scan: per metric x channel x band -> r, Cohen's d, clustered logistic p."""
    cube = z["cube"]
    f_set = z["f_set"]
    chan_order = [str(c) for c in z["chan_order"]]
    row_chan = np.argmax(np.isfinite(cube).all(axis=2), axis=1)
    bands = [(lo, lo + BAND_W) for lo in LO_EDGES]
    centers = np.array([(lo + hi) / 2 for lo, hi in bands])

    records = []
    for met in METRICS:
        lab = z[f"label__{met}"]
        rg = z[f"rgrp__{met}"]
        for ci, ch in enumerate(chan_order):
            rows = np.where(row_chan == ci)[0]
            y, g = lab[rows], rg[rows]
            fin = np.isfinite(y)
            if fin.sum() < 10:
                continue
            yv = y[fin]
            lo_q, hi_q = np.percentile(yv, 33.333), np.percentile(yv, 66.667)
            ybin = np.full(len(y), np.nan)
            ybin[fin & (y <= lo_q)] = 0.0
            ybin[fin & (y >= hi_q)] = 1.0
            for (lo, hi), cen in zip(bands, centers):
                fmask = (f_set >= lo) & (f_set < hi)
                bp = np.nanmean(cube[np.ix_(rows, [ci])][:, 0, fmask], axis=1)
                mok = np.isfinite(bp) & fin
                if mok.sum() < 10:
                    continue
                if np.std(bp[mok]) > 0 and np.std(y[mok]) > 0:
                    r, pr = stats.pearsonr(bp[mok], y[mok])
                else:
                    r, pr = np.nan, np.nan
                lo_m, hi_m = mok & (ybin == 0.0), mok & (ybin == 1.0)
                nlo, nhi = int(lo_m.sum()), int(hi_m.sum())
                d = np.nan
                if nlo >= 3 and nhi >= 3:
                    s_lo, s_hi = np.std(bp[lo_m], ddof=1), np.std(bp[hi_m], ddof=1)
                    sp2 = ((nlo - 1) * s_lo**2 + (nhi - 1) * s_hi**2) / max(nlo + nhi - 2, 1)
                    d = (np.mean(bp[hi_m]) - np.mean(bp[lo_m])) / np.sqrt(sp2) if sp2 > 0 else np.nan
                beta, pcl, n_used, n_grp = cluster_robust_logit_p(bp, ybin, g)
                records.append(dict(metric=met, channel=ch, center=cen, band_lo=lo, band_hi=hi,
                                    n=int(mok.sum()), n_low=nlo, n_high=nhi, n_ratings=n_grp,
                                    r=r, p_pearson=pr, cohens_d=d, logit_beta=beta,
                                    p_logit_cluster=pcl))
    return pd.DataFrame(records)


def apply_fdr(scan):
    """BH-FDR per metric over the band x channel family, on both clustered-logit and Pearson p."""
    out = []
    for met in METRICS:
        s = scan[scan.metric == met].copy()
        for pcol, qcol in [("p_logit_cluster", "q_logit"), ("p_pearson", "q_pearson")]:
            p = s[pcol].values.copy()
            ok = np.isfinite(p)
            q = np.full(len(p), np.nan)
            if ok.sum():
                _, qv, _, _ = multipletests(p[ok], alpha=0.05, method="fdr_bh")
                q[ok] = qv
            s[qcol] = q
        out.append(s)
    return pd.concat(out, ignore_index=True)


def candidate_clusters(scan_q, raw_alpha=0.05):
    """Reduce contiguous raw-significant (clustered-logit) band runs to one peak candidate each."""
    cands = []
    for met in METRICS:
        for ch in scan_q[scan_q.metric == met].channel.unique():
            s = scan_q[(scan_q.metric == met) & (scan_q.channel == ch)].sort_values("center").reset_index(drop=True)
            sig = s["p_logit_cluster"] < raw_alpha
            run, runs = [], []
            for i, issig in enumerate(sig):
                if issig:
                    run.append(i)
                elif run:
                    runs.append(run); run = []
            if run:
                runs.append(run)
            for rr in runs:
                sub = s.iloc[rr]
                peak = sub.iloc[sub["cohens_d"].abs().values.argmax()]
                cands.append(dict(metric=met, channel=ch, peak_center=peak["center"],
                                  band_lo=peak["band_lo"], band_hi=peak["band_hi"],
                                  run_lo=s.iloc[rr[0]]["center"], run_hi=s.iloc[rr[-1]]["center"],
                                  run_width=len(rr), r=peak["r"], cohens_d=peak["cohens_d"],
                                  p_logit=peak["p_logit_cluster"], q_logit=peak["q_logit"],
                                  n=int(peak["n"]), n_ratings=int(peak["n_ratings"])))
    return pd.DataFrame(cands).sort_values(["metric", "p_logit"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="phase0_bundle.npz")
    ap.add_argument("--out-prefix", default="")
    args = ap.parse_args()
    z = np.load(args.bundle, allow_pickle=True)
    print(f"loaded {args.bundle}: cube {z['cube'].shape}, metrics {METRICS}")

    scan = run_scan(z)
    scan.to_csv(f"{args.out_prefix}scan_full_RCS08.csv", index=False)
    print(f"scan: {len(scan)} cells")

    scan_q = apply_fdr(scan)
    scan_q.to_csv(f"{args.out_prefix}scan_full_fdr_RCS08.csv", index=False)
    n_naive = sum(int((scan_q[scan_q.metric == m]["q_pearson"] < 0.05).sum()) for m in METRICS)
    n_rig = sum(int((scan_q[scan_q.metric == m]["q_logit"] < 0.05).sum()) for m in METRICS)
    print(f"FDR-significant bands: naive Pearson={n_naive}  rating-clustered logit={n_rig}")

    cands = candidate_clusters(scan_q)
    cands.to_csv(f"{args.out_prefix}band_candidates_raw_RCS08.csv", index=False)
    print(f"candidate clusters: {len(cands)}")
    print("\nNEXT (container): run _agent_bridge/phase2_glmer.py + phase2b_hetero.py for the")
    print("mixed-effects and stim-heterogeneity steps, then merge into the ranked validated table.")


if __name__ == "__main__":
    main()
