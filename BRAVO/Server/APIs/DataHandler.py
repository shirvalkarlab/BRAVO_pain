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
from modules import Database, DataCurator

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

class DataUploadHandler(RestViews.APIView):

    parser_classes = [RestParsers.MultiPartParser, RestParsers.FormParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "DataType", "Institute", "Metadata", "File"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        institute = models.Institute.find(name=request.data["Institute"])
        if not institute:
            return Response(status=403)
        
        if not institute.has_permission(request.user):
            return Response(status=403)
        
        if ".." in request.data["File"].name or os.path.sep in request.data["File"].name:
            return Response(status=400, data={"message": "Filename not Supported"})
        
        rawBytes = request.data["File"].read()
        metadata = {**{
            "UploadType": request.data["DataType"],
            "Institute": institute.pk,
            "Uploader": request.user.pk,
            "UniqueHashed": hmac.new(HASH_KEY.encode("utf8"), rawBytes, hashlib.sha256).hexdigest()
        }, **json.loads(request.data["Metadata"])}

        source_file = DataCurator.saveCacheFile(request.data["File"].name, metadata, rawBytes)
        if models.SourceFile.objects.exclude(pk=source_file.pk).filter(metadata__Institute=institute.pk, metadata__UniqueHashed=metadata["UniqueHashed"]).exists():
            print("Duplicate File Found")
            source_file.delete()
            return Response(status=301)
        
        lockFile = source_file.pointer + ".lock"
        if request.data["DataType"] == "MedtronicJSON":
            try:
                if not request.data["ParticipantId"] == "batch-upload":
                    if not Database.checkManagePermission(request.user, request.data["ParticipantId"]):
                        return Response(status=403)

                    person = models.Participant.find(uid=request.data["ParticipantId"])
                    if not person:
                        return Response(status=400, data={"message": "Participant not found."})
                    
                    DataCurator.MedtronicPerceptJSONDecoder(source_file, person=person)
                else:
                    DataCurator.MedtronicPerceptJSONDecoder(source_file)
                    
            except Exception as e:
                print(request.data["File"].name)
                print(traceback.format_exc())
                source_file.delete()
                return Response(status=400, data={"message": str(e)})
            
        elif request.data["DataType"] == "BRAVOExportv1":
            try:
                DataCurator.ImportBRAVOExport(source_file)
            except Exception as e:
                print(request.data["File"].name)
                print(traceback.format_exc())
                source_file.delete()
                return Response(status=400, data={"message": str(e)})
            source_file.delete()
            
        elif request.data["DataType"] == "UFMDAT":
            person = models.Participant.find(uid=request.data["ParticipantId"])
            if not person:
                return Response(status=400, data={"message": "Participant not found."})
            
            if not person.institute.uid == institute.uid:
                return Response(status=403)

            try:
                DataCurator.UFMDATDecoder(source_file, person)
            except Exception as e:
                print(request.data["File"].name)
                print(traceback.format_exc())
                source_file.delete()
                return Response(status=400, data={"message": str(e)})

        get_or_none(os.remove)(lockFile)
        return Response(status=200)

class RecordingTimeShiftHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "AnalysisId", "RecordingId", "Alignment"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        Analysis = models.Analysis.find(uid=request.data["AnalysisId"])
        if not Analysis:
            return Response(status=403)
        
        Recording = Analysis.recordings.filter(uid=request.data["RecordingId"]).first()
        if not Recording.source.owner.uid == request.data["ParticipantId"]:
            return Response(status=403)
        
        rel = models.RecordingRel.find(analysis=Analysis, recording=Recording)
        if not rel:
            return Response(status=403)
        
        try:
            Recording.adjusted_alignment = float(request.data["Alignment"])
            Recording.save()
        except:
            return Response(status=400, data={"message": "Time Alignment is not valid"})

        return Response(status=200)

class TimeSeriesRecordingHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "RecordingId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        recording = models.Recording.find(uid=request.data["RecordingId"])
        if not recording.source.owner.uid == request.data["ParticipantId"]:
            return Response(status=403)
        
        if request.data["RequestType"] == "RawTimeseries":
            Data = Database.loadSourceFile(recording.pointer, recording.hashed)
            Data["Alignment"] = recording.adjusted_alignment
            if "ChannelIndex" in request.data.keys():
                Data["Data"] = Data["Data"][:,int(request.data["ChannelIndex"])]
                Data["Missing"] = Data["Missing"][:,int(request.data["ChannelIndex"])]

            return Response(status=200, data=Data)


        return Response(status=400, data={"message": "Malformed Input"})