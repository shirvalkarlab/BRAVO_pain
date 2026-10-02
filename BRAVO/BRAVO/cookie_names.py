"""Login-cookie names for one BRAVO (decision 374).

A browser keeps one cookie per host NAME and ignores the port, so two BRAVOs reached as `localhost`
(the local one at :80, Jetstream2's through an SSH tunnel at :8080) shared one `sessionid` and each
answered 403 to the other's login. BRAVO_COOKIE_SUFFIX gives a server its own names; Jetstream2's
compose override sets "_js2". Unset, the names are Django's own.

A module of its own, imported by settings.py, so the rule can be tested without Django's settings
(which need the server's environment; CI has none), as `maths_threads.py` is (decision 353).
"""
import os

SUFFIX_ENV = "BRAVO_COOKIE_SUFFIX"


def cookie_names(environ=None):
    suffix = (environ if environ is not None else os.environ).get(SUFFIX_ENV, "").strip()
    return "sessionid" + suffix, "csrftoken" + suffix
