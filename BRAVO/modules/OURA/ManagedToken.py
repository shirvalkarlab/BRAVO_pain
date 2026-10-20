"""Private, participant-bound bearer-token refresh using native Oura parsers.

Credentials never enter Device.auth. Every stream is fetched before publishing a
new immutable snapshot; a failed/expired request leaves the previous source intact.
"""
from datetime import date, datetime, timedelta, timezone
import contextlib
import hashlib
import hmac
import json
import os
from pathlib import Path
import struct
import re
import stat
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
import numpy as np

CONFIG_ENV = "BRAVO_OURA_MANAGED_CONFIG_FILE"
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_TOTAL_RECORDS = 1_000_000
MAX_TOTAL_PAGES = 2000
MAX_SECONDS = 15 * 60
STREAMS = {
    "DailyActivity": "getDailyActivity", "DailyReadiness": "getDailyReadiness",
    "DailyCardiovascularAge": "getDailyCardiovascularAge", "DailySpo2": "getDailySpo2",
    "DailyStress": "getDailyStress", "HeartRate": "getHeartRate", "Sleep": "getSleep",
}
ENDPOINTS = {"personal_info", "daily_activity", "daily_readiness", "daily_cardiovascular_age",
             "daily_spo2", "daily_stress", "heartrate", "sleep"}


class ManagedOuraError(RuntimeError):
    """Sanitized operational error; never includes provider response bodies."""


def private_json(path):
    if not isinstance(path, (str, Path)):
        raise ManagedOuraError("Oura configuration path is invalid.")
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in [path, *path.parents]):
        raise ManagedOuraError("Oura configuration must use an absolute, non-symlink private file.")
    try:
        st = path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid not in (0, os.getuid()):
            raise ManagedOuraError("Oura configuration file permissions are not private.")
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ManagedOuraError("Oura private configuration is unavailable or malformed.") from None
    if not isinstance(data, dict):
        raise ManagedOuraError("Oura private configuration must be an object.")
    return data


def binding(participant):
    path = os.environ.get(CONFIG_ENV)
    if not path:
        raise ManagedOuraError("Managed Oura credentials are not configured.")
    document = private_json(path)
    entries = document.get("participants")
    if document.get("schema_version") != 1 or not isinstance(entries, dict):
        raise ManagedOuraError("Unsupported managed Oura configuration.")
    item = entries.get(str(participant.uid))
    if not isinstance(item, dict) or item.get("institute_uid") != str(participant.institute_id):
        raise ManagedOuraError("Managed Oura participant binding is unavailable.")
    if not isinstance(item.get("account_id_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["account_id_sha256"]):
        raise ManagedOuraError("Managed Oura account identity is not verified.")
    try:
        start = date.fromisoformat(item["start_date"])
        zone = ZoneInfo(item["timezone"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ManagedOuraError("Managed Oura date settings are invalid.") from None
    if start < date(2010, 1, 1) or start > datetime.now(zone).date():
        raise ManagedOuraError("Managed Oura start date is outside the supported range.")
    secret = private_json(item.get("token_file", ""))
    token = secret.get("access_token")
    if not isinstance(token, str) or not token or token.strip() != token or "\n" in token or "\r" in token:
        raise ManagedOuraError("Managed Oura access token is unavailable.")
    return item, token


class Transport:
    """Allowlisted, bounded read-only requests with pagination and exact ID dedup."""
    def __init__(self, token, account_digest, session=None):
        self.token, self.account_digest = token, account_digest
        self.session = session or requests.Session()
        self.owns_session = session is None
        self.seen = {}
        self.total_bytes = self.total_records = self.total_pages = 0
        self.started = time.monotonic()

    def close(self):
        if self.owns_session:
            self.session.close()

    def query(self, endpoint, params):
        if endpoint not in {"v2/usercollection/" + name for name in ENDPOINTS}:
            raise ManagedOuraError("Unsupported managed Oura endpoint.")
        params = dict(params)
        page_tokens, combined = set(), []
        seen = self.seen.setdefault(endpoint, {})
        for _ in range(100):
            self.total_pages += 1
            if self.total_pages > MAX_TOTAL_PAGES or time.monotonic() - self.started > MAX_SECONDS:
                raise ManagedOuraError("Oura refresh exceeded its bounded work limit.")
            response = None
            try:
                response = self.session.get("https://api.ouraring.com/" + endpoint,
                    headers={"Authorization": "Bearer " + self.token}, params=params,
                    timeout=(10, 30), allow_redirects=False, stream=True)
                if response.status_code in (401, 403):
                    raise ManagedOuraError("Oura authorization expired or access was denied; renew the private access token.")
                if response.status_code != 200:
                    raise ManagedOuraError("Oura provider request failed; previous data were preserved.")
                body = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    self.total_bytes += len(chunk)
                    if (len(body) + len(chunk) > MAX_RESPONSE_BYTES or
                            self.total_bytes > MAX_TOTAL_BYTES or
                            time.monotonic() - self.started > MAX_SECONDS):
                        raise ManagedOuraError("Oura provider response exceeded the bounded work limit.")
                    body.extend(chunk)
                payload = json.loads(body)
            except (requests.RequestException, ValueError):
                raise ManagedOuraError("Oura provider was unavailable or returned invalid JSON; previous data were preserved.") from None
            finally:
                if response is not None:
                    response.close()
            if endpoint.endswith("/personal_info"):
                if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
                    raise ManagedOuraError("Oura account identity was missing.")
                digest = hashlib.sha256(payload["id"].encode()).hexdigest()
                if not hmac.compare_digest(digest, self.account_digest):
                    raise ManagedOuraError("Oura account does not match the verified participant binding.")
                return payload
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ManagedOuraError("Oura provider returned an invalid data collection.")
            for record in payload["data"]:
                self.total_records += 1
                if self.total_records > MAX_TOTAL_RECORDS:
                    raise ManagedOuraError("Oura refresh exceeded its record limit.")
                if not isinstance(record, dict):
                    raise ManagedOuraError("Oura provider returned an invalid data record.")
                # Heart-rate records lack id; their timestamp/source tuple is the native identity.
                identity = record.get("id")
                if identity is None and endpoint.endswith("/heartrate"):
                    identity = (record.get("timestamp"), record.get("source"))
                if (not isinstance(identity, (str, tuple)) or not identity or
                        isinstance(identity, tuple) and not all(isinstance(v, str) and v for v in identity)):
                    raise ManagedOuraError("Oura data record lacks a stable identity.")
                encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
                if identity in seen:
                    if seen[identity] != encoded:
                        raise ManagedOuraError("Oura returned conflicting copies of the same record.")
                    continue
                seen[identity] = encoded
                combined.append(record)
            token = payload.get("next_token")
            if token is None or token == "":
                return {"data": combined}
            if not isinstance(token, str) or token in page_tokens:
                raise ManagedOuraError("Oura pagination was invalid or repeated.")
            page_tokens.add(token)
            params["next_token"] = token
        raise ManagedOuraError("Oura pagination exceeded the bounded page limit.")


def collect(native_api_class, token, item, *, today=None, session=None):
    """Use the deployed native parsers; only transport/authentication is adapted."""
    with contextlib.closing(Transport(token, item["account_id_sha256"], session)) as transport:
        requester = native_api_class(token)
        requester.query = transport.query
        requester.verifyToken()
        start = date.fromisoformat(item["start_date"])
        last = today or datetime.now(ZoneInfo(item["timezone"])).date()
        data = {name: [] for name in STREAMS}
        # Shared boundary dates cover inclusive and exclusive daily API windows. The
        # transport deduplicates exact provider identities across pages and chunks.
        stop = last + timedelta(days=1)
        current = start
        while current < stop:
            boundary = min(current + timedelta(days=28), stop)
            for name, method in STREAMS.items():
                try:
                    rows = getattr(requester, method)(current.isoformat(), boundary.isoformat())
                    if not isinstance(rows, list):
                        raise ManagedOuraError("Native Oura parser did not return records.")
                    data[name].extend(rows)
                except ManagedOuraError:
                    raise
                except Exception:
                    raise ManagedOuraError("A native Oura stream could not be decoded; previous data were preserved.") from None
            current = boundary
        return data, {"start_date": start.isoformat(), "through_date": last.isoformat(),
                      "counts": {name: len(rows) for name, rows in data.items()}}

def content_digest(data):
    """Exact typed content identity independent of Python aliasing/pickle memo IDs."""
    digest = hashlib.sha256()
    def atom(tag, payload=b""):
        digest.update(tag)
        digest.update(struct.pack(">Q", len(payload)))
        digest.update(payload)
    def walk(value):
        if isinstance(value, np.ndarray):
            if value.dtype.hasobject:
                raise ManagedOuraError("Oura snapshots cannot contain object arrays.")
            atom(b"array-dtype", value.dtype.str.encode())
            atom(b"array-shape", json.dumps(value.shape).encode())
            atom(b"array-data", np.ascontiguousarray(value).tobytes())
        elif isinstance(value, np.generic):
            walk(value.item())
        elif value is None:
            atom(b"null")
        elif isinstance(value, bool):
            atom(b"bool", b"1" if value else b"0")
        elif isinstance(value, int):
            atom(b"int", str(value).encode())
        elif isinstance(value, float):
            atom(b"float", struct.pack(">d", value))
        elif isinstance(value, str):
            atom(b"str", value.encode())
        elif isinstance(value, (list, tuple)):
            atom(b"list" if isinstance(value, list) else b"tuple", str(len(value)).encode())
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            if not all(isinstance(key, str) for key in value):
                raise ManagedOuraError("Oura snapshot mappings require string keys.")
            atom(b"dict", str(len(value)).encode())
            for key in sorted(value):
                walk(key)
                walk(value[key])
        else:
            raise ManagedOuraError("Oura snapshot contains an unsupported value type.")
    walk(data)
    return digest.hexdigest()


def recording_directory(participant):
    root = Path(os.environ["DATASERVER_PATH"])
    if not root.is_dir():
        raise ManagedOuraError("Oura storage root is unavailable; refresh cannot create it.")
    directory = root / "recordings" / str(participant.uid)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root, directory


def publish(participant, data, receipt):
    """Publish a complete immutable file and DB pointer; never overwrite old bytes."""
    from django.db import transaction
    from Server import models
    from modules import Database
    root, directory = recording_directory(participant)
    digest = content_digest(data)
    with transaction.atomic():
        # Serialize first creation too, when no SourceFile row exists to lock.
        models.Participant.objects.select_for_update().get(pk=participant.pk)
        source = models.SourceFile.find(owner=participant, type="OuraRingAPISource")
        if source and source.metadata.get("ManagedOuraContentSHA256") == digest:
            stored = Database.loadSourceFile(source.pointer, source.hashed)
            if content_digest(stored) != digest:
                raise ManagedOuraError("Stored Oura snapshot did not match its verified content.")
            return dict(receipt, unchanged=True)
        pointer = str(directory / (uuid4().hex + ".bdat"))
        hashed = Database.saveSourceFile(data, pointer)
        if not isinstance(hashed, str) or not re.fullmatch(r"[0-9a-f]{64}", hashed):
            raise ManagedOuraError("Oura snapshot could not be saved; previous data were preserved.")
        # The database must never point to a payload that has not reached durable
        # storage. Keep old payloads for recovery and publish only after readback.
        os.chmod(pointer, 0o600)
        with open(pointer, "rb") as handle:
            os.fsync(handle.fileno())
        # Sync both new directory entries too, for a participant without prior data.
        for folder in (directory, directory.parent, root):
            directory_fd = os.open(str(folder), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        stored = Database.loadSourceFile(pointer, hashed)
        if content_digest(stored) != digest:
            raise ManagedOuraError("New Oura snapshot failed authenticated readback; previous data were preserved.")
        if source is None:
            source = models.SourceFile(name="OuraRingAPISource", type="OuraRingAPISource", owner=participant)
        source.pointer, source.hashed = pointer, hashed
        source.metadata = dict(source.metadata, ManagedOuraContentSHA256=digest,
            ManagedOura={"version": 1, **receipt, "completed_at": datetime.now(timezone.utc).isoformat()})
        source.save()
    return dict(receipt, unchanged=False)


def refresh(device):
    from filelock import FileLock, Timeout
    from modules.OURA.DataManager import OuraRingAPI
    participant = device.owner
    item, token = binding(participant)
    _, lock_dir = recording_directory(participant)
    try:
        with FileLock(str(lock_dir / ".managed-oura-refresh.lock"), timeout=0):
            data, receipt = collect(OuraRingAPI, token, item)
            return publish(participant, data, receipt)
    except Timeout:
        raise ManagedOuraError("An Oura refresh is already running for this participant.") from None
    except ManagedOuraError:
        raise
    except Exception:
        raise ManagedOuraError("Oura snapshot could not be published; previous data were preserved.") from None
