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
Execute AI Model API Module
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
from modules.AIModels import ModelManager

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

class RequestPrediction(RestViews.APIView):
    """
    API View for AI/Machine Learning model predictions
    
    This view provides functionality for accessing and utilizing machine learning
    models for neural data analysis, including pre-trained models.
    
    **URL:** ``/requestAIPrediction``
    
    **Methods:** POST
    
    **Permissions:** Authenticated users with participant access permissions
    
    **Request Parameters:**
    
    :param RequestType: Type of operation to perform
    :type RequestType: str
    :param AnalysisName: Name of the analysis or model to execute
    :type AnalysisName: str
    :param Data: Input data for the model, typically in JSON format
    :type Data: dict
    
    **Response Format:**
    
    Model dependent.

    **HTTP Status Codes:**
    
    * ``200`` - Success
    * ``400`` - Malformed input
    * ``401`` - Unauthorized access
    * ``403`` - Insufficient permissions
    
    **Example Usage:**
    
    .. code-block:: matlab
    
        # Get available AI models
        Input = struct();
        Input.Data = Data.Signal.SignalSeries(1).Data(1,:);
        Input.SamplingRate = Data.Signal.SignalSeries(1).SamplingRate;
        Result = requester.RequestAIPrediction('BetaPeakDetection', Input);
    """
    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "AnalysisName", "Data"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if request.data["AnalysisName"] in ModelManager.Overview.keys():
            try:
                result = ModelManager.Overview[request.data["AnalysisName"]]["Method"](request.data["Data"])
                return Response(status=200, data=result)
            except Exception as e:
                return Response(status=400, data={"message": "Error executing model: " + str(e)})
            
        return Response(status=400, data={"message": "Model not found"})