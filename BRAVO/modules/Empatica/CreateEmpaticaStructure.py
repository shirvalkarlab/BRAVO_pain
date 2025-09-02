import os, sys 
import numpy as np 
from avro.datafile import DataFileReader
from avro.io import DatumReader
import time
import pandas as pd 
import blosc2
import pickle
import json
import subprocess
from scipy import io as sio

def getOffsetString(offset):
    if offset >= 0:
        return f"+{int(offset/3600):02d}:{int((offset%3600)/60):02d}"
    else:
        return f"-{int(abs(offset)/3600):02d}:{int((abs(offset)%3600)/60):02d}"

def createPlaceholderRecording(date):
    Recording = dict()
    Recording["SamplingRate"] = -1
    Recording["ChannelNames"] = []
    Recording["Time"] = np.zeros(0)
    Recording["Duration"] = 0
    Recording["Data"] = np.zeros((0,1))
    Recording["Missing"] = np.zeros((0,1))
    Recording["StartTime"] = date
    Recording["Descriptor"] = {}
    Recording["Metadata"] = {}
    return Recording

def BRAVORecordingBinaryFormat(Recordings):
    pData = bytes("BRAVORecordingStructure", "utf-8")
    pData += np.array([len(Recordings)], dtype=np.int32).tobytes()
    for Recording in Recordings:
        rData = bytes("BRAVORecording", "utf-8")
        rData += np.array([Recording["SamplingRate"]], dtype=np.float64).tobytes()
        rData += np.array([len(Recording["ChannelNames"])], dtype=np.int32).tobytes()
        rData += np.array([len(Recording["ChannelNames"][i]) for i in range(len(Recording["ChannelNames"]))], dtype=np.int32).tobytes()
        for channel in Recording["ChannelNames"]:
            rData += bytes(channel, "utf-8")
        rData += np.array([len(Recording["Time"])], dtype=np.int32).tobytes()
        rData += Recording["Time"].astype(np.float64).tobytes()
        for i in range(len(Recording["ChannelNames"])):
            rData += np.array([len(Recording["Data"][:,i])], dtype=np.int32).tobytes()
            rData += Recording["Data"][:,i].astype(np.float64).tobytes()
        for i in range(len(Recording["ChannelNames"])):
            rData += np.array([len(Recording["Missing"][:,i])], dtype=np.int32).tobytes()
            rData += Recording["Missing"][:,i].astype(np.int8).tobytes()
        rData += np.array([Recording["StartTime"]], dtype=np.float64).tobytes()
        Descriptor = json.dumps(Recording["Descriptor"]).encode("utf-8")
        rData += np.array([len(Descriptor)], dtype=np.int32).tobytes()
        rData += Descriptor
        Metadata = json.dumps(Recording["Metadata"]).encode("utf-8")
        rData += np.array([len(Metadata)], dtype=np.int32).tobytes()
        rData += Metadata
        if not type(Recording["Duration"]) == int:
            rData += np.array([len(Recording["Duration"])], dtype=np.int32).tobytes()
            rData += Recording["Duration"].astype(np.float64).tobytes()
        pData += rData 
    return pData

SourceDir = sys.argv[1]

while True:
    subprocess.run(["bash", "modules/Empatica/SyncData.sh"])
    study_ids = os.listdir(SourceDir)
    for study_id in study_ids:
        if study_id == ".DS_Store" or study_id.endswith(".py") or study_id.endswith(".sh") or study_id.endswith("Processed"):
            continue
        print("Processing Study: ", study_id)

        site_ids = os.listdir(SourceDir + "/" + study_id)
        for site_id in site_ids:
            if site_id == ".DS_Store":
                continue
            print("Processing Site: ", site_id)

            metadatas = os.listdir(SourceDir + "/" + study_id + "/" + site_id + "/metadata")
            participant_ids = []
            for i in range(len(metadatas)):
                if metadatas[i].endswith("metadata.csv"):
                    participant_id = metadatas[i].replace(f"{study_id}-{site_id}-", "").replace("_metadata.csv", "")
                    if not participant_id in participant_ids:
                        participant_ids.append(participant_id)
            
            participants = []
            for participant_id in participant_ids:
                df = pd.read_csv(SourceDir + "/" + study_id + "/" + site_id + "/metadata/" + study_id + "-" + site_id + "-" + participant_id + "_metadata.csv")
                participant = {
                    "ParticipantId": participant_id,
                    "SiteId": site_id,
                    "StudyId": study_id,
                    "OrganizationId": "",
                }
                for i in df.index:
                    if not pd.isna(df["time_offset"][i] ):
                        participant["Timezone"] = getOffsetString(df["time_offset"][i])
                        participant["TimezoneName"] = df["timezone_location"][i]
                    if not pd.isna(df["algo_version"][i]):
                        participant["AlgorithmVersion"] = df["algo_version"][i]

                participants.append(participant)

            session_dates = os.listdir(SourceDir + "/" + study_id + "/" + site_id + "/participant_data")
            for date in session_dates:
                if date == ".DS_Store":
                    continue
                print("Processing Date: ", date)

                participant_datas = os.listdir(SourceDir + "/" + study_id + "/" + site_id + "/participant_data/" + date)
                for participant_data in participant_datas:
                    if participant_data == ".DS_Store":
                        continue
                    
                    if os.path.exists(SourceDir + "/Processed/" + participant_data + "-" + date + "-raw_data.bdata"):
                        continue
                    
                    print("Processing Participant Data: ", participant_data)

                    Recordings = []
                    RawData = []

                    participant_raw_data_dir = SourceDir + "/" + study_id + "/" + site_id + "/participant_data/" + date + "/" + participant_data + "/raw_data/v6"
                    if os.path.exists(participant_raw_data_dir):
                        all_raw_datas = os.listdir(participant_raw_data_dir)
                        for file in all_raw_datas:
                            if file == ".DS_Store" or file.endswith(".bpkl"):
                                continue

                            if file.endswith(".pkl"):
                                os.remove(os.path.join(participant_raw_data_dir, file))
                                continue
                            
                            datumReader = DatumReader()
                            with open(os.path.join(participant_raw_data_dir, file), 'rb') as f:
                                try:
                                    reader = DataFileReader(f, datumReader)
                                    for record in reader:
                                        record["date"] = int(file.split("_")[1].replace(".avro",""))
                                        RawData.append(record)
                                    reader.close()
                                except Exception as e:
                                    print(f"Error reading Avro file {file}: {e}")
                    
                    for data in RawData:
                        Metadata = {
                            "RecordingType": "EmpaticaData",
                            "ParticipantId": data["enrollment"]["participantID"],
                            "SiteId": data["enrollment"]["siteID"],
                            "StudyId": data["enrollment"]["studyID"],
                            "OrganizationId": data["enrollment"]["organizationID"],
                            "DeviceSerialNumber": data["deviceSn"],
                            "DeviceType": data["deviceModel"],
                            "FirmwareVersion": data["fwVersion"],
                            "HardwareVersion": data["hwVersion"],
                            "AlgorithmVersion": data["algoVersion"],
                            "SchemaVersion": data["schemaVersion"],
                            "Timezone": getOffsetString(data["timezone"])
                        }
                        for key in data["rawData"].keys():
                            if key == "accelerometer":
                                if len(data["rawData"][key]["x"]) == 0:
                                    continue
                                Recording = createPlaceholderRecording(data["rawData"][key]["timestampStart"] / 1000000)
                                Recording["Metadata"] = Metadata

                                Recording["SamplingRate"] = data["rawData"][key]["samplingFrequency"]
                                Recording["Descriptor"] = data["rawData"][key]["imuParams"]

                                Recording["ChannelNames"] = ["ACC.X", "ACC.Y", "ACC.Z"]
                                Recording["ChannelUnits"] = ["g", "g", "g"]
                                Recording["Data"] = np.zeros((len(data["rawData"][key]["x"]), 3))
                                Recording["Data"][:, 0] = np.array(data["rawData"][key]["x"], dtype=float) * Recording["Descriptor"]["conversionFactor"]
                                Recording["Data"][:, 1] = np.array(data["rawData"][key]["y"], dtype=float) * Recording["Descriptor"]["conversionFactor"]
                                Recording["Data"][:, 2] = np.array(data["rawData"][key]["z"], dtype=float) * Recording["Descriptor"]["conversionFactor"]
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                Recording["Time"] = np.arange(len(Recording["Data"])) / Recording["SamplingRate"]
                                Recordings.append(Recording)
                            
                            elif key == "gyroscope":
                                if len(data["rawData"][key]["x"]) == 0:
                                    continue
                                Recording = createPlaceholderRecording(data["rawData"][key]["timestampStart"] / 1000000)
                                Recording["Metadata"] = Metadata

                                Recording["SamplingRate"] = data["rawData"][key]["samplingFrequency"]
                                Recording["Descriptor"] = data["rawData"][key]["imuParams"]

                                Recording["ChannelNames"] = ["GYRO.X", "GYRO.Y", "GYRO.Z"]
                                Recording["ChannelUnits"] = ["dps", "dps", "dps"]
                                Recording["Data"] = np.zeros((len(data["rawData"][key]["x"]), 3))
                                Recording["Data"][:, 0] = np.array(data["rawData"][key]["x"], dtype=float) * Recording["Descriptor"]["conversionFactor"]
                                Recording["Data"][:, 1] = np.array(data["rawData"][key]["y"], dtype=float) * Recording["Descriptor"]["conversionFactor"]
                                Recording["Data"][:, 2] = np.array(data["rawData"][key]["z"], dtype=float) * Recording["Descriptor"]["conversionFactor"]
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                Recording["Time"] = np.arange(len(Recording["Data"])) / Recording["SamplingRate"]
                                Recordings.append(Recording)

                            elif key == "magnetometer":
                                if len(data["rawData"][key]["x"]) == 0:
                                    continue
                                Recording = createPlaceholderRecording(data["rawData"][key]["timestampStart"] / 1000000)
                                Recording["Metadata"] = Metadata

                                Recording["SamplingRate"] = data["rawData"][key]["samplingFrequency"]
                                Recording["Descriptor"] = {
                                    "QualityIndex": data["rawData"][key]["qualityIndex"],
                                }

                                Recording["ChannelNames"] = ["MAG.X", "MAG.Y", "MAG.Z"]
                                Recording["ChannelUnits"] = ["µT", "µT", "µT"]
                                Recording["Data"] = np.zeros((len(data["rawData"][key]["x"]), 3))
                                Recording["Data"][:, 0] = np.array(data["rawData"][key]["x"], dtype=float)
                                Recording["Data"][:, 1] = np.array(data["rawData"][key]["y"], dtype=float)
                                Recording["Data"][:, 2] = np.array(data["rawData"][key]["z"], dtype=float)
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                Recording["Time"] = np.arange(len(Recording["Data"])) / Recording["SamplingRate"]
                                Recordings.append(Recording)

                            elif key == "eda":
                                if len(data["rawData"][key]["values"]) == 0:
                                    continue

                                Recording = createPlaceholderRecording(data["rawData"][key]["timestampStart"] / 1000000)
                                Recording["Metadata"] = Metadata

                                Recording["SamplingRate"] = data["rawData"][key]["samplingFrequency"]

                                Recording["ChannelNames"] = ["ElectroDermal Activity"]
                                Recording["ChannelUnits"] = ["µS"]
                                Recording["Data"] = np.zeros((len(data["rawData"][key]["values"]), 1))
                                Recording["Data"][:, 0] = np.array(data["rawData"][key]["values"], dtype=float)
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                Recording["Time"] = np.arange(len(Recording["Data"])) / Recording["SamplingRate"]
                                Recordings.append(Recording)

                            elif key == "temperature":
                                if len(data["rawData"][key]["values"]) == 0:
                                    continue

                                Recording = createPlaceholderRecording(data["rawData"][key]["timestampStart"] / 1000000)
                                Recording["Metadata"] = Metadata

                                Recording["SamplingRate"] = data["rawData"][key]["samplingFrequency"]

                                Recording["ChannelNames"] = ["Temperature"]
                                Recording["ChannelUnits"] = ["°C"]
                                Recording["Data"] = np.zeros((len(data["rawData"][key]["values"]), 1))
                                Recording["Data"][:, 0] = np.array(data["rawData"][key]["values"], dtype=float)
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                Recording["Time"] = np.arange(len(Recording["Data"])) / Recording["SamplingRate"]
                                Recordings.append(Recording)
                            
                            elif key == "bvp":
                                if len(data["rawData"][key]["values"]) == 0:
                                    continue

                                Recording = createPlaceholderRecording(data["rawData"][key]["timestampStart"] / 1000000)
                                Recording["Metadata"] = Metadata

                                Recording["SamplingRate"] = data["rawData"][key]["samplingFrequency"]

                                Recording["ChannelNames"] = ["Blood Volume Pulse"]
                                Recording["ChannelUnits"] = ["nW"]
                                Recording["Data"] = np.zeros((len(data["rawData"][key]["values"]), 1))
                                Recording["Data"][:, 0] = np.array(data["rawData"][key]["values"], dtype=float)
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                Recording["Time"] = np.arange(len(Recording["Data"])) / Recording["SamplingRate"]
                                Recordings.append(Recording)
                            
                            elif key == "steps":
                                if len(data["rawData"][key]["values"]) == 0:
                                    continue

                                Recording = createPlaceholderRecording(data["rawData"][key]["timestampStart"] / 1000000)
                                Recording["Metadata"] = Metadata

                                Recording["SamplingRate"] = data["rawData"][key]["samplingFrequency"]

                                Recording["ChannelNames"] = ["Steps"]
                                Recording["ChannelUnits"] = ["steps"]
                                Recording["Data"] = np.zeros((len(data["rawData"][key]["values"]), 1))
                                Recording["Data"][:, 0] = np.array(data["rawData"][key]["values"], dtype=float)
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                Recording["Time"] = np.arange(len(Recording["Data"])) / Recording["SamplingRate"]
                                Recordings.append(Recording)
                            
                            elif key == "ambientLight":
                                if len(data["rawData"][key]["values"]) == 0:
                                    continue

                                Recording = createPlaceholderRecording(data["rawData"][key]["timestampStart"] / 1000000)
                                Recording["Metadata"] = Metadata

                                Recording["SamplingRate"] = data["rawData"][key]["samplingFrequency"]

                                Recording["ChannelNames"] = ["Ambient Light"]
                                Recording["ChannelUnits"] = ["lux"]
                                Recording["Data"] = np.zeros((len(data["rawData"][key]["values"]), 1))
                                Recording["Data"][:, 0] = np.array(data["rawData"][key]["values"], dtype=float)
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                Recording["Time"] = np.arange(len(Recording["Data"])) / Recording["SamplingRate"]
                                Recordings.append(Recording)
                            
                            # Combined Events into one recording
                            TagsTime = np.array(data["rawData"]["tags"]["tagsTimeMicros"]) / 1000000
                            SystolicPeaksTime = np.array(data["rawData"]["systolicPeaks"]["peaksTimeNanos"]) / 1000000000

                            Recording = createPlaceholderRecording(data["date"])
                            Recording["Metadata"] = Metadata

                            Recording["SamplingRate"] = -1
                            Recording["ChannelNames"] = ["Tags", "Systolic Peaks"]
                            Recording["ChannelUnits"] = ["", ""]
                            Recording["Time"] = np.unique(np.concatenate((TagsTime, SystolicPeaksTime)))
                            Recording["Time"].sort()
                            Recording["Data"] = np.zeros((len(Recording["Time"]), 2))
                            for t in range(len(Recording["Time"])):
                                if Recording["Time"][t] in TagsTime:
                                    Recording["Data"][t,0] = 1
                                if Recording["Time"][t] in SystolicPeaksTime:
                                    Recording["Data"][t,1] = 1
                            Recording["Missing"] = np.zeros(Recording["Data"].shape)
                            Recordings.append(Recording)

                    participant_processed_data_dir = SourceDir + "/" + study_id + "/" + site_id + "/participant_data/" + date + "/" + participant_data + "/digital_biomarkers/aggregated_per_minute"
                    if os.path.exists(participant_processed_data_dir):
                        biomarkers = os.listdir(participant_processed_data_dir)

                        participant = {
                            "ParticipantId": participant_data.split("-")[0],
                            "SiteId": site_id,
                            "StudyId": study_id,
                            "DeviceSerialNumber": participant_data.split("-")[1],
                        }
                        for n in range(len(participants)):
                            if participant["ParticipantId"] == participants[n]["ParticipantId"]:
                                participant = participants[n]
                                break

                        for biomarker in biomarkers:
                            if biomarker == ".DS_Store":
                                continue

                            if biomarker.endswith(".csv"):
                                df = pd.read_csv(os.path.join(participant_processed_data_dir, biomarker))
                                
                                AllChannels = []
                                for key in df.keys():
                                    if key in ["timestamp_unix", "timestamp_iso", "participant_full_id", "missing_value_reason"]:
                                        continue

                                    if key not in AllChannels:
                                        AllChannels.append(key)

                                Recording = createPlaceholderRecording(df["timestamp_unix"].iloc[0] / 1000)
                                Recording["Metadata"] = participant
                                Recording["Metadata"]["RecordingType"] = "EmpaticaData"
                                Recording["Metadata"]["Filename"] = biomarker.replace(".csv", "")
                                Recording["SamplingRate"] = -1
                                Recording["ChannelNames"] = AllChannels
                                Recording["ChannelUnits"] = [""] * len(Recording["ChannelNames"])
                                Recording["Data"] = np.zeros((len(df), len(Recording["ChannelNames"])))
                                for channel in Recording["ChannelNames"]:
                                    if df[channel].dtype == "object":
                                        Recording["Descriptor"][channel] = {}
                                        options = df[channel].unique().tolist()
                                        for option in options:
                                            if option not in Recording["Descriptor"][channel].keys():
                                                Recording["Descriptor"][channel][option] = options.index(option)
                                        Recording["Data"][:, Recording["ChannelNames"].index(channel)] = df[channel].apply(lambda x: Recording["Descriptor"][channel].get(x, -1)).values
                                    else:
                                        Recording["Data"][:, Recording["ChannelNames"].index(channel)] = df[channel].values
                                
                                Recording["Missing"] = np.zeros(Recording["Data"].shape)
                                for i in df.index:
                                    if not pd.isna(df["missing_value_reason"][i]):
                                        Recording["Missing"][i, :] = 1
                                
                                Recording["Time"] = df["timestamp_unix"].values / 1000
                                Recording["StartTime"] = Recording["Time"][0]
                                Recording["Time"] -= Recording["StartTime"]  # Normalize time to start at 0
                                
                                Recordings.append(Recording)

                    # Save Recordings to a file
                    with open(SourceDir + "/Processed/" + participant_data + "-" + date + "-raw_data.bdata", "wb+") as f:
                        pData = BRAVORecordingBinaryFormat(Recordings)
                        f.write(blosc2.compress2(pData, typesize=1))
    
    time.sleep(3600)