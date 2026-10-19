"""Which contact pair and band each chronic-log reading was sensed on: ONE schedule per device,
built from the settings records of every export (the PI's go-ahead, 2026-10-18; decision 487).

Until then each chronic recording carried its own export's schedule, read off that export's
`GroupHistory` as if each entry STARTED at its date, and the event-log switches of the active
group were ignored. Two faults, measured on RCS08 (scripts `_agent_bridge/_dbl_*.py`):
  1. a `GroupHistory` entry records the settings at the START of the session it is dated at (all
     132 sessions that changed sensing match that session's `Groups.Initial`, none its
     `Groups.Final`), so every change was filed one session late;
  2. a switch of active group made between sessions (event log `ActiveGroup`, old -> new) was
     ignored, so readings after it were filed under the old group's sensing.
Because two exports read different histories, 2,350 readings (one value, one current) were filed
under two labels.

THE RULE. A reading at time r takes, on its side:
  * the LEFT VIEW: the settings at the last session END at or before r (`Groups.Final`, its active
    group), with every event-log switch after that end and up to r applied. The view is void when
    a session started after that end and before r (its own end is not known);
  * the RIGHT VIEW: the settings at the first session START at or after r (`Groups.Initial`, or a
    `GroupHistory` entry, both the start-of-session settings), with the switches between r and
    that start undone (the active group at r is the first such switch's old group).
Both known and equal: that label. One known: that one. Both known and different: the right view
(the active group's start-of-session record), and the reading is FLAGGED (`ScheduleFlagged`).

The schedule is a pure function of the SET of records (deduplicated, sorted by content), so it
does not depend on the order the exports arrived (CLAUDE.md section 11). It is written as the
change-point lists every reader already takes (`ContactSchedule` [[t, "0-3"], ...],
`FreqScheduleHz` [[t, hz], ...]: the last change at or before a reading's time applies) onto every
chronic recording of the device, so all readers file a reading under the same label.

All times are on the tablet clock: the export is converted before decoding (TabletClock.py).

DECISION 488 (the PI, 2026-10-19: "File each reading under the lead it actually came from").
  * THE LEAD THE SIGNAL CAME FROM. Each export files the chronic log under each lead, but a group
    can sense ONE lead's signal for both leads' entries (RCS08: group D with adaptive stimulation,
    R 0-3 from 2026-02 to 2026-05 and group C 2026-04-16 to 04-28; L 1-3 from 2026-09-02 to
    2026-10-08): both entries' signal result names the same lead (`signal_lead`), and the
    session-report PDF prints that lead's name under the other entry's SENSING SETUP. The other
    lead's log then holds a copy of that signal. Each side's schedule says which lead its signal
    came from (`SignalLeadSchedule` [[t, "LEFT"], ...]; the lead whose log holds it when the
    settings say nothing); `DecodeCommon.representation.merge_chronic_repeats` files the copy
    under that lead and merges it with that lead's own reading. Read from the settings only:
    equal power never moves a reading.
  * FALSE SWITCHES. A logged switch whose new group is the group already in force is dropped
    (`_real_switches`); the 2026-09-10 22:52 "A -> D" switch (one export only) had filed 18
    right-lead readings under group A.
"""
import json
from datetime import datetime

import numpy as np

#: Percept bipolar sensing-channel config -> contact label, as `Session._CONTACT_LABELS`.
_CONTACT_LABELS = {
    "ZERO_AND_THREE": "0-3", "ONE_AND_THREE": "1-3", "ZERO_AND_TWO": "0-2",
    "ZERO_AND_ONE": "0-1", "TWO_AND_THREE": "2-3", "ONE_AND_TWO": "1-2",
}
SIDES = ("Left", "Right")
HEMI_TOKEN = {"Left": "LeftHemisphere", "Right": "RightHemisphere"}
#: a session START this long after the last known END means a session whose end is not known
VOID_AFTER_S = 60.0


def _t(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _groups(group_list):
    """(active group id, {group id: {side: [contact, hz]}}) of one Groups list."""
    if isinstance(group_list, dict):
        group_list = group_list.get("Final") or group_list.get("Initial") or []
    out, active = {}, None
    for g in group_list or []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("GroupId") or "").split(".")[-1]
        if not gid:
            continue
        if g.get("ActiveGroup"):
            active = gid
        ps = g.get("ProgramSettings") if isinstance(g.get("ProgramSettings"), dict) else {}
        for ch in ps.get("SensingChannel", []) or []:
            if not isinstance(ch, dict):
                continue
            hemi = str(ch.get("HemisphereLocation") or "")
            side = "Left" if "Left" in hemi else ("Right" if "Right" in hemi else None)
            contact = _CONTACT_LABELS.get(str(ch.get("Channel") or "").split(".")[-1])
            ss = ch.get("SensingSetup") if isinstance(ch.get("SensingSetup"), dict) else {}
            try:
                hz = round(float(ss.get("FrequencyInHertz")), 2)
            except (TypeError, ValueError):
                hz = None
            lead = ganged_lead(ch) or signal_lead(ss)
            if side and contact:
                out.setdefault(gid, {})[side] = [contact, hz] + ([lead] if lead else [])
    return active, out


def ganged_lead(sensing_entry):
    """The lead a sensing entry is ganged to (`GangedToHemisphere`, e.g. "HemisphereLocationDef.Left"
    -> "LEFT"), or None. On RCS08 it is set on 676 session-record entries, every one of them an
    entry whose signal result names that same other lead, and on no other (2026-10-19)."""
    g = str(sensing_entry.get("GangedToHemisphere") or "") if isinstance(sensing_entry, dict) else ""
    return "LEFT" if g.endswith("Left") else ("RIGHT" if g.endswith("Right") else None)


def signal_lead(sensing_setup):
    """The lead a sensing entry's signal comes from: the suffix of its signal result's channel
    (`SensingSetup.ChannelSignalResult.Channel`, e.g. "SensingChannelDef.ONE_THREE_LEFT" -> "LEFT"),
    or None when the entry carries none. On RCS08 every entry naming the OTHER lead belongs to a
    group whose other entry names its own lead, with the same contact pair and band (876 of 876
    entries, 2026-10-19); the session-report PDF prints that lead's name under the entry's SENSING
    SETUP (decision 488)."""
    r = sensing_setup.get("ChannelSignalResult") if isinstance(sensing_setup, dict) else None
    ch = str((r or {}).get("Channel") or "").split(".")[-1].upper() if isinstance(r, dict) else ""
    return "LEFT" if ch.endswith("_LEFT") else ("RIGHT" if ch.endswith("_RIGHT") else None)


def settings_record(JSON):
    """One export's settings record: its session start and end settings, its `GroupHistory`
    entries (start-of-session settings) and its event-log switches of active group. JSON-safe."""
    rec = {"starts": [], "ends": [], "switches": []}
    if not isinstance(JSON, dict):
        return rec
    g = JSON.get("Groups") if isinstance(JSON.get("Groups"), dict) else {}
    ts, te = _t(JSON.get("SessionDate")), _t(JSON.get("SessionEndDate"))
    if ts is not None and g.get("Initial"):
        a, gr = _groups(g.get("Initial"))
        rec["starts"].append([ts, "initial", a, gr])
    if te is not None and g.get("Final"):
        a, gr = _groups(g.get("Final"))
        rec["ends"].append([te, a, gr])
    for e in JSON.get("GroupHistory") or []:
        if not isinstance(e, dict):
            continue
        t = _t(e.get("SessionDate"))
        if t is None:
            continue
        a, gr = _groups(e.get("Groups"))
        rec["starts"].append([t, "history", a, gr])
    for e in ((JSON.get("DiagnosticData") or {}).get("EventLogs") or []):
        if not isinstance(e, dict) or "ActiveGroup" not in str(e.get("ParameterTrendId") or ""):
            continue
        t = _t(e.get("DateTime"))
        if t is None:
            continue
        rec["switches"].append([t, str(e.get("OldGroupId") or "").split(".")[-1],
                                str(e.get("NewGroupId") or "").split(".")[-1]])
    return rec


def _key(x):
    return json.dumps(x, sort_keys=True)


def union(records):
    """The union of many exports' settings records, each item once, in an order set by content.
    Two items at the same second with different settings are both kept (counted)."""
    starts, ends, switches = {}, {}, {}
    for r in records or []:
        if not isinstance(r, dict):
            continue
        for t, kind, a, gr in r.get("starts") or []:
            starts[_key([round(float(t)), a, gr])] = (float(t), a, gr)
        for t, a, gr in r.get("ends") or []:
            ends[_key([round(float(t)), a, gr])] = (float(t), a, gr)
        for t, o, n in r.get("switches") or []:
            switches[_key([round(float(t)), o, n])] = (float(t), o, n)
    order = lambda d: [d[k] for k in sorted(d, key=lambda k: (d[k][0], k))]
    U = {"starts": order(starts), "ends": order(ends)}
    U["switches"], U["switches_dropped"] = _real_switches(U["ends"], U["starts"], order(switches))
    U["conflicts"] = sum(len(v) - len({round(x[0]) for x in v}) for v in (U["starts"], U["ends"]))
    U["_et"] = [x[0] for x in U["ends"]]
    U["_st"] = [x[0] for x in U["starts"]]
    U["_wt"] = [x[0] for x in U["switches"]]
    return U


def _real_switches(ends, starts, switches):
    """The switches of active group that happened, and how many were dropped (the PI asked for the
    2026-09-10 case to be resolved, 2026-10-19; decision 488). Walked in time order carrying the
    group in force (a session end sets it to that session's final active group, a session start to
    its initial one): a switch whose NEW group is the group already in force is a false entry and
    is dropped; any other is kept and moves the group in force. On RCS08 180 of 457 distinct
    switches are false (156 name A as the old group), mostly present in one export only; the
    decision-487 rule took each one's old group as in force before it."""
    ev = sorted([(x[0], 0, x[1]) for x in ends] + [(x[0], 0, x[1]) for x in starts]
                + [(x[0], 1, x) for x in switches], key=lambda e: (e[0], e[1]))
    state, kept, dropped = None, [], 0
    for t, k, x in ev:
        if k == 0:
            state = x
            continue
        if state is not None and x[2] == state:
            dropped += 1
        else:
            kept.append(x)
            state = x[2]
    return kept, dropped


def views_at(U, r, side):
    """(left view, right view) at time r on one side: each [contact, hz] or None."""
    left, right = _views_full(U, r, side)
    return (None if left is None else list(left[:2])), (None if right is None else list(right[:2]))


def _views_full(U, r, side):
    """`views_at`, each view as stored: [contact, hz] or [contact, hz, signal lead]."""
    import bisect
    ends, starts, sw = U["ends"], U["starts"], U["switches"]
    et = U.get("_et") or [x[0] for x in ends]
    st = U.get("_st") or [x[0] for x in starts]
    wt = U.get("_wt") or [x[0] for x in sw]
    left = right = None
    i = bisect.bisect_right(et, r) - 1
    if i >= 0:
        t0, act, G = ends[i]
        k = bisect.bisect_right(st, t0 + VOID_AFTER_S)        # first start after t0 + 60 s
        if not (k < len(st) and st[k] <= r):
            for j in range(bisect.bisect_right(wt, t0), bisect.bisect_right(wt, r)):
                act = sw[j][2]
            left = (G.get(act) or {}).get(side)
    k = bisect.bisect_left(st, r)
    if k < len(st):
        t1, act, G = starts[k]
        j = bisect.bisect_right(wt, r)
        if j < len(wt) and wt[j] <= t1:
            act = sw[j][1]
        right = (G.get(act) or {}).get(side)
    return left, right


def label_at(U, r, side):
    """([contact, hz] or None, flagged) at time r on one side, by THE RULE in the module text."""
    lab, _lead, flagged = label_and_lead_at(U, r, side)
    return lab, flagged


def label_and_lead_at(U, r, side):
    """([contact, hz] or None, the lead the signal comes from ("LEFT"/"RIGHT", or None when the
    settings do not say), flagged) at time r on one side. The label and the flag follow THE RULE on
    contact and band alone; the lead is the chosen view's, else the other view's when it names the
    same contact and band."""
    left, right = _views_full(U, r, side)
    lead_of = lambda v: v[2] if v is not None and len(v) > 2 else None
    if left is not None and right is not None:
        same = list(left[:2]) == list(right[:2])
        chosen, other, flagged = (right, left, not same)
    else:
        chosen = left if left is not None else right
        other, same, flagged = None, False, False
    if chosen is None:
        return None, None, False
    lead = lead_of(chosen) or (lead_of(other) if same else None)
    return list(chosen[:2]), lead, flagged


def side_schedules(U):
    """Per side: the change-point lists every chronic reader takes, and the stretches flagged.
    The views only change at a record or switch time, so the label of each stretch between two
    such times is the label at its middle; a stretch with no known label keeps the one before.

    NO SETTINGS RECORD OF ITS OWN (decision 488). A stretch whose views give no label -- before the
    first record that names this side's sensing, or under a record whose active group lists no
    sensing -- is listed in ``ScheduleNoRecord``. Before the first labelled stretch it takes that
    stretch's label, written explicitly from time 0 (every reader already took the first change
    point for a reading before it, so no reading's label moves); later ones keep the one before.
    On RCS08 the first labelled stretch starts 2025-07-16 18:16:20; every reading before it (the
    pre-implant log and the implant day up to that time) is listed."""
    B = sorted({x[0] for x in U["ends"]} | {x[0] for x in U["starts"]} | {x[0] for x in U["switches"]})
    out = {}
    if not B:
        return out
    probes = [(0.0, B[0] - 1.0)] + [(B[i], 0.5 * (B[i] + B[i + 1])) for i in range(len(B) - 1)] + [(B[-1], B[-1] + 1.0)]
    for side in SIDES:
        contact, freq, flagged, unknown, leads, norec = [], [], [], 0, [], []
        last = None
        own = side.upper()
        for i, (t_cp, r) in enumerate(probes):
            lab, lead, flag = label_and_lead_at(U, r, side)
            if lab is None:
                unknown += 1
                t_end = probes[i + 1][0] if i + 1 < len(probes) else None   # open end: null (decision 490)
                if norec and norec[-1][1] == t_cp:
                    norec[-1][1] = t_end
                else:
                    norec.append([t_cp, t_end])
                lab = last
                lead = leads[-1][1] if leads else None      # a stretch with no label keeps the one before
            if lab is None:
                continue
            # the settings name no lead: the reading stays under the lead whose log holds it
            lead = lead or own
            if not leads or leads[-1][1] != lead:
                leads.append([t_cp, lead])
            if not contact or contact[-1][1] != lab[0]:
                contact.append([t_cp, lab[0]])
            if lab[1] is not None and (not freq or freq[-1][1] != lab[1]):
                freq.append([t_cp, lab[1]])
            if flag:
                t_end = probes[i + 1][0] if i + 1 < len(probes) else None   # open end: null (decision 490)
                if flagged and flagged[-1][1] == t_cp:
                    flagged[-1][1] = t_end
                else:
                    flagged.append([t_cp, t_end])
            last = lab
        if contact:
            for lst in (contact, freq, leads):        # the first label, from time 0 (see above)
                if lst:
                    lst[0][0] = min(float(lst[0][0]), 0.0)
            out[HEMI_TOKEN[side]] = {"ContactSchedule": contact, "FreqScheduleHz": freq,
                                     "ScheduleFlagged": flagged, "stretches_unknown": unknown,
                                     "SignalLeadSchedule": leads, "ScheduleNoRecord": norec}
    return out


def restamp_device_chronic(source_files, recordings_by_source, save=True):
    """Write the one schedule onto every chronic recording of one device's exports.

    `source_files`: the device's export rows, each with `metadata["SensingSettingsRecord"]`;
    `recordings_by_source`: {source uid: [chronic Recording rows]}. Returns counts. Exports with no
    settings record add nothing (counted)."""
    records, missing = [], 0
    for sf in source_files:
        rec = (getattr(sf, "metadata", None) or {}).get("SensingSettingsRecord")
        if rec is None:
            missing += 1
        else:
            records.append(rec)
    U = union(records)
    sched = side_schedules(U)
    n = changed = 0
    for sf in source_files:
        for row in recordings_by_source.get(str(sf.uid), []):
            md = row.metadata if isinstance(row.metadata, dict) else {}
            chans = md.get("ChannelNames") or []
            hemi = str(chans[0]).split(" ")[0] if chans else ""
            s = sched.get(hemi)
            n += 1
            if not s:
                continue
            new = dict(md, ContactSchedule=s["ContactSchedule"], FreqScheduleHz=s["FreqScheduleHz"],
                       ScheduleFlagged=s["ScheduleFlagged"], SignalLeadSchedule=s["SignalLeadSchedule"],
                       ScheduleNoRecord=s["ScheduleNoRecord"],
                       ScheduleSource="one schedule from every export of the device (decisions 487, 488)")
            if new != md:
                changed += 1
                if save:
                    row.metadata = new
                    row.save()
    return {"exports": len(source_files), "exports_without_record": missing, "chronic_recordings": n,
            "restamped": changed, "conflicts": U["conflicts"], "switches_dropped": U["switches_dropped"],
            "flagged_stretches": {h: len(v["ScheduleFlagged"]) for h, v in sched.items()}}
