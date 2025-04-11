#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 12 14:00:53 2021

@author: Jackson Cagle
"""

import numpy as np
from scipy import io as sio
import pandas as pd
import json
from io import BytesIO

def getStr(item):
    if type(item) == np.ndarray:
        return getStr(item[0])
    return str(item)

def decodeMATLABFile(matFile):
    Data = sio.loadmat(BytesIO(matFile))

    if "DataType" in Data.keys():
        if Data["DataType"] == "CustomizedTimelineData":
            TimelineEntries = []
            Channel = {"ChannelNames": []}

            Channel["SamplingRate"] = -1 # Variable Frequency
            Channel["Time"] = []
            Channel["Data"] = []
            for i in range(len(Data["Channels"])):
                Channel["ChannelNames"].append(getStr(Data["Channels"][i]))

            Channel["Data"] = np.array(Data["Data"])
            Channel["Time"] = np.array(Data["Time"]).flatten()
            Channel["Duration"] = np.array(Data["Duration"]).flatten()
            Channel["StartTime"] = Channel["Time"][0]
            TimelineEntries.append(Channel)
            return "CustomizedTimelineData", TimelineEntries
            
        elif Data["DataType"] == "CustomizedStreamingData":
            Channel = {"ChannelNames": []}
            Channel["Descriptor"] = json.loads(getStr(Data["Metadata"]))
            Channel["SamplingRate"] = Data["Fs"][0] # Expect only 1 sampling rate due to how Data matrix format.
            for i in range(len(Data["Channels"])):
                Channel["ChannelNames"].append(getStr(Data["Channels"][i]))

            Channel["Data"] = np.array(Data["Data"]).T
            Channel["Time"] = np.arange(Data["Data"].shape[1]) / Channel["SamplingRate"]
            Channel["StartTime"] = Channel["Descriptor"]["StartTime"]
            Channel["Missing"] = np.zeros(Channel["Data"].shape)
            Channel["Duration"] = Channel["Time"][-1]
            return "CustomizedStreamingData", [Channel]
    
    else:
        SamplingRates = np.unique(Data["Fs"])
        MinimumRecordingDuration = np.min(Data["Data"].shape[1]/Data["Fs"])
        
        SensorMATs = []
        for fs in SamplingRates:
            Channel = {"ChannelNames": []}
            Channel["Time"] = np.arange(fs * MinimumRecordingDuration) / fs
            Channel["Data"] = []
            for i in range(len(Data["Channels"])):
                if Data["Fs"][i] == fs and not np.all(Data["Data"][i,:] == 0):
                    Channel["Data"].append(np.interp(Channel["Time"] + Data["Time"][i,0], Data["Time"][i,:], Data["Data"][i,:]))
                    Channel["ChannelNames"].append(getStr(Data["Channels"][i]))

            Channel["Data"] = np.array(Channel["Data"]).T
            Channel["SamplingRate"] = fs
            Channel["StartTime"] = Data["Time"][0,0]
            Channel["Missing"] = np.zeros(Channel["Data"].shape)
            Channel["Duration"] = MinimumRecordingDuration
            SensorMATs.append(Channel)
        
        return "ExternalSensorStreaming", SensorMATs
