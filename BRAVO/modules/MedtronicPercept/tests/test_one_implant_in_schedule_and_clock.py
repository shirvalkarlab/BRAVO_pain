"""One implant filed as several device records joins ONE chronic-log schedule and ONE tablet-clock
anchor table (decision 489; `DecodeCommon/implants.py`, `DataCurator.implant_device_uids`).

RCS08's two implant-day exports sit on a device record whose serial number differs from the main
record's (decision 479: the Dropbox copies mask it, theirs was restored). The PI ruled the records
one implant (2026-10-19). Pinned on made-up rows: the schedule's restamp, the clock anchor tables
(one record's, every record's of an owner, and the ingest's own) all take the linked record's
exports; records of another owner, or with another serial and no ruling, stay apart.

Plain asserts, no arguments: runs in the container suite."""
import types

from modules import DataCurator as DC

RCS08 = "2e3c75c00d7f4f37b53a048d195f11da"


class _QS:
    def __init__(self, rows):
        self.rows = list(rows)

    def _ok(self, r, k, v):
        if k.endswith("__in"):
            return getattr(r, k[:-4]) in set(v)
        if k == "owner":
            return getattr(r, "owner_id") == getattr(v, "uid", v)
        if k == "source__in":
            return r.source_id in {getattr(x, "uid", x) for x in v}
        return getattr(r, k) == v

    def filter(self, **kw):
        return _QS(r for r in self.rows if all(self._ok(r, k, v) for k, v in kw.items()))

    def values_list(self, *f, flat=False):
        return [getattr(r, f[0]) for r in self.rows] if flat else [tuple(getattr(r, x) for x in f) for r in self.rows]

    def __iter__(self):
        return iter(self.rows)


def _models():
    dev = lambda uid, serial, owner: types.SimpleNamespace(uid=uid, serial_number=serial, owner_id=owner, type="Percept RC")
    devices = [dev("main", "S7", RCS08), dev("main2", "S7", RCS08), dev("implantday", "S10", RCS08),
               dev("other", "S99", "someone-else"), dev("other2", "Z", "someone-else")]
    sf = lambda uid, device, owner, n: types.SimpleNamespace(
        uid=uid, device=device, owner_id=owner, type="MedtronicJSON",
        metadata={"ClockAnchor": {"n": n}, "SensingSettingsRecord": {"starts": [], "ends": [], "switches": []}})
    files = [sf("f1", "implantday", RCS08, 1), sf("f2", "main", RCS08, 2), sf("f3", "main2", RCS08, 3),
             sf("f4", "other2", "someone-else", 4)]
    return types.SimpleNamespace(
        DBSDevice=types.SimpleNamespace(objects=_QS(devices)),
        SourceFile=types.SimpleNamespace(objects=_QS(files)),
        Recording=types.SimpleNamespace(objects=_QS([])))


def _with(fn):
    saved = (DC.models, DC.TabletClock.AnchorTable)
    try:
        DC.models = _models()
        DC.TabletClock.AnchorTable = lambda anchors: sorted(a["n"] for a in anchors)
        return fn()
    finally:
        DC.models, DC.TabletClock.AnchorTable = saved


def test_the_implant_day_record_and_the_main_records_are_one_implant():
    got = _with(lambda: DC.implant_device_uids("main"))
    assert got == ["implantday", "main", "main2"], got
    # another owner's records never join by the ruling
    assert _with(lambda: DC.implant_device_uids("other2")) == ["other2"]


def test_the_clock_anchor_table_of_one_record_holds_every_record_of_its_implant():
    assert _with(lambda: DC.clock_anchor_table(device_uid="main")) == [1, 2, 3]
    assert _with(lambda: DC.clock_anchor_table(device_uid="implantday")) == [1, 2, 3]


def test_the_owner_wide_clock_tables_are_keyed_by_implant():
    got = _with(lambda: DC.clock_anchor_tables(types.SimpleNamespace(uid=RCS08)))
    assert got == {"main": [1, 2, 3], "main2": [1, 2, 3], "implantday": [1, 2, 3]}, got


def test_the_ingest_table_of_a_new_export_takes_every_record_of_its_implant():
    sf = types.SimpleNamespace(owner_id=RCS08, metadata={})
    J = {"DeviceInformation": {"Final": {"NeurostimulatorSerialNumber": "S10"}}}
    saved = DC.TabletClock.export_anchor
    try:
        DC.TabletClock.export_anchor = lambda JSON: {"n": 9}
        own, table = _with(lambda: DC._ingest_clock_table(J, sf))
    finally:
        DC.TabletClock.export_anchor = saved
    assert table == [1, 2, 3, 9], table


def test_the_chronic_schedule_restamp_takes_the_linked_records_exports():
    seen = {}
    saved = DC.__dict__.get("_restamp_probe")
    from modules.MedtronicPercept import chronic_schedule as CS
    keep = CS.restamp_device_chronic
    try:
        CS.restamp_device_chronic = lambda sfs, by: seen.setdefault("sfs", sorted(s.uid for s in sfs))
        _with(lambda: DC.restamp_chronic_schedule(types.SimpleNamespace(uid=RCS08), types.SimpleNamespace(uid="main")))
    finally:
        CS.restamp_device_chronic = keep
    assert seen["sfs"] == ["f1", "f2", "f3"], seen
