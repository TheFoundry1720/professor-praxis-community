import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_skill', ROOT / 'install_skill.py') if (ROOT / 'install_skill.py').exists() else None
installer = importlib.util.module_from_spec(spec) if spec else None
if spec:
    spec.loader.exec_module(installer)

def package(source):
    """API fixtures require the full canonical package, not SKILL alone."""
    source.mkdir(parents=True)
    for relative in installer.MANIFEST:
        entry = source / relative
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text('synthetic package file\n', encoding='utf-8')
    return source

class InstallTests(unittest.TestCase):
    def test_install_copies_only_skill_into_explicit_home(self):
        self.assertIsNotNone(installer, 'explicit-home skill installer is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'release/skills/professor-praxis'
            package(source)
            (source / 'SKILL.md').write_text('---\nname: professor-praxis\ndescription: Test skill.\n---\nTest body.\n', encoding='utf-8')
            (source / 'scripts/praxis_engine.py').write_text('print("synthetic")\n', encoding='utf-8')
            (source / 'scripts/__pycache__').mkdir()
            (source / 'scripts/__pycache__/private.pyc').write_bytes(b'not-source')
            (root / 'release/private.txt').write_text('must not install', encoding='utf-8')
            home = root / 'chosen-home'
            result = installer.install(home, source=source)
            target = home / 'skills/professor-praxis'
            self.assertEqual(Path(result['installed_to']), target)
            self.assertTrue((target / 'SKILL.md').is_file())
            self.assertEqual((target / 'scripts/praxis_engine.py').read_text(), 'print("synthetic")\n')
            self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}, set(installer.MANIFEST) | {'.praxis-install-origin.json'})
            import json
            self.assertEqual(json.loads((target / '.praxis-install-origin.json').read_text()), {
                'schema_version': 1, 'source_release': str(root / 'release'), 'installed_skill': str(target)})
            self.assertFalse((source / '.praxis-install-origin.json').exists())
            self.assertFalse((target / 'scripts/__pycache__').exists())
            self.assertFalse((home / 'private.txt').exists())
            self.assertFalse((home / 'config.yaml').exists())

    def test_existing_skill_is_not_overwritten(self):
        self.assertIsNotNone(installer)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            package(source)
            (source / 'SKILL.md').write_text('test source', encoding='utf-8')
            target = root / 'home/skills/professor-praxis'
            target.mkdir(parents=True)
            marker = target / 'keep.md'
            marker.write_text('existing user skill', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                installer.install(root / 'home', source=source)
            self.assertEqual(marker.read_text(), 'existing user skill')
            self.assertFalse((target / 'SKILL.md').exists())

    def test_existing_lock_is_preserved_and_blocks_installation(self):
        self.assertIsNotNone(installer)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            package(source)
            (source / 'SKILL.md').write_text('test source', encoding='utf-8')
            parent = root / 'home/skills'
            parent.mkdir(parents=True)
            lock = parent / '.professor-praxis-install.lock'
            lock.write_text('another installation', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'busy'):
                installer.install(root / 'home', source=source)
            self.assertEqual(lock.read_text(), 'another installation')
            self.assertFalse((parent / 'professor-praxis').exists())

    def test_unexpected_source_data_is_rejected_before_destination_write(self):
        self.assertIsNotNone(installer)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            package(source)
            (source / 'SKILL.md').write_text('test source', encoding='utf-8')
            (source / '.env').write_text('SYNTHETIC forbidden file', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'non-source'):
                installer.install(root / 'home', source=source)
            self.assertFalse((root / 'home').exists())

if __name__ == '__main__':
    unittest.main()
