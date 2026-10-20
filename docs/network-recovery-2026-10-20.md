# REDCap and Closed-loop network recovery — October 20

## Change and diagnosis

The browser previously treated Axios `ERR_NETWORK` as a terminal failure. Only
HTTP 502/503/504 received a retry. Actual Chrome XHR checks with the installed
Axios version show that a dropped connection can carry a response object with
status **0**; this is not an HTTP response. Recovery must handle that shape as
well as an absent response.

A separate REDCap refresh race was reproduced: closely spaced focus and
visibility events could queue another full read, discard the first successful
response, and then leave an error if the second read failed. Focus and visibility
now share the serialized saved-revision check. A completed sync still queues the
newer full read, and account/server/participant isolation remains enforced.

The new transport policy retries a specifically inspected read operation once,
after 1.5 seconds, for HTTP 502/503/504 or statusless/status-zero `ERR_NETWORK`.
When the browser explicitly reports offline, it waits up to another 15 seconds
for reconnection before using that retry. A persistent failure returns to the
page's error state. The retry keeps the original server URL.

An exact endpoint allowlist replaces the broad `/api/query` prefix rule.
`queryClosedLoopChosenBand` retries only `Action: read`; choosing or clearing a
band never retries. Unknown operations, other HTTP errors, cancellations and
timeouts do not receive this retry. Analysis reads may repeat existing compute,
provider reads and content-keyed cache/provenance work after a dropped connection;
the policy does not replay a sync/import job, provider mutation or band change.

## Evidence and limits

Further live inspection identified an upstream HTTP connection reset returning
502 from Caddy, without an application worker restart or OOM. The installed
Caddy configuration used its 120-second upstream idle timeout, while Gunicorn's
two-second keepalive was passed to Uvicorn. Caddy documents this mismatch as a
cause of resets and 502 responses for POST requests. The follow-up configuration
disables idle connection reuse only between Caddy and the application; public
HTTPS, authentication and write semantics remain unchanged.
See [Caddy's HTTP transport documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#the-http-transport).

A second duplicate-read trigger was found in the sync button. On page mount,
the initial status response could replay a historical completed job as a new
completion, suppressing the initial timeline response and queueing another full
read. The first successful status response now establishes the mount's baseline.
An observed running job completing, or a newly started job completing, still
refreshes the views once. Tests cover historical succeeded/failed jobs, remounts,
account isolation and recovery after an uncertain Start response without
replaying the Start request. Deployment of these follow-up changes is recorded
in [release status](release-status.md) after acceptance.

The precise underlying cause of every historical connection drop remains
unconfirmed. The change addresses demonstrated client recovery and refresh-ordering
failures; it does not claim to eliminate connectivity failures themselves.

Intentional connection failures are tested against a loopback-only synthetic
server with actual Chrome and the installed Axios library. Production providers
are not fault-injected. Unit regressions cover retry limits, offline deadlines,
listener cleanup, HTTP/access failures, chosen-band write exclusion, original
server binding and focus/sync ordering.

This change does not alter scientific calculations, provider configuration,
source ingestion, saved band choices or the unresolved PSD assignments.
Deployment and exact acceptance results are recorded in the current release
status after verification; this document alone is not a deployment claim.
