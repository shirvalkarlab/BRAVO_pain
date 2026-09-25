"""Speed-up item 4 (the PI, 2026-09-25): work repeated inside ONE request is done once.

Measured on RCS08 (a Closed-Loop request, a cold store): the tile key built 15 times (8.1 s), the
recordings decoded 9 times (6.7 s), REDCap pulled 3 times (3.6 s). The within-request scope that
already held the pain reports now also holds these, and it still cannot outlive the request: a new
recording or report is seen by the next request. Plain asserts; container suite.
"""
from modules.Biomarkers import bravo_service as BS


def test_inside_one_request_a_value_is_computed_once_and_gone_after():
    calls = []
    def compute():
        calls.append(1)
        return [len(calls)]
    with BS.pro_request_scope():
        a = BS._request_memo(("thing", "p"), compute)
        b = BS._request_memo(("thing", "p"), compute)
        assert calls == [1] and a == b == [1]
        a.append(99)                                     # a caller changing its copy
        assert BS._request_memo(("thing", "p"), compute) == [1]
    assert BS._request_memo(("thing", "p"), compute) == [2]  # a new request computes again
    assert BS._request_memo(("thing", "p"), compute) == [3]  # and outside a request, every time


def test_the_scope_nests_so_an_inner_endpoint_shares_the_outer_request():
    calls = []
    with BS.pro_request_scope():
        BS._request_memo(("x",), lambda: calls.append(1) or 1)
        with BS.pro_request_scope():
            BS._request_memo(("x",), lambda: calls.append(1) or 1)
    assert calls == [1]
