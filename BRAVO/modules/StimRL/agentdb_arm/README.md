# AgentDB arm of the offline RL study

The PI asked to "use the agentdb skill to choose appropriate models and follow its recipe for
training". The skill (`~/.claude/skills/agentdb-reinforcementlearning/SKILL.md`) says which
models suit which problem and gives a three-step recipe. This folder follows both. AgentDB's own
code does none of the training, for the reasons below, so the models are written in PyTorch.

## What AgentDB itself provides (checked 2026-10-02, npm tarballs read with `rg`)

- **Today's AgentDB (3.0.0-alpha.20) has no plugin templates.** Its command line has no
  `create-plugin` or `list-templates`.
- **1.0.7 shipped the plugins the skill describes, but they do not train.**
  `dist/plugins/implementations/`:
  - `decision-transformer.js`: `train()` reads its data from `getAllExperiences()`, which
    returns an empty list every time ("For now, return empty"). So it either throws "Not enough
    experiences" or trains on nothing. Even with data, `backward()` updates only the output
    layer's bias ("Simplified Adam update").
  - `sarsa.js`: `train()` returns `loss: 0` and only decays epsilon. Its Q-table is keyed on
    the first 10 state numbers rounded to 2 decimals.
  - `actor-critic.js`: `train()` returns `loss: 0`. Saving and loading are `console.log` only.
  - `reasoningbank/adapter/agentdb-adapter.js`: `adapter.train()` calls the plugin's
    `train()`, so it reaches the empty Decision Transformer above.
  - `mcp/learning/core/policy-optimizer.js`: a Q-table keyed on encoded state text. Its
    reported "improvements" are fixed strings ("+15%", "+20%", "+25%") chosen by the mean reward.
- **1.3.9 to 3.0.0-alpha.20 (`controllers/LearningSystem`) is a look-up table, not a model.**
  The state is a string. Values are stored under the exact key `state|action`. `trainBatch` uses
  the Q-learning target (best next value) for every session type, SARSA included. The "Decision
  Transformer" score is the average reward stored under that exact key. A 22-number state written
  as text never matches another state, so nothing carries over to a new state.
- **agentic-flow 1.10.2** `createAgentDBAdapter` imports `agentdb/reasoningbank/adapter/agentdb-adapter`.
  Only AgentDB 1.0.x has that path, but agentic-flow asks for `agentdb ^1.4.3`, which does not
  have it. Its `computeEmbedding` falls back to a hash of the text under `npx`, so "similar"
  experiences are not close in pain or setting.

None of this code was run, and none of the patient data went into it.

## What is here

- `models.py`:
  - The recipe's experience store, with the skill's confidence and success fields.
  - A split that holds out 20% of visits, by visit and never by row.
  - The recipe's step 3: retrieve the most similar successful experiences. Similarity is the
    cosine of the state vectors, not a hash.
  - The three models the skill points to:
    - **Decision Transformer**: the skill's pick for learning offline from logged data. It uses
      the skill's settings: context 20, width 128, 8 heads, 6 layers.
    - **SARSA**: the skill's conservative pick for safety-critical tasks.
    - **Actor-Critic**: the skill's pick for continuous settings. It uses the skill's settings:
      actor_lr 0.001, critic_lr 0.002, gamma 0.99, entropy_coef 0.01.
- `run_agentdb_arm.py`:
  - Runs one model type over the reward variants and seeds, using the recipe's training settings:
    epochs 100, batch 64, learning rate 0.001, validation split 0.2.
  - Scores each run with `validation.evaluate_policy` and writes
    `_agent_bridge/_stim_rl_data/results/agentdb_<model>_<variant>_<seed>.json`.
  - `--model retrieval` scores the recipe's step 3 on its own.
- `test_agentdb_arm.py`: the tests. They use small made-up data, not patient data.

Run (from `BRAVO/modules`, one process per model type):

    ~/.venvs/bravo-stim-rl/bin/python -m StimRL.agentdb_arm.run_agentdb_arm --model sarsa
    ~/.venvs/bravo-stim-rl/bin/python -m pytest StimRL/agentdb_arm -q -p no:cacheprovider

## Choices the skill leaves open

- The model that gets scored is the one trained on 80% of visits, as in the recipe. A different
  seed gives a different held-out set of visits.
- A visit's last step has no next step. Its value target is the reward alone.
- SARSA uses 36 coarse setting groups: rate 4 x Left current 3 x Right current 3.
  - It recommends only groups that the training data used at least 3 times.
  - A recommended group becomes the average of the settings actually used in it, so it never
    proposes a setting nobody has tried.
- Actor-Critic learns from logged data only. The critic learns Q(s, a) from the next logged
  step. The actor copies the logged settings, weighted by exp(advantage) and capped at 20. This
  is advantage-weighted actor-critic.
- Decision Transformer:
  - A long-term home period has no history within a visit, so the model sees one step. It aims
    for the 90th percentile of the returns-to-go seen in training.
  - The learning rate warms up over 10 epochs. Without warm-up, at the recipe's 0.001, one of 9
    runs (level reward, seed 1) collapsed. It gave the same corner setting for every state, and
    its training loss stayed at 0.81.
- The state size is read from the data, never written into the code.
