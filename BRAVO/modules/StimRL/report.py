"""Collect every saved result into one ranked summary (markdown) and one figure.

    cd BRAVO/modules && ~/.venvs/bravo-stim-rl/bin/python -m StimRL.report --out <folder>

Ranking: the expected drop in home pain is `-near_minus_far_change`: how much more home pain fell
(0-10 points, from the previous period) in long-term periods near the model's recommendation than
in periods far from it, from the long-term record no model trained on. It is an association in
records where settings were not assigned at random, not a measured effect of the recommendation. The risk score is how close the recommendations sit
to the 4.5 mA ceiling (0 below 4.0 mA, 1 at the ceiling). Models whose recommendations ever pass a
limit are ranked after every model whose recommendations never do.
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
import pandas as pd

from .data_pipeline import DEFAULT_DATA_DIR

FAMILY = {"BC": "deep", "CQL": "deep", "IQL": "deep", "TD3+BC": "deep"}


def collect(results_dir: str) -> pd.DataFrame:
    rows = []
    for p in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        if os.path.basename(p) == "sanity_check.json":
            continue
        r = json.load(open(p))
        base = os.path.basename(p)
        if base.startswith("agentdb_") and "variant" not in r:
            for v in ("worst_site", "delta", "level"):
                if f"_{v}_" in base:
                    r["variant"] = v
                    r["model"] = "AgentDB pick: " + base[len("agentdb_"):base.index(f"_{v}_")].replace("_", " ")
                    break
        if "model" not in r or "variant" not in r:
            continue
        flat = {k: v for k, v in r.items() if not isinstance(v, (dict, list))}
        for k, v in (r.get("heldout") or {}).items():
            flat[f"heldout_{k}"] = v
        for sname, s in (r.get("sensitivity") or {}).items():
            for k in ("rho_dist_change", "near_minus_far_change", "n_periods"):
                flat[f"{sname}_{k}"] = s.get(k)
        flat["source"] = ("agentdb arm" if os.path.basename(p).startswith("agentdb")
                          else "d3rlpy (mps)" if os.path.basename(p).startswith("deep") else "small / reference")
        flat["file"] = os.path.basename(p)
        rows.append(flat)
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["model", "variant", "source"])
    out = pd.DataFrame({
        "seeds": g.size(),
        "expected_drop": -g["near_minus_far_change"].mean(),
        "expected_drop_sd": g["near_minus_far_change"].std(),
        "rho_dist_change": g["rho_dist_change"].mean(),
        "rho_dist_change_sd": g["rho_dist_change"].std(),
        "p_shift_median": g["p_dist_change_shift"].median(),
        "rho_adv": g["rho_adv"].mean(),
        "p_adv_shift_median": g["p_adv_shift"].median(),
        "rho_dist_level": g["rho_dist"].mean(),
        "no_visit_drop": -g["no_visit_periods_near_minus_far_change"].mean()
        if "no_visit_periods_near_minus_far_change" in df else np.nan,
        "washin24_drop": -g["washin_24h_near_minus_far_change"].mean()
        if "washin_24h_near_minus_far_change" in df else np.nan,
        "model_gain": g["model_gain_vs_history"].mean(),
        "risk": g["risk_mean"].mean(),
        "share_ge_4mA": g["share_at_or_above_4mA"].mean(),
        "share_past_limit": g["share_past_limit"].mean(),
    })
    for c in ("heldout_action_diff", "heldout_td_error", "heldout_initial_state_value"):
        if c in df.columns:
            out[c] = g[c].mean()
    out = out.reset_index()
    out["safe"] = out["share_past_limit"] == 0
    return out.sort_values(["safe", "expected_drop", "risk"], ascending=[False, False, True]).reset_index(drop=True)


def _fmt(x, nd=2):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def markdown(summary: pd.DataFrame, df: pd.DataFrame, recs: dict, sanity: dict | None) -> str:
    L = ["# Offline RL tournament: ranked by expected drop in home pain against risk", ""]
    if sanity:
        algos = [k for k in sanity if isinstance(sanity[k], dict)]
        moved = ", ".join(f"{k} {sanity[k]['params_moved']}/{sanity[k]['params_checked']}" for k in algos)
        L += [f"Apple GPU check: MPS available = {sanity.get('mps_available')}, device {sanity.get('device')}; "
              f"weights moved after 5 pilot updates: {moved}.", ""]
    L += ["Expected drop: how much more home pain fell from the previous period (0-10 points) in long-term "
          "periods near the recommendation than in periods far from it (thirds by distance); positive is good. "
          "An association in records where settings were not randomised. rho_change: rank correlation of "
          "distance with the change in pain (positive is good); p: one-sided, from rotating the series. "
          "rho_adv: rank correlation of the model's predicted gain from each switch with the observed drop. "
          "No-visit and 24 h columns: the expected drop on the periods with no visit inside (24) and with a "
          "24-hour wash-in (34). Risk: 0 below 4.0 mA, 1 at the 4.5 mA ceiling. Mean over seeds.", "",
          "| rank | model | reward | source | seeds | expected drop (sd) | rho_change | p | rho_adv | p (adv) | no-visit drop | 24 h drop | risk | past a limit |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in summary.iterrows():
        L.append(f"| {i + 1} | {r.model} | {r.variant} | {r.source} | {r.seeds} | {_fmt(r.expected_drop)} "
                 f"({_fmt(r.expected_drop_sd)}) | {_fmt(r.rho_dist_change)} | {_fmt(r.p_shift_median, 3)} | "
                 f"{_fmt(r.rho_adv)} | {_fmt(r.p_adv_shift_median, 3)} | {_fmt(r.no_visit_drop)} | "
                 f"{_fmt(r.washin24_drop)} | {_fmt(r.risk, 3)} | {_fmt(r.share_past_limit)} |")
    ho = [c for c in summary.columns if c.startswith("heldout_")]
    if ho:
        L += ["", "Held-out visits (5-fold by visit, d3rlpy evaluators, deep models only): action difference "
              "from the clinician's choice (mean squared, scaled units), TD error, and the value the model "
              "expects from the first state of a left-out visit (its own estimate, pain points).", "",
              "| model | reward | action diff | TD error | initial-state value |", "|---|---|---|---|---|"]
        for _, r in summary[summary[ho[0]].notna()].iterrows():
            L.append(f"| {r.model} | {r.variant} | {_fmt(r.get('heldout_action_diff'), 3)} | "
                     f"{_fmt(r.get('heldout_td_error'), 3)} | {_fmt(r.get('heldout_initial_state_value'), 2)} |")
    if recs:
        L += ["", "## Today's recommendation from the top models (seed 0), per Left contact", ""]
        for name, tab in recs.items():
            L += [f"**{name}**", "", "| Left contact | rate Hz | Left mA | Right mA | Left us | Right us | risk |",
                  "|---|---|---|---|---|---|---|"]
            for r in tab:
                L.append(f"| {r['left_contact']} | {r['freq_hz']:.0f} | {r['amp_mA_Left']:.2f} | {r['amp_mA_Right']:.2f} | "
                         f"{r['pw_us_Left']:.0f} | {r['pw_us_Right']:.0f} | {r['risk']:.2f} |")
            L.append("")
    return "\n".join(L)


def figure(summary: pd.DataFrame, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    markers = {"delta": "o", "level": "s", "worst_site": "^"}
    models = list(dict.fromkeys(summary["model"]))
    cmap = plt.get_cmap("tab20")
    for i, m in enumerate(models):
        s = summary[summary.model == m]
        for _, r in s.iterrows():
            ax.errorbar(r.risk, r.expected_drop, yerr=r.expected_drop_sd if np.isfinite(r.expected_drop_sd) else None,
                        fmt=markers.get(r.variant, "o"), color=cmap(i % 20), ms=7, capsize=2,
                        label=m if r.variant == s.variant.iloc[0] else None)
    ax.axhline(0, color="0.5", lw=0.8)
    ax.set_xlabel("risk of recommendations (0 below 4.0 mA, 1 at the 4.5 mA ceiling)")
    ax.set_ylabel("expected drop in home pain (points, 0-10)")
    ax.set_title("Expected drop in home pain against risk (circle: delta, square: level, triangle: worst site)",
                 fontsize=10)
    ax.legend(fontsize=7, ncol=2, frameon=False, loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(DEFAULT_DATA_DIR, "results"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=3)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    df = collect(a.results)
    summary = summarise(df)
    summary.to_csv(os.path.join(a.out, "tournament_summary.csv"), index=False)
    recs = {}
    for _, r in summary[summary.safe].head(a.top).iterrows():
        f = df[(df.model == r.model) & (df.variant == r.variant) & (df.seed == 0)]["file"]
        if len(f):
            rec = json.load(open(os.path.join(a.results, f.iloc[0]))).get("recommendation")
            if rec:
                recs[f"{r.model}, {r.variant} reward"] = rec
    sp = os.path.join(a.results, "sanity_check.json")
    sanity = json.load(open(sp)) if os.path.exists(sp) else None
    open(os.path.join(a.out, "tournament_summary.md"), "w").write(markdown(summary, df, recs, sanity))
    figure(summary, os.path.join(a.out, "expected_drop_vs_risk.png"))
    print(summary[["model", "variant", "seeds", "expected_drop", "rho_dist_change", "p_shift_median", "rho_adv",
                   "p_adv_shift_median", "no_visit_drop", "washin24_drop", "risk", "share_past_limit"]].round(3).to_string())


if __name__ == "__main__":
    main()
