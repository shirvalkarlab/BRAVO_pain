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
NeuroPace Persyst Data Processor
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os 
import json 
import numpy as np

from modules import Database
from modules.HelperFunctions import current_time, get_or_none

key = os.environ.get('DATASERVER_ENCRYPTION')

def getScaling(deviceType, gain):
    if deviceType == "RNS-320":
        if gain == "Low":
            return 6.54
        if gain == "Med-Low":
            return 3.27
        if gain == "Med-High":
            return 1.63
        if gain == "High":
            return 0.82 
        return 1
    
    elif deviceType == "RNS-300M":
        if gain == "Low":
            return 3.8
        if gain == "Med-Low":
            return 2.0
        if gain == "Med-High":
            return 1.2
        if gain == "High":
            return 0.8 
        return 1
    
    else:
        return 1

def parsePersystRecording(dat, lay):
    allChannels = []
    samplingRates = []
    gains = []
    data = []
    for i in range(1,5):
        EnableKey = f"AmplifierChannel{i}"
        if lay["Configurations"][EnableKey+"ECoGStorageEnabled"] == "On":
            for key in lay["ChannelNames"]:
                if lay["ChannelNames"][key] == str(i):
                    allChannels.append(key)

            samplingRates.append(float(lay["Configurations"][EnableKey+"SampleRate"].replace("Hz","")))
            gains.append(lay["Configurations"][EnableKey+"Gain"])

    DataArray = np.frombuffer(dat, dtype=np.int16)
    RecordingDuration = len(DataArray) / np.sum(samplingRates)
    currentIndex = 0
    for i in range(len(allChannels)):
        data.append(DataArray[currentIndex:currentIndex+int(RecordingDuration*samplingRates[i])])
        currentIndex += int(RecordingDuration*samplingRates[i])

    UniqueSamplingRates = np.unique(samplingRates)

    DeviceType = lay["PatientInformation"]["DeviceType"] if "DeviceType" in lay["PatientInformation"].keys() else ""
    PersystData = []
    for fs in UniqueSamplingRates:
        Channel = {"ChannelNames": []}
        Channel["Time"] = np.arange(fs * RecordingDuration) / fs
        Channel["Data"] = []
        for i in range(len(allChannels)):
            if samplingRates[i] == fs:
                data[i] = (data[i] - 512) * getScaling(DeviceType, gains[i])
                Channel["Data"].append(data[i])
                Channel["ChannelNames"].append(allChannels[i])

        Channel["Data"] = np.array(Channel["Data"]).T
        Channel["SamplingRate"] = fs
        Channel["StartTime"] = lay["PatientInformation"]["SessionDate"]
        Channel["Missing"] = np.zeros(Channel["Data"].shape)
        Channel["Duration"] = RecordingDuration
        PersystData.append(Channel)
    
    return [{
        "name": "",
        "type": "NeuroPacePersystStreams",
        "date": Recording["StartTime"],
        "recording": Recording,
        "metadata": {
            "ChannelNames": Recording["ChannelNames"],
            "Duration": Recording["Duration"],
        }
    } for Recording in PersystData]


def decodeMedtronicJSON(JSON):
    Data = get_or_none(Percept.extractPerceptJSON)(JSON)
    if not Data:
        raise Exception("Medtronic Percept Content Extraction Error")
    
    # TODO: Handle Process Failure

    # Extract Device/Patient Info
    SessionOverview = extractPatientInformation(JSON)
