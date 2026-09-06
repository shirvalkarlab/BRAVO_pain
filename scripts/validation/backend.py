"""Run portable tests against disposable SQLite/storage, with whole-tree coverage.

The container must have networking disabled and only the source mount. Private
appliance data/model acceptance is separate; tests never contact deployed services.
Isolated loopback component fixtures publish no host ports.
"""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path('/workspace/BRAVO')
if (ROOT / '.env').exists():
    raise SystemExit('Refusing a backend .env: portable tests must not load deployment secrets')
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.update(
    DJANGO_SETTINGS_MODULE='BRAVO.settings',
    DJANGO_SECRET_KEY='synthetic-validation-not-a-deployment-key',
    DATASERVER_ENCRYPTION=base64.urlsafe_b64encode(b'0' * 32).decode(),
    DATASERVER_HASHKEY='synthetic-only',
    DJANGO_MODE='DEBUG',
    OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
    FIBIT_CLIENT_ID='', FIBIT_CLIENT_SECRET='',
    GoogleHealth_CLIENT_ID='', GoogleHealth_CLIENT_SECRET='', GoogleHealth_CLIENT_REDIRECT_URI='',
)
os.environ.pop('BRAVO_RUN_LIVE_SOURCE_TESTS', None)
from coverage_gate import CONTRACT, discover, source_fingerprint
initial_fingerprint = source_fingerprint(Path('/workspace'), 'python')

with tempfile.TemporaryDirectory(prefix='bravo-validation-') as storage:
    os.environ['DATASERVER_PATH'] = storage + '/'
    # Start before importing Django/project code; unimported source files also
    # appear through source= below. Percentages from statements are never used.
    import coverage
    collector = coverage.Coverage(branch=True, source=['modules', 'Server', 'BRAVO'],
                                  config_file=False, data_file='/results/.coverage')
    collector.set_option('report:include_namespace_packages', True)
    collector.start()
    from django.conf import settings
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
    settings.LOGGING_CONFIG = None
    import django
    django.setup()
    from django.test.runner import DiscoverRunner
    runner = DiscoverRunner(verbosity=0, interactive=False)
    runner.setup_test_environment()
    databases = runner.setup_databases()
    try:
        import pytest
        test_paths = sys.argv[1:] or [
            'Server', 'modules/Biomarkers/tests', 'modules/StimOptimizer/tests',
            'modules/ClosedLoopDeployment/tests', 'tests']
        result = int(pytest.main([
            '-q', '-ra', '--durations=10', '--disable-warnings', '-p', 'no:cacheprovider',
            # Include Django's historical filename without mixing a directory
            # and its child file, which narrows pytest's collection selection.
            '-o', 'python_files=test_*.py *_test.py tests.py',
        ] + test_paths))
    finally:
        runner.teardown_databases(databases)
        runner.teardown_test_environment()
        collector.stop()
        profile = json.loads(CONTRACT.read_text())['python']
        sources, _ = discover(Path('/workspace'), profile)
        collector.get_data().touch_files([str(Path('/workspace') / path) for path in sources])
        collector.save()
    # A fresh diagnostic report is useful even on failure. Its status remains
    # failed and cannot pass the gate; stale reports were removed by the caller.
    collector.json_report(outfile='/results/python.json')
    # Normalize the container's backend-relative paths to repository-relative.
    target = Path('/results/python.json')
    report = json.loads(target.read_text())
    report['files'] = {'BRAVO/' + name: value for name, value in report['files'].items()}
    target.write_text(json.dumps(report))
    # Fingerprint the exact mounted source after successful execution. The host
    # checker rejects stale source/report pairs instead of trusting an old green.
    if source_fingerprint(Path('/workspace'), 'python') != initial_fingerprint:
        raise SystemExit('Source changed while tests ran; rerun validation')
    Path('/results/backend-status.json').write_text(json.dumps({
        'status': ('diagnostic' if sys.argv[1:] else 'passed') if result == 0 else 'failed',
        'fingerprint': initial_fingerprint,
        'coverage_version': coverage.__version__, 'tests': 'portable only',
    }))
    raise SystemExit(result)
