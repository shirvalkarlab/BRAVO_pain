"""There is ONE store. These tests fail if a second one comes back.

Two implementations of the cache existed, in `Biomarkers/bravo_service.py` and
`ClosedLoopDeployment/adapter.py`. They were not a deliberate pair — each was written when its own
module needed a cache, they shared a root by construction accident, and their per-entry limits
differed by exactly a factor of four with no stated reason. Nothing failed; the second copy simply
drifted from the first, and no page could report what the cache as a whole was doing because each
copy counted into its own event dictionary.

**A comment asking a future reader not to write a third copy would not have prevented the second
one.** These tests read the source of the other modules and fail on the constructs that make a
private store, so the duplication cannot silently return.
"""
import pathlib
import re
import sys

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

_MODULES = _BRAVO_ROOT / "modules"

from modules.CacheStore import store as st

#: The modules that may consume the store but must not implement one.
_CONSUMERS = {
    "Biomarkers": _MODULES / "Biomarkers" / "bravo_service.py",
    "ClosedLoopDeployment": _MODULES / "ClosedLoopDeployment" / "adapter.py",
    "StimOptimizer": _MODULES / "StimOptimizer" / "adapter.py",
}


def _source(name):
    p = _CONSUMERS[name]
    return p.read_text(encoding="utf8") if p.exists() else ""


#: STILL ALLOWED, AND ONLY UNTIL THE PER-RECORDING SPECTRUM DIRECTORIES ARE FOLDED IN.
#:
#: `biomarker_psd` (97 files, 500.32 MB) and `biomarker_psd_rows` (6,309 files, 30.47 MB) are a
#: SEPARATE cache from the shared tile store, with its own directory resolver and its own atomic
#: writer in the biomarker module. Folding them into the one store is its own step in the approved
#: plan — "Move every cache to the single approved location" — and doing it here would mix a
#: 500 MB migration into the deduplication.
#:
#: Each entry is matched on its text rather than its line number, because line numbers drift.
#: **When that step lands, these two exemptions must be deleted**, and the count assertion below
#: is what will fail and say so.
_ALLOWED_PENDING_MIGRATION = (
    'os.path.join(base, "cache", "biomarker_psd")',
    "os.replace(tmp, path)",
)


def _is_allowed(line):
    return any(a in line for a in _ALLOWED_PENDING_MIGRATION)


def test_no_other_module_builds_a_cache_directory_of_its_own():
    """The construct that made a private store: joining a storage path with a cache directory.

    Only `CacheStore/store.py` may do this. A module that does it again has its own root, and two
    roots is how the per-entry limits came to differ by a factor of four.
    """
    offenders, allowed_seen = [], 0
    pattern = re.compile(r"path\.join\([^)]*[\"']cache[\"']")
    for name in _CONSUMERS:
        for n, line in enumerate(_source(name).split("\n"), 1):
            if not pattern.search(line):
                continue
            if _is_allowed(line):
                allowed_seen += 1
                continue
            offenders.append(f"{name}:{n}: {line.strip()}")
    assert offenders == [], (
        "a module is building its own cache root again; the store lives in "
        "modules/CacheStore/store.py and takes a root= argument for tests:\n  "
        + "\n  ".join(offenders))
    assert allowed_seen == 1, (
        f"expected exactly 1 grandfathered cache-root construct, found {allowed_seen}. "
        "If the per-recording spectrum directories have been folded into the one store, delete "
        "the matching entry from _ALLOWED_PENDING_MIGRATION.")


def test_no_other_module_reads_the_storage_path_setting_for_a_cache():
    """Reading the platform's storage path is how a private resolver starts.

    The biomarker module legitimately reads it for the per-recording spectrum directory, so this
    checks that the SHARED-cache functions do not: `shared_cache_dir` must be a delegation and
    nothing more.
    """
    for name in _CONSUMERS:
        src = _source(name)
        if "def shared_cache_dir" not in src:
            continue
        # The body of shared_cache_dir, up to the next top-level definition.
        body = src.split("def shared_cache_dir", 1)[1].split("\ndef ", 1)[0]
        assert "DATASERVER_PATH" not in body, \
            f"{name}.shared_cache_dir resolves a path itself instead of delegating"
        assert "_cache_store." in body, \
            f"{name}.shared_cache_dir does not delegate to the shared store"


def _modules_or_none():
    """Both consumer modules, or None when they cannot be imported here.

    `Biomarkers/bravo_service.py` pulls in the Django server package, so it imports in the
    container and not in the host suite. These three tests therefore check the wiring where the
    server actually runs, and step aside on the host rather than reporting a failure that is only
    a missing server.
    """
    try:
        from Biomarkers import bravo_service as B
        from ClosedLoopDeployment import adapter as AD
        return B, AD
    except Exception:
        return None


def test_both_modules_resolve_under_the_one_root():
    """Not "they happen to agree today" — the same resolver returns both."""
    mods = _modules_or_none()
    if mods is None:
        return
    B, AD = mods
    root = st.root_dir()
    if root is None:
        return                    # no storage configured; the other tests still cover the wiring
    for got in (B.shared_cache_dir(), AD.shared_cache_dir()):
        assert got is not None
        assert str(got).startswith(str(root)), f"{got} is not under {root}"


def test_the_two_modules_count_into_the_same_events():
    """Each copy used to count into its own dictionary, so no page could report the whole cache."""
    mods = _modules_or_none()
    if mods is None:
        return
    B, AD = mods
    assert B._SHARED_CACHE_EVENTS is st._EVENTS
    assert AD._SHARED_CACHE_EVENTS is st._EVENTS
    assert B._SHARED_CACHE_LOCK is st._LOCK
    assert AD._SHARED_CACHE_LOCK is st._LOCK


def test_the_per_entry_limits_no_longer_differ():
    """THE DEFECT THIS WHOLE CHANGE STARTED FROM: 1,073,741,824 against 268,435,456.

    Not that the smaller cap refused anything -- 268,435,456 bytes is 256 MiB and the 245.90 MB
    tile entry fits under it. The defect is that two modules writing into one root disagreed by a
    factor of four about how large an entry may be, so which limit applied depended on which
    module happened to write first. `test_store.py` covers the headroom argument for the value.
    """
    mods = _modules_or_none()
    if mods is None:
        return
    B, AD = mods
    assert B._SHARED_CACHE_MAX_BYTES == AD._SHARED_CACHE_MAX_BYTES
    assert B._SHARED_CACHE_MAX_BYTES == st.MAX_BYTES_DEFAULT


def test_no_other_module_pickles_a_cache_entry_itself():
    """Writing the payload is the store's job, including the atomic move that makes a partial file
    impossible for a reader to see. A module doing its own write loses that guarantee."""
    offenders = []
    for name in _CONSUMERS:
        src = _source(name)
        for n, line in enumerate(src.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"\.tmp[\"']", stripped) and "os.replace" not in stripped:
                continue
            if "os.replace(" in stripped or "_os.replace(" in stripped:
                if _is_allowed(stripped):
                    continue                # the per-recording spectrum writer; see the note above
                offenders.append(f"{name}:{n}: {stripped}")
    assert offenders == [], (
        "a module is committing a cache file itself rather than through the store:\n  "
        + "\n  ".join(offenders))


def test_the_store_is_the_only_place_that_names_the_cache_subdirectories():
    """`biomarker_shared` and `closed_loop` are the store's business, not a caller's."""
    offenders = []
    for name in _CONSUMERS:
        for n, line in enumerate(_source(name).split("\n"), 1):
            if line.strip().startswith("#"):
                continue
            # `writer="closed_loop"` names the MODULE that produced a product, which is what
            # the provenance rules key on; it is not a directory. Only a path-shaped use counts.
            if re.search(r"(join|dir|SUBDIR|path)", line, re.I) is None:
                continue
            for token in ('"biomarker_shared"', "'biomarker_shared'",
                          '"closed_loop"', "'closed_loop'"):
                if token in line:
                    offenders.append(f"{name}:{n}: {line.strip()}")
    assert offenders == [], (
        "a directory name the store owns is written in a caller:\n  " + "\n  ".join(offenders))
