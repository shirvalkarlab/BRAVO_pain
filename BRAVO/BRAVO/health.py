import os
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def health(request):
    """Report only whether the appliance's required local dependencies work."""
    checks = {"database": False, "storage": False}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone() == (1,)
    except Exception:
        pass

    storage_path = Path(settings.DATASERVER_PATH)
    checks["storage"] = storage_path.is_dir() and os.access(storage_path, os.R_OK | os.W_OK)

    healthy = all(checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status=200 if healthy else 503,
    )
