"""The Biomarkers page's top timeline is an ACQUISITION timeline (decision 216, the PI, 2026-09-20):
what was recorded, when, on which contact, by which route, at what calibrated band power -- and it
never depends on a pain report.

Measured on RCS08 before this change (`_tl_profile.py`): the fresh build took 5.0 s, of which the
per-report matching was 0.6 s; the cost the page paid was the KEY -- the result was memoised per
worker process under the pain-report digest, so every new report rebuilt it on every worker.
Now:
  * the payload holds no pain series, no per-report matched values (`pro_lsb`) and no
    rating-centred sample index; it is keyed on the recording set, the calibration constants and a
    rule version, stored in the one store as a raw kind, and fronted by the per-worker memo;
  * the rating-centred sample index the Binarization card reads has its own small endpoint,
    keyed on the recording set and the report digest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers import bravo_service as bs  # noqa: E402
from Biomarkers.routines import analytics  # noqa: E402
from CacheStore import provenance  # noqa: E402

ACQ_KEYS = {"records", "stim", "freq_bands", "span", "samples", "lsb_overview", "events", "montage_events"}
PAIN_KEYS = {"pain", "psd_scan_index"}


def test_the_timeline_key_carries_the_recording_set_the_constants_and_a_rule_version_and_no_report():
    k1 = bs._acquisition_timeline_key(("P", 1, 1, "hash one"))
    k2 = bs._acquisition_timeline_key(("P", 1, 2, "hash two"))
    assert k1 != k2
    flat = " ".join(str(x) for x in k1)
    assert bs._ACQ_TIMELINE_RULE_VERSION in flat
    assert str(float(analytics.LSB_PER_UV2_TRANSFORM)) in flat and str(float(analytics.LSB_PER_DEVICE_PSD)) in flat
    old = analytics.LSB_PER_UV2_TRANSFORM
    try:
        analytics.LSB_PER_UV2_TRANSFORM = 999.0
        assert bs._acquisition_timeline_key(("P", 1, 1, "hash one")) != k1
    finally:
        analytics.LSB_PER_UV2_TRANSFORM = old
    # nothing about a pain report can enter it: the helper takes the recording set and nothing else
    import inspect
    assert list(inspect.signature(bs._acquisition_timeline_key).parameters) == ["recording_set"]


def test_the_acquisition_timeline_is_a_raw_kind_in_the_one_store():
    assert "acquisition_timeline" in provenance.RAW_KINDS
    assert bs._ACQ_TIMELINE_KIND == "acquisition_timeline"


def test_the_availability_build_carries_no_pain_field_and_the_compute_response_no_availability_block():
    """The PI, 2026-09-21 (decision 226): the Compute response used to carry the whole timeline
    payload again (2.7 s of 11-14 s, about 7 MB on RCS08) as a fallback for the two dedicated
    endpoints; it no longer does, and the builder has no report-dependent path left."""
    import inspect
    acq = bs._build_availability("NO-SUCH-PARTICIPANT", chronic_list=[], powerdomain_list=[], td_list=[],
                                 region_map={}, psd_list=[])
    assert set(acq) >= ACQ_KEYS and not (set(acq) & PAIN_KEYS), sorted(acq)
    params = set(inspect.signature(bs._build_availability).parameters)
    assert not (params & {"pro_df", "label_metric", "acquisition_only", "warm"}), sorted(params)
    src = inspect.getsource(bs.run_for_participant)
    assert "_build_availability" not in src and '"availability"' not in src


def test_the_timeline_endpoint_reads_no_pain_report_and_takes_no_matching_tolerance():
    import inspect
    src = inspect.getsource(bs.availability_for_participant)
    for name in ("_load_pros", "_native_lsb_tolerance_param", "_pro_table_digest", "_resolve_biomarker_metric", "pro_lsb"):
        assert name not in src, name
    assert "_acquisition_timeline_key" in src
    # the key decides: read by the key, build and write only on a miss, never write a failed build
    assert "_cache_store.load(_ACQ_TIMELINE_KIND" in src and "_cache_store.store(_ACQ_TIMELINE_KIND" in src
    assert 'payload.get("failed")' in src


def test_the_sample_index_has_its_own_endpoint_keyed_on_the_report_digest():
    import inspect
    assert callable(bs.psd_scan_index_for_participant)
    src = inspect.getsource(bs.psd_scan_index_for_participant)
    assert "_pro_table_digest" in src and "_rating_centred_scan_index" in src


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); passed += 1; print(f"PASS {fn.__name__}")
        except Exception:                                  # noqa: BLE001
            print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")


def test_the_per_report_band_power_value_is_built_nowhere():
    """Backend review (the PI, 2026-09-21). The Compute response used to carry, inside its
    `availability` block, one band-power value per pain report per channel (`pro_lsb`: 30 channels,
    18,330 points, 2.5 MB, 0.35 s on RCS08) chosen at a match window the request could not set
    (`_native_lsb_tolerance_param` substituted the page's window, 60 min by default). No page read
    it under any fallback, so the helper, the parameter and the response field are gone."""
    import inspect
    assert not hasattr(bs, "_pro_lsb_by_channel")
    assert not hasattr(bs, "_native_lsb_tolerance_param")
    src = inspect.getsource(bs._build_availability)
    assert "pro_lsb" not in src and "native_lsb_tolerance_s" not in src
    full = bs._build_availability("NO-SUCH-PARTICIPANT", chronic_list=[], powerdomain_list=[], td_list=[],
                                  region_map={}, psd_list=[])
    assert "pro_lsb" not in full
    assert "native_lsb_tolerance_s" not in inspect.getsource(bs.run_for_participant)
