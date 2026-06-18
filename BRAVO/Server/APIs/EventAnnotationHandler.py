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
from modules.SurveyForms import RedcapForm
from modules.SurveyForms import RedcapImport, RedcapImportService

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
                if rel:
                    if not rel.record.short_link == request.data["FormLink"]:
                        return Response(status=400, data={"message": "Your Passcode does not apply to the Survey Form you are attempting to submit."})
                    Form = rel.record.get_info()
                    return Response(status=200, data=Form)

            form = models.ScaleForms.find(short_link=request.data["FormLink"])
            if not form:
                return Response(status=403)

            Form = form.get_info()
            Form["Editable"] = form.institute.has_permission(request.user, "Edit")
            if Form["Type"] == "Redcap Linked Survey" and type(Form["Record"]) == dict:
                Form["Record"] = Form["Record"]["FieldMapping"]
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

        elif request.data["RequestType"] == "RequestAvailabilityMatrix":
            # Per-patient score-availability summary: for every participant in the requesting
            # user's institute(s), list which forms/instruments have records, each with its field
            # list and record count. Powers the summary table in the Survey & Questionnaire module.
            if not request.user or not request.user.is_authenticated:
                return Response(status=403)
            try:
                Institutes = models.Institute.find_all(members=request.user)
                AllForms = list(models.ScaleForms.find_all(institute__in=Institutes))

                def _field_list(form):
                    rec = form.record
                    pages = rec if isinstance(rec, list) else (rec.get("FieldMapping", []) if isinstance(rec, dict) else [])
                    fields = []
                    for page in pages:
                        for q in page.get("questions", []):
                            if q.get("text") == "Time":
                                continue
                            if q.get("type") in ("score", "redcapForm", "cumulativeScore"):
                                fields.append(q.get("text", ""))
                    return fields

                # Pre-compute field lists per form once.
                form_fields = {form.uid: _field_list(form) for form in AllForms}

                Participants = []
                for institute in Institutes:
                    Participants.extend(list(models.Participant.from_institute(institute)))

                Matrix = []
                InstrumentSet = []  # ordered union of instrument names seen with records
                for participant in Participants:
                    row = {"ParticipantId": participant.uid, "ParticipantName": participant.name, "Instruments": []}
                    for form in AllForms:
                        count = models.ScaleRecord.objects.filter(source=form, participant=participant).count()
                        if count == 0:
                            continue
                        row["Instruments"].append({
                            "FormId": form.uid,
                            "Instrument": form.name,
                            "RecordType": form.record_type,
                            "Count": count,
                            "Fields": form_fields.get(form.uid, []),
                            "Version": form.record_version,
                        })
                        if form.name not in InstrumentSet:
                            InstrumentSet.append(form.name)
                    if row["Instruments"]:
                        Matrix.append(row)

            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})

            return Response(status=200, data={"Instruments": InstrumentSet, "Participants": Matrix})

        return Response(status=400, data={"message": "Malformed Input"})

class SetSurveyForms(RestViews.APIView):

    parser_classes = [RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType"]):
            return Response(status=400, data={"message": "Malformed Input"})
        
        if request.data["RequestType"] == "Create":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "Institute", "FormName", "FormType", "FormContent"], accepted_keys=["RequestType", "Institute", "FormName", "FormType", "FormContent", "RedcapInfo"]):
                return Response(status=400, data={"message": "Malformed Input"})
                
            Institute = models.Institute.find(uid=request.data["Institute"])
            if not Institute:
                return Response(status=403)
            if not Institute.has_permission(request.user, "Edit"):
                return Response(status=403)

            try:
                form = models.ScaleForms.create(Institute, request.data["FormName"], request.data["FormType"])
                if request.data["FormType"] == "Redcap Linked Survey" and "RedcapInfo" in request.data.keys():
                    if not RedcapForm.validateRedcapAPI(request.data["RedcapInfo"]["API"], request.data["RedcapInfo"]["Token"]):
                        form.delete()
                        raise Exception("Redcap API Validation Failed")
                        
                    form.record = {
                        "RedcapURL": request.data["RedcapInfo"]["API"],
                        "RedcapToken": request.data["RedcapInfo"]["Token"],
                        "FieldMapping": []
                    }
                    form.save()
                    
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
            if not form.institute.has_permission(request.user, "Edit"):
                return Response(status=403)

            try:
                Record = json.loads(json.dumps(request.data["FormContent"]))
                if form.record_type == "Redcap Linked Survey":
                    timeVariableFound = False
                    for page in Record:
                        for question in page["questions"]:
                            if question["text"] == "Time" and question["type"] == "redcapForm":
                                timeVariableFound = True
                                
                    if not timeVariableFound:
                        raise Exception("Redcap Linked Survey must contain a 'Time' variable of type 'redcapForm' to record submission time.")
                    
                    form.update_version({
                        "RedcapURL": form.record["RedcapURL"],
                        "RedcapToken": form.record["RedcapToken"],
                        "FieldMapping": Record
                    })
                else:
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
        if not form.institute.has_permission(request.user, "Delete"):
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
        
        Permissions = Database.checkAccessPermission(request.user, request.data["ParticipantId"], 
                                study_uid=request.user.configuration["ActiveStudy"] if "ActiveStudy" in request.user.configuration.keys() else None)
        if not Permissions:
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

            if not Database.checkManagePermission(request.user, request.data["ParticipantId"], "Edit"):
                return Response(status=403)
            
            try:
                form = models.ScaleForms.find(uid=request.data["FormId"])
                rel = models.ParticipantLinkRel.create(Participant, form)
                if form.record_type == "Redcap Linked Survey" and type(form.record) == dict and "RecordId" in request.data.keys():
                    rel.link_code = request.data["RecordId"]
                    rel.save()

            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})
            
            return Response(status=200, data=rel.link_code)

        elif request.data["RequestType"] == "RemoveLink":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "ParticipantId", "FormId"]):
                return Response(status=400, data={"message": "Malformed Input"})

            if not Database.checkManagePermission(request.user, request.data["ParticipantId"], "Edit"):
                return Response(status=403)
            
            try:
                form = models.ScaleForms.find(uid=request.data["FormId"])
                rel = models.ParticipantLinkRel.find(participant=Participant, record=form)
                if rel and form.record_type == "Redcap Linked Survey":
                    rel.delete()
                else:
                    raise Exception("Link Not Found")

            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})
            
            return Response(status=200, data=rel.link_code)

        elif request.data["RequestType"] == "RequestRecords":
            if not get_or_none(sanitize_input)(request.data, required_keys=["RequestType", "ParticipantId", "FormId"]):
                return Response(status=400, data={"message": "Malformed Input"})

            try:
                form = models.ScaleForms.find(uid=request.data["FormId"])
                if form.record_type == "Redcap Linked Survey":
                    rel = models.ParticipantLinkRel.find(participant=Participant, record=form)
                    AllRecords = RedcapForm.queryRedcapFormRecords(Participant, form, recordId=rel.link_code)
                else:
                    AllRecords = models.ScaleRecord.find_all(source=form, participant=Participant)
                    AllRecords = [i.get_info() for i in AllRecords]
                    AllRecords.sort(key=lambda x: x["Date"])

            except Exception as e:
                print(traceback.format_exc())
                return Response(status=400, data={"message": str(e)})
            
            return Response(status=200, data=AllRecords)

        return Response(status=404)


class ImportRedcapCSV(RestViews.APIView):
    """Offline ingest of a tidy REDCap export into native ScaleForms/ScaleRecord rows.

    Accepts EITHER a multipart CSV upload, OR a JSON body with inline rows / a server-side path:

      multipart:  File=<csv>, ParticipantId, [InstrumentName], [Layout], [Replace]
      json:       ParticipantId, [InstrumentName], [Layout], [Replace], and ONE of
                    Rows      : list[dict]  -- already-tidy per-report rows (wide), OR
                    ServerPath: str         -- a CSV path under the server's _pro_dump dir.

    The participant's institute owns the created form; the caller must have Upload (or Edit)
    permission on the participant. Returns the per-instrument import summary list.
    """

    parser_classes = [RestParsers.MultiPartParser, RestParsers.FormParser, RestParsers.JSONParser]
    permission_classes = [IsAuthenticated]

    # Imports may only read CSVs from this confined directory (the pipeline's PRO dump), never an
    # arbitrary server path supplied by the client.
    ALLOWED_SERVER_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "_pro_dump"
    )

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        import pandas as pd

        participant_id = request.data.get("ParticipantId")
        if not participant_id:
            return Response(status=400, data={"message": "Malformed Input"})

        # Permission: Upload right on the participant (Edit is a superset for non-batch use).
        if not Database.checkManagePermission(request.user, participant_id, "Upload"):
            if not Database.checkManagePermission(request.user, participant_id, "Edit"):
                return Response(status=403)

        Participant = models.Participant.find(uid=participant_id)
        if not Participant:
            return Response(status=403)
        institute = Participant.institute
        if institute is None:
            return Response(status=400, data={"message": "Participant has no institute to own the form."})
        if not institute.has_permission(request.user, "Edit"):
            return Response(status=403)

        instrument_name = request.data.get("InstrumentName") or None
        layout = request.data.get("Layout") or "auto"
        replace = str(request.data.get("Replace", "true")).lower() not in ("false", "0", "no")

        # ---- resolve the data source -------------------------------------------------------
        try:
            if "File" in request.data and hasattr(request.data["File"], "read"):
                fname = getattr(request.data["File"], "name", "")
                if ".." in fname or os.path.sep in fname:
                    return Response(status=400, data={"message": "Invalid file name"})
                source = pd.read_csv(request.data["File"], low_memory=False)
            elif request.data.get("Rows"):
                source = pd.DataFrame(request.data["Rows"])
            elif request.data.get("ServerPath"):
                # Confine to ALLOWED_SERVER_DIR (no traversal, must resolve inside the dump dir).
                name = os.path.basename(str(request.data["ServerPath"]))
                path = os.path.realpath(os.path.join(self.ALLOWED_SERVER_DIR, name))
                root = os.path.realpath(self.ALLOWED_SERVER_DIR)
                if not (path == root or path.startswith(root + os.sep)) or not os.path.isfile(path):
                    return Response(status=400, data={"message": "ServerPath not allowed"})
                source = pd.read_csv(path, low_memory=False)
            else:
                return Response(status=400, data={"message": "No CSV File, Rows, or ServerPath provided."})
        except Exception as e:
            print(traceback.format_exc())
            return Response(status=400, data={"message": "Could not read the provided data: %s" % str(e)})

        # ---- parse + persist ---------------------------------------------------------------
        try:
            results = RedcapImportService.import_export(
                Participant, institute, source,
                instrument_name=instrument_name, layout=layout, replace=replace,
            )
        except Exception as e:
            print(traceback.format_exc())
            return Response(status=400, data={"message": str(e)})

        if not results:
            return Response(status=400, data={"message": "No importable records found in the data."})

        total = sum(r["RecordsImported"] for r in results)
        return Response(status=200, data={"Instruments": results, "TotalRecords": total})


class QueryEventHandler(RestViews.APIView):

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
        
        AllEvents = []
        try:
            Annotations = Event.queryAnnotations(request.data["ParticipantId"], type="ChronicCustomEvent")
            AllEvents.extend(Annotations)
            DBSEvents = Event.queryDBSEvents(request.data["ParticipantId"], type="PatientControllerEvent", data=request.data["RequestType"] == "RequestData")
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
        
        Permissions = Database.checkAccessPermission(request.user, request.data["ParticipantId"], 
                                study_uid=request.user.configuration["ActiveStudy"] if "ActiveStudy" in request.user.configuration.keys() else None)
        if not Permissions:
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
        
        Permissions = Database.checkAccessPermission(request.user, request.data["ParticipantId"], 
                                study_uid=request.user.configuration["ActiveStudy"] if "ActiveStudy" in request.user.configuration.keys() else None)
        if not Permissions:
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
        
        Permissions = Database.checkAccessPermission(request.user, request.data["ParticipantId"], 
                                study_uid=request.user.configuration["ActiveStudy"] if "ActiveStudy" in request.user.configuration.keys() else None)
        if not Permissions:
            return Response(status=403)
        
        try:
            Event.deleteAnnotation(request.data["ParticipantId"], request.data["EventId"])
        except Exception as e:
            print(traceback.format_exc())
            return Response(status=400, data={"message": str(e)})

        return Response(status=200)