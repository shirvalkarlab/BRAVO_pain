"""Synthetic owner-scoped implant membership must be shared by clock and schedule readers.
    Explicit private configuration binds device IDs; other owners and future
    implants remain separate even when type or serial matches."""
import types

from modules import DataCurator as DC
from modules.DecodeCommon import implants
from modules.DecodeCommon.private_clinical_config import ClinicalConfigurationUnavailable

OWNER = "synthetic-owner"


class _QS:
    def __init__(self, rows):
        self.rows = list(rows)

    def _ok(self, r, k, v):
        if k == "metadata__SerialIdentityMasked":
            return (r.metadata or {}).get("SerialIdentityMasked") == v
        if k.endswith("__in"):
            return getattr(r, k[:-4]) in set(v)
        if k == "owner":
            return getattr(r, "owner_id") == getattr(v, "uid", v)
        if k == "source__in":
            return r.source_id in {getattr(x, "uid", x) for x in v}
        return getattr(r, k) == v

    def select_for_update(self):
        return self

    def filter(self, **kw):
        return _QS(r for r in self.rows if all(self._ok(r, k, v) for k, v in kw.items()))

    def values_list(self, *f, flat=False):
        return [getattr(r, f[0]) for r in self.rows] if flat else [tuple(getattr(r, x) for x in f) for r in self.rows]

    def __iter__(self):
        return iter(self.rows)


def _models():
    dev = lambda uid, serial, owner: types.SimpleNamespace(uid=uid, serial_number=serial, owner_id=owner, type="Percept RC")
    devices = [dev("main", "S7", OWNER), dev("main2", "S7", OWNER), dev("implantday", "S10", OWNER),
               dev("other", "S99", "someone-else"), dev("other2", "Z", "someone-else")]
    sf = lambda uid, device, owner, n: types.SimpleNamespace(
        uid=uid, device=device, owner_id=owner, type="MedtronicJSON", hashed="f" * 64,
        save=lambda **kwargs: None, metadata={"ClockAnchor": {"n": n}, "SensingSettingsRecord": {"starts": [], "ends": [], "switches": []}})
    files = [sf("f1", "implantday", OWNER, 1), sf("f2", "main", OWNER, 2), sf("f3", "main2", OWNER, 3),
             sf("f4", "other2", "someone-else", 4)]
    return types.SimpleNamespace(
        DBSDevice=types.SimpleNamespace(objects=_QS(devices)),
        SourceFile=types.SimpleNamespace(objects=_QS(files)),
        Recording=types.SimpleNamespace(objects=_QS([])))


def _with(fn):
    saved = (DC.models, DC.TabletClock.AnchorTable, implants.participant_section)
    def section(owner, key):
        if str(owner) != OWNER:
            raise ClinicalConfigurationUnavailable("No synthetic evidence")
        return {"groups": [{"device_type": "Percept RC", "device_uids": ["main", "main2", "implantday"]}]}
    try:
        DC.models = _models()
        implants.participant_section = section
        DC.TabletClock.AnchorTable = lambda anchors, **kwargs: sorted(a["n"] for a in anchors)
        return fn()
    finally:
        DC.models, DC.TabletClock.AnchorTable, implants.participant_section = saved


def test_the_implant_day_record_and_the_main_records_are_one_implant():
    got = _with(lambda: DC.implant_device_uids("main"))
    assert got == ["implantday", "main", "main2"], got
    # another owner's records never join by the ruling
    assert _with(lambda: DC.implant_device_uids("other2")) == ["other2"]


def test_the_clock_anchor_table_of_one_record_holds_every_record_of_its_implant():
    assert _with(lambda: DC.clock_anchor_table(device_uid="main")) == [1, 2, 3]
    assert _with(lambda: DC.clock_anchor_table(device_uid="implantday")) == [1, 2, 3]


def test_the_owner_wide_clock_tables_are_keyed_by_implant():
    got = _with(lambda: DC.clock_anchor_tables(types.SimpleNamespace(uid=OWNER)))
    assert got == {"main": [1, 2, 3], "main2": [1, 2, 3], "implantday": [1, 2, 3]}, got


def test_the_ingest_table_of_a_new_export_takes_every_record_of_its_implant():
    sf = types.SimpleNamespace(owner_id=OWNER, metadata={})
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
        CS.restamp_device_chronic = lambda sfs, by: (seen.setdefault("sfs", sorted(s.uid for s in sfs)) and {"status": "complete"})
        _with(lambda: DC.restamp_chronic_schedule(types.SimpleNamespace(uid=OWNER), types.SimpleNamespace(uid="main")))
    finally:
        CS.restamp_device_chronic = keep
    assert seen["sfs"] == ["f1", "f2", "f3"], seen
