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
from . import clinic_pain as CLPAIN
from . import current_map_schedule as CMS
from . import pipeline
from . import safety_ceiling as SC
from . import stage1_openloop as S1
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
#: THE LINEAR-ALGEBRA THREAD POOL IS CAPPED TO ONE THREAD FOR THE WHOLE REQUEST (2026-09-12).
#:
#: Every matrix this request factorises is small: a Gaussian-process fit on 54 to 69 epochs, an
#: ordinary least-squares fit on a few hundred tiles with about ten columns. OpenBLAS in the
#: container defaults to sixteen threads, and on matrices this size the threads spend their time
#: waiting for each other rather than computing. Measured on RCS08 (probe_so_blas_threads.py): one
#: arm's fit took 3.9 to 4.7 s with the default pool and 0.26 to 0.32 s with one thread, in two
#: alternating rounds, and every number it produced -- the posterior mean and spread over the whole
#: grid, the safe mask, the fitted kernel, the marginal likelihood, the optimum, the queue, the
#: batches -- was bit for bit identical. The cap is applied around the whole request rather than
#: around each fit because the same overhead sits under every small factorisation on the way, and
#: a request holds one gunicorn worker either way, so nothing else in the process loses threads it
#: was using.
#:
#: `STIM_OPTIMIZER_BLAS_THREADS` in the environment overrides the cap: "0" leaves the pool as it
#: is (this is how the before-and-after timing was measured), any other integer sets it. The
#: `threadpoolctl` package ships with scikit-learn and is present in the container; where it is
#: absent (the host test runner) the request runs with the pool untouched, which is what it did
#: before this cap existed.
#: ==========================================================================================
BLAS_THREADS_ENV = "STIM_OPTIMIZER_BLAS_THREADS"


def _blas_threads_capped():
    """Context manager: the BLAS/LAPACK thread pool capped for the duration, or a no-op."""
    import contextlib
    raw = os.environ.get(BLAS_THREADS_ENV, "1").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 1
    if n <= 0:
        return contextlib.nullcontext()
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:                               # pragma: no cover - host runner
        return contextlib.nullcontext()
    return threadpool_limits(limits=n, user_api="blas")

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


#: How many trailing elements of the response key describe the RESPONSE only and not the four
#: tables (review S11, 2026-09-12, raised from 4): the deployable band range the evidence carries
#: (two Biomarkers constants), the ClosedLoop flag (the readiness block only), the two-stage
#: settings (the flag, the override reason AND the override's name, the explore-outside-the-
#: adaptive-envelope override AND its name) and the figure backend. None of these changes the
#: four tables, which come from the flat fit alone; keyed on them, two requests differing only
#: in one of these would sweep each other's tables on every write.
_RESPONSE_ONLY_KEY_TAIL = 9


def _band_span_key_element():
    """The deployable band range as a key element: the two Biomarkers constants the evidence
    frame's centres depend on (`adapter.deployable_band_span`), which the code digest does not
    cover because they live in another module (review S11). Their absence is itself a key
    element, so a response computed without them is never served to a request that has them."""
    try:
        lo, hi = adapter.deployable_band_span()
        return (float(lo), float(hi))
    except Exception as exc:                              # noqa: BLE001 -- named, not hidden
        return ("band span unavailable", type(exc).__name__)


def _explore_outside_key_element(rd) -> str:
    """The response-key element for the explore-outside-the-envelope override.

    "absent" and "present but empty" produce different blocks (the second says the override was
    ignored), so they must be different key elements, or a request naming the key with no reason
    could be served a copy that never mentions it.
    """
    if TWO_STAGE_EXPLORE_OUTSIDE_KEY not in (rd or {}):
        return "0:"
    return "1:" + str((rd or {}).get(TWO_STAGE_EXPLORE_OUTSIDE_KEY) or "").strip()


def _response_signature(uid, matched_key, tiles_key, amp_key, gt_key, request_data, sites, hemis,
                        washin_min, backend):
    """The response key: every input and every setting the fitted result depends on, and the
    response-only settings last, so `_products_signature` can drop them."""
    rd = request_data or {}
    return (RESPONSE_KIND, _RULE_VERSION, _CODE_DIGEST, str(uid), matched_key, tiles_key, amp_key,
            gt_key, tuple(sites), tuple(hemis), float(washin_min),
            int(rd.get("NBatches", 3)), int(rd.get("Q", 4)),
            # ---- the response-only tail, `_RESPONSE_ONLY_KEY_TAIL` elements from here ----
            _band_span_key_element(),
            bool(rd.get("ClosedLoop", True)),
            # The two-stage block is part of the stored response, so the flag and the override
            # reason that shape it are in the key: a request without the flag is never served a
            # copy that carries the block, and one with it is never served a copy without it.
            # The NAMES travel too (review S11): the block prints them, so a second request with
            # the same reason and a different name must not be served the first name.
            bool(_two_stage_requested(rd)), str(rd.get(TWO_STAGE_OVERRIDE_REASON_KEY) or ""),
            str(rd.get(TWO_STAGE_OVERRIDE_BY_KEY) or ""),
            _explore_outside_key_element(rd),
            str(rd.get(TWO_STAGE_EXPLORE_OUTSIDE_BY_KEY) or ""),
            str(backend))


def _products_signature(sig):
    """The key of the four tables: the response key without the response-only tail.

    The backend changes only whether figure JSON is in the response, the two-stage settings
    change only whether the `two_stage` block is in it, the ClosedLoop flag only whether the
    readiness block is, and the band range only what the evidence frame carries; none changes
    the four tables. Keyed on them, two requests differing only in one of those would sweep
    each other's tables on every write, since the store keeps one entry per kind and participant.
    """
    return tuple(sig[:-_RESPONSE_ONLY_KEY_TAIL])


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


#: ==========================================================================================
#: THE RATE-STRATUM AND POOLED SURFACES (2026-09-14, following decisions 157/158).
#:
#: `two_stage.stage1.rate_strata` and `current_map_schedule` carry the NUMBERS decision 158's
#: three-check honesty rule reads, but not the (left current, right current) surface those
#: numbers describe -- so nothing could draw the heatmap the page needs to show WHY a rate reads
#: flat, or WHERE the tried combinations sit. These two functions add it, read straight off the
#: RateStratum/JointStratum objects Stage 1 already holds; no number here is recomputed.
def _round_grid(a, ndigits=4):
    """A 2-D array as a plain nested list, each finite value rounded, a non-finite value `None`
    (never `NaN`, which is not valid JSON)."""
    out = []
    for row in np.asarray(a, float):
        out.append([None if not np.isfinite(v) else round(float(v), ndigits) for v in row])
    return out


def _rate_stratum_surface(rs) -> dict | None:
    """The (amplitude-Left, amplitude-Right) surface for one FITTED `stage1_openloop.RateStratum`.

    `mu[i][j]` / `sd[i][j]` / `safe[i][j]` are the posterior mean, its standard deviation, and
    whether the cell clears the safety model, at `amps_mA[i]` on the left and `amps_mA[j]` on the
    right -- both axes share the one grid the rate was fitted on
    (`rs.grid.amps_left`, identical to `amps_right` since both sides are fit on
    `stage1_openloop.JOINT_AMP_GRID`). `points` are the individual rated epochs the fit actually
    regressed (`rs.meta["points"]`), never a grid cell -- the raw evidence a reader overlays ON
    the surface.
    """
    if rs is None or not getattr(rs, "fitted", False) or rs.grid is None:
        return None
    amps = [round(float(v), 4) for v in np.asarray(rs.grid.amps_left, float)]
    points = [dict(amp_left_mA=_jsonable(p.get("amp_left_mA")),
                   amp_right_mA=_jsonable(p.get("amp_right_mA")),
                   n_reports=_jsonable(p.get("n_reports")),
                   J=_jsonable(p.get("J")), epoch=_jsonable(p.get("epoch")))
             for p in ((rs.meta or {}).get("points") or [])]
    return dict(amps_mA=amps, mu=_round_grid(rs.mu), sd=_round_grid(rs.sd),
               safe=[[bool(v) for v in row] for row in np.asarray(rs.safe, bool)],
               points=points)


def _rate_stratum_lookup(s1) -> dict:
    """`{(pw_us_left, pw_us_right, rate_hz), rounded: RateStratum}` over every joint stratum Stage
    1 fitted, so a serialised `rate_strata` row can find its own raw object back."""
    out = {}
    for (pwl, pwr), sl in (getattr(s1, "slices", None) or {}).items():
        for rate, rs in (getattr(sl, "rate_strata", None) or {}).items():
            out[(round(float(pwl), 6), round(float(pwr), 6), round(float(rate), 6))] = rs
    return out


def _attach_rate_stratum_surfaces(records, s1):
    """Add a `surface` key to every FITTED row of the already-serialised `rate_strata` records,
    in place. An unfitted row (`fitted: False`) is left exactly as it was -- no `surface` key --
    so the frontend's own presence check ("does this row carry a surface") is enough to tell a
    fitted rate from one that never cleared the epoch floor."""
    lut = _rate_stratum_lookup(s1)
    for row in records:
        if not row.get("fitted"):
            continue
        key = (round(float(row["pw_us_left"]), 6), round(float(row["pw_us_right"]), 6),
              round(float(row["rate_hz"]), 6))
        surf = _rate_stratum_surface(lut.get(key))
        if surf is not None:
            row["surface"] = surf
    return records


def _joint_pooled_surfaces(s1) -> dict:
    """One entry per fitted (pulse-width-Left, pulse-width-Right) joint stratum:
    `{"<pwl:g>_<pwr:g>": {pw_us_left, pw_us_right, surface_at_rate: {"<rate:g>": {amps_mA, mu, sd,
    safe}}}}` -- the POOLED 3-input surface's own slice at each rate that stratum actually
    delivered, for reference only (see `stage1_openloop.RateStratum`'s own docstring on why the
    honest per-rate surface, not this one, decides a current). Built once per stratum rather than
    once per rate-strata row, since every rate inside one stratum shares the one pooled fit."""
    out = {}
    for (pwl, pwr), sl in (getattr(s1, "slices", None) or {}).items():
        key = f"{float(pwl):g}_{float(pwr):g}"
        rates = {}
        for rate in (getattr(sl, "rate_strata", None) or {}).keys():
            fi = int(np.argmin(np.abs(np.asarray(sl.grid.freqs, float) - float(rate))))
            mu3 = sl.grid.as_surface(sl.mu)[fi]
            sd3 = sl.grid.as_surface(sl.sd)[fi]
            safe3 = sl.grid.as_surface(np.asarray(sl.safe, float))[fi] > 0
            rates[f"{float(rate):g}"] = dict(
                amps_mA=[round(float(v), 4) for v in np.asarray(sl.grid.amps_left, float)],
                mu=_round_grid(mu3), sd=_round_grid(sd3),
                safe=[[bool(v) for v in row] for row in safe3])
        out[key] = dict(pw_us_left=float(pwl), pw_us_right=float(pwr), surface_at_rate=rates)
    return out


#: ==========================================================================================
#: DISPLAY FIELDS FOR THE PAGE (2026-09-12, the page redesign, phase 3).
#:
#: The page printed sensing contacts by their raw keys ("ONE_THREE_LEFT"), which spell the
#: contact numbers out as words, and printed the setting in force as ONE rate and ONE pulse width
#: for both sides, read from Stage 1's `incumbent_pw_us` -- which Stage 1 read from the LEFT
#: column for both sides until 2026-09-12 (review S1; it now reads each side's own column). On
#: RCS08 the design matrix carries `pw_us_Right` too and it reads 150 us on the incumbent epoch
#: while the left reads 100 us, so the page was printing the left pulse width as the right side's.
#: These fields carry each side's own values, and the Medtronic-form labels, so the page reads
#: rather than derives them.
#:
#: ONE DEFINITION OF THE CONTACT LABEL. The sensing label is `Biomarkers.routines.analytics
#: .format_channel` (the "L 0⁻2⁺" every other page prints, decision 131); it is called here and
#: not re-implemented. The STIMULATION contacts are a different thing -- the settings stream keeps
#: the cathode segments only ("2a-2b-2c"), never the anode -- so their label is the side letter and
#: the cathode contacts with a superscript minus, a whole ring collapsed to its digit ("L 2⁻"), and
#: no anode is printed because none is recorded. `contacts_raw` travels beside it.
#: ==========================================================================================
def sensing_display(channel) -> dict:
    """`display_short` / `display_hemisphere` / `display_contacts` for a sensing contact pair,
    from the Biomarkers formatter. Absent (None) when the formatter cannot be imported, never a
    label invented here."""
    try:
        try:
            from modules.Biomarkers.routines import analytics as _an
        except ImportError:
            from Biomarkers.routines import analytics as _an
        f = _an.format_channel(str(channel), region="")
        return {"display_short": f["short"], "display_hemisphere": f["hemisphere"],
                "display_contacts": f["contacts"]}
    except Exception:                                     # noqa: BLE001 -- no label, not an error
        return {"display_short": None, "display_hemisphere": None, "display_contacts": None}


def stim_contacts_short(cathode, hemisphere) -> str | None:
    """The programmed cathode contacts in the page's Medtronic form: "L 2⁻" for "2a-2b-2c" on the
    Left, "R 1⁻2⁻" for "1a-1b-1c-2a-2b-2c" on the Right, "L 1a⁻1b⁻" when a ring is only partly
    used. None when nothing is recorded ("none", empty, NaN)."""
    if cathode is None:
        return None
    raw = str(cathode).strip()
    if not raw or raw.lower() in ("none", "nan", "case"):
        return None
    side = "L" if str(hemisphere) == "Left" else ("R" if str(hemisphere) == "Right" else "")
    segs = [t for t in raw.replace("+", "-").split("-") if t]
    by_ring = {}
    for t in segs:
        digit = "".join(ch for ch in t if ch.isdigit())
        letter = "".join(ch for ch in t if ch.isalpha()).lower()
        by_ring.setdefault(digit, set()).add(letter)
    parts = []
    for digit in sorted(by_ring, key=lambda d: (d == "", d)):
        letters = by_ring[digit]
        if letters == {"a", "b", "c"} or letters == {""}:
            parts.append(f"{digit}⁻")
        else:
            parts.extend(f"{digit}{l}⁻" for l in sorted(letters))
    return f"{side} {''.join(parts)}".strip()


def in_force_by_side(es, epochs=None) -> dict:
    """The setting in force on EACH side: rate, that side's own pulse width and current, and its
    programmed cathode contacts, with the epoch and the time it began. Empty when there is no
    epoch; a side's value is None when its column is absent or empty, never the other side's.

    READ FROM THE FULL EPOCH TABLE when one is given (review S7, 2026-09-12). ``es`` is the
    matched table, which keeps only the epochs with at least one usable pain report, so its
    newest epoch is the newest RATED setting -- and after a reprogramming, until the first
    rating filed more than one minute later, that is the PREVIOUS setting, not the one the
    device is on. ``epochs`` is ``adapter.exposure_epochs``'s output, every epoch rated or not;
    its newest row is the setting in force. Each side's block then carries
    ``has_ratings_yet`` (is that epoch in the matched table) and ``fitted_incumbent_epoch`` (the
    newest rated epoch, which every surface's gain is referenced to, unchanged), and
    ``differs_from_fitted_incumbent`` says when the two are not the same epoch. Without
    ``epochs`` the matched table is read as before.
    """
    if es is None or len(es) == 0 or "t0" not in es.columns:
        return {}
    fitted = es.sort_values("t0").iloc[-1]
    fitted_epoch = float(fitted["epoch"]) if "epoch" in es.columns else None
    src = "matched table (newest rated epoch)"
    row = fitted
    if epochs is not None and len(epochs) and "t_start" in epochs.columns:
        row = epochs.sort_values("t_start").iloc[-1]
        src = "full epoch table (newest device setting, rated or not)"
    rated = set(pd.to_numeric(es["epoch"], errors="coerce").dropna().astype(float)) \
        if "epoch" in es.columns else set()
    out = {}
    for side in ("Left", "Right"):
        def _col(name, r=row):
            v = r.get(name) if hasattr(r, "get") else None
            return None if v is None or (isinstance(v, float) and np.isnan(v)) else v
        cath = _col(f"cathode_{side}")
        epoch = _col("epoch")
        has_ratings = (float(epoch) in rated) if epoch is not None else None
        out[side] = {
            "rate_hz": _jsonable(_col("freq_hz")),
            "pulse_width_us": _jsonable(_col(f"pw_us_{side}")),
            "amplitude_mA": _jsonable(_col(f"amp_mA_{side}")),
            "contacts_raw": (None if cath is None else str(cath)),
            "contacts_short": stim_contacts_short(cath, side),
            "epoch": _jsonable(epoch),
            "since_utc": _jsonable(_col("t_start") if _col("t_start") is not None else _col("t0")),
            "source": src,
            "has_ratings_yet": has_ratings,
            "fitted_incumbent_epoch": _jsonable(fitted_epoch),
            "differs_from_fitted_incumbent": (
                bool(float(epoch) != float(fitted_epoch))
                if epoch is not None and fitted_epoch is not None else None),
            "note": (None if epoch is None or fitted_epoch is None or float(epoch) == float(fitted_epoch)
                     else (f"the device has been on epoch {float(epoch):g} since "
                           f"{_jsonable(_col('t_start'))}, but no pain rating has been filed under "
                           f"it yet, so every surface's gain is still measured against epoch "
                           f"{float(fitted_epoch):g}, the newest rated one")),
        }
    return out


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


#: ==========================================================================================
#: THE TWO-STAGE PATH, WIRED 2026-09-12 ("wire/configure stim optimizer with a two-stage
#: openloop to CL-path setup").
#:
#: The open-loop search that freezes a rate and pulse width (`stage1_openloop`), the gate that
#: decides whether that frozen configuration may proceed to closed loop (`routines/stage_gate`),
#: and the closed-loop stage (`stage2_closedloop`) existed, were tested, and were reached by
#: nothing: `pipeline.run_two_stage_live`'s only callers were tests. This block is the caller.
#:
#: OFF BY DEFAULT. A request that does not carry `TwoStage: true` gets the response it always got,
#: with no `two_stage` key. With the flag, the path runs on the inputs this request has already
#: loaded -- the matched therapy-and-pain table (`es`) and the settings stream -- and the LFP
#: evidence is built from the same tile cache the closed-loop readiness panel reads, pinned to the
#: rate Stage 1 froze. Every number in the block is copied out of the subsystem's own result
#: objects; nothing is recomputed here.
#:
#: BACKEND. Stage 1 fits `routines/surrogate.py`, the scikit-learn Gaussian process that
#: `pipeline.run` also uses. PyTorch, GPyTorch and BoTorch are not imported anywhere on this path
#: (BOTORCH_REFACTOR.md: "Do not add PyTorch to the production Django container").
#:
#: NOT AN INPUT, said plainly. `routines/stage_gate.RCS08_SELECTED_BANDS` and
#: `RCS08_RESPONSE_SUMMARY` are a snapshot of 2026-09-02 that the decision log has moved past
#: (decisions 38, 59, 62, 64, 124); they are NOT passed, so the gate evaluates its four live
#: conditions and not the two snapshot ones. The amplitude-effect table the service reads is
#: reported beside this block and is not an argument the subsystem accepts.
#: ==========================================================================================
TWO_STAGE_FLAG = "TwoStage"
TWO_STAGE_OVERRIDE_REASON_KEY = "TwoStageOverrideReason"
TWO_STAGE_OVERRIDE_BY_KEY = "TwoStageOverrideBy"
#: THE ADAPTIVE ENVELOPE (2026-09-12, the PI: "don't recommend settings that adaptive cannot use
#: unless there is a scientific or physiological reason"). Stage 1 now searches only settings the
#: device's closed-loop mode can be programmed with (rate at or above the 55 Hz adaptive minimum,
#: `routines/adaptive_envelope.py`) and reports what it excluded and why. These two keys are the
#: exception the instruction allows: a NON-EMPTY reason under the first lifts the constraint and
#: travels, with the name under the second, on the frozen configuration. The first key present
#: with an empty reason changes nothing and the block says the override was ignored.
TWO_STAGE_EXPLORE_OUTSIDE_KEY = "TwoStageExploreOutsideAdaptive"
TWO_STAGE_EXPLORE_OUTSIDE_BY_KEY = "TwoStageExploreOutsideAdaptiveBy"
TWO_STAGE_BACKEND = ("scikit-learn Gaussian process (StimOptimizer/routines/surrogate.py); "
                     "PyTorch, GPyTorch and BoTorch are not used on this path -- the optional "
                     "PyTorch backend was deleted on 2026-09-12 and no request can select it")


def _two_stage_requested(request_data) -> bool:
    v = (request_data or {}).get(TWO_STAGE_FLAG, False)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def _two_stage_jsonable(v):
    """`_jsonable`, extended for what the two-stage result objects carry: tables, dataclasses,
    numpy scalars inside tuples used as dictionary keys, and sets."""
    import dataclasses
    if isinstance(v, pd.DataFrame):
        return {"columns": [str(c) for c in v.columns],
                "index": [_two_stage_jsonable(i) for i in v.index],
                "records": [_two_stage_jsonable(r) for r in v.to_dict("records")]}
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {f.name: _two_stage_jsonable(getattr(v, f.name)) for f in dataclasses.fields(v)}
    if isinstance(v, dict):
        return {(("%g" % k) if isinstance(k, (float, np.floating)) else str(k)):
                _two_stage_jsonable(x) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return [_two_stage_jsonable(x) for x in sorted(v, key=str)]
    if isinstance(v, (list, tuple, np.ndarray, pd.Series)):
        return [_two_stage_jsonable(x) for x in list(v)]
    return _jsonable(v)


def _frozen_joint_stratum(s1, frozen):
    """The one `stage1_openloop.JointStratum` that the frozen configuration was chosen from, or
    ``None`` when nothing was fitted (no adaptive-capable setting, or no strata at all)."""
    if not frozen.settings:
        return None
    left = frozen.setting("Left") if any(s.hemisphere == "Left" for s in frozen.settings) else None
    right = frozen.setting("Right") if any(s.hemisphere == "Right" for s in frozen.settings) else None
    pwl = left.pw_us if left is not None else None
    pwr = right.pw_us if right is not None else None
    if pwl is None or pwr is None:
        return None
    return (s1.slices or {}).get((float(pwl), float(pwr)))


def _joint_queue_frame(s1, frozen, limit=25):
    """WHAT TO TEST NEXT: never-tested cells whose optimistic bound still beats the incumbent, on
    the ONE joint stratum that was actually frozen -- the direct replacement for the old per-arm
    "what to test at the next visit" table, now over (rate, amplitude-Left, amplitude-Right)
    jointly rather than one side at a time.

    Ordered by expected improvement exactly as `routines.acquisition.exploration_queue` orders it
    (unchanged). Eligibility against the delivered-settings census -- whether a row is already on
    the in-clinic testing schedule -- is NOT reproduced here: that annotation belongs to the flat,
    per-arm pipeline's own `_queue_frame`, which cross-references a census this joint path does not
    carry the same way, and building an equivalent joint version is future work, not silently
    faked. This table therefore carries a `rank`, both currents, the predicted gain and its
    uncertainty, and the expected improvement only.
    """
    sl = _frozen_joint_stratum(s1, frozen)
    if sl is None or sl.queue is None or len(sl.queue) == 0:
        return pd.DataFrame()
    from .routines import acquisition as _ACQ
    gx = sl.grid.grid_X()
    idx = np.asarray(sl.queue, int)[:limit]
    ei = _ACQ.expected_improvement(sl.mu[idx], sl.sd[idx], float(sl.incumbent_mu))
    return pd.DataFrame({
        "rank": np.arange(1, len(idx) + 1),
        "freq_hz": gx[idx, 0], "amp_mA_left": gx[idx, 1], "amp_mA_right": gx[idx, 2],
        "posterior_mean": sl.mu[idx], "posterior_sd": sl.sd[idx],
        "expected_improvement": ei,
        "prior_reports_at_this_cell": sl.n_reports[idx],
    })


def _joint_batch_frame(s1, frozen):
    """The within-visit batch (``ACQ.select_batch_within_visit_joint``) for the ONE joint stratum
    that was frozen, as a plain table."""
    sl = _frozen_joint_stratum(s1, frozen)
    if sl is None or not sl.batch:
        return pd.DataFrame()
    return pd.DataFrame([
        dict(rank=i + 1, freq_hz=b.freq_hz, amp_mA_left=b.amp_mA_left, amp_mA_right=b.amp_mA_right,
             posterior_mean=b.mu, posterior_sd=b.sd, acquisition=b.acq, reason=b.reason,
             exploration_fraction=b.exploration_fraction)
        for i, b in enumerate(sl.batch)])


#: ==========================================================================================
#: THE CLINIC-SHEET PAIN STREAM (2026-09-14). The PI's decision, verbatim: "Import all in-clinic
#: AND at-home testing visits. Pull the in-clinic numbers separately (not in REDCap) as an
#: independent data stream for system optimization (critical)." This fits the SAME per-rate
#: (amplitude-Left, amplitude-Right) surfaces Stage 1 already fits on the REDCap stream, on the
#: clinic-and-home testing workbooks alone -- never pooled with the REDCap stream, never changing
#: the REDCap-based recommendation. See `StimOptimizer.clinic_pain`.
def _side_effect_evidence_block(participant):
    """`clinic_pain.amplitude_severity_evidence` on this participant's stored clinic steps, for
    the closed-loop gate's over-envelope refusal (2026-09-15, the PI: "recompute always"). Never
    raises: a failure comes back as a not-assessable answer naming the failure, so the gate still
    says plainly that no statistic was available rather than quoting a stale one."""
    try:
        steps, _stamp, reason = CLPAIN.load_clinic_steps(participant, consumer="stim_optimizer",
                                                          root=_SHARED_CACHE_DIR_OVERRIDE)
        if steps is None or len(steps) == 0:
            return dict(assessable=False, rho=None, p=None, n_scored_stim_on=0, n_above_4mA=0,
                        reason=reason or "no clinic steps stored", sentence=None)
        return CLPAIN.amplitude_severity_evidence(steps)
    except Exception as exc:                                      # noqa: BLE001 -- adjunct block
        _log.exception("StimOptimizer: the side-effect-versus-current statistic could not be computed")
        return dict(assessable=False, rho=None, p=None, n_scored_stim_on=0, n_above_4mA=0,
                    reason=f"could not be computed: {type(exc).__name__}: {exc}", sentence=None)


def _clinic_stream_stage1_block(participant, *, hemispheres, safety_ceiling_by_hemisphere,
                                redcap_pooled_var, in_force=None) -> dict:
    """`{"rate_strata_clinic": [...], "clinic_stream": {...}}`. Never raises: a failure is
    reported under `clinic_stream.reason` with `clinic_stream.available = False`."""
    try:
        fit = CLPAIN.fit_clinic_rate_strata(
            participant, hemispheres=tuple(hemispheres),
            safety_ceiling_by_hemisphere=safety_ceiling_by_hemisphere,
            redcap_pooled_var=redcap_pooled_var, in_force=in_force,
            root=_SHARED_CACHE_DIR_OVERRIDE)
    except Exception as exc:                                      # noqa: BLE001 -- adjunct block
        _log.exception("StimOptimizer: the clinic-sheet stream fit failed")
        return {"rate_strata_clinic": [],
               "clinic_stream": {"available": False,
                                 "reason": f"the clinic-sheet fit could not run: "
                                          f"{type(exc).__name__}: {exc}"}}
    fit["visits"] = _clinic_stream_visits_summary(participant)
    s1c = fit.pop("stage1_result", None)
    if s1c is None or not fit.get("available"):
        return {"rate_strata_clinic": [], "clinic_stream": fit}
    rate_strata_clinic = _attach_rate_stratum_surfaces(
        _frame_records(getattr(s1c, "rate_summary", None)), s1c)
    for row in rate_strata_clinic:
        row["source"] = "clinic_sheets"
        row["n_visits"] = fit.get("n_files")
        row["n_clinic"] = fit.get("n_clinic")
        row["n_home"] = fit.get("n_home")
    fit["strata_skipped"] = {str(k): str(v) for k, v in (s1c.skipped or {}).items()}
    return {"rate_strata_clinic": rate_strata_clinic, "clinic_stream": fit}


def _clinic_stream_visits_summary(participant) -> list:
    """One row per visit date: setting, step/pain counts, rates and current ranges tried -- what
    the page can list as "what was ingested" without re-reading the store's raw table."""
    try:
        steps, _stamp, reason = CLPAIN.load_clinic_steps(
            participant, consumer="stim_optimizer", root=_SHARED_CACHE_DIR_OVERRIDE)
    except Exception:                                             # noqa: BLE001
        return []
    if steps is None or len(steps) == 0:
        return []
    out = []
    for (vdate, setting), sub in steps.groupby(["visit_date", "setting"]):
        rates = sorted(float(r) for r in sub["freq_hz"].dropna().unique())
        amps = pd.concat([sub["amp_mA_Left"], sub["amp_mA_Right"]]).dropna()
        # Every row in the stored table already carries at least one pain score (that is what
        # made it a step worth parsing), so "with pain" and "steps" are the same count here.
        out.append(dict(
            visit_date=str(vdate), setting=str(setting), n_steps=int(len(sub)),
            n_with_pain=int(len(sub)), rates_hz=rates,
            amp_mA_min=(float(amps.min()) if len(amps) else None),
            amp_mA_max=(float(amps.max()) if len(amps) else None)))
    out.sort(key=lambda r: r["visit_date"])
    return out


def _two_stage_payload(rep, *, inputs, seconds, in_force=None, clinic_block=None) -> dict:
    """The `two_stage` block from a `pipeline.TwoStageReport`: Stage 1's frozen configuration,
    the gate's verdict with each condition's reason and the evidence it read, Stage 2's output or
    its refusal, and a provenance sentence per stage. Read from the report, never recomputed."""
    s1, gate, s2, man = rep.stage1, rep.gate, rep.stage2, dict(rep.manifest or {})
    frozen = s1.frozen
    lfp = dict(man.get("lfp_evidence") or {})

    settings = []
    for s in frozen.settings:
        settings.append({
            "hemisphere": s.hemisphere,
            "rate_hz": _jsonable(s.rate_hz),
            "pulse_width_us": _jsonable(s.pw_us),
            "amplitude_preferred_mA": _jsonable(s.amp_star_mA),
            "amplitude_delivered_min_mA": _jsonable(s.amp_delivered_min_mA),
            "amplitude_delivered_max_mA": _jsonable(s.amp_delivered_max_mA),
            "n_epochs_fitted_on_the_chosen_stratum": _jsonable(s.n_epochs_fitted),
            "rate_resolved": _jsonable(s.rate_resolved),
            "pulse_width_resolved": _jsonable(s.pw_resolved),
            "resolved": bool(s.resolved),
            # The joint resolution's own numbers (2026-09-14): identical on both sides of one
            # configuration, since there is one rate knob and one joint comparison against the
            # incumbent now. Carried here so a reader (DecisionStrip.js) does not have to
            # cross-reference the strata table to find the gain the verdict rests on.
            "gain": _jsonable(getattr(s, "gain", float("nan"))),
            "sd_of_difference": _jsonable(getattr(s, "sd_of_difference", float("nan"))),
            "reasons": [str(r) for r in s.reasons],
            "detail": _two_stage_jsonable(dict(s.detail or {})),
        })
    stage1 = {
        "frozen_configuration": {
            "settings": settings,
            "primary_item": str(frozen.primary_item),
            "incumbent_epoch": _jsonable(frozen.incumbent_epoch),
            "incumbent_rate_hz": _jsonable(frozen.incumbent_rate_hz),
            "incumbent_pulse_width_us": _jsonable(frozen.incumbent_pw_us),
            # Each side's own pulse width in force, from its own column (review S1);
            # `incumbent_pulse_width_us` above is the LEFT column's value, kept under its name.
            "incumbent_pulse_width_us_by_side": _two_stage_jsonable(
                dict(getattr(frozen, "incumbent_pw_us_by_side", None) or {})),
            "data_horizon": str(frozen.data_horizon),
            "washin_min": _jsonable(frozen.washin_min),
            "n_epochs_total": _jsonable(frozen.n_epochs_total),
            "resolved": bool(frozen.resolved),
            "overridden": bool(frozen.overridden),
            "override": _two_stage_jsonable(dict(frozen.override)) if frozen.override else None,
            # The adaptive envelope (2026-09-12): whether the search was held to settings the
            # closed-loop mode can use, what it excluded and why, and -- when lifted -- the stated
            # reason and who gave it. Copied from Stage 1's own record; the per-side detail is
            # under each setting's `detail.adaptive_envelope`.
            "adaptive_envelope": _two_stage_jsonable(dict(getattr(frozen, "adaptive_envelope",
                                                                  None) or {})),
            # Stage 1 searches rate x pulse width x amplitude per side. The electrode contacts are
            # not a searched dimension and the frozen configuration does not carry them; the
            # sensing contact the gate's evidence came from is under `lfp_evidence.selected_key`.
            "contacts": None,
            "contacts_note": ("Stage 1 does not choose or freeze the stimulation contacts; it "
                              "freezes the rate, the pulse width and the preferred amplitude on "
                              "each side. The sensing contact behind the gate's LFP evidence is "
                              "named in lfp_evidence.selected_key."),
            # Each side's OWN setting in force (2026-09-12), read from the full epoch table
            # (review S7): what the device is actually programmed to on each side, contacts
            # included, whether or not a rating has been filed under it yet.
            "in_force_by_side": dict(in_force or {}),
        },
        "strata": _frame_records(s1.summary),
        # ONE ROW PER (pulse-width pair, rate) that was even attempted (2026-09-14): whether a
        # per-rate current surface was fitted, its resolution verdict and numbers, and the
        # pooled 3-input model's own slice at that rate for reference only. This is what
        # actually decided the current under "frozen_configuration" above; see
        # ``stage1_openloop.RateStratum``.
        "rate_strata": _attach_rate_stratum_surfaces(
            _frame_records(getattr(s1, "rate_summary", None)), s1),
        # The POOLED 3-input surface's own slice at every rate a stratum delivered, once per
        # (pulse-width-Left, pulse-width-Right) stratum -- reference only, never what a current is
        # read off; see `_joint_pooled_surfaces` and `stage1_openloop.RateStratum`.
        "pooled_surfaces": _joint_pooled_surfaces(s1),
        "strata_skipped": {str(k): str(v) for k, v in (s1.skipped or {}).items()},
        "audit": _two_stage_jsonable(dict(s1.audit or {})),
        # WHAT TO TEST NEXT, from the JOINT stratum that was actually frozen (2026-09-14). There
        # is one such stratum now, not one per side (rate is shared), so there is one queue and
        # one batch rather than a per-arm pair. Never rate/amplitude combinations already
        # delivered -- `ACQ.exploration_queue`'s own rule, unchanged.
        "queue": _frame_records(_joint_queue_frame(s1, frozen)),
        "batch": _frame_records(_joint_batch_frame(s1, frozen)),
        "describe": frozen.describe(),
        # THE CLINIC-SHEET PAIN STREAM (2026-09-14), independent of everything above: the SAME
        # per-rate surface shape, fitted on the clinic-and-home testing workbooks alone. Never
        # pooled with the REDCap-based `rate_strata`; see `_clinic_stream_stage1_block`.
        "rate_strata_clinic": (clinic_block or {}).get("rate_strata_clinic", []),
        "clinic_stream": (clinic_block or {}).get(
            "clinic_stream", {"available": False, "reason": "not requested"}),
    }

    conditions = []
    for c in gate.conditions:
        conditions.append({"name": c.name, "verdict": c.verdict, "passed": _jsonable(c.passed),
                           "overridden": bool(c.overridden), "detail": str(c.detail),
                           "evidence": _two_stage_jsonable(dict(c.evidence or {}))})
    gate_block = {
        "passed": bool(gate.passed),
        "verdict": gate.headline,
        "n_conditions": len(gate.conditions),
        "conditions": conditions,
        "refusals": [{"condition": n, "reason": d} for n, d in gate.refusals()],
        "failed": list(gate.failed_names()),
        "not_assessed": list(gate.not_assessed_names()),
        "describe": gate.describe(),
    }

    if s2.started:
        stage2 = {
            "started": True,
            "n_valid_policies": int(s2.n_valid),
            "n_rejected": int(len(s2.rejected)) if s2.rejected is not None else 0,
            "policies": _frame_records(s2.policies),
            "rejected": _frame_records(s2.rejected, limit=200),
            "best": (_two_stage_jsonable(s2.best().to_dict()) if s2.best() is not None else None),
            "ranking_basis": str(s2.ranking_basis),
            "ranking_assessed": _jsonable(s2.ranking_assessed),
            "notes": [str(n) for n in s2.notes],
            "describe": s2.describe(),
        }
    else:
        stage2 = {
            "started": False,
            "reason": ("the gate refused, so Stage 2 did not start; the refusals are listed "
                       "under gate.refusals and repeated here"),
            "refusal_reasons": [{"condition": n, "reason": d} for n, d in s2.refusal_reasons],
            "notes": [str(n) for n in s2.notes],
            "describe": s2.describe(),
        }

    sel = lfp.get("selected_key")
    env = dict(getattr(frozen, "adaptive_envelope", None) or {})
    env_sentence = ""
    if env.get("statement"):
        env_sentence = (f" The search was {env['statement']}"
                        + (f"; {env.get('n_exclusions', 0)} exclusion(s) are listed under the "
                           "frozen configuration" if env.get("constrained") else "")
                        + "." + (f" NOTE: {env['override_ignored']}."
                                 if env.get("override_ignored") else ""))
    provenance = {
        "stage1": (f"Stage 1 read the matched therapy-and-pain table this request loaded "
                   f"({inputs.get('matched_table') or 'no store key'}): "
                   f"{frozen.n_epochs_total} epochs, primary outcome {frozen.primary_item}, "
                   f"incumbent epoch {frozen.incumbent_epoch:g} at "
                   f"{frozen.incumbent_rate_hz:g} Hz; {len(s1.slices)} pulse-width strata fitted, "
                   f"{len(s1.skipped or {})} skipped." + env_sentence),
        "gate": (f"The gate read the frozen configuration from Stage 1 and LFP evidence built "
                 f"from the tile cache ({inputs.get('tiles') or 'no store key'}) with the "
                 f"settings stream ({inputs.get('settings_stream') or 'no store key'}), pinned to "
                 f"the frozen rate {lfp.get('pinned_rate_hz')} Hz: "
                 + (f"cell {tuple(sel)} was selected"
                    if sel else f"no cell was selected ({lfp.get('refusal_class')})")
                 + f"; {lfp.get('n_cells_screened', 0)} cells screened, "
                   f"{lfp.get('n_cells_unbuildable', 0)} could not be built."),
        "stage2": ("Stage 2 read the frozen configuration and the gate result"
                   + (" and enumerated closed-loop policies on the selected LFP evidence."
                      if s2.started else "; it did not start because the gate refused.")),
    }

    lfp_out = _two_stage_jsonable(lfp)
    # The sensing contact the check read, in the page's form ("L 0⁻2⁺"), beside its raw key;
    # and, per side (review S3), the contact each side's check read.
    lfp_out["selected_display_short"] = (sensing_display(sel[0])["display_short"]
                                         if sel and len(sel) else None)
    for side, blk in (lfp_out.get("selected_by_side") or {}).items():
        k = blk.get("selected_key") if isinstance(blk, dict) else None
        if isinstance(blk, dict):
            blk["selected_display_short"] = (sensing_display(k[0])["display_short"]
                                             if k and len(k) else None)
    return {
        "requested": True,
        "available": True,
        "backend": TWO_STAGE_BACKEND,
        "seconds": _jsonable(seconds),
        "can_deploy_closed_loop": bool(rep.can_deploy_closed_loop()),
        "stage1": stage1,
        "gate": gate_block,
        "lfp_evidence": lfp_out,
        "stage2": stage2,
        "manifest": _two_stage_jsonable({k: v for k, v in man.items() if k != "lfp_evidence"}),
        "inputs": dict(inputs),
        "provenance": provenance,
        "describe": rep.describe(),
    }


def two_stage_block(participant, es, *, request_data, stream, washin_min, hemispheres, sites,
                    data_horizon, inputs, in_force=None, evidence_inputs=None,
                    safety_ceiling_by_hemisphere=None) -> dict:
    """Run the open-loop -> gate -> closed-loop path on this request's own inputs and report it.

    Never raises into the response: a failure here is reported under `two_stage.reason` and the
    open-loop optimizer's own result stands.
    """
    import time as _time
    from .routines import objective as _obj

    rd = request_data or {}
    override_reason = rd.get(TWO_STAGE_OVERRIDE_REASON_KEY)
    override_reason = str(override_reason).strip() if override_reason else None
    # The explore-outside-the-adaptive-envelope override. `requested` is "the key is present",
    # whatever it carries, so that a key with an empty reason is reported as ignored rather than
    # treated as if it had never been sent.
    explore_requested = TWO_STAGE_EXPLORE_OUTSIDE_KEY in rd
    explore_reason = rd.get(TWO_STAGE_EXPLORE_OUTSIDE_KEY) if explore_requested else None
    explore_reason = str(explore_reason).strip() if explore_reason else None
    explore_by = (str(rd.get(TWO_STAGE_EXPLORE_OUTSIDE_BY_KEY)).strip()
                  if explore_reason and rd.get(TWO_STAGE_EXPLORE_OUTSIDE_BY_KEY) else None)
    t0 = _time.perf_counter()
    # Recomputed from the clinic sheets on every request and handed to the gate, which quotes it
    # (or says none was available) in an over-envelope refusal -- never a typed number.
    side_effect_evidence = _side_effect_evidence_block(participant)
    gate_kwargs = {"side_effect_evidence": side_effect_evidence}
    if safety_ceiling_by_hemisphere:
        gate_kwargs["ceiling_mA"] = safety_ceiling_by_hemisphere
    try:
        rep = pipeline.run_two_stage_live(
            participant, design=es, stream=stream, request_data=request_data,
            washin_min=float(washin_min), amp_ceiling=_obj.AMP_HARD_LIMIT_MA,
            hemispheres=tuple(hemispheres), primary_item=str(tuple(sites)[0]),
            data_horizon=data_horizon, evidence_inputs=evidence_inputs,
            override_reason=override_reason,
            override_by=(str(rd.get(TWO_STAGE_OVERRIDE_BY_KEY)) if override_reason
                         and rd.get(TWO_STAGE_OVERRIDE_BY_KEY) else None),
            explore_outside_adaptive_reason=explore_reason,
            explore_outside_adaptive_by=explore_by,
            explore_outside_adaptive_requested=explore_requested,
            # The PI-stated ceiling per side (2026-09-12): the safety model's severity-3 seed
            # in Stage 1, as in the flat fit, and the ceiling the gate checks the limits against.
            stage1_kwargs=({"safety_ceiling_by_hemisphere": safety_ceiling_by_hemisphere}
                           if safety_ceiling_by_hemisphere else None),
            gate_kwargs=gate_kwargs)
    except Exception as exc:                          # noqa: BLE001 -- adjunct block
        _log.exception("StimOptimizer: the two-stage path failed")
        return {"requested": True, "available": False, "backend": TWO_STAGE_BACKEND,
                "seconds": _jsonable(_time.perf_counter() - t0), "inputs": dict(inputs),
                "reason": f"the two-stage path could not run: {type(exc).__name__}: {exc}"}
    # The REDCap stream's own pooled within-setting variance, already computed inside Stage 1
    # (`objective.build_objective`'s own `pooled_within_var` column) -- read back, not
    # recomputed, and used ONLY as a fallback noise estimate for the clinic stream when the
    # clinic stream cannot estimate its own (see `clinic_pain.fit_clinic_rate_strata`).
    try:
        _redcap_pooled_var = float(rep.stage1.D["pooled_within_var"].iloc[0])
    except Exception:                                  # noqa: BLE001
        _redcap_pooled_var = None
    clinic_block = _clinic_stream_stage1_block(
        participant, hemispheres=hemispheres,
        safety_ceiling_by_hemisphere=safety_ceiling_by_hemisphere,
        redcap_pooled_var=_redcap_pooled_var, in_force=in_force)
    # The same answer the gate was given, beside the clinic stream it was computed from.
    clinic_block.setdefault("clinic_stream", {})["side_effect_vs_current"] = _jsonable(
        side_effect_evidence)
    return _two_stage_payload(rep, inputs=inputs, seconds=_time.perf_counter() - t0,
                              in_force=in_force, clinic_block=clinic_block)


def run_for_participant(request_data: dict) -> dict:
    """Build the design matrix from platform data, fit every arm, return a JSON-able payload.

    The work is `_run_for_participant`; this wrapper only caps the linear-algebra thread pool for
    its duration (see `BLAS_THREADS_ENV` above), which changes no number and, measured on RCS08,
    removes most of the time the arm fits and the closed-loop screen spent waiting on threads.
    """
    with _blas_threads_capped():
        return _run_for_participant(request_data)


def _run_for_participant(request_data: dict) -> dict:
    """Build the design matrix from platform data, fit every arm, return a JSON-able payload.

    Request keys (all optional except ParticipantId):
      ParticipantId  participant uid
      Sites          list of pain-site metric names (default left_leg + back)
      Hemispheres    list of "Left"/"Right" (default both)
      WashinMin      wash-in exclusion in MINUTES (default 1.0 — PI-declared for a rapid responder)
      Backend        "plotly" (default, returns figure JSON) or "none" (tables only, fast)
      NBatches, Q    forward-simulation depth for the trajectory panel
      TwoStage       true runs the open-loop -> gate -> closed-loop path on the same inputs and
                     attaches it under `two_stage`; absent or false (the default) leaves the
                     response exactly as it was
      TwoStageOverrideReason, TwoStageOverrideBy
                     a clinician override of the gate's resolution condition, with the reason it
                     requires (stage1_openloop.clinician_override); only read when TwoStage is on
      TwoStageExploreOutsideAdaptive, TwoStageExploreOutsideAdaptiveBy
                     by default Stage 1 recommends only settings the device's closed-loop mode
                     can use (rate at or above the 55 Hz adaptive minimum) and lists what it
                     excluded and why under two_stage.stage1.frozen_configuration
                     .adaptive_envelope. A NON-EMPTY scientific or physiological reason under
                     the first key lifts that constraint; the reason and the name under the
                     second travel on the frozen configuration. The first key with an empty
                     reason changes nothing and the block says the override was ignored. Only
                     read when TwoStage is on; both are in the response key.
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
            served["cache_status"] = _cache_status(uid, sig)
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

    # THE FLAT, PER-ARM PIPELINE (`pipeline.run`) IS NO LONGER CALLED FROM THIS REQUEST PATH
    # (2026-09-14). The PI's instruction, verbatim: "Get rid of the whole arm strip and chart
    # display. That arm thing doesn't make any sense and shouldn't belong there. Only keep the
    # newer two-stage plan." The page no longer renders the per-arm strip, its chart, the 5
    # per-arm figures or the per-arm "what to test next" queue that all read `arms` -- see
    # `Client/src/views/Reports/StimOptimizer/index.js`. `pipeline.run`, `routines.plots`,
    # `_arm_comparison` and `_blockers` are UNCHANGED and still fully tested
    # (`tests/test_pipeline.py`); `pipeline.run` remains a valid, documented, independent entry
    # point for anyone who wants the two independent per-hemisphere (frequency, amplitude)
    # surfaces (its own module docstring is unchanged), it is simply not reachable from this page
    # any more. The two-stage plan (`two_stage_block`, below) is unaffected: it has always run
    # its own path (`pipeline.run_two_stage_live`), never through this call.
    #
    # THE SAFETY MODEL'S CEILING, stated by the PI per side (`safety_ceiling.py`, 2026-09-12):
    # built once here and handed to Stage 1 (inside `two_stage_block`) and to the gate, so every
    # safe set and the "under the ceiling" check read one source.
    _ceilings = SC.ceilings_by_hemisphere(uid, hemis)
    # THE SENSED SIGNAL AND THE EPOCHS ARE BUILT ONCE FOR BOTH CONSUMERS BELOW (2026-09-12). The
    # closed-loop readiness screen and the two-stage path each asked `adapter.evidence_inputs` for
    # the same pair -- the recordings, the tile cache and the exposure epochs -- and on RCS08 each
    # build cost about 3 s. Built here with the stream this request already holds; a failure hands
    # None to both, and each then builds its own exactly as it did before, so the degradation is
    # unchanged. The screen's own try/except still owns any failure inside the screen.
    _ev_inputs = None
    if bool((request_data or {}).get("ClosedLoop", True)) or _two_stage_requested(request_data):
        try:
            _ev_inputs = adapter.evidence_inputs(participant, stream=_stream)
        except Exception as exc:                          # noqa: BLE001 -- each consumer builds its own
            # One line rather than a traceback: the consumer that then fails the same way logs
            # its own traceback and reports the reason in the response.
            _log.warning("StimOptimizer: the shared evidence inputs could not be built (%r); "
                         "each consumer will build its own", exc)
    # THE SETTING IN FORCE, from the full epoch table (review S7): the epochs the evidence
    # inputs already carry when they were built, else the stream collapsed to epochs here
    # (0.02 s on RCS08), else the matched table's newest rated epoch as before.
    try:
        _epochs_full = (_ev_inputs[1] if _ev_inputs is not None
                        else (adapter.exposure_epochs(_stream) if _stream is not None else None))
    except Exception as exc:                              # noqa: BLE001 -- fall back to the matched table
        _log.warning("StimOptimizer: the full epoch table could not be built (%r)", exc)
        _epochs_full = None
    in_force = in_force_by_side(es, epochs=_epochs_full)
    _screen_out = {}
    out = {
        "available": True,
        "participant": uid,
        "design_matrix": design_matrix_summary(es),
        # Each side's own rate, pulse width, current and cathode contacts from the newest epoch
        # (2026-09-12), so the page's decision strip reads them rather than the left side's twice.
        "in_force_by_side": in_force,
        # `manifest`, `summary`, `arms`, `recommendation_supported` and `blockers` came from the
        # flat, per-arm pipeline (`pipeline.run`), which this request path no longer calls
        # (2026-09-14: the arm strip and its chart are gone from the page). The two-stage plan
        # under `two_stage`, below, is the page's only recommendation now.
        "washin_min": washin_min,
        "closed_loop": closed_loop_readiness(participant, es,
                                             include=bool((request_data or {})
                                                          .get("ClosedLoop", True)),
                                             inputs=_ev_inputs, screen_out=_screen_out,
                                             ceilings=_ceilings),
        "amplitude_effect": amp_block,
        "ground_truth": gt_block,
        "store": store_block,
    }
    # THE TWO-STAGE PATH, only when asked for. Attached before the write-back so the stored
    # response carries it; the flag is in the response key, so a request without the flag is
    # never served this copy.
    if _two_stage_requested(request_data):
        out["two_stage"] = two_stage_block(
            participant, es, request_data=request_data, stream=_stream, washin_min=washin_min,
            hemispheres=hemis, sites=sites, data_horizon=horizon,
            inputs={"matched_table": matched_key, "tiles": tiles_key,
                    "settings_stream": stream_key},
            in_force=in_force, evidence_inputs=_ev_inputs,
            safety_ceiling_by_hemisphere=_ceilings)
    # THE TITRATION SESSION TO RUN NEXT (2026-09-12 evening, the PI: "make #4 a feature of next
    # stim opt recommendation combined with 30"): designed from this participant's own record,
    # attached before the write-back so the stored response carries it. Never raises.
    out["titration_plan"] = titration_plan_block(
        participant, in_force=in_force, screen=_screen_out.get("screen"),
        ceilings=_ceilings, hemispheres=hemis, es=es)
    # THE JOINT CURRENT-MAP TITRATION SCHEDULE (2026-09-14, his instruction: "do (c) both and
    # make a titration schedule to actually make these plots useful"). Computed on every request
    # from inputs this request already holds; nothing is stored.
    out["current_map_schedule"] = current_map_schedule_block(
        participant, es=es, in_force=in_force, ceilings=_ceilings)
    if sig is not None:
        try:
            # `rep` no longer exists on this path (the flat pipeline is not run here); every
            # read of it inside `_write_outputs` already goes through `getattr(rep, ..., None)`,
            # so `None` degrades exactly the way an empty `rep.arms`/`rep.summary` always did.
            _write_outputs(str(uid), sig, prov, None, out)
        except Exception as exc:                      # noqa: BLE001
            # Say so in the response rather than only in the log: a request that silently
            # stores nothing looks, from the page, exactly like one that stored everything.
            _log.warning("StimOptimizer: the outputs were not written back (%r)", exc)
            store_block["write_error"] = repr(exc)
    out["cache_status"] = _cache_status(uid, sig)             # Track C step 4
    return out


_CACHE_STATUS_MEANING = ("the date this optimizer response was last computed and stored; a "
                         "request with the same recordings, settings, pain reports and controls "
                         "is served from it, and any change to those computes and stores it again")


def _cache_status(uid, sig):
    if sig is None:
        return {"kind": RESPONSE_KIND, "exists": False, "last_built_utc": None,
                "what_it_means": _CACHE_STATUS_MEANING,
                "note": "this response is not stored (the store block says why)"}
    return _cache_store.status_for_page(RESPONSE_KIND, str(uid), sig,
                                        what_it_means=_CACHE_STATUS_MEANING,
                                        root=_SHARED_CACHE_DIR_OVERRIDE)


#: ==========================================================================================
#: THE TITRATION SESSION TO RUN NEXT (open item 30 and decision 144, joined by the PI's decision
#: of 2026-09-12 evening). `titration_plan.py` holds the arithmetic; this block gathers the
#: inputs the request already holds -- each side's setting in force, the PI-stated ceiling, the
#: readiness screen's per-side best contact -- and reads the two stored tables the Closed-Loop
#: page writes (the pooled current-to-power table and the per-run points table) ONCE each, as
#: `stim_optimizer`, so the sentence "no run holds 8 settled settings today" is derived from the
#: record and not typed. On screen: Stim Optimizer page, "Titration session to run next".
#: ==========================================================================================
POOLED_KIND = "within_visit_pooled_shape"
RUN_POINTS_KIND = "three_source_run_points"


def _stored_table_as_stim_optimizer(kind, uid):
    """`(frame or None, note)`: the newest stored entry of `kind`, read as stim_optimizer; a
    refusal or a miss is a note, never an error."""
    try:
        table, stamp = _cache_store.load_newest(kind, uid, consumer="stim_optimizer",
                                                root=_SHARED_CACHE_DIR_OVERRIDE)
    except _provenance.SelfDerivedProduct as exc:
        return None, f"{kind}: refused by the store: {exc}"
    except Exception as exc:                          # noqa: BLE001
        return None, f"{kind}: could not be read: {exc!r}"
    if table is None:
        return None, (f"{kind}: no entry is stored for this participant (the Closed-Loop page writes it)"
                      if not stamp else f"{kind}: the newest entry could not be read")
    if not isinstance(table, pd.DataFrame):
        try:
            table = pd.DataFrame(table)
        except Exception:                             # noqa: BLE001
            return None, f"{kind}: the stored payload is not a table"
    return table, f"{kind}: read, {len(table)} rows, written {stamp.get('written_utc')}"


def _best_contact_for_side(screen, side, rate_hz=None):
    """The readiness screen's best cell for stimulation on `side`, as a dict with the page's
    contact label: the screen's own ranking (`lfp_evidence.best_deployable`, ipsilateral first)
    among deployable cells AT THE SESSION'S RATE when `rate_hz` is given -- the same selection
    the two-stage gate makes per side (`pipeline.select_for_side`), because a response measured
    at one rate says nothing about another -- else among deployable cells at any rate, named as
    such; else the cell on that side with the most responding bands. None when the screen has no
    cell for the side."""
    if screen is None or len(screen) == 0 or "hemisphere" not in screen.columns:
        return None, "the readiness screen has no cells"
    from .routines import lfp_evidence as _ev
    key = _ev.best_deployable(screen, hemisphere=side, rate_hz=rate_hz) if rate_hz is not None else None
    how = None
    if key is not None:
        how = (f"the readiness screen's best deployable cell for this side at the session's rate, "
               f"{float(rate_hz):g} Hz (lfp_evidence.best_deployable, the gate's own per-side pick)")
    else:
        key = _ev.best_deployable(screen, hemisphere=side)
        if key is not None:
            how = ("the readiness screen's best deployable cell for this side, at any rate "
                   "(lfp_evidence.best_deployable)"
                   + (f"; no cell on this side passed at the session's rate of {float(rate_hz):g} Hz, "
                      f"so its evidence is from {float(key[2]):g} Hz" if rate_hz is not None else ""))
    if key is not None:
        rows = screen[(screen["channel"].astype(str) == str(key[0]))
                      & (screen["hemisphere"].astype(str) == str(key[1]))
                      & np.isclose(pd.to_numeric(screen["rate_hz"], errors="coerce"), float(key[2]))]
    else:
        rows = screen[screen["hemisphere"].astype(str) == str(side)]
        if rows.empty:
            return None, f"the readiness screen has no cell for {side} stimulation"
        rows = rows.sort_values(["n_responding", "median_separation_d"], ascending=False).head(1) \
            if "n_responding" in rows.columns else rows.head(1)
        how = ("no cell for this side passed the readiness screen; the cell on this side with the "
               "most responding bands")
    r = rows.iloc[0]
    rec = {k: _jsonable(r.get(k)) for k in ("channel", "hemisphere", "rate_hz", "n_bands", "n_responding",
                                            "responding_fraction", "median_separation_d",
                                            "laterality", "sensing_side", "deployable")}
    rec.update(sensing_display(rec.get("channel")))
    if str(rec.get("laterality")) == "contralateral" and "sensing_side" in screen.columns:
        # The pick is a contact on the OTHER side (decision 143, S3): name the best contact on
        # THIS side too, whatever it scored, so the clinician can weigh the extra device
        # configuration a contralateral pairing needs against the evidence on the side itself.
        own = screen[(screen["hemisphere"].astype(str) == str(side))
                     & (screen["sensing_side"].astype(str) == str(side))]
        if rate_hz is not None and "rate_hz" in own.columns:
            at_rate = own[np.isclose(pd.to_numeric(own["rate_hz"], errors="coerce"), float(rate_hz))]
            own = at_rate if len(at_rate) else own
        if len(own):
            cols = [c for c in ("deployable", "n_responding", "median_separation_d") if c in own.columns]
            o = own.sort_values(cols, ascending=False).iloc[0]
            alt = {k: _jsonable(o.get(k)) for k in ("channel", "rate_hz", "n_bands", "n_responding",
                                                    "deployable", "blocking_reasons")}
            alt.update(sensing_display(alt.get("channel")))
            rec["ipsilateral_alternative"] = alt
    return rec, how


#: ==========================================================================================
#: THE JOINT CURRENT-TITRATION SCHEDULE (2026-09-14). His instruction, verbatim: "do (c) both and
#: make a titration schedule to actually make these plots useful." The finding it answers: the
#: pooled 3-input surface's own optimum at a thinly-sampled rate was noise (a 0.002-point "gain"
#: against a 1.11-point spread), so the honest per-rate check in `stage1_openloop.py` often
#: correctly reports "no current can be recommended" -- and this schedule is the sheet that fills
#: in the record so that stops being the answer. See `current_map_schedule.py` for the arithmetic.
#: ==========================================================================================
def _schedule_safety_predicate(es, *, ceilings):
    """A cheap `is_safe(left_mA, right_mA)` for the schedule: the two per-side `SafetyGP`s the
    open-loop search already fits, built here directly from the request's own design matrix so
    the schedule can be computed on every request, not only when `TwoStage` is asked for. Returns
    `(predicate_or_None, note)`; a fit failure degrades to no safety restriction beyond each
    side's own PI-stated ceiling, which the schedule always applies regardless."""
    try:
        from .routines import surrogate as _SUR
        safety_grid = _SUR.ParameterGrid(PLT.FREQ_GRID, S1.JOINT_AMP_GRID)
        sgp = {}
        for side in ("Left", "Right"):
            Xs, sev, sv, _meta = SC.safety_seed(
                es, f"amp_mA_{side}", freq_grid=PLT.FREQ_GRID, ceiling=(ceilings or {}).get(side),
                min_tolerated_h=S1.MIN_TOLERATED_H)
            sgp[side] = _SUR.SafetyGP(safety_grid, random_state=0).fit(Xs, sev, sv)
    except Exception as exc:                          # noqa: BLE001 -- degrade, never raise
        _log.info("StimOptimizer: schedule safety model unavailable (%r); ceiling only", exc)
        return None, f"the joint safety model could not be fitted ({exc!r}); only each side's own ceiling was applied"

    def is_safe(left_mA, right_mA, *, rate_hz):
        ok_l = bool(np.asarray(sgp["Left"].safe_mask(X=[[float(rate_hz), float(left_mA)]],
                                                      beta=PLT.BETA))[0])
        ok_r = bool(np.asarray(sgp["Right"].safe_mask(X=[[float(rate_hz), float(right_mA)]],
                                                       beta=PLT.BETA))[0])
        return ok_l and ok_r
    return is_safe, "the joint safety model fitted from this participant's own settings history"


def current_map_schedule_block(participant, *, es, in_force, ceilings) -> dict:
    """The `current_map_schedule` response block, never raising."""
    uid = str(getattr(participant, "uid", participant))
    try:
        left = dict((in_force or {}).get("Left") or {})
        right = dict((in_force or {}).get("Right") or {})
        rate_hz = left.get("rate_hz") if left.get("rate_hz") is not None else right.get("rate_hz")
        pwl, pwr = left.get("pulse_width_us"), right.get("pulse_width_us")
        if rate_hz is None or pwl is None or pwr is None:
            return CMS.unavailable_schedule(
                "the setting in force is not fully known (rate and both pulse widths are needed), "
                "so no schedule can be designed")
        cl = (ceilings or {}).get("Left"); cr = (ceilings or {}).get("Right")
        ceiling_left = cl[0] if cl else None
        ceiling_right = cr[0] if cr else None
        stratum = pd.DataFrame()
        if isinstance(es, pd.DataFrame) and len(es):
            need = {"freq_hz", "pw_us_Left", "pw_us_Right", "amp_mA_Left", "amp_mA_Right", "n"}
            if need.issubset(es.columns):
                m = (np.isclose(pd.to_numeric(es["freq_hz"], errors="coerce"), float(rate_hz))
                     & np.isclose(pd.to_numeric(es["pw_us_Left"], errors="coerce"), float(pwl))
                     & np.isclose(pd.to_numeric(es["pw_us_Right"], errors="coerce"), float(pwr)))
                stratum = es.loc[m]
        is_safe_raw, safety_note = _schedule_safety_predicate(es, ceilings=ceilings)
        is_safe = ((lambda l, r: is_safe_raw(l, r, rate_hz=rate_hz)) if is_safe_raw is not None
                  else None)
        block = CMS.build_schedule(
            rate_hz=rate_hz, pw_us_left=pwl, pw_us_right=pwr,
            ceiling_left_mA=ceiling_left, ceiling_right_mA=ceiling_right,
            in_force_left_mA=left.get("amplitude_mA"), in_force_right_mA=right.get("amplitude_mA"),
            existing_epochs_at_stratum=stratum, epochs_for_reporting_rate=es, is_safe=is_safe)
        block["safety_model_note"] = safety_note
        return _jsonable(block)
    except Exception as exc:                          # noqa: BLE001 -- adjunct card
        _log.exception("StimOptimizer: the current-map schedule could not be built for %s", uid)
        return CMS.unavailable_schedule(f"the schedule could not be built: {exc}")


def titration_plan_block(participant, *, in_force, screen, ceilings, hemispheres, es=None) -> dict:
    """The `titration_plan` response block (`titration_plan.plan_for_sides`), never raising.

    `es` (2026-09-14) is the request's own design matrix, used only to fit the joint safety model
    the "joint corners" block is restricted to (the same builder `current_map_schedule_block`
    already uses, `_schedule_safety_predicate`); `None` degrades to capping the corners at each
    side's own ceiling with no further safety restriction, named as such.
    """
    from . import titration_plan as _tp
    from .routines import percept_adaptive as _pa
    uid = str(getattr(participant, "uid", participant))
    try:
        pooled, pooled_note = _stored_table_as_stim_optimizer(POOLED_KIND, uid)
        runs, runs_note = _stored_table_as_stim_optimizer(RUN_POINTS_KIND, uid)
        try:
            from modules.ClosedLoopDeployment import post_ramp as _pr
        except ImportError:
            from ClosedLoopDeployment import post_ramp as _pr
        margin = _pr.margin_becomes_available(runs)
        lo, hi = _pa.ADAPTIVE_LFP_BAND_HZ
        sides = {}
        for side in hemispheres:
            side = str(side)
            f = dict((in_force or {}).get(side) or {})
            src = f.get("source") or "the settings stream"
            since = f.get("since_utc")
            in_force_src = (f"the setting in force on the {side} side, from the {src}"
                            + (f", since {since}" if since else ""))
            ceiling = (ceilings or {}).get(side)
            if ceiling is None:
                ceiling = SC.ceiling_for(uid, side)
            contact, how = _best_contact_for_side(
                screen, side, rate_hz=_tp.rate_to_hold(f.get("rate_hz"))["rate_hz"])
            rec = _tp.record_today_for_contact(pooled, runs, (contact or {}).get("channel"),
                                               lo_hz=lo, hi_hz=hi)
            rec["pooled_table_note"] = pooled_note
            rec["run_points_table_note"] = runs_note
            sides[side] = dict(
                rate_in_force_hz=f.get("rate_hz"), rate_source=in_force_src,
                pulse_width_us=f.get("pulse_width_us"), pulse_width_source=in_force_src,
                ceiling_mA=ceiling[0], ceiling_source=str(ceiling[1]),
                contact=contact, contact_source=how, record_today=rec)
        # THE JOINT CORNERS' SAFETY RESTRICTION (2026-09-14): the same per-side SafetyGP the home
        # current-map schedule already fits, at the session's own rate (the higher of the two
        # sides' held rates, so neither side's own adaptive minimum is understated). A fit
        # failure degrades to capping only, never raises.
        joint_is_safe = None
        joint_safety_note = "no design matrix was supplied, so the joint corners are capped at each side's own ceiling only"
        if isinstance(es, pd.DataFrame) and len(es):
            rl = (sides.get("Left") or {}).get("rate_in_force_hz")
            rr = (sides.get("Right") or {}).get("rate_in_force_hz")
            rl2 = _tp.rate_to_hold(rl)["rate_hz"] if "Left" in sides else None
            rr2 = _tp.rate_to_hold(rr)["rate_hz"] if "Right" in sides else None
            session_rate = (max(rl2, rr2) if (rl2 is not None and rr2 is not None)
                           else (rl2 if rl2 is not None else rr2))
            if session_rate is not None:
                is_safe_raw, joint_safety_note = _schedule_safety_predicate(es, ceilings=ceilings)
                if is_safe_raw is not None:
                    joint_is_safe = (lambda l, r, _f=is_safe_raw, _rt=session_rate:
                                     _f(l, r, rate_hz=_rt))
        block = _tp.plan_for_sides(sides, margin=margin, in_force=in_force,
                                   joint_is_safe=joint_is_safe)
        block["stored_tables"] = {"pooled": pooled_note, "run_points": runs_note}
        block["joint_corners"]["safety_model_note"] = joint_safety_note
        return _jsonable(block)
    except Exception as exc:                          # noqa: BLE001 -- adjunct card
        _log.exception("StimOptimizer: the titration plan could not be built for %s", uid)
        return {"available": False, "reason": f"the titration plan could not be built: {exc}"}


def closed_loop_readiness(participant, es, *, include=True, inputs=None, screen_out=None,
                          ceilings=None) -> dict:
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
        from . import pipeline as _pl
        from .routines import objective as _obj, percept_adaptive as _pa

        # ONE definition of the 18 bands (review S13, 2026-09-12): `bands=None` lets
        # `lfp_evidence.build_evidence` take every stored band that fits inside the adaptive
        # range, at the cache's own width, exactly as the two-stage path does. This used to
        # build the list by hand at a hard-coded 5 Hz width, so a change of the cache's band
        # width would have broken this panel while the two-stage path kept working.
        # `inputs` is the (sensed frame, epochs) pair the request built once for both this
        # screen and the two-stage path; None builds it here (2026-09-12).
        le = _pl.live_evidence(participant, amp_ceiling=_obj.AMP_HARD_LIMIT_MA, bands=None,
                               inputs=inputs)
        screen = le.screen if le.screen is not None else pd.DataFrame()
        if screen_out is not None:
            # The full screen frame for the titration plan (2026-09-12), which picks each side's
            # best contact off it; handed back through the caller's own dict so the readiness
            # payload itself is unchanged and the screen is built once.
            screen_out["screen"] = screen
        n_deployable = 0 if screen.empty else int(screen["deployable"].sum())
        # The contact pair in the page's form on every row and on the selected cell
        # (2026-09-12): `display_short` "L 0⁻2⁺" beside the raw key, from the one formatter.
        cells = _frame_records(
            screen[screen["n_responding"] > 0].sort_values("n_responding", ascending=False)
            if not screen.empty else screen, limit=20)
        for c in cells:
            c.update(sensing_display(c.get("channel")))
        selected = None
        if le.selected_key:
            selected = {"channel": le.selected_key[0], "hemisphere": le.selected_key[1],
                        "rate_hz": float(le.selected_key[2])}
            selected.update(sensing_display(le.selected_key[0]))
        return {
            "available": True,
            "ready": bool(le.selected is not None),
            "verdict": le.describe(),
            "selected": selected,
            "n_cells_screened": int(len(screen)),
            "n_cells_deployable": n_deployable,
            "amp_hard_limit_mA": _jsonable(_obj.AMP_HARD_LIMIT_MA),
            # The PI-stated SAFE ceiling per side (safety_ceiling.py, 4.5 mA on RCS08 since
            # 2026-09-14) is a different number from the module's hard cap above: the search and
            # the titration ladder obey the safe ceiling; the hard cap only bounds the search grid
            # and the readiness evidence. The page prints both so "current limit" is never read
            # as the safe one when it is not.
            "safe_ceiling_mA_by_side": ({h: _jsonable(v[0]) for h, v in (ceilings or {}).items()}
                                        if ceilings else None),
            "adaptive_window_hz": list(_pa.ADAPTIVE_LFP_BAND_HZ),
            "min_adaptive_rate_hz": _jsonable(_pa.MIN_ADAPTIVE_RATE_HZ),
            # Only the cells that responded at all: the full 50-row screen is mostly cells with no
            # response, which is not what a reader needs to see first.
            "responding_cells": cells,
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
