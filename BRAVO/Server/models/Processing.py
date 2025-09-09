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
SQL Table Definitions
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
import json
import datetime
from cryptography.fernet import Fernet

from modules.Database import deleteSourceFile
from modules.HelperFunctions import current_time, get_token, get_or_none, uuid4_hex

DATABASE_PATH = os.environ.get('DATASERVER_PATH')
BRAVO_Path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SLURM_JOB_PATH = os.path.join(BRAVO_Path, "modules", "AsyncJobScheduler")

class AsyncJob(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, unique=True, primary_key=True)
    name = models.CharField(max_length=512, default="")
    type = models.CharField(max_length=128, default="")
    date = models.FloatField(default=current_time)
    metadata = models.JSONField(default=dict)

    recording_uid = models.CharField(max_length=32, default="", blank=True)
    state = models.CharField(max_length=32, default="Pending")  # Pending, Running, Completed, Failed
    result_message = models.CharField(max_length=1024, default="", blank=True)

    requester = models.ForeignKey('PlatformUser', models.CASCADE, null=True)
    
    def include(*args, **kwargs):
        return AsyncJob.objects.filter(**kwargs).exists()

    def find(*args, **kwargs):
        return AsyncJob.objects.filter(**kwargs).first()

    def find_all(*args, **kwargs):
        return AsyncJob.objects.filter(**kwargs).all()

    def create(*args, **kwargs):
        file = AsyncJob(**kwargs)
        file.save()
        return file
    
    def has_permission(self, user):
        return self.owner == user

    def purge(*args, **kwargs):
        return AsyncJob.objects.filter(**kwargs).delete()
    
    def get_info(self):
        return {
            "Id": self.uid,
            "Name": self.name,
            "Type": self.type,
            "Date": self.date,
            "Metadata": self.metadata,
            "State": self.state,
            "Result": self.result_message
        }
    
@receiver(pre_delete, sender=AsyncJob)
def on_asyncjob_delete(sender, instance, **kwargs):
    print(SLURM_JOB_PATH)
    get_or_none(os.remove)(os.path.join(SLURM_JOB_PATH, instance.uid + ".sh"))