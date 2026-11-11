"""Service layer: the single entry point the BRAVO API calls for Closed-Loop Deployment.

Mirrors `modules/Biomarkers/bravo_service.run_for_participant` and
`modules/StimOptimizer/bravo_service.run_for_participant` — takes the request dict, pulls what it
needs from the platform database, runs the module, and returns a JSON-able dict. This module is the
one place in the package that resolves a participant from the ORM; `adapter.py` and everything under
it stay callable from a plain interpreter with frames in hand.

WHY THIS FILE EXISTS AT ALL, WRITTEN 2026-09-10. The other two analysis modules each had a
`bravo_service.py` and this one did not: the view resolved the participant itself and called
`adapter.report_for_participant` directly. That is not a naming quibble. It meant the module had no
single door, so the two things a door is for — saying what the module promises to return, and
noticing when it cannot — lived in the view instead, mixed in with permission checks.

AND THE NOTICING WAS THE PART THAT FAILED. The view wrapped the whole call in one
`except Exception` and answered HTTP 200 with `{"available": False, "reason": "deployment report
error: " + str(e)}`. That is a reasonable thing for a page to show. It is a terrible thing to be the
ONLY record, and on 2026-09-04 it became exactly that: a module-level import broke the entire
package, every request returned that HTTP 200, and nothing logged it. **It stayed broken for five
days and was found by reading code, not by anything reporting it.**

So the contract here is deliberately two-sided:

  * THE PAGE gets a plain sentence it can render, always, whatever happened.
  * THE LOG gets the exception with its traceback, always, whatever happened.

Neither substitutes for the other. A reason the page shows is seen by whoever is looking at that one
participant; a log line is seen by whoever is asking why something is wrong at all, and those are
rarely the same person at the same moment.

HONESTY CONTRACT. `run_for_participant` never raises. Every return carries `available`, and a False
answer carries a `reason` saying which step could not be taken -- never an empty payload that a
reader has to interpret as either "nothing applies here" or "something broke", which are different
conclusions.
"""
import logging as _logging

_log = _logging.getLogger(__name__)

try:                                                   # container path root
    from modules.ClosedLoopDeployment import adapter as _adapter
except ImportError:                                    # host test-suite path root
    from ClosedLoopDeployment import adapter as _adapter


#: What the view passes through, with the defaults the endpoint documents.
DEFAULT_HEMISPHERE = "Left"
DEFAULT_POWER_SCALE = "power_linear"                   # the device-parity scale of rule D11


def request_hemisphere(request_data):
    """The side the report is evaluated on, in this order: the request's own ``Hemisphere``; the
    first candidate's ``actuated_hemisphere``, then its ``sensing_hemisphere``; then the endpoint's
    documented default.

    WHY THE CANDIDATE COMES BEFORE THE DEFAULT (review C1, 2026-09-12). The page never sent
    ``Hemisphere``; the old line ``request_data.get("Hemisphere", DEFAULT_HEMISPHERE)`` therefore
    handed the adapter "Left" for every request, and the adapter used that side for the impedance,
    the capture amplitudes, the current-to-power and amplitude-to-pain slopes, the capture currents
    and the simulation -- for a band picked on a RIGHT contact too. A band's own side is a fact
    about the band; the default is only for a request that names no side anywhere.
    """
    rd = request_data or {}
    if rd.get("Hemisphere"):
        return rd["Hemisphere"]
    cands = rd.get("Candidates") or []
    c0 = cands[0] if cands and isinstance(cands[0], dict) else {}
    return c0.get("actuated_hemisphere") or c0.get("sensing_hemisphere") or DEFAULT_HEMISPHERE


def _participant_or_none(participant_uid):
    """Resolve the participant. The ORM import is deferred to call time for the same reason
    `adapter.report_for_participant` defers its sibling-module imports: at module import time the
    Django app registry may not be populated, and the host test suite has no Django at all."""
    from Server import models
    return models.Participant.find(uid=participant_uid)


def _request_scope():
    """The Biomarkers module's within-request scope (pain reports, recordings, tile key fetched once
    per request; speed-up item 4, 2026-09-25), or no scope where that module cannot be imported."""
    import contextlib
    try:
        from modules.Biomarkers import bravo_service as _bs
    except ImportError:
        try:
            from Biomarkers import bravo_service as _bs
        except Exception:                                  # noqa: BLE001 -- host runner, no Django
            return contextlib.nullcontext()
    except Exception:                                      # noqa: BLE001
        return contextlib.nullcontext()
    return _bs.pro_request_scope()


#: The saved Closed-Loop report (decision 423).
REPORT_KIND = "closed_loop_report"


def run_for_participant(request_data):
    """Build the Closed-Loop Deployment report for one participant, inside one request scope.

    A band's report then carries `threshold_comparison` (programmed now against candidate
    thresholds on the home record; `threshold_comparison.py`), worked out on read and never saved:
    it holds pain-score summaries (CLAUDE.md section 7 rule 5) and changes no threshold, verdict or
    gate. Neutral `BRAVO_THRESHOLD_COMPARISON=0`: not built."""
    with _request_scope():
        out = _run_for_participant(request_data)
        return _with_threshold_comparison(out, request_data)


def _with_threshold_comparison(out, request_data):
    """``out`` with `threshold_comparison` beside it (a shallow copy), for a band's available report;
    ``out`` itself under the neutral setting, for the grid alone, or when the report is not available."""
    try:
        from modules.ClosedLoopDeployment import threshold_comparison as _tc
    except ImportError:                                # pragma: no cover - host spelling
        from ClosedLoopDeployment import threshold_comparison as _tc
    rd = request_data or {}
    if (not _tc.ENABLED or not isinstance(out, dict) or out.get("available") is False
            or not rd.get("Candidates") or rd.get("ThreeSourcePooled") or rd.get("ClosedLoopSimulation")):
        return out
    import time as _time
    t0 = _time.perf_counter()
    try:
        block = _threshold_comparison(rd, out)
    except Exception as exc:                           # noqa: BLE001 - a label only; the report stands
        _log.exception("closed-loop: the threshold comparison failed for %s", rd.get("ParticipantId"))
        block = {"available": False, "reason": f"the threshold comparison could not be built: {exc!r}"}
    block["seconds"] = _time.perf_counter() - t0
    out = dict(out)
    out["threshold_comparison"] = block
    return out


def _programmed_adaptive(participant):
    """`threshold_comparison.programmed_adaptive` of the newest device export, remembered under that
    file's identity (the device-facts memo, its own key), so a new export is a miss."""
    from modules import DataCurator as _DC
    from modules.ClosedLoopDeployment import device_facts as _df, session_report_facts as _srf
    from modules.ClosedLoopDeployment import threshold_comparison as _tc
    sfs = _srf.session_report_files(participant)
    if not sfs:
        return {"available": False, "reason": "no device export on record"}
    newest = _srf.newest_by_stamp(sfs)
    key = ("threshold_comparison_programmed", str(participant.uid), str(newest.uid), str(newest.hashed or ""))
    return _df._memoised_active_group_facts(key, lambda: _tc.programmed_adaptive(_DC.loadPerceptJSON(newest)))


def _threshold_comparison(rd, report):
    """The `threshold_comparison` block for one band's report (see `threshold_comparison.py`)."""
    import numpy as np
    from modules.Biomarkers import bravo_service as bs
    from modules.Biomarkers.routines import availability as av, chronic_band_choice as cbc
    from modules.ClosedLoopDeployment import threshold_comparison as _tc
    uid = rd.get("ParticipantId")
    participant = _participant_or_none(uid)
    cand = (rd.get("Candidates") or [{}])[0] or {}
    pair = cbc._canon(cand.get("channel")) if cand.get("channel") is not None else None
    band = {"pair": pair, "centre_hz": cand.get("center_hz"), "side": request_hemisphere(rd)}
    th = report.get("threshold") or {}
    report_pair = {"upper": th.get("upper"), "lower": th.get("lower"), "rule": th.get("placement_rule")}
    ps_info = report.get("pain_score") or {}
    key = ps_info.get("key") or "nrs"
    label = ps_info.get("label") or key
    # the home record (chronic log) as C5 reads it, and each lead's own current
    chronic = bs._load_recordings(uid, bs.CHRONIC_TYPES)
    pdl = bs._load_recordings(uid, bs.POWERDOMAIN_TYPES)
    samples = cbc.chronic_samples_by_pair(chronic, pdl)
    schedules = _tc.frequency_schedules(chronic)
    currents = cbc.lead_currents(chronic)
    # the pain score the report is computed on, as the page's other pain readings take it
    req = {"ParticipantId": uid, "LabelMetric": key}
    if rd.get("IncludeClinicSheetRatings") is not None:
        req["IncludeClinicSheetRatings"] = rd["IncludeClinicSheetRatings"]
    pro = bs._load_pros(req, participant)
    if str(rd.get("IncludeClinicSheetRatings") or "") in ("1", "true", "True"):
        pro, _blk = bs._merge_clinic_sheet_ratings_into_pro_df(uid, key, key, pro, req)
    blended, metric, _parts = bs._resolve_biomarker_metric({"LabelMetric": key}, pro)
    ps = av.pain_series(blended, metric)
    design = _adapter.design_rule_if_stored(participant, cand, hemisphere=request_hemisphere(rd)) or {}
    block = _tc.comparison_block(
        programmed=_programmed_adaptive(participant), band=band, report_pair=report_pair,
        samples_by_pair=samples, schedules=schedules, lead_currents=currents,
        report_t=np.asarray(ps.get("t", []), float), report_y=np.asarray(ps.get("y", []), float),
        pain_label=label, design_table=design.get("table"))
    block["pain_score_key"] = metric
    return block


def _run_for_participant(request_data):
    """Build the Closed-Loop Deployment report for one participant. Never raises.

    Inputs, from `request_data`: `ParticipantId` (required), `Candidates` (list of dicts carrying at
    least `channel` and `center_hz`), optional `Hemisphere` and `PowerScale`, and `PainScore` (one
    of the Biomarkers heat maps' pain scores; every band-to-pain reading on the report is computed
    on it, NRS when none is sent, and the response's `pain_score` says which was used).

    Output: the adapter's report dict, which always carries `available` and, when that is False, a
    `reason`. A report built for a real participant also carries `cache_status`, so the page can
    state when the data behind it were last assembled.
    """
    participant_uid = (request_data or {}).get("ParticipantId")
    if not participant_uid:
        return {"available": False, "reason": "ParticipantId is required"}
    scale = (request_data or {}).get("PowerScale", DEFAULT_POWER_SCALE)
    if scale != DEFAULT_POWER_SCALE:
        # Linear is the only scale (D11); the log columns left the joined table on 2026-09-19
        # (decision 202). Refused here with a plain reason rather than as a logged exception.
        return {"available": False,
                "reason": (f"PowerScale must be {DEFAULT_POWER_SCALE!r}: the device thresholds linear "
                           f"band power and no other scale is computed (got {scale!r})")}

    try:
        participant = _participant_or_none(participant_uid)
    except Exception as exc:                           # noqa: BLE001
        _log.exception("closed-loop: could not resolve participant %s", participant_uid)
        return {"available": False,
                "reason": f"the participant could not be looked up: {exc!r}"}

    if participant is None:
        # Not an error and not logged as one: asking about a participant who is not there is an
        # ordinary thing for a client to do, and it is already visible in the response.
        return {"available": False, "reason": "participant not found"}

    # THE POOLED THREE-SOURCE VIEW ON ITS OWN. The page asks for this AFTER its first figures are
    # up (the PI, 2026-09-11: "prefetch the data after the first figures load"), so it must not
    # rebuild the report: it reads the two stored tables the last full report wrote and groups
    # them. Cheap, and never something the verdict waits for.
    if (request_data or {}).get("ThreeSourcePooled"):
        try:
            return _adapter.three_source_pooled_for_participant(participant)
        except Exception as exc:                       # noqa: BLE001
            _log.exception("closed-loop: the pooled three-source view failed for %s",
                           participant_uid)
            return {"available": False,
                    "reason": f"the pooled three-source view could not be built: {exc!r}"}

    # THE STORED SIMULATION ON ITS OWN (Phase 8): read back after the first figures, never built here.
    if (request_data or {}).get("ClosedLoopSimulation"):
        try:
            _cands = (request_data or {}).get("Candidates") or []
            return _adapter.closed_loop_simulation_for_participant(
                participant, _cands[0] if _cands else None,
                hemisphere=request_hemisphere(request_data))
        except Exception as exc:                       # noqa: BLE001
            _log.exception("closed-loop: the stored simulation could not be read for %s", participant_uid)
            return {"available": False,
                    "reason": f"the stored simulation could not be read: {exc!r}"}

    def _build():
        return _adapter.report_for_participant(
            participant, request_data,
            candidates=(request_data or {}).get("Candidates"),
            hemisphere=request_hemisphere(request_data),
            power_scale=(request_data or {}).get("PowerScale", DEFAULT_POWER_SCALE))

    try:
        # SAVED ON THE SERVER (decision 423): a report for a band is worked out once and served to
        # every request with the same inputs (`adapter.report_input_fingerprints` plus the code).
        # The band grid and the stored-results line are read fresh each time. The grid alone (no
        # band) is not saved. A failure to build the label builds the report as before.
        if not (request_data or {}).get("Candidates"):
            return _build()
        try:
            inputs = _adapter.report_input_fingerprints(participant, request_data)
        except Exception:                              # noqa: BLE001 - the report stands without it
            _log.warning("closed-loop: the saved-report label could not be built for %s",
                         participant_uid, exc_info=True)
            return _build()
        try:
            from modules.CacheStore import saved_answers as _saved, request_memory as _memory
        except ImportError:                            # pragma: no cover - host spelling
            from CacheStore import saved_answers as _saved, request_memory as _memory
        # remembered, so the server can work it out again when the data change (decision 435)
        _memory.remember(REPORT_KIND, participant_uid, request_data)
        # THE BAND GRID LEAVES A BAND'S REPORT (decision 431): the page reads the grid from its own
        # request (the one with no band), never from here, and re-reading it for a served report
        # cost about 1.8 s. The report still reads the grid while it is built (its direction check).
        def _build_without_grid():
            out = _build()
            if isinstance(out, dict):
                out.pop("band_sweep_grid", None)
            return out
        return _saved.serve_or_build(
            REPORT_KIND, participant_uid, inputs, _build_without_grid, writer="closed_loop",
            volatile=("cache_status",),
            refresh=lambda: {"cache_status": _adapter._cache_status_or_reason(participant)},
            root=_adapter._SHARED_CACHE_DIR_OVERRIDE)
    except Exception as exc:                           # noqa: BLE001
        # THE LINE THAT WAS MISSING FOR FIVE DAYS. `exception` rather than `warning`, so the
        # traceback goes with it: the failure this replaces was an ImportError raised at module
        # scope, and the name of the module that would not import is only in the traceback.
        _log.exception("closed-loop: the deployment report failed for %s", participant_uid)
        return {"available": False,
                "reason": f"the deployment report could not be built: {exc!r}"}


def stim_program(request_data):
    """The stimulation program the device runs today, for the Closed-Loop page's "Inherit current
    settings" (decision 467): each side's contacts, Amp, PW and closed-loop limits, the shared
    rate, and each lead's stored target name. Read from the newest export; never raises."""
    uid = (request_data or {}).get("ParticipantId")
    if not uid:
        return {"available": False, "reason": "ParticipantId is required"}
    try:
        from . import stim_program as _sp
        return _sp.current_program(uid)
    except Exception as exc:                           # noqa: BLE001
        _log.exception("closed-loop: the current stimulation program could not be read for %s", uid)
        return {"available": False, "reason": f"the current stimulation program could not be read: {exc!r}"}


def wiring_comparison(request_data):
    """The three sense-to-control wirings compared by simulation, for the wiring card (decision
    472; `wiring_simulation.py` says how). Never raises.

    Inputs: `ParticipantId`; `Bands` {"Left": {channel, center_hz, band_width_hz}, "Right": {...}},
    the band chosen on each side; `PainScore`; the matching settings and `StimProgram` exactly as
    the page sends them with its reports, so the four reports asked for here (each band on each
    stimulator) are the page's own requests and are served from the same saved answers.
    """
    rd = request_data or {}
    uid = rd.get("ParticipantId")
    bands = rd.get("Bands") or {}
    if not uid:
        return {"available": False, "reason": "ParticipantId is required"}
    if not all(isinstance(bands.get(s), dict) and bands[s].get("channel") and bands[s].get("center_hz") is not None
               for s in ("Left", "Right")):
        return {"available": False, "reason": "choose a band on each side to compare the three wirings"}
    try:
        with _request_scope():
            return _wiring_comparison(rd, uid, bands)
    except Exception as exc:                           # noqa: BLE001
        _log.exception("closed-loop: the wiring comparison failed for %s", uid)
        return {"available": False, "reason": f"the wiring comparison could not be built: {exc!r}"}


_PASS_THROUGH = ("ParticipantId", "PainScore", "PowerScale", "StimProgram")


def _wiring_comparison(rd, uid, bands):
    import time as _time
    import numpy as np
    import pandas as pd
    from . import wiring_simulation as W
    from . import three_source_response as _3src
    from . import amplitude_effect as _amp
    try:
        from modules.Biomarkers import bravo_service as bs
        from modules.Biomarkers.routines import availability as av
    except ImportError:                                # pragma: no cover - host spelling
        from Biomarkers import bravo_service as bs
        from Biomarkers.routines import availability as av
    t0 = _time.perf_counter()
    base = {k: v for k, v in rd.items() if k not in ("Bands", "Candidates", "Hemisphere")}
    base.setdefault("PowerScale", DEFAULT_POWER_SCALE)
    pain_score = rd.get("PainScore") or "nrs"

    # 1. Each band on each stimulator: its thresholds, current limits and the device's verdict.
    ctrls, pairings = {}, {}
    for band_side in W.SIDES:
        b = bands[band_side]
        for stim in W.SIDES:
            cand = {"channel": b["channel"], "center_hz": float(b["center_hz"]),
                    "band_width_hz": float(b.get("band_width_hz") or 5.0),
                    "sensing_hemisphere": band_side, "actuated_hemisphere": stim,
                    "rate_hz": None, "pulse_width_us": None, "threshold_mode": "dual"}
            if band_side != stim:
                cand["contralateral_pairing_acknowledged"] = True
            rep = _run_for_participant(dict(base, Hemisphere=stim, Candidates=[cand]))
            th = (rep or {}).get("threshold") or {}
            vd = (rep or {}).get("verdict_detail") or {}
            el = (rep or {}).get("eligibility") or {}
            refused_by = [r.get("rule_id") for r in el.get("failures", [])
                          if r.get("counts_toward_verdict") is not False]
            ok = all(th.get(k) is not None for k in ("upper", "lower", "amp_limit_low", "amp_limit_high"))
            ctrls[(band_side, stim)] = ({"upper": th["upper"], "lower": th["lower"],
                                         "amp_low_mA": th["amp_limit_low"], "amp_high_mA": th["amp_limit_high"]}
                                        if ok and rep.get("available") else None)
            pairings[f"{band_side}>{stim}"] = {
                "band_side": band_side, "stim_side": stim, "available": bool((rep or {}).get("available")),
                "device_allows": vd.get("device_eligible"), "refused_by": refused_by,
                "thresholds_placed": ok, "reason": (rep or {}).get("reason")}
    allowed = {}
    for w, drives in W.WIRINGS.items():
        vals = [pairings[f"{drives[c]}>{c}"]["device_allows"] for c in W.SIDES]
        allowed[w] = True if all(v is True for v in vals) else (False if any(v is False for v in vals) else None)

    # 2. Each band's 3 s pieces with both stimulators' current.
    loaded = {}
    series = {}
    for side in W.SIDES:
        b = bands[side]
        by_hem = {h: _adapter.simulation_inputs_for_participant(uid, contact=b["channel"],
                                                                centre_hz=float(b["center_hz"]),
                                                                hemisphere=h, loaded=loaded)
                  for h in W.SIDES}
        base_in = by_hem[side]
        t = np.asarray(base_in["t"], float)
        amp_other = dict(zip(np.asarray(by_hem[W.SIDES[1 - W.SIDES.index(side)]]["t"], float).tolist(),
                             np.asarray(by_hem[W.SIDES[1 - W.SIDES.index(side)]]["amp_obs"], float).tolist()))
        series[side] = {"t": t, "power": np.asarray(base_in["power"], float),
                        f"amp_{side}": np.asarray(base_in["amp_obs"], float),
                        "contact": b["channel"], "centre_used_hz": base_in.get("centre_used_hz"),
                        "absent_reason": base_in.get("absent_reason")}
        other = W.SIDES[1 - W.SIDES.index(side)]
        series[side][f"amp_{other}"] = np.array([amp_other.get(x, np.nan) for x in t.tolist()])
    for side in W.SIDES:
        if not len(series[side]["t"]):
            return {"available": False, "gates_nothing": True,
                    "reason": (f"no 3 s voltage-trace pieces on the {side.lower()} band "
                               f"({series[side]['absent_reason'] or 'none stored'})")}
    stretches, med = W.joint_stretches(series["Left"], series["Right"])

    # 3. The change in power per mA: own side from the stored pooled row, other side measured here.
    pooled = _adapter.pooled_shape_if_stored(uid)
    power = bs._load_recordings(uid, bs.POWERDOMAIN_TYPES)
    runs = _3src.find_single_side_runs_from_device(_3src.read_device_current(power)) if power else []
    k, k_source = {s: {} for s in W.SIDES}, {}
    for s in W.SIDES:
        b = bands[s]
        for c in W.SIDES:
            if c == s:
                row = _amp.pooled_row(pooled, b["channel"], float(b["center_hz"]))
                v = (row or {}).get("pooled_slope_per_mA")
                if v is not None and np.isfinite(float(v)):
                    k[s][c] = float(v)
                    k_source[f"{s}<{c}"] = {"slope_per_mA": float(v), "measured": True,
                                            "source": "stored pooled line across visits (decision 103)",
                                            "n": (row or {}).get("n"), "n_runs": None}
                    continue
            xs, ys, lab = W.settled_points(runs, c, series[s]["t"], series[s]["power"])
            est = W.cross_slope(xs, ys, lab)
            if c == s:
                est["source"] = est["source"].replace("the other side's", "this side's own")
            k[s][c] = est["slope_per_mA"]
            k_source[f"{s}<{c}"] = est

    # 4. The pain ratings, as the page's other pain readings take them.
    req = {"ParticipantId": uid, "LabelMetric": pain_score}
    for key in ("IncludeClinicSheetRatings",):
        if rd.get(key) is not None:
            req[key] = rd[key]
    pro = bs._load_pros(req)
    if str(rd.get("IncludeClinicSheetRatings") or "") in ("1", "true", "True"):
        pro, _blk = bs._merge_clinic_sheet_ratings_into_pro_df(uid, pain_score, pain_score, pro, req)
    ps = av.pain_series(pro, pain_score)
    rt = np.asarray(ps["t"], float)
    ry = np.asarray(ps["y"], float)
    rday = (pd.to_datetime(rt, unit="s", utc=True).tz_convert("America/Los_Angeles").strftime("%Y-%m-%d")
            .to_numpy() if rt.size else np.empty(0, dtype=object))

    # 5. One timing for all three: the participant's record-derived one.
    timing = (_adapter._timing_runs_for_simulation(uid, "Left", None).get("recommended") or {})
    out = W.compare(stretches, med, ctrls, k, rt, ry, rday, timing=timing.get("params") or {},
                    allowed=allowed)
    out.update({"available": True, "pairings": pairings, "response_per_mA": k_source,
                "timing_source": timing.get("source"), "pain_score": pain_score,
                "bands": {s: {"channel": bands[s]["channel"], "center_hz": float(bands[s]["center_hz"]),
                              "centre_used_hz": series[s]["centre_used_hz"]} for s in W.SIDES},
                "n_ratings_total": int(rt.size), "seconds": _time.perf_counter() - t0})
    return out
