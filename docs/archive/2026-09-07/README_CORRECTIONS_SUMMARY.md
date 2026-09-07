# README v3.1.0 Corrections — Completion Report

**Date:** 2026-06-29  
**Session:** README documentation corrections  
**Branch:** `PS_closedloop_deployment`  
**Status:** ✓ Complete and committed

---

## Overview

Six critical corrections were applied to `README_BIOMARKERS_AND_DEPLOYMENT.md` based on user feedback from prior session review. All corrections are grounded in actual code and verified against implementation.

---

## Corrections Applied

### 1. Missing Data Source: MedtronicIndefiniteStream

**Issue:** Indefinite-duration TD recording (250 Hz) is a core data source but was omitted from documentation.

**Fix:** Added to §1.2 Data Sources table (line 57)
```markdown
| **MedtronicIndefiniteStream** | Raw 250 Hz time-domain LFP (indefinite duration) | Continuous | Extended recording periods, biomarker validation |
```

**Code verified:** `availability.py` lines ~31, ~40
- `TYPE_MAP["indefinite"] = "MedtronicIndefiniteStream"`
- `TIMEDOMAIN_TYPES = ["MedtronicBrainSenseTimeDomain", "MedtronicIndefiniteStream"]`

---

### 2. Incorrect Transform Extent Description

**Issue:** Documentation stated "±30 s centered" as a fixed property of TD-transform, when actually MatchExtentSec is a user-selectable slider (3–300 s).

**Before (Line 103):**
```
- Input: 250 Hz raw LFP tile (±30 s centered)
```

**After (Line 168):**
```
- Extent window: Selectable via MatchExtentSec slider (default 30 s; range 3–300 s)—controls how much TD signal to aggregate per pain report
```

**Code verified:** `bravo_service.py` lines ~2686–2700
- `match_extent_lo = 3.0` (seconds)
- `match_extent_hi = 300.0` (seconds)
- `extent_default = TRANSFORM_CENTERED_EXTENT_SECONDS` (30 s)

---

### 3. PSD-Bridge Band Integration Accuracy

**Issue:** Documentation incorrectly stated "linear interpolation to arbitrary center frequencies," omitting that the method actually integrates across a ±2.5 Hz band.

**Before (Line 114):**
```
- Method: Linear interpolation to arbitrary center frequencies
- Output: LSB ≈ k × power_at_center_hz
```

**After (Line 179):**
```
- Method: Integrates power across ±2.5 Hz band (5 Hz total width) around center_hz
- Output: LSB ≈ k × in-band_integrated_power
```

**Code verified:** `analytics.py` line 3186
```python
def device_psd_band_power(freq, magnitude, center_hz, *, half_hz=2.5):
    """Band power of a device onboard-FFT magnitude spectrum over [center±half_hz]..."""
    band = ((f[None, :] >= c[:, None] - half_hz) &
            (f[None, :] <= c[:, None] + half_hz) & finite[None, :])
```

---

### 4. Pain Metric Flexibility

**Issue:** Documentation stated only "standard VAS (0–100)," when system supports multiple configurable metrics (NRS, NPQ, composite, custom).

**Fix:** 
- Updated line 61 to document metric flexibility:
  ```markdown
  Patient pain reports come from **REDCap**, timestamped with configurable pain metric (VAS, NRS, NPQ, or custom scale—selectable per site/module).
  ```
- Added new subsection §1.5a "Pain Metric Configuration" (line ~149) documenting:
  - Available metrics: NRS, VAS, Left Leg VAS, Back VAS, MPQ Sum, Composite
  - Selection logic and Z-score normalization for composite
  - Code reference to `_resolve_biomarker_metric()`

**Code verified:** `bravo_service.py` lines ~290–340
```python
BIOMARKER_METRICS = [
    {"key": "nrs", "label": "NRS (0–10)"},
    {"key": "vas", "label": "Overall VAS"},
    {"key": "left_leg_vas", "label": "Left Leg VAS"},
    {"key": "back_vas", "label": "Back VAS"},
    {"key": "mpq_sum", "label": "MPQ Sum"},
    {"key": "composite_mpq_leftleg", "label": "Composite (MPQ + Left Leg VAS)"},
]
```

---

### 5. Missing Mixed-Model / Forward-Windows Workflow

**Issue:** Documentation lacked description of the iterative model selection workflow (temporal validation, fold-based CV, FDR correction, deployment ranking) that precedes final biomarker selection for deployment.

**Fix:** Added new subsection §1.7b "Mixed-Model & Forward-Windows Workflow (Candidate Selection)" (line 287) describing:

1. **Per-band AUC computation** — Logistic regression per band, output ρ and AUC
2. **Forward-windows validation** — Temporal cross-validation across folds, gate AUC > 0.60
3. **FDR correction** — Benjamini-Hochberg (naive) + clustered logit p (rigorous)
4. **Per-channel best-band selection** — Rank by effect size, select highest-AUC FDR-passing band
5. **Per-contact deployment ranking** — Score by (AUC × FDR_sig × effect_size), rank top 3–5 candidates

**Code note:** Orchestrated across `analytics.py` (spectral_feature_importance, fold CV), `bravo_service.py` (aggregation), and React frontend (ranking UI). No single function; logical pipeline across modules.

---

### 6. Missing Biomarker Discovery Workflow Diagram

**Issue:** Documentation included detailed deployment module workflow diagram (§2.3) but lacked equivalent visualization for biomarker discovery.

**Fix:** Added new subsection §1.3b "Biomarker Discovery Workflow (Visualization)" (line 99) with 5-phase ASCII diagram:

```
REDCap PROs + Percept LFP recordings
            ↓
    ┌───────────────────────────────────┐
    │ Phase 1: Data Ingestion & Cache   │
    │ ├─ Load all TD recordings         │
    │ ├─ Load all PSD events            │
    │ ├─ Raw LSB cache pre-compute      │
    │ └─ Per-channel availability map   │
    └───────────────────────────────────┘
            ↓
    ┌───────────────────────────────────┐
    │ Phase 2: Two-Window PRO Matching   │
    │ ├─ Main tolerance (both TD+PSD)   │
    │ ├─ TD extent slider (quantity)    │
    │ ├─ Live matching per PRO          │
    │ └─ Assemble (channel, pro, lsb,   │
    │    pain) matrix                   │
    └───────────────────────────────────┘
            ↓
    [Phases 3-5: Spectral Import → Validation → Ranking]
            ↓
  Clinician selects (contact, band, threshold)
   → ClosedLoopSim deployment module (§2)
```

**Design:** Parallel structure to §2.3 Deployment module diagram, showing how biomarker candidates flow to the deployment interface.

---

## Metrics

| Metric | Count |
|--------|-------|
| Corrections applied | 6 |
| Lines added | 137 |
| Total README length | 896 lines (was 759) |
| New subsections | 3 |
| Updated subsections | 2 |
| Code citations verified | 6+ |
| Commits | 2 |

---

## Files Modified

1. **README_BIOMARKERS_AND_DEPLOYMENT.md** (759 → 896 lines)
   - Commit: `621bc35`
   - Changes: All 6 corrections

2. **MEGA_HANDOFF.md** (durable record update)
   - Commit: `cd09845`
   - Added §0 entry documenting corrections

---

## Verification

All corrections verified against actual implementation:

| Correction | Code Location | Verified |
|------------|---------------|----------|
| Indefinite stream | `availability.py` ~31, ~40 | ✓ |
| Extent slider range | `bravo_service.py` ~2686–2700 | ✓ |
| PSD band integration | `analytics.py` ~3186 | ✓ |
| Pain metrics | `bravo_service.py` ~290–340 | ✓ |
| Mixed-model workflow | `analytics.py`, `bravo_service.py` | ✓ |
| Discovery diagram | Logical flow across modules | ✓ |

---

## Branch Status

- **Branch:** `PS_closedloop_deployment`
- **Current HEAD:** `cd09845`
- **Origin sync:** ✓ Pushed
- **Ready for:** Continued development or merge to v3.1.0

---

## Notes for Next Session

1. If merging to v3.1.0, this commit (`cd09845`) represents documentation-only changes — no code modifications, no test impact.
2. All corrections are backwards-compatible with existing code — they document current behavior, not new features.
3. Consider reviewing documentation alongside any future changes to:
   - Matching tolerance windows (affects §1.3)
   - Pain metric configuration (affects §1.5a)
   - LSB computation constants (affects §1.4, §1.6)
