# A common pipeline for biomarker discovery, and the most reliable path to closed-loop deployment

**Written 2026-09-08. A design document and a literature-grounded recommendation, not a build —
nothing here has been coded.** It answers four things asked together: the narrow question left
open by the merging-spectrum-builders ADR, a design for a common matching-and-statistics pipeline
with user-set parameters cached by their own signature, the cost and benefit of building it, and
the scientific question underneath all of it — what is the most useful and reliable method to
deploy a Biomarkers finding to closed-loop control on the device.

Two research passes fed this: a full code-level map of every deployment gate and every existing
pain-report-matching mechanism, and a PubMed-grounded review of what published closed-loop DBS and
N-of-1 trial methodology actually require before trusting a biomarker to drive stimulation. Both
are cited throughout rather than summarized once at the top, per this project's own rule that a
claim and its evidence belong in the same place.

---

## 1. Requirements

**Functional.** A researcher exploring RCS08's recordings needs to try different ways of matching
a pain report to a recording (how close counts as "near," which direction, whether one recording
may serve more than one report) and different ways of turning matched samples into a statistic
(which correction, which effect size), see the result quickly, and come back to a parameter
combination already tried without paying for it twice. A clinician deciding whether to program a
band onto the device needs one page that states, honestly, whether the evidence for that band
clears every check that matters — never a page that reads as ready because a check could not run.

**Non-functional.** Above both of those: the stored numbers must be correct, and a change to how
one is produced must prove, on live data, that it did not move (this project's Core Principle 2,
restated in every decision this session). The participant is one person (N=1) with autocorrelated,
visit-clustered pain ratings — not a between-subjects trial, and the statistics have to fit that
shape, not borrow one that doesn't.

**Constraints, found by direct code reading (Part 2 of the investigation, full detail in §3
below).** Four separate mechanisms already match pain reports to recordings, each with its own
tolerance, its own (partial) direction control, and its own independence rule — two of the four
have **no** independence rule at all: a single recording, or a single pain report, can be claimed
by an unlimited number of matches. The device accepts exactly one threshold, on one band, at one
sensing contact, inside an 8-30 Hz range — closed-loop control is a single-number decision, however
much statistics went into choosing it.

---

## 2. High-level design

The insight the earlier ADR (`adr_2026-09-08_merging_the_two_live_spectrum_builders.md`) landed
on generalizes past just those two builders: **the part of this pipeline that is genuinely shared
across every routine is matching a pain report to a recording and deciding which samples count.
The part that must stay separate is what statistic gets computed from the matched samples**, because
the four existing routines answer four different scientific questions (raw Welch power vs
calibrated device-LSB; cluster-robust-and-autocorrelation-adjusted correlation vs
permutation-and-bootstrap-corrected sweep vs cross-validated AUC scan vs device-unit calibration
regression) and forcing one correction method onto all four would silently misrepresent at least
three of them.

So: one shared layer for matching, one separate layer per routine for statistics.

```
 ┌─────────────────────────────────────────────────────────────────┐
 │  LAYER 1 — the matched-sample cache (NEW)                        │
 │  Inputs: participant, recordings (via channel_index, Track D),   │
 │  pain-report snapshot, and the match SETTINGS a user picked:     │
 │  tolerance, direction, window-reuse, max-per-rating/refractory,  │
 │  binarization strategy.                                          │
 │  Output: one canonical list of (band-power sample, pain value,   │
 │  timestamp, rating-cluster id) tuples, per (channel, band).      │
 │  Cache key = every one of those settings, the same discipline    │
 │  the calibrated sweep already uses (decision 26: the key         │
 │  decides whether to write, not the caller).                      │
 └─────────────────────────────────────────────────────────────────┘
                 │                    │                   │
                 ▼                    ▼                   ▼
 ┌───────────────────────┐ ┌──────────────────────┐ ┌────────────────────┐
 │ LAYER 2a               │ │ LAYER 2b              │ │ LAYER 2c            │
 │ compute_psd_pain_      │ │ calibrated band-by-   │ │ spectral_feature_   │
 │ correlation's own      │ │ length sweep's own    │ │ importance's own    │
 │ chain: cluster-robust  │ │ chain: permutation +  │ │ chain: cross-        │
 │ p, autocorrelation-    │ │ bootstrap + AUC,      │ │ validated AUC,       │
 │ adjusted p-grid, BH-   │ │ BH-FDR across 22      │ │ cluster-robust        │
 │ FDR, block-permutation │ │ centres               │ │ logistic Wald p       │
 └───────────────────────┘ └──────────────────────┘ └────────────────────┘
```

**This directly answers the narrow question.** Connecting Builder A's disk cache to Builder B's
live path was the risky direction because Builder A's cache holds whichever window it happened to
be built for, and Builder B's own correctness depends on computing its own window, on its own
terms, every time — reading the wrong cached window silently, with no crash and no obviously wrong
number, is exactly the failure class this project's rules exist to prevent. **The fix is not to
connect the two existing caches to each other; it's to give both a new, shared cache keyed on
their own match settings.** A read only ever returns a hit when the settings genuinely match,
by construction — not by hoping the cache was built for the same purpose. When Builder B's
session-level, first-30-seconds setting and Builder A's rating-centered setting differ (as they
do today), they simply produce two different, correctly separate cache entries. The sharing
happens exactly when it's safe to happen, and nowhere else.

---

## 3. Deep dive

### 3.1 What already exists, and what is genuinely reusable

Four matching mechanisms exist today, and reading their actual parameter surfaces (not their
names) shows they are three variations on the same two knobs — a tolerance radius and a direction
— plus, in two of the four, an independence rule that the other two lack entirely:

| Mechanism | Tolerance | Direction | Independence rule | User-settable today |
|---|---|---|---|---|
| `per_pro_lsb` tiered precedence | 120 s, hardcoded | none | **none** — one source can serve unlimited reports | No |
| Calibrated sweep's `live_lsb_spectrum_match` | `MatchToleranceMin` / `MatchExtentSec` | nearest / prior / pro_first | `AllowWindowReuse` (default strict, one window per report) | Yes |
| `align_pros(target="session")` | `match_tolerance_min` | nearest only | **none** — one report can match unlimited sessions | Partial (tolerance only) |
| `_forecast_match_direction` / `_match_to_pro` | `tolerance_min` | pro_first / nearest / prior | explicit refractory-gapped cap (`max_per_rating`, `refractory_min`) | Yes — the most fully parameterized of the four |

This table is itself a finding worth acting on independent of everything else in this document:
**two of the four production matching paths have no rule at all against one recording or one
report being claimed by an unbounded number of matches**, which is a form of pseudoreplication —
treating dependent samples as independent — that this project's own house rules elsewhere call out
by name as a real, previously-caught error (decision 17's impedance term, significant under a
naive fit and not once grouping was accounted for).

A single shared matching layer, with the fully-parameterized mechanism's own shape (tolerance +
direction + max-per-rating + refractory, the richest of the four already) as the schema, would
close that gap everywhere at once rather than patching two call sites separately.

### 3.2 What is NOT reusable, and should not be forced

The downstream statistics stay four separate treatments — restated from the earlier ADR because
it is the load-bearing constraint on this whole design: Builder B's own headline is a
cluster-robust, autocorrelation-adjusted, FDR-selected, block-permutation-corrected p-value on raw
Welch power over the continuous spectrum; the calibrated sweep corrects by permutation and
bootstrap over 22 fixed, device-relevant centres and computes an AUC statistic the other routine
never does; the sliding-window scan defaults to a third, differently-calibrated feature and
explicitly labels itself exploratory; the calibration regression isn't a pain statistic at all.
None of that changes here. What changes is only where the **matched samples** those four
treatments start from come from.

### 3.3 A gap the literature review found, not previously identified in this project

Reading how a within-visit causal check (does raising current raise or lower a band's power,
inside one recorded ladder — already built, decisions 40/55/56) relates to a cross-visit
correlation check (does that band's power track pain across visits — already built, decision 38)
surfaced a genuine, currently-missing consistency check: **nothing today automatically confirms
the two point the same direction.** If a band rises with pain (so the control law would want to
push its power down) but the within-visit dose-response shows raising current also raises that
band's power, the two analyses disagree, and that disagreement is the concrete, checkable form of
the "does the device chase its own tail" problem this project's own `ClosedLoopDeployment/
stability.py` docstring already names as the reason cross-setting stability is checked at all.
Both inputs this check needs are already computed; nothing about it requires new statistics, only
a comparison that isn't run yet.

---

## 4. Scale and reliability — the most useful and reliable method to deploy for closed-loop control

**Short answer, stated plainly: a band is ready to drive closed-loop stimulation only after it
clears eight checks, in order, five of which this project has already built and proven on RCS08,
one of which is a small, buildable addition using data already computed, one of which is a new
individual-level threshold this project can compute from its own stored ratings, and one of which
— a randomized, within-subject test that closing the loop actually helps — genuinely cannot be
answered by any amount of further engineering, because it is a clinical trial design question, not
a code question, and because this project's own README states there is no interface that writes
to the device at all.**

| # | Check | Method | Status |
|---|---|---|---|
| 1 | The band moves with stimulation, reproducibly, within visits | Pooled, cluster-robust curvature test on rising/falling current ladders, ≥2 independent visits, on the one-sided (post-peak) stretch when curved | **Built** — decisions 40, 55, 56 |
| 2 | The band tracks pain, out of sample | Forward-chaining validation, fit on past visits, tested on future ones, never re-folded | **Built** — decision 12, which already caught two bands whose in-sample estimate reversed out of sample (26.4 Hz: 0.55→0.24; 8.8 Hz: 0.52→0.37) |
| 3 | Checks 1 and 2 agree on direction | Compare the sign of the within-visit dose-response against the sign the cross-visit correlation implies | **Not built.** The concrete, checkable form of the stimulation-artifact / "chases its own tail" confound this project's own code already names as the reason cross-setting stability matters |
| 4 | Correction for testing many bands and contacts at once | Benjamini-Hochberg FDR, independently per grid, never pooled | **Built** — decision 63 |
| 5 | Honest intervals under autocorrelated, visit-clustered ratings | Moving-block bootstrap with effective sample size; cluster-robust, visit-grouped standard errors; reported as a signed, de-folded lower bound, never a bare point estimate | **Built** — decisions 7, 8, 17, 19, 55 |
| 6 | The effect is big enough to matter **for this one person** | An individual reliable-change threshold from RCS08's own historical same-condition rating variance, with the population benchmark (≈2 points / ≈30% on the 0-10 scale, Farrar et al. 2001) reported only as a secondary, explicitly group-derived cross-check | **Not built** — a new analysis, using ratings this project already stores |
| 7 | Closing the loop on the band actually helps, causally | A randomized, within-subject crossover — short alternating blocks of biomarker-driven versus fixed stimulation, analyzed as a paired contrast (the N-of-1 trial methodology of Kravitz, Duan &amp; Schmid 2013; the closest published template for chronic pain specifically is the PREEMPT protocol, Barr et al. 2015, *Trials*, 10.1186/s13063-015-0590-8) | **Cannot be built here** — a clinical protocol decision, not a code change; this repository has no device-write interface at all |
| 8 | Re-check on a schedule, not once | Repeat checks 1-3 on a fixed interval or after any programming change, with an explicit stop rule if a previously-passing check stops passing | **Partially built** — the three-state gate (decision 9: pass/fail/indeterminate, never green on absent evidence) has the right shape; nothing yet re-runs it on a schedule |

**Why this ordering, and why "most rigorous" isn't automatically "most useful."** Checks 1-5 and
their proofs are, on the evidence gathered, *more* rigorous than what has been published for
Parkinson's beta-band adaptive DBS specifically — the strongest published human aDBS programs (the
Stanford/UW beta-burst work, Wilkins et al. 2025, *Brain Communications*,
10.1093/braincomms/fcaf266) treat one calibrated lab session, under four randomized conditions, as
feasibility evidence and say so explicitly, reserving chronic validation as future work; no
published aDBS-for-Parkinson's paper found in this search ran a forward-chained, held-out
statistical validation before a lab session. This project already does. The one place the
published field is unambiguously ahead is check 7: the NeuroPace RNS pivotal trial (Morrell 2011,
*Neurology*, 10.1212/WNL.0b013e3182302056) is built on exactly this shape — an individually
hand-tuned detector, established first, then tested by randomizing patients to responding versus
sham over 12 weeks (37.9% vs 17.3% seizure reduction, p=0.012) — and that randomized test of the
causal claim is the one thing missing here. **The most useful and reliable method, therefore, is
not a single statistic — it is this ordered protocol, with the engineering pieces (1, 2, 4, 5
already built; 3 and 6 straightforward additions) feeding a candidate list into the one piece that
has to happen outside this codebase (7), repeated on a schedule (8) rather than trusted once.**

One further, RCS08-specific risk the literature review surfaced and that no published aDBS-for-PD
work addresses, because it doesn't arise the same way in that population: stimulation settings in
this trial are changed by clinical judgment, sometimes *because of* how the patient is doing. If a
clinician raises current when pain is worse, "stimulation setting" and "pain state" become
confounded through the clinician's own decisions, independent of any direct electrical
relationship. Check 3 above is the direct test for this — a band whose cross-visit correlation
with pain is actually just tracking correlated clinical decisions would very plausibly disagree in
direction with its own within-visit, current-imposed dose-response.

---

## 5. Trade-off analysis

**Cost of building the shared matching layer (§2-3).** Real engineering effort proportional to
what Track D just finished, times roughly four call sites instead of two: a canonical matched-
sample schema (which itself needs a decision — Welch power, calibrated device-LSB, and the sliding
scan's third feature source are not the same physical quantity, so the schema needs a
quantity/method field, or this becomes two shared layers rather than one; that is a design
question this document surfaces rather than resolves). Each migrated call site needs the same
equality-proof discipline as every change this project has made — live field-count and
difference-count comparisons, not a smaller bar because the change is "just plumbing." Exposing
match settings as sliders on the exploration page also runs against the page's own very recent
redesign choice (decision 62, Option 2, "search-first, minimal chrome") — more configurability is
more surface area exactly where the last redesign deliberately removed it, and that tension is
real, not cosmetic.

**Benefit.** Removes a currently-real correctness risk (two of four matching mechanisms have no
independence rule at all, §3.1) in one place instead of four. Makes "does band X survive under
match rule A vs match rule B" directly, honestly comparable — genuinely useful for exactly the kind
of exploration this tool exists for. The caching-by-signature part has already, empirically, been
worth building once (the calibrated sweep's own settings-keyed cache: an unchanged request served
in ~3 s against ~6 s fresh on RCS08, decision 38) and would extend that same, already-proven value
to the other three routines.

**What I'd revisit as this grows.** If the canonical schema turns out to need per-quantity
variants (Welch power vs calibrated LSB vs the sliding-scan's own feature), that's not a reason not
to build it — it's a reason to build two shared layers instead of one, which is still a real
reduction from four independent matching implementations. If checks 1-3 above start disagreeing
often rather than rarely, that's information about how confounded this specific dataset actually
is, not a reason to weaken the check.

---

## 6. Recommendation

1. **Do not connect Builder A's cache to Builder B's live path directly** — unchanged from the
   earlier ADR, and now more specifically: replace that question with building the shared
   matched-sample cache instead, which gets the sharing safely.
2. **Build check 3 (§4) first, on its own, independent of everything else in this document.** It
   is small, uses data already computed, and answers a real, currently-open safety question about
   every band this project has looked at so far.
3. **Build check 6 (§4) next** — an individual reliable-change threshold from RCS08's own rating
   history, alongside (not instead of) the published population benchmark.
4. **The shared matching layer (§2-3) is a real, worthwhile consolidation, not an urgent one** —
   scope and cost estimate above; the two independence-rule gaps it would close are the most
   concrete reason to do it, separate from any speed benefit.
5. **Check 7 needs a decision from the clinical team, not from this codebase** — named here so it
   isn't silently assumed to be someone else's problem indefinitely.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
