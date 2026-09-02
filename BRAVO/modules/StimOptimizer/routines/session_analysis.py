"""Turn a filled-in clinic schedule sheet into setting-level results.

WHAT THIS MODULE IS FOR
-----------------------
:mod:`StimOptimizer.routines.schedule` produces the blank sheet that goes into the clinic: one row
per test step, with columns the clinician fills in by hand during the visit. This module reads that
sheet back once it has been filled in and answers the only question the visit was run to answer,
which is whether any candidate stimulation setting is better than the setting the patient is
already on.

Everything here is deliberately conservative, and the reasons are written out rather than assumed,
because each one corrects a specific mistake that has already been made once in this project.

RE-DERIVING THE WASH-IN RATHER THAN TRUSTING IT
----------------------------------------------
The protocol says to wait sixty seconds after programming a new setting before asking the patient
for a rating. Sixty seconds is a protocol parameter declared by the principal investigator; it is
not something the analysis is free to change. What the analysis *can* do is check whether the
sixty seconds actually elapsed, because in a busy clinic they frequently do not. We therefore ask
the clinician to write down two clock times per step, the time the setting was programmed and the
time the rating was taken, and we subtract them to recover the wash-in that really happened. A step
whose real wash-in fell short of the threshold is dropped from the primary analysis, and the number
of steps dropped is reported as a number. It is never dropped silently.

A step whose times are missing or unreadable is reported as "not assessed". It is not reported as
compliant. We do not know that the wash-in was long enough, and writing down that we do not know is
more useful than a guess in either direction.

BLOCK MUST ENTER EVERY MODEL AS A FACTOR
----------------------------------------
This project has measured, in this patient, that pain ratings decline over the course of a visit.
In a fixed running order "the later setting" and "the better setting" are the same variable. The
schedule is therefore a randomised complete block design, and the analysis carries block as a
factor so that the within-visit drift is removed by the model instead of being assumed away.

Because the reader should be able to see how large that drift is rather than take our word for it,
this module fits every model twice, once with the block factor and once without it, and reports
both side by side. In a perfectly complete block design the two sets of setting coefficients will
be similar and the block-adjusted one will simply be more precise. If steps have been dropped, for
short wash-in or for any other reason, the design is no longer balanced and the two can differ a
great deal. That difference is exactly the thing the reader needs to see.

WHY THE STANDARD ERRORS ARE CLUSTER-ROBUST
------------------------------------------
Several pain ratings are taken at each step, one per body site, and if a step is rated more than
once those ratings belong to the same step as well. Ratings that share a step are not independent
of one another: whatever was going on with the patient at that moment affects all of them. Ordinary
standard errors assume independence and would therefore be too small. We cluster the standard
errors on the step, which is the level at which the correlation lives.

When a model is fitted to a single body site and each step contributes exactly one rating, every
cluster contains one observation. In that situation the cluster-robust estimator reduces to the
ordinary heteroskedasticity-robust estimator, which is the correct behaviour and not a failure. The
clustering is what protects the standard errors as soon as a step contributes more than one rating,
which is what happens the moment a clinician records a repeat rating.

THE NOISE FLOOR, AND WHY THE ANCHOR REPEATS
-------------------------------------------
The incumbent setting appears once in every block. That repetition is the only reason the
within-session measurement noise can be estimated separately from the between-setting effect. The
patient is on the same setting each time the anchor comes round, so the spread of the anchor's own
ratings is a direct measurement of how much a rating moves for reasons that have nothing to do with
the setting. We call that spread the noise floor and we report it. A candidate setting whose
estimated advantage is smaller than the noise floor has not been shown to do anything the patient
could feel, however small its p-value.

RESOLUTION IS A PROPERTY OF THE DIFFERENCE, NOT OF THE CANDIDATE
----------------------------------------------------------------
An earlier version of this project compared a confidence band around a candidate against a single
point estimate of the incumbent. That is wrong, and it is wrong in the direction that manufactures
findings, because it throws away the incumbent's own uncertainty. The incumbent's mean is estimated
from a handful of ratings and carries just as much uncertainty as the candidate's.

The fix is structural rather than a correction applied afterwards. Every model in this module codes
the setting factor with the incumbent as the reference level, so each estimated coefficient *is*
the difference between that candidate and the incumbent, and its standard error is the standard
error of that difference. It already contains the incumbent's variance and the covariance between
the two estimates. When the confidence interval on such a coefficient excludes zero, the difference
has been resolved against its own uncertainty, with both settings' uncertainty inside it.

SIDE EFFECTS ARE DESCRIBED, NOT MODELLED
----------------------------------------
This project has already looked for a relationship between stimulation amplitude and side-effect
severity in this patient's historical record and did not find one: across four hundred and
seventeen non-procedural steps with stimulation on, the rank correlation between amplitude and
severity was very close to zero, moderate-or-worse events were about as common below two
milliamps as at or above it, and several moderate events occurred with the stimulator at zero.
Fitting a model that assumes severity rises with amplitude would impose a shape the data have
already refused. This module therefore reports the observed severity distribution per setting and
flags every moderate or severe event individually, and it does not fit a dose-response model.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# The four pain sites the clinic sheet asks for, in the order they appear on the sheet. The primary
# outcome for this patient is the LEFT LEG. That is not an arbitrary default: in this patient's
# historical record the global "overall" rating misses the stimulation effect that every
# site-specific score detects, so a session judged on the overall rating alone would conclude that
# nothing works.
DEFAULT_SITES = ("left_leg", "left_foot", "back", "overall")
PRIMARY_SITE = "left_leg"

#: Column name prefix for the pain ratings on the clinic sheet.
NRS_PREFIX = "nrs_"

#: The protocol wash-in, in seconds. Declared by the principal investigator. This module checks
#: compliance against it and never changes it.
WASHIN_THRESHOLD_S = 60.0

#: The 0-3 coding of the side-effect column on the clinic sheet, and the words it stands for.
SIDE_EFFECT_LABELS = {0: "none", 1: "mild", 2: "moderate", 3: "severe"}
_SIDE_EFFECT_WORDS = {"none": 0, "nil": 0, "no": 0, "0": 0,
                      "mild": 1, "1": 1,
                      "mod": 2, "moderate": 2, "2": 2,
                      "severe": 3, "sev": 3, "3": 3}

#: Wash-in compliance statuses. Exactly one is assigned to every step.
WASHIN_COMPLIANT = "compliant"
WASHIN_SHORT = "short"
WASHIN_NEGATIVE = "negative"
WASHIN_NOT_ASSESSED = "not_assessed"

#: Verdict labels returned by :func:`verdicts`.
VERDICT_BETTER_RESOLVED = "better_resolved"
VERDICT_BETTER_UNRESOLVED = "better_unresolved"
VERDICT_NO_DIFFERENCE = "no_difference"
VERDICT_WORSE = "worse"
VERDICT_NOT_ASSESSED = "not_assessed"


# ---------------------------------------------------------------------------------------------
# 1. Reading the clock times a clinician actually wrote down
# ---------------------------------------------------------------------------------------------

# A trailing "am"/"pm", written any of the ways people write it: "pm", "PM", "p.m.", " p", "P.M."
_MERIDIEM = re.compile(r"\s*([ap])\.?\s*m?\.?\s*$", re.IGNORECASE)
# Minutes must be written with two digits. This rejects "12.7", which is what a spreadsheet
# produces when a cell was formatted as a number rather than a time, and "14:3", which could
# equally have meant 14:03 or 14:30. Refusing to read an ambiguous time is the right behaviour
# here: a step whose wash-in is not assessed is honest, a step whose wash-in was guessed is not.
_COLON_FORM = re.compile(r"^(\d{1,2})[:.\-h](\d{2})(?:[:.\-](\d{1,2}))?$")
_DIGIT_FORM = re.compile(r"^(\d{3,6})$")


def parse_clock_time(value):
    """Read one clock time the way a clinician might have written it during a busy visit.

    Returns a pair ``(seconds_since_midnight, resolution_s)``. ``resolution_s`` is 1.0 when the
    clinician wrote seconds and 60.0 when they wrote only hours and minutes, and it matters: if a
    time is recorded only to the nearest minute then a wash-in derived from two such times is only
    known to the nearest minute, which is the same size as the sixty-second threshold we are
    checking against. Both elements of the pair are ``None`` when the value cannot be read at all.

    The formats accepted are the ones people really write: ``"14:03"``, ``"14:03:22"``,
    ``"2:03 pm"``, ``"2:03:15 PM"``, ``"1403"``, ``"140322"``, ``"14.03"`` and ``"14h03"``, with
    surrounding whitespace ignored. Anything else, including an empty cell, the string ``"n/a"``
    and any out-of-range time such as ``"25:00"``, returns ``(None, None)``. We deliberately do not
    guess at a value we cannot read, because a guessed wash-in would be indistinguishable in the
    output from a measured one.
    """
    if value is None:
        return None, None
    if isinstance(value, float) and np.isnan(value):
        return None, None
    if isinstance(value, (pd.Timestamp,)):
        return float(value.hour * 3600 + value.minute * 60 + value.second), 1.0

    text = str(value).strip().lower()
    if not text:
        return None, None

    # Pull off a trailing "am"/"pm" (with or without dots or a space) before looking at the digits.
    meridiem = None
    m = _MERIDIEM.search(text)
    if m:
        letter = m.group(1)
        if letter:
            meridiem = letter.lower()
            text = text[:m.start()].strip()
    text = text.replace(" ", "")
    if not text:
        return None, None

    hour = minute = second = None
    resolution = 60.0

    m = _COLON_FORM.match(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if m.group(3) is not None:
            second = int(m.group(3))
            resolution = 1.0
    else:
        m = _DIGIT_FORM.match(text)
        if m:
            digits = m.group(1)
            if len(digits) in (3, 4):          # "903" -> 9:03, "1403" -> 14:03
                hour, minute = int(digits[:-2]), int(digits[-2:])
            elif len(digits) in (5, 6):        # "90322" -> 9:03:22, "140322" -> 14:03:22
                hour, minute, second = int(digits[:-4]), int(digits[-4:-2]), int(digits[-2:])
                resolution = 1.0
    if hour is None:
        return None, None

    second = 0 if second is None else second
    if not (0 <= minute <= 59 and 0 <= second <= 59):
        return None, None

    if meridiem is not None:
        # A twelve-hour clock only has hours 1 to 12. "13:00 pm" is not a time, it is a typo, and
        # we would rather say so than silently pick one of the two things it might have meant.
        if not (1 <= hour <= 12):
            return None, None
        if meridiem == "p" and hour != 12:
            hour += 12
        elif meridiem == "a" and hour == 12:
            hour = 0
    elif not (0 <= hour <= 23):
        return None, None

    return float(hour * 3600 + minute * 60 + second), resolution


# ---------------------------------------------------------------------------------------------
# 2. The realised wash-in, step by step
# ---------------------------------------------------------------------------------------------

@dataclass
class WashinReport:
    """What actually happened to the wash-in during the visit, as opposed to what was planned."""

    threshold_s: float
    per_step: pd.DataFrame
    n_steps: int = 0
    n_compliant: int = 0
    n_short: int = 0
    n_negative: int = 0
    n_not_assessed: int = 0
    realised_s: dict = field(default_factory=dict)
    #: True when every readable step was timed to the nearest minute.
    minute_resolution_only: bool = False
    #: How many readable steps were timed to the nearest minute rather than the nearest second.
    #: Any step at all in this state deserves the caveat, because a wash-in derived from
    #: minute-resolution times is uncertain by about as much as the threshold being checked.
    n_minute_resolution: int = 0

    def describe(self) -> str:
        lines = [f"Wash-in check against the declared {self.threshold_s:g} second protocol "
                 f"({self.n_steps} steps):",
                 f"  {self.n_compliant} steps met the threshold.",
                 f"  {self.n_short} steps were rated too soon and are excluded from the primary "
                 f"analysis.",
                 f"  {self.n_negative} steps recorded a rating time BEFORE the programming time, "
                 f"which is a data-entry error rather than a short wash-in.",
                 f"  {self.n_not_assessed} steps had missing or unreadable times, so their wash-in "
                 f"is not assessed rather than assumed compliant."]
        if self.realised_s:
            lines.append(f"  Among readable steps the realised wash-in ran from "
                         f"{self.realised_s['min']:.0f} to {self.realised_s['max']:.0f} seconds "
                         f"with a median of {self.realised_s['median']:.0f} seconds.")
        if self.n_minute_resolution:
            scope = ("Every readable step was" if self.minute_resolution_only
                     else f"{self.n_minute_resolution} readable step(s) were")
            lines.append(f"  {scope} timed to the nearest minute rather than the nearest second, "
                         f"so the wash-in for those steps is only known to within about sixty "
                         f"seconds, which is the size of the threshold itself. A step recorded as "
                         f"sitting exactly on the threshold could really have been either side of "
                         f"it. Treat the compliant/short split for those steps as approximate.")
        return "\n".join(lines)


def derive_washin(sheet, *, threshold_s=WASHIN_THRESHOLD_S,
                  programmed_col="actual_time_programmed", rated_col="actual_time_rated"):
    """Recover the wash-in that really happened at each step and judge it against the protocol.

    ``sheet`` is the filled-in clinic schedule, one row per step. Returns a
    :class:`WashinReport` whose ``per_step`` frame carries, for every step, the two parsed clock
    times in seconds since midnight, the realised wash-in in seconds, the resolution the times were
    written to, and a status which is one of ``"compliant"``, ``"short"``, ``"negative"`` or
    ``"not_assessed"``.

    The distinction between ``"short"`` and ``"not_assessed"`` is the point of this function. A
    short step is one we measured and found wanting, and it is excluded from the primary analysis.
    A not-assessed step is one we could not measure. Rolling the second into the first would either
    throw away usable data or quietly pass unverified data through, depending on which way we
    guessed, and neither is acceptable in a study whose purpose is to validate a biomarker.
    """
    df = pd.DataFrame(sheet).copy()
    for col in (programmed_col, rated_col):
        if col not in df.columns:
            raise KeyError(f"the sheet has no {col!r} column; got {list(df.columns)}")

    prog = [parse_clock_time(v) for v in df[programmed_col]]
    rate = [parse_clock_time(v) for v in df[rated_col]]

    rows = []
    for i, ((p_s, p_res), (r_s, r_res)) in enumerate(zip(prog, rate)):
        washin = np.nan
        resolution = np.nan
        if p_s is None or r_s is None:
            status = WASHIN_NOT_ASSESSED
        else:
            washin = r_s - p_s
            # The worse of the two resolutions governs what the difference is really known to.
            resolution = max(p_res, r_res)
            if washin < 0:
                status = WASHIN_NEGATIVE
            elif washin < threshold_s:
                status = WASHIN_SHORT
            else:
                status = WASHIN_COMPLIANT
        rows.append({"t_programmed_s": p_s, "t_rated_s": r_s,
                     "washin_s_actual": washin, "washin_resolution_s": resolution,
                     "washin_status": status})

    per_step = pd.concat([df.reset_index(drop=True),
                          pd.DataFrame(rows)], axis=1)

    readable = per_step.washin_s_actual.dropna()
    realised = {}
    if len(readable):
        realised = {"n": int(len(readable)), "min": float(readable.min()),
                    "q25": float(readable.quantile(0.25)), "median": float(readable.median()),
                    "q75": float(readable.quantile(0.75)), "max": float(readable.max()),
                    "mean": float(readable.mean())}

    res = per_step.washin_resolution_s.dropna()
    counts = per_step.washin_status.value_counts()
    return WashinReport(
        threshold_s=float(threshold_s), per_step=per_step, n_steps=int(len(per_step)),
        n_compliant=int(counts.get(WASHIN_COMPLIANT, 0)),
        n_short=int(counts.get(WASHIN_SHORT, 0)),
        n_negative=int(counts.get(WASHIN_NEGATIVE, 0)),
        n_not_assessed=int(counts.get(WASHIN_NOT_ASSESSED, 0)),
        realised_s=realised,
        minute_resolution_only=bool(len(res) and (res >= 60.0).all()),
        n_minute_resolution=int((res >= 60.0).sum()))


# ---------------------------------------------------------------------------------------------
# 3. Reshaping the sheet into something a model can be fitted to
# ---------------------------------------------------------------------------------------------

def to_long(sheet, *, sites=DEFAULT_SITES, nrs_prefix=NRS_PREFIX):
    """Reshape one-row-per-step into one-row-per-rating, which is the unit a model needs.

    The clinic sheet is wide because that is what is convenient to fill in on paper: a step is a
    row and each body site is a column. A model needs the opposite shape, one row per rating, with
    the body site as a label rather than a column position. Ratings that are blank or not a number
    between zero and ten are dropped, and the number dropped is available to the caller through the
    returned frame's ``attrs`` so that a sheet full of typing errors cannot look like a clean sheet
    with fewer steps.
    """
    df = pd.DataFrame(sheet).copy()
    if "step" not in df.columns:
        df["step"] = np.arange(1, len(df) + 1)
    if "block" not in df.columns:
        df["block"] = 1
    if "setting" not in df.columns:
        raise KeyError("the sheet must carry a 'setting' column naming the setting tested at each "
                       "step; without it there is nothing to compare")

    keep = ["step", "block", "setting"]
    for extra in ("washin_status", "washin_s_actual", "ampL", "ampR", "freq",
                  "side_effect_none_mild_mod_severe", "notes"):
        if extra in df.columns:
            keep.append(extra)

    frames, n_unreadable = [], 0
    for site in sites:
        col = f"{nrs_prefix}{site}"
        if col not in df.columns:
            continue
        raw = df[col]
        value = pd.to_numeric(raw, errors="coerce")
        # A rating outside the 0-10 numeric rating scale is a transcription error, not a rating.
        out_of_range = value.notna() & ~value.between(0, 10)
        n_unreadable += int(out_of_range.sum())
        value = value.where(~out_of_range)
        part = df[keep].copy()
        part["site"] = site
        part["nrs"] = value.to_numpy()
        frames.append(part)

    if not frames:
        raise KeyError(f"the sheet carries none of the expected rating columns "
                       f"{[nrs_prefix + s for s in sites]}")

    long = pd.concat(frames, ignore_index=True)
    n_blank = int(long.nrs.isna().sum()) - n_unreadable
    long = long.dropna(subset=["nrs"]).reset_index(drop=True)
    long["step"] = long["step"].astype(int)
    long["block"] = long["block"].astype(int)
    long["setting"] = long["setting"].astype(str)
    long.attrs["n_ratings_out_of_range"] = int(n_unreadable)
    long.attrs["n_ratings_blank"] = int(max(n_blank, 0))
    return long


def usable_mask(long, *, exclude_statuses=(WASHIN_SHORT, WASHIN_NEGATIVE),
                unverified_policy="include"):
    """Which rows enter the primary analysis, given the wash-in check.

    Steps whose measured wash-in fell short of the protocol, and steps whose recorded times run
    backwards, are excluded. What to do with steps whose wash-in could not be assessed is a
    judgement call rather than a fact, so it is a parameter. The default is to include them, on the
    grounds that a clinician who forgot to write a time has not thereby demonstrated a protocol
    violation, and that excluding every step with a missing time would in the worst case discard
    the entire visit. Whichever policy is chosen, the count of affected steps is reported, so a
    reader can see how much of the result rests on unverified steps.
    """
    if unverified_policy not in ("include", "exclude"):
        raise ValueError("unverified_policy must be 'include' or 'exclude'")
    if "washin_status" not in long.columns:
        return pd.Series(True, index=long.index)
    bad = set(exclude_statuses)
    if unverified_policy == "exclude":
        bad = bad | {WASHIN_NOT_ASSESSED}
    return ~long.washin_status.isin(bad)


# ---------------------------------------------------------------------------------------------
# 4. Setting effects, with and without the block factor
# ---------------------------------------------------------------------------------------------

# statsmodels names a treatment-coded coefficient "C(setting, Treatment(reference='A'))[T.B]".
# The nested parentheses mean the pattern has to run greedily to the LAST ")[T." in the name.
_TERM = re.compile(r"^C\(setting.*\)\[T\.(.+)\]$")
_BLOCK_TERM = re.compile(r"^C\(block\)\[T\.(.+)\]$")


@dataclass
class SettingEffects:
    """One fitted model: every candidate setting's difference from the incumbent, at one site."""

    site: str
    anchor: str
    with_block: bool
    table: pd.DataFrame
    block_effects: pd.DataFrame
    n_obs: int
    n_clusters: int
    df_resid: float
    fitted: bool = True
    reason: str = ""
    #: How many contrasts came back with a standard error that is not a finite number. This is
    #: rare but real: with one rating per step every cluster contains a single observation, and
    #: the cluster-robust sandwich can then come out numerically non-positive-definite, which
    #: leaves a negative variance on the diagonal and a missing standard error. Such a contrast
    #: has no usable uncertainty and must not be given a verdict.
    n_nonfinite_se: int = 0


def fit_setting_effects(long, *, site, anchor, with_block=True, cluster_col="step", alpha=0.05):
    """Fit one site's ratings on setting and (optionally) block, with cluster-robust errors.

    The setting factor is coded with ``anchor`` as its reference level, so every coefficient the
    model returns is already the difference between that candidate setting and the incumbent, and
    the standard error attached to it is the standard error of that difference. This is the whole
    reason the model is specified this way rather than as a set of per-setting means compared
    afterwards: a difference computed after the fact from two independent-looking means would drop
    the covariance term and understate the uncertainty.

    Standard errors are clustered on ``cluster_col``, which is the step. Ratings taken at the same
    step share whatever was happening to the patient at that moment and are not independent.

    Returns a :class:`SettingEffects`. If the model cannot be fitted at all, for instance because
    the site has no usable ratings or because only the anchor was tested, the returned object has
    ``fitted=False`` and a plain-English ``reason``, and no numbers are invented to fill the gap.
    """
    import statsmodels.formula.api as smf

    empty = pd.DataFrame(columns=["setting", "coef", "se", "ci_lo", "ci_hi", "pvalue", "n_obs"])
    d = long[long.site == site].copy() if "site" in long.columns else long.copy()
    d = d.dropna(subset=["nrs"])

    def _unfitted(reason):
        return SettingEffects(site=site, anchor=anchor, with_block=with_block, table=empty.copy(),
                              block_effects=pd.DataFrame(columns=["block", "coef", "se", "pvalue"]),
                              n_obs=int(len(d)), n_clusters=int(d[cluster_col].nunique())
                              if cluster_col in d.columns else 0,
                              df_resid=float("nan"), fitted=False, reason=reason)

    if d.empty:
        return _unfitted(f"there are no usable ratings for the {site} site")
    if anchor not in set(d.setting):
        return _unfitted(f"the incumbent anchor {anchor!r} was never rated at the {site} site, so "
                         f"there is nothing to compare the candidates against")
    if d.setting.nunique() < 2:
        return _unfitted(f"only the incumbent {anchor!r} has usable ratings at the {site} site")

    n_blocks = d.block.nunique()
    use_block = bool(with_block) and n_blocks >= 2
    formula = f"nrs ~ C(setting, Treatment(reference='{anchor}'))"
    if use_block:
        formula += " + C(block)"

    n_params = d.setting.nunique() + (n_blocks - 1 if use_block else 0)
    n_clusters = int(d[cluster_col].nunique()) if cluster_col in d.columns else int(len(d))
    if n_clusters <= n_params:
        return _unfitted(
            f"the {site} site has {n_clusters} independent steps for {n_params} parameters, which "
            f"is not enough to estimate a cluster-robust covariance; the model was not fitted "
            f"rather than fitted with unusable standard errors")

    model = smf.ols(formula, data=d)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if cluster_col in d.columns:
            res = model.fit(cov_type="cluster", cov_kwds={"groups": d[cluster_col].to_numpy()})
        else:
            res = model.fit(cov_type="HC1")
        # These are computed lazily and are the point at which a non-positive-definite
        # cluster-robust covariance surfaces as a warning from numpy about taking the square root
        # of a negative number. The warning is suppressed here because the condition is not
        # ignored: it is counted into n_nonfinite_se below and turned into a "not assessed"
        # verdict downstream, which is a great deal more visible than a line on standard error.
        ci = res.conf_int(alpha=alpha)
        _ = res.bse, res.pvalues
    counts = d.setting.value_counts()
    rows = []
    for term in res.params.index:
        m = _TERM.match(term)
        if not m:
            continue
        name = m.group(1)
        rows.append({"setting": name, "coef": float(res.params[term]),
                     "se": float(res.bse[term]), "ci_lo": float(ci.loc[term, 0]),
                     "ci_hi": float(ci.loc[term, 1]), "pvalue": float(res.pvalues[term]),
                     "n_obs": int(counts.get(name, 0))})
    table = pd.DataFrame(rows, columns=empty.columns).sort_values("setting").reset_index(drop=True)

    brows = []
    for term in res.params.index:
        m = _BLOCK_TERM.match(term)
        if m:
            brows.append({"block": m.group(1), "coef": float(res.params[term]),
                          "se": float(res.bse[term]), "pvalue": float(res.pvalues[term])})
    block_effects = pd.DataFrame(brows, columns=["block", "coef", "se", "pvalue"])

    bad_se = int((~np.isfinite(table[["se", "ci_lo", "ci_hi"]].to_numpy())).any(axis=1).sum()) \
        if len(table) else 0
    out = SettingEffects(site=site, anchor=anchor, with_block=use_block, table=table,
                         block_effects=block_effects, n_obs=int(res.nobs),
                         n_clusters=n_clusters, df_resid=float(res.df_resid),
                         n_nonfinite_se=bad_se)
    # Keep the fitted result available for callers that want the full model, but out of the way of
    # the tidy table that most callers will use.
    out.table.attrs["formula"] = formula
    out.table.attrs["anchor_mean"] = float(res.params.get("Intercept", np.nan))
    return out


# ---------------------------------------------------------------------------------------------
# 5. The within-session noise floor, measured from the repeated anchor
# ---------------------------------------------------------------------------------------------

@dataclass
class NoiseFloor:
    """How much a rating moves when nothing about the setting has changed.

    Three numbers are kept apart on purpose. ``sd`` is what was actually measured from the
    incumbent's repeated ratings. ``quantisation_sd`` is the irreducible spread that comes from
    recording pain on a whole-number scale: a rating written as 6 stands for anything the patient
    might have meant between 5.5 and 6.5, and a value uniformly spread over an interval one point
    wide has a standard deviation of one over the square root of twelve, about 0.29 points.
    ``sd_applied`` is the larger of the two and is the number the verdict gate actually uses.

    The distinction matters because of a degenerate case that will happen in practice. With three
    anchor ratings on a whole-number scale it is entirely possible that all three come out
    identical, and the measured standard deviation is then exactly zero. Zero is not credible
    evidence that the measurement is noise-free; it is what three coarse observations look like
    when they happen to agree. Using zero as the gate would let any difference at all, however
    tiny, count as exceeding the noise floor. Falling back on the quantisation width prevents that
    while staying honest about which number came from the data.
    """

    site: str
    anchor: str
    sd: float
    n: int
    dof: int
    method: str
    note: str
    values: tuple = ()
    quantisation_sd: float = 0.0
    sd_applied: float = float("nan")

    def describe(self) -> str:
        if not np.isfinite(self.sd):
            return (f"[{self.site}] the within-session noise floor could not be measured: "
                    f"{self.note}")
        text = (f"[{self.site}] the incumbent {self.anchor!r} was rated {self.n} times during the "
                f"session and those ratings had a standard deviation of {self.sd:.2f} points. "
                f"{self.note}")
        if self.sd_applied > self.sd + 1e-12:
            text += (f" The measured spread is below the {self.quantisation_sd:.2f} point spread "
                     f"that the whole-number rating scale imposes on its own, so the gate uses "
                     f"{self.sd_applied:.2f} points instead. A measured spread of "
                     f"{self.sd:.2f} from {self.n} coarse ratings is not evidence that the "
                     f"measurement is noise-free.")
        else:
            text += f" The verdict gate uses {self.sd_applied:.2f} points."
        return text


def noise_floor(long, *, site, anchor, rating_resolution=1.0):
    """Measure the within-session noise from the incumbent's own repeated ratings.

    The incumbent is programmed once per block. Each time it comes round the patient is on exactly
    the same setting, so any difference between those ratings is measurement noise, mood, fatigue,
    or the within-visit drift, but it is definitely not an effect of the setting. The spread of
    those ratings is therefore a direct, assumption-free measurement of how large a difference has
    to be before it means anything.

    Two versions are computed depending on what the data allow. If some block contains more than
    one anchor rating then the noise can be pooled *within* blocks, which removes the within-visit
    drift and leaves something closer to pure measurement noise. If, as in the standard schedule,
    the anchor is rated exactly once per block, then the only estimate available is the spread
    across blocks, and that spread contains the drift as well as the noise. In that case the number
    is reported with an explicit note saying so, because it is an upper bound on the noise rather
    than an estimate of it.
    """
    d = long[(long.site == site)] if "site" in long.columns else long.copy()
    d = d[d.setting.astype(str) == str(anchor)].dropna(subset=["nrs"])
    quant_sd = float(rating_resolution) / float(np.sqrt(12.0))

    if len(d) < 2:
        return NoiseFloor(site=site, anchor=anchor, sd=float("nan"), n=int(len(d)), dof=0,
                          method="none",
                          note=(f"the incumbent was rated {len(d)} time(s) at this site, and at "
                                f"least two ratings are needed to measure any spread at all, so "
                                f"the noise floor is not assessed"),
                          values=tuple(d.nrs.astype(float)),
                          quantisation_sd=quant_sd, sd_applied=float("nan"))

    per_block = d.groupby("block").nrs.count()
    if (per_block >= 2).any():
        # Pooled within-block variance: sum of squared deviations from each block's own mean,
        # divided by the total degrees of freedom left after removing one mean per block.
        ss, dof = 0.0, 0
        for _, g in d.groupby("block"):
            if len(g) >= 2:
                ss += float(((g.nrs - g.nrs.mean()) ** 2).sum())
                dof += len(g) - 1
        sd = float(np.sqrt(ss / dof)) if dof > 0 else float("nan")
        note = ("It was measured within blocks, so the within-visit drift has been removed from it "
                "and it reflects moment-to-moment rating noise.")
        method = "pooled_within_block"
    else:
        sd = float(d.nrs.astype(float).std(ddof=1))
        dof = len(d) - 1
        note = ("The incumbent was rated only once per block, so this spread contains the "
                "within-visit drift as well as the rating noise. Treat it as an upper bound on "
                "the noise rather than a measurement of it.")
        method = "across_block_sd"

    applied = float(max(sd, quant_sd)) if np.isfinite(sd) else float("nan")
    return NoiseFloor(site=site, anchor=anchor, sd=sd, n=int(len(d)), dof=int(dof), method=method,
                      note=note, values=tuple(float(v) for v in d.nrs),
                      quantisation_sd=quant_sd, sd_applied=applied)


# ---------------------------------------------------------------------------------------------
# 6. The verdict
# ---------------------------------------------------------------------------------------------

def verdicts(effects, floor, *, min_obs=2):
    """Turn fitted differences into one plain statement per candidate setting.

    Two separate gates have to be passed before this function will say that a candidate is better
    than the incumbent, and they are gates on different things.

    The first gate is statistical. The confidence interval on the coefficient must exclude zero.
    Because the model codes the incumbent as the reference level, that coefficient is the
    difference between the two settings and its interval is the interval of that difference,
    carrying the incumbent's uncertainty inside it. A candidate whose interval touches zero has not
    been separated from the incumbent, no matter how favourable its point estimate looks.

    The second gate is practical. The size of the difference must exceed the within-session noise
    floor measured from the incumbent's own repeated ratings. A difference smaller than the amount
    a rating moves on its own during the same visit is not something the patient can be said to
    have felt.

    The two gates are applied asymmetrically and that asymmetry is deliberate. Declaring a setting
    *better* requires both gates, because acting on a false positive means reprogramming a patient
    onto a setting that does nothing. Declaring a setting *worse* requires only the statistical
    gate, because a candidate that looks harmful should be flagged even if the harm is small.

    A setting with fewer than ``min_obs`` usable ratings gets the verdict ``"not_assessed"``. It
    does not get a verdict computed from one rating and a wide interval, because a reader skimming
    a results table will read "no difference" as evidence of no difference rather than as an
    absence of evidence.
    """
    cols = ["setting", "verdict", "coef", "ci_lo", "ci_hi", "pvalue", "n_obs",
            "separates_from_incumbent", "exceeds_noise_floor", "noise_floor_sd", "reason"]
    if not getattr(effects, "fitted", False) or effects.table.empty:
        return pd.DataFrame(columns=cols)

    # The gate uses sd_applied rather than the raw measured spread, because a measured spread of
    # zero from three whole-number ratings would otherwise let any difference at all through. See
    # the NoiseFloor docstring for why the whole-number scale sets a floor of its own.
    sd = float(getattr(floor, "sd_applied", float("nan")))
    if not np.isfinite(sd):
        sd = float(getattr(floor, "sd", float("nan")))
    rows = []
    for r in effects.table.itertuples(index=False):
        separates = bool((r.ci_lo > 0) or (r.ci_hi < 0))
        if np.isfinite(sd):
            exceeds = bool(abs(r.coef) > sd)
        else:
            exceeds = False

        if not np.isfinite([r.se, r.ci_lo, r.ci_hi]).all():
            # A missing standard error is not a wide one. Without a usable uncertainty the two
            # gates below cannot be evaluated at all, and letting the row fall through would
            # quietly hand it whichever verdict the point estimate's sign happens to imply.
            verdict = VERDICT_NOT_ASSESSED
            reason = ("the cluster-robust standard error for this contrast is not a finite "
                      "number, so the difference has no usable uncertainty and no verdict can be "
                      "issued from it")
        elif r.n_obs < min_obs:
            verdict = VERDICT_NOT_ASSESSED
            reason = (f"only {r.n_obs} usable rating(s) for this setting, fewer than the {min_obs} "
                      f"required before a verdict is issued")
        elif separates and r.coef > 0:
            verdict = VERDICT_WORSE
            reason = ("the interval on the difference lies entirely above zero, so this setting "
                      "gave higher pain than the incumbent")
        elif separates and r.coef < 0 and exceeds:
            verdict = VERDICT_BETTER_RESOLVED
            reason = (f"the interval on the difference lies entirely below zero and the difference "
                      f"of {abs(r.coef):.2f} points is larger than the {sd:.2f} point "
                      f"within-session noise floor")
        elif separates and r.coef < 0:
            verdict = VERDICT_BETTER_UNRESOLVED
            reason = (f"the interval on the difference excludes zero, but the difference of "
                      f"{abs(r.coef):.2f} points is not larger than the "
                      f"{sd:.2f} point within-session noise floor"
                      if np.isfinite(sd) else
                      "the interval on the difference excludes zero, but the within-session noise "
                      "floor could not be measured, so the difference cannot be called resolved")
        elif r.coef < 0:
            verdict = VERDICT_BETTER_UNRESOLVED
            reason = ("the point estimate favours this setting, but the interval on the difference "
                      "includes zero, so the difference is not resolved against its own "
                      "uncertainty")
        else:
            verdict = VERDICT_NO_DIFFERENCE
            reason = ("the interval on the difference includes zero and the point estimate does "
                      "not favour this setting over the incumbent")

        rows.append({"setting": r.setting, "verdict": verdict, "coef": r.coef, "ci_lo": r.ci_lo,
                     "ci_hi": r.ci_hi, "pvalue": r.pvalue, "n_obs": r.n_obs,
                     "separates_from_incumbent": separates, "exceeds_noise_floor": exceeds,
                     "noise_floor_sd": sd, "reason": reason})
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------------------------
# 7. Side effects: described, never modelled
# ---------------------------------------------------------------------------------------------

def code_side_effect(value):
    """Read the side-effect cell, which is coded 0 to 3, and return an integer or ``None``.

    The sheet asks for a number, but clinicians write words, so both are accepted. Anything that is
    neither is returned as ``None`` and counted as unknown rather than assumed to be zero.
    Assuming a blank cell means "no side effect" would turn every skipped question into evidence of
    safety, which is precisely backwards.
    """
    if value is None:
        return None
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value) if 0 <= int(value) <= 3 else None
    if isinstance(value, float):
        if np.isnan(value):
            return None
        return int(value) if float(value).is_integer() and 0 <= value <= 3 else None
    text = str(value).strip().lower().rstrip(".")
    if not text:
        return None
    return _SIDE_EFFECT_WORDS.get(text)


def side_effect_summary(sheet, *, column="side_effect_none_mild_mod_severe"):
    """Report the observed severity distribution per setting and flag every serious event.

    No dose-response model is fitted here, and that is a finding rather than an omission. This
    patient's historical record was examined for a relationship between stimulation amplitude and
    side-effect severity across four hundred and seventeen non-procedural steps with stimulation
    on, and none was found: the rank correlation was essentially zero, moderate-or-worse events
    were about as frequent below two milliamps as at or above two milliamps, and several moderate
    events were recorded with the stimulator delivering nothing at all. A monotone amplitude model
    would impose a shape these data have already refused, and its fitted slope would be read as
    evidence for a relationship that has been looked for and not found.

    Returns ``(distribution, flags)``. ``distribution`` has one row per setting with a count in
    each severity category and a count of unknowns. ``flags`` has one row per moderate or severe
    event, carrying the step, the setting, the amplitudes and whatever the clinician wrote in the
    notes, because a serious event is read individually and never as a summary statistic.
    """
    df = pd.DataFrame(sheet).copy()
    if column not in df.columns:
        raise KeyError(f"the sheet has no {column!r} column; got {list(df.columns)}")
    if "setting" not in df.columns:
        raise KeyError("the sheet must carry a 'setting' column")

    df["_severity"] = [code_side_effect(v) for v in df[column]]
    df["_label"] = [SIDE_EFFECT_LABELS.get(v, "unknown") for v in df["_severity"]]

    order = ["none", "mild", "moderate", "severe", "unknown"]
    dist = (df.groupby("setting")["_label"].value_counts().unstack(fill_value=0)
            .reindex(columns=order, fill_value=0).reset_index())
    dist["n_steps"] = dist[order].sum(axis=1)
    dist["n_moderate_or_worse"] = dist["moderate"] + dist["severe"]

    serious = df[df["_severity"].isin([2, 3])].copy()
    flag_cols = [c for c in ("step", "block", "setting", "freq", "ampL", "ampR", "notes")
                 if c in serious.columns]
    flags = serious[flag_cols].copy()
    flags["severity"] = serious["_severity"].astype(int).to_numpy()
    flags["severity_label"] = serious["_label"].to_numpy()
    return dist.reset_index(drop=True), flags.reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# 8. The whole thing, end to end
# ---------------------------------------------------------------------------------------------

@dataclass
class SessionAnalysis:
    """Everything the visit produced, in one object, with nothing hidden behind a summary."""

    anchor: str
    primary_site: str
    sites: tuple
    washin: WashinReport
    n_excluded_short_washin: int
    n_excluded_negative_time: int
    n_unverified_washin: int
    unverified_policy: str
    effects: dict = field(default_factory=dict)
    effects_no_block: dict = field(default_factory=dict)
    noise: dict = field(default_factory=dict)
    verdicts: dict = field(default_factory=dict)
    side_effect_distribution: pd.DataFrame = field(default_factory=pd.DataFrame)
    side_effect_flags: pd.DataFrame = field(default_factory=pd.DataFrame)
    long: pd.DataFrame = field(default_factory=pd.DataFrame)

    def primary_verdicts(self) -> pd.DataFrame:
        """The verdict table for the primary outcome, which for this patient is the left leg."""
        return self.verdicts.get(self.primary_site, pd.DataFrame())

    def any_setting_beats_incumbent(self) -> bool:
        """True only if some setting is better than the incumbent at the primary site AND the
        difference is larger than the within-session noise floor. Deliberately strict."""
        v = self.primary_verdicts()
        return bool(len(v) and (v.verdict == VERDICT_BETTER_RESOLVED).any())

    def drift_comparison(self, site=None) -> pd.DataFrame:
        """Put the block-adjusted and unadjusted setting effects side by side for one site.

        The purpose is to make the size of the within-visit drift visible. In a complete block
        design, where every setting is tested once in every block, the drift is orthogonal to the
        setting and the two columns of coefficients will be close together, with the adjusted one
        more precise. If steps have been dropped the balance is broken and the two can diverge, and
        the amount they diverge is how much the block adjustment is doing.
        """
        site = site or self.primary_site
        a, b = self.effects.get(site), self.effects_no_block.get(site)
        if a is None or b is None or not a.fitted or not b.fitted:
            return pd.DataFrame()
        out = a.table[["setting", "coef", "se", "ci_lo", "ci_hi", "pvalue"]].merge(
            b.table[["setting", "coef", "se", "ci_lo", "ci_hi", "pvalue"]],
            on="setting", suffixes=("_block_adjusted", "_unadjusted"))
        out["shift_from_block_adjustment"] = (out.coef_block_adjusted - out.coef_unadjusted)
        return out

    def report_text(self) -> str:
        """A plain-English write-up of the session, suitable for pasting into a session note."""
        out = [self.washin.describe(), ""]
        if self.n_excluded_short_washin or self.n_excluded_negative_time:
            out.append(f"{self.n_excluded_short_washin + self.n_excluded_negative_time} step(s) "
                       f"were excluded from the primary analysis on the wash-in check.")
        if self.n_unverified_washin:
            out.append(f"{self.n_unverified_washin} step(s) could not be checked and were "
                       f"{'kept in' if self.unverified_policy == 'include' else 'held out of'} "
                       f"the primary analysis under the '{self.unverified_policy}' policy.")
        out.append("")

        site = self.primary_site
        out.append(f"PRIMARY OUTCOME: the {site.replace('_', ' ')}. This is the primary outcome "
                   f"because in this patient's historical record the global rating misses the "
                   f"stimulation effect that every site-specific score detects.")
        fl = self.noise.get(site)
        if fl is not None:
            out.append(fl.describe())

        eff = self.effects.get(site)
        if eff is None or not eff.fitted:
            out.append(f"No model could be fitted at the {site} site: "
                       f"{getattr(eff, 'reason', 'the site is absent from the sheet')}.")
        else:
            out.append(f"Model: {eff.table.attrs.get('formula', '')}, {eff.n_obs} ratings across "
                       f"{eff.n_clusters} steps, standard errors clustered on the step.")
            v = self.verdicts.get(site, pd.DataFrame())
            if len(v):
                out.append("")
                out.append("Verdict per candidate setting, against the incumbent "
                           f"{self.anchor!r}:")
                for r in v.itertuples(index=False):
                    out.append(f"  {r.setting}: {r.verdict}. Difference "
                               f"{r.coef:+.2f} points (95% interval {r.ci_lo:+.2f} to "
                               f"{r.ci_hi:+.2f}, p = {r.pvalue:.3f}). {r.reason}.")
            if not self.any_setting_beats_incumbent():
                out.append("")
                out.append("No candidate setting was shown to be better than the incumbent by more "
                           "than the within-session noise floor. This is the expected outcome of a "
                           "single session with this many settings and this few ratings each, and "
                           "it is a result rather than a failure: it says the incumbent should be "
                           "kept and that separating these settings needs more sessions, not that "
                           "the settings are identical.")

        drift = self.drift_comparison(site)
        if len(drift):
            worst = drift.shift_from_block_adjustment.abs().max()
            out.append("")
            out.append(f"Effect of adjusting for the within-visit drift: the largest change in any "
                       f"setting's estimated difference when the block factor is added is "
                       f"{worst:.2f} points. In a complete block design this should be small "
                       f"because the design already makes drift orthogonal to setting; a large "
                       f"value means the design was broken by dropped steps and the unadjusted "
                       f"numbers should not be used.")
            be = eff.block_effects if eff is not None and eff.fitted else pd.DataFrame()
            if len(be):
                terms = ", ".join(f"block {r.block} {r.coef:+.2f}" for r in be.itertuples())
                out.append(f"Estimated block shifts relative to the first block: {terms}. A "
                           f"negative value means ratings were lower later in the visit.")

        if len(self.side_effect_flags):
            out.append("")
            out.append(f"{len(self.side_effect_flags)} moderate or severe side-effect event(s) "
                       f"were recorded and are listed individually in the flags table.")
        else:
            out.append("")
            out.append("No moderate or severe side-effect event was recorded during the session.")
        out.append("No amplitude/severity dose-response model was fitted, because this "
                   "relationship has been looked for in this patient's historical record and was "
                   "not found.")
        return "\n".join(out)


def analyze_session(sheet, *, anchor="A", sites=DEFAULT_SITES, primary_site=PRIMARY_SITE,
                    washin_threshold_s=WASHIN_THRESHOLD_S, unverified_policy="include",
                    min_obs=2, alpha=0.05):
    """Run the whole post-session analysis on a filled-in clinic schedule sheet.

    ``sheet`` is a path to the filled CSV or an already-loaded frame. The steps are, in order: read
    the clock times and recover the wash-in that really happened; drop the steps that fell short of
    the protocol and count them; reshape to one row per rating; fit each site twice, with and
    without the block factor; measure the within-session noise from the incumbent's repeated
    ratings; issue one verdict per candidate; and describe the side effects without modelling them.
    """
    if isinstance(sheet, (str, bytes)) or hasattr(sheet, "read_text"):
        sheet = pd.read_csv(sheet)
    sheet = pd.DataFrame(sheet).copy()

    washin = derive_washin(sheet, threshold_s=washin_threshold_s)
    long_all = to_long(washin.per_step, sites=sites)
    keep = usable_mask(long_all, unverified_policy=unverified_policy)
    long = long_all[keep].reset_index(drop=True)

    effects, effects_nb, noise, verd = {}, {}, {}, {}
    for site in sites:
        if f"{NRS_PREFIX}{site}" not in sheet.columns:
            continue
        effects[site] = fit_setting_effects(long, site=site, anchor=anchor, with_block=True,
                                            alpha=alpha)
        effects_nb[site] = fit_setting_effects(long, site=site, anchor=anchor, with_block=False,
                                               alpha=alpha)
        noise[site] = noise_floor(long, site=site, anchor=anchor)
        verd[site] = verdicts(effects[site], noise[site], min_obs=min_obs)

    dist, flags = side_effect_summary(sheet)

    return SessionAnalysis(
        anchor=str(anchor), primary_site=primary_site, sites=tuple(sites), washin=washin,
        n_excluded_short_washin=washin.n_short, n_excluded_negative_time=washin.n_negative,
        n_unverified_washin=washin.n_not_assessed, unverified_policy=unverified_policy,
        effects=effects, effects_no_block=effects_nb, noise=noise, verdicts=verd,
        side_effect_distribution=dist, side_effect_flags=flags, long=long)
