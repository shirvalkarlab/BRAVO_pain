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
    for stream in streamList:
        Recording = dict()
        Recording["SamplingRate"] = stream["SamplingRate"]
        Recording["ChannelNames"] = [stream["Channel"]]
        Recording["Data"] = stream["Data"]
        Recording["Missing"] = stream["Missing"]
        Recording["StartTime"] = stream["FirstPacketDateTime"]
        Recording["Descriptor"] = {}
        if "PSD" in stream.keys():
            Recording["Descriptor"]["MedtronicPSD"] = stream["PSD"]
        Recording["Duration"] = Recording["Data"].shape[0] / Recording["SamplingRate"]
        NewRecordings.append(Recording)

    return NewRecordings
