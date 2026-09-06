"""Synthetic filesystem/thread tests: no database, participant data or network."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


class AnalysisJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'DATASERVER_PATH': self.temporary.name})
        self.environment.start()
        self.modules = []
        self.gates = []
        self.jobs = self.load_worker()

    def load_worker(self):
        path = Path(__file__).resolve().parents[1] / 'modules/AnalysisJobs.py'
        spec = importlib.util.spec_from_file_location('synthetic_analysis_jobs_' + str(len(self.modules)), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.modules.append(module)
        return module

    def tearDown(self):
        for gate in self.gates:
            gate.set()
        for module in self.modules:
            module._EXECUTOR.shutdown(wait=True)
        self.environment.stop()
        self.temporary.cleanup()

    def gate(self):
        event = threading.Event()
        self.gates.append(event)
        return event

    def wait_result(self, identity, compute, module=None, expected=200):
        module = module or self.jobs
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status, payload = module.get_or_start(identity, compute)
            if status == expected:
                return payload
            if status not in (202, expected):
                self.fail(f'Unexpected job status {status}: {payload}')
            time.sleep(.01)
        self.fail('Synthetic job did not finish')

    def test_concurrent_requests_deduplicate_and_return_original_json_payload(self):
        gate, started = self.gate(), self.gate()
        calls = []
        def compute():
            calls.append(1)
            started.set()
            self.assertTrue(gate.wait(3))
            return {'values': [0, None, 5], 'InputManifest': 'synthetic'}
        with ThreadPoolExecutor(max_workers=12) as requests:
            responses = list(requests.map(lambda _: self.jobs.get_or_start({'participant': 'synthetic'}, compute), range(24)))
        self.assertTrue(started.wait(1))
        self.assertEqual(len(calls), 1)
        self.assertEqual({r[0] for r in responses}, {202})
        self.assertEqual(len({r[1]['job_id'] for r in responses}), 1)
        gate.set()
        self.assertEqual(self.wait_result({'participant': 'synthetic'}, compute),
                         {'values': [0, None, 5], 'InputManifest': 'synthetic'})

    def test_result_survives_worker_recreation_and_files_are_private(self):
        identity = {'participant': 'synthetic', 'manifest': 'v1'}
        self.wait_result(identity, lambda: {'result': 7})
        worker = self.load_worker()
        def never():
            raise AssertionError('Persistent result must be reused')
        self.assertEqual(worker.get_or_start(identity, never), (200, {'result': 7}))
        root = Path(self.temporary.name) / 'analysis-jobs'
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        for path in root.glob('*.json'):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertFalse(list(root.glob('*.tmp')))

    def test_failure_is_not_success_does_not_leak_exception_and_retries(self):
        identity = {'endpoint': 'failure'}
        calls = []
        def fail():
            calls.append(1)
            raise ValueError('secret synthetic credential')
        payload = self.wait_result(identity, fail, expected=500)
        self.assertEqual(payload['status'], 'failed')
        self.assertNotIn('secret', json.dumps(payload))
        self.assertEqual(self.jobs.get_or_start(identity, fail)[0], 500)
        self.assertEqual(len(calls), 1)
        self.jobs._FAILURE_RETRY_SECONDS = 0
        self.assertEqual(self.wait_result(identity, lambda: {'recovered': True}), {'recovered': True})

    def test_stale_running_status_without_lock_is_restarted(self):
        identity = {'endpoint': 'restart'}
        canonical = json.dumps(identity, sort_keys=True, allow_nan=False, separators=(',', ':'))
        job_id = hashlib.sha256(canonical.encode()).hexdigest()
        path = self.jobs._directory() / (job_id + '.json')
        self.jobs._write(path, {'status': 'running', 'job_id': job_id})
        self.assertEqual(self.wait_result(identity, lambda: {'restarted': True}), {'restarted': True})

    def test_changed_manifest_and_permission_cannot_share_cached_result(self):
        one = {'participant': 'synthetic', 'manifest': 'v1', 'permission': 'one'}
        two = {**one, 'manifest': 'v2'}
        three = {**one, 'permission': 'two'}
        self.assertEqual(self.wait_result(one, lambda: {'value': 1}), {'value': 1})
        self.assertEqual(self.wait_result(two, lambda: {'value': 2}), {'value': 2})
        self.assertEqual(self.wait_result(three, lambda: {'value': 3}), {'value': 3})

    def test_separate_workers_deduplicate_and_global_lock_serializes_distinct_jobs(self):
        worker = self.load_worker()
        gate, started, second_started = self.gate(), self.gate(), self.gate()
        calls = []
        def first():
            calls.append('first')
            started.set()
            self.assertTrue(gate.wait(3))
            return {'first': True}
        def second():
            calls.append('second')
            second_started.set()
            return {'second': True}
        self.jobs.get_or_start({'job': 1}, first)
        self.assertTrue(started.wait(1))
        self.assertEqual(worker.get_or_start({'job': 1}, second)[0], 202)
        self.assertEqual(worker.get_or_start({'job': 2}, second)[0], 202)
        self.assertFalse(second_started.wait(.1))
        gate.set()
        self.wait_result({'job': 2}, second, module=worker)
        self.assertEqual(calls, ['first', 'second'])

    def test_queue_capacity_is_bounded_and_busy_poll_can_retry_without_lock_leak(self):
        gate, started = self.gate(), self.gate()
        def blocked():
            started.set()
            self.assertTrue(gate.wait(3))
            return {'done': True}
        for index in range(8):
            self.assertEqual(self.jobs.get_or_start({'job': index}, blocked)[0], 202)
        self.assertTrue(started.wait(1))
        response = self.jobs.get_or_start({'job': 9}, lambda: {'retry': True})
        self.assertEqual(response[0], 202)
        self.assertIn('capacity', response[1]['message'])
        gate.set()
        self.assertEqual(self.wait_result({'job': 9}, lambda: {'retry': True}), {'retry': True})

    def test_non_json_or_nonfinite_result_is_failed_not_cached_as_success(self):
        self.wait_result({'bad': 'nan'}, lambda: {'value': float('nan')}, expected=500)
        self.wait_result({'bad': 'list'}, lambda: [1, 2], expected=500)

    def test_failed_atomic_publish_preserves_prior_result_and_removes_temporary(self):
        path = self.jobs._directory() / 'publication.json'
        self.jobs._write(path, {'previous': 1})
        with patch.object(self.jobs.os, 'replace', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                self.jobs._write(path, {'partial': 2})
        self.assertEqual(self.jobs._read(path), {'previous': 1})
        self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_completion_between_initial_read_and_lock_is_reused_without_duplicate_compute(self):
        read = self.jobs._read
        reads = []
        def complete_after_first_read(path):
            value = read(path)
            reads.append(path)
            if len(reads) == 1:
                self.jobs._write(path, {'status': 'complete', 'payload': {'concurrent': 7}})
            return value
        def must_not_run():
            raise AssertionError('Completed concurrent result should be reused')
        with patch.object(self.jobs, '_read', side_effect=complete_after_first_read):
            self.assertEqual(self.jobs.get_or_start({'race': 'completion'}, must_not_run),
                             (200, {'concurrent': 7}))
        # The race path must release the actual file lock.
        lock = self.jobs.FileLock(str(reads[0].with_suffix('.lock')), timeout=0)
        with lock:
            self.assertTrue(lock.is_locked)

    def test_executor_rejection_releases_admission_slot_and_lock_for_retry(self):
        with patch.object(self.jobs._EXECUTOR, 'submit', side_effect=RuntimeError('executor stopping')):
            status, result = self.jobs.get_or_start({'submission': 'retry'}, lambda: {'ignored': True})
        self.assertEqual(status, 500)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.wait_result({'submission': 'retry'}, lambda: {'retry': True}), {'retry': True})
        acquired = [self.jobs._SLOTS.acquire(blocking=False) for _ in range(8)]
        self.assertEqual(acquired, [True] * 8)
        for _ in acquired:
            self.jobs._SLOTS.release()


if __name__ == '__main__':
    unittest.main()
