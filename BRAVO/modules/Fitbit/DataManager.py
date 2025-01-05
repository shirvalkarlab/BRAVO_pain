import os
import datetime
import numpy as np

from Server import models
from modules import Database
from modules.Fitbit import DataQuery

DATABASE_PATH = os.environ.get('DATASERVER_PATH')

def loadFitbitData(Participant):
    Data = {}
    source = models.SourceFile.find(owner=Participant, type="FitbitWebAPISource")
    if source:
        Data = Database.loadSourceFile(source.pointer, source.hashed)
    return Data

def saveFitbitData(Participant, data):
    if not models.SourceFile.include(type="FitbitWebAPISource", owner=Participant):
        source = models.SourceFile(name="FitbitWebAPISource", type="FitbitWebAPISource", owner=Participant)
        source.save()
        source.pointer = DATABASE_PATH + "recordings" + os.path.sep + Participant.uid + os.path.sep + source.uid + ".bdat"
    else:
        source = models.SourceFile.find(owner=Participant, type="FitbitWebAPISource")

    source.hashed = Database.saveSourceFile(data, source.pointer)
    source.save()

def calculateDateKey(period):
    keys = []
    for day in np.arange(period[0], period[1]+1, 3600*24):
        keys.append(DataQuery.fitbitDate(day))
    return keys

def formatFitbitData(data, type):
    Data = {"Time": [], "Data": [], "DateLabel": []}
    if not type in data.keys():
        return Data

    if type == "active-zone-minutes":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Value = {}
            for key in data[type][i]["value"].keys():
                Value[key] = float(data[type][i]["value"][key])
            Data["Data"].append(Value)
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "distance":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "Distance": float(data[type][i]["value"])
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "elevation":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "Elevation": float(data[type][i]["value"])
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "floors":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "Floor": float(data[type][i]["value"])
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "minutesSedentary":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "MinutesSedentary": float(data[type][i]["value"])
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "minutesLightlyActive":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "MinutesLightlyActive": float(data[type][i]["value"])
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "minutesFairlyActive":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "MinutesFairlyActive": float(data[type][i]["value"])
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "minutesVeryActive":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "MinutesVeryActive": float(data[type][i]["value"])
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "steps":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "Steps": float(data[type][i]["value"])
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "heart-rate":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Value = {}
            for j in data[type][i]["value"]["heartRateZones"]:
                Value[j["name"]] = [float(j["min"]), (float(j["min"])+float(j["max"]))/2 , float(j["max"])]
            Data["Data"].append(Value)
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "heart-rate-variability":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "DailyHeartRateVariability": float(data[type][i]["value"]["dailyRmssd"]),
                "DeepHeartRateVariability": float(data[type][i]["value"]["deepRmssd"]),
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "oxygen-saturation":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "OxygenSaturation": [float(data[type][i]["value"]["min"]), float(data[type][i]["value"]["avg"]) , float(data[type][i]["value"]["max"])]
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "skin-temperature":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Value = {}
            for j in data[type][i]["value"].keys():
                Value[j] = float(data[type][i]["value"][j])
            Value["SkinTemperatureLogType"] = data[type][i]["logType"]
            Data["Data"].append(Value)
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "core-temperature":
        # TODO: Not available on the watches we purchased. 
        pass
    
    elif type == "breathing-rate":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "BreathingRate": float(data[type][i]["value"]["breathingRate"]),
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    elif type == "sleep":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateOfSleep"] + "T00:00:00+00:00").timestamp())
            Data["Data"].append({
                "SleepDuration": float(data[type][i]["duration"]),
                "SleepTotalSleepMinutes": float(data[type][i]["minutesAsleep"]),
                "SleepTotalTimeInBed": float(data[type][i]["timeInBed"]),
                "SleepStartTime": datetime.datetime.fromisoformat(data[type][i]["startTime"]),
                "SleepEndTime": datetime.datetime.fromisoformat(data[type][i]["endTime"]),
                "SleepDuration": float(data[type][i]["duration"]),
            })
            Data["Unstructured"] = data[type][i]
            Data["DateLabel"].append(data[type][i]["dateOfSleep"])
    
    elif type == "cardioscore":
        for i in range(len(data[type])):
            Data["Time"].append(datetime.datetime.fromisoformat(data[type][i]["dateTime"] + "T00:00:00+00:00"))
            Vo2Max = data[type][i]["value"]["vo2Max"].split("-")
            Data["Data"].append({
                "MaximalOxygenConsumption": [float(Vo2Max[0]), (float(Vo2Max[0])+float(Vo2Max[1]))/2 , float(Vo2Max[1])],
            })
            Data["DateLabel"].append(data[type][i]["dateTime"])

    else:
        print(type)

    return Data

def filterDataByDateKeys(data, datekey):
    FilteredData = {"Time": [], "Data": [], "DateLabel": []}
    for i in range(len(data["DateLabel"])):
        if data["DateLabel"][i] in datekey:
            FilteredData["Time"].append(data["Time"][i])
            FilteredData["Data"].append(data["Data"][i])
            FilteredData["DateLabel"].append(data["DateLabel"][i])
    return FilteredData

def refreshFitbitData(device):
    DataTypes = ["active-zone-minutes","distance","elevation","floors","minutesSedentary","minutesLightlyActive","minutesFairlyActive","minutesVeryActive",
        "steps","heart-rate","heart-rate-variability","oxygen-saturation","skin-temperature","core-temperature","breathing-rate","sleep","cardioscore"]

    AcceptedDates = []
    for date in device.date_periods:
        AcceptedDates.extend(calculateDateKey(date))

    DateToQuery = []
    for date in AcceptedDates:
        DateToQuery.append(datetime.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())

    DateToQuery = sorted(DateToQuery)
    DateBreaks = np.where(np.diff(sorted(DateToQuery)) > 3600*24)[0]
    if len(DateBreaks) == 0:
        Data = DataQuery.queryAllData(device, int(DateToQuery[0]), int(DateToQuery[-1]))
    
    for key in DataTypes:
        Data[key] = formatFitbitData(Data, key)
    return Data

def calculateDataDifference(device, data):
    DataTypes = ["active-zone-minutes","distance","elevation","floors","minutesSedentary","minutesLightlyActive","minutesFairlyActive","minutesVeryActive",
        "steps","heart-rate","heart-rate-variability","oxygen-saturation","skin-temperature","core-temperature","breathing-rate","sleep","cardioscore"]

    AcceptedDates = []
    for date in device.date_periods:
        AcceptedDates.extend(calculateDateKey(date))

    if len(data.keys()) == 0:
        DateToQuery = []
        for date in AcceptedDates:
            DateToQuery.append(datetime.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())

        DateToQuery = sorted(DateToQuery)
        DateBreaks = np.where(np.diff(sorted(DateToQuery)) > 3600*24)[0]
        if len(DateBreaks) == 0:
            Data = DataQuery.queryAllData(device, int(DateToQuery[0]), int(DateToQuery[-1]))
        
        for key in DataTypes:
            Data[key] = formatFitbitData(data, key)
        return Data

    else:
        ExistingData = {}
        for key in DataTypes:
            ExistingData[key] = formatFitbitData(data, key)
            ExistingData[key] = filterDataByDateKeys(ExistingData[key], AcceptedDates)

            DateToQuery = []
            for date in AcceptedDates:
                if not date in ExistingData[key]["DateLabel"]:
                    DateToQuery.append(datetime.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())

            DateToQuery = sorted(DateToQuery)
            DateBreaks = np.where(np.diff(sorted(DateToQuery)) > 3600*24)[0]

            if len(DateBreaks) == 0:
                pass
            else:
                pass 
            