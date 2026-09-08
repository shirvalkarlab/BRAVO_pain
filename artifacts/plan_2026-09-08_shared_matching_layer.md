# Plan — the shared matched-sample cache (Layer 1), and migrating the four existing matchers onto it

Follows directly from `design_2026-09-08_biomarker_pipeline_and_closed_loop_deployment.md` §2-3
(decision 73) and the PI's go-ahead, 2026-09-08: *"plan out and build the consolidation with this
shared matching layer."* Check 7 (a randomized within-subject crossover) is explicitly out of
scope for this project and is not part of this plan.

## The split, restated concretely

**Layer 1 (new): one shared, settings-keyed cache** that answers "which pain report matches which
recording, and which samples count" — nothing about which statistic gets computed from the match.

**Layer 2 (unchanged): the four existing statistical treatments**, each kept exactly as it is
today, each simply reading its matched samples from Layer 1 instead of running its own matching
loop. No correction method, scale, or statistic changes for any of the four.

## The four existing matchers, and what Layer 1's schema must cover

Read directly from source, not from memory, before this plan was written:

| Mechanism | File | Tolerance | Direction | Independence rule |
|---|---|---|---|---|
| `per_pro_lsb` tiered precedence | `Biomarkers/routines/availability.py:1386` | 120 s, hardcoded | none | **none** |
| `live_lsb_spectrum_match` (calibrated sweep) | `Biomarkers/routines/availability.py:1837` | `MatchToleranceMin`/`MatchExtentSec` | nearest / prior / pro_first | `AllowWindowReuse` (default strict) |
| `align_pros(target="session")` | `Biomarkers/adapter.py:100` | `match_tolerance_min` | nearest only | **none** |
| `_match_to_pro` / `_forecast_match_direction` | `Biomarkers/routines/streaming_psd.py:592`, `Biomarkers/bravo_service.py:6547` | `tolerance_min` | pro_first / nearest / prior | explicit `max_per_rating` + `refractory_min` |

Layer 1's schema is the fourth mechanism's own shape — tolerance, direction, max-per-rating,
refractory — because it is already the richest of the four and closes decision 73's own finding
(two of four mechanisms allow a single recording or report to be claimed by an unbounded number of
matches, the same pseudoreplication shape decision 17's impedance term was rejected for).

## Track A — the Layer 1 module itself (build first; nothing else can start before this exists)

**A1. Write `BRAVO/modules/DecodeCommon/matching.py`** (a leaf module, like the rest of
`DecodeCommon` — small, stable, imported by every consumer, importing nothing from Biomarkers,
StimOptimizer or ClosedLoopDeployment, per `DecodeCommon`'s own dependency-direction rule).
Exposes one function, `matched_samples(pro_times, sample_times, sample_values, *, tolerance_min,
direction, max_per_rating=1, refractory_min=0.0)`, returning the canonical `(sample_value,
pain_value, sample_time, rating_cluster_id)` tuple list the design doc's Layer 1 box specifies.
Built as the richest existing mechanism's own algorithm (`_match_to_pro`), read and ported rather
than re-derived from scratch, then proven equal to `_match_to_pro`'s own output on constructed
fixtures covering all three directions and the refractory cap.

**A2. Write the cache key and the store wiring** in `ClosedLoopDeployment/adapter.py` (or a new
small `matching_cache.py` beside it, decided during A1 once the shape is clear): `settings =
{tolerance_min, direction, max_per_rating, refractory_min, sample_kind, band_center_hz,
sensing_contact}`, hashed the same way the calibrated sweep's own `sweep_settings` dict already is
(decision 26's own template, named for reuse in the design doc). Registered as raw-derived in
`provenance.RAW_KINDS` reasoning parallel to `therapy_pain_matched` (decision 37): the match itself
is a deterministic function of its inputs and settings, embodying no exploration choice, so
refusing it to a consumer would refuse the very table this layer exists to share.

**A3. Unit tests**: every direction (nearest/prior/pro_first) against hand-built fixtures with a
known correct match; the refractory/max-per-rating cap actually excludes a match that the same
fixture without the cap would allow (the regression test for the gap decision 73 found); a cache
round trip through the store, proven byte-identical on a re-request with the same settings
(decision 26's own `test_a_matching_key_leaves_the_directory_byte_identical` is the template).

## Track B — migrate the four call sites onto Layer 1, one at a time, each its own commit

Each step is independent of the others and each carries its own live equality proof — this is
where the real risk is, and where decision 73's own caution applies: reading a wrong cached match
silently is a no-crash, no-obviously-wrong-number failure, the exact class this project's rules
exist to catch. Order chosen by risk (settled to volatile matcher first is deliberately reversed
here — start with the one with NO independence rule, since it is the biggest correctness gap, not
the easiest port):

**B1. `align_pros(target="session")`** (`Biomarkers/adapter.py`) — currently allows one report to
match unlimited sessions. Wire it to Layer 1 with `max_per_rating=1` as this call site's default
(preserving today's *behavior* requires deliberately checking whether any live caller depends on
the unbounded-match behavior first — if one does, that dependency is itself a finding to report,
not silently changed). Live equality proof: full page response before/after, field count and
difference count.

**B2. `per_pro_lsb` tiered precedence** (`availability.py:1386`) — currently a hardcoded 120 s
tolerance with no independence rule. Same treatment as B1; this one feeds `run_for_participant`'s
main response, so the equality proof is the same byte-identical-response discipline used for
Track D steps 1-2 (decision 71).

**B3. `live_lsb_spectrum_match`** (`availability.py:1837`) — already the most parameterized of the
remaining three (has `AllowWindowReuse`), so this port is mostly a schema translation rather than a
behavior change. Live equality proof against the calibrated sweep's own stored response
(`biomarker_band_sweep`), same discipline as decision 38's own proof.

**B4. `_match_to_pro` / `_forecast_match_direction`** (`streaming_psd.py`, `bravo_service.py`) —
this is the mechanism Layer 1's own schema was copied from, so the port should be closest to a
pure delegation. Still gets its own equality proof, since "should be a no-op" is a claim to verify,
not assume (this project's own repeated lesson — Track A step 8's first live run wrote nothing
back while every test passed, decision 41).

Each of B1-B4 lands only after A1-A3 are committed and both test suites are green; each is its own
commit with its own field-count/difference-count numbers in the same report as any speed claim
(`ARCHITECTURE_cache_store.md` §7).

## Explicitly excluded from this plan

- **Check 7 (a randomized within-subject crossover)** — out of scope for this project per the
  user's own instruction; the design doc's decision 73 already recorded this and it is not
  reopened here.
- **Changing any of the four statistical treatments themselves** (Layer 2) — restated because it
  is the load-bearing constraint from §3.2 of the design doc, not a detail to lose track of during
  implementation.
- **The direction-consistency check's own wiring into `deployment_summary`** (decision 74) is a
  separate, already-built, standalone piece; nothing in this plan depends on it and it is not
  bundled into these tracks.
- **A user-facing settings UI for Layer 1's own parameters** — the design doc's own requirements
  mention this as a future nicety ("it would be nice if we could specify... using the levers and
  sliders"); this plan builds the cache and its schema, not a control panel, unless asked for
  separately.

## Dependency graph, in short

```
A1 -> A2 -> A3          (Layer 1 must exist and be proven before any migration)
         │
         ├── B1 (align_pros)                  — independent of B2-B4
         ├── B2 (per_pro_lsb)                 — independent of B1, B3, B4
         ├── B3 (live_lsb_spectrum_match)      — independent of B1, B2, B4
         └── B4 (_match_to_pro)                — independent of B1, B2, B3
```

B1-B4 can be built and reviewed in any order, or in parallel by separate sessions, once Track A is
committed — the risk in each is local to that one call site's own equality proof, not shared
between them.
