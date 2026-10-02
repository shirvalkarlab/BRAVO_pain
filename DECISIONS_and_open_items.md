# Decisions and open items — the digest

**Compacted 2026-09-19 at the PI's direction; shortened again 2026-09-26 ("not every decision needs to
be held, and many can be merged").** Every decision number resolves here, on its own one-line row or
inside a merged row that names its range. The full rows, with every proof, field count, timing and
verbatim quote, are in `docs/decision_log_full_2026-09-19.md`; a decision number resolves there. PI
quotes are paraphrased here with his permission (2026-09-19). Struck rows stay struck: the mistake is
the lesson. New decisions are appended to Part 3 here (one or two lines) AND as a full row in the full log.

---

## Part 1 — Standing rules, by subject (the log's current state)

**Signal, units, calibration**
- **Every time comes from the tablet clock, never the device (INS) clock** (328): one home `MedtronicPercept/TabletClock.py`; device ticks only measure gaps inside a block.
- Pain-report timestamps are California wall-clock; device times are UTC; convert before matching (2). The chronic detector joins on the California calendar day (142). The session matcher caps nothing per report; reports claimed by more than one session are counted and warned about (221).
- Windows with >10% zero-filled samples are dropped (4), in every routine (57-59).
- 60 Hz notch off by default (13). Only the two 256-point FFT modes convert (14). The voltage trace converts by the transform route at **345.59** (211; recipe and de-identified blocks in `routines/calibration.py`, 208); the bridge constant, 72.16, is composed, never "measured" (33, house rules). The frozen per-participant log-log model (11) is deleted (218; `DEVICE_percept_rc.md` §10 keeps its numbers). 8.8 Hz R 0-3+ counts only from 2026-03-01 (16); no impedance term (17).
- **Log power enters no calculation, anywhere** (PI, 2026-09-19; 202, 204-206, 212, 218).
- **Time is modelled nowhere**: drift is a current effect in a patient >3 years into disease; no age penalty, no time input (193-196).
- **Every view and product starts at the device's implant date** (RCS08: 2025-07-16 18:06 UTC; `DecodeCommon/data_start.py`): measurements before it are dropped where they are read, the setting in force at implant is kept and moved to it; the rows stay in the database (260). The cut reaches the export, the raw recordings list, the participant-context service, the custom-analysis pipeline (263), the saved tiles and PSDs (289) and the timeline's chronic files (313).
- One vocabulary: **TD** for band power from the time-domain recording in 3 s pieces (montage recordings included, labelled "Montage"), **PSD** for the device's own 30 s snapshot; never "spectrum" bare (115, 298, 299, house rules).

**Statistics and verdicts**
- Discrimination intervals are signed, never folded; the lower bound may fall below 0.5 (7, 8, 19). Validation is forward-chaining out-of-sample (12).
- Gates have three states; a gate that goes green on absence of evidence is unsafe (9). A not-assessed condition still blocks but is counted separately in the wording (176).
- "Established" means the point sign; intervals and p stay as caveats; verdict flagged provisional when any interval spans zero (147). D19 passes on point signs (134); D26 capture checks read the pooled slope and WARN (139).
- **Every chance test that moves the pain ratings is the exact rotation test**: the pain scores slid along in time by every possible step once, the observed order counted once, smallest p 1/n; above 5,000 values 1,000 distinct steps (`stats_utils.rotations`, one home; 314, 315). The chunk shuffle is deleted. Family-wise correction on the grid: Benjamini-Hochberg over 22 centres (63). The cell interval is a block bootstrap, its block the pain series' lag-1 decorrelation length (183).
- Every model fitted offline holds its test rows out as blocks of TIME with the neighbouring rows dropped from training, the gap from the label's own decorrelation timescale (240); held-out scores are taken **within each block**, never pooled across blocks (310); every candidate is reported plainly AND with the stimulation current taken out; an out-of-sample score is never folded; none of this refuses anything (240). The current is taken out as a named SHAPE with its flexibility stated: a 3-knot spline in the two guards, a straight line in `partial_corr` and the adjusted grid; fitted on training rows only (241).
- **A reading with the current taken out is descriptive**: it never re-selects a band or moves a verdict (233 answer 2; 234, 242, 243, 293). The current-adjusted heat-map grid sits behind a switch, plain by default (234).
- E1 (current-to-power) is the pooled titration slope, model B: one intercept per run, ramped side's current, single-side runs, other side held at ANY constant (126, 197, 198); both legs of a ladder count, and a streaming restart under 20 s with the current held does not split a run (213). Never pooled across visits at the per-run level (40); curvature tested pooled across visits (errors allowing for repeated measurements within a visit) before any switching value on a peaked band, and only on one side of the peak (55, 56, 124).
- **The one-band rule**: a sensing contact and rate is usable when ONE band falls with current AND rises with pain on the stored Biomarkers grid; no majority rules (199). "Rises with pain" means positive with the block-bootstrap interval wholly above zero ("supported", 210); the grid's stricter "established" is shown beside it. On RCS08 today 0 of 50 contact-and-rate combinations are usable (217).
- **The device's sensing-pair rule**: the pair must be the two contacts flanking the lead's stimulating contact (stimulate on 1, sense 0-2; on 2, sense 1-3; on 1 and 2, sense 0-3; on 0 or 3 nothing). One home, `DecodeCommon/sensing_rule.py` (305); applied on the Stim optimizer's readiness table (217) and as blocking device rule D52 on the Closed-loop page (247). On RCS08 the allowed pairs are L 1-3+ and R 0-3+.
- **Harmonics**: the folded multiples of the stimulation rate come from one home (`analytics.harmonic_landings_hz`, 277); a band on one is flagged and analysed either way, a warning, never a refusal (220, 287), in the PI's wording: it "carries a folded multiple of the stimulation rate", never "measures the stimulator". At 55 Hz every centre from 22.5 to 29.5 Hz carries one (277).
- Honest current: a milliamp number is recommended only when three per-speed checks pass (not flat, beats today beyond scatter, ≥6 pairs each ≥5 ratings on ≥2 California days spanning ≥1 mA) (158, 184). Rate ≥55 Hz unless a stated reason (138). Left and right are modelled together (157). Pulse-width pairings are fitted separately by default; a pooled fit sits behind the current-map card's toggle, for the clinic stream too (222, 255). A clinic setting counts only the ratings that carry the score being fitted (258c). The Stim optimizer's calibration check is a warning (238, 233 answer 6); a current whose pain map moves between blocks of time carries a dagger, read as the whole group's readings moving, not the setting (253, 275, 294).
- ~~Reliable change index~~: deleted (231); too few pairs, too much scatter.
- Post-move margin: 0 s by measurement; the 20 s switch stays OFF by the PI's ruling: use as much data as we can (144, 178-179, 191, 196, 217).
- **Safety ceiling: PI-stated, 4.5 mA each side** (145, 160), one home `StimOptimizer/safety_ceiling.py`. **No page proposes, recommends, schedules, simulates or exports a current above it**: the Closed-loop limits are capped with the cap stated (306); the Stim optimizer's held ladder side, safe sets, queues and second-stage windows are bounded (308); a setting in force above it is shown, never offered (312). The module's 5.0 mA hard limit is not the safe ceiling. Side-effect score 2 is its own rung, cost 2.0 (165); moderate/severe steps never seed "tolerated" (164); the amplitude-severity statistic is recomputed each request (166).
- Thresholds are placed from the record: median averaged reading ± the design rule's minimum; the tablet's capture pair shown beside (180). Timing: averaging 3 s, onset 30 s (max enterable), blanking 30 s, transitions 30 s, startup 15 s (150, 169); ranges, the 8-30 Hz adaptive band range included, have one home, `DecodeCommon/device_ranges.py` (168, 285).
- Ground truth per row: device band power passing the 99.5th-percentile ceiling table > calibrated trace > composed (tagged) > never uncalibrated; both values and fold ratio where both exist (33, 47, 52).

**The store**
- One store, `BRAVO/modules/CacheStore/`; a second implementation is a test failure (30). Key decides whether to write (26); key from database rows alone (24, 25). The saved 3 s tiles are read or written only for the one input set every page uses; any other request builds in memory (289).
- **No pain rating in any recording-derived key or payload** (23): the Closed-loop inputs entry holds the settings stream and the design matrix is built per request (273); it is keyed on the recording set, the tile key, both calibration constants and a rule version (215, 289).
- Every derived write carries `writer=` and flattened `provenance=`; a consumer whose own output is in the chain is refused, and the refusal raises (31, 39). A refused entry is replaced, not skipped (41).
- Recordings cached without expiry; pain reports fetched fresh on every build; the held table serves drill-downs only until the next build (22, 78). The Biomarkers top timeline is an acquisition timeline, a raw kind with nothing from a pain report in it (216).
- Parquet+zstd tables, npz arrays, pickle otherwise; CSV/JSON excluded because the therapy timestamp is timezone-aware (29). Redis: 512 MB, allkeys-lru, locks/freshness/small values only, protocol 2 (27, 28).
- One entry per participant per kind by default; `KEEP_NEWEST_BY_KIND` names the kinds that keep more (sweep kinds 12; the stability answer 12, one per grid, 248; simulation, design rule and robustness 6, one per candidate, 309; two Stim optimizer responses); the daily-default heat-map grids are kept by a keep group outside the twelve (318). Six writes reporting success and one file on disk is the failure this prevents (107).
- A stored heat-map grid or stability answer is served to another page only under the rule in force (293, 317) and only for its own grid (248, 256).
- A test that touches the store clears or restores ONLY while its own override is in force, and never reaches a launcher that writes to the production root; three times a test has reached that root (96, 116, 129).
- Memos are keyed on the participant's current recording set, not the participant (130); work repeated within one request is held for that request only (267, 278).
- Saved control analyses are not the store: one file per run under `BRAVOStorage/control_analyses/`, every run kept, run offline only; a page never starts one (264).

**Pages**
- Names: "Biomarkers exploration", "Stim optimizer", "Closed-loop deployment" (325). Style by the minimalist specification (`artifacts/design_2026-09-26_minimalist_redesign/`, 320): one typeface, five sizes, text greys at 4.5:1 or darker, the heat maps' hover text the one 11 px exception (325); **red only for device refusals and the safe ceiling**, with its glyph; statistical blockers in ink with ✕ (322); no decision numbers in page text (303, 321); each page opens on its answer.
- Closed-loop figures draw once and restyle by trace index; rebuilding on interaction reintroduces the flash (5, hard). Plotly `doubleClick:false` and guarded purge on the heat maps (91). Figures that had the toolbar keep it; the heat maps have none (88, 324).
- The Biomarkers module does not deal in what stimulation does to a biomarker (108). The heat maps are the headline; nine lengths, 1 s to 60 s (170); the Closed-loop "Choose a band" card reads the SAME stored grid under the Biomarkers page's settings tag, the clinic-sheet switch included, and the stability answer filed for that grid (131, 248).
- The Closed-loop page is one decision card plus separate evidence cards (302; supersedes 258(a)). A report or summary computed for another band, pain score or clinic-sheet setting than the one chosen is withheld from every card and named, with Recompute offered (302, 307). The pain-score dropdown (NRS default) drives every band-to-pain reading (E2, E3, the stability card); E2 reads each piece's own settings period's ratings (290, 292). Clinic-sheet ratings enter the deployment summary only by the red-outlined button, off by default (258b).
- The chosen closed-loop band is held on the server, append-only, naming who chose it; the browser keeps a mirror and says when it holds the only copy (249). A band picked on the grid carries its grid's pain score, split and window to the deployment summary (254).
- A page judges a band on its own side (141). Every card's text is pinned by a fixture render test asserting what a clinician must read and the retired words' absence (174).
- Stim contact notation is the clinic sheet's own, `L C+2-`; sensing pairs keep superscripts (181).

**Process**
- Commit identity: Prasad Shirvalkar, `prasad.shirvalkar@ucsf.edu`, inline `-c` (49). Default branch `PS_closedloop_deployment`; `v3.1.0` is a label (177). No worktrees: the container mounts only the main checkout (102, 177).
- Written record: superseded documents go to `docs/archive/<date>/` by `git mv`, never deleted; no suite count in any document (34). Plan kept with planning-with-files, inject-smart, committed (36); autonomous mode with attestation allowed per plan, gated mode never (223). CI runs the page tests (257) and numba (271).
- Only code changes are open items; clinic notes live separately (open items, 2026-09-10).
- Every check ships with its live proof: field count and difference count, never a tolerance; alternating timings; the first live run of step 8 wrote nothing while every test passed (41).

---

## Part 2 — Open items

**Waiting on the PI**
- Clinic record: the setting in force (L 3.0 mA 100 us, R 2.5 mA 150 us) dates from 2026-09-02 19:15 UTC, not 09-03 as older rows say (328). [2026-09-26, decision 329: the records naming 09-03 carry dated notes and every saved control analysis and the chronic level-shift report were re-run; what moved is in 329.] [2026-09-27: the product name is answered, decision 338; the server-written wording package (WP8) is still open.]
- The N-items in `artifacts/pending_items_from_handoffs_2026-09-25.md`, ruled on 2026-09-27. Closed, no code needed (his call): N-01, N-02, N-03, N-07, N-08, N-13, N-14, N-16, N-17, N-18. N-10 (a July 2025 clinic step above the then-current safety limit) closed on his account: he attributes it to side effects that showed up days later, not a records error. N-06 (programming and testing closed loop after titration) is not a pending build item at all — nothing is coded; it is waiting on a usable sensing pair to exist, which is a state of the data, not of the software. N-11 (the sliding-window request default) and N-12 (the unused shuffle detector) are built — decisions 340 and 341. N-04, N-05 and N-20 were already answered by 280/285, 315 and 301. Still open:
  - **N-09.** Two separate records exist of what stimulation rate was used: the clinic's paper testing sheets (filled by hand during visits, one-second precision, 820 steps across 29 visits) and the device's own automatically-saved settings history. The device's own history shows only 7 different rates were ever used. The clinic sheets show 10, including four — 25, 85, 100 and 180 Hz — that never appear anywhere in the device's history. One of those four (100 Hz) is clearly written in the original spreadsheet for two specific test groups in July 2025, so it is not a data-entry mistake. There is no way to tell, from the sheets or the device record alone, whether those four rates were actually delivered to the patient and the device simply failed to save a record of it (the device only saves a new record at certain moments, not continuously), or whether they were planned and written down but never actually given. Nothing in either record settles it — it would need someone who was in the room for those visits to say which happened.
- RCSchronicpain (another repository): checked 2026-09-27 — the working tree is clean and pushed; the uncommitted work is a stash, `stash@{0}` "Claude Code BRAVO session edits 2026-09-25", 14 files / 959 lines (a MATLAB behavioral-outcomes refactor and new statistics/test files, not just "two plots recoloured" as it was summarised) on branch `refactor_stages123`. The PI said to delete it; the permission system refused (irreversible local destruction) — he needs to run `git stash drop stash@{0}` himself in that repository, after confirming the size above is really disposable. A separate, unrelated stash (`stash@{1}`, "On main: !!GitHub_Desktop<main>") was left untouched. The "3 token-shaped values" are `credentials/define_env_redcapAPI_tokens.m`, already committed and pushed by the PI himself (`717bb6d8`, "update credentials") — not a new finding, and not touched.
- Left for the PI by 322: the timeline gutter's Arial, the faint PLANNING ONLY watermark, the badge component's uppercase.
- How the Closed-loop page's 21 "can't be programmed yet" reasons are sorted into four buckets — the PI is reviewing this himself (2026-09-27: "I'll check it out and let you know").
- [2026-10-02: resolved by 366, fixed in the cache itself.] Closed-Loop page redrew without end once its simulation loads, and always shows "Something it depends on has changed": `resultCache.getResult` (his file) reports each read's time as the computed time, and the simulation's label includes it (365). [2026-10-02]
- [2026-09-27: resolved — decisions 339 and 343 shortened the hover's third line in the two places it had grown ("fdr" wording, dropping the independent-ratings addendum). If it still runs long, that would need a further specific instruction, since the remaining wording is what the hover's own 2026-09-16 ruling asked for.]
- [2026-09-27: resolved — the PI ran the build himself, which caught one string the initial sweep missed (a registration-page disclaimer); rebuilt again and confirmed by grep. The frontend bundle is current through decision 339.]

**Code, not yet built** (from the 2026-09-25 handoff scan)
- P-11: the voltage trace's device units on the timeline, to be checked against 216. [2026-09-27: P-10 closed — the joining repair keeps the first block's tablet time, `MedtronicPercept/tests/test_no_tick_times.py`, built with 328.]
- P-18: the timeline's detail panel; draft in `artifacts/spec_2026-09-25_P18_timeline_detail_panel.md`.

**Waiting on data or a visit**
- **Next visits** (protocol `artifacts/protocol_2026-09-25_rate_swap_and_down_first_ladder.md`, every question answered, §11): visits up to 3 hours door to door; Visit 1 includes the rate swap (the second cycle decided in the chair) and a second rater; Visit 2 the stimulation-off block with the full 90-minute wait; the down-first ladder answers the carry-over question (272). One tablet check at the first home session: the chronic log carries on across a change of group.
- The titration readings (237) reach the card only once the visit's own data exist.

**Caveats on the record, not fixable**
- [2026-09-27: the PI considers both resolved, no further action.] The short-tile-copy measurement gap (289: two 2026-09 windows read an incomplete slice of a recording; the current window was re-measured, the two older ones cannot be re-run but their comparisons stand), and the R statistics environment (288: installed in the Dockerfiles, no image built to test it).
- Not watched on screen: 292's dropdown effects, 294's daggers, 324's q wording (superseded in part by 339's shortened wording, itself confirmed only by reading the built files, not a browser).

**Rewritten, not open**: 10. The 110 Hz "heat map" does not exist in the platform; the pre-registration (`PREREG_RCS08_110Hz.json`) is unrun and its counts do not reproduce (109). Re-measure before reopening.

**Notes for the clinic, not items**: 55 Hz has one left-only visit day on the left electrode; the device never computes its own FFT while current is stepped, so that source is empty for every ladder; the clinic implication of 217 (L 0-3+ needs L C+1-2-) stands.

**Closed**: the titration session (item 30, run 2026-09-16; 213); the rulings of 2026-09-21 (218-227); item 15 (258, 284, 291); every "found, not changed" note in 249-318 (fixed by 254, 255, 270, 309, 314, 315, 317, 318, 323; P-16 declined, 316). Resolved by consolidation, do not re-open: disk reads are 4.8% of the page; matching is 0.2-1.7% of Recompute. Closed items 1-9, 11-14, 16-29, 31 are one line each in the full log's Part 2.

---

## Part 3 — Every decision, one line (number, date where it matters)

Refs are commits or PRs; `→N` means superseded by N; a range such as `282-288.` is one merged row.

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
~~22~~. →78. Recordings cached without expiry stands; reports never cached, except the read-only drill-downs.
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
63. Family-wise correction: Benjamini-Hochberg over 22 centres, no autocorrelation adjustment (its p-values from the exact rotation test since 315).
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
199. One-band rule; usable cells 6 → 4, all on harmonics (measured on the short tile copy, 289; the count since set by 210 and 217).
200. Review leftovers C3, C4, C6, C7, T2, T3 built.
201. C6 off-label line removed.
202. No log power on the E1 path; remaining sites listed for the PI.
203. Context compaction: this digest, the full log in `docs/`, shorter CLAUDE.md, house rules and store architecture; handoffs, worker reports, completed plans and generic rules deleted.
204. No log power on the pooled full-spectrum path or in the pain correlation; 10 of 132 stability verdicts moved, the chosen band unchanged (measured on the short tile copy, 289).
205. The outlier rule (5 MAD) and the heat map's logistic cross-check on raw power; the log-scale option refused.
206. The aperiodic (1/f) fit deleted with its `fooof` transform; reached by no page; the device cannot threshold a peak's prominence.
207. Calibration exploration (no code): the frozen model's curvature is between-band gain pooled into one slope; the constant was refitted instead.
208. The June calibration anchor reproduced with the lab's code and extended to 2026-09-03 (n 133, k 345.59); block gate and 5-MAD ratio rule adopted; recipe and de-identified blocks in the repository.
~~209~~. →211. The transform constant as the midpoint of two eras, 349.10.
210. The one-band rule's pain leg loosened to "supported" (positive, block-bootstrap interval wholly above zero); "established" shown beside it.
211. The transform constant is 345.59 everywhere, the recipe's one median over every block (209 superseded); composed bridge 72.16; verdicts unchanged.
212. The Biomarkers calibration panel draws the calibration in effect (the transform constant over every paired block, the June reference, the bridge ratio per centre and pair, constants read from the server) instead of the frozen June model.
213. The titration run finder joins two recordings split by a tablet restart under 20 s with the current held, and measures a setting reached by a rise or a fall, tagged by leg (the PI: pool both legs); the 2026-09-16 left ladder reads 8 settled currents in one run; verdicts unchanged.
214. The Closed-Loop "LSB & power" cross-check reads the voltage trace in microvolts with the transform band power, against the constant in effect; the independent pairing gives 1/352.7 µV² per LSB, 0.98 times it.
215. The Closed-Loop inputs entry is keyed on the recording set, both calibration constants and a rule version; it had served a frame built under the old constant.
216. The Biomarkers top timeline is an acquisition timeline: it reads no pain report and is stored as the raw kind `acquisition_timeline`; the rating-centred sample index has its own endpoint (`/queryPsdScanIndex`).
217. The readiness table applies the device's sensing-pair rule; on RCS08 (left C+2-, right C+1-2-) the allowed pairs are L 1-3+ and R 0-3+, neither with a band rising with pain: usable combinations 11 -> 0 of 50. The 20 s margin switch stays OFF.
218-222. The PI's rulings of 2026-09-21, built: the frozen June log-log model deleted (218); four chronic-detector routines with no caller deleted (219); the harmonic rule a warning, never a refusal (220); the session matcher keeps no cap per report and warns on sharing (221); pooling across pulse widths behind the current-map card's toggle, default separate (222).
223. Amends 36: a plan's `.mode` may carry `inject-smart autonomous`, attested at start and after every edit; `gate` stays off.
224-227. The 2026-09-21 cleanup: the Binarization card laid out as option C with a timing histogram (224); the per-report band-power reader deleted, both copies (225); the Compute response no longer carries a second copy of the timeline (226); the audit leftovers built: the left refit panel deleted, the calibration recipe reports an interval and spread on its median ratio, the band around a modelled threshold is the participant's own scatter, stale-constant comments reworded (227).
228. The heat-map square's scatter and violin use the same ratings the grid correlated, clinic-sheet ratings included when the switch is on (they had read REDCap only and drawn a rising line beside a negative r); sheet points hollow.
229. Exploratory search on L 1-3+ over 252 settings of window, direction, cap, reuse and sheets: no row positive with q < 0.05; with the sheets on 10-22 of 22 bands fall with pain per setting; the near-hit 24.5 Hz, 60 s, 120-min pre-report square reads r 0.32, p 0.054, not resolved (corrected by 315). A lead, not a band to program.
230. An exploratory ladder for L C+1-2- on the titration card, where the best sensing pair (L 0-3+) needs other stimulating contacts: a 15-step up/down ladder, three 5-minute holds off / on / off, a first-exposure stop rule, 33 sheet rows (rate set by 236; watch list by 277).
231. The reliable-change index deleted with its card and tests (12 pairs, too much scatter); supersedes 75, 104, 111, 112.
232. Research batch of 2026-09-22: four reports, each debated by a three-reviewer panel (`artifacts/research_2026-09-22_*`, synthesis). Common finding: on the left lead the bands that rise with pain rest on the current in force. Eight questions for the PI.
233. The PI's eight answers: (1) the ladder's reading is the ramp with the current term, the holds beside it; (2) "supported" need not survive taking the current out; the adjusted value is descriptive only; (3) the exploratory ladder runs at 55 Hz, the rate in force; (4) the back site's parallel fit is wired; (5) the next session runs 55 Hz at 100/150 us, merged with the 60/160 us record; (6) the calibration check is a warning; (7) the current-adjusted grid is behind a switch; (8) the chosen band is recorded on the server.
234. The heat map's correlation with the current in force on the pair's own side taken out, behind `AdjustForStimCurrent` (off by default); the plain value still selects and decides; the switch is in the store key, not the cross-page settings tag; the current is read from `therapy_settings` (`routines/stim_current.py`).
235. Three interim caveats on the pages: the triangle's current-confound sentence for a left 21.5-27.5 Hz band (replaced by 242's adjusted reading), the current map's pooled association stated as not holding out of sample, and the heat maps' RCS08 lines rewritten.
236. The exploratory ladder runs at the rate in force, 55 Hz, the cell's own rate shown beside it; supersedes 230's rate (its "24.5 Hz is clear" corrected by 277).
237. Two readings of one titration session (`titration_readings.py`): the ramp with the current taken out is the reading, the holds beside it; a band that is 98% the current gets no adjusted number; one visit is a lead to repeat, never an established result. Not yet on the card.
238. The clinic-stream fit follows the site it is asked for (it was hard-coded to the left leg); the back site gets its own parallel fit; the pre-registered calibration check runs per surface as a warning.
239. `coverage_gap` turns the coverage refusal into what the next visit must deliver (pairs to repeat or add, under the ceiling); a ladder stepping one side can never pass without joint corners (its ruling-5 count corrected by 255, 258(c)).
240. Two guards for every offline model (held-out blocks of time with neighbours dropped; a current-confound check) and the check before any decoder (`confound_diagnostic.py`); on no page. No set of bands beats its own shuffled level on any pair (corrected by 310, 315).
241. The current is taken out as a named shape (`stats_utils.CovariateShape`: line, squared term, 3-knot spline, three kernels, one level per setting); the guards default to the spline, `partial_corr` keeps the line. On L 1-3+ a turn-over of pain with current is suggestive, not established; no shape changes the verdict.
242. The Closed-Loop page says what its answer rests on: one verdict on the sign-off sheet, the stability answer ranked in "What would change this" and printed inside the coherence note, one caveats list (`adapter.caveats_for_report`), and E2 read again with the current in force taken out, descriptive. NRS today: left 0.564 plainly, 0.553 adjusted (corrected by 290).
243. The Stim Optimizer page ordered as a decision is made, with the sensing rule in the open, "still positive with the current taken out" per band (read from a stored adjusted grid only), the "proven better" exposure and the rate-pin assumption stated (layout since amended by 303, 320, 325).
244. The Closed-Loop jump links follow the page's own card order, pinned by a test that reads the page file.
245. Amends 243: the current map's legend open on load; the search's stopping rule shown per side (not assessable on RCS08).
246. Housekeeping: three unread field groups left the Closed-Loop response; each heat-map square carries its effective number of independent ratings and each grid its shuffle reconciliation; the whole-search count line (corrected by 315); the time-of-day and weekend check (moved by 264; R 1-3+'s cycle withdrawn by 265). Pain and L 1-3+ band power both run higher at weekends; taking the weekend out moves the correlation by at most 0.019.
247. Device rule D52, the sensing-pair rule, blocking on the Closed-Loop page (L 0-2+ had been called permitted while the lead stimulates on contact 2); caveat numbers at four decimals; the heat maps drawn at their box's width.
248. The stability answer keeps one entry per grid (12), names its grid, and the "Choose a band" card reads only its own grid's answer; the grid settings list gained the clinic-sheet switch (131 had been broken since 186).
249. The chosen closed-loop band recorded on the server, append-only, naming who chose it (`chosen_band.py`, `/api/queryClosedLoopChosenBand`); the page says when a browser holds the only copy; the sign-off sheet names the band and its grid.
250. The parameter card's notes carry one heading counting its own checks; the two long-failing Closed-Loop page tests repaired.
251. The coverage gap printed on the current-map card under "Enough combinations tried?".
252. One-off check of whether left chronic band power steps when left settings change (`stepB3_chronic_level_shift.py`): 4 of 21 changes readable; the three on L 1-3+ at 23.44 Hz all show power falling as current rises, one interval excluding zero. Nothing reads it.
253. Why the Stim Optimizer's maps fail their calibration check (`calibration_diagnosis`, a warning): the left-leg 55 Hz 60/160 us map moves between blocks of time; the others are thin data. No boundary-avoiding kernel built (read with 275).
254. A band chosen on the grid carries its grid's pain score, split and window to the deployment summary (it had used NRS and a tertile split whatever the grid).
255. The clinic stream's fits pooled over pulse widths reach the page with the toggle; ruling 5's merged answer (`next_session_coverage`) heads the clinic section. Corrects 239: 3 of 6 qualifying pairs, not 5 (2 of 6 since 258(c)).
256. The stability run's stopped-early rule protects its own grid's answer, not the newest of any grid.
257. CI runs the page tests (jest).
258. The PI's rulings of 2026-09-24: (a) sign-off card last (superseded by 302); (b) a red-outlined button adds clinic-sheet ratings to the deployment summary, off by default, through one merge helper; (c) a clinic setting counts only ratings carrying the score being fitted (the back fit had dropped back-only settings); (d) legibility (superseded by 320).
259. The recompute bar enlarged (rule 7 lifted once for it).
260. Every view and product starts at the implant date (RCS08 2025-07-16 18:06 UTC; `DecodeCommon/data_start.py`); earlier measurements dropped where read, the setting in force kept and moved to it; rows stay in the database.
261. The coverage check reads a stored table's rating days as days (arrays had been counted as sums, or not at all).
262. The PI's two analyses: in the both-off stretch 2025-07-16 to 08-22 the left 21.5-25.5 Hz family rises with VAS pain (a lead to confirm); a current with memory never beats the current in force; corrects 240's matching window to 60 minutes (its readings corrected by 310).
263. The implant-date cut reaches the export, the raw recordings list, the participant-context service and the custom-analysis pipeline.
264-265. Control analyses saved offline and shown on the Biomarkers and Stim Optimizer pages (`modules/ControlAnalyses/`, one card, every run kept); 265 corrects 246: from implant on R 1-3+ has no daily cycle; L 0-2+ keeps one.
266-271. Speed-ups of 2026-09-25, every value unchanged: tiles built in batches, the FFT still once per piece (266); work repeated inside one request done once (267); the E2 adjusted interval's fits on one thread (268); the design rule's filter compiled with numba, no on-disk cache (269); CI installs numba (271). Also 270: the participant-context service works for RCS08 again.
272. The carry-over test, saved: on the record every fall came after its rise, so carry-over and drift cannot be told apart; a down-first ladder would answer it.
273-274. No pain rating saved under a label that ignores it: the Closed-Loop inputs hold the settings stream, the design matrix built per request (273); numba's type-checking log silenced below warnings (274).
275. Regression-to-the-mean check: the swing at 1.6/1.2 mA is the whole group's over those weeks, not that setting's; 253's reading restated.
276. Decision 262's p with the current taken out replaced by that reading's own shuffle (corrected by 310, 315: nothing beats its null).
277. One harmonic check for both modules (`analytics.harmonic_landings_hz`), in the PI's advisory wording; at 55 Hz every centre 22.5-29.5 Hz carries a folded multiple, 24.5 Hz included; 9 of 22 centres clear.
278-279. Speed-ups, exact: the recording-set identity worked out once per request (278); the grid's medians in one computation (279).
280-281. Page fixes: the ROC cut-point in standardized band power units, the burn-in stated, stale record lines corrected (280); a clinic-sheet cell with a written correction keeps the delivered value (281, P-13).
282-288. The 2026-09-25 batch: rating persistence and stepped-current-every-band control analyses (282); three more numba compilations and one-column time-block labels (283); the stability panel says when it was assembled (284); handoff items P-05 to P-09 and P-15, and the three-week burn-in kept because without it the mixed model fails to converge (285); P-14 resolved by calling the one difference routine (286); bands on a harmonic flagged, never struck (287); the Dockerfiles install R 4.3.3 with lme4, lmerTest and emmeans, no image built (288).
289. The saved 3 s tiles are read or written only for the one input set every page uses; anything else builds in memory; the key carries the implant date. A short copy had been served in three windows (Part 2).
290. E2 had read the ratings of the settings period before each piece's own since `8fbe11ba`; fixed. The only E2 the page ever called established was the wrong period's: L 1-3+ Left Leg VAS now 0.641, not established.
291-292. The stability card: each state's odds ratio with its interval, one rating in one state and one week (291); intervals clustered on the pain report, and a pain-score dropdown driving every band-to-pain reading on the Closed-Loop page, NRS by default (292).
293. The deployment summary prints its area with the current taken out beside the plain one, descriptive; the "Choose a band" card reads only stability answers under the rule in force.
294. A dagger beside every recommended current whose pain map moves between blocks of time, worded after 275; pooled maps checked too, the across-rates table not.
295-296. Speed-ups, exact: the calibration check's held-out folds refitted in parallel (295); the settings history kept per session file (`therapy_settings_by_file`), so a new file costs one parse (296).
297. The research band detector, two versions, saved as control analyses (`band_detector.py`); with REDCap ratings only no reading on either pair clears q < 0.05 (p corrected by 314). A lead, not a finding.
298-299. One vocabulary on the pages: TD and PSD, no "spectrum"; the heat-map square's split by source printed (298); montage pieces labelled "Montage" (299).
300-301. The beta-peak classifiers re-saved under the pinned scikit-learn; old PSD files counted, nothing to delete (300); the visit protocol revised, the June mock-ups removed (301, commit `4590af6a`).
302-304. The three pages cut to one decision card and fewer words (the PI, 2026-09-26): Closed-Loop one decision card plus separate evidence cards (supersedes 258(a)), the device-units panel prints no value to program, a report for any band but the chosen one withheld and named (302); Stim Optimizer status line, allowed pairs in the open (303); Biomarkers pain-score selector first, one status line (304).
305. The device's sensing-pair rule has one home, `DecodeCommon/sensing_rule.py`; the grid response carries it outside its key.
306. The Closed-Loop page recommends no current above the per-side safe ceiling (the upper limit had inherited 4.8 mA); capped with the measured currents kept and the cap stated; a cap, not a refusal.
307. One pain score and one clinic-sheet setting across the Closed-Loop page (a report under another is withheld and named); the sensing-pair tabs named for screen readers.
308. The Stim Optimizer proposes, recommends, schedules and exports no current above a side's ceiling: the held ladder side held at it, safe sets bounded, queues filtered, second-stage windows read it; the 5.0 mA module limit is not the safe ceiling.
309. The robustness answer keeps six entries, one per candidate (107's failure again); the timeline prints pain scores by their display label.
310. The check before any decoder scores held-out predictions within each block of time (pooled, the current alone had been reading which block a rating sat in); the rotation null keeps the observed order. Nothing beats its own null on any pair.
311. P-12's band-power cells re-measured on the full tiles; every conclusion stands (R 0-3+ in 323).
312. Seven small items: a setting in force above the ceiling shown, never offered; the timeline's pain label fitted to its gutter; the control-analyses and stored-results lines folded; the ROC panel prints 293's adjusted area; the stability grid's kind and rule in one home (`sweep_settings.py`); a stale class name renamed; P-16 left to the PI (316).
313. The acquisition timeline dates a spanning chronic file from the implant date; refusals name the quantity, not the column.
314. The research band detector uses the exact rotation p and draws each reading against its own shuffled level; the Closed-Loop page prints no column name. With REDCap ratings alone nothing on either pair clears q < 0.05.
315. Every chance test that moves the pain ratings is the exact rotation test (`stats_utils.rotations`); the chunk shuffle deleted (a band unrelated to pain had read p ≤ 0.05 in 10.7% of records). Bands clearing the 22-band correction: daily 32 -> 10, the Biomarkers page's settings 34 -> 17; the one-band rule still 0 of 50.
316. P-16 (rename the Stim Optimizer package) not done: the PI, "no rename".
317. Other pages serve a stored heat-map grid only when built under the grid rule in force; rule, kind and key in `sweep_settings.py`.
318. The daily-default heat-map grids stay on disk through a keep group, one per pain score, outside the twelve.
319. The sign-flip bootstrap projects each vector directly, so R 0-3+ fits in memory; every p, estimate and standard error unchanged.
320-325. The minimalist, plain-language redesign and its follow-ups (specification in `artifacts/design_2026-09-26_minimalist_redesign/`): one typeface, five sizes, greys at 4.5:1 or darker, colour for data (320); nine mismatches with the specification fixed (321); twelve taste proposals, red only for device refusals and the ceiling, statistical blockers in ink with ✕ (322); 318 and 319 proved live and P-12 measured on R 0-3+ (323); the figure toolbar, the corrected-q label and the device-rule counts restored (324); the old page names back ("Biomarkers exploration", "Stim optimizer", "Closed-loop deployment"), matching settings behind one "Adjust matching parameters" button, the two heat maps aligned, long Stim optimizer sections fold, blank clinic-sheet cells left blank (325).
326. The page-against-server review (2026-09-26; 40 findings, 39 kept after a skeptic's check), fixed on all three pages: the Stim optimizer's current map was drawn mirrored across its diagonal since 3779bfb8 (2026-09-14), now flipped (the server was right); its "proven better" strip reads the frozen setting's own verdict and joint pulse-width stratum; its saved answer is keyed on the clinic-sheet steps; the Closed-loop headline follows the server's verdict and blockers; read-back ticks clear on any change; each device refusal names who can clear it (`resolved_by`, for the PI to look over); Biomarkers heat maps say when they are older than the controls and follow the clinic-sheet switch together; p or q in [0.045, 0.05) prints "< 0.05"; safety lines stay in the open under the new folds; the clinic sheet is named by a study code only.
327. Records cleaned (the PI, 2026-09-26): this digest cut from 213 KB to 54 KB (every number still resolves; detail in the full log); all ten finished plans and the superseded design papers moved to `docs/archive/2026-09-26/` with an INDEX; SPEC.md is the one current design specification, amended through 326; no live plan remains.
328. Every time is on the tablet clock (the PI, 2026-09-26: "INS device time should not be used anywhere for any reason"). Measured on RCS08: `FirstPacketDateTime`, the chronic log, patient events, the event log and group history are on the DEVICE clock, which ran ahead of the tablet by up to 2.1 h by 2026-09 (about 25 s a day since 2025-12); only `SessionDate`/`SessionEndDate` are the tablet clock. Rule, one home (`MedtronicPercept/TabletClock.py`, applied on read, raw exports never rewritten): an entry's tablet time is its own device seconds count plus the anchor of the export it was first carried in, anchor = SessionEndDate minus the Final DeviceDateTimeOffsetInSeconds (spread 121 s over the record; 27 exports without an end time use SessionDate minus Initial); device ticks only measure a gap or the spacing of power readings inside one block. The stored record was corrected in place with a 1.3 GB backup and restore script, and the copies the device clock had created were collapsed to one row per entry (patient events 21,109 -> 1,226 kept; therapy changes, recharge and settings snapshots likewise); 396 old-block entries left out. Verdicts and effect signs unchanged; today's setting has been in force since 2026-09-02 19:15 UTC, not 09-03.
329. The analyses and records that read the old device clock, fixed (the PI, 2026-09-26: "Fix those analyses re Sep 3"): every record dating today's setting 2026-09-03 corrected to 2026-09-02 19:15 UTC; a typed stretch date removed from a card; the chronic level-shift report fixed (readings resolved against every record's schedule) and, with every saved control analysis, re-run. Moved: L 0-2+ has no daily cycle (no pair has one); R 0-3+ at 30 s is the one plain reading above its shuffled level before any decoder (p 0.035, q 0.42); ratings at 60 s fell (L 1-3+ 187 -> 104); the regression-to-the-mean outside comparison 33.8% -> 6.6%; a 6 h current memory edges past the current in force on NRS. Unchanged: the 0 mA L 1-3+ rise with VAS, the level-shift directions, nothing in the band detector clearing q < 0.05.
330. Every time field in the 583 exports checked (184 paths): no tablet-clock field was missed (only SessionDate and SessionEndDate, true UTC with correct daylight saving), and every device field that is read is converted; converted times are within seconds almost always, at most about 5 min. REDCap, clinic-sheet and converted device times now agree (median 0.3 and 0.0 min; 393 of 778 reports within 2 min of her own remote press, against 20 on the device clock). The 45-60 s rows' earlier counts rested on re-stamped copies of one press. Recommended and adopted: a 15-minute window either side (`artifacts/analysis_2026-09-26_json_time_fields_and_matching.md`).
331. Matching defaults (the PI, 2026-09-26, on 330): one home, `sweep_settings.py` (the Biomarkers page's `matchingDefaults.js` pinned to it by a page test); the window 15 min either side for the page (a saved 5 or 60 moved once) and the daily defaults (was 60); the direction "nearest" (was "pro_first": under it a report kept two TD pieces under 30 s apart, 3 reports on RCS08, 0 under "nearest", which pairs 380 reports against 377); cap 3, gap 2 min, TD 30 s, no reuse, sheets off kept (no measured basis). The Closed-Loop page inherits the Biomarkers page's last run (its grid, the stability card, the summary but its direction) and prints it in one line. Live RCS08: every verdict and 0 of 50 usable unchanged; the daily NRS grid 9 -> 7 bands past the 22-band correction (all falling, L 1-3+); the L 1-3+ 24.5 Hz summary "VALIDATED (stim-dependent)" -> "candidate" (its mixed model had not converged, OR 2.44, 2.43-2.44); the Stim optimizer's right-side exploratory ladder (R 0-2+) is no longer proposed.
332. A grid's stability answer is computed on the grid's own pain score (found by 331): the daily precompute asks with the score as `SweepMetric` only, the per-point setup read `LabelMetric` and fell back to NRS, so all six daily grids carried the NRS answers (100 cannot tell, 32 behaves differently). Now each uses its own (rule v7): NRS unchanged; VAS 87 / 45, Left Leg VAS 120 / 12, back VAS 103 / 29, McGill 100 / 29 (3 not computable), composite 122 / 10 (cannot tell / behaves differently).
333. E1's fallback to the whole-record estimate is now a caveat, not silent (an open item from 326). The current-to-power edge prefers the pooled titration-session table (decision 124); when that table cannot be read, the report falls back to the setting-epoch slope over the whole record, which can carry the opposite sign (measured, L 1-3+ 24.5 Hz: pooled -7.31 per mA against the fallback +1.63). The `source` field already named which was used; the caveats list now says so in the open when the fallback fires. No value or verdict changes; live today both sides read the pooled table, so 0 caveats added, 0 fields differing.
334. The all-band scan follows the clinic-sheet switch, the same as the heat maps (the PI, 2026-09-27: "if clinic readings were activated by clicking the buttons they should be used ... same as the heat maps inherit"). Confirmed the heat maps merge sheet ratings via the same `_merge_clinic_sheet_ratings` the grid, its drill-down and the deployment summary already call; the scan (`run_for_participant`) took a tidy DataFrame that routine cannot write to, so a new sibling adds the sheet ratings as DataFrame rows instead, through the same `sheet_ratings_for_metric` lookup. Existing report rows are never touched (a pure concatenation, per row); off, nothing changes.
335. Every fold/collapsible toggle drawn as one prominent, filled arrow chip, not six copies of a plain 14 px character (the PI, 2026-09-27: "make any clickable drop-down area much more prominent, perhaps with a really big toggle arrow"). One home, `views/Reports/paper/FoldArrow.js`: a rounded, accent-tinted chip with a bold accent-coloured arrow, used by `paper/Fold.js`, `paper/Section.js`, `ClosedLoopSim/Fold.js`, `ClosedLoopSim/ThreeSourceResponsePanel.js`, `Biomarkers/MatchWindowBand.js`'s "Adjust matching parameters" button and `StimOptimizer/typeScale.js`'s `SizedFold`; a source test fails if any of them draws its own arrow again. Visual only; no value, verdict or safety text moves.
336. The tertile split's stored key no longer moves when the percentile sliders were left dragged (the PI, 2026-09-27, resolving the "key naming inconsistency" open item). `sweep_settings.label_strategy_params` now returns the fixed 33.3333/66.6667 cuts whenever the strategy is "tertile", instead of whatever the sliders were last left at; the computed split itself never changed, only the duplicate-filing this caused.
337. A caution line, and two shortened on-plot boxes, on the Biomarkers "split into high and low pain" preview (the PI, 2026-09-27, building the never-finished "pain-day balance" item and the ballooning-box complaint). `binarizationModel.classBalanceFlag` warns when the two groups are too few (Peduzzi et al. 1996, floor 10 in the smaller group) or too lopsided (3:1, a general severity threshold); the "Low"/"High"/"Left out" boxes on the histogram now carry only their essential count, the source breakdown staying on hover.
338. The platform's on-screen name is "UF/UCSF BRAVO" (the PI, 2026-09-27, on the name left open by 320). Changed in the browser tab title, the per-page title suffix, the sidebar brand, the top navigation bar and (caught after the first bundle check) a Chinese-locale registration disclaimer. Bundle rebuilt and confirmed by grep.
339. The corrected-q wording is shorter everywhere it appears: "q 0.03 (fdr 22 bands)", not "q 0.03 (p corrected for testing 22 bands)" (the PI, 2026-09-27; "fdr" is now the standing shorthand for this correction). Fixed in both places that build it (the Biomarkers heat maps and the Closed-Loop tooltip); every pinning test updated; bundle rebuilt.
340. The server's sliding-window request default now matches what the page has actually sent for years (false), instead of true (open item N-11). Nothing on any live page changes (proven: the page's own request is byte-identical before/after); a caller that omits the field now gets the cheap all-data fit instead of the old train/test detector, which stays reachable on purpose, not deleted.
341. The old time-domain branch's unused 1,000-shuffle band inference is deleted, and everything that fed only it (open item N-12, "see if ok to delete old one including shuffles"). Checked first: the fallback timeline and the on-screen "claimed by more than one session" warning both still work (they read a different part of the same branch, kept); nothing reads the shuffle test's own output, on any page, ever. Proven live: 51 fields removed, 0 added, 0 of the rest differing.
342. CI's Secret scan job fixed: three RCS08 fixture files added since the last pass each carried a cache-store key gitleaks' entropy rule flagged as a fake API key. Same false-positive shape as before, verified the same way, fingerprinted rather than loosened.
343. The heat-map hover's rating count dropped its "(about N independent)" addendum (the PI, 2026-09-27: "trim the heat-map hover text now, use your judgment"). That detail stays on the pinned panel line, which already carries it; the hover now prints only the plain count and the corrected q, matching the hover's own original 2026-09-16 ruling ("X ratings, q = Y and nothing else").
344. The titration card took a one-visit plan for 2026-09-30 (the PI: L and R C+1-2-, max L 2.5 / R 3 mA, sense L 0-3 and R 0-3, 55 Hz) through a per-visit table that changes the card and its Google-sheet export only, never the safety ceiling; RCS08's entry was removed after the visit, the mechanism kept.
345. The menu named "Choosing stimulation settings" twice: the redesign's name for "Customized Analysis / Analysis Builder" landed on both the group and the platform's own Analysis Builder page. The page is "Analysis builder" again; the group keeps the name.
346. Step A of the contact-aware Stim Optimizer (the PI, 2026-09-30 / 10-01): the model never read the contacts, so Left ring 1 and ring 2 were one surface. Groups are now (left pulse width, right pulse width, Left contact); Left-0-mA stretches join every contact group (his ruling); the reference is the configuration in force; the pulse-width-pooled fit keeps contacts apart; clinic stretches key on Left contact, read from six sheet notations. Live RCS08: 60/160 us split 13 (L C+1-) / 8 (L C+2-); the 55 Hz next-visit check counts only L C+2- and now finds 1 of 6 current pairs, not 2. Corrects my first summary of the literature: Sarikhani 2022 did search contact (with amplitude); none of the three searched contact, rate and amplitude together.
347. Step B (partial pooling across Left contacts) is built and judged offline, not wired in: a shared pain surface plus a per-contact deviation whose size the data estimate. On RCS08 a contact effect shows only when all pulse widths are fitted together (home: share 1.0, p 0.002, held-out error 0.902 vs 0.932 for step A's separate surfaces, interval of the difference -0.09 to +0.04 points; clinic: share 0.59, p 0.003), and contact and pulse width changed together, so it may be a pulse-width effect; within the one pairing with two Left contacts (home 60/160 us) there is none (p 1.0). It does not predict held-out days better than step A, so by the module's rule it stays offline. Step D waits.
348. Step C, server side only: the response ranks every (Left contact, rate) block for the next clinic visit at the pairing in force, most promising first (the PI: candidates = contacts that carried current plus L C+1-2-; rank by predicted improvement + 2 SD). On RCS08 47 of 48 blocks have no surface and tie at the prior bound (2.78 NRS points), so the response says the tie and offers no single next block; the one fitted block (L C+2-, 55 Hz, the setting in force) ranks last (best 0.55 points at L 3.5 / R 3.0 mA). Not on the page until he decides how a tie is broken.
349. Step C borrows across rates and pulse widths (the PI, 2026-10-01: "extend it to borrow across pulse widths"): a contact with at least 8 clinic stretches of its own gets one fit over all its rates and pulse widths, read at the block's rate and the pulse widths in force, and a contact block is scored only where Left carries current. On RCS08: 17 blocks borrowed (L 1+2-, L C+2-, L C+1-), every one predicted worse than the setting in force; the 30 blocks of the five contacts with fewer than 8 stretches (L C+1-2- among them) still tie at the top, so no single block is offered. Left C+1-2- in the Percept record (2025-07-16 to 2025-12-03) was programmed at 0 mA on every one of its 227 rows.
350. The Stim optimizer page shows the next-block ranking as two lists (the PI, 2026-10-01): contacts not yet tested enough to predict (tied at the top), then the measured blocks ranked with where each prediction comes from. The clinic and home-visit sheets (30 local copies, synced 2026-09-17) DO record Left C+1-2- with current: 0.5 and 1.0 mA on 2025-10-30 (110 Hz, 100 us), home program group D at 1.0 mA (110 Hz, from 2025-10-30) then 1.6 mA (145 Hz, from 2025-11-19), and 1.6 mA at the 2026-02-03 at-home test (165 Hz, 140 us); only one of those steps carries a pain rating, which is why the model sees one Left C+1-2- stretch. The Percept settings history shows none of them with current.
351. Visit sheets: every step is kept, rated or not (the PI, 2026-10-01). Unrated steps are filled first from the visit's own Notes tab (timed verbal ratings), then from REDCap (the survey filed while the step was in force, VAS / 10); what stays unrated counts as EXPOSURE to its contact, never as pain data, and an unrated step with no time at all is a plan, not exposure (the 09_24_26 sheet is the titration card's exported ladder, never filled in). After a manual Drive sync (the local copy had stopped at 2026-09-17): 958 steps, 539 rated on the Stim tab, 30 from Notes, 6 from REDCap, 383 unrated. Rules recorded in CLAUDE.md section 10 and docs/clinic_sheets_parsing.yaml.
352. Plotly out of the main page file (step 2 of the 2026-10-01 speed-up list, the PI's go-ahead). The route table imported the experimental pages eagerly (unused there) and App.js imported the offline report and the two survey pages eagerly; the experimental pages and the offline report import Plotly, so every page, the login page included, downloaded it first. Now all four load on demand. main.*.js 6,581,540 -> 726,653 bytes (1,879 -> 214 KB compressed); Plotly (3.5 MB) in its own chunk, fetched when a charting page opens (seen in the browser on the offline report, no console errors). 5 jest tests (3 watched RED); 1,026 of 1,026 across 119 suites.
353. One maths-library thread by default in every BRAVO process (step 3 of the 2026-10-01 speed-up list). Each web worker had started as many maths threads as the machine has cores (16 on the Mac, 64 on the Jetstream2 BRAVO); several workers then fight over the cores (decisions 140 and 268 measured small fits 10-15x slower that way). Proof on RCS08, one thread against the default: heat-map grid 43,685 numbers compared, 19 differ, all timing; Closed-Loop report 73,600 compared, 3 differ, timing; Stim Optimizer two-stage 64,212 compared, 1 differs, timing. Single requests alternating default/one/default/one: 9.73/8.60/8.84/8.30 s, 27.04/25.89/26.91/26.74 s, 24.14/23.99/25.05/25.44 s. A thread count already set in the environment still wins. 3 tests (BRAVO/maths_threads.py, imported first by settings.py).
354. Fewer page redraws (step 6, items C3-C5, of the 2026-10-01 speed-up list). Biomarkers page: the pain series for the composite score is built once per score choice instead of on every render, and the Biomarker Data Timeline no longer redraws on a slider change unless the high/low split view is showing (the only view that reads the matching result). Stim Optimizer page: the squares of 'Where have currents been tried' are drawn the first time that closed section is opened, not on page load, and stay drawn after it is closed again. No number on any page changes; 2 orientation tests now open the section first, as a reader does. 5 new page tests (watched RED; commit 3f7a289f says 8, wrongly); 1,031 of 1,031 across 121 files.
355. The Stim Optimizer page asks for the two-stage plan at the same time as its own answer, not after it (step 4, item C2, of the 2026-10-01 speed-up list). The server stores the two answers separately and works them out in separate web workers, so waiting only added the plan's whole computing time. Same numbers either way (RCS08: the page's answer 10,541 values, 0 differ; the plan's 64,212, 1 differs, its own computing time). With nothing saved, the plan is ready at 73.5 s instead of 106.4-106.8 s on the Jetstream2 BRAVO (page answer unchanged, 32.3 s) and at 25.9-27.9 s instead of 35.4-37.5 s on the Mac (page answer 0.4-0.7 s later, the two share its cores); two alternating rounds each. Item B2 (the 'sleeping' in the Stim Optimizer profile) was dropped: it is joblib waiting for its leave-one-out workers. 2 page tests (1 watched RED); 1,033 of 1,033 across 122 files.
356. Batched band power equals the one-at-a-time calculation on the Jetstream2 BRAVO too (2026-10-02, the PI: make them identical). Its x86 chip's maths library split the band-sum product over all segments differently from a one-segment product: 2,241 of 29,400 values differed in the last binary digit (largest 3.9e-16 of the value; 0 on the Mac). The band sums now run one segment at a time, the single call's own size: 0 of 29,400 differ on Jetstream2; the Mac's numbers cannot change (its single call is untouched).
357. The Closed-Loop report simulates its record's segments in worker processes (2026-10-02). Each segment depends on itself alone; results are combined in segment order, so every sum is added as before. RCS08 on Jetstream2, warm, run side by side: 73,600 values, 0 analysis values differ (3 computing-time fields); the request 42.4 -> 38.4 s, its simulation step 9.1 -> 5.3 s (one round). Fitting the Stim Optimizer's groups in parallel was tried and dropped: 52.6 -> 66.6 s, and 55.2 s with the cores shared, because each call has only 4-10 groups and their held-out checks already run in parallel.
358. The Stim Optimizer request runs its independent blocks side by side in threads (2026-10-02): the readiness check beside the two-stage block, and the clinic-sheet fit beside each further pain site. RCS08 on Jetstream2, warm, run side by side: 64,212 values, 0 analysis values differ (only the two-stage block's own computing time); 52.4 -> 45.6 s (one round). Threads share the request's inputs instead of copying them; they still share Python's lock, which caps the gain. STIM_OPTIMIZER_CONCURRENT_BLOCKS=0 turns it off.
359. Unpacked recordings are kept in each Jetstream2 web worker between requests (2026-10-02). Unpacking RCS08's recordings cost 12.3 s of every Closed-Loop request; a deep copy of the kept content costs 1.5 s. Each file is kept under its path and content hash (a changed file is read and verified again) and every caller gets a deep copy, so no request can change another's data. RCS08 on Jetstream2, warm, side by side: Closed-Loop 38.8 -> 29.1 s (73,600 values, 0 analysis values differ), two-stage 51.6 -> 45.6 s (64,212, 0), heat-map grid 9.1 -> 9.0 s (43,685, 0). The decoded recordings are 4.0 GB per worker, so it is off unless BRAVO_RECORDING_CACHE_MB sets a budget; only the Jetstream2 BRAVO sets one (6000 MB per worker, 16 workers).
360. The Stim Optimizer's 1,080 band checks run in worker processes (2026-10-02). Each check (two regression fits: does this band's power move with current?) depends on its own cell; whole cells go out in chunks and come back in order. RCS08 on Jetstream2, warm, three side-by-side rounds: two-stage request 45.2 -> 38.2, 55.0 -> 46.5, 45.9 -> 38.1 s; 64,212 values, 0 analysis values differ. STIM_OPTIMIZER_SCREEN_JOBS=1 turns it off; screens under 100 checks stay in one process.
361. The Closed-Loop threshold-rule fit skips the blank padding after each stretch's last reading (2026-10-02): RCS08's table is 366 stretches x 1,499 steps with 42,684 of 548,634 cells holding a reading, and the compiled loop did every cell 900 times per fit. Each step's sum still runs over the whole row in the same order, so all 900 parameter sets give the same likelihoods to the last bit; the fit takes 0.81 s instead of 2.39 s (alternating rounds), the warm Closed-Loop request 38.7 -> 36.5 and 38.1 -> 35.1 s (73,600 values, 0 analysis values differ).
362. The heat-map grid sweeps its contact pairs side by side in threads (2026-10-02): each pair reads only its own cache; answers return in pair order. RCS08 on Jetstream2, warm, side by side: 9.4 -> 7.8 s; 43,685 values, the 19 that differ are all computing-time fields. BIOMARKER_SWEEP_THREADS=1 turns it off.
363. The clinic-sheet epoch frame converts each step's time to a California day once per frame, not per setting and pain site (2026-10-02): `_rating_days` ran 2,432 times per frame on RCS08, half of a build that runs twice per Stim Optimizer request. RCS08 on Jetstream2: 304 epochs x 45 columns, 13,680 cells, 0 differ; a build 7.1-8.9 s -> 3.0-3.9 s (three each, side by side on a busy machine).
364. One worker-pool size for every BRAVO process pool (2026-10-02): the core count less one (63 on the Jetstream2 BRAVO, 15 on the Mac, unchanged there), or BRAVO_POOL_JOBS. joblib keeps one pool per web worker and rebuilds it whenever a call asks for a different size: 1.3-1.5 s each time on Jetstream2, against 0.02 s to reuse it; the Closed-Loop simulation asked for 64 and the Stim Optimizer for 15. The pool's size never changes an answer (each use's tests compare against one process); on Jetstream2 the held-out folds took 35.2 s at 48 workers and 35.8 s at 15.
365. Fewer page redraws, part 2 (2026-10-02; speed-up items C5, C6, C8; sub-agent, reviewed). Closed-Loop: the Background fold's three-source figure and three simulation figures are drawn when the fold first opens, not on page load; "Sign and print" and "Export JSON" ask the page to draw them first, so the record still carries them. The "Which band?" grid and five Stim Optimizer cards redraw only when their inputs change. The research checks at the foot of the Biomarkers and Stim Optimizer pages are requested when their fold first opens. Redraw time during one page load in page tests (the sub-agent's alternating rounds): Stim Optimizer cards 336 -> 35-39 ms, Closed-Loop grid 70 -> 30 ms; each page's full text byte-identical (51,057 and 46,831 characters). 16 new page tests. C7 not done: it needs a test that two simultaneous R requests are safe. **Held for the PI:** once its simulation loads, the Closed-Loop page redraws without end and always shows "Something it depends on has changed", because the shared result cache reports each read's time as the computed time (`resultCache.getResult`, the PI's file); a page-side fix and its test are ready, not applied.
366. The result cache's "computed at" is the time an answer was stored, not its last read (2026-10-02; the PI: "YES APPLY IT", and lifted rule 7, "these are our files, edit as needed"). `resultCache.getResult` had returned the read time, so the Closed-Loop page redrew without end once its simulation loaded (12 extra redraws in half a second in a page test, 0 after) and always showed "Something it depends on has changed"; the Recompute bar's "Computed …" line and the printed Closed-Loop record showed read time. Fixed at the source; the page-side stamp the sub-agent proposed (365) is not used. 3 new tests watched failing; page tests 1,038 passed.
367. The test sets consolidated (2026-10-02; the PI authorised it directly; sub-agent, reviewed). Both Python sets on JS2, side by side: 145 -> 66 s wall. Host 1,907 -> 1,893 passed, container 956 -> 946, 0 failed; page tests 1,033 -> 1,019 (14 duplicates). Speed: Stage 1 fits in tests that never read the calibration check pass `calibration_check=False` (a warning that changes no recommendation, 233 ruling 6; 77.6 -> 7.7 s per fit, verdicts identical); identical fits built once per module; the two threshold equality checks split into 5 and 3 pieces. 30 Python tests removed, each named against the test that covers it (full log). Untrue names split or fixed: `test_family_wise_correction_is_isolated_per_grid...` never ran the sweep (its true half kept; per-grid isolation now untested), `test_lag_corr_finds_a_planted_lag_one...`, `test_block_length_for_returns_one...`.

---

## Part 4 — Lineage, in brief

PRs #3-#8 built the engine, figures, audit and validation; #9 (`39dfb2f`, 2026-06-29) merged 61 commits into `v3.1.0`; #10-#12 followed; since 2026-09-15 work lands on the default branch directly. Landmarks: `90eb109` calibrated closed-loop band power; `958cc89` matcher vectorised 21.4x with 0 differences; `688a185` withdrew an invented constant; `6c3c9f2` corrected brain-side labels by amendment. Two pushed messages (`b700717`, `7ab2d1b`) wrongly say the container path is not a live mount. Full lineage: the full log.
