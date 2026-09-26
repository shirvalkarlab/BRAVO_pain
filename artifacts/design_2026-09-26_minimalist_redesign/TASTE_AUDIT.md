# Taste audit of the minimalist redesign (2026-09-26)

Read-only audit of the redesign against three third-party design skills the PI chose
(`Leonxlnx/taste-skill`: `skills/taste-skill` v2 "design-taste-frontend", `skills/minimalist-skill`,
`skills/redesign-skill`), `SPEC.md` and the house rules. Section C lists proposals not yet built
and waiting on the PI; D lists conflicts with the hard constraints; E lists places where the code
did not match SPEC.md, fixed afterwards (decision 321). The screenshots it read were rendered from
saved or stubbed data; the "m"/"me" text beside titles (icon font not loaded), the side menu over
the Biomarkers page (a hover) and "ceiling not sent" (an old saved report) came from that setup.

The taste skill says it is for "landing pages, portfolios, and redesigns. Not dashboards, not data
tables, not multi-step product UI"; its own section 13 says to state that and use only what fits.

- **Carried over:** reading the brief and its quiet constraints (0); the trust-first dial row (1.A);
  one accent colour and one radius system (4.2, 4.4); loading, empty and error states, contrast, one
  label per action (4.5); label above input (4.6); rereading every sentence (4.9); one theme (4.11);
  reduced motion (6.B); no pure black (9.A); keep page structure and navigation labels (11.C, 11.F).
- **Not carried over:** hero, image, logo-wall and bento rules; eyebrows, marquees, scroll animation;
  serif fonts; Tailwind, Next.js or Motion; real photographs; the 25-word paragraph limit and the
  "no 20-row tables" rule (the tables are the data); moving to Carbon.

## A. Design Read and dials

"Reading this as: clinical decision-support product screens (not a landing page) for a neurologist
and research team choosing deep brain stimulation settings, with a quiet, trust-first minimalist
language, leaning toward the existing Material UI stack re-tokenised as a plain clinical instrument
(IBM Plex Sans, near-black on white, one blue accent, red kept for refusals)."

- Design variance 3 of 10: predictable aligned columns for scanning a safety answer.
- Motion 1 of 10: nothing fades or slides in front of a clinical value.
- Density 6 of 10: clinicians compare many numbers side by side.

## B. Already done

One flat accent colour, no gradients; red reserved for safety with its glyph (one table, `tokens.js`
STATE); one radius system (4 px controls, 6 px cards), hairline cards with no shadow; one typeface
(IBM Plex Sans, 400/600) with tabular figures; no pure black in text; prose capped at 68 characters;
sentence case (except the recompute bar, the PI's file); every text colour at least 4.5:1, recomputed
by `tokens.test.js`; plain-row folds with content kept mounted; figures without toolbar, gridlines or
legend boxes, directly labelled, colour-blind-safe; one filled primary button per card; the current
page marked in the menu; semantic section, header and navigation elements; only the fold arrow moves.

## C. Proposed changes not yet made (for the PI; most valuable first)

1. **Visible keyboard focus ring**: 2 px accent outline, 2 px offset, on keyboard focus only
   (`assets/theme/base/globals.js`, `assets/theme/components/button/*`, the two fold components).
   Most buttons now turn the browser's ring off and show nothing.
2. **Composed empty and loading states**: collapse empty figure space to one sentence
   (`Biomarkers/index.js`, `MatchWindowBand.js`, `BinarizationPreview.js`: about 200 and 350 px blank
   in the screenshot); still grey blocks shaped like the table instead of spinners
   (`StimOptimizer/DecisionStrip.js`, `TwoStagePlanCard.js`, `Biomarkers/BiomarkerHeatmapGrids.js`,
   `BandTimeSweepPanel.js`), keeping the existing words.
3. **Links recognisable without colour**: underline links inside sentences (`globals.js` removes all
   underlines; the blue against body text is 1.63:1); leave the jump-link row.
4. **Respect "reduce motion"**: smooth scroll (`globals.js`), fold arrows (`paper/Fold.js`,
   `Biomarkers/Fold.js`) and side-menu transitions (`SidenavRoot.js`) become instant.
5. **Balanced heading line breaks**: `text-wrap: balance` on headings and the 22 px status sentence,
   `pretty` on prose (`typography.js`, `paper/PageHead.js`, `StimOptimizer/index.js`, `paper/Section.js`).
6. **Build every page from the shared components**: `Biomarkers/Fold.js` repeats `paper/Fold.js`;
   Biomarkers sections use their own card style; the Closed-Loop page writes its own ceiling line;
   the Closed-Loop and Stim Optimizer heads are hand-built instead of `PageHead`.
7. **Page skeleton for screen readers**: main region with an id and a "Skip to content" link, names
   for icon buttons (`layouts/DatabaseLayout/DashboardLayout.js`,
   `components/Navbars/DashboardNavbar/index.js`); browser tab title set to each page's question.
8. **Do not depend on the online icon font**: host Material Icons locally or draw the few navigation
   icons from an installed library (`Client/public/index.html`); needs the PI's approval if a package
   is added.
9. **Empty cells as words**: "none" or "not given" instead of "—" (`StimOptimizer/DecisionStrip.js`,
   `SensingEvidenceTable.js:267`); a dash reads as "em dash" and can be mistaken for zero.
10. **One number grouping per row**: "30 000" against "30000" in `ClosedLoopSim/PrescriptionPanel.js`.
11. **No "·" separators in the jump-link row** (`StimOptimizer/index.js`; a dot starts a line on a phone).
12. **Background items as plain rows, not cards** (`Biomarkers/index.js`, e.g. "Calibration in effect").

## D. Conflicts (hard constraints or the spec win)

1. Scroll-in fades and staggered entry (minimalist 7, redesign "Motion Upgrades"): no motion may hide or
   delay a clinical value.
2. Background imagery, grain, light spots, photographs (minimalist 6, 8.6; redesign; taste 4.8): colour
   belongs to the data; plain surfaces stay.
3. Secondary grey #787774 (minimalist 3): 4.48:1 on white, 4.28 on the page colour; #5E5E5E (6.48:1)
   stays. The #EAEAEA input border (1.2:1) is too faint; #8A8A8A (3.45:1) stays.
4. Uppercase wide-tracked pill badges (minimalist 5): sentence case wins; the one uppercase line left is
   inside `RecomputeBar.js`, the PI's file.
5. Pastel tags including pale red (minimalist 4): red only for refusals and the ceiling.
6. Fonts (SF Pro/Geist, an editorial serif, monospace, a 500 weight): one face, IBM Plex Sans 400/600.
7. Hover-lift shadows and "motion shown" (taste 5; minimalist): no card shadows, no decorative motion.
8. Em-dash ban (taste 9.G): the house rules govern wording; safety and server text stay word for word.
9. Middle-dot rationing against the spec's approved pairing line: the spec wins there; only the
   jump-link row (C11) is worth changing.
10. Dark mode mandatory (taste 6.C, 8): the spec postpones it until its own contrast table is measured.
11. A new design system or stack (Carbon, Tailwind, Motion, Next.js): stay on Material UI, plain JavaScript.
12. "No hand-drawn SVG icons": the ✕ ▲ ○ ✓ markers are required by the spec as meaning markers.
13. 96-128 px section spacing and a narrower column: the spec's 64 px and 1,120 px suit clinical scanning.
14. **For the PI: what red means.** The hard constraint says red only for device refusals and the
    ceiling; SPEC 2.3 and `tokens.js` also allow red for anything that "blocks closed loop". So the Stim
    Optimizer shows "✕ Setting not proven better" in red (`StimOptimizer/StatusLine.js:69`), a statistical
    result, not a device refusal; likewise "✕ No usable sensing pair" and the red "not usable" rows
    (`SensingEvidenceTable.js:112-114`). Under the narrower rule these need black ink with ✕.

## E. Code that did not match SPEC.md (defects; fixed in decision 321)

1. The Closed-Loop (541 px) and Stim Optimizer (662 px) pages scrolled sideways at 390 px
   (`ClosedLoopSim/PrescriptionPanel.js`, `StimOptimizer/DecisionStrip.js`); the breadcrumb overlapped the
   title on a phone.
2. Caution-coloured text without its ▲ (`PrescriptionPanel.js` 62-68, 146-149, 161-163;
   `DecisionStrip.js` 197, 201; `ClosedLoopSim/index.js` 147-155).
3. The line under each title omitted the participant code (`Biomarkers/index.js` 652-653,
   `ClosedLoopSim/index.js` 415, `StimOptimizer/index.js` 199-203).
4. The Biomarkers head had no status sentence or list; both sat inside the first section card.
5. A decision number in page text (`BiomarkerHeatmapGrids.js:292`, "(decision 217)"); the reason the
   device refuses the pairs sat in a closed fold (borderline; the count is in the open).
6. The Closed-Loop ceiling line was hand-written, named one side and said "not sent with this report".
7. Timeline controls outside the protected gutter: Arial 11 px base font, 13, 12.5 px and italic
   (`BiomarkerDataTimeline.js` 1056, 1187-1196).
8. The fallback timeline (`BiomarkerTimeline.js`): "LEFT HEMISPHERE" in capitals at 21 px; 13 and 13.5 px.
9. App-wide: `stepLabel.js:34` uppercase; `colors.js` `black` #000000 (key kept on purpose).
