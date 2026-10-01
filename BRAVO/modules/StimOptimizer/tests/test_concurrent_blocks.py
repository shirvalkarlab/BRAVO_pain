"""Independent blocks of one Stim Optimizer request run side by side in threads (2026-10-02): the
readiness check beside the two-stage block, the clinic fit beside each further site's block.

Values, not shapes: a block started in a thread sees this request's context (the request memo is
the same dict, so what one block memoises the others reuse), its answer is the one a direct call
gives, and with the setting off no thread is started at all.
"""
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor

from StimOptimizer import bravo_service as BS

_REQ = contextvars.ContextVar("req", default=None)


def _block(x, *, y):
    memo = _REQ.get()
    memo[x] = memo.get(x, 0) + y
    return (x * 10 + y, threading.get_ident())


def test_a_block_in_a_thread_sees_the_request_context_and_returns_the_direct_answer(monkeypatch):
    monkeypatch.setenv(BS.CONCURRENT_BLOCKS_ENV, "1")
    memo = {}
    _REQ.set(memo)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [BS._start_block(pool, _block, i, y=7) for i in (1, 2)]
        got = [f.result() for f in futures]
    assert [g[0] for g in got] == [_block(1, y=7)[0], _block(2, y=7)[0]] == [17, 27]
    assert all(g[1] != threading.get_ident() for g in got)          # ran in other threads
    assert memo == {1: 14, 2: 14}                                     # the same memo dict


def test_with_the_setting_off_no_thread_is_started(monkeypatch):
    monkeypatch.setenv(BS.CONCURRENT_BLOCKS_ENV, "0")
    assert BS._concurrent_blocks() is False
    assert BS._start_block(None, _block, 1, y=1) is None
    monkeypatch.setenv(BS.CONCURRENT_BLOCKS_ENV, "1")
    assert BS._concurrent_blocks() is True
