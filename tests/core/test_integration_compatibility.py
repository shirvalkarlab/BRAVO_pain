"""Synthetic integration regressions; no live database, credentials, exports or services."""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from cryptography.fernet import Fernet
import django
from django.conf import settings
from django.test import override_settings
import numpy as np
import pytest

APP = Path(__file__).resolve().parents[2] / "BRAVO"
sys.path.insert(0, str(APP))
sys.path.append(str(APP / "modules"))
_storage = tempfile.TemporaryDirectory(prefix="bravo-core-test-")
os.environ["DATASERVER_PATH"] = _storage.name + os.sep
os.environ["DATASERVER_ENCRYPTION"] = Fernet.generate_key().decode()
os.environ["DATASERVER_HASHKEY"] = "synthetic-integration-key"
os.environ.pop("REDIS_HOST", None)
os.environ["FIBIT_CLIENT_ID"] = "synthetic"
os.environ["FIBIT_CLIENT_SECRET"] = "synthetic"
if not settings.configured:
    settings.configure(
        SECRET_KEY="synthetic-core-only", DEBUG=True,
        INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes", "Server"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        AUTH_USER_MODEL="Server.PlatformUser", DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
    )
django.setup()

from modules import Database, DataCurator, DataAnalysis, Therapy
from modules.Biomarkers.routines import calibration
from modules.ClosedLoopDeployment import device_facts
from Server.APIs import DataAnalysis as AnalysisAPI
from django.http import QueryDict


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError("network access is forbidden in synthetic core tests")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.delenv("BRAVO_CALIBRATION_DIR", raising=False)
    monkeypatch.delenv("BRAVO_DEVICE_FACTS_DIR", raising=False)


def test_debug_does_not_bypass_participant_permissions(monkeypatch):
    participant = SimpleNamespace(institute=SimpleNamespace(has_permission=lambda *a: False))
    monkeypatch.setattr(Database.models.Participant, "find", lambda **kwargs: participant)
    with override_settings(DEBUG=True):
        assert Database.checkAccessPermission(object(), "synthetic-subject") is False
        assert Database.checkManagePermission(object(), "synthetic-subject", "Delete") is False


def test_timeseries_get_keeps_binary_response_and_metadata(monkeypatch):
    data = np.array([1.25, -2.5], dtype=np.float64)
    seen = []
    monkeypatch.setattr(Database, "checkAccessPermission", lambda *a, **k: {"Deidentified": True})
    def load(participant, recording, config):
        seen.append((participant, recording, config))
        return data, {"SamplingRate": 250, "DataSize": [2]}
    monkeypatch.setattr(DataAnalysis, "getTimeseriesData", load)
    request = SimpleNamespace(GET=QueryDict("ParticipantId=synthetic&RecordingId=recording&Step=2"),
                              user=SimpleNamespace(configuration={}))
    response = AnalysisAPI.QueryTimeseriesAnalysis().get(request)
    assert response.content == data.tobytes()
    assert response["Content-Type"] == "application/octet-stream"
    assert json.loads(response["X-Metadata"])["SamplingRate"] == 250
    assert seen == [("synthetic", "recording", {"StartTime": 0, "StopTime": 0, "Step": 2})]


def test_timeseries_get_denied_does_not_load_data(monkeypatch):
    monkeypatch.setattr(Database, "checkAccessPermission", lambda *a, **k: False)
    monkeypatch.setattr(DataAnalysis, "getTimeseriesData", lambda *a: pytest.fail("denied data read"))
    request = SimpleNamespace(GET=QueryDict("ParticipantId=synthetic&RecordingId=recording"),
                              user=SimpleNamespace(configuration={}))
    assert AnalysisAPI.QueryTimeseriesAnalysis().get(request).status_code == 403


def test_native_routes_and_handlers_coexist_with_prasad_and_aditya():
    tree = ast.parse((APP / "Server/APIs/urls.py").read_text())
    routes = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "path"}
    assert {"requestGoogleHealthAuth", "queryGoogleHealthData", "queryFilterData",
            "queryBiomarkerAnalysis", "queryClosedLoopDeployment", "queryStimOptimizer",
            "queryRedcapTimeline", "queryHomeNeuralTimeline", "queryOuraTimeline"} <= routes
    assert callable(DataCurator.UFMDATv3Decoder)
    assert callable(DataCurator.decodeMDATv3)
    for name in ("queryTherapyHistoryMetadata", "queryTherapyModification", "queryTherapyGroups",
                 "createAgenticAIOverview", "therapy_from_data_start"):
        assert callable(getattr(Therapy, name))


def test_calibration_empty_install_reports_missing_evidence():
    result = calibration.panel_payload("SYNTHETIC", deployed_k=345.59,
                                      deployed_bridge_ratio=4.789, deployed_bridge=72.16)
    assert result["available"] is False
    assert result["reason_code"] == "calibration_data_unavailable"
    assert "not configured" in result["reason"]
    assert "blocks" not in result


def test_calibration_private_tables_newest_and_exact_date(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAVO_CALIBRATION_DIR", str(tmp_path))
    old = tmp_path / "SYNTHETIC_transform_blocks_2026-01-01.csv"
    new = tmp_path / "SYNTHETIC_transform_blocks_2026-02-01.csv"
    for path, value in [(old, 2), (new, 3)]:
        path.write_text(f"existing_uv2,target_lsb_all\n{value},600\n")
    assert calibration.block_table_path("synthetic") == str(new)
    assert calibration.block_table_path("synthetic", "2026-01-01") == str(old)
    assert calibration.load_blocks("synthetic")[0]["existing_uv2"] == 3


@pytest.mark.parametrize("selector,date", [("../other", None), ("SYNTHETIC", "../../outside")])
def test_calibration_selector_cannot_leave_private_directory(tmp_path, monkeypatch, selector, date):
    monkeypatch.setenv("BRAVO_CALIBRATION_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        calibration.block_table_path(selector, date)


def test_calibration_symlink_cannot_leave_private_directory(tmp_path, monkeypatch):
    root = tmp_path / "private"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("must not be read")
    (root / "SYNTHETIC_transform_blocks_2026-01-01.csv").symlink_to(outside)
    monkeypatch.setenv("BRAVO_CALIBRATION_DIR", str(root))
    with pytest.raises(FileNotFoundError):
        calibration.block_table_path("SYNTHETIC")


def test_private_facts_require_matching_subject_and_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAVO_DEVICE_FACTS_DIR", str(tmp_path))
    path = tmp_path / "synthetic.json"
    document = {"participant_uid": "other", "summary": {"n_files": 2},
                "provenance": {"source": "synthetic fixture", "scanned_at": "2026-01-01"}}
    path.write_text(json.dumps(document))
    assert device_facts._private_summary("synthetic") == ({}, {})
    document["participant_uid"] = "synthetic"
    path.write_text(json.dumps(document))
    assert device_facts._private_summary("synthetic") == (document["summary"], document["provenance"])
    document.pop("provenance")
    path.write_text(json.dumps(document))
    assert device_facts._private_summary("synthetic") == ({}, {})
    assert device_facts._private_summary("../synthetic") == ({}, {})


def test_fresh_ingested_record_starts_summary_build_without_private_fallback(monkeypatch):
    launches = []
    monkeypatch.setattr(device_facts, "_ingested_file_set", lambda uid: ([], "synthetic-key", None))
    monkeypatch.setattr(device_facts._cache_store, "load", lambda *a: None)
    monkeypatch.setattr(device_facts._cache_store, "load_newest", lambda *a: (None, None))
    def launch(uid, sig):
        launches.append((uid, sig))
        return {"launched": True}
    monkeypatch.setattr(device_facts, "launch_summary_rebuild_in_background", launch)
    summary, resolution = device_facts._load_summary("synthetic")
    assert summary == {} and resolution["source"] == "none"
    assert resolution["launch"] == {"launched": True}
    assert launches == [("synthetic", "synthetic-key")]


def test_private_facts_fallback_is_labeled_and_never_claims_current(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAVO_DEVICE_FACTS_DIR", str(tmp_path))
    (tmp_path / "synthetic.json").write_text(json.dumps({
        "participant_uid": "synthetic", "summary": {"n_files": 2},
        "provenance": {"source": "synthetic fixture", "scanned_at": "2026-01-01"},
    }))
    monkeypatch.setattr(device_facts, "_ingested_file_set", lambda uid: (None, None, "test database absent"))
    summary, resolution = device_facts._load_summary("synthetic")
    assert summary == {"n_files": 2}
    assert resolution["source"] == "supplied"
    assert "externally supplied scan" in resolution["sentence"]
    assert "synthetic fixture" in resolution["sentence"]
    assert resolution["launch"] is None


def test_restored_therapy_modifications_obey_prasad_data_start(monkeypatch):
    monkeypatch.setattr(Therapy._data_start, "data_start_s", lambda participant: 100)
    monkeypatch.setattr(Therapy.models.DBSDevice, "find_all", lambda **kwargs: [SimpleNamespace(uid="device")])
    monkeypatch.setattr(Therapy.models.SourceFile, "find_all", lambda **kwargs: [object()])
    rows = [{"Date": 25, "Type": "TherapyChangeGroup"},
            {"Date": 75, "Type": "TherapyChangeGroup"},
            {"Date": 50, "Type": "Other"},
            {"Date": 125, "Type": "TherapyChangeGroup"}]
    monkeypatch.setattr(Therapy.models.TherapyModification, "find_all",
                        lambda **kwargs: [SimpleNamespace(get_info=lambda row=row: dict(row)) for row in rows])
    result = Therapy.queryTherapyModification(object())
    assert [row["Date"] for row in result] == [100, 125]
    assert all(row["Device"] == "device" for row in result)
    assert rows[1]["Date"] == 75, "input observations are not mutated"


def test_revoked_study_membership_denies_before_data_relationship(monkeypatch):
    participant = SimpleNamespace(institute=SimpleNamespace(has_permission=lambda *a: False))
    study = object()
    monkeypatch.setattr(Database.models.Participant, "find", lambda **kw: participant)
    monkeypatch.setattr(Database.models.Study, "find", lambda **kw: study)
    monkeypatch.setattr(Database.models.StudyRel, "find", lambda **kw: None)
    monkeypatch.setattr(Database.models.StudyDataRel, "find", lambda **kw: pytest.fail("revoked study data read"))
    assert Database.checkAccessPermission(object(), "a", study_uid="stale-study") is False


def test_active_study_member_retains_deidentified_access(monkeypatch):
    participant = SimpleNamespace(institute=SimpleNamespace(has_permission=lambda *a: False))
    monkeypatch.setattr(Database.models.Participant, "find", lambda **kw: participant)
    monkeypatch.setattr(Database.models.Study, "find", lambda **kw: object())
    monkeypatch.setattr(Database.models.StudyRel, "find", lambda **kw: object())
    monkeypatch.setattr(Database.models.StudyDataRel, "find", lambda **kw: SimpleNamespace(permission={}))
    assert Database.checkAccessPermission(object(), "a", study_uid="study") == {"Deidentified": True}


def test_institute_debug_never_grants_nonmember_access(monkeypatch):
    institute = SimpleNamespace(members=SimpleNamespace(filter=lambda **kw: SimpleNamespace(exists=lambda: False)))
    monkeypatch.setattr(Database.models.InstituteRel, "find", lambda **kw: None)
    with override_settings(DEBUG=True):
        assert Database.models.Institute.has_permission(institute, SimpleNamespace(uid="outsider")) is False
        assert Database.models.Institute.has_permission(institute, SimpleNamespace(uid="outsider"), "Delete") is False


def test_private_pair_evidence_is_exact_subject_and_side_bound(tmp_path, monkeypatch):
    document = {"participant_uid": "synthetic-a", "provenance": {"source": "synthetic", "scanned_at": "2026-01-01"},
                "programmed_pairs": {"Left": {"55/60": 2}, "Right": {"55/160": 1}},
                "programmed_pairs_provenance": "synthetic observed pairs"}
    (tmp_path / "synthetic-a.json").write_text(json.dumps(document))
    monkeypatch.setenv("BRAVO_DEVICE_FACTS_DIR", str(tmp_path))
    monkeypatch.setattr(device_facts, "_load_summary", lambda uid: ({}, {}))
    assert device_facts.brainsense_pair_programmed(55, 60, "Left", "synthetic-a") is True
    assert device_facts.brainsense_pair_programmed(55, 60, "Right", "synthetic-a") is False
    assert device_facts.brainsense_pair_programmed(55, 60, "Left", "synthetic-b") is None
    assert device_facts.brainsense_pair_programmed(55, 60, "Left") is None
    (tmp_path / "synthetic-b.json").write_text(json.dumps(document))
    assert device_facts.brainsense_pair_programmed(55, 60, "Left", "synthetic-b") is None
    document["programmed_pairs"] = {"Left": []}
    (tmp_path / "synthetic-a.json").write_text(json.dumps(document))
    assert device_facts.brainsense_pair_programmed(55, 60, "Left", "synthetic-a") is None


@pytest.fixture
def redcap_boundary(monkeypatch):
    from modules.Biomarkers import bravo_service as service
    monkeypatch.setenv("REDCAP_API_URL", "https://synthetic.invalid")
    monkeypatch.setenv("REDCAP_API_TOKEN", "synthetic-only")
    monkeypatch.setattr(service, "_resolve_field_map", lambda *a: {})
    monkeypatch.setattr(service, "_load_pt_config", lambda *a: {"record_id": "synthetic-a"})
    monkeypatch.setattr(service.redcap_client, "redcap_fields_for_field_map", lambda fm: ([], None))
    return service


def test_redcap_missing_binding_never_exports(redcap_boundary, monkeypatch):
    service = redcap_boundary
    monkeypatch.setattr(service, "_load_pt_config", lambda *a: None)
    monkeypatch.setattr(service.redcap_client, "pull_redcap", lambda **kw: pytest.fail("unbound export"))
    with pytest.raises(ValueError, match="participant-bound"):
        service._load_pros_raw({}, participant=object())


def test_redcap_mismatched_selector_never_exports(redcap_boundary, monkeypatch):
    service = redcap_boundary
    monkeypatch.setattr(service.redcap_client, "pull_redcap", lambda **kw: pytest.fail("wrong record export"))
    with pytest.raises(ValueError, match="does not match"):
        service._load_pros_raw({"RedcapRecordId": "synthetic-b"}, participant=object())


def test_redcap_retry_and_connector_response_remain_participant_bound(redcap_boundary, monkeypatch):
    import pandas as pd
    service = redcap_boundary
    calls = []
    monkeypatch.setattr(service, "_resolve_field_map", lambda *a: {"timestamp_label": "time"})
    monkeypatch.setattr(service, "_redcap_narrow_pull_enabled", lambda: True)
    monkeypatch.setattr(service.redcap_client, "redcap_fields_for_field_map", lambda fm: (["time"], None))
    def pull(**kwargs):
        calls.append(kwargs)
        if "fields" in kwargs:
            raise RuntimeError("synthetic narrow failure")
        return pd.DataFrame({"record_id": ["synthetic-a", "synthetic-b"], "score": [3, 7]})
    monkeypatch.setattr(service.redcap_client, "pull_redcap", pull)
    result = service._load_pros_raw({}, participant=object())
    assert calls == [{"fields": ["time"], "records": ["synthetic-a"]}, {"records": ["synthetic-a"]}]
    assert result.to_dict("records") == [{"record_id": "synthetic-a", "score": 3}]


def test_optional_ai_model_unavailable_returns_explicit_503(monkeypatch):
    from Server.APIs import AIModels
    def unavailable(data):
        raise AIModels.ModelUnavailable("synthetic trusted assets are absent")
    monkeypatch.setattr(AIModels.ModelManager, "Overview", {"Synthetic": {"Method": unavailable}})
    request = SimpleNamespace(data={"RequestType": "Predict", "AnalysisName": "Synthetic", "Data": {}})
    response = AIModels.RequestPrediction.post.__wrapped__(AIModels.RequestPrediction(), request)
    assert response.status_code == 503
    assert response.data["code"] == "model_unavailable"


def test_pro_request_memo_separates_explicit_participant_ids(redcap_boundary):
    service = redcap_boundary
    assert service._pro_scope_key({"ParticipantId": "synthetic-a"}, None) != service._pro_scope_key(
        {"ParticipantId": "synthetic-b"}, None)


@pytest.mark.parametrize("peer,header,trusted,expected", [
    ("198.51.100.9", "203.0.113.99", [], "198.51.100.9"),
    ("198.51.100.9", "203.0.113.99", ["172.30.0.2/32"], "198.51.100.9"),
    ("172.30.0.2", "203.0.113.99", ["172.30.0.2/32"], "203.0.113.99"),
    ("172.30.0.2", "2001:db8::1", ["172.30.0.2/32"], "2001:db8::1"),
    ("172.30.0.2", "203.0.113.99, 198.51.100.9", ["172.30.0.2/32"], None),
    ("172.30.0.2", "", ["172.30.0.2/32"], None),
    ("", "203.0.113.99", ["172.30.0.2/32"], None),
])
def test_homepage_client_ip_requires_trusted_peer(peer, header, trusted, expected):
    from Server import views
    request = SimpleNamespace(META={"REMOTE_ADDR": peer, "HTTP_X_BRAVO_CLIENT_IP": header,
                                    "HTTP_X_FORWARDED_FOR": "192.0.2.99"})
    with override_settings(BRAVO_TRUSTED_PROXY_CIDRS=trusted):
        assert views.get_client_ip(request) == expected


def test_homepage_burst_is_temporary_and_never_blacklists_proxy(monkeypatch):
    from Server import views
    from django.http import HttpResponse
    views.ConsecutiveError.clear()
    checked = []
    monkeypatch.setattr(views.models.BlacklistRecords, "exists", lambda **kw: checked.append(kw) or False)
    monkeypatch.setattr(views.models.BlacklistRecords, "save", lambda *a, **k: pytest.fail("automatic permanent blacklist"))
    monkeypatch.setattr(views, "render", lambda *a, **kw: HttpResponse("synthetic app"))
    now = [100.0]
    monkeypatch.setattr(views.time, "monotonic", lambda: now[0])
    def request(client):
        return SimpleNamespace(META={"REMOTE_ADDR": "172.30.0.2", "HTTP_X_BRAVO_CLIENT_IP": client},
                               user=SimpleNamespace(is_authenticated=False))
    invoke = lambda client: views.Homepage.get.__wrapped__(views.Homepage(), request(client))
    with override_settings(BRAVO_TRUSTED_PROXY_CIDRS=["172.30.0.2/32"]):
        for _ in range(10):
            assert invoke("203.0.113.10").status_code == 200
        limited = invoke("203.0.113.10")
        assert limited.status_code == 429 and limited["Retry-After"] == "10"
        assert invoke("203.0.113.11").status_code == 200
        now[0] += 10
        assert invoke("203.0.113.10").status_code == 200
    assert all(row["ip_address"] != "172.30.0.2" for row in checked)
    views.ConsecutiveError.clear()


@pytest.mark.parametrize("age,active,accepted", [(0, 1, True), (17999, 1, True),
                                                 (18000, 1, False), (18001, 1, False),
                                                 (-1, 1, False), (60, 0, False)])
def test_desktop_authentication_enforces_five_hour_expiry_and_active_account(monkeypatch, age, active, accepted):
    from Server import authentication
    now = 100000.0
    user = SimpleNamespace(is_active=active)
    def lookup(**kwargs):
        assert kwargs["token"] == "synthetic-token"
        created = now - age
        record = SimpleNamespace(user=user) if kwargs["date__gt"] < created <= kwargs["date__lte"] else None
        return SimpleNamespace(first=lambda: record)
    monkeypatch.setattr(authentication.models, "current_time", lambda: now)
    monkeypatch.setattr(authentication.models.AuthenticationTokens.objects, "filter", lookup)
    request = SimpleNamespace(headers={"X-Secure-Auth-Token": "synthetic-token"})
    result = authentication.BRAVOAPIAuthentication().authenticate(request)
    assert (result is not None) is accepted
    assert getattr(request, "csrf_processing_done", False) is accepted


def test_api_key_cannot_reactivate_disabled_account(monkeypatch):
    from Server import authentication
    monkeypatch.setattr(authentication.models.PlatformUser, "find", lambda **kw: SimpleNamespace(is_active=0))
    request = SimpleNamespace(headers={"X-Secure-API-Key": "synthetic-key"})
    assert authentication.BRAVOAPIAuthentication().authenticate(request) is None
    assert not getattr(request, "csrf_processing_done", False)
