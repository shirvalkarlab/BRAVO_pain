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

key = os.environ.get('DATASERVER_ENCRYPTION')
secureEncoder = Fernet(key)

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

def get_token(size=16):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=size))

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
