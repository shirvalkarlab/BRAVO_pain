"""D39 needs to know whether the implant has a lead on each side (the PI, 2026-10-08: the wiring
choice "Left sensing drives both" uses contralateral sensing). The fact comes from the newest
device's stored leads."""
from unittest import mock

from ClosedLoopDeployment import device_facts as df


def _facts(sides):
    with mock.patch("ClosedLoopDeployment.stim_program.lead_targets", return_value=sides), \
         mock.patch.object(df, "session_report_facts_for", return_value=({}, {})):
        return df.facts_for_participant("nobody", [], sensing_hemisphere="Left", actuated_hemisphere="Right")


def test_two_leads_is_a_dual_lead_implant():
    out = _facts({"Left": "Left GPe", "Right": "Right MD Thal"})
    assert out["dual_lead_implant"] is True
    assert "stored leads" in out["_provenance"]["dual_lead_implant"]


def test_one_lead_is_not():
    assert _facts({"Left": "Left GPe"})["dual_lead_implant"] is False


def test_no_stored_leads_leaves_it_unknown():
    assert "dual_lead_implant" not in _facts({})
