"""Fresh installations load real URL routes without optional vendor credentials."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

APP = Path(__file__).resolve().parents[2] / "BRAVO"
SETUP = '''
import os
import socket
from unittest.mock import patch
from types import SimpleNamespace
from cryptography.fernet import Fernet
os.environ["DATASERVER_ENCRYPTION"] = Fernet.generate_key().decode()
os.environ["DATASERVER_HASHKEY"] = "synthetic-only"
def no_network(*args, **kwargs):
    raise AssertionError("optional integration attempted network access")
socket.socket.connect = no_network
from django.conf import settings
settings.configure(
    SECRET_KEY="synthetic-only", DEBUG=True,
    INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "Server"],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    AUTH_USER_MODEL="Server.PlatformUser", DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    ROOT_URLCONF="BRAVO.urls", USE_TZ=True,
)
import django
django.setup()
'''


def isolated(tmp_path, code):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path),
        "PYTHONPATH": os.pathsep.join((str(APP), str(APP / "modules"))),
        "DATASERVER_PATH": str(tmp_path) + os.sep,
        "MPLCONFIGDIR": str(tmp_path / "mpl"), "NUMBA_CACHE_DIR": str(tmp_path / "numba"),
        "BRAVO_REMEMBER_REQUESTS": "0", "SAVED_ANSWERS_REFRESH": "0",
        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
    }
    result = subprocess.run([sys.executable, "-c", SETUP + textwrap.dedent(code)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_routes_and_migration_checks_without_oauth(tmp_path):
    isolated(tmp_path, '''
        from django.core.management import call_command
        from django.urls import get_resolver
        assert get_resolver().check() == []
        call_command("migrate", verbosity=0, interactive=False)
    ''')


@pytest.mark.parametrize("provider", ["Fitbit", "GoogleHealth"])
@pytest.mark.parametrize("partial", [False, True])
def test_missing_oauth_is_unavailable_without_network_or_device_creation(tmp_path, provider, partial):
    isolated(tmp_path, f'''
        from modules.{provider} import DataQuery
        from Server.APIs import {provider}Dashboard as api
        if {partial!r}:
            DataQuery.{"FITBIT_CLIENT_ID" if provider == "Fitbit" else "GoogleHealth_CLIENT_ID"} = "synthetic-partial-config"
        import requests
        assert not DataQuery.oauthConfigured()
        with patch.object(requests, "post", side_effect=no_network):
            assert DataQuery.retrieveToken("synthetic-code"{', "verifier"' if provider == 'Fitbit' else ''}) is None
            assert DataQuery.refreshToken({{"refresh_token": "synthetic"}}) is None
        participant = SimpleNamespace()
        user = SimpleNamespace(configuration={{}})
        with patch.object(api.Database, "checkAccessPermission", return_value=True), \\
             patch.object(api.models.Participant, "find", return_value=participant), \\
             patch.object(api.models.{'FitbitDevice' if provider == 'Fitbit' else 'GoogleHealth'}, "find", side_effect=AssertionError("device lookup must follow config check")):
            for request_type in ("RequestURL", "VerifyToken"):
                request = SimpleNamespace(data={{"RequestType": request_type, "ParticipantId": "synthetic"}}, user=user)
                response = api.{provider}AuthHandler().post(request)
                assert response.status_code == 503
                assert "not configured" in response.data["message"]
            request = SimpleNamespace(data={{"RequestType": "Refresh{provider}Data", "ParticipantId": "synthetic"}}, user=user)
            response = api.Query{provider}Data().post(request)
            assert response.status_code == 503
        refresh = api.{'DataManager' if provider == 'Fitbit' else 'DataQuery'}.refresh{provider}Data
        try:
            refresh(None)
        except RuntimeError as error:
            assert "not configured" in str(error)
        else:
            raise AssertionError("missing OAuth must stop service refresh before any device/data access")
    ''')


@pytest.mark.parametrize("provider", ["Fitbit", "GoogleHealth"])
def test_configured_oauth_preserves_token_exchange(tmp_path, provider):
    keys = (['FIBIT_CLIENT_ID', 'FIBIT_CLIENT_SECRET'] if provider == 'Fitbit' else
            ['GoogleHealth_CLIENT_ID', 'GoogleHealth_CLIENT_SECRET', 'GoogleHealth_CLIENT_REDIRECT_URI'])
    isolated(tmp_path, f'''
        for key in {keys!r}:
            os.environ[key] = "synthetic-config"
        from modules.{provider} import DataQuery
        import requests
        assert DataQuery.oauthConfigured()
        token = {{"access_token": "synthetic-access", "refresh_token": "synthetic-refresh"}}
        with patch.object(requests, "post", return_value=SimpleNamespace(json=lambda: dict(token))) as post:
            assert DataQuery.retrieveToken("synthetic-code"{', "verifier"' if provider == 'Fitbit' else ''}) == token
            assert post.call_args.kwargs["data"]["grant_type"] == "authorization_code"
            assert post.call_args.kwargs["data"]["client_id"] == "synthetic-config"
            refreshed = DataQuery.refreshToken({{**token, "timezoneOffset": 0}})
            assert refreshed["access_token"] == token["access_token"]
            assert post.call_args.kwargs["data"]["grant_type"] == "refresh_token"
        from Server.APIs import {provider}Dashboard as api
        participant = SimpleNamespace()
        user = SimpleNamespace(configuration={{}})
        device = SimpleNamespace(auth={{}}, pkce="synthetic-verifier", uid="synthetic-device")
        manager = api.{'DataManager' if provider == 'Fitbit' else 'DataQuery'}
        with patch.object(api.Database, "checkAccessPermission", return_value=True), \\
             patch.object(api.models.Participant, "find", return_value=participant), \\
             patch.object(api.models.{'FitbitDevice' if provider == 'Fitbit' else 'GoogleHealth'}, "find", return_value=device):
            request = SimpleNamespace(data={{"RequestType": "RequestURL", "ParticipantId": "synthetic"}}, user=user)
            response = api.{provider}AuthHandler().post(request)
            assert response.status_code == 200
            assert "client_id=synthetic-config" in response.data["OAuthURL"]
            device.auth = dict(token)
            request.data["RequestType"] = "Refresh{provider}Data"
            with patch.object(manager, "refresh{provider}Data") as refresh:
                assert api.Query{provider}Data().post(request).status_code == 200
                refresh.assert_called_once_with(device)
        # The real service passes its configuration gate before reading saved data.
        device.owner = participant
        class ReachedDataLoad(Exception):
            pass
        with patch.object(manager, "load{provider}Data", side_effect=ReachedDataLoad):
            try:
                manager.refresh{provider}Data(device)
            except ReachedDataLoad:
                pass
            else:
                raise AssertionError("configured service did not reach its normal data loader")
    ''')
