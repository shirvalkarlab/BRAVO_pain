# Decisions and open items — the digest

**Compacted 2026-09-19 at the PI's direction.** Every decision row keeps its number here in one or two
lines. The full rows, with every proof, field count and verbatim quote, are in
`docs/decision_log_full_2026-09-19.md`; a decision number resolves there. PI quotes are paraphrased
here with his permission (2026-09-19). Struck rows stay struck: the mistake is the lesson. New
decisions are appended to Part 3 here AND as a full row in the full log.

---

## Part 1 — Standing rules, by subject (the log's current state)

**Signal, units, calibration**
- Pain-report timestamps are California wall-clock; device times are UTC; convert before matching (2). The chronic detector joins on the California calendar day (142).
- Windows with >10% zero-filled samples are dropped (4); this rule now reaches every routine (57-59).
- 60 Hz notch off by default (13). Only the two 256-point FFT modes convert (14). Conversion from the voltage trace: the transform route at 349.10 since 209 (352.62 from 18; recipe and blocks in `routines/calibration.py`, 208); the composed constant is composed, never "measured" (33, house rules).
- Per-participant conversion model is a frozen stored asset with tiered fallback (11); 8.8 Hz R 0-3+ counts only from 2026-03-01 (16); no impedance term (17).
- **Log power enters no calculation, anywhere** (PI, 2026-09-19; 202). The E1 path (202), the pooled full-spectrum path and the pain correlation (204), the outlier rule and cross-check (205), the aperiodic fit (206, deleted) are done. The frozen log-log model (`psd_lsb_model.py`) was explored (207) and the constant refit instead (208); the Biomarkers page's calibration panel now draws the calibration in effect from the recipe (212), and the v1 asset is read by nothing on a page.
- **Time is modelled nowhere**: drift is a current effect in a patient >3 years into disease; no age penalty, no time input (193-196).
- Never say "spectrum" bare; name the quantity (115, house rules).

**Statistics and verdicts**
- Discrimination intervals are signed, never folded; the lower bound may fall below 0.5 (7, 8, 19). Validation is forward-chaining out-of-sample (12).
- Gates have three states; a gate that goes green on absence of evidence is unsafe (9). A not-assessed condition still blocks but is counted separately in the wording (176).
- "Established" means the point sign; intervals and p stay as caveats; verdict flagged provisional when any interval spans zero (147). D19 passes on point signs (134); D26 capture checks read the pooled slope and WARN (139).
- Family-wise correction on the grid: Benjamini-Hochberg over 22 centres per grid, no autocorrelation adjustment (63); the cell interval is a block bootstrap sized like the shuffle (183).
- E1 (current-to-power) is the pooled titration slope, model B: one intercept per run, ramped side's current, single-side runs, other side held at ANY constant (126, 197, 198). Never pooled across visits at the per-run level (40); curvature tested pooled across visits, cluster-robust, before any switching value on a peaked band, and only on one side of the peak (55, 56, 124).
- The one-band rule: a sensing contact and rate is usable when ONE band falls with current AND rises with pain on the stored Biomarkers grid; no majority rules (199). "Rises with pain" means positive with the block-bootstrap interval wholly above zero (supported, 210); the grid's stricter "established" is shown beside it. On RCS08 every qualifying band sits on a stimulator harmonic and L 1-3+ / L 0-2+ have no positive band — his to weigh.
- Honest current: a milliamp number is recommended only when three per-speed checks pass (not flat, beats today beyond scatter, ≥6 pairs each ≥5 ratings on ≥2 California days spanning ≥1 mA) (158, 184). Rate ≥55 Hz unless a stated reason (138). Left and right are modelled together (157).
- Reliable change: short-gap (≤1 h) pairwise SD per score, same-minute repeats removed, stim-off pairs kept; a warning, never a blocker (104, 111, 112).
- Post-move margin: 0 s by measurement; the 20 s switch stays OFF (144, 178-179, 191, 196).
- Safety ceiling is PI-stated: 4.5 mA both sides (145, 160). Side-effect score 2 is its own rung, cost 2.0 (165); moderate/severe steps never seed "tolerated" (164); the amplitude-severity statistic is recomputed each request (166).
- Thresholds are placed from the record: median averaged reading ± the design rule's minimum; the tablet's capture pair shown beside (180). Timing: averaging 3 s, onset 30 s (max enterable), blanking 30 s, transitions 30 s, startup 15 s (150, 169); ranges have one home, `DecodeCommon/device_ranges.py` (168).
- Ground truth per row: device band power passing the 99.5th-percentile ceiling table > calibrated trace > composed (tagged) > never uncalibrated; both values and fold ratio where both exist (33, 47, 52).

**The store**
- One store, `BRAVO/modules/CacheStore/`; a second implementation is a test failure (30). Key decides whether to write (26); key from database rows alone (24, 25); no pain rating in any recording-derived key or payload (23).
- Every derived write carries `writer=` and flattened `provenance=`; a consumer whose own output is in the chain is refused, and the refusal raises (31, 39). A refused entry is replaced, not skipped (41).
- Recordings cached without expiry; pain reports fetched fresh on every build; the held table serves drill-downs only until the next build (22, 78).
- Parquet+zstd tables, npz arrays, pickle otherwise; CSV/JSON excluded because the therapy timestamp is timezone-aware (29). Redis: 512 MB, allkeys-lru, locks/freshness/small values only, protocol 2 (27, 28).
- One entry per participant per kind by default; `KEEP_NEWEST_BY_KIND` names the kinds that keep more (sweep kinds 12; simulation, design rule 6; two Stim Optimizer responses) — six writes reporting success and one file on disk is the failure this prevents (107, 128, 146, 152).
- A test that touches the store clears or restores ONLY while its own override is in force, and never reaches a launcher that writes to the production root; three times a test has reached that root (96: real jobs started; 116, 129: the root cleared).
- Memos are keyed on the participant's current recording set, not the participant (130).

**Pages**
- Closed-loop figures draw once and restyle by trace index; rebuilding on interaction reintroduces the flash (5, hard). Plotly `doubleClick:false` and guarded purge on the Biomarkers heat maps (91).
- The Biomarkers module does not deal in what stimulation does to a biomarker (108). The heat maps are the headline; nine lengths, 1 s to 60 s (170); the Closed-Loop "Choose a band" card reads the SAME stored grid under the Biomarkers page's settings tag (131).
- A page judges a band on its own side (141). Every card's text is pinned by a fixture render test asserting what a clinician must read and the retired words' absence (174).
- Stim contact notation is the clinic sheet's own, `L C+2-`; sensing pairs keep superscripts (181).

**Process**
- Commit identity: Prasad Shirvalkar, `prasad.shirvalkar@ucsf.edu`, inline `-c` (49). Default branch `PS_closedloop_deployment`; `v3.1.0` is a label (177). No worktrees: the container mounts only the main checkout (102, 177).
- Written record: superseded documents go to `docs/archive/<date>/` by `git mv`, never deleted; no suite count in any document (34). Plan kept with planning-with-files, inject-smart, committed (36).
- Only code changes are open items; clinic notes live separately (open items, 2026-09-10).
- Every check ships with its live proof: field count and difference count, never a tolerance; alternating timings; the first live run of step 8 wrote nothing while every test passed (41).

---

## Part 2 — Open items

**On the PI**
- **30. Titration session** designed so a response peak can be estimated: one rate, 0 to ceiling in 0.5 mA steps, ≥60 s a step, up then down, streaming, baseline and impedance before and after. The Stim Optimizer card "Titration session to run next" recommends it (146, 160). Code side waits on the data (T7, 156).
- The frozen log-log model asset (`psd_lsb_model.py`, `data/psd_lsb_models/RCS08.json`): drawn by no page since 212 and read by no calculation since 2026-06-28; delete it or keep it as a record -- his call.
- Pooling across pulse widths, option A behind a toggle (189's plan). `align_pros` `max_per_rating` cap (118). The four zero-caller chronic-detector routines (187). Apply the harmonic rule to the readiness screen or not (199).
- Item 15 remainder: labelling and navigation niceties on the Closed-Loop page (scroll-link, print stylesheet).

**Rewritten, not open**
- 10. The 110 Hz "heat map" does not exist in the platform; the pre-registration (`PREREG_RCS08_110Hz.json`, read by nothing) is unrun and its own counts do not reproduce; the five left-only days carry one current each (109). Re-measure before reopening.

**Notes for the clinic, not items**: 55 Hz has one left-only visit day on the left electrode, nothing to confirm against; the device never computes its own FFT while current is stepped, so that source is empty for every ladder.

**Resolved by consolidation, do not re-open**: disk reads are 4.8% of the page (the cost was 72 million channel-name normalisations, since fixed); the module README edits are absorbed; matching is 0.2-1.7% of Recompute (the costs are the 1,000-shuffle test and the 90-band scan).

Closed items 1-9, 11-14, 16-29, 31 are one line each in the full log's Part 2 with their resolving decision.

---

## Part 3 — Every decision, one line (number, date where it matters)

Refs are commits or PRs; `→N` means superseded by N.

1. R interface converter built without the frame converter (`33f45a5`).
2. Pain-report timestamp is California local; parsing as UTC smears matches 7-8 h (`a4e4e68`).
3. Concatenation repair kept; re-decode matched 67 of 67.
4. Windows >10% missing samples dropped; zero-fill deflated band power.
5. Figures draw once, restyle by trace index; memoised params — hard constraint (`255e0ef`).
6. Net-benefit cut-point rule removed; it equals the cost rule (PR #3).
7. Discrimination interval not folded (`c50be37`).
8. Per-epoch AUC signed; orientation fixed once on the pooled result (PR #5).
9. Three-state gates; stability gate abstains when its test cannot run (PR #5).
10. Recommendation single-sourced; recommended vs programmed stated; abstain on ramp guidance (`b0597f8`).
11. Frozen per-participant conversion model with tiered fallback; modelled switching value flagged (`771f3c2`).
12. Forward-chaining out-of-sample validation; in-sample hid reversals 0.55→0.24 (`d9d58a4`).
13. Mains notch off by default (`f915257`).
14. Only 256-point modes convert (`f915257`).
15. Direct spectrum-to-device route; round trip adds nothing, 0.8% (`f915257`).
16. 8.8 Hz R 0-3+ from 2026-03-01; earlier data sit in a settling transient (`e9d7a80`).
17. Impedance term rejected, p 0.26 with grouping (`a9c3a01`).
18. Transform route at 352.62 is the primary trace conversion (r 0.9927) (→209 →211: 345.59).
19. Moving-block bootstrap, effective n, de-folded lower bound as gate.
~~20~~. →21. Cut-point converted through the frozen model: a units error (z-scored log fed as linear).
21. Fallback models the device power line off the raw trace at the cut-point's own centre; never converts the switching value (`09798f7`).
~~22~~. Amended by 78. Recordings cached without expiry stands; "reports never cached" now has one exception, the read-only drill-downs; no cheap freshness check exists.
23. No pain rating in tile file or key; report change alters 19,464 values and causes 0 writes.
24. File key from database rows alone, 0.33 s.
25. Key carries event metadata, decode stamping, every constant.
26. Key decides whether to write, not the caller.
27. Redis for locks and small values; big products stay files (0.05 vs 0.14 s).
28. Redis 512 MB, allkeys-lru, both compose files (`b7036bf`).
29. Parquet+zstd tables, npz arrays; CSV/JSON lose the timezone.
30. One store implementation; duplicate deleted.
31. Provenance chain and constructed-cycle proof before any write-back.
32. Band range is all 22 centres 8.5-29.5 Hz; "8-20" was a slip.
33. Ground-truth rule with ceiling check and fold ratio.
34. Record consolidated; 50 documents archived by `git mv`; no suite counts in documents.
35. Pain-report snapshot keyed on content, read by no page, history kept.
36. Plan in planning-with-files, inject-smart, committed, no attestation or gate.
37. `therapy_settings` raw, keyed on source-file rows; `therapy_pain_matched` raw-derived; 0.01 vs 33 s.
38. Sweep writes two tidy tables and serves its response on key match.
39. Store refuses derived kind without writer; one module object under both import spellings; `exploration_ladder`.
40. Amplitude effect per run and band, never pooled across visits at this level.
41. Stim Optimizer reads as consumer, writes five products, refused entry replaced, code digest in key; first live run wrote nothing while tests passed.
42. DecodeCommon is real code on both runners; naive start time mirrors platform.
43. per_pro readers use channel_index behind a switch; 0 differences; 54 vs 65 s.
44. Tile builder reads prepared traces; under 1 s saved of 37.
45. Deployment report accepts the calibrated frame (had raised on every candidate).
46. Redis build lock on the tile key: four cold requests, one build, 41 vs 368 s.
47. Device route ceiling (provisional →52); `ground_truth_verdict` written and read.
48. `cache_status` on every module response; one line under each recompute control.
49. Commit identity: the PI's own name and UCSF address.
~~50~~. →51. Per-recording spectra into the store: "read by no page" was true and beside the point.
51. Assembled matrix into the store; per-recording directory stays, stamp-served (0.35 vs 3.1 s).
52. Device ceiling = 99.5th-percentile table per (electrode, centre) from full history.
53. Track E done: `biomarker_psd_matrix` raw kind; row order follows collection order.
54. Result cache bounded by bytes and resident participants; do-not-edit lifted once.
55. Switching value on a peaked band only on the one-to-one side; pooled cluster-robust curvature test first.
56. Pooled curvature test built and run live; mixed result, one contact 13 points over 4 visits.
57. Entangled routine never applied the zero-fill rule (review).
58. Fixed: missing mask carried through the adapter.
59. Proof: 31 of 386 recordings excluded; 29,704 values moved; a best band moved.
60. Recompute fires one request per press, watched live.
61. Do not fold the entangled routine into the sweep; four axes differ.
62. Heat-map redesign: Option 2, search-first.
63. Family-wise correction: Benjamini-Hochberg, no autocorrelation adjustment.
64. Match direction wired into the sweep; BH built; a missed rule-version bump served a stale response.
65. Track D go-ahead: BH label on the CL grid; forbidden bands stay selectable, greyed.
66. Track A built (SVG grids, hover/click, contact strip); drill-down outlier bug caught.
67. Track D built; device-rules column not built (rules need amplitude etc.); bare import broke the container.
68. Track D leftovers closed; one `MatchDirection` helper.
69. All-None family test; `bh_fdr` matches statsmodels to 1e-10.
70. RCS08 had zero study links; Join Study, grid seen live, grant revoked.
71. `native_lsb_by_channel` added; the two live spectrum builders left unmerged.
72. Merging the builders not recommended: same DSP, different sampling unit, four treatments.
73. Shared matching layer designed; two of four matchers had no independence rule; crossover trial is what the field has and we cannot build.
74. Direction consistency check built (chain-rule signs); contact filter bug caught.
75. Reliable-change floor built; not assessable on RCS08 then.
76. `DecodeCommon/matching.py` ported from the richest matcher; 600-trial equality.
77. Older scatter/violin panel removed; hover 2.9 s → ~1 s via recordings memo.
78. Amends 22: report table held for drill-downs until the next build.
79. Six backend efficiency fixes, each with a 0-difference proof.
80. Frontend dead code removed; purge-on-update and defeated memo bugs fixed.
81. Four Plotly render-manager findings evaluated, none worth 58-file blast radius.
82a. CL module audit: sign-off card read the retired `stim_stable` flag; two checks unwired.
82b. Biomarkers grid on the shared cache; one Recompute control; background prefetch of other scores.
83. `stim_stable` gate reads the three-way verdict; `adaptive_band` checks edges; two dead files deleted.
84. Host suite run in the container: one failure was an environment mismatch; the test wiped the cache (→116).
85. Participant id passed to the store; cross-participant eviction fixed.
86. One pain-score dropdown; Y-axis shows delivered lengths; Medtronic labels; gunicorn needed SIGHUP.
87. Plotly heat maps with side panels; requested vs delivered length carried separately.
88. Gridlines off; shared `heatmapHeight`; modebar off.
89. Sizing regression in 88 corrected.
90. Title and stats rows; plots fill width; thumbnails L then R; pooled warning hidden.
91. Native Plotly scatter and violin; click listener and double-click crash fixed.
92. Availability endpoint cached on recording set and report digest: 8.4 s → 0.6 s.
93. "How to read this" drawer deduped and reordered, 669 → 436 words.
94. Sweep outliers: fixed per-(contact, centre) ceilings applied per 3 s piece with backfill; 0.436% excluded.
95. Dead export button → "Open this grid in Closed-Loop".
96. Stability grid in a detached process after the grid lands; page key vs run key mismatch found only live.
97. Daily stability precompute loop; stopped-early run refused.
98. Stability column proof: 5,148 fields, 0 differing; page 291 s → 10.6 s.
99. "Cannot tell" example re-anchored to 17.5 Hz; the p depends on band width.
100. CL module: cache status on every return; wrong-key handler; zero logger calls fixed.
101. CL `bravo_service.py`; catch-all logs (the 5-day silent outage); note/reason mismatch fixed.
102. Naive timestamps are UTC on every machine; gitignore `_agent_bridge/_*`; agent worktrees were months stale.
103. Consistency check wired; `within_visit_pooled_shape` stored so cold and warm agree.
104. Reliable change wired as a warning; wrong-frame defect caught by reading values (threshold from 0.93 spread is 2.6).
105. `within_visit_band_scores` deleted after a live run showed nothing unique.
106. Device-snapshot share marked per cell; R 0-3+ 79% snapshot-served, length axis 7x flatter.
107. Every score precomputed; store kept one entry per kind → `KEEP_NEWEST_BY_KIND`; fan-out guard.
108. Item 10 closed: Biomarkers does not model stimulation effects.
109. No 110 Hz figure exists; pre-registration unrun; counts do not reproduce.
110. Fake patient and per-rating overlay deleted; neighbouring-line trap noted.
111. Reliable change = 1 h pairwise SD per score, repeats removed; panel added; NRS threshold 1.01.
112. Stim-off pairs stay in the floor.
113. Sign-off card embeds browser-side figure snapshots; grid cache slot collision; stale workers.
114. Timeline circle equals the many-centre reader at its centre, 240 of 240.
115. Many-centre reader deleted; never write "spectrum" bare.
116. Host suite's one failure fixed; it had been clearing the production cache every run.
117. Pooled-PSD builder on the shared matcher; 0 differences; dead branch crashes.
118. `align_pros` already shared; two selectors are not matchers; `max_per_rating` open.
119. Histogram caption names the score and the record total.
120. Timeline's own match window removed.
121. Dash markers removed; snapshot route honours 30 s per snapshot on the length axis.
122. CL grid is a 22-row heat map with radios; hemisphere commit bug fixed.
123. CL prose folded; ledger to counts strip; "Sign agreement", "Full parameter recommendation", three column names.
124. E1 stays a straight-line slope; literature and RCS08 support no peak yet; titration protocol → item 30.
125. Three-source panel pooled across visits from stored per-run points; prefetched.
126. E1 is the pooled titration slope; historical estimate kept beside it.
127. No row; numbering gap in the original log.
128. CL-DBS simulations card, M0-M3, 3 s pieces on the device clock; per-candidate entries.
129. A test emptied the production store; clear only under the override.
130. Memos keyed on recording set identity.
131. CL grid reads the Biomarkers page's own stored grid by settings tag; built on demand.
132. Device rules read rate and pulse width from programmed settings when the candidate lacks them.
133. D16 impedance from a fixed-current test; automatic low-current reads are spurious fails.
134. D19 passes on point signs.
135. D30 answered from the device's active group.
136. Device facts rebuilt daily from ingested reports; two scanner misreads fixed.
137. 123 dead tests deleted; two-stage path wired behind a flag.
138. Stage 1 recommends ≥55 Hz unless a stated reason.
139. D26 checks read the pooled slope and warn.
140. Stim Optimizer first build 51 → 10 s; BLAS to one thread; no GPU in the container.
141. CL page judges a band on its own side; 20 s margin first wired.
142. Chronic detector on the California day; 26.2% of ratings moved; memo and key fixes.
143. Stim Optimizer review: own-side pulse width; one module object per package; stream anchors off.
144. 20 s margin behind a switch, OFF: two removed points flipped a verdict.
145. Ceiling PI-stated; 3,696 lines of dead modules deleted; unread Biomarkers blocks removed.
146. Titration session card designed from the record (amended by 160); two Stim Optimizer responses kept.
147. "Established" = point sign; provisional flag.
148. Timing parameter ranges found (FDA table 2); record-derived recommendations.
149. Ranges wired into both modules; "programmed today" shown.
150. Six-method contest; Kalman design rule adopted; averaging 3 s for response time.
151. Simulation card replays programmed and recommended timing; undone switches counted.
152. T3 design rule built; its kind added to `KEEP_NEWEST_BY_KIND`.
153. T4 occupancy check; a sign error caught against the contest's report.
154. T6 startup dip, two methods shown, not reconciled.
155. T5 block bootstrap, vectorised by precompute; 36-90 s reproduced bit for bit.
156. T7 gain wiring confirmed on constructed data; waits on the titration session.
157. Left and right modelled together; arm strip removed; injected "coordinator" messages ignored.
158. Honest-current rule; home titration schedule; two claims in 157 corrected.
159. Current map cards on the page; surfaces on the response.
160. Ceiling 4.5 mA; ladder redesign: ramp+test rows, 1.0 mA down legs, joint corners, sheet rows.
161. Clinic sheets ingested as their own stream; Excel turned "8/10" into a date.
162. Titration card and clinic section drawn.
163. "Make Google sheet" button; openpyxl `value=None` is a no-op.
164. Moderate/severe steps excluded from tolerated anchors.
165. Score 2 is its own rung, cost 2.0.
166. Amplitude-severity statistic recomputed per request; typed number retired.
167. Clinician review: 19 findings; root cause "computed, stored, not on the page".
168. Three Criticals fixed; device ranges one home in DecodeCommon.
169. Ranges reconciled with the tablet; onset max 30 s; 5-minute rows beyond the device.
170. Onset grids capped at 30 s; sweep ends at 60 s, nine lengths.
171. Heat-map text and layout to the PI's wording.
172. Retired-table notes reworded for the heat map.
173. Corrected-statistic line beside the violin; no repeated n.
174. Referent audit executed: 10 of 12 fixed; render test per card.
175. "What would change this" item reworded; second in-clinic plan table removed; sign-off duplicate.
176. Four leftovers: capital, stale comments, dead builders, gate wording (both copies).
177. Default branch `PS_closedloop_deployment`.
178. 20 s margin ON.
179. 178 reversed the same night; OFF until a titration session decides it.
180. Thresholds placed from the record; capture pair beside them.
181. Google Sheets via the PI's OAuth token; `L C+2-` notation; centred cells.
182. Clinic sheets synced from Drive daily.
183. Block bootstrap for cell intervals.
184. Coverage counts occasions: ≥2 California days per pair.
185. Stability answers on the Biomarkers grid; one home for the words.
186. Clinic-sheet ratings in heat maps behind a switch, default off.
187. T1 was a misinterpretation; the unread powerdomain block deleted.
188. Hover three lines; Pearson and Mann-Whitney p on the backend via scipy; browser stats deleted.
189. Descriptions folded; pairing line; pulse-width pooling plan (A behind toggle) not built.
190. Duration weighting measured: no recommendation changes.
191. Margin sweep: 0 of 30 settled values change; margin is a min-hold filter.
192. Current map absolute ratings, colour centred on today's setting.
193. Age penalty inert and unsupported; log drift ≠ raw drift.
194. Time as fitted input (→196).
195. Clinic stream without time input (→196).
196. Time modelled nowhere; S7 settled at 0 s; run finder needed the other-side rule.
197. Runs count whatever the other side is held at; 11 → 17 runs.
198. Pooled slope model B kept.
199. One-band rule; usable cells 6 → 4, all on harmonics.
200. Review leftovers C3, C4, C6, C7, T2, T3 built.
201. C6 off-label line removed.
202. No log power on the E1 path; remaining sites listed for the PI.
203. Context compaction: this digest, the full log in `docs/`, shorter CLAUDE.md, house rules and store architecture; handoffs, worker reports, completed plans and generic rules deleted.
204. No log power on the pooled full-spectrum path (the matrix stores raw power under `X`; the stability test, mixed model, per-era ROC and band feature read it raw) or in the pain correlation (`transform="raw"`); 10 of 132 stability verdicts moved, the chosen band unchanged; the correlation's MAD rule on raw power drops more samples (106 -> 93) -- item 3.
205. The outlier rule and the heat map's logistic cross-check on raw power, 5 MAD unchanged; the log-scale option refused; one-sided trimming of a multiplicative feature accepted with the rule; chronic detector sample set and summary move (AUC 0.554 -> 0.555).
206. The aperiodic (1/f) fit deleted with its `fooof` transform; reached by no page; the device cannot threshold a peak's prominence.
207. Calibration exploration (no code): the frozen model's curvature is between-band gain pooled into one slope; within-band slopes about 1; raw fits agree with the median ratio; the frozen-model rewrite was scratched in favour of refitting the constant on the new data.
208. The June anchor reproduced with the lab's benchmark (n 131, r 0.9927) and extended to 2026-09-03 (n 133 gated, k 345.59, r 0.992); block gate (3 s, 6 readings) and 5-MAD ratio rule adopted; bridge ratio 4.789 refit as raw median 4.755, kept; recipe and de-identified blocks and pairs in the repository.
~~209~~. →211. The transform constant as the midpoint of 352.62 and 345.59, 349.10; composed bridge 72.90; page labels read the served constant; every calibrated number scales by 0.9900, verdicts unchanged; heat-map correlations move at most 0.044 through the ceiling exclusion.
210. The one-band rule's pain leg loosened to "supported" (positive, block-bootstrap interval wholly above zero); "established" reported beside it; usable cells 0 -> 11 on today's data, L 0-3+ Left 125 Hz selected.
211. The transform constant is 345.59 everywhere: the adopted recipe's one median over every block, not a midpoint of eras (209 superseded); composed bridge 72.16; every calibrated number scales by 0.9899, verdicts and the 11 usable cells unchanged.
212. The Biomarkers page's bottom-right calibration panel draws the calibration in effect (the transform constant over every paired block with the recipe's gate and rule, the June reference from the same table, the bridge ratio per centre and contact pair, both constants read from the server) instead of the frozen June log-log model; raw axes; the committed band's own refit draws the constant beside its fit; no source file carries a constant.

---

## Part 4 — Lineage, in brief

PRs #3-#8 built the engine, figures, audit, validation; #9 (`39dfb2f`, 2026-06-29) merged 61 commits into `v3.1.0`; #10-#12 followed; since 2026-09-15 work lands on the default branch directly. Landmarks: `90eb109` calibrated closed-loop band power (verdict 2 → 6 of 50, sign of current-to-power reversed); `958cc89` matcher vectorised 21.4x, 0 differences over 1,080 configurations; `688a185` withdrew an invented constant; `6c3c9f2` corrected brain-side labels by amendment. Two pushed messages (`b700717`, `7ab2d1b`) wrongly say the container path is not a live mount. Full lineage: the full log, Part 3.
