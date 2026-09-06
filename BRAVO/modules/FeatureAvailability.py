"""Data-backed navigation prerequisites, distinct from scientific validation outcomes."""
from collections import Counter
import logging

import numpy as np

log = logging.getLogger(__name__)
SNAPSHOT_TYPES = {"MedtronicBrainSenseSurvey", "MedtronicBaselineMontages", "MedtronicElectrodeIdentifier"}
TIME_TYPES = SNAPSHOT_TYPES | {"CustomizedStreamingData", "MedtronicBrainSenseTimeDomain",
    "MedtronicBrainSensePowerDomain", "MedtronicIndefiniteStream", "DelsysMDAT", "SynchronizedMDAT",
    "HPFCSV", "AOMPX", "MATFile"}
RESEARCH_TYPES = {"MedtronicBrainSenseSurvey", "MedtronicBaselineMontages", "MedtronicBrainSenseTimeDomain",
    "MedtronicBrainSensePowerDomain", "MedtronicIndefiniteStream", "MedtronicChronicBrainSense",
    "PatientControllerEvent"}
MEDICATION_NAMES = {"MEDOFF_DBSOFF_UPDRS", "MEDOFF_THRESHOLD", "MEDOFF_DBSON_UPDRS",
    "MEDON_DBSOFF_UPDRS", "MEDON_THRESHOLD", "MEDON_DBSON_UPDRS"}


def _finite(value):
    if isinstance(value, dict):
        return any(_finite(item) for item in value.values())
    if isinstance(value, (str, bool)) or value is None:
        return False
    try:
        return bool(np.isfinite(np.asarray(value, dtype=float)).any())
    except (ValueError, TypeError):
        return False


def measurement_record_count(data):
    """Count actual stored observations, not placeholder days or a connected device."""
    if not isinstance(data, dict):
        return 0
    count = 0
    for records in data.values():
        if not isinstance(records, (list, tuple)):
            continue
        for record in records:
            if not isinstance(record, dict) or (record.get("Metadata") or {}).get("NoData"):
                continue
            present = _finite(record.get("Descriptor"))
            try:
                values = np.asarray(record.get("Data", []), dtype=float)
                missing = np.asarray(record.get("Missing", np.zeros_like(values)))
                present = present or bool((np.isfinite(values) & (missing == 0)).any())
            except (ValueError, TypeError):
                pass
            score = (record.get("OuraMetadata") or record.get("Metadata") or {}).get("Score")
            present = present or (_finite(score) and float(score) >= 0)
            count += int(present)
    return count


def build_feature_map(counts, available_models, errors=None):
    errors = errors or {}
    result = {}
    def add(key, count, reason, *, kind="data", setup=False, error_key=None):
        error = errors.get(error_key or key)
        result[key] = {"available": bool(count) and not error, "reason": error or ("" if count else reason),
                       "kind": "unknown" if error else kind, "count": int(count or 0)}
        if setup:
            result[key]["setup"] = True
    add("therapyHistory", counts.get("therapy"), "No eligible therapy history")
    add("nerual-activity-snapshot", counts.get("snapshot"), "No neural snapshot data")
    add("time-series-analysis", counts.get("timeseries"), "No time-series data")
    add("chronic-neural-activity", counts.get("chronic"), "No chronic neural data")
    add("events", counts.get("events"), "No recorded events")
    add("FormRecords", counts.get("surveys"), "No survey records")
    add("redcapTimeline", counts.get("daily_pros"), "No approved REDCap surveys", error_key="daily_pros")
    add("PainScores", counts.get("daily_pros"), "No approved daily pain surveys", error_key="daily_pros")
    for key, field, label, setup in [
        ("FitbitDashboard", "fitbit", "Fitbit", True),
        ("GoogleHealthDashboard", "google", "Google Health", True),
        ("OuraRingDashboard", "oura", "Oura", True),
        ("EmpaticaDataExplorer", "empatica", "Empatica", False),
    ]:
        add(key, counts.get(field), f"No {label} data", setup=setup, error_key=field)
    add("ouraFreeReps", counts.get("oura"), "No eligible Oura data", error_key="oura")
    add("3dImageViewer", counts.get("imaging"), "No imaging data")
    timeline = sum(counts.get(k, 0) or 0 for k in ("timeline", "chronic", "surveys", "oura", "fitbit", "empatica"))
    add("multimodal-timeline-report", timeline, "No timeline data")
    research = min(counts.get("daily_pros", 0), counts.get("research_neural", 0))
    for key in ("biomarkers", "closedLoopSim"):
        add(key, research, "Needs approved daily surveys and neural data", kind="research", error_key="daily_pros")
    add("stimOptimizer", min(research, counts.get("therapy", 0)),
        "Needs approved daily surveys, neural data and therapy history", kind="research", error_key="daily_pros")
    # Expose actual prerequisites, not a fabricated number of temporally matched pairs.
    for key in ("biomarkers", "closedLoopSim", "stimOptimizer"):
        result[key].pop("count", None)
        result[key]["inputs"] = {"daily_surveys": counts.get("daily_pros", 0),
                                  "neural_recordings": counts.get("research_neural", 0)}
    result["stimOptimizer"]["inputs"]["therapy_records"] = counts.get("therapy", 0)
    # The bundled native beta methods remain usable even when optional Lavu/Wong models are absent.
    has_methods = any(available_models.values())
    for key in ("AIHealthcare", "PredictTherapyParameters"):
        add(key, counts.get("prediction", counts.get("snapshot", 0)) if has_methods else 0,
            "No qualifying neural surveys" if has_methods else "Prediction methods are not installed",
            kind="data" if has_methods else "code")
        result[key]["models"] = dict(available_models)
    # This legacy page discards RequestAIResult and has no result renderer. Native methods remain
    # available through the dedicated Predict Therapy Parameters page.
    result["AIHealthcare"].update(available=False, kind="code", reason=
        "Result viewer is not implemented; use Predict Therapy Parameters")
    add("InClinicMedicationCycle", counts.get("medication_cycle"), "No labeled medication-cycle recordings")
    return result


def for_participant(participant):
    from django.db.models import Count, Q
    from Server import models
    from modules import AnalysisData, DataAnalysis
    from modules.RCS08DataPolicy import IMPLANT_DAY, applies_to

    sources = AnalysisData.eligible_source_files(participant)
    recording_qs = models.Recording.find_all(source__in=sources)
    neural_qs = recording_qs.filter(date__gte=IMPLANT_DAY) if applies_to(participant) else recording_qs
    neural = Counter({row["type"]: row["n"] for row in neural_qs.values("type").annotate(n=Count("uid"))})
    all_records = Counter({row["type"]: row["n"] for row in recording_qs.values("type").annotate(n=Count("uid"))})
    source_counts = Counter({row["type"]: row["n"] for row in sources.values("type").annotate(n=Count("uid"))})
    therapy = models.Therapy.find_all(source__in=sources)
    events = models.DBSEvent.find_all(source__in=sources)
    if applies_to(participant):
        therapy, events = therapy.filter(date__gte=IMPLANT_DAY), events.filter(date__gte=IMPLANT_DAY)
    annotations = models.Annotation.find_all(owner=participant, type="ChronicCustomEvent")
    annotations = annotations.filter(Q(source__isnull=True) | Q(source__in=sources))
    counts = {
        "therapy": therapy.count(), "snapshot": sum(neural[k] for k in SNAPSHOT_TYPES),
        "prediction": neural["MedtronicBrainSenseSurvey"] + neural["MedtronicBaselineMontages"],
        "timeseries": sum(neural[k] for k in TIME_TYPES), "chronic": neural["MedtronicChronicBrainSense"],
        "research_neural": sum(neural[k] for k in RESEARCH_TYPES),
        "events": events.count() + annotations.count(),
        "surveys": models.ScaleRecord.find_all(participant=participant).count(),
        "imaging": source_counts["NeuroImage"], "empatica": all_records["EmpaticaData"],
        "timeline": all_records["CustomizedTimelineData"] + all_records["AppleWatchData"],
        "medication_cycle": neural_qs.filter(type="MedtronicBrainSensePowerDomain", name__in=MEDICATION_NAMES).count(),
    }
    errors = {}
    try:
        counts["daily_pros"] = len(AnalysisData.canonical_pros(participant))
    except (ValueError, TypeError):
        counts["daily_pros"] = 0
        errors["daily_pros"] = "Approved daily-survey provenance needs repair"
        log.exception("Cannot verify daily-survey availability for %s", participant.uid)
    sensor_loaders = {
        "oura": ("OuraRingAPISource", "modules.OURA.DataManager", "loadOuraRingData"),
        "fitbit": ("FitbitWebAPISource", "modules.Fitbit.DataManager", "loadFitbitData"),
        "google": ("GoogleHealthSource", "modules.GoogleHealth.DataQuery", "loadGoogleHealthData"),
    }
    from importlib import import_module
    for key, (source_type, package, name) in sensor_loaders.items():
        counts[key] = 0
        if not source_counts[source_type]:
            continue
        try:
            counts[key] = measurement_record_count(getattr(import_module(package), name)(participant))
        except Exception:
            errors[key] = "Stored data could not be checked"
            log.exception("Cannot verify %s data availability for %s", key, participant.uid)
    return build_feature_map(counts, DataAnalysis.machineLearningAvailability(), errors)
