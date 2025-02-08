requester = BRAVORequestAPI('Q7LMHCTKMPCH9443TGYKZ099PDXIYCJSCWYPOQZCFJPQI9SP76D9AGEXWI8E5M8Q', ...
    'http://localhost:27286');

% List All Participant in User's Institute
Participants = requester.QueryParticipants();

% Choose One Participant
Participant = Participants(3);

% List all Therapeutic Analyses (BrainSense Streaming related)
Analyses = requester.QueryTherapeuticEffectAnalysis(Participant.Id).Analyses;

% Request Data 
Data = requester.QueryTherapeuticEffectAnalysis(Participant.Id, ...
    "analysis_uid", Analyses.Analyses(1).Id);

% List all Time-series Recordings (External Sensors, Indefinite Streams,
% Surveys, and many other time-series data)
Recordings = requester.QueryTimeseriesAnalysis(Participant.Id).Recordings;

% Request Data
Data = requester.QueryTimeseriesAnalysis(Participant.Id, ...
    "analysis_uid", Recordings(1).Id);

% Retrieve Snapshots (this is PSD only, to get raw data, use Time-series
% Recordings APIs)
Data = requester.QueryNeuralActivitySnapshot(Participant.Id);

% Retrieve Chronic Timeline
Data = requester.QueryChronicNeuralActivity(Participant.Id);

% Retrieve Therapy History
Data = requester.QueryTherapyHistory(Participant.Id);

% Retrieve Patient DBS Events (This is already done when querying Timeline,
% this is a separate API that only query event, so it is faster)
Data = requester.QueryParticipantEvents(Participant.Id);

% Retrieve Annotations (on BRAVO, not the tablet)
Data = requester.QueryParticipantAnnotations(Participant.Id);

% Retrieve Surveys (on BRAVO, not Redcap unless we make a
% separate link module that connect both)
Surveys = requester.QueryParticipantSurveyRecords(Participant.Id);

% Retrieve records of Survey (Only result is obtained here, refer to
% Surveys.Forms to identify what is the question statement for each
% response. 
Data = requester.QueryParticipantSurveyRecords(Participant.Id, Surveys.Links(1).FormId);
