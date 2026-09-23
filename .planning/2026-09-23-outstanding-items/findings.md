# Findings

- The stability answer depends on the grid's pain score: 3,123 of 5,148 stored values differ between the NRS and Left Leg VAS answers (2026-09-23).
- The Closed-Loop page sent the clinic-sheet switch; the server dropped it (fixed in 248).
- A band chosen on the grid carries an empty label, so the deployment summary uses its default pain score and split (nrs / tertile) whatever grid the band came from (2026-09-23; reported in 249, not changed).
- Decision 239's merged clinic-stream answer (55 Hz, both pairings, 1 pair short) is on no response: the clinic stream has no pooled-across-pulse-widths fit (2026-09-23, reported in 251).
- The left chronic log has no readings Jan-Mar 2026 or Jun 2026; most settings just before a held one are visit steps of under an hour (2026-09-23, decision 252).
