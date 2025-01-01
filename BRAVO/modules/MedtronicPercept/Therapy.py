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
Therapy History Module
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
from datetime import datetime
import copy
import numpy as np
import pandas as pd

from modules.MedtronicPercept import Percept

key = os.environ.get('DATASERVER_ENCRYPTION')

def saveTherapyEvents(therapyList):
    """ Save Therapy Change History in Database

    Args:
      participant: Participant node object. Therapy is direct child node of Participant
      device: Device Object that the therapy is delivered from.
      therapyList: Array of Therapy Configuration structures extracted from Medtronic JSON file.

    Returns:
      Array of Newly Created Therapy History
    """

    NewTherapies = list()
    for therapy in therapyList:
        if "TherapyStatus" in therapy.keys():
            event = { "name": "", "type": "TherapyStatus", "date": therapy["DateTime"].timestamp(), "previous_state": "OFF" if therapy["TherapyStatus"] else "ON", "new_state": "ON" if therapy["TherapyStatus"] else "OFF", }
        else:
            event = { "name": "", "type": "TherapyChangeGroup", "date": therapy["DateTime"].timestamp(), "previous_state": therapy["OldGroupId"], "new_state": therapy["NewGroupId"], }
        NewTherapies.append(event)
    return NewTherapies

def extractTherapySettings(therapyList):
    """ Save Therapy Settings in Database

    Args:
      participant: Participant node object. Therapy is direct child node of Participant
      device: Device Object that the therapy is delivered from.
      therapyList: Array of Therapy Configuration structures extracted from Medtronic JSON file.
      sessionDate: DateTime object indicating when the therapy configuration is saved.
      type: One of three data types: ["Past Therapy","Pre-visit Therapy","Post-visit Therapy"].

    Returns:
      Array of Newly Created Therapy Settings
    """

    NewTherapies = []
    for therapy in therapyList:
        for hemisphere in ["LeftHemisphere", "RightHemisphere"]:
            if hemisphere in therapy.keys():
                therapyObject = {
                    "hemisphere": "Left" if hemisphere == "LeftHemisphere" else "Right",
                    "group_type": "",
                    "group_name": therapy["GroupName"],
                    "group_id": therapy["GroupId"],
                    "stimulation_type": therapy[hemisphere]["Mode"],
                    "stimulation_settings": [],
                    "adaptive_settings": [],
                    "sensing_settings": []
                }

                if therapyObject["stimulation_type"] == "Interleaving":
                    for i in range(len(therapy[hemisphere]["Frequency"])):
                        stimulationSetting = {
                            "amplitude": therapy[hemisphere]["Amplitude"][i],
                            "amplitude_unit": therapy[hemisphere]["Unit"][i],
                            "pulsewidth": therapy[hemisphere]["PulseWidth"][i],
                            "pulsewidth_unit": "uS",
                            "frequency": therapy[hemisphere]["Frequency"][i]
                        }
                        
                        contact = []
                        amplitude = []
                        return_contact = []
                        for channel in therapy[hemisphere]["Channel"][i]:
                            ChannelName, ChannelIndex = Percept.reformatElectrodeDef(channel["Electrode"])
                            if channel["ElectrodeStateResult"] == "ElectrodeStateDef.Positive":
                                return_contact.append(ChannelIndex)
                            elif channel["ElectrodeStateResult"] == "ElectrodeStateDef.Negative":
                                contact.append(ChannelIndex)
                                if "ElectrodeAmplitudeInMilliAmps" in channel.keys():
                                    amplitude.append(channel["ElectrodeAmplitudeInMilliAmps"])
                                else:
                                    amplitude.append(therapy[hemisphere]["Amplitude"][i])
                        
                        stimulationSetting["amplitude_fraction"] = amplitude
                        stimulationSetting["contact"] = contact
                        stimulationSetting["return_contact"] = return_contact
                        
                        try:
                            if "Cycling" in therapy["GroupSettings"].keys():
                                if therapy["GroupSettings"]["Cycling"]["Enabled"]:
                                    stimulationSetting["cycling_period"] = therapy["GroupSettings"]["Cycling"]["OnDurationInMilliSeconds"] + therapy["GroupSettings"]["Cycling"]["OffDurationInMilliSeconds"]
                                    stimulationSetting["cycling"] = therapy["GroupSettings"]["Cycling"]["OnDurationInMilliSeconds"] / stimulationSetting["cycling_period"]
                                else:
                                    stimulationSetting["cycling"] = 1
                        except Exception as e:
                            print(e)
                            pass

                        therapyObject["stimulation_settings"].append(stimulationSetting)
                        therapyObject["sensing_settings"].append(None)
                        therapyObject["adaptive_settings"].append(None)

                else:
                    stimulationSetting = {
                        "amplitude": therapy[hemisphere]["Amplitude"],
                        "amplitude_unit": therapy[hemisphere]["Unit"],
                        "pulsewidth": therapy[hemisphere]["PulseWidth"],
                        "pulsewidth_unit": "uS",
                        "frequency": therapy[hemisphere]["Frequency"]
                    }
                    
                    contact = []
                    return_contact = []
                    amplitude = []
                    for channel in therapy[hemisphere]["Channel"]:
                        ChannelName, ChannelIndex = Percept.reformatElectrodeDef(channel["Electrode"])
                        if channel["ElectrodeStateResult"] == "ElectrodeStateDef.Positive":
                            return_contact.append(ChannelIndex)
                        elif channel["ElectrodeStateResult"] == "ElectrodeStateDef.Negative":
                            contact.append(ChannelIndex)
                            if "ElectrodeAmplitudeInMilliAmps" in channel.keys():
                                amplitude.append(channel["ElectrodeAmplitudeInMilliAmps"])
                            else:
                                amplitude.append(therapy[hemisphere]["Amplitude"])
                            
                    stimulationSetting["amplitude_fraction"] = amplitude
                    stimulationSetting["contact"] = contact
                    stimulationSetting["return_contact"] = return_contact
                    
                    try:
                        if therapy["GroupSettings"]["Cycling"]["Enabled"]:
                            stimulationSetting["cycling_period"] = therapy["GroupSettings"]["Cycling"]["OnDurationInMilliSeconds"] + therapy["GroupSettings"]["Cycling"]["OffDurationInMilliSeconds"]
                            stimulationSetting["cycling"] = therapy["GroupSettings"]["Cycling"]["OnDurationInMilliSeconds"] / stimulationSetting["cycling_period"]
                        else:
                            stimulationSetting["cycling"] = 1
                    except:
                        pass

                    therapyObject["stimulation_settings"].append(stimulationSetting)

                    if "SensingSetup" in therapy[hemisphere].keys():
                        therapyObject["sensing_settings"].append({
                            "type": "Medtronic BrainSense",
                            "sensing": {
                                "Thresholds": {
                                    "LFPThresholds": therapy[hemisphere]["LFPThresholds"] if "LFPThresholds" in therapy[hemisphere].keys() else [0,0],
                                    "MeasuredLFP": therapy[hemisphere]["MeasuredLFP"] if "MeasuredLFP" in therapy[hemisphere].keys() else [0,0],
                                    "CaptureAmplitudes": therapy[hemisphere]["CaptureAmplitudes"] if "CaptureAmplitudes" in therapy[hemisphere].keys() else [0,0],
                                    "AmplitudeThreshold": therapy[hemisphere]["AmplitudeThreshold"] if "AmplitudeThreshold" in therapy[hemisphere].keys() else [0,0],
                                },
                                "SensingSetup": therapy[hemisphere]["SensingSetup"]
                            }
                        })
                    else:
                        therapyObject["sensing_settings"].append(None)

                    if "AdaptiveSetup" in therapy[hemisphere].keys():
                        therapyObject["adaptive_settings"].append({
                            "type": "Medtronic Adaptive",
                            "adaptive": therapy[hemisphere]["AdaptiveSetup"]
                        })
                    else:
                        therapyObject["adaptive_settings"].append(None)

                NewTherapies.append(therapyObject)

    return NewTherapies

