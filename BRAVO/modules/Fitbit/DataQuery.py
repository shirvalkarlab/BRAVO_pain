import os
import base64
import requests
import traceback
import datetime

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
FITBIT_CLIENT_ID = os.environ["FIBIT_CLIENT_ID"]
FITBIT_CLIENT_SECRET = os.environ["FIBIT_CLIENT_SECRET"]

FitbitDataTypes = {
    "active-zone-minutes": ["activities/active-zone-minutes", "activities-active-zone-minutes"], 
    "distance": ["activities/distance", "activities-distance"], 
    "elevation": ["activities/elevation", "activities-elevation"], 
    "floors": ["activities/floors", "activities-floors"],  
    "minutesSedentary": ["activities/minutesSedentary", "activities-minutesSedentary"],  
    "minutesLightlyActive": ["activities/minutesLightlyActive", "activities-minutesLightlyActive"],  
    "minutesFairlyActive": ["activities/minutesFairlyActive", "activities-minutesFairlyActive"], 
    "minutesVeryActive": ["activities/minutesVeryActive", "activities-minutesVeryActive"], 
    "steps": ["activities/steps", "activities-steps"], 
    "heart-rate": ["activities/heart", "activities-heart"], 
    "heart-rate-variability": ["hrv", "hrv"], 
    "oxygen-saturation": ["spo2", ""], 
    "skin-temperature": ["temp/skin", "tempSkin"], 
    "core-temperature": ["temp/core", "tempCore"], 
    "breathing-rate": ["br", "br"],
    "sleep": ["sleep", "sleep"],
    "cardioscore": ["cardioscore", "cardioScore"]
}

def fitbitDate(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

def retrieveToken(code, verifier):
    try:
        response = requests.post("https://api.fitbit.com/oauth2/token", headers={
            "Authorization": "Basic " + base64.b64encode((FITBIT_CLIENT_ID+":"+FITBIT_CLIENT_SECRET).encode("utf-8")).decode(), 
            "Content-Type": "application/x-www-form-urlencoded"
        }, data={
            "client_id": FITBIT_CLIENT_ID,
            "grant_type": "authorization_code",
            "redirect_uri": "https://bravo-api.jcagle.solutions/oath/fitbit_redirect",
            "code": code,
            "code_verifier": verifier
        })
        data = response.json()
        if "access_token" in data.keys() and "refresh_token" in data.keys():
            return data 

    except Exception as e:
        print(traceback.format_exc())

    return None

def refreshToken(token):
    try:
        response = requests.post("https://api.fitbit.com/oauth2/token", headers={
            "Authorization": "Basic " + base64.b64encode((FITBIT_CLIENT_ID+":"+FITBIT_CLIENT_SECRET).encode("utf-8")).decode(), 
            "Content-Type": "application/x-www-form-urlencoded"
        }, data={
            "client_id": FITBIT_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"]
        })
        data = response.json()
        if "access_token" in data.keys() and "refresh_token" in data.keys():
            return data 

    except Exception as e:
        print(traceback.format_exc())

TimeseriesMaxQueryTime = {
    "activities/active-zone-minutes": 94608000, 
    "activities/distance": 94608000, 
    "activities/elevation": 94608000, 
    "activities/floors": 94608000,  
    "activities/minutesSedentary": 94608000,  
    "activities/minutesLightlyActive": 94608000,  
    "activities/minutesFairlyActive": 94608000, 
    "activities/minutesVeryActive": 94608000, 
    "activities/steps": 94608000, 
    "activities/heart": 31536000,
    "hrv": 2592000,
    "br": 2592000,
    "cardioscore": 2592000,
    "spo2": 94608000,
    "sleep": 8640000,
    "temp/skin": 2592000,
    "temp/core": 2592000
}

def getGeneralTimeseries(device, type="br", start_date=0, end_date=0):
    if end_date == 0:
        end_date = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
    
    if start_date == 0:
        start_date = end_date - TimeseriesMaxQueryTime[type]

    token = device.auth
    url = "https://api.fitbit.com/1/user/-/" + type + "/date/" + fitbitDate(start_date) + "/" + fitbitDate(end_date) + ".json"
    print(url)
    response = requests.get(url, headers={
        "Authorization": "Bearer " + token["access_token"], 
        "Content-Type": "application/json",
    })

    if response.status_code == 200:
        data = response.json()
        return data
    
    elif response.status_code == 401:
        print("Refresh Auth Token")
        newToken = refreshToken(device.auth)
        if not newToken:
            raise Exception("Authorization Expired. Refreshing Failed. Please reauthorize.")
        device.auth = newToken
        device.save()
        return getGeneralTimeseries(device, type, start_date, end_date)

    elif response.status_code == 429:
        raise Exception("Request Rate Limit reached for Fitbit APIs.")
    
    else:
        data = response.json()
        if "details" in data.keys():
            raise Exception(data["details"])
        
    raise Exception("Unknown Fitbit API Error: " + str(response.status_code))

def queryFitbitData(device, type, start_date, end_date):
    Data = []
    if end_date - start_date >= TimeseriesMaxQueryTime[FitbitDataTypes[type][0]]:
        for new_start in range(start_date, end_date, TimeseriesMaxQueryTime[FitbitDataTypes[type][0]]):
            if new_start + TimeseriesMaxQueryTime[FitbitDataTypes[type][0]] > end_date:
                new_end = end_date
            else:
                new_end = new_start + TimeseriesMaxQueryTime[FitbitDataTypes[type][0]]

            data = getGeneralTimeseries(device, FitbitDataTypes[type][0], new_start, new_end)
            if FitbitDataTypes[type][1] == "":
                Data.extend(data)
            else:
                Data.extend(data[FitbitDataTypes[type][1]])
        
        return Data

    data = getGeneralTimeseries(device, FitbitDataTypes[type][0], start_date, end_date)
    if FitbitDataTypes[type][1] == "":
        Data = data
    else:
        Data = data[FitbitDataTypes[type][1]]
    
    return Data

def queryAllData(device, start_date, end_date):
    Data = {}
    for key in FitbitDataTypes.keys():
        print(key)
        Data[key] = queryFitbitData(device, key, start_date, end_date)
    return Data