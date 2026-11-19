"""Shared set-up for the store's tests (2026-10-05: the same sandbox had been written out in four
files). Not a test file: `run_tests.py` and pytest collect only `test_*.py`, and no name here
starts with `test_`, because the container runner calls every callable `test_*` a module holds,
imported ones included.

The BRAVO root is on the path already: `conftest.py` puts it there under pytest, and the container
runner starts from it."""
import hashlib
import os
import shutil
import tempfile

from modules.CacheStore import store as st

UID = "2e3c75c00d7f4f37b53a048d195f11da"


class Sandbox:
    """Point the store at a fresh directory and turn the ledger off for the duration; yields the
    directory.

    The ledger is off because these tests must run with no database at all; `test_ledger.py`
    covers it separately against SQLite in memory.
    """

    def __enter__(self):
        from modules.CacheStore import ledger
        self._dir = tempfile.mkdtemp(prefix="bravo_store_test_")
        self._prev_dir, self._prev_ledger = st.DIR_OVERRIDE, ledger.ENABLED
        st.DIR_OVERRIDE, ledger.ENABLED = self._dir, False
        st.clear()
        return self._dir

    def __exit__(self, *exc):
        from modules.CacheStore import ledger
        st.DIR_OVERRIDE, ledger.ENABLED = self._prev_dir, self._prev_ledger
        shutil.rmtree(self._dir, ignore_errors=True)
        return False


def tree(root):
    """Every file under the root with its size and content hash, for byte-identity checks."""
    out = {}
    for dirpath, _dirs, names in os.walk(root):
        for n in sorted(names):
            p = os.path.join(dirpath, n)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = (os.path.getsize(p),
                                                 hashlib.sha256(fh.read()).hexdigest())
    return out


def refused(fn, *args, **kwargs):
    """The SelfDerivedProduct the call raised, or None when it returned."""
    from modules.CacheStore import provenance as prov
    try:
        fn(*args, **kwargs)
    except prov.SelfDerivedProduct as exc:
        return exc
    return None
