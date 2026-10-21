"""Authenticated, participant-scoped read endpoints for Aditya's seven-tab page."""
import logging
import hashlib
import json
import os
import math
from pathlib import Path
from datetime import datetime, timezone

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules import Database
from modules import AdityaPresentation as presentation
from modules import AdityaNeuralSettings as neural_settings

_log = logging.getLogger(__name__)


def _pain(participant_uid, context):
    from Server import models
    from modules.Biomarkers import bravo_service
    from modules import Therapy
    from modules.SurveyForms import StandardMPQ
    from modules.DecodeCommon import data_start
    # Read the authoritative snapshots directly, with Prasad's implant eligibility;
    # queryTherapyHistory builds inferred transitions and fails on an empty history.
    participant = models.Participant.find(uid=participant_uid)
    sources = models.SourceFile.find_all(owner=participant)
    snapshots = [row.get_info() for row in models.ElectricalTherapy.find_all(therapy__source__in=sources)]
    snapshots, _ = Therapy.therapy_from_data_start(snapshots, [], data_start.data_start_s(participant))
    observations = presentation.therapy_observations({"TherapyConfiguration": [{"History": snapshots}]})
    # Fail closed even if a future canonical loader reintroduces a broad fallback.
    # Only the server's participant configuration may bind a REDCap project record.
    binding = bravo_service._load_pt_config(participant, {}) if participant is not None else None
    record_id = _bound_record(binding)
    if record_id is None:
        result = presentation.pain_timeline({}, context, observations)
        result["message"] = "Participant-specific REDCap mapping is unavailable; no surveys were requested. " + result["message"]
        return result
    reports = _processed_redcap(_stored_redcap(participant))
    if not reports:
        result = presentation.pain_timeline({}, context, observations)
        result["message"] = "Stored REDCap surveys are unavailable; sync is required to import them. " + result["message"]
        return result
    # Request source-flagged sheet ratings for the separate clinic display only.
    # pain_timeline excludes them from REDCap points; scientific analysis defaults stay unchanged.
    reports, mpq_provenance = StandardMPQ.derive(reports, binding)
    canonical = bravo_service.pain_scores_for_participant({"ParticipantId": participant_uid,
        "RedcapRecordId": record_id, "IncludeClinicSheetRatings": True, "ProcessedPRO": reports})
    canonical = StandardMPQ.display_metrics(canonical, mpq_provenance)
    result = presentation.pain_timeline(canonical, context, observations)
    result["provenance"]["standard_mpq"] = mpq_provenance
    result["message"] = "Stored REDCap surveys from completed imports; upstream freshness is not verified by this display. " + result["message"]
    return result


def _stored_redcap(participant):
    """The exact participant/institute form maintained by the sync provider."""
    from Server import models
    from modules.SurveyForms import RedcapImport
    form = models.ScaleForms.find(institute=participant.institute,
        name="Daily REDCap " + participant.uid, record_type=RedcapImport.RECORD_TYPE)
    if form is None or not models.ParticipantLinkRel.include(participant=participant, record=form):
        return None
    rows = list(models.ScaleRecord.objects.filter(source=form, participant=participant).values_list("uid", "date", "record"))
    return {"form": str(form.uid), "version": form.record_version, "mapping": form.record,
            "rows": sorted(rows, key=lambda row: str(row[0]))}


def _processed_redcap(snapshot):
    """Reverse the canonical wide import without reinterpreting UTC or missingness."""
    if snapshot is None:
        return []
    pages = snapshot["mapping"]
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("Invalid stored REDCap form")
    questions = pages[0]["questions"]
    if not isinstance(questions, list) or len(questions) < 2:
        raise ValueError("Invalid stored REDCap questions")
    if questions[-1].get("variableName") != "_pro_time_utc" or questions[-1].get("text") != "Time":
        raise ValueError("Stored REDCap timestamp is not canonical UTC")
    names = [q.get("variableName") for q in questions[:-1]]
    if any(not isinstance(name, str) or not name or name.startswith("_") for name in names) or len(set(names)) != len(names):
        raise ValueError("Invalid stored REDCap metrics")
    if any(q.get("type") != "score" for q in questions[:-1]):
        raise ValueError("Invalid stored REDCap metric type")
    reports = []
    for _, date, record in snapshot["rows"]:
        if type(date) not in (int, float) or not math.isfinite(date):
            raise ValueError("Invalid stored REDCap instant")
        if not isinstance(record, list) or len(record) != 1 or not isinstance(record[0], list) or len(record[0]) != len(questions):
            raise ValueError("Invalid stored REDCap result")
        values = record[0][:-1]
        if any(value is not None and (type(value) not in (int, float) or not math.isfinite(value)) for value in values):
            raise ValueError("Invalid stored REDCap score")
        reports.append({**dict(zip(names, values)),
                        "_pro_time_utc": datetime.fromtimestamp(date, timezone.utc).replace(tzinfo=None)})
    return reports


def _bound_record(binding):
    if not isinstance(binding, dict):
        return None
    values = [binding[key] for key in ("pt", "record_id") if key in binding]
    if not values or any(isinstance(v, bool) or not isinstance(v, (str, int)) or not str(v).strip() for v in values):
        return None
    return str(values[0]) if len({str(value) for value in values}) == 1 else None


def _clinic_snapshot(participant_uid):
    """Read one committed native clinic product and its completed target receipt."""
    try:
        from modules.StimOptimizer import clinic_pain as clinic
        payload, stamp = clinic._cache_store.load_newest(clinic.CLINIC_PAIN_KIND, participant_uid)
        if payload is None:
            return {"status": "unavailable"}, None
        root = Path(os.environ["DATASERVER_PATH"]) / "daily-clinic-receipts"
        key = f"{clinic.CLINIC_PAIN_KIND}/{participant_uid}/{stamp['signature_key']}"
        candidates = sorted(root.glob("*.json"))
        if len(candidates) > 10000:
            raise ValueError("Clinic receipt inventory exceeds bound")
        receipt = None
        for path in candidates:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
                raise ValueError("Invalid clinic receipt file")
            candidate = json.loads(path.read_bytes())
            if candidate.get("target_participant_uid") == participant_uid and candidate.get("canonical_store_key") == key:
                receipt = candidate
        identity = {"stamp": stamp, "receipt": receipt}
        if receipt is None:
            return {"status": "unavailable"}, identity
        calendar = presentation.clinic_calendar(payload["manifest"].to_dict("records"), payload["steps"].to_dict("records"),
            stamp, receipt, participant_uid, clinic._visit_date_from_title, clinic._infer_setting,
            datetime.now(presentation.PACIFIC).timestamp())
        return calendar, identity
    except Exception:
        _log.warning("Stored clinic calendar validation failed")
        return {"status": "invalid"}, None


def _home_revision(participant_uid, context, request, clinic_identity):
    """Opaque, participant-scoped identity from rows only; no recording decoding."""
    from Server import models
    from modules.Biomarkers import bravo_service
    person = models.Participant.find(uid=participant_uid)
    if person is None:
        raise ValueError("Unknown participant")
    sources = models.SourceFile.find_all(owner=person)
    rows = models.Recording.find_all(source__in=sources, type__in=bravo_service.CHRONIC_TYPES)
    rows = sorted((str(row.uid), str(row.hashed), str(row.type), str(row.pointer),
                   json.dumps(row.metadata, sort_keys=True, default=str)) for row in rows)
    source_identity = sorted((str(source.uid), str(source.hashed), json.dumps(source.metadata, sort_keys=True, default=str)) for source in sources)
    identity = ["automatic-observations-v1", presentation.VERSION, neural_settings.VERSION, participant_uid, context, clinic_identity, rows, source_identity,
                bravo_service._recording_set_identity(participant_uid),
                presentation.date_windows(request, context), datetime.now(presentation.PACIFIC).date().isoformat()]
    return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


def _home(participant_uid, context, request):
    from modules.Biomarkers import bravo_service
    from modules.DecodeCommon import representation
    from modules.Biomarkers.routines import availability
    windows = presentation.date_windows(request, context)
    scope = presentation.neural_observation_scope(context)
    calendar, identity = _clinic_snapshot(participant_uid) if scope and scope.get("mode") == "automatic" else (None, None)
    revision = _home_revision(participant_uid, context, request, [calendar, identity])
    if request.get("RequestType") == "Revision":
        return {"revision": revision}
    recordings = bravo_service._load_recordings(participant_uid, bravo_service.CHRONIC_TYPES) if windows and context.get("home_intervals") else []
    if scope and scope.get("mode") == "automatic":
        current_calendar, current_identity = _clinic_snapshot(participant_uid)
        if (current_calendar, current_identity) != (calendar, identity):
            calendar = {"status": "unavailable", "reason": "changed_during_read"}
    result = presentation.neural_timeline(request, context, recordings, representation.native_lsb_by_channel,
        representation.chronic_pair_keys, calendar=calendar, stim_series=availability.stim_series)
    if any(recording.get("SourceId") for recording in recordings):
        from Server import models
        from modules import DataCurator
        person = models.Participant.find(uid=participant_uid)
        sources = {str(source.uid): source for source in models.SourceFile.find_all(owner=person)}
        # Selected original sources only; share the canonical device clock tables.
        tables = DataCurator.clock_anchor_tables(person)
        result = neural_settings.link_settings(result, recordings,
            lambda uid: DataCurator.loadPerceptJSON(sources[uid], table=tables.get(sources[uid].device or '')),
            native_series=representation.native_lsb_by_channel, pair_keys=representation.chronic_pair_keys)
    result["revision"] = revision
    return result


def _oura(participant_uid):
    from Server import models
    from modules.OURA import DataManager
    participant = models.Participant.find(uid=participant_uid)
    return presentation.oura_timeline(DataManager.loadOuraRingData(participant))


def _timeline_revision(kind, participant_uid, context):
    """Identify stored dependencies without decoding data or contacting providers.

    The saved report stamp identifies provider snapshots; native survey values also identify a
    correction back to a previously saved table (whose old stamp is not rewritten).
    These are invalidation signals, not a claim about upstream freshness.
    """
    from Server import models
    participant = models.Participant.find(uid=participant_uid)
    if participant is None:
        raise ValueError("Unknown participant")
    identity = ["presentation-stored-revision-v1", presentation.VERSION, kind, participant_uid, context]
    if kind == "oura":
        source = models.SourceFile.find(owner=participant, type="OuraRingAPISource")
        identity.append([str(source.uid), str(source.hashed), str(source.pointer)] if source else None)
    else:
        from modules.Biomarkers import bravo_service
        from modules.DecodeCommon import data_start
        binding = bravo_service._load_pt_config(participant, {})
        record_id = _bound_record(binding)
        field_map = bravo_service._resolve_field_map({"RedcapRecordId": record_id}, participant)
        stamps = [bravo_service._cache_store.newest_stamp(kind, participant_uid,
                    root=bravo_service._SHARED_CACHE_DIR_OVERRIDE)
                  for kind in (bravo_service._REDCAP_SNAPSHOT_KIND, bravo_service.CLINIC_SHEET_STEPS_KIND)]
        sources = models.SourceFile.find_all(owner=participant)
        therapy = [row.get_info() for row in models.ElectricalTherapy.find_all(therapy__source__in=sources)]
        surveys = _stored_redcap(participant)
        # Database iteration order is not provenance. Encode first so JSON-valued
        # fields need no ordering relation of their own.
        therapy = sorted(json.dumps(row, sort_keys=True, default=str, allow_nan=False) for row in therapy)
        identity.extend([binding, field_map, stamps, therapy, surveys, data_start.data_start_s(participant)])
    return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


class _PresentationView(APIView):
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]
    kind = None

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        data = request.data
        if not isinstance(data, dict) or not isinstance(data.get("ParticipantId"), str) or not data["ParticipantId"].strip():
            return Response({"message": "Malformed Input"}, status=400)
        participant_uid = data["ParticipantId"]
        # Only display selectors are accepted. No ProcessedPRO, filesystem path,
        # metadata, account, active-study override or scientific rule from clients.
        allowed = {"ParticipantId", "RequestType"} | ({"window", "start_date", "end_date"} if self.kind == "home" else set())
        if set(data) - allowed or ("RequestType" in data and data["RequestType"] != "Revision"):
            return Response({"message": "Unsupported display parameter"}, status=400)
        try:
            permissions = Database.checkAccessPermission(request.user, participant_uid,
                                study_uid=request.user.configuration.get("ActiveStudy"))
        except Exception:
            _log.exception("Aditya presentation access service unavailable")
            return Response({"message": "The access service is temporarily unavailable."}, status=503)
        if not permissions:
            return Response(status=403)
        if self.kind == "home":
            try:
                presentation.date_windows(data, {})
            except (ValueError, KeyError, TypeError):
                return Response({"message": "Invalid date window"}, status=400)
        try:
            context = {} if self.kind == "oura" else presentation.read_context(participant_uid)
            if self.kind == "home":
                result = _home(participant_uid, context, data)
            else:
                # Capture before any full read. A concurrent sync must remain
                # detectable on the next check, never labeled already consumed.
                revision = _timeline_revision(self.kind, participant_uid, context)
                if data.get("RequestType") == "Revision":
                    return Response({"revision": revision}, status=200)
                result = _oura(participant_uid) if self.kind == "oura" else _pain(participant_uid, context)
                result["revision"] = revision
        except Exception:
            _log.exception("Aditya presentation source unavailable")
            return Response({"message": "The authoritative data source is temporarily unavailable."}, status=503)
        return Response(result, status=200)


class QueryRedcapTimeline(_PresentationView):
    kind = "pain"


class QueryHomeNeuralTimeline(_PresentationView):
    kind = "home"


class QueryOuraTimeline(_PresentationView):
    kind = "oura"
