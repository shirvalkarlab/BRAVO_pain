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
import numpy as np
import json

from modules.HelperFunctions import current_time, get_token, uuid4_hex

class TherapyModification(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, unique=True, primary_key=True)
    name = models.CharField(max_length=128, default="")
    type = models.CharField(max_length=128, default="")
    date = models.FloatField(default=current_time)

    previous_state = models.CharField(max_length=128, default="")
    new_state = models.CharField(max_length=128, default="")

    owner = models.ForeignKey('Participant', models.CASCADE)
    source = models.ForeignKey('SourceFile', models.CASCADE, null=True)

    def include(*args, **kwargs):
        return TherapyModification.objects.select_related("source").filter(**kwargs).exists()

    def find_all(*args, **kwargs):
        return TherapyModification.objects.select_related("source").filter(**kwargs).order_by("date").all()
    
    def get_info(self):
        return {
            "Id": self.uid,
            "Name": self.name,
            "Type": self.type,
            "Date": self.date,
            "Previous": self.previous_state,
            "New": self.new_state,
        }

class Annotation(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, unique=True, primary_key=True)
    name = models.CharField(max_length=128, default="")
    type = models.CharField(max_length=128, default="")
    date = models.FloatField(default=current_time)
    duration = models.FloatField(default=0)

    owner = models.ForeignKey('Participant', models.CASCADE)
    source = models.ForeignKey('SourceFile', models.CASCADE, null=True)
    
    def include(*args, **kwargs):
        return Annotation.objects.select_related("owner").filter(**kwargs).exists()

    def find(*args, **kwargs):
        return Annotation.objects.select_related("owner").filter(**kwargs).first()
    
    def find_all(*args, **kwargs):
        return Annotation.objects.select_related("owner").filter(**kwargs).order_by("date").all()
    
    def get_info(self):
        return {
            "Id": self.uid,
            "Name": self.name,
            "Type": self.type,
            "Date": self.date,
            "Duration": self.duration,
        }

    
class DBSEvent(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, unique=True, primary_key=True)
    name = models.CharField(max_length=128, default="")
    type = models.CharField(max_length=128, default="")
    date = models.FloatField(default=current_time)

    source = models.ForeignKey('SourceFile', models.CASCADE)
    
    data = models.ManyToManyField("Recording", related_name="has_data")

    def include(*args, **kwargs):
        return DBSEvent.objects.select_related("source").filter(**kwargs).exists()

    def find(*args, **kwargs):
        return DBSEvent.objects.select_related("source").filter(**kwargs).first()
    
    def find_all(*args, **kwargs):
        return DBSEvent.objects.select_related("source").filter(**kwargs).order_by("date").all()
    
    def get_info(self, data=False):
        return {
            "Id": self.uid,
            "Name": self.name,
            "Type": self.type,
            "Date": self.date,
            "Recording": [data.get_info() for data in self.data.all()] if data else []
        }

class ScaleForms(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, unique=True, primary_key=True)
    name = models.CharField(max_length=128, default="")
    date = models.FloatField(default=current_time)
    institute = models.ForeignKey("Institute", models.CASCADE, null=True)

    short_link = models.CharField(max_length=128, default=get_token)
    record = models.JSONField(default=list)
    record_type = models.CharField(max_length=128, default="")
    record_version = models.IntegerField(default=0)

    def include(*args, **kwargs):
        return ScaleForms.objects.select_related("institute").filter(**kwargs).exists()

    def find(*args, **kwargs):
        return ScaleForms.objects.select_related("institute").order_by("-record_version").filter(**kwargs).first()
    
    def find_all(*args, **kwargs):
        return ScaleForms.objects.select_related("institute").order_by("-record_version").filter(**kwargs).all()
    
    def create(institute, name, type):
        if ScaleForms.include(institute=institute, name=name):
            raise Exception("Form Existed")

        token = get_token(8)
        while ScaleForms.include(short_link=token):
            token = get_token(8)

        form = ScaleForms(name=name, institute=institute, short_link=token, record_type=type, record_version=1)
        form.save()
        return form

    def update_version(self, record):
        if json.dumps(record) == json.dumps(self.record):
            return self

        if ScaleRecord.include(source=self):
            form = ScaleForms(name=self.name, institute=self.institute, short_link=self.short_link, record=record, record_type=self.record_type, record_version=self.record_version+1)
            form.save()
            return form
        else:
            self.record = record
            self.record_version += 1
            self.save()
            return self

    def get_info(self, count=None):
        info = {
            "Id": self.uid,
            "Name": self.name,
            "Type": self.record_type,
            "Date": self.date,
            "Institute": self.institute.name,
            "ShortLink": self.short_link,
            "Record": self.record,
            "Version": self.record_version,
        }
        if count:
            info["Count"] = ScaleRecord.objects.filter(source=self, participant=count).count()

        if self.record_type == "Redcap Linked Survey":
            info["Record"] = info["Record"].get("FieldMapping", [])

        return info

class ParticipantLinkRel(models.Model):
    participant = models.ForeignKey("Participant", on_delete=models.CASCADE)
    record = models.ForeignKey("ScaleForms", on_delete=models.CASCADE)
    link_code = models.CharField(max_length=128, default="")

    def include(*args, **kwargs):
        return ParticipantLinkRel.objects.select_related("participant", "record").filter(**kwargs).exists()

    def find(*args, **kwargs):
        return ParticipantLinkRel.objects.select_related("participant", "record").filter(**kwargs).first()
    
    def find_all(*args, **kwargs):
        return ParticipantLinkRel.objects.select_related("participant", "record").filter(**kwargs).all()
    
    def create(participant, form):
        if ParticipantLinkRel.include(participant=participant, record=form):
            raise Exception("Link Existed")

        token = get_token(64)
        while ParticipantLinkRel.include(link_code=token):
            token = get_token(64)

        link = ParticipantLinkRel(participant=participant, record=form, link_code=token)
        link.save()
        return link

    def get_info(self):
        return {
            "Id": self.link_code,
            "FormURL": self.record.short_link,
            "FormId": self.record.uid,
            "Participant": self.participant.uid 
        }
        
class ScaleRecord(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, unique=True, primary_key=True)
    name = models.CharField(max_length=128, default="")
    date = models.FloatField(default=current_time)
    source = models.ForeignKey('ScaleForms', models.CASCADE)

    participant = models.ForeignKey('Participant', models.CASCADE)
    record = models.JSONField(default=dict)

    def include(*args, **kwargs):
        return ScaleRecord.objects.select_related("source").filter(**kwargs).exists()

    def find(*args, **kwargs):
        return ScaleRecord.objects.select_related("source").filter(**kwargs).first()
    
    def find_all(*args, **kwargs):
        return ScaleRecord.objects.select_related("source").filter(**kwargs).all()
    
    def create(participant, form, result, date=None):
        record = ScaleRecord(participant=participant, source=form, record=result)
        if date:
            record.date = date
        record.save()
        return record

    def get_info(self):
        return {
            "Id": self.uid,
            "Name": self.name,
            "Date": self.date,
            "Result": self.record,
        }
        