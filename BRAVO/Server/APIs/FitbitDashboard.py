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
Fitbit Dashboard APIs
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

import rest_framework.views as RestViews
import rest_framework.parsers as RestParsers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.conf import settings

from Server import models
from modules.HelperFunctions import sanitize_input, get_or_none, PKCE_code_challenger
from modules import Database, DataCurator
from modules.Fitbit import DataQuery, DataManager

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

class FitbitAuthHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "ParticipantId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        Participant = models.Participant.find(uid=request.data["ParticipantId"])
        if not Participant:
            return Response(status=403)

        device = models.FitbitDevice.find(owner=Participant)
        if not device:
            device = models.FitbitDevice.create(owner=Participant)
        
        if request.data["RequestType"] == "RequestURL":
            if len(device.auth.keys()) > 0:
                return Response(status=200, data=device.date_periods)

            challenger = PKCE_code_challenger(device.pkce)
            FitbitAuthURL = "https://www.fitbit.com/oauth2/authorize?" + urlencode({
                "response_type": "code",
                "client_id": os.environ["FIBIT_CLIENT_ID"],
                "code_challenge": challenger,
                "code_challenge_method": "S256",
                "state": device.uid,
                "redirect_uri": "https://bravo-api.jcagle.solutions/oath/fitbit_redirect"
            })
            FitbitAuthURL += "&scope=activity+cardio_fitness+electrocardiogram+heartrate+irregular_rhythm_notifications+location+nutrition+oxygen_saturation+profile+respiratory_rate+settings+sleep+social+temperature+weight"
            return Response(status=200, data={"OAuthURL": FitbitAuthURL})
        
        elif request.data["RequestType"] == "VerifyToken":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "ParticipantId", "TokenURL"]):
                return Response(status=400, data={"message": "Malformed Input"})

            if not request.data["TokenURL"].startswith("https://bravo-api.jcagle.solutions/oath/fitbit_redirect?"):
                return Response(status=400, data={"message": "Malformed Input"})

            tokenURL = parse_qs(request.data["TokenURL"].replace("https://bravo-api.jcagle.solutions/oath/fitbit_redirect?",""))
            if not len(tokenURL.keys()) == 2:
                return Response(status=400, data={"message": "Malformed Input"})

            if not tokenURL["state"][0] == device.uid + "#_=_":
                return Response(status=400, data={"message": "Verification Failed"})

            data = DataQuery.retrieveToken(tokenURL["code"][0], device.pkce)
            if not data:
                return Response(status=400, data={"message": "Verification Failed"})

            device.auth = data
            device.save()
            return Response(status=200)
            
        elif request.data["RequestType"] == "SetAuthPeriod":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "ParticipantId", "DatePeriods"]):
                return Response(status=400, data={"message": "Malformed Input"})

            if len(device.auth.keys()) == 0:
                return Response(status=400, data={"message": "Verification Failed"})

            if not type(request.data["DatePeriods"]) == list:
                return Response(status=400, data={"message": "Malformed Input"})
            for i in range(len(request.data["DatePeriods"])):
                if not type(request.data["DatePeriods"][i]) == list:
                    return Response(status=400, data={"message": "Malformed Input"})
                for j in range(len(request.data["DatePeriods"])):
                    request.data["DatePeriods"][i][j] = float(request.data["DatePeriods"][i][j])

            device.date_periods = request.data["DatePeriods"]
            device.save()
            return Response(status=200)
        
        return Response(status=400, data={"message": "Malformed Input"})

class QueryFitbitData(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        Participant = models.Participant.find(uid=request.data["ParticipantId"])
        device = models.FitbitDevice.find(owner=Participant)
        if not device:
            device = models.FitbitDevice.create(owner=Participant)
        
        if len(device.auth.keys()) == 0:
            return Response(status=400, data={"message": "Verification Failed"})

        Data = DataManager.loadFitbitData(Participant)
        DataManager.calculateDataDifference(device, Data)

        #Data = DataQuery.queryAllData(device, 0, 0)
        #DataManager.saveFitbitData(Participant, Data)

        return Response(status=200)
