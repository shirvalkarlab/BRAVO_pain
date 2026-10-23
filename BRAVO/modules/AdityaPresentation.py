"""Read-only presentation adapters; Prasad services remain the scientific authority.

Optional private JSON at BRAVO_ADITYA_PRESENTATION_METADATA has schema_version=1,
participants keyed by database uid. Each entry must have reviewed=true and revision.
Only reviewed display context belongs there; never credentials or raw source paths.
Home eligibility is explicit half-open UTC home_intervals [{start,end}], reconciled
with the authoritative clinic schedule by the reviewer. An optional reviewed
home_continuity policy labels later observations as assumed home between documented
sessions; it does not extend historical eligibility or establish device activation.
No nearest-setting fill, new importer, or private cache is introduced here.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
import math
import os
import re
from zoneinfo import ZoneInfo

VERSION = "prasad-presentation-v5-home-continuity"
PACIFIC = ZoneInfo("America/Los_Angeles")
ALIASES = {"nrs": "nrs_intensity", "vas": "vas_intensity",
           "left_leg_vas": "left_leg_vas_intensity"}


def finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def read_context(participant_uid):
    """An administrator-configured local input, never a client-supplied filename."""
    path = os.environ.get("BRAVO_ADITYA_PRESENTATION_METADATA")
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported presentation metadata schema")
    entry = document.get("participants", {}).get(str(participant_uid), {})
    if not entry.get("reviewed") or not entry.get("revision"):
        return {}
    # Explicit allowlist prevents returning arbitrary private metadata to browsers.
    allowed = ("revision", "phases", "visit_days", "home_intervals", "comparisons",
               "home_transitions", "home_unknown_intervals", "neural_scope", "neural_observation_scope", "home_continuity",
               "program_mode_evidence")
    context = {key: deepcopy(entry[key]) for key in allowed if key in entry}
    neural_scope(context)
    neural_observation_scope(context)
    home_continuity_policy(context)
    return context


def neural_scope(context):
    """Validate optional display coverage; it never supplies or extends eligibility."""
    if "neural_scope" not in context:
        return None
    scope = context["neural_scope"]
    if not isinstance(scope, dict) or set(scope) != {"coverage_start", "coverage_end", "description"}:
        raise ValueError("Invalid neural display scope")
    start, end = scope["coverage_start"], scope["coverage_end"]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)) or start >= end:
        raise ValueError("Invalid neural coverage bounds")
    description = scope["description"]
    if not isinstance(description, str) or not description.strip() or len(description) > 500 or any(ord(c) < 32 for c in description):
        raise ValueError("Invalid neural coverage description")
    for interval in context.get("home_intervals", []):
        if not isinstance(interval, dict) or set(interval) != {"start", "end"}:
            raise ValueError("Invalid scoped neural interval")
        low, high = interval["start"], interval["end"]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (low, high)) or not start <= low < high <= end:
            raise ValueError("Neural interval lies outside reviewed coverage")
    return {"coverage_start": start, "coverage_end": end, "description": description.strip()}


def window_coverage(window, scope):
    """Describe overlap only; retain the original requested period and data."""
    low = max(window["start"], scope["coverage_start"])
    high = min(window["end"], scope["coverage_end"])
    if low >= high:
        return {"status": "outside", "start": None, "end": None}
    status = "covered" if low == window["start"] and high == window["end"] else "partial"
    return {"status": status, "start": low, "end": high}


def unavailable(topic):
    return {"available": False, "message": f"Reviewed {topic} unavailable.",
            "metrics": [], "episodes": []}


def pain_timeline(canonical, context=None, observations=()):
    context = context or {}
    metrics, clinic = [], {}
    for metric in canonical.get("metrics", []):
        key = ALIASES.get(metric["key"], metric["key"])
        points, visits = [], []
        for point in metric.get("points", []):
            ts, value = finite(point.get("t_epoch")), finite(point.get("v"))
            if ts is None or value is None:
                continue
            item = {"time": ts, "value": value, "record": point.get("record"),
                    "phase": None, "source": "clinic-sheet" if point.get("sheet") else "REDCap"}
            (visits if point.get("sheet") else points).append(item)
        metrics.append({"key": key, "label": metric["label"], "range": metric["range"], "points": points})
        if visits:
            clinic[key] = visits
    transitions = deepcopy(context.get("home_transitions", []))
    comparisons = context.get("comparisons", {})
    return {"metrics": metrics, "phases": deepcopy(context.get("phases", [])),
            "visits": {"available": bool(clinic), "metrics": clinic,
                       "message": "Canonical clinic-sheet ratings, kept separate." if clinic else "No clinic-sheet ratings in the canonical response."},
            "stimulation": {"available": bool(transitions or observations),
                            "message": "Device observations do not establish home activation times.",
                            "home_transitions": transitions, "settings_observations": list(observations),
                            "home_unknown_intervals": deepcopy(context.get("home_unknown_intervals", []))},
            "comparisons": {key: deepcopy(comparisons.get(key, unavailable(key + " assignments")))
                            for key in ("stimulation", "medications")},
            "message": "Legacy canonical MPQ values are preserved separately from the standard 15-item MPQ. Standard MPQ is available only from a verified item mapping. Source record identity is unavailable where record is null.",
            "provenance": {"source": "Biomarkers.pain_scores_for_participant", "adapter_version": VERSION,
                           "metadata_revision": context.get("revision"), "record_identity_available": all(
                               p["record"] is not None for m in metrics for p in m["points"])}}


_SENSIGHT_MODELS = {"SenSight B33015", "SenSight B33005"}
_PERCEPT_LEADS = _SENSIGHT_MODELS | {"Medtronic 3387", "Medtronic 3389"}


def _side(stim):
    target = stim.get("Electrode", {}).get("Target", "")
    return "left" if target.startswith("Left") else "right" if target.startswith("Right") else None


def _contacts(stim, side):
    """Normalize only documented Medtronic labels; unknown labels remain unresolved.

    Source ChannelNames are local on BOTH leads. The existing schematic contract
    uses the right lead's +8 display offset. Source strings are preserved separately.
    """
    parts = []
    for field, polarity in (("Contact", "-"), ("ReturnContact", "+")):
        for label in stim.get(field, []):
            if label == "CAN":
                token = "C"
            else:
                match = re.fullmatch(r"E0([0-3])(?:-([ABC]))?", str(label))
                if not match or stim.get("Electrode", {}).get("Type") not in _PERCEPT_LEADS:
                    return "Unresolved source contacts"
                level, segment = int(match[1]), (match[2] or "").lower()
                if segment and (level not in (1, 2) or stim["Electrode"]["Type"] not in _SENSIGHT_MODELS):
                    return "Unresolved source contacts"
                token = str(level + (8 if side == "right" else 0)) + segment
            parts.append(token + polarity)
    return " ".join(parts) or "Not recorded"


def _cycling(stim):
    duty, period = finite(stim.get("Cycling")), finite(stim.get("CyclingPeriod"))
    if duty is None:
        return None
    if duty == 1:
        return "Off"
    if not 0 <= duty < 1:
        return "Unknown (invalid recorded duty fraction)"
    if stim.get("Electrode", {}).get("Type") not in _PERCEPT_LEADS:
        return f"Recorded duty fraction {duty:g}; period unit unverified"
    if period is None or period <= 0:
        return "On"
    # MedtronicPercept/Therapy stores OnDurationInMilliSeconds + OffDurationInMilliSeconds.
    return f"On · On {duty * period / 1000:g} s / Off {(1-duty) * period / 1000:g} s"


def therapy_observations(history):
    """Recorded snapshots only, preserving distinct programs, units and lead model.

    Program numbers are presentation indices in the canonical source list's order,
    not inferred hardware program IDs. Raw program types do not prove adaptive delivery.
    """
    output = []
    for device in history.get("TherapyConfiguration", []):
        for row in device.get("History", []):
            ts = finite(row.get("Date"))
            if ts is None:
                continue
            settings = {"group": [{"label": "Group", "value": row.get("GroupName") or row.get("GroupId") or "Unknown"},
                                  {"label": "Mode at observation", "value": row.get("StimulationType") or "Unknown"}],
                        "left": [], "right": []}
            cycling, models = set(), {"left": set(), "right": set()}
            stimuli = row.get("StimulationSettings", [])
            counts = {side: sum(_side(stim) == side for stim in stimuli) for side in ("left", "right")}
            indices = {"left": 0, "right": 0}
            for stim in stimuli:
                side = _side(stim)
                if side is None:
                    continue
                indices[side] += 1
                prefix = f"Program {indices[side]} · " if counts[side] > 1 else ""
                def add(label, value):
                    settings[side].append({"label": prefix + label, "value": value})
                electrode = stim.get("Electrode", {})
                models[side].add(electrode.get("Type"))
                add("Tablet target", electrode.get("Target", ""))
                unit = stim.get("PulsewidthUnit", "")
                pulse_unit = "µs" if unit in ("uS", "us", "µs", "μs") else unit
                for label, field, unit in (("Frequency", "Frequency", "Hz"), ("Amplitude", "Amplitude", stim.get("AmplitudeUnit", "")),
                                           ("Pulse width", "Pulsewidth", pulse_unit)):
                    value = finite(stim.get(field))
                    if value is not None:
                        add(label, f"{value:g} {unit}".strip())
                if stim.get("Contact") or stim.get("ReturnContact"):
                    add("Stimulation contacts", _contacts(stim, side))
                    add("Source contacts", " ".join(map(str, stim.get("Contact", []))) + " → " + " ".join(map(str, stim.get("ReturnContact", []))))
                cycle = _cycling(stim)
                if cycle is not None:
                    cycling.add(cycle)
            if cycling:
                value = next(iter(cycling)) if len(cycling) == 1 else "Conflicting records: " + "; ".join(sorted(cycling))
                settings["group"].append({"label": "Cycling", "value": value})
            geometry = {side: "sensight" for side, types in models.items() if types and types <= _SENSIGHT_MODELS}
            output.append({"id": str(row.get("Id", "")), "time": ts, "time_precision": "instant",
                           "kind": "settings_observation", "label": row.get("Type", "Settings observation"),
                           "mode": row.get("StimulationType") or "unknown", "evidence": "Device settings observation; activation time, adaptive delivery state and home status unknown. Program indices follow source list order.",
                           "lead_geometry": geometry,
                           "source_ids": [str(row["SourceId"])] if row.get("SourceId") else [], "settings": settings})
    return sorted(output, key=lambda item: item["time"])


def _day(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        return None


def oura_timeline(stored):
    """Normalize stored Oura values, original days and missing masks; never sync.

    Sleep total is a presentation-only sum of distinct non-overlapping stored sleep
    episodes per Oura day. Overlap/conflicting exports produce null, never double
    count. No completeness or QC claim is made for the provider's returned episodes.
    """
    metrics = []
    specs = (("DailyActivity", "Steps", "steps", "Steps", "steps", 1),
             ("DailyActivity", "ActiveCalories", "active_calories", "Active calories", "kcal", 1),
             ("DailyActivity", "NonWearTime", "nonwear", "Non-wear time", "hours", 3600),
             ("DailyReadiness", None, "readiness", "Readiness", "score", 1))
    for family, field, key, label, unit, divisor in specs:
        days = defaultdict(set)
        for row in stored.get(family, []):
            day = _day(row.get("Metadata", {}).get("DayLabel"))
            if day is None:
                continue
            value = finite(row.get("Descriptor", {}).get(field) if field else row.get("Metadata", {}).get("Score"))
            days[day].add(value / divisor if value is not None and value >= 0 else None)
        points = [{"day": d, "value": next(iter(v)) if len(v) == 1 else None} for d, v in sorted(days.items())]
        metrics.append(_oura_metric(key, label, unit, "Daily activity", points, "Provider daily value; conflicting exports are unavailable."))
    episodes = defaultdict(dict)
    invalid_days = set()
    for row in stored.get("Sleep", []):
        day = _day(row.get("Metadata", {}).get("DayLabel"))
        if day is None:
            continue
        desc = row.get("Descriptor", {})
        start, end, duration = (finite(desc.get(k)) for k in ("BedtimeStart", "BedtimeEnd", "TotalSleepDuration"))
        if start is None or end is None or duration is None or end <= start or duration < 0 or duration > end - start:
            invalid_days.add(day)
            continue
        episodes[day].setdefault((start, end), set()).add(duration)
    points = []
    for day in sorted(set(episodes) | invalid_days):
        rows = sorted(episodes[day].items())
        valid = day not in invalid_days and all(len(v) == 1 for _, v in rows)
        valid = valid and all(rows[i-1][0][1] <= rows[i][0][0] for i in range(1, len(rows)))
        points.append({"day": day, "value": sum(next(iter(v)) for _, v in rows) / 3600 if valid else None})
    metrics.append(_oura_metric("sleep_total", "Total recorded sleep", "hours", "Sleep", points,
                               "Sum of distinct, non-overlapping stored episodes on the original Oura day, including naps only if returned. Completeness unverified."))
    for column, key, label, unit in ((0, "sleep_heart_rate", "Sleep heart rate", "bpm"), (1, "sleep_hrv", "Sleep heart rate variability", "ms")):
        samples = {}
        for row in stored.get("Sleep", []):
            day = _day(row.get("Metadata", {}).get("DayLabel"))
            start, fs = finite(row.get("StartTime")), finite(row.get("SamplingRate"))
            if day is None or start is None or fs is None or fs <= 0:
                continue
            mask = row.get("Missing", [])
            for i, values in enumerate(row.get("Data", [])):
                value = finite(values[column]) if len(values) > column else None
                if i >= len(mask) or len(mask[i]) <= column or mask[i][column] or value is None or value < 0:
                    value = None
                index = (day, start + i / fs)
                samples.setdefault(index, set()).add(value)
        pts = [{"day": d, "time": t, "value": next(iter(v)) if len(v) == 1 else None} for (d, t), v in sorted(samples.items())]
        metrics.append(_oura_metric(key, label, unit, "Sleep", pts, "Stored sleep samples; provider missing mask retained.", "sample"))
    return {"metrics": metrics, "defaults": [m["key"] for m in metrics if m["default"] and m["available"]],
            "provenance": {"source": "OURA.DataManager.loadOuraRingData", "day_basis": "original Oura DayLabel", "qc_versions": [], "adapter_version": VERSION},
            "message": "Stored provider data; no additional reviewed QC is asserted."}


def _oura_metric(key, label, unit, group, points, definition, resolution="day"):
    return {"key": key, "label": label, "unit": unit, "group": group, "resolution": resolution,
            "available": any(p["value"] is not None for p in points), "default": key in ("steps", "sleep_total"),
            "definition": definition, "points": points}


def date_windows(request, context, now=None):
    """Pacific calendar boundaries, half-open UTC endpoints (including DST)."""
    today = (now or datetime.now(PACIFIC)).astimezone(PACIFIC).date()
    mode = request.get("window", "visits")
    if mode == "custom":
        start, end = date.fromisoformat(request["start_date"]), date.fromisoformat(request["end_date"])
        if start > end:
            raise ValueError("start_date must precede end_date")
        ranges = [("selected", "Selected dates", start, end + timedelta(days=1))]
    elif mode == "past28":
        ranges = [("selected", "Past 28 days", today - timedelta(days=27), today + timedelta(days=1))]
    elif mode == "visits":
        days = sorted({date.fromisoformat(d) for d in context.get("visit_days", []) if date.fromisoformat(d) <= today})
        ranges = [("current", "Since latest reviewed visit", days[-1], today + timedelta(days=1))] if days else []
        if len(days) >= 2:
            ranges.append(("previous", "Between previous reviewed visits", days[-2], days[-1]))
    else:
        raise ValueError("Unknown window")
    return [{"id": key, "label": label, "start": datetime.combine(start, time.min, PACIFIC).timestamp(),
             "end": datetime.combine(end, time.min, PACIFIC).timestamp()} for key, label, start, end in ranges]


CHRONIC_ANALYSIS_POLICY = {"id": "prasad_chronic_v1", "exact_zero_power_excluded": True,
                           "invalid_code_power_excluded": True, "raw_values_preserved": True}


def _schedule_intervals(value):
    """None means absent/malformed evidence, distinct from a recorded empty list."""
    if not isinstance(value, list):
        return None
    intervals = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            return None
        start, end = finite(item[0]), finite(item[1])
        if start is None or (item[1] is not None and (end is None or end <= start)):
            return None
        intervals.append((start, end))
    return intervals


def _sensing_provenance(states):
    available = all(state[0] for state in states)
    flagged, inherited = any(state[1] for state in states), any(state[2] for state in states)
    return {"status": "recorded" if available and not flagged and not inherited else "unverified",
            "metadata_available": available, "conflicting_settings": flagged, "inherited_settings": inherited}


def home_timeline(request, context, recordings, native_series, pair_keys, now=None, stim_series=None):
    """Native chronic values only. Explicit reviewed home intervals gate eligibility.

    native_series and pair_keys are the authoritative DecodeCommon functions,
    injected to make the pure presentation contract testable without a database.
    """
    recordings = list(recordings)
    windows = date_windows(request, context, now)
    scope = neural_scope(context)
    result = {"status": "unavailable", "timezone": "America/Los_Angeles", "visit_days": context.get("visit_days", []),
              "windows": [], "message": "Reviewed home eligibility and visit calendar are required; no home periods are inferred."}
    if recordings and all(recording.get("ChronicAnalysisPolicy") == CHRONIC_ANALYSIS_POLICY for recording in recordings):
        result["chronic_analysis_policy"] = dict(CHRONIC_ANALYSIS_POLICY)
    if scope is not None:
        result["neural_scope"] = scope
    intervals = context.get("home_intervals", [])
    if not intervals or not windows:
        return result
    buckets = defaultdict(lambda: defaultdict(set))
    amplitudes = defaultdict(set)
    provenance = defaultdict(set)
    for recording in recordings:
        names = recording.get("ChannelNames", [])
        if not names:
            continue
        hemi = "LEFT" if str(names[0]).upper().startswith("LEFT") else "RIGHT" if str(names[0]).upper().startswith("RIGHT") else None
        if hemi is None:
            continue
        # No streaming list: avoids substituting or borrowing streaming contact mappings.
        native = native_series([recording], [])
        canonical = {}
        for channel, series in native.items():
            for ts, value, hz in zip(series["t"], series["y"], series["center_hz"]):
                canonical[(channel, ts)] = (value, hz)
        times = list(recording.get("Time", []))
        keys = pair_keys(recording, times, hemi, str(names[0]))
        data = recording.get("Data", [])
        flagged = _schedule_intervals(recording.get("ScheduleFlagged"))
        inherited = _schedule_intervals(recording.get("ScheduleNoRecord"))
        available = flagged is not None and inherited is not None
        for i, ts in enumerate(times):
            ts = finite(ts)
            if ts is None or i >= len(data) or not any(float(p["start"]) <= ts < float(p["end"]) for p in intervals):
                continue
            power, hz = canonical.get((keys[i], ts), (None, None))
            amplitude = finite(data[i][1]) if len(data[i]) > 1 else None
            if amplitude is not None and amplitude < 0:
                amplitude = None
            provenance[(hemi.lower(), keys[i], hz, ts)].add((available,
                any(start <= ts and (end is None or ts < end) for start, end in (flagged or [])),
                any(start <= ts and (end is None or ts < end) for start, end in (inherited or []))))
            buckets[(hemi.lower(), keys[i], hz)][ts].add(finite(power))
            amplitudes[(hemi.lower(), ts)].add(amplitude)
    current_by_side = {}
    if stim_series is not None:
        for side in ("left", "right"):
            series = stim_series(recordings, hemisphere=side.title())
            observations = defaultdict(set)
            for ts, value in zip(series["t"], series["y"]):
                ts, value = finite(ts), finite(value)
                if ts is not None and any(float(p["start"]) <= ts < float(p["end"]) for p in intervals):
                    observations[ts].add(value if value is None or value >= 0 else None)
            current_by_side[side] = [{"time": ts, "amplitude": next(iter(values)) if len(values) == 1 else None,
                                     "amplitude_conflict": len(values) > 1}
                                    for ts, values in sorted(observations.items())]
    for window in windows:
        panels = []
        for side in ("left", "right"):
            segments = []
            for (hemi, channel, hz), rows in sorted(buckets.items(), key=lambda item: str(item[0])):
                if hemi != side:
                    continue
                points = []
                for ts, power_values in sorted(rows.items()):
                    if not window["start"] <= ts < window["end"]:
                        continue
                    point = {"time": ts}
                    for field, values in (("power", power_values), ("amplitude", amplitudes[(side, ts)])):
                        vals = values - {None}
                        point[field] = next(iter(vals)) if len(vals) == 1 else None
                        point[field + "_conflict"] = len(vals) > 1
                    points.append((point, _sensing_provenance(provenance[(side, channel, hz, ts)])))
                # Split disconnected runs: a known-band trace must not bridge an
                # intervening invalid/unknown-band sample or an absent ten-minute bin.
                runs = []
                for point, sensing in points:
                    if not runs or point["time"] - runs[-1][1][-1]["time"] > 600 or sensing != runs[-1][0]:
                        runs.append((sensing, []))
                    runs[-1][1].append(point)
                for run_index, (sensing, run) in enumerate(runs):
                    segments.append({"id": f"{side}:{channel}:{hz}:{run_index}", "start": run[0]["time"], "end": min(window["end"], math.nextafter(run[-1]["time"], math.inf)),
                                     "end_basis": "exclusive_sample_envelope", "sensing_provenance": sensing,
                                     "source_channel": channel,
                                     "mode": "unknown", "sensing_side": side if "_" in channel else None, "sensing_contacts": channel if "_" in channel else None,
                                     "center_frequency_hz": hz, "power_band_label": f"{hz:g} Hz" if hz is not None else "Recorded band; center unknown",
                                     "mapping_status": "recorded" if "_" in channel else "unknown", "threshold_status": "unavailable",
                                     "evidence": "Native LFPTrendLogs; reviewed home eligibility. No stimulation-side mapping or thresholds inferred.",
                                     "settings": {"group": [], "left": [], "right": []}, "thresholds": [], "points": run})
            panel = {"side": side, "segments": segments}
            if stim_series is not None:
                panel["amplitude_series"] = [point for point in current_by_side[side] if window["start"] <= point["time"] < window["end"]]
                panel["amplitude_provenance"] = "Recorded current for this stimulation lead from the shared Prasad current reader, including current carried beside opposite-lead sensing. Exact recording times; no power-to-current alignment or control mapping inferred. Missing or conflicting current remains a gap."
            panels.append(panel)
        window["panels"] = panels
        if scope is not None:
            window["coverage"] = window_coverage(window, scope)
    result.update(status="available", windows=windows, message="Native ten-minute power (LSB) and amplitude (mA); gaps and conflicts retained.")
    return result


def neural_observation_scope(context):
    """Optional server-only display scope; never extends reviewed home eligibility."""
    if "neural_observation_scope" not in context:
        return None
    scope = context["neural_observation_scope"]
    if isinstance(scope, dict) and set(scope) == {"mode", "description"} and scope["mode"] == "automatic":
        reviewed = neural_scope(context)
        if reviewed is None or not context.get("home_intervals"):
            raise ValueError("Automatic observations require reviewed home context")
        description = scope["description"]
        if not isinstance(description, str) or not description.strip() or len(description) > 500 or any(ord(c) < 32 for c in description):
            raise ValueError("Invalid neural observation description")
        return {"mode": "automatic", "description": description.strip()}
    if not isinstance(scope, dict) or set(scope) != {"start", "end", "description"}:
        raise ValueError("Invalid neural observation scope")
    start, end = scope["start"], scope["end"]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in (start, end)) or start >= end:
        raise ValueError("Invalid neural observation bounds")
    description = scope["description"]
    if not isinstance(description, str) or not description.strip() or len(description) > 500 or any(ord(c) < 32 for c in description):
        raise ValueError("Invalid neural observation description")
    reviewed = neural_scope(context)
    if reviewed is None or not context.get("home_intervals"):
        raise ValueError("Neural observation scope requires reviewed home context")
    if start < reviewed["coverage_end"] and reviewed["coverage_start"] < end:
        raise ValueError("Neural observation scope overlaps reviewed coverage")
    return {"start": start, "end": end, "description": description.strip()}


def home_continuity_policy(context):
    """Validate reviewed, server-only continuity assumptions and dated evidence.

    This is a presentation policy, never evidence of location, settings activation,
    or absence of undocumented events. Evidence digests bind private review notes;
    their contents and provider identifiers are not exposed to the browser.
    """
    if "home_continuity" not in context:
        return None
    policy = context["home_continuity"]
    required = {"policy", "last_stimulation_date", "confirmation_date", "source_kind", "evidence_sha256"}
    if (not isinstance(policy, dict) or set(policy) not in (required, required | {"documented_sessions"})
            or policy["policy"] != "assume_until_documented_stim"
            or policy["source_kind"] != "operator_confirmation"):
        raise ValueError("Invalid home continuity policy")
    def day(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Invalid home continuity date")
        return date.fromisoformat(value)
    def evidence(value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid home continuity evidence digest")
    last, confirmed = day(policy["last_stimulation_date"]), day(policy["confirmation_date"])
    if confirmed < last:
        raise ValueError("Home continuity confirmation precedes stimulation")
    evidence(policy["evidence_sha256"])
    sessions = policy.get("documented_sessions", [])
    if not isinstance(sessions, list):
        raise ValueError("Invalid documented stimulation sessions")
    for session in sessions:
        if (not isinstance(session, dict) or set(session) != {"date", "source_kind", "evidence_sha256"}
                or session["source_kind"] not in ("clinic_sheet", "slack_stimulation_summary")):
            raise ValueError("Invalid documented stimulation session")
        day(session["date"])
        evidence(session["evidence_sha256"])
    if neural_observation_scope(context) is None or context["neural_observation_scope"].get("mode") != "automatic":
        raise ValueError("Home continuity requires automatic observations")
    return deepcopy(policy)


def home_continuity_provenance(context, calendar, today):
    """Apply the assumption between documented session days; preserve uncertainty."""
    policy = home_continuity_policy(context)
    if policy is None:
        return {}, [], []
    if date.fromisoformat(policy["confirmation_date"]) > today:
        raise ValueError("Home continuity confirmation is in the future")
    cutoff = today.isoformat()
    documented = {row["date"] for row in policy.get("documented_sessions", [])}
    documented.add(policy["last_stimulation_date"])
    known = set(context.get("visit_days", []) + calendar["days"]) | documented
    # Tomorrow's known session has a pre-midnight exclusion margin today, but
    # cannot yet become the latest completed-date anchor or supersede confirmation.
    anchors = {day for day in set(calendar["clinic_days"]) | documented if day <= cutoff}
    latest = max(day for day in known if day <= cutoff)
    superseded = latest > policy["last_stimulation_date"]
    provenance = {
        "home_status": "assumed_continuing_home",
        "home_status_basis": "documented_stimulation_calendar" if superseded else "operator_confirmed_no_new_stimulation_visits",
        "home_status_confirmed_through": None if superseded else policy["confirmation_date"],
        "home_confirmation_status": "superseded_by_documented_session" if superseded else "current",
        "last_documented_stimulation_date": latest,
        "home_policy_confirmation_date": policy["confirmation_date"],
        "message": ("Home periods continue by reviewed assumption between documented stimulation sessions. "
                    "Known testing days and inclusive 600-second margins are excluded; new stored clinic dates and reviewed stimulation summaries update these exclusions. "
                    "This does not verify physical location, device settings activation or calendar completeness.")}
    return provenance, sorted(known), sorted(anchors)


def observation_intervals(scope, visit_days):
    """Subtract known Pacific testing days, including both 600-second margins.

    visit_days includes documented home-testing dates. Its completeness outside
    reviewed coverage is not asserted. These are display intervals, not home labels.
    """
    intervals = [{"start": scope["start"], "end": scope["end"]}]
    for day in sorted({date.fromisoformat(value) for value in visit_days}):
        low = datetime.combine(day, time.min, PACIFIC).timestamp() - 600
        high = math.nextafter(datetime.combine(day + timedelta(days=1), time.min, PACIFIC).timestamp() + 600, math.inf)
        remaining = []
        for interval in intervals:
            start, end = interval["start"], interval["end"]
            if high <= start or end <= low:
                remaining.append(interval)
            else:
                if start < low:
                    remaining.append({"start": start, "end": low})
                if high < end:
                    remaining.append({"start": high, "end": end})
        intervals = remaining
    return intervals


def neural_timeline(request, context, recordings, native_series, pair_keys, now=None, calendar=None, stim_series=None):
    """Keep reviewed home output intact and append separately labelled observations."""
    scope = neural_observation_scope(context)
    recordings = list(recordings)
    result = home_timeline(request, context, recordings, native_series, pair_keys, now, stim_series)
    if scope is None:
        return result
    result["observation_windows"] = []
    exclusions = context.get("visit_days", [])
    anchors = exclusions
    if scope.get("mode") == "automatic":
        scope, exclusions, anchors, provenance = automatic_observations(context, recordings, calendar, now)
        result["observation_provenance"] = provenance
        if scope is None:
            return result
    result["observation_scope"] = scope
    display_context = {"visit_days": anchors,
                       "home_intervals": observation_intervals(scope, exclusions)}
    observed = home_timeline(request, display_context, recordings, native_series, pair_keys, now, stim_series)
    for window in observed["windows"]:
        if "observation_provenance" in result and window["id"] in ("current", "previous"):
            window["label"] = "Since latest stored clinic date" if window["id"] == "current" else "Between stored clinic dates"
        timestamps = []
        for panel in window["panels"]:
            timestamps.extend(point["time"] for point in panel.get("amplitude_series", []) if point["amplitude"] is not None)
            for segment in panel["segments"]:
                segment["display_basis"] = "recorded_observations"
                segment["mapping_status"] = "unknown"
                continuity = result.get("observation_provenance", {}).get("home_status") == "assumed_continuing_home"
                segment["evidence"] = ("Native LFPTrendLogs outside historical reviewed home coverage; known documented testing days and inclusive 600-second margins excluded. "
                    + ("Home continuity follows the reviewed assumption between documented stimulation sessions; physical location is not directly verified. " if continuity else
                       "Physical home/location and testing-calendar completeness are unverified. ")
                    + "No stimulation-side mapping, control mode or thresholds inferred.")
                if continuity:
                    segment["home_status"] = "assumed_continuing_home"
                timestamps.extend(point["time"] for point in segment["points"])
        if not timestamps:
            continue
        window["display_basis"] = "recorded_observations"
        window["coverage_basis"] = "recorded_sample_envelope"
        window["coverage"] = {"status": "partial", "start": min(timestamps),
                              "end": min(window["end"], math.nextafter(max(timestamps), math.inf))}
        window["observed_samples"] = len(timestamps)
        result["observation_windows"].append(window)
    return result


def clinic_calendar(manifest, steps, stamp, receipt, participant_uid, parse_day, infer_setting, now):
    """Validate the complete persisted native snapshot; never read/provider-fetch sheets."""
    kind = "clinic_pain_steps"
    if (not isinstance(stamp.get("signature_key"), str) or not re.fullmatch(r"[0-9a-f]{40}", stamp["signature_key"])
            or stamp.get("kind") != kind or stamp.get("participant_uid") != participant_uid
            or type(receipt.get("format")) is not int or receipt.get("format") != 1 or receipt.get("target_participant_uid") != participant_uid
            or receipt.get("repeat_wrote") is not False
            or receipt.get("canonical_store_key") != f"{kind}/{participant_uid}/{stamp.get('signature_key')}"):
        raise ValueError("Clinic receipt does not bind canonical product")
    built = datetime.fromisoformat(stamp["written_utc"])
    if built.tzinfo is None or not math.isfinite(built.timestamp()) or built.timestamp() > now:
        raise ValueError("Invalid clinic snapshot timestamp")
    if (type(receipt.get("workbook_files")) is not int or type(receipt.get("parsed_steps")) is not int
            or not manifest or len(manifest) != receipt.get("workbook_files") or len(steps) != receipt.get("parsed_steps")):
        raise ValueError("Clinic snapshot counts differ")
    files, days, clinic_days = {}, set(), set()
    for entry in manifest:
        name = entry["file"]
        day = parse_day(name)
        setting = entry["setting"]
        if (not isinstance(name, str) or name in files or day is None
                or setting not in ("clinic", "home") or setting != infer_setting(name)
                or entry.get("error") not in (None, "")):
            raise ValueError("Invalid clinic calendar entry")
        value = day.date().isoformat()
        files[name] = (value, setting)
        days.add(value)
        if setting == "clinic":
            clinic_days.add(value)
    hashes = {}
    for entry in steps:
        name = entry["file"]
        day = entry["visit_date_ts"]
        if (name not in files or day is None or not hasattr(day, "date")
                or (day.date().isoformat(), entry["setting"]) != files[name]
                or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise ValueError("Clinic step provenance differs")
        hashes.setdefault(name, set()).add(entry["sha256"])
        if len(hashes[name]) != 1:
            raise ValueError("Clinic step content conflicts")
    return {"status": "stored_snapshot", "days": sorted(days), "clinic_days": sorted(clinic_days),
            "built_at": built.isoformat()}


def automatic_observations(context, recordings, calendar, now=None):
    """Derive observational coverage, never reviewed eligibility or physical location."""
    current = now or datetime.now(PACIFIC)
    instant = current.timestamp()
    calendar = calendar or {"status": "unavailable"}
    provenance = {"mode": "automatic", "calendar_status": calendar["status"],
                  "calendar_built_at": calendar.get("built_at"), "freshness": "upstream_unverified",
                  "testing_calendar_completeness": "unverified", "location_status": "unverified",
                  "message": "Latest stored clinic snapshot; upstream freshness, location and testing-calendar completeness are unverified."}
    if calendar["status"] != "stored_snapshot":
        provenance["message"] = ("Clinic snapshot changed while loading; automatic observations withheld until refresh. Historical reviewed periods are unchanged."
            if calendar.get("reason") == "changed_during_read" else
            "Accepted clinic calendar unavailable; automatic observations withheld. Historical reviewed periods are unchanged.")
        return None, [], [], provenance
    continuity, policy_exclusions, policy_anchors = home_continuity_provenance(context, calendar, current.astimezone(PACIFIC).date())
    provenance.update(continuity)
    start = neural_scope(context)["coverage_end"]
    times = [finite(value) for row in recordings for value in row.get("Time", [])
             if not isinstance(value, (str, bool))]
    valid = [value for value in times if value is not None and start <= value <= instant]
    if not valid:
        provenance["message"] = "No stored neural observations after reviewed coverage and before the current time."
        return None, [], [], provenance
    scope = {"start": start, "end": math.nextafter(max(valid), math.inf),
             "description": neural_observation_scope(context)["description"]}
    exclusions = policy_exclusions if continuity else sorted(set(context.get("visit_days", [])) | set(calendar["days"]))
    anchors = policy_anchors if continuity else calendar["clinic_days"]
    return scope, exclusions, anchors, provenance
