"""Session reports stored under renamed file names are still session reports (decision 467).

On the Jetstream2 server every RCS08 export is stored under a renamed name (eight letters, an
underscore, four digits, ".json"), with no "Session" and no date token in it. The rule "the name
contains Session" matched 0 of 586 files there, so every fact read from the newest export (the
active group's rate, pulse width, contacts and closed-loop limits) was missing on that server.
The rule now also takes every Medtronic device export, and "newest" falls back to the stored
session date when the name carries no date token.

No database: rows are stubs.
"""
from types import SimpleNamespace as R

from ClosedLoopDeployment import session_report_facts as SRF


def test_a_renamed_medtronic_export_is_a_session_report():
    assert SRF.is_session_report(R(name="abcdefgh_1234.json", type="MedtronicJSON"))
    assert SRF.is_session_report(R(name="Report_Json_Session_Report_20260911T083131.json", type=None))
    assert not SRF.is_session_report(R(name="abcdefghijklmnopqrstuvwxyza", type="ChronicNeuralActivitySource"))


def test_newest_falls_back_to_the_stored_date_when_the_name_has_no_token():
    old = R(name="zzzzzzzz_9999.json", type="MedtronicJSON", date=1790726777.0)   # 2026-09-30 00:06 UTC
    new = R(name="aaaaaaaa_0001.json", type="MedtronicJSON", date=1790792470.0)   # 2026-09-30 18:21 UTC
    assert SRF.newest_by_stamp([old, new]) is new
    assert SRF.row_stamp(new).startswith("20260930T182110")


def test_a_name_with_a_date_token_keeps_the_token_order():
    a = R(name="Rcs08.db - Report_Json_Session_Report_20260911T083131.json", date=1.0)
    b = R(name="RCS08 - Report_Json_Session_Report_20250801T000000.json", date=2e9)
    assert SRF.newest_by_stamp([a, b]) is a
    assert SRF.row_stamp(a) == SRF.report_stamp(a.name)
