"""Exercise the real image template preparation on synthetic built assets."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from django.template import Context, Engine

SCRIPT = Path(__file__).resolve().parents[2] / "deploy/prepare-frontend.mjs"


def test_prepared_page_renders_csrf_and_identifies_exact_static_bytes(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node is required to exercise container frontend preparation")
    (tmp_path / "build/static/js").mkdir(parents=True)
    payload = b"console.log('synthetic frontend');"
    (tmp_path / "build/static/js/main.test.js").write_bytes(payload)
    (tmp_path / "build/index.html").write_text(
        '<html><head><script src="/static/js/main.test.js"></script></head><body><div id="root"></div></body></html>'
    )
    revision = "a" * 40
    subprocess.run(["node", str(SCRIPT)], cwd=tmp_path,
                   env={**os.environ, "REACT_APP_BUILD_REVISION": revision}, check=True)
    html = (tmp_path / "build/index.html").read_text()
    rendered = Engine().from_string(html).render(Context({"csrf_token": "synthetic-csrf"}))
    assert 'name="csrfmiddlewaretoken" value="synthetic-csrf"' in rendered
    assert f'name="bravo-build-revision" content="{revision}"' in rendered
    identity = json.loads((tmp_path / "build/static/build-identity.json").read_text())
    assert identity == {"revision": revision, "assets": {
        "/static/js/main.test.js": hashlib.sha256(payload).hexdigest()
    }}


def test_unidentified_build_is_refused(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node is required to exercise container frontend preparation")
    result = subprocess.run(["node", str(SCRIPT)], cwd=tmp_path,
        env={**os.environ, "REACT_APP_BUILD_REVISION": "unverified-local-build"}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "full accepted Git commit" in result.stderr
