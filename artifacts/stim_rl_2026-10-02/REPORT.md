# Offline reinforcement learning for RCS08's stimulation settings: what was built and how it did

2026-10-02, overnight autonomous run. **On no page.** Nothing here is called by the server or
shown in the browser, and nothing writes to the device. Code: `BRAVO/modules/StimRL/`
(README there). Ranked tables: `tournament_summary.md` / `.csv` and `expected_drop_vs_risk.png` in
this folder. Literature and model search: `literature.md`.

## 1. Bottom line

1. **No model's recommendation is linked to how the patient did at home.** We tested 48 model ×
   reward combinations (references included) on 52 long-term setting periods (563 REDCap reports, none used in
   training). The best was the Gaussian-process bandit: periods whose setting was nearer its
   recommendation saw 0.49 points more pain drop than periods far from it (rank correlation 0.21,
   rotation p 0.096). Its sign reverses on the 24 periods with no visit inside them.
   The smallest correlation this test could detect 80% of the time is about 0.34, so the result
   cannot rule an effect out: it says we could not detect one.
2. **One weak, unconfirmed signal in the clinic sheets.** In visits held out of training, the
   Q-table actor-critic (and its one-step version) with the `delta` reward ranked the relief that
   followed a switch slightly above chance: switch-gain rank correlation 0.11. Refitting on
   settings shuffled within visits gave p 0.020. The pre-stated stricter test (Section 5) was met
   in 9 to 13 of 20 random splits. With about 15 combinations tested, this does not survive
   correction. No deep model showed it reproducibly (CQL met the rule on 2 of 6 runs, Section 5a).
3. **No RL model beat copying clinicians by a margin the data could detect.** Behaviour cloning
   (BC) and "clinicians' most common setting" sit within the same non-significant range as every
   RL model.
4. **The AgentDB package trains nothing on numbers.** Its RL training code is stubbed (checked in
   the package files, Section 7). The three models its skill recommends were rebuilt in PyTorch;
   none showed any signal (all p > 0.46).
5. **One model is unsafe as built.** TD3+BC with the `level` or `worst_site` reward recommended a
   setting past a limit for 6 to 19% of periods in 3 of 9 runs. In 6 of 9 runs its mean Right pulse
   width was 266 to 290 µs, where the allowed range tops out at 290.

**Recommendation: do not use any of these models to choose settings.** The next useful step is a
small blinded, randomised in-clinic comparison (Section 9), which tests a recommendation directly
instead of mining records where settings were not assigned at random.

## 2. What was built (Steps 1 to 4 of the request)

- **Step 1, environment.** `~/.venvs/bravo-stim-rl`: Python 3.12.12 (arm64 native), PyTorch
  2.14.1 with the Apple GPU (MPS) available, d3rlpy 2.8.1, SQLAlchemy 2.1.2, pandas, scikit-learn.
- **Step 2, data pipeline** (`data_pipeline.py`).
  - **Snapshot:** `export_snapshot.py` runs in the container, reads the saved tables and writes
    them to the gitignored scratch area. A SQLAlchemy database is built from that snapshot (built
    once under a lock; each table's row count is checked against the export).
  - **Trajectories:** one episode per visit sheet, in-clinic and at-home pooled (your instruction).
  - **State, 24 numbers:** the seven pain sites, their mean and worst, the side-effect grade, the
    setting in force, the Left contact, at home or not, and the visit's first rating.
  - **Action:** rate, Left and Right current, Left and Right pulse width.
  - **Reward, three versions:**
    - `delta`: drop in mean pain since the last step;
    - `level`: drop below the visit's first rating;
    - `worst_site`: half `level`, half the drop on the worst site.

    All three subtract the side-effect cost (Stim Optimizer's ladder: 0, 1, 2 points). They
    subtract up to 2 points between 4.0 mA and the 4.5 mA ceiling. A setting past a limit, or a
    moderate side effect, ends the episode with -10 points.
  - **Output:** a d3rlpy `MDPDataset`: 30 episodes, 496 transitions.
- **Step 3, tournament** (`train_tournament.py`, `device="mps:0"`):
  - **Deep models:** BC, CQL, IQL and TD3+BC, each run with 3 rewards × 3 seeds, 5,000 updates,
    and a five-part split by visit for d3rlpy's held-out scores.
  - **Small models:** the Q-table actor-critic you asked for (`tabular.py`). Its critic is a
    table of 18 state cells × 72 setting cells; its actor is a probability table weighted by how
    often clinicians chose each cell and by a pessimistic value. It is read two ways: "exploit"
    (the setting to keep) and "explore" (the setting to test next). Alongside it, a one-step
    Q-table bandit and a Gaussian-process bandit (the Stim Optimizer's model family).
  - **AgentDB arm:** in `agentdb_arm/`.
  - **References:** keep the current setting; clinicians' most common setting; random settings.
- **Step 4, checks.**
  - **MPS sanity check:** all networks on `mps:0`; after 5 pilot updates every trainable weight
    moved, with finite losses (BC 6/6, CQL 34/34, IQL 37/37, TD3+BC 36/36 parameter tensors).
  - **Scorers:** d3rlpy's evaluators (initial-state value, TD error, action difference) on visits
    held out of training.
  - **Report:** this file, the ranked summary and the figure.

## 3. Data

- **Training:**
  - 569 rated visit-sheet steps (458 in-clinic, 111 at-home) from 31 sheets.
  - 45 steps from the July 2025 sheet were dropped: it records no rate or pulse width.
  - Unrated steps never count as pain data.
  - No REDCap value enters training.
- **Validation:**
  - 92 long-term setting periods since implant, of which 52 had at least 3 home reports and a
    period before them. Reports filed on a visit day are left out.
  - The six REDCap items are put on the 0-10 scale (nrs, vas, left leg, back, McGill total,
    relief reversed) and averaged.
  - Home reports sit about 3 points higher than sheet ratings (7.35 against 4.39). So each home
    state is mapped to the training value at the same rank before a model sees it.
- **Safety in the data:**
  - No rated step broke a limit, and no side-effect grade above 1 was recorded (15 grades in all).
  - So the models never saw a terminal penalty in real data. Only 5 transitions (all at exactly
    4.5 mA) carried the near-ceiling penalty.
  - The safety rules are enforced by the reward in principle, and by a filter on the small models'
    recommendations. They were not learned from experience.

## 4. How the models were scored, and why on change

Pain carries over from one long-term period to the next (rank correlation 0.55 between consecutive
periods), so a score on pain LEVELS rewards any model that echoes last period's pain. A critic
that ignores the setting scored 0.548 that way. All primary scores therefore use the change in home
pain from the previous period:

- **Expected drop:** how much more pain fell in periods near the recommendation than far from it,
  in points (thirds by distance).
- **rho_change:** the rank correlation of distance with the change.
- **rho_adv:** the rank correlation of the model's predicted gain from each switch with the drop
  that followed.
- **p-values:** from rotating the series, which keeps neighbouring periods' similarity.

Sensitivity sets: the 24 periods with no visit inside, and the 34 with a 24-hour wash-in.

## 5. Results

Long-term home record (mean over seeds; full table in `tournament_summary.md`):

| model (best reward) | expected drop, points | rho_change | p | rho_adv (p) | 24 no-visit periods | past a limit |
|---|---|---|---|---|---|---|
| GP bandit (delta) | 0.49 | 0.21 | 0.096 | 0.01 (0.50) | -0.13 | 0 |
| Q-table actor-critic, explore (delta) | 0.32 | 0.16 | 0.115 | 0.00 (0.50) | 0.69 | 0 |
| Clinicians' most common setting (constant) | 0.16 | 0.13 | 0.096 | none | 0.57 | 0 |
| IQL (level) | 0.10 | 0.05 | 0.35 | 0.24 (0.058) | 0.16 | 0 |
| BC (copies clinicians) | -0.06 | 0.00 | 0.58 | none | 0.01 | 0 |
| TD3+BC (delta) | -0.04 | 0.01 | 0.67 | 0.04 (0.48) | 0.10 | 0 |
| CQL (level) | -0.14 | -0.05 | 0.67 | -0.19 (0.92) | 0.16 | 0 |
| AgentDB pick: actor-critic (worst site) | 0.03 | 0.01 | 0.56 | 0.03 (0.58) | 0.02 | 0 |
| Keep current setting | -0.51 | -0.30 | 1.00 | none | -0.35 | 0.06 |
| Random setting | 0.10 | 0.06 | 0.35 | none | 0.17 | 0.35 |

"Keep current setting" scores -0.30 because bigger setting changes were followed by bigger
pain drops. Clinicians change settings when pain is high, and high pain tends to fall by itself.
It is not evidence that changing helps.

Clinic sheets, visits held out of training (five-part split by visit). The question: does the
model's predicted gain from a switch rank the relief that followed?

- Raw value correlations (0.06 to 0.86) are matched by a model blind to settings (0.23 to 0.61),
  so they only show that pain persists.
- The switch gain: Q-table actor-critic, delta, 0.112 (within-visit shuffle p 0.003; refit on
  shuffled settings p 0.020). Q-table bandit 0.107. GP bandit -0.02. All deep models -0.04 to
  -0.09.
- Stricter test, its rule set before running. Both conditions must hold:
  - (a) q(s, next) ranks relief after removing q(s, current) and current pain (and, for the level
    rewards, the visit's first rating), with p < 0.05;
  - (c) the gain keeps its sign on switches between two active settings.

  Q-table, `delta` reward: (a) 0.063, p about 0.04; (c) 0.11 to 0.13 on 52 switches; the rule was
  met in 9 to 13 of 20 random splits. Every other small model, and every model with the level
  rewards, was met in 0 of 20 (GP: 1 of 3). The deep models are in Section 5a.

### 5a. Deep models, stricter test (seed 0)

Each deep model was fitted 5 times (five-part split by visit, 5,000 updates each).

- **Plain switch gain:** negative for every deep model and reward, from -0.04 to -0.09.
- **IQL and TD3+BC:** fail the rule on every reward. (c) is negative (-0.03 to -0.21).
- **CQL with the `delta` reward:** fails.
- **CQL with the `level` and `worst_site` rewards:** passes on seed 0.
  - (a), with the baseline removed: 0.041 and 0.081 (p 0.006).
  - (c): 0.033 and 0.007.

  Re-run on seeds 1 and 2, it passed in 0 of 4 runs once the baseline is removed. In the two
  seed-2 runs, (a) was -0.02 and -0.01.
- **CQL's own home score points the other way:** rho_adv -0.19 to -0.20.

So no deep model's recommendations are supported.

## 6. Safety and behaviour of the models

- Recommendations past a limit (current above 4.5 mA, or rate or width outside the device range):
  TD3+BC with the `level` reward in 2 of 3 seeds (6% and 10% of periods) and with the
  `worst_site` reward in 1 of 3 (19%); every other model 0% (retrieval 1.3%).
- TD3+BC's recommendations are far from clinicians' choices (held-out action difference 2.2 to
  3.6, against 0.35 to 0.47 for BC, CQL and IQL). With the `level` and `worst_site` rewards it rates its own
  first-state value at 7.1 to 7.6 pain points, far above any observed relief.
- CQL's values are unstable on held-out visits (TD error 62 to 95, against 0.5 to 2.3 for the
  others).
- The explore reading of the Q-table first recommended 10 Hz at 0 mA for every active contact.
  It had learned that off and sham steps were followed by relief. Recommendations are now
  restricted to settings that fit the contact (fixed and tested).

## 7. AgentDB (the skill you asked for)

- **The package itself:** `npx agentdb@latest` (3.0.0-alpha.20) no longer has the
  `create-plugin` RL templates. In version 1.0.7 the Decision Transformer's training data loader
  returns an empty list (`decision-transformer.js:382`: "For now, return empty"). The SARSA and
  Actor-Critic `train()` report `loss: 0` (`sarsa.js:277`, `actor-critic.js:342`). Later versions
  are an exact text look-up of state and action.
- **What was run instead:** the skill's three picks rebuilt in PyTorch, following its recipe
  (store experiences, train with a 20% hold-out split by visit, retrieve similar past steps):
  - Decision Transformer (the skill's recommended offline model);
  - SARSA (its safety-critical pick);
  - Actor-Critic (its continuous-setting pick);
  - plus the recipe's retrieval step.
- **Result:** none showed a change-based signal. Every rotation p was above 0.46, and most
  correlations pointed the wrong way. 21 tests pass in `agentdb_arm/`.

## 8. Independent checks by separate agents, and what they changed

- **Code audit** (found 12 defects; all fixed and tested before the final runs):
  - Q-table recommendations were per-column medians, never-delivered combinations in 26 of 51
    cells.
  - Blank sheet cells were filled after unrated rows were dropped (17 values wrong).
  - rho_q measured pain persistence, not the model.
  - Validation states were far outside the training range.
  - Today's recommendation used stale pain.
  - The REDCap overall VAS was mapped to the right leg.
  - A new site's first rating mid-visit was counted as a change.
  - Two reward versions depended on a baseline not in the state.
  - Four tests checked less than their names said.
- **Independent replication from the specification alone:** matched 494 transitions, the reward
  mean and spread, 52 periods, 563 reports and the contact counts exactly. It found float32 noise
  splitting tied distances (correlations moved by up to 0.03), now fixed and tested. It also found
  two exclusion rules the specification left out.
- **Scientific critique:** named the threats used above. Ratings that drive the next choice, plus
  pain falling by itself. Unblinded minute-long ratings. Clinic relief is not home outcome. A home
  test too small to show "no effect". Many tries on one split. It proposed the stricter test
  (Section 5) and the next-visit design.
- **Concurrency bug** (found when the tournament crashed): parallel processes rebuilt one
  database file at once. 10 of 12 parallel loads failed, and 2 silently read doubled data
  (1,138 rows instead of 569). Fixed with a lock and an atomic swap; regression test added.
- **Literature:** 71 items checked against a source record; 3 spot-checked again by hand (all
  matched). Its main lessons are a one-step (bandit) model first, pessimism about rarely tried
  settings, planned evaluation, and comparison with copying the clinician. They proved right
  here. No published RL study chose chronic-pain DBS settings.

## 9. What may be claimed, and what next

May be claimed:

- On 52 home setting periods, no model's recommendation was linked to pain change. The best
  rotation p was 0.096; the smallest detectable correlation is about 0.34.
- One exploratory clinic-sheet signal (Q-table, delta reward, 0.11) is not confirmed.

May not be claimed: that any model learned the best setting, that any model lowers pain, or that
stimulation settings have no effect (a narrow, non-random range of settings was tested).

Next visit (needs your go-ahead; drafted by the critique agent):

- **Settings compared:** fix the Left contact beforehand. Compare one model setting (R), chosen
  from combinations already delivered and at most 4.5 mA per side, with the current home
  setting (C).
- **Steps:** 6 R-C pairs, the order within each pair set in advance by a sealed coin flip.
- **Timing:** 10 minutes per step, rated at minute 8, then 5 minutes back at C.
- **Blinding:** the patient and the person recording the ratings are not told the setting; an
  unblinded programmer changes it.
- **Outcome:** overall pain, R minus C within each pair.
- **Analysis:** a sign-flip shuffle over the 64 possible orders. Success means a mean of -1 point
  or better with one-sided p < 0.05.
- **Stopping:** return to C at a mild-persistent side effect; end the session at a moderate one.
- **Before the visit:** check the scatter of repeat ratings already on the sheets. If the
  within-pair spread is above about 1 point, 6 pairs are too few.
- **After the visit:** repeat at a second visit, then a randomised 2-week home crossover.

## 10. Reproduce

```bash
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 300 --wait 300 \
  "python3 -B modules/StimRL/export_snapshot.py"
cd BRAVO/modules
~/.venvs/bravo-stim-rl/bin/python -m pytest StimRL/tests StimRL/agentdb_arm -q -W ignore -p no:cacheprovider
~/.venvs/bravo-stim-rl/bin/python -m StimRL.train_tournament --sanity
~/.venvs/bravo-stim-rl/bin/python -m StimRL.train_tournament --variants delta --seeds 0 1 2 --steps 5000
~/.venvs/bravo-stim-rl/bin/python -m StimRL.train_tournament --heldout-value --variants delta --seeds 0
~/.venvs/bravo-stim-rl/bin/python -m StimRL.run_switch_gain_check
~/.venvs/bravo-stim-rl/bin/python -m StimRL.report --out ../../artifacts/stim_rl_2026-10-02
```
