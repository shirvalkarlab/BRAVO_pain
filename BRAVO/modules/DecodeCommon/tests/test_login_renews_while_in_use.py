"""A login lasts while it is being used (the PI, 2026-11-18).

Found 2026-11-17: the Closed-Loop page's Recompute button looked dead. The login (1 hour, set at
login in `Server/APIs/Auth.py`) had run out, every request was answered 403 as an unknown user, and
the page kept showing its old copy. Django renews a login's hour only when the login is changed,
unless `SESSION_SAVE_EVERY_REQUEST` is on; with it on, every request starts the hour again, so the
login ends one hour after the last request rather than one hour after logging in.

A text check, as in test_cookie_names_per_server.py: Django's settings need the server's
environment, which CI does not have.
"""
from pathlib import Path

SETTINGS = Path(__file__).resolve().parents[3] / "BRAVO" / "settings.py"


def test_every_request_renews_the_login():
    lines = [l.split("#")[0].strip() for l in SETTINGS.read_text().splitlines()]
    assert "SESSION_SAVE_EVERY_REQUEST = True" in lines
