# BRAVO Pain Biomarker — Session Handoff (2026-06-23 ~16:15)

## State at handoff
- **Repo:** `/Users/pshirvalkar/dev/BRAVO_pain`  **Branch:** `PS_biomarker_module`  **HEAD:** `b870b3f`
- **Bridge cwd inside container:** `/usr/src/BRAVO`  **RCS08 uid:** `2e3c75c00d7f4f37b53a048d195f11da`
- **Backend test suite:** 125/125 green  •  **Latest frontend bundle:** `main.43075266.js`  •  tracked tree clean
- Backend reloaded (`kill -HUP 1`) so the live server runs the fixed code.

### Operating loop (stateful bridge)
```
cd BRAVO/_agent_bridge && python3 bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
# run tests:   python3 _agent_bridge/run_tests.py
# reload:      kill -HUP 1
# frontend:    cd Client && env CI=false GENERATE_SOURCEMAP=false npm run build
# commit:      git -c user.name="Prasad Shirvalkar" -c user.email="prasad.shirvalkar@ucsf.edu" commit ...
```

## What shipped this session (8 commits, a6b6eb4 → b870b3f)
Drove the 4 audit review docs (FIXHANDOUT_MASTER, PARITY, FRONTEND, FIXHANDOUT_pro_timezone).

| Commit | What |
|---|---|
| `c46efd8` | `.gitignore` for `_agent_bridge/` one-offs; tracked `run_tests.py` |
| `208c3e4` | **#1 (HIGH)** stim-era LOCF (was next-sample) + ISO8601 parse (a naive parse was NaT-ing 83% of sample times) |
| `640746d` | **#2 (MED)** glmer + stim-stability click-validate parity: per-channel binarization, elapsed-week cluster, ddof=1, sep-guard `\|beta\|>50`, stim-LRT manual chi2 df=n_eras-1 |
| `6278226` | **#4/#5/#7** slider gate on `pro_first`, empty-state copy, histogram purge unmount-only |
| `626aba8` | **#3 (MED)** PRO timezone normalized at ingestion: `_load_pros` adds canonical `_pro_time_utc`; readers route through `_pro_times_utc_series` |
| `ff0f16f` | **FEATURE** pain matched/unmatched + class-color overlay on timeline pain row (`painMatched` field) |
| `c0654e7` | **#6/#8/#9/#10** binByKey collision precedence, abbreviations spelled out, region map de-hardcoded, stale 44/682→290/682 comment |
| `b870b3f` | **#3 follow-up** live preview count was STILL 61/682 — see below |

## The #3 follow-up (important — was the user-visible bug)
The "61 of 682 paired" in the live binarization preview was a **second surface** of the tz bug.
Fix #3 corrected the timeline pain ROW + scan pool (epoch-seconds), but the preview COUNT is computed
**client-side** in `index.js` from `/api/queryPainScores`, which carried only a tz-naive UTC string.
The client did `Date.parse(p.t)/1000` → re-read in the **browser's local (Pacific)** zone → every
rating shifted +7 h → ~3/4 of matchable PROs fell off the PSDs.
- **Fix:** backend now emits numeric `t_epoch` (UTC seconds, `tt.value/1e9`) on every pain point;
  `painSeriesLive` matches on `t_epoch` (Date.parse fallback only for old payloads); composite path
  carries it through.
- **Proven on RCS08** (left_leg_vas, pro_first, ±60min, cap1): `t_epoch` UTC → **264** matched;
  Date.parse-local(−7h) → **55** (reproduces the screenshot's ~61). Overall VAS lands near 290.
- Regression test `test_pain_scores_emit_utc_t_epoch`.

### ⚠️ NEXT SESSION — first action: user verification still pending
The user has NOT yet confirmed the live number in the browser. Ask them to **hard-refresh** (new
bundle `main.43075266.js`) and confirm Overall VAS at ±60 min now reads ~290/682. If it does NOT:
suspect (a) browser cached the old bundle, or (b) another `Date.parse`/`new Date(p.t)` consumer of
`/api/queryPainScores` — note `PainScores/index.js` (the separate Pain Scores report page) still
does `Date.parse(p.t)` for stage-window membership; it was left untouched this session and may show
the same −7/−8 h drift on that page. Verify whether that page needs the same `t_epoch` treatment.

## Known honest caveat (not a bug)
**VAS@61.5 Hz** stim-stability verdict reads *dependent* live (LRT p≈0.048) vs the offline report's
*stable* (p≈0.127). Proven NOT a parity bug: the offline method on the live pooled detail gives the
identical live chi2 (6.075). The 3-era model is singular (HIGH era n=17); live vs the frozen offline
bundle differ only by lme4 optimizer vintage on a degenerate p≈0.05 fit. Leave as-is.

## Carried-forward open threads (from Wave-2, not yet done)
- High-freq (54–87 Hz) stim-artifact / recording-trigger scrutiny — 84.5 Hz demo anchor sits OFF the
  8–30 Hz adaptive band (correctly flagged non-deployable but remains the demo anchor). Refit with a
  `source` random intercept was suggested.
- 5 narrow-Wald-CI v2 candidates need a 500-iter cluster bootstrap.
- Composite-metric statistical power problem.
- Only `date_time_s1_daily` is normalized at ingestion; REDCap delivers other timestamp columns
  (`stage_0_mini_vas_timestamp`, etc.) — any metric whose time comes from a different column has the
  same latent 7–8 h bug. `_normalize_pro_times` currently pins one column name.

## Key code locations
- `bravo_service.py`: `_load_pros`=1093, `_load_pros_raw` (wrapped), `_normalize_pro_times` + `_PRO_TIME_UTC_COL`
  (~after `_pro_timestamps_utc` @1534), `_pro_times_utc_series`, `_pro_match_arrays`, `pain_scores_for_participant`
  (t_epoch emit ~3186), `DEFAULT_MATCH_TOLERANCE_MIN`=60
- `availability.py`: `pain_series`=177 (reads `_pro_time_utc`, epoch via view int64/1e9)
- `adapter.py`: `combine` ~134 (prefers `_pro_time_utc`)
- `index.js`: `painSeriesLive`=~252 (matches on `t_epoch`), composite synth ~215
- `binarizationModel.js`: `proSorted[].i0` capture, `painMatched` build, binByKey collision precedence ~273
- `BiomarkerDataTimeline.js`: pain-row markers (closed/open + class color) ~596, region resolver in lane header, `HEMI2` (no hardcoded region) =126
