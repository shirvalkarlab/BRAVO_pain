#!/usr/bin/env python3
"""Run synthetic upstream tests in a fresh, service-free process environment.

The temporary settings module is on PYTHONPATH so spawned replay/helper workers
inherit the same disposable database, rather than falling back to live settings.
"""
import os
from pathlib import Path
import sys
import tempfile


def main():
    from cryptography.fernet import Fernet
    root = Path(__file__).resolve().parents[1]
    app = root / "BRAVO"
    with tempfile.TemporaryDirectory(prefix="bravo-portable-") as temporary:
        temp = Path(temporary)
        (temp / "bravo_portable_settings.py").write_text('''import os
SECRET_KEY = "synthetic-isolated-tests-only"
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "rest_framework", "Server"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ["BRAVO_ISOLATED_DB"]}}
AUTH_USER_MODEL = "Server.PlatformUser"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
DATASERVER_PATH = os.environ["DATASERVER_PATH"]
REST_FRAMEWORK = {}
''')
        os.environ.clear()
        pythonpath = os.pathsep.join(map(str, (temp, app, app / "modules")))
        os.environ.update(
            PATH=os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin")),
            HOME=temporary, TMPDIR=temporary,
            PYTHONPATH=pythonpath,
            DATASERVER_PATH=temporary + os.sep,
            DATASERVER_ENCRYPTION=Fernet.generate_key().decode(),
            DATASERVER_HASHKEY="synthetic-isolation",
            BRAVO_ISOLATED_DB=str(temp / "test.sqlite3"),
            DJANGO_SETTINGS_MODULE="bravo_portable_settings",
            BRAVO_REMEMBER_REQUESTS="0", SAVED_ANSWERS_REFRESH="0",
            BRAVO_POOL_JOBS="2", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
            MKL_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1",
            MPLCONFIGDIR=str(temp / "mpl"), NUMBA_CACHE_DIR=str(temp / "numba"),
        )
        sys.path[:0] = [str(temp), str(app), str(app / "modules")]
        import django
        django.setup()
        from django.core.management import call_command
        call_command("migrate", verbosity=0, interactive=False)
        import pytest
        suites = [str(app / "modules" / name / "tests") for name in (
            "ClosedLoopDeployment", "StimOptimizer", "CacheStore", "DecodeCommon", "ControlAnalyses",
            "Biomarkers", "MedtronicPercept", "SurveyForms", "StimRL"
        ) if (app / "modules" / name / "tests").is_dir()]
        arguments = sys.argv[1:] or suites
        return pytest.main(["-c", str(app / "modules" / "pytest.ini"), *arguments,
                            "--import-mode=importlib", "-m", "not store and not live", "-q", "-W", "ignore"])


if __name__ == "__main__":
    raise SystemExit(main())
