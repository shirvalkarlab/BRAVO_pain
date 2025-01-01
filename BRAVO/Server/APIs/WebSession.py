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
Browser Session Configuration Module
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

from email.policy import default
import rest_framework.views as RestViews
import rest_framework.parsers as RestParsers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.conf import settings

from modules import Database
import json
from copy import deepcopy

defaultSessionConfigs = {
    "language": "en",
    "miniSidenav": False,
    "darkMode": False
}

def formatRequestSession(session):
    formattedSession = dict()
    if "patient_deidentified_id" in session.keys():
        formattedSession["patientID"] = session["patient_deidentified_id"]

    for key in defaultSessionConfigs.keys():
        if key in session.keys():
            formattedSession[key] = session[key]
        else:
            formattedSession[key] = deepcopy(defaultSessionConfigs[key])

    if "ProcessingSettings" in session.keys():
        formattedSession["processingConfiguration"] = session["ProcessingSettings"]

    return formattedSession

class QuerySessionConfig(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if request.user.is_authenticated:
            userSession = formatRequestSession(request.user.configuration)
            for key in request.data["session"].keys():
                if not key in userSession.keys():
                    userSession[key] = request.data["session"][key]
            return Response(status=200, data={"session": userSession, "user": request.user.get_info()})
        
        userSession = formatRequestSession({})
        return Response(status=200, data={"session": userSession, "user": {}})

class UpdateSessionConfig(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [AllowAny]
    
    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if request.user.is_authenticated:
            userConfig = request.user.configuration
            userConfig["ProcessingSettings"], _ = Database.retrieveProcessingSettings(userConfig)

            for key in request.data.keys():
                if key in defaultSessionConfigs.keys():
                    if key in request.data.keys():
                        userConfig[key] = request.data[key]

            request.user.configuration = userConfig
            request.user.save()

        return Response(status=200)

class QueryProcessingQueue(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        return Response(status=200, data=[])
