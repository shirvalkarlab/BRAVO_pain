""""""
"""
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under Open Source GPL-3.0 License

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
"""
Data Upload Handler Module
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
import json
import traceback
from copy import deepcopy
from pathlib import Path
import hmac, hashlib

import rest_framework.views as RestViews
import rest_framework.parsers as RestParsers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.conf import settings

from Server import models
from modules.HelperFunctions import sanitize_input, get_or_none
from modules import Database, DataCurator, DataAnalysis

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

class QueryAnalysisConfigurations(RestViews.APIView):
    
    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if request.data["RequestType"] == "QueryConfigurations":
            userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)
            return Response(status=200, data=userConfig)

        elif request.data["RequestType"] == "UpdateConfigurations":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "Configurations"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            userConfig, _ = Database.retrieveProcessingSettings({"ProcessingConfiguration": request.data["Configurations"]})
            request.user.configuration["ProcessingConfiguration"] = userConfig
            request.user.save()
            return Response(status=200, data=userConfig)

class QueryTherapeuticEffectAnalysis(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        if request.data["RequestType"] == "Overview":
            Overview = DataAnalysis.queryAvailableAnalyses(request.data["ParticipantId"], "TherapeuticAnalysis")
            return Response(status=200, data=Overview)

        elif request.data["RequestType"] == "AddNewAnalysis":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "TherapyIds", "RecordingIds"]):
                return Response(status=400, data={"message": "Malformed Input"})

            if len(request.data["RecordingIds"]) == 0 or len(request.data["TherapyIds"]) == 0:
                return Response(status=400, data={"message": "Malformed Input"})

            AllRecordings = []
            AllRecordings.extend(request.data["RecordingIds"])
            AllRecordings.extend(request.data["TherapyIds"])
            result = DataAnalysis.createAnalysis(request.data["ParticipantId"], "TherapeuticAnalysis", AllRecordings)
            if result:
                return Response(status=200, data=result.get_info())
            else:
                return Response(status=400, data={"message": "Fail to create analysis"})
                
        elif request.data["RequestType"] == "DeleteAnalysis":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId"]):
                return Response(status=400, data={"message": "Malformed Input"})

            result = DataAnalysis.deleteAnalysis(request.data["ParticipantId"], request.data["AnalysisId"])
            if result:
                return Response(status=200)
            else:
                return Response(status=400, data={"message": "Fail to delete analysis"})

        elif request.data["RequestType"] == "RequestData":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId", "ActiveChannels"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            if "ProcessingConfiguration" in request.data.keys():
                userConfig, _ = Database.retrieveProcessingSettings({"ProcessingConfiguration": request.data["ProcessingConfiguration"]})
            else:
                userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)

            result = Database.getCachedResult("/queryTherapeuticEffectAnalysis", request.data["ParticipantId"], {**userConfig, **request.data})
            if result:
                return Response(status=200, data=result)

            metadata = {**userConfig, **request.data, **{
                "ActiveChannels": ""
            }}
            Analysis = Database.getCachedResult("/queryTherapeuticEffectAnalysis", request.data["ParticipantId"], metadata)
            if not Analysis:
                Analysis = DataAnalysis.processTherapeuticAnalysis(request.data["ParticipantId"], request.data["AnalysisId"], userConfig)
                #Database.saveCachedResult(Analysis, "/queryTherapeuticEffectAnalysis", request.data["ParticipantId"], metadata)
                         
            if not request.data["ActiveChannels"] == "RequestAllChannel":
                Analysis = DataAnalysis.selectRecordingChannel(Analysis, request.data["ActiveChannels"])

            Database.saveCachedResult(Analysis, "/queryTimeseriesAnalysis", request.data["ParticipantId"], {**userConfig, **request.data})
            return Response(status=200, data=Analysis)

        elif request.data["RequestType"] == "UpdateData":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId", "RecordingName", "StimulationLabel"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            analysis = models.Analysis.find(uid=request.data["AnalysisId"])
            for recording in analysis.recordings.all():
                if not recording.source.owner.uid == request.data["ParticipantId"]:
                    return Response(status=400, data={"message": "Permission Denied"})

                if recording.type == "MedtronicBrainSenseTimeDomain":
                    recording.name = request.data["RecordingName"]
                    recording.save()
                elif recording.type == "MedtronicBrainSensePowerDomain":
                    recording.name = request.data["RecordingName"]
                    sideN = 0
                    for side in ["Left", "Right"]:
                        if side in recording.metadata["Therapy"].keys():
                            recording.metadata["Therapy"][side]["SegmentMode"] = request.data["StimulationLabel"][sideN]
                            sideN += 1
                    recording.save()
            analysis.name = request.data["RecordingName"]
            analysis.save()
            return Response(status=200)

        elif request.data["RequestType"] == "DeleteCache":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            analysis = models.Analysis.find(uid=request.data["AnalysisId"])
            for recording in analysis.recordings.all():
                if not recording.source.owner.uid == request.data["ParticipantId"]:
                    return Response(status=400, data={"message": "Permission Denied"})
                
                DataAnalysis.deleteProcessedData(recording=recording)

            return Response(status=200)

        return Response(status=400, data={"message": "Malformed Input"})
    
class QueryTimeseriesAnalysis(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        if request.data["RequestType"] == "Overview":
            Overview = DataAnalysis.queryAvailableAnalyses(request.data["ParticipantId"], "TimeSeriesAnalysis")
            return Response(status=200, data=Overview)

        elif request.data["RequestType"] == "RequestData":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId", "ActiveChannels"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            if "ProcessingConfiguration" in request.data.keys():
                userConfig, _ = Database.retrieveProcessingSettings({"ProcessingConfiguration": request.data["ProcessingConfiguration"]})
            else:
                userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)

            result = Database.getCachedResult("/queryTimeseriesAnalysis", request.data["ParticipantId"], {**userConfig, **request.data})
            if result:
                return Response(status=200, data=result)

            Analysis = DataAnalysis.processTimeseriesAnalysis(request.data["ParticipantId"], request.data["AnalysisId"], userConfig)
            if not request.data["ActiveChannels"] == "RequestAllChannel":
                Analysis = DataAnalysis.selectRecordingChannel(Analysis, request.data["ActiveChannels"])

            Database.saveCachedResult(Analysis, "/queryTimeseriesAnalysis", request.data["ParticipantId"], {**userConfig, **request.data})
            return Response(status=200, data=Analysis)

        elif request.data["RequestType"] == "DeleteCache":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            recording = models.Recording.find(uid=request.data["AnalysisId"])
            if not recording.source.owner.uid == request.data["ParticipantId"]:
                return Response(status=400, data={"message": "Permission Denied"})
            
            DataAnalysis.deleteProcessedData(recording=recording)
            return Response(status=200)

        return Response(status=400, data={"message": "Malformed Input"})
    
class QueryNeuralActivitySnapshot(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        if request.data["RequestType"] == "RequestAll":
            if "ProcessingConfiguration" in request.data.keys():
                userConfig, _ = Database.retrieveProcessingSettings({"ProcessingConfiguration": request.data["ProcessingConfiguration"]})
            else:
                userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)

            result = Database.getCachedResult("/queryNeuralActivitySnapshot", request.data["ParticipantId"], {**userConfig, **request.data})
            if result:
                return Response(status=200, data=result)

            Analysis = DataAnalysis.queryNeuralActivitySnapshot(request.data["ParticipantId"], userConfig)
            Database.saveCachedResult(Analysis, "/queryNeuralActivitySnapshot", request.data["ParticipantId"], {**userConfig, **request.data})
            return Response(status=200, data=Analysis)
        
        elif request.data["RequestType"] == "DeleteCache":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            recording = models.Recording.find(uid=request.data["AnalysisId"])
            if not recording.source.owner.uid == request.data["ParticipantId"]:
                return Response(status=400, data={"message": "Permission Denied"})
            
            DataAnalysis.deleteProcessedData(recording=recording)
            return Response(status=200)

        return Response(status=400, data={"message": "Malformed Input"})
    
class QueryChronicNeuralActivity(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        if request.data["RequestType"] == "RequestAll":
            if "ProcessingConfiguration" in request.data.keys():
                userConfig, _ = Database.retrieveProcessingSettings({"ProcessingConfiguration": request.data["ProcessingConfiguration"]})
            else:
                userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)

            result = Database.getCachedResult("/queryChronicNeuralActivity", request.data["ParticipantId"], {**userConfig, **request.data})
            if result:
                return Response(status=200, data=result)

            Analysis = DataAnalysis.queryChronicNeuralActivity(request.data["ParticipantId"], userConfig)
            Database.saveCachedResult(Analysis, "/queryChronicNeuralActivity", request.data["ParticipantId"], {**userConfig, **request.data})
            return Response(status=200, data=Analysis)

class QueryCustomizedAnalysis(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        if request.data["RequestType"] == "RequestList":
            analysis = models.Analysis.find_all(type="CustomizedAnalysis", metadata__ParticipantId= request.data["ParticipantId"])
            return Response(status=200, data=[i.get_info() for i in analysis])

        elif request.data["RequestType"] == "ProcessingNodes":
            nodes = DataAnalysis.queryProcessingNodes()
            return Response(status=200, data=nodes)

        elif request.data["RequestType"] == "NewAnalysis":
            analysis = models.Analysis.create(name="Unnamed", type="CustomizedAnalysis", metadata={
                "ParticipantId": request.data["ParticipantId"]
            })
            
            info = analysis.get_info()
            return Response(status=200, data=info)

        elif request.data["RequestType"] == "EditAnalysis":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "AnalysisId", "AnalysisName", "RequestType"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            analysis = models.Analysis.find(uid=request.data["AnalysisId"], type="CustomizedAnalysis", metadata__ParticipantId=request.data["ParticipantId"])
            if not analysis:
                return Response(status=403)

            analysis.name = request.data["AnalysisName"]
            analysis.save()
            return Response(status=200)
        
        elif request.data["RequestType"] == "SaveAnalysisPipeline":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "AnalysisId", "Nodes", "Edges", "StartProcessing", "RequestType"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            analysis = models.Analysis.find(uid=request.data["AnalysisId"], type="CustomizedAnalysis", metadata__ParticipantId=request.data["ParticipantId"])
            if not analysis:
                return Response(status=403)
            
            analysis.metadata["Results"] = False
            analysis.metadata["Nodes"] = request.data["Nodes"]

            # Reset Results
            for i in analysis.metadata["Nodes"]:
                if "Result" in i["data"].keys():
                    del i["data"]["Result"]

            analysis.metadata["Edges"] = request.data["Edges"]

            try:
                if request.data["StartProcessing"]:
                    DataAnalysis.processCustomizedPipeline(analysis)
                    analysis.metadata["Results"] = True
            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})
            
            analysis.save()
            Overview = DataAnalysis.queryCustomizedAnalysis(request.data["ParticipantId"], analysis)
            return Response(status=200, data=Overview)

        elif request.data["RequestType"] == "DeleteAnalysis":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "AnalysisId", "RequestType"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            analysis = models.Analysis.find(uid=request.data["AnalysisId"], type="CustomizedAnalysis", metadata__ParticipantId=request.data["ParticipantId"])
            if not analysis:
                return Response(status=403)

            analysis.delete()
            return Response(status=200)

        elif request.data["RequestType"] == "AnalysisOverview":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "AnalysisId", "RequestType"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            analysis = models.Analysis.find(uid=request.data["AnalysisId"], type="CustomizedAnalysis", metadata__ParticipantId=request.data["ParticipantId"])
            if not analysis:
                return Response(status=403)
            
            Overview = DataAnalysis.queryCustomizedAnalysis(request.data["ParticipantId"], analysis)
            return Response(status=200, data=Overview)
        
        return Response(status=400, data={"message": "Malformed Input"})