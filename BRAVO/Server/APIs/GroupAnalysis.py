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
Group Data Analysis API Module
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

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.conf import settings

from Server import models
from .Participants import queryParticipantFunc
from modules.HelperFunctions import sanitize_input, get_or_none, json_compliant_handler
from modules import Database, DataCurator, DataAnalysis
from modules.AnalysisPipelineScripts import ExtractSpectralFeaturesDuringStimulation, ExtractSpectralFeaturesDuringSurvey


DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

class QueryGroupAnalysis(RestViews.APIView):
    
    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "AnalysisName"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if request.data["AnalysisName"] == "ExtractSpectralFeaturesDuringStimulation":
            if request.data["RequestType"] == "RequestTable":
                Participants = queryParticipantFunc(request.user)
                result = ExtractSpectralFeaturesDuringStimulation.QueryAnalysisResultTable(Participants)
                return Response(status=200, data=result)
            
            elif request.data["RequestType"] == "RequestPSD":
                if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "Contact"]):
                    return Response(status=400, data={"message": "Malformed Input"})
                
                Permissions = Database.checkAccessPermission(request.user, request.data["ParticipantId"], 
                                study_uid=request.user.configuration["ActiveStudy"] if "ActiveStudy" in request.user.configuration.keys() else None)
                if not Permissions:
                    return Response(status=403)
        
                result = ExtractSpectralFeaturesDuringStimulation.QueryAnalysisResultPSD(request.data["ParticipantId"], request.data["Contact"])
                return Response(status=200, data=result)
            
        elif request.data["AnalysisName"] == "ExtractSpectralFeaturesDuringSurvey":
            if request.data["RequestType"] == "RequestTable":
                Participants = queryParticipantFunc(request.user)
                result = ExtractSpectralFeaturesDuringSurvey.QueryAnalysisResultTable(Participants)
                return Response(status=200, data=result)
            
            elif request.data["RequestType"] == "RequestPSD":
                if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "Contact"]):
                    return Response(status=400, data={"message": "Malformed Input"})
                
                Permissions = Database.checkAccessPermission(request.user, request.data["ParticipantId"], 
                                study_uid=request.user.configuration["ActiveStudy"] if "ActiveStudy" in request.user.configuration.keys() else None)
                if not Permissions:
                    return Response(status=403)

                result = ExtractSpectralFeaturesDuringSurvey.QueryAnalysisResultPSD(request.data["ParticipantId"], request.data["Contact"])
                return Response(status=200, data=result)
            
        return Response(status=400, data={"message": "Malformed Input"})

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def get(self, request):
        AnalysisName = self.request.query_params.get('AnalysisName')
        Participants = queryParticipantFunc(request.user)
        
        if AnalysisName == "ExtractSpectralFeaturesDuringStimulation":
            result = ExtractSpectralFeaturesDuringStimulation.QueryAnalysisResultRaw(Participants)
            return HttpResponse(bytes(result), status=200, headers={
                "Content-Type": "application/octet-stream"
            })
        
        elif AnalysisName == "ExtractSpectralFeaturesDuringSurvey":
            result = ExtractSpectralFeaturesDuringSurvey.QueryAnalysisResultPSD(request.data["ParticipantId"], request.data["Contact"])
            return HttpResponse(bytes(result), status=200, headers={
                "Content-Type": "application/octet-stream"
            })
        
        return Response(status=403)
        