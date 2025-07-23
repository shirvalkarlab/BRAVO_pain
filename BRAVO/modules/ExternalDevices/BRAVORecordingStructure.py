import numpy as np
import pandas as pd
from io import BytesIO
import blosc2
import json

def convertToBinaryFormat(Recordings):
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

def decodebdata(rawBytes):
    if not rawBytes.startswith(b"BRAVORecordingStructure"):
        raise ValueError("Invalid BRAVORecordingStructure data format")
    
    nRecordings = int.from_bytes(rawBytes[23:27], "little")
    Recordings = []
    
    offset = 27
    while offset < len(rawBytes):
        if not rawBytes[offset:offset+14] == b"BRAVORecording":
            raise ValueError("Invalid BRAVORecording data format")

        Recording = {}
        Recording["SamplingRate"] = np.frombuffer(rawBytes[offset+14:offset+22], dtype=np.float64)[0]
        offset += 22

        Recording["ChannelNames"] = []
        nChannels = int.from_bytes(rawBytes[offset:offset+4], "little")
        ChannelNameLengths = np.frombuffer(rawBytes[offset+4:offset+4+nChannels*4], dtype=np.int32)
        offset += 4+nChannels*4
        for i in range(nChannels):
            channelNameLength = ChannelNameLengths[i]
            channelName = rawBytes[offset:offset+channelNameLength].decode("utf-8")
            Recording["ChannelNames"].append(channelName)
            offset += channelNameLength
        
        nTimes = int.from_bytes(rawBytes[offset:offset+4], "little")
        Recording["Time"] = np.frombuffer(rawBytes[offset+4:offset+4+nTimes*8], dtype=np.float64)
        offset += 4+nTimes*8

        Recording["Data"] = []
        for i in range(nChannels):
            nData = int.from_bytes(rawBytes[offset:offset+4], "little")
            Recording["Data"].append(np.frombuffer(rawBytes[offset+4:offset+4+nData*8], dtype=np.float64))
            offset += 4+nData*8
        Recording["Data"] = np.array(Recording["Data"]).T

        Recording["Missing"] = []
        for i in range(nChannels):
            nData = int.from_bytes(rawBytes[offset:offset+4], "little")
            Recording["Missing"].append(np.frombuffer(rawBytes[offset+4:offset+4+nData], dtype=np.int8))
            offset += 4+nData
        Recording["Missing"] = np.array(Recording["Missing"]).T

        Recording["StartTime"] = np.frombuffer(rawBytes[offset:offset+8], dtype=np.float64)[0]
        offset += 8

        DescriptorLength = int.from_bytes(rawBytes[offset:offset+4], "little")
        Recording["Descriptor"] = json.loads(rawBytes[offset+4:offset+4+DescriptorLength].decode("utf-8"))
        offset += 4 + DescriptorLength

        MetadataLength = int.from_bytes(rawBytes[offset:offset+4], "little")
        Recording["Metadata"] = json.loads(rawBytes[offset+4:offset+4+MetadataLength].decode("utf-8"))
        offset += 4 + MetadataLength

        if not rawBytes[offset:offset+14] == b"BRAVORecording":
            nTimes = int.from_bytes(rawBytes[offset:offset+4], "little")
            Recording["Duration"] = np.frombuffer(rawBytes[offset+4:offset+4+nTimes*8], dtype=np.float64)
            offset += 4+nTimes*8
        else:
            Recording["Duration"] = 0
        
        Recordings.append(Recording)
    
    return Recordings