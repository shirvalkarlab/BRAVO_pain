"""Phase 0: one joined epoch-level table that every downstream estimator reads.

This is plumbing, and the module plan calls it the highest-value item precisely because it is
plumbing: before it existed each estimator built its own near-miss of the same join, so two panels
could disagree about what the brain was doing at a given moment and neither was obviously wrong.

The table is keyed on (session, channel, setting epoch) and carries, for every scanned band, BOTH
power scales, the delivered stimulation settings per hemisphere, the stimulation era, and the
matched pain report.

THE ONE SUBTLETY WORTH READING BEFORE USING THIS. The stored spectral matrix holds LOG power per
frequency bin. Band power on the linear scale is the ARITHMETIC mean of the linear bin powers, and
the arithmetic mean of linear values is not the exponentiated mean of their logarithms — that is the
GEOMETRIC mean, which is systematically smaller and differently weighted whenever the bins are
unequal. This is not a pedantic distinction here: rule D11 records that the device computes LFP
Power as a linear sum of squared magnitude rather than a log quantity, so the linear scale is the
device-relevant one, while the biomarker pipeline validated its bands on the log scale. Both are
therefore computed and carried side by side under names that say which is which, so a downstream
estimator can never silently take the wrong one, and so the question of whether the scale changes
the winner can actually be answered rather than assumed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import logging as _logging
import os as _os
import pickle as _pickle
import re as _re
import threading as _threading

import numpy as np
import pandas as pd

from ClosedLoopDeployment import edges as _edges

try:                                                    # host runner: BRAVO/modules is the root
    from Biomarkers.routines import sweep_settings as _sweep_settings
except ImportError:                                     # pragma: no cover - container spelling
    from modules.Biomarkers.routines import sweep_settings as _sweep_settings

_log = _logging.getLogger(__name__)

#: THE PAIN SCORES THIS PAGE CAN BE COMPUTED ON: the Biomarkers heat maps' own list, read from its
#: one home (`sweep_settings.BIOMARKER_METRICS`), never copied (the PI, 2026-09-25 night: nothing on
#: the Closed-Loop page is computed on NRS alone). NRS stays the default for a request that names
#: none, which is what every request sent before the dropdown existed.
PAIN_SCORE_KEYS = tuple(m["key"] for m in _sweep_settings.BIOMARKER_METRICS)
PAIN_SCORE_LABELS = {m["key"]: m["label"] for m in _sweep_settings.BIOMARKER_METRICS}
DEFAULT_PAIN_SCORE = _sweep_settings.DEFAULT_BIOMARKER_METRIC


def pain_score_from_request(request_data):
    """The pain score the report is computed on, from the request's ``PainScore``.

    Returns ``{key, label, requested, fell_back_to_nrs, reason}``: a key outside the heat maps' list
    is refused by name and NRS used, and a request that names none says so, so the page can print
    which score it is looking at rather than assume."""
    requested = (request_data or {}).get("PainScore")
    if requested in PAIN_SCORE_LABELS:
        return {"key": requested, "label": PAIN_SCORE_LABELS[requested], "requested": requested,
                "fell_back_to_nrs": False, "reason": None}
    reason = ("no pain score was sent with the request, so NRS was used" if not requested else
              f"the pain score {requested!r} is not one of the heat maps' choices "
              f"({', '.join(PAIN_SCORE_KEYS)}), so NRS was used")
    return {"key": DEFAULT_PAIN_SCORE, "label": PAIN_SCORE_LABELS[DEFAULT_PAIN_SCORE],
            "requested": requested, "fell_back_to_nrs": True, "reason": reason}


def stability_request_body(participant_uid, channel, center_hz, band_width_hz, *, pain_score):
    """The request the stability card sends the Biomarkers test: the band, and the pain score as
    that module's own ``LabelMetric``, so the per-state odds ratios are on the chosen score."""
    return {"ParticipantId": participant_uid, "Channel": channel, "CenterHz": float(center_hz),
            "BandWidthHz": float(band_width_hz), "LabelMetric": pain_score}


def design_matrix_with_pain_score(participant, design_matrix, epochs, pain_score):
    """The per-setting design matrix with a column for ``pain_score``, and a note when one cannot be
    made (None otherwise).

    The design matrix carries the reported scores (``nrs``, ``vas``, ``left_leg_vas``,
    ``back_vas``, ``mpq_sum``) but not the composite, which the Biomarkers module blends per pain
    report (each part put in units of its own scatter, the parts present averaged). For the
    composite that blend is done by the Biomarkers module's own function on the same reports, and
    the per-report values are averaged per setting by the same rule as every other score
    (``StimOptimizer.adapter.attach_pros``, the same wash-in minutes). Built per request and never
    saved: it is a pain rating (CLAUDE.md section 8 rule 5).
    """
    if design_matrix is None or not len(design_matrix) or pain_score in design_matrix.columns:
        return design_matrix, None
    if pain_score != _sweep_settings.COMPOSITE_METRIC:
        return design_matrix, (f"the settings table carries no {pain_score!r} ratings, so no "
                               f"reading on that score could be made")
    try:
        from modules.Biomarkers import bravo_service as _bs
    except ImportError:                                   # pragma: no cover - host spelling
        from Biomarkers import bravo_service as _bs
    try:
        from StimOptimizer import adapter as _sa
    except ImportError:                                   # pragma: no cover
        from modules.StimOptimizer import adapter as _sa
    pro_df = _bs._load_pros({}, participant)
    if pro_df is None or not len(pro_df):
        return design_matrix, "no pain reports could be read for the composite"
    blended, metric, _parts = _bs._resolve_biomarker_metric({"LabelMetric": pain_score}, pro_df)
    if metric != pain_score:
        return design_matrix, ("the composite could not be formed: neither of its parts varies "
                               "in the reports")
    washin = (_sa.build_design_matrix.__kwdefaults__ or {}).get("washin_min", 1.0)
    per_setting = _sa.attach_pros(epochs, blended, _bs._pro_times_utc_series(blended),
                                  washin_min=washin, items=(pain_score,))
    if per_setting is None or not len(per_setting):
        return design_matrix, "no pain report fell inside a setting for the composite"
    cols = ["epoch", pain_score, f"{pain_score}_sd", f"{pain_score}_n"]
    out = design_matrix.merge(per_setting[[c for c in cols if c in per_setting.columns]],
                              on="epoch", how="left")
    return out, None

#: The scanned band centres and width used throughout this project.
DEFAULT_BAND_CENTERS_HZ = tuple(float(x) for x in np.arange(10.5, 28.0, 1.0))
DEFAULT_BAND_WIDTH_HZ = 5.0

#: Stimulation era boundaries in mA, shared with the Biomarkers stability test so the two modules
#: cut the amplitude axis in the same place.
ERA_OFF_MAX_MA = 0.1
ERA_LOW_MAX_MA = 1.5


#: The settings columns have been spelled two ways in this codebase: ``amp_Left`` in the raw pivot
#: and ``amp_mA_Left`` in the exposure-epoch frame that callers actually receive. Accepting only one
#: of them is how the Phase 0 table silently came back with no amplitude at all — the join succeeded,
#: every downstream edge reported "no estimable band", and nothing raised. The canonical spelling
#: emitted by this module is the one with units, matching StimOptimizer.
_AMP_NAMES = ("amp_mA_{h}", "amp_{h}")
_PW_NAMES = ("pw_us_{h}", "pw_{h}")


def resolve_setting_column(columns, kind, hemisphere):
    """First matching spelling of a settings column, or None. ``kind`` is 'amp' or 'pw'."""
    names = _AMP_NAMES if kind == "amp" else _PW_NAMES
    for pat in names:
        c = pat.format(h=hemisphere)
        if c in columns:
            return c
    return None


def canonical_amp_col(hemisphere):
    return f"amp_mA_{hemisphere}"


def _era(amp):
    if amp is None or not np.isfinite(amp):
        return None
    if amp < ERA_OFF_MAX_MA:
        return "OFF"
    return "LOW" if amp <= ERA_LOW_MAX_MA else "HIGH"


def _era_column(amp):
    """``_era``, decided for a whole column of currents in one pass instead of once per row.

    Speed-up proposal 5 of ``artifacts/research_2026-09-25_options/06_remaining_speed_ups.md``:
    the joined table called ``_era`` about 11 million times (10,996,416 on RCS08) building the
    ``era_Left`` / ``era_Right`` columns, one Python call per row. Every row is decided by the same
    two comparisons against the same two constants (``ERA_OFF_MAX_MA``, ``ERA_LOW_MAX_MA``), so this
    does the three comparisons once over the whole numeric array instead.

    ``amp`` must already be numeric (the callers pass it through ``pd.to_numeric(..., errors="coerce")``
    first, exactly as the row-by-row version did). Returns a plain object array holding the same three
    strings ``_era`` returns, and ``None`` -- never NaN -- wherever ``_era`` would have returned
    ``None`` (missing, or non-finite). An object array is used on purpose rather than a pandas
    ``Categorical`` or a string dtype, so a downstream comparison such as ``T["era_Left"] == "OFF"``
    or ``... is None`` behaves exactly as it did when the column was built from a Python list of
    ``_era`` results.
    """
    a = np.asarray(amp, dtype=float)
    out = np.full(a.shape, None, dtype=object)
    finite = np.isfinite(a)
    out[finite & (a < ERA_OFF_MAX_MA)] = "OFF"
    out[finite & (a >= ERA_OFF_MAX_MA) & (a <= ERA_LOW_MAX_MA)] = "LOW"
    out[finite & (a > ERA_LOW_MAX_MA)] = "HIGH"
    return out


def band_powers(psd, freqs, centers=DEFAULT_BAND_CENTERS_HZ, width=DEFAULT_BAND_WIDTH_HZ):
    """Per-band power from one row's stored spectrum, a dict keyed by band centre: the arithmetic
    mean of the raw bin powers inside the band, the device-comparable quantity (rule D11).

    The stored spectrum is raw power (the assembled matrix's ``X``, decision 204). Until
    2026-09-19 it was decibels and this function undid them first; the same day's earlier change
    (decision 202) had already removed the decibel and mean-of-log companions the joined table
    carried, read by nothing. Log power enters no calculation (the PI, 2026-09-19).
    """
    lin_bins = np.asarray(psd, dtype=float)
    f = np.asarray(freqs, dtype=float)
    if lin_bins.shape[0] != f.shape[0]:
        raise ValueError(f"psd has {lin_bins.shape[0]} bins but freqs has {f.shape[0]}")
    out_lin = {}
    half = float(width) / 2.0
    for c in centers:
        m = (f >= c - half) & (f < c + half)
        if not m.any():
            out_lin[c] = np.nan
            continue
        with np.errstate(invalid="ignore"):
            out_lin[c] = float(np.nanmean(lin_bins[m]))
    return out_lin


def _assign_epoch(t_epoch_s, epochs):
    """Setting-epoch index for each PSD timestamp, or -1 when it falls in no epoch.

    Half-open intervals on purpose: a sample landing exactly on a settings change belongs to the NEW
    epoch, because the change had already been programmed when it was recorded.
    """
    t = np.asarray(t_epoch_s, dtype=float)
    out = np.full(t.shape[0], -1, dtype=int)
    if epochs is None or len(epochs) == 0:
        return out
    # Cast explicitly to nanosecond resolution BEFORE taking the integer view. Under pandas 3 a
    # datetime column may carry microsecond resolution, and `.astype("int64")` returns the raw
    # integer in whatever unit the dtype happens to have — so dividing by 1e9 silently produced
    # timestamps a thousand times too small, every sample fell outside every epoch, and the joined
    # table came back empty with no error anywhere. The same resolution-independent idiom is used in
    # Biomarkers/routines/analytics.py for exactly this reason.
    starts = (pd.to_datetime(epochs["t_start"], utc=True).to_numpy()
              .astype("datetime64[ns]").astype("int64") / 1e9)
    ends = (pd.to_datetime(epochs["t_end"], utc=True).to_numpy()
            .astype("datetime64[ns]").astype("int64") / 1e9)
    # THE OPEN-ENDED LAST EPOCH EXTENDS TO +INF (review C9, 2026-09-12). The settings stream's
    # last epoch ends at the newest export's own session time, not at the moment the setting
    # stopped being in force (`StimOptimizer.adapter.exposure_epochs` marks it `open_ended`, and
    # its own `attach_pros` already extends it for the pain reports for exactly this reason). A
    # recording made after that export's session time is still under that setting; treating the
    # end as a wall put it in no epoch, with no amplitude and no row in the joined table. Measured
    # on RCS08 on 2026-09-12: 0 of 304,488 spectra fell there (the newest precedes the last
    # export's session time by 49 s), so on this record the change moves nothing; the rule is
    # kept right for the day a recording lands between two exports.
    open_ended = (epochs["open_ended"].fillna(False).astype(bool).to_numpy()
                  if "open_ended" in epochs.columns else np.zeros(len(epochs), dtype=bool))
    for i, (a, b, oe) in enumerate(zip(starts, ends, open_ended)):
        m = (t >= a) & (t < b) if (np.isfinite(b) and not oe) else (t >= a)
        out[m] = i
    return out


# ---------------------------------------------------------------------------------------------
# PHASE 0 CACHE
# ---------------------------------------------------------------------------------------------
#: The joined table costs ~70 s to build for RCS08 (109,296 rows from 6,072 spectra against 120
#: exposure epochs), and the deployment endpoint rebuilt it on EVERY request — so the live page sat
#: on a spinner for over a minute each time a clinician changed a candidate. Every consumer wants
#: the same table for the same inputs, so it is memoised.
#:
#: WHY THE SIGNATURE IS A CONTENT HASH AND NOT A SHAPE. A cache keyed on row counts would serve a
#: stale table whenever the data changed without changing its size — a corrected amplitude, a
#: re-decoded spectrum, an epoch boundary moving. On a module whose output authorises programming a
#: neurostimulator, serving a stale table is far worse than rebuilding one, so the key folds in the
#: actual VALUES of the columns the join depends on. Hashing 109k rows costs well under a second
#: against the 70 s it saves, which is why the safe choice is also the affordable one.
_JOINED_MEMO = {}
_JOINED_MEMO_LOCK = _threading.Lock()

#: Entries are large (a 109k-row frame), so the memo holds few. Two is enough for the access
#: pattern that matters: a clinician toggling between two candidate configurations on one page.
_JOINED_MEMO_MAX = 2


class MissingFingerprintColumn(KeyError):
    """Raised when a column named in a cache key is not on the frame being hashed.

    This is a loud failure on purpose, and the reason is the whole history of this function. See
    :func:`_frame_fingerprint`.
    """


def _frame_fingerprint(df, columns=(), *, either=(), at_least_one=(), also=()):
    """A content hash of the columns a cached result depends on, plus the frame's row count.

    Four ways of naming columns, because the frames here genuinely differ in which columns they
    carry and the difference between "this column is missing" and "this column does not apply to
    this participant" has to be expressible:

    ``columns``
        Must be on the frame. A missing one raises.
    ``either``
        Groups of alternative spellings of ONE quantity. The first spelling present in each group
        is hashed; a group with none of its spellings present raises. The settings columns really
        do carry two spellings in this codebase (``amp_Left`` in the raw pivot, ``amp_mA_Left`` in
        the frame callers receive), so this is a feature of the data, not a way of tolerating typos.
    ``at_least_one``
        Groups where EVERY present member is hashed and the group as a whole must not be empty.
        This is how the delivered current is named. A participant implanted on one side only has no
        right-hand amplitude column and that is not an error, but a frame with no amplitude column
        at all is the failure that once made the whole joined table come back with no current in it
        while raising nothing, so it raises here.
    ``also``
        Hashed when present, skipped when absent, and either way the outcome is written into the
        key. Pulse width and contact labels belong here: they are worth tracking and they can
        legitimately be absent. The difference from the behaviour this function used to have is
        that the key now says which of these were found, so an absence cannot be mistaken for a
        column that was hashed.

    A NAMED COLUMN THAT IS ABSENT NOW RAISES, AND THAT CHANGE IS THE POINT OF THIS FUNCTION. The
    first version skipped absent columns. It was handed three names that do not exist on the real
    spectral frame ("frequency", "log_power", "center_hz"), so it quietly hashed only ``t`` and
    ``channel``, reported its own mode as "hashed", and then did not change when the spectra
    themselves changed. A recording decoded a second time with the same timestamps would have been
    served the previous result by a cache whose key claimed to be a content hash. A cache that is
    stale while reporting itself verified is worse than having no cache at all, because nobody
    goes looking for the problem. Raising means a mistyped column name is found the first time the
    code runs instead of never.

    THE ARRAY-VALUED COLUMN IS THE OTHER HALF OF THE DIFFICULTY. The spectral frame is one row per
    sample and channel with a whole spectrum held as a numpy array in ``psd`` and its frequency
    axis in ``freqs``. ``pandas.util.hash_pandas_object`` cannot hash a column whose values are
    arrays; it raises, and the first version answered that by giving up on the column, which put
    the frame's shape in the key in place of its contents. Array columns are therefore hashed over
    their raw bytes. If a column still cannot be hashed for some reason not anticipated here, the
    returned key begins with "degraded" and names the column and the failure, so the weakening is
    visible in the key itself rather than hidden inside a key that looks healthy.

    A frame of ``None`` returns a marker rather than raising, because "there is no epoch frame" is
    a legitimate state that must be distinguishable from every real frame.
    """
    if df is None:
        return ("none",)
    have = list(getattr(df, "columns", []))
    have_set = set(have)
    chosen = []
    missing = [c for c in columns if c not in have_set]
    if missing:
        raise MissingFingerprintColumn(
            f"cannot fingerprint on {missing}: not on this frame, which has {sorted(have)}. "
            f"A cache key that silently drops a column it cannot find stops tracking the data "
            f"that column carries.")
    chosen.extend(columns)
    for group in either:
        pick = next((c for c in group if c in have_set), None)
        if pick is None:
            raise MissingFingerprintColumn(
                f"cannot fingerprint: none of the alternative spellings {tuple(group)} is on this "
                f"frame, which has {sorted(have)}.")
        chosen.append(pick)
    for group in at_least_one:
        picks = [c for c in group if c in have_set]
        if not picks:
            raise MissingFingerprintColumn(
                f"cannot fingerprint: the frame carries none of {tuple(group)}, so the quantity "
                f"they hold would go untracked. It has {sorted(have)}.")
        chosen.extend(picks)
    # Recorded whether found or not, so that a later reader of the key can tell an absent optional
    # column from one that was hashed. The old behaviour left absence with no trace at all.
    optional_note = tuple((c, c in have_set) for c in also)
    chosen.extend(c for c in also if c in have_set)
    # A column named in two categories at once would otherwise be hashed twice, which is harmless
    # but makes a key that is confusing to read next to another one. Order is preserved so the key
    # is the same on every run.
    chosen = list(dict.fromkeys(chosen))
    if not chosen:
        raise ValueError("a fingerprint over no columns is a row count wearing the name of a "
                         "content hash; name the columns the cached result depends on")

    parts, degraded = [], []
    for c in chosen:
        col = df[c]
        arr = col.to_numpy()
        first = arr[0] if arr.shape[0] else None
        if isinstance(first, (np.ndarray, list, tuple)):
            try:
                parts.append((c, _bytes_hash_of_array_column(arr)))
            except Exception as exc:
                degraded.append((c, type(exc).__name__))
        else:
            try:
                parts.append((c, int(pd.util.hash_pandas_object(col, index=True).sum())))
            except Exception as exc:
                degraded.append((c, type(exc).__name__))
    # The row count is kept as a cheap extra guard, but the column COUNT deliberately is not:
    # naming an explicit subset is what lets a column added downstream leave a cached result valid,
    # and folding in the width of the frame would undo that without anyone noticing.
    if degraded:
        return ("degraded", int(df.shape[0]), tuple(parts), tuple(degraded), optional_note)
    return ("hashed", int(df.shape[0]), tuple(parts), optional_note)


def _bytes_hash_of_array_column(arr):
    """Hash a column whose values are arrays, over the raw bytes of every value.

    One ``np.stack`` when the arrays all share a length, which is the case for a spectral frame and
    turns the whole column into a single contiguous block of bytes. Ragged values fall back to one
    update per value, which is slower but still hashes every number rather than skipping the
    column. Values are cast to float first so that two columns holding the same numbers in
    different integer widths cannot hash differently and force a needless rebuild.
    """
    h = _hashlib.blake2b(digest_size=16)
    try:
        block = np.stack([np.asarray(v, dtype=float) for v in arr])
        h.update(np.ascontiguousarray(block).tobytes())
        return h.hexdigest()
    except ValueError:                       # ragged: the lengths differ from row to row
        for v in arr:
            h.update(np.ascontiguousarray(np.asarray(v, dtype=float)).tobytes())
        return h.hexdigest()


#: The calibrated frame names each band's power column by its centre: ``band_lsb_26.5`` is the
#: five-hertz band centred on 26.5 Hz, already on the device's own scale. Same rule as
#: ``lfp_evidence.CAL_LSB_PREFIX``; spelled here rather than imported so this module keeps its
#: one-way dependency on the Stim Optimizer routines to call time.
_CAL_LSB_PREFIX = "band_lsb_"
_CAL_NATIVE_PREFIX = "band_native_"
_CAL_CENTER_RE = _re.compile(r"^" + _CAL_LSB_PREFIX + r"(-?\d+(?:\.\d+)?)$")


def calibrated_centres(psd_frame):
    """The band centres a calibrated frame carries, read from its own column names.

    An empty tuple means the frame is the older kind, one whole spectrum per row in ``psd``
    and ``freqs``. Since 2026-09-05 (`90eb109`) ``evidence_inputs`` returns the calibrated kind
    by default, and until this function existed the join and its fingerprint still assumed the
    older one, so the deployment report raised on every candidate and the page showed "the three
    edges have not been estimated". Track G step 1.
    """
    out = []
    for c in getattr(psd_frame, "columns", ()):
        m = _CAL_CENTER_RE.match(str(c))
        if m:
            out.append(float(m.group(1)))
    return tuple(sorted(out))


def _joined_signature(psd_frame, epochs, centers, width):
    # These are the columns lfp_evidence.frame_from_matrix actually emits, and the epoch columns
    # exposure_epochs emits. Both are now required rather than optional, so a rename upstream
    # breaks this loudly instead of narrowing the key to whatever still happens to match. A
    # calibrated frame is hashed over every band column it carries and its tile-quality flags.
    cal = calibrated_centres(psd_frame)
    if cal:
        power_cols = tuple(f"{_CAL_LSB_PREFIX}{c:g}" for c in cal)
        psd_fp = _frame_fingerprint(psd_frame, ("t", "channel", "source", "band_half_hz") + power_cols,
                                    also=("tile_ok", "tile_saturated", "tile_window_s"))
    else:
        psd_fp = _frame_fingerprint(psd_frame, ("t", "channel", "source", "psd", "freqs"))
    return (psd_fp,
            _frame_fingerprint(epochs, ("t_start", "t_end", "freq_hz"),
                               at_least_one=(("amp_mA_Left", "amp_Left",
                                              "amp_mA_Right", "amp_Right"),),
                               also=("pw_us_Left", "pw_us_Right", "cathode_Left",
                                     "cathode_Right", "dur_h", "epoch")),
            tuple(float(c) for c in (centers or ())), float(width))


#: THE ACTUAL BOTTLENECK, measured 2026-09-04 rather than assumed. A stage profile of one
#: deployment report on RCS08 came out as:
#:
#:     StimOptimizer.evidence_inputs          32.96 s
#:     StimOptimizer.build_design_matrix      33.99 s
#:     joined_table (cold)                     2.62 s
#:     edges.actuation_edge                    0.09 s
#:     pipeline.run                            0.05 s
#:
#: so 67 of the 70 seconds are the two input fetches, and the joined table — which I had assumed
#: was the problem and cached first — is 4% of the request. Both fetches re-read and re-decode the
#: same recordings from the database on every request, and both are pure functions of the recording
#: set, so both are memoised here.
#:
#: THE KEY IS THE RECORDING SET, NOT A TIMER. An expiry-based cache would serve a stale plot for
#: however long the window lasts, and this project has already lost a session to exactly that class
#: of confusion — a frozen Biomarkers plot whose cause was un-ingested files rather than a bad
#: cache. Keying on the identity of every recording means a new ingest invalidates immediately and
#: nothing else does.
_INPUTS_MEMO = {}
_INPUTS_MEMO_LOCK = _threading.Lock()
_INPUTS_MEMO_MAX = 2


# ---------------------------------------------------------------------------------------------
# THE SAME CACHE, SHARED BETWEEN THE SERVER'S WORKER PROCESSES AND ACROSS RESTARTS
# ---------------------------------------------------------------------------------------------
#: WHY A FILE AND NOT JUST THE MEMO ABOVE. The memo lives in one process's memory, and the server
#: runs FOUR worker processes (boot.sh caps gunicorn at four; sixteen exhausted the lab machine's
#: memory). Two requests from the same page can land on two different workers, so the memo alone
#: makes "computed once" true per worker and not per participant: the first request to each worker
#: pays the full build, and there are four workers. The development server also runs
#: with reload enabled, so every edit to any Python file replaces all four workers and throws the
#: memo away again. That is why the endpoint could still feel slow after the memo went in.
#:
#: THE MEASUREMENT THAT DECIDED THIS, taken on RCS08 through the bridge on 2026-09-06. Building the
#: inputs from the database takes 71.66 s. The same objects pickle to 5.5 MB, write in 0.01 s and
#: read back in 0.01 s. So a worker that finds the file does in a hundredth of a second what would
#: otherwise take over a minute, and the file costs a rounding error to produce. Nothing about this
#: is a close call.
#:
#: WHAT IS DELIBERATELY NOT DONE HERE. There is no expiry time. An expiry-based cache serves a
#: stale answer for however long the window lasts and then hides the fact by fixing itself, and
#: this project has already lost a session to that class of confusion. The file is keyed on the
#: same content signature as the memo, so a new ingest replaces it immediately and nothing else
#: does. There is also no attempt to share the joined table this way: it rebuilds in 2.66 s, which
#: is 3.6% of a cold request, and putting a 112,068-row frame through a file for that saving is not
#: worth the extra thing that can go wrong.
#: ===========================================================================================
#: THE STORE ITSELF NOW LIVES IN ONE PLACE: `modules/CacheStore/store.py`.
#:
#: This module used to carry a full second copy of the mechanism that `Biomarkers/bravo_service.py`
#: also carried — its own directory resolver, loader, writer, event counters and lock. The two
#: shared a root by construction accident rather than by design, and the per-entry limits differed
#: by exactly a factor of four: 268,435,456 bytes here against 1,073,741,824 there, for no stated
#: reason. The shared store uses the LARGER — but for HEADROOM rather than refusal, and an earlier
#: version of this note had the arithmetic wrong. 268,435,456 bytes is 256 MiB, so this module's
#: cap would NOT have refused the 245.90 MB biomarker tile entry; it leaves 4 to 9 percent to
#: spare. Single-digit headroom on the one entry the cache exists to hold is the reason to raise
#: it, because crossing a limit is SILENT: the write is refused, the tiles stay in one worker's
#: memory, and the page becomes slow again with nothing a reader would look at.
#:
#: What is left below is a thin delegation. The names are kept because this module's tests and two
#: bridge scripts call them. The guard recorded in the old `shared_cache_stats` — skip a file that
#: has gone rather than raising, because one of four workers can be clearing the directory while
#: another is reporting on it — is kept, and now applies to every module rather than this one.
#:
#: THE TWO ENTRIES HERE REBUILD ONCE after this change, because their file naming moved. That
#: costs about 0.4 s: this endpoint is served entirely from the biomarker tile file and makes zero
#: decode calls. The tile entry itself was NOT re-homed, precisely because rebuilding it costs 37
#: seconds and 245.90 MB of it is already on disk.
#: ===========================================================================================
# THE IMPORT ROOT DIFFERS BETWEEN THE TWO TEST RUNNERS, so both spellings are tried. The
# container puts `/usr/src/BRAVO` on the path, which makes this package `modules.CacheStore`; the
# host suite runs from `BRAVO/modules` with that directory as the root, which makes it
# `CacheStore`. A single spelling breaks one of the two runners at import time, which is how this
# was found.
try:
    from modules.CacheStore import store as _cache_store
except ImportError:                                   # pragma: no cover - depends on the runner
    from CacheStore import store as _cache_store

#: Tests point this at a directory of their own. It is passed THROUGH to the shared store rather
#: than resolved here, so there is still only one resolver.
_SHARED_CACHE_DIR_OVERRIDE = None

#: Refuse to write an entry larger than this. Tests lower it to check the refusal.
_SHARED_CACHE_MAX_BYTES = _cache_store.MAX_BYTES_DEFAULT

#: Part of the file name, so an older file is never read by newer code.
_SHARED_CACHE_FORMAT = _cache_store.FORMAT_VERSION

#: THE SAME OBJECTS the shared store counts into and locks with, bound by reference rather than
#: copied — so a count read here is the count the store actually made.
_SHARED_CACHE_EVENTS = _cache_store._EVENTS
_SHARED_CACHE_LOCK = _cache_store._LOCK

#: Which kinds this module owns. Both live in the same directory under the one root.
_SHARED_KINDS = ("inputs", "response")


def shared_cache_dir():
    """Where this module's shared files go, or None when there is nowhere to put them."""
    return _cache_store.kind_dir("inputs", root=_SHARED_CACHE_DIR_OVERRIDE)


def _shared_path(kind, signature, *, participant_uid=None):
    """The file this signature would be stored at, or None.

    `participant_uid` is optional and defaults to `None` (the store's own "shared" naming) for
    callers with no single participant in scope. When a real value is passed, `CacheStore._stem`
    folds it into the file name too — the signature already made the key unique per participant
    (via `recording_set_signature`), but the STORE's own eviction step, `_sweep_superseded`, only
    ever grouped by this `participant_uid` argument, never by the signature it can't see inside.
    Every caller here used to pass `None`, so every participant's entry of a given kind shared the
    same "shared" eviction group — a write for one participant would remove every OTHER
    participant's resident entry of that kind too, not just its own stale ones. See decision 85.
    """
    stem = _cache_store._stem(kind, participant_uid, signature, root=_SHARED_CACHE_DIR_OVERRIDE)
    return None if stem is None else stem + ".pkl"


def _shared_load(kind, signature, *, participant_uid=None, consumer=None):
    """The stored product for this signature, or None. Every failure is a miss, never an error."""
    return _cache_store.load(kind, participant_uid, signature, consumer=consumer,
                             root=_SHARED_CACHE_DIR_OVERRIDE)


def _shared_store(kind, signature, payload, *, participant_uid=None, provenance=None, trigger=None):
    """Write the product where the other worker processes can find it. True if it landed."""
    return _cache_store.store(kind, participant_uid, signature, payload,
                              writer="closed_loop", trigger=trigger or f"{kind}_build",
                              provenance=provenance,
                              root=_SHARED_CACHE_DIR_OVERRIDE,
                              max_bytes=_SHARED_CACHE_MAX_BYTES)


#: ===========================================================================================
#: TRACK D: reading the calibrated grid's stored entry as `consumer="closed_loop"`.
#:
#: D1: the grid (every band centre crossed with every length of signal, for every sensing contact
#: pair) is ALREADY the whole content of `Biomarkers.bravo_service`'s stored `biomarker_band_sweep`
#: entry -- confirmed by reading `analytics.band_time_sweep_from_power`'s own return value, which
#: is one row per band centre times one column per length of signal, per channel, before this track
#: touched anything. No new field was needed for the grid itself; this reader is the only new code
#: D1 needed.
#:
#: `load_newest` (not `load`) is used because this module cannot know the exact settings key
#: Biomarkers built the entry under -- the same reason `StimOptimizer.bravo_service` reads Closed-
#: Loop Deployment's own `amplitude_effect_by_band` table the same way (decision 41,
#: `ARCHITECTURE_cache_store.md` §2 "Reading without the writer's key").
#:
#: D2(b): the two fast columns Biomarkers attaches are `cross_setting_stability_raw` (the
#: untranslated `_validate_band_core` "stim" result) and `device_rules_status` (see
#: `Biomarkers.bravo_service.DEVICE_RULES_STATUS_NOTE` for why no device-rule verdict is attached
#: at all). The honest four-valued TRANSLATION of the raw stability result belongs here, on the
#: Closed-Loop Deployment side, because `stability.py`'s own docstring makes the import direction a
#: hard rule (Biomarkers must never import ClosedLoopDeployment back) -- so Biomarkers stores the
#: raw form and this reader is where `stability.finding_from_stability_result` is actually called,
#: exactly the same call `report_for_participant`'s own inline snippet already makes for one
#: candidate. `ClosedLoopDeployment/tests/test_track_d_grid_stability_translation.py` proves the
#: two are identical.
#: The kind name of the stored cross-setting-stability grid, written by
#: `Biomarkers.bravo_service.compute_and_store_stability_grid`, and the rule its answers are
#: computed under. The card reads an answer only when it was computed under this rule (2026-09-25):
#: the Biomarkers page keys its answers on the rule, and this card, which matches on the grid alone,
#: went on printing the previous rule's answers after P-03 moved it.
#:
#: ONE HOME (2026-09-26): both come from `Biomarkers/routines/sweep_settings.py`, the Django-free
#: file `bravo_service` itself takes them from (importing `bravo_service` here would need Django's
#: app registry, which the host suite does not configure). Until then this module carried pinned
#: copies; `tests/test_track_d_grid_stability_translation.py` now pins that neither side writes its
#: own string again.
STABILITY_GRID_KIND = _sweep_settings.STABILITY_GRID_KIND
STABILITY_GRID_RULE_VERSION = _sweep_settings.STABILITY_GRID_RULE_VERSION


#: The request keys that decide WHICH stored grid the Biomarkers page shows: the pain score and
#: the matching and split settings. The Closed-Loop page sends the same ones (read from the
#: Biomarkers page's own persisted controls), and nothing else from the request reaches the sweep.
#: The clinic-sheet switch (decision 186) was missing until 2026-09-23: the page sent it and this
#: list dropped it, so with sheets on the Biomarkers page this card read the sheets-off grid.
GRID_SETTING_KEYS = ("SweepMetric", "LabelMetric", "MatchToleranceMin", "MatchDirection",
                     "AllowWindowReuse", "LabelStrategy", "PercentileLow", "PercentileHigh",
                     "IncludeClinicSheetRatings")


def _build_grid_through_biomarkers(participant_uid, rd):
    """Build (and store) the calibrated grid exactly as the Biomarkers page would for these
    settings. Its own function so a test can stand in for it; needs Django and the recordings."""
    try:
        from Biomarkers import bravo_service as _bio
    except ImportError:                                          # pragma: no cover
        from modules.Biomarkers import bravo_service as _bio
    return _bio.band_time_sweep_for_participant(dict(rd, ParticipantId=participant_uid,
                                                     BandTimeSweep="1"))


def stored_current_adjusted_grid(participant_uid, request_data=None, *, consumer="closed_loop"):
    """The newest stored grid built WITH the current taken out, under the request's settings, or
    ``{"available": False, "reason": ...}``. READ-ONLY: it never builds (panel C item 6).

    The switch (decision 234) is in the grid's store key but not in its cross-page settings tag, so
    `band_sweep_grid_for_closed_loop` cannot tell the two apart. The sidecar records the switch
    since 2026-09-23 (`extra["adjust_for_stim_current"]`); a grid stored before that date carries
    no flag and is read as plain here, which can only under-report, never mislabel.
    """
    rd = {k: v for k, v in (request_data or {}).items() if k in GRID_SETTING_KEYS}
    try:
        try:
            from Biomarkers.routines import sweep_settings as _sweep_settings
        except ImportError:                                      # pragma: no cover
            from modules.Biomarkers.routines import sweep_settings as _sweep_settings
        want = _sweep_settings.sweep_settings_tag_from_request(rd)
        # Only a grid written under the grid rule in force (decision 317), as below.
        payload, stamp = _cache_store.load_newest(
            _sweep_settings.GRID_KIND, participant_uid, consumer=str(consumer),
            root=_SHARED_CACHE_DIR_OVERRIDE,
            match=lambda meta: ((meta.get("extra") or {}).get("sweep_settings") == want
                                and (meta.get("extra") or {}).get("adjust_for_stim_current") is True
                                and _sweep_settings.grid_written_under_rule_in_force(meta)))
    except Exception as exc:                                     # noqa: BLE001
        _log.warning("reading the stored current-adjusted grid raised for %s", participant_uid,
                     exc_info=True)
        return {"available": False, "reason": f"reading the current-adjusted grid raised {exc!r}"}
    if payload is None:
        return {"available": False,
                "reason": ("no grid with the stimulation current taken out is stored under these "
                           "settings; the Biomarkers page's switch builds one")}
    out = dict(payload)
    out["available"] = True
    out["stamp"] = dict(stamp or {})
    return out


def band_sweep_grid_for_closed_loop(participant_uid, request_data=None, *, consumer="closed_loop"):
    """The calibrated grid the Biomarkers page shows under the SAME pain score and matching and
    split settings, as `consumer="closed_loop"` (or the `consumer` given: the Stim Optimizer reads
    it as "stim_optimizer" for decision 199's pain-relationship half of its readiness rule), with
    every row's stability result translated to the honest four-valued answer. Never raises.

    WHICH ENTRY, 2026-09-11. The store keeps up to twelve grids per participant (decision 107),
    one per score and settings combination, and this used to read the newest of them whatever it
    was built under -- so the card disagreed with the Biomarkers page whenever the daily precompute
    had written another score last (the decision-107 defect met a third time). It now matches the
    newest entry whose sidecar tag equals the tag of the settings in the request
    (`Biomarkers.bravo_service.sweep_settings_tag_from_request`, the same helpers the sweep uses),
    which is the newest grid the Biomarkers page has stored under those settings: a grid that page
    rebuilt for a new pain report or a new ingest supersedes the older one here too. When no stored
    grid matches -- the settings were never used on the Biomarkers page, or the rule version moved
    -- it builds one through the Biomarkers sweep itself (the PI: "fetch each time from the
    Biomarkers latest cache heat-map grid, if it's outdated"), which stores it, and reads that back;
    the response says so (`built_now`). `grid_settings` carries what the served grid was built
    under, for the card to print.
    """
    try:
        from . import stability as _stab
    except ImportError:                                          # pragma: no cover
        from modules.ClosedLoopDeployment import stability as _stab
    rd = {k: v for k, v in (request_data or {}).items() if k in GRID_SETTING_KEYS}
    # The tag comes from the Django-free routine (`routines/sweep_settings.py`) so this works in
    # the host suite too; the Biomarkers service itself is imported only when a grid must be built.
    try:
        try:
            from Biomarkers.routines import sweep_settings as _sweep_settings
        except ImportError:                                      # pragma: no cover
            from modules.Biomarkers.routines import sweep_settings as _sweep_settings
        want = _sweep_settings.sweep_settings_tag_from_request(rd)
    except Exception as exc:                                     # noqa: BLE001
        _log.warning("closed-loop: the grid settings could not be resolved", exc_info=True)
        return {"available": False, "reason": f"the grid settings could not be resolved: {exc!r}"}

    # AND ONLY A GRID WRITTEN UNDER THE GRID RULE IN FORCE (decision 317, 2026-09-26). The rule is
    # inside the grid's key, so the Biomarkers page never serves an older-rule grid, but this reader
    # matches on the tag and went on serving one under any settings that page had not rebuilt (the
    # stability answers' fault, fixed for them in decision 293(b)). An older-rule grid is treated
    # exactly as no grid: the build below, which writes one under the rule in force.
    def _matches(meta):
        return (((meta.get("extra") or {}).get("sweep_settings") or None) == want
                and _sweep_settings.grid_written_under_rule_in_force(meta))

    def _read():
        return _cache_store.load_newest(
            _sweep_settings.GRID_KIND, participant_uid, consumer=str(consumer),
            root=_SHARED_CACHE_DIR_OVERRIDE, match=_matches)

    built_now = False
    try:
        payload, stamp = _read()
    except Exception as exc:                                     # noqa: BLE001
        _log.warning("closed-loop: reading the stored calibrated grid raised for %s",
                     participant_uid, exc_info=True)
        return {"available": False, "reason": f"reading the calibrated grid raised {exc!r}"}
    if payload is None:
        # Nothing stored under these settings: build it the way the Biomarkers page would, which
        # writes it under the tag, then read it back as this module. A build that could not be
        # stored (no report key, say) is served from the response itself and marked as such.
        try:
            fresh = _build_grid_through_biomarkers(participant_uid, rd)
            built_now = True
            payload, stamp = _read()
            if payload is None and isinstance(fresh, dict) and fresh.get("band_time_sweep"):
                payload, stamp = fresh, {"written_utc": None, "extra": {"sweep_settings": want}}
        except Exception as exc:                                 # noqa: BLE001
            _log.warning("closed-loop: building the calibrated grid raised for %s",
                         participant_uid, exc_info=True)
            return {"available": False, "reason": f"building the calibrated grid raised {exc!r}",
                    "grid_settings": dict(want, metric_label=None, stored_utc=None, built_now=True)}
    if payload is None:
        return {"available": False,
                "reason": ("no calibrated grid could be built for this participant under these "
                           "settings; visit the Biomarkers exploration page first"),
                "stamp": stamp, "grid_settings": dict(want, metric_label=None, stored_utc=None,
                                                      built_now=built_now)}
    grid_settings = dict(want)
    grid_settings.update({
        "metric_label": (payload.get("metric_label")
                         or ((stamp or {}).get("extra") or {}).get("metric_label")
                         or _sweep_settings.metric_label(want["sweep_metric"])),
        "stored_utc": (stamp or {}).get("written_utc"),
        "built_now": built_now,
    })

    # THE SECOND SOURCE OF THE STABILITY ANSWER, and in practice the only one that ever fires.
    # `cross_setting_stability_raw` is attached to a row only when the grid was built with
    # `IncludeCrossSettingStability`, which no client has ever set because it made the request pay
    # for every fit inline. The answer is now computed off the request path instead -- after the
    # page's own grid lands, and on a daily schedule -- and stored under its own kind, so this
    # reads that entry and matches it to rows by (channel, band centre).
    #
    # The row's own field still WINS when present: a caller that deliberately asked for the inline
    # computation gets exactly what it asked for, not a stored answer that may have been built
    # under different settings.
    # Read the entry DIRECTLY through the store rather than importing
    # `Biomarkers.bravo_service.load_stored_stability_grid`. That module imports `Server.models`,
    # which needs Django's app registry to be ready -- fine inside a request, but it raises
    # `AppRegistryNotReady` in the host test suite, which does not configure Django. An enhancement
    # to one column must not decide whether this function works at all.
    #
    # The kind name comes from its Django-free home, `Biomarkers/routines/sweep_settings.py`, the
    # same object `bravo_service` writes under (2026-09-26).
    #
    # THE ANSWER FOR THIS GRID, NOT THE NEWEST ONE (2026-09-23). The stability answer depends on the
    # pain score the grid was built for (on RCS08, 3,123 of 5,148 stored values differ between the
    # NRS grid's answer and the Left Leg VAS grid's), and the store keeps one answer per grid. This
    # used to read the newest answer of any grid, so the card could print another score's answer
    # beside its own grid. Each answer's sidecar names its grid's key, and the grid read above
    # carries that same key, so the match is exact; no match means "not tested", never a borrowed
    # answer. An answer written before its sidecar named a grid is never matched.
    #
    # AND ONLY AN ANSWER COMPUTED UNDER THE RULE IN FORCE (2026-09-25). The Biomarkers page files
    # each answer under the stability rule it was computed with, so a new rule is a new key there;
    # this card matched on the grid alone and went on printing the previous rule's answers until the
    # background job rebuilt them (found when P-03 moved the rule to one pain report per block).
    # Two passes: an answer whose sidecar names the rule in force first; failing that, one whose
    # sidecar names no rule (every answer written before this date), accepted only when the rule
    # its own payload carries is the one in force. The Biomarkers side finds those older answers by
    # their exact key and will not rewrite them, so refusing them outright would leave the card on
    # "not tested" until the rule next moves. Any other rule reads "not tested", never borrowed.
    stored_stability = {}
    _grid_key = str(((payload or {}).get("sweep_key") or {}).get("signature_key") or "")
    try:
        _payload = None
        if _grid_key:
            for _sidecar_rule in (STABILITY_GRID_RULE_VERSION, None):
                _payload, _ = _cache_store.load_newest(
                    STABILITY_GRID_KIND, participant_uid, consumer=str(consumer),
                    root=_SHARED_CACHE_DIR_OVERRIDE,
                    match=lambda meta, _r=_sidecar_rule: (
                        (meta.get("extra") or {}).get("sweep_key") == _grid_key
                        and (meta.get("extra") or {}).get("rule_version") == _r))
                if _payload is not None:
                    break
            if (_payload or {}).get("rule_version") != STABILITY_GRID_RULE_VERSION:
                _payload = None
        for _flat, _value in ((_payload or {}).get("points") or {}).items():
            _ch, _, _centre = str(_flat).rpartition("|")
            try:
                stored_stability[(_ch, float(_centre))] = _value
            except (TypeError, ValueError):
                continue
    except Exception:                                            # noqa: BLE001
        # Never fatal: the rows say "not tested". But LOGGED (review C7, 2026-09-12): on this
        # failure every row of the "Choose a band" card's stability column reads the dashed "not
        # tested", indistinguishable from "the background job has not run yet", and nothing else
        # would say which of the two it was.
        _log.warning("closed-loop: the stored stability grid could not be read for %s; every row "
                     "will show 'not tested'", participant_uid, exc_info=True)
        stored_stability = {}

    sweeps = payload.get("band_time_sweep") or {}
    out_sweeps = {}
    any_stability = False
    stability_from_store = 0
    for channel, sweep in sweeps.items():
        band_width_hz = float(sweep.get("band_width_hz", 5.0) or 5.0)
        new_sweep = dict(sweep)
        for key in ("best_correlation_rows", "best_auc_rows"):
            rows = sweep.get(key) or []
            new_rows = []
            for row in rows:
                new_row = dict(row)
                raw = row.get("cross_setting_stability_raw")
                if raw is None and stored_stability:
                    _c = row.get("band_center_hz")
                    if _c is not None:
                        raw = stored_stability.get((str(channel), float(_c)))
                        if raw is not None:
                            stability_from_store += 1
                if raw is not None:
                    any_stability = True
                    # `band_center_hz`, not `center_hz` -- see the note in
                    # `Biomarkers.bravo_service._attach_grid_export_columns` on this same field
                    # name, confirmed by reading a real row live on RCS08.
                    center_hz = row.get("band_center_hz")
                    try:
                        finding = _stab.finding_from_stability_result(
                            raw, channel, float(center_hz) if center_hz is not None else 0.0,
                            band_width_hz=band_width_hz)
                        new_row["cross_setting_stability"] = finding.as_payload()
                    except Exception as exc:                     # noqa: BLE001
                        # Per ROW, so this can repeat. That is the point: if the translation is
                        # raising, it is almost certainly raising for every row, and a log with one
                        # line per row is how someone finds out at all -- the page just shows "not
                        # tested", which is indistinguishable from a band that was never tested.
                        _log.warning("closed-loop: translating the stability answer raised for "
                                     "%s %s at %s Hz", participant_uid, channel, center_hz,
                                     exc_info=True)
                        new_row["cross_setting_stability"] = {
                            "answer": "not tested", "test_ran": False,
                            "reason": f"translation raised {exc!r}"}
                    new_row.pop("cross_setting_stability_raw", None)
                new_rows.append(new_row)
            new_sweep[key] = new_rows
        out_sweeps[channel] = new_sweep

    return {"available": True, "band_time_sweep": out_sweeps, "stamp": stamp,
            "grid_settings": grid_settings,
            "cross_setting_stability_included": any_stability,
            # How many rows got their answer from the stored grid rather than from the row itself.
            # Reported so a reader can tell "the background job has run" from "the request computed
            # it inline", which are different things with different freshness.
            "cross_setting_stability_from_store": stability_from_store}


def shared_cache_stats():
    """What the shared files have done, for the interface and for tests."""
    d = shared_cache_dir()
    files = []
    if d is not None:
        try:
            files = sorted(f for f in _os.listdir(d)
                           if f.endswith((".pkl", ".parquet", ".npz")))
        except OSError:
            files = []
    with _SHARED_CACHE_LOCK:
        events = dict(_SHARED_CACHE_EVENTS)
    # SKIP A FILE THAT HAS GONE RATHER THAN RAISING. There are four worker processes: one can be
    # inside `clear_shared_cache` while another is here, and then asking a removed file for its
    # size raises straight out of a function whose entire job is to report a number for the
    # interface. A statistics call must never be the thing that breaks a page.
    total = 0
    for f in files:
        try:
            total += _os.path.getsize(_os.path.join(d, f))
        except OSError:
            pass
    return {"directory": d, "entries": len(files), "files": files,
            "bytes": total if d else 0,
            "max_bytes_per_entry": _SHARED_CACHE_MAX_BYTES, "events": events}


def clear_shared_cache():
    """Remove every shared file of this module's kinds, including older format versions."""
    removed = 0
    for kind in _SHARED_KINDS:
        removed += _cache_store.clear(kind, root=_SHARED_CACHE_DIR_OVERRIDE)
    with _SHARED_CACHE_LOCK:
        for k in _SHARED_CACHE_EVENTS:
            _SHARED_CACHE_EVENTS[k] = 0
    return removed



def _once_per_request(key, compute):
    """`compute()` once per request, through the within-request memo Biomarkers' `bravo_service`
    module already keeps for the tile key and the decoded recordings (decision 267's
    `_request_memo`) -- the same scope `ClosedLoopDeployment.bravo_service.run_for_participant`
    opens around every request. Computed fresh wherever that scope cannot be reached: the host test
    suite has no `Server` package at all, so `Biomarkers.bravo_service` (the only Django-coupled
    file in that package) fails to import before anything Django-specific runs; and a caller outside
    any request has opened no scope, in which case `_request_memo` itself falls through to
    `compute()`. Any other failure reaching the memo is treated the same way, rather than as a
    reason to fail the caller -- a speed-up must never be able to break a page.
    """
    try:
        from Biomarkers import bravo_service as _bsvc
    except ImportError:                                          # pragma: no cover
        try:
            from modules.Biomarkers import bravo_service as _bsvc
        except Exception:                                        # noqa: BLE001 -- no Django here
            return compute()
    except Exception:                                             # noqa: BLE001
        return compute()
    return _bsvc._request_memo(key, compute)


def recording_set_signature(participant):
    """Identity of every recording that feeds the inputs, so a new ingest invalidates the cache.

    Folds in each recording's own uid and content hash rather than a count or a max date: a
    re-decode that replaces a recording in place changes neither of those, and a count alone would
    also miss a deletion balanced by an insertion.

    Reads only the three columns the signature needs (`uid`, `hashed`, `type`) rather than whole
    Recording objects joined to their source files, and is computed once per request
    (`_once_per_request`): one Closed-Loop request asked for this 10 to 14 times (proposal 1,
    2026-09-25). Measured live on RCS08: the lean query gives the identical answer, about 38 times
    faster (0.017 s against 0.41-0.64 s).
    """
    puid = str(getattr(participant, "uid", participant))

    def _compute():
        from Server import models as _m
        sfs = list(_m.SourceFile.find_all(owner=participant))
        rows = list(_m.Recording.objects.filter(source__in=sfs)
                    .values_list("uid", "hashed", "type"))
        ident = sorted((str(u), str(h), str(t)) for (u, h, t) in rows)
        blob = "|".join("~".join(t) for t in ident).encode("utf8")
        return (puid, len(sfs), len(rows), _hashlib.blake2b(blob, digest_size=16).hexdigest())

    return _once_per_request(("cl_recording_set_signature", puid), _compute)


#: The `inputs` entry's own rule version (decision 215). Bump it when what the entry holds changes
#: for a reason no recording and no constant would show.
#: v3 (2026-09-24): the settings stream the entry reads now starts at the implant date.
#: v4 (2026-09-25): the entry holds the settings stream in place of the design matrix, so no pain
#: rating is saved under a key that a new report cannot move (CLAUDE.md section 8 rule 5).
_INPUTS_RULE_VERSION = "v4_inputs_settings_from_implant_date_no_pain_ratings"


def inputs_signature(participant):
    """The key of the `inputs` store entry: the recording set, the calibration constants in
    effect and this entry's rule version (decision 215).

    The entry's evidence frame carries `band_lsb_<centre>` columns read from the tiles, which are
    keyed on the constants (decision 25); until 2026-09-20 this entry was keyed on the recording
    set alone, so a constant change (decisions 209, 211) left an entry on disk serving LSB computed
    under the old constant until a recording was added or removed.
    """
    from Biomarkers.routines import analytics as _an
    # THE TILE ENTRY'S OWN KEY TOO (decision 289): the frame is read from the saved tiles, and the
    # tiles can change with no recording and no constant moving (the one input set; the implant
    # date). None where no server can be asked, as before.
    return (recording_set_signature(participant), _INPUTS_RULE_VERSION,
            float(_an.LSB_PER_UV2_TRANSFORM), float(_an.LSB_PER_DEVICE_PSD),
            _tiles_key_for(participant))


def evidence_inputs_cached(participant, *, force_refresh=False):
    """``StimOptimizer.evidence_inputs`` memoised with the settings stream, and ``build_design_matrix``
    made fresh from them on every call.

    Returns ``(psd_frame, epochs, design_matrix)``. WHAT IS SAVED IS RECORDING-DERIVED ONLY: the
    evidence frame, the exposure epochs and the settings stream, under the recording set, the
    constants and a rule version. The design matrix carries the pain ratings (``nrs``, ``vas``, ...),
    so it is NOT saved here: saved under this key, a report filed without a new recording would be
    served stale with no visible symptom (CLAUDE.md section 8 rule 5; found 2026-09-25, when the
    saved and a fresh build still agreed). It is built on each call from the saved stream through
    ``build_design_matrix``, whose own saved table is keyed on the settings AND the pain-report
    snapshot, so an unchanged record costs a store read and a new report rebuilds only the match.

    Callers must treat the returned frames as READ-ONLY, or copy before mutating: they are the same
    objects handed to every other caller. That is the same contract the Biomarkers assembled-matrix
    cache imposes.
    """
    from StimOptimizer import adapter as _sa
    sig = inputs_signature(participant)
    # The real participant identity, passed to the store (decision 85) so its own eviction step
    # (`_sweep_superseded`) can tell this participant's stale "inputs" entries apart from every
    # OTHER participant's -- passing `None` here, as every call site used to, put every
    # participant's entry into the store's one undifferentiated "shared" eviction group, so a
    # fresh build for participant A would delete participant B's still-current cached entry too.
    # `str(getattr(participant, "uid", participant))` mirrors `recording_set_signature`'s own
    # derivation immediately above, so both agree on the same identity for the same participant.
    pid = str(getattr(participant, "uid", participant))
    if not force_refresh:
        with _INPUTS_MEMO_LOCK:
            hit = _INPUTS_MEMO.get(sig)
        if hit is None:
            # Nothing in this process's memory, so ask whether another worker process already built
            # it. This is the step that makes the build happen once per participant rather than
            # once per worker per restart.
            shared = _shared_load("inputs", sig, participant_uid=pid, consumer="closed_loop")
            if shared is not None:
                _remember_inputs(sig, shared)
                hit = shared
        if hit is not None:
            psd, eps, stream = hit
            return psd, eps, _sa.build_design_matrix(participant, stream=stream)
    # READ, DECRYPT AND PARSE THE PARTICIPANT'S STORED PERCEPT FILES ONCE, NOT TWICE. Both of the
    # two calls below need the same dated settings stream, and until this line existed each of them
    # built its own copy of it. That meant opening, decrypting and parsing the same 568 stored files
    # a second time for no new information, so 1,136 file reads where 568 would do.
    #
    # MEASURED ON PARTICIPANT RCS08 THROUGH THE BRIDGE ON 2026-09-06, with both this process's
    # memory of the inputs and the shared cache file emptied first so the build was genuinely cold.
    # One pass over the 568 files takes 33.65 seconds. Building the inputs the old way, with each
    # function parsing the files for itself, took 74.13 seconds and then 68.32 seconds on two
    # alternating attempts. Building them with the frame shared, as below, took 35.71 seconds and
    # then 35.08 seconds. That is 38.41 seconds and 33.24 seconds saved. The whole report the page
    # shows went from 76.66 seconds to 41.55 seconds.
    #
    # NOTHING THE PAGE REPORTS MOVED. The three objects this function returns were compared column
    # by column and row by row between the two ways of building them and were identical: the
    # assembled spectra frame at 6,226 rows, the exposure epochs at 123 rows and the epoch-level
    # design matrix at 92 rows. So was the joined table built from them, at 112,068 rows. The whole
    # report was walked value by value, 1,321 values in all, with no differences; running the new
    # way twice over gave no differences either, which is the control that says the report is
    # reproducible run to run and that the comparison therefore means something.
    #
    # SHARING ONE FRAME IS SAFE HERE for two specific reasons, both checked in the tests. Each of
    # those two functions builds that frame identically when nothing is handed in, namely
    # settings_stream(participant) with no other arguments. And neither of them filters, sorts or
    # otherwise alters the frame before using it; both only read from it.
    stream = _sa.settings_stream(participant)
    psd, eps = _sa.evidence_inputs(participant, stream=stream)
    out = (psd, eps, stream)
    _remember_inputs(sig, out)
    _shared_store("inputs", sig, out, participant_uid=pid,
                  provenance=_inputs_provenance(participant, stream, None))
    return psd, eps, _sa.build_design_matrix(participant, stream=stream)


def _inputs_provenance(participant, stream, dm):
    """The chain for the `inputs` bundle: the settings stream's entry, the matched table's entry
    with its own chain when a design matrix is passed (since rule v4 the bundle holds none, so
    none is cited), and the tile entry the sensed frame was read from. Each is cited only when its key is known; a frame built without the
    store has no key and is simply not cited, and the tile key is skipped when the recordings
    identity cannot be built."""
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                   # pragma: no cover - depends on the runner
        from CacheStore import provenance as _prov
    entries = []
    stream_key = getattr(stream, "attrs", {}).get(_cache_store.STORE_KEY_ATTR)
    if stream_key:
        entries.append(_prov.entry(stream_key, kind="therapy_settings", writer="stim_optimizer"))
    dm_key = getattr(dm, "attrs", {}).get(_cache_store.STORE_KEY_ATTR)
    if dm_key:
        chain = []
        try:
            kind, uid, _hash = dm_key.split("/", 2)
            stamp = _cache_store.newest_stamp(kind, uid, root=_SHARED_CACHE_DIR_OVERRIDE) or {}
            chain = stamp.get("provenance") or []
        except Exception:                                 # noqa: BLE001 — the chain is optional
            # Logged (review C7): a shorter chain is what lets the self-derived refusal miss.
            _log.warning("closed-loop: the matched table's provenance chain could not be read "
                         "for %s; the inputs entry cites it without its chain",
                         getattr(participant, "uid", participant), exc_info=True)
            chain = []
        entries.append(_prov.entry(dm_key, kind="therapy_pain_matched", writer="stim_optimizer",
                                   chain=chain))
    try:
        from modules.Biomarkers import bravo_service as _bsvc
        uid = getattr(participant, "uid", participant)
        tiles_sig = _bsvc._raw_lsb_shared_signature(uid, _bsvc._LSB_SPECTRUM_CENTERS)
        if tiles_sig is not None:
            entries.append(_prov.entry(
                _cache_store.product_key(_bsvc._RAW_LSB_SHARED_KIND, uid, tiles_sig),
                kind=_bsvc._RAW_LSB_SHARED_KIND, writer="biomarkers"))
    except Exception:                                     # noqa: BLE001 — no server, no tile key
        _log.warning("closed-loop: the tile entry's key could not be built for %s; the inputs "
                     "entry's provenance omits it", getattr(participant, "uid", participant),
                     exc_info=True)
    return _prov.flatten(entries)


def _remember_inputs(sig, out):
    with _INPUTS_MEMO_LOCK:
        if sig not in _INPUTS_MEMO and len(_INPUTS_MEMO) >= _INPUTS_MEMO_MAX:
            _INPUTS_MEMO.pop(next(iter(_INPUTS_MEMO)), None)
        _INPUTS_MEMO[sig] = out


def inputs_cache_stats():
    with _INPUTS_MEMO_LOCK:
        return {"entries": len(_INPUTS_MEMO), "max": _INPUTS_MEMO_MAX,
                "psd_rows": [0 if v[0] is None else int(v[0].shape[0])
                             for v in _INPUTS_MEMO.values()]}


def clear_inputs_cache(*, shared=False):
    """Empty this process's memory of the inputs, and optionally the shared files too.

    ``shared`` defaults to False so that a test or a script clearing its own process cannot
    accidentally make every other worker process rebuild.
    """
    with _INPUTS_MEMO_LOCK:
        _INPUTS_MEMO.clear()
    if shared:
        clear_shared_cache()


# ---------------------------------------------------------------------------------------------
# HOW MUCH BAND POWER MOVES PER MILLIAMP, FOR EVERY BAND, EVERY ELECTRODE AND EVERY CLINIC VISIT
# ---------------------------------------------------------------------------------------------
#: WHAT THIS CACHE IS FOR, AND WHAT THE MEASUREMENT SAYS ABOUT IT. The PI's request was that the
#: figures relating stimulation current to band power be worked out once and reused, and that only
#: a new in-clinic testing sheet should make them be worked out again. That is what the key here
#: does. It is worth being straight about the size of the saving, measured on RCS08 through the
#: bridge on 2026-09-06: assembling the evidence for every electrode, side and stimulation rate
#: from the 820 parsed clinic steps takes 0.15 s, and fitting all 3,920 single-band regressions
#: that follow takes 1.23 s, so 1.38 s in total. That is real but it is not the reason the
#: deployment page was slow; the two database fetches above account for 94% of a cold request. The
#: honest reason to cache this is that repeating a fit produces no new information, and that having
#: the key already include the sheet contents means the figures cannot be quietly reused after a
#: sheet is edited.
#:
#: THE KEY HASHES THE PARSED STEPS THEMSELVES. Not a row count: an amplitude corrected from 2.5 to
#: 2.0 mA in a sheet leaves the count untouched, and this data has already been re-parsed several
#: times with corrections to the left-and-right convention and to two mis-spelled column headings.
#: Not a file modification date either: the steps arrive here as a frame that has been through a
#: parser, so the date on any file is a date for something other than the values being used, and
#: copying a sheet between folders changes it for no reason at all.
#:
#: The tile power is hashed too, over its bytes, because the same sheet read against re-decoded
#: recordings is a different calculation with the same steps. Whichever recordings contributed is
#: therefore part of the key by way of their contents.
_RESPONSE_MEMO = {}
_RESPONSE_MEMO_LOCK = _threading.Lock()

#: Each entry holds the per-band figures for up to a hundred or so cells, which is small next to
#: the frames above, so a few more entries are affordable here than in the joined-table memo.
_RESPONSE_MEMO_MAX = 4


def clinic_steps_signature(steps):
    """A content hash of the parsed in-clinic testing steps.

    The required columns are the ones the calculation actually reads: the length of each held
    setting, the stimulation rate, and the current delivered. The step time and the visit label are
    each accepted under either of the two spellings this project uses — ``t0`` and ``visit`` on a
    frame prepared for the estimator, ``t_local`` and ``visit_date`` on a frame straight from the
    parser — and one of each must be present. The current is required as a pair in which at least
    one side is present, because a sheet may record one side only, but a sheet recording no current
    at all cannot support this calculation and raising is the right answer. Anything else missing
    raises too, because a key that silently stopped tracking the delivered current would let an
    edited sheet go unnoticed, which is the exact failure this is built to prevent.
    """
    return _frame_fingerprint(
        pd.DataFrame(steps), ("window_s", "rate_hz"),
        either=(("t0", "t_local"), ("visit", "visit_date")),
        at_least_one=(("amp_mA_Left", "amp_mA_Right"),),
        also=("pw_us_Left", "pw_us_Right", "visit_date", "session_type", "settled_s"))


def _tiles_signature(tiles_by_channel):
    """A content hash of the per-electrode tile times and tile power.

    Hashed over raw bytes in one pass per array. These arrays are large — 298,953 tiles across six
    electrodes on this participant, each with 98 band centres — so anything per-element here would
    cost more than the fits it protects.
    """
    if not tiles_by_channel:
        return ("no_tiles",)
    out = []
    for ch in sorted(tiles_by_channel):
        t, p = tiles_by_channel[ch]
        h = _hashlib.blake2b(digest_size=16)
        for a in (np.ascontiguousarray(np.asarray(t, dtype=float)),
                  np.ascontiguousarray(np.asarray(p, dtype=float))):
            h.update(str(a.shape).encode("utf8"))
            h.update(a.tobytes())
        out.append((str(ch), h.hexdigest()))
    return ("hashed", tuple(out))


def amplitude_response_cached(steps, tiles_by_channel, *, centers_hz,
                              response_fn=None, hemispheres=("Left", "Right"), rates=None,
                              channels=None, force_refresh=False, **kw):
    """Band power against stimulation current, for every band, electrode and clinic visit.

    Returns a dict with four entries: ``cells`` maps each (electrode, side, rate) to its assembled
    evidence, ``audit`` says why every combination that yielded nothing was unusable, ``scores`` is
    the per-band table, and ``selected`` names the combination the conditions in
    ``lfp_evidence.screen_cells`` leave standing, or None when none does.

    The result is held in this process's memory and in a file the other worker processes can read,
    keyed on the contents of the clinic steps and of the tile power. A new or corrected testing
    sheet changes the key and the figures are worked out again; running the same sheet twice does
    no arithmetic the second time.

    ``response_fn`` defaults to ``StimOptimizer.routines.lfp_response.assess_response``, which is
    what the open-loop pipeline uses. It is keyed by name rather than by identity, because a
    function object's address changes on every restart and would make the key useless; the
    consequence is that editing the body of a response function without renaming it will not
    invalidate this cache, so pass ``force_refresh=True`` while working on one.

    Callers must treat the returned frames and evidence as read-only, or copy them first: they are
    the same objects handed to every other caller. That is the same contract the cached inputs and
    the cached joined table impose.
    """
    from StimOptimizer.routines import lfp_evidence as _ev
    from StimOptimizer.routines import within_visit as _wv
    if response_fn is None:
        from StimOptimizer.routines import lfp_response as _lr
        response_fn = _lr.assess_response

    cen = tuple(float(c) for c in np.asarray(centers_hz, dtype=float).ravel())
    sig = ("response", clinic_steps_signature(steps), _tiles_signature(tiles_by_channel), cen,
           tuple(str(h) for h in hemispheres),
           None if rates is None else tuple(float(r) for r in rates),
           None if channels is None else tuple(str(c) for c in channels),
           f"{getattr(response_fn, '__module__', '?')}.{getattr(response_fn, '__qualname__', '?')}",
           tuple(sorted((str(k), repr(v)) for k, v in kw.items())))

    # No `participant_uid` is passed on the two `_shared_*` calls below (decision 85 fixed
    # `evidence_inputs_cached`'s "inputs" kind, which has a live caller and a real participant in
    # scope; this "response" kind has neither today -- `steps`/`tiles_by_channel` carry no
    # participant identity of their own, and grepping the whole module tree finds this function
    # called only from its own test file). Left as `participant_uid=None` (the store's "shared"
    # group) rather than inventing one; if this is ever wired to a real caller, that caller should
    # pass the real participant through here too, the same way `evidence_inputs_cached` now does.
    if not force_refresh:
        with _RESPONSE_MEMO_LOCK:
            hit = _RESPONSE_MEMO.get(sig)
        if hit is not None:
            return hit
        shared = _shared_load("response", sig, consumer="closed_loop")
        if shared is not None:
            _remember_response(sig, shared)
            return shared

    cells, audit = _wv.build_all_within_visit(
        steps, centers_hz=np.asarray(cen, dtype=float), tiles_by_channel=tiles_by_channel,
        hemispheres=hemispheres, rates=rates, channels=channels, **kw)
    if cells:
        scores, selected = _ev.screen_cells(cells, response_fn=response_fn)
    else:
        scores, selected = pd.DataFrame(), None
    out = {"cells": cells, "audit": audit, "scores": scores, "selected": selected}
    _remember_response(sig, out)
    _shared_store("response", sig, out)
    return out


def _remember_response(sig, out):
    with _RESPONSE_MEMO_LOCK:
        if sig not in _RESPONSE_MEMO and len(_RESPONSE_MEMO) >= _RESPONSE_MEMO_MAX:
            _RESPONSE_MEMO.pop(next(iter(_RESPONSE_MEMO)), None)
        _RESPONSE_MEMO[sig] = out


def response_cache_stats():
    """Entries and how many combinations each holds, for the interface and for tests."""
    with _RESPONSE_MEMO_LOCK:
        return {"entries": len(_RESPONSE_MEMO), "max": _RESPONSE_MEMO_MAX,
                "cells": [len(v.get("cells") or {}) for v in _RESPONSE_MEMO.values()],
                "scored_bands": [int(getattr(v.get("scores"), "shape", (0,))[0])
                                 for v in _RESPONSE_MEMO.values()]}


def clear_response_cache(*, shared=False):
    with _RESPONSE_MEMO_LOCK:
        _RESPONSE_MEMO.clear()
    if shared:
        clear_shared_cache()


def joined_table_cached(psd_frame, epochs, *, centers=None, width=DEFAULT_BAND_WIDTH_HZ,
                        force_refresh=False, **kwargs):
    """``joined_table`` with a content-keyed memo. Returns the SAME object to every caller.

    Callers must therefore treat the result as read-only, or copy it before mutating. That is the
    price of not rebuilding a 70-second table per request, and it is the same contract the
    Biomarkers assembled-matrix cache already imposes.
    """
    cen = tuple(DEFAULT_BAND_CENTERS_HZ if centers is None else centers)
    # The pain frame merged into the table is part of its label (2026-09-25): left out, a memo hit
    # handed back the ratings of whichever request built the entry first.
    pro = kwargs.get("pro_frame")
    pro_fp = None if pro is None else _frame_fingerprint(
        pro, ("epoch",), also=("report_id",) + PAIN_SCORE_KEYS)
    sig = (_joined_signature(psd_frame, epochs, cen, width), pro_fp)
    if not force_refresh:
        with _JOINED_MEMO_LOCK:
            hit = _JOINED_MEMO.get(sig)
        if hit is not None:
            return hit
    out = joined_table(psd_frame, epochs, centers=cen, width=width, **kwargs)
    with _JOINED_MEMO_LOCK:
        if sig not in _JOINED_MEMO and len(_JOINED_MEMO) >= _JOINED_MEMO_MAX:
            _JOINED_MEMO.pop(next(iter(_JOINED_MEMO)), None)
        _JOINED_MEMO[sig] = out
    return out


def joined_cache_stats():
    """Entries and their row counts, for the interface and for tests."""
    with _JOINED_MEMO_LOCK:
        return {"entries": len(_JOINED_MEMO), "max": _JOINED_MEMO_MAX,
                "rows": [int(getattr(v, "shape", (0,))[0]) for v in _JOINED_MEMO.values()]}


def clear_joined_cache():
    with _JOINED_MEMO_LOCK:
        _JOINED_MEMO.clear()


def _attach_setting_pain(T, pro_frame):
    """The per-setting pain ratings onto every chunk, matched on the chunk's OWN setting.

    ``pro_frame`` is filed under the settings table's own number, ``epoch``, which
    `StimOptimizer.adapter.exposure_epochs` counts from 1; each chunk carries that number from its
    own setting (the ``epoch`` column of the setting context). ``setting_epoch`` is something else:
    the setting's POSITION in the table, counted from 0, which the regressions use only to group
    chunks. Until 2026-09-25 the ratings were matched on ``setting_epoch``, so every chunk carried
    the ratings of the setting BEFORE its own -- on RCS08, L 1-3+ at 24.5 Hz, 42,568 of 42,568 rated
    chunks, checked against the recording and report times. Only E2 (band power against pain) and
    its current-removed reading read these columns.

    A chunk outside every setting, or whose setting was never rated, carries no rating. A settings
    table with no ``epoch`` number gives nothing to match on, so no rating is attached rather than
    one guessed from a position.
    """
    if pro_frame is None or not len(pro_frame) or "epoch" not in pro_frame.columns:
        return T
    if "epoch" not in T.columns:
        _log.warning("ClosedLoopDeployment: the settings table carries no setting number, so no "
                     "pain rating was attached to the joined table")
        return T
    keep = [c for c in ("epoch", "report_id") + PAIN_SCORE_KEYS if c in pro_frame.columns]
    pain = pro_frame[keep].copy()
    pain["epoch"] = pd.to_numeric(pain["epoch"], errors="coerce").astype(float)
    n = len(T)
    T = T.assign(epoch=pd.to_numeric(T["epoch"], errors="coerce").astype(float)).merge(
        pain, on="epoch", how="left")
    if len(T) != n:
        raise ValueError(f"the pain frame names a setting more than once: {n} chunks became "
                         f"{len(T)} when the ratings were attached")
    return T


def joined_table(psd_frame, epochs, *, centers=DEFAULT_BAND_CENTERS_HZ,
                 width=DEFAULT_BAND_WIDTH_HZ, pro_frame=None):
    """The Phase 0 table: one row per (PSD sample, band).

    Long rather than wide in the band dimension. Wide would mean 18 columns per power scale and a
    reshape inside every estimator; long lets an estimator filter to its band and keeps the three
    power scales as three columns rather than fifty-four.

    ``pro_frame``, when supplied, must carry ``epoch`` and a report identifier; the matched pain
    report is joined on the setting epoch rather than on time, because the epoch is the unit the
    exposure model already assigns reports to and re-deriving it here would let the two drift.
    """
    if psd_frame is None or len(psd_frame) == 0:
        return pd.DataFrame()
    if calibrated_centres(psd_frame):
        return _joined_table_calibrated(psd_frame, epochs, centers=centers, pro_frame=pro_frame)
    ep_idx = _assign_epoch(psd_frame["t"].to_numpy(), epochs)

    rows = []
    have_epochs = epochs is not None and len(epochs) > 0
    for i, (_, r) in enumerate(psd_frame.iterrows()):
        lin = band_powers(r["psd"], r["freqs"], centers, width)
        e = int(ep_idx[i])
        ctx = {}
        if have_epochs and e >= 0:
            row = epochs.iloc[e]
            ctx = {c: row.get(c) for c in
                   ("freq_hz", "cathode_Left", "cathode_Right", "t_start", "t_end", "dur_h",
                    "epoch", "open_ended")
                   if c in epochs.columns}
            # Normalise the settings columns to the canonical spelling regardless of which one the
            # incoming frame used, so downstream estimators need to know only one name.
            for h in ("Left", "Right"):
                ac = resolve_setting_column(epochs.columns, "amp", h)
                pc = resolve_setting_column(epochs.columns, "pw", h)
                if ac:
                    ctx[canonical_amp_col(h)] = row.get(ac)
                if pc:
                    ctx[f"pw_us_{h}"] = row.get(pc)
        for c in centers:
            rows.append({
                "t": float(r["t"]), "channel": r["channel"], "source": r.get("source"),
                "setting_epoch": e, "center_hz": float(c), "band_width_hz": float(width),
                "power_linear": lin[c],
                **ctx,
            })
    T = pd.DataFrame(rows)
    if T.empty:
        return T
    for h in ("Left", "Right"):
        c = canonical_amp_col(h)
        if c in T.columns:
            T[f"era_{h}"] = _era_column(pd.to_numeric(T[c], errors="coerce").to_numpy(dtype=float))
    return _attach_setting_pain(T, pro_frame)


def _joined_table_calibrated(psd_frame, epochs, *, centers=DEFAULT_BAND_CENTERS_HZ, pro_frame=None):
    """``joined_table`` for the calibrated frame: one row per (tile, band), power read from the
    band's own column rather than integrated from a spectrum.

    ONE POWER SCALE. ``power_linear`` is the stored value itself, already the device's linear band
    power (the quantity a switching value is typed in). Until 2026-09-19 two log columns sat beside
    it (a decibel expression, and an always-empty mean-of-log); rule D11 fixes the scale to linear,
    nothing read them, and the PI's rule of that day (decision 202) is that log power enters no
    calculation, so they are gone.

    THE TILE-QUALITY GATE. A tile the cache marked not usable, or railed, is left out, which is the
    same gate the other deployment panels apply to this frame before they read it.

    THE BAND WIDTH is the frame's own (twice ``band_half_hz``); a ``centers`` entry the frame does
    not carry yields no rows for that centre, never a neighbour's value.
    """
    f = psd_frame
    keep = np.ones(len(f), dtype=bool)
    if "tile_ok" in f.columns:
        keep &= f["tile_ok"].to_numpy(dtype=bool)
    if "tile_saturated" in f.columns:
        keep &= ~f["tile_saturated"].to_numpy(dtype=bool)
    f = f.loc[keep].reset_index(drop=True)
    n_dropped = int((~keep).sum())
    if len(f) == 0:
        T = pd.DataFrame()
        T.attrs["rows_dropped_by_tile_gate"] = n_dropped
        return T
    width = 2.0 * float(pd.to_numeric(f["band_half_hz"], errors="coerce").iloc[0])
    ep_idx = _assign_epoch(f["t"].to_numpy(dtype=float), epochs)
    have_epochs = epochs is not None and len(epochs) > 0

    # the epoch context, once per tile, by fancy indexing rather than one row lookup per tile
    ctx_cols = {}
    if have_epochs:
        safe = np.where(ep_idx >= 0, ep_idx, 0)
        for c in ("freq_hz", "cathode_Left", "cathode_Right", "t_start", "t_end", "dur_h",
                  "epoch", "open_ended"):
            if c in epochs.columns:
                vals = epochs[c].to_numpy()[safe]
                ctx_cols[c] = np.where(ep_idx >= 0, vals, None) if vals.dtype == object \
                    else pd.Series(vals).where(ep_idx >= 0).to_numpy()
        for h in ("Left", "Right"):
            ac = resolve_setting_column(epochs.columns, "amp", h)
            pc = resolve_setting_column(epochs.columns, "pw", h)
            if ac:
                ctx_cols[canonical_amp_col(h)] = pd.Series(
                    pd.to_numeric(epochs[ac], errors="coerce").to_numpy()[safe]).where(ep_idx >= 0).to_numpy()
            if pc:
                ctx_cols[f"pw_us_{h}"] = pd.Series(
                    pd.to_numeric(epochs[pc], errors="coerce").to_numpy()[safe]).where(ep_idx >= 0).to_numpy()

    blocks = []
    t = f["t"].to_numpy(dtype=float)
    chan = f["channel"].to_numpy()
    src = f["source"].to_numpy() if "source" in f.columns else np.array([None] * len(f), dtype=object)
    for c in centers:
        col = f"{_CAL_LSB_PREFIX}{float(c):g}"
        if col not in f.columns:
            continue
        lin = pd.to_numeric(f[col], errors="coerce").to_numpy(dtype=float)
        block = {"t": t, "channel": chan, "source": src, "setting_epoch": ep_idx,
                 "center_hz": np.full(len(f), float(c)), "band_width_hz": np.full(len(f), width),
                 "power_linear": lin}
        nat = f"{_CAL_NATIVE_PREFIX}{float(c):g}"
        if nat in f.columns:
            block["device_native"] = f[nat].to_numpy(dtype=bool)
        block.update(ctx_cols)
        blocks.append(pd.DataFrame(block))
    if not blocks:
        T = pd.DataFrame()
        T.attrs["rows_dropped_by_tile_gate"] = n_dropped
        return T
    T = pd.concat(blocks, ignore_index=True)
    for h in ("Left", "Right"):
        c = canonical_amp_col(h)
        if c in T.columns:
            T[f"era_{h}"] = _era_column(pd.to_numeric(T[c], errors="coerce").to_numpy(dtype=float))
    T = _attach_setting_pain(T, pro_frame)
    T.attrs["rows_dropped_by_tile_gate"] = n_dropped
    T.attrs["band_power_source"] = "calibrated"
    return T



# `scale_disagreement(T)` -- how often the linear and mean-of-log scales picked a different winning
# band (hypothesis H4 of the module plan) -- stood here until 2026-09-19. It was computed on every
# request and read by no panel; decision 202 removed the mean-of-log column it compared, so it went.

def _num(x):
    """JSON-safe number. NaN and infinity are not valid JSON and silently become nulls or crash
    the serialiser depending on the encoder, so they are converted explicitly here rather than
    being discovered by the browser."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _json_safe(x):
    """Every number through ``_num``, strings and booleans as they are, nested to any depth.

    One converter for every nested payload this module serialises, so a NaN cannot reach the
    browser down one path while being converted down another.
    """
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, (list, tuple)):
        return [_json_safe(i) for i in x]
    if isinstance(x, dict):
        return {str(k): _json_safe(i) for k, i in x.items()}
    return _num(x)


def _capture_verdicts_to_dict(v):
    """JSON-safe copy of ``ThresholdPlan.capture_verdicts`` (``authority.d26_capture_verdicts``)."""
    if not v:
        return None
    return _json_safe(dict(v))


def report_to_dict(rep):
    """Flatten a DeploymentReport for the interface.

    The verdict is expressed as THREE states rather than a boolean, because the interface has to
    distinguish "the device forbids this" from "the evidence does not support it". Those call for
    different actions by the reader — the first is a configuration problem, the second is a
    measurement problem — and collapsing them into one "not ready" was the specific complaint the
    panel disposition raised.
    """
    el = rep.eligibility
    device_ok = bool(el.eligible) if el is not None else None
    edges_ok = bool(rep.edges) and all(e.resolved for e in rep.edges.values())
    # PRESERVE THE THREE STATES. `CoherenceReport.coherent` is None when at least one contributing
    # edge is unresolved, meaning "not established", which is a different finding from False,
    # meaning "the signs contradict each other". Wrapping it in bool() collapsed None to False and
    # made the interface report a contradiction that the data had not shown — the exact failure this
    # panel was rebuilt to prevent.
    coherent = None if rep.coherence is None else rep.coherence.coherent
    # THE PROVISIONAL FLAG (PI rule 2026-09-13, "established means mean only": point sign decides,
    # but flag as provisional). `resolved` is the point sign since that date, so a report can be
    # licensed while an edge's interval spans zero; the verdict string then carries the count so a
    # reader of the word "supported" also reads what it rests on. The denominator is the number of
    # edges the report holds, three on every real report.
    n_unest = int(getattr(rep, "n_edges_unestablished", 0) or 0)
    n_edges = len(rep.edges or {})
    licensed = rep.is_licensed()
    provisional = bool(getattr(rep, "provisional", False))
    unestablished_edges = [k for k, e in (rep.edges or {}).items()
                           if not getattr(e, "statistically_established", False)]

    if device_ok is False:
        verdict = "blocked"
    elif licensed and provisional:
        verdict = f"supported (point signs only; {n_unest} of {n_edges} intervals span zero)"
    elif licensed:
        verdict = "supported"
    else:
        verdict = "unsupported"

    return {
        "available": True,
        "participant": rep.participant,
        "verdict": verdict,
        "licensed": licensed,
        "verdict_detail": {
            "device_eligible": device_ok,
            "all_edges_resolved": edges_ok,
            # The caveat beside the verdict, never inside it: which edges rest on their point
            # sign alone, and how many. `provisional` is True only for a licensed report.
            "provisional": provisional,
            "n_edges_unestablished": n_unest,
            "n_edges": n_edges,
            "unestablished_edges": unestablished_edges,
            "all_edges_statistically_established": bool(rep.edges) and n_unest == 0,
            "coherent": coherent,
            "blockers": list(rep.blockers),
            # Gate nothing; shown beside the verdict. The two D26 capture verdicts live here since
            # 2026-09-12 (PI: "b and c"). `getattr` so a report object that predates the field
            # serialises as an empty list rather than raising.
            "warnings": list(getattr(rep, "warnings", []) or []),
        },
        "eligibility": None if el is None else {
            "eligible": el.eligible, "checked": el.checked, "summary": el.summary(),
            "failures": el.failures, "unknowns": el.unknowns, "advisories": el.advisories,
            # The fourth bucket. Rows land here when another rule already charged the SAME
            # consideration from the SAME input, so the observation is kept and only the duplicate
            # charge against the verdict is dropped. Omitting it made the four bucket lengths fail
            # to account for the rules checked, which is the arithmetic a reader uses to satisfy
            # themselves that nothing was quietly discarded.
            "deferred": getattr(el, "deferred", []) or [],
        },
        "edges": {k: {
            "name": e.name, "estimate": _num(e.estimate),
            "ci": None if e.ci is None else [_num(e.ci[0]), _num(e.ci[1])],
            "p": _num(e.p), "n": int(e.n), "cluster_unit": e.cluster_unit,
            "n_clusters": int(e.n_clusters), "scale": e.scale, "sign": e.sign,
            # `resolved` is the point sign since 2026-09-13; `statistically_established` is the
            # interval rule it used to be, carried as the caveat the page prints beside the sign.
            "resolved": e.resolved,
            "statistically_established": bool(getattr(e, "statistically_established", False)),
            "note": e.note, "confounded_by": list(e.confounded_by),
            # WHICH ESTIMATE this is (review 2026-09-15, C1): "screening_historical" or
            # "pooled_titration" on E1, None on E2 and E3. The triangle draws them differently.
            "source": getattr(e, "source", None),
            # WHICH ESTIMATOR produced the interval and the p-value, read from edges.py so the
            # switch has exactly one definition. The deployment panel used to hardcode the cluster
            # threshold in JavaScript with a comment claiming to mirror edges.py, and by then the
            # comment was wrong twice over: the constant had stopped being a disqualification floor
            # and become a choice between two estimators.
            "inference": _edges.estimator_for(e.n_clusters),
            # THE SAME EDGE WITH A THIRD QUANTITY TAKEN OUT, or absent when nobody asked (panel D
            # item 4). On E2 that quantity is the stimulation current in force. Descriptive: the
            # page prints it beside the plain reading and no gate reads it.
            "adjusted": _json_safe(getattr(e, "adjusted", None)),
        } for k, e in (rep.edges or {}).items()},
        # `edges_historical` (the setting-epoch E1 the pooled slope replaced, decision 126) LEFT THE
        # RESPONSE on 2026-09-23 (panel D item 10): no page, module or server read it. It stays on
        # the report object, `rep.edges_historical`, and E1 still names which estimate it is.
        "coherence": None if rep.coherence is None else {
            "coherent": rep.coherence.coherent, "p_coherent": _num(rep.coherence.p_coherent),
            "expected_pattern": rep.coherence.expected_pattern,
            "observed_pattern": rep.coherence.observed_pattern,
            "n_boot": rep.coherence.n_boot, "note": rep.coherence.note,
        },
        # The programmable prescription. Every field carries its provenance because the interface
        # must be able to distinguish a value derived from this participant's data from a
        # manufacturer default and from a field whose adjustable range is unpublished — a clinician
        # transcribing these into a programmer is entitled to know which is which, and rendering
        # them identically would invite a default to be entered as though it were a measurement.
        # The controller replay. Not serialised at all until 2026-09-04, so the panel could not
        # show the counterfactual trajectory even when the pipeline had computed it. The amplitude
        # TRAJECTORY itself is deliberately omitted: it is one value per controller step over
        # months of recording, far too large for a payload, and the fractions plus the transition
        # count are what a reader acts on. Its caveat is carried through verbatim because the
        # trajectory is what the control law would have done to a power series recorded under the
        # participant's actual programming, which is not a forecast of what the device would
        # deliver once the loop is closed.
        # `protocol` LEFT THE RESPONSE on 2026-09-23 (panel D item 10): a titration-session plan
        # built from the two capture currents that no page read -- the page's titration plan is
        # the Stim Optimizer's card (decisions 146, 160, 230, 236). The plan is still built on
        # the report (`rep.protocol`, which can add a blocker if it fails) and keeps its tests.
        "replay": None if rep.replay is None else {
            "frac_time_at_upper": rep.replay.frac_time_at_upper,
            "frac_time_at_lower": rep.replay.frac_time_at_lower,
            # The longest CONTINUOUS excursion at each limit. Emitted rather than withheld, unlike
            # the per-step trajectories these are derived from, because they are two scalars and
            # they answer the question the fractions cannot: how long one stretch at the upper
            # limit could last. None means no trajectory was available; 0.0 means the limit was
            # never reached, and those must not be collapsed by the interface.
            "longest_run_at_upper_s": rep.replay.longest_run_at_upper_s,
            "longest_run_at_lower_s": rep.replay.longest_run_at_lower_s,
            "n_transitions": rep.replay.n_transitions,
            "saturated": rep.replay.saturated,
            "params": {k: v for k, v in (rep.replay.params or {}).items()},
            "note": rep.replay.note,
        },
        # EVERY MODE, plus which one this module recommends and why. The interface renders a
        # toggle from this, so the clinician can look at what Single Threshold would require
        # instead of taking the module's word that Dual is better. `selected` is what the candidate
        # asked for and `recommended` is what this module would choose; they are deliberately
        # separate keys so a page showing the non-recommended mode still displays the advice.
        "prescriptions": None if getattr(rep, "prescriptions", None) is None else {
            "recommended": rep.prescriptions.get("recommended"),
            "selected": getattr(getattr(rep, "prescription", None), "mode", None),
            "recommendation": {k: v for k, v in (rep.prescriptions.get("recommendation") or {}).items()
                               if not k.startswith("_")},
            "modes": {m: {
                "mode": pr.mode,
                "fields": pr.as_rows(),
                "not_applicable": [{"parameter": f.name, "units": f.units, "why": f.why,
                                    "status": f.status, "origin": f.origin, "confirm": f.confirm}
                                   for f in (pr.not_applicable or [])],
                "couplings": list(pr.couplings or []),
                "unknowns": list(pr.unknowns or []),
                "note": pr.note,
                "duty": None if pr.duty is None else {
                    k: getattr(pr.duty, k) for k in (
                        "lfp_frac_above", "lfp_frac_between", "lfp_frac_below",
                        "stim_frac_at_upper", "stim_frac_at_lower", "stim_frac_mid",
                        "mean_amplitude_mA", "amplitude_duty", "transitions_per_hour",
                        "hours_observed",
                        "hours_of_signal", "coverage_frac", "fractions_are_of_observed_samples",
                        "onset_windows_upper", "onset_windows_lower", "onset_inoperative",
                        "max_time_at_upper_limit_s", "max_time_at_lower_limit_s")} | {
                    "caveats": list(pr.duty.caveats or [])},
            } for m, pr in (rep.prescriptions.get("modes") or {}).items()},
        },
        "prescription": None if getattr(rep, "prescription", None) is None else {
            "mode": rep.prescription.mode,
            "fields": rep.prescription.as_rows(),
            "not_applicable": [{"parameter": f.name, "units": f.units, "why": f.why,
                                "status": f.status, "origin": f.origin, "confirm": f.confirm}
                               for f in (rep.prescription.not_applicable or [])],
            "couplings": list(rep.prescription.couplings or []),
            "unknowns": list(rep.prescription.unknowns or []),
            "note": rep.prescription.note,
            "duty": None if rep.prescription.duty is None else {
                k: getattr(rep.prescription.duty, k) for k in (
                    "lfp_frac_above", "lfp_frac_between", "lfp_frac_below",
                    "stim_frac_at_upper", "stim_frac_at_lower", "stim_frac_mid",
                    "mean_amplitude_mA", "amplitude_duty", "transitions_per_hour",
                    "hours_observed",
                    # Coverage travels with the fractions or they will be misread. Omitting these
                    # three from this tuple already happened once: the caveat text carried the
                    # numbers while the fields serialised as null, so an interface reading the
                    # fields alone could have printed "49.6% of the day" for a record with 0.012%
                    # coverage. Any field added to DutyCycle must be added here too.
                    "hours_of_signal", "coverage_frac", "fractions_are_of_observed_samples",
                    "onset_windows_upper", "onset_windows_lower", "onset_inoperative",
                    # The longest CONTINUOUS excursion at each limit, which the fractions above
                    # cannot express and which is the number a clinician needs before consenting.
                    "max_time_at_upper_limit_s", "max_time_at_lower_limit_s")} | {
                "caveats": list(rep.prescription.duty.caveats or [])},
        },
        # Decision 180: what the record-based placement did (`_place_thresholds_from_record`, handed
        # to `pipeline.run` as `place_thresholds`, so the ledger, the replay and the rows all read it).
        "threshold_placement": getattr(rep, "threshold_placement", None),
        "threshold": None if rep.threshold is None else {
            "upper": _num(rep.threshold.upper), "lower": _num(rep.threshold.lower),
            "control_authority": _num(rep.threshold.control_authority),
            "capture_amp_low": _num(rep.threshold.capture_amp_low),
            "capture_amp_high": _num(rep.threshold.capture_amp_high),
            # Decision 306: the adaptive limits the card recommends -- the capture currents held at
            # or below the PI-stated safe ceiling for the stimulated side -- and that ceiling.
            "amp_limit_low": _num(rep.threshold.amplitude_limits()[0]),
            "amp_limit_high": _num(rep.threshold.amplitude_limits()[1]),
            "safety_ceiling_mA": _num(getattr(rep.threshold, "safety_ceiling_mA", None)),
            "safety_ceiling_provenance": getattr(rep.threshold, "safety_ceiling_provenance", "") or None,
            "amp_limit_low_note": getattr(rep.threshold, "amp_limit_low_note", None),
            "amp_limit_high_note": getattr(rep.threshold, "amp_limit_high_note", None),
            "frac_time_below": _num(rep.threshold.frac_time_below),
            "frac_time_between": _num(rep.threshold.frac_time_between),
            "frac_time_above": _num(rep.threshold.frac_time_above),
            "predicted_recapture_alert": rep.threshold.predicted_recapture_alert,
            "problems": list(rep.threshold.problems), "note": rep.threshold.note,
            # The two D26 verdicts as warnings (gate nothing) and in structured form, with the
            # between-visit comparison they used to rest on reported beside them as a number.
            "warnings": list(getattr(rep.threshold, "warnings", []) or []),
            "placement_rule": getattr(rep.threshold, "placement_rule", "capture"),
            "capture_upper": _num(getattr(rep.threshold, "capture_upper", None)),
            "capture_lower": _num(getattr(rep.threshold, "capture_lower", None)),
            "placement_note": getattr(rep.threshold, "placement_note", ""),
            "placement": dict(getattr(rep.threshold, "placement", {}) or {}),
            "capture_verdicts": _capture_verdicts_to_dict(
                getattr(rep.threshold, "capture_verdicts", None)),
        },
        "manifest": rep.manifest,
        "candidates": rep.candidates,
    }


#: Which card on the page each caveat belongs to, so a reader can go and look at the number rather
#: than take the sentence on trust. These are the page's own card names, in its own words.
CAVEAT_CARDS = {
    "verdict": "the decision card",
    "evidence": "the evidence triangle",
    "thresholds": "the parameters to transcribe",
    "timing": "the parameters to transcribe",
    "simulation": "the closed-loop simulations",
    "stability": "does this band mean the same thing at every current",
}


#: The evidence checks the decision card lists in yellow when they should have run and did not
#: (decision 302; the PI, 2026-09-26: "if the evidence wasn't evaluated but should have been, use
#: yellow bullet points ... in five words or less"). At most four words each, so "Untested: <label>"
#: is at most five. One home: the page prints these and adds no words of its own.
EVIDENCE_CHECK_LABELS = {
    "E1": "Current changes band power",
    "E2": "Band power tracks pain",
    "E3": "Current changes pain",
    "coherence": "Sign agreement",
    "stability": "Stable across currents",
}

_EVIDENCE_CHECK_WHY = {
    "E1": "no point estimate for how band power changes with current",
    "E2": "no point estimate for how pain changes with band power",
    "E3": "no point estimate for how pain changes with current",
    "coherence": "the test of whether the three signs agree did not return an answer",
    "stability": "the test of whether the band means the same thing at every current did not run",
}


def evidence_not_evaluated(payload):
    """The evidence checks that should have been evaluated for this report and were not.

    Returned as [{key, label, card, why}] in the order the evidence card draws them, assembled per
    request from what the payload already carries and stored nowhere, like the caveats list. Only
    ABSENCE is listed: an edge with no point estimate, a sign test that returned nothing, a stability
    test that did not run. An answer that came back unsettled ("cannot tell", an interval spanning
    zero) is an answer and is read on its own card, never here. A missing edge makes the sign test
    impossible by construction, so the sign test is listed only when every edge is present -- one
    absence is one bullet.
    """
    if not payload or not isinstance(payload, dict) or payload.get("available") is not True:
        return []
    rows = []
    edges = payload.get("edges") or {}
    missing_edge = False
    for k in ("E1", "E2", "E3"):
        e = edges.get(k) if isinstance(edges, dict) else None
        if not isinstance(e, dict) or e.get("estimate") is None or e.get("resolved") is False:
            missing_edge = True
            rows.append(k)
    co = payload.get("coherence")
    if not missing_edge and (not isinstance(co, dict) or co.get("coherent") is None):
        rows.append("coherence")
    stab = payload.get("band_stability")
    if not isinstance(stab, dict) or not stab.get("answer") or stab.get("answer") == "not tested":
        rows.append("stability")
    card = {"stability": CAVEAT_CARDS["stability"]}
    return [{"key": k, "label": EVIDENCE_CHECK_LABELS[k],
             "card": card.get(k, CAVEAT_CARDS["evidence"]),
             "why": (((stab or {}).get("reason") if k == "stability" and isinstance(stab, dict)
                      else None) or _EVIDENCE_CHECK_WHY[k])}
            for k in rows]


def caveats_for_report(payload):
    """Every caveat on one served report, as one flat list of {severity, text, card}.

    WHY THIS EXISTS (panel D item 3, 2026-09-22). This page prints numbers of two kinds: ones with
    an uncertainty interval and ones without. Nothing on the page said which was which, so a
    threshold placed from a median and a discrimination value with a bootstrap interval were read
    with the same confidence. The list names every number that carries no interval today, beside
    the warnings the report already holds and the point-sign caveat on the verdict itself.

    IT IS ASSEMBLED PER REQUEST AND STORED NOWHERE. Nothing here is a new measurement: every entry
    restates something the payload already carries, so a stored copy could only go stale. It is
    also NOT another stage of the argument -- it gates nothing and refuses nothing.

    ``severity`` is "high" for something that changes what the answer means, "medium" for a number
    a clinician would transcribe that has no interval, and "low" for a number that qualifies one
    panel only.
    """
    if not payload or not isinstance(payload, dict) or payload.get("available") is not True:
        return []
    rows = []
    vd = payload.get("verdict_detail") or {}

    # 1. THE REPORT'S OWN WARNINGS, word for word. Today these are the two D26 capture verdicts.
    for w in (vd.get("warnings") or []):
        if isinstance(w, str) and w.strip():
            rows.append({"severity": "high", "text": w.strip(), "card": CAVEAT_CARDS["thresholds"]})
    for w in ((payload.get("threshold") or {}).get("warnings") or []):
        if isinstance(w, str) and w.strip() and w.strip() not in [r["text"] for r in rows]:
            rows.append({"severity": "high", "text": w.strip(), "card": CAVEAT_CARDS["thresholds"]})

    # 2. THE VERDICT RESTS ON POINT SIGNS. The PI's rule of 2026-09-13 licenses a verdict on the
    #    sign of each point estimate; which intervals span zero is the caveat, and it belongs on
    #    the printed record beside the word a clinician reads.
    if vd.get("provisional") is True:
        names = [str(e) for e in (vd.get("unestablished_edges") or [])]
        which = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else "".join(names)
        rows.append({
            "severity": "high",
            "text": (f"The verdict rests on the point signs alone: the interval spans zero on "
                     f"{which or 'at least one edge'} ({vd.get('n_edges_unestablished')} of "
                     f"{vd.get('n_edges')}). A point sign is a direction, not an established "
                     f"effect."),
            "card": CAVEAT_CARDS["evidence"]})

    # 3. THE BAND-POWER-TO-PAIN READING AND THE CURRENT IN FORCE (panel D item 4). Printed whether
    #    the second reading could be made or not, because "it could not be made" is itself a
    #    caveat on the first one.
    e2 = ((payload.get("edges") or {}).get("E2") or {})
    adj = e2.get("adjusted") or None
    if adj:
        # The current in words, never its column (decision 314); an answer saved before the words
        # were carried gets them from the estimator's own table (decision 313).
        from Biomarkers.routines.analytics import _covariate_words
        cur_words = adj.get("adjusted_for_words") or _covariate_words(adj.get("adjusted_for"))[0]
        if adj.get("available") and adj.get("auc") is not None:
            lo, hi = adj.get("auc_low"), adj.get("auc_high")
            span = (f", interval {float(lo):.3f} to {float(hi):.3f}"
                    if (lo is not None and hi is not None) else "")
            rows.append({
                "severity": "medium",
                "text": (f"How well this band tells high pain from low pain is reported without "
                         f"the stimulation current taken out of it. Read again with {cur_words} "
                         f"in force removed from the band power, it "
                         f"is {float(adj['auc']):.3f}{span}, against 0.5 for coin flipping."),
                "card": CAVEAT_CARDS["evidence"]})
        else:
            rows.append({
                "severity": "medium",
                "text": (f"How well this band tells high pain from low pain carries no term for "
                         f"the stimulation current in force, and the reading with the current "
                         f"taken out could not be made here: {adj.get('why', 'no reason recorded')}."),
                "card": CAVEAT_CARDS["evidence"]})

    # 4. THE NUMBERS WITH NO INTERVAL. Each is named with its value, so the sentence can be checked
    #    against the card rather than believed.
    thr = payload.get("threshold") or {}
    if thr.get("upper") is not None or thr.get("lower") is not None:
        # FOUR DECIMALS, as the parameter card prints the same two values (`fmtPower` in
        # deployFormat.js). This line printed the raw float -- "172.2737406083742" on the signed
        # sheet (the PI, 2026-09-22) -- so one number read two ways on one page.
        def _as_card(v):
            try:
                f = float(v)
            except (TypeError, ValueError):
                return str(v)
            return f"{f:.4f}" if np.isfinite(f) else str(v)
        # NO VALUE WHILE THE DEVICE REFUSES (decision 302). The parameter table withholds every
        # value when the device rules refuse the configuration, because a number on screen during a
        # programming visit gets typed; this caveat printed both thresholds to four places on the
        # same card regardless. The sentence stays, the numbers go.
        if vd.get("device_eligible") is True:
            which = (f"({_as_card(thr.get('lower'))} and {_as_card(thr.get('upper'))} in the "
                     f"stimulator's own units) ")
        else:
            which = "(withheld while the device refuses this configuration) "
        rows.append({
            "severity": "medium",
            "text": (f"The two switching values the device would use {which}"
                     f"are a median reading plus or minus a fixed minimum, and carry no interval. "
                     f"How far they would move on a different day is not shown."),
            "card": CAVEAT_CARDS["thresholds"]})
        rows.append({
            "severity": "medium",
            "text": ("The smallest gap the design rule allows between those two values is a fixed "
                     "number from a simulation, not a measurement on this patient, and carries no "
                     "interval."),
            "card": CAVEAT_CARDS["thresholds"]})
    presc = payload.get("prescription") or {}
    if presc.get("fields"):
        rows.append({
            "severity": "medium",
            "text": ("The timing values to transcribe (how long the device averages, how long it "
                     "waits before switching, how long it holds after a switch) carry a word for "
                     "how confident we are and no interval."),
            "card": CAVEAT_CARDS["timing"]})

    # 5. THE SIMULATION'S FRACTIONS. Only the run-resampled model carries an interval; the other
    #    models' fractions are single numbers and are drawn identically, which invites a reader to
    #    treat them alike.
    sim = payload.get("closed_loop_simulation") or {}
    models = (sim.get("models") or {}) if isinstance(sim, dict) else {}
    if models:
        rows.append({
            "severity": "low",
            "text": ("In the closed-loop simulations only M3 resamples whole runs and so carries "
                     "an interval; the fractions of time the other models spend at each limit are "
                     "single numbers with none."),
            "card": CAVEAT_CARDS["simulation"]})

    # 6. THE STABILITY ANSWER, when it is anything other than a demonstrated pass.
    stab = payload.get("band_stability") or {}
    if stab.get("answer") and stab.get("answer") != "behaves the same":
        rows.append({
            "severity": "high" if stab.get("answer") == "behaves differently" else "medium",
            "text": (f"Whether this band means the same thing about pain at every stimulation "
                     f"current: {stab.get('answer')}. "
                     f"{stab.get('reason') or ''}").strip(),
            "card": CAVEAT_CARDS["stability"]})

    order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda r: order.get(r["severity"], 3))
    return rows


#: How many of the newest runs of stepped current the deployment page DRAWS. The amplitude-effect
#: table is built from every run the device's record holds, not only these, because Stim
#: Optimizer's question is which bands are still unresolved anywhere in the record.
THREE_SOURCE_RUNS_ON_PAGE = 4

#: Every run, for the table. The comparison builder takes a count, so "all" is a count no record
#: will reach.
_ALL_RUNS = 10_000


def amplitude_effect_signature(participant, *, tiles_key, min_settings=3):
    """The key for the amplitude-effect table: the tile entry, the recording set that the ladders
    are read from, and the settled-window rule. Nothing decoded enters it (decision 24)."""
    from StimOptimizer.routines import within_visit as _wv
    from . import amplitude_effect as _amp
    return (_amp.KIND, _amp.RULE_VERSION, str(getattr(participant, "uid", participant)),
            tiles_key, recording_set_signature(participant), "all_runs", int(min_settings),
            float(_wv.PRE_CHANGE_WINDOW_S), int(_wv.MIN_CHUNKS_PRE_CHANGE),
            int(_amp.MIN_POINTS_CURVATURE))


def ground_truth_signature(participant, *, tiles_key, min_settings=3):
    """The key for the ground-truth verdict table: the tile entry, the recording set the ladders
    are read from, the settled-window rule and the device ceiling. Nothing decoded enters it."""
    from StimOptimizer.routines import within_visit as _wv
    from . import ground_truth as _gt
    from . import three_source_response as _3src
    return (_gt.KIND, _gt.RULE_VERSION, str(getattr(participant, "uid", participant)),
            tiles_key, recording_set_signature(participant), "all_runs", int(min_settings),
            float(_wv.PRE_CHANGE_WINDOW_S), int(_wv.MIN_CHUNKS_PRE_CHANGE),
            _3src.CEILING_RULE_VERSION, float(_3src.DEVICE_MIN_SAMPLE_FRACTION))


def ground_truth_if_stored(participant, *, min_settings=3):
    """The stored verdict's summary when the store already holds it under the current key."""
    from . import ground_truth as _gt
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        return None
    uid = str(getattr(participant, "uid", participant))
    sig = ground_truth_signature(participant, tiles_key=tiles_key, min_settings=min_settings)
    stamp = _cache_store.read_stamp(_gt.KIND, uid, sig, root=_SHARED_CACHE_DIR_OVERRIDE)
    if not stamp:
        return None
    extra = stamp.get("extra") or {}
    return {"written": True, "served_from_store": True,
            "store_key": _cache_store.product_key(_gt.KIND, uid, sig),
            "n_rows": extra.get("n_rows"), "n_runs": extra.get("n_runs"),
            "routes": extra.get("routes"), "stored_utc": stamp.get("written_utc")}


def write_ground_truth(participant, build, *, min_settings=3):
    """Apply the ground-truth rule (decision 33) to every run and write the verdict table where
    Stim Optimizer reads it, with the tile entry in its provenance. Track G step 2.

    Returns a summary for the response: the store key, whether the entry is on disk, the row and
    run counts, how many rows each route won, and the reason when nothing could be written.
    """
    from . import ground_truth as _gt
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                # pragma: no cover - depends on the runner
        from CacheStore import provenance as _prov
    if not build or not build.get("comparisons"):
        return {"written": False, "n_rows": 0, "n_runs": 0,
                "reason": (build or {}).get("absent_reason") or "no run of stepped current"}
    table = _gt.table_from_build(build)
    routes = ({str(k): int(v) for k, v in table["ground_truth_route"].value_counts().items()}
              if len(table) else {})
    summary = {"written": False, "n_rows": int(len(table)),
               "n_runs": int(table["run_label"].nunique()) if len(table) else 0,
               "routes": routes, "store_key": None,
               "device_spikes_excluded": int(table["device_spikes_excluded"].sum()) if len(table) else 0}
    from . import three_source_response as _3src
    summary["device_spike_ceiling_rule"] = _3src.CEILING_RULE_VERSION
    if not len(table):
        summary["reason"] = "no route had a settled value in any run"
        return summary
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        summary["reason"] = "no tile entry key, so the table was derived but not stored"
        return summary
    uid = str(getattr(participant, "uid", participant))
    sig = ground_truth_signature(participant, tiles_key=tiles_key, min_settings=min_settings)
    prov = _prov.flatten([_prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")])
    _cache_store.store_if_absent(_gt.KIND, uid, sig, lambda: table,
                                 writer="closed_loop", trigger="deployment_report",
                                 provenance=prov, n_recordings=None,
                                 extra={"min_settings": int(min_settings),
                                        "n_rows": summary["n_rows"], "n_runs": summary["n_runs"],
                                        "routes": routes,
                                        "device_spike_ceiling_rule": _3src.CEILING_RULE_VERSION},
                                 root=_SHARED_CACHE_DIR_OVERRIDE)
    summary["served_from_store"] = False
    summary["store_key"] = _cache_store.product_key(_gt.KIND, uid, sig)
    summary["written"] = _cache_store.read_stamp(_gt.KIND, uid, sig,
                                                 root=_SHARED_CACHE_DIR_OVERRIDE) is not None
    return summary


def amplitude_effect_if_stored(participant, *, min_settings=3):
    """The response summary for an amplitude-effect table already in the store, or None.

    Asked BEFORE the comparison is built, so that a request whose table is already on disk builds
    only the runs the page draws rather than every run in the record.
    """
    from . import amplitude_effect as _amp
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        return None
    uid = str(getattr(participant, "uid", participant))
    sig = amplitude_effect_signature(participant, tiles_key=tiles_key, min_settings=min_settings)
    stamp = _cache_store.read_stamp(_amp.KIND, uid, sig, root=_SHARED_CACHE_DIR_OVERRIDE)
    if not stamp:
        return None
    extra = stamp.get("extra") or {}
    return {"written": True, "served_from_store": True,
            "store_key": _cache_store.product_key(_amp.KIND, uid, sig),
            "n_rows": extra.get("n_rows"), "n_runs": extra.get("n_runs"),
            "n_bands": extra.get("n_bands"), "stored_utc": stamp.get("written_utc")}


def _tiles_key_for(participant):
    """The store key of the tile entry the comparison read, or None with no server to ask."""
    try:
        from modules.Biomarkers import bravo_service as _bsvc
        uid = getattr(participant, "uid", participant)
        sig = _bsvc._raw_lsb_shared_signature(uid, _bsvc._LSB_SPECTRUM_CENTERS)
        if sig is None:
            return None
        return _cache_store.product_key(_bsvc._RAW_LSB_SHARED_KIND, uid, sig)
    except Exception:                                  # noqa: BLE001 — no server, no tile key
        return None


def write_amplitude_effect(participant, build, *, min_settings=3):
    """Derive the per-band amplitude-effect table from the comparison and write it to the store.

    `build` must hold EVERY run the record supports (built with `max_runs=_ALL_RUNS`), not only the
    runs the page draws. Returns a small summary for the response: the store key, whether the
    entry is on disk, the row and run counts, and the reason when nothing could be written. The
    table is written only when the tile entry can be named, because a key that cannot change with
    its inputs would serve a stale answer; without it the table is still derived and its counts
    reported.
    """
    from . import amplitude_effect as _amp
    from . import three_source_response as _3src
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                # pragma: no cover - depends on the runner
        from CacheStore import provenance as _prov

    if not build or not build.get("comparisons"):
        return {"written": False, "n_rows": 0, "n_runs": 0,
                "reason": (build or {}).get("absent_reason") or "no run of stepped current"}
    table = _amp.table_from_build(build, checked_lo_hz=_3src.CHECKED_LO_HZ,
                                  checked_hi_hz=_3src.CHECKED_HI_HZ,
                                  band_half_hz=_3src.BAND_HALF_HZ)
    summary = {"written": False, "n_rows": int(len(table)),
               "n_runs": int(table["run_label"].nunique()) if len(table) else 0,
               "n_bands": int(table["band_center_hz"].nunique()) if len(table) else 0,
               "store_key": None}
    if not len(table):
        summary["reason"] = "the voltage-trace route had nothing to show in any run"
        return summary
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        summary["reason"] = "no tile entry key, so the table was derived but not stored"
        return summary
    uid = str(getattr(participant, "uid", participant))
    sig = amplitude_effect_signature(participant, tiles_key=tiles_key, min_settings=min_settings)
    prov = _prov.flatten([_prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")])
    _cache_store.store_if_absent(_amp.KIND, uid, sig, lambda: table,
                                 writer="closed_loop", trigger="deployment_report",
                                 provenance=prov, n_recordings=None,
                                 extra={"min_settings": int(min_settings),
                                        "n_rows": summary["n_rows"], "n_runs": summary["n_runs"],
                                        "n_bands": summary["n_bands"]},
                                 root=_SHARED_CACHE_DIR_OVERRIDE)
    summary["served_from_store"] = False
    summary["store_key"] = _cache_store.product_key(_amp.KIND, uid, sig)
    summary["written"] = _cache_store.read_stamp(_amp.KIND, uid, sig,
                                                 root=_SHARED_CACHE_DIR_OVERRIDE) is not None
    return summary


def pooled_shape_signature(participant, *, tiles_key, min_points=None):
    """The key for the pooled within-visit table. Same inputs as the per-run amplitude table --
    the tile entry, the recording set the ladders are read from, and the settled-window rule --
    plus the pooling floor, because a pool that needs eight points is not the same answer as one
    that needs five. Nothing decoded enters it (decision 24)."""
    from StimOptimizer.routines import within_visit as _wv
    from . import amplitude_effect as _amp
    floor = int(_amp.MIN_POINTS_CURVATURE if min_points is None else min_points)
    return (_amp.POOLED_KIND, _amp.POOLED_RULE_VERSION,
            str(getattr(participant, "uid", participant)), tiles_key,
            recording_set_signature(participant), "all_runs", floor,
            float(_wv.PRE_CHANGE_WINDOW_S), int(_wv.MIN_CHUNKS_PRE_CHANGE))


def write_pooled_shape(participant, build, *, is_every_run, min_points=None):
    """Derive the pooled within-visit table from a FULL-run comparison and write it to the store.

    `is_every_run` is not a courtesy flag -- **this function refuses to write when it is False.**
    Pooling the dose-response over the page's truncated build produces a table that looks complete
    and answers from a fraction of the visits, and a stored wrong answer is worse than no stored
    answer because everything downstream then trusts it. Measured on RCS08, ONE_THREE_LEFT at
    17.5 Hz: a full build pools 13 points across 4 visits, the 4-run page slice pools 6 across 1.
    """
    from . import amplitude_effect as _amp
    from . import three_source_response as _3src
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                # pragma: no cover - depends on the runner
        from CacheStore import provenance as _prov

    summary = {"written": False, "n_rows": 0, "n_contacts": 0, "n_bands": 0, "store_key": None}
    if not is_every_run:
        summary["reason"] = ("the comparison was built from only the runs the page draws, and a "
                             "pooled answer from a fraction of the visits must not be stored")
        return summary
    if not build or not build.get("comparisons"):
        summary["reason"] = ((build or {}).get("absent_reason")
                             or "no run of stepped current to pool")
        return summary

    table = _amp.pooled_table_from_build(build, checked_lo_hz=_3src.CHECKED_LO_HZ,
                                         checked_hi_hz=_3src.CHECKED_HI_HZ,
                                         band_half_hz=_3src.BAND_HALF_HZ,
                                         min_points=(_amp.MIN_POINTS_CURVATURE
                                                     if min_points is None else min_points))
    summary["n_rows"] = int(len(table))
    if not len(table):
        summary["reason"] = "the voltage-trace route had nothing to pool in any run"
        return summary
    summary["n_contacts"] = int(table["sensing_contact"].nunique())
    summary["n_bands"] = int(table["band_center_hz"].nunique())
    summary["n_assessed"] = int((table["pooled_direction"].astype(str) != "not assessed").sum())

    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        summary["reason"] = "no tile entry key, so the table was derived but not stored"
        return summary
    uid = str(getattr(participant, "uid", participant))
    sig = pooled_shape_signature(participant, tiles_key=tiles_key, min_points=min_points)
    prov = _prov.flatten([_prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")])
    _cache_store.store_if_absent(_amp.POOLED_KIND, uid, sig, lambda: table,
                                 writer="closed_loop", trigger="deployment_report",
                                 provenance=prov, n_recordings=None,
                                 extra={"n_rows": summary["n_rows"],
                                        "n_contacts": summary["n_contacts"],
                                        "n_bands": summary["n_bands"]},
                                 root=_SHARED_CACHE_DIR_OVERRIDE)
    summary["store_key"] = _cache_store.product_key(_amp.POOLED_KIND, uid, sig)
    summary["written"] = _cache_store.read_stamp(_amp.POOLED_KIND, uid, sig,
                                                 root=_SHARED_CACHE_DIR_OVERRIDE) is not None
    return summary


def pooled_shape_stored_for_current_key(participant, min_points=None):
    """Whether the pooled table exists under the CURRENT key (rule version, recording set). Asked
    before the comparison is built, like `run_points_stored_for_current_key`: a version bump of
    the table (v2, 2026-09-11) would otherwise never be written in the steady state, because the
    truncated build refuses to derive it and nothing forced a full build."""
    from . import amplitude_effect as _amp
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        return False
    uid = str(getattr(participant, "uid", participant))
    sig = pooled_shape_signature(participant, tiles_key=tiles_key, min_points=min_points)
    return _cache_store.read_stamp(_amp.POOLED_KIND, uid, sig, root=_SHARED_CACHE_DIR_OVERRIDE) is not None


def pooled_shape_if_stored(participant):
    """The newest stored pooled within-visit table for this participant, or None.

    `load_newest` rather than a keyed lookup, for the same reason decision 41 established: the page
    reading this cannot know the key the writer built it under. It is read on EVERY request,
    including the ones whose own build was truncated -- that is the whole point, since the stored
    table was pooled from every run and so gives the same answer either way.
    """
    from . import amplitude_effect as _amp
    try:
        payload, _stamp = _cache_store.load_newest(_amp.POOLED_KIND,
                                                   str(getattr(participant, "uid", participant)),
                                                   consumer="closed_loop",
                                                   root=_SHARED_CACHE_DIR_OVERRIDE)
        return payload
    except Exception:                                  # noqa: BLE001 - a miss is not an error
        _log.warning("closed-loop: the stored pooled within-visit table could not be read for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        return None


def run_points_signature(participant, *, tiles_key):
    """The key for the stored per-run points: the same inputs as the pooled table (the tile entry,
    the recording set) plus this table's own rule version. Nothing decoded enters it."""
    from StimOptimizer.routines import within_visit as _wv
    from . import run_points as _rp
    return (_rp.KIND, _rp.RULE_VERSION, str(getattr(participant, "uid", participant)), tiles_key,
            recording_set_signature(participant), "all_runs",
            float(_wv.PRE_CHANGE_WINDOW_S), int(_wv.MIN_CHUNKS_PRE_CHANGE))


def write_run_points(participant, build, *, is_every_run):
    """Store every run's points from a FULL-run comparison (redesign decisions 5 and 10).

    Refuses a truncated build for the reason `write_pooled_shape` gives: a stored table built from
    the page's four newest runs would look complete and be missing every older visit.
    """
    from . import run_points as _rp
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                # pragma: no cover - depends on the runner
        from CacheStore import provenance as _prov

    summary = {"written": False, "n_rows": 0, "n_runs": 0, "store_key": None}
    if not is_every_run:
        summary["reason"] = ("the comparison was built from only the runs the page draws, and a "
                             "points table from a fraction of the visits must not be stored")
        return summary
    if not build or not build.get("comparisons"):
        summary["reason"] = ((build or {}).get("absent_reason")
                             or "no run of stepped current to store")
        return summary

    table = _rp.run_points_table_from_build(build)
    summary["n_rows"] = int(len(table))
    if not len(table):
        summary["reason"] = "the comparison produced no rows to store"
        return summary
    summary["n_runs"] = int(table["run"].nunique())

    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        summary["reason"] = "no tile entry key, so the table was derived but not stored"
        return summary
    uid = str(getattr(participant, "uid", participant))
    sig = run_points_signature(participant, tiles_key=tiles_key)
    prov = _prov.flatten([_prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")])
    _cache_store.store_if_absent(_rp.KIND, uid, sig, lambda: table,
                                 writer="closed_loop", trigger="deployment_report",
                                 provenance=prov, n_recordings=None,
                                 extra={"n_rows": summary["n_rows"], "n_runs": summary["n_runs"]},
                                 root=_SHARED_CACHE_DIR_OVERRIDE)
    summary["store_key"] = _cache_store.product_key(_rp.KIND, uid, sig)
    summary["written"] = _cache_store.read_stamp(_rp.KIND, uid, sig,
                                                 root=_SHARED_CACHE_DIR_OVERRIDE) is not None
    return summary


def run_points_stored_for_current_key(participant):
    """Whether the per-run points table exists under the CURRENT recording set's key.

    Asked before the comparison is built, the same way `amplitude_effect_if_stored` is: a request
    whose table is already on disk builds only the runs the page draws; one whose table is missing
    -- the first request after a new upload, or the first ever -- builds every run so the table
    can be written from a full build. Without this the steady-state page would refuse to write
    the table forever, which is what the first live run of this code did (2026-09-11).
    """
    from . import run_points as _rp
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        return False
    uid = str(getattr(participant, "uid", participant))
    sig = run_points_signature(participant, tiles_key=tiles_key)
    return _cache_store.read_stamp(_rp.KIND, uid, sig, root=_SHARED_CACHE_DIR_OVERRIDE) is not None


def run_points_if_stored(participant):
    """The newest stored per-run points table for this participant, or None (same reading rule
    as `pooled_shape_if_stored`: the newest by name, since the page cannot rebuild the key)."""
    from . import run_points as _rp
    try:
        payload, _stamp = _cache_store.load_newest(_rp.KIND,
                                                   str(getattr(participant, "uid", participant)),
                                                   consumer="closed_loop",
                                                   root=_SHARED_CACHE_DIR_OVERRIDE)
        return payload
    except Exception:                                  # noqa: BLE001 - a miss is not an error
        _log.warning("closed-loop: the stored per-run points table could not be read for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        return None


def three_source_pooled_for_participant(participant):
    """The pooled-by-side view alone, from the stored tables, for the page's background fetch.

    Reads what the last FULL report wrote (`write_run_points`, `write_pooled_shape`) and groups
    it; builds nothing. When nothing is stored yet the payload says so and the page shows that
    sentence; the next full report writes both tables and the fetch after it finds them.
    """
    from . import run_points as _rp
    view = _rp.pooled_view_payload(run_points_if_stored(participant),
                                   pooled_shape_if_stored(participant))
    view["available"] = True
    view["cache_status"] = _cache_status_or_reason(participant)
    return view


# ---------------------------------------------------------------------------------------------
# THE CLOSED-LOOP SIMULATION (Phase 8 of the 2026-09-11 redesign; simulation.py)
# ---------------------------------------------------------------------------------------------
def simulation_inputs_for_participant(uid, *, contact, centre_hz, hemisphere, epochs=None,
                                      loaded=None):
    """The series the simulation runs over: every 3 s piece of voltage trace on `contact`, its
    band power at the stored centre nearest `centre_hz`, and the amplitude the device was
    delivering on `hemisphere` at that moment.

    WHY THE TILES AND NOT THE REPORT'S OWN SERIES. The page's replay runs over the joined table --
    one spectrum per recording, chronic snapshots minutes apart -- and on RCS08 correctly refuses
    to run, because samples 230 s apart cannot resolve a 150 s ramp (the duty-cycle card's own
    "not answerable at this sampling cadence"). The 3 s tiles the three-source comparison's
    time-domain route already reads resolve it fifty times over, and they are the same calibrated
    quantity (device-unit LSB) the thresholds were placed on (decision 45).

    THE AMPLITUDE comes from the device's own per-sample current record where a piece falls inside
    a streaming recording (the same clock as the power; `three_source_response.read_device_current`),
    and from the settings epochs otherwise. A piece with neither is dropped and counted rather than
    given an amplitude it did not have.
    """
    from Biomarkers import bravo_service as bs
    from Biomarkers.routines import availability as _avail
    from . import three_source_response as _3src

    out = {"t": np.empty(0), "power": np.empty(0), "amp_obs": np.empty(0), "n_pieces": 0,
           "n_unusable_pieces": 0, "n_dropped_no_amplitude": 0, "n_from_device_current": 0,
           "n_from_epochs": 0, "centre_used_hz": None, "contact": str(contact)}
    # THE RECORDINGS THE SAME REQUEST ALREADY DECODED are taken from ``loaded`` when the
    # three-source build handed them over (review C8, 2026-09-12); anything it did not load is
    # loaded here as before. ``_load_recordings`` decodes from disk on every call, so without this
    # every report that wrote a simulation decoded the same files twice.
    loaded = loaded if isinstance(loaded, dict) else {}
    power = loaded.get("power") if loaded.get("power") is not None else \
        bs._load_recordings(uid, bs.POWERDOMAIN_TYPES)
    td = loaded.get("td") if loaded.get("td") is not None else \
        bs._load_recordings(uid, bs.TIMEDOMAIN_TYPES)
    psd = loaded.get("psd") if loaded.get("psd") is not None else \
        bs._load_recordings(uid, bs.AVAILABILITY_PSD_TYPES)
    cache = loaded.get("cache")
    if cache is None:
        chans = list(dict.fromkeys(_avail._canon_channel(c) for c in bs._derive_chan_order(td)))
        cache = bs._raw_lsb_cache_cached(
            uid, chans, list(td) + list(psd),
            bs._event_psd_lsb_blocks(uid, sensing_index=bs._build_sensing_config_index(list(td))),
            montage_psd_blocks=bs._montage_psd_lsb_blocks(uid, montage_recordings=psd))
    entry = cache.get(str(contact)) or {}
    tiles = entry.get("td") or {}
    t = np.asarray(tiles.get("t", []), dtype=float)
    lsb = np.asarray(tiles.get("lsb", np.empty((0, 0))), dtype=float)
    if t.size == 0 or lsb.ndim != 2 or lsb.shape[0] != t.size:
        out["absent_reason"] = f"no 3 s voltage-trace pieces are stored for contact {contact}"
        return out
    centres = np.asarray(entry.get("centres_hz", entry.get("centers_hz", [])), dtype=float)
    if centres.size != lsb.shape[1]:
        out["absent_reason"] = "the tile entry's centre list does not match its band-power columns"
        return out
    j = int(np.argmin(np.abs(centres - float(centre_hz))))
    out["centre_used_hz"] = float(centres[j])
    p = lsb[:, j].astype(float)
    ok = np.ones(t.size, dtype=bool)
    if tiles.get("ok") is not None:
        ok &= np.asarray(tiles["ok"], dtype=bool)
    if tiles.get("saturated") is not None:
        ok &= ~np.asarray(tiles["saturated"], dtype=bool)
    out["n_pieces"] = int(t.size)
    out["n_unusable_pieces"] = int((~ok).sum())
    p = np.where(ok, p, np.nan)                     # unusable pieces are MISSING estimates, held

    # the amplitude in force: the device's own current record first
    side = str(hemisphere).upper()
    amp = np.full(t.size, np.nan)
    src = np.zeros(t.size, dtype=int)
    current = _3src.read_device_current(power)
    for block in current.get("blocks", []):
        bt = np.asarray(block["t"], dtype=float)
        names = [c for c in block["mA"] if str(c).upper().endswith(side)]
        if bt.size < 2 or not names:
            continue
        ba = np.asarray(block["mA"][names[0]], dtype=float)
        lo, hi = float(bt[0]), float(bt[-1])
        m = (t >= lo) & (t <= hi) & ~np.isfinite(amp)
        if not m.any():
            continue
        k = np.clip(np.searchsorted(bt, t[m]), 0, bt.size - 1)
        amp[m] = ba[k]
        src[m] = 1
    # then the settings epochs -- through the ONE epoch assignment the joined table uses
    # (`_assign_epoch`; review C9, 2026-09-12). This used to be a private copy with a closed end
    # (`t <= t_end` where `_assign_epoch` is half-open) and without the nanosecond cast that
    # function documents, so the report and the simulation could have disagreed about which
    # epoch a piece was in; measured on RCS08 the two agree on every piece today (0 differences,
    # see the review's implementation report), and now they cannot drift.
    if epochs is not None and len(epochs):
        col = canonical_amp_col(hemisphere)
        if col not in epochs.columns:
            col = resolve_setting_column(epochs.columns, "amp", hemisphere)
        if col is not None and "t_start" in epochs.columns and "t_end" in epochs.columns:
            ea = pd.to_numeric(epochs[col], errors="coerce").to_numpy(dtype=float)
            need = ~np.isfinite(amp)
            k = _assign_epoch(t[need], epochs)
            inside = (k >= 0) & np.isfinite(np.where(k >= 0, ea[np.clip(k, 0, None)], np.nan))
            idx = np.flatnonzero(need)[inside]
            amp[idx] = ea[k[inside]]
            src[idx] = 2
    keep = np.isfinite(amp)
    out["n_dropped_no_amplitude"] = int((~keep).sum())
    out["n_from_device_current"] = int((src == 1).sum())
    out["n_from_epochs"] = int((src == 2).sum())
    out["t"], out["power"], out["amp_obs"] = t[keep], p[keep], amp[keep]
    return out


def _run_windows_epoch_s(points, *, contact):
    """(start, end) epoch seconds of every run of stepped current on `contact`, from the STORED
    per-run points table (which always holds every run; the page's own build is truncated to
    four once the write-back entries exist, and an answer that depended on that would depend on
    cache state -- decision 103's own complaint). Local timestamps are America/Los_Angeles."""
    wins = []
    if points is None or not len(points) or "window_end_local" not in points.columns:
        return wins
    sub = points[points["sensing_contact"].astype(str) == str(contact)]
    for _, r in sub.drop_duplicates("run").iterrows():
        try:
            lo = pd.Timestamp(r["window_start_local"], tz="America/Los_Angeles").timestamp()
            hi = pd.Timestamp(r["window_end_local"], tz="America/Los_Angeles").timestamp()
            wins.append((float(lo), float(hi)))
        except Exception:                               # noqa: BLE001
            # The ambiguous hour of a daylight-saving change is one way this raises; the run is
            # dropped from the simulation's windows, and since review C7 that is logged.
            _log.warning("closed-loop: run %r on %s has a window the simulation could not "
                         "parse (%r to %r); it is left out of the simulation",
                         r.get("run"), contact, r.get("window_start_local"),
                         r.get("window_end_local"), exc_info=True)
            continue
    return wins


def _run_points_for(points, *, contact, centre_hz):
    """(current, settled power, run label) of the time-domain route on one contact at the stored
    centre nearest `centre_hz`, from the stored per-run points table -- what M3 resamples."""
    from . import run_points as _rp
    if points is None or not len(points):
        return None
    sub = points[(points["sensing_contact"].astype(str) == str(contact))
                 & (points["source"].astype(str) == _rp.ROUTE_TIME_DOMAIN)
                 & points["settled_band_power_device_units"].notna()]
    if sub.empty:
        return None
    centres = sub["band_centre_hz"].astype(float)
    c = float(centres.iloc[int(np.argmin(np.abs(centres.to_numpy() - float(centre_hz))))])
    sub = sub[np.isclose(centres, c)]
    return (sub["current_mA"].astype(float).to_numpy(),
            sub["settled_band_power_device_units"].astype(float).to_numpy(),
            sub["run"].astype(str).tolist())


def simulation_signature(participant, *, tiles_key, contact, centre_hz, hemisphere, power_scale,
                         plan, n_resample, seed):
    """The key: the tile entry and recording set (the series), the candidate, the thresholds and
    limits the controller runs with, the resampling settings, and this module's rule version."""
    from . import simulation as _sim
    from . import amplitude_effect as _amp_sig
    from . import timing_recommendation as _tr_sig
    # The pooled table's rule version is IN the key (2026-09-12): the simulation closes its loop
    # through that table's fitted curve, so a table rebuilt under a new rule must not be served
    # a simulation built from the old one -- the decision-107 class of defect, one table over.
    # The RECOMMENDED-timing table's own version is folded in the same way (T2, 2026-09-13): an
    # edit to `RECORD_DERIVED_TIMING_MS` must invalidate a stored replay built under the old
    # numbers. `recording_set_signature` already changes when a new session report is ingested
    # (session reports are Recording rows), which is what invalidates the PROGRAMMED-timing half.
    return (_sim.KIND, _sim.RULE_VERSION, _amp_sig.POOLED_RULE_VERSION, _tr_sig.TABLE_VERSION,
            str(getattr(participant, "uid", participant)), tiles_key,
            recording_set_signature(participant), str(contact), round(float(centre_hz), 3),
            str(hemisphere), str(power_scale),
            # the LIMITS the controller runs with -- the capture currents held at or below the
            # safe ceiling (decision 306) -- so a capped plan never serves a replay run to 4.8 mA
            tuple(None if v is None else round(float(v), 6)
                  for v in (plan.upper, plan.lower, *plan.amplitude_limits())),
            int(n_resample), int(seed))


# --- the two timing regimes T2 replays (2026-09-13) --------------------------------------------
#: `replay.DEFAULT_PARAMS`'s field name -> the field name it reads from a timing dict, whether
#: that dict is `device_facts.programmed_closed_loop_timing`'s per-side entry (both onset timers,
#: `onset_upper_ms`/`onset_lower_ms`) or `timing_recommendation.for_participant`'s per-participant
#: table (the same two field names, decision 150). THE REPLAY CARRIES ONE ONSET TIMER, NOT TWO --
#: `replay.DEFAULT_PARAMS["onset_ms"]` applies to both directions -- so the upper threshold's own
#: onset is used and the lower one is not silently averaged into it.
_SIM_PARAM_FROM_TIMING_FIELD = (
    ("averaging_ms", "averaging_ms"),
    ("onset_ms", "onset_upper_ms"),
    ("detection_blanking_ms", "detection_blanking_ms"),
    ("transition_up_ms", "transition_up_ms"),
    ("transition_down_ms", "transition_down_ms"),
)


def _simulation_params_from_timing_dict(values_by_field):
    """`{replay param name: float ms}` for every field a timing dict states; a field the dict does
    not carry is left out, so `simulate_series` falls back to `replay.DEFAULT_PARAMS` (the
    white-paper Dual Threshold value) for it rather than being handed a fabricated number."""
    out = {}
    for repl_key, dev_key in _SIM_PARAM_FROM_TIMING_FIELD:
        v = (values_by_field or {}).get(dev_key)
        if v is None:
            continue
        try:
            out[repl_key] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _timing_runs_for_simulation(uid, hemisphere, device_facts):
    """The two timing regimes T2 replays (contest_2026-09-13_SYNTHESIS.md section 4): what the
    device is PROGRAMMED to run today on the candidate's own hemisphere, and this participant's
    record-derived RECOMMENDATION (decision 150). Reads `device_facts["active_sensing_group_timing"]`
    -- already computed once by `report_for_participant` -- rather than looking the session report
    up again. Either regime may be wholly or partly absent; an absent field falls back to the
    white-paper default inside `simulate_series`, and the source sentence below says so rather than
    silently substituting the other regime's numbers."""
    from . import timing_recommendation as _tr

    prog_all = (device_facts or {}).get("active_sensing_group_timing")
    programmed_raw = (prog_all or {}).get(hemisphere) if isinstance(prog_all, dict) else None
    programmed_params = _simulation_params_from_timing_dict(programmed_raw)
    programmed_source = (
        f"measured: the device's newest session report, the active sensing group's own programmed "
        f"timing on {hemisphere} (the onset shown is the upper threshold's own onset timer; the "
        "replay applies one onset timer to both directions)"
        if programmed_raw else
        "no active sensing group with a programmed timing was found for this hemisphere on this "
        "participant's newest session report; the white-paper Dual Threshold default is used")

    rec_raw = _tr.for_participant(uid) or {}
    rec_values = {k: (v or {}).get("value_ms") for k, v in rec_raw.items()}
    recommended_params = _simulation_params_from_timing_dict(rec_values) if rec_raw else dict(programmed_params)
    recommended_source = (_tr.RECORD_DERIVED_PROVENANCE if rec_raw else
                          "no record-derived recommendation is on file for this participant; the "
                          "same timing as \"as programmed today\" is used instead")

    # WHICH OF THE RECOMMENDED VALUES THE RECORD CANNOT DECIDE (C3 of the 2026-09-15 review,
    # decision 200): the recommendation table grades each field; the ones graded "Low" (the two
    # transitions and the detection blanking on RCS08) went into the replay with no mention on
    # the card's headline. The replay's own parameter names, in the replay's order, so the
    # simulation payload can say "using three timing values the record cannot decide". What the
    # device RUNS today is a measurement, not a recommendation: nothing to qualify.
    low = [repl for repl, dev_key in _SIM_PARAM_FROM_TIMING_FIELD
           if str(((rec_raw.get(dev_key) or {}).get("confidence") or "")).lower() == "low"]
    return {
        "programmed": {"label": "As programmed today", "params": programmed_params,
                       "source": programmed_source, "low_confidence_fields": [],
                       "timing_qualifier": None},
        "recommended": {"label": "Record-derived recommendation", "params": recommended_params,
                        "source": recommended_source, "low_confidence_fields": low,
                        "timing_qualifier": _timing_qualifier(low)},
    }


_TIMING_FIELD_WORDS = {"averaging_ms": "averaging", "onset_ms": "onset",
                       "detection_blanking_ms": "detection blanking",
                       "transition_up_ms": "transition up", "transition_down_ms": "transition down"}
_COUNT_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def _timing_qualifier(low_fields):
    """The sentence the simulation card prepends to its headline when the recommended regime
    rests on timing values the record could not decide, or None when it rests on none."""
    if not low_fields:
        return None
    words = [_TIMING_FIELD_WORDS.get(f, f) for f in low_fields]
    n = _COUNT_WORDS.get(len(words), str(len(words)))
    return (f"using {n} timing value{'s' if len(words) != 1 else ''} the record cannot decide "
            f"({', '.join(words)}; graded Low on the parameter card)")


def write_simulation(participant, *, rep, build, candidate, hemisphere, power_scale, epochs,
                     n_resample=None, seed=0, loaded=None, device_facts=None):
    """Run the simulation for the report's first candidate TWICE -- once under the timing the
    device is programmed to run today, once under this participant's record-derived recommendation
    (T2, 2026-09-13, contest_2026-09-13_SYNTHESIS.md section 4) -- and store both under one entry
    (kind `closed_loop_simulation`), citing the raw roots its inputs cite. The summary says what
    was written or why not; the payload itself is read back by
    `closed_loop_simulation_for_participant` when the page asks for it after its first figures are
    up. `device_facts` is the `dev` dict `report_for_participant` already built (it carries
    `active_sensing_group_timing`); passing it here avoids a second, redundant session-report read."""
    from . import simulation as _sim
    from . import replay as _replay
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                # pragma: no cover - depends on the runner
        from CacheStore import provenance as _prov

    summary = {"written": False, "store_key": None, "n_pieces": 0, "seconds": None}
    plan = getattr(rep, "threshold", None)
    if plan is None or plan.upper is None or plan.lower is None:
        summary["reason"] = "no thresholds were placed for this candidate, so there is no controller to run"
        return summary
    if None in plan.amplitude_limits():
        summary["reason"] = "the plan has no capture amplitude range, which the limits are held to"
        return summary
    contact = (candidate or {}).get("channel")
    centre = (candidate or {}).get("center_hz")
    if contact is None or centre is None:
        summary["reason"] = "the candidate carries no sensing contact or band centre"
        return summary
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        summary["reason"] = "no tile entry key, so nothing could be run or stored"
        return summary
    n_resample = _sim.DEFAULT_N_RESAMPLE if n_resample is None else int(n_resample)
    uid = str(getattr(participant, "uid", participant))
    sig = simulation_signature(participant, tiles_key=tiles_key, contact=contact, centre_hz=centre,
                               hemisphere=hemisphere, power_scale=power_scale, plan=plan,
                               n_resample=n_resample, seed=seed)
    summary["store_key"] = _cache_store.product_key(_sim.KIND, uid, sig)
    if _cache_store.read_stamp(_sim.KIND, uid, sig, root=_SHARED_CACHE_DIR_OVERRIDE) is not None:
        summary["written"] = True
        summary["already_stored"] = True
        return summary

    import time as _time
    t0 = _time.perf_counter()
    inputs = simulation_inputs_for_participant(uid, contact=contact, centre_hz=float(centre),
                                               loaded=loaded,
                                               hemisphere=hemisphere, epochs=epochs)
    summary["n_pieces"] = int(inputs.get("n_pieces", 0))
    if inputs.get("absent_reason") or not len(inputs["t"]):
        summary["reason"] = inputs.get("absent_reason") or "no usable pieces with a known amplitude"
        return summary
    from . import amplitude_effect as _amp
    pooled_table = pooled_shape_if_stored(participant)
    pooled_row = _amp.pooled_row(pooled_table, contact, float(centre))
    stored_points = run_points_if_stored(participant)
    points = _run_points_for(stored_points, contact=contact, centre_hz=float(centre))
    run_windows = _run_windows_epoch_s(stored_points, contact=contact)

    # THE TWO TIMING REGIMES (T2, 2026-09-13): the same series, thresholds and response curve, run
    # once under what the device is programmed to run today and once under this participant's
    # record-derived recommendation, so the card can show both rather than silently replacing one
    # with the other. `run_models` already accepts `params=`; each regime just supplies a different
    # (possibly partial) override of `replay.DEFAULT_PARAMS`.
    timing = _timing_runs_for_simulation(uid, hemisphere, device_facts)
    runs = {}
    for _key, _meta in timing.items():
        runs[_key] = _sim.run_models(inputs["t"], inputs["power"], inputs["amp_obs"], plan, pooled_row,
                                     run_points=points, run_windows=run_windows,
                                     n_resample=n_resample, seed=seed,
                                     params=(_meta["params"] or None),
                                     min_points_resample=_amp.MIN_POINTS_CURVATURE)
        runs[_key]["timing_label"] = _meta["label"]
        runs[_key]["timing_source"] = _meta["source"]
        runs[_key]["timing_params_ms"] = dict(_replay.DEFAULT_PARAMS, **(_meta["params"] or {}))
        # C3 (decision 200): which of this regime's timing values the record cannot decide
        runs[_key]["timing_low_confidence_fields"] = list(_meta.get("low_confidence_fields") or [])
        runs[_key]["timing_qualifier"] = _meta.get("timing_qualifier")

    payload = {"gates_nothing": True, "rule_version": _sim.RULE_VERSION,
              "timing_runs": runs, "primary_run": "recommended"}
    payload["inputs"] = {k: inputs[k] for k in ("n_pieces", "n_unusable_pieces", "n_dropped_no_amplitude",
                                                "n_from_device_current", "n_from_epochs",
                                                "centre_used_hz", "contact")}
    payload["candidate"] = {"channel": str(contact), "center_hz": float(centre), "hemisphere": str(hemisphere),
                            "power_scale": str(power_scale)}
    payload["pooled_row_found"] = pooled_row is not None
    payload["seconds"] = _time.perf_counter() - t0
    summary["seconds"] = payload["seconds"]

    chain = [_prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")]
    for kind in (_amp.POOLED_KIND,):
        try:
            _p, stamp = _cache_store.load_newest(kind, uid, consumer="closed_loop",
                                                 root=_SHARED_CACHE_DIR_OVERRIDE)
            chain += list((stamp or {}).get("provenance") or [])
        except Exception:                               # noqa: BLE001 -- the tiles alone then
            _log.warning("closed-loop: the %s chain could not be read for %s; the simulation's "
                         "provenance cites the tiles alone", kind, uid, exc_info=True)
    _primary = runs.get("recommended") or {}
    _cache_store.store_if_absent(_sim.KIND, uid, sig, lambda: payload,
                                 writer="closed_loop", trigger="deployment_report",
                                 provenance=_prov.flatten(chain), n_recordings=None,
                                 extra={"n_pieces": summary["n_pieces"], "active_model": _primary.get("active_model"),
                                        "refused": bool(_primary.get("refused")),
                                        "candidate": _simulation_candidate_tag(contact, centre, hemisphere)},
                                 root=_SHARED_CACHE_DIR_OVERRIDE)
    summary["written"] = _cache_store.read_stamp(_sim.KIND, uid, sig, root=_SHARED_CACHE_DIR_OVERRIDE) is not None
    summary["active_model"] = _primary.get("active_model")
    summary["refused"] = bool(_primary.get("refused"))
    summary["timing_runs"] = {k: {"refused": bool(v.get("refused")), "active_model": v.get("active_model"),
                                  "timing_source": v.get("timing_source")} for k, v in runs.items()}
    return summary


def _simulation_candidate_tag(contact, centre_hz, hemisphere):
    """What the sidecar records the simulation is FOR, so a read can pick the right entry: the
    store keeps several per participant (one per candidate) and the newest is not necessarily the
    one the page is showing."""
    try:
        c = round(float(centre_hz), 3)
    except (TypeError, ValueError):
        c = None
    return {"channel": str(contact), "center_hz": c, "hemisphere": str(hemisphere)}


def simulation_if_stored(participant, candidate=None, *, hemisphere="Left"):
    """The newest stored simulation for this participant -- for THIS candidate when one is given
    (matched on the sidecar's `candidate` tag), else the newest of any -- or None."""
    from . import simulation as _sim
    match = None
    if candidate and candidate.get("channel") is not None and candidate.get("center_hz") is not None:
        want = _simulation_candidate_tag(candidate["channel"], candidate["center_hz"],
                                         candidate.get("actuated_hemisphere")
                                         or candidate.get("sensing_hemisphere") or hemisphere)
        match = lambda meta: (meta.get("extra") or {}).get("candidate") == want  # noqa: E731
    try:
        payload, _stamp = _cache_store.load_newest(_sim.KIND, str(getattr(participant, "uid", participant)),
                                                   consumer="closed_loop",
                                                   root=_SHARED_CACHE_DIR_OVERRIDE, match=match)
        return payload
    except Exception:                                  # noqa: BLE001 - a miss is not an error
        _log.warning("closed-loop: the stored simulation could not be read for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        return None


def closed_loop_simulation_for_participant(participant, candidate=None, *, hemisphere="Left"):
    """The stored simulation for this candidate alone, for the page's background fetch after its
    first figures. Builds nothing: the report writes it, this reads it back."""
    payload = simulation_if_stored(participant, candidate, hemisphere=hemisphere)
    if payload is None:
        # `refused`/`models` kept alongside the newer `timing_runs`/`primary_run` (2026-09-13, T2)
        # so a caller written against either shape reads the same "nothing stored yet" answer.
        payload = {"gates_nothing": True, "refused": True, "models": {},
                   "timing_runs": {}, "primary_run": None,
                   "absent_reason": ("no simulation is stored for this configuration yet; the report "
                                     "writes one the next time it runs with thresholds placed for it")}
    payload = dict(payload)
    payload["available"] = True
    payload["cache_status"] = _cache_status_or_reason(participant)
    return payload


# ---------------------------------------------------------------------------------------------
# THE CONFIRMATIONS-AND-SEPARATION DESIGN RULE (T3, 2026-09-13; design_rule.py)
# ---------------------------------------------------------------------------------------------
def design_rule_signature(participant, *, tiles_key, contact, centre_hz, hemisphere, upper, lower):
    """The key: the tile entry and recording set (the series the model is fit on), the candidate,
    the pair's MIDPOINT (the noise simulation holds the level there and answers the separation, so
    two pairs with one midpoint are one question -- decision 180's placement fits at the median and
    the record pair it places has that midpoint, one fit), and this file's own rule version."""
    from . import design_rule as _dr
    mid = (None if upper is None or lower is None
           else round(0.5 * (float(upper) + float(lower)), 6))
    return (_dr.KIND, _dr.RULE_VERSION, str(getattr(participant, "uid", participant)), tiles_key,
            recording_set_signature(participant), str(contact), round(float(centre_hz), 3),
            str(hemisphere), mid)


def _place_thresholds_from_record(participant, rep, cands, *, hemisphere, loaded=None, epochs=None):
    """Decision 180: return ``(plan, placement)`` where ``plan`` is ``rep.threshold`` re-placed from
    the record when that is possible and the capture plan (labelled) when it is not.

    Steps, in order: the median averaged reading at the recommended averaging (T4's re-averaging);
    the design rule fitted with its level at that median (T3; stored under a key that depends on the
    midpoint, so the record pair -- whose midpoint is the median -- reuses it); the pair.
    """
    from . import threshold_placement as _tpl
    from . import timing_recommendation as _tr
    plan = getattr(rep, "threshold", None)
    if plan is None or plan.upper is None or plan.lower is None:
        return plan, {"available": False, "rule": "record",
                      "reason": "no capture pair was placed, so there is nothing to re-place"}
    c0 = (cands[0] or {}) if cands else {}
    contact, centre = c0.get("channel"), c0.get("center_hz")
    if contact is None or centre is None:
        return _tpl.apply(plan, {"available": False, "reason": "the candidate carries no sensing "
                                                                "contact or band centre"}), \
            {"available": False, "reason": "the candidate carries no sensing contact or band centre"}
    uid = str(getattr(participant, "uid", participant))
    timing = _tr.for_participant(uid) or {}
    avg_ms = (timing.get("averaging_ms") or {}).get("value_ms")
    onset_ms = (timing.get("onset_upper_ms") or {}).get("value_ms")
    if not avg_ms or not onset_ms:
        pl = {"available": False, "rule": "record",
              "reason": "no recommended averaging or onset duration is in force for this participant"}
        return _tpl.apply(plan, pl), pl
    inputs = simulation_inputs_for_participant(uid, contact=contact, centre_hz=float(centre),
                                               loaded=loaded, hemisphere=hemisphere, epochs=epochs)
    if inputs.get("absent_reason") or not len(inputs["t"]):
        pl = {"available": False, "rule": "record",
              "reason": inputs.get("absent_reason") or "no usable pieces for this contact"}
        return _tpl.apply(plan, pl), pl
    med = _tpl.median_level(inputs["t"], inputs["power"], averaging_s=float(avg_ms) / 1000.0)
    if not med.get("available"):
        pl = {"available": False, "rule": "record", "reason": med.get("reason"), "median": med}
        return _tpl.apply(plan, pl), pl
    # the design rule, fitted (or served) with its level at the median
    import dataclasses as _dc
    provisional = _dc.replace(plan, upper=float(med["median"]), lower=float(med["median"]))
    dr_summary = write_design_rule(participant, candidate=c0, hemisphere=hemisphere,
                                   threshold_plan=provisional, loaded=loaded, epochs=epochs)
    dr_payload = design_rule_if_stored(participant, c0, hemisphere=hemisphere)
    rows = [] if not dr_payload or dr_payload.get("refused") else (dr_payload.get("table") or [])
    placement = _tpl.record_pair(median=med["median"], design_rows=rows,
                                 averaging_ms=avg_ms, onset_ms=onset_ms)
    placement["median"] = med
    placement["design_rule"] = {"store_key": dr_summary.get("store_key"),
                                "model": (dr_payload or {}).get("model"),
                                "refused": bool((dr_payload or {}).get("refused")) if dr_payload else None,
                                "reason": dr_summary.get("reason")}
    placement["capture_upper"], placement["capture_lower"] = plan.upper, plan.lower
    new_plan = _tpl.apply(plan, placement, observed_series=inputs["power"])
    placement["placement_rule"] = new_plan.placement_rule
    return new_plan, placement


def write_design_rule(participant, *, candidate, hemisphere, threshold_plan, loaded=None,
                      epochs=None):
    """Fit the design-rule model on the same 3 s tiles the simulation reads and store the
    averaging x onset separation table, citing the tiles as its raw root. Refuses, rather than
    fits on nothing, exactly where `write_simulation` refuses: no thresholds, no candidate, no
    tile entry, or no usable pieces. A matching key is served from the store rather than refit."""
    from . import design_rule as _dr
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                # pragma: no cover - depends on the runner
        from CacheStore import provenance as _prov

    summary = {"written": False, "store_key": None, "seconds": None}
    plan = threshold_plan
    if plan is None or plan.upper is None or plan.lower is None:
        summary["reason"] = ("no thresholds were placed for this candidate, so there is nothing "
                             "for a separation rule to be measured against")
        return summary
    contact = (candidate or {}).get("channel")
    centre = (candidate or {}).get("center_hz")
    if contact is None or centre is None:
        summary["reason"] = "the candidate carries no sensing contact or band centre"
        return summary
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        summary["reason"] = "no tile entry key, so nothing could be run or stored"
        return summary
    uid = str(getattr(participant, "uid", participant))
    sig = design_rule_signature(participant, tiles_key=tiles_key, contact=contact,
                                centre_hz=centre, hemisphere=hemisphere, upper=plan.upper,
                                lower=plan.lower)
    summary["store_key"] = _cache_store.product_key(_dr.KIND, uid, sig)
    if _cache_store.read_stamp(_dr.KIND, uid, sig, root=_SHARED_CACHE_DIR_OVERRIDE) is not None:
        summary["written"] = True
        summary["already_stored"] = True
        return summary

    import time as _time
    t0 = _time.perf_counter()
    inputs = simulation_inputs_for_participant(uid, contact=contact, centre_hz=float(centre),
                                               loaded=loaded, hemisphere=hemisphere, epochs=epochs)
    if inputs.get("absent_reason") or not len(inputs["t"]):
        summary["reason"] = inputs.get("absent_reason") or "no usable pieces with a known amplitude"
        return summary
    payload = _dr.design_rule_for_series(inputs["t"], inputs["power"], inputs["amp_obs"],
                                         upper=plan.upper, lower=plan.lower)
    payload["candidate"] = {"channel": str(contact), "center_hz": float(centre),
                            "hemisphere": str(hemisphere)}
    payload["seconds"] = _time.perf_counter() - t0
    summary["seconds"] = payload["seconds"]

    chain = [_prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")]
    _cache_store.store_if_absent(
        _dr.KIND, uid, sig, lambda: payload, writer="closed_loop", trigger="deployment_report",
        provenance=_prov.flatten(chain), n_recordings=None,
        extra={"refused": bool(payload.get("refused")), "model": payload.get("model"),
              "candidate": _simulation_candidate_tag(contact, centre, hemisphere)},
        root=_SHARED_CACHE_DIR_OVERRIDE)
    summary["written"] = (_cache_store.read_stamp(_dr.KIND, uid, sig,
                                                  root=_SHARED_CACHE_DIR_OVERRIDE) is not None)
    summary["refused"] = bool(payload.get("refused"))
    summary["model"] = payload.get("model")
    return summary


def design_rule_if_stored(participant, candidate=None, *, hemisphere="Left"):
    """The newest stored design-rule table for this candidate, matched on the sidecar's
    `candidate` tag exactly as `simulation_if_stored` matches -- or ``None``."""
    from . import design_rule as _dr
    match = None
    if candidate and candidate.get("channel") is not None and candidate.get("center_hz") is not None:
        want = _simulation_candidate_tag(candidate["channel"], candidate["center_hz"],
                                         candidate.get("actuated_hemisphere")
                                         or candidate.get("sensing_hemisphere") or hemisphere)
        match = lambda meta: (meta.get("extra") or {}).get("candidate") == want  # noqa: E731
    try:
        payload, _stamp = _cache_store.load_newest(_dr.KIND,
                                                   str(getattr(participant, "uid", participant)),
                                                   consumer="closed_loop",
                                                   root=_SHARED_CACHE_DIR_OVERRIDE, match=match)
        return payload
    except Exception:                                  # noqa: BLE001 - a miss is not an error
        _log.warning("closed-loop: the stored design-rule table could not be read for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        return None


# ---------------------------------------------------------------------------------------------
# THE BLOCK-BOOTSTRAP ROBUSTNESS CHECK (T5, 2026-09-13; robustness.py)
# ---------------------------------------------------------------------------------------------
def robustness_signature(participant, *, tiles_key, contact, centre_hz, hemisphere, upper, lower,
                         amp_low, amp_high, n_boot, seed):
    """The key: the tile entry and recording set (the series the bootstrap resamples), the
    candidate, the two stored thresholds and the capture amplitude range (the grid is centred at
    the thresholds' own midpoint and the replay is held to the capture range), the bootstrap's own
    replicate count and seed, and this file's own rule version -- the identical shape
    `design_rule_signature` uses, one row over."""
    from . import robustness as _rb
    return (_rb.KIND, _rb.RULE_VERSION, str(getattr(participant, "uid", participant)), tiles_key,
            recording_set_signature(participant), str(contact), round(float(centre_hz), 3),
            str(hemisphere),
            None if upper is None else round(float(upper), 6),
            None if lower is None else round(float(lower), 6),
            None if amp_low is None else round(float(amp_low), 6),
            None if amp_high is None else round(float(amp_high), 6),
            int(n_boot), int(seed))


def write_robustness(participant, *, candidate, hemisphere, threshold_plan, loaded=None,
                     epochs=None, n_boot=None, seed=0):
    """Replay the real controller over the same 3 s tiles the simulation and the design rule read,
    across the grid `robustness.py` defines, and store the 200-replicate block-bootstrap interval
    on the onset duration, threshold gap and detection blanking. Refuses, rather than bootstraps on
    nothing, exactly where `write_design_rule` and `write_simulation` refuse: no thresholds, no
    candidate, no tile entry, no capture amplitude range, or no usable pieces. A matching key is
    served from the store rather than rebootstrapped."""
    from . import robustness as _rb
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                # pragma: no cover - depends on the runner
        from CacheStore import provenance as _prov

    summary = {"written": False, "store_key": None, "seconds": None}
    plan = threshold_plan
    if plan is None or plan.upper is None or plan.lower is None:
        summary["reason"] = ("no thresholds were placed for this candidate, so there is nothing "
                             "for a robustness bootstrap to be measured against")
        return summary
    if None in plan.amplitude_limits():
        summary["reason"] = "the plan has no capture amplitude range, which the replay is held to"
        return summary
    # the limits the replay is held to: the capture currents capped at the safe ceiling (306)
    _amp_lo, _amp_hi = plan.amplitude_limits()
    contact = (candidate or {}).get("channel")
    centre = (candidate or {}).get("center_hz")
    if contact is None or centre is None:
        summary["reason"] = "the candidate carries no sensing contact or band centre"
        return summary
    tiles_key = _tiles_key_for(participant)
    if tiles_key is None:
        summary["reason"] = "no tile entry key, so nothing could be run or stored"
        return summary
    n_boot = _rb.DEFAULT_N_BOOT if n_boot is None else int(n_boot)
    uid = str(getattr(participant, "uid", participant))
    sig = robustness_signature(participant, tiles_key=tiles_key, contact=contact,
                               centre_hz=centre, hemisphere=hemisphere, upper=plan.upper,
                               lower=plan.lower, amp_low=_amp_lo,
                               amp_high=_amp_hi, n_boot=n_boot, seed=seed)
    summary["store_key"] = _cache_store.product_key(_rb.KIND, uid, sig)
    if _cache_store.read_stamp(_rb.KIND, uid, sig, root=_SHARED_CACHE_DIR_OVERRIDE) is not None:
        summary["written"] = True
        summary["already_stored"] = True
        return summary

    import time as _time
    t0 = _time.perf_counter()
    inputs = simulation_inputs_for_participant(uid, contact=contact, centre_hz=float(centre),
                                               loaded=loaded, hemisphere=hemisphere, epochs=epochs)
    if inputs.get("absent_reason") or not len(inputs["t"]):
        summary["reason"] = inputs.get("absent_reason") or "no usable pieces with a known amplitude"
        return summary
    payload = _rb.robustness_for_series(inputs["t"], inputs["power"], inputs["amp_obs"],
                                        upper=plan.upper, lower=plan.lower,
                                        amp_low=_amp_lo,
                                        amp_high=_amp_hi, n_boot=n_boot, seed=seed)
    payload["candidate"] = {"channel": str(contact), "center_hz": float(centre),
                            "hemisphere": str(hemisphere)}
    payload["seconds"] = _time.perf_counter() - t0
    summary["seconds"] = payload["seconds"]

    chain = [_prov.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")]
    _cache_store.store_if_absent(
        _rb.KIND, uid, sig, lambda: payload, writer="closed_loop", trigger="deployment_report",
        provenance=_prov.flatten(chain), n_recordings=None,
        extra={"refused": bool(payload.get("refused")), "n_feasible": payload.get("n_feasible"),
              "candidate": _simulation_candidate_tag(contact, centre, hemisphere)},
        root=_SHARED_CACHE_DIR_OVERRIDE)
    summary["written"] = (_cache_store.read_stamp(_rb.KIND, uid, sig,
                                                  root=_SHARED_CACHE_DIR_OVERRIDE) is not None)
    summary["refused"] = bool(payload.get("refused"))
    summary["n_feasible"] = payload.get("n_feasible")
    return summary


def robustness_if_stored(participant, candidate=None, *, hemisphere="Left"):
    """The newest stored robustness bootstrap for this candidate, matched on the sidecar's
    `candidate` tag exactly as `design_rule_if_stored` matches -- or ``None``."""
    from . import robustness as _rb
    match = None
    if candidate and candidate.get("channel") is not None and candidate.get("center_hz") is not None:
        want = _simulation_candidate_tag(candidate["channel"], candidate["center_hz"],
                                         candidate.get("actuated_hemisphere")
                                         or candidate.get("sensing_hemisphere") or hemisphere)
        match = lambda meta: (meta.get("extra") or {}).get("candidate") == want  # noqa: E731
    try:
        payload, _stamp = _cache_store.load_newest(_rb.KIND,
                                                   str(getattr(participant, "uid", participant)),
                                                   consumer="closed_loop",
                                                   root=_SHARED_CACHE_DIR_OVERRIDE, match=match)
        return payload
    except Exception:                                  # noqa: BLE001 - a miss is not an error
        _log.warning("closed-loop: the stored robustness bootstrap could not be read for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        return None


def cache_status_for_page(participant):
    """When the decoded recordings and settings this report reads were last assembled."""
    meaning = ("the date the decoded recordings, the therapy settings and the matched pain reports "
               "this report reads were last assembled and stored; a newer upload assembles them "
               "again under a new key")
    try:
        sig = recording_set_signature(participant)
    except Exception as exc:                          # noqa: BLE001
        return {"kind": "inputs", "exists": False, "last_built_utc": None,
                "what_it_means": meaning, "note": f"the recording-set key could not be built: {exc!r}"}
    # Same participant_uid `evidence_inputs_cached` now stores under (decision 85) -- passing
    # `None` here after that fix would look up the wrong file and always report "no stored entry".
    pid = str(getattr(participant, "uid", participant))
    return _cache_store.status_for_page("inputs", pid, sig, what_it_means=meaning,
                                        root=_SHARED_CACHE_DIR_OVERRIDE)


def _cache_status_or_reason(participant):
    """`cache_status_for_page`, but it can never be the thing that breaks a report.

    Every return path of `report_for_participant` carries this, including the two empty states, so
    it runs even when the participant has no spectra at all. It is one sidecar read and no
    computation, but "cheap" is not "cannot fail" -- an unreadable sidecar or a store pointed
    nowhere must degrade to a stated reason rather than take down a page that otherwise had
    something to show.
    """
    try:
        return cache_status_for_page(participant)
    except Exception as exc:                           # noqa: BLE001
        _log.warning("closed-loop report: the cache status could not be read for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        # `note`, NOT `reason`. The page's own `CacheStatusLine.js` renders `status.note` and lists
        # it in its propTypes; it has no `reason` field at all, so a first draft of this handler put
        # the explanation somewhere the page cannot display it -- the very failure this function
        # exists to avoid, reproduced one level down. Caught in review before it shipped anywhere a
        # reader would look. The rest of the shape matches `store.status_for_page`'s own, so the
        # same fields are present whether the status was read or could not be.
        return {"kind": "inputs", "exists": False, "last_built_utc": None,
                "note": f"the cache status could not be read: {exc!r}",
                "what_it_means": "the report itself is unaffected; only its freshness line is."}


def programmed_settings_from_epochs(eps, hemisphere):
    """The device's own programmed rate and pulse width on one side, read off the exposure-epoch
    table (``StimOptimizer.adapter.exposure_epochs``) rather than asked of the caller.

    WHY THIS EXISTS. A band picked from the calibrated grid (the "Choose a band" card) carries a
    channel and a centre frequency and nothing about stimulation, because the grid is built from
    recordings, not from a proposed setting. D27 and D31 both need a rate and a pulse width, so
    every such candidate reached them as ``None`` and both rules blocked or went unknown for a
    reason that has nothing to do with the band -- the device has a real, current rate and pulse
    width on record, it was simply never read.

    WHICH EPOCH. The one in force now: the open-ended epoch if the table has one (the current row
    never closes because nothing has changed since), otherwise the epoch with the latest start
    time.

    WHICH SIDE. Pulse width is asymmetric between hemispheres on this participant, so the caller
    must say which hemisphere's column to read (``"Left"`` or ``"Right"``); this function does not
    guess or pool the two sides.

    NEVER A FABRICATED VALUE. An absent table, an empty table, an unrecognised hemisphere, or a
    hemisphere whose pulse-width column the table does not carry all return an empty dict, never a
    guessed number. A ``None``-valued fact must stay ``None``.

    Returns a dict with up to five keys: ``rate_hz``, ``pulse_width_us``, the lead's stimulating
    ring numbers ``stim_rings_on_sensing_lead`` and its programmed cathode as written
    ``stim_contacts_on_sensing_lead`` (both for device rule D52), and ``_provenance`` (one sentence
    naming the epoch and when it started, for the caller to attach to whichever facts it actually
    filled in).
    """
    out = {}
    if hemisphere not in ("Left", "Right"):
        return out
    try:
        if eps is None or len(eps) == 0 or "t_start" not in eps.columns:
            return out
    except (TypeError, AttributeError):
        return out

    if "open_ended" in eps.columns and bool(eps["open_ended"].fillna(False).any()):
        rows = eps.loc[eps["open_ended"] == True]                       # noqa: E712
    else:
        rows = eps
    row = rows.sort_values("t_start").iloc[-1]

    rate = row.get("freq_hz")
    if rate is not None and not pd.isna(rate):
        out["rate_hz"] = float(rate)

    pw_col = f"pw_us_{hemisphere}"
    pw = row.get(pw_col) if pw_col in row.index else None
    if pw is not None and not pd.isna(pw):
        out["pulse_width_us"] = float(pw)
    # THE CONTACTS THIS LEAD STIMULATES ON (the PI, 2026-09-22; device rule D52). The device allows
    # sensing only on the pair immediately flanking the stimulating contacts (decision 217), and this
    # page said "the device permits this configuration" for a pair the contacts in force do not
    # allow, because nothing here read them. Parsed by the rule's one home (`DecodeCommon.sensing_rule
    # .stim_rings`, the parser the readiness card uses); a row with no cathode gives no contacts,
    # never a guess.
    cath_col = f"cathode_{hemisphere}"
    cath = row.get(cath_col) if cath_col in row.index else None
    if cath is not None and not pd.isna(cath) and str(cath).strip():
        try:
            from modules.DecodeCommon import sensing_rule as _sensing_rule
        except ImportError:                                  # host suite: BRAVO/modules is the root
            from DecodeCommon import sensing_rule as _sensing_rule
        rings = sorted(_sensing_rule.stim_rings(cath))
        if rings:
            out["stim_rings_on_sensing_lead"] = rings
            out["stim_contacts_on_sensing_lead"] = str(cath)

    if out:
        when = row.get("t_start")
        try:
            when_s = pd.Timestamp(when).strftime("%Y-%m-%d %H:%M UTC")
        except (TypeError, ValueError):
            when_s = str(when)
        state = "open-ended" if bool(row.get("open_ended")) else "closed"
        # The epoch number arrives as a numpy float; print it as the integer a reader expects.
        try:
            epoch_s = str(int(row.get("epoch")))
        except (TypeError, ValueError):
            epoch_s = str(row.get("epoch"))
        out["_provenance"] = (
            f"measured: the device's programmed setting on the {hemisphere} as of {when_s} "
            f"(exposure epoch {epoch_s}, {state})")
    return out


def rate_commitment_from_active_group(candidate_rate_hz, active_group):
    """D30's committed-for-this-attempt flag, DERIVED from the device (PI decision 2026-09-12,
    option a): the candidate's rate counts as committed when it equals the rate frozen in the
    device's newest ACTIVE sensing group.

    Pure, so it is testable with no database. ``active_group`` is what
    ``device_facts.active_sensing_group_facts`` returns. Returns a dict with
    ``rate_committed_for_this_attempt`` (True or False) and ``_provenance`` (one sentence), or an
    EMPTY dict when either rate is unknown -- then nothing is supplied and D30 stays not
    determinable, which is the honest answer rather than a guessed one.
    """
    try:
        cand = float(candidate_rate_hz) if candidate_rate_hz is not None else None
    except (TypeError, ValueError):
        cand = None
    dev_rate = (active_group or {}).get("active_sensing_group_rate_hz")
    try:
        dev_rate = float(dev_rate) if dev_rate is not None else None
    except (TypeError, ValueError):
        dev_rate = None
    if cand is None or dev_rate is None:
        return {}
    group = (active_group or {}).get("active_sensing_group")
    if cand == dev_rate:
        return {"rate_committed_for_this_attempt": True,
                "_provenance": (
                    f"derived: the candidate's {cand:g} Hz equals the rate already frozen in the "
                    f"device's active sensing group {group} (PI decision 2026-09-12, option a)")}
    return {"rate_committed_for_this_attempt": False,
            "_provenance": (
                f"derived: the candidate's {cand:g} Hz differs from the {dev_rate:g} Hz frozen in "
                f"the device's active sensing group {group}; committing this rate means a new "
                f"group and a new threshold capture (PI decision 2026-09-12, option a)")}


def report_for_participant(participant, request_data=None, *, candidates=None, hemisphere="Left",
                           power_scale="power_linear", force_refresh=None):
    """Fetch this participant's data from the platform and build the report.

    Imports of the sibling modules are deferred to call time for the same reason
    ``StimOptimizer.adapter`` defers its Biomarkers import: at module import time the Django app
    registry may not be populated, and a module-level import would also create a cycle between the
    three analysis modules.
    """
    from modules.StimOptimizer import adapter as _sa
    from . import pipeline as _pl

    rd = request_data or {}

    # TRACK D: computed FIRST and unconditionally, before either early return below, because
    # browsing the grid to CHOOSE a point is exactly the situation where no candidate has been
    # picked yet -- the case the two early returns below both cover. A grid read gated behind "a
    # candidate already exists" would never be reachable from the one screen that needs it: picking
    # a first candidate. Cheap even when it finds nothing: one store read, no model fit, no ORM
    # query beyond the participant already resolved by the caller.
    try:
        _grid_export = band_sweep_grid_for_closed_loop(getattr(participant, "uid", participant), rd)
    except Exception as _grid_exc:                     # noqa: BLE001
        _log.warning("closed-loop report: the calibrated grid could not be read for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        _grid_export = {"available": False,
                        "reason": f"the calibrated grid could not be read: {_grid_exc!r}"}

    # Both fetches go through the memo: measured at 32.96 s and 33.99 s respectively on RCS08, i.e.
    # 67 of the 70 s this endpoint used to take. build_design_matrix ACCEPTS request_data and never
    # references it, so it is a pure function of the participant and safe to key on the recording
    # set; it is called with default washin_min and items, and a caller varying those would need
    # them in the key.
    # DECISION 48 APPLIES TO THE EMPTY STATES TOO, and until 2026-09-10 it did not reach them: the
    # only `cache_status` in this function sat on the final return, so the two early returns below
    # -- which are what a reader sees BEFORE choosing a candidate, i.e. most of the time -- came
    # back without it, and the page's shared "last built" line had nothing to show. That is
    # precisely the "no stored results yet" case decision 48 names. Measured live on RCS08 before
    # the fix: this endpoint returned exactly three keys, `available`, `band_sweep_grid`, `reason`.
    _status = _cache_status_or_reason(participant)

    psd, eps, dm = evidence_inputs_cached(participant, force_refresh=bool(force_refresh))
    if psd is None:
        return {"available": False,
                "reason": "this participant has no assembled TD and PSD band power, so no control signal can be "
                          "evaluated. Sensing recordings must be ingested first.",
                "band_sweep_grid": _grid_export,
                "cache_status": _status}

    # THE PAIN SCORE EVERY BAND-TO-PAIN READING ON THE PAGE IS COMPUTED ON (the PI, 2026-09-25
    # night): E2 and E3, the stability card and its per-state odds ratios. Chosen on the page,
    # sent as `PainScore`; the ratings are joined here, per request, and never into the saved
    # `inputs` entry, whose key takes no pain score (decision 273).
    _pain = pain_score_from_request(rd)
    _dm_note = None
    try:
        dm, _dm_note = design_matrix_with_pain_score(participant, dm, eps, _pain["key"])
    except Exception as _dm_exc:                       # noqa: BLE001 -- the edge says it is missing
        _log.warning("closed-loop report: the %s ratings could not be joined for %s",
                     _pain["key"], getattr(participant, "uid", participant), exc_info=True)
        _dm_note = f"the {_pain['label']} ratings could not be joined: {_dm_exc!r}"
    if _dm_note:
        _pain = dict(_pain, not_available=_dm_note)

    cands = candidates or rd.get("Candidates") or []
    if not cands:
        return {"available": False,
                "reason": "no candidate configuration was supplied. Choose a channel and centre "
                          "frequency on the Biomarker Exploration page first; deployability is "
                          "evaluated for a specific configuration, not for a participant.",
                "band_sweep_grid": _grid_export,
                "cache_status": _status}
    # THE TWO SIDES OF THE FIRST CANDIDATE, resolved once here and used everywhere below (review
    # C1, 2026-09-12). Until then one name, ``_hemi``, preferred the ACTUATED side and was used
    # for the impedance and the survey facts too, and the page always sent
    # ``actuated_hemisphere: "Left"`` -- so a band on a right contact was judged on the left
    # lead's impedance, the left survey's artefact flags and LFP bins, the left capture, the left
    # paused amplitude, and (through ``hemisphere`` handed to the pipeline as the raw request
    # value) the left current for E1, E3, the capture currents and the simulation. Nothing on the
    # page said so; the only symptom was a D39 "contralateral pairing" row that was wrong about
    # why. Facts about the SENSING lead use ``_sens_hemi``; facts about the STIMULATED side and
    # every current column use ``_act_hemi``. The request's own ``Hemisphere`` is the fallback for
    # a candidate that names no side, never an override of one that does.
    _c0_side = (cands[0] or {}) if cands else {}
    _sens_hemi = (_c0_side.get("sensing_hemisphere") or _c0_side.get("actuated_hemisphere")
                  or hemisphere)
    _act_hemi = (_c0_side.get("actuated_hemisphere") or _c0_side.get("sensing_hemisphere")
                 or hemisphere)
    _norm_side = {"left": "Left", "right": "Right"}
    _sens_hemi = _norm_side.get(str(_sens_hemi).strip().lower(), _sens_hemi) if _sens_hemi else _sens_hemi
    _act_hemi = _norm_side.get(str(_act_hemi).strip().lower(), _act_hemi) if _act_hemi else _act_hemi
    # From here on ``hemisphere`` IS the actuated side: the pipeline's manifest, its amplitude
    # column, the prescription's validated side and the simulation's amplitude series all take it.
    hemisphere = _act_hemi or hemisphere

    # Device facts the rules need but the analysis tables cannot supply. Fetched here rather than
    # inside pipeline.run so the pipeline stays free of ORM imports and remains testable on frames.
    dev = {}
    try:
        from ClosedLoopDeployment import device_facts as _df
        from Server import models as _m
        _p = participant if hasattr(participant, "uid") else _m.Participant.find(uid=participant)
        _sfs = _m.SourceFile.find_all(owner=_p)
        _imp = list(_m.Recording.find_all(source__in=_sfs, type="MedtronicDeviceImpedance"))
        dev = _df.facts_for_participant(getattr(_p, "uid", participant), _imp,
                                        sensing_hemisphere=_sens_hemi,
                                        actuated_hemisphere=_act_hemi,
                                        channel=(cands[0] or {}).get("channel"))
    except Exception as exc:                      # never let a fact lookup take down the report
        _log.warning("closed-loop report: device facts unavailable for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        dev = {"_provenance": {}, "_error": f"device facts unavailable: {exc!r}"}

    # RATE AND PULSE WIDTH THE DEVICE IS ACTUALLY PROGRAMMED AT, read from the exposure-epoch
    # table `eps` already loaded above (`evidence_inputs_cached`) rather than asked of the caller.
    # D27 and D31 both need a rate and a pulse width, and a band picked from the calibrated grid
    # (the "Choose a band" card) carries neither -- the frontend never sends them, because the grid
    # is built from recordings, not from a proposed setting. Without this every such candidate
    # blocked or went unknown on D27/D31 for a reason that has nothing to do with the band.
    #
    # This is a DEVICE FACT, not a candidate default, so it is folded into `dev` the same way the
    # facts above are: `pipeline._facts_for` only fills a candidate's key when the candidate itself
    # left it `None`, so an explicit rate or pulse width the caller already supplied is never
    # overridden here.
    #
    # THE SENSING SIDE, the same ``_sens_hemi`` the device facts above use: D31's own predicate
    # keys its programmed-pair lookup on `sensing_hemisphere` (then the legacy `hemisphere` key,
    # never `actuated_hemisphere`), so the rate/pulse-width pair filled in here must come from the
    # side D31 then checks it against. (Before review C1 this was the one place that already read
    # the sensing side; the split above made the rest of the function agree with it.)
    try:
        _prog_hemi = _sens_hemi if _sens_hemi in ("Left", "Right") else None
        _prog = programmed_settings_from_epochs(eps, _prog_hemi) if _prog_hemi else {}
        _prog_prov = _prog.pop("_provenance", None)
        if _prog:
            dev.setdefault("_provenance", {})
            for _pk, _pv in _prog.items():
                if dev.get(_pk) is None:
                    dev[_pk] = _pv
                    if _prog_prov:
                        dev["_provenance"][_pk] = _prog_prov
    except Exception as exc:                # never let this take down the report either
        _log.warning("closed-loop report: programmed rate/pulse width unavailable for %s",
                     getattr(participant, "uid", participant), exc_info=True)

    # THE DEVICE'S ACTIVE SENSING GROUP, read live from the newest ingested session report, and
    # D30's committed-rate flag derived from it (PI decision 2026-09-12, option a). Read live rather
    # than from the committed session-report summary because that summary is stale on this exact
    # point (it says 110 Hz; the device says 55 Hz). Its own try/except: a failure here is logged
    # with its traceback and D30 simply stays not determinable; it never takes down the report.
    try:
        from ClosedLoopDeployment import device_facts as _df_ag
        _ag = _df_ag.active_sensing_group_facts(participant)
        if _ag:
            dev.setdefault("_provenance", {})
            _ag_sentence = (
                f"measured: the device's newest session report ({_ag.get('session_report_date')}), "
                f"active group {_ag.get('active_sensing_group')} with sensing configured, rate "
                f"{_ag.get('active_sensing_group_rate_hz')!r} Hz, pulse widths "
                f"{_ag.get('active_sensing_group_pulse_widths_us')!r} us, adaptive therapy "
                f"{_ag.get('active_sensing_group_adaptive_status')!r}")
            for _ak, _av in _ag.items():
                if dev.get(_ak) is None:
                    dev[_ak] = _av
                    dev["_provenance"][_ak] = _ag_sentence
            # The candidate's rate is what pipeline._facts_for will end up with: its own rate_hz
            # when it states one, else the device fact filled in above from the exposure epochs.
            _cand_rate = (cands[0] or {}).get("rate_hz")
            if _cand_rate is None:
                _cand_rate = dev.get("rate_hz")
            _rc = rate_commitment_from_active_group(_cand_rate, _ag)
            _rc_prov = _rc.pop("_provenance", None)
            if _rc and dev.get("rate_committed_for_this_attempt") is None:
                dev["rate_committed_for_this_attempt"] = _rc["rate_committed_for_this_attempt"]
                if _rc_prov:
                    dev["_provenance"]["rate_committed_for_this_attempt"] = _rc_prov
    except Exception as exc:                # never let this take down the report either
        _log.warning("closed-loop report: the device's active sensing group could not be read "
                     "for %s", getattr(participant, "uid", participant), exc_info=True)

    # ---------------------------------------------------------------------------------------------
    # THE THREE-SOURCE COMPARISON AND THE TWO TABLES IT WRITES COME BEFORE THE PIPELINE (review
    # C6, 2026-09-12). The pipeline's E1 and the two D26 verdicts read the stored pooled table
    # (``_pooled_e1`` below); until this move the request READ that table first and WROTE it
    # afterwards, so on the first request after a new run of stepped current landed (a clinic
    # visit) the triangle and the D26 warnings came from the previous table while the simulation
    # card, which reads the table after the write, used the new one -- two panels on one page
    # disagreeing about which table they read, and the page caches the whole answer until
    # Recompute. The payloads are gathered in ``_pre`` and copied onto ``out`` once it exists.
    _pre = {}
    # ---------------------------------------------------------------------------------------------
    # HOW STIMULATION CURRENT MOVED BAND POWER, MEASURED THREE SEPARATE WAYS AND PUT SIDE BY SIDE.
    #
    # WHY THIS IS ON THIS PAGE. Closed loop watches the power in one band and moves the current when
    # that power crosses a threshold typed into the stimulator. There are three different ways to get
    # a band power out of this device -- from the streamed voltage trace, from the device's own
    # onboard spectrum, and from the band power the device computes on board and reports directly --
    # and they come from three different recordings. Whoever is about to program a threshold should be
    # able to see all three next to each other over the same stimulation settings, in the device's own
    # units, before they pick a number.
    #
    # THIS GATES NOTHING, and that is deliberate rather than an oversight. The payload says so in
    # `gates_nothing`, no verdict on this page reads it, and no blocking rule depends on it. The PI
    # asked for it as something informative for the person reading the page, and a comparison of
    # three measurement routes is not a device rule traceable to a page of a Medtronic manual, which
    # is what every blocking rule here is.
    #
    # AND IT MUST NOT BE READ AS THREE INDEPENDENT CONFIRMATIONS. The device computes its own band
    # power on board from the very voltage trace the first route reads, and the contact surveys
    # behind the second route are where the conversion into device units was fitted in the first
    # place. Agreement across the three says the conversion is behaving. The payload carries that
    # sentence in `notes` and in the figure footer, so a panel cannot show the numbers without it.
    _3build, _amp_stored = None, None
    _3_is_every_run = False
    _3loaded = {}                    # the recordings the build decoded, for the simulation (C8)
    try:
        from . import three_source_response as _3src
        from . import three_source_plots as _3plot
        # The table (Track A step 7) needs every run; the page draws the newest few. When the
        # table for this record is already stored, only the page's runs are built.
        try:
            _amp_stored = amplitude_effect_if_stored(participant)
            _gt_stored = ground_truth_if_stored(participant)
        except Exception:                               # noqa: BLE001 — the page comes first
            _log.warning("closed-loop report: could not read the stored amplitude-effect or ground-truth entries for %s; both will be rebuilt",
                         getattr(participant, "uid", participant), exc_info=True)
            _amp_stored = None
            _gt_stored = None
        # Every run is built when ANY of the write-back tables is missing for this recording set:
        # the amplitude-effect table, the ground-truth verdict, or (since 2026-09-11) the per-run
        # points behind the pooled three-source view. Otherwise only the page's runs are built.
        try:
            _rp_stored = run_points_stored_for_current_key(participant)
            _ps_stored = pooled_shape_stored_for_current_key(participant)
        except Exception:                               # noqa: BLE001 -- a miss means build
            _log.warning("closed-loop report: could not check the stored per-run points for %s",
                         getattr(participant, "uid", participant), exc_info=True)
            _rp_stored = _ps_stored = False
        _3_max_runs = (THREE_SOURCE_RUNS_ON_PAGE
                       if (_amp_stored and _gt_stored and _rp_stored and _ps_stored) else _ALL_RUNS)
        _3_is_every_run = _3_max_runs == _ALL_RUNS
        _3loaded = {}
        _3build = _3src.build_for_participant(
            getattr(participant, "uid", participant), max_runs=_3_max_runs,
            loaded_sink=_3loaded)
        _page = dict(_3build, comparisons=list(_3build.get("comparisons", []))
                     [:THREE_SOURCE_RUNS_ON_PAGE])
        _pre["three_source_response"] = _3plot.report_payload(_page)
    except Exception as _exc:                          # never let this take down the whole report
        # Say WHY it is missing, for the same reason as the stability block above: an absent key
        # reads on the page as "does not apply", and this having failed is not that.
        _log.warning("closed-loop report: the three-source comparison could not be assembled for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        _pre["three_source_response"] = {
            "comparisons": [], "gates_nothing": True,
            "absent_reason": ("the three-way comparison of how current moves band power could not "
                              f"be assembled: {_exc!r}"),
        }

    # THE POOLED WITHIN-VISIT TABLE, written only from a build that holds every run. This is what
    # lets the consistency check below answer the same way on every request instead of depending on
    # whether this particular one happened to rebuild the comparison in full.
    try:
        _pre["within_visit_pooled_shape"] = write_pooled_shape(
            participant, _3build, is_every_run=_3_is_every_run)
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the pooled within-visit table could not be written "
                     "for %s", getattr(participant, "uid", participant), exc_info=True)
        _pre["within_visit_pooled_shape"] = {
            "written": False, "n_rows": 0, "n_contacts": 0, "n_bands": 0, "store_key": None,
            "reason": f"the pooled within-visit table could not be written: {_exc!r}"}

    # THE PER-RUN POINTS, stored beside the pooled table under the same refusal, and the pooled-by-
    # side view the redesigned three-source panel draws (redesign plan decisions 5, 9, 10). Read
    # back on EVERY request, including the truncated ones, for the same reason the pooled table is.
    try:
        from . import run_points as _rp
        _pre["three_source_run_points"] = write_run_points(
            participant, _3build, is_every_run=_3_is_every_run)
        _pre["three_source_pooled"] = _rp.pooled_view_payload(
            run_points_if_stored(participant), pooled_shape_if_stored(participant),
            absent_reason=(_pre["three_source_run_points"].get("reason")
                           if not _pre["three_source_run_points"].get("written") else None))
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the per-run points could not be stored or grouped "
                     "for %s", getattr(participant, "uid", participant), exc_info=True)
        _pre["three_source_run_points"] = {"written": False, "n_rows": 0, "n_runs": 0,
                                          "store_key": None,
                                          "reason": f"could not be stored: {_exc!r}"}
        _pre["three_source_pooled"] = {"gates_nothing": True, "sides": [],
                                      "absent_reason": f"could not be grouped: {_exc!r}"}

    # The pooled titration slope for the first candidate, from the stored table (decision 103),
    # handed to the pipeline as E1 (redesign decision 9). None when nothing is stored yet.
    _pooled_e1 = None
    try:
        from . import amplitude_effect as _amp_e1
        _c0 = (cands[0] or {}) if cands else {}
        if _c0.get("channel") is not None and _c0.get("center_hz") is not None:
            _pooled_e1 = _amp_e1.pooled_row(pooled_shape_if_stored(participant),
                                            _c0["channel"], float(_c0["center_hz"]))
    except Exception:                                  # noqa: BLE001 -- E1 falls back to the table
        _log.warning("closed-loop report: the pooled slope for E1 could not be read for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        _pooled_e1 = None
    # Decision 180: the pair is re-placed from the record INSIDE the run, right after the capture
    # rule, so the eligibility ledger, the replay and the parameter card's rows all read it.
    def _place(rep_, cands_):
        return _place_thresholds_from_record(participant, rep_, cands_, hemisphere=hemisphere,
                                             loaded=_3loaded, epochs=eps)
    rep = _pl.run(getattr(participant, "uid", participant), psd_frame=psd, epochs=eps,
                  design_matrix=dm, candidates=cands, hemisphere=hemisphere,
                  power_scale=power_scale, device_facts=dev, pooled_e1=_pooled_e1,
                  place_thresholds=_place, pain_score=_pain["key"])
    out = report_to_dict(rep)
    out["pain_score"] = _pain
    out.update(_pre)                     # the three-source and table payloads built above
    out["device_facts"] = {k: v for k, v in dev.items() if not k.startswith("_")}
    out["device_facts_provenance"] = dev.get("_provenance", {})
    out["impedance_status"] = dev.get("_impedance_status")
    out["impedance_status_counts"] = dev.get("_impedance_status_counts")

    # DOES THIS BAND MEAN THE SAME THING ABOUT PAIN AT EVERY STIMULATION SETTING?
    #
    # The PI asked for this on 2026-09-06: "does the frequency band behave the same way under every
    # setting? This should actually reach the Closedloop deployment page because it's really
    # important." Until now it did not: the biomarkers page computed it and neither this module nor
    # StimOptimizer imported the result, so the deployment page never saw it.
    #
    # We REUSE the answer the biomarkers path already computed rather than refitting the model here.
    # That path runs the test as part of validating a band, so translating its result costs no model
    # fitting and adds almost nothing to the request. Refitting would need R and would be slow.
    #
    # READ `band_stability["answer"]`, WHICH HAS FOUR VALUES, AND NEVER THE UPSTREAM `stim_stable`
    # FLAG. That flag has two values and on this participant's own data it disagrees with the honest
    # answer. THE LIVE EXAMPLE, re-measured on RCS08 on 2026-09-09 at the calibrated grid's own
    # settings (5 Hz band, pain split into thirds): ONE_THREE_LEFT at 17.5 Hz. The interaction test
    # does not reject (p = 0.372), so the flag reads True and downstream looks like a pass -- but
    # the interval on the largest difference between stimulation states runs from -0.52 to +0.89,
    # which both straddles zero and is wider than the declared margin of 0.69, so the data cannot
    # tell a steady band from a materially unsteady one. "We could not tell" and "it behaved the
    # same" are different conclusions and collapsing them has already cost this project real errors
    # in three other places.
    #
    # THE EXAMPLE USED TO BE ONE_THREE_LEFT AT 12.5 Hz (p = 0.290, interval -1.23 to +0.22), and
    # that pair is kept here as dated history rather than quietly deleted, because the reason it
    # had to be replaced is itself worth knowing. That point reads p = 0.0323 today, interval
    # -1.238 to -0.104, answer "behaves differently" -- a THIRD value, not the "cannot tell" the
    # comment claimed. It was chased down on 2026-09-09 and the cause is none of the obvious ones:
    # Track D's own code, checked out byte-for-byte and run on today's data, returns 0.0323 to
    # twelve significant figures, both from the cached spectrum matrix and with that matrix
    # rebuilt; truncating the pain reports back to 2026-09-07 changes nothing (the model has the
    # same 421 rows in 37 groups either way, and only three reports separate the two dates); and
    # the time-domain recording count is the same 386 it was then. What the same point IS very
    # sensitive to is the band width: 0.286 at 1 Hz, 0.094 at 2 Hz, 0.049 at 4 Hz, 0.032 at 5 Hz,
    # 0.073 at 10 Hz. So a number quoted for this point without its band width beside it is not a
    # reproducible claim, which is the practical lesson and the reason the replacement above states
    # its settings.
    #
    # THIS BLOCKS NOTHING. The payload says so in `blocking_status`. Whether "behaves differently"
    # should stop a deployment is the PI's call, not this module's: every other blocking rule here
    # is a device rule traceable to a page of a Medtronic manual, and this is a statistical finding
    # about one participant.
    try:
        from modules.Biomarkers import bravo_service as _bsvc
        from . import stability as _stab
        _first = (cands[0] or {}) if cands else {}
        _ch, _fc = _first.get("channel"), _first.get("center_hz")
        if _ch is not None and _fc is not None:
            _bw = float(_first.get("band_width_hz", 5.0))
            _core = _bsvc._validate_band_core(stability_request_body(
                getattr(participant, "uid", participant), _ch, float(_fc), _bw,
                pain_score=_pain["key"]))
            _raw = (_core.get("stim") or {}) if _core.get("available") else {
                "available": False,
                "reason": (_core.get("reason") or "the biomarkers path returned nothing usable"),
            }
            _finding = _stab.finding_from_stability_result(_raw, _ch, float(_fc),
                                                          band_width_hz=_bw)
            out["band_stability"] = _finding.as_payload()
            out["band_stability_summary"] = _stab.summarise([_finding])
            # AND SAID INSIDE THE COHERENCE NOTE (panel D item 5, 2026-09-22). The note is where a
            # reader is told what the three edges together do and do not show; leaving the
            # stability answer out of it let a coherent sign pattern read as a settled finding
            # about a band whose meaning had never been shown to hold still. The wording has one
            # home, in `consistency.note_with_stability`, and appending is idempotent.
            if isinstance(out.get("coherence"), dict):
                from . import consistency as _consistency
                out["coherence"]["note"] = _consistency.note_with_stability(
                    out["coherence"].get("note"), out["band_stability"])
    except Exception as _exc:                      # never let this take down the whole report
        # Say WHY it is missing. A key that is simply absent reads on the page as "does not apply",
        # and this check being unavailable is not the same as it not applying.
        _log.warning("closed-loop report: the stability answer could not be assembled for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        from . import stability as _stab_err
        out["band_stability"] = {
            "answer": "not tested", "test_ran": False,
            "reason": f"the stability answer could not be assembled: {_exc!r}",
            "blocking_status": _stab_err.BLOCKING_STATUS,
            "answers_possible": list(_stab_err.ANSWERS),
        }
        # The note says "not tested" too, for the same reason the payload does: a coherence note
        # that is silent about stability reads as though stability had been shown.
        if isinstance(out.get("coherence"), dict):
            from . import consistency as _consistency_err
            out["coherence"]["note"] = _consistency_err.note_with_stability(
                out["coherence"].get("note"), out["band_stability"])

    # TRACK D: the grid computed once, at the top of this function -- see the note there on why it
    # runs before either early return, and `band_sweep_grid_for_closed_loop` above for the design.
    out["band_sweep_grid"] = _grid_export

    # THE CLOSED-LOOP SIMULATION, run for the first candidate and stored under its own key; the
    # page fetches the payload after its first figures are up. Its inputs are the 3 s tiles, the
    # stored pooled curve and the stored per-run points, so it runs after those are written.
    try:
        out["closed_loop_simulation"] = write_simulation(
            participant, rep=rep, build=_3build, candidate=(cands[0] if cands else None),
            hemisphere=hemisphere, power_scale=power_scale, epochs=eps, loaded=_3loaded,
            device_facts=dev)
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the simulation could not be run or stored for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        out["closed_loop_simulation"] = {"written": False, "store_key": None,
                                         "reason": f"could not be run or stored: {_exc!r}"}

    # THE CONFIRMATIONS-AND-SEPARATION DESIGN RULE (T3, 2026-09-13; design_rule.py): fit the
    # noise-only model on the same tiles the simulation reads, store the averaging x onset
    # separation table, and read it straight back -- a matching key is a store read, a fresh fit
    # costs what the simulation's own fit already costs. Attached by patching the SERIALISED
    # ``out["prescriptions"]``/``out["prescription"]`` row dicts `report_to_dict(rep)` already
    # built a few lines above (`out = report_to_dict(rep)`), rather than mutating `rep.prescriptions`
    # itself -- `report_to_dict` runs once, before this point, and a mutation made to the
    # dataclasses afterward would never reach the dict this function actually returns. The table
    # needs the thresholds `pipeline.run` itself just placed (the noise simulation holds the level
    # at their midpoint), which is also why this runs after `pipeline.run`, alongside
    # `write_simulation`, rather than inside `pipeline.run`.
    try:
        _dr_summary = write_design_rule(
            participant, candidate=(cands[0] if cands else None), hemisphere=hemisphere,
            threshold_plan=rep.threshold, loaded=_3loaded, epochs=eps)
        out["closed_loop_design_rule"] = _dr_summary
        _dr_payload = design_rule_if_stored(participant, (cands[0] if cands else None),
                                            hemisphere=hemisphere)
        if _dr_payload is not None and out.get("prescriptions"):
            from . import timing_recommendation as _tr_dr
            from . import prescription as _presc
            _rec_timing = _tr_dr.for_participant(getattr(participant, "uid", participant)) or {}
            _avg_ms = (_rec_timing.get("averaging_ms") or {}).get("value_ms")
            _onset_ms = (_rec_timing.get("onset_upper_ms") or {}).get("value_ms")

            def _patch_rows(field_rows):
                for row in (field_rows or []):
                    if row.get("parameter") not in ("Upper LFP threshold", "Lower LFP threshold"):
                        continue
                    up_v = next((r.get("value") for r in field_rows
                               if r.get("parameter") == "Upper LFP threshold"), None)
                    lo_v = next((r.get("value") for r in field_rows
                               if r.get("parameter") == "Lower LFP threshold"), None)
                    note = _presc.design_rule_note(_dr_payload, upper=up_v, lower=lo_v,
                                                   averaging_ms=_avg_ms, onset_ms=_onset_ms)
                    if note is not None:
                        row["design_rule_note"] = note

            for _mode_dict in (out["prescriptions"].get("modes") or {}).values():
                _patch_rows(_mode_dict.get("fields"))
            if out.get("prescription"):
                _patch_rows(out["prescription"].get("fields"))
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the design rule could not be run, stored or attached "
                     "for %s", getattr(participant, "uid", participant), exc_info=True)
        out["closed_loop_design_rule"] = {"written": False, "store_key": None,
                                          "reason": f"could not be run or stored: {_exc!r}"}

    # ---------------------------------------------------------------------------------------------
    # THE THRESHOLD OCCUPANCY CHECK (T4, 2026-09-13; occupancy.py; contest decision 150,
    # synthesis section 4): where this participant's own averaged readings actually sit relative
    # to the stored pair, at the averaging duration the card recommends -- and whether the pair
    # behaves as a single threshold in all but name, or sits well off the level the signal
    # occupies. Uses the SAME loader design_rule.py and simulation.py already call
    # (`simulation_inputs_for_participant`, defined in this file) and is patched onto the
    # SERIALISED prescription rows, for the identical reason the design-rule block above is:
    # `report_to_dict` has already turned the dataclasses into plain dicts by this point.
    try:
        from . import occupancy as _occ
        from . import timing_recommendation as _tr_occ
        from . import prescription as _presc_occ
        _c0_occ = (cands[0] or {}) if cands else {}
        _up_occ = getattr(rep.threshold, "upper", None)
        _lo_occ = getattr(rep.threshold, "lower", None)
        _rec_timing_occ = _tr_occ.for_participant(getattr(participant, "uid", participant)) or {}
        _avg_s_occ = ((_rec_timing_occ.get("averaging_ms") or {}).get("value_ms") or 0.0) / 1000.0
        if (_c0_occ.get("channel") is not None and _c0_occ.get("center_hz") is not None
                and _up_occ is not None and _lo_occ is not None and _avg_s_occ > 0):
            _occ_inputs = simulation_inputs_for_participant(
                getattr(participant, "uid", participant), contact=_c0_occ["channel"],
                centre_hz=float(_c0_occ["center_hz"]), loaded=_3loaded, hemisphere=hemisphere,
                epochs=eps)
            if not _occ_inputs.get("absent_reason") and len(_occ_inputs["t"]):
                # BOTH CLOCKS (T3, decision 200): the card's recommended averaging and the
                # averaging the device runs today on this side, read off the newest session
                # report's active sensing group (`dev["active_sensing_group_timing"]`).
                _prog_t = (dev.get("active_sensing_group_timing") or {}) if isinstance(dev, dict) else {}
                _prog_avg_ms = ((_prog_t.get(hemisphere) or {}).get("averaging_ms")
                                if isinstance(_prog_t, dict) else None)
                _prog_avg_s = (float(_prog_avg_ms) / 1000.0
                               if _prog_avg_ms is not None and float(_prog_avg_ms) > 0 else None)
                _occ_payload = _occ.threshold_occupancy_two_clocks(
                    _occ_inputs["t"], _occ_inputs["power"], upper=_up_occ, lower=_lo_occ,
                    averaging_s=_avg_s_occ, programmed_averaging_s=_prog_avg_s)
            else:
                _occ_payload = {"available": False,
                                "reason": (_occ_inputs.get("absent_reason")
                                          or "no usable pieces for this contact")}
        elif _up_occ is None or _lo_occ is None:
            _occ_payload = {"available": False,
                            "reason": "no thresholds are placed for this candidate"}
        elif _avg_s_occ <= 0:
            _occ_payload = {"available": False,
                            "reason": "no averaging duration is in force to average onto"}
        else:
            _occ_payload = {"available": False,
                            "reason": "the candidate carries no sensing contact or band centre"}
        out["threshold_occupancy"] = _occ_payload
        _occ_note = _presc_occ.occupancy_note(_occ_payload)
        if _occ_note is not None and out.get("prescriptions"):

            def _patch_occ_rows(field_rows):
                for row in (field_rows or []):
                    if row.get("parameter") in ("Upper LFP threshold", "Lower LFP threshold"):
                        row["occupancy_note"] = _occ_note

            for _mode_dict in (out["prescriptions"].get("modes") or {}).values():
                _patch_occ_rows(_mode_dict.get("fields"))
            if out.get("prescription"):
                _patch_occ_rows(out["prescription"].get("fields"))
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the threshold occupancy check could not be computed "
                     "for %s", getattr(participant, "uid", participant), exc_info=True)
        out["threshold_occupancy"] = {"available": False,
                                      "reason": f"could not be computed: {_exc!r}"}

    # ---------------------------------------------------------------------------------------------
    # THE START-OF-STRETCH BIAS CHECK (T6, 2026-09-13; startup_bias.py; contest decision 150,
    # synthesis section 4, task 7): are the first readings after a gap in recording low compared
    # with the rest of that stretch, and for how long -- two of the contest's own entries measured
    # this on the same participant and band and disagreed (D found a real dip, E found none), and
    # both methods are run here, faithfully, on THIS candidate's own recordings rather than
    # reconciled into one answer. Needs no optimiser and no simulation (unlike `design_rule.py`),
    # so it is computed fresh on every report exactly as `occupancy.py` is, and patched onto the
    # SERIALISED prescription rows for the identical reason the two blocks above are: by this
    # point `report_to_dict` has already turned the dataclasses into plain dicts.
    try:
        from . import startup_bias as _sb
        from . import prescription as _presc_sb
        _c0_sb = (cands[0] or {}) if cands else {}
        if _c0_sb.get("channel") is not None and _c0_sb.get("center_hz") is not None:
            _sb_inputs = simulation_inputs_for_participant(
                getattr(participant, "uid", participant), contact=_c0_sb["channel"],
                centre_hz=float(_c0_sb["center_hz"]), loaded=_3loaded, hemisphere=hemisphere,
                epochs=eps)
            if not _sb_inputs.get("absent_reason") and len(_sb_inputs["t"]):
                _sb_payload = _sb.startup_bias_for_series(_sb_inputs["t"], _sb_inputs["power"],
                                                          _sb_inputs["amp_obs"])
            else:
                _sb_payload = {"refused": True,
                               "reason": (_sb_inputs.get("absent_reason")
                                         or "no usable pieces for this contact")}
        else:
            _sb_payload = {"refused": True,
                           "reason": "the candidate carries no sensing contact or band centre"}
        out["closed_loop_startup_bias"] = _sb_payload
        _sb_note = _presc_sb.startup_bias_note(_sb_payload)
        if _sb_note is not None and out.get("prescriptions"):

            def _patch_sb_rows(field_rows):
                for row in (field_rows or []):
                    if row.get("parameter") == "Adaptive startup delay":
                        row["startup_bias_note"] = _sb_note

            for _mode_dict in (out["prescriptions"].get("modes") or {}).values():
                _patch_sb_rows(_mode_dict.get("fields"))
            if out.get("prescription"):
                _patch_sb_rows(out["prescription"].get("fields"))
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the start-of-stretch bias check could not be computed "
                     "for %s", getattr(participant, "uid", participant), exc_info=True)
        out["closed_loop_startup_bias"] = {"refused": True,
                                           "reason": f"could not be computed: {_exc!r}"}

    # ---------------------------------------------------------------------------------------------
    # THE BLOCK-BOOTSTRAP ROBUSTNESS CHECK (T5, 2026-09-13; robustness.py; contest decision 150,
    # synthesis section 4, task 5): "robustness as an interval, not a point" -- a 200-replicate
    # block bootstrap, resampling this participant's own recorded stretches with replacement,
    # reporting the 2.5th-97.5th percentile of the onset duration (and threshold gap, and detection
    # blanking) a designer replaying the real controller against this record would have picked.
    # Stored (unlike occupancy.py and startup_bias.py, T4 and T6, which are cheap enough to compute
    # fresh on every report) because it is a real numerical search -- 576 configurations replayed
    # over every training stretch -- the same cost class as `write_design_rule`'s own fit, and for
    # the identical reason that function is stored. Attached by patching the SERIALISED
    # `out["prescriptions"]`/`out["prescription"]` row dicts, for the identical reason the three
    # blocks above are: `report_to_dict` has already turned the dataclasses into plain dicts.
    try:
        _rb_summary = write_robustness(
            participant, candidate=(cands[0] if cands else None), hemisphere=hemisphere,
            threshold_plan=rep.threshold, loaded=_3loaded, epochs=eps)
        out["closed_loop_robustness"] = _rb_summary
        _rb_payload = robustness_if_stored(participant, (cands[0] if cands else None),
                                           hemisphere=hemisphere)
        if _rb_payload is not None and out.get("prescriptions"):
            from . import prescription as _presc_rb
            _rb_note = _presc_rb.robustness_note(_rb_payload)
            if _rb_note is not None:

                def _patch_rb_rows(field_rows):
                    for row in (field_rows or []):
                        if "nset duration" in (row.get("parameter") or ""):
                            row["robustness_note"] = _rb_note

                for _mode_dict in (out["prescriptions"].get("modes") or {}).values():
                    _patch_rb_rows(_mode_dict.get("fields"))
                if out.get("prescription"):
                    _patch_rb_rows(out["prescription"].get("fields"))
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the robustness bootstrap could not be run, stored or "
                     "attached for %s", getattr(participant, "uid", participant), exc_info=True)
        out["closed_loop_robustness"] = {"written": False, "store_key": None,
                                         "reason": f"could not be run or stored: {_exc!r}"}

    # ---------------------------------------------------------------------------------------------
    # THE CONSISTENCY CHECK (decision 74): does raising current on this contact move pain the way
    # the correlation implies, THROUGH this band?
    #
    # Closing the loop means moving CURRENT to move POWER in the hope of moving PAIN. This project
    # computes both links separately and, until now, nothing combined them. Multiplying the two
    # signs answers the only question that matters for actuation: whether turning this contact up is
    # expected to relieve or worsen pain through this band.
    #
    # WIRED HERE BECAUSE BOTH INPUTS ARE ALREADY IN HAND at this exact point and neither costs
    # anything new: `_3build` is the three-source comparison built a few lines above, and
    # `_grid_export` is the calibrated grid read once at the top of this function. The check fits no
    # new model -- it reads two results that already exist and reports the sign combination.
    # Decision 74 shipped it deliberately unwired ("built and proven as a standalone, callable check
    # first") and named this as where it belongs: as a CAVEAT.
    #
    # IT GATES NOTHING, and `gates_nothing` says so in the payload. On missing or non-significant
    # evidence the answer is "not assessed", never a manufactured pass -- decision 9's three-state
    # discipline. Whether a contradiction here should stop a deployment is the PI's call, exactly as
    # it is for `band_stability` above.
    try:
        from . import direction_consistency as _dc
        from . import amplitude_effect as _amp_pool
        _dc_first = (cands[0] or {}) if cands else {}
        _dc_ch, _dc_fc = _dc_first.get("channel"), _dc_first.get("center_hz")
        if _dc_ch is None or _dc_fc is None:
            out["implied_control_direction"] = {
                "implied_control_direction": "not assessed", "gates_nothing": True,
                "reason": "the candidate carries no sensing contact or band centre"}
        else:
            # THE POOLED HALF COMES FROM THE STORED TABLE, NEVER FROM `_3build`. That build is
            # truncated to the runs the page draws whenever the write-back entries already exist --
            # the steady state -- and pooling over it answers from a fraction of the visits. The
            # stored table was pooled from every run, so this reads the same on a cold request and a
            # warm one, which is the property that makes it a finding rather than an artefact.
            _dc_pooled = _amp_pool.pooled_row(pooled_shape_if_stored(participant),
                                              _dc_ch, float(_dc_fc))
            if _dc_pooled is None:
                out["implied_control_direction"] = {
                    "implied_control_direction": "not assessed", "gates_nothing": True,
                    "reason": ("the pooled within-visit table has no row for this contact and band "
                               "yet; it is written the next time the comparison is built from every "
                               "run, and this check reads it rather than pooling a partial one")}
            else:
                _dc_out = _dc.for_band(_3build, _grid_export, _dc_ch, float(_dc_fc),
                                       pooled=_dc_pooled)
                _dc_out["gates_nothing"] = True
                _dc_out["pooled_from"] = "stored table, pooled across every run"
                out["implied_control_direction"] = _dc_out
    except Exception as _exc:                          # never let this take down the whole report
        _log.warning("closed-loop report: the consistency check could not be assembled for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        out["implied_control_direction"] = {
            "implied_control_direction": "not assessed", "gates_nothing": True,
            "reason": f"the consistency check could not be assembled: {_exc!r}"}

    # TRACK A STEP 7: THE AMPLITUDE EFFECT ON EVERY BAND, WRITTEN WHERE STIM OPTIMIZER CAN READ IT.
    # Derived from the comparison just built, so it costs no second pass over the recordings, and
    # written through the one store with the tile entry in its provenance. A failure here is
    # reported in the response rather than raised, like everything else on this page.
    try:
        out["amplitude_effect_by_band"] = (_amp_stored if _amp_stored is not None
                                           else write_amplitude_effect(participant, _3build))
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the amplitude-effect table could not be derived or written for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        # The success path's own field names, so a consumer reading `n_rows` off this block does not
        # have to branch on whether it succeeded. No live consumer reads them today; matching the
        # shape now is what keeps that cheap to rely on later.
        out["amplitude_effect_by_band"] = {"written": False, "n_rows": 0, "n_runs": 0, "n_bands": 0,
                                           "store_key": None,
                                           "reason": f"could not be derived: {_exc!r}"}
    # TRACK G STEP 2: THE GROUND-TRUTH VERDICT (decision 33), written where Stim Optimizer reads it.
    try:
        out["ground_truth_verdict"] = (_gt_stored if _gt_stored is not None
                                       else write_ground_truth(participant, _3build))
    except Exception as _exc:                          # noqa: BLE001
        # REPORTED UNDER ITS OWN KEY. This handler used to write `amplitude_effect_by_band`, which
        # did two wrong things at once: the ground-truth failure was left with no explanation at
        # all (an absent key reads on the page as "does not apply", which is exactly what the
        # three-source block above says not to do), and the amplitude-effect result set two blocks
        # earlier -- which had succeeded -- was overwritten with a report of a failure that never
        # happened. Found 2026-09-10 by an audit comparing what each try-block assigns against what
        # its own handler reports.
        _log.warning("closed-loop report: the ground-truth verdict could not be written for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        out["ground_truth_verdict"] = {"written": False, "n_rows": 0, "n_runs": 0,
                                       "routes": {}, "store_key": None,
                                       "reason": f"the ground-truth verdict could not be "
                                                 f"written: {_exc!r}"}

    # THE CAVEATS LIST, assembled last because it reads what every block above wrote (panel D item
    # 3). It is not another stage of the argument: it restates what the payload already carries,
    # gates nothing, and is stored nowhere, so it cannot go stale against the report it describes.
    try:
        out["caveats"] = caveats_for_report(out)
    except Exception as _exc:                          # noqa: BLE001
        _log.warning("closed-loop report: the caveats list could not be assembled for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        out["caveats"] = [{"severity": "high", "card": "the verdict header",
                           "text": f"The list of caveats could not be assembled: {_exc!r}. Read "
                                   f"that as one missing list, not as a report with no caveats."}]

    # THE EVIDENCE THAT SHOULD HAVE BEEN EVALUATED AND WAS NOT, for the decision card's yellow
    # bullets (decision 302). Per request, stored nowhere, like the caveats above.
    try:
        out["evidence_not_evaluated"] = evidence_not_evaluated(out)
    except Exception:                                  # noqa: BLE001
        _log.warning("closed-loop report: the not-evaluated list could not be assembled for %s",
                     getattr(participant, "uid", participant), exc_info=True)
        out["evidence_not_evaluated"] = None

    out["cache_status"] = _status                              # Track C step 4
    return out
