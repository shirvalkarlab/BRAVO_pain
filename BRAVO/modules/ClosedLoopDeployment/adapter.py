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


def _joined_signature(psd_frame, epochs, centers, width):
    # These are the columns lfp_evidence.frame_from_matrix actually emits, and the epoch columns
    # exposure_epochs emits. Both are now required rather than optional, so a rename upstream
    # breaks this loudly instead of narrowing the key to whatever still happens to match.
    return (_frame_fingerprint(psd_frame, ("t", "channel", "source", "log_psd", "freqs")),
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
_SHARED_CACHE_SUBDIR = "closed_loop"

#: Refuse to write an entry larger than this. A cache is a convenience and must never be the
#: reason a disk fills up on a machine that is also holding the participant's recordings. The
#: inputs measure 5.5 MB, so this is roughly fifty times the size of the thing it is sized for.
_SHARED_CACHE_MAX_BYTES = 256 * 1024 * 1024

#: Bumped whenever the shape of what gets stored changes. It is part of the file name, so an older
#: file is never read by newer code; the old file is simply not looked for and gets swept by
#: clear_shared_cache.
_SHARED_CACHE_FORMAT = 1

#: Tests and any caller who wants no file at all point this at a directory of their own or set it
#: to None. None means "memory only" and is not an error.
_SHARED_CACHE_DIR_OVERRIDE = None

_SHARED_CACHE_EVENTS = {"hits": 0, "misses": 0, "writes": 0, "refused_too_big": 0,
                        "unreadable": 0, "no_directory": 0}
_SHARED_CACHE_LOCK = _threading.Lock()


def shared_cache_dir():
    """Where the shared files go, or None when there is nowhere to put them.

    The platform already makes a cache directory next to the participant recordings and settings
    creates it at import time, so this uses that rather than inventing a location. Returning None
    when Django is not configured is what lets the unit tests run with no server and no disk
    writing at all.
    """
    if _SHARED_CACHE_DIR_OVERRIDE is not None:
        d = str(_SHARED_CACHE_DIR_OVERRIDE)
    else:
        try:
            from django.conf import settings as _st
            base = getattr(_st, "DATASERVER_PATH", None)
            if not base:
                return None
            d = _os.path.join(str(base), "cache", _SHARED_CACHE_SUBDIR)
        except Exception:
            return None
    try:
        _os.makedirs(d, exist_ok=True)
    except Exception:
        return None
    return d


def _shared_path(kind, signature):
    d = shared_cache_dir()
    if d is None:
        return None
    key = _hashlib.blake2b(repr(signature).encode("utf8"), digest_size=20).hexdigest()
    return _os.path.join(d, f"{kind}.v{_SHARED_CACHE_FORMAT}.{key}.pkl")


def _shared_load(kind, signature):
    """The stored result for this signature, or None.

    THE STORED SIGNATURE IS CHECKED AGAINST THE REQUESTED ONE rather than trusted from the file
    name. The name holds a hash, and a hash can in principle collide; more practically, a file
    could be left behind by code that built its signature differently. Comparing the signature
    itself means a mismatch is a miss and a rebuild, never a wrong answer.

    Every failure here is a miss, never an exception. A half-written file, a payload written by a
    different pandas version, a permissions change — none of those is a reason for a clinician's
    page to return an error, because the correct answer is always still obtainable by rebuilding.
    """
    p = _shared_path(kind, signature)
    if p is None:
        with _SHARED_CACHE_LOCK:
            _SHARED_CACHE_EVENTS["no_directory"] += 1
        return None
    if not _os.path.exists(p):
        with _SHARED_CACHE_LOCK:
            _SHARED_CACHE_EVENTS["misses"] += 1
        return None
    try:
        with open(p, "rb") as fh:
            stored = _pickle.load(fh)
        if not isinstance(stored, dict) or stored.get("signature") != signature:
            raise ValueError("stored signature does not match the requested one")
        with _SHARED_CACHE_LOCK:
            _SHARED_CACHE_EVENTS["hits"] += 1
        return stored["payload"]
    except Exception as exc:
        _log.info("ClosedLoopDeployment: discarding unreadable shared cache file %s (%r)", p, exc)
        with _SHARED_CACHE_LOCK:
            _SHARED_CACHE_EVENTS["unreadable"] += 1
        try:
            _os.remove(p)
        except OSError:
            pass
        return None


def _shared_store(kind, signature, payload):
    """Write the result where the other worker processes can find it. Returns True if it landed.

    WRITTEN TO A TEMPORARY NAME AND THEN MOVED INTO PLACE. Four workers can finish the same build
    at the same moment, and a reader can arrive mid-write. Writing straight to the final name would
    let a reader see a truncated file; ``os.replace`` is atomic within a directory, so a reader
    sees either the old complete file or the new complete file and never a partial one. The
    temporary name carries the process id so two writers cannot tread on each other's temporary
    file either.
    """
    p = _shared_path(kind, signature)
    if p is None:
        return False
    tmp = f"{p}.{_os.getpid()}.tmp"
    try:
        blob = _pickle.dumps({"signature": signature, "payload": payload,
                              "written_utc": _dt.datetime.now(_dt.timezone.utc).isoformat()},
                             protocol=5)
        if len(blob) > _SHARED_CACHE_MAX_BYTES:
            with _SHARED_CACHE_LOCK:
                _SHARED_CACHE_EVENTS["refused_too_big"] += 1
            _log.info("ClosedLoopDeployment: not sharing a %.1f MB %s entry through a file "
                      "(limit %.0f MB); it stays in this process's memory only",
                      len(blob) / 1e6, kind, _SHARED_CACHE_MAX_BYTES / 1e6)
            return False
        with open(tmp, "wb") as fh:
            fh.write(blob)
        _os.replace(tmp, p)
        with _SHARED_CACHE_LOCK:
            _SHARED_CACHE_EVENTS["writes"] += 1
        return True
    except Exception as exc:
        _log.info("ClosedLoopDeployment: could not write shared cache file %s (%r)", p, exc)
        try:
            _os.remove(tmp)
        except OSError:
            pass
        return False


def shared_cache_stats():
    """What the shared files have done, for the interface and for tests."""
    d = shared_cache_dir()
    files = []
    if d is not None:
        try:
            files = sorted(f for f in _os.listdir(d) if f.endswith(".pkl"))
        except OSError:
            files = []
    with _SHARED_CACHE_LOCK:
        events = dict(_SHARED_CACHE_EVENTS)
    return {"directory": d, "entries": len(files), "files": files,
            "bytes": sum(_os.path.getsize(_os.path.join(d, f)) for f in files) if d else 0,
            "max_bytes_per_entry": _SHARED_CACHE_MAX_BYTES, "events": events}


def clear_shared_cache():
    """Remove every shared file, including ones written by an older format version."""
    d = shared_cache_dir()
    removed = 0
    if d is not None:
        for f in list(_os.listdir(d)) if _os.path.isdir(d) else []:
            if f.endswith(".pkl") or f.endswith(".tmp"):
                try:
                    _os.remove(_os.path.join(d, f))
                    removed += 1
                except OSError:
                    pass
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
    if not force_refresh:
        with _INPUTS_MEMO_LOCK:
            hit = _INPUTS_MEMO.get(sig)
        if hit is not None:
            return hit
        # Nothing in this process's memory, so ask whether another worker process already built
        # it. This is the step that makes the build happen once per participant rather than once
        # per worker per restart.
        shared = _shared_load("inputs", sig)
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
    _shared_store("inputs", sig, out)
    return out


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

    if not force_refresh:
        with _RESPONSE_MEMO_LOCK:
            hit = _RESPONSE_MEMO.get(sig)
        if hit is not None:
            return hit
        shared = _shared_load("response", sig)
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
    # Both fetches go through the memo: measured at 32.96 s and 33.99 s respectively on RCS08, i.e.
    # 67 of the 70 s this endpoint used to take. build_design_matrix ACCEPTS request_data and never
    # references it, so it is a pure function of the participant and safe to key on the recording
    # set; it is called with default washin_min and items, and a caller varying those would need
    # them in the key.
    psd, eps, dm = evidence_inputs_cached(participant, force_refresh=bool(force_refresh))
    if psd is None:
        return {"available": False,
                "reason": "this participant has no assembled spectra, so no control signal can be "
                          "evaluated. Sensing recordings must be ingested first."}

    cands = candidates or rd.get("Candidates") or []
    if not cands:
        return {"available": False,
                "reason": "no candidate configuration was supplied. Choose a channel and centre "
                          "frequency on the Biomarker Exploration page first; deployability is "
                          "evaluated for a specific configuration, not for a participant."}
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
    # answer: on ONE_THREE_LEFT at 12.5 Hz the test did not reject (p = 0.290) so the flag reads
    # True, which downstream looks like a pass -- but the interval on the largest difference between
    # stimulation states runs from -1.23 to +0.22, far wider than the declared margin of 0.69, so
    # the data cannot tell a steady band from a materially unsteady one. "We could not tell" and
    # "it behaved the same" are different conclusions and collapsing them has already cost this
    # project real errors in three other places.
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
    try:
        from . import three_source_response as _3src
        from . import three_source_plots as _3plot
        out["three_source_response"] = _3plot.report_payload(
            _3src.build_for_participant(getattr(participant, "uid", participant)))
    except Exception as _exc:                          # never let this take down the whole report
        # Say WHY it is missing, for the same reason as the stability block above: an absent key
        # reads on the page as "does not apply", and this having failed is not that.
        out["three_source_response"] = {
            "comparisons": [], "gates_nothing": True,
            "absent_reason": ("the three-way comparison of how current moves band power could not "
                              f"be assembled: {_exc!r}"),
        }
    return out
