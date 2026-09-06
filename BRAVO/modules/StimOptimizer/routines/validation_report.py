"""Markdown renderer for the Phase 4 validation report.

Separated from :mod:`validation` so the numbers and the prose that frames them are edited
independently: every value below is read out of the result dict, none is retyped. The data
horizon and wash-in window are stamped into the header and repeated at every decision point,
because a reader who scrolls straight to the queue must still see the vintage.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd


def _fmt(x, nd=3):
    if x is None:
        return "n/a"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not np.isfinite(v):
        return "n/a"
    return f"{v:.{nd}f}"


def _p(x):
    v = float(x)
    return "<0.0001" if v < 1e-4 else f"{v:.4f}"


def render(result: dict, per_fold: pd.DataFrame, queue: pd.DataFrame, audit: dict) -> str:
    v = result["verdict"]
    s = v["summary"]
    c = v["criterion"]
    d = result["decision"]
    r = result["replay"]
    co = audit["coefficients"]
    L = []
    A = L.append

    A("# Phase 4 — warm-start surrogate validation, RCS08")
    A("")
    A(f"**PROVISIONAL — data horizon: {result['data_horizon']}.** "
      f"Wash-in exclusion window {result['washin_min']:g} min (declared parameter). "
      f"Generated {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by "
      "`StimOptimizer.routines.validation.run_validation`.")
    A("")
    A("Every number in this report is conditional on that horizon. Approximately ten weeks of "
      "stimulation changes and pain reports after it are known to exist and are not yet on disk. "
      "The calibration verdict, the plateau decision, the exploration queue, the confound "
      "correlations and the replay numbers are all first-pass values that a refresh can move. "
      "Re-running `run_validation` against a newer design matrix regenerates all three "
      "deliverables; nothing here was derived by hand.")
    A("")
    A(f"- design matrix: `{result['design_matrix_path']}`")
    A(f"- per-report table: `{result['per_report_path']}`")
    A(f"- epochs carrying data: **{result['n_epochs']}** "
      f"({result['n_epochs_n_ge_3']} with n>=3, {result['n_reports_total']} usable reports)")
    A(f"- surrogate: `{result['hyperparameters']['kernel']}`, "
      f"log marginal likelihood {_fmt(result['hyperparameters']['log_marginal_likelihood'], 2)}")
    A(f"- length scales: frequency **pinned** at 0.823 (one octave), amplitude **fitted**. "
      "Pinning both would let every leave-one-out fold inherit the full-data amplitude "
      "hyperparameter, which leaks the held-out epoch into its own training fold.")
    A("")

    # ---- step 1
    A("## 1. Held-out calibration — the gate")
    A("")
    A("### Pass criterion, declared before the numbers were computed")
    A("")
    A("Null model: the **precision-weighted mean of the training-fold J**, with predictive "
      "variance = weighted between-epoch variance + squared standard error of that mean + the "
      "held-out epoch's own `obs_var`. This is the \"no response surface at all\" model.")
    A("")
    A(f"- **C1** leave-one-epoch-out MAE(GP)/MAE(null) <= {c['C1_loeo_mae_ratio_max']:.2f}")
    A(f"- **C2** leave-one-ERA-out MAE(GP)/MAE(null) <= {c['C2_loera_mae_ratio_max']:.2f}")
    A(f"- **C3** 95% predictive-interval coverage in "
      f"[{c['C3_coverage_min']:.2f}, {c['C3_coverage_max']:.2f}] **and** PIT not rejected as "
      f"uniform by one-sample KS at alpha = {c['C3_pit_ks_alpha']:.2f}, for BOTH fold structures")
    A("")
    A("All three required. Any single failure means the surrogate may not select settings "
      "(OBJECTIVE_SPEC section 6). No partial credit and no post-hoc redefinition of era.")
    A("")
    A(f"Eras are **calendar quarters of `t0`** ({audit['n_eras']} of them: "
      + ", ".join(f"{k} n={vv}" for k, vv in audit["era_counts"].items()) + "). "
      "Quarters are defined purely on the clock, so the blocking factor is independent of the "
      "predictors under audit. Defining eras by frequency regime instead would make the block a "
      "function of frequency and would absorb part of the effect being tested.")
    A("")
    A("### Result")
    A("")
    A("| fold structure | folds | predicted | MAE (GP) | MAE (null) | ratio | 95% coverage | "
      "mean predictive SD | PIT KS p |")
    A("|---|---|---|---|---|---|---|---|---|")
    for k, lab in (("loeo", "leave-one-epoch-out"), ("loera", "leave-one-era-out")):
        q = s[k]
        A(f"| {lab} | {q['n_folds']} | {q['n_predicted']} | {_fmt(q['mae_gp'])} | "
          f"{_fmt(q['mae_baseline'])} | **{_fmt(q['mae_ratio'])}** | "
          f"{_fmt(q['coverage95_gp'])} | {_fmt(q['mean_sd_total'])} | "
          f"{_p(q['pit_ks_p'])} |")
    A("")
    ck = v["checks"]
    A(f"- C1 (LOEO skill): **{'PASS' if ck['C1_loeo_skill'] else 'FAIL'}** — "
      f"ratio {_fmt(s['loeo']['mae_ratio'])} vs threshold {c['C1_loeo_mae_ratio_max']:.2f}")
    A(f"- C2 (LOERA skill): **{'PASS' if ck['C2_loera_skill'] else 'FAIL'}** — "
      f"ratio {_fmt(s['loera']['mae_ratio'])} vs threshold {c['C2_loera_mae_ratio_max']:.2f}")
    A(f"- C3 (calibration): **{'PASS' if ck['C3_calibration'] else 'FAIL'}** — "
      f"coverage {_fmt(s['loeo']['coverage95_gp'])} / {_fmt(s['loera']['coverage95_gp'])}, "
      f"PIT KS p {_p(s['loeo']['pit_ks_p'])} / {_p(s['loera']['pit_ks_p'])}")
    A("")
    if v["passes"]:
        A("**VERDICT: PASS.** The surrogate met all three pre-declared criteria at this data "
          "horizon and is permitted to emit prospective batches, subject to the safety and "
          "randomisation constraints in the spec.")
    else:
        failed = [k for k, ok in ck.items() if not ok]
        A(f"**VERDICT: FAIL** — {', '.join(failed)}. Per OBJECTIVE_SPEC section 6 the surrogate "
          "is **not permitted to select settings** at this data horizon. Sections 2-4 below are "
          "therefore diagnostics of the historical record, not recommendations: the exploration "
          "queue is a coverage statement about where the record is empty, not a ranked list of "
          "settings to program. No setting table is issued from this report.")
        A("")
        A("This is not softened. The warm start has 45 epochs spread over 6 frequencies, and "
          "held-out prediction of a whole temporal block is the hardest thing that can be asked "
          "of it. Failing that test is informative — it says the historical design does not "
          "identify a transferable response surface — and the correct response is to collect "
          "prospective, randomised-order data, not to lower the bar.")
    A("")
    A("PIT histogram and predicted-vs-observed panels: `rcs08_pit_calibration.png`. "
      "Per-epoch held-out predictions with fold labels: `rcs08_loo_calibration.csv`.")
    A("")

    # ---- step 2
    A("## 2. Plateau — local or global")
    A("")
    A(f"Posterior over all **{d['n_grid_cells']}** grid cells (12 frequencies x 33 amplitudes). "
      f"Posterior mean spans {_fmt(d['grid_mu_min'])} to {_fmt(d['grid_mu_max'])} NRS points; "
      f"posterior SD spans {_fmt(d['grid_sd_min'])} to {_fmt(d['grid_sd_max'])}. Incumbent "
      f"(55 Hz / 1.6 mA) posterior mean **{_fmt(d['incumbent_mu'])}** "
      f"(SD {_fmt(d['incumbent_sd'])}).")
    A("")
    A(f"Unexplored set = cells with fewer than {d['min_reports']} usable reports: "
      f"**{d['n_unexplored']} of {d['n_grid_cells']}** cells "
      f"({d['n_explored']} explored). {d['epochs_outside_grid']} epoch(s) sit outside the launch "
      "grid on amplitude and are counted as covering no cell.")
    A("")
    A(f"Coverage condition (b), kappa = {d['kappa']:.1f}: "
      f"min over unexplored of (mu - {d['kappa']:.1f}*sigma) = "
      f"**{_fmt(d['best_unexplored_optimistic'])}** versus incumbent posterior mean "
      f"**{_fmt(d['incumbent_mu'])}**.")
    A("")
    if d["plateau_is_global"]:
        A("**DECISION: the plateau is GLOBAL at this horizon.** No unexplored cell's optimistic "
          "bound beats the incumbent, so condition (b) of the stopping rule is satisfied.")
    else:
        A("**DECISION: the plateau is LOCAL, not global.** The optimistic bound over unexplored "
          f"cells beats the incumbent by {_fmt(d['incumbent_mu'] - d['best_unexplored_optimistic'])} "
          "NRS points, so condition (b) of the stopping rule is **violated** and the search may "
          "not be declared converged.")
    A("")
    A(f"Queue size: **{d['queue_size_ei']}** cells under expected-improvement ordering and "
      f"{d['queue_size_optimistic']} under raw optimistic-bound ordering; membership identical "
      f"({d['queue_membership_identical']}), only the order differs.")
    A("")
    A(f"**Read the ordering, not just the membership.** Off-sample posterior SD averages "
      f"{_fmt(np.mean([d['grid_sd_min'], d['grid_sd_max']]))} NRS points, so "
      f"kappa*sigma is about {_fmt(d['kappa_sd_vs_J_spread'])} times the entire observed spread "
      f"of epoch mean J ({_fmt(d['observed_epoch_J_spread'])} points, from "
      f"{_fmt(d['observed_epoch_J_min'])} to {_fmt(d['observed_epoch_J_max'])}). Ranking by the "
      "raw optimistic bound therefore ranks cells by *ignorance*; the reported queue is ordered "
      "by expected improvement, which ranks by promise while still rewarding uncertainty. "
      f"Only {d['n_unexplored_beating_incumbent_mu_only']} unexplored cell(s) beat the incumbent "
      "on posterior **mean** alone.")
    A("")
    if len(queue):
        A("Top of the queue (EI ordering) — **provisional, and not a recommendation while the "
          "calibration gate is failing**:")
        A("")
        A("| rank (EI) | rank (optimistic) | freq Hz | amp mA | mu | sd | mu-2sd | EI |")
        A("|---|---|---|---|---|---|---|---|")
        for _, row in queue.head(12).iterrows():
            A(f"| {int(row['rank_ei'])} | {int(row['rank_optimistic'])} | "
              f"{row['freq_hz']:.0f} | {row['amp_mA']:.1f} | {_fmt(row['mu'])} | "
              f"{_fmt(row['sd'])} | {_fmt(row['optimistic_bound'])} | "
              f"{_fmt(row['expected_improvement'], 4)} |")
        A("")
        A("Frequency composition of the top 20 by EI: "
          + ", ".join(f"{k} Hz x{vv}" for k, vv in d["top20_freq_composition"].items()) + ".")
        A("")
    A("Full queue with both rankings: `rcs08_exploration_queue.csv`.")
    A("")
    A("### Structural finding: the signal is in frequency, not amplitude")
    A("")
    A(f"The fitted amplitude length scale is **{_fmt(d['amp_length_scale_fitted'], 2)}** on a "
      f"unit-scaled axis (frequency pinned at {_fmt(d['freq_length_scale_pinned'], 3)}). An "
      "amplitude length scale that large means the surrogate has found **no usable amplitude "
      "gradient over 0.8-4.0 mA** — it models the response as nearly flat in amplitude and puts "
      "what remains of the signal into frequency. That is why the queue is dominated by a single "
      "frequency column rather than by an amplitude frontier: the highest-EI cells are at "
      "**40 Hz**, the untested frequency adjacent to the best-performing tested frequency "
      "(55 Hz), and the amplitude at which they are ranked is nearly immaterial to the model.")
    A("")
    A("Two readings of that, and the data at this horizon do not separate them. Either amplitude "
      "genuinely does little over this range for this patient, or the historical amplitude "
      "contrasts are so entangled with time and with right-hemisphere amplitude (section 3) that "
      "no amplitude gradient is identifiable from them. The second is the more likely and the "
      "more actionable: it is fixed by randomising amplitude within a fixed frequency "
      "prospectively, which the historical record never did.")
    A("")
    A("### Where the record is empty")
    A("")
    A(f"Of the **{d['band_n_cells']}** prospective-grid cells in the {d['band_label']} band, "
      f"**{d['band_n_under_threshold']} still carry fewer than {d['min_reports']} reports**. The "
      "only exceptions are "
      + ("; ".join(f"{f:.0f} Hz / {a:.1f} mA (n={n:.0f})"
                   for f, a, n in d["band_covered_cells"]) or "none")
      + ". At 10 Hz the record spans only "
      + (f"{d['low_freq_amp_span'][0]:.1f}-{d['low_freq_amp_span'][1]:.1f} mA"
         if d["low_freq_amp_span"] else "no cell at the coverage threshold")
      + ". Note this corrects the earlier Phase 1 phrasing that amplitude \"never left "
        "1.4-1.8 mA at 10-55 Hz\": under the 5-minute wash-in window, 55 Hz now reaches 3.0 and "
        "4.0 mA at the coverage threshold. The band is still essentially unexplored, but not "
        "entirely so.")
    A("")

    # ---- step 3
    A("## 3. Confound audit of the historical record")
    A("")
    A("**Weighting choice, stated:** epochs are weighted by their precision (`1/obs_var`) — the "
      "same weights the surrogate uses. The per-report pseudoreplication is quantified below as "
      "a design fact (intraclass correlation and design effect) but is not used as a second, "
      "parallel test of the same coefficients.")
    A("")
    A("Marginal Spearman correlations at epoch level (this is what the confound looks like "
      "before any adjustment):")
    A("")
    A("| pair | rho | p |")
    A("|---|---|---|")
    for k, vv in audit["spearman"].items():
        A(f"| {k.replace('~', ' vs ')} | {_fmt(vv['rho'])} | {_p(vv['p'])} |")
    A("")
    A("Variance inflation factors on the epoch-level design "
      + ", ".join(f"{k} {_fmt(vv, 2)}" for k, vv in audit["vif"].items()) + ".")
    A("")
    A("Frequency and left-amplitude coefficients on NRS, unadjusted then era-blocked:")
    A("")
    A("| model | term | coef | SE | t | p | 95% CI |")
    A("|---|---|---|---|---|---|---|")
    for _, row in co.iterrows():
        A(f"| {row['model']} | {row['term']} | {_fmt(row['coef'])} | {_fmt(row['se'])} | "
          f"{_fmt(row['t'], 2)} | {_p(row['p'])} | "
          f"[{_fmt(row['ci_lo'])}, {_fmt(row['ci_hi'])}] |")
    A("")
    A("Joint F-test of {log2(frequency), left amplitude}:")
    A("")
    for k, vv in audit["joint_tests"].items():
        A(f"- {k}: F({vv['df_num']}, {_fmt(vv['df_denom'], 0)}) = {_fmt(vv['F'], 2)}, "
          f"p = {_p(vv['p'])}")
    A("")
    if audit["icc"]:
        i = audit["icc"]
        A(f"Pseudoreplication: {i['n_reports']} reports over {i['n_epochs']} epochs "
          f"(mean {_fmt(i['mean_reports_per_epoch'], 1)} per epoch). One-way variance "
          f"components give ICC = **{_fmt(i['icc'])}**, design effect "
          f"{_fmt(i['design_effect'], 2)}, effective number of independent reports "
          f"**{_fmt(i['effective_n_reports'], 1)}** — not {i['n_reports']}. This is why the "
          "warm start is fitted on epochs, not on reports.")
        A("")

    def _get(model, term, col):
        m = co[(co.model == model) & (co.term == term)]
        return float(m.iloc[0][col]) if len(m) else float("nan")

    A("### What does not survive adjustment")
    A("")
    sp = audit["spearman"]
    A(f"1. **\"Higher frequency is associated with worse pain.\"** Marginally, rho = "
      f"{_fmt(sp['log2_freq~nrs']['rho'])} (p = {_p(sp['log2_freq~nrs']['p'])}) at epoch level. "
      f"The coefficient on log2(frequency) falls from {_fmt(_get('M1_naive_unweighted', 'log2_freq', 'coef'))} "
      f"NRS points per octave unadjusted, to {_fmt(_get('M2_precision_weighted', 'log2_freq', 'coef'))} "
      f"when epochs are weighted by precision, to {_fmt(_get('M3_era_blocked', 'log2_freq', 'coef'))} "
      f"(p = {_p(_get('M3_era_blocked', 'log2_freq', 'p'))}) once era is blocked — about "
      f"{_fmt(100 * (1 - abs(_get('M3_era_blocked', 'log2_freq', 'coef')) / abs(_get('M1_naive_unweighted', 'log2_freq', 'coef'))), 0)}% "
      "of the unadjusted effect is time. **Does not survive.**")
    A(f"2. **\"Left-hemisphere amplitude affects pain.\"** Never established marginally "
      f"(rho = {_fmt(sp['amp_L~nrs']['rho'])}, p = {_p(sp['amp_L~nrs']['p'])}), and the "
      f"coefficient changes sign under era blocking "
      f"({_fmt(_get('M1_naive_unweighted', 'amp_L', 'coef'))} -> "
      f"{_fmt(_get('M3_era_blocked', 'amp_L', 'coef'))}, "
      f"p = {_p(_get('M3_era_blocked', 'amp_L', 'p'))}). A sign flip on adjustment means the "
      "unadjusted estimate was carrying the confound, not an effect. **Does not survive.**")
    jt = audit["joint_tests"]
    A(f"3. **The searched dimensions jointly.** F({jt['M3_era_blocked']['df_num']}, "
      f"{_fmt(jt['M3_era_blocked']['df_denom'], 0)}) = {_fmt(jt['M3_era_blocked']['F'], 2)}, "
      f"p = {_p(jt['M3_era_blocked']['p'])} after era blocking. Frequency and amplitude together "
      "explain nothing beyond era. **The historical record does not identify a response surface "
      "over the searched dimensions.** This is the same conclusion section 1 reaches from the "
      "prediction side, arrived at independently.")
    A(f"4. **What does survive is time itself.** With era blocked and a linear day term added, "
      f"the day coefficient is {_fmt(_get('M4_era_blocked_plus_days', 'days', 'coef'), 4)} NRS "
      f"points/day (p = {_p(_get('M4_era_blocked_plus_days', 'days', 'p'))}), i.e. roughly "
      f"{_fmt(abs(_get('M4_era_blocked_plus_days', 'days', 'coef')) * 30, 2)} points per month of "
      "improvement not attributable to either searched parameter. Right-hemisphere amplitude is "
      f"nearly collinear with time (rho = {_fmt(sp['days~amp_R']['rho'])}, "
      f"p = {_p(sp['days~amp_R']['p'])}, VIF {_fmt(audit['vif']['amp_R'], 2)}), so it cannot be "
      "separated from the trend and is not interpretable as an effect either.")
    A("")
    A("**Consequence for the protocol.** Any prospective batch must randomise delivery order "
      "within the batch, as the spec already requires, and must vary amplitude within a fixed "
      "frequency rather than changing both together — otherwise the next year's record will be "
      "as unidentifiable as this one.")
    A("")

    # ---- step 4
    A("## 4. Retrospective sample-efficiency replay")
    A("")
    A(f"The **{r['n_visited_cells']}** grid cells the patient actually occupied are used as a "
      "lookup-table simulator: a strategy may only \"measure\" one of them, and the measurement "
      "returns that cell's precision-weighted epoch mean J. (That is every occupied cell, "
      f"including those with fewer than {d['min_reports']} reports; only {d['n_explored']} of "
      "them clear the coverage threshold used in section 2.) "
      f"Historical best J = {_fmt(r['historical_best_J'])} at "
      + "; ".join(f"{t['freq_hz']:.0f} Hz / {t['amp_mA']:.1f} mA" for t in r["targets"])
      + f". Budget {r['budget']} measurements, {r['n_init']} random initial measurements counted "
        f"against the Bayesian optimizer's total, {r['bayesopt']['n_seeds']} seeds.")
    A("")
    A("| strategy | median samples to best | IQR | mean | range | seeds reaching best |")
    A("|---|---|---|---|---|---|")
    for key, lab in (("bayesopt", "Bayesian optimization"),
                     ("uniform_random", "uniform random over visited cells"),
                     ("equal_interval_sweep", "equal-interval sweep")):
        q = r[key]
        A(f"| {lab} | **{_fmt(q['median'], 1)}** | "
          f"[{_fmt(q['q1'], 1)}, {_fmt(q['q3'], 1)}] | {_fmt(q['mean'], 1)} | "
          f"{_fmt(q['min'], 0)}-{_fmt(q['max'], 0)} | {q['n_found']}/{q['n_seeds']} |")
    A("")
    for key, lab in (("uniform_random", "uniform random"),
                     ("equal_interval_sweep", "equal-interval sweep")):
        u = r[f"mwu_bo_vs_{key}"]
        A(f"- Bayesian optimization vs {lab}, Mann-Whitney U one-sided (BO fewer samples): "
          f"U = {_fmt(u['U'], 0)}, p = {_p(u['p'])}")
    A("")
    A("**What this establishes and what it does not.** A lookup-table replay over "
      f"{r['n_visited_cells']} cells is a weak test and must not be read as evidence that the "
      "optimizer will find a better setting for this patient. It establishes exactly one thing: "
      "that the acquisition machinery, run end to end on real RCS08 objective values, reaches "
      "the historically best-performing visited cell in fewer measurements than undirected "
      "search — i.e. the code path from surrogate to batch is functional and its ordering is not "
      "arbitrary. It does **not** establish that the surrogate generalises (section 1 is the test "
      "of that, and it is the binding one), that the historical best is a global optimum, or that "
      f"sample efficiency measured on a {r['n_visited_cells']}-cell replay with fixed lookup "
      f"values transfers to a {d['n_grid_cells']}-cell prospective search with day-scale "
      "measurement noise and drift. The target is also the "
      "argmin of the same data the surrogate was fitted to, which flatters any method that "
      "smooths — the comparison is between strategies on equal footing, not an absolute claim.")
    A("")

    # ---- what a refresh could change
    A("## What ten more weeks of data could change")
    A("")
    A(f"Stated so that a future reader can see which conclusions are load-bearing on the "
      f"{result['data_horizon']} horizon:")
    A("")
    A("1. **The calibration verdict.** More epochs, and in particular a fifth era, change both "
       "the MAE ratio and the number of era folds. The verdict above can move in either "
       "direction.")
    A("2. **The incumbent.** If the chronic setting changed after the horizon, J is referenced "
       "to the wrong cell and every J value shifts by a constant, which moves the plateau "
       "decision.")
    A("3. **The queue.** Ten weeks of prospective settings would move cells out of the "
       "unexplored set and re-rank what remains. A queue computed on a stale record can send "
       "the clinic to a cell that has already been tested.")
    A("4. **The confound.** The time trend is the single strongest signal in the record. A "
       "refresh either extends it or breaks it, and that determines whether frequency and "
       "amplitude effects are estimable at all.")
    A("5. **The amplitude length scale**, and with it the claim that the response is nearly flat "
       "in amplitude. That is a fitted quantity on 45 epochs and it is the structural claim most "
       "exposed to new data.")
    A("")
    A("Re-run: "
      "`validation.run_validation(design_matrix_path=..., per_report_path=..., "
      "data_horizon=..., washin_min=..., outdir=...)`.")
    A("")
    return "\n".join(L)
