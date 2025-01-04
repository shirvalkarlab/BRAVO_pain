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
    if type == "steps":
        for i in range(len(data)):
            Data["Time"].append(datetime.datetime.fromisoformat(data[i]["dateTime"] + "T00:00:00+00:00"))
            Data["Data"].append({
                "Steps": int(data[i]["value"])
            })
            Data["DateLabel"].append(data[i]["dateTime"])
    return Data

def filterDataByDateKeys(data, datekey):
    FilteredData = {"Time": [], "Data": [], "DateLabel": []}
    for i in range(len(data["DateLabel"])):
        if data["DateLabel"][i] in datekey:
            FilteredData["Time"].append(data["Time"][i])
            FilteredData["Data"].append(data["Data"][i])
            FilteredData["DateLabel"].append(data["DateLabel"][i])
    return FilteredData

def calculateDataDifference(device, data):
    DataTypes = ["active-zone-minutes","distance","elevation","floors","minutesSedentary","minutesLightlyActive","minutesFairlyActive","minutesVeryActive",
        "steps","heart-rate","heart-rate-variability","oxygen-saturation","skin-temperature","core-temperature","breathing-rate","sleep","cardioscore"]

    AcceptedDates = []
    for date in device.date_periods:
        AcceptedDates.extend(calculateDateKey(date))

    ExistingData = {}
    for key in DataTypes:
        ExistingData[key] = formatFitbitData(data[key], key)
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
        
    for date in device.date_periods:
        DateKeys = calculateDateKey(date)
        for key in DataTypes:
            if key == "steps":
                ExistingData = formatFitbitData(data[key], key)
                if len(data[key]) == 0:
                    data[key] = DataQuery.queryFitbitData(device, key, start_date=date[0], end_date=date[1])
                else:
                    print(data[key][0])