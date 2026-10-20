"""REDCap: a 20 s limit, a plain "not answering" error, and ONE download per refresh pass (the PI,
2026-10-06, ruling on decision 22 for the refresh job only; decision 464).

Pages still download the pain reports on every request. Inside one refresh pass, the pass sets a
folder (`BRAVO_REDCAP_PASS_DIR`); the first download writes its table there and every replay of
that pass reads it, so the pass's fingerprint and every answer it builds use the same report set.

No fixtures: the plain-assert runner calls each test with no arguments (`_fake` does the setting up).
"""
import contextlib
import os
import pathlib
import sys
import tempfile
import types

import pandas as pd

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.Biomarkers.routines import redcap_client as rc


class _FakeProject:
    made = []
    calls = []
    fail = None

    def __init__(self, url, token, **kw):
        _FakeProject.made.append(kw)

    def export_records(self, **kw):
        if _FakeProject.fail:
            raise _FakeProject.fail
        _FakeProject.calls.append(kw)
        return pd.DataFrame({"record_id": ["8"], "nrs": [len(_FakeProject.calls)]})


@contextlib.contextmanager
def _fake(pass_dir=False):
    _FakeProject.made, _FakeProject.calls, _FakeProject.fail = [], [], None
    saved_mod = sys.modules.get("redcap")
    saved_creds = rc.get_redcap_credentials
    saved_env = os.environ.pop(rc.PASS_DIR_ENV, None)
    sys.modules["redcap"] = types.SimpleNamespace(Project=_FakeProject)
    rc.get_redcap_credentials = lambda cfg=None: ("https://x/api/", "tok")
    rc.forget_projects()
    with tempfile.TemporaryDirectory() as d:
        if pass_dir:
            os.environ[rc.PASS_DIR_ENV] = d
        try:
            yield d
        finally:
            os.environ.pop(rc.PASS_DIR_ENV, None)
            if saved_env is not None:
                os.environ[rc.PASS_DIR_ENV] = saved_env
            rc.get_redcap_credentials = saved_creds
            if saved_mod is None:
                sys.modules.pop("redcap", None)
            else:
                sys.modules["redcap"] = saved_mod
            rc.forget_projects()


def test_every_redcap_call_has_a_time_limit():
    with _fake():
        rc.pull_redcap()
        assert _FakeProject.made == [{"timeout": rc.REDCAP_TIMEOUT_SECONDS}]
        assert rc.REDCAP_TIMEOUT_SECONDS == 20.0


def test_a_silent_redcap_is_said_plainly():
    import requests
    with _fake():
        _FakeProject.fail = requests.exceptions.ConnectTimeout("timed out")
        try:
            rc.pull_redcap()
        except rc.RedcapUnavailable as exc:
            assert "REDCap did not answer" in str(exc)
        else:
            raise AssertionError("a silent REDCap must raise RedcapUnavailable")


def test_pages_still_download_every_time():
    with _fake():
        rc.pull_redcap()
        b = rc.pull_redcap()
        assert len(_FakeProject.calls) == 2 and int(b["nrs"][0]) == 2


def test_inside_a_pass_one_download_is_shared():
    with _fake(pass_dir=True):
        a = rc.pull_redcap(fields=["nrs"], records=["8"])
        b = rc.pull_redcap(fields=["nrs"], records=["8"])
        c = rc.pull_redcap()                              # a different request: its own download
        assert len(_FakeProject.calls) == 2
        assert a.equals(b) and b is not a                 # each caller its own copy
        assert int(c["nrs"][0]) == 2
