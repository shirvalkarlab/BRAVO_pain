# BRAVO Biomarker & Closed-Loop Deployment Module

**Version:** v3.1.0  
**Last Updated:** 2026-06-29

---

## Overview

This document describes the **Biomarker** identification pipeline and the **ClosedLoopSim** (Deployment) module—the end-to-end workflow for validating brain biomarkers of chronic pain and deploying them in closed-loop DBS via the Medtronic Percept RC.

### Architecture at a Glance

```
REDCap PROs + Percept LFP data (Django backend)
            ↓
   bravo_service.py (DRF API endpoint)
            ↓
   ┌─────────────────────────────────────┐
   │ Biomarker Module (BRAVO_pain/)      │
   │ ├─ Raw data ingestion               │
   │ ├─ LSB caching & matching (2-window)│
   │ ├─ Spectral analytics               │
   │ ├─ Binarization & validation        │
   │ └─ Per-channel scoring              │
   └─────────────────────────────────────┘
            ↓
   JSON response + React visualization
            ↓
   ┌─────────────────────────────────────┐
   │ Deployment Module (ClosedLoopSim)   │
   │ ├─ Band candidate selection         │
   │ ├─ ROC & performance panel          │
   │ ├─ Deployment verdicts              │
   │ └─ Closed-loop sign-off card        │
   └─────────────────────────────────────┘
            ↓
   Clinician selects (contact, freq, threshold)
   → Programs Percept RC for closed-loop therapy
```

---

## 1. Biomarker Module (`BRAVO/modules/Biomarkers/`)

### 1.1 Purpose

Identify the brain location (contact × frequency band) whose Local Field Potential (LFP) power best tracks pain, quantify statistical confidence, and provide a deployable threshold for real-time detection.

### 1.2 Data Sources

The biomarker module ingests multiple Percept recording types:

| Recording Type | Data | Sampling | Use Case |
|---|---|---|---|
| **BrainSenseStream** | Raw 250 Hz time-domain LFP | Continuous | Spectral correlation (streaming_psd.py) |
| **MedtronicIndefiniteStream** | Raw 250 Hz time-domain LFP (indefinite duration) | Continuous | Extended recording periods, biomarker validation |
| **ChronicBrainSense** | 10-min aggregated power trends (6 Hz – 100 Hz) | ~10 min intervals | Threshold-based detection (threshold_biomarker.py) |
| **Montage/Survey PSD** | 100-point power spectra (device snapshots or clinical montages) | Discrete snapshots | LSB bridge calibration (device_psd_band_power) |

Patient pain reports come from **REDCap**, timestamped with configurable pain metric (NRS, VAS, region-specific VAS, MPQ, or composite—selectable per site/module).

### 1.3 Two-Window Matching Logic (Critical)

**The Challenge:**  
Pain reports must be matched to neural data in time. The original pipeline used two unrelated time windows (±30 s for TD, ±120 s for PSD), causing UI/computation mismatch.

**Solution (v3.1.0):**  
- **Main slider (MatchToleranceMin):** Eligibility window for BOTH modalities (e.g., ±2 h default → 120 min)
- **Extent slider (MatchExtentSec):** TD-only quantity controller (how many of the nearest 3-s epochs to use per pain report; rounds to `nearest round(extent_s / 3)` tiles)
- **PSD:** Always medians ALL eligible events within the main tolerance window (no quantity cap)

**Pseudocode:**
```python
def live_lsb_spectrum_match(pro_t, tol_s, td_quantity_s):
    """
    tol_s: main tolerance in seconds (gates both TD and PSD)
    td_quantity_s: TD signal quantity (nearest how many seconds of signal)
    """
    # TD branch
    td_eligible = [tile for tile in all_td_tiles if |tile.t - pro_t| <= tol_s]
    n_td_cap = max(1, round(td_quantity_s / 3))  # nearest N tiles
    td_used = sorted(td_eligible, key=|t - pro_t|)[:n_td_cap]  # nearest-first
    td_lsb = median(td_used)
    
    # PSD branch
    psd_eligible = [event for event in all_psd_events if |event.t - pro_t| <= tol_s]
    psd_lsb = median(psd_eligible)  # no cap
    
    return {tier: 'td_transform' if td_lsb else 'psd_bridge',
            lsb: td_lsb or psd_lsb}
```

**Live matching call site:** `bravo_service.py` ~2970  
**Implementation:** `availability.py` `live_lsb_spectrum_match()` ~1321

---

### 1.3b Biomarker Discovery Workflow (Visualization)

The biomarker identification pipeline flows from raw data through validation to deployment candidates:

```
REDCap PROs + Percept LFP recordings
            ↓
    ┌───────────────────────────────────┐
    │ Phase 1: Data Ingestion & Cache   │
    │ ├─ Load all TD recordings         │
    │ ├─ Load all PSD events (device+   │
    │ │  survey+montage)                │
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
    ┌───────────────────────────────────┐
    │ Phase 3: Spectral Feature Import. │
    │ ├─ Per band (2.5–99.5 Hz, 1 Hz    │
    │ │  steps)                          │
    │ ├─ Pearson ρ vs pain rating       │
    │ ├─ Logistic AUC + p-value         │
    │ ├─ Fold-based validation (temp.   │
    │ │  CV)                            │
    │ └─ Output: (band, ρ, AUC, p)      │
    │   per channel                     │
    └───────────────────────────────────┘
            ↓
    ┌───────────────────────────────────┐
    │ Phase 4: Statistical Validation    │
    │ ├─ FDR correction (naive +        │
    │ │  rigorous)                       │
    │ ├─ Per-channel best-band select   │
    │ ├─ Binarization (tertiles, per    │
    │ │  PRO)                           │
    │ └─ Per-channel confidence badge   │
    │   (FDR sig, direction)            │
    └───────────────────────────────────┘
            ↓
    ┌───────────────────────────────────┐
    │ Phase 5: Deployment Ranking        │
    │ ├─ Score contacts by (AUC ×       │
    │ │  FDR_sig × effect_size)         │
    │ ├─ Rank top 3–5 candidates        │
    │ └─ Present to clinician           │
    └───────────────────────────────────┘
            ↓
  Clinician selects (contact, band, threshold)
   → ClosedLoopSim deployment module (§2)
   → Program Percept RC for closed-loop therapy
```

---

### 1.4 LSB Computation

**LSB (Log Spectral Basis):** Normalized power in log scale, calibrated to pain-responsive frequency ranges.

#### TD-Transform (k=352.62)
- Input: 250 Hz raw LFP signal around PRO timestamp
- Extent window: Selectable via MatchExtentSec slider (default 30 s; range 3–300 s)—controls how much TD signal to aggregate per pain report
- Method: Hann-windowed 50% overlapping FFT (n_fft=256, step=0.5 s)
- Detrend: Per-window mean removal
- Aggregate: Median across windows
- Calibration band: 7.8–30 Hz (LSB_VALIDATED_HZ_LO to LSB_DEPLOYABLE_HZ_HI)
- Output: LSB = k × median(windowed_power_db)

**File:** `availability.py` `td_transform_band_power()` ~2886

#### PSD-Bridge (k≈73.63)
- Input: Device or survey PSD snapshot (100-point log-spaced 1–100 Hz)
- Method: Integrates power across ±2.5 Hz band (5 Hz total width) around center_hz
- Saturation gate: Skip if peak >4000 µV (PRO_LSB_SATURATION_UV)
- Output: LSB ≈ k × in-band_integrated_power

**File:** `analytics.py` `device_psd_band_power()` ~3186

---

### 1.5 Cache & Real-Time Matching

**Raw Cache (`raw_lsb_spectrum_cache`):**  
Pre-computed 3-second TD tiles + PSD events, memoized per patient. Enables fast matching without re-computing FFTs on every slider movement.

```python
def raw_lsb_spectrum_cache(participant_id, extent_s=30.0, window_s=3.0):
    """
    extent_s: surrounding window for TD (default TRANSFORM_CENTERED_EXTENT_SECONDS=30.0)
    window_s: tile size for raw cache (default RAW_LSB_WINDOW_SECONDS=3.0)
    
    Returns: {
        channel: [...],
        centers_hz: [2.5, 3.5, ..., 99.5],  # _LSB_SPECTRUM_CENTERS
        band_half_hz: 2.5,
        td: {t, lsb[n_windows×n_channels], saturated, source},
        psd: {t, lsb[n_channels], calibrated, source},
        n_td_windows, n_psd_windows
    }
    """
```

**File:** `availability.py` `raw_lsb_spectrum_cache()` ~1156

---

### 1.5a Pain Metric Configuration (v3.1.0)

The biomarker module supports **multiple pain scales**, configurable per site or patient cohort:

**Available metrics:**
- **NRS** (Numeric Rating Scale, 0–10)
- **VAS** (Visual Analog Scale, 0–100)
- **Left Leg VAS** (region-specific VAS)
- **Back VAS** (region-specific VAS)
- **MPQ Sum** (McGill Pain Questionnaire total)
- **Composite (MPQ + Left Leg VAS)** — Z-score normalized blend

**Selection logic:**
```python
# In bravo_service.py::_resolve_biomarker_metric()
metric = request_data.get("LabelMetric") or DEFAULT_BIOMARKER_METRIC  # default: "nrs"

if metric == COMPOSITE_METRIC:
    # Z-score each part, average available parts per row
    # Improves coverage (either part → day included) and balance vs. min-max blend
else:
    # Use single metric directly
```

**File:** `bravo_service.py` `_resolve_biomarker_metric()` ~290

---

### 1.6 Key Constants

```python
# Scaling factors
LSB_PER_UV2_TRANSFORM = 352.62       # TD-transform scale (analytics.py:2829)
LSB_PER_DEVICE_PSD = 73.63           # Device PSD scale (analytics.py:2830)

# Frequency validation
LSB_VALIDATED_HZ_LO = 7.8            # Lowest validated freq (availability.py:2789)
LSB_VALIDATED_HZ_HI = 28.3           # Highest validated freq (availability.py:2790)
LSB_DEPLOYABLE_HZ_HI = 30.0          # Deployment ceiling (availability.py:2819)

# Windowing
TRANSFORM_WIN_SECONDS = 1.0          # Hann window duration (analytics.py)
TRANSFORM_STEP_SECONDS = 0.5         # FFT hop size (analytics.py)
TRANSFORM_CENTERED_EXTENT_SECONDS = 30.0  # ±TD extent (analytics.py)
RAW_LSB_WINDOW_SECONDS = 3.0         # Raw cache tile size (availability.py)

# Spectra
TRANSFORM_N_FFT = 256                # FFT size
fmax = 100.0                         # Max analysis frequency
band_width_hz = 5.0                  # Spectral feature width
n_peaks = 6                          # Peaks for feature importance

# Thresholds
PRO_LSB_SATURATION_UV = 4000.0       # Max acceptable peak (availability.py:843)
max_missing_frac = 0.10              # Allow 10% missing samples
```

---

### 1.7 Spectral Feature Importance (Biomarker Discovery)

**Goal:** For each contact, find the best `(center_hz, bandwidth)` that tracks pain.

**Method:** 
1. Build LSB matrix: shape `(n_ratings, n_channels, n_freq_bands)`
2. Per band, per channel: compute Pearson ρ vs pain, compute AUC via logistic regression
3. Fold AUC: `max(auc, 1 - auc)` so suppression (neg ρ, low AUC) reads as high confidence
4. FDR correction: Benjamini-Hochberg (naive) + clustered logit p (rigorous)
5. Output: Per-channel `selected_band` (best band + its stats)

**File:** `analytics.py` `spectral_feature_importance()` ~1128

---

### 1.7b Mixed-Model & Forward-Windows Workflow (Candidate Selection)

Before deploying a final biomarker, the data undergoes iterative model selection and validation:

**Overview:**  
The spectral feature importance scan (§1.7) identifies candidate bands per contact. The subsequent workflow refines these candidates through temporal validation and statistical rigor before selecting the deployment-ready biomarker.

**Workflow steps:**

1. **Per-band per-contact AUC computation** (all matched PROs, pooled)
   - Logistic regression: Pain (high/low) ~ LSB, per band
   - Output: ρ (Pearson correlation), AUC, p-value (naive Pearson + clustered logit)

2. **Forward-windows validation (temporal cross-validation)**
   - Split pain reports into temporal folds (e.g., weeks 1–4, 5–8, etc.)
   - For each fold: train binarizer on other folds, test on held-out fold
   - Track AUC stability across folds (flag if any fold AUC < 0.55)
   - Gate: Only bands with median fold AUC > 0.60 advance

3. **FDR correction (multiple comparisons)**
   - Naive: Benjamini-Hochberg on all band × channel tests
   - Rigorous: Clustered logit p-value (accounts for pain autocorrelation) → Benjamini-Hochberg
   - Both reported; rigorous preferred for final deployment

4. **Per-channel best-band selection**
   - Rank bands by effect size (|ρ|) descending
   - Select highest-AUC band that passes FDR gate (or best effect size if none sig)
   - Lock this band for deployment candidate ranking

5. **Per-contact deployment ranking**
   - Score each contact: (AUC × FDR_significance × effect_size) / background_variability
   - Rank contacts by score
   - Top 3–5 contacts presented to clinician for final selection

**Outcome:**  
A shortlist of deployable (contact, band, threshold) triplets, ranked by statistical confidence. Clinician selects based on anatomical location, effect direction (elevation vs. suppression), and clinical priors.

**Code note:**  
This workflow is orchestrated across `analytics.py` (spectral_feature_importance, fold CV), `bravo_service.py` (request aggregation, response packing), and the React frontend (candidate ranking UI). No single function; rather a logical pipeline across functions. The README documents the contract, not the per-function decomposition.

---

**Output shape:**
```python
{
    'channels': [
        {
            'channel': 'R 0-3+',
            'selected_band': 25.5,  # center Hz
            'rho': -0.483,          # Pearson correlation
            'auc_signed': 0.439,    # Folded AUC
            'q': 0.52,              # FDR q-value
            'direction': 'suppression',  # or 'elevation'
            'fdr_significant': False,
            'n_td': 18,             # distinct PROs w/ TD LSB
            'n_psd': 83,            # distinct PROs w/ PSD LSB
        },
        ...
    ],
    'binarization': {...}
}
```

---

### 1.8 Binarization (Label Generation)

**Goal:** Create a binary pain label (high/low) for threshold training.

**Method (v3.1.0):**
1. Count distinct PROs per channel with resolved LSB
2. Compute tertile cuts on the unique-PRO pain-score distribution
3. Label: low (bottom tertile), high (top tertile), excluded (middle)

**File:** `analytics.py` `_binarize_labels()` ~908

**Critical fix (v3.1.0):**  
Previously computed tertiles on the pseudoreplicated per-sample vector (one entry per LSB estimate, not per PRO). Now:
```python
def _binarize_labels(ratings_per_pro, percentile_low=33.3333, percentile_high=66.6667):
    """
    ratings_per_pro: list of pain scores (one per distinct PRO w/ LSB)
    Returns: labels (one per PRO, not per sample)
    """
    low_thresh = np.percentile(ratings_per_pro, percentile_low)
    high_thresh = np.percentile(ratings_per_pro, percentile_high)
    return {pro: 'low' if score <= low_thresh
                 'high' if score >= high_thresh
                 'excluded' for score, pro in ...}
```

---

### 1.9 Per-Channel Count Semantics (v3.1.0)

**The Fix:**  
Response includes per-channel sample counts that must match logical entities:

```python
{
    'channels': [
        {
            'n_high': 204,           # distinct PROs labeled high on this channel
            'n_low': 206,            # distinct PROs labeled low on this channel
            'n_excluded': 9,         # distinct PROs labeled excluded
            'n_td': 94,              # distinct PROs w/ TD LSB on this channel
            'n_psd': 325,            # distinct PROs w/ PSD bridge on this channel
            # Invariant: n_high + n_low + n_excluded = n_td + n_psd = n_channel
        }
    ]
}
```

**Implementation:** `analytics.py` ~1271 (`chan_fin` gating), ~1433 (n_high/low/excluded), ~1434 (n_td/n_psd_bridge)

---

### 1.10 Data Flow (Full Request → Response)

```
POST /api/queryBiomarkerAnalysis
  {
    participant_id: "2e3c75c00d7f4f37b53a048d195f11da",
    MatchToleranceMin: 120,       # minutes → tol_s = 7200 s
    MatchExtentSec: 30,           # seconds → td_quantity_s
    AllowWindowReuse: false,      # per-modality, no sample reuse across PROs
  }
  │
  ├─ bravo_service.py::queryBiomarkerAnalysis() ~2970
  │   ├─ Load Recordings (TD, montage PSD, event PSD, survey PSD)
  │   ├─ Build raw cache: raw_lsb_spectrum_cache()
  │   ├─ For each channel:
  │   │   ├─ live_lsb_spectrum_match(pro.t, tol_s, td_quantity_s)
  │   │   ├─ Collect LSB for all PROs on channel
  │   │   └─ Assemble (channel, pro, lsb, pain) tuples
  │   │
  │   └─ spectral_feature_importance(lsb_matrix, pain_vector, ...)
  │       ├─ Per band, per channel: ρ, AUC, p-value
  │       ├─ FDR correction (naive + rigorous)
  │       ├─ Select best band per channel
  │       └─ Return {channels: [...], binarization: {...}}
  │
  └─ Response JSON
      {
        "source": "both",
        "channels": [
          {
            "channel": "L 0-2+",
            "selected_band": 19.5,
            "rho": -0.815,
            "auc_signed": 0.938,
            ...
          },
          ...
        ],
        "binarization": {
          "n_high": 1336,
          "n_low": 1021,
          ...
        }
      }
```

---

### 1.11 Testing & Validation

#### Unit Tests
- **test_analytics.py:** Scatter dedup, binarization tertiles, FDR logic, AUC folding
- **test_per_pro_lsb.py:** Matching logic, nearest-tile capping, reuse semantics
- **test_availability.py:** Cache generation, saturation gating, tier assignment

**Run all tests:**
```bash
cd /usr/src/BRAVO
PYTHONPATH=/usr/src/BRAVO:/usr/src/BRAVO/modules python3 -m pytest \
  BRAVO/modules/Biomarkers/tests/test_analytics.py \
  BRAVO/modules/Biomarkers/tests/test_per_pro_lsb.py \
  -v
```

**Expected:** 261 PASS / 0 FAIL (as of v3.1.0 merge commit 39dfb2f)

#### Audit Tool
Validate response JSON consistency:
```bash
python3 BRAVO/modules/Biomarkers/tools/audit_biomarker_payload.py \
  --json /tmp/biomarker_response.json
```

Will flag any mismatches between labels shown on plots vs. actual data.

---

## 2. Deployment Module (`Client/src/views/Reports/ClosedLoopSim/`)

### 2.1 Purpose

Clinician-facing interface for selecting a validated biomarker band and configuring it for closed-loop deployment on the Percept RC.

### 2.2 Components

| File | Role |
|---|---|
| **index.js** | Main report container; state management (selected band, thresholds, channel toggles) |
| **BandCandidateStore.js** | Spectral feature list ("which bands are available for this contact?") |
| **DeploymentVerdictStrip.js** | Statistical verdict badge (FDR-significant, effect direction) |
| **DeploymentRocPanel.js** | ROC curve per selected band (sensitivity vs. 1-specificity) |
| **LsbPowerPanel.js** | LSB power time series with threshold overlay |
| **ConversionModelPanel.js** | Calibration between device LSB and patient pain score |
| **EraRefitPanel.js** | Refit thresholds on new eras (patient trajectory changes) |
| **DeploySignoffCard.js** | Final sign-off: "I approve (contact, band, threshold) for this patient" |
| **palette.js** | Color scheme (contacts, severity bands) |
| **deployPrint.css** | Print-friendly styling |

---

### 2.3 Workflow

```
1. Clinician navigates to ClosedLoopSim report for a patient
                ↓
2. React loads biomarker response via queryBiomarkerAnalysis
                ↓
3. User selects a contact → BandCandidateStore displays available bands
                ↓
4. User selects a band → DeploymentRocPanel shows ROC, statistical verdict
                ↓
5. User adjusts sensitivity slider → Threshold updates in LsbPowerPanel
                ↓
6. User reviews pain-calibration in ConversionModelPanel
                ↓
7. User clicks "Approve" in DeploySignoffCard
                ↓
8. POST /api/deployBiomarker with (contact, band, threshold) 
   → Percept RC receives program update (via Medtronic API)
```

---

### 2.4 Key UI Elements

#### Band Candidate Store
Shows all statistically validated bands for selected contact.
- Sorted by effect size (|ρ|) descending
- Color-coded: green (elevation, rho > 0), orange (suppression, rho < 0)
- FDR badge: green = q < 0.05, grey = q ≥ 0.05

#### Verdict Strip
Compact summary:
```
✓ FDR-significant | β suppressed @ 25.5 Hz | ρ = -0.81 | AUC = 0.94
```

#### ROC Panel
- X-axis: 1 − specificity (false positive rate)
- Y-axis: Sensitivity (true positive rate)
- Diagonal: chance (AUC = 0.5)
- Threshold slider overlays on curve

#### LSB Power Timeline
- Y-axis: LSB (scaled contact voltage estimate)
- X-axis: time
- Red shading: high pain episodes
- Horizontal threshold line: current detector setting
- Hover: PRO timestamp, pain score, LSB value, detection decision

---

### 2.5 Threshold Selection

**Goal:** Choose a LSB cut point that maximizes clinical utility (high sensitivity, acceptable false-alarm rate).

**Interface:**
- Slider: drag to adjust threshold
- ROC curve: click point to snap to preset sensitivity (e.g., 80%, 90%)
- Metrics update live: "At this threshold: 89% of pain events detected, 5 false alarms per hour"

**Typical workflow:**
1. Start with Youden index (sensitivity + specificity − 1, maximized)
2. Adjust for patient tolerance of false alarms vs. missed detections
3. Sign off when satisfied

---

### 2.6 Deployment API

**Endpoint:** `POST /api/deployBiomarker`

```json
{
  "participant_id": "2e3c75c00d7f4f37b53a048d195f11da",
  "contact": "L 0-2+",
  "center_hz": 25.5,
  "threshold_lsb": 45.2,
  "sensing_mode": "chronic",  // or "streaming"
  "clinician_notes": "Patient reports symptom relief with prior tremor DBS at 160 Hz..."
}
```

**Backend handling (deferred to next session):**
- Validate threshold is within learned distribution
- Query Medtronic API to push program to RC
- Log sign-off timestamp and clinician ID
- Archive old program for audit trail

---

### 2.7 Refit Workflow (EraRefitPanel)

Over time, patient pain characteristics may shift. Refit allows:
1. Select new data era (e.g., "last 30 days" after med change)
2. Re-run binarization on new era only
3. Compare new threshold to old (alert if >15% shift)
4. Approve new threshold or revert

---

## 3. Deployment Checklist

Before deploying a biomarker, confirm:

### Data Quality
- [ ] ≥20 pain reports with matched neural data on selected contact
- [ ] LSB saturation events <5% of total
- [ ] No >2 h gaps in neural data

### Statistical
- [ ] FDR-significant band (q < 0.05) or strong effect size (|ρ| > 0.7)
- [ ] AUC > 0.65 on held-out fold
- [ ] Effect direction consistent with prior (pain suppression or elevation expected?)

### Clinical
- [ ] Contact location confirmed on imaging (correct target)
- [ ] Threshold tested offline: "would this have caught recent pain episodes?"
- [ ] Clinician approved verdict in DeploySignoffCard

### System
- [ ] Percept RC firmware supports custom power thresholds (typically RC+7.0+)
- [ ] Medtronic API credentials configured (PERCEPT_API_KEY env)
- [ ] Test push-to-device on mock RC (if available)

---

## 4. Configuration & Tuning

### Environment Variables

```bash
# REDCap
export REDCAP_API_URL="https://redcap.ucsf.edu/api/"
export REDCAP_API_TOKEN="<your-token>"

# Percept (if using live device sync)
export PERCEPT_API_KEY="<medtronic-api-key>"
export PERCEPT_PATIENT_LOOKUP="<endpoint>"

# Biomarker tuning (optional)
export BRAVO_MAIN_BIPOLAR="ZERO_THREE,ONE_THREE,ZERO_TWO"  # Default pairs
export LSB_VALIDATED_HZ_RANGE="7.8-30.0"  # Deployment freq ceiling
```

### Key Hyperparameters (analytics.py)

| Param | Default | Meaning |
|---|---|---|
| `band_width_hz` | 5.0 | Spectral feature width around center |
| `low_pct` / `high_pct` | 33.3 / 66.7 | Binarization percentiles (tertiles) |
| `n_peaks` | 6 | Top spectral peaks to report |
| `max_scatter` | 400 | Max points on correlation scatter (deduplicate if >) |
| `max_missing_frac` | 0.10 | Tolerance for NaN samples in LSB matrix |

### Matching Slider Ranges (bravo_service.py)

| Param | Min | Default | Max | Unit |
|---|---|---|---|---|
| `MatchToleranceMin` | 1 | 60 | 1440 | minutes |
| `MatchExtentSec` | 3 | 30 | 300 | seconds (TD only) |

---

## 5. Common Issues & Troubleshooting

### "No biomarkers found" / Blank report

**Cause:** No pain reports matched to neural data within tolerance window.

**Fix:**
1. Check MatchToleranceMin is not too restrictive (try 120 min)
2. Verify participant has both TD and PSD recordings
3. Check pain reports timestamped correctly in REDCap (not in future)
4. Run audit: `python3 tools/audit_biomarker_payload.py --json <response>`

### Per-channel counts don't match (n_high ≠ n_td + n_psd)

**Cause:** Old analytics.py, or counts computed on wrong entity (sample vs. PRO).

**Fix:**
- Update to v3.1.0+ (commit 39dfb2f or later)
- Check that response uses `rating_group` for per-PRO binarization, not per-sample

### FDR q-value is unexpectedly high (>0.05 for all bands)

**Cause:** 
- Small sample size (n < 50 PROs)
- High autocorrelation in pain scores not accounted for
- Multiple comparisons (many channels × many bands)

**Fix:**
- Increase tolerance window (MatchToleranceMin) to capture more reports
- Use rigorous FDR (clustered logit) instead of naive Benjamini-Hochberg
- Focus on largest effect sizes (|ρ| > 0.7) regardless of q-value

### Threshold deployment rejected by Percept RC

**Cause:**
- RC firmware does not support custom power thresholds
- Threshold value outside valid range for device (typically 0–4095 LSB)
- Device API credentials expired

**Fix:**
- Check RC firmware version (must be RC+7.0 or later)
- Verify threshold is in range: log-scale LSB should be ~0–100 on typical patients
- Refresh Medtronic API token

---

## 6. Architecture Decisions

### Why Two-Window Matching?

The original single window caused **UI/computation mismatch**: the main slider (MatchToleranceMin) only affected binarization, not the LSB computation itself. Users expanded the slider expecting more matches but got none.

**Solution:** Main slider gates eligibility for both TD and PSD; separate TD-extent slider controls TD aggregation only. This keeps the UI paradigm: "one slider per control."

### Why Per-Channel, Not Per-Contact?

Each physical contact pair (e.g., "L 0-2+") represents one **channel** in the recording. We compute LSB and biomarkers per channel because:
1. Each channel has independent electrode impedance and noise
2. Each channel may respond differently to stimulation (heterogeneous effect)
3. Clinician must program each channel's threshold separately on the RC

### Why Fold AUC?

Biomarkers can work in two directions:
- **Elevation:** Pain → increased power (e.g., beta-band increase)
- **Suppression:** Pain → decreased power (e.g., theta-band suppression)

Folding AUC (`max(auc, 1 - auc)`) treats both as equally confident, and the `direction` field tells you which. This avoids artificially low AUC for suppression bands.

### Why Montage PSD in Cache?

Montage snapshots (device-recorded PSDs during clinical programming) provide calibration points. They:
- Anchor LSB scaling across patients
- Provide LSB estimates when no real-time TD is available
- Enable "what-if" modeling (simulate threshold on montage data)

---

## 7. Testing Workflow

### Local Testing (No Docker)

```bash
cd /Users/pshirvalkar/dev/BRAVO_pain

# Run unit tests
PYTHONPATH=BRAVO:BRAVO/modules python3 -m pytest \
  BRAVO/modules/Biomarkers/tests/ -v --tb=short

# Audit a response
python3 BRAVO/modules/Biomarkers/tools/audit_biomarker_payload.py \
  --json /tmp/my_response.json
```

### Bridge Testing (Full Stack)

```bash
# Sync code into bridge
cp BRAVO/modules/Biomarkers/routines/*.py /usr/src/BRAVO/_agent_bridge/

# Run container suite
docker-compose exec bravo-server python3 /usr/src/BRAVO/_agent_bridge/run_tests.py

# Live API call
curl -X POST http://localhost/api/queryBiomarkerAnalysis \
  -H "Content-Type: application/json" \
  -d '{
    "participant_id": "2e3c75c00d7f4f37b53a048d195f11da",
    "MatchToleranceMin": 120,
    "MatchExtentSec": 30
  }' | jq '.channels[0]'
```

### Regression Testing

After any change to analytics.py or availability.py:
1. Run full test suite
2. Save response JSON for regression participant (2e3c75c0)
3. Run audit tool
4. Compare per-channel counts to prior commit (expect ≤5% variation)

---

## 8. Key Files Reference

### Backend Analytics

```
BRAVO/modules/Biomarkers/
├── bravo_service.py          # Django DRF endpoint, caching, parameter parsing
├── routines/
│   ├── analytics.py          # Spectral feature importance, binarization, FDR
│   ├── availability.py       # LSB matching, cache, raw FFT computation
│   ├── streaming_psd.py      # Welch PSD from raw TD (provenance: Yiyuan Han)
│   ├── threshold_biomarker.py # Chronic-trend analysis, Otsu labeling
│   ├── stats_utils.py        # Autocorr, permutation null, block length
│   └── redcap_client.py      # REDCap PRO ingestion (vendored, no external deps)
├── tests/
│   ├── test_analytics.py     # Scatter dedup, binarization, AUC
│   ├── test_per_pro_lsb.py   # Matching semantics, capping
│   └── test_availability.py  # Cache, saturation, tier logic
└── tools/
    └── audit_biomarker_payload.py  # JSON validation & label-data consistency
```

### Frontend Deployment

```
Client/src/views/Reports/ClosedLoopSim/
├── index.js                    # Main report, state, slider handlers
├── BandCandidateStore.js       # Spectral band list
├── DeploymentVerdictStrip.js   # Statistical badge
├── DeploymentRocPanel.js       # ROC curve visualization
├── LsbPowerPanel.js            # LSB timeline + threshold line
├── ConversionModelPanel.js     # Pain-score calibration
├── EraRefitPanel.js            # Threshold refit on new data eras
├── DeploySignoffCard.js        # Final approval card
├── palette.js                  # Color definitions
└── deployPrint.css             # Print-friendly layout
```

---

## 9. Development & Contribution

### Adding a New Spectral Metric

1. **Analytics:**
   - Add metric function to `analytics.py`
   - Compute per-band, per-channel
   - Return dict with confidence interval

2. **Testing:**
   - Write unit test in `test_analytics.py`
   - Validate on 2e3c75c0 (regression participant)

3. **Audit:**
   - Update `tools/audit_biomarker_payload.py` if response schema changes
   - Re-audit all saved responses

4. **Docs:**
   - Update this README
   - Note any parameter tuning needed

### Changing Binarization Logic

**High risk.** Affects:
- Training data for closed-loop detector
- ROC curves (sensitivity/specificity)
- Deployment decisions

**Procedure:**
1. Announce change on Slack
2. Write regression test on multiple participants
3. Save responses before/after; compare per-channel distributions
4. Require second review before merging

---

## 10. Citation & Acknowledgments

**Biomarker validation:**  
Shirvalkar P, Prosky J, Chin G, et al. *First-in-human prediction of chronic pain state using intracranial neural biomarkers.* Nature Neuroscience. 2023 May;26(5):1090-1099. PMID: 37217725.

**Spectral analysis (streaming_psd):**  
Adapted from `biomarker_analysis_streaming.ipynb` (Yiyuan Han, Shirvalkar Lab).  
Welch PSD computation: scipy.signal.welch (original windowing/overlap preserved).

**Chronic-trend analysis (threshold_biomarker):**  
Byte-for-byte port from `threshold_biomarker.ipynb` cell 13 (Shirvalkar Lab).

**REDCap integration:**  
PyCap library (https://redcap-tools.github.io/pycap/).  
Token-based API auth via environment variables.

---

## Document Version History

| Date | Commit | Changes |
|---|---|---|
| 2026-06-29 | 39dfb2f | v3.1.0 final: Two-window matching, per-channel count fixes, full docs |
| 2026-06-28 | 2daf80e | Phase 1–4a complete: R1/R2/R11/R12 remediation |
| 2026-06-27 | d521acd | Raw cache + live matching wired in |

---

**Questions?** See the compaction history or open an issue on GitHub.

