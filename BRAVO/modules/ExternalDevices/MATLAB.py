#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 12 14:00:53 2021

@author: Jackson Cagle
"""

import numpy as np
from scipy import io as sio
import pandas as pd
from io import BytesIO

def decodeMATLABFile(matFile):
    Data = sio.loadmat(BytesIO(matFile))
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
                Channel["ChannelNames"].append(Data["Channels"][i])
        Channel["Data"] = np.array(Channel["Data"]).T
        Channel["SamplingRate"] = fs
        Channel["StartTime"] = Data["Time"][0,0]
        Channel["Missing"] = np.zeros(Channel["Data"].shape)
        Channel["Duration"] = MinimumRecordingDuration
        SensorMATs.append(Channel)
    
    return SensorMATs
