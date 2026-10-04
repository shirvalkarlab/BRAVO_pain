"""pytest set-up for every module's tests: tests never add requests to the live server's list of
requests to replay (`CacheStore.request_memory`, decision 435); a test that checks remembering turns
it on itself, with a stand-in Redis."""
import os

os.environ.setdefault("BRAVO_REMEMBER_REQUESTS", "0")
