# HANDOFF — BRAVO biomarker module, post-PRO-first-revalidation
Generated: 2026-06-23 13:00
Picks up from: `HANDOFF_biomarker_20260623_0135.md` (post-wave-1)
Governing spec: `DESIGN_biomarker_pipeline_v2.md` (artifact_id `bab71722-0293-453e-9d21-36b77a26cbac`)

## State of the world

**Repo:** `/Users/pshirvalkar/dev/BRAVO_pain`
**Branch:** `PS_biomarker_module`
**HEAD:** `a9f1a69` (Binarization preview: PRO-first framing throughout)
**Bundle:** `main.38be0cad.js`, chunk `964.65f3b2e8.chunk.js`
**Tests:** 109/109
**Participant:** RCS08, uid `2e3c75c00d7f4f37b53a048d195f11da`
**Backend container:** bridge via `BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO`
**Frontend build (host):** `cd Client && env CI=false GENERATE_SOURCEMAP=false npm run build`
**Backend reload:** bridge `kill -HUP 1`
**Commit identity:** `git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu"`

## What shipped after the prior handoff (2 commits)

| SHA | Title |
|---|---|
| `a9f1a69` | Binarization preview: PRO-first framing throughout (captions, badges, copy) |
| `856c44c` | PSD<->PRO matching: PRO-first default + 60-min default window |

Prior handoff (HEAD=283d2b1) covered: scan rigor pass (FDR), click-validate endpoint + readout, live-feedback UI fixes, legend uirevision, ring-canonicalizer, click-panel violin.

## The matching change in one paragraph

The original default (`tol=15 min`, `direction="prior"` — PSD must precede the rating) covered only 44 of 682 pain reports on RCS08. Prasad spotted this from the timeline raster — most "unselected" PSDs were close to pain ratings but excluded by the strict window. Fix: new `direction="pro_first"` mode in `_match_to_pro` walks pain ratings (the units of statistical independence) and claims up to max_per_rating closest PSDs per channel each within tolerance, never re-claiming a PSD already taken by an earlier rating. PRO-first is now the discovery default with `tol=60 min`. PSD-first "nearest" and "prior" modes are preserved for back-compat and the threshold-deployment view (forecasting). UI exposes all three with plain-language captions; binarization preview copy now leads with the unit that fits the toggle (pain ratings under PRO-first, neural samples under PSD-first).

Effect at the new defaults (vas metric, RCS08):

| direction | PROs covered | PSD-rows matched |
|---|---|---|
| prior (old default) | 67 / 682 (9.8%) | 517 |
| nearest | 288 / 682 (42.2%) | 1,352 |
| **pro_first (new)** | **290 / 682 (42.5%)** | **1,627** |

## Re-validation under PRO-first (v2)

Full standalone validation re-run against the new pool. Headline numbers vs v1:

- **Pseudoreplication contrast** holds in 5/6 metrics (rigorous FDR ≤ naive FDR). VAS flips (191 rigorous vs 169 naive) — clustered logit gains more from larger PRO n than Pearson does; noted in methods.
- **12 candidates survive mixed-effects FDR** (vs 14 in v1; different bands).
- **7 of 12 have credible 95% CIs** (CI width > 0.10 in OR units). The other 5 carry numerically narrow Wald CIs (cluster saturation artifact) — re-validate via cluster bootstrap before deployment.
- **9 of 12 are stim-stable** by LRT.
- **v1's best closed-loop target (leg-VAS @ 23.5 Hz, OR ≈ 15) does NOT survive v2** — it didn't enter the top 8 by Cohen's d under the larger left-leg-VAS pool (264 PROs). v1 was likely benefiting from low-n optimism.
- **New best closed-loop targets** (all stim-stable, credible CIs, negative direction, off the device's 8–30 Hz adaptive default): NRS @ 84.5 Hz on ZERO_THREE_RIGHT (OR 0.41), NRS @ 55.5 Hz on ONE_THREE_RIGHT (OR 0.23 — strongest effect), VAS @ 61.5 Hz on ZERO_TWO_LEFT (OR 0.11 — widest CI from low n).
- **High-frequency signal scrutiny is more urgent now**, not less: more high-freq candidates survive, but patient-event PSDs cluster around pain reports by construction — a recording-trigger signature could masquerade as a pain signal. Wave 2 should refit with a `source` random intercept or stratify by source.

Reference artifacts (saved, featured):

- [VALIDATION_report_RCS08_v2.md] — at repo root, ~10 KB, methods + findings + caveats
- [validated_band_candidates_v2.csv]({{artifact:d279db71-0239-48e5-b83e-89d7df62d5dc}}) — the 12-row deliverable table
- [fig1_pseudoreplication_v2.png]({{artifact:428c0b5b-ca9b-4fab-bcc0-e6ed28f60880}}) — naive vs rigorous FDR per metric
- [fig2_forest_OR_v2.png]({{artifact:35c4f3f0-3969-4272-8764-02a73c8caee3}}) — forest plot of credible-CI candidates
- [fig3_stim_stability_v2.png]({{artifact:12d01fd4-c969-4cbb-8b36-a10b7d7ec4e5}}) — per-era ORs

Underlying tables (hidden but available): scan_full_fdr_v2.csv (3,312 cells), band_candidates_raw_v2.csv (66 clusters), glmer_results_v2.csv (42 fits), stim_hetero_v2.csv (12 LRTs), phase0_meta_v2.json.

## Files touched after the prior handoff

Backend:
- `BRAVO/modules/Biomarkers/routines/streaming_psd.py` — `_match_to_pro` extended with `pro_first`, `build_pooled_detail_from_matrix` defaults flipped to `tol=60`/`pro_first`, survey_usage carries `psd_per_pro_{mean,median,max}`.
- `BRAVO/modules/Biomarkers/bravo_service.py` — `DEFAULT_MATCH_TOLERANCE_MIN = 60.0`; `MatchDirection` parser is three-way (pro_first / nearest / prior).
- `BRAVO/modules/Biomarkers/tests/test_match_to_pro.py` (new, 6 tests).

Frontend:
- `Client/src/views/Reports/Biomarkers/index.js` — three-way ToggleButtonGroup, default `pro_first`, default tolerance 60, plain-language captions per option.
- `Client/src/views/Reports/Biomarkers/binarizationModel.js` — JS mirror of the backend `pro_first` matcher, emits `psd_per_pro_*` and `pct_psd_used`.
- `Client/src/views/Reports/Biomarkers/BinarizationPreview.js` — header + readout + signpost-badge copy all branch on `counts.match_direction`. PRO-first leads with pain ratings; PSD-first leads with neural samples.

Standalone validation (not in version control, under `BRAVO/_agent_bridge/`):
- `phase0_build_v2.py`, `phase1_scan_v2.py`, `phase2_glmer_v2.py`, `phase2b_hetero_v2.py`, `phase3_artifacts_v2.py`.

## Open threads carried into wave 2

1. **Narrow-CI candidates (5 of 12 v2).** Wald CIs from saturated random-effect fits (n_clusters small). Cluster-bootstrap (500 iters) re-validation needed before any of these go to deployment. About one screen of new code in `phase2_glmer_v2.py`.
2. **High-frequency stim-artifact / recording-trigger scrutiny.** Patient-event PSDs are recorded BECAUSE the patient triggered something — when that something is "report pain", recording timing correlates with pain by construction. Wave 2 deliverable: refit each validated candidate with a `source` random intercept or stratify by source, then surface a "source-stratified OR" badge in the click-validate panel.
3. **The composite metric is still flagged** — 6 rigorous-FDR cells and zero validated bands. Default the BandCandidate emission to single-metric anchors.
4. **The validation report v2 supersedes v1.** v1 artifacts (ca8a004e/462d6324 + figs) are kept for diff/audit but should not seed wave 2.

## Wave 2 — Threshold-deployment module (Prasad's call to start)

Architecture split (unchanged from prior handoff):
- **Biomarker module (wave-1 done):** discovery + per-candidate validation. Full-spectrum exploration, FDR rigor, click-validate, violin/scatter on click.
- **Threshold-deployment module (wave 2):** one validated BandCandidate at a time, deployment-engineering controls. The current Power-Domain section is the seed; extend it.

### Proposed wave-2 panels

1. **BandCandidate emission.** Click a VALIDATED band → export `BandCandidate` (channel, lo–hi Hz, direction, OR + CI, FDR q, stim-stability flag, per-era ORs, n) into project state. Spec in `DESIGN_biomarker_pipeline_v2.md` §6.
2. **ROC with rating-clustered CI.** AUC + 95% confidence band over the validated band's matched samples, with the rating-clustered correction the discovery scan uses. Deployment-grade AUC, distinct from the scan's CV AUC.
3. **Cut-point search.** Youden / F1 / Net Benefit slider, cut-point shown on ROC + band-power histogram (high vs low overlay). Cut-point in z-units AND raw band-power units AND **Timeline LSB** (DESIGN §6 anchor 0.0034 LSB↔µV² empirical).
4. **Power / sample-size.** Given the participant's PRO-day count and the measured effect size, what stim-amplitude effect can we detect at 80% power? Standard formula on binomial proportion. Tells the clinician whether another data-collection round is needed.
5. **Stim-state cross-validation.** Re-fit per era, report per-era AUC + cut-point. Flag where they diverge by more than a threshold — the deployment-time analog of the stim-stability LRT.
6. **"Deploy to Percept" sign-off card.** Read-only summary: channel, band, cut-point in LSB, direction, expected sens/spec, CI, caveats. The artifact a clinician approves.

Phase sequencing (one PR per phase):
- **Phase A:** BandCandidate object + emit-from-biomarker + load-into-threshold round-trip.
- **Phase B:** ROC + cut-point on the loaded BandCandidate.
- **Phase C:** LSB conversion + power analysis.
- **Phase D:** Per-era cross-validation panel.
- **Phase E:** Sign-off card + (eventually) Percept-RC push hook.

### Wave-2 priors (must-read before starting)

- **The match-window default is now 60 min, direction `pro_first`.** When wave 2 reads the matched pool for ROC, it should respect whatever is on the request (caller controls). The deployment view may want to default to `prior` (forecasting) for the ROC — that's a deliberate design decision, not a bug.
- **`channel.raw` may be missing on older scan payloads.** Frontend click-validate already falls back to `channel.short`. Confirm on first wave-2 click; if missing, add `channel.raw` to the scan emission (one line in `analytics.py`).
- **`fdr_summary` numbers in the live UI come from a slightly different grid than the offline standalone** (live uses 96 centers, offline uses 92). The INVARIANT (rigorous ≤ naive) holds in both; just note the diff in the deployment view methods.
- **figure-style kernel plugin** is still loaded. Use `apply_nature_style()` for wave-2 figures.

### Tactical notes

- **`BRAVO/_agent_bridge/` accumulated ~25 untracked one-offs.** They are intentionally not version-controlled. Consider adding `BRAVO/_agent_bridge/{audit,phase,grab,glmer,stim,scan,band,validated,fig}_*` to `.gitignore` if it becomes noisy.
- **`/Users/pshirvalkar/.config/git/ignore` warning is benign.** Surfaces on every git op. Ignore.
- **Don't remove the existing Power-Domain section.** Wave 2 grows it; this is the seed of the threshold-deployment view.
- **The leg-VAS 23.5 Hz candidate from v1 is OUT.** Don't seed wave 2 with that as a demo band.

## Quick re-orient commands

```bash
# Confirm where we are
cd /Users/pshirvalkar/dev/BRAVO_pain
git log --oneline -8
git status -s | head -20

# Tests (should be 109/109)
cd BRAVO/_agent_bridge
python3 bridge_client.py --cwd /usr/src/BRAVO --timeout 600 \
  "python3 _agent_bridge/run_tests.py 2>&1 | grep -E 'PASS|FAIL' | tail -2"

# Backend reload after edits
python3 bridge_client.py --cwd /usr/src/BRAVO --timeout 30 "kill -HUP 1"

# Frontend rebuild (HOST, NOT container)
cd /Users/pshirvalkar/dev/BRAVO_pain/Client
env CI=false GENERATE_SOURCEMAP=false npm run build
```

## Live-app sanity check before wave 2 starts

Open the biomarkers view on RCS08. Recommended demo bands:

- **NRS @ 84.5 Hz on ZERO_THREE_RIGHT** — VALIDATED stim-stable green, OR 0.41 (0.28 – 0.58). Negative direction.
- **NRS @ 55.5 Hz on ONE_THREE_RIGHT** — VALIDATED stim-stable green, OR 0.23 (0.08 – 0.70). Negative direction, strongest stim-stable effect.
- **VAS @ 61.5 Hz on ZERO_TWO_LEFT** — VALIDATED stim-stable green, OR 0.11 (0.02 – 0.51). Negative direction, wide CI from low n.
- **VAS @ 45.5 Hz on ONE_THREE_LEFT** — VALIDATED stim-dependent amber. Per-era ORs diverge (OFF 1.8, LOW 0.15, HIGH 0.31).

Check the binarization panel:
- Header reads "290 of 682 pain reports (42.5%) paired with neural data at ±60 min"
- Big readout names PSD-per-PRO depth stats (mean/median/max)
- Italics describe the PRO-first mechanism
- Signpost badges lead with pain-rating counts; PSD counts and source breakdown sit underneath

Toggle to "Nearest (±)" and the framing should flip: PSDs lead the headline, pain ratings sit underneath. Toggle to "Prior (forecast)" and you'll see the pre-PRO-first numbers (67 PROs covered). All copy should follow.

---
End of handoff.
