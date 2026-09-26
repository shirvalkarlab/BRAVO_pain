# Design review: the Stim Optimizer and Biomarkers pages (2026-09-26)

This review is read-only. It changes no code. It applies the PI's ruling for the Closed-Loop page
of 2026-09-26 to the other two analysis pages:

- one status line;
- red bullets of five words or fewer for what the device refuses;
- yellow bullets for evidence that was not evaluated;
- details folded when the setting is allowed and supported;
- nothing said twice.

**Skills loaded and applied:** tufte-viz, tufte-test, scientific-visualization, dataviz,
design:ux-copy, design:design-critique, design:accessibility-review, bravo-stimoptimizer-figures
(for the Stim Optimizer panels) and bravo-timeline-layout (for the Biomarkers timeline). Four
more were added at the PI's request and loaded afterwards: design-taste-frontend (v2),
design-taste-frontend-v1, minimalist-ui and image-to-code. Section 4 says which rules were taken
from each of these and which were declined, and why.

**How the words were counted.** A temporary jest test rendered the whole Stim Optimizer page
against its saved RCS08 response (`StimOptimizer/__fixtures__/rcs08_stim_optimizer_two_stage.json`).
It also rendered the Biomarkers heat-map card and calibration panel against their saved responses.
It counted words that are visible on load and words inside a closed fold. The test was then
deleted.

**Limit of the counts.** The saved responses date from 2026-09-15 (the calibration one from
2026-09-20). The live page prints more than they do, because these blocks were added later:

- the sensing-rule sentence (decision 243);
- what the next visit must deliver (251);
- the ruling-5 line (255);
- the daggers (294);
- the stopping rule (245);
- the exposure line (243).

So every Stim Optimizer count below is **a lower bound**.

The Biomarkers top card (timeline, matching controls, binarization preview) needs live requests to
render. Its counts are **estimates from the page's string literals**, not a render.

---

## 1. Stim Optimizer page

**The decision it serves.** Should today's stimulation setting change? If not, what must the next
visit collect? A second question sits beside that one: can closed loop start? On RCS08 today the
answers are "no change proven", "a titration ladder and some repeated settings", and "no".

### 1.1 The cards in order, words visible on load / words folded (saved response of 2026-09-15)

| # | Card | Visible | Folded |
|---|---|---|---|
| 0 | Recompute bar | — | — |
| 1 | Readiness table ("N of 50 contact-and-rate combinations usable"), 22 rows × 12 columns | 443 | 530 |
| 2 | Decision strip ("No side has a setting proven better than today's") | 270 | 304 |
| 3 | Current map, the squares | 1,104 | 511 (1,227 / 611 with descriptions open) |
| 4 | Titration session to run next, including the 34-row clinic-sheet table | 2,095 | 532 |
| 5 | Home programming schedule | 447 | 0 |
| 6 | Closed loop: may it start? (four checks, two charts) | 682 | 934 |
| 7 | Evidence base footer | 39 | 0 |
| 8 | Control analyses (dropdown; one saved analysis shown) | about 40 plus the analysis | — |
| | **Total** | **at least 5,100** | **at least 2,800** |

At a reading pace of about 200 words a minute, the words visible on load take **25 minutes** to
read. A clinic visit cannot absorb that.

### 1.2 Top problems

**(a) One fact is stated in four to six places.**

- "No current can be recommended" appears in five places:
  - the decision strip, once per side;
  - the strip's folded reasons;
  - each square's heading ("no current can be recommended at this speed yet");
  - each square's closing sentence, which restates the three ✓/✗ check lines directly above it;
  - the plan card's folded record of how the answer was reached.
- "Closed loop cannot start" appears in four places:
  - the readiness headline;
  - the plan card's headline;
  - its check rows;
  - "Nothing was drawn up: 2 checks above block (...)".
- The safe ceiling (4.5 mA each side) is printed five times: the readiness caption, both titration
  sides, the home schedule and the current-limits check.
- Three sentences exist only to point at another card:
  - "This table is the evidence. Whether closed loop may start is decided by the four checks in the card … at the foot of this page";
  - "The per-contact evidence … is the readiness table at the top of this page";
  - "The in-clinic test to run next is the … card above".
- The stopping rule prints the same 45-word sentence for Left and then for Right.
- "Not enough data (N epochs, below the 8-epoch floor); no surface is drawn" is one line per unfitted
  rate. That is 15 lines in the saved response, 8 of them in the clinic-sheet section alone.

**(b) Text a clinician cannot use at the visit, visible on load.**

- The 34-row, 19-column clinic-sheet table inside the titration card: about 1,200 of the card's
  2,095 words. The "Make Google sheet" button already exports it.
- The per-side "why this design" prose.
- The 22-row readiness table. After the device's sensing-pair rule (decision 217), only 2 rows can
  ever be usable with today's contacts: L 1⁻3⁺ and R 0⁻3⁺.
- Research labels throughout: "stratum", "surface", "posterior", "incumbent", "frozen setting",
  "epochs". The house rules ban some of the page's own words in bare form: "floor" in the
  "8-epoch floor", "Separation (SD)" as a column head and an axis label, and "best deployable cell"
  in the titration record.
- Decision numbers in page text: "decision 210", "decision 217", "decision 133", "decision 144".

**(c) One thing uses different words in different places.**

- One continuous exposure to one setting is called "epochs" on the current map and the home
  schedule, "stretches of unchanged settings" in the strip and the footer, and "stretches fitted"
  in the plan table.
- The speed is called "rate" on some cards and "stimulation speed" on others.
- "Resolved" (the strip) and "proven better" (the headline) mean the same thing.
- "Adaptive mode" and "closed loop" are used for the same thing.
- The readiness column says "falls with current (time removed)", although decision 196 says time is
  modelled nowhere. What is actually removed is the difference between clinic visits. The house
  rules' replacement is "after removing differences between time blocks".

**(d) Figures that carry little data, or carry it by colour alone** (tufte-test, scored from code;
uncertainty medium, because nothing could be drawn in jsdom).

- **The current map's colour scale** is green → yellow → red (`#1A9850 / #FEE08B / #D73027`). About
  1 man in 12 cannot tell those two ends apart (red-green colour blindness). It is also the only
  red-green scale on the platform. The Biomarkers heat maps use the Okabe-Ito blue/orange pair
  (`BIN_LO / BIN_HI`), which that reader can tell apart.
  Rubric: data-ink pass; no 3D pass; direct labelling **fail** (the key is a 110-word paragraph
  above the squares); axes pass; colour **fail**; annotation pass; integrity pass (the middle of the
  scale sits on today's rating).
- **The band bars in the "does power change with current" check** (`BandResponseStrip`) use four
  states: both, direction only, does not respond, not measurable. Three are told apart by fill
  colour alone (green, amber, red), which fails WCAG 1.4.1. The y-axis is headed "separation (SD)".
- **The gain bar** in the decision strip draws "+0.00 ± 1.57" on both sides when the rate in force
  is kept. The gain is zero by construction in that case, so the bar shows a fixed zero with an
  interval. One line of text would say the same.
- **The excluded-settings chart** takes a whole figure per side to show one setting refused
  (10 Hz is below the 55 Hz minimum for closed loop).

**(e) Legibility against decision 258's own rule.**

- Axis text in five chart files is drawn in `#7A7A7A`, **4.29:1 on white**, below the 4.5:1
  minimum: `BandResponseStrip`, `ClosedLoopChecks`, `ExcludedSettingsChart`, `GainBar`, and the
  axis heads in `BandResponseStrip`.
- The legibility test from 258 (`ClosedLoopSim/legibility.test.js`) did not catch this, for two
  reasons. It reads only `color:` style values, not SVG `fill=` attributes. Its list of light greys
  also leaves out `#7A7A7A`.

**(f) Stale wording in live code, found in passing and not changed here.**

- The readiness fold still describes the harmonic rule as "|250 − rate|, half, a quarter and three
  quarters of the rate". Decision 277 replaced that rule with every whole multiple of the rate,
  folded by the 250 Hz sampling rate.
- The per-row harmonic tooltip says "a fall there with current may be the stimulator, not the
  brain". This is close to the phrase the PI retired on 2026-09-06, that a band "measures the
  stimulator".
- Server wording that reaches the page:
  - "8-epoch floor" (`stage1_openloop.py`);
  - "the voltage trace exists for every step" (`titration_plan.py`; the house word is TD);
  - "no band falls with current once the time confound is removed (no significant negative
    era-blocked slope)" (`lfp_evidence.py`).

### 1.3 What works, and should be kept

- The headline is derived from the numbers ("No side has a setting proven better than today's"),
  as rule 1 of the figures skill requires.
- The verdict has three states, and "not determinable" is kept apart from "not resolved" (rule 5).
- Values stay in the open and prose sits in folds (the `Fold` component).
- The current map's legend is open on load and its caveat is in the open (decisions 245 and 235).
- The one-line evidence footer (243).

### 1.4 Proposed layout

Each item can be built in one pass. They are ranked by how much reading they save.

**Folding cannot break a pin (decision 174).** The page's text pins read `textContent`. A folded
paragraph stays in the page, because `Fold` keeps its children mounted. So moving text into a fold
fails no existing pin. Deleting text does fail pins.

```
[Recompute bar]                                                         (unchanged, 259)
STATUS  Keep today's setting on both sides; closed loop cannot start.
  ● No usable sensing pair            (red: the device refuses every pair tried)
  ● Rate below 55 Hz refused          (red, only when it applies)
  ▲ Current map too thin: 4 pairs     (yellow: not enough evidence)
  ▲ Pulse width not assessed          (yellow)
  ▲ Current limits not proposed       (yellow)
  ▲ Pain map moves over time †        (yellow; the 294 dagger, one bullet)
[1 Readiness]   the device's sensing rule sentence; 2 rows (the allowed pairs) open;
                "Show all 22 combinations screened" folded
[2 Decision]    L and R: now → preferred, verdict glyph; one stopping line for both sides
[3 Current map] caveat + legend open (235, 245); per square: heading, three ✓/✗ checks,
                "what the next visit must deliver" (251); unfitted rates as ONE line per
                pulse-width pairing; the square's closing sentence folded
[4 Next visit]  titration: rate, pulse widths, sensing pair, 15 + 15 steps, 74 min,
                [Make Google sheet]; the sheet table and "why this design" folded
[5 Home]        headline line + table (unchanged, or folded: see S7)
[6 Checks]      four check rows with glyphs; each chart folded under its own row
[footer]        evidence base (unchanged)
[Control analyses] folded by default
```

Every bullet carries a glyph as well as a colour: ● for red and ▲ for yellow. Colour is then never
the only signal. The text uses `#1A1A1A` ink; only the glyph is coloured (dataviz, "text wears text
tokens").

| # | Proposal | Words saved (visible on load) | Standing rulings it touches |
|---|---|---|---|
| S1 | Titration card: fold the clinic-sheet table, the per-side "why this design" prose and the per-side harmonic paragraph; keep the ladder summary and the export button open | about 1,700 | 146, 160, 162, 163, 230/236 (the design is kept; only its display folds). Not a reversal. |
| S2 | Current map: one line per pulse-width pairing for the unfitted rates ("Not drawn, too few stretches: 10 Hz (2), 165 Hz (2)"); fold each square's closing sentence, which repeats its three checks | about 550 | 245 (the legend stays open), 235(b) (the caveat stays open), 251 and 255 (the next-visit line and the ruling-5 line stay open), 294 (the dagger stays). Not a reversal. |
| S3 | Readiness: the two allowed-pair rows open, the other 20 folded; the three explanatory paragraphs become one line plus a fold; drop the pointer sentence to the plan card | about 350 | 243(a) (the two readiness cards stay two cards), 217 (its sentence still opens the table), 243(c) (the "still positive with the current taken out" line stays open). Not a reversal. |
| S4 | Status line with red and yellow bullets at the top, computed from fields already on the response (the plan's check conditions, `sensing_rule`, the per-rate checks, the block-of-time state); this lets the three pointer sentences and "Nothing was drawn up" go | about 100 net | 243(a), the page order: this adds a line above the readiness card and moves no card. `StimOptimizer.pageOrder.test.js` still passes if the status line avoids the test's search strings. **The PI decides whether a line above the readiness card is allowed.** |
| S5 | Closed-loop checks card: fold the band-bar chart and the excluded-settings chart under their own check rows; fold the override note and the note about the joint search's untested cells | about 250 | 168 (the "history, not a proposal" line and the side-effect sentence stay open). Not a reversal. |
| S6 | Decision strip: one stopping line when both sides read alike ("Both sides: not assessable, no batch has been run and rated"); the definition of "resolved" and the exposure line into a fold or a tooltip | about 120 | **245(b)** ("When to stop searching" printed per side), **243(b)** ("resolved" defined once at the top of the strip) and **243(d)** (the exposure line printed under the strip). All three would be reversals of placement; **the PI decides.** Merging the two identical stopping lines alone reverses nothing. |
| S7 | Put the home schedule inside the next-visit card as a second fold | about 400 | **The page file records a PI ruling of 2026-09-12 that these stay two cards**, and 243(a) places them together. This is a reversal; **the PI decides.** |
| S8 | Control analyses card closed by default ("Research checks, saved offline (11)") | the analysis shown, 100 to 300 | 264 (the card stays at the foot). Not a reversal. |
| S9 | Accessibility, zero words saved: axis text `#7A7A7A` → `#5E5E5E` in 5 files; a pattern or shape per state on the band bars, not colour alone; the current map's scale changed to the platform's blue ↔ light grey ↔ orange; the 258 legibility test extended to SVG `fill` and `#7A7A7A` | 0 | 258 (enforces it). The colour change also changes the legend wording "as small (as green) as possible … green is better than today and red worse", which is text the PI opened on load in **245**. **The PI approves the new wording.** |
| S10 | Words: one name for a stretch of unchanged settings (drop "epochs"); "minimum" for "floor"; "the gap between the two measured power levels, in units of their own scatter" for "Separation (SD)"; decision numbers out of page text; the stale harmonic fold (1.2 f) matched to 277 | about 50 | 277 and 287 (matches them). Three server strings ("8-epoch floor", "voltage trace", "era-blocked slope") need a server edit and a new saved response. |

**Estimate.** At least 5,100 visible words on load become **about 900**, a cut of about 80%. That
assumes S1 to S5 and S8, with S6 and S7 left as they are. The 900 are: status line and bullets 40,
readiness 90, decision strip 170, current map 330 (legend 110, caveat 70), next visit 120,
checks 110, footer 39.

---

## 2. Biomarkers page

**The decision it serves.** Is there a band, on a sensing pair the device allows with today's
contacts, whose power tracks this patient's pain well enough to carry to the Closed-Loop page as a
candidate? And under which pain score and matching settings? The page explores; it programs
nothing. On RCS08 the answer on the daily defaults is "no band clears the 22-band correction"
(decisions 229 and 246).

### 2.1 The cards in order

| # | Card | Visible | Folded |
|---|---|---|---|
| 0 | Recompute bar | — | — |
| 1 | "Pain Biomarker Exploration": data timeline; report-coverage band; matching controls (four sliders and toggles); binarization preview; the pain-score selector (red box); memory-use messages; "Biomarker computed against", "Binarized by", "Recorded power channels" | about 400 (estimate) | about 300 (estimate; "Expand descriptions") |
| 2 | Heat maps, "How well each band tracks pain": 6 sensing-pair thumbnails, two grids, and the pinned cell's scatter and violin | 184 (plus about 120 once a cell is pinned) | 845 ("How to read this") |
| 3 | Sliding correlation over time (only after a compute) | about 30 plus a figure | — |
| 4 | Device-scale calibration: an intro paragraph, the panel, and an italic caption | 75 + 327 + 25 | 0 |
| 5 | Control analyses | about 40 plus the analysis | — |
| | **Total** | **about 1,300** | **about 1,150** |

### 2.2 Top problems

**(a) The heat-map drawer is 1,029 words once opened.**

About 450 of those words are the seven RCS08 lines about the 2026-09-21 search of 252 settings.
That is research narrative, fixed in the code for one participant, and it sits above the ten bullets
that explain how to read the grid. The PI placed those lines at the head of the drawer, in bold
(decisions 229, 235(c) and 246(d)).

**(b) The first control comes last.**

The pain-score selector drives the timeline, the preview and the grid. It sits below the matching
controls and the preview it drives. It is also called "Pain metric" there and "Pain score" on the
heat maps.

**(c) Developer text sits on a clinical page.**

- "View retained in memory (X of Y MB used) — it returns without recomputing from the deployment page".
- "(computed on N full-resolution samples)".
- The "Recorded power channels" list, which repeats the timeline's own lanes.
- Two names for one action: "sent when you press Compute", then "Click Recompute above".

**(d) The calibration section says one thing three times.**

"Composed, not measured" is in the panel. The italic caption under it says it again. The
intro paragraph then explains why the section exists. No clinician acts on this panel at a visit;
it matters before one.

**(e) One label names two different calculations.**

- The heat-map drawer defines TD as band power from 3 s pieces (decision 298).
- The binarization caption defines TD as "band power estimated over 30 s by Welch's method".

Both may be accurate for their own product: the rating-centred sample index and the heat-map grid
are built differently. But a reader meets one abbreviation with two meanings on one page. Other
words also vary for one thing: "neural sample", "LSB samples" (a slider label), "PRO" (in the
timeline legend "no PRO in window"), "binarize", and "KMeans".

**(f) Legibility.**

- 35 text sizes under 11 px across 5 files:
  - calibration panel 20;
  - binarization preview 5;
  - data timeline 5;
  - older timeline 3;
  - heat maps 2.
- Timeline text in greys well below 4.5:1:
  - `#9AA0A6` "no PRO data" and "no stim data" at 9.5 px: 2.64:1;
  - `#aaa` axis ticks: 2.32:1;
  - `#bbb` "LSB": about 1.9:1.
- Decision 258's rule covers the Closed-Loop and Stim Optimizer pages. Its test does not read the
  Biomarkers folder.

**(g) Pairs the device refuses look the same as pairs it allows.**

The six thumbnails do not say which pairs the device allows with today's contacts. On RCS08 four of
the six (L 0⁻2⁺, L 0⁻3⁺, R 0⁻2⁺, R 1⁻3⁺) cannot drive closed loop today (decision 217). A band found
on one of them cannot be programmed without moving the stimulating contacts.

### 2.3 What works, and should be kept

- Small multiples of the sensing pairs.
- The two grids side by side, one per question.
- A white circle on every column's best cell (171).
- The three-line hover (188).
- The Okabe-Ito diverging scale.
- The split by source printed as text above the scatter (298).
- The "Open this grid in Closed-Loop" link.

### 2.4 Proposed layout

```
[Recompute bar]
STATUS  Allowed pairs today: L 1⁻3⁺, R 0⁻3⁺. No band clears the 22-band correction (NRS, 60 min).
  ● 4 of 6 pairs refused          (red: the device's sensing rule with today's contacts)
  ▲ 79% of ratings from PSD       (yellow; from the grid's own count)
  ▲ Stability not yet tested      (yellow, when the column reads "not tested")
[Pain score ▾]  first, above everything it drives
[1 Timeline]    unchanged geometry (bravo-timeline-layout); legend and annotation greys raised
[2 Matching]    controls + preview; memory lines and the power-channel list removed or folded
[3 Heat maps]   thumbnails marked "allowed today" / "needs other contacts" in words;
                "How to read this" = the ten reading bullets; the 2026-09-21 search lines
                moved (see B1)
[4 Calibration] one line: "TD 345.59 LSB per µV² (measured, 133 blocks) · PSD 72.16 (composed)";
                the panel folded under it
[5 Control analyses] closed by default
```

| # | Proposal | Words saved | Standing rulings it touches |
|---|---|---|---|
| B1 | Take the seven RCS08 search lines out of the "How to read this" drawer and into the control-analyses card, as a saved entry dated 2026-09-21; the drawer keeps the ten reading bullets | about 450 in the drawer | **229, 235(c), 246(d)**: the PI put these lines at the head of the drawer, in bold. This is a reversal; **the PI decides.** A smaller step that reverses less: a fold inside the drawer headed "The 2026-09-21 search on L 1⁻3⁺ (7 lines)". |
| B2 | Calibration: one open status line with the panel folded; drop the intro paragraph and the repeated italic caption | about 400 | 212 and 227 (the panel's content is unchanged, only folded). Not a reversal. |
| B3 | Status line and bullets above the heat maps, computed from the grid (`correlation_by_recording_source`, the stability column, the q values) and the sensing rule; thumbnails labelled in words for allowed or refused pairs | adds about 40; lets readers skip the drawer | 217 (applies it to this page). Decision 108 (Biomarkers does not deal in what stimulation does to a band) is untouched, because the sensing rule concerns contacts, not stimulation effects. Not a reversal. |
| B4 | Pain-score selector first; memory-use lines and "computed on N samples" removed; "Recorded power channels" folded; one verb for the compute action | about 100 | 62 fixes the order of the grids under the timeline, and this moves only the selector. Not a reversal. |
| B5 | One name per thing: "pain score" (not "metric"), "rating" (not "PRO"), "pieces" or "samples" consistently, "split into high and low" (not "binarize"); the TD label carries its length where it differs ("TD, 30 s around the rating") | about 30 | 298 (extends it). The source-word tests (`biomarkersPageSourceWords.test.js`, `heatmapSourceWords.test.js`) need their lists extended, not loosened. |
| B6 | Legibility: text of 11 px or more, greys of 4.5:1 or more, and the 258 test extended to the Biomarkers folder | 0 | 258 (extends it to a third page). **The timeline skill's rule:** raise the fonts only through its column-geometry constants (`F_TICK`, the start fonts, `LBL_GAP` / `LEFT_CAP`), never with a fixed shift, and check that the columns do not overlap with `assert_no_overlap` before building. |
| B7 | Fold the sliding-correlation panel | about 30 plus a figure | none |

**Estimate.** About 1,300 visible words on load become **about 550**. The opened drawer goes from
1,029 words to about 580.

---

## 4. The four added design skills: rules taken and rules declined

**How these skills fit these pages.** All four are written for marketing pages, landing pages and
portfolios. design-taste-frontend says itself (§13) that dashboards and dense product screens are
outside its scope. These two pages are clinical tools inside an existing Material-UI app, so where
a skill conflicts with the PI's rulings or the house rules, the rulings win.

**The design read** (design-taste-frontend §0.B). Reading this as a redesign that keeps the
existing look, for a clinician deciding at a visit, in a trust-first and accessibility-critical
language, built on the existing Material-UI system.

**Settings.** The skill's settings run 1 to 10: how varied the layout is, how much moves, and how
densely it is packed. Set here to layout 2, movement 1, density 6. The skill's own preset for a
public-sector service is 3, 2 and 5; density is one higher because this page is mostly numbers.

### 4.1 Rules found in two or more of the new skills (the old skills gave the same finding)

**Too many nested boxes.** image-to-code §16 and design-taste-frontend §4.4 both warn against
boxes inside boxes. The Biomarkers top card nests three:

- an outer card;
- a card inside it with a 2.5 px black border (`index.js`, the matching block);
- a separate red 2.5 px box around the pain-score selector.

The calibration panel sits inside its own 2 px bordered box. **Taken** into B4: keep one card for
the section, and replace the inner borders with space and one thin rule. The red box stays until
the PI says otherwise, because it marks the one control that drives everything.

**Long lists get a short version and a link to the rest.** design-taste-frontend §4.9 says a long
list should become "top 3-5 + view full list". **Taken.** That rule is the reasoning behind:

- S3: 2 readiness rows open, 20 folded;
- S1: the 34-row sheet table folded;
- S2: one line for the unfitted rates.

**The page must not scroll sideways on a laptop.** image-to-code §15 asks for a first screen that
reads cleanly on a small laptop, and design-taste-frontend §3.E asks for layouts that collapse on
narrow screens. **Taken; this is a new finding.** Both Stim Optimizer tables force sideways
scrolling there:

- the readiness grid has a fixed `minWidth: 1180` (`SensingEvidenceTable.js`);
- the decision strip's fixed columns need about 1,330 px with their gaps (`DecisionStrip.js`).

Folding the readiness table to 2 rows (S3) does not fix its width. So S3 also drops the two count
bars, which duplicate the number printed beside them, and moves "why not" under the row. The
decision strip moves the gain bar and verdict under the setting when the page is narrower than
1,280 px.

### 4.2 design-taste-frontend (v2)

**Taken:**

- **Audit before any change, and keep what works** (§11). §1.3 and §2.3 above are that audit. The
  preserved list:
  - routes and anchor ids (the Closed-Loop jump links point at the anchor `#cl-grid`);
  - card titles the jest pins read;
  - the platform's colours: `#1A1A1A` ink, `#5E5E5E` secondary grey, Okabe-Ito accents.
- **One label for each action** (§4.5). The Biomarkers page says "sent when you press Compute" and
  "Click Recompute above" for the one action. Taken into B4 as one verb: Recompute.
- **Fewer tick-box bars with grey tracks** (§9.F). The readiness count bars (`CountBar`, a
  `#EEEEEE` grey track under a coloured fill) repeat the number printed beside them. Taken into S3:
  drop the bars and keep the number. This also agrees with tufte-viz (less ink that carries no
  data).
- **Loading messages** (§4.5). The Stim Optimizer's loading message is a 55-word paragraph under a
  spinner. Proposed: one line ("Loading the settings history and the readiness screen, about
  10 s"), with the rest folded.
- **No long dashes in new text; one middle dot per line** (§9.F, §9.G). Taken **for the new
  status line and bullets only**. The sample stopping line in S6 was rewritten without a dash.

**Declined:**

- **A page-wide sweep of long dashes and middle dots.** The house rules do not ban them. About a
  hundred pinned strings contain them, and changing them would fail those tests for no gain in
  clinical reading.
- **Fonts** (Geist, Satoshi; "avoid Inter"). The app's Material-UI type is kept, and this is not a
  choice for a design review.
- **Tailwind, Motion, GSAP; scroll and hover motion; "motion claimed, motion shown".** Declined on
  decision 5: figures draw once, and a redraw causes the flash that decision was made to stop.
  Movement is set to 1.
- **Hero rules and a mandatory dark mode.** The app has a dark-mode setting, but nobody asked for
  work on it.
- **Images and a logo wall.** A clinical page has no need for them.
- **Treating the uppercase column headers as "eyebrows".** They are table headers, not section
  labels.
- **Treating the coloured bullets as "decorative status dots".** The red and yellow bullets carry a
  meaning (refused / not evaluated), which the skill itself allows.

### 4.3 design-taste-frontend-v1

**Taken:**

- **No emoji.** The "Recorded power channels" list and the band-above-50-Hz note print ⚠, which
  many systems draw as a colour emoji. Taken into B4: a text word ("above 50 Hz") or the
  platform's own warning glyph.
- **No boxes around data on a dense page** (Rule 4). This supports the nested-box finding in 4.1.

**Declined:**

- **"Always-on" moving parts, lists that animate in one after another, and spring physics.**
  Declined on decision 5, as above, and as a distraction during a visit.
- **"No Inter".** Fonts are out of scope, as above.
- **Serif rules.** Nothing on either page uses a serif.

### 4.4 minimalist-ui

**Taken:**

- **Pale background colours with dark text of the same colour, for tags.** These give the red and
  yellow bullets a form that passes contrast: pale red `#FDEBEC` with text `#9F2F2D` (6.26:1), and
  pale yellow `#FBF3DB` with text `#956400` (4.62:1). The ● and ▲ glyphs stay, so colour is never
  the only signal.
- **Folds without boxes, separated only by a thin rule.** This fits the existing `Fold` component
  (a link-styled toggle, no box).

**Declined:**

- **Its secondary grey `#787774`.** It is 4.48:1 on white, under the 4.5:1 minimum; the house
  `#5E5E5E` (6.48:1) stays.
- **Its 1 px `#EAEAEA` borders as the only edge.** At 1.2:1 they are too faint for card edges in a
  clinic room. This is offered to the PI as an option, not as a proposal.
- **Serif headings, new fonts, scroll-in animation, soft background gradients and background
  images, bento grids, "sections must not feel empty".** All of these are marketing devices.
  Empty space next to a number is fine here.

### 4.5 image-to-code

**The image step was not done.** This session has no image-generation tool, so the skill's
required first step, generating a design image, was not run. No mock-up image accompanies this
review. The layouts in §1.4 and §2.4 are text sketches. If the PI wants rendered mock-ups, a session
with an image tool can draw one image per page from those sketches, as §4 of the skill asks.

**The rules that need no image were applied:**

- **A calm first screen with one message** (§14, §15). The status line is the page's first thing
  to read: at most two lines, with no badges, figures or tags beside it.
- **No boxes inside boxes** (§16). See 4.1.
- **Less small interface clutter** (§17). Taken into B4 and S8: out go the lines about memory use,
  "computed on N full-resolution samples", the cache-status and "served from memory" lines under
  the recompute bar, and "Recorded power channels". The cache status line is the PI's area near
  `RecomputeBar.js`, so **the PI decides whether it moves into a fold**.
- **Every section has a varied, deliberate rhythm, and no section is empty** (§31, §32). Applied
  as: every card opens with one line that answers its question, and its detail sits below.

**Declined:**

- **The image-first workflow, one image per section, the "signature components" and the
  motion-implied choices.** No generation tool is available here, and the pages already exist as
  code. A review that generated a new visual look would be designing a different product.

---

## 5. For the PI: the proposals that reverse or amend a standing ruling

1. **S4.** A status line above the readiness card (243's order is otherwise untouched).
2. **S6.** Moving 243(b)'s "resolved" definition, 243(d)'s exposure line and 245(b)'s per-side
   stopping rule into a fold or a tooltip. Merging the two identical stopping lines alone needs no
   ruling.
3. **S7.** The home schedule inside the next-visit card, against the page's recorded "two cards"
   ruling of 2026-09-12.
4. **S9.** The current map's colour scale changed from red-green, with a new legend sentence to
   replace the one opened in 245.
5. **B1.** The 2026-09-21 search lines moved out of the drawer (229, 235(c), 246(d)), or folded
   inside it.
6. **Section 4.5.** Whether the cache-status line under the recompute bar goes into a fold. It
   sits beside the PI's own `RecomputeBar.js` (rule 7), although the line itself is a separate
   file (`CacheStatusLine.js`).

Every other proposal only folds text, removes a repeat, fixes contrast, or renames a term. None of
those changes a value, a verdict or a card's order.

**Not checked on screen.** The counts come from the 2026-09-15 saved responses, rendered in jsdom.
No page was opened in a browser for this review.
