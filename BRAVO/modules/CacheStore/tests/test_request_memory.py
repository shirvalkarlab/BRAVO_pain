"""The band requests the pages send are remembered per participant, so the server can work their
answers out again when the data change (the PI, 2026-10-04: "yes do 3b", decision 435).

Values: one request asked twice is one entry with the newer time; two different requests are two;
an entry older than the keep period is dropped; with Redis unreachable nothing raises and nothing
is remembered."""
from modules.CacheStore import locks, request_memory as rm


class FakeRedis:
    def __init__(self):
        self.h = {}

    def hset(self, key, field, value):
        self.h.setdefault(key, {})[field] = value if isinstance(value, bytes) else str(value).encode()

    def hgetall(self, key):
        return {k.encode() if isinstance(k, str) else k: v for k, v in self.h.get(key, {}).items()}

    def hdel(self, key, *fields):
        for f in fields:
            self.h.get(key, {}).pop(f if isinstance(f, str) else f.decode(), None)

    def expire(self, key, seconds):
        return True

    def scan_iter(self, match):
        pre = match.rstrip("*")
        return [k.encode() for k in self.h if k.startswith(pre)]

    def get(self, key):
        v = self.h.get("__kv__", {}).get(key)
        return v

    def set(self, key, value):
        self.h.setdefault("__kv__", {})[key] = value if isinstance(value, bytes) else str(value).encode()


def _with(fake, fn):
    import os
    saved, saved_env = locks.CLIENT_FACTORY, os.environ.get(rm.OFF_ENV)
    locks.CLIENT_FACTORY = (lambda: fake)
    os.environ[rm.OFF_ENV] = "1"                    # the test runners turn remembering off
    try:
        return fn()
    finally:
        locks.CLIENT_FACTORY = saved
        if saved_env is None:
            os.environ.pop(rm.OFF_ENV, None)
        else:
            os.environ[rm.OFF_ENV] = saved_env


def test_one_request_twice_is_one_entry_two_requests_two():
    fake = FakeRedis()
    clock = [1000.0]

    def run():
        real = rm._now
        rm._now = lambda: clock[0]
        try:
            rm.remember("deployment_summary", "u1", {"ParticipantId": "u1", "CenterHz": 23.5})
            clock[0] = 2000.0
            rm.remember("deployment_summary", "u1", {"CenterHz": 23.5, "ParticipantId": "u1"})
            rm.remember("deployment_roc", "u1", {"ParticipantId": "u1", "CenterHz": 24.5})
            return rm.recent("u1")
        finally:
            rm._now = real
    got = _with(fake, run)
    # newest first; seen at the same time, by kind
    assert [(g["kind"], g["body"]["CenterHz"], g["seen"]) for g in got] == [
        ("deployment_roc", 24.5, 2000.0), ("deployment_summary", 23.5, 2000.0)]


def test_old_entries_are_dropped():
    fake = FakeRedis()

    def run():
        real = rm._now
        try:
            rm._now = lambda: 0.0
            rm.remember("deployment_summary", "u1", {"ParticipantId": "u1", "CenterHz": 1.0})
            rm._now = lambda: rm.KEEP_SECONDS + 10.0
            rm.remember("deployment_summary", "u1", {"ParticipantId": "u1", "CenterHz": 2.0})
            return rm.recent("u1")
        finally:
            rm._now = real
    got = _with(fake, run)
    assert [g["body"]["CenterHz"] for g in got] == [2.0]


def test_redis_unreachable_raises_nothing():
    class Down:
        def __getattr__(self, name):
            def boom(*a, **k):
                raise ConnectionError("down")
            return boom

    def run():
        rm.remember("deployment_summary", "u1", {"ParticipantId": "u1"})
        return rm.recent("u1"), rm.participants()
    assert _with(Down(), run) == ([], [])


def test_participants_lists_who_has_remembered_requests():
    fake = FakeRedis()

    def run():
        rm.remember("deployment_summary", "u1", {"ParticipantId": "u1"})
        rm.remember("deployment_summary", "u2", {"ParticipantId": "u2"})
        return sorted(rm.participants())
    assert _with(fake, run) == ["u1", "u2"]
