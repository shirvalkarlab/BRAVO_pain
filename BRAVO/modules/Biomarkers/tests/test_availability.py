"""Tests for the data-availability timeline extractor (routines/availability.py).

Django-free, runs on synthetic recording dicts shaped like the decoded Percept recordings the
production loader yields. Validates lane (dtype) mapping, timestamp/duration extraction, sensing
center-frequency attribution+snapping, the categorical legend bands, and the pain/stim series.
"""
import sys
import pathlib
import datetime

import numpy as np
import pandas as pd

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.Biomarkers.routines import availability as av

T0 = datetime.datetime(2025, 8, 29, 12, 0, 0).timestamp()


def _recs():
    """One recording per Percept product, in decoded-dict shapes (adapter contract)."""
    return {
        "MedtronicBrainSenseTimeDomain": [
            {"ChannelNames": ["ZERO_THREE_LEFT"], "Data": np.zeros((16750, 1)),
             "SamplingRate": 250, "StartTime": T0, "Duration": 67.0}],
        "MedtronicIndefiniteStream": [
            {"ChannelNames": ["ZERO_THREE_LEFT", "ONE_THREE_LEFT"], "Data": np.zeros((69413, 2)),
             "SamplingRate": 250, "StartTime": T0}],
        "MedtronicChronicBrainSense": [
            {"ChannelNames": ["LeftHemisphere LFP", "LeftHemisphere Amplitude"],
             "Time": np.array([T0 + i * 600 for i in range(20)]),
             "Data": np.column_stack([np.linspace(700, 900, 20), [1.5] * 20]),
             "SamplingRate": -1,
             "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": 12.7}}}}}],
        "MedtronicBrainSensePowerDomain": [
            {"ChannelNames": ["ZERO_THREE_RIGHT Power", "ZERO_THREE_RIGHT Stimulation"],
             "Data": np.zeros((208, 2)), "SamplingRate": 2, "StartTime": T0 + 7200,
             "Descriptor": {"Therapy": {"Right": {"SensingSetup": {"FrequencyInHertz": 13.66}}}}}],
        "MedtronicBaselineMontages": [
            {"ChannelNames": ["ZERO_THREE_LEFT"], "Data": np.zeros((250, 1)),
             "SamplingRate": 250, "StartTime": T0 + 3600, "PeakFrequencyInHertz": 10.74}],
    }


def test_lane_mapping_and_products():
    recs = av.extract_availability(_recs())
    by_dtype = {}
    for r in recs:
        by_dtype.setdefault(r["dtype"], set()).add(r["product"])
    # Indefinite + BrainSense TD land in the timedomain lane; a montage carrying real 2-D TD also
    # emits a "montage_td" coverage twin into the timedomain lane (raw-coverage parity with
    # streaming) while KEEPING its psd record. chronic+pd in bandpower.
    assert by_dtype["timedomain"] == {"streaming_td", "indefinite", "montage_td"}
    assert by_dtype["bandpower"] == {"timeline_lsb", "streaming_lsb"}
    assert by_dtype["psd"] == {"montage_psd"}


def test_montage_td_emits_coverage_twin_alongside_psd():
    """A survey/montage record with real 2-D TD Data surfaces BOTH as a psd record (its tick +
    modeled-LSB source) AND as a parallel timedomain coverage record on the SAME channel/time, so
    montage TD draws the same raw-coverage block as indefinite streaming. A PSD-only montage (no
    2-D Data) emits NO coverage twin."""
    recs = av.extract_availability(_recs())
    montage_psd = [r for r in recs if r["product"] == "montage_psd"][0]
    twin = [r for r in recs if r["product"] == "montage_td"]
    assert len(twin) == 1
    tw = twin[0]
    assert tw["dtype"] == "timedomain" and tw["channel"] == montage_psd["channel"]
    assert abs(tw["t_start"] - montage_psd["t_start"]) < 1e-6
    assert tw["meta"].get("from_product") == "montage_psd"
    # PSD-only montage (no real TD array) -> no coverage twin
    psd_only = {"MedtronicBaselineMontages": [
        {"ChannelNames": ["ZERO_THREE_LEFT"], "SamplingRate": 250,
         "StartTime": T0 + 3600, "PeakFrequencyInHertz": 10.74}]}   # no "Data"
    recs2 = av.extract_availability(psd_only)
    assert [r for r in recs2 if r["product"] == "montage_td"] == []
    assert [r for r in recs2 if r["product"] == "montage_psd"]    # psd record still present


def test_timestamp_and_duration():
    recs = av.extract_availability(_recs())
    td = [r for r in recs if r["product"] == "streaming_td"][0]
    assert abs(td["t_start"] - T0) < 1.0
    assert abs(td["dur_s"] - 67.0) < 0.01
    # chronic duration derived from its Time array span (19 * 600 s)
    chronic = [r for r in recs if r["product"] == "timeline_lsb"][0]
    assert abs(chronic["dur_s"] - 19 * 600) < 1.0


def test_center_freq_attribution_and_snap():
    recs = av.extract_availability(_recs())
    chronic = [r for r in recs if r["product"] == "timeline_lsb"][0]
    streaming = [r for r in recs if r["product"] == "streaming_lsb"][0]
    # chronic freq comes from the GROUP-level Therapy hemisphere fallback (12.7 exact bin)
    assert chronic["meta"]["center_hz"] == 12.7
    # power-domain 13.66 snaps to the 13.7 Percept FFT bin
    assert streaming["meta"]["center_hz"] == 13.7
    # montage peak snaps to 10.7
    montage = [r for r in recs if r["product"] == "montage_psd"][0]
    assert montage["meta"]["peak_hz"] == 10.7


def test_present_freq_bands_matches_rendered_channels():
    recs = av.extract_availability(_recs())
    # Only the two bandpower channels carry a configured center freq -> legend has exactly those.
    assert av.present_freq_bands(recs) == [12.7, 13.7]


def test_snap_freq_edges():
    assert av.snap_freq(None) is None
    assert av.snap_freq(13.66) == 13.7
    assert av.snap_freq(7.81) == 7.8
    assert av.snap_freq(float("nan")) is None


def test_pain_series_drops_nulls_and_sorts():
    pro = pd.DataFrame({"date_time_s1_daily": ["2025-08-30 10:00", "2025-08-29 09:00", None],
                        "nrs": [4, 7, 9]})
    ps = av.pain_series(pro, "nrs")
    assert ps["metric"] == "nrs"
    assert len(ps["t"]) == 2                 # null-timestamp row dropped
    assert ps["y"] == [7.0, 4.0]             # sorted by time (29th before 30th)
    assert ps["t"][0] < ps["t"][1]


def test_pain_series_missing_metric_column():
    pro = pd.DataFrame({"date_time_s1_daily": ["2025-08-29 09:00"], "nrs": [7]})
    assert av.pain_series(pro, "vas")["t"] == []   # metric absent -> empty, not error


def test_stim_series_concatenates_and_filters():
    chronic = [{"Time": np.array([T0 + i * 600 for i in range(5)]),
                "Data": np.column_stack([np.zeros(5), [0, 1.5, 1.5, 2.0, np.nan]])}]
    ss = av.stim_series(chronic)
    assert ss["y"] == [0.0, 1.5, 1.5, 2.0]   # NaN amplitude dropped
    assert len(ss["t"]) == 4


def test_empty_inputs_are_safe():
    assert av.extract_availability({}) == []
    assert av.extract_availability(None) == []
    assert av.pain_series(None, "nrs")["t"] == []
    assert av.stim_series([])["t"] == []
    assert av.present_freq_bands([]) == []
    assert av.lsb_series(None, None) == {}
    assert av.lsb_series([], []) == {}


def test_lsb_series_streaming_real_values_and_sentinel_filter():
    """Power-domain LSB: real per-sample values, sentinel/negative dropped, center freq tagged."""
    sentinel = 2.0 ** 31 - 1
    pd_rec = {
        "ChannelNames": ["ZERO_THREE_LEFT Power", "ZERO_THREE_LEFT Stimulation"],
        "Data": np.array([[535.0, 0.0], [596.0, 0.0], [sentinel, 0.0], [-3.0, 0.0], [610.0, 1.5]]),
        "SamplingRate": 2, "StartTime": T0,
        "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": 12.7}}}}}
    out = av.lsb_series([], [pd_rec])
    assert "ZERO_THREE_LEFT" in out
    s = out["ZERO_THREE_LEFT"]
    assert s["y"] == [535.0, 596.0, 610.0]            # sentinel and negative removed
    assert set(s["center_hz"]) == {12.7}              # snapped sensing center
    assert set(s["source"]) == {"streaming"}
    assert s["t"][0] == T0 and s["t"][1] == T0 + 0.5  # 2 Hz spacing, absolute time


def test_lsb_series_chronic_remaps_to_sensing_contact_and_pools():
    """Chronic LFP (named by hemisphere) is remapped onto the configured sensing CONTACT for that
    hemisphere, so streaming + chronic for the same physical channel pool into one lane."""
    pd_rec = {
        "ChannelNames": ["ZERO_THREE_LEFT Power"],
        "Data": np.array([[500.0], [520.0]]), "SamplingRate": 2, "StartTime": T0,
        "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": 12.7}}}}}
    chronic = [{"ChannelNames": ["LeftHemisphere LFP", "LeftHemisphere Amplitude"],
                "Time": np.array([T0 + 600, T0 + 1200]),
                "Data": np.column_stack([[810.0, 830.0], [1.5, 1.5]]), "SamplingRate": -1,
                "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": 12.7}}}}}]
    out = av.lsb_series(chronic, [pd_rec])
    # chronic folded onto the streaming contact, not a separate 'LeftHemisphere LFP' lane
    assert "ZERO_THREE_LEFT" in out
    assert "LeftHemisphere LFP" not in out
    s = out["ZERO_THREE_LEFT"]
    assert s["source"] == ["streaming", "streaming", "chronic", "chronic"]   # time-sorted
    assert s["y"] == [500.0, 520.0, 810.0, 830.0]


def test_lsb_series_psd_modeled_tier_from_montage_td():
    """Montage-survey TD with NO native LSB still gets a calibrated, FLAGGED modeled LSB point: the
    tier Welch-256s the TD and routes the band integral through analytics.psd_band_to_lsb (k=269).
    The emitted lsb must EQUAL psd_band_to_lsb on the same Welch PSD (single conversion path), and the
    sample must be tagged source='psd_modeled' / modeled=True so the frontend draws it distinctly."""
    from modules.Biomarkers.routines import analytics
    rng = np.random.default_rng(0)
    fs, center = 250.0, 20.0
    n = 250 * 30  # 30 s, like a montage sweep
    tsec = np.arange(n) / fs
    # a 20 Hz oscillation in µV + broadband noise -> real power in the 17.5-22.5 Hz band
    sig = 8.0 * np.sin(2 * np.pi * center * tsec) + rng.normal(0, 2.0, n)
    montage = [{
        "ChannelNames": ["ZERO_THREE_LEFT"],
        "Data": sig.reshape(-1, 1), "SamplingRate": fs, "StartTime": T0,
        "PeakFrequencyInHertz": center}]
    out = av.lsb_series([], [], montage_td_recordings=montage,
                        sensing_hz_by_channel={"ZERO_THREE_LEFT": center})
    assert "ZERO_THREE_LEFT" in out
    s = out["ZERO_THREE_LEFT"]
    assert s["source"] == ["psd_modeled"] and s["modeled"] == [True]
    assert s["method"][0].startswith("welch256_band_integral_x_k=269")
    # the lane's modeled LSB equals the shared helper applied to the same Welch-256 PSD
    f, psd = analytics.welch256_density(sig, fs)
    expect = analytics.psd_band_to_lsb(psd, f, center)["lsb"]
    assert abs(s["y"][0] - expect) < 1e-6, (s["y"][0], expect)
    assert s["y"][0] > 0 and s["t"][0] == float(T0)


def test_lsb_series_psd_modeled_canon_name_and_device_peak():
    """Montage-survey records use ring/sweep names (ZERO_AND_THREE_LEFT_RING) and carry the device's
    per-contact peak in Descriptor.MedtronicPSD. The tier must (a) canonicalize the name so the
    modeled point lands on the SAME lane as native LSB, and (b) use the device peak as the center when
    no configured sensing band is supplied for that contact."""
    rng = np.random.default_rng(1)
    fs, center = 250.0, 12.7
    n = 250 * 25
    tsec = np.arange(n) / fs
    sig = 6.0 * np.sin(2 * np.pi * center * tsec) + rng.normal(0, 2.0, n)
    montage = [{
        "ChannelNames": ["ZERO_AND_THREE_LEFT_RING"],
        "Data": sig.reshape(-1, 1), "SamplingRate": fs, "StartTime": T0,
        "Descriptor": {"MedtronicPSD": [{"PeakFrequencyInHertz": center}]}}]
    out = av.lsb_series([], [], montage_td_recordings=montage)   # no sensing_hz -> uses device peak
    assert "ZERO_THREE_LEFT" in out and "ZERO_AND_THREE_LEFT_RING" not in out
    s = out["ZERO_THREE_LEFT"]
    assert s["source"] == ["psd_modeled"] and s["center_hz"][0] == av.snap_freq(center)


def test_lsb_overview_modeled_tier_is_separate_hollow_layer():
    """Modeled points must NOT fold into native streaming session blocks or the chronic line — they
    ride a separate 'modeled' layer (hollow markers), and a modeled outlier must not rescale the
    native y-window."""
    lsb = {"ZERO_THREE_LEFT": {
        "t": [T0, T0 + 0.5, T0 + 1.0, T0 + 4000],
        "y": [500.0, 520.0, 510.0, 9000.0],                  # last is a big modeled outlier
        "center_hz": [12.7, 12.7, 12.7, 19.5],               # 19.5 is an exact Percept FFT bin
        "source": ["streaming", "streaming", "streaming", "psd_modeled"],
        "modeled": [False, False, False, True],
        "method": [None, None, None, "welch256_band_integral_x_k=269"]}}
    ov = av.lsb_overview(lsb)
    d = ov["ZERO_THREE_LEFT"]
    # streaming session block holds ONLY the 3 native samples; the modeled point is excluded
    assert len(d["sessions"]) == 1 and d["sessions"][0]["n"] == 3
    # modeled layer carries the one hollow point, with its (FFT-bin-snapped) center and method tag
    assert len(d["modeled"]) == 1
    assert d["modeled"][0]["y"] == 9000.0 and d["modeled"][0]["center_hz"] == 19.5
    assert d["modeled"][0]["method"] == "welch256_band_integral_x_k=269"
    # the native y-window is set by sensed samples only — the 9000 outlier does NOT widen it
    assert d["y_hi"] < 1000.0


def test_lsb_overview_compacts_to_chronic_line_and_session_blocks():
    """The overview collapses per-sample LSB into a chronic LINE + per-session BLOCKS, splitting
    sessions on a time gap AND on a sensing-frequency change."""
    # two streaming sessions (gap > 30 min) at the same freq, then one chronic run
    lsb = {"ZERO_THREE_LEFT": {
        "t": [T0, T0 + 0.5, T0 + 1.0,                      # session A (12.7 Hz)
              T0 + 7200, T0 + 7200.5,                      # session B (after a 2 h gap)
              T0 + 20000, T0 + 20600, T0 + 21200],         # chronic run
        "y": [500.0, 520.0, 510.0, 900.0, 920.0, 810.0, 830.0, 820.0],
        "center_hz": [12.7, 12.7, 12.7, 12.7, 12.7, 12.7, 12.7, 12.7],
        "source": ["streaming", "streaming", "streaming", "streaming", "streaming",
                   "chronic", "chronic", "chronic"]}}
    ov = av.lsb_overview(lsb)
    d = ov["ZERO_THREE_LEFT"]
    assert d["chronic"] is not None and len(d["chronic"]["t"]) == 3   # chronic line present
    assert len(d["sessions"]) == 2                                    # two streaming blocks
    s0 = d["sessions"][0]
    assert s0["t0"] == T0 and s0["n"] == 3 and s0["med"] == 510.0     # session summary stats
    assert s0["center_hz"] == 12.7
    assert d["y_lo"] <= 510.0 <= d["y_hi"]                            # robust window spans values


def test_lsb_overview_splits_session_on_frequency_change():
    """A sensing-frequency change starts a NEW session block even without a time gap."""
    lsb = {"ZERO_THREE_RIGHT": {
        "t": [T0, T0 + 0.5, T0 + 1.0, T0 + 1.5],
        "y": [100.0, 110.0, 700.0, 720.0],
        "center_hz": [8.78, 8.78, 26.37, 26.37],         # freq switches mid-stream
        "source": ["streaming", "streaming", "streaming", "streaming"]}}
    ov = av.lsb_overview(lsb)
    sessions = ov["ZERO_THREE_RIGHT"]["sessions"]
    assert len(sessions) == 2
    assert [s["center_hz"] for s in sessions] == [8.8, 26.4]   # snapped to FFT bins


def test_lsb_overview_chronic_line_carries_center_hz():
    """The chronic 24/7 trend now carries a per-sample sensing center frequency (the band IS
    reprogrammed over time), aligned with t/y through decimation so the frontend can colour it."""
    lsb = {"ZERO_THREE_LEFT": {
        "t": [T0 + i for i in range(8)],
        "y": [800.0 + i for i in range(8)],
        "center_hz": [9.8, 9.8, 9.8, 9.8, 12.7, 12.7, 12.7, 12.7],   # band switches mid-record
        "source": ["chronic"] * 8}}
    chronic = av.lsb_overview(lsb)["ZERO_THREE_LEFT"]["chronic"]
    assert chronic is not None
    assert "center_hz" in chronic
    # same length as t/y, and both programmed bands are represented in order
    assert len(chronic["center_hz"]) == len(chronic["t"]) == len(chronic["y"])
    assert set(chronic["center_hz"]) == {9.8, 12.7}
    assert chronic["center_hz"][0] == 9.8 and chronic["center_hz"][-1] == 12.7


def test_event_markers_labels_patient_events():
    """Patient-annotated events -> one labeled marker per press with the patient's label, the peak
    frequency, hemisphere count, and a decimated PSD for the hover-overview."""
    freq = np.arange(0, 100.5, 0.5)
    # two hemispheres: a clear beta peak at 13.5 Hz above the 1/f floor (snaps to the 13.7 Hz bin)
    floor = 1.0 / (freq + 1.0)
    p1 = floor.copy(); p1[freq == 13.5] = 50.0
    p2 = floor.copy(); p2[freq == 13.5] = 40.0
    ev = [{"name": "Higher Pain", "t": T0 + 3600, "psds": [(freq, p1)]},
          {"name": "Feeling Good", "t": T0, "psds": [(freq, p1), (freq, p2)]}]
    out = av.event_markers(ev)
    assert out["n"] == 2
    assert out["labels"] == ["Feeling Good", "Higher Pain"]   # distinct labels, sorted
    e0 = out["events"][0]                                      # sorted by time -> Feeling Good first
    assert e0["t"] == T0 and e0["label"] == "Feeling Good" and e0["n_chan"] == 2
    assert e0["peak_hz"] == 13.7                               # snapped beta peak, averaged
    assert e0["peak_power"] is not None and e0["peak_power"] > 1.0
    assert e0["psd"] is not None and len(e0["psd"]["freq"]) == len(e0["psd"]["mag"])
    assert [e["t"] for e in out["events"]] == [T0, T0 + 3600]


def test_event_markers_label_without_psd_is_kept():
    """An event with a label but no usable spectrum still appears (peak_hz/psd null), so the press
    is demarcated even when the snapshot PSD is absent."""
    out = av.event_markers([{"name": "Medication", "t": T0, "psds": []}])
    assert out["n"] == 1
    e = out["events"][0]
    assert e["label"] == "Medication" and e["peak_hz"] is None and e["psd"] is None


def test_event_markers_handles_empty_and_malformed():
    assert av.event_markers([])["n"] == 0
    assert av.event_markers(None)["n"] == 0
    assert av.event_markers([{"t": None}, {"no_time": 1}, 42])["n"] == 0


def test_montage_event_dedup_against_psd_times():
    """Montage-PSD snapshots that coincide (within tolerance) with an already-shown montage/survey
    PSD recording are dropped; only the unmatched sweeps survive. (Mirrors the dedup in
    bravo_service._load_montage_psd_events, exercised here on its core bisect logic.)"""
    import bisect
    dedup = sorted([T0, T0 + 1000.0, T0 + 5000.0])
    tol = 5.0

    def is_dup(t):
        i = bisect.bisect_left(dedup, t)
        return any(0 <= j < len(dedup) and abs(dedup[j] - t) <= tol for j in (i - 1, i))

    snaps_t = [T0 + 2.0,      # within 5 s of T0           -> dup
               T0 + 1004.0,   # within 5 s of T0+1000      -> dup
               T0 + 2500.0,   # no match                   -> keep
               T0 + 5000.0,   # exact match                -> dup
               T0 + 9000.0]   # no match                   -> keep
    kept = [t for t in snaps_t if not is_dup(t)]
    assert kept == [T0 + 2500.0, T0 + 9000.0]
