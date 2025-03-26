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
Percept Session JSON Processor
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os 
import json 

from modules import Database
from modules.MedtronicPercept import BrainSenseEvent, BrainSenseStream, BrainSenseSurvey, IndefiniteStream, ChronicBrainSense, Therapy, Percept
from modules.HelperFunctions import current_time, get_or_none

key = os.environ.get('DATASERVER_ENCRYPTION')

def extractPatientInformation(JSON):
    PatientOverview = {}
    PatientOverview["SessionTimestamp"] = Percept.estimateSessionDateTime(JSON)
    PatientOverview["SessionTimezone"] = "UTC" + JSON["ProgrammerUtcOffset"]

    PatientInformation = JSON["PatientInformation"]["Final"]
    PatientOverview["Name"] = PatientInformation["PatientFirstName"] + " " + PatientInformation["PatientLastName"]
    PatientOverview["MRN"] = PatientInformation["PatientId"]
    
    if PatientInformation["Diagnosis"] == "DiagnosisTypeDef.ParkinsonsDisease":
        PatientOverview["Diagnosis"] = "Parkinson's Disease"
    elif PatientInformation["Diagnosis"] == "DiagnosisTypeDef.EssentialTremor":
        PatientOverview["Diagnosis"] = "Essential Tremor"
    else:
        PatientOverview["Diagnosis"] = PatientInformation["Diagnosis"].replace("DiagnosisTypeDef.","")

    if PatientInformation["PatientGender"] == "PatientGenderDef.MALE":
        PatientOverview["Sex"] = "Male"
    elif PatientInformation["PatientGender"] == "PatientGenderDef.FEMALE":
        PatientOverview["Sex"] = "Female"
    else:
        PatientOverview["Sex"] = "Unknown"

    # Patient Date of Birth does not exist for non-Percept Device
    PatientOverview["DOB"] = 0
    if "PatientDateOfBirth" in PatientInformation.keys():
        if not PatientInformation["PatientDateOfBirth"] == "":
            PatientOverview["DOB"] = Percept.getTimestamp(PatientInformation["PatientDateOfBirth"])
    
    
    DeviceInformation = JSON["DeviceInformation"]["Final"]
    PatientOverview["Device"] = {}
    PatientOverview["Device"]["Type"] = DeviceInformation["Neurostimulator"]
    PatientOverview["Device"]["Name"] = DeviceInformation["DeviceName"] if "DeviceName" in DeviceInformation.keys() else ""
    PatientOverview["Device"]["SerialNumber"] = DeviceInformation["NeurostimulatorSerialNumber"]
    PatientOverview["Device"]["BatteryPercent"] = -1
    PatientOverview["Device"]["EOL"] = 0

    try:
        if "BatteryPercentage" in JSON["BatteryInformation"].keys():
            JSON["BatteryInformation"]["BatteryPercentage"]

        if "EstimatedBatteryLifeMonths" in JSON["BatteryInformation"].keys():
            PatientOverview["Device"]["EOL"] = PatientOverview["SessionTimestamp"] + int(JSON["BatteryInformation"]["EstimatedBatteryLifeMonths"])*30*3600
        elif "ERIDate" in JSON["BatteryInformation"].keys():
            PatientOverview["Device"]["EOL"] = Percept.getTimestamp(JSON["BatteryInformation"]["ERIDate"])
        
    except:
        pass
    
    if DeviceInformation["NeurostimulatorLocation"] == "InsLocation.CHEST_RIGHT":
        PatientOverview["Device"]["Location"] = "Right IPG"
    elif DeviceInformation["NeurostimulatorLocation"] == "InsLocation.CHEST_LEFT":
        PatientOverview["Device"]["Location"] = "Left IPG"
    else:
        PatientOverview["Device"]["Location"] = DeviceInformation["NeurostimulatorLocation"].replace("InsLocation.", "")

    PatientOverview["Device"]["ImplantDate"] = Percept.getTimestamp(DeviceInformation["ImplantDate"])
    PatientOverview["Device"]["ConnectedLeads"] = []

    LeadInformation = JSON["LeadConfiguration"]["Final"]
    for lead in LeadInformation:
        TargetLocation = lead["Hemisphere"].replace("HemisphereLocationDef.","") + " "
        if lead["LeadLocation"] == "LeadLocationDef.Vim":
            TargetLocation += "VIM"
        elif lead["LeadLocation"] == "LeadLocationDef.Stn":
            TargetLocation += "STN"
        elif lead["LeadLocation"] == "LeadLocationDef.Gpi":
            TargetLocation += "GPi"
        else:
            TargetLocation += lead["LeadLocation"].replace("LeadLocationDef.","")

        electrode = {
            "name": TargetLocation,
            "custom_name": TargetLocation,
        }
        if lead["ElectrodeNumber"] == "InsPort.ZERO_THREE" or lead["ElectrodeNumber"] == "InsPort.EIGHT_ELEVEN":
            electrode["channel_count"] = 4
        elif lead["ElectrodeNumber"] == "InsPort.ZERO_SEVEN" or lead["ElectrodeNumber"] == "InsPort.EIGHT_FIFTEEN":
            electrode["channel_count"] = 8
        
        if lead["Model"] == "LeadModelDef.LEAD_B33015":
            electrode["type"] = "SenSight B33015"
            electrode["channel_names"] = ["E00","E01-A","E01-B","E01-C","E02-A","E02-B","E02-C","E03"]
        elif lead["Model"] == "LeadModelDef.LEAD_B33005":
            electrode["type"] = "SenSight B33005"
            electrode["channel_names"] = ["E00","E01-A","E01-B","E01-C","E02-A","E02-B","E02-C","E03"]
        elif lead["Model"] == "LeadModelDef.LEAD_3387":
            electrode["type"] = "Medtronic 3387"
            electrode["channel_names"] = ["E00","E01","E02","E03"]
        elif lead["Model"] == "LeadModelDef.LEAD_3389":
            electrode["type"] = "Medtronic 3389"
            electrode["channel_names"] = ["E00","E01","E02","E03"]
        elif lead["Model"] == "LeadModelDef.LEAD_OTHER":
            electrode["type"] = "Other"
            electrode["channel_names"] = ["Contact-"+str(i) for i in range(electrode["channel_count"])]
        else:
            electrode["type"] = lead["Model"].replace("LeadModelDef.","")
            electrode["channel_names"] = ["Contact-"+str(i) for i in range(electrode["channel_count"])]

        PatientOverview["Device"]["ConnectedLeads"].append(electrode)

    return PatientOverview

def decodeMedtronicJSON(JSON):
    Data = get_or_none(Percept.extractPerceptJSON)(JSON)
    if not Data:
        raise Exception("Medtronic Percept Content Extraction Error")
    
    # TODO: Handle Process Failure

    # Extract Device/Patient Info
    SessionOverview = extractPatientInformation(JSON)

    # Extract Therapy 
    Therapies = []
    if "StimulationGroups" in Data.keys():
        Therapies += [{**therapy, **{
            "name": "",
            "type": "Post-visit Therapy",
            "date": SessionOverview["SessionTimestamp"],
        }} for therapy in Therapy.extractTherapySettings(Data["StimulationGroups"])]

    if "PreviousGroups" in Data.keys():
        Therapies += [{**therapy, **{
            "name": "",
            "type": "Pre-visit Therapy",
            "date": SessionOverview["SessionTimestamp"],
        }} for therapy in Therapy.extractTherapySettings(Data["PreviousGroups"])]
    
    if "TherapyHistory" in Data.keys():
        for i in range(len(Data["TherapyHistory"])):
            Therapies += [{**therapy, **{
                "name": "",
                "type": "Past Therapy",
                "date": Percept.getTimestamp(Data["TherapyHistory"][i]["DateTime"]),
            }} for therapy in Therapy.extractTherapySettings(Data["TherapyHistory"][i]["Therapy"])]

    # Extract Therapy Change History
    TherapyChangeHistory = []
    if "TherapyChangeHistory" in Data.keys():
        TherapyChangeHistory = Therapy.saveTherapyEvents(Data["TherapyChangeHistory"])
    
    # Process BrainSense Survey
    SurveyRecordings = []
    if "ElectrodeIdentifierTD" in Data.keys():
        SurveyRecordings += [{
            "name": "",
            "type": "MedtronicElectrodeIdentifier",
            "date": Recording["StartTime"],
            "recording": Recording,
            "metadata": {
                "ChannelNames": Recording["ChannelNames"],
                "Duration": Recording["Duration"],
            }
        } for Recording in BrainSenseSurvey.saveBrainSenseSurvey(Data["ElectrodeIdentifierTD"])]

    if "MontagesTD" in Data.keys():
        SurveyRecordings += [{
            "name": "",
            "type": "MedtronicBrainSenseSurvey",
            "date": Recording["StartTime"],
            "recording": Recording,
            "metadata": {
                "ChannelNames": Recording["ChannelNames"],
                "Duration": Recording["Duration"],
            }
        } for Recording in BrainSenseSurvey.saveBrainSenseSurvey(Data["MontagesTD"])]

    if "BaselineTD" in Data.keys():
        SurveyRecordings += [{
            "name": "",
            "type": "MedtronicBaselineMontages",
            "date": Recording["StartTime"],
            "recording": Recording,
            "metadata": {
                "ChannelNames": Recording["ChannelNames"],
                "Duration": Recording["Duration"],
            }
        } for Recording in BrainSenseSurvey.saveBrainSenseSurvey(Data["BaselineTD"])]
    
    if "StimulationTD" in Data.keys():
        SurveyRecordings += [{
            "name": "",
            "type": "MedtronicStimulationMontages",
            "date": Recording["StartTime"],
            "recording": Recording,
            "metadata": {
                "ChannelNames": Recording["ChannelNames"],
                "Duration": Recording["Duration"],
            }
        } for Recording in BrainSenseSurvey.saveBrainSenseSurvey(Data["StimulationTD"])]

    # Process Montage Streams
    StreamingRecordings = []
    if "IndefiniteStream" in Data.keys():
        StreamingRecordings += [{
            "name": "",
            "type": "MedtronicIndefiniteStream",
            "date": Recording["StartTime"],
            "recording": Recording,
            "metadata": {
                "ChannelNames": Recording["ChannelNames"],
                "Duration": Recording["Duration"],
            }
        } for Recording in IndefiniteStream.saveIndefiniteStreams(Data["IndefiniteStream"])]
        
    # Process BrainSense Streams
    TimeDomainRecordings = []
    PowerDomainRecordings = []
    if "StreamingTD" in Data.keys() and "StreamingPower" in Data.keys():
        TimeDomainRecordings, PowerDomainRecordings = BrainSenseStream.saveBrainSenseStreams(Data["StreamingTD"], Data["StreamingPower"], FixBreaking=JSON["AutomaticStreamingFix"])
        StreamingRecordings += [{
            "name": "",
            "type": "MedtronicBrainSenseTimeDomain",
            "date": Recording["StartTime"],
            "recording": Recording,
            "metadata": {
                "ChannelNames": Recording["ChannelNames"],
                "Duration": Recording["Duration"],
            }
        } for Recording in TimeDomainRecordings]
        StreamingRecordings += [{
            "name": "",
            "type": "MedtronicBrainSensePowerDomain",
            "date": Recording["StartTime"],
            "recording": Recording,
            "metadata": {
                "ChannelNames": Recording["ChannelNames"],
                "Duration": Recording["Duration"],
                "Therapy": Recording["Descriptor"]["Therapy"],
            }
        } for Recording in PowerDomainRecordings]

    # Stiore Chronic BrainSenses
    ChronicRecordings = []
    if "LFPTrends" in Data.keys():
        ChronicRecordings += [{
            "name": "",
            "type": "MedtronicChronicBrainSense",
            "date": Recording["StartTime"],
            "recording": Recording,
            "metadata": {
                "ChannelNames": Recording["ChannelNames"],
            }
        } for Recording in ChronicBrainSense.saveChronicBrainSense(Data["LFPTrends"])]
    
    EventRecordings = []
    if "PatientEventLogs" in Data.keys():
        EventRecordings = BrainSenseEvent.saveBrainSenseEvents(Data["PatientEventLogs"])
    
    if "Impedance" in Data.keys():
        for impedanceData in Data["Impedance"]:
            EventRecordings.append({
                "name": "",
                "type": "MedtronicDeviceImpedance",
                "date": SessionOverview["SessionTimestamp"],
                "metadata": {"device": ""},
                "data": impedanceData
            })

    return {
        "SessionOverview": SessionOverview,
        "Therapies": Therapies,
        "TherapyChangeHistory": TherapyChangeHistory,
        "SurveyRecordings": SurveyRecordings,
        "StreamingRecordings": StreamingRecordings,
        "ChronicRecordings": ChronicRecordings,
        "EventRecordings": EventRecordings
    }