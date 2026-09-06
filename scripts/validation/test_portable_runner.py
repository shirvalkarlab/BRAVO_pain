"""Exercise the actual shell runner without Docker or deployment credentials."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PortableRunnerTests(unittest.TestCase):
    def run_backend(self, legacy_config):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            source = Path(__file__).resolve().parents[1] / 'bravo-validate'
            shutil.copy2(source, root / 'scripts/bravo-validate')
            (root / 'BRAVO').mkdir()
            requirements = root / 'BRAVO/requirements.txt'
            requirements.write_text('synthetic requirement\n')
            if legacy_config:
                (root / 'BRAVO/mysql.config').write_text('synthetic-secret-must-stay-private')
            binary = root / 'bin'
            binary.mkdir()
            docker = binary / 'docker'
            docker.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if '--entrypoint' in sys.argv:
    print(os.environ['TEST_REQUIREMENTS_SHA'] + '  requirements.txt')
elif sys.argv[1:3] != ['image', 'inspect']:
    Path(os.environ['TEST_DOCKER_ARGS']).write_text(json.dumps(sys.argv[1:]))
''')
            docker.chmod(0o755)
            args_file = root / 'args.json'
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                       TEST_REQUIREMENTS_SHA=hashlib.sha256(requirements.read_bytes()).hexdigest(),
                       TEST_DOCKER_ARGS=str(args_file))
            subprocess.run(['bash', str(root / 'scripts/bravo-validate'), 'backend'],
                           env=env, check=True, capture_output=True, text=True)
            args = json.loads(args_file.read_text())
            self.assertIn('--network', args)
            self.assertEqual(args[args.index('--network') + 1], 'none')
            self.assertIn(str(root / 'BRAVO') + ':/workspace/BRAVO:ro', args)
            mysql = [arg for arg in args if ':/workspace/BRAVO/mysql.config' in arg]
            if legacy_config:
                self.assertEqual(len(mysql), 1)
                mounted = Path(mysql[0].split(':/workspace')[0])
                self.assertEqual(mounted.read_bytes(), b'')
                self.assertNotEqual(mounted, root / 'BRAVO/mysql.config')
            else:
                self.assertEqual(mysql, [])
                self.assertFalse((root / 'BRAVO/mysql.config').exists())

    def test_clean_checkout_needs_no_mysql_mountpoint(self):
        self.run_backend(False)

    def test_legacy_config_is_hidden_by_empty_overlay(self):
        self.run_backend(True)
