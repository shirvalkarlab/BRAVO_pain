#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 12 14:00:53 2021

@author: Jackson Cagle
"""

import numpy as np
import pandas as pd
from io import BytesIO

def decodeDelsysFormat(rawData):
    PackageOnset = np.where([rawData[i:i+3] == b"BML" for i in range(len(rawData)-2)])[0]
    PackageType = [[rawData[i+4:i+8]][0] for i in PackageOnset]
    
    TriggerSequence = np.where([PackageType[i] == b'Trg ' for i in range(len(PackageType))])[0]
    if len(TriggerSequence) > 0:
        Triggers = dict()
        Triggers["Time"] = np.zeros((len(TriggerSequence)))
        Triggers["String"] = list()
        Triggers["Unique"] = list()
        Triggers["ByteOnset"] = np.zeros((len(TriggerSequence)),dtype=int)
        Triggers["DataOnset"] = np.zeros((len(TriggerSequence)),dtype=int)
        
        for i in range(len(TriggerSequence)):
            onsetByte = int(PackageOnset[TriggerSequence[i]])
            Triggers["Time"][i] = int.from_bytes(rawData[onsetByte + 20 : onsetByte + 28], "little")
            Triggers["String"].append(rawData[onsetByte + 8 : onsetByte + 20].decode("utf-8").replace("\x00",""))
            if Triggers["String"][-1] not in Triggers["Unique"]:
                Triggers["Unique"].append(Triggers["String"][-1])
            Triggers["ByteOnset"][i] = onsetByte
            Triggers["DataOnset"][i] = onsetByte + 32
        
        Delsys = dict()
        Delsys["Triggers"] = Triggers
        Delsys["EMG"] = [np.zeros((0,1))] * 16
        Delsys["Acc"] = [np.zeros((0,3))] * 16
        Delsys["Gyro"] = [np.zeros((0,3))] * 16
        Delsys["Mag"] = [np.zeros((0,3))] * 16
        
        for i in range(len(Triggers["String"])):
            for sensorID in range(16):
                if Triggers["String"][i].find(f"imuEMG{sensorID}") >= 0:
                    if i == len(Triggers["String"])-1:
                        payload = rawData[Triggers["DataOnset"][i]:]
                    else:
                        payload = rawData[Triggers["DataOnset"][i]:Triggers["ByteOnset"][i+1]]
                    Delsys["EMG"][sensorID] = np.concatenate((Delsys["EMG"][sensorID], np.frombuffer(payload, dtype="<f4", count=int(len(payload)/4), offset=0).reshape((int(len(payload)/4),1))), axis=0)
                
                elif Triggers["String"][i].find(f"imuAUX{sensorID}") >= 0:
                    if i == len(Triggers["String"])-1:
                        payload = rawData[Triggers["DataOnset"][i]:]
                    else:
                        payload = rawData[Triggers["DataOnset"][i]:Triggers["ByteOnset"][i+1]]
                    reconstructedData = np.frombuffer(payload, dtype="<f4", count=int(len(payload)/4), offset=0)
                    dataLength = int(len(reconstructedData) / 3)
                    
                    Delsys["Acc"][sensorID] = np.concatenate((Delsys["Acc"][sensorID], reconstructedData[dataLength*0:dataLength*1].reshape(3, int(dataLength/3)).T), axis=0)
                    Delsys["Gyro"][sensorID] = np.concatenate((Delsys["Gyro"][sensorID], reconstructedData[dataLength*1:dataLength*2].reshape(3, int(dataLength/3)).T), axis=0)
                    Delsys["Mag"][sensorID] = np.concatenate((Delsys["Mag"][sensorID], reconstructedData[dataLength*2:dataLength*3].reshape(3, int(dataLength/3)).T), axis=0)
        
        Delsys["EMGTime"] = np.array(range(np.max([Delsys["EMG"][i].shape[0] for i in range(16)]))) / 1111.111
        Delsys["IMUTime"] = np.array(range(np.max([Delsys["Acc"][i].shape[0] for i in range(16)]))) / 148.148
        
        for sensorID in range(16):
            for t in range(1,Delsys["Acc"][sensorID].shape[0]):
                if Delsys["Acc"][sensorID][t,0] == 0:
                    Delsys["Acc"][sensorID][t,0] = Delsys["Acc"][sensorID][t-1,0]
                if Delsys["Acc"][sensorID][t,1] == 0:
                    Delsys["Acc"][sensorID][t,1] = Delsys["Acc"][sensorID][t-1,1]
                if Delsys["Acc"][sensorID][t,2] == 0:
                    Delsys["Acc"][sensorID][t,2] = Delsys["Acc"][sensorID][t-1,2]
                    
            for t in range(1,Delsys["Gyro"][sensorID].shape[0]):
                if Delsys["Gyro"][sensorID][t,0] == 0:
                    Delsys["Gyro"][sensorID][t,0] = Delsys["Gyro"][sensorID][t-1,0]
                if Delsys["Gyro"][sensorID][t,1] == 0:
                    Delsys["Gyro"][sensorID][t,1] = Delsys["Gyro"][sensorID][t-1,1]
                if Delsys["Gyro"][sensorID][t,2] == 0:
                    Delsys["Gyro"][sensorID][t,2] = Delsys["Gyro"][sensorID][t-1,2]
                    
            for t in range(1,Delsys["Mag"][sensorID].shape[0]):
                if Delsys["Mag"][sensorID][t,0] == 0:
                    Delsys["Mag"][sensorID][t,0] = Delsys["Mag"][sensorID][t-1,0]
                if Delsys["Mag"][sensorID][t,1] == 0:
                    Delsys["Mag"][sensorID][t,1] = Delsys["Mag"][sensorID][t-1,1]
                if Delsys["Mag"][sensorID][t,2] == 0:
                    Delsys["Mag"][sensorID][t,2] = Delsys["Mag"][sensorID][t-1,2]
        return Delsys
    return []

def decodeMDATData(mdatFile):
    Trigno = decodeDelsysFormat(mdatFile)
    TrignoSensorList = []
    
    Data = {"ChannelNames": []}
    for i in range(len(Trigno["EMG"])):
        if len(Trigno["EMG"][i]) > 0:
            Data["ChannelNames"].append("EMG." + str(i+1))
    
    Data["Data"] = np.zeros((len(Trigno["EMGTime"]), len(Data["ChannelNames"])))
    Counter = 0
    for i in range(len(Trigno["EMG"])):
        if len(Trigno["EMG"][i]) > 0:
            Data["Data"][:len(Trigno["EMG"][i]),Counter] = Trigno["EMG"][i].flatten()
            Counter += 1
    Data["SamplingRate"] = np.around(1/np.median(np.diff(Trigno["EMGTime"])),3)
    Data["StartTime"] = Trigno['Triggers']["Time"][0]
    Data["Missing"] = np.zeros(Data["Data"].shape)
    Data["Duration"] = Data["Data"].shape[0]/Data["SamplingRate"]
    TrignoSensorList.append(Data)

    for sensorKey in ["Acc", "Gyro", "Mag"]:
        Data = {"ChannelNames": []}
        for i in range(len(Trigno[sensorKey])):
            if len(Trigno[sensorKey][i]) > 0:
                Data["ChannelNames"].append(sensorKey + "." + str(i+1) + ".X")
                Data["ChannelNames"].append(sensorKey + "." + str(i+1) + ".Y")
                Data["ChannelNames"].append(sensorKey + "." + str(i+1) + ".Z")
    
        Data["Data"] = np.zeros((len(Trigno["IMUTime"]), len(Data["ChannelNames"])))
        Counter = 0
        for i in range(len(Trigno[sensorKey])):
            if Trigno[sensorKey][i].shape[0] > 0:
                for j in range(3):
                    Data["Data"][:Trigno[sensorKey][i].shape[0],Counter] = Trigno[sensorKey][i][:,j].flatten()
                    Counter += 1
        Data["SamplingRate"] = np.around(1/np.median(np.diff(Trigno["IMUTime"])),3)
        Data["StartTime"] = Trigno['Triggers']["Time"][0]
        Data["Missing"] = np.zeros(Data["Data"].shape)
        Data["Duration"] = Data["Data"].shape[0]/Data["SamplingRate"]
        TrignoSensorList.append(Data)

    return TrignoSensorList

def decodeHPFCSVData(mdatFile):
    CSV = pd.read_csv(BytesIO(mdatFile), skiprows=0)
    keys = list(CSV.keys())

    HPFCSV = list()

    i = 0
    while i < len(keys):
        if keys[i].startswith("X[s]"):
            SensorData = {
                "Name": keys[i+1],
                "Time": np.array(CSV[keys[i]])
            }
            SensorData["Time"] = SensorData["Time"][~np.isnan(SensorData["Time"])]
            SensorData["Data"] = np.array(CSV[keys[i+1]])[:len(SensorData["Time"])]
            HPFCSV.append(SensorData)
            i += 2
        else:
            i += 1
    
    MinimumRecordingDuration = np.min([i["Time"][-1]-i["Time"][0] for i in HPFCSV if not np.all(i["Data"] == 0)])
    SamplingRates = np.unique([np.around(1/np.median(np.diff(i["Time"])),0) for i in HPFCSV if not np.all(i["Data"] == 0)])

    TrignoSensorList = []
    for fs in SamplingRates:
        Data = {"ChannelNames": []}
        Data["Time"] = np.arange(fs * MinimumRecordingDuration) / fs
        Data["Data"] = []
        for i in range(len(HPFCSV)):
            SamplingRate = np.around(1/np.median(np.diff(HPFCSV[i]["Time"])),0)
            if SamplingRate == fs and not np.all(HPFCSV[i]["Data"] == 0):
                Data["Data"].append(np.interp(Data["Time"] + HPFCSV[i]["Time"][0], HPFCSV[i]["Time"], HPFCSV[i]["Data"]))
                Data["ChannelNames"].append(HPFCSV[i]["Name"])
        Data["Data"] = np.array(Data["Data"]).T
        Data["SamplingRate"] = fs
        Data["StartTime"] = HPFCSV[i]["Time"][0]
        Data["Missing"] = np.zeros(Data["Data"].shape)
        Data["Duration"] = MinimumRecordingDuration
        TrignoSensorList.append(Data)
    
    return TrignoSensorList
