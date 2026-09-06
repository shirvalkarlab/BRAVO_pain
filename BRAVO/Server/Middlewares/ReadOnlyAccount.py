"""Server-side API restrictions for appliance viewer accounts."""

import json

from django.http import JsonResponse


# These endpoints only read shared BRAVO data or update the viewer's own local
# navigation/preferences. Every other API endpoint is denied by default.
READ_ONLY_POST_PATHS = frozenset(
    {
        "/api/logout",
        "/api/queryParticipantEvents",
        "/api/queryParticipantAnnotations",
        "/api/querySessions",
        "/api/updateSessions",
        "/api/queryProcessingQueue",
        "/api/queryParticipants",
        "/api/queryParticipantInformation",
        "/api/queryOuraFreeReps",
        "/api/queryOuraTimeline",
        "/api/queryRedcapTimeline",
        "/api/queryHomeNeuralTimeline",
        "/api/checkAccessPermission",
        "/api/queryTherapyHistory",
        "/service/queryParticipants",
        "/service/queryParticipantContext",
    }
)


# Mixed-purpose endpoints are restricted to explicitly read-only operations.
READ_ONLY_REQUEST_TYPES = {
    "/api/queryProfile": frozenset({None, "ChangeMainInstitute", "ChangeActiveStudy"}),
    "/api/queryFitbitData": frozenset({"RequestOverview"}),
    "/api/queryGoogleHealthData": frozenset({"RequestOverview"}),
    "/api/queryOuraRingData": frozenset({"RequestOverview"}),
    "/api/queryEmpaticaData": frozenset({"RequestOverview", "RequestData"}),
    "/api/queryRawTimeseries": frozenset({"Overview", "RawTimeseries"}),
    "/api/querySourceFiles": frozenset({"All"}),
    "/api/queryImageSourceFiles": frozenset({"ListAll", "GetPagination"}),
    "/api/querySurveyForms": frozenset({"RequestAll", "RequestForm"}),
    "/api/queryParticipantSurveyRecords": frozenset({"RequestAll", "RequestRecords"}),
    "/api/queryAnalysisConfigurations": frozenset({"QueryConfigurations"}),
    "/api/queryTherapeuticEffectAnalysis": frozenset({"Overview", "RequestData"}),
    "/api/queryNeuralActivitySnapshot": frozenset({"RequestAll"}),
    "/api/queryChronicNeuralActivity": frozenset({"RequestAll"}),
    "/api/queryChronicTimeline": frozenset({"RequestAll", "RequestData"}),
    "/api/queryTimeseriesAnalysis": frozenset({"Overview", "RequestData"}),
    "/api/queryBurstAnalysis": frozenset({"RequestData"}),
    "/api/queryCustomizedAnalysis": frozenset(
        {"RequestList", "ProcessingNodes", "AnalysisOverview", "AnalysisOutput"}
    ),
    "/api/queryMedicationCycleAnalysis": frozenset({"RequestAll", "RequestAnalysis"}),
    "/api/queryAIModels": frozenset({"RequestAll"}),
    "/api/queryGroupAnalysis": frozenset(
        {"RequestTable", "RequestFullTable", "RequestPSD"}
    ),
    "/api/queryAsyncJobQueue": frozenset({"GetAllStatus", "GetJobStatus"}),
    "/api/queryFilterData": frozenset({"GetFilterOptions", "ApplyFilters"}),
    "/api/v2/queryTherapyHistory": frozenset(
        {"Metadata", "TherapyModification", "Impedance", "TherapyGroup", "TherapyComparison"}
    ),
    "/api/v2/queryTimeseriesAnalysis": frozenset(
        {"Overview", "RequestData", "RequestSpectrogram"}
    ),
}


def _json_request_type(request):
    if not request.body:
        return None
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload.get("RequestType")


def is_read_only_user(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "configuration", {}).get("ReadOnly", False)
    )


def viewer_request_allowed(request):
    path = request.path.rstrip("/") or "/"
    if not path.startswith(("/api/", "/service/")):
        return True
    if request.method == "POST" and path in READ_ONLY_POST_PATHS:
        return True
    allowed_types = READ_ONLY_REQUEST_TYPES.get(path)
    return bool(request.method == "POST" and allowed_types is not None
                and _json_request_type(request) in allowed_types)


class ReadOnlyAccountMiddleware:
    """Deny viewer-account API operations unless explicitly permitted above."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not is_read_only_user(getattr(request, "user", None)):
            return self.get_response(request)

        if viewer_request_allowed(request):
            return self.get_response(request)

        return JsonResponse(
            {"message": "This account has view-only access."}, status=403
        )
