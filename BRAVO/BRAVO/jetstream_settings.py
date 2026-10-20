"""Explicit production settings; no implicit ingestion or refresh jobs."""
import os

os.environ["DJANGO_MODE"] = "PRODUCTION"
for _name in (
    "DJANGO_SECRET_KEY", "DATASERVER_ENCRYPTION", "DATASERVER_HASHKEY",
    "DATASERVER_PATH", "BRAVO_DATABASE", "BRAVO_DATABASE_USER",
    "BRAVO_DATABASE_PASSWORD", "BRAVO_DATABASE_HOST", "BRAVO_DATABASE_PORT",
    "SERVER_HOST", "SERVER_ADDRESS",
):
    if not os.environ.get(_name):
        raise RuntimeError(f"Required deployment setting is missing: {_name}")
if not os.environ["SERVER_ADDRESS"].startswith("https://"):
    raise RuntimeError("SERVER_ADDRESS must use HTTPS for Jetstream")

from .settings import *  # noqa: E402,F403

BRAVO_TRUSTED_PROXY_CIDRS = os.environ.get("BRAVO_TRUSTED_PROXY_CIDRS", "").split()
DEBUG = False
ALLOWED_HOSTS = [os.environ["SERVER_HOST"]]
CSRF_TRUSTED_ORIGINS = [os.environ["SERVER_ADDRESS"].rstrip("/")]
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True
STATIC_ROOT = os.environ.get("BRAVO_STATIC_ROOT", "/app/staticfiles")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}
