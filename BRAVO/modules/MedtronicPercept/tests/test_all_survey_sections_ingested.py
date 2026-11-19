"""Every survey, signal-check and threshold section of an export is ingested (the PI, 2026-10-05,
decision 443: "ingest ALL of them ... if EVEN one BIT is OFF, INGEST and TIMESTAMP"). Until now the
ingester read only the montage, the electrode identifier and the calibration tests; the electrode
survey (time-domain and spectra), the electrode identifier's spectra, the in-session signal check
and the threshold band-power streams were never read.

Rules, all on the device's own values compared bit for bit, never recomputed or rescaled:
- an electrode-survey stream identical to the montage stream of the same start and contact pair is
  the same recording written twice and is dropped; one value different -> ingested;
- a spectrum (montage, electrode survey, electrode identifier) goes to its run when exactly one run
  on its side carries its contact pair; otherwise it is kept as a spectrum of unknown run, to be
  stamped with the session start; a survey spectrum identical to a montage spectrum is dropped;
- a signal-check spectrum identical to any other spectrum of the export is dropped, otherwise kept;
- every threshold band-power stream is kept with its own start time and every reading."""
import copy

from modules.MedtronicPercept import Percept

T1, T2, T3 = "2026-06-10T18:00:00Z", "2026-06-10T18:05:00Z", "2026-06-10T18:10:00Z"
PAIRS = ["ZERO_AND_ONE", "ZERO_AND_TWO", "ZERO_AND_THREE", "ONE_AND_TWO", "ONE_AND_THREE", "TWO_AND_THREE"]


def td(t, ch, base=0.0, ticks_key="TicksInMses", data_key="TimeDomainData"):
    s = {"FirstPacketDateTime": t, "Channel": ch, "Pass": "FIRST", "Gain": 250, "SampleRateInHz": 250,
         "GlobalSequences": ",".join(str(i) for i in range(1, 11)), "GlobalPacketSizes": ",".join(["50"] * 10),
         ticks_key: "", data_key: [base + i for i in range(500)]}
    if ticks_key == "TicksInMs":
        s["Hemisphere"] = "HemisphereLocationDef." + ("Left" if "LEFT" in ch else "Right")
    return s


def psd(pair, side, scale=1.0, fkey="LFPFrequency", mkey="LFPMagnitude"):
    return {"SensingElectrodes": "SensingElectrodeConfigDef." + pair, "Hemisphere": "HemisphereLocationDef." + side,
            "ArtifactStatus": "ARTIFACT_NOT_PRESENT", fkey: [1.0, 2.0, 3.0], mkey: [scale * 1.0, scale * 2.0, 3.0]}


def export():
    montage = [td(T1, p + "_LEFT_RING", 1) for p in PAIRS] + [td(T2, p + "_LEFT_RING", 2) for p in PAIRS] \
        + [td(T3, p + "_RIGHT_RING", 3) for p in PAIRS]
    survey_td = [td(T1, p + "_LEFT_RING", 1, "TicksInMs", "TimeDomainDatainMicroVolts") for p in PAIRS]
    survey_td[0]["TimeDomainDatainMicroVolts"][7] += 0.001          # one value off: a new recording
    return {
        "SessionDate": "2026-06-10T17:55:00Z",
        "LfpMontageTimeDomain": montage,
        "LFPMontage": [psd(p, "Left") for p in PAIRS] + [psd(p, "Right") for p in PAIRS],
        "BrainSenseSurveysTimeDomain": [{"SurveyMode": "ElectrodeSurvey", "ElectrodeSurvey": survey_td},
                                        {"SurveyMode": "ElectrodeIdentifier", "ElectrodeIdentifier": [
                                            dict(td(T3, "ELECTRODE_ONE_A", 9, "TicksInMs", "TimeDomainDatainMicroVolts"),
                                                 Hemisphere="HemisphereLocationDef.Left")]}],
        "BrainSenseSurveys": [{"SurveyMode": "ElectrodeSurvey", "ElectrodeSurvey":
                               [psd(p, "Right", 1.0, "LFPFrequencyinHertz", "LFPMagnitudeinMicroVoltPeak") for p in PAIRS[:5]]
                               + [psd(PAIRS[5], "Right", 7.0, "LFPFrequencyinHertz", "LFPMagnitudeinMicroVoltPeak")]},
                              {"SurveyMode": "ElectrodeIdentifier", "ElectrodeIdentifier":
                               [psd("ELECTRODE_ONE_A", "Left", 5.0, "LFPFrequencyinHertz", "LFPMagnitudeinMicroVoltPeak")]}],
        "MostRecentInSessionSignalCheck": [
            {"Channel": "ZERO_AND_THREE_LEFT", "ArtifactStatus": "x", "SignalFrequencies": [1.0, 2.0, 3.0],
             "SignalPsdValues": [1.0, 2.0, 3.0], "PeakFrequencies": [], "PeakValues": []},
            {"Channel": "ONE_AND_THREE_LEFT", "ArtifactStatus": "x", "SignalFrequencies": [1.0, 2.0, 3.0],
             "SignalPsdValues": [4.0, 4.0, 4.0], "PeakFrequencies": [], "PeakValues": []}],
        "Thresholds": [{"Channel": "Left", "FirstPacketDateTime": T2, "SampleRateInHz": 2,
                        "LfpData": [{"Seq": i, "Left": {"LFP": 100 + i}, "Right": {}} for i in range(5)]}],
        "Groups": {"Final": [{"ActiveGroup": True, "ProgramSettings": {"SensingChannel": [
            {"HemisphereLocation": "HemisphereLocationDef.Left", "Channel": "SensingElectrodeConfigDef.ONE_AND_THREE",
             "SensingSetup": {"FrequencyInHertz": 23.44}, "UpperLfpThreshold": 900.0, "LowerLfpThreshold": 400.0,
             "MeasuredUpperLfp": 950, "MeasuredLowerLfp": 380, "ElectrodeState": []},
            {"HemisphereLocation": "HemisphereLocationDef.Right", "Channel": "SensingElectrodeConfigDef.ZERO_AND_TWO"}]}}]},
    }


def _run():
    data = {}
    J = export()
    Percept.extractBrainSenseSurvey(copy.deepcopy(J), data)
    Percept.extractThresholdStreams(copy.deepcopy(J), data)
    return data


def test_montage_spectra_go_to_their_single_run_or_are_kept_with_run_unknown():
    data = _run()
    right = [s for s in data["MontagesTD"] if "RIGHT" in s["Channel"]]
    assert all("PSD" in s for s in right)                         # one right run: attached
    left = [s for s in data["MontagesTD"] if "LEFT" in s["Channel"]]
    assert not any("PSD" in s for s in left)                      # two left runs: not guessed
    unknown = [u for u in data["SurveyPSDRunUnknown"] if u["source"] == "LFPMontage"]
    assert len(unknown) == 6 and all(len(u["candidate_runs"]) == 2 for u in unknown)


def test_electrode_survey_streams_identical_to_the_montage_are_dropped_one_value_off_kept():
    data = _run()
    assert [s["Channel"] for s in data["ElectrodeSurveyTD"]] == [PAIRS[0] + "_LEFT_RING"]


def test_survey_spectra_identical_to_montage_dropped_differing_ingested():
    data = _run()
    es = [u for u in data["SurveyPSDRunUnknown"] if u["source"] == "BrainSenseSurveys/ElectrodeSurvey"]
    attached = [s for s in data["MontagesTD"] if s.get("SurveyPSD")]
    assert len(es) + len(attached) == 1                           # only the one that differs


def test_electrode_identifier_spectrum_attached_to_its_run():
    data = _run()
    ei = data["ElectrodeIdentifierTD"]
    assert len(ei) == 1 and ei[0]["PSD"]["LFPMagnitudeinMicroVoltPeak"] == [5.0, 10.0, 3.0]


def test_signal_checks_identical_to_another_spectrum_dropped_others_kept():
    data = _run()
    assert [c["Channel"] for c in data["SignalCheckPSD"]] == ["ONE_AND_THREE_LEFT"]


def test_threshold_streams_kept_with_start_and_every_reading():
    data = _run()
    th = data["ThresholdPower"]
    assert len(th) == 1 and th[0]["Channel"] == "Left"
    setup = th[0]["SensingSetup"]                                  # the side's own settings, as written
    assert setup["Channel"] == "SensingElectrodeConfigDef.ONE_AND_THREE"
    assert setup["SensingSetup"]["FrequencyInHertz"] == 23.44 and setup["UpperLfpThreshold"] == 900.0
    assert list(th[0]["Sequences"]) == [0, 1, 2, 3, 4] and list(th[0]["LeftPower"]) == [100, 101, 102, 103, 104]
    assert th[0]["FirstPacketDateTime"] == Percept.getTimestamp(T2)


def test_each_section_becomes_a_stored_recording_with_its_time():
    from modules.MedtronicPercept import Session
    data = _run()
    start = Percept.getTimestamp("2026-06-10T17:55:00Z")
    recs = Session.surveyExtraRecordings(data, start)
    by = {}
    for r in recs:
        by.setdefault(r["type"], []).append(r)
    assert len(by["MedtronicElectrodeSurvey"]) == 1 and by["MedtronicElectrodeSurvey"][0]["date"] == Percept.getTimestamp(T1)
    assert len(by["MedtronicSurveyPSD"]) == 6 + (1 if not any(s.get("SurveyPSD") for s in data["MontagesTD"]) else 0)
    assert all(r["date"] == start and r["recording"]["RunUnknown"] for r in by["MedtronicSurveyPSD"])
    assert len(by["MedtronicSignalCheckPSD"]) == 1 and by["MedtronicSignalCheckPSD"][0]["date"] == start
    assert len(by["MedtronicThresholdPowerDomain"]) == 1 and by["MedtronicThresholdPowerDomain"][0]["date"] == Percept.getTimestamp(T2)
