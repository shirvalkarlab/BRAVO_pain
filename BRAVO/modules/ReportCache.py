"""Share rendered read-only reports between workers; expire them on data changes."""
import gzip
import hashlib
import json
import os
import time
from functools import wraps
from contextvars import ContextVar
from pathlib import Path
from uuid import uuid4

from django.db import transaction
from django.http import HttpResponse
from filelock import FileLock, Timeout
from rest_framework.renderers import JSONRenderer

from modules.OURA import QualityControl

VERSION = "aditya-integrated-reports-2"
MAX_AGE = None  # Input revisions and processing/configuration keys determine freshness.
_calculation_revision = ContextVar("report_revision", default=None)


def calculation_revision():
    return _calculation_revision.get() or revision()


def analysis_policy_identity():
    """Fingerprint policies applied at read time; do not relabel stored REDCap rows.

    These three small files are read afresh so mutable CSV changes cannot outlive
    an in-memory digest cache. Published REDCap form changes use normal DB revision.
    """
    module_root = Path(__file__).resolve().parent
    files = (module_root / "RCS08DataPolicy.py", module_root / "OURA" / "QualityControl.py",
             QualityControl.POLICY_PATH)
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
    return hashlib.sha256(json.dumps(hashes).encode()).hexdigest()


def directory():
    root = Path(os.environ["DATASERVER_PATH"]) / "report-cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def revision(name="revision"):
    try:
        return (directory() / name).read_text()
    except FileNotFoundError:
        return "initial"


def invalidate(*, neural=False):
    """Publish an atomic revision after a committed source/configuration edit."""
    def publish():
        root = directory()
        value = uuid4().hex
        temp = root / ("revision." + value)
        temp.write_text(value)
        temp.replace(root / "revision")
        if neural:
            temp = root / ("neural-revision." + value)
            temp.write_text(value)
            temp.replace(root / "neural-revision")
    transaction.on_commit(publish)


def _response(compressed, request, state):
    accepts_gzip = False
    for part in request.headers.get("Accept-Encoding", "").split(","):
        name, *parameters = part.strip().split(";")
        if name == "gzip":
            try:
                quality = next((float(p.strip()[2:]) for p in parameters if p.strip().startswith("q=")), 1)
                accepts_gzip = quality > 0
            except ValueError:
                pass
    response = HttpResponse(compressed if accepts_gzip else gzip.decompress(compressed), content_type="application/json")
    if accepts_gzip:
        response["Content-Encoding"] = "gzip"
    response["Vary"] = "Accept-Encoding"
    response["Cache-Control"] = "no-store"
    response["X-BRAVO-Report-Cache"] = state
    return response


def cached_report(function):
    @wraps(function)
    def wrapped(view, request, *args, **kwargs):
        from modules import Database
        permitted_types = {None, "RequestAll", "TherapyGroup"}
        participant = request.data.get("ParticipantId")
        if not participant or request.data.get("RequestType") not in permitted_types:
            return function(view, request, *args, **kwargs)
        configuration = request.user.configuration
        permission = Database.checkAccessPermission(request.user, participant, study_uid=configuration.get("ActiveStudy"))
        if not permission:
            return function(view, request, *args, **kwargs)
        processing, _ = Database.retrieveProcessingSettings(configuration)
        policy_identity = analysis_policy_identity()
        identity = json.dumps([VERSION, getattr(view, "cache_version", None), policy_identity, request.path, request.data, processing, permission,
                               hasattr(request.user, "api_access")], sort_keys=True, default=str)
        key = hashlib.sha256(identity.encode()).hexdigest()
        path = directory() / (key + ".gz")

        def read(expected):
            try:
                if MAX_AGE is not None and time.time() - path.stat().st_mtime > MAX_AGE:
                    return None
                with path.open("rb") as source:
                    saved_revision = source.readline().decode().strip()
                    if saved_revision == expected or expected is None:
                        return source.read()
            except FileNotFoundError:
                pass
            return None

        current = revision()
        saved = read(current)
        if saved is not None:
            return _response(saved, request, "HIT")
        if not _warming.get() and refresh_in_progress():
            previous = read(None)
            if previous is not None:
                return _response(previous, request, "UPDATING")
        # Concurrent readers wait for one calculation, then reuse its result.
        lock = FileLock(str(path) + ".lock", timeout=60)
        try:
            lock.acquire()
        except Timeout:
            response = HttpResponse('{"message":"This report is still being prepared. Please retry shortly."}',
                                    status=503, content_type="application/json")
            response["Retry-After"] = "5"
            return response
        try:
            current = revision()
            saved = read(current)
            if saved is not None:
                return _response(saved, request, "HIT")
            token = _calculation_revision.set(current + ":" + policy_identity)
            try:
                response = function(view, request, *args, **kwargs)
            finally:
                _calculation_revision.reset(token)
            if response.status_code != 200 or not hasattr(response, "data"):
                return response
            compressed = gzip.compress(JSONRenderer().render(response.data), compresslevel=2)
            if revision() == current:
                temp = path.with_suffix(".tmp")
                temp.write_bytes(current.encode() + b"\n" + compressed)
                temp.replace(path)
            return _response(compressed, request, "MISS")
        finally:
            lock.release()
    return wrapped


def data_changed(sender, instance, **kwargs):
    derived_sources = {"CachedResult", "ChronicNeuralActivitySource", "ProcessedCustomizedStreamingData"}
    if sender.__name__ == "SourceFile" and instance.type in derived_sources:
        return
    if sender.__name__ == "Recording" and (
        instance.original_id or instance.type.startswith("Processed") or instance.source.type in derived_sources
    ):
        return
    neural = sender.__name__ in {"DBSDevice", "Electrode", "Therapy", "ElectricalTherapy", "AdaptiveTherapy", "ElectricalStimulation", "TherapyModification"}
    if sender.__name__ == "SourceFile":
        neural = instance.type == "MedtronicJSON"
    elif sender.__name__ == "Recording":
        neural = instance.type.startswith("Medtronic")
    invalidate(neural=neural)


def relations_changed(sender, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        invalidate(neural=True)


def register_signals():
    from django.db.models.signals import post_save, post_delete, m2m_changed
    from Server import models
    for name in ("SourceFile", "Recording", "Participant", "DBSDevice", "Electrode", "Annotation",
                 "ScaleForms", "ScaleRecord", "ParticipantLinkRel", "OuraRingDevice",
                 "Therapy", "ElectricalTherapy", "AdaptiveTherapy", "ElectricalStimulation", "TherapyModification", "DBSEvent"):
        model = getattr(models, name)
        post_save.connect(data_changed, sender=model, dispatch_uid="report-save-" + name)
        post_delete.connect(data_changed, sender=model, dispatch_uid="report-delete-" + name)
    m2m_changed.connect(relations_changed, sender=models.DBSDevice.electrodes.through, dispatch_uid="report-device-electrodes")


def refresh_in_progress():
    """Existing viewers may keep the last completed report during a sync."""
    root = Path(os.environ['DATASERVER_PATH'])
    for path in (root / 'sync-state' / 'rcs08-execution.lock', directory() / 'preparing.lock'):
        lock = FileLock(str(path), timeout=0)
        try:
            lock.acquire()
        except Timeout:
            return True
        else:
            lock.release()
    return False


_warming = ContextVar('warming_reports', default=False)


def prewarm_participant(participant):
    """Prepare the existing report views for each effective signed-in user configuration."""
    from django.urls import resolve
    from rest_framework.test import APIRequestFactory, force_authenticate
    from Server import models
    from modules import Database
    factory = APIRequestFactory()
    results = []
    endpoints = (
        ('neural', '/api/queryChronicNeuralActivity', {'RequestType': 'RequestAll'}),
        ('multimodal', '/api/queryChronicTimeline', {'RequestType': 'RequestAll'}),
        ('snapshot', '/api/queryNeuralActivitySnapshot', {'RequestType': 'RequestAll'}),
        ('therapy', '/api/v2/queryTherapyHistory', {'RequestType': 'TherapyGroup'}),
        ('oura-freereps', '/api/queryOuraFreeReps', {}),
        ('redcap-pretrial', '/api/queryRedcapTimeline', {}),
    )
    seen = set()
    with FileLock(str(directory() / 'preparing.lock'), timeout=0):
        token = _warming.set(True)
        try:
            for user in models.PlatformUser.objects.filter(institute=participant.institute, is_active=1):
                permission = Database.checkAccessPermission(user, participant.uid, study_uid=user.configuration.get('ActiveStudy'))
                if not permission:
                    continue
                processing, _ = Database.retrieveProcessingSettings(user.configuration)
                identity = json.dumps([processing, permission], sort_keys=True, default=str)
                if identity in seen:
                    continue
                seen.add(identity)
                for name, path, payload in endpoints:
                    start = time.perf_counter()
                    request = factory.post(path, {'ParticipantId': participant.uid, **payload}, format='json', HTTP_ACCEPT_ENCODING='gzip')
                    force_authenticate(request, user=user)
                    response = resolve(path).func(request)
                    if hasattr(response, 'render'):
                        response.render()
                    if response.status_code != 200:
                        raise RuntimeError(f'{name} report preparation failed (HTTP {response.status_code})')
                    results.append({'report': name, 'seconds': round(time.perf_counter()-start, 3),
                                    'cache': response.get('X-BRAVO-Report-Cache', 'none')})
        finally:
            _warming.reset(token)
    return results
