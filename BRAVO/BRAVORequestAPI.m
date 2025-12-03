classdef BRAVORequestAPI
    % Request APIs to interface with BRAVO Platform (v3.0.0-alpha)
    %   Detailed explanation goes here
    
    properties
        APIKey
        ServerAddress
        Profile
    end
    
    methods
        function requester = BRAVORequestAPI(key,server)
            arguments
                key char
                server char = 'http://localhost:27286'
            end
            
            requester.APIKey = key;
            requester.ServerAddress = server;
            requester.Profile = GetUserInfo(requester);
        end
        
        %{  
        Example Usage:
            Profile = requester.GetUserInfo();
        %}
        function response = GetUserInfo(requester)
            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/queryProfile'], options);
        end
        
        %{  
        Example Usage:
            Config = requester.QueryAnalysisConfiguration();
        %}
        function response = QueryAnalysisConfiguration(requester, params)
            arguments
                requester
                params.config = false
            end

            data.Configurations = struct();
            if isa(params.config, 'struct')
                data.Configurations = params.config;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/queryProfile'], data, options);
        end
        
        function response = DeleteParticipant(requester, participant_uid)
            arguments
                requester
                participant_uid
            end

            data.ParticipantId = participant_uid;

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 500);
            response = webwrite([requester.ServerAddress '/api/deleteParticipantInformation'], data, options);
        end
        
        function response = AddNewParticipant(requester, participant_name)
            arguments
                requester
                participant_name
            end

            data.Name = participant_name;

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/createParticipantInformation'], data, options);
        end
        
        function response = AddNewDBSDevice(requester, participant_uid, device_type, device_serial)
            arguments
                requester
                participant_uid
                device_type
                device_serial
            end

            data.ParticipantId = participant_uid;
            data.DeviceType = "DBSDevice";
            data.ManufacturerDeviceType = device_type;
            data.SerialNumber = device_serial;

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/manageParticipantDevice'], data, options);
        end
        
        function response = QueryParticipants(requester)
            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/queryParticipants'], options);
        end
        
        function response = QueryParticipantInformation(requester, participant_uid)
            arguments
                requester
                participant_uid
            end

            data.ParticipantId = participant_uid;

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/queryParticipantInformation'], data, options);
        end
        
        % This include chronic events and patient controller events
        function response = QueryParticipantEvents(requester, participant_uid)
            arguments
                requester
                participant_uid
            end

            data.ParticipantId = participant_uid;

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/queryParticipantEvents'], data, options);
        end
        
        % This include chronic annotations and streaming annotations
        function response = QueryParticipantAnnotations(requester, participant_uid)
            arguments
                requester
                participant_uid
            end

            data.ParticipantId = participant_uid;

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/queryParticipantAnnotations'], data, options);
        end
        
        function response = QueryParticipantSurveyRecords(requester, participant_uid, form_uid)
            arguments
                requester
                participant_uid
                form_uid = false
            end

            data.ParticipantId = participant_uid;
            data.RequestType = 'RequestAll';
            
            if isa(form_uid, 'char')
                data.RequestType = 'RequestRecords';
                data.FormId = form_uid;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 5);
            response = webwrite([requester.ServerAddress '/api/queryParticipantSurveyRecords'], data, options);
        end
        
        function response = QueryTherapeuticEffectAnalysis(requester, participant_uid, params)
            arguments
                requester
                participant_uid
                params.analysis_uid = false
                params.config = false
                params.refresh = false
            end

            data.ParticipantId = participant_uid;
            data.RequestType = 'Overview';

            if params.refresh
                data.RequestType = "DeleteCache";
                data.AnalysisId = params.analysis_uid;
                options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
                webwrite([requester.ServerAddress '/api/queryTherapeuticEffectAnalysis'], data, options);

                params.refresh = false;
                params = namedargs2cell(params);
                response = QueryTherapeuticEffectAnalysis(requester, participant_uid, params{:});
                return;
            end

            if isa(params.analysis_uid, 'char') || isa(params.analysis_uid, 'string')
                data.RequestType = 'RequestData';
                data.AnalysisId = params.analysis_uid;
                data.ActiveChannels = 'RequestAllChannel';
            end

            if isa(params.config, 'struct')
                data.ProcessingConfiguration = params.config;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/queryTherapeuticEffectAnalysis'], data, options);
        end

        function response = QueryTimeseriesAnalysis(requester, participant_uid, params)
            arguments
                requester
                participant_uid
                params.analysis_uid = false
                params.therapy_uid = false
                params.config = false
                params.refresh = false
            end

            data.ParticipantId = participant_uid;
            data.RequestType = 'Overview';
            data.TherapyId = params.therapy_uid;

            if params.refresh
                data.RequestType = "DeleteCache";
                data.AnalysisId = params.analysis_uid;
                data.TherapyId = params.therapy_uid;
                options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
                webwrite([requester.ServerAddress '/api/queryTimeseriesAnalysis'], data, options);

                params.refresh = false;
                params = namedargs2cell(params);
                response = QueryTimeseriesAnalysis(requester, participant_uid, params{:});
                return;
            end

            if isa(params.analysis_uid, 'char') || isa(params.analysis_uid, 'string')
                data.RequestType = 'RequestData';
                data.AnalysisId = params.analysis_uid;
                data.ActiveChannels = 'RequestAllChannel';
            end

            if isa(params.config, 'struct')
                data.ProcessingConfiguration = params.config;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/queryTimeseriesAnalysis'], data, options);
        end
        
        function response = QueryChronicNeuralActivity(requester, participant_uid, params)
            arguments
                requester
                participant_uid
                params.refresh = false
            end

            data.ParticipantId = participant_uid;
            data.RequestType = 'RequestAll';

            if params.refresh
                data.RequestType = "DeleteCache";
                options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
                webwrite([requester.ServerAddress '/api/queryChronicNeuralActivity'], data, options);

                params.refresh = false;
                params = namedargs2cell(params);
                response = QueryChronicNeuralActivity(requester, participant_uid, params{:});
                return;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/queryChronicNeuralActivity'], data, options);
        end
        
        function response = QueryChronicTimeline(requester, participant_uid, params)
            arguments
                requester
                participant_uid
                params.refresh = false
            end

            data.ParticipantId = participant_uid;
            data.RequestType = 'RequestAll';

            if params.refresh
                data.RequestType = "DeleteCache";
                options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
                webwrite([requester.ServerAddress '/api/queryChronicTimeline'], data, options);

                params.refresh = false;
                params = namedargs2cell(params);
                response = QueryChronicTimeline(requester, participant_uid, params{:});
                return;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/queryChronicTimeline'], data, options);
        end
        
        function response = QueryNeuralActivitySnapshot(requester, participant_uid, params)
            arguments
                requester
                participant_uid
                params.refresh = false
                params.config = false
            end

            data.ParticipantId = participant_uid;
            data.RequestType = 'RequestAll';
            
            if class(params.config) == "struct"
                data.ProcessingConfiguration = params.config;
            end

            if params.refresh
                data.RequestType = "DeleteCache";
                options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
                webwrite([requester.ServerAddress '/api/queryNeuralActivitySnapshot'], data, options);

                params.refresh = false;
                params = namedargs2cell(params);
                response = QueryNeuralActivitySnapshot(requester, participant_uid, params{:});
                return;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/queryNeuralActivitySnapshot'], data, options);
        end
        
        function response = QueryBurstAnalysis(requester, participant_uid, recording_ids, channel, fc, params)
            arguments
                requester
                participant_uid
                recording_ids
                channel
                fc
                params.config = false
            end

            data.ParticipantId = participant_uid;
            data.RequestType = 'RequestData';
            data.RecordingIds = recording_ids;
            data.Channel = channel;
            data.CenterFrequency = fc;

            disp(data);

            if isa(params.config, 'struct')
                data.ProcessingConfiguration = params.config;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/queryBurstAnalysis'], data, options);
        end
        
        function response = QueryTherapyHistory(requester, participant_uid)
            arguments
                requester
                participant_uid
            end

            data.ParticipantId = participant_uid;
            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/queryTherapyHistory'], data, options);
        end

        function response = QueryMedicationCycleAnalysis(requester, participant_uid, params)
            arguments
                requester
                participant_uid
                params.recording_ids = false
            end

            data.ParticipantId = participant_uid;
            data.RequestType = 'RequestAll';

            if isa(params.recording_ids, 'cell')
                data.RequestType = 'RequestAnalysis';
                data.RecordingIds = params.recording_ids;
            end

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/queryMedicationCycleAnalysis'], data, options);
        end

        function response = RequestAIPrediction(requester, analysis_name, input)
            arguments
                requester
                analysis_name,
                input
            end
            
            data.RequestType = 'RequestAnalysis';
            data.AnalysisName = analysis_name;
            data.Data = input;

            options = weboptions('HeaderFields', {'X-Secure-API-Key' requester.APIKey;}, 'Timeout', 60);
            response = webwrite([requester.ServerAddress '/api/requestAIPrediction'], data, options);
        end
    end
end

