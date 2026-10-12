"""Professor Praxis: validate evidence records and refresh a local read-only view.

No model inference, credential handling, remote requests, note writes or history
appends. Hermes evaluates sources; this module guards and projects those results.
"""
import argparse
import copy
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
from html.parser import HTMLParser
import re
import sys
import tempfile
from urllib.parse import urlsplit, quote, unquote, parse_qsl

if sys.version_info < (3, 14):
    raise RuntimeError('Professor Praxis requires Python 3.14 or newer')

SCHEMA = 1
ROOT = Path(__file__).resolve().parent


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('missing or invalid ' + field)
    return value


def strings(value, field):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError('invalid ' + field)
    return value


def timestamp(value):
    value = text(value, 'timestamp')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
        raise ValueError('timestamp requires ISO date T time, timezone and at most microsecond precision')
    if value[-1] != 'Z' and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError('invalid timezone offset hour or minute')
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed


def https_url(value):
    value = text(value, 'URL')
    decoded = unquote(value)
    if re.search(r'[\s\\\x00-\x1f\x7f]', decoded):
        raise ValueError('unsafe URL characters')
    u = urlsplit(value)
    if u.scheme != 'https' or not u.hostname or u.username or u.password:
        raise ValueError('HTTPS URL without credentials required')
    host = u.hostname.rstrip('.').casefold()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        numeric_alias = all(re.fullmatch(r'(?:[0-9]+|0x[0-9a-f]+)', part) for part in host.split('.'))
        if numeric_alias or '.' not in host or host.endswith(('.localhost', '.local', '.internal', '.lan', '.home')) or not re.fullmatch(r'[a-z0-9.-]+', host):
            raise ValueError('local or invalid URL host')
    else:
        if not address.is_global:
            raise ValueError('local URL host')
    if u.port is not None and not 0 < u.port < 65536:
        raise ValueError('invalid URL port')
    sensitive = re.compile(r'(?:api.?key|token|password|secret|signature|credential|session.?id|authorization)', re.I)
    if any(sensitive.search(k) or k.casefold() in ('sig', 'auth', 'key', 'session') for part in (u.query, u.fragment) for k, _ in parse_qsl(part, keep_blank_values=True)):
        raise ValueError('credential/session URL parameters forbidden')
    return value


def validate_record(record, realm):
    if not isinstance(record, dict):
        raise ValueError('record must be an object')
    if realm not in ('personal', 'work'):
        raise ValueError('explicit realm required')
    if record.get('realm') != realm:
        raise ValueError('realm mismatch')
    if record.get('kind') not in ('video', 'podcast', 'article'):
        raise ValueError('unsupported source kind')
    if record.get('coverage') == 'metadata_only':
        if record.get('summary') or record.get('ideas') or record.get('tools') or record.get('source_text'):
            raise ValueError('metadata only cannot establish content')
        a = record.get('assessment')
        if a and (a.get('recommendation') != 'Unknown' or a.get('value') != 'unknown' or a.get('confidence') != 'low'):
            raise ValueError('metadata coverage cannot support firm grade')
    if not isinstance(record, dict):
        raise ValueError('record must be an object')
    for k in ('id', 'title', 'author'):
        text(record.get(k), k)
    if not re.fullmatch(r'[A-Za-z0-9:_-]{1,120}', record['id']):
        raise ValueError('invalid stable ID')
    https_url(record.get('url'))
    timestamp(record.get('captured_at'))
    note_path = record.get('note_path')
    if note_path is not None:
        text(note_path, 'note_path')
        path = Path(note_path)
        if not path.is_absolute() or '..' in path.parts or path.suffix.casefold() != '.md' or re.search(r'[\x00-\x1f\x7f]', note_path):
            raise ValueError('note_path requires an absolute Markdown path without traversal or control characters, or null')
    duration = record.get('duration_minutes')
    if duration is not None and (type(duration) not in (int, float) or not 0 < duration < 100000):
        raise ValueError('invalid duration')
    if record.get('coverage') not in ('full_text', 'full_transcript', 'metadata_only', 'prior_note'):
        raise ValueError('invalid coverage')
    for k in ('summary', 'ideas'):
        strings(record.get(k), k)
    if not isinstance(record.get('tools'), list):
        raise ValueError('invalid tools')
    if record['coverage'] in ('full_text', 'full_transcript'):
        text(record.get('source_text'), 'source text')
    for t in record['tools']:
        if not isinstance(t, dict):
            raise ValueError('invalid tool entry')
        for k in ('name', 'purpose', 'source_evidence'):
            text(t.get(k), 'tool ' + k)
        if t.get('kind') not in ('platform', 'MCP', 'CLI', 'library', 'other', 'unclear') or t.get('origin') not in ('video', 'source', 'assistant_suggestion', 'unclear') or t.get('decision') not in ('investigate', 'already use', 'skip', 'unclear'):
            raise ValueError('invalid tool classification')
        if t['origin'] == 'unclear' and (record['coverage'] != 'prior_note' or t['source_evidence'] != 'No source evidence retained' or t.get('verification_status') != 'Legacy provenance unavailable'):
            raise ValueError('unclear provenance is only a legacy missing-evidence marker')
        for k in ('source_anchor', 'chapter_anchor', 'verification_status', 'verification_date', 'official_docs_url', 'pricing', 'security', 'relevance'):
            if t.get(k) is not None and not isinstance(t[k], str):
                raise ValueError('tool ' + k + ' must be string or null')
        if t.get('official_docs_url') is not None:
            https_url(t['official_docs_url'])
        if record['coverage'] in ('full_text', 'full_transcript') and t['origin'] != 'assistant_suggestion' and ' '.join(t['source_evidence'].split()).casefold() not in ' '.join(record['source_text'].split()).casefold():
            raise ValueError('tool quote absent from source text')
    if record.get('action') is not None:
        text(record['action'], 'proposed action')
    if record.get('action_state') not in (None, 'open', 'applied', 'dropped'):
        raise ValueError('invalid action state')
    a = record.get('assessment')
    if a is not None:
        for k in ('rationale', 'time_guidance'):
            text(a.get(k), k)
        timestamp(a.get('reviewed_at'))
        if timestamp(record['captured_at']) > timestamp(a['reviewed_at']):
            raise ValueError('capture cannot be later than assessment review')
        if a.get('recommendation') not in ('Watch', 'Listen', 'Read', 'Skim', 'Skip', 'Unknown') or a.get('value') not in ('high', 'moderate', 'low', 'unknown') or a.get('confidence') not in ('high', 'medium', 'low'):
            raise ValueError('invalid assessment grade')
        if record['coverage'] in ('metadata_only', 'prior_note') and (a['recommendation'] != 'Unknown' or a['value'] != 'unknown' or a['confidence'] != 'low'):
            raise ValueError('insufficient source coverage for firm grade')
        if not isinstance(a.get('novelty'), list):
            raise ValueError('invalid novelty')
        for n in a['novelty']:
            for k in ('idea', 'evidence', 'prior_evidence'):
                text(n.get(k), k)
            if n.get('bucket') not in ('new', 'reinforcement', 'repetition', 'unknown'):
                raise ValueError('invalid novelty bucket')
            if record['coverage'] in ('full_text', 'full_transcript') and ' '.join(n['evidence'].split()).casefold() not in ' '.join(record['source_text'].split()).casefold():
                raise ValueError('novelty quote absent from source text')
            strings(n.get('compared_with'), 'comparison IDs')
            if n['bucket'] in ('reinforcement', 'repetition') and not n['compared_with']:
                raise ValueError('prior source required for overlap')
            if record['coverage'] in ('metadata_only', 'prior_note') and n['bucket'] != 'unknown':
                raise ValueError('insufficient coverage for novelty')
        c = a.get('credibility')
        if not isinstance(c, dict):
            raise ValueError('credibility required')
        for k in ('topic', 'judgment', 'comparison'):
            text(c.get(k), k)
        strings(c.get('unknowns'), 'credibility unknowns')
        if not isinstance(c.get('evidence'), list):
            raise ValueError('credibility evidence required')
        for k in ('established', 'comparison_established'):
            if type(c.get(k, False)) is not bool:
                raise ValueError('credibility ' + k + ' must be boolean')
        if c.get('comparison_established', False) and not c.get('established', False):
            raise ValueError('established comparison requires established credibility')
        strings(c.get('compared_sources', []), 'credibility comparison IDs')
        if (c.get('established', False) or c.get('comparison_established', False)) and not c['evidence']:
            raise ValueError('established credibility requires cited evidence')
        if c.get('comparison_established', False) and not c.get('compared_sources'):
            raise ValueError('established comparison requires prior sources')
        for e in c['evidence']:
            text(e.get('claim'), 'credibility claim')
            https_url(e.get('url'))
            if timestamp(e.get('checked_at')) > timestamp(a['reviewed_at']):
                raise ValueError('citation checked after assessment review')
    allowed = ('id', 'realm', 'kind', 'title', 'author', 'url', 'captured_at', 'duration_minutes', 'coverage', 'summary', 'ideas', 'tools', 'assessment', 'note_path', 'action', 'action_state', 'source_text')
    return {k: copy.deepcopy(record.get(k)) for k in allowed}


def strict_record(record, realm):
    """Closed persisted schema; no consumption/mastery or arbitrary payloads."""
    def shape(value, keys, field):
        if not isinstance(value, dict) or set(value) - set(keys.split()):
            raise ValueError('invalid or unsupported ' + field + ' fields')
    shape(record, 'id realm kind title author url captured_at duration_minutes coverage summary ideas tools assessment note_path action action_state source_text', 'record')
    assessment = record.get('assessment')
    if assessment is not None:
        shape(assessment, 'recommendation value confidence rationale time_guidance reviewed_at novelty credibility', 'assessment')
        novelty = assessment.get('novelty')
        if not isinstance(novelty, list):
            raise ValueError('invalid novelty')
        for entry in novelty:
            shape(entry, 'idea bucket evidence compared_with prior_evidence', 'novelty')
        credibility = assessment.get('credibility')
        shape(credibility, 'topic judgment comparison unknowns established comparison_established compared_sources evidence', 'credibility')
        if not isinstance(credibility.get('evidence'), list):
            raise ValueError('invalid credibility evidence')
        for entry in credibility['evidence']:
            shape(entry, 'claim url checked_at', 'citation')
    if not isinstance(record.get('tools'), list):
        raise ValueError('invalid tools')
    for entry in record['tools']:
        shape(entry, 'name purpose source_evidence kind origin decision source_anchor chapter_anchor verification_status verification_date official_docs_url pricing security relevance', 'tool')
    validated = validate_record(record, realm)
    if assessment:
        lists = [n['compared_with'] for n in assessment['novelty']] + [assessment['credibility'].get('compared_sources', [])]
        for identifiers in lists:
            if len(set(identifiers)) != len(identifiers):
                raise ValueError('duplicate comparison IDs')
    return validated


def public_text(value):
    """Limited pattern guard, not a guarantee against arbitrary unlabelled secrets."""
    def safe_text_url(match):
        try:
            return https_url(match[0])
        except ValueError:
            return '[unsafe URL omitted]'
    value = re.sub(r'https?://[^\s`<>"\']+', safe_text_url, value, flags=re.I)
    value = re.sub(r'''(?i)(["'])(?:[a-z]:[\\/]|\\\\|file://|/|~/)[^\r\n]*?\1''', '[local path omitted]', value)
    # Unquoted paths may contain spaces: omit the ambiguous line tail as well.
    value = re.sub(r'(?i)(?:(?<!\w)[a-z]:[\\/]|\\\\|file://|(?<![:/\w])/(?!/)|~/)[^\r\n`<>"\']+', '[local path omitted]', value)
    value = re.sub(r'(?i)\b(?:api[_ -]?key|password|secret|(?:access[_ -]?|refresh[_ -]?|auth[_ -]?)?token|session[_ -]?id)\s*[:=]\s*(?:"[^"\n]*"|\'[^\'\n]*\'|[^\s,;]+)', '[credential/session assignment omitted]', value)
    value = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~-]+', '[credential omitted]', value)
    return value


def public_projection(value, key=None):
    if isinstance(value, dict):
        return {k: public_projection(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [public_projection(v, key) for v in value]
    if isinstance(value, str) and key not in ('id', 'source_id', 'compared_with', 'compared_sources', 'tools', 'url', 'docs_url', 'obsidian_uri'):
        return public_text(value)
    return value


def build_snapshot(records, notes_root, vault_name, generated_at, realm):
    if realm not in ('personal', 'work'):
        raise ValueError('explicit realm required')
    generated = timestamp(generated_at)
    root = no_links(Path(notes_root).absolute()).resolve()
    sources = []
    aggregated = {}
    ids = set()
    originals, prior_content = {}, {}
    for raw in records:
        r = validate_record(raw, realm)
        if timestamp(r['captured_at']) > generated or (r['assessment'] and timestamp(r['assessment']['reviewed_at']) > generated):
            raise ValueError('capture or review later than snapshot generated_at')
        if r['id'] in ids:
            raise ValueError('duplicate source ID')
        ids.add(r['id'])
        originals[r['id']] = r
        captured = timestamp(r['captured_at'])
        available = timestamp(r['assessment']['reviewed_at']) if r['assessment'] else captured
        pieces = [(piece, available) for piece in [r.get('source_text') or ''] + r['ideas']] if r['coverage'] != 'metadata_only' else []
        note_text, uri = '', None
        if r['note_path'] is not None:
            note = scoped_path(Path(r['note_path']), root)
            if not note.is_relative_to(root):
                raise ValueError('note path escapes approved root')
            before = note.stat()
            note_text = note.read_text(encoding='utf-8')
            after = note.stat()
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise ValueError('note changed during read; retry snapshot')
            note_text = re.sub(r'\A\ufeff?---\r?\n[\s\S]*?\r?\n---(?:\r?\n|\Z)', '', note_text)
            # Current note text is authoritative, but no old version is inferred.
            if r['coverage'] != 'metadata_only':
                pieces.append((note_text, max(captured, dt.datetime.fromtimestamp(after.st_mtime, dt.timezone.utc))))
            # The approved notes root is inside this vault; vault path comes from config.
            rel = (Path(root.name) / note.relative_to(root)).as_posix()
            if public_text(vault_name) == vault_name and public_text(rel) == rel:
                uri = 'obsidian://open?vault=' + quote(vault_name, safe='') + '&file=' + quote(rel, safe='')
        prior_content[r['id']] = pieces
        source = {k: r[k] for k in ('id', 'realm', 'kind', 'title', 'author', 'url', 'captured_at', 'duration_minutes', 'coverage', 'summary', 'ideas')}
        # Projection-only metadata from the same retained evidence used below.
        # Never trust a raw marker or expose private source_text to the browser.
        evidence_times = [available for piece, available in pieces if piece.strip()]
        source['prior_evidence_available_at'] = min(evidence_times).isoformat() if evidence_times else None
        assessment = r['assessment']
        if assessment:
            assessment = {k: assessment[k] for k in ('recommendation', 'value', 'confidence', 'rationale', 'time_guidance', 'reviewed_at')}
            assessment['novelty'] = [{k: n[k] for k in ('idea', 'bucket', 'evidence', 'compared_with', 'prior_evidence')} for n in r['assessment']['novelty']]
            c = r['assessment']['credibility']
            assessment['credibility'] = {k: c[k] for k in ('topic', 'judgment', 'comparison', 'unknowns')}
            assessment['credibility'].update(established=c.get('established', False), comparison_established=c.get('comparison_established', False), compared_sources=c.get('compared_sources', []))
            if not c.get('established', False):
                assessment['credibility']['judgment'] = 'Not established'
            if not c.get('comparison_established', False):
                assessment['credibility']['comparison'] = 'Not established'
            assessment['credibility']['evidence'] = [{k: e[k] for k in ('claim', 'url', 'checked_at')} for e in c['evidence']]
        source.update(assessment=assessment, note_text=note_text, obsidian_uri=uri, status='assessed' if assessment else 'captured', action=r.get('action'), action_state=r.get('action_state'), tools=[])
        for t in r['tools']:
            name, kind = text(t.get('name'), 'tool name'), t.get('kind')
            if kind not in ('platform', 'MCP', 'CLI', 'library', 'other', 'unclear'):
                raise ValueError('invalid tool kind')
            origin = t.get('origin')
            if origin not in ('video', 'source', 'assistant_suggestion', 'unclear'):
                raise ValueError('invalid tool provenance')
            text(t.get('source_evidence'), 'tool evidence')
            text(t.get('purpose'), 'tool purpose')
            if t.get('decision') not in ('investigate', 'already use', 'skip', 'unclear'):
                raise ValueError('invalid tool decision')
            docs = t.get('official_docs_url')
            if docs:
                https_url(docs)
            key = (name.casefold(), kind)
            ident = 'tool:' + hashlib.sha256((key[0] + '|' + key[1]).encode()).hexdigest()[:16]
            entry = aggregated.setdefault(key, {'id': ident, 'name': name, 'kind': kind, 'mentions': []})
            entry['name'] = min(entry['name'], name)  # stable lexical spelling, not first-input precedence
            mention = {'source_id': r['id'], 'origin': origin, 'purpose': t['purpose'], 'evidence': t['source_evidence'], 'anchor': t.get('source_anchor') or t.get('chapter_anchor'), 'verification': t.get('verification_status', 'Not checked'), 'verification_date': t.get('verification_date'), 'docs_url': docs, 'pricing': t.get('pricing', 'unknown'), 'security': t.get('security', 'unknown'), 'decision': t['decision'], 'relevance': t.get('relevance', 'unknown')}
            entry['mentions'].append(mention)
            source['tools'].append(ident)
        sources.append(source)
    for s in sources:
        if s['assessment']:
            for ident in s['assessment']['credibility']['compared_sources']:
                if ident not in ids or ident == s['id']:
                    raise ValueError('credibility comparison requires another recorded source')
                if timestamp(originals[ident]['captured_at']) > timestamp(s['assessment']['reviewed_at']):
                    raise ValueError('credibility source captured after assessment review')
                if not any(piece.strip() and available <= timestamp(s['assessment']['reviewed_at']) for piece, available in prior_content[ident]):
                    raise ValueError('credibility comparison requires usable prior content')
            for n in s['assessment']['novelty']:
                if any(i not in ids or i == s['id'] for i in n['compared_with']):
                    raise ValueError('comparison must reference another recorded source')
                for ident in n['compared_with']:
                    prior = originals[ident]
                    if timestamp(prior['captured_at']) > timestamp(s['assessment']['reviewed_at']):
                        raise ValueError('comparison source captured after assessment review')
                    normalize = lambda value: ' '.join(value.split()).casefold()
                    if not any(normalize(n['prior_evidence']) in normalize(piece) for piece, available in prior_content[ident] if piece.strip() and available <= timestamp(s['assessment']['reviewed_at'])):
                        raise ValueError('prior evidence quote absent from usable prior content')
    sources.sort(key=lambda s: (timestamp(s['captured_at']), s['id']), reverse=True)
    tools = sorted(aggregated.values(), key=lambda t: (t['name'].casefold(), t['kind']))
    for t in tools:
        t['mentions'].sort(key=lambda m: (m['source_id'], m['origin'], m['evidence'], json.dumps(m, ensure_ascii=True, sort_keys=True, allow_nan=False)))
    counts = {'sources': len(sources), 'assessed': sum(s['status'] == 'assessed' for s in sources), 'captured': sum(s['status'] == 'captured' for s in sources), 'ideas': sum(len(s['ideas']) for s in sources), 'open_actions': sum(bool(s['action']) and s['action_state'] == 'open' for s in sources), 'tool_leads': len(tools), 'investigate_leads': sum(any(m['decision'] == 'investigate' for m in t['mentions']) for t in tools)}
    return public_projection({'schema_version': SCHEMA, 'realm': realm, 'generated_at': generated_at, 'library_limits': 'Comparison covers recorded sources only, not everything the learner knows. Captured does not mean learned. Credibility is topic-specific; missing evidence is unknown. Sensitive-text cleanup is a limited pattern guard, not a guarantee against arbitrary secrets.', 'sources': sources, 'tools': tools, 'counts': counts})


def no_links(path):
    """Reject symlink/junction ancestry, including an explicitly chosen root."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute path without traversal required for approved scope')
    for current in (path, *path.parents):
        if current.is_symlink() or current.is_junction():
            raise ValueError('symlink or junction escapes approved scope')
    return path


def scoped_path(path, root):
    """Check the target and every intermediate ancestor before any IO."""
    path, root = no_links(Path(path).absolute()), no_links(Path(root).absolute())
    if not path.is_relative_to(root):
        raise ValueError('path escapes approved scope')
    current = path
    while True:
        if not current.resolve().is_relative_to(root):
            raise ValueError('resolved path escapes approved scope')
        if current == root:
            break
        current = current.parent
    return path.resolve()


def compare_candidates(candidate, library):
    def tokens(value):
        stop = {'this', 'that', 'with', 'from', 'your', 'what', 'have', 'into', 'does', 'when', 'more', 'than', 'which', 'only', 'about', 'before'}
        return {w for w in re.findall(r'[a-z]{4,}', value.casefold()) if w not in stop}
    query = tokens(' '.join(candidate.get('ideas', []) + candidate.get('summary', [])))
    matches = []
    for r in library:
        if r['id'] == candidate['id']:
            continue
        ideas = r.get('ideas', [])
        overlap = query & tokens(' '.join(ideas + r.get('summary', [])))
        if overlap:
            matches.append({'source_id': r['id'], 'title': r['title'], 'author': r['author'], 'matching_terms': sorted(overlap), 'recorded_ideas': ideas})
    matches.sort(key=lambda r: (-len(r['matching_terms']), r['source_id']))
    return {'limits': 'Lexical candidates only: not semantic equivalence, mastery, personal novelty or source credibility. Hermes must read and compare the cited sources.', 'candidates': matches[:10]}


def refresh(snapshot, template_path, output_path, *, project_root=None):
    project = no_links(Path(project_root or ROOT).absolute()).resolve()
    output = scoped_path(output_path, project)
    timestamp(snapshot.get('generated_at'))
    output.parent.mkdir(parents=True, exist_ok=True)
    scoped_path(output, project)
    lock = scoped_path(output.with_name(output.name + '.lock'), project)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('refresh lock held; another refresh may be in progress') from None
    try:
        os.close(descriptor)
        return _refresh_locked(snapshot, template_path, output, project_root=project)
    finally:
        lock.unlink(missing_ok=True)


def _data_container(html):
    """Require one real, closed application/json script with the expected ID."""
    class Parser(HTMLParser):
        def __init__(self):
            # The dashboard requires scripting; noscript contents are text.
            super().__init__(convert_charrefs=False, scripting=True)
            self.count, self.active, self.closed, self.data = 0, False, False, ''
            self.template_depth = 0
        def handle_starttag(self, tag, attrs):
            if tag == 'template':
                self.template_depth += 1
            values = dict(attrs)
            if values.get('id') == 'praxis-data':
                self.count += 1
                if self.template_depth or tag != 'script' or values.get('type') != 'application/json' or len(values) != len(attrs):
                    raise ValueError('invalid praxis-data JSON script container')
                self.active = True
        def handle_startendtag(self, tag, attrs):
            # HTML ignores the self-closing slash on these non-void elements.
            self.handle_starttag(tag, attrs)
            if tag in self.CDATA_CONTENT_ELEMENTS or tag in ('noscript', 'plaintext'):
                self.set_cdata_mode(tag)
            elif tag in self.RCDATA_CONTENT_ELEMENTS:
                self.set_cdata_mode(tag, escapable=True)
        def handle_endtag(self, tag):
            if tag == 'template' and self.template_depth:
                self.template_depth -= 1
            if tag == 'script' and self.active:
                self.active, self.closed = False, True
        def handle_data(self, data):
            if self.active:
                self.data += data
    parser = Parser()
    parser.feed(html)
    parser.close()
    if parser.count != 1 or parser.active or not parser.closed:
        raise ValueError('expected exactly one closed praxis-data JSON script container')
    return parser.data


def _atomic_bytes(data, output, project):
    """Stage, flush/fsync, replace; errors leave no temporary files."""
    staging = None
    try:
        stream = tempfile.NamedTemporaryFile(dir=output.parent, prefix='.praxis-', suffix='.tmp', delete=False)
        staging = Path(stream.name)
        with stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        scoped_path(staging, project)
        scoped_path(output, project)
        os.replace(staging, output)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


def _refresh_locked(snapshot, template_path, output_path, *, project_root):
    """Reserve generation durably BEFORE replacing HTML, under refresh's lock.

    <output>.watermark.json schema 1 binds realm/output, generation, prior and
    reserved HTML SHA256. Either hash is valid after a partial transaction. A
    failed HTML write may advance the watermark: retry at the same/newer time.
    Missing metadata for existing HTML requires operator recovery, not guessing.
    File fsync + atomic replace provides normal process-failure durability; no
    claim is made about filesystem/controller guarantees during power loss.
    """
    project = no_links(Path(project_root).absolute()).resolve()
    output = scoped_path(output_path, project)
    watermark = scoped_path(output.with_name(output.name + '.watermark.json'), project)
    template = Path(template_path).read_text(encoding='utf-8')
    if template.count('%%PRAXIS_DATA%%') != 1:
        raise ValueError('template must have exactly one data token')
    if _data_container(template).strip() != '%%PRAXIS_DATA%%':
        raise ValueError('data token must fill praxis-data JSON script container')
    generation = timestamp(snapshot.get('generated_at'))
    realm = snapshot.get('realm')
    if realm not in ('personal', 'work'):
        raise ValueError('explicit realm required')
    def encode(value):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    payload = encode(snapshot)
    previous_bytes = output.read_bytes() if output.exists() else None
    previous_digest = hashlib.sha256(previous_bytes).hexdigest() if previous_bytes is not None else None
    old = None
    if previous_bytes is not None:
        old = json.loads(_data_container(previous_bytes.decode('utf-8')))
        if not isinstance(old, dict) or old.get('realm') != realm:
            raise ValueError('invalid previous snapshot realm/data')
        old_generation = timestamp(old.get('generated_at'))
    if watermark.exists():
        metadata = json.loads(watermark.read_text(encoding='utf-8'))
        keys = {'schema_version', 'realm', 'output', 'generated_at', 'html_sha256', 'reserved_sha256'}
        if not isinstance(metadata, dict) or set(metadata) != keys or type(metadata['schema_version']) is not int or metadata['schema_version'] != 1 or metadata['realm'] != realm or metadata['output'] != output.relative_to(project).as_posix():
            raise ValueError('invalid scoped watermark metadata')
        for key in ('html_sha256', 'reserved_sha256'):
            value = metadata[key]
            if (key == 'html_sha256' and value is None):
                continue
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('invalid watermark hash')
        floor = timestamp(metadata['generated_at'])
        if previous_digest not in (metadata['html_sha256'], metadata['reserved_sha256']) or (old is not None and old_generation > floor):
            raise ValueError('watermark inconsistent with last good HTML')
        if generation < floor:
            raise ValueError('older generated snapshot cannot replace newer watermark')
    elif previous_bytes is not None:
        raise ValueError('watermark metadata missing for existing output')
    html = template.replace('%%PRAXIS_DATA%%', payload).encode('utf-8')
    if old is not None:
        stable = copy.deepcopy(snapshot)
        stable['generated_at'] = old['generated_at']
        if template.replace('%%PRAXIS_DATA%%', encode(stable)).encode('utf-8') == previous_bytes:
            html = previous_bytes
    digest = hashlib.sha256(html).hexdigest()
    reservation = {'schema_version': 1, 'realm': realm, 'output': output.relative_to(project).as_posix(), 'generated_at': snapshot['generated_at'], 'html_sha256': previous_digest, 'reserved_sha256': digest}
    # No HTML change can become visible until its freshness floor is persisted.
    _atomic_bytes(json.dumps(reservation, sort_keys=True, allow_nan=False).encode('utf-8'), watermark, project)
    unchanged = html == previous_bytes
    if not unchanged:
        _atomic_bytes(html, output, project)
    return {'unchanged': unchanged, 'sha256': digest, 'path': str(output)}
