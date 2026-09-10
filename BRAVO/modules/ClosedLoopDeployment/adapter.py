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

_log = _logging.getLogger(__name__)

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


def band_powers(log_psd, freqs, centers=DEFAULT_BAND_CENTERS_HZ, width=DEFAULT_BAND_WIDTH_HZ):
    """Per-band power on both scales from one row's log spectrum.

    Returns (linear, log_of_linear, mean_of_log), each a dict keyed by band centre.

    ``linear`` is the arithmetic mean of the linear bin powers and is the device-comparable
    quantity (D11). ``log_of_linear`` is its decibel expression, which is a monotone relabelling of
    the same ordering. ``mean_of_log`` is the quantity the biomarker pipeline used; it is the
    geometric mean in disguise and can rank bands differently, which is why it is returned rather
    than quietly replaced.
    """
    lp = np.asarray(log_psd, dtype=float)
    f = np.asarray(freqs, dtype=float)
    if lp.shape[0] != f.shape[0]:
        raise ValueError(f"log_psd has {lp.shape[0]} bins but freqs has {f.shape[0]}")
    lin_bins = np.power(10.0, lp / 10.0)
    out_lin, out_log, out_mol = {}, {}, {}
    half = float(width) / 2.0
    for c in centers:
        m = (f >= c - half) & (f < c + half)
        if not m.any():
            out_lin[c] = out_log[c] = out_mol[c] = np.nan
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            lin = float(np.nanmean(lin_bins[m]))
            out_lin[c] = lin
            out_log[c] = 10.0 * np.log10(lin) if lin > 0 else np.nan
            out_mol[c] = float(np.nanmean(lp[m]))
    return out_lin, out_log, out_mol


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
    for i, (a, b) in enumerate(zip(starts, ends)):
        m = (t >= a) & (t < b) if np.isfinite(b) else (t >= a)
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
    sample and channel with a whole spectrum held as a numpy array in ``log_psd`` and its frequency
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

    An empty tuple means the frame is the older kind, one whole spectrum per row in ``log_psd``
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
        psd_fp = _frame_fingerprint(psd_frame, ("t", "channel", "source", "log_psd", "freqs"))
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
#: `Biomarkers.bravo_service.compute_and_store_stability_grid`.
#:
#: DUPLICATED ON PURPOSE, AND PINNED BY A TEST. Importing the constant would mean importing
#: `bravo_service`, which imports `Server.models` and therefore needs Django's app registry — it
#: raises `AppRegistryNotReady` in the host suite, which does not configure Django. Reading one
#: extra column must never decide whether this whole function can run.
#: `tests/test_track_d_grid_stability_translation.py` asserts this string still equals
#: `bravo_service.STABILITY_GRID_KIND`, so a rename on that side fails loudly here.
STABILITY_GRID_KIND = "biomarker_band_stability_grid"


def band_sweep_grid_for_closed_loop(participant_uid):
    """The calibrated grid, as `consumer="closed_loop"`, with every row's stability result
    translated to the honest four-valued answer. Never raises.

    Returns `{"available": False, "reason": ...}` when nothing is stored yet -- Track D's export
    reads a grid Biomarkers already built and cached; it does not trigger a fresh, expensive build
    on Closed-Loop Deployment's own request, the same "browse a pre-computed grid" design the ADR
    calls for (`adr_2026-09-08_biomarkers_closedloop_matrix_export.md`).
    """
    try:
        from . import stability as _stab
    except ImportError:                                          # pragma: no cover
        from modules.ClosedLoopDeployment import stability as _stab
    try:
        payload, stamp = _cache_store.load_newest(
            "biomarker_band_sweep", participant_uid, consumer="closed_loop",
            root=_SHARED_CACHE_DIR_OVERRIDE)
    except Exception as exc:                                     # noqa: BLE001
        return {"available": False, "reason": f"reading the calibrated grid raised {exc!r}"}
    if payload is None:
        return {"available": False,
                "reason": ("no calibrated grid is stored yet for this participant; visit the "
                           "Biomarkers exploration page first"),
                "stamp": stamp}

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
    # The kind name is duplicated here rather than imported for the same reason.
    # `test_track_d_grid_stability_translation.py` asserts it still equals
    # `bravo_service.STABILITY_GRID_KIND`, so the two are pinned by a test instead of by an import
    # this module cannot afford to make.
    stored_stability = {}
    try:
        _payload, _ = _cache_store.load_newest(
            STABILITY_GRID_KIND, participant_uid, consumer="closed_loop",
            root=_SHARED_CACHE_DIR_OVERRIDE)
        for _flat, _value in ((_payload or {}).get("points") or {}).items():
            _ch, _, _centre = str(_flat).rpartition("|")
            try:
                stored_stability[(_ch, float(_centre))] = _value
            except (TypeError, ValueError):
                continue
    except Exception:                                            # noqa: BLE001
        stored_stability = {}                                    # never fatal; rows say "not tested"

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
                        new_row["cross_setting_stability"] = {
                            "answer": "not tested", "test_ran": False,
                            "reason": f"translation raised {exc!r}"}
                    new_row.pop("cross_setting_stability_raw", None)
                new_rows.append(new_row)
            new_sweep[key] = new_rows
        out_sweeps[channel] = new_sweep

    return {"available": True, "band_time_sweep": out_sweeps, "stamp": stamp,
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



def recording_set_signature(participant):
    """Identity of every recording that feeds the inputs, so a new ingest invalidates the cache.

    Folds in each recording's own uid and content hash rather than a count or a max date: a
    re-decode that replaces a recording in place changes neither of those, and a count alone would
    also miss a deletion balanced by an insertion.
    """
    from Server import models as _m
    sfs = list(_m.SourceFile.find_all(owner=participant))
    recs = list(_m.Recording.find_all(source__in=sfs))
    ident = sorted((str(getattr(r, "uid", "")), str(getattr(r, "hashed", "")),
                    str(getattr(r, "type", ""))) for r in recs)
    blob = "|".join("~".join(t) for t in ident).encode("utf8")
    return (str(getattr(participant, "uid", participant)), len(sfs), len(recs),
            _hashlib.blake2b(blob, digest_size=16).hexdigest())


def evidence_inputs_cached(participant, *, force_refresh=False):
    """``StimOptimizer.evidence_inputs`` and ``build_design_matrix``, memoised together.

    Returns ``(psd_frame, epochs, design_matrix)``. The two calls are cached as one entry because
    every consumer needs all three and they share the same invalidation condition, so splitting
    them would double the signature cost for no benefit.

    Callers must treat the returned frames as READ-ONLY, or copy before mutating: they are the same
    objects handed to every other caller. That is the same contract the Biomarkers assembled-matrix
    cache imposes.
    """
    from StimOptimizer import adapter as _sa
    sig = recording_set_signature(participant)
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
        if hit is not None:
            return hit
        # Nothing in this process's memory, so ask whether another worker process already built
        # it. This is the step that makes the build happen once per participant rather than once
        # per worker per restart.
        shared = _shared_load("inputs", sig, participant_uid=pid, consumer="closed_loop")
        if shared is not None:
            _remember_inputs(sig, shared)
            return shared
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
    dm = _sa.build_design_matrix(participant, stream=stream)
    out = (psd, eps, dm)
    _remember_inputs(sig, out)
    _shared_store("inputs", sig, out, participant_uid=pid,
                  provenance=_inputs_provenance(participant, stream, dm))
    return out


def _inputs_provenance(participant, stream, dm):
    """The chain for the `inputs` bundle: the settings stream's entry, the matched table's entry
    with its own chain (which names the pain-report snapshot), and the tile entry the sensed
    frame was read from. Each is cited only when its key is known; a frame built without the
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
        pass
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
    sig = _joined_signature(psd_frame, epochs, cen, width)
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
        lin, logl, mol = band_powers(r["log_psd"], r["freqs"], centers, width)
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
                "power_linear": lin[c], "power_log_of_linear": logl[c],
                "power_mean_of_log": mol[c],
                **ctx,
            })
    T = pd.DataFrame(rows)
    if T.empty:
        return T
    for h in ("Left", "Right"):
        c = canonical_amp_col(h)
        if c in T.columns:
            T[f"era_{h}"] = [_era(x) for x in pd.to_numeric(T[c], errors="coerce")]
    if pro_frame is not None and len(pro_frame) and "epoch" in pro_frame.columns:
        keep = [c for c in ("epoch", "report_id", "nrs", "vas") if c in pro_frame.columns]
        T = T.merge(pro_frame[keep].rename(columns={"epoch": "setting_epoch"}),
                    on="setting_epoch", how="left")
    return T


def _joined_table_calibrated(psd_frame, epochs, *, centers=DEFAULT_BAND_CENTERS_HZ, pro_frame=None):
    """``joined_table`` for the calibrated frame: one row per (tile, band), power read from the
    band's own column rather than integrated from a spectrum.

    THE THREE POWER SCALES. ``power_linear`` is the stored value itself, already the device's
    linear band power (the quantity a switching value is typed in). ``power_log_of_linear`` is its
    decibel expression. ``power_mean_of_log`` is NOT available from this frame: it is the mean of
    the per-bin log spectrum inside the band, and the calibrated frame holds no per-bin spectrum,
    so the column is present and empty rather than filled with a look-alike.

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
        with np.errstate(invalid="ignore", divide="ignore"):
            logl = np.where(lin > 0, 10.0 * np.log10(np.where(lin > 0, lin, 1.0)), np.nan)
        block = {"t": t, "channel": chan, "source": src, "setting_epoch": ep_idx,
                 "center_hz": np.full(len(f), float(c)), "band_width_hz": np.full(len(f), width),
                 "power_linear": lin, "power_log_of_linear": logl,
                 "power_mean_of_log": np.full(len(f), np.nan)}
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
            T[f"era_{h}"] = [_era(x) for x in pd.to_numeric(T[c], errors="coerce")]
    if pro_frame is not None and len(pro_frame) and "epoch" in pro_frame.columns:
        keep_cols = [c for c in ("epoch", "report_id", "nrs", "vas") if c in pro_frame.columns]
        T = T.merge(pro_frame[keep_cols].rename(columns={"epoch": "setting_epoch"}),
                    on="setting_epoch", how="left")
    T.attrs["rows_dropped_by_tile_gate"] = n_dropped
    T.attrs["band_power_source"] = "calibrated"
    return T


def scale_disagreement(T):
    """How often the two power scales would pick a different winning band.

    This answers hypothesis H4 of the module plan directly. It is a diagnostic, not a verdict: a
    high disagreement rate does not say which scale is right, only that the choice is consequential
    and must therefore be made deliberately rather than inherited from whichever pipeline ran first.
    """
    if T is None or T.empty:
        return {"available": False, "reason": "empty table"}
    g = T.dropna(subset=["power_linear", "power_mean_of_log"])
    if g.empty:
        return {"available": False, "reason": "no rows with both scales"}
    win_lin = g.loc[g.groupby(["t", "channel"])["power_linear"].idxmax(), ["t", "channel", "center_hz"]]
    win_mol = g.loc[g.groupby(["t", "channel"])["power_mean_of_log"].idxmax(), ["t", "channel", "center_hz"]]
    m = win_lin.merge(win_mol, on=["t", "channel"], suffixes=("_lin", "_mol"))
    if m.empty:
        return {"available": False, "reason": "no comparable samples"}
    disagree = float((m.center_hz_lin != m.center_hz_mol).mean())
    return {"available": True, "n_samples": int(len(m)),
            "disagreement_rate": disagree,
            "median_abs_shift_hz": float((m.center_hz_lin - m.center_hz_mol).abs().median()),
            "note": ("fraction of (time, channel) samples where the linear and mean-of-log scales "
                     "pick a different peak band. The device uses the linear scale (D11); the "
                     "biomarker pipeline validated on mean-of-log.")}


# ---------------------------------------------------------------------------------------------
# Phase 7 seam: live platform data -> a JSON-serialisable DeploymentReport for the interface
# ---------------------------------------------------------------------------------------------
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

    if device_ok is False:
        verdict = "blocked"
    elif rep.is_licensed():
        verdict = "supported"
    else:
        verdict = "unsupported"

    return {
        "available": True,
        "participant": rep.participant,
        "verdict": verdict,
        "licensed": rep.is_licensed(),
        "verdict_detail": {
            "device_eligible": device_ok,
            "all_edges_resolved": edges_ok,
            "coherent": coherent,
            "blockers": list(rep.blockers),
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
            "resolved": e.resolved, "note": e.note, "confounded_by": list(e.confounded_by),
            # WHICH ESTIMATOR produced the interval and the p-value, read from edges.py so the
            # switch has exactly one definition. The deployment panel used to hardcode the cluster
            # threshold in JavaScript with a comment claiming to mirror edges.py, and by then the
            # comment was wrong twice over: the constant had stopped being a disqualification floor
            # and become a choice between two estimators.
            "inference": _edges.estimator_for(e.n_clusters),
        } for k, e in (rep.edges or {}).items()},
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
        # The titration protocol. Also unserialised until 2026-09-04, so a session plan the
        # pipeline had generated could not be shown. The power figures are carried because a plan
        # whose detectable effect size is implausibly large is a plan not worth running, and the
        # clinician is the person who can judge that; the seed is carried so a plan can be
        # regenerated identically, which is what makes the randomised order auditable rather than
        # merely random.
        "protocol": None if rep.protocol is None else {
            "steps": list(rep.protocol.steps or []),
            "n_steps": len(rep.protocol.steps or []),
            "n_pairs": rep.protocol.n_pairs,
            "alpha": rep.protocol.alpha,
            "power": rep.protocol.power,
            "detectable_d": rep.protocol.detectable_d,
            "duration_min": rep.protocol.duration_min,
            "seed": rep.protocol.seed,
            "note": rep.protocol.note,
        },
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
                        "qualified_transitions", "unqualified_excursions", "hours_observed",
                        "hours_of_signal", "coverage_frac", "fractions_are_of_observed_samples",
                        "onset_windows_upper", "onset_windows_lower", "onset_inoperative",
                        "max_time_at_upper_limit_s", "max_time_at_lower_limit_s",
                        "predicted_failure_mode")} | {
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
                    "qualified_transitions", "unqualified_excursions", "hours_observed",
                    # Coverage travels with the fractions or they will be misread. Omitting these
                    # three from this tuple already happened once: the caveat text carried the
                    # numbers while the fields serialised as null, so an interface reading the
                    # fields alone could have printed "49.6% of the day" for a record with 0.012%
                    # coverage. Any field added to DutyCycle must be added here too.
                    "hours_of_signal", "coverage_frac", "fractions_are_of_observed_samples",
                    "onset_windows_upper", "onset_windows_lower", "onset_inoperative",
                    # The longest CONTINUOUS excursion at each limit, which the fractions above
                    # cannot express and which is the number a clinician needs before consenting.
                    "max_time_at_upper_limit_s", "max_time_at_lower_limit_s",
                    "predicted_failure_mode")} | {
                "caveats": list(rep.prescription.duty.caveats or [])},
        },
        "threshold": None if rep.threshold is None else {
            "upper": _num(rep.threshold.upper), "lower": _num(rep.threshold.lower),
            "control_authority": _num(rep.threshold.control_authority),
            "capture_amp_low": _num(rep.threshold.capture_amp_low),
            "capture_amp_high": _num(rep.threshold.capture_amp_high),
            "frac_time_below": _num(rep.threshold.frac_time_below),
            "frac_time_between": _num(rep.threshold.frac_time_between),
            "frac_time_above": _num(rep.threshold.frac_time_above),
            "predicted_recapture_alert": rep.threshold.predicted_recapture_alert,
            "problems": list(rep.threshold.problems), "note": rep.threshold.note,
        },
        "manifest": rep.manifest,
        "candidates": rep.candidates,
    }


#: How many of the newest runs of rising current the deployment page DRAWS. The amplitude-effect
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
                "reason": (build or {}).get("absent_reason") or "no run of rising current"}
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
                "reason": (build or {}).get("absent_reason") or "no run of rising current"}
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
        _grid_export = band_sweep_grid_for_closed_loop(getattr(participant, "uid", participant))
    except Exception as _grid_exc:                     # noqa: BLE001
        _grid_export = {"available": False,
                        "reason": f"the calibrated grid could not be read: {_grid_exc!r}"}

    # Both fetches go through the memo: measured at 32.96 s and 33.99 s respectively on RCS08, i.e.
    # 67 of the 70 s this endpoint used to take. build_design_matrix ACCEPTS request_data and never
    # references it, so it is a pure function of the participant and safe to key on the recording
    # set; it is called with default washin_min and items, and a caller varying those would need
    # them in the key.
    psd, eps, dm = evidence_inputs_cached(participant, force_refresh=bool(force_refresh))
    if psd is None:
        return {"available": False,
                "reason": "this participant has no assembled spectra, so no control signal can be "
                          "evaluated. Sensing recordings must be ingested first.",
                "band_sweep_grid": _grid_export}

    cands = candidates or rd.get("Candidates") or []
    if not cands:
        return {"available": False,
                "reason": "no candidate configuration was supplied. Choose a channel and centre "
                          "frequency on the Biomarker Exploration page first; deployability is "
                          "evaluated for a specific configuration, not for a participant.",
                "band_sweep_grid": _grid_export}
    # Device facts the rules need but the analysis tables cannot supply. Fetched here rather than
    # inside pipeline.run so the pipeline stays free of ORM imports and remains testable on frames.
    dev = {}
    try:
        from ClosedLoopDeployment import device_facts as _df
        from Server import models as _m
        _p = participant if hasattr(participant, "uid") else _m.Participant.find(uid=participant)
        _sfs = _m.SourceFile.find_all(owner=_p)
        _imp = list(_m.Recording.find_all(source__in=_sfs, type="MedtronicDeviceImpedance"))
        _hemi = (cands[0] or {}).get("actuated_hemisphere") or (cands[0] or {}).get(
            "sensing_hemisphere") or hemisphere
        dev = _df.facts_for_participant(getattr(_p, "uid", participant), _imp,
                                        hemisphere=_hemi,
                                        channel=(cands[0] or {}).get("channel"))
    except Exception as exc:                      # never let a fact lookup take down the report
        dev = {"_provenance": {}, "_error": f"device facts unavailable: {exc!r}"}

    rep = _pl.run(getattr(participant, "uid", participant), psd_frame=psd, epochs=eps,
                  design_matrix=dm, candidates=cands, hemisphere=hemisphere,
                  power_scale=power_scale, device_facts=dev)
    out = report_to_dict(rep)
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
            _core = _bsvc._validate_band_core({
                "ParticipantId": getattr(participant, "uid", participant),
                "Channel": _ch, "CenterHz": float(_fc), "BandWidthHz": _bw,
            })
            _raw = (_core.get("stim") or {}) if _core.get("available") else {
                "available": False,
                "reason": (_core.get("reason") or "the biomarkers path returned nothing usable"),
            }
            _finding = _stab.finding_from_stability_result(_raw, _ch, float(_fc),
                                                          band_width_hz=_bw)
            out["band_stability"] = _finding.as_payload()
            out["band_stability_summary"] = _stab.summarise([_finding])
    except Exception as _exc:                      # never let this take down the whole report
        # Say WHY it is missing. A key that is simply absent reads on the page as "does not apply",
        # and this check being unavailable is not the same as it not applying.
        from . import stability as _stab_err
        out["band_stability"] = {
            "answer": "not tested", "test_ran": False,
            "reason": f"the stability answer could not be assembled: {_exc!r}",
            "blocking_status": _stab_err.BLOCKING_STATUS,
            "answers_possible": list(_stab_err.ANSWERS),
        }

    # TRACK D: the grid computed once, at the top of this function -- see the note there on why it
    # runs before either early return, and `band_sweep_grid_for_closed_loop` above for the design.
    out["band_sweep_grid"] = _grid_export

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
    try:
        from . import three_source_response as _3src
        from . import three_source_plots as _3plot
        # The table (Track A step 7) needs every run; the page draws the newest few. When the
        # table for this record is already stored, only the page's runs are built.
        try:
            _amp_stored = amplitude_effect_if_stored(participant)
            _gt_stored = ground_truth_if_stored(participant)
        except Exception:                               # noqa: BLE001 — the page comes first
            _amp_stored = None
            _gt_stored = None
        _3build = _3src.build_for_participant(
            getattr(participant, "uid", participant),
            max_runs=(THREE_SOURCE_RUNS_ON_PAGE if (_amp_stored and _gt_stored) else _ALL_RUNS))
        _page = dict(_3build, comparisons=list(_3build.get("comparisons", []))
                     [:THREE_SOURCE_RUNS_ON_PAGE])
        out["three_source_response"] = _3plot.report_payload(_page)
    except Exception as _exc:                          # never let this take down the whole report
        # Say WHY it is missing, for the same reason as the stability block above: an absent key
        # reads on the page as "does not apply", and this having failed is not that.
        out["three_source_response"] = {
            "comparisons": [], "gates_nothing": True,
            "absent_reason": ("the three-way comparison of how current moves band power could not "
                              f"be assembled: {_exc!r}"),
        }

    # TRACK A STEP 7: THE AMPLITUDE EFFECT ON EVERY BAND, WRITTEN WHERE STIM OPTIMIZER CAN READ IT.
    # Derived from the comparison just built, so it costs no second pass over the recordings, and
    # written through the one store with the tile entry in its provenance. A failure here is
    # reported in the response rather than raised, like everything else on this page.
    try:
        out["amplitude_effect_by_band"] = (_amp_stored if _amp_stored is not None
                                           else write_amplitude_effect(participant, _3build))
    except Exception as _exc:                          # noqa: BLE001
        out["amplitude_effect_by_band"] = {"written": False,
                                           "reason": f"could not be derived: {_exc!r}"}
    # TRACK G STEP 2: THE GROUND-TRUTH VERDICT (decision 33), written where Stim Optimizer reads it.
    try:
        out["ground_truth_verdict"] = (_gt_stored if _gt_stored is not None
                                       else write_ground_truth(participant, _3build))
    except Exception as _exc:                          # noqa: BLE001
        out["amplitude_effect_by_band"] = {"written": False,
                                           "reason": f"the amplitude-effect table could not be "
                                                     f"written: {_exc!r}"}

    out["cache_status"] = cache_status_for_page(participant)   # Track C step 4
    return out
