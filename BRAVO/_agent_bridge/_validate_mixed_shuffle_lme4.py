"""Part 2 continued: the page's own p (lme4 Wald) on the same made-up bands, in parallel."""
import os, sys, json, warnings, logging
warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
def _init():
    global Lmer, ctx, DF
    import warnings, logging; warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)
    sys.path.insert(0, "/usr/src/BRAVO")
    from pymer4.models import Lmer
    from modules.Biomarkers.routines.analytics import _rpy2_converter_ctx as ctx
    DF = pd.read_pickle("/usr/src/BRAVO/_agent_bridge/_mm_df.pkl")
def one(xb):
    d = DF.copy(); d["band_power"] = xb
    try:
        with ctx():
            m = Lmer("pain_high ~ band_power + (1|cluster)", data=d, family="binomial"); m.fit(summarize=False)
        w = [str(v) for v in (getattr(m, "warnings", None) or [])]
        bad = any(("failed to converge" in s.lower()) or ("unidentifiable" in s.lower()) for s in w)
        return float(m.coefs.loc["band_power"]["P-val"]), bad
    except Exception:
        return float("nan"), True
if __name__ == "__main__":
    for phi in sys.argv[1:]:
        B = np.load(f"/usr/src/BRAVO/_agent_bridge/_mm_bands_{phi}.npy")
        with ProcessPoolExecutor(int(os.environ.get("NPROC", "24")), mp_context=mp.get_context("spawn"), initializer=_init) as ex:
            out = list(ex.map(one, list(B), chunksize=8))
        p = np.array([a for a, _ in out]); bad = np.array([b for _, b in out])
        ok = np.isfinite(p) & ~bad
        print(json.dumps({"lag1": phi, "records": len(B), "converged": int(ok.sum()),
                          "page_wald_false_p_le_0.05": round(float(np.mean(p[ok] <= 0.05)), 4)}), flush=True)
