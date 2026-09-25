"""The control analyses run on a participant's record and saved (2026-09-24).

These run OFFLINE -- through `python3 -m modules.ControlAnalyses.run <key> [participant]` -- never
on a page request, and they read the modules' own inputs: the Biomarkers matcher and 3 s-piece
band power, the settings stream from the implant date on (decision 260), the pain reports. They
write nothing to the cache store; each run adds one saved result (`snapshots.save`).

Promoted from the probes of 2026-09-24 (`_agent_bridge/_probe_offwindow_band_pain.py`,
`_probe_confound_live.py`, `_probe_dose_history.py`), whose numbers decision 262 records.
"""
import numpy as np
import pandas as pd

from . import snapshots as SN
from . import stats as ST

CA = "America/Los_Angeles"
_WORD = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3"}


def pair_name(ch):
    """A sensing pair as the pages write it: ONE_THREE_LEFT -> L 1-3+."""
    parts = str(ch).split("_")
    if len(parts) == 3 and parts[0] in _WORD and parts[1] in _WORD and parts[2] in ("LEFT", "RIGHT"):
        return f"{parts[2][0]} {_WORD[parts[0]]}-{_WORD[parts[1]]}+"
    return str(ch)
DAY = 86400.0
MIN_STRETCH_DAYS = 3.0


# ------------------------------------------------------------------------------------------------
# shared inputs
# ------------------------------------------------------------------------------------------------

def _bs():
    from modules.Biomarkers import bravo_service as BS
    return BS


def _stream(uid):
    from modules.Biomarkers.routines import stim_current as SC
    return SC.settings_stream_for(uid)


def _side_steps(stream, hemi):
    h = np.asarray(stream["hemi"], dtype=object)
    m = np.array([str(x) == hemi for x in h])
    t = np.asarray(stream["t_s"], float)[m]
    a = np.asarray(stream["amp_mA"], float)[m]
    o = np.argsort(t, kind="stable")
    return t[o], a[o]


def _ratings(uid, metric):
    """Report times (epoch s) and scores for one pain score, from the implant date on."""
    from modules.DecodeCommon import data_start as DS
    BS = _bs()
    P = BS.models.Participant.find(uid=uid)
    req = {"ParticipantId": uid, "LabelMetric": metric}
    pro_df = BS._load_pros(req, P)
    pro_df, m, _ = BS._resolve_biomarker_metric(req, pro_df)
    t, v = BS._pro_match_arrays(pro_df, m)
    t, v = np.asarray(t, float), np.asarray(v, float)
    keep = DS.keep_from(t, DS.data_start_s(uid)) & np.isfinite(v)
    o = np.argsort(t[keep])
    return t[keep][o], v[keep][o], m


def _ca_days(t):
    return pd.to_datetime(np.asarray(t, float), unit="s", utc=True).tz_convert(CA).strftime("%Y-%m-%d").to_numpy()


def _iso(t):
    return pd.Timestamp(float(t), unit="s", tz="UTC").tz_convert(CA).strftime("%Y-%m-%d")


def stretches(stream, *, min_days=MIN_STRETCH_DAYS, until_s=None, merge_h=24.0):
    """Runs of the settings stream when a side was at 0 mA: `both off`, `left off, right on`,
    `right off, left on`, each at least `min_days` long, from the stream alone."""
    tl, al = _side_steps(stream, "Left")
    tr, ar = _side_steps(stream, "Right")
    edges = np.unique(np.concatenate([tl, tr]))
    if edges.size == 0:
        return []
    end = float(until_s if until_s is not None else edges[-1] + DAY)
    L = ST.dose_history(edges, tl, al, 0)
    R = ST.dose_history(edges, tr, ar, 0)

    def kind(l, r):
        if l == 0 and r == 0:
            return "both off"
        if l == 0 and r > 0:
            return "left off, right on"
        if r == 0 and l > 0:
            return "right off, left on"
        return None

    runs, cur, start = [], "unset", None
    for i, t0 in enumerate(edges):
        k = kind(L[i], R[i]) if np.isfinite(L[i]) and np.isfinite(R[i]) else None
        if k != cur:
            if cur != "unset":
                runs.append([cur, start, t0])
            cur, start = k, t0
    if cur != "unset":
        runs.append([cur, start, end])
    # A clinic visit steps the current for minutes to hours: a run shorter than `merge_h` takes the
    # kind of the run before it, so a visit does not split a stretch in two (found on RCS08's
    # left-off stretch of 2025-08-22 to 10-21, which visits cut into pieces under 3 days).
    merged = []
    for k, a, b in runs:
        if merged and (b - a) < merge_h * 3600.0:
            merged[-1][2] = b
            continue
        if merged and merged[-1][0] == k:
            merged[-1][2] = b
            continue
        merged.append([k, a, b])
    runs = [(k, a, b) for k, a, b in merged if k is not None]
    out = []
    for k, a, b in runs:
        if (b - a) / DAY >= float(min_days):
            out.append(dict(kind=k, start_s=float(a), end_s=float(b),
                            label=f"{k}, {_iso(a)} to {_iso(b)}", days=round((b - a) / DAY, 1)))
    return out


# ------------------------------------------------------------------------------------------------
# 1. band against pain with the current off
# ------------------------------------------------------------------------------------------------

def run_zero_ma(uid, *, metrics=("vas", "nrs"), seconds=60.0, same_day_tol_h=12.0, n_boot=2000, save=True):
    from modules.Biomarkers.routines import stim_current as SC
    from Server import models
    BS = _bs()
    stream = _stream(uid)
    td, psd_list, events, montage, chan_order, channels = BS._recordings_setup_cached(uid)
    raw_by_ch = BS._raw_lsb_cache_cached(uid, channels, list(td or []) + list(psd_list or []),
                                         events, montage_psd_blocks=montage)
    P = BS.models.Participant.find(uid=uid)
    rec = pd.DataFrame(list(models.Recording.objects.filter(source__owner=P).values("type", "date")))
    streamed = ["MedtronicBrainSenseTimeDomain", "MedtronicIndefiniteStream", "MedtronicBrainSenseSurvey",
                "MedtronicBaselineMontages", "MedtronicStimulationMontages", "PatientControllerEvent"]
    str_all = stretches(stream)
    coverage, rows, pooled = [], [], []
    for metric in metrics:
        t, v, mname = _ratings(uid, metric)
        day = _ca_days(t)
        in_str = [np.flatnonzero((t >= s["start_s"]) & (t < s["end_s"])) for s in str_all]
        for ch, cache in (raw_by_ch or {}).items():
            if not cache:
                continue
            side = SC.hemisphere_of_channel(ch)
            near, _s, centers, *_ = BS._band_time_sweep_power_by_seconds(
                t, cache, None, tol_s=same_day_tol_h * 3600.0, allow_window_reuse=True,
                match_direction="nearest", channel=ch, participant_uid=uid, seconds=[seconds])
            page, *_ = BS._band_time_sweep_power_by_seconds(
                t, cache, None, tol_s=3600.0, allow_window_reuse=False,
                match_direction="pro_first", channel=ch, participant_uid=uid, seconds=[seconds])
            X = np.asarray(near[seconds], float)
            has = np.isfinite(X).all(axis=1)
            has_page = np.isfinite(np.asarray(page[seconds], float)).all(axis=1)
            both_off_ix = []
            for s, ix in zip(str_all, in_str):
                # a stretch reads a pair only when that pair's own side is off
                if s["kind"] == "left off, right on" and side != "Left":
                    continue
                if s["kind"] == "right off, left on" and side != "Right":
                    continue
                m = ix[has[ix]]
                coverage.append(dict(score=mname, pair=ch, stretch=s["label"], kind=s["kind"],
                                     reports=int(ix.size), days_with_reports=int(len(set(day[ix]))),
                                     matched_60min=int(has_page[ix].sum()), matched_same_day=int(m.size),
                                     days_matched=int(len(set(day[m])))))
                if s["kind"] == "both off":
                    both_off_ix.append((s["label"], m))
                if m.size < 8 or len(np.unique(v[m])) < 3:
                    continue
                pv = []
                pain_t = ST.spearman_within(t[m], v[m])
                for j, c in enumerate(centers):
                    r, lo, hi, p = ST.day_resampled_rho(X[m, j], v[m], day[m], n_boot=n_boot, seed=j)
                    rows.append(dict(score=mname, pair=ch, stretch=s["label"], kind=s["kind"], centre=float(c),
                                     n=int(m.size), days=int(len(set(day[m]))), rho=r, lo=lo, hi=hi, p=p,
                                     band_vs_time=ST.spearman_within(t[m], X[m, j]), pain_vs_time=pain_t))
                    pv.append(p)
                for k, q in enumerate(ST.bh_q(pv)):
                    rows[-len(pv) + k]["q"] = float(q)
            mb = np.concatenate([m for _l, m in both_off_ix]) if both_off_ix else np.array([], int)
            if mb.size >= 12:
                lab = np.concatenate([[l] * m.size for l, m in both_off_ix])
                pv = []
                for j, c in enumerate(centers):
                    r, lo, hi, p = ST.day_resampled_rho(X[mb, j], v[mb], day[mb], strata=lab, n_boot=n_boot, seed=j)
                    pooled.append(dict(score=mname, pair=ch, centre=float(c), n=int(mb.size),
                                       days=int(len(set(day[mb]))), rho=r, lo=lo, hi=hi, p=p))
                    pv.append(p)
                for k, q in enumerate(ST.bh_q(pv)):
                    pooled[-len(pv) + k]["q"] = float(q)
    for s in str_all:
        r = rec[(rec["date"] >= s["start_s"]) & (rec["date"] < s["end_s"]) & rec["type"].isin(streamed)]
        s["recordings_by_type"] = {str(k): int(n) for k, n in r.groupby("type").size().items()}
    reading = _zero_ma_reading(rows)
    result = dict(stretches=str_all, coverage=coverage, bands=rows, pooled_both_off=pooled)
    settings = dict(scores=list(metrics), seconds_of_signal=seconds,
                    matching=f"nearest recording within {same_day_tol_h:g} h, a recording may serve several ratings",
                    coverage_also_at="the page's 60-minute window, report first, no reuse",
                    interval="95%, resampling whole California days", n_boot=n_boot,
                    correction="Benjamini-Hochberg over the bands of one pair, stretch and score")
    return _finish(uid, "zero_ma_within_stretch", result, settings, reading, save)


def _zero_ma_reading(rows):
    out = []
    df = pd.DataFrame(rows)
    if df.empty:
        return ["No stretch had enough matched ratings to read."]
    for (score, pair, stretch), g in df.groupby(["score", "pair", "stretch"], sort=False):
        pos = g[(g.q < 0.05) & (g.rho > 0)]
        neg = g[(g.q < 0.05) & (g.rho < 0)]
        if pos.empty and neg.empty:
            continue
        parts = []
        if not pos.empty:
            parts.append("rise with pain at " + ", ".join(f"{c:g} Hz ({r:+.2f})" for c, r in zip(pos.centre, pos.rho)))
        if not neg.empty:
            parts.append(f"{len(neg)} band(s) fall with pain")
        trend = ""
        if (g.band_vs_time.abs().median() > 0.3) and (abs(g.pain_vs_time.iloc[0]) > 0.3):
            trend = (f" Both drift over the stretch (bands {g.band_vs_time.median():+.2f} with time, pain "
                     f"{g.pain_vs_time.iloc[0]:+.2f}), which can produce this on its own.")
        out.append(f"{stretch}, {pair_name(pair)}, {score} ({int(g.n.iloc[0])} ratings, {int(g.days.iloc[0])} days): "
                   + "; ".join(parts) + " (q < 0.05)." + trend)
    return out or ["No band survives correction for the bands tested in any stretch."]


# ------------------------------------------------------------------------------------------------
# 2. what the stimulation current explains
# ------------------------------------------------------------------------------------------------

def run_current_explains(uid, *, lengths=(30.0, 60.0), tol_min=60.0, n_perm=200, save=True):
    from modules.Biomarkers.routines import analytics, stim_current, confound_diagnostic as CD
    BS = _bs()
    req = {"ParticipantId": uid}
    P = BS.models.Participant.find(uid=uid)
    pro_df = BS._load_pros(req, P)
    pro_df, metric, _ = BS._resolve_biomarker_metric(req, pro_df)
    strategy, low, high = BS._label_strategy_params(req)
    t, v = BS._pro_match_arrays(pro_df, metric)
    t, v = np.asarray(t, float), np.asarray(v, float)
    y = np.asarray(analytics._binarize_labels(v, strategy=strategy, low_pct=low, high_pct=high), float)
    td, psd_list, events, montage, chan_order, channels = BS._recordings_setup_cached(uid)
    raw_by_ch = BS._raw_lsb_cache_cached(uid, channels, list(td or []) + list(psd_list or []),
                                         events, montage_psd_blocks=montage)
    rows = []
    for secs in lengths:
        for ch, cache in (raw_by_ch or {}).items():
            if not cache:
                continue
            power, _s, centers, *_ = BS._band_time_sweep_power_by_seconds(
                t, cache, None, tol_s=tol_min * 60.0, allow_window_reuse=False,
                match_direction=BS._sweep_match_direction(req), channel=ch, participant_uid=uid,
                seconds=[secs])
            X = np.asarray(power[secs], float)
            cur, _blk = stim_current.current_in_force_for_reports(uid, t, channel=ch)
            cur = np.asarray(cur, float)
            keep = np.isfinite(y) & np.isfinite(cur) & np.isfinite(X).all(axis=1)
            row = dict(pair=ch, seconds=secs, n=int(keep.sum()))
            if int(keep.sum()) < CD.MIN_ROWS:
                row["reason"] = "too few ratings with a recording"
                rows.append(row)
                continue
            d = CD.pre_build_diagnostic(X[keep], y[keep], cur[keep], band_labels=[float(c) for c in centers],
                                        n_perm=n_perm)
            row.update(current_alone=d["current_alone"]["auc"], bands=d["bands_plain"]["auc"],
                       bands_without_current=d["bands_adjusted"]["auc"], null_p50=d["null"]["p50"],
                       null_p95=d["null"]["p95"], p=d["bands_plain"].get("p_value"),
                       # The adjusted reading's OWN honest reference: a null that rotates the label
                       # and refits the SAME current-removed pipeline (`confound_diagnostic`,
                       # 2026-09-25) -- not the plain reading's null decision 262's "p 0.04" used.
                       bands_without_current_p=d["bands_adjusted"].get("p_value"),
                       bands_without_current_null_p50=d.get("null_adjusted", {}).get("p50"),
                       bands_without_current_null_p95=d.get("null_adjusted", {}).get("p95"),
                       shape=d["covariate_shape_in_words"], verdict=d["verdict"])
            rows.append(row)
    reading = []
    for r in rows:
        if r.get("bands") is None:
            continue
        outside = r["bands_without_current"] is not None and r["null_p95"] is not None and r["bands_without_current"] > r["null_p95"]
        line = (f"{pair_name(r['pair'])}, {r['seconds']:g} s ({r['n']} ratings): current alone {r['current_alone']:.3f}, "
               f"every band {r['bands']:.3f}, bands without the current {r['bands_without_current']:.3f} "
               f"({'outside' if outside else 'inside'} the shuffled-data 95th, {r['null_p95']:.3f})")
        if r.get("bands_without_current_p") is not None:
            line += (f"; its own honest reference (a null that rotates the label and refits the SAME "
                    f"current-removed pipeline) gives p {r['bands_without_current_p']:.3f}")
        reading.append(line + ".")
    reading.append("Replaces decision 240's figures, which matched ratings within 60 seconds instead of 60 minutes.")
    reading.append("Corrects decision 262's 'p 0.04' for the reading with the current taken out, which was "
                   "read off the plain reading's null; see settings for the honest reference used here.")
    settings = dict(score=metric, split=f"{strategy} {low:g}/{high:g}", match_window_min=tol_min,
                    lengths_s=list(lengths), shuffles=n_perm,
                    held_out="blocks of time with the neighbouring rows dropped (decision 240)",
                    bands_without_current_p=("a null that rotates the pain label and refits the SAME "
                                             "adjusted (current-taken-out) pipeline on each rotation -- "
                                             "not the plain reading's null decision 262 used"))
    return _finish(uid, "current_explains", dict(rows=rows), settings, reading, save)


# ------------------------------------------------------------------------------------------------
# 4. a current with memory
# ------------------------------------------------------------------------------------------------

TAUS_H = (0, 1, 6, 24, 72, 168, 336)


def run_current_with_memory(uid, *, metrics=("nrs", "left_leg_vas"), taus_h=TAUS_H, n_boot=2000, save=True):
    from modules.Biomarkers.routines import stats_utils as SU
    stream = _stream(uid)
    sides = {h: _side_steps(stream, h) for h in ("Left", "Right")}
    curves = []
    for metric in metrics:
        t, y, mname = _ratings(uid, metric)
        folds = SU.purged_time_blocked_folds(t.size, y=y, n_folds=5)
        rows = ST.tau_curve(t, y, sides, list(taus_h), folds, n_boot=n_boot, days=_ca_days(t))
        curves.append(dict(score=mname, n=int(t.size), days=int(len(set(_ca_days(t)))), rows=rows))
    drift = _drift_with_memory(uid, sides, taus_h)
    reading = []
    for c in curves:
        best = max(c["rows"], key=lambda r: r["r2"])
        reading.append(f"{c['score']} ({c['n']} ratings): held-out R2 {c['rows'][0]['r2']:+.3f} with the current in "
                       f"force; the best memory is {best['tau_h']} h ({best['r2']:+.3f}).")
    for stratum in sorted(set(d["stratum"] for d in drift if d.get("stratum"))):
        moves = [d["tau_h"] for d in drift if d.get("stratum") == stratum and d.get("verdict") == "moves between blocks of time"]
        if not moves:
            continue
        other = [t_ for t_ in taus_h if t_ not in moves]
        reading.append(f"The {stratum} pain surface moves between blocks of time "
                       + ("at every memory length tested, 0 to " + (f"{taus_h[-1] // 24} days" if taus_h[-1] >= 24 else f"{taus_h[-1]} h")
                          if not other else f"at {', '.join(str(t_) + ' h' for t_ in moves)} but not at {', '.join(str(t_) + ' h' for t_ in other)}")
                       + ": remembering the current does not explain its drift.")
    settings = dict(scores=list(metrics), taus_h=list(taus_h),
                    model="a squared term in each side's remembered current, least squares",
                    held_out="5 blocks of time, the neighbouring rows dropped (decision 240)",
                    interval="change in held-out squared error, 95%, resampling whole California days",
                    n_boot=n_boot)
    return _finish(uid, "current_with_memory", dict(curves=curves, drift=drift), settings, reading, save)


def _drift_with_memory(uid, sides, taus_h):
    """Decision 253's diagnosis on every fitted surface, with each epoch's currents replaced by the
    mean remembered current at its usable ratings."""
    from modules.StimOptimizer import adapter as AD, stage1_openloop as S1
    BS = _bs()
    P = BS.models.Participant.find(uid=uid)
    es = AD.build_design_matrix(P, {"ParticipantId": uid}, washin_min=1.0)
    pro_df = BS._load_pros({"ParticipantId": uid}, P)
    tt = (pd.to_datetime(BS._pro_times_utc_series(pro_df), utc=True).astype("int64") // 10**9).to_numpy().astype(float)
    tt = tt[np.isfinite(tt)]
    ts = (pd.to_datetime(es["t_start"], utc=True).astype("int64") // 10**9).to_numpy().astype(float)
    te = (pd.to_datetime(es["t_end"], utc=True).astype("int64") // 10**9).to_numpy().astype(float)
    open_end = es["open_ended"].fillna(False).to_numpy(bool) if "open_ended" in es.columns else np.zeros(len(es), bool)
    out = []
    for tau in taus_h:
        e2 = es.copy()
        if tau:
            for i in range(len(e2)):
                m = (tt >= ts[i] + 60.0) & ((tt < te[i]) | open_end[i])
                if m.any():
                    for side, col in (("Left", "amp_mA_Left"), ("Right", "amp_mA_Right")):
                        e2.iloc[i, e2.columns.get_loc(col)] = float(np.mean(ST.dose_history(tt[m], *sides[side], tau)))
        try:
            s1 = S1.run_stage1(e2, primary_item="left_leg", calibration_check=True, pool_pulse_widths=False)
        except Exception as ex:                                    # noqa: BLE001 -- reported, not raised
            out.append(dict(tau_h=tau, stratum=None, reason=f"stage 1 could not run: {ex}"))
            continue
        for key, sl in s1.slices.items():
            for rate, rs in (getattr(sl, "rate_strata", {}) or {}).items():
                if not getattr(rs, "fitted", False):
                    continue
                d = ((rs.meta or {}).get("calibration") or {}).get("diagnosis") or {}
                out.append(dict(tau_h=tau, stratum=f"{float(rate):g} Hz {float(key[0]):g}/{float(key[1]):g} us",
                                n_epochs=int(rs.n_epochs), verdict=d.get("verdict"),
                                coverage=d.get("coverage95"), between_block_share=d.get("between_block_share"),
                                between_block_p=d.get("between_block_p")))
    return out


# ------------------------------------------------------------------------------------------------
# 3. time of day and weekends
# ------------------------------------------------------------------------------------------------

def run_time_of_day(uid, *, metrics=("nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum"), save=True):
    from modules.CacheStore import store as CS
    from modules.DecodeCommon import data_start as DS
    from . import time_of_day as TD
    payload, _stamp = CS.load_newest("biomarker_psd_matrix", uid, consumer="biomarkers")
    if payload is None:
        raise RuntimeError("no stored band-power matrix for this participant; open the Biomarkers page once")
    t = np.asarray(payload["t"], float)
    keep = DS.keep_from(t, DS.data_start_s(uid))
    X = np.asarray(payload["X"])[keep]
    ch = np.asarray(payload["channel"], str)[keep]
    rows = TD.rows_for(X, t[keep], ch, payload["f_set"], rng=np.random.default_rng(20260923))
    pain = []
    for metric in metrics:
        tt, v, mname = _ratings(uid, metric)
        if tt.size:
            pain.append(dict(score=mname, **TD.weekend_pain(tt, v, rng=np.random.default_rng(0))))
    reading = []
    for c in sorted(set(r["channel"] for r in rows)):
        rr = [r for r in rows if r["channel"] == c and not r.get("why")]
        daily = sum(1 for r in rr if r["R_daily_ci"][0] > r["R_daily_shuffle_p95"])
        wk_up = sum(1 for r in rr if r["r_weekend_ci"][0] > 0)
        wk_dn = sum(1 for r in rr if r["r_weekend_ci"][1] < 0)
        reading.append(f"{pair_name(c)} ({rr[0]['n'] if rr else 0} recordings): a daily cycle above chance in {daily} of "
                       f"{len(rr)} bands; higher at weekends in {wk_up}, lower in {wk_dn}.")
    for p_ in pain:
        if p_.get("why") is None:
            reading.append(f"Pain, {p_['score']}: weekend minus weekday within the week {p_['within_week']:+.2f} "
                           f"({p_['ci'][0]:+.2f} to {p_['ci'][1]:+.2f}, p {p_['p']:.3f}, {p_['n_weeks']} weeks).")
    settings = dict(bands=f"22 centres, 8.5-29.5 Hz, {TD.BAND_WIDTH_HZ:g} Hz wide", clock="California",
                    interval="block bootstrap over recordings in time order", n_boot=TD.N_BOOT,
                    shuffles_of_hours=TD.N_SHUFFLE, pain="weekend minus weekday within each week; weeks resampled")
    return _finish(uid, "time_of_day", dict(bands=rows, pain=pain), settings, reading, save)


# ------------------------------------------------------------------------------------------------
# 5. pain around each on/off switch
# ------------------------------------------------------------------------------------------------

SWITCH_BINS_D = ((0, 2), (2, 5), (5, 9), (9, 14), (14, 28))


def switches(stream, *, min_days=MIN_STRETCH_DAYS):
    """Every moment a side went off or came on, from the stretches with a side off: at each start or
    end of a stretch, the side state just before and just after, described by what changed (a
    stretch that runs straight into another is one switch, not an end and a start)."""
    OFF = {"both off": (True, True), "left off, right on": (True, False),
           "right off, left on": (False, True), None: (False, False)}
    st = stretches(stream, min_days=min_days)

    def state_at(t):
        for s_ in st:
            if s_["start_s"] <= t < s_["end_s"]:
                return s_["kind"]
        return None

    times = sorted({round(x, 0) for s_ in st for x in (s_["start_s"], s_["end_s"])})
    out = []
    for t in times:
        before, after = OFF[state_at(t - 1.0)], OFF[state_at(t)]
        if before == after:
            continue
        went_off = [side for side, b_, a_ in zip(("left", "right"), before, after) if a_ and not b_]
        came_on = [side for side, b_, a_ in zip(("left", "right"), before, after) if b_ and not a_]
        parts = []
        for sides, verb in ((went_off, "off"), (came_on, "on")):
            if len(sides) == 2:
                parts.append(f"both sides {verb}")
            elif sides:
                parts.append(f"the {sides[0]} side {verb}")
        out.append(dict(t_s=float(t), label=f"{' and '.join(parts)}, {_iso(t)}",
                        direction="off" if went_off and not came_on else ("on" if came_on and not went_off else "mixed")))
    return out


def pain_around(events, t, v, *, before_d=14, bins=SWITCH_BINS_D):
    """Mean pain and the number of ratings in the window before each switch and in each window
    after it; descriptive, no statistics."""
    t, v = np.asarray(t, float), np.asarray(v, float)
    rows = []
    for e in events:
        d = (t - e["t_s"]) / DAY
        pre = (d > -before_d) & (d < 0)
        row = dict(label=e["label"], direction=e["direction"],
                   before=dict(mean=float(v[pre].mean()) if pre.any() else None, n=int(pre.sum())), after=[])
        for a, b in bins:
            m = (d > a) & (d <= b)
            row["after"].append(dict(days=f"{a}-{b}", mean=float(v[m].mean()) if m.any() else None, n=int(m.sum())))
        rows.append(row)
    return rows


def run_onoff_switches(uid, *, metric="nrs", save=True):
    events = switches(_stream(uid))
    t, v, mname = _ratings(uid, metric)
    rows = pain_around(events, t, v)
    reading = [f"{r['label']}: {r['before']['mean']:.2f} before" if r["before"]["mean"] is not None else f"{r['label']}: no ratings before"
               for r in rows]
    reading = [line + "; after: " + ", ".join(
        f"{w['days']} d {w['mean']:.2f} (n {w['n']})" for w in r["after"] if w["mean"] is not None) + "."
        for line, r in zip(reading, rows)]
    reading.append("Descriptive: 2 to 40 ratings per window, no statistics; a window may overlap the next switch.")
    settings = dict(score=mname, before_days=14, after_windows_days=[f"{a}-{b}" for a, b in SWITCH_BINS_D],
                    switches="the starts and ends of stretches with a side at 0 mA for at least 3 days")
    return _finish(uid, "onoff_switches", dict(switches=rows), settings, reading, save)


# ------------------------------------------------------------------------------------------------
# 6. up the ladder and down: carry-over
# ------------------------------------------------------------------------------------------------

def _clinic_steps_frame(uid):
    """The clinic sheets' steps (both clinic and at-home sheets) from the implant date on, in the
    shape `carry_over.step_frame` reads."""
    from modules.DecodeCommon import data_start as DS
    from modules.StimOptimizer import clinic_pain as CP
    from . import carry_over as CO
    steps, _stamp, why = CP.load_clinic_steps(uid, consumer="stim_optimizer")
    if steps is None or len(steps) == 0:
        raise RuntimeError(why or "no clinic-sheet steps are stored for this participant")
    t = pd.to_datetime(steps["t_utc"], utc=True, errors="coerce")
    t_s = (t.astype("int64") // 10**9).astype(float).where(t.notna(), np.nan).to_numpy()
    start = DS.data_start_s(uid)
    visit_t = pd.Series(t_s).groupby(steps["visit_date"].to_numpy()).transform("max").to_numpy()
    keep = ~np.isfinite(visit_t) | (visit_t >= (start or -np.inf))

    def num(c):
        return pd.to_numeric(steps[c], errors="coerce")

    def g(v):
        return "nan" if not np.isfinite(v) else f"{v:g}"

    cfg = [f"{g(r)}|{g(pl)}|{g(pr)}|{c}" for r, pl, pr, c in
           zip(num("freq_hz"), num("pw_us_Left"), num("pw_us_Right"), steps["contacts_raw"].fillna(""))]
    d = pd.DataFrame(dict(visit=steps["visit_date"].astype(str), setting=steps["setting"].astype(str),
                          t_s=t_s, row_index=num("row_index"), amp_L=num("amp_mA_Left"),
                          amp_R=num("amp_mA_Right"), cfg=cfg))
    for item in CO.ITEMS:
        d[item] = num(item)
    return d[keep].reset_index(drop=True)


def _by_current(pairs):
    """Aggregates only (no single rating is saved): per side, current and order, the number of
    pairs and the mean readings."""
    if pairs is None or len(pairs) == 0:
        return []
    out = []
    for (side, cur, first), g in pairs.groupby(["side", "current_mA", "falling_first"]):
        out.append(dict(side=side, current_mA=float(cur), falling_first=bool(first), n_pairs=int(len(g)),
                        n_visits=int(g["visit"].nunique()), rising=float(g["rising"].mean()),
                        falling=float(g["falling"].mean()), diff=float(g["diff"].mean()),
                        minutes_apart=float(g["minutes_apart"].median())))
    return out


def run_carry_over(uid, *, n_boot=2000, save=True):
    from . import carry_over as CO
    from modules.CacheStore import store as CS
    long = CO.step_frame(_clinic_steps_frame(uid))
    n_visits = int(long["visit"].nunique())
    pain, holds = [], []
    for item in CO.ITEMS:
        pairs = CO.leg_pairs(long, item)
        s = CO.by_order(pairs, n_boot=n_boot)
        kind, sentence = CO.order_reading(s)
        clinic = pairs[pairs["setting"] == "clinic"] if len(pairs) else pairs
        by_side = {side: CO.paired_summary(g["diff"], g["visit"], n_boot=n_boot)
                   for side, g in (pairs.groupby("side") if len(pairs) else [])}
        pain.append(dict(item=item, words=CO.ITEM_WORDS[item], summary=s, verdict=kind, sentence=sentence,
                         by_side=by_side, clinic_only=CO.by_order(clinic, n_boot=n_boot),
                         by_current=_by_current(pairs),
                         settings_seen=int(len(pairs)), visits_with_pairs=int(pairs["visit"].nunique()) if len(pairs) else 0))
        h = CO.held_changes(long, item)
        for on in (True, False):
            hh = h[h["on"] == on] if len(h) else h
            summ = CO.paired_summary(hh["change"], hh["visit"], n_boot=n_boot) if len(hh) else CO.paired_summary([], [])
            summ.update(item=item, words=CO.ITEM_WORDS[item], on=on,
                        minutes_median=float(hh["minutes"].median()) if len(hh) else None)
            holds.append(summ)
    rp, _stamp = CS.load_newest("three_source_run_points", uid, consumer="stim_optimizer")
    lp = CO.ladder_pairs(rp)
    if len(lp):                                   # the page's 22 band centres (decision 32)
        lp = lp[(lp["band_centre_hz"] >= 8.5 - 1e-9) & (lp["band_centre_hz"] <= 29.5 + 1e-9)]
    ladder = []
    if len(lp):
        for (src, ch), g in lp.groupby(["source", "sensing_contact"], sort=False):
            s = CO.by_order(g.assign(diff=g["relative_diff"], visit=g["run"]), n_boot=n_boot)
            bands = []
            for c, gb in g.groupby("band_centre_hz"):
                bs = CO.paired_summary(gb["relative_diff"], gb["run"], n_boot=n_boot)
                bands.append(dict(centre=float(c), mean=bs["mean"], lo=bs["lo"], hi=bs["hi"],
                                  n_pairs=bs["n_pairs"], n_runs=bs["n_visits"]))
            means = np.array([b["mean"] for b in bands], float)
            ladder.append(dict(source=src, pair=ch, summary=s, verdict=CO.order_reading(s)[0],
                               n_runs=int(g["run"].nunique()), n_bands=int(g["band_centre_hz"].nunique()),
                               bands_lower=int((means < 0).sum()), bands_higher=int((means > 0).sum()),
                               median_over_bands=float(np.median(means)) if means.size else None,
                               bands=bands))
    reading = _carry_over_reading(pain, holds, ladder)
    result = dict(pain=pain, holds=holds, ladder=ladder, n_visits=n_visits)
    settings = dict(sheets="the clinic and at-home testing sheets, from the implant date on",
                    pairs=("a current reached by a rise and by a fall within one visit, on one side, with the "
                           "rate, pulse widths, contacts and the other side's current unchanged"),
                    reading_per_step="the last rating of the site while the setting was held",
                    interval="95%, resampling whole visits (runs for the ladder points)", n_boot=n_boot,
                    p="sign flips of whole visits",
                    ladder="settled band power from the stored ladder points (decision 213), falling / rising - 1")
    return _finish(uid, "carry_over_ladder", result, settings, reading, save)


def _fmt_ci(s, fmt="+.2f"):
    if s.get("lo") is None:
        return "no interval"
    return f"{format(s['lo'], fmt)} to {format(s['hi'], fmt)}"


def _carry_over_reading(pain, holds, ladder):
    out = []
    for p in pain:
        s = p["summary"]
        a, b = s["falling after rising"], s["falling before rising"]
        if not s["all"]["n_pairs"]:
            out.append(f"{p['words']}: no current was rated on both legs of one visit.")
            continue
        line = (f"{p['words']}: {s['all']['n_pairs']} currents rated on both legs, {s['all']['n_visits']} visits; "
                f"pain on the way down minus on the way up {s['all']['mean']:+.2f} ({_fmt_ci(s['all'])}). ")
        if len(p["by_side"]) > 1:
            line += "By side: " + ", ".join(f"{side.lower()} {x['mean']:+.2f} ({x['n_pairs']} currents)"
                                            for side, x in p["by_side"].items()) + ". "
        for name, x in (("Fall after the rise", a), ("Fall before the rise", b)):
            line += (f"{name}: {x['mean']:+.2f} ({x['n_pairs']} pairs, {_fmt_ci(x)}). " if x["n_pairs"]
                     else f"{name}: none. ")
        out.append(line + p["sentence"][0].upper() + p["sentence"][1:] + ".")
    for h in holds:
        if h["n_pairs"]:
            out.append(f"{h['words']}, held at one setting with stimulation {'on' if h['on'] else 'off'} and rated again "
                       f"(median {h['minutes_median']:.0f} min later, {h['n_pairs']} times on {h['n_visits']} visits): "
                       f"{h['mean']:+.2f} ({_fmt_ci(h)}); lower {h['n_lower']}, higher {h['n_higher']}, the same {h['n_same']}.")
    for L in ladder:
        s = L["summary"]["all"]
        out.append(f"Settled band power, {L['source']}, {pair_name(L['pair'])} ({L['n_runs']} ladder run(s), "
                   f"{L['n_bands']} bands of 8.5-29.5 Hz): on the way down {100 * L['median_over_bands']:+.1f}% against "
                   f"the way up at the median band, higher in {L['bands_higher']} bands and lower in {L['bands_lower']}; "
                   + ("every fall came after its rise." if not s.get("n_pairs") or not L["summary"]["falling before rising"]["n_pairs"]
                      else "falls came both before and after their rises."))
    return out


# ------------------------------------------------------------------------------------------------
# 7. regression to the mean at one setting
# ------------------------------------------------------------------------------------------------

#: The one rate/pulse-width group decision 253 flagged; the specification's own recommendation is
#: to run this first on that group, and generalise to every group later "if it proves useful"
#: (`artifacts/research_2026-09-25_options/01_regression_to_the_mean.md`).
REGRESSION_TO_MEAN_TARGET_STRATUM = dict(freq_hz=55.0, pw_us_Left=60.0, pw_us_Right=160.0)


def _objective_table(uid, *, primary_item="left_leg"):
    """The whole record's per-setting-period table (`t0`, `J`, `obs_var`, the rate and pulse
    widths, `feasible`), built with the SAME defaults `StimOptimizer.stage1_openloop.run_stage1`
    uses (the latest epoch by `t0` as the incumbent, no pooled-variance override), so the target
    stratum read from it below is the same rows that produced decision 253's own numbers."""
    from modules.StimOptimizer import adapter as AD
    from modules.StimOptimizer.routines import objective as OBJ
    BS = _bs()
    P = BS.models.Participant.find(uid=uid)
    es = AD.build_design_matrix(P, {"ParticipantId": uid}, washin_min=1.0)
    incumbent_epoch = float(es.sort_values("t0")["epoch"].iloc[-1])
    D = OBJ.build_objective(es, incumbent_epoch=incumbent_epoch, cfg={"primary_item": primary_item})
    D = D.loc[D["feasible"]].copy()
    D["t0_s"] = (pd.to_datetime(D["t0"], utc=True).astype("int64") // 10**9).astype(float)
    return D


def run_regression_to_mean(uid, *, primary_item="left_leg",
                           target_stratum=None, save=True):
    from . import regression_to_mean as RM
    target = dict(target_stratum or REGRESSION_TO_MEAN_TARGET_STRATUM)
    D = _objective_table(uid, primary_item=primary_item)
    cols = ["t0_s", "amp_mA_Left", "amp_mA_Right", "J", "obs_var"]
    full = D[["t0_s", "J", "obs_var"]].rename(columns={"t0_s": "t0"})
    match = np.ones(len(D), dtype=bool)
    for col, val in target.items():
        match &= np.isclose(pd.to_numeric(D[col], errors="coerce").to_numpy(float), float(val))
    sub = D.loc[match, cols].rename(columns={"t0_s": "t0"})
    if sub.empty:
        result = {"setting": None, "reason": f"no setting-periods at {target}"}
        reading = [f"No setting-periods matched the target group {target}; nothing to read."]
    else:
        result = RM.diagnosis(sub, full)
        reading = _regression_to_mean_reading(result)
    settings = dict(
        primary_item=primary_item, target_stratum=target,
        blocks="the same 3 time blocks decision 253's own calibration diagnosis uses (equal counts, time order)",
        weights="inverse of each setting-period's own rating noise (obs_var), decision 253's own weights",
        internal_comparison=("exact enumeration of every way to split this stratum's own setting-periods "
                             "into a group this size and the rest -- no random sampling"),
        outside_comparison="every run of setting-periods this size, adjacent in time, across the whole record")
    return _finish(uid, "regression_to_mean", result, settings, reading, save)


def _fmt_block_row(r):
    return f"block {r['block'] + 1}: {r['mean']:+.2f} (n {r['n']}, se {r['se']:.2f})"     # 1-3, as the figure


def _regression_to_mean_reading(diag):
    if diag.get("setting") is None:
        return [diag.get("reason", "not computable")]
    setting, t, o = diag["setting"], diag["target"], diag["other"]
    s5, s6, s7 = diag["internal_comparison"], diag["outside_comparison"], diag["extremity"]
    out = [f"Target setting {setting['amp_mA_Left']:g}/{setting['amp_mA_Right']:g} mA "
          f"({diag['n_target']} of {diag['n_target'] + diag['n_other']} setting-periods in this group): "
          + "; ".join(_fmt_block_row(r) for r in t["by_block"]) + "."]
    if t["heterogeneity"]["p"] is not None:
        line = f"Heterogeneity across blocks: Q {t['heterogeneity']['q']:.2f}, p {t['heterogeneity']['p']:.2g}"
        if t["trend"]["slope"] is not None:
            line += f"; trend {t['trend']['slope']:+.2f} per block"
        out.append(line + ".")
    else:
        out.append(f"Heterogeneity across blocks: {t['heterogeneity']['reason']}.")
    if s5.get("p_two_sided") is not None:
        out.append(
            "Internal comparison (is this specific to the current pair, or the whole group over the same "
            f"calendar weeks?): a randomly chosen group of {diag['n_target']} of the same "
            f"{diag['n_target'] + diag['n_other']} setting-periods matches or exceeds this swing in "
            f"{s5['p_two_sided'] * 100:.1f}% of {s5['n_valid']} usable splits of {s5['n_total']} "
            f"({s5['floor']} is the smallest this can read), and falls at least as far in the same "
            f"direction in {s5['p_same_direction'] * 100:.1f}%.")
    else:
        out.append(f"Internal comparison: {s5.get('reason', 'not computable')}.")
    if s6.get("fraction_ge") is not None:
        out.append(
            "Outside comparison (is a swing this size common anywhere in the record?): "
            f"{s6['fraction_ge'] * 100:.1f}% of {s6['n_windows']} overlapping runs of {s6['window_size']} "
            "setting-periods elsewhere in the record show a swing at least this large (these runs overlap "
            "heavily and are not independent looks).")
    else:
        out.append("Outside comparison: not computable (no background record of setting-periods).")
    if s7.get("value") is not None:
        out.append(f"Block 1 sat {s7['value']:+.1f} standard errors from the whole record's own long-run "
                   f"average ({s7['block1_mean']:+.2f} against {s7['record_mean']:+.2f}); the more extreme "
                   "this is, the more reversion regression to the mean predicts on its own.")
    out.append("Descriptive only: reports whether this looks like the group's own background pattern or "
               "something unusual about this current pair; never selects a setting or blocks a recommendation.")
    return out


# ------------------------------------------------------------------------------------------------
# A4. day-to-day correlation of the pain ratings
# ------------------------------------------------------------------------------------------------

RATING_PERSISTENCE_METRICS = ("nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum")


def run_rating_persistence(uid, *, metrics=RATING_PERSISTENCE_METRICS, save=True):
    from . import rating_persistence as RP
    stream = _stream(uid)
    both_off = sorted((s for s in stretches(stream) if s["kind"] == "both off"), key=lambda s: s["start_s"])
    zero = both_off[0] if both_off else None
    rows = []
    for metric in metrics:
        t, v, mname = _ratings(uid, metric)
        if t.size == 0:
            rows.append(dict(score=mname, n_ratings=0, n_days=0, lags=[], effective_days=None,
                             ratio=None, calendar_days_needed=[], zero_ma=None))
            continue
        _days_all, daily_all = RP.daily_mean_series(_ca_days(t), v)
        row = RP.score_summary(mname, t.size, daily_all)
        row["zero_ma"] = None
        if zero is not None:
            m = (t >= zero["start_s"]) & (t < zero["end_s"])
            if m.any():
                _days_z, daily_z = RP.daily_mean_series(_ca_days(t[m]), v[m])
                row["zero_ma"] = RP.score_summary(mname, int(m.sum()), daily_z, label=zero["label"])
        rows.append(row)
    reading = RP.reading(rows)
    settings = dict(scores=list(metrics), lags_days=list(RP.LAGS_DAYS),
                    zero_ma_stretch=(zero["label"] if zero else None),
                    independent_days_needed=RP.INDEPENDENT_DAYS_NEEDED,
                    original_report="research_2026-09-25_options/02_next_clinic_visit_protocol.md, "
                                    "'Sample size and power from the record's own numbers'",
                    effective_days="Bretherton/Bartlett lag-1 correction (Biomarkers.stats_utils.effective_n), "
                                  "a daily-mean series against its own later self")
    return _finish(uid, "rating_persistence", dict(rows=rows), settings, reading, save)


# ------------------------------------------------------------------------------------------------
# A5. stepped current and bands with no plausible pain relationship
# ------------------------------------------------------------------------------------------------

def run_stepped_current_all_bands(uid, *, n_boot=2000, save=True):
    from . import stepped_current_bands as EA
    from modules.CacheStore import store as CS
    rp, _stamp = CS.load_newest("three_source_run_points", uid, consumer="stim_optimizer")
    d = EA.usable_rows(rp)
    bands, ratios = EA.per_route_pair(d, n_boot=n_boot) if len(d) else ([], [])
    reading = (EA.reading(ratios) if ratios else
              ["No stored titration-ladder points for this participant; open the Stim Optimizer "
               "page's readiness screen once to build them."])
    result = dict(bands=bands, ratios=ratios, n_rows_used=int(len(d)),
                 n_rows_total=int(len(rp)) if rp is not None else 0)
    settings = dict(family_hz=[EA.FAMILY_LO_HZ, EA.FAMILY_HI_HZ], far_below_hz=EA.FAR_BELOW_HZ,
                    far_above_hz=EA.FAR_ABOVE_HZ, model="one intercept per ladder run, straight-line "
                    "current term (decisions 126, 198)", relative_to="the band's own mean settled power "
                    "(a fraction per mA, never a log -- decisions 193-196, 202)",
                    interval="95%, resampling whole ladder runs", n_boot=n_boot,
                    excludes="bands the comparison itself flags as reading the stimulator, and any "
                            "row the comparison refused (why_not_used)")
    return _finish(uid, "stepped_current_all_bands", result, settings, reading, save)


# ------------------------------------------------------------------------------------------------

def _finish(uid, key, result, settings, reading, save):
    from modules.DecodeCommon import data_start as DS
    t, _v, _m = _ratings(uid, "nrs")
    data_from = _iso(DS.data_start_s(uid)) if DS.data_start_s(uid) else None
    data_through = _iso(t.max()) if t.size else None
    if not save:
        return dict(key=key, result=result, settings=settings, reading=reading,
                    data_from=data_from, data_through=data_through)
    return SN.save(uid, key, result, settings=settings, reading=reading, data_from=data_from,
                   data_through=data_through, run_by="ControlAnalyses.run")


RUNNERS = {"zero_ma_within_stretch": run_zero_ma, "current_explains": run_current_explains,
           "current_with_memory": run_current_with_memory, "time_of_day": run_time_of_day,
           "onoff_switches": run_onoff_switches, "carry_over_ladder": run_carry_over,
           "regression_to_mean": run_regression_to_mean,
           "rating_persistence": run_rating_persistence,
           "stepped_current_all_bands": run_stepped_current_all_bands}
