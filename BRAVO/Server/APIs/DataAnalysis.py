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

        elif request.data["RequestType"] == "RequestData":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId", "ActiveChannels"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)
            result = Database.getCachedResult("/queryTherapeuticEffectAnalysis", request.data["ParticipantId"], {**userConfig, **request.data})
            if result:
                return Response(status=200, data=result)

            Analysis = DataAnalysis.processTherapeuticAnalysis(request.data["ParticipantId"], request.data["AnalysisId"], userConfig)
            LimitedAnalysis = DataAnalysis.selectRecordingChannel(Analysis, request.data["ActiveChannels"])
            
            #Database.saveCachedResult(LimitedAnalysis, "/queryTherapeuticEffectAnalysis", request.data["ParticipantId"], {**userConfig, **request.data})
            return Response(status=200, data=LimitedAnalysis)

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
            userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)
            result = Database.getCachedResult("/queryChronicNeuralActivity", request.data["ParticipantId"], {**userConfig, **request.data})
            if result:
                return Response(status=200, data=result)

            Analysis = DataAnalysis.queryNeuralActivitySnapshot(request.data["ParticipantId"], userConfig)
            #LimitedAnalysis = DataAnalysis.selectRecordingChannel(Analysis, request.data["ActiveChannels"])
            #Database.saveCachedResult(LimitedAnalysis, "/queryTherapeuticEffectAnalysis", request.data["ParticipantId"], {**userConfig, **request.data})
            return Response(status=200, data=Analysis)
        
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
            userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)
            result = Database.getCachedResult("/queryChronicNeuralActivity", request.data["ParticipantId"], {**userConfig, **request.data})
            if result:
                return Response(status=200, data=result)

            Analysis = DataAnalysis.queryChronicNeuralActivity(request.data["ParticipantId"], userConfig)
            #LimitedAnalysis = DataAnalysis.selectRecordingChannel(Analysis, request.data["ActiveChannels"])
            #Database.saveCachedResult(LimitedAnalysis, "/queryTherapeuticEffectAnalysis", request.data["ParticipantId"], {**userConfig, **request.data})
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