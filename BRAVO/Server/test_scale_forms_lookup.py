"""Large survey form lookup sorts identifiers while retaining version semantics."""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from Server import models


class ScaleFormLookupTests(TestCase):
    def test_latest_version_found_without_sorting_large_payload_or_joined_rows(self):
        institute = models.Institute.objects.create(name='Synthetic institute')
        other = models.Institute.objects.create(name='Other institute')
        kwargs = dict(institute=institute, name='Synthetic form', record_type='REDCap API Sync')
        models.ScaleForms.objects.create(**kwargs, record_version=1, record=[{'body':'old'}])
        expected = [{'body':'x'*300000}]
        latest = models.ScaleForms.objects.create(**kwargs, record_version=3, record=expected)
        models.ScaleForms.objects.create(institute=other, name='Synthetic form', record_type='REDCap API Sync', record_version=9)
        models.ScaleForms.objects.create(institute=institute, name='Synthetic form', record_type='different', record_version=10)
        with CaptureQueriesContext(connection) as queries:
            found = models.ScaleForms.find(**kwargs)
            self.assertEqual(found.uid, latest.uid)
            self.assertEqual(found.record, expected)
            self.assertEqual(found.institute.name, institute.name)
        self.assertEqual(len(queries), 2)
        first = queries[0]['sql']
        select_clause = first.split(' FROM ')[0]
        self.assertIn('uid', select_clause)
        self.assertNotIn('record', select_clause)
        self.assertNotIn(' JOIN ', first)
        self.assertIn('record_version', first.split(' ORDER BY ')[1])
        self.assertIn('DESC', first)
        self.assertNotIn('record_version', queries[1]['sql'].split(' ORDER BY ')[-1])

    def test_missing_form_returns_none_with_single_identifier_query(self):
        with CaptureQueriesContext(connection) as queries:
            found = models.ScaleForms.find(name='Missing form')
        self.assertIsNone(found)
        self.assertEqual(len(queries), 1)
        self.assertNotIn('record', queries[0]['sql'].split(' FROM ')[0])
