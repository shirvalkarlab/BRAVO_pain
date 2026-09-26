"""The device's sensing-pair rule: which pair of contacts a lead may sense on while it stimulates.

THE RULE (decision 217; the PI, 2026-09-20). While a lead stimulates, BrainSense senses only on the
two contacts immediately flanking the stimulating contact or contacts: stimulate on 1 and sense
0-2, on 2 and sense 1-3, on 1 and 2 together and sense 0-3; stimulating on 0 or 3 leaves no pair
(the three configurations per lead of the BrainSense tip card pp. 7-8 and the white paper p. 8;
A610 p. 36 sends such a lead to the other side). It is read per lead from the cathode in force.

WHY IT LIVES HERE (2026-09-26). Three pages apply it: the Stim Optimizer's readiness card (decision
243's `closed_loop.sensing_rule` block), the Closed-Loop page's device rule D52 (decision 247) and
the Biomarkers heat maps, which mark the pairs the device refuses today. The arithmetic was the Stim
Optimizer's, and Biomarkers may not import the Stim Optimizer (decision 234: the dependency runs the
other way), so it moved to DecodeCommon, which every analysis package may import. The Stim
Optimizer's old names (`bravo_service.stim_rings`, `sensing_rule_block`, `lfp_evidence
.flanking_pair`, `pair_flanks_stimulation`, `sensing_pair_rings`, `titration_plan
.stim_rings_for_sensing_pair`) are delegations to this module, so no caller changed its import;
`tests/test_sensing_rule.py` fails if a second definition comes back.

NOTHING HERE READS A DATABASE OR THE STORE. The caller supplies the contacts in force; the page's
labels ("L 1⁻3⁺") come from the caller too (`display_of`), because the formatter is the Biomarkers
page's (`analytics.format_channel`) and this package imports no analysis module.
"""

#: Ring number to the word the channel names spell it with.
RING_NAMES = ("ZERO", "ONE", "TWO", "THREE")
_RING_WORDS = {"ZERO": 0, "ONE": 1, "TWO": 2, "THREE": 3}

#: The decision that states the rule, carried on every block.
DECISION = 217


def stim_rings(cathode) -> set:
    """The ring numbers a programmed cathode stimulates on: "2a-2b-2c" -> {2},
    "1a-1b-1c-2a-2b-2c" -> {1, 2}; empty for none / blank / NaN."""
    if cathode is None:
        return set()
    raw = str(cathode).strip()
    if not raw or raw.lower() in ("none", "nan", "case"):
        return set()
    out = set()
    for t in raw.replace("+", "-").split("-"):
        digit = "".join(ch for ch in t if ch.isdigit())
        if digit:
            out.add(int(digit))
    return out


def sensing_pair_rings(channel):
    """The two ring numbers of a bipolar sensing channel name (``ZERO_TWO_LEFT`` -> (0, 2)), or
    None when the name does not carry two ring words."""
    words = [w for w in str(channel or "").upper().split("_") if w in _RING_WORDS]
    if len(words) != 2:
        return None
    a, b = _RING_WORDS[words[0]], _RING_WORDS[words[1]]
    return (min(a, b), max(a, b))


def flanking_pair(stim_rings):
    """The one sensing pair the device allows for a set of stimulating rings on a lead: the two
    contacts immediately flanking them -- (1, 3) for contact 2, (0, 2) for contact 1, (0, 3) for
    contacts 1 and 2 together; None for contact 0 or 3 (nothing flanks them), an empty set, or a
    non-contiguous set (decision 217; the three configurations per lead of the BrainSense tip
    card p. 7-8 and the white paper p. 8)."""
    rings = sorted({int(r) for r in (stim_rings or set())})
    if not rings or rings != list(range(rings[0], rings[-1] + 1)):
        return None
    lo, hi = rings[0] - 1, rings[-1] + 1
    return (lo, hi) if 0 <= lo and hi <= 3 else None


def pair_flanks_stimulation(channel, stim_rings):
    """Is this sensing pair the one the device allows with these stimulating rings on its lead?
    None when the pair cannot be read or no stimulating ring is given."""
    pair = sensing_pair_rings(channel)
    if pair is None or not stim_rings:
        return None
    return pair == flanking_pair(stim_rings)


def stim_rings_for_sensing_pair(channel):
    """The stimulating rings a sensing pair REQUIRES: the inverse of the flanking rule
    (`flanking_pair`, decision 217). (0, 3) needs {1, 2}; (0, 2) needs {1}; (1, 3) needs {2}; a
    pair with nothing between its contacts, or a name that is not a pair, gives None."""
    pair = sensing_pair_rings(channel)
    if pair is None:
        return None
    lo, hi = pair
    inner = set(range(lo + 1, hi))
    return inner or None


def channel_for_pair(pair, side) -> str:
    """The channel name for a ring pair on a lead: ((1, 3), "Left") -> "ONE_THREE_LEFT"."""
    return f"{RING_NAMES[pair[0]]}_{RING_NAMES[pair[1]]}_{str(side).upper()}"


def rings_in_force_by_side(stream):
    """The stimulating contacts in force per lead, from the device's own dated settings stream.

    ``stream`` is the settings stream's frame (the raw store kind ``therapy_settings``: one row per
    timestamp and side, with ``t``, ``hemi`` and ``cathode``). A lead's contacts in force are its
    NEWEST row's cathode -- a setting holds until the next one is filed. Returns
    ``{"Left": {"rings", "cathode", "newest_row_utc"}, "Right": {...}}`` (``newest_row_utc`` is
    when that newest row was filed -- a session that read the device -- not when the contacts were
    programmed); a lead with no row, or a frame
    without the columns, gives no rings and no cathode, which applies no rule (never a guess).
    """
    out = {side: {"rings": set(), "cathode": None, "newest_row_utc": None} for side in ("Left", "Right")}
    cols = set(getattr(stream, "columns", ()))
    if stream is None or not {"t", "hemi", "cathode"} <= cols or not len(stream):
        return out
    import pandas as pd                                      # local: only this reader needs it

    t = pd.to_datetime(stream["t"], utc=True, errors="coerce")
    hemi = stream["hemi"].astype(str)
    for side in out:
        mask = (hemi == side) & t.notna()
        if not bool(mask.any()):
            continue
        idx = t[mask].sort_values(kind="stable").index[-1]
        cath = stream.loc[idx, "cathode"]
        cath = None if cath is None or (isinstance(cath, float) and cath != cath) else str(cath)
        out[side] = {"rings": stim_rings(cath), "cathode": cath,
                     "newest_row_utc": t[idx].isoformat()}
    return out


def sensing_rule_block(rings_by_side, *, cells=None, n_screened=None, n_usable=None,
                       display_of=None, extra_by_side=None) -> dict:
    """The rule stated ONCE for a page, per lead, in the shape every page reads (decision 243).

    Per lead: the rings it stimulates on today (``stim_rings``), whether a rule applies
    (``rule_applied``: False when no stimulating contact is on record), the one sensing pair the
    device then allows (``allowed_pair``, ``allowed_channel``, and the page label
    ``allowed_display`` from ``display_of(channel)``, the channel name where that gives nothing),
    and ``why`` in words. A lead stimulating on an end contact allows no pair and says so.

    THE COUNT IS THE READINESS SCREEN'S, AND ONLY WHERE THERE IS ONE. The Stim Optimizer passes
    ``cells`` (its screened rows with ``channel`` and ``deployable``), ``n_screened`` and
    ``n_usable``; each lead then carries how many rows on its allowed pair are usable, and the
    sentence ends with the count it explains -- word for word as that card has printed it since
    decision 243. A page with no screen (the heat maps) passes none of them: the per-lead count is
    None, never 0, and the sentence says what a band on another pair means instead.

    ``extra_by_side`` adds fields to a lead's row (the Biomarkers page's cathode as written and when
    it came into force); it never replaces a field the rule itself sets.
    """
    counted = n_screened is not None or n_usable is not None
    by_side, named = {}, []
    for side in ("Left", "Right"):
        rings = sorted(int(r) for r in ((rings_by_side or {}).get(side) or set()))
        row = {"stim_rings": rings, "rule_applied": bool(rings), "allowed_pair": None,
               "allowed_channel": None, "allowed_display": None,
               "n_usable_on_allowed_pair": 0 if counted else None, "why": None}
        if not rings:
            row["why"] = "no stimulating contact is recorded in force on this lead, so no rule is applied"
        else:
            pair = flanking_pair(set(rings))
            if pair is None:
                row["why"] = (f"this lead stimulates on contact(s) {', '.join(map(str, rings))}, "
                              f"which nothing flanks on both sides, so the device allows no "
                              f"sensing pair on it")
            else:
                ch = channel_for_pair(pair, side)
                row.update(allowed_pair=[int(pair[0]), int(pair[1])], allowed_channel=ch,
                           allowed_display=(display_of(ch) if display_of else None) or ch)
                if counted:
                    row["n_usable_on_allowed_pair"] = int(sum(
                        1 for c in (cells or ()) if str(c.get("channel")) == ch
                        and c.get("deployable") is True))
                row["why"] = (f"stimulating on contact(s) {', '.join(map(str, rings))}, the device "
                              f"senses only on the two contacts flanking them")
                named.append(row)
        for k, v in ((extra_by_side or {}).get(side) or {}).items():
            row.setdefault(k, v)
        by_side[side] = row
    if counted:
        n_s = int(n_screened or 0)
        n_u = int(n_usable or 0)
        if named:
            pairs = " and ".join(r["allowed_display"] for r in named)
            usable_named = [r for r in named if r["n_usable_on_allowed_pair"] > 0]
            if not usable_named:
                which = ("neither has a usable band" if len(named) == 2 else "it has no usable band")
            else:
                which = " and ".join(f"{r['allowed_display']} has {r['n_usable_on_allowed_pair']} usable"
                                     for r in usable_named)
            sentence = (f"While today's contacts are stimulating, the device allows one sensing pair per "
                        f"lead: {pairs}. {which[0].upper() + which[1:]}, so {n_u} of {n_s} "
                        f"contact-and-rate combinations are usable for closed loop.")
        else:
            sentence = (f"No sensing pair is allowed by today's stimulating contacts on either lead, so "
                        f"{n_u} of {n_s} combinations are usable for closed loop.")
    elif named:
        pairs = " and ".join(r["allowed_display"] for r in named)
        sentence = (f"While today's contacts are stimulating, the device allows one sensing pair per "
                    f"lead: {pairs}. A band found on any other pair cannot drive closed loop without "
                    f"moving the stimulating contacts.")
    else:
        sentence = ("Today's stimulating contacts name no allowed sensing pair on either lead; each "
                    "lead's reason is given beside it.")
    return {"by_side": by_side, "sentence": sentence, "decision": DECISION}
