"""Each BRAVO can have its own login-cookie names (2026-10-02, decision 374).

A browser keeps one cookie per host NAME and ignores the port, so the local BRAVO at
`http://localhost` and the Jetstream2 BRAVO reached through a tunnel at `http://localhost:8080`
shared one `sessionid`: logging in to one made the other see an unknown login and answer 403 to every
request. `BRAVO_COOKIE_SUFFIX` (set in Jetstream2's compose override only) is added to the session and
CSRF cookie names; unset, they stay Django's own, so the local BRAVO is unchanged.

The rule lives in `BRAVO/cookie_names.py`, tested on its own (no Django settings, so CI can run it);
one check confirms settings.py uses it.
"""
import sys
from pathlib import Path

BRAVO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BRAVO_ROOT))

from BRAVO.cookie_names import cookie_names  # noqa: E402


def test_with_no_suffix_the_cookie_names_are_djangos_own():
    assert cookie_names({}) == ("sessionid", "csrftoken")


def test_an_empty_or_blank_suffix_changes_nothing():
    assert cookie_names({"BRAVO_COOKIE_SUFFIX": ""}) == ("sessionid", "csrftoken")
    assert cookie_names({"BRAVO_COOKIE_SUFFIX": "  "}) == ("sessionid", "csrftoken")


def test_a_suffix_is_added_to_both_cookie_names():
    assert cookie_names({"BRAVO_COOKIE_SUFFIX": "_js2"}) == ("sessionid_js2", "csrftoken_js2")


def test_settings_takes_its_cookie_names_from_that_rule():
    text = (BRAVO_ROOT / "BRAVO" / "settings.py").read_text()
    assert "from BRAVO.cookie_names import cookie_names" in text
    assert "SESSION_COOKIE_NAME, CSRF_COOKIE_NAME = _cookie_names()" in text
