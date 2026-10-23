"""Duplicates across exports are decided on the device's values, bit for bit (the PI, 2026-10-05,
decision 445): "If exact bit for bit duplicate with existing ingested recording, ok to DROP, but if
EVEN one bit is off, INGEST". On RCS08 the same montage spectrum appears in many exports (3,830 copies
of 108 spectra whose run cannot be told), and 5 time-domain streams appear twice with identical
values but different bookkeeping.

Values: the key of a spectrum ignores everything but contact pair, side, frequencies and magnitudes,
under either export spelling; a time-domain copy with identical values, or the start of a stored one,
is a duplicate; a longer stream whose start is the stored one replaces it; one value off is new."""
import numpy as np

from modules.MedtronicPercept.BrainSenseSurvey import spectrumKey, streamRelation


def test_spectrum_key_reads_only_device_values_under_either_spelling():
    a = {"SensingElectrodes": "SensingElectrodeConfigDef.ZERO_AND_THREE", "Hemisphere": "HemisphereLocationDef.Left",
         "LFPFrequency": [1.0, 2.0], "LFPMagnitude": [3.0, 4.0], "ArtifactStatus": "x"}
    b = {"SensingElectrodes": "SensingElectrodeConfigDef.ZERO_AND_THREE", "Hemisphere": "HemisphereLocationDef.Left",
         "LFPFrequencyinHertz": [1.0, 2.0], "LFPMagnitudeinMicroVoltPeak": [3.0, 4.0], "PeakFrequencyInHertz": 9}
    c = dict(a, LFPMagnitude=[3.0, 4.0000001])
    assert spectrumKey(a) == spectrumKey(b) != spectrumKey(c)


def test_stream_relation_on_values():
    x = np.arange(20.0).reshape(10, 2)
    assert streamRelation(x, x.copy()) == "duplicate"
    assert streamRelation(x, x[:4]) == "duplicate"                 # new is the start of the stored
    assert streamRelation(x[:4], x) == "longer"                    # stored is the start of the new
    y = x.copy(); y[3, 1] += 1e-9
    assert streamRelation(x, y) == "new"
