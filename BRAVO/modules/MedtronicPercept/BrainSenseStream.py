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
Medtronic Percept BrainSense Streaming Module
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
from datetime import datetime
import copy
import numpy as np
import pandas as pd

from modules.HelperFunctions import uuid4_hex
from modules.MedtronicPercept import Percept

key = os.environ.get('DATASERVER_ENCRYPTION')

def saveBrainSenseStreams(StreamingTD, StreamingPower, FixBreaking=True):
    """ Save BrainSense Streaming Data in Database Storage

    Args:
      deviceID: UUID4 deidentified id for each unique Percept device.
      StreamingTD: BrainSense TimeDomain structure extracted from Medtronic JSON file.
      StreamingPower: BrainSense Power Channel structure extracted from Medtronic JSON file.
      sourceFile: filename of the raw JSON file that the original data extracted from.

    Returns:
      Boolean indicating if new data is found (to be saved).
    """

    TimeDomainRecordings = []
    PowerDomainRecordings = []

    StreamingTD.sort(key=lambda element: element["FirstPacketDateTime"] + len(element["Data"])/element["SamplingRate"])
    StreamingPower.sort(key=lambda element: element["FirstPacketDateTime"] + len(element["Power"])/element["SamplingRate"])

    n = 0
    while n < len(StreamingTD):
        if n+1 >= len(StreamingTD):
            Recording = dict()
            Recording["SamplingRate"] = StreamingTD[n]["SamplingRate"]
            Recording["ChannelNames"] = [StreamingTD[n]["Channel"]]
            Recording["Data"] = np.zeros((len(StreamingTD[n]["Data"]), 1))
            Recording["Data"][:,0] = StreamingTD[n]["Data"]
            Recording["Missing"] = np.zeros((len(StreamingTD[n]["Missing"]), 1))
            Recording["Missing"][:,0] = StreamingTD[n]["Missing"]
            Recording["StartTime"] = StreamingTD[n]["FirstPacketDateTime"]
            Recording["Duration"] = Recording["Data"].shape[0] / Recording["SamplingRate"]
            TimeDomainRecordings.append(Recording)
            n += 1

        elif StreamingTD[n]["FirstPacketDateTime"] == StreamingTD[n+1]["FirstPacketDateTime"]:
            Recording = dict()
            Recording["SamplingRate"] = StreamingTD[n]["SamplingRate"]
            Recording["ChannelNames"] = [StreamingTD[n]["Channel"], StreamingTD[n+1]["Channel"]]
            
            if not len(StreamingTD[n]["Data"]) == len(StreamingTD[n+1]["Data"]):
                Recording["Data"] = np.zeros((np.max((len(StreamingTD[n]["Data"]),len(StreamingTD[n+1]["Data"]))), 2))
                Recording["Missing"] = np.ones((np.max((len(StreamingTD[n]["Data"]),len(StreamingTD[n+1]["Data"]))), 2))
                Recording["Data"][:len(StreamingTD[n]["Data"]),0] = StreamingTD[n]["Data"]
                Recording["Data"][:len(StreamingTD[n+1]["Data"]),1] = StreamingTD[n+1]["Data"]
                Recording["Missing"][:len(StreamingTD[n]["Data"]),0] = StreamingTD[n]["Missing"]
                Recording["Missing"][:len(StreamingTD[n+1]["Data"]),1] = StreamingTD[n+1]["Missing"]
            else:
                Recording["Data"] = np.zeros((len(StreamingTD[n]["Data"]), 2))
                Recording["Missing"] = np.ones((len(StreamingTD[n]["Missing"]), 2))
                Recording["Data"][:,0] = StreamingTD[n]["Data"]
                Recording["Data"][:,1] = StreamingTD[n+1]["Data"]
                Recording["Missing"][:,0] = StreamingTD[n]["Missing"]
                Recording["Missing"][:,1] = StreamingTD[n+1]["Missing"]

            Recording["StartTime"] = StreamingTD[n]["FirstPacketDateTime"]
            Recording["Duration"] = Recording["Data"].shape[0] / Recording["SamplingRate"]
            TimeDomainRecordings.append(Recording)
            n += 2

        else:
            Recording = dict()
            Recording["SamplingRate"] = StreamingTD[n]["SamplingRate"]
            Recording["ChannelNames"] = [StreamingTD[n]["Channel"]]
            Recording["Data"] = np.zeros((len(StreamingTD[n]["Data"]), 1))
            Recording["Data"][:,0] = StreamingTD[n]["Data"]
            Recording["Missing"] = np.zeros((len(StreamingTD[n]["Missing"]), 1))
            Recording["Missing"][:,0] = StreamingTD[n]["Missing"]
            Recording["StartTime"] = StreamingTD[n]["FirstPacketDateTime"]
            Recording["Duration"] = Recording["Data"].shape[0] / Recording["SamplingRate"]
            TimeDomainRecordings.append(Recording)
            n += 1

    for n in range(len(StreamingPower)):
        Recording = dict()
        Recording["SamplingRate"] = StreamingPower[n]["SamplingRate"]
        Channel = StreamingPower[n]["Channel"].split(",")
        if len(Channel) == 1:
            Recording["ChannelNames"] = [Channel[0] + " Power", Channel[0] + " Stimulation"]
            ChannelIndex = 0 if np.all(np.array(StreamingPower[n]["Power"][:,1]) == 0) else 1
            Recording["Data"] = np.zeros((len(StreamingPower[n]["Power"]), 2))
            Recording["Missing"] = np.zeros((len(StreamingPower[n]["Missing"]), 2))
            Recording["Data"][:,0] = StreamingPower[n]["Power"][:,ChannelIndex]
            Recording["Data"][:,1] = StreamingPower[n]["Stimulation"][:,ChannelIndex]
            Recording["Missing"][:,0] = StreamingPower[n]["Missing"][:,ChannelIndex]
            Recording["Missing"][:,1] = StreamingPower[n]["Missing"][:,ChannelIndex]
        else:
            Recording["ChannelNames"] = [Channel[0] + " Power", Channel[1] + " Power", Channel[0] + " Stimulation", Channel[1] + " Stimulation"]
            Recording["Data"] = np.zeros((len(StreamingPower[n]["Power"]), 4))
            Recording["Missing"] = np.zeros((len(StreamingPower[n]["Missing"]), 4))
            Recording["Data"][:,:2] = StreamingPower[n]["Power"]
            Recording["Data"][:,2:] = StreamingPower[n]["Stimulation"]
            Recording["Missing"][:,:2] = StreamingPower[n]["Missing"]
            Recording["Missing"][:,2:] = StreamingPower[n]["Missing"]

        Recording["StartTime"] = StreamingPower[n]["FirstPacketDateTime"]
        Recording["Duration"] = Recording["Data"].shape[0] / Recording["SamplingRate"]
        Recording["Descriptor"] = {
            "Therapy": StreamingPower[n]["TherapySnapshot"]
        }
        
        PowerDomainRecordings.append(Recording)

    if len(TimeDomainRecordings) == len(PowerDomainRecordings):

        # Updated Power Domain Alignment based on Benchtop Testing
        for n in range(len(TimeDomainRecordings)):
            for i in range(len(StreamingTD)):
                if StreamingTD[i]["FirstPacketDateTime"] == TimeDomainRecordings[n]["StartTime"]:
                    for j in range(len(StreamingTD[i]["Ticks"])):
                        if StreamingTD[i]["Sequences"][j] == (StreamingPower[n]["Sequences"][0] - 1):
                            #PowerDomainRecordings[n]["StartTime"] = TimeDomainRecordings[n]["StartTime"] + (StreamingTD[i]["Ticks"][j] - StreamingTD[i]["Ticks"][0]) / 1000
                            pass # NEED VERIFICATION
        
        if FixBreaking:
            print("Fix Breaking")
            # Fix Breaking TimeDomain Recording based on PowerDomain Recordings (Therapy) Descriptor
            i = 1
            while i < len(TimeDomainRecordings):
                # if Channel Name is not matching:
                if not TimeDomainRecordings[i]["ChannelNames"] == TimeDomainRecordings[i-1]["ChannelNames"] or not PowerDomainRecordings[i]["ChannelNames"] == PowerDomainRecordings[i-1]["ChannelNames"]:
                    i += 1
                    continue

                # if Therapy is not matching
                # First, we will remove LowerLimitInMilliAmps and UpperLimitInMilliAmps from comparison.
                # Because adjustment of amplitude could change such limit. 
                for ChannelName in TimeDomainRecordings[i]["ChannelNames"]:
                    channels, hemisphere = Percept.reformatChannelName(ChannelName)

                PowerDomainRecordings[i]["Descriptor"]["Therapy"][hemisphere]["LowerLimitInMilliAmps"] = 0
                PowerDomainRecordings[i]["Descriptor"]["Therapy"][hemisphere]["UpperLimitInMilliAmps"] = 0
                PowerDomainRecordings[i-1]["Descriptor"]["Therapy"][hemisphere]["LowerLimitInMilliAmps"] = 0
                PowerDomainRecordings[i-1]["Descriptor"]["Therapy"][hemisphere]["UpperLimitInMilliAmps"] = 0 
                
                if not Percept.dictionaryCompare(PowerDomainRecordings[i]["Descriptor"]["Therapy"], PowerDomainRecordings[i-1]["Descriptor"]["Therapy"]):
                    i += 1
                    continue

                # Now that we know they are supposed to be identical. There is still the concern that "Segmented Stimulation" is not stored in SenSight Leads.
                # Our Criteria should be the following:
                #       1) 2nd Stream start stimulation amplitude = 1st Stream
                #       2) If both end/start are 0, the 1st Stream does not contain high stimulation amplitude.
                StimulationChannelIndexes = [n for n in range(len(PowerDomainRecordings[i]["ChannelNames"])) if PowerDomainRecordings[i]["ChannelNames"][n].endswith("Stimulation")]
                StartAmplitude = PowerDomainRecordings[i]["Data"][0, StimulationChannelIndexes].tolist()
                EndAmplitude = PowerDomainRecordings[i-1]["Data"][-1, StimulationChannelIndexes].tolist()
                if not StartAmplitude == EndAmplitude: 
                    i += 1
                    continue

                if np.max(StartAmplitude) == 0:
                    PreviousUniqueAmplitudes = []
                    for n in StimulationChannelIndexes:
                        PreviousUniqueAmplitudes.extend(np.unique(PowerDomainRecordings[i-1]["Data"][:, n]).tolist())

                    # Stimulation Unchanged
                    if not len(PreviousUniqueAmplitudes) == len(StimulationChannelIndexes): 
                        i += 1
                        continue
                
                Timeskip = TimeDomainRecordings[i]["StartTime"] - (TimeDomainRecordings[i-1]["StartTime"] + TimeDomainRecordings[i-1]["Duration"])
                if Timeskip > 30: # This has been updated to 30 seconds break only in favor of AnalysisBuilder customized inclusion
                    i += 1
                    continue

                if Timeskip < -1:
                    print("Timeskip is negative. Failure in identifying StartTime?")
                    i += 1
                    continue

                # To Merge
                nSampleSkipped = int(Timeskip * TimeDomainRecordings[i]["SamplingRate"])
                if nSampleSkipped < 0: 
                    nSampleSkipped = 0
                    
                TimeDomainRecordings[i-1]["Data"] = np.concatenate((TimeDomainRecordings[i-1]["Data"], np.zeros((nSampleSkipped, TimeDomainRecordings[i-1]["Data"].shape[1])), TimeDomainRecordings[i]["Data"]))
                TimeDomainRecordings[i-1]["Missing"] = np.concatenate((TimeDomainRecordings[i-1]["Missing"], np.ones((nSampleSkipped, TimeDomainRecordings[i-1]["Missing"].shape[1])), TimeDomainRecordings[i]["Missing"]))
                TimeDomainRecordings[i-1]["Duration"] = TimeDomainRecordings[i]["StartTime"] + TimeDomainRecordings[i]["Duration"] - TimeDomainRecordings[i-1]["StartTime"]

                nSampleSkipped = int(Timeskip * PowerDomainRecordings[i]["SamplingRate"])
                if nSampleSkipped < 0: 
                    nSampleSkipped = 0

                FillingData = np.zeros((nSampleSkipped, PowerDomainRecordings[i-1]["Data"].shape[1]))
                FillingData[:, StimulationChannelIndexes] = StartAmplitude
                PowerDomainRecordings[i-1]["Data"] = np.concatenate((PowerDomainRecordings[i-1]["Data"], FillingData, PowerDomainRecordings[i]["Data"]))
                PowerDomainRecordings[i-1]["Missing"] = np.concatenate((PowerDomainRecordings[i-1]["Missing"], np.ones((nSampleSkipped, PowerDomainRecordings[i-1]["Missing"].shape[1])), PowerDomainRecordings[i]["Missing"]))
                PowerDomainRecordings[i-1]["Duration"] = PowerDomainRecordings[i]["StartTime"] + PowerDomainRecordings[i]["Duration"] - PowerDomainRecordings[i-1]["StartTime"]

                del(PowerDomainRecordings[i])
                del(TimeDomainRecordings[i])
    
    return TimeDomainRecordings, PowerDomainRecordings

def createDefaultAnalysis(TimeDomainRecordings, PowerDomainRecordings):
    AllAnalyses = []
    for i in range(len(TimeDomainRecordings)):
        for j in range(len(PowerDomainRecordings)):
            LatestStartTime = np.max((PowerDomainRecordings[j]["Date"], TimeDomainRecordings[i]["Date"]))
            EarliestEndTime = np.min((PowerDomainRecordings[j]["Date"] + PowerDomainRecordings[j]["Metadata"]["Duration"], TimeDomainRecordings[i]["Date"] + TimeDomainRecordings[i]["Metadata"]["Duration"]))
            ShortestDuration = np.min((PowerDomainRecordings[j]["Metadata"]["Duration"], TimeDomainRecordings[i]["Metadata"]["Duration"]))
            if LatestStartTime <= EarliestEndTime:
                Overlap = (EarliestEndTime - LatestStartTime) / ShortestDuration
                if Overlap > 0.7 and Overlap < 1.3 and np.abs(PowerDomainRecordings[j]["Metadata"]["Duration"] - TimeDomainRecordings[i]["Metadata"]["Duration"]) < 180:
                    AllAnalyses.append({
                        "Type": "DefaultTherapeuticAnalysis",
                        "Name": "",
                        "Date": TimeDomainRecordings[i]["Date"],
                        "DataType": ["MedtronicTimeDomain", "MedtronicTherapy"],
                        "DataShift": [0,0],
                        "Metadata": {
                            "Timezone": TimeDomainRecordings[i]["Timezone"],
                            "DataId": [TimeDomainRecordings[i]["Id"], PowerDomainRecordings[j]["Id"]],
                        },
                    })
                    
    return AllAnalyses

def processTherapyInformation(data, devceInfo):
    StimulationSeries = []
    TherapyConfiguration = data["Descriptor"]
    for i in range(len(data["ChannelNames"])):
        if data["ChannelNames"][i].endswith("Stimulation"):
            Channel, Hemisphere = Percept.reformatChannelName(data["ChannelNames"][i].replace(" Stimulation",""))
            Target = ""
            for lead in devceInfo["Electrodes"]:
                if lead["Target"].startswith(Hemisphere):
                    Target = lead["CustomName"] + " " + f"E{Channel[0]:02}-E{Channel[1]:02}"
            
            if "ElectrodeState" in TherapyConfiguration["Therapy"][Hemisphere].keys():
                StimulationContact = Percept.reformatStimulationChannel(TherapyConfiguration["Therapy"][Hemisphere]["ElectrodeState"])
            elif "SensingChannel" in TherapyConfiguration["Therapy"][Hemisphere].keys():
                SensingContact, Hemisphere = Percept.reformatChannelName(TherapyConfiguration["Therapy"][Hemisphere]["SensingChannel"].replace("SensingChannelDef.",""))
                if SensingContact == [0,2]:
                    StimulationContact = "E01"
                elif SensingContact == [1,3]:
                    StimulationContact = "E02"
                elif SensingContact == [0,3]:
                    StimulationContact = "E01-E02"
            
            Stimulation = np.around(data["Data"][:,i],2)
            TimeArray = np.arange(len(Stimulation)) / data["SamplingRate"] + data["StartTime"]
            indexOfChanges = np.where(np.abs(np.diff(Stimulation)) > 0)[0]+1
            if len(indexOfChanges) == 0:
                indexOfChanges = np.insert(indexOfChanges,0,0)
            elif indexOfChanges[0] < 0:
                indexOfChanges[0] = 0
            else:
                indexOfChanges = np.insert(indexOfChanges,0,0)
            indexOfChanges = np.insert(indexOfChanges,len(indexOfChanges),len(Stimulation)-1)

            for j in indexOfChanges:
                StimulationSeries.append({"Time": TimeArray[j], "TherapyOverview": {
                    "Type": "StandardIPGStimulation",
                    "Device": devceInfo["GenericName"],
                    "Name": StimulationContact, "Hemisphere": Hemisphere,
                    "Amplitude": Stimulation[j], "Frequency": TherapyConfiguration["Therapy"][Hemisphere]["RateInHertz"],
                    "Pulsewidth": TherapyConfiguration["Therapy"][Hemisphere]["PulseWidthInMicroSecond"],
                    "Dosage": TherapyConfiguration["Therapy"][Hemisphere]["RateInHertz"] * TherapyConfiguration["Therapy"][Hemisphere]["PulseWidthInMicroSecond"] * (Stimulation[j]*1e-3) * 1000 * Stimulation[j]*1e-3, # TODO: Get Therapy Impedance Somewhere
                    "DosageUnit": "μW",
                    "ChannelName": Target
                }})

    StimulationSeries.sort(key=lambda x: x["Time"])

    CurrentTherapy = {}
    StimulationSeriesFormatted = []
    for i in range(len(StimulationSeries)):
        TherapyTarget = StimulationSeries[i]["TherapyOverview"]["Device"] + ": " + StimulationSeries[i]["TherapyOverview"]["ChannelName"]
        CurrentTherapy[TherapyTarget] = StimulationSeries[i]["TherapyOverview"]
        if i > 0:
            if not StimulationSeries[i-1]["Time"] == StimulationSeries[i]["Time"]:
                StimulationSeries[i]["TherapyOverview"] = CurrentTherapy.copy()
                StimulationSeriesFormatted.append(StimulationSeries[i])
            else:
                StimulationSeriesFormatted[-1]["TherapyOverview"] = CurrentTherapy.copy()
        else:
            StimulationSeries[i]["TherapyOverview"] = CurrentTherapy.copy()
            StimulationSeriesFormatted.append(StimulationSeries[i])

    TherapyKey = "Amplitude"
    TherapyGraph = []
    for hemisphere in ["Left", "Right"]:
        TherapyGraphTrend = {
            "Channel": "", 
            "Value": [],
            "Unit": "mA",
            "Legend": ""
        }

        LastTherapyIndex = ""
        for i in range(len(StimulationSeriesFormatted)):
            if hemisphere in StimulationSeriesFormatted[i]["TherapyOverview"].keys():
                if LastTherapyIndex == "" or StimulationSeriesFormatted[i]["TherapyOverview"][hemisphere][TherapyKey] != LastTherapyIndex:
                    LastTherapyIndex = StimulationSeriesFormatted[i]["TherapyOverview"][hemisphere][TherapyKey]
                    if len(TherapyGraphTrend["Value"]) > 0:
                        TherapyGraphTrend["Value"].append({
                            "Time": StimulationSeriesFormatted[i]["Time"],
                            "Value": TherapyGraphTrend["Value"][len(TherapyGraphTrend["Value"])-1]["Value"]
                        })
                    TherapyGraphTrend["Value"].append({
                        "Time": StimulationSeriesFormatted[i]["Time"],
                        "Value": LastTherapyIndex
                    })
                    TherapyGraphTrend["Channel"] = StimulationSeriesFormatted[i]["TherapyOverview"][hemisphere]["ChannelName"]
        
        if len(TherapyGraphTrend["Value"]) > 0:
            TherapyGraphTrend["Value"].append({
                "Time": StimulationSeriesFormatted[-1]["Time"],
                "Value": TherapyGraphTrend["Value"][len(TherapyGraphTrend["Value"])-1]["Value"]
            })
            TherapyGraph.append(TherapyGraphTrend)

    return StimulationSeriesFormatted, TherapyGraph

def reformatChannelName(name, electrodes):
    Target = ""

    if "_REFERENCE_" in name:
        Channel, Hemisphere = Percept.reformatChannelName(name)[0]
        for lead in electrodes:
            if lead["Target"].startswith(Hemisphere):
                if type(Channel[0]) == int:
                    Target = lead["CustomName"] + " " + f"E{Channel[0]:02}"
                else:
                    Target = lead["CustomName"] + " " + f"E0{Channel[0]:.1f}"
    else:
        Channel, Hemisphere = Percept.reformatChannelName(name)
        for lead in electrodes:
            if lead["Target"].startswith(Hemisphere):
                if type(Channel[0]) == int:
                    Target = lead["CustomName"] + " " + f"E{Channel[0]:02}-E{Channel[1]:02}"
                else:
                    Target = lead["CustomName"] + " " + f"E0{Channel[0]:.1f}-E0{Channel[1]:.1f}"
                
    return Target if len(Target) > 0 else name

def reformatStimulationChannel(name, electrodes):
    Channel, Hemisphere = Percept.reformatChannelName(name)
    Target = ""
    for lead in electrodes:
        if lead["Target"].startswith(Hemisphere):
            if Channel == [0,2]:
                Target = lead["CustomName"] + " " + f"E01"
            elif Channel == [1,3]:
                Target = lead["CustomName"] + " " + f"E02"
            elif Channel == [0,3]:
                Target = lead["CustomName"] + " " + f"E01-E02"
            else:
                Target = lead["CustomName"] + " " + f"Sensing: E0{Channel[0]:.1}-E0{Channel[1]:.1}"

    return Target if len(Target) > 0 else name