"""Actual shared-viewer policy with synthetic requests, without database/provider I/O."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from rest_framework.exceptions import PermissionDenied

_spec = importlib.util.spec_from_file_location("shared_read_only_policy", Path(__file__).resolve().parents[2] / "BRAVO/Server/read_only.py")
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)
VIEWER = NS(is_authenticated=True, configuration={"SharedReadOnly": True})


def request(path, data=None, method="POST", query=None):
    return NS(path=path, method=method, data={} if data is None else data,
              query_params={} if query is None else query)


def allow(path, data=None, **kwargs):
    policy.enforce_read_only(request(path, data, **kwargs), VIEWER)


def deny(path, data=None, **kwargs):
    with pytest.raises(PermissionDenied, match="read-only"):
        allow(path, data, **kwargs)


@pytest.mark.parametrize("user", [NS(), NS(configuration=None), NS(configuration=[]),
    NS(configuration={}), NS(configuration={"SharedReadOnly": 1}), NS(configuration={"SharedReadOnly": "true"})])
def test_flag_requires_explicit_boolean(user):
    assert not policy.is_read_only(user)


def test_scope_and_existing_accounts_unchanged():
    assert policy.is_read_only(VIEWER)
    policy.enforce_read_only(request('/api/uploadData'), NS(is_authenticated=False, configuration=VIEWER.configuration))
    policy.enforce_read_only(request('/api/uploadData'), NS(is_authenticated=True, configuration={}))


@pytest.mark.parametrize("path,data", [
    ("/api/login", {"Email":"shirvalkarlab","Password":"synthetic","Persistent":True}),
    ("/api/logout", {}), ("/api/querySessions", {"session":{"language":"en"}}),
    ("/api/queryProfile", {}), ("/api/queryParticipants", {}),
    ("/api/queryRedcapTimeline", {"ParticipantId":"synthetic"}),
    ("/api/queryRedcapTimeline", {"ParticipantId":"synthetic","RequestType":"Revision"}),
    ("/api/queryHomeNeuralTimeline", {"ParticipantId":"synthetic","window":"all"}),
    ("/api/queryOuraTimeline", {"ParticipantId":"synthetic"}),
    ("/api/queryTherapeuticEffectAnalysis", {"ParticipantId":"synthetic","RequestType":"Overview"}),
    ("/api/queryTimeseriesAnalysis", {"ParticipantId":"synthetic","RequestType":"RequestData","AnalysisId":"synthetic","TherapyId":"","ActiveChannels":[]}),
    ("/api/queryClosedLoopChosenBand", {"ParticipantId":"synthetic","Action":"read"}),
    ("/api/queryBiomarkerAnalysis", {"ParticipantId":"synthetic","BandTimeSweep":"1","SweepMetric":"nrs","MatchToleranceMin":15,"IncludeClinicSheetRatings":False}),
    ("/api/queryBiomarkerAnalysis", {"ParticipantId":"synthetic","BandTimeSweepCell":"1","Channel":"synthetic","BandCenterHz":20,"IntegrationSeconds":30}),
    ("/api/queryStimOptimizer", {"ParticipantId":"synthetic","Sites":["left_leg","back"],"Hemispheres":["Left","Right"],"WashinMin":1,"Backend":"none","NBatches":3,"Q":4,"TwoStage":True}),
    ("/api/queryClosedLoopDeployment", {"ParticipantId":"synthetic","Candidates":[],"ThreeSourcePooled":True}),
    ("/api/queryWiringComparison", {"ParticipantId":"synthetic","Bands":{}}),
    ("/api/v2/queryTherapyHistory", {"ParticipantId":"synthetic","RequestType":"TherapyGroup"}),
    ("/api/queryImageSourceFiles", {"ParticipantId":"synthetic","RequestType":"ListAll"}),
    ("/api/queryImageSourceFiles", {"ParticipantId":"synthetic","RequestType":"GetPagination","SourceId":"existing"}),
])
def test_representative_read_journeys(path,data):
    allow(path,data)


@pytest.mark.parametrize("path,data", [
    ("/api/login", {"Email":"shirvalkarlab","Password":"synthetic","DesktopAuthentication":False}),
    ("/api/queryProfile", {"RequestType":"RefreshAPIToken"}),
    ("/api/queryProfile", {"RequestType":"ChangeMainInstitute","InstituteId":"other"}),
    ("/api/queryProfile", {"RequestType":"ChangeActiveStudy","StudyId":"other"}),
    ("/api/updateSessions", {"SharedReadOnly":False}),
    ("/api/manageStudyInformation", {"RequestType":"GetStudies"}),
    ("/api/manualSync", {"RequestType":"Start","ParticipantId":"synthetic"}),
    ("/api/queryOuraRingData", {"RequestType":"RefreshOuraRingData","ParticipantId":"synthetic"}),
    ("/api/queryClosedLoopChosenBand", {"ParticipantId":"synthetic","Action":"choose"}),
    ("/api/queryClosedLoopChosenBand", {"ParticipantId":"synthetic","Action":"clear"}),
    ("/api/queryChronicNeuralActivity", {"ParticipantId":"synthetic","RequestType":"DeleteCache"}),
    ("/api/querySurveyForms", {"RequestType":"SubmitForm"}),
    ("/api/queryAnalysisConfigurations", {"RequestType":"UpdateConfigurations"}),
    ("/api/queryTherapeuticEffectAnalysis", {"RequestType":"AddNewAnalysis"}),
    ("/api/queryImageSourceFiles", {"RequestType":"UpdateModel"}),
    ("/api/queryImageSourceFiles", {"RequestType":"GetPagination","SourceId":"TemplateElectrode_Medtronic_B33015"}),
    ("/api/queryImageSourceFiles", {"RequestType":"GetPagination","SourceId":[]}),
    ("/api/queryGroupAnalysis", {"AnalysisName":"AnnotationTrainer","RequestType":"RequestTable"}),
    ("/api/queryGroupAnalysis", {"AnalysisName":"ExtractSpectralFeaturesDuringSurvey","RequestType":"RequestRefresh"}),
    ("/api/v2/queryTherapyHistory", {"RequestType":"TherapyComparison"}),
    ("/api/exportTitrationSheet", {}), ("/api/register", {}),
    ("/api/requestOuraRingAuth", {"RequestType":"RequestURL"}),
    ("/api/requestAIPrediction", {}), ("/api/queryNewFeature", {}),
    ("/service/queryParticipants", {}), ("/api/v2/queryTimeseriesAnalysis", {}),
    ("/api/queryParticipants/", {}), ("/api/queryProfile", []),
    ("/api/queryProfile", ""), ("/api/queryParticipants", {"unexpected":"value"}),
    ("/api/queryClosedLoopChosenBand", {"Action":["read"]}),
])
def test_mutations_unknown_routes_and_ambiguous_input_denied(path,data):
    deny(path,data)


@pytest.mark.parametrize("flag", ["ForceRefresh","ProcessedPRO","RedcapFieldMap","PtConfig","RedcapRecordId","Participant","TwoStageOverrideBy","TwoStageOverrideReason","Action","StartProcessing"])
def test_source_override_keys_are_denied_even_if_false(flag):
    for path in ("/api/queryBiomarkerAnalysis", "/api/queryStimOptimizer", "/api/queryClosedLoopDeployment"):
        deny(path,{"ParticipantId":"synthetic",flag:False})


@pytest.mark.parametrize("method", ["PUT","PATCH","DELETE","HEAD","OPTIONS","post"])
def test_other_methods_denied(method):
    deny('/api/queryProfile',method=method)


def test_post_query_string_cannot_smuggle_second_operation():
    deny('/api/queryProfile',query={'RequestType':'RefreshAPIToken'})


@pytest.mark.parametrize("path,query", [
    ('/api/downloadData',{'CacheType':'queryImageModel','ParticipantId':'synthetic','RecordingId':'existing'}),
    ('/api/downloadData',{'CacheType':'queryTherapyHistory','ParticipantId':'synthetic','RequestType':'Raw'}),
    ('/api/queryFilterData',{'ParticipantId':'synthetic','RecordingId':'existing','ChannelFormat':'clean'}),
    ('/api/queryOuraRingData',{'ParticipantId':'synthetic'}),
])
def test_reviewed_gets_allowed(path,query):
    allow(path,method='GET',query=query)


def test_get_does_not_mean_read_only():
    deny('/api/downloadData',method='GET',query={'CacheType':'ClearDataUpload'})
    deny('/api/queryProfile',method='GET')
    deny('/api/downloadData',method='GET',query={'CacheType':'queryImageModel','Unexpected':'x'})


def test_duplicate_query_values_denied():
    class Query(dict):
        def lists(self):
            return [(key, value if isinstance(value,list) else [value]) for key,value in self.items()]
    allow('/api/queryOuraRingData',method='GET',query=Query(ParticipantId='synthetic'))
    deny('/api/queryOuraRingData',method='GET',query=Query(ParticipantId=['first','second']))


def test_full_participant_backup_is_not_a_safe_viewer_download():
    deny("/api/downloadParticipantExport", method="GET", query={"ParticipantId":"synthetic"})
