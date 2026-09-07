"""Service layer: the single entry point the BRAVO API calls for StimOptimizer.

Mirrors the shape of ``modules/Biomarkers/bravo_service.run_for_participant`` — takes the request
dict, pulls what it needs from the platform database, runs the module, and returns a JSON-able dict.
No Django imports at module scope beyond the models the adapter needs, no template rendering, and no
kaleido: figures are returned as Plotly figure JSON for the browser to draw, never rendered to PNG
server-side.

HONESTY CONTRACT
----------------
This module's whole point is that it must be able to say "the data do not support a
recommendation". ``run_for_participant`` therefore always returns:

* ``recommendation_supported`` — False unless at least one arm resolves its optimum against its own
  posterior uncertainty. As of 2026-08-30 no RCS08 arm does.
* ``arms[].optimum_resolved`` — per-arm version of the same test.
* ``blockers`` — the reasons a recommendation is withheld, in plain language, so the UI shows them
  next to the figures instead of the reader having to infer it from a chart.

A caller that ignores those fields and reads ``opt_freq_hz``/``opt_amp_mA`` as a recommendation is
misusing the module.
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

from . import adapter
from . import pipeline
from .routines import plots as PLT

# THE IMPORT ROOT DIFFERS BETWEEN THE TWO TEST RUNNERS, so both spellings are tried (see adapter).
try:
    from modules.CacheStore import provenance as _provenance
    from modules.CacheStore import store as _cache_store
except ImportError:                                   # pragma: no cover - depends on the runner
    from CacheStore import provenance as _provenance
    from CacheStore import store as _cache_store

_log = logging.getLogger(__name__)

DEFAULT_SITES = ("left_leg", "back")
DEFAULT_HEMISPHERES = ("Left", "Right")

#: ==========================================================================================
#: TRACK A STEP 8 — "Have Stim Optimizer read the store and write its outputs back".
#:
#: READS. The matched table comes through `adapter.build_design_matrix`, which asks the store as
#: `stim_optimizer` (step 5). The amplitude effect on every band is read here as the NEWEST entry
#: the closed-loop module wrote (step 7), again as `stim_optimizer`: that is the edge the
#: provenance refusal exists for, and it is exercised on every request. The response says which
#: tile entry that table describes and whether it is the current one, so a reader is never handed
#: a verdict about an older recording set without being told.
#:
#: WRITES. Four products with the chain of everything they derived from: the summary per arm (an
#: arm is one pain site on one brain side, fitted on its own), the
#: exploration ladder (the queue), the batch, and the manifest with the blockers. And the response
#: itself, served back when nothing feeding it has changed. A stored response whose chain contains
#: this module's own ladder is REFUSED by the store; the refusal is reported in the response and
#: the request computes fresh, because a page must not go blank over a loop in its inputs and a
#: silent recompute would hide the loop.
#:
#: WHAT THE AMPLITUDE TABLE DOES NOT YET DO. It is read and reported. Feeding it into the
#: exploration queue's arithmetic is a modelling decision (open item 3 in the decision log) and
#: is not made here.
#: ==========================================================================================
RESPONSE_KIND = "stim_optimizer_response"
SUMMARY_KIND = "stim_optimizer_summary"
LADDER_KIND = "exploration_ladder"
BATCH_KIND = "exploration_batch"
MANIFEST_KIND = "stim_optimizer_manifest"
AMPLITUDE_KIND = "amplitude_effect_by_band"
GROUND_TRUTH_KIND = "ground_truth_verdict"
_RULE_VERSION = "v1_four_outputs"

#: Response fields that describe the run that produced the response, not its results.
#: Tests point this at a directory of their own; passed through to the one store.
_SHARED_CACHE_DIR_OVERRIDE = None


def _tiles_key_for(participant):
    """`(key, reason)`: the store key of the current tile entry, or None and why there is none."""
    try:
        try:
            from modules.Biomarkers import bravo_service as _bsvc
        except ImportError:
            from Biomarkers import bravo_service as _bsvc
        uid = getattr(participant, "uid", participant)
        sig = _bsvc._raw_lsb_shared_signature(uid, _bsvc._LSB_SPECTRUM_CENTERS)
        if sig is None:
            return None, "the participant has no tile entry to key on (no recordings on the server)"
        return _cache_store.product_key(_bsvc._RAW_LSB_SHARED_KIND, uid, sig), None
    except Exception as exc:                          # noqa: BLE001 — no server, no tile key
        return None, f"the tile key could not be built: {exc!r}"


def _code_digest():
    """A digest of this module and its routines, so a change to the arithmetic changes the key.

    The fitted surface depends on constants spread through `pipeline.py` and `routines/`; naming
    each one in the key by hand is how a stale response gets served after someone edits a bound.
    A deployment therefore invalidates every stored response, which decision 26 accepted for the
    tile store for the same reason.
    """
    import glob
    import hashlib
    here = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(here, "*.py"))
                   + glob.glob(os.path.join(here, "routines", "*.py")))
    h = hashlib.blake2b(digest_size=8)
    for f in files:
        h.update(os.path.relpath(f, here).encode())
        with open(f, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


_CODE_DIGEST = _code_digest()


def summarise_amplitude_effect(table, *, lo_hz, hi_hz):
    """Per contact, side, rate and band inside the adaptive window: how many runs, how many
    currents at most and over what range, whether any run showed a straight-line movement at
    p < 0.05, whether curvature could be assessed. Counts, not adjectives.

    `any_detectable_movement` has three values: True, movement was detected in at least one run;
    False, a line was fitted in at least one run and none reached p < 0.05 across the currents
    tested; None, no line could be fitted at all. A False is listed with the number and range of
    currents and the smallest standard error of the slope, because "no movement was detectable"
    is a statement about what those currents could show and not about the band.
    """
    empty = {"rows": [], "n_rows_read": 0, "n_rows_in_window": 0, "n_rows_not_grouped": 0,
             "combinations_with_no_detectable_movement": [], "combinations_not_assessed": []}
    if table is None or len(table) == 0:
        return empty
    t = table[(table["band_center_hz"] >= float(lo_hz)) & (table["band_center_hz"] <= float(hi_hz))]
    keys = ["sensing_contact", "ramped_side", "stimulation_rate_hz", "band_center_hz"]
    rows, no_movement, not_assessed = [], [], []
    grouped = 0
    for k, g in t.groupby(keys, sort=True):
        grouped += len(g)
        p = pd.to_numeric(g["slope_p"], errors="coerce")
        se = pd.to_numeric(g.get("slope_stderr"), errors="coerce") if "slope_stderr" in g else None
        fitted = int(p.notna().sum())
        detectable = True if bool((p < 0.05).any()) else (False if fitted else None)
        curv = bool(pd.to_numeric(g["p_curvature"], errors="coerce").notna().any())
        row = {"sensing_contact": k[0], "ramped_side": k[1],
               "stimulation_rate_hz": _jsonable(k[2]), "band_center_hz": float(k[3]),
               "n_runs": int(len(g)), "n_runs_with_a_fitted_line": fitted,
               "max_currents_tested": int(pd.to_numeric(g["n_currents_tested"]).max()),
               "current_min_mA": _jsonable(pd.to_numeric(g["current_min_mA"]).min()),
               "current_max_mA": _jsonable(pd.to_numeric(g["current_max_mA"]).max()),
               "best_slope_p": _jsonable(p.min()),
               "min_slope_stderr": _jsonable(se.min()) if se is not None else None,
               "any_detectable_movement": detectable,
               "any_curvature_assessed": curv,
               "fold_range": [_jsonable(pd.to_numeric(g["fold_max_over_min"]).min()),
                              _jsonable(pd.to_numeric(g["fold_max_over_min"]).max())],
               "visits": sorted(set(map(str, g["visit_date"])))}
        rows.append(row)
        flagged = {k2: row[k2] for k2 in ("sensing_contact", "ramped_side", "stimulation_rate_hz",
                                          "band_center_hz", "n_runs", "max_currents_tested",
                                          "current_min_mA", "current_max_mA", "min_slope_stderr")}
        if detectable is False and not curv:
            no_movement.append(flagged)
        elif detectable is None:
            not_assessed.append(flagged)
    return {"rows": rows, "n_rows_read": int(len(table)), "n_rows_in_window": int(len(t)),
            # rows the grouping dropped because one of its four keys was missing
            "n_rows_not_grouped": int(len(t) - grouped),
            "combinations_with_no_detectable_movement": no_movement,
            "combinations_not_assessed": not_assessed}


def amplitude_effect_block(participant, *, tiles_key_now):
    """Read the newest amplitude-effect table as Stim Optimizer and report it."""
    from .routines import percept_adaptive as _pa
    uid = str(getattr(participant, "uid", participant))
    block = {"available": False, "read_as": "stim_optimizer", "store_key": None}
    try:
        table, stamp = _cache_store.load_newest(AMPLITUDE_KIND, uid, consumer="stim_optimizer",
                                                root=_SHARED_CACHE_DIR_OVERRIDE)
    except _provenance.SelfDerivedProduct as exc:
        block["reason"] = f"refused by the store: {exc}"
        block["refused"] = True
        return block
    except Exception as exc:                          # noqa: BLE001
        block["reason"] = f"could not be read: {exc!r}"
        return block
    if table is None:
        if stamp:
            block["reason"] = (f"the newest amplitude-effect entry (written "
                               f"{stamp.get('written_utc')}) could not be read and was discarded; "
                               f"the closed-loop deployment page writes it again")
        else:
            block["reason"] = ("no amplitude-effect table has been written for this "
                               "participant; the closed-loop deployment page writes it")
        return block
    chain = stamp.get("provenance") or []
    tiles_in_chain = [c.get("key") for c in chain if c.get("kind") == "raw_lsb_tiles"]
    lo, hi = _pa.ADAPTIVE_LFP_BAND_HZ
    block.update({
        "available": True,
        "store_key": f"{AMPLITUDE_KIND}/{uid}/{stamp.get('signature_key')}",
        "written_utc": stamp.get("written_utc"), "writer": stamp.get("writer"),
        "provenance": chain,
        "describes_current_recordings": (bool(tiles_key_now in tiles_in_chain)
                                         if tiles_key_now and tiles_in_chain else None),
        "adaptive_window_hz": [float(lo), float(hi)],
        "summary": None,
    })
    try:
        block["summary"] = summarise_amplitude_effect(table, lo_hz=lo, hi_hz=hi)
    except Exception as exc:                          # noqa: BLE001
        # The table is the closed-loop module's; a column it renamed must not take this request
        # down, and must not be hidden either.
        block["summary_error"] = f"the table could not be summarised: {exc!r}"
    return block


def ground_truth_block(participant, *, tiles_key_now):
    """Read the newest ground-truth verdict (Track G step 2) as Stim Optimizer and report it.

    This is the edge the provenance refusal was built for: the verdict is computed from
    recordings whose settings Stim Optimizer's own ladder chose, so the store refuses a table
    whose chain contains this module's output, and the refusal is reported rather than hidden.
    The table is read and counted here; feeding it into the exploration arithmetic is a
    modelling decision that is not made in this step.
    """
    uid = str(getattr(participant, "uid", participant))
    block = {"available": False, "read_as": "stim_optimizer", "store_key": None}
    try:
        table, stamp = _cache_store.load_newest(GROUND_TRUTH_KIND, uid, consumer="stim_optimizer",
                                                root=_SHARED_CACHE_DIR_OVERRIDE)
    except _provenance.SelfDerivedProduct as exc:
        block["reason"] = f"refused by the store: {exc}"
        block["refused"] = True
        return block
    except Exception as exc:                          # noqa: BLE001
        block["reason"] = f"could not be read: {exc!r}"
        return block
    if table is None:
        block["reason"] = ("no ground-truth verdict has been written for this participant; the "
                           "closed-loop deployment page writes it" if not stamp else
                           "the newest ground-truth entry could not be read and was discarded")
        return block
    chain = stamp.get("provenance") or []
    tiles_in_chain = [c.get("key") for c in chain if c.get("kind") == "raw_lsb_tiles"]
    try:
        routes = {str(k): int(v) for k, v in table["ground_truth_route"].value_counts().items()}
        with_both = table.dropna(subset=["fold_device_over_voltage_trace"])
        fold = with_both["fold_device_over_voltage_trace"].astype(float)
        summary = {"n_rows": int(len(table)), "n_runs": int(table["run_label"].nunique()),
                   "rows_by_route": routes,
                   "device_spikes_excluded": int(table["device_spikes_excluded"].sum()),
                   "rows_with_both_device_and_voltage_trace": int(len(with_both)),
                   "fold_device_over_voltage_trace_min": _jsonable(fold.min()) if len(fold) else None,
                   "fold_device_over_voltage_trace_max": _jsonable(fold.max()) if len(fold) else None}
    except Exception as exc:                          # noqa: BLE001
        summary = None
        block["summary_error"] = f"the table could not be summarised: {exc!r}"
    block.update({
        "available": True,
        "store_key": f"{GROUND_TRUTH_KIND}/{uid}/{stamp.get('signature_key')}",
        "written_utc": stamp.get("written_utc"), "writer": stamp.get("writer"),
        "provenance": chain,
        "describes_current_recordings": (bool(tiles_key_now in tiles_in_chain)
                                         if tiles_key_now and tiles_in_chain else None),
        "summary": summary,
    })
    return block


def _response_signature(uid, matched_key, tiles_key, amp_key, gt_key, request_data, sites, hemis,
                        washin_min, backend):
    """The response key: every input and every setting the fitted result depends on, and the
    figure backend last, so `_products_signature` can drop it."""
    rd = request_data or {}
    return (RESPONSE_KIND, _RULE_VERSION, _CODE_DIGEST, str(uid), matched_key, tiles_key, amp_key,
            gt_key, tuple(sites), tuple(hemis), float(washin_min),
            int(rd.get("NBatches", 3)), int(rd.get("Q", 4)), bool(rd.get("ClosedLoop", True)),
            str(backend))


def _products_signature(sig):
    """The key of the four tables: the response key without the figure backend.

    The backend changes only whether figure JSON is in the response. Keyed on it, a request
    with figures and one without would sweep each other's tables on every write, since the store
    keeps one entry per kind and participant.
    """
    return tuple(sig[:-1])


def _write_outputs(uid, sig, prov, rep, out):
    """The four products and the response, through the store. Records what is present after."""
    common = dict(writer="stim_optimizer", trigger="stim_optimizer_request", provenance=prov,
                  root=_SHARED_CACHE_DIR_OVERRIDE)
    # A stored entry the store REFUSED is still on disk under this key. Writing "if absent" would
    # find it, write nothing, and leave every later request to be refused and recomputed again;
    # so after a refusal the fresh, clean products replace it.
    replace = bool(out["store"].get("refusal"))
    out["store"]["replaced_refused_entry"] = replace
    table_sig = _products_signature(sig)
    ladder, batch = [], []
    for label, arm in (getattr(rep, "arms", None) or {}).items():
        for name, frame, target in (("queue", getattr(arm, "queue", None), ladder),
                                    ("batch", getattr(arm, "batch", None), batch)):
            if frame is None or len(frame) == 0:
                continue
            f = frame.reset_index(drop=True).copy()
            # The pipeline's queue already carries its own `rank` (1 is the best cell); keep it
            # rather than write a second one. On the live record the first version of this
            # inserted `rank` unconditionally, pandas refused the duplicate, and nothing was
            # written back at all.
            if "rank" not in f.columns:
                f.insert(0, "rank", range(1, len(f) + 1))
            for name, value in (("hemisphere", str(getattr(arm, "hemisphere", ""))),
                                ("site", str(getattr(arm, "site", ""))),
                                ("arm", str(label))):
                if name not in f.columns:
                    f.insert(0, name, value)
            target.append(f)
    products = [
        (SUMMARY_KIND, (getattr(rep, "summary", None)
                        if getattr(rep, "summary", None) is not None and len(rep.summary)
                        else None), None),
        (LADDER_KIND, (pd.concat(ladder, ignore_index=True) if ladder else None), None),
        (BATCH_KIND, (pd.concat(batch, ignore_index=True) if batch else None), None),
        (MANIFEST_KIND, {"manifest": out.get("manifest"), "blockers": out.get("blockers"),
                         "recommendation_supported": out.get("recommendation_supported"),
                         "design_matrix": out.get("design_matrix")}, "pickle"),
    ]

    def put(kind, key, payload, fmt):
        if replace:
            _cache_store.store(kind, uid, key, payload, fmt=fmt, **common)
        else:
            _cache_store.store_if_absent(kind, uid, key, lambda p=payload: p, fmt=fmt, **common)
        return _cache_store.read_stamp(kind, uid, key, root=_SHARED_CACHE_DIR_OVERRIDE) is not None

    written = {}
    for kind, payload, fmt in products:
        if payload is None:
            written[kind] = None
            continue
        try:
            written[kind] = put(kind, table_sig, payload, fmt)
        except Exception as exc:                      # noqa: BLE001
            _log.warning("StimOptimizer: %s was not written back (%r)", kind, exc)
            written[kind] = False
    # `written` means present in the store under this request's key once the request is over.
    # The response's own flag is set before the response is stored, because the stored copy
    # cannot record the outcome of its own write; it is corrected in memory if the write fails.
    written[RESPONSE_KIND] = True
    out["store"]["written"] = dict(written)
    try:
        if not put(RESPONSE_KIND, sig, out, "pickle"):
            out["store"]["written"][RESPONSE_KIND] = False
    except Exception as exc:                          # noqa: BLE001
        _log.warning("StimOptimizer: the response was not written back (%r)", exc)
        out["store"]["written"][RESPONSE_KIND] = False


def _jsonable(v):
    """numpy/pandas -> plain Python, so DRF's stdlib encoder can serialize without default=str."""
    if v is None:
        return None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if not np.isfinite(f) else f
    if isinstance(v, float):
        return None if not np.isfinite(v) else v
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray, pd.Series)):
        return [_jsonable(x) for x in list(v)]
    return v


def _frame_records(df, cols=None, limit=None):
    if df is None or len(df) == 0:
        return []
    d = df if cols is None else df[[c for c in cols if c in df.columns]]
    if limit:
        d = d.head(int(limit))
    return [_jsonable(r) for r in d.to_dict("records")]


def design_matrix_summary(es: pd.DataFrame) -> dict:
    """What the warm start actually contains — shown above the figures so the reader sees the
    evidence base before any surface. Counts, not adjectives."""
    if es is None or len(es) == 0:
        return {"available": False, "reason": "no exposure epochs with pain reports"}
    out = {
        "available": True,
        "n_epochs": int(len(es)),
        "n_reports": int(pd.to_numeric(es.get("n"), errors="coerce").fillna(0).sum()),
        "t_first": _jsonable(pd.to_datetime(es["t0"]).min()) if "t0" in es.columns else None,
        "t_last": _jsonable(pd.to_datetime(es["t0"]).max()) if "t0" in es.columns else None,
        "states": {str(k): int(v) for k, v in es["state"].value_counts().items()}
                  if "state" in es.columns else {},
    }
    for c in ("amp_mA_Left", "amp_mA_Right", "freq_hz", "pw_us_Left"):
        if c in es.columns:
            s = pd.to_numeric(es[c], errors="coerce").dropna()
            if len(s):
                out[f"{c}_range"] = [_jsonable(s.min()), _jsonable(s.max())]
                out[f"{c}_levels"] = int(s.nunique())
    for site in ("left_leg_vas", "back_vas"):
        if site in es.columns:
            out[f"{site}_epochs"] = int(pd.to_numeric(es[site], errors="coerce").notna().sum())
    return out


def run_for_participant(request_data: dict) -> dict:
    """Build the design matrix from platform data, fit every arm, return a JSON-able payload.

    Request keys (all optional except ParticipantId):
      ParticipantId  participant uid
      Sites          list of pain-site metric names (default left_leg + back)
      Hemispheres    list of "Left"/"Right" (default both)
      WashinMin      wash-in exclusion in MINUTES (default 1.0 — PI-declared for a rapid responder)
      Backend        "plotly" (default, returns figure JSON) or "none" (tables only, fast)
      NBatches, Q    forward-simulation depth for the trajectory panel
    """
    from Server import models

    uid = (request_data or {}).get("ParticipantId")
    if not uid:
        return {"available": False, "reason": "ParticipantId is required"}
    participant = models.Participant.find(uid=uid)
    if participant is None:
        return {"available": False, "reason": f"participant {uid} not found"}

    washin_min = float((request_data or {}).get("WashinMin", 1.0))
    sites = tuple((request_data or {}).get("Sites") or DEFAULT_SITES)
    hemis = tuple((request_data or {}).get("Hemispheres") or DEFAULT_HEMISPHERES)
    backend = str((request_data or {}).get("Backend", "plotly")).lower()

    # READ, DECRYPT AND PARSE THE STORED PERCEPT FILES ONCE PER REQUEST, NOT TWICE.
    #
    # This endpoint needed the same dated settings stream in two places and built it separately in
    # each: once inside `build_design_matrix` below, and once as the delivered-settings census
    # further down. One pass opens 568 stored files for RCS08, so doing it twice was 1,136 file
    # reads where 568 would do, for no new information. `ClosedLoopDeployment.adapter`
    # already builds it once and passes it to both of its consumers; this is the same fix on the
    # other endpoint, using the `stream` argument both functions have carried all along -- their
    # docstrings say what it is for and nothing was passing it.
    #
    # THE DEGRADATION BEHAVIOUR OF BOTH CONSUMERS IS PRESERVED EXACTLY. `stream=None` means "build
    # your own", which is what every caller written before that argument existed does, so if this
    # build fails, `build_design_matrix` behaves precisely as it did before and the census is
    # omitted rather than the request failing -- which is what the census's own try/except did.
    try:
        _stream = adapter.settings_stream(participant)
    except Exception:                                     # noqa: BLE001 — falls back to per-consumer builds
        _log.exception("StimOptimizer: settings stream unavailable; each consumer will build its own")
        _stream = None

    try:
        es = adapter.build_design_matrix(participant, request_data, washin_min=washin_min,
                                         stream=_stream)
    except Exception as e:
        _log.exception("StimOptimizer: design matrix build failed for %s", uid)
        return {"available": False, "reason": f"could not build the design matrix: {e}"}
    if es is None or len(es) == 0:
        return {"available": False,
                "reason": "no exposure epochs carry usable pain reports for this participant",
                "washin_min": washin_min}

    # TRACK A STEP 8: READ THE STORE AS STIM OPTIMIZER, AND SERVE THE RESPONSE WHEN NOTHING CHANGED.
    matched_key = getattr(es, "attrs", {}).get(_cache_store.STORE_KEY_ATTR)
    tiles_key, tiles_reason = _tiles_key_for(participant)
    stream_key = (getattr(_stream, "attrs", {}).get(_cache_store.STORE_KEY_ATTR)
                  if _stream is not None else None)
    amp_block = amplitude_effect_block(participant, tiles_key_now=tiles_key)
    gt_block = ground_truth_block(participant, tiles_key_now=tiles_key)
    store_block = {"response_key": None, "served_from_store": False, "written": None,
                   "refusal": None, "reason": None,
                   "inputs": {"matched_table": matched_key, "tiles": tiles_key,
                              "amplitude_effect": amp_block.get("store_key"),
                              "ground_truth_verdict": gt_block.get("store_key")}}
    sig = prov = None
    matched_stamp = _cache_store.stamp_for_key(matched_key, root=_SHARED_CACHE_DIR_OVERRIDE) \
        if matched_key else None
    if not matched_key:
        store_block["reason"] = "the matched table carries no store key, so nothing is stored"
    elif matched_stamp is None:
        store_block["reason"] = ("the matched table's own entry could not be found in the store, "
                                 "so its chain cannot be cited and nothing is stored")
    elif not tiles_key:
        store_block["reason"] = f"no tile key, so nothing is stored: {tiles_reason}"
    elif stream_key is None:
        # The queue's eligibility columns come from the settings census, which is this stream.
        # A response computed without it is a degraded one and must not be served to a request
        # that would have had the census.
        store_block["reason"] = ("the settings stream was unavailable, so this response was "
                                 "computed without the delivered-settings census and is not stored")
    else:
        sig = _response_signature(uid, matched_key, tiles_key, amp_block.get("store_key"),
                                  gt_block.get("store_key"), request_data, sites, hemis,
                                  washin_min, backend)
        store_block["response_key"] = _cache_store.product_key(RESPONSE_KIND, uid, sig)
        try:
            served = _cache_store.load(RESPONSE_KIND, uid, sig, consumer="stim_optimizer",
                                       root=_SHARED_CACHE_DIR_OVERRIDE)
        except _provenance.SelfDerivedProduct as exc:
            served = None
            store_block["refusal"] = str(exc)
            _log.warning("StimOptimizer: the stored response was refused (%s); computing", exc)
        except Exception as exc:                      # noqa: BLE001
            served = None
            _log.info("StimOptimizer: the stored response could not be read (%r)", exc)
        if isinstance(served, dict):
            served = dict(served)
            # The store block describes THIS request, not the one that wrote the entry: a
            # refusal, a write error or a reason recorded then would otherwise come back with
            # every served copy as if it had happened again.
            stored = dict(served.get("store") or {})
            written = dict(stored.get("written") or {})
            written[RESPONSE_KIND] = True         # it was just read back, so it is present
            served["store"] = dict(store_block, served_from_store=True,
                                   response_key=store_block["response_key"], written=written,
                                   refusal=None, reason=None, replaced_refused_entry=False,
                                   stored_utc=(_cache_store.read_stamp(
                                       RESPONSE_KIND, uid, sig,
                                       root=_SHARED_CACHE_DIR_OVERRIDE) or {}).get("written_utc"))
            served["amplitude_effect"] = amp_block
            served["ground_truth"] = gt_block
            return served
        # The chain of exactly the entries this request used: the matched table's own sidecar,
        # found by the key the design matrix carries, and the amplitude table's sidecar as read
        # above. Not "the newest of each kind", which is the same entry only until the next write.
        entries = [_provenance.entry(matched_key, kind="therapy_pain_matched",
                                     writer="stim_optimizer",
                                     chain=matched_stamp.get("provenance") or []),
                   _provenance.entry(tiles_key, kind="raw_lsb_tiles", writer="biomarkers")]
        if amp_block.get("available"):
            entries.append(_provenance.entry(amp_block["store_key"], kind=AMPLITUDE_KIND,
                                             writer="closed_loop",
                                             chain=amp_block.get("provenance") or []))
        if gt_block.get("available"):
            entries.append(_provenance.entry(gt_block["store_key"], kind=GROUND_TRUTH_KIND,
                                             writer="closed_loop",
                                             chain=gt_block.get("provenance") or []))
        prov = _provenance.flatten(entries)

    # The horizon must describe the DATA SPAN, not the last epoch's start. `t0` is when the final
    # setting began, which understates the span by however long that setting has been in force —
    # here it read 2026-08-12 while settings ran to 08-28 and reports to 08-29. Use the latest
    # evidence actually incorporated: the end of the last epoch, and the last report attached.
    horizon = "settings and pain reports as ingested at request time"
    if "t0" in es.columns:
        ends = [pd.to_datetime(es["t0"]).max()]
        if "t_end" in es.columns:
            ends.append(pd.to_datetime(es["t_end"]).max())
        last = max(e for e in ends if pd.notna(e))
        horizon = (f"epochs {pd.to_datetime(es['t0']).min():%Y-%m-%d} to "
                   f"{last:%Y-%m-%d} ({int(len(es))} epochs, "
                   f"{int(pd.to_numeric(es.get('n'), errors='coerce').fillna(0).sum())} reports)")

    try:
        # The settings census is what lets the exploration queue report ELIGIBILITY rather than
        # just promise. Without it the queue panel cannot distinguish a cell the patient has already
        # received from one that has never been delivered, which is precisely the contradiction
        # between this queue and the in-clinic schedule that the panel now explains. Failure to
        # build it must not take down the optimizer, so it degrades to no annotation.
        # The census IS the stream built at the top of this function -- the same frame, built with
        # `settings_stream(participant)` and no filtering, which is exactly what this line used to
        # build for itself. Reusing it is what removes the second pass over the stored files. When
        # the build at the top failed, this is None and the queue omits its eligibility annotation,
        # which is the same degradation this line's own try/except gave.
        _census = _stream
        rep = pipeline.run(es, sites=sites, hemispheres=hemis, delivered_census=_census,
                           outdir=None, render_figures=False,
                           data_horizon=horizon, washin_min=washin_min,
                           n_batches=int((request_data or {}).get("NBatches", 3)),
                           q=int((request_data or {}).get("Q", 4)))
    except Exception as e:
        _log.exception("StimOptimizer: pipeline failed for %s", uid)
        return {"available": False, "reason": f"pipeline failed: {e}",
                "design_matrix": design_matrix_summary(es)}

    arms = {}
    for label, arm in (rep.arms or {}).items():
        ctx = arm.ctx
        m = dict(ctx.meta)
        entry = {
            "site": arm.site, "hemisphere": arm.hemisphere,
            "n_epochs_fitted": _jsonable(m.get("n_epochs_fitted") or m.get("n_epochs")),
            "incumbent_epoch": _jsonable(m.get("incumbent_epoch")),
            "incumbent_xy": _jsonable(m.get("incumbent_xy")),
            "incumbent_mu": _jsonable(m.get("incumbent_mu")),
            # the incumbent's OWN uncertainty — the resolution gate compares the DIFFERENCE, so the
            # UI must be able to show both sides of it rather than a band on the candidate alone
            "incumbent_sd": _jsonable(m.get("incumbent_sd")),
            "optimum": {"freq_hz": _jsonable(m.get("x_star", [None, None])[0]),
                        "amp_mA": _jsonable(m.get("x_star", [None, None])[1]),
                        "posterior_mean": _jsonable(m.get("mu_star")),
                        "posterior_sd": _jsonable(m.get("sd_star"))},
            # `_jsonable`, NOT `bool(...)`. The bool() cast collapsed a three-valued answer to
            # two: an arm whose predicted advantage was measured and found too small to call, and
            # an arm whose difference could not be formed at all, both arrived as False. The
            # interface was recomputing the difference itself to recover the third state.
            "optimum_resolved": _jsonable(arm.surface_can_resolve_its_optimum())
                                if hasattr(arm, "surface_can_resolve_its_optimum") else None,
            # THE COMPARISON THE VERDICT IS ABOUT, serialised rather than left to the interface.
            # The panel was duplicating sqrt(sd_star^2 + sd_incumbent^2) and hardcoding the
            # resolution multiple, so a change to either would leave the displayed numbers
            # silently disagreeing with the verdict printed beside them.
            "comparison": _arm_comparison(arm),
            "kernel": _jsonable(m.get("kernel")),
            # Use the canonical boolean. `safe_contiguous_ceiling` is a float (NaN when there is no
            # ceiling), never None, so testing it against None was constant True and silently
            # disabled the non-contiguous-safe-set blocker for every arm.
            "safe_contiguous": _jsonable(m.get("safe_is_contiguous")),
            "safe_contiguous_ceiling": _jsonable(m.get("safe_contiguous_ceiling")),
            "queue": _frame_records(arm.queue, limit=25),
            "batch": _frame_records(arm.batch),
            "provenance": {"data_horizon": _jsonable(m.get("data_horizon")),
                           "washin_min": _jsonable(m.get("washin_min")),
                           "amp_col": _jsonable(m.get("amp_col"))},
        }
        if backend == "plotly":
            try:
                _fig = _plotly_figures(ctx)
                entry["figures"] = _fig["figures"]
                # Per-figure failures, keyed by the same name the page uses to look the figure up,
                # so a panel can render the reason in place of the figure it expected. Distinct
                # from `figures_error`, which means the whole attempt failed and there is nothing
                # at all to draw — most often because plotly is missing from the image.
                entry["figure_errors"] = _fig["figure_errors"]
            except Exception as e:
                entry["figures"] = {}
                entry["figure_errors"] = {}
                entry["figures_error"] = str(e)
        arms[label] = entry

    supported = bool(rep.recommendation_is_supported()) if hasattr(rep, "recommendation_is_supported") else False
    # Amplitude actually DELIVERED per hemisphere, so a blocker can tell a prediction inside the
    # model's support from one beyond it.
    observed_amp_range = {}
    for hemi in ("Left", "Right"):
        col = f"amp_mA_{hemi}"
        if col in es.columns:
            s = pd.to_numeric(es[col], errors="coerce").dropna()
            if len(s):
                observed_amp_range[hemi] = (float(s.min()), float(s.max()))
    blockers = _blockers(rep, arms, observed_amp_range)
    out = {
        "available": True,
        "participant": uid,
        "design_matrix": design_matrix_summary(es),
        "manifest": _jsonable(rep.manifest),
        "summary": _frame_records(rep.summary),
        "arms": arms,
        "recommendation_supported": supported,
        "blockers": blockers,
        "washin_min": washin_min,
        "closed_loop": closed_loop_readiness(participant, es,
                                             include=bool((request_data or {})
                                                          .get("ClosedLoop", True))),
        "amplitude_effect": amp_block,
        "ground_truth": gt_block,
        "store": store_block,
    }
    if sig is not None:
        try:
            _write_outputs(str(uid), sig, prov, rep, out)
        except Exception as exc:                      # noqa: BLE001
            # Say so in the response rather than only in the log: a request that silently
            # stores nothing looks, from the page, exactly like one that stored everything.
            _log.warning("StimOptimizer: the outputs were not written back (%r)", exc)
            store_block["write_error"] = repr(exc)
    return out


def closed_loop_readiness(participant, es, *, include=True) -> dict:
    """Whether the sensed LFP could drive Adaptive Therapy for this participant, and if not why.

    This is a DIFFERENT question from the open-loop optimizer above it, and the payload keeps them
    apart deliberately. The optimizer asks which stimulation setting relieves pain best; this asks
    whether any sensed band moves with stimulation amplitude, which is the only lever Adaptive
    Therapy has. A band can predict pain beautifully and still be useless as a control signal.

    The screen is returned in full, not just the verdict. A refusal caused by absent data and one
    caused by a real negative response are clinically different conclusions, and only the per-cell
    blocking reasons distinguish them — so a UI can say WHICH it is rather than showing an
    unexplained "not ready".

    Never raises into the response: this is an adjunct panel, and a failure here must not take down
    the open-loop optimizer, which is the primary content. Failure is reported as a reason string.
    """
    if not include:
        return {"available": False, "reason": "not requested (ClosedLoop=false)"}
    try:
        import numpy as _np
        from . import pipeline as _pl
        from .routines import objective as _obj, percept_adaptive as _pa

        lo, hi = _pa.ADAPTIVE_LFP_BAND_HZ
        bands = [(float(c), 5.0) for c in _np.arange(lo + 2.5, hi - 2.5 + 0.01, 1.0)]
        le = _pl.live_evidence(participant, amp_ceiling=_obj.AMP_HARD_LIMIT_MA, bands=bands)
        screen = le.screen if le.screen is not None else pd.DataFrame()
        n_deployable = 0 if screen.empty else int(screen["deployable"].sum())
        return {
            "available": True,
            "ready": bool(le.selected is not None),
            "verdict": le.describe(),
            "selected": ({"channel": le.selected_key[0], "hemisphere": le.selected_key[1],
                          "rate_hz": float(le.selected_key[2])} if le.selected_key else None),
            "n_cells_screened": int(len(screen)),
            "n_cells_deployable": n_deployable,
            "amp_hard_limit_mA": _jsonable(_obj.AMP_HARD_LIMIT_MA),
            "adaptive_window_hz": list(_pa.ADAPTIVE_LFP_BAND_HZ),
            "min_adaptive_rate_hz": _jsonable(_pa.MIN_ADAPTIVE_RATE_HZ),
            # Only the cells that responded at all: the full 50-row screen is mostly cells with no
            # response, which is not what a reader needs to see first.
            "responding_cells": _frame_records(
                screen[screen["n_responding"] > 0].sort_values("n_responding", ascending=False)
                if not screen.empty else screen, limit=20),
            "audit": _frame_records(le.audit, limit=100) if le.audit is not None else [],
        }
    except Exception as e:                                    # noqa: BLE001 — adjunct panel
        _log.exception("StimOptimizer: closed-loop readiness failed")
        return {"available": False,
                "reason": f"closed-loop readiness could not be evaluated: {e}"}


def _arm_comparison(arm):
    """The candidate-versus-incumbent difference and its uncertainty, as the resolution rule sees it.

    Serialised so the interface never reconstructs it. The resolution verdict is a statement about
    `gain` against `k * sd_of_difference`, and a table that prints two posterior means and two
    separate standard deviations asks the reader to combine four numbers in their head to see the
    quantity the verdict is actually about.

    `sd_of_difference` is sqrt(var1 + var2) without the joint covariance term, which the pipeline
    documents: because nearby cells on a smooth kernel are positively correlated, dropping
    `-2*cov` OVERSTATES the variance, so the rule is conservative — it can withhold a
    recommendation it might have supported, but it cannot manufacture one.
    """
    import math

    from .routines import resolution as _RES

    m = getattr(arm, "meta", None) or {}
    try:
        gain = float(m.get("incumbent_mu")) - float(m.get("mu_star"))
    except (TypeError, ValueError):
        gain = None
    # The same propagation the gate and the figure headline use, so the three cannot disagree.
    sd_d = _RES.sd_of_difference(m.get("sd_star"), m.get("incumbent_sd"))
    if not math.isfinite(sd_d) or sd_d <= 0:
        sd_d = None
    k = _RES.RESOLUTION_K
    return {
        "gain": _jsonable(gain),
        "sd_of_difference": _jsonable(sd_d),
        "k": k,
        "margin": _jsonable(k * sd_d) if sd_d is not None else None,
        "sign_convention": ("the objective is a pain score, so LOWER is better and a POSITIVE gain "
                            "favours the candidate over the setting currently in force"),
        "note": ("sd_of_difference is sqrt(sd_candidate^2 + sd_incumbent^2). The joint covariance "
                 "term is omitted because the two cells are not predicted jointly; since nearby "
                 "cells on a smooth kernel are positively correlated, omitting it overstates the "
                 "variance and makes the resolution rule conservative rather than permissive."),
    }


def _blockers(rep, arms, observed_amp_range=None) -> list:
    """Plain-language reasons a parameter recommendation is withheld."""
    observed_amp_range = observed_amp_range or {}
    out = []
    # THREE STATES, counted separately. A bare truthiness test read `None` as a negative, so once
    # the pipeline stopped collapsing the tri-state an arm whose difference could not be FORMED
    # would still have counted towards "every arm was measured and none resolved" — a positive
    # claim about an arm on which nothing was measured.
    _resolved = [k for k, a in arms.items() if a.get("optimum_resolved") is True]
    _too_small = [k for k, a in arms.items() if a.get("optimum_resolved") is False]
    _unformed = [k for k, a in arms.items() if a.get("optimum_resolved") is None]
    if not _resolved:
        msg = ("No arm can distinguish its own best setting from the setting currently in force. "
               "The surfaces show where to look next, not what to program.")
        if _too_small:
            msg += (f" For {len(_too_small)} arm(s) the predicted gain over the setting in force is "
                    f"smaller than the uncertainty of that difference, which more exposure at those "
                    f"cells could change.")
        if _unformed:
            msg += (f" For {len(_unformed)} arm(s) the difference could not be formed at all because "
                    f"a posterior was degenerate, so those arms were NOT compared rather than "
                    f"compared and found wanting; that needs the fit repaired, not more exposure.")
        out.append(msg)
    for label, a in arms.items():
        if a.get("safe_contiguous") is False:
            out.append(f"{label}: the safe set is not contiguous in amplitude, so the safety model "
                       f"permits isolated cells rather than a single ceiling — the seed needs "
                       f"prospective side-effect data before it can bound a ramp.")
    # The optimum can be inside the safe SET while lying above the contiguous safe CEILING, i.e. in
    # a disconnected safe island. That matters clinically rather than cosmetically: a monotone
    # amplitude ramp from the setting in force to that cell would pass through amplitudes the safety
    # model rejects, so the cell is not reachable by the procedure a clinician would actually use.
    unreachable = []
    for label, a in arms.items():
        amp = (a.get("optimum") or {}).get("amp_mA")
        ceil = a.get("safe_contiguous_ceiling")
        try:
            if amp is not None and ceil is not None and np.isfinite(float(ceil)) \
                    and float(amp) > float(ceil):
                unreachable.append(f"{label} (optimum {float(amp):g} mA vs reachable ceiling "
                                   f"{float(ceil):g} mA)")
        except (TypeError, ValueError):
            continue
    if unreachable:
        out.append("Proposed optimum lies ABOVE the contiguous safe ceiling for: "
                   + ", ".join(unreachable) +
                   ". The cell is inside the safe set but in a disconnected island, so a monotone "
                   "amplitude ramp toward it would cross amplitudes the safety model rejects. This "
                   "is a consequence of the two-anchor safety seed, which has no prospective "
                   "side-effect data to shape it, and must be resolved before any ramp is planned.")

    # Two distinct things get conflated here, so both are checked separately.
    #
    # (a) Optimum at the EDGE of the search GRID. That is the surface saying "keep going", which is
    #     what a monotone trend looks like at a boundary. Rare in practice — the grid runs past the
    #     delivered range — so this usually emits nothing, which is the correct outcome, not a bug.
    # (b) Optimum beyond the amplitude ever actually DELIVERED on that hemisphere. This is the one
    #     that fires on real data and is the more meaningful warning: the surrogate is predicting
    #     outside its own support, where the posterior mean is driven by the prior mean function and
    #     the fitted trend rather than by any observation.
    edge, extrap = [], []
    try:
        grid_hi, grid_lo = float(max(PLT.AMP_GRID)), float(min(PLT.AMP_GRID))
    except Exception:
        grid_hi = grid_lo = None
    for label, a in arms.items():
        amp = (a.get("optimum") or {}).get("amp_mA")
        if amp is None:
            continue
        amp = float(amp)
        if grid_hi is not None and (amp >= grid_hi - 1e-9 or amp <= grid_lo + 1e-9):
            edge.append(f"{label} (at {amp:g} mA)")
        rng = observed_amp_range.get(a.get("hemisphere"))
        if rng and np.isfinite(rng[1]) and amp > float(rng[1]) + 1e-9:
            extrap.append(f"{label} (optimum {amp:g} mA vs {float(rng[1]):g} mA ever delivered on "
                          f"the {a.get('hemisphere')} side)")
    if edge:
        out.append("Optimum sits at the EDGE of the amplitude grid for: " + ", ".join(edge) +
                   ". An edge optimum is the surface extrapolating to its boundary rather than "
                   "locating an interior optimum; widening the grid would move the edge, not "
                   "resolve the underlying confound.")
    if extrap:
        out.append("Optimum lies ABOVE the highest amplitude ever delivered for: "
                   + ", ".join(extrap) +
                   ". Outside its own support the posterior mean is carried by the prior mean "
                   "function and the fitted amplitude trend, not by data, and that trend is "
                   "confounded with time in this record. Treat such a cell as a hypothesis to test, "
                   "never as a setting to program.")

    skipped = (rep.manifest or {}).get("skipped") or {}
    for label, why in skipped.items():
        out.append(f"{label}: not fitted — {why}")
    out.append("Settings were historically confounded with time (amplitude rose over the record), and "
               "within-visit testing ramped amplitude monotonically, so neither the chronic nor the "
               "acute record can separate a parameter effect from a time effect. Randomising the "
               "order of settings within a visit is the prerequisite for any recommendation.")
    return out


#: The five figures the browser draws, in the order the page presents them. The order is not
#: cosmetic and is documented in the figure-conventions skill: the posterior surface is the panel
#: that answers the page's question — whether the predicted optimum is separated from the setting
#: currently in force — and the four that follow are secondary to it.
PLOTLY_FIGURES = (
    ("posterior_surface", "fig1_posterior_surface"),
    ("acquisition", "fig2_acquisition_decomposition"),
    ("trajectory", "fig3_search_trajectory"),
    ("dual_model", "fig4_dual_model"),
    ("coverage", "fig5_coverage_map"),
)


def _plotly_figures(ctx) -> dict:
    """Plotly figure JSON for the browser. Never renders images server-side (no kaleido).

    RETURNS BOTH the figures and a per-figure error map, because the previous shape could lose a
    figure without saying so. This function used to catch each figure's exception and log it at
    DEBUG level, so a single broken figure simply did not appear in the returned dict; the caller
    sets `figures_error` only when the WHOLE call raises, and the page had nothing to render and
    nothing to report. That is the same failure class as the missing plotly dependency, which cost
    this page all five figures while looking like an interface that had never been wired for them.

    A figure that fails now names itself, its exception type and its message, so the panel can say
    which one is missing and why instead of rendering an empty box.
    """
    import json as _json
    import traceback as _tb

    import plotly.io as pio
    out = {}
    errors = {}
    for name, fn in PLOTLY_FIGURES:
        f = getattr(PLT, fn, None)
        if f is None:
            # A builder that is not present at all is a different fault from one that raised: it
            # means this service and plots.py have drifted apart, which a deployment can cause and
            # which no amount of data will fix.
            errors[name] = {"builder": fn, "error_type": "MissingBuilder",
                            "message": (f"plots.{fn} does not exist in this build, so the figure "
                                        f"could not be attempted. The service and plots.py have "
                                        f"drifted apart.")}
            continue
        try:
            out[name] = _json.loads(pio.to_json(f(ctx)))
        except Exception as e:
            errors[name] = {"builder": fn, "error_type": type(e).__name__, "message": str(e)}
            # Kept at debug for the traceback, which is too long for a payload, while the summary
            # above travels to the browser.
            _log.debug("StimOptimizer: figure %s failed: %s", fn, _tb.format_exc())
    return {"figures": out, "figure_errors": errors}
