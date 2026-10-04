"""The REDCap project connection is kept for up to an hour per process (the PI, 2026-10-04,
decision 432, plan item 5). Each pain-report download made three calls: the project's data
dictionary (metadata, 0.23-0.48 s), the form-event map (0.22 s) and the reports themselves (0.34-0.44
s). The first two describe the project's design, which changes only when the project is edited,
never when a report is filed; the connection that holds them is now kept, and the reports are
still fetched on every call, so no answer can be a report short.

Values: two downloads within the hour make one connection and two report fetches; after the hour,
a new connection; different credentials, a new connection."""
import sys
import types

from modules.Biomarkers.routines import redcap_client as RC


class _FakeProject:
    made = []
    exports = []

    def __init__(self, url, key):
        _FakeProject.made.append((url, key))

    def export_records(self, **kw):
        _FakeProject.exports.append(kw)
        import pandas as pd
        return pd.DataFrame({"record_id": [1], "n": [len(_FakeProject.exports)]})


def _with_fake(fn):
    real_mod = sys.modules.get("redcap")
    sys.modules["redcap"] = types.SimpleNamespace(Project=_FakeProject)
    real_env = {k: RC.os.environ.get(k) for k in ("REDCAP_API_URL", "REDCAP_API_TOKEN")}
    RC.os.environ["REDCAP_API_URL"], RC.os.environ["REDCAP_API_TOKEN"] = "u", "k"
    _FakeProject.made, _FakeProject.exports = [], []
    RC.forget_projects()
    try:
        fn()
    finally:
        RC.forget_projects()
        if real_mod is None:
            sys.modules.pop("redcap", None)
        else:
            sys.modules["redcap"] = real_mod
        for k, v in real_env.items():
            if v is None:
                RC.os.environ.pop(k, None)
            else:
                RC.os.environ[k] = v


def test_two_downloads_within_the_hour_share_one_connection_and_fetch_the_reports_twice():
    def run():
        a = RC.pull_redcap(fields=["x"])
        b = RC.pull_redcap(fields=["x"])
        assert len(_FakeProject.made) == 1 and len(_FakeProject.exports) == 2
        assert int(a["n"].iloc[0]) == 1 and int(b["n"].iloc[0]) == 2
    _with_fake(run)


def test_after_the_hour_a_new_connection_is_made():
    def run():
        clock = [1000.0]
        real = RC._now
        RC._now = lambda: clock[0]
        try:
            RC.pull_redcap()
            clock[0] += RC.PROJECT_KEEP_SECONDS + 1
            RC.pull_redcap()
        finally:
            RC._now = real
        assert len(_FakeProject.made) == 2
    _with_fake(run)


def test_other_credentials_make_their_own_connection():
    def run():
        RC.pull_redcap()
        RC.os.environ["REDCAP_API_TOKEN"] = "another"
        RC.pull_redcap()
        assert [k for _, k in _FakeProject.made] == ["k", "another"]
    _with_fake(run)
