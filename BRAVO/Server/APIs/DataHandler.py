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
from io import BytesIO
import pandas as pd
import numpy as np

import rest_framework.views as RestViews
import rest_framework.parsers as RestParsers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.conf import settings

from Server import models
from modules.HelperFunctions import sanitize_input, get_or_none
from modules import Database, DataCurator, DataAnalysis, ImageDatabase

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
            
        elif request.data["DataType"] == "AlphaOmegaMPX":
            person = models.Participant.find(uid=request.data["ParticipantId"])
            if not person:
                return Response(status=400, data={"message": "Participant not found."})
            
            if not person.institute.uid == institute.uid:
                return Response(status=403)

            try:
                DataCurator.AlphaOmegaMPXDecoder(source_file, person)
            except Exception as e:
                print(request.data["File"].name)
                print(traceback.format_exc())
                source_file.delete()
                return Response(status=400, data={"message": str(e)})

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

        elif request.data["DataType"] == "HDFCSV":
            person = models.Participant.find(uid=request.data["ParticipantId"])
            if not person:
                return Response(status=400, data={"message": "Participant not found."})
            
            if not person.institute.uid == institute.uid:
                return Response(status=403)

            try:
                if "StartTime" in request.data.keys():
                    DataCurator.HDFCSVDecoder(source_file, person, startTime=request.data["StartTime"])
                else:
                    DataCurator.HDFCSVDecoder(source_file, person)
            except Exception as e:
                print(request.data["File"].name)
                print(traceback.format_exc())
                source_file.delete()
                return Response(status=400, data={"message": str(e)})

        elif request.data["DataType"] == "NeuroImage":
            person = models.Participant.find(uid=request.data["ParticipantId"])
            if not person:
                return Response(status=400, data={"message": "Participant not found."})
            
            if not person.institute.uid == institute.uid:
                return Response(status=403)

            try:
                DataCurator.NeuroImageStorage(source_file, person)
            except Exception as e:
                print(request.data["File"].name)
                print(traceback.format_exc())
                source_file.delete()
                return Response(status=400, data={"message": str(e)})

        get_or_none(os.remove)(lockFile)
        return Response(status=200)

class DataDownloadHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def get(self, request):
        ParticipantId = self.request.query_params.get('ParticipantId')
        CacheType = self.request.query_params.get('CacheType')

        if not Database.checkAccessPermission(request.user, ParticipantId):
            return Response(status=403)

        if CacheType == "queryTherapeuticEffectAnalysis":
            AnalysisId = self.request.query_params.get('AnalysisId')
            userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)
            FilePointer = DataAnalysis.downloadTherapeuticAnalysis(ParticipantId, AnalysisId, userConfig)
            
            with BytesIO() as fp:
                FilePointer.to_csv(fp, index=False)
                filename = "TherapeuticEffectAnalysis_" + ParticipantId + "_" + AnalysisId + ".csv"
                response = HttpResponse( fp.getvalue(), content_type="text/csv" )
                response["Content-Disposition"] = "attachment; filename=" + filename
                return response

        elif CacheType == "queryTimeseriesAnalysis":
            RecordingId = self.request.query_params.get('RecordingId')
            userConfig, _ = Database.retrieveProcessingSettings(request.user.configuration)
            FilePointer = DataAnalysis.downloadTimeseriesAnalysis(ParticipantId, RecordingId, userConfig)
            
            with BytesIO() as fp:
                FilePointer.to_csv(fp, index=False)
                filename = "Timeseries_" + ParticipantId + "_" + RecordingId + ".csv"
                response = HttpResponse( fp.getvalue(), content_type="text/csv" )
                response["Content-Disposition"] = "attachment; filename=" + filename
                return response

        elif CacheType == "queryImageModel":
            RecordingId = self.request.query_params.get('RecordingId')
            file_data = ImageDatabase.stlReader(ParticipantId, RecordingId)
            if not file_data:
                return Response(status=400, data={"message": "Recording does not exist."})

            return HttpResponse(bytes(file_data), status=200, headers={
                "Content-Type": "application/octet-stream"
            })
        return Response(status=200)
        
    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "CacheType", "DataId"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)

        if request.data["CacheType"] == "queryImageModel":
            file = models.SourceFile.find(uid=request.data["DataId"])
            if not file.owner.uid == request.data["ParticipantId"]:
                return Response(status=403)
            
            if file.metadata["FileType"] == "STL":
                file_data = DataCurator.loadCacheFile(file)
                return HttpResponse(bytes(file_data), status=200, headers={
                    "Content-Type": "application/octet-stream"
                })

        return Response(status=400, data={"message": "Malformed Input"})
        
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
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkAccessPermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        if request.data["RequestType"] == "Overview":
            Recordings = Database.listRecordings(request.data["ParticipantId"])
            return Response(status=200, data=Recordings)

        elif request.data["RequestType"] == "RawTimeseries":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "RecordingId"]):
                return Response(status=400, data={"message": "Malformed Input"})
        
            recording = models.Recording.find(uid=request.data["RecordingId"])
            if not recording.source.owner.uid == request.data["ParticipantId"]:
                return Response(status=403)
        
            Data = Database.loadSourceFile(recording.pointer, recording.hashed)
            Data["Alignment"] = recording.adjusted_alignment
            if "ChannelIndex" in request.data.keys():
                Data["Data"] = Data["Data"][:,int(request.data["ChannelIndex"])]
                Data["Missing"] = Data["Missing"][:,int(request.data["ChannelIndex"])]
            
            if not "Time" in Data.keys():
                Data["Time"] = np.arange(len(Data["Data"]))/Data["SamplingRate"]

            return Response(status=200, data=Data)
        return Response(status=400, data={"message": "Malformed Input"})

class DataSourceFileHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkManagePermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        if request.data["RequestType"] == "All":
            SourceFiles = Database.listSourceFiles(request.data["ParticipantId"])
            return Response(status=200, data=SourceFiles)
        
        elif request.data["RequestType"] == "Delete":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "SourceId"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            Participant = models.Participant.find(uid=request.data["ParticipantId"])
            source = models.SourceFile.find(uid=request.data["SourceId"], owner=Participant)
            if not source:
                return Response(status=400, data={"message": "Source File not found."})
            source.delete()
            return Response(status=200)

        return Response(status=400, data={"message": "Malformed Input"})
        
class NeuroImageFileHandler(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if not Database.checkManagePermission(request.user, request.data["ParticipantId"]):
            return Response(status=403)
        
        if request.data["RequestType"] == "ListAll":
            SourceFiles = Database.listSourceFiles(request.data["ParticipantId"], file_type="NeuroImage")
            return Response(status=200, data=SourceFiles)
        
        elif request.data["RequestType"] == "Delete":
            if not get_or_none(sanitize_input)(request.data, required_keys=["ParticipantId", "RequestType", "SourceId"]):
                return Response(status=400, data={"message": "Malformed Input"})
            
            Participant = models.Participant.find(uid=request.data["ParticipantId"])
            source = models.SourceFile.find(uid=request.data["SourceId"], owner=Participant)
            if not source:
                return Response(status=400, data={"message": "Source File not found."})
            source.delete()
            return Response(status=200)

        return Response(status=400, data={"message": "Malformed Input"})
        