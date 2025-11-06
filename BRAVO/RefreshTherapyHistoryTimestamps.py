import os
import pickle, blosc2
import hashlib, hmac
from datetime import datetime

from BRAVO import wsgi 
from Server import models 
from modules import Database, DataCurator
from modules import Therapy as TherapyModule
from modules.MedtronicPercept import Percept, Therapy, Session

import json
import numpy as np
from cryptography.fernet import Fernet
DATABASE_PATH = os.environ.get('DATASERVER_PATH')
HASH_KEY = os.environ.get('DATASERVER_HASHKEY')
key = os.environ.get('DATASERVER_ENCRYPTION')
secureEncoder = Fernet(key)

User = models.PlatformUser.find(email="")
Participants = models.Participant.find_all(institute=User.institute)

for k in range(0, len(Participants)):
    participant = Participants[k]
    print(f"Processing Participant:", participant.uid)
    Sources = models.SourceFile.find_all(owner=participant, type="MedtronicJSON")
    for n in range(len(Sources)):
        session = Sources[n]
        try:
            pointer = session.pointer.replace("\\", os.path.sep).replace("/", os.path.sep)
            with open(pointer, "rb") as file:
                rawBytes = file.read()
            decompressed = blosc2.decompress2(rawBytes)
            rawBytes = secureEncoder.decrypt(decompressed)
            JSON = rawBytes.decode("utf-8")
            JSON = json.loads(JSON)
        except Exception as e:
            print("  Could not load session data.")
            print(e)
            continue

        PatientInformation = Session.extractPatientInformation(JSON)
        SessionDate = PatientInformation["SessionTimestamp"]
        if not (session.date == SessionDate):
            print("  Timestamps not correct, different:", str(session.date - SessionDate) + " seconds")
            session.date = SessionDate
            session.save()
            models.Therapy.find_all(source=session, type="Pre-visit Therapy").update(date=SessionDate)
            models.Therapy.find_all(source=session, type="Post-visit Therapy").update(date=SessionDate)
