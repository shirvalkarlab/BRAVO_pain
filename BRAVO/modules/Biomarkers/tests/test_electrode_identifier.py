"""The electrode identifier check (the PI, 2026-10-06): the device's own spectra and rankings of each
electrode against the other lead's contact 3, stimulation off, shown at the bottom of the Biomarkers
page. Device values at face value: nothing is computed from a spectrum; the ranking, selected and
peak frequencies and artefact flag are the device's own.

Pinned: electrodes and references are named in the clinic's numbering (left 0-3, right 8-11,
segments 1a-2c / 9a-10c); a run's side and group (rings or segments) come from its channels; a run
whose PSD entries hold no values, or that has none, is counted but carries no spectrum; a spectrum
whose run could not be told is kept and flagged; the summary counts, per side and group, how often
the device ranked each electrode highest among the runs it ranked. Plain `assert`, no arguments."""
from modules.Biomarkers.routines import electrode_identifier as EI

FREQ = [round(0.9765625 * i, 2) for i in range(100)]


def _entry(el, side, ranking="HIGHEST_RANK", sel=11.72, peak=11.72, art="ARTIFACT_NOT_PRESENT", values=True):
    ref_side = "Right" if side == "Left" else "Left"
    return {"SensingElectrodes": el, "Hemisphere": side, "ReferenceElectrode": "ELECTRODE_THREE_RING",
            "ReferenceHemisphere": ref_side, "RankingatSelectedFrequency": ranking,
            "SelectedFrequencyInHertz": sel, "PeakFrequencyInHertz": peak, "PeakMagnitudeInMicroVoltRMS": 1.5,
            "ArtifactStatus": art, "LFPFrequencyinHertz": FREQ if values else [],
            "LFPMagnitudeinMicroVoltPeak": [0.1 * (i % 7) for i in range(100)] if values else []}


def _run(t, side, entries, electrodes=None):
    ref = "RIGHT" if side == "Left" else "LEFT"
    els = electrodes or [e["SensingElectrodes"] for e in entries if isinstance(e, dict)]
    return {"StartTime": t, "ChannelNames": [f"{el}_{side.upper()}_REFERENCE_ELECTRODE_THREE_RING_{ref}" for el in els],
            "Descriptor": {"MedtronicPSD": entries}}


RINGS = ["ELECTRODE_ZERO_RING", "ELECTRODE_ONE_RING", "ELECTRODE_TWO_RING", "ELECTRODE_THREE_RING"]


def test_electrodes_and_references_use_the_clinic_numbering():
    assert EI.electrode_label("ELECTRODE_ZERO_RING", "Left") == "0"
    assert EI.electrode_label("ELECTRODE_THREE_RING", "Right") == "11"
    assert EI.electrode_label("ELECTRODE_ONE_A", "Left") == "1a"
    assert EI.electrode_label("ELECTRODE_TWO_C", "Right") == "10c"
    run = EI.runs([_run(1.0e9, "Left", [_entry(e, "Left") for e in RINGS])], [])[0]
    assert run["side"] == "Left" and run["group"] == "rings" and run["reference"] == "11 (right lead)"
    assert [e["electrode"] for e in run["electrodes"]] == ["0", "1", "2", "3"]


def test_device_values_pass_through_unchanged():
    e = _entry("ELECTRODE_ONE_RING", "Left", ranking="MIDDLE_RANK", sel=16.6, peak=21.48, art="SQC_ARTIFACT_PRESENT")
    run = EI.runs([_run(1.0e9, "Left", [e])], [])[0]
    got = run["electrodes"][0]
    assert got["uvp"] == e["LFPMagnitudeinMicroVoltPeak"] and got["freq"] == e["LFPFrequencyinHertz"]
    assert (got["ranking"], got["selected_hz"], got["peak_hz"], got["artifact"]) == ("middle", 16.6, 21.48, True)


def test_runs_without_values_or_without_entries_are_counted_with_no_spectrum():
    empty = _run(2.0e9, "Right", [_entry(e, "Right", ranking="", sel=0, peak=0, art="", values=False) for e in RINGS])
    none = _run(3.0e9, "Right", [None, None, None, None], electrodes=RINGS)
    rs = EI.runs([empty, none], [])
    assert [r["psd"] for r in rs] == ["entries without values", "no PSD entry"]
    assert all(not r["electrodes"] or all(e["uvp"] == [] for e in r["electrodes"]) for r in rs)
    assert all(r["side"] == "Right" and r["group"] == "rings" for r in rs)


def test_a_spectrum_whose_run_could_not_be_told_is_kept_and_flagged():
    unknown = {"StartTime": 4.0e9, "RunUnknown": True, "Source": "BrainSenseSurveys/ElectrodeIdentifier",
               "Descriptor": {"MedtronicPSD": [_entry("ELECTRODE_ONE_A", "Left")]}}
    other = {"StartTime": 4.0e9, "RunUnknown": True, "Source": "LFPMontage",
             "Descriptor": {"MedtronicPSD": [_entry("ELECTRODE_ONE_A", "Left")]}}
    rs = EI.runs([], [unknown, other])
    assert len(rs) == 1 and rs[0]["run_unknown"] is True and rs[0]["group"] == "segments"


def test_the_summary_counts_how_often_each_electrode_was_ranked_highest_per_side_and_group():
    def ranked(t, top, side="Left"):
        return _run(t, side, [_entry(e, side, ranking="HIGHEST_RANK" if e == top else "LOWEST_RANK") for e in RINGS])
    recs = [ranked(1e9, "ELECTRODE_ONE_RING"), ranked(2e9, "ELECTRODE_ONE_RING"), ranked(3e9, "ELECTRODE_ZERO_RING"),
            _run(4e9, "Left", [_entry(e, "Left", ranking="NOT_AVAILABLE", sel=0) for e in RINGS]),
            ranked(5e9, "ELECTRODE_TWO_RING", side="Right")]
    s = EI.summary(EI.runs(recs, []))
    left = s["Left rings"]
    assert (left["n_runs"], left["n_with_spectra"], left["n_ranked"]) == (4, 4, 3)
    assert left["highest_counts"] == {"1": 2, "0": 1} and left["most_often_highest"] == ["1"]
    assert left["selected_hz"]["n"] == 3                       # a run with no frequency selected is not counted
    assert s["Right rings"]["highest_counts"] == {"10": 1}     # sides never pooled


def test_insufficient_separation_is_a_ranked_run_with_no_highest():
    rec = _run(1e9, "Left", [_entry(e, "Left", ranking="INSUFFICIENT_SIGNAL_SEPARATION") for e in RINGS])
    s = EI.summary(EI.runs([rec], []))["Left rings"]
    assert s["n_ranked"] == 0 and s["n_insufficient_separation"] == 1 and s["highest_counts"] == {}


def test_single_electrode_spectra_of_one_session_and_side_form_one_row_still_flagged():
    """The export stores a run-unknown spectrum one electrode per record; those of one session start,
    side and group are the export's one PSD set and are shown as one row. A repeated electrode means
    two sets, which are never merged."""
    def one(el, t=4.0e9, side="Left"):
        return {"StartTime": t, "RunUnknown": True, "Source": "BrainSenseSurveys/ElectrodeIdentifier",
                "Descriptor": {"MedtronicPSD": [_entry(el, side)]}}
    rs = EI.runs([], [one(e) for e in RINGS] + [one("ELECTRODE_ZERO_RING", side="Right")])
    assert [(r["side"], len(r["electrodes"]), r["run_unknown"]) for r in rs] == [("Left", 4, True), ("Right", 1, True)]
    twice = EI.runs([], [one("ELECTRODE_ZERO_RING"), one("ELECTRODE_ZERO_RING")])
    assert [len(r["electrodes"]) for r in twice] == [1, 1]
