#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Give a general description of UF AO MPX File here.

"""

import sys, os
import numpy as np
from datetime import datetime

E_Command_Generic_Message       = 7 
E_Command_Module_Params         = 8 
E_Command_Stim_Start            = 10 
E_Command_Stim_Stop             = 11 
E_Command_Motor_Up              = 100
E_Command_Motor_Down            = 101
E_Command_Motor_Stop            = 102
E_Command_Motor_SetPos          = 106  
E_Command_Motor_SetSpeed        = 110 
E_Command_Motor_Config          = 115 
E_Command_WirelessMap_ChannelChange    = 200 
E_Command_WirelessMap_TemplMatchTemplChange    = 230 
E_Command_WirelessMap_TemplMatchThreshold      = 231 
E_Command_WirelessMap_TemplMatchSpikesSelector = 232 
E_Command_MGPlus_Imp_Values            = 411 
E_Command_Traj_Settings                = 522
E_Command_Filter_Params                = 867

# Status Bytes Definitions
E_Status_Generic_Message            = 2 
E_Status_Stim_Status                = 4 

# Generic Message Definitions
E_GenMes_MessageMotorMilage       = 3 
E_GenMes_HeadStageStatuses        = 6 
E_GenMes_TMDeactivate             = 14
E_GenMes_TextMessage              = 20
E_GenMes_PortAsStrobe             = 21
E_GenMes_ChannelState             = 25
E_GenMes_ChannelDownSample        = 26
E_GenMes_ReferenceChanged         = 34

# Module Parameters
E_Module_ModuleStimulus          = 1 
E_Module_AnalogOutputParam       = 3 
E_Module_ElectrodeParam          = 5 

def removeMPXDateTime(filename):
    with open(filename, "rb") as file:
        rawBytes = file.read()
        
    rawBytesArray = bytearray(rawBytes)
    
    blockOffset = 0
    while blockOffset < len(rawBytes) - 5:
        blockLength = int.from_bytes(rawBytes[slice(blockOffset + 0, blockOffset + 2)], byteorder="little")
        blockType = str(bytes([rawBytes[blockOffset + 2]]), "utf-8")
        
        if rawBytes[blockOffset + 2] == 104:
            rawBytesArray[slice(blockOffset+10, blockOffset+18)] = bytearray(np.array([0,0,0,0,1,1,208,7], dtype=np.uint8).tobytes())
            
        blockOffset += blockLength
        
    with open(filename, "wb+") as file:
        file.write(bytes(rawBytesArray))

def decodeMPX(rawBytes, StreamToParse=list()):
    """
    AlphaOmega MPX File Format Decoder for Python. 
    
    Parameters:
    StreamToParse (array): Array of headers to parse.

    Returns:
    Content (dictionary): Dictionary of parsed output, contain headers, raw data, and streams.
    """
    
    Content = {"Header": dict(), "Data": dict(), "Stream": list()}
    
    ChannelDefinitionPackage = list()
    ChannelDataPackage = list()
    ChannelDataLength = dict()
    ChannelNameMap = dict()
    
    Stream = dict()
    
    blockOffset = 0
    while blockOffset < len(rawBytes) - 5:
        blockLength = int.from_bytes(rawBytes[slice(blockOffset + 0, blockOffset + 2)], byteorder="little")
        blockType = str(bytes([rawBytes[blockOffset + 2]]), "utf-8")
        
        # ASCII 'h' = 104
        if rawBytes[blockOffset + 2] == 104:
            Content["Header"]["ProgramVersion"] = np.frombuffer(rawBytes[blockOffset+8:blockOffset+10], dtype=np.uint16)[0]
            Content["Header"]["SessionDateTime"] = datetime(int.from_bytes(rawBytes[slice(blockOffset+16, blockOffset+18)], byteorder="little"), rawBytes[blockOffset+15], rawBytes[blockOffset+14],
                                                            rawBytes[blockOffset+10], rawBytes[blockOffset+11], rawBytes[blockOffset+12])
            Content["Header"]["MinimumAcquisitionTime"] = np.frombuffer(rawBytes[blockOffset+20:blockOffset+28], dtype=float)[0]
            Content["Header"]["MaximumAcquisitionTime"] = np.frombuffer(rawBytes[blockOffset+28:blockOffset+36], dtype=float)[0]
            Content["Header"]["EraseCount"] = np.frombuffer(rawBytes[blockOffset+36:blockOffset+40], dtype=np.int32)[0]
            Content["Header"]["DataFormatVersion"] = rawBytes[40]
            Content["Header"]["ApplicationName"] = rawBytes[blockOffset+41:blockOffset+51].rstrip(b'\x00').decode("utf-8")
            Content["Header"]["ResourceVersion"] = rawBytes[blockOffset+51:blockOffset+55].rstrip(b'\x00').decode("utf-8")
        
        # ASCII '0' = 48
        elif rawBytes[blockOffset + 2] == 48:
            pass
        
        # ASCII '1' = 49
        elif rawBytes[blockOffset + 2] == 49:
            pass
        
        # ASCII '2' = 50
        elif rawBytes[blockOffset + 2] == 50:
            ChannelDefinitionPackage.append((blockOffset, blockLength))
        
        # ASCII '3' = 51
        elif rawBytes[blockOffset + 2] == 51:
            pass
        
        # ASCII '4' = 52
        elif rawBytes[blockOffset + 2] == 52:
            #ChannelDataPackage.append((blockOffset, blockLength))
            #print(blockLength)
            pass
        
        # ASCII '5' = 53
        elif rawBytes[blockOffset + 2] == 53:
            ChannelDataPackage.append((blockOffset, blockLength))
            ChannelID = np.frombuffer(rawBytes[blockOffset+4:blockOffset+6], dtype=np.int16)[0]
            if ChannelID in ChannelDataLength.keys():
                ChannelDataLength[ChannelID] += (blockLength - 10) / 2
            else:
                ChannelDataLength[ChannelID] = (blockLength - 10) / 2
        
        # ASCII 'S' = 83
        elif rawBytes[blockOffset + 2] == 83:
            if len(Stream) > 0:
                Content["Stream"].append(Stream)
            Stream = {"ChannelName": "", "Channel": 0, "Data": list()}
            Stream["ChannelName"] = rawBytes[blockOffset+14:blockOffset+blockLength-4].rstrip(b'\x00').decode("utf-8")
            Stream["Channel"] = np.frombuffer(rawBytes[blockOffset+8:blockOffset+10], dtype=np.int16)[0]
    
        # ASCII 'b' = 98
        elif rawBytes[blockOffset + 2] == 98:
            pass
    
        # ASCII 'E' = 69
        elif rawBytes[blockOffset + 2] == 69:
            StreamStruct = dict()
            StreamStruct["Timestamp"] = np.frombuffer(rawBytes[blockOffset+4:blockOffset+8], dtype=np.uint32)[0]
            
            # Command Type "M" = 77
            if rawBytes[blockOffset+10] == 77:
                StreamStruct["isStatus"] = False
                StreamStruct["StatusByte"] = rawBytes[blockOffset+11]
                StreamStruct["PackageType"] = np.frombuffer(rawBytes[blockOffset+12:blockOffset+14], dtype=np.int16)[0]
                
                if not StreamStruct["PackageType"] in StreamToParse and not len(StreamToParse) == 0:
                    blockOffset += blockLength
                    continue
                    
                if StreamStruct["PackageType"] == E_Command_Generic_Message:
                    StreamStruct["MessageType"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    
                    if not StreamStruct["MessageType"] in StreamToParse and not len(StreamToParse) == 0:
                        blockOffset += blockLength
                        continue
                    
                    if StreamStruct["MessageType"] == E_GenMes_ChannelDownSample:
                        StreamStruct["ChannelID"], _, StreamStruct["DownSampleFactor"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+22], dtype=np.int16)
    
                    # TODO: TM Dactivate. According to StreamFormat.h this is replaced. See Wiki [77,3,7,0,14,0]
                    elif StreamStruct["MessageType"] == E_GenMes_TMDeactivate:
                        pass
                    
                    # TODO: Reference Changed. See Wiki [77,3,7,0,34,0]
                    elif StreamStruct["MessageType"] == E_GenMes_ReferenceChanged:
                        pass
                    
                    elif StreamStruct["MessageType"] == E_GenMes_PortAsStrobe:
                        StreamStruct["ChannelID"] = np.frombuffer(rawBytes[blockOffset+20:blockOffset+22], dtype=np.int16)[0]
                        StreamStruct["Strobe"] = rawBytes[blockOffset+16] == 1
                    
                    elif StreamStruct["MessageType"] == E_GenMes_ChannelState:
                        StreamStruct["ChannelID"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+18], dtype=np.int16)[0]
                        StreamStruct["AcquisitionOn"] = rawBytes[blockOffset+20] == 1
                    
                    elif StreamStruct["MessageType"] == E_GenMes_TextMessage:
                        StreamStruct["RealTimestamp"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+20], dtype=np.uint32)[0]
                        StreamStruct["Message"] = rawBytes[blockOffset+22:blockOffset+blockLength].rstrip(b'\x00').decode("utf-8")
    
                elif StreamStruct["PackageType"] == E_Command_WirelessMap_TemplMatchTemplChange:
                    StreamStruct["ChannelID"], StreamStruct["TemplateID"], StreamStruct["nPoints"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+20], dtype=np.int16)
                    StreamStruct["TemplatePoints"] = np.frombuffer(rawBytes[blockOffset+20:blockOffset+52], dtype=np.int16)
                    StreamStruct["TemplateMode"] = np.frombuffer(rawBytes[blockOffset+52:blockOffset+54], dtype=np.int16)[0]
                
                elif StreamStruct["PackageType"] == E_Command_WirelessMap_TemplMatchThreshold:
                    StreamStruct["ChannelID"], StreamStruct["TemplateID"], StreamStruct["Threshold"], StreamStruct["NoiseLevel"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+22], dtype=np.int16)
                
                elif StreamStruct["PackageType"] == E_Command_WirelessMap_TemplMatchSpikesSelector:
                    StreamStruct["YCoord"] = [0,0]
                    StreamStruct["ChannelID"], StreamStruct["Enabled"], StreamStruct["TemplateID"], StreamStruct["XCoord"], StreamStruct["YCoord"][0], StreamStruct["YCoord"][1], StreamStruct["SpikeSelector"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+28], dtype=np.int16)
                
                elif StreamStruct["PackageType"] == E_Command_Traj_Settings:
                    StreamStruct["TrajectoryIndex"], StreamStruct["TrajectorySide"], StreamStruct["BenGunType"]  = np.frombuffer(rawBytes[blockOffset+14:blockOffset+20], dtype=np.int16)
                    StreamStruct["BenGunElectrodeMap"] = np.frombuffer(rawBytes[blockOffset+20:blockOffset+30], dtype=np.int16)
                    StreamStruct["MaxElectrode"] = np.frombuffer(rawBytes[blockOffset+30:blockOffset+32], dtype=np.int16)[0]
                    StreamStruct["CenPosX"], StreamStruct["CenPosY"], StreamStruct["StartDepth"], StreamStruct["TargetDepth"], StreamStruct["MacroMicroDistance"] = np.frombuffer(rawBytes[blockOffset+32:blockOffset+52], dtype=np.float32)
                    StreamStruct["LeadType"] = np.frombuffer(rawBytes[blockOffset+52:blockOffset+54], dtype=np.int16)[0]
                
                elif StreamStruct["PackageType"] == E_Command_Module_Params:
                    StreamStruct["ModuleType"], StreamStruct["DestinationID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+18], dtype=np.int16)
                    if StreamStruct["ModuleType"] == E_Module_ModuleStimulus:
                        StreamStruct["StimulationChannel"], StreamStruct["StimulationReturn"], StreamStruct["StimulationType"] = np.frombuffer(rawBytes[blockOffset+18:blockOffset+24], dtype=np.int16)
                        StreamStruct["Amplitudes"] = np.frombuffer(rawBytes[blockOffset+24:blockOffset+28], dtype=np.int16)
                        StreamStruct["PulseWidths"] = np.frombuffer(rawBytes[blockOffset+28:blockOffset+32], dtype=np.int16)
                        StreamStruct["Duration"] = np.frombuffer(rawBytes[blockOffset+32:blockOffset+36], dtype=np.int32)[0]
                        StreamStruct["Frequency"], StreamStruct["StopRecChannelMask"], StreamStruct["StopRecGroupID"], StreamStruct["IncStepSize"] = np.frombuffer(rawBytes[blockOffset+36:blockOffset+44], dtype=np.int16)
                        StreamStruct["PulseDelays"] = np.frombuffer(rawBytes[blockOffset+46:blockOffset+50], dtype=np.int16)
                        StreamStruct["AnalogStim"], StreamStruct["AnalogWaveID"] = np.frombuffer(rawBytes[blockOffset+50:blockOffset+54], dtype=np.int16)
                    
                    # TODO: Analog Output. I do not have enough data to reverse engineer this.
                    elif StreamStruct["ModuleType"] == E_Module_AnalogOutputParam:
                        pass
                    
                    # TODO: We are still missing a lot of unknowns. See Wiki [77,3,8,0,5,0]
                    elif StreamStruct["ModuleType"] == E_Module_ElectrodeParam:
                        StreamStruct["ImpedanceWave"] = [0,0]
                        StreamStruct["ImpedanceWave"][0], StreamStruct["ChannelID"], StreamStruct["ImpedanceWave"][1] = np.frombuffer(rawBytes[blockOffset+26:blockOffset+32], dtype=np.int16)
                        StreamStruct["HSGain"] = np.frombuffer(rawBytes[blockOffset+34:blockOffset+36], dtype=np.int16)[0]
                        StreamStruct["ContactType"] = np.frombuffer(rawBytes[blockOffset+38:blockOffset+40], dtype=np.int16)[0]
                        StreamStruct["PreGain"] = np.frombuffer(rawBytes[blockOffset+42:blockOffset+44], dtype=np.int16)[0]
                        
                elif StreamStruct["PackageType"] == E_Command_Stim_Start:
                    StreamStruct["ChannelID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    
                elif StreamStruct["PackageType"] == E_Command_Stim_Stop:
                    StreamStruct["ChannelID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    
                elif StreamStruct["PackageType"] == E_Command_Motor_Up:
                    StreamStruct["MotorID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    StreamStruct["OffSetPosition"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+20], dtype=np.int32)[0]
                
                elif StreamStruct["PackageType"] == E_Command_Motor_Down:
                    StreamStruct["MotorID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    StreamStruct["OffSetPosition"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+20], dtype=np.int32)[0]
                
                elif StreamStruct["PackageType"] == E_Command_Motor_Stop:
                    StreamStruct["MotorID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    
                elif StreamStruct["PackageType"] == E_Command_Motor_SetPos:
                    StreamStruct["MotorID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    StreamStruct["Position"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+20], dtype=np.int32)[0]
                
                elif StreamStruct["PackageType"] == E_Command_Motor_SetSpeed:
                    StreamStruct["MotorID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    StreamStruct["Speed"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+20], dtype=np.int32)[0]
                
                elif StreamStruct["PackageType"] == E_Command_Motor_Config:
                    StreamStruct["MotorID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    StreamStruct["Position"], StreamStruct["ZeroPosition"], StreamStruct["TargetPosition"], StreamStruct["StartPosition"], StreamStruct["Speed"], StreamStruct["Range"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+40], dtype=np.int32)
    
                elif StreamStruct["PackageType"] == E_Command_WirelessMap_ChannelChange:
                    StreamStruct["ChannelID"], StreamStruct["Level"], StreamStruct["Direction"], StreamStruct["Gain"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+22], dtype=np.int16)
                    StreamStruct["Enabled"] = rawBytes[blockOffset+22] == 1
                
                elif StreamStruct["PackageType"] == E_Command_Filter_Params:
                    StreamStruct["DownSampleFactor"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    StreamStruct["FilterParams"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+20], dtype=np.int32)[0]
                    StreamStruct["ChannelID"], StreamStruct["FilterType"] = np.frombuffer(rawBytes[blockOffset+20:blockOffset+24], dtype=np.int16)
                    StreamStruct["Coefficients"] = np.frombuffer(rawBytes[blockOffset+24:blockOffset+64], dtype=np.int16)
                    StreamStruct["nCoefficient"] = np.frombuffer(rawBytes[blockOffset+64:blockOffset+66], dtype=np.int16)[0]
                
                elif StreamStruct["PackageType"] == E_Command_MGPlus_Imp_Values:
                    StreamStruct["ChannelMask"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    StreamStruct["Impedances"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+80], dtype=np.int32)
                    StreamStruct["ChannelGroupID"] = np.frombuffer(rawBytes[blockOffset+80:blockOffset+82], dtype=np.int16)[0]
                
                else:
                    print(StreamStruct["PackageType"])
                
            elif rawBytes[blockOffset+10] == 83:
                StreamStruct["isStatus"] = True
                StreamStruct["StatusByte"] = rawBytes[blockOffset+11]
                StreamStruct["PackageType"] = np.frombuffer(rawBytes[blockOffset+12:blockOffset+14], dtype=np.int16)[0]
                
                if not StreamStruct["PackageType"] in StreamToParse:
                    blockOffset += blockLength
                    continue
                    
                if StreamStruct["PackageType"] == E_Status_Stim_Status:
                    StreamStruct["ChannelID"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    StreamStruct["FrequencyDeviation"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+18], dtype=np.int16)[0]
                    StreamStruct["StimStatus"] = np.frombuffer(rawBytes[blockOffset+18:blockOffset+20], dtype=np.int16)[0]
                    StreamStruct["MeasuredAmplitudes"] = np.frombuffer(rawBytes[blockOffset+20:blockOffset+24], dtype=np.int16)

                if StreamStruct["PackageType"] == E_Status_Generic_Message:
                    StreamStruct["MessageType"] = np.frombuffer(rawBytes[blockOffset+14:blockOffset+16], dtype=np.int16)[0]
                    
                    if not StreamStruct["MessageType"] in StreamToParse:
                        blockOffset += blockLength
                        continue
                    
                    if StreamStruct["MessageType"] == E_GenMes_ChannelDownSample:
                        StreamStruct["ChannelID"], _, StreamStruct["DownSampleFactor"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+22], dtype=np.int16)
    
                    if StreamStruct["MessageType"] == E_GenMes_MessageMotorMilage:
                        StreamStruct["MotorMilage"] = np.frombuffer(rawBytes[blockOffset+16:blockOffset+20], dtype=np.int32)[0]
                        StreamStruct["MotorCardStatus"] = np.frombuffer(rawBytes[blockOffset+20:blockOffset+22], dtype=np.int16)[0] == 0
                        
            else:
                print(rawBytes[blockOffset+10])
                
            Stream["Data"].append(StreamStruct)
            
        else:
            print(rawBytes[blockOffset + 2])
            
        blockOffset += blockLength
    
    Content["Stream"].append(Stream)
    
    for blockOffset, blockLength in ChannelDefinitionPackage:
        if np.frombuffer(rawBytes[blockOffset+12:blockOffset+14], dtype=np.int16)[0] in ChannelDataLength.keys():
            ChannelDefinition = dict()
            ChannelDefinition["isAnalog"] = np.frombuffer(rawBytes[blockOffset+8:blockOffset+10], dtype=np.int16)[0] == 1
            ChannelDefinition["isInput"] = np.frombuffer(rawBytes[blockOffset+10:blockOffset+12], dtype=np.int16)[0] == 1
            ChannelDefinition["ChannelID"] = np.frombuffer(rawBytes[blockOffset+12:blockOffset+14], dtype=np.int16)[0]
            
            # There are different headers for Analog vs Digital
            # Analog Channel
            if ChannelDefinition["isAnalog"]:
                ChannelDefinition["Mode"] = np.frombuffer(rawBytes[blockOffset+18:blockOffset+20], dtype=np.int16)[0]
                ChannelDefinition["BitResolution"] = np.frombuffer(rawBytes[blockOffset+20:blockOffset+24], dtype=np.float32)[0]
                ChannelDefinition["SamplingRate"] = np.frombuffer(rawBytes[blockOffset+24:blockOffset+28], dtype=np.float32)[0] * 1000
                ChannelDefinition["BlockSize"] = np.frombuffer(rawBytes[blockOffset+28:blockOffset+30], dtype=np.int16)[0]
                ChannelDefinition["Shape"] = np.frombuffer(rawBytes[blockOffset+30:blockOffset+32], dtype=np.int16)[0]
                
                # Continuous Analog Channel
                if ChannelDefinition["Mode"] == 0:
                    ChannelDefinition["SampleValues"] = np.zeros((int(ChannelDataLength[ChannelDefinition["ChannelID"]])),dtype=np.int16)
                    ChannelDefinition["Duration"] = np.frombuffer(rawBytes[blockOffset+32:blockOffset+36], dtype=np.float32)[0]
                    ChannelDefinition["TotalGain"] = np.frombuffer(rawBytes[blockOffset+36:blockOffset+38], dtype=np.int16)[0]
                    ChannelDefinition["ChannelName"] = rawBytes[blockOffset+38:blockOffset+blockLength].rsplit(b'\x00')[0].decode("utf-8")
                
                # Segmented Analog Channel
                elif ChannelDefinition["Mode"] == 1:
                    ChannelDefinition["Trigger"] = dict()
                    ChannelDefinition["Trigger"]["TimeRange"] = np.frombuffer(rawBytes[blockOffset+32:blockOffset+40], dtype=np.float32)
                    ChannelDefinition["Trigger"]["Level"] = np.frombuffer(rawBytes[blockOffset+40:blockOffset+42], dtype=np.int16)[0]
                    ChannelDefinition["Trigger"]["Mode"] = np.frombuffer(rawBytes[blockOffset+42:blockOffset+44], dtype=np.int16)[0]
                    ChannelDefinition["Trigger"]["isRMS"] = np.frombuffer(rawBytes[blockOffset+44:blockOffset+46], dtype=np.int16)[0] == 1
                    ChannelDefinition["TotalGain"] = np.frombuffer(rawBytes[blockOffset+46:blockOffset+48], dtype=np.int16)[0]
                    ChannelDefinition["ChannelName"] = rawBytes[blockOffset+48:blockOffset+blockLength].rsplit(b'\x00')[0].decode("utf-8")
                
                # Older MPX version contain other modes
                else:
                    ChannelDefinition["ChannelName"] = f"Unknown_{ChannelDefinition['ChannelID']}"
                    
            # Digital Channel
            else:
                ChannelDefinition["SampleValues"] = np.zeros((int(ChannelDataLength[ChannelDefinition["ChannelID"]]),2),dtype=np.uint32)
                ChannelDefinition["SamplingRate"] = np.frombuffer(rawBytes[blockOffset+18:blockOffset+22], dtype=np.float32)[0] * 1000
                ChannelDefinition["SaveTrigger"] = np.frombuffer(rawBytes[blockOffset+22:blockOffset+24], dtype=np.int16)[0]
                ChannelDefinition["Duration"] = np.frombuffer(rawBytes[blockOffset+24:blockOffset+28], dtype=np.float32)[0]
                ChannelDefinition["PreviousState"] = np.frombuffer(rawBytes[blockOffset+28:blockOffset+30], dtype=np.int16)[0]
                ChannelDefinition["ChannelName"] = rawBytes[blockOffset+30:blockOffset+blockLength].rsplit(b'\x00')[0].decode("utf-8")
            
            ChannelNameMap[ChannelDefinition["ChannelID"]] = ChannelDefinition["ChannelName"]
            Content["Data"][ChannelDefinition["ChannelID"]] = ChannelDefinition 
    
    for item in ChannelDataLength.keys():
        if not item in Content["Data"].keys():
            ChannelDefinition = dict()
            ChannelDefinition["ChannelID"] = item
            ChannelDefinition["isAnalog"] = False
            ChannelDefinition["Mode"] = -1
            ChannelDefinition["SampleValues"] = np.zeros((int(ChannelDataLength[ChannelDefinition["ChannelID"]]),2),dtype=np.uint32)
            Content["Data"][item] = ChannelDefinition 
        ChannelDataLength[item] = 0
        
    for blockOffset, blockLength in ChannelDataPackage:
        ChannelID = np.frombuffer(rawBytes[blockOffset+4:blockOffset+6], dtype=np.int16)[0]
    
        # Analog Data Structure
        if Content["Data"][ChannelID]["isAnalog"] and Content["Data"][ChannelID]["Mode"] == 0:
            chuck = slice(int(ChannelDataLength[ChannelID]), ChannelDataLength[ChannelID] + int((blockLength-10)/2))
            Content["Data"][ChannelID]["SampleValues"][chuck] = np.frombuffer(rawBytes[blockOffset+6:blockOffset+blockLength-4], dtype=np.int16)
            ChannelDataLength[ChannelID] += int((blockLength-10)/2)
            
        # Digital
        if not Content["Data"][ChannelID]["isAnalog"]:
            Content["Data"][ChannelID]["SampleValues"][int(ChannelDataLength[ChannelID]),0] = np.frombuffer(rawBytes[blockOffset+8:blockOffset+12], dtype=np.uint32)
            Content["Data"][ChannelID]["SampleValues"][int(ChannelDataLength[ChannelID]),1] = np.frombuffer(rawBytes[blockOffset+6:blockOffset+8], dtype=np.uint16)
            ChannelDataLength[ChannelID] += 1
    
    
    return Content

def extractAlphaOmegaRecordings(rawBytes):
    MPXData = decodeMPX(rawBytes)
    SamplingRates = np.unique([MPXData["Data"][chan_id]["SamplingRate"] for chan_id in MPXData["Data"].keys() if "SamplingRate" in MPXData["Data"][chan_id].keys()])

    MPXRecordingList = []
    for fs in SamplingRates:
        Data = {"ChannelNames": []}
        Data["Data"] = []
        for chan_id in MPXData["Data"].keys():
            if "SamplingRate" in MPXData["Data"][chan_id].keys():
                if MPXData["Data"][chan_id]["SamplingRate"] == fs and "SampleValues" in MPXData["Data"][chan_id].keys():
                    Data["Data"].append(MPXData["Data"][chan_id]["SampleValues"])
                    Data["ChannelNames"].append(MPXData["Data"][chan_id]["ChannelName"])
                    Data["Duration"] = len(MPXData["Data"][chan_id]["SampleValues"]) / float(fs)
                    Data["Time"] = np.arange(len(MPXData["Data"][chan_id]["SampleValues"])) / float(fs)
        Data["Data"] = np.array(Data["Data"]).T
        Data["SamplingRate"] = float(fs)
        Data["StartTime"] = MPXData["Header"]["SessionDateTime"].timestamp()
        Data["Missing"] = np.zeros(Data["Data"].shape)
        MPXRecordingList.append(Data)
    
    return MPXRecordingList