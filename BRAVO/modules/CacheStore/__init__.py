"""The one cache store, and the provenance chain that keeps the modules from confirming themselves.

`store`      — read and write cached products; one implementation for all three modules.
`provenance` — the chain carried by every written-back product, and the refusal that uses it.
`ledger`     — the append-only record in the database of what wrote each product and from what.
`locks`      — the short-lived Redis build lock, so four workers do not build one product at once.
"""
import sys as _sys

from . import ledger, locks, provenance, store     # noqa: F401  (re-exported for callers)

__all__ = ["store", "provenance", "ledger", "locks"]

# ONE MODULE OBJECT UNDER BOTH SPELLINGS. The container imports this package as
# `modules.CacheStore` and the host test suite as `CacheStore`; once both roots are on the path in
# one process (the store's own tests put the BRAVO root there), the two spellings would load two
# copies with two `ENABLED` flags, two counters and two locks — the one-store rule broken by an
# import path. Registering this package and its three modules under the other name too makes a
# later import of either spelling hand back the same objects. Found by a test that switched the
# store off under one spelling while the adapter under review held the other.
_OTHER = "CacheStore" if __name__ == "modules.CacheStore" else "modules.CacheStore"
for _name, _mod in (("", _sys.modules[__name__]), (".store", store),
                    (".provenance", provenance), (".ledger", ledger), (".locks", locks)):
    _sys.modules.setdefault(_OTHER + _name, _mod)
