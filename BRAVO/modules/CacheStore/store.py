"""The one cache store, callable by any module that needs it.

WHY THIS FILE EXISTS. Two implementations of this existed, one in
`Biomarkers/bravo_service.py` and one in `ClosedLoopDeployment/adapter.py`, each with its own
directory resolver, loader, writer, event counters and lock. They shared a root by construction
accident rather than by design, and their per-entry limits differed by exactly a factor of four
(1,073,741,824 bytes against 268,435,456) for no stated reason. Stim Optimizer had no store at all
and is the slowest endpoint. This module is the superset of both, and `tests/test_one_store.py`
fails if any module resolves a cache directory of its own.

WHAT IS DELIBERATELY NOT DONE HERE.

* **No expiry.** An expiry-based cache serves a stale answer for as long as the expiry lasts. Every
  product stored here is keyed on the identity and content of everything that feeds it, so a new
  ingest replaces it immediately and nothing else does. Wall-clock time is not an input to
  correctness and must not become one.
* **No pain rating, anywhere, in any key of a recording-derived product.** The tiles are built with
  no knowledge of any rating, the same tiles serve every pain score and every match rule, and the
  reports are fetched fresh on every request. A rating in the key would discard a 37-second build
  every time a report was filed; a rating in the payload would let a file serve a stale rating,
  which is the one failure in this system with no visible symptom.
* **The caller does not decide whether to write. The key does.** A page whose key already matches
  what is on disk writes nothing, and a test asserts the directory is byte-identical afterwards.

THE FORMATS, and why each. Chosen from measurements on the real 6,629-row therapy table on
2026-09-06; the sizes and timings below are from that day and the tile figures from 2026-09-06.

* A table goes to **Parquet with zstd** — 0.027 MB against pickle's 0.451, and a stable published
  format rather than a version-fragile one that is unsafe to load. **Pickle writes twice as fast
  and reads are tied**, so this is a choice about size and durability and not about speed.
* Arrays go to a **compressed array file**. They are three-dimensional and numeric, not tabular,
  and the 245.90 MB tile store reads in 0.05 s that way against 0.56 s as lists of Python numbers.
* Anything else falls back to **pickle**, which is what both predecessors used throughout.
* **Comma-separated and JSON files are excluded on correctness, not preference.** The therapy table
  carries a timezone-aware timestamp and neither format round-trips it, so every consumer would
  re-parse the timestamp that matches therapy to neural signal — which is exactly where timezone
  errors enter this project.

THE STAMP. Every entry carries a small sidecar holding when it was written, what triggered it, how
many recordings it covers, and the provenance of every input it derived from. The sidecar is
written **after** the payload and is the commit marker, so a reader sees a complete entry or no
entry. It exists so a page can show the date of the last cache update without opening a 245 MB
file, and so the shared-memory freshness key has something authoritative to mirror.
"""

import datetime
import hashlib
import json
import logging
import os
import pickle
import re
import threading

_log = logging.getLogger(__name__)

#: Bumped when the shape of what gets stored changes. It is part of the file name, so an older file
#: is never read by newer code — the old name is simply not looked for, and `clear` sweeps it.
FORMAT_VERSION = 1

#: One limit for every kind, and it is the LARGER of the two predecessors': 1,073,741,824 bytes
#: here against the closed-loop module's 268,435,456.
#:
#: THE REASON IS HEADROOM, NOT REFUSAL, and an earlier version of this comment got that wrong.
#: 268,435,456 bytes is 256 MiB, so it would NOT have refused today's 245.90 MB tile entry — it
#: leaves between 4 and 9 percent to spare, depending on whether that measurement was decimal or
#: binary. Single-digit headroom on the ONE entry the cache exists to hold is the problem: one more
#: visit's recordings, or one more sensing channel, crosses it. And CROSSING IT IS SILENT — the
#: write is refused, the tiles stay in one worker's memory, and the page simply becomes slow again
#: with nothing a reader would think to look at. The larger cap leaves about 4.2 times the current
#: size.
#:
#: A cache is a convenience and must never be the reason a disk fills on a machine that is also
#: holding the participant's recordings, which is why there is a limit at all. Override per kind
#: through `MAX_BYTES_BY_KIND`.
MAX_BYTES_DEFAULT = 1024 * 1024 * 1024

MAX_BYTES_BY_KIND = {}

#: The subdirectory each kind lives in. A kind not named here gets a directory of its own name.
#: `raw_lsb_tiles` keeps its historical directory AND its historical file naming, because that
#: entry costs 37 seconds to rebuild and 245.90 MB of it is already on disk; moving it would throw
#: that away for no gain. The two closed-loop kinds are re-homed and rebuild once, which costs
#: about 0.4 s because that endpoint is served entirely from the tile file.
_KIND_DIRS = {
    "raw_lsb_tiles": "biomarker_shared",
    "inputs": "closed_loop",
    "response": "closed_loop",
}

#: Kinds whose file name must stay byte-identical to what the predecessor wrote, so the existing
#: files keep being found. Everything else uses the current naming.
_LEGACY_NAMING = {"raw_lsb_tiles"}

#: Kinds whose SUPERSEDED entries are kept rather than swept when a new one lands.
#:
#: The sweep exists because one tile entry is 245 MB and a month of daily uploads would otherwise
#: leave seven gigabytes of files that can never be read again. The pain-report snapshot is the
#: opposite case: a few tens of kilobytes, written once per distinct report set, and its whole
#: purpose is that a result computed on a given day can name the exact report table it used. A
#: swept snapshot would leave the ledger row and the key but not the table, which is the one thing
#: an audit needs. Growth is bounded by how often reports are filed, about one snapshot a day.
KEEP_HISTORY_KINDS = {"redcap_reports"}

#: Tests and any caller who wants a directory of their own point this at one. None means "ask
#: Django, then the environment", which is the production path.
DIR_OVERRIDE = None

#: THE ONE NAME under which a frame carries the key of the store entry it came from, in
#: `DataFrame.attrs`. Defined here and imported by every module, so the two modules that pass
#: frames to each other cannot drift apart on the spelling and silently stop citing each other.
STORE_KEY_ATTR = "bravo_store_key"

#: THE OFF SWITCH. Set False and every read is a miss and every write is a no-op, with no
#: exception raised anywhere. Two reasons it exists rather than relying on an unset storage path:
#:
#: 1. **Operations.** If a stored product is ever suspected of being wrong, the store can be turned
#:    off and every page recomputes from the recordings, with no code change and no deployment.
#:    Before this, the only way to get that was to remove a directory the server was writing to.
#: 2. **Tests.** "There is nowhere to write" and "there is somewhere but do not use it" were the
#:    same state in both predecessors, so the behaviour with no store at all could not be tested on
#:    a machine where the platform is configured. It failed exactly that way in the container.
ENABLED = True

#: ONE set of counters for every module, deliberately. The two predecessors each kept their own,
#: so no page could report what the cache as a whole was doing. `wrong_channels` and `unpackable`
#: are counted by the biomarker tile path and live here for the same reason.
_EVENTS = {"hits": 0, "misses": 0, "writes": 0, "refused_too_big": 0, "unreadable": 0,
           "no_directory": 0, "swept": 0, "refused_self_derived": 0, "legacy_no_sidecar": 0,
           "wrong_channels": 0, "unpackable": 0, "refused_no_writer": 0,
           "written_without_provenance": 0}
_LOCK = threading.Lock()


def _bump(name, n=1):
    with _LOCK:
        _EVENTS[name] = _EVENTS.get(name, 0) + n


# --------------------------------------------------------------------------------------------
# where things live
# --------------------------------------------------------------------------------------------

def root_dir(root=None):
    """The single cache root, or None when there is nowhere to put anything.

    Returning None rather than raising is what lets the tests run with no server and no disk
    writing at all, and it is also the right behaviour in production: a cache that cannot be
    written is a cache miss, never an error on a clinician's page.

    `root` is an explicit root supplied by the caller. It exists so the two module-level
    compatibility functions can pass their own override through to THIS resolver instead of
    computing a directory themselves — which is what having two resolvers meant in the first
    place. Production passes nothing.
    """
    if not ENABLED:
        return None
    if root is not None:
        return str(root)
    if DIR_OVERRIDE is not None:
        return str(DIR_OVERRIDE)
    base = None
    try:
        from django.conf import settings
        base = getattr(settings, "DATASERVER_PATH", None)
    except Exception:
        base = None
    if not base:
        base = os.environ.get("DATASERVER_PATH")
    if not base:
        return None
    return os.path.join(str(base), "cache")


def kind_dir(kind, *, create=True, root=None):
    """The directory for one kind of stored product, or None."""
    r = root_dir(root)
    if r is None:
        return None
    d = os.path.join(r, _KIND_DIRS.get(kind, kind))
    if create:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            return None
    elif not os.path.isdir(d):
        return None
    return d


def signature_key(signature):
    """The short stable name for a signature.

    `repr` of the signature rather than a JSON encoding, because both predecessors did that and the
    existing 782 MB of files depend on it. Changing it would silently miss every one of them.
    """
    return hashlib.blake2b(repr(signature).encode("utf8"), digest_size=20).hexdigest()


_SAFE_UID = re.compile(r"[^A-Za-z0-9_-]")


def _safe_uid(participant_uid):
    """The participant identifier as it may appear inside a file name.

    THE IDENTIFIER ARRIVES FROM THE REQUEST. Every page reads `ParticipantId` out of the request
    body and hands it here, and when the database lookup finds nobody by that name the raw string
    still reached this function and became part of a path. Real identifiers are 32 hex characters,
    so anything outside letters, digits, dash and underscore is replaced with an underscore: a
    value like `../../x` cannot climb out of the cache directory, and a dot cannot collide with the
    dots this file name uses as separators (the superseded-entry sweep matches on `.<uid>.`).
    None keeps its existing spellings -- "shared" here, the literal "None" under legacy naming --
    because entries already on disk carry them. Open item 17, closed 2026-09-10.
    """
    return _SAFE_UID.sub("_", str(participant_uid))


def _stem(kind, participant_uid, signature, root=None):
    """The path without an extension, or None."""
    d = kind_dir(kind, root=root)
    if d is None:
        return None
    key = signature_key(signature)
    if kind in _LEGACY_NAMING:
        uid = "None" if participant_uid is None else _safe_uid(participant_uid)
        return os.path.join(d, f"{kind}.v{FORMAT_VERSION}.{uid}.{key}")
    uid = "shared" if participant_uid is None else _safe_uid(participant_uid)
    return os.path.join(d, f"{kind}.v{FORMAT_VERSION}.{uid}.{key}")


_EXT_FOR_FORMAT = {"parquet": ".parquet", "npz": ".npz", "pickle": ".pkl"}
_FORMAT_FOR_EXT = {v: k for k, v in _EXT_FOR_FORMAT.items()}


def _existing_payload_path(stem):
    for ext in (".parquet", ".npz", ".pkl"):
        p = stem + ext
        if os.path.exists(p):
            return p
    return None


def _meta_path(stem):
    return stem + ".meta.json"


# --------------------------------------------------------------------------------------------
# choosing a format
# --------------------------------------------------------------------------------------------

def _is_frame(obj):
    try:
        import pandas as pd
    except Exception:
        return False
    return isinstance(obj, pd.DataFrame)


def _is_array_bundle(obj):
    """True for a non-empty flat mapping whose every value is an array. Anything else is not."""
    if not isinstance(obj, dict) or not obj:
        return False
    try:
        import numpy as np
    except Exception:
        return False
    return all(isinstance(k, str) for k in obj) and \
        all(isinstance(v, np.ndarray) for v in obj.values())


def choose_format(payload):
    """Which format this payload goes in. See the module docstring for why each."""
    if _is_frame(payload):
        return "parquet"
    if _is_array_bundle(payload):
        return "npz"
    return "pickle"


# --------------------------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------------------------

def read_stamp(kind, participant_uid, signature, root=None):
    """The sidecar for one entry, or None. Opens no payload file.

    This is what lets a page show the date of the last cache update without reading 245 MB, and it
    is the authoritative copy that the shared-memory freshness key mirrors.
    """
    stem = _stem(kind, participant_uid, signature, root=root)
    if stem is None:
        return None
    return _read_meta_file(_meta_path(stem))


def _read_meta_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf8") as fh:
            meta = json.load(fh)
        return meta if isinstance(meta, dict) else None
    except Exception:
        return None


def newest_stamp(kind, participant_uid, root=None, match=None):
    """The newest sidecar for this kind and participant, whatever its signature, or None.

    A page needs to say "last updated" before it knows whether today's key matches, so this looks
    the participant up by name rather than by signature. ``match``, when given, is a predicate on
    the sidecar: the newest sidecar it accepts is returned, so a kind that keeps several entries
    per participant (KEEP_NEWEST_BY_KIND) can be read back by what its `extra` says it is for.
    """
    d = kind_dir(kind, create=False, root=root)
    if d is None:
        return None
    marker = f".{_safe_uid(participant_uid)}." if participant_uid is not None else "."
    best, best_written = None, ""
    try:
        names = os.listdir(d)
    except OSError:
        return None
    for name in names:
        if not name.startswith(f"{kind}.v") or not name.endswith(".meta.json"):
            continue
        if marker not in name:
            continue
        meta = _read_meta_file(os.path.join(d, name))
        if meta is None:
            continue
        if match is not None:
            try:
                if not match(meta):
                    continue
            except Exception:                            # noqa: BLE001 -- a predicate that raises matches nothing
                continue
        w = str(meta.get("written_utc") or "")
        if w >= best_written:
            best, best_written = meta, w
    return best


def stamp_for_key(key, root=None):
    """The sidecar of the entry a product key names (`kind/participant/signature_key`), or None.

    For a reader that holds a key handed to it by another module and needs the chain of exactly
    that entry, not of whichever entry of the kind is newest. The store keeps one entry per kind
    and participant and sweeps the rest, so "the newest" and "the one named" agree only until the
    next write; a chain copied from the wrong entry would cite inputs the product never used.
    """
    try:
        kind, uid, skey = str(key).split("/")
    except ValueError:
        return None
    d = kind_dir(kind, create=False, root=root)
    if d is None:
        return None
    meta = _read_meta_file(_meta_path(os.path.join(d, f"{kind}.v{FORMAT_VERSION}.{uid}.{skey}")))
    if meta and meta.get("signature_key") == skey:
        return meta
    return None


def _discard_entry(stem, why):
    """Remove every file of an entry that cannot be used, so it is not offered again."""
    for path in [stem + ext for ext in _EXT_FOR_FORMAT.values()] + [_meta_path(stem)]:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    _log.warning("CacheStore: discarded an unusable entry %s (%s)", stem, why)


def status_for_page(kind, participant_uid, signature, *, what_it_means, root=None):
    """What a page shows about its cache: whether an entry exists under the current key, when it
    was last built, what triggered it, and a plain sentence saying what the date means.

    The date is read from the entry's own sidecar, never from a file timestamp a copy or a backup
    would falsify, and "no entry yet" is a state the page must show rather than a blank: a page
    computed from the recordings just now and a page served from a file built last month have to
    be distinguishable at a glance (Track C step 4).
    """
    stamp = read_stamp(kind, participant_uid, signature, root=root) if signature is not None else None
    if not stamp:
        return {"kind": kind, "exists": False, "last_built_utc": None, "trigger": None,
                "n_recordings": None, "what_it_means": what_it_means,
                "note": "no stored entry under the current key: this page was computed from the "
                        "recordings for this request, and the result is stored now for the next one"}
    return {"kind": kind, "exists": True, "last_built_utc": stamp.get("written_utc"),
            "trigger": stamp.get("trigger"), "n_recordings": stamp.get("n_recordings"),
            "writer": stamp.get("writer"), "what_it_means": what_it_means, "note": None}


def load_newest(kind, participant_uid, *, consumer=None, root=None, match=None):
    """`(payload, stamp)` for the newest entry of this kind and participant, or `(None, None)`.

    FOR A READER THAT CANNOT REBUILD THE WRITER'S KEY. The amplitude-effect table is keyed by the
    closed-loop module on inputs Stim Optimizer does not hold, and Stim Optimizer must not import
    that module (the dependency runs one way). So it asks for the newest entry by name and gets
    the sidecar back with it, so it can say WHICH inputs the table describes and whether they are
    the current ones. The sidecar names the payload file and its format; the consumer refusal
    applies exactly as in `load`. An entry whose payload is missing or unreadable is discarded and
    returned as `(None, stamp)`, so the caller can say that an entry existed and could not be
    read, which is not the same as no entry having been written.
    """
    stamp = newest_stamp(kind, participant_uid, root=root, match=match)
    if not stamp:
        _bump("misses")
        return None, None
    d = kind_dir(kind, create=False, root=root)
    key, fmt = stamp.get("signature_key"), stamp.get("format")
    if d is None or not key or fmt not in _EXT_FOR_FORMAT:
        _bump("misses")
        return None, None
    uid = participant_uid if participant_uid is not None else "shared"
    stem = os.path.join(d, f"{kind}.v{FORMAT_VERSION}.{uid}.{key}")
    path = stem + _EXT_FOR_FORMAT[fmt]
    if not os.path.exists(path):
        _bump("unreadable")
        _discard_entry(stem, "its sidecar names a payload file that does not exist")
        return None, stamp
    if consumer is not None:
        from . import provenance
        verdict = provenance.refusal_for(consumer, stamp.get("provenance") or [])
        if verdict is not None:
            _bump("refused_self_derived")
            _log.warning("CacheStore: %s refused the newest %s entry: %s", consumer, kind, verdict)
            raise provenance.SelfDerivedProduct(verdict)
    try:
        payload = _load_payload(path, fmt)
        if fmt == "pickle" and isinstance(payload, dict) \
                and "signature" in payload and "payload" in payload:
            payload = payload["payload"]
    except Exception as exc:                                    # noqa: BLE001
        _bump("unreadable")
        _discard_entry(stem, repr(exc))
        return None, stamp
    _bump("hits")
    return payload, stamp


def _load_payload(path, fmt):
    if fmt == "parquet":
        import pandas as pd
        return pd.read_parquet(path)
    if fmt == "npz":
        import numpy as np
        with np.load(path, allow_pickle=False) as z:
            return {k: z[k] for k in z.files}
    with open(path, "rb") as fh:
        return pickle.load(fh)


def load(kind, participant_uid, signature, *, consumer=None, root=None):
    """The stored product for this signature, or None.

    THE STORED SIGNATURE IS CHECKED AGAINST THE REQUESTED ONE rather than trusted from the file
    name. The name holds a hash, and a hash can in principle collide; more practically a file could
    be left behind by code that built its signature differently. Comparing the signature itself
    means a mismatch is a miss and a rebuild, never a wrong answer.

    EVERY FAILURE HERE IS A MISS, NEVER AN EXCEPTION. A half-written file, a payload written by a
    different array-library version, a permissions change — none of those is a reason for a
    clinician's page to return an error, because the correct answer is always still obtainable by
    rebuilding.

    `consumer` names the module asking. When it is given, an entry whose provenance already
    contains that module's own output is REFUSED, so a module cannot consume a product derived from
    its own choices. See `provenance.py` for why that matters and for the constructed-cycle proof.
    """
    stem = _stem(kind, participant_uid, signature, root=root)
    if stem is None:
        _bump("no_directory")
        return None
    path = _existing_payload_path(stem)
    if path is None:
        _bump("misses")
        return None
    fmt = _FORMAT_FOR_EXT[os.path.splitext(path)[1]]
    try:
        # THE SIDECAR IS CHECKED BEFORE THE PAYLOAD IS OPENED. A sidecar whose signature is not
        # the one asked for means the entry is a miss whatever the payload holds, and a caller
        # that only wants to know whether to write should not pay for reading a payload to find
        # out. Only a legacy pickle with no sidecar has to be opened to be checked.
        meta = _read_meta_file(_meta_path(stem))
        if meta is not None and meta.get("signature_key") != signature_key(signature):
            raise ValueError("the sidecar's signature is not the one being asked for")
        if meta is not None and meta.get("format") not in (None, fmt):
            # A payload in one format under a sidecar describing another means a format change
            # without a FORMAT_VERSION bump left an older file behind. Rebuild rather than serve.
            raise ValueError(f"the payload is {fmt} but the sidecar says {meta.get('format')}")
        raw = _load_payload(path, fmt)

        if fmt == "pickle" and isinstance(raw, dict) \
                and "signature" in raw and "payload" in raw:
            # Both predecessors wrapped the payload in a dict carrying the signature. Entries
            # written before this module existed have no sidecar, so the signature inside the file
            # is the only check available for them, and it is the one that must be honoured.
            if raw.get("signature") != signature:
                raise ValueError("the signature stored in the file is not the one asked for")
            payload = raw["payload"]
            if meta is None:
                _bump("legacy_no_sidecar")
        else:
            if meta is None:
                # A payload with no sidecar in a format that cannot carry the signature itself
                # cannot be verified at all. Refuse it rather than trust a hash: a rebuild is
                # always correct, and a wrong answer is not.
                raise ValueError("no sidecar, so the signature cannot be checked")
            if meta.get("signature_key") != signature_key(signature):
                raise ValueError("the sidecar's signature is not the one being asked for")
            payload = raw

        if consumer is not None and meta is not None:
            from . import provenance
            verdict = provenance.refusal_for(consumer, meta.get("provenance") or [])
            if verdict is not None:
                _bump("refused_self_derived")
                _log.warning("CacheStore: %s refused a %s entry: %s", consumer, kind, verdict)
                raise provenance.SelfDerivedProduct(verdict)

        _bump("hits")
        return payload
    except Exception as exc:
        try:
            from . import provenance
            if isinstance(exc, provenance.SelfDerivedProduct):
                raise                       # a refusal is a decision and must not look like a miss
        except ImportError:
            pass
        _log.warning("CacheStore: discarding an unusable entry %s (%r)", path, exc)
        _bump("unreadable")
        for p in (path, _meta_path(stem)):
            try:
                os.remove(p)
            except OSError:
                pass
        return None


# --------------------------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------------------------

#: HOW MANY CURRENT ENTRIES A KIND MAY KEEP PER PARTICIPANT. The default is one, which is what
#: every kind did before this table existed and what every kind not named here still does: a new
#: entry lands under a new name and the old one is removed, so a month of daily uploads cannot
#: leave seven gigabytes of tiles nothing can read.
#:
#: ONE IS WRONG FOR A KIND WHOSE KEY CARRIES A CHOICE THE READER MAKES. The band-by-length grid is
#: keyed on the pain score among other things (decision 38), so the six scores are six entries of
#: one kind for one participant -- and under a limit of one, writing the sixth deleted the other
#: five. Measured on RCS08 on 2026-09-10 while building the every-score precompute (open item 7):
#: six scores were computed and stored, each reporting success, and ONE file was left on disk. The
#: page then rebuilt a score that had just been "stored", in 8.9 s, and nothing anywhere said why.
#:
#: TWELVE, NOT SIX, AND NOT UNBOUNDED. Six covers one full set of scores; twelve covers two, which
#: is what actually happens -- the daily pass builds every score at the default settings, and a
#: page-triggered pass builds every score at whatever settings the reader is using. At 0.67 MB an
#: entry that is about 8 MB a participant. Keeping history without a limit was rejected for the
#: reason decision 28 gives for Redis: a store that only grows is not a cache.
KEEP_NEWEST_BY_KIND = {
    "biomarker_band_sweep": 12,
    "biomarker_band_correlation": 12,
    "biomarker_band_discrimination": 12,
    # One simulation per candidate band (closed_loop_simulation is keyed on the candidate), so
    # switching the committed band must not evict the last one -- the decision-107 lesson again,
    # met live on 2026-09-11 when the page's own report evicted the probe's entry.
    "closed_loop_simulation": 6,
}


def _entry_stems(names, prefix, marker):
    """The distinct entry stems among these file names, each with its newest file's timestamp.

    An entry is a payload plus a `.meta.json` sidecar, so the two must be kept or removed together;
    grouping by stem is what makes that true by construction rather than by remembering to pair
    them up. The payload's extension varies by format, so the stem is taken as everything before
    the final dot, with the sidecar's two-part suffix handled first.
    """
    stems = {}
    for name in names:
        if not name.startswith(prefix) or marker not in name:
            continue
        stem = name[:-len(".meta.json")] if name.endswith(".meta.json") else name.rsplit(".", 1)[0]
        stems.setdefault(stem, []).append(name)
    return stems


def _sweep_superseded(kind, participant_uid, keep_stem, root=None, keep_newest=None):
    """Remove this participant's older entries of the same kind once the new one has landed.

    A new ingest changes the signature, so the new entry lands under a new name and the old one
    would otherwise sit there forever. One tile entry is 245 MB, so a month of daily uploads would
    leave seven gigabytes of files that can never be read again. Only this participant's files of
    this kind are touched, and ONLY AFTER the replacement is safely in place.

    The entry just written is always kept. Beyond it, `KEEP_NEWEST_BY_KIND` says how many of the
    next-newest entries of this kind survive; the default of one keeps none of them, which is the
    behaviour every kind had before that table existed. See its own note for why one is the wrong
    answer for a kind whose key carries a choice the reader makes.
    """
    d = kind_dir(kind, create=False, root=root)
    if d is None:
        return 0
    prefix = f"{kind}.v"
    marker = f".{_safe_uid(participant_uid)}." if participant_uid is not None else ".shared."
    keep = os.path.basename(keep_stem)
    limit = int(KEEP_NEWEST_BY_KIND.get(kind, 1) if keep_newest is None else keep_newest)
    removed = 0
    try:
        names = os.listdir(d)
    except OSError:
        return 0

    stems = _entry_stems(names, prefix, marker)
    others = [s for s in stems if not s.startswith(keep) and not keep.startswith(s)]
    if limit > 1 and others:
        # Newest first by the most recent file in the entry, so an entry read or rewritten recently
        # outlives one nothing has touched. `limit - 1` because the entry just written holds the
        # first place and is never a candidate for removal.
        def _newest(stem):
            best = 0.0
            for n in stems[stem]:
                try:
                    best = max(best, os.path.getmtime(os.path.join(d, n)))
                except OSError:
                    pass
            return best
        others.sort(key=_newest, reverse=True)
        others = others[limit - 1:]

    for stem in others:
        for name in stems[stem]:
            try:
                os.remove(os.path.join(d, name))
                removed += 1
            except OSError:
                pass
    if removed:
        _bump("swept", removed)
    return removed


def _write_payload(tmp, payload, fmt, signature):
    """Write the payload and return its size in bytes."""
    if fmt == "parquet":
        # The signature key rides in the table's own metadata as well as in the sidecar, so a
        # payload separated from its sidecar can still be identified rather than guessed at.
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pandas(payload, preserve_index=True)
        md = dict(table.schema.metadata or {})
        md[b"bravo_signature_key"] = signature_key(signature).encode("ascii")
        pq.write_table(table.replace_schema_metadata(md), tmp, compression="zstd")
        return os.path.getsize(tmp)
    if fmt == "npz":
        import numpy as np
        with open(tmp, "wb") as fh:
            np.savez_compressed(fh, **payload)
        return os.path.getsize(tmp)
    blob = pickle.dumps({"signature": signature, "payload": payload}, protocol=5)
    with open(tmp, "wb") as fh:
        fh.write(blob)
    return len(blob)


def store(kind, participant_uid, signature, payload, *, provenance=None, trigger=None,
          n_recordings=None, fmt=None, extra=None, writer=None, root=None, max_bytes=None):
    """Write the product where the other worker processes can find it. True if it landed.

    WRITTEN TO A TEMPORARY NAME AND THEN MOVED INTO PLACE. All four workers can finish the same
    build at the same moment, and a reader can arrive in the middle of a write. Writing straight to
    the final name would let that reader see a truncated file; the move is atomic within a
    directory, so a reader sees either the old complete entry or the new complete one and never a
    partial one. The temporary name carries the process id so two writers cannot tread on each
    other's temporary file either.

    THE SIDECAR IS MOVED LAST AND IS THE COMMIT MARKER, so an entry is never visible without the
    stamp and the provenance that describe it.

    `provenance` is the list of keys of every input this product derived from, and `writer` names
    the module that produced it. Both are what make the refusal in `load` possible; a product
    written without them can be consumed by anything, which is why every write-back call site
    passes them.
    """
    stem = _stem(kind, participant_uid, signature, root=root)
    if stem is None:
        return False
    # A DERIVED PRODUCT MUST NAME ITS WRITER. Without it the refusal in `load` has nothing to
    # match, and a sidecar with no writer and no provenance is indistinguishable from a raw
    # input to anything that later cites it. Refusing here makes a call site that forgot fail at
    # write time, where it is found, rather than widen what looks safe to read. Missing
    # provenance on a derived kind is counted and logged rather than refused, because an empty
    # chain is sometimes true (nothing derived from another module's output yet).
    from . import provenance as _prov
    if kind not in _prov.RAW_KINDS and writer is None:
        _bump("refused_no_writer")
        _log.warning("CacheStore: refusing to write derived kind %r with no writer", kind)
        return False
    if kind not in _prov.RAW_KINDS and provenance is None:
        _bump("written_without_provenance")
        _log.warning("CacheStore: derived kind %r written with no provenance chain", kind)
    fmt = fmt or choose_format(payload)
    final = stem + _EXT_FOR_FORMAT[fmt]
    tmp = f"{final}.{os.getpid()}.tmp"
    tmp_meta = f"{_meta_path(stem)}.{os.getpid()}.tmp"
    limit = max_bytes if max_bytes is not None else MAX_BYTES_BY_KIND.get(kind, MAX_BYTES_DEFAULT)
    try:
        size = _write_payload(tmp, payload, fmt, signature)
        if size > limit:
            _bump("refused_too_big")
            _log.info("CacheStore: not storing a %.1f MB %s entry (limit %.0f MB); it stays in "
                      "this process's memory only", size / 1e6, kind, limit / 1e6)
            os.remove(tmp)
            return False
        meta = {
            "kind": kind,
            "participant_uid": participant_uid,
            "signature_key": signature_key(signature),
            "format": fmt,
            "format_version": FORMAT_VERSION,
            "payload_bytes": int(size),
            "written_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "trigger": trigger or "unspecified",
            "writer": writer,
            "n_recordings": (int(n_recordings) if n_recordings is not None else None),
            "provenance": list(provenance or []),
        }
        if extra:
            meta["extra"] = extra
        with open(tmp_meta, "w", encoding="utf8") as fh:
            json.dump(meta, fh, sort_keys=True)
        os.replace(tmp, final)
        os.replace(tmp_meta, _meta_path(stem))
        _bump("writes")
        if kind not in KEEP_HISTORY_KINDS:
            _sweep_superseded(kind, participant_uid, stem, root=root)
        # THE LEDGER RECORDS THE PRODUCTION STORE ONLY. A write under a caller's own root, or under
        # the test override, is not part of the record of what the server holds: the container
        # test suite had written 214 rows for a participant called "test-participant" into the
        # live table, and the ledger carries no directory, so nothing could tell them apart.
        if root is None and DIR_OVERRIDE is None:
            try:
                from . import ledger
                ledger.record(meta)
            except Exception as exc:            # a ledger outage must never fail a page
                _log.info("CacheStore: could not record %s in the ledger (%r)", kind, exc)
        return True
    except Exception as exc:
        _log.warning("CacheStore: could not write %s (%r)", final, exc)
        for p in (tmp, tmp_meta):
            try:
                os.remove(p)
            except OSError:
                pass
        return False


def product_key(kind, participant_uid, signature):
    """The name by which other products refer to this one in their provenance."""
    return f"{kind}/{participant_uid}/{signature_key(signature)}"


def store_if_absent(kind, participant_uid, signature, build, **kw):
    """`(payload, wrote)` — building and writing only when the key does not match.

    THE KEY DECIDES, NOT THE CALLER. This is the entry point that makes that true by construction
    rather than by every caller remembering to check first.
    """
    # The SAME root for the read as for the write. Before this line the read went to the
    # production root while the write went to the caller's, so under a test override the key
    # never matched and every call wrote: the first snapshot test caught it.
    got = load(kind, participant_uid, signature, consumer=kw.get("consumer"), root=kw.get("root"))
    if got is not None:
        return got, False
    payload = build()
    if payload is None:
        return None, False
    kw.pop("consumer", None)
    wrote = store(kind, participant_uid, signature, payload, **kw)
    return payload, wrote


# --------------------------------------------------------------------------------------------
# reporting and housekeeping
# --------------------------------------------------------------------------------------------

def stats(kind=None, root=None):
    """What the store holds and what it has done, for the interface and for the tests."""
    r = root_dir(root)
    dirs, total = {}, 0
    if r is not None and os.path.isdir(r):
        for sub in sorted(os.listdir(r)):
            d = os.path.join(r, sub)
            if not os.path.isdir(d):
                continue
            n, b = 0, 0
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for name in names:
                if name.endswith(".tmp"):
                    continue
                try:
                    b += os.path.getsize(os.path.join(d, name))
                except OSError:
                    pass               # a concurrent sweep can remove a file between the two calls
                if not name.endswith(".meta.json"):
                    n += 1
            dirs[sub] = {"entries": n, "bytes": b}
            total += b
    with _LOCK:
        events = dict(_EVENTS)
    out = {"root": r, "directories": dirs, "bytes": total, "events": events,
           "max_bytes_default": MAX_BYTES_DEFAULT}
    if kind is not None:
        out["kind_directory"] = kind_dir(kind, create=False, root=root)
    return out


def clear(kind=None, root=None):
    """Remove stored entries, including ones written by an older format version.

    With no argument this clears every kind. Both predecessors exposed this, and the closed-loop
    module calls it on a deliberate recompute.
    """
    r = root_dir(root)
    removed = 0
    if r is None or not os.path.isdir(r):
        return 0
    subs = [_KIND_DIRS.get(kind, kind)] if kind is not None else sorted(os.listdir(r))
    for sub in subs:
        d = os.path.join(r, sub)
        if not os.path.isdir(d):
            continue
        for name in list(os.listdir(d)):
            if not name.endswith((".pkl", ".parquet", ".npz", ".meta.json", ".tmp")):
                continue
            try:
                os.remove(os.path.join(d, name))
            except OSError:
                continue
            # ENTRIES removed, not files. A sidecar is part of its entry rather than a second
            # thing, and a caller asking "how many did you clear" means entries.
            if not name.endswith((".meta.json", ".tmp")):
                removed += 1
    if kind is None:
        with _LOCK:
            for k in _EVENTS:
                _EVENTS[k] = 0
    return removed
