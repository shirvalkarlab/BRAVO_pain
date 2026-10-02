"""Each BRAVO can have its own login-cookie name (2026-10-02).

A browser keeps one cookie per host NAME and ignores the port, so the local BRAVO at
`http://localhost` and the Jetstream2 BRAVO reached through a tunnel at `http://localhost:8080` shared
the one `sessionid` cookie: logging in to one made the other see an unknown login and answer 403 to
every request. `BRAVO_COOKIE_SUFFIX` (set in Jetstream2's compose override only) is added to the
session and CSRF cookie names. Unset, the names stay Django's own, so the local BRAVO is unchanged.

Each check runs a fresh interpreter, because settings are read once at import.
"""
import os
import subprocess
import sys
from pathlib import Path

BRAVO_ROOT = Path(__file__).resolve().parents[3]

PROBE = (
    "import os, sys; sys.path.insert(0, %r); os.environ['DJANGO_SETTINGS_MODULE'] = 'BRAVO.settings'\n"
    "from BRAVO import settings as S\n"
    "print(S.SESSION_COOKIE_NAME, S.CSRF_COOKIE_NAME)\n"
) % (str(BRAVO_ROOT),)


def _names(suffix):
    env = {k: v for k, v in os.environ.items() if k != "BRAVO_COOKIE_SUFFIX"}
    if suffix is not None:
        env["BRAVO_COOKIE_SUFFIX"] = suffix
    out = subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True,
                         timeout=120, cwd=str(BRAVO_ROOT))
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.strip().splitlines()[-1]


def test_with_no_suffix_the_cookie_names_are_djangos_own():
    assert _names(None) == "sessionid csrftoken"


def test_an_empty_suffix_changes_nothing():
    assert _names("") == "sessionid csrftoken"


def test_a_suffix_is_added_to_both_cookie_names():
    assert _names("_js2") == "sessionid_js2 csrftoken_js2"
