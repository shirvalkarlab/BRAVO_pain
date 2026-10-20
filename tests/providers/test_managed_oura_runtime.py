"""Real Django persistence and normal native Oura route behavior, isolated only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from test_optional_oauth_startup import isolated


def test_real_snapshot_atomicity_and_native_dashboard_guards(tmp_path):
    isolated(tmp_path, '''
        from django.core.management import call_command
        from Server import models
        from Server.APIs import OuraRingDashboard as api
        from modules.OURA import DataManager, ManagedToken
        from modules import Database
        import numpy as np
        from pathlib import Path

        call_command("migrate", verbosity=0, interactive=False)
        participant = models.Participant.objects.create(name="Synthetic Oura")
        device = models.OuraRingDevice.objects.create(owner=participant, auth={"managed_token_file": True})
        sample = {"Sleep": [{"Data": np.array([[60.,0.]]), "Missing":np.array([[0.,1.]]),
                              "StartTime": 1., "Metadata":{"DayLabel":"2020-01-01"}}]}
        first=ManagedToken.publish(participant,sample,{"counts":{"Sleep":1}})
        assert first["unchanged"] is False
        source=models.SourceFile.find(owner=participant,type="OuraRingAPISource")
        old_pointer, old_hash=source.pointer,source.hashed
        loaded=DataManager.loadOuraRingData(participant)
        assert np.array_equal(loaded["Sleep"][0]["Data"],sample["Sleep"][0]["Data"])
        assert ManagedToken.publish(participant,sample,{})["unchanged"] is True
        with patch.object(models.SourceFile,"save",side_effect=RuntimeError("synthetic commit failure")):
            try:ManagedToken.publish(participant,{"Sleep":[]},{})
            except RuntimeError:pass
            else:raise AssertionError("must fail")
        source.refresh_from_db()
        assert source.pointer==old_pointer and source.hashed==old_hash and Path(old_pointer).exists()
        assert len(DataManager.loadOuraRingData(participant)["Sleep"])==1

        user=SimpleNamespace(configuration={})
        participant_view=SimpleNamespace(institute=SimpleNamespace(has_permission=lambda *args:True))
        with patch.object(api.Database,"checkAccessPermission",return_value=True), \\
             patch.object(api.models.Participant,"find",return_value=participant_view), \\
             patch.object(api.models.OuraRingDevice,"find",return_value=device):
            for kind in ("VerifyToken","DeleteAuthentication","SetAuthPeriod"):
                req=SimpleNamespace(user=user,data={"ParticipantId":"synthetic","RequestType":kind})
                assert api.OuraRingAuthHandler().post(req).status_code==400
            req=SimpleNamespace(user=user,data={"ParticipantId":"synthetic","RequestType":"RefreshOuraRingData"})
            with patch.object(ManagedToken,"refresh",return_value={}) as refresh:
                assert api.QueryOuraRingData().post(req).status_code==200
                refresh.assert_called_once_with(device)
            with patch.object(ManagedToken,"refresh",side_effect=ManagedToken.ManagedOuraError("Oura authorization expired")):
                failed=api.QueryOuraRingData().post(req)
                assert failed.status_code==503 and "expired" in failed.data["message"]
            participant_view.institute.has_permission=lambda *args:False
            with patch.object(ManagedToken,"refresh",side_effect=AssertionError("unauthorized refresh")):
                assert api.QueryOuraRingData().post(req).status_code==403
            req.data["RequestType"]="RequestOverview"
            with patch.object(DataManager,"loadOuraRingData",return_value=sample):
                assert api.QueryOuraRingData().post(req).status_code==200
            # Existing OAuth route branches remain available for ordinary devices.
            participant_view.institute.has_permission=lambda *args:True
            for kind in ("VerifyToken","SetAuthPeriod","DeleteAuthentication"):
                device.auth={"token":"synthetic","refresh_token":"synthetic-refresh"}
                req.data["RequestType"]=kind
                response=api.OuraRingAuthHandler().post(req)
                assert response.status_code==(200 if kind=="DeleteAuthentication" else 400)
                assert "administrator" not in str(response.data)
            # Existing OAuth mode still dispatches to its original loader.
            device.auth={"token":"synthetic","refresh_token":"synthetic-refresh"}
            with patch.object(DataManager,"loadOuraRingData",side_effect=RuntimeError("native loader reached")):
                try:DataManager.refreshOuraRingData(device)
                except RuntimeError as exc:assert str(exc)=="native loader reached"
                else:raise AssertionError("native OAuth path was bypassed")
    ''')


def test_normal_authenticated_request_production_csrf_and_access_checks(tmp_path):
    isolated(tmp_path, '''
        from django.core.management import call_command
        from django.test import Client, override_settings
        from django.middleware.csrf import _get_new_csrf_string
        from django.urls import path
        from Server import models
        from Server.APIs import OuraRingDashboard as api
        from modules.OURA import DataManager
        import importlib, sys, types
        call_command("migrate", verbosity=0, interactive=False)
        user=models.PlatformUser.objects.create_user(email="oura-test@example.invalid",password="synthetic-only",user_name="Synthetic")
        with override_settings(DEBUG=False, ALLOWED_HOSTS=["bravo.test"], ROOT_URLCONF="synthetic_oura_urls",
                MIDDLEWARE=["django.contrib.sessions.middleware.SessionMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware"]):
            api=importlib.reload(api)
            urls=types.ModuleType("synthetic_oura_urls")
            urls.urlpatterns=[path("query",api.QueryOuraRingData.as_view()),path("auth",api.OuraRingAuthHandler.as_view())]
            sys.modules[urls.__name__]=urls
            client=Client(enforce_csrf_checks=True,HTTP_HOST="bravo.test")
            payload={"ParticipantId":"synthetic","RequestType":"RequestOverview"}
            assert client.post("/query",payload,content_type="application/json",secure=True).status_code==403
            assert client.login(email="oura-test@example.invalid",password="synthetic-only")
            assert client.post("/query",payload,content_type="application/json",secure=True).status_code==403
            csrf=_get_new_csrf_string();client.cookies["csrftoken"]=csrf
            person=SimpleNamespace(institute=SimpleNamespace(has_permission=lambda *args:True))
            device=SimpleNamespace(auth={"managed_token_file":True},date_periods=[])
            with patch.object(api.Database,"checkAccessPermission",return_value=True), \\
                 patch.object(api.models.Participant,"find",return_value=person), \\
                 patch.object(api.models.OuraRingDevice,"find",return_value=device), \\
                 patch.object(DataManager,"loadOuraRingData",return_value={"Sleep":[]}):
                kwargs={"content_type":"application/json","secure":True,"HTTP_X_CSRFTOKEN":csrf,"HTTP_ORIGIN":"https://bravo.test"}
                assert client.post("/query",payload,**kwargs).status_code==200
                auth=client.post("/auth",dict(payload,RequestType="RequestURL"),**kwargs)
                assert auth.status_code==200 and auth.json()=={"ManagedByServer":True,"DatePeriods":[],"CanRefresh":True}
                device.auth={"token":"synthetic","refresh_token":"synthetic"}
                legacy=client.post("/auth",dict(payload,RequestType="RequestURL"),**kwargs)
                assert legacy.status_code==200 and legacy.json()==[]
                device.auth={"managed_token_file":True}
                person.institute.has_permission=lambda *args:False
                viewer=client.post("/auth",dict(payload,RequestType="RequestURL"),**kwargs)
                assert viewer.json()["CanRefresh"] is False
                with patch.object(api.Database,"checkAccessPermission",return_value=False):
                    assert client.post("/query",payload,**kwargs).status_code==403
                assert client.post("/query",payload,content_type="application/json",secure=True,HTTP_X_CSRFTOKEN=csrf,HTTP_ORIGIN="https://wrong.test").status_code==403
    ''')
