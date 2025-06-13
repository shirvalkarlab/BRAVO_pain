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
User-Level Authentication and Permission
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

from Server.models import PlatformUser, Institute
from django.contrib.auth.hashers import check_password

import re
def validateEmail(email):
    return re.fullmatch(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', email)

def registerUser(email, password, user_name="", institute="Independent"):
    if not validateEmail(email):
        raise Exception("Email Validation Failed")
    
    user = PlatformUser.include(email)
    if user:
        raise Exception("Email Already Used")

    user = PlatformUser.create(email, password, user_name)

    if not institute == "Independent":
        if not institute.has_permission(user):
            institute.join(user, "Member")
        user.institute = institute

    return user

def verifyUser(email, password):
    user = PlatformUser.find(email=email)
    if not user:
        raise Exception("Permission Denied")

    password_valid = check_password(password, user.password)
    if not password_valid:
        raise Exception("Permission Denied")

    return user

def newInstitute(user, name):
    if Institute.include(name):
        raise Exception("Institute Already Exists")

    institute = Institute.create(name)
    institute.join(user, "Admin")
    return institute

def addToInstitute(user, name, permitted_by):
    if Institute.include(name):
        raise Exception("Institute Already Exists")

    if not Institute.has_permission(name, permitted_by.uid):
        raise Exception("Permission Denied")

    institute = Institute.join(user, "Member")
    return institute

def removeFromInstitute(user, name, permitted_by):
    if Institute.include(name):
        raise Exception("Institute Already Exists")

    if not Institute.has_permission(name, permitted_by.uid):
        raise Exception("Permission Denied")

    return Institute.remove(name, user.uid)
