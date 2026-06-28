import numpy as np
from sklearn import metrics

def vec_weighted_auc(use_score, y, W):
    perm = np.argsort(use_score, kind="mergesort")
    ss = use_score[perm]; ys = y[perm]
    Wp = W[:, perm].astype(float)
    pos_w = Wp * (ys == 1)[None, :]; neg_w = Wp * (ys == 0)[None, :]
    npos = pos_w.sum(1); nneg = neg_w.sum(1)
    gid = np.concatenate([[0], np.cumsum(np.diff(ss) > 0)]).astype(int)
    G = int(gid[-1]) + 1
    S = np.zeros((ss.size, G)); S[np.arange(ss.size), gid] = 1.0
    gpos = pos_w @ S; gneg = neg_w @ S
    cum_before = np.cumsum(gneg, axis=1) - gneg
    U = (gpos * (cum_before + 0.5 * gneg)).sum(1)
    auc = np.full(U.shape, np.nan)
    ok = (npos > 0) & (nneg > 0)
    auc[ok] = U[ok] / (npos[ok] * nneg[ok])
    return auc

rng = np.random.default_rng(0)
maxerr = 0.0; ntested = 0
for trial in range(300):
    N = int(rng.integers(12, 60))
    y = rng.integers(0, 2, N)
    if len(np.unique(y)) < 2:
        y[0] = 0; y[1] = 1
    score = rng.integers(0, 5, N).astype(float)
    w = rng.integers(0, 4, N)
    if w.sum() == 0: w[0] = 1
    yexp = np.repeat(y, w); sexp = np.repeat(score, w)
    if len(np.unique(yexp)) < 2:
        continue
    sk = metrics.roc_auc_score(yexp, sexp)
    mine = vec_weighted_auc(score, y, w[None, :].astype(float))[0]
    maxerr = max(maxerr, abs(sk - mine)); ntested += 1
print("VEC_AUC_CHECK tested=%d max_abs_err=%.3e" % (ntested, maxerr))
