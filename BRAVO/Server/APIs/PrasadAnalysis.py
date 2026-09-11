"""Prasad research modules, using Aditya authorization and approved input snapshots."""
import hashlib
import hmac
import importlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, connections
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from Server import models
from modules import AnalysisData, Database
from modules.HelperFunctions import json_compliant_handler

# Research methods selectively integrated through Prasad commit d745360d.
OPERATIONS = {
    "queryBiomarkerAnalysis": ("Biomarkers", "run_for_participant", ()),
    "queryDataAvailability": ("Biomarkers", "availability_for_participant", ()),
    "queryPainScores": ("Biomarkers", "pain_scores_for_participant", ()),
    "queryBandValidation": ("Biomarkers", "validate_band_for_participant", ("Channel", "CenterHz")),
    "emitBandCandidate": ("Biomarkers", "build_band_candidate", ("Channel", "CenterHz")),
    "queryDeploymentROC": ("Biomarkers", "band_deployment_roc", ("Channel", "CenterHz")),
    "queryLsbPower": ("Biomarkers", "band_lsb_and_power", ("Channel", "CenterHz")),
    "queryPsdLsbConversion": ("Biomarkers", "band_psd_lsb_conversion", ("Channel",)),
    "queryPsdLsbConversionModel": ("Biomarkers", "psd_lsb_conversion_model", ()),
    "queryDeploymentRocByEra": ("Biomarkers", "band_deployment_roc_by_era", ("Channel", "CenterHz")),
    "queryDeploymentSummary": ("Biomarkers", "deployment_summary", ("Channel", "CenterHz")),
    "queryStimOptimizer": ("StimOptimizer", "run_for_participant", ()),
    "queryClosedLoopResearch": ("ClosedLoopDeployment", "run_for_participant", ("Channel", "CenterHz")),
}
FORBIDDEN_INPUTS = {"ProcessedPRO", "RedcapFieldMap", "PtConfig", "RedcapRecordId", "Stages", "Participant"}


# Existing numerical limits follow the research service's clamps. The optimizer
# multipliers had no upper bound: ten batches/candidates is an API resource cap,
# leaving its research defaults (3 batches, 4 candidates) unchanged.
def validated_controls(data, operation):
    data = dict(data)
    ranges = {
        "CenterHz": (0, 125, False), "BandWidthHz": (0, 250, False),
        "PercentileLow": (0, 100, True), "PercentileHigh": (0, 100, True),
        "MaxPerRating": (1, 50, True), "RefractoryMin": (0, 720, True),
        "OutlierNMad": (0, 50, True), "MatchExtentSec": (3, 300, True),
        "WindowMonths": (0, 120, False), "WindowStep": (0, 120, False),
        "MatchWindowH": (0.25, 6, True), "NBatches": (1, 10, True), "Q": (1, 10, True),
        "NBoot": (200 if operation == "queryPsdLsbConversion" else 50, 5000, True),
        "WashinMin": (0, None, True), "MatchToleranceMin": (None, None, True),
        "Cutpoint": (None, None, True),
    }
    integers = {"MaxPerRating", "NBoot", "NBatches", "Q"}
    enums = {
        "source": {"timedomain", "powerdomain", "both", "chronic"},
        "LabelStrategy": {"tertile", "percentile", "median", "kmeans", "cutoff"},
        "OutlierScale": {"log", "raw"}, "MatchDirection": {"pro_first", "pro-first", "pro", "nearest", "prior"},
        "Backend": {"plotly", "none"},
        "ThresholdMode": {"dual", "single", "singleinverse", "single_inverse", "single-inverse", "singlethreshold", "singlethresholdinverse"},
    }
    boolean_keys = {"SlidingWindow", "UseLiveMatching", "AllowWindowReuse", "ClosedLoop"}
    text_keys = {"ParticipantId", "Channel", "LabelMetric"}
    list_keys = {"Sites": {"left_leg", "back"}, "Hemispheres": {"Left", "Right"}}
    allowed = set(ranges) | set(enums) | boolean_keys | text_keys | set(list_keys) | {"ForceRefresh"}
    if set(data) - allowed:
        raise ValueError("Unknown analysis controls: " + ", ".join(sorted(set(data) - allowed)))
    for key in text_keys & data.keys():
        if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > 512:
            raise ValueError("Choose a valid " + key + ".")
    for key, (low, high, inclusive) in ranges.items():
        if key not in data:
            continue
        # Empty windows retain the existing full/default-window meaning.
        if key in {"WindowMonths", "WindowStep"} and data[key] in (None, ""):
            data.pop(key)
            continue
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError(key + " must be a finite number.")
        try:
            value = float(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(key + " must be a finite number.")
        if (not math.isfinite(value) or (low is not None and (value < low if inclusive else value <= low))
                or (high is not None and value > high)):
            raise ValueError(key + " is outside its supported range.")
        if key in integers and not value.is_integer():
            raise ValueError(key + " must be a whole number.")
        data[key] = int(value) if key in integers else value
    if data.get("PercentileLow", 33.3333) >= data.get("PercentileHigh", 66.6667):
        raise ValueError("The lower percentile must be less than the upper percentile.")
    for key, choices in enums.items():
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, str) or value.strip().lower().replace(" ", "") not in choices:
            raise ValueError("Choose a supported " + key + ".")
        data[key] = value.strip().lower().replace(" ", "")
    for key in boolean_keys & data.keys():
        value = data[key]
        if isinstance(value, bool):
            continue
        if not isinstance(value, (str, int)) or str(value).lower() not in {"1", "0", "true", "false", "yes", "no", "on", "off", ""}:
            raise ValueError(key + " must be true or false.")
        data[key] = str(value).lower() in {"1", "true", "yes", "on"}
    for key, choices in list_keys.items():
        if key in data:
            value = data[key]
            if (not isinstance(value, list) or not 1 <= len(value) <= len(choices)
                    or any(not isinstance(item, str) or item not in choices for item in value)
                    or len(set(value)) != len(value)):
                raise ValueError("Choose supported " + key + ".")
    if "ForceRefresh" in data:
        value = data["ForceRefresh"]
        if value is not None and (not isinstance(value, (bool, str, int)) or str(value).lower() not in {
                "", "0", "false", "no", "none", "off", "1", "true", "yes", "on", "matrix", "matrix_only",
                "all", "full", "recompute", "hard", "2"}):
            raise ValueError("Choose a supported cache refresh mode.")
    return data


def deidentified_result(value, participant):
    """Apply BRAVO's Name->UID, MRN->empty, DOB->0 semantics to nested research output.

    Model metadata and filenames can contain the source participant label even
    after a rename. Mask those structured model fields and exact label occurrences,
    including dictionary keys, while retaining dates and scientific metric labels.
    This follows existing access semantics; it is not a new deidentification claim.
    """
    uid = str(participant.uid)
    labels = {str(getattr(participant, key, "") or "") for key in ("name", "code", "mrn")}
    # Frozen model payloads identify their source participant independently of DB names.
    def collect(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower() in {"participant", "participant_name", "patient_name", "participant_code"} and isinstance(child, str):
                    labels.add(child)
                if str(key) == "model_hashes" and isinstance(child, dict):
                    labels.update(str(filename).rsplit(".", 1)[0] for filename in child)
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)
    collect(value)
    labels.discard("")
    labels.discard(uid)
    def redact_text(text):
        for label in sorted(labels, key=len, reverse=True):
            # Underscores delimit labels in model filenames; avoid replacing a
            # short participant name inside an unrelated scientific word.
            text = re.sub(r"(?<![A-Za-z0-9])" + re.escape(label) + r"(?![A-Za-z0-9])", uid, text, flags=re.IGNORECASE)
        return text
    def clean(item):
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                normalized = str(key).lower().replace("_", "")
                if str(key) in {"model_hashes", "policy_hashes"} and isinstance(child, dict):
                    # Preserve artifact digests without distributing participant-named paths.
                    child = {"artifact_" + str(index): digest for index, (_, digest) in enumerate(sorted(child.items()))}
                if normalized in {"mrn", "medicalrecordnumber"}:
                    child = ""
                elif normalized in {"dob", "dateofbirth", "birthdate"}:
                    child = 0
                elif normalized in {"participant", "participantname", "patientname", "participantcode"} and isinstance(child, str):
                    child = uid
                # A bare Name is only identity-bearing when it matches a known label.
                result[redact_text(str(key))] = clean(child)
            return result
        if isinstance(item, list):
            return [clean(child) for child in item]
        return redact_text(item) if isinstance(item, str) else item
    return clean(value)


@lru_cache(maxsize=1)
def analysis_code_fingerprint():
    root = Path(AnalysisData.__file__).parent
    digest = hashlib.sha256()
    paths = [Path(__file__), Path(AnalysisData.__file__), root / "AnalysisJobs.py",
             root / "PerceptClock.py", root / "PerceptClockData.py"]
    for package in ("Biomarkers", "StimOptimizer", "ClosedLoopDeployment"):
        paths.extend(sorted((root / package).rglob("*.py")))
    for path in paths:
        digest.update(str(path.relative_to(root.parent)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def server_process_epoch():
    """Shared master process start ticks; never generate a worker-random token."""
    try:
        parent = os.getppid()
        raw = Path(f"/proc/{parent}/stat").read_text()
        return f"{parent}:{raw.rsplit(')', 1)[1].split()[19]}", True
    except (OSError, IndexError):
        return str(os.getpid()), False


class QueryServerIdentity(APIView):
    """Revalidate a browser result cache against authorization and approved inputs.

    Adapted from Prasad's server-boot identity endpoint. Aditya also binds the
    opaque token to participant/QC inputs, user/session, permissions and processing
    settings. This endpoint reads metadata only and never starts an analysis job.
    """
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        data = request.data
        if (not isinstance(data, dict) or set(data) != {"ParticipantId"}
                or not isinstance(data.get("ParticipantId"), str) or not data["ParticipantId"].strip()):
            return Response({"message": "A participant is required."}, status=400)
        permissions = Database.checkAccessPermission(request.user, data["ParticipantId"],
                                                     study_uid=request.user.configuration.get("ActiveStudy"))
        if not permissions:
            return Response(status=403)
        participant = models.Participant.find(uid=data["ParticipantId"])
        if participant is None:
            return Response(status=404)
        manifest = AnalysisData.input_manifest(participant)
        processing, _ = Database.retrieveProcessingSettings(request.user.configuration)
        epoch, stable = server_process_epoch()
        identity = {"participant": data["ParticipantId"], "input": manifest["fingerprint"],
                    "permission": permissions, "processing": processing,
                    "user": str(request.user.pk), "study": request.user.configuration.get("ActiveStudy"),
                    "session": getattr(getattr(request, "session", None), "session_key", None),
                    "code": analysis_code_fingerprint(), "epoch": epoch,
                    "environment": os.environ.get("BRAVO_MAIN_BIPOLAR", "").strip()}
        token = hmac.new(settings.SECRET_KEY.encode(),
                         json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(),
                         hashlib.sha256).hexdigest()
        response = Response({"boot_token": token, "stable_across_workers": stable,
                             "detail": "Opaque identity of server, approved inputs, permissions and analysis settings."})
        response["Cache-Control"] = "no-store"
        return response


class ResearchAnalysis(APIView):
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]
    operation = None

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        from modules.AnalysisJobs import get_or_start
        package, function, required = OPERATIONS[self.operation]
        data = request.data
        if not isinstance(data, dict) or not isinstance(data.get("ParticipantId"), str):
            return Response({"message": "A participant is required."}, status=400)
        if any(key not in data or data[key] is None for key in required):
            return Response({"message": "Required analysis controls are missing."}, status=400)
        if FORBIDDEN_INPUTS.intersection(data) or any(key.startswith("_") for key in data):
            return Response({"message": "Analyses use the platform's approved data. Alternate survey rows or configurations are not accepted."}, status=400)
        if "Channel" in required and not isinstance(data["Channel"], str):
            return Response({"message": "Choose a channel."}, status=400)
        if "CenterHz" in required:
            try:
                if not math.isfinite(float(data["CenterHz"])) or float(data["CenterHz"]) <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                return Response({"message": "Choose a valid positive band frequency."}, status=400)
        try:
            data = validated_controls(data, self.operation)
        except ValueError as exc:
            return Response({"message": str(exc)}, status=400)
        permissions = Database.checkAccessPermission(request.user, data["ParticipantId"],
                                                     study_uid=request.user.configuration.get("ActiveStudy"))
        if not permissions:
            return Response(status=403)
        participant = models.Participant.find(uid=data["ParticipantId"])
        if participant is None:
            return Response(status=404)
        manifest = AnalysisData.input_manifest(participant)
        processing, _ = Database.retrieveProcessingSettings(request.user.configuration)
        arguments = json.loads(json.dumps(data))
        identity = {"endpoint": self.operation, "request": arguments, "input": manifest["fingerprint"],
                    "processing": processing, "permission": permissions,
                    "code": analysis_code_fingerprint(),
                    "scientific_environment": {"BRAVO_MAIN_BIPOLAR": os.environ.get("BRAVO_MAIN_BIPOLAR", "").strip()}}

        def compute():
            close_old_connections()
            try:
                fresh = models.Participant.find(uid=participant.uid)
                if AnalysisData.input_manifest(fresh)["fingerprint"] != manifest["fingerprint"]:
                    raise RuntimeError("Data changed before analysis; retry against the current snapshot")
                service = importlib.import_module("modules." + package + ".bravo_service")
                result = getattr(service, function)(arguments)
                if AnalysisData.input_manifest(fresh)["fingerprint"] != manifest["fingerprint"]:
                    raise RuntimeError("Data changed during analysis; retry against the current snapshot")
                result = json_compliant_handler(result)
                result["InputManifest"] = {**manifest, "analysis_code": identity["code"]}
                if permissions.get("Deidentified", True):
                    result = deidentified_result(result, fresh)
                return result
            finally:
                connections.close_all()

        status, payload = get_or_start(identity, compute)
        response = Response(payload, status=status)
        response["Cache-Control"] = "no-store"
        if status == 202:
            response["Retry-After"] = "3"
        return response
