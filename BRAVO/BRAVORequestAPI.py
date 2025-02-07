
import requests
import json
import os
import pickle as pkl
import datetime

class BRAVOPlatformRequest:
    def __init__(self, api_key, server="http://localhost"):
        self.__Server = server
        self.__request = requests.Session()
        self.__API_Key = api_key

    def query(self, url, data=None, files=None, content_type="application/json"):
        if not content_type:
            Headers = {"X-Secure-API-Key": self.__API_Key}
        else:
            Headers = {"Content-Type": content_type, "X-Secure-API-Key": self.__API_Key}

        if data:
            return self.__request.post(self.__Server + url,
                                       json.dumps(data) if content_type else data,
                                       headers=Headers)
        elif files:
            return self.__request.post(self.__Server + url,
                                       files=files,
                                       headers=Headers)
        else:
            return self.__request.post(self.__Server + url,
                                       headers=Headers)
    
    def GetUserInfo(self):
        response = self.query("/api/queryProfile")
        if response.status_code == 200:
            payload = response.json()
            self.User = payload
            return payload
        else:
            if response.status_code == 400:
                raise Exception(f"Network Error: {response.json()}")
            else:
                raise Exception(f"Network Error: {response.status_code}")
    
    def QueryParticipants(self):
        response = self.query("/api/queryParticipants")
        if response.status_code == 200:
            payload = response.json()
            return payload
        else:
            if response.status_code == 400:
                raise Exception(f"Network Error: {response.json()}")
            else:
                raise Exception(f"Network Error: {response.status_code}")
    
    def QueryTherapeuticEffectAnalysis(self, participant_uid, analysis_uid=None, config=None ):
        form = {"ParticipantId": participant_uid, "RequestType": "Overview"}
        if analysis_uid:
            form["RequestType"] = "RequestData"
            form["AnalysisId"] = analysis_uid
            form["ActiveChannels"] = "RequestAllChannel"
            
        if config:
            form["ProcessingConfiguration"] = config
            
        response = self.query("/api/queryTherapeuticEffectAnalysis", data=form)
        if response.status_code == 200:
            payload = response.json()
            return payload
        else:
            if response.status_code == 400:
                raise Exception(f"Network Error: {response.json()}")
            else:
                raise Exception(f"Network Error: {response.status_code}")
    
    def QueryTimeSeriesAnalysis(self, participant_uid, recording_uid=None, config=None ):
        form = {"ParticipantId": participant_uid, "RequestType": "Overview"}
        if recording_uid:
            form["RequestType"] = "RequestData"
            form["AnalysisId"] = recording_uid
            form["ActiveChannels"] = "RequestAllChannel"

        if config:
            form["ProcessingConfiguration"] = config
            
        response = self.query("/api/queryTimeseriesAnalysis", data=form)
        if response.status_code == 200:
            payload = response.json()
            return payload
        else:
            if response.status_code == 400:
                raise Exception(f"Network Error: {response.json()}")
            else:
                raise Exception(f"Network Error: {response.status_code}")
    
    def QueryRawTimeseries(self, participant_uid, recording_uid=None ):
        form = {"ParticipantId": participant_uid, "RequestType": "Overview"}
        if recording_uid:
            form["RequestType"] = "RawTimeseries"
            form["RecordingId"] = recording_uid
            
        response = self.query("/api/queryRawTimeseries", data=form)
        if response.status_code == 200:
            payload = response.json()
            return payload
        else:
            if response.status_code == 400:
                raise Exception(f"Network Error: {response.json()}")
            else:
                raise Exception(f"Network Error: {response.status_code}")
    
    def UploadMedtronicJSON(self, participant, file, metadata={"device_location": "", "infer_from_device": True}):
        form = {
            "File": file,
            "DataType": (None, "MedtronicJSON"), 
            "ParticipantId": (None, participant), 
            "Institute": (None, self.User["Institute"]), 
            "Metadata": (None, json.dumps(metadata))
        }

        response = self.query("/api/uploadData", files=form, content_type=None)
        if response.status_code == 200:
            return True
        elif response.status_code == 301:
            return True
        else:
            if response.status_code == 400:
                raise Exception(f"Network Error: {response.json()}")
            else:
                raise Exception(f"Network Error: {response.status_code}")
            