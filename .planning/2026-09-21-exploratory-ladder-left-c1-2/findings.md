# Findings

- L C+1-2- carried 0.0 mA only (14 epochs, 2025-07-18 to 2025-10-10, 983 h, 102 reports); contact 1 alone 0-3.5 mA, mostly 1.6 mA.
- Readiness screen, Left: best contact L 0-3+ at 125 Hz, pain-positive 24.5, 25.5, 26.5, 27.5 Hz, 0 bands falling with current (never stimulated through 1+2).
- In force Left: C+2-, 55 Hz, 100 us; Right held at 2.5 mA.
- The one-day "1a-2a" epoch (2025-11-12, 1.0 mA, 1 report) matched rings {1,2} and made the exposure sentence say "0 to 1 mA"; full-ring and partial-ring epochs are now counted apart (`ever_powered` reads full rings only).
- The proposed configuration's rate must be the cell's (125 Hz), and the rate in force (55 Hz) shown beside it; at 55 Hz the half-rate harmonic (27.5 Hz) sits on the watched bands.
- Field diff, before/after pickles: 8,821 common, 8 differing (cache_status.*, store.*: the response key carries the code digest), 1,630 added, 2 removed (bookkeeping). The ordinary ladders, joint corners and session time are untouched.
