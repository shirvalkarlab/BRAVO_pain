# Decisions and open items — the digest

Compacted 2026-09-19 and 2026-09-26 at the PI's direction ("not every decision needs to be held, and many can be merged"); compressed 2026-10-02. Every decision resolves here and in full (proofs, counts, timings, quotes) in `docs/decision_log_full_2026-09-19.md`. PI quotes paraphrased with permission (2026-09-19). Struck rows stay struck: the mistake is the lesson. New decisions: a line in Part 3 AND a full row in the full log.

Abbreviations: SO, CL, BM = Stim Optimizer, Closed-Loop, Biomarkers (page or module); JS2 = the Jetstream2 BRAVO; Mac = the local BRAVO; fdr = Benjamini-Hochberg correction across bands; `→N` = superseded by N.

---

## Part 1 — Standing rules, by subject (the log's current state)

**Signal, units, calibration**
- **Tablet clock only, never the device (INS) clock**; device ticks only for gaps within a block (328; `MedtronicPercept/TabletClock.py`).
- Pain reports California local, device UTC (2); chronic detector on California days (142); matcher warns on shared reports, no cap (221).
- Windows >10% zero-filled dropped everywhere (4, 57-59).
- 60 Hz notch off (13); only 256-point FFT modes convert (14). Trace converts at **345.59** (208, 211; `routines/calibration.py`); bridge 72.16 composed, never "measured" (33). Log-log model deleted (11, 218; `DEVICE_percept_rc.md` §10). 8.8 Hz R 0-3+ only from 2026-03-01 (16); no impedance term (17).
- **Log power in no calculation** (PI, 2026-09-19; 202, 204-206, 212, 218).
- **Time modelled nowhere**: drift is a current effect >3 years in (193-196).
- **Every view starts at the implant date** (RCS08 2025-07-16 18:06 UTC; `DecodeCommon/data_start.py`; 260, 263, 289, 313).
- **TD** = time-domain band power, 3 s pieces (montage: "Montage"); **PSD** = the device's 30 s snapshot; never bare "spectrum" (115, 298, 299).

**Statistics and verdicts**
- Intervals signed, never folded; lower bound may be <0.5 (7, 8, 19); forward-chaining validation (12).
- Refusing checks: three states, never pass on absent evidence (9); not-assessed blocks, counted apart (176).
- "Established" = point sign; provisional if any interval spans zero (147); D19 on point signs (134); D26 warns (139).
- **Every chance test moving pain ratings is the exact rotation test**: smallest p 1/n; >5,000 values: 1,000 steps (`stats_utils.rotations`; 314, 315). Grid fdr over 22 centres (63); cell interval by block bootstrap, block = lag-1 decorrelation length (183).
- Offline models: held-out TIME blocks, neighbours dropped, scored **within each block**, reported plain AND current-removed, never refusing (240, 310); current as a named shape, 3-knot spline in guards (241).
- **Current-removed readings are descriptive**, never re-selecting a band or moving a verdict (233 answer 2; 234, 242, 243, 293).
- E1 = change in power per mA pooled over titration runs (model B; other side at ANY fixed current; both legs; <20 s restarts join) (126, 197, 198, 213); never pooled across visits per run (40); curvature tested pooled before any switching value on a peaked band (55, 56, 124).
- **One-band rule**: usable when ONE band falls with current AND rises with pain ("supported") on the stored BM grid (199, 210). RCS08: 0 of 50 (217).
- **Sensing-pair rule**: sense on contacts flanking the stimulating one (1: 0-2; 2: 1-3; 1 and 2: 0-3; 0 or 3: none) (217, 247, 305). RCS08: L 1-3+, R 0-3+.
- **Harmonics** flagged and analysed, never refused; a band "carries a folded multiple of the stimulation rate", never "measures the stimulator" (220, 277, 287).
- Current recommended only when three per-speed checks pass (not flat; beats today beyond scatter; ≥6 pairs of ≥5 ratings on ≥2 California days spanning ≥1 mA) (158, 184); rate ≥55 Hz unless reasoned (138); L and R together (157); pulse widths separate by default (222, 255); clinic settings count only fitted-score ratings (258c); calibration check warns (233 answer 6, 238); drifting pain maps get a dagger (253, 275, 294).
- ~~Reliable change index~~ deleted (231).
- Post-move margin 0 s; 20 s switch OFF (PI: use as much data as we can) (144, 178-179, 191, 196, 217).
- **Safety ceiling 4.5 mA per side, PI-stated** (145, 160; `StimOptimizer/safety_ceiling.py`): **no page proposes, recommends, schedules, simulates or exports a current above it** (306, 308, 312); the 5.0 mA module limit is not it. Side-effect score 2 its own rung, cost 2.0 (165); moderate/severe steps never seed "tolerated" (164); severity statistic per request (166).
- Device thresholds: median averaged reading ± design rule's minimum (180); averaging 3 s, onset 30 s (max), blanking 30 s, transitions 30 s, startup 15 s (150, 169); ranges incl. the 8-30 Hz adaptive band in `DecodeCommon/device_ranges.py` (168, 285).
- Ground truth per row: ceiling-checked device band power (99.5th percentile) > calibrated trace > composed (tagged) > never uncalibrated (33, 47, 52).

**The store**
- One store, `BRAVO/modules/CacheStore/` (30); its key, from database rows alone, decides writing (24, 25, 26); saved 3 s pieces for the shared input set only (289).
- **No pain rating in any recording-derived key or payload** (23, 215, 273, 289).
- Derived writes carry `writer=` and flattened `provenance=`; self-consuming chains refused; refused entries replaced (31, 39, 41).
- Recordings cached without expiry, pain reports fresh each build (22, 78); BM top timeline holds no pain data (216).
- Parquet+zstd, npz, else pickle (29); Redis 512 MB, allkeys-lru, small values, protocol 2 (27, 28).
- One entry per participant per kind unless `KEEP_NEWEST_BY_KIND` (sweep 12, stability 12, per-candidate 6, two SO responses); daily-default grids kept apart (107, 248, 309, 318).
- Stored grids and stability answers cross pages only under the current rule, for their own grid (248, 256, 293, 317).
- Store tests clear only under their own override and never reach a job writing the production root (breached three times: 96, 116, 129).
- Memos keyed on the recording set (130); in-request repeats held per request (267, 278).
- Control analyses are not the store: one file per run in `BRAVOStorage/control_analyses/`, offline only (264).

**Pages**
- Names "Biomarkers exploration", "Stim optimizer", "Closed-loop deployment"; minimalist specification (`artifacts/design_2026-09-26_minimalist_redesign/`): one typeface, five sizes, greys 4.5:1 or darker, 11 px hover the one exception; **red only for device refusals and the safe ceiling**; no decision numbers on pages; each opens on its answer (303, 320, 321, 322, 325).
- CL figures draw once, restyle by trace index (5, hard); heat maps: `doubleClick:false`, guarded purge, no toolbar (88, 91, 324).
- BM does not model stimulation effects (108); heat maps are the headline, nine lengths 1-60 s (170); CL "Choose a band" reads the SAME stored grid and stability answer (131, 248).
- CL: one decision card plus evidence cards (302; supersedes 258(a)); off-choice reports withheld, named (307); pain-score dropdown, NRS default, drives every band-to-pain reading (290, 292); sheet ratings reach the deployment summary only via the red-outlined button (258b).
- Chosen CL band on the server, append-only, with chooser (249); grid-picked bands carry their grid's settings (254).
- Pages judge a band on its own side (141); card text pinned by render tests (174).
- Stim notation `L C+2-`; sensing pairs keep superscripts (181).

**Process**
- Commits as Prasad Shirvalkar, `prasad.shirvalkar@ucsf.edu`, inline `-c` (49); branch `PS_closedloop_deployment`, `v3.1.0` a label, no worktrees (102, 177).
- Superseded documents `git mv` to `docs/archive/<date>/`; no suite counts (34). Plans: planning-with-files, inject-smart, committed, autonomous with attestation, never gated (36, 223). CI runs page tests, numba (257, 271).
- Only code changes are open items (2026-09-10).
- Every check ships live proof: field and difference counts, never a tolerance; alternating timings (step 8's first live run wrote nothing, 41).

---

## Part 2 — Open items

**Waiting on the PI**
- [2026-10-02: resolved by 373, not built.] The matched samples rebuilt by each Closed-Loop deployment request were measured with store writes blocked (2.5-3.1 s); with writes allowed the setup is 1.7-2.5 s, of which a memo could skip about 0.1 s (373).
- Setting in force (L 3.0 mA 100 us, R 2.5 mA 150 us) dates from 2026-09-02 19:15 UTC, not 09-03 (328). [2026-09-26: 09-03 rows annotated, analyses re-run (329).] [2026-09-27: name answered (338); server wording package WP8 open.]
- N-items (`artifacts/pending_items_from_handoffs_2026-09-25.md`), ruled 2026-09-27. Closed, no code: N-01, N-02, N-03, N-07, N-08, N-13, N-14, N-16, N-17, N-18; N-10 (July 2025 step above the then limit: late side effects, not a records error); N-06 waits on a usable sensing pair. Built: N-11 (340), N-12 (341). Answered: N-04 (280/285), N-05 (315), N-20 (301). Open:
  - **N-09.** Sheets show 10 rates (820 hand-filled steps, 29 visits, one-second precision), the device history 7; 25, 85, 100, 180 Hz never on the device; 100 Hz clearly written for two July 2025 test groups. Delivered-but-unsaved or planned-never-given: only someone present can say.
- RCSchronicpain (another repository), 2026-09-27: tree clean, pushed; `stash@{0}` "Claude Code BRAVO session edits 2026-09-25", 14 files / 959 lines (MATLAB outcomes refactor, statistics/test files) on `refactor_stages123`. PI said delete; permission refused; he runs `git stash drop stash@{0}` after checking. `stash@{1}` ("On main: !!GitHub_Desktop<main>") untouched. "3 token-shaped values" = `credentials/define_env_redcapAPI_tokens.m`, pushed by the PI (`717bb6d8`, "update credentials"); untouched.
- Left for the PI by 322: gutter Arial, faint PLANNING ONLY watermark, badge uppercase.
- CL's 21 "can't be programmed yet" reasons in four buckets: PI reviewing (2026-09-27).
- [Resolved by 366, 2026-10-02, in the cache.] CL redrew endlessly once its simulation loaded, always showing "Something it depends on has changed": `resultCache.getResult` (his file) gave read time as computed time, which the simulation label includes (365).
- [Resolved 2026-09-27.] Hover third line shortened (339, 343); more needs his instruction (2026-09-16 ruling).
- [Resolved 2026-09-27.] PI's build caught a missed registration-page disclaimer; rebuilt, grep-confirmed; bundle current through 339.

**Code, not yet built** (2026-09-25 handoff scan)
- P-11: trace device units on the timeline, check against 216. [2026-09-27: P-10 closed with 328, first block's tablet time kept, `MedtronicPercept/tests/test_no_tick_times.py`.]
- P-18: timeline detail panel; draft `artifacts/spec_2026-09-25_P18_timeline_detail_panel.md`.

**Waiting on data or a visit**
- **Next visits** (`artifacts/protocol_2026-09-25_rate_swap_and_down_first_ladder.md` §11): ≤3 h; Visit 1 rate swap (second cycle chosen in the chair), second rater; Visit 2 stimulation off, full 90-minute wait; down-first ladder answers carry-over (272). First home session: check the chronic log spans a group change.
- Titration readings (237) reach the card once the visit's data exist.

**Caveats on the record, not fixable**
- [PI: both resolved, 2026-09-27.] Short-copy gap (289: two 2026-09 windows read a partial recording; current one re-measured, older two stand); R environment (288: in the Dockerfiles, no image built).
- Not watched on screen: 292's dropdown, 294's daggers, 324's q wording (partly →339; checked in built files only).

**Rewritten, not open**: 10. No 110 Hz "heat map" exists; pre-registration (`PREREG_RCS08_110Hz.json`) unrun, counts do not reproduce (109); re-measure before reopening.

**Notes for the clinic, not items**: 55 Hz has one left-only visit day on the left electrode; no device FFT while current is stepped, so none for any ladder; 217 stands (L 0-3+ needs L C+1-2-).

**Closed**: titration session (item 30, 2026-09-16; 213); 2026-09-21 rulings (218-227); item 15 (258, 284, 291); "found, not changed" notes in 249-318 (fixed by 254, 255, 270, 309, 314, 315, 317, 318, 323; P-16 declined, 316). Do not reopen: disk reads 4.8% of the page; matching 0.2-1.7% of Recompute. Items 1-9, 11-14, 16-29, 31: full log Part 2.

---

## Part 3 — Every decision, one line (number, date where it matters)

Refs: commits or PRs; a range like `282-288.` is one merged row.

1. R converter without the frame converter (`33f45a5`).
2. Pain reports California local; UTC parsing smeared matches 7-8 h (`a4e4e68`).
3. Concatenation repair kept; re-decode 67/67.
4. Windows >10% missing dropped (zero-fill deflated power).
5. Figures draw once, restyle by trace index, memoised params: hard rule (`255e0ef`).
6. Net-benefit cut-point rule removed (= cost rule; PR #3).
7. Discrimination interval not folded (`c50be37`).
8. Per-epoch AUC signed, oriented once on the pooled result (PR #5).
9. Three-state refusing checks; stability check abstains if untestable (PR #5).
10. One-source recommendation; recommended vs programmed stated; abstains on ramp guidance (`b0597f8`).
11. Frozen per-participant conversion model, tiered fallback; modelled switching value flagged (`771f3c2`).
12. Forward-chaining out-of-sample validation (in-sample hid reversals 0.55→0.24) (`d9d58a4`).
13. Mains notch off (`f915257`).
14. Only 256-point modes convert (`f915257`).
15. Direct spectrum-to-device route; round trip within 0.8% (`f915257`).
16. 8.8 Hz R 0-3+ from 2026-03-01 (earlier: settling transient) (`e9d7a80`).
17. Impedance term rejected, p 0.26 with grouping (`a9c3a01`).
18. Transform route at 352.62 primary (r 0.9927) (→209 →211: 345.59).
19. Moving-block bootstrap, effective n; de-folded lower bound refuses.
~~20~~. →21. Cut-point through the frozen model: units error (z-scored log as linear).
21. Fallback models device power off the raw trace at the cut-point's centre; never converts the switching value (`09798f7`).
~~22~~. →78. Recordings cached without expiry; reports uncached except read-only drill-downs.
23. No pain rating in piece file or key: a report change alters 19,464 values, writes 0.
24. File key from database rows alone (0.33 s).
25. Key holds event metadata, decode stamping, every constant.
26. Key, not caller, decides writing.
27. Redis for locks, small values; big products as files (0.05 vs 0.14 s).
28. Redis 512 MB, allkeys-lru, both compose files (`b7036bf`).
29. Parquet+zstd tables, npz arrays (CSV/JSON lose the timezone).
30. One store implementation; duplicate deleted.
31. Provenance chain and constructed-cycle proof before write-back.
32. Band range: 22 centres, 8.5-29.5 Hz ("8-20" a slip).
33. Ground-truth rule: ceiling check, fold ratio.
34. 50 documents archived by `git mv`; no suite counts in documents.
35. Pain-report snapshot keyed on content, unread, history kept.
36. Plan: planning-with-files, inject-smart, committed; no attestation or gate.
37. `therapy_settings` raw, keyed on source-file rows; `therapy_pain_matched` raw-derived; 0.01 vs 33 s.
38. Sweep writes two tidy tables; key match serves its response.
39. Store refuses writer-less derived kinds; one module object for both import spellings; `exploration_ladder`.
40. Amplitude effect per run and band, never pooled across visits.
41. SO reads as consumer, writes five products; refused entries replaced; code digest in key; first live run wrote nothing, tests green.
42. DecodeCommon real on both runners; naive start time mirrors platform.
43. per_pro readers on channel_index behind a switch: 0 differences, 54 vs 65 s.
44. Piece builder reads prepared traces (<1 s of 37 saved).
45. Deployment report accepts the calibrated frame (had raised on every candidate).
46. Redis build lock on the pieces' key: four cold requests, one build, 41 vs 368 s.
47. Device route ceiling (provisional →52); `ground_truth_verdict` written and read.
48. `cache_status` on every module response, one line under each recompute control.
49. Commit identity: the PI's name, UCSF address.
~~50~~. →51. Per-recording spectra to the store ("read by no page" true, beside the point).
51. Assembled matrix stored; per-recording directory stamp-served (0.35 vs 3.1 s).
52. Device ceiling = 99.5th-percentile table per (electrode, centre), full history.
53. Track E: `biomarker_psd_matrix` raw kind, rows in collection order.
54. Result cache bounded by bytes and resident participants (do-not-edit lifted once).
55. Switching value on a peaked band: one-to-one side only, after a pooled curvature test (visit-level errors).
56. Pooled curvature test live: mixed; one contact, 13 points, 4 visits.
57. Entangled routine skipped the zero-fill rule (review).
58. Fixed: missing mask through the adapter.
59. 31 of 386 recordings excluded; 29,704 values and a best band moved.
60. Recompute: one request per press (watched live).
61. Entangled routine stays out of the sweep (four axes differ).
62. Heat-map redesign: Option 2, search-first.
63. Grid fdr over 22 centres, no autocorrelation adjustment (rotation-test p since 315).
64. Match direction in the sweep; BH built; missed rule-version bump served a stale response.
65. Track D: BH label on the CL grid; forbidden bands selectable, greyed.
66. Track A (SVG grids, hover/click, contact strip); drill-down outlier bug caught.
67. Track D minus the device-rules column (needs amplitude etc.); bare import broke the container.
68. Track D leftovers closed; one `MatchDirection` helper.
69. All-None family test; `bh_fdr` = statsmodels to 1e-10.
70. RCS08 had zero study links: joined, grid seen live, grant revoked.
71. `native_lsb_by_channel` added; two live spectrum builders unmerged.
72. Builders not merged: same DSP, different sampling unit, four treatments.
73. Shared matching layer designed; two of four matchers lacked independence rules; a crossover trial is unbuildable.
74. Direction consistency check (chain-rule signs); contact filter bug caught.
~~75~~. →231. Reliable-change minimum built; unassessable on RCS08 then.
76. `DecodeCommon/matching.py` ported from the richest matcher; 600-trial equality.
77. Old scatter/violin panel removed; hover 2.9→~1 s (recordings memo).
78. Amends 22: report table held for drill-downs until the next build.
79. Six backend efficiency fixes, each 0-difference.
80. Frontend dead code removed; purge-on-update and defeated-memo bugs fixed.
81. Four Plotly render-manager findings: none worth a 58-file blast radius.
82a. CL audit: sign-off read retired `stim_stable`; two checks unwired.
82b. BM grid on the shared cache; one Recompute; other scores prefetched.
83. `stim_stable` reads the three-way verdict; `adaptive_band` checks edges; two dead files deleted.
84. Host suite in the container: one environment mismatch; the test wiped the cache (→116).
85. Participant id to the store; cross-participant eviction fixed.
86. One pain-score dropdown; Y-axis delivered lengths; Medtronic labels; gunicorn needed SIGHUP.
87. Plotly heat maps with side panels; requested and delivered lengths separate.
88. Gridlines off; shared `heatmapHeight`; modebar off.
89. 88's sizing regression corrected.
90. Title, stats rows; full-width plots; thumbnails L then R; pooled warning hidden.
91. Native Plotly scatter, violin; click listener and double-click crash fixed.
92. Availability endpoint cached on recording set and report digest: 8.4→0.6 s.
93. "How to read this" drawer deduped, reordered: 669→436 words.
94. Sweep outliers: fixed per-(contact, centre) ceilings per 3 s piece, backfilled; 0.436% excluded.
95. Dead export button → "Open this grid in Closed-Loop".
96. Stability grid by background job after the grid; page/run key mismatch found live.
97. Daily stability precompute; stopped-early run refused.
98. Stability column: 5,148 fields, 0 differ; page 291→10.6 s.
99. "Cannot tell" example at 17.5 Hz (p depends on band width).
100. CL: cache status on every return; wrong-key handler; zero logger calls fixed.
101. CL `bravo_service.py`; catch-all logs (5-day silent outage); note/reason mismatch fixed.
102. Naive timestamps UTC everywhere; gitignore `_agent_bridge/_*`; agent worktrees were months stale.
103. Consistency check wired; `within_visit_pooled_shape` stored, cold = warm.
~~104~~. →231. Reliable change as warning; wrong-frame defect caught reading values (0.93 spread gives cut-off 2.6).
105. `within_visit_band_scores` deleted (nothing unique live).
106. Snapshot share per cell; R 0-3+ 79% snapshot-served, length axis 7x flatter.
107. Every score precomputed; `KEEP_NEWEST_BY_KIND` replaces one-entry-per-kind; guard against jobs starting jobs.
108. Item 10 closed: BM does not model stimulation effects.
109. No 110 Hz figure exists; pre-registration unrun, counts irreproducible.
110. Fake patient, per-rating overlay deleted; neighbouring-line trap noted.
~~111~~. →231. Reliable change = 1 h pairwise SD per score, repeats removed; panel; NRS cut-off 1.01.
~~112~~. →231. Stim-off pairs stay in the reliable-change minimum.
113. Sign-off embeds browser figure snapshots; grid cache slot collision; stale workers.
114. Timeline circle = many-centre reader at its centre (240/240).
115. Many-centre reader deleted; never bare "spectrum".
116. Host suite's failure fixed: it cleared the production cache each run.
117. Pooled-PSD builder on the shared matcher (0 differences); dead branch crashes.
118. `align_pros` already shared; two selectors are not matchers; `max_per_rating` open.
119. Histogram caption names score and total.
120. Timeline's own match window removed.
121. Dash markers removed; snapshot route counts 30 s per snapshot on the length axis.
122. CL grid: 22-row heat map, radios; hemisphere commit bug fixed.
123. CL prose folded; ledger → counts strip; renamed "Sign agreement", "Full parameter recommendation", three columns.
124. E1 stays linear (no peak in literature or RCS08); titration protocol → item 30.
125. Three-source panel pooled across visits from stored per-run points, prefetched.
126. E1 = change in power per mA pooled over titration runs; historical estimate beside.
127. No row (numbering gap).
128. CL-DBS simulations card, M0-M3, 3 s pieces, device clock; per-candidate entries.
129. A test emptied the production store; clear only under the override.
130. Memos keyed on recording-set identity.
131. CL grid reads BM's stored grid by settings tag, built on demand.
132. Device rules take rate and pulse width from programmed settings if missing.
133. D16 impedance from a fixed-current test; automatic low-current reads fail spuriously.
134. D19 passes on point signs.
135. D30 from the device's active group.
136. Device facts rebuilt daily; two scanner misreads fixed.
137. 123 dead tests deleted; two-stage path behind a flag.
138. Stage 1: ≥55 Hz unless reason stated.
139. D26 reads pooled change in power per mA; warns.
140. SO first build 51→10 s; BLAS one thread; no GPU in the container.
141. CL judges a band on its own side; 20 s margin first wired.
142. Chronic detector on the California day: 26.2% of ratings moved; memo, key fixes.
143. SO review: own-side pulse width; one module object per package; stream anchors off.
144. 20 s margin behind a switch, OFF (two removed points flipped a verdict).
145. Ceiling PI-stated; 3,696 lines of dead modules and unread BM blocks deleted.
146. Titration session card from the data (amended by 160); two SO responses kept.
147. "Established" = point sign; provisional flag.
148. Timing ranges from FDA table 2; recommendations from the data.
149. Ranges in both modules; "programmed today" shown.
150. Six-method contest: Kalman design rule; averaging 3 s for response time.
151. Simulation card replays programmed and recommended timing, counting undone switches.
152. T3 design rule; kind in `KEEP_NEWEST_BY_KIND`.
153. T4 occupancy check; sign error caught against the contest report.
154. T6 startup dip: two methods, unreconciled.
155. T5 block bootstrap vectorised: 36-90 s, bit for bit.
156. T7 gain wiring confirmed on constructed data; awaits titration.
157. L and R modelled together; four-chart strip removed; injected "coordinator" messages ignored.
158. Honest-current rule; home titration schedule; two claims in 157 corrected.
159. Current map cards on the page; surfaces in the response.
160. Ceiling 4.5 mA; ladder: ramp+test rows, 1.0 mA down legs, joint corners, sheet rows.
161. Clinic sheets a separate stream; Excel turned "8/10" into a date.
162. Titration card and clinic section drawn.
163. "Make Google sheet" button; openpyxl `value=None` does nothing.
164. Moderate/severe steps excluded from tolerated anchors.
165. Score 2 its own rung, cost 2.0.
166. Amplitude-severity statistic per request; typed number retired.
167. Clinician review: 19 findings; root cause "computed, stored, not on the page".
168. Three Criticals fixed; device ranges in DecodeCommon.
169. Ranges match the tablet; onset max 30 s; 5-minute rows beyond the device.
170. Onset grids ≤30 s; sweep to 60 s, nine lengths.
171. Heat-map text, layout in the PI's wording.
172. Retired-table notes reworded for the heat map.
173. Corrected-statistic line beside the violin; n not repeated.
174. Referent audit: 10 of 12 fixed; render test per card.
175. "What would change this" reworded; second in-clinic plan table and sign-off duplicate removed.
176. Four leftovers: capital, stale comments, dead builders, check wording (both copies).
177. Default branch `PS_closedloop_deployment`.
178. 20 s margin ON.
179. 178 reversed that night: OFF until a titration session decides.
180. Thresholds placed from the data; tablet's low/high-current pair beside.
181. Google Sheets via the PI's OAuth token; `L C+2-` notation; centred cells.
182. Clinic sheets synced from Drive daily.
183. Block bootstrap for cell intervals.
184. Coverage counts occasions: ≥2 California days per pair.
185. Stability answers on the BM grid, one home for the words.
186. Clinic-sheet ratings in heat maps behind a switch, off.
187. T1 misread; unread powerdomain block deleted.
188. Hover three lines; Pearson, Mann-Whitney p on the backend (scipy); browser stats deleted.
189. Descriptions folded; pairing line; pulse-width pooling plan (A, toggle) unbuilt.
190. Duration weighting: no recommendation changes.
191. Margin sweep: 0 of 30 settled values change; margin = minimum-hold filter.
192. Current map: absolute ratings, colour centred on today's setting.
193. Age penalty inert, unsupported; log drift ≠ raw drift.
194. Time as fitted input (→196).
195. Clinic stream without time input (→196).
196. Time modelled nowhere; S7 at 0 s; run finder needed the other-side rule.
197. Runs count whatever the other side holds: 11→17.
198. Pooled E1 model B kept.
199. One-band rule: usable cells 6→4, all harmonics (short copy, 289; since 210, 217).
200. Review leftovers C3, C4, C6, C7, T2, T3 built.
201. C6 off-label line removed.
202. No log power on the E1 path; other sites listed for the PI.
203. Compaction: digest, full log (`docs/`), shorter CLAUDE.md, house rules, store architecture; handoffs, reports, plans, generic rules deleted.
204. No log power in the pooled full-spectrum path or pain correlation: 10 of 132 stability verdicts moved, chosen band kept (short copy, 289).
205. Outlier rule (5 MAD), heat-map logistic cross-check on raw power; log-scale option refused.
206. Aperiodic (1/f) fit and `fooof` transform deleted (unused; device cannot threshold peak prominence).
207. Calibration (no code): frozen model's curvature = between-band gain pooled into one line; constant refitted.
208. June calibration anchor reproduced, extended to 2026-09-03 (n 133, k 345.59); block check, 5-MAD ratio rule; recipe, de-identified blocks committed.
~~209~~. →211. Transform constant = midpoint of two time blocks, 349.10.
210. One-band rule's pain leg: "supported" (positive, interval above zero); "established" beside.
211. Transform constant 345.59 everywhere (one median over all blocks; 209 superseded); bridge 72.16 composed; verdicts unchanged.
212. BM calibration panel shows the calibration in effect (transform constant, June reference, per-centre/pair bridge ratio, server constants), not the June model.
213. Run finder joins recordings split by <20 s tablet restarts at held current; rising and falling settings count, tagged by leg (PI: pool both); 2026-09-16 left ladder: 8 settled currents, one run; verdicts unchanged.
214. CL "LSB & power" cross-check: µV trace with transform band power vs the constant in effect; independent pairing 1/352.7 µV² per LSB (0.98×).
215. CL inputs keyed on recording set, both calibration constants, rule version (had served a stale-constant frame).
216. BM top timeline = acquisition timeline: no pain reports, raw kind `acquisition_timeline`; rating-centred index at `/queryPsdScanIndex`.
217. Readiness applies the sensing-pair rule: RCS08 (left C+2-, right C+1-2-) allows L 1-3+, R 0-3+, neither pain-rising; usable 11→0 of 50; 20 s margin OFF.
218-222. PI rulings 2026-09-21: June log-log model (218) and four uncalled chronic-detector routines (219) deleted; harmonic rule warns only (220); matcher: no per-report cap, warns on sharing (221); pulse-width pooling behind a toggle, default separate (222).
223. Amends 36: plan `.mode` may be `inject-smart autonomous`, attested at start and per edit; `gate` off.
224-227. 2026-09-21 cleanup: Binarization card option C, timing histogram (224); per-report band-power reader deleted (225); duplicate timeline dropped (226); left refit panel deleted, recipe reports median-ratio interval and spread, modelled-threshold band = own scatter, stale-constant comments fixed (227).
228. Square's scatter and violin use the grid's ratings, sheets included when on (REDCap-only drew a rising line beside a negative r); sheet points hollow.
229. Exploratory search, L 1-3+, 252 settings (window, direction, cap, reuse, sheets): no row positive at q < 0.05; sheets on, 10-22 of 22 bands fall with pain; near-hit 24.5 Hz, 60 s, 120-min pre-report: r 0.32, p 0.054 (corrected by 315). A lead.
230. Exploratory ladder, L C+1-2- (L 0-3+ needs those contacts): 15 steps up/down, three 5-minute holds off/on/off, first-exposure stop, 33 sheet rows (rate 236; watch list 277).
231. Reliable-change index deleted (12 pairs, too much scatter); supersedes 75, 104, 111, 112.
232. Research batch 2026-09-22: four reports, three reviewers each (`artifacts/research_2026-09-22_*`): left-lead pain-rising bands rest on the current in force; eight questions for the PI.
233. PI's answers: (1) ladder reading = ramp with current term, holds beside; (2) "supported" need not survive current removal; (3) ladder at 55 Hz; (4) back-site parallel fit; (5) next session 55 Hz, 100/150 us, merged with 60/160 us data; (6) calibration check warns; (7) adjusted grid behind a switch; (8) chosen band on the server.
234. Heat-map correlation with own-side current removed, behind `AdjustForStimCurrent` (off); plain value decides; switch in the store key, not the settings tag; current from `therapy_settings` (`routines/stim_current.py`).
235. Interim caveats: current-confound note on a left 21.5-27.5 Hz band (→242); current map's pooled association fails out of sample; heat maps' RCS08 lines rewritten.
236. Exploratory ladder at 55 Hz, the rate in force (cell's rate beside); supersedes 230 ("24.5 Hz is clear" corrected by 277).
237. Titration readings (`titration_readings.py`): ramp with current removed, holds beside; no adjusted number for a band 98% current; one visit = a lead. Not yet on the card.
238. Clinic-stream fit follows the requested site (was left leg); back site fitted; pre-registered calibration check per surface warns.
239. `coverage_gap`: coverage refusal → pairs the next visit must repeat or add, under the ceiling; one-side ladders need joint corners (ruling-5 count corrected by 255, 258(c)).
240. Two guards per offline model and a pre-decoder check (`confound_diagnostic.py`), on no page; no band set beats its shuffled level (corrected by 310, 315).
241. Current removed as a named shape (`stats_utils.CovariateShape`: line, square, 3-knot spline, three kernels, per-setting levels); guards spline, `partial_corr` line. L 1-3+ pain turning over with current: suggestive; no shape changes the verdict.
242. CL basis stated: one sign-off verdict; stability answer ranked in "What would change this" and the coherence note; one caveats list (`adapter.caveats_for_report`); E2 current-removed, descriptive (NRS left 0.564 plain, 0.553 adjusted; corrected by 290).
243. SO ordered as a decision: sensing rule visible; "still positive with the current taken out" per band (stored adjusted grid); "proven better" exposure and rate-pin assumption stated (layout →303, 320, 325).
244. CL jump links follow card order (test reads the page file).
245. Amends 243: current-map legend open; stopping rule per side (unassessable on RCS08).
246. Housekeeping: three unread CL field groups removed; squares show effective independent ratings, grids shuffle reconciliation; whole-search count (corrected by 315); time-of-day and weekend check (moved by 264; R 1-3+ cycle withdrawn, 265): weekends raise pain and L 1-3+ power; removing them moves r ≤0.019.
247. Device rule D52 (sensing pair) blocks on CL (had passed L 0-2+ with contact 2 stimulating); caveats to four decimals; heat maps at box width.
248. Stability answer: one entry per grid (12), named; "Choose a band" reads only its grid's; grid settings gain the sheet switch (131 broken since 186).
249. Chosen CL band on the server, append-only, with chooser (`chosen_band.py`, `/api/queryClosedLoopChosenBand`); browser-only copy flagged; sign-off names band and grid.
250. Parameter notes: one heading counting its checks; two long-failing CL tests repaired.
251. Coverage gap under "Enough combinations tried?" on the current-map card.
252. One-off left chronic power vs left setting changes (`stepB3_chronic_level_shift.py`): 4 of 21 readable; three on L 1-3+ at 23.44 Hz fall as current rises, one interval excluding zero; unread.
253. SO maps fail calibration (`calibration_diagnosis`, warning): left-leg 55 Hz 60/160 us map drifts between time blocks; others thin. No boundary-avoiding kernel (see 275).
254. Grid-chosen band carries its grid's pain score, split, window to the deployment summary (was NRS, tertiles).
255. Pulse-width-pooled clinic fits via the toggle; ruling 5's merged answer (`next_session_coverage`) heads the clinic section. Corrects 239: 3 of 6 pairs, not 5 (2 of 6 since 258(c)).
256. Stopped-early stability run protects its own grid's answer.
257. CI runs page tests (jest).
258. PI rulings 2026-09-24: (a) sign-off card last (→302); (b) red-outlined button adds sheet ratings to the deployment summary, default off, one merge helper; (c) clinic settings count only ratings with the fitted score; (d) legibility (→320).
259. Recompute bar enlarged (rule 7 lifted once).
260. Every view starts at the implant date (RCS08 2025-07-16 18:06 UTC; `DecodeCommon/data_start.py`): earlier measurements dropped on read, setting in force moved to it, rows kept.
261. Coverage reads stored rating days as days (had summed or skipped arrays).
262. PI's analyses: both-off stretch 2025-07-16 to 2025-08-22, left 21.5-25.5 Hz family rises with VAS (lead); a current with memory never beats the current in force; 240's window → 60 minutes (corrected by 310).
263. Implant cut reaches export, raw recordings list, participant-context service, custom-analysis pipeline.
264-265. Control analyses saved offline, one card on BM and SO (`modules/ControlAnalyses/`, all runs kept); 265 corrects 246: from implant, R 1-3+ has no daily cycle, L 0-2+ does.
266-271. Exact speed-ups 2026-09-25: pieces in batches, one FFT each (266); in-request repeats once (267); E2 interval fits single-threaded (268); numba design-rule filter, no disk cache (269); CI installs numba (271); 270: participant-context service fixed for RCS08.
272. Carry-over test saved: every fall followed its rise, so carry-over and drift cannot be told apart; a down-first ladder would.
273-274. No pain rating under a label that ignores it: CL inputs hold the settings stream, design matrix per request (273); numba type-check log silenced (274).
275. Regression to the mean: the 1.6/1.2 mA swing is the whole group's drift those weeks, not the setting (restates 253).
276. 262's current-removed p → its own shuffle (corrected by 310, 315: nothing beats its shuffled level).
277. One harmonic check (`analytics.harmonic_landings_hz`), PI's advisory wording; at 55 Hz centres 22.5-29.5 Hz, 24.5 Hz included, carry a folded multiple; 9 of 22 clear.
278-279. Exact speed-ups: recording-set identity once per request (278); grid medians in one pass (279).
280-281. ROC cut-point in standardized band power units, burn-in stated, stale lines fixed (280); corrected sheet cells keep the delivered value (281, P-13).
282-288. 2026-09-25 batch: rating-persistence, stepped-current control analyses (282); three numba compilations, one-column time-block labels (283); stability panel dated (284); P-05 to P-09, P-15; three-week burn-in kept for convergence (285); P-14 via the difference routine (286); harmonic bands flagged, not struck (287); Dockerfiles install R 4.3.3, lme4, lmerTest, emmeans, unbuilt (288).
289. Saved 3 s pieces only for the one input set all pages use, else in memory; key carries the implant date. A short copy had served three windows (Part 2).
290. E2 read the previous settings period's ratings since `8fbe11ba`; fixed. The only E2 ever "established" was that one: L 1-3+ Left Leg VAS now 0.641, not established.
291-292. Stability card: per-state odds ratio with interval, one rating in one state and one week (291); intervals allow repeats per pain report; CL pain-score dropdown (NRS default) drives every band-to-pain reading (292).
293. Deployment summary shows the current-removed area beside the plain one; "Choose a band" reads only current-rule stability answers.
294. Dagger on each recommended current whose pain map drifts between time blocks (wording per 275); pooled maps too, not the across-rates table.
295-296. Exact speed-ups: calibration folds in parallel (295); settings history per session file (`therapy_settings_by_file`), one parse per new file (296).
297. Research band detector (two versions, `band_detector.py`) saved as control analyses; REDCap-only: nothing clears q < 0.05 on either pair (p per 314). A lead.
298-299. Pages say TD and PSD, never "spectrum"; square's split by source shown (298); montage pieces labelled "Montage" (299).
300-301. Beta-peak classifiers re-saved under pinned scikit-learn; old PSD files counted, none deleted (300); visit protocol revised, June mock-ups removed (301, `4590af6a`).
302-304. One decision card per page (PI, 2026-09-26): CL decision plus evidence cards (supersedes 258(a)), device-units panel gives no value to program, unchosen bands' reports withheld and named (302); SO status line, allowed pairs visible (303); BM pain-score selector first, one status line (304).
305. Sensing-pair rule in `DecodeCommon/sensing_rule.py`; grid response carries it outside its key.
306. CL recommends nothing above the per-side ceiling (limit had inherited 4.8 mA): capped, cap stated, measured currents kept; not a refusal.
307. One pain score and sheet setting across CL (others withheld, named); sensing-pair tabs named for screen readers.
308. SO offers nothing above a side's ceiling: held ladder side at it, safe sets bounded, queues filtered, second-stage windows capped; the 5.0 mA module limit is not the ceiling.
309. Robustness answer: six entries, one per candidate (107's failure again); timeline shows pain-score labels.
310. Pre-decoder check scores held-out predictions within each time block (pooled, current alone predicted the block); rotation keeps observed order. Nothing beats its shuffled level.
311. P-12's band-power cells re-measured on full pieces; conclusions stand (R 0-3+: 323).
312. Seven items: setting in force above the ceiling shown, not offered; timeline pain label fits gutter; control-analyses and stored-results lines folded; ROC prints 293's adjusted area; stability kind and rule in `sweep_settings.py`; stale class renamed; P-16 to the PI (316).
313. Timeline dates a spanning chronic file from implant; refusals name the quantity, not the column.
314. Band detector: exact rotation p, each reading against its shuffled level; CL prints no column names. REDCap-only: nothing clears q < 0.05.
315. Every chance test moving pain ratings = exact rotation test (`stats_utils.rotations`); chunk shuffle deleted (false p ≤ 0.05 in 10.7% of records). Past the 22-band correction: daily 32→10 bands, BM settings 34→17; one-band rule still 0 of 50.
316. P-16 (rename the SO package): PI, "no rename".
317. Cross-page grids served only if built under the grid rule in force; rule, kind, key in `sweep_settings.py`.
318. Daily-default grids kept by a keep group, one per pain score, outside the twelve.
319. Sign-flip bootstrap projects vectors directly; R 0-3+ fits in memory; every p, estimate, standard error unchanged.
320-325. Minimalist redesign (`artifacts/design_2026-09-26_minimalist_redesign/`): one typeface, five sizes, greys 4.5:1 or darker, colour for data (320); nine mismatches fixed (321); twelve taste proposals: red only for device refusals and the ceiling, statistical blockers in ink with ✕ (322); 318, 319 proved live, P-12 on R 0-3+ (323); toolbar, corrected-q label, device-rule counts restored (324); old names back ("Biomarkers exploration", "Stim optimizer", "Closed-loop deployment"), one "Adjust matching parameters" button, heat maps aligned, long SO sections fold, blank sheet cells blank (325).
326. Page-against-server review (2026-09-26; 40 findings, 39 kept after a skeptic's check): SO current map mirrored across its diagonal since 3779bfb8 (2026-09-14), flipped; "proven better" strip reads the frozen setting's verdict and joint pulse-width stratum; saved answer keyed on sheet steps; CL headline follows the server; read-back ticks clear on change; refusals name who clears them (`resolved_by`, for PI review); BM heat maps flag staleness, follow the sheet switch together; p or q in [0.045, 0.05) prints "< 0.05"; safety lines unfolded; sheet named by study code.
327. Records cleaned (PI, 2026-09-26): digest 213→54 KB; ten finished plans, superseded designs to `docs/archive/2026-09-26/` with INDEX; SPEC.md the one design specification (through 326); no live plan.
328. Tablet clock only (PI, 2026-09-26). On RCS08 `FirstPacketDateTime`, chronic log, patient events, event log, group history use the DEVICE clock (≤2.1 h fast by 2026-09, ~25 s/day since 2025-12); only `SessionDate`/`SessionEndDate` are tablet. `MedtronicPercept/TabletClock.py` (on read; exports untouched): tablet time = device seconds + export anchor (SessionEndDate − Final DeviceDateTimeOffsetInSeconds; spread 121 s; 27 exports lacking end time: SessionDate − Initial). Database corrected in place (1.3 GB backup); duplicates collapsed (patient events 21,109→1,226); 396 old-block entries excluded. Verdicts unchanged; setting in force since 2026-09-02 19:15 UTC, not 09-03.
329. Device-clock readers fixed (PI, 2026-09-26, re Sep 3): today's setting re-dated 2026-09-03 → 2026-09-02 19:15 UTC; typed stretch date removed; level-shift report fixed, re-run with all control analyses. Moved: no pair has a daily cycle (L 0-2+ lost it); R 0-3+ at 30 s the one plain reading above its shuffled level before any decoder (p 0.035, q 0.42); 60 s ratings fell (L 1-3+ 187→104); regression-to-the-mean outside comparison 33.8%→6.6%; 6 h current memory edges past the current in force (NRS). Unchanged: 0 mA L 1-3+ rise with VAS, level-shift directions, band detector (nothing at q < 0.05).
330. All 583 exports' time fields checked (184 paths): no tablet-clock field missed (only SessionDate, SessionEndDate: true UTC, daylight saving correct); every device field read is converted (at most ~5 min off). REDCap, sheet and device times agree (median 0.3, 0.0 min; 393 of 778 reports within 2 min of her remote press vs 20 on the device clock). Earlier 45-60 s counts were re-stamped copies of one press. Adopted: 15 min either side (`artifacts/analysis_2026-09-26_json_time_fields_and_matching.md`).
331. Matching defaults (PI, 2026-09-26, on 330) in `sweep_settings.py` (`matchingDefaults.js` pinned by test): window 15 min either side for page (saved 5 or 60 moved once) and daily (was 60); direction "nearest", not "pro_first" (kept two TD pieces <30 s apart: 3 reports on RCS08, 0 under "nearest"; pairs 380 vs 377 reports); cap 3, gap 2 min, TD 30 s, no reuse, sheets off. CL inherits BM's last run (grid, stability card, summary except direction). RCS08: verdicts, 0 of 50 unchanged; daily NRS grid 9→7 bands past the 22-band correction (all falling, L 1-3+); L 1-3+ 24.5 Hz "VALIDATED (stim-dependent)"→"candidate" (unconverged, OR 2.44, 2.43-2.44); SO right ladder (R 0-2+) dropped.
332. Stability answer per grid's own pain score (found by 331; precompute set only `SweepMetric`, setup read `LabelMetric`, fell back to NRS: six grids held NRS answers, 100 cannot tell, 32 behaves differently). Rule v7, cannot tell/behaves differently: NRS unchanged; VAS 87/45, Left Leg VAS 120/12, back VAS 103/29, McGill 100/29 (3 not computable), composite 122/10.
333. E1's fallback now a stated caveat (open item from 326): when the pooled titration table (124) is unreadable, the per-setting-period change in power per mA over all data can flip sign (L 1-3+ 24.5 Hz: pooled -7.31 per mA, fallback +1.63); `source` already named it. Live: both sides pooled, 0 caveats added, 0 fields differing.
334. All-band scan follows the clinic-sheet switch like the heat maps (PI, 2026-09-27): `run_for_participant` takes a DataFrame `_merge_clinic_sheet_ratings` cannot write, so a sibling appends sheet rows via `sheet_ratings_for_metric`; existing rows untouched; off, no change.
335. Fold toggles: one filled arrow chip, not six plain 14 px characters (PI, 2026-09-27): `views/Reports/paper/FoldArrow.js` in `paper/Fold.js`, `paper/Section.js`, `ClosedLoopSim/Fold.js`, `ClosedLoopSim/ThreeSourceResponsePanel.js`, `Biomarkers/MatchWindowBand.js`, `StimOptimizer/typeScale.js` (`SizedFold`); a test fails any private arrow. Visual only.
336. Tertile key no longer moves with left-dragged sliders (PI, 2026-09-27, "key naming inconsistency"): `sweep_settings.label_strategy_params` returns fixed 33.3333/66.6667; the split never changed, only duplicate filing.
337. BM high/low pain split preview (PI, 2026-09-27): `binarizationModel.classBalanceFlag` warns on too few (Peduzzi et al. 1996: minimum 10 in the smaller group) or lopsided groups (3:1, a general severity cut-off); "Low"/"High"/"Left out" boxes show counts only, sources on hover.
338. On-screen name "UF/UCSF BRAVO" (PI, 2026-09-27; open since 320): tab, page titles, sidebar, top bar, a Chinese-locale registration disclaimer. Rebuilt; grep-confirmed.
339. Corrected q reads "q 0.03 (fdr 22 bands)", not "q 0.03 (p corrected for testing 22 bands)" (PI, 2026-09-27; "fdr" standing shorthand): BM heat maps, CL tooltip; tests updated.
340. Server's sliding-window default true → false, as the page has sent for years (N-11); live pages unchanged (request byte-identical); omitting callers get the all-data fit; old train/test detector kept reachable.
341. Old time-domain branch's unused 1,000-shuffle band inference deleted with its sole inputs (N-12); fallback timeline and "claimed by more than one session" warning kept. Live: 51 fields removed, 0 added, 0 differing.
342. CI secret scan: store keys in three new RCS08 fixtures fingerprinted (gitleaks entropy false positive), rule not loosened.
343. Heat-map hover drops "(about N independent)" (PI, 2026-09-27; kept on the panel line): count and corrected q only, per the 2026-09-16 ruling ("X ratings, q = Y and nothing else").
344. Titration card took a one-visit plan for 2026-09-30 (PI: L and R C+1-2-, max L 2.5 / R 3 mA, sense L 0-3, R 0-3, 55 Hz) via a per-visit table that never touches the ceiling; RCS08's entry removed after, mechanism kept.
345. Menu said "Choosing stimulation settings" twice (redesign renamed "Customized Analysis / Analysis Builder" in group and page); page reverted to "Analysis builder".
346. Contact-aware SO, step A (PI, 2026-09-30 / 10-01): groups (left pulse width, right pulse width, Left contact) split Left ring 1 from 2; Left-0-mA stretches join every contact group (his ruling); reference = configuration in force; pooled-pulse-width fit keeps contacts apart; clinic stretches keyed from six sheet notations. RCS08: 60/160 us → 13 (L C+1-) / 8 (L C+2-); 55 Hz check counts only L C+2-: 1 of 6 pairs, not 2. Correction: Sarikhani 2022 searched contact (with amplitude); none of three searched contact, rate and amplitude together.
347. Step B (partial pooling across Left contacts) built, kept offline: RCS08 contact effect only with all pulse widths pooled (home: share 1.0, p 0.002, held-out error 0.902 vs A's 0.932, difference interval -0.09 to +0.04 points; clinic: share 0.59, p 0.003), confounded with pulse width; none within the one two-contact pairing (home 60/160 us, p 1.0). No held-out gain over A, so offline (module rule). Step D waits.
348. Step C, server only: ranks (Left contact, rate) blocks for the next visit at the pairing in force (PI: candidates = current-carrying contacts plus L C+1-2-; rank = predicted improvement + 2 SD). RCS08: 47 of 48 blocks lack a surface, tie at the prior bound (2.78 NRS points): no single block offered; the one fitted (L C+2-, 55 Hz, in force) ranks last (best 0.55 points at L 3.5 / R 3.0 mA). Off-page until he rules on ties.
349. Step C borrows across rates and pulse widths (PI, 2026-10-01): contacts with ≥8 own clinic stretches get one fit, read at the block's rate and pulse widths in force; blocks scored only where Left carries current. RCS08: 17 blocks borrowed (L 1+2-, L C+2-, L C+1-), all worse than the setting in force; 30 blocks of five contacts with <8 stretches (incl. L C+1-2-) tie at top. Percept history (2025-07-16 to 2025-12-03): L C+1-2- at 0 mA on all 227 rows.
350. SO ranks next blocks in two lists (PI, 2026-10-01): too-untested contacts (tied), then measured blocks with prediction sources. Sheets (30 local copies, synced 2026-09-17) show L C+1-2- with current: 0.5, 1.0 mA on 2025-10-30 (110 Hz, 100 us); home group D 1.0 mA (110 Hz, from 2025-10-30), 1.6 mA (145 Hz, from 2025-11-19); 1.6 mA at home 2026-02-03 (165 Hz, 140 us). One has a pain rating (one modelled stretch); Percept history shows none.
351. Visit sheets: every step kept (PI, 2026-10-01). Unrated steps take Notes-tab timed verbal ratings, then REDCap (survey filed while in force, VAS / 10); still unrated = EXPOSURE, never pain data; untimed = a plan (09_24_26 = the titration card's unfilled export). After a manual Drive sync (copy stopped 2026-09-17): 958 steps; 539 rated on the Stim tab, 30 from Notes, 6 from REDCap, 383 unrated. Rules: CLAUDE.md section 10, docs/clinic_sheets_parsing.yaml.
352. Plotly out of the main bundle (speed-up step 2, 2026-10-01, PI's go-ahead): four eagerly imported pages now load on demand, so login no longer downloads it. main.*.js 6,581,540→726,653 bytes (1,879→214 KB compressed); Plotly (3.5 MB) its own chunk (offline report checked, no console errors). 5 jest tests (3 watched RED); 1,026/1,026 across 119 suites.
353. One maths-library thread per BRAVO process (speed-up step 3, 2026-10-01): one per core (16 Mac, 64 JS2) contended (140, 268: small fits 10-15x slower). RCS08, one thread vs default: grid 43,685 numbers, 19 differ; CL 73,600, 3; SO two-stage 64,212, 1; all timing fields. Alternating default/one: 9.73/8.60/8.84/8.30 s, 27.04/25.89/26.91/26.74 s, 24.14/23.99/25.05/25.44 s. Environment setting wins. 3 tests (BRAVO/maths_threads.py, first import in settings.py).
354. Fewer redraws (speed-up step 6, C3-C5, 2026-10-01): BM composite pain series once per score choice; Biomarker Data Timeline redraws on slider change only in the high/low split view; SO 'Where have currents been tried' squares drawn on first opening, then kept. No number changes; 2 orientation tests open the section first. 5 new page tests (watched RED; commit 3f7a289f wrongly says 8); 1,031/1,031 across 121 files.
355. SO requests the two-stage plan with its answer (speed-up step 4, C2, 2026-10-01). RCS08: answer 10,541 values, 0 differ; plan 64,212, 1 (computing time). Cold: plan 106.4-106.8→73.5 s on JS2 (answer 32.3 s, unchanged); 35.4-37.5→25.9-27.9 s on the Mac (answer 0.4-0.7 s later); two alternating rounds each. B2 (profile 'sleeping') dropped: joblib awaiting leave-one-out workers. 2 page tests (1 watched RED); 1,033/1,033 across 122 files.
356. Batched band power = one-at-a-time on JS2 too (2026-10-02, PI: make them identical): x86 maths library differed in the last binary digit for 2,241 of 29,400 values (≤3.9e-16; 0 on the Mac); band sums now per segment: 0 of 29,400 differ; Mac path untouched.
357. CL simulates segments in worker processes, combined in order (2026-10-02). RCS08/JS2 warm, side by side: 73,600 values, 0 analysis values differ (3 timing fields); request 42.4→38.4 s, simulation 9.1→5.3 s (one round). Parallel SO group fits dropped: 52.6→66.6 s, 55.2 s sharing cores (4-10 groups; folds already parallel).
358. SO runs independent blocks in threads (2026-10-02): readiness beside two-stage, sheet fit beside each extra pain site. RCS08/JS2 warm, side by side: 64,212 values, 0 analysis values differ; 52.4→45.6 s (one round); Python's lock caps it. STIM_OPTIMIZER_CONCURRENT_BLOCKS=0 disables.
359. JS2 web workers keep unpacked recordings (2026-10-02): unpacking RCS08 cost 12.3 s per CL request, a deep copy 1.5 s; keyed by path and content hash; callers get deep copies. RCS08/JS2 warm, side by side: CL 38.8→29.1 s (73,600 values, 0 analysis values differ), two-stage 51.6→45.6 s (64,212, 0), grid 9.1→9.0 s (43,685, 0). 4.0 GB per worker: off unless BRAVO_RECORDING_CACHE_MB is set; JS2: 6000 MB per worker, 16 workers.
360. SO's 1,080 band checks (two regression fits each) in worker processes, whole cells in chunks, in order (2026-10-02). RCS08/JS2 warm, three side-by-side rounds: two-stage 45.2→38.2, 55.0→46.5, 45.9→38.1 s; 64,212 values, 0 differ. STIM_OPTIMIZER_SCREEN_JOBS=1 disables; <100 checks stay single-process.
361. CL threshold-rule fit skips padding after each stretch's last reading (2026-10-02): RCS08's 366 stretches × 1,499 steps hold 42,684 of 548,634 cells, each visited 900 times per fit. Row sums keep their order: all 900 parameter sets match to the last bit; fit 2.39→0.81 s (alternating rounds); warm CL request 38.7→36.5, 38.1→35.1 s (73,600 values, 0 differ).
362. Grid sweeps contact pairs in threads, each on its own cache, in order (2026-10-02). RCS08/JS2 warm, side by side: 9.4→7.8 s; 43,685 values, 19 differ, all timing. BIOMARKER_SWEEP_THREADS=1 disables.
363. Clinic-sheet epoch frame converts step times to California days once per frame (2026-10-02): `_rating_days` had run 2,432 times per frame, half a build run twice per SO request on RCS08. JS2: 304 epochs × 45 columns, 13,680 cells, 0 differ; build 7.1-8.9→3.0-3.9 s (three each, side by side, busy machine).
364. One worker-pool size for all BRAVO process pools (2026-10-02): cores minus one (63 JS2; 15 Mac, unchanged) or BRAVO_POOL_JOBS; joblib rebuilt a worker's pool on each size change (1.3-1.5 s on JS2 vs 0.02 s reuse; CL asked 64, SO 15). Size never changes answers; JS2 folds 35.2 s at 48 workers, 35.8 s at 15.
365. Fewer redraws, part 2 (2026-10-02; items C5, C6, C8; sub-agent, reviewed): CL Background fold's three-source and three simulation figures drawn on first opening ("Sign and print", "Export JSON" draw them first); "Which band?" grid and five SO cards redraw on input change only; BM and SO research checks load on first opening. Page-test redraw time: SO cards 336→35-39 ms, CL grid 70→30 ms; page text byte-identical (51,057, 46,831 characters). 16 new page tests. C7 not done (needs a test that two simultaneous R requests are safe). Endless CL redraw (`resultCache.getResult`, the PI's file) held for him; fixed by 366.
366. Result cache's "computed at" = time stored, not last read (2026-10-02; PI: "YES APPLY IT", lifting rule 7: "these are our files, edit as needed"). `resultCache.getResult` returning read time had made CL redraw endlessly (12 extra redraws in half a second in a page test, 0 after) and stamped the Recompute bar and printed CL record with read time. Fixed at the source, not by 365's page stamp. 3 new tests watched failing; 1,038 page tests passed.
367. The test sets consolidated (2026-10-02; the PI authorised it directly; sub-agent, reviewed). Both Python sets on JS2, side by side: 145 -> 66 s wall. Host 1,907 -> 1,893 passed, container 956 -> 946, 0 failed; page tests 1,033 -> 1,019 (14 duplicates). Speed: Stage 1 fits in tests that never read the calibration check pass `calibration_check=False` (a warning that changes no recommendation, 233 ruling 6; 77.6 -> 7.7 s per fit, verdicts identical); identical fits built once per module; the two threshold equality checks split into 5 and 3 pieces. 30 Python tests removed, each named against the test that covers it (full log). Untrue names split or fixed: `test_family_wise_correction_is_isolated_per_grid...` never ran the sweep (its true half kept; per-grid isolation now untested), `test_lag_corr_finds_a_planted_lag_one...`, `test_block_length_for_returns_one...`.
368. The design rule's per-step sum no longer calls itself (2026-10-02; the PI: "fix that problem where the design rule shouldn't call itself"). `_pairwise_sum` walks numpy's pairwise tree with an explicit stack; same numbers, same order. Equal bit for bit to np.sum and to the old recursive sum at 26 lengths (0-8,192, 6 draws each) and to the old sum at 8,193-65,536. Prepares the disk cache (369).
369. Each web worker starts warm (2026-10-02; the PI: keep the pool warm "by setting very reasonable limits"). `BRAVO/warmup.py`, run by `gunicorn.conf.py`'s `post_worker_init`: imports, R under its lock, every numba loop. All numba loops now use the disk cache (design rule since 368; controller loop and robustness replay; reverses the caution of 269/283). Every pool asks through `parallel.loky_backend()` so a started pool is the one requests reuse; `BRAVO_POOL_IDLE_SECONDS` keeps it. Jetstream2 budget: 16 web workers x pool 31, kept a day, recording cache 3,000 MB: ~127 GB idle, ~175 GB worst (runbook 3a). Mac: no pool at start (`BRAVO_WARMUP_POOL` unset).
370. The 3-second chunk table builds in worker processes when it must be rebuilt (2026-10-02; sub-agent, reviewed). `Biomarkers/routines/availability.py`: `_td_tile_values` (FFT work, in workers) and `_append_tile_rows` (rows, in the caller); neighbouring recordings go to the shared pool in groups of near-equal sample count. `BRAVO_TILE_JOBS=1` forces serial; under 2,000,000 samples for a pair it stays serial; a pool failure falls back to serial. RCS08 on JS2, cold, store writes blocked: 324,651 chunks, 6 pairs, 860 recordings; 33,888,141 fields, 0 differing old/new, serial/workers. 24.9 -> 9.4 s (4 alternating rounds 8.8-10.6 s vs 24.8-25.0 s). 5 new tests (3 watched failing).
371. Closed-Loop ROC and month-by-month checks: two R requests at once are safe; caching their R fits is not worth it (2026-10-02; sub-agent, reviewed; item C7). `test_r_fits_run_together_safely.py`: every R call holds `analytics._R_GLOBAL_LOCK` (11 inside, 0 outside); the control fails without the lock; 8 simultaneous fits equal the one-at-a-time answers, 0 fields differing. R is ~1.3 s of each request (26% of ROC and month-by-month at 4.6-5.2 s, 11% of device units, 13% of sign-off), below the 3 s bar; no cache built. Larger saving, held for the PI: each of the four requests rebuilds the matched samples (2.5-3.1 s, about half the ROC) and that object carries pain ratings (rule 5, decision 22).
372. The heat-map grid's per-pair statistics run in worker processes (2026-10-02; sub-agent, reviewed; item B7 part 2). `Biomarkers/bravo_service._band_time_sweep_channels` split into matching (threads, 362), statistics (shared pool, `_sweep_statistics`, `routines/sweep_workers.py`) and finishing; each pair is one task, results in pair order, each task builds its own generator from the request's seed. `BIOMARKER_SWEEP_PROCESSES=1` forces serial; a pool failure falls back and logs. RCS08 on JS2, warm, 4 alternating rounds: 7.4-7.7 -> 5.6-5.9 s; 43,685 fields, 19 differing, all computing-time fields (two runs of the old code differ in the same 19). 5 new tests. Limited by 6 pairs, matching (2.9 s) and 2.2 s outside the sweep.
373. Matched-samples memo for the four Closed-Loop requests: not built; decision 371's 2.5-3.1 s was measured with store writes blocked (2026-10-02; the PI said build it; sub-agent measured first). Warm on JS2 with a copy of the store, `_band_validation_setup` takes 1.7-2.5 s: pain ratings from REDCap 0.85-1.4 s and the recording key 0.61-0.66 s (both needed to build any safe key, decision 22), loading the saved matrix 0.013 s, building the matched samples 0.05 s, recordings 0.02 s, stimulation series 0.03 s. A memo skips ~0.1 s of a 4.6-5.2 s request. Left, if wanted: the recording key (0.65 s, 0.32 s of it JSON decoding of 3,942 rows' metadata; a narrower query gives the same key string, a refactor with a key-identical proof) and the REDCap fetch (~1 s; needs a cheap did-anything-change check).
374. Jetstream2 has its own login-cookie names (2026-10-02; the PI): a browser keeps one cookie per host name and ignores the port, so the local BRAVO at `http://localhost` and Jetstream2 through an SSH tunnel at `http://localhost:8080` shared one `sessionid`, and each answered 403 ("credentials were not provided", user `AnonymousUser`) to the other's login (the pain-score dropdown, the saved research checks, the Biomarkers reload). `BRAVO/settings.py`: `BRAVO_COOKIE_SUFFIX` is added to `SESSION_COOKIE_NAME` and `CSRF_COOKIE_NAME`; unset, they are Django's own, so the local BRAVO is unchanged; Jetstream2's override sets `_js2`. 3 new tests (failed first). Log in once more on each.
375. Each web worker loads the Biomarkers data before its first click (2026-10-02; the PI: clicking heat-map cells was slow "even though it's supposed to be warm", slower on Jetstream2). Measured: the first cell request in a web worker loads the REDCap ratings and decodes the 860 recordings (6.0-6.4 s on the Mac, 12.0 s on JS2); later cell requests in that worker take 0.03-0.13 s, also after 70 idle seconds. With 16 workers on JS2 most early clicks were a first one. `BRAVO/warmup.py` gains a `participants` step (after the pool): the page's own grid request then one cell request for each of the three participants with recordings; `BRAVO_WARMUP_PARTICIPANTS` sets the count (3; 0 off). Fresh process on the Mac after the step: first cell clicks 0.11 / 0.03 / 0.03 s (was ~6 s); the warm-up takes 10.6 s longer; the shared pool is the same after the requests. 6 new tests (5 failed first).
376. Jetstream2 worker pool 31 -> 16 (2026-10-02): after the participants warm-up (375) the machine used 188 of 245 GB (each web worker 8 GB: 4.9 GB of data caches, 2.7 GB of recording cache; 528 pool processes). Closed-Loop warm at pool 31 vs 16, alternating, JS2: 22.6 / 23.6 s vs 22.5 / 23.4 s; the two-stage request had shown no change at 48 vs 15 (358). Pool 16 gave 162 GB used (83 GB available), warm-up 30 s per worker. The recording cache (3,000 MB per worker, 44 GB in all) does not speed cell clicks (first clicks equal with it off: 0.18 / 0.03 / 0.03 s vs 0.08 / 0.03 / 0.03 s); kept for Closed-Loop (359). Runbook 3a updated.
377. CI on GitHub fixed (2026-10-02; the PI: "fix why it keeps failing"). Every run since 2026-10-01 failed for three reasons, none a product fault: (1) `openpyxl` was not installed by the workflow, so 6 clinic-sheet tests errored (since decision 351); (2) the cookie-name tests (374) imported the full Django settings, which need the server's environment; the rule moved to `BRAVO/cookie_names.py`, tested alone; (3) two page-test files (365's `ClosedLoopPage.speed` and `StimOptimizer.speed`) took 3-6 s on a CI runner against jest's 5 s limit: `Client/src/setupTests.js` sets 30 s. Host suite in CI before: 3 failed, 1861 passed, 6 errors.
378. Biomarkers page, the PI's list of 2026-10-02 (sub-agent, reviewed; not seen in a browser): one Recompute button (the heat-map one removed); changing the pain score no longer marks the page stale (each prefetched grid is filed under its own score; the page-level check ignores the score; the match window, direction, reuse, clinic-sheet scores and the high/low split still mark it, the note names which); the cell detail (scatter, violins, hover) is cached at module level, 200 cells, keyed by participant, score, settings and cell, so a click repeats with 0 requests also after switching score or leaving the page (the old per-component ref was emptied on every grid change and on leaving; not from the 2026-10-02 speed-ups); "how well band power tells high pain from low" -> "AUC"; scatter line "r, p, n" and violin line "AUC, p, n high, n low" on one line each, the 22-bands allowance sentence removed, "not allowing for the 22 bands tested" -> "uncorrected"; one shared plot margin so the scatter and violin centre under their heat maps; the notes block terse, 14/22 px (was 12/18); the coverage sentence on three stacked lines (the second ±10 min is the fixed 10-minute count, not the slider); the saved research checks are Plotly figures with hover (numbers from the saved result), scientific titles ("Out-of-sample stimulation-current prediction" and eight more), light alternating row shading in the two row figures, and every x axis ends on a labelled tick (the stepped-current figure had none past 50 Hz; the "100" is inferred, not seen). 1,070 page tests pass.
379. Stim Optimizer and Closed-Loop wording, minimalist (2026-10-02; the PI: scientists, not lay language; "make it minimalist, like Apple"). Stim Optimizer section titles: "Candidate vs. current setting" (was "Is any setting proven better than today's?"), "Sampled currents, predicted pain" ("Where have currents been tried, and what does the fit predict?"), "Closed-loop readiness" ("Can closed loop start?"), "Closed loop at frozen rate and pulse width" (the long two-stage card title), "Next-visit requirements" ("What must the next visit deliver?"); the tests that pinned the old titles pin the new ones. Closed-Loop page: the inherited-matching line (body size, grey, one terse line: "Matching from Biomarkers, 2026-09-26 21:05 UTC: ±30 min, nearest, ≤3 per report, 2 min apart, no reuse, clinic sheets out, tertile split, NRS."), the grid's settings line under "Which band?" ("Grid: NRS · ±10 min · nearest · tertile 33/67%", build time in the hover; the signed record keeps the long form), the warning ("Per-setting consistency not computed yet."), the column heads ("AUC", "Corrected, 22 bands") and the legend line (body size). Top panel: the context line under the title (`paper/PageHead`, all pages), the decision card's eyebrow and the chosen-band record line are body size (14/22 px, was caption 12/18). Not done: the headings of the cards below the grid, not seen live. 238 Closed-Loop and 207 Stim Optimizer page tests pass.
380. Closed-Loop card headings and small text (2026-10-02; the PI: do the card headings too). Headings: "Band selection" (was "Which band?"), "Device rule check" ("Does the device allow it?"), "Evidence consistency" ("Does the evidence hang together?"), "Stability across stimulation states", "Verdict sensitivity" ("What would change this answer?"), page title "Closed-loop feasibility and entry values"; the three evidence links "Device control of signal", "Signal tracks pain", "Therapeutic effect". Every 12 px caption paragraph in the Closed-Loop panels is 14 px (table column heads and the figures keep their size). Also the PI's ruling on the Biomarkers page: the high/low split stays a recompute trigger (it redefines high and low); the pain score does not (all six grids are in the saved store, ~2 s each on both servers, and prefetched). 1,070 page tests pass.

---

## Part 4 — Lineage, in brief

- PRs #3-#8: engine, figures, audit, validation. #9 (`39dfb2f`, 2026-06-29): 61 commits into `v3.1.0`; #10-#12 followed. From 2026-09-15: work lands on the default branch.
- `90eb109`: calibrated closed-loop band power. `958cc89`: matcher vectorised 21.4x, 0 differences. `688a185`: invented constant withdrawn. `6c3c9f2`: brain-side labels corrected by amendment.
- `b700717`, `7ab2d1b`: pushed messages wrongly say the container path is not a live mount. Full lineage: the full log.
