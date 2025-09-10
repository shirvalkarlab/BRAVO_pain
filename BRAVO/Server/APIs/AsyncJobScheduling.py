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
from modules.AsyncJobScheduler import ProcessingScheduler

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

class QueryAsyncJobQueue(RestViews.APIView):
    
    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if request.data["RequestType"] == "GetAllStatus":
            AllJobs = models.AsyncJob.find_all(requester=request.user)
            Results = []
            for job in AllJobs:
                ret = ProcessingScheduler.CheckJobStatus(job)
                Results.append(ret)
            return Response(status=200, data=Results)

        if request.data["RequestType"] == "ClearCompletedJobs":
            models.AsyncJob.objects.filter(state="Completed", requester=request.user).delete()
            AllJobs = models.AsyncJob.find_all(requester=request.user)
            Results = []
            for job in AllJobs:
                ret = ProcessingScheduler.CheckJobStatus(job)
                Results.append(ret)
            return Response(status=200, data=Results)

        elif request.data["RequestType"] == "GetJobStatus":
            if not get_or_none(sanitize_input)(request.data, required_keys=["JobId"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            job = models.AsyncJob.find(uid=request.data["JobId"], requester=request.user)
            ret = ProcessingScheduler.CheckJobStatus(job)
            return Response(status=200, data=ret)

        return Response(status=400, data={"message": "Malformed Input"})
