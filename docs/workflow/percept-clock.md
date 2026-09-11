# Percept clock recovery for biomarker inputs

Exported INS wall-clock timestamps can change when the same stored observation is
exported again. Biomarker inputs therefore use preserved device clock blocks and
counter offsets, anchored to programmer SessionDate/SessionEndDate. Original
exports, stored dates, sample arrays and manual alignment settings are retained.

`PerceptClock.extract_source` indexes Initial/Final programmer/device clock pairs
and FirstPacketDateTime coordinates before the decoder mutates its input. A
participant-scoped map checks continuity using both phases, prefers Final anchors
for mapping, and interpolates only between observed anchors in the same device
and positive clock block. A missing coordinate, nonmonotonic block, unbracketed
counter or anchor-intercept change greater than 120 seconds is unresolved and
excluded from clock-corrected biomarker input. The discontinuity threshold is a
conservative quality guard, not a statistical confidence interval. Programmer
wall time is assumed correct; acquisition latency and unobserved clock changes
limit precision. No offset is fitted to pain values or decoding performance.

Time-domain, montage and power-stream start times are mapped through their
FirstPacketDateTime coordinates. Relative samples and sampling rates are not
warped. Chronic trend timestamps have no FirstPacketDateTime mapping and remain
outside this correction's supported scope. A saved manual alignment is applied
once after recovery. Conflicting manual shifts on physical duplicates fail the
analysis rather than choosing an arbitrary row.

Patient-event PSD identity is device, clock block, counter and hemisphere.
Every pair of copies must have equivalent frequency/spectral arrays, allowing
at most four representable binary64 steps per value for database serialization.
This comparison never rounds or rewrites the stored arrays. Meaningful spectral
disagreements at the same physical coordinate fail explicitly. Export date,
source file and event label are not physical identifiers. Identical samples in
file-backed recordings are likewise deduplicated at the recovered physical
coordinate. Conflicting explicit sensing identities are refused. Matching,
event availability and PSD indexes share the canonical event iterator.

Future imports retain the index and reconcile PSDs independently of annotation
wall-time deduplication. Existing sources use `manage.py index_percept_clock
--participant-uid UID` for a dry run and `--apply` for an authorized, transactional
index/backfill. It authenticates eligible retained originals first, preserves
source hashes and existing recordings, and restores missing native event
representations and annotation links. Native event rows retain their original
hemisphere sets and metadata; the canonical analysis view deduplicates physical
observations across exports. The
native preimplant insertion guard is retained; acceptance must check for any
raw/recovered implant-boundary crossings before promotion.

Source indexes and clock implementation hashes participate in canonical input
identity, invalidating analysis and inner PSD caches. The analysis response
reports event clock recovery and duplicate/exclusion counts. Private acceptance
must reconcile original sources, retained records, recovered unique inputs,
matched ratings and rendered performance, with the same scientific controls.
