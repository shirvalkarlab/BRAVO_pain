"""Does pain at one current depend on whether the current was reached going up or coming down?
(the PI, 2026-09-25: the carry-over test.) Free of the database; the runner feeds it the clinic
sheets' steps and the stored ladder points.

WHAT IS COMPARED. Within one visit, a current reached by a rise (from a lower current) and the
same current reached by a fall (from a higher one), with the rate, pulse widths, contacts and the
other side's current all unchanged. If stimulation keeps working for a while after it is turned
down, pain on the way down sits lower than pain at the same current on the way up.

THE SHEETS WRITE A STEP TWICE. The ladder of 2026-09-16 writes each setting as it is reached and
again a minute later while it is held; a held reading belongs to the step it continues. A run of
identical settings is one BLOCK, its leg is the direction of the change into it, and a block's
reading for a pain site is its LAST rating of that site (the longest exposure). The change between
a block's first and last rating is reported on its own (`held_changes`): pain moving within
minutes at one current.

THE CONFOUND THIS DESIGN CANNOT REMOVE, AND HOW IT IS READ. When the way down always follows the
way up, "down" also means "later in the visit", and pain drifting over a visit reads exactly like
carry-over. The two are told apart by the ORDER: carry-over lowers the falling reading whichever
leg came first; drift over the visit lowers it when the fall came later and RAISES it when the fall
came first. So every summary is given for the two orders separately (`by_order`).
"""
import numpy as np
import pandas as pd

#: Currents within this of each other are one current.
MATCH_MA = 0.05
#: The clinic sheets' three most rated sites (the overall item is the NRS).
ITEMS = ("overall", "left_leg", "back")
ITEM_WORDS = {"overall": "overall (NRS)", "left_leg": "left leg", "back": "back"}
ORDERS = ("falling after rising", "falling before rising")


def visit_order(t_s, row_index):
    """The time order of one visit's steps. A step with no time written takes the time of the step
    above it on the sheet, so it keeps its place in the sheet's own order."""
    t = np.asarray(t_s, float)
    r = np.asarray(row_index, float)
    by_row = np.argsort(r, kind="stable")
    filled = t[by_row].copy()
    last = np.nan
    for i in range(filled.size):
        if np.isfinite(filled[i]):
            last = filled[i]
        else:
            filled[i] = last
    first = np.flatnonzero(np.isfinite(filled))
    if first.size:
        filled[:first[0]] = filled[first[0]]
    else:
        filled[:] = 0.0
    rank = np.empty(r.size)
    rank[by_row] = np.arange(r.size)
    t_full = np.empty(t.size)
    t_full[by_row] = filled
    return np.lexsort((rank, t_full))


def _same(a, b):
    if not np.isfinite(a) and not np.isfinite(b):
        return True
    return bool(np.isfinite(a) and np.isfinite(b) and abs(a - b) < MATCH_MA / 2)


def blocks(amp_L, amp_R, cfg):
    """For steps in time order: the block each belongs to (a run of identical settings), and per
    side the leg of that block -- "rising" or "falling" when that side alone changed into it with
    the rate, pulse widths and contacts (`cfg`) unchanged, otherwise None -- with the current it
    came from."""
    aL, aR = np.asarray(amp_L, float), np.asarray(amp_R, float)
    n = aL.size
    out = dict(block=np.zeros(n, int), held=np.zeros(n, bool),
               leg_Left=[None] * n, leg_Right=[None] * n,
               from_Left=np.full(n, np.nan), from_Right=np.full(n, np.nan))
    for i in range(1, n):
        sL, sR = _same(aL[i], aL[i - 1]), _same(aR[i], aR[i - 1])
        if cfg[i] == cfg[i - 1] and sL and sR:
            out["held"][i] = True
            out["block"][i] = out["block"][i - 1]
            for side in ("Left", "Right"):
                out[f"leg_{side}"][i] = out[f"leg_{side}"][i - 1]
                out[f"from_{side}"][i] = out[f"from_{side}"][i - 1]
            continue
        out["block"][i] = out["block"][i - 1] + 1
        if cfg[i] != cfg[i - 1]:
            continue
        for side, a, other_same in (("Left", aL, sR), ("Right", aR, sL)):
            if not other_same or not (np.isfinite(a[i]) and np.isfinite(a[i - 1])):
                continue
            out[f"leg_{side}"][i] = "rising" if a[i] > a[i - 1] else "falling"
            out[f"from_{side}"][i] = a[i - 1]
    return out


def step_frame(steps):
    """One row per step, in time order within each visit, with its block and legs. `steps` has
    `visit`, `t_s`, `row_index`, `amp_L`, `amp_R`, `cfg`, `setting` and the pain sites."""
    parts = []
    for visit, g in steps.groupby("visit", sort=False):
        g = g.reset_index(drop=True)
        o = visit_order(g["t_s"].to_numpy(float), g["row_index"].to_numpy(float))
        g = g.iloc[o].reset_index(drop=True)
        t = g["t_s"].to_numpy(float).copy()
        for i in range(t.size):                      # a missing time is the step above's
            if not np.isfinite(t[i]):
                t[i] = t[i - 1] if i else np.nan
        g["t_s"] = t
        b = blocks(g["amp_L"].to_numpy(float), g["amp_R"].to_numpy(float), g["cfg"].tolist())
        g["block"] = [f"{visit}#{k}" for k in b["block"]]
        for k in ("held", "leg_Left", "leg_Right", "from_Left", "from_Right"):
            g[k] = b[k]
        parts.append(g)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _key(v):
    return "none" if not np.isfinite(v) else int(round(float(v) / MATCH_MA))


def leg_pairs(long, item):
    """Each current reached both by a rise and by a fall within one visit, on one side, with
    everything else unchanged: the pain site's reading on each leg (the mean over blocks when a
    leg was visited more than once) and the difference, falling minus rising."""
    rows = []
    for side, other in (("Left", "Right"), ("Right", "Left")):
        amp, oth = f"amp_{side[0]}", f"amp_{other[0]}"
        d = long[long[f"leg_{side}"].isin(["rising", "falling"]) & np.isfinite(long[item].astype(float))]
        if d.empty:
            continue
        last = d.groupby("block", sort=False).tail(1)
        start = long.groupby("block")["t_s"].min()
        for _k, g in last.groupby([last["visit"], last[amp].map(_key), last[oth].map(_key), last["cfg"]], sort=False):
            up, dn = g[g[f"leg_{side}"] == "rising"], g[g[f"leg_{side}"] == "falling"]
            if up.empty or dn.empty:
                continue
            t_up, t_dn = start[up["block"]].min(), start[dn["block"]].min()
            rows.append(dict(visit=g["visit"].iloc[0], setting=g["setting"].iloc[0], side=side,
                             current_mA=float(g[amp].iloc[0]),
                             other_mA=float(g[oth].iloc[0]) if np.isfinite(g[oth].iloc[0]) else None,
                             cfg=g["cfg"].iloc[0], rising=float(up[item].astype(float).mean()),
                             falling=float(dn[item].astype(float).mean()),
                             diff=float(dn[item].astype(float).mean() - up[item].astype(float).mean()),
                             n_rising=int(len(up)), n_falling=int(len(dn)),
                             from_mA=float(dn[f"from_{side}"].mean()),
                             falling_first=bool(t_dn < t_up), minutes_apart=float(abs(t_dn - t_up) / 60.0)))
    return pd.DataFrame(rows)


def paired_summary(diffs, units, *, n_boot=2000, seed=0, max_exact=12, n_flip=10000):
    """The mean difference over pairs with a 95% interval resampling whole units (visits), the
    counts lower / higher / the same, and a sign-flip p that flips all of a unit's pairs together
    (exact up to `max_exact` units)."""
    d = np.asarray(diffs, float)
    u = np.asarray(units)
    out = dict(n_pairs=int(d.size), n_visits=int(len(set(u.tolist()))),
               n_lower=int((d < 0).sum()), n_higher=int((d > 0).sum()), n_same=int((d == 0).sum()),
               mean=None, lo=None, hi=None, p_sign_flip=None)
    if d.size == 0:
        return out
    out["mean"] = float(d.mean())
    uu = np.unique(u)
    idx = [np.flatnonzero(u == x) for x in uu]
    if uu.size >= 2:
        rng = np.random.default_rng(seed)
        bs = [d[np.concatenate([idx[j] for j in rng.integers(0, uu.size, uu.size)])].mean()
              for _ in range(int(n_boot))]
        out["lo"], out["hi"] = (float(v) for v in np.percentile(bs, [2.5, 97.5]))
    sums = np.array([d[i].sum() for i in idx])
    obs = abs(sums.sum())
    if uu.size <= max_exact:
        signs = np.array(np.meshgrid(*[[-1.0, 1.0]] * uu.size)).reshape(uu.size, -1).T
    else:
        signs = np.random.default_rng(seed + 1).choice([-1.0, 1.0], size=(int(n_flip), uu.size))
    stat = np.abs(signs @ sums)
    out["p_sign_flip"] = float(np.mean(stat >= obs - 1e-12))
    return out


def by_order(pairs, *, n_boot=2000, seed=0):
    """`paired_summary` over every pair and over each order separately."""
    out = {}
    if pairs is None or len(pairs) == 0:
        return {k: paired_summary([], []) for k in ("all",) + ORDERS}
    out["all"] = paired_summary(pairs["diff"], pairs["visit"], n_boot=n_boot, seed=seed)
    for name, first in zip(ORDERS, (False, True)):
        g = pairs[pairs["falling_first"] == first]
        out[name] = paired_summary(g["diff"], g["visit"], n_boot=n_boot, seed=seed)
    return out


def held_changes(long, item):
    """Each block rated at least twice for the pain site: its last rating minus its first, the
    minutes between them, and whether stimulation was on (either side above 0 mA)."""
    rows = []
    d = long[np.isfinite(long[item].astype(float))]
    for blk, g in d.groupby("block", sort=False):
        if len(g) < 2:
            continue
        a, b = g.iloc[0], g.iloc[-1]
        on = bool(np.nan_to_num(float(a["amp_L"])) > 0 or np.nan_to_num(float(a["amp_R"])) > 0)
        rows.append(dict(visit=a["visit"], setting=a["setting"], block=blk,
                         amp_L=float(a["amp_L"]), amp_R=float(a["amp_R"]), on=on,
                         first=float(a[item]), last=float(b[item]), change=float(b[item]) - float(a[item]),
                         minutes=float((b["t_s"] - a["t_s"]) / 60.0), n_readings=int(len(g))))
    return pd.DataFrame(rows)


def ladder_pairs(rp):
    """The same comparison on the device's ladder points (`three_source_run_points`): within one
    run, route, sensing pair and band, the settled band power at a current reached by a rise and at
    the same current reached by a fall, and the fall's power as a fraction of the rise's, minus 1.
    Rows the comparison refused, and bands measuring the stimulator, are left out."""
    if rp is None or len(rp) == 0:
        return pd.DataFrame()
    d = rp.copy()
    d["_pos"] = np.arange(len(d))
    pw = pd.to_numeric(d["settled_band_power_device_units"], errors="coerce")
    ok = (np.isfinite(pw) & (d["why_not_used"].fillna("") == "") & d["leg"].isin(["rising", "falling"])
          & ~d["band_is_measuring_the_stimulator"].eq(True))
    d = d[ok].assign(_pw=pw[ok], _cur=d.loc[ok, "current_mA"].astype(float).map(_key))
    rows = []
    keys = ["source", "run", "sensing_contact", "band_centre_hz", "_cur"]
    for k, g in d.groupby(keys, sort=False):
        up, dn = g[g["leg"] == "rising"], g[g["leg"] == "falling"]
        if up.empty or dn.empty:
            continue
        r_up, r_dn = float(up["_pw"].mean()), float(dn["_pw"].mean())
        rows.append(dict(source=k[0], run=k[1], sensing_contact=k[2], band_centre_hz=float(k[3]),
                         current_mA=float(g["current_mA"].iloc[0]), rising=r_up, falling=r_dn,
                         relative_diff=r_dn / r_up - 1.0 if r_up > 0 else float("nan"),
                         falling_first=bool(dn["_pos"].min() < up["_pos"].min())))
    return pd.DataFrame(rows)


def _excludes_zero(s):
    return s.get("lo") is not None and s.get("hi") is not None and (s["lo"] > 0 or s["hi"] < 0)


def order_reading(summary):
    """`(kind, sentence)` from `by_order`: "carry-over" when the fall reads lower in BOTH orders
    with each interval below zero; "drift" when the sign follows the order and at least one
    interval excludes zero; "one order" when only one order occurs; otherwise "no difference"."""
    a, b = summary[ORDERS[0]], summary[ORDERS[1]]
    if not a.get("n_pairs") or not b.get("n_pairs"):
        return ("one order", "only one order occurs, so carry-over cannot be told apart from pain "
                             "drifting over the visit")
    if a["hi"] is not None and b["hi"] is not None and a["hi"] < 0 and b["hi"] < 0:
        return ("carry-over", "lower on the way down whichever leg came first, which is what "
                              "carry-over predicts")
    if (a["mean"] * b["mean"] < 0) and (_excludes_zero(a) or _excludes_zero(b)):
        return ("drift", "the sign follows the order (lower when the fall came later, higher when it "
                         "came first), which is what pain drifting over the visit produces, not carry-over")
    return ("no difference", "no difference that either order can tell apart from chance")
