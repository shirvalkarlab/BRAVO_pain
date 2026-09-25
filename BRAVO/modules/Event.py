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
Event and Annotations
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os, sys, pathlib
import hashlib, hmac
import shutil
from filelock import Timeout, FileLock

from Server import models
from modules.DecodeCommon import data_start as _data_start
from modules.MedtronicPercept import BrainSenseStream

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

def queryAnnotations(participant_uid, type=None, start_time=0, duration=0):
    """ Query all custom annotations of a specific type within a time window

    Args:
        participant_uid (string): Participant UUID (BRAVO_ID)
        type (string): Type of the custom annotation (i.e.: RecordingCustomEvent, ChronicCustomEvent)
        start_time (float, optional): If query from a desired time window, this is the start UNIX Timestamp of the window. Defaults to None.
        duration (float, optional): If query from a desired time window, this is the duration of the window in "seconds". Defaults to None.

    Returns:
        [info]: _description_
    """

    Participant = models.Participant.find(uid=participant_uid)
    QueryDict = {"owner": Participant}
    if type:
        QueryDict["type"] = type
    if start_time > 0 and duration > 0:
        QueryDict["date__gte"] = start_time
        QueryDict["date__lte"] = start_time+duration
    return [i.get_info() for i in models.Annotation.find_all(**QueryDict)]

def queryDBSEvents(participant_uid, type=None, source_files=[], start_time=0, duration=0, data=False):
    if len(source_files) == 0:
        Participant = models.Participant.find(uid=participant_uid)
        SourceFiles = models.SourceFile.find_all(owner=Participant)
    else:
        SourceFiles = source_files

    QueryDict = {"source__in": SourceFiles}
    if type:
        QueryDict["type"] = type
    if start_time > 0 and duration > 0:
        QueryDict["date__gte"] = start_time
        QueryDict["date__lte"] = start_time+duration
    # From the implant date on (the PI, 2026-09-24): events before it are the device on the bench.
    DataStart = _data_start.data_start_s(participant_uid)
    if DataStart > 0:
        QueryDict["date__gte"] = max(float(QueryDict.get("date__gte", 0)), DataStart)
    
    return [i.get_info(data=data) for i in models.DBSEvent.find_all(**QueryDict)]
        
def addAnnotation(participant_uid, type, name, date, duration=0):
    if not type in ["RecordingCustomEvent", "ChronicCustomEvent"]:
        raise Exception("Unknown Annotation Type")
    Participant = models.Participant.find(uid=participant_uid)
    Annotation = models.Annotation(name=name, date=date, duration=duration, type=type, owner=Participant)
    Annotation.save()
    if Annotation.type == "ChronicCustomEvent":
        models.SourceFile.purge(type="CachedResult", metadata__URL="/queryChronicNeuralActivity", metadata__Participant=participant_uid)
    elif Annotation.type == "RecordingCustomEvent":
        models.SourceFile.purge(type="CachedResult", metadata__URL="/queryTimeseriesAnalysis", metadata__Participant=participant_uid)
        models.SourceFile.purge(type="CachedResult", metadata__URL="/queryTherapeuticEffectAnalysis", metadata__Participant=participant_uid)
    return Annotation

def deleteAnnotation(participant_uid, annotation_uid):
    Participant = models.Participant.find(uid=participant_uid)
    Annotation = models.Annotation.find(uid=annotation_uid, owner=Participant)
    if Annotation:
        if Annotation.type == "ChronicCustomEvent":
            models.SourceFile.purge(type="CachedResult", metadata__URL="/queryChronicNeuralActivity", metadata__Participant=participant_uid)
        elif Annotation.type == "RecordingCustomEvent":
            models.SourceFile.purge(type="CachedResult", metadata__URL="/queryTimeseriesAnalysis", metadata__Participant=participant_uid)
            models.SourceFile.purge(type="CachedResult", metadata__URL="/queryTherapeuticEffectAnalysis", metadata__Participant=participant_uid)
        Annotation.delete()