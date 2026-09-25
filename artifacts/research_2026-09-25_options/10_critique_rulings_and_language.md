# Adversarial critique: `00_SYNTHESIS.md` against standing rulings and house writing rules

Reviewed: `artifacts/research_2026-09-25_options/00_SYNTHESIS.md` against CLAUDE.md §8,
`HOUSE_RULES_writing_and_claims.md` in full, and `DECISIONS_and_open_items.md` Part 1 and the named
rows. Line numbers are from the copy read this session (re-grep before citing them elsewhere, per
rule 3).

## Table

| # | Category | Exact sentence (location) | Rule broken | Rewrite |
|---|---|---|---|---|
| 1 | (2) unreadable without the code | "I read `confound_diagnostic.py`'s `pre_build_diagnostic` function directly: it computes a shuffled-data p-value only for the plain 'every band' reading (`plain["p_value"]`), never for the 'bands with current taken out' reading. I then read the live page code that runs this check, `ControlAnalyses/runners.py`'s `run_current_explains`: it assigns `p=d["bands_plain"].get("p_value")`..." (§3b, lines 122-127) | House rules §1/§2 and CLAUDE §8 rule 12: name what a thing does first, put the function/field name in brackets only if he'd need it to find the code; four code identifiers (`pre_build_diagnostic`, `plain["p_value"]`, `run_current_explains`, `p=d["bands_plain"].get(...)`) are woven into the sentence instead. | "The chance-shuffle check only computes a p-value for the plain reading (current still in it); for the current-taken-out reading it only records whether the result falls inside or outside the range chance alone would produce, never a p-value (the code: `confound_diagnostic.pre_build_diagnostic` and `ControlAnalyses/runners.py`)." |
| 2 | (2)/House §1 jargon | "Six of the seven reports investigate this patient's own record (RCS08)" and 7 further bare uses of "record" (lines 26, 36, 43, 78, 82, 133, 193, 246) | House rules replacement table: "record, full record" is flagged unintelligible bare; write "all the data we have." | Replace each with "all the data we have (RCS08)" / "in all the data we have so far" as context requires. |
| 3 | (2)/House §1 jargon | "every alternative tried, including a model-free reshuffling test, agrees in direction" (line 241, Option 7 summary) | House rules replacement table: "direction" bare is flagged; the reserved replacement is "whether power rises or falls as current increases," or here, "which way the effect points." | "every alternative tried ... points the same way (toward no difference between conditions)." |
| 4 | (2)/House §1 jargon | "matches across reports 1, 2, 4, and 5 ... (0.600, 0.708, 0.722, 0.743, 0.681, 0.683, the two null values)" (line 155) | House rules replacement table: "permutation, null" bare must read "shuffling the data to see what happens by chance." | "...and the two numbers describing what shuffling the data by chance alone would produce." |
| 5 | (1) tension with a standing ruling, unflagged | "The report specifies a research-grade detector (every band read together, current taken out with a shape that can turn over) and a device-realistic one ... and asks the PI to settle three choices before any of it is built" (Option 4, lines 200-209); table row 4 says "Whether a device-realistic, single-band, single-current-adjusted signal survives the sensing-pair rule and the harmonic warning" (line 169) | Decision 233 answer 2 and decision 210: the current-taken-out reading is descriptive only and "never re-selects a band ... on its own" in the shipped one-band-rule pipeline (decisions 199, 210). Option 4 proposes a new tool whose stated purpose is to select/flag a band FROM the adjusted reading. The synthesis never states that this is a separate research tool and does not loosen 233's rule for the shipped platform. | Add one sentence to Option 4: "This is a new, separate research tool built only with the PI's explicit go-ahead; it does not change decision 233's rule that the adjusted reading is descriptive only and never re-selects a band in the platform's own one-band-rule pipeline." |
| 6 | (5) PI question not cleanly answerable | Question 5: "adopt the report's three recommended defaults as a package ... or specify a different combination?" (lines 300-303) bundles three separate choices (which ratings, continuous vs. split, device timing at which tier) into one yes/no-shaped question. | House rules §4/§12 (plain, answerable questions) | Split into three sub-questions, each answerable alone: "5a. Use REDCap ratings as primary, clinic-sheet ratings shown separately, never merged — yes/no? 5b. Keep pain continuous for the research-grade version and split it into two groups only for the device-realistic version — yes/no? 5c. Build the device's own timing into the device-realistic version from the start, checking it only at the end for the research-grade version — yes/no?" |
| 7 | (3) precision loss on a sourced number | "the honest answer is close to a coin flip (roughly 0.5), not 1-in-25" (line 48-49) | House rules §2: "say the number and its meaning in one breath" — the actual corrected number (0.48, from report 5's Bonferroni arithmetic) is available and more informative than "roughly 0.5." | "the honest answer, corrected for the twelve combinations tried, is about 0.48 — close to a coin flip, not 1-in-25." |

## Checked and found compliant (noted so the PI does not have to re-check)

- No use of "spectrum" bare, no log-power language, no proposal to model time (Option 3 explicitly
  argues against it, consistent with decisions 193-196), no pooling across electrodes, no default-on
  merging of clinic-sheet ratings (the opposite is recommended, consistent with decision 258), no
  resurrection of the deleted reliable-change index, no claim that a one-visit finding is
  "established," no reserved-word misuse of "threshold" or "floor," no line numbers or suite counts
  quoted from a document as if current. The "p = 0.04" correction (§3b) and the misdated-session
  correction (§3a) are handled exactly as house rules require: claim and number together, with the
  document reference checked against the decision log's own text.
- Decision 215's "20 cells ... all pain-report columns" citation (line 145) checked against the FULL
  decision-215 row in `docs/decision_log_full_2026-09-19.md` (not the digest): the quote is accurate.
- Questions 1, 2, 3, 4, 6, 7, 8, 9 are each answerable yes/no or by naming one of a short, explicit
  list of options without reading any underlying report.

## Counts

Category (1) standing-ruling contradictions: 1 (tension flagged, not an outright contradiction — a
missing caveat, not a broken rule). Category (2) unreadable without the code / bare jargon: 4.
Category (3) numbers without source or imprecise: 1 (all other numbers checked traced to a named
decision or report). Category (4) forbidden claims: 0. Category (5) unanswerable PI questions: 1 of
9 (Question 5).
