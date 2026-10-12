"""Isolated link-scope regressions; never use a real profile or notes tree."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from test_install import installer


class InstallLinkTests(unittest.TestCase):
    def source(self, root):
        source = root / 'source'
        source.mkdir()
        shipped = installer.ROOT / 'skills/professor-praxis'
        for relative in ('SKILL.md', 'LICENSE.md', 'references/record-contract.md',
                         'references/metadata-record.json', 'scripts/praxis_engine.py',
                         'scripts/praxis_cli.py', 'scripts/dashboard.html'):
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((shipped / relative).read_bytes())
        return source

    def link(self, link, target, *, symlink=False):
        if os.name == 'nt' and not symlink:
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest('symlink unavailable: ' + str(error))

    def destination_case(self, placement, *, symlink=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(root)
            outside = root / 'outside'
            outside.mkdir()
            marker = outside / 'keep.md'
            marker.write_text('synthetic existing target', encoding='utf-8')
            home = root / 'home'
            if placement == 'home':
                link = home
            elif placement == 'ancestor':
                link = root / 'ancestor'
                home = link / 'new/home'
            elif placement == 'skills':
                home.mkdir()
                link = home / 'skills'
            else:
                (home / 'skills').mkdir(parents=True)
                link = home / 'skills/professor-praxis'
            self.link(link, outside, symlink=symlink)
            try:
                with self.assertRaises(ValueError):
                    installer.install(home, source=source)
                self.assertEqual(sorted(p.name for p in outside.iterdir()), ['keep.md'])
                self.assertEqual(marker.read_text(), 'synthetic existing target')
            finally:
                # Remove only the isolated link, never its target contents.
                if link.is_junction():
                    link.rmdir()
                else:
                    link.unlink()

    def test_home_junction_refused(self):
        self.destination_case('home')

    def test_destination_ancestor_junction_refused_before_mkdir(self):
        self.destination_case('ancestor')

    def test_skills_junction_refused(self):
        self.destination_case('skills')

    def test_existing_target_junction_preserved(self):
        self.destination_case('target')

    def test_home_symlink_refused(self):
        self.destination_case('home', symlink=True)

    def test_destination_ancestor_symlink_refused(self):
        self.destination_case('ancestor', symlink=True)

    def source_link_case(self, placement, *, symlink=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(root)
            outside = root / 'outside'
            outside.mkdir()
            marker = outside / 'private-note.md'
            marker.write_text('SYNTHETIC PRIVATE MUST NOT READ', encoding='utf-8')
            original = marker.read_bytes()
            home = root / 'home'
            if placement == 'ancestor':
                link = root / 'linked-root'
                self.link(link, root, symlink=symlink)
                selected = link / 'source'
            elif placement == 'source':
                link = root / 'linked-source'
                self.link(link, source, symlink=symlink)
                selected = link
            else:
                link = source / 'references/private-notes'
                self.link(link, outside, symlink=symlink)
                selected = source
            copyfile = installer.shutil.copyfile

            def guarded_copy(src, dst, **kwargs):
                self.assertNotEqual(Path(src).name, 'private-note.md', 'external note read attempted')
                return copyfile(src, dst, **kwargs)

            try:
                with mock.patch.object(installer.shutil, 'copyfile', side_effect=guarded_copy):
                    with self.assertRaises(ValueError):
                        installer.install(home, source=selected)
                self.assertFalse(home.exists(), 'source rejected before destination creation')
                self.assertEqual(marker.read_bytes(), original)
            finally:
                if link.is_junction():
                    link.rmdir()
                else:
                    link.unlink()

    def test_source_junction_refused_before_copy(self):
        self.source_link_case('source')

    def test_source_ancestor_junction_refused_before_copy(self):
        self.source_link_case('ancestor')

    def test_source_descendant_junction_never_reads_external_note(self):
        self.source_link_case('descendant')

    def test_source_descendant_symlink_refused(self):
        self.source_link_case('descendant', symlink=True)

    def test_nonmanifest_markdown_refused_before_destination_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(root)
            (source / 'private-note.md').write_text('synthetic private note', encoding='utf-8')
            with self.assertRaises(ValueError):
                installer.install(root / 'home', source=source)
            self.assertFalse((root / 'home').exists())

    def test_partial_source_is_not_an_installable_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(root)
            (source / 'scripts/dashboard.html').unlink()
            with self.assertRaises(ValueError):
                installer.install(root / 'home', source=source)
            self.assertFalse((root / 'home').exists())

    def test_copy_failure_cleans_only_own_stage_and_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(root)
            home = root / 'home'
            parent = home / 'skills'
            parent.mkdir(parents=True)
            marker = parent / 'keep.md'
            marker.write_text('existing synthetic user file', encoding='utf-8')
            copy = installer.shutil.copy2
            copied = 0

            def failing_copy(src, dst):
                nonlocal copied
                copied += 1
                if copied == 2:
                    raise OSError('injected package copy failure')
                return copy(src, dst)

            with mock.patch.object(installer.shutil, 'copy2', side_effect=failing_copy):
                with self.assertRaisesRegex(OSError, 'injected package'):
                    installer.install(home, source=source)
            self.assertEqual(list(parent.iterdir()), [marker])
            self.assertEqual(marker.read_text(), 'existing synthetic user file')
            installer.install(home, source=source)  # own lock removed; retry works
            self.assertTrue((parent / 'professor-praxis/SKILL.md').is_file())
            self.assertFalse((parent / '.professor-praxis-install.lock').exists())
            self.assertEqual(list(parent.glob('.praxis-install-*')), [])

    def test_source_destination_disjointness_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source(root)
            before = {p.relative_to(source).as_posix(): p.read_bytes()
                      for p in source.rglob('*') if p.is_file()}
            for home in (source, source / 'home', root):
                with self.subTest(home=home), self.assertRaisesRegex(ValueError, 'contain each other'):
                    installer.install(home, source=source)
            self.assertEqual({p.relative_to(source).as_posix(): p.read_bytes()
                              for p in source.rglob('*') if p.is_file()}, before)
            self.assertFalse((root / 'skills').exists())
            self.assertFalse((source / 'home').exists())
