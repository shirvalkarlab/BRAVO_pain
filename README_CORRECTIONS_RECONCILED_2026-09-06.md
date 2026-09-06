# `README_CORRECTIONS_SUMMARY.md` re-checked against the code — 2026-09-06

That document is dated **2026-06-29** and closes with "Current HEAD: `cd09845`". There have been
**103 commits since**, several of them tonight and one of them changing the very thing its own
closing note flagged as a risk. Every one of its six corrections was re-checked against the code as
it stands now. The verdict in one line: **all six are substantively still true, every one of their
code citations has moved, one of them describes machinery that no longer exists, and the single
biggest change since it was written is absent.**

---

## The one real conflict

### Correction 5 — "Mixed-Model & Forward-Windows Workflow"

It documents two things that no longer describe the code.

**"Forward-windows validation — temporal cross-validation across folds, gate AUC > 0.60".** There is
no such gate. Searching the whole `Biomarkers` package for a 0.60 threshold on an area-under-the-curve
value returns nothing; the only surviving `0.60` is `sep_pain >= 0.60` at `Biomarkers/pipeline.py:1475`,
which is a **separation** threshold in a different pipeline and not a gate on bands. Anyone reading
the README to learn how candidate bands are screened would look for a gate that is not there.

**"FDR correction — Benjamini-Hochberg (naive) + clustered logit p".** Half true, and the half that
is true is the older path. `bh_fdr` still exists (`Biomarkers/routines/stats_utils.py:20`) and is
still used by the spectral scan (`analytics.py:944`, `947`, `954`). But the section added tonight
does **not** use it: it uses a **selection-aware** reference instead —
`shuffled_best_of_windows_p95`, `p_selection_aware`, and three-valued `answer` verdicts referenced
to the no-discrimination value, with `BAND_PAIN_ESTABLISHED` at `analytics.py:4794`. That is a
stricter and differently-shaped correction, and it exists precisely because a Benjamini-Hochberg
q-value does not account for having taken the maximum over ten correlated integration times.

**What the README needs:** §1.7b should say that the older spectral scan corrects with
Benjamini-Hochberg, that the band-by-integration-time section corrects for **selection over
windows** by permutation instead, and that the AUC > 0.60 gate is gone. Two different corrections
for two different questions is the accurate picture; one method described as the method is not.

---

## The significant omission

**The closed-loop deployment module now reads band power from the lab's calibrated route, and the
README does not mention it.** Searching `README_BIOMARKERS_AND_DEPLOYMENT.md` for `band_power_linear`
or any statement about the closed-loop module using the calibrated route returns **zero** matches.

This matters more than any wording fix in the document, because it is the change that moved the
science: switching that module onto the calibrated recipe took the deployable verdict from **2 of 50
to 6 of 50 settings**, changed the selected setting from `ONE_THREE_LEFT`/Left/165 Hz to
`ZERO_TWO_LEFT`/Left/55 Hz, and reversed the sign of the current-to-power relationship on a large
minority of entries. The README still describes LSB computation as a Biomarkers-side concern only.

And the corrections document **predicted this exact gap**. Its own closing note 3 reads: "Consider
reviewing documentation alongside any future changes to … LSB computation constants (affects §1.4,
§1.6)." That review came due and was not done. It is the one genuinely **outstanding** item in the
document.

---

## The six corrections, re-verified

| # | claim | still true? | citation in the document | where it actually is now |
|---|---|---|---|---|
| 1 | `MedtronicIndefiniteStream` is a time-domain source | **yes** | `availability.py` ~31, ~40 | `bravo_service.py:42` |
| 2 | extent is a slider, 3–300 s, default 30 s | **yes** | `bravo_service.py` ~2686–2700 | `bravo_service.py:2981–2982` (`lo=3.0, hi=300.0`); default `analytics.TRANSFORM_CENTERED_EXTENT_SECONDS` at `analytics.py:3526`; React sends `MatchExtentSec` default 30 (`Client/src/views/Reports/Biomarkers/index.js:151`, `206`) |
| 3 | the PSD bridge integrates ±2.5 Hz, not interpolates | **yes** | `analytics.py:3186` | `analytics.py:3602` |
| 4 | six configurable pain scores, not VAS only | **yes** | `bravo_service.py` ~290–340 | `bravo_service.py:280–289` |
| 5 | mixed-model / forward-windows workflow | **partly — see above** | across modules | gate gone; correction method superseded for the new section |
| 6 | discovery workflow diagram | phases 1–2 yes | logical flow | phases 3–5 inherit correction 5's staleness |

**Correction 3 is now load-bearing in a way it was not in June.** The PI's rule of 2026-09-06 —
"the band centers should reflect plus or minus 2.5 Hz for a total 5 Hz band centered at the
frequency that it is named for" — is the same ±2.5 Hz half-width, and it is set at
`availability.py:706`, `848`, `1008` and `1158` (`band_half_hz=2.5`). The README's June wording and
tonight's rule agree, which is worth stating rather than leaving as coincidence: **a stored column is
already the full 5 Hz band on its named centre, so neighbouring columns must never be summed or
averaged to build one — they overlap heavily and would inflate every value.**

---

## Two things stale in the document beyond line numbers

1. **`LSB_PER_UV2_TRANSFORM = 352.62` is still correct and still the primary route**, but the
   document (and README line 245) cites `analytics.py:2829`; it now lives at `analytics.py:3362`,
   with the source-of-truth statement at `3318` and the shared helper documented at `3580`. The
   value was re-confirmed tonight when an invented constant of ~215 was withdrawn in favour of this
   calibrated one.
2. **"Current HEAD: `cd09845`" and "container suite 261/261"** are both far behind. Current container
   Biomarkers is **PASS=370 FAIL=0** and ClosedLoopDeployment + StimOptimizer is **778 passed / 41
   skipped**, each read from an actual run.

---

## One new fact the README should carry and cannot have known

**The band-by-integration-time section deliberately does NOT read `MatchExtentSec`.** The code says
so at `bravo_service.py:5364–5366`: sweeping the length of signal is the whole point of that
section, so the slider that fixes a single length is intentionally ignored there. The README
describes the extent slider as governing the page. It governs the rest of the page but not that
section, and a reader adjusting the slider and seeing the sweep unchanged would reasonably think
something was broken.

---

## Recommended edits, in priority order

1. **§1.4 / §1.6** — record that the closed-loop deployment module reads band power from the
   calibrated route, and what that changed. This is the outstanding item the document itself
   predicted.
2. **§1.7b** — remove the AUC > 0.60 gate; distinguish the spectral scan's Benjamini-Hochberg
   correction from the new section's selection-over-windows permutation.
3. **§1.3** — note the one section that deliberately ignores `MatchExtentSec`, and why.
4. **All six citations** — repoint to the lines in the table above.
5. **§1.7b / new** — document the sweep: the delivered-versus-requested lengths, that 0.5 is the
   no-discrimination reference, and that the reported best-of-ten is optimistic by construction.

Nothing in the document needs deleting as wrong. It needs repointing, one workflow paragraph
rewritten, and one section added.
