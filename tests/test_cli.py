"""CLI acceptance tests use only isolated synthetic workspaces."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'skills/professor-praxis/scripts/praxis_cli.py'


def record():
    return {'id': 'article:synthetic', 'realm': 'personal', 'kind': 'article', 'title': 'Synthetic learning source', 'author': 'Example author', 'url': 'https://example.org/learning', 'captured_at': '2026-01-01T12:00:00+00:00', 'duration_minutes': 80, 'coverage': 'full_text', 'source_text': 'Shared useful idea. Alpha reads files.', 'summary': ['Shared useful idea.'], 'ideas': ['Shared useful idea.'], 'tools': [], 'note_path': None, 'assessment': {'recommendation': 'Read', 'value': 'moderate', 'confidence': 'medium', 'rationale': 'Source text retained.', 'time_guidance': 'Read the overview.', 'reviewed_at': '2026-01-02T12:00:00+00:00', 'novelty': [{'idea': 'Shared useful idea.', 'bucket': 'new', 'evidence': 'Shared useful idea.', 'compared_with': [], 'prior_evidence': 'Not found in recorded library; not proof of ignorance.'}], 'credibility': {'topic': 'Files', 'judgment': 'Unknown', 'comparison': 'Unknown', 'unknowns': ['Not independently verified.'], 'established': False, 'comparison_established': False, 'compared_sources': [], 'evidence': []}}}


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.notes = self.root / 'notes'
        self.input = self.root / 'assessment.json'

    def call(self, command, *args, ok=True):
        self.assertTrue(CLI.is_file(), 'portable CLI is not implemented')
        result = subprocess.run([sys.executable, '-B', str(CLI), command, *map(str, args)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def init(self, **options):
        return self.call('init', '--workspace', self.workspace, '--notes-root', self.notes, '--vault-name', 'Synthetic vault', **options)

    def write_record(self, value=None):
        self.input.write_text(json.dumps(value or record()), encoding='utf-8')
        return self.input

    def test_save_validate_compare_and_render_grounded_source(self):
        self.init()
        self.write_record()
        self.assertTrue(self.call('validate', '--record', self.input, '--realm', 'personal')['valid'])
        saved = self.call('save', '--workspace', self.workspace, '--record', self.input)
        self.assertEqual(saved['source_id'], record()['id'])
        self.assertEqual(self.call('status', '--workspace', self.workspace)['counts']['sources'], 1)
        self.assertEqual(json.loads(Path(saved['path']).read_text())['source_text'], record()['source_text'])
        refreshed = self.call('refresh', '--workspace', self.workspace)
        self.assertEqual(refreshed['counts']['assessed'], 1)
        html = (self.workspace / 'dashboard/index.html').read_text(encoding='utf-8')
        self.assertIn('Synthetic learning source', html)
        self.assertNotIn('%%PRAXIS_DATA%%', html)
        candidate = record()
        candidate['id'] = 'article:candidate'
        self.write_record(candidate)
        comparison = self.call('compare', '--workspace', self.workspace, '--record', self.input)
        self.assertEqual(comparison['candidates'][0]['source_id'], record()['id'])
        self.assertIn('Lexical', comparison['limits'])
        self.assertEqual(list(self.notes.iterdir()), [])
        self.assertTrue(self.call('refresh', '--workspace', self.workspace)['unchanged'])

    def test_init_creates_explicit_empty_workspace_and_is_idempotent(self):
        result = self.init()
        self.assertEqual(result['counts']['sources'], 0)
        self.assertTrue(self.notes.is_dir())
        output = self.workspace / 'dashboard/index.html'
        self.assertTrue(output.is_file())
        before = (output.read_bytes(), output.stat().st_mtime_ns, (self.workspace / 'config.json').read_bytes())
        self.assertTrue(self.init()['unchanged'])
        self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns, (self.workspace / 'config.json').read_bytes()), before)
        self.assertEqual(self.call('status', '--workspace', self.workspace)['counts']['sources'], 0)
        self.assertEqual(list((self.workspace / 'learning/personal/praxis/assessments').iterdir()), [])

    def test_init_refuses_incompatible_or_unapproved_roots_without_writes(self):
        self.workspace.mkdir()
        marker = self.workspace / 'unrelated.txt'
        marker.write_text('Do not alter', encoding='utf-8')
        self.init(ok=False)
        self.assertEqual(list(self.workspace.iterdir()), [marker])
        self.assertFalse(self.notes.exists())
        marker.unlink()
        self.init()
        before = (self.workspace / 'config.json').read_bytes()
        self.call('init', '--workspace', self.workspace, '--notes-root', self.root / 'different', '--vault-name', 'Synthetic vault', ok=False)
        self.assertEqual((self.workspace / 'config.json').read_bytes(), before)
        self.assertFalse((self.root / 'different').exists())
        self.call('init', '--workspace', self.root / 'new', '--notes-root', self.root / 'new/nested', '--vault-name', 'Synthetic vault', ok=False)
        self.assertFalse((self.root / 'new').exists())
        self.call('init', '--workspace', '.', '--notes-root', self.notes, '--vault-name', 'Synthetic vault', ok=False)
        self.call('init', '--workspace', self.root / '../escape', '--notes-root', self.notes, '--vault-name', 'Synthetic vault', ok=False)

    def test_workspace_lock_fails_closed_for_all_operations(self):
        self.init()
        self.write_record()
        lock = self.workspace / '.praxis.lock'
        lock.write_text('held', encoding='utf-8')
        before = (self.workspace / 'dashboard/index.html').read_bytes()
        for command in ('save', 'refresh', 'status', 'compare'):
            with self.subTest(command=command):
                args = ['--workspace', self.workspace]
                if command in ('save', 'compare'):
                    args += ['--record', self.input]
                self.assertIn('lock', self.call(command, *args, ok=False)['error'])
        self.assertIn('lock', self.init(ok=False)['error'])
        self.assertEqual(lock.read_text(), 'held')
        self.assertEqual((self.workspace / 'dashboard/index.html').read_bytes(), before)
        self.assertEqual(list((self.workspace / 'learning/personal/praxis/assessments').iterdir()), [])

    def test_invalid_library_cannot_be_repaired_by_save_or_refresh(self):
        self.init()
        self.write_record()
        saved = self.call('save', '--workspace', self.workspace, '--record', self.input)
        self.call('refresh', '--workspace', self.workspace)
        output = self.workspace / 'dashboard/index.html'
        watermark = output.with_name(output.name + '.watermark.json')
        before = (output.read_bytes(), watermark.read_bytes(), Path(saved['path']).read_bytes())
        store = Path(saved['path']).parent
        duplicate = store / 'duplicate.json'
        for invalid in (json.dumps(record()), '{', '[]'):
            duplicate.write_text(invalid, encoding='utf-8')
            for command in ('save', 'refresh', 'compare', 'status'):
                with self.subTest(invalid=invalid, command=command):
                    args = ['--workspace', self.workspace]
                    if command in ('save', 'compare'):
                        args += ['--record', self.input]
                    self.call(command, *args, ok=False)
            self.assertEqual((output.read_bytes(), watermark.read_bytes(), Path(saved['path']).read_bytes()), before)
        duplicate.unlink()
        log = self.workspace / 'learning/personal/log.jsonl'
        log.write_text('', encoding='utf-8')
        self.assertIn('legacy', self.call('refresh', '--workspace', self.workspace, ok=False)['error'])
        self.assertEqual((output.read_bytes(), watermark.read_bytes(), Path(saved['path']).read_bytes()), before)

    def test_save_preserves_stable_identity_and_review_chronology(self):
        self.init()
        self.write_record()
        saved = self.call('save', '--workspace', self.workspace, '--record', self.input)
        path = Path(saved['path'])
        before = path.read_bytes()
        for key, value in (('url', 'https://example.org/other'), ('kind', 'video'), ('title', 'Other title'), ('author', 'Other author'), ('captured_at', '2026-01-01T11:00:00+00:00'), ('note_path', str(self.notes / 'other.md')), ('action_state', 'applied')):
            candidate = record()
            candidate[key] = value
            self.write_record(candidate)
            with self.subTest(key=key):
                self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
                self.assertEqual(path.read_bytes(), before)
        candidate = record()
        candidate['assessment']['reviewed_at'] = '2026-01-01T13:00:00+00:00'
        self.write_record(candidate)
        self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
        self.assertEqual(path.read_bytes(), before)
        candidate = record()
        candidate['assessment']['rationale'] = 'Updated grounded rationale.'
        candidate['assessment']['reviewed_at'] = '2026-01-03T12:00:00+00:00'
        self.write_record(candidate)
        self.assertEqual(self.call('save', '--workspace', self.workspace, '--record', self.input)['path'], str(path))
        self.assertEqual(json.loads(path.read_text())['captured_at'], record()['captured_at'])

    def link_directory(self, link, target):
        if os.name == 'nt':
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_junction_roots_and_workspace_descendants_are_rejected(self):
        import shutil
        outside = self.root / 'outside'
        outside.mkdir()
        sentinel = outside / 'sentinel.md'
        sentinel.write_text('Do not read or overwrite', encoding='utf-8')
        self.link_directory(self.workspace, outside)
        self.init(ok=False)
        self.assertEqual(list(outside.iterdir()), [sentinel])
        self.workspace.rmdir() if os.name == 'nt' else self.workspace.unlink()
        self.link_directory(self.notes, outside)
        self.init(ok=False)
        self.assertFalse(self.workspace.exists())
        self.notes.rmdir() if os.name == 'nt' else self.notes.unlink()
        for boundary in ('learning', 'learning/personal', 'learning/personal/praxis/assessments', 'dashboard'):
            with self.subTest(boundary=boundary):
                self.init()
                link = self.workspace / boundary
                shutil.rmtree(link)
                self.link_directory(link, outside)
                self.write_record()
                self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
                self.call('refresh', '--workspace', self.workspace, ok=False)
                self.assertEqual(list(outside.iterdir()), [sentinel])
                link.rmdir() if os.name == 'nt' else link.unlink()
                shutil.rmtree(self.workspace)

    def test_config_corruption_or_missing_store_is_not_an_empty_library(self):
        self.init()
        cfg_path = self.workspace / 'config.json'
        original = cfg_path.read_bytes()
        base = json.loads(original)
        variants = [base | {'workspace': str(self.root / 'other')}, base | {'schema_version': True}, base | {'realm': 'other'}, base | {'notes_root': str(self.root / 'absent')}, base | {'extra': 'unsupported'}, [], {'realm': 'personal'}]
        output = self.workspace / 'dashboard/index.html'
        watermark = output.with_name(output.name + '.watermark.json')
        before = (output.read_bytes(), watermark.read_bytes())
        for value in variants:
            cfg_path.write_text(json.dumps(value), encoding='utf-8')
            with self.subTest(value=value):
                self.call('refresh', '--workspace', self.workspace, ok=False)
                self.assertEqual((output.read_bytes(), watermark.read_bytes()), before)
        cfg_path.write_bytes(original)
        store = self.workspace / 'learning/personal/praxis/assessments'
        store.rmdir()
        self.call('refresh', '--workspace', self.workspace, ok=False)
        self.assertEqual((output.read_bytes(), watermark.read_bytes()), before)

    def test_save_rejects_consumption_mastery_and_unsupported_record_fields(self):
        self.init()
        candidates = []
        for key in ('consumed', 'mastery', 'learned', 'extra'):
            candidate = record()
            candidate[key] = True
            candidates.append(candidate)
        for branch in ('assessment', 'credibility', 'novelty'):
            candidate = record()
            target = candidate['assessment'] if branch == 'assessment' else candidate['assessment'][branch] if branch == 'credibility' else candidate['assessment']['novelty'][0]
            target['mastery'] = 'invented'
            candidates.append(candidate)
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.write_record(candidate)
                self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
        self.assertEqual(list((self.workspace / 'learning/personal/praxis/assessments').iterdir()), [])

    def test_noncanonical_assessment_filename_cannot_create_duplicate_on_update(self):
        self.init()
        self.write_record()
        saved = self.call('save', '--workspace', self.workspace, '--record', self.input)
        canonical = Path(saved['path'])
        renamed = canonical.with_name('manual.json')
        canonical.rename(renamed)
        before = renamed.read_bytes()
        self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
        self.assertFalse(canonical.exists())
        self.assertEqual(renamed.read_bytes(), before)

    def test_duplicate_json_keys_and_nonfinite_values_fail_before_save(self):
        self.init()
        base = json.dumps(record())
        for raw in (base.replace('{', '{"id":"conflicting",', 1), base.replace('"duration_minutes": 80', '"duration_minutes": NaN')):
            self.input.write_text(raw, encoding='utf-8')
            with self.subTest(raw=raw):
                self.call('validate', '--record', self.input, '--realm', 'personal', ok=False)
                self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
        self.assertEqual(list((self.workspace / 'learning/personal/praxis/assessments').iterdir()), [])

    def test_save_checks_cross_source_quotes_against_prior_content_not_metadata(self):
        self.init()
        prior = record()
        prior['id'] = 'article:prior'
        prior['assessment']['reviewed_at'] = '2026-01-01T13:00:00+00:00'
        self.write_record(prior)
        self.call('save', '--workspace', self.workspace, '--record', self.input)
        current = record()
        current['assessment']['novelty'][0].update(bucket='repetition', compared_with=[prior['id']], prior_evidence='Shared useful idea.')
        self.write_record(current)
        saved = self.call('save', '--workspace', self.workspace, '--record', self.input)
        before = Path(saved['path']).read_bytes()
        for quote in ('Fabricated prior evidence.', 'Later note-derived idea.'):
            current['assessment']['novelty'][0]['prior_evidence'] = quote
            self.write_record(current)
            self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
            self.assertEqual(Path(saved['path']).read_bytes(), before)
        current['assessment']['novelty'][0].update(compared_with=['article:missing'], prior_evidence='Shared useful idea.')
        self.write_record(current)
        self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
        self.assertEqual(Path(saved['path']).read_bytes(), before)

    def test_save_reads_only_approved_note_and_never_modifies_it(self):
        self.init()
        note = self.notes / 'approved.md'
        original = '---\nprivate: omit frontmatter\n---\n# Synthetic saved note\n'
        note.write_text(original, encoding='utf-8')
        current = record()
        current['note_path'] = str(note)
        self.write_record(current)
        self.call('save', '--workspace', self.workspace, '--record', self.input)
        self.call('refresh', '--workspace', self.workspace)
        html = (self.workspace / 'dashboard/index.html').read_text(encoding='utf-8')
        self.assertIn('Synthetic saved note', html)
        self.assertNotIn('omit frontmatter', html)
        self.assertEqual(note.read_text(encoding='utf-8'), original)
        current['id'] = 'article:outside'
        outside = self.root / 'outside.md'
        outside.write_text('UNAPPROVED_SECRET', encoding='utf-8')
        current['note_path'] = str(outside)
        self.write_record(current)
        self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
        self.assertEqual((self.workspace / 'dashboard/index.html').read_text(encoding='utf-8'), html)
        self.assertNotIn('UNAPPROVED_SECRET', html)

    def test_scripts_are_self_contained_when_installed_without_repository(self):
        from test_install import installer
        home = self.root / 'isolated-home'
        installer.install(home)
        isolated = home / 'skills/professor-praxis/scripts'
        standalone = isolated / CLI.name
        args = [sys.executable, '-B', str(standalone), 'init', '--workspace', str(self.workspace), '--notes-root', str(self.notes), '--vault-name', 'Synthetic vault', '--realm', 'work']
        result = subprocess.run(args, cwd=self.root, text=True, capture_output=True, env=dict(os.environ, HERMES_HOME=str(self.root / 'must-not-read')))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['sources'], 0)
        current = record()
        current['realm'] = 'work'
        self.write_record(current)
        result = subprocess.run([sys.executable, '-B', str(standalone), 'save', '--workspace', str(self.workspace), '--record', str(self.input)], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run([sys.executable, '-B', str(standalone), 'refresh', '--workspace', str(self.workspace)], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['sources'], 1)
        self.assertEqual(list(isolated.glob('__pycache__')), [])
        self.assertFalse((self.root / 'must-not-read').exists())

    def test_synthetic_ui_fixture_renders_all_source_types(self):
        self.init()
        fixture = json.loads((ROOT / 'tests/ui_fixture.json').read_text(encoding='utf-8'))
        for current in fixture['records']:
            self.write_record(current)
            self.call('save', '--workspace', self.workspace, '--record', self.input)
        result = self.call('refresh', '--workspace', self.workspace)
        self.assertEqual(result['counts']['sources'], 3)
        self.assertEqual(result['counts']['assessed'], 2)
        self.assertEqual(result['counts']['tool_leads'], 2)
        self.assertTrue(self.call('refresh', '--workspace', self.workspace)['unchanged'])

    def test_metadata_capture_can_gain_a_first_approved_note_and_assessment(self):
        self.init()
        captured = record()
        captured.update(coverage='metadata_only', source_text=None, summary=[], ideas=[], assessment=None)
        self.write_record(captured)
        saved = self.call('save', '--workspace', self.workspace, '--record', self.input)
        note = self.notes / 'first-approved-note.md'
        note.write_text('# Synthetic full assessment note', encoding='utf-8')
        assessed = record()
        assessed['note_path'] = str(note)
        self.write_record(assessed)
        updated = self.call('save', '--workspace', self.workspace, '--record', self.input)
        self.assertEqual(updated['path'], saved['path'])
        stored = json.loads(Path(updated['path']).read_text(encoding='utf-8'))
        self.assertEqual(stored['captured_at'], captured['captured_at'])
        self.assertEqual(stored['note_path'], str(note))
        second = self.notes / 'second-note.md'
        second.write_text('# Another note', encoding='utf-8')
        assessed['note_path'] = str(second)
        self.write_record(assessed)
        self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)
        self.assertEqual(json.loads(Path(updated['path']).read_text(encoding='utf-8')), stored)

    def test_malformed_note_paths_fail_before_persistence_and_preserve_last_good(self):
        self.init()
        self.write_record()
        saved = self.call('save', '--workspace', self.workspace, '--record', self.input)
        self.call('refresh', '--workspace', self.workspace)
        path = Path(saved['path'])
        output = self.workspace / 'dashboard/index.html'
        watermark = output.with_name(output.name + '.watermark.json')
        before = (path.read_bytes(), output.read_bytes(), watermark.read_bytes())
        for value in ([], False, 0, '', '  ', {}, 'relative.md', str(self.notes / 'bad.txt')):
            current = record()
            current['note_path'] = value
            self.write_record(current)
            with self.subTest(value=value):
                self.assertIn('note', self.call('validate', '--record', self.input, '--realm', 'personal', ok=False)['error'])
                self.assertIn('note', self.call('save', '--workspace', self.workspace, '--record', self.input, ok=False)['error'])
                self.assertEqual((path.read_bytes(), output.read_bytes(), watermark.read_bytes()), before)
        self.assertEqual(list(self.notes.iterdir()), [])
        self.assertEqual(list(path.parent.iterdir()), [path])
