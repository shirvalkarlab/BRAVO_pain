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
        
        # this montage's own streams only (decision 442): every stream of the export used to be
        # appended, giving each montage the other montages' spectra under its own start time
        for i in range(len(streamList)): 
            if not StreamGroupIndexes[i]:
                continue
            if "PSD" in streamList[i].keys():
                Recording["Descriptor"]["MedtronicPSD"].append(streamList[i]["PSD"])
            else:
                Recording["Descriptor"]["MedtronicPSD"].append(None)

        # electrode-survey spectra that differ from the montage's, kept beside it (decision 443)
        _survey = [streamList[i].get("SurveyPSD") for i in range(len(streamList)) if StreamGroupIndexes[i]]
        if any(x is not None for x in _survey):
            Recording["Descriptor"]["SurveyPSD"] = _survey
        Recording["Duration"] = Recording["Data"].shape[0] / Recording["SamplingRate"]
        NewRecordings.append(Recording)
        
    return NewRecordings


def spectrumKey(psd):
    """The identity of one device spectrum (decision 445): contact pair, side, frequencies and
    magnitudes exactly as the device wrote them, under either export spelling (`LFPMagnitude` in
    the montage, `LFPMagnitudeinMicroVoltPeak` in the survey). Nothing else, so the same spectrum
    repeated in another export, or written again in the survey section, has the same key."""
    import hashlib
    import json
    def first(*keys):
        for k in keys:
            if psd.get(k) is not None:
                return [float(v) for v in psd[k]]
        return None
    ident = [str(psd.get("SensingElectrodes", "")).split(".")[-1], str(psd.get("Hemisphere", "")).split(".")[-1],
             first("LFPFrequency", "LFPFrequencyinHertz"), first("LFPMagnitude", "LFPMagnitudeinMicroVoltPeak")]
    return hashlib.sha256(json.dumps(ident).encode("utf8")).hexdigest()


def streamRelation(stored, new):
    """How a new time-domain stream relates to a stored one with the same start and contacts,
    on the values alone (decision 445): "duplicate" (identical, or the start of the stored one),
    "longer" (the stored one is its start: it replaces it), "new" (any value differs)."""
    a = np.asarray(stored, dtype=float)
    b = np.asarray(new, dtype=float)
    if a.ndim != b.ndim or a.shape[1:] != b.shape[1:]:
        return "new"
    n = min(a.shape[0], b.shape[0])
    if not np.array_equal(a[:n], b[:n], equal_nan=True):
        return "new"
    return "longer" if b.shape[0] > a.shape[0] else "duplicate"
