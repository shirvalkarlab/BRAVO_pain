# Biomarkers module

Runs the `dbs_stage2_percept` pain-biomarker routines on BRAVO's decoded Percept recordings,
aligned to REDCap patient-reported outcomes (PROs). **Library mode only** for now — no Django
endpoint, no React.

## Two selectable biomarker data sources
Biomarker identification can run from either Percept data modality, or both at once:

| `source` | Data | Science | Output per sample |
|---|---|---|---|
| `"timedomain"` | raw 250 Hz BrainSense streaming (`BrainSenseStream` recordings) | streaming PSD ↔ pain correlation (`routines/streaming_psd.py`) | PSD at the most pain-correlated `(channel, freq)` band, per session |
| `"chronic"` | the ~10-min BrainSense Timeline LFP power trend (`ChronicBrainSense` recordings) | sliding-window threshold detector (`routines/threshold_biomarker.py`) | smoothed LFP power + learned threshold + binary pain prediction, per ~10-min sample |
| `"both"` | both | both, run independently | merged onto **one timeline** (`td_*` + `chronic_*` columns) for same-page comparison |

`source="both"` keeps each science path fully isolated and merges their timelines with a
`merge_asof` onto the dense chronic spine (nearest session within 1 day; NaN where none) — so a
future React page reads one CSV and single-source is just the degenerate (one-prefix) case.

## Layout
| Path | Role |
|---|---|
| `routines/streaming_psd.py` | Time-domain science, extracted from `biomarker_analysis_streaming.ipynb` (transform/correlation funcs **verbatim**; Welch epoching a faithful port — see its PROVENANCE note). |
| `routines/threshold_biomarker.py` | Chronic-trend science, **byte-for-byte** from `threshold_biomarker.ipynb` cell 13 (`otsu1d`, `_sens_spec`, `_find_best_threshold_for_metric`, `run_sliding_window_dual`) + thin `run_chronic_threshold`. |
| `routines/redcap_client.py` | REDCap PRO pull, vendored from `dbs_io/utils.py`. PyCap call unchanged; **token via env vars**. |
| `adapter.py` | The only glue: time-domain reshape, chronic tidy-frame (`bravo_chronic_to_lfp_df`), PRO alignment (`align_pros`), and `merge_timelines`. |
| `pipeline.py` | `run_biomarker(source=...)` dispatch + branches + one-patient runner → flat file. |
| `tests/test_adapter.py` | Fidelity, alignment, chronic, merge, and back-compat tests on synthetic fixtures (10 tests). |

## ⚠️ Chronic-source caveats (read before trusting numbers)
- **`pain_level` binarization differs from the notebook.** `threshold_biomarker.ipynb` builds the
  binary label via **KMeans on `[left_leg_vas, mpq_sum]`**. The adapter instead uses a transparent
  cutoff on one chosen PRO metric (`pain_level = metric >= pain_cutoff`, default = the metric's
  median). Pass an explicit `--pain-cutoff`, or swap the binarizer, to match your labeling intent.
- **Needs many days of trend.** The sliding window is `train_days + gap_days + test_days`
  (default 7+1+2 = 10 days). One Chronic recording spans minutes, so `chronic` accepts a **list**
  of recordings that are concatenated into one long trend. Too little span → `n_windows = 0`.
- **Threshold units.** The default grid `np.arange(60, 200, 1)` is calibrated to the notebook's raw
  LFP magnitude. BRAVO's Chronic `Data[:,0]` is the decoded equivalent (device-internal power
  units); confirm magnitudes match or pass your own `thresholds`.

## Secrets
Set credentials via environment variables — **never commit a token**:
```bash
export REDCAP_API_URL="https://redcap.ucsf.edu/api/"
export REDCAP_API_TOKEN="…"          # project API token
```
A gitignored local JSON (`{"api_url":…, "api_key":…}`) is supported as a dev fallback only.

## Run the tests
```bash
python -m pytest modules/Biomarkers/tests/test_adapter.py -q
# or, with no pytest installed:
python modules/Biomarkers/tests/test_adapter.py
```

## Run the pipeline (library mode)
```bash
# time-domain only (default)
python -m modules.Biomarkers.pipeline --patient RCS08 --source timedomain \
    --pro-csv pt_data/RCS08_redcap_proc.csv --pt-config pt_config/RCS08_config.json \
    --recordings-npz decoded_RCS08.npz      # NPZ key "recordings" = list of TimeDomain dicts

# chronic only
python -m modules.Biomarkers.pipeline --patient RCS08 --source chronic --pain-cutoff 5 \
    --pro-csv pt_data/RCS08_redcap_proc.csv --pt-config pt_config/RCS08_config.json \
    --chronic-npz chronic_RCS08.npz         # NPZ key "chronic" = Chronic dict OR list of them

# both, on one timeline
python -m modules.Biomarkers.pipeline --patient RCS08 --source both \
    --pro-csv pt_data/RCS08_redcap_proc.csv --pt-config pt_config/RCS08_config.json \
    --recordings-npz decoded_RCS08.npz --chronic-npz chronic_RCS08.npz
```
Outputs `combined_<patient>_<source>.{csv,npz}` — the unified timeline (timestamp, `td_*` and/or
`chronic_*` biomarker columns, stim amplitude, PRO metrics) plus per-branch detail arrays, each
tagged with its source `code_version`.

## Deferred hooks (later phases)
- **Percept decode** → `pipeline.decode_percept_session` (wire to
  `modules/MedtronicPercept/BrainSenseStream.saveBrainSenseStreams` and `ChronicBrainSense.saveChronicBrainSense`).
- **Django persistence** → `pipeline.write_combined` is where
  `DataAnalysis.saveAnalysisProcessedData(..., type="BiomarkerStreamingPSD"|"BiomarkerChronicThreshold", metadata={codeVersion})`
  attaches.
- **DRF endpoint + React plot** → consume the unified `combined` timeline produced here (one CSV,
  `td_*` and `chronic_*` series share one x-axis).
- **Source registry** → if a 3rd data source appears, promote the `source` enum in `run_biomarker`
  to a registry (cheap then; deliberately deferred now per the design decision).
