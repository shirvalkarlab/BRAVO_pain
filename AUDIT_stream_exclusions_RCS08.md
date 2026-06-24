# Data-stream exclusion audit — full-spectrum exploration (RCS08)

**Generated:** 2026-06-23 · **Participant:** RCS08 `2e3c75c00d7f4f37b53a048d195f11da`
**Question asked:** "Look through the entire database history of all the different streams.
Tell me upfront if anything is being excluded or not being used in the current full-spectrum
exploration — the same class of problem as the patient-event streams we caught last session."

**Method:** queried the live DB through the container bridge. Counted every `Recording.type`
for the participant, then traced each type through the scan's three ingestion gates
(`TIMEDOMAIN_TYPES`, `AVAILABILITY_PSD_TYPES`, `PATIENT_EVENT_TYPE` in `bravo_service.py`) and
the channel-name filter (`_MAIN_BIPOLAR`). For the non-ingested types I **decoded the actual
`.bdat`** to see whether they carry usable full-spectrum + channel + timestamp content, and
checked decoded `StartTime` coincidence to test for duplication.

---

## The complete inventory (4,702 recordings, 12 types)

| Type | n | Status | What happens to it |
|---|---:|---|---|
| PatientControllerEvent | 2160 | **scan** | 2,625 PSD rows enter scan (the fix we shipped last session) |
| MedtronicDeviceImpedance | 485 | n/a | hardware QC, no neural signal — correctly ignored |
| MedtronicChronicBrainSense | 431 | deploy | Timeline LSB; deployment-threshold anchor, not a scan stream (by design) |
| **TimeFrequencyAnalysis** | **321** | **🔴 OUT** | **consumed by NO biomarker path at all** |
| **NeuralActivitySnapshot** | **319** | **🟠 DUP** | duplicate re-export of the survey sweep; only on timeline as dedup'd markers |
| MedtronicBrainSenseTimeDomain | 224 | scan | 316 rows → scan (the 1 programmed bipolar pair) |
| MedtronicBrainSensePowerDomain | 221 | deploy | band-power-over-time; timeline lane only (by design) |
| **MedtronicBrainSenseSurvey** | **202** | **🟠 PARTIAL** | **6 of its 12 ring pairs silently dropped by the name filter** |
| MedtronicStimulationMontages | 114 | scan | bipolar-named channels pass → scan |
| MedtronicIndefiniteStream | 108 | scan | all 6 contacts, stim-off → scan |
| MedtronicBaselineMontages | 59 | scan | bipolar-named channels pass → scan |
| MedtronicElectrodeIdentifier | 58 | n/a | config metadata, no neural signal — correctly ignored |

**Current scan matrix:** 4,155 rows — 2,625 Patient event · 948 TD streaming · 582 Montage/survey
(span 2025-06-18 → 2026-06-22).

---

## Three findings, in priority order

### 🟠 Finding 1 — The channel-name filter is THE silent gate, and it is the same class of bug as the events one

`_MAIN_BIPOLAR` membership is tested by an **exact** string match (`str(n).upper() in _MAIN_BIPOLAR`).
The set holds `{ZERO_THREE_*, ONE_THREE_*, ZERO_TWO_*}`. But the **Survey / montage** products name
their channels in Medtronic's *ring* vocabulary — `ZERO_AND_THREE_LEFT_RING`, `ONE_AND_THREE_RIGHT_RING`,
etc. Those never match, so they are dropped before Welch.

Decoded proof (per recording, the 12 ring pairs):
```
raw:  ZERO_AND_ONE_*  ZERO_AND_TWO_*  ZERO_AND_THREE_*  ONE_AND_TWO_*  ONE_AND_THREE_*  TWO_AND_THREE_*  (×L/R)
```
The six "off-band" pairs (`ZERO_AND_ONE`, `ZERO_AND_TWO`→ZERO_TWO survives via a different spelling,
`ONE_AND_TWO`, `TWO_AND_THREE`) are dropped. **Crucially, the three pairs that DO eventually match only
do so because the Stimulation/Baseline montages happen to also export them under the *short* spelling
(`ONE_THREE_LEFT`).** The Survey product itself contributes **zero** rows under its native ring names —
its 202 recordings × 12 channels are filtered to nothing, and the pool is carried entirely by the other
two montage products.

This is exactly the events failure mode: a **naming-convention mismatch upstream of the scan silently
zeroes out a whole product**, and the pool looks "fine" only because a sibling product covers the same
contacts under a different spelling. It cost us the *breadth* the Survey was supposed to add — and it
means the two non-bipolar-but-useful pairs (`ZERO_AND_ONE`, `TWO_AND_THREE`) are **invisible to discovery
on every product**, even though they are legitimate sensing montages.

**Fix:** add a ring→bipolar canonicalizer at the filter (`ZERO_AND_THREE_LEFT_RING → ZERO_THREE_LEFT`,
strip `_AND_`/`_RING`). One function, applied in `_welch_rows_into` + `_psd_sample_index`. Decide
separately whether to widen `_MAIN_BIPOLAR` to admit `ZERO_AND_ONE` / `TWO_AND_THREE` (they are real
bipolar pairs, just not the closed-loop-sensing six).

### 🟠 Finding 2 — NeuralActivitySnapshot is a duplicate of the Survey sweep (do NOT naively add it)

Tempting to "rescue" the 319 NeuralActivitySnapshot records into the scan — but decoded `StartTime`
coincidence shows they are **the same physical montage sweeps**, re-exported under a second type label:

```
decoded-StartTime coincidence (±120 s):  TFA ↔ NAS = 320/321   NAS ↔ Survey = 225   TFA ↔ Survey = 226
```

(The earlier ORM-`date` "all 2026-06-22" was an ingest stamp — the handoff already flagged NAS `.date`
as a processing stamp ~11 days off. The decoded `StartTime` is the real recording time and spans
2025-07-16 → 2026-06-10, matching Survey.) So NeuralActivitySnapshot, Survey, and TimeFrequencyAnalysis
are **three labels on one ~21 s montage sweep**. Adding NAS to the scan after fixing Finding 1 would
**triple-count** every sweep. Correct action: fix the name filter once (Finding 1), keep deduplicating
by StartTime, and treat NAS purely as the timeline-marker source it already is.

### 🔴 Finding 3 — TimeFrequencyAnalysis (n=321) is consumed by literally no biomarker code path

`grep` across `modules/Biomarkers` + the frontend: **zero** references. It is created by the generic
`DataAnalysis.py` processing path (a Welch spectrogram re-export) and read only by an unrelated
Experimental "TherapeuticPrediction" view. For the biomarker module it is dead weight — and, like NAS,
it is the **same sweep** as Survey (320/321 coincident). So there is no missed signal here; the finding
is "321 records exist that the biomarker module neither uses nor needs to." Worth stating so it is not
later mistaken for an untapped stream.

---

## What is correctly excluded (not bugs)

- **Impedance (485) + ElectrodeIdentifier (58):** hardware/config, no neural signal.
- **ChronicBrainSense (431) + PowerDomain (221):** deployment/timeline streams. Per DESIGN §3, the
  deployed threshold anchors to Timeline LSB; these are band-locked and intentionally feed the timeline
  lanes and threshold step, not the full-spectrum discovery scan.

## Bottom line

One real bug of the events class: **the `_MAIN_BIPOLAR` exact-string filter silently drops the Survey
product's native ring-named channels** (and hides two legitimate bipolar pairs from discovery on every
product). The other two large "unused" streams (NeuralActivitySnapshot, TimeFrequencyAnalysis) are
**duplicate re-exports of the survey sweep** — correctly kept out of the pool; adding them would
double/triple-count. Recommended action is a single ring→bipolar canonicalizer plus an explicit decision
on whether the two extra pairs should join the discovery set.
