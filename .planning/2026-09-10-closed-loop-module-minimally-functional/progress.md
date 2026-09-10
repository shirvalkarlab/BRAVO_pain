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
