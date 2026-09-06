"""Fail-closed lint regressions, including real linters on synthetic source."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import lint


class LintReportTests(unittest.TestCase):
    def result(self, payload, code=0):
        return subprocess.CompletedProcess([], code, json.dumps(payload), '')

    def test_missing_files_and_bad_linter_output_cannot_pass(self):
        for result in [self.result([], 2), self.result({}, 0), self.result([], 1),
                       subprocess.CompletedProcess([], 0, 'not-json', '')]:
            with self.subTest(result=result), self.assertRaises(ValueError):
                lint.parse_report('python', result, ['BRAVO/example.py'])
        with self.assertRaisesRegex(ValueError, 'requested critical files'):
            lint.parse_report('javascript', self.result([]), ['Client/src/example.js'])

    def test_unexpected_paths_and_unknown_severity_fail(self):
        python = [{'filename': '/workspace/other.py', 'location': {'row': 1},
                   'code': 'F821', 'message': 'Undefined name'}]
        with self.assertRaisesRegex(ValueError, 'unexpected source files'):
            lint.parse_report('python', self.result(python, 1), ['BRAVO/example.py'])
        javascript = [{'filePath': '/usr/src/Client/src/example.js',
                       'messages': [{'severity': 0, 'line': 1, 'message': 'invalid'}]}]
        with self.assertRaisesRegex(ValueError, 'unknown diagnostic severity'):
            lint.parse_report('javascript', self.result(javascript), ['Client/src/example.js'])

    def test_maintenance_warning_remains_visible(self):
        report = [{'filename': '/workspace/BRAVO/example.py', 'location': {'row': 1},
                   'code': 'F401', 'message': 'Unused import'}]
        raw, findings = lint.parse_report('python', self.result(report, 1), ['BRAVO/example.py'])
        self.assertEqual(raw, report)
        self.assertEqual(findings[0]['severity'], 'warning')

    def test_scope_cannot_be_empty_or_reference_an_undeclared_file(self):
        with tempfile.TemporaryDirectory() as folder:
            contract = Path(folder) / 'contract.json'
            contract.write_text(json.dumps({'python': {'critical_functions': {}}}))
            with patch.object(lint, 'CONTRACT', contract), patch.object(lint, 'discover', return_value=(set(), set())):
                with self.assertRaisesRegex(ValueError, 'nonempty critical scope'):
                    lint.source_paths(Path(folder), 'python')
            contract.write_text(json.dumps({'python': {'critical_functions': {'other.py': ['example']}}}))
            with patch.object(lint, 'CONTRACT', contract), patch.object(lint, 'discover', return_value=({'safe.py'}, {'safe.py'})):
                with self.assertRaisesRegex(ValueError, 'inside declared source roots'):
                    lint.source_paths(Path(folder), 'python')

    def test_changed_tool_version_requires_preparation(self):
        with patch.object(lint.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ruff 0.0.0', '')):
            with self.assertRaisesRegex(ValueError, 'run scripts/bravo-validate prepare'):
                lint.check_language(Path('/synthetic'), 'python', ['BRAVO/example.py'])


class ActualLinterTests(unittest.TestCase):
    """Missing Docker or prepared linters fails rather than skipping evidence."""

    def run_gate(self, python_source, javascript_source):
        with tempfile.TemporaryDirectory(prefix='bravo-synthetic-lint-') as folder:
            root = Path(folder)
            (root / 'BRAVO').mkdir()
            (root / 'Client/src').mkdir(parents=True)
            (root / 'BRAVO/example.py').write_text(python_source)
            (root / 'Client/src/example.js').write_text(javascript_source)
            shutil.copy2(lint.ROOT / 'Client/package.json', root / 'Client/package.json')
            paths = {'python': ['BRAVO/example.py'], 'javascript': ['Client/src/example.js']}
            # Substitute fixture routing only; real pinned linters and main's
            # actual CLI return status determine pass/fail.
            with patch.object(lint, 'ROOT', root), patch.object(lint, 'source_paths', side_effect=lambda _, lang: paths[lang]), \
                    patch.object(lint, 'source_fingerprint', return_value='synthetic-fixed-source'), patch('sys.argv', ['lint.py']):
                result = lint.main()
            return result, json.loads((root / 'reports/validation/lint-summary.json').read_text())

    def test_valid_sources_pass_and_maintenance_warning_is_reported(self):
        code, report = self.run_gate('import math\nVALUE = 1\n', 'export const value = 1;\n')
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['profiles'][0]['warnings'], 1)

    def test_undefined_python_name_fails_gate(self):
        code, report = self.run_gate('VALUE = unknown_value\n', 'export const value = 1;\n')
        self.assertEqual(code, 1)
        self.assertEqual(report['profiles'][0]['errors'], 1)
        self.assertEqual(report['profiles'][0]['findings'][0]['rule'], 'F821')

    def test_invalid_python_syntax_fails_gate(self):
        code, report = self.run_gate('def broken(:\n    pass\n', 'export const value = 1;\n')
        self.assertEqual(code, 1)
        self.assertGreater(report['profiles'][0]['errors'], 0)

    def test_actual_eslint_undefined_name_fails_gate(self):
        code, report = self.run_gate('VALUE = 1\n', 'export const value = unknownValue;\n')
        self.assertEqual(code, 1)
        self.assertEqual(report['profiles'][1]['errors'], 1)
        self.assertEqual(report['profiles'][1]['findings'][0]['rule'], 'no-undef')


class ShellGateTests(unittest.TestCase):
    def run_shell_gate(self, mode, stale_dependency=None, lint_exit=0):
        with tempfile.TemporaryDirectory(prefix='bravo-lint-shell-') as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            (root / 'bin').mkdir()
            (root / 'Client').mkdir()
            dependencies = {'package.json': b'{"name":"synthetic"}\n',
                            'package-lock.json': b'{"lockfileVersion":3}\n'}
            for name, content in dependencies.items():
                (root / 'Client' / name).write_bytes(content)
            shutil.copy2(lint.ROOT / 'scripts/bravo-validate', root / 'scripts/bravo-validate')
            fake_python = root / 'bin/python3'
            fake_python.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$LINT_TEST_CALLS"
case "$1" in *lint.py) exit "$LINT_TEST_EXIT";; esac
exit 0
''')
            fake_python.chmod(0o755)
            fake_docker = root / 'bin/docker'
            fake_docker.write_text('''#!/bin/sh
case "$*" in
  *package-lock.json) printf '%s  package-lock.json\\n' "$LINT_TEST_LOCK_SHA";;
  *package.json) printf '%s  package.json\\n' "$LINT_TEST_PACKAGE_SHA";;
  *) exit 97;;
esac
''')
            fake_docker.chmod(0o755)
            calls = root / 'calls.log'
            environment = dict(os.environ, PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'],
                               LINT_TEST_CALLS=str(calls), LINT_TEST_EXIT=str(lint_exit),
                               LINT_TEST_PACKAGE_SHA=hashlib.sha256(dependencies['package.json']).hexdigest(),
                               LINT_TEST_LOCK_SHA=hashlib.sha256(dependencies['package-lock.json']).hexdigest())
            if stale_dependency:
                key = 'LINT_TEST_PACKAGE_SHA' if stale_dependency == 'package.json' else 'LINT_TEST_LOCK_SHA'
                environment[key] = '0' * 64
            result = subprocess.run(['bash', str(root / 'scripts/bravo-validate'), mode],
                                    env=environment, capture_output=True, text=True, check=False)
            return result, calls.read_text().splitlines() if calls.exists() else []

    def test_lint_failure_stops_actual_check_entrypoint_before_runtime_stages(self):
        result, calls = self.run_shell_gate('check', lint_exit=9)
        self.assertEqual(result.returncode, 9)
        self.assertEqual(calls, ['-m unittest discover -s scripts/validation -p test_*.py',
                                 'scripts/validation/lint.py'])

    def test_stale_package_or_lock_stops_standalone_lint_before_tools_run(self):
        for dependency in ('package.json', 'package-lock.json'):
            with self.subTest(dependency=dependency):
                result, calls = self.run_shell_gate('lint', stale_dependency=dependency)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f'Validation dependencies changed (Client/{dependency})', result.stderr)
                self.assertIn('run scripts/bravo-validate prepare again', result.stderr)
                self.assertEqual(calls, [])

    def test_current_package_and_lock_allow_standalone_lint(self):
        result, calls = self.run_shell_gate('lint')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, ['scripts/validation/lint.py'])


if __name__ == '__main__':
    unittest.main()
