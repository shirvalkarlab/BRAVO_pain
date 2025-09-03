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
Empatica Dashboard APIs
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
import json
import traceback
from copy import deepcopy
from pathlib import Path
import hmac, hashlib, base64
from urllib.parse import urlencode, parse_qs
import pickle

import rest_framework.views as RestViews
import rest_framework.parsers as RestParsers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.conf import settings

from Server import models
from modules.HelperFunctions import sanitize_input, get_or_none, json_compliant_handler, lttb_optimized, minimum_change_eliminator
from modules import Database, DataCurator
from modules.Empatica import DataManager

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

class QueryEmpaticaData(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        Permissions = Database.checkAccessPermission(request.user, request.data["ParticipantId"], 
                                study_uid=request.user.configuration["ActiveStudy"] if "ActiveStudy" in request.user.configuration.keys() else None)
        if not Permissions:
            return Response(status=403)
        
        APIAccess = hasattr(request.user, "api_access")
        Participant = models.Participant.find(uid=request.data["ParticipantId"])
        if request.data["RequestType"] == "RequestOverview":
            Data = DataManager.loadEmpaticaDataOverview(Participant)
            return Response(status=200, data=Data)

        elif request.data["RequestType"] == "RequestData":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ChannelName"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            Data = DataManager.loadEmpaticaData(Participant, channel_name=request.data["ChannelName"])
            if not APIAccess:
                for i in range(len(Data)):
                    if len(Data[i]["Data"]) > int(Data[i]["Time"][-1] - Data[i]["Time"][0])*10:
                        Data[i]["Time"], Data[i]["Data"] = lttb_optimized(Data[i]["Time"], Data[i]["Data"], threshold=int((Data[i]["Time"][-1] - Data[i]["Time"][0]) * 10))
                        #Data[i]["Time"], Data[i]["Data"] = minimum_change_eliminator(Data[i]["Time"], Data[i]["Data"], threshold=0.5)
                        
            Data = json_compliant_handler(Data)
            return Response(status=200, data=Data)
            
        return Response(status=200)

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def get(self, request):
        ParticipantId = self.request.query_params.get('ParticipantId')
        Permissions = Database.checkAccessPermission(request.user, ParticipantId, 
                                study_uid=request.user.configuration["ActiveStudy"] if "ActiveStudy" in request.user.configuration.keys() else None)
        if not Permissions:
            return Response(status=403)
        
        Participant = models.Participant.find(uid=ParticipantId)
        device = models.FitbitDevice.find(owner=Participant)
        if not device:
            device = models.FitbitDevice.create(owner=Participant)
        
        if len(device.auth.keys()) == 0:
            return Response(status=400, data={"message": "Verification Failed"})

        Data = DataManager.loadFitbitData(Participant)
        result = pickle.dumps(Data)
        return HttpResponse(bytes(result), status=200, headers={
            "Content-Type": "application/octet-stream"
        })
