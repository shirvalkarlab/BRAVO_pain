# Why the two ways of computing uncertainty in the Closed-Loop evidence disagree at 40 or more groups

## 1. Short answer
- The number of groups is the wrong thing to count. The code switches methods at 40 groups. What actually decides whether the faster method can be trusted is how evenly the information is spread across the groups. On this record it is spread very unevenly. In the regressions checked, 52 to 65 groups carry the information of only about 1 to 19 evenly spread groups.
- When the information sits in a handful of groups, the resampling method is right and the faster method's intervals are too narrow. On constructed data built like this record, with no true relationship, the faster method calls a relationship at the 5% level in 12% to 19% of datasets. The resampling method does so in 4% to 6%.
- When one group carries almost all the information, neither method can be believed. The resampling method then fails in a way that looks like success. On RCS08 this happens in 29 of 90 cells of the band-power-to-pain regression. The cause is 6 recorded power values, all in one long stimulation-off stretch, each 100 to 180 times the cell's 99.9th percentile.
- The one live use at 40 or more groups agrees. That use is E3, the change in pain per milliamp on the Closed-Loop page. It has one row per group: 90 groups on the left and 91 on the right. The three methods give p 0.0085 / 0.013 / 0.011 on the left and 0.023 / 0.031 / 0.029 on the right. Nothing on the page moves because of this analysis.

## 2. The two methods, and where each runs today
Both methods measure how uncertain a straight-line fit is when many samples share one group and so are not independent.
- Method 1, adding up the scatter group by group (the cluster-robust sandwich, CR0). The line is fitted once. Its uncertainty is the sum, over groups, of how far each group's samples sit from the line. It is justified by an argument that holds better as the number of groups grows.
- Method 2, flipping whole groups (the restricted wild cluster bootstrap-t). Every group is kept. The data are rebuilt many times with the line forced to the value being tested. In each rebuild, each group's leftover deviations are multiplied by +1 or -1 at random. The test statistic is recomputed each time.
- The handoff's phrase "resamples whole groups" is not quite right: no group is dropped or repeated, only sign-flipped. E2 today does resample whole pain reports, but it uses neither method.
- The switch is estimator_for in analytics.py, re-exported by edges.py.

Where the switch is reached today, on the Closed-Loop page's evidence triangle:
- E1 on screen is the pooled titration estimate. It uses neither method through the switch: it has its own sandwich on 5 runs (left) and 9 (right).
- The historical E1 (actuation_edge) goes through the switch. On RCS08 it has 56 to 65 groups, so it uses method 1. It has been on no page since decision 246.
- E2 on screen is an area under the curve with whole-report resampling. No switch.
- E3 on screen goes through the switch at 90 and 91 groups, so it uses method 1.

## 3. Where "they should agree" came from
- The code says method 1 rejects a true null "0.060 to 0.076" of the time. That figure comes from simulate_clustered in test_bootstrap.py. In that simulation every group has exactly 20 samples, and the tested quantity is normal and constant within each group.
- The record has neither property. That is why the 2026-09-04 disagreement stayed unexplained: at 54 to 83 groups, method 1 resolved 34 band-to-pain cells and method 2 resolved 6.

Three candidate causes, cheapest checked first:
1. Not a like-for-like comparison. Falsified: both methods ran on the same rows in the same script. The small-sample correction moves the error by about 1%, but the interval widths differ by 1.1 to 250 times. E3 agrees within 3% to 4%.
2. Information concentrated in a few groups, because group sizes differ by orders of magnitude and band power has a long upper tail. Supported, by construction and on the record.
3. Within-group errors not shaped like the simulation's (the handoff's guess). Not needed: CR0 assumes no particular shape, and in the constructed runs only the balance changed.

The measure used is the effective number of groups: one over the sum of the squared shares of the tested quantity's spread held by each group (partial leverage, MacKinnon, Nielsen and Webb 2023). Equal shares across 60 groups give 60; one group holding everything gives 1.

## 4. Results

### 4.1 Constructed data
Setup: 60 groups, no true relationship, 1,000 datasets per scenario (chance error about ±0.014). Each entry gives the effective number of groups, then the rate of false "yes" at the 5% level for sandwich / flipping / drop-one (the drop-one method is the cluster jackknife, CR3), then the median ratio of interval widths, flipping over sandwich.

Band-to-pain design (the outcome is the same for every sample in a group):
- Equal sizes, normal quantity: 40.9 effective groups; 0.068 / 0.047 / 0.054; ratio 1.07.
- Unequal sizes: 12.1; 0.170 / 0.063 / 0.064; ratio 1.25.
- Long upper tail: 5.1; 0.123 / 0.044 / 0.051; ratio 1.40.
- Unequal sizes and long tail: 3.6; 0.181 / 0.044 / 0.054; ratio 1.88.
- One group holding about 30% of rows, with far higher power: 1.3; 0.633 / 0.171 / 0.028; ratio 8.3.

Current-to-power design (the tested quantity is constant within a group):
- Equal sizes: 32.8; 0.059 / 0.038 / 0.043; ratio 1.07.
- Unequal sizes: 10.6; 0.174 / 0.061 / 0.070; ratio 1.31.
- Five currents, 60% at one: 10.8; 0.074 / 0.048 / 0.046; ratio 1.15.
- Unequal sizes and five currents: 5.3; 0.189 / 0.040 / 0.057; ratio 1.49.
- One group holding about 30% of rows and the only different current: 2.0; 0.634 / 0.108 / 0.228; ratio 3.9.

An earlier run of the dominant case, with the dominant group of ordinary size, gave flipping 0.021 and 0.002: the opposite error.

### 4.2 RCS08 (aggregates only; every cell has 52 to 65 groups, so the code picks method 1 everywhere)

Current-to-power, the historical E1 design:
- 90 cells, 31,195 to 43,913 samples each.
- 4.7 to 18.9 effective groups (median 11.8).
- Intervals excluding zero: sandwich 25, flipping 14, drop-one 21. All 14 found by flipping are also found by the other two.
- Flipping's interval is 1.10 to 2.56 times the sandwich's (median 1.21). The gap grows as the effective count shrinks (rank correlation -0.73).
- Worst on R 1-3+ (sandwich 6, flipping 0) and R 0-2+ (10 against 6), each with 4.7 effective groups.

Band power to pain, the regression as it stood on 2026-09-04:
- 90 cells, 43,241 to 50,106 samples each.
- 1.0 to 9.6 effective groups (median 1.6).
- The width ratio runs from 0.88 to 250.7 (median 3.04). It tracks the effective count (rank correlation -0.93) and not the raw count of groups (+0.40).
- In the 61 cells where no group holds 90% of the information, intervals exclude zero in 31 (flipping), 29 (sandwich) and 12 (drop-one).
- In the 29 cells where one group holds 90% or more: sandwich 0, drop-one 0, and flipping gives p below 0.05 in 24 while its own interval excludes zero in only 2. Across all 90 cells, 24 report p below 0.05 beside an interval that contains zero.

Why the flipping p collapses:
- When one group dominates, the test statistic is close to that group's contribution divided by itself, so it is capped near 1.
- On L 0-3+ at 16.5 to 24.5 Hz, the observed statistic is 0.96 to 0.98 and the 95th percentile of the rebuilt statistics is 0.90 to 0.95. So p comes out 0.001 to 0.017, decided by the second decimal of a number that carries no information.
- The interval, found by testing a grid of values, steps over that narrow region: at most 2 of 401 grid points inside any reported interval are rejected. The live code pairs this p with this interval on one edge.

The dominant group:
- It is the same stretch on all three left pairs: both sides at 0 mA, 289.7 hours long, 11% to 13% of the rows.
- Its median band power is not unusual: 0.66 to 0.83 times the other groups'.
- Six of its samples (0.1% of the stretch) carry 99.6% to 99.8% of its share. Their band power is 103 to 182 times the cell's 99.9th percentile. No sample in any other group exceeds 2.4 times it.
- That they are recording artefacts is inferred from their size, not checked against the recordings.

E3: 45.5 (left) and 36.2 (right) effective groups; p as in §1; flipping's interval is 1.04 and 1.03 times the sandwich's.

## 5. Found on the way (not built)
1. The live E1 on the triangle uses the sandwich on 5 runs (left, L 1-3+ 24.5 Hz) and 9 runs (right, R 0-3+) with no switch. The code is within_visit._cluster_robust_ols, with a t reference on (samples − columns) degrees of freedom. Numbers are from the saved Closed-Loop captures of 2026-09-25. p is 0.72 and 0.18, so no verdict rests on it, but its interval is too narrow.
2. The response's inference label, estimator_for(n_clusters), names the wrong method on two edges. For pooled E1 it says "wild cluster bootstrap-t" although the sandwich was used. For E2 it says the bootstrap on the left (31 reports) and CR0 on the right (48) although E2 resamples whole reports. No page reads the field.
3. _BootstrapPlan builds a samples-by-samples matrix: Pr = Xr @ np.linalg.pinv(Xr). Today's cells hold 43,835 to 64,510 samples, so that matrix is 15 to 33 GB. For R 0-3+ it exceeded the container's 42 GB and the process was killed, which is why that pair is missing. The switch never sends an RCS08 cell there, but a participant with fewer than 40 stretches would hit it. There is an exact fix that avoids the matrix; it would need its own equality proof.
4. The live E2 is rank-based, so the six values cannot dominate it. Its report-resampling interval was not examined.

## 6. Which is right for this record
- With the information in about 4 to 20 effective groups: flipping, with drop-one agreeing. The sandwich is too narrow.
- With one group at 90% or more: neither. The honest answer is "cannot be judged", and the cause is the six samples, not the choice of method.
- The live E3 is fine either way.

## 7. References
- Cameron, Gelbach and Miller (2008), Rev Econ Stat 90:414.
- Cameron and Miller (2015), J Hum Resour 50:317.
- Carter, Schnepel and Steigerwald (2017), Rev Econ Stat 99:698.
- MacKinnon and Webb (2017), J Appl Econom 32:233.
- MacKinnon, Nielsen and Webb (2023), J Econom 232:272.
===== END DOCUMENT =====

DRAFT DECISION ROW: P-12 explained (read-only, no code changed). The Closed-Loop edges switch from the cluster-robust sandwich to the wild cluster bootstrap-t at 40 groups. The two disagree above 40 because what matters is how evenly the information is spread across the groups, not how many there are. The 0.060 to 0.076 rate quoted in the code came from a simulation with 20 samples in every group.
- Constructed data, 60 groups, no true effect: once the information sits in 4 to 12 effective groups, the sandwich calls a relationship in 12% to 19% of datasets; flipping and drop-one stay at 4% to 7%. With one dominant group, every method fails (sandwich 63%).
- RCS08, 5 of 6 sensing pairs, all cells 52 to 65 groups. Current-to-power: 4.7 to 18.9 effective groups; the sandwich resolves 25 cells, flipping 14, drop-one 21. Band-to-pain regression as of 09-04: in 29 of 90 cells one stimulation-off stretch holds 90% or more of the information, carried by 6 samples at 103 to 182 times the 99.9th percentile. There, flipping's p-value collapses (p below 0.05 in 24 of the 29 cells while its interval excludes zero in only 2), and the sandwich and drop-one resolve none.
- The live E3 (one row per group, 90 and 91 groups) agrees across all three methods: p 0.0085 / 0.013 / 0.011 on the left and 0.023 / 0.031 / 0.029 on the right. Nothing on any page moves.
- Found on the way: the triangle's E1 uses the sandwich on 5 and 9 runs with no switch; the response mislabels the method on E1 and E2; the flipping routine builds a samples-by-samples matrix of 15 to 33 GB, too big for R 0-3+.

## Correction, 2026-09-26 (decision 289)

This analysis was run between 20:44 and 21:13 UTC on 2026-09-25, while the saved 3 s tiles were a
short copy (293,108 TD pieces where the full set is 303,321; decision 289). Its E3 numbers read no
tile and reproduce on the full tiles (left p 0.0085 on 90 groups, right 0.023 on 91). Its band-power
cells (current-to-power and the band-to-pain regression) were read from the short copy, so their
sample counts (31,195 to 43,913 and 43,241 to 50,106 per cell) and the counts of resolved cells
(for example 29 of 90 cells with one dominant group) need re-measuring; that has not been done. The
band-to-pain regression here matched each piece's own settings period, so decision 290's join error
does not touch it. The method comparison on constructed data (section 4.1) reads no recording and
stands.
