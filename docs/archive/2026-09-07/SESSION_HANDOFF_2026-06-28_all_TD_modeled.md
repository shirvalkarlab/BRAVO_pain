# Session handoff — deployment modeled-LSB now pools ALL TD products (2026-06-28)

**Branch:** `PS_closedloop_deployment` (off `e8a0d3f`). **Suite 240/240 PASS** (was 239; +1 new test).
**Not committed** (per PI: no agent commits/PRs) — review-ready changeset for the human to land.

## What this session did
Closed the open item "wire the TD sources into the deployment modeled tier" — corrected to the PI's
actual intent: **deployment modeled LSB must pool EVERY raw-µV TD product, not only montage/survey TD.**

### The gap (pre-existing, since the 2026-06-28 `09798f7` TIER-1 rewrite)
The Biomarker **exploration timeline** feeds the modeled-LSB helper the full TD superset —
streaming TD (`MedtronicBrainSenseTimeDomain` + `MedtronicIndefiniteStream`, `td_list`) **plus**
montage/survey TD (`psd_list`) — at bravo_service.py:2310/2323. But the two **deployment endpoints**
(`band_lsb_and_power`, `deployment_summary`) only loaded `psd_list` (montage/survey) and passed
`td_recordings=list(psd_list or [])` to `availability.modeled_lsb_at_center`. Any band the device only
ever **streamed** (never montage-swept) silently lost those TD samples from the deployable
percentile-anchored threshold pool. `modeled_lsb_at_center` was already generic (its docstring even said
"pass BrainSense streaming TD too if/when a caller loads it") — the callers just never loaded it.

### The fix (deployment-only; exploration timeline untouched)
Both endpoints now also load `streaming_td = _load_recordings(uid, TIMEDOMAIN_TYPES)` and pass
`td_for_modeled = list(streaming_td or []) + list(psd_list or [])` to the helper. Power-domain records
(chronic/powerdomain, `fs<=0`) and unnamed/foreign columns are still excluded by the helper's existing
fs/ChannelName guards — no cross-channel or units leak. The native-preferred precedence is unchanged
(modeled used only when no native threshold exists). Helper docstring updated; both stale
"`psd_list` is the montage/survey TD" comments corrected to "`td_for_modeled` is ALL raw-µV TD".

### E2E verification on real RCS08 (ZERO_THREE_RIGHT, via the actual helper through the bridge)
335 streaming TD recs = **232 BrainSenseTimeDomain + 103 IndefiniteStream** (the IndefiniteStream
records each carry ALL 6 contacts) + 395 montage/survey recs. In-band modeled pool roughly **tripled**
and the deployable p50 shifted a few %:

| center | montage-only n / p50 | ALL-TD n / p50 |
|---|---|---|
| 8.8  | 156 / 496.3 | 469 / 515.1 |
| 20.0 | 156 / 175.5 | 469 / 178.1 |
| 26.4 | 156 / 102.5 | 469 / 105.4 |
| 55.5 | 156 / 26.7  | 469 / 26.8  |

ZERO_THREE_RIGHT@20 Hz streaming split: +211 BrainSenseTimeDomain +102 IndefiniteStream = 313 added
(156→469). **IndefiniteStream is the dominant streaming source**: because each IndefiniteStream record
carries all 6 contacts, it adds a uniform **+102 points to EVERY channel**, whereas BrainSenseTimeDomain
is sparse off 0-3R (per-channel bstd @20 Hz: 0-3R 211, 0-3L 44, 1-3L 39, 0-2L 8, 0-2R 3, 1-3R 1). For
the 0-2 / 1-3 contacts the early IndefiniteStreaming sessions are essentially the ONLY streaming TD —
exactly the data that was being dropped before this fix.

The streamed-only contribution is real (n 156→469) and moves the patient-facing modeled threshold,
confirming this was a genuine data-coverage gap, not a no-op. (Correction to an earlier draft of this
doc: this participant has **103 IndefiniteStream** recordings, not 0 — an earlier probe mislabeled them
because the decoded payload drops the source-type marker; the loader pulls them via TIMEDOMAIN_TYPES.)

## Tests
+1 net: `test_modeled_lsb_at_center_pools_streaming_and_montage_td` (two same-channel TD records at
distinct times -> 2 pooled points; montage-only -> 1; union contains the montage point). Existing 8
helper-branch tests already cover guard behavior (foreign-channel, power-domain skip, malformed columns,
orientation, short-column, fail-closed, PSD band-gate, high-gamma no-snap). **240/240 via
`python3 _agent_bridge/run_tests.py`.**

## Files changed (uncommitted)
- `BRAVO/modules/Biomarkers/bravo_service.py` — both deployment endpoints load streaming TD and pass
  the combined `td_for_modeled` superset; stale comments corrected.
- `BRAVO/modules/Biomarkers/routines/availability.py` — `modeled_lsb_at_center` docstring (td_recordings
  is now the full streaming + montage superset).
- `BRAVO/modules/Biomarkers/tests/test_availability.py` — +1 multi-source pooling regression test.

## Open / next
- No frontend change (modeled threshold value flows through existing payload keys; only its numeric
  value moved). A rebuild is NOT required for this change.
- The PSD-only bridge tier (`psd_recordings=`) is still passed `None` by both endpoints — montage+streaming
  TD covers RCS08. Wire PSD events in only if a participant has PSD-only bands with no TD at all.
