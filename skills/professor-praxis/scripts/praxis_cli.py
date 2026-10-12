"""Explicit, local Professor Praxis workspaces. Python 3.14+, stdlib only."""
import sys
sys.dont_write_bytecode = True
if sys.version_info < (3, 14):
    raise SystemExit('Professor Praxis requires Python 3.14 or newer')
import argparse
import datetime as dt
import json
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
import praxis_engine as engine

SCRIPTS = Path(__file__).absolute().parent
ORIGIN = '.praxis-install-origin.json'


def release_marker(root):
    """Recognize only this release layout, without walking directory contents."""
    markers = ('install_skill.py', 'README.md', 'LICENSE.md', 'skills/professor-praxis/SKILL.md')
    return all(engine.no_links(root / marker).is_file() for marker in markers)


def source_release():
    engine.no_links(SCRIPTS / 'praxis_cli.py')
    engine.no_links(SCRIPTS / 'praxis_engine.py')
    skill = engine.no_links(SCRIPTS.parent)
    origin = engine.no_links(skill / ORIGIN)
    if origin.exists():
        if not origin.is_file():
            raise ValueError('invalid local install-origin file')
        value = read_json(origin)
        keys = {'schema_version', 'source_release', 'installed_skill'}
        if not isinstance(value, dict) or set(value) != keys or type(value['schema_version']) is not int or value['schema_version'] != 1:
            raise ValueError('invalid local install-origin schema')
        paths = {}
        for key in ('source_release', 'installed_skill'):
            raw = engine.text(value[key], 'install-origin ' + key)
            if any(ord(c) < 32 or ord(c) == 127 for c in raw):
                raise ValueError('invalid install-origin path')
            path = explicit_root(raw)
            if str(path) != raw or path.resolve() != path:
                raise ValueError('install-origin paths must be canonical')
            paths[key] = path
        if paths['installed_skill'] != skill or overlaps(paths['source_release'], skill):
            raise ValueError('invalid local install-origin binding')
        return paths['source_release']
    # Direct repository execution is the only provenance-free write mode.
    repository = SCRIPTS.parents[2]
    if skill == repository / 'skills/professor-praxis' and release_marker(repository):
        return repository
    raise ValueError('local install-origin missing; reinstall from the release source')


def overlaps(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def read_json(path):
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate JSON key: ' + key)
            value[key] = item
        return value
    def nonfinite(value):
        raise ValueError('nonfinite JSON value forbidden: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object, parse_constant=nonfinite)


def explicit_root(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or path == Path(path.anchor):
        raise ValueError('explicit absolute non-root path without traversal required')
    return engine.no_links(path)


def check_roots(workspace, notes):
    explicit_root(workspace)
    explicit_root(notes)
    if workspace.is_relative_to(notes) or notes.is_relative_to(workspace):
        raise ValueError('workspace and notes root must be disjoint')
    skill = SCRIPTS.parent
    if workspace.is_relative_to(skill) or skill.is_relative_to(workspace):
        raise ValueError('workspace cannot overlap installed skill')
    if notes.is_relative_to(skill) or skill.is_relative_to(notes):
        raise ValueError('notes root cannot overlap installed skill')
    repository = source_release()
    for name, path in (('workspace', workspace), ('notes root', notes)):
        if overlaps(path, repository):
            raise ValueError(name + ' cannot overlap source release repository')
        for ancestor in (path, *path.parents):
            if ancestor == Path(ancestor.anchor):
                break
            if release_marker(ancestor):
                raise ValueError(name + ' cannot be inside a recognizable release repository')
    if not workspace.parent.is_dir() or not notes.parent.is_dir():
        raise ValueError('chosen roots must have existing parent directories')
    if workspace.exists() and not workspace.is_dir() or notes.exists() and not notes.is_dir():
        raise ValueError('chosen roots must be directories')


def config(workspace):
    engine.scoped_path(workspace / 'config.json', workspace)
    cfg = read_json(workspace / 'config.json')
    required = {'schema_version', 'workspace', 'notes_root', 'vault_name', 'realm'}
    if not isinstance(cfg, dict) or set(cfg) != required or type(cfg['schema_version']) is not int or cfg['schema_version'] != 1:
        raise ValueError('invalid workspace config schema')
    if cfg['workspace'] != str(workspace) or cfg['realm'] not in ('personal', 'work'):
        raise ValueError('workspace config binding or realm mismatch')
    engine.text(cfg['vault_name'], 'vault name')
    check_roots(workspace, explicit_root(cfg['notes_root']))
    if not Path(cfg['notes_root']).is_dir():
        raise ValueError('approved notes root is absent')
    for path in ('learning', 'learning/' + cfg['realm'], 'learning/' + cfg['realm'] + '/praxis/assessments', 'dashboard', '.praxis.lock'):
        engine.scoped_path(workspace / path, workspace)
    return cfg


def records(workspace, cfg):
    store = engine.scoped_path(workspace / 'learning' / cfg['realm'] / 'praxis/assessments', workspace)
    if not store.is_dir():
        raise ValueError('assessment store is missing; not an empty library')
    if (workspace / 'learning' / cfg['realm'] / 'log.jsonl').exists():
        raise ValueError('legacy log.jsonl input is unsupported; migrate explicitly outside this CLI')
    result = []
    for path in sorted(store.glob('*.json')):
        record = engine.strict_record(read_json(engine.scoped_path(path, workspace)), cfg['realm'])
        if path.name != assessment_filename(record['id']):
            raise ValueError('noncanonical assessment filename; use save, not manual store copies')
        result.append(record)
    if len({r['id'] for r in result}) != len(result):
        raise ValueError('duplicate assessment ID')
    engine.build_snapshot(result, cfg['notes_root'], cfg['vault_name'], dt.datetime.now(dt.timezone.utc).isoformat(), cfg['realm'])
    return result


def snapshot(workspace, cfg):
    return engine.build_snapshot(records(workspace, cfg), cfg['notes_root'], cfg['vault_name'], dt.datetime.now(dt.timezone.utc).isoformat(), cfg['realm'])


def render(workspace, cfg):
    snap = snapshot(workspace, cfg)
    result = engine.refresh(snap, SCRIPTS / 'dashboard.html', workspace / 'dashboard/index.html', project_root=workspace)
    return dict(result, counts=snap['counts'])


@contextmanager
def workspace_lock(workspace):
    lock = engine.scoped_path(workspace / '.praxis.lock', workspace)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('workspace lock held; operator recovery required if stale') from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def initialize(workspace, notes, vault, realm):
    check_roots(workspace, notes)
    engine.text(vault, 'vault name')
    if workspace.exists() and not (workspace / 'config.json').exists() and any(workspace.iterdir()):
        raise ValueError('refusing nonempty uninitialized workspace')
    cfg = {'schema_version': 1, 'workspace': str(workspace), 'notes_root': str(notes), 'vault_name': vault, 'realm': realm}
    workspace.mkdir(exist_ok=True)
    with workspace_lock(workspace):
        path = workspace / 'config.json'
        if path.exists():
            if config(workspace) != cfg:
                raise ValueError('incompatible workspace configuration')
        else:
            notes.mkdir(exist_ok=True)
            (workspace / 'learning' / realm / 'praxis/assessments').mkdir(parents=True, exist_ok=True)
            engine._atomic_bytes(json.dumps(cfg, indent=2).encode('utf-8'), path, workspace)
        return render(workspace, cfg)


def assessment_filename(source_id):
    return hashlib.sha256(source_id.encode('utf-8')).hexdigest() + '.json'


def save(workspace, cfg, candidate):
    library = records(workspace, cfg)
    previous = next((r for r in library if r['id'] == candidate['id']), None)
    if previous:
        for key in ('realm', 'kind', 'url', 'title', 'author', 'captured_at', 'action_state'):
            if previous.get(key) != candidate.get(key):
                raise ValueError('immutable source identity/history conflict: ' + key)
        if previous.get('note_path') is not None and candidate.get('note_path') != previous['note_path']:
            raise ValueError('immutable approved note binding conflict: note_path')
        if previous['assessment']:
            if not candidate['assessment'] or engine.timestamp(candidate['assessment']['reviewed_at']) < engine.timestamp(previous['assessment']['reviewed_at']):
                raise ValueError('assessment cannot erase or backdate prior review')
    elif candidate.get('action_state') not in (None, 'open'):
        raise ValueError('save cannot record action application or consumption')
    proposed = [r for r in library if r['id'] != candidate['id']] + [candidate]
    engine.build_snapshot(proposed, cfg['notes_root'], cfg['vault_name'], dt.datetime.now(dt.timezone.utc).isoformat(), cfg['realm'])
    filename = assessment_filename(candidate['id'])
    path = workspace / 'learning' / cfg['realm'] / 'praxis/assessments' / filename
    engine._atomic_bytes(json.dumps(candidate, indent=2, allow_nan=False).encode('utf-8'), path, workspace)
    return {'saved': True, 'source_id': candidate['id'], 'path': str(path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init')
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--notes-root', type=Path, required=True)
    p.add_argument('--vault-name', required=True)
    p.add_argument('--realm', choices=('personal', 'work'), default='personal')
    for name in ('status', 'refresh'):
        p = sub.add_parser(name)
        p.add_argument('--workspace', type=Path, required=True)
    p = sub.add_parser('validate')
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--realm', choices=('personal', 'work'), required=True)
    for name in ('compare', 'save'):
        p = sub.add_parser(name)
        p.add_argument('--workspace', type=Path, required=True)
        p.add_argument('--record', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            candidate = engine.strict_record(read_json(args.record), args.realm)
            print(json.dumps({'valid': True, 'source_id': candidate['id'], 'coverage': candidate['coverage']}))
            return 0
        workspace = explicit_root(args.workspace)
        if args.command == 'init':
            result = initialize(workspace, explicit_root(args.notes_root), args.vault_name, args.realm)
        else:
            # Scope/provenance validation must precede even the lock write.
            config(workspace)
            with workspace_lock(workspace):
                cfg = config(workspace)
                if args.command in ('save', 'compare'):
                    candidate = engine.strict_record(read_json(args.record), cfg['realm'])
                    result = save(workspace, cfg, candidate) if args.command == 'save' else engine.compare_candidates(candidate, records(workspace, cfg))
                elif args.command == 'refresh':
                    result = render(workspace, config(workspace))
                else:
                    result = {'counts': snapshot(workspace, config(workspace))['counts'], 'workspace': str(workspace)}
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        print(json.dumps({'error': str(exc), 'last_good_preserved': True}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
