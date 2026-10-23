"""The band requests the pages sent, remembered per participant (the PI, 2026-10-04: "yes do 3b",
decision 435), so the server can work their answers out again when the data change, before anyone
asks (`ClosedLoopDeployment.refresh_saved_answers`).

WHY THE REQUESTS THEMSELVES. A saved answer is filed under a label built from the whole request
(`saved_answers.label`), and the pages build their requests in the browser: the band picked, the
neighbours asked for ahead, the strongest bands the Biomarkers page asks for. Replaying the bodies
the pages actually sent rebuilds exactly the answers they will read, with no second copy of the
browser's request-building rules on the server.

Kept in Redis, one hash per participant (field: a digest of kind and request; value: kind, request,
time last seen), for `KEEP_SECONDS`. Best effort: Redis unreachable means nothing is remembered and
nothing raises; the pages work as before.
"""
import hashlib
import json
import os
import time

from . import locks as _locks

KEY_PREFIX = "bravo:saved_answer_requests:"
#: "0" turns remembering off: the replay job sets it, so its own replays do not keep a request
#: alive that no page has asked for since.
OFF_ENV = "BRAVO_REMEMBER_REQUESTS"
#: How long a request is remembered after it was last sent.
KEEP_SECONDS = 14 * 24 * 3600.0


def _now():
    return time.time()


def _field(kind, body):
    blob = json.dumps([str(kind), body], sort_keys=True, default=str)
    return hashlib.blake2b(blob.encode("utf8"), digest_size=16).hexdigest()


def remember(kind, participant_uid, request_data):
    """Note that ``request_data`` was asked for under ``kind``. Never raises."""
    if os.environ.get(OFF_ENV, "1").strip() == "0":
        return False
    try:
        client = _locks._client()
        if client is None or not participant_uid:
            return False
        body = {k: v for k, v in dict(request_data or {}).items()}
        value = json.dumps({"kind": str(kind), "body": body, "seen": _now()}, sort_keys=True,
                           default=str)
        key = KEY_PREFIX + str(participant_uid)
        client.hset(key, _field(kind, body), value)
        client.expire(key, int(KEEP_SECONDS))
        return True
    except Exception:                                          # noqa: BLE001 -- best effort
        return False


def recent(participant_uid):
    """The remembered requests seen within `KEEP_SECONDS`, newest first: ``[{kind, body, seen}]``.
    Older ones are removed. Never raises."""
    try:
        client = _locks._client()
        if client is None:
            return []
        key = KEY_PREFIX + str(participant_uid)
        rows, old = [], []
        for field, raw in (client.hgetall(key) or {}).items():
            try:
                row = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            except ValueError:
                old.append(field)
                continue
            if _now() - float(row.get("seen", 0.0)) > KEEP_SECONDS:
                old.append(field)
            else:
                rows.append(row)
        if old:
            client.hdel(key, *old)
        return sorted(rows, key=lambda r: (-float(r["seen"]), r["kind"], json.dumps(r["body"],
                                                                                    sort_keys=True)))
    except Exception:                                          # noqa: BLE001 -- best effort
        return []


def participants():
    """Every participant with remembered requests. Never raises."""
    try:
        client = _locks._client()
        if client is None:
            return []
        out = []
        for k in client.scan_iter(match=KEY_PREFIX + "*"):
            k = k.decode() if isinstance(k, bytes) else str(k)
            out.append(k[len(KEY_PREFIX):])
        return out
    except Exception:                                          # noqa: BLE001 -- best effort
        return []
