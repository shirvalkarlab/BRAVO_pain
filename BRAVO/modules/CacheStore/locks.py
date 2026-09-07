"""A short-lived build lock in Redis, so four workers do not start the same 37-second build at once.

WHAT IT PROTECTS. Nothing else stops every gunicorn worker that misses the shared tile file from
building the same participant's tiles at the same moment. The store's atomic write means the file
ends up correct whichever finishes last, but the machine does four builds' work for one file and
the page waits on the slowest.

THREE HARD REQUIREMENTS, EACH TESTED. The lock EXPIRES on its own (`ttl_s`), so a worker that dies
mid-build cannot wedge the participant. A waiter that runs out of patience (`wait_s`) FALLS BACK
TO BUILDING rather than failing the page. Redis being unreachable, or the client library absent,
DEGRADES TO TODAY'S BEHAVIOUR: build, with no error.

Redis 5 here, so every client is constructed with protocol version 2 (`CLAUDE.md` section 3).
"""
import contextlib
import logging
import os
import threading
import time
import uuid

_log = logging.getLogger(__name__)

ENABLED = True
#: Tests hand in a callable returning a client with `set(name, value, nx=, ex=)`, `get`, `eval`.
CLIENT_FACTORY = None
EVENTS = {"builder": 0, "served": 0, "fallback_timeout": 0, "fallback_no_redis": 0,
          "fallback_disabled": 0}
_EVENTS_LOCK = threading.Lock()

_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


def _bump(name):
    with _EVENTS_LOCK:
        EVENTS[name] = EVENTS.get(name, 0) + 1


def _client():
    if CLIENT_FACTORY is not None:
        return CLIENT_FACTORY()
    host = os.environ.get("REDIS_HOST")
    if not host:
        return None
    try:
        import redis
    except ImportError:
        return None
    return redis.Redis(host=host, port=int(os.environ.get("REDIS_PORT", "6379")), protocol=2,
                       socket_connect_timeout=0.5, socket_timeout=1.0)


class Outcome(object):
    """What happened at the lock: `role` is "builder", "served" or "fallback"; `reason` says why."""

    __slots__ = ("role", "reason", "waited_s")

    def __init__(self, role, reason="", waited_s=0.0):
        self.role, self.reason, self.waited_s = role, reason, float(waited_s)

    def __repr__(self):
        return "Outcome(%s, %r, %.2fs)" % (self.role, self.reason, self.waited_s)


@contextlib.contextmanager
def build_lock(name, *, ttl_s=180.0, wait_s=120.0, poll_s=0.5, ready=None):
    """Hold the lock named `name` while building, or wait for whoever holds it.

    Yields an `Outcome`. "builder": this caller holds the lock and should build; it is released on
    exit. "served": `ready()` returned true while waiting, so the product now exists and the caller
    should read it instead of building. "fallback": build anyway, because the lock is disabled,
    Redis is unreachable, or `wait_s` passed without the product appearing.
    """
    if not ENABLED:
        _bump("fallback_disabled")
        yield Outcome("fallback", "lock disabled")
        return
    token = uuid.uuid4().hex
    try:
        client = _client()
        if client is None:
            raise RuntimeError("no Redis host configured")
        acquired = bool(client.set(name, token, nx=True, ex=int(max(1, round(ttl_s)))))
    except Exception as exc:                                    # noqa: BLE001
        _bump("fallback_no_redis")
        _log.info("CacheStore lock %s: Redis unavailable (%r); building without a lock", name, exc)
        yield Outcome("fallback", "redis unavailable: %r" % (exc,))
        return
    if acquired:
        _bump("builder")
        try:
            yield Outcome("builder", "lock acquired")
        finally:
            try:
                client.eval(_RELEASE, 1, name, token)
            except Exception as exc:                            # noqa: BLE001
                _log.info("CacheStore lock %s: release failed (%r); it expires on its own", name, exc)
        return
    # Someone else is building. Wait for the product, or for the lock to free up, or give up.
    t0 = time.monotonic()
    while True:
        waited = time.monotonic() - t0
        try:
            if ready is not None and ready():
                _bump("served")
                yield Outcome("served", "built by another worker", waited)
                return
            if client.set(name, token, nx=True, ex=int(max(1, round(ttl_s)))):
                _bump("builder")
                try:
                    yield Outcome("builder", "lock acquired after waiting", waited)
                finally:
                    try:
                        client.eval(_RELEASE, 1, name, token)
                    except Exception:                           # noqa: BLE001
                        pass
                return
        except Exception as exc:                                # noqa: BLE001
            _bump("fallback_no_redis")
            yield Outcome("fallback", "redis failed while waiting: %r" % (exc,), waited)
            return
        if waited >= wait_s:
            _bump("fallback_timeout")
            _log.warning("CacheStore lock %s: waited %.0f s for another worker's build; building "
                         "anyway", name, waited)
            yield Outcome("fallback", "waited %.0f s" % waited, waited)
            return
        time.sleep(poll_s)


def stats():
    with _EVENTS_LOCK:
        return dict(EVENTS)
