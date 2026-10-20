'Session reports stored under renamed file names are still session reports (decision 467).'
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
    a = R(name="SYNTHETIC01.db - Report_Json_Session_Report_20260911T083131.json", date=1.0)
    b = R(name="SYNTHETIC01 - Report_Json_Session_Report_20250801T000000.json", date=2e9)
    assert SRF.newest_by_stamp([a, b]) is a
    assert SRF.row_stamp(a) == SRF.report_stamp(a.name)
