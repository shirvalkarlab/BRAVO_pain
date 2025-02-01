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
Database Participant APIs
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

from django.contrib.auth import authenticate, login, logout

import rest_framework.views as RestViews
import rest_framework.parsers as RestParsers
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.conf import settings

from modules.HelperFunctions import sanitize_input, get_or_none
from modules import Database, Auth
from Server import models

class QueryParticipants(RestViews.APIView):
    
    permission_classes = [IsAuthenticated,]
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        AllParticipants = []
        institute = request.user.institute
        if institute:
            AllParticipants = models.Participant.from_institute(institute)

        if "ParticipantGroupId" in request.data.keys():
            study = models.Study.find(uid=request.data["ParticipantGroupId"])
            if study:
                AllParticipants = study.participants

        AllParticipantInfos = []
        for i in range(len(AllParticipants)):
            ParticipantInfo = AllParticipants[i].get_info()
            ParticipantInfo["DBSDevices"] = Database.extractParticipantDevices(AllParticipants[i])
            AllParticipantInfos.append(ParticipantInfo)
        return Response(status=200, data=AllParticipantInfos)

class QueryParticipantInformation(RestViews.APIView):
    
    permission_classes = [IsAuthenticated,]
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        ParticipantInfo = Database.extractParticipantInformation(request.data["ParticipantId"])
        return Response(status=200, data=ParticipantInfo)

class UpdateParticipantInformation(RestViews.APIView):
    
    permission_classes = [IsAuthenticated,]
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId"], accepted_keys=["ParticipantId", "MergeWith", "Name", "DOB", "Sex", "Diagnosis", "DiagnosisStartTime", "Tags"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkManagePermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        Participant = models.Participant.find(uid=request.data["ParticipantId"])

        if "MergeWith" in request.data.keys():
            if not Database.checkManagePermission(request.user, request.data["MergeWith"]):
                return Response(status=403)

            TargetParticipant = models.Participant.find(uid=request.data["MergeWith"])
            try:
                Database.mergeParticipants(source=Participant, target=TargetParticipant)
            except Exception as e:
                return Response(status=400, data={"message": str(e)})
            return Response(status=200)

        if "Name" in request.data.keys():
            Participant.name = request.data["Name"]
        if "DOB" in request.data.keys():
            Participant.date_of_birth = request.data["DOB"]
        if "Sex" in request.data.keys():
            Participant.sex = request.data["Sex"]
        if "Diagnosis" in request.data.keys():
            Participant.diagnosis = request.data["Diagnosis"]
        if "Tags" in request.data.keys():
            Participant.tags.clear()
            for tag_name in request.data["Tags"]:
                tag, _ = models.Tag.find_or_create(name=tag_name, owner=request.user)
                Participant.tags.add(tag)

        Participant.save()
        ParticipantInfo = Database.extractParticipantInformation(request.data["ParticipantId"])
        return Response(status=200, data=ParticipantInfo)

class DeleteParticipantInformation(RestViews.APIView):
    
    permission_classes = [IsAuthenticated,]
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId"], accepted_keys=["ParticipantId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkManagePermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        Participant = models.Participant.find(uid=request.data["ParticipantId"])
        Participant.delete()
        return Response(status=200)

class UpdateDeviceInformation(RestViews.APIView):
    
    permission_classes = [IsAuthenticated,]
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "DeviceId"], accepted_keys=["ParticipantId", "DeviceId", "Name", "Electrodes"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkManagePermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        Participant = models.Participant.find(uid=request.data["ParticipantId"])
        DBSDevice = models.DBSDevice.find(owner=Participant, uid=request.data["DeviceId"])
        if not DBSDevice:
            return Response(status=403)
        
        if "Name" in request.data.keys():
            DBSDevice.name = request.data["Name"]
        if "Electrodes" in request.data.keys():
            for electrode in request.data["Electrodes"]:
                lead = DBSDevice.electrodes.filter(uid=electrode["Id"]).first() # NOTE: SQL-Specific QuerySet
                lead.custom_name = electrode["CustomName"]
                lead.save()

        DBSDevice.save()
        ParticipantInfo = Database.extractParticipantInformation(request.data["ParticipantId"])
        return Response(status=200, data=ParticipantInfo)

class DeleteDeviceInformation(RestViews.APIView):
    
    permission_classes = [IsAuthenticated,]
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "DeviceId"], accepted_keys=["ParticipantId", "DeviceId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkManagePermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        Participant = models.Participant.find(uid=request.data["ParticipantId"])
        DBSDevice = models.DBSDevice.find(owner=Participant, uid=request.data["DeviceId"])
        if not DBSDevice:
            return Response(status=403)
        
        models.SourceFile.find_all(owner=Participant, metadata__Device=DBSDevice.uid).delete()
        DBSDevice.delete()
        ParticipantInfo = Database.extractParticipantInformation(request.data["ParticipantId"])
        return Response(status=200, data=ParticipantInfo)

class CreateParticipantInformation(RestViews.APIView):
    
    permission_classes = [IsAuthenticated,]
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["Name"], accepted_keys=["Name", "DOB", "Sex", "Diagnosis", "DiseaseStartTime"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        person, person_created = models.Participant.find_or_create(request.data["Name"], "", request.user.institute.uid)
        if person_created:
            if "DOB" in request.data.keys():
                person.date_of_birth = request.data["DOB"]
            if "Sex" in request.data.keys():
                person.sex = request.data["Sex"]
            if "Diagnosis" in request.data.keys():
                person.diagnosis = request.data["Diagnosis"]
            if "DiseaseStartTime" in request.data.keys():
                person.disease_start_time = request.data["DiseaseStartTime"]
            person.institute = request.user.institute
            person.save()
        else:
            return Response(status=400, data={"message": "Participant Name Used"})
        
        return Response(status=200, data=person.get_info())

class CheckAccessPermission(RestViews.APIView):
    
    permission_classes = [IsAuthenticated,]
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=200)
        
        return Response(status=403)