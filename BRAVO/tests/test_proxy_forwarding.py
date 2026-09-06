"""Actual appliance Nginx/Uvicorn boundary, isolated from deployed services."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request, urlopen

import pytest
from django.test import RequestFactory
from Server import views


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def proxy(tmp_path_factory):
    directory = tmp_path_factory.mktemp("proxy")
    upstream_port, nginx_port = free_port(), free_port()
    while nginx_port == upstream_port:
        nginx_port = free_port()
    (directory / "probe.py").write_text('''import json
async def app(scope, receive, send):
    body = json.dumps({"client": scope["client"][0], "scheme": scope["scheme"],
                       "headers": dict((k.decode(), v.decode()) for k,v in scope["headers"])}).encode()
    await send({"type":"http.response.start", "status":200, "headers":[(b"content-type",b"application/json")]})
    await send({"type":"http.response.body", "body":body})
''')
    production = (Path(__file__).resolve().parents[1] / "bravo_nginx.conf").read_text()
    production = production.replace("listen 80;", f"listen 127.0.0.1:{nginx_port};")
    production = production.replace("127.0.0.1:27286", f"127.0.0.1:{upstream_port}")
    config = directory / "nginx.conf"
    config.write_text(
        f"pid {directory}/nginx.pid;\nerror_log stderr;\nevents {{}}\n"
        + "http { access_log off;\n" + production + "\n}\n"
    )
    processes = []
    with (directory / "process.log").open("w+") as log:
        try:
            processes.append(subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "probe:app", "--app-dir", str(directory),
                 "--host", "127.0.0.1", "--port", str(upstream_port), "--lifespan", "off",
                 "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"], stdout=log, stderr=log,
            ))
            processes.append(subprocess.Popen(
                ["nginx", "-c", str(config), "-p", str(directory), "-g", "daemon off;"],
                stdout=log, stderr=log,
            ))
            url = f"http://127.0.0.1:{nginx_port}"
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urlopen(url + "/healthz", timeout=1) as response:
                        assert response.status == 200
                    break
                except OSError:
                    if any(process.poll() is not None for process in processes) or time.monotonic() > deadline:
                        log.flush()
                        pytest.fail((directory / "process.log").read_text())
                    time.sleep(0.05)
            yield url
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


@pytest.mark.parametrize("route", ["/healthz", "/api/probe", "/socket/probe", "/index"])
@pytest.mark.parametrize("origin", ["198.51.100.23", "2001:db8::23", None])
def test_real_proxy_origin_and_alternate_header(proxy, route, origin):
    headers = {"X-Forward-For": "203.0.113.99", "X-Forwarded-Proto": "https"}
    if origin:
        headers["X-Forwarded-For"] = origin
    with urlopen(Request(proxy + route, headers=headers), timeout=5) as response:
        result = json.load(response)
    assert result["client"] == (origin or "127.0.0.1")
    assert result["scheme"] == "https"
    assert "x-forward-for" not in result["headers"]


def test_client_identity_uses_only_resolved_connection():
    assert views.get_client_ip(SimpleNamespace(META={
        "REMOTE_ADDR": "198.51.100.23", "HTTP_X_FORWARD_FOR": "203.0.113.99",
        "HTTP_X_FORWARDED_FOR": "203.0.113.98",
    })) == "198.51.100.23"
    assert views.get_client_ip(SimpleNamespace(META={"HTTP_X_FORWARD_FOR": "203.0.113.99"})) is None


def test_explicit_ban_cannot_be_evaded_by_alternate_header():
    request = RequestFactory().get("/index", REMOTE_ADDR="198.51.100.23",
                                   HTTP_X_FORWARD_FOR="203.0.113.99")
    with patch.object(views.models.BlacklistRecords, "exists", return_value=True) as banned:
        response = views.Homepage.as_view()(request)
    banned.assert_called_once_with(ip_address="198.51.100.23")
    assert b"404-NOTFOUND" in response.content
