'One-time authorized Google OAuth consent for sheet export. Run this utility on a machine with a browser. Supply client and token paths as arguments, or use the ignored BRAVO/secrets defaults. The token is written with owner-only permissions. Configure the OAuth application audience and publication state appropriately; testing-mode credentials may expire. Revoke access through the Google account security settings and remove the token when no longer needed.'
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
