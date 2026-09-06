#!/usr/bin/env python3
"""Preserve legacy participant assets outside source/image publication.

Never replaces a different destination file or removes an original. The same
container paths are supplied by read-only Compose mounts after this migration.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile


ASSET_DIRECTORIES = {
    "config": "BRAVO/config",
    "psd_lsb_models": "BRAVO/modules/Biomarkers/data/psd_lsb_models",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root):
    root = Path(root)
    destination = root / "secrets/runtime_assets"
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.is_symlink():
        raise ValueError("Runtime asset directory must not be a symlink")
    os.chmod(destination, 0o700)
    planned = []
    for category, relative in ASSET_DIRECTORIES.items():
        folder = destination / category
        if folder.is_symlink():
            raise ValueError("Runtime asset category must not be a symlink")
        folder.mkdir(mode=0o700, exist_ok=True)
        source = root / relative
        for original in sorted(source.glob("*")):
            if original.is_symlink() or not original.is_file():
                raise ValueError("Unexpected non-file in legacy runtime assets")
            target = folder / original.name
            if target.is_symlink():
                raise ValueError("Runtime asset must not be a symlink")
            if target.exists() and digest(original) != digest(target):
                raise ValueError(f"Conflicting private runtime asset: {category}/{original.name}")
            planned.append((original, target))
    # Check all conflicts before making any copies.
    for original, target in planned:
        if not target.exists():
            descriptor, temporary = tempfile.mkstemp(dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(original.read_bytes())
                os.link(temporary, target)  # Refuse concurrent replacement.
            finally:
                os.unlink(temporary)
        os.chmod(target, 0o600)
        if digest(original) != digest(target):
            raise ValueError("Runtime asset verification failed")
    assets = []
    for category in ASSET_DIRECTORIES:
        for path in sorted((destination / category).iterdir()):
            if path.is_symlink() or not path.is_file():
                raise ValueError("Unexpected private runtime asset")
            os.chmod(path, 0o600)
            assets.append({"path": str(path.relative_to(destination)),
                           "sha256": digest(path), "bytes": path.stat().st_size})
    manifest = destination / "manifest.json"
    if manifest.is_symlink():
        raise ValueError("Runtime manifest must not be a symlink")
    descriptor, temporary = tempfile.mkstemp(dir=destination)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"version": 1, "assets": assets}, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, manifest)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return assets


if __name__ == "__main__":
    assets = prepare(Path(__file__).resolve().parents[1])
    print(f"Verified {len(assets)} private runtime assets; originals unchanged.")
