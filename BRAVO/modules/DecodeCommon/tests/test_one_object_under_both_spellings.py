"""Every analysis package is ONE module object under both import spellings (review C4, decision 143).

The container imports `modules.X`, the host suite `X`; with both roots on the path a process used to
hold two copies of every submodule -- two 245 MB tile memos per worker, two copies of every
module-level switch, and a monkeypatch that landed on the copy the code under test was not using.
This test puts both roots on the path, imports a lazily loaded submodule of each package under both
spellings, and requires the SAME object. A package-level alias alone fails it (measured 2026-09-12:
`types` came back as two objects); the meta-path finder in `DecodeCommon.import_alias` passes it.
"""
import importlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULES = os.path.abspath(os.path.join(_HERE, "..", ".."))
_BRAVO = os.path.abspath(os.path.join(_MODULES, ".."))
for _root in (_MODULES, _BRAVO):
    if _root not in sys.path:
        sys.path.insert(0, _root)

CASES = [
    ("ClosedLoopDeployment", "types"),
    ("ClosedLoopDeployment", "constraints"),
    ("Biomarkers", "routines.sweep_settings"),
    ("StimOptimizer", "routines.percept_adaptive"),
    ("DecodeCommon", "import_alias"),
]


def test_each_package_submodule_is_one_object_under_both_spellings():
    for pkg, sub in CASES:
        a = importlib.import_module(f"{pkg}.{sub}")
        b = importlib.import_module(f"modules.{pkg}.{sub}")
        assert a is b, f"{pkg}.{sub}: two module objects ({a.__name__!r} and {b.__name__!r})"


def test_a_module_level_switch_is_one_switch():
    a = importlib.import_module("StimOptimizer.routines.plots")
    b = importlib.import_module("modules.StimOptimizer.routines.plots")
    before = a.USE_STREAM_LIMIT_ANCHORS
    try:
        a.USE_STREAM_LIMIT_ANCHORS = not before
        assert b.USE_STREAM_LIMIT_ANCHORS is (not before)
    finally:
        a.USE_STREAM_LIMIT_ANCHORS = before


def test_the_package_itself_is_one_object():
    for pkg, _ in CASES:
        assert importlib.import_module(pkg) is importlib.import_module("modules." + pkg), pkg
