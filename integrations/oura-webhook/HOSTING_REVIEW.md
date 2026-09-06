# Hosting setup for review — not deployed

**Superseded:** The user chose “Use latest measurement; no hosting.” This is an unused review artifact. No receiver hosting, deployment, or webhook activation is planned; active BRAVO work uses the cached latest Oura measurement from its existing daily/manual sync.

**Proposed host: Cloudflare Workers Free with one SQLite-backed Durable Object.** This supplies an HTTPS receiver that remains available while the Mac sleeps, with durable notification metadata and no always-running rented server. The implementation is prepared in `cloudflare/`; its bundle and real local Worker runtime have been verified with synthetic values. It has not been uploaded, provisioned remotely, authenticated against a Cloudflare account, or registered with Oura.

The decision is whether this specific participant-linked metadata and the Oura application secret may be hosted in the selected Cloudflare account. An opaque Oura UUID is **pseudonymous, not anonymous**. Notification dates and data categories may themselves be sensitive. This proposal makes no institutional approval, BAA, HIPAA, or data-residency claim. If the institution requires these records to stay on an approved institutional host, use the existing Python receiver behind that host's HTTPS service instead; its deployment instructions and identical status schema are in `README.md`.

## What runs where

```text
Oura signed notifications → Cloudflare HTTPS Worker → private SQLite Durable Object
                                         ↑
Mac's existing daily/manual Oura sync → authenticated GET /status
                                         ↓
                             local BRAVO metadata snapshot
```

Cloudflare receives notifications continuously. BRAVO reads the status only during its existing daily/manual sync and displays that saved snapshot until its next sync. There is no 30-second polling timer, no new scientific data fetch, no Mac tunnel, and no incoming connection to the Mac. The displayed timestamp is an Oura data-change event notification, not a direct measurement of `LastAppSync`.

## Compare the concrete options

| Choice | Availability while Mac sleeps | Cost/operations | Data custody |
| --- | --- | --- | --- |
| Proposed Cloudflare Worker + SQLite Durable Object | Independent of Mac | Free-plan allowances; no VM maintenance; rejected operations if free limits are exceeded | Cloudflare account processes Oura UUID and event metadata; institutional review needed |
| Approved institutional HTTPS Linux host + existing Python receiver | Independent of Mac | Existing host capacity and owner-operated updates/backups; host availability must be confirmed | Fits the institution's approved hosting arrangement if specifically authorized |
| Mac-local receiver or tunnel | Depends on Mac/network being awake | Operationally unreliable for this purpose | Does not solve always-available receipt |

An actual institutional hostname/account has not been supplied or verified. Cloudflare is therefore a concrete **proposal**, not a claim that a public host is already approved.

## Expected cost and limits

As checked September 5, 2026, Workers Free includes 100,000 requests/day; SQLite Durable Objects are available on the Free plan. Durable Object Free allowances include 100,000 requests/day, 13,000 GB-seconds/day, 5 million SQL rows read/day, 100,000 rows written/day, and 5 GB total SQL storage. Exceeding a Free-plan allowance fails the affected operations rather than automatically providing unlimited service. These are shared account allowances, not dedicated reservations for BRAVO. [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/), [Durable Objects pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/).

For illustration, 1,000 distinct notifications/day plus a few daily/manual status reads is comfortably below request allowances; each notification writes a metadata row and associated indexes. Actual Oura notification volume has not been measured. Unauthenticated public traffic still consumes Worker requests even though it cannot access the Durable Object. Free-tier availability is not a clinical-service SLA. The reviewed account must remain on **Workers Free**; do not enable a paid plan or paid feature without separate authorization. No account setting or subscription has been changed.

## Prepared artifacts and scope

- `cloudflare/worker.mjs`: Worker request validation and SQLite Durable Object persistence. No third-party runtime library or outbound health-data requests.
- `cloudflare/wrangler.jsonc`: binding and SQLite migration; preview/public Workers URLs disabled; `ACTIVATION_APPROVED=false` makes all requests fail closed.
- `cloudflare/worker.test.mjs`: Node tests using actual WebCrypto, HTTP objects, and SQLite. Only the Cloudflare base class and binding/storage adapter are substituted.
- `cloudflare/runtime-check.mjs`: synthetic acceptance against an already-running disposable Worker on loopback only.
- Existing Python WSGI receiver and tests remain available for an institutional host.

The current Wrangler configuration uses the documented `new_sqlite_classes` migration form. Cloudflare also offers newer declarative class exports; do not mix the two configuration mechanisms. [SQLite storage configuration](https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage/).

## Data, secrets, and endpoints

Stored fields: Oura UUID, keyed deduplication fingerprint, event timestamp, first receipt timestamp, event type, and data type. Object IDs are used transiently to derive the keyed fingerprint; raw request bodies, health values, object IDs, signatures, and tokens are not saved in application storage or logs. Provider infrastructure still processes requests, including the verification query and notification payload. Disabled Worker observability is not a promise that the provider keeps no operational metadata.

Secrets required in the approved account's Worker secret bindings: `OURA_CLIENT_SECRET`, `OURA_VERIFICATION_TOKEN`, `OURA_READ_TOKEN`, and `OURA_USER_ID`. The three secrets must be independent and at least 32 characters. The UUID must be verified against the authorized account before activation. The Cloudflare account and Oura client ID are also needed for deployment and subsequent subscription management; no real values are checked in.

Public paths after approval: challenge `GET /oura-webhook`, signed-event `POST /oura-webhook`. Protected path: `GET /status` with the read bearer token. No browser CORS access, UI, health-data fetch endpoint, or unauthenticated status is provided. Invalid signatures and token requests are rejected before allocating a Durable Object. Notification identity is selected server-side from the configured UUID; callers cannot choose another participant.

The status response is identical in field names and meaning to the Python receiver: `schema_version`, `source`, `user_id`, `as_of`, `latest_notification`, `last_received_at`, `meaning`. ISO timestamps may contain a `.000` fractional-second component. Latest event time cannot move backward; duplicates do not advance first receipt; delete events stay labeled delete. The timestamp age policy accepts up to 65-minute delivery delay and 60-second forward clock skew. Body reads are capped at 4096 bytes even without a reliable Content-Length header. Raw-body HMAC and real signed-delivery verification remain as documented in `README.md`.

## Local review and activation sequence

Local tests require Node 24+ for built-in SQLite and module hooks:

```sh
cd cloudflare
node --test worker.test.mjs
```

**Only after the hosting/data-custody proposal is approved**, confirm the selected Cloudflare account and Free plan, then use the approved Wrangler release to validate/bundle the configuration. Before deployment run `wrangler whoami` to confirm account identity. Wrangler 4.129.0 was installed only under `/private/tmp/oura-worker-runtime`. A `wrangler deploy --dry-run` compilation succeeded (9.01 KiB bundle). `wrangler dev --local` then ran the real workerd 1.20260903.1 runtime with its bundled Miniflare 5.20260903.0-alpha on `127.0.0.1:8789`, using only synthetic UUID/tokens and disposable local SQLite storage. Local signature, challenge, status and ordering acceptance passed. The server was stopped afterward. No Wrangler login, secret upload, remote development command, remote deployment, or Oura subscription call was run.

The activation work is concrete but still pending:

1. Verify the approved Cloudflare account, data-custody decision, Oura UUID, and application credentials. Revalidate the already-tested Worker bundle/configuration if the approved deployment uses a different Wrangler version. Cloudflare account entitlements and remote operation still need verification.
2. Provision this Worker and its SQLite namespace with `ACTIVATION_APPROVED=false`, public URLs disabled, and no custom route. Upload secrets through protected interactive Worker-secret input or the approved secret manager. Do not place real secret values in commands, files, or logs.
3. With the approved public hostname selected, enable its HTTPS route (or explicitly approve the assigned `workers.dev` URL), then set `ACTIVATION_APPROVED=true`. Do not enable preview URLs or Worker request tracing.
4. Confirm unauthenticated status is rejected and signed synthetic validation behaves correctly. Register only approved Oura subscription combinations at the HTTPS `/oura-webhook` endpoint, after checking for existing subscriptions. Configure subscription renewal before the returned expiration.
5. Verify one genuine Oura signed delivery and exact-body signature compatibility, then confirm the next existing BRAVO sync saves the returned status. Confirm retries do not advance the event display. Until these checks pass, label this source pending activation.

Rollback: deactivate the receiver/public route and remove or suspend the Oura subscriptions through their supported API. Leave existing local BRAVO snapshots labeled with their old observation time; do not turn an inactive receiver into an apparent fresh sync. Deleting the cloud namespace or its retained metadata is a separate explicit cleanup action.

## Verification limit

Local tests exercise signing, authentication, UUID isolation, exact-body tampering, strict metadata schema, duplicate fields, replay/future bounds, out-of-order delivery, persistence across object reconstruction, storage errors, and metadata-only retention. The real local workerd/SQLite Durable Object runtime passed signed-notification, authentication, UUID binding, exact-body tampering, replay/future rejection, status, deduplication, ordering, and delete-event checks. Persistent reconstruction is covered by the SQLite unit suite; a separate real-runtime restart test was not run. The free-account entitlement, remote HTTPS endpoint, Oura registration, and genuine webhook delivery remain **unverified until approved activation**.

Local verifier note: direct Miniflare API startup returned an opaque internal runtime error; the official pinned Wrangler `dev --local` command succeeded and was used for the real-runtime acceptance. No product-code workaround or authentication bypass was added.
