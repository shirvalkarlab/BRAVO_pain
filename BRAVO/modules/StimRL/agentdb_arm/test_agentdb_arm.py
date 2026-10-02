"""Checks for the AgentDB-recipe arm, on a tiny synthetic dataset (no patient data).

    cd BRAVO/modules && ~/.venvs/bravo-stim-rl/bin/python -m pytest StimRL/agentdb_arm -q
"""
import numpy as np
import pytest

from StimRL.agentdb_arm import models as M


def synthetic(n_visits=8, steps=12, seed=0):
    """Visits whose reward is highest when the Left current (action[1]) matches state[0]."""
    rng = np.random.default_rng(seed)
    out = []
    for v in range(n_visits):
        s = rng.uniform(0, 1, M.STATE_DIM)
        for t in range(steps):
            a = rng.uniform(-1, 1, M.ACTION_DIM)
            r = 1.0 - abs(a[1] - (2 * s[0] - 1))
            s2 = rng.uniform(0, 1, M.STATE_DIM)
            out.append({"visit": f"v{v}", "state": s.tolist(), "action": a.tolist(), "reward": float(r),
                        "next_state": s2.tolist(), "done": False})
            s = s2
    return out


@pytest.fixture(scope="module")
def store():
    return M.ExperienceStore(synthetic())


def test_store_keeps_recipe_fields_and_visit_order(store):
    eps = store.episodes()
    assert len(eps) == 8 and all(len(e) == 12 for e in eps)
    r = store.records[0]
    assert r["confidence"] == (0.9 if r["reward"] > 0 else 0.5)
    assert r["success_count"] == int(r["reward"] > 0)


def test_done_splits_an_episode():
    ex = synthetic(n_visits=1, steps=6)
    ex[2]["done"] = True
    eps = M.ExperienceStore(ex).episodes()
    assert [len(e) for e in eps] == [3, 3]


def test_split_is_by_visit_never_by_row(store):
    tr, va = M.split_by_visit(store, 0.2, seed=1)
    assert len(va) == 2 and not set(tr) & set(va) and len(tr) + len(va) == 8


def test_sarsa_next_action_is_next_step_in_same_visit(store):
    t = store.transitions()
    assert np.allclose(t["a2"][0], store.records[1]["action"])
    assert t["end"][11] == 1.0 and t["end"][10] == 0.0


def test_retrieval_returns_most_similar_successful(store):
    q = store.records[5]["state"]
    m = store.retrieve(q, k=3)
    assert all(x["success_count"] == 1 for x in m)
    assert m[0]["similarity"] >= m[-1]["similarity"]


SMALL = {"decision_transformer": dict(context=5, embed_dim=32, n_heads=4, n_layers=2)}


@pytest.mark.parametrize("name", list(M.AGENTS))
def test_policy_actions_are_n_by_5_within_minus1_plus1(store, name):
    M.set_seed(0)
    agent = M.AGENTS[name](device="cpu", **SMALL.get(name, {}))
    agent.fit(store, epochs=5, batch_size=16, learning_rate=1e-3, seed=0, val=store)
    obs = np.random.default_rng(1).uniform(0, 1, (7, M.STATE_DIM)).astype(np.float32)
    a = agent.policy(obs)
    assert a.shape == (7, M.ACTION_DIM)
    assert np.all(a >= -1) and np.all(a <= 1)
    if getattr(agent, "q", None) is not None:
        assert agent.q(obs, a).shape == (7,)


def test_decision_transformer_training_loss_falls(store):
    M.set_seed(0)
    agent = M.DecisionTransformerAgent(device="cpu", **SMALL["decision_transformer"])
    h = agent.fit(store, epochs=30, batch_size=16, seed=0)["train_loss_history"]
    assert np.mean(h[-3:]) < np.mean(h[:3])


@pytest.mark.parametrize("name", ["sarsa", "actor_critic"])
def test_value_loss_falls_when_gamma_is_zero(store, name):
    """With look-ahead (gamma 0.99) the value targets grow as training spreads value back through
    a visit, so the squared error need not fall; with gamma 0 it is a plain regression and must."""
    M.set_seed(0)
    agent = M.AGENTS[name](device="cpu", gamma=0.0)
    h = agent.fit(store, epochs=30, batch_size=16, seed=0)["train_loss_history"]
    assert np.mean(h[-3:]) < 0.5 * np.mean(h[:3])


def test_actor_critic_policy_moves_toward_logged_settings(store):
    M.set_seed(0)
    agent = M.ActorCriticAgent(device="cpu")
    before = agent.eval_loss(store)["actor_mse"]
    agent.fit(store, epochs=30, batch_size=16, seed=0)
    assert agent.eval_loss(store)["actor_mse"] < before


def test_sarsa_only_recommends_cells_the_data_delivered(store):
    agent = M.SarsaAgent(device="cpu", min_support=3)
    agent.fit(store, epochs=5, batch_size=16, seed=0)
    a = agent.policy(np.random.default_rng(2).uniform(0, 1, (20, M.STATE_DIM)).astype(np.float32))
    assert np.all(agent.support[agent.bins.index(a)] >= 3)
