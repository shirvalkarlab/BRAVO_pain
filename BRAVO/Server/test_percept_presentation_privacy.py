import copy
import json
import unittest
from modules.PerceptPresentationPrivacy import sanitize_patient_identifiers


class PerceptPresentationPrivacyTests(unittest.TestCase):
    def test_removes_identifiers_only_and_preserves_all_scientific_content(self):
        patient={'PatientFirstName':'Synthetic','PatientLastName':'Example','PatientId':'TEST-MRN','PatientDateOfBirth':'2000-01-01','PatientGender':'Unknown'}
        report={'PatientInformation':{'Initial':copy.deepcopy(patient),'Final':copy.deepcopy(patient)},'EventSummary':{'SessionStartDate':'2026-01-01T00:00:00Z'},'BrainSenseTimeDomain':[{'FirstPacketDateTime':'2026-01-01T00:00:00Z','TimeDomainData':[1,2,3]}],'Groups':{'Final':[{'Amplitude':2.0}]}}
        raw=json.dumps(report).encode();clean,changed=sanitize_patient_identifiers(raw)
        parsed=json.loads(clean)
        self.assertEqual(len(changed),8)
        for entry in parsed['PatientInformation'].values():
            self.assertEqual(entry['PatientFirstName'],'')
            self.assertEqual(entry['PatientLastName'],'')
            self.assertEqual(entry['PatientDateOfBirth'],'')
            self.assertEqual(entry['PatientId'],'RCS08')
        expected=copy.deepcopy(report);expected['PatientInformation']=parsed['PatientInformation']
        self.assertEqual(parsed,expected)
        self.assertEqual(json.loads(raw),report)

    def test_existing_masked_report_is_byte_identical(self):
        raw=json.dumps({'PatientInformation':{'Initial':{'PatientFirstName':'███████','PatientId':'RCS08','PatientDateOfBirth':''}}}).encode()
        self.assertEqual(sanitize_patient_identifiers(raw),(raw,[]))

    def test_sanitizing_twice_is_idempotent(self):
        raw=b'{"PatientInformation":{"Final":{"PatientFirstName":"Synthetic"}}}'
        clean,_=sanitize_patient_identifiers(raw)
        self.assertEqual(sanitize_patient_identifiers(clean),(clean,[]))

    def test_unexpected_identifier_structure_fails_closed(self):
        with self.assertRaises(ValueError):
            sanitize_patient_identifiers(b'{"PatientInformation":{"Final":{"PatientFirstName":{"text":"Synthetic"}}}}')
