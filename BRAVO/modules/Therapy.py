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

import timeit

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
    for device in DBSDevices:
        DeviceInfo = device.get_info()
        TherapyDevices.append(DeviceInfo)

        SourceFiles = models.SourceFile.find_all(owner=Participant, metadata__Device=device.uid)
        TherapyHistory = {
            "Device": DeviceInfo,
            "History": [i.get_info() for i in models.ElectricalTherapy.find_all(therapy__source__in=SourceFiles)]
        }

        TherapyHistory["History"] = [i for i in TherapyHistory["History"] if (i["Type"] in ["Pre-visit Therapy", "Post-visit Therapy", "Past Therapy"])]
        TherapyHistory["History"].sort(key=lambda x: x["Date"])
        TherapyHistories.append(TherapyHistory)
    
        DeviceTherapyModification = {
            "Device": DeviceInfo,
            "History": [i.get_info() for i in models.TherapyModification.find_all(source__in=SourceFiles)]
        }
        DeviceTherapyModification["History"].sort(key=lambda x: x["Date"])
        
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

        TherapyModifications.append(DeviceTherapyModification)

    return {"TherapyModification": TherapyModifications, "TherapyDevices": TherapyDevices, "TherapyConfiguration": TherapyHistories}

def findClosestTherapy(timestamp, hemisphere, group, TherapyHistories):
    ClosestTherapy = {"Pre": None, "Post": None}
    for i in range(len(TherapyHistories)):
        for j in range(len(TherapyHistories[i]["StimulationSettings"])):
            if TherapyHistories[i]["StimulationSettings"][j]["Electrode"]["Target"].startswith(hemisphere):
                if TherapyHistories[i]["GroupId"].startswith(group):
                    if TherapyHistories[i]["Date"] >= timestamp:
                        if TherapyHistories[i]["Type"] == "Past Therapy" and not ClosestTherapy["Post"]:
                                ClosestTherapy["Post"] = {
                                    "TherapyId": TherapyHistories[i]["Id"],
                                    "Date": TherapyHistories[i]["Date"],
                                    "Stimulation": TherapyHistories[i]["StimulationSettings"][j],
                                    "Adaptive": TherapyHistories[i]["AdaptiveSettings"][j]
                                }

                        elif TherapyHistories[i]["Type"] == "Pre-visit Therapy":
                            if not ClosestTherapy["Post"]:
                                ClosestTherapy["Post"] = {
                                    "TherapyId": TherapyHistories[i]["Id"],
                                    "Date": TherapyHistories[i]["Date"],
                                    "Stimulation": TherapyHistories[i]["StimulationSettings"][j],
                                    "Adaptive": TherapyHistories[i]["AdaptiveSettings"][j]
                                }
                            elif TherapyHistories[i]["Date"] - ClosestTherapy["Post"]["Date"] < 3600*12:
                                ClosestTherapy["Post"] = {
                                    "TherapyId": TherapyHistories[i]["Id"],
                                    "Date": TherapyHistories[i]["Date"],
                                    "Stimulation": TherapyHistories[i]["StimulationSettings"][j],
                                    "Adaptive": TherapyHistories[i]["AdaptiveSettings"][j]
                                }

                    if TherapyHistories[i]["Date"] < timestamp:
                        if TherapyHistories[i]["Type"] == "Post-visit Therapy":
                            ClosestTherapy["Pre"] = {
                                "TherapyId": TherapyHistories[i]["Id"],
                                "Date": TherapyHistories[i]["Date"],
                                "Stimulation": TherapyHistories[i]["StimulationSettings"][j],
                                "Adaptive": TherapyHistories[i]["AdaptiveSettings"][j]
                            }
                        elif TherapyHistories[i]["Type"] == "Past Therapy" and ClosestTherapy["Pre"]:
                            if TherapyHistories[i]["Date"] > ClosestTherapy["Pre"]["Date"] + 3600*12:
                                ClosestTherapy["Pre"] = None
                                
    return ClosestTherapy

def findClosestAdaptiveTherapy(timestamp, ClosestTherapy):
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
                