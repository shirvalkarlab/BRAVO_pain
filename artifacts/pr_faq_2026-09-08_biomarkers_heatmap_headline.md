# PR-FAQ — the calibrated grid becomes the headline of Biomarkers Exploration

**Written 2026-09-08.**

## The one-paragraph version

Right now, opening the Biomarkers page runs an older, research-only calculation first, and the
newer calculation — the one that checks the exact 22 frequency points a real implanted device can
use, on the device's own power scale — only appears afterward, with no way to click into it. This
redesign flips that: the device-realistic grid runs first and becomes the main thing on the page,
with a click on any point in it opening the same scatter, line, and violin plots a reader already
knows how to use. The always-visible timeline showing every recording and pain report the
participant has stays exactly where it is, above everything else.

## Why now

The calibrated grid is already the finding this project treats as its headline result. Burying it
behind a slower, less device-realistic calculation, with no way to explore it, works against that.
Two other real gaps surfaced while designing this: one of the page's own controls (which direction
in time a pain rating gets matched to a recording) silently does nothing on the calibrated grid
today, and nothing on the page corrects for testing 22 frequency points at once, only for choosing
the best of ten signal lengths at each one. Both are fixed as part of this same redesign rather than
left for later, since fixing the display without fixing what it is displaying would just make a
half-correct number easier to find.

## Frequently asked questions

**Does this change any number that has already been reported or published?** The correlation and
AUC values themselves do not change. Two new things appear: a label saying whether a point survives
testing 22 frequencies at once, and — once match-direction is wired in — a note saying which
direction of time the matching used. Both are additions, proven live against the current numbers
before shipping, not replacements for them.

**Does this merge the two different biomarker calculations into one?** No. Decision 61 already
settled, with evidence, that the older full-spectrum calculation and the newer calibrated one answer
different questions on different scales and must stay separate. This redesign changes which one is
shown first and how a reader moves between them; it does not change what either one computes.

**What does Closed-Loop Deployment gain from this?** Today it only ever sees one band a user has
already chosen. This redesign lets it receive the whole calibrated grid instead, pre-computed, so a
user can browse any point there and see its effect on that page's own settings without leaving it or
recomputing from scratch.

**What is explicitly not being decided by this document?** Which of the three page designs to build,
the exact tie-break rule for choosing a "best" cell, and the final sign-off on the new statistical
correction's method — all three need the PI's own answer before any of this is built, listed at the
end of the accompanying requirements document.
