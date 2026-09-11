"""Synthetic clock fixtures with hand-derived UTC expectations; no private data."""
import copy
import importlib.util
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
                      {"Frequency": [1], "FFTBinData": [float("nan")]}]:
            with self.subTest(value=value):
                self.assertFalse(clock.valid_spectrum(value))

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


class PhysicalSnapshotTests(unittest.TestCase):
    def test_identity_ignores_export_wall_time_but_retains_device_side_and_content(self):
        original = spectrum()
        identity = clock.snapshot_identity("device-a", "Left", original)
        self.assertEqual(identity, clock.snapshot_identity("device-a", "Left",
                         {**original, "DateTime": "2020-01-02T00:00:00Z", "EventName": "renamed"}))
        for device, side, block in [("device-b", "Left", original), ("device-a", "Right", original),
                                    ("device-a", "Left", spectrum(counter=201)),
                                    ("device-a", "Left", spectrum(FFTBinData=[1.5, 2.6]))]:
            self.assertNotEqual(identity, clock.snapshot_identity(device, side, block))
        for device, block in [(None, original), ("device-a", {}), ("device-a", spectrum(block=0))]:
            self.assertIsNone(clock.snapshot_identity(device, "Left", block))

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
