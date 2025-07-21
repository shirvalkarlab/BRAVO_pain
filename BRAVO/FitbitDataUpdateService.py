from BRAVO import wsgi
from Server import models
from modules.Fitbit import DataManager, DataQuery

import datetime
import time
import numpy as np

while True:
    AllDevices = models.FitbitDevice.find_all()
    for device in AllDevices:
        Participant = device.owner
        DataManager.refreshFitbitData(device)

    time.sleep(300)