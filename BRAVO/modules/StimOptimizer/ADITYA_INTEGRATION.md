# Aditya settings and survey adapter

The optimizer shares Biomarkers' canonical stored QC survey frame and UTC timestamps. It does
not fetch independent REDCap exports or accept injected production survey rows.

Settings use only eligible stored Percept source files, recheck the RCS08 lead/device source
policy against the JSON itself, and reject preimplant session/history snapshots. The original
explicit-hemisphere parser is retained for legacy and sensing group schemas. Source/group
identities are attached to settings rows. Exact duplicate active settings collapse; conflicting
settings at one timestamp/hemisphere are refused instead of arbitrarily selecting a file.

The normalized therapy table and this specialized adapter share source eligibility and implant
bounds, but are not identical products: the therapy table contains all named groups and dated
pre/post/past configurations, whereas this adapter reconstructs only ActiveGroup snapshots.
The 2026-09-03 read-only comparison decoded 577 eligible JSONs and checked 6,716 active
per-hemisphere settings against the canonical Percept decoder: all amplitude/pulse-width/frequency
triples agree. Canonical import deduplicates repeated therapy records across sources, so equivalence
must include the group/time/side/type key across eligible sources, not only the original source ID.
Five reports exposed a timestamp difference: raw SessionDate differed from the canonical session
estimator by 3,852–7,136 seconds. Their ten per-hemisphere rows match the normalized Post-visit
Therapy records exactly at the estimator time. The adapter now uses that same
`Percept.estimateSessionDateTime` for Groups.Final; historical snapshots retain their own dates.
The final comparison accounts for all 6,716 rows by canonical key and values: 2,320 match within
the original source and 4,396 match deduplicated records from another eligible source. There are
zero unmatched rows, conflicting settings or unsupported groups in this dataset.
Gaps between device snapshots remain an exposure-inference limitation requiring review before
recommendations.

The imported model assumes one program per hemisphere and a shared bilateral frequency.
Multiple interleaved programs, missing program values, duplicate sensing sides and unequal
bilateral frequencies therefore produce explicit unavailable reasons. A missing hemisphere is
unknown, never stimulation off. Genuine zero amplitude remains zero. These refusals avoid
silently fitting a different exposure model than the data support.

Source analytical methods, including the latest negative-slope/majority safeguards, remain
unchanged. Synthetic integration tests cover ambiguity, frequency assumptions and zero/missing
state behavior. Actual data support, end-to-end runtime behavior and scientific validation are
separate integration gates.

One settings stream is reused within a request by the design matrix, delivered-setting census and
closed-loop evidence. The initial live decode cost about 52 seconds on this laptop. Reusing its
result constructs the 86-epoch design matrix from 682 canonical QC reports in 0.262 seconds,
avoiding up to two additional full decodes. Persistent job caching is managed by the API integration.
Three epochs have unknown hemisphere state and remain explicitly unknown. These counts describe
the validation dataset and do not establish prospective recommendation validity.

Unreadable eligible JSONs abort the request with a retryable error. They cannot silently shrink
the exposure history. Raw-policy exclusions remain intentional exclusions, and valid empty
datasets remain supported.
