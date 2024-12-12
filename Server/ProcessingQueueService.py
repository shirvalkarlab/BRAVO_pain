""""""
"""
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2023 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
"""
Crontab Queue Processor
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
@date: Thu Sep 16 12:05:09 2021
"""

import os
import sys
from pathlib import Path
import json
import datetime
import dateutil
import shutil
import time
import numpy as np
import pytz
from cryptography.fernet import Fernet
import pickle
from zipfile import ZipFile, ZIP_LZMA

import websocket
from BRAVO import asgi

from Backend import models
from modules.Percept import Sessions as PerceptSessions
from modules.Summit import Sessions as SummitSessions
from modules import Database, AnalysisBuilder
from decoder import Percept, Summit

DATABASE_PATH = os.environ.get('DATASERVER_PATH')

def processJSONUploads():
    ws = websocket.WebSocket()
    if models.ProcessingQueue.objects.filter(type="decodeJSON", state="InProgress").exists():
        print(datetime.datetime.now())
        BatchQueues = models.ProcessingQueue.objects.filter(type="decodeJSON", state="InProgress").order_by("datetime").all()
        for queue in BatchQueues:
            if not models.ProcessingQueue.objects.filter(state="InProgress", queue_id=queue.queue_id).exists():
                continue
            queue.state = "Processing"
            queue.save()
            try:
                ws.connect("ws://localhost:3001/socket/notification")
                ws.send(json.dumps({
                    "NotificationType": "TaskProcessing",
                    "TaskUser": str(queue.owner),
                    "TaskID": str(queue.queue_id),
                    "Authorization": os.environ["ENCRYPTION_KEY"],
                    "State": "Processing",
                    "Message": "",
                }))
                ws.close()
            except Exception as e:
                print(e)

            print(f"Start Processing {queue.descriptor['filename']}")
            newPatient = None
            ErrorMessage = ""
            ProcessingResult = ""
            
            try:
                JSON = Percept.decodeEncryptedJSON(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"], os.environ.get('ENCRYPTION_KEY'))
            except:
                queue.state = "Error"
                queue.descriptor["Message"] = "JSON Format Error"
                print(queue.descriptor["Message"])
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)

                continue

            try:
                user = models.PlatformUser.objects.get(unique_user_id=queue.owner)
                if (user.is_admin or user.is_clinician):
                    ProcessingResult, newPatient, _ = PerceptSessions.processPerceptJSON(user, queue.descriptor["filename"]) 
                else:
                    if "device_deidentified_id" in queue.descriptor:
                        ProcessingResult, _, _ = PerceptSessions.processPerceptJSON(user, queue.descriptor["filename"], device_deidentified_id=queue.descriptor["device_deidentified_id"])
                    elif "passkey" in queue.descriptor:
                        table = Database.getDeidentificationLookupTable(user, queue.descriptor["passkey"])
                        ProcessingResult, newPatient, _ = PerceptSessions.processPerceptJSON(user, queue.descriptor["filename"], lookupTable=table)

            except Exception as e:
                ErrorMessage = str(e)
                print(ErrorMessage)

            print(f"End Processing {queue.descriptor['filename']}")
            if ProcessingResult == "Success":
                queue.state = "Complete"
                queue.save()
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Complete",
                        "Message": ErrorMessage,
                    }))

                    if newPatient:
                        newPatient = Database.extractPatientTableRow(str(queue.owner), newPatient)
                        ws.send(json.dumps({
                            "NotificationType": "NewPatient",
                            "TaskUser": str(queue.owner),
                            "NewPatient": newPatient,
                            "Authorization": os.environ["ENCRYPTION_KEY"],
                        }))

                    ws.close()
                except Exception as e:
                    print(e)
            else:
                print(ErrorMessage)
                queue.state = "Error"
                queue.descriptor["Message"] = ErrorMessage
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                
                PerceptSessions.saveCacheJSON(queue.descriptor["filename"], json.dumps(JSON).encode('utf-8'))

def processAnnotations():
    ws = websocket.WebSocket()
    if models.ProcessingQueue.objects.filter(type="annotations", state="Error").exists():
        print(datetime.datetime.now())
        BatchQueues = models.ProcessingQueue.objects.filter(type="annotations", state="Error").order_by("datetime").all()
        for queue in BatchQueues:
            if not models.ProcessingQueue.objects.filter(state="Error", queue_id=queue.queue_id).exists():
                continue
            queue.state = "Processing"
            queue.save()
            ErrorMessage = ""
            try:
                ws.connect("ws://localhost:3001/socket/notification")
                ws.send(json.dumps({
                    "NotificationType": "TaskProcessing",
                    "TaskUser": str(queue.owner),
                    "TaskID": str(queue.queue_id),
                    "Authorization": os.environ["ENCRYPTION_KEY"],
                    "State": "Processing",
                    "Message": "",
                }))
                ws.close()
            except Exception as e:
                print(e)

            print(f"Start Processing {queue.descriptor['filename']}")
            try:
                AnalysisBuilder.processAnnotations(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"], queue.descriptor['patientId'])
            except Exception as e:
                queue.state = "Error"
                queue.descriptor["Message"] = str(e)
                print(queue.descriptor["Message"])
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                continue

            print(f"End Processing {queue.descriptor['filename']}")
            if ErrorMessage == "":
                queue.state = "Complete"
                queue.save()
            else:
                print(ErrorMessage)
                queue.state = "Error"
                queue.descriptor["Message"] = ErrorMessage
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)

def processExternalRecordingUpload():
    ws = websocket.WebSocket()
    if models.ProcessingQueue.objects.filter(type="externalCSVs", state="InProgress").exists():
        print(datetime.datetime.now())
        BatchQueues = models.ProcessingQueue.objects.filter(type="externalCSVs", state="InProgress").order_by("datetime").all()
        for queue in BatchQueues:
            if not models.ProcessingQueue.objects.filter(state="InProgress", queue_id=queue.queue_id).exists():
                continue
            queue.state = "Processing"
            queue.save()
            ErrorMessage = ""
            try:
                ws.connect("ws://localhost:3001/socket/notification")
                ws.send(json.dumps({
                    "NotificationType": "TaskProcessing",
                    "TaskUser": str(queue.owner),
                    "TaskID": str(queue.queue_id),
                    "Authorization": os.environ["ENCRYPTION_KEY"],
                    "State": "Processing",
                    "Message": "",
                }))
                ws.close()
            except Exception as e:
                print(e)

            print(f"Start Processing {queue.descriptor['filename']}")
            try:
                ProcessedData = AnalysisBuilder.processExternalRecordings(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])
            except:
                queue.state = "Error"
                queue.descriptor["Message"] = "CSV Format Error"
                print(queue.descriptor["Message"])
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                continue

            try:
                ProcessedData["SamplingRate"] = float(queue.descriptor["descriptor"]["SamplingRate"])
                ProcessedData["StartTime"] = float(queue.descriptor["descriptor"]["StartTime"])/1000 # Javascript Time is in Milliseconds
                ProcessedData["Missing"] = np.zeros(ProcessedData["Data"].shape)
                ProcessedData["Duration"] = ProcessedData["Data"].shape[0]/ProcessedData["SamplingRate"]
                recording = models.ExternalRecording(patient_deidentified_id=queue.descriptor["patientId"], 
                                         recording_type=queue.descriptor["descriptor"]["Label"], 
                                         recording_date=datetime.datetime.fromtimestamp(ProcessedData["StartTime"]).astimezone(pytz.utc),
                                         recording_duration=ProcessedData["Duration"])
                
                filename = Database.saveSourceFiles(ProcessedData, "ExternalRecording", "Raw", recording.recording_id, recording.patient_deidentified_id)
                recording.recording_datapointer = filename
                recording.save()
                
            except Exception as e:
                ErrorMessage = str(e)

            print(f"End Processing {queue.descriptor['filename']}")
            if ErrorMessage == "":
                queue.state = "Complete"
                queue.save()
            else:
                print(ErrorMessage)
                queue.state = "Error"
                queue.descriptor["Message"] = ErrorMessage
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                
    if models.ProcessingQueue.objects.filter(type="DelsysHDFCSV", state="InProgress").exists():
        print(datetime.datetime.now())
        BatchQueues = models.ProcessingQueue.objects.filter(type="DelsysHDFCSV", state="InProgress").order_by("datetime").all()
        for queue in BatchQueues:
            if not models.ProcessingQueue.objects.filter(state="InProgress", queue_id=queue.queue_id).exists():
                continue
            queue.state = "Processing"
            queue.save()
            ErrorMessage = ""
            try:
                ws.connect("ws://localhost:3001/socket/notification")
                ws.send(json.dumps({
                    "NotificationType": "TaskProcessing",
                    "TaskUser": str(queue.owner),
                    "TaskID": str(queue.queue_id),
                    "Authorization": os.environ["ENCRYPTION_KEY"],
                    "State": "Processing",
                    "Message": "",
                }))
                ws.close()
            except Exception as e:
                print(e)

            print(f"Start Processing {queue.descriptor['filename']}")
            try:
                ProcessedDataList = AnalysisBuilder.processTrignoHDFCSVRecordings(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])
            except Exception as e:
                print(e)
                queue.state = "Error"
                queue.descriptor["Message"] = str(e)
                print(queue.descriptor["Message"])
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                continue
            
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

            try:
                for ProcessedData in ProcessedDataList:
                    ProcessedData["StartTime"] = float(queue.descriptor["descriptor"]["StartTime"])/1000
                    recording = models.ExternalRecording(patient_deidentified_id=queue.descriptor["patientId"], 
                                            recording_type="DelsysCSV." + ("_".join(CommonName(ProcessedData["ChannelNames"]))), 
                                            recording_date=datetime.datetime.fromtimestamp(ProcessedData["StartTime"]).astimezone(pytz.utc),
                                            recording_duration=ProcessedData["Duration"])
                    filename = Database.saveSourceFiles(ProcessedData, "ExternalRecording", "Raw", recording.recording_id, recording.patient_deidentified_id)
                    recording.recording_datapointer = filename
                    recording.save()
                
            except Exception as e:
                ErrorMessage = str(e)

            print(f"End Processing {queue.descriptor['filename']}")
            if ErrorMessage == "":
                try:
                    os.remove(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])
                except:
                    pass
                queue.state = "Complete"
                queue.save()
            else:
                print(ErrorMessage)
                queue.state = "Error"
                queue.descriptor["Message"] = ErrorMessage
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)

    if models.ProcessingQueue.objects.filter(type="externalMDATs", state="InProgress").exists():
        print(datetime.datetime.now())
        BatchQueues = models.ProcessingQueue.objects.filter(type="externalMDATs", state="InProgress").order_by("datetime").all()
        for queue in BatchQueues:
            if not models.ProcessingQueue.objects.filter(state="InProgress", queue_id=queue.queue_id).exists():
                continue
            queue.state = "Processing"
            queue.save()
            ErrorMessage = ""
            try:
                ws.connect("ws://localhost:3001/socket/notification")
                ws.send(json.dumps({
                    "NotificationType": "TaskProcessing",
                    "TaskUser": str(queue.owner),
                    "TaskID": str(queue.queue_id),
                    "Authorization": os.environ["ENCRYPTION_KEY"],
                    "State": "Processing",
                    "Message": "",
                }))
                ws.close()
            except Exception as e:
                print(e)

            print(f"Start Processing {queue.descriptor['filename']}")
            try:
                ProcessedDataList = AnalysisBuilder.processMDATRecordings(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])
            except Exception as e:
                print(e)
                queue.state = "Error"
                queue.descriptor["Message"] = str(e)
                print(queue.descriptor["Message"])
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                continue

            try:
                for ProcessedData in ProcessedDataList:
                    recording = models.ExternalRecording(patient_deidentified_id=queue.descriptor["patientId"], 
                                            recording_type="DelsysMDAT." + ProcessedData["ChannelNames"][0].split(".")[0], 
                                            recording_date=datetime.datetime.fromtimestamp(ProcessedData["StartTime"]).astimezone(pytz.utc),
                                            recording_duration=ProcessedData["Duration"])
                    filename = Database.saveSourceFiles(ProcessedData, "ExternalRecording", "Raw", recording.recording_id, recording.patient_deidentified_id)
                    recording.recording_datapointer = filename
                    recording.save()
                
            except Exception as e:
                ErrorMessage = str(e)

            print(f"End Processing {queue.descriptor['filename']}")
            if ErrorMessage == "":
                try:
                    os.remove(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])
                except:
                    pass
                queue.state = "Complete"
                queue.save()
            else:
                print(ErrorMessage)
                queue.state = "Error"
                queue.descriptor["Message"] = ErrorMessage
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                
    if models.ProcessingQueue.objects.filter(type="bravoWearable", state="InProgress").exists():
        print(datetime.datetime.now())
        BatchQueues = models.ProcessingQueue.objects.filter(type="bravoWearable", state="InProgress").order_by("datetime").all()
        for queue in BatchQueues:
            if not models.ProcessingQueue.objects.filter(state="InProgress", queue_id=queue.queue_id).exists():
                continue
            queue.state = "Processing"
            queue.save()
            ErrorMessage = ""
            try:
                ws.connect("ws://localhost:3001/socket/notification")
                ws.send(json.dumps({
                    "NotificationType": "TaskProcessing",
                    "TaskUser": str(queue.owner),
                    "TaskID": str(queue.queue_id),
                    "Authorization": os.environ["ENCRYPTION_KEY"],
                    "State": "Processing",
                    "Message": "",
                }))
                ws.close()
            except Exception as e:
                print(e)

            print(f"Start Processing {queue.descriptor['filename']}")
            try:
                ProcessedDataList = AnalysisBuilder.processBRAVOWearableStructure(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])
            except Exception as e:
                print(e)
                queue.state = "Error"
                queue.descriptor["Message"] = str(e)
                print(queue.descriptor["Message"])
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                continue

            try:
                for ProcessedData in ProcessedDataList:
                    recording = models.ExternalRecording(patient_deidentified_id=queue.descriptor["patientId"], 
                                            recording_type="BRAVOWearable." + ProcessedData["ChannelNames"][0].split(".")[0], 
                                            recording_date=datetime.datetime.fromtimestamp(ProcessedData["StartTime"]).astimezone(pytz.utc),
                                            recording_duration=ProcessedData["Duration"])
                    filename = Database.saveSourceFiles(ProcessedData, "ExternalRecording", "Raw", recording.recording_id, recording.patient_deidentified_id)
                    recording.recording_datapointer = filename
                    recording.save()
                
            except Exception as e:
                ErrorMessage = str(e)

            print(f"End Processing {queue.descriptor['filename']}")
            if ErrorMessage == "":
                try:
                    os.remove(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])
                except:
                    pass
                queue.state = "Complete"
                queue.save()
            else:
                print(ErrorMessage)
                queue.state = "Error"
                queue.descriptor["Message"] = ErrorMessage
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                
def processSummitZIPUpload():
    ws = websocket.WebSocket()
    if models.ProcessingQueue.objects.filter(type="decodeSummitZIP", state="InProgress").exists():
        print(datetime.datetime.now())
        BatchQueues = models.ProcessingQueue.objects.filter(type="decodeSummitZIP", state="InProgress").order_by("datetime").all()
        for queue in BatchQueues:
            if not models.ProcessingQueue.objects.filter(state="InProgress", queue_id=queue.queue_id).exists():
                continue
            queue.state = "Processing"
            queue.save()
            ErrorMessage = ""
            try:
                ws.connect("ws://localhost:3001/socket/notification")
                ws.send(json.dumps({
                    "NotificationType": "TaskProcessing",
                    "TaskUser": str(queue.owner),
                    "TaskID": str(queue.queue_id),
                    "Authorization": os.environ["ENCRYPTION_KEY"],
                    "State": "Processing",
                    "Message": "",
                }))
                ws.close()
            except Exception as e:
                print(e)

            print(f"Start Processing {queue.descriptor['filename']}")
            try:
                with ZipFile(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"]) as zObject:
                    zObject.extractall(path=DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"].replace(".zip",""))
                
            except:
                queue.state = "Error"
                queue.descriptor["Message"] = "ZipFile Format Error"
                print(queue.descriptor["Message"])
                queue.save()
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                continue
            
            try:
                user = models.PlatformUser.objects.get(unique_user_id=queue.owner)
                if "device_deidentified_id" in queue.descriptor:
                    ProcessingResult, _, _ = SummitSessions.processSummitSession(user, DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"].replace(".zip",""), device_deidentified_id=queue.descriptor["device_deidentified_id"])
                    if not ProcessingResult == "Success":
                        raise Exception(ProcessingResult)
                    
            except Exception as e:
                ErrorMessage = str(e)
                print(ErrorMessage)

            print(f"End Processing {queue.descriptor['filename']}")
            if ErrorMessage == "":
                queue.state = "Complete"
                queue.save()

                shutil.rmtree(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"].replace(".zip",""))
                os.remove(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])

            else:
                queue.state = "Error"
                queue.descriptor["Message"] = ErrorMessage
                queue.save()

                shutil.rmtree(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"].replace(".zip",""))
                os.remove(DATABASE_PATH + "cache" + os.path.sep + queue.descriptor["filename"])
                
                try:
                    ws.connect("ws://localhost:3001/socket/notification")
                    ws.send(json.dumps({
                        "NotificationType": "TaskComplete",
                        "TaskUser": str(queue.owner),
                        "TaskID": str(queue.queue_id),
                        "Authorization": os.environ["ENCRYPTION_KEY"],
                        "State": "Error",
                        "Message": queue.descriptor["Message"],
                    }))
                    ws.close()
                except Exception as e:
                    print(e)
                

def exportDatabase():
    if models.ProcessingQueue.objects.filter(type="ExportDatabase", state="InProgress").exists():
        print(datetime.datetime.now())
        BatchQueues = models.ProcessingQueue.objects.filter(type="ExportDatabase", state="InProgress").order_by("datetime").all()
        for queue in BatchQueues:
            if not models.ProcessingQueue.objects.filter(state="InProgress", queue_id=queue.queue_id).exists():
                continue
            queue.state = "Processing"
            queue.save()
                
        key = os.environ.get('ENCRYPTION_KEY')
        secureEncoder = Fernet(key)

        exportKey = queue.descriptor["exportKey"]
        exportEncoder = Fernet(exportKey)

        if queue.descriptor["patientId"] == "All":
            user = models.PlatformUser.objects.get(unique_user_id=queue.owner)
            patients = models.Patient.objects.filter(institute=user.institute).all()
        else:
            patients = models.Patient.objects.filter(deidentified_id=queue.descriptor["patientId"]).all()

        counter = 0
        for patient in patients:
            try:
                ExportFile = open(DATABASE_PATH + "raws" + os.path.sep + str(queue.owner) + os.path.sep + str(patient.deidentified_id) + "_Export.bin", "wb+")
                devices = models.PerceptDevice.objects.filter(patient_deidentified_id=patient.deidentified_id).all() 
                Header = {
                    "Id": str(patient.deidentified_id),
                    "Name": (patient.getPatientFirstName(key) + " " + patient.getPatientLastName(key)) if queue.descriptor["identified"] else str(patient.deidentified_id),
                    "Gender": patient.getPatientGender(key),
                    "Diagnosis": patient.diagnosis,
                    "MRN": patient.getPatientMRN(key) if queue.descriptor["identified"] else "",
                    "DOB": patient.birth_date.timestamp() if queue.descriptor["identified"] else 0,
                    "Tags": patient.tags,
                    "Devices": [{
                        "Id": str(device.deidentified_id),
                        "SerialNumber": device.getDeviceSerialNumber(key) if queue.descriptor["identified"] else str(device.deidentified_id),
                        "Type": device.device_type,
                        "Name": device.device_name,
                        "ImplantDate": device.implant_date.timestamp(),
                        "Location": device.device_location,
                        "Leads": device.device_lead_configurations,
                    } for device in devices]
                }
                headerBytes = exportEncoder.encrypt(json.dumps(Header).encode("utf8"))

                # Write Initial Headers
                ExportFile.write("BRAVO EXPORT".encode("utf-8"))

                # Write Header Byte Size (4 bytes)
                ExportFile.write(np.array(len(headerBytes), dtype=np.int32).tobytes())
                ExportFile.write(headerBytes)

                availableSessions = models.PerceptSession.objects.filter(device_deidentified_id__in=[device.deidentified_id for device in devices]).all()
                for session in availableSessions:
                    with open(DATABASE_PATH + session.session_file_path, "rb") as file:
                        rawBytes = exportEncoder.encrypt(secureEncoder.decrypt(file.read()))
                
                    # Write Session Segment Header (7 bytes)
                    ExportFile.write("NVMSEDA".encode("utf-8"))
                    ExportFile.write(np.array(len(rawBytes), dtype=np.int32).tobytes())
                    ExportFile.write(rawBytes)

                for annotation in models.CustomAnnotations.objects.filter(patient_deidentified_id=patient.deidentified_id).all():
                    rawBytes = exportEncoder.encrypt(json.dumps({
                        "Type": annotation.event_type,
                        "Name": annotation.event_name,
                        "Date": annotation.event_time.timestamp(),
                        "Duration": annotation.event_duration,
                    }).encode("utf8"))

                    # Write Session Segment Header (7 bytes)
                    ExportFile.write("EVSDADA".encode("utf-8"))
                    ExportFile.write(np.array(len(rawBytes), dtype=np.int32).tobytes())
                    ExportFile.write(rawBytes)

                for recording in models.ExternalRecording.objects.filter(patient_deidentified_id=patient.deidentified_id).all():
                    rawBytes = exportEncoder.encrypt(json.dumps({
                        "Type": recording.recording_type,
                        "Info": recording.recording_info,
                        "Date": recording.recording_date.timestamp(),
                        "Duration": recording.recording_duration,
                    }).encode("utf8"))

                    # Write Session Segment Header (7 bytes)
                    ExportFile.write("AVSDADA".encode("utf-8"))
                    ExportFile.write(np.array(len(rawBytes), dtype=np.int32).tobytes())
                    ExportFile.write(rawBytes)

                    Data = Database.loadSourceDataPointer(recording.recording_datapointer)
                    pData = pickle.dumps(Data)
                    ExportFile.write(np.array(len(pData), dtype=np.int32).tobytes())
                    ExportFile.write(pData)

                ExportFile.close()

                counter += 1
                print(counter)
                
            except Exception as e:
                print(e)
                print(patient.deidentified_id)
                
        queue.state = "Complete"
        queue.delete()


if __name__ == '__main__':
    processJSONUploads()
    processSummitZIPUpload()
    processExternalRecordingUpload()
    processAnnotations()
    exportDatabase()
