# Release status

The shared site is [BRAVO on Jetstream](https://bravo-aditya.mde260021.projects.jetstream-cloud.org/).
Access requires an individual authorized account. This is a research application;
a chart or candidate is not a clinical programming instruction.

The shared application currently runs
`05ce6fa6244bff65151af6b6d3ccc27215734329`. The follow-up
`f79d381de29f46d0b6b7a0e10f15b505a7fff605` was rolled back after live acceptance
exposed a cold-start import recursion in the Closed-loop wiring comparison.

The public source now incorporates replacement candidate
`effa7a838a6e4bbf1de535dff1bae8b5e09a3217`, which fixes concurrent import-alias
registration. Its final deployment acceptance remains pending. The code and
passing tests do not establish that the candidate is installed; this page will
be updated after actual live acceptance.

The fix handles transient browser connection errors with one bounded safe-read
retry and prevents duplicate focus/visibility events from discarding a successful
timeline response. The follow-up disables upstream idle connection reuse and
prevents a historical sync completion from replaying on page mount. It never
retries chosen-band writes. Local tests and an actual
browser against a synthetic failing server verified recovery; the underlying
cause of every historical connection drop remains unconfirmed.

## Known limits

- Unresolved PSD contact assignments remain ambiguous, with raw spectra retained.
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
