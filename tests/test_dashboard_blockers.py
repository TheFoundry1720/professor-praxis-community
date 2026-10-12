"""Optional Node/Edge QA against actual generated data and dashboard JavaScript.

Normal runtime stays stdlib-only. These tests skip explicitly when Node or the
optional Playwright package/Edge executable is absent; no tooling is installed.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from test_blocker_engine import comparison_records, comparison_snapshot, PRIVATE_TEXT
from test_engine import praxis, ROOT

TEMPLATE = ROOT / 'skills/professor-praxis/scripts/dashboard.html'
EDGE = Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'

# Both environments execute the same actual dashboard functions. Only payload
# mutations for fail-closed QA occur here; no production logic is duplicated.
CASES = r"""
const prior = sourceMap.get('article:prior');
const source = sourceMap.get('article:test');
const original = structuredClone(prior);
const credibility = source.assessment.credibility;
const results = {};
const state = () => credibilityState(credibility, source).comparisonEstablished;
results.generated = state();
for (const [name, value] of Object.entries({
  invalid: 'not-a-timestamp', invalidOffset: '2026-10-10T12:00:00+00:99',
  future: '2026-10-10T15:00:00-04:00', beforeCapture: '2026-10-10T11:59:59-04:00',
  fractionalFuture: '2026-10-10T14:00:00.000001-04:00',
  nullMarker: null, boolMarker: true, emptyMarker: ''
})) {
  prior.prior_evidence_available_at = value;
  results[name] = state();
}
delete prior.prior_evidence_available_at;
results.missing = state();
Object.assign(prior, original);
prior.coverage = 'metadata_only';
results.metadata = state();
Object.assign(prior, original);
credibility.established = false;
results.unestablished = state();
credibility.established = true;
const checked = credibility.evidence[0].checked_at;
credibility.evidence[0].checked_at = '2026-10-10T15:00:00-04:00';
results.futureCitation = state();
credibility.evidence[0].checked_at = checked;
return results;
"""
EXPECTED = {'generated': True, **{name: False for name in (
    'invalid', 'invalidOffset', 'future', 'beforeCapture', 'fractionalFuture',
    'nullMarker', 'boolMarker', 'emptyMarker', 'missing', 'metadata',
    'unestablished', 'futureCitation')}}


def valid_flag_snapshots(root):
    for established, comparison in ((False, False), (True, False), (True, True)):
        current, prior = comparison_records()
        c = current['assessment']['credibility']
        c.update(established=established, comparison_established=comparison)
        if not comparison:
            c['compared_sources'] = []
        if not established:
            c.update(evidence=[], judgment='Unknown', comparison='Unknown')
        yield established, comparison, praxis.build_snapshot([current, prior], root, 'Synthetic vault', '2026-10-10T14:00:00-04:00', 'personal')


class DashboardNodeBlockers(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'optional Node runtime unavailable')
    def test_actual_generated_valid_flags_match_backend(self):
        with tempfile.TemporaryDirectory() as temp:
            template = TEMPLATE.read_text(encoding='utf-8')
            functions = template[template.index('function nonblank('):template.index('function openComparison(')]
            script = "const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));\nconst sourceMap = new Map(data.sources.map(s => [s.id, s]));\n" + functions + "\nconst s = sourceMap.get('article:test'); const state = credibilityState(s.assessment.credibility, s); console.log(JSON.stringify([state.established, state.comparisonEstablished]));"
            for established, comparison, snapshot in valid_flag_snapshots(temp):
                with self.subTest(established=established, comparison=comparison):
                    result = subprocess.run(['node', '-e', script], input=json.dumps(snapshot), capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), [established, comparison])
    @unittest.skipUnless(shutil.which('node'), 'optional Node runtime unavailable')
    def test_generated_private_source_only_comparison_and_unsupported_variants(self):
        with tempfile.TemporaryDirectory() as temp:
            snapshot = comparison_snapshot(temp)
            self.assertNotIn(PRIVATE_TEXT, json.dumps(snapshot))
            template = TEMPLATE.read_text(encoding='utf-8')
            functions = template[template.index('function nonblank('):template.index('function openComparison(')]
            script = "const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n" \
                     "const sourceMap = new Map(data.sources.map(s => [s.id, s]));\n" + functions + \
                     '\nconsole.log(JSON.stringify((() => {' + CASES + '})()));'
            result = subprocess.run(['node', '-e', script], input=json.dumps(snapshot), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), EXPECTED)


class DashboardBrowserBlockers(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('playwright') and EDGE.is_file(),
                         'optional Playwright package or Edge unavailable')
    def test_actual_generated_dashboard_private_source_comparison_and_fail_closed_variants(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = comparison_snapshot(root)
            output = root / 'dashboard.html'
            praxis.refresh(snapshot, TEMPLATE, output, project_root=root)
            self.assertNotIn(PRIVATE_TEXT, output.read_text(encoding='utf-8'))
            # Playwright/Node also put their isolated browser temp files in the
            # approved scratch directory, not Windows' unrelated temp location.
            scratch = str(root.parent)
            with mock.patch.dict(os.environ, {'TMPDIR': scratch, 'TMP': scratch, 'TEMP': scratch}):
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=str(EDGE), headless=True)
                    try:
                        page = browser.new_page()
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.route('https://**/*', lambda route: route.abort())
                        page.goto(output.as_uri())
                        self.assertEqual(page.evaluate('() => {' + CASES + '}'), EXPECTED)
                        page.evaluate("openComparison('article:test')")
                        self.assertIn('Synthetic supported comparison', page.locator('#dialog-content').inner_text())
                        page.evaluate("sourceMap.get('article:prior').prior_evidence_available_at = null; openComparison('article:test')")
                        self.assertIn('Not established: no supported credibility comparison', page.locator('#dialog-content').inner_text())
                        self.assertEqual(errors, [])
                        for established, comparison, valid in valid_flag_snapshots(root):
                            with self.subTest(established=established, comparison=comparison):
                                path = root / ('flags-' + str(established) + '-' + str(comparison) + '.html')
                                praxis.refresh(valid, TEMPLATE, path, project_root=root)
                                page.goto(path.as_uri())
                                self.assertEqual(page.evaluate("() => { const s = sourceMap.get('article:test'); const state = credibilityState(s.assessment.credibility, s); return [state.established, state.comparisonEstablished]; }"), [established, comparison])
                                self.assertEqual(errors, [])
                    finally:
                        browser.close()
