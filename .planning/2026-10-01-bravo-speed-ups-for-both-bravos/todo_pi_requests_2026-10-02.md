# PI requests after "Right now it's good because all the heat maps ... are prefetched and kept" (2026-10-02)
The PI is asleep (back in a few hours). Work autonomously, front end IN SEQUENCE by me or the ONE UI agent (a4d14010c0a2bc20e); never several front-end agents (consistency). Commit each item separately with a decision row.

## With the UI agent (Biomarkers page), status = running
- [ ] A. Two "Recompute" buttons on the Biomarkers page: redundant, keep one.
- [ ] B. "Checks against chance / against the current" plots (bottom, "What was recorded, and when?" fold, saved research checks) -> Plotly style with hover stats.
- [ ] C. Missing "100" at the right edge of the x axis on that plot/map ("looks janky").
- [ ] D. Client cache: hover, scatter, violins were cached before and the speed-up "uncached" it -> make cells survive (module-level cache keyed by participant+settings+metric); clicking again = 0 requests.
- [ ] E. Recompute note ("these settings have changed") only when MATCHING changed; changing the pain-metric dropdown must NOT mark stale (all metrics prefetched and kept).
- [ ] F. Replace "how well band power tells high pain from low" with "AUC" everywhere on the Biomarkers page.
- [ ] G. Lines above scatter / violin: one line each. Scatter: r, p, n. Violin: AUC = X, p = 0.Y, n = A high, n = B low. Remove the "allowance for 22 bands ... circle/square" phrase. "not allowing for the 22 bands tested" -> "uncorrected".
- [ ] H. Heat maps vs scatter/violin: align horizontally, centre each under its heat map.
- [ ] I. Notes block under the heat maps: terse wording (PI's examples), bigger clean font:
      "104 of 139 matched reports (75%) had no TD in match window; read from PSD (N s row = nearest ceil(N/30) PSDs, else none)" /
      "Match window defined under 'Adjust matching parameters'" / "Heat maps use home pain surveys only; clinic titration sessions toggled off" /
      "Rows ≤30 s: device averaging window (0–30 s on tablet)" / "Rows 45 s–1 min: one averaging window + onset hold (each ≤30 s); device holds level, no averaging" /
      "Circle: ✓ band tracks pain equally at every stimulation setting; ✕ differently; ? unknown".
- [ ] J. "363 of 619 Back VAS reports have a band-power reading within ±10 min; 363 within ±10 min; 395 within ±60 min." -> stack on separate lines, no semicolons. Ask PI if the two ±10 min are a duplicate.

## Server / caching (me)
- [x] Web workers warm each participant before the first click (decision 375). JS2 pool 31 -> 16 (376). CI fixed (377, run result to be read).
- [ ] Verify the heat-map grids for ALL pain metrics are still served from the saved store / prefetched after my 362/372 changes (grid request for each metric: `served_from_store`, time); the PI says caching seemed to be lost.
- [ ] Verify on both servers after the UI work: the grid for every metric, cell click, switching metric = no recompute.

## Stim Optimizer + Closed-Loop wording (me, in sequence AFTER the UI agent finishes; one consistent style)
- [ ] K. Stim Optimizer: plot "what the stimulation current explains" -> scientific title e.g. "Out-of-sample stimulation-current prediction".
- [ ] L. Dot/raster rows hard to follow: very light alternating row shading (Excel-like), NOT the colour of any dot. 
- [ ] M. Section titles in lay language ("Where have currents been tried, and what does the fit predict?", "Is any setting proven better than today's?", etc.): succinct 5-6-word scientific titles, jargon-minimal but accurate.
- [ ] N. Closed-Loop module: remove the tiny text around the top panel and under "Which band?" -> minimalist (Apple-like), keep the language but concise, to the point.
- [ ] O. Read CI result for 94f6672b; fix anything left.

## Round 2 (PI, 2026-10-02 after the build): "Keep a system going to tell you more things to change"
- [x] R2-1. Cell title "L 1⁻3⁺ (Left GPi) · 24.5 Hz · 1m of signal": centre over the scatter and violin plots.
- [x] R2-2. Run-on text "TD values: R −0.24 (−0.56 to +0.07), 35 reports · PSD values: R −0.05 (−0.49 to +0.48), 15 reports": use n=X not "X reports"; keep "R −0.24 (interval)" style; PSD on a NEW LINE below TD.
- [x] R2-3. Bold q-value text for each graph: order = report q 0.XX (FDR, 22 bands); then the report interval; REMOVE "established / across settings / cannot tell" etc. (that belongs on the Closed-Loop page). Same for scatter and violin; make them complementary.
- [x] R2-4. AUC stats line: n for Low is cut off, shows "..." — fix.
(Add every later request here first, then do it, one commit each with a decision row.)

## Round 3 (PI, 2026-10-02, going to sleep; autonomous)
- [x] R3-1. ALL pages: every metric / settings dropdown gets a clear blue border (Closed-Loop pain-score select, Biomarkers metric select, "Adjust matching parameters" selects incl. the high/low split select). One shared style.
- [x] R3-2. Fold "Each lead's contacts and the pair it allows" (now "Contacts and allowed pair"): content far too verbose/redundant -> concise.
- [x] R3-3 (first pass done, decision 383; continue with the dense card bodies: TitrationSessionCard, ClosedLoopChecks, DeploymentRocPanel, ClosedLoopSimulationPanel, LsbPowerPanel, template strings with numbers). Go through ALL module pages with a fine-toothed comb: concise text, noun-phrase titles, body-size captions (the style of decisions 380/381).
- [x] R3-4. Commit this style to memory (feedback memory) AND to the BRAVO visualization skill (~/.claude/skills: bravo-stimoptimizer-figures / bravo-timeline-layout / bravo-session-rules: add a style section; maybe a new skill bravo-ui-style).
