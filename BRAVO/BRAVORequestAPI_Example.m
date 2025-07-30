requester = BRAVORequestAPI('Q7LMHCTKMPCH9443TGYKZ099PDXIYCJSCWYPOQZCFJPQI9SP76D9AGEXWI8E5M8Q', ...
    'http://localhost');

NewParticipant = requester.AddNewParticipant("NeuroPace01");
Device = requester.AddNewDBSDevice(NewParticipant.Id, "NeuroPace RNS-320", "LGS-000000");

% List All Participant in User's Institute
Participants = requester.QueryParticipants();

% Choose One Participant
Participant = Participants(424);

% List all Time-series Recordings (External Sensors, Indefinite Streams,
% Surveys, and many other time-series data)
Recordings = requester.QueryTimeseriesAnalysis(Participant.Id).Recordings;

% Request Data
Data = requester.QueryTimeseriesAnalysis(Participant.Id, ...
    "analysis_uid", Recordings{1}.Id, "therapy_uid", "");

% Burst Waveform
Data = requester.QueryTimeseriesAnalysis(Participant.Id, ...
    "analysis_uid", Recordings{20}.Id, "therapy_uid", "");
BetaBurst = requester.QueryBurstAnalysis(Participant.Id, {Data.Signal(1).RecordingId}, Data.Signal(1).SignalSeries.ChannelNames{1}, 22);

% Retrieve Snapshots (this is PSD only, to get raw data, use Time-series
% Recordings APIs)
Data = requester.QueryNeuralActivitySnapshot(Participant.Id);

% Retrieve Chronic Timeline
Data = requester.QueryChronicNeuralActivity(Participant.Id);

% Retrieve Chronic Timeline (Generic)
Data = requester.QueryChronicTimeline(Participant.Id);

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

% Query Medication Cycle Analysis (In-Clinic ADBS Testing)
Data = requester.QueryMedicationCycleAnalysis(Participant.Id);
Data = requester.QueryMedicationCycleAnalysis(Participant.Id, 'recording_ids', {Data.Recordings.Id});

Input = struct();
Input.Data = Data.Signal.SignalSeries(1).Data(1,:);
Input.SamplingRate = Data.Signal.SignalSeries(1).SamplingRate;
Result = requester.RequestAIPrediction('BetaPeakDetection', Input);