"""The recent-reports check: does a band keep the same clear sign on the reports filed lately?
(wave 2, C8; the PI, 2026-10-21: "Recent-reports check, warn".)

WHAT IT IS. The pain reports are put in time order and the report at the 70% mark is found
(`choice_cut`); its time is the cut, and its California calendar date is printed wherever the check
is (`choice_cut_date`). The cut is ROLLING: it is worked out afresh from the pain series on every
build, so it moves as reports arrive (the PI's ruling of 2026-10-18). One cut per request, from the
series the heat-map grid and the Closed-Loop sign-off both build (the pain reports after the
clinic-sheet merge): every contact pair, every grid (mixed, TD-only, PSD-only), every chronic answer
and the sign-off print the same one.

Each band's link with pain (Pearson r) is then read again on that band's OWN matched reports filed
after the cut, at the length of signal and from the source its row already uses, with its interval
by the row's own method (whole reports resampled in blocks, `analytics._block_boot_r_interval`), and
the counts after and before the cut. Status: "checked", "too few recent reports" (fewer than
`RECENT_MIN_REPORTS` after the cut), or "no reports after the cut". A checked band whose recent r has
the other sign, or whose recent interval reaches across zero, gets a warning appended to `why`; the
other two statuses get a short note instead.

WHAT IT IS NOT. Band choice stays on ALL the data: nothing is blanked, and no answer, status,
verdict, gate or p reads this. The recent reports were also used in choosing, so this checks
consistency over time, not an independent test. No rotation p is given: with the counts RCS08 has
after the cut (9-17 TD-matched reports per contact pair on 2026-10-21) the smallest p a rotation
could reach is 1/9 to 1/17, above 0.05.

No Django: the callers hand in the series.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import analytics
from .local_time import local_calendar_day

#: The share of reports, in time order, at or before the cut.
RECENT_SHARE = 0.70
#: Fewer recent reports than this and the band is not checked ("too few recent reports").
RECENT_MIN_REPORTS = 10

STATUS_CHECKED = "checked"
STATUS_TOO_FEW = "too few recent reports"
STATUS_NONE = "no reports after the cut"

WHAT = ("the band's link with pain (Pearson r) read again on its own matched reports filed after the "
        "70% cut by time (the cut rolls forward as reports arrive), with its interval by the row's own "
        "method; a warning only, it changes no answer. These recent reports were also used in "
        "choosing, so this checks consistency over time, not an independent test")
WARNING_TAIL = ("These recent reports were also used in choosing, so this checks consistency over "
                "time, not an independent test")


def choice_cut(report_times_s, share=RECENT_SHARE):
    """The time (UTC seconds) of the report at the ``share`` mark, the reports in time order: the
    last of the first floor(share x n). None for ``share`` of 1 or more (the neutral share), or when
    that leaves no report on either side of the cut (fewer than 2 reports)."""
    t = np.asarray(report_times_s if report_times_s is not None else [], dtype=float).ravel()
    t = np.sort(t[np.isfinite(t)])
    if float(share) >= 1.0 or t.size < 2:
        return None
    k = int(np.floor(float(share) * t.size))
    if k < 1:
        return None
    return float(t[k - 1])


def cut_date(cut_s):
    """The California calendar date (ISO) of a cut, or None."""
    if cut_s is None:
        return None
    d = local_calendar_day(pd.Timestamp(float(cut_s), unit="s"))
    return d.isoformat() if d is not None else None


def cut_block(report_times_s, pain_values=None, share=RECENT_SHARE):
    """The request's one cut: on the reports with a time and (when given) a finite pain score."""
    t = np.asarray(report_times_s if report_times_s is not None else [], dtype=float).ravel()
    ok = np.isfinite(t)
    if pain_values is not None:
        y = np.asarray(pain_values, dtype=float).ravel()
        if y.size == t.size:
            ok &= np.isfinite(y)
    t = t[ok]
    cut = choice_cut(t, share)
    return {"available": cut is not None, "choice_cut_s": cut, "choice_cut_date": cut_date(cut),
            "share": float(share), "rolling": True, "n_reports": int(t.size),
            "n_before": (int((t <= cut).sum()) if cut is not None else None),
            "n_after": (int((t > cut).sum()) if cut is not None else None),
            "what": WHAT}


def _fmt(v):
    return "%+.2f" % float(v)


def recent_check(x, y, t, cut, *, r_all, n_boot, rng):
    """The check on one band: ``x`` its band power, ``y`` the pain score, ``t`` the report times,
    one entry per report (NaN where the band has no value); ``cut`` the request's `cut_block`;
    ``r_all`` the band's own r on all its reports (the row's). Draws only from ``rng``."""
    x = np.asarray(x, float).ravel(); y = np.asarray(y, float).ravel(); t = np.asarray(t, float).ravel()
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(t)
    c = (cut or {}).get("choice_cut_s")
    date = (cut or {}).get("choice_cut_date")
    out = {"choice_cut_date": date, "choice_cut_s": c, "status": STATUS_NONE, "n_after": 0,
           "n_before": int(m.sum()) if c is None else int((m & (t <= c)).sum()),
           "pearson_r": None, "pearson_r_low": None, "pearson_r_high": None,
           "r_all_reports": (float(r_all) if r_all is not None and np.isfinite(r_all) else None),
           "consistent": None, "warning": None, "note": None,
           "min_reports": RECENT_MIN_REPORTS, "what": WHAT}
    if c is None:
        out["note"] = "Recent-reports check: no cut could be placed (too few pain reports)"
        out["words"] = out["note"]
        return out
    after = m & (t > c)
    n = int(after.sum())
    out["n_after"] = n
    if n == 0:
        out["note"] = "Recent-reports check: no reports after %s at this band" % date
        out["words"] = out["note"]
        return out
    if n < RECENT_MIN_REPORTS:
        out["status"] = STATUS_TOO_FEW
        out["note"] = ("Recent-reports check: only %d reports after %s (fewer than %d), not checked"
                       % (n, date, RECENT_MIN_REPORTS))
        out["words"] = out["note"]
        return out
    out["status"] = STATUS_CHECKED
    order = np.argsort(t[after], kind="stable")          # time order, for the blocks
    xa, ya = x[after][order], y[after][order]
    if np.ptp(xa) == 0 or np.ptp(ya) == 0:
        out["note"] = ("Recent-reports check: band power or pain does not vary over the %d reports "
                       "after %s" % (n, date))
        out["words"] = out["note"]
        return out
    r = float(np.corrcoef(xa, ya)[0, 1])
    lo, hi = analytics._block_boot_r_interval(xa.copy(), ya.copy(), n_boot=int(n_boot), rng=rng)
    out.update(pearson_r=r, pearson_r_low=lo, pearson_r_high=hi)
    ra = out["r_all_reports"]
    interval = ("[%s, %s]" % (_fmt(lo), _fmt(hi)) if lo is not None and hi is not None
                else "(no interval)")
    head = "On the %d reports after %s, r is %s %s" % (n, date, _fmt(r), interval)
    if ra is None or ra == 0:
        out["words"] = head
        return out
    clear = lo is not None and hi is not None and (lo > 0 or hi < 0)
    out["consistent"] = bool(clear and np.sign(r) == np.sign(ra))
    if out["consistent"]:
        out["words"] = head + ": the same clear sign as on all reports"
    else:
        out["warning"] = head + ": not the same clear sign as on all reports. " + WARNING_TAIL
        out["words"] = out["warning"]
    return out


def appended_text(rc):
    """What the check appends to a row's `why`: its warning, else its note, else nothing."""
    if not isinstance(rc, dict):
        return None
    return rc.get("warning") or rc.get("note") or None


def append_warning(why, text):
    """``why`` with ``text`` appended the way the other warnings are (". " between)."""
    if not text:
        return why
    if not why:
        return text
    return str(why) + ". " + text


def append_to_rows(rows):
    """Append each row's recent-check text to its `why`, in place. Reads and changes nothing else."""
    for r in rows or []:
        if isinstance(r, dict) and isinstance(r.get("recent_check"), dict):
            txt = appended_text(r["recent_check"])
            if txt:
                r["why"] = append_warning(r.get("why"), txt)
    return rows
