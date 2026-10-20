"""The portable runner cannot inherit credentials/services and propagates failure."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("should_fail", [False, True])
def test_runner_isolation_cleanup_and_exit_status(tmp_path, should_fail):
    root = Path(__file__).resolve().parents[2]
    evidence = tmp_path / "evidence.json"
    probe = tmp_path / "test_probe.py"
    probe.write_text(f'''
import json
import os
from pathlib import Path
def test_isolation():
    from django.conf import settings
    from Server.models import Participant
    assert "REDIS_HOST" not in os.environ
    assert "BRAVO_DATABASE" not in os.environ
    assert "TEST_UNRELATED_SECRET" not in os.environ
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert Participant.objects.count() == 0
    assert os.environ["SAVED_ANSWERS_REFRESH"] == "0"
    assert os.environ["BRAVO_POOL_JOBS"] == "2"
    Path({str(evidence)!r}).write_text(json.dumps({{"directory": os.environ["HOME"]}}))
    assert not {should_fail!r}, "synthetic deliberate failure"
''')
    environment = dict(os.environ, REDIS_HOST="unreachable.invalid", BRAVO_DATABASE="never-use",
                       TEST_UNRELATED_SECRET="synthetic-only")
    result = subprocess.run([sys.executable, str(root / "scripts/run_portable_tests.py"), str(probe)],
                            cwd=root, env=environment, capture_output=True, text=True, timeout=90)
    assert result.returncode == int(should_fail), result.stdout + result.stderr
    directory = Path(json.loads(evidence.read_text())["directory"])
    assert not directory.exists()
