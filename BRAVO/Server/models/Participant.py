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

from django.db import models
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
import json
import datetime

from modules.HelperFunctions import current_time, get_token, uuid4_hex

def newToken():
    return get_token(64)

def newVerification():
    return get_token(16)

class Participant(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, unique=True, primary_key=True)
    name = models.CharField(max_length=512, default="")
    date_of_birth = models.FloatField(default=0)
    sex = models.CharField(max_length=32, default="Unknown")
    
    mrn = models.CharField(max_length=128, default="")
    diagnosis = models.CharField(max_length=128, default="Unknown")
    disease_start_time = models.FloatField(default=0)
    
    tags = models.ManyToManyField("Tag", related_name="has_tag")
    institute = models.ForeignKey('Institute', models.CASCADE, null=True)

    last_update = models.FloatField(default=current_time)
    
    original = models.ForeignKey('Participant', models.CASCADE, null=True)

    def include(*args, **kwargs):
        return Participant.objects.filter(**kwargs).exists()

    def find(*args, **kwargs):
        return Participant.objects.filter(**kwargs).first()

    def create(*args, **kwargs):
        return Participant(**kwargs)

    def find_or_create(name, mrn, institute):
        person = Participant.objects.filter(mrn=mrn, institute_id=institute).first()
        if person and len(mrn) > 0:
            return person, False
        
        person = Participant.objects.filter(name=name, institute_id=institute).first()
        if person:
            return person, False
        
        person = Participant(name=name, mrn=mrn, institute_id=institute)
        person.save()
        return person, True
    
    def from_institute(institute):
        return Participant.objects.filter(institute=institute).all()
    
    def get_info(self):
        return {
            "Id": self.uid,
            "Name": self.name,
            "DOB": self.date_of_birth,
            "Sex": self.sex,
            "MRN": self.mrn,
            "Diagnosis": self.diagnosis,
            "LastModified": self.last_update,
            "Tags": [i.name for i in self.tags.all()],
        }

class Tag(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, primary_key=True)
    name = models.CharField(max_length=512, default="")
    
    owner = models.ForeignKey('PlatformUser', models.CASCADE)

    def find_or_create(name, owner):
        tag = Tag.objects.filter(name=name, owner=owner).first()
        if tag:
            return tag, False
    
        tag = Tag(name=name, owner=owner)
        tag.save()
        return tag, True
