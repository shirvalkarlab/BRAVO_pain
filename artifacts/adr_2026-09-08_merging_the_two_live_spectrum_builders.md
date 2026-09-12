# ADR — whether, and how, to merge the two live spectrum builders

**Written 2026-09-08. Research and a plan only — no code changed by this document.**

## The question this document answers

Track D step 2 of the cache-store plan ("reduce the three spectrum builders") was left
deliberately unfinished: the one confirmed-dead builder was removed, but merging the two
genuinely live ones was flagged as needing its own sign-off first, because it touches the one
place in this codebase where a spectrum computation and a pain-correlation statistic are computed
in the same pass. This document is that investigation, done before asking for the sign-off rather
than after.

**The premise it was asked to check: do the two live spectrum builders produce identical data?**
Not quite, and the "not quite" is the whole shape of the answer below.

## The two builders, and what was actually found

**Builder A** — `bravo_service._assemble_psd_rows_cached` (the disk-cached per-recording spectrum
assembler, backing the 6,309-file `biomarker_psd_rows` directory findings.md §6j already named).
**Builder B** — `pipeline.run_timedomain_branch` → `streaming_psd.compute_psd_pain_correlation`,
the routine that runs on the main Biomarkers page every request, with no disk cache of its own.

**They call the same low-level function.** Both go through `streaming_psd._welch_rows_into`'s
family or directly through `streaming_psd.welch_psd_for_instance` — the identical Butterworth
high-pass filter, the identical 30-second truncation, the identical Welch window and 50 percent
overlap, the identical 101-point 0.95–100 Hz frequency grid, no mains notch on either path, and
(since decision 58) the identical dropped-packet rejection rule. For a given recording and a
given window, the two would compute a numerically identical spectrum. This part of the premise is
right.

**They do not ask for the same windows.** Builder A can produce more than one row per recording:
a plain first-30-seconds-of-session row, or — when pain reports are supplied — a **rating-centered**
row per pain report that overlaps the recording, a fresh window built around each report's own
timestamp rather than the session's start. Builder B never does this. It computes exactly **one**
spectrum per recording, always the first-30-seconds window, and matches the nearest pain report
onto that one spectrum afterward. Same recipe, different serving size — the row sets the two
builders produce are not interchangeable, even though the underlying arithmetic is.

## The statistics landscape is four analyses wide, not two

Reading what each builder's output actually feeds found four genuinely different downstream
treatments, confirmed by reading each one's own code rather than assumed from its name:

1. **Builder B's own pipeline** (`pipeline.run_timedomain_branch`) — the main page's headline: a
   naive and a cluster-robust (sandwich, rating-clustered) p-value computed side by side, an
   autocorrelation-adjusted p-value grid (effective-N, because daily pain is serially correlated),
   Benjamini-Hochberg band selection on that honest grid, a Fisher-z confidence interval, a
   stim-amplitude-adjusted partial correlation, an explicit sensitivity analysis against the
   MAD-filtered sample, and a rating-level block-permutation p-value as the actual reported
   significance — not the FDR q, which is a selection filter, not the headline number.
2. **`build_pooled_psd_detail`**, fed by Builder A's cached rows, shaped to match Builder B's
   output so `spectral_feature_importance` can consume either — but that consumer is its own,
   differently-scoped analysis: a 5 Hz sliding-window scan across the full spectrum in 1 Hz steps,
   defaulting to a **completely different** calibrated device-LSB feature (from a third cache,
   `_pro_lsb_spectrum_cached`, built off the transform DSP route, not the Welch route at all) with
   its own cross-validated-AUC and cluster-robust logistic Wald-p machinery, and explicitly
   documented as exploratory — "NOTHING here is a validated biomarker."
3. **`band_psd_lsb_conversion`**, also fed by Builder A's cached rows: a bootstrapped
   proportional-law regression fitting the device's own LSB units against microvolts-squared power.
   Not a pain-correlation statistic at all — a device calibration fit.
4. **The calibrated band-by-length sweep** (`analytics.py`), which decision 61 already ruled
   should not be folded into Builder B, for reasons that generalize directly to this question:
   different frequency coverage, different sample unit, different correction method, an AUC
   statistic the folded-into routine doesn't compute. That decision didn't examine Builder A at
   all — it compared Builder B against this fourth, unrelated routine — but its reasoning is the
   right template for the question this document actually answers.

None of the four are the same statistical question wearing different clothes. This project's own
established caution about folding differently-scoped analyses together — stated once already, for
a different pair — turns out to generalize to this pair too, once actually checked rather than
assumed.

## What is safe to do, and what is not

**Safe, and worth doing on its own, no sign-off needed:** formalize that the two builders already
share the same DSP primitive. They call it independently today; nothing documents that this is
intentional shared infrastructure rather than two teams having separately arrived at the same
Welch parameters. A small, behavior-preserving refactor — one named helper both call for the
missing-data-aware Welch invocation, proven equal by the same field-count/difference-count
discipline this project already applies everywhere — would make the sharing explicit without
touching either builder's window-selection logic or any downstream statistic. This is pure
housekeeping: it changes what the code says about itself, not what it computes.

**Not safe without the sign-off, and the reason is now specific rather than general:** wiring
Builder B to read Builder A's disk-cached rows (the original step 2 wording, "wire the others to
it"). Builder A's cache holds whichever row shape it was built for — a first-30-seconds row, or a
rating-centered row, depending on the call that populated it — and Builder B's own correctness
(the decision 58/59 missing-data fix, its own sorted-epoch and rating-group-identity construction)
depends on computing its own epochs fresh, on its own terms, every time. Reading a cache built for
a different purpose risks silently importing the wrong window per recording — not a crash, not a
wrong-looking number, just the headline statistic quietly computed from a different sample than
its own pipeline intends. That is exactly the failure class this project's rules exist to catch,
and exactly why the equality-proof discipline (field count and difference count on live data,
never a tolerance) would need to specifically watch for a shift in *which* window got used, not
merely whether the Welch arithmetic agrees.

## Recommendation

1. **Close the "reduce the three spectrum builders" step as done in its safe form only**, which it
   already is (decision 71): the dead builder removed, the two live builders left as they are,
   the connection between them explicitly not made.
2. **If the shared-DSP housekeeping is wanted**, it can be done now, independently, with no
   statistics decision attached — a small, low-risk refactor with its own equality proof, the same
   shape as every other change this project has made to this code.
3. **Do not connect Builder A's cache to Builder B's live path.** The investigation this document
   is built on did not find a case for it — the two builders answer different questions on
   purpose, matching this project's own precedent for the adjacent question it already decided.
   If there is a reason to want this beyond "the plan said to" — a specific measured cost Builder
   B's live recomputation imposes that the cache would remove — that would be a new, narrower
   question with its own measurement, not a resumption of this one.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
