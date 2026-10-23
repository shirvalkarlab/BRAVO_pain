"""Every band's Closed-Loop requests, built exactly as the page builds them (the PI, 2026-10-06:
"Register ... redoing all 660 after each data change with the 10-minute refresh job"; decision 463).

WHY A COPY OF THE PAGE'S BUILDERS. A saved answer is filed under its whole request
(`CacheStore.saved_answers.label`), and the page builds its requests in the browser. To work out
every band's answers before anyone asks, the refresh job (`refresh_saved_answers`) needs the exact
bodies the page would send for each band on the band grid: the report, the summary, the ROC, the
month-by-month check and the band power (whose cut-point is the band's own ROC Youden point, so it
moves with every new pain report and is filled in per pass). This module is that copy, function for
function. It is pinned to the page by a shared fixture: the page test
`Client/src/views/Reports/ClosedLoopSim/allBandRequests.fixture.test.js` writes
`tests/fixtures/all_band_requests.json` from the page's own functions, and
`tests/test_all_band_requests.py` checks this copy against it, numbers included (the page's JSON
sends 5, never 5.0).

The page's builders it copies, by file: `useBandSweepGrid.biomarkerGridSettings`,
`BandSweepGridPanel.{gridCentres, refusedByRule, bandRecordFromGrid}`,
`inheritedMatching.matchingRequestKeys`, `candidateRequestParams.{requestParamsFromCandidate,
bandPainScore, summaryRequestParams, reportCandidateFromBand, rocSettings, eraSettings, lsbSettings}`,
`useDeploymentReport.deploymentReportBody`, `useDeploymentSummary.deploymentSummaryBody`,
`neighbourPrefetch.neighbourRequests`; and the defaults in `Biomarkers/matchingDefaults.js`.

THE SETTINGS. The page's requests carry the Biomarkers page's last-run matching settings, which
live in the reader's browser. `settings_from` takes them from the newest report request the page
sent (remembered by `CacheStore.request_memory`), else from the committed band's saved grid
settings, over the page's defaults; it says which.
"""
import json
import re

#: `useBandSweepGrid.GRID_SETTING_KEYS`, in order.
GRID_SETTING_KEYS = ["LabelMetric", "MatchToleranceMin", "MatchDirection", "AllowWindowReuse",
                     "LabelStrategy", "PercentileLow", "PercentileHigh", "IncludeClinicSheetRatings"]
#: `inheritedMatching.MATCHING_KEYS` and `SUMMARY_MATCHING_KEYS` (all but the direction).
MATCHING_KEYS = ["MatchToleranceMin", "MatchDirection", "AllowWindowReuse", "MaxPerRating",
                 "RefractoryMin", "IncludeClinicSheetRatings", "LabelStrategy", "PercentileLow",
                 "PercentileHigh"]
SUMMARY_MATCHING_KEYS = [k for k in MATCHING_KEYS if k != "MatchDirection"]
#: `painScores.PAIN_SCORE_OPTIONS` keys and `DEFAULT_PAIN_SCORE`.
PAIN_SCORE_KEYS = ["nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum", "composite_mpq_leftleg"]
DEFAULT_PAIN_SCORE = "nrs"
#: `biomarkerStateStore.defaultMatchingSettings()` (from `matchingDefaults.MATCHING_DEFAULTS`).
DEFAULT_SETTINGS = {"LabelMetric": "nrs", "LabelStrategy": "tertile", "PercentileLow": 33.3333,
                    "PercentileHigh": 66.6667, "MatchToleranceMin": 15, "MatchDirection": "nearest",
                    "AllowWindowReuse": False, "MaxPerRating": 3, "RefractoryMin": 2,
                    "MatchExtentSec": 30, "IncludeClinicSheetRatings": False}
_BOOL_KEYS = ("AllowWindowReuse", "IncludeClinicSheetRatings")
#: The committed band's saved grid settings (`grid_settings`) -> the page's request keys.
_GRID_SETTINGS_TO_KEYS = {"sweep_metric": "LabelMetric", "label_strategy": "LabelStrategy",
                          "percentile_low": "PercentileLow", "percentile_high": "PercentileHigh",
                          "match_tolerance_min": "MatchToleranceMin",
                          "match_direction": "MatchDirection",
                          "allow_window_reuse": "AllowWindowReuse",
                          "include_clinic_sheet_ratings": "IncludeClinicSheetRatings"}


def _js(o):
    """A value as the page's JSON carries it: a whole-valued number is written without ".0"."""
    if isinstance(o, dict):
        return {k: _js(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_js(v) for v in o]
    if isinstance(o, float) and o.is_integer():
        return int(o)
    return o


def _num(v):
    """JavaScript's `Number(v)` for the values these requests carry."""
    if v is None:
        return 0
    return float(v) if not isinstance(v, bool) else int(v)


def _flag(v):
    return "1" if v else ""


def settings_from(remembered, committed_grid_settings=None):
    """`(settings, source)`: the inherited matching settings, as the page holds them (request keys,
    booleans as booleans). From the newest remembered report request (`source` "page"), else from
    the committed band's grid settings ("committed band"), else the page's defaults ("defaults")."""
    s = dict(DEFAULT_SETTINGS)
    source = "defaults"
    for k_from, k_to in _GRID_SETTINGS_TO_KEYS.items():
        v = (committed_grid_settings or {}).get(k_from)
        if v is not None:
            s[k_to] = v
            source = "committed band"
    for row in remembered or []:
        if row.get("kind") != "closed_loop_report":
            continue
        body = row.get("body") or {}
        for k in MATCHING_KEYS:
            if k in body and body[k] is not None:
                s[k] = (body[k] in ("1", 1, True)) if k in _BOOL_KEYS else body[k]
        if body.get("PainScore"):
            s["LabelMetric"] = body["PainScore"]
        source = "page"
        break
    return s, source


def matching_request_keys(settings, keys=MATCHING_KEYS):
    """`matchingRequestKeys`: the settings under `keys`, booleans as "1" / ""."""
    out = {}
    for k in keys:
        v = (settings or {}).get(k)
        if v is None:
            continue
        out[k] = _flag(v) if isinstance(v, bool) else v
    return out


def grid_body(uid, settings, pain_score=None):
    """The band grid request (`useBandSweepGrid`: `{ParticipantId, Candidates: [], ...biomarkerGridSettings}`)."""
    settings = {**DEFAULT_SETTINGS, **(settings or {})}      # `loadMatchingRun`: the run over the defaults
    out = {"ParticipantId": uid, "Candidates": []}
    for k in GRID_SETTING_KEYS:
        v = (settings or {}).get(k)
        if v is None:
            continue
        out[k] = _flag(v) if isinstance(v, bool) else v
    metric = pain_score or (settings or {}).get("LabelMetric")
    if metric:
        out["LabelMetric"] = metric
        out["SweepMetric"] = metric
    return _js(out)


def _merged_centres(sweep):
    seen = []
    for r in list((sweep or {}).get("best_correlation_rows") or []) + list((sweep or {}).get("best_auc_rows") or []):
        if r is None or r.get("band_center_hz") is None:
            continue
        c = r["band_center_hz"]
        if c not in seen:
            seen.append(c)
    vals = []
    for c in seen:
        try:
            f = float(c)
        except (TypeError, ValueError):
            continue
        if f == f and f not in (float("inf"), float("-inf")):
            vals.append(f)
    return sorted(vals)


def _side_of(ch, sweep):
    if (sweep or {}).get("display_hemisphere"):
        return sweep["display_hemisphere"]
    if re.search("LEFT", str(ch), re.I):
        return "Left"
    if re.search("RIGHT", str(ch), re.I):
        return "Right"
    return None


def refused_channels(grid):
    """`refusedByRule`: the pairs the grid's sensing rule refuses today."""
    sweeps = (grid or {}).get("band_time_sweep") or {}
    by_side = ((grid or {}).get("sensing_rule") or {}).get("by_side")
    if not by_side:
        return set()
    out = set()
    for ch in sweeps:
        r = by_side.get(_side_of(ch, sweeps[ch]))
        if r and r.get("rule_applied") and r.get("allowed_channel") != ch:
            out.add(ch)
    return out


def band_record(grid, channel, centre):
    """`bandRecordFromGrid`."""
    s = ((grid or {}).get("band_time_sweep") or {}).get(channel) or {}
    return {"contact": channel, "center_freq_hz": centre,
            "bandwidth_hz": _num(s.get("band_width_hz") or 5.0),
            "hemisphere": _side_of(channel, s), "threshold_mode": "dual", "label": {},
            "grid_settings": (grid or {}).get("grid_settings") or None}


def band_pain_score(bc):
    """`bandPainScore(...).key`."""
    key = ((bc.get("label") or {}).get("pro_metric")
           or ((bc.get("grid_settings") or {}).get("sweep_metric")))
    return key if key in PAIN_SCORE_KEYS else DEFAULT_PAIN_SCORE


def _request_params_from_candidate(bc):
    gs = bc.get("grid_settings") or {}
    rp = {}
    if gs.get("sweep_metric"):
        rp["LabelMetric"] = gs["sweep_metric"]
    if gs.get("label_strategy"):
        rp["LabelStrategy"] = gs["label_strategy"]
    if gs.get("percentile_low") is not None:
        rp["PercentileLow"] = gs["percentile_low"]
    if gs.get("percentile_high") is not None:
        rp["PercentileHigh"] = gs["percentile_high"]
    if gs.get("match_tolerance_min") is not None:
        rp["MatchToleranceMin"] = gs["match_tolerance_min"]
    return rp


def summary_request_params(bc, include_sheets, pain, settings):
    """`summaryRequestParams`."""
    rp = {**_request_params_from_candidate(bc), **matching_request_keys(settings, SUMMARY_MATCHING_KEYS)}
    rp.pop("IncludeClinicSheetRatings", None)
    if pain:
        rp["LabelMetric"] = pain
    if include_sheets:
        rp["IncludeClinicSheetRatings"] = "1"
    return rp


def _band_fields(bc):
    c = bc.get("center_freq_hz")
    return {"Channel": bc.get("contact"), "CenterHz": None if c is None else _num(c),
            "BandWidthHz": _num(bc.get("bandwidth_hz") or 5.0)}


def report_body(uid, bc, pain, matching):
    """`deploymentReportBody` for `reportCandidateFromBand(bc)`, no hemisphere or scale given."""
    side = bc.get("hemisphere") or "Left"
    body = {"ParticipantId": uid, **(matching or {}), "Hemisphere": side, "PainScore": pain or "nrs",
            "PowerScale": "power_linear",
            "Candidates": [] if bc.get("contact") is None else [{
                "channel": bc["contact"], "center_hz": _num(bc.get("center_freq_hz")),
                "band_width_hz": _num(bc.get("bandwidth_hz") or 5.0),
                "sensing_hemisphere": bc.get("hemisphere") or None, "actuated_hemisphere": side,
                "rate_hz": None, "pulse_width_us": None, "threshold_mode": "dual"}]}
    return _js(body)


def summary_body(uid, bc, rp):
    """`deploymentSummaryBody` with match direction "prior" and no cut-point."""
    return _js({"ParticipantId": uid, "Channel": bc.get("contact"), "CenterHz": _num(bc.get("center_freq_hz")),
                "BandWidthHz": _num(bc.get("bandwidth_hz") or 5.0), "MatchDirection": "prior", **rp})


def lsb_body(template, cutpoint):
    """The band-power request for one cut-point (`lsbSettings` with `{threshold, matchDir: "prior"}`)."""
    out = dict(template)
    out["Cutpoint"] = None if cutpoint is None else float(cutpoint)
    return _js(out)


def all_band_requests(uid, grid, settings):
    """Every band on the grid the device allows: `[{channel, centre, report, summary, roc, era,
    lsb_template}]`, in the page's own order (contacts as the grid lists them, centres ascending)."""
    settings = {**DEFAULT_SETTINGS, **(settings or {})}      # `loadMatchingRun`: the run over the defaults
    sweeps = (grid or {}).get("band_time_sweep") or {}
    refused = refused_channels(grid)
    report_matching = matching_request_keys(settings, MATCHING_KEYS)
    include_sheets = bool(report_matching.get("IncludeClinicSheetRatings"))
    out = []
    for ch in sweeps:
        if ch in refused:
            continue
        for c in _merged_centres(sweeps[ch]):
            bc = band_record(grid, ch, c)
            pain = band_pain_score(bc)
            rp = summary_request_params(bc, include_sheets, pain, settings)
            fields = _band_fields(bc)
            out.append({
                "channel": ch, "centre": _js(c),
                "report": report_body(uid, bc, pain, report_matching),
                "summary": summary_body(uid, bc, rp),
                "roc": _js({"ParticipantId": uid, **fields, "MatchDirection": "prior", **rp}),
                "era": _js({"ParticipantId": uid, **fields, **rp}),
                "lsb_template": _js({"ParticipantId": uid, **fields, "MatchDirection": "prior",
                                     "Cutpoint": None, **rp}),
            })
    return json.loads(json.dumps(out))


# ---- registration with the refresh job, and the two steps it runs for a registered participant ----
#: Redis hash: participant -> "1" when every band is worked out ahead. Kept without expiry (Redis
#: keeps its data across restarts on Jetstream2, decision 457).
REGISTER_KEY = "bravo:saved_answer_all_bands"
#: The refresh job's kind for "band power at this band's own ROC cut-point".
LSB_FROM_ROC_KIND = "band_lsb_power_from_roc"


def _client():
    from modules.CacheStore import locks
    return locks._client()


def register(uid):
    """Work out every band ahead for `uid` at each refresh pass whose data changed."""
    _client().hset(REGISTER_KEY, str(uid), "1")


def unregister(uid):
    _client().hdel(REGISTER_KEY, str(uid))


def registered_participants():
    """Every registered participant. Never raises."""
    try:
        c = _client()
        return [k.decode() if isinstance(k, bytes) else str(k) for k in (c.hgetall(REGISTER_KEY) or {})] if c else []
    except Exception:                                          # noqa: BLE001 -- best effort
        return []


def registered(uid):
    return str(uid) in registered_participants()


def order_committed_first(bands, committed):
    """The committed band, then its neighbours on the same pair nearest first, then every other band
    in the grid's order (decision 464): the bands a reader is likeliest to open are ready first."""
    if not committed or committed.get("channel") is None or committed.get("centre") is None:
        return list(bands)
    ch, c = committed["channel"], float(committed["centre"])
    same = sorted((b for b in bands if b["channel"] == ch), key=lambda b: (abs(float(b["centre"]) - c), float(b["centre"])))
    return same + [b for b in bands if b["channel"] != ch]


def plan_for(uid):
    """`{bands, settings_source, n_refused, grid_available}` for one participant: the band grid worked
    out from the page's grid request (with the settings `settings_from` finds), then every band's
    requests. Run by the refresh job in one of its replay processes (it loads the recordings)."""
    from modules.CacheStore import request_memory
    from modules.Biomarkers import bravo_service as bs
    from modules.ClosedLoopDeployment import bravo_service as cl, chosen_band
    try:
        cur = chosen_band.current(uid) or {}
        bc = ((cur.get("record") or {}).get("band_candidate")) or {}
        gs = bc.get("grid_settings")
        committed = {"channel": bc.get("contact"), "centre": bc.get("center_freq_hz")}
    except Exception:                                          # noqa: BLE001 -- defaults then
        gs, committed = None, None
    settings, source = settings_from(request_memory.recent(uid), gs)
    out = cl.run_for_participant(grid_body(uid, settings)) or {}
    grid = bs.json_compliant_handler(out.get("band_sweep_grid") or {})
    if not grid or grid.get("available") is False:
        return {"bands": [], "settings_source": source, "n_refused": 0, "grid_available": False}
    return {"bands": order_committed_first(all_band_requests(uid, grid, settings), committed),
            "settings_source": source,
            "n_refused": len(refused_channels(grid)), "grid_available": True}


def replay_lsb_from_roc(body):
    """The band-power request the page sends after its ROC answers: at the ROC's own Youden
    cut-point (`neighbourPrefetch.prefetchPanels`). No cut-point, no request (the page sends none)."""
    from modules.Biomarkers import bravo_service as bs
    env = bs.band_deployment_roc(dict(body["roc"])) or {}
    roc = env.get("roc") or {}
    yd = (((roc.get("operating_points") or {}).get("youden")) or {}) if env.get("available") and roc.get("available") else {}
    if yd.get("threshold") is None:
        return {"available": False, "reason": "no cut-point from the band's ROC; the page sends none"}
    return bs.band_lsb_and_power(lsb_body(body["lsb_template"], yd["threshold"]))
