"""Mirror managed sources into Git; preserve repository and release files."""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import tempfile
from build import ROOT,release_assets,inside

DOCUMENTS=('.gitignore','.gitattributes','VERSION','CHANGELOG.md','BUILDING.md',
           'PROJECT-VERSIONS.md','README.txt','requirements.txt','requirements-build.txt','Start-Loona.cmd')
MANAGED_DIRECTORIES=('assets','tests','packaging')
PROTECTED_ROOT_NAMES={'.git','.github','dist','release','releases','RELEASE-ARTIFACTS.json'}
PROTECTED_PREFIXES=('social-preview','release','github','publish')

def protected_name(name):
    return name in PROTECTED_ROOT_NAMES or name.lower().startswith(PROTECTED_PREFIXES)

def managed_root_file(name):
    return not protected_name(name) and (name in DOCUMENTS or name.endswith('.py'))

def linked(path):
    return path.is_symlink() or path.is_junction()

def checked_path(root,relative):
    root=Path(root).resolve()
    relative=Path(relative)
    target=inside(root/relative,root)
    current=root
    for part in relative.parts:
        current=current/part
        if linked(current):raise ValueError(f'Refusing managed link/junction: {current}')
    return target

def tree_files(folder):
    if not folder.exists():return []
    if linked(folder):raise ValueError(f'Refusing managed link/junction: {folder}')
    if not folder.is_dir():raise ValueError(f'Expected managed directory: {folder}')
    files=[]
    for parent,dirs,names in os.walk(folder,followlinks=False):
        for name in dirs+names:
            path=Path(parent)/name
            if name in ('.git','.github') or linked(path):
                raise ValueError(f'Refusing repository state or link in managed directory: {path}')
        files.extend(Path(parent)/name for name in names)
    return files

def source_files(root=ROOT):
    root=Path(root).resolve()
    files=[Path(name) for name in DOCUMENTS if (root/name).is_file()]
    files.extend(p.relative_to(root) for p in root.glob('*.py')
                 if not protected_name(p.name) and not p.name.startswith('test'))
    for folder in ('tests','packaging'):
        files.extend(p.relative_to(root) for p in tree_files(root/folder)
                     if '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo','.tmp','.log','.bak'))
    files.extend(release_assets(root))
    for relative in files:
        if not checked_path(root,relative).is_file():raise FileNotFoundError(root/relative)
    if not (root/'main.py').is_file() or not (root/'VERSION').is_file():
        raise ValueError('Source must contain main.py and VERSION')
    return sorted(set(files))

def managed_files(root):
    root=Path(root).resolve()
    files=[]
    if not root.exists():return set()
    for child in root.iterdir():
        if child.name in MANAGED_DIRECTORIES:
            files.extend(p.relative_to(root) for p in tree_files(child))
        elif managed_root_file(child.name):
            checked_path(root,child.name)
            if not child.is_file():raise ValueError(f'Expected managed root file: {child}')
            files.append(Path(child.name))
    return set(files)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def preserved_snapshot(root):
    """Hash unowned files including .git; do not follow links."""
    root=Path(root)
    result={}
    def record(path):
        relative=path.relative_to(root).as_posix()
        if linked(path):result[relative]='link:'+os.readlink(path)
        elif path.is_file():result[relative]=digest(path)
        else:
            result[relative]='directory'
            for child in path.iterdir():record(child)
    if root.exists():
        for child in root.iterdir():
            if child.name not in MANAGED_DIRECTORIES and not managed_root_file(child.name):record(child)
    return result

def synchronize(source,destination,apply=False):
    source=Path(source).resolve()
    destination=Path(destination).absolute()
    if linked(destination):raise ValueError('Destination must not be a link/junction')
    destination=destination.resolve()
    if source==destination or source.parent!=destination.parent:
        raise ValueError('Source and destination must be separate sibling trees')
    expected=set(source_files(source))
    actual=managed_files(destination)
    added=expected-actual
    removed=actual-expected
    updated={p for p in expected&actual if digest(source/p)!=digest(destination/p)}
    plan={'added':sorted(added),'updated':sorted(updated),'removed':sorted(removed)}
    print(f'Dev: {source}\nGit: {destination}\nSource files: {len(expected)}')
    print(f'Add: {len(added)}; update: {len(updated)}; delete stale: {len(removed)}')
    for relative in sorted(removed):print(f'DELETE {relative.as_posix()}')
    if not apply:
        print('Preview only. Use --apply to mirror managed files.')
        return plan
    preserved=preserved_snapshot(destination)
    staging_parent=checked_path(source,'build')
    staging_parent.mkdir(exist_ok=True)
    # Stage first, retain old managed contents until verification succeeds.
    with tempfile.TemporaryDirectory(prefix='git-sync-',dir=staging_parent) as temporary:
        stage=Path(temporary)/'new'
        backup=Path(temporary)/'old'
        stage.mkdir();backup.mkdir()
        for folder in MANAGED_DIRECTORIES:(stage/folder).mkdir()
        for relative in sorted(expected):
            target=checked_path(stage,relative)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source/relative,target)
        names=set(MANAGED_DIRECTORIES)|{p.name for p in expected|actual if len(p.parts)==1}
        destination.mkdir(parents=True,exist_ok=True)
        changed=[]
        try:
            for name in sorted(names):
                target=checked_path(destination,name)
                saved=backup/name
                replacement=stage/name
                if target.exists():target.rename(saved)
                changed.append(name)
                if replacement.exists():replacement.rename(target)
            if managed_files(destination)!=expected:raise ValueError('Stale/missing managed files after sync')
            if any(digest(source/p)!=digest(destination/p) for p in expected):
                raise ValueError('Managed content differs after sync')
            if preserved_snapshot(destination)!=preserved:
                raise ValueError('Preserved repository/release files changed during synchronization')
        except Exception:
            for name in reversed(changed):
                target=checked_path(destination,name)
                if target.is_dir():shutil.rmtree(target)
                elif target.exists():target.unlink()
                saved=backup/name
                if saved.exists():saved.rename(target)
            raise
    print(f'PASS: exact managed mirror ({len(expected)} files); no stale files; preserved files unchanged.')
    print('No Git commands, commits, tags or publication.')
    return plan

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Replace managed contents and remove stale files')
    args=parser.parse_args()
    if ROOT.name!='Loona-Desktop':parser.error('Run from Dev outputs/Loona-Desktop')
    destination=ROOT.parent/'Loona-Desktop-Git'
    inside(destination,ROOT.parent)
    synchronize(ROOT,destination,args.apply)

if __name__=='__main__':main()

