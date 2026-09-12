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

# A pain report is matched to the nearest recording whose timestamp falls within this many
# minutes. Was 15: the narrow window dropped 80 % of the otherwise-usable pool on RCS08, and with
# the pro_first direction the 60-minute window lifts coverage to 290 of 682 reports (42.5 %).
DEFAULT_MATCH_TOLERANCE_MIN = 60.0


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
        low = float(request_data.get("PercentileLow", 33.3333))
        high = float(request_data.get("PercentileHigh", 66.6667))
    except (TypeError, ValueError):
        low, high = 33.3333, 66.6667
    if not (0 <= low < high <= 100):
        low, high = 33.3333, 66.6667
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


def sweep_match_direction(request_data):
    """The discovery sweep's reading of `MatchDirection`: "prior", "nearest", else "pro_first".
    Deliberately NOT `bravo_service._forecast_match_direction`, which falls back to "prior" for the
    threshold-deployment view's causal-forecasting reading; collapsing the two would silently
    change one of their fallbacks."""
    request_data = request_data or {}
    _md = str(request_data.get("MatchDirection", "pro_first")).lower()
    return "prior" if _md == "prior" else ("nearest" if _md == "nearest" else "pro_first")


def allow_window_reuse_param(request_data):
    request_data = request_data or {}
    return str(request_data.get("AllowWindowReuse", "")).lower() in ("1", "true", "yes", "on")


def sweep_metric_param(request_data):
    """The section's own `SweepMetric`, else the page's `LabelMetric`, else the default; an
    unknown score falls back to the default the way `_resolve_biomarker_metric` does."""
    request_data = request_data or {}
    metric = request_data.get("SweepMetric") or request_data.get("LabelMetric") or DEFAULT_BIOMARKER_METRIC
    if metric not in {m["key"] for m in BIOMARKER_METRICS}:
        metric = DEFAULT_BIOMARKER_METRIC
    return metric


def sweep_settings_tag(*, label_metric, match_tolerance_min, match_direction, allow_window_reuse,
                       label_strategy, percentile_low, percentile_high):
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
    }


def sweep_settings_tag_from_request(request_data):
    """`sweep_settings_tag` for a request, through the same parsers the sweep uses."""
    rd = request_data or {}
    strategy, low, high = label_strategy_params(rd)
    return sweep_settings_tag(
        label_metric=sweep_metric_param(rd), match_tolerance_min=match_tolerance_param(rd),
        match_direction=sweep_match_direction(rd), allow_window_reuse=allow_window_reuse_param(rd),
        label_strategy=strategy, percentile_low=low, percentile_high=high)


def metric_label(key):
    return next((m["label"] for m in BIOMARKER_METRICS if m["key"] == key), str(key))
