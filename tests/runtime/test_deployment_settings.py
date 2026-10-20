"""Check the production overlay without loading a database or source settings."""
import os
import json
import shutil
from pathlib import Path
import runpy
import subprocess
import sys
import types

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "BRAVO"
REQUIRED = (
    "DJANGO_SECRET_KEY", "DATASERVER_ENCRYPTION", "DATASERVER_HASHKEY",
    "DATASERVER_PATH", "BRAVO_DATABASE", "BRAVO_DATABASE_USER",
    "BRAVO_DATABASE_PASSWORD", "BRAVO_DATABASE_HOST", "BRAVO_DATABASE_PORT",
    "SERVER_HOST", "SERVER_ADDRESS",
)


@pytest.fixture
def production_env(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(APP_ROOT))
    # Explicitly isolate the imported development settings: these tests exercise
    # the production overlay, while schema integration is tested separately.
    monkeypatch.setitem(sys.modules, "BRAVO.settings", types.ModuleType("BRAVO.settings"))
    for key in REQUIRED:
        monkeypatch.setenv(key, "synthetic-test-value")
    monkeypatch.setenv("DATASERVER_PATH", str(tmp_path))
    monkeypatch.setenv("SERVER_HOST", "bravo.example.test")
    monkeypatch.setenv("SERVER_ADDRESS", "https://bravo.example.test")
    monkeypatch.delenv("BRAVO_STATIC_ROOT", raising=False)


@pytest.mark.parametrize("missing", REQUIRED)
def test_refuses_missing_production_settings(production_env, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        runpy.run_module("BRAVO.jetstream_settings")


def test_refuses_public_http(production_env, monkeypatch):
    monkeypatch.setenv("SERVER_ADDRESS", "http://bravo.example.test")
    with pytest.raises(RuntimeError, match="HTTPS"):
        runpy.run_module("BRAVO.jetstream_settings")


def test_production_cookies_and_proxy_contract(production_env):
    result = runpy.run_module("BRAVO.jetstream_settings")
    assert result["DEBUG"] is False
    assert result["ALLOWED_HOSTS"] == ["bravo.example.test"]
    assert result["CSRF_TRUSTED_ORIGINS"] == ["https://bravo.example.test"]
    for name in ("SESSION_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT"):
        assert result[name] is True
    assert result["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")
    assert result["STATIC_ROOT"] == "/app/staticfiles"


def test_static_root_is_explicitly_overridable(production_env, monkeypatch):
    monkeypatch.setenv("BRAVO_STATIC_ROOT", "/isolated/static")
    result = runpy.run_module("BRAVO.jetstream_settings")
    assert result["STATIC_ROOT"] == "/isolated/static"


def test_worker_config_does_not_register_source_startup_jobs(monkeypatch):
    monkeypatch.delenv("BRAVO_WEB_WORKERS", raising=False)
    monkeypatch.delenv("BRAVO_REQUEST_TIMEOUT", raising=False)
    result = runpy.run_path(str(APP_ROOT.parent / "deploy/gunicorn.conf.py"))
    assert result["workers"] == 4
    assert result["timeout"] == 300
    assert "when_ready" not in result
    assert callable(result["post_worker_init"])
    assert callable(result["worker_exit"])
    monkeypatch.setenv("BRAVO_WEB_WORKERS", "2")
    monkeypatch.setenv("BRAVO_REQUEST_TIMEOUT", "90")
    result = runpy.run_path(str(APP_ROOT.parent / "deploy/gunicorn.conf.py"))
    assert result["workers"] == 2
    assert result["timeout"] == 90


def test_worker_lifecycle_registers_and_runs_pool_cleanup(monkeypatch):
    calls = []
    module = types.ModuleType("modules.DecodeCommon.parallel")
    module.stop_pool_on_signals = lambda: calls.append("signals")
    module.shutdown_pool = lambda: calls.append("shutdown")
    monkeypatch.setitem(sys.modules, "modules.DecodeCommon.parallel", module)
    config = runpy.run_path(str(APP_ROOT.parent / "deploy/gunicorn.conf.py"))
    config["post_worker_init"](None)
    config["worker_exit"](None, None)
    assert calls == ["signals", "shutdown"]


def test_destructive_smoke_refuses_non_hosted_runner():
    result = subprocess.run(
        [sys.executable, str(APP_ROOT.parent / "scripts/smoke_container_deployment.py")],
        env={**os.environ, "GITHUB_ACTIONS": "false"},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "limited to GitHub-hosted CI runners" in result.stderr


@pytest.mark.parametrize("configured", [False, True])
def test_compose_forwards_optional_oauth_only_when_supplied(tmp_path, configured):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose CLI required for rendered deployment contract")
    keys = ("FIBIT_CLIENT_ID", "FIBIT_CLIENT_SECRET", "GoogleHealth_CLIENT_ID",
            "GoogleHealth_CLIENT_SECRET", "GoogleHealth_CLIENT_REDIRECT_URI")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path)}
    # Docker Desktop keeps plugins beside its binary. Reuse only that executable
    # location while keeping the caller's Docker credentials/config out of tests.
    plugins = Path(docker).resolve().parent.parent / "cli-plugins"
    if plugins.is_dir():
        config = tmp_path / ".docker"
        config.mkdir()
        (config / "config.json").write_text(json.dumps({"cliPluginsExtraDirs": [str(plugins)]}))
    for key in ("MYSQL_ROOT_PASSWORD", "BRAVO_DATABASE_PASSWORD", "DATASERVER_ENCRYPTION",
                "DATASERVER_HASHKEY", "DJANGO_SECRET_KEY", "BRAVO_DOMAIN"):
        env[key] = "synthetic-only"
    env["BUILD_REVISION"] = "a" * 40
    for key in ("BRAVO_DB_DIRECTORY", "BRAVO_DATA_DIRECTORY", "BRAVO_PRIVATE_DIRECTORY"):
        env[key] = str(tmp_path / key.lower())
    if configured:
        env.update({key: "synthetic-optional-value" for key in keys})
    empty = tmp_path / "empty.env"
    empty.touch()
    result = subprocess.run([docker, "compose", "--env-file", str(empty), "-f",
                             str(APP_ROOT.parent / "docker-compose.yml"), "config", "--format", "json"],
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    forwarded = json.loads(result.stdout)["services"]["app"]["environment"]
    assert {key: forwarded[key] for key in keys} == {
        key: "synthetic-optional-value" if configured else "" for key in keys
    }


def test_mysql_ingest_smoke_refuses_non_hosted_runner():
    result = subprocess.run(
        [sys.executable, str(APP_ROOT.parent / "scripts/mysql_ingest_precision_smoke.py")],
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "requires the disposable hosted CI harness" in result.stderr


def test_mysql_ingest_equivalent_encoding_fixture_preserves_exact_values():
    module = runpy.run_path(str(APP_ROOT.parent / "scripts/mysql_ingest_precision_smoke.py"))
    first = module["synthetic_document"](0.125)
    alternate = module["synthetic_document"](0.125, alternate_numeric_encoding=True)
    assert first == alternate  # Exact numeric equality, no tolerance or rounding.
    assert json.dumps(first, sort_keys=True) != json.dumps(alternate, sort_keys=True)
