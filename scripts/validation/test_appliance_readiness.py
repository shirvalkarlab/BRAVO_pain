"""Exercise the real appliance CLI against synthetic external-command replies."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ApplianceReadinessTests(unittest.TestCase):
    def check_page(self, page):
        with tempfile.TemporaryDirectory(prefix="bravo-readiness-") as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts/bravo-appliance", root / "scripts/bravo-appliance")
            (root / ".env.appliance").write_text("BRAVO_HTTP_PORT=8080\n")
            (root / "page.html").write_text(page)
            commands = root / "bin"
            commands.mkdir()
            (commands / "docker").write_text(
                '#!/bin/sh\ncase "$*" in *"port bravo-server 80"*) echo 127.0.0.1:8080;; esac\n'
            )
            (commands / "curl").write_text(
                '#!/bin/sh\ncase "$*" in\n'
                '  *"/healthz"*) echo healthy;;\n'
                '  *"/index"*) cat "$FIXTURE_PAGE";;\n'
                '  *) printf 200;;\nesac\n'
            )
            for command in commands.iterdir():
                command.chmod(0o755)
            return subprocess.run(
                ["bash", str(root / "scripts/bravo-appliance"), "check"],
                env={**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                     "FIXTURE_PAGE": str(root / "page.html")},
                text=True, capture_output=True, timeout=10, check=False,
            )

    def test_legacy_error_page_with_correct_title_is_not_ready(self):
        page = (ROOT / "BRAVO/Server/templates/404.html").read_text()
        result = self.check_page(page)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not return the BRAVO client bundle", result.stderr)

    def test_client_bundle_is_ready(self):
        result = self.check_page(
            '<title>UF BRAVO Platform</title><div id="root"></div>'
            '<script src="/static/js/main.synthetic.js"></script>'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("localhost checks passed", result.stdout)

    def test_each_client_marker_is_required(self):
        for fragment in ('<div id="root"></div>', '<script src="/static/js/main.js"></script>'):
            with self.subTest(fragment=fragment):
                result = self.check_page('<title>UF BRAVO Platform</title>' + fragment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("did not return the BRAVO client bundle", result.stderr)


if __name__ == "__main__":
    unittest.main()
