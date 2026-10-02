# StimRL: offline reinforcement learning for stimulation settings (research only)

**On no page today.** Nothing here is called by the server or shown in the browser, and nothing
writes to the device. It is a research comparison, run by hand on the Mac, separate from Stim
Optimizer (which uses Bayesian optimisation).

## What it does

It asks: from what the patient reported at each step of every visit sheet, can a learning
model recommend a rate, current per side and pulse width per side that would lower pain, and does
its recommendation agree with how the patient actually felt on long-term settings at home?

* **Training data:** every rated step of the in-clinic and at-home visit sheets, pooled (the PI,
  2026-10-02). One visit is one episode. Unrated steps never count as pain data (decision 351).
  No REDCap value enters training.
* **State:** the seven pain sites (carried forward within a visit), their mean and worst, the
  side-effect grade, the setting in force, the Left contact the next setting uses, at home or not.
  No date or clock time (decision 196).
* **Action:** the next setting: rate, Left and Right current, Left and Right pulse width.
  Contacts are not chosen by the model; it recommends a setting **for** a contact, and never pools
  two contacts into one recommendation (decision 74).
* **Reward (three versions, compared):** `delta` (drop in mean pain from the last step), `level`
  (drop below the visit's first rating) and `worst_site` (half `level`, half the drop in the worst
  site). All subtract the side-effect cost (0 / 1 / 2 points, Stim Optimizer's ladder), subtract up
  to 2 points between 4.0 mA and the 4.5 mA ceiling, and end the episode with -10 points on a
  moderate or worse side effect or a setting past a limit.
* **Validation:** the long-term setting periods since implant with at least 3 REDCap home reports
  (52 periods, 563 reports in the 2026-10-02 snapshot), reports on visit days left out. Six REDCap
  items are put on the 0-10 scale and averaged (nrs, vas, left leg, back, McGill total, relief
  reversed).

## Models

| model | what it is |
|---|---|
| BC | copies clinicians' choices (the baseline any RL model must beat) |
| CQL | conservative Q-learning: marks down settings unlike those in the data |
| IQL | implicit Q-learning: values only settings in the data, then a weighted copy |
| TD3+BC | actor-critic pulled toward clinicians' choices |
| Q-table actor-critic | the critic is a table over 18 state cells x 72 setting cells; the actor is a table of probabilities weighted by clinicians' frequencies and a pessimistic value; read as `exploit` (keep) or `explore` (test next) |
| Q-table bandit | the same table, one step ahead only (gamma 0) |
| GP bandit | Gaussian process on state and setting, one step ahead (the Stim Optimizer family) |
| AgentDB arm | the models the `agentdb-reinforcementlearning` skill recommends; see `agentdb_arm/README.md` |
| references | keep the setting in force; clinicians' most common setting per state; random |

## Files

* `export_snapshot.py`: in the container, writes the three tables to `_agent_bridge/_stim_rl_data/` (gitignored).
* `config.py`: every limit, with the module it is copied from (tests check they agree).
* `data_pipeline.py`: SQLAlchemy database, reward, safety, state and action encoding, d3rlpy `MDPDataset`, validation set.
* `tabular.py`, `train_tournament.py`, `validation.py`, `report.py`.

## Running

```bash
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 300 --wait 300 \
  "python3 -B modules/StimRL/export_snapshot.py"
cd BRAVO/modules
~/.venvs/bravo-stim-rl/bin/python -m pytest StimRL/tests -q -W ignore -p no:cacheprovider
~/.venvs/bravo-stim-rl/bin/python -m StimRL.train_tournament --sanity
~/.venvs/bravo-stim-rl/bin/python -m StimRL.train_tournament --variants delta --seeds 0 1 2 --steps 5000
~/.venvs/bravo-stim-rl/bin/python -m StimRL.report --out ../../artifacts/stim_rl_2026-10-02
```

The venv: `uv venv --python 3.12 ~/.venvs/bravo-stim-rl` then
`uv pip install torch d3rlpy sqlalchemy pymysql pandas numpy scipy scikit-learn matplotlib pytest gymnasium`.
These tests are not part of either container test set (they need PyTorch on the Mac).

Never load a d3rlpy file of unknown origin: `d3rlpy.load_learnable` runs `pickle.load`.
