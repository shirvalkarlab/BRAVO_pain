"""Put BRAVO/modules on sys.path so `ClosedLoopDeployment` imports the same way it does in-container.

Mirrors ``StimOptimizer/tests/conftest.py`` deliberately. This module imports device constants from
``StimOptimizer.routines.percept_adaptive`` rather than retyping them, so both packages have to be
importable by their top-level names for the tests to exercise the same import path the application
uses.
"""
import sys
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))


import shutil as _shutil
import tempfile as _tempfile

import pytest as _pytest


@_pytest.fixture
def grid_sandbox():
    """The store, the Closed-Loop adapter's own store directory and the ledger pointed at a fresh
    temporary directory for one test, for the files that import the HOST spellings
    (`CacheStore.store`, `ClosedLoopDeployment.adapter`): the `modules.`-prefixed spellings are other
    module objects and are not redirected. Cleared before and after while the override still points
    at the sandbox (decision 129). Written 2026-10-05 from three identical copies, in
    test_grid_matches_biomarkers_settings.py, test_grid_rule_in_force.py and
    test_track_d_grid_stability_translation.py."""
    from CacheStore import ledger, store as st
    from ClosedLoopDeployment import adapter
    d = _tempfile.mkdtemp(prefix="bravo_cld_grid_")
    prev = st.DIR_OVERRIDE, adapter._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED
    st.DIR_OVERRIDE, adapter._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED = d, d, False
    st.clear()
    try:
        yield d
    finally:
        st.clear()                       # while the override still points at the sandbox
        st.DIR_OVERRIDE, adapter._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED = prev
        _shutil.rmtree(d, ignore_errors=True)
