# BRAVO design specification: a quiet clinical instrument

> **Status, 2026-09-26.** This is the one current design specification for the three analysis
> pages. It was built (decision 320), corrected where the code did not match it (321), extended by
> the taste follow-up (322), and amended by the PI's later rulings (324, 325). Each rule a later
> decision changed carries a dated "Amended" note beside it; the text above each note is the rule
> as first written. The taste audit beside this file (`TASTE_AUDIT.md`) stays: page code cites its
> item numbers (C1-C12, D1-D14). The two proposals and the five evaluations this was merged from
> are archived in `docs/archive/2026-09-26/design/design_2026-09-26_minimalist_redesign/`.

**Base: Proposal 1** (one typeface, near-black text on white, one accent colour, red kept for safety only, answer first). **Taken from Proposal 2:**
- a third visible state, "not checked", so that a check that could not run never looks like a pass (decisions 9 and 176);
- a caution ink that is always paired with a glyph;
- the right side drawn in orange (#E69F00), so it no longer clashes with high pain in vermillion;
- the nine-stop diverging scale;
- every section built as a question, a one-sentence answer and one figure;
- a shared set of page components under `Views/Reports/paper/`;
- one line under the title naming the participant and the pain score.

I recomputed every contrast ratio below with the WCAG formula; none is copied from the proposals.

---

## 1. Principles

1. The page opens with its answer. The first sentence on every page answers that page's question.
2. Red means one thing only: the device refuses, or the value is above the safe current ceiling. Red always comes with ✕.
3. Colour belongs to the data. Page text is black and grey; the only exceptions are the answer accent and the three state inks, and each state ink always has its glyph.
4. Labels go on the data, not in legend boxes. Small multiples share one scale and one key.
5. Numbers, their meaning and the safety wording do not change. Only how they are shown changes.

---

## 2. Tokens

New file: `Client/src/assets/theme/base/tokens.js`. `colors.js`, `typography.js`, `borders.js`, `boxShadows.js` and `globals.js` read from it, and pages import from it. No page file holds a hex value of its own.

### 2.1 Surfaces and lines (never text)

| Token | Hex | Use |
|---|---|---|
| `surface` | #FFFFFF | cards, figures |
| `page` | #FAFAF8 | window background |
| `fillMuted` | #F4F4F1 | table header band, fold rows, the selected table row |
| `rule` | #D9D9D6 | hairlines and dividers (1.41:1; not for text or for a meaningful graphic) |
| `graphic` | #8A8A8A | axis lines, interval bars, reference lines (3.45:1 on white, 3.30:1 on page; meets the 3:1 minimum for graphics; **never text**) |

### 2.2 Text inks

Contrast is given on white / page #FAFAF8 / fillMuted #F4F4F1.

| Token | Hex | Contrast | Use |
|---|---|---|---|
| `ink` | #1A1A1A | 17.40 / 16.65 / 15.79 | titles, answers, numbers, pass rows (with ✓) |
| `ink2` | #3D3D3D | 10.86 / 10.39 / 9.86 | body prose |
| `ink3` | #5E5E5E | 6.48 / 6.20 / 5.88 | captions, axis ticks and titles, secondary text. **This is the lightest text grey allowed.** |

The following are deleted as text colours: #7b809a (3.9:1), #6C757D, #6E6E6E, #6A6A6A, #adb5bd, #aaa/#bbb, and every other literal grey.

### 2.3 Meaning inks (text-safe; each has a tint for bullet fills)

| Token | Hex | Contrast on white / page / its own tint | Glyph | Meaning |
|---|---|---|---|---|
| `accent` | #0B5CAD | 6.67 / 6.38 / 5.98 on #EEF3FA; white text on it 6.67 | none | the decision answer, the single primary button, the selected tab or cell, the active navigation item. Not for chart series and not for decoration. |
| `refused` | #B42318 | 6.57 / 6.29 / 5.85 on #FBEFEE; white on it 6.57 | ✕ | the device refuses; above the safe ceiling |
| `caution` | #8A5A00 | 5.93 / 5.67 / 5.46 on #FBF5EA | ▲ | needs more data; not yet certain; moves over time |
| `notChecked` | = `ink3` #5E5E5E | 6.48 / 6.20 / 5.88 on fillMuted | ○ | could not be checked (a check that cannot run still blocks, but is counted separately) |
| pass | = `ink` | 17.40 | ✓ | passes. There is no green in page text. |

> **Amended 2026-09-26 by decision 322** (the PI's ruling on taste audit D14): red is for device
> refusals and the safe ceiling only. The row above first also said "blocks closed loop"; a
> statistical result that blocks closed loop (a setting not proven better, no usable sensing pair,
> a readiness row that is not usable) is drawn in `ink` with ✕, not in red.

Rules:
- Red (#B42318) and blue (#0B5CAD) are almost equally light (6.57 against 6.67), so the glyph is compulsory. Colour alone never carries a meaning.
- When a figure colour must appear as text, use its dark variant: vermillion → #A84300 (6.06 on white), bluish green → #00755A (5.69). #D55E00 (3.9:1) and #009E73 (3.4:1) are for marks and fills only.

### 2.4 Type

- **One face: IBM Plex Sans**, weights 400 and 600, loaded from Google Fonts in `public/index.html`. Fallback `system-ui, sans-serif`. Set `font-variant-numeric: tabular-nums` on `body` so mA and device-unit columns line up.
- Remove Roboto 300, Lato, the leaflet stylesheet and the extra Material Icons variants.

> **Amended 2026-09-26 by decision 322** (taste audit C8): the fonts, IBM Plex Sans and the icon
> font, are served from the application's own build, not loaded from Google Fonts.

| Role | px / line height | Weight |
|---|---|---|
| Page answer (status sentence) | 22 / 29 | 600 |
| Section title, written as a question | 18 / 25 | 600 |
| Lead answer under a section title; key numbers | 16 / 24 | 400 (the number itself 600) |
| Body, controls, tables, fold text | 14 / 22 | 400 |
| Caption, table header, axis title, figure tick | 12 / 18 | 400 |

- Use these five sizes and no others. The smallest is 12, which keeps a margin above the 11 px floor, and it applies to SVG and Plotly text as drawn on screen.

  > **Amended 2026-09-26 by decision 325(d):** one exception, the Biomarkers heat maps' hover
  > text, is 11 px (the page's 11 px floor, decision 304); the legibility test names it.
- Sentence case everywhere. No uppercase, no letter-spacing, and buttons included.
- Delete `fontSizeXXS` (10.4 px, below the floor), `d1`–`d6`, `fontWeightLight` and `fontWeightLighter`.
- Replace the uppercase 11 px `HEAD` style in `StimOptimizer/typeScale.js` with 12 px, weight 600, `ink3`, sentence case.

### 2.5 Space, width, radius, shadow

- **Spacing:** 4, 8, 16, 24, 32, 48, 64 and no other values (MUI factors 0.5, 1, 2, 3, 4, 6, 8).
  - Card padding 24 (32 at 1280 px and wider).
  - 32 between cards; 64 between sections.
  - 8 from a title to its answer; 16 from the answer to its figure.
- **Width:** the content column is at most 1120 px. Prose is at most `68ch`. Only the heat maps and the timeline may use the full column. On a phone, 16 px side gutters and no horizontal scroll on the page.
  > **Clarified 2026-09-26** (decision 321, and commit e623b998 for the Stim Optimizer page): a
  > table wider than a phone scrolls sideways inside its own card, capped at the card's width; the
  > page itself never scrolls sideways.
- **Radius:** 4 for inputs, buttons and chips; 6 for cards (`borders.js` → `{ none: 0, sm: 4, md: 6 }`).
- **Shadow:** none on cards, the navigation bar, the sidebar or buttons. Menus, popovers and tooltips only use `0 4px 16px rgba(0,0,0,.08)`. Delete `0 2px 0 #1A1A1A`.
- **Cards:** white, a 1 px `rule` border, no card inside a card. The decision card alone carries a 4 px left bar in `accent`, or in `refused` when the device refuses.

### 2.6 Dark mode

`Client/src/assets/theme-dark/` is marked unsupported for the three pain pages in this pass: they force the light theme. It gets its own later package with its own contrast table, rather than a guessed one.

---

## 3. Figure style

New file: `Client/src/views/Reports/figureStyle.js`. Every Plotly and SVG figure on the three pages imports it. Nothing else defines figure fonts, greys or configuration.

```js
// Client/src/views/Reports/figureStyle.js
import { T } from "assets/theme/base/tokens";   // ink, ink3, graphic, rule, surface, refused ...

export const FONT_FAMILY = "'IBM Plex Sans', system-ui, sans-serif";

export const PLOTLY_LAYOUT = {
  font: { family: FONT_FAMILY, size: 12, color: T.ink },
  paper_bgcolor: T.surface,
  plot_bgcolor: T.surface,
  margin: { l: 56, r: 72, t: 16, b: 44 },          // right margin holds direct labels
  showlegend: false,                               // direct labels instead
  hoverlabel: { font: { family: FONT_FAMILY, size: 12, color: T.ink },
                bgcolor: T.surface, bordercolor: T.rule },
  xaxis: {
    showgrid: false, zeroline: false,
    showline: true, linecolor: T.graphic, linewidth: 1,
    ticks: "outside", ticklen: 4, tickcolor: T.graphic,
    tickfont: { size: 12, color: T.ink3 },
    title: { font: { size: 12, color: T.ink3 }, standoff: 8 },
    automargin: true,
  },
  yaxis: {
    showgrid: false, zeroline: false,
    showline: true, linecolor: T.graphic, linewidth: 1,
    ticks: "outside", ticklen: 4, tickcolor: T.graphic,
    tickfont: { size: 12, color: T.ink3 },
    title: { font: { size: 12, color: T.ink3 }, standoff: 8 },
    automargin: true,
  },
};

export const PLOTLY_CONFIG = { displayModeBar: false, responsive: true, displaylogo: false };
// Amended 2026-09-26 by decision 324(a): figureStyle also exports PLOTLY_CONFIG_WITH_TOOLBAR,
// used by every figure that had a toolbar before the redesign (see section 3.2).

// Reference lines: chance, zero, the safe ceiling. Always labelled at the line's end.
export const REF_LINE      = { color: T.graphic, width: 1, dash: "dash" };
export const CEILING_LINE  = { color: T.refused, width: 1.5, dash: "dash" };   // label "safe ceiling 4.5 mA" in T.refused
export const MONTH_GRID    = "#EEEEEC";   // the timeline only, month lines only

// Direct label helper: text at the right end of a series, in ink (or the series' text-safe ink).
export const directLabel = (x, y, text, color = T.ink) => ({
  x, y, text, xanchor: "left", xshift: 6, showarrow: false,
  font: { family: FONT_FAMILY, size: 12, color },
});

// SVG figures: draw at the container's real pixel width (useMeasuredWidth), never viewBox-scaled,
// so 12 px text stays 12 px on screen; below 480 px the figure scrolls inside its card.
export const SVG_TEXT = { fontFamily: FONT_FAMILY, fontSize: 12, fill: T.ink3 };
```

### 3.1 Colour scales

New file: `Client/src/assets/theme/base/dataColors.js`.

```js
// Okabe-Ito, fixed order. Marks and fills only; text uses T.ink or the *_TEXT variants.
export const CATEGORICAL = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"];

export const SIDE      = { left: "#0072B2", right: "#E69F00" };    // every page, always
export const PAIN      = { high: "#D55E00", low: "#0072B2", middle: "#BDBDBD" };
export const CONTEXT   = "#8C8C8C";                                 // 3.36:1, grey marks for context
export const TEXT_VARIANT = { "#D55E00": "#A84300", "#009E73": "#00755A" };

// Diverging, blue -> light grey -> vermillion. The ends and midpoint keep the
// StimOptimizer.designReview.test.js colour-stop pin (#0072B2, #E4E4E4, #D55E00).
export const DIVERGING = [
  [0.000, "#0072B2"], [0.125, "#3F8FC4"], [0.250, "#86B6D8"], [0.375, "#C4DAEA"],
  [0.500, "#E4E4E4"],
  [0.625, "#F1CDB0"], [0.750, "#E8A273"], [0.875, "#DE7B3A"], [1.000, "#D55E00"],
];

// Fixed symmetric ranges, printed on each key; values beyond saturate (the hover prints the true value).
export const RANGE = {
  correlation: [-0.5, 0.5],
  areaUnderCurve: [0.25, 0.75],          // centred on 0.5 = coin toss
  // current maps: +/- the largest |predicted pain - today's| across every square on the card
};

// Sequential (cividis), for ordered quantities: frequency lanes, counts.
export const SEQUENTIAL = ["#00204D", "#213D6B", "#555B6C", "#7B7A77", "#A59C74", "#D3C064", "#FFE945"];
```

### 3.2 Marks

| Element | How it is drawn |
|---|---|
| Colour key | A thin bar, 8 px tall, above each heat map or once per row of small multiples. Its ends are labelled in words in `ink3` ("falls with pain ← 0 → rises with pain"; "lower in high pain ← 0.5 coin toss → higher in high pain"). |
| Best-cell ring | `ink`, 1.5 px, with a 1 px white outline. The ring that marks "clears the 22-band correction" is 2.5 px. |
| Stability, drawn inside a cell | Shape only, in `ink` with a white outline: ✓ same, ✕ different, ? cannot tell. No green or red. |
| Hollow and filled | Hollow = not certain / clinic-sheet rating. Filled = certain / home survey. The meaning is stated once, in the caption. |
| Frequency ticks | True band centres ("8.5, 11.5 …") or round 10/15/20/25/30 Hz on a linear axis. Never `toFixed(0)`. |
| Zoom toolbar, gridlines, legend boxes, titles on the canvas | None. The figure's title is its card's question. |

> **Amended 2026-09-26 by decision 324(a):** the figure toolbar (save as picture, zoom, pan) is
> back on every figure that had one before the redesign, so reviewers can save figures for the
> deployment record: the Closed-Loop ROC curve, feature histogram, forward-chained area, per-state
> refit, simulation, three-source and power-curve figures, and the Biomarkers sliding correlation
> and calibration figures (`PLOTLY_CONFIG_WITH_TOOLBAR`). The timing histogram has its older zoom
> and pan toolbar, with no picture export. Figures that never had one stay without: the heat maps
> (decision 88), the device-readings gauge, the current map and the high / low preview. Gridlines,
> legend boxes and titles on the canvas stay off.

---

## 4. Page rules

1. **How a page opens:**
   - the title, written as a question;
   - one `ink3` line: "RCS08 · pain score Left Leg VAS" (the de-identified code, never the uid);
   - the **status sentence** (22 px, from the server where the server already writes it);
   - a **status list** of at most five items, each five words or fewer and each with its glyph: ✕ refused, ▲ caution, ○ not checked;
   - on Stim Optimizer and Closed-Loop, the **ceiling line**, read from the server and never typed in: "Safe current ceiling: 4.5 mA left, 4.5 mA right (set by the PI). Nothing above it is offered on this page."

   > **Amended 2026-09-26 by decision 325(a):** the menu, breadcrumb and browser-tab names are
   > the old page names again, "Biomarkers exploration", "Stim optimizer" and "Closed-loop
   > deployment"; each page's own question heading stays as its title. (Taste audit C7 had set the
   > browser tab to the page's question; 325(a) replaces that.)
2. **Controls come next, in one row.** The pain-score selector is first: a plain outlined select with the note "Every chart below uses this score." At most three controls are visible; the rest go under "More options". Developer actions (load a saved band file, clear, stored results) go in one ⋯ menu. The recompute bar stays exactly as it is.
3. **At most four open sections, then "Background" (folded).** Every section has:
   - a question as its title;
   - a one-sentence answer carrying the number and its meaning;
   - one figure, or a short table;
   - at most three sentences of reading;
   - at most one "How this was worked out" fold.
4. **Folds:**
   - Fold methods, alternative views, rows for combinations the device refuses today, research checks and calibration.
   - Never fold a device refusal, the ceiling, "not a value to program", or a "held, not refused" note.
   - No fold inside a fold. A fold is one 14 px row, "▸ Label (what is inside)".
   - Folded children stay mounted, so jest tests that read folded text still find it.

   > **Amended 2026-09-26 by decision 325(e), Stim optimizer page only:** its three very long
   > sections (the current map, "Can closed loop start?" and the next visit) open and close from
   > their title and start closed, their contents mounted; a jump link to a closed section opens
   > it. The current map's out-of-sample caveat stays in the open while its section is closed
   > (decision 235). The page head, with its status list and ceiling line, is never folded.
5. **Tables with more than five columns** become aligned comparisons (Today | Suggested | Difference) or sentences. Headers are 12 px, sentence case, `ink3`, on `fillMuted`.
6. **One primary button per card:** accent fill, white text, 600, 36 px tall. Secondary buttons: white with a 1 px `ink3` border.
7. **Jump links** sit in a slim contents row under the status list, never inside a card.
8. **Text sent by the server is shown as sent in this pass.** Where a wording row in §6 is produced by Python (status lines, stability words, notes, caveats, rule labels), it goes to a separate backend package that carries its own before/after field count on live data. The frontend packages change only text written in `Client/src`.

---

## 5. The three pages

### 5.1 Biomarkers: "Which brain signal tracks pain?"

1. **Head.**
   - The status sentence from the server's status line.
   - The status list "✕ 4 of 6 pairs refused today".
   - The pain-score selector, a plain outlined select. **The red outline is removed.**
   - The "Pain Biomarker Exploration" title card is removed.
2. **§1 "Does band power rise or fall with pain?"**
   - The six pair thumbnails as small multiples, 120×60 px, on the **same ±0.5 scale** as the large maps, labelled above at 12 px. Refused pairs are greyed and keep ✕ "Refused today". The selected pair has a 2 px `accent` underline.
   - The two large maps side by side, with a shared key, true-centre ticks, the dark best-cell ring and stability shown by shape.
   - Hover: "correlation −0.31 · 117 ratings (about 98 independent) · p 0.002 after allowing for 22 bands".
   - Clicking a cell opens the scatter, with direct labels "high pain", "low pain", "○ clinic sheet" and "r = …" at the end of the fitted line.
   - One `ink3` caveat line above the maps.
   - The "How to read this" drawer at 14 px weight 400.

   > **Amended 2026-09-26 by decisions 324(b) and 325(c, d).** The correlation is written "R";
   > "for this square alone" is gone. The value after the 22-band correction (a Benjamini-Hochberg
   > q from the server) is printed as "q ... (p corrected for testing 22 bands)" on the hover and
   > the pinned-cell line, never as "p ... after allowing for 22 bands"; the plain per-square p is
   > unchanged. Every p and q has at most two decimals ("p < 0.01" below 0.005); R and the area
   > under the curve have two decimals. The hover text is 11 px (see section 2.4). The left map is
   > titled "R with pain" and the right "High vs Low Pain Logistic classification" (the PI's
   > wording; the number it draws is the area under the curve of a rank comparison). Titles, keys,
   > maps, the clicked square's statistics and its two plots share rows across the two columns, so
   > both maps start at the same height and the scatter and violin do too.
3. **§2 "How are reports paired with recordings?"**
   - Folded to one line: "Paired within ±60 min · each report picks its recordings · up to 3 per report · home surveys only · Change".
   - Opened, it shows match window, split rule and clinic sheets. The other five controls sit under "More options".
   - Each control has one sentence of 15 words or fewer under it. The "Expand descriptions" button is removed. The timing histogram is this section's figure.

   > **Amended 2026-09-26 by decision 325(b):** every matching control sits behind one large bold
   > "Adjust matching parameters" button, closed by default, with the settings in force printed
   > beside it. It opens ONE compact panel holding the match window, the split, the direction, the
   > clinic-sheet switch, the cap per report, the gap, the length of signal, reuse and the high /
   > low split's own controls (the preview with its cut handles). There is no "More options" row
   > and no separate fold rows here; page text that pointed at "the matching card" or "the
   > histogram card" names the button.
4. **§3 "What was recorded, and when?"** The timeline:
   - the title moves to the card header, the legend border goes, ticks are 12 px, month gridlines are #EEEEEC;
   - lanes use `SEQUENTIAL` (cividis), with frequency labels in `ink` beside a coloured tick;
   - the short legend reads "High pain · Low pain · Middle, not used · Device snapshot (PSD) · Patient button press · Daily device log".
   - **Gutter geometry and fonts are not touched.** Load the `bravo-timeline-layout` skill first.
5. **Background (folded):**
   - how each band's link with pain changed over time (shared `DIVERGING`, colour bar titled "correlation with pain");
   - how band power is converted to device units (the two constants stay visible when open; direct labels replace the legends);
   - checks against chance and against the current, run offline;
   - the 2026-09-21 search, opening on one plain sentence and then 14 px weight 400.

### 5.2 Closed-Loop: "Can this setting be programmed, and what do I enter?"

1. **Head.**
   - Pain score, and clinic-sheet ratings as a plain on/off switch in `accent`. **The red outline goes.**
   - "Load a saved band file" and "Clear" move to the ⋯ menu.
   - Contents row.
2. **Decision card** (4 px left bar):
   - an eyebrow line "L 1-3+ · 24.5 Hz · pain score NRS";
   - the verdict at 22 px;
   - red ✕ and caution ▲ bullets **worded exactly as today**;
   - the values to enter, only when the device allows them, with a "Programmed today" column and the capped-ceiling note unchanged;
   - "Sign and print" as the one primary button;
   - one Details fold.
3. **§1 "Which band?"**
   - The band-choice grid on `DIVERGING`, with its ends labelled "pain lower when power high / higher", 0.5 marked "no relationship".
   - Pair tabs as a segmented control: the two allowed pairs first; the others greyed, each with its reason.
4. **§2 "Does the device allow it?"**
   - Three counts in the open: "Refuses (n) · Could not check (n) · Allowed (n)". Refused rows stay open in `refused` with ✕, their wording unchanged.

     > **Amended 2026-09-26 by decision 324(c):** the counts add up. "Allowed" counts only rules
     > that passed; rules that passed with their value shown and the non-blocking notes get their
     > own counts in the open, and the line ends with the total, for example "Refuses (1) · Could
     > not check (0) · Allowed (20) · Passed, value shown (6) · Notes, not blocking (25) of 52
     > rules checked".
   - Deferred, advisory and pinned rows go under "Notes, not blocking".
5. **§3 "Does the evidence hang together?"**
   - Three aligned dot-and-interval strips, zero aligned, named "Current → band power", "Band power → pain" and "Current → pain". The value and interval are printed at the dot; hollow means not certain.
   - The triangle drawing and the four-column coherence table become one sentence per link.
   - Counts, the reading with the current taken out, and resampling go in the fold. The adjusted line keeps its words.
6. **§4 "Does the band mean the same at every stimulation state?"** One sentence, then the per-state odds-ratio table (off / low current / high current) with intervals, and the "measured on" date.
7. **Background (folded):**
   - how much band power changes per milliamp, measured three ways;
   - "What the automatic adjustment would have done: simulated, not measured, decides nothing", with lines labelled directly and no M-codes in visible text;
   - the switching point, device units, and the month-by-month check. Remove the "frozen PSD→LSB model" tier labels.

All text in the fill inks moves to `TEXT_VARIANT` or `ink`.

### 5.3 Stim Optimizer: "Should today's setting change, and can closed loop start?"

1. **Head.**
   - Status sentence: "Keep today's setting on both sides; closed loop cannot start."
   - The ceiling line.
   - Status list: "✕ No usable sensing pair · ▲ Next visit: 4 pairs short · ▲ Pain map moves over time". Its key reads "✕ blocks · ▲ needs more data or caution · ○ not checked".
2. **§1 "Is any setting proven better than today's?"**
   - Per side, a Today | Suggested | Difference comparison with one row each for rate, pulse width and current; a zero difference reads "same".
   - The gain as a sentence, then the gain bar: interval in `graphic`, point in `accent`, ends "worse ← → better", unit "pain points".
   - The stopping rule in one line.
3. **§2 "Where have currents been tried, and what does the fit predict?"**
   - Small multiples: one row per stream (home surveys; clinic sheets), squares of about 240 px (responsive, square aspect).
   - **One shared colour range and one key per card.**
   - The ceiling drawn as a `CEILING_LINE`, labelled "safe ceiling 4.5 mA", with light hatching beyond it. Direct labels "today ×" and "best ★".
   - Three one-line checks under each square.
   - The caveat in one ▲ sentence, its numbers in the mounted fold.
   - "Pulse widths: separate | pooled" as a segmented control in the section header, with "Show explanations" as a text link.
4. **§3 "Can closed loop start?"**
   - The two allowed pairs as sentence blocks with ✓ or ✕ and "Why not".
   - The four checks.
   - The other 19 combinations in a folded table with sentence-case headers.
5. **§4 "What must the next visit deliver?"**
   - One line (date, rate, pulse widths, ceiling, about N minutes) with "Make Google sheet".
   - Two ladders as step plots of current against step number, with the ceiling dashed and the held side labelled.
   - The exploratory ladder below a hairline, not in a box.
   - The band ticks on an 8–30 Hz axis; flagged centres as hollow rings labelled "rate ×4 → 30 Hz"; the PI's wording "carries a folded multiple of the stimulation rate" kept.
   - The home schedule, including the "In force, above today's ceiling" line.
   - One "Why this design" fold.

   > **Amended 2026-09-26 by decision 325(f):** in the clinic sheet's tables an empty cell is left
   > blank, not "not given" (this replaces taste audit C9 for that sheet only; elsewhere an empty
   > cell is still a word, never "—"). Sections 2, 3 and 4 of this page start closed (see section
   > 4, rule 4).
6. **Footer:** the evidence base as a quiet key/value row. Its accessible text keeps "Evidence base: N stretches of unchanged settings · M pain reports used".

---

## 6. Wording (current text → plain replacement)

Rows marked **S** come from the server and go to the backend package (§4 rule 8).

| Current | Plain replacement |
|---|---|
| q = 0.0022 / corrected q | p 0.002 after allowing for all 22 bands tested **(amended below: 324(b))** |
| AUC | how well it tells high pain from low (0.5 = coin toss, 1 = perfect) |
| Pearson r … (uncorrected) | correlation for this square alone, not allowing for the 22 bands tested **(amended below: 325(d))** |
| Mann-Whitney; high n=…, low n=… | rank test; N high-pain and M low-pain reports (the test's name kept in the drawer only) |
| Correlation with pain — depends only on matching | Does band power rise or fall with pain? **(map title amended below: 325(c))** |
| High vs low pain (AUC) — also depends on the high / low cuts above | Does band power tell high-pain reports from low-pain ones? **(map title amended below: 325(c))** |
| Band power (LSB); Device LFP power (LSB); Timeline LSB | Band power (device units, LSB), with LSB defined once per card |
| 22-band correction | the allowance for testing 22 bands at once |
| established / supported / not resolved **S** | kept as words; each defined once in the key ("clearly above zero and past the 22-band allowance" / "range wholly above zero" / "cannot tell") |
| Report-first / Neural-first / Neural-first, pre-report | each report picks its nearest recordings / each recording picks its nearest report / each recording picks the next report after it |
| Tertile (low/high, drop middle); Low ≤ 33ᵗʰ pct | lowest and highest thirds of ratings; the middle third left out |
| Window reuse / Allow reuse | let one stretch of recording answer more than one report |
| neural sample(s) | band-power readings |
| montage / patient event | contact-survey recordings from clinic / snapshots the patient triggered from her remote |
| 1 MAD of the ratio; gated or flagged | typical spread of the ratio; left out as too short or far from the rest |
| typical miss ×1.05 | median fold error 1.05 |
| out-of-sample score (0.5 is chance) | how well it predicts pain in weeks it was not fitted on (0.5 = coin toss) |
| shuffled-data 95th | the level chance alone reaches 1 time in 20 |
| Filled: survives correction … (q < 0.05) | Filled dot: still clear after allowing for the bands tested |
| vas / left_leg_vas (raw keys) | the page's pain-score labels ("Left Leg VAS") |
| Control analyses | Checks against chance and against the current (run offline) |
| E1 / E2 / E3; edge | Current → band power; Band power → pain; Current → pain; "link" |
| control law | what the device's automatic adjustment assumes |
| SIGN − (INTERVAL SPANS ZERO) | Falls as current rises; the range crosses zero, so not yet certain |
| SCREENING STATISTIC, NOT A MEASUREMENT | read off the whole history, where current and time move together; not a measured effect of current |
| n observations in k clusters; Partial correlation | n readings from k separate groups; correlation after taking the current out |
| CL-DBS simulations; M0 / M1 / M2 / M3 | What the automatic adjustment would have done (simulated); as recorded / straight-line response / peaked response / range over resampled days |
| timing regimes; settling time τ; onset, blanking | two sets of timing settings; how long power takes to settle; the wait before switching and the pause after it |
| the capture range | the low and high currents at which band power was measured |
| payload; load-bearing; predicate; derived by subtraction | removed from visible text |
| VIOLATED / CANNOT BE EVALUATED / DEFERRED … | Refuses / Could not check / Counted under another rule (the refusal sentences themselves unchanged) |
| stim era; band×era LRT; Per-era CIs | stimulation state (off / low / high current); test of whether the link differs between states; 95% range for each state |
| False / True positive rate | low-pain moments flagged as high (%) / high-pain moments caught (%) |
| Oriented band power (standardized, cut-point scale) | band power, scaled so 0 is the switching point |
| Forward-chained held-out AUC; in-sample AUC | tested on each later week after training on the weeks before; measured on the data it was fitted to |
| Detection power for AUC > 0.5 (%); DEFF; CI-low | chance of detecting a real link with pain (%); counted as about m independent ratings; lower end of the 95% range |
| from frozen PSD→LSB model (…) | removed (the model was deleted in decision 218) |
| oriented log-power (comment) | removed (decision 202) |
| Load BandCandidate JSON | Load a saved band file |
| pooled slope (device units per mA) | change in band power per milliamp, all visits together |
| Time domain derived LSB / PSD derived LSB / Direct LSB recording | From the recording (TD) / From the device's 30-second snapshot (PSD) / The device's own band-power reading |
| gain over the setting in force ± 1 SD; pts | predicted change in pain against today's setting, with its uncertainty; pain points |
| search prefers (usable in closed loop) | suggested setting (one closed loop could use) |
| an extrapolation | a guess beyond any current this side has received |
| falls with current (clinic-visit differences removed) | power goes down as current goes up, after allowing for differences between clinic visits |
| power gap (scatter units) | the gap between the two measured power levels, in units of their own scatter |
| Closed loop: may it start on the frozen setting? | Can closed loop start on the rate and pulse width locked in beforehand? |
| Surface flat? | Do the predictions differ across currents by more than their own uncertainty? |
| pulse-width pairing; REDCap | left and right pulse widths together; home pain surveys |
| wash-in | the first minutes after a setting change, whose ratings are left out |
| 20 s post-ramp margin; settled settings | dropping the first 20 s after each current change; steps held long enough to read |
| ladder; joint corners | the planned sequence of currents stepped up and down; extra steps where both sides change together |
| stratum; Stage 1 / Stage 2; envelope | one group of settings fitted together; the open-loop search; closed loop; the range of currents closed loop may use |
| Pain map moves over time (†) **S** | The predicted pain at the same setting changed from one block of weeks to the next |
| Customized Analysis / Analysis Builder | Choosing stimulation settings |
| Biomarker Exploration / Open-Loop Stim Optimizer / Closed-Loop Deployment | Which brain signal tracks pain / Which current to try next / Closed-loop settings to program **(amended below: 325(a))** |
| UF BRAVO Platform | the PI chooses (for example "BRAVO Pain · UCSF") |

> **Amended 2026-09-26.** Five rows above were changed by later rulings:
> - **324(b):** the corrected value is printed as "q 0.002 (p corrected for testing 22 bands)" on
>   the Biomarkers heat-map hover and pinned-cell line and in the Closed-Loop "Choose a band"
>   tooltip; a corrected q is never written as "p".
> - **325(d):** the correlation is "R", and "for this square alone" is removed; p and q are
>   printed to at most two decimals ("p < 0.01" below 0.005), R and the area under the curve to two.
> - **325(c):** the two heat maps are titled "R with pain" and "High vs Low Pain Logistic
>   classification" (the PI's wording).
> - **325(a):** the menu, breadcrumb and browser-tab names are "Biomarkers exploration", "Stim
>   optimizer" and "Closed-loop deployment"; the question headings stay on the pages.

**Kept word for word:**
- "carries a folded multiple of the stimulation rate"
- "not a value to program"
- "Unmet:" / "Unchecked:" and the device-rule labels
- "held, not refused"
- "Capped at the 4.5 mA safe ceiling …"
- "blue is better than today and orange worse"
- "Closing the loop moves time at the upper amplitude limit from 26.5% to 23.8%"
- "Sign and print", "Export JSON"

---

## 7. Implementation status

> **Trimmed 2026-09-26.** This section first held the eight work packages (files to touch, jest pins
> to update, the build order). WP1 to WP7 are built, so that list is kept in git only: read
> `SPEC.md` at commit 1f12ce80. What stays true of it is below.

- **Built:** WP1 shared tokens and figure defaults (d5d380eb), WP2 app shell (9591f067), WP3
  Biomarkers page (7838f3e2), WP4 control-analysis card (ec8b8454), WP5 Stim Optimizer page
  (01db521d), WP6 Closed-Loop page (fceb8072), WP7 cross-page cleanup (700c3bbd), and the
  redesign audit (7090388c); all recorded as decision 320, with the fixes of 321 and the taste
  follow-up of 322.
- **Not built: WP8, server wording** (left on purpose in decision 320; section 4 rule 8 puts it after the PI rules). The section 6 rows marked **S** and the
  device-rule labels are written by Python. Changing them is a backend package of its own: each
  change proved on live RCS08 with a field count and a difference count (the differences must be
  sentences only), and both test suites rerun.
- **Still waiting on the PI** (decisions 320 and 322): the product name ("UF BRAVO Platform"), the
  dark theme (section 2.6), the timeline gutter's Arial, the faint PLANNING ONLY watermark, and the
  badge component's uppercase.
- **Standing rules from the plan:** a frontend change is followed by one serial `npm run build`
  (CLAUDE.md section 8 rule 2), jest, and a check that the served code-split chunks carry the new
  strings; the timeline goes through the `bravo-timeline-layout` skill, and the Stim Optimizer and
  Closed-Loop figures through the `bravo-stimoptimizer-figures` skill.

---

## 8. What not to change

- **The PI's files:** `Client/src/database/resultCache.js`, `Client/src/database/useCachedResult.js` and `Client/src/views/Reports/RecomputeBar.js`. They are not edited and not restyled; other code may only read them.
- **Every number and its meaning.** No value, interval, count, verdict or rounding that changes meaning. Frequency ticks show true centres. Saturated colour cells still show the exact value on hover.
- **Safety wording, word for word:** the safe current ceiling and its capped note, the device refusals ("Unmet:", "Unchecked:", the D-rule labels, "This configuration cannot be programmed"), "not a value to program", "held, not refused", and the PI's harmonic wording. Refusals keep red with ✕ and are never folded.
- **The floors:** no text under 11 px as rendered on screen (this spec uses 12 px or more); every text colour at least 4.5:1 on its actual background; meaningful graphics at least 3:1. (Amended 2026-09-26 by decision 325(d): the heat maps' hover text is the one place at 11 px.)
- **Plain JavaScript only;** no TypeScript.
- **The timeline's left-gutter geometry and fonts** change only through the `bravo-timeline-layout` skill.
- **Three-state checks:** "not checked" is never drawn as a pass.