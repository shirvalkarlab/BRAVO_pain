"""The build lock's three hard requirements, on a stand-in for Redis. No pytest, so the container
runs this file too."""
import threading
import time

from modules.CacheStore import locks


class _FakeRedis(object):
    """Just enough of Redis: SET NX EX, GET, and the compare-and-delete script."""

    def __init__(self, store=None, fail=False):
        self.store = {} if store is None else store
        self.fail = fail
        self.lock = threading.Lock()

    def set(self, name, value, nx=False, ex=None):
        if self.fail:
            raise ConnectionError("redis down")
        with self.lock:
            if nx and name in self.store:
                return False
            self.store[name] = value
            return True

    def get(self, name):
        return self.store.get(name)

    def eval(self, script, n, name, token):
        with self.lock:
            if self.store.get(name) == token:
                del self.store[name]
                return 1
            return 0


def _with(fake):
    prev = locks.CLIENT_FACTORY
    locks.CLIENT_FACTORY = lambda: fake
    return prev


def test_the_first_caller_builds_and_releases_only_its_own_token():
    fake = _FakeRedis(); prev = _with(fake)
    try:
        with locks.build_lock("k", ttl_s=5) as o:
            assert o.role == "builder" and "k" in fake.store
            fake.store["k"] = "someone-else"          # the lock expired and another worker took it
        assert fake.store["k"] == "someone-else", "release must not delete another worker's lock"
        with locks.build_lock("k2", ttl_s=5) as o:
            assert o.role == "builder"
        assert "k2" not in fake.store
    finally:
        locks.CLIENT_FACTORY = prev


def test_a_waiter_is_served_when_the_product_appears():
    fake = _FakeRedis({"k": "other"}); prev = _with(fake)
    flag = {"ready": False}
    def later():
        time.sleep(0.15); flag["ready"] = True
    threading.Thread(target=later).start()
    try:
        with locks.build_lock("k", ttl_s=5, wait_s=5, poll_s=0.02, ready=lambda: flag["ready"]) as o:
            assert o.role == "served" and o.waited_s >= 0.1
    finally:
        locks.CLIENT_FACTORY = prev


def test_a_waiter_that_runs_out_of_patience_builds_rather_than_failing():
    fake = _FakeRedis({"k": "other"}); prev = _with(fake)
    try:
        with locks.build_lock("k", ttl_s=5, wait_s=0.1, poll_s=0.02, ready=lambda: False) as o:
            assert o.role == "fallback" and "waited" in o.reason
    finally:
        locks.CLIENT_FACTORY = prev


def test_a_waiter_takes_the_lock_when_the_holder_releases_it():
    fake = _FakeRedis({"k": "other"}); prev = _with(fake)
    def release():
        time.sleep(0.1); fake.store.pop("k", None)
    threading.Thread(target=release).start()
    try:
        with locks.build_lock("k", ttl_s=5, wait_s=5, poll_s=0.02, ready=lambda: False) as o:
            assert o.role == "builder" and "after waiting" in o.reason
    finally:
        locks.CLIENT_FACTORY = prev


def test_redis_unreachable_degrades_to_building_with_no_error():
    prev = _with(_FakeRedis(fail=True))
    try:
        with locks.build_lock("k", ttl_s=5) as o:
            assert o.role == "fallback" and "unavailable" in o.reason
    finally:
        locks.CLIENT_FACTORY = prev
    prev = locks.CLIENT_FACTORY; locks.CLIENT_FACTORY = lambda: None
    try:
        with locks.build_lock("k", ttl_s=5) as o:
            assert o.role == "fallback"
    finally:
        locks.CLIENT_FACTORY = prev


def test_the_lock_can_be_switched_off():
    prev_e = locks.ENABLED; locks.ENABLED = False
    try:
        with locks.build_lock("k") as o:
            assert o.role == "fallback" and "disabled" in o.reason
    finally:
        locks.ENABLED = prev_e


def test_eight_concurrent_callers_produce_exactly_one_builder():
    fake = _FakeRedis(); prev = _with(fake)
    built = []; roles = []; ready = {"v": False}
    def worker():
        with locks.build_lock("k", ttl_s=5, wait_s=5, poll_s=0.01, ready=lambda: ready["v"]) as o:
            roles.append(o.role)
            if o.role == "builder":
                time.sleep(0.1); built.append(1); ready["v"] = True
    try:
        ts = [threading.Thread(target=worker) for _ in range(8)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert sum(built) == 1, roles
        assert roles.count("builder") == 1 and roles.count("served") == 7, roles
    finally:
        locks.CLIENT_FACTORY = prev
