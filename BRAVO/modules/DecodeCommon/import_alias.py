"""One module object under both import spellings of an analysis package.

The container puts /usr/src/BRAVO on the path, so a package under modules/ is imported there as
`modules.X`; the host test suite runs from BRAVO/modules, so the same package is `X`. Once both
roots are on the path in one process -- which is the case in every gunicorn worker, because
`settings.py` appends modules/ to sys.path while the views import `modules.X` -- the two
spellings load two copies of every submodule: two sets of in-process memos (the 245.90 MB tile
entry twice per worker), two copies of every module-level switch, and a test's monkeypatch that
lands on the copy the code under test is not using (decision 125 met that).

`CacheStore` and `DecodeCommon` solved this for themselves by listing their few submodules and
registering each under the other name at import. That does not scale to a package whose
submodules are imported lazily by callers, and registering the PACKAGE alone is not enough:
`import X.sub` finds `X` in sys.modules and then loads `X.sub` afresh through the package's
__path__ (measured 2026-09-12: a package-only alias still gave two `types` objects). So this
finder sits on sys.meta_path and answers every import under the OTHER spelling by importing the
canonical spelling and handing back that same object. importlib registers it under the alias
name too; the module keeps its own __name__ and __spec__ because `module_from_spec` never
overwrites attributes a module already has.

Whichever spelling imports the package first is its canonical one; the other becomes the alias.
"""
import importlib
import importlib.abc
import importlib.machinery
import sys

_PREFIX = "modules."


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, module):
        self._module = module

    def create_module(self, spec):
        return self._module            # the canonical object; importlib registers it under the alias

    def exec_module(self, module):
        return None                    # already executed under its canonical name


class _AliasFinder(importlib.abc.MetaPathFinder):
    """Imports of `<alias>` or `<alias>.<sub>` return the module `<canonical>[.<sub>]`."""

    bravo_alias = None                 # the attribute the dedupe check reads, class-identity-free

    def __init__(self, alias, canonical):
        self.bravo_alias, self.canonical = alias, canonical

    def find_spec(self, fullname, path=None, target=None):
        alias = self.bravo_alias
        if fullname != alias and not fullname.startswith(alias + "."):
            return None
        canonical_name = self.canonical + fullname[len(alias):]
        if canonical_name in sys.modules and fullname in sys.modules:
            return None
        module = importlib.import_module(canonical_name)
        return importlib.machinery.ModuleSpec(fullname, _AliasLoader(module),
                                              is_package=hasattr(module, "__path__"))


def alias_both_spellings(package_name):
    """Call from a package's `__init__` with its own `__name__`, after the package is importable."""
    if package_name.startswith(_PREFIX):
        canonical, alias = package_name, package_name[len(_PREFIX):]
    else:
        canonical, alias = package_name, _PREFIX + package_name
    if any(getattr(f, "bravo_alias", None) == alias for f in sys.meta_path):
        return
    sys.modules.setdefault(alias, sys.modules[canonical])
    sys.meta_path.insert(0, _AliasFinder(alias, canonical))
