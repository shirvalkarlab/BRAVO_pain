# Release status

The shared site is [BRAVO on Jetstream](https://bravo-aditya.mde260021.projects.jetstream-cloud.org/).
Access requires an individually authorized account or the shared read-only lab
account supplied privately by the administrator. This is a research application;
a chart or candidate is not a clinical programming instruction.

## Settings and source context — live acceptance passed

The settings/source-context release is deployed. Neural intervals link to the
original reports contributing their samples; details retain recovered program
settings, controller relationships, dated observations and chronology limits.
Source configuration does not establish continuous adaptive delivery between
observations. Conflicting configurations remain individually inspectable.
Readable labels preserve source values, and settings actions expose populated
recorded settings or meaningful sensing details. See
[Reading settings and source context](settings-source-context.md).

All seven Aditya tab journeys passed normal read-only browser checks covering
populated charts, physical tooltips, available selectors and expanded details.
Checks included a real source conflict, settings source values, medication
regimen/condition details, supported wearable defaults and daily/sleep-sample
hovers. Tooltip clipping was checked at desktop and narrow viewport sizes.
Oura Refresh view preserved its selected metrics and repopulated all five saved
charts. This is bounded
journey and sampled-data evidence, not certification of every observation,
optional native analysis or complete upstream coverage.

Normal owner/viewer saved-data reads preserved scientific values and access
boundaries. Read-only checks preserved reviewed PSD assignments, their source
qualifications and raw spectra. Runtime identity, services and existing target
timers passed final operational checks; acceptance started no provider import.
The native saved Closed-loop view recovered from initial browser network errors
on a normal reload; optional analyses are outside this acceptance.
Continuous activation, missing home assignments and historical medication use
remain qualified where the source evidence does not establish them.

The public application candidate `10bc3e248415b7246076f5ed502e6730172c8fb9`
passed all five validation jobs. The final publication and its exact review/CI
revision are tracked in [PR #21](https://github.com/shirvalkarlab/BRAVO_pain/pull/21).
Public source retains the existing lab lineage and publication boundaries.
Documentation commits do not change the deployed application.

## Earlier accepted recent-neural release

The recent-neural follow-up is deployed and passed live acceptance checks.
Multimodal Summary and Neural Data displayed matching recent observations with
actual timestamps and gaps. All seven Aditya tabs loaded; native PSD and Biomarkers
views showed qualified contact assignments, the Biomarkers histogram populated,
Closed-loop loaded, and a missing implant date displayed **Not recorded**. Reviewed
home-continuity assumptions and uncertain settings remain explicit. Contact
overlays retain conflicting export labels and raw spectra; they are not source
agreement. These checks do not certify every optional report or complete coverage.

The public source is merged through [PR #19](https://github.com/shirvalkarlab/BRAVO_pain/pull/19)
at `a8794b953c7ce05c5317b5a947993d32ef4e069b`; all five checks passed for reviewed
candidate `7e1731125437fd0f62424d45a38a4ff4d0d14afc`. Final operational checks
confirmed application services, existing daily/manual timers and provider enable
flags. Source refresh remains separate from application deployment: an enabled
timer does not prove a future import succeeded or all upstream files are current.

A separately reviewed withheld source was accepted through a bounded import.
A repeat added no duplicates, and read-only canonical checks verified the added
data while preserving existing records and reviewed contact qualifications.
Unverified device identities remain withheld by the normal importer. Earlier
failed sync receipts remain historical records; this repair is not a claim that
a new all-stream sync has completed.

## Earlier shared-viewer acceptance

The October 20 shared-viewer application release was deployed and is now superseded
by the recent-neural release above. Its reviewed public
source is merged through [PR #16](https://github.com/shirvalkarlab/BRAVO_pain/pull/16)
at `86bbad6dbbe15263b01d486c47b7fe95c30003b0`; all five CI jobs passed for the
reviewed public candidate `712e362ed15d01deaba5a15ab54ec3a6d44ea77c`. The release
retains the earlier network-recovery, concurrent-import and sync-refresh corrections.

The public source contains the reviewed publication variant described in
[publication provenance](publication-provenance.md), rather than private deployment
inputs or history. Documentation commits do not change the installed application.
The operator's acceptance record retains the exact deployed image/revision identity.

Normal shared-viewer sign-in, representative saved-data responses matching the
authorized owner, permission denials and independent session logout passed live
checks. Twenty independent sessions completed 40 concurrent lightweight reads
without failures. A separate check launched twenty complete chart reads concurrently
(ten REDCap and ten Oura); all succeeded with unchanged saved results, with the
slowest response taking about a minute. This supports simultaneous viewing with
that waiting-time limit, but is not a performance guarantee for twenty uncached
heavy analyses. Application services and owned timers
were preserved; these acceptance checks did not start a provider import.

All seven Aditya tabs populated in the shared-viewer browser. Biomarkers and
Stimulation Optimizer populated, and Closed-loop completed; all three disabled
Recompute. Native Therapy History finished loading with device selection and dated
history. The owner's initial Closed-loop load and the viewer's initial Stimulation
Optimizer load recovered from network errors on fresh reloads; an initial viewer
neural read recovered with **Refresh view**. This bounded browser check does not
certify every optional native report or heavy uncached analysis. The release does not guarantee complete data
coverage or eliminate future network and provider failures. A completed wiring comparison can still withhold a recommendation
when matching ratings are absent. See [shared viewer](shared-viewer.md) for its
permissions and the distinction between refreshing a view and running a sync.

The fix handles transient browser connection errors with one bounded safe-read
retry and prevents duplicate focus/visibility events from discarding a successful
timeline response. The follow-up disables upstream idle connection reuse and
prevents a historical sync completion from replaying on page mount. It never
retries chosen-band writes. Local tests and an actual
browser against a synthetic failing server verified recovery; the underlying
cause of every historical connection drop remains unconfirmed.

## Known limits

- Conflicting PSD source labels remain retained. A separately reviewed timeline
  assignment is explicitly distinguished from source agreement; unresolved
  assignments remain ambiguous and raw spectra remain available.
- Unverified recent neural periods are labeled and remain separate from reviewed
  home analysis eligibility.
- Provider availability, completed imports and valid analysis inputs are separate
  requirements. A working page does not guarantee complete or current coverage.
- Optional model weights and participant-specific clinical evidence are private
  deployment inputs and are absent from this source snapshot.
- This public source omits private anatomy presentation overrides. It displays
  supplied device/record labels without inferring anatomy from a participant code.
- Persistent network failures still surface an error after the bounded retry;
  access errors, timeouts and mutations are not automatically replayed.

See the [user guide](user-guide.md), [network recovery record](network-recovery-2026-10-20.md)
and [publication provenance](publication-provenance.md).
