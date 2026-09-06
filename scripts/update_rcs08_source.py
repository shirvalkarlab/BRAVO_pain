#!/usr/bin/env python3
"""Update only the host Dropbox source path in an appliance environment file."""

import argparse
import os
from pathlib import Path
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_dir():
        parser.error(f"RCS08 neural source folder does not exist: {source}")

    key = "RCS08_NEURAL_SOURCE"
    lines = []
    replaced = False
    with args.env_file.open(encoding="utf-8") as current:
        for line in current:
            if line.startswith(f"{key}="):
                lines.append(f"{key}={source}\n")
                replaced = True
            else:
                lines.append(line)
    if not replaced:
        lines.append(f"{key}={source}\n")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".env.appliance.", dir=args.env_file.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.writelines(lines)
        os.replace(temporary_name, args.env_file)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    print(f"Updated RCS08 neural source to {source}")


if __name__ == "__main__":
    main()
