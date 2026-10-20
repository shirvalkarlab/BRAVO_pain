"""Fail-closed browser-view policy for explicitly provisioned shared viewers.

This is an additional restriction, never a participant-access grant. Existing
handlers still authorize each participant. Normal report reads may populate their
existing derived caches; source changes, saved choices, provider refreshes and
administration are excluded. Guarded authentication invokes this after resolving
identity and before a handler executes, including views with AllowAny permissions.
"""
from rest_framework.exceptions import PermissionDenied


MESSAGE = "This shared account is read-only. Use your individual account to make changes."


def is_read_only(user):
    configuration = getattr(user, "configuration", None)
    return isinstance(configuration, dict) and configuration.get("SharedReadOnly") is True


# Each rule is (accepted top-level keys, exact selector values). No prefix or
# HTTP-verb heuristic: several POST query routes and one GET download route write.
def _rule(keys="", **selectors):
    return frozenset(keys.split()), {key: tuple(values) for key, values in selectors.items()}


_MATCHING = "LabelMetric LabelStrategy PercentileLow PercentileHigh MatchToleranceMin MaxPerRating RefractoryMin MatchDirection MatchExtentSec AllowWindowReuse IncludeClinicSheetRatings"
_BAND = "Channel CenterHz BandWidthHz Cutpoint NBoot ThresholdMode"
_POST = {
    "/api/login": _rule("Email Password Persistent"),
    "/api/logout": _rule(),
    "/api/querySessions": _rule("session"),
    "/api/queryProfile": _rule(),
    "/api/queryParticipants": _rule(),
    "/api/queryParticipantInformation": _rule("ParticipantId"),
    "/api/checkAccessPermission": _rule("ParticipantId"),
    "/api/queryProcessingQueue": _rule(),
    "/api/queryServerIdentity": _rule(),
    "/api/queryParticipantAnnotations": _rule("ParticipantId"),
    "/api/queryParticipantEvents": _rule("ParticipantId RequestType", RequestType=("RequestAll", "RequestData")),
    "/api/queryAnalysisConfigurations": _rule("RequestType", RequestType=("QueryConfigurations",)),
    "/api/querySourceFiles": _rule("ParticipantId RequestType", RequestType=("All",)),
    "/api/queryImageSourceFiles": _rule("ParticipantId RequestType SourceId ElectrodeName", RequestType=("ListAll", "GetPagination")),
    "/api/queryRawTimeseries": _rule("ParticipantId RequestType RecordingId ChannelIndex", RequestType=("Overview", "RawTimeseries")),
    "/api/queryTherapeuticEffectAnalysis": _rule("ParticipantId RequestType AnalysisId ActiveChannels ProcessingConfiguration", RequestType=("Overview", "RequestData")),
    "/api/queryTimeseriesAnalysis": _rule("ParticipantId RequestType AnalysisId TherapyId ActiveChannels ProcessingConfiguration", RequestType=("Overview", "RequestData")),
    "/api/queryNeuralActivitySnapshot": _rule("ParticipantId RequestType ProcessingConfiguration", RequestType=("RequestAll",)),
    "/api/queryChronicNeuralActivity": _rule("ParticipantId RequestType ProcessingConfiguration", RequestType=("RequestAll",)),
    "/api/queryChronicTimeline": _rule("ParticipantId RequestType ProcessingConfiguration DataIds Channel", RequestType=("RequestAll", "RequestData")),
    "/api/queryBurstAnalysis": _rule("ParticipantId RequestType RecordingIds Channel CenterFrequency ProcessingConfiguration", RequestType=("RequestData",)),
    "/api/queryMedicationCycleAnalysis": _rule("ParticipantId RequestType RecordingIds", RequestType=("RequestAll", "RequestAnalysis")),
    "/api/queryCustomizedAnalysis": _rule("ParticipantId RequestType AnalysisId ResultId ActiveChannels", RequestType=("RequestList", "ProcessingNodes", "AnalysisOverview", "AnalysisOutput")),
    "/api/queryTherapyHistory": _rule("ParticipantId Compact"),
    # These are the current default Therapy History page's actual v2 readers.
    "/api/v2/queryTherapyHistory": _rule("ParticipantId RequestType", RequestType=("Metadata", "TherapyModification", "Impedance", "TherapyGroup")),
    "/api/queryRedcapTimeline": _rule("ParticipantId RequestType", RequestType=(None, "Revision")),
    "/api/queryOuraTimeline": _rule("ParticipantId RequestType", RequestType=(None, "Revision")),
    "/api/queryHomeNeuralTimeline": _rule("ParticipantId RequestType window start_date end_date", RequestType=(None, "Revision")),
    "/api/queryOuraRingData": _rule("ParticipantId RequestType", RequestType=("RequestOverview",)),
    "/api/queryFitbitData": _rule("ParticipantId RequestType", RequestType=("RequestOverview",)),
    "/api/queryGoogleHealthData": _rule("ParticipantId RequestType", RequestType=("RequestOverview",)),
    "/api/queryEmpaticaData": _rule("ParticipantId RequestType ChannelName", RequestType=("RequestOverview", "RequestData")),
    "/api/querySurveyForms": _rule("RequestType FormLink VersionRel", RequestType=("RequestAll", "RequestForm", "RequestAvailabilityMatrix")),
    "/api/queryParticipantSurveyRecords": _rule("ParticipantId RequestType FormId", RequestType=("RequestAll", "RequestRecords")),
    "/api/queryFilterData": _rule("RequestType Filters", RequestType=("GetFilterOptions", "ApplyFilters")),
    "/api/queryAsyncJobQueue": _rule("RequestType JobId", RequestType=("GetAllStatus", "GetJobStatus")),
    "/api/queryGroupAnalysis": _rule("RequestType AnalysisName ParticipantId Contact", RequestType=("RequestTable", "RequestFullTable", "RequestPSD"), AnalysisName=("ExtractSpectralFeaturesDuringStimulation", "ExtractSpectralFeaturesDuringSurvey")),
    "/api/queryControlAnalyses": _rule("ParticipantId Page", Page=("biomarkers", "stim_optimizer")),
    "/api/queryClosedLoopChosenBand": _rule("ParticipantId Action", Action=("read",)),
    "/api/queryPainScores": _rule("ParticipantId IncludeClinicSheetRatings"),
    "/api/queryPsdScanIndex": _rule("ParticipantId LabelMetric IncludeClinicSheetRatings"),
    "/api/queryDataAvailability": _rule("ParticipantId"),
    "/api/queryElectrodeIdentifierCheck": _rule("ParticipantId"),
    "/api/queryPsdLsbConversionModel": _rule("ParticipantId"),
    "/api/queryStimProgram": _rule("ParticipantId"),
    "/api/queryTimelineDetail": _rule("ParticipantId Channel Dtype Product TStart TEnd"),
    "/api/queryBiomarkerAnalysis": _rule("ParticipantId source SlidingWindow WindowMonths WindowStep BandTimeSweep BandTimeSweepCell SweepMetric Channel BandCenterHz IntegrationSeconds IncludeCrossSettingStability " + _MATCHING),
    "/api/queryStimOptimizer": _rule("ParticipantId Sites Hemispheres WashinMin Backend NBatches Q ClosedLoop TwoStage"),
    "/api/queryClosedLoopDeployment": _rule("ParticipantId Hemisphere PowerScale PainScore Candidates StimProgram ThreeSourcePooled ClosedLoopSimulation " + _MATCHING),
    "/api/queryWiringComparison": _rule("ParticipantId PowerScale PainScore Bands StimProgram " + _MATCHING),
    "/api/queryDeploymentROC": _rule("ParticipantId " + _MATCHING + " " + _BAND),
    "/api/queryDeploymentRocByEra": _rule("ParticipantId " + _MATCHING + " " + _BAND),
    "/api/queryDeploymentSummary": _rule("ParticipantId " + _MATCHING + " " + _BAND),
    "/api/queryLsbPower": _rule("ParticipantId " + _MATCHING + " " + _BAND),
}
_GET = {
    "/api/downloadData": _rule("CacheType ParticipantId AnalysisId RecordingId RequestType", CacheType=("queryTherapeuticEffectAnalysis", "queryNeuralActivitySnapshot", "queryTimeseriesAnalysis", "queryImageModel", "queryTherapyHistory", "queryChronicNeuralActivity"), RequestType=(None, "Raw", "TherapyModification", "TherapyHistory")),
    "/api/queryFilterData": _rule("ParticipantId RecordingId ChannelFormat", ChannelFormat=(None, "raw", "clean")),
    "/api/querySourceFiles": _rule("ParticipantId SourceId RequestType"),
    "/api/queryOuraRingData": _rule("ParticipantId"),
    "/api/queryFitbitData": _rule("ParticipantId"),
    "/api/queryGoogleHealthData": _rule("ParticipantId"),
}


def _accepts(rule, data):
    keys, selectors = rule
    return set(data).issubset(keys) and all(data.get(key) in values for key, values in selectors.items())


def enforce_read_only(request, user):
    """Deny every unreviewed operation for a flagged, authenticated identity.

    Do not access request.user here: DRF calls this while authenticating it.
    Parsing a body is safe, but JSON must be an object and query strings cannot
    smuggle a second operation into a POST. Do not normalize paths or methods.
    """
    if not getattr(user, "is_authenticated", False) or not is_read_only(user):
        return
    path = request.path
    method = request.method
    query = request.query_params
    # The authenticated SPA shell is a DRF view too. Only the exact read-only
    # Homepage handler is exempt; unknown API/service URLs stay fail-closed.
    if method == "GET" and not path.startswith(("/api", "/service")):
        view = getattr(request, "parser_context", {}).get("view")
        if view is not None:
            from Server.views import Homepage
            if type(view) is Homepage:
                return
    if method == "POST":
        data = request.data
        if not isinstance(data, dict) or query or path not in _POST or not _accepts(_POST[path], data):
            raise PermissionDenied(MESSAGE)
        # The otherwise read-shaped image pagination can create a new electrode
        # SourceFile. Existing image sources remain viewable.
        if path == "/api/queryImageSourceFiles" and data.get("RequestType") == "GetPagination":
            source = data.get("SourceId")
            if not isinstance(source, str) or source.startswith("TemplateElectrode"):
                raise PermissionDenied(MESSAGE)
    elif method == "GET":
        if path not in _GET or not _accepts(_GET[path], query):
            raise PermissionDenied(MESSAGE)
        # Django QueryDict picks the last duplicate value. Reject ambiguity even
        # if another layer would interpret the first one.
        if hasattr(query, "lists") and any(len(values) != 1 for _, values in query.lists()):
            raise PermissionDenied(MESSAGE)
    else:
        raise PermissionDenied(MESSAGE)
