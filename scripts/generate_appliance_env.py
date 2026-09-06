#!/usr/bin/env python3
"""Create the ignored environment file for the local BRAVO Docker stack."""

import argparse
import base64
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--rcs08-neural-source", type=Path, required=True)
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    neural_source = args.rcs08_neural_source.expanduser().resolve()
    if not neural_source.is_dir():
        parser.error(f"RCS08 neural source folder does not exist: {neural_source}")

    values = {
        "BRAVO_HTTP_PORT": str(args.port),
        "MYSQL_DATABASE": "BRAVOServer",
        "MYSQL_USER": "BRAVOAdmin",
        "MYSQL_ROOT_PASSWORD": secrets.token_urlsafe(32),
        "MYSQL_PASSWORD": secrets.token_urlsafe(32),
        "DATASERVER_ENCRYPTION": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "DATASERVER_HASHKEY": secrets.token_urlsafe(48),
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "RCS08_NEURAL_SOURCE": str(neural_source),
        "RCS08_OURA_START_DATE": "2025-01-01",
    }

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(args.output, flags, 0o600)
    except FileExistsError:
        parser.error(f"{args.output} already exists; refusing to replace appliance secrets")

    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.writelines(f"{key}={value}\n" for key, value in values.items())

    print(f"Created {args.output} with mode 0600 for http://localhost:{args.port}")


if __name__ == "__main__":
    main()
