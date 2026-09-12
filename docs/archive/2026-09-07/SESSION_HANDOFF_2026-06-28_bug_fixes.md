# Session Handoff — 2026-06-28 (Biomarker Exploration Timeline Bug Fixes)

## State at session end
- Branch: `PS_closedloop_deployment`
- HEAD: `e8a0d3f` (unchanged — no agent commits per policy)
- Uncommitted: `bravo_service.py`, `test_availability.py`, `BiomarkerDataTimeline.js`, `MEGA_HANDOFF.md`, this file
- Suite: **249/249 PASS** (in-container runner via `_agent_bridge/run_tests.py`)
- Bug 3/4: investigation sub-agent running at session end — see §Bug 3/4 below

---

## Bug 1 — Event-PSD channel resolver (COMPLETE)

### Root cause
`_event_block_channel` used a static per-hemisphere guess (`Right→ZERO_THREE`, `Left→ONE_THREE`)
when `SenseID` was absent. On RCS008, **84% of 3,119 event PSD blocks lack SenseID** and 86% are
Right-hemisphere → ~86% of all event PSDs were silently dumped onto R 0-3.

This affected:
1. **Timeline ticks** — all events appeared in the R 0-3 lane
2. **Binarization scan pool** — R 0-3's pool was contaminated with misrouted events; other channels
   starved. This is a biomarker-accuracy issue.

### Architecture decision
Channel assignment stays at **analysis time**, not ingestion. `BrainSenseEvent.saveBrainSenseEvents`
stores the raw per-hemisphere FFT dict verbatim (with `SenseID`, `Frequency`, `FFTBinData`). The
resolver runs when `bravo_service` reads it back. New JSONs automatically benefit; richer TD records
accumulate over time and improve index coverage for older events too.

### New functions (bravo_service.py)
- `_build_sensing_config_index(decoded_recs)` — per-hemisphere `[(epoch_s, channel)]` sorted list
  from single-channel decoded recording dicts. Guard: `len(chans)==1` per hemisphere — excludes
  IndefiniteStream and montage sweeps (all-pair sensors) automatically. Accepts TD + PowerDomain.
- `_build_sensing_config_index_from_rows(psd_rows)` — companion for the cached-assembly path
  (flat Welch rows, `source == "TD streaming"` only; excludes Montage/survey rows).
- `_resolve_event_channel(hemi_key, sense_id, t_event, sensing_index)` — priority:
  1. SenseID (authoritative device record)
  2. Most-recent prior config in 90-day window (`_SENSING_WINDOW_S = 90 * 86400`)
  3. Nearest-after config in window (covers events before first session)
  4. `None` — skip, never guess

### Removed
- `_EVENT_HEMI_DEFAULT_CONTACT` dict fully removed from all production paths
- `_event_block_channel` reduced to a SenseID-only shim (backward compat only)

### Call sites wired
| Call site | File | Sensing index source |
|---|---|---|
| Availability timeline ticks (`_event_psd_index`) | bravo_service.py ~2399 | `td_list + powerdomain_list` |
| Availability scan pool (`_event_psd_index`) | bravo_service.py ~2522 | same `_sensing_idx` |
| Availability LSB bridge (`_event_psd_lsb_blocks`) | bravo_service.py ~2436 | same `_sensing_idx` |
| `_assemble_psd_rows` (direct decode path) | bravo_service.py ~919 | `td_list` only |
| `_assemble_psd_rows_cached` (cached path) | bravo_service.py ~1320 | `_build_sensing_config_index_from_rows(rows)` |
| Warm PSD cache path | bravo_service.py ~1508 | `td_list` only |
| Deployment scan path | bravo_service.py ~2750 | `td` only |

**Note on source selection:** `td_list` (streaming TD) is used for sites where PowerDomain isn't
in scope. At the availability payload site, `powerdomain_list` is available and included.
Montage/survey (`psd_list`) is explicitly excluded everywhere — those are all-pair sweeps.

### Live RCS008 validation
| Metric | Before | After |
|---|---|---|
| Blocks routed | 484/3119 (16%) | 3119/3119 (100%) |
| R 0-3 | 445 | 2696 |
| L 1-3 | 34 | 407 |
| L 0-3 | 4 | 15 |
| Unresolved (skipped) | 2635 | 0 |
| Bilateral events | — | 421 (both L+R resolved independently) |

Dominant bilateral pair: R=ZERO_THREE_RIGHT + L=ONE_THREE_LEFT (407 events).

### Regression tests added (test_availability.py, +9)
- `test_resolver_returns_none_when_no_sense_id_and_no_index`
- `test_resolver_uses_sense_id_when_present`
- `test_resolver_picks_nearest_prior_config_from_index`
- `test_resolver_falls_back_to_nearest_after_when_no_prior`
- `test_resolver_respects_window_and_returns_none_when_too_far`
- `test_resolver_excludes_all_pair_sweeps_from_index`
- `test_resolver_left_hemi_key`
- `test_build_sensing_config_index_accepts_power_domain_records`
- `test_build_sensing_config_index_from_rows_basic`

---

## Bug 2 — Modeled-LSB symbol fix (COMPLETE)

### Root cause
`BiomarkerDataTimeline.js` lane-level modeled tier used `symbol: "diamond-open"` for ALL methods
regardless of DSP route. The per-rating tier already used `TIER_SYMBOL = {td_transform: "circle-open",
psd_bridge: "diamond-open"}` correctly, but the two layers shared `diamond-open` for psd_bridge
making per-rating PSD-bridge points visually identical to lane-level points. TD-modeled per-rating
points were invisible behind PSD-bridge diamonds.

### Fix (BiomarkerDataTimeline.js)
1. **Lane-level modeled tier**: within each frequency group, partition `ms` into `ms_td`
   (method startsWith `"td_transform"`) and `ms_psd` (startsWith `"event_psd_bridge"`); push two
   traces — `circle-open` for TD, `diamond-open` for PSD-bridge.
2. **Non-binMode legend**: single `diamond-open` entry split into two:
   - `circle-open` → `"modeled LSB  (○ TD-transform ×352.62 — hollow circle)"`
   - `diamond-open` → `"modeled LSB  (◇ PSD→LSB bridge ×73.63 — hollow diamond)"`
3. **Per-rating legend names** (both binMode and non-binMode): added `"same symbols: "` prefix to
   clarify the per-rating layer uses the identical glyph convention.
4. **Removed** redundant `matched ≥1 PSD` / `no neural match` pain-rating swatches from binMode
   glyph key (per user note: binarization mode already communicates matched/unmatched via color).
5. **`nLegRows`**: binMode `7→5`, non-binMode `8→9`.

---

## Bug 3 — Rating-count mismatch (REAL BUG FOUND AND FIXED)

Sub-agent `bug3_bug4_investigation.md` identified three root causes:

**3a (REAL BUG, FIXED) — stale `proIdxByBin` in BinarizationPreview.js:**
`scanModel` was missing from the `useEffect` dep array (line 346). `proIdxByBin` is computed inside
that effect from `scanModel.samples`, but stale renders persisted whenever `scanModel` rebuilt
(e.g. `matchDirection` change) without any other listed dep changing. The 187/106 discrepancy was
this stale render — the Set-computed unique-rating count was from the previous model. Fix: added
`scanModel` to the dep array.

**3b — proIdxByBin can exceed survey_usage.n_pro_used at bin boundaries (by design, no fix):**
A rating at exactly a cut boundary can have its matched PSDs on different channels split between
bins, appearing in two bins' Sets. So `sum(proIdxByBin)` may exceed `nProUsed`. This is
mathematically correct behavior — the badge labels already distinguish "pain ratings" vs "PSDs".

**3c — semantic gap in labels (by design, no fix needed):**
`proIdxByBin.low` = unique rating indices in the low bin (rating-centric); `counts.n_low` = total
matched PSD rows (neural-sample-centric). In `pro_first` mode with maxPerRating=3 and 3 active
channels, one rating → up to 9 PSD rows, so n_low can be ≫ proIdxByBin.low. Both are correct for
what they measure; labels already say "pain ratings" vs "PSDs".

### Fix applied
`BinarizationPreview.js` line 346: added `scanModel` to useEffect dep array.

---

## Bug 4 — LSB point-count parity scatter vs pool (FIXED — 3 root causes)

Sub-agent identified 4 root causes; fixes applied for 3:

**4a (architectural — no fix needed):** Scatter filters per `(channel × band)` using
`isfinite(bp_log) & label_fin` → count ≤ n_channel. Pool is ALL matched PSDs across all channels.
These are genuinely different quantities; binarization pool ≠ per-channel scatter count by design.

**4b (FIXED) — scatter subsampled but title shows capped count:**
`max_scatter=400` cap in analytics.py subsample the scatter dots, but `nShown = sc.x.length`
reported the subsampled count. Fix: title now shows `ch.n_channel` (true per-channel matched count)
with ` shown: N` suffix only when scatter was actually subsampled (`nShown < ch.n_channel`).

**4c (FIXED) — no stale-window flag in scatter title:**
Scatter is built at scan-time match window; client preview updates live with slider. When
`matchDirty` (slider changed since last scan), scatter title now shows `· scan at prior window`.
`matchDirty` prop threaded: `index.js → BiomarkerAnalytics → SpectralFeatureImportance`.

**4d (resolved by Bug 1 fix):** Event PSDs without SenseID were dropped from both client pool and
backend pool symmetrically (both called without sensing_index). After Bug 1 fix, both paths now
receive a sensing_index → symmetric resolution, parity maintained.

**Prior sub-agent fix (4 - scatter/violin parity):**
`nShown = nlo + nhi + nmid` (from `sc.n_grp`) instead of `sc.x.length`. Violin caption now leads
with `n=${nShown}:`. Both panels locked to same server-side source.

---

## Bug 4 addendum — scatter title null-guard fix (BiomarkerAnalytics.js)

**Issue found post-merge:** The cap-disclosure expression `nShown < (ch.n_channel || nShown)`
evaluates to `false` when `ch.n_channel` is null (fallback makes it `nShown < nShown`), so the
` shown: N` suffix never appeared when the server omitted `n_channel`.

**Fix:** Changed to `(ch.n_channel != null && nShown < ch.n_channel)` — the suffix only renders
when `ch.n_channel` is definitively present and the scatter was subsampled below it.

File: `Client/src/views/Reports/Biomarkers/BiomarkerAnalytics.js`
Frontend rebuilt after this fix (`npm run build` — confirmed "The build folder is ready").

---

## Gotchas for next agent
1. **No agent commits** — all changes uncommitted per policy; user lands them.
2. **Bridge** runs at `BRAVO/_agent_bridge/bridge_client.py`, Django in container at `/usr/src/BRAVO`.
3. **RCS008 uid**: `2e3c75c00d7f4f37b53a048d195f11da` (stale: `1eda36458758461383721208bbe6bb87`).
4. **Suite runner**: `python3 _agent_bridge/run_tests.py` (via bridge); no pytest in container.
5. **Sensing index source rule**: always `td_list` (streaming TD) or `td_list + powerdomain_list`;
   never include `psd_list` (montage sweeps — all-pair sensors, filtered anyway but misleading).
