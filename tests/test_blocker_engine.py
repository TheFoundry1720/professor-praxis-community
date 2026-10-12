"""Focused release-blocker regressions using synthetic records only."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from test_engine import praxis, article, full_record, NOW

MARKER = 'prior_evidence_available_at'
PRIVATE_TEXT = 'SYNTHETIC_PRIVATE_SOURCE_TEXT_ONLY'


def comparison_records():
    prior = article() | {'id': 'article:prior', 'coverage': 'full_text',
                         'source_text': PRIVATE_TEXT, 'summary': [], 'ideas': []}
    current = full_record()
    current['assessment']['credibility'].update(
        established=True, comparison_established=True, compared_sources=[prior['id']],
        comparison='Synthetic supported comparison',
        evidence=[{'claim': 'Synthetic documented behavior', 'url': current['url'], 'checked_at': NOW}])
    return current, prior


def comparison_snapshot(root):
    return praxis.build_snapshot(comparison_records(), root, 'Synthetic vault', NOW, 'personal')


class CredibilityFlagTests(unittest.TestCase):
    def test_all_four_flags_keep_citation_and_prior_requirements(self):
        with tempfile.TemporaryDirectory() as temp:
            for established in (False, True):
                for comparison in (False, True):
                    current, prior = comparison_records()
                    c = current['assessment']['credibility']
                    c.update(established=established, comparison_established=comparison)
                    if not comparison:
                        c['compared_sources'] = []
                    if not established and not comparison:
                        c.update(judgment='Unknown', comparison='Unknown', evidence=[])
                    with self.subTest(established=established, comparison=comparison):
                        if comparison and not established:
                            with self.assertRaisesRegex(ValueError, 'comparison.*established credibility'):
                                praxis.strict_record(current, 'personal')
                            continue
                        validated = praxis.strict_record(current, 'personal')
                        projected = praxis.build_snapshot([validated, prior], temp, 'Synthetic vault', NOW, 'personal')
                        out = next(s for s in projected['sources'] if s['id'] == current['id'])['assessment']['credibility']
                        self.assertIs(out['established'], established)
                        self.assertIs(out['comparison_established'], comparison)
                        if established:
                            citation = c['evidence'][0]
                            for bad in ([], [{'claim': citation['claim'], 'url': 'file:///private', 'checked_at': NOW}],
                                        [{'claim': citation['claim'], 'url': citation['url'], 'checked_at': '2026-10-10T15:00:00-04:00'}]):
                                c['evidence'] = bad
                                with self.assertRaises(ValueError):
                                    praxis.strict_record(current, 'personal')
                            c['evidence'] = [citation]
                        if comparison:
                            for records in ([current], [current, prior | {'coverage': 'metadata_only', 'source_text': None}],
                                            [current, prior | {'captured_at': '2026-10-10T15:00:00-04:00'}]):
                                with self.assertRaises(ValueError):
                                    praxis.build_snapshot(records, temp, 'Synthetic vault', NOW, 'personal')

    def test_comparison_cannot_be_established_when_credibility_is_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            current, prior = comparison_records()
            current['assessment']['credibility']['established'] = False
            for validator in (praxis.validate_record, praxis.strict_record):
                with self.subTest(validator=validator.__name__), self.assertRaisesRegex(ValueError, 'comparison.*established credibility'):
                    validator(current, 'personal')
            with self.assertRaisesRegex(ValueError, 'comparison.*established credibility'):
                praxis.build_snapshot([current, prior], temp, 'Synthetic vault', NOW, 'personal')


class TimestampOffsetTests(unittest.TestCase):
    def test_invalid_offset_components_are_not_normalized(self):
        for offset in ('+00:99', '+01:99', '-00:60', '-01:99', '+24:00', '-24:00'):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                praxis.timestamp('2026-01-01T12:00:00' + offset)

    def test_legal_aware_fractional_chronology_is_preserved(self):
        earlier = praxis.timestamp('2026-01-01T12:00:00.123455Z')
        later = praxis.timestamp('2026-01-01T13:00:00.123456+01:00')
        self.assertLess(earlier, later)
        self.assertEqual(praxis.timestamp('2026-01-01T12:00:00Z'),
                         praxis.timestamp('2026-01-01T07:00:00-05:00'))
        self.assertEqual(praxis.timestamp('2026-01-01T12:00:00.1+23:59').microsecond, 100000)


class EvidenceAvailabilityTests(unittest.TestCase):
    def test_private_source_only_projects_derived_availability_not_source_text(self):
        with tempfile.TemporaryDirectory() as temp:
            snapshot = comparison_snapshot(temp)
            prior = next(s for s in snapshot['sources'] if s['id'] == 'article:prior')
            current = next(s for s in snapshot['sources'] if s['id'] == 'article:test')
            self.assertTrue(current['assessment']['credibility']['comparison_established'])
            self.assertEqual(prior.get(MARKER), prior['captured_at'])
            self.assertNotIn(PRIVATE_TEXT, json.dumps(snapshot))
            self.assertNotIn('source_text', json.dumps(snapshot))

    def test_user_marker_is_never_evidence_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            current, prior = comparison_records()
            prior.update(coverage='prior_note', source_text=None)
            prior[MARKER] = prior['captured_at']
            with self.assertRaises(ValueError):
                praxis.strict_record(prior, 'personal')
            with self.assertRaisesRegex(ValueError, 'usable prior content'):
                praxis.build_snapshot([current, prior], temp, 'Synthetic vault', NOW, 'personal')
            snapshot = praxis.build_snapshot([prior], temp, 'Synthetic vault', NOW, 'personal')
            self.assertIsNone(snapshot['sources'][0].get(MARKER))

    def test_saved_note_availability_is_not_backdated_to_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            note = root / 'prior.md'
            note.write_text('Synthetic retained note evidence', encoding='utf-8')
            modified = praxis.timestamp('2026-10-10T13:00:00-04:00')
            os.utime(note, (modified.timestamp(), modified.timestamp()))
            record = article() | {'coverage': 'prior_note', 'note_path': str(note)}
            snapshot = praxis.build_snapshot([record], root, 'Synthetic vault', NOW, 'personal')
            self.assertEqual(snapshot['sources'][0].get(MARKER), modified.astimezone(praxis.dt.timezone.utc).isoformat())

    def test_reassessed_private_source_available_at_review_not_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            prior = full_record()
            prior.update(summary=[], ideas=[])
            snapshot = praxis.build_snapshot([prior], temp, 'Synthetic vault', NOW, 'personal')
            self.assertEqual(snapshot['sources'][0].get(MARKER), NOW)


class NotePathTests(unittest.TestCase):
    def test_malformed_note_paths_are_not_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            for value in ([], False, 0, '', '  ', {}, 123, 'relative.md',
                          str(Path(temp) / 'not-markdown.txt'),
                          str(Path(temp) / '../escape.md'), str(Path(temp) / 'nul\x00.md')):
                record = article() | {'note_path': value}
                for validator in (praxis.validate_record, praxis.strict_record):
                    with self.subTest(value=value, validator=validator.__name__), self.assertRaisesRegex(ValueError, 'note'):
                        validator(record, 'personal')
                with self.subTest(value=value, validator='snapshot'), self.assertRaisesRegex(ValueError, 'note'):
                    praxis.build_snapshot([record], temp, 'Synthetic vault', NOW, 'personal')

    def test_null_or_approved_actual_markdown_path_preserves_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            note = root / 'approved.md'
            original = 'Synthetic saved note evidence'
            note.write_text(original, encoding='utf-8')
            for value in (None, str(note)):
                record = article() | {'note_path': value}
                self.assertEqual(praxis.strict_record(record, 'personal')['note_path'], value)
                snapshot = praxis.build_snapshot([record], root, 'Synthetic vault', NOW, 'personal')
                self.assertEqual(snapshot['sources'][0]['note_text'], original if value else '')
                self.assertEqual(note.read_text(), original)
