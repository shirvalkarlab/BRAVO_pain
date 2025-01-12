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
from modules import Database, Event

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

class QuerySurveyForms(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if request.data["RequestType"] == "RequestAll":
            try:
                Institutes = models.Institute.find_all(members=request.user)
                AllForms = models.ScaleForms.find_all(institute__in=Institutes)
                UniqueForms = []
                for i in range(len(AllForms)):
                    nonUniqueFound = False
                    for j in range(len(UniqueForms)):
                        if AllForms[i].short_link == UniqueForms[j]["ShortLink"]:
                            nonUniqueFound = True
                    
                    if not nonUniqueFound:
                        UniqueForms.append(AllForms[i].get_info())

            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})

            return Response(status=200, data=UniqueForms)
        
        elif request.data["RequestType"] == "RequestForm":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "FormLink"]):
                return Response(status=400, data={"message": "Malformed Input"})

            if "VersionRel" in request.data.keys():
                rel = models.ParticipantLinkRel.find(link_code=request.data["VersionRel"])
                if not rel.record.short_link == request.data["FormLink"]:
                    return Response(status=400, data={"message": "Your Passcode does not apply to the Survey Form you are attempting to submit."})
                Form = rel.record.get_info()
                return Response(status=200, data=Form)

            form = models.ScaleForms.find(short_link=request.data["FormLink"])
            if not form:
                return Response(status=403)

            Form = form.get_info()
            Form["Editable"] = form.institute.has_permission(request.user)
            return Response(status=200, data=Form)

        elif request.data["RequestType"] == "SubmitForm":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "FormId", "Version", "Date", "Passcode", "FormResults"]):
                return Response(status=400, data={"message": "Malformed Input"})

            rel = models.ParticipantLinkRel.find(link_code=request.data["Passcode"])
            if not rel:
                return Response(status=403)

            try:
                result = json.loads(json.dumps(request.data["FormResults"]))
                form = models.ScaleForms.find(short_link=rel.record.short_link, uid=request.data["FormId"])
                if not form:
                    raise Exception("Unknown Survey Form ID")
                record = models.ScaleRecord.create(rel.participant, form, result, date=request.data["Date"])
            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})

            return Response(status=200)

        return Response(status=400, data={"message": "Malformed Input"})

class SetSurveyForms(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if request.data["RequestType"] == "Create":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "Institute", "FormName", "FormType", "FormContent"]):
                return Response(status=400, data={"message": "Malformed Input"})
                
            Institute = models.Institute.find(uid=request.data["Institute"])
            if not Institute:
                return Response(status=403)
            if not Institute.has_permission(request.user):
                return Response(status=403)

            try:
                form = models.ScaleForms.create(Institute, request.data["FormName"], request.data["FormType"])
            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})

            return Response(status=200, data=form.get_info())

        elif request.data["RequestType"] == "Update":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "FormLink", "FormContent"]):
                return Response(status=400, data={"message": "Malformed Input"})

            form = models.ScaleForms.find(short_link=request.data["FormLink"])
            if not form:
                return Response(status=403)
            if not form.institute.has_permission(request.user):
                return Response(status=403)

            try:
                Record = json.loads(json.dumps(request.data["FormContent"]))
                form.update_version(Record)

            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})

            return Response(status=200, data=form.get_info())

        return Response(status=400, data={"message": "Malformed Input"})
    
class DeleteSurveyForms(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["FormId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        form = models.ScaleForms.find(uid=request.data["FormId"])
        if not form:
            return Response(status=403)
        if not form.institute.has_permission(request.user):
            return Response(status=403)
        
        form.delete()
        return Response(status=200)

class QueryParticipantSurveyRecords(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "ParticipantId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkManagePermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        Participant = models.Participant.find(uid=request.data["ParticipantId"])

        if request.data["RequestType"] == "RequestAll":
            try:
                Institutes = models.Institute.find_all(members=request.user)
                AllForms = models.ScaleForms.find_all(institute__in=Institutes)
                AllForms = [i.get_info(count=Participant) for i in AllForms]
            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})
            
            try:
                Links = models.ParticipantLinkRel.find_all(participant=Participant)
                AllLinks = [i.get_info() for i in Links]
            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})
            
            return Response(status=200, data={"Links": AllLinks, "Forms": AllForms})

        elif request.data["RequestType"] == "AddLink":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "ParticipantId", "FormId"]):
                return Response(status=400, data={"message": "Malformed Input"})

            try:
                form = models.ScaleForms.find(uid=request.data["FormId"])
                rel = models.ParticipantLinkRel.create(Participant, form)

            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})
            
            return Response(status=200, data=rel.link_code)

        elif request.data["RequestType"] == "RequestRecords":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "ParticipantId", "FormId"]):
                return Response(status=400, data={"message": "Malformed Input"})

            try:
                form = models.ScaleForms.find(uid=request.data["FormId"])
                AllRecords = models.ScaleRecord.find_all(source=form, participant=Participant)
                AllRecords = [i.get_info() for i in AllRecords]

            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})
            
            return Response(status=200, data=AllRecords)

        return Response(status=404)
        
class QueryEventHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        AllEvents = []
        try:
            Annotations = Event.queryAnnotations(request.data["ParticipantId"], type="ChronicCustomEvent")
            AllEvents.extend(Annotations)
            DBSEvents = Event.queryDBSEvents(request.data["ParticipantId"], type="PatientControllerEvent", data=False)
            AllEvents.extend(DBSEvents)
        except Exception as e:
            print(traceback.format_exc())
            return Response(status=400, data={"message": str(e)})

        return Response(status=200, data={"Annotations": AllEvents})
    
class QueryAnnotationHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        AllEvents = []
        try:
            Annotations = Event.queryAnnotations(request.data["ParticipantId"])
            AllEvents.extend(Annotations)
        except Exception as e:
            print(traceback.format_exc())
            return Response(status=400, data={"message": str(e)})

        return Response(status=200, data={"Annotations": AllEvents})
    
class InsertAnnotationHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "EventType", "EventName", "EventTime", "EventDuration"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        try:
            Annotation = Event.addAnnotation(request.data["ParticipantId"], request.data["EventType"], request.data["EventName"], request.data["EventTime"], request.data["EventDuration"])
        except Exception as e:
            print(traceback.format_exc())
            return Response(status=400, data={"message": str(e)})

        return Response(status=200, data=Annotation.get_info())
    
class DeleteAnnotationHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "EventId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        try:
            Event.deleteAnnotation(request.data["ParticipantId"], request.data["EventId"])
        except Exception as e:
            print(traceback.format_exc())
            return Response(status=400, data={"message": str(e)})

        return Response(status=200)