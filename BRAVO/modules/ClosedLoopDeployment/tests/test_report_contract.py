"""The Closed-Loop report's own response contract: what every return path must carry, and the rule
that a failure is reported under the key that failed.

WHY THIS FILE EXISTS. Two defects found on 2026-09-10 by auditing this module against the other
two, both of which are invisible on a page and invisible to a green suite:

  1. `report_for_participant` attached `cache_status` on its LAST return only. Its two early
     returns -- the empty states, which is what a reader sees before choosing a candidate, so most
     of the time -- came back without it, and the shared "last built" line decision 48 put on all
     three module pages had nothing to show. Measured live on RCS08 before the fix: the endpoint
     returned exactly three keys, `available`, `band_sweep_grid`, `reason`.

  2. The handler around the ground-truth write reported its failure as an AMPLITUDE-EFFECT failure.
     That lost the real reason (an absent key reads on the page as "does not apply", which the
     three-source block a few lines above explicitly says not to do) AND overwrote an
     amplitude-effect result that had just succeeded, with a report of a failure that never
     happened.

Both are checked by reading the module's own source rather than by running the report, so these
tests need no database, no participant and no store.
"""
import ast
import inspect
import pathlib

import pytest

try:
    from modules.ClosedLoopDeployment import adapter
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import adapter


_ADAPTER_SRC = pathlib.Path(inspect.getsourcefile(adapter)).read_text()
_TREE = ast.parse(_ADAPTER_SRC)


def _function(name):
    for node in ast.walk(_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone from adapter.py")


def _returns_in(fn):
    """Every `return` in this function, excluding any nested function's own returns."""
    nested = {n for f in ast.walk(fn)
              if isinstance(f, ast.FunctionDef) and f is not fn
              for n in ast.walk(f)}
    return [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n not in nested]


# --------------------------------------------------------------------------------------------
# 1. every return path carries the freshness line
# --------------------------------------------------------------------------------------------

def test_every_return_path_of_the_report_carries_cache_status():
    """Decision 48: every module response carries `cache_status`, INCLUDING the case where nothing
    is stored yet. The empty states are not exempt -- they are the case it was written for."""
    fn = _function("report_for_participant")
    assigned_to_out = {
        t.slice.value
        for n in ast.walk(fn) if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
        and t.value.id == "out" and isinstance(t.slice, ast.Constant)
    }

    missing = []
    for ret in _returns_in(fn):
        val = ret.value
        if isinstance(val, ast.Dict):
            keys = {k.value for k in val.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "cache_status" not in keys:
                missing.append((ret.lineno, sorted(keys)))
        elif isinstance(val, ast.Name) and val.id == "out":
            if "cache_status" not in assigned_to_out:
                missing.append((ret.lineno, "returns `out`, which is never given a cache_status"))
        else:
            missing.append((ret.lineno, f"unrecognised return shape {type(val).__name__}"))

    assert not missing, (
        f"return path(s) in report_for_participant carry no cache_status: {missing}. "
        f"Decision 48 covers the empty states too -- that is the 'no stored results yet' case it "
        f"names, and it is what a reader sees before a candidate has been chosen.")


def test_the_report_has_more_than_one_return_path_so_the_check_above_means_something():
    """Guards the guard: if report_for_participant were ever reduced to a single return, the test
    above would still pass while checking almost nothing."""
    assert len(_returns_in(_function("report_for_participant"))) >= 3


def test_a_cache_status_that_cannot_be_read_does_not_take_down_the_report(monkeypatch):
    """One sidecar read is cheap, but cheap is not the same as cannot-fail. An unreadable sidecar
    must degrade to a stated reason, not an exception on a page that otherwise had something."""
    def _boom(_participant):
        raise OSError("the store is pointed at a directory that is not there")

    monkeypatch.setattr(adapter, "cache_status_for_page", _boom)
    got = adapter._cache_status_or_reason(object())

    assert isinstance(got, dict)
    assert got["exists"] is False
    assert "could not be read" in got["reason"]
    assert "not there" in got["reason"], "the real cause was swallowed"


# --------------------------------------------------------------------------------------------
# 2. a failure is reported under the key that failed
# --------------------------------------------------------------------------------------------

def _handler_key_mismatches(fn):
    """Handlers that report a failure under a response key their own try-block never assigned.

    A sibling error key (`figures` -> `figures_error`) is the project's existing convention and is
    allowed. Reporting under a DIFFERENT feature's key is the defect: it loses the real failure and
    corrupts an unrelated result that may well have succeeded.
    """
    def keys(nodes, var):
        out = set()
        for n in nodes:
            for sub in ast.walk(n):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                                and t.value.id == var and isinstance(t.slice, ast.Constant)):
                            out.add(t.slice.value)
        return out

    bad = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        for var in ("out",):
            tk = keys(node.body, var)
            if not tk:
                continue
            for h in node.handlers:
                for hk in keys(h.body, var):
                    ok = hk in tk or any(hk in (f"{k}_error", f"{k}_reason") for k in tk)
                    if not ok:
                        bad.append((h.lineno, hk, sorted(tk)))
    return bad


def test_each_handler_reports_the_key_its_own_try_block_assigns():
    """THE SYSTEMIC GUARD, not just the one instance. Nothing checked this before, which is why a
    handler could report a ground-truth failure under the amplitude-effect key and stay that way
    through every review and every green suite -- the mislabelled key is only reachable when the
    write actually raises, and no test made it raise."""
    bad = _handler_key_mismatches(_function("report_for_participant"))
    assert not bad, (
        "handler(s) report a failure under a key their own try-block never assigned "
        f"(line, reported_key, keys_the_try_assigned): {bad}. This loses the real failure -- an "
        "absent key reads on the page as 'does not apply' -- and overwrites an unrelated result "
        "that may have succeeded.")


def _handler_messages_for(fn, key):
    """Every failure message a handler writes under `out[key]`, with the pieces of a split f-string
    joined back together.

    Read off the syntax tree rather than the raw source text on purpose: these messages are wrapped
    across lines, so `"a b c" in source` is false for a phrase that IS in the message. The first
    draft of this test made exactly that mistake and failed against correct code.
    """
    msgs = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        for h in node.handlers:
            for sub in ast.walk(h):
                if not isinstance(sub, ast.Assign):
                    continue
                for t in sub.targets:
                    if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                            and t.value.id == "out" and isinstance(t.slice, ast.Constant)
                            and t.slice.value == key):
                        text = "".join(
                            c.value for c in ast.walk(sub.value)
                            if isinstance(c, ast.Constant) and isinstance(c.value, str))
                        msgs.append(text)
    return msgs


def test_the_ground_truth_handler_names_the_ground_truth():
    """The specific instance, stated so a regression says which feature broke rather than only that
    some key mismatched."""
    fn = _function("report_for_participant")

    gt = " ".join(_handler_messages_for(fn, "ground_truth_verdict"))
    assert "ground-truth verdict could not be written" in gt, (
        f"the ground-truth write's failure is no longer reported under its own key with its own "
        f"message; found {gt!r}")

    amp = " ".join(_handler_messages_for(fn, "amplitude_effect_by_band"))
    assert "ground-truth" not in amp, (
        f"a ground-truth failure is being reported under the amplitude-effect key again; "
        f"found {amp!r}")
    assert "amplitude-effect table could not be written" not in amp, (
        "the amplitude-effect handler carries the ground-truth handler's old message, which is the "
        "exact copy-paste this test exists to catch")

# --------------------------------------------------------------------------------------------
# 3. a failure that reaches the payload also reaches the log
# --------------------------------------------------------------------------------------------

def test_every_failure_handler_in_the_report_also_logs():
    """MONITORING, which this module had none of. Counted 2026-09-10 across the three analysis
    modules: Biomarkers made 43 logger calls, CacheStore 17, StimOptimizer 13, and
    ClosedLoopDeployment **zero** -- it declared a logger at adapter.py:37 and never called it.

    So a failure inside the closed-loop report was visible only if the reader happened to open the
    one payload field carrying it, and the store-read failure was not visible at all: it set both
    stored entries to None and the page simply rebuilt them, looking entirely normal while redoing
    that work on every single request.

    The rule this pins: a handler in `report_for_participant` that tells the PAGE something went
    wrong must also tell the LOG. The page's reason is for whoever is looking at that participant;
    the log line is for whoever is asking why the server is slow, and they are rarely the same
    person at the same time.
    """
    fn = _function("report_for_participant")
    unlogged = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        for h in node.handlers:
            body = list(ast.walk(ast.Module(body=h.body, type_ignores=[])))
            # An ImportError fallback is the double-import pattern, not a failure. Skip it.
            names = {n.id for n in body if isinstance(n, ast.Name)}
            handled = getattr(h.type, "id", None) or getattr(getattr(h.type, "attr", None), "id", None)
            if handled == "ImportError":
                continue
            says_something = any(
                isinstance(n, ast.Constant) and isinstance(n.value, str)
                and any(w in n.value.lower() for w in
                        ("reason", "error", "absent", "could not", "unavailable"))
                for n in body)
            logs = any(
                isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == "_log"
                for n in body)
            if says_something and not logs:
                unlogged.append(h.lineno)
            # the silent store-read handler is the one that used to vanish entirely
            if not says_something and not logs and "_amp_stored" in names:
                unlogged.append(h.lineno)

    assert not unlogged, (
        f"handler(s) at line(s) {unlogged} report a failure to the page but not to the log. "
        f"A failure nobody can see from outside one participant's page is a failure nobody "
        f"will act on.")


def test_the_module_actually_calls_the_logger_it_declares():
    """Guards against the whole set being removed at once, which the per-handler test above would
    not catch if the handlers went with them."""
    assert "_log = " in _ADAPTER_SRC, "adapter.py no longer declares a logger"
    calls = _ADAPTER_SRC.count("_log.warning(") + _ADAPTER_SRC.count("_log.error(") \
        + _ADAPTER_SRC.count("_log.info(") + _ADAPTER_SRC.count("_log.exception(")
    assert calls >= 7, (
        f"adapter.py makes only {calls} logger call(s); it declared a logger and made none at all "
        f"until 2026-09-10, which is the state this test exists to prevent returning to")
