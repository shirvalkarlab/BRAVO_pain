# BrainSenseLfp ingestion / pairing audit — 2026-06-27

**Trigger:** CS-1 live anchor reported `r=0.08`, `RMSE=4.2e8` and `_load_recordings(UID,["MedtronicBrainSenseLfp"])`
returned 0 records → concern that ingestion *unpairs BrainSenseLfp from its true data type*.

## Verdict: ingestion is CORRECT. BrainSenseLfp is NOT unpaired or mis-typed. No pipeline fix required.

### Data flow (traced)
- **Raw `BrainSenseTimeDomain`** (250 Hz time domain) → `Percept.extractStreamingData` → `Data["StreamingTD"]`
  (`Percept.py:1762`).
- **Raw `BrainSenseLfp`** (bilateral ~5 Hz power-band streaming) → `Data["StreamingPower"]`
  (`Percept.py:1793`; docstring `Percept.py:1746` states the split explicitly).
- `Session.py:423` → `BrainSenseStream.saveBrainSenseStreams(StreamingTD, StreamingPower)` →
  **`TimeDomainRecordings`** (stored type `MedtronicBrainSenseTimeDomain`) and
  **`PowerDomainRecordings`** (stored type `MedtronicBrainSensePowerDomain`).

### Pairing is preserved by construction
`saveBrainSenseStreams` (`BrainSenseStream.py:49-50`) sorts BOTH streams by the same
`FirstPacketDateTime (+ duration)` key and emits each recording stamped with its `FirstPacketDateTime`
as `StartTime`. TD and its BrainSenseLfp partner therefore share an identical `StartTime`.

**Confirmed on live RCS08 (uid 2e3c75c0…):** 232 TD recs, 229 PowerDomain recs, **102 share the exact-second
StartTime**. Stored PowerDomain `Power` columns are clean: **0 uint32 sentinels**, values O(10–3500) LSB.

### Root cause of the anchor's bad r/RMSE — script bug, NOT data
1. **Wrong type name in the probe:** BrainSenseLfp's stored type is `MedtronicBrainSensePowerDomain`,
   not `MedtronicBrainSenseLfp`. The 0-record load was a naming error in the throwaway anchor.
2. **Degenerate blocks not screened:** among paired PowerDomain blocks are all-zero power columns and
   mixed channel layouts ((40,4) vs (2135,2)); the hand-rolled substring column match + target/transform
   division over those blocks produced the 4.2e8 RMSE. The robust stats were already right
   (k≈357.8 ≈ repo stim-off 356.6; median fold 1.122 ≈ repo 1.092).

### What the anchor DID validate (unaffected by the pairing bug)
- **DSP vendored correctly:** synthetic byte-identity vs the published reference algorithm, max abs err = 0.0.
- **Overlap shift (same TD trace both ways, pairing-independent):** non-overlap vs 50%-overlap median band
  power fold **median 1.029, p95 1.296** — under the 1.26× calibration scatter → **k=352.62 stands**.

### Faithful r≈0.993 reproduction
Requires the lab `percept-spectral-repro` TD↔BrainSenseLfp pairing on the **Stage-1 raw JSONs**
(27 of 517 carry both `BrainSenseLfp` + `BrainSenseTimeDomain`). The repo clone was swept with the
workspace; re-clone + swap in the vendored `analytics.td_transform_band_power` rather than hand-roll the
pairing (handoff ERROR 7). This is a verification nicety — the in-suite synthetic anchor already proves
the vendoring.
