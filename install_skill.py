"""Copy the self-contained skill into an explicitly selected Hermes home.

No network, credentials, global configuration changes or automatic overwrites.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

ROOT = Path(__file__).absolute().parent
IGNORE_DIRS = {'__pycache__', '.git', '.pytest_cache'}
MANIFEST = ('SKILL.md', 'LICENSE.md', 'references/record-contract.md',
            'references/metadata-record.json', 'scripts/praxis_engine.py',
            'scripts/praxis_cli.py', 'scripts/dashboard.html')

def no_links(path):
    """Inspect lexical ancestry before resolve or any destination write."""
    if '..' in path.parts:
        raise ValueError('installation paths must not contain traversal')
    for entry in (path, *path.parents):
        if entry.is_symlink() or entry.is_junction():
            raise ValueError('symlink or junction in installation path')
        try:
            attributes = entry.lstat().st_file_attributes if os.name == 'nt' else 0
        except FileNotFoundError:
            continue
        if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('reparse point in installation path')
    return path

def install(hermes_home, *, source=None):
    source = no_links(Path(source or ROOT / 'skills/professor-praxis').absolute())
    if not source.is_dir():
        raise ValueError('a regular skill directory with SKILL.md is required')
    # Inspect entries without following links; validate the complete package
    # before creating any destination. Arbitrary Markdown is not package code.
    pending, seen = [source], set()
    while pending:
        directory = pending.pop()
        for entry in directory.iterdir():
            no_links(entry)
            relative = entry.relative_to(source)
            ignored = any(part in IGNORE_DIRS for part in relative.parts)
            if entry.is_dir():
                if not ignored and relative.as_posix() not in ('scripts', 'references'):
                    raise ValueError('unexpected non-source directory in skill: ' + relative.as_posix())
                pending.append(entry)
            elif entry.is_file():
                if ignored:
                    continue
                if relative.as_posix() not in MANIFEST:
                    raise ValueError('unexpected non-source/package file in skill: ' + relative.as_posix())
                seen.add(relative.as_posix())
            else:
                raise ValueError('regular package file required: ' + relative.as_posix())
    if seen != set(MANIFEST):
        raise ValueError('incomplete skill package: missing canonical manifest files')
    source = source.resolve()
    release = source.parent.parent if source.name == 'professor-praxis' and source.parent.name == 'skills' else source
    home = no_links(Path(hermes_home).expanduser().absolute())
    home = home.resolve()
    if home.is_relative_to(release) or release.is_relative_to(home):
        raise ValueError('source and destination must not contain each other')
    parent = no_links(home / 'skills')
    if parent.is_symlink() or not parent.resolve().is_relative_to(home):
        raise ValueError('skills directory escapes the selected home')
    target = parent / 'professor-praxis'
    if target.exists() or target.is_symlink():
        raise ValueError('skill already exists; no files were overwritten')
    no_links(target)
    parent.mkdir(parents=True, exist_ok=True)
    lock = parent / '.professor-praxis-install.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('installation is busy; do not remove its lock automatically') from None
    stage = None
    try:
        os.close(fd)
        if target.exists() or target.is_symlink():
            raise ValueError('skill already exists; no files were overwritten')
        no_links(target)
        stage = Path(tempfile.mkdtemp(prefix='.praxis-install-', dir=parent))
        for relative in MANIFEST:
            entry = no_links(source / relative)
            destination = stage / 'professor-praxis' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, destination)
        # Generated locally, never an input to the seven-file release manifest.
        # Canonical source ancestry was checked before resolving above. Preserve
        # its lexical boundary even if that release is later moved or removed.
        origin = {'schema_version': 1, 'source_release': str(release), 'installed_skill': str(target)}
        (stage / 'professor-praxis/.praxis-install-origin.json').write_text(
            json.dumps(origin, indent=2, allow_nan=False), encoding='utf-8')
        os.rename(stage / 'professor-praxis', target)
        return {'installed_to': str(target), 'workspace_created': False, 'configuration_changed': False}
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        lock.unlink(missing_ok=True)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hermes-home', required=True, type=Path, help='Explicit active profile home; never inferred from another machine')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(install(args.hermes_home), indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'error': str(error)}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
