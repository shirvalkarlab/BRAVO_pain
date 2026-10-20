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
import datetime, pytz
import uuid
from cryptography.fernet import Fernet
import secrets
import hashlib, base64
import numpy as np

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

def utc_offset_to_timezone(offset_str):
    # Parse the offset string
    sign = -1 if '-' in offset_str else 1
    hours, minutes = map(int, offset_str.replace('UTC', '').replace('+', '').replace('-', '').split(':'))
    total_minutes = sign * (hours * 60 + minutes)

    # Create a FixedOffset timezone
    return pytz.FixedOffset(total_minutes)

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
        except FileNotFoundError:
            return None
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

def lttb_optimized(x, y, threshold=200000):
    """
    Optimized LTTB algorithm for downsampling time-series data.

    Parameters:
        x (np.ndarray): 1D array of time or x-values.
        y (np.ndarray): 1D array of corresponding y-values.
        threshold (int): Number of points to retain.

    Returns:
        (np.ndarray, np.ndarray): Downsampled x and y arrays.
    """
    if threshold >= len(x) or threshold == 0:
        return x, y

    data = np.column_stack((x, y))
    sampled = np.zeros((threshold, 2))
    sampled[0] = data[0]
    sampled[-1] = data[-1]

    bucket_size = (len(data) - 2) / (threshold - 2)
    a = 0

    for i in range(1, threshold - 1):
        start = int((i - 1) * bucket_size) + 1
        end = int(i * bucket_size) + 1
        next_end = int((i + 1) * bucket_size) + 1

        bucket = data[start:end]
        next_bucket = data[end:next_end]

        if len(next_bucket) == 0:
            avg_x, avg_y = data[-1]
        else:
            avg_x = np.mean(next_bucket[:, 0])
            avg_y = np.mean(next_bucket[:, 1])

        ax, ay = data[a]
        dx = ax - bucket[:, 0]
        dy = bucket[:, 1] - ay
        area = np.abs((ax - avg_x) * dy - dx * (avg_y - ay))
        max_idx = np.argmax(area)
        sampled[i] = bucket[max_idx]
        a = start + max_idx
    return sampled[:, 0], sampled[:, 1]

def minimum_change_eliminator(x, y, threshold=0.1):
    threshold_level = threshold * np.std(y)
    last_value = y[0]
    selected_indices = [0]
    for i in range(1, len(y)):
        if np.abs(y[i] - last_value) > threshold_level:
            last_value = y[i]
            selected_indices.append(i)

    x_filtered = x[selected_indices]
    y_filtered = y[selected_indices]
    return x_filtered, y_filtered

def json_compliant_handler(data):
    if type(data) == list:
        for i in range(len(data)):
            data[i] = json_compliant_handler(data[i])
    elif type(data) == dict:
        for item in data.keys():
            data[item] = json_compliant_handler(data[item])
    elif type(data) == np.ndarray:
        data = data.tolist()
        data = json_compliant_handler(data)
    elif type(data) == float:
        if np.isnan(data) or np.isinf(data):
            return None
    return data

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
