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
