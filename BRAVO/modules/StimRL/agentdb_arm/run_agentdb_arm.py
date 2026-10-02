"""Run one model type over reward variants and seeds; score each run the study's one way.

    cd BRAVO/modules
    ~/.venvs/bravo-stim-rl/bin/python -m StimRL.agentdb_arm.run_agentdb_arm --model sarsa

Models: decision_transformer, sarsa, actor_critic, retrieval (the recipe's step 3 on its own).
Each run: load the stored experiences (recipe step 1), hold out 20% of visits (by visit), train
with the recipe's epochs 100, batch size 64, learning rate 0.001 (step 2), score on the long-term
home record with `validation.evaluate_policy`, compare with the retrieval suggestion (step 3) and
write `_agent_bridge/_stim_rl_data/results/agentdb_<model>_<variant>_<seed>.json`.
Everything stays on this machine.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time

import numpy as np

from StimRL import data_pipeline as D, validation as V
from StimRL.agentdb_arm import models as M

RESULTS = os.path.join(D.DEFAULT_DATA_DIR, "results")
RECIPE = {"epochs": 100, "batch_size": 64, "learning_rate": 1e-3, "validation_split": 0.2}


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    return x


def check_data(store, tr, val, *, expect_periods=None, expect_experiences=None):
    """Refuse to run on data that disagree with themselves. (A database read while another
    process rebuilt it once gave doubled rows with no error.)"""
    assert len(store) == len(tr.transitions), \
        f"experiences file has {len(store)} rows, the database gives {len(tr.transitions)}: regenerate one"
    assert store.state_dim == tr.observations.shape[1], "experiences file and database differ in state size"
    obs_dim = {len(o) for o in val["obs"]}
    assert obs_dim == {store.state_dim}, f"validation states have {obs_dim} numbers, training {store.state_dim}"
    assert val["epoch"].is_unique, "a long-term setting period appears twice in validation (doubled rows?)"
    if expect_periods is not None:
        assert len(val) == expect_periods, f"validation periods {len(val)} != {expect_periods}"
    if expect_experiences is not None:
        assert len(store) == expect_experiences, f"experiences {len(store)} != {expect_experiences}"


def run_one(model: str, variant: str, seed: int, *, loaded=None, n_perm=2000, device=None,
            expect_periods=None, expect_experiences=None) -> dict:
    t0 = time.time()
    db, _tr, val = loaded or D.load(variant=variant)
    with open(os.path.join(D.DEFAULT_DATA_DIR, f"experiences_{variant}.json")) as f:
        store = M.ExperienceStore(json.load(f))                       # recipe step 1
    check_data(store, _tr, val, expect_periods=expect_periods, expect_experiences=expect_experiences)
    train_v, held_v = M.split_by_visit(store, RECIPE["validation_split"], seed)
    train, held = store.subset(train_v), store.subset(held_v)
    M.set_seed(seed)
    ret_policy, ret_conf = M.retrieval_policy(train, k=10)            # recipe step 3

    if model == "retrieval":
        policy, q, fit = ret_policy, None, {"note": "no training: nearest successful stored experience"}
        cfg = {"k": 10}
    else:
        agent = M.AGENTS[model](device=device)
        fit = agent.fit(train, epochs=RECIPE["epochs"], batch_size=RECIPE["batch_size"],   # step 2
                        learning_rate=RECIPE["learning_rate"], seed=seed, val=held)
        policy, q, cfg = agent.policy, getattr(agent, "q", None), agent.cfg

    out = V.evaluate_policy(f"agentdb_{model}", policy, val, q=q, n_perm=n_perm)
    obs = np.stack(val["obs"].to_list()).astype(np.float32)
    a_model, a_ret = np.clip(policy(obs), -1, 1), ret_policy(obs)
    out["recipe_step3"] = {
        "rms_distance_model_vs_retrieved_action": float(np.mean(V.action_distance(a_model, a_ret))),
        "mean_retrieval_confidence": float(np.nanmean(ret_conf(obs))),
    }
    # how many different settings the model recommends across the 52 periods (1 = a constant)
    out["n_distinct_recommendations"] = int(len(np.unique(np.round(a_model, 3), axis=0)))
    rec = V.recommend(policy, {c: D.latest_state(db, c) for c in D.C.CONTACT_LEVELS}, q=q)
    assert len(rec) == len(D.C.CONTACT_LEVELS), f"recommendations for {len(rec)} contacts"
    out.update({
        "arm": "agentdb", "model_type": model, "reward_variant": variant, "seed": seed,
        "state_size": store.state_dim, "n_experiences": len(store),
        "recipe": RECIPE, "config": cfg,
        "n_train_visits": len(train_v), "n_heldout_visits": len(held_v),
        "n_train_experiences": len(train), "n_heldout_experiences": len(held),
        "heldout_visits": held_v,
        "train_loss": fit.get("train_loss"), "val_loss": fit.get("val_loss"),
        "training": {k: v for k, v in fit.items() if k not in ("train_loss", "val_loss")},
        "recommendation_by_contact": rec.to_dict(orient="records"),
        "device": str(getattr(locals().get("agent"), "device", "cpu")),
        "seconds_total": time.time() - t0,
    })
    return _clean(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(M.AGENTS) + ["retrieval"])
    ap.add_argument("--variants", nargs="+", default=list(D.REWARD_VARIANTS))
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--n-perm", type=int, default=2000)
    ap.add_argument("--device", default=None)
    ap.add_argument("--expect-periods", type=int, default=None,
                    help="refuse to run unless the validation set has exactly this many periods")
    ap.add_argument("--expect-experiences", type=int, default=None,
                    help="refuse to run unless there are exactly this many experiences")
    a = ap.parse_args()
    os.makedirs(RESULTS, exist_ok=True)
    for variant in a.variants:
        loaded = D.load(variant=variant)
        for seed in a.seeds:
            r = run_one(a.model, variant, seed, loaded=loaded, n_perm=a.n_perm, device=a.device,
                        expect_periods=a.expect_periods, expect_experiences=a.expect_experiences)
            path = os.path.join(RESULTS, f"agentdb_{a.model}_{variant}_{seed}.json")
            with open(path, "w") as f:
                json.dump(r, f, indent=1)
            print(f"{a.model} {variant} seed {seed}: rho_dist={r['rho_dist']} p_shift={r['p_dist_shift']} "
                  f"rho_q={r['rho_q']} train={r['train_loss']} val={r['val_loss']} "
                  f"{r['seconds_total']:.0f}s -> {path}", flush=True)


if __name__ == "__main__":
    main()
