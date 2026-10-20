"""Exercise the real therapy API projection with isolated storage and mocked data owners."""
import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from cryptography.fernet import Fernet
import django
from django.conf import settings
import pytest

APP = Path(__file__).resolve().parents[2] / "BRAVO"
sys.path.insert(0, str(APP)); sys.path.append(str(APP / "modules"))
_storage = tempfile.TemporaryDirectory(prefix="bravo-native-api-test-")
os.environ["DATASERVER_PATH"] = _storage.name + os.sep
os.environ["DATASERVER_ENCRYPTION"] = Fernet.generate_key().decode()
os.environ["DATASERVER_HASHKEY"] = "synthetic-native-api-only"
os.environ.pop("REDIS_HOST", None)
if not settings.configured:
    settings.configure(SECRET_KEY="synthetic-native-api-only", DEBUG=True,
        INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes", "Server"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        AUTH_USER_MODEL="Server.PlatformUser", DEFAULT_AUTO_FIELD="django.db.models.BigAutoField", USE_TZ=True)
django.setup()
from Server.APIs import Therapy as API

@pytest.fixture
def source(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError("unexpected network or database call")
    import socket
    monkeypatch.setattr(socket, "create_connection", forbidden)
    history = {"TherapyModification": [{"Device": "synthetic", "History": [{"Date": 1, "Therapy": {"Raw": [1]}}]}],
               "TherapyTimeline": [{"Date": 1, "Therapies": [{"Raw": [1]}], "DefinedTherapies": [{"Current": 0}]}],
               "TherapyConfiguration": [{"Current": 0}], "TherapyDevices": ["synthetic"]}
    monkeypatch.setattr(API.models.Participant, "find", forbidden)
    monkeypatch.setattr(API.Therapy, "queryTherapyHistory", forbidden)
    monkeypatch.setattr(API.Therapy, "queryElectrodeImpedances", forbidden)
    monkeypatch.setattr(API.Database, "saveCachedResult", forbidden)
    return history

def request(compact=None):
    data = {"ParticipantId": "synthetic"}
    if compact is not None: data["Compact"] = compact
    return SimpleNamespace(data=data, user=SimpleNamespace(configuration={}))

def test_denied_compact_request_never_reads_or_caches_source(monkeypatch, source):
    monkeypatch.setattr(API.Database, "checkAccessPermission", lambda *a, **k: False)
    assert API.QueryTherapyHistory().post(request(True)).status_code == 403

@pytest.mark.parametrize("compact", [None, True, False])
def test_real_api_keeps_full_cache_and_projects_only_explicit_compact_response(monkeypatch, source, compact):
    seen=[]; cached=[]; participant=object()
    monkeypatch.setattr(API.Database, "checkAccessPermission", lambda *a, **k: True)
    monkeypatch.setattr(API.models.Participant, "find", lambda **kw: participant)
    def query(p):
        assert p is participant; seen.append(p); return source
    monkeypatch.setattr(API.Therapy, "queryTherapyHistory", query)
    monkeypatch.setattr(API.Therapy, "queryElectrodeImpedances", lambda p: [1,2])
    monkeypatch.setattr(API.Database, "saveCachedResult", lambda data,*a: cached.append(copy.deepcopy(data)))
    response=API.QueryTherapyHistory().post(request(compact))
    assert response.status_code == 200 and seen == [participant]
    assert cached == [source]
    assert "Therapy" in cached[0]["TherapyModification"][0]["History"][0]
    assert "Therapies" in cached[0]["TherapyTimeline"][0]
    if compact is True:
        expected=copy.deepcopy(source)
        del expected["TherapyModification"][0]["History"][0]["Therapy"]
        del expected["TherapyTimeline"][0]["Therapies"]
        assert response.data == expected
    else:
        assert response.data is source


def test_real_therapy_group_route_preserves_device_scope_and_implant_cutoff(monkeypatch):
    from Server.APIv2 import Therapy as APIv2
    participant=object();calls=[]
    monkeypatch.setattr(APIv2.Database, "checkAccessPermission", lambda *a, **kw: True)
    monkeypatch.setattr(APIv2.models.Participant, "find", lambda **kw: participant)
    monkeypatch.setattr(APIv2.Therapy._data_start, "data_start_s", lambda p: 2)
    def devices(**kwargs):
        assert kwargs == {"owner": participant}
        return [SimpleNamespace(uid="D1"),SimpleNamespace(uid="empty"),SimpleNamespace(uid="D2")]
    def sources(**kwargs):
        assert kwargs["owner"] is participant
        device=kwargs["metadata__contains"]["Device"];calls.append(device)
        return [] if device=="empty" else [device]
    def rows(**kwargs):
        device=kwargs["therapy__source__in"][0]
        def item(n,date):
            return {"Id":str(n),"SourceId":device,"Date":date,"GroupId":"A","Type":"Past Therapy",
                    "StimulationSettings":[{"current":n}],"AdaptiveSettings":[]}
        return [SimpleNamespace(get_info=lambda row=row: copy.deepcopy(row))
                for row in [item(1,1),item(2,2),item(3,2)]]
    monkeypatch.setattr(APIv2.models.DBSDevice,"find_all",devices)
    monkeypatch.setattr(APIv2.models.SourceFile,"find_all",sources)
    monkeypatch.setattr(APIv2.models.ElectricalTherapy,"find_all",rows)
    req=SimpleNamespace(data={"ParticipantId":"synthetic","RequestType":"TherapyGroup"},user=SimpleNamespace(configuration={}))
    response=APIv2.QueryTherapyHistory().post(req)
    assert response.status_code == 200
    assert calls == ["D1","empty","D2"]
    assert [r["Device"] for r in response.data] == ["D1","D2"]
    assert all(r["Date"]==2 and r["Id"]=="2" and r["StimulationSettings"]==[{"current":2},{"current":3}] for r in response.data)


def test_denied_v2_therapy_group_request_never_loads_participant(monkeypatch):
    from Server.APIv2 import Therapy as APIv2
    monkeypatch.setattr(APIv2.Database,"checkAccessPermission",lambda *a,**kw:False)
    monkeypatch.setattr(APIv2.models.Participant,"find",lambda **kw:pytest.fail("denied source read"))
    req=SimpleNamespace(data={"ParticipantId":"synthetic","RequestType":"TherapyGroup"},user=SimpleNamespace(configuration={}))
    assert APIv2.QueryTherapyHistory().post(req).status_code==403
