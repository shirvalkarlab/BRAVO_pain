# Aditya integration boundary

Initial imported source: `shirvalkar/PS_closedloop_deployment` commit
`604ee5cca3cadc635a5270b127203180f7177665`, with reviewed source updates through `8fbe11b`.
Source analytical methods and their regression tests
are retained; this import does not reproduce or endorse historical scientific claims.

Production PRO loads call `modules.AnalysisData.canonical_pros(participant)`. Request-supplied
ProcessedPRO, REDCap credentials/maps and alternate patient configuration cannot replace that
cohort. Standalone fixture mode accepts explicit ProcessedPRO, but never automatically fetches
REDCap. Canonical metric labels/ranges come from the stored form metadata (including expanded
18-item versus standard 15-item MPQ); missing values and true zero values are retained.

Every recording/source query passes through `eligible_source_files`, and RCS08 recording dates
and per-event timestamps have the reviewed implant-day lower bound. Programmed adaptive
threshold queries apply the same eligible source and therapy date filters. Source payloads are
read-only. Spectral transforms still have their own explicitly named analysis eligibility rules
(e.g. missing-aware Welch, contact/source taxonomy); a derived spectral sample is not an Oura or
survey observation.

Assembled PSD and in-process LSB caches include the canonical input-manifest fingerprint.
Per-recording Welch caches include the RCS08 policy source-content digest as well as source hash,
method versions and exact subsecond rating-time identity (sorted float64 bytes, not rounded seconds).
All NPZ writes use a unique temporary file and atomic
replacement, including assembled matrices. Parent integration supplies job deduplication and
bounded overall concurrency.

Availability requests, including nightly availability preparation, do not dispatch an additional
background Welch matrix build. Their returned availability records are unchanged. Full biomarker
analysis builds the spectral matrix when explicitly requested.

The frozen source calibration remains available for research comparison and is explicitly marked
unvalidated against the current canonical-QC cohort, with its SHA256 and source commit.
Loading it does not refit it. Its filename is constrained, and its process cache invalidates when
file content changes. `ready_to_program` is false; analytical gate outcomes remain available as
`research_gates_passed`. There is no device-programming functionality.

The isolated candidate-runtime source suite completed with 721 passed and 47 skipped in 69.55 s.
It uses a synthetic in-memory database with networking disabled. Subsequent focused package
adapter checks passed all 25 tests, including stream reuse, canonical session-time parity and
complete-input failure handling added
after that full run. Authenticated live API and browser testing remain separate gates owned by the
main integration task. Detailed logs are under `reports/prasad-integration-2026-09-03`.

Unexpected recording-read, event-query or event-provenance errors abort analysis with retryable
errors. A failed decode cannot be persisted as a valid empty spectral cache entry. Successfully
decoded recordings with no eligible channels still cache their legitimate empty result. The
`complete_inputs_v1` cache component invalidates both per-record and assembled spectral entries
created before this distinction was enforced.

## Recording alignment consistency

The import now applies native `recording.adjusted_alignment` once to derived `StartTime`,
absolute chronic `Time`, and event timestamps before matching. Relative time coordinates and
source signal values remain unchanged. Payloads carry the applied offset and recording identity;
reapplying the helper does not double-shift. Per-record spectral cache identity includes the
offset, so changing alignment cannot retrieve previously centered spectra.

No sampling-rate scaling is applied: repository inspection found `fs_scaling_factor` stored and
serialized as `SamplingRateScaling`, but no native Python or Client consumer implementing that
scaling. Inventing one here would create a different time/frequency basis from native BRAVO.
The field remains in the input fingerprint so its future supported interpretation can invalidate
results. Native reference: `modules/DataAnalysis.py` exposes additive `Alignment` beside signals;
TimeSeriesAnalysis uses `StartTime + relative time + Alignment`.

Five imported historical live-cohort tests hard-code the prior source participant UID. They are
explicitly opt-in (`BRAVO_RUN_LIVE_SOURCE_TESTS=1`) and skipped in the synthetic suite; their
scientific assertions remain unchanged. Current-cohort golden/API tests are owned by the main
integration task. The synthetic harness uses no production database or credentials.


## September 4 update through d7ea9795

Reviewed nine Prasad source commits after 8fbe11ba, ending at
`d7ea979552944eff2f6ea0ebebc0208bc47ed683`. Selectively reconciled the
ClosedLoopDeployment analytics, device constraints, statistical inference,
cache, and existing research evidence panel into the dirty Aditya working tree.
No whole-source merge, source-branch execution, or raw-data endpoint was added.
Biomarkers and StimOptimizer retain their earlier imported implementations;
the shared input manifest records the latest reviewed integration revision.

- Retain canonical corrected daily PROs, approved spectra, post-implant source
  policy, selected metric/wash-in settings, and queued persistent analysis jobs.
- Wild-cluster bootstrap-t now replaces the unreliable small-cluster CR0 interval
  below 40 clusters. Observational regressions remain confounded; statistical
  significance is not prospective validation or authorization to program.
- Evaluate device rule signs after estimating the edges, distinguish blocking
  failures from missing evidence, and retain duplicate/deferred rule explanations.
- Use eligible, original, post-implant impedance metadata for the device evidence.
  Missing current programmer/capture/artifact facts remain unknown. The upstream
  private `_facts_RCS08.json` and patient-specific PI defaults are not imported.
  The generic offline session-report extractor is installed but is not run on
  unfiltered folders by the live canonical analysis. Connecting an independently
  reviewed summary to ingest remains future work.
- Preserve all PRO and settings columns in the joined-table cache identity;
  failed identity construction bypasses memoization. The imported alternate
  entrypoint routes through the canonical service and cannot accept raw inputs.
- Show measured facts/provenance, edge uncertainty, failures, unknowns, advisory
  shortfalls and deferred duplicate checks in the existing research panel.
  Every result remains research-only; unsupported evidence is not a device ban.
- Historical source retirement findings retain their original 8fbe11ba source
  identity, separate from newly recomputed evidence and the current source version.

Local validation and deployment evidence:
`reports/prasad-integration-2026-09-04/` (ignored, machine-local).
