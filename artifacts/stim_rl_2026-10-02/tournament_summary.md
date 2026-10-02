# Offline RL tournament: ranked by expected drop in home pain against risk

Apple GPU check: MPS available = True, device mps:0; weights moved after 5 pilot updates: BC 6/6, CQL 34/34, IQL 37/37, TD3+BC 36/36.

Expected drop: how much more home pain fell from the previous period (0-10 points) in long-term periods near the recommendation than in periods far from it (thirds by distance); positive is good. An association in records where settings were not randomised. rho_change: rank correlation of distance with the change in pain (positive is good); p: one-sided, from rotating the series. rho_adv: rank correlation of the model's predicted gain from each switch with the observed drop. No-visit and 24 h columns: the expected drop on the periods with no visit inside (24) and with a 24-hour wash-in (34). Risk: 0 below 4.0 mA, 1 at the 4.5 mA ceiling. Mean over seeds.

| rank | model | reward | source | seeds | expected drop (sd) | rho_change | p | rho_adv | p (adv) | no-visit drop | 24 h drop | risk | past a limit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | GP bandit | delta | small / reference | 1 | 0.49 () | 0.21 | 0.096 | 0.01 | 0.500 | -0.12 | 0.49 | 0.000 | 0.00 |
| 2 | QTable-AC (explore) | delta | small / reference | 1 | 0.32 () | 0.16 | 0.115 | -0.00 | 0.500 | 0.69 | 0.02 | 0.000 | 0.00 |
| 3 | QTable-AC (explore) | level | small / reference | 1 | 0.32 () | 0.16 | 0.115 | -0.00 | 0.442 | 0.69 | 0.02 | 0.000 | 0.00 |
| 4 | QTable-AC (explore) | worst_site | small / reference | 1 | 0.32 () | 0.16 | 0.115 | 0.01 | 0.423 | 0.69 | 0.02 | 0.000 | 0.00 |
| 5 | Most common setting (55.0, 0.0, 0.0, 60.0, 160.0) | delta | small / reference | 1 | 0.16 () | 0.13 | 0.096 |  |  | 0.57 | -0.02 | 0.000 | 0.00 |
| 6 | Most common setting (55.0, 0.0, 0.0, 60.0, 160.0) | level | small / reference | 1 | 0.16 () | 0.13 | 0.096 |  |  | 0.57 | -0.02 | 0.000 | 0.00 |
| 7 | Most common setting (55.0, 0.0, 0.0, 60.0, 160.0) | worst_site | small / reference | 1 | 0.16 () | 0.13 | 0.096 |  |  | 0.57 | -0.02 | 0.000 | 0.00 |
| 8 | IQL | level | d3rlpy (mps) | 3 | 0.10 (0.14) | 0.05 | 0.346 | 0.24 | 0.058 | 0.16 | -0.06 | 0.010 | 0.00 |
| 9 | GP bandit | level | small / reference | 1 | 0.07 () | 0.06 | 0.327 | -0.01 | 0.481 | 0.07 | -0.19 | 0.000 | 0.00 |
| 10 | AgentDB pick: actor critic | worst_site | agentdb arm | 3 | 0.03 (0.05) | 0.01 | 0.558 | 0.03 | 0.577 | 0.02 | 0.08 | 0.001 | 0.00 |
| 11 | QTable bandit (gamma 0) | level | small / reference | 1 | 0.02 () | 0.02 | 0.481 | 0.00 | 0.423 | 0.12 | -0.34 | 0.000 | 0.00 |
| 12 | QTable bandit (gamma 0) | worst_site | small / reference | 1 | 0.02 () | 0.02 | 0.481 | 0.01 | 0.423 | 0.12 | -0.34 | 0.000 | 0.00 |
| 13 | AgentDB pick: sarsa | delta | agentdb arm | 3 | -0.01 (0.11) | -0.02 | 0.635 | -0.03 | 0.654 | 0.60 | -0.47 | 0.000 | 0.00 |
| 14 | TD3+BC | delta | d3rlpy (mps) | 3 | -0.04 (0.30) | 0.00 | 0.673 | 0.04 | 0.481 | 0.10 | -0.15 | 0.034 | 0.00 |
| 15 | IQL | worst_site | d3rlpy (mps) | 3 | -0.05 (0.15) | -0.01 | 0.596 | 0.09 | 0.385 | 0.01 | 0.04 | 0.014 | 0.00 |
| 16 | IQL | delta | d3rlpy (mps) | 3 | -0.05 (0.11) | 0.00 | 0.462 | 0.08 | 0.231 | 0.12 | -0.04 | 0.016 | 0.00 |
| 17 | Clinician mode (table) | delta | small / reference | 1 | -0.06 () | 0.05 | 0.404 | 0.01 | 0.538 | 0.27 | 0.21 | 0.000 | 0.00 |
| 18 | Clinician mode (table) | level | small / reference | 1 | -0.06 () | 0.05 | 0.404 | -0.07 | 0.712 | 0.27 | 0.21 | 0.000 | 0.00 |
| 19 | Clinician mode (table) | worst_site | small / reference | 1 | -0.06 () | 0.05 | 0.404 | -0.06 | 0.635 | 0.27 | 0.21 | 0.000 | 0.00 |
| 20 | BC | delta | d3rlpy (mps) | 3 | -0.06 (0.12) | -0.00 | 0.577 |  |  | 0.01 | -0.00 | 0.026 | 0.00 |
| 21 | BC | level | d3rlpy (mps) | 3 | -0.06 (0.12) | -0.00 | 0.577 |  |  | 0.01 | -0.00 | 0.026 | 0.00 |
| 22 | BC | worst_site | d3rlpy (mps) | 3 | -0.06 (0.12) | -0.00 | 0.577 |  |  | 0.01 | -0.00 | 0.026 | 0.00 |
| 23 | QTable bandit (gamma 0) | delta | small / reference | 1 | -0.08 () | 0.08 | 0.288 | 0.08 | 0.250 | 0.36 | 0.24 | 0.000 | 0.00 |
| 24 | QTable-AC (exploit) | delta | small / reference | 1 | -0.08 () | 0.08 | 0.288 | -0.00 | 0.500 | 0.36 | 0.24 | 0.000 | 0.00 |
| 25 | AgentDB pick: actor critic | level | agentdb arm | 3 | -0.10 (0.15) | -0.02 | 0.635 | 0.03 | 0.538 | 0.04 | -0.03 | 0.002 | 0.00 |
| 26 | QTable-AC (exploit) | worst_site | small / reference | 1 | -0.11 () | -0.01 | 0.596 | 0.01 | 0.423 | 0.12 | -0.34 | 0.000 | 0.00 |
| 27 | AgentDB pick: actor critic | delta | agentdb arm | 3 | -0.12 (0.14) | -0.04 | 0.615 | -0.05 | 0.769 | -0.01 | 0.01 | 0.004 | 0.00 |
| 28 | AgentDB pick: decision transformer | level | agentdb arm | 3 | -0.12 (0.05) | -0.08 | 0.788 |  |  | -0.08 | -0.27 | 0.004 | 0.00 |
| 29 | CQL | level | d3rlpy (mps) | 3 | -0.14 (0.05) | -0.05 | 0.673 | -0.19 | 0.923 | 0.16 | -0.39 | 0.001 | 0.00 |
| 30 | AgentDB pick: sarsa | level | agentdb arm | 3 | -0.14 (0.06) | -0.04 | 0.538 | -0.13 | 0.692 | 0.25 | -0.52 | 0.000 | 0.00 |
| 31 | AgentDB pick: decision transformer | worst_site | agentdb arm | 3 | -0.14 (0.05) | -0.06 | 0.750 |  |  | 0.06 | -0.16 | 0.006 | 0.00 |
| 32 | CQL | delta | d3rlpy (mps) | 3 | -0.15 (0.02) | -0.06 | 0.712 | -0.16 | 0.865 | 0.04 | -0.35 | 0.000 | 0.00 |
| 33 | AgentDB pick: decision transformer | delta | agentdb arm | 3 | -0.15 (0.09) | -0.06 | 0.712 |  |  | -0.15 | -0.20 | 0.000 | 0.00 |
| 34 | AgentDB pick: retrieval | delta | agentdb arm | 3 | -0.16 (0.05) | -0.02 | 0.635 |  |  | -0.16 | -0.04 | 0.000 | 0.00 |
| 35 | QTable-AC (exploit) | level | small / reference | 1 | -0.18 () | -0.10 | 0.769 | -0.00 | 0.442 | 0.11 | -0.34 | 0.000 | 0.00 |
| 36 | CQL | worst_site | d3rlpy (mps) | 3 | -0.18 (0.06) | -0.06 | 0.731 | -0.20 | 0.923 | 0.07 | -0.42 | 0.001 | 0.00 |
| 37 | AgentDB pick: sarsa | worst_site | agentdb arm | 3 | -0.19 (0.12) | -0.06 | 0.654 | -0.08 | 0.750 | 0.16 | -0.46 | 0.000 | 0.00 |
| 38 | GP bandit | worst_site | small / reference | 1 | -0.29 () | -0.17 | 0.923 | 0.07 | 0.385 | 0.09 | -0.56 | 0.000 | 0.00 |
| 39 | Random setting | delta | small / reference | 1 | 0.10 () | 0.06 | 0.346 |  |  | 0.17 | -0.25 | 0.673 | 0.35 |
| 40 | Random setting | level | small / reference | 1 | 0.10 () | 0.06 | 0.346 |  |  | 0.17 | -0.25 | 0.673 | 0.35 |
| 41 | Random setting | worst_site | small / reference | 1 | 0.10 () | 0.06 | 0.346 |  |  | 0.17 | -0.25 | 0.673 | 0.35 |
| 42 | TD3+BC | worst_site | d3rlpy (mps) | 3 | -0.12 (0.08) | -0.04 | 0.673 | 0.15 | 0.115 | 0.15 | -0.34 | 0.106 | 0.06 |
| 43 | AgentDB pick: retrieval | level | agentdb arm | 3 | -0.22 (0.14) | -0.06 | 0.731 |  |  | -0.20 | -0.12 | 0.013 | 0.01 |
| 44 | AgentDB pick: retrieval | worst_site | agentdb arm | 3 | -0.22 (0.06) | -0.05 | 0.712 |  |  | -0.20 | -0.12 | 0.013 | 0.01 |
| 45 | TD3+BC | level | d3rlpy (mps) | 3 | -0.33 (0.26) | -0.12 | 0.923 | 0.26 | 0.077 | -0.06 | -0.32 | 0.113 | 0.05 |
| 46 | Keep current setting | delta | small / reference | 1 | -0.51 () | -0.30 | 1.000 |  |  | -0.35 | -0.60 | 0.112 | 0.06 |
| 47 | Keep current setting | level | small / reference | 1 | -0.51 () | -0.30 | 1.000 |  |  | -0.35 | -0.60 | 0.112 | 0.06 |
| 48 | Keep current setting | worst_site | small / reference | 1 | -0.51 () | -0.30 | 1.000 |  |  | -0.35 | -0.60 | 0.112 | 0.06 |

Held-out visits (5-fold by visit, d3rlpy evaluators, deep models only): action difference from the clinician's choice (mean squared, scaled units), TD error, and the value the model expects from the first state of a left-out visit (its own estimate, pain points).

| model | reward | action diff | TD error | initial-state value |
|---|---|---|---|---|
| IQL | level | 0.363 | 2.272 | 1.75 |
| TD3+BC | delta | 3.638 | 0.696 | 2.40 |
| IQL | worst_site | 0.374 | 2.279 | 1.59 |
| IQL | delta | 0.346 | 0.546 | 0.87 |
| BC | delta | 0.468 |  |  |
| BC | level | 0.468 |  |  |
| BC | worst_site | 0.468 |  |  |
| CQL | level | 0.365 | 61.635 | -1.13 |
| CQL | delta | 0.364 | 94.807 | -3.51 |
| CQL | worst_site | 0.361 | 66.687 | -1.26 |
| TD3+BC | worst_site | 2.265 | 1.864 | 7.60 |
| TD3+BC | level | 2.190 | 2.093 | 7.08 |

## Today's recommendation from the top models (seed 0), per Left contact

**GP bandit, delta reward**

| Left contact | rate Hz | Left mA | Right mA | Left us | Right us | risk |
|---|---|---|---|---|---|---|
| L C+2- | 55 | 1.00 | 1.00 | 290 | 290 | 0.00 |
| L C+1- | 55 | 1.40 | 1.00 | 60 | 160 | 0.00 |
| off (Left 0 mA) | 10 | 0.00 | 0.00 | 60 | 60 | 0.00 |
| L 1+2- | 55 | 1.00 | 1.00 | 290 | 290 | 0.00 |
| L C+2a- | 55 | 1.00 | 1.00 | 290 | 290 | 0.00 |

**QTable-AC (explore), delta reward**

| Left contact | rate Hz | Left mA | Right mA | Left us | Right us | risk |
|---|---|---|---|---|---|---|
| L C+2- | 10 | 2.50 | 0.00 | 60 | 60 | 0.00 |
| L C+1- | 10 | 2.50 | 0.00 | 60 | 60 | 0.00 |
| off (Left 0 mA) | 10 | 0.00 | 0.00 | 60 | 160 | 0.00 |
| L 1+2- | 10 | 2.50 | 0.00 | 60 | 60 | 0.00 |
| L C+2a- | 10 | 2.50 | 0.00 | 60 | 60 | 0.00 |

**QTable-AC (explore), level reward**

| Left contact | rate Hz | Left mA | Right mA | Left us | Right us | risk |
|---|---|---|---|---|---|---|
| L C+2- | 10 | 2.50 | 0.00 | 60 | 60 | 0.00 |
| L C+1- | 10 | 2.50 | 0.00 | 60 | 60 | 0.00 |
| off (Left 0 mA) | 10 | 0.00 | 0.00 | 60 | 160 | 0.00 |
| L 1+2- | 10 | 2.50 | 0.00 | 60 | 60 | 0.00 |
| L C+2a- | 10 | 2.50 | 0.00 | 60 | 60 | 0.00 |
