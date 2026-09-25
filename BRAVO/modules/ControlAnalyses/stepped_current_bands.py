"""Does settled band power change with current as much in bands with no plausible pain relationship
as in the pain-linked family? (finding M1 of
`artifacts/research_2026-09-25_options/08_critique_science.md`, item A5 of `11_REVISED_PLAN.md`,
2026-09-25.) Free of the database; the runner feeds it the stored titration-ladder points (kind
`three_source_run_points`, read as consumer `stim_optimizer` the way `carry_over.ladder_pairs`
already does).

WHAT THIS CHECKS. Decision 229 found that with the clinic sheets included, 11 to 22 of 22 bands
(8.5-29.5 Hz) fall with pain on the exploratory grid. The two reports behind the 2026-09-24 research
batch explain that only with rating psychology (placebo, recall bias, expectation, unblinding). A
cheaper, mechanistic alternative already sits in this project's own measurements: the bands
containing 55 Hz itself rise 18-fold with current (`METHODS_measurement_and_findings.md` section 5)
-- the stimulator "looks like" a huge signal to the recording chain. If actively STEPPING the
current also perturbs the recording broadly (an amplifier or gain-state change, not a brain signal),
it would move bands with no plausible relationship to pain too, and would need no patient psychology
at all.

**What an electrical explanation predicts, and what this shows.** If a broad electrical effect of
stepping the current is what moves the clinic-sheet grid, bands far from any plausible pain family
(below 12 Hz, above 32 Hz) should change with current about AS MUCH as the 21.5-27.5 Hz family the
grid actually flags -- a ratio near 1. If the family's movement is instead specific to those bands,
the far bands should change far less -- a ratio well under 1. This module fits, per recording route
and sensing pair, the change in settled band power per mA of the side being stepped (one intercept
per ladder run, the pooled titration model's own shape, decisions 126/198), relative to that band's
own settled power (a fraction per mA, never a log -- decisions 193-196, 202), with a 95% interval
resampling whole runs, and reports the ratio of the far bands' typical |change per mA| to the
family's.

Descriptive throughout: it never selects a band or a setting, and blocks nothing.
"""
import numpy as np
import pandas as pd

#: The pain-linked family decisions 229, 236 watch (21.5-27.5 Hz, the ladder's 1 Hz-apart, 5 Hz-wide
#: grid). "Far" bands (below 12 Hz, above 32 Hz) have no plausible relationship to pain on the same
#: grid -- the ranges named in the analysis specification.
FAMILY_LO_HZ, FAMILY_HI_HZ = 21.5, 27.5
FAR_BELOW_HZ, FAR_ABOVE_HZ = 12.0, 32.0

#: Fewer than this many distinct ladder runs: a slope is reported with no interval (too few units
#: to resample), matching this package's other resampled-interval helpers (e.g. `carry_over.
#: paired_summary`, which needs at least 2 units before it bootstraps at all).
MIN_RUNS_FOR_INTERVAL = 3


def usable_rows(rp):
    """The ladder points a slope can be fit to: a settled value that was not refused, from a move
    (`leg` is `rising` or `falling` -- an `unchanged` row has no current change to relate power to),
    and not a band the comparison itself flags as reading the stimulator rather than the brain."""
    if rp is None or len(rp) == 0:
        return pd.DataFrame()
    d = pd.DataFrame(rp).copy()
    pw = pd.to_numeric(d["settled_band_power_device_units"], errors="coerce")
    ok = (np.isfinite(pw) & (d["why_not_used"].fillna("") == "")
          & d["leg"].isin(["rising", "falling"])
          & ~d["band_is_measuring_the_stimulator"].fillna(False).astype(bool))
    d = d[ok].copy()
    d["settled_band_power_device_units"] = pw[ok]
    d["current_mA"] = pd.to_numeric(d["current_mA"], errors="coerce")
    d["band_centre_hz"] = pd.to_numeric(d["band_centre_hz"], errors="coerce")
    return d.reset_index(drop=True)


def family_of(centre_hz):
    """`"family"`, `"far"` or `None` (neither -- inside neither range, so left out of the ratio)."""
    c = float(centre_hz)
    if FAMILY_LO_HZ - 1e-9 <= c <= FAMILY_HI_HZ + 1e-9:
        return "family"
    if c < FAR_BELOW_HZ - 1e-9 or c > FAR_ABOVE_HZ + 1e-9:
        return "far"
    return None


def _fit_slope(current, power, run_labels):
    """Change in `power` per unit of `current`, one intercept per distinct label in `run_labels`
    (the pooled titration model's own shape, decisions 126, 198): `power = intercept[run] + slope *
    current`. `None` when the design has no spare row to estimate a slope from, or is singular."""
    current = np.asarray(current, dtype=float)
    power = np.asarray(power, dtype=float)
    labels, runs = np.unique(np.asarray(run_labels), return_inverse=True)
    n_runs = int(labels.size)
    if current.size < n_runs + 1:
        return None
    D = np.zeros((current.size, n_runs + 1))
    D[np.arange(current.size), runs] = 1.0
    D[:, -1] = current
    try:
        beta, _res, rank, _sv = np.linalg.lstsq(D, power, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if rank < D.shape[1]:
        return None
    return float(beta[-1])


def band_slope(current, power, run, *, n_boot=2000, seed=0):
    """One band's slope (change in settled power per mA of the stepped side) and a 95% interval
    resampling whole runs, expressed relative to the band's own mean settled power (a fraction per
    mA). `lo`/`hi` are `None` with fewer than `MIN_RUNS_FOR_INTERVAL` distinct runs or a slope that
    could not be fit."""
    current = np.asarray(current, dtype=float)
    power = np.asarray(power, dtype=float)
    run = np.asarray(run)
    baseline = float(np.mean(power)) if power.size else float("nan")
    slope = _fit_slope(current, power, run)
    rel = (slope / baseline) if (slope is not None and np.isfinite(baseline) and baseline != 0) else None
    out = dict(n=int(current.size), n_runs=int(np.unique(run).size), baseline=(baseline if np.isfinite(baseline) else None),
               slope_per_mA=slope, relative_slope_per_mA=rel, lo=None, hi=None)
    uu = np.unique(run)
    if rel is None or uu.size < MIN_RUNS_FOR_INTERVAL:
        return out
    rng = np.random.default_rng(seed)
    idx = {u: np.flatnonzero(run == u) for u in uu}
    bs = []
    for _ in range(int(n_boot)):
        picks = rng.choice(uu, uu.size, replace=True)
        rows = np.concatenate([idx[u] for u in picks])
        pseudo_run = np.concatenate([np.full(idx[u].size, k) for k, u in enumerate(picks)])
        s = _fit_slope(current[rows], power[rows], pseudo_run)
        if s is not None and baseline:
            bs.append(s / baseline)
    if len(bs) >= 100:
        out["lo"], out["hi"] = (float(v) for v in np.percentile(bs, [2.5, 97.5]))
    return out


def per_route_pair(d, *, n_boot=2000, seed=0):
    """`band_slope` for every band of every (route, sensing pair) in the usable rows `d`, tagged
    `family` / `far` / neither by `family_of`. Returns `(bands, ratios)`: one row per band, and one
    row per (route, pair) with the median |relative change per mA| of its family bands, its far
    bands, and their ratio (far over family -- near 1 is what a current-triggered electrical effect
    predicts, well under 1 is what a pain-specific family predicts)."""
    bands = []
    if d is None or len(d) == 0:
        return bands, []
    for (src, ch), g in d.groupby(["source", "sensing_contact"], sort=False):
        for c, gb in g.groupby("band_centre_hz", sort=False):
            grp = family_of(c)
            if grp is None:
                continue
            s = band_slope(gb["current_mA"], gb["settled_band_power_device_units"], gb["run"],
                           n_boot=n_boot, seed=seed)
            bands.append(dict(route=src, pair=ch, centre_hz=float(c), group=grp, **s))
    bdf = pd.DataFrame(bands)
    ratios = []
    if not bdf.empty:
        for (src, ch), g in bdf.groupby(["route", "pair"], sort=False):
            fam = g[g["group"] == "family"]["relative_slope_per_mA"].dropna()
            far = g[g["group"] == "far"]["relative_slope_per_mA"].dropna()
            fam_med = float(np.median(np.abs(fam))) if len(fam) else None
            far_med = float(np.median(np.abs(far))) if len(far) else None
            ratios.append(dict(route=src, pair=ch, n_family_bands=int(len(fam)), n_far_bands=int(len(far)),
                               family_median_abs_relative_slope=fam_med, far_median_abs_relative_slope=far_med,
                               far_over_family_ratio=(far_med / fam_med if fam_med else None)))
    return bands, ratios


def reading(ratios):
    """Plain-English lines, one per (route, sensing pair) with both groups of bands, plus a
    one-line statement of what an electrical explanation would predict."""
    out = []
    for r in ratios:
        if r["far_over_family_ratio"] is None:
            out.append(f"{r['route']}, {r['pair']}: not enough family or far bands with a fitted "
                       f"change per mA to read a ratio ({r['n_family_bands']} family, {r['n_far_bands']} far).")
            continue
        out.append(f"{r['route']}, {r['pair']}: the family (21.5-27.5 Hz, {r['n_family_bands']} bands) changes "
                   f"{100 * r['family_median_abs_relative_slope']:.1f}% per mA at the median band; the far bands "
                   f"(below 12 Hz or above 32 Hz, {r['n_far_bands']} bands) change "
                   f"{100 * r['far_median_abs_relative_slope']:.1f}%; ratio (far over family) "
                   f"{r['far_over_family_ratio']:.2f}.")
    finite = [r["far_over_family_ratio"] for r in ratios if r["far_over_family_ratio"] is not None]
    if finite:
        out.append("An electrical effect of stepping the current, moving the recording broadly rather than "
                   "a pain-specific signal, predicts a ratio near 1; a signal specific to the family predicts "
                   "a ratio well under 1. " + (
                       f"Every route and pair reads at or above 1 (median {np.median(finite):.2f})."
                       if min(finite) >= 0.8 else
                       f"Every route and pair reads well under 1 (median {np.median(finite):.2f})."
                       if max(finite) <= 0.5 else
                       f"The ratio varies by route and pair (median {np.median(finite):.2f}, "
                       f"{min(finite):.2f} to {max(finite):.2f})."))
    out.append("Descriptive: never selects a band. This does not decide between the two explanations by "
               "itself; it says whether the electrical one is at least as consistent with this record as "
               "the psychological one decision 229's own reports favoured.")
    return out
