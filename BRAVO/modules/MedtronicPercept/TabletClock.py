"""Every time in a Percept export, on the tablet's clock. THE ONE HOME for it.

WHY (the PI, 2026-09-26): "INS device time should not be used anywhere for any reason." The
implanted device keeps its own clock and it drifts; on RCS08 it ran ahead of the tablet's
internet-synced clock by about +110 s in August 2025, +2,250 s in February 2026 and +7,700 s in
September 2026 (547 of 583 exports; the other 36 read within 40 s).

WHAT EACH FIELD IS (measured on RCS08's 583 exports, 2026-09-26; DEVICE_percept_rc.md, parsing
trap 2). Every dated field of an export -- `FirstPacketDateTime` of every stream, montage, survey
and test, the chronic log's, patient events' and event log's `DateTime`, `GroupHistory[].SessionDate`,
`RechargeCount[].SessionStartDate`, `EventSummary`'s two dates, `DeviceDateTime`, `Annotations[].Date`
-- carries two companions, `<field>BlockId` and `<field>OffsetInSeconds`, and within one export
equals (the export's DeviceDateTime - its DeviceDateTimeOffsetInSeconds) + the entry's own
OffsetInSeconds (+ a fixed difference for its family: -600 s for the chronic log, 0 for the rest).
So the string is the DEVICE's clock; the OffsetInSeconds is the device's own seconds counter, which
is sound; and the export's top-level `SessionDate` (the one time with no companions) is the TABLET's
clock: SessionDate - DeviceDateTimeOffsetInSeconds holds within 294 s over the whole record.

THE CONVERSION (the PI's rulings of 2026-09-26). For an entry with offset `o` in clock block `b`:

    tablet time = o + FAMILY_DIFFERENCE_S[family] + anchor
    anchor      = SessionEndDate - DeviceInformation.Final.DeviceDateTimeOffsetInSeconds of the
                  export the entry was DERIVED FROM: the FIRST export that carries it (the PI,
                  2026-09-26: "the session where the data was derived from, obviously"). A stream,
                  montage or survey: its own export. A chronic reading, event, therapy change or
                  setting snapshot re-sent in every later export: the first one, so every copy
                  converts to one time.

WHICH EXPORT CARRIED AN ENTRY FIRST cannot be read off the device readings alone: on RCS08 the
earliest export whose Final reading is at or after an entry does not carry it for 5,643 of 25,054
left chronic readings, 2,853 of 5,354 event-log entries and others (an export not fully read
carries no logs). So each stored export records the entries it carried FIRST -- by family, clock
block and own OffsetInSeconds -- in `SourceFile.metadata["ClockAnchor"]["first_carried"]`, written
at ingest (`convert_export` returns them), and every later export looks its entries up there. An
entry is identified by family, block and own offset; two different entries at one offset (two
event-log lines in one second) share the anchor and keep their own content.

WHICH TABLET TIME PAIRS WITH WHICH DEVICE READING (measured on RCS08's 575 exports of block 43):
SessionEndDate (the save) with the Final reading. That anchor moves by a median 1 s between
consecutive exports (90th percentile 2 s, at most 7 s); SessionDate with the Initial reading moves by
a median 13 s (at most 266 s), and on the device counter Final - Initial exceeds SessionEndDate -
SessionDate by a median 34 s: the Initial reading is taken before the tablet stamps SessionDate. Both
put all 2,971 stream, montage and test starts inside [SessionDate, SessionEndDate]. An export with no
SessionEndDate (27 on RCS08, all block 43) falls back to SessionDate - Initial, which reads a median
34 s (5 to 105 s) later; its anchor says which rule made it (`rule`).

(b) An entry in a clock block that has no export of its own cannot be converted; it is LEFT OUT of
the converted export, counted per family in `JSON["_TabletClock"]`, and logged.
(c) Exports whose device clock read close to the tablet's are converted by the same rule.

The raw exports on disk are never rewritten: every reader decodes them through `convert_export`
(`DataCurator.loadPerceptJSON`). The conversion reads only the offsets, never the device strings, so
it is idempotent. The strings are written back in the export's own format (".000Z" where the field
had milliseconds); on RCS08 every tablet time is a whole second, and so is every converted one.
"""
import hashlib
import logging
from datetime import datetime, timezone

_log = logging.getLogger(__name__)

#: THE FIXED DIFFERENCE of a field family from (its export's device anchor + its own offset), in
#: seconds, measured on RCS08 (2026-09-26, `_agent_bridge/_clock_kfam.py`): the chronic log's
#: entries sit 600 s before (46,471 of 50,926 and 28,811 of 32,183 entries in their export's own
#: block; the rest are entries logged under an earlier device reading, which the offset rule does
#: not need). Every other family: 0.
FAMILY_DIFFERENCE_S = {"LFPTrendLogs": -600.0}

#: Keys whose values are never converted: the export's own tablet time and the free-text fields.
_TABLET_FIELDS = ("SessionDate",)


def _parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def _format_like(original, t):
    """`t` (epoch seconds) in the format of `original`: milliseconds where it had them, 'Z'."""
    d = datetime.fromtimestamp(t, tz=timezone.utc)
    body = original[:-1] if original.endswith("Z") else original
    if "." in body.split("T")[-1]:
        n = len(body.split(".")[-1])
        frac = ("%.*f" % (n, t % 1))[2:] if n else ""
        return d.strftime("%Y-%m-%dT%H:%M:%S") + "." + frac + "Z"
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def export_anchor(JSON):
    """This export's clock anchor, or None: {"block", "final_offset_s", "anchor_s", "rule",
    "session_date_s"}. anchor_s = SessionEndDate - Final.DeviceDateTimeOffsetInSeconds; where the
    export has no SessionEndDate, SessionDate - Initial.DeviceDateTimeOffsetInSeconds (rule says which)."""
    try:
        di = JSON["DeviceInformation"]
        fin, ini = di["Final"], di["Initial"]
        f_off = float(fin["DeviceDateTimeOffsetInSeconds"])
        blk = fin["DeviceDateTimeBlockId"]
        sd = _parse(JSON["SessionDate"])
    except Exception:
        return None
    try:
        se = _parse(JSON["SessionEndDate"]) if JSON.get("SessionEndDate") else None
    except Exception:
        se = None
    if se is not None:
        return {"block": blk, "final_offset_s": f_off, "anchor_s": se - f_off,
                "rule": "SessionEndDate-Final", "session_date_s": sd}
    try:
        i_off = float(ini["DeviceDateTimeOffsetInSeconds"])
        if ini.get("DeviceDateTimeBlockId") != blk:
            return None
    except Exception:
        return None
    return {"block": blk, "final_offset_s": f_off, "anchor_s": sd - i_off,
            "rule": "SessionDate-Initial (no SessionEndDate)", "session_date_s": sd}


class AnchorTable:
    """One device's exports: their anchors, and which export carried each entry first.

    Built from anchor dicts ({"block", "final_offset_s", "anchor_s", optional "first_carried":
    {family: {block: [offsets]}}}); where two exports both list an entry, the one read earlier on
    the device counter wins."""

    def __init__(self, anchors):
        by, seen, first = {}, set(), {}
        for a in sorted([a for a in (anchors or []) if a], key=lambda a: float(a["final_offset_s"])):
            k = (a["block"], float(a["final_offset_s"]), float(a["anchor_s"]))
            if k not in seen:
                seen.add(k)
                by.setdefault(a["block"], []).append((float(a["final_offset_s"]), float(a["anchor_s"])))
            for fam, blocks in (a.get("first_carried") or {}).items():
                for blk, offs in blocks.items():
                    for o in offs:
                        first.setdefault((fam, str(blk), float(o)), float(a["anchor_s"]))
        self._by = {b: sorted(v) for b, v in by.items()}
        self._first = first

    def __len__(self):
        return sum(len(v) for v in self._by.values())

    def first_carrier_anchor(self, family, block, offset):
        return self._first.get((family, str(block), float(offset)))

    def block_anchor(self, block):
        """The anchor of the latest export of `block` (for an entry of an older clock block that
        no export of that block carried), or None when the block has no export."""
        rows = self._by.get(block)
        return rows[-1][1] if rows else None

    def digest_upto(self, anchor):
        """A digest of what an export's entries can be converted with: every export read at or
        before it on the device counter (their anchors and how many entries each carried first),
        and every export of another clock block. `anchor` None: all."""
        h = hashlib.sha1()
        lim = float(anchor["final_offset_s"]) if anchor else float("inf")
        own_blk = anchor["block"] if anchor else None
        for b in sorted(self._by, key=str):
            for off, a in self._by[b]:
                if b != own_blk or off <= lim:
                    h.update(("%s|%r|%r;" % (b, off, a)).encode())
        n = sum(1 for k, v in self._first.items())
        h.update(("first:%d" % n).encode() if anchor is None else b"")
        return h.hexdigest()[:16]

    def digest(self):
        return self.digest_upto(None)


def _family(path, field):
    for fam in FAMILY_DIFFERENCE_S:
        if fam in path:
            return fam
    return field


def convert_export(JSON, anchors, convert=True):
    """Rewrite every device-clock time in `JSON` IN PLACE to the tablet's clock; returns counts.

    `convert=False` only leaves out the entries that cannot be converted and keeps every time as
    it is: the same export as the conversion sees it, on the device clock (for comparisons).

    `anchors`: an AnchorTable or a list of anchor dicts of the device's other exports. Each entry
    takes the anchor of the export that carried it first; one that no stored export carried is this
    export's, and is returned in `counts["first_carried"]` for the ingest to record. An entry of an
    older clock block that no export of that block carried takes that block's latest export (counted
    as "other_block"). A dict entry of a list whose block has no export at all is removed from the
    list; a time outside a list that cannot be converted is left as it is; both counted.
    """
    own = export_anchor(JSON)
    table = anchors if isinstance(anchors, AnchorTable) else AnchorTable(list(anchors or []))
    counts = {"converted": {}, "left_out": {}, "left_unconverted": {}, "other_block": {},
              "first_carried": {}}

    def bump(kind, fam, n=1):
        counts[kind][fam] = counts[kind].get(fam, 0) + n

    def convert_dict(d, path):
        """Convert d's own time fields; False when one of them has no anchor."""
        ok = True
        for f in list(d.keys()):
            v = d[f]
            if f in _TABLET_FIELDS and path == "":
                continue
            if not isinstance(v, str) or (f + "OffsetInSeconds") not in d:
                continue
            if v == "" or "█" in v:
                continue
            fam = _family(path, f)
            key = path + "." + f
            blk, off = d.get(f + "BlockId"), float(d[f + "OffsetInSeconds"])
            a = table.first_carrier_anchor(key, blk, off)
            if a is None and own is not None and blk == own["block"]:
                a = own["anchor_s"]                     # this export carried it first
                counts["first_carried"].setdefault(key, {}).setdefault(str(blk), []).append(off)
            elif a is None:
                a = table.block_anchor(blk)
                if a is not None:
                    bump("other_block", key)
            if a is None:
                ok = False
                continue
            if convert:
                t = float(d[f + "OffsetInSeconds"]) + FAMILY_DIFFERENCE_S.get(fam, 0.0) + a
                d[f] = _format_like(v, t)
                bump("converted", path + "." + f)
        return ok

    def walk(o, path):
        if isinstance(o, dict):
            if not convert_dict(o, path):
                bump("left_unconverted", path)
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    walk(v, path + "." + ("<date>" if k[:2] == "20" else k))
        elif isinstance(o, list):
            keep = []
            for v in o:
                if isinstance(v, dict):
                    if not convert_dict(v, path + "[]"):
                        bump("left_out", path + "[]")
                        continue
                    for k, w in v.items():
                        if isinstance(w, (dict, list)):
                            walk(w, path + "[]." + ("<date>" if k[:2] == "20" else k))
                    keep.append(v)
                else:
                    walk(v, path + "[]")
                    keep.append(v)
            o[:] = keep

    walk(JSON, "")
    if counts["left_out"] or counts["left_unconverted"]:
        _log.info("TabletClock: entries in a clock block with no export of their own: left out %s, "
                  "left unconverted %s", counts["left_out"], counts["left_unconverted"])
    for fam in counts["first_carried"].values():
        for blk in fam:
            fam[blk] = sorted(set(fam[blk]))
    counts["anchor"] = own
    counts["table_digest"] = table.digest()
    JSON["_TabletClock"] = counts
    return counts
