# Decisions and open items — the digest

**Compacted 2026-09-19 at the PI's direction.** Every decision row keeps its number here in one or two
lines. The full rows, with every proof, field count and verbatim quote, are in
`docs/decision_log_full_2026-09-19.md`; a decision number resolves there. PI quotes are paraphrased
here with his permission (2026-09-19). Struck rows stay struck: the mistake is the lesson. New
decisions are appended to Part 3 here AND as a full row in the full log.

---

## Part 1 — Standing rules, by subject (the log's current state)

**Signal, units, calibration**
- Pain-report timestamps are California wall-clock; device times are UTC; convert before matching (2). The chronic detector joins on the California calendar day (142). The session matcher caps nothing per report; reports claimed by more than one session are counted and warned about (221).
- Windows with >10% zero-filled samples are dropped (4); this rule now reaches every routine (57-59).
- 60 Hz notch off by default (13). Only the two 256-point FFT modes convert (14). Conversion from the voltage trace: the transform route at 349.10 since 209 (352.62 from 18; recipe and blocks in `routines/calibration.py`, 208); the composed constant is composed, never "measured" (33, house rules).
- Per-participant conversion model is a frozen stored asset with tiered fallback (11); 8.8 Hz R 0-3+ counts only from 2026-03-01 (16); no impedance term (17).
- **Log power enters no calculation, anywhere** (PI, 2026-09-19; 202). The E1 path (202), the pooled full-spectrum path and the pain correlation (204), the outlier rule and cross-check (205), the aperiodic fit (206, deleted) are done. The frozen log-log model was explored (207), the constant refit instead (208), the Biomarkers page's calibration panel draws the calibration in effect from the recipe (212), and the model and its asset were deleted (218; `DEVICE_percept_rc.md` §10 keeps its numbers).
- **Time is modelled nowhere**: drift is a current effect in a patient >3 years into disease; no age penalty, no time input (193-196).
- Never say "spectrum" bare; name the quantity (115, house rules).

**Statistics and verdicts**
- Discrimination intervals are signed, never folded; the lower bound may fall below 0.5 (7, 8, 19). Validation is forward-chaining out-of-sample (12).
- Gates have three states; a gate that goes green on absence of evidence is unsafe (9). A not-assessed condition still blocks but is counted separately in the wording (176).
- "Established" means the point sign; intervals and p stay as caveats; verdict flagged provisional when any interval spans zero (147). D19 passes on point signs (134); D26 capture checks read the pooled slope and WARN (139).
- Family-wise correction on the grid: Benjamini-Hochberg over 22 centres per grid, no autocorrelation adjustment (63); the cell interval is a block bootstrap sized like the shuffle (183).
- E1 (current-to-power) is the pooled titration slope, model B: one intercept per run, ramped side's current, single-side runs, other side held at ANY constant (126, 197, 198); both legs of a ladder count, and a streaming restart under 20 s with the current held does not split a run (213). Never pooled across visits at the per-run level (40); curvature tested pooled across visits, cluster-robust, before any switching value on a peaked band, and only on one side of the peak (55, 56, 124).
- The one-band rule: a sensing contact and rate is usable when ONE band falls with current AND rises with pain on the stored Biomarkers grid; no majority rules (199). A usable cell whose qualifying bands all sit on a stimulator harmonic carries a warning, never a refusal (220). The sensing pair must be the two contacts immediately flanking the lead's stimulating contact -- stimulate on 1 and sense 0-2, on 2 and sense 1-3, on 1 and 2 and sense 0-3; on 0 or 3 nothing (217; the device's three configurations per lead). "Rises with pain" means positive with the block-bootstrap interval wholly above zero (supported, 210); the grid's stricter "established" is shown beside it. On RCS08 every qualifying band sits on a stimulator harmonic and L 1-3+ / L 0-2+ have no positive band — his to weigh.
- Honest current: a milliamp number is recommended only when three per-speed checks pass (not flat, beats today beyond scatter, ≥6 pairs each ≥5 ratings on ≥2 California days spanning ≥1 mA) (158, 184). Rate ≥55 Hz unless a stated reason (138). Left and right are modelled together (157). Pulse-width pairings are fitted separately by default; a pooled fit over every pairing, the pulse widths as inputs, sits behind the current-map card's toggle (222).
- ~~Reliable change: short-gap (≤1 h) pairwise SD per score, same-minute repeats removed, stim-off pairs kept; a warning, never a blocker (104, 111, 112).~~ Deleted (231): too few pairs, too much scatter to mean anything (RCS08 Left Leg VAS: 12 pairs, pooled SD 11.1, threshold 30.8 of 100).
- Post-move margin: 0 s by measurement; the 20 s switch stays OFF -- by the PI's ruling after the titration session was run: use as much data as we can (144, 178-179, 191, 196, 217).
- Safety ceiling is PI-stated: 4.5 mA both sides (145, 160). Side-effect score 2 is its own rung, cost 2.0 (165); moderate/severe steps never seed "tolerated" (164); the amplitude-severity statistic is recomputed each request (166).
- Thresholds are placed from the record: median averaged reading ± the design rule's minimum; the tablet's capture pair shown beside (180). Timing: averaging 3 s, onset 30 s (max enterable), blanking 30 s, transitions 30 s, startup 15 s (150, 169); ranges have one home, `DecodeCommon/device_ranges.py` (168).
- Ground truth per row: device band power passing the 99.5th-percentile ceiling table > calibrated trace > composed (tagged) > never uncalibrated; both values and fold ratio where both exist (33, 47, 52).

**The store**
- One store, `BRAVO/modules/CacheStore/`; a second implementation is a test failure (30). Key decides whether to write (26); key from database rows alone (24, 25); no pain rating in any recording-derived key or payload (23).
- Every derived write carries `writer=` and flattened `provenance=`; a consumer whose own output is in the chain is refused, and the refusal raises (31, 39). A refused entry is replaced, not skipped (41). The Closed-Loop `inputs` entry is keyed on the recording set AND the two calibration constants AND a rule version (215); it served a three-day-stale frame under the old constant until then.
- Recordings cached without expiry; pain reports fetched fresh on every build; the held table serves drill-downs only until the next build (22, 78). The Biomarkers page's top timeline is an acquisition timeline: keyed on the recording set and the constants, stored as a raw kind, nothing in it from a pain report; the rating-centred sample index has its own endpoint (216).
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
- Written record: superseded documents go to `docs/archive/<date>/` by `git mv`, never deleted; no suite count in any document (34). Plan kept with planning-with-files, inject-smart, committed (36); autonomous mode with attestation allowed per plan, gated mode never (223).
- Only code changes are open items; clinic notes live separately (open items, 2026-09-10).
- Every check ships with its live proof: field count and difference count, never a tolerance; alternating timings; the first live run of step 8 wrote nothing while every test passed (41).

---

## Part 2 — Open items

**On the PI**
- **30. Titration session**: RUN on 2026-09-16, both sides (the PI, 2026-09-20; 213): the record holds 8 settled currents on the left ladder and 10 on the right. The 20 s margin switch stays OFF by his ruling (217). Closed.
- Ruled 2026-09-21 and built (218-222): the frozen model deleted; the zero-caller chronic-detector routines deleted; the harmonic rule a warning, never blocking; the matcher's report cap stays out and the sharing warns; pooling across pulse widths behind the current-map card's toggle, default separate. The clinic implication of 217 (L 0-3+ needs L C+1-2-) stands; the full-spectrum matrix keeps rebuilding on a new report. The audit code leftovers were ruled on and built the same day (223-227): nothing of that list remains open.
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
~~75~~. →231. Reliable-change floor built; not assessable on RCS08 then.
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
~~104~~. →231. Reliable change wired as a warning; wrong-frame defect caught by reading values (threshold from 0.93 spread is 2.6).
105. `within_visit_band_scores` deleted after a live run showed nothing unique.
106. Device-snapshot share marked per cell; R 0-3+ 79% snapshot-served, length axis 7x flatter.
107. Every score precomputed; store kept one entry per kind → `KEEP_NEWEST_BY_KIND`; fan-out guard.
108. Item 10 closed: Biomarkers does not model stimulation effects.
109. No 110 Hz figure exists; pre-registration unrun; counts do not reproduce.
110. Fake patient and per-rating overlay deleted; neighbouring-line trap noted.
~~111~~. →231. Reliable change = 1 h pairwise SD per score, repeats removed; panel added; NRS threshold 1.01.
~~112~~. →231. Stim-off pairs stay in the floor.
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
213. The 2026-09-16 titration session was run in full but under-counted: the run finder never joined two streaming recordings (the tablet restarted twice, once for 12 s with the current held), and only a RISE into a setting counted, so the first setting of every recording and every down-leg step were discarded. Now recordings separated by less than the 20 s move window with the current unchanged are one record; each setting carries the device's own current before its move; a setting reached by a rise OR a fall is measured and tagged by leg (the PI: pool both legs). Left 9/16 ladder 1+4 -> 8 settled currents in one run; 4 of 15 runs hold 8 or more; run points 4,845 -> 8,353 rows (1,588 falling); E1 on L 1-3+ n 18 -> 33, p 0.21 -> 0.72; verdicts unchanged.
214. The Closed-Loop "LSB & power" card's µV²/LSB cross-check read the stored voltage trace as ADC counts (×0.146) and took a segment-averaged band power; now unscaled microvolts, the transform band power, compared with the constant in effect instead of a 0.01 rule of thumb. On RCS08 the independent pairing (218 streaming sessions against the device's own readings at ~0 mA) gives 0.00283 µV² per LSB = 1/352.7, 0.98× the constant in effect: confidence low -> high; nothing else on the response moves.
215. The Closed-Loop `inputs` store entry (the evidence frame with its calibrated LSB columns) is keyed on the recording set, the two calibration constants in effect and a rule version, not the recording set alone; live, the entry on disk had been written on 2026-09-17 under the old constant and was still being served -- the rebuild has 13,617 more tiles and 90 report fields move (prescriptions, thresholds, E1), verdict unchanged.
216. The Biomarkers page's top timeline is an acquisition timeline: the endpoint reads no pain report, the per-report matched circles are gone, the payload (records, stim, calibrated overview, events, samples) is keyed on the recording set, the constants and a rule version and stored as the raw kind `acquisition_timeline`; the rating-centred sample index the Binarization card reads has its own endpoint `/queryPsdScanIndex`. Measured first: the matching step was 0.6 s of a 5.0 s build; the cost was the per-worker memo keyed on the report digest. Served: memo hit 1.2 s -> 0.015 s, from the store 0.02-0.05 s; a filed report causes zero builds and zero writes; 430,108 retained fields, 1 differing (the span no longer runs to the newest report; the page widens the axis from the live pain series).
217. The readiness screen applies the device's sensing rule: the sensing pair must be the two contacts immediately flanking the lead's stimulating contact (three configurations per lead -- BrainSense tip card pp. 7-8, white paper p. 8, A610 p. 36), read per lead from the cathode in force; a cell on any other pair is refused with the allowed pair named. On RCS08 (left C+2-, right C+1-2-) the allowed pairs are L 1-3+ and R 0-3+, neither of which has a band rising with pain: usable cells 11 -> 0 of 50. The 20 s margin switch stays OFF by the PI's ruling (use as much data as we can).
218. The frozen June log-log conversion model deleted (module, asset, tests); DEVICE §10 keeps its numbers; the calibration endpoint unchanged (3,007 fields).
219. The four chronic-detector routines with no caller deleted (336 lines, 9 tests); `roc_analysis` and `lfp_distribution` stay with their pipeline caller.
220. The harmonic rule on the readiness screen is a warning, never a refusal: a usable cell resting on harmonic bands alone is flagged and its sentence printed; `deployable` never written; on RCS08 today 0 usable so none fires.
221. The session matcher keeps no cap per report; the sharing is counted and warned about (RCS08, 60 min: 41 of 76 matched reports shared, at most 24 sessions); 0 fields differing.
222. Pooling across pulse widths (189's option A) behind the current-map card's toggle, default separate: one surface per speed over every pairing, pulse widths as inputs, read at the pairing in force; on RCS08 coverage passes at 55 and 110 Hz where the separate fits could not, every pooled surface reads flat, nothing resolves; separate rows untouched.
223. Amends 36: `.mode` may carry `inject-smart autonomous`; the plan is attested at init and re-attested after every edit; `gate` stays off.
224. The Binarization card laid out as option C (the PI, 2026-09-21): a top band with the coverage sentence, the match window, the split rule and the match direction, and a timing histogram (each neural sample's signed minutes to its nearest report, one translucent series per source overlaid, the window's 25% tails and any side the direction excludes in grey); the left column restyled, the preview untouched. Backend review: the Compute response's unread per-report band-power value (2.5 MB, 0.35 s) and its 60-minute tolerance helper deleted, 0 of 249,322 fields differing. Report-first stays two-sided; only "Before the report" is one-sided.
225. The per-report band-power reader deleted, both copies and their tests (the PI, 2026-09-21): `availability.per_pro_lsb` with its reference scan and `DecodeCommon.per_pro_lsb_indexed`, 26 tests; nothing on any page read its answer since decision 216; the tier names and the tile-cache matcher stay. Host 1434 -> 1419, container 699 -> 674, 0 failing.
226. The Compute response no longer carries a second copy of the timeline payload (the PI, 2026-09-21): it was a fallback for the timeline and sample-index endpoints (2.7 s and about 7 MB per Compute on RCS08); the builder has no report-dependent path left; the page draws the timeline from its own endpoint only, so a failed timeline request shows as one. Compute 36,570 fields in common, 0 differing, 212,752 removed; timeline 430,108 fields, 0 differing.
227. The audit leftovers ruled on (the PI, 2026-09-21). B1: the Biomarkers page's left refit panel (Welch-based, log-space check, a percentage of the constant in effect from a different recipe) deleted with its endpoint and routine as redundant; the calibration-in-effect panel takes the row. C1: the recipe reports a 95% bootstrap interval on the median ratio, 1 MAD of the raw ratio and a raw proportionality check (RCS08: 345.59, 339.4-350.7, 1 MAD 18.6 = 5.4%, Spearman -0.02 p 0.78 over 133 blocks), drawn and printed on the panel. A2: the band either side of a MODELLED threshold on the Closed-Loop card is that scatter per participant, never the deleted model's log-space 1.26 (L 1-3+ 22.5 Hz: 851-1351 -> 1014-1130); no blocks, no band. D: 49 stale-constant comment lines reworded to name the constant in effect; ten dated historical lines stay. E: the two uncalled statistics helpers deleted (101 lines). Host 1419 / 2 / 0, container 673 / 0.
228. The heat-map cell's scatter and violin come from the same ratings the grid correlated (the PI, 2026-09-21: r printed negative, line drawn rising): the drill-down never read the clinic-sheet switch, so with sheets on it matched the REDCap ratings alone (L 1-3+ 22.5 Hz 45 s: 97 points, r +0.104, against the grid's 172 and -0.033); it now merges the sheet ratings as the grid does and tags each point, drawn hollow; live test RED (97 vs 172) -> GREEN (r equal to 2e-15, slope sign = sign of r). Also: the calibration panel's jest suite had failed to parse since bd46556d, which claimed jest passed; repaired.
229. Exploratory search on L 1-3+ (the PI, 2026-09-21: is any band positive with pain under any window or knob?): 252 settings (windows 2-120 min, three directions, caps 1/3/10, reuse, clinic sheets) through the page's grid routine, store reads on and writes off; 0 positive rows with q < 0.05 out of 5,544; sheets off, the one "established" cell is 24.5 Hz at 60 s, 120-min window, pre-report (r 0.33, 0.17-0.48, n 59, q 0.23), and 21.5-25.5 Hz "supported" in 1-8 settings per window against 3-9 negative by chance; sheets on, 11-22 of 22 bands per setting fall with pain (1,545 negative rows with q < 0.05). Read as a lead for the next titration session, not a band to program. The five headline lines head the heat maps' "How to read this" drawer in bold, for RCS08 only. A first run with the store off had no clinic sheets (they are read from the store) and was discarded.
230. The exploratory ladder for L C+1-2- on the Stim Optimizer's titration card (the PI, 2026-09-21: a ladder "very helpful for deciding how the biomarker moves and its acute effect on pain"): when the readiness screen's best sensing pair on a side needs other stimulating contacts than the ones in force (L 0-3+ needs C+1-2-, the flanking rule inverted), the plan carries `proposed[side]`: the configuration, its rate from that cell (125 Hz; in force 55, whose half-rate harmonic sits on the watched 24.5-27.5 Hz bands), the pain-positive bands to watch and their harmonic clearance, the record for that configuration (L C+1-2-: 14 epochs 2025-07-18 to 2025-11-12 at 0.0 mA only; one day on part of a ring at 1 mA, counted apart), a first-exposure stop rule (side-effect score 2, decision 165), part A the 15-step up/down ladder for the biomarker's slope with the other side held, part B three 5-minute holds off / on / off at the top current tolerated with a rating every minute and the patient blind to the current; 33 clinic-sheet rows appended after the joint corners, in the Google-sheet export. Live RCS08: 8,821 fields in common, 8 differing (bookkeeping), 1,630 added, 2 removed (bookkeeping); host 1424 / 2 / 0, container 673 / 0, jest 31 across the seven Stim Optimizer suites. The card's new section waits on a live watch (the pane logged out at the session restart).
231. The reliable-change index deleted (the PI, 2026-09-22: too much variance; delete the decision that kept it): the module (`ClosedLoopDeployment/reliable_change.py`), its test, the adapter's block on the Closed-Loop response (`reliable_change`), the page's card (`ReliableChangePanel.js`, "How big a change in this patient's own rating means anything?") and the jest pins; decisions 75, 104, 111, 112 superseded. On RCS08 the index rested on 12 short-gap pairs of Left Leg VAS (pooled SD 11.1 on a 0-100 scale, a threshold of 30.8) and gated nothing. Also: a Closed-Loop smoke test still imported the panel deleted in 227 and had failed to run since; repaired. Panel A's proposal to print the index beside grid cells is dropped by this ruling.
232. Research batch and panels (the PI, 2026-09-22, overnight): four reports (the Biomarkers pipeline against the literature; alternative detection and symptom-tracking methods; the Stim Optimizer's Bayesian algorithm end to end; the Closed-Loop page's integration) each debated by a three-reviewer panel on a shared board to consensus (A round 4, B 3, C 4, D 3), every adopted action with an elicited probability and range and, where the record allowed, a live measurement with its interval; `artifacts/research_2026-09-22_*` and the synthesis. The finding that runs through all four: on the left lead the bands that rise with pain rest on the current in force (every "supported" 21.5-26.5 Hz cell on L 1-3+ and the ladder's 24.5-27.5 Hz watch bands on L 0-3+ lose their wholly-positive interval once the left current is partialled out; the grid and E2 carry no current term). Also measured: the Stim Optimizer's surrogate fails its own pre-registered calibration check on the live strata (55 Hz quarter-out coverage 0.37) and nothing runs it; the clinic-stream fit hard-codes the left leg; a two-state model of the ratings is not identifiable; the right-lead closed-loop candidate reads the right lead's own record. No code changed by the panels; eight open questions for the PI are collected in the synthesis §4.
233. The eight questions answered (the PI, 2026-09-22, on the panels' synthesis §4). (1) The ladder's pain reading is the current-stepped ramp WITH the current term, and he wants the fixed-current holds' reading beside it to decide finally: both are built and reported, the ramp's is the one to read. (2) "Supported" does NOT require a band to stay positive once the current in force is partialled out; the adjusted value is reported descriptively beside the plain one and never re-selects a band or moves a verdict (decision 210 stands). (3) The exploratory ladder runs at 55 Hz, the rate in force, not the 125 Hz of the cell where the bands were found: decision 230's rate rationale is overridden. Consequence, stated and kept as a warning, never a refusal (decision 220): at 55 Hz the half-rate harmonic is 27.5 Hz and a band is 5 Hz wide, so the harmonic falls INSIDE 25.5, 26.5 and 27.5 Hz and only 24.5 Hz stays clear (corrected on measurement in 236; this line first said three of them were clear, comparing centres to the harmonic and forgetting the band's own width). (4) The back site gets its parallel fit wired once the clinic-stream site defect is fixed (C-9 then C-1 becomes wire, not retire). (5) The next titration session runs 55 Hz at the pulse-width pairing in force (100/150 us), and its data are merged with the 60/160 us record for the analysis (pooling for that stratum, decision 222's toggle). (6) The surrogate's calibration check is reported as a WARNING, never blocking. (7) The current-adjusted grid sits behind a switch, the plain grid the default. (8) The chosen closed-loop band is recorded on the server and updated whenever a new band is chosen.
234. The heat map's correlation with the stimulation current taken out of it, behind a switch (the PI, 2026-09-22, rulings 2 and 7; panel A's item 1, the first step of the cross-cutting build order). `AdjustForStimCurrent` off by default: with it on, every cell of a pair's grid also carries the correlation computed with the current in force on that pair's own side taken out of both the band power and the pain score (`adjusted_correlation_grid`, `pearson_r_adjusted` and the change on each selected row, `covariate_adjustment` saying whether it could be done and why not). The plain value still selects the band, carries the interval and sets the verdict -- descriptive, never a gate. The current per pain report is read from the dated settings the device's own files carry, the raw store kind `therapy_settings`, as consumer "biomarkers" (`routines/stim_current.py`); Biomarkers does not import StimOptimizer and no second parser exists. The switch is in the store KEY, not in the cross-page settings tag (decision 131 untouched), so a grid built with the switch off is the same product it always was and is still served, while a switch-on request cannot be answered from one. Live RCS08 (NRS, the daily defaults): 33,919 fields in common, 0 correlation values moved (1,904 differing = 293 bookkeeping, 1,851 the stability column, which is a background product keyed on the grid's own key and so unbuilt for the new key, 24 the covariate block, 1 a wall-clock sentence), 2,952 added, 1 removed (a timestamp). What it says: on L 1-3+ the 22.5-27.5 Hz bands read -0.13 to -0.18 against NRS plainly and -0.23 to -0.28 with the current out; on L 0-3+, the ladder's own pair, +0.08 to +0.20 plainly and +0.01 to +0.12 with it out, the positive readings shrinking by 0.06 to 0.11. Six tests first, watched RED. Host 1406 / 2 / 0, container 679 / 0 (was 673).
235. The three interim caveats, on the pages read today (step 2 of the panels' cross-cutting build order; panel D item 9, panel B item 8, panel A item 5). (a) Closed-Loop evidence triangle: one sentence under the band-power-to-pain edge naming the current in force as an unadjusted confound, for a LEFT candidate whose centre is 21.5-27.5 Hz only (`CURRENT_CONFOUND_NOTE`, `currentConfoundApplies`), and the module's own "PROVISIONAL: ... rests on the point signs alone" half of the coherence note pulled out of its fold into the open, the method half left in it. (b) Stim Optimizer current-map card: the pooled "higher current, lower pain" association is stated as not holding out of sample (area under the curve 0.41 left alone, 0.49 both sides, against 0.57 for shuffled data, 611 ratings, folds separated in time), in the open, never behind the descriptions button. (c) The heat maps' RCS08 lines rewritten from five to six: q defined in plain words, "established" and the 22-band correction told apart in adjoining sentences (the contradiction the clinician found), the direction names and "reuse" explained, the pair named in the line that states the negative result, and a new line carrying decision 234's measurement (L 0-3+ 22.5-27.5 Hz +0.08 to +0.20 plainly, +0.01 to +0.12 adjusted; L 1-3+ -0.13 to -0.18 becomes -0.23 to -0.28). Tests first, watched RED: 5 new jest on the triangle (present for a left in-family band, absent for the right lead and for an out-of-family centre, the provisional sentence outside a CLOSED fold rather than merely mounted, the method half still inside), 2 on the current-map card, the drawer's referent test extended. Jest across the three pages 153 / 155, the two failures the known pair (decision 147). Chunks 732.075fce90, 100.2afc23f7, 63.8c13dd7e carry the three sentences; workers reloaded. Not yet watched live: the browser pane needs the PI's login.
236. The exploratory ladder runs at the rate in force, 55 Hz (the PI's ruling 3 of decision 233, built): `configuration_plan` holds `rate_to_hold(rate_in_force_hz)` instead of the cell's rate, reports the cell's own rate beside it (`cell_rate_hz`), and says both in one sentence. The harmonic consequence is named rather than merely flagged: at 55 Hz the half-rate harmonic (27.5 Hz) falls inside the 5 Hz width of 25.5, 26.5 and 27.5 Hz, leaving 24.5 Hz -- the near-hit cell of decision 229 -- the one clean band to watch; `watch_on_harmonic_hz` and `watch_clear_hz` carry the two lists and the card's sentence names them. Live: the ladder is 55 Hz at the pairing in force (100/150 us, the PI's ruling 5), 33 sheet rows, 15 steps and three holds unchanged. Host 1406 / 2 / 0, container 679 / 0; 50 / 50 in the plan's own tests. Decision 230's rate rationale is superseded.
237. The two readings of one titration session, and which is the reading (the PI's ruling 1 of decision 233; step 3 of the cross-cutting build order; panel B item 1 with panel A item 8). `StimOptimizer/routines/titration_readings.py`: `ramp_reading` gives, per watched band across the ladder's settled steps, the plain correlation between band power and pain and the one with the step's own current taken out, each with a resampled interval, plus the band's correlation with the current itself; `holds_reading` gives, for pain and for each band, the ON block against the two OFF blocks with an interval; `session_reading` carries both side by side with the ruling named on it -- the ramp with the current term is the reading, the holds are beside it for comparison. Two refusals are stated rather than computed around: a band that moves almost exactly with the current (98% of its movement or more) gets no adjusted number, because taking the current out of it leaves only noise, and that is itself the finding; a block with no ratings, a constant current or too few steps is a reason, not a crash. **What a ladder cannot settle, measured while building it**: on 15 settled steps a band with NO pain relationship still reads beyond 0.4 once the current is out about one draw in eight, and clears zero about one in fourteen (120 constructed ladders), so every reading carries the sentence that one visit is a lead to repeat, never an established result (METHODS §7). The mirror case is true too and pinned by the tests: a real relationship can read weak plainly and strong adjusted, because the current's own variance dilutes it -- the direction the live left-lead record already shows. Eleven tests, RED first; host 1417 / 2 / 0, container 679 / 0. The card's wiring waits on the visit's own data.
