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
Data Analysis Pipelines
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os, sys, pathlib
import pickle, blosc
import hashlib, hmac
import shutil
import copy
from filelock import Timeout, FileLock

import numpy as np
from scipy import signal, stats, optimize
from specparam import SpectralModel

from Server import models
import modules.utility.SignalProcessingUtility as SPU
from modules.utility.PythonUtility import rangeSelection, uniqueList
from modules import Database, Therapy, Event
from modules.MedtronicPercept import BrainSenseStream, ChronicBrainSense, BrainSenseEvent, Percept

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

def queryAvailableAnalyses(participant_uid, request_type):
    Overview = {"Analyses": [], "Recordings": []}
    Participant = models.Participant.find(uid=participant_uid)
    if request_type == "TherapeuticAnalysis":
        SourceFiles = models.SourceFile.find_all(owner=Participant)
        DBSDevices = [device.get_info() for device in models.DBSDevice.find_all(owner=Participant)]
        Recordings = models.Recording.find_all(source__in=SourceFiles, type__in=["MedtronicBrainSenseTimeDomain", "MedtronicBrainSensePowerDomain", "MedtronicIndefiniteStream"])
        
        Overview["Recordings"] = []
        for recording in Recordings:
            Description = recording.get_info()
            if recording.type == "MedtronicBrainSenseTimeDomain":
                for device in DBSDevices:
                    if device["Id"] == recording.source.metadata["Device"]:
                        Description["Device"] = device
                        for i in range(len(Description["Metadata"]["ChannelNames"])):
                            Description["Metadata"]["ChannelNames"][i] = BrainSenseStream.reformatChannelName(Description["Metadata"]["ChannelNames"][i], Description["Device"]["Electrodes"])

            elif recording.type == "MedtronicBrainSensePowerDomain":
                for device in DBSDevices:
                    if device["Id"] == recording.source.metadata["Device"]:
                        Description["Therapy"] = [{
                            "Hemisphere": side,
                            "Frequency": recording.metadata["Therapy"][side]["RateInHertz"],
                            "Pulsewidth": recording.metadata["Therapy"][side]["PulseWidthInMicroSecond"],
                            "Contact": BrainSenseStream.reformatStimulationChannel(recording.metadata["Therapy"][side]["SensingChannel"].replace("SensingChannelDef.",""), device["Electrodes"]),
                            "Segment": ""
                        } for side in ["Left", "Right"] if side in recording.metadata["Therapy"].keys()]
                        Description["Device"] = device
                        for i in range(len(Description["Metadata"]["ChannelNames"])):
                            if Description["Metadata"]["ChannelNames"][i].endswith("Stimulation"):
                                Description["Metadata"]["ChannelNames"][i] = BrainSenseStream.reformatChannelName(Description["Metadata"]["ChannelNames"][i], Description["Device"]["Electrodes"]) + " Stimulation"
                            else:
                                Description["Metadata"]["ChannelNames"][i] = BrainSenseStream.reformatChannelName(Description["Metadata"]["ChannelNames"][i], Description["Device"]["Electrodes"]) + " Recording"

            Overview["Recordings"].append(Description)
        
        AnalysisList = BrainSenseStream.createDefaultAnalysis([recording for recording in Overview["Recordings"] if recording["Type"] == "MedtronicBrainSenseTimeDomain"],
                                                              [recording for recording in Overview["Recordings"] if recording["Type"] == "MedtronicBrainSensePowerDomain"])
        
        for analysis in AnalysisList:
            Analysis = models.Analysis.find(type=analysis["Type"], metadata__DataId=analysis["Metadata"]["DataId"])
            if not Analysis:
                print(analysis["Metadata"]["DataId"])
                Analysis = models.Analysis.create(type=analysis["Type"], name=analysis["Name"], date=analysis["Date"], metadata=analysis["Metadata"])
                for recordingId in analysis["Metadata"]["DataId"]:
                    recording = Recordings.filter(uid=recordingId).first() # NOTE: SQL-Specific QuerySet
                    Analysis.add_recording(recording)
            
            Overview["Analyses"].append(Analysis.get_info())
        
    return Overview

def processTherapeuticAnalysis(participant_uid, analysis_uid, config):
    Analysis = models.Analysis.find(uid=analysis_uid)
    AnalysisStruct = {"Signal": [], "Therapy": [], "Annotations": []}
    for recording in Analysis.recordings.all():
        if not recording.source.owner.pk == participant_uid:
            raise Exception("Permission Denied. Accessing Denied Recordings")
        
        if recording.type in ["MedtronicBrainSenseTimeDomain"]:
            rel = models.RecordingRel.find(analysis=Analysis, recording=recording)
            Data = Database.loadSourceFile(recording.pointer, recording.hashed)
            Data = processTimeDomainStreaming(recording, Data, config)
            Data["Data"] = Data["Data"].T
            del Data["Missing"]
            
            DBSDevice = models.DBSDevice.find(uid=recording.source.metadata["Device"]).get_info()
            for i in range(len(Data["ChannelNames"])):
                Data["ChannelNames"][i] = DBSDevice["Heritage"] + ": " + BrainSenseStream.reformatChannelName(Data["ChannelNames"][i], DBSDevice["Electrodes"])

            TimeShift = rel.time_shift if rel else 0
            AnalysisStruct["Signal"].append({
                "Type": "Signal",
                "RecordingId": recording.uid,
                "SignalSeries": Data,
                "Alignment": TimeShift
            })

            Annotations = Event.queryAnnotations(participant_uid, "RecordingCustomEvent", start_time=Data["StartTime"]+TimeShift, duration=Data["Duration"])
            AnalysisStruct["Annotations"].extend(Annotations)

        elif recording.type in ["MedtronicBrainSensePowerDomain"]:
            rel = models.RecordingRel.find(analysis=Analysis, recording=recording)
            Data = Database.loadSourceFile(recording.pointer, recording.hashed)
            DBSDevice = models.DBSDevice.find(uid=recording.source.metadata["Device"]).get_info()
            TherapeuticLabel, TherapyGraphs = BrainSenseStream.processTherapyInformation(Data, DBSDevice)
            AnalysisStruct["Therapy"].append({
                "Type": "Therapy",
                "RecordingId": recording.uid,
                "TherapySeries": TherapeuticLabel,
                "TherapyGraphs": TherapyGraphs,
                "Alignment": rel.time_shift if rel else 0
            })

    AnalysisStruct["Annotations"] = uniqueList(AnalysisStruct["Annotations"])
    return AnalysisStruct

def processTimeDomainStreaming(recording, data, config):
    if config["TimeSeriesRecording"]["StandardFilter"]["value"] == "Butterworth 1-100Hz":
        [b,a] = signal.butter(5, np.array([1,100])*2/data["SamplingRate"], 'bp', output='ba')
        data["Data"] = signal.filtfilt(b, a, data["Data"], axis=0)

    if config["TimeSeriesRecording"]["NotchFilter"]["value"] == "Notch 55-65Hz":
        [b,a] = signal.butter(5, np.array([55,65])*2/data["SamplingRate"], 'bandstop', output='ba')
        data["Data"] = signal.filtfilt(b, a, data["Data"], axis=0)
    elif config["TimeSeriesRecording"]["NotchFilter"]["value"] == "Notch 45-55Hz":
        [b,a] = signal.butter(5, np.array([45,55])*2/data["SamplingRate"], 'bandstop', output='ba')
        data["Data"] = signal.filtfilt(b, a, data["Data"], axis=0)

    for i in range(len(data["ChannelNames"])):
        if config["TimeSeriesRecording"]["WienerFilter"]["value"] == "Use Wiener Filter":
            data["Data"][:,i] -= signal.wiener(data["Data"][:,i], mysize=int(data["SamplingRate"] / 2))

    if config["TimeSeriesRecording"]["CardiacFilter"]["value"] == "Use Adaptive Template Matching":
        data = handleCardiacFilter(recording, data, {
            "StandardFilter": config["TimeSeriesRecording"]["StandardFilter"]["value"],
            "NotchFilter": config["TimeSeriesRecording"]["NotchFilter"]["value"],
            "WienerFilter": config["TimeSeriesRecording"]["WienerFilter"]["value"],
            "CardiacFilter": config["TimeSeriesRecording"]["CardiacFilter"]["value"]
        })
    
    data = handleTimeFrequencyAnalysis(recording, data, {
        "StandardFilter": config["TimeSeriesRecording"]["StandardFilter"]["value"],
        "NotchFilter": config["TimeSeriesRecording"]["NotchFilter"]["value"],
        "WienerFilter": config["TimeSeriesRecording"]["WienerFilter"]["value"],
        "CardiacFilter": config["TimeSeriesRecording"]["CardiacFilter"]["value"],
        "SpectrogramMethod": config["TimeSeriesRecording"]["SpectrogramMethod"]["value"],
        "BaselineCorrection": config["TimeSeriesRecording"]["BaselineCorrection"]["value"],
        "Normalization": config["TimeSeriesRecording"]["Normalization"]["value"]
    })

    return data

def handleCardiacFilter(recording, data, config):
    ProcessedData = models.ProcessedRecording.find(source=recording, type="CardiacFlitered", metadata=config)
    if ProcessedData:
        return Database.loadSourceFile(ProcessedData.pointer, ProcessedData.hashed)

    Window = int(data["SamplingRate"] / 2)
    for i in range(len(data["ChannelNames"])):
        KurtosisIndex = range(0, len(data["Data"][:,i])-Window)
        ExpectedKurtosis = np.zeros((len(KurtosisIndex)))
        for j in range(len(KurtosisIndex)):
            zScore = stats.zscore(data["Data"][:,i][KurtosisIndex[j]:KurtosisIndex[j]+Window])
            ExpectedKurtosis[j] = np.mean(np.power(zScore, 4))

        [b,a] = signal.butter(3, np.array([0.5, 2])*2/data["SamplingRate"], "bandpass")
        ExpectedKurtosis = signal.filtfilt(b,a,ExpectedKurtosis)
        Peaks, _ = signal.find_peaks(ExpectedKurtosis, distance=125)
        Peaks += int(Window/2)

        CardiacEpochs = []
        SearchWindow = int(data["SamplingRate"] * 0.4)
        for j in range(len(Peaks)):
            if ExpectedKurtosis[Peaks[j]-int(Window/2)] < 1.2:
                continue

            ShiftPeak = 0
            if Peaks[j]-SearchWindow-ShiftPeak < 0 or Peaks[j]+SearchWindow-ShiftPeak >= len(data["Data"][:,i]):
                continue 
            findPeak = np.argmax(data["Data"][:,i][Peaks[j]-SearchWindow:Peaks[j]+SearchWindow])
            ShiftPeak = SearchWindow-findPeak
            if Peaks[j]-SearchWindow-ShiftPeak < 0 or Peaks[j]+SearchWindow-ShiftPeak >= len(data["Data"][:,i]):
                continue 
            CardiacEpochs.append(data["Data"][:,i][Peaks[j]-SearchWindow-ShiftPeak:Peaks[j]+SearchWindow-ShiftPeak])

        EKGTemplate = np.mean(np.array(CardiacEpochs), axis=0)
        EKGTemplate = EKGTemplate / (np.max(EKGTemplate)-np.min(EKGTemplate))

        def EKGTemplateFunc(xdata, amplitude, offset):
            return EKGTemplate * amplitude + offset

        CardiacFiltered = copy.deepcopy(data["Data"][:,i])
        for j in range(len(Peaks)):
            ShiftPeak = 0
            if Peaks[j]-SearchWindow-ShiftPeak < 0 or Peaks[j]+SearchWindow-ShiftPeak >= len(data["Data"][:,i]):
                continue 

            findPeak = np.argmax(data["Data"][:,i][Peaks[j]-SearchWindow:Peaks[j]+SearchWindow])
            ShiftPeak = SearchWindow-findPeak
            if Peaks[j]-SearchWindow-ShiftPeak < 0 or Peaks[j]+SearchWindow-ShiftPeak >= len(data["Data"][:,i]):
                continue
            
            sliceSelection = np.arange(Peaks[j]-SearchWindow-ShiftPeak, Peaks[j]+SearchWindow-ShiftPeak)
            Original = data["Data"][:,i][sliceSelection]
            params, covmat = optimize.curve_fit(EKGTemplateFunc, sliceSelection, Original)
            CardiacFiltered[sliceSelection] = Original - EKGTemplateFunc(sliceSelection, *params)
        data["Data"][:,i] = CardiacFiltered
    
    ProcessedData = models.ProcessedRecording.create(recording, "CardiacFlitered")
    ProcessedData.pointer = DATABASE_PATH + "recordings" + os.path.sep + recording.source.owner.uid + os.path.sep + ProcessedData.uid + ".bdat"
    ProcessedData.hashed = Database.saveSourceFile(data, ProcessedData.pointer)
    ProcessedData.metadata = config
    ProcessedData.save()
    return data

def handleTimeFrequencyAnalysis(recording, data, config):
    ProcessedData = models.ProcessedRecording.find(source=recording, type="TimeFrequencyAnalysis", metadata=config)
    if ProcessedData:
        return Database.loadSourceFile(ProcessedData.pointer, ProcessedData.hashed)
    
    data["Spectrum"] = []
    for i in range(len(data["ChannelNames"])):
        if config["SpectrogramMethod"] == "Welch's Periodogram":
            Spectrum = SPU.welchSpectrogram(data["Data"][:,i], window=1.0, overlap=0.5, frequency_resolution=0.5, fs=data["SamplingRate"])

        elif config["SpectrogramMethod"] == "Short-time Fourier Transform":
            Spectrum = SPU.defaultSpectrogram(data["Data"][:,i], window=1.0, overlap=0.5, frequency_resolution=0.5, fs=data["SamplingRate"])

        else: # Default Welch's Periodogram
            Spectrum = SPU.welchSpectrogram(data["Data"][:,i], window=1.0, overlap=0.5, frequency_resolution=0.5, fs=data["SamplingRate"])

        Spectrum["Missing"] = SPU.calculateMissingLabel(data["Missing"][:,i], window=1.0, overlap=0.5, fs=data["SamplingRate"])
        #Spectrum["Time"] += data["StartTime"] + (Configuration["Descriptor"][recordingId]["TimeShift"]/1000)# TODO Check later
        del Spectrum["logPower"]

        dropMissing = False
        if dropMissing:
            TimeSelection = Spectrum["Missing"] == 0
            Spectrum["Missing"] = Spectrum["Missing"][TimeSelection]
            Spectrum["Time"] = Spectrum["Time"][TimeSelection]
            Spectrum["Power"] = Spectrum["Power"][:, TimeSelection]
            Spectrum["logPower"] = Spectrum["logPower"][:, TimeSelection]
        
        if config["Normalization"] == "1/f PSD Trend Removal":
            meanPSDs = np.nanmean(np.array(Spectrum["Power"]), axis=1)
            WindowRange = [1,data["SamplingRate"]/2 if data["SamplingRate"] < 200 else 100]

            FrequencyWindow = rangeSelection(Spectrum["Frequency"], WindowRange)
            fm = SpectralModel(peak_width_limits=[1,24])
            fm.fit(np.array(Spectrum["Frequency"])[FrequencyWindow], meanPSDs[FrequencyWindow], WindowRange)
            oof = fm.get_model("aperiodic", "linear")
            
            for j in range(Spectrum["Power"].shape[1]):
                Spectrum["Power"][FrequencyWindow,j] = np.array(Spectrum["Power"][FrequencyWindow,j]) / oof

            Spectrum["Power"] = Spectrum["Power"][FrequencyWindow,:]
            Spectrum["Frequency"] = np.array(Spectrum["Frequency"])[FrequencyWindow]
            
        elif config["Normalization"] == "Gamma Band Normalize":
            meanPSDs = np.nanmean(np.array(Spectrum["Power"]), axis=1)
            FrequencyWindow = rangeSelection(Spectrum["Frequency"], [70,90])
            MeanRefPower = np.nanmean(meanPSDs[FrequencyWindow])
            for j in range(Spectrum["Power"].shape[1]):
                Spectrum["Power"][:,j] = np.array(Spectrum["Power"][:,j]) / MeanRefPower
        
        Spectrum["Config"] = {**Spectrum["Config"], **config}
        data["Spectrum"].append(Spectrum)
    
    ProcessedData = models.ProcessedRecording.create(recording, "TimeFrequencyAnalysis")
    ProcessedData.pointer = DATABASE_PATH + "recordings" + os.path.sep + recording.source.owner.uid + os.path.sep + ProcessedData.uid + ".bdat"
    ProcessedData.hashed = Database.saveSourceFile(data, ProcessedData.pointer)
    ProcessedData.metadata = config
    ProcessedData.save()
    return data

def handlePowerSpectralEstimation(recording, data, config):
    ProcessedData = models.ProcessedRecording.find(source=recording, type="PowerSpectralEstimation", metadata=config)
    if ProcessedData:
        return Database.loadSourceFile(ProcessedData.pointer, ProcessedData.hashed)
    
    data["PSD"] = []
    if len(data["ChannelNames"]) == 1:
        data["Data"] = data["Data"].reshape(-1,1)
        data["Missing"] = data["Missing"].reshape(-1,1)

    for i in range(len(data["ChannelNames"])):
        PowerSpectralEstimation = {}
        if config["SpectrogramMethod"] == "Welch's Periodogram":
            Spectrum = SPU.welchSpectrogram(data["Data"][:,i], window=1.0, overlap=0.5, frequency_resolution=0.5, fs=data["SamplingRate"])

        elif config["SpectrogramMethod"] == "Short-time Fourier Transform":
            Spectrum = SPU.defaultSpectrogram(data["Data"][:,i], window=1.0, overlap=0.5, frequency_resolution=0.5, fs=data["SamplingRate"])

        else: # Default Welch's Periodogram
            Spectrum = SPU.welchSpectrogram(data["Data"][:,i], window=1.0, overlap=0.5, frequency_resolution=0.5, fs=data["SamplingRate"])

        Spectrum["Missing"] = SPU.calculateMissingLabel(data["Missing"][:,i], window=1.0, overlap=0.5, fs=data["SamplingRate"])
        TimeSelection = Spectrum["Missing"] == 0
        Spectrum["Power"] = Spectrum["Power"][:, TimeSelection]

        if config["Normalization"] == "1/f PSD Trend Removal":
            meanPSDs = np.nanmean(np.array(Spectrum["Power"]), axis=1)
            WindowRange = [1,data["SamplingRate"]/2 if data["SamplingRate"] < 200 else 100]

            FrequencyWindow = rangeSelection(Spectrum["Frequency"], WindowRange)
            fm = SpectralModel(peak_width_limits=[1,24])
            fm.fit(np.array(Spectrum["Frequency"])[FrequencyWindow], meanPSDs[FrequencyWindow], WindowRange)
            oof = fm.get_model("aperiodic", "linear")
            
            for j in range(Spectrum["Power"].shape[1]):
                Spectrum["Power"][FrequencyWindow,j] = np.array(Spectrum["Power"][FrequencyWindow,j]) / oof

            Spectrum["Power"] = Spectrum["Power"][FrequencyWindow,:]
            Spectrum["Frequency"] = np.array(Spectrum["Frequency"])[FrequencyWindow]
            
        elif config["Normalization"] == "Gamma Band Normalize":
            meanPSDs = np.nanmean(np.array(Spectrum["Power"]), axis=1)
            FrequencyWindow = rangeSelection(Spectrum["Frequency"], [70,90])
            MeanRefPower = np.nanmean(meanPSDs[FrequencyWindow])
            for j in range(Spectrum["Power"].shape[1]):
                Spectrum["Power"][:,j] = np.array(Spectrum["Power"][:,j]) / MeanRefPower
        
        PowerSpectralEstimation["Frequency"] = Spectrum["Frequency"]
        PowerSpectralEstimation["Power"] = np.mean(Spectrum["Power"],axis=1)
        PowerSpectralEstimation["stdPower"] = np.std(Spectrum["Power"],axis=1)
        PowerSpectralEstimation["nObservation"] = np.sum(TimeSelection)
        PowerSpectralEstimation["Config"] = {**Spectrum["Config"], **config}
        data["PSD"].append(PowerSpectralEstimation)
    
    ProcessedData = models.ProcessedRecording.create(recording, "PowerSpectralEstimation")
    ProcessedData.pointer = DATABASE_PATH + "recordings" + os.path.sep + recording.source.owner.uid + os.path.sep + ProcessedData.uid + ".bdat"
    ProcessedData.hashed = Database.saveSourceFile(data, ProcessedData.pointer)
    ProcessedData.metadata = config
    ProcessedData.save()
    return data

def selectRecordingChannel(analysis, channel_names=[]):
    AllChannels = []
    ActiveChannels = []

    FilteredAnalysis = {"Signal": [], "Therapy": analysis["Therapy"], "Annotations": analysis["Annotations"]}
    for trial in range(len(analysis["Signal"])):
        if len(ActiveChannels) == 0:
            if len(channel_names) == 0:
                if len(analysis["Signal"][trial]["SignalSeries"]["ChannelNames"]) > 3:
                    ActiveChannels.append(analysis["Signal"][trial]["SignalSeries"]["ChannelNames"][0])
                    ActiveChannels.append(analysis["Signal"][trial]["SignalSeries"]["ChannelNames"][1])
                    ActiveChannels.append(analysis["Signal"][trial]["SignalSeries"]["ChannelNames"][2])
                else:
                    ActiveChannels.extend(analysis["Signal"][trial]["SignalSeries"]["ChannelNames"])
            else:
                ActiveChannels = channel_names

        for i in range(len(analysis["Signal"][trial]["SignalSeries"]["ChannelNames"])):
            if not analysis["Signal"][trial]["SignalSeries"]["ChannelNames"][i] in AllChannels:
                AllChannels.append(analysis["Signal"][trial]["SignalSeries"]["ChannelNames"][i])

            if analysis["Signal"][trial]["SignalSeries"]["ChannelNames"][i] in ActiveChannels:
                SelectedRecording = copy.deepcopy(analysis["Signal"][trial])
                SelectedRecording["SignalSeries"]["ChannelNames"] = SelectedRecording["SignalSeries"]["ChannelNames"][i]
                SelectedRecording["SignalSeries"]["Data"] = SelectedRecording["SignalSeries"]["Data"][i,:]
                SelectedRecording["SignalSeries"]["Spectrum"] = SelectedRecording["SignalSeries"]["Spectrum"][i]
                FilteredAnalysis["Signal"].append(SelectedRecording)

    FilteredAnalysis["AllChannels"] = AllChannels
    FilteredAnalysis["ActiveChannel"] = ActiveChannels
    return FilteredAnalysis

def queryNeuralActivitySnapshot(participant_uid, config):
    NeuralActivitySnapshot = {"AnalysisType": "NeuralActivitySnapshot", "Recordings": []}

    Participant = models.Participant.find(uid=participant_uid)
    SourceFiles = models.SourceFile.find_all(owner=Participant)
    Recordings = models.Recording.find_all(source__in=SourceFiles, type__in=["MedtronicBrainSenseSurvey", "MedtronicBaselineMontages"])

    for recording in Recordings:
        Description = recording.get_info()
        Data = Database.loadSourceFile(recording.pointer, recording.hashed)
        Data = processNeuralActivitySnapshot(recording, Data, config)
        
        DBSDevice = models.DBSDevice.find(uid=recording.source.metadata["Device"]).get_info()
        for i in range(len(Data["ChannelNames"])):
            Data["ChannelNames"][i] = DBSDevice["Heritage"] + ": " + BrainSenseStream.reformatChannelName(Data["ChannelNames"][i], DBSDevice["Electrodes"])
            Data["ChannelNames"][i] = Data["ChannelNames"][i].replace(".1","A").replace(".2","B").replace(".3","C")

        NeuralActivitySnapshot["Recordings"].append({**Description, **{
            "Type": recording.type,
            "RecordingId": recording.uid,
            "Channels": Data["ChannelNames"],
            "PSDs": Data["PSD"],
        }})
        
    return NeuralActivitySnapshot

def processNeuralActivitySnapshot(recording, data, config):
    ProcessedData = models.ProcessedRecording.find(source=recording, type="TimeFrequencyAnalysis", metadata=config)
    if ProcessedData:
        return Database.loadSourceFile(ProcessedData.pointer, ProcessedData.hashed)
    
    if config["TimeSeriesRecording"]["StandardFilter"]["value"] == "Butterworth 1-100Hz":
        [b,a] = signal.butter(5, np.array([1,100])*2/data["SamplingRate"], 'bp', output='ba')
        data["Data"] = signal.filtfilt(b, a, data["Data"], axis=0)

    if config["TimeSeriesRecording"]["NotchFilter"]["value"] == "Notch 55-65Hz":
        [b,a] = signal.butter(5, np.array([55,65])*2/data["SamplingRate"], 'bandstop', output='ba')
        data["Data"] = signal.filtfilt(b, a, data["Data"], axis=0)
    elif config["TimeSeriesRecording"]["NotchFilter"]["value"] == "Notch 45-55Hz":
        [b,a] = signal.butter(5, np.array([45,55])*2/data["SamplingRate"], 'bandstop', output='ba')
        data["Data"] = signal.filtfilt(b, a, data["Data"], axis=0)

    for i in range(len(data["ChannelNames"])):
        if config["TimeSeriesRecording"]["WienerFilter"]["value"] == "Use Wiener Filter":
            data["Data"][:,i] -= signal.wiener(data["Data"][:,i], mysize=int(data["SamplingRate"] / 2))

    if config["TimeSeriesRecording"]["CardiacFilter"]["value"] == "Use Adaptive Template Matching":
        data = handleCardiacFilter(recording, data, {
            "StandardFilter": config["TimeSeriesRecording"]["StandardFilter"]["value"],
            "NotchFilter": config["TimeSeriesRecording"]["NotchFilter"]["value"],
            "WienerFilter": config["TimeSeriesRecording"]["WienerFilter"]["value"],
            "CardiacFilter": config["TimeSeriesRecording"]["CardiacFilter"]["value"]
        })
    
    data = handlePowerSpectralEstimation(recording, data, {
        "StandardFilter": config["TimeSeriesRecording"]["StandardFilter"]["value"],
        "NotchFilter": config["TimeSeriesRecording"]["NotchFilter"]["value"],
        "WienerFilter": config["TimeSeriesRecording"]["WienerFilter"]["value"],
        "CardiacFilter": config["TimeSeriesRecording"]["CardiacFilter"]["value"],
        "SpectrogramMethod": config["PowerSpectralDensity"]["PSDMethod"]["value"],
        "BaselineCorrection": config["TimeSeriesRecording"]["BaselineCorrection"]["value"],
        "Normalization": config["TimeSeriesRecording"]["Normalization"]["value"]
    })

    return data

def queryChronicNeuralActivity(participant_uid, config):
    Participant = models.Participant.find(uid=participant_uid)
    DBSDevices = models.DBSDevice.find_all(owner=Participant)
    SourceFiles = models.SourceFile.find_all(owner=Participant)

    ChronicNeuralActivity = {"AnalysisType": "", "ChronicNeuralActivity": [], "Annotations": []}

    Annotations = Event.queryDBSEvents(participant_uid, "PatientControllerEvent", source_files=SourceFiles)
    ChronicNeuralActivity["Annotations"].extend(Annotations)

    Annotations = Event.queryAnnotations(participant_uid, "ChronicCustomEvent")
    ChronicNeuralActivity["Annotations"].extend(Annotations)
    
    if models.Recording.include(source__in=SourceFiles, type__in=["MedtronicChronicBrainSense"]):
        ChronicNeuralActivity["AnalysisType"] = "MedtronicChronicBrainSense"
        Recording = models.Recording.find(type="MedtronicChronicNeuralActivity", source__owner=Participant)
        if True:
        #if not Recording:
            Recordings = models.Recording.find_all(source__in=SourceFiles, type__in=["MedtronicChronicBrainSense"])
            Activity = ChronicBrainSense.extractChronicNeuralActivity(Participant, DBSDevices, Recordings, config)
            ChronicNeuralActivity["ChronicNeuralActivity"] = Activity

            source = models.SourceFile(name="ChronicNeuralActivitySource", type="ChronicNeuralActivitySource", owner=Participant)
            source.save()
            recording = models.Recording(name="ChronicNeuralActivity", type="MedtronicChronicNeuralActivity", source=source)
            recording.pointer = DATABASE_PATH + "recordings" + os.path.sep + recording.source.owner.uid + os.path.sep + recording.uid + ".bdat"
            recording.hashed = Database.saveSourceFile(Activity, recording.pointer)
            recording.save()
        else:
            ChronicNeuralActivity["ChronicNeuralActivity"] = Database.loadSourceFile(Recording.pointer, Recording.hashed)

        # Rename Channels
        for i in range(len(ChronicNeuralActivity["ChronicNeuralActivity"])):
            ChronicNeuralActivity["ChronicNeuralActivity"][i]["Device"] = DBSDevices.filter(uid=ChronicNeuralActivity["ChronicNeuralActivity"][i]["Device"]).first().get_info()
            for j in range(len(ChronicNeuralActivity["ChronicNeuralActivity"][i]["ChannelNames"])):
                for k in range(len(ChronicNeuralActivity["ChronicNeuralActivity"][i]["Device"]["Electrodes"])):
                    if ChronicNeuralActivity["ChronicNeuralActivity"][i]["ChannelNames"][j].startswith(ChronicNeuralActivity["ChronicNeuralActivity"][i]["Device"]["Electrodes"][k]["Target"].split(" ")[0]):
                        ChronicNeuralActivity["ChronicNeuralActivity"][i]["ChannelNames"][j] = ChronicNeuralActivity["ChronicNeuralActivity"][i]["Device"]["Electrodes"][k]["CustomName"] + " " + ChronicNeuralActivity["ChronicNeuralActivity"][i]["ChannelNames"][j].split(" ")[-1]
                        break
        
        # Annotation Events
        for i in range(len(ChronicNeuralActivity["Annotations"])):
            if ChronicNeuralActivity["Annotations"][i]["Type"] == "PatientControllerEvent":
                ChronicNeuralActivity["Annotations"][i]["EventPSDs"] = []
                if len(ChronicNeuralActivity["Annotations"][i]["Recording"]) > 0:
                    for j in range(len(ChronicNeuralActivity["Annotations"][i]["Recording"])):
                        EventPSDs = BrainSenseEvent.extractBrainSenseEventRecording(ChronicNeuralActivity["Annotations"][i]["Recording"][j], DBSDevices)
                        ChronicNeuralActivity["Annotations"][i]["EventPSDs"].extend(EventPSDs)
            
                for j in range(len(ChronicNeuralActivity["Annotations"][i]["EventPSDs"])):
                    ChronicNeuralActivity["Annotations"][i]["EventPSDs"][j]["TherapyString"] = "Unknown"
                    for k in range(len(ChronicNeuralActivity["ChronicNeuralActivity"])):
                        if ChronicNeuralActivity["ChronicNeuralActivity"][k]["ChannelNames"][0].startswith(ChronicNeuralActivity["Annotations"][i]["EventPSDs"][j]["ChannelName"]):
                            if ChronicNeuralActivity["ChronicNeuralActivity"][k]["Device"]["Id"] == ChronicNeuralActivity["Annotations"][i]["EventPSDs"][j]["Device"]:
                                if ChronicNeuralActivity["Annotations"][i]["Date"] >= ChronicNeuralActivity["ChronicNeuralActivity"][k]["Time"][0] and ChronicNeuralActivity["Annotations"][i]["Date"] <= ChronicNeuralActivity["ChronicNeuralActivity"][k]["Time"][-1]:
                                    ChronicNeuralActivity["Annotations"][i]["EventPSDs"][j]["TherapyString"] = ChronicNeuralActivity["ChronicNeuralActivity"][k]["TherapyString"]
                                    break
                
                del ChronicNeuralActivity["Annotations"][i]["Recording"]
    return ChronicNeuralActivity
