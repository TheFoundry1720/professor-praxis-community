import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'skills/professor-praxis/scripts/praxis_engine.py'
spec = importlib.util.spec_from_file_location('praxis_engine', ENGINE) if ENGINE.exists() else None
praxis = importlib.util.module_from_spec(spec) if spec else None
if spec:
    spec.loader.exec_module(praxis)

def work_record():
    return {'id': 'article:test', 'realm': 'work', 'kind': 'article', 'title': 'Synthetic article', 'author': 'Test author', 'url': 'https://example.org/test', 'captured_at': '2026-01-01T12:00:00+00:00', 'duration_minutes': None, 'coverage': 'metadata_only', 'summary': [], 'ideas': [], 'tools': [], 'assessment': None, 'note_path': None}

class PortableEngineTests(unittest.TestCase):
    def test_explicit_work_realm_metadata_is_honestly_unknown(self):
        self.assertIsNotNone(praxis, 'portable engine is not implemented')
        self.assertEqual(praxis.validate_record(work_record(), 'work')['coverage'], 'metadata_only')
        snap = praxis.build_snapshot([work_record()], ROOT, 'Synthetic vault', '2026-01-02T12:00:00+00:00', 'work')
        self.assertEqual(snap['counts']['captured'], 1)
        self.assertIsNone(snap['sources'][0]['assessment'])
        self.assertIn('learner', snap['library_limits'])

import copy
import json
import os
import tempfile
from unittest import mock
def article():
    return {'id': 'article:test', 'realm': 'personal', 'kind': 'article', 'title': 'Synthetic article', 'author': 'Test author', 'url': 'https://example.org/test', 'captured_at': '2026-10-10T12:00:00-04:00', 'duration_minutes': None, 'coverage': 'metadata_only', 'summary': [], 'ideas': [], 'tools': [], 'assessment': None, 'note_path': None}
class AssessmentTests(unittest.TestCase):

    def test_metadata_record_is_supported_without_learning_profile(self):
        self.assertIsNotNone(praxis, 'assessment validator is not implemented')
        result = praxis.validate_record(article(), 'personal')
        self.assertEqual(result['coverage'], 'metadata_only')
        self.assertEqual(result['kind'], 'article')

    def test_metadata_cannot_support_firm_grade_or_invent_content(self):
        rec = article()
        rec['assessment'] = {'recommendation': 'Watch', 'value': 'high', 'confidence': 'high'}
        with self.assertRaisesRegex(ValueError, 'incomplete|metadata|coverage'):
            praxis.validate_record(rec, 'personal')
        rec['assessment'] = None
        rec['ideas'] = ['Title-derived invention']
        with self.assertRaisesRegex(ValueError, 'metadata'):
            praxis.validate_record(rec, 'personal')

    def test_full_assessment_requires_traceable_novelty_and_credibility(self):
        rec = article()
        rec.update(coverage='full_text', source_text='Local files and properties.', ideas=['Local Markdown views'], summary=['A core plugin queries note properties.'])
        rec['assessment'] = {'recommendation': 'Read', 'value': 'moderate', 'confidence': 'medium', 'rationale': 'New implementation detail in recorded library.', 'time_guidance': 'Read the overview.', 'reviewed_at': rec['captured_at'], 'novelty': [{'idea': 'Local Markdown views', 'bucket': 'new', 'evidence': 'Local files and properties.', 'compared_with': [], 'prior_evidence': 'Not found in recorded sources, not proof of ignorance.'}], 'credibility': {'topic': 'Product behavior', 'judgment': 'Primary docs; no independent audit.', 'comparison': 'No same-topic prior source.', 'established': True, 'comparison_established': False, 'compared_sources': [], 'evidence': [{'claim': 'Local files', 'url': rec['url'], 'checked_at': rec['captured_at']}], 'unknowns': ['Deployment not tested.']}}
        self.assertEqual(praxis.validate_record(rec, 'personal')['assessment']['recommendation'], 'Read')
        bad = copy.deepcopy(rec)
        bad['assessment']['novelty'][0]['evidence'] = ''
        with self.assertRaises(ValueError):
            praxis.validate_record(bad, 'personal')
        bad = copy.deepcopy(rec)
        bad['assessment']['credibility']['evidence'][0]['url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError):
            praxis.validate_record(bad, 'personal')
        bad = copy.deepcopy(rec)
        bad['captured_at'] = 'not-a-date'
        with self.assertRaises(ValueError):
            praxis.validate_record(bad, 'personal')
        bad = copy.deepcopy(rec)
        bad['url'] = 'https://user:secret@example.org'
        with self.assertRaises(ValueError):
            praxis.validate_record(bad, 'personal')

    def test_projection_aggregates_mentions_and_keeps_each_note_with_stable_ids(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            notes = Path(temp)
            note = notes / 'first.md'
            note.write_text('---\nprivate: local-path\n---\n# First real text\n', encoding='utf-8')
            first = article()
            first.update(id='video:first', kind='video', coverage='prior_note', note_path=str(note), ideas=['Saved idea'], summary=['Saved idea'])
            tool = {'name': 'Shared tool', 'kind': 'CLI', 'origin': 'video', 'purpose': 'Task', 'source_evidence': 'Actual source mention', 'decision': 'investigate'}
            first['tools'] = [tool]
            first['private_secret'] = 'MUST_NOT_APPEAR'
            second = copy.deepcopy(first)
            second.update(id='podcast:second', kind='podcast', note_path=None, captured_at='2026-10-10T13:00:00-04:00')
            second['tools'][0].update(origin='source', source_evidence='Different podcast evidence')
            out = praxis.build_snapshot([first, second], notes, 'Synthetic test vault', '2026-10-10T14:00:00-04:00', 'personal')
            self.assertEqual([s['id'] for s in out['sources']], ['podcast:second', 'video:first'])
            self.assertEqual(len(out['tools']), 1)
            self.assertEqual(len(out['tools'][0]['mentions']), 2)
            self.assertIn('First real text', out['sources'][1]['note_text'])
            self.assertNotIn('private:', out['sources'][1]['note_text'])
            self.assertNotIn('MUST_NOT_APPEAR', str(out))
            self.assertNotIn('note_path', str(out))
            self.assertEqual(out['counts']['captured'], 2)
            self.assertEqual(out['counts']['investigate_leads'], 1)
            self.assertEqual(praxis.build_snapshot([second, first], notes, 'Synthetic test vault', '2026-10-10T14:00:00-04:00', 'personal'), out)

    def test_refresh_is_idempotent_atomic_and_preserves_last_good_on_failure(self):
        import tempfile
        self.assertTrue(hasattr(praxis, 'refresh'), 'atomic refresh is not implemented')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / 'template.html'
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            out = root / 'index.html'
            snap = praxis.build_snapshot([], root, 'test', '2026-10-10T14:00:00-04:00', 'personal')
            first = praxis.refresh(snap, template, out, project_root=root)
            self.assertFalse(first['unchanged'])
            before = out.read_bytes()
            second = praxis.refresh(snap, template, out, project_root=root)
            self.assertTrue(second['unchanged'])
            self.assertEqual(out.read_bytes(), before)
            template.write_text('BROKEN TEMPLATE', encoding='utf-8')
            with self.assertRaises(ValueError):
                praxis.refresh(snap, template, out, project_root=root)
            self.assertEqual(out.read_bytes(), before)
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap['library_limits'] = '</script><img src=x onerror=alert(1)>'
            praxis.refresh(snap, template, out, project_root=root)
            self.assertNotIn('<img src=x', out.read_text(encoding='utf-8'))

    def test_full_source_needs_text_and_quote_support(self):
        rec = article()
        rec.update(coverage='full_text', summary=['Documented implementation'], source_text='Local files and properties.')
        rec['assessment'] = {'recommendation': 'Read', 'value': 'moderate', 'confidence': 'medium', 'rationale': 'Concrete detail.', 'time_guidance': 'Read it.', 'reviewed_at': rec['captured_at'], 'novelty': [{'idea': 'Local files', 'bucket': 'new', 'evidence': 'Invented quotation', 'compared_with': [], 'prior_evidence': 'No matching recorded idea.'}], 'credibility': {'topic': 'Product', 'judgment': 'Official docs', 'comparison': 'Unknown', 'established': False, 'comparison_established': False, 'compared_sources': [], 'evidence': [], 'unknowns': ['Audit unknown']}}
        with self.assertRaisesRegex(ValueError, 'source text|quote'):
            praxis.validate_record(rec, 'personal')
        rec['assessment']['novelty'][0]['evidence'] = 'Local files and properties.'
        self.assertEqual(praxis.validate_record(rec, 'personal')['coverage'], 'full_text')
        rec.pop('source_text')
        with self.assertRaisesRegex(ValueError, 'source text'):
            praxis.validate_record(rec, 'personal')

    def test_candidate_overlap_never_claims_semantic_novelty_or_mastery(self):
        self.assertTrue(hasattr(praxis, 'compare_candidates'), 'comparison retrieval is missing')
        prior = article()
        prior.update(id='video:old', coverage='prior_note', ideas=['Persistent memory separates owner decisions and external claims'])
        candidate = article()
        candidate.update(id='article:new', coverage='full_text', source_text='Memory is bounded.', ideas=['Persistent memory separates external claims'])
        result = praxis.compare_candidates(candidate, [prior])
        self.assertIn('Lexical candidates', result['limits'])
        self.assertEqual(result['candidates'][0]['source_id'], 'video:old')
        self.assertNotIn('new_to_you', str(result))
        self.assertNotIn('trust_score', str(result))
        self.assertEqual(praxis.compare_candidates(candidate, [])['candidates'], [])

    def test_repeat_refresh_does_not_rewrite_only_for_new_clock_time(self):
        import tempfile
        self.assertTrue(hasattr(praxis, 'refresh'))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / 'template.html'
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap = praxis.build_snapshot([], root, 'test', '2026-10-10T14:00:00-04:00', 'personal')
            out = root / 'index.html'
            praxis.refresh(snap, template, out, project_root=root)
            before = out.read_bytes()
            snap['generated_at'] = '2026-10-10T15:00:00-04:00'
            self.assertTrue(praxis.refresh(snap, template, out, project_root=root)['unchanged'])
            self.assertEqual(out.read_bytes(), before)
            template.write_text('<p>New design</p><script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            self.assertFalse(praxis.refresh(snap, template, out, project_root=root)['unchanged'])

    def test_validator_rejects_malformed_evidence_tools_and_unsafe_types(self):
        for value in (None, [], 'not a record'):
            with self.assertRaises(ValueError):
                praxis.validate_record(value, 'personal')
        rec = article()
        rec.update(coverage='full_text', source_text='Tool Alpha reads files.', tools=[{'name': 'Alpha', 'kind': 'CLI', 'origin': 'source', 'purpose': 'Read files', 'source_evidence': 'Made-up tool quotation', 'decision': 'investigate'}])
        with self.assertRaisesRegex(ValueError, 'quote'):
            praxis.validate_record(rec, 'personal')
        rec['tools'][0]['source_evidence'] = 'Tool Alpha reads files.'
        self.assertEqual(praxis.validate_record(rec, 'personal')['tools'][0]['name'], 'Alpha')
        rec['tools'][0]['official_docs_url'] = 'file:///C:/private'
        with self.assertRaises(ValueError):
            praxis.validate_record(rec, 'personal')

    def test_note_scope_escape_and_unknown_comparison_fail_before_write(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            notes = Path(temp) / 'Learning'
            notes.mkdir()
            outside = Path(temp) / 'outside.md'
            outside.write_text('Private outside note', encoding='utf-8')
            rec = article()
            rec.update(coverage='prior_note', note_path=str(outside))
            with self.assertRaisesRegex(ValueError, 'escapes'):
                praxis.build_snapshot([rec], notes, 'Vault', '2026-10-10T14:00:00-04:00', 'personal')
NOW = "2026-10-10T14:00:00-04:00"
def full_record():
    r = article()
    r.update(coverage='full_text', source_text='Shared useful idea. Alpha reads files.', summary=['Shared useful idea.'], ideas=['Shared useful idea.'])
    r['assessment'] = {'recommendation': 'Read', 'value': 'moderate', 'confidence': 'medium', 'rationale': 'Evidence retained.', 'time_guidance': 'Read overview.', 'reviewed_at': NOW, 'novelty': [{'idea': 'Shared useful idea.', 'bucket': 'new', 'evidence': 'Shared useful idea.', 'compared_with': [], 'prior_evidence': 'Not found in recorded library.'}], 'credibility': {'topic': 'Files', 'judgment': 'Unverified strong claim', 'comparison': 'Unverified superiority', 'established': False, 'comparison_established': False, 'compared_sources': [], 'evidence': [], 'unknowns': ['Independent audit unknown.']}}
    return r
def tool():
    return {'name': 'Alpha', 'kind': 'CLI', 'origin': 'source', 'purpose': 'Read files', 'source_evidence': 'Alpha reads files.', 'decision': 'investigate'}
class ReviewRegressions(unittest.TestCase):

    def snapshot(self, records, notes):
        return praxis.build_snapshot(records, notes, 'Synthetic vault', NOW, 'personal')

    def link_directory(self, link, target):
        if os.name == 'nt':
            import subprocess
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_frontmatter_closed_at_eof_is_not_projected(self):
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                note = root / 'note.md'
                original = newline.join(('---', 'private_internal: SYNTHETIC_FRONTMATTER_ONLY', '---')).encode('utf-8')
                note.write_bytes(original)
                record = article() | {'coverage': 'prior_note', 'note_path': str(note)}
                projected = self.snapshot([record], root)
                self.assertEqual(projected['sources'][0]['note_text'], '')
                self.assertNotIn('SYNTHETIC_FRONTMATTER_ONLY', json.dumps(projected))
                self.assertEqual(note.read_bytes(), original)

    def test_bom_frontmatter_is_removed_without_losing_saved_body(self):
        for newline in ('\n', '\r\n'):
            for body in ('', '# Saved note body\n', '# Saved note body\n\n---\nBody divider\n---'):
                with self.subTest(newline=repr(newline), body=body), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    note = root / 'note.md'
                    original = ('\ufeff' + newline.join(('---', 'private_internal: SYNTHETIC_FRONTMATTER_BOM', '---')) + (newline + body.replace('\n', newline) if body else '')).encode('utf-8')
                    note.write_bytes(original)
                    record = article() | {'coverage': 'prior_note', 'note_path': str(note)}
                    projected = self.snapshot([record], root)
                    self.assertEqual(projected['sources'][0]['note_text'], body)
                    self.assertNotIn('SYNTHETIC_FRONTMATTER_BOM', json.dumps(projected))
                    self.assertEqual(note.read_bytes(), original)

    def test_citation_and_snapshot_chronology_orderings(self):
        with tempfile.TemporaryDirectory() as temp:
            r = full_record()
            citation = {'claim': 'Behavior', 'url': r['url'], 'checked_at': '2026-10-10T13:00:00-04:00'}
            r['assessment']['credibility']['evidence'] = [citation]
            self.snapshot([r], temp)
            citation['checked_at'] = '2026-10-10T15:00:00-04:00'
            with self.assertRaisesRegex(ValueError, 'citation|checked'):
                praxis.validate_record(r, 'personal')

    def test_snapshot_chronology_orderings(self):
        with tempfile.TemporaryDirectory() as temp:
            for field in ('captured_at', 'reviewed_at'):
                future = full_record() if field == 'reviewed_at' else article()
                if field == 'reviewed_at':
                    future['assessment'][field] = '2026-10-10T15:00:00-04:00'
                else:
                    future[field] = '2026-10-10T15:00:00-04:00'
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'snapshot|generated'):
                    self.snapshot([future], temp)
            self.snapshot([full_record(), article() | {'id': 'article:other'}], temp)

    def test_output_junction_escape_is_rejected_before_template_or_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project, outside = (root / 'project', root / 'outside')
            project.mkdir()
            outside.mkdir()
            template = project / 'template.html'
            template.write_text('%%PRAXIS_DATA%%', encoding='utf-8')
            self.link_directory(project / 'site', outside)
            with mock.patch.object(praxis, 'ROOT', project):
                with self.assertRaisesRegex(ValueError, 'escape|scope'):
                    praxis.refresh(self.snapshot([], root), template, project / 'site/personal/index.html')
            self.assertEqual(list(outside.iterdir()), [])

    def test_overlap_references_require_usable_prior_quote_and_chronology(self):
        with tempfile.TemporaryDirectory() as temp:
            current = full_record()
            prior = article()
            prior.update(id='video:prior', kind='video', coverage='prior_note', ideas=['SHARED   useful idea.'])
            n = current['assessment']['novelty'][0]
            n.update(bucket='repetition', compared_with=[prior['id']], prior_evidence='shared useful idea.')
            self.snapshot([current, prior], temp)
            variants = []
            bad = copy.deepcopy(prior)
            bad.update(coverage='metadata_only', ideas=[])
            variants.append((current, bad))
            bad = copy.deepcopy(prior)
            bad['captured_at'] = '2026-10-11T12:00:00-04:00'
            variants.append((current, bad))
            bad = copy.deepcopy(current)
            bad['assessment']['novelty'][0]['prior_evidence'] = 'Unsupported overlap assertion'
            variants.append((bad, prior))
            bad = copy.deepcopy(current)
            bad['assessment']['novelty'][0].update(bucket='new', prior_evidence='Unsupported comparison')
            variants.append((bad, prior))
            for candidate, previous in variants:
                with self.subTest(prior=previous['coverage'], captured=previous['captured_at'], novelty=candidate['assessment']['novelty']):
                    with self.assertRaises(ValueError):
                        self.snapshot([candidate, previous], temp)
            current['captured_at'] = '2026-10-11T12:00:00-04:00'
            with self.assertRaises(ValueError):
                praxis.validate_record(current, 'personal')

    def test_credibility_missing_or_false_flags_project_not_established(self):
        with tempfile.TemporaryDirectory() as temp:
            for missing in (True, False):
                r = full_record()
                c = r['assessment']['credibility']
                if missing:
                    c.pop('established')
                    c.pop('comparison_established')
                    c.pop('compared_sources')
                projected = self.snapshot([r], temp)['sources'][0]['assessment']['credibility']
                self.assertEqual(projected['judgment'], 'Not established')
                self.assertEqual(projected['comparison'], 'Not established')
                self.assertIs(projected['established'], False)
                self.assertIs(projected['comparison_established'], False)
                self.assertEqual(projected['compared_sources'], [])

    def test_established_credibility_requires_citations_and_usable_comparison_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            prior = article()
            prior.update(id='video:prior', coverage='prior_note', ideas=['Shared useful idea.'])
            r = full_record()
            c = r['assessment']['credibility']
            c.update(established=True, comparison_established=True, compared_sources=[prior['id']], evidence=[{'claim': 'Documented behavior', 'url': 'https://example.org/docs', 'checked_at': NOW}])
            out = self.snapshot([r, prior], temp)['sources'][1]['assessment']['credibility']
            self.assertTrue(out['established'])
            invalid = [('established', 'true'), ('comparison_established', 1), ('evidence', []), ('compared_sources', []), ('compared_sources', [r['id']]), ('compared_sources', ['missing']), ('compared_sources', {'id': prior['id']})]
            for key, value in invalid:
                with self.subTest(key=key, value=value):
                    bad = copy.deepcopy(r)
                    bad['assessment']['credibility'][key] = value
                    with self.assertRaises(ValueError):
                        self.snapshot([bad, prior], temp)
            for changes in ({'coverage': 'metadata_only', 'ideas': []}, {'captured_at': '2026-10-11T12:00:00-04:00'}, {'ideas': []}):
                bad = copy.deepcopy(prior)
                bad.update(changes)
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.snapshot([r, bad], temp)

    def test_current_note_edit_cannot_ground_an_earlier_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            note = root / 'prior.md'
            note.write_text('Edited saved note quotation.', encoding='utf-8')
            prior = article()
            prior.update(id='video:prior', coverage='prior_note', note_path=str(note))
            current = full_record()
            current['assessment']['novelty'][0].update(bucket='repetition', compared_with=[prior['id']], prior_evidence='Edited saved note quotation.')
            after = praxis.timestamp('2026-10-11T12:00:00-04:00').timestamp()
            os.utime(note, (after, after))
            with self.assertRaisesRegex(ValueError, 'prior|available|content'):
                self.snapshot([current, prior], root)
            before = praxis.timestamp('2026-10-09T12:00:00-04:00').timestamp()
            os.utime(note, (before, before))
            self.snapshot([current, prior], root)
            current['assessment']['novelty'] = []
            current['assessment']['credibility']['compared_sources'] = [prior['id']]
            self.snapshot([current, prior], root)
            os.utime(note, (after, after))
            with self.assertRaisesRegex(ValueError, 'prior|available|content'):
                self.snapshot([current, prior], root)

    def test_empty_snapshot_rejects_invalid_explicit_realm(self):
        with tempfile.TemporaryDirectory() as temp:
            for realm in ('unapproved', None, ''):
                with self.subTest(realm=realm), self.assertRaisesRegex(ValueError, 'realm'):
                    praxis.build_snapshot([], temp, 'Synthetic vault', NOW, realm)

    def test_mention_ties_use_all_projected_fields_deterministically(self):
        with tempfile.TemporaryDirectory() as temp:
            record = full_record()
            first, second = (tool(), tool())
            first.update(purpose='Z purpose', decision='skip', security='unchecked')
            second.update(purpose='A purpose', decision='investigate', security='unknown')
            record['tools'] = [first, second]
            before = self.snapshot([record], temp)
            record['tools'].reverse()
            self.assertEqual(self.snapshot([record], temp), before)
            first.update(purpose='A purpose', decision='investigate', security='unknown', relevance=None)
            second['relevance'] = 'unknown'
            record['tools'] = [first, second]
            before = self.snapshot([record], temp)
            record['tools'].reverse()
            self.assertEqual(self.snapshot([record], temp), before)

    def test_tool_display_spelling_is_independent_of_input_order(self):
        with tempfile.TemporaryDirectory() as temp:
            first = full_record()
            first['tools'] = [tool()]
            second = copy.deepcopy(first)
            second['id'] = 'article:second'
            second['tools'][0]['name'] = 'ALPHA'
            self.assertEqual(self.snapshot([first, second], temp), self.snapshot([second, first], temp))

    def test_noop_generation_watermark_rejects_intermediate_stale_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap = self.snapshot([], root)
            praxis.refresh(snap, template, output, project_root=root)
            before, modified = (output.read_bytes(), output.stat().st_mtime_ns)
            snap['generated_at'] = '2026-10-10T16:00:00-04:00'
            self.assertTrue(praxis.refresh(snap, template, output, project_root=root)['unchanged'])
            self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), (before, modified))
            stale = copy.deepcopy(snap)
            stale.update(generated_at='2026-10-10T15:00:00-04:00', library_limits='Stale changed data')
            with self.assertRaisesRegex(ValueError, 'older|stale'):
                praxis.refresh(stale, template, output, project_root=root)
            metadata = output.with_name(output.name + '.watermark.json')
            self.assertTrue(metadata.is_file())
            self.assertEqual(json.loads(metadata.read_text())['generated_at'], snap['generated_at'])
            self.assertEqual(output.read_bytes(), before)

    def assert_inaccessible_container_preserves_last_good(self, html):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            valid = '<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>'
            template.write_text(valid, encoding='utf-8')
            snapshot = self.snapshot([], root)
            praxis.refresh(snapshot, template, output, project_root=root)
            watermark = output.with_name(output.name + '.watermark.json')
            before = (output.read_bytes(), output.stat().st_mtime_ns, watermark.read_bytes(), watermark.stat().st_mtime_ns)
            template.write_text(html, encoding='utf-8')
            newer = snapshot | {'generated_at': '2026-10-10T16:00:00-04:00', 'library_limits': 'Synthetic replacement must not publish.'}
            try:
                with self.assertRaisesRegex(ValueError, 'container|script'):
                    praxis.refresh(newer, template, output, project_root=root)
            finally:
                after = (output.read_bytes(), output.stat().st_mtime_ns, watermark.read_bytes(), watermark.stat().st_mtime_ns)
                self.assertEqual(after, before, 'invalid template changed last-good HTML or watermark')
                self.assertFalse(output.with_name(output.name + '.lock').exists())
                self.assertEqual(list(root.glob('.praxis-*.tmp')), [])

    def test_template_wrapped_container_rejected_before_publication(self):
        script = '<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>'
        for html in ('<template>' + script + '</template>', '<template><template></template>' + script + '</template>', '<template/>' + script):
            with self.subTest(html=html):
                self.assert_inaccessible_container_preserves_last_good(html)

    def test_raw_text_wrapped_container_rejected_before_publication(self):
        script = '<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>'
        for tag in ('noscript', 'textarea', 'title', 'xmp', 'iframe', 'noembed', 'noframes', 'plaintext', 'style'):
            for opening in ('<' + tag + '>', '<' + tag + '/>'):
                with self.subTest(tag=tag, opening=opening):
                    self.assert_inaccessible_container_preserves_last_good(opening + script + '</' + tag + '>')
        self.assert_inaccessible_container_preserves_last_good('<plaintext></plaintext>' + script)

    def test_document_container_remains_valid_outside_inert_or_text_content(self):
        script = '<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>'
        prefixes = ('', '<!doctype html><html><head><title>Synthetic dashboard</title><style>body { color: black; }</style></head><body>', '<template><p>Unrelated inert content</p></template>', '<noscript>Enable scripting</noscript>', '<textarea><template></textarea>', '<!-- <template> -->')
        for prefix in prefixes:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                template, output = (root / 'template.html', root / 'index.html')
                html = prefix + '<main>' + script + '</main>'
                template.write_text(html, encoding='utf-8')
                snapshot = self.snapshot([], root)
                self.assertFalse(praxis.refresh(snapshot, template, output, project_root=root)['unchanged'])
                self.assertEqual(json.loads(praxis._data_container(output.read_text(encoding='utf-8'))), snapshot)
                self.assertTrue(praxis.refresh(snapshot, template, output, project_root=root)['unchanged'])

    def test_template_requires_actual_json_data_container(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            for html in ('<div>%%PRAXIS_DATA%%</div>', '<script id="praxis-data">%%PRAXIS_DATA%%</script>', '<div id="praxis-data" type="application/json">%%PRAXIS_DATA%%</div>', '<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script><script id="praxis-data" type="application/json">{}</script>'):
                template.write_text(html, encoding='utf-8')
                with self.subTest(html=html), self.assertRaisesRegex(ValueError, 'container|script'):
                    praxis.refresh(self.snapshot([], root), template, output, project_root=root)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_name(output.name + '.watermark.json').exists())
                self.assertFalse(output.with_name(output.name + '.lock').exists())

    def test_existing_output_without_watermark_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap = self.snapshot([], root)
            output.write_text(template.read_text().replace('%%PRAXIS_DATA%%', json.dumps(snap)), encoding='utf-8')
            before = output.read_bytes()
            with self.assertRaisesRegex(ValueError, 'watermark|metadata'):
                praxis.refresh(snap, template, output, project_root=root)
            self.assertEqual(output.read_bytes(), before)

    def test_watermark_metadata_and_output_corruption_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap = self.snapshot([], root)
            praxis.refresh(snap, template, output, project_root=root)
            watermark = output.with_name(output.name + '.watermark.json')
            before, original = (output.read_bytes(), watermark.read_bytes())
            metadata = json.loads(original)
            variants = ['{', '[]', json.dumps(metadata | {'realm': 'work'}), json.dumps(metadata | {'output': 'different.html'}), json.dumps(metadata | {'schema_version': True}), json.dumps(metadata | {'generated_at': '2026-10-10T13:00:00-04:00'}), json.dumps(metadata | {'generated_at': 'no date'}), json.dumps(metadata | {'html_sha256': '0' * 64, 'reserved_sha256': '0' * 64}), json.dumps(metadata | {'reserved_sha256': None})]
            for value in variants:
                watermark.write_text(value, encoding='utf-8')
                with self.subTest(value=value), self.assertRaises(ValueError):
                    praxis.refresh(snap, template, output, project_root=root)
                self.assertEqual(output.read_bytes(), before)
                self.assertEqual(watermark.read_text(), value)
                self.assertFalse(output.with_name(output.name + '.lock').exists())
                self.assertEqual(list(root.glob('.praxis-*.tmp')), [])
            watermark.write_bytes(original)
            for value in ('<div>broken HTML</div>', '<script id="praxis-data" type="application/json">not JSON</script>', template.read_text().replace('%%PRAXIS_DATA%%', json.dumps(snap | {'realm': 'work'}))):
                output.write_text(value, encoding='utf-8')
                with self.subTest(output=value), self.assertRaises(ValueError):
                    praxis.refresh(snap, template, output, project_root=root)
                self.assertEqual(output.read_text(), value)
                self.assertEqual(watermark.read_bytes(), original)

    def test_watermark_path_cannot_resolve_outside_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project, outside = (root / 'project', root / 'outside')
            project.mkdir()
            outside.mkdir()
            template, output = (project / 'template.html', project / 'index.html')
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            self.link_directory(output.with_name(output.name + '.watermark.json'), outside)
            with self.assertRaisesRegex(ValueError, 'scope|escape'):
                praxis.refresh(self.snapshot([], root), template, output, project_root=project)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse(output.exists())
            self.assertFalse(output.with_name(output.name + '.lock').exists())

    def test_partial_html_failures_reserve_generation_and_allow_retry(self):
        for operation in ('create', 'write', 'flush', 'fsync', 'replace'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                template, output = (root / 'template.html', root / 'index.html')
                template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
                snap = self.snapshot([], root)
                praxis.refresh(snap, template, output, project_root=root)
                before = output.read_bytes()
                snap.update(generated_at='2026-10-10T16:00:00-04:00', library_limits='New reserved content')
                calls = 0
                factory, fsync, replace = (praxis.tempfile.NamedTemporaryFile, praxis.os.fsync, praxis.os.replace)

                class FailingStream:

                    def __init__(self, stream):
                        self.stream, self.name = (stream, stream.name)

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        self.stream.close()

                    def write(self, data):
                        if operation == 'write':
                            raise OSError('injected HTML write failure')
                        return self.stream.write(data)

                    def flush(self):
                        raise OSError('injected HTML flush failure')

                def temporary(**kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        if operation == 'create':
                            raise OSError('injected HTML create failure')
                        if operation in ('write', 'flush'):
                            return FailingStream(factory(**kwargs))
                    return factory(**kwargs)

                def sync(fd):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise OSError('injected HTML fsync failure')
                    return fsync(fd)

                def swap(source, target):
                    if Path(target) == output:
                        raise OSError('injected HTML replace failure')
                    return replace(source, target)
                failure = mock.patch.object(praxis.tempfile, 'NamedTemporaryFile', side_effect=temporary) if operation in ('create', 'write', 'flush') else mock.patch.object(praxis.os, 'fsync', side_effect=sync) if operation == 'fsync' else mock.patch.object(praxis.os, 'replace', side_effect=swap)
                with failure, self.assertRaisesRegex(OSError, 'injected HTML'):
                    praxis.refresh(snap, template, output, project_root=root)
                self.assertEqual(output.read_bytes(), before)
                watermark = output.with_name(output.name + '.watermark.json')
                self.assertEqual(json.loads(watermark.read_text())['generated_at'], snap['generated_at'])
                self.assertFalse(output.with_name(output.name + '.lock').exists())
                self.assertEqual(list(root.glob('.praxis-*.tmp')), [])
                stale = snap | {'generated_at': '2026-10-10T15:00:00-04:00'}
                with self.assertRaisesRegex(ValueError, 'older|stale'):
                    praxis.refresh(stale, template, output, project_root=root)
                self.assertFalse(praxis.refresh(snap, template, output, project_root=root)['unchanged'])
                self.assertIn('New reserved content', output.read_text())

    def test_first_publication_partial_reservation_is_retryable_but_not_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap = self.snapshot([], root)
            replace = praxis.os.replace

            def fail_html(source, target):
                if Path(target) == output:
                    raise OSError('injected first HTML replace failure')
                return replace(source, target)
            with mock.patch.object(praxis.os, 'replace', side_effect=fail_html), self.assertRaisesRegex(OSError, 'injected'):
                praxis.refresh(snap, template, output, project_root=root)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob('.praxis-*.tmp')), [])
            stale = snap | {'generated_at': '2026-10-10T13:00:00-04:00'}
            with self.assertRaisesRegex(ValueError, 'older|stale'):
                praxis.refresh(stale, template, output, project_root=root)
            praxis.refresh(snap, template, output, project_root=root)
            praxis.refresh(snap, template, output, project_root=root)
            output.unlink()
            with self.assertRaisesRegex(ValueError, 'inconsistent'):
                praxis.refresh(snap, template, output, project_root=root)

    def test_staging_failures_clean_all_artifacts_and_preserve_last_good(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap = self.snapshot([], root)
            praxis.refresh(snap, template, output, project_root=root)
            before = output.read_bytes()
            watermark_before = output.with_name(output.name + '.watermark.json').read_bytes()
            snap['library_limits'] = 'Changed synthetic snapshot.'
            factory = praxis.tempfile.NamedTemporaryFile

            class WriteFailure:

                def __init__(self, stream):
                    self.stream, self.name = (stream, stream.name)

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.stream.close()

                def write(self, data):
                    raise OSError('injected write failure')
            failures = (mock.patch.object(praxis.tempfile, 'NamedTemporaryFile', side_effect=OSError('injected create failure')), mock.patch.object(praxis.tempfile, 'NamedTemporaryFile', side_effect=lambda **kw: WriteFailure(factory(**kw))), mock.patch.object(praxis.os, 'fsync', side_effect=OSError('injected fsync failure')), mock.patch.object(praxis.os, 'replace', side_effect=OSError('injected replace failure')))
            for failure in failures:
                with failure, self.assertRaisesRegex(OSError, 'injected'):
                    praxis.refresh(snap, template, output, project_root=root)
                self.assertEqual(output.read_bytes(), before)
                self.assertEqual(output.with_name(output.name + '.watermark.json').read_bytes(), watermark_before)
                self.assertEqual(sorted((p.name for p in root.iterdir())), ['index.html', 'index.html.watermark.json', 'template.html'])

    def test_refresh_lock_fails_closed_without_touching_held_lock_or_last_good(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap = self.snapshot([], root)
            praxis.refresh(snap, template, output, project_root=root)
            before = output.read_bytes()
            lock = output.with_name(output.name + '.lock')
            lock.write_text('held by another refresh', encoding='utf-8')
            snap['library_limits'] = 'Changed synthetic snapshot.'
            with self.assertRaisesRegex(ValueError, 'lock|progress'):
                praxis.refresh(snap, template, output, project_root=root)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(lock.read_text(encoding='utf-8'), 'held by another refresh')
            lock.unlink()
            self.assertFalse(praxis.refresh(snap, template, output, project_root=root)['unchanged'])
            self.assertFalse(lock.exists())

    def test_older_generated_snapshot_cannot_replace_newer_published_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = (root / 'template.html', root / 'index.html')
            template.write_text('<script id="praxis-data" type="application/json">%%PRAXIS_DATA%%</script>', encoding='utf-8')
            snap = self.snapshot([], root)
            praxis.refresh(snap, template, output, project_root=root)
            before = output.read_bytes()
            snap.update(generated_at='2026-10-10T13:00:00-04:00', library_limits='Stale snapshot with different data.')
            with self.assertRaisesRegex(ValueError, 'older|stale'):
                praxis.refresh(snap, template, output, project_root=root)
            self.assertEqual(output.read_bytes(), before)
            self.assertFalse(output.with_name(output.name + '.lock').exists())

    def test_sensitive_cleanup_preserves_structural_ids_and_handles_quoted_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            r = full_record()
            r['id'] = 'session-id:stable-source'
            r['title'] = '"C:\\Program Files\\private report.txt" token=hidden-value https://user:private@example.org/a https://example.org/docs'
            out = self.snapshot([r], temp)
            self.assertEqual(out['sources'][0]['id'], r['id'])
            title = out['sources'][0]['title']
            for value in ('private report.txt', 'hidden-value', 'user:private'):
                self.assertNotIn(value, title)
            self.assertIn('https://example.org/docs', title)

    def test_obsidian_uri_does_not_encode_sensitive_vault_or_filename_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            note = root / 'session_id=private-session.md'
            note.write_text('Safe saved note.', encoding='utf-8')
            r = article()
            r.update(coverage='prior_note', note_path=str(note))
            out = praxis.build_snapshot([r], root, 'password=private-vault', NOW, 'personal')
            self.assertIsNone(out['sources'][0]['obsidian_uri'])
            self.assertIn('Safe saved note.', out['sources'][0]['note_text'])

    def test_unquoted_local_paths_with_spaces_do_not_leave_filename_suffixes(self):
        values = ('Saved to C:\\Program Files\\private report.txt', 'Local file /home/alice/private report.txt', 'Local file \\\\server\\private share\\report.txt', 'Local file ~/private notes/report.txt')
        for value in values:
            with self.subTest(value=value):
                cleaned = praxis.public_text(value)
                self.assertNotIn('report.txt', cleaned)
                self.assertIn('[local path omitted]', cleaned)

    def test_urls_reject_local_hosts_credentials_and_sensitive_parameters(self):
        bad = ('https://127.1/x', 'https://0177.0.0.1/x', 'https://0x7f.0.0.1/x', 'https://example.org/?sig=secret', 'https://localhost/x', 'https://127.0.0.1/x', 'https://[::1]/x', 'https://192.168.1.2/x', 'https://10.0.0.3/x', 'https://machine.local/x', 'https://machine/x', 'https://example.org/?api_key=secret', 'https://example.org/?token=secret', 'https://example.org/?password=secret', 'https://example.org/?signature=secret', 'https://example.org/#session_id=private', 'https://example.org/a b', 'https://***@localhost/x')
        for url in bad:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    praxis.https_url(url)
        safe = 'https://example.org/docs?q=alpha#section'
        self.assertEqual(praxis.https_url(safe), safe)
        with tempfile.TemporaryDirectory() as temp:
            r = article()
            r['url'] = safe
            self.assertEqual(self.snapshot([r], temp)['sources'][0]['url'], safe)

    def test_optional_tool_fields_reject_nested_or_nonscalar_data(self):
        fields = ('source_anchor', 'chapter_anchor', 'verification_status', 'verification_date', 'official_docs_url', 'pricing', 'security', 'relevance')
        for field in fields:
            for value in ({'session': 'private'}, ['private'], 123, False):
                with self.subTest(field=field, value=value):
                    r = full_record()
                    t = tool()
                    t[field] = value
                    r['tools'] = [t]
                    with self.assertRaises(ValueError):
                        praxis.validate_record(r, 'personal')

    def test_sensitive_text_is_cleaned_in_every_projection_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            r = full_record()
            leak = 'C:\\private\\record.txt /home/alice/private ~/.ssh/key api_key=abc123 session_id=private-session'
            r['source_text'] += ' ' + leak
            for k in ('title', 'author', 'action'):
                r[k] = leak
            r['summary'] = [leak]
            r['ideas'] = [leak]
            a = r['assessment']
            a['rationale'] = a['time_guidance'] = leak
            a['novelty'][0].update(idea=leak, evidence=leak, prior_evidence=leak)
            a['credibility'].update(topic=leak, unknowns=[leak], evidence=[{'claim': leak, 'url': 'https://example.org/a', 'checked_at': NOW}])
            t = tool()
            for k in ('name', 'purpose', 'source_evidence', 'source_anchor', 'verification_status', 'pricing', 'security', 'relevance'):
                t[k] = leak
            r['tools'] = [t]
            out = json.dumps(self.snapshot([r], temp))
            for private in ('record.txt', '/home/alice', '~/.ssh', 'abc123', 'private-session'):
                self.assertNotIn(private, out)
            self.assertIn('https://example.org/a', out)
            self.assertNotIn('source_text', out)

class StrictRecordTests(unittest.TestCase):
    def test_metadata_cannot_smuggle_source_text(self):
        r = article()
        r['source_text'] = 'Invented title-derived text.'
        with self.assertRaisesRegex(ValueError, 'metadata'):
            praxis.validate_record(r, 'personal')

    def test_strict_schema_rejects_duplicate_comparison_ids(self):
        r = full_record()
        r['assessment']['novelty'][0].update(bucket='repetition', compared_with=['prior', 'prior'])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            praxis.strict_record(r, 'personal')
        r = full_record()
        r['assessment']['credibility']['compared_sources'] = ['prior', 'prior']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            praxis.strict_record(r, 'personal')

    def test_timestamp_contract_matches_dashboard_without_precision_loss(self):
        for value in ('2026-01-01 12:00:00+00:00', '2026-01-01T12:00:00.0000001+00:00', '2026-01-01T12:00:00+0000', '2026-01-01X12:00:00+00:00'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                praxis.timestamp(value)
        self.assertEqual(praxis.timestamp('2026-01-01T12:00:00.123456Z').microsecond, 123456)
