from Server import models

import os, sys
from pathlib import Path
import datetime, pytz
import pickle
import numpy as np
from scipy import stats, signal
import subprocess

from modules import DataAnalysis, Database, DataCurator
from modules.HelperFunctions import utc_offset_to_timezone

DATABASE_PATH = os.environ.get('DATASERVER_PATH')

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

def ExtractFTGPeak(Frequency, Power):
    FrequencySelection = ((Frequency > 55) & (Frequency < 95))
    GammaBand = Power[FrequencySelection,:]
    GammaFluctuation = signal.detrend(np.mean(GammaBand, axis=1), type="linear")
    GammaCI = np.zeros((GammaBand.shape[0],2))
    for i in range(GammaBand.shape[0]):
        GammaCI[i,:] = stats.t.interval(0.95, len(GammaFluctuation)-1, loc=GammaFluctuation[i], scale=np.std(GammaFluctuation))
    
    MaxGammaIndex = np.argmax(GammaCI[:,1])
    GammaParameters = {"MaxGamma": GammaCI[MaxGammaIndex,:], "GammaFrequency": Frequency[FrequencySelection][MaxGammaIndex], "Significant": False}

    GammaDetection = np.array(GammaCI[MaxGammaIndex,0] > GammaFluctuation, dtype=float)
    StartPeak = np.where(np.diff(GammaDetection) == -1)[0]
    EndPeak = np.where(np.diff(GammaDetection) == 1)[0]
    if len(StartPeak) == 1 and len(EndPeak) == 1 and GammaCI[MaxGammaIndex,1] > 2:
        GammaParameters["PeakStart"] = Frequency[FrequencySelection][StartPeak[0]]
        GammaParameters["PeakEnd"] = Frequency[FrequencySelection][EndPeak[0]]
        GammaParameters["Significant"] = True
    return GammaParameters

def FTGPeakDetector(data):
    # data require dict({"Data": list, "SamplingRate": float})
    if type(data["Data"]) is not list:
        raise ValueError("Data must be a list of time series data.")
    data["Data"] = np.array(data["Data"])
    data["Missing"] = np.zeros(data["Data"].shape)
    data["ChannelNames"] = ["Input Data"]

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

    Data = DataAnalysis.processTimeDomainStreaming(None, data, userConfig)
    MeanPSD = np.nanmedian(Data["Spectrum"][0]["Power"],axis=1)
    StdPSD = np.nanstd(Data["Spectrum"][0]["Power"],axis=1)
    if np.any(StdPSD == 0):
        return None
    
    MeanPSD = MovingAverageFilter(MeanPSD, 5)
    AperiodicComponent = ExtractAperiodicComponents(Data["Spectrum"][0]["Frequency"], MeanPSD)
    NormalizedSpectrum = Data["Spectrum"][0]["Power"] / AperiodicComponent.reshape(-1,1)
    GammaParameters = ExtractFTGPeak(Data["Spectrum"][0]["Frequency"], NormalizedSpectrum)

    collection = {
        "PowerSpectrum": MeanPSD,
        "StdPower": StdPSD,
        "Frequency": Data["Spectrum"][0]["Frequency"],
        "AperiodicComponent": AperiodicComponent,
        "FTGStats": GammaParameters
    }
    return collection
    