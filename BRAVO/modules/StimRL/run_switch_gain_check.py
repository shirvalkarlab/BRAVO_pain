"""Run the pre-stated switch-gain decomposition (validation.switch_gain_decomposition) for the
small models over 20 five-part splits by visit; writes results/switch_gain_check_small.json.

    cd BRAVO/modules && ~/.venvs/bravo-stim-rl/bin/python -m StimRL.run_switch_gain_check
"""
import json
import os

import numpy as np

from . import data_pipeline as D
from . import tabular as T
from . import validation as V

MODELS = {"QTable-AC": lambda: T.TabularActorCritic(gamma=0.5),
          "QTable bandit (gamma 0)": lambda: T.TabularActorCritic(gamma=0.0),
          "GP bandit": lambda: T.GPBandit()}


def main(seeds=range(20), n_perm=500):
    out = {}
    for var in D.REWARD_VARIANTS:
        _, tr, _ = D.load(variant=var)
        for name, mk in MODELS.items():
            if name == "GP bandit":
                ss = list(seeds)[:3]                       # the GP fit is slow; 3 splits
            else:
                ss = list(seeds)
            rows = [V.switch_gain_decomposition(lambda d, mk=mk: mk().fit(d).q, tr.transitions,
                                                seed=s, n_perm=n_perm) for s in ss]
            agg = {k: float(np.median([r[k] for r in rows])) for k in rows[0] if not k.startswith("supports")}
            agg["share_of_splits_supporting"] = float(np.mean([r["supports_recommendations"] for r in rows]))
            agg["share_supporting_after_baseline"] = float(np.mean([r["supports_after_baseline"] for r in rows]))
            agg["n_splits"] = len(rows)
            out[f"{name}|{var}"] = agg
            print(f"{var:10s} {name:24s}", {k: round(v, 3) for k, v in agg.items()}, flush=True)
    path = os.path.join(D.DEFAULT_DATA_DIR, "results", "switch_gain_check_small.json")
    json.dump(out, open(path, "w"), indent=1)


if __name__ == "__main__":
    main()
