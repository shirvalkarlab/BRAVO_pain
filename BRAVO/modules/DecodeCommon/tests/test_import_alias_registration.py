"""Cold import registration, isolated from clinical modules and services."""
import importlib
import importlib.util
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from DecodeCommon import import_alias as aliases


@pytest.fixture
def package(tmp_path, monkeypatch):
    import modules
    name = "_SyntheticAliasRegression"
    directory = tmp_path / "modules" / name
    directory.mkdir(parents=True)
    monkeypatch.syspath_prepend(str(tmp_path / "modules"))
    monkeypatch.setattr(modules, "__path__", [str(tmp_path / "modules"), *modules.__path__])
    monkeypatch.setitem(sys.modules, "_alias_test_helper", aliases)
    (directory / "__init__.py").write_text(
        "from _alias_test_helper import alias_both_spellings\n"
        "alias_both_spellings(__name__)\n"
    )
    (directory / "child.py").write_text("VALUE = object()\n")
    yield name, directory
    names = (name, "modules." + name)
    sys.meta_path[:] = [finder for finder in sys.meta_path
                       if getattr(finder, "bravo_alias", None) not in names]
    for key in list(sys.modules):
        if any(key == prefix or key.startswith(prefix + ".") for prefix in names):
            del sys.modules[key]


@pytest.mark.parametrize("prefixed", [False, True])
def test_opposite_and_repeated_registration_keep_one_canonical_module(package, prefixed):
    name, _ = package
    first, second = ("modules." + name, name) if prefixed else (name, "modules." + name)
    canonical = importlib.import_module(first)
    # Both __init__ spellings can run during a concurrent cold import.
    for spelling in (second, first, second):
        aliases.alias_both_spellings(spelling)
    finders = [f for f in sys.meta_path if getattr(f, "bravo_alias", None) in (first, second)]
    assert len(finders) == 1
    assert finders[0].canonical == first
    assert importlib.import_module(second) is canonical
    child = importlib.import_module(second + ".child")
    assert importlib.import_module(first + ".child") is child
    assert child.__name__ == first + ".child"
    assert finders[0].find_spec("unrelated.module") is None
    assert finders[0].find_spec(second + ".child") is None


def test_simultaneous_cold_package_initializers_do_not_install_reverse_finders(package, monkeypatch):
    name, directory = package
    barrier = threading.Barrier(2)
    monkeypatch.setattr(aliases, "test_barrier", barrier, raising=False)
    (directory / "__init__.py").write_text(
        "from _alias_test_helper import alias_both_spellings, test_barrier\n"
        "test_barrier.wait(timeout=5)\n"
        "alias_both_spellings(__name__)\n"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(importlib.import_module, spelling)
                   for spelling in (name, "modules." + name)]
        first, second = [future.result(timeout=10) for future in futures]
    assert first is second
    assert len([f for f in sys.meta_path
                if getattr(f, "bravo_alias", None) in (name, "modules." + name)]) == 1
    assert importlib.import_module(name + ".child") is importlib.import_module("modules." + name + ".child")


def test_helper_copies_share_registration_lock():
    spec = importlib.util.spec_from_file_location("_alias_helper_copy", aliases.__file__)
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)
    assert copy._REGISTRATION_LOCK is aliases._REGISTRATION_LOCK
