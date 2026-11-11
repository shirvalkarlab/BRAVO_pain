"""pytest set-up for every module's tests: tests never add requests to the live server's list of
requests to replay (`CacheStore.request_memory`, decision 435); a test that checks remembering turns
it on itself, with a stand-in Redis."""
import os

os.environ.setdefault("BRAVO_REMEMBER_REQUESTS", "0")


def pytest_collection_modifyitems(config, items):
    """Mark the tests `slow_tests.py` lists `slow`, so `-m "not slow"` gives the fast run (decision 451)."""
    import pytest
    try:
        from slow_tests import is_slow
    except ImportError:                      # run from another folder
        from modules.slow_tests import is_slow
    for item in items:
        if is_slow(item.fspath, getattr(item, "originalname", item.name)):
            item.add_marker(pytest.mark.slow)
