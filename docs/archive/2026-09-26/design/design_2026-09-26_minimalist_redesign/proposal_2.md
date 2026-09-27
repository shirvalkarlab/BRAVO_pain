# One design system for BRAVO: the page reads like a scientific paper

**Approach.** Each page reads like a short paper. It has a title and a two-line abstract that gives the answer. Then come numbered sections, each opened by a question, answered in one sentence and carried by one main figure with a numbered caption. The method goes in a fold. Analyst material goes into supplementary sections at the end. Headings, text and rules are black and grey. Colour appears only inside figures, with one exception: device refusals and the safe current ceiling keep their red, and red always comes with a glyph.

All contrast ratios below were computed against white (#FFFFFF, the surface) and against the proposed page background (#FBFAF7). The numbers are ratios.

---

## 1. Design tokens

### 1.1 Colour used by the page itself (not in figures)

| Token | Hex | On white | On page | Use |
|---|---|---|---|---|
| `ink` | #1A1A1A | 17.4 | 16.7 | titles, answers, numbers |
| `ink2` | #3D3D3D | 10.9 | 10.4 | body text |
| `ink3` | #5E5E5E | 6.5 | 6.2 | captions, labels, axis titles, secondary text |
| `rule` | #C9C9C4 | 1.7 | — | hairlines and dividers only, **never text** |
| `hairline` | #ECEBE7 | — | — | table row separators, figure frame if any |
| `surface` | #FFFFFF | — | — | the column the text sits in |
| `page` | #FBFAF7 | — | — | window background, a paper tone |
| `link` | #0B5CAD | 6.7 | 6.4 | links and the one primary button; the only accent |
| `refused` | #B42318 | 6.6 | 6.3 | device refuses, above the safe ceiling, blocks closed loop. **Always with ✕** |
| `caution` | #8A5A00 | 5.9 | 5.7 | needs more data, not yet certain. **Always with ▲** |
| `notAssessed` | `ink3` + ○ | 6.5 | 6.2 | could not be checked; the third state of a gate, so a gate never looks green by default |

- A check that passes is drawn in `ink` with ✓. There is no green in page text. This removes the red against green pair everywhere outside figures.
- The following are deleted from text use: #7b809a (3.9), #D55E00 (3.9), #009E73 (3.4) and #6C757D (4.7, too close to the limit).

### 1.2 Figure palette (new file `Client/src/assets/theme/base/dataColors.js`)

**Categories (Okabe-Ito, in a fixed order):**

| Role | Hex | Note |
|---|---|---|
| blue | #0072B2 | 5.2; passes as text too |
| vermillion | #D55E00 | marks and fills only |
| bluish green | #009E73 | marks and fills only |
| orange | #E69F00 | marks and fills only |
| sky | #56B4E9 | marks and fills only |
| purple | #CC79A7 | marks and fills only |
| grey for context | #8C8C8C | 3.4; meets the 3:1 minimum for graphics |

**Fixed meanings, the same on every page:**
- Left side is #0072B2, right side is #E69F00. Where both sides appear, the right side's direct labels are set in `ink`.
- High pain is #D55E00, low pain is #0072B2, middle ratings left out are #BDBDBD.
- When a colour must appear as text (for example a direct label), use `ink` with a coloured marker beside it, or the darker text variant: vermillion becomes #A84300 (6.1), bluish green becomes #00755A (5.7).

**Diverging scale** for correlation, predicted pain against today, and area under the curve around 0.5. Nine stops, blue to grey to orange:

#0072B2 · #3F8FC4 · #86B6D8 · #C4DAEA · **#E4E4E4** · #F1CDB0 · #E8A273 · #DE7B3A · #D55E00

- The midpoint stays #E4E4E4, the colour already pinned in `StimOptimizer.designReview.test.js` (lines about 336–337). Cells near zero then read as light grey against white rather than disappearing.
- Every heat map gets one shared symmetric range per card, printed on the key:
  - correlation: ±0.5, values beyond it saturate;
  - area under the curve: 0.5 ± 0.25;
  - current maps: the largest deviation from today across every square on the card.
- The Plotly `RdBu` scale in `BiomarkerAnalytics.js` is retired.

**Sequential scale** (cividis; colour-blind safe and roughly even in lightness), for ordered quantities such as frequency lanes, counts and time:

#00204D · #213D6B · #555B6C · #7B7A77 · #A59C74 · #D3C064 · #FFE945

- On the timeline this replaces the 25-hue `FREQ_PALETTE`. Every lane also gets a direct text label, so colour is never the only key.
- Lane labels are drawn in `ink` with a coloured tick. That satisfies `legibility.test.js`'s 4.5:1 check, but its "same hue family" check has to change (see §6).

**Figure ink:**

| Element | Value |
|---|---|
| axis line | #8C8C8C, 1 px |
| ticks and tick labels | `ink3` |
| gridlines | #ECEBE7, y-axis only, or none |
| reference lines (0, chance at 0.5, the safe ceiling) | `ink3`, 1 px dashed, each labelled directly ("chance", "safe ceiling 4.5 mA") |
| best-cell ring | `ink`, 1.5 px, with a 1 px white outline |
| stability in a cell | shape only, in `ink` with a white outline: ✓ same, ✕ different, ? cannot tell |

### 1.3 Type (`typography.js`)

**Faces.**
- Headings: **Source Serif 4**, the editorial voice.
- Body, controls and all figure text: **IBM Plex Sans**, with `font-variant-numeric: tabular-nums` so mA and device-unit columns line up.
- Both load from Google Fonts in `public/index.html`. Roboto weight 300, Lato, the leaflet stylesheet and the extra Material Icons variants are removed.

| Role | Size / line height | Weight | Face |
|---|---|---|---|
| Page title (h1) | 28 / 36 | 600 | serif |
| Abstract / answer | 19 / 28 | 400 (the answer clause at 600) | sans |
| Section heading (h2, a question) | 21 / 28 | 600 | serif |
| Sub-heading (h3) | 16 / 24 | 600 | sans |
| Body | 16 / 26 | 400 | sans |
| Small (tables, controls, fold text) | 14 / 22 | 400 | sans |
| Caption ("Figure 2.", table header, figure axis titles) | 12.5 / 18 | 400; the "Figure n." label at 600 | sans |
| Figure ticks | 12 (never under 11 **on screen**) | 400 | sans |

- Two weights only (400 and 600), so `fontWeightLight` and `fontWeightLighter` are removed.
- Sentence case everywhere. Buttons are no longer uppercase. The 11 px all-caps `HEAD` style in `StimOptimizer/typeScale.js` is removed.
- Removed sizes: `fontSizeXXS` 10.4 px (below the 11 px floor) and d1–d6.
- **Maximum line length: 68ch for prose. Figures may use the full column.**

### 1.4 Spacing, radius, shadow

- **Spacing**, and no other values: 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64. Mapped to the MUI spacing factor (8 px): 0.5, 1, 1.5, 2, 3, 4, 6, 8.
  - Between sections: 64 px, with a hairline 32 px above each heading.
  - Heading to answer: 8. Answer to figure: 24. Figure to caption: 12.
- **Radius**: 0 for sections and figures; 4 for inputs, buttons and chips (`borders.js` becomes `{none: 0, sm: 4}`).
- **Shadow**: none. The one exception is menus and popovers: `0 4px 16px rgba(0,0,0,.08)` (`boxShadows.js`).
- **Cards stop being boxes.** `components/card/index.js` sets no shadow, no border and a transparent background. A "card" becomes a section on the page, and nothing is framed inside anything else.
- **Column**: the text column is 1120 px maximum and centred on the page colour, with 32 px padding at 1280 px and wider, 16 px on a phone. Figures can run the full 1120 px.

---

## 2. Page structure rules

1. **How a page opens:**
   - page title (serif 28);
   - one line naming the participant code (RCS08, never the hash) and the pain score in use;
   - an **abstract** of at most two sentences that gives the page's answer;
   - under it, a single **status list** of at most five items (✕ refused, ▲ caution, ○ not checked), each five words or fewer.
   - Safe-ceiling line, shown on the Stim Optimizer and Closed-Loop pages: "Safe current ceiling: 4.5 mA left, 4.5 mA right (stated by the PI). Nothing above it is offered on this page." It is read from the server and is never typed in by hand.
2. **Sections.** At most **four open numbered sections** per page, then "Supplementary" (S1, S2, …), each folded. A section is:
   - a heading that asks a question;
   - a one-sentence answer, with the number in it;
   - one hero figure, or a short table if there is no figure;
   - a caption in the form "Figure n. What is plotted. How to read the colour.";
   - at most three short sentences of interpretation;
   - one "How this was worked out" fold.
3. **When to fold.** Open: anything a clinician decides with, and every safety statement (device refusals, the safe ceiling, "not a value to program"). Folded: methods, alternative views (pulse widths pooled, other sensing pairs), settings not allowed today, research checks, calibration. There is one fold per section at most, and never a fold inside a fold. Folds keep their children mounted, so jest pins that read folded text still pass.
4. **Controls.** Controls sit above the figure they change, in one row, at 14 px. At most three are visible; the rest go under "More options". Any per-page option that decides the answer is repeated in the abstract line ("Paired within 60 min · REDCap only").
5. **Figures are the heroes:**
   - small multiples share one scale;
   - labels sit directly on the data, with no legend boxes;
   - one key per card;
   - no Plotly toolbar (`displayModeBar: false`);
   - figure titles live in the caption, not on the canvas;
   - SVG figures are drawn at their real pixel width, never scaled down below 11 px text.
6. **Jump links** become a slim table of contents under the abstract ("1 · 2 · 3 · Supplementary"). They are no longer inside a card.

---

## 3. Wording rules

1. Headings are questions. Answers are one sentence with the number and its meaning in the same breath ("Band power and pain move together weakly: correlation −0.31, not clear once all 22 bands are allowed for").
2. No codes in visible text:
   - E1, E2, E3 → "current → band power", "band power → pain", "current → pain";
   - M0 to M3 → "as recorded", "simulated, straight-line response", "simulated, peaked response", "range over resampled days";
   - edge, control law, LRT, CI, AUC, q, DEFF, MAD, era, stratum, payload and pts are replaced as in the five evaluations' jargon lists and the replacement table in `HOUSE_RULES_writing_and_claims.md` §2.
   - A code may appear only in hover text or inside a methods fold.
3. The first use on each page of a term that cannot be avoided gets a plain definition in brackets: "device units (LSB)", "PSD (the device's own 30-second snapshot)", "TD (band power from the continuous recording)".
4. Sentence case. No capitalised warnings: "SIGN − (INTERVAL SPANS ZERO)" becomes "Falls as current rises; the range crosses zero, so not yet certain".
5. The reserved words keep their meaning. "Threshold" is only the device's switching setting. The safety wording (device refusals, "not a value to program", the safe current ceiling) is kept word for word and only restyled.
6. Chance is always named: "0.5 = coin toss"; "the level shuffled data reach 1 time in 20".
7. Numbers keep their meaning; only their presentation changes. Ticks show true band centres: "8.5, 11.5, …" or round 10/15/20/25/30 Hz on a linear axis. They are never rounded half a hertz away from the band they mark.

---

## 4. The three pages, top to bottom

### 4.1 Biomarkers: "Which brain signal tracks pain?"

- **Title, then** the pain-score selector as a plain 14 px outlined select with the line "Every figure below uses this score". The red outline goes, because red now means only "refused".
- **Abstract:** "Allowed pairs today: L 1-3+, R 0-3+. After allowing for 22 bands, 0 bands rise with pain and 17 fall." The numbers come from the server's status line.
- **Status list:** "✕ 4 of 6 pairs refused today".
- **§1 "Which bands move with pain?"**
  - Hero figure: the six pair thumbnails as small multiples (about 120×60 px, same scale). Refused pairs are greyed and keep ✕ and "Refused today".
  - Below them, the two large maps side by side, one shared diverging key labelled at its ends ("falls with pain" / "rises with pain"), true-centre ticks, a dark best-cell ring and stability shown by shape.
  - Hover: "correlation −0.31 · 117 ratings (about 98 independent) · after 22 bands: p 0.002".
  - The drill-down scatter has direct labels ("high pain", "low pain", "○ clinic sheet").
  - Fold: "How to read this" at 14 px regular weight.
- **§2 "How are reports paired with recordings?"** A one-line summary with a "Change" button. The three main controls (match window, split rule, clinic sheets) are shown; five more sit under "More options". The timing histogram is the figure.
- **§3 "What was recorded, and when?"** The timeline:
  - title moved into the caption, ticks at 12 px;
  - cividis lanes, each labelled in the gutter;
  - a short legend of plain terms, direct where possible.
  - Gutter geometry follows the `bravo-timeline-layout` skill; load it before touching the file.
- **Supplementary (folded):**
  - S1: how each band's link with pain changed over time (shared diverging scale);
  - S2: how band power is converted to device units (the two constants stay visible when the fold is open);
  - S3: checks against chance and against the current, run offline;
  - S4: the 2026-09-21 search, opening on one plain sentence.

### 4.2 Stim Optimizer: "Should today's setting change?"

- **Abstract:** "Keep today's setting on both sides; closed loop cannot start." Then the **safe-ceiling line**. Status list: "✕ No usable sensing pair", "▲ Next visit: 4 pairs short", "▲ Pain map moves over time".
  - The yellow key is renamed "needs more data or caution"; ○ is kept for "not checked".
- **§1 "Is any setting proven better than today's?"** Per side, a three-row comparison (rate, pulse width, current) against Today, Suggested and Difference, with "same" where nothing changes. Then the gain as a sentence plus the gain bar: interval drawn in #8C8C8C, ends labelled "worse ← → better", unit "pain points". The stopping rule is one line.
- **§2 "Where have currents been tried, and what does the fit predict?"**
  - Hero: current maps as small multiples, one row per stream (home surveys, clinic sheets), about 240 px squares, **one shared scale and key per card**, the safe ceiling drawn as a dashed line labelled "safe ceiling 4.5 mA" with hatching beyond it, and direct labels "today" and "best".
  - Three one-line checks sit under each square.
  - The caveat is one sentence in `caution` with ▲; its numbers (0.41, 0.57, 611 ratings) go into the fold, which stays mounted.
  - "Pulse widths: separate | pooled" is a segmented control in the section header.
- **§3 "Can closed loop start?"** The two allowed pairs as sentence blocks with ✓ or ✕ and "Why not", then the four checks. Fold: the other 19 combinations, in a table with sentence-case 12.5 px headers.
- **§4 "What must the next visit deliver?"** One line (date, rate, pulse widths, ceiling, about N minutes) and "Make Google sheet". The two ladders drawn as step plots of current against step number, with the ceiling as a dashed line. The exploratory ladder follows under a hairline, not in a box. The home schedule sits inside this section. The frequency bands are ticks on an 8–30 Hz axis, with flagged centres drawn as hollow rings and labelled where the rate's multiple folds onto them ("rate ×4 → 30 Hz").
- **Footer:** the evidence base as a key and value row. The accessible text keeps the pinned prefix "Evidence base: N stretches of unchanged settings · M pain reports used".

### 4.3 Closed-Loop: "Can this setting be programmed, and what do I enter?"

- **Header controls:** pain score, and clinic-sheet ratings as a plain on/off switch (the red outline goes). "Load a saved band file" and "Clear" move into an overflow menu.
- **Abstract:** the single verdict line from decision 242, and the band as an eyebrow line: "L 1-3+ · 24.5 Hz · pain score NRS". The status list uses the existing red and yellow bullets, **worded exactly as today**.
- **§1 "What do I enter?"**
  - The values to enter, only when the device allows them, with a "Programmed today" column.
  - The safe-ceiling line: "Capped at the 4.5 mA safe ceiling; the highest current measured was 4.8 mA".
  - "Sign and print" as the one primary button.
  - A 4 px left rule in `ink`, or `refused` when blocked, is the only accent. No 2 px border.
- **§2 "Which band?"** The band-choice grid on the shared diverging key with labelled ends. Allowed pairs come first in a segmented control; the others are greyed with their reason.
- **§3 "Does the evidence hang together?"** Three small-multiple dot-and-interval strips with zero aligned, each labelled "Current → band power", "Band power → pain", "Current → pain". Value and interval sit at the dot; hollow dot means not certain, filled means certain. The triangle drawing and the coherence table are replaced by one sentence per question. Fold: counts, partial correlation and resampling.
- **§4 "Does the device allow it?"** Counts: "Refuses (n) · Could not check (n) · Allowed (n)". Refused rows are open, with ✕ in `refused`. Fold: "Notes, not blocking".
- **Supplementary (folded):**
  - S1: does the band mean the same thing at every stimulation state (stability, odds ratios with intervals)?
  - S2: how much band power changes per milliamp, measured three ways;
  - S3: what the automatic adjustment would have done ("Simulated, not measured. Decides nothing."), with lines labelled directly;
  - S4: the switching point, the device units and the month-by-month check (the three analyst panels, with "frozen PSD→LSB model" labels removed).

---

## 5. Files that change

**Theme** (`Client/src/assets/theme/`):
- `base/colors.js`: new neutral scale, `link`, and `status.{refused,caution,notAssessed}`. Removes the pink primary, gradients, social-media colours, coloured shadows and the badge colours. `text.main` and `secondary.main` become `ink3` or darker.
- `base/typography.js`
- `base/borders.js`
- `base/boxShadows.js`
- `base/globals.js`: body on `page`, tabular numbers.
- new `base/dataColors.js`
- `components/card/index.js`
- `components/button/*`
- `components/sidenav.js`
- `components/appBar.js`
- `components/breadcrumbs.js`
- `components/tabs/*`
- `components/tooltip.js`
- `theme-rtl.js`: mirror the same tokens.

**Shell:**
- `Client/public/index.html` and `manifest.json`: fonts, name, theme colour.
- `Client/src/App.js` (brand name)
- `Client/src/routes.js`: a "Choosing stimulation settings" group with the three pages in decision order.
- `components/SideMenu/SidenavRoot.js` and its styles: flat and light.
- `components/Navbars/DashboardNavbar/*`: flat 56 px header with page title and participant code.
- `assets/translation.js`
- `layouts/DatabaseLayout/DashboardLayout.js`: text column and spacing.

**Shared page pieces:**
- new `Client/src/views/Reports/paper/`: `PageHead.js`, `Section.js`, `Figure.js`, `Caption.js`, `Fold.js`, `StatusList.js`
- new `Client/src/views/Reports/figureStyle.js`: font, ticks, grid, axis line, config, and scales taken from `dataColors`.
- `ClosedLoopSim/palette.js` and `StimOptimizer/typeScale.js` become re-exports of the theme tokens.
- `legibleText.js` is deleted once `text.main` passes contrast.

**Pages:**
- Biomarkers: `Biomarkers/index.js`, `BiomarkerHeatmapGrids.js`, `gridReadouts.js`, `binarizationModel.js`, `BiomarkerDataTimeline.js` (colours only, through the timeline-layout skill), `BiomarkerAnalytics.js`, `MatchWindowBand.js`, `BinarizationPreview.js`, `CalibrationInEffectPanel.js`, `ControlAnalyses/figures.js`, `ControlAnalyses/ControlAnalysesCard.js`
- Stim Optimizer: `StimOptimizer/index.js`, `StatusLine.js`, `DecisionStrip.js`, `GainBar.js`, `CurrentMapCard.js`, `CurrentMapScheduleCard.js`, `SensingEvidenceTable.js`, `TitrationSessionCard.js`, `TwoStagePlanCard.js`
- Closed-Loop: `ClosedLoopSim/index.js`, `DecisionCard.js`, `EvidenceTrianglePanel.js`, `DeviceRuleLedger.js`, `BandSweepGridPanel.js`, `ClosedLoopSimulationPanel.js`, `DeploymentRocPanel.js`, `LsbPowerPanel.js`, `EraRefitPanel.js`, `ThreeSourceResponsePanel.js`, `DeploySignoffCard.js`, `WhatWouldChangeThis.js`

**Not touched:** `database/resultCache.js`, `database/useCachedResult.js`, `views/Reports/RecomputeBar.js`.

**Order of work:** tokens first, as a style-only commit with no text changes. Then one commit per page. The frontend bundle must be rebuilt after each (CLAUDE.md §8 rule 2).

---

## 6. Jest pins that would change

- `legibility.test.js`: the hex values it expects become token values. Extend it to reject fill inks used as text (`color: PAL.fail`, `PAL.pass`, #D55E00, #009E73), and drop the "label in its line's hue family" rule for timeline lanes (labels become `ink` with a coloured tick).
- The page-level legibility checks from decisions 258 and 259, and `threePagesNoSpectrumWord.test.js`: expected colours change. The spectrum-word rule stays.
- Biomarkers referent test (about line 177): pins `fontWeight '700'` on the L 1-3+ search lines; those lines become weight 400.
- `gridReadouts.test.js`: pins "117 ratings, q = 0.0022", "(about 98 independent)", the "corrected q … established" readout, and /tick/, /cross/, /amber/ in the stability text.
- `DeploymentJumpLinks.order.test.js`: section order and labels change.
- Closed-Loop `DecisionCard` and `panels.payload` tests: pin "SIGNS AGREE" / "SIGNS DISAGREE" and the E1/E2 control-law sentences.
- `EvidenceTriangle.*.test.js`: caveat and adjusted-line text.
- `DeviceRuleLedger` tests: /VIOLATED · 1/, /CANNOT BE EVALUATED · 4/ and the other bucket headings.
- Simulation panel: the pinned sentence "Closing the loop moves time at the upper amplitude limit from 26.5% to 23.8%" is kept as it is.
- Stim Optimizer `pageOrder` test: the "Evidence base: …" prefix is kept as accessible text.
- `StimOptimizer.designReview.test.js`: the phrase "blue is better than today and orange worse" and the #0072B2 / #E4E4E4 / #D55E00 colour stops are both kept.
- `ControlAnalysesCard.test` and `BandDetector.test`: some reading strings.