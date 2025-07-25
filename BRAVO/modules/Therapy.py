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
Therapy Query Module
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
from datetime import datetime
import copy
import numpy as np
import pandas as pd
import uuid
from cryptography.fernet import Fernet

from Server import models

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')
key = os.environ.get('DATASERVER_ENCRYPTION')
secureEncoder = Fernet(key)

def queryTherapyHistory(Participant):
    """ Extract all therapy change logs in Percept related to a specific participant.

    This pipeline go through all therapy change logs and extract the time at which a group changes is made. 
    The pipeline will also extract the actual setting that the device is on before and after changes.

    Args:
    
    Returns:
      List of therapy group history ordered by time. 
    """

    TherapyModifications = []
    TherapyHistories = []
    TherapyDevices = []

    DBSDevices = models.DBSDevice.find_all(owner=Participant)
    DBSDeviceDict = {}
    for i in range(len(DBSDevices)):
        if not DBSDevices[i].serial_number in DBSDeviceDict.keys():
            DBSDeviceDict[DBSDevices[i].serial_number] = []
        DBSDeviceDict[DBSDevices[i].serial_number].append(DBSDevices[i])

    for key in DBSDeviceDict.keys():
        LeadCount = 0
        for i in range(len(DBSDeviceDict[key])):
            DeviceInfoTemp = DBSDeviceDict[key][0].get_info()
            if len(DeviceInfoTemp["Electrodes"]) > LeadCount:
                LeadCount = len(DeviceInfoTemp["Electrodes"])
                DeviceInfo = DeviceInfoTemp
        TherapyDevices.append(DeviceInfo)

        TherapyHistory = {
            "Device": DeviceInfo,
            "History": []
        }
        DeviceTherapyModification = {
            "Device": DeviceInfo,
            "History": []
        }

        for i in range(len(DBSDeviceDict[key])):
            device = DBSDeviceDict[key][i]
            SourceFiles = models.SourceFile.find_all(owner=Participant, metadata__Device=device.uid)
            TherapyHistory["History"].extend([i.get_info() for i in models.ElectricalTherapy.find_all(therapy__source__in=SourceFiles)])
            DeviceTherapyModification["History"].extend([i.get_info() for i in models.TherapyModification.find_all(source__in=SourceFiles)])

        DeviceTherapyModification["History"].sort(key=lambda x: x["Date"])
        TherapyHistory["History"] = [i for i in TherapyHistory["History"] if (i["Type"] in ["Pre-visit Therapy", "Post-visit Therapy", "Past Therapy"])]
        TherapyHistory["History"].sort(key=lambda x: x["Date"])
        TherapyHistories.append(TherapyHistory)
        
        LastTherapyChange = None
        VisitTimestamps = np.unique([i["Date"] for i in TherapyHistory["History"]])
        for i in range(len(VisitTimestamps)):
            LastTherapyChange = None
            for j in range(0, len(DeviceTherapyModification["History"])):
                if DeviceTherapyModification["History"][j]["Type"] == "TherapyChangeGroup":
                    if DeviceTherapyModification["History"][j]["Date"] > VisitTimestamps[i] and LastTherapyChange:
                        DeviceTherapyModification["History"].insert(j, {
                            "Id": uuid.uuid4().hex,
                            "Name": "",
                            "Type": "TherapyChangeGroup",
                            "Date": VisitTimestamps[i],
                            "Previous": LastTherapyChange,
                            "New": LastTherapyChange,
                        })
                        break
                    LastTherapyChange = DeviceTherapyModification["History"][j]["New"]
        
        if LastTherapyChange:
            DeviceTherapyModification["History"].append({
                "Id": uuid.uuid4().hex,
                "Name": "",
                "Type": "TherapyChangeGroup",
                "Date": VisitTimestamps[-1],
                "Previous": LastTherapyChange,
                "New": LastTherapyChange,
            })

        for j in range(len(DeviceTherapyModification["History"])):
            if DeviceTherapyModification["History"][j]["Type"] == "TherapyChangeGroup":
                GroupId = DeviceTherapyModification["History"][j]["New"]
                for k in range(len(TherapyHistory["History"])):
                    if TherapyHistory["History"][k]["GroupId"] == GroupId and TherapyHistory["History"][k]["Date"] > DeviceTherapyModification["History"][j]["Date"]:
                        if not "TherapyGroup" in DeviceTherapyModification["History"][j].keys():
                            DeviceTherapyModification["History"][j]["TherapyGroup"] = TherapyHistory["History"][k]
                        elif TherapyHistory["History"][k]["Date"] < DeviceTherapyModification["History"][j]["TherapyGroup"]["Date"]+24*3600 and DeviceTherapyModification["History"][j]["TherapyGroup"]["Type"] == "Past Therapy":
                            DeviceTherapyModification["History"][j]["TherapyGroup"] = TherapyHistory["History"][k]
                        
                    elif TherapyHistory["History"][k]["GroupId"] == GroupId and TherapyHistory["History"][k]["Date"] == DeviceTherapyModification["History"][j]["Date"]: 
                        if not "TherapyGroup" in DeviceTherapyModification["History"][j].keys():
                            DeviceTherapyModification["History"][j]["TherapyGroup"] = TherapyHistory["History"][k]

                        if DeviceTherapyModification["History"][j]["TherapyGroup"]["Type"] == TherapyHistory["History"][k]["Type"]:
                            ExistingSides = [DeviceTherapyModification["History"][j]["TherapyGroup"]["StimulationSettings"][t]["Electrode"]["Target"] for t in range(len(DeviceTherapyModification["History"][j]["TherapyGroup"]["StimulationSettings"]))]
                            if TherapyHistory["History"][k]["StimulationSettings"][0]["Electrode"]["Target"] not in ExistingSides:
                                DeviceTherapyModification["History"][j]["TherapyGroup"]["StimulationSettings"].extend(TherapyHistory["History"][k]["StimulationSettings"])
                                DeviceTherapyModification["History"][j]["TherapyGroup"]["AdaptiveSettings"].extend(TherapyHistory["History"][k]["AdaptiveSettings"])

        TherapyModifications.append(DeviceTherapyModification)

        i = 1
        lastVisit = 0
        GroupDurationCounter = {}
        while i < len(VisitTimestamps):
            TotalDuration = VisitTimestamps[i] - VisitTimestamps[lastVisit]
            if TotalDuration < 3600*24:
                for history in TherapyHistory["History"]:
                    if history["Date"] == VisitTimestamps[i] and history["Type"] in ["Pre-visit Therapy", "Past Therapy"]:
                        if history["GroupId"] in GroupDurationCounter.keys():
                            history["Percent"] = GroupDurationCounter[history["GroupId"]]
                        else:
                            history["Percent"] = 0
                            
                i += 1
                continue

            GroupDurationCounter = {}
            LastGroupTime = 0
            LastGroup = ""
            for j in range(len(DeviceTherapyModification["History"])):
                if DeviceTherapyModification["History"][j]["Type"] == "TherapyChangeGroup":
                    if DeviceTherapyModification["History"][j]["Date"] >= VisitTimestamps[lastVisit] and DeviceTherapyModification["History"][j]["Date"] <= VisitTimestamps[i]:
                        if not DeviceTherapyModification["History"][j]["Previous"] in GroupDurationCounter.keys():
                            GroupDurationCounter[DeviceTherapyModification["History"][j]["Previous"]] = 0
                        if LastGroupTime == 0:
                            GroupDurationCounter[DeviceTherapyModification["History"][j]["Previous"]] += DeviceTherapyModification["History"][j]["Date"] - VisitTimestamps[lastVisit]
                        else:
                            GroupDurationCounter[DeviceTherapyModification["History"][j]["Previous"]] += DeviceTherapyModification["History"][j]["Date"] - LastGroupTime
                        LastGroupTime = DeviceTherapyModification["History"][j]["Date"]
                        LastGroup = DeviceTherapyModification["History"][j]["New"]

            if not LastGroup in GroupDurationCounter.keys():
                GroupDurationCounter[LastGroup] = 0
            GroupDurationCounter[LastGroup] += VisitTimestamps[i] - LastGroupTime

            for key in GroupDurationCounter.keys():
                GroupDurationCounter[key] /= TotalDuration

            for history in TherapyHistory["History"]:
                if history["Date"] == VisitTimestamps[i] and history["Type"] in ["Pre-visit Therapy", "Past Therapy"]:
                    if history["GroupId"] in GroupDurationCounter.keys():
                        history["Percent"] = GroupDurationCounter[history["GroupId"]]
                    else:
                        history["Percent"] = 0

            lastVisit = i  
            i += 1
    
    return {"TherapyModification": TherapyModifications, "TherapyDevices": TherapyDevices, "TherapyConfiguration": TherapyHistories}

def findSameSourceTherapy(source_uid, hemisphere, group, TherapyHistories):
    for history in TherapyHistories:
        for j in range(len(history["StimulationSettings"])):
            if history["SourceId"] == source_uid and history["GroupId"].startswith(group) and history["StimulationSettings"][j]["Electrode"]["Target"].startswith(hemisphere) and history["Type"] == "Pre-visit Therapy":
                return {
                    "Type": "Pre-visit Therapy",
                    "TherapyId": history["Id"],
                    "Date": history["Date"],
                    "Stimulation": history["StimulationSettings"][j],
                    "Adaptive": history["AdaptiveSettings"][j]
                }
    
    return None

def findClosestTherapy(timestamp, hemisphere, group, TherapyHistories):
    TherapyHistories.sort(key=lambda x: x["Date"])
    ClosestTherapy = {"Pre": None, "Post": None}
    for i in range(len(TherapyHistories)):
        for j in range(len(TherapyHistories[i]["StimulationSettings"])):
            if TherapyHistories[i]["StimulationSettings"][j]["Electrode"]["Target"].startswith(hemisphere):
                if TherapyHistories[i]["GroupId"].startswith(group):
                    if TherapyHistories[i]["Date"] >= timestamp:
                        if TherapyHistories[i]["Type"] == "Pre-visit Therapy":
                            if not ClosestTherapy["Post"]:
                                ClosestTherapy["Post"] = {
                                    "Type": "Pre-visit Therapy",
                                    "TherapyId": TherapyHistories[i]["Id"],
                                    "Date": TherapyHistories[i]["Date"],
                                    "Stimulation": TherapyHistories[i]["StimulationSettings"][j],
                                    "Adaptive": TherapyHistories[i]["AdaptiveSettings"][j]
                                }
                            elif TherapyHistories[i]["Date"] - ClosestTherapy["Post"]["Date"] < 3600*24 and ClosestTherapy["Post"]["Type"] == "Past Therapy":
                                ClosestTherapy["Post"] = {
                                    "Type": "Pre-visit Therapy",
                                    "TherapyId": TherapyHistories[i]["Id"],
                                    "Date": TherapyHistories[i]["Date"],
                                    "Stimulation": TherapyHistories[i]["StimulationSettings"][j],
                                    "Adaptive": TherapyHistories[i]["AdaptiveSettings"][j]
                                }
                                
                        elif TherapyHistories[i]["Type"] == "Past Therapy" and not ClosestTherapy["Post"]:
                            ClosestTherapy["Post"] = {
                                "Type": "Past Therapy",
                                "TherapyId": TherapyHistories[i]["Id"],
                                "Date": TherapyHistories[i]["Date"],
                                "Stimulation": TherapyHistories[i]["StimulationSettings"][j],
                                "Adaptive": TherapyHistories[i]["AdaptiveSettings"][j]
                            }

                    if TherapyHistories[i]["Date"] < timestamp:
                        if TherapyHistories[i]["Type"] == "Post-visit Therapy":
                            ClosestTherapy["Pre"] = {
                                "Type": "Post-visit Therapy",
                                "TherapyId": TherapyHistories[i]["Id"],
                                "Date": TherapyHistories[i]["Date"],
                                "Stimulation": TherapyHistories[i]["StimulationSettings"][j],
                                "Adaptive": TherapyHistories[i]["AdaptiveSettings"][j]
                            }
                        elif TherapyHistories[i]["Type"] == "Past Therapy" and ClosestTherapy["Pre"]:
                            if TherapyHistories[i]["Date"] > ClosestTherapy["Pre"]["Date"] + 3600*12:
                                ClosestTherapy["Pre"] = None
                                
    return ClosestTherapy

def queryElectrodeImpedances(participant):
    SourceFiles = models.SourceFile.find_all(owner=participant)
    ImpedanceRecordss = models.DBSEvent.find_all(type__endswith="Impedance", source__in=SourceFiles)
    ElectrodeImpedances = []
    for impedance in ImpedanceRecordss:
        Descriptor = impedance.get_info(data=True)
        ElectrodeImpedances.append(Descriptor)
    return ElectrodeImpedances
    
def findClosestAdaptiveTherapy(timestamp, ClosestTherapy):
    # This is a new function based on SourceFile JSON ID
    if ClosestTherapy["Post"]:
        return ClosestTherapy["Post"]

    if not ClosestTherapy["Post"] and not ClosestTherapy["Pre"]:
        return None
    elif not ClosestTherapy["Post"]:
        return ClosestTherapy["Pre"] if ClosestTherapy["Pre"]["Adaptive"] else None
    elif not ClosestTherapy["Pre"]:
        return ClosestTherapy["Post"] if ClosestTherapy["Post"]["Adaptive"] else None
    else:
        if ClosestTherapy["Post"]["Date"] - timestamp < timestamp - ClosestTherapy["Pre"]["Date"]:
            if "SensingSetup" in ClosestTherapy["Post"]["Adaptive"]["RecordingConfiguration"]["Config"]:
                return ClosestTherapy["Post"]
            elif "SensingSetup" in ClosestTherapy["Pre"]["Adaptive"]["RecordingConfiguration"]["Config"]:
                return ClosestTherapy["Pre"]
            
        else:
            if "SensingSetup" in ClosestTherapy["Pre"]["Adaptive"]["RecordingConfiguration"]["Config"]:
                return ClosestTherapy["Pre"]
            elif "SensingSetup" in ClosestTherapy["Post"]["Adaptive"]["RecordingConfiguration"]["Config"]:
                return ClosestTherapy["Post"]
    return None

def checkDuplicate(device, therapy):
    AllTherapies = models.Therapy.find_all(source__metadata__Device=device.uid, type=therapy["type"], date=therapy["date"])
    if len(AllTherapies) == 0:
        return False
    
    AllElectricalTherapy = models.ElectricalTherapy.find_all(group_type=therapy["group_type"], group_id=therapy["group_id"], stimulation_type=therapy["stimulation_type"], therapy__in=AllTherapies)
    if len(AllElectricalTherapy) == 0:
        return False

    electrode = device.electrodes.filter(target__startswith=therapy["hemisphere"]).first()
    for electrical_therapy in AllElectricalTherapy:
        AllTrue = True
        for i in range(len(therapy["stimulation_settings"])):
            setting = therapy["stimulation_settings"][i]
            if not electrical_therapy.stimulation_settings.filter(electrode=electrode, **{key: setting[key] for key in setting.keys() if key in ["contact", "return_contact", "amplitude", "amplitude_fraction", "amplitude_unit", "pulsewidth", "pulsewidth_unit", "frequency", "cycling", "cycling_period"]}).exists():
                AllTrue = False
        
        if AllTrue:
            return True
        
    return False
                