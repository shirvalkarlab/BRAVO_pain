"""Gate regressions use independent tiny reports, not project coverage results."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import coverage_gate as gate


class CoverageGateTests(unittest.TestCase):
    def test_statement_percent_is_not_branch_percent(self):
        entry = {'summary': {'percent_covered': 99, 'num_branches': 20,
                             'covered_branches': 10, 'missing_branches': 10}}
        self.assertEqual(gate.branch_counts(entry, 'python'), (10, 20))

    def test_invalid_or_absent_branch_instrumentation_rejected(self):
        for values in ((20, 19, 0), (True, 0, 1), (2, -1, 3)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                gate.branch_counts({'summary': dict(zip(
                    ('num_branches', 'covered_branches', 'missing_branches'), values))}, 'python')
        with self.assertRaises(KeyError):
            gate.branch_counts({'summary': {'percent_covered': 100}}, 'python')

    def test_istanbul_counts_each_outcome_and_validates_map(self):
        report = {'b': {'0': [2, 0], '1': [1, 4]}, 'branchMap': {
            '0': {'locations': [{}, {}]}, '1': {'locations': [{}, {}]}}}
        self.assertEqual(gate.branch_counts(report, 'javascript'), (3, 4))
        report['branchMap']['1']['locations'] = [{}]
        with self.assertRaises(ValueError):
            gate.branch_counts(report, 'javascript')

    def test_unimported_new_critical_file_is_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/new.py').write_text('if ready:\n    run()\n')
            (root / 'src/test_new.py').write_text('assert True\n')
            source, critical = gate.discover(root, {'source_roots': ['src'],
                'extensions': ['.py'], 'critical_globs': ['src/**/*.py']})
            self.assertEqual(source, {'src/new.py'})
            self.assertEqual(critical, source)
            with self.assertRaisesRegex(ValueError, 'no files'):
                gate.discover(root, {'source_roots': ['src'], 'extensions': ['.py'],
                                    'critical_globs': ['src/missing.py']})

    def test_python_function_scope_uses_its_branches_and_refuses_missing_names(self):
        entry = {'summary': {'num_branches': 1000, 'covered_branches': 1, 'missing_branches': 999},
                 'functions': {'new_helper': {'summary': {
                     'num_branches': 20, 'covered_branches': 19, 'missing_branches': 1}}}}
        self.assertEqual(gate.function_branches(entry, 'python', 'new_helper'), (19, 20))
        with self.assertRaisesRegex(ValueError, 'missing'):
            gate.function_branches(entry, 'python', 'typo')

    def test_istanbul_function_counts_outcomes_in_named_bounds_not_renderer_or_function_hits(self):
        def point(line, column=0):
            return {'line': line, 'column': column}
        def branch(start, end):
            return {'loc': {'start': point(start), 'end': point(end)}, 'locations': [{}, {}]}
        entry = {'fnMap': {'0': {'name': 'prepare',
                     'decl': {'start': point(2), 'end': point(2, 10)},
                     'loc': {'start': point(3), 'end': point(10)}}},
                 'f': {'0': 9999},
                 'b': {'parameter': [1, 0], 'nested': [5, 2], 'renderer': [0, 0]},
                 'branchMap': {'parameter': branch(2, 2), 'nested': branch(6, 7), 'renderer': branch(12, 13)}}
        self.assertEqual(gate.function_branches(entry, 'javascript', 'prepare'), (3, 4))
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            gate.function_branches(entry, 'javascript', 'typo')
        entry['fnMap']['1'] = entry['fnMap']['0']
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            gate.function_branches(entry, 'javascript', 'prepare')

    def test_threshold_and_missing_report_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/a.py').write_text('pass\n')
            profile = {'source_roots': ['src'], 'extensions': ['.py'],
                       'critical_globs': ['src/*.py']}
            (root / 'backend-status.json').write_text(json.dumps({'status': 'passed', 'fingerprint': 'fixture'}))
            report = {'meta': {'branch_coverage': True}, 'files': {
                'src/a.py': {'summary': {'num_branches': 20, 'covered_branches': 18, 'missing_branches': 2}}}}
            (root / 'python.json').write_text(json.dumps(report))
            with patch.object(gate, 'source_fingerprint', return_value='fixture'):
                result = gate.measure(root, root, 'python', profile, 95)
                self.assertEqual(result['critical']['percent'], 90)
                self.assertEqual(len(result['below_threshold']), 2)
                report['files']['src/a.py']['summary'].update(covered_branches=19, missing_branches=1)
                (root / 'python.json').write_text(json.dumps(report))
                self.assertEqual(gate.measure(root, root, 'python', profile, 95)['below_threshold'], [])
                (root / 'src/unimported.py').write_text('pass\n')
                with self.assertRaisesRegex(ValueError, 'missing coverage'):
                    gate.measure(root, root, 'python', profile, 95)
            with patch.object(gate, 'source_fingerprint', return_value='changed'):
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    gate.measure(root, root, 'python', profile, 95)


if __name__ == '__main__':
    unittest.main()
