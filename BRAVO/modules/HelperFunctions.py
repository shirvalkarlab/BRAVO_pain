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

import os
import traceback
import random, string
import datetime
import uuid
from cryptography.fernet import Fernet
import secrets
import hashlib, base64

key = os.environ.get('DATASERVER_ENCRYPTION')
secureEncoder = Fernet(key)

PermissionDefinitions = {
    "Admin": {
        "AddEvent": True,
        "Edit": True,
        "Upload": True,
        "Delete": True,
    },
    "Member": {
        "AddEvent": True,
        "Edit": False,
        "Upload": True,
        "Delete": False,
    }
}

def get_permission(permission_dict, permit):
    position = permission_dict["Position"]

    if not position in PermissionDefinitions.keys():
        return False
    
    if not permit in PermissionDefinitions[position].keys():
        return False 
    
    return PermissionDefinitions[position][permit]

def get_or_none(func):
    def wrapped_func(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            print(traceback.format_exc())
            return None
    return wrapped_func

def sanitize_input(data, required_keys=[], accepted_keys=[]):
    if len(required_keys) == 0 and len(accepted_keys) == 0:
        return True
    
    hasKey = []
    for key in data:
        if not key in accepted_keys and len(accepted_keys) > 0:
            raise Exception("Unaccepted Form Data Received. Malformed Request.")
        if key in required_keys:
            hasKey.append(key)
    
    if len(hasKey) < len(required_keys):
        raise Exception("Insufficient Form Data Input. Malformed Request.")
    
    return True

def PKCE_code_verifier():
    return secrets.token_urlsafe(64)

def PKCE_code_challenger(pkce):
    return base64.urlsafe_b64encode(hashlib.sha256(pkce.encode("utf-8")).digest()).decode().strip().replace("=","")

def get_token(size=16):
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for i in range(size))

def uuid4_hex():
    return uuid.uuid4().hex

def current_time():
    return datetime.datetime.now(tz=datetime.timezone.utc).timestamp()

def encryptMessage(message):
    return secureEncoder.encrypt(message.encode("utf-8")).decode("utf-8")

def decryptMessage(message):
    try:
        return secureEncoder.decrypt(message.encode("utf-8")).decode("utf-8")
    except:
        return message
