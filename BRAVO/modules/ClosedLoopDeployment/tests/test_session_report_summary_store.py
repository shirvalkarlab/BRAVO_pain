"""The session-report summary: the pure scanner, the store, the three-way resolution, the launcher.

Until 2026-09-12 every session-report fact the device rules read came from a file scanned once on
2026-09-05 and committed next to the module (`_facts_RCS08.json`), refreshed by nothing. These
tests pin the replacement: the scanner is one pure pass over `(stamp, dict)` documents that the
shared-drive wrapper and the ingested-record builder both call; the summary is stored in the one
cache store under the participant's session-report file set; `device_facts` resolves the stored
current summary, then the newest stale one, then the committed file, and says which in every
provenance sentence; and a stale or missing summary starts the rebuild in the background, once.

No database anywhere in this file. Rows are stubs with `uid`, `hashed` and `name`; the decrypting
loader is a dict lookup; the store is pointed at a temporary directory for its WHOLE life,
including teardown (decision 129: a test once wiped the production store by restoring the override
before clearing).
"""
from __future__ import annotations

import json
import os

import pytest

from ClosedLoopDeployment import device_facts as DF
from ClosedLoopDeployment import session_report_facts as SRF

try:
    from modules.CacheStore import ledger as _ledger
    from modules.CacheStore import provenance as _prov
    from modules.CacheStore import store as st
except ImportError:                                              # pragma: no cover
    from CacheStore import ledger as _ledger
    from CacheStore import provenance as _prov
    from CacheStore import store as st

RCS08_UID = "2e3c75c00d7f4f37b53a048d195f11da"


# ------------------------------------------------------------------------------------------------
# fixtures: hand-built session reports, stub source-file rows, a store on a temporary directory
# ------------------------------------------------------------------------------------------------
def _sensing_channel(hemi, *, rate=None, pw=100, lo=3.0, up=4.0, adaptive="NOT_CONFIGURED"):
    ch = {"HemisphereLocation": f"HemisphereLocationDef.{hemi}",
          "PulseWidthInMicroSecond": pw,
          "LowerCaptureAmplitudeInMilliAmps": lo, "UpperCaptureAmplitudeInMilliAmps": up,
          "AdaptiveTherapyStatus": f"AdaptiveTherapyStatusDef.{adaptive}",
          "UpperLimitInMilliAmps": None, "LowerLimitInMilliAmps": None}
    if rate is not None:
        ch["RateInHertz"] = rate
    return ch


def _group(gid, *, active, rate, sensing, cycling=False):
    return {"GroupId": f"GroupIdDef.{gid}", "ActiveGroup": active,
            "ProgramSettings": {"RateInHertz": rate, "SensingChannel": sensing},
            "GroupSettings": {"Cycling": {"Enabled": cycling}}}


def _survey(pair, hemi, status, freqs, mags):
    return {"SensingElectrodes": pair, "Hemisphere": hemi,
            "ArtifactStatus": f"ArtifactStatusDef.{status}",
            "LFPFrequencyinHertz": freqs, "LFPMagnitudeinMicroVoltPeak": mags}


def _older_report():
    """A 110 Hz active sensing group, adaptive NOT_CONFIGURED, capture 3.0-5.0 mA."""
    return {
        "SessionDate": "2026-09-01T10:00:00Z",
        "Groups": {"Final": [
            _group("GROUP_B", active=True, rate=110,
                   sensing=[_sensing_channel("Left", pw=100, lo=3.0, up=5.0),
                            _sensing_channel("Right", pw=100, lo=3.0, up=4.0)]),
            _group("GROUP_A", active=False, rate=130, sensing=[], cycling=True),
        ], "Initial": []},
        "BrainSenseSurveys": [{"ElectrodeSurvey": [
            _survey("ONE_AND_THREE", "Left", "ARTIFACT_NOT_PRESENT", [8.0, 10.0, 20.0], [0.2, 0.3, 0.25]),
        ]}],
    }


def _newer_report():
    """GROUP_D at 55 Hz, adaptive RUNNING on both channels, capture 2.0-4.0 mA, one pulse width
    on both sides (the scanner's interleaving rule reads pulse widths across BOTH sensing channels
    of a group, so unequal sides would flag it; that rule is not what these tests pin)."""
    return {
        "SessionDate": "2026-09-11T15:30:00Z",
        "Groups": {"Final": [
            _group("GROUP_D", active=True, rate=55,
                   sensing=[_sensing_channel("Left", pw=100, lo=2.0, up=4.0, adaptive="RUNNING"),
                            _sensing_channel("Right", pw=100, lo=2.0, up=3.5, adaptive="RUNNING")]),
        ], "Initial": []},
        "BrainSenseSurveys": [{"ElectrodeSurvey": [
            _survey("ONE_AND_THREE", "Left", "SQC_ARTIFACT_PRESENT", [8.0, 10.0, 20.0], [0.4, 0.5, 0.45]),
        ]}],
    }


OLD_NAME = "Report_Json_Session_Report_20260901T100000.json"
NEW_NAME = "Report_Json_Session_Report_20260911T153000.json"
BAD_NAME = "Report_Json_Session_Report_20260905T120000.json"


class _Row:
    """A stand-in for `Server.models.SourceFile`: the three attributes the key is built from."""
    def __init__(self, uid, hashed, name):
        self.uid, self.hashed, self.name = uid, hashed, name


def _rows(*names):
    return [_Row(f"uid-{i}", f"hash-{i}-{n[-11:-5]}", n) for i, n in enumerate(sorted(names))]


def _loader_for(mapping):
    """A decrypting loader stand-in: `name -> bytes`, raising for an unreadable file."""
    def _load(sf):
        raw = mapping[sf.name]
        if raw is None:
            raise ValueError("cannot decrypt")
        return json.dumps(raw).encode("utf-8")
    return _load


@pytest.fixture
def temp_store(tmp_path):
    """The store on a temporary directory for the WHOLE test, cleared while still pointed there."""
    prev = st.DIR_OVERRIDE, _ledger.ENABLED
    st.DIR_OVERRIDE, _ledger.ENABLED = str(tmp_path), False
    st.clear()
    try:
        yield str(tmp_path)
    finally:
        st.clear()                       # BEFORE restoring: clearing after would hit the real root
        st.DIR_OVERRIDE, _ledger.ENABLED = prev


@pytest.fixture
def launcher_on(monkeypatch):
    """Let the launcher run under the test root, count spawns instead of starting a process, and
    make sure the environment switch is not off."""
    spawned = []
    monkeypatch.setattr(DF, "SESSION_REPORT_SUMMARY_LAUNCH_UNDER_OVERRIDE_ROOT", True)
    monkeypatch.setattr(DF, "SESSION_REPORT_SUMMARY_BACKGROUND", True)
    monkeypatch.setattr(DF, "_spawn_detached", lambda argv, log: spawned.append(argv))
    monkeypatch.delenv(DF.SESSION_REPORT_SUMMARY_BACKGROUND_ENV, raising=False)
    return spawned


def _flat(o, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            _flat(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o):
            _flat(v, f"{prefix}[{i}]", out)
    else:
        out[prefix] = o
    return out


# ------------------------------------------------------------------------------------------------
# 1. the refactor: scan_folder is scan_documents, field for field
# ------------------------------------------------------------------------------------------------
def test_scan_folder_on_a_temporary_folder_equals_scan_documents_on_the_same_documents_field_for_field(tmp_path):
    (tmp_path / OLD_NAME).write_text(json.dumps(_older_report()))
    (tmp_path / NEW_NAME).write_text(json.dumps(_newer_report()))
    (tmp_path / BAD_NAME).write_text("{ this is not json")
    from_folder = SRF.scan_folder(str(tmp_path))
    from_docs = SRF.scan_documents([(SRF.report_stamp(OLD_NAME), _older_report()),
                                    (SRF.report_stamp(BAD_NAME), None),
                                    (SRF.report_stamp(NEW_NAME), _newer_report())])
    fa, fb = _flat(from_folder), _flat(from_docs)
    compared = [k for k in fa if k in fb]
    differing = [k for k in compared if fa[k] != fb[k]]
    assert len(fa) == len(fb) == len(compared), (set(fa) ^ set(fb))
    assert differing == []
    assert compared, "the comparison must have compared something"
    assert from_folder["n_files"] == 3 and from_folder["n_unreadable"] == 1


# ------------------------------------------------------------------------------------------------
# 2. the scanner's answers on hand-built reports
# ------------------------------------------------------------------------------------------------
def test_scan_documents_reads_the_d32_group_the_capture_and_the_programmed_pairs_from_the_newest_report():
    S = SRF.scan_documents([(OLD_NAME, _older_report()), (NEW_NAME, _newer_report())])
    d32 = S["d32_newest_active_sensing_group"]
    assert d32["rates_seen"] == [55.0], "the NEWEST active sensing group, not the older one"
    assert d32["pulse_widths_seen"] == [100.0]
    assert d32["cycling_in_group"] is False and d32["multiple_rates_in_group"] is False
    assert d32["interleaving_in_group"] is False and d32["patient_limits_configured"] is False
    assert d32["has_pocket_adaptor"] is None, "not in any report, so never assumed"
    assert S["adaptive_status_newest"] == "RUNNING" and S["adaptive_has_run"] is True
    assert S["adaptive_status_counts"] == {"NOT_CONFIGURED": 2, "RUNNING": 2}
    assert S["capture_newest"] == {"Left": {"lower_mA": 2.0, "upper_mA": 4.0, "pw_us": 100, "rate_hz": 55},
                                   "Right": {"lower_mA": 2.0, "upper_mA": 3.5, "pw_us": 100, "rate_hz": 55}}
    assert S["capture_pairs"] == {"Left": {"3.0/5.0": 1, "2.0/4.0": 1},
                                  "Right": {"3.0/4.0": 1, "2.0/3.5": 1}}
    assert S["capture_ceiling_violations"]["Left"] == {"violating": 0, "total": 2}
    # the D31 counts, recorded for the next step's comparison against the hardcoded table
    assert S["brainsense_programmed_pairs"] == {"Left": {"110/100": 1, "55/100": 1},
                                                "Right": {"110/100": 1, "55/100": 1}}
    assert SRF.programmed_pairs_table(S) == {"Left": {(110.0, 100.0): 1, (55.0, 100.0): 1},
                                             "Right": {(110.0, 100.0): 1, (55.0, 100.0): 1}}
    assert S["artifact_status"] == {"ONE_AND_THREE_Left": {"ARTIFACT_NOT_PRESENT": 1,
                                                           "SQC_ARTIFACT_PRESENT": 1}}
    assert S["cycling_by_group_kind"] == {"sensing/active/False": 2, "no_sensing/inactive/True": 1}


def test_scan_documents_orders_newest_by_stamp_and_not_by_iteration_order():
    forward = SRF.scan_documents([(OLD_NAME, _older_report()), (NEW_NAME, _newer_report())])
    backward = SRF.scan_documents([(NEW_NAME, _newer_report()), (OLD_NAME, _older_report())])
    assert forward["d32_newest_active_sensing_group"]["rates_seen"] == [55.0]
    assert backward["d32_newest_active_sensing_group"]["rates_seen"] == [55.0]
    assert forward["adaptive_status_newest"] == backward["adaptive_status_newest"] == "RUNNING"


def test_newest_is_ordered_by_the_date_token_in_the_name_and_not_by_the_uploaders_prefix():
    """Found on the first live rebuild: 532 of RCS08's 572 ingested names are prefixed
    `Rcs08.db - Report_Json_...`, 30 carry no prefix, and a few say `RCS08 - `, `JI - ` or
    `Report_JI Pacu_`. Compared as bare strings the prefix-less August 2025 names sorted above every
    2026 name, so "newest" was an August 2025 file."""
    prefixed_new = "Rcs08.db - Report_Json_Session_Report_20260911T083131.json"
    bare_old = "Report_Json_Session_Report_20250821T114520.json"
    pacu = "Report_JI Pacu_Json_Session_Report_20250716T222813.json"
    assert bare_old > prefixed_new, "the bare string order is the wrong one"
    assert SRF.report_stamp(prefixed_new) > SRF.report_stamp(bare_old) > SRF.report_stamp(pacu)
    assert SRF.report_stamp("no token here.json") == "no token here.json"
    rows = [_Row("a", "h1", bare_old), _Row("b", "h2", prefixed_new), _Row("c", "h3", pacu)]
    assert SRF.newest_by_stamp(rows).name == prefixed_new
    # the scanner sees the same order: the prefixed 2026 report is the newest active group
    S = SRF.scan_documents([(SRF.report_stamp(bare_old), _older_report()),
                            (SRF.report_stamp(prefixed_new), _newer_report())])
    assert S["d32_newest_active_sensing_group"]["rates_seen"] == [55.0]
    loader = _loader_for({bare_old: _older_report(), prefixed_new: _newer_report(), pacu: _older_report()})
    S2 = SRF.summary_from_ingested("p-pre", rows=rows, loader=loader)
    assert S2["newest_stamp"] == prefixed_new
    assert S2["newest_stamp_key"] == SRF.report_stamp(prefixed_new)
    assert S2["adaptive_status_newest"] == "RUNNING"


def test_summary_from_ingested_uses_the_row_name_as_the_stamp_and_adds_the_bookkeeping_fields():
    rows = _rows(OLD_NAME, NEW_NAME, BAD_NAME)
    loader = _loader_for({OLD_NAME: _older_report(), NEW_NAME: _newer_report(), BAD_NAME: None})
    S = SRF.summary_from_ingested("p-x", rows=rows, loader=loader)
    assert S["n_files"] == 3 and S["n_unreadable"] == 1
    assert S["newest_stamp"] == NEW_NAME and S["newest_stamp_key"] == SRF.report_stamp(NEW_NAME)
    assert S["source"] == "ingested" and S["participant_uid"] == "p-x"
    assert S["source_signature"] == list(SRF.file_set_signature(rows))
    assert str(S["built_utc"]).startswith("20")
    assert S["d32_newest_active_sensing_group"]["rates_seen"] == [55.0]


# ------------------------------------------------------------------------------------------------
# 3. the key: the file set, in a fixed order, never the names alone
# ------------------------------------------------------------------------------------------------
def test_file_set_signature_ignores_row_order_and_changes_with_a_files_hash_or_a_new_file():
    a = _rows(OLD_NAME, NEW_NAME)
    b = list(reversed(a))
    assert SRF.file_set_signature(a) == SRF.file_set_signature(b)
    reingested = [_Row(r.uid, r.hashed + "x" if r.name == NEW_NAME else r.hashed, r.name) for r in a]
    assert SRF.file_set_signature(reingested) != SRF.file_set_signature(a)
    assert SRF.file_set_signature(a + [_Row("uid-9", "h9", BAD_NAME)]) != SRF.file_set_signature(a)
    assert SRF.file_set_signature([]) is None
    assert SRF.file_set_signature(a)[0] == SRF.SUMMARY_KIND
    assert SRF.file_set_signature(a)[1] == SRF.SUMMARY_RULE_VERSION


def test_the_summary_kind_is_raw_and_is_released_to_every_module(temp_store):
    rows = _rows(OLD_NAME, NEW_NAME)
    loader = _loader_for({OLD_NAME: _older_report(), NEW_NAME: _newer_report()})
    sig = SRF.file_set_signature(rows)
    assert SRF.SUMMARY_KIND in _prov.RAW_KINDS
    assert st.store(SRF.SUMMARY_KIND, "p-raw", sig,
                    SRF.summary_from_ingested("p-raw", rows=rows, loader=loader),
                    writer="closed_loop", provenance=[])
    for consumer in ("closed_loop", "stim_optimizer", "biomarkers"):
        got = st.load(SRF.SUMMARY_KIND, "p-raw", sig, consumer=consumer)
        assert got["adaptive_status_newest"] == "RUNNING"


# ------------------------------------------------------------------------------------------------
# 4. rebuild_and_store: the key decides
# ------------------------------------------------------------------------------------------------
def test_rebuild_and_store_stores_on_the_first_run_and_reports_already_current_on_the_second(temp_store):
    rows = _rows(OLD_NAME, NEW_NAME)
    calls = []
    base = _loader_for({OLD_NAME: _older_report(), NEW_NAME: _newer_report()})

    def loader(sf):
        calls.append(sf.name)
        return base(sf)

    first = SRF.rebuild_and_store("p-cmd", rows=rows, loader=loader)
    assert first["stored"] is True and first["already_current"] is False
    assert first["n_files"] == 2 and first["newest_stamp"] == NEW_NAME
    assert len(calls) == 2, "every file decrypted exactly once"
    second = SRF.rebuild_and_store("p-cmd", rows=rows, loader=loader)
    assert second["already_current"] is True and second["stored"] is False
    assert second["n_files"] == 2 and second["newest_stamp"] == NEW_NAME
    assert len(calls) == 2, "the second run opened no file"
    assert second["store_key"] == first["store_key"]
    forced = SRF.rebuild_and_store("p-cmd", rows=rows, loader=loader, force=True)
    assert forced["stored"] is True and len(calls) == 4
    # a NEW file set is a new key, so the next run rebuilds rather than reporting current
    more = rows + [_Row("uid-9", "h9", BAD_NAME)]
    loader2 = _loader_for({OLD_NAME: _older_report(), NEW_NAME: _newer_report(), BAD_NAME: None})
    third = SRF.rebuild_and_store("p-cmd", rows=more, loader=loader2)
    assert third["stored"] is True and third["n_files"] == 3 and third["n_unreadable"] == 1
    assert third["store_key"] != first["store_key"]


def test_rebuild_and_store_stores_nothing_for_a_participant_with_no_session_reports(temp_store):
    out = SRF.rebuild_and_store("p-none", rows=[], loader=_loader_for({}))
    assert out["stored"] is False and out["already_current"] is False
    assert "no ingested session reports" in out["reason"]
    assert st.newest_stamp(SRF.SUMMARY_KIND, "p-none") is None


# ------------------------------------------------------------------------------------------------
# 5. the resolution order in device_facts, and the sentence each branch writes
# ------------------------------------------------------------------------------------------------
def _stub_file_set(monkeypatch, rows_by_uid):
    monkeypatch.setattr(SRF, "session_report_files",
                        lambda participant: list(rows_by_uid.get(str(getattr(participant, "uid", participant)), [])))


def test_resolution_a_serves_the_stored_summary_for_the_current_file_set_and_never_starts_the_launcher(
        temp_store, launcher_on, monkeypatch):
    rows = _rows(OLD_NAME, NEW_NAME)
    _stub_file_set(monkeypatch, {"p-a": rows})
    loader = _loader_for({OLD_NAME: _older_report(), NEW_NAME: _newer_report()})
    assert SRF.rebuild_and_store("p-a", rows=rows, loader=loader)["stored"]
    S, res = DF._load_summary("p-a")
    assert res["source"] == "current" and res["launch"] is None
    assert res["sentence"] == (f"rebuilt from 2 ingested session reports, newest {NEW_NAME}, "
                               f"built {S['built_utc'][:10]}")
    assert S["adaptive_status_newest"] == "RUNNING"
    facts, prov = DF.session_report_facts_for("p-a", channel="ONE_THREE_LEFT", hemisphere="Left")
    assert facts["session_report_summary_source"] == "current"
    assert prov["session_report_summary_source"] == res["sentence"]
    assert facts["capture_amp_low_mA"] == 2.0 and facts["capture_amp_high_mA"] == 4.0
    assert prov["capture_amp_high_mA"].startswith("measured: session reports, 2 files (rebuilt from 2")
    DF._load_summary("p-a")
    assert launcher_on == [], "a current summary starts nothing, however often it is asked"


def test_resolution_b_serves_the_newest_stale_summary_says_how_many_reports_it_misses_and_starts_the_rebuild_once(
        temp_store, launcher_on, monkeypatch):
    old_rows = _rows(OLD_NAME)
    loader = _loader_for({OLD_NAME: _older_report()})
    assert SRF.rebuild_and_store("p-b", rows=old_rows, loader=loader)["stored"]
    # two reports ingested since: the stored summary's key no longer matches
    now_rows = _rows(OLD_NAME, BAD_NAME, NEW_NAME)
    _stub_file_set(monkeypatch, {"p-b": now_rows})
    S, res = DF._load_summary("p-b")
    assert res["source"] == "stale"
    assert res["sentence"] == (f"STALE: built from 1 files on {S['built_utc'][:10]}; 2 newer "
                               f"session reports are not included")
    assert S["adaptive_status_newest"] == "NOT_CONFIGURED", "the stale answer, used and labelled"
    assert res["launch"]["launched"] is True
    assert launcher_on[-1][2:] == ["rebuild_session_report_summary", "--participant", "p-b"]
    assert len(launcher_on) == 1
    # the marker holds the second request back, on this worker or any other
    S2, res2 = DF._load_summary("p-b")
    assert res2["source"] == "stale" and res2["launch"]["launched"] is False
    assert "cooldown" in res2["launch"]["reason"]
    assert len(launcher_on) == 1, "exactly one launch within the cooldown"
    facts, prov = DF.session_report_facts_for("p-b", channel="ONE_THREE_LEFT", hemisphere="Left")
    assert facts["session_report_summary_source"] == "stale"
    assert prov["session_report_summary_source"].startswith("STALE: built from 1 files")
    assert prov["session_report_summary_source"].endswith(
        f"; background rebuild not started: {res2['launch']['reason']}")
    assert prov["capture_amp_low_mA"].startswith("measured: session reports, 1 files (STALE:")


def test_resolution_c_falls_back_to_the_committed_scan_names_the_ingested_record_and_starts_the_rebuild(
        temp_store, launcher_on, monkeypatch):
    rows = _rows(OLD_NAME, NEW_NAME, BAD_NAME)
    _stub_file_set(monkeypatch, {RCS08_UID: rows})
    S, res = DF._load_summary(RCS08_UID)
    assert res["source"] == "committed"
    assert res["sentence"] == (f"committed scan of 2026-09-05 over 1,154 shared-drive files; the "
                               f"ingested record has 3 reports, newest {NEW_NAME}")
    assert S["n_files"] == 1154 and S["adaptive_status_newest"] == "NOT_CONFIGURED"
    assert res["launch"]["launched"] is True and len(launcher_on) == 1
    facts, prov = DF.session_report_facts_for(RCS08_UID, channel="ONE_THREE_LEFT", hemisphere="Left")
    assert facts["session_report_summary_source"] == "committed"
    assert ("; background rebuild not started: a rebuild for this key started"
            in prov["session_report_summary_source"]), "the second call sits inside the cooldown"
    assert prov["artifact_flags"].startswith("measured: session reports, 1154 files (committed scan of 2026-09-05")


def test_resolution_c_without_a_queryable_record_says_so_and_starts_nothing(temp_store, launcher_on, monkeypatch):
    def _boom(participant):
        raise RuntimeError("no database here")
    monkeypatch.setattr(SRF, "session_report_files", _boom)
    S, res = DF._load_summary(RCS08_UID)
    assert res["source"] == "committed" and res["launch"] is None
    assert res["sentence"] == ("committed scan of 2026-09-05 over 1,154 shared-drive files; the "
                               "ingested record could not be queried (RuntimeError: no database here)")
    assert launcher_on == []


def test_a_participant_with_no_summary_anywhere_gives_no_facts_and_no_provenance(temp_store, launcher_on, monkeypatch):
    _stub_file_set(monkeypatch, {"p-nobody": []})
    S, res = DF._load_summary("p-nobody")
    assert S == {} and res["source"] == "none" and res["launch"] is None
    assert DF.session_report_facts_for("p-nobody", channel="ONE_THREE_LEFT", hemisphere="Left") == ({}, {})
    assert launcher_on == []


# ------------------------------------------------------------------------------------------------
# 6. the launcher's own refusals
# ------------------------------------------------------------------------------------------------
def test_the_launcher_refuses_under_a_test_override_root_by_default(temp_store, monkeypatch):
    spawned = []
    monkeypatch.setattr(DF, "_spawn_detached", lambda argv, log: spawned.append(argv))
    monkeypatch.delenv(DF.SESSION_REPORT_SUMMARY_BACKGROUND_ENV, raising=False)
    assert DF.SESSION_REPORT_SUMMARY_LAUNCH_UNDER_OVERRIDE_ROOT is False, "the default is the safe one"
    sig = SRF.file_set_signature(_rows(OLD_NAME))
    out = DF.launch_summary_rebuild_in_background("p-refused", sig)
    assert out["launched"] is False and "caller's own root" in out["reason"]
    assert spawned == []
    assert not os.path.exists(DF._summary_launch_marker(sig)), "refused before the marker is written"


def test_the_launcher_is_switched_off_by_the_environment_variable(temp_store, launcher_on, monkeypatch):
    monkeypatch.setenv(DF.SESSION_REPORT_SUMMARY_BACKGROUND_ENV, "0")
    out = DF.launch_summary_rebuild_in_background("p-off", SRF.file_set_signature(_rows(OLD_NAME)))
    assert out["launched"] is False and "switched off" in out["reason"]
    assert launcher_on == []


def test_the_launcher_writes_the_marker_before_spawning_and_a_new_file_set_gets_its_own_cooldown(
        temp_store, launcher_on):
    sig1 = SRF.file_set_signature(_rows(OLD_NAME))
    sig2 = SRF.file_set_signature(_rows(OLD_NAME, NEW_NAME))
    assert DF.launch_summary_rebuild_in_background("p-m", sig1)["launched"] is True
    assert os.path.exists(DF._summary_launch_marker(sig1))
    assert DF.launch_summary_rebuild_in_background("p-m", sig1)["launched"] is False
    assert DF.launch_summary_rebuild_in_background("p-m", sig2)["launched"] is True
    assert len(launcher_on) == 2


# ---------------------------------------------------------------------------------------------
# D32's two flags, corrected 2026-09-12 after the first live rebuild failed D32 on the very group
# running adaptive DBS (RCS08 GROUP_D: 100 us Left / 150 us Right, adaptive limits 2.0-3.0 mA).
# ---------------------------------------------------------------------------------------------
def _chan(hemi, rate, pw, status, upper=None, lower=None):
    return {"HemisphereLocation": f"HemisphereLocationDef.{hemi}", "RateInHertz": rate,
            "PulseWidthInMicroSecond": pw, "AdaptiveTherapyStatus": f"ADBSStatusDef.{status}",
            "UpperLimitInMilliAmps": upper, "LowerLimitInMilliAmps": lower,
            "UpperCaptureAmplitudeInMilliAmps": upper, "LowerCaptureAmplitudeInMilliAmps": lower}


def _d32_of(sensing):
    doc = {"Groups": {"Final": [_group("GROUP_D", active=True, rate=55, sensing=sensing)]}}
    return SRF.scan_documents([("Report_Json_Session_Report_20260911T083131.json", doc)])[
        "d32_newest_active_sensing_group"]


def test_one_pulse_width_per_hemisphere_is_not_interleaving_even_when_the_two_sides_differ():
    d32 = _d32_of([_chan("Left", 55, 100, "RUNNING", 3.0, 2.0),
                   _chan("Right", 55, 150, "RUNNING", 2.5, 1.5)])
    assert d32["interleaving_in_group"] is False
    assert d32["pulse_widths_seen"] == [100.0, 150.0]


def test_two_pulse_widths_on_one_hemisphere_is_interleaving():
    d32 = _d32_of([_chan("Left", 55, 100, "RUNNING", 3.0, 2.0),
                   _chan("Left", 55, 60, "RUNNING", 3.0, 2.0)])
    assert d32["interleaving_in_group"] is True


def test_limits_on_a_channel_running_adaptive_therapy_are_adaptive_limits_not_patient_limits():
    d32 = _d32_of([_chan("Left", 55, 100, "RUNNING", 3.0, 2.0),
                   _chan("Right", 55, 150, "RUNNING", 2.5, 1.5)])
    assert d32["patient_limits_configured"] is False


def test_limits_on_a_sensing_only_channel_are_patient_limits():
    d32 = _d32_of([_chan("Left", 55, 100, "NOT_CONFIGURED", 4.0, 0.0),
                   _chan("Right", 55, 150, "NOT_CONFIGURED", 3.0, 0.0)])
    assert d32["patient_limits_configured"] is True


def test_a_channel_with_no_limit_values_means_patient_limits_are_not_configured():
    d32 = _d32_of([_chan("Left", 55, 100, "NOT_CONFIGURED")])
    assert d32["patient_limits_configured"] is False
