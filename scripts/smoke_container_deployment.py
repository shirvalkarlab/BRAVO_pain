#!/usr/bin/env python3
"""Exercise already-built images on an ephemeral CI runner, without source data.

Uses the real Compose/settings/Caddy stack. All state and credentials are new;
the local Caddy CA is trusted only by this process, never installed on the host.
"""
import base64
from contextlib import contextmanager
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
HOST = "bravo-smoke.example.test"


@contextmanager
def localhost_resolution():
    original = socket.getaddrinfo
    def resolve(host, *args, **kwargs):
        return original("127.0.0.1" if host == HOST else host, *args, **kwargs)
    socket.getaddrinfo = resolve
    try:
        yield
    finally:
        socket.getaddrinfo = original


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("This destructive disposable smoke is limited to GitHub-hosted CI runners")
    revision = os.environ["BUILD_REVISION"]
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise SystemExit("BUILD_REVISION must identify the full accepted commit")
    for image in ("backend", "web"):
        actual = subprocess.check_output([
            "docker", "inspect", "--format", '{{index .Config.Labels "org.opencontainers.image.revision"}}',
            f"bravo-aditya-{image}:{revision}",
        ], text=True).strip()
        assert actual == revision, (image, actual)
    with tempfile.TemporaryDirectory(prefix="bravo-container-smoke-") as directory:
        root = Path(directory)
        for name in ("db", "data", "private"):
            (root / name).mkdir()
        (root / "private" / "backup-rehearsal.txt").write_text("synthetic-private-provenance")
        environment = {
            "BUILD_REVISION": revision,
            "BRAVO_DOMAIN": HOST,
            "BRAVO_BIND_ADDRESS": "127.0.0.1",
            "BRAVO_DB_DIRECTORY": str(root / "db"),
            "BRAVO_DATA_DIRECTORY": str(root / "data"),
            "BRAVO_PRIVATE_DIRECTORY": str(root / "private"),
            "MYSQL_ROOT_PASSWORD": secrets.token_hex(32),
            "BRAVO_DATABASE_PASSWORD": secrets.token_hex(32),
            "DATASERVER_ENCRYPTION": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "DATASERVER_HASHKEY": secrets.token_hex(32),
            "DJANGO_SECRET_KEY": secrets.token_hex(48),
            "BRAVO_WEB_WORKERS": "1", "BRAVO_POOL_JOBS": "1",
        }
        env_file = root / "synthetic.env"
        env_file.write_text("".join(f"{k}={v}\n" for k, v in environment.items()))
        env_file.chmod(0o600)
        # Same proxy behavior, with an ephemeral local CA instead of public ACME.
        caddy = root / "Caddyfile"
        caddy.write_text((ROOT / "deploy/Caddyfile").read_text().replace(
            "    encode zstd gzip", "    tls internal\n    encode zstd gzip"))
        override = root / "compose-smoke.json"
        override.write_text(json.dumps({"services": {"web": {"volumes": [
            f"{caddy}:/etc/caddy/Caddyfile:ro"
        ]}}}))
        # Do not let a caller's deployment variables override this synthetic file.
        compose_env = {key: value for key, value in os.environ.items()
                       if not key.startswith(("BRAVO_", "DATASERVER_", "DJANGO_", "MYSQL_", "BUILD_REVISION"))}
        compose = ["docker", "compose", "--project-name", f"bravo-smoke-{os.getpid()}",
                   "--env-file", str(env_file), "-f", str(ROOT / "docker-compose.yml"),
                   "-f", str(override)]
        def run(*args, **kwargs):
            return subprocess.run(compose + list(args), check=True, timeout=240, env=compose_env, **kwargs)
        def app_python(code):
            run("run", "--rm", "-T", "app", "python", "-c", code)
        try:
            run("config", "--quiet")
            run("up", "-d", "--wait", "mysql", "redis")
            run("run", "--rm", "--no-deps", "--user", "0", "app", "chown", "10001:10001", "/data/bravo")
            run("run", "--rm", "-T", "app", "python", "-m", "django", "migrate", "--noinput")
            run("run", "--rm", "-T", "app", "python", "-m", "django", "makemigrations", "--check", "--dry-run")
            run("run", "--rm", "-T", "-e", "BRAVO_SYNTHETIC_INGEST_SMOKE=1",
                "-e", "GITHUB_ACTIONS=true", "-e", "RUNNER_ENVIRONMENT=github-hosted",
                "app", "python", "-c", (ROOT / "scripts/mysql_ingest_precision_smoke.py").read_text())
            # This regression checks the source statistical runtime and a fitted
            # synthetic repeated-measures example, not participant validation.
            run("run", "--rm", "-T", "app", "Rscript", "-e", '''
stopifnot(as.character(getRversion()) == "4.3.3")
stopifnot(as.character(packageVersion("lme4")) == "1.1.35.1")
stopifnot(as.character(packageVersion("lmerTest")) == "3.1.3")
stopifnot(as.character(packageVersion("emmeans")) == "1.10.0")
set.seed(123); d <- expand.grid(subject=factor(1:12), time=0:5)
d$y <- 2 + 0.7*d$time + rep(rnorm(12),6) + rnorm(nrow(d),sd=0.1)
fit <- lmerTest::lmer(y ~ time + (1|subject), data=d)
stopifnot(abs(lme4::fixef(fit)[["time"]] - 0.7) < 0.1)
stopifnot(all(is.finite(as.data.frame(emmeans::emmeans(fit, ~time, at=list(time=c(0,5))))$emmean)))
cat("Pinned R mixed-model smoke passed\\n")
''')
            app_python("import pymer4; import rpy2.robjects as ro; assert str(ro.r('R.version$major')[0]) == '4'")
            password = secrets.token_hex(24)
            # Secret travels on stdin, never in process arguments or CI logs.
            run("run", "--rm", "-T", "app", "python", "-c",
                "import sys,django;django.setup();from Server.models import PlatformUser;"
                "PlatformUser.create('synthetic-smoke@example.test',sys.stdin.read(),'Synthetic smoke')",
                input=password, text=True)
            run("up", "-d", "app", "web")
            ca = root / "local-root.crt"
            deadline = time.monotonic() + 90
            while True:
                try:
                    run("cp", "web:/data/caddy/pki/authorities/local/root.crt", str(ca),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except subprocess.CalledProcessError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(2)
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(ca))),
                urllib.request.HTTPCookieProcessor(jar))
            def request(path, data=None, csrf=None):
                headers = {"Content-Type": "application/json", "Origin": f"https://{HOST}"}
                if csrf:
                    headers["X-CSRFToken"] = csrf
                req = urllib.request.Request(f"https://{HOST}{path}",
                    data=None if data is None else json.dumps(data).encode(), headers=headers)
                with opener.open(req, timeout=20) as response:
                    return response.read()
            with localhost_resolution():
                while True:
                    try:
                        html = request("/").decode()
                        break
                    except (urllib.error.URLError, ConnectionError):
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(3)
                assert f'name="bravo-build-revision" content="{revision}"' in html
                assert 'name="csrfmiddlewaretoken"' in html
                identity = json.loads(request("/static/build-identity.json"))
                assert identity["revision"] == revision
                assert identity["assets"], "No compiled frontend assets identified"
                for path, digest in identity["assets"].items():
                    assert hashlib.sha256(request(path)).hexdigest() == digest, path
                login = json.loads(request("/api/login", {"Email": "synthetic-smoke@example.test", "Password": password}))
                assert login["Email"] == "synthetic-smoke@example.test"
                # Login rotates CSRF: use freshly rendered DOM token, as the UI does.
                html = request("/").decode()
                token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)[1]
                assert json.loads(request("/api/queryProfile", {}, token))["Email"] == login["Email"]
                try:
                    request("/api/queryProfile", {})
                    raise AssertionError("Authenticated POST without CSRF must fail")
                except urllib.error.HTTPError as exc:
                    assert exc.code == 403
                run("restart", "app")
                # Same cookie and MySQL data must survive replacement of workers.
                for attempt in range(30):
                    try:
                        assert json.loads(request("/api/queryProfile", {}, token))["Email"] == login["Email"]
                        break
                    except urllib.error.HTTPError as exc:
                        if exc.code not in (502,503) or attempt == 29:
                            raise
                        time.sleep(2)
            # Rehearse backup/restore before any participant ingestion. Database,
            # encrypted data and keys are captured together in an owner-only root.
            app_python("import os;from pathlib import Path;from cryptography.fernet import Fernet;"
                       "Path(os.environ['DATASERVER_PATH'],'smoke-preservation.enc').write_bytes("
                       "Fernet(os.environ['DATASERVER_ENCRYPTION']).encrypt(b'synthetic-restored-payload'))")
            backup = root / "backup"
            backup.mkdir(mode=0o700)
            def save_private(name, payload):
                path = backup / name
                path.write_bytes(payload)
                path.chmod(0o600)
            dump = run("exec", "-T", "mysql", "sh", "-c",
                'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --no-tablespaces '
                '--set-gtid-purged=OFF --routines --triggers --events bravo_aditya',
                stdout=subprocess.PIPE).stdout
            save_private("database.sql", dump)
            data_tar = run("run", "--rm", "-T", "--user", "0", "app", "tar", "-czf", "-", "-C", "/data/bravo", ".",
                           stdout=subprocess.PIPE).stdout
            save_private("data.tar.gz", data_tar)
            save_private("environment.env", env_file.read_bytes())
            # Only a synthetic provenance sentinel exists in private inputs;
            # no clinical values are filled in as part of backup or restore.
            shutil.copytree(root / "private", backup / "private")
            checksums = {str(p.relative_to(backup)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in backup.rglob("*") if p.is_file()}
            save_private("sha256.json", json.dumps(checksums).encode())
            assert all(hashlib.sha256((backup / name).read_bytes()).hexdigest() == digest
                       for name, digest in checksums.items())
            # A separate schema and fresh storage directory ensure this really
            # restores a backup instead of merely restarting the original data.
            run("exec", "-T", "mysql", "sh", "-c", 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot',
                input=b"CREATE DATABASE bravo_restore; GRANT ALL ON bravo_restore.* TO 'bravo_aditya'@'%';")
            run("exec", "-T", "mysql", "sh", "-c", 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot bravo_restore',
                input=(backup / "database.sql").read_bytes())
            restored = root / "restored-data"
            restored.mkdir()
            restore_env = backup / "restore.env"
            restore_env.write_text((backup / "environment.env").read_text().replace(
                f"BRAVO_DATA_DIRECTORY={root / 'data'}", f"BRAVO_DATA_DIRECTORY={restored}").replace(
                f"BRAVO_PRIVATE_DIRECTORY={root / 'private'}", f"BRAVO_PRIVATE_DIRECTORY={backup / 'private'}"))
            restore_env.chmod(0o600)
            restore_override = root / "restore-compose.json"
            restore_override.write_text(json.dumps({"services": {"app": {"environment": {"BRAVO_DATABASE": "bravo_restore"}}}}))
            compose[compose.index("--env-file") + 1] = str(restore_env)
            compose.extend(["-f", str(restore_override)])
            run("run", "--rm", "-T", "--user", "0", "app", "sh", "-c",
                "tar -xzf - -C /data/bravo && chown -R 10001:10001 /data/bravo",
                input=(backup / "data.tar.gz").read_bytes())
            app_python("import os,django;django.setup();from pathlib import Path;from cryptography.fernet import Fernet;"
                       "from django.db import connection;assert connection.settings_dict['NAME']=='bravo_restore';"
                       "assert Fernet(os.environ['DATASERVER_ENCRYPTION']).decrypt("
                       "Path(os.environ['DATASERVER_PATH'],'smoke-preservation.enc').read_bytes())==b'synthetic-restored-payload';"
                       "assert Path('/run/bravo-private/backup-rehearsal.txt').read_text()=='synthetic-private-provenance'")
            run("up", "-d", "--force-recreate", "app")
            with localhost_resolution():
                # Existing session restored from SQL, followed by a new login.
                for attempt in range(30):
                    try:
                        assert json.loads(request("/api/queryProfile", {}, token))["Email"] == login["Email"]
                        break
                    except urllib.error.HTTPError as exc:
                        if exc.code not in (502,503) or attempt == 29:
                            raise
                        time.sleep(2)
                jar.clear()
                assert json.loads(request("/api/login", {"Email": login["Email"], "Password": password}))["Email"] == login["Email"]
                html = request("/").decode()
                restored_token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)[1]
                assert json.loads(request("/api/queryProfile", {}, restored_token))["Email"] == login["Email"]
            print("Container smoke passed: MySQL migrations, pinned R fit, TLS, CSRF auth, static hashes, revision, restart and separate database/storage backup restoration")
        finally:
            # Never print environment/config: this keeps synthetic credentials out
            # of logs and exercises the same operational logging rule as deployment.
            subprocess.run(compose + ["logs", "--no-color", "--tail", "100", "app", "web"], timeout=30, env=compose_env)
            run("down", "--volumes", "--remove-orphans")
            # MySQL owns its bind-mounted files; remove only this disposable root.
            subprocess.run(["docker", "run", "--rm", "-v", f"{root}:/smoke", "alpine:3.21",
                "sh", "-c", "rm -rf /smoke/db /smoke/data /smoke/restored-data"], check=True, timeout=60)


if __name__ == "__main__":
    main()
