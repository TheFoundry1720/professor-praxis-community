"""Isolated source/install boundary regressions; never use live user data."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_install import installer

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'skills/professor-praxis/scripts/praxis_cli.py'
ORIGIN = '.praxis-install-origin.json'


def release(root):
    source = root / 'release/skills/professor-praxis'
    for relative in installer.MANIFEST:
        entry = source / relative
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_bytes((ROOT / 'skills/professor-praxis' / relative).read_bytes())
    for name in ('install_skill.py', 'README.md', 'LICENSE.md'):
        (root / 'release' / name).write_bytes((ROOT / name).read_bytes())
    return source


def init(cli, workspace, notes):
    return subprocess.run([sys.executable, '-B', str(cli), 'init', '--workspace',
                           str(workspace), '--notes-root', str(notes), '--vault-name',
                           'SYNTHETIC'], capture_output=True, text=True)


class ReleaseBoundaryTests(unittest.TestCase):
    def test_externally_installed_cli_rejects_both_source_roots_before_writes(self):
        for inside in ('workspace', 'notes'):
            with self.subTest(inside=inside), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = release(root)
                boundary = root / 'release'
                installer.install(root / 'home', source=source)
                cli = root / 'home/skills/professor-praxis/scripts/praxis_cli.py'
                workspace = (boundary if inside == 'workspace' else root) / 'workspace'
                notes = (boundary if inside == 'notes' else root) / 'notes'
                before = {p.relative_to(boundary).as_posix(): p.read_bytes()
                          for p in boundary.rglob('*') if p.is_file()}
                result = init(cli, workspace, notes)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('release', result.stdout)
                self.assertFalse(workspace.exists(), 'reject before workspace/lock creation')
                self.assertFalse(notes.exists(), 'reject before notes creation')
                self.assertEqual(before, {p.relative_to(boundary).as_posix(): p.read_bytes()
                                         for p in boundary.rglob('*') if p.is_file()})

    def test_source_release_destination_overlap_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = release(root)
            for home in (root / 'release', root / 'release/local-home'):
                with self.subTest(home=home), self.assertRaisesRegex(ValueError, 'source.*destination'):
                    installer.install(home, source=source)
            self.assertFalse((root / 'release/local-home').exists())
            self.assertFalse((root / 'release/skills/professor-praxis' / ORIGIN).exists())

    def test_known_other_release_ancestor_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = release(root)
            installer.install(root / 'home', source=source)
            other = root / 'other'
            other.mkdir()
            moved = release(other).parent.parent
            cli = root / 'home/skills/professor-praxis/scripts/praxis_cli.py'
            result = init(cli, root / 'workspace', moved / 'notes')
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn('release', result.stdout)
            self.assertFalse((root / 'workspace').exists())
            self.assertFalse((moved / 'notes').exists())

    def test_config_scope_is_checked_before_workspace_lock_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = release(root)
            installer.install(root / 'home', source=source)
            cli = root / 'home/skills/professor-praxis/scripts/praxis_cli.py'
            workspace, notes = root / 'workspace', root / 'notes'
            self.assertEqual(init(cli, workspace, notes).returncode, 0)
            cfg = workspace / 'config.json'
            value = json.loads(cfg.read_text())
            value['notes_root'] = str(root / 'release')
            cfg.write_text(json.dumps(value), encoding='utf-8')
            lock = workspace / '.praxis.lock'
            lock.write_text('SYNTHETIC HELD LOCK', encoding='utf-8')
            result = subprocess.run([sys.executable, '-B', str(cli), 'refresh', '--workspace', str(workspace)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('release', result.stdout, 'scope validation must precede even lock creation')
            self.assertEqual(lock.read_text(), 'SYNTHETIC HELD LOCK')

    def test_origin_remains_lexical_after_release_move_or_removal(self):
        for removed in (False, True):
            for inside in ('workspace', 'notes'):
                with self.subTest(removed=removed, inside=inside), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    source = release(root)
                    boundary = root / 'release'
                    installer.install(root / 'home', source=source)
                    if removed:
                        shutil.rmtree(boundary)  # only this test's synthetic copy
                    else:
                        boundary.rename(root / 'moved-release')
                    boundary.mkdir()  # reuse the old lexical location
                    workspace = (boundary if inside == 'workspace' else root) / 'workspace'
                    notes = (boundary if inside == 'notes' else root) / 'notes'
                    cli = root / 'home/skills/professor-praxis/scripts/praxis_cli.py'
                    result = init(cli, workspace, notes)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn('release', result.stdout)
                    self.assertFalse(workspace.exists())
                    self.assertFalse(notes.exists())
                    # Ordinary private locations still work with an absent origin.
                    self.assertEqual(init(cli, root / 'normal-workspace', root / 'normal-notes').returncode, 0)

    def test_missing_or_malformed_origin_refuses_external_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            installer.install(root / 'home', source=release(root))
            skill = root / 'home/skills/professor-praxis'
            origin, cli = skill / ORIGIN, skill / 'scripts/praxis_cli.py'
            original = json.loads(origin.read_text())
            variants = [None, '{', '[]', json.dumps(original | {'extra': True}),
                        json.dumps(original | {'schema_version': True}),
                        json.dumps(original | {'source_release': 'relative'}),
                        json.dumps(original | {'source_release': str(root / 'a/../release')}),
                        json.dumps(original | {'source_release': []}),
                        json.dumps(original | {'source_release': str(skill)}),
                        json.dumps(original | {'installed_skill': str(root / 'other')}),
                        json.dumps(original).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')]
            for value in variants:
                if value is None:
                    origin.unlink()
                else:
                    origin.write_text(value, encoding='utf-8')
                with self.subTest(value=value):
                    result = init(cli, root / 'workspace', root / 'notes')
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertFalse((root / 'workspace').exists())
                    self.assertFalse((root / 'notes').exists())

    def test_linked_installed_scripts_cannot_hide_execution_scope(self):
        from test_install_links import InstallLinkTests
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            installer.install(root / 'home', source=release(root))
            skill = root / 'home/skills/professor-praxis'
            scripts = skill / 'scripts'
            moved = root / 'moved-scripts'
            scripts.rename(moved)
            InstallLinkTests.link(self, scripts, moved)
            try:
                result = init(scripts / 'praxis_cli.py', root / 'workspace', root / 'notes')
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse((root / 'workspace').exists())
                self.assertFalse((root / 'notes').exists())
            finally:
                scripts.rmdir() if scripts.is_junction() else scripts.unlink()

    def test_origin_junction_and_linked_source_path_are_refused(self):
        from test_install_links import InstallLinkTests
        for linked in ('origin', 'source'):
            with self.subTest(linked=linked), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                installer.install(root / 'home', source=release(root))
                skill = root / 'home/skills/professor-praxis'
                origin = skill / ORIGIN
                outside = root / 'outside'
                outside.mkdir()
                marker = outside / 'keep.md'
                marker.write_text('SYNTHETIC DO NOT READ', encoding='utf-8')
                if linked == 'origin':
                    origin.unlink()
                    link = origin
                else:
                    link = root / 'linked-source'
                    metadata = json.loads(origin.read_text())
                    metadata['source_release'] = str(link)
                    origin.write_text(json.dumps(metadata), encoding='utf-8')
                InstallLinkTests.link(self, link, outside)
                try:
                    result = init(skill / 'scripts/praxis_cli.py', root / 'workspace', root / 'notes')
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn('scope', result.stdout)
                    self.assertFalse((root / 'workspace').exists())
                    self.assertFalse((root / 'notes').exists())
                    self.assertEqual(marker.read_text(), 'SYNTHETIC DO NOT READ')
                    self.assertEqual(list(outside.iterdir()), [marker])
                finally:
                    link.rmdir() if link.is_junction() else link.unlink()

    def test_roots_containing_source_release_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            origin_parent = root / 'source-parent'
            origin_parent.mkdir()
            installer.install(root / 'home', source=release(origin_parent))
            cli = root / 'home/skills/professor-praxis/scripts/praxis_cli.py'
            for inside in ('workspace', 'notes'):
                workspace = origin_parent if inside == 'workspace' else root / 'workspace'
                notes = origin_parent if inside == 'notes' else root / 'notes'
                with self.subTest(inside=inside):
                    result = init(cli, workspace, notes)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn('release', result.stdout)
                    self.assertFalse((origin_parent / 'config.json').exists())
                    self.assertFalse((root / 'workspace').exists())
                    self.assertFalse((root / 'notes').exists())

    def test_fresh_install_has_exact_source_bytes_and_local_only_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = release(root)
            before = {name: (source / name).read_bytes() for name in installer.MANIFEST}
            installer.install(root / 'home', source=source)
            skill = root / 'home/skills/professor-praxis'
            self.assertEqual({p.relative_to(skill).as_posix() for p in skill.rglob('*') if p.is_file()}, set(installer.MANIFEST) | {ORIGIN})
            self.assertEqual(before, {name: (skill / name).read_bytes() for name in installer.MANIFEST})
            self.assertFalse((source / ORIGIN).exists())
            self.assertEqual(json.loads((skill / ORIGIN).read_text()), {
                'schema_version': 1, 'source_release': str(root / 'release'), 'installed_skill': str(skill)})
            # An installed/local metadata file must never become package input.
            with self.assertRaisesRegex(ValueError, 'non-source'):
                installer.install(root / 'another-home', source=skill)
            self.assertFalse((root / 'another-home').exists())
            result = init(skill / 'scripts/praxis_cli.py', root / 'workspace', root / 'notes')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['counts']['sources'], 0)

    def test_direct_source_cli_rejects_notes_inside_source_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = release(root)
            workspace, notes = root / 'workspace', root / 'release/notes'
            result = init(source / 'scripts/praxis_cli.py', workspace, notes)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertFalse(workspace.exists())
            self.assertFalse(notes.exists())


if __name__ == '__main__':
    unittest.main()
