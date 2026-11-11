"""Each montage keeps only its own device spectra (the PI, 2026-10-05, decision 442). The survey
saver appended the PSD of every stream in an export to every montage in it, so an export with two
montages gave each the other's spectra too, stamped with the wrong montage's start time.

Values: two montages at different times, two channels each, one PSD per stream: each montage holds
exactly its own two spectra, in its own channel order."""
import numpy as np

from modules.MedtronicPercept import BrainSenseSurvey


def _stream(t, ch, psd_tag):
    return {"FirstPacketDateTime": t, "Channel": ch, "SamplingRate": 250, "Data": np.zeros(500),
            "Missing": np.zeros(500), "PSD": {"tag": psd_tag, "Channel": ch}}


def test_each_montage_holds_its_own_spectra_only():
    streams = [_stream(100.0, "A", "a100"), _stream(100.0, "B", "b100"),
               _stream(200.0, "A", "a200"), _stream(200.0, "B", "b200")]
    recs = BrainSenseSurvey.saveBrainSenseSurvey(streams)
    by_time = {r["StartTime"]: [p["tag"] for p in r["Descriptor"]["MedtronicPSD"]] for r in recs}
    assert by_time == {100.0: ["a100", "b100"], 200.0: ["a200", "b200"]}
