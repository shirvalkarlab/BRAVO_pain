#!/bin/sh
set -eu
# This writes only static assets inside this application container. Database
# migrations, account creation, ingestion and cache refresh are explicit actions.
python -m django collectstatic --noinput
exec gunicorn -c /app/deploy/gunicorn.conf.py BRAVO.asgi:application
