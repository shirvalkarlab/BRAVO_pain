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
Data Curators 
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os, pathlib
import uuid
import shutil
import datetime
import json
from cryptography.fernet import Fernet
import hmac, hashlib
import pickle
import numpy as np
import pandas as pd
from io import BytesIO

from Server import models
from modules.MedtronicPercept.Session import decodeMedtronicJSON
from modules.ExternalDevices.DelsysTrigno import decodeMDATData, decodeHDFCSVData
from modules.AlphaOmega.MPX import extractAlphaOmegaRecordings
from modules import Database, Therapy, Event

import time

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')
key = os.environ.get('DATASERVER_ENCRYPTION')
secureEncoder = Fernet(key)

def loadCacheFile(source_file):
    rawBytes = Database.loadSourceFile(source_file.pointer, source_file.hashed, bytes=True)
    rawBytes = secureEncoder.decrypt(rawBytes)
    return rawBytes

def saveCacheFile(filename, metadata, raw_bytes):
    source_file = models.SourceFile.create(type=metadata["UploadType"], metadata=metadata)
    source_file.name = filename
    source_file.pointer = DATABASE_PATH + "cache" + os.path.sep + source_file.uid + "_" + filename
    hashed = Database.saveSourceFile(secureEncoder.encrypt(raw_bytes), source_file.pointer, bytes=True)
    source_file.hashed = hashed
    source_file.save()
    return source_file

def MedtronicPerceptJSONDecoder(source_file, device=None, person=None):
    rawBytes = loadCacheFile(source_file)
    JSON = json.loads(rawBytes)
    DatabaseEntries = decodeMedtronicJSON(JSON)

    # Process Patient/Device/Electrode Information for Storage and Query
    if not device:
        device, device_created = models.DBSDevice.find_or_create(DatabaseEntries["SessionOverview"]["Device"]["SerialNumber"], DatabaseEntries["SessionOverview"]["Device"]["ConnectedLeads"], DatabaseEntries["SessionOverview"]["Device"]["Type"], source_file.metadata["Institute"])
        if not device_created and device.owner.institute_id == source_file.metadata["Institute"]:
            if not person:
                person = device.owner
            else:
                if not person.uid == device.owner.uid:
                    raise Exception("Attempting to upload data of another Participant. Please merge record before attempt so")

        else:
            if not person:
                person, person_created = models.Participant.find_or_create(DatabaseEntries["SessionOverview"]["Name"], DatabaseEntries["SessionOverview"]["MRN"], source_file.metadata["Institute"])
                if person_created:
                    person.date_of_birth = DatabaseEntries["SessionOverview"]["DOB"]
                    person.sex = DatabaseEntries["SessionOverview"]["Sex"]
                    person.diagnosis = DatabaseEntries["SessionOverview"]["Diagnosis"]
                    person.institute_id = source_file.metadata["Institute"]
                    person.save()
            
            device.owner = person
            device.name = DatabaseEntries["SessionOverview"]["Device"]["Name"]
            device.implanted_date = DatabaseEntries["SessionOverview"]["Device"]["ImplantDate"]
            device.implanted_location = DatabaseEntries["SessionOverview"]["Device"]["Location"]
            device.estimated_eol = DatabaseEntries["SessionOverview"]["Device"]["EOL"]
            device.device_bloodline = DatabaseEntries["SessionOverview"]["Device"]["Location"]
            device.save()
    
    elif not person:
        person = device.owner

    # This method is designed in a way that Electroe remain the same even with new DBS device. 
    for lead in DatabaseEntries["SessionOverview"]["Device"]["ConnectedLeads"]:
        electrode, electrode_created = models.Electrode.find_or_create(person, lead["name"])
        if electrode_created:
            electrode.type = lead["type"]
            electrode.custom_name = lead["custom_name"]
            electrode.channel_count = lead["channel_count"]
            electrode.channel_names = lead["channel_names"]
            electrode.save()
        
        if not device.electrodes.filter(uid=electrode.uid).exists():
            device.electrodes.add(electrode)
        
        if DatabaseEntries["SessionOverview"]["SessionTimestamp"] < electrode.implanted_date:
            electrode.implanted_date = DatabaseEntries["SessionOverview"]["SessionTimestamp"]
            electrode.save()
    
    # Therapy History Storage
    for therapy in DatabaseEntries["Therapies"]:
        if Therapy.checkDuplicate(device, therapy):
            continue 

        therapy_object = models.Therapy(**{key: therapy[key] for key in therapy.keys() if key in ["name", "type", "date"]}, source=source_file)
        therapy_object.save()

        stimulation_therapy = models.ElectricalTherapy(**{key: therapy[key] for key in therapy.keys() if key in ["group_type", "group_name", "group_id", "stimulation_type"]}, therapy=therapy_object)
        stimulation_therapy.save()

        for i in range(len(therapy["stimulation_settings"])):
            setting = therapy["stimulation_settings"][i]

            electrode = device.electrodes.filter(target__startswith=therapy["hemisphere"]).first()
            detail_setting = models.ElectricalStimulation(**{key: setting[key] for key in setting.keys() if key in ["contact", "return_contact", "amplitude", "amplitude_fraction", "amplitude_unit", "pulsewidth", "pulsewidth_unit", "frequency", "cycling", "cycling_period"]}, group=stimulation_therapy)
            detail_setting.electrode = electrode
            detail_setting.save()
            stimulation_therapy.stimulation_settings.add(detail_setting)
    
            detail_setting = models.AdaptiveTherapy(group=stimulation_therapy)
            if therapy["sensing_settings"][i]:
                detail_setting.sensing_type = therapy["sensing_settings"][i]["type"]
                detail_setting.sensing = therapy["sensing_settings"][i]["sensing"]
                
            if therapy["adaptive_settings"][i]:
                detail_setting.adaptive_type = therapy["adaptive_settings"][i]["type"]
                detail_setting.adaptive = therapy["adaptive_settings"][i]["adaptive"]
            detail_setting.save()
            stimulation_therapy.adaptive_settings.add(detail_setting)
    
    AllEntries = []
    for log in DatabaseEntries["TherapyChangeHistory"]:
        if models.TherapyModification.include(date=log["date"], type=log["type"], source__metadata__Device=device.uid, owner=person):
            continue
        AllEntries.append(models.TherapyModification(**log, source=source_file, owner=person))
    models.TherapyModification.objects.bulk_create(AllEntries)
    
    for survey in DatabaseEntries["SurveyRecordings"]:
        recording = models.Recording(**{key: survey[key] for key in survey.keys() if key in ["name", "type", "date", "metadata"]}, source=source_file)
        if models.Recording.include(date=recording.date, type=recording.type, metadata=recording.metadata, source__owner=person):
            recording.delete()
            continue
        filename = DATABASE_PATH + "recordings" + os.path.sep + person.uid + os.path.sep + recording.uid + ".bdat"
        hashed = Database.saveSourceFile(survey["recording"], filename)
        # TODO: Error handling
        if not hashed:
            print("Hashing Failed for Data Storage")
            print(recording.__dict__)
            continue 
        if models.Recording.include(hashed=hashed, source__owner=person):
            recording.delete()
        else:
            recording.pointer = filename
            recording.hashed = hashed
            recording.save()

    for stream in DatabaseEntries["StreamingRecordings"]:
        recording = models.Recording(**{key: stream[key] for key in stream.keys() if key in ["name", "type", "date", "metadata"]}, source=source_file)
        if models.Recording.include(date=recording.date, type=recording.type, metadata=recording.metadata, source__owner=person):
            recording.delete()
            continue
        filename = DATABASE_PATH + "recordings" + os.path.sep + person.uid + os.path.sep + recording.uid + ".bdat"
        hashed = Database.saveSourceFile(stream["recording"], filename)
        # TODO: Error handling
        if not hashed:
            print("Hashing Failed for Data Storage")
            print(recording.__dict__)
            continue 
        if models.Recording.include(hashed=hashed, source__owner=person):
            recording.delete()
        else:
            recording.pointer = filename
            recording.hashed = hashed
            recording.save()

    for stream in DatabaseEntries["ChronicRecordings"]:
        recording = models.Recording(**{key: stream[key] for key in stream.keys() if key in ["name", "type", "date", "metadata"]}, source=source_file)
        if models.Recording.include(date=recording.date, type=recording.type, metadata=recording.metadata, source__owner=person):
            recording.delete()
            continue

        filename = DATABASE_PATH + "recordings" + os.path.sep + person.uid + os.path.sep + recording.uid + ".bdat"
        hashed = Database.saveSourceFile(stream["recording"], filename)
        # TODO: Error handling
        if not hashed:
            print("Hashing Failed for Data Storage")
            print(recording.__dict__)
            continue
        if models.Recording.include(hashed=hashed, source__owner=person):
            recording.delete()
        else:
            recording.pointer = filename
            recording.hashed = hashed
            recording.save()

        full_recording = models.Recording.find(type="MedtronicChronicNeuralActivity", source__owner=person)
        if full_recording:
            full_recording.delete()

    for event in DatabaseEntries["EventRecordings"]:
        if models.DBSEvent.include(date=event["date"], type=event["type"], name=event["name"], source__owner=person):
            continue
        event_log = models.DBSEvent(**{key: event[key] for key in event.keys() if key in ["name", "type", "date"]}, source=source_file)
        event_log.save()
        if "data" in event.keys():
            recording = models.Recording(**{key: event[key] for key in event.keys() if key in ["name", "type", "date", "metadata"]}, source=source_file)
            recording.metadata = {**recording.metadata, **event["data"]}
            recording.save()
            event_log.data.add(recording)
    
    os.makedirs(DATABASE_PATH + "raws" + os.path.sep + person.uid, exist_ok=True)
    shutil.move(source_file.pointer, DATABASE_PATH + "raws" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".json")
    source_file.pointer = DATABASE_PATH + "raws" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".json"
    source_file.metadata["Timezone"] = DatabaseEntries["SessionOverview"]["SessionTimezone"]
    source_file.metadata["Device"] = device.uid
    source_file.owner = person
    source_file.save()

    person.last_update = models.current_time()
    person.save()
    return True

def NeuroImageStorage(source_file, person):
    os.makedirs(DATABASE_PATH + "imaging" + os.path.sep + person.uid, exist_ok=True)
    if source_file.pointer.endswith(".nii") or source_file.pointer.endswith(".nii.gz"):
        source_file.metadata["FileType"] = "NifTi"
    elif source_file.pointer.endswith(".stl"):
        source_file.metadata["FileType"] = "STL"
    elif source_file.pointer.endswith(".glb"):
        source_file.metadata["FileType"] = "Blender Scene"
    else:
        source_file.metadata["FileType"] = "Unknown"

    shutil.move(source_file.pointer, DATABASE_PATH + "imaging" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".image")
    source_file.pointer = DATABASE_PATH + "imaging" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".image"
    source_file.metadata["Timezone"] = ""
    source_file.metadata["Device"] = ""
    source_file.owner = person
    source_file.save()

def EventCSVDecoder(source_file, person):
    rawBytes = loadCacheFile(source_file)
    CSV = pd.read_csv(BytesIO(rawBytes), skiprows=0)

    if not "Time" in CSV.keys() or not "Annotation" in CSV.keys() or not "Type" in CSV.keys() or not "Duration" in CSV.keys():
        raise Exception("CSV Format Error")
    
    for i in CSV.index:
        Timestamp = 0
        try:
            Timestamp = datetime.datetime.fromisoformat(CSV["Time"][i]).timestamp()
        except:
            Timestamp = float(CSV["Time"][i])
        Event.addAnnotation(person.uid, CSV["Type"][i], CSV["Annotation"][i], Timestamp, CSV["Duration"][i])

def HDFCSVDecoder(source_file, person, startTime=None):
    rawBytes = loadCacheFile(source_file)
    TrignoData = decodeHDFCSVData(rawBytes)

    def CommonName(nameList):
        commonNames = []
        allSubString = nameList[0].split(" ")
        for i in range(len(allSubString)):
            Found = True
            for j in range(len(nameList)):
                if not allSubString[i] in nameList[j].split(" "):
                    Found = False 
            if Found:
                commonNames.append(allSubString[i])
        return commonNames

    for ProcessedData in TrignoData:
        if startTime and ProcessedData["StartTime"] == 0:
            ProcessedData["StartTime"] = startTime

        recording = models.Recording(**{
            "name": "", "type": "HDFCSV", "date": ProcessedData["StartTime"], "metadata": {
                "SensorType": ("_".join(CommonName(ProcessedData["ChannelNames"]))),
                "Duration": ProcessedData["Duration"],
                "ChannelNames": ProcessedData["ChannelNames"]
            }
        }, source=source_file)
        if models.Recording.include(date=recording.date, type=recording.type, metadata=recording.metadata, source__owner=person):
            recording.delete()
            continue

        filename = DATABASE_PATH + "recordings" + os.path.sep + person.uid + os.path.sep + recording.uid + ".bdat"
        hashed = Database.saveSourceFile(ProcessedData, filename)
        # TODO: Error handling
        if not hashed:
            print("Hashing Failed for Data Storage")
            print(recording.__dict__)
            continue 
        if models.Recording.include(hashed=hashed):
            recording.delete()
        else:
            recording.pointer = filename
            recording.hashed = hashed
            recording.save()

    os.makedirs(DATABASE_PATH + "raws" + os.path.sep + person.uid, exist_ok=True)
    shutil.move(source_file.pointer, DATABASE_PATH + "raws" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".mdat")
    source_file.pointer = DATABASE_PATH + "raws" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".mdat"
    source_file.metadata["Timezone"] = ""
    source_file.metadata["Device"] = ""
    source_file.owner = person
    source_file.save()

    person.last_update = models.current_time()
    person.save()
    
    models.SourceFile.purge(type="CachedResult", date__lt=person.last_update, metadata__Participant=person.uid)
    return True

def AlphaOmegaMPXDecoder(source_file, person, name=""):
    rawBytes = loadCacheFile(source_file)
    MPXData = extractAlphaOmegaRecordings(rawBytes)
    
    def CommonName(nameList):
        commonNames = []
        allSubString = nameList[0].split(" ")
        for i in range(len(allSubString)):
            Found = True
            for j in range(len(nameList)):
                if not allSubString[i] in nameList[j].split(" "):
                    Found = False 
            if Found:
                commonNames.append(allSubString[i])
        return commonNames

    for ProcessedData in MPXData:
        recording = models.Recording(**{
            "name": name, "type": "AOMPX", "date": ProcessedData["StartTime"], "metadata": {
                "SensorType": ("_".join(CommonName(ProcessedData["ChannelNames"]))),
                "Duration": ProcessedData["Duration"],
                "ChannelNames": ProcessedData["ChannelNames"]
            }
        }, source=source_file)
        if models.Recording.include(date=recording.date, type=recording.type, metadata=recording.metadata):
            recording.delete()
            continue

        filename = DATABASE_PATH + "recordings" + os.path.sep + person.uid + os.path.sep + recording.uid + ".bdat"
        hashed = Database.saveSourceFile(ProcessedData, filename)
        # TODO: Error handling
        if not hashed:
            print("Hashing Failed for Data Storage")
            print(recording.__dict__)
            continue 
        if models.Recording.include(hashed=hashed):
            recording.delete()
        else:
            recording.pointer = filename
            recording.hashed = hashed
            recording.save()

    os.makedirs(DATABASE_PATH + "raws" + os.path.sep + person.uid, exist_ok=True)
    shutil.move(source_file.pointer, DATABASE_PATH + "raws" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".mdat")
    source_file.pointer = DATABASE_PATH + "raws" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".mdat"
    source_file.metadata["Timezone"] = ""
    source_file.metadata["Device"] = ""
    source_file.owner = person
    source_file.save()

    person.last_update = models.current_time()
    person.save()
    
    models.SourceFile.purge(type="CachedResult", date__lt=person.last_update, metadata__Participant=person.uid)
    return True

def UFMDATDecoder(source_file, person):
    rawBytes = loadCacheFile(source_file)
    TrignoData = decodeMDATData(rawBytes)

    for ProcessedData in TrignoData:
        recording = models.Recording(**{
            "name": "", "type": "DelsysMDAT", "date": ProcessedData["StartTime"], "metadata": {
                "SensorType": ProcessedData["ChannelNames"][0].split(".")[0],
                "Duration": ProcessedData["Duration"],
                "ChannelNames": ProcessedData["ChannelNames"]
            }
        }, source=source_file)
        if models.Recording.include(date=recording.date, type=recording.type, metadata=recording.metadata):
            recording.delete()
            continue

        filename = DATABASE_PATH + "recordings" + os.path.sep + person.uid + os.path.sep + recording.uid + ".bdat"
        hashed = Database.saveSourceFile(ProcessedData, filename)
        # TODO: Error handling
        if not hashed:
            print("Hashing Failed for Data Storage")
            print(recording.__dict__)
            continue 
        if models.Recording.include(hashed=hashed):
            recording.delete()
        else:
            recording.pointer = filename
            recording.hashed = hashed
            recording.save()

    os.makedirs(DATABASE_PATH + "raws" + os.path.sep + person.uid, exist_ok=True)
    shutil.move(source_file.pointer, DATABASE_PATH + "raws" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".mdat")
    source_file.pointer = DATABASE_PATH + "raws" + os.path.sep + person.uid + os.path.sep + source_file.uid + ".mdat"
    source_file.metadata["Timezone"] = ""
    source_file.metadata["Device"] = ""
    source_file.owner = person
    source_file.save()

    person.last_update = models.current_time()
    person.save()
    
    models.SourceFile.purge(type="CachedResult", date__lt=person.last_update, metadata__Participant=person.uid)
    return True

def ImportBRAVOExport(source_file):
    rawBytes = loadCacheFile(source_file)
    if not rawBytes[:12].decode("utf-8") == "BRAVO EXPORT":
        raise Exception("Incorrect File Format")

    FernetEncoder = Fernet(source_file.metadata["Password"])

    HeaderSize = int.from_bytes(rawBytes[12:16], "little")
    Header = json.loads(FernetEncoder.decrypt(rawBytes[16:16+HeaderSize].decode("utf-8")))

    # Process Patient/Device/Electrode Information for Storage and Query
    person = models.Participant.find(uid=uuid.UUID(Header["Id"]).hex)
    if person:
        raise Exception("Participant with the same UID Existed")
    for i in range(len(Header["Devices"])):
        device = models.DBSDevice.find(serial_number=Header["Devices"][i]["SerialNumber"])
        if device:
            print(device.__dict__)
            raise Exception("Device ID Existed")
    
    person = models.Participant(uid=uuid.UUID(Header["Id"]).hex, name=Header["Name"], sex=Header["Gender"], date_of_birth=Header["DOB"],
                        diagnosis=Header["Diagnosis"], mrn=Header["MRN"], institute_id=source_file.metadata["Institute"])
    person.save()
    
    """
    DBSDevices = []
    for i in range(len(Header["Devices"])):
        device, _ = models.DBSDevice.find_or_create(Header["Devices"][i]["SerialNumber"], Header["Devices"][i]["Type"], source_file.metadata["Institute"])
        device.owner = person
        device.name = Header["Devices"][i]["Name"]
        device.implanted_date = Header["Devices"][i]["ImplantDate"]
        device.implanted_location = Header["Devices"][i]["Location"]
        device.device_bloodline = Header["Devices"][i]["Location"]
        device.save()
        DBSDevices.append(device)
    """

    currentIndex = 16+HeaderSize
    while currentIndex < len(rawBytes):
        PacketType = rawBytes[currentIndex:currentIndex+7].decode("utf-8")
        if PacketType == "NVMSEDA":
            PacketSize = int.from_bytes(rawBytes[currentIndex+7:currentIndex+11], "little")
            PacketContent = FernetEncoder.decrypt(rawBytes[currentIndex+11:currentIndex+11+PacketSize])
            metadata = {
                "UploadType": "MedtronicJSON",
                "Institute": source_file.metadata["Institute"],
                "Uploader": source_file.metadata["Uploader"],
                "UniqueHashed": hmac.new(HASH_KEY.encode("utf8"), PacketContent, hashlib.sha256).hexdigest()
            }
            json_file = saveCacheFile(person.uid + "_" + uuid.uuid4().hex + ".json", metadata, PacketContent)
            #lockFile = json_file.pointer + ".lock"
            if models.SourceFile.objects.exclude(pk=json_file.pk).filter(metadata__Institute=metadata["Institute"], metadata__UniqueHashed=metadata["UniqueHashed"]).exists():
                json_file.delete()
            else:
                try:
                    MedtronicPerceptJSONDecoder(json_file, person=person)
                except Exception as e:
                    json_file.delete()
                    person.delete()
                    raise Exception("Processing Error: " + str(e))
            currentIndex += 11+PacketSize

        elif PacketType == "EVSDADA":
            PacketSize = int.from_bytes(rawBytes[currentIndex+7:currentIndex+11], "little")
            PacketContent = json.loads(FernetEncoder.decrypt(rawBytes[currentIndex+11:currentIndex+11+PacketSize]).decode("utf-8"))
            models.Annotation(name=PacketContent["Name"], type=PacketContent["Type"], date=PacketContent["Date"], duration=PacketContent["Duration"], owner=person).save()
            currentIndex += 11+PacketSize

        elif PacketType == "AVSDADA":
            PacketSize = int.from_bytes(rawBytes[currentIndex+7:currentIndex+11], "little")
            PacketHeader = json.loads(FernetEncoder.decrypt(rawBytes[currentIndex+11:currentIndex+11+PacketSize]).decode("utf-8"))
            PacketContentSize = int.from_bytes(rawBytes[currentIndex+11+PacketSize:currentIndex+15+PacketSize], "little")
            PacketContent = rawBytes[currentIndex+15+PacketSize:currentIndex+15+PacketSize+PacketContentSize]
            
            metadata = {
                "UploadType": "ImportedSource",
                "Institute": source_file.metadata["Institute"],
                "Uploader": source_file.metadata["Uploader"],
                "UniqueHashed": source_file.uid
            }

            bin_file = models.SourceFile.find(type="ImportedSource", name=source_file.uid, owner=person)
            if not bin_file:
                bin_file = models.SourceFile(type="ImportedSource", name=source_file.uid, owner=person)
                bin_file.save()
            
            recording = models.Recording(name="ExternalRecording", type=PacketHeader["Type"], date=PacketHeader["Date"], metadata=PacketHeader, source=bin_file)
            filename = DATABASE_PATH + "recordings" + os.path.sep + person.uid + os.path.sep + recording.uid + ".bdat"
            hashed = Database.saveSourceFile(pickle.loads(PacketContent), filename)
            # TODO: Error handling
            if not hashed:
                print("Hashing Failed for Data Storage")
                print(recording.__dict__)
            else:
                recording.pointer = filename
                recording.hashed = hashed
                recording.save()
            
            currentIndex += 15+PacketSize+PacketContentSize


