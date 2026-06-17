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

class SourceFile(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, unique=True, primary_key=True)
    name = models.CharField(max_length=512, default="")
    type = models.CharField(max_length=128, default="")
    date = models.FloatField(default=current_time)
    pointer = models.CharField(max_length=1024, default="")
    hashed = models.CharField(max_length=64, default="")
    metadata = models.JSONField(default=dict)
    # Indexed mirror of metadata["UniqueHashed"] (HMAC-SHA256 of the raw upload bytes). The duplicate
    # check filters on this; querying it via the JSON field (metadata__UniqueHashed) forces a
    # full-table JSON-extract scan on MySQL that grows with every stored file, so the dedup query got
    # slower the more uploads existed. A plain indexed CharField makes that lookup an index seek.
    unique_hashed = models.CharField(max_length=64, default="", db_index=True)

    owner = models.ForeignKey('Participant', models.CASCADE, null=True)
    
    def include(*args, **kwargs):
        return SourceFile.objects.filter(**kwargs).exists()

    def find(*args, **kwargs):
        return SourceFile.objects.filter(**kwargs).first()

    def find_all(*args, **kwargs):
        return SourceFile.objects.filter(**kwargs).all()

    def create(*args, **kwargs):
        file = SourceFile(**kwargs)
        file.save()
        return file
    
    def has_permission(self, user):
        return self.owner == user

    def purge(*args, **kwargs):
        return SourceFile.objects.filter(**kwargs).delete()
    
    def purge_cache():
        return SourceFile.objects.filter(type="CachedResult").delete()
    
    def get_info(self):
        return {
            "Id": self.uid,
            "Name": self.name,
            "Type": self.type,
            "Date": self.date,
            "Metadata": self.metadata
        }
    
@receiver(pre_delete, sender=SourceFile)
def on_sourcefile_delete(sender, instance, **kwargs):
    if len(instance.pointer) > 0:
        get_or_none(deleteSourceFile)(instance.pointer)
        get_or_none(os.remove)(instance.pointer + ".lock")