"""Copy reviewable source files from Dev into its clean Git sibling; never run Git."""
from pathlib import Path
import argparse
import shutil
from build import ROOT,release_assets,inside

DOCUMENTS=('.gitignore','.gitattributes','VERSION','CHANGELOG.md','BUILDING.md',
           'PROJECT-VERSIONS.md','README.txt','requirements.txt','requirements-build.txt','Start-Loona.cmd')

def source_files():
    files=[Path(name) for name in DOCUMENTS]
    files.extend(p.relative_to(ROOT) for p in ROOT.glob('*.py') if not p.name.startswith('test'))
    files.extend(p.relative_to(ROOT) for p in (ROOT/'tests').rglob('*.py') if '__pycache__' not in p.parts)
    files.extend(p.relative_to(ROOT) for p in (ROOT/'tests/fixtures').glob('*.json'))
    files.append(Path('packaging/README.txt'))
    files.extend(release_assets())
    return sorted(set(files))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Copy files; default only previews the operation')
    args=parser.parse_args()
    if ROOT.name!='Loona-Desktop':
        parser.error('Run this script from the Dev folder outputs/Loona-Desktop')
    destination=inside(ROOT.parent/'Loona-Desktop-Git',ROOT.parent)
    files=source_files()
    print(f'Dev: {ROOT}\nGit: {destination}\nSource files: {len(files)}')
    if not args.apply:
        print('Preview only. Use --apply to copy. No files will be deleted.')
        return
    for relative in files:
        source=inside(ROOT/relative,ROOT)
        target=inside(destination/relative,destination)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
    print('Copied source snapshot. No deletions, Git commands, commits, tags or uploads.')
    print('If files were removed or renamed in Dev, review obsolete files in Git manually.')

if __name__=='__main__':main()
