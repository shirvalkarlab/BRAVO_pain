# Progress: Closed-Loop module minimally functional

## Session 1 — 2026-09-10

### Phase 1 — the audit and the alignment (complete, pushed)
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Module works end to end for a real candidate | A real report | `available: true`, 26 keys, verdict `blocked`, both write-backs written, 21.6 s | Pass |
| `cache_status` on every return path | All three | Was 1 of 3; now 3 of 3, verified live (3 keys → 4) | Pass |
| A failure reaches the log | Any log call | Was **0** logger calls in the whole module; now 9 in `adapter.py` plus the service and the view | Pass |
| Adversarial review of those fixes | Agreement | NEEDS CHANGE on one — the explanation was under `reason`, the page renders `note` | Fixed |
| Container suite | 606 | **606 passed, 0 failed** | Pass |
| Host suite | 1000 + known 1 | **1008 passed**, 42 skipped, 1 failed (known) | Pass |

Commits `deb1987c` and `91de6282`, both pushed. Decisions 100 and 101.

### Phase 2 — the consistency check (in progress)
| Step | State |
|------|-------|
| Read the four-function chain and its inputs | Done |
| Both inputs already in scope in `report_for_participant` | Confirmed by reading |
| Wired as `implied_control_direction`, `gates_nothing: True` | Done, not yet proven live |
| Live proof on RCS08 | **Next** |

### Next session starts here
Prove the consistency check live on RCS08 for a real candidate, then Phase 3 (`reliable_change`).
Nothing is deleted without reading the decision log first — decisions 74 and 75 record several of
these functions as deliberately built ahead of their wiring.

### The PI's four decisions, 2026-09-10
| Question | Chosen | Consequence |
|---|---|---|
| How the consistency check gets pooled data | **Store a pooled table** off the request path | Page keeps ~8 s; the check answers from every visit instead of "not assessed" |
| Open item 26, device-spectrum cells | **Mark the affected cells** on the grid | Needs a per-cell flag through the sweep response, not just drawer text |
| Open item 10, the device-rules screen | **Cross the grid with a candidate setting** | The screen becomes live-computed per setting; supersedes the ADR's pre-compute argument |
| Open item 7, which pain scores to sweep | **Every score, precomputed** | ~6x compute moved off the request path, like the stability grid's daily pass |

### Phase 2 live proof, and the defect it found
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| The check is reachable and returns a payload | A real answer | Yes, on 4 points across 2 contacts | Pass |
| It gates nothing | `gates_nothing: true`, verdict unmoved | True; verdict `blocked`/`licensed` false on every point, unchanged | Pass |
| The answer does not depend on cache state | Same answer either way | **FAILED** — cold: 13 points / 4 visits; warm: 6 points / 1 visit, same band, same day | Fixed |

### Phase 2b — the stored pooled table
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Cold and warm give the SAME answer | Identical | **13 points / 4 visits on all three runs** (cold, warm, warm again) | Pass |
| The table is a real result | Rows with answers | 294 rows, 3 contacts, 98 centres, **194 assessed** | Pass |
| A truncated build is refused | Not written, not even derived | Refused with a reason; the derivation is never called | Pass |
| The page does not regress | ~8 s warm | 11.2 s and 8.8 s warm; 32.5 s on the cold build-and-store | Pass |
| Container suite | 608 | **608 passed, 0 failed** | Pass |
| Host suite | 1010 + 9 new | **1019 passed**, 42 skipped, 1 failed (known) | Pass |

### Phase 3 — reliable_change wired as a warning
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Reports a floor per pain score | Populates when data allow | **All six**: nrs 0.93 / 78 epochs, mpq_sum 4.84, vas 13.39, back_vas 13.42, left_leg_vas 14.38, relief 17.29 | Pass |
| Blocks nothing | All other analyses present, verdict unmoved | 29 keys, all 8 others present, `blocked`/`licensed` false unchanged | Pass |
| First draft passed the wrong frame | — | `eps` has no rating columns; every item said "no ratings matched" and would have forever | Fixed |
| Container / host | 608 / 1019 | **608 passed 0 failed / 1019 passed**, 1 known | Pass |

### Phase 4 — within_visit_band_scores deleted
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| What the third grouping says | Live numbers | 22 bands x 3 contacts, **0 responders everywhere** (pooled table: 194 of 294 assessed) | Ran |
| Caveat stated | Not buried | `assess_response` defaults to requiring suppression; the zero is "no band that suppresses" | Stated |
| Deletion breaks nothing | Suites green | **Broke 3 tests** — the import block was a re-export; repointed them at `within_visit` | Fixed |
| Host / container | 1016 / 608 | **1016 passed** (1019 − 3 removed), **608 passed 0 failed** | Pass |

### Phase 5 — open item 26, the device-spectrum mark
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| How much of the record is affected | Unknown before measuring | **R 0-3+ 358 of 451 (79.4%)**, L 1-3+ 83 of 174 (47.7%), then 3, 5, 0, 0 | Measured |
| Does the axis actually stand still there | The structural claim, observed | Correlation travels **0.037** across all ten lengths on R 0-3+ against 0.160 / 0.253 on the two contacts with none | Measured |
| The mark agrees with the matcher | Same counts | 358 / 83 / 3 / 5 / 0 / 0 on both, all six contacts | Pass |
| The denominator is the cell's own | Equals `n_grid` | True on every contact; the curve grid's equals its own high+low | Pass |
| The two grids can disagree | Constructed, since RCS08 cannot show it | Curve denominator 6 against 9; correlation share 1/3, curve share 0 | Pass |
| Per-cell really differs from per-contact | Not just theory | The outlier rule left ONE cell with 8 reports where its neighbours had 9 — share 0.375 against 0.333 | Pass |
| Equality proof, no tolerance | No scientific value moves | 27,935 before, 36,399 after, **0 dropped, 8,464 added, 24 of 27,935 differ — all wall-clock timing** | Pass |
| Frontend reached the served bundle | Strings, not component names | All four strings in `806.168b8286.chunk.js`; build clean, no warning in the touched file | Pass |
| Container suite | 608 + new | **620 passed, 0 failed** (+12) | Pass |

**A defect of my own, caught by the equality proof rather than by review.** The per-report flag was
built inside `chunk_exclusion`, which is copied into the served response whole — so the first proof
showed **4,584 added fields named `from_device_spectrum`**, one boolean per pain report per contact
pair, growing with every report filed, for a fact the grids already carry summarised per cell. It is
also not an exclusion, and a field is easiest to misread under the wrong name. Lifted out; added
fields fell from 13,048 to 8,464; a regression test pins it.

**A second one, caught by my own new test.** The first version asserted every cell's share was
exactly 3/9. One cell's is 0.375, because the outlier rule dropped a report from that cell alone.
The expectation was wrong, not the code — and the test now pins that difference deliberately, since
it is the clearest evidence that a per-contact share pasted onto every cell would be wrong.

### Phase 6 — open item 7, every pain score precomputed
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Every score is built and stored | Six stored | Six, six distinct keys, 6.8-11.0 s each | Pass |
| **Do they survive each other?** | Six on disk | **ONE of six** — the store keeps one entry per participant per kind | **Defect** |
| After the store fix | Six on disk | **6 of 6, 4.05 MB total** | Pass |
| A page request for a stored score | Served, not rebuilt | Served in 2.4 s where it had rebuilt in 8.9 s | Pass |
| Speed + equality, alternating rounds | No scientific value moves | served 2.9 / 5.4 s against fresh 10.4 / 12.0 s; **36,401 compared, 22 differing, all bookkeeping, 0 scientific** | Pass |
| The daily pass | Cheap when nothing moved | Six `already_current` at 2.5-2.9 s each; no-recordings participant not a failure; exit 0 | Pass |
| Fan-out guard | Neither launcher starts anything inside a precompute run | Both refuse, with a control proving the refusal is the flag's doing | Pass |
| Container / host | 620 / 1016 + new | **635 passed 0 failed** (+15) / **1021 passed** (+5), 1 known | Pass |

**The defect is the finding.** Six writes each reported success and five of the six answers were
gone. Nothing on any page or in any log said so, and every test passed throughout — because no test
had ever asked what happened to the entry written *before last*. Fixed in the store rather than
worked around in the caller, because the one-entry-per-kind rule is the store's own.

**A hazard in my own test, disclosed rather than quietly fixed.** The control called the launcher
without switching the feature off; on the container runner, whose store points at the production
root, it went all the way through and really started background jobs for a participant called "u",
leaving two marker files in the live cache directory. That is decision 96's own finding reproduced
one launcher later. Markers cleared, test fixed, re-run leaves none.
