"""The correction across the band choices: a Benjamini-Hochberg q beside each band, a LABEL AND
WARNING ONLY (wave 2, C9; the PI, 2026-10-18: "correction family = the allowed sensing pairs x 22
centres x the choosing sources, for the CURRENT pain score only"; 2026-10-21: a label and warning,
like C6-C8).

ONE FAMILY PER CONTACT PAIR (the PI, 2026-10-21: "the multiple comparisons correction Q should
only be corrected on each bipolar contact pair separately ... the left side ... should be corrected
... independently from the right side"). Each allowed pair is corrected over its own bands only;
no pair's p values enter another pair's q.

WHAT EACH FAMILY IS. Every band that could be chosen for closed loop on one allowed pair under
today's contacts, for the one pain score the request asks for:
  * the sensing pairs the device allows while today's contacts stimulate (decision 217's rule,
    `DecodeCommon.sensing_rule`, read from the contacts in force when the grid is read; never typed
    in here: with RCS08 stimulating on contacts 1 and 2 of both leads that is L 0-3 and R 0-3);
  * x the band centres each pair's grid built (22 when nothing is missing);
  * x the sources that choose a band since C4 and C5: the TD-only grid's correlation rows, and the
    chronic log's answer where it decides the band (`choice_source: "chronic"`). Each band is
    counted ONCE, by the rotation p of the source that decides it: the chronic answer's
    `p_rotation` where the chronic log decides, else the TD-only row's `p_selection_aware` (its
    rotation p, chosen as the best of the lengths of signal). PSD-only and mixed rows never choose,
    and the area-under-the-curve rows are the same bands again, so none of them is in the family.
No p is computed here; a band with no p is left out and counted, never given another source's p.

WHAT q DOES. Nothing that decides. It is shown beside each band (`family_q`), and on a band that is
"established" (the row's answer) or "supported" (decision 210: rises with pain, its interval wholly
above zero) whose q is above `Q_WARN`, a plain warning is appended to `why`. No answer, status,
verdict, gate or p reads it. The per-grid q over one pair's 22 centres (`family_wise_q_8_to_30hz`,
decision 63) stays beside it.

WHERE IT IS PUT ON. When a grid is READ, never stored (like the stability answers, decision 185):
the contacts in force change without the recordings or the ratings changing, so a stored q could be
served stale, and no store key changes. The Biomarkers grid response (`attach`, after the sensing
rule is attached) and the Closed-Loop reader (`ClosedLoopDeployment.adapter
.band_sweep_grid_for_closed_loop`, on its choosing view, `correct`) both call it; the Closed-Loop
sign-off summary carries its band's q (`summary_block`). The band tables (`band_results_tables`) do
not carry q: they are written with the grid and filed under its key, so a q in them would be stored.

`BRAVO_FAMILY_CORRECTION=0` is the neutral setting: the path is skipped, the response is returned
as it was given.

No Django: the callers hand in the grid and the rule block.
"""
from __future__ import annotations

import os as _os

import numpy as np

from . import sweep_settings as _sw
from .stats_utils import bh_fdr

try:                                                     # the container's spelling, then the host's
    from modules.DecodeCommon import sensing_rule as _sensing_rule
except ImportError:                                      # pragma: no cover
    from DecodeCommon import sensing_rule as _sensing_rule

#: The neutral setting (`BRAVO_FAMILY_CORRECTION=0`): skip the path entirely.
ENABLED = _os.environ.get("BRAVO_FAMILY_CORRECTION", "1").strip() != "0"
#: A band that reads established or supported with q above this gets the warning.
Q_WARN = 0.05
METHOD = "Benjamini-Hochberg"
DECISION_RULE = 217

STATUS_IN = "in the family"
STATUS_NOT_ALLOWED = "not an allowed sensing pair"
STATUS_NO_P = "no p on this band, so not in the family"
STATUS_NEVER_CHOOSES = "never chooses a band (PSD-only or mixed grid), so not in the family"
STATUS_AUC = ("area under the curve: not in the family (each band is counted once, by the p of the "
              "source that decides its correlation)")
STATUS_NO_RULE = "no sensing-pair rule on record (no contacts in force), so no family is formed"
STATUS_NO_TD = "this pair has no TD-only grid, so none of its bands is in the family"

#: The fields this puts on a row (the band tables leave them out; see the module note).
ROW_FIELDS = ("family_q", "family_p", "family_p_source", "family_q_status", "family_q_warning",
              "family_n")
#: The start of the warning, as it is appended to `why`.
WARNING_HEAD = "After correcting for the"

NOT_STORED = ("attached when the grid is read, never part of its key or payload: the family follows "
              "the contacts in force, which change without the recordings or the ratings changing")
WHAT = ("Benjamini-Hochberg q within each sensing pair the device allows under today's contacts, "
        "corrected separately per pair: that pair's band centres built, each band once, by the rotation p "
        "of the source that decides it (the chronic log where it decides, else the TD-only grid), "
        "for this pain score only. A label and warning only: it changes no answer, status, verdict, "
        "gate or p")


def allowed_pairs(rule_block):
    """``{channel: side}`` of the sensing pairs the rule allows, read off a `sensing_rule_block`
    (``by_side[side].allowed_channel``). Empty when no rule is on record or no lead has a pair."""
    out = {}
    if not isinstance(rule_block, dict) or rule_block.get("available") is False:
        return out
    for side, row in (rule_block.get("by_side") or {}).items():
        ch = (row or {}).get("allowed_channel")
        if ch and (row or {}).get("rule_applied", True):
            out[str(ch)] = str(side)
    return out


def rule_block_for_participant(participant_uid):
    """The sensing rule with today's contacts, as the Biomarkers heat maps read it (the settings
    stream's newest row per lead, `stim_current.contacts_in_force`), for callers that hold no grid
    response with the block on it (the Closed-Loop reader, the sign-off summary). No contacts on
    record, or a failed read: ``{"available": False, ...}`` with the reason. Never raises."""
    from . import stim_current as _sc
    try:
        got = _sc.contacts_in_force(participant_uid)
    except Exception as exc:                                    # noqa: BLE001 - a label only
        return {"available": False, "by_side": {},
                "reason": f"reading the dated stimulation settings raised {exc!r}"}
    if got is None:
        return {"available": False, "by_side": {},
                "reason": "no dated stimulation settings have been filed for this participant"}
    by = got.get("by_side") or {}
    blk = _sensing_rule.sensing_rule_block({s: (v or {}).get("rings") for s, v in by.items()})
    blk["available"] = True
    return blk


def _finite(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _decides_chronic(row):
    return (row.get("decided_by") == "chronic"
            or (row.get("choice_source") == "chronic" and bool((row.get("chronic") or {}).get("covered"))))


def deciding_p(row):
    """``(p, source)``: the rotation p of the source that decides this band. The chronic answer's
    ``p_rotation`` where the chronic log decides (``choice_source: "chronic"``, covered), else the
    row's own ``p_selection_aware``. None when that source has no p (never the other source's)."""
    if _decides_chronic(row):
        return _finite((row.get("chronic") or {}).get("p_rotation")), "chronic"
    return _finite(row.get("p_selection_aware")), "TD"


def _deciding_view(row):
    """The row as the band is decided: a row already in the choosing view as it is; a raw TD row
    whose band the chronic log decides, through `sweep_settings.chronic_decides` (a copy)."""
    if row.get("decided_by") == "chronic" or row.get("choice_source") != "chronic":
        return row
    return _sw.chronic_decides(row)


def standing(row):
    """"established" (the deciding answer), "supported" (decision 210: rises with pain, interval
    wholly above zero), or None."""
    v = _deciding_view(row)
    if str(v.get("answer") or "") == "established":
        return "established"
    r, lo = _finite(v.get("pearson_r")), _finite(v.get("pearson_r_low"))
    if r is not None and lo is not None and r > 0 and lo > 0:
        return "supported"
    return None


def _append(why, text):
    if not text:
        return why
    return text if not why else str(why) + ". " + text


def _views(sweep):
    """``(choosing grid or None, [every grid on the pair], why none)`` for one pair's sweep, in
    either the Biomarkers view (the mixed grid with ``by_source_grid``) or the choosing view the
    Closed-Loop reader serves (`sweep_settings.choosing_sweep`)."""
    if not isinstance(sweep, dict):
        return None, [], STATUS_NO_TD
    by = sweep.get("by_source_grid")
    if isinstance(by, dict):
        grids = [sweep] + [g for g in by.values() if isinstance(g, dict)]
        if _sw.CHOOSING_GRID == "mixed":
            return sweep, grids, None
        td = by.get(_sw.GRID_SOURCE_TD)
        return (td if isinstance(td, dict) else None), grids, (None if isinstance(td, dict)
                                                                else STATUS_NO_TD)
    cg = sweep.get("choosing_grid")
    if cg == "none":
        return None, [sweep], STATUS_NO_TD
    return sweep, [sweep], None                   # the choosing view, or a grid before C4


def _copy_sweep(sweep):
    """A copy of one pair's sweep with every grid dict and every best row copied, so nothing the
    store or another reader holds is changed."""
    out = dict(sweep)
    for key in ("best_correlation_rows", "best_auc_rows"):
        if isinstance(out.get(key), list):
            out[key] = [dict(r) if isinstance(r, dict) else r for r in out[key]]
    by = out.get("by_source_grid")
    if isinstance(by, dict):
        nb = {}
        for name, g in by.items():
            if isinstance(g, dict):
                g = dict(g)
                for key in ("best_correlation_rows", "best_auc_rows"):
                    if isinstance(g.get(key), list):
                        g[key] = [dict(r) if isinstance(r, dict) else r for r in g[key]]
            nb[name] = g
        out["by_source_grid"] = nb
    return out


def _blank(row, status):
    row.update(family_q=None, family_p=None, family_p_source=None, family_q_status=status,
               family_q_warning=None, family_n=None)


def _label(sweep, ch):
    return (sweep or {}).get("display_short") or str(ch)


def correct(sweeps, rule_block, *, label_metric=None):
    """``(new sweeps, block)``: every best row of every pair's grids labelled (copies; the input is
    never changed), and the family's own block. See the module note for the family and the rule."""
    allowed = allowed_pairs(rule_block)
    rule_ok = isinstance(rule_block, dict) and rule_block.get("available") is not False
    new = {ch: _copy_sweep(sw) if isinstance(sw, dict) else sw for ch, sw in (sweeps or {}).items()}
    family, n_built, missing = [], 0, []
    for ch, sw in new.items():
        choosing, grids, why_none = _views(sw)
        for g in grids:
            for r in g.get("best_correlation_rows") or []:
                if isinstance(r, dict) and g is not choosing:
                    _blank(r, STATUS_NEVER_CHOOSES)
            for r in g.get("best_auc_rows") or []:
                if isinstance(r, dict):
                    _blank(r, STATUS_AUC if g is choosing else STATUS_NEVER_CHOOSES)
        if choosing is None:
            if ch in allowed:
                missing.append({"channel": ch, "display": _label(sw, ch), "why": why_none})
            continue
        for r in choosing.get("best_correlation_rows") or []:
            if not isinstance(r, dict):
                continue
            p, src = deciding_p(r)
            if p is not None:
                n_built += 1
            if not rule_ok:
                _blank(r, STATUS_NO_RULE)
            elif ch not in allowed:
                _blank(r, STATUS_NOT_ALLOWED)
            elif p is None:
                _blank(r, STATUS_NO_P)
                r["family_p_source"] = src
            else:
                family.append((r, p, src, ch))
    for ch in allowed:
        if ch not in new:
            missing.append({"channel": ch, "display": ch,
                            "why": "this pair is not on the grid, so none of its bands is in the family"})
    labels = [_label(new.get(ch), ch) for ch in sorted(allowed)]
    pairs_txt = ", ".join(labels)
    n = len(family)
    q = np.full(n, np.nan)
    per_pair = {}
    for ch in sorted({c for _r, _p, _s, c in family}):          # one correction per pair
        idx = [i for i, f in enumerate(family) if f[3] == ch]
        q[idx] = bh_fdr(np.array([family[i][1] for i in idx], dtype=float))
        per_pair[ch] = {"display": _label(new.get(ch), ch), "n_in_family": len(idx),
                        "smallest_p": min(family[i][1] for i in idx),
                        "smallest_q": float(np.min(q[idx])),
                        "n_q_at_most_q_warn": int(np.sum(q[idx] <= Q_WARN))}
    n_warned = 0
    for (r, p, src, ch), qi in zip(family, q):
        qv = float(qi)
        k = per_pair[ch]["n_in_family"]
        r.update(family_q=qv, family_p=p, family_p_source=src, family_q_status=STATUS_IN,
                 family_q_warning=None, family_n=k)
        st = standing(r)
        if st is not None and qv > Q_WARN:
            w = (f"{WARNING_HEAD} {k} bands tested on {per_pair[ch]['display']}, "
                 f"this band's q is {qv:.2f}: it may be a chance finding")
            r["family_q_warning"] = w
            r["why"] = _append(r.get("why"), w)
            n_warned += 1
            per_pair[ch]["n_warned"] = per_pair[ch].get("n_warned", 0) + 1
    ps = [p for _r, p, _s, _c in family]
    block = {
        "available": bool(rule_ok and allowed),
        "method": METHOD, "q_warn": Q_WARN, "pain_score": label_metric,
        "allowed_pairs": sorted(allowed), "allowed_pairs_display": labels,
        "pairs_outside": sorted(ch for ch in new if ch not in allowed),
        "n_in_family": n, "n_built": int(n_built),
        "n_from_chronic": sum(1 for _r, _p, s, _c in family if s == "chronic"),
        "n_from_td": sum(1 for _r, _p, s, _c in family if s == "TD"),
        "per_pair": per_pair, "corrected_per_pair": True,
        "missing": missing,
        "smallest_p": (min(ps) if ps else None),
        "smallest_q": (float(np.min(q)) if n else None),
        "n_q_at_most_q_warn": int(np.sum(q <= Q_WARN)) if n else 0,
        "n_warned": n_warned,
        "words": ((f"corrected within each pair separately: "
                   + "; ".join(f"{v['display']} across {v['n_in_family']} bands"
                               for v in per_pair.values())
                   + f" ({n_built} built; each band once, by the p of the source that decides it)")
                  if per_pair else f"no allowed pair has bands to correct (allowed: {pairs_txt or 'none'})"
                  if rule_ok else STATUS_NO_RULE),
        "what": WHAT, "not_stored": NOT_STORED, "rule_decision": DECISION_RULE,
        "rule_reason": (None if rule_ok else (rule_block or {}).get("reason")),
    }
    return new, block


def attach(resp, rule_block=None):
    """A grid response with `correct` applied: its ``band_time_sweep`` replaced by the labelled copy
    and ``family_correction`` added. The rule is the response's own ``sensing_rule`` block unless one
    is given. A copy; the response is returned as it was when the switch is off or it holds no grid.
    Never raises."""
    if not ENABLED or not isinstance(resp, dict) or not isinstance(resp.get("band_time_sweep"), dict):
        return resp
    try:
        rule = rule_block if rule_block is not None else resp.get("sensing_rule")
        sweeps, block = correct(resp["band_time_sweep"], rule, label_metric=resp.get("label_metric"))
    except Exception as exc:                                    # noqa: BLE001 - a label only
        out = dict(resp)
        out["family_correction"] = {"available": False, "words": f"the correction failed ({exc!r})"}
        return out
    out = dict(resp)
    out["band_time_sweep"] = sweeps
    out["family_correction"] = block
    return out


def band_block(sweeps, block, channel, centre):
    """One band's q, for the sign-off summary: its row's family fields on the pair's choosing grid,
    with the family's words. A band not on the grid says so."""
    sw = (sweeps or {}).get(str(channel))
    choosing, _grids, _why = _views(sw)
    row = None
    for r in (choosing or {}).get("best_correlation_rows") or []:
        if isinstance(r, dict) and _finite(r.get("band_center_hz")) == _finite(centre):
            row = r
            break
    out = {k: (row or {}).get(k) for k in ROW_FIELDS}
    if row is None:
        why = next((m.get("why") for m in ((block or {}).get("missing") or [])
                    if m.get("channel") == str(channel)), None)
        out["family_q_status"] = ("this band is not on the grid" if choosing is not None
                                  else why or STATUS_NO_TD)
    for k in ("words", "n_in_family", "n_built", "allowed_pairs", "allowed_pairs_display",
              "pain_score", "method"):
        out[k] = (block or {}).get(k)
    return out


def summary_block(participant_uid, request_data, channel, centre, *, load_newest=None):
    """The sign-off summary's band q: the stored grid under the summary's own pain score and
    settings (the same tag and rule the Closed-Loop reader matches; never built here), its choosing
    view, corrected with today's contacts. The summary always matches its reports "prior" (the
    Closed-Loop page's request), while the grid a band is chosen from is built at the Biomarkers
    page's direction, so when no grid is stored at the summary's own direction the newest grid that
    agrees on every other setting is read, and the block names its direction
    (`grid_match_direction`). No stored grid: the reason, no q. Never raises."""
    try:
        want = _sw.sweep_settings_tag_from_request(request_data or {})
        if load_newest is None:
            try:
                from modules.CacheStore import store as _st
            except ImportError:                                  # pragma: no cover
                from CacheStore import store as _st
            load_newest = _st.load_newest

        def _matcher(ignore_direction):
            def _match(meta):
                tag = dict(((meta.get("extra") or {}).get("sweep_settings") or {}))
                w = dict(want)
                if ignore_direction:
                    tag.pop("match_direction", None)
                    w.pop("match_direction", None)
                return bool(tag) and tag == w and _sw.grid_written_under_rule_in_force(meta)
            return _match

        payload = stamp = None
        for ignore in (False, True):
            payload, stamp = load_newest(_sw.GRID_KIND, participant_uid, consumer="closed_loop",
                                         match=_matcher(ignore))
            if isinstance(payload, dict) and payload.get("band_time_sweep"):
                break
        if not isinstance(payload, dict) or not payload.get("band_time_sweep"):
            return {"family_q": None, "family_q_status": ("no stored grid under this summary's pain "
                                                          "score and settings, so no q"),
                    "family_q_warning": None}
        choosing = _sw.choosing_grid(payload).get("band_time_sweep") or {}
        sweeps, block = correct(choosing, rule_block_for_participant(participant_uid),
                                label_metric=want.get("sweep_metric"))
        out = band_block(sweeps, block, channel, centre)
        out["grid_match_direction"] = (((stamp or {}).get("extra") or {}).get("sweep_settings")
                                       or {}).get("match_direction")
        return out
    except Exception as exc:                                    # noqa: BLE001 - a label only
        return {"family_q": None, "family_q_status": f"the correction failed ({exc!r})",
                "family_q_warning": None}
