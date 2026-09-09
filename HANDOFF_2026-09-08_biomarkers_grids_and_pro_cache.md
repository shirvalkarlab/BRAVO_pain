# Handoff — the Biomarkers grid work, and what the next session should know

**Written 2026-09-08.** Branch `PS_closedloop_deployment`. **The next session's stated goal is to
polish, optimise and clean up the visualisation and engineering for closed-loop deployability.**
This document is what that session needs from this one; it does not restate the reference documents.

---

## 0. Read these first, in this order

1. `CLAUDE.md` §10 — the rules that override everything, including that a plan is not permission.
2. `HOUSE_RULES_writing_and_claims.md` — before writing any reply, report or commit message.
3. `DECISIONS_and_open_items.md` — **decisions 77 and 78 are this session's**, and **decision 22 is
   now struck through as amended by 78**. Read all three together; 78 is a deliberate, bounded
   exception and its own row says exactly what it does and does not claim.
4. `.planning/2026-09-08-biomarkers-heatmap-plotting-redesign/` — this session's plan, findings and
   progress, in the `planning-with-files` shape. All six phases report complete.

**The cache-store plan is a different, older task** (`.planning/2026-09-06-cache-store-and-record-consolidation/`).
`.planning/.active_plan` now points at the new one. Do not merge them.

---

## 1. What changed in the code, and where

| File | What changed |
|---|---|
| `Biomarkers/bravo_service.py` | `spectral_feature_importance` removed from `td_tasks`; `pro_lsb_spectrum_by_channel` removed from `_compute_analytics`; new `_RECORDINGS_SETUP_MEMO` + `_recordings_setup_cached`; new `_PRO_BUILD_CACHE` + `_remember_pain_reports` + `_pain_reports_for_drilldown`; the grid build and the cell drill-down now share the recordings memo |
| `Biomarkers/adapter.py` | `align_pros(target="session")` migrated onto `DecodeCommon.matching.matched_samples` (earlier in this session — see §4) |
| `Biomarkers/BiomarkerAnalytics.js` | the `SpectralFeatureImportance` component (~600 lines) and its render deleted; the wrapping section's title/subtitle rewritten, because it described the removed scan's own methodology |
| `Biomarkers/BiomarkerHeatmapGrids.js` | the two grids enlarged: stacked full-width, taller rows, larger ticks, and **axis titles that did not exist before**; `viewBox` + `width="100%"` so they scale rather than overflow |
| `Biomarkers/index.js` | dead `UseLiveMatching` removed; new live `NativeLsbToleranceSec` knob; `MatchExtentSec` debounce gap fixed; matching controls grouped under one heading |
| `DECISIONS_and_open_items.md` | decisions 77 and 78 added; decision 22 struck through and amended |

**The frontend bundle in `Client/build/` was rebuilt and is committed with the source.** The axis
title string was confirmed present in the served chunk. Do not commit a source change here without
rebuilding — that has cost this project a whole panel once already (`OPERATIONS_runbook.md` §4).

---

## 2. The performance rule that now governs the pain reports (decision 78) — READ BEFORE TOUCHING IT

The PI amended decision 22 directly. The rule, in his framing: **once the Biomarkers module has
loaded and everything is on screen, the pain-report table is held; it is fetched again only when
someone presses Recompute, or the page's data is computed from a new load.**

**The mechanism has no clock in it.** `_load_pros` hands every real fetch to
`_remember_pain_reports`, so `_PRO_BUILD_CACHE` is always "whatever the most recent real fetch
produced". Every endpoint that BUILDS something still fetches fresh, and by doing so re-seeds it.
Only the hover preview and the pinned cell panel read it back. **That is the whole invalidation
rule — a build replaces the entry, and nothing expires it.**

**What decision 22 was right about, and still is.** There is no cheap freshness check available.
`_pro_table_digest` hashes the table AFTER the fetch, so it can dedup a write but can never save a
fetch, and REDCap offers no metadata-only "has anything changed" call this codebase can ask. 78 buys
speed by accepting a bounded, disclosed staleness — **a rating filed while a grid is already on
screen does not reach a hover preview until the next build** — not by finding a free check. If a
future session is tempted to "just add a freshness check", read this paragraph again first.

**Four gunicorn workers means four independent caches.** A hover landing on a worker that has not
built for that participant fetches once and seeds itself. Self-healing; needs no cross-worker
invalidation. Do not add one without a measured reason.

---

## 3. Measurements, so nobody has to re-derive them

All on live RCS08 through the bridge.

| Thing | Before | After |
|---|---|---|
| One hover / click-through cell request | ~2.9 s, every time | 0.024–0.053 s after the build |
| REDCap fetches per grid build | 1 | 1 (unchanged, by design) |
| REDCap fetches across six hovers | 6 | **0** |
| REDCap fetches on Recompute | 1 | 1 (unchanged, by design) |

Where the original 2.9 s went, timed per step: `_load_recordings`(TD) 1.27 s, REDCap 0.65 s,
`_load_recordings`(PSD) 0.38 s, `_event_psd_lsb_blocks` 0.33 s. **The LSB tile cache was already
fast at 0.013 s and was never the problem** — a hypothesis worth killing early if it resurfaces.

**Equality proofs (field count and difference count, never a tolerance):**
- Panel removal: 254,741 fields removed, every one under `timedomain.*`; **0 of 7,150,676 common
  fields changed value.**
- Held-table hover vs forced fresh-fetch hover, identical cell: 1,335 fields, **0 differences**.
- Grid build, two genuinely fresh builds with the store bypassed on both sides: 27,865 fields,
  **19 differing, every one a wall-clock `*_seconds` timing field.**
- Container suite **593 passed, 0 failed** after every change. Biomarkers has no host-suite
  membership, so the container suite is the only one that applies to this work.

---

## 4. Work that is finished but NOT yet closed out

**The shared matching layer, Track B.** `DecodeCommon/matching.py` (decision 76) exists and its
Layer 1 is proven. Of the four call sites it was meant to absorb:
- `align_pros(target="session")` — **migrated this session**, in `adapter.py`, uncommitted until the
  commit carrying this handoff. A real bug was found and fixed during it: `.to_datetime64()` on a
  Timestamp built from a plain `datetime` gives MICROSECOND resolution in pandas 2.x, so casting to
  int64 and dividing by 1e9 read microseconds as nanoseconds — **a silent 1000x error** that would
  have massively widened the effective match window. Forcing `.astype("datetime64[ns]")` first fixes
  it. Residual after a reference-epoch precision refinement: 171 of 7,405,417 fields differ at
  ~1e-12 minutes, the float64 floor. Reported rather than hidden.
- `live_lsb_spectrum_match` and `streaming_psd._match_to_pro` — **not migrated.**
- `per_pro_lsb` — **deliberately not migrated, and the reason matters.** Its matching is a
  three-tier source precedence (native sensed → rating-centred TD-transform window → PSD-bridge
  coincidence), and **only tier 1 is the kind of nearest-neighbour-within-tolerance operation
  `matched_samples` models.** Forcing tiers 2 and 3 through it would either warp the shared layer or
  migrate a third of the function and call it done. The PI has not ruled on this; it is open.

---

## 5. What is NOT verified, stated plainly

- **No logged-in browser check of the finished page.** This session's browser tool opens a fresh
  sandboxed browser per call and could not hold a login; registration and the study-join code path
  both stalled. The demo credential the PI supplied (`demo@bravo.local`) arrived after those
  attempts and was never exercised end to end. **So: the grids are proven correct by data and by
  the served-chunk check, but nobody has looked at them.** That is the first thing the next session
  should do, and it is cheap now that a credential exists. **`OPERATIONS_runbook.md` §4 now ends
  with how to sign in** — ask the PI for the demo password rather than registering a new account,
  and read the paragraph there about why a fresh account cannot see RCS08 at all.
- **The "one big pre-joined matrix"** the PI floated — one table joining TD, PSD, LSB, timestamps
  and the matched pain report for direct lookup — was **not built**, on the recommendation that with
  hovers at ~30 ms the join it would eliminate is no longer measurable, so it would add a new cache
  shape and a new invalidation surface for no observable gain. **This is his call to make, not a
  closed question.** It may still be worth it as a substrate for *further analysis* rather than for
  plot speed, which is a different argument and was not evaluated.

---

## 6. Two findings parked for the next session, both real

1. **`SlidingWindow` is a dead frontend knob that still gates real backend computation.** In
   `index.js` it is a hardcoded `const slidingWindow = false` with no setter — nothing can ever
   change it — yet it is sent on every request and `_window_params_body` branches on it. Unlike
   `UseLiveMatching` (removed this session, which was inert), **this one has real computational
   effect**, so removing it is a behaviour decision, not a cleanup. Untouched deliberately.
2. **`compute_psd_pain_correlation` is computed on every request and reaches no visible UI.**
   `pipeline.run_timedomain_branch` runs the full per-channel/per-frequency correlation grid, then
   collapses it to one FDR-selected band written onto the timeline as `td_biomarker_*`. The only
   consumer of `td_biomarker_value` is `BiomarkerTimeline.js`, **the legacy fallback timeline that
   only renders when the modern availability payload is missing** — which, in normal operation, it
   never is. So a full correlation grid is computed and thrown away on every request. Worth a
   decision; not touched here because it is unrelated to the visualisation work.

---

## 7. Straight into the next goal: closed-loop deployability

Things this session touched that bear directly on it:

- **The calibrated band-by-length grid is the headline result and now the only scatter/violin path
  on the page.** The duplicated exploratory scan is gone, so there is one number per cell and one
  place it comes from. That is a better starting point for a deployability view than what existed
  this morning.
- **`ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop`** already reads the stored grid
  as `consumer="closed_loop"` (decision 67). The export button in `BiomarkerHeatmapGrids.js` is
  still gated on a field check and **may now be lightable** — it was written before Track D landed
  and deliberately stays disabled until the field it looks for exists. Worth checking first; it is
  possibly a one-line win.
- **Decision 67's open item 10 is still open**: the device-rules screen cannot be evaluated from a
  (contact, band centre) pair alone, and the neutral "not assessable from a band alone" note that
  shipped instead needs the PI's ruling on whether it is the final answer.
- **The honest four-valued stability translation** (`stability.finding_from_stability_result`) is on
  the Closed-Loop side and expensive (315 s for a full grid with it on, against 5.7 s off), which is
  why it is off by default. Any deployability view that wants it must decide where that cost lands.

---

## 8. Repository state at the time of writing

- Everything described here is committed on `PS_closedloop_deployment` in the commit carrying this
  file. **Count commits ahead of the remote with `git rev-list --count origin/PS_closedloop_deployment..HEAD`
  rather than trusting a number written here** — numbers in documents in this project have gone
  stale inside a single session.
- **`.gitignore` blanket-ignores `HANDOFF_*.md` with negations appended.** This file was checked
  with `git status` to confirm it is actually tracked. If you add another handoff, check the same
  way; an untracked file survives only until someone runs `git clean`.
- Scratch probes were written under `BRAVO/_agent_bridge/_*` (gitignored) and deleted after use.
  A throwaway venv at `/tmp/plotly_venv` holds plotly + kaleido, used to render a figure from real
  data without a browser — a genuinely useful trick when the browser tool cannot hold a login.
