"""Device-flagged artifact spectra remain stored but cannot select bands.
Synthetic montage and signal-check fixtures exercise SQC/CT artifact flags;
IMPEDANCE_FAILURE is not an artifact flag under the upstream device rule D17.
"""
import numpy as np

from modules.Biomarkers import bravo_service as BS

F = list(np.arange(0.0, 100.0, 0.98))
P = [1.0] * len(F)


def _montage(entries, t="2020-01-01T10:00:00Z"):
    return {"StartTime": t, "Descriptor": {"MedtronicPSD": entries}}


def _entry(pair, hemi, status):
    e = {"SensingElectrodes": f"SensingElectrodeConfigDef.{pair}", "Hemisphere": f"HemisphereLocationDef.{hemi}",
         "LFPFrequency": F, "LFPMagnitude": P}
    if status is not None:
        e["ArtifactStatus"] = status
    return e


def _check(channel, status):
    return {"StartTime": "2020-01-01T11:00:00Z",
            "Descriptor": {"SignalCheck": {"Channel": f"SensingElectrodeConfigDef.{channel}",
                                           "SignalFrequencies": F, "SignalPsdValues": P,
                                           "ArtifactStatus": status}}}


def test_the_flag_rule():
    assert BS._psd_artifact_flagged("ArtifactStatusDef.SQC_ARTIFACT_PRESENT")
    assert BS._psd_artifact_flagged("CT_ARTIFACT_PRESENT")
    assert not BS._psd_artifact_flagged("ArtifactStatusDef.ARTIFACT_NOT_PRESENT")
    assert not BS._psd_artifact_flagged("IMPEDANCE_FAILURE")
    assert not BS._psd_artifact_flagged(None) and not BS._psd_artifact_flagged("")


def test_flagged_montage_and_signal_check_psds_give_no_band_choice_block():
    recs = [_montage([_entry("ZERO_AND_THREE", "Left", "ArtifactStatusDef.ARTIFACT_NOT_PRESENT"),
                      _entry("ONE_AND_THREE", "Left", "ArtifactStatusDef.SQC_ARTIFACT_PRESENT"),
                      _entry("ZERO_AND_TWO", "Left", None),
                      _entry("ZERO_AND_THREE", "Right", "IMPEDANCE_FAILURE")]),
            _check("ZERO_AND_THREE_LEFT", "ArtifactStatusDef.CT_ARTIFACT_PRESENT"),
            _check("ONE_AND_THREE_LEFT", "ArtifactStatusDef.ARTIFACT_NOT_PRESENT")]
    blocks = BS._montage_psd_lsb_blocks("uid", montage_recordings=recs)
    got = sorted((b["channel"], b["origin"]) for b in blocks)
    assert got == sorted([("ZERO_THREE_LEFT", "montage"), ("ZERO_TWO_LEFT", "montage"),
                          ("ZERO_THREE_RIGHT", "montage"), ("ONE_THREE_LEFT", "signal check")]), got
    out = BS._montage_psd_artifact_excluded(recs)
    assert out == {"ONE_THREE_LEFT": 1, "ZERO_THREE_LEFT": 1}, out


def test_the_stored_pieces_are_filed_under_the_new_rule():
    """The stored 3 s pieces' label is built from database rows and constants, which this rule
    changes neither of; without the rule version the old pieces, flagged PSDs and all, would be
    served."""
    assert "flagged_psds_out" in BS._RAW_LSB_RULE_VERSION
    assert BS._RAW_LSB_RULE_VERSION in BS._raw_lsb_constants_block()
