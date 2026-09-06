"""True branch gate for current critical scope; full discovered-tree legacy baseline.

No percentage uses line/statement counts. All source files are discovered even
if tests never import them; critical modules/functions are explicitly declared.
No active critical file exclusion or threshold override is supported. Test
sources are not production scope.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = Path(__file__).with_name('contract.json')


def is_source(path, extensions):
    return (path.is_file() and path.suffix in extensions and
            not any(part in {'tests', 'migrations', '__pycache__'} for part in path.parts) and
            not path.name.startswith('test_') and path.name != 'tests.py' and
            '.test.' not in path.name and '.spec.' not in path.name)


def discover(root, profile):
    sources = set()
    for folder in profile['source_roots']:
        directory = root / folder
        if not directory.is_dir():
            raise ValueError(f'Missing source root: {folder}')
        sources.update(path.relative_to(root).as_posix() for path in directory.rglob('*')
                       if is_source(path, profile['extensions']))
    if not sources:
        raise ValueError('Empty source scope')
    critical = set()
    for pattern in profile['critical_globs']:
        matches = {path.relative_to(root).as_posix() for path in root.glob(pattern)
                   if is_source(path, profile['extensions'])}
        if not matches:
            raise ValueError(f'Critical source pattern has no files: {pattern}')
        critical.update(matches)
    if not critical <= sources:
        raise ValueError('Critical files outside discovered source scope')
    return sources, critical


def source_fingerprint(root, language):
    contract = json.loads(CONTRACT.read_text())
    profile = contract[language]
    digest = hashlib.sha256(CONTRACT.read_bytes())
    # Include tests and source, not just the covered scope. Changing a fixture or
    # runner invalidates the evidence too. Never read .env or patient artifacts.
    for folder in profile['source_roots']:
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and path.suffix in profile['extensions']:
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
    for path in sorted(CONTRACT.parent.glob('*.py')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    extra = ['BRAVO/requirements.txt'] if language == 'python' else [
        'Client/package.json', 'Client/package-lock.json', 'Client/jsconfig.json']
    for name in extra:
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    if language == 'python':
        # The API compatibility regression verifies the real frontend caller.
        # Focused diagnostic containers may omit it; the full gate mounts it.
        caller = root / 'Client/src/views/Reports/Biomarkers/index.js'
        digest.update(caller.read_bytes() if caller.is_file() else b'frontend-caller-not-mounted')
    return digest.hexdigest()


def branch_counts(entry, language):
    if language == 'python':
        summary = entry['summary']
        total, covered, missing = (summary[key] for key in
                                   ('num_branches', 'covered_branches', 'missing_branches'))
        if any(type(n) is not int or n < 0 for n in (total, covered, missing)) or covered + missing != total:
            raise ValueError('Invalid coverage.py branch counts')
        return covered, total
    branches, mapping = entry['b'], entry['branchMap']
    if not isinstance(branches, dict) or branches.keys() != mapping.keys():
        raise ValueError('Istanbul branch maps do not match')
    covered = total = 0
    for key, values in branches.items():
        if not values or len(values) != len(mapping[key]['locations']):
            raise ValueError('Invalid Istanbul branch locations')
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError('Invalid Istanbul branch hits')
        total += len(values)
        covered += sum(value > 0 for value in values)
    return covered, total


def function_branches(entry, language, name):
    if language == 'python':
        functions = entry['functions']
        if name not in functions:
            raise ValueError(f'Critical function missing from coverage report: {name}')
        return branch_counts(functions[name], language)
    matches = [function for function in entry['fnMap'].values() if function['name'] == name]
    if len(matches) != 1:
        raise ValueError(f'Critical Istanbul function must exist exactly once: {name}')
    def position(value):
        point = value['line'], value['column']
        if any(type(number) is not int or number < 0 for number in point):
            raise ValueError('Invalid Istanbul source position')
        return point
    function = matches[0]['loc']
    start, end = position(function['start']), position(function['end'])
    if 'decl' in matches[0]:
        start = min(start, position(matches[0]['decl']['start']))
    if start > end:
        raise ValueError('Invalid Istanbul function bounds')
    selected = {}
    for key, branch in entry['branchMap'].items():
        location = branch['loc']
        branch_start, branch_end = position(location['start']), position(location['end'])
        if branch_start > branch_end:
            raise ValueError('Invalid Istanbul branch bounds')
        if start <= branch_start and branch_end <= end:
            selected[key] = branch
    # Include outcomes in callbacks nested inside this named function: they are
    # part of its new preparation logic. Never use the function-hit count as
    # branch coverage, nor include unrelated renderer branches outside its range.
    return branch_counts({'branchMap': selected,
        'b': {key: entry['b'][key] for key in selected}}, 'javascript')


def measure(root, results, language, profile, minimum):
    sources, critical = discover(root, profile)
    status = json.loads((results / ('backend-status.json' if language == 'python' else 'frontend-status.json')).read_text())
    if status['status'] != 'passed' or status['fingerprint'] != source_fingerprint(root, language):
        raise ValueError(f'{language}: source changed or tests did not pass; rerun tests')
    report = json.loads((results / ('python.json' if language == 'python' else 'coverage-final.json')).read_text())
    if language == 'python':
        if report['meta']['branch_coverage'] is not True:
            raise ValueError('Python branch instrumentation missing')
        entries = report['files']
    else:
        entries = {}
        for name, entry in report.items():
            path = Path(name)
            if name.startswith('/usr/src/Client/src/'):
                relative = 'Client/src/' + name.removeprefix('/usr/src/Client/src/')
            else:
                relative = path.resolve().relative_to(root).as_posix() if path.is_absolute() else name
            if relative in entries:
                raise ValueError('Duplicate normalized coverage path')
            entries[relative] = entry
    absent = sorted(sources - entries.keys())
    if absent:
        raise ValueError(f'{language}: discovered sources missing coverage: {absent}')
    counts = {name: branch_counts(entries[name], language) for name in sorted(sources)}
    units = {name: counts[name] for name in critical}
    function_results = []
    for file, functions in profile.get('critical_functions', {}).items():
        if file not in sources or file in critical:
            raise ValueError('Function scope must identify a legacy file outside whole-module strict scope')
        if not functions or len(set(functions)) != len(functions):
            raise ValueError('Critical function names must be nonempty and unique')
        for function in functions:
            if not isinstance(function, str) or not function:
                raise ValueError('Invalid critical function name')
            label = file + '::' + function
            covered, total = function_branches(entries[file], language, function)
            units[label] = covered, total
            function_results.append({'function': label, 'covered_branches': covered,
                'total_branches': total, 'percent': covered * 100 / total if total else None})
    failures = []
    def summary(names):
        selected = {**counts, **units}
        covered = sum(selected[name][0] for name in names)
        total = sum(selected[name][1] for name in names)
        return {'covered_branches': covered, 'total_branches': total,
                'percent': covered * 100 / total if total else None}
    for name in sorted(units):
        covered, total = units[name]
        if total and covered * 100 < minimum * total:
            failures.append({'file': name, **summary([name])})
    aggregate = summary(units)
    if aggregate['total_branches'] and aggregate['percent'] < minimum:
        failures.append({'file': '<critical aggregate>', **aggregate})
    return {'language': language, 'legacy_baseline': summary(sources),
            'legacy_files': len(sources), 'critical_files': len(critical),
            'critical_function_results': function_results,
            'critical': aggregate, 'below_threshold': failures,
            'zero_branch_critical_units': [name for name in sorted(units) if units[name][1] == 0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-frontend', action='store_true')
    parser.add_argument('--record-frontend', action='store_true')
    args = parser.parse_args()
    results = ROOT / 'reports/validation'
    if args.start_frontend:
        (results / 'frontend-start.json').write_text(json.dumps({
            'fingerprint': source_fingerprint(ROOT, 'javascript')}))
        return 0
    if args.record_frontend:
        initial = json.loads((results / 'frontend-start.json').read_text())['fingerprint']
        if initial != source_fingerprint(ROOT, 'javascript'):
            raise ValueError('Source changed while frontend tests ran; rerun validation')
        (results / 'frontend-status.json').write_text(json.dumps({
            'status': 'passed', 'fingerprint': initial,
            'tests': 'portable only',
        }))
        return 0
    contract = json.loads(CONTRACT.read_text())
    if contract['version'] != 1 or contract['minimum_true_branch_percent'] != 95:
        raise ValueError('Unsupported contract or weakened branch threshold')
    exceptions = contract.get('legacy_exceptions', [])
    for item in exceptions:
        fields = {'path', 'source_revision', 'reason', 'risk', 'alternative_evidence', 'owner', 'revisit'}
        if set(item) != fields or any(not isinstance(item[key], str) or not item[key].strip() for key in fields):
            raise ValueError('Legacy exceptions require exact scope, reason, risk, evidence, owner and revisit condition')
        if not (ROOT / item['path']).is_file():
            raise ValueError('Legacy exception file is missing')
    function_files = set().union(*(contract[language].get('critical_functions', {}) for language in ('python', 'javascript')))
    if not function_files <= {item['path'] for item in exceptions}:
        raise ValueError('Partial function scope requires an explicit legacy exception for the remaining file')
    outcomes, errors = [], []
    for language in ('python', 'javascript'):
        try:
            outcomes.append(measure(ROOT, results, language, contract[language], 95))
        except (KeyError, ValueError, OSError, TypeError) as error:
            errors.append(f'{language}: {error}')
    payload = {'profiles': outcomes, 'errors': errors,
               'legacy_exceptions': exceptions,
               'status': 'failed' if errors or any(item['below_threshold'] for item in outcomes) else 'passed'}
    results.mkdir(parents=True, exist_ok=True)
    (results / 'branch-summary.json').write_text(json.dumps(payload, indent=2) + '\n')
    print(json.dumps(payload, indent=2))
    return 1 if payload['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
