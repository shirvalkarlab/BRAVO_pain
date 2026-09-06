"""Direct production policy tests for wholly retained and wholly excluded epochs."""
import unittest
import numpy as np
from modules.RCS08DataPolicy import IMPLANT_DAY, filter_decoded_entries


class NeuralPolicyRuntimeTests(unittest.TestCase):
    def test_wholly_preimplant_chronic_record_is_dropped_without_relabeling_it(self):
        entries = {'ChronicRecordings': [{'date': IMPLANT_DAY - 10, 'metadata': {}, 'recording': {
            'Time': np.array([IMPLANT_DAY - 10, IMPLANT_DAY - 1]), 'Data': np.array([[1, 2], [3, 4]])}}]}
        removed = filter_decoded_entries(entries)
        self.assertEqual(removed, {'ChronicSamples': 2})
        self.assertEqual(entries['ChronicRecordings'], [])

    def test_exact_boundary_and_later_chronic_samples_are_unchanged(self):
        times = np.array([IMPLANT_DAY, IMPLANT_DAY + 600])
        values = np.array([[0, 1], [2, 3]])
        item = {'date': IMPLANT_DAY, 'metadata': {'Duration': 600}, 'recording': {
            'Time': times, 'Data': values, 'StartTime': IMPLANT_DAY, 'Duration': 600}}
        entries = {'ChronicRecordings': [item], 'Therapies': [{'date': IMPLANT_DAY}]}
        self.assertEqual(filter_decoded_entries(entries), {})
        self.assertIs(entries['ChronicRecordings'][0], item)
        self.assertIs(item['recording']['Time'], times)
        self.assertIs(item['recording']['Data'], values)
        self.assertEqual(entries['Therapies'], [{'date': IMPLANT_DAY}])
