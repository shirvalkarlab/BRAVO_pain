"""Every device spectrum ingested since decision 443 reaches matching (the PI, 2026-10-05: "use for
matching", decision 446): the electrode survey's own spectra (survey spelling `...inHertz`,
`...inMicroVoltPeak`), spectra of unknown run (at the session start) and the in-session signal check
(`SensingChannelDef.<pair>_<side>`, `SignalFrequencies`, `SignalPsdValues`). Device values as written;
nothing rescaled.

Values: one montage spectrum, one extra survey spectrum on the same recording, one run-unknown
spectrum, one signal check -> four blocks, each on its contact pair and time, values untouched."""
from modules.Biomarkers import bravo_service as bs


def test_every_spectrum_kind_becomes_a_block_on_its_pair_and_time():
    mont = {"RecordingType": "MedtronicBrainSenseSurvey", "StartTime": 1750001000.0,
            "Descriptor": {"MedtronicPSD": [{"SensingElectrodes": "SensingElectrodeConfigDef.ZERO_AND_THREE",
                                              "Hemisphere": "HemisphereLocationDef.Left",
                                              "LFPFrequency": [1.0, 2.0], "LFPMagnitude": [3.0, 4.0]}],
                           "SurveyPSD": [{"SensingElectrodes": "SensingElectrodeConfigDef.ONE_AND_THREE",
                                          "Hemisphere": "HemisphereLocationDef.Left",
                                          "LFPFrequencyinHertz": [1.0, 2.0], "LFPMagnitudeinMicroVoltPeak": [5.0, 6.0]}]}}
    unknown = {"RecordingType": "MedtronicSurveyPSD", "StartTime": 1750000900.0, "RunUnknown": True,
               "Descriptor": {"MedtronicPSD": [{"SensingElectrodes": "SensingElectrodeConfigDef.ZERO_AND_TWO",
                                                 "Hemisphere": "HemisphereLocationDef.Right",
                                                 "LFPFrequency": [1.0, 2.0], "LFPMagnitude": [7.0, 8.0]}]}}
    check = {"RecordingType": "MedtronicSignalCheckPSD", "StartTime": 1750000900.0,
             "Descriptor": {"SignalCheck": {"Channel": "SensingChannelDef.ZERO_THREE_RIGHT",
                                            "SignalFrequencies": [1.0, 2.0], "SignalPsdValues": [9.0, 10.0]}}}
    blocks = bs._montage_psd_lsb_blocks("u", montage_recordings=[mont, unknown, check])
    got = sorted((b["channel"], b["t"], list(b["power"]), b["origin"]) for b in blocks)
    assert got == [
        ("ONE_THREE_LEFT", 1750001000.0, [5.0, 6.0], "electrode survey"),
        ("ZERO_THREE_LEFT", 1750001000.0, [3.0, 4.0], "montage"),
        ("ZERO_THREE_RIGHT", 1750000900.0, [9.0, 10.0], "signal check"),
        ("ZERO_TWO_RIGHT", 1750000900.0, [7.0, 8.0], "run unknown"),
    ]


def test_the_new_types_are_loaded_for_matching():
    assert "MedtronicElectrodeSurvey" in bs.AVAILABILITY_PSD_TYPES
    assert set(bs.SPECTRUM_ONLY_TYPES) == {"MedtronicSurveyPSD", "MedtronicSignalCheckPSD"}
