"""Synthetic clock fixtures with hand-derived UTC expectations; no private data."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import unittest


_SPEC = importlib.util.spec_from_file_location(
    "percept_clock_under_test", Path(__file__).resolve().parents[1] / "modules" / "PerceptClock.py"
)
clock = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(clock)
T = 1577836800.0  # 2020-01-01T00:00:00Z, independent calendar reference.


def anchor(counter, seconds, phase="Final", block=7):
    return {"phase": phase, "block": block, "counter": counter, "utc": T + seconds}


def source(uid="a", anchors=None, starts=None, device="device-a"):
    return {"uid": uid, "device": device,
            "index": {"version": clock.VERSION, "anchors": anchors or [], "starts": starts or []}}


def spectrum(counter=200, block=7, **extra):
    return {"DateTimeBlockId": block, "DateTimeOffsetInSeconds": counter,
            "Frequency": [10, 20], "FFTBinData": [1.5, 2.5],
            "DateTime": "2020-01-01T03:00:00Z", **extra}


def record(uid="r1", source_uid="a", metadata=None, **extra):
    return {"uid": uid, "source_uid": source_uid,
            "metadata": {"Left": spectrum()} if metadata is None else metadata,
            "name": "Event", "alignment": 0, **extra}


def two_sources():
    return [source("a", [anchor(100, 100)]), source("b", [anchor(300, 320)])]


def advance_float(value, direction, steps):
    for _ in range(steps):
        value = math.nextafter(value, direction)
    return value


class ScalarClockTests(unittest.TestCase):
    def test_number_rejects_boolean_nonfinite_and_non_numeric(self):
        for value in [True, False, None, "nan", float("inf"), -float("inf"), "oops", {}, []]:
            with self.subTest(value=value):
                self.assertIsNone(clock.number(value))
        self.assertEqual(clock.number("1.25"), 1.25)
        self.assertEqual(clock.number(-3), -3.0)

    def test_utc_requires_timezone_and_valid_era(self):
        for value in [None, 1577836800, "not-a-date", "2020-01-01", "2020-01-01T00:00:00",
                      "0001-01-01T00:00:00Z", "2014-12-31T23:59:59Z"]:
            with self.subTest(value=value):
                self.assertIsNone(clock.utc(value))
        self.assertEqual(clock.utc("2020-01-01T00:00:00Z"), T)
        self.assertEqual(clock.utc("2020-01-01T02:00:00+02:00"), T)
        self.assertEqual(clock.utc("2015-01-01T00:00:00+00:00"), 1420070400)

    def test_coordinate_accepts_zero_counter_but_not_placeholder_block(self):
        self.assertEqual(clock.coordinate("7", "0"), (7, 0.0))
        self.assertEqual(clock.coordinate(7, 1.25), (7, 1.25))
        for block, counter in [(None, 1), (7, None), (0, 1), (-1, 1), (1.5, 1),
                               (7, -1), (True, 1), (7, "nan")]:
            with self.subTest(block=block, counter=counter):
                self.assertIsNone(clock.coordinate(block, counter))


class SourceExtractionTests(unittest.TestCase):
    def payload(self):
        return {"SessionDate": "2020-01-01T00:01:40Z", "SessionEndDate": "2020-01-01T00:05:20Z",
                "DeviceInformation": {
                    "Initial": {"DeviceDateTimeBlockId": 7, "DeviceDateTimeOffsetInSeconds": 100,
                                "DeviceDateTime": "2020-01-01T03:00:00Z"},
                    "Final": {"DeviceDateTimeBlockId": 7, "DeviceDateTimeOffsetInSeconds": 300,
                              "DeviceDateTime": "2020-01-01T03:03:20Z"}}}

    def test_both_anchors_come_from_programmer_not_ins_wall_time(self):
        raw = self.payload()
        before = copy.deepcopy(raw)
        got = clock.extract_source(raw)
        self.assertEqual([(a["phase"], a["counter"], a["utc"]) for a in got["anchors"]],
                         [("Initial", 100, T + 100), ("Final", 300, T + 320)])
        self.assertEqual(got["anchors"][0]["ins_utc"], T + 10800)
        self.assertEqual(raw, before)

    def test_nested_starts_deduplicate_coordinates_without_editing_raw(self):
        packet = {"FirstPacketDateTime": "2020-01-01T03:00:00Z", "FirstPacketDateTimeBlockId": 7,
                  "FirstPacketDateTimeOffsetInSeconds": 200, "Samples": [1, 2]}
        payload = {"nested": [packet, {"deeper": copy.deepcopy(packet)}, 42,
                              {**packet, "FirstPacketDateTimeBlockId": 0}]}
        before = copy.deepcopy(payload)
        self.assertEqual(clock.extract_source(payload)["starts"],
                         [{"raw": T + 10800, "block": 7, "counter": 200}])
        self.assertEqual(payload, before)

    def test_contradictory_session_bounds_reject_both_anchors(self):
        for end in ["2020-01-01T00:00:00Z", "2020-01-01T08:01:40Z"]:
            payload = self.payload()
            payload["SessionEndDate"] = end
            self.assertEqual(clock.extract_source(payload)["anchors"], [])

    def test_partial_or_invalid_source_structure(self):
        for payload in [None, [], {}, {"DeviceInformation": []},
                        {"DeviceInformation": {"Initial": [], "Final": {}}}]:
            self.assertEqual(clock.extract_source(payload)["anchors"], [])
        payload = self.payload()
        del payload["SessionEndDate"]
        self.assertEqual([a["phase"] for a in clock.extract_source(payload)["anchors"]], ["Initial"])
        payload = self.payload()
        payload["DeviceInformation"]["Final"]["DeviceDateTime"] = "0001-01-01T00:00:00Z"
        payload["DeviceInformation"]["Initial"]["DeviceDateTimeBlockId"] = 0
        self.assertEqual(clock.extract_source(payload)["anchors"], [])

    def test_spectrum_validity_checks_both_arrays(self):
        self.assertTrue(clock.valid_spectrum(spectrum()))
        self.assertTrue(clock.valid_spectrum({"Frequency": (10,), "FFTBinData": (2,)}))
        for value in [None, [], {}, {"Frequency": [], "FFTBinData": []},
                      {"Frequency": [1], "FFTBinData": [1, 2]},
                      {"Frequency": [1], "FFTBinData": "2"},
                      {"Frequency": [True], "FFTBinData": [1]},
                      {"Frequency": [1], "FFTBinData": [False]},
                      {"Frequency": [1], "FFTBinData": ["not-numeric"]},
                      {"Frequency": [1], "FFTBinData": [None]}]:
            with self.subTest(value=value):
                self.assertFalse(clock.valid_spectrum(value))

    def test_nonfinite_and_nonpositive_bins_are_left_for_downstream_qc(self):
        # Four ordinary positive bins remain usable after per-bin QC. A clock
        # index must not discard this entire physical PSD or remove its bad bins.
        block = spectrum(Frequency=[1, 2, 3, 4, 5, 6, float("inf")],
                         FFTBinData=[1, 2, 3, 4, float("nan"), 0, -float("inf")])
        self.assertTrue(clock.valid_spectrum(block))
        self.assertTrue(clock.valid_spectrum({"Frequency": ["1", "nan"],
                                             "FFTBinData": ["2.5", "-inf"]}))
        self.assertIsNone(clock.number(float("nan")))  # Clock coordinates remain strict.
        self.assertIsNone(clock.number(float("inf")))

    def test_event_extraction_keeps_nonfinite_raw_bins(self):
        block = spectrum(Frequency=[1, 2, 3, 4, 5], FFTBinData=[1, 2, 3, 4, float("nan")])
        payload = {"DiagnosticData": {"LfpFrequencySnapshotEvents": [
            {"DateTime": "2020-01-01T03:00:00Z", "LfpFrequencySnapshotEvents": {"Left": block}}]}}
        before = json.dumps(payload, sort_keys=True)
        got = clock.extract_event_recordings(payload)
        self.assertEqual(len(got), 1)
        self.assertEqual(json.dumps(got[0]["metadata"]["Left"], sort_keys=True),
                         json.dumps(block, sort_keys=True))
        self.assertEqual(json.dumps(payload, sort_keys=True), before)

    def test_event_extraction_preserves_raw_spectrum_and_copies_metadata(self):
        raw_spectrum = spectrum()
        payload = {"DiagnosticData": {"LfpFrequencySnapshotEvents": [None,
            {"DateTime": "bad", "LfpFrequencySnapshotEvents": {"Left": raw_spectrum}},
            {"DateTime": "2020-01-01T03:00:00Z", "LfpFrequencySnapshotEvents": []},
            {"DateTime": "2020-01-01T03:00:00Z", "LfpFrequencySnapshotEvents": {"junk": {}}},
            {"DateTime": "2020-01-01T03:00:00Z", "EventName": "Pain",
             "LfpFrequencySnapshotEvents": {"Left": raw_spectrum, "junk": {}}},
            {"DateTime": "2020-01-01T03:00:00Z", "LfpFrequencySnapshotEvents": {"Right": raw_spectrum}}]}}
        before = copy.deepcopy(payload)
        got = clock.extract_event_recordings(payload)
        self.assertEqual([r["name"] for r in got], ["Pain", "Event"])
        self.assertEqual(got[0]["date"], T + 10800)
        self.assertEqual(set(got[0]["metadata"]), {"Left"})
        self.assertEqual(payload, before)
        got[0]["metadata"]["Left"]["FFTBinData"][0] = 999
        self.assertEqual(raw_spectrum["FFTBinData"], [1.5, 2.5])

    def test_event_extraction_invalid_containers(self):
        for payload in [None, {}, {"DiagnosticData": []},
                        {"DiagnosticData": {"LfpFrequencySnapshotEvents": {}}}]:
            self.assertEqual(clock.extract_event_recordings(payload), [])


class ClockMappingTests(unittest.TestCase):
    def test_interpolation_uses_elapsed_counter_fraction(self):
        # Counter halfway from 100 to 300; UTC spans 220 seconds, so +110 from first.
        index = clock.build_index(two_sources())
        got = clock.recover(index, "device-a", 7, 200)
        self.assertEqual(got["t"], T + 210)
        self.assertEqual(got["status"], "interpolated")
        self.assertEqual(got["anchor_span_seconds"], 200)
        self.assertEqual(got["intercept_change_seconds"], 20)
        self.assertEqual(got["anchor_sources"], ["a", "b"])
        self.assertEqual(clock.recover(index, "device-a", 7, 150)["t"], T + 155)

    def test_exact_anchors_and_no_extrapolation(self):
        index = clock.build_index(two_sources())
        for counter, utc in [(100, T + 100), (300, T + 320)]:
            got = clock.recover(index, "device-a", 7, counter)
            self.assertEqual((got["status"], got["t"]), ("anchored", utc))
        for counter in [99, 301]:
            got = clock.recover(index, "device-a", 7, counter)
            self.assertEqual(got["status"], "outside_observed_clock_range")
            self.assertIsNone(got["t"])

    def test_final_preferred_per_source_initial_only_fallback(self):
        index = clock.build_index([source("a", [anchor(100, 100, "Initial"), anchor(120, 120)]),
                                   source("b", [anchor(300, 300, "Initial")])])
        self.assertEqual([a["counter"] for a in index["groups"][("device-a", 7)]], [120, 300])
        self.assertEqual(clock.recover(index, "device-a", 7, 100)["status"], "outside_observed_clock_range")
        self.assertEqual(clock.recover(index, "device-a", 7, 200)["t"], T + 200)

    def test_initial_final_counter_reset_invalidates_even_discarded_initial(self):
        index = clock.build_index([source("a", [anchor(200, 100, "Initial"), anchor(100, 120)]),
                                   source("b", [anchor(300, 320)])])
        got = clock.recover(index, "device-a", 7, 200)
        self.assertEqual(got["status"], "nonmonotonic_clock_block")
        self.assertIsNone(got["t"])

    def test_reused_counter_at_distinct_utc_is_ambiguous(self):
        index = clock.build_index([source("a", [anchor(100, 100)]), source("b", [anchor(100, 110)])])
        self.assertEqual(clock.recover(index, "device-a", 7, 100)["status"], "nonmonotonic_clock_block")

    def test_initial_reused_counter_invalidates_monotonic_finals(self):
        # Both Finals increase normally, but two Initial observations claim the
        # same device coordinate at different programmer times. No unique map.
        sources = [source("a", [anchor(100, 100, "Initial"), anchor(100, 100)]),
                   source("b", [anchor(100, 110, "Initial"), anchor(300, 320)])]
        got = clock.recover(clock.build_index(sources), "device-a", 7, 200)
        self.assertEqual(got["status"], "nonmonotonic_clock_block")
        self.assertIsNone(got["t"])

    def test_duplicate_anchors_are_stable_under_source_order(self):
        sources = [source("z", [anchor(100, 100)]), source("a", [anchor(100, 100)])]
        self.assertEqual(clock.build_index(sources), clock.build_index(list(reversed(sources))))
        got = clock.recover(clock.build_index(sources), "device-a", 7, 100)
        self.assertEqual(got["anchor_sources"], ["a"])

    def test_120_second_discontinuity_boundary(self):
        for delta, status in [(120, "interpolated"), (120.01, "clock_anchor_discontinuity"),
                              (-120, "interpolated"), (-120.01, "clock_anchor_discontinuity")]:
            with self.subTest(delta=delta):
                index = clock.build_index([source("a", [anchor(100, 100)]),
                                           source("b", [anchor(300, 300 + delta)])])
                got = clock.recover(index, "device-a", 7, 200)
                self.assertEqual(got["status"], status)
                if status == "interpolated":
                    self.assertEqual(got["t"], T + 200 + delta / 2)
                else:
                    self.assertIsNone(got["t"])

    def test_device_block_isolation_and_missing_coordinates(self):
        index = clock.build_index(two_sources())
        for device, block, counter in [(None, 7, 200), ("device-a", 0, 200), ("device-a", 7, None)]:
            self.assertEqual(clock.recover(index, device, block, counter)["status"], "missing_clock_coordinates")
        for device, block in [("different-device", 7), ("device-a", 8)]:
            self.assertEqual(clock.recover(index, device, block, 200)["status"], "missing_programmer_anchor")

    def test_invalid_source_and_anchor_entries_cannot_supply_clock(self):
        sources = [{}, source(device=None), {"device": "device-a", "index": []},
                   {"device": "device-a", "index": {"version": "obsolete"}},
                   source(anchors=[None, {}, anchor(0, 100, block=0), anchor(100, -T),
                                   anchor(100, 100, phase="unknown"), {**anchor(100, 100), "utc": None}])]
        self.assertEqual(clock.build_index(sources), {"groups": {}, "invalid": set()})

    def test_recover_start_uses_exact_source_coordinates_not_wall_offset(self):
        sources = two_sources()
        sources[0]["index"]["starts"] = [{"raw": T + 10800, "block": 7, "counter": 200},
                                             {"raw": T + 10800, "block": 7, "counter": 200}]
        got = clock.recover_start(clock.build_index(sources), sources[0], T + 10800.0005)
        self.assertEqual((got["t"], got["block"], got["counter"]), (T + 210, 7, 200))
        self.assertEqual(clock.recover_start(clock.build_index(sources), sources[0], T + 10800.002)["status"],
                         "missing_start_coordinates")
        self.assertEqual(clock.recover_start(clock.build_index(sources), {}, T)["status"], "missing_start_coordinates")
        sources[0]["index"]["starts"].append({"raw": T + 10800, "block": 8, "counter": 200})
        self.assertEqual(clock.recover_start(clock.build_index(sources), sources[0], T + 10800)["status"],
                         "conflicting_start_coordinates")


class NativeStartAliasTests(unittest.TestCase):
    kind = "MedtronicBrainSenseTimeDomain"

    def fixture(self, offset=.375):
        sources = two_sources()
        entry = {"decoded_raw": T+10800+offset, "original_raw": T+10800,
                 "block": 7, "counter": 200, "sample_start_offset_seconds": offset,
                 "recording_type": self.kind, "source_kind": "BrainSenseTimeDomain"}
        sources[0]["index"]["decoded_start_aliases"] = [entry]
        return sources, entry

    def test_sample_offset_is_added_after_counter_interpolation(self):
        sources, entry = self.fixture()
        got = clock.recover_start(clock.build_index(sources), sources[0], entry["decoded_raw"], self.kind)
        self.assertEqual(got["base_utc"], T+210)
        self.assertEqual(got["t"], T+210.375)
        self.assertEqual(got["sample_start_offset_seconds"], .375)
        self.assertEqual(got["source_kinds"], ["BrainSenseTimeDomain"])
        self.assertEqual(clock.recover_start(clock.build_index(sources), sources[0], entry["decoded_raw"],
                                            "NeuralActivitySnapshot")["t"], T+210.375)

    def test_typed_stream_never_uses_raw_or_nearby_alias(self):
        sources, entry = self.fixture()
        sources[0]["index"]["starts"] = [{"raw": T+10800, "block":7, "counter":200}]
        for stamp, kind in [(T+10800, self.kind), (entry["decoded_raw"]+.01, self.kind),
                            (entry["decoded_raw"], "MedtronicBrainSensePowerDomain")]:
            self.assertEqual(clock.recover_start(clock.build_index(sources), sources[0], stamp, kind)["status"],
                             "missing_start_coordinates")
        entry["counter"] = 1000
        self.assertIsNone(clock.recover_start(clock.build_index(sources), sources[0], entry["decoded_raw"], self.kind)["t"])

    def test_ambiguous_derived_snapshot_fails(self):
        sources, entry = self.fixture()
        sources[0]["index"]["starts"] = [{"raw":entry["decoded_raw"], "block":7, "counter":200}]
        self.assertEqual(clock.recover_start(clock.build_index(sources), sources[0], entry["decoded_raw"],
                                            "NeuralActivitySnapshot")["status"], "conflicting_start_coordinates")

    def test_malformed_aliases_and_stale_indices_are_explicit(self):
        for changes in [{"decoded_raw":None}, {"decoded_raw":1}, {"original_raw":None},
                        {"original_raw":1}, {"sample_start_offset_seconds":float('nan')},
                        {"block":0}, {"source_kind":None}, {"source_kind":""},
                        {"sample_start_offset_seconds":8}]:
            sources, entry = self.fixture(); stamp=entry["decoded_raw"]; entry.update(changes)
            self.assertEqual(clock.recover_start(clock.build_index(sources), sources[0], stamp, self.kind)["status"],
                             "invalid_start_alias", changes)
        for data, expected in [([], "missing_start_coordinates"), ([1], "missing_start_coordinates"),
                               ({"version":"old"}, "stale_clock_index"),
                               ({"version":clock.VERSION,"decoded_start_aliases":{}}, "invalid_start_alias")]:
            self.assertEqual(clock.recover_start({}, {"index":data}, T, self.kind)["status"], expected)
        for stamp in [None,1,float('inf')]:
            self.assertEqual(clock.recover_start({}, {}, stamp, self.kind)["status"], "invalid_start_time")
        sources, entry = self.fixture()
        sources[0]["index"]["decoded_start_aliases"][:0]=[None, {}, {"recording_type":"unknown"}]
        self.assertEqual(clock.recover_start(clock.build_index(sources), sources[0], entry["decoded_raw"], self.kind)["t"], T+210.375)

    def test_invalid_raw_coordinates_and_out_of_era_corrected_time(self):
        sources=two_sources(); data=sources[0]["index"]
        for starts in [{}, [{"raw":T,"block":0,"counter":200}]]:
            data["starts"]=starts
            self.assertEqual(clock.recover_start(clock.build_index(sources),sources[0],T)["status"], "invalid_start_coordinates")
        data["starts"]=[None,{}, {"raw":T,"block":7,"counter":200}]
        self.assertEqual(clock.recover_start(clock.build_index(sources),sources[0],T)["t"],T+210)
        sources, entry=self.fixture(offset=-1e9)
        entry["original_raw"]=T+2e9;entry["decoded_raw"]=T+1e9
        self.assertEqual(clock.recover_start(clock.build_index(sources),sources[0],entry["decoded_raw"],self.kind)["status"],"invalid_start_alias")


class SpectralEquivalenceTests(unittest.TestCase):
    def test_reported_one_ulp_roundtrip_is_equivalent_without_mutation(self):
        left = spectrum(FFTBinData=[3.6904201006916604, 2.5])
        right = spectrum(FFTBinData=[3.690420100691661, 2.5])
        before = copy.deepcopy((left, right))
        self.assertTrue(clock.spectra_equivalent(left, right))
        self.assertTrue(clock.spectra_equivalent(right, left))
        self.assertEqual((left, right), before)

    def test_four_steps_allowed_five_rejected_at_multiple_exponents(self):
        for value in [1e-12, 1.0, 1e12, -1.0, -1e12]:
            for direction in [-math.inf, math.inf]:
                with self.subTest(value=value, direction=direction):
                    left = spectrum(FFTBinData=[value, 2.5])
                    four = spectrum(FFTBinData=[advance_float(value, direction, 4), 2.5])
                    five = spectrum(FFTBinData=[advance_float(value, direction, 5), 2.5])
                    self.assertTrue(clock.spectra_equivalent(left, four))
                    self.assertFalse(clock.spectra_equivalent(left, five))

    def test_zero_and_exponent_boundaries_count_exact_representable_steps(self):
        # Three predecessors below 1 plus two successors above it are five
        # steps, despite the change in ULP size at 1.0.
        below = advance_float(1.0, -math.inf, 3)
        above = advance_float(1.0, math.inf, 2)
        self.assertFalse(clock.spectra_equivalent(spectrum(FFTBinData=[below, 2]),
                                                spectrum(FFTBinData=[above, 2])))
        tiny = math.ulp(0.0)
        self.assertTrue(clock.spectra_equivalent(spectrum(FFTBinData=[-2 * tiny, 2]),
                                               spectrum(FFTBinData=[2 * tiny, 2])))
        self.assertFalse(clock.spectra_equivalent(spectrum(FFTBinData=[-2 * tiny, 2]),
                                                spectrum(FFTBinData=[3 * tiny, 2])))
        self.assertTrue(clock.spectra_equivalent(spectrum(FFTBinData=[-0.0, 2]),
                                               spectrum(FFTBinData=[0.0, 2])))

    def test_meaningful_relative_changes_are_not_equivalent(self):
        for value in [1e-12, 3.6904201006916604, 1e12]:
            self.assertFalse(clock.spectra_equivalent(spectrum(FFTBinData=[value, 2]),
                                                    spectrum(FFTBinData=[value * (1 + 1e-9), 2])))
        self.assertFalse(clock.spectra_equivalent(spectrum(Frequency=[10, 20]),
                                                spectrum(Frequency=[10, 20.00000002])))

    def test_nonfinite_matching_and_invalid_arrays(self):
        for left, right, expected in [(float("nan"), float("nan"), True),
                                      (math.inf, math.inf, True), (-math.inf, -math.inf, True),
                                      (math.inf, -math.inf, False), (math.inf, 1, False),
                                      (1, math.inf, False), (float("nan"), 1, False),
                                      (1, float("nan"), False)]:
            self.assertEqual(clock.spectra_equivalent(spectrum(FFTBinData=[left, 2]),
                                                     spectrum(FFTBinData=[right, 2])), expected)
        for left, right in [({}, spectrum()), (spectrum(), {}),
                            (spectrum(), spectrum(Frequency=[10], FFTBinData=[1.5]))]:
            self.assertFalse(clock.spectra_equivalent(left, right))


class PhysicalSnapshotTests(unittest.TestCase):
    def test_nonfinite_snapshot_identity_and_dedup_are_deterministic(self):
        block = spectrum(Frequency=[1, 2, 3, 4, float("inf")],
                         FFTBinData=[1, 2, 3, 4, float("nan")])
        other = json.loads(json.dumps(block))  # Independently parsed NaN objects.
        other["DateTime"] = "2020-01-02T09:00:00Z"
        identity = clock.snapshot_identity("device-a", "Left", block)
        self.assertIsNotNone(identity)
        self.assertEqual(identity, clock.snapshot_identity("device-a", "Left", other))
        records = [record(metadata={"Left": block}), record("r2", "b", metadata={"Left": other})]
        before = json.dumps(records, sort_keys=True)
        rows, counts = clock.canonical_snapshots(records, two_sources())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["t"], T + 210)
        self.assertEqual(counts["duplicate_export_copies"], 1)
        self.assertEqual(len(rows[0]["spectrum"]["FFTBinData"]), 5)
        self.assertEqual(json.dumps(records, sort_keys=True), before)

    def test_identity_uses_device_side_coordinates_not_payload_or_wall_time(self):
        original = spectrum()
        identity = clock.snapshot_identity("device-a", "Left", original)
        self.assertEqual(identity, clock.snapshot_identity("device-a", "Left",
                         {**original, "DateTime": "2020-01-02T00:00:00Z", "EventName": "renamed"}))
        for device, side, block in [("device-b", "Left", original), ("device-a", "Right", original),
                                    ("device-a", "Left", spectrum(counter=201))]:
            self.assertNotEqual(identity, clock.snapshot_identity(device, side, block))
        self.assertEqual(identity, clock.snapshot_identity("device-a", "Left", spectrum(FFTBinData=[1.5, 2.6])))
        for device, block in [(None, original), ("device-a", {}), ("device-a", spectrum(block=0))]:
            self.assertIsNone(clock.snapshot_identity(device, "Left", block))

    def test_material_same_coordinate_payload_difference_is_explicit_conflict(self):
        records = [record(), record("r2", metadata={"Left": spectrum(FFTBinData=[1.5, 2.6])})]
        before = copy.deepcopy(records)
        with self.assertRaisesRegex(ValueError, "conflicting spectral payloads"):
            clock.canonical_snapshots(records, two_sources())
        self.assertEqual(records, before)

    def test_roundtrip_equivalent_copies_deduplicate_and_retain_original_values(self):
        raw = spectrum(FFTBinData=[3.6904201006916604, 2.5])
        stored = spectrum(FFTBinData=[3.690420100691661, 2.5])
        records = [record("a", metadata={"Left": raw}), record("b", metadata={"Left": stored})]
        before = copy.deepcopy(records)
        rows, counts = clock.canonical_snapshots(records, two_sources())
        self.assertEqual(len(rows), 1)
        self.assertEqual(counts["duplicate_export_copies"], 1)
        self.assertEqual(rows[0]["spectrum"]["FFTBinData"][0], 3.6904201006916604)
        self.assertEqual(records, before)

    def test_every_pair_checked_not_a_nontransitive_representative(self):
        # The lexically selected midpoint is within four steps of both ends;
        # the ends are eight steps apart and must not silently become one PSD.
        records = [record("a", metadata={"Left": spectrum(FFTBinData=[advance_float(1, math.inf, 4), 2])}),
                   record("b", metadata={"Left": spectrum(FFTBinData=[1, 2])}),
                   record("c", metadata={"Left": spectrum(FFTBinData=[advance_float(1, math.inf, 8), 2])})]
        for order in [records, list(reversed(records)), records[1:] + records[:1]]:
            with self.assertRaisesRegex(ValueError, "conflicting spectral payloads"):
                clock.canonical_snapshots(order, two_sources())

    def test_dedup_maps_once_and_applies_manual_shift_once_raw_unchanged(self):
        sources = two_sources()
        records = [record("z", "a", name="Streaming", alignment=30),
                   record("a", "b", metadata={"Left": spectrum(DateTime="2020-01-02T09:00:00Z", SenseID="L13")},
                          name="Pain", alignment=30)]
        before = copy.deepcopy((sources, records))
        rows, counts = clock.canonical_snapshots(records, sources)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["t"], T + 240)  # Interpolated +210, then exactly one +30 shift.
        self.assertEqual(rows[0]["name"], "Pain")
        self.assertEqual(rows[0]["names"], ["Pain", "Streaming"])
        self.assertEqual(rows[0]["sense_id"], "L13")
        self.assertEqual(rows[0]["provenance"]["source_uids"], ["a", "b"])
        self.assertEqual(rows[0]["provenance"]["manual_alignment_seconds"], 30)
        self.assertEqual(counts["physical_psds"], 1)
        self.assertEqual(counts["duplicate_export_copies"], 1)
        self.assertEqual(counts["exported_psd_copies"], 2)
        self.assertEqual(counts["interpolated"], 1)
        self.assertEqual((sources, records), before)
        self.assertEqual(clock.canonical_snapshots(list(reversed(records)), list(reversed(sources))), (rows, counts))

    def test_streaming_only_and_missing_names_remain_defined(self):
        sources = two_sources()
        for name, expected in [("Streaming", "Streaming"), (None, "Event")]:
            rows, _ = clock.canonical_snapshots([record(name=name)], sources)
            self.assertEqual(rows[0]["name"], expected)
            self.assertIsNone(rows[0]["sense_id"])

    def test_manual_shift_conflicts_and_invalid_shifts_fail_closed(self):
        for shift in [1, None, "nan", True]:
            with self.subTest(shift=shift):
                with self.assertRaisesRegex(ValueError, "conflicting alignment or sensing metadata"):
                    clock.canonical_snapshots([record(), record("r2", alignment=shift)], two_sources())

    def test_explicit_sense_conflict_fails_closed(self):
        records = [record(metadata={"Left": spectrum(SenseID="L13")}),
                   record("r2", metadata={"Left": spectrum(SenseID="L02")})]
        with self.assertRaisesRegex(ValueError, "conflicting alignment or sensing metadata"):
            clock.canonical_snapshots(records, two_sources())

    def test_bad_metadata_missing_identity_and_unresolved_clock_are_counted(self):
        records = [{**record(), "metadata": None}, record("invalid", metadata={"Left": {}}),
                   record("missing", source_uid="absent"),
                   record("block-zero", metadata={"Left": spectrum(block=0)}),
                   record("unobserved", metadata={"Left": spectrum(counter=400)})]
        rows, counts = clock.canonical_snapshots(records, two_sources())
        self.assertEqual(rows, [])
        self.assertEqual(counts["invalid_metadata"], 1)
        self.assertEqual(counts["missing_clock_coordinates"], 2)
        self.assertEqual(counts["outside_observed_clock_range"], 1)
        self.assertEqual(counts["physical_psds"], 1)
        self.assertEqual(counts["recovered_physical_psds"], 0)

    def test_equal_spectra_on_different_hemispheres_are_distinct_physical_psds(self):
        rows, counts = clock.canonical_snapshots([record(metadata={"Left": spectrum(), "Right": spectrum()})], two_sources())
        self.assertEqual({r["hemisphere"] for r in rows}, {"Left", "Right"})
        self.assertEqual(counts["physical_psds"], 2)
        self.assertEqual(counts["duplicate_export_copies"], 0)


if __name__ == "__main__":
    unittest.main()
