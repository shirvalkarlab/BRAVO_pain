"""Portable correctness lint using the same declared critical scope as coverage.

Unused Python imports/locals and existing ESLint warnings remain visible advisory
findings. Syntax, undefined names and every other selected error fail acceptance.
"""
import argparse
import json
from pathlib import Path
import subprocess

from coverage_gate import CONTRACT, ROOT, discover, source_fingerprint

RUFF_VERSION = '0.16.6'
ESLINT_VERSION = '8.8.0'
PYTHON_ADVISORIES = frozenset({'F401', 'F841'})
IMAGES = {'python': 'bravo-local:validation-tests',
          'javascript': 'bravo-local:validation-client'}


def source_paths(root, language):
    profile = json.loads(CONTRACT.read_text())[language]
    discovered, critical = discover(root, profile)
    critical.update(profile.get('critical_functions', {}))
    if not critical or not critical <= discovered:
        raise ValueError('Lint requires a nonempty critical scope inside declared source roots')
    return sorted(critical)


def command(root, language, paths):
    args = ['docker', 'run', '--rm', '--network', 'none']
    if language == 'python':
        args += ['-v', f'{root / "BRAVO"}:/workspace/BRAVO:ro',
                 '-w', '/workspace', IMAGES[language], 'ruff', 'check',
                 '--isolated', '--no-cache', '--select', 'E9,F',
                 '--output-format', 'json', *paths]
    else:
        args += ['-v', f'{root / "Client/src"}:/usr/src/Client/src:ro',
                 '-v', f'{root / "Client/package.json"}:/usr/src/Client/package.json:ro',
                 '-w', '/usr/src/Client', IMAGES[language],
                 './node_modules/.bin/eslint', '--no-cache', '--format', 'json',
                 *(path.removeprefix('Client/') for path in paths)]
    return args


def parse_report(language, result, paths):
    if result.returncode not in (0, 1):
        raise ValueError(f'{language} linter failed to execute (exit {result.returncode}): {result.stderr.strip()}')
    report = json.loads(result.stdout)
    if not isinstance(report, list):
        raise ValueError(f'{language} linter did not return a diagnostic list')
    findings = []
    if language == 'python':
        for item in report:
            findings.append({'path': item['filename'].removeprefix('/workspace/'),
                             'line': item['location']['row'], 'rule': item['code'],
                             'severity': 'warning' if item['code'] in PYTHON_ADVISORIES else 'error',
                             'message': item['message']})
    else:
        reported = {item['filePath'].replace('/usr/src/Client/', 'Client/', 1) for item in report}
        if reported != set(paths):
            raise ValueError('ESLint report does not cover the requested critical files')
        for item in report:
            for message in item['messages']:
                if message['severity'] not in (1, 2):
                    raise ValueError('ESLint returned an unknown diagnostic severity')
                findings.append({'path': item['filePath'].replace('/usr/src/Client/', 'Client/', 1),
                                 'line': message['line'], 'rule': message.get('ruleId'),
                                 'severity': 'error' if message['severity'] == 2 else 'warning',
                                 'message': message['message']})
    if result.returncode == 1 and not findings:
        raise ValueError(f'{language} linter failed without diagnostic evidence')
    if any(item['path'] not in paths for item in findings):
        raise ValueError(f'{language} diagnostics refer to unexpected source files')
    return report, findings


def check_language(root, language, paths):
    version_command = ['ruff', '--version'] if language == 'python' else [
        './node_modules/.bin/eslint', '--version']
    expected = f'ruff {RUFF_VERSION}' if language == 'python' else f'v{ESLINT_VERSION}'
    version = subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                              IMAGES[language], *version_command],
                             capture_output=True, text=True, check=True).stdout.strip()
    if version != expected:
        raise ValueError(f'{language} lint tool changed; run scripts/bravo-validate prepare (expected {expected})')
    result = subprocess.run(command(root, language, paths), capture_output=True, text=True, check=False)
    return parse_report(language, result, paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ruff-version', action='store_true')
    args = parser.parse_args()
    if args.ruff_version:
        print(RUFF_VERSION)
        return 0
    results = ROOT / 'reports/validation'
    results.mkdir(parents=True, exist_ok=True)
    for name in ('lint-python.json', 'lint-javascript.json', 'lint-summary.json'):
        (results / name).unlink(missing_ok=True)
    profiles, errors = [], []
    for language in ('python', 'javascript'):
        try:
            paths = source_paths(ROOT, language)
            before = source_fingerprint(ROOT, language)
            report, findings = check_language(ROOT, language, paths)
            (results / f'lint-{language}.json').write_text(json.dumps(report, indent=2) + '\n')
            if source_fingerprint(ROOT, language) != before:
                raise ValueError(f'{language} source changed during lint; rerun acceptance')
            profiles.append({'language': language, 'files': paths, 'fingerprint': before,
                             'errors': sum(item['severity'] == 'error' for item in findings),
                             'warnings': sum(item['severity'] == 'warning' for item in findings),
                             'findings': findings})
        except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
            errors.append(f'{language}: {error}')
    status = 'failed' if errors or any(profile['errors'] for profile in profiles) else 'passed'
    summary = {'status': status, 'profiles': profiles, 'errors': errors,
               'python_rules': ['E9', 'F'], 'python_warning_rules': sorted(PYTHON_ADVISORIES),
               'javascript_config': 'existing Client/package.json react-app + react-app/jest',
               'versions': {'ruff': RUFF_VERSION, 'eslint': ESLINT_VERSION}}
    (results / 'lint-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    for profile in profiles:
        print(f'{profile["language"]}: {len(profile["files"])} critical files; '
              f'{profile["errors"]} errors, {profile["warnings"]} advisory warnings')
    for error in errors:
        print(error)
    return int(status == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
