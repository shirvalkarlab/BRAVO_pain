"""The pain score and the matching and split settings a calibrated grid is built under: the
constants, the request parsers, and the one tag that names a stored grid by them.

Every parser reads its request through a variable spelled `request_data`, because
`Biomarkers/tests/test_stability_background_launch.py` reads the request KEYS each parser touches
off its source by that spelling, to prove the background stability run carries exactly the settings
the sweep reads. A different spelling here would hide a key from that guard.

WHY THIS IS ITS OWN FILE, 2026-09-11. `bravo_service` imports Django's models at import time, so
nothing that must also run in the host test suite (which does not configure Django) can import it.
The Closed-Loop Deployment module has to derive the SAME tag the Biomarkers writer stamps on each
stored grid, from the same request keys, through the same parsers -- otherwise the two pages read
different entries (decision 131). Keeping the parsers here, and having `bravo_service` import them
from here under the names it always used, means there is one copy and it needs no Django.

Nothing here reads a database or a report table. The metric resolution is the key-validation half
of `bravo_service._resolve_biomarker_metric` (the composite blend that function also does needs
the report table and does not change which KEY the grid is stored under).
"""
from __future__ import annotations

# THE STORED CROSS-SETTING-STABILITY GRID: its kind name and the rule its answers are computed
# under. ONE HOME since 2026-09-26: `bravo_service` (the writer) and the Closed-Loop page's reader
# (`ClosedLoopDeployment/adapter.py`) both import these, and the reader cannot import
# `bravo_service` (it needs Django), so they live here. Before, the reader carried pinned copies.
STABILITY_GRID_KIND = "biomarker_band_stability_grid"

# Bump when anything about how a point's answer is computed changes, so an entry built under the
# old rule is never served as if it carried the new one.
# v2 read decibels off the pooled detail (decision 204); v3 raw power; v4 (2026-09-24) the shared
# setup honours the clinic-sheet switch, so a sheets-on grid's answers are rebuilt with the sheets;
# v5 (2026-09-25, P-03) one pain report counted in one stimulation state and one week, and each
# state's odds ratio carries its interval; v6 (2026-09-25 night) the per-state standard errors,
# and so the "behaves the same" check, are clustered on the pain report.
STABILITY_GRID_RULE_VERSION = "v7_grid_own_pain_score"  # 2026-09-26: answers on the grid's own pain score (was NRS for SweepMetric-only requests); tablet clock since v6  # tablet clock (2026-09-26): every time from the tablet's clock, TabletClock.py

# THE STORED HEAT-MAP GRID ITSELF: its kind name and the rule it is built under. ONE HOME since
# decision 317 (2026-09-26), for the same reason as the stability grid's above: the Biomarkers
# writer (`bravo_service._BAND_SWEEP_RESPONSE_KIND`, `_BAND_SWEEP_RULE_VERSION`) and the other
# pages' readers (`ClosedLoopDeployment/adapter.py`: the "Choose a band" card and the Stim
# Optimizer's readiness table) both need them, and the readers cannot import `bravo_service`.
# Bump the rule when anything about how a grid's numbers are computed changes, so a grid built under
# the old rule is never served as if it carried the new one -- by the Biomarkers page (the rule is in
# its key) or by another page (the rule is on the sidecar, `grid_written_under_rule_in_force`).
# v24: every chance test is every other rotation once (decision 315); v23: correlation by recording
# source; v22: effective count on each cell; v21: outlier rule on raw power; v20: cell p-values,
# decision 188.
GRID_KIND = "biomarker_band_sweep"
GRID_RULE_VERSION = "v24_exact_rotation_null_tablet_clock"  # tablet clock (2026-09-26): every time from the tablet's clock, TabletClock.py
# The two raw inputs every grid names in its chain, in the order its key carries them: the saved
# 3-second tiles (`bravo_service._RAW_LSB_SHARED_KIND`) and the pain-report snapshot.
GRID_INPUT_KINDS = ("raw_lsb_tiles", "redcap_reports")

# Pain-score choices the page offers. `key` must be a column in the tidy report table (the
# composite is synthesised at analysis time from its two parts).
BIOMARKER_METRICS = [
    {"key": "nrs", "label": "NRS (0–10)"},
    {"key": "vas", "label": "Overall VAS"},
    {"key": "left_leg_vas", "label": "Left Leg VAS"},
    {"key": "back_vas", "label": "Back VAS"},
    {"key": "mpq_sum", "label": "MPQ Sum"},
    {"key": "composite_mpq_leftleg", "label": "Composite (MPQ + Left Leg VAS)"},
]
DEFAULT_BIOMARKER_METRIC = "nrs"
COMPOSITE_METRIC = "composite_mpq_leftleg"
COMPOSITE_PARTS = ("mpq_sum", "left_leg_vas")

# How the pain score is split into low and high for the AUC. "tertile" keeps the lowest and
# highest thirds and drops the middle (the best detector target on RCS08); "median" keeps every
# report at a 50/50 split; "kmeans" is the legacy two-cluster notebook labeler.
BINARIZATION_STRATEGIES = [
    {"key": "tertile", "label": "Tertile (low/high, drop middle)"},
    {"key": "percentile", "label": "Percentile (adjustable cuts)"},
    {"key": "median",  "label": "Median split"},
    {"key": "kmeans",  "label": "KMeans (legacy)"},
]
DEFAULT_BINARIZATION = "tertile"

# THE MATCHING DEFAULTS, ONE HOME (decision 331, the PI's ruling of 2026-09-26). Every page and
# every offline analysis that means "the default matching" reads these; the Biomarkers page's
# constants block (`Client/src/views/Reports/Biomarkers/matchingDefaults.js`) carries the same
# values and a page test (`Client/src/views/Reports/Biomarkers/matchingDefaults.test.js`) fails if
# the two disagree.
#
# The window: how far either side of a pain report a band-power measurement may lie and still be
# paired with it, in minutes. 15 since decision 331, measured on RCS08 on the tablet clock
# (`artifacts/analysis_2026-09-26_json_time_fields_and_matching.md`, Part 2): 15 minutes keeps
# 97-98% of the real PSD matches and 85-88% of the real TD matches; 60 minutes (the default from
# 2026-06-28 to 2026-09-26) added almost nothing real and about tripled the matches a report moved
# to a neighbouring day also finds; 5 minutes lost 7-26% of the real PSD matches and nearly 40% of
# the real TD ones. The clock error left after decision 328 (seconds, at most about 5 minutes) is
# well inside it.
DEFAULT_MATCH_TOLERANCE_MIN = 15.0
# Either side of the report: the remote presses fall before and after a report about equally (242
# and 234 reports within 5 minutes), so "prior" (the recording must come first) is not the default.
# Of the two two-sided choices, "nearest" (each recording pairs with the report nearest it, either
# side) since decision 331, was "pro_first" (each report claims its nearest recordings). In the heat
# maps the two are the same rule (their matcher treats only "prior" differently). Where they
# differ -- the all-band scan, the deployment summary and the stability test -- "nearest" is the
# one that counts one press once: the minimum gap between the samples one report keeps applies
# under it and not under "pro_first". Measured on RCS08 (NRS, 15 minutes, cap 3, gap 2 min, the
# pooled matcher behind the summary and the stability test): under "pro_first" 3 reports kept two
# TD rows less than 30 s apart on one contact pair (5 such pairs), under "nearest" none; and
# "nearest" pairs as many reports (380 against 377; 712 report-and-pair groups against 706). Neither
# lets one recording count for two reports.
DEFAULT_MATCH_DIRECTION = "nearest"
# One stretch of recording answers one report (no reuse): a PSD snapshot, one press of her remote,
# and a 3-second TD piece each count for the one report nearest them, never for two.
DEFAULT_ALLOW_WINDOW_REUSE = False
# The all-band scan's, the deployment summary's and the stability test's cap per report and minimum
# gap between the samples one report keeps. NO MEASURED BASIS for either value (decision 331 did not
# measure them); kept at their values since 2026-06-28. The gap is what keeps two overlapping
# pieces of one press out of one report under the default direction above ("pro_first" ignores it).
DEFAULT_MAX_PER_RATING = 3
DEFAULT_REFRACTORY_MIN = 2.0
# How much TD signal a report's value is the median of, in seconds (the all-band scan only; the
# heat maps have it as their own axis). Kept at 30 s, no new measurement.
DEFAULT_MATCH_EXTENT_SEC = 30.0
# The clinic and at-home sheets' ratings: out unless asked for (decision 186).
DEFAULT_INCLUDE_CLINIC_SHEET_RATINGS = False
# The high / low split's cuts, for "tertile" and "percentile".
DEFAULT_PERCENTILE_LOW = 33.3333
DEFAULT_PERCENTILE_HIGH = 66.6667


def matching_defaults():
    """The matching and split defaults as the request keys the pages send, for the page that
    serves them and for the test that pins the page's copy."""
    return {"LabelMetric": DEFAULT_BIOMARKER_METRIC, "LabelStrategy": DEFAULT_BINARIZATION,
            "PercentileLow": DEFAULT_PERCENTILE_LOW, "PercentileHigh": DEFAULT_PERCENTILE_HIGH,
            "MatchToleranceMin": DEFAULT_MATCH_TOLERANCE_MIN,
            "MatchDirection": DEFAULT_MATCH_DIRECTION,
            "AllowWindowReuse": DEFAULT_ALLOW_WINDOW_REUSE,
            "MaxPerRating": DEFAULT_MAX_PER_RATING, "RefractoryMin": DEFAULT_REFRACTORY_MIN,
            "MatchExtentSec": DEFAULT_MATCH_EXTENT_SEC,
            "IncludeClinicSheetRatings": DEFAULT_INCLUDE_CLINIC_SHEET_RATINGS}


def matching_words(tol_min=None):
    """The window in words, for sentences that state it: "15-minute" by default."""
    v = DEFAULT_MATCH_TOLERANCE_MIN if tol_min is None else float(tol_min)
    return f"{v:g}-minute"


def label_strategy_params(request_data):
    """(label_strategy, low_pct, high_pct). `LabelStrategy` selects the labeler (default
    'tertile'); `PercentileLow`/`PercentileHigh` override the cuts. Unknown strategies and
    unusable cuts fall back to the defaults."""
    request_data = request_data or {}
    strat = (request_data.get("LabelStrategy") or DEFAULT_BINARIZATION)
    valid = {s["key"] for s in BINARIZATION_STRATEGIES} | {"percentile", "cutoff"}
    if strat not in valid:
        strat = DEFAULT_BINARIZATION
    try:
        low = float(request_data.get("PercentileLow", DEFAULT_PERCENTILE_LOW))
        high = float(request_data.get("PercentileHigh", DEFAULT_PERCENTILE_HIGH))
    except (TypeError, ValueError):
        low, high = DEFAULT_PERCENTILE_LOW, DEFAULT_PERCENTILE_HIGH
    if not (0 <= low < high <= 100):
        low, high = DEFAULT_PERCENTILE_LOW, DEFAULT_PERCENTILE_HIGH
    return strat, low, high


def match_tolerance_param(request_data):
    """`MatchToleranceMin` as a positive number of minutes. A missing key uses the default; an
    explicit 0, negative or non-numeric value disables time-matching (None)."""
    request_data = request_data or {}
    if "MatchToleranceMin" not in request_data:
        return DEFAULT_MATCH_TOLERANCE_MIN
    try:
        v = float(request_data.get("MatchToleranceMin"))
    except (TypeError, ValueError):
        return DEFAULT_MATCH_TOLERANCE_MIN
    return v if v > 0 else None


def per_rating_cap_params(request_data):
    """(max_per_rating, refractory_min): how many samples one pain report may keep per contact pair
    (`MaxPerRating`, 1..50) and the minimum gap in minutes between them (`RefractoryMin`, 0..720);
    a missing or unreadable value takes the default, an out-of-range one is clamped. One home since
    decision 331; `bravo_service._per_rating_cap_params` delegates here."""
    request_data = request_data or {}

    def _num(key, default, lo, hi, cast):
        if key not in request_data:
            return default
        try:
            v = cast(request_data.get(key))
        except (TypeError, ValueError):
            return default
        return min(hi, max(lo, v))

    return (_num("MaxPerRating", DEFAULT_MAX_PER_RATING, 1, 50, lambda x: int(round(float(x)))),
            _num("RefractoryMin", DEFAULT_REFRACTORY_MIN, 0.0, 720.0, float))


#: The request keys that carry the matching and split settings from the Biomarkers page to every
#: request that matches pain reports to recordings (decision 331). The pain score is not among them:
#: each page names it in its own key (`LabelMetric`, `SweepMetric`, the Closed-Loop `PainScore`).
MATCHING_REQUEST_KEYS = ("MatchToleranceMin", "MatchDirection", "AllowWindowReuse", "MaxPerRating",
                         "RefractoryMin", "IncludeClinicSheetRatings", "LabelStrategy",
                         "PercentileLow", "PercentileHigh")


def matching_applied(request_data, *, direction_reader=None):
    """The matching and split settings a request is answered under, through the same parsers the
    Biomarkers routines use: the echo a page compares with what it asked for (decision 331).
    `direction_reader` is the caller's own direction parser where it differs from the sweep's."""
    rd = request_data or {}
    strategy, low, high = label_strategy_params(rd)
    cap, gap = per_rating_cap_params(rd)
    tol = match_tolerance_param(rd)
    return {"match_tolerance_min": None if tol is None else float(tol),
            "match_direction": (direction_reader or sweep_match_direction)(rd),
            "allow_window_reuse": allow_window_reuse_param(rd),
            "max_per_rating": int(cap), "refractory_min": float(gap),
            "include_clinic_sheet_ratings": include_clinic_sheet_ratings_param(rd),
            "label_strategy": strategy, "percentile_low": float(low), "percentile_high": float(high)}


def sweep_match_direction(request_data):
    """The discovery sweep's reading of `MatchDirection`: "prior", "nearest", else "pro_first".
    Deliberately NOT `bravo_service._forecast_match_direction`, which falls back to "prior" for the
    threshold-deployment view's causal-forecasting reading; collapsing the two would silently
    change one of their fallbacks."""
    request_data = request_data or {}
    _md = str(request_data.get("MatchDirection", DEFAULT_MATCH_DIRECTION)).lower()
    return "prior" if _md == "prior" else ("nearest" if _md == "nearest" else "pro_first")


def forecast_match_direction(request_data):
    """The direction reading of the band-validation endpoints (the deployment summary, its ROC and
    the stability test): "pro_first" (also "pro-first", "pro"), "nearest", else "prior" -- an
    unrecognised value falls back to the causal "prior", unlike `sweep_match_direction`. A missing
    key takes the default. One home since decision 331 (`bravo_service._forecast_match_direction`
    delegates here), so the Closed-Loop report can echo what the stability card used."""
    _md = str((request_data or {}).get("MatchDirection", DEFAULT_MATCH_DIRECTION)).lower()
    if _md in ("pro_first", "pro-first", "pro"):
        return "pro_first"
    if _md == "nearest":
        return "nearest"
    return "prior"


def allow_window_reuse_param(request_data):
    request_data = request_data or {}
    return str(request_data.get("AllowWindowReuse", "")).lower() in ("1", "true", "yes", "on")


def include_clinic_sheet_ratings_param(request_data):
    """Whether the clinic and at-home sheets' scores are pooled into the heat maps as extra ratings
    (decision 186). OFF unless the request says so: the sheet steps were taken while current was
    being stepped on purpose, and a reader should choose to look at the heat maps that way."""
    # Spelled `request_data.get(...)` so the whitelist guard in
    # `test_stability_background_launch.py` can read the key off this source (decision 131's rule).
    value = request_data.get("IncludeClinicSheetRatings", "") if request_data else ""
    return str(value).lower() in ("1", "true", "yes", "on")


def sweep_metric_param(request_data):
    """The section's own `SweepMetric`, else the page's `LabelMetric`, else the default; an
    unknown score falls back to the default the way `_resolve_biomarker_metric` does."""
    request_data = request_data or {}
    metric = request_data.get("SweepMetric") or request_data.get("LabelMetric") or DEFAULT_BIOMARKER_METRIC
    if metric not in {m["key"] for m in BIOMARKER_METRICS}:
        metric = DEFAULT_BIOMARKER_METRIC
    return metric


def adjust_for_stim_current_param(request_data):
    """Whether the grid also reports each cell's correlation with the stimulation current taken out.

    OFF unless the request says otherwise (the PI, 2026-09-22: the adjusted grid sits behind a
    switch, the plain grid the default). The adjusted value never selects a band or moves a verdict;
    it is reported beside the plain one, descriptively.
    """
    return str((request_data or {}).get("AdjustForStimCurrent", "")).lower() in ("1", "true", "yes", "on")


def sweep_settings_tag(*, label_metric, match_tolerance_min, match_direction, allow_window_reuse,
                       label_strategy, percentile_low, percentile_high,
                       include_clinic_sheet_ratings=False):
    """The settings a stored grid was built under, as one normalised, JSON-safe dict.

    WHY, 2026-09-11. The store keeps up to twelve grids per participant (decision 107), one per
    pain score and per combination of matching and split settings, and the Closed-Loop Deployment
    page's "Choose a band" card read the NEWEST of them whatever it was built under, while the
    Biomarkers page shows the one for its own controls; the two disagreed whenever the daily
    precompute had written another score last. The tag is written into each grid's sidecar
    (`extra["sweep_settings"]`) and the Closed-Loop reader matches on it, so both pages read the
    same entry; it is also what that card prints.
    """
    return {
        "sweep_metric": str(label_metric),
        "match_tolerance_min": (None if match_tolerance_min is None else float(match_tolerance_min)),
        "match_direction": str(match_direction),
        "allow_window_reuse": bool(allow_window_reuse),
        "label_strategy": str(label_strategy),
        "percentile_low": float(percentile_low),
        "percentile_high": float(percentile_high),
        "include_clinic_sheet_ratings": bool(include_clinic_sheet_ratings),
    }


def sweep_settings_tag_from_request(request_data):
    """`sweep_settings_tag` for a request, through the same parsers the sweep uses."""
    rd = request_data or {}
    strategy, low, high = label_strategy_params(rd)
    return sweep_settings_tag(
        label_metric=sweep_metric_param(rd), match_tolerance_min=match_tolerance_param(rd),
        match_direction=sweep_match_direction(rd), allow_window_reuse=allow_window_reuse_param(rd),
        label_strategy=strategy, percentile_low=low, percentile_high=high,
        include_clinic_sheet_ratings=include_clinic_sheet_ratings_param(rd))


def default_settings_keep_group(tag, adjust_for_stim_current=False):
    """The keep group a grid's sidecar names when it was built at the daily default settings, else
    None (the PI, 2026-09-26: keep the daily-default grid on disk).

    The store keeps twelve grids per participant, oldest out first, and a reader working at other
    settings writes grids faster than the daily pass: on RCS08 all twelve kept were at the Biomarkers
    page's settings, so the default-settings grid the Stim Optimizer reads on every request had aged
    out and was rebuilt each time (decision 317, 10.4-10.7 s). The store keeps the newest entry of
    each group whatever else is written (`CacheStore.store._sweep_superseded`). One group per pain
    score, and the grid with the current taken out apart from the plain one, since each is read on
    its own. Only the defaults are grouped, or the protection would keep everything.
    """
    if not isinstance(tag, dict) or not tag.get("sweep_metric"):
        return None
    if tag != sweep_settings_tag_from_request({"SweepMetric": tag["sweep_metric"]}):
        return None
    group = f"default_settings:{tag['sweep_metric']}"
    return group + (":current_adjusted" if adjust_for_stim_current else "")


def metric_label(key):
    return next((m["label"] for m in BIOMARKER_METRICS if m["key"] == key), str(key))


def grid_signature(participant_uid, tiles_key, report_key, label_metric, settings, *,
                   rule_version=GRID_RULE_VERSION):
    """The store signature of one heat-map grid: the ONE assembly of its key (decision 317).

    `bravo_service._band_sweep_signature` builds every grid's key through this, and
    `grid_written_under_rule_in_force` rebuilds a key through it to recognise a grid written before
    sidecars named their rule, so the two cannot drift apart. `settings` is the dict of every
    setting the sweep ran under (`band_time_sweep_for_participant`'s `sweep_settings`). The imports
    are deferred so reading the settings tag never pays for the arithmetic module.
    """
    from . import analytics, band_results_tables
    return (GRID_KIND, str(rule_version), band_results_tables.RULE_VERSION,
            str(participant_uid), tiles_key, report_key, str(label_metric),
            tuple(sorted((k, v) for k, v in settings.items())),
            tuple(float(s) for s in analytics.BAND_TIME_SWEEP_SECONDS),
            float(analytics.BAND_TIME_SWEEP_WIDTH_HZ),
            float(analytics.BAND_TIME_SWEEP_CENTER_LO_HZ),
            float(analytics.BAND_TIME_SWEEP_CENTER_HI_HZ),
            int(analytics.BAND_TIME_SWEEP_N_PERM), int(analytics.BAND_TIME_SWEEP_N_BOOT), 0)


def _key_settings_from_sidecar(extra):
    """The settings dict of a grid's key, rebuilt from what its sidecar records: the settings tag
    and the current-adjustment switch. Three settings are not on the sidecar and are taken at the
    values every page sends, which are the parsers' defaults: the outlier rule's multiple and scale,
    and the inline stability column (off). A grid built with any other value gets a different key
    and is not recognised -- a reader can only under-report, never serve an unknown rule."""
    from . import analytics
    tag = extra.get("sweep_settings") or {}
    tol_min = tag.get("match_tolerance_min")
    return {
        "eligibility_radius_seconds": (float(tol_min) * 60.0 if tol_min
                                       else float(max(analytics.BAND_TIME_SWEEP_SECONDS))),
        "allow_window_reuse": bool(tag.get("allow_window_reuse")),
        "label_strategy": tag.get("label_strategy"),
        "percentile_low": float(tag.get("percentile_low")),
        "percentile_high": float(tag.get("percentile_high")),
        "outlier_n_mad": float(analytics.OUTLIER_N_MAD),
        "outlier_scale": analytics.OUTLIER_SCALE,
        "match_direction": tag.get("match_direction"),
        "include_cross_setting_stability": False,
        "include_clinic_sheet_ratings": bool(tag.get("include_clinic_sheet_ratings")),
        "adjust_for_stim_current": bool(extra.get("adjust_for_stim_current", False)),
    }


def grid_written_under_rule_in_force(meta):
    """Whether the stored grid this sidecar describes was written under `GRID_RULE_VERSION`.

    WHY (decision 317, 2026-09-26). The rule is inside a grid's key, which is a hash, so the
    Biomarkers page never serves an older-rule grid; but the Closed-Loop card and the Stim Optimizer
    find a grid by its settings tag, and went on serving a grid built under an older rule under any
    settings the Biomarkers page had not rebuilt -- the fault decision 293(b) fixed for the stability
    answers. A sidecar written since then names its rule (`extra["rule_version"]`) and is read by it.
    One written before names none: its key is rebuilt from what the sidecar records (its two inputs'
    keys, its settings tag, its switch) under the rule in force, and it counts only if the rebuilt
    key is its own. Anything that cannot be rebuilt counts as not in force. Never raises.
    """
    try:
        meta = meta or {}
        extra = meta.get("extra") or {}
        if "rule_version" in extra:
            return extra.get("rule_version") == GRID_RULE_VERSION
        inputs = {p.get("kind"): p.get("key") for p in (meta.get("provenance") or [])
                  if isinstance(p, dict)}
        tiles_key, report_key = (inputs.get(k) for k in GRID_INPUT_KINDS)
        tag = extra.get("sweep_settings") or {}
        if not (tiles_key and report_key and tag.get("sweep_metric") and meta.get("signature_key")):
            return False
        try:
            from modules.CacheStore import store as _store
        except ImportError:                                     # host suite: modules/ is the root
            from CacheStore import store as _store
        sig = grid_signature(meta.get("participant_uid"), tiles_key, report_key,
                             tag["sweep_metric"], _key_settings_from_sidecar(extra))
        return _store.signature_key(sig) == meta.get("signature_key")
    except Exception:                                           # noqa: BLE001
        return False
