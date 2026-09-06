# BRAVO: viewing the shared site and running your own copy

## Choose what you need

| Goal | Where it runs | What you can change |
| --- | --- | --- |
| View the lab's current data | Owner-provided HTTPS link | Your navigation and display preferences only |
| Explore or edit an independent copy | Your own computer, at `http://127.0.0.1:8080` | Your local data and settings |
| Maintain the shared site | Designated host and owner's administrator account | Shared data, configuration, accounts and releases |

The shared site's viewer account cannot upload, delete, edit patient records,
start synchronization, or download original source files. Do not use the shared
administrator account for ordinary viewing. Local accounts, databases and API
credentials are separate from shared-site accounts.

## View the shared site

1. Obtain the current HTTPS link and an individual viewer account from the owner.
   Credentials are distributed privately; they are not in this repository.
2. Open the link in a current browser and sign in. For a Tailscale **Funnel** link,
   viewers do not need Tailscale installed or a Tailscale account.
3. Select the study participant and desired report. The displayed source dates
   indicate the latest represented data, which may precede the upload/sync date.
4. Change chart ranges or display controls as needed. Editing and synchronization
   remain restricted to the administrator.
5. Log out when finished, especially on a shared computer.

If the link is unavailable, first ask whether the host is awake, connected and
running BRAVO and Tailscale. Repeatedly resetting a password does not fix an offline
host. An expired session requires signing in again. Send the owner the page name
and error message; never send a password or API token.

## Run an independent local copy

Use the [installation and account-provisioning instructions](../local-deployment.md)
and the dated release handoff.
A source clone alone does not contain patient data, credentials or a working
administrator account. Obtain authorized data separately or configure your own
REDCap/Oura credentials. A viewer account on the shared site does not grant source
export permission.

Keep the local instance's database volumes and encryption keys together. Do not
point an independent instance at the shared database, shared writable Dropbox
folder, or the owner's Slack/Slides automation destinations. Do not copy the
owner's scheduled jobs into an independent analysis installation.

Verify the local URL and build identity before making edits. Edits to your own
instance must not change the shared site. Use a different local port if another
application already owns port 8080; do not stop unrelated software to claim it.

## Host connectivity

Funnel exposes the configured HTTPS service to the internet; BRAVO's login and
server-side permissions control data access. Tailscale **Serve** is different:
its HTTPS service is private to authorized tailnet devices. Both require the host
to stay awake and connected. The Mac App Store Tailscale client requires desktop
login after a reboot. A laptop test host is therefore not automatically an
unattended, reboot-resilient production service.

Funnel is included in Tailscale plans. Free-plan eligibility is separate from
whether the feature exists; verify the account's permitted use before promising
ongoing free institutional hosting. See the [official Funnel guide](https://tailscale.com/docs/features/tailscale-funnel)
and [plan terms](https://tailscale.com/pricing).

## Verification status

On 09/05/2026, the initial primary-laptop Funnel was tested from the second
laptop through a forced public relay address. Normal viewer login and data access
passed; anonymous data access and viewer mutation/source-download routes were
denied. Logout removed access again. Birthdates were hidden and session cookies
were secure. The private dated receipt records the exact host and test output.

Replacement-host migration is a separate acceptance step. Consult its dated
handoff for the current host, published commit, rollback and sole scheduler owner.
A successful initial hosting test does not certify a future replacement host.
