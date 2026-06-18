# Biomarkers module

Pain-biomarker identification and validation for closed-loop DBS, running on BRAVO's decoded
Percept recordings aligned to REDCap patient-reported outcomes (PROs). The module now ships
**end-to-end**: a DRF endpoint (`POST /api/queryBiomarkerAnalysis`) drives an interactive React
report card (`Client/src/views/Reports/Biomarkers/`) that a clinician uses to choose which contact,
band, and threshold to program on the Percept RC. A separate `POST /api/queryPainScores` serves the
PRO time series for the Pain Scores report.

The scientific goal: given a patient's chronic LFP-power trend and streaming PSD, find the
`(contact, frequency)` band whose power tracks pain, validate that it generalizes (not just an
in-sample fit), and report it honestly enough that the programmed detector is trustworthy.

> **Provenance / accountability note.** Every analytic that makes a claim on a plot (which contact,
> which sensing frequency, which AUC) is auditable against the response JSON with
> `tools/audit_biomarker_payload.py`. Run it after any change to the analytics — it is the CI gate
> for label-vs-data consistency.

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
| `bravo_service.py` | Django entry point. `run_for_participant(request)` loads the patient's decoded recordings + REDCap PROs and builds the full analytics payload the React card consumes (`_compute_analytics` runs the panel-driving analytics concurrently via `_run_parallel`, per-pooled and per-channel). `pain_scores_for_participant` backs the Pain Scores report. |
| `pipeline.py` | `run_biomarker(source=...)` dispatch + per-source branches; splits the power-domain input per bipolar contact and tags each per_channel entry with `summary.hemisphere` / `summary.kind`. |
| `routines/streaming_psd.py` | Time-domain science, extracted from `biomarker_analysis_streaming.ipynb` (transform/correlation funcs **verbatim**; Welch epoching a faithful port — see its PROVENANCE note). |
| `routines/threshold_biomarker.py` | Chronic-trend science, **byte-for-byte** from `threshold_biomarker.ipynb` cell 13 (`otsu1d`, `_sens_spec`, `_find_best_threshold_for_metric`, `run_sliding_window_dual`) + thin `run_chronic_threshold`. |
| `routines/analytics.py` | Panel-driving analytics: `roc_analysis`, `sliding_window_analytics` (per-window ROC), `lfp_distribution` (Otsu histogram), `power_pain_scatter` (continuous power-vs-pain correlation), `cluster_scatter`, `pain_binarization`, and the streaming corr-spectrum. |
| `routines/stats_utils.py` | Statistical rigor primitives: `balanced_metrics`, `bh_fdr`, `fisher_z_ci`, `effective_n` / `partial_corr` (autocorrelation-aware), `block_length_for`, and `auc_block_perm_null` (circular-block permutation null for the AUC). |
| `routines/redcap_client.py` | REDCap PRO pull, vendored from `dbs_io/utils.py`. PyCap call unchanged; **token via env vars**. |
| `adapter.py` | Glue: time-domain reshape, chronic tidy-frame (`bravo_chronic_to_lfp_df`), PRO alignment (`align_pros`), label binarization (`_threshold_pain_level`: tertile/median/cutoff/kmeans), and `merge_timelines`. |
| `tools/audit_biomarker_payload.py` | **Provenance reviewer.** Runs against a saved `queryBiomarkerAnalysis` response JSON and flags label-vs-data inconsistencies. Exit 1 on any ERROR (CI-gateable). See "Auditing" below. |
| `tests/` | `test_adapter.py`, `test_analytics.py`, `test_stats_utils.py`, `test_pipeline_stats.py`, `test_process_redcap.py` — fidelity, statistics, and regression tests on synthetic fixtures. Run all before committing. |

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
Run every suite before committing (each is also a runnable script with no pytest dependency):
```bash
export PYTHONPATH=/path/to/BRAVO
for t in test_adapter test_analytics test_stats_utils test_pipeline_stats test_process_redcap; do
  python modules/Biomarkers/tests/$t.py
done
# or, with pytest:  python -m pytest modules/Biomarkers/tests -q
```

## Run the pipeline (library / CLI mode)
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

## Statistical rigor (`routines/stats_utils.py`)
The detector must not be reported as validated on the strength of an in-sample fit. The module
separates **in-sample** from **out-of-fold** performance and tests significance against an
autocorrelation-preserving null:

- **Balanced chance, not majority.** `balanced_metrics` reports `balanced_accuracy = (sens+spec)/2`
  whose chance level is **0.50 regardless of class imbalance**. The majority-class fraction is
  reported separately as the baseline for *raw* accuracy only — it is **not** the comparator (an
  earlier bug set chance to the majority fraction, ~0.88 at 88% prevalence; fixed).
- **Direction-folded AUC.** Separability is `max(AUC, 1-AUC)` — an AUC of 0.21 separates as well as
  0.79; band/peak selection everywhere uses `argmax(|corr|)`, so a strong *negative* power↔pain
  relationship is selected on its merits.
- **Circular-block permutation null** (`auc_block_perm_null`). Daily pain is serially correlated, so
  an i.i.d. label shuffle makes p anti-conservative. The null circular-block-permutes the labels
  (block = lag-1 decorrelation timescale via `block_length_for`, positive autocorrelation only) and
  recomputes the folded AUC. Returns the add-one empirical `p_value`, `null_q` quantiles
  (p50/p95/p99) for a ceiling line, and a ≤200-value `null_sample` so the card can draw the null
  **distribution** as a swarm over the chance bar.
- **Autocorrelation-aware correlations.** `effective_n` (Bartlett) and `partial_corr` deflate the
  effective sample size and residualize confounds before reporting r/p and `fisher_z_ci` intervals;
  spectrum significance markers are `bh_fdr`-corrected across the band search.

**Headline on RCS08:** neither biomarker branch is statistically validated on the current data —
the power-domain in-sample AUC ≈ 0.69 does **not** reproduce out-of-fold (CV balanced accuracy
≈ 0.51, ≈ chance), and the permutation p / FDR q are not significant. The card surfaces that
honestly rather than presenting the optimistic in-sample number as a result.

## React report card (`Client/src/views/Reports/Biomarkers/`)
| Panel | What it shows |
|---|---|
| **Binarization preview** (`BinarizationPreview.js`) | Live PRO histogram with the tertile/median cut lines; aggregates to one value per calendar day (matching the backend daily-broadcast labels); reports days **and** raw-sample counts excluded/low/high. Fixed 0.2-wide bins. |
| **ROC curve** (`BiomarkerAnalytics.js`) | One ROC per contact + a bold **per-hemisphere mean** (Left=blue family, Right=orange family; the two stimulation targets are never averaged together). Faint per-window ROCs overlaid when the sliding window is on. Provenance is built from the contacts **actually drawn** (single-class contacts have no ROC and are excluded from the frequency list and count). |
| **Honest performance** | In-sample AUC vs CV balanced accuracy vs chance, following the contact/hemisphere toggle. Permuted-null AUCs as a gray swarm over the chance bar; per-contact values as open dots (the bar is the **pooled** detector, not the mean of the dots). |
| **Power vs pain correlation** | Continuous power biomarker vs the **selected** continuous pain score, with Pearson r and p, in its own panel — updates with the toggle. Pain kept continuous here (ROC/Otsu binarize it); p is the ordinary Pearson p, not corrected for the band search. |
| **Power band-power distribution + Otsu** | Histogram + Otsu split, both computed on the **same MAD-outlier-excluded** set so the bars and the threshold describe one distribution. |
| **Timeline** (`BiomarkerTimeline.js`) | Power-domain band power over time (labeled with recorded center frequencies + pooled-contact provenance), pain markers, stim amplitude; sensing-config change markers. |

**Frequency provenance rule (important).** ROC/distribution/sliding/scatter panels report each
plotted contact's **own recorded** `center_hz` (from `recorded_powers`), never `chronic_center_hz`
(the chronic 10-min trend's separate fixed sensing frequency). Conflating the two produced a
"@ 28.3 Hz" label on contacts that recorded at 23.4/26.4 Hz — fixed, and the audit tool checks it.

## Auditing (`tools/audit_biomarker_payload.py`)
The card makes many label claims checkable against the response JSON without rendering pixels. Save
a `queryBiomarkerAnalysis` response and run:
```bash
python modules/Biomarkers/tools/audit_biomarker_payload.py payload.json        # text report
python modules/Biomarkers/tools/audit_biomarker_payload.py payload.json --json # machine-readable
```
It flags: ROC drawn-vs-recorded frequency/count mismatches, chronic-vs-recorded provenance, honest
swarm dot counts, the per_channel hemisphere partition, AUC≈1.0 batch artifacts, sliding-window
visibility, and the pooled-target warning. Exit code is 1 on any ERROR so it can gate CI.

## Deferred / later phases
- **Django persistence of computed detectors** → `saveAnalysisProcessedData(..., type="Biomarker*",
  metadata={codeVersion})` once a programmed detector should be stored alongside its recording.
- **Per-target separation** → the power-domain threshold currently pools the two stimulation targets
  (Left GPi + Right VIM) into one raw-scale threshold (surfaced via `powerdomain_pooled_warning`); a
  per-target detector with train-fold KMeans and block-bootstrap CIs is the next rigor step.
- **REDCap field-map wiring** for the KMeans labeler's `[left_leg_vas, mpq_sum]` features.
