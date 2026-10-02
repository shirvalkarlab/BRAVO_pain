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
