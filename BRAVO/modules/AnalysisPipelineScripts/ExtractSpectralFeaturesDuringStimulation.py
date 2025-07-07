from Server import models

import os, sys
import datetime, pytz
import numpy as np
from scipy import stats
import pickle

from modules import DataAnalysis, Database, DataCurator
from modules.HelperFunctions import utc_offset_to_timezone

DATABASE_PATH = os.environ.get('DATASERVER_PATH')

AnalysisScriptType = "ExtractSpectralFeaturesDuringStimulation"

def HandleRefreshAnalysis():
    Participants = [participant.get_info() for participant in models.Participant.find_all()]
    source_file = models.SourceFile.find(type=AnalysisScriptType, metadata={
        "User": "Admin"
    })
    if not source_file:
        source_file = models.SourceFile.create(type=AnalysisScriptType, metadata={
            "User": "Admin"
        })
        source_file.name = AnalysisScriptType
        source_file.pointer = DATABASE_PATH + "cache" + os.path.sep + source_file.name + ".bpkl"
        hashed = Database.saveSourceFile([], source_file.pointer)
        source_file.hashed = hashed
        source_file.save()

    RecordingCollections = Database.loadSourceFile(source_file.pointer, source_file.hashed)

    def checkHistory(items, newItem):
        for item in items:
            if item["ParticipantId"] == newItem["ParticipantId"] and item["Date"] == newItem["Date"] and  item["Contact"] == newItem["Contact"]:
                return True
        return False

    for participant in Participants:
        Data = DataAnalysis.queryAvailableAnalyses(participant["Id"], "TimeSeriesAnalysis")
        Dates = {}
        for i in range(len(Data["Recordings"])):
            if Data["Recordings"][i]["Timezone"] == "":
                Data["Recordings"][i]["Timezone"] = "UTC-04:00"
            RecordingDate = datetime.datetime.fromtimestamp(Data["Recordings"][i]["Date"]).astimezone(utc_offset_to_timezone(Data["Recordings"][i]["Timezone"])).strftime("%Y-%m-%d")
            Data["Recordings"][i]["LocalDate"] = RecordingDate
            if "Therapy" in Data["Recordings"][i].keys():
                for j in range(len(Data["Recordings"][i]["Therapy"])):
                    TherapyParameter = str(Data["Recordings"][i]["Therapy"][j]["Frequency"]) + "Hz " + str(Data["Recordings"][i]["Therapy"][j]["Pulsewidth"]) + "uSec"

                    if not Data["Recordings"][i]["Therapy"][j]["Contact"] in Dates.keys():
                        Dates[Data["Recordings"][i]["Therapy"][j]["Contact"]] = {}
                    
                    if not TherapyParameter in Dates[Data["Recordings"][i]["Therapy"][j]["Contact"]].keys():
                        Dates[Data["Recordings"][i]["Therapy"][j]["Contact"]][TherapyParameter] = {}
                        
                    if not RecordingDate in Dates[Data["Recordings"][i]["Therapy"][j]["Contact"]][TherapyParameter].keys():
                        Dates[Data["Recordings"][i]["Therapy"][j]["Contact"]][TherapyParameter][RecordingDate] = []
                    
                    Dates[Data["Recordings"][i]["Therapy"][j]["Contact"]][TherapyParameter][RecordingDate].extend(Data["Recordings"][i]["Therapy"][j]["UniqueAmplitudes"])

        for contact in Dates.keys():
            for therapyParam in Dates[contact].keys():
                for date in Dates[contact][therapyParam].keys():
                    Dates[contact][therapyParam][date] = np.unique(Dates[contact][therapyParam][date])
                    if len(Dates[contact][therapyParam][date]) > 3 and 0 in Dates[contact][therapyParam][date]:
                        Recordings = []
                        for i in range(len(Data["Recordings"])):
                            if "Therapy" in Data["Recordings"][i].keys():
                                if Data["Recordings"][i]["LocalDate"] == date:
                                    for j in range(len(Data["Recordings"][i]["Therapy"])):
                                        if Data["Recordings"][i]["Therapy"][j]["Contact"] == contact:
                                            TherapyParameter = str(Data["Recordings"][i]["Therapy"][j]["Frequency"]) + "Hz " + str(Data["Recordings"][i]["Therapy"][j]["Pulsewidth"]) + "uSec"
                                            if TherapyParameter == therapyParam:
                                                Recordings.append({
                                                    "TimeSeries": Data["Recordings"][i]["Id"],
                                                    "Therapy": Data["Recordings"][i]["Therapy"][j]["Id"]
                                                })

                        collection = {
                            "ParticipantId": participant["Id"],
                            "Diagnosis": participant["Diagnosis"],
                            "Contact": contact,
                            "Date": date,
                            "TherapyParameters": therapyParam,
                            "UniqueAmplitudes": Dates[contact][therapyParam][date],
                            "Recordings": Recordings
                        }
                        if not checkHistory(RecordingCollections, collection):
                            RecordingCollections.append(collection)

    userConfig, _ = Database.retrieveProcessingSettings({"ProcessingConfiguration": {
        "TimeSeriesRecording": {
            "StandardFilter": {
                "value": "Butterworth 1-100Hz"
            },
            "CardiacFilter": {
                "value": "No Filter"
            },
            "SpectrogramMethod": {
                "value": "Welch's Periodogram"
            }
        }
    }})
    userConfig["APIAccess"] = True

    def ExtractTherapyLevelPSDs(Analysis):
        for therapy in Analysis["Therapy"]:
            for k in range(len(therapy["TherapySeries"])):
                therapy["TherapySeries"][k]["Spectrum"] = {}
                therapy["TherapySeries"][k]["Frequency"] = []
                for i in range(len(Analysis["Signal"])):
                    for j in range(len(Analysis["Signal"][i]["SignalSeries"]["ChannelNames"])):
                        Time = np.array(Analysis["Signal"][i]["SignalSeries"]["Spectrum"][j]["Time"]) + Analysis["Signal"][i]["SignalSeries"]["StartTime"]
                        TimeSelection = Time > therapy["TherapySeries"][k]["Time"]+3
                        if k < len(therapy["TherapySeries"])-1:
                            TimeSelection = TimeSelection & (Time < therapy["TherapySeries"][k+1]["Time"]-3)
                        therapy["TherapySeries"][k]["Spectrum"][Analysis["Signal"][i]["SignalSeries"]["ChannelNames"][j]] = np.array(Analysis["Signal"][i]["SignalSeries"]["Spectrum"][j]["Power"])[:,TimeSelection]
                        therapy["TherapySeries"][k]["Frequency"] = np.array(Analysis["Signal"][i]["SignalSeries"]["Spectrum"][j]["Frequency"])
        return Analysis["Therapy"]

    def MovingAverageFilter(signal, window_size):
        window = np.ones(window_size) / window_size
        return np.convolve(signal, window, mode='same')

    def ExtractAperiodicComponents(Frequency, Power):
        FrequencySelection = ((Frequency > 55) & (Frequency < 90)) | ((Frequency > 30) & (Frequency < 40)) 
        YData = np.log10(Power[FrequencySelection])
        XData = np.log10(Frequency[FrequencySelection])
        coe = np.polyfit(XData, YData, 1)
        AperiodicBaseline = np.polyval(coe, np.log10(Frequency))
        for j in range(len(AperiodicBaseline)):
            if np.isnan(AperiodicBaseline[-j-1]):
                AperiodicBaseline[-j-1] = AperiodicBaseline[-j]
        AperiodicBaseline = np.power(10,AperiodicBaseline)
        return AperiodicBaseline

    for collection in RecordingCollections:
        print(collection["ParticipantId"] + " " + collection["Contact"])
        
        SensingChannel = "Unknown"
        if collection["Contact"].endswith("E01-E02"):
            SensingChannel = collection["Contact"].replace("E01-E02","E00-E03")
        elif collection["Contact"].endswith("E02"):
            SensingChannel = collection["Contact"].replace("E02","E01-E03")
        elif collection["Contact"].endswith("E01"):
            SensingChannel = collection["Contact"].replace("E01","E00-E02")
        
        UniqueTherapyAmplitudes = {}
        for recording in collection["Recordings"]:
            Analysis = DataAnalysis.processTimeseriesAnalysis(collection["ParticipantId"], recording["TimeSeries"], userConfig)
            Analysis["Therapy"] = DataAnalysis.processTimeseriesAnalysis(collection["ParticipantId"], recording["Therapy"], userConfig)["Therapy"]
            TherapyPSDs = ExtractTherapyLevelPSDs(Analysis)
            
            for amp in collection["UniqueAmplitudes"]:
                for therapy in TherapyPSDs:
                    for k in range(len(therapy["TherapySeries"])):
                        for chan in therapy["TherapySeries"][k]["TherapyOverview"].keys():
                            if chan.endswith(SensingChannel):
                                if therapy["TherapySeries"][k]["TherapyOverview"][chan]["Amplitude"] == amp:
                                    PSDFrequency = therapy["TherapySeries"][k]["Frequency"]
                                    if chan in therapy["TherapySeries"][k]["Spectrum"].keys():
                                        if not amp in UniqueTherapyAmplitudes.keys():
                                            UniqueTherapyAmplitudes[amp] = therapy["TherapySeries"][k]["Spectrum"][chan]
                                        else:
                                            UniqueTherapyAmplitudes[amp] = np.concatenate((UniqueTherapyAmplitudes[amp], therapy["TherapySeries"][k]["Spectrum"][chan]), axis=1)
        
        GammaFrequency = float(collection["TherapyParameters"].split("Hz ")[0]) / 2
        GammaSelection = (PSDFrequency < GammaFrequency+2) & (PSDFrequency > GammaFrequency-2)
        collection["PSDs"] = []
        for amp in sorted(collection["UniqueAmplitudes"]):
            if amp in UniqueTherapyAmplitudes.keys():
                if UniqueTherapyAmplitudes[amp].shape[1] > 3:
                    PSDInfo = {
                        "PowerSpectrum": np.nanmedian(UniqueTherapyAmplitudes[amp],axis=1),
                        "StdPower": np.nanstd(UniqueTherapyAmplitudes[amp],axis=1) / np.sqrt(UniqueTherapyAmplitudes[amp].shape[1]),
                        "Amplitudes": amp, 
                        "Frequency": PSDFrequency
                    }
                    PSDInfo["AperiodicComponent"] = ExtractAperiodicComponents(PSDFrequency, MovingAverageFilter(PSDInfo["PowerSpectrum"],5))
                    
                    GammaPower = np.nanmedian(UniqueTherapyAmplitudes[amp][GammaSelection, :],axis=0)
                    GammaPower = GammaPower[~np.isnan(GammaPower)]
                    GammaFluctuation = np.mean(UniqueTherapyAmplitudes[amp][((PSDFrequency < 90) & (PSDFrequency > 60)) & (~GammaSelection), :],axis=1)
                    if stats.sem(GammaPower) > 1e5 or stats.sem(GammaFluctuation) > 1e5:
                        continue
                    
                    ConfidenceInterval = stats.t.interval(0.95, len(GammaPower)-1, loc=np.median(GammaPower) / np.median(GammaFluctuation), scale=np.std(GammaFluctuation/ np.median(GammaFluctuation)))
                    
                    PSDInfo["FTG"] = {
                        "CenterFrequency": GammaFrequency,
                        "Power": ConfidenceInterval,
                    }
                    collection["PSDs"].append(PSDInfo)
        
        collection["FTGStats"] = {"FirstAppearance": 0, "MaxGamma": [-99,-99], "LastAppearance": 0}
        if len(collection["PSDs"]) > 1:
            for i in range(1, len(collection["PSDs"])):
                if collection["PSDs"][i]["FTG"]["Power"][0] > collection["PSDs"][0]["FTG"]["Power"][1]:
                    if collection["FTGStats"]["FirstAppearance"] == 0:
                        collection["FTGStats"]["FirstAppearance"] = collection["PSDs"][i]["Amplitudes"]
                    if collection["PSDs"][i]["FTG"]["Power"][0] > collection["FTGStats"]["MaxGamma"][1]:
                        collection["FTGStats"]["MaxGamma"] = collection["PSDs"][i]["FTG"]["Power"]
                    collection["FTGStats"]["LastAppearance"] = collection["PSDs"][i]["Amplitudes"]

    hashed = Database.saveSourceFile(RecordingCollections, source_file.pointer)
    source_file.hashed = hashed
    source_file.save()

def QueryAnalysisResultTable(Participants):
    source_file = models.SourceFile.find(type=AnalysisScriptType, metadata={
        "User": "Admin"
    })
    if not source_file:
        return []

    RecordingCollections = Database.loadSourceFile(source_file.pointer, source_file.hashed)
    ParticipantIds = [participant["Id"] for participant in Participants]

    RecordingCollections = [collection for collection in RecordingCollections if collection["ParticipantId"] in ParticipantIds]
    
    ResultTable = {"Participants": Participants, "RecordingCollection": []}
    for collection in RecordingCollections:
        ResultTable["RecordingCollection"].append({
            "ParticipantId": collection["ParticipantId"],
            "Date": collection["Date"],
            "Contact": collection["Contact"],
            "TherapyParameters": collection["TherapyParameters"],
            "UniqueAmplitudes": collection["UniqueAmplitudes"],
            "FTGStats": collection["FTGStats"]
        })
        
    return ResultTable

def QueryAnalysisResultPSD(ParticipantId, Contact):
    source_file = models.SourceFile.find(type=AnalysisScriptType, metadata={
        "User": "Admin"
    })
    if not source_file:
        return []

    RecordingCollections = Database.loadSourceFile(source_file.pointer, source_file.hashed)
    RecordingCollections = [collection for collection in RecordingCollections if collection["ParticipantId"] == ParticipantId]
    
    Result = []
    for collection in RecordingCollections:
        if collection["Date"] + " " + collection["Contact"] + " " + collection["TherapyParameters"] == Contact:
            Result = collection["PSDs"]
        
    return Result

def QueryAnalysisResultRaw(Participants):
    source_file = models.SourceFile.find(type=AnalysisScriptType, metadata={
        "User": "Admin"
    })
    if not source_file:
        return []

    ParticipantIds = [participant["Id"] for participant in Participants]
    RecordingCollections = Database.loadSourceFile(source_file.pointer, source_file.hashed)
    RecordingCollections = [collection for collection in RecordingCollections if collection["ParticipantId"] in ParticipantIds]
    
    return pickle.dumps(RecordingCollections)