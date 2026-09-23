# Findings

- The stability answer depends on the grid's pain score: 3,123 of 5,148 stored values differ between the NRS and Left Leg VAS answers (2026-09-23).
- The Closed-Loop page sent the clinic-sheet switch; the server dropped it (fixed in 248).
- A band chosen on the grid carries an empty label, so the deployment summary uses its default pain score and split (nrs / tertile) whatever grid the band came from (2026-09-23; reported in 249, not changed).
