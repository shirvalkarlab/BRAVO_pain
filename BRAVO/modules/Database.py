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
Database Interaction 
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os, sys, pathlib
import pickle, blosc
import hashlib, hmac
import shutil
from filelock import Timeout, FileLock

from Server import models
from modules.MedtronicPercept import BrainSenseStream

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')

def retrieveProcessingSettings(config=dict()):
    options = {
        "TimeSeriesRecording": {
            "StandardFilter": {
                "name": "Standard Bandpass Filter",
                "description": "",
                "options": ["No Filter","Butterworth 1-100Hz"],
                "value": "Butterworth 1-100Hz"
            },
            "NotchFilter": {
                "name": "Powerline Noise Notch Filter",
                "description": "",
                "options": ["No Filter","Notch 55-65Hz","Notch 45-55Hz"],
                "value": "No Filter"
            },
            "WienerFilter": {
                "name": "Wiener Filter for Artifact Removals",
                "description": "",
                "options": ["No Filter","Use Wiener Filter"],
                "value": "No Filter"
            },
            "CardiacFilter": {
                "name": "Cardiac Filter for EKG Removals",
                "description": "",
                "options": ["No Filter","Use Adaptive Template Matching"],
                "value": "No Filter"
            },
            "SpectrogramMethod": {
                "name": "Time-Frequency Analysis Algorithm",
                "description": "",
                "options": ["Welch's Periodogram","Short-time Fourier Transform","Wavelet","Autoregressive Model (Yule-Walker)"],
                "value": "Welch's Periodogram"
            },
            "BaselineCorrection": {
                "name": "Baseline Correlation for Time-Frequency Analysis",
                "description": "",
                "options": ["No Correction", "Use Baseline Correction"],
                "value": "No Correction"
            },
            "Normalization": {
                "name": "Normalization for Time-Frequency Analysis",
                "description": "",
                "options": ["No Normalization", "1/f PSD Trend Removal"],
                "value": "No Normalization"
            },
        },
        "PowerSpectralDensity": {
            "PSDMethod": {
                "name": "Power Spectrum Estimation Algorithm",
                "description": "",
                "options": ["Estimated Medtronic PSD","Welch's Periodogram","Autoregressive Model (Yule-Walker)","Short-time Fourier Transform"],
                "value": "Welch's Periodogram"
            },
            "MonopolarEstimation": {
                "name": "Monopolar Estimation Algorithm",
                "description": "",
                "options": ["No Estimation", "DETEC Algorithm (Strelow et. al., 2022)"],
                "value": "No Estimation"
            },
        }
    }

    if not "ProcessingConfiguration" in config.keys():
        return options, True
    
    if not type(config["ProcessingConfiguration"]) == dict:
        return options, True

    for key in config["ProcessingConfiguration"].keys():
        if type(config["ProcessingConfiguration"][key]) == dict:
            for subkey in config["ProcessingConfiguration"][key].keys():
                if type(config["ProcessingConfiguration"][key][subkey]) == dict and subkey in options[key].keys():
                    if config["ProcessingConfiguration"][key][subkey]["name"] == options[key][subkey]["name"] and config["ProcessingConfiguration"][key][subkey]["description"] == options[key][subkey]["description"] and config["ProcessingConfiguration"][key][subkey]["options"] == options[key][subkey]["options"]:
                        options[key][subkey]["value"] = config["ProcessingConfiguration"][key][subkey]["value"]
    
    return options, not (options==config["ProcessingConfiguration"])

def checkConfiguration(metadata, config):
    if not type(metadata) == dict:
        return False 
    
    for key in config:
        if not key in metadata.keys():
            return False
        if not metadata[key] == config[key]:
            return False
    
    return True

def checkAccessPermission(user, participant_uid):
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return False 
    
    if Participant.institute.has_permission(user):
        return True
    
    return models.Study.include(members=user, participant__pk=participant_uid)

def checkManagePermission(user, participant_uid):
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return False
    return Participant.institute.has_permission(user)

def extractParticipantInformation(participant_uid):
    Participant = models.Participant.find(uid=participant_uid)
    ParticipantInfo = Participant.get_info()
    ParticipantInfo["DBSDevices"] = [i.get_info() for i in models.DBSDevice.find_all(owner=Participant)]
    return ParticipantInfo

def deleteSourceFile(pointer):
    if not pointer.startswith(DATABASE_PATH) or ".." in pointer:
        raise Exception("Malicious Attempt at Accessing Other Data in the Computer.")
    
    lock = FileLock(pointer + ".lock")
    try:
        with lock.acquire(timeout=30):
            pathlib.Path.unlink(pathlib.Path(pointer))
        return True
    except Timeout:
        print("Lockfile Not Acquired before Timeout")
        return False

def saveSourceFile(datastruct, pointer, bytes=False):
    if not pointer.startswith(DATABASE_PATH) or ".." in pointer:
        raise Exception("Malicious Attempt at Accessing Other Data in the Computer.")
    
    if not bytes:
        pData = pickle.dumps(datastruct, protocol=pickle.HIGHEST_PROTOCOL)
    else:
        pData = datastruct

    lock = FileLock(pointer + ".lock")
    try:
        with lock.acquire(timeout=30):
            with open(pointer + ".tmp", "wb+") as file:
                rawBytes = blosc.compress(pData)
                hashed = hmac.new(HASH_KEY.encode("utf8"), rawBytes, hashlib.sha256).hexdigest()
                file.write(rawBytes)
            shutil.move(pointer + ".tmp", pointer)
            return hashed
    except Timeout:
        print("Lockfile Not Acquired before Timeout")
        return False

def loadSourceFile(pointer, verifiedHash, bytes=False):
    if not pointer.startswith(DATABASE_PATH) or ".." in pointer:
        raise Exception("Malicious Attempt at Accessing Other Data in the Computer.")
    
    with open(pointer, "rb") as file:
        rawBytes = file.read()
    hashed = hmac.new(HASH_KEY.encode("utf8"), rawBytes, hashlib.sha256).hexdigest()
    if not hashed == verifiedHash:
        raise Exception(f"DANGER: Unauthorized Modification of Data {pointer}, risk of Pickle Arbitrary Code Execution.")

    decompressed = blosc.decompress(rawBytes)

    # If Request Raw Byte Data
    if bytes:
        return decompressed
    
    # Else just pickle load it
    datastruct = pickle.loads(decompressed)
    return datastruct

def getCachedResult(url, participant_uid, config):
    models.SourceFile.purge(type="CachedResult", date__lt=models.current_time() - 3600)
    metadata = {**config, **{"URL": url, "Participant": participant_uid}}
    result = models.SourceFile.find(type="CachedResult", metadata=metadata)
    if result:
        return loadSourceFile(result.pointer, result.hashed)
    
def saveCachedResult(data, url, participant_uid, config):
    metadata = {**config, **{"URL": url, "Participant": participant_uid}}
    result = models.SourceFile.create(type="CachedResult", metadata=metadata)
    result.pointer = DATABASE_PATH + "visualization" + os.path.sep + participant_uid + os.path.sep + result.uid + ".bdat"
    result.hashed = saveSourceFile(data, DATABASE_PATH + "visualization" + os.path.sep + participant_uid + os.path.sep + result.uid + ".bdat")
    result.save()