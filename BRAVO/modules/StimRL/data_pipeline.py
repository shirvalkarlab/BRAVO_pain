"""Visit-sheet steps -> offline RL trajectories; long-term settings -> the validation set.

Runs on the Mac host (PyTorch, d3rlpy). Reads the snapshot `export_snapshot.py` wrote, through a
SQLAlchemy database (SQLite by default; any SQLAlchemy URL works), and builds:

* TRAINING: one episode per visit sheet, in-clinic and at-home pooled (the PI, 2026-10-02). Each
  step of an episode is one RATED step: the state is how the patient felt at that step (seven
  pain sites, the composite and worst site, the side-effect grade) plus the setting that produced
  it; the action is the setting of the next rated step; the reward is the change in symptoms it
  brought, minus side-effect cost and safety penalties. Unrated steps are exposure, never pain data
  (decision 351), so they never become a state or a reward. No REDCap value enters training.
* VALIDATION: one row per long-term setting period since implant, with the REDCap home reports
  filed during it (several scales pooled onto the 0-10 sheet scale), the state the patient was in
  before it and the setting itself.

Time is modelled nowhere (decision 196): no date or clock time is a feature; the order of steps
within one visit is the only sequence used.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from . import config as C

DEFAULT_DATA_DIR = os.environ.get(
    "STIM_RL_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "_agent_bridge", "_stim_rl_data"))

RATED_SOURCES = ("stim_tab", "notes_tab")
SETTING_COLS = list(C.ACTION_NAMES)


# ==================================================================================================
# 1. The retrospective database
# ==================================================================================================
class RetrospectiveDB:
    """SQLAlchemy access to the exported snapshot. `build_from_snapshot` loads the three CSVs into
    tables and checks each row count against the export manifest; the query methods read back."""

    TABLES = ("visit_steps", "chronic_epochs", "redcap_reports")

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR, url: str | None = None):
        self.data_dir = os.path.abspath(data_dir)
        self.url = url or f"sqlite:///{os.path.join(self.data_dir, 'stim_rl.sqlite')}"
        self.engine = create_engine(self.url, future=True)

    def _manifest(self) -> dict:
        with open(os.path.join(self.data_dir, "manifest.json")) as f:
            return json.load(f)

    def _counts(self, engine) -> dict | None:
        try:
            with engine.connect() as c:
                return {t: int(c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()) for t in self.TABLES}
        except Exception:                                             # noqa: BLE001
            return None

    def build_from_snapshot(self) -> dict:
        """Load the CSVs into a fresh database file and swap it in whole, so a reader in another
        process never sees a half-built table; refuse if a row count disagrees with the export."""
        manifest = self._manifest()
        if not self.url.startswith("sqlite:///"):
            return self._load_tables(self.engine, manifest)
        path = self.url[len("sqlite:///"):]
        tmp = f"{path}.{os.getpid()}.tmp"
        eng = create_engine(f"sqlite:///{tmp}", future=True)
        try:
            counts = self._load_tables(eng, manifest)
        finally:
            eng.dispose()
        os.replace(tmp, path)
        self.engine.dispose()
        return counts

    def _load_tables(self, engine, manifest) -> dict:
        for t in self.TABLES:
            pd.read_csv(os.path.join(self.data_dir, f"{t}.csv")).to_sql(t, engine, if_exists="replace", index=False)
        counts = self._counts(engine)
        for t in self.TABLES:
            if counts[t] != manifest[t]["rows"]:
                raise ValueError(f"{t}: {counts[t]} rows in the database, {manifest[t]['rows']} exported")
        return counts

    def ensure_built(self) -> dict:
        """Build the database only when it is missing or its row counts differ from the export;
        a lock file keeps two processes from building at once."""
        import fcntl
        want = {t: self._manifest()[t]["rows"] for t in self.TABLES}
        with open(os.path.join(self.data_dir, ".stim_rl_db.lock"), "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                have = self._counts(self.engine)
                return have if have == want else self.build_from_snapshot()
            finally:
                fcntl.flock(lk, fcntl.LOCK_UN)

    def _read(self, sql: str, **params) -> pd.DataFrame:
        with self.engine.connect() as c:
            return pd.read_sql(text(sql), c, params=params)

    def rated_steps(self) -> pd.DataFrame:
        """Visit-sheet steps with a sheet rating (Stim Testing or Notes tab), in sheet order, with
        each blank setting cell filled from the sheet's previous written value over EVERY row,
        rated or not (a sheet leaves a cell blank when it did not change, and a change can be
        written on an unrated row; audit 2026-10-02 found 17 values taken from an older row). A row
        whose current exceeds the 5 mA action top is a parse error (the 12.0 mA row of 10_14_25)
        and is neither used nor copied forward."""
        df = self._read("SELECT * FROM visit_steps ORDER BY file, row_index")
        for c in SETTING_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        bad = (df["amp_mA_Left"] > C.AMP_ACTION_MAX_MA) | (df["amp_mA_Right"] > C.AMP_ACTION_MAX_MA)
        df = df[~bad].copy()
        df[SETTING_COLS] = df.groupby("file")[SETTING_COLS].ffill()
        return df[df["rating_source"].isin(RATED_SOURCES)].reset_index(drop=True)

    def all_steps(self) -> pd.DataFrame:
        return self._read("SELECT * FROM visit_steps ORDER BY file, row_index")

    def chronic_epochs(self) -> pd.DataFrame:
        df = self._read("SELECT * FROM chronic_epochs ORDER BY t_start")
        for c in ("t_start", "t_end"):
            df[c] = pd.to_datetime(df[c], utc=True, format="mixed")
        return df

    def redcap_reports(self) -> pd.DataFrame:
        df = self._read("SELECT * FROM redcap_reports")
        df["t_utc"] = pd.to_datetime(df["t_utc"], utc=True, format="mixed")
        return df.sort_values("t_utc").reset_index(drop=True)


# ==================================================================================================
# 2. Safety and reward
# ==================================================================================================
class SafetyModel:
    """How close a setting is to the limits, and whether it breaks one. Settings are raw units."""

    def __init__(self, ceiling=C.AMP_CEILING_MA, warn=C.AMP_WARN_MA):
        self.ceiling, self.warn = float(ceiling), float(warn)

    def side_risk(self, amp: float) -> float:
        """0 below the warning current, rising to 1 at the ceiling, above 1 past it."""
        if not np.isfinite(amp):
            return 0.0
        return max(0.0, (amp - self.warn) / (self.ceiling - self.warn))

    def risk(self, setting) -> float:
        f, aL, aR, pL, pR = (float(x) for x in setting)
        r = max(self.side_risk(aL), self.side_risk(aR))
        if self.violates(setting):
            r = max(r, 1.0 + 1e-9)
        return r

    def violates(self, setting) -> bool:
        f, aL, aR, pL, pR = (float(x) for x in setting)
        eps = 1e-9
        if aL > self.ceiling + eps or aR > self.ceiling + eps:
            return True
        lo, hi = C.DEVICE_RATE_HZ
        if np.isfinite(f) and not (lo <= f <= hi):
            return True
        lo, hi = C.DEVICE_PW_US
        return any(np.isfinite(p) and not (lo <= p <= hi) for p in (pL, pR))

    def penalty(self, setting) -> tuple[float, bool]:
        """(penalty in pain points, terminal). Terminal on a broken limit; graded near the ceiling."""
        if self.violates(setting):
            return C.TERMINAL_PENALTY, True
        return -C.PROXIMITY_PENALTY * min(1.0, self.risk(setting)), False


REWARD_VARIANTS = ("delta", "level", "worst_site")


def _common_change(a: dict, b: dict, how: str = "mean") -> float:
    """a minus b over the pain sites both states carry a REAL rating for (rated at that step or
    carried forward within the visit), so a site's first rating mid-visit is not read as a change
    (audit 2026-10-02: 24 transitions jumped 1.31 points on average from that alone). With no site
    in common, the overall score's change."""
    common = [s for s in C.PAIN_SITES if s in a["real"] and s in b["real"]]
    if not common:
        return float(a["sites"]["overall"] - b["sites"]["overall"])
    f = np.mean if how == "mean" else np.max
    return float(f([a["sites"][s] for s in common]) - f([b["sites"][s] for s in common]))


@dataclass
class RewardFunction:
    """R(s_t, a_t, s_t+1) in pain points (0-10 scale; positive = better).

    Symptom term, by variant (each over the sites rated in both states, `_common_change`):
      delta       mean pain at s_t minus at s_t+1: relief from the step just taken
      level       mean pain at the visit's first rating minus at s_t+1: how far below where the
                  visit started the patient now is (the baseline is part of the state)
      worst_site  half of `level`, half the same on the worst single site, so a setting that
                  helps the average while one site gets worse is not fully rewarded
    Then minus the side-effect cost (0 / 1 / 2 points for none / mild / mild-persistent) and the
    safety penalty. A moderate or severe side effect, or a setting past a limit, ends the episode
    with TERMINAL_PENALTY added.
    """
    variant: str = "delta"
    safety: SafetyModel = field(default_factory=SafetyModel)

    def __post_init__(self):
        if self.variant not in REWARD_VARIANTS:
            raise ValueError(f"unknown reward variant {self.variant!r}")

    def __call__(self, cur: dict, nxt: dict, setting_next, baseline: dict) -> tuple[float, bool, dict]:
        if self.variant == "delta":
            sym = _common_change(cur, nxt)
        elif self.variant == "level":
            sym = _common_change(baseline, nxt)
        else:
            sym = 0.5 * _common_change(baseline, nxt) + 0.5 * _common_change(baseline, nxt, "max")
        se = nxt.get("side_effect")
        terminal = False
        se_cost = 0.0
        if se is not None and np.isfinite(se):
            if se >= C.SIDE_EFFECT_TERMINAL_AT:
                terminal = True
            else:
                se_cost = C.SIDE_EFFECT_COST.get(int(round(se)), 0.0)
        pen, safety_terminal = self.safety.penalty(setting_next)
        terminal = terminal or safety_terminal
        if terminal:
            r = sym + C.TERMINAL_PENALTY
        else:
            r = sym - se_cost + pen
        return float(r), terminal, {"symptom": float(sym), "side_effect_cost": se_cost,
                                    "safety_penalty": float(pen if not terminal else C.TERMINAL_PENALTY)}


# ==================================================================================================
# 3. State and action encoding
# ==================================================================================================
_LOW = np.asarray(C.ACTION_LOW, dtype=float)
_HIGH = np.asarray(C.ACTION_HIGH, dtype=float)


def normalize_action(setting) -> np.ndarray:
    """Raw [Hz, mA, mA, us, us] -> [-1, 1] per dimension (values outside the range stay outside)."""
    s = np.asarray(setting, dtype=float)
    return 2.0 * (s - _LOW) / (_HIGH - _LOW) - 1.0


def denormalize_action(a) -> np.ndarray:
    a = np.clip(np.asarray(a, dtype=float), -1.0, 1.0)
    return _LOW + (a + 1.0) * 0.5 * (_HIGH - _LOW)


def contact_onehot(label) -> np.ndarray:
    v = np.zeros(len(C.CONTACT_LEVELS) + 1, dtype=np.float32)
    if isinstance(label, str) and label in C.CONTACT_LEVELS:
        v[C.CONTACT_LEVELS.index(label)] = 1.0
    else:
        v[-1] = 1.0
    return v


STATE_NAMES = ([f"pain_{s}" for s in C.PAIN_SITES] + ["composite", "worst", "side_effect"]
               + [f"cur_{a}" for a in C.ACTION_NAMES]
               + [f"contact_{c}" for c in C.CONTACT_LEVELS] + ["contact_other", "at_home"]
               + ["baseline_composite", "baseline_worst"])
#: Positions of the symptom numbers in the state (aligned between streams in validation).
SYMPTOM_IDX = list(range(0, 9)) + [22, 23]


def encode_state(sym: dict, setting_cur, contact_next, at_home: bool, baseline: dict | None = None) -> np.ndarray:
    """Symptoms (0-10 scaled to 0-1), the setting in force (scaled to 0-1 over the action range),
    the Left contact the next setting will use (one-hot), whether the visit was at home, and the
    visit's first rating (composite and worst site; the `level` rewards are measured from it)."""
    baseline = baseline or sym
    sites = [sym["sites"][s] / 10.0 for s in C.PAIN_SITES]
    se = sym.get("side_effect")
    se = 0.0 if se is None or not np.isfinite(se) else se / 4.0
    cur = (normalize_action(setting_cur) + 1.0) / 2.0
    return np.concatenate([np.asarray(sites + [sym["composite"] / 10.0, sym["worst"] / 10.0, se]),
                           cur, contact_onehot(contact_next), [1.0 if at_home else 0.0],
                           [baseline["composite"] / 10.0, baseline["worst"] / 10.0]]).astype(np.float32)


def _symptoms_from_row(row: pd.Series, carried: dict, sites_in_visit: list) -> dict | None:
    """Seven sites with gaps carried forward within the visit (`real`: rated now or earlier this
    visit); a site not yet rated takes the overall score for the state only. The composite is the
    mean over the sites this visit ever rated; the worst is their maximum."""
    overall = row.get("overall")
    has_overall = overall is not None and np.isfinite(overall)
    vals, real = {}, set()
    for s in C.PAIN_SITES:
        v = row.get(s)
        if v is not None and np.isfinite(v):
            carried[s] = float(v)
        if s in carried:
            vals[s] = carried[s]
            real.add(s)
        else:
            vals[s] = float(overall) if has_overall else np.nan
    rated = [vals[s] for s in sites_in_visit if np.isfinite(vals[s])]
    if not rated:
        return None
    for s in C.PAIN_SITES:                         # sites never rated this visit: fill for the state
        if not np.isfinite(vals[s]):
            vals[s] = float(np.mean(rated))
    return {"sites": vals, "real": real, "composite": float(np.mean(rated)), "worst": float(np.max(rated)),
            "side_effect": row.get("side_effect_score")}


def _clean_settings(steps: pd.DataFrame) -> pd.DataFrame:
    """Steps still missing any of the five settings after the sheet fill are dropped (a gap is
    also filled from the visit's previous step here, for callers that pass unfilled steps)."""
    d = steps.copy()
    for c in SETTING_COLS:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d[SETTING_COLS] = d.groupby("file")[SETTING_COLS].ffill()
    bad = (d["amp_mA_Left"] > C.AMP_ACTION_MAX_MA) | (d["amp_mA_Right"] > C.AMP_ACTION_MAX_MA)
    d = d[~bad]
    return d.dropna(subset=SETTING_COLS)


# ==================================================================================================
# 4. Trajectories
# ==================================================================================================
@dataclass
class Trajectories:
    observations: np.ndarray
    actions: np.ndarray
    rewards: np.ndarray
    terminals: np.ndarray
    timeouts: np.ndarray
    episode_visit: list            # visit file of each episode, in order
    transitions: pd.DataFrame      # one row per real transition (for tabular / bandit / AgentDB)
    variant: str

    def mdp_dataset(self, visits=None):
        """The d3rlpy MDPDataset, optionally restricted to some visits (for cross-validation)."""
        import d3rlpy
        obs, act, rew, term, tout = self._subset(visits)
        return d3rlpy.dataset.MDPDataset(
            observations=obs, actions=act, rewards=rew, terminals=term, timeouts=tout,
            action_space=d3rlpy.ActionSpace.CONTINUOUS, action_size=act.shape[1])

    def _subset(self, visits):
        if visits is None:
            return self.observations, self.actions, self.rewards, self.terminals, self.timeouts
        keep = set(visits)
        ends = np.flatnonzero((self.terminals + self.timeouts) > 0)
        starts = np.r_[0, ends[:-1] + 1]
        idx = np.concatenate([np.arange(s, e + 1) for s, e, v in
                              zip(starts, ends, self.episode_visit) if v in keep])
        return (self.observations[idx], self.actions[idx], self.rewards[idx],
                self.terminals[idx], self.timeouts[idx])


class TrajectoryBuilder:
    """Rated visit-sheet steps -> episodes (one per visit, split where a step ends one)."""

    def __init__(self, reward: RewardFunction):
        self.reward = reward

    def build(self, rated: pd.DataFrame) -> Trajectories:
        d = _clean_settings(rated)
        O, A, R, T, TO, ep_visit, rows = [], [], [], [], [], [], []
        for visit, g in d.groupby("file", sort=True):
            g = g.sort_values("row_index")
            sites_in_visit = [s for s in C.PAIN_SITES if g[s].notna().any()]
            carried = {}
            seq = []
            for _, row in g.iterrows():
                sym = _symptoms_from_row(row, carried, sites_in_visit)
                if sym is not None:
                    seq.append((row, sym))
            if len(seq) < 2:
                continue
            at_home = str(g["setting"].iloc[0]) == "home"
            baseline = seq[0][1]
            ep = {"O": [], "A": [], "R": []}

            def close(final_row, final_sym, terminal, base):
                if terminal:
                    if ep["O"]:
                        O.extend(ep["O"]); A.extend(ep["A"]); R.extend(ep["R"])
                        T.extend([0.0] * (len(ep["O"]) - 1) + [1.0]); TO.extend([0.0] * len(ep["O"]))
                        ep_visit.append(visit)
                else:
                    if ep["O"]:
                        s_last = encode_state(final_sym, final_row[SETTING_COLS].to_numpy(float),
                                              final_row["left_contact"], at_home, base)
                        O.extend(ep["O"] + [s_last])
                        A.extend(ep["A"] + [normalize_action(final_row[SETTING_COLS].to_numpy(float))])
                        R.extend(ep["R"] + [0.0]); T.extend([0.0] * (len(ep["O"]) + 1))
                        TO.extend([0.0] * len(ep["O"]) + [1.0])
                        ep_visit.append(visit)
                ep["O"], ep["A"], ep["R"] = [], [], []

            for t in range(len(seq) - 1):
                (r0, s0), (r1, s1) = seq[t], seq[t + 1]
                cur = r0[SETTING_COLS].to_numpy(float)
                nxt = r1[SETTING_COLS].to_numpy(float)
                obs = encode_state(s0, cur, r1["left_contact"], at_home, baseline)
                rew, term, parts = self.reward(s0, s1, nxt, baseline)
                ep["O"].append(obs); ep["A"].append(normalize_action(nxt)); ep["R"].append(rew)
                nxt_contact = seq[t + 2][0]["left_contact"] if t + 2 < len(seq) else r1["left_contact"]
                rows.append({"visit": visit, "at_home": at_home, "t": t, "reward": rew, "terminal": term,
                             "composite": s0["composite"], "composite_next": s1["composite"],
                             "contact_next": r1["left_contact"], "obs": obs,
                             "next_obs": encode_state(s1, nxt, nxt_contact, at_home, baseline),
                             **{f"cur_{k}": v for k, v in zip(C.ACTION_NAMES, cur)},
                             **{f"act_{k}": v for k, v in zip(C.ACTION_NAMES, nxt)}, **parts})
                if term:
                    close(r1, s1, True, baseline)
                    baseline = s1
            close(seq[-1][0], seq[-1][1], False, baseline)
        return Trajectories(np.asarray(O, np.float32), np.asarray(A, np.float32),
                            np.asarray(R, np.float32), np.asarray(T, np.float32),
                            np.asarray(TO, np.float32), ep_visit, pd.DataFrame(rows),
                            self.reward.variant)


# ==================================================================================================
# 5. Long-term validation set
# ==================================================================================================
def redcap_points(reports: pd.DataFrame) -> pd.DataFrame:
    """Each REDCap item on the 0-10 sheet scale (higher = worse) plus their per-report mean."""
    out = pd.DataFrame(index=reports.index)
    for item, f in C.REDCAP_TO_POINTS.items():
        if item in reports.columns:
            out[item] = f(pd.to_numeric(reports[item], errors="coerce"))
    out["composite"] = out.mean(axis=1, skipna=True)
    out["t_utc"] = reports["t_utc"]
    return out


def _sym_from_redcap(means: pd.Series) -> dict | None:
    """REDCap means -> the sheet's seven sites. Overall is the mean of nrs and the overall VAS
    (`vas` is overall pain, StimOptimizer ITEM_COLUMNS); back from back_vas; left leg and left
    foot from left_leg_vas. Head and the right leg and foot have no REDCap item: like a site a
    visit never rated, they take the mean of the sites that do."""
    def g(k):
        v = means.get(k, np.nan)
        return float(v) if np.isfinite(v) else np.nan
    overall = np.nanmean([g("nrs"), g("vas")]) if np.isfinite([g("nrs"), g("vas")]).any() else np.nan
    observed = {"overall": overall, "back": g("back_vas"), "left_leg": g("left_leg_vas"),
                "left_foot": g("left_leg_vas")}
    observed = {k: v for k, v in observed.items() if np.isfinite(v)}
    if not observed:
        return None
    base = [observed[k] for k in ("overall", "back", "left_leg") if k in observed]
    comp = float(np.mean(base))
    sites = {s: observed.get(s, comp) for s in C.PAIN_SITES}
    return {"sites": sites, "real": set(observed), "composite": comp, "worst": float(max(base)),
            "side_effect": 0.0}


def _quantile_map(x, ref_from, ref_to):
    """Each value's rank within `ref_from`, read off as the same quantile of `ref_to`."""
    ref_from = np.sort(np.asarray(ref_from, float))
    q = np.searchsorted(ref_from, x, side="right") / max(len(ref_from), 1)
    q = np.clip(q - 0.5 / max(len(ref_from), 1), 0, 1)
    return np.quantile(np.asarray(ref_to, float), q)


def chronic_validation_set(db: RetrospectiveDB, *, exclude_visit_days: bool = True,
                           exclude_periods_with_visits: bool = False, washin_h: float | None = None,
                           align_to: np.ndarray | None = None, keep_latest: bool = False) -> pd.DataFrame:
    """One row per long-term setting period with enough home reports.

    Columns: the setting (raw), its Left contact, mean pain in points over its reports (the six-item
    composite and each item), the report count, `prev_pain_composite` (the same for the last
    earlier period with reports), `has_visit` (a visit sheet falls inside it), and `obs`: the state
    before it (the previous period's reports as symptoms, the previous period's setting in force).
    REDCap levels sit higher than sheet ratings (mean composite 7.35 against 4.39 in training,
    audit 2026-10-02), so with `align_to` (training states) every symptom number is replaced by the
    training value at the same rank: the models are asked about states like those they learned on.
    Reports filed on a visit-sheet day are left out by default. `washin_h` overrides the 1-minute
    wash-in.
    """
    ep = db.chronic_epochs()
    rep = redcap_points(db.redcap_reports())
    raw_rep = db.redcap_reports()
    vd = pd.to_datetime(db.all_steps()["visit_date_ts"], utc=True, errors="coerce")
    visit_days = sorted(set(vd.dt.tz_convert("America/Los_Angeles").dt.date.dropna()))
    if exclude_visit_days:
        local = rep["t_utc"].dt.tz_convert("America/Los_Angeles").dt.date
        keep = ~local.isin(set(visit_days))
        rep, raw_rep = rep[keep], raw_rep[keep.values]
    for c in SETTING_COLS:
        ep[c] = pd.to_numeric(ep[c], errors="coerce")
    washin = pd.Timedelta(hours=washin_h) if washin_h is not None else pd.Timedelta(minutes=C.WASHIN_MIN)
    rows = []
    prev_sym, prev_setting, prev_pain = None, None, np.nan
    for _, e in ep.iterrows():
        sel = (rep["t_utc"] >= e["t_start"] + washin) & (rep["t_utc"] < e["t_end"])
        r = rep[sel]
        means = r.drop(columns=["t_utc"]).mean(numeric_only=True)
        raw_means = raw_rep[sel.values].mean(numeric_only=True)
        setting = e[SETTING_COLS].to_numpy(float)
        d0 = e["t_start"].tz_convert("America/Los_Angeles").date()
        d1 = e["t_end"].tz_convert("America/Los_Angeles").date()
        rec = {"epoch": e["epoch"], "t_start": e["t_start"], "dur_h": e["dur_h"],
               "left_contact": e["left_contact"], "n_reports": int(len(r)),
               "has_visit": any(d0 <= v <= d1 for v in visit_days),
               **{k: v for k, v in zip(C.ACTION_NAMES, setting)},
               **{f"pain_{k}": means.get(k, np.nan) for k in list(C.REDCAP_TO_POINTS) + ["composite"]},
               "prev_pain_composite": prev_pain}
        ok_prev = (prev_sym is not None and prev_setting is not None
                   and np.isfinite(setting).all() and np.isfinite(prev_setting).all())
        rec["obs"] = encode_state(prev_sym, prev_setting, e["left_contact"], True) if ok_prev else None
        own = _sym_from_redcap(raw_means) if len(r) else None
        rec["own_obs"] = (encode_state(own, setting, e["left_contact"], True)
                          if own is not None and np.isfinite(setting).all() else None)
        rows.append(rec)
        if own is not None:
            prev_sym, prev_pain = own, float(means.get("composite", np.nan))
        prev_setting = setting
    out = pd.DataFrame(rows)
    keep = out["obs"].notna() & (out["n_reports"] >= C.MIN_REPORTS_PER_EPOCH) \
        & np.isfinite(out[list(C.ACTION_NAMES)]).all(axis=1) & np.isfinite(out["prev_pain_composite"])
    if exclude_periods_with_visits:
        keep &= ~out["has_visit"]
    if keep_latest:
        keep.iloc[-1] = keep.iloc[-1] or out["own_obs"].iloc[-1] is not None
    out = out[keep].reset_index(drop=True)
    if align_to is not None and len(out):
        ref = np.stack(out["obs"].to_list())
        for col in ("obs", "own_obs"):
            arr = [None if o is None else o.copy() for o in out[col]]
            for j in SYMPTOM_IDX:
                for a in arr:
                    if a is not None:
                        a[j] = _quantile_map(a[j], ref[:, j], align_to[:, j])
            out[col] = arr
    return out


def validation_sets(db: RetrospectiveDB, train_obs: np.ndarray) -> dict:
    """The primary validation set and three sensitivity versions, all aligned to training."""
    return {
        "primary": chronic_validation_set(db, align_to=train_obs),
        "no_visit_periods": chronic_validation_set(db, align_to=train_obs, exclude_periods_with_visits=True),
        "washin_24h": chronic_validation_set(db, align_to=train_obs, washin_h=24.0),
        "unaligned": chronic_validation_set(db),
    }


def latest_state(db: RetrospectiveDB, contact: str, train_obs: np.ndarray | None = None) -> np.ndarray | None:
    """The state to recommend from today: the NEWEST period's own reports and its own setting
    (audit 2026-10-02: the previous version used the period before it), aligned to training."""
    v = chronic_validation_set(db, exclude_visit_days=False, align_to=train_obs, keep_latest=True)
    if v.empty or v["own_obs"].iloc[-1] is None:
        return None
    obs = v["own_obs"].iloc[-1].copy()
    obs[15:15 + len(C.CONTACT_LEVELS) + 1] = contact_onehot(contact)
    return obs


def load(data_dir: str = DEFAULT_DATA_DIR, variant: str = "delta"):
    """Convenience: (db, trajectories, primary validation set) for one reward variant."""
    db = RetrospectiveDB(data_dir)
    db.ensure_built()
    traj = TrajectoryBuilder(RewardFunction(variant)).build(db.rated_steps())
    return db, traj, chronic_validation_set(db, align_to=traj.observations)


if __name__ == "__main__":
    db = RetrospectiveDB()
    print("tables:", db.ensure_built())
    for v in REWARD_VARIANTS:
        tr = TrajectoryBuilder(RewardFunction(v)).build(db.rated_steps())
        ds = tr.mdp_dataset()
        print(f"{v:10s} episodes={len(ds.episodes)} transitions={ds.transition_count} "
              f"terminals={int(tr.terminals.sum())} reward mean={tr.transitions.reward.mean():.2f} "
              f"sd={tr.transitions.reward.std():.2f} obs_dim={tr.observations.shape[1]}")
    for name, val in validation_sets(db, tr.observations).items():
        print(f"validation {name:16s} periods={len(val)} reports={int(val.n_reports.sum())} "
              f"contacts={val.left_contact.value_counts().to_dict()}")
