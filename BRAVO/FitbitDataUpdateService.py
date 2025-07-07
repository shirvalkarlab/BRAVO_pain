from BRAVO import wsgi
from Server import models
from modules.Fitbit import DataManager, DataQuery

import datetime
import time
import numpy as np

def createPlaceholderRecording(date):
    DateTimeObj = datetime.datetime.fromisoformat(DataQuery.fitbitDate(date) + "T00:00:00+00:00")
    Metadata = {
        "QueryTime": DataQuery.fitbitDate(date),
        "Timezone": DateTimeObj.tzname(),
        "DayLabel": "",
        "DailySummaryTimestamp": DateTimeObj.timestamp(),
        "Score": -1,
        "ScoreContributors": {},
        "NoData": True
    }
    Descriptor = {}

    Recording = dict()
    Recording["SamplingRate"] = -1
    Recording["ChannelNames"] = []
    Recording["Time"] = np.zeros(0)
    Recording["Data"] = np.zeros((0,1))
    Recording["Missing"] = np.zeros((0,1))
    Recording["StartTime"] = DateTimeObj.timestamp()
    Recording["Duration"] = 0
    Recording["Descriptor"] = Descriptor
    Recording["Metadata"] = Metadata
    return Recording

def hasData(listItems, date):
    for i in range(len(listItems)):
        if "Metadata" in listItems[i].keys():
            if listItems[i]["Metadata"]["QueryTime"] == date:
                return True
    return False

while True:
    AllDevices = models.FitbitDevice.find_all()
    for device in AllDevices:
        Participant = device.owner

        Data = DataManager.loadFitbitData(Participant)
        DataTypes = ["active-zone-minutes","distance","elevation","floors",
                    "minutesSedentary","minutesLightlyActive","minutesFairlyActive","minutesVeryActive",
                    "steps","heart-rate","heart-rate-variability","oxygen-saturation",
                    "skin-temperature","core-temperature","breathing-rate","sleep","cardioscore"]

        AcceptedDates = []
        for date in device.date_periods:
            AcceptedDates.extend(DataManager.calculateDateKey(date))

        DateToQuery = []
        for date in AcceptedDates:
            QueryTimestamp = datetime.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp()
            if QueryTimestamp > datetime.datetime.now().timestamp():
                continue
            DateToQuery.append(QueryTimestamp)
        DateToQuery = sorted(DateToQuery)

        try:
            for date in DateToQuery:
                for resource in ["activities/heart", "activities/active-zone-minutes", "activities/calories", "activities/distance", "activities/elevation", "activities/floors", "activities/steps", "hrv", "spo2"]:
                    if not (resource+"-intraday") in Data.keys():
                        Data[resource+"-intraday"] = []

                    if hasData(Data[resource+"-intraday"], DataQuery.fitbitDate(date)):
                        continue
                    
                    result = DataQuery.getIntradayActivityTimeseries(device, resource, date)
                    if resource == "activities/active-zone-minutes":
                        if len(result[resource.replace("/","-") + "-intraday"]) == 0:
                            Recording = createPlaceholderRecording(date)
                            Data[resource+"-intraday"].append(Recording)
                            continue

                        for n in range(len(result[resource.replace("/","-") + "-intraday"])):
                            DateTimeObj = datetime.datetime.fromisoformat(result[resource.replace("/","-") + "-intraday"][n]["dateTime"] + "T00:00:00+00:00")
                            Metadata = {
                                "QueryTime": DataQuery.fitbitDate(date),
                                "Timezone": DateTimeObj.tzname(),
                                "DayLabel": result[resource.replace("/","-") + "-intraday"][n]["dateTime"],
                                "DailySummaryTimestamp": DateTimeObj.timestamp(),
                                "Score": -1,
                                "ScoreContributors": {},
                            }

                            Descriptor = {}

                            Recording = dict()
                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = ["activeZoneMinutes"]
                            Recording["Time"] = np.zeros(len(result[resource.replace("/","-") + "-intraday"][n]["minutes"]))
                            Recording["Data"] = np.zeros((len(result[resource.replace("/","-") + "-intraday"][n]["minutes"]), len(Recording["ChannelNames"])))
                            for i in range(len(result[resource.replace("/","-") + "-intraday"][n]["minutes"])):
                                Recording["Time"][i] = datetime.datetime.fromisoformat(result[resource.replace("/","-") + "-intraday"][n]["minutes"][i]["minute"].replace(".000", "+00:00")).timestamp()
                                for j in range(len(Recording["ChannelNames"])):
                                    Recording["Data"][i,j] = result[resource.replace("/","-") + "-intraday"][n]["minutes"][i]["value"][Recording["ChannelNames"][j]]

                            Recording["Missing"] = np.zeros((len(result[resource.replace("/","-") + "-intraday"][n]["minutes"]), len(Recording["ChannelNames"])))
                            Recording["StartTime"] = DateTimeObj.timestamp()
                            if len(Recording["Time"]) > 0:
                                Recording["Duration"] = Recording["Time"][-1] - Recording["Time"][0]
                            else:
                                Recording["Duration"] = 0
                            Recording["Descriptor"] = Descriptor
                            Recording["Metadata"] = Metadata
                            Data[resource+"-intraday"].append(Recording)

                    elif resource.startswith("activities"):
                        DateTimeObj = datetime.datetime.fromisoformat(result[resource.replace("/","-")][0]["dateTime"] + "T00:00:00+00:00")
                        Metadata = {
                            "QueryTime": DataQuery.fitbitDate(date),
                            "Timezone": DateTimeObj.tzname(),
                            "DayLabel": result[resource.replace("/","-")][0]["dateTime"],
                            "DailySummaryTimestamp": DateTimeObj.timestamp(),
                            "Score": result[resource.replace("/","-")][0]["value"],
                            "ScoreContributors": {},
                        }

                        Descriptor = {}

                        Recording = dict()
                        Recording["SamplingRate"] = -1
                        Recording["ChannelNames"] = [resource]
                        Recording["Time"] = np.zeros(len(result[resource.replace("/","-") + "-intraday"]["dataset"]))
                        Recording["Data"] = np.zeros((len(result[resource.replace("/","-") + "-intraday"]["dataset"]), 1))
                        for i in range(len(result[resource.replace("/","-") + "-intraday"]["dataset"])):
                            Recording["Time"][i] = datetime.datetime.fromisoformat(Metadata["DayLabel"] + "T" + result[resource.replace("/","-") + "-intraday"]["dataset"][i]["time"] + "+00:00").timestamp()
                            Recording["Data"][i,0] = result[resource.replace("/","-") + "-intraday"]["dataset"][i]["value"]

                        Recording["Missing"] = np.zeros((len(result[resource.replace("/","-") + "-intraday"]["dataset"]), 2))
                        Recording["StartTime"] = DateTimeObj.timestamp()
                        if len(Recording["Time"]) > 0:
                            Recording["Duration"] = Recording["Time"][-1] - Recording["Time"][0]
                        else:
                            Recording["Duration"] = 0
                        Recording["Descriptor"] = Descriptor
                        Recording["Metadata"] = Metadata
                        Data[resource+"-intraday"].append(Recording)

                    elif resource == "hrv":
                        if len(result[resource]) == 0:
                            Recording = createPlaceholderRecording(date)
                            Data[resource+"-intraday"].append(Recording)
                            continue

                        for n in range(len(result[resource])):
                            DateTimeObj = datetime.datetime.fromisoformat(result[resource][n]["dateTime"] + "T00:00:00+00:00")
                            Metadata = {
                                "QueryTime": DataQuery.fitbitDate(date),
                                "Timezone": DateTimeObj.tzname(),
                                "DayLabel": result[resource][n]["dateTime"],
                                "DailySummaryTimestamp": DateTimeObj.timestamp(),
                                "Score": -1,
                                "ScoreContributors": {},
                            }

                            Descriptor = {}

                            Recording = dict()
                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = ["rmssd", "coverage", "hf", "lf"]
                            Recording["Time"] = np.zeros(len(result[resource][n]["minutes"]))
                            Recording["Data"] = np.zeros((len(result[resource][n]["minutes"]), 4))
                            for i in range(len(result[resource][n]["minutes"])):
                                Recording["Time"][i] = datetime.datetime.fromisoformat(result[resource][n]["minutes"][i]["minute"].replace(".000", "+00:00")).timestamp()
                                for j in range(len(Recording["ChannelNames"])):
                                    Recording["Data"][i,j] = result[resource][n]["minutes"][i]["value"][Recording["ChannelNames"][j]]

                            Recording["Missing"] = np.zeros((len(result[resource][n]["minutes"]), 4))
                            Recording["StartTime"] = DateTimeObj.timestamp()
                            if len(Recording["Time"]) > 0:
                                Recording["Duration"] = Recording["Time"][-1] - Recording["Time"][0]
                            else:
                                Recording["Duration"] = 0
                            Recording["Descriptor"] = Descriptor
                            Recording["Metadata"] = Metadata
                            Data[resource+"-intraday"].append(Recording)

                    elif resource == "spo2":
                        if len(result) == 0:
                            Recording = createPlaceholderRecording(date)
                            Data[resource+"-intraday"].append(Recording)
                            continue

                        for n in range(len(result)):
                            DateTimeObj = datetime.datetime.fromisoformat(result[n]["dateTime"] + "T00:00:00+00:00")
                            Metadata = {
                                "QueryTime": DataQuery.fitbitDate(date),
                                "Timezone": DateTimeObj.tzname(),
                                "DayLabel": result[n]["dateTime"],
                                "DailySummaryTimestamp": DateTimeObj.timestamp(),
                                "Score": -1,
                                "ScoreContributors": {},
                            }

                            Descriptor = {}

                            Recording = dict()
                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = ["spo2"]
                            Recording["Time"] = np.zeros(len(result[n]["minutes"]))
                            Recording["Data"] = np.zeros((len(result[n]["minutes"]), 1))
                            for i in range(len(result[n]["minutes"])):
                                Recording["Time"][i] = datetime.datetime.fromisoformat(result[n]["minutes"][i]["minute"].replace(".000", "+00:00")).timestamp()
                                Recording["Data"][i,0] = result[n]["minutes"][i]["value"]

                            Recording["Missing"] = np.zeros((len(result[n]["minutes"]), 1))
                            Recording["StartTime"] = DateTimeObj.timestamp()
                            if len(Recording["Time"]) > 0:
                                Recording["Duration"] = Recording["Time"][-1] - Recording["Time"][0]
                            else:
                                Recording["Duration"] = 0
                            Recording["Descriptor"] = Descriptor
                            Recording["Metadata"] = Metadata
                            Data[resource+"-intraday"].append(Recording)

                for key in DataQuery.FitbitDataTypes.keys():
                    if not key in Data.keys():
                        Data[key] = []

                    if hasData(Data[key], DataQuery.fitbitDate(date)):
                        continue

                    result = DataQuery.queryFitbitData(device, key, int(date), int(date))
                    if len(result) == 0:
                        Recording = createPlaceholderRecording(date)
                        Data[key].append(Recording)
                        continue
                    
                    if key in ["active-zone-minutes", "heart-rate-variability", "oxygen-saturation", "skin-temperature", "core-temperature", "breathing-rate"]:
                        for n in range(len(result)):
                            DateTimeObj = datetime.datetime.fromisoformat(result[n]["dateTime"] + "T00:00:00+00:00")
                            Metadata = {
                                "QueryTime": DataQuery.fitbitDate(date),
                                "Timezone": DateTimeObj.tzname(),
                                "DayLabel": result[n]["dateTime"],
                                "DailySummaryTimestamp": DateTimeObj.timestamp(),
                                "Score": -1,
                                "ScoreContributors": {},
                            }

                            Descriptor = {}

                            Recording = dict()
                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = [a for a in result[n]["value"].keys()]
                            Recording["Time"] = np.zeros(1)
                            Recording["Data"] = np.zeros((1, len(Recording["ChannelNames"])))
                            
                            Recording["Time"][0] = DateTimeObj.timestamp()
                            for i in range(len(Recording["ChannelNames"])):
                                Recording["Data"][0,i] = result[n]["value"][Recording["ChannelNames"][i]]

                            Recording["Missing"] = np.zeros((1, len(Recording["ChannelNames"])))
                            Recording["StartTime"] = DateTimeObj.timestamp()
                            Recording["Duration"] = 0
                            Recording["Descriptor"] = Descriptor
                            Recording["Metadata"] = Metadata
                            Data[key].append(Recording)
                    
                    elif key in ["heart-rate"]:
                        for n in range(len(result)):
                            DateTimeObj = datetime.datetime.fromisoformat(result[n]["dateTime"] + "T00:00:00+00:00")
                            Metadata = {
                                "QueryTime": DataQuery.fitbitDate(date),
                                "Timezone": DateTimeObj.tzname(),
                                "DayLabel": result[n]["dateTime"],
                                "DailySummaryTimestamp": DateTimeObj.timestamp(),
                                "Score": -1,
                                "ScoreContributors": {},
                            }

                            Descriptor = {}

                            Recording = dict()
                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = [zone["name"] for zone in result[n]["value"]["heartRateZones"]]
                            Recording["Time"] = np.zeros(1)
                            Recording["Data"] = np.zeros((1, len(Recording["ChannelNames"])))
                            
                            Recording["Time"][0] = DateTimeObj.timestamp()
                            for i in range(len(Recording["ChannelNames"])):
                                for j in range(len(result[n]["value"]["heartRateZones"])):
                                    if Recording["ChannelNames"][i] == result[n]["value"]["heartRateZones"][j]["name"]:
                                        Recording["Data"][0,i] = result[n]["value"]["heartRateZones"][j]["minutes"]
                                        break
                            Recording["Missing"] = np.zeros((1, len(Recording["ChannelNames"])))
                            Recording["StartTime"] = DateTimeObj.timestamp()
                            Recording["Duration"] = 0
                            Recording["Descriptor"] = Descriptor
                            Recording["Metadata"] = Metadata
                            Data[key].append(Recording)

                    elif key in ["sleep"]:
                        for n in range(len(result)):
                            DateTimeObj = datetime.datetime.fromisoformat(result[0]["startTime"].replace(".000", "+00:00"))
                            Metadata = {
                                "QueryTime": DataQuery.fitbitDate(date),
                                "Timezone": DateTimeObj.tzname(),
                                "DayLabel": result[0]["dateOfSleep"],
                                "DailySummaryTimestamp": DateTimeObj.timestamp(),
                                "Score": -1,
                                "ScoreContributors": {},
                            }

                            Descriptor = {
                                "AwakeCount": result[n]["awakeCount"],
                                "AwakeDuration": result[n]["awakeDuration"],
                                "AwakeningsCount": result[n]["awakeningsCount"],
                                "Duration": result[n]["duration"],
                                "Efficiency": result[n]["efficiency"],
                                "MinutesAfterWakeup": result[n]["minutesAfterWakeup"],
                                "MinutesAsleep": result[n]["minutesAsleep"],
                                "MinutesAwake": result[n]["minutesAwake"],
                                "MinutesToFallAsleep": result[n]["minutesToFallAsleep"],
                                "RestlessCount": result[n]["restlessCount"],
                                "RestlessDuration": result[n]["restlessDuration"],
                                "TimeInBed": result[n]["timeInBed"],
                            }

                            Recording = dict()
                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = ["SleepStage"]
                            Recording["Time"] = np.zeros(len(result[n]["minuteData"]))
                            Recording["Data"] = np.zeros((len(result[n]["minuteData"]), len(Recording["ChannelNames"])))
                            
                            for i in range(len(result[n]["minuteData"])):
                                DatePart = result[n]["startTime"].split("T")[0]
                                Recording["Time"][i] = datetime.datetime.fromisoformat(DatePart + "T" + result[n]["minuteData"][i]["dateTime"] + "+00:00").timestamp()
                                if Recording["Time"][i] < Recording["Time"][i-1]:
                                    Recording["Time"][i] += 3600*24
                                Recording["Data"][i,0] = float(result[n]["minuteData"][i]["value"])

                            Recording["Missing"] = np.zeros((len(result[n]["minuteData"]), len(Recording["ChannelNames"])))
                            Recording["StartTime"] = DateTimeObj.timestamp()
                            Recording["Duration"] = 0
                            Recording["Descriptor"] = Descriptor
                            Recording["Metadata"] = Metadata
                            Data[key].append(Recording)

                    elif key in ["cardioscore"]:
                        for n in range(len(result)):
                            DateTimeObj = datetime.datetime.fromisoformat(result[n]["dateTime"] + "T00:00:00+00:00")
                            Metadata = {
                                "QueryTime": DataQuery.fitbitDate(date),
                                "Timezone": DateTimeObj.tzname(),
                                "DayLabel": result[n]["dateTime"],
                                "DailySummaryTimestamp": DateTimeObj.timestamp(),
                                "Score": -1,
                                "ScoreContributors": {},
                            }

                            Descriptor = {}

                            Recording = dict()
                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = ["vo2MaxRange0", "vo2MaxRange1"]
                            Recording["Time"] = np.zeros(1)
                            Recording["Data"] = np.zeros((1, len(Recording["ChannelNames"])))
                            
                            Recording["Time"][0] = DateTimeObj.timestamp()
                            Recording["Data"][0,0] = float(result[n]["value"]["vo2Max"].split("-")[0])
                            Recording["Data"][0,1] = float(result[n]["value"]["vo2Max"].split("-")[1])

                            Recording["Missing"] = np.zeros((1, len(Recording["ChannelNames"])))
                            Recording["StartTime"] = DateTimeObj.timestamp()
                            Recording["Duration"] = 0
                            Recording["Descriptor"] = Descriptor
                            Recording["Metadata"] = Metadata
                            Data[key].append(Recording)

                    elif key in ["distance", "elevation", "floors", "minutesSedentary", "minutesLightlyActive", "minutesFairlyActive", "minutesVeryActive", "steps"]:
                        for n in range(len(result)):
                            DateTimeObj = datetime.datetime.fromisoformat(result[n]["dateTime"] + "T00:00:00+00:00")
                            Metadata = {
                                "QueryTime": DataQuery.fitbitDate(date),
                                "Timezone": DateTimeObj.tzname(),
                                "DayLabel": result[n]["dateTime"],
                                "DailySummaryTimestamp": DateTimeObj.timestamp(),
                                "Score": -1,
                                "ScoreContributors": {},
                            }

                            Descriptor = {}

                            Recording = dict()
                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = [key]
                            Recording["Time"] = np.zeros(1)
                            Recording["Data"] = np.zeros((1, len(Recording["ChannelNames"])))
                            
                            Recording["Time"][0] = DateTimeObj.timestamp()
                            Recording["Data"][0,0] = float(result[n]["value"])
                            Recording["Missing"] = np.zeros((1, len(Recording["ChannelNames"])))
                            Recording["StartTime"] = DateTimeObj.timestamp()
                            Recording["Duration"] = 0
                            Recording["Descriptor"] = Descriptor
                            Recording["Metadata"] = Metadata
                            Data[key].append(Recording)
                    
        except Exception as e:
            print(str(e))

        DataManager.saveFitbitData(Participant, Data)
    
    time.sleep(300)