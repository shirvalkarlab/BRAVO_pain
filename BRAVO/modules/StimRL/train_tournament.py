"""Train and score every model on the same data: the tournament.

    cd BRAVO/modules && ~/.venvs/bravo-stim-rl/bin/python -m StimRL.train_tournament --sanity
    cd BRAVO/modules && ~/.venvs/bravo-stim-rl/bin/python -m StimRL.train_tournament \
        --variants delta level worst_site --seeds 0 1 2 --steps 5000

Deep offline RL (d3rlpy, on the Apple GPU through `device="mps:0"`):
  BC       behaviour cloning: copies what clinicians chose (the baseline every RL model must beat)
  CQL      conservative Q-learning: lowers the value of settings unlike those in the data
  IQL      implicit Q-learning: learns values only from settings in the data, then a weighted copy
  TD3+BC   an actor-critic pulled toward clinicians' choices by a copying term
Small-data models (`tabular.py`): the Q-table actor-critic (exploit and explore readings), the
same table with no look-ahead (gamma 0, a contextual bandit), and the Gaussian-process bandit.
References: keep the current setting; clinicians' most common choice per state; random settings.

Scores (`validation.py`) come from the long-term home record, which no model saw; held-out-visit
scores (d3rlpy's evaluators on visits left out of training) come from 5-fold cross-validation by
visit. Results go to `_agent_bridge/_stim_rl_data/results/` (gitignored: they describe a patient).
"""
from __future__ import annotations

import argparse
import json
import os
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from . import config as C
from . import data_pipeline as D
from . import tabular as T
from . import validation as V

RESULTS = os.path.join(D.DEFAULT_DATA_DIR, "results")
DEEP_ALGOS = ("BC", "CQL", "IQL", "TD3+BC")


def device() -> str:
    import torch
    return "mps:0" if torch.backends.mps.is_available() else "cpu:0"


def make_algo(name: str, *, gamma: float, seed: int, dev: str):
    import d3rlpy
    from d3rlpy.models.encoders import VectorEncoderFactory
    enc = VectorEncoderFactory(hidden_units=[64, 64])
    common = dict(batch_size=64)
    if name == "BC":
        return d3rlpy.algos.BCConfig(encoder_factory=enc, learning_rate=1e-3, **common).create(device=dev)
    if name == "CQL":
        return d3rlpy.algos.CQLConfig(actor_encoder_factory=enc, critic_encoder_factory=enc, gamma=gamma,
                                      conservative_weight=5.0, n_action_samples=10,
                                      actor_learning_rate=1e-4, critic_learning_rate=3e-4,
                                      **common).create(device=dev)
    if name == "IQL":
        return d3rlpy.algos.IQLConfig(actor_encoder_factory=enc, critic_encoder_factory=enc,
                                      value_encoder_factory=enc, gamma=gamma, expectile=0.7,
                                      weight_temp=3.0, **common).create(device=dev)
    if name == "TD3+BC":
        return d3rlpy.algos.TD3PlusBCConfig(actor_encoder_factory=enc, critic_encoder_factory=enc,
                                            gamma=gamma, alpha=2.5, **common).create(device=dev)
    raise ValueError(name)


def _snapshot(algo):
    import torch
    out = {}
    for mname, m in vars(algo.impl.modules).items():
        if isinstance(m, torch.nn.Module):
            for pname, p in m.named_parameters():
                if p.requires_grad:
                    out[f"{mname}.{pname}"] = p.detach().to("cpu").clone()
    return out


def sanity_check(n_steps: int = 5) -> dict:
    """The Apple GPU is present, every algorithm's tensors live on it, and 5 updates move the
    weights of every trainable network with finite losses (gradients flow end to end)."""
    import torch
    assert torch.backends.mps.is_available() is True, "Apple GPU (MPS) not available"
    db, tr, _ = D.load(variant="delta")
    ds = tr.mdp_dataset()
    report = {"mps_available": True, "device": device(), "transitions": int(ds.transition_count)}
    for name in DEEP_ALGOS:
        algo = make_algo(name, gamma=0.9, seed=0, dev=device())
        algo.build_with_dataset(ds)
        devs = {str(p.device) for m in vars(algo.impl.modules).values() if isinstance(m, torch.nn.Module)
                for p in m.parameters()}
        assert devs == {"mps:0"}, f"{name}: parameters on {devs}"
        before = _snapshot(algo)
        losses = []
        rng = np.random.default_rng(0)
        for _ in range(n_steps):
            batch = ds.sample_transition_batch(64)
            losses.append({k: float(v) for k, v in algo.update(batch).items()})
        after = _snapshot(algo)
        moved = {k: bool((after[k] - before[k]).abs().max() > 0) for k in before}
        # target networks are copies updated slowly or not at all in 5 steps; every other one must move
        stuck = [k for k, v in moved.items() if not v and "targ" not in k]
        finite = all(np.isfinite(v) for l in losses for v in l.values())
        assert finite, f"{name}: non-finite loss {losses}"
        assert not stuck, f"{name}: no gradient reached {stuck}"
        report[name] = {"params_checked": len(moved), "params_moved": int(sum(moved.values())),
                        "params_not_moved": sorted(k for k, v in moved.items() if not v),
                        "first_loss": losses[0], "last_loss": losses[-1]}
    return report


# ---- wrappers so every model is scored by the same code -------------------------------------------
def deep_fns(algo, name):
    pol = lambda o: algo.predict(np.asarray(o, np.float32))
    q = None if name == "BC" else (lambda o, a: algo.predict_value(np.asarray(o, np.float32),
                                                                   np.asarray(a, np.float32)))
    return pol, q


def heldout_scores(name, tr, *, gamma, seed, steps, dev, n_folds=5) -> dict:
    """5-fold cross-validation by visit with d3rlpy's evaluators on the left-out visits."""
    from d3rlpy.metrics import (TDErrorEvaluator, AverageValueEstimationEvaluator,
                                InitialStateValueEstimationEvaluator, ContinuousActionDiffEvaluator)
    visits = sorted(set(tr.episode_visit))
    rng = np.random.default_rng(seed)
    rng.shuffle(visits)
    folds = [visits[i::n_folds] for i in range(n_folds)]
    rows = []
    for k, test in enumerate(folds):
        train = [v for v in visits if v not in test]
        algo = make_algo(name, gamma=gamma, seed=seed, dev=dev)
        ds_tr, ds_te = tr.mdp_dataset(train), tr.mdp_dataset(test)
        algo.fit(ds_tr, n_steps=steps, n_steps_per_epoch=steps, show_progress=False,
                 save_interval=10 ** 9, experiment_name=f"cv_{name}_{seed}_{k}", with_timestamp=False,
                 logger_adapter=_null_logger())
        r = {"action_diff": ContinuousActionDiffEvaluator(ds_te.episodes)(algo, ds_te)}
        if name != "BC":
            r["td_error"] = TDErrorEvaluator(ds_te.episodes)(algo, ds_te)
            r["avg_value"] = AverageValueEstimationEvaluator(ds_te.episodes)(algo, ds_te)
            r["initial_state_value"] = InitialStateValueEstimationEvaluator(ds_te.episodes)(algo, ds_te)
        rows.append(r)
    return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}


def _null_logger():
    from d3rlpy.logging import NoopAdapterFactory
    return NoopAdapterFactory()


def run_deep(name, variant, seed, steps, gamma, dev, *, cv=True) -> dict:
    import d3rlpy
    d3rlpy.seed(seed)
    db, tr, _ = D.load(variant=variant)
    vals = D.validation_sets(db, tr.observations)
    algo = make_algo(name, gamma=gamma, seed=seed, dev=dev)
    t0 = time.time()
    algo.fit(tr.mdp_dataset(), n_steps=steps, n_steps_per_epoch=steps, show_progress=False,
             save_interval=10 ** 9, experiment_name=f"{name}_{variant}_{seed}", with_timestamp=False,
             logger_adapter=_null_logger())
    train_s = time.time() - t0
    pol, q = deep_fns(algo, name)
    res = V.evaluate_all(name, pol, vals, q=q, seed=seed)
    res.update(variant=variant, seed=seed, gamma=gamma, steps=steps, train_s=round(train_s, 1), device=dev,
               n_transitions=int(len(tr.transitions)))
    rec = V.recommend(pol, {c: D.latest_state(db, c, tr.observations) for c in C.CONTACT_LEVELS}, q=q)
    res["recommendation"] = rec.to_dict(orient="records")
    if cv:
        d3rlpy.seed(seed)
        res["heldout"] = heldout_scores(name, tr, gamma=gamma, seed=seed, steps=steps, dev=dev)
    return res


def run_small(variant, seed) -> list:
    """The table and GP models are deterministic given the data, so they run once (seed 0)."""
    db, tr, _ = D.load(variant=variant)
    vals = D.validation_sets(db, tr.observations)
    out = []
    latest = {c: D.latest_state(db, c, tr.observations) for c in C.CONTACT_LEVELS}
    models = [("QTable-AC (exploit)", T.TabularActorCritic(gamma=0.5, seed=seed), "exploit"),
              ("QTable-AC (explore)", T.TabularActorCritic(gamma=0.5, seed=seed), "explore"),
              ("QTable bandit (gamma 0)", T.TabularActorCritic(gamma=0.0, seed=seed), "exploit"),
              ("Clinician mode (table)", T.TabularActorCritic(gamma=0.0, beta=0.0, temperature=1e9, seed=seed), "exploit"),
              ("GP bandit", T.GPBandit(seed=seed), "exploit")]
    for name, m, mode in models:
        m.fit(tr.transitions)
        pol = (lambda mm, md: (lambda o: mm.policy(o, md)))(m, mode)
        res = V.evaluate_all(name, pol, vals, q=m.q, seed=seed)
        res.update(variant=variant, seed=seed, device="cpu", n_transitions=int(len(tr.transitions)))
        res["recommendation"] = V.recommend(pol, latest, q=m.q).to_dict(orient="records")
        out.append(res)
    const = V.make_constant_policy(tr.transitions)
    for name, pol in [("Keep current setting", V.stay_policy), ("Random setting", V.make_random_policy(seed)),
                      (f"Most common setting {const.setting}", const)]:
        res = V.evaluate_all(name, pol, vals, seed=seed)
        res.update(variant=variant, seed=seed, device="cpu")
        out.append(res)
    return out


def run_heldout_value(name, variant, seed, steps, gamma, dev) -> dict:
    """The clinic-sheet held-out test (`validation.heldout_visit_value_rank`) for one deep model."""
    import d3rlpy
    _, tr, _ = D.load(variant=variant)

    cache = {}

    def fit(train_tr):
        visits = sorted(set(train_tr["visit"]))
        key = tuple(visits)
        if key in cache:                       # the decomposition reuses the same five fits
            return cache[key]
        d3rlpy.seed(seed)
        algo = make_algo(name, gamma=gamma, seed=seed, dev=dev)
        algo.fit(tr.mdp_dataset(visits), n_steps=steps, n_steps_per_epoch=steps, show_progress=False,
                 save_interval=10 ** 9, experiment_name=f"hv_{name}_{variant}_{seed}", with_timestamp=False,
                 logger_adapter=_null_logger())
        cache[key] = lambda o, a: algo.predict_value(np.asarray(o, np.float32), np.asarray(a, np.float32))
        return cache[key]

    r = V.heldout_visit_value_rank(fit, tr.transitions, seed=seed)
    r["decomposition"] = V.switch_gain_decomposition(fit, tr.transitions, seed=seed, n_perm=500)
    r.update(model=name, variant=variant, seed=seed, steps=steps)
    return r


def _save(res, fname):
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, fname), "w") as f:
        json.dump(res, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sanity", action="store_true")
    ap.add_argument("--variants", nargs="+", default=list(D.REWARD_VARIANTS))
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--algos", nargs="+", default=list(DEEP_ALGOS))
    ap.add_argument("--steps", type=int, default=5000)
    ap.add_argument("--gamma", type=float, default=0.5)
    ap.add_argument("--no-cv", action="store_true")
    ap.add_argument("--small-only", action="store_true")
    ap.add_argument("--heldout-value", action="store_true",
                    help="only the clinic held-out switch-gain test for the value-based deep models")
    a = ap.parse_args()
    if a.heldout_value:
        for v in a.variants:
            for s in a.seeds:
                for name in [x for x in a.algos if x != "BC"]:
                    r = run_heldout_value(name, v, s, a.steps, a.gamma, device())
                    _save(r, f"heldout_value_{name.replace('+', 'p')}_{v}_{s}.json")
                    print(name, v, s, {k: round(x, 3) for k, x in r.items() if isinstance(x, float)},
                          {k: round(x, 3) for k, x in r["decomposition"].items() if isinstance(x, float)}, flush=True)
        return
    if a.sanity:
        rep = sanity_check()
        _save(rep, "sanity_check.json")
        print(json.dumps(rep, indent=1, default=str))
        return
    dev = device()
    for v in a.variants:
        for s in a.seeds:
            if s == a.seeds[0]:
                for r in run_small(v, s):
                    slug = "".join(ch if ch.isalnum() else "_" for ch in r["model"])[:40]
                    _save(r, f"small_{slug}_{v}_{s}.json")
            if a.small_only:
                continue
            for name in a.algos:
                t0 = time.time()
                r = run_deep(name, v, s, a.steps, a.gamma, dev, cv=not a.no_cv)
                _save(r, f"deep_{name.replace('+', 'p')}_{v}_{s}.json")
                print(f"{name:7s} {v:10s} seed {s}: rho_dist_change {r['rho_dist_change']:+.3f} "
                      f"(p_shift {r['p_dist_change_shift']:.3f}) rho_adv {r['rho_adv']:+.3f} "
                      f"near-far change {r['near_minus_far_change']:+.2f} risk {r['risk_mean']:.3f} "
                      f"past-limit {r['share_past_limit']:.2f}  [{time.time() - t0:.0f} s]", flush=True)


if __name__ == "__main__":
    main()
