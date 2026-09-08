# PRD — making the calibrated heat maps the headline of Biomarkers Exploration

**Written 2026-09-08. Status: awaiting the PI's decisions, listed at the end. Nothing here is
authorization to implement (CLAUDE.md §10 rule 8).**

---

## 1. Why this change

The Biomarkers exploration page runs two different calculations that both ask "does this band's
power track pain": an older routine that scans a continuous 0-100 Hz range with raw, uncalibrated
signal strength, and a newer one that checks 22 fixed frequency points a real implanted device can
actually be programmed at, using the device's own calibrated power scale. Decision 61 already
settled that these two must stay separate calculations — this document is not about merging them.

Today the newer, device-realistic calculation is buried behind the older one (its button is
disabled until the older routine has run), and its two result grids — one for correlation, one for
how well a band tells high pain from low pain apart — are not clickable and carry no drill-down.
The PI wants the reverse: the device-realistic grids should be the first thing computed and the
dominant thing on screen, with the older routine's scatter, line, and violin plots reachable as a
drill-down from a chosen grid cell, all underneath the always-visible timeline that shows every
recording and pain report the participant has.

## 2. What is on the page today (verified against the live source, not assumed)

Top to bottom: a recompute control and cache-status line; the Biomarker Data Timeline (always
shown, no click handling, no computation needed); a pain-score picker; a progress bar; a controls
box (binarization method and cuts, a three-way match-direction toggle, a match-time-window slider,
a seconds-per-rating slider) with a live histogram preview; a run button; a text summary; the older
routine's single dual-axis curve with click-to-drill scatter and violin plots and a "Commit this
band" action; the newer routine's two heat map grids, gated behind the older routine having already
run, with no click handling at all; and the device-scale calibration panels.

Where the two displays disagree today: two separate ways of choosing a sensing contact pair; three
different frequency vocabularies (a continuous 0-100 Hz range, 22 fixed points, and the device's
own recorded sensing centres on the timeline); two different signal-length conventions (the older
routine uses one length from a slider, the newer one tries ten fixed lengths and explicitly ignores
that slider); two different correlation types (confirmed this session: the older routine reports a
rank correlation, the newer one a straight-line correlation); two different ways of orienting the
high/low-pain separation number; the same two accent colours reused for unrelated meanings in three
different places; two pain-score pickers that can silently disagree; and well over a printed page of
small-print captions before any plot is read.

## 3. The one asymmetry the design must make visible

**The correlation grid depends only on how pain reports are matched to recordings** — the match
time-window, and (once wired in, see §5) whether the match looks only at recordings from before a
pain report or also looks forward. **It does not depend on the binarization scheme at all.**

**The AUC grid depends on both of those matching choices AND on the binarization scheme**, because
telling high pain from low pain apart requires a high/low split to exist in the first place.

A reader who changes the binarization cuts and expects the correlation grid to change is expecting
something that cannot happen; a reader who changes the match window and expects only the AUC grid
to respond is missing that the correlation grid responds too. Every option below states, concretely,
how it shows this on screen rather than only in a caption.

## 4. Three whole-page design options

All three share this fixed order, top to bottom, per the PI's instruction: the timeline, unchanged
and paramount; the binarization controls and their preview, kept; the two heat map grids as the
headline; a drill-down for one chosen cell (a scatter plot with a fitted line, plus violin plots
comparing the high-pain and low-pain groups); the device-scale calibration panels, last.

### Option 1 — Guided diagnostic

On arrival, the page has already picked the single best cell the server marks as an established
relationship (see §7 for what "established" means) and shows it, filled in, in the drill-down panel
below the grids. Both grids carry a thick outline on that cell. A small stepper reads, for example,
"Candidate 1 of 4 — left one-three contact, 22.5 Hz, 60 seconds of signal" with next and previous
controls that walk through the server's own ranked list, across contact pairs as well as frequency
points. Clicking any other cell directly leaves the walk and pins that cell instead; hovering a cell
first shows a small live preview before a click commits it. A one-line badge at the top of the grid
section states which matching direction produced the numbers underneath it (see §5), and the
correlation grid carries a static note — "unaffected by the binarization choice above" — that never
changes, while the AUC grid briefly highlights and re-draws whenever the binarization cuts change,
so the asymmetry in §3 is shown by what moves and what does not.

*Strength.* This is the option that most literally makes the grids the dominant message — a reader
sees a real, chosen answer within a second of the page finishing its first calculation, with no
click required. *Cost.* Choosing "the best cell" bakes in a ranking rule (established beats not
settled beats not assessed; a tie inside "established" needs a rule the PI states, e.g. larger
correlation or larger distance from a coin-flip AUC) that the PI must approve explicitly (§8).

### Option 2 — Search-first, minimal chrome

No cell is pre-selected. The grids are a pure browsing surface: hovering any cell shows a small
preview card with its numbers and a miniature scatter; clicking pins that preview into the full
drill-down panel. A row of small thumbnail grids, one per sensing contact pair, sits above the two
main grids so the contact pair is chosen by looking, not by a dropdown — clicking a thumbnail swaps
the two large grids to that contact. Nearly all of today's small-print captions collapse into a
single "how to read this" panel that starts closed. The asymmetry in §3 is shown structurally: the
correlation grid's frame never changes appearance when the binarization cuts move; the AUC grid's
frame flashes once when it recomputes, so the two grids visibly behave differently under the same
edit rather than only describing that difference in words.

*Strength.* The smallest amount of new logic to build — no ranking rule, no stepper state — and the
page reads as a clean, quiet instrument rather than a report. *Cost.* A first-time reader gets no
suggested starting point and must find a strong cell by browsing; this option leans more on the
reader's own judgement than Option 1 does.

### Option 3 — Timeline-anchored

The timeline itself gains the job of choosing the sensing contact pair: clicking a lane's label
sets the contact pair for everything below it. Choosing a cell in either grid echoes back onto the
timeline by dimming every pain report and recording span that did not feed that cell, so a reader
can see, directly on the one view that already shows every recording the participant has, exactly
which visits and which reports a given result rests on — a direct, visual answer to whether a
result comes from one visit or many. Below the timeline, the two grids and a single drill-down panel
follow the master-and-detail pattern of Option 1 without the guided walk.

*Strength.* This is the option that most fully honours "the timeline is paramount," since the
timeline becomes load-bearing rather than merely decorative. *Cost, and a hard prerequisite.* This
is the only option that changes the timeline's own rendered behaviour, and the timeline's left-hand
label layout was tuned by hand against a signed-off figure whose exact rules are not written down
anywhere (CLAUDE.md §9). **This option must not begin until those rules are asked for and written
down.** It should be sequenced after Option 1 or 2 ships, not attempted first.

### Recommendation, as a lean and not a decision

Lead with **Option 1**. It satisfies "make the heat maps the dominant message" most directly, it
carries no blocking prerequisite the way Option 3 does, and its added complexity (the ranking rule
and the stepper) is bounded and reviewable in one sitting. Hold Option 3 for a second phase once the
timeline's label conventions are in hand. Option 2 is the fallback if the ranking rule in Option 1
turns out to need more scientific discussion than one plan can resolve.

## 5. Wiring the match-direction setting into the calibrated grids

Confirmed this session by reading the code: the page's three-way match-direction control (labelled
"PRO-first," "Nearest," and "Prior") already reaches only the older routine. The newer, calibrated
matching function takes no direction argument at all and always matches symmetrically in both time
directions within the match window — confirmed live, changing the control today produces identical
matched counts and identical timings for the calibrated grids, because the setting is never read.

The three options mean, in code terms: "PRO-first" walks each pain report and claims the nearest
eligible recordings on either side of it; "Nearest" matches each recording to whichever pain report
is closest in either direction; "Prior" is the one-directional, forecasting-safe choice — a
recording is only matched to a pain report that comes at or after it, so nothing "sees the future."

The calibrated matcher needs a small, additive change (one new keyword argument, one new
one-directional neighbour search reusing the existing search machinery, and the same request-field
reading the older routine already does) to respect the same three choices — no shared logic needs
inventing, since the "prior" direction's logic already exists in the older routine and only needs a
one-directional counterpart written for the newer, window-based matcher.

**New requirement, confirmed as buildable:** the page must report, as a plain reported number,
whether the grids on screen came from a "prior" (backward-looking only) match or a "prospective"
(either-direction) match, shown once per contact pair's grid pair since the setting applies to the
whole request. This is new instrumented behaviour, not a display change — once built, it needs the
same live-data proof this project requires for anything computed for the first time: does changing
the setting actually change which recordings get matched to which reports, checked on RCS08's real
data, not just assumed.

## 6. Exporting the full grid to Closed-Loop Deployment

See `adr_2026-09-08_biomarkers_closedloop_matrix_export.md` for the full design and the reasoning
behind it. In summary: the calibrated grid's response is already being kept in the shared cache
store today, with a provenance chain already built from its own inputs. Extending that same stored
entry so Closed-Loop Deployment can read the whole grid — not just one committed band — reuses this
project's existing pattern exactly (the same one that already lets Stim Optimizer read a band table
Closed-Loop Deployment wrote), and reading it does not trigger the self-derived-product refusal
(decision 31), because Closed-Loop's own choices do not determine which recordings exist to feed
this grid the way Stim Optimizer's exploration choices do.

Closed-Loop Deployment's own page is hard-wired today to evaluate exactly one band candidate per
request. Letting a user browse the whole grid there needs a compact version of the same
grid-with-selection interaction proposed above, and — because the full per-band evaluation on that
page costs up to half a minute per band today — a small set of fast, pre-computed columns (whether
the device's own rules forbid a configuration; whether the band's relationship holds up across
different stimulation settings) added once per grid rather than recomputed on every click. The
slower checks (the full three-source comparison, the receiver-operating curve) stay behind a click,
computed live only for whichever band the user actually opens.

## 7. The family-wise correction, restricted to 8-30 Hz

See `adr_2026-09-08_biomarkers_sweep_family_wise_correction.md` for the full design. In summary: the
calibrated grid's existing three-state answer (established, not settled, not assessed) already
corrects for choosing the best of ten signal lengths per frequency point, but does not yet correct
for testing 22 frequency points at once. This document proposes adding that second correction using
the same method (Benjamini-Hochberg, the project's one existing multiple-testing correction
function) the older routine already uses, applied only across the calibrated grid's own 22 points —
which are already confined to 8 to 30 Hz by the device's own limits, so this is not a new
restriction, it is simply not pooling in the older routine's much wider range. **Resolved by the PI
this turn: this correction is a label shown on every cell, never a gate** — a cell that fails it
remains fully browsable and exportable to Closed-Loop Deployment.

## 8. Decisions still needed from the PI before implementation starts

Per CLAUDE.md §10 rule 8, approving this plan is not the same as authorizing implementation, and
several specific method questions below still need his direct answer, not an assumed one.

1. **Which of the three options to build first** (§4) — a lean toward Option 1 is offered, not a
   decision.
2. **The tie-break rule inside Option 1's guided walk**, if Option 1 is chosen — when two cells are
   both "established," which one the page shows first (larger correlation, or larger distance from
   a coin-flip AUC, or something else).
3. **Confirmation of the exact correction method for §7** — Benjamini-Hochberg is what this project
   already uses elsewhere and is proposed here for that reason, but every prior correction choice in
   this project has its own explicit sign-off, and this one should too.
4. **Whether the family-wise correction in §7 also needs the same autocorrelation adjustment** the
   older routine applies before its own correction (a separate fix for pain ratings being related to
   each other over time, not the same thing as correcting for testing many bands) — the explorer
   investigation found no such adjustment exists yet for the calibrated grid at all, corrected or
   not, which is a separate, currently-open question about the calibrated grid's honesty that this
   plan surfaces but does not resolve.
5. **Confirmation that Option 3 (§4) should wait** for the timeline's label conventions to be
   written down, rather than being attempted with invented geometry.
