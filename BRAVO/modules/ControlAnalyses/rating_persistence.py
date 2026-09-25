"""Is a day's mean pain rating predictable from the days around it, and what does that do to the
visit-count estimate in the next-visit protocol? (finding M2 of
`artifacts/research_2026-09-25_options/08_critique_science.md`, item A4 of `11_REVISED_PLAN.md`,
2026-09-25.) Free of the database; the runner feeds it one score's matched report times and values.

WHAT THIS CHECKS. Report 02's own visit-count table (`02_next_clinic_visit_protocol.md`, "Sample
size and power") solved the Fisher-z sample-size formula for how many INDEPENDENT days would be
needed to find the observed correlation reliably -- about 52 days for one band tested alone, 73 for
the four pre-registered bands, 98 for a fresh 22-band discovery pass -- and then said a visit adds
one calendar day toward that count. Both halves treat a calendar day of daily-mean pain as an
independent draw. If today's rating is correlated with yesterday's, it is not: the EFFECTIVE number
of independent days in a run of N calendar days is smaller than N. This module reuses the same
lag-1 correction this project already built and uses elsewhere for a band-power-to-pain correlation
(`Biomarkers.stats_utils.effective_n`, decision 246), applied here to a pain score against its own
later self, and restates report 02's 52/73/98 as calendar days once that correction is applied.

Descriptive throughout: it recommends no visit count and blocks nothing.
"""
import numpy as np
import pandas as pd

try:
    from modules.Biomarkers.routines import stats_utils as SU
except ImportError:                                            # host spelling
    from Biomarkers.routines import stats_utils as SU

#: Report 02's own table (`02_next_clinic_visit_protocol.md`, "Sample size and power"): independent
#: days needed for 80% power at a 0.05 significance level, at the observed correlation (about
#: 0.38), for one band tested alone, the four pre-registered bands (corrected for four), and a
#: fresh 22-band discovery pass (corrected for 22). A list, not a dict, so the payload a page reads
#: carries the target's own name and count beside its restated calendar-day count -- nothing here
#: needs a second, JS-side copy of the numbers to draw a table of them.
INDEPENDENT_DAYS_NEEDED = (dict(name="one band, tested alone", independent_days=52.0),
                          dict(name="the four pre-registered bands", independent_days=73.0),
                          dict(name="a fresh 22-band discovery pass", independent_days=98.0))

LAGS_DAYS = tuple(range(1, 8))


def daily_mean_series(days, values):
    """One row per calendar day present in `days` (its mean of `values`), reindexed onto EVERY day
    from the first to the last so a fixed lag in the returned array is a fixed number of calendar
    days apart. A day with no rating is NaN, never interpolated (decisions 193-196: time is
    modelled nowhere). `days` is anything `pandas.to_datetime` reads (e.g. "%Y-%m-%d" strings).
    Returns `(day_strings, daily_values)`."""
    idx = pd.to_datetime(np.asarray(days))
    if idx.size == 0:
        return np.array([], dtype=str), np.array([], dtype=float)
    daily = pd.Series(np.asarray(values, dtype=float), index=idx).groupby(level=0).mean()
    full = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    return full.strftime("%Y-%m-%d").to_numpy(), daily.reindex(full).to_numpy(dtype=float)


def lag_corr(daily_values, k):
    """`(r, n_pairs)`: the Pearson correlation of a daily-mean series with itself `k` calendar days
    later, over the day-pairs where both sides are finite (a gap in the calendar breaks the pair on
    neither side, since `daily_mean_series` already reindexed every day). NaN with fewer than 4
    usable pairs or either side constant."""
    x = np.asarray(daily_values, dtype=float)
    if k <= 0 or k >= x.size:
        return float("nan"), 0
    a, b = x[:-k], x[k:]
    m = np.isfinite(a) & np.isfinite(b)
    n = int(m.sum())
    if n < 4 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return float("nan"), n
    return float(np.corrcoef(a[m], b[m])[0, 1]), n


def effective_days(daily_values):
    """The Bretherton/Bartlett effective sample size of a daily-mean series against its own later
    self (`Biomarkers.stats_utils.effective_n` with both arguments the same series -- the same
    formula collapses to `N * (1 - r1^2) / (1 + r1^2)` when the two series are identical): how many
    independent days a run of N autocorrelated calendar days is worth. `None` with fewer than 3
    finite days."""
    x = np.asarray(daily_values, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 3:
        return None
    return float(SU.effective_n(x, x))


def yield_ratio(daily_values):
    """Effective independent days per calendar day (`effective_days / calendar days with a
    rating`). `None` when there are too few days to say."""
    x = np.asarray(daily_values, dtype=float)
    n = int(np.isfinite(x).sum())
    if n == 0:
        return None
    eff = effective_days(x)
    return None if eff is None else float(eff / n)


def calendar_days_for(independent_days, ratio):
    """Report 02's independent-day target restated as calendar days, at one yield ratio. `None`
    when the ratio is unusable."""
    if ratio is None or ratio <= 0:
        return None
    return float(independent_days) / float(ratio)


def score_summary(score, n_ratings, daily_values, *, label=None):
    """One score's reading: the lag-1 to lag-7 day-to-day correlations, the effective number of
    independent days, the yield ratio, and report 02's three targets restated as calendar days at
    this series' own ratio."""
    x = np.asarray(daily_values, dtype=float)
    n_days = int(np.isfinite(x).sum())
    lags = []
    for k in LAGS_DAYS:
        r, n_pairs = lag_corr(x, k)
        lags.append(dict(lag_days=k, r=(float(r) if np.isfinite(r) else None), n_pairs=n_pairs))
    eff = effective_days(x)
    ratio = yield_ratio(x)
    calendar = [dict(name=t["name"], independent_days=t["independent_days"],
                     calendar_days=calendar_days_for(t["independent_days"], ratio))
               for t in INDEPENDENT_DAYS_NEEDED]
    return dict(score=score, label=label, n_ratings=int(n_ratings), n_days=n_days, lags=lags,
                effective_days=eff, ratio=ratio, calendar_days_needed=calendar)


def reading(rows):
    """Plain-English lines: the day-to-day correlation and the effective count per score, the same
    for the 0 mA stretch where it exists, and report 02's targets restated as calendar days at the
    0 mA stretch's own VAS ratio -- the score and stretch the 0.38 correlation report 02 quotes was
    read from (decisions 262a, 264)."""
    out = []
    for r in rows:
        if r.get("n_days", 0) < 4:
            out.append(f"{r['score']}: too few days with a rating to read.")
            continue
        lag1 = next((line["r"] for line in r["lags"] if line["lag_days"] == 1), None)
        line = f"{r['score']} ({r['n_ratings']} ratings on {r['n_days']} days)"
        if lag1 is not None:
            line += f": a day's mean rating correlates with the next day's at {lag1:+.2f}"
        else:
            line += ": the next-day correlation could not be read (too few adjacent day-pairs)"
        if r.get("effective_days") is not None:
            line += (f"; {r['effective_days']:.1f} of those {r['n_days']} days count as independent "
                     f"({100 * r['ratio']:.0f}% of the raw count)")
        out.append(line + ".")
        z = r.get("zero_ma")
        if z and z.get("effective_days") is not None:
            out.append(f"{r['score']}, the 0 mA stretch ({z['label']}, {z['n_days']} days): "
                       f"{z['effective_days']:.1f} independent days ({100 * z['ratio']:.0f}% of the raw count).")
    vas = next((r.get("zero_ma") for r in rows if r["score"] == "vas" and r.get("zero_ma")), None)
    if vas and vas.get("ratio"):
        parts = [f"{t['independent_days']:.0f} to {t['calendar_days']:.0f} calendar days ({t['name']})"
                 for t in vas.get("calendar_days_needed", []) if t.get("calendar_days") is not None]
        if parts:
            out.append("Report 02's independent-day targets, restated as calendar days at the 0 mA stretch's "
                       "own VAS day-to-day correlation (the score and stretch its 0.38 was read from): "
                       + "; ".join(parts) + ".")
    else:
        out.append("The 0 mA stretch did not give VAS a usable day-to-day correlation, so report 02's targets "
                   "are not restated as calendar days here.")
    out.append("Descriptive: corrects a planning number only; recommends no visit count and blocks nothing.")
    return out
