# BRAVO design system: a quiet clinical instrument

The whole app uses near-black and greys, with one blue and one red. **Blue** marks the answer a clinician acts on. **Red** marks only what is unsafe or refused by the device. Everything else is black or grey text on white with plenty of space, in one typeface.

I edited nothing. All contrast ratios below were computed with the WCAG formula against white (#FFFFFF) and against the page background (#F7F7F5).

---

## 1. Design tokens

All tokens live in `Client/src/assets/theme/base/*`. Pages read them and hold no colour values of their own.

### 1a. Colours

**Text and lines**

| Token | Hex | On white | On page #F7F7F5 | Use |
|---|---|---|---|---|
| `ink` | #1A1A1A | 17.4:1 | 16.2:1 | headings, numbers, body |
| `ink2` | #3D3D3D | 10.9:1 | 10.1:1 | long body text |
| `ink3` | #5C5C5C | 6.7:1 | 6.2:1 | secondary text, captions, axis ticks (5.97:1 on the muted fill below) |
| `inkFaint` | #6B6B6B | 5.3:1 | 5.0:1 | the lightest grey allowed for text |
| `graphic` | #8A8A8A | 3.45:1 | — | graphics only (axis lines, interval bars). Graphics need 3:1. **Never text.** |
| `rule` | #D9D9D6 | 1.4:1 | — | hairlines and dividers only |
| `fillMuted` | #F2F2F0 | — | — | folded rows, table header band |
| `surface` | #FFFFFF | — | — | cards |
| `page` | #F7F7F5 | — | — | page background |

**The two colours with a meaning**

| Token | Hex | Contrast | Use |
|---|---|---|---|
| `accent` (the decision) | #0B5CAD | 6.7:1 on white; 6.0:1 on its tint #EEF3FA; white text on it 6.7:1 | the status line's answer, the one primary button, the selected cell or tab, the active navigation bar. **Never** decoration, links in prose, or chart series. |
| `danger` (safety only) | #B42318 | 6.6:1 on white; 5.85:1 on its tint #FBEFEE; white on it 6.6:1 | device refusals, the safe current ceiling, "cannot be programmed". **Always paired with a glyph (✕).** |

**Rules for the other states**

- **Caution** ("needs more data", "not assessed") has no colour of its own. Show it in `ink` with a hollow glyph (△ or ○). This removes the six ambers now in use (#8a5a00, #8A6100, #956400, #B17500, …).
- **Pass or allowed** is `ink` with ✓. A pass does not need to shout.
- Red and blue have almost the same lightness (1.01:1 between them), so hue and glyph must always tell them apart. That is why a glyph is mandatory.

**Figure colours** (for data marks only, never text)

- **Diverging scale** for correlation and predicted pain: #0072B2 → #6FA8D0 → #E4E4E4 → #E6A57A → #D55E00. The ends are Okabe-Ito blue and vermillion (colour-blind safe). Keeping #0072B2, #E4E4E4 and #D55E00 keeps the pin in `StimOptimizer.designReview.test.js` (the current-map colour stops).
  - The midpoint is a light grey, not white, so a cell near 0 is still visible on a white card.
  - Correlation range is fixed at ±0.5, the same on every pair, with values beyond it drawn at full colour.
  - The area-under-the-curve grids are centred on 0.5.
- **Sequential scale** (cividis, colour-blind safe): #00224E, #35456C, #666970, #948E77, #C8B866, #FEE838. Use it for frequency on the timeline and for rating counts.
- **Categorical scale**: Okabe-Ito in a fixed order: #0072B2, #D55E00, #009E73, #CC79A7, #E69F00, #56B4E9.
  - Left side is always #0072B2 and right side always #D55E00, on every page.
  - High pain is vermillion and low pain is blue.
  - #D55E00 (3.9:1) and #009E73 (3.4:1) are for marks only. Any word in those hues uses `ink`, or `danger` if it is a refusal.
- **Reference lines**: chance, zero and the ceiling are drawn in `graphic` #8A8A8A, 1 px dashed, with a direct label in `ink3` ("chance 0.5", "safe ceiling 4.5 mA"). The ceiling line uses `danger`.

### 1b. Type

One typeface: **IBM Plex Sans**, weights 400 and 600, with same-width digits turned on (`font-variant-numeric: tabular-nums`) so mA and power columns line up. The fallback is `system-ui`. Lato, Roboto, Arial and Helvetica all go.

| Role | px | Weight | Line height | Where |
|---|---|---|---|---|
| Page answer | 22 | 600 | 1.3 | the one status sentence at the top |
| Section title | 18 | 600 | 1.35 | "Today's setting", "Closed loop", "Next visit" |
| Card title | 16 | 600 | 1.4 | written as a plain question |
| Body | 14 | 400 | 1.55 | all prose, controls, tables |
| Secondary / caption | 12 | 400 | 1.5 | captions, table headers, figure titles, axis titles |
| Figure ticks | 12 | 400 | — | Plotly and SVG, drawn at true pixel size |

- Five sizes and no others. The smallest is 12 px, which leaves a margin above the 11 px floor.
- No uppercase and no letter-spacing, buttons included.
- Bold is used only for key numbers, and only once per sentence.

### 1c. Spacing, width, radii, shadows

- **Spacing scale**: 4, 8, 16, 24, 32, 48, 64. Use no other values.
  - Card padding: 24 px (32 px at 1280 px and wider).
  - Between cards: 32 px. Between sections: 64 px.
  - Title to content: 16 px. Between controls in a group: 16 px.
- **Width**: running text is capped at 68 characters (`maxWidth: '68ch'`). The content column is capped at 1120 px. Only the heat-map grids and the timeline may run full width.
- **Radii**: 4 px for inputs and buttons, 6 px for cards. Remove the 12 px to 160 px radii.
- **Shadows**: none on cards, the navigation bar or the sidebar. A single `0 4px 16px rgba(0,0,0,.08)` for menus, popovers and tooltips only. Remove the hard `0 2px 0 #1A1A1A` button shadows.
- **Borders**: cards are separated by space. At most a 1 px `rule` border, and never a card inside a card. The decision card alone gets a 3 px left bar in `accent`, or in `danger` when the device refuses.

### 1d. Figure style: one shared module, `Client/src/views/Reports/figureStyle.js`

- Font is inherited from the page. Ticks are 12 px in `ink3`; axis titles are 12 px, sentence case, and say units in words ("Band power (device units, LSB)").
- Axis lines are 1 px `graphic`. No gridlines, except faint month lines (#EEEEEC) on the timeline.
- The zoom toolbar is off everywhere (`displayModeBar: false`). Figures resize with their box (`responsive: true`).
- No legend boxes. Every series is labelled at its end, in its own colour or in `ink`. Colour keys are thin bars with the ends labelled in words.
- SVG figures are drawn at their real pixel width (measured, or `minWidth` with scrolling inside the card), so 12 px text never shrinks below 11 px.
- Small multiples share one scale and one key per row.

---

## 2. Page structure rules

1. **A page opens with its answer.** In order:
   - a 22 px status sentence that answers the page's question;
   - under it, at most four bullets of five words or fewer, each with a glyph: red ✕ for refusals, ink △ for caution;
   - one fixed line naming the safe ceiling when currents appear on the page: "Safe current ceiling: 4.5 mA left, 4.5 mA right (set by the PI). Nothing above it is offered here."
2. **Controls come next, in one row.** The pain-score selector is first, as a plain outlined select with the note "Every chart below uses this score." Nothing else sits in the header. Developer actions ("Load a saved band file", "Clear", "Stored results") go in one ⋯ menu. The recompute bar keeps its own look, because `RecomputeBar.js` is the PI's file.
3. **Three sections at most, and three to five open cards per page.** Each section opens with its own one-line answer.
4. **When to fold:**
   - Fold anything no decision on the page reads: method, provenance, research checks, calibration, rows for sensing pairs the device refuses today, and "How this was estimated".
   - Never fold a safety sentence, a device refusal or the ceiling.
   - A fold is a single 14 px row, "▸ Label (what is inside)". Folds keep their contents in the page even when closed, so tests that read text inside a fold still pass.
5. **One primary button per card.**
6. **Tables with more than five columns** become aligned comparisons (Today | Suggested | Difference) or plain sentences. Headers are 12 px sentence case.
7. **Every figure answers a question** written in its card title. Direct labels replace legends. Captions are one sentence.

---

## 3. Wording rules

1. The house rules' §2 replacement table is the dictionary. The terms that are flagged most often:
   - **q** → "p after allowing for all 22 bands tested"
   - **AUC** → "how well it tells high pain from low (0.5 = coin toss)"
   - **E1 / E2 / E3** → "Current → band power", "Band power → pain", "Current → pain"
   - **M0–M3** → "as recorded", "simulated, straight-line response", "simulated, peaked response", "range over resampled days"
   - **era** → "stimulation state (off / low / high)" or "calendar month", whichever the grouping really is
   - **LSB** → "device units (LSB)" on first use on each card
   - **control law** → "what the automatic adjustment assumes"
   - **stratum** → "one group of settings fitted together"
   - **Neural-first / Report-first** → "each recording picks its nearest report" / "each report picks its nearest recordings"
   - **REDCap** → "home pain surveys"
   - Raw score keys such as `left_leg_vas` always go through the pain-score label list.
2. Every card title is a question ("Does band power rise or fall with pain?").
3. No capitals for emphasis. Strings such as "SIGN − (INTERVAL SPANS ZERO)" become sentence case: "Falls as current rises · the range crosses zero, so not yet certain."
4. A number goes with its meaning in the same phrase: "0.62 (0.5 = coin toss)".
5. Never print a column name. Never print a decision number in page text.
6. Keep safety wording and the PI's advisory wording word for word: "carries a folded multiple of the stimulation rate", "not a value to program", the "Unmet:/Unchecked:" device labels, and "held, not refused". A short plain note may follow them.
7. Frequency is printed as its true centre: "23.5", never a rounded "24".

---

## 4. The three pages, top to bottom

### Biomarkers: "Which brain signal tracks pain?"

1. **Status sentence and bullets.** Example: "Allowed pairs today: L 1-3+, R 0-3+. On Left Leg VAS, after allowing for 22 bands, no band rises with pain." Then "✕ 4 of 6 pairs refused".
2. **Pain-score selector.** The red outline goes.
3. **Section "Which band tracks pain".**
   - Six pair thumbnails in one row, about 120×60 px, drawn on the same ±0.5 scale as the big maps. Refused pairs are greyed and keep "✕ Refused today".
   - The two maps side by side, each with its colour key ("falls with pain ← 0 → rises with pain"; "lower in high pain ← 0.5 coin toss → higher in high pain").
   - Frequency ticks at the true centres.
   - The best cell ringed in `ink` (#1A1A1A) with a white outline; stability shown by a glyph drawn inside (✓, ✕ or ?), not by green and red.
   - Clicking a cell opens the drill-down scatter, with direct labels "high pain", "low pain" and "○ clinic sheet".
4. **Section "How reports are paired with recordings".** Folded to one line, for example "Paired within ±60 min · report picks its samples · up to 3 per report · home surveys only · Change". Opened, it shows three controls, with the other five under "More pairing options". The timing histogram sits inside.
5. **Acquisition timeline.**
   - The title moves to the card header; the legend border goes.
   - Lanes use the cividis scale for frequency, with the frequency labelled at the lane.
   - Ticks are 12 px. Gutter geometry and fonts go only through the `bravo-timeline-layout` skill.
6. **Folded at the bottom:** how each band's link with pain changed over time; how band power is converted to device units (the two constants stay visible when open); research checks run offline.

### Stim Optimizer: "Should today's setting change, and can closed loop start?"

1. **Status sentence** ("Keep today's setting on both sides; closed loop cannot start."), then the ceiling line, then the bullets.
2. **Section "Today's setting".**
   - For each side, a Today | Suggested | Difference comparison, one row each for rate, pulse width and current. A zero difference reads "same".
   - A gain bar with the ends labelled "worse ← → better", "pain points", and its band drawn in #8A8A8A.
   - Under it, the current maps as small multiples: about 240 px squares, one shared colour range and one key per row, the ceiling drawn as a dashed `danger` line with hatching beyond it, and direct labels "today ×" and "best ★".
   - Three one-line checks under each square.
   - The caveat about current and pain in one sentence, with its numbers folded beneath.
   - "Pulse widths: separate | pooled" as a two-option switch in the card header.
3. **Section "Closed loop".** The two allowed pairs as sentences ("L 1-3+ at 55 Hz: 0 of 22 bands fall with current and rise with pain, so it cannot drive closed loop"), then the four checks. The nine-column grid for the other 19 combinations is folded.
4. **Section "Next visit".**
   - One line: date, rate, pulse widths, ceiling, about N minutes, and the "Make Google sheet" button.
   - Two ladder step diagrams (current against step, ceiling dashed).
   - The exploratory ladder below a hairline, with no box around it.
   - The home schedule.
   - One "Why this design" fold.
5. **Footer:** a quiet key/value row for the evidence base.

### Closed-Loop: "Can this setting be programmed, and what do I enter?"

1. **Decision card** (3 px left bar).
   - A small line above the headline: "L 1-3+ · 24.5 Hz · pain score NRS".
   - The headline at 22 px.
   - The red ✕ and ink △ bullets, word for word.
   - The values to enter, with a "Programmed today" column, and "Sign and print".
   - A Details fold.
   - The jump links move out of the card into a slim contents row under the page title.
2. **Section "Why".**
   - Device rules: three counts in the open (Refuses / Could not check / Allowed); the refusal rows stay open in `danger`.
   - The evidence: three aligned dot-and-interval strips named in words, the value labelled at the dot. The triangle drawing goes.
   - Whether the band means the same in every stimulation state, as one sentence plus the table of per-state odds ratios.
3. **Section "Background for the analyst"**, folded:
   - current and band power, measured three ways;
   - the simulation, titled "What the automatic adjustment would have done (simulated, not measured; decides nothing)", with direct line labels;
   - the switching point, device units and the per-state check. The labels left over from the deleted log-power model go.
   - The band-choice grid moves here, or sits as a compact first control above the decision card with its ends labelled in words.

---

## 5. Files that would change

- **Theme:** `Client/src/assets/theme/base/{colors,typography,borders,boxShadows,globals}.js`, `components/{card,button/*,sidenav,appBar,breadcrumbs,tooltip,table/*}.js`, and the matching `Client/src/assets/theme-dark/` files. Either map the tokens there or mark dark mode unsupported.
- **Shell:** `Client/public/index.html` (font, title, theme-color #0B5CAD, drop Lato and leaflet), `public/manifest.json`, `src/App.js` (brand name, which the PI chooses), `src/routes.js` (a first group "Choosing stimulation settings" holding the three pages in decision order), `components/SideMenu/*` (light sidebar with no shadow), `components/Navbars/DashboardNavbar/*` (flat 56 px bar with the participant code), `layouts/DatabaseLayout/DashboardLayout.js` (width cap), `assets/translation.js`.
- **New modules:** `Client/src/views/Reports/figureStyle.js`, and `Client/src/assets/theme/base/dataColors.js`, which replaces the page palettes. `ClosedLoopSim/palette.js` and `StimOptimizer/typeScale.js` would re-export from it.
- **Deleted:** `Client/src/views/Reports/legibleText.js` and its wrappers, once the theme's grey passes contrast.
- **Pages:** everything under `Views/Reports/Biomarkers`, `StimOptimizer`, `ClosedLoopSim` and `ControlAnalyses` swaps its colour values for tokens.
  - Do this in two commits: first a refactor that only swaps colours for tokens with no visible change, then the redesign.
  - `RecomputeBar.js`, `resultCache.js` and `useCachedResult.js` stay untouched.

---

## 6. Tests that would need changing

- **Legibility tests** in `Biomarkers/legibility.test.js`, `ClosedLoopSim/legibility.test.js` and the page source checks from decisions 258 and 259 assert literal greys. Rewrite them to assert the tokens, and extend them to reject `PAL.fail` or `PAL.pass` used as text colours and any colour value written outside the token files.
- **Wording pins** in `gridReadouts.test.js` ("q = 0.0022", tick/cross/amber), the referent test (bold search lines), `DeviceRuleLedger` (the capitalised group headings), the decision-card and evidence-triangle tests ("SIGNS AGREE", E1/E2 sentences), and `ControlAnalysesCard` and `BandDetector` readings.
- **Order and layout pins** in `DeploymentJumpLinks.order.test.js` and the Stim Optimizer page-order test ("Evidence base: …" prefix, card order).
- **Not affected:** `pageLayout.test.js` (the pain selector stays first and the constants stay visible) and the `designReview` colour-stop pin (the ends are kept).