# Session log — 2026-09-23

- Read panel D's plan and audited what was already true. Item 5's page half was already done: the
  stability card is full width and directly after the evidence triangle. Only its note half was
  outstanding.
- Built in this order, each with its tests watched failing first: the second reading of the
  band-power-to-pain edge (10 tests), the stability sentence in the coherence note (4), the caveats
  list (7), then the four page changes (12 jest tests).
- Measured, on constructed records, because no live one was reachable:
  - a current driving both the band and the pain: 1.000 plainly, 0.477 with the current taken out;
  - a band with its own pain relationship: 0.917 plainly, 0.909 adjusted, partial correlation
    +0.657 (+0.551 to +0.719);
  - on a table of the live record's shape (32,069 samples, 32 pain reports) the estimator took
    3.07 s plainly and 5.53 s with the second reading (medians of three alternating rounds:
    5.41/3.07/2.52 against 5.66/5.40/5.53), and the plain answer's 23 fields came back with 0
    differing when the adjustment was asked for.
- Suites: host 1409 passed / 5 skipped / 0 failed. Two tests initially failed only because this
  session's virtual environment had no Google API package; installed, they pass. The container suite
  cannot run here (no MySQL, Redis, R or rpy2).
- Jest on the Closed-Loop page: 61 of 63 passing. The two failures are the known pair (decision 147);
  confirmed pre-existing by running the page's suites on a stashed tree before the changes.
- Bundle rebuilt and the four new sentences found in chunk 732.487c2ca2 by their own string literals.
- OWED: the live before-and-after on RCS08. The payload gains `caveats` and `edges.E2.adjusted`,
  the coherence note gains one sentence, and nothing else should move.

- 2026-09-22, the PI's machine: the live before-and-after run and recorded in decision 242. Both
  sides lose nothing and change no number; the new reading on the left is 0.469 against 0.559, and
  0.552 on its own sample, so taking the current out is what moves it. Container 702 / 0 (first run
  on this code), host 1450 / 2 / 0, jest 61 / 63 (the known pair).
