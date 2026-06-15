# BRAVO Pain Biomarkers — Session Handoff

> Working notes for continuing this work in a new session. Everything below is live as of
> commit `6f119f6` on branch `PS_biomarker_module`.

## TL;DR
We added a **Pain Biomarkers** analysis module + card and a **Pain Scores** report to a fork of
the UF BRAVO platform, and we run the whole platform **locally in Docker**. Everything works with
a **demo participant**. Next step: load **real patient data** (REDCap + a Percept upload).

## Where things live (IMPORTANT)
- **Repo (use this path — local, NOT OneDrive):** `/Users/pshirvalkar/Documents/GitHub/BRAVO_pain`
  - OneDrive's `CloudStorage/...GitHub` copies are unreliable (they dehydrate/de-root mid-session).
    Work only in `~/Documents/GitHub/BRAVO_pain`.
- **Git:** branch `PS_biomarker_module`, pushed to `github.com/shirvalkarlab/BRAVO_pain` (public).
  Our commits start at `2a9a42e`. To push, plain `git push origin PS_biomarker_module` works.
- **Yiyuan's notebooks** (reference for the science/plots): clone fresh —
  `git clone https://github.com/shirvalkarlab/dbs_stage2_percept` (public). Key files:
  `threshold_biomarker.ipynb` (chronic), `biomarker_analysis_streaming.ipynb` (time-domain),
  `redcap_pull.py` / `full_trend_pain_score.ipynb` (pain-score metrics + stages).

## Running platform (Docker, already up)
- App: **http://localhost/** (nginx serves the React SPA + proxies `/api`). Django dev server on `:27286`.
- **Login: `demo@bravo.local` / `biomarker123`.** If asked for a "Server Host", use `localhost`.
- **Demo participant** (synthetic data): name "Demo Biomarker Patient", **MRN `DEMO_BIOMARKER`**,
  uid `e30b54dc17d3488dbe1945bb911f5549`. Any participant with that MRN returns synthetic demo data.
- Compose: top-level `docker-compose.yml` + `docker-compose.override.yml` (builds from `dockerfile.dev`,
  live-mounts `./BRAVO` + `./Client/build`, and `./BRAVO/bravo_nginx.dev.conf` as the SPA nginx config).
- Commands (run from repo root):
  - Bring up / restart: `docker compose up -d` · `docker compose restart bravo-server`
  - Logs: `docker compose logs bravo-server --since 5m`
  - Shell: `docker compose exec bravo-server python3 manage.py shell`

## Dev workflow
- **Python is live-mounted** → the Django dev server auto-reloads on save. No rebuild needed for
  backend changes (`BRAVO/...`).
- **React requires a rebuild** (the served bundle is `Client/build`, mounted into nginx):
  ```bash
  cd /Users/pshirvalkar/Documents/GitHub/BRAVO_pain/Client
  docker run --rm -v "$PWD":/app -w /app node:16 bash -lc \
    "CI=false GENERATE_SOURCEMAP=false npm run build"
  ```
  (Use Node 16 — the repo pins 14–16; the host Node is too new. `node_modules` already exists.)
  Then **hard-refresh the browser (Cmd+Shift+R)**.
- **Tests** (15, all pass) against the pinned scientific stack, inside the container:
  ```bash
  docker compose exec -w /usr/src/BRAVO bravo-server python3 -W ignore \
    modules/Biomarkers/tests/test_adapter.py
  ```
- **Verify a Python env locally** (for quick checks): `/Users/pshirvalkar/miniconda3/envs/py313/bin/python`
  has numpy/scipy/sklearn/pandas. Container has the BRAVO-pinned versions (numpy 2.1.3, sklearn 1.5.2…).

## What we built
### Backend — `BRAVO/modules/Biomarkers/`
- `routines/streaming_psd.py` — time-domain PSD↔pain (verbatim from `biomarker_analysis_streaming.ipynb`).
- `routines/threshold_biomarker.py` — chronic sliding-window LFP threshold detector + KMeans
  `pain_level` labeler (verbatim from `threshold_biomarker.ipynb`).
- `routines/redcap_client.py` — REDCap PRO pull (PyCap; token via env vars).
- `routines/analytics.py` — visualization analytics (sliding-window AUC/R, ROC, LFP/Otsu histogram,
  cluster scatter, streaming corr-spectrum, PSD spectra/spectrogram) + `format_channel()`
  (contact numbers + cathode⁻/anode⁺ polarity + brain region).
- `adapter.py` — maps BRAVO recording dicts → routine inputs; PRO alignment; `merge_timelines`.
- `pipeline.py` — `run_biomarker(source="timedomain"|"chronic"|"both", ...)`.
- `bravo_service.py` — **Django-coupled** glue: loads a participant's decoded recordings + REDCap PROs,
  runs the pipeline, and serves JSON. Has demo-data paths. Also `pain_scores_for_participant()`.
- `requirements.txt` adds `PyCap`.

### Backend — API (`BRAVO/Server/APIs/`)
- `DataAnalysis.py`: `QueryBiomarkerAnalysis`, `QueryPainScores` (DRF views, `IsAuthenticated`).
- `urls.py`: `/api/queryBiomarkerAnalysis`, `/api/queryPainScores`.

### Frontend — `Client/src/views/Reports/`
- `Biomarkers/` — **Pain Biomarkers** card: source toggle (Time-domain/Chronic/Both), stacked-subplot
  timeline, and `BiomarkerAnalytics.js` (Time-domain section + Chronic section of Yiyuan's figures).
  Registered in `routes.js` under the **Customized Analysis** group; route
  `/reports/biomarkers/:participant_uid`.
- `PainScores/` — **Pain Scores** report under **Surveys & Questionnaires**; route
  `/pain-scores/:participant_uid`. Per-metric grid + normalized all-metric overlay (with metric
  toggles) + Pearson correlation heatmap (red=positive) + **trial stage** bands & global stage toggles.

### Local-dev auth (commits `efd6b02`, `6e72525`)
For the standalone local instance we relaxed auth (DEBUG only; production paths untouched):
`Server/authentication.CsrfExemptSessionAuthentication` (used in `settings.py` when `DEBUG`) fixed
the "You do not have the permission" login 403 (stale CSRF cookie), plus DEBUG-open participant
access + localhost CSRF/hosts.

## NEXT: load real patient data (the current goal)
1. **REDCap** — set on the `bravo-server` service env (compose), then `docker compose up -d`:
   - `REDCAP_API_URL`, `REDCAP_API_TOKEN`. (Currently NOT set → only demo data flows.)
   - The patient's REDCap **field map** lives in your `pt_config/<pt>_config.json`
     (`instruments`, `timestamp_label`, `metric_labels`, `program_dates`). The endpoints expect tidy
     columns `date_time_s1_daily`, `nrs`, `vas`, `left_leg_vas`, `back_vas`, `relief`,
     `mpq_sum/aff/sen`, `electrocuting`, `tingly`. **TODO:** wire `redcap_pull.py`'s processing
     (filter instrument + pivot) into `redcap_client`/`bravo_service` so raw REDCap column names map
     correctly. Until then you can POST `ProcessedPRO` (a list of tidy dicts) in the request body.
   - Trial **stages**: pass `Stages` in the request (or derive from `pt_config.program_dates`
     server-side). Demo uses `_demo_stages()`.
2. **Percept data** (for the biomarker time-domain/chronic, not needed for Pain Scores) — upload a
   Percept session JSON through BRAVO's normal upload flow for the participant, so `Recording` rows
   (types `MedtronicBrainSenseTimeDomain`, `MedtronicChronicBrainSense`) exist.
   `bravo_service._load_recordings` reads them.
3. Create/choose a **real participant** in the same institute as the login user (so access checks pass),
   navigate to the Biomarkers / Pain Scores reports, and validate. On real data, AUC/R won't be the
   demo's perfect 1.0.

## Known issue to investigate: slow uploads
Large Percept files (~73 MB) "spin" for ~a minute. Likely cause: the **single-threaded Django dev
server (`runserver`)** doing the **synchronous Percept JSON decode** (CPU-heavy) on upload, plus
macOS Docker bind-mount overhead. It's working, just slow. Options for the new session:
- Switch the `bravo-server` command to a real ASGI server with workers
  (`Docker/docker-compose.yml` shows a `daphne -p 3001 ... BRAVO.asgi:application` variant), or
- Offload decode to the existing `modules/AsyncJobScheduler` background processing, or
- Just upload fewer/smaller sessions to start. (nginx `client_max_body_size` is already 500M.)

## Quick API smoke (session/cookie path)
```bash
J=/tmp/j; curl -s -c $J -b $J -X POST -H 'Content-Type: application/json' \
  -d '{"Email":"demo@bravo.local","Password":"biomarker123"}' http://localhost/api/login
curl -s -c $J -b $J -X POST -H 'Content-Type: application/json' \
  -d '{"ParticipantId":"e30b54dc17d3488dbe1945bb911f5549"}' http://localhost/api/queryPainScores
```
