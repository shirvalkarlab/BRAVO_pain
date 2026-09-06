"""Migration must preserve scientific assets and refuse conflicting copies."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "private_runtime", Path(__file__).resolve().parents[1] / "prepare_private_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class PrivateRuntimeTests(unittest.TestCase):
    def test_preserves_assets_after_legacy_sources_are_absent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "BRAVO/modules/Biomarkers/data/psd_lsb_models/SYNTHETIC.json"
            source.parent.mkdir(parents=True)
            original = b'{"channels": {"synthetic": {"gain": 2.125}}}\n'
            source.write_bytes(original)
            first = runtime.prepare(root)
            self.assertEqual(source.read_bytes(), original)
            copied = root / "secrets/runtime_assets/psd_lsb_models/SYNTHETIC.json"
            self.assertEqual(copied.read_bytes(), original)
            self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
            source.unlink()
            self.assertEqual(runtime.prepare(root), first)

    def test_conflict_leaves_existing_and_source_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "BRAVO/config/policy.csv"
            source.parent.mkdir(parents=True)
            source.write_text('approved\n')
            runtime.prepare(root)
            source.write_text('changed\n')
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                runtime.prepare(root)
            self.assertEqual(source.read_text(), 'changed\n')
            self.assertEqual((root / 'secrets/runtime_assets/config/policy.csv').read_text(), 'approved\n')

    def test_empty_independent_install_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(runtime.prepare(root), [])
            link = root / 'secrets/runtime_assets/config/policy.csv'
            link.symlink_to(root / 'absent')
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                runtime.prepare(root)


if __name__ == '__main__':
    unittest.main()
