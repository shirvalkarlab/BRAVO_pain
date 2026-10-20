"""Read-only standard short-form MPQ from a verified daily aggregate field map.

The daily form codes the fifteen standard descriptors 1/2/3, with an
unselected descriptor meaning none. The three additional descriptors are not
part of the standard score. Stored aggregates cannot establish completion or
validate individual item coding; this helper preserves the canonical row set.
"""
import math

SENSORY = tuple(name + "_s1_daily" for name in (
    "throbbing", "shooting", "stabbing", "sharp", "cramping", "gnawing",
    "hot_burning", "aching", "heavy", "tender", "splitting"))
AFFECTIVE = tuple(name + "_s1_daily" for name in (
    "tiring_exhausting", "sickening", "fearful", "cruel_punishing"))
METRICS = (
    ("mpq_standard_sensory_0_33", "Standard MPQ sensory (0–33)", [0, 33]),
    ("mpq_standard_affective_0_12", "Standard MPQ affective (0–12)", [0, 12]),
    ("mpq_standard_0_45", "Standard MPQ total (0–45)", [0, 45]),
)
RULE = "daily-standard-mpq-verified-aggregates-v1"


def _fields_match(actual, expected):
    return (isinstance(actual, list) and len(actual) == len(expected)
            and all(isinstance(item, str) for item in actual) and set(actual) == set(expected))


def _mapping_matches(binding):
    if not isinstance(binding, dict):
        return False
    metrics = binding.get("metric_labels")
    return (isinstance(metrics, dict)
            and binding.get("instruments") == ["stage_1_daily_surveys_vasnrsmpq"]
            and binding.get("timestamp_label") == "date_time_s1_daily"
            and _fields_match(metrics.get("mpq_sen"), SENSORY)
            and _fields_match(metrics.get("mpq_aff"), AFFECTIVE))


def _aggregate(value, maximum):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value != int(value) or not 0 <= value <= maximum:
        raise ValueError("Invalid standard MPQ aggregate")
    return int(value)


def derive(reports, binding):
    """Copy rows; add standard metrics only for an exact trusted server field map.

    Never join by timestamp: duplicate-time reports remain independent rows.
    One missing subscale means no selected items there only when the other
    subscale is observed. Both missing remain missing, never an invented zero.
    Invalid bounds/coding suppress all three standard scores for that row.
    """
    matched = _mapping_matches(binding)
    provenance = {"rule": RULE, "mapping_verified": matched, "derived_rows": 0,
                  "expanded_total_mapping_verified": matched and binding["metric_labels"].get("mpq_sum") == "mpq_s1_daily",
                  "missing_rows": 0, "invalid_rows": 0,
                  "completion_status_available": False, "item_level_validation_available": False,
                  "message": ("Standard MPQ is derived from the verified stored 11 sensory and 4 affective item aggregates; no rescaling. Canonical report selection is preserved. Completion status and individual item validation are unavailable in stored aggregate rows." if matched else
                              "Standard MPQ is unavailable because the stored aggregate item mapping is not verified. Legacy canonical scores are preserved.")}
    result = []
    for source in reports:
        row = {key: value for key, value in source.items() if key not in {m[0] for m in METRICS}}
        result.append(row)
        if not matched:
            continue
        try:
            sensory = _aggregate(row.get("mpq_sen"), 33)
            affective = _aggregate(row.get("mpq_aff"), 12)
        except ValueError:
            provenance["invalid_rows"] += 1
            continue
        if sensory is None and affective is None:
            provenance["missing_rows"] += 1
            continue
        sensory = 0 if sensory is None else sensory
        affective = 0 if affective is None else affective
        row.update(dict(zip((m[0] for m in METRICS), (sensory, affective, sensory + affective))))
        provenance["derived_rows"] += 1
    return result, provenance


def display_metrics(canonical, provenance):
    """Relabel only this display's verified expanded total, never its values.

    The shared Prasad metric registry retains its legacy range for compatibility.
    A verified daily form establishes the actual eighteen-item maximum of 54.
    """
    result = dict(canonical)
    result["metrics"] = [dict(metric) for metric in canonical.get("metrics", [])]
    for metric in result["metrics"]:
        if metric["key"] == "mpq_sum" and provenance["expanded_total_mapping_verified"]:
            metric.update(label="Expanded MPQ total (18 items, 0–54)", range=[0, 54])
    return result
