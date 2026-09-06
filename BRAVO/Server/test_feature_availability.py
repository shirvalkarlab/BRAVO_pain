"""Navigation gates must reflect usable data, not connected-device inventory."""
import unittest
import numpy as np
from modules.FeatureAvailability import build_feature_map, measurement_record_count


class FeatureAvailabilityTests(unittest.TestCase):
    def test_native_methods_remain_available_without_optional_models(self):
        result = build_feature_map({"snapshot": 4}, {"Native beta": True, "Lavu": False, "Wong": False})
        self.assertTrue(result["PredictTherapyParameters"]["available"])
        self.assertFalse(result["AIHealthcare"]["available"])
        self.assertIn("Predict Therapy Parameters", result["AIHealthcare"]["reason"])
        self.assertFalse(result["PredictTherapyParameters"]["models"]["Lavu"])
        self.assertEqual(build_feature_map({"snapshot": 4}, {})["AIHealthcare"]["kind"], "code")

    def test_empty_sensor_does_not_disable_actual_streams(self):
        result = build_feature_map({"oura": 12, "surveys": 5, "chronic": 8}, {})
        self.assertFalse(result["FitbitDashboard"]["available"])
        self.assertEqual(result["FitbitDashboard"]["reason"], "No Fitbit data")
        self.assertTrue(result["FitbitDashboard"]["setup"])
        for key in ("OuraRingDashboard", "FormRecords", "chronic-neural-activity", "multimodal-timeline-report"):
            self.assertTrue(result[key]["available"])

    def test_research_requires_canonical_daily_pros_and_neural(self):
        result = build_feature_map({"surveys": 100, "research_neural": 4, "therapy": 10}, {})
        self.assertFalse(result["biomarkers"]["available"])
        result = build_feature_map({"daily_pros": 12, "research_neural": 4, "therapy": 10}, {})
        for key in ("biomarkers", "closedLoopSim", "stimOptimizer"):
            self.assertTrue(result[key]["available"])
            self.assertEqual(result[key]["kind"], "research")
            self.assertNotIn("count", result[key])
            self.assertEqual(result[key]["inputs"]["daily_surveys"], 12)
        self.assertFalse(build_feature_map({"daily_pros": 12, "research_neural": 4}, {})["stimOptimizer"]["available"])

    def test_unreadable_data_not_misreported_as_absence(self):
        result = build_feature_map({"oura": 0}, {}, {"oura": "Stored data could not be checked"})
        self.assertEqual(result["OuraRingDashboard"]["kind"], "unknown")
        self.assertEqual(result["OuraRingDashboard"]["reason"], "Stored data could not be checked")

    def test_placeholder_missing_and_qc_masked_records_do_not_count_but_zero_does(self):
        rows = [
            {"Metadata": {"NoData": True}, "Data": [[0]]},
            {"Data": [[np.nan]], "Missing": [[0]], "Descriptor": {}},
            {"Data": [[1]], "Missing": [[1]], "Descriptor": {}},
            {"Data": [[0]], "Missing": [[0]]},
            {"Data": [], "Descriptor": {"steps": 0}},
            {"Data": [], "OuraMetadata": {"Score": 75}},
            {"Data": [], "Metadata": {"Score": -1}},
        ]
        self.assertEqual(measurement_record_count({"sensor": rows}), 3)

    def test_no_imaging_or_medication_labels_produces_explicit_disabled_states(self):
        result = build_feature_map({"timeseries": 600}, {})
        self.assertFalse(result["3dImageViewer"]["available"])
        self.assertFalse(result["InClinicMedicationCycle"]["available"])
        self.assertEqual(len(result), 21)
        self.assertFalse(result["redcapTimeline"]["available"])
        self.assertTrue(build_feature_map({"daily_pros": 1}, {})["redcapTimeline"]["available"])
        self.assertFalse(result["ouraFreeReps"]["available"])
        self.assertTrue(build_feature_map({"oura": 1}, {})["ouraFreeReps"]["available"])
