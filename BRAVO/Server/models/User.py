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

from modules.HelperFunctions import current_time, get_token, uuid4_hex, get_permission

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

    api_token = models.CharField(max_length=128, default=newToken)
    verification_code = models.CharField(max_length=16, default=newVerification)

    is_active = models.IntegerField(default=1)
    is_mobile = models.IntegerField(default=0)
    is_admin = models.IntegerField(default=0)

    def find(email=None, api_token=None):
        if email:
            return PlatformUser.objects.filter(email=email).first()
        if api_token:
            return PlatformUser.objects.filter(api_token=api_token).first()
    
    def include(email):
        return PlatformUser.objects.filter(email=email).exists()

    def create(email, password, user_name):
        user = PlatformUser.objects.create_user(email=email, password=password, user_name=user_name)
        institute = Institute.create(email)
        user.institute = institute
        user.save()
        institute.members.add(user)
        rel = InstituteRel.find(member=user, institute=institute)
        rel.permission = {
            "Position": "Admin"
        }
        rel.save()
        return user
    
    def get_info(self):
        Studies = [study.get_info(self) for study in Study.find_all(members=self)]
        info = {"Email": self.email, "Name": self.user_name, 
                "Institute": self.institute.name if self.institute else "", "InstituteId": self.institute.uid if self.institute else "", 
                "Studies": Studies, "StudyName": "Disabled", "StudyId": ""}
        
        if "ActiveStudy" in self.configuration.keys():
            study = Study.find(uid=self.configuration["ActiveStudy"], members=self)
            if study:
                info["StudyName"] = study.name
                info["StudyId"] = study.uid
        
        return info

class InstituteRel(models.Model):
    institute = models.ForeignKey("Institute", on_delete=models.CASCADE)
    member = models.ForeignKey("PlatformUser", on_delete=models.CASCADE)
    permission = models.JSONField(default=dict)

    def find(*args, **kwargs):
        return InstituteRel.objects.prefetch_related("institute", "member").filter(**kwargs).first()

    def get_info(self):
        return {
            "Institute": self.institute.uid,
            "Member": self.member.uid,
            "Permission": self.permission
        }

class Institute(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, primary_key=True)
    invite_code = models.CharField(max_length=512, default="")
    name = models.CharField(max_length=512, default="")
    members = models.ManyToManyField("PlatformUser", related_name="institute_has_member", through="InstituteRel")

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

    def join(self, user, permission):
        rel = InstituteRel(institute=self, member=user, permission={
            "Position": permission
        })
        rel.save()

    def leave(self, user):
        self.members.remove(user)

    def has_permission(self, user, type="View"):
        if type == "View":
            return self.members.filter(uid=user.uid).exists()
        else:
            rel = InstituteRel.find(institute=self, member=user)
            return get_permission(rel.permission, type)

class StudyRel(models.Model):
    study = models.ForeignKey("Study", on_delete=models.CASCADE)
    member = models.ForeignKey("PlatformUser", on_delete=models.CASCADE)
    permission = models.JSONField(default=dict)

    def find(*args, **kwargs):
        return StudyRel.objects.prefetch_related("study", "member").filter(**kwargs).first()

    def create(*args, **kwargs):
        return StudyRel(**kwargs)

    def get_info(self):
        return {
            "Study": self.study.uid,
            "Member": self.member.uid,
            "Permission": self.permission
        }
    
class StudyDataRel(models.Model):
    study = models.ForeignKey("Study", on_delete=models.CASCADE)
    participant = models.ForeignKey("Participant", on_delete=models.CASCADE)
    permission = models.JSONField(default=dict)

    def find(*args, **kwargs):
        return StudyDataRel.objects.prefetch_related("study", "participant").filter(**kwargs).first()

    def create(*args, **kwargs):
        return StudyDataRel(**kwargs)

    def get_info(self):
        return {
            "Study": self.study.uid,
            "Participant": self.participant.uid,
            "Permission": self.permission
        }
    
class Study(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, primary_key=True)
    name = models.CharField(max_length=512, default="")
    
    invite_code = models.CharField(max_length=512, default="")
    members = models.ManyToManyField("PlatformUser", related_name="study_has_member", through="StudyRel")
    participants = models.ManyToManyField("Participant", related_name="has_participant", through="StudyDataRel")

    def include(*args, **kwargs):
        return Study.objects.prefetch_related("members", "participants").filter(**kwargs).exists()

    def find(*args, **kwargs):
        return Study.objects.prefetch_related("members", "participants").filter(**kwargs).first()

    def find_all(*args, **kwargs):
        return Study.objects.prefetch_related("members", "participants").filter(**kwargs).all()

    def has_permission(self, user):
        return self.members.filter(uid=user.uid).exists()
    
    def create(name):
        if Study.objects.filter(name=name).exists():
            return None
        
        uid = uuid4_hex()
        while Institute.objects.filter(uid=uid).exists() or Study.objects.filter(uid=uid).exists():
            uid = uuid4_hex()
            
        study = Study(uid=uid, name=name)
        study.invite_code = get_token(64)
        study.save()
        return study

    def get_info(self, user):
        rel = StudyRel.find(study=self, member=user)

        info = {
            "Id": self.uid, 
            "Name": self.name,
            "InviteCode": self.invite_code,
            "Permission": rel.permission["Position"],
            "Members": [{"Name": member.user_name, "Email": member.email} for member in self.members.all()],
            "Participants": []
        }

        for participant in self.participants.all():
            data_rel = StudyDataRel.find(study=self, participant=participant)
            info["Participants"].append({
                "Id": participant.uid, 
                "Name": participant.name if rel.permission["Position"] == "Admin" else participant.uid,
                "Permissions": data_rel.permission
            })
        
        return info

class BlacklistRecords(models.Model):
    uid = models.CharField(max_length=32, default=uuid4_hex, primary_key=True)
    name = models.CharField(max_length=512, default="")
    ip_address = models.CharField(max_length=32, default="")
    date = models.FloatField(default=current_time)
    reason = models.CharField(max_length=512, default="")
    
    def exists(*args, **kwargs):
        return BlacklistRecords.objects.filter(**kwargs).exists()
