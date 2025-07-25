from Server import models
from modules import Database

def loadEmpaticaDataOverview(Participant):
    # Load Empatica data for the given participant
    recordings = models.Recording.find_all(type="EmpaticaData", source__owner=Participant)

    Overview = []
    for recording in recordings:
        Overview.append({
            "Id": recording.uid,
            "Name": recording.name,
            "Date": recording.date,
            "ChannelNames": recording.metadata["ChannelNames"],
        })

    return Overview

def loadEmpaticaData(Participant, channel_name):
    # Load Empatica data for the given participant and channel
    recordings = models.Recording.find_all(type="EmpaticaData", source__owner=Participant)

    Results = []
    for recording in recordings:
        if channel_name in recording.metadata["ChannelNames"]:
            EmpaticaData = Database.loadSourceFile(recording.pointer, recording.hashed)
            for i in range(len(EmpaticaData)):
                for j in range(len(EmpaticaData[i]["ChannelNames"])):
                    if EmpaticaData[i]["ChannelNames"][j] == channel_name:
                        Results.append({
                            "Id": recording.uid,
                            "Time": EmpaticaData[i]["Time"],
                            "Data": EmpaticaData[i]["Data"][:, j],
                            "ChannelName": channel_name,
                            "StartTime": EmpaticaData[i]["StartTime"],
                        })

    return Results