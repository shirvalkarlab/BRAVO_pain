# Oura notification timestamp receiver

Standalone Python 3.11+ WSGI application using only the standard library and SQLite. Nothing here imports BRAVO, fetches Oura data, creates subscriptions, exposes a tunnel, or publishes a service. No credentials or actual user UUID are included.

## Meaning and BRAVO integration

This records an **authenticated Oura data-change notification**, not `LastAppSync`, app-open time, an exact ring upload time, or proof that all streams are current. Oura describes delivery roughly 30 seconds after a sync; background updates also generate notifications. Thirty seconds is approximate delivery latency, not a promised polling interval.

BRAVO should read `/status` **only during its existing scheduled daily or manually requested Oura sync**, validate the returned bound `user_id`, and persist that snapshot with its existing source metadata. Display that stored snapshot until the next existing sync. Do not introduce background status polling or fetch additional scientific data because a notification arrives.

`GET /status` requires `Authorization: Bearer <OURA_READ_TOKEN>` and returns:

```json
{
  "schema_version": 1,
  "source": "oura_webhook",
  "user_id": "11111111-1111-4111-8111-111111111111",
  "as_of": "2026-09-05T17:00:30Z",
  "latest_notification": {
    "event_time": "2026-09-05T17:00:00Z",
    "received_at": "2026-09-05T17:00:30Z",
    "event_type": "update",
    "data_type": "sleep"
  },
  "last_received_at": "2026-09-05T17:00:30Z",
  "meaning": "Authenticated Oura data-change notification; not app-open time or LastAppSync."
}
```

`latest_notification` is the accepted notification with the greatest **event_time**, never the latest retry. `received_at` is the first receipt of that notification. `last_received_at` is the greatest first-receipt time of any distinct accepted notification, including an older event delivered out of order. `as_of` is when this status response was read. All times are UTC ISO 8601. Before any notification, both notification and receipt fields are `null`; absence does not establish that the user has not synced. Delete notifications are retained and explicitly labeled `delete`, not treated as newly available health data.

## Required private configuration

Provide these as protected host environment variables; do not put their values in shell history, repository files, request logs, or browser code:

| Variable | Value |
| --- | --- |
| `OURA_WEBHOOK_DB` | Absolute path in a persistent private directory, e.g. `/var/lib/oura-webhook/state.db` |
| `OURA_USER_ID` | Verified Oura UUID corresponding to the participant's authorized account |
| `OURA_CLIENT_SECRET` | Existing registered Oura application's client secret, at least 32 characters |
| `OURA_VERIFICATION_TOKEN` | Independent random secret, at least 32 characters |
| `OURA_READ_TOKEN` | Separate random secret, at least 32 characters, shared only with BRAVO's server-side sync |

The receiver creates the database owner-only and refuses an existing group/world-readable database. The directory, backups, and parent directories must also be private. Store secrets in the approved host's secret manager. Client-secret rotation changes the keyed deduplication fingerprints; perform a controlled rotation outside Oura's retry window to avoid treating an old event as a new receipt. The greatest event timestamp still cannot move backward.

## Run and test locally

From this directory:

```sh
python3 -m unittest -v test_receiver
```

With private environment configured, `python3 receiver.py` runs a quiet diagnostic server bound only to `127.0.0.1:8787`. It never binds a public address. The diagnostic server is for local testing, not direct public exposure.

## Deploy only after an approved host is selected

Use an approved production WSGI runtime behind HTTPS, with this directory as its working directory and `receiver:create_app()` as its factory. For a host that supplies Gunicorn:

```sh
gunicorn --bind 127.0.0.1:8787 --workers 2 --timeout 10 'receiver:create_app()'
```

Run under a dedicated unprivileged service account with `umask 077`, persistent private local SQLite storage, automatic restart, and a synchronized UTC clock. Do not use ephemeral serverless storage or several hosts sharing a network SQLite file. Configure the HTTPS proxy to buffer requests, enforce a 4096-byte request body limit, apply a short request/header timeout and reasonable rate limits, and leave the JSON body bytes unmodified. Disable query-string/body/header capture in proxy logs and tracing: the challenge query contains the verification token, and authorization headers contain secrets. Do not enable application access logging.

Routes:

- Public `GET /oura-webhook`: verification token plus challenge only; returns `{"challenge":"..."}` after constant-time token verification.
- Public `POST /oura-webhook`: authenticated notification only. Signature is HMAC-SHA256 of the exact timestamp header bytes followed by exact body bytes, keyed by the client secret. Hex signatures are compared in constant time.
- Protected `GET /status`: bearer token, preferably additionally restricted to the BRAVO host at the proxy. Do not expose it without authentication.
- All other routes/methods: 404. All responses: `Cache-Control: no-store`.

Oura's current documentation demonstrates HMAC over `timestamp + JSON.stringify(body)`. This receiver intentionally preserves wire bytes rather than reserializing parsed JSON; proxy/body rewriting will therefore fail verification. A real signed delivery is required during approved activation to confirm the deployment receives Oura's signed wire representation. Never add an unsigned fallback to resolve an integration mismatch.

The timestamp header is interpreted as Unix **seconds**, matching the official ten-digit example. Delivery timestamps older than 65 minutes or over 60 seconds in the future are rejected; this accommodates the documented roughly one-hour retry period. Event times require an explicit timezone and cannot be more than 60 seconds beyond receipt/signing time. This skew allowance is a receiver policy, not a claim about device accuracy. Duplicate semantic events are acknowledged without advancing receipt; reordered events cannot move the latest event backward. Full payloads, object IDs, signatures, and health values are never stored or logged. SQLite keeps user UUID, keyed event fingerprint, event time, first receipt, event type, and data type only. One receiver configuration serves one bound UUID; other users are rejected and cannot update its status.

## External activation still required

An approved HTTPS hostname, deployment credentials, verified Oura UUID, Oura application's client ID/secret, valid participant consent, and chosen event/data subscriptions are required. Neither deployment nor registration has been performed.

After approving and validating the host, register subscriptions using Oura's `POST https://api.ouraring.com/v2/webhook/subscription`, with private `x-client-id` and `x-client-secret` headers and a JSON body containing `callback_url`, `verification_token`, `event_type`, and `data_type`. Use the approved HTTPS `/oura-webhook` URL. Create only selected event/data combinations after listing existing subscriptions to avoid duplicates. The receiver does not need OAuth access/refresh tokens because it does not fetch health records. Keep the application's secret server-side.

List subscriptions via `GET /v2/webhook/subscription`. Check returned `expiration_time` and renew the approved subscription using `PUT /v2/webhook/subscription/renew/{id}` before it expires. Subscription maintenance is separate from BRAVO's data-sync schedule. After registration, verify the challenge, one genuine signed event, duplicate/reordered delivery behavior, protected status, and the next existing BRAVO sync before marking this source active. Missing notifications or expired subscriptions require operator follow-up; they do not prove user inactivity.

## Provenance

Protocol and enums checked 2026-09-05 against the [official Oura V2 documentation](https://cloud.ouraring.com/v2/docs), its Webhook Subscription Routes section, and the downloaded official OpenAPI document. The official schema lists create/update/delete, event/data types, subscription client credentials, and expiration time. The documented notification example includes `event_type`, `data_type`, `object_id`, `event_time`, and `user_id`. UUID binding, size limits, exact-body processing, replay tolerance, metadata-only persistence, and status authentication are explicit receiver design decisions.
