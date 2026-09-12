"""Put the BRAVO root AND BRAVO/modules on sys.path, so both spellings of the store's package
import (`modules.CacheStore` in the container, `CacheStore` on the host) resolve in any test order.

Until 2026-09-12 each test file in this directory inserted the root itself, except `test_locks.py`,
which imported `modules.CacheStore.locks` and only worked because an earlier file in the same
process had already inserted the root. Under pytest-xdist, or run on its own, it failed at import.
The root is inserted here, once, before any test module in this directory is imported.
"""
import sys
from pathlib import Path

_BRAVO_ROOT = Path(__file__).resolve().parents[3]
_MODULES_DIR = Path(__file__).resolve().parents[2]
for _p in (_MODULES_DIR, _BRAVO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
