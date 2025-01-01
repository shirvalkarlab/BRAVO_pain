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

class PlatformUserManager(BaseUserManager):
    def create_user(self, email, password=None, user_name=""):
        if not email or not password:
            raise Exception("Email or Password Missing")
        user = self.model(email=self.normalize_email(email), user_name=user_name)
        user.set_password(password)
        user.save()
        return user

class PlatformUser(AbstractBaseUser):
    USERNAME_FIELD = "email"
    objects = PlatformUserManager()

    uid = models.CharField(max_length=32, default=uuid4_hex, primary_key=True)
    email = models.CharField(max_length=255, unique=True)
    user_name = models.CharField(max_length=255, default="")
    institute = models.ForeignKey("Institute", models.SET_NULL, null=True)

    register_date = models.FloatField(default=current_time)
    configuration = models.JSONField(default=dict)

    api_token = models.CharField(max_length=64, default=newToken)
    verification_code = models.CharField(max_length=16, default=newVerification)

    is_active = models.IntegerField(default=1)
    is_mobile = models.IntegerField(default=0)
    is_admin = models.IntegerField(default=0)

    def find(email):
        return PlatformUser.objects.filter(email=email).first()
    
    def include(email):
        return PlatformUser.objects.filter(email=email).exists()

    def create(email, password, user_name):
        user = PlatformUser.objects.create_user(email=email, password=password, user_name=user_name)
        institute = Institute.create(email)
        user.institute = institute
        user.save()
        institute.members.add(user)
        return user
    
    def get_info(self):
        return {"Email": self.email, "Name": self.user_name, "Institute": self.institute.name if self.institute else "", "InstituteId": self.institute.uid if self.institute else ""}

class Institute(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, primary_key=True)
    name = models.CharField(max_length=512, default="")
    members = models.ManyToManyField("PlatformUser", related_name="institute_has_member")

    def include(*args, **kwargs):
        return Institute.objects.filter(**kwargs).exists()

    def find(*args, **kwargs):
        return Institute.objects.filter(**kwargs).first()

    def find_all(*args, **kwargs):
        return Institute.objects.filter(**kwargs).all()

    def create(name):
        if Institute.objects.filter(name=name).exists():
            return None
        
        uid = uuid4_hex()
        while Institute.objects.filter(uid=uid).exists() or Study.objects.filter(uid=uid).exists():
            uid = uuid4_hex()
            
        institute = Institute(uid=uid, name=name)
        institute.save()
        return institute

    def join(self, user):
        self.members.add(user)

    def leave(self, user):
        self.members.remove(user)

    def has_permission(self, user):
        return self.members.filter(uid=user.uid).exists()
    
class Study(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, primary_key=True)
    name = models.CharField(max_length=512, default="")
    
    members = models.ManyToManyField("PlatformUser", related_name="study_has_member")
    participants = models.ManyToManyField("Participant", related_name="has_participant")

    def include(*args, **kwargs):
        return Study.objects.prefetch_related("members", "participants").filter(**kwargs).exists()

    def find(*args, **kwargs):
        return Study.objects.prefetch_related("members", "participants").filter(**kwargs).first()

    def has_permission(self, user):
        return self.members.filter(uid=user.uid).exists()
    
    def create(name):
        if Study.objects.filter(name=name).exists():
            return None
        
        uid = uuid4_hex()
        while Institute.objects.filter(uid=uid).exists() or Study.objects.filter(uid=uid).exists():
            uid = uuid4_hex()
            
        study = Study(uid=uid, name=name)
        study.save()
        return study
