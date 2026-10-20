"""Pure cache identities for recordings whose authoritative labels can change."""
import hashlib
import json


def row_identity(uid, hashed, rtype, metadata):
    """Include the full JSON metadata, preserving missing versus explicitly empty evidence."""
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")
    return (str(uid), str(hashed), str(rtype), hashlib.sha256(encoded).hexdigest())


def digest(rows, start_s, config_digest):
    """Stable under row order; change with labels, implant cutoff or private configuration."""
    payload = [sorted(rows), float(start_s or 0.0), str(config_digest)]
    encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf8")
    return hashlib.blake2b(encoded, digest_size=16).hexdigest()
