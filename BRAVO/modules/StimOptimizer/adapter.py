"""Build the StimOptimizer epoch-level design matrix from the running platform's own data.

WHY THIS READS THE STORED JSON RATHER THAN THE THERAPY TABLES
-------------------------------------------------------------
BRAVO normalizes stimulation settings into ``Therapy`` -> ``ElectricalTherapy`` ->
``ElectricalStimulation``. Those rows are dated and carry amplitude, pulse width, frequency and a
bare ``contact`` index list — but **they do not carry the hemisphere**. Recovering it means mapping
contact indices through the device's lead ``Target``/``CustomName`` definitions, and at the same
timestamp there are several rows differing by GROUP rather than by side. Getting that mapping subtly
wrong would silently swap the two hemispheres, which is a wrong-science failure, not a crash.

So this adapter reads the participant's stored session-report JSON through
``DataCurator.loadCacheFile`` and reuses the SAME dual-schema active-group parser that was validated
against the RCS08 file census, where the hemisphere is stated explicitly by the device
(``LeftHemisphere``/``RightHemisphere`` keys, or ``SensingChannel[].HemisphereLocation``). The
platform already stores every byte it needs; nothing is re-fetched from disk outside BRAVO.

THE TWO SCHEMAS (this is the trap that produced an incomplete record once already)
---------------------------------------------------------------------------------
Amplitude lives in one of two places depending on how a group is configured:

* **Legacy.** ``ProgramSettings.{LeftHemisphere,RightHemisphere}.Programs[]`` with the delivered
  amplitude in ``AmplitudeInMilliAmps`` and the rate at group level in ``ProgramSettings.RateInHertz``.
* **BrainSense.** A sensing-configured group has **no hemisphere keys at all**. The per-hemisphere
  program moves to ``ProgramSettings.SensingChannel[]``, one entry per hemisphere identified by
  ``HemisphereLocation``, with the delivered amplitude in ``SuspendAmplitudeInMilliAmps``.

A parser that reads only the first silently returns an incomplete history. Both are handled here.

TIME BASE
---------
Session-report filenames carry a LOCAL wall-clock stamp while the JSON's ``SessionDate`` field is
UTC — a seven-hour offset for this site that silently reduced a naive join to a handful of rows once.
This adapter uses ``SessionDate`` (already UTC) throughout and never parses the filename, so there is
no timezone arithmetic to get wrong. ``GroupHistory`` snapshots carry their own UTC ``SessionDate``.

VALIDATION (2026-08-30, against the file-based census this replaces)
-------------------------------------------------------------------
On the 1,239 shared (timestamp, hemisphere) keys — all of them ``GroupHistory`` rows, which use the
same UTC field in both reconstructions — amplitude, pulse width, rate, cathode label and schema tag
are **identical at 100%**. The ``session`` rows do not share keys because the census keyed them off
the FILENAME stamp while this adapter uses ``SessionDate``; measured on twelve August files the two
differ by a median of **1.4 minutes** (range 0.8 to 65.1 minutes, the outlier being 2026-08-06).
``SessionDate`` is the device's own timestamp and is preferred. Note the interaction with the
1-minute wash-in default: a shift of that size can move a report across the wash-in boundary, so it
is a real if small difference, not a rounding artefact.
"""
from __future__ import annotations

import hashlib as _hashlib
import json
import logging

import numpy as np
import pandas as pd

# THE IMPORT ROOT DIFFERS BETWEEN THE TWO TEST RUNNERS, so both spellings are tried. The container
# puts `/usr/src/BRAVO` on the path, which makes the package `modules.CacheStore`; the host suite
# runs from `BRAVO/modules` with that directory as the root, which makes it `CacheStore`.
try:
    from modules.CacheStore import provenance as _provenance
    from modules.CacheStore import store as _cache_store
    from modules.DecodeCommon import data_start as _data_start
except ImportError:                                   # pragma: no cover - depends on the runner
    from CacheStore import provenance as _provenance
    from CacheStore import store as _cache_store
    from DecodeCommon import data_start as _data_start

_log = logging.getLogger(__name__)

#: Tests point this at a directory of their own. It is passed THROUGH to the shared store rather
#: than resolved here, so there is still only one resolver.
_SHARED_CACHE_DIR_OVERRIDE = None

#: The two products this module writes to the one store (Track A step 5 of the approved plan,
#: "Write the therapy and pain matched table into the store").
#:
#: `therapy_settings` is the dated per-hemisphere settings stream read from the participant's stored
#: Percept files. It is a RAW input in the provenance sense: it records what the device was
#: programmed to deliver, and no module's analysis choice produced it. Building it opens, decrypts
#: and parses every stored file, which is the single most expensive thing this module does, so a
#: stored copy is what turns a request that used to pay that cost every time into one that reads a
#: small table.
#:
#: `therapy_pain_matched` is the epoch-level design matrix: the settings epochs with the pain
#: reports aggregated onto them. Its key carries the settings key AND the pain-report snapshot key,
#: so a newly filed report changes the key and a stale rating can never be served from it. It is
#: registered as raw-derived in `CacheStore/provenance.py` because it is a deterministic join of two
#: raw inputs and embodies no module's choice.
THERAPY_SETTINGS_KIND = "therapy_settings"
THERAPY_PAIN_MATCHED_KIND = "therapy_pain_matched"

#: Bumped when the RULE that produces either table changes: the group parser, the epoch keys, the
#: aggregation. The constants that shape a table are in its key already.
#: v2 (2026-09-12, review S8): the stream carries `upper_is_patient_limit`, whether each row's
#: programmed upper limit is a patient limit (a clinician's ceiling) or the adaptive amplitude
#: limit of a group running adaptive therapy (decision 136). A stream stored under v1 lacks the
#: column and is rebuilt once (about 33 s on RCS08).
#: v3 (2026-09-24, the PI): the stream starts at the device's implant date (`apply_data_start`);
#: on RCS08 its first rows had been four January-April 2025 snapshots the patient never received.
_THERAPY_SETTINGS_RULE_VERSION = "v3_active_groups_from_implant_date"
_THERAPY_PAIN_MATCHED_RULE_VERSION = "v1_epoch_means"

#: The frame attribute under which a table carries the key of the store entry it came from, so a
#: product derived from it can cite it. The same name the Biomarkers module uses for the pain-report
#: snapshot, on purpose: one name, whichever module handed the frame over.
STORE_KEY_ATTR = _cache_store.STORE_KEY_ATTR

#: The frame attribute the builder sets to say how many stored files it could not read. A stream
#: built with unreadable files is returned but NOT stored, because the file set that keys it has not
#: changed and the stored copy would carry the gap until it did.
UNREADABLE_ATTR = "n_unreadable_source_files"

# Percept session-report SourceFile types that carry Groups/GroupHistory.
_JSON_SOURCE_TYPES = ("MedtronicJSON", "DefaultType")

# Chronic REDCap item columns the optimizer can target, and the site each belongs to. Keep in step
# with StimOptimizer.routines.objective.ITEM_COLUMNS.
PRO_ITEMS = ("left_leg_vas", "back_vas", "nrs", "vas", "mpq_sum", "relief")

# Parameters whose change opens a new exposure epoch. Anything the patient could feel.
_EPOCH_KEYS = ("freq_hz", "amp_mA_Left", "amp_mA_Right", "pw_us_Left", "pw_us_Right",
               "cathode_Left", "cathode_Right")


# --------------------------------------------------------------------------------------------------
# device JSON -> dated per-hemisphere settings
# --------------------------------------------------------------------------------------------------
def contact_label(estates):
    """Cathode/anode label from an ``ElectrodeState`` list. Verbatim from the validated census."""
    neg, pos = [], []
    for e in (estates or []):
        nm = (e.get("Electrode", "") or "").replace("ElectrodeDef.", "") \
            .replace("SenSight_", "").replace("Sensight_", "")
        st = (e.get("ElectrodeStateResult", "") or "").split(".")[-1]
        if st == "Negative":
            neg.append(nm)
        elif st == "Positive":
            pos.append(nm)
    return ("-".join(sorted(neg)) or "none", "+".join(sorted(pos)) or "case")


def _sensing_upper_is_patient_limit(ch):
    """Is a sensing channel's ``UpperLimitInMilliAmps`` a PATIENT limit, or the adaptive
    amplitude limit of a group running adaptive therapy? Decision 136's rule, IMPORTED from the
    closed-loop module (``session_report_facts._patient_limits_configured``) rather than retyped:
    a limit on a channel whose ``AdaptiveTherapyStatus`` is RUNNING is the controller's own
    range, not a clinician's ceiling. ``None`` when the channel carries no limit or the rule
    cannot be read; ``True``/``False`` otherwise.
    """
    u, lo = ch.get("UpperLimitInMilliAmps"), ch.get("LowerLimitInMilliAmps")
    if u is None and lo is None:
        return None
    try:
        try:
            from modules.ClosedLoopDeployment import session_report_facts as _srf
        except ImportError:
            from ClosedLoopDeployment import session_report_facts as _srf
    except Exception as exc:                          # noqa: BLE001 -- the rule could not be read
        _log.debug("StimOptimizer: decision 136's limit rule unavailable (%r)", exc)
        return None
    v = _srf._patient_limits_configured([ch], [(u, lo)])
    return None if v is None else bool(v)


def group_settings(g):
    """Amplitude / pulse width / rate / contacts per hemisphere, handling BOTH schemas.

    Legacy hemisphere keys win when present; the sensing channel fills any side they did not cover
    (``setdefault``), so a group carrying both never double-counts.

    ``upper_is_patient_limit`` (2026-09-12, review S8): a legacy program's upper limit is a
    clinician's ceiling (True when present); a sensing channel's is judged by decision 136's rule
    (see :func:`_sensing_upper_is_patient_limit`). ``None`` when no limit is recorded.
    """
    ps = g.get("ProgramSettings") or {}
    out = {}
    for hemi, tag in (("LeftHemisphere", "Left"), ("RightHemisphere", "Right")):
        h = ps.get(hemi)
        if isinstance(h, dict) and (h.get("Programs") or []):
            pr = h["Programs"][0]
            cath, _ = contact_label(pr.get("ElectrodeState"))
            upper = pr.get("UpperLimitInMilliAmps")
            out[tag] = dict(amp=pr.get("AmplitudeInMilliAmps"),
                            pw=pr.get("PulseWidthInMicroSecond"),
                            rate=ps.get("RateInHertz"),
                            upper=upper,
                            upper_is_patient_limit=(True if upper is not None else None),
                            cathode=cath, schema="hemisphere")
    for ch in (ps.get("SensingChannel") or []):
        tag = ((ch.get("HemisphereLocation") or "").split(".")[-1])
        if tag not in ("Left", "Right"):
            continue
        cath, _ = contact_label(ch.get("ElectrodeState"))
        out.setdefault(tag, dict(amp=ch.get("SuspendAmplitudeInMilliAmps"),
                                 pw=ch.get("PulseWidthInMicroSecond"),
                                 rate=ch.get("RateInHertz") or ps.get("RateInHertz"),
                                 upper=ch.get("UpperLimitInMilliAmps"),
                                 upper_is_patient_limit=_sensing_upper_is_patient_limit(ch),
                                 cathode=cath, schema="sensing"))
    return out


def _participant_uid(participant):
    return str(getattr(participant, "uid", participant))


def source_file_signature(participant, *, source_types=_JSON_SOURCE_TYPES):
    """Identity of the stored files the settings stream reads, FROM THE DATABASE ROWS ALONE.

    Decision 24 in `DECISIONS_and_open_items.md`: a stored product must be findable before anything
    is decoded, so the key is built from the rows and never from the decoded content. Each file
    contributes its uid, its content hash and its type; the file NAME is deliberately left out,
    because the export file names on this platform can carry a patient's name and nothing derived
    from them belongs in a key that is written to disk. A re-upload that replaces a file in place
    changes its content hash; an added or removed file changes the count and the digest.

    Returns a tuple, or raises when there is no database to ask (library mode), in which case the
    caller builds the stream without the store.
    """
    from Server import models

    rows = []
    for sf in models.SourceFile.objects.filter(owner=participant):
        if source_types and getattr(sf, "type", None) not in source_types:
            continue
        rows.append((str(getattr(sf, "uid", "")), str(getattr(sf, "hashed", "")),
                     str(getattr(sf, "type", ""))))
    rows.sort()
    blob = "|".join("~".join(r) for r in rows).encode("utf8")
    return (THERAPY_SETTINGS_KIND, _THERAPY_SETTINGS_RULE_VERSION, _participant_uid(participant),
            tuple(source_types) if source_types else None, len(rows),
            _hashlib.blake2b(blob, digest_size=16).hexdigest(),
            float(_data_start.data_start_s(participant)))


def settings_stream(participant, *, source_types=_JSON_SOURCE_TYPES) -> pd.DataFrame:
    """Every dated ACTIVE-group setting for a participant, one row per (timestamp, hemisphere).

    THE STORE ANSWERS FIRST. The key is the identity of the participant's stored files (see
    `source_file_signature`), so the same file set is parsed once and then read back as a small
    Parquet table by every worker; a new upload changes the key and the stream is rebuilt. The
    returned frame carries its store key under `STORE_KEY_ATTR` so the matched table built from it
    can cite it. A stream with unreadable files, or an empty one, is returned but not stored.

    With no database to ask, or with the store turned off, this builds exactly as it always did.
    Reads both the end-of-session state (``Groups.Final``) and the dated between-session snapshots
    (``GroupHistory``). The snapshots matter: a session-only reconstruction loses the resolution that
    makes short exposures visible at all.
    """
    try:
        sig = source_file_signature(participant, source_types=source_types)
    except Exception as exc:                   # noqa: BLE001 — no database: build, do not store
        _log.debug("StimOptimizer: no source-file signature, building the stream unstored (%r)", exc)
        return _build_settings_stream(participant, source_types=source_types)
    uid = _participant_uid(participant)
    not_stored = []

    def build():
        out = _build_settings_stream(participant, source_types=source_types)
        if len(out) == 0 or out.attrs.get(UNREADABLE_ATTR, 0):
            not_stored.append(out)
            return None
        return out

    got, _wrote = _cache_store.store_if_absent(
        THERAPY_SETTINGS_KIND, uid, sig, build,
        writer="stim_optimizer", trigger="settings_stream", provenance=[],
        n_recordings=sig[4], extra={"source_types": list(source_types or ())},
        root=_SHARED_CACHE_DIR_OVERRIDE)
    if got is None:
        return not_stored[0] if not_stored else _build_settings_stream(
            participant, source_types=source_types)
    got.attrs[STORE_KEY_ATTR] = _cache_store.product_key(THERAPY_SETTINGS_KIND, uid, sig)
    return got


def _rows_from_session(d) -> list:
    """The settings rows ONE decrypted session file contributes, in the order the builder has
    always made them: the active groups of its end-of-session state, then those of each dated
    snapshot. A pure function of the file's content, which is what lets the rows be kept per file
    (`THERAPY_SETTINGS_BY_FILE_KIND`)."""
    recs = []
    t_session = pd.to_datetime(d.get("SessionDate"), errors="coerce", utc=True)
    for g in ((d.get("Groups") or {}).get("Final") or []):
        if not g.get("ActiveGroup"):
            continue
        for tag, s in group_settings(g).items():
            recs.append(dict(t=t_session, src="session", hemi=tag, **s))
    for snap in (d.get("GroupHistory") or []):
        ts = pd.to_datetime(snap.get("SessionDate"), errors="coerce", utc=True)
        for g in (snap.get("Groups") or []):
            if not g.get("ActiveGroup"):
                continue
            for tag, s in group_settings(g).items():
                recs.append(dict(t=ts, src="history", hemi=tag, **s))
    return recs


# --------------------------------------------------------------------------------------------------
# the per-file settings history: each stored file parsed once (the PI's yes, 2026-09-25)
# --------------------------------------------------------------------------------------------------
#: The rows each stored session file contributed to the settings stream, kept in the one store so
#: that a new file costs one parse instead of all of them. Measured on RCS08 on 2026-09-25 before
#: building it: a cold build of the stream decrypts 582 files (4.1 GB of JSON text) and takes 34.4 s,
#: of which reading, checking, decompressing, decrypting and parsing the files is all but 0.7 s --
#: JSON parsing 18.7 s, decryption 11.9 s, file reads 5.9 s -- and the frame, sort and implant-date
#: cut 0.01 s. Every new session file used to repeat all of it.
#:
#: WHAT THE ENTRY IS. A mapping from each file's identity -- its uid and the content hash the
#: database holds for it, never its name, which can carry a patient's name -- to the list of row
#: dicts `_rows_from_session` made from it, pickled whole. The hash is the HMAC the loader checks
#: on every read, so a row list filed under it describes exactly the bytes that would be decrypted.
#: A file that could not be read is never in it: a build with an unreadable file writes no entry,
#: so the next build tries that file again rather than remembering it as "no rows". A file that
#: parsed to no rows IS in it, as an empty list.
#:
#: HOW IT IS READ. The newest entry for the participant whose parsing rule matches is the donor;
#: every file whose identity it holds is reused, the rest are decrypted and parsed, and the rows are
#: assembled in the database's file order, then framed, dropped, sorted and cut at the implant date
#: exactly as before. So the list handed to the frame is the same list of equal dicts in the same
#: order, and the (unstable) sort sees the same input.
#:
#: WHY RAW. Like `therapy_settings`, it records what the device was programmed to deliver, parsed
#: from the device's own files with no module's choice in between; it is the same product before
#: its rows are pooled. Nothing reads it as evidence and nothing cites it.
#:
#: ONE ENTRY PER PARTICIPANT (the store's default), replaced whole on each new file set: the donor
#: is always the previous entry, and an older one could only hold files the newer one also holds.
THERAPY_SETTINGS_BY_FILE_KIND = "therapy_settings_by_file"
_THERAPY_SETTINGS_BY_FILE_RULE_VERSION = "v1_rows_per_source_file"

_PARSE_DIGEST = None


def _settings_parse_digest():
    """A digest of the code that turns one file into rows, and of the pandas version that parses
    its dates, so a change to either reuses nothing (decision 41's code digest, narrowed to the
    parse). Includes decision 136's limit rule, which lives in the closed-loop module; when that
    rule cannot be imported the rows differ (the limit reads None), so the digest says so."""
    global _PARSE_DIGEST
    if _PARSE_DIGEST is None:
        import inspect
        parts = [_THERAPY_SETTINGS_BY_FILE_RULE_VERSION, "pandas " + pd.__version__]
        for fn in (_rows_from_session, group_settings, contact_label,
                   _sensing_upper_is_patient_limit):
            parts.append(inspect.getsource(fn))
        try:
            try:
                from modules.ClosedLoopDeployment import session_report_facts as _srf
            except ImportError:
                from ClosedLoopDeployment import session_report_facts as _srf
            parts.append(inspect.getsource(_srf._patient_limits_configured))
        except Exception:                             # noqa: BLE001 -- the rule could not be read
            parts.append("decision 136's limit rule unavailable")
        _PARSE_DIGEST = _hashlib.blake2b("\n".join(parts).encode("utf8"),
                                         digest_size=16).hexdigest()
    return _PARSE_DIGEST


def _file_identity(sf):
    """A stored file's identity from its database row: uid and content hash, never its name."""
    return f"{getattr(sf, 'uid', '')}~{getattr(sf, 'hashed', '')}"


def _rows_by_file_signature(participant, source_types, idents, parse_digest):
    blob = "|".join(sorted(idents)).encode("utf8")
    return (THERAPY_SETTINGS_BY_FILE_KIND, _THERAPY_SETTINGS_BY_FILE_RULE_VERSION, parse_digest,
            _participant_uid(participant), tuple(source_types) if source_types else None,
            len(idents), _hashlib.blake2b(blob, digest_size=16).hexdigest())


def _rows_by_file_donor(participant, source_types, parse_digest):
    """`(rows_by_identity, signature_key)` of the newest per-file entry written under this parsing
    rule, or `({}, None)`. A half-written entry has no sidecar and is never seen; an entry whose
    payload cannot be read is discarded by the store and reads as none."""
    want = list(source_types or ())

    def match(meta):
        extra = meta.get("extra") or {}
        return extra.get("parse_digest") == parse_digest and extra.get("source_types") == want
    try:
        got, stamp = _cache_store.load_newest(THERAPY_SETTINGS_BY_FILE_KIND,
                                              _participant_uid(participant),
                                              root=_SHARED_CACHE_DIR_OVERRIDE, match=match)
    except Exception as exc:                          # noqa: BLE001 -- a donor is an optimisation
        _log.info("StimOptimizer: per-file settings rows unreadable, parsing every file (%r)", exc)
        return {}, None
    if not isinstance(got, dict):
        return {}, None
    return got, (stamp or {}).get("signature_key")


def _build_settings_stream(participant, *, source_types=_JSON_SOURCE_TYPES) -> pd.DataFrame:
    """Parse the stored Percept files into the settings stream. The `therapy_settings` entry is
    not consulted here; the per-file rows (`THERAPY_SETTINGS_BY_FILE_KIND`) are, so only files not
    seen before are decrypted and parsed."""
    from Server import models
    from modules import DataCurator

    sfs = [sf for sf in models.SourceFile.objects.filter(owner=participant)
           if not (source_types and getattr(sf, "type", None) not in source_types)]
    parse_digest = _settings_parse_digest()
    known, donor_key = _rows_by_file_donor(participant, source_types, parse_digest)
    recs, rows_by_file, n_read, n_failed, n_parsed = [], {}, 0, 0, 0
    for sf in sfs:
        ident = _file_identity(sf)
        rows = known.get(ident)
        if rows is None:
            try:
                d = json.loads(DataCurator.loadCacheFile(sf))
            except Exception as e:                  # encrypted-cache miss, non-JSON, pointer moved
                n_failed += 1
                _log.debug("StimOptimizer: could not read SourceFile %s (%s)",
                           getattr(sf, "uid", "?"), e)
                continue
            rows = _rows_from_session(d)
            n_parsed += 1
        n_read += 1
        rows_by_file[ident] = rows
        recs.extend(rows)
    if n_failed:
        _log.info("StimOptimizer: read %d source files, %d unreadable", n_read, n_failed)
    else:
        # THE KEY DECIDES WHETHER TO WRITE: the same file set under the same rule is already on
        # disk and is left byte-identical. Never written with an unreadable file (see above).
        sig = _rows_by_file_signature(participant, source_types, list(rows_by_file), parse_digest)
        if rows_by_file and _cache_store.signature_key(sig) != donor_key:
            _cache_store.store(
                THERAPY_SETTINGS_BY_FILE_KIND, _participant_uid(participant), sig, rows_by_file,
                writer="stim_optimizer", trigger="settings_stream", provenance=[],
                n_recordings=len(rows_by_file),
                extra={"source_types": list(source_types or ()), "parse_digest": parse_digest,
                       "n_parsed_this_build": int(n_parsed)},
                root=_SHARED_CACHE_DIR_OVERRIDE)
    if not recs:
        out = pd.DataFrame(columns=["t", "src", "hemi", "amp", "pw", "rate", "upper",
                                    "upper_is_patient_limit", "cathode", "schema"])
    else:
        out = pd.DataFrame(recs).dropna(subset=["t", "amp", "rate"])
        out = out.sort_values("t").reset_index(drop=True)
        out = apply_data_start(out, _data_start.data_start_s(participant))
    out.attrs[UNREADABLE_ATTR] = int(n_failed)
    return out


def apply_data_start(stream: pd.DataFrame, start_s) -> pd.DataFrame:
    """The stream from the participant's implant date on (the PI, 2026-09-24; `DecodeCommon.data_start`).

    A setting holds until the next change, so per side the rows at the LAST timestamp before the
    start are kept and moved to the start -- the setting in force when the device went in -- and
    every earlier row is dropped. On RCS08 that drops four January-April 2025 snapshots the patient
    never received and starts the stream on 2025-07-16 at the setting then in force. With no start,
    the stream is returned unchanged.
    """
    if stream is None or len(stream) == 0 or not start_s or float(start_s) <= 0:
        return stream
    start = pd.Timestamp(float(start_s), unit="s", tz="UTC")
    t = pd.to_datetime(stream["t"], utc=True)
    before = t < start
    if not before.any():
        return stream
    keep = ~before
    moved = pd.Series(False, index=stream.index)
    for _hemi, idx in stream.index[before].to_series().groupby(stream.loc[before, "hemi"]):
        last_t = t.loc[idx].max()
        at_last = idx[t.loc[idx] == last_t]
        keep.loc[at_last] = True
        moved.loc[at_last] = True
    out = stream.loc[keep].copy()
    out.loc[moved.loc[keep], "t"] = start
    return out.sort_values("t", kind="stable").reset_index(drop=True)


#: The columns that every settings stream must carry. ``settings_stream`` always returns a frame
#: with these columns, including when it found nothing at all and returns zero rows. Anything handed
#: in through the optional ``stream`` argument below is checked against this list.
_STREAM_REQUIRED_COLUMNS = ("t", "src", "hemi", "amp", "pw", "rate", "cathode", "schema")


def _use_stream_or_build_one(participant, stream):
    """Give back the settings stream that was handed in, or build a fresh one when none was.

    WHY THIS EXISTS. Reading, decrypting and parsing the participant's stored Percept files is the
    single most expensive thing this module does. Measured on participant RCS08 through the bridge
    on 2026-09-06, one pass opens 568 stored files (556 of type MedtronicJSON and 12 of type
    DefaultType), takes 33.65 seconds and yields 6,617 settings rows. Two functions in this file
    each needed that same frame, so a caller that wanted both paid for it twice, which is 1,136 file
    reads instead of 568. Both of those functions now take an optional ``stream`` argument, and when
    a caller passes the frame it already built, the second pass does not happen. When a caller
    passes nothing, the frame is built here exactly as it always was, so no existing caller changes
    behaviour.

    A FRAME THAT IS MISSING A COLUMN RAISES HERE RATHER THAN BEING QUIETLY ACCEPTED. This project
    has already been bitten once by a place that named columns which did not exist on the real frame
    and then carried on as if everything were fine, so the wrong answer was produced with no error
    anywhere. If somebody hands in an object that is not a pandas frame, or a frame that does not
    carry the columns the settings stream is defined to carry, that is a programming mistake and it
    stops here with a message naming what was missing.

    Note that an empty settings stream is a legitimate answer and is accepted: a participant with no
    readable Percept files gets zero rows, but ``settings_stream`` still labels those zero rows with
    the full set of columns, so the check below passes.
    """
    if stream is None:
        return settings_stream(participant)
    if not isinstance(stream, pd.DataFrame):
        raise TypeError("the stream argument must be the pandas frame that "
                        "StimOptimizer.adapter.settings_stream returns, or None to build one here; "
                        f"got {type(stream).__name__}")
    missing = [c for c in _STREAM_REQUIRED_COLUMNS if c not in stream.columns]
    if missing:
        raise KeyError("the stream handed in is missing the columns "
                       f"{missing}, which the settings stream is defined to carry; it has "
                       f"{sorted(stream.columns)}")
    return stream


def exposure_epochs(stream: pd.DataFrame) -> pd.DataFrame:
    """Collapse the settings stream into exposure epochs, opening a new one on ANY change.

    Returns one row per epoch with ``t_start``, ``t_end``, ``dur_h`` and the wide per-hemisphere
    settings. The final epoch is left open-ended at the last observation, so its ``dur_h`` is a
    lower bound rather than a measured duration — callers that weight by exposure must treat it so.
    """
    if stream.empty:
        return pd.DataFrame()
    wide = stream.pivot_table(index="t", columns="hemi",
                             values=["amp", "pw", "rate", "cathode"],
                             aggfunc="first")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.sort_index()
    # One shared frequency: the device runs both sides at the same rate. Prefer the left, fall back
    # to the right so a unilateral record still yields a frequency.
    #
    # THAT ASSUMPTION IS CHECKED, NOT TRUSTED (review S9, 2026-09-12). An epoch opens on
    # `freq_hz`, which is the Left rate wherever the Left has one, so a change of the Right rate
    # alone would open no epoch and every Right-side surface would be fitted at the Left's rate.
    # Measured on RCS08's stream: 1,172 timestamps carry both sides and 0 carry different rates.
    # The count of timestamps where the two sides disagree is carried on the frame as
    # `attrs["n_timestamps_rates_differ"]`; a record where it is not zero needs `rate_Right` in
    # `_EPOCH_KEYS` and a bump of `_THERAPY_SETTINGS_RULE_VERSION`, and `rates_agree_across_sides`
    # says so rather than letting the epochs quietly carry one side's rate for both.
    freq = None
    n_differ = 0
    if "rate_Left" in wide.columns and "rate_Right" in wide.columns:
        both = wide[["rate_Left", "rate_Right"]].dropna()
        n_differ = int((~np.isclose(pd.to_numeric(both["rate_Left"], errors="coerce"),
                                    pd.to_numeric(both["rate_Right"], errors="coerce"))).sum())
        if n_differ:
            _log.warning("StimOptimizer: the Left and Right rates differ at %d timestamps; the "
                         "epochs open on the Left rate only", n_differ)
    for c in ("rate_Left", "rate_Right"):
        if c in wide.columns:
            freq = wide[c] if freq is None else freq.fillna(wide[c])
    wide["freq_hz"] = freq
    ren = {"amp_Left": "amp_mA_Left", "amp_Right": "amp_mA_Right",
           "pw_Left": "pw_us_Left", "pw_Right": "pw_us_Right",
           "cathode_Left": "cathode_Left", "cathode_Right": "cathode_Right"}
    wide = wide.rename(columns=ren)
    keys = [k for k in _EPOCH_KEYS if k in wide.columns]
    if not keys:
        return pd.DataFrame()
    sig = wide[keys].astype(object).where(pd.notna(wide[keys]), "NA").astype(str).agg("|".join, axis=1)
    wide["epoch"] = (sig != sig.shift()).cumsum().astype(float)
    ep = (wide.reset_index().groupby("epoch", as_index=False)
          .agg(t_start=("t", "min"), **{k: (k, "first") for k in keys}))
    ep["t_end"] = ep["t_start"].shift(-1)
    ep.loc[ep.index[-1], "t_end"] = wide.index.max()
    ep["dur_h"] = (ep["t_end"] - ep["t_start"]).dt.total_seconds() / 3600.0
    ep["open_ended"] = False
    ep.loc[ep.index[-1], "open_ended"] = True
    ep.attrs["n_timestamps_rates_differ"] = int(n_differ)
    ep.attrs["rates_agree_across_sides"] = bool(n_differ == 0)
    return ep


# --------------------------------------------------------------------------------------------------
# pain reports -> epoch-level design matrix
# --------------------------------------------------------------------------------------------------
def _stim_state(row) -> str:
    """Classify the therapeutic state. A hemisphere at 0 mA is a DIFFERENT state, not a low dose —
    mixing the two inflates any apparent amplitude gradient (documented in OBJECTIVE_SPEC)."""
    l = row.get("amp_mA_Left")
    r = row.get("amp_mA_Right")
    l0 = (l == 0) or pd.isna(l)
    r0 = (r == 0) or pd.isna(r)
    if l0 and r0:
        return "both_off"
    if l0:
        return "left_off_right_on"
    if r0:
        return "right_off_left_on"
    return "bilateral_active"


def _california_day_strings(when):
    """ISO date strings of the California calendar day of each UTC instant (decision 142's rule,
    `Biomarkers.routines.local_time.local_calendar_day`); NaT gives None."""
    try:
        from modules.Biomarkers.routines.local_time import local_calendar_day
    except ImportError:                                        # pragma: no cover - host spelling
        from Biomarkers.routines.local_time import local_calendar_day
    return pd.Series([d.isoformat() if d is not None and not pd.isna(d) else None
                      for d in local_calendar_day(pd.Series(when))], index=getattr(when, "index", None))


def attach_pros(epochs: pd.DataFrame, pro_df: pd.DataFrame, pro_times_utc,
                *, washin_min=1.0, items=PRO_ITEMS) -> pd.DataFrame:
    """Aggregate pain reports onto epochs, excluding reports inside the wash-in window.

    ``washin_min`` is a PROTOCOL parameter, not a modelling one: RCS08 is a rapid responder with a
    demonstrated response under a minute, so the default is 1 minute rather than the 24 h that an
    earlier pass assumed. Each item gets a mean, an SD and a count, because the optimizer weights an
    epoch by its own within-epoch dispersion and replicate count.
    """
    if epochs.empty or pro_df is None or len(pro_df) == 0:
        return pd.DataFrame()
    t = pd.to_datetime(pd.Series(pro_times_utc), utc=True, errors="coerce")
    keep = t.notna().to_numpy()
    p = pro_df.loc[keep].copy()
    p["_t"] = t[keep].to_numpy()
    ep = epochs.sort_values("t_start").reset_index(drop=True)
    idx = np.searchsorted(ep["t_start"].to_numpy(), p["_t"].to_numpy(), side="right") - 1
    p["epoch"] = np.where(idx >= 0, ep["epoch"].to_numpy()[np.clip(idx, 0, None)], np.nan)
    p = p.merge(ep[["epoch", "t_start", "t_end"]], on="epoch", how="left")
    p["h_since_change"] = (p["_t"] - p["t_start"]).dt.total_seconds() / 3600.0
    # The FINAL epoch is open-ended: its `t_end` is merely the last settings observation, not the
    # moment the setting stopped being in force. Testing `_t < t_end` therefore silently DROPS every
    # pain report collected after the last device export — which is the same silent-truncation
    # failure that made the Biomarkers timeline look frozen. A report after the last settings
    # observation belongs to the setting still in force, so the open epoch extends to +inf.
    # Its `dur_h` remains a lower bound; `open_ended` marks it for anything weighting by exposure.
    if "open_ended" in ep.columns:
        p = p.merge(ep[["epoch", "open_ended"]], on="epoch", how="left")
        p["open_ended"] = p["open_ended"].fillna(False).astype(bool)
    else:
        p["open_ended"] = False
    p["in_epoch"] = (p["_t"] < p["t_end"]) | p["open_ended"]
    p["usable"] = p["in_epoch"] & (p["h_since_change"] >= float(washin_min) / 60.0)

    have = [c for c in items if c in p.columns]
    if not have:
        raise KeyError(f"pain-report frame carries none of {list(items)}; "
                       f"has {sorted(p.columns)[:15]}")
    u = p.loc[p["usable"]]
    agg = {}
    for c in have:
        agg[c] = (c, "mean")
        agg[f"{c}_sd"] = (c, "std")
        agg[f"{c}_n"] = (c, "count")
    cell = u.groupby("epoch", as_index=False).agg(n=("_t", "size"), **agg)
    # The distinct California calendar days each epoch's usable ratings were filed on (decision
    # 184): the coverage half of the honest-current check counts occasions, not ratings. The same
    # day rule as the Biomarkers join (decision 142).
    days = u.assign(_day=_california_day_strings(u["_t"])).groupby("epoch")["_day"].agg(
        lambda v: tuple(sorted(set(v.dropna()))))
    cell = cell.merge(days.rename("rating_days").reset_index(), on="epoch", how="left")
    cell["rating_days"] = [tuple(v) if isinstance(v, tuple) else () for v in cell["rating_days"]]
    cell["n_rating_days"] = [len(v) for v in cell["rating_days"]]
    out = ep.merge(cell, on="epoch", how="inner")
    out["t0"] = out["t_start"]
    out["state"] = out.apply(_stim_state, axis=1)
    return out


#: The two things ``evidence_inputs`` can hand back as the sensed half of the join.
#:
#: ``"calibrated"`` is the one to use and is the default. It reads the Biomarkers module's cache of
#: three-second tiles, in which band power has ALREADY been put on the device's own number scale by
#: the lab's own calibration, inside that module. Nothing is rescaled on the way through here.
#:
#: ``"decibel_density"`` is the route this function used until 2026-09-06: the assembled spectra,
#: which store a decibel power density that the closed-loop module then linearised and integrated
#: across the band. That quantity is proportional to the one the device works in but is not on the
#: device's scale, so a number from it cannot be compared against a threshold programmed into the
#: device. It is kept because the before-and-after comparison of the change needs it and because
#: other work may want the spectra themselves.
BAND_POWER_CALIBRATED = "calibrated"
BAND_POWER_DECIBEL_DENSITY = "decibel_density"


def _calibrated_lsb_cache(uid, _bs):
    """The Biomarkers cache of three-second tiles with band power on the device's scale.

    Returns ``{}`` when this participant has no time-domain recordings to tile, which is a normal
    state for someone with stimulation settings but no sensing.

    Also returns ``{}`` when the Biomarkers service in front of us does not offer the cache at all.
    That happens with the small stand-in modules the adapter tests install in place of the real
    service, which hold only the handful of functions those tests need. Reporting "no sensed signal"
    for a service that cannot supply any is the same answer as for a participant who has none, and
    it is the answer those tests already expect. A service that DOES offer the cache and then fails
    is a real failure and is left to raise.

    THE SAME REQUEST EVERY OTHER PAGE MAKES (decision 289). The saved tiles are shared by every
    page. This function used to assemble its own inputs -- the time-domain recordings only, without
    the survey/montage recordings, and the patient-event PSDs assigned to a sensing pair without
    the sensing index (730 of 4,512 kept on RCS08) -- and when the Stim Optimizer was the first page
    to build after an ingest, it wrote that short copy for everyone (2026-09-25 20:03 UTC: 293,108
    tiles where the full set is 303,321). It now asks through the Biomarkers module's one request
    and never assembles the list itself.
    """
    if not hasattr(_bs, "_raw_lsb_cache_canonical"):
        return {}
    return _bs._raw_lsb_cache_canonical(uid)


def _deployable_band_span(_bs):
    """The band centres worth carrying: those the device could actually place a sensing window on.

    The lab's own two constants set this range, and they are read rather than restated. Everything
    outside it is excluded for a device reason and not a statistical one: nothing above 30 Hz can be
    programmed as an adaptive sensing band at all, so a band up there is not deployment evidence
    however it behaves, and the lab marks the device's own readings as calibrated only inside this
    same range. Carrying all 98 stored centres instead of these 22 would quadruple the size of a
    frame that is already large and would add nothing a deployment could use.

    RAISES when the constants cannot be read (review S12, 2026-09-12). Until then a failed import
    returned ``None``, which ``evidence_inputs`` reads as "carry every centre the cache holds":
    under the host runner the single spelling ``modules.Biomarkers`` did not resolve, so the
    frame silently carried 98 centres instead of 22 with no message. Both spellings are tried,
    the way every other cross-module import in this module is; a service that genuinely lacks
    the constants is a broken service, not a wider range.
    """
    try:
        from modules.Biomarkers.routines import analytics as _an
    except ImportError:
        from Biomarkers.routines import analytics as _an
    lo = getattr(_an, "LSB_VALIDATED_HZ_LO", None)
    hi = getattr(_an, "LSB_DEPLOYABLE_HZ_HI", None)
    if lo is None or hi is None:
        raise RuntimeError("the Biomarkers analytics module carries no LSB_VALIDATED_HZ_LO / "
                           "LSB_DEPLOYABLE_HZ_HI, so the deployable band range cannot be read")
    return (float(lo), float(hi))


def deployable_band_span() -> tuple:
    """``(lo_hz, hi_hz)`` of the band centres the device could place a sensing window on, read
    from the Biomarkers module's two constants. Public so the response key can name them
    (review S11): the evidence frame's centres depend on them and nothing else in the key did.
    """
    return _deployable_band_span(None)


def evidence_inputs(participant, *, force_refresh=None, sources=None, stream=None,
                    band_power=BAND_POWER_CALIBRATED):
    """Live platform data -> ``(sensed_frame, epochs)`` ready for ``routines.lfp_evidence``.

    This is the seam that made Stage 2 runnable on real recordings. It reuses the Biomarkers
    module's own sensed signal rather than re-deriving spectra, so the two modules share one
    definition of what the brain was doing at a given moment, and it builds the exposure epochs from
    THIS module's settings reconstruction, so they share one definition of what stimulation was
    being delivered.

    WHAT CHANGED, 2026-09-06. This used to hand back the assembled spectra, which store a decibel
    power density, and the closed-loop module then linearised and integrated that density to get
    band power. Nobody had ever calibrated that recipe, so the numbers were proportional to the
    quantity the device works in but sat about two hundred times below it, while being labelled as
    being in the device's units. The Biomarkers module already computes band power on the device's
    own scale, in three-second tiles across the whole recording history, using the recipe the lab
    validated and the calibration numbers that go with it. This function now reads those tiles. No
    scale factor is applied here or anywhere else in the closed-loop module; the multiplication that
    puts the numbers on the device's scale happens inside the Biomarkers module, where it is
    calibrated and tested. Pass ``band_power=BAND_POWER_DECIBEL_DENSITY`` to get the older frame,
    which is what the before-and-after comparison of this change uses.

    The tiles are expensive to build and are cached by the Biomarkers layer, keyed on which
    recordings exist rather than on time, so a changed record produces a new key by itself.
    ``force_refresh`` is passed through to the assembled-spectra route, which is the only one of the
    two that takes it.

    Returns ``(None, epochs)`` when the participant has no sensed signal, rather than raising — a
    participant with settings but no sensing is a normal state, not an error.

    ``stream`` is an optional settings stream that the caller has already built. Pass the frame that
    ``settings_stream`` returned and this function will use it instead of reading, decrypting and
    parsing the participant's stored Percept files a second time. Leave it as None and the frame is
    built here, which is what every caller written before this argument existed does. The frame this
    function builds for itself is ``settings_stream(participant)`` with no arguments beyond the
    participant and with no filtering applied afterwards, so a caller that hands in exactly that
    gets exactly the same epochs it would have got otherwise.
    """
    try:
        from modules.Biomarkers import bravo_service as _bs  # local: avoids a module-level cycle
    except ImportError:                                       # the host runner's spelling
        from Biomarkers import bravo_service as _bs
    from .routines import lfp_evidence as _ev

    epochs = exposure_epochs(_use_stream_or_build_one(participant, stream))
    uid = getattr(participant, "uid", participant)

    if band_power == BAND_POWER_DECIBEL_DENSITY:
        mat = _bs._cached_psd_matrix(uid, force_refresh=force_refresh)
        if not mat:
            return None, epochs
        return _ev.frame_from_matrix(mat, sources=sources), epochs
    if band_power != BAND_POWER_CALIBRATED:
        raise ValueError(f"band_power must be {BAND_POWER_CALIBRATED!r} or "
                         f"{BAND_POWER_DECIBEL_DENSITY!r}, got {band_power!r}")

    cache = _calibrated_lsb_cache(uid, _bs)
    if not cache:
        return None, epochs
    span = _deployable_band_span(_bs)
    centers = None
    if span is not None:
        lo, hi = span
        stored = np.asarray(next(iter(cache.values()))["centers_hz"], float)
        centers = [float(c) for c in stored if lo - 1e-9 <= c <= hi + 1e-9]
    frame = _ev.frame_from_lsb_cache(cache, centers_hz=centers, sources=sources)
    if frame is None or not len(frame):
        return None, epochs
    return frame, epochs


def evidence_for_participant(participant, *, hemispheres=("Left", "Right"), rates=None,
                             channels=None, force_refresh=None, sources=None, stream=None,
                             inputs=None, **kw):
    """Every usable ``LfpEvidence`` for a participant, plus the audit of what was unusable.

    Returns ``(evidence_dict, audit_frame)`` keyed on ``(channel, hemisphere, rate_hz)``. The audit
    frame is not optional output: a cell that yields no evidence because the data cannot support the
    test must be distinguishable from one that yields a genuine negative, and only the audit says
    which. Callers handing this to the stage gate should report both.

    ``stream`` is an already-built settings stream, forwarded to :func:`evidence_inputs` so a
    caller that has parsed the participant's stored Percept files once does not pay for it again.
    ``None`` means build it here, which is what every caller written before this argument did.

    ``inputs`` is the ``(sensed_frame, epochs)`` pair :func:`evidence_inputs` returns, already
    built by the caller (2026-09-12). One Stim Optimizer request builds the evidence twice -- once
    for the closed-loop readiness screen and once, pinned to the rate Stage 1 froze, inside the
    two-stage path -- and the sensed frame is the same both times: loading the recordings and the
    tile cache cost about 3 s per build on RCS08. Handing the pair in skips that; ``None`` builds
    it here as before. Nothing downstream writes into either frame.
    """
    from .routines import lfp_evidence as _ev
    band_power = kw.pop("band_power", BAND_POWER_CALIBRATED)
    if inputs is not None:
        psd, epochs = inputs
    else:
        psd, epochs = evidence_inputs(participant, force_refresh=force_refresh, sources=sources,
                                      stream=stream, band_power=band_power)
    if psd is None:
        return {}, pd.DataFrame([{"reason_unusable": "no sensed signal for this participant",
                                  "usable": False}])
    return _ev.build_all(psd, epochs, hemispheres=hemispheres, rates=rates, channels=channels, **kw)


def build_design_matrix(participant, request_data=None, *, washin_min=1.0,
                        items=PRO_ITEMS, stream=None) -> pd.DataFrame:
    """End-to-end: platform data -> the epoch matrix ``StimOptimizer.pipeline.run`` consumes.

    Reuses Biomarkers' own pain-report loader and UTC normalization so there is ONE definition of a
    rating timestamp across the two modules.

    ``stream`` is an optional settings stream that the caller has already built. Pass the frame that
    ``settings_stream`` returned and this function will use it instead of reading, decrypting and
    parsing the participant's stored Percept files a second time. Leave it as None and the frame is
    built here, which is what every caller written before this argument existed does. The frame this
    function builds for itself is ``settings_stream(participant)`` with no arguments beyond the
    participant and with no filtering applied afterwards, which is the same frame
    ``evidence_inputs`` builds for itself, so one frame can safely serve both.
    """
    try:
        from modules.Biomarkers import bravo_service as _bs
    except ImportError:                                       # the host runner's spelling
        from Biomarkers import bravo_service as _bs

    stream = _use_stream_or_build_one(participant, stream)
    if stream.empty:
        return pd.DataFrame()
    ep = exposure_epochs(stream)
    if ep.empty:
        return pd.DataFrame()
    pro_df = _bs._load_pros(request_data or {}, participant)
    times = _bs._pro_times_utc_series(pro_df)

    # THE MATCHED TABLE IS STORED ONLY WHEN BOTH OF ITS INPUTS CAN BE NAMED. The settings key comes
    # from the stream's store entry and the report key from the pain-report snapshot; a stream built
    # without the store, or reports handed in through the request body, have no key, and a product
    # whose inputs cannot be cited is computed and handed back but never written. Without the
    # report key in particular there would be nothing to make a newly filed report change the key.
    settings_key = getattr(stream, "attrs", {}).get(STORE_KEY_ATTR)
    report_key = getattr(pro_df, "attrs", {}).get(STORE_KEY_ATTR) if pro_df is not None else None
    if not settings_key or not report_key:
        return attach_pros(ep, pro_df, times, washin_min=washin_min, items=items)

    uid = _participant_uid(participant)
    sig = (THERAPY_PAIN_MATCHED_KIND, _THERAPY_PAIN_MATCHED_RULE_VERSION, uid,
           settings_key, report_key, float(washin_min), tuple(items))
    not_stored = []

    def build():
        out = attach_pros(ep, pro_df, times, washin_min=washin_min, items=items)
        if len(out) == 0:
            not_stored.append(out)
            return None
        return out

    got, _wrote = _cache_store.store_if_absent(
        THERAPY_PAIN_MATCHED_KIND, uid, sig, build,
        consumer="stim_optimizer",
        writer="stim_optimizer", trigger="design_matrix",
        provenance=_provenance.flatten([
            _provenance.entry(settings_key, kind=THERAPY_SETTINGS_KIND, writer="stim_optimizer"),
            _provenance.entry(report_key, kind="redcap_reports", writer="biomarkers"),
        ]),
        extra={"washin_min": float(washin_min), "items": list(items)},
        root=_SHARED_CACHE_DIR_OVERRIDE)
    if got is None:
        return not_stored[0] if not_stored else pd.DataFrame()
    got.attrs[STORE_KEY_ATTR] = _cache_store.product_key(THERAPY_PAIN_MATCHED_KIND, uid, sig)
    return got
