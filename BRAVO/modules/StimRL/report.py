"""Collect every saved result into one ranked summary (markdown) and one figure.

    cd BRAVO/modules && ~/.venvs/bravo-stim-rl/bin/python -m StimRL.report --out <folder>

Ranking: the expected drop in home pain is `-near_minus_far` (mean home pain, 0-10 points, in the
third of long-term periods farthest from the model's recommendation minus the third closest),
taken from the long-term record no model saw. The risk score is how close the recommendations sit
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
        if "model" not in r or "variant" not in r:
            continue
        flat = {k: v for k, v in r.items() if not isinstance(v, (dict, list))}
        for k, v in (r.get("heldout") or {}).items():
            flat[f"heldout_{k}"] = v
        flat["source"] = ("agentdb arm" if os.path.basename(p).startswith("agentdb")
                          else "d3rlpy (mps)" if os.path.basename(p).startswith("deep") else "small / reference")
        flat["file"] = os.path.basename(p)
        rows.append(flat)
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["model", "variant", "source"])
    out = pd.DataFrame({
        "seeds": g.size(),
        "expected_drop": -g["near_minus_far"].mean(),
        "expected_drop_sd": g["near_minus_far"].std(),
        "rho_dist": g["rho_dist"].mean(),
        "rho_dist_sd": g["rho_dist"].std(),
        "p_shift_median": g["p_dist_shift"].median(),
        "rho_q": g["rho_q"].mean(),
        "p_q_shift_median": g["p_q_shift"].median(),
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
    L += ["Expected drop: mean home pain (0-10 points) in the third of long-term setting periods farthest "
          "from the model's recommendation minus the third closest; positive means periods near the "
          "recommendation hurt less. rho_dist: rank correlation of that distance with pain (positive is good); "
          "p: one-sided, from rotating the pain series (keeps neighbouring periods' similarity). rho_q: rank "
          "correlation of the model's own value of each period's setting with minus its pain. Risk: 0 below "
          "4.0 mA, 1 at the 4.5 mA ceiling. Mean over seeds.", "",
          "| rank | model | reward | source | seeds | expected drop (sd) | rho_dist | p | rho_q | p (q) | risk | at/above 4 mA | past a limit |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in summary.iterrows():
        L.append(f"| {i + 1} | {r.model} | {r.variant} | {r.source} | {r.seeds} | {_fmt(r.expected_drop)} "
                 f"({_fmt(r.expected_drop_sd)}) | {_fmt(r.rho_dist)} | {_fmt(r.p_shift_median, 3)} | "
                 f"{_fmt(r.rho_q)} | {_fmt(r.p_q_shift_median, 3)} | {_fmt(r.risk, 3)} | "
                 f"{_fmt(r.share_ge_4mA)} | {_fmt(r.share_past_limit)} |")
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
    print(summary[["model", "variant", "seeds", "expected_drop", "rho_dist", "p_shift_median", "rho_q",
                   "risk", "share_past_limit"]].round(3).to_string())


if __name__ == "__main__":
    main()
