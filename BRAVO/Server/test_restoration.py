"""Regression checks for restored functionality and performance contracts."""
import pytest
import copy
import random
from django.test import SimpleTestCase
from modules.Therapy import groupTherapySettings
from modules.utility.PythonUtility import uniqueListOfDicts, _uniqueListOfDictsByComparison


class TherapyGroupingTests(SimpleTestCase):
    def test_grouping_matches_legacy_order_and_retains_all_settings(self):
        rng = random.Random(19)
        rows = [{"Id": i, "SourceId": rng.choice(["a", "b"]), "Date": rng.choice([1, 2]),
                 "GroupId": rng.choice(["A", "B"]), "Type": rng.choice(["Pre-visit Therapy", "Post-visit Therapy", "Past Therapy", "Other"]),
                 "StimulationSettings": [{"amplitude": i / 10}], "AdaptiveSettings": [{"threshold": i}]}
                for i in range(150)]
        original = copy.deepcopy(rows)
        expected = []
        for source in sorted({r["SourceId"] for r in rows}):
            for date in sorted({r["Date"] for r in rows}):
                for group in sorted({r["GroupId"] for r in rows}):
                    for kind in ["Pre-visit Therapy", "Post-visit Therapy", "Past Therapy"]:
                        matching = [r for r in rows if (r["SourceId"],r["Date"],r["GroupId"],r["Type"]) == (source,date,group,kind)]
                        if matching:
                            result = copy.deepcopy(matching[0])
                            for row in matching[1:]:
                                for field in ["StimulationSettings", "AdaptiveSettings"]:
                                    result[field].extend(row[field])
                            expected.append(result)
        self.assertEqual(groupTherapySettings(rows), expected)
        self.assertEqual(rows, original)
        self.assertEqual(groupTherapySettings([]), [])


class DeduplicationTests(SimpleTestCase):
    def test_scalar_list_and_missing_keys_match_existing_behavior(self):
        rows = [{"a":1,"b":[1,2],"first":True}, {"a":True,"b":[1.0,2]},
                {"a":2,"b":[1,2]}, {"a":2}, {"a":2}, {"a":2,"b":[2,1]},
                {"a":2,"b":(2,1)}, {"a":None,"b":[]}, {"a":None,"b":[]}]
        self.assertEqual(uniqueListOfDicts(rows,["a","b"]), _uniqueListOfDictsByComparison(rows,["a","b"]))
        self.assertIs(uniqueListOfDicts(rows,["a","b"])[0],rows[0])

    def test_nan_is_not_deduplicated_as_a_real_value(self):
        nan=float('nan')
        rows=[{"a":nan},{"a":nan},{"a":0},{"a":0}]
        self.assertEqual(len(uniqueListOfDicts(rows,["a"])),3)


class StoredSurveyTests(SimpleTestCase):
    def test_preserves_zero_missing_values_and_utc_timestamps(self):
        from types import SimpleNamespace
        from modules.DataAnalysis import storedSurveyTimeline
        form = SimpleNamespace(name='Pain', record_type='REDCap API Sync', record=[{'questions':[
            {'type':'score','text':'Score','show':True}, {'type':'text','text':'Notes','show':True}]}])
        rows = [{'Date':1000,'Result':[[0,'ok']]}, {'Date':1060,'Result':[[4]]}, {'Date':1120,'Result':[]}]
        result=storedSurveyTimeline(form, rows)
        self.assertEqual(result['Time'],[1000,1060,1120])
        self.assertEqual(result['Data'],[[0,4,None]])
        self.assertEqual(result['ChannelNames'],['[REDCap] Pain - Score'])


@pytest.mark.usefixtures("synthetic_oura_policy")
class SharedReportCacheTests(SimpleTestCase):
    def setUp(self):
        import tempfile
        from unittest.mock import patch
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for patcher in [patch.dict('os.environ',DATASERVER_PATH=self.directory.name),
                        patch('modules.Database.checkAccessPermission',return_value={'Deidentified':False}),
                        patch('modules.Database.retrieveProcessingSettings',return_value=({},False)),
                        patch('modules.ReportCache.transaction.on_commit',side_effect=lambda f:f())]:
            patcher.start();self.addCleanup(patcher.stop)

    def request(self, encoding='gzip'):
        from types import SimpleNamespace
        return SimpleNamespace(data={'ParticipantId':'test','RequestType':'RequestAll'},path='/test-report',
                               headers={'Accept-Encoding':encoding},user=SimpleNamespace(configuration={}))

    def test_concurrent_readers_share_one_calculation_and_refresh_after_edit(self):
        import time, json, gzip
        from concurrent.futures import ThreadPoolExecutor
        from rest_framework.response import Response
        from modules.ReportCache import cached_report, invalidate
        calls=[]
        @cached_report
        def report(view, request):
            calls.append(1);time.sleep(.08)
            return Response({'values':[0,None,4], 'generation':len(calls)})
        with ThreadPoolExecutor(max_workers=20) as pool:
            results=list(pool.map(lambda _:report(None,self.request()),range(20)))
        self.assertEqual(len(calls),1)
        self.assertEqual(sum(r['X-BRAVO-Report-Cache']=='MISS' for r in results),1)
        for r in results:
            self.assertEqual(json.loads(gzip.decompress(r.content))['values'],[0,None,4])
        invalidate()
        r=report(None,self.request('gzip;q=0'))
        self.assertNotIn('Content-Encoding',r)
        self.assertEqual(json.loads(r.content)['generation'],2)

    def test_revoked_permission_never_reads_cached_result(self):
        from unittest.mock import patch
        from rest_framework.response import Response
        from modules.ReportCache import cached_report
        calls=[]
        @cached_report
        def report(view,request):
            calls.append(1)
            return Response({'test':len(calls)})
        report(None,self.request())
        with patch('modules.Database.checkAccessPermission',return_value=False):
            response=report(None,self.request())
        self.assertEqual(response.data,{'test':2}) # delegated to the view's live permission check
        self.assertEqual(len(calls),2)

    def test_change_during_calculation_is_not_saved_as_fresh(self):
        from rest_framework.response import Response
        from modules.ReportCache import cached_report, invalidate, calculation_revision, revision
        calls=[]
        @cached_report
        def report(view,request):
            before=calculation_revision();invalidate()
            self.assertEqual(calculation_revision(),before)
            self.assertNotEqual(revision(),before)
            calls.append(1)
            return Response({'test':1})
        report(None,self.request());report(None,self.request())
        self.assertEqual(len(calls),2)


class ModelAvailabilityTests(SimpleTestCase):
    def test_missing_assets_are_explicit_not_success_or_name_error(self):
        from modules import DataAnalysis
        from unittest.mock import patch
        with patch.object(DataAnalysis,'ContactPredictor',None):
            name='Survey-based Contact Selection (Lavu et. al., 2025)'
            self.assertNotIn(name,DataAnalysis.extractMachineLearningModels('test'))
            with self.assertRaises(DataAnalysis.ModelUnavailable):
                DataAnalysis.extractMachineLearningModels('test',name,{'RequestType':'RequestAIResult'})


class ReportInvalidationTests(SimpleTestCase):
    def test_raw_recording_edits_invalidate_but_derived_calculations_do_not(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from modules.ReportCache import data_changed
        sender=type('Recording',(),{})
        raw=SimpleNamespace(original_id=None,type='MedtronicBrainSenseSurvey',source=SimpleNamespace(type='MedtronicJSON'))
        derived=SimpleNamespace(original_id='raw-id',type='NeuralActivitySnapshot',source=raw.source)
        with patch('modules.ReportCache.invalidate') as invalidate:
            data_changed(sender,raw);invalidate.assert_called_once()
            invalidate.reset_mock();data_changed(sender,derived);invalidate.assert_not_called()


class SnapshotCacheTests(SimpleTestCase):
    def test_existing_snapshot_does_not_read_raw_recording_again(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from modules.DataAnalysis import processNeuralActivitySnapshot
        recording=SimpleNamespace(pointer='raw',hashed='rawhash')
        processed=SimpleNamespace(pointer='processed',hashed='processedhash')
        value={'PSD':'cached-result'}
        with patch('modules.DataAnalysis.models.Recording.find',return_value=processed), patch('modules.Database.loadSourceFile',return_value=value) as read:
            self.assertIs(processNeuralActivitySnapshot(recording,None,{}),value)
            read.assert_called_once_with('processed','processedhash')

@pytest.mark.usefixtures("synthetic_oura_policy")
class PersistentReportCacheTests(SimpleTestCase):
    setUp = SharedReportCacheTests.setUp
    request = SharedReportCacheTests.request
    def test_unchanged_saved_report_survives_age_and_new_wrapper(self):
        import os, time
        from rest_framework.response import Response
        from modules import ReportCache
        calls=[]
        def compute(view,request):
            calls.append(1)
            return Response({'values':[0,None,7]})
        ReportCache.cached_report(compute)(None,self.request())
        for path in ReportCache.directory().glob('*.gz'):
            os.utime(path,(time.time()-86400*3,time.time()-86400*3))
        response=ReportCache.cached_report(compute)(None,self.request())
        self.assertEqual(response['X-BRAVO-Report-Cache'],'HIT')
        self.assertEqual(len(calls),1)

    def test_last_completed_report_remains_available_during_preparation(self):
        from filelock import FileLock
        from rest_framework.response import Response
        from modules import ReportCache
        calls=[]
        @ReportCache.cached_report
        def report(view,request):
            calls.append(1)
            return Response({'generation':len(calls)})
        report(None,self.request())
        ReportCache.invalidate()
        with FileLock(str(ReportCache.directory()/'preparing.lock')):
            response=report(None,self.request())
            self.assertEqual(response['X-BRAVO-Report-Cache'],'UPDATING')
            self.assertEqual(len(calls),1)
        self.assertEqual(report(None,self.request())['X-BRAVO-Report-Cache'],'MISS')
        self.assertEqual(len(calls),2)

    def test_only_neural_changes_expire_shared_neural_derivation(self):
        from modules import ReportCache
        before=ReportCache.revision('neural-revision')
        ReportCache.invalidate()
        self.assertEqual(ReportCache.revision('neural-revision'),before)
        ReportCache.invalidate(neural=True)
        self.assertNotEqual(ReportCache.revision('neural-revision'),before)
