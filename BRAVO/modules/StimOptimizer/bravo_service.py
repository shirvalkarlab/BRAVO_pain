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

import numpy as np
import pandas as pd

from . import adapter
from . import pipeline
from .routines import plots as PLT

_log = logging.getLogger(__name__)

DEFAULT_SITES = ("left_leg", "back")
DEFAULT_HEMISPHERES = ("Left", "Right")


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

    try:
        es = adapter.build_design_matrix(participant, request_data, washin_min=washin_min)
    except Exception as e:
        _log.exception("StimOptimizer: design matrix build failed for %s", uid)
        return {"available": False, "reason": f"could not build the design matrix: {e}"}
    if es is None or len(es) == 0:
        return {"available": False,
                "reason": "no exposure epochs carry usable pain reports for this participant",
                "washin_min": washin_min}

    horizon = "settings and pain reports as ingested at request time"
    if "t0" in es.columns:
        horizon = f"through {pd.to_datetime(es['t0']).max():%Y-%m-%d}"

    try:
        rep = pipeline.run(es, sites=sites, hemispheres=hemis,
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
            "optimum_resolved": bool(arm.surface_can_resolve_its_optimum())
                                if hasattr(arm, "surface_can_resolve_its_optimum") else None,
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
                entry["figures"] = _plotly_figures(ctx)
            except Exception as e:
                entry["figures"] = {}
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
    return {
        "available": True,
        "participant": uid,
        "design_matrix": design_matrix_summary(es),
        "manifest": _jsonable(rep.manifest),
        "summary": _frame_records(rep.summary),
        "arms": arms,
        "recommendation_supported": supported,
        "blockers": blockers,
        "washin_min": washin_min,
    }


def _blockers(rep, arms, observed_amp_range=None) -> list:
    """Plain-language reasons a parameter recommendation is withheld."""
    observed_amp_range = observed_amp_range or {}
    out = []
    if not any(a.get("optimum_resolved") for a in arms.values()):
        out.append("No arm can distinguish its own best setting from the setting currently in force: "
                   "for every arm the predicted gain is smaller than the posterior uncertainty at "
                   "that cell. The surfaces show where to look next, not what to program.")
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


def _plotly_figures(ctx) -> dict:
    """Plotly figure JSON for the browser. Never renders images server-side (no kaleido)."""
    import json as _json
    import plotly.io as pio
    out = {}
    for name, fn in (("posterior_surface", "fig1_posterior_surface"),
                     ("acquisition", "fig2_acquisition_decomposition"),
                     ("trajectory", "fig3_search_trajectory"),
                     ("dual_model", "fig4_dual_model"),
                     ("coverage", "fig5_coverage_map")):
        f = getattr(PLT, fn, None)
        if f is None:
            continue
        try:
            out[name] = _json.loads(pio.to_json(f(ctx)))
        except Exception as e:
            _log.debug("StimOptimizer: figure %s failed (%s)", fn, e)
    return out
