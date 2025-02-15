""""""
"""
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
"""
Medtronic Percept BrainSense Survey Module
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
from datetime import datetime
import copy
import numpy as np
import pandas as pd

key = os.environ.get('DATASERVER_ENCRYPTION')

def saveBrainSenseSurvey(streamList):
    """ Save BrainSense Survey Data in Database Storage

    Args:
      deviceID: UUID4 deidentified id for each unique Percept device.
      surveyList: Array of BrainSense Survey structures extracted from Medtronic JSON file.
      sourceFile: filename of the raw JSON file that the original data extracted from.

    Returns:
      Boolean indicating if new data is found (to be saved).
    """

    NewRecordings = []
    StreamDates = list()
    for stream in streamList:
        StreamDates.append(stream["FirstPacketDateTime"])
    UniqueSessionDates = np.unique(StreamDates)

    for date in UniqueSessionDates:
        Recording = dict()
        Recording["SamplingRate"] = streamList[0]["SamplingRate"]
        StreamGroupIndexes = [stream["FirstPacketDateTime"] == date for stream in streamList]
        Recording["ChannelNames"] = [streamList[i]["Channel"] for i in range(len(streamList)) if StreamGroupIndexes[i]]
        Recording["StartTime"] = date
        Recording["Descriptor"] = {"MedtronicPSD": []}
        
        RecordingSize = [len(streamList[i]["Data"]) for i in range(len(streamList)) if StreamGroupIndexes[i]]
        if len(np.unique(RecordingSize)) > 1:
            print("Inconsistent Recording Size for Survey Stream")
            maxSize = np.max(RecordingSize)
            Recording["Data"] = np.zeros((maxSize, len(RecordingSize)))
            Recording["Missing"] = np.ones((maxSize, len(RecordingSize)))
            n = 0
            for i in range(len(streamList)): 
                if StreamGroupIndexes[i]:
                    Recording["Data"][:RecordingSize[n], n] = streamList[i]["Data"]
                    Recording["Missing"][:RecordingSize[n], n] = streamList[i]["Missing"]
                    n += 1
        else:
            Recording["Data"] = np.zeros((RecordingSize[0], len(RecordingSize)))
            Recording["Missing"] = np.ones((RecordingSize[0], len(RecordingSize)))
            n = 0
            for i in range(len(streamList)): 
                if StreamGroupIndexes[i]:
                    Recording["Data"][:, n] = streamList[i]["Data"]
                    Recording["Missing"][:, n] = streamList[i]["Missing"]
                    n += 1
        
        for i in range(len(streamList)): 
            if "PSD" in streamList[i].keys():
                Recording["Descriptor"]["MedtronicPSD"].append(streamList[i]["PSD"])
            else:
                Recording["Descriptor"]["MedtronicPSD"].append(None)

        Recording["Duration"] = Recording["Data"].shape[0] / Recording["SamplingRate"]
        NewRecordings.append(Recording)
        
    return NewRecordings
