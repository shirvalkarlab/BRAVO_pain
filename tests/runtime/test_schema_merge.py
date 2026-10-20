"""Exercise both source migration histories on disposable SQLite databases.

No production settings, credentials, configuration files or services are loaded.
These tests check schema/data compatibility; MySQL deployment is a separate gate.
"""
import os
from pathlib import Path
import sys
import tempfile

from cryptography.fernet import Fernet
import django
from django.conf import settings
import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "BRAVO"
sys.path.insert(0, str(APP_ROOT))
sys.path.append(str(APP_ROOT / "modules"))
_storage = tempfile.TemporaryDirectory(prefix="bravo-schema-storage-")
os.environ["DATASERVER_PATH"] = _storage.name + os.sep
os.environ["DATASERVER_ENCRYPTION"] = Fernet.generate_key().decode()
os.environ["DATASERVER_HASHKEY"] = "synthetic-schema-test-key"
os.environ.pop("REDIS_HOST", None)

if not settings.configured:
    settings.configure(
        SECRET_KEY="synthetic-schema-test-only",
        INSTALLED_APPS=[
            "django.contrib.auth", "django.contrib.contenttypes", "Server",
        ],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        AUTH_USER_MODEL="Server.PlatformUser",
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
    )
django.setup()

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.management import call_command


@pytest.fixture
def database(tmp_path):
    connection.close()
    # Refuse a misconfigured invocation instead of touching an inherited DB.
    assert connection.vendor == "sqlite"
    connection.settings_dict["NAME"] = str(tmp_path / "schema.sqlite3")
    yield connection
    connection.close()


@pytest.mark.parametrize("predecessor", [
    None,
    "0010_recording_fs_scaling_factor",
    "0009_sourcefile_device_institute",
])
def test_schema_upgrade_preserves_both_histories(database, predecessor):
    executor = MigrationExecutor(database)
    assert executor.loader.detect_conflicts() == {}
    target = [("Server", "0011_merge_fixel_prasad")]

    if predecessor:
        executor.migrate([("Server", predecessor)])
        state = executor.loader.project_state([("Server", predecessor)])
        SourceFile = state.apps.get_model("Server", "SourceFile")
        Recording = state.apps.get_model("Server", "Recording")
        source_kwargs = {"uid": "synthetic-source", "metadata": {"UniqueHashed": "abc123"}}
        recording_kwargs = {"uid": "synthetic-recording", "metadata": {"source": "synthetic"}}
        if predecessor.startswith("0010"):
            recording_kwargs["fs_scaling_factor"] = 1.025
        else:
            source_kwargs.update(unique_hashed="abc123", device="synthetic-device", institute="synthetic-lab")
            recording_kwargs["content_fingerprint"] = "synthetic-fingerprint"
        source = SourceFile.objects.create(**source_kwargs)
        Recording.objects.create(source=source, **recording_kwargs)

    executor = MigrationExecutor(database)
    executor.migrate(target)
    state = executor.loader.project_state(target)
    SourceFile = state.apps.get_model("Server", "SourceFile")
    Recording = state.apps.get_model("Server", "Recording")
    assert {"unique_hashed", "device", "institute"} <= {f.name for f in SourceFile._meta.fields}
    assert {"fs_scaling_factor", "content_fingerprint"} <= {f.name for f in Recording._meta.fields}
    assert state.apps.get_model("Server", "GoogleHealth")
    assert state.apps.get_model("Server", "LLMCache")

    if predecessor:
        source = SourceFile.objects.get(pk="synthetic-source")
        recording = Recording.objects.get(pk="synthetic-recording")
        assert source.unique_hashed == "abc123"
        assert recording.metadata == {"source": "synthetic"}
        if predecessor.startswith("0010"):
            assert recording.fs_scaling_factor == 1.025
            assert recording.content_fingerprint == ""
        else:
            assert recording.content_fingerprint == "synthetic-fingerprint"
            assert recording.fs_scaling_factor == 1
            assert (source.device, source.institute) == ("synthetic-device", "synthetic-lab")

    # The same command can be rerun after a restart, with no pending operation.
    assert MigrationExecutor(database).migration_plan(target) == []
    call_command("makemigrations", "Server", check=True, dry_run=True, verbosity=0)


def test_recording_serializer_retains_fixel_scaling():
    from Server.models import Recording, SourceFile
    source = SourceFile(uid="synthetic-source", metadata={})
    recording = Recording(source=source, fs_scaling_factor=1.025, content_fingerprint="synthetic")
    assert recording.get_info()["SamplingRateScaling"] == 1.025
