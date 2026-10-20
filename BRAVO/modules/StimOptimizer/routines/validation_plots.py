"""Static validation diagnostics for the StimOptimizer warm start.

Kept separate from :mod:`plots`, which holds the interactive Plotly decision figures for the
clinical front end. These are matplotlib panels that belong next to the numbers in the Phase 4
report, and they are deliberately self-contained: styling is set from explicit rcParams inside
each function rather than inherited from a session, so a figure regenerated months later looks
the same.

Every figure takes an explicit ``data_horizon`` string and stamps it into the figure itself. A
calibration panel with no vintage on it is the easiest way to read a stale result as a current
one.
"""
from __future__ import annotations

import numpy as np

_BASE, _MID, _SMALL = 9, 8, 7
_GREY = "#5A5A5A"
_FOCAL = "#1F4E79"      # surrogate
_COMP = "#B0B0B0"       # precision-weighted-mean null
_ALARM = "#C4451C"      # uniform reference


def _style(mpl):
    mpl.rcParams.update({
        "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
        "font.size": _BASE, "axes.titlesize": _BASE, "axes.labelsize": _BASE,
        "legend.fontsize": _MID, "xtick.labelsize": _SMALL, "ytick.labelsize": _SMALL,
        "axes.titlelocation": "left", "axes.titleweight": "regular",
        "axes.spines.top": False, "axes.spines.right": False,
        "xtick.direction": "out", "ytick.direction": "out",
        "legend.frameon": False, "axes.grid": False,
    })


def plot_pit_calibration(per_fold, verdict, path: str, *, data_horizon: str) -> str:
    """Three-panel held-out calibration diagnostic.

    (a) PIT histogram, leave-one-epoch-out. (b) PIT histogram, leave-one-era-out. (c) held-out
    predicted vs observed epoch mean J under era blocking, with 95% predictive intervals, against
    the precision-weighted-mean null.

    A well-calibrated predictive distribution gives uniform PIT values. Over-wide intervals pile
    PIT up in the middle; over-narrow intervals pile it at the two ends. Panel (c) is where a
    surrogate with correct intervals but no skill shows itself: points hugging a horizontal band
    rather than the identity line means the model is predicting the same value everywhere.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _style(matplotlib)

    s = verdict["summary"]
    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.1))
    bins = np.linspace(0, 1, 7)

    for ax, key, letter, lab in ((axes[0], "loeo", "a", "leave-one-epoch-out"),
                                 (axes[1], "loera", "b", "leave-one-era-out")):
        g = per_fold[(per_fold.fold_structure == key) & per_fold.gp_pit.notna()]
        pit = g["gp_pit"].to_numpy(float)
        ax.hist(pit, bins=bins, color=_FOCAL, edgecolor="white", linewidth=0.6)
        ax.axhline(len(pit) / (len(bins) - 1), color=_ALARM, linestyle="--", linewidth=1.1,
                   zorder=3)
        ax.set_xlabel("probability integral transform")
        ax.set_ylabel("held-out epochs" if key == "loeo" else "")
        ax.set_xlim(0, 1)
        ax.set_title(f"{letter}   Intervals are honest: {lab}\n"
                     f"n={len(pit)}, KS p={s[key]['pit_ks_p']:.2f}, "
                     f"95% coverage={s[key]['coverage95_gp']:.2f}", fontsize=_MID)
        ax.margins(y=0.16)
    axes[0].text(0.03, 0.93, "uniform expectation", transform=axes[0].transAxes,
                 color=_ALARM, fontsize=_SMALL, va="top")

    ax = axes[2]
    g = per_fold[(per_fold.fold_structure == "loera") & per_fold.gp_mu.notna()]
    obs = g["J_observed"].to_numpy(float)
    mu = g["gp_mu"].to_numpy(float)
    sdt = g["gp_sd_total"].to_numpy(float)
    lo = min(obs.min(), (mu - 1.96 * sdt).min())
    hi = max(obs.max(), (mu + 1.96 * sdt).max())
    pad = 0.06 * (hi - lo)
    ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], color=_GREY, linewidth=0.9, zorder=1)
    ax.errorbar(obs, mu, yerr=1.96 * sdt, fmt="o", markersize=3.4, color=_FOCAL,
                ecolor=_FOCAL, elinewidth=0.8, capsize=0, alpha=0.85, zorder=3,
                label="surrogate (95% PI)")
    ax.plot(obs, g["base_mu"].to_numpy(float), "s", markersize=3.0, color=_COMP,
            markeredgecolor=_COMP, zorder=2, label="precision-weighted mean")
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlabel("observed epoch mean J (NRS points)")
    ax.set_ylabel("held-out prediction")
    ax.set_title("c   But nearly flat: era-blocked prediction\n"
                 f"MAE {s['loera']['mae_gp']:.3f} vs null {s['loera']['mae_baseline']:.3f}, "
                 f"ratio {s['loera']['mae_ratio']:.2f} (pass needs <=0.90)", fontsize=_MID)
    ax.legend(loc="upper left", handletextpad=0.4, borderpad=0.1)
    ax.text(0.98, 0.03, "lower J = better", transform=ax.transAxes, ha="right",
            fontsize=_SMALL, color=_GREY)

    verdict_txt = "FAIL — surrogate not permitted to select settings" if not verdict["passes"] \
        else "PASS"
    fig.text(0.005, -0.13,
             f"PROVISIONAL — {data_horizon}. J is minimised and referenced to the incumbent "
             f"chronic setting, so J = 0 is the status quo and negative is better. Every fold "
             f"refits the kernel on its training fold only (frequency length scale pinned, "
             f"amplitude free). Pre-declared criterion: MAE ratio <= "
             f"{verdict['criterion']['C1_loeo_mae_ratio_max']:.2f} against the null on BOTH fold "
             f"structures, 95% coverage in [{verdict['criterion']['C3_coverage_min']:.2f}, "
             f"{verdict['criterion']['C3_coverage_max']:.2f}], PIT KS p >= "
             f"{verdict['criterion']['C3_pit_ks_alpha']:.2f}. Outcome: {verdict_txt}.",
             fontsize=_SMALL, color=_GREY, wrap=True, va="top")
    fig.subplots_adjust(wspace=0.34)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
