"""Each side's stimulation program read from the device's active group (decision 467), for the
Closed-Loop page's "Inherit current settings". Pure: a hand-written group, the shape of RCS08's
2026-09-30 export (both spellings of "SenSight" occur in one list there)."""
from ClosedLoopDeployment import device_facts as DF


def _ch(side, cath, mA, pw, lo, hi, suspend=True):
    st = [{"Electrode": f"ElectrodeDef.{'SenSight' if i == 0 else 'Sensight'}_{c}",
           "ElectrodeStateResult": "ElectrodeStateDef.Negative", "ElectrodeAmplitudeInMilliAmps": mA}
          for i, c in enumerate(cath)]
    st.append({"Electrode": "ElectrodeDef.Case", "ElectrodeStateResult": "ElectrodeStateDef.Positive"})
    ch = {"HemisphereLocation": f"HemisphereLocationDef.{side}", "ElectrodeState": st,
          "PulseWidthInMicroSecond": pw, "RateInHertz": 55, "LowerLimitInMilliAmps": lo,
          "UpperLimitInMilliAmps": hi, "Channel": "SensingElectrodeConfigDef.ONE_AND_THREE"}
    if suspend:
        ch["SuspendAmplitudeInMilliAmps"] = round(mA * len(cath), 2)
    return ch


def test_each_side_reads_its_own_contacts_amplitude_pulse_width_and_limits():
    p = DF.programmed_stimulation([_ch("Left", ["2a", "2b", "2c"], 1.0, 100, 1.4, 4.0),
                                   _ch("Right", ["1a", "1b", "1c", "2a", "2b", "2c"], 0.4166, 150, 1.2, 3.0)])
    assert p["Left"]["contacts"] == {"2a": -1, "2b": -1, "2c": -1, "case": 1}
    assert (p["Left"]["amp_mA"], p["Left"]["pw_us"], p["Left"]["lower_limit_mA"], p["Left"]["upper_limit_mA"]) == (3.0, 100.0, 1.4, 4.0)
    assert len([v for v in p["Right"]["contacts"].values() if v == -1]) == 6
    assert (p["Right"]["pw_us"], p["Right"]["upper_limit_mA"], p["Right"]["sensing_channel"]) == (150.0, 3.0, "ONE_AND_THREE")


def test_without_a_paused_amplitude_the_negative_contacts_currents_are_summed():
    p = DF.programmed_stimulation([_ch("Left", ["2a", "2b", "2c"], 1.0, 100, None, None, suspend=False)])
    assert p["Left"]["amp_mA"] == 3.0 and p["Left"]["lower_limit_mA"] is None


def test_the_group_reader_carries_the_program():
    d = {"Groups": {"Final": [{"ActiveGroup": True, "GroupId": "GroupIdDef.GROUP_D",
                               "ProgramSettings": {"RateInHertz": 55,
                                                   "SensingChannel": [_ch("Left", ["2a"], 3.0, 100, 1.4, 4.0)]}}]}}
    assert DF.active_sensing_group_from_report(d)["active_sensing_group_program"]["Left"]["contacts"] == {"2a": -1, "case": 1}
