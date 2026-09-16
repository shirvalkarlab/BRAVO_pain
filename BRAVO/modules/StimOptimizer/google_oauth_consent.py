"""One-time consent for the "Make Google sheet" export (decision 181): sign the server in AS YOU.

Run this ON A MACHINE WITH A BROWSER (the PI's Mac), from the repository root, once:

    cd /Users/pshirvalkar/dev/BRAVO_pain
    python3 -m venv /tmp/gauth && /tmp/gauth/bin/pip install -q google-auth-oauthlib
    /tmp/gauth/bin/python BRAVO/modules/StimOptimizer/google_oauth_consent.py

It opens your browser at Google's consent page for the OAuth client whose JSON sits at
`BRAVO/secrets/google_oauth_client.json`; you sign in and click Allow for Drive and Sheets; it
then writes `BRAVO/secrets/google_oauth_token.json` (owner-only permissions) and prints the
account it was granted for. The server reads that file on its next worker restart. Both files are
inside `secrets/`, which git ignores. Revoke at any time at myaccount.google.com > Security >
Third-party access; then delete the token file.

The app's audience in Google Cloud must be EXTERNAL and PUBLISHED (a personal Gmail can never be
"inside" a Cloud organisation, so Internal refuses it; an External app left in "Testing" has its
tokens expire after seven days, which would break the button silently). Done 2026-09-16.
"""
from __future__ import annotations

import json
import os
import sys

SCOPES = ("https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/spreadsheets")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # BRAVO/
    client = argv[0] if argv else os.path.join(root, "secrets", "google_oauth_client.json")
    token = argv[1] if len(argv) > 1 else os.path.join(root, "secrets", "google_oauth_token.json")
    if not os.path.isfile(client):
        print(f"no OAuth client file at {client}; download it from Google Cloud > Credentials "
              f"(OAuth client ID, Desktop app) and put it there", file=sys.stderr)
        return 2
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("google-auth-oauthlib is not installed here: pip install google-auth-oauthlib",
              file=sys.stderr)
        return 2
    flow = InstalledAppFlow.from_client_secrets_file(client, scopes=list(SCOPES))
    creds = flow.run_local_server(port=0, prompt="select_account consent", access_type="offline")
    if not creds.refresh_token:
        print("Google returned no refresh token; revoke the app's access in your Google account "
              "and run this again", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(token), exist_ok=True)
    with open(token, "w") as fh:
        fh.write(creds.to_json())
    os.chmod(token, 0o600)
    who = "(account not reported)"
    try:
        from google.auth.transport.requests import AuthorizedSession
        r = AuthorizedSession(creds).get("https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)")
        who = r.json().get("user", {}).get("emailAddress", who)
    except Exception:                                  # noqa: BLE001 - informational only
        pass
    print(f"wrote {token} for {who}; restart the server's workers to use it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
