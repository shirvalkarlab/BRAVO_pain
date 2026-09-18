import numpy as np
import pandas as pd
from io import BytesIO

def decodeMDATv2(rawBytes):
    packets = []
    startIndex = 0
    while startIndex < len(rawBytes):
        header = rawBytes[startIndex : startIndex + 4]
        if not header == b'PFF\x00':
            raise Exception("ReadMDAT Format Error: Header Error")
        
        Time = np.frombuffer(rawBytes[startIndex + 4 : startIndex + 12], dtype="<i8")[0]
        dataLengths = np.frombuffer(rawBytes[startIndex + 12 : startIndex + 20], dtype="<i4")
        Trigger = rawBytes[startIndex + 20 : startIndex + 20 + dataLengths[0]].decode("utf-8")
        if Trigger == "TriggerText":
            Data = rawBytes[startIndex + 20 + dataLengths[0] : startIndex + 20 + dataLengths[0] + dataLengths[1]].decode("utf-8")
        else:
            Data = np.frombuffer(rawBytes[startIndex + 20 + dataLengths[0] : startIndex + 20 + dataLengths[0] + dataLengths[1]], dtype="<f8")
            
        packets.append({
            "Time": Time,
            "Type": Trigger,
            "Data": Data
        })

        startIndex += 20 + dataLengths[0] + dataLengths[1]

    RecordingId = 0
    DelsysRecording = []
    for i in range(len(packets)):
        if packets[i]["Type"] == "TriggerText":
            if packets[i]["Data"] == "Delsys Started":
                RecordingId += 1

    Channels = []
    for i in range(len(packets)):
        if packets[i]["Type"].endswith(" SamplingRate"):
            ChannelName = packets[i]["Type"].replace(" SamplingRate","")
            Channels.append(ChannelName)
    Channels = sorted(Channels)

    Delsys = []
    for n in range(len(Channels)):
        totalSize = 0
        startTime = 0
        fs = -1
        for i in range(len(packets)):
            if packets[i]["Type"] == "TriggerText":
                if packets[i]["Data"] == "Delsys Started":
                    startTime = packets[i]["Time"]
            elif packets[i]["Type"] == Channels[n] + " SamplingRate":
                fs = packets[i]["Data"]
            elif packets[i]["Type"] == Channels[n]:
                totalSize += len(packets[i]["Data"])

        Signal = np.zeros(totalSize)
        totalSize = 0
        for i in range(len(packets)):
            if packets[i]["Type"] == Channels[n]:
                Signal[totalSize:totalSize + len(packets[i]["Data"])] = packets[i]["Data"]
                totalSize += len(packets[i]["Data"])
        
        Delsys.append({
            "Name": Channels[n],
            "Data": Signal,
            "SamplingRate": fs,
            "StartTime": startTime
        })

    SamplingRates = np.unique([Delsys[i]["SamplingRate"] for i in range(len(Delsys))])

    SensorDataList = []
    for fs in SamplingRates:
        RecordingDurations = [len(Delsys[i]["Data"]) for i in range(len(Delsys)) if Delsys[i]["SamplingRate"] == fs]
        MinRecordingDuration = np.min(RecordingDurations)

        Data = {"ChannelNames": []}
        Data["Time"] = np.arange(MinRecordingDuration) / fs
        Data["Data"] = []
        for i in range(len(Delsys)):
            if Delsys[i]["SamplingRate"] == fs:
                Data["Data"].append(Delsys[i]["Data"][:MinRecordingDuration])
                Data["ChannelNames"].append(Delsys[i]["Name"])
        Data["Data"] = np.array(Data["Data"]).T
        Data["SamplingRate"] = fs
        Data["StartTime"] = Delsys[i]["StartTime"] / 1000
        Data["Missing"] = np.zeros(Data["Data"].shape)
        Data["Duration"] = MinRecordingDuration / fs
        SensorDataList.append(Data)
    
    return SensorDataList


def _mdatPackets(rawBytes):
    """Validate packet boundaries before interpreting either MDAT version."""
    packets = []
    offset = 0
    while offset < len(rawBytes):
        if len(rawBytes) - offset < 20 or rawBytes[offset:offset + 4] != b'PFF\x00':
            raise ValueError("Invalid or truncated MDAT packet header")
        timestamp = int(np.frombuffer(rawBytes[offset + 4:offset + 12], dtype="<i8")[0])
        name_size, data_size = np.frombuffer(rawBytes[offset + 12:offset + 20], dtype="<i4")
        end = offset + 20 + int(name_size) + int(data_size)
        if name_size <= 0 or data_size < 0 or end > len(rawBytes):
            raise ValueError("Invalid or truncated MDAT packet length")
        name = rawBytes[offset + 20:offset + 20 + name_size].decode("utf-8")
        payload = rawBytes[offset + 20 + name_size:end]
        if name in ("TriggerText", "Delsys_ChannelIDs"):
            data = payload.decode("utf-8")
        else:
            if data_size % 8:
                raise ValueError("Invalid MDAT numeric payload length")
            data = np.frombuffer(payload, dtype="<f8")
        packets.append((timestamp, name, data))
        offset = end
    if not packets:
        raise ValueError("Empty MDAT recording")
    return packets


def decodeMDATAuto(rawBytes):
    """The shared .mdat extension must not silently change legacy v2 routing."""
    packets = _mdatPackets(rawBytes)
    if any(name == "Delsys_ChannelIDs" for _, name, _ in packets):
        return decodeMDATv3(rawBytes)
    return decodeMDATv2(rawBytes)


def decodeMDATv3(rawBytes):
    """Decode v3 packets without truncating channels or inventing gap samples.

    Packet timestamps are retained as millisecond native timestamps. Each
    channel/contiguous interval is a separate recording, so channels with
    different starts or sample counts never acquire another channel's clock.
    """
    rates = {}
    pending_channel = None
    channel_packets = {}
    for timestamp, name, data in _mdatPackets(rawBytes):
        if name == "Delsys_ChannelIDs":
            if not data:
                raise ValueError("Empty MDAT channel identifier")
            pending_channel = data
        elif name == "Delsys_SamplingRate":
            if pending_channel is None or len(data) != 1 or not np.isfinite(data[0]) or data[0] <= 0:
                raise ValueError("Invalid MDAT channel sampling rate")
            if pending_channel in rates and rates[pending_channel] != float(data[0]):
                raise ValueError("MDAT channel sampling rate changes within file")
            rates[pending_channel] = float(data[0])
            pending_channel = None
        elif name.startswith("Delsys_DataPacket|"):
            channel = name.split("|", 1)[1]
            if channel not in rates or not len(data):
                raise ValueError("MDAT data requires channel rate and nonempty samples")
            channel_packets.setdefault(channel, []).append((timestamp, data))
    if not channel_packets:
        raise ValueError("MDAT v3 contains no channel samples")

    recordings = []
    for channel, packets in channel_packets.items():
        rate = rates[channel]
        chunks, times = [], []
        start = end = None
        sample_count = 0
        for timestamp, values in packets:
            clock = timestamp / 1000
            if end is not None and clock < end - 0.0005:
                raise ValueError("Overlapping or out-of-order MDAT packets")
            if end is not None and abs(clock - end) > 0.0005:
                recordings.append(_mdatSegment(channel, rate, start, chunks, times))
                chunks, times = [], []
            if not chunks:
                start = clock
                sample_count = 0
            chunks.append(values)
            sample_count += len(values)
            times.append(timestamp)
            end = start + sample_count / rate
        recordings.append(_mdatSegment(channel, rate, start, chunks, times))
    return recordings


def _mdatSegment(channel, rate, start, chunks, packet_times):
    values = np.concatenate(chunks).reshape(-1, 1)
    missing = ~np.isfinite(values)
    return {"ChannelNames": [channel], "Time": np.arange(len(values)) / rate,
            "Data": values, "SamplingRate": rate, "StartTime": start,
            "Missing": missing.astype(int), "Duration": len(values) / rate,
            "ClockBasis": "native MDAT packet timestamp (milliseconds)",
            "PacketTimesMilliseconds": list(packet_times), "FormatVersion": 3}
