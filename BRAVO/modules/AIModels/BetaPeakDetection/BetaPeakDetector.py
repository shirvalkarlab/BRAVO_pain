from pathlib import Path
import numpy as np
from scipy import signal, stats
from modules import Database, DataAnalysis
import pickle

with open(Path(__file__).parent / "BetaPeakDetector.pkl", "rb") as f:
    BetaPeakDetector = pickle.load(f)

with open(Path(__file__).parent / "BetaPeakIdentifier_Classification.pkl", "rb") as f:
    BetaPeakIdentifier_Classifier = pickle.load(f)

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

def BetaPeakDetector(data):
    # data require dict({"Data": list, "SamplingRate": float})
    if type(data["Data"]) is not list:
        raise ValueError("Data must be a list of time series data.")
    data["Data"] = np.array(data["Data"])
    data["Missing"] = np.zeros(data["Data"].shape)
    data["ChannelNames"] = []

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

    PSD = MeanPSD[Data["Spectrum"][0]["Frequency"] < 100]
    PSDFrequency = Data["Spectrum"][0]["Frequency"][Data["Spectrum"][0]["Frequency"] < 100]
    BetaBand = (PSDFrequency >= 11) & (PSDFrequency <= 30)
    NormBeta = np.log10(PSD[BetaBand]) / np.sum(np.log10(PSD[BetaBand]))
    MeanPSDPower = np.mean(np.log10(PSD))
    Feature = np.concatenate((NormBeta, [MeanPSDPower]))
    
    HasBetaPeak = BetaPeakDetector.predict_proba([Feature])[0][1]
    Result = {"PredictedCenterFrequency": []}
    Result["BetaPresence"] = HasBetaPeak
    
    TestingCenter = np.arange(10, 90, 0.5)
    Label = []
    for j in TestingCenter:
        index = PSDFrequency.tolist().index(j)
        Feature = np.zeros(20)
        Feature[:20] = PSD[index-10:index+10]
        
        Y_pred = BetaPeakIdentifier_Classifier.predict_proba([Feature])[0][1]
        Label.append(Y_pred)
        Result["PredictedCenterFrequency"].append({
            "Frequency": j,
            "Probability": Y_pred,
        })
    
    return Result