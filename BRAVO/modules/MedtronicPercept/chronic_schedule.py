"""One chronic sensing schedule from the complete set of an implant's exports.

At a reading's time, use the last session-end settings with intervening active-group
switches applied (left view), and the next session-start settings with intervening
switches undone (right view). A later session with no known end voids the left view.
Equal views agree; if both differ, choose the right view and flag the interval.
One known view is used alone. No known view is labeled unverified.

The union is deterministic and retains conflicting records. Signal-lead assignments
come from explicit settings, never equal measured power. False switches into the
already active group are dropped. All times use the canonical tablet clock.
Decisions 487, 488 and 490; participant evidence remains in private provenance."""
import json
import math
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
    """Lead explicitly named by GangedToHemisphere, or None when absent."""
    g = str(sensing_entry.get("GangedToHemisphere") or "") if isinstance(sensing_entry, dict) else ""
    return "LEFT" if g.endswith("Left") else ("RIGHT" if g.endswith("Right") else None)


def signal_lead(sensing_setup):
    """Lead explicitly named by SensingSetup.ChannelSignalResult.Channel, or None."""
    r = sensing_setup.get("ChannelSignalResult") if isinstance(sensing_setup, dict) else None
    ch = str((r or {}).get("Channel") or "").split(".")[-1].upper() if isinstance(r, dict) else ""
    return "LEFT" if ch.endswith("_LEFT") else ("RIGHT" if ch.endswith("_RIGHT") else None)


def validate_settings_record(record):
    """Validate an explicitly prepared record; missing/malformed is never an empty record.

    Return the unchanged record on success. Only JSON-safe, finite, known shapes
    enter the schedule union. In particular, all three collections must exist;
    {"starts": [], "ends": [], "switches": []} is a valid prepared empty record.
    """
    def finite(value):
        try:
            return type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            return False

    def group_id(value, optional=False):
        return (optional and value is None) or (isinstance(value, str) and bool(value))

    def groups(value):
        if not isinstance(value, dict):
            raise ValueError("Malformed sensing group table")
        for gid, sides in value.items():
            if not group_id(gid) or not isinstance(sides, dict):
                raise ValueError("Malformed sensing group")
            for side, label in sides.items():
                if side not in SIDES or not isinstance(label, list) or len(label) not in (2, 3):
                    raise ValueError("Malformed sensing label")
                if label[0] not in _CONTACT_LABELS.values():
                    raise ValueError("Unknown sensing contact")
                if label[1] is not None and (not finite(label[1]) or label[1] <= 0):
                    raise ValueError("Invalid sensing frequency")
                if len(label) == 3 and label[2] not in ("LEFT", "RIGHT"):
                    raise ValueError("Invalid signal lead")

    if not isinstance(record, dict) or set(record) != {"starts", "ends", "switches"}:
        raise ValueError("Missing or malformed sensing settings record")
    for name, size in (("starts", 4), ("ends", 3), ("switches", 3)):
        if not isinstance(record[name], list):
            raise ValueError("Malformed sensing record collection")
        for item in record[name]:
            if not isinstance(item, list) or len(item) != size or not finite(item[0]):
                raise ValueError("Malformed sensing record event")
            if name == "switches":
                if not group_id(item[1]) or not group_id(item[2]):
                    raise ValueError("Malformed active-group switch")
            else:
                if name == "starts" and item[1] not in ("initial", "history"):
                    raise ValueError("Unknown sensing start record kind")
                if not group_id(item[-2], optional=True):
                    raise ValueError("Malformed active group")
                groups(item[-1])
    return record


def settings_record(JSON):
    """One export's settings record: its session start and end settings, its `GroupHistory`
    entries (start-of-session settings) and its event-log switches of active group. JSON-safe."""
    rec = {"starts": [], "ends": [], "switches": []}
    if not isinstance(JSON, dict):
        raise ValueError("An export must be a JSON object")
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
    return validate_settings_record(rec)


def _key(x):
    return json.dumps(x, sort_keys=True)


def union(records):
    """The union of many exports' settings records, each item once, in an order set by content.
    Two items at the same second with different settings are both kept (counted)."""
    starts, ends, switches = {}, {}, {}
    def remember(target, key, value):
        # Preserve upstream rounded-second duplicate identity, but choose the
        # earliest actual timestamp deterministically instead of the last arrival.
        target[key] = min(target.get(key, value), value, key=lambda item: item[0])
    for r in records or []:
        validate_settings_record(r)
        for t, kind, a, gr in r.get("starts") or []:
            remember(starts, _key([round(float(t)), a, gr]), (float(t), a, gr))
        for t, a, gr in r.get("ends") or []:
            remember(ends, _key([round(float(t)), a, gr]), (float(t), a, gr))
        for t, o, n in r.get("switches") or []:
            remember(switches, _key([round(float(t)), o, n]), (float(t), o, n))
    order = lambda d: [d[k] for k in sorted(d, key=lambda k: (d[k][0], k))]
    U = {"starts": order(starts), "ends": order(ends)}
    U["switches"], U["switches_dropped"] = _real_switches(U["ends"], U["starts"], order(switches))
    U["conflicts"] = sum(len(v) - len({round(x[0]) for x in v}) for v in (U["starts"], U["ends"]))
    U["_et"] = [x[0] for x in U["ends"]]
    U["_st"] = [x[0] for x in U["starts"]]
    U["_wt"] = [x[0] for x in U["switches"]]
    return U


def _real_switches(ends, starts, switches):
    """Drop switches whose new group is already active (decision 488).
    Walk session starts, ends and switches in chronological order; any other
    switch is retained and becomes the new group in force."""
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
    """Build contact, frequency and signal-lead change points with uncertainty intervals.
    An interval without a known label retains the preceding label, or the first
    later label before any label is known, and is listed in ScheduleNoRecord.
    Open interval ends use JSON null, never infinity (decision 490)."""
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


RULE_VERSION = "complete-owner-bound-schedule-v1"

def restamp_device_chronic(source_files, recordings_by_source, save=True):
    """Prepare every row before writing, rejecting incomplete source metadata.

    The caller owns the database transaction and implant-scoped lock. ``save=False``
    computes the exact change count without modifying supplied row objects.
    A complete inventory with no verified label retains old labels but marks all
    times unverified. An absent or malformed record raises before any mutation.
    """
    source_files = list(source_files)
    records = []
    for sf in source_files:
        metadata = getattr(sf, "metadata", None)
        rec = metadata.get("SensingSettingsRecord") if isinstance(metadata, dict) else None
        records.append(validate_settings_record(rec))
    U = union(records)
    sched = side_schedules(U)
    n, changes = 0, []
    for sf in source_files:
        for row in recordings_by_source.get(str(sf.uid), []):
            md = row.metadata if isinstance(row.metadata, dict) else {}
            chans = md.get("ChannelNames") or []
            hemi = str(chans[0]).split(" ")[0] if chans else ""
            s = sched.get(hemi)
            n += 1
            if s:
                new = dict(md, ContactSchedule=s["ContactSchedule"], FreqScheduleHz=s["FreqScheduleHz"],
                           ScheduleFlagged=s["ScheduleFlagged"], SignalLeadSchedule=s["SignalLeadSchedule"],
                           ScheduleNoRecord=s["ScheduleNoRecord"],
                           ScheduleSource="one schedule from every export of the implant (decisions 487, 488)")
            else:
                new = dict(md, ScheduleFlagged=[], ScheduleNoRecord=[[0.0, None]],
                           ScheduleSource="complete export inventory; no verified sensing settings for this lead")
            # Validate storage for every candidate before the first row is touched.
            json.dumps(new, allow_nan=False)
            if new != md:
                changes.append((row, new))
    if save:
        for row, new in changes:
            row.metadata = new
            row.save()
    return {"status": "complete", "exports": len(source_files), "exports_without_record": 0,
            "chronic_recordings": n, "restamped": len(changes), "conflicts": U["conflicts"],
            "switches_dropped": U["switches_dropped"],
            "flagged_stretches": {h: len(v["ScheduleFlagged"]) for h, v in sched.items()}}
