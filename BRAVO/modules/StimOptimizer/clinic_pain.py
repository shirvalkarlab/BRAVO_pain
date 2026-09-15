"""The lab's clinic and at-home testing workbooks, read as a SECOND, INDEPENDENT pain stream.

WHY THIS EXISTS. The PI's decision of 2026-09-14: "Import all in-clinic AND at-home testing
visits. Pull the in-clinic numbers separately (not in REDCap) as an independent data stream for
system optimization (critical)." Today the pain posterior (`routines.objective.build_objective`,
`StimOptimizer.stage1_openloop.run_stage1`) sees only REDCap reports matched to device exposure
epochs (`StimOptimizer.adapter.build_design_matrix`). `ClosedLoopDeployment.clinic_steps` already
documents these same workbooks and their five parsing traps, but it parses only the AMPLITUDE
steps for the ramp/settling-window analysis -- it never reads the patient's verbal pain scores.
This module reads those pain scores and turns them into an epoch-level table shaped exactly like
what `objective.build_objective` and `stage1_openloop.run_stage1` already consume, so the SAME
per-rate two-input (left current, right current) surfaces used on the REDCap stream can be fitted
on the clinic stream too, kept separate rather than pooled (that pooling choice is the PI's, not
made here).

READ `ClosedLoopDeployment.clinic_steps`'S MODULE DOCSTRING FIRST if you have not: every one of its
five parsing traps has already produced a wrong number in this project, and two of them (the
bilateral-cell convention, the transposed July 2025 sheet) apply here too.

THE DATA. `BRAVO/_pro_dump/clinic_sheets/RCS08/` -- 29 workbooks, one template, `manifest.json`
(gitignored: the patient's own words are in the free-text notes columns of these files, and the
Google Drive export file names on the shared drive carry real names elsewhere in this project; kept
out of the repository for the same reason). In the live container this is
`/usr/src/BRAVO/_pro_dump/clinic_sheets/RCS08/`.

WHAT IS NOT UNIFORM ACROSS THE 29 WORKBOOKS, checked directly with openpyxl on 2026-09-14 rather
than assumed from one example (`clinic_steps.py` trap 2 already warns that orientation is not
uniform; the same is true of the header's exact row and column layout):

  * The header naming row is not always row 11 in the sense of "the next row is data". The newest
    workbook (2026_Sep2) adds a "Stim Set" column and a two-row merged sub-header for a genuine
    numeric side-effect SEVERITY column ("SIDE EFFECT" on the header row, "SCORE" on the row below,
    0-4 on the scale printed on the sheet: 0=none, 1=mild, 2=mild persistent, 3=moderate, 4=avoid),
    followed by a row that is the sheet's own printed warning text, not data. Every other workbook
    has real data starting the row immediately below the header. So columns are matched BY NAME,
    with the typo tolerance `clinic_steps.py` already established ("Timastamp", "PW (ms)" holding
    microsecond values), and a row is skipped as non-data when every one of Amp / Contacts /
    Timestamp / the seven pain columns is empty on it -- which is exactly what a merged-header
    continuation row or a printed-warning row looks like, and what a real data row never is.
  * Column POSITIONS shift workbook to workbook (extra "Stim Set", "Threshold", "sEEG Contacts"
    columns come and go); only the NAMES are stable, and even the names carry per-scribe suffixes
    ("Side Effect? (Aditya)", "Timestamp (Donna)") that are stripped before matching.
  * The three 2025 workbooks named in the task brief (Aug 21, Sep 04, Sep 18) carry only
    Head/Back/Left Leg/Left Foot -- no Overall, no right-side columns -- and Sep 04/Sep 18 use a
    "Verbal" column in the position the newer sheets call "Overall"; treated as the same field.
    Sep 04 also carries the "PW (ms)" and "Timastamp" typos `clinic_steps.py` names, AND scores
    written as strings like "9/10" rather than plain numbers -- parsed as the numerator.
  * July 2025 keeps its step times, amplitudes and pain scores in the NOTES tab, not the (heavily
    transposed) "STIM TESTING" tab -- the PI's own words: "the verbal scores are in the Stim tab,
    with one sheet as an exception in the Notes tab." Parsed separately, `_parse_july_2025_notes`.
    Its rate and pulse width are NOT recovered here (see that function's docstring); every row from
    this file therefore carries `freq_hz`/`pw_us_Left`/`pw_us_Right` as NaN, disclosed rather than
    guessed, and such rows cannot enter a per-rate surface (which groups by rate) -- they still
    count in the file-level totals this module reports.

WHAT THIS MODULE DOES NOT DO. It never converts a bilateral cell the wrong way round (`_split_bilateral`
keeps the house rule: the value before "/" or "&" is LEFT, per `clinic_steps.py` trap 4 and the PI's
2026-09-05 ruling), it never invents a rate or pulse width the sheet did not record, and it never
turns a prose pain description ("Left leg: 8->0") into a number -- such text is counted as
`n_unparsed_prose` and left out of the parsed table entirely.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)

try:
    from modules.CacheStore import store as _cache_store
except ImportError:                                        # pragma: no cover - host spelling
    from CacheStore import store as _cache_store

#: The store kind. RAW: nobody's choice produced these numbers, they are the lab's own testing
#: record -- see `CacheStore.provenance.RAW_KINDS`.
CLINIC_PAIN_KIND = "clinic_pain_steps"

#: Bumped whenever the parsing rule changes, so a stored entry built under an older rule is never
#: served as if it were built under this one (the same discipline every other rule version in this
#: project follows, e.g. `Biomarkers.bravo_service._BAND_SWEEP_RULE_VERSION`).
_RULE_VERSION = "v1_clinic_pain_2026-09-14"

#: The seven pain-site fields this module reports, in the order the task and the sheets themselves
#: use. `overall` also catches the two 2025 workbooks' "Verbal" column and July 2025's "Current
#: verbal pain score" column -- all three name the same single global rating.
PAIN_FIELDS = ("overall", "head", "back", "left_leg", "left_foot", "right_leg", "right_foot")

#: The device's own severity ladder, printed on the newest workbook's boundary row ("0-4; 0=none,
#: 1=mild, 2=mild persistent, 3=moderate, 4=avoid"). Only that one workbook carries a genuine
#: numeric severity column (the two-row "SIDE EFFECT"/"SCORE" header); every other workbook's
#: "Side Effect?" column is free text and is not parsed as a number here.
SIDE_EFFECT_SEVERITY_LABEL = {0: "none", 1: "mild", 2: "mild", 3: "moderate", 4: "severe"}


# =====================================================================================
# Column-name canonicalisation -- BY NAME, never by position (see module docstring).
# =====================================================================================

def _canon_header(text) -> str | None:
    """One header cell's canonical field name, or ``None`` when it names nothing this module
    reads. Typo- and suffix-tolerant: strips a trailing "(Name)" scribe annotation, then matches
    on a stable prefix/exact form."""
    if text is None:
        return None
    t = str(text).strip().lower()
    if not t:
        return None
    t = re.sub(r"\(.*?\)", "", t).strip()
    if not t:
        return None
    if t.startswith("stim set"):
        return "stim_set"
    if t.startswith("group"):
        return "group"
    if "seeg" in t:
        return "seeg_contacts"
    if t.startswith("contacts"):
        return "contacts"
    if t.startswith("amp"):
        return "amp"
    if t.startswith("rate"):
        return "rate"
    if t.startswith("pw"):                          # "PW (us)" / "PW (µs)" / "PW (ms)" (typo trap)
        return "pw"
    if t.startswith("threshold"):
        return "threshold"
    if t.startswith("duration"):
        return "duration"
    if t == "side effect":                           # the bare header of the SCORE sub-column
        return "side_effect_score"
    if t.startswith("side effect"):
        return "side_effect_text"
    if "timastamp" in t or t.startswith("timestamp"):  # "Timastamp" typo trap (clinic_steps.py #3)
        return "timestamp"
    if t.startswith("movement"):
        return "movement"
    if t.startswith("general notes"):
        return "notes"
    if t.startswith("sensing contact"):
        return "sensing_contact"
    if t.startswith("sensing freq"):
        return "sensing_freq"
    if t.startswith("test order"):
        return "test_order"
    if t == "overall" or t == "verbal" or t == "current verbal pain score":
        return "overall"
    if t == "head":
        return "head"
    if t == "back":
        return "back"
    if t == "left leg":
        return "left_leg"
    if t == "left foot":
        return "left_foot"
    if t == "right leg":
        return "right_leg"
    if t == "right foot":
        return "right_foot"
    return None


def _find_header_row(ws, *, search_rows=range(1, 26), max_col=33):
    """The row index (1-based) whose cells canonicalise to the most known fields, requiring at
    least "amp" and "contacts" among them -- the two columns every real Stim Testing tab has
    regardless of which optional columns come and go. Returns ``None`` when no row qualifies
    (the transposed July 2025 sheet, handled separately, never qualifies)."""
    best_row, best_score = None, 0
    for r in search_rows:
        seen = set()
        for c in range(1, max_col + 1):
            v = ws.cell(row=r, column=c).value
            canon = _canon_header(v)
            if canon:
                seen.add(canon)
        if "amp" in seen and "contacts" in seen and len(seen) > best_score:
            best_row, best_score = r, len(seen)
    return best_row


def _column_map(ws, header_row, *, max_col=33) -> dict:
    """``{canonical_name: 1-based column index}`` for the first occurrence of each name."""
    out = {}
    for c in range(1, max_col + 1):
        canon = _canon_header(ws.cell(row=header_row, column=c).value)
        if canon and canon not in out:
            out[canon] = c
    return out


# =====================================================================================
# Value parsing
# =====================================================================================

_NUM_OVER_10 = re.compile(r"^\s*(\d{1,2}(?:\.\d+)?)\s*/\s*10\s*$")
_PLAIN_NUM = re.compile(r"^\s*[-+]?\d{1,3}(?:\.\d+)?\s*$")
_PROSE_SCORE_HINT = re.compile(
    r"(head|back|leg|foot|overall|pain|score)\D{0,15}?\d{1,2}\D{0,6}?(->|→|/\s*10|out of 10)",
    re.I)


def _parse_pain_value(v):
    """A finite float pain score, or ``None``. Handles plain numbers, "N/10" strings (the
    numerator is the score), a real Excel date object that "N/10" was AUTO-CONVERTED into by
    Excel's own text-to-date guessing (see below), and leaves anything else -- including a value
    already handled as prose elsewhere -- unparsed.

    THE DATE-CONVERSION TRAP, found by reading the real workbooks rather than assumed: several
    sheets (confirmed on the September 2025 and June 2026 files) store a pain score of, say, 8 out
    of 10 not as the text "8/10" but as a genuine Excel date -- ``datetime(<some year>, 8, 10)`` --
    because typing "8/10" into an unformatted Excel cell is auto-recognised as a date (month 8, day
    10) rather than kept as text. The day is always 10 in every example found, which is exactly
    what "/10" becoming a date would produce, and the month is always in 1-10 -- so a date whose
    day is 10 and whose month is a valid one-to-ten score is read back as that month number. A
    date that does not fit this shape is left unparsed rather than guessed at.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if np.isfinite(v) else None
    if hasattr(v, "year") and hasattr(v, "month") and hasattr(v, "day"):
        if int(v.day) == 10 and 1 <= int(v.month) <= 10:
            return float(v.month)
        return None
    s = str(v).strip()
    if not s:
        return None
    m = _NUM_OVER_10.match(s)
    if m:
        return float(m.group(1))
    if _PLAIN_NUM.match(s):
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _looks_like_unparsed_prose(*texts) -> bool:
    for t in texts:
        if t and isinstance(t, str) and _PROSE_SCORE_HINT.search(t):
            return True
    return False


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _side_markers(text) -> tuple:
    """Whether ``text`` names the left hemisphere, the right, both (or neither)."""
    if not text:
        return (False, False)
    t = str(text)
    has_l = bool(re.search(r"(?i)^\s*L\b", t)) or bool(re.search(r"(?i)(?<![A-Za-z])L(?=[A-Za-z])", t))
    has_r = bool(re.search(r"(?i)^\s*R\b", t)) or bool(re.search(r"(?i)(?<![A-Za-z])R(?=[A-Za-z])", t))
    return (has_l, has_r)


def _split_bilateral(raw):
    """``(left_raw, right_raw, mode)``. LEFT IS ALWAYS BEFORE THE SEPARATOR (clinic_steps.py trap
    4, the PI's 2026-09-05 ruling), for both the "/" and the "&" forms. A bare scalar is returned
    on both sides under mode ``"scalar"``; the caller resolves which side(s) it really belongs to
    from the contacts field via `_side_markers`."""
    if raw is None:
        return (None, None, "none")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return (raw, raw, "scalar")
    s = str(raw).strip()
    if not s:
        return (None, None, "none")
    m = re.match(r"^L\s*([\-0-9.]+)\s*/\s*R\s*([\-0-9.]+)$", s, re.I)
    if m:
        return (m.group(1), m.group(2), "lr_labeled")
    for sep in ("/", "&"):
        if sep in s:
            parts = s.split(sep, 1)
            if len(parts) == 2:
                return (parts[0].strip(), parts[1].strip(), "pair")
    if _PLAIN_NUM.match(s):
        return (s, s, "scalar")
    return (None, None, "unparsed")


def _assign_amp_sides(raw_amp, contacts_text):
    """(left_mA, right_mA) from a raw Amp cell, LEFT before any separator. A bare scalar is
    assigned to whichever side the contacts text names; when both or neither are named (the common
    case for a 0 mA / SHAM baseline, or a contacts field that carries no L/R marker at all) the
    scalar is applied to BOTH sides, which is the safe reading for a shared/symmetric setting and
    is disclosed as a heuristic in the module docstring."""
    left_raw, right_raw, mode = _split_bilateral(raw_amp)
    if mode in ("none", "unparsed"):
        return (None, None)
    if mode == "scalar":
        has_l, has_r = _side_markers(contacts_text)
        if has_l and not has_r:
            return (_f(left_raw), None)
        if has_r and not has_l:
            return (None, _f(right_raw))
        return (_f(left_raw), _f(right_raw))
    return (_f(left_raw), _f(right_raw))


def _assign_pw_sides(raw_pw, contacts_text):
    left_raw, right_raw, mode = _split_bilateral(raw_pw)
    if mode in ("none", "unparsed"):
        return (None, None)
    if mode == "scalar":
        has_l, has_r = _side_markers(contacts_text)
        if has_l and not has_r:
            return (_f(left_raw), None)
        if has_r and not has_l:
            return (None, _f(right_raw))
        return (_f(left_raw), _f(right_raw))
    return (_f(left_raw), _f(right_raw))


# =====================================================================================
# Per-workbook parsing
# =====================================================================================

@dataclass
class FileCounts:
    file: str
    setting: str
    n_steps: int = 0
    n_with_pain: int = 0
    n_unparsed_prose: int = 0
    n_skipped_no_setting: int = 0


def _infer_setting(title: str) -> str:
    t = title.lower()
    if "at-home" in t or "at home" in t or "home" in t:
        return "home"
    return "clinic"


_SIDE_SECTION_WORDS = re.compile(r"(?i)\bleft\b|\bright\b")


def _row_is_blank_for(ws, r, cmap, max_col):
    keys = ("amp", "contacts", "timestamp", *PAIN_FIELDS)
    for k in keys:
        c = cmap.get(k)
        if c is None:
            continue
        v = ws.cell(row=r, column=c).value
        if v is not None and str(v).strip() != "":
            return False
    return True


def _parse_generic_stim_testing(ws, *, file_title, file_name, sha256, setting, max_col=33):
    rows_out = []
    counts = FileCounts(file=file_name, setting=setting)
    header_row = _find_header_row(ws, max_col=max_col)
    if header_row is None:
        return rows_out, counts, "no header row found (amp+contacts not both present)"
    cmap = _column_map(ws, header_row, max_col=max_col)

    state = dict(amp_L=None, amp_R=None, rate=None, pw_L=None, pw_R=None,
                 contacts=None, duration=None)
    have_ever_set_amp = False
    hemi_section = None  # 'L' / 'R' / None, from a pure section-label row

    max_row = ws.max_row or header_row
    for r in range(header_row + 1, max_row + 1):
        def cell(key):
            c = cmap.get(key)
            return ws.cell(row=r, column=c).value if c is not None else None

        contacts_v = cell("contacts")
        seeg_v = cell("seeg_contacts")
        amp_v = cell("amp")
        rate_v = cell("rate")
        pw_v = cell("pw")
        dur_v = cell("duration")
        ts_v = cell("timestamp")
        notes_v = cell("notes")
        side_text_v = cell("side_effect_text")
        se_score_v = cell("side_effect_score")

        if _row_is_blank_for(ws, r, cmap, max_col):
            continue

        # A pure section-label row: only a Group-ish first cell, text naming a hemisphere, and
        # nothing else populated -- e.g. "Right VIM (Right MD Thal)" on the 2025 single-hemisphere
        # sheets. Updates the bias used to resolve an ambiguous scalar amp/pw below.
        group_v = cell("group")
        only_group_text = (group_v is not None and str(group_v).strip() != ""
                           and all(cell(k) in (None, "") for k in
                                   ("contacts", "amp", "rate", "pw", "timestamp", *PAIN_FIELDS)))
        if only_group_text and _SIDE_SECTION_WORDS.search(str(group_v)):
            low = str(group_v).lower()
            hemi_section = "L" if "left" in low else ("R" if "right" in low else hemi_section)
            continue

        contacts_text = " / ".join(str(x) for x in (contacts_v, seeg_v) if x not in (None, ""))
        bias_text = contacts_text or (hemi_section or "")

        if amp_v not in (None, ""):
            aL, aR = _assign_amp_sides(amp_v, bias_text)
            state["amp_L"], state["amp_R"] = aL, aR
            state["contacts"] = contacts_text or state["contacts"]
            have_ever_set_amp = have_ever_set_amp or aL is not None or aR is not None
            counts.n_steps += 1
        if rate_v not in (None, ""):
            state["rate"] = _f(rate_v)
        if pw_v not in (None, ""):
            pL, pR = _assign_pw_sides(pw_v, bias_text)
            if pL is not None or pR is not None:
                state["pw_L"], state["pw_R"] = pL, pR
        if dur_v not in (None, ""):
            state["duration"] = _f(dur_v)

        pains = {}
        for site in PAIN_FIELDS:
            pv = _parse_pain_value(cell(site))
            if pv is not None:
                pains[site] = pv
        se_score = _parse_pain_value(se_score_v)

        prose = _looks_like_unparsed_prose(notes_v, side_text_v)
        if prose:
            counts.n_unparsed_prose += 1

        if not pains:
            continue

        if state["amp_L"] is None and state["amp_R"] is None and not have_ever_set_amp:
            counts.n_skipped_no_setting += 1
            continue

        counts.n_with_pain += 1
        t_local = ts_v if hasattr(ts_v, "hour") else None
        rows_out.append(dict(
            visit_date=file_title, setting=setting, file=file_name, sha256=sha256,
            row_index=r, t_local=t_local,
            amp_mA_Left=state["amp_L"], amp_mA_Right=state["amp_R"], freq_hz=state["rate"],
            pw_us_Left=state["pw_L"], pw_us_Right=state["pw_R"],
            contacts_raw=state["contacts"], duration_s=state["duration"],
            side_effect_score=se_score,
            overall=pains.get("overall"), head=pains.get("head"), back=pains.get("back"),
            left_leg=pains.get("left_leg"), left_foot=pains.get("left_foot"),
            right_leg=pains.get("right_leg"), right_foot=pains.get("right_foot"),
            notes=notes_v))
    return rows_out, counts, None


_AMP_MA_RE = re.compile(r"([\-0-9.]+)\s*mA", re.I)
_JULY_LEFT_MARK = re.compile(r"starting on l side", re.I)
_JULY_RIGHT_MARK = re.compile(r"switching over to r side", re.I)


def _parse_july_2025_notes(wb, *, file_title, file_name, sha256, setting):
    """The one workbook the PI named as the exception: verbal pain scores live in the "Notes" tab,
    not the (transposed) "STIM TESTING" tab (`ClosedLoopDeployment.clinic_steps` trap 5). Amplitude
    and contacts are parsed from the "Activity" column's free text ("1.5mA c+2-"); hemisphere comes
    from the two marker phrases in that same column. RATE AND PULSE WIDTH ARE NOT RECOVERED HERE:
    they live on the transposed Stim Testing tab in a shape that would need a timestamp-proximity
    join across two very differently laid out tabs to attach correctly, and the PI's brief for this
    file named only the pain-score exception, not that join -- so `freq_hz`/`pw_us_Left`/
    `pw_us_Right` are NaN on every row from this file, which is disclosed in the verification
    report rather than guessed at."""
    if "Notes" not in wb.sheetnames:
        return [], FileCounts(file=file_name, setting=setting), "no Notes tab"
    ws = wb["Notes"]
    header_row = None
    cmap = {}
    for r in range(1, 6):
        seen = {}
        for c in range(1, min(ws.max_column or 20, 20) + 1):
            v = ws.cell(row=r, column=c).value
            if v is None:
                continue
            t = str(v).strip().lower()
            if t == "time":
                seen["time"] = c
            elif t == "activity":
                seen["activity"] = c
            elif t in ("current verbal pain score",):
                seen["overall"] = c
            elif t == "head":
                seen["head"] = c
            elif t in ("back",):
                seen["back"] = c
            elif t in ("left leg",):
                seen["left_leg"] = c
            elif t in ("left foot",):
                seen["left_foot"] = c
        if "time" in seen and "activity" in seen:
            header_row, cmap = r, seen
            break
    if header_row is None:
        return [], FileCounts(file=file_name, setting=setting), "no Time/Activity header found"

    rows_out = []
    counts = FileCounts(file=file_name, setting=setting)
    hemi = None
    state_amp = None
    state_contacts = None
    max_row = ws.max_row or header_row
    for r in range(header_row + 1, max_row + 1):
        def cell(key):
            c = cmap.get(key)
            return ws.cell(row=r, column=c).value if c is not None else None

        t_local = cell("time")
        activity = cell("activity")
        if isinstance(activity, str):
            if _JULY_LEFT_MARK.search(activity):
                hemi = "L"
            elif _JULY_RIGHT_MARK.search(activity):
                hemi = "R"
            m = _AMP_MA_RE.search(activity)
            if m:
                counts.n_steps += 1
                val = _f(m.group(1))
                contacts_txt = activity[m.end():].strip(" .,-")
                if hemi == "L":
                    state_amp = (val, None)
                elif hemi == "R":
                    state_amp = (None, val)
                else:
                    state_amp = (val, val)
                state_contacts = contacts_txt or state_contacts
            elif isinstance(activity, str) and re.search(r"(?i)^\s*off\s*$", activity):
                counts.n_steps += 1
                state_amp = (0.0, 0.0)

        pains = {}
        for key in ("overall", "head", "back", "left_leg", "left_foot"):
            pv = _parse_pain_value(cell(key))
            if pv is not None:
                pains[key] = pv
        if not pains:
            continue
        if state_amp is None:
            counts.n_skipped_no_setting += 1
            continue
        counts.n_with_pain += 1
        t_l = t_local if hasattr(t_local, "hour") else None
        rows_out.append(dict(
            visit_date=file_title, setting=setting, file=file_name, sha256=sha256,
            row_index=r, t_local=t_l,
            amp_mA_Left=state_amp[0], amp_mA_Right=state_amp[1], freq_hz=None,
            pw_us_Left=None, pw_us_Right=None,
            contacts_raw=state_contacts, duration_s=None, side_effect_score=None,
            overall=pains.get("overall"), head=pains.get("head"), back=pains.get("back"),
            left_leg=pains.get("left_leg"), left_foot=pains.get("left_foot"),
            right_leg=None, right_foot=None, notes=None))
    return rows_out, counts, None


def _visit_date_from_title(title: str):
    """The visit calendar date, California wall-clock, from the title's own MM_DD_YY (or
    MM_DD_YYYY). Returns ``None`` when the title carries no parseable date -- callers keep the
    title string for `visit_date` regardless; this is only for sorting/grouping."""
    m = re.search(r"(\d{1,2})_(\d{1,2})_(\d{2,4})", title)
    if not m:
        return None
    mo, da, yr = (int(x) for x in m.groups())
    if yr < 100:
        yr += 2000
    try:
        return pd.Timestamp(year=yr, month=mo, day=da, tz="America/Los_Angeles")
    except ValueError:
        return None


def parse_workbook(path) -> pd.DataFrame:
    """One workbook -> one DataFrame, one row per step-with-a-pain-score. Columns: see the module
    docstring's task-facing summary; also carries `.attrs["counts"]` (a `FileCounts`) and
    `.attrs["error"]` (a reason string, or ``None``) for the per-file report."""
    import openpyxl

    path = str(path)
    file_name = path.rsplit("/", 1)[-1]
    with open(path, "rb") as fh:
        sha256 = hashlib.sha256(fh.read()).hexdigest()
    title = file_name.rsplit(".", 1)[0]
    setting = _infer_setting(title)

    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    try:
        is_july_2025 = "july 2025" in title.lower() or "07_30_25" in title
        stim_tab = next((n for n in wb.sheetnames if "stim testing" in n.lower()), None)
        if is_july_2025 and stim_tab and "notes" in [n.lower() for n in wb.sheetnames]:
            rows_out, counts, err = _parse_july_2025_notes(
                wb, file_title=title, file_name=file_name, sha256=sha256, setting=setting)
        elif stim_tab:
            ws = wb[stim_tab]
            rows_out, counts, err = _parse_generic_stim_testing(
                ws, file_title=title, file_name=file_name, sha256=sha256, setting=setting)
        else:
            rows_out, counts, err = [], FileCounts(file=file_name, setting=setting), "no Stim Testing tab"
    finally:
        wb.close()

    cols = ["visit_date", "setting", "file", "sha256", "t_local", "t_utc",
           "amp_mA_Left", "amp_mA_Right", "freq_hz", "pw_us_Left", "pw_us_Right",
           "contacts_raw", "duration_s", "side_effect_score", *PAIN_FIELDS, "notes", "row_index"]
    df = pd.DataFrame(rows_out, columns=cols) if rows_out else pd.DataFrame(columns=cols)
    vdate = _visit_date_from_title(title)
    if len(df):
        if vdate is not None:
            def _combine(t_local):
                if t_local is None:
                    return pd.NaT
                ts = pd.Timestamp(year=vdate.year, month=vdate.month, day=vdate.day,
                                  hour=t_local.hour, minute=t_local.minute,
                                  second=t_local.second,
                                  microsecond=getattr(t_local, "microsecond", 0),
                                  tz="America/Los_Angeles")
                return ts
            df["t_utc"] = df["t_local"].map(_combine)
            df["t_utc"] = pd.to_datetime(df["t_utc"], utc=True)
        df["visit_date_ts"] = vdate
    else:
        df["visit_date_ts"] = pd.NaT
    df.attrs["counts"] = counts
    df.attrs["error"] = err
    return df


def parse_folder(folder) -> tuple:
    """Every workbook in ``folder`` (the template excluded) -> ``(steps_df, manifest_df)``.

    ``manifest_df`` is one row per file with the per-file counts (`n_steps`, `n_with_pain`,
    `n_unparsed_prose`, `n_skipped_no_setting`) and any parse error, so a caller can print exactly
    what happened per file without re-opening anything.
    """
    import glob
    import os

    files = sorted(glob.glob(os.path.join(str(folder), "*.xlsx")))
    files = [f for f in files if "_Template_" not in os.path.basename(f)]

    frames = []
    manifest_rows = []
    for f in files:
        try:
            df = parse_workbook(f)
        except Exception as exc:                                   # noqa: BLE001
            _log.warning("clinic_pain: could not parse %s: %r", f, exc)
            manifest_rows.append(dict(file=os.path.basename(f), setting=_infer_setting(f),
                                      n_steps=0, n_with_pain=0, n_unparsed_prose=0,
                                      n_skipped_no_setting=0,
                                      error=f"{type(exc).__name__}: {exc}"))
            continue
        counts = df.attrs.get("counts")
        manifest_rows.append(dict(
            file=counts.file, setting=counts.setting, n_steps=counts.n_steps,
            n_with_pain=counts.n_with_pain, n_unparsed_prose=counts.n_unparsed_prose,
            n_skipped_no_setting=counts.n_skipped_no_setting, error=df.attrs.get("error")))
        if len(df):
            frames.append(df)

    steps = (pd.concat(frames, ignore_index=True) if frames
            else pd.DataFrame(columns=["visit_date", "setting", "file", "sha256", "t_local",
                                       "t_utc", "amp_mA_Left", "amp_mA_Right", "freq_hz",
                                       "pw_us_Left", "pw_us_Right", "contacts_raw", "duration_s",
                                       "side_effect_score", *PAIN_FIELDS, "notes", "row_index",
                                       "visit_date_ts"]))
    manifest = pd.DataFrame(manifest_rows)
    return steps, manifest


# =====================================================================================
# The epoch-level frame `objective.build_objective` / `stage1_openloop.run_stage1` consume.
# =====================================================================================

#: How long a delivered, non-zero current must have run before the safety model counts it as
#: TOLERATED evidence (`safety_ceiling.tolerated_anchors`). The module-wide default,
#: `stage1_openloop.MIN_TOLERATED_H` = 72 hours, describes the chronic REDCap stream, where an
#: epoch spanning days is what "sustained without incident" means. A clinic-sheet step is a
#: supervised test lasting tens of seconds to a few minutes (`ClosedLoopDeployment.clinic_steps`'s
#: own settled window is 30 s), so 72 hours would make every clinic epoch count as UNTESTED and
#: leave the safety model with no tolerated anchor at all -- exactly the failure
#: `surrogate.SafetyGP.seed_from_history` refuses outright ("need at least one tolerated anchor
#: AND one limit anchor"). A clinic step that ran for at least this long, under direct clinical
#: supervision, with the patient free to report a problem, is the honest analogue of "tolerated"
#: at this stream's own timescale; 0.001 h (3.6 s) is below every real settled window this record
#: holds, so it excludes only a step whose own duration was not recorded at all (0 or NaN).
CLINIC_MIN_TOLERATED_H = 0.001

#: Rounding applied to (rate, amp-Left, amp-Right, pw-Left, pw-Right) before two steps are treated
#: as "the same setting" for the purposes of pooling a within-setting variance. Coarser than raw
#: float equality so a 1.599999 vs 1.6 reading from two different cells does not spuriously split
#: one setting into two.
_SETTING_NDIGITS = 2


def epoch_frame_from_steps(steps: pd.DataFrame, *, primary_item="left_leg") -> pd.DataFrame:
    """One row per DISTINCT (rate, amp-Left, amp-Right, pw-Left, pw-Right) setting actually
    observed in the clinic stream -- "each sheet step is one epoch" in the sense that this frame
    is built at the clinic visit's own grain rather than aggregated into REDCap-style multi-day
    epochs, but a setting tested more than once (the same combination repeated, whether inside one
    visit or across several) becomes ONE epoch with ``n`` = how many times, so
    ``routines.objective.pooled_within_epoch_var`` has something to pool where the record repeats
    a setting. Columns match the "acute clinic-testing frame" `routines.objective.ITEM_COLUMNS`
    already names (`pain_Overall`, `pain_Left_Leg`, ...), each on its native 0-10 scale, so
    `objective.build_objective`'s own item resolution finds them with no rescaling.
    """
    if len(steps) == 0:
        return pd.DataFrame()

    d = steps.copy()
    for c in ("freq_hz", "amp_mA_Left", "amp_mA_Right", "pw_us_Left", "pw_us_Right"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    # A setting needs a rate and at least one current to enter a per-rate surface at all.
    d = d.dropna(subset=["freq_hz"])
    d = d[(d["amp_mA_Left"].notna()) | (d["amp_mA_Right"].notna())]
    if len(d) == 0:
        return pd.DataFrame()
    d["amp_mA_Left"] = d["amp_mA_Left"].fillna(0.0)
    d["amp_mA_Right"] = d["amp_mA_Right"].fillna(0.0)
    d["pw_us_Left"] = d["pw_us_Left"]
    d["pw_us_Right"] = d["pw_us_Right"].fillna(d["pw_us_Left"])
    d["pw_us_Left"] = d["pw_us_Left"].fillna(d["pw_us_Right"])

    key_cols = ["freq_hz", "amp_mA_Left", "amp_mA_Right", "pw_us_Left", "pw_us_Right"]
    for c in key_cols:
        d[f"_k_{c}"] = d[c].round(_SETTING_NDIGITS)

    item_col = {"overall": "pain_Overall", "head": "pain_Head", "back": "pain_Back",
               "left_leg": "pain_Left_Leg", "left_foot": "pain_Left_Foot",
               "right_leg": "pain_Right_Leg", "right_foot": "pain_Right_Foot"}

    rows = []
    for i, (key, sub) in enumerate(d.groupby([f"_k_{c}" for c in key_cols], dropna=False)):
        row = dict(epoch=float(i), freq_hz=float(sub["freq_hz"].iloc[0]),
                   amp_mA_Left=float(sub["amp_mA_Left"].iloc[0]),
                   amp_mA_Right=float(sub["amp_mA_Right"].iloc[0]),
                   pw_us_Left=(float(sub["pw_us_Left"].iloc[0])
                              if pd.notna(sub["pw_us_Left"].iloc[0]) else float("nan")),
                   pw_us_Right=(float(sub["pw_us_Right"].iloc[0])
                               if pd.notna(sub["pw_us_Right"].iloc[0]) else float("nan")),
                   n=int(len(sub)), t0=sub["t_utc"].min(),
                   dur_h=float((sub["duration_s"].fillna(0).sum()) / 3600.0),
                   setting=("mixed" if sub["setting"].nunique() > 1 else sub["setting"].iloc[0]),
                   n_visits=int(sub["visit_date"].nunique()),
                   n_clinic=int((sub["setting"] == "clinic").sum()),
                   n_home=int((sub["setting"] == "home").sum()))
        for site, col in item_col.items():
            vals = sub[site].dropna().astype(float)
            row[col] = float(vals.mean()) if len(vals) else float("nan")
            row[f"{col}_sd"] = float(vals.std(ddof=1)) if len(vals) >= 2 else float("nan")
        se = sub["side_effect_score"].dropna()
        if len(se):
            worst = int(round(float(se.max())))
            row["se_severity"] = SIDE_EFFECT_SEVERITY_LABEL.get(
                max(0, min(4, worst)), None)
        else:
            row["se_severity"] = None
        rows.append(row)

    out = pd.DataFrame(rows)
    if not out["dur_h"].gt(0).any():
        out["dur_h"] = 60.0 / 3600.0  # a bare fallback: at least one settled window's worth
    else:
        out.loc[out["dur_h"] <= 0, "dur_h"] = out.loc[out["dur_h"] > 0, "dur_h"].median()
    return out


# =====================================================================================
# The store
# =====================================================================================

def _participant_uid(participant):
    return str(getattr(participant, "uid", participant))


def folder_signature(folder) -> tuple:
    """Identity of the folder's own file set (name + content hash per file, decision 37's
    `source_file_signature` shape) -- never the decoded content, so a re-run over an unchanged
    folder writes nothing (the store's own key-decides rule, decision 26)."""
    import glob
    import hashlib as _hl
    import os

    files = sorted(glob.glob(os.path.join(str(folder), "*.xlsx")))
    files = [f for f in files if "_Template_" not in os.path.basename(f)]
    rows = []
    for f in files:
        with open(f, "rb") as fh:
            h = _hl.sha256(fh.read()).hexdigest()
        rows.append((os.path.basename(f), h))
    rows.sort()
    blob = "|".join(f"{n}~{h}" for n, h in rows).encode("utf8")
    return (CLINIC_PAIN_KIND, _RULE_VERSION, len(rows),
           _hl.blake2b(blob, digest_size=16).hexdigest())


def ingest_and_store(participant, folder, *, root=None) -> dict:
    """Parse ``folder`` and write it as the raw kind `clinic_pain_steps`, keyed on the folder's
    own file set. Re-running with an unchanged folder writes nothing (the key already matches).
    Returns a small report dict: ``{written, n_files, n_steps, n_with_pain, store_key}``.
    """
    uid = _participant_uid(participant)
    sig = folder_signature(folder)

    def build():
        steps, manifest = parse_folder(folder)
        if len(steps) == 0:
            return None
        return {"steps": steps, "manifest": manifest, "folder": str(folder)}

    got, wrote = _cache_store.store_if_absent(
        CLINIC_PAIN_KIND, uid, sig, build,
        writer="clinic_sheet_ingest", trigger="ingest_clinic_sheets", provenance=[],
        n_recordings=sig[2], root=root)
    if got is None:
        return dict(written=False, n_files=0, n_steps=0, n_with_pain=0, store_key=None,
                   reason="no clinic steps parsed from this folder")
    steps = got["steps"]
    return dict(written=bool(wrote), n_files=int(steps["file"].nunique()) if len(steps) else 0,
               n_steps=int(len(steps)), n_with_pain=int(len(steps)),
               store_key=_cache_store.product_key(CLINIC_PAIN_KIND, uid, sig))


def load_clinic_steps(participant, *, consumer=None, root=None):
    """The newest stored clinic-pain-steps table for this participant, or ``None`` with a reason
    when nothing has been ingested yet."""
    uid = _participant_uid(participant)
    got, stamp = _cache_store.load_newest(CLINIC_PAIN_KIND, uid, consumer=consumer, root=root)
    if got is None:
        return None, None, "no clinic sheets have been ingested for this participant yet"
    return got.get("steps"), stamp, None


# =====================================================================================
# The independent per-rate fit
# =====================================================================================

def fit_clinic_rate_strata(participant, *, hemispheres=("Left", "Right"),
                           safety_ceiling_by_hemisphere=None, redcap_pooled_var=None,
                           root=None) -> dict:
    """Fit the SAME per-rate (amp-Left, amp-Right) surfaces `stage1_openloop.run_stage1` fits on
    the REDCap stream, on the clinic stream alone. Never raises: a failure comes back as
    ``{"available": False, "reason": ...}``.

    THIS NEVER POOLS with the REDCap-based fit and never changes the REDCap-based recommendation:
    it is a second, independent read of the same question, exactly as asked for. Whether to pool
    the two streams one day is the PI's call, not made here.
    """
    from . import stage1_openloop as S1
    from .routines import objective as OBJ

    steps, stamp, reason = load_clinic_steps(participant, consumer="stim_optimizer", root=root)
    if steps is None or len(steps) == 0:
        return dict(available=False, reason=reason or "no clinic steps stored", n_files=0,
                   n_steps=0, n_with_pain=0, n_unparsed_prose=0, visit_dates=[], store_key=None)

    ep = epoch_frame_from_steps(steps, primary_item="left_leg")
    n_files = int(steps["file"].nunique())
    visit_dates = sorted(str(v) for v in steps["visit_date"].dropna().unique())
    n_clinic = int((steps["setting"] == "clinic").sum())
    n_home = int((steps["setting"] == "home").sum())
    base = dict(available=True, n_files=n_files, n_steps=int(len(steps)),
               n_with_pain=int(len(steps)), n_unparsed_prose=None, visit_dates=visit_dates,
               n_clinic=n_clinic, n_home=n_home,
               store_key=(stamp or {}).get("signature_key") if isinstance(stamp, dict) else None)

    if len(ep) == 0 or "pain_Left_Leg" not in ep.columns or ep["pain_Left_Leg"].notna().sum() < 2:
        base.update(available=False,
                   reason="fewer than two Left Leg pain readings with a usable setting could be "
                          "built from the stored clinic steps")
        return base

    ep = ep.dropna(subset=["pain_Left_Leg", "pain_Left_Leg_sd"], how="all")
    ep = ep[ep["pain_Left_Leg"].notna()].reset_index(drop=True)
    ep["epoch"] = np.arange(len(ep), dtype=float)

    try:
        own_pooled = OBJ.pooled_within_epoch_var(ep, "pain_Left_Leg_sd", "n", min_n=3)
        pooled_var_used, pooled_source = own_pooled, "clinic_own"
        note = (f"the clinic stream's own pooled within-setting variance "
               f"({own_pooled:.4f}) was estimable and used")
    except ValueError:
        if redcap_pooled_var is not None and np.isfinite(redcap_pooled_var):
            pooled_var_used, pooled_source = float(redcap_pooled_var), "redcap_fallback"
            note = ("the clinic stream has no setting repeated at least 3 times, so its own "
                   f"pooled variance could not be estimated; the REDCap stream's pooled "
                   f"variance ({redcap_pooled_var:.4f}) was used instead")
        else:
            pooled_var_used, pooled_source = 1.0, "hardcoded_fallback"
            note = ("neither the clinic stream nor the REDCap stream had an estimable pooled "
                   "variance; a nominal value of 1.0 NRS^2 was used so the fit could still run")

    try:
        s1 = S1.run_stage1(ep, hemispheres=hemispheres, primary_item="left_leg",
                          safety_ceiling_by_hemisphere=safety_ceiling_by_hemisphere,
                          pooled_var_override=pooled_var_used,
                          min_tolerated_h=CLINIC_MIN_TOLERATED_H)
    except Exception as exc:                                        # noqa: BLE001
        base.update(available=False, reason=f"the clinic-stream fit failed: "
                                            f"{type(exc).__name__}: {exc}")
        return base

    base.update(n_epochs=int(len(ep)), pooled_var=pooled_var_used, pooled_var_source=pooled_source,
               note=note, incumbent_epoch=float(s1.frozen.incumbent_epoch),
               incumbent_rate_hz=float(s1.frozen.incumbent_rate_hz))
    return dict(base, stage1_result=s1)
