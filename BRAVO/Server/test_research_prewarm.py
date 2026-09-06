"""Synthetic maintenance tests: no source sync, production database or network."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from zoneinfo import ZoneInfo
from unittest.mock import Mock, patch

from modules import ResearchPrewarm as warm, RCS08Preparation as preparation
from Server.management.commands.run_rcs08_maintenance import maintenance_deadline
from django.core.management.base import CommandError


class ResearchPrewarmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DATASERVER_PATH": self.temp.name})
        env.start(); self.addCleanup(env.stop)
        self.user = types.SimpleNamespace(uid="user")
        self.participant = types.SimpleNamespace(uid="participant", institute="institute")

    def test_roster_matches_only_the_two_cheap_default_browser_requests(self):
        self.assertEqual(warm.default_requests("participant"), [
            ("queryPainScores", {"ParticipantId": "participant"}),
            ("queryDataAvailability", {"ParticipantId": "participant"}),
        ])

    def test_queue_returns_pending_without_waiting_and_keeps_user_ids_private(self):
        with patch.object(warm, "_eligible_users", return_value=[self.user]), patch.object(warm, "_invoke", return_value=(202, {"job_id": "job", "message": "Queued"})) as invoke:
            summary = warm.queue_defaults(self.participant)
        self.assertEqual(invoke.call_count, 2)
        self.assertEqual(summary["status"], "pending")
        self.assertNotIn("user_uid", json.dumps(summary))
        self.assertEqual(warm._read(warm._path("participant"))["entries"][0]["user_uid"], "user")

    def test_low_budget_skips_even_cheap_views(self):
        with patch.object(warm.time, "time", return_value=100), patch.object(warm, "_invoke") as invoke:
            self.assertEqual(warm.queue_defaults(self.participant, deadline=189)["status"], "skipped_budget")
            invoke.assert_not_called()

    def test_equivalent_permissions_and_processing_share_preparation(self):
        users = [types.SimpleNamespace(uid=str(i), configuration={"ActiveStudy": "study", "processing": i % 2}) for i in range(4)]
        models = types.SimpleNamespace(PlatformUser=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kw: users)))
        database = types.SimpleNamespace(checkAccessPermission=lambda user, *a, **kw: {} if user.uid == "3" else {"read": True},
                                         retrieveProcessingSettings=lambda config: ({"setting": config["processing"]}, None))
        import modules
        with patch.dict(sys.modules, {"Server": types.SimpleNamespace(models=models)}), patch.object(modules, "Database", database, create=True):
            self.assertEqual([u.uid for u in warm._eligible_users(self.participant)], ["0", "1"])

    def test_status_records_unavailable_separately_from_processing_failure(self):
        entry = {"operation": "queryPainScores", "request": {}}
        with patch.object(warm, "_invoke", return_value=(200, {"available": False, "reason": "No approved surveys"})):
            warm._submit(entry, self.user)
        self.assertEqual(entry["status"], "unavailable")
        with patch.object(warm, "_invoke", return_value=(500, {})):
            warm._submit(entry, self.user)
        self.assertEqual(entry["status"], "failed")

    def test_expired_pending_status_never_restarts_computation(self):
        warm._write(warm._path("participant"), {"participant_uid": "participant", "deadline": 100,
                    "entries": [{"operation": "queryDataAvailability", "status": "pending", "message": "Queued"}]})
        with patch.dict(sys.modules, {"Server": types.SimpleNamespace(models=Mock())}), patch.object(warm, "_invoke") as invoke:
            changed = warm.poll_pending()
        self.assertEqual(changed[0]["status"], "incomplete")
        invoke.assert_not_called()

    def test_old_heavy_roster_cannot_be_requeued(self):
        warm._write(warm._path("participant"), {"participant_uid": "participant", "deadline": 10000,
                    "entries": [{"operation": "queryBiomarkerAnalysis", "status": "pending", "message": "Queued", "user_uid": "user", "request": {}}]})
        models = types.SimpleNamespace(Participant=types.SimpleNamespace(find=lambda **kw: self.participant))
        with patch.dict(sys.modules, {"Server": types.SimpleNamespace(models=models)}), patch.object(warm.time, "time", return_value=100), patch.object(warm, "_eligible_users", return_value=[self.user]), patch.object(warm, "_invoke") as invoke:
            changed = warm.poll_pending()
        self.assertEqual(changed[0]["status"], "failed")
        invoke.assert_not_called()


class PreparationDeadlineTests(unittest.TestCase):
    def test_nightly_window_and_late_start_budget(self):
        timezone = ZoneInfo("America/Los_Angeles")
        # Winter, summer and both DST-transition dates follow Pacific wall time.
        for month, day in ((1, 4), (9, 4), (3, 8), (11, 1)):
            now = dt.datetime(2026, month, day, 6, 30, tzinfo=timezone)
            with self.subTest(date=now.date()):
                self.assertEqual(maintenance_deadline(now) - now.timestamp(), 1800)
                self.assertEqual(maintenance_deadline(now, now.timestamp() + 14400) - now.timestamp(), 1800)
                self.assertEqual(maintenance_deadline(now, now.timestamp() + 60) - now.timestamp(), 60)
                start = now.replace(hour=3, minute=0)
                self.assertEqual(maintenance_deadline(start) - start.timestamp(), 14400)
                extended = now.replace(hour=5, minute=0)
                self.assertEqual(maintenance_deadline(extended) - extended.timestamp(), 7200)
                for hour, minute in ((2, 59), (7, 0), (12, 0)):
                    with self.assertRaises(CommandError):
                        maintenance_deadline(now.replace(hour=hour, minute=minute))

    def test_no_worker_starts_after_budget_expires(self):
        import modules
        with patch.object(modules, "ReportCache", Mock(), create=True), patch.object(preparation.time, "time", return_value=100), patch.object(preparation.subprocess, "Popen") as start:
            with self.assertRaises(preparation.PreparationTimeout):
                preparation._run_preparation(deadline=104, mode="Nightly")
        start.assert_not_called()

    def test_stopping_parent_also_kills_any_remaining_descendants(self):
        process = Mock(pid=123)
        with patch.object(preparation.os, "killpg") as kill:
            preparation._stop_group(process)
        self.assertEqual(kill.call_args_list[0].args, (123, signal.SIGTERM))
        self.assertEqual(kill.call_args_list[-1].args, (123, signal.SIGKILL))

    def test_deadline_stops_group_and_invalidates_even_after_partial_commits(self):
        import modules
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"DATASERVER_PATH": folder}):
            process = Mock(pid=123, returncode=-15)
            process.wait.side_effect = subprocess.TimeoutExpired("worker", 95)
            process.poll.return_value = -15
            cache = Mock()
            with patch.object(modules, "ReportCache", cache, create=True), patch.object(preparation.time, "time", return_value=100), patch.object(preparation.subprocess, "Popen", return_value=process), patch.object(preparation, "_stop_group") as stop:
                with self.assertRaises(preparation.PreparationTimeout):
                    preparation._run_preparation(deadline=200, mode="Nightly")
            stop.assert_called_once()
            cache.invalidate.assert_called_once_with(neural=True)
            self.assertEqual(process.wait.call_args.kwargs["timeout"], 95)

    def test_manual_and_nightly_share_one_preparation_lock(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"DATASERVER_PATH": folder}):
            with preparation.preparation_lock():
                self.assertTrue(preparation.is_preparing())
                with patch.object(preparation, "_run_preparation") as run:
                    with self.assertRaisesRegex(RuntimeError, "already running"):
                        preparation.run_preparation(deadline=100, mode="Nightly")
                    run.assert_not_called()
            self.assertFalse(preparation.is_preparing())


class MaintenanceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DATASERVER_PATH": self.temp.name})
        env.start(); self.addCleanup(env.stop)

    def test_supervised_success_uses_own_process_group_and_caps_requested_budget(self):
        import modules
        def spawn(command, **kwargs):
            Path(command[-1]).write_text('{"redcap":{"written":1}}')
            return Mock(returncode=0, wait=Mock(return_value=0), poll=Mock(return_value=0))
        for mode, requested, expected in (("Manual", 100000, 7300), ("Nightly", 100000, 14500),
                                          ("Nightly", 1800, 1800)):
            with self.subTest(mode=mode, requested=requested), patch.object(modules, "ReportCache", Mock(), create=True), patch.object(preparation.time, "time", return_value=100), patch.object(preparation.subprocess, "Popen", side_effect=spawn) as start:
                result = preparation.run_preparation(deadline=requested, mode=mode)
            self.assertEqual(result, {"redcap": {"written": 1}})
            self.assertTrue(start.call_args.kwargs["start_new_session"])
            self.assertEqual(float(start.call_args.args[0][-3]), expected)

    def test_nonzero_worker_exit_invalidates_and_reports_private_log(self):
        import modules
        process = Mock(returncode=1, poll=Mock(return_value=1))
        cache = Mock()
        with patch.object(modules, "ReportCache", cache, create=True), patch.object(preparation.time, "time", return_value=100), patch.object(preparation.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "private preparation log"):
                preparation.run_preparation(deadline=1000, mode="Nightly")
        cache.invalidate.assert_called_once_with(neural=True)

    def test_unexpected_supervisor_error_stops_active_child(self):
        import modules
        process = Mock(returncode=None, poll=Mock(return_value=None))
        process.wait.side_effect = OSError("synthetic wait failure")
        cache = Mock()
        with patch.object(modules, "ReportCache", cache, create=True), patch.object(preparation.time, "time", return_value=100), patch.object(preparation.subprocess, "Popen", return_value=process), patch.object(preparation, "_stop_group") as stop:
            with self.assertRaises(OSError):
                preparation.run_preparation(deadline=1000, mode="Nightly")
        stop.assert_called_once_with(process)
        cache.invalidate.assert_called_once_with(neural=True)

    def test_group_shutdown_escalation_and_already_exited_group(self):
        process = Mock(pid=123)
        process.wait.side_effect = [subprocess.TimeoutExpired("worker", 4), 0]
        with patch.object(preparation.os, "killpg", side_effect=[None, ProcessLookupError()]):
            preparation._stop_group(process)
        with patch.object(preparation.os, "killpg", side_effect=ProcessLookupError()):
            preparation._stop_group(process)

    def test_worker_runs_in_order_and_polls_only_cheap_pending_views(self):
        from Server.management.commands import prepare_rcs08_cycle as worker
        output = Path(self.temp.name) / "result.json"
        participant = types.SimpleNamespace(uid="participant")
        events = []
        with patch.object(worker, "start_deadline_watchdog"), patch.object(worker.RCS08Sync, "run_sync", side_effect=lambda **kw: events.append("sync") or {"redcap": {"written": 1}}), patch.object(worker.RCS08Sync, "resolve_participant", return_value=participant), patch.object(worker.ReportCache, "prewarm_participant", side_effect=lambda p: events.append("standard") or []), patch.object(worker.ResearchPrewarm, "queue_defaults", side_effect=lambda p, **kw: events.append("cheap") or {"status": "pending"}), patch.object(worker.ResearchPrewarm, "poll_pending") as poll, patch.object(worker.ResearchPrewarm, "_read", return_value={}), patch.object(worker.ResearchPrewarm, "_summary", return_value={"status": "complete"}), patch.object(worker.time, "time", return_value=100), patch.object(worker.time, "sleep"):
            worker.Command().handle(deadline=1000, result=str(output))
        self.assertEqual(events, ["sync", "standard", "cheap"])
        poll.assert_called_once()
        self.assertEqual(json.loads(output.read_text())["research"]["status"], "complete")

    def test_worker_wont_start_sync_after_deadline(self):
        from Server.management.commands import prepare_rcs08_cycle as worker
        with patch.object(worker, "start_deadline_watchdog"), patch.object(worker.time, "time", return_value=100), patch.object(worker.RCS08Sync, "run_sync") as sync:
            with self.assertRaises(CommandError):
                worker.Command().handle(deadline=103, result=str(Path(self.temp.name) / "result.json"))
        sync.assert_not_called()

    def test_oneshot_command_passes_window_deadline_and_reports_failure(self):
        from Server.management.commands import run_rcs08_maintenance as maintenance
        now = dt.datetime(2026, 9, 4, 13, 30, tzinfo=dt.timezone.utc)
        for failure in (False, True):
            with self.subTest(failure=failure), patch.object(maintenance.dt, "datetime", wraps=dt.datetime) as clock, patch.object(maintenance, "run_preparation", side_effect=RuntimeError("busy") if failure else None, return_value={}) as run:
                clock.now.return_value = now
                if failure:
                    with self.assertRaisesRegex(CommandError, "busy"):
                        maintenance.Command().handle(deadline_epoch=None)
                else:
                    maintenance.Command().handle(deadline_epoch=None)
                self.assertEqual(run.call_args.kwargs["deadline"] - now.timestamp(), 1800)

    def test_expired_requested_deadline_is_refused_inside_window(self):
        now = dt.datetime(2026, 9, 4, 11, 30, tzinfo=dt.timezone.utc)
        with self.assertRaises(CommandError):
            maintenance_deadline(now, now.timestamp())

    def test_manual_daemon_only_runs_explicit_requests_and_preserves_failures(self):
        from Server.management.commands import run_rcs08_scheduler as scheduler
        for busy, request, failure in ((True, None, False), (False, None, False), (False, {"request_id": "test"}, False), (False, {"request_id": "test"}, True)):
            with self.subTest(busy=busy, request=request, failure=failure), patch.object(scheduler, "is_preparing", return_value=busy), patch.object(scheduler.RCS08ManualSync, "fail_interrupted_request"), patch.object(scheduler.RCS08ManualSync, "claim_request", return_value=request) as claim, patch.object(scheduler.RCS08ManualSync, "complete_request") as complete, patch.object(scheduler.RCS08ManualSync, "fail_request") as failed, patch.object(scheduler, "run_preparation", side_effect=RuntimeError("synthetic") if failure else None, return_value={}) as run, patch.object(scheduler.time, "sleep", side_effect=StopIteration):
                with self.assertRaises(StopIteration):
                    scheduler.Command().run_scheduler(poll_seconds=10)
                if busy:
                    claim.assert_not_called()
                if request and not busy:
                    run.assert_called_once()
                    (failed if failure else complete).assert_called_once()
                else:
                    run.assert_not_called()

    def test_manual_daemon_singleton_and_lock_cleanup(self):
        from Server.management.commands import run_rcs08_scheduler as scheduler
        lock = Mock()
        with patch.object(scheduler.RCS08ManualSync, "scheduler_lock", return_value=lock), patch.object(scheduler.Command, "run_scheduler"):
            scheduler.Command().handle(poll_seconds=10)
        lock.release.assert_called_once()
        from filelock import Timeout
        lock.acquire.side_effect = Timeout("busy")
        with patch.object(scheduler.RCS08ManualSync, "scheduler_lock", return_value=lock):
            with self.assertRaises(CommandError):
                scheduler.Command().handle(poll_seconds=10)

    def test_all_management_arguments_parse(self):
        from Server.management.commands import prepare_rcs08_cycle, run_rcs08_maintenance, run_rcs08_scheduler
        for module, args in ((prepare_rcs08_cycle, ["--deadline", "1000", "--result", "/tmp/result"]),
                             (run_rcs08_maintenance, ["--deadline-epoch", "1000"]),
                             (run_rcs08_scheduler, ["--external-maintenance"])):
            parser = module.Command().create_parser("manage.py", "test")
            parser.parse_args(args)


class PrewarmFailureAndPollTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DATASERVER_PATH": self.temp.name}); env.start(); self.addCleanup(env.stop)
        self.user = types.SimpleNamespace(uid="user")
        self.participant = types.SimpleNamespace(uid="participant", institute="institute")

    def test_invalid_paths_and_unpublished_status_are_not_accepted(self):
        with self.assertRaises(ValueError):
            warm._path("../other")
        path = warm._path("participant")
        self.assertEqual(warm._read(path), {})
        path.write_text('[]'); self.assertEqual(warm._read(path), {})
        with patch.object(warm.json, "dump", side_effect=ValueError("synthetic")):
            with self.assertRaises(ValueError):
                warm._write(path, {})
        self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_internal_factory_invokes_the_resolved_view_with_authenticated_user(self):
        def view(request):
            self.assertEqual(request.path, '/api/queryPainScores')
            self.assertIs(request._force_auth_user, self.user)
            self.assertEqual(json.loads(request.body), {'ParticipantId': 'participant'})
            return types.SimpleNamespace(status_code=202, data={'status': 'queued'})
        with patch('django.urls.resolve', return_value=types.SimpleNamespace(func=view)):
            self.assertEqual(warm._invoke(self.user, 'queryPainScores', {'ParticipantId': 'participant'}), (202, {'status': 'queued'}))

    def test_raised_view_error_is_failed_and_mid_queue_budget_stops_new_jobs(self):
        entry = {"operation": "queryPainScores", "request": {}}
        with patch.object(warm, '_invoke', side_effect=RuntimeError('synthetic')), patch.object(warm.log, 'exception'):
            warm._submit(entry, self.user)
        self.assertEqual(entry['status'], 'failed')
        with patch.object(warm.time, 'time', side_effect=[100, 150, 151]), patch.object(warm, '_eligible_users', return_value=[self.user]), patch.object(warm, '_invoke') as invoke:
            result = warm.queue_defaults(self.participant, deadline=200)
        self.assertEqual(result['status'], 'incomplete'); invoke.assert_not_called()

    def test_poll_pending_completes_or_reports_revoked_access_without_requeueing_failures(self):
        models = types.SimpleNamespace(Participant=types.SimpleNamespace(find=lambda **kw: self.participant))
        for authorized, reply, expected in ((True, (200, {'available': True}), 'complete'),
                                            (False, (200, {}), 'failed'),
                                            (True, (202, {'message': 'Queued', 'job_id': 'job'}), 'pending')):
            state = {'participant_uid': 'participant', 'deadline': 1000, 'entries': [{'operation': 'queryPainScores', 'status': 'pending', 'message': 'Queued', 'request': {'ParticipantId': 'participant'}, 'user_uid': 'user'}]}
            warm._write(warm._path('participant'), state)
            with patch.dict(sys.modules, {'Server': types.SimpleNamespace(models=models)}), patch.object(warm.time, 'time', return_value=100), patch.object(warm, '_eligible_users', return_value=[self.user] if authorized else []), patch.object(warm, '_invoke', return_value=reply) as invoke:
                changed = warm.poll_pending()
                self.assertEqual(warm._summary(warm._read(warm._path('participant')))['status'], expected)
                if expected == 'pending': self.assertEqual(changed, [])
                if not authorized: invoke.assert_not_called()
                warm.poll_pending()  # not due; never starts another request
                self.assertLessEqual(invoke.call_count, 1)

    def test_status_lock_contention_does_not_start_duplicate_jobs(self):
        from filelock import FileLock
        state = {'participant_uid': 'participant', 'deadline': 1000, 'entries': [{'operation': 'queryPainScores', 'status': 'pending', 'message': 'Queued'}]}
        path = warm._path('participant'); warm._write(path, state)
        with FileLock(str(path.with_suffix('.lock')), timeout=0), patch.dict(sys.modules, {'Server': types.SimpleNamespace(models=Mock())}), patch.object(warm, '_invoke') as invoke:
            self.assertEqual(warm.queue_defaults(self.participant)['status'], 'pending')
            self.assertEqual(warm.poll_pending(), [])
        invoke.assert_not_called()

    def test_worker_rejects_non_object_result(self):
        import modules
        def spawn(command, **kwargs):
            Path(command[-1]).write_text('[]')
            return Mock(returncode=0, wait=Mock(return_value=0), poll=Mock(return_value=0))
        with patch.object(modules, 'ReportCache', Mock(), create=True), patch.object(preparation.time, 'time', return_value=100), patch.object(preparation.subprocess, 'Popen', side_effect=spawn):
            with self.assertRaisesRegex(RuntimeError, 'valid result'):
                preparation.run_preparation(deadline=1000, mode='Manual')

    def test_real_subprocess_timeout_stops_descendants_and_releases_shared_lock(self):
        """Real OS process-group test; tiny sleepers only, no Django/sync in children."""
        import modules
        import time
        pid_path = Path(self.temp.name) / 'grandchild.pid'
        child = ('import os,signal,time; '
                 'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                 f'open({str(pid_path)!r},"w").write(str(os.getpid())); '
                 'time.sleep(300)')
        parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(300)'
        real_popen = subprocess.Popen
        processes = []
        def spawn_tiny(_command, **kwargs):
            process = real_popen([sys.executable, '-c', parent], **kwargs)
            processes.append(process)
            ready_deadline = time.monotonic() + 2
            while not pid_path.exists() and time.monotonic() < ready_deadline:
                time.sleep(.01)
            self.assertTrue(pid_path.exists())
            return process
        started = time.monotonic()
        try:
            with patch.object(modules, 'ReportCache', Mock(), create=True), patch.object(preparation.subprocess, 'Popen', side_effect=spawn_tiny):
                with self.assertRaises(preparation.PreparationTimeout):
                    preparation.run_preparation(deadline=time.time() + 7, mode='Synthetic')
            self.assertLess(time.monotonic() - started, 8)
            self.assertIsNotNone(processes[0].poll())
            self.assertFalse(preparation.is_preparing())
            # On Linux an orphan can briefly be a zombie awaiting PID1; that is
            # terminated, not running. The validation container is disposable.
            stat = Path('/proc') / pid_path.read_text() / 'stat'
            deadline = time.monotonic() + 1
            while stat.exists() and stat.read_text().split()[2] not in ('Z', 'X') and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(not stat.exists() or stat.read_text().split()[2] in ('Z', 'X'))
        finally:
            for process in processes:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()


    def test_child_watchdog_requires_own_group_and_keeps_absolute_deadline(self):
        with patch.object(preparation.os, "getpgrp", return_value=1), patch.object(preparation.os, "getpid", return_value=2):
            with self.assertRaisesRegex(RuntimeError, "own supervised"):
                preparation.start_deadline_watchdog(1000)
        with patch.object(preparation.os, "getpgrp", return_value=42), patch.object(preparation.os, "getpid", return_value=42), patch.object(preparation.time, "time", return_value=100), patch.object(preparation, "Timer") as timer, patch.object(preparation.os, "killpg") as kill:
            preparation.start_deadline_watchdog(160)
            self.assertEqual(timer.call_args.args[0], 60)
            self.assertTrue(timer.return_value.daemon)
            timer.return_value.start.assert_called_once()
            timer.call_args.args[1]()
            kill.assert_called_once_with(42, signal.SIGKILL)

    def test_real_child_watchdog_terminates_without_supervisor_intervention(self):
        code = ('import time; from modules.RCS08Preparation import start_deadline_watchdog; '
                'start_deadline_watchdog(time.time()+0.25); time.sleep(30)')
        process = subprocess.Popen([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                                   start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            process.wait(timeout=3)
            self.assertEqual(process.returncode, -signal.SIGKILL, process.stderr.read().decode())
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            process.stderr.close()
