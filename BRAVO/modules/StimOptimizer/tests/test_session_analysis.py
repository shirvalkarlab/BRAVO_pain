"""Tests for the post-session analysis of a filled-in clinic schedule sheet.

Every test here works on synthetic sheets whose ground truth is known by construction, because the
only way to show that an estimator recovers an effect is to put a known effect in and check that
the number that comes out is the number that went in. Each test's docstring says what would be
wrong with the analysis if that test failed, since a failing assertion on its own does not tell a
future reader which scientific mistake it was placed there to catch.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import schedule as SCHED
from StimOptimizer.routines import session_analysis as SA

SETTINGS = list("ABCDEFG")
CANDIDATES = pd.DataFrame({
    "id": SETTINGS,
    "freq": [55.0, 55.0, 55.0, 55.0, 55.0, 165.0, 165.0],
    "ampL": [3.5, 4.5, 2.0, 3.5, 3.9, 2.4, 4.5],
    "ampR": [3.0, 3.0, 3.0, 1.9, 3.0, 3.0, 3.0],
})


# ---------------------------------------------------------------------------------------------
# Helpers for building a synthetic FILLED sheet with known ground truth
# ---------------------------------------------------------------------------------------------

def _clock(seconds, *, with_seconds=False):
    """Render a number of seconds since midnight the way a clinician would write it down."""
    h, rem = divmod(int(round(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if with_seconds else f"{h:02d}:{m:02d}"


def blank_sheet(*, n_blocks=3, seed=11):
    """A blank clinic sheet with exactly the schema the real one has, from the real generator."""
    sched, _ = SCHED.randomized_block_schedule(CANDIDATES, seed=seed, n_blocks=n_blocks,
                                               washin_s=60.0, min_per_step=3.5)
    return sched


def fill_sheet(sched, *, effects=None, drift_per_block=0.0, base=6.0, noise_sd=0.0,
               washin_s=75.0, seed=0, sites=SA.DEFAULT_SITES, with_seconds=True,
               side_effects=None, start_hour=14):
    """Fill a blank sheet with ratings generated from a KNOWN model, so truth is available.

    The generating model is deliberately simple and fully specified: every rating is the base
    level, plus the true effect of the setting tested at that step, plus a drift term that is
    ``drift_per_block`` multiplied by how many blocks have elapsed, plus Gaussian noise. Ratings
    are left as continuous numbers rather than rounded to whole points, because rounding would add
    a second source of error and make it impossible to say whether a recovered coefficient missed
    its target because the estimator is wrong or because the rounding moved it.
    """
    rng = np.random.default_rng(seed)
    effects = effects or {}
    df = sched.copy()
    prog, rated, values = [], [], []
    t0 = start_hour * 3600
    for r in df.itertuples():
        p = t0 + float(r.t_plan_min) * 60.0
        w = washin_s(r) if callable(washin_s) else float(washin_s)
        prog.append(_clock(p, with_seconds=with_seconds))
        rated.append(_clock(p + w, with_seconds=with_seconds))
        values.append(base + effects.get(r.setting, 0.0)
                      + drift_per_block * (int(r.block) - 1)
                      + rng.normal(0.0, noise_sd))
    df["actual_time_programmed"] = prog
    df["actual_time_rated"] = rated
    values = np.asarray(values, dtype=float)
    for site in sites:
        df[f"{SA.NRS_PREFIX}{site}"] = values
    df["side_effect_none_mild_mod_severe"] = 0 if side_effects is None else side_effects
    df["notes"] = ""
    return df


# ---------------------------------------------------------------------------------------------
# 1. Reading the clock times a clinician actually wrote
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("14:03", 14 * 3600 + 3 * 60),
    (" 14:03 ", 14 * 3600 + 3 * 60),
    ("14:03:22", 14 * 3600 + 3 * 60 + 22),
    ("2:03 pm", 14 * 3600 + 3 * 60),
    ("2:03PM", 14 * 3600 + 3 * 60),
    ("2:03 p.m.", 14 * 3600 + 3 * 60),
    ("2:03:15 PM", 14 * 3600 + 3 * 60 + 15),
    ("1403", 14 * 3600 + 3 * 60),
    ("903", 9 * 3600 + 3 * 60),
    ("140322", 14 * 3600 + 3 * 60 + 22),
    ("14.03", 14 * 3600 + 3 * 60),
    ("14h03", 14 * 3600 + 3 * 60),
    ("12:30 am", 30 * 60),
    ("12:30 pm", 12 * 3600 + 30 * 60),
])
def test_clock_times_are_read_in_every_format_a_clinician_writes(text, expected):
    """A wash-in can only be re-derived if the times can be read. If this fails, real steps get
    silently reclassified as 'not assessed' purely because of how the clinician wrote the time,
    and the exclusion count in the report becomes meaningless."""
    seconds, _ = SA.parse_clock_time(text)
    assert seconds == pytest.approx(float(expected))


@pytest.mark.parametrize("junk", ["", "   ", "n/a", "N/A", "xyz", "25:00", "14:60", "13:00 pm",
                                  "-", "??", "later", "2026-09-03", None, np.nan, 12.7])
def test_unreadable_times_return_nothing_rather_than_a_guess(junk):
    """The dangerous failure mode is not refusing to parse, it is parsing something wrong and
    producing a wash-in that looks measured. A guessed time is indistinguishable in the output
    from a real one, so anything that cannot be read confidently must come back as nothing."""
    assert SA.parse_clock_time(junk) == (None, None)


def test_the_resolution_a_time_was_written_to_is_reported():
    """A wash-in derived from two times written to the nearest minute is only known to the
    nearest minute, which is the same size as the sixty-second threshold being checked. If the
    resolution is not carried through, the report cannot warn that the compliant/short split is
    approximate and a reader will over-trust it."""
    assert SA.parse_clock_time("14:03")[1] == 60.0
    assert SA.parse_clock_time("14:03:22")[1] == 1.0
    assert SA.parse_clock_time("1403")[1] == 60.0
    assert SA.parse_clock_time("140322")[1] == 1.0


def test_minute_only_sheets_are_flagged_as_approximate():
    """The whole-visit consequence of the previous test."""
    minute = SA.derive_washin(fill_sheet(blank_sheet(), with_seconds=False))
    second = SA.derive_washin(fill_sheet(blank_sheet(), with_seconds=True))
    assert minute.minute_resolution_only is True
    assert second.minute_resolution_only is False
    assert "approximate" in minute.describe()


# ---------------------------------------------------------------------------------------------
# 2. The wash-in check: exclusions are counted, never silent
# ---------------------------------------------------------------------------------------------

def test_the_realised_washin_is_re_derived_and_not_taken_from_the_protocol():
    """The sheet says the wash-in was planned as sixty seconds. If the analysis reported the
    planned value it would report sixty here, and the entire point of asking the clinician for
    two clock times would be lost."""
    sheet = fill_sheet(blank_sheet(), washin_s=95.0)
    rep = SA.derive_washin(sheet)
    assert (sheet.washin_s == 60.0).all(), "the planned wash-in on the sheet is still 60 s"
    assert rep.realised_s["median"] == pytest.approx(95.0)
    assert rep.n_compliant == len(sheet)


def test_steps_rated_too_soon_are_excluded_and_the_count_is_reported():
    """A step rated before the drug-free equivalent of the wash-in has elapsed is measuring the
    previous setting as much as the current one. Dropping such steps is correct; dropping them
    without saying how many were dropped is not, because a reader cannot tell a clean session
    from one where a third of the steps were rushed."""
    sched = blank_sheet()
    short_steps = {3, 7, 12}
    sheet = fill_sheet(sched, washin_s=lambda r: 20.0 if r.step in short_steps else 80.0)
    res = SA.analyze_session(sheet)

    assert res.washin.n_short == len(short_steps)
    assert res.n_excluded_short_washin == len(short_steps)
    assert res.washin.n_compliant == len(sched) - len(short_steps)
    # The excluded steps really are gone from the modelled data, not merely counted.
    assert set(res.long.step) == set(sched.step) - short_steps
    # And the count reaches the human-readable report rather than living only in an attribute.
    assert f"{len(short_steps)} steps were rated too soon" in res.washin.describe()


def test_a_step_at_exactly_the_threshold_counts_as_compliant():
    """The protocol says to wait sixty seconds. Sixty seconds is a wait of sixty seconds."""
    rep = SA.derive_washin(fill_sheet(blank_sheet(), washin_s=60.0))
    assert rep.n_compliant == 21 and rep.n_short == 0


def test_missing_times_are_not_assessed_rather_than_assumed_compliant():
    """This is the distinction the module exists to preserve. A clinician who did not write a
    time has not demonstrated a protocol violation, and has not demonstrated compliance either.
    Collapsing 'unknown' into 'compliant' would quietly pass unverified steps into a biomarker
    validation as though they had been checked."""
    sheet = fill_sheet(blank_sheet())
    sheet.loc[[1, 5], "actual_time_rated"] = ""
    sheet.loc[[9], "actual_time_programmed"] = "oops"
    rep = SA.derive_washin(sheet)

    assert rep.n_not_assessed == 3
    assert rep.n_compliant == len(sheet) - 3
    statuses = rep.per_step.washin_status.tolist()
    for i in (1, 5, 9):
        assert statuses[i] == SA.WASHIN_NOT_ASSESSED
    assert "not assessed rather than assumed compliant" in rep.describe()


def test_unverified_steps_can_be_held_out_and_the_choice_is_visible():
    """Whether to analyse steps whose wash-in could not be checked is a judgement, not a fact, so
    it is a parameter with both settings working and the count reported either way."""
    sheet = fill_sheet(blank_sheet())
    sheet.loc[[2, 8], "actual_time_rated"] = ""
    kept = SA.analyze_session(sheet, unverified_policy="include")
    dropped = SA.analyze_session(sheet, unverified_policy="exclude")
    assert kept.n_unverified_washin == dropped.n_unverified_washin == 2
    assert set(kept.long.step) - set(dropped.long.step) == {3, 9}
    assert "kept in" in kept.report_text() and "held out of" in dropped.report_text()


def test_a_rating_time_before_the_programming_time_is_a_data_error_not_a_short_washin():
    """Negative elapsed time cannot be a rushed wash-in; it is a transcription error. Folding it
    into the short-wash-in count would inflate an apparent protocol-compliance problem with what
    is really a paperwork problem, and the two need different fixes."""
    sheet = fill_sheet(blank_sheet())
    sheet.loc[4, "actual_time_programmed"] = "23:59:00"
    rep = SA.derive_washin(sheet)
    assert rep.n_negative == 1 and rep.n_short == 0
    assert rep.per_step.washin_status.iloc[4] == SA.WASHIN_NEGATIVE
    # Negative-time steps are excluded from the modelled data just as short ones are.
    res = SA.analyze_session(sheet)
    assert 5 not in set(res.long.step) and res.n_excluded_negative_time == 1


# ---------------------------------------------------------------------------------------------
# 3. Recovering a known setting effect
# ---------------------------------------------------------------------------------------------

def test_a_known_setting_effect_is_recovered_with_the_right_sign_and_size():
    """The basic estimator check. A model that cannot return an effect that was put into the data
    by construction cannot be trusted with an effect that was not."""
    truth = {"B": -1.5, "G": +0.8}
    sheet = fill_sheet(blank_sheet(), effects=truth, noise_sd=0.15, seed=3)
    res = SA.analyze_session(sheet)
    tab = res.effects[SA.PRIMARY_SITE].table.set_index("setting")

    assert tab.loc["B", "coef"] == pytest.approx(-1.5, abs=0.35)
    assert tab.loc["G", "coef"] == pytest.approx(+0.8, abs=0.35)
    for quiet in ("C", "D", "E", "F"):
        assert abs(tab.loc[quiet, "coef"]) < 0.35, f"{quiet} should have no effect"


def test_every_reported_coefficient_is_a_difference_from_the_incumbent():
    """The estimand is the difference from the incumbent, not each setting's own mean level. If
    the model returned raw means the numbers would look plausible and be answering a different
    question, and no downstream check would notice."""
    sheet = fill_sheet(blank_sheet(), base=7.0, effects={"B": -2.0}, noise_sd=0.0)
    eff = SA.fit_setting_effects(SA.to_long(SA.derive_washin(sheet).per_step),
                                 site=SA.PRIMARY_SITE, anchor="A", with_block=True)
    tab = eff.table.set_index("setting")
    assert "A" not in tab.index, "the reference level must not appear as its own contrast"
    assert tab.loc["B", "coef"] == pytest.approx(-2.0, abs=1e-6)
    # The base level of 7 lives in the intercept, not in the contrasts.
    assert eff.table.attrs["anchor_mean"] == pytest.approx(7.0, abs=1e-6)


def test_standard_errors_are_clustered_on_the_step():
    """Ratings taken at the same step share whatever was happening to the patient at that moment.
    Treating four body-site ratings from one step as four independent observations would shrink
    every standard error by about half and turn noise into findings."""
    sheet = fill_sheet(blank_sheet(), effects={"B": -1.0}, noise_sd=0.5, seed=5)
    long = SA.to_long(SA.derive_washin(sheet).per_step)
    # Pool all four sites into one model so that each step genuinely contributes four ratings.
    pooled = long.copy()
    pooled["site"] = "pooled"
    clustered = SA.fit_setting_effects(pooled, site="pooled", anchor="A", cluster_col="step")
    naive = SA.fit_setting_effects(pooled.assign(step=np.arange(len(pooled))),
                                   site="pooled", anchor="A", cluster_col="step")
    se_c = clustered.table.set_index("setting").loc["B", "se"]
    se_n = naive.table.set_index("setting").loc["B", "se"]
    assert clustered.n_clusters == 21 and naive.n_clusters == len(pooled)
    assert se_c > se_n, ("clustering on the step must widen the standard error relative to "
                         "pretending every rating is its own independent observation")


# ---------------------------------------------------------------------------------------------
# 4. The block factor and the within-visit drift
# ---------------------------------------------------------------------------------------------

def _imbalanced_sheet(drift_per_block=-1.0, noise_sd=0.05, seed=17):
    """A session whose design has been broken: B sits late in the visit and C sits early.

    This is what a complete block design looks like AFTER steps have been dropped, which is the
    realistic case, and it is the only case in which the block adjustment changes the point
    estimates. In an intact complete block design drift is orthogonal to setting by construction,
    so the adjustment buys precision rather than a shift, and a test built on an intact design
    could not demonstrate that the adjustment does anything at all.
    """
    rng = np.random.default_rng(seed)
    rows = []
    layout = ([(1, "A"), (1, "A"), (1, "C"), (1, "C"), (1, "C")]
              + [(2, "A"), (2, "A"), (2, "B"), (2, "C")]
              + [(3, "A"), (3, "A"), (3, "B"), (3, "B"), (3, "B")])
    t = 14 * 3600
    for k, (block, setting) in enumerate(layout, start=1):
        y = 6.0 + drift_per_block * (block - 1) + rng.normal(0, noise_sd)
        rows.append({"step": k, "block": block, "setting": setting,
                     "actual_time_programmed": _clock(t + 210 * k, with_seconds=True),
                     "actual_time_rated": _clock(t + 210 * k + 80, with_seconds=True),
                     "nrs_left_leg": y, "nrs_left_foot": y, "nrs_back": y, "nrs_overall": y,
                     "side_effect_none_mild_mod_severe": 0, "notes": "",
                     "ampL": 3.5, "ampR": 3.0, "freq": 55.0})
    return pd.DataFrame(rows)


def test_within_visit_drift_is_removed_by_the_block_factor():
    """The true setting effect here is exactly zero for every setting; the only thing in the data
    besides noise is a one-point-per-block decline. With the block factor in the model the
    estimated setting effects must come back at zero. If they do not, a visit's worth of drift is
    being reported as a therapeutic effect, which is the single failure mode this project's
    schedule design exists to prevent."""
    res = SA.analyze_session(_imbalanced_sheet())
    tab = res.effects[SA.PRIMARY_SITE].table.set_index("setting")
    for s in ("B", "C"):
        assert abs(tab.loc[s, "coef"]) < 0.12, (s, tab.loc[s, "coef"])
    # And the drift itself is estimated, so a reader can see how big it was.
    be = res.effects[SA.PRIMARY_SITE].block_effects.set_index("block")
    assert be.loc["2", "coef"] == pytest.approx(-1.0, abs=0.12)
    assert be.loc["3", "coef"] == pytest.approx(-2.0, abs=0.12)


def test_the_same_drift_is_NOT_removed_when_the_block_factor_is_dropped():
    """The other half of the previous test, and the reason both models are reported side by side.
    Without the block term the same zero-effect data make B look better than the incumbent and C
    look worse, purely because of when in the visit they were tested. A reader who sees only the
    adjusted numbers has to take on trust that the adjustment mattered; seeing both makes the size
    of the confound visible."""
    res = SA.analyze_session(_imbalanced_sheet())
    unadj = res.effects_no_block[SA.PRIMARY_SITE].table.set_index("setting")
    assert unadj.loc["B", "coef"] < -0.4, "unadjusted, late-tested B should look spuriously better"
    assert unadj.loc["C", "coef"] > +0.4, "unadjusted, early-tested C should look spuriously worse"

    comp = res.drift_comparison()
    assert len(comp) == 2
    assert comp.shift_from_block_adjustment.abs().max() > 0.4
    assert "largest change in any setting's estimated difference" in res.report_text()


def test_block_adjustment_buys_precision_even_when_the_design_is_intact():
    """In a complete block design the adjustment should not move the point estimates much, because
    the design has already made drift orthogonal to setting. What it should do is soak up the
    drift's contribution to the residual and narrow the intervals. Both halves are checked, since
    a large shift here would mean the schedule generator had produced an unbalanced design."""
    sheet = fill_sheet(blank_sheet(), drift_per_block=-0.8, noise_sd=0.25, seed=9)
    res = SA.analyze_session(sheet)
    comp = res.drift_comparison()
    assert comp.shift_from_block_adjustment.abs().max() < 1e-8, (
        "a complete block design makes drift orthogonal to setting, so the point estimates must "
        "not move at all")
    assert (comp.se_block_adjusted < comp.se_unadjusted).all()


def test_a_single_block_session_drops_the_block_term_instead_of_failing():
    """A session that runs short may deliver only one block. One block is still analysable; a
    block factor with one level is not estimable. The model must drop the term and say that it
    did, rather than crash or pretend it adjusted for a drift it could not see."""
    rng = np.random.default_rng(4)
    rows = []
    for k, setting in enumerate(["A", "B", "C"] * 4, start=1):
        rows.append({"step": k, "block": 1, "setting": setting, "site": "left_leg",
                     "nrs": 6.0 + (-1.0 if setting == "B" else 0.0) + rng.normal(0, 0.2)})
    eff = SA.fit_setting_effects(pd.DataFrame(rows), site="left_leg", anchor="A", with_block=True)
    assert eff.fitted is True and eff.with_block is False
    assert eff.block_effects.empty
    assert eff.table.set_index("setting").loc["B", "coef"] == pytest.approx(-1.0, abs=0.3)


def test_a_session_with_too_few_steps_for_its_parameters_is_refused_not_fitted():
    """A single complete block of seven settings gives seven steps and seven parameters, which
    leaves no residual degrees of freedom and no basis for a cluster-robust covariance. The model
    must decline. Fitting it anyway would produce coefficients that look like estimates and
    standard errors that are meaningless, and nothing downstream would be able to tell."""
    res = SA.analyze_session(fill_sheet(blank_sheet(n_blocks=1), effects={"B": -1.0},
                                        noise_sd=0.2, seed=4))
    eff = res.effects[SA.PRIMARY_SITE]
    assert eff.fitted is False
    assert "not enough to estimate a cluster-robust covariance" in eff.reason
    assert res.primary_verdicts().empty


# ---------------------------------------------------------------------------------------------
# 5. The within-session noise floor
# ---------------------------------------------------------------------------------------------

def test_the_noise_floor_is_measured_from_the_repeated_incumbent():
    """The incumbent repeats once per block for exactly this purpose: the patient is on the same
    setting each time, so the spread of those ratings measures how much a rating moves for reasons
    unrelated to the setting. Without a repeated setting the noise and the effect are not
    separately identified and every contrast is measured against an unknown."""
    sheet = fill_sheet(blank_sheet(), noise_sd=0.0)
    # Overwrite the three anchor ratings with a known spread.
    anchor_rows = sheet.index[sheet.setting == "A"]
    assert len(anchor_rows) == 3
    sheet.loc[anchor_rows, "nrs_left_leg"] = [5.0, 6.0, 7.0]
    fl = SA.noise_floor(SA.to_long(SA.derive_washin(sheet).per_step),
                        site="left_leg", anchor="A")
    assert fl.n == 3 and fl.dof == 2
    assert fl.sd == pytest.approx(1.0)          # sd of 5, 6, 7 with one degree of freedom removed
    assert fl.method == "across_block_sd"
    assert "upper bound" in fl.note, ("with one anchor rating per block the spread contains the "
                                      "within-visit drift and must be labelled as an upper bound")


def test_repeated_anchor_ratings_inside_a_block_give_a_drift_free_noise_floor():
    """When the anchor is rated more than once within a single block the drift can be differenced
    out, and the resulting number is closer to pure rating noise. The module must use that better
    estimate when it is available and say which one it used."""
    long = pd.DataFrame({
        "step": [1, 2, 3, 4, 5, 6], "block": [1, 1, 2, 2, 1, 2],
        "setting": ["A", "A", "A", "A", "B", "B"], "site": ["left_leg"] * 6,
        "nrs": [5.0, 6.0, 8.0, 9.0, 5.5, 8.5],
    })
    fl = SA.noise_floor(long, site="left_leg", anchor="A")
    assert fl.method == "pooled_within_block"
    # Within each block the two anchor ratings differ by one point, so the pooled within-block
    # standard deviation is 1/sqrt(2), and the three-point between-block jump is excluded.
    assert fl.sd == pytest.approx(1.0 / np.sqrt(2.0))
    assert fl.sd < float(np.std([5.0, 6.0, 8.0, 9.0], ddof=1))


def test_a_measured_spread_of_zero_does_not_become_a_gate_of_zero():
    """Pain is recorded in whole points, and three whole-number ratings that happen to agree give
    a measured spread of exactly zero. Zero is not evidence that the measurement is noise-free,
    and using it as the gate would let a difference of one hundredth of a point count as clearing
    the noise floor. The whole-number scale sets its own irreducible floor and that is used
    instead, with both numbers reported so the substitution is visible."""
    long = pd.DataFrame({"step": [1, 2, 3], "block": [1, 2, 3], "setting": ["A"] * 3,
                         "site": ["left_leg"] * 3, "nrs": [6.0, 6.0, 6.0]})
    fl = SA.noise_floor(long, site="left_leg", anchor="A")
    assert fl.sd == 0.0
    assert fl.sd_applied == pytest.approx(1.0 / np.sqrt(12.0), abs=1e-9)
    assert fl.sd_applied > 0
    assert "not evidence that the measurement is noise-free" in fl.describe()


def test_the_noise_floor_is_not_assessed_when_the_incumbent_was_rated_once():
    """One rating has no spread. Reporting a noise floor of zero, or of anything else, would be
    inventing a number, so the honest output is that it was not assessed."""
    long = pd.DataFrame({"step": [1], "block": [1], "setting": ["A"], "site": ["left_leg"],
                         "nrs": [6.0]})
    fl = SA.noise_floor(long, site="left_leg", anchor="A")
    assert not np.isfinite(fl.sd) and fl.method == "none"
    assert "not assessed" in fl.describe()


# ---------------------------------------------------------------------------------------------
# 6. The verdict, and the resolution gate
# ---------------------------------------------------------------------------------------------

def _effects_table(rows):
    """Wrap a hand-written table of contrasts so the verdict logic can be tested in isolation."""
    tab = pd.DataFrame(rows, columns=["setting", "coef", "se", "ci_lo", "ci_hi", "pvalue",
                                      "n_obs"])
    return SA.SettingEffects(site="left_leg", anchor="A", with_block=True, table=tab,
                             block_effects=pd.DataFrame(), n_obs=int(tab.n_obs.sum()),
                             n_clusters=int(tab.n_obs.sum()), df_resid=10.0, fitted=True)


def _floor(sd):
    return SA.NoiseFloor(site="left_leg", anchor="A", sd=sd, n=3, dof=2,
                         method="across_block_sd", note="", sd_applied=sd)


def test_the_verdict_table_covers_all_four_outcomes():
    """One statement per candidate, and the statement has to distinguish 'we showed it is better'
    from 'it looks better and we could not show it'."""
    eff = _effects_table([
        ("B", -1.50, 0.20, -1.95, -1.05, 0.0001, 3),   # clears both gates
        ("C", -0.20, 0.05, -0.31, -0.09, 0.0020, 3),   # separates, but smaller than the noise
        ("D", -0.90, 0.60, -2.20, +0.40, 0.1500, 3),   # points better, interval touches zero
        ("E", +1.10, 0.30, +0.45, +1.75, 0.0030, 3),   # separates upward
        ("F", +0.10, 0.40, -0.77, +0.97, 0.8000, 3),   # nothing there
    ])
    v = SA.verdicts(eff, _floor(0.5)).set_index("setting")
    assert v.loc["B", "verdict"] == SA.VERDICT_BETTER_RESOLVED
    assert v.loc["C", "verdict"] == SA.VERDICT_BETTER_UNRESOLVED
    assert v.loc["D", "verdict"] == SA.VERDICT_BETTER_UNRESOLVED
    assert v.loc["E", "verdict"] == SA.VERDICT_WORSE
    assert v.loc["F", "verdict"] == SA.VERDICT_NO_DIFFERENCE


def test_a_difference_smaller_than_the_noise_floor_is_not_called_resolved():
    """A statistically detectable difference that is smaller than the amount a rating moves on its
    own during the same visit has not been shown to be something the patient could feel. The
    p-value here is tiny and the verdict must still withhold 'resolved'."""
    eff = _effects_table([("C", -0.20, 0.05, -0.31, -0.09, 0.002, 3)])
    strict = SA.verdicts(eff, _floor(0.5)).iloc[0]
    lenient = SA.verdicts(eff, _floor(0.05)).iloc[0]
    assert strict.verdict == SA.VERDICT_BETTER_UNRESOLVED and not strict.exceeds_noise_floor
    assert lenient.verdict == SA.VERDICT_BETTER_RESOLVED and bool(lenient.exceeds_noise_floor)
    assert bool(strict.separates_from_incumbent), ("the statistical gate passed; it is the "
                                                     "noise-floor gate that refused it")


def test_resolution_is_judged_against_the_uncertainty_of_the_DIFFERENCE():
    """The mistake this test exists to prevent was made once in this project and corrected: a
    confidence band was placed around the candidate and compared against a single point estimate
    of the incumbent, which throws away the incumbent's own uncertainty and manufactures findings.

    The data here are built so the two approaches disagree as loudly as possible. The incumbent's
    ratings swing wildly, the candidate's do not move at all, and the two means differ by two
    points. Comparing the candidate's very narrow band against the incumbent's point estimate says
    the difference is resolved. Carrying the incumbent's uncertainty into the difference says it is
    nowhere near resolved, and that is the correct answer.
    """
    swings = [1.0, 9.0, 1.0, 9.0, 1.0, 9.0]
    flat = [3.0] * 6
    long = pd.DataFrame({
        "step": list(range(1, 13)), "block": [1] * 12,
        "setting": ["A"] * 6 + ["B"] * 6, "site": ["left_leg"] * 12,
        "nrs": swings + flat,
    })
    eff = SA.fit_setting_effects(long, site="left_leg", anchor="A", with_block=False)
    row = eff.table.set_index("setting").loc["B"]

    # The estimated difference is right, and it is the DIFFERENCE that carries the uncertainty.
    assert row.coef == pytest.approx(-2.0, abs=1e-8)
    assert row.ci_lo < 0 < row.ci_hi, "the interval on the difference must include zero"

    # The naive comparison that was corrected: a band around the candidate alone. The candidate's
    # ratings are identical, so its own spread is zero and its band is a point that plainly
    # excludes the incumbent's mean of 5. This is what the module must NOT do.
    naive_candidate_sd = float(np.std(flat, ddof=1))
    assert naive_candidate_sd == 0.0
    assert abs(np.mean(flat) - np.mean(swings)) > 0.0, "the naive test would declare a difference"

    v = SA.verdicts(eff, _floor(0.3)).set_index("setting")
    assert v.loc["B", "verdict"] == SA.VERDICT_BETTER_UNRESOLVED
    assert not v.loc["B", "separates_from_incumbent"]
    assert "includes zero" in v.loc["B", "reason"]


def test_the_contrast_standard_error_carries_both_settings_uncertainty():
    """A structural statement of the same point, checked against the textbook formula. The
    standard error of a difference between two group means is the square root of the sum of their
    squared standard errors; if the module were reporting only the candidate's own standard error
    the number would be smaller than that."""
    a = [2.0, 4.0, 6.0, 8.0, 3.0, 7.0]
    b = [4.0, 5.0, 6.0, 5.0, 4.0, 6.0]
    long = pd.DataFrame({"step": list(range(1, 13)), "block": [1] * 12,
                         "setting": ["A"] * 6 + ["B"] * 6, "site": ["x"] * 12, "nrs": a + b})
    eff = SA.fit_setting_effects(long, site="x", anchor="A", with_block=False)
    se_reported = float(eff.table.set_index("setting").loc["B", "se"])
    se_a = float(np.std(a, ddof=1)) / np.sqrt(len(a))
    se_b = float(np.std(b, ddof=1)) / np.sqrt(len(b))
    assert se_reported > se_b, "the reported error must exceed the candidate's own error alone"
    assert se_reported == pytest.approx(np.sqrt(se_a ** 2 + se_b ** 2), rel=0.35)


def test_a_setting_with_too_few_usable_steps_gets_not_assessed_not_a_verdict():
    """A reader skimming a results table reads 'no difference' as evidence of no difference. When
    a setting has almost no usable data the honest output is that it was not assessed, so that
    absence of evidence is never presented as evidence of absence."""
    eff = _effects_table([("B", -0.9, 0.6, -2.2, 0.4, 0.15, 1),
                          ("C", -0.9, 0.6, -2.2, 0.4, 0.15, 3)])
    v = SA.verdicts(eff, _floor(0.4), min_obs=2).set_index("setting")
    assert v.loc["B", "verdict"] == SA.VERDICT_NOT_ASSESSED
    assert "fewer than the 2 required" in v.loc["B", "reason"]
    assert v.loc["C", "verdict"] != SA.VERDICT_NOT_ASSESSED


def test_not_assessed_reaches_the_verdict_table_end_to_end_when_washin_kills_a_setting():
    """The realistic route to too-little-data: a setting whose steps were nearly all rushed. The
    exclusions must propagate all the way to a 'not assessed' verdict rather than quietly
    producing a confident-looking estimate from one surviving rating."""
    sched = blank_sheet()
    doomed = set(sched.loc[sched.setting == "G", "step"].iloc[:2])
    sheet = fill_sheet(sched, effects={"B": -1.0}, noise_sd=0.3, seed=6,
                       washin_s=lambda r: 15.0 if r.step in doomed else 80.0)
    res = SA.analyze_session(sheet)
    v = res.primary_verdicts().set_index("setting")
    assert res.n_excluded_short_washin == 2
    assert v.loc["G", "n_obs"] == 1
    assert v.loc["G", "verdict"] == SA.VERDICT_NOT_ASSESSED


def test_a_contrast_with_no_usable_standard_error_gets_no_verdict():
    """This is not hypothetical. When each step contributes a single rating every cluster holds
    one observation, and the cluster-robust sandwich can come out numerically
    non-positive-definite, leaving a negative variance on the diagonal and a missing standard
    error. A missing standard error is not a wide one. If such a row fell through to the ordinary
    logic it would receive whichever verdict the sign of its point estimate implied, with no
    uncertainty behind it at all."""
    eff = _effects_table([("B", -1.5, np.nan, np.nan, np.nan, np.nan, 3),
                          ("C", -1.5, 0.20, -1.95, -1.05, 0.0001, 3)])
    eff.n_nonfinite_se = 1
    v = SA.verdicts(eff, _floor(0.3)).set_index("setting")
    assert v.loc["B", "verdict"] == SA.VERDICT_NOT_ASSESSED
    assert "not a finite number" in v.loc["B", "reason"]
    assert v.loc["C", "verdict"] == SA.VERDICT_BETTER_RESOLVED, ("one unusable contrast must not "
                                                                 "invalidate the others")


def test_the_minute_resolution_caveat_fires_even_on_a_partly_minute_resolution_sheet():
    """A sheet where only some times were written to the nearest minute still has steps whose
    wash-in is uncertain by about as much as the sixty-second threshold being checked. An
    all-or-nothing caveat would stay silent on exactly the mixed sheets a real clinic produces."""
    sheet = fill_sheet(blank_sheet(), with_seconds=True)
    for i in (0, 1, 2):
        sheet.loc[sheet.index[i], "actual_time_programmed"] = \
            str(sheet.loc[sheet.index[i], "actual_time_programmed"])[:5]
        sheet.loc[sheet.index[i], "actual_time_rated"] = \
            str(sheet.loc[sheet.index[i], "actual_time_rated"])[:5]
    rep = SA.derive_washin(sheet)
    assert rep.n_minute_resolution == 3
    assert rep.minute_resolution_only is False
    assert "3 readable step(s) were timed to the nearest minute" in rep.describe()


def test_when_nothing_beats_the_incumbent_the_report_says_so_plainly():
    """The expected outcome of a single session is that no candidate separates. That is a result
    and the report must state it as one, rather than leaving an empty table for a reader to
    interpret as an inconclusive or failed session."""
    res = SA.analyze_session(fill_sheet(blank_sheet(), noise_sd=1.2, seed=21))
    assert res.any_setting_beats_incumbent() is False
    assert "No candidate setting was shown to be better than the incumbent" in res.report_text()


# ---------------------------------------------------------------------------------------------
# 7. Side effects
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (0, 0), (1, 1), (2, 2), (3, 3), ("0", 0), ("2", 2), ("none", 0), ("None", 0), ("mild", 1),
    ("moderate", 2), ("mod", 2), ("severe", 3), (2.0, 2),
])
def test_side_effect_codes_and_words_are_both_accepted(raw, expected):
    """The sheet asks for a number from zero to three; clinicians write words. Both must read."""
    assert SA.code_side_effect(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, np.nan, "?", "unknown", 4, -1, "worse"])
def test_a_blank_side_effect_cell_is_unknown_and_never_none(raw):
    """Reading a skipped question as 'no side effect' would turn every unasked question into
    evidence of safety, which is exactly backwards in a safety column."""
    assert SA.code_side_effect(raw) is None


def test_the_severity_distribution_is_reported_per_setting():
    sheet = fill_sheet(blank_sheet(), side_effects=0)
    sheet["side_effect_none_mild_mod_severe"] = \
        sheet["side_effect_none_mild_mod_severe"].astype(object)
    sheet.loc[sheet.setting == "G", "side_effect_none_mild_mod_severe"] = [0, 1, 2]
    sheet.loc[sheet.index[0], "side_effect_none_mild_mod_severe"] = ""
    dist, _ = SA.side_effect_summary(sheet)
    g = dist.set_index("setting").loc["G"]
    assert (g["none"], g["mild"], g["moderate"], g["severe"]) == (1, 1, 1, 0)
    assert dist["unknown"].sum() == 1
    assert dist.n_steps.sum() == len(sheet)


def test_every_moderate_or_severe_event_is_flagged_individually():
    """A serious event is read one at a time with its setting and amplitudes attached, never as a
    rate buried in a summary row."""
    sheet = fill_sheet(blank_sheet(), side_effects=0)
    sheet.loc[sheet.index[4], "side_effect_none_mild_mod_severe"] = 2
    sheet.loc[sheet.index[11], "side_effect_none_mild_mod_severe"] = 3
    sheet.loc[sheet.index[2], "side_effect_none_mild_mod_severe"] = 1
    _, flags = SA.side_effect_summary(sheet)
    assert len(flags) == 2, "mild events are counted but not flagged"
    assert set(flags.severity) == {2, 3}
    for col in ("step", "setting", "ampL", "ampR", "severity_label"):
        assert col in flags.columns


def test_no_amplitude_severity_dose_response_model_is_fitted():
    """This patient's historical record was examined for a relationship between amplitude and
    side-effect severity across four hundred and seventeen non-procedural steps with stimulation
    on, and none was found. A monotone model would impose a shape the data have refused, and its
    slope would then be read as evidence for the relationship. This test guards against someone
    adding one back."""
    dist, flags = SA.side_effect_summary(fill_sheet(blank_sheet(), side_effects=0))
    numeric_outputs = set(dist.columns) | set(flags.columns)
    for forbidden in ("slope", "coef", "pvalue", "odds_ratio", "threshold", "ed50"):
        assert not any(forbidden in str(c).lower() for c in numeric_outputs), forbidden
    assert not hasattr(SA, "fit_amplitude_severity")
    res = SA.analyze_session(fill_sheet(blank_sheet(), side_effects=0))
    assert "No amplitude/severity dose-response model was fitted" in res.report_text()


# ---------------------------------------------------------------------------------------------
# 8. Reshaping, robustness and the end-to-end contract
# ---------------------------------------------------------------------------------------------

def test_ratings_outside_the_zero_to_ten_scale_are_dropped_and_counted():
    """A 66 in a pain column is a slipped keystroke for 6, not a rating. Keeping it would move a
    mean by several points; dropping it silently would hide that the sheet needs checking."""
    sheet = fill_sheet(blank_sheet(), noise_sd=0.0)
    sheet.loc[sheet.index[3], "nrs_left_leg"] = 66.0
    sheet.loc[sheet.index[7], "nrs_back"] = -2.0
    long = SA.to_long(SA.derive_washin(sheet).per_step)
    assert long.attrs["n_ratings_out_of_range"] == 2
    assert long.nrs.between(0, 10).all()


def test_a_completely_blank_sheet_produces_no_verdicts_and_does_not_crash():
    """The analysis will be pointed at a sheet before it is filled in, by accident if nothing
    else. It must say that nothing could be fitted rather than raise, and above all it must not
    return a table of zeros that looks like a result."""
    res = SA.analyze_session(blank_sheet())
    assert res.washin.n_not_assessed == 21 and res.washin.n_compliant == 0
    assert res.long.empty
    for site in SA.DEFAULT_SITES:
        assert res.effects[site].fitted is False
        assert res.verdicts[site].empty
    assert res.any_setting_beats_incumbent() is False
    assert "No model could be fitted" in res.report_text()


def test_a_site_the_clinician_left_blank_is_reported_as_unfitted_not_as_null_effects():
    sheet = fill_sheet(blank_sheet(), effects={"B": -1.0}, noise_sd=0.2, seed=8)
    sheet["nrs_back"] = ""
    res = SA.analyze_session(sheet)
    assert res.effects["back"].fitted is False and "no usable ratings" in res.effects["back"].reason
    assert res.effects[SA.PRIMARY_SITE].fitted is True


def test_the_primary_outcome_is_the_left_leg():
    """Established for this patient: the global rating misses the stimulation effect that every
    site-specific score detects, so a session judged on the overall rating would conclude that
    nothing works. The default must not drift back to the global score."""
    assert SA.PRIMARY_SITE == "left_leg"
    res = SA.analyze_session(fill_sheet(blank_sheet(), effects={"B": -1.2}, noise_sd=0.2, seed=2))
    assert res.primary_site == "left_leg"
    assert res.primary_verdicts().equals(res.verdicts["left_leg"])
    assert "PRIMARY OUTCOME: the left leg" in res.report_text()


def test_the_analysis_accepts_a_csv_path_as_well_as_a_frame(tmp_path):
    """Tomorrow the input is a file the clinic hands over, not an object in memory."""
    sheet = fill_sheet(blank_sheet(), effects={"B": -1.4}, noise_sd=0.2, seed=12)
    path = tmp_path / "filled.csv"
    sheet.to_csv(path, index=False)
    from_frame = SA.analyze_session(sheet)
    from_path = SA.analyze_session(str(path))
    pd.testing.assert_frame_equal(
        from_frame.effects[SA.PRIMARY_SITE].table, from_path.effects[SA.PRIMARY_SITE].table)


REAL_SHEET = Path("/Users/pshirvalkar/.claude-science/orgs/e1a4e614-cfd2-4f53-ae46-1203303ddbf1/"
                  "artifacts/proj_937f45eb8797/3dcc8995-619a-4b15-80f5-56d2971e3ef8/"
                  "v75619ca9_rcs08_clinic_schedule_v2.csv")


@pytest.mark.skipif(not REAL_SHEET.exists(), reason="the real clinic sheet is not on this machine")
def test_the_real_clinic_sheet_is_accepted_and_analysable_once_filled():
    """The schema check that matters: the sheet that will actually come back from the clinic must
    go through this module unmodified. The ratings are synthetic, but every column name, dtype and
    row count is the real one."""
    sheet = pd.read_csv(REAL_SHEET)
    assert len(sheet) == 21
    filled = fill_sheet(sheet, effects={"B": -1.6}, drift_per_block=-0.4, noise_sd=0.3, seed=1)
    res = SA.analyze_session(filled)
    assert res.effects[SA.PRIMARY_SITE].fitted
    assert res.effects[SA.PRIMARY_SITE].table.set_index("setting").loc["B", "coef"] == \
        pytest.approx(-1.6, abs=0.4)
    assert len(res.primary_verdicts()) == 6
    assert isinstance(res.report_text(), str) and len(res.report_text()) > 500
