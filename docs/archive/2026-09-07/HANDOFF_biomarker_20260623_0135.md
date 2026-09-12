# HANDOFF — BRAVO biomarker module, post-wave-1
Generated: 2026-06-23 01:35
Picks up from: `HANDOFF_biomarker_20260622_2132.md`
Governing spec: `DESIGN_biomarker_pipeline_v2.md` (artifact_id `bab71722-0293-453e-9d21-36b77a26cbac`)

---

## State of the world

**Repo:** `/Users/pshirvalkar/dev/BRAVO_pain`
**Branch:** `PS_biomarker_module`
**HEAD:** `283d2b1` (Frontend click-validate: glmer OR+CI readout, stim-stability badge)
**Served bundle:** `main.c3b10ccd.js` (chunk `964.3432ec75.chunk.js` carries the biomarker view)
**Tests:** 103/103 (run via `python3 bridge_client.py --cwd /usr/src/BRAVO --timeout 600 "python3 _agent_bridge/run_tests.py"`)
**Participant:** RCS08, uid `2e3c75c00d7f4f37b53a048d195f11da`
**Backend container:** Docker; bridge via `BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO`
**Frontend host build:** `cd Client && env CI=false GENERATE_SOURCEMAP=false npm run build`
**Backend reload:** bridge `kill -HUP 1`
**Commit identity:** `git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu"`

## What shipped this session (10 commits, this branch)

This session, top to bottom:

| SHA | Title |
|---|---|
| `283d2b1` | Frontend click-validate: glmer OR+CI readout, stim-stability badge |
| `aba58f7` | Wave-1 click-validate endpoint: glmer OR+CI and band × stim-era LRT |
| `2c64ca2` | Live-feedback fixes to rigor-pass UI: legend, violin dots, legend reset |
| `3cd8bc0` | Frontend rigor pass: FDR-marker dots on scan plot + pseudoreplication subtitle |
| `36d81d7` | Backend rigor pass: BH-FDR over band × channel grid in `spectral_feature_importance` |
| `5969d7c` | Preserve scan-plot legend toggles across band-click re-renders |
| `8473189` | Ring-aware channel canon — stop silently dropping the Survey product |
| `5f4a612` | Click panel: two-up scatter + violin with effect size |
| `806b929` | Timeline legend order (montage PSD at top, raw TD at bottom) |
| `60f231a` | Timeline legend recolor + reorder |

## Wave 1 in one paragraph

The discovery view is now statistically honest. The full-spectrum scan still emits Pearson r and AUC as before, but adds per-band BH-FDR over the band × channel grid using rating-clustered logistic p as the primary inference, and the scan plot draws black-ringed marker dots on every FDR-significant band (legend-grouped to the channel toggle). The subtitle carries the live pseudoreplication contrast — "N bands survive rigorous FDR; M survive naive Pearson FDR" — directly from `fdr_summary` in the backend payload. Clicking a band fires `/api/queryBandValidation`, which runs glmer (pain_high ~ band_power + (1|weekly_era)) and a band × stim-era LRT in the container and returns an OR + 95% CI + stim-stability verdict. The verdict surfaces as a color-coded badge (green: stim-stable, amber: stim-dependent, grey: candidate/failed) plus three explanatory lines under the violin.

## Validation findings (the standalone notebook delivered earlier)

These rulings stand from the offline validation pipeline and seed wave 2:

- **Pseudoreplication is the dominant risk.** 911 naive-Pearson FDR-significant cells across the 6-metric grid; 5 survive rating-clustered FDR.
- **14 validated band-candidates** survive the full pipeline (glmer FDR q<0.05, non-singular, no separation). 12 of 14 live on ZERO_THREE bilaterally (high-frequency 54–87 Hz, negative direction for NRS/VAS/MPQ); 1 is back-VAS on ZERO_TWO_LEFT @ 88 Hz (also negative); 1 is left-leg-VAS on ONE_THREE_LEFT @ 23.5 Hz (positive, OR=15.4).
- **Stim split:** 5 stim-dependent (all high-freq ZERO_THREE; effect abolished at HIGH stim) + 9 stim-stable.
- **Best closed-loop target:** the left-leg-VAS beta-band candidate on ONE_THREE_LEFT @ 23.5 Hz — stim-stable across all three eras (OR ≈ 11.7 / 4.8 / 4.8), and on the device's adaptive band (8–30 Hz).

Reference artifacts (saved, featured):
- `validated_band_candidates_RCS08.csv` `0e660411-b19c-4e98-a7a4-16841e2593db`
- `VALIDATION_report_RCS08.md` `ca8a004e-5b58-4656-a105-149db3f4a2e1`
- `validate_biomarkers_RCS08.py` `e72d706b-ab64-4339-922e-b7c2b686091f`
- `fig1_pseudoreplication_RCS08.png` `42c1d9c8-1a60-4e3b-ad8e-26fc9be82a2b`
- `fig2_forest_OR_RCS08.png` `a876058b-d348-43d9-8911-11bc500f5afa`
- `fig3_stim_stability_RCS08.png` `3a789884-cae0-4894-84f4-c55d2952e981`
- `AUDIT_stream_exclusions_RCS08.md` `f6aa2f03-4bc4-44e2-b3ef-44fedf2eccb9`
- `stream_audit_RCS08.png` `2617bb5f-c971-47e9-a883-8f1eb8c134b8`

## Endpoints & files of record

**New endpoint:** `POST /api/queryBandValidation`
- View: `Server/APIs/DataAnalysis.py` → `QueryBandValidation`
- URL: `Server/APIs/urls.py` line 83
- Service: `modules/Biomarkers/bravo_service.py` → `validate_band_for_participant` (just before `pain_scores_for_participant`)
- Analytics: `modules/Biomarkers/routines/analytics.py` → `band_mixedmodel_inference` (now emits `or_lo`/`or_hi`/`singular`) and `band_stim_stability` (new — band × stim-era LRT with OFF/LOW/HIGH ORs)

**Scan rigor pass (already wired into existing endpoint):** `spectral_feature_importance` in `analytics.py` now adds per-channel `q`, `q_pearson`, `is_fdr_sig`, `p_pearson`, plus a top-level `fdr_summary: {n_bands_total, n_rigorous_fdr, n_naive_fdr, alpha=0.05, method="BH-FDR", family="band x channel (per metric)"}`.

**Frontend wiring:** `Client/src/views/Reports/Biomarkers/BiomarkerAnalytics.js`
- `SpectralFeatureImportance` reads `scan.fdr_summary` for the subtitle annotation
- Per-channel FDR-marker overlay traces in the trace-build loop (one-line `ch.is_fdr_sig`)
- New `ValidationReadout` component fires `/api/queryBandValidation` on band click; renders badge + 3 caption lines
- `index.js` passes `participantUid` + `requestParams` through so the validation call uses the identical band-feature definition as the clicked scan dot

## Open threads picked up from prior session

1. **High-frequency (54–87 Hz) bands need stim-artifact scrutiny** before being treated as deployable biomarkers (line-noise harmonics + DBS spillover need explicit ruling-out on raw TD).
2. **Composite metric validated = 0** — likely a power problem with the blended label, not necessarily a true null. Flagged in the validation report's Caveats.
3. **`fdr_summary` numbers were 88 of 576 (live) vs 5 of 558 (offline standalone).** Live numbers came from the live scan grid; offline used a slightly different grid spec. The CONTRAST direction (rigorous ≤ naive) holds in both — the invariant the UI annotation rests on. Worth a one-paragraph note for the deployment module's methods section about which grid lives in production.
4. **`channel.raw` may not always exist in the scan payload.** The click-validate frontend falls back to `channel.short`, and the backend resolver in `band_mixedmodel_inference` accepts either, so this is safe — but worth confirming on first live click of wave 2 and adding `channel.raw` to the scan emission if needed.

## Wave 2 — Threshold-deployment module (Prasad's call to start)

The architecture conversation that ran mid-session resolved to this split:

- **Biomarker module (now wave-1-done):** discovery + per-candidate validation. Full-spectrum exploration, FDR rigor, click-validate (glmer + stim-LRT), violin/scatter on click.
- **Threshold-deployment module (wave-2 new view):** operates on **one validated BandCandidate at a time**, with deployment-engineering controls. Ingests the BandCandidate object the DESIGN spec defines (§6 schema, with the Timeline LSB anchoring in §5). The current Power-Domain section is the seed — keep it; the new view extends it.

### Proposed wave-2 panels

1. **BandCandidate emission.** First wire: clicking a VALIDATED band in the biomarker view exports a `BandCandidate` (channel, lo–hi Hz, direction, OR + CI, FDR q, stim-stability flag, per-era ORs, sample n) into project state. New endpoint or RPC, OR a JSON download artifact + manual upload — pick based on UX simplicity. Spec lives in `DESIGN_biomarker_pipeline_v2.md` §6.
2. **ROC with rating-clustered CI.** AUC + 95% confidence band over the validated band's matched samples, with the rating-clustered correction the discovery scan uses. This is the deployment-grade AUC — not the cross-validated AUC the scan shows.
3. **Cut-point search.** Youden / F1 / Net Benefit slider, with the resulting cut-point shown on both the ROC and the band-power histogram (high-pain vs low-pain density overlay). Cut-point in z-units AND in raw band-power units AND in **Timeline LSB** (DESIGN §6, anchor formula 0.0034 LSB↔µV² empirical).
4. **Power / sample-size.** For the measured effect size (OR from glmer or AUC from ROC), given the participant's PRO-day count, what stim-amplitude effect can we detect with 80% power? (Standard formula on the binomial proportion.) Answers "do we need another data-collection round before we trust this threshold?"
5. **Stim-state cross-validation panel.** Re-fit on each era (OFF/LOW/HIGH), report per-era AUC + chosen cut-point. Flag where they diverge by more than a configurable threshold — the deployment-time analog of the stim-stability test the click-validate does.
6. **"Deploy to Percept" review card.** Final read-only summary: channel, band, cut-point in LSB, direction, expected sensitivity/specificity, confidence interval, deployment caveats. This is the artifact a clinician signs off on.

Suggested commit sequencing (one logical PR per phase):
- **Phase A:** BandCandidate object + emit-from-biomarker-view + load-into-threshold-view round-trip. Smallest end-to-end change that makes the two views talk.
- **Phase B:** ROC + cut-point in the threshold view (read-only on the loaded BandCandidate).
- **Phase C:** LSB conversion + power analysis.
- **Phase D:** Per-era cross-validation panel.
- **Phase E:** Sign-off card + (eventually) Percept-RC push hook.

### Things to keep in mind

- **`/Users/pshirvalkar/.config/git/ignore` warning is benign** — it surfaces on every git operation. Ignore.
- **figure-style kernel plugin still loads cleanly** (`apply_nature_style()` + helpers). For wave-2 figures, use it.
- **Don't remove the existing Power-Domain section yet.** Wave 2 grows it; this is the seed of the threshold-deployment view.
- **Composite metric** (mpq + left_leg_vas blend) had zero validated candidates — for wave-2 deployment UX, default the BandCandidate emission to single-metric (NRS or VAS as anchor); composite is a power-flagged "advanced" option.
- **Pre-cleanup before next push:** the `BRAVO/_agent_bridge/` dir has ~15 untracked one-off scripts from this session (audit_*.py, phase0_*.py, phase2*.py, grab_band*.py, glmer_*.csv, phase0_*.npz). These are not under version control by intent (bridge sandbox). Consider a `.gitignore` line `BRAVO/_agent_bridge/audit_*.py` etc. if they're getting noisy.

## Quick re-orient commands for the next session

```bash
# Confirm where we are
cd /Users/pshirvalkar/dev/BRAVO_pain
git log --oneline -8
git status -s | head -20

# Tests (101/101 → should be 103/103)
cd BRAVO/_agent_bridge
python3 bridge_client.py --cwd /usr/src/BRAVO --timeout 600 \
  "python3 _agent_bridge/run_tests.py 2>&1 | grep -E 'PASS|FAIL' | tail -2"

# Backend reload after edits
python3 bridge_client.py --cwd /usr/src/BRAVO --timeout 30 "kill -HUP 1"

# Frontend rebuild (HOST, NOT container — Client is not mounted)
cd /Users/pshirvalkar/dev/BRAVO_pain/Client
env CI=false GENERATE_SOURCEMAP=false npm run build
```

## Live-app sanity check the user should do before wave-2 starts

Click any FDR-significant band on the scan plot — the validation readout should populate under the violin within ~1s. Recommended demo bands:

- **Left-leg-VAS @ 23.5 Hz on ONE_THREE_LEFT** — should read VALIDATED (stim-stable), green; OR ≈ 15, per-era ORs all > 1.
- **VAS @ 82 Hz on ZERO_THREE_RIGHT** — should read VALIDATED (stim-dependent), amber; OR << 1 at OFF/LOW, ~1 at HIGH.

If the first click works, wave 2 can start. If not, the most likely culprit is `channel.raw` missing from the scan payload — see open thread (4).

---
End of handoff.
