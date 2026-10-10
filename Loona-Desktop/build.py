"""Local Windows build only: no Git commands, tags, uploads or publication."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from app_metadata import read_version,APP_TITLE,EXE_BASENAME

ROOT=Path(__file__).resolve().parent
BUILD=ROOT/'build'
DIST=ROOT/'dist'
APP_NAME=EXE_BASENAME

def prepare_icon(root=ROOT):
    from PIL import Image
    root=Path(root)
    with Image.open(root/'packaging/LoonaDesktopPet-icon.png') as image:
        if image.width!=image.height:raise ValueError('Application icon PNG must be square')
        image.convert('RGBA').save(root/'assets/app-icon.ico',format='ICO',
            sizes=[(n,n) for n in (16,24,32,48,64,128,256)])
    # Designer-supplied close-up for the small notification-area slot.
    with Image.open(root/'packaging/LoonaDesktopPet-tray.png') as image:
        if image.width!=image.height:raise ValueError('Tray icon PNG must be square')
        rgba=image.convert('RGBA')
        if rgba.getchannel('A').getbbox() is None:raise ValueError('Tray icon is empty')
        rgba.save(root/'assets/tray-icon.ico',format='ICO',
            sizes=[(n,n) for n in (16,24,32,48,64)])

def verify_branding(executable,version):
    import ctypes as C
    from ctypes import wintypes as W
    executable=str(Path(executable).resolve())
    library=C.WinDLL('version',use_last_error=True)
    size_fn=library.GetFileVersionInfoSizeW
    size_fn.argtypes=[W.LPCWSTR,C.POINTER(W.DWORD)];size_fn.restype=W.DWORD
    size=size_fn(executable,None)
    if not size:raise C.WinError(C.get_last_error())
    buffer=C.create_string_buffer(size)
    info=library.GetFileVersionInfoW
    info.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p];info.restype=W.BOOL
    if not info(executable,0,size,buffer):raise C.WinError(C.get_last_error())
    query=library.VerQueryValueW
    query.argtypes=[C.c_void_p,W.LPCWSTR,C.POINTER(C.c_void_p),C.POINTER(W.UINT)];query.restype=W.BOOL
    fields={'ProductName':APP_TITLE,'FileDescription':APP_TITLE,'CompanyName':APP_TITLE,
            'FileVersion':version,'ProductVersion':version,'OriginalFilename':APP_NAME+'.exe'}
    for field,expected in fields.items():
        pointer=C.c_void_p();length=W.UINT()
        if not query(buffer,'\\StringFileInfo\\040904B0\\'+field,C.byref(pointer),C.byref(length)):
            raise ValueError(f'Missing Windows version field: {field}')
        if C.wstring_at(pointer)!=expected:raise ValueError(f'Windows version field mismatch: {field}')
    kernel=C.WinDLL('kernel32',use_last_error=True)
    load=kernel.LoadLibraryExW;load.argtypes=[W.LPCWSTR,W.HANDLE,W.DWORD];load.restype=W.HMODULE
    release=kernel.FreeLibrary;release.argtypes=[W.HMODULE];release.restype=W.BOOL
    handle=load(executable,None,2)
    if not handle:raise C.WinError(C.get_last_error())
    callback_type=C.WINFUNCTYPE(W.BOOL,W.HMODULE,C.c_void_p,C.c_void_p,C.c_ssize_t)
    enumerate_names=kernel.EnumResourceNamesW
    enumerate_names.argtypes=[W.HMODULE,C.c_void_p,callback_type,C.c_ssize_t];enumerate_names.restype=W.BOOL
    try:
        for kind,minimum in ((14,1),(3,7)):
            names=[]
            def collect(module,resource_type,name,parameter):
                names.append(name)
                return True
            callback=callback_type(collect)
            if not enumerate_names(handle,C.c_void_p(kind),callback,0) or len(names)<minimum:
                raise ValueError('Multi-size Windows icon missing from executable')
    finally:release(handle)
    print(f'PASS: Windows branding: {APP_TITLE}, {APP_NAME}.exe, version {version}, embedded icon',flush=True)

def local_build_environment():
    """Keep dependency downloads, tool caches and subprocess scratch on the project drive."""
    folders={'TEMP':BUILD/'tmp','TMP':BUILD/'tmp',
             'PIP_CACHE_DIR':BUILD/'cache/pip','PYINSTALLER_CONFIG_DIR':BUILD/'cache/pyinstaller'}
    env=dict(os.environ)
    for key,path in folders.items():
        path.mkdir(parents=True,exist_ok=True)
        env[key]=str(path)
    return env

def inside(path,parent):
    path=Path(path).resolve()
    path.relative_to(Path(parent).resolve())
    return path

def release_assets(root=ROOT):
    """Positive allowlist: build cannot copy scratch files or machine state."""
    root=Path(root)
    paths=[Path('assets/Loona.png'),Path('assets/revamp/manifest.json'),
           Path('assets/revamp/quality-profile.json'),Path('assets/petting-smile/animation.json')]
    paths.append(Path('assets/app-icon.ico'))
    paths.append(Path('assets/tray-icon.ico'))
    manifest=json.loads((root/paths[1]).read_text(encoding='utf-8'))
    for name,entry in manifest['animations'].items():
        if not re.fullmatch(r'[a-z][a-z-]*',name):raise ValueError('Unsafe animation group')
        durations=entry['durations_ms']
        if not durations or any(not isinstance(d,(float,int)) or d<=0 for d in durations):
            raise ValueError(f'Invalid animation duration: {name}')
        for i in range(len(durations)):
            paths.extend([Path(f'assets/revamp/{name}/{i:02}.png'),Path(f'assets/revamp/hq/{name}/{i:02}.png')])
    for i in range(16):
        paths.extend([Path(f'assets/revamp/look/{i:02}.png'),Path(f'assets/revamp/hq/look/{i:02}.png')])
    # These small legacy folders are used to discover the four extra states at startup.
    for name in ('sitting','falling','slipping','balancing'):
        paths.extend(Path(f'assets/animations/{name}/{i:02}.png') for i in range(12))
    for folder in ('hq','frames'):
        paths.extend(Path(f'assets/petting-smile/{folder}/{i:02}.png') for i in range(8))
    for relative in paths:
        file=inside(root/relative,root)
        if not file.is_file():raise FileNotFoundError(file)
    return paths

def stage_assets(destination,root=ROOT):
    destination=Path(destination)
    paths=release_assets(root)
    for relative in paths:
        target=inside(destination/relative,destination)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(root)/relative,target)
    return paths

def run(command,env=None,cwd=ROOT,timeout=None):
    print('>',subprocess.list2cmdline([str(c) for c in command]),flush=True)
    subprocess.run([str(c) for c in command],cwd=cwd,env=env,check=True,timeout=timeout)

def verify_archive(archive,name,version,env):
    """Test the exact downloadable ZIP in a fresh directory, without source/Python paths."""
    with tempfile.TemporaryDirectory(prefix='unpacked release ',dir=BUILD) as temporary:
        extracted=Path(temporary)
        with zipfile.ZipFile(archive) as zipped:
            bad=zipped.testzip()
            if bad:raise ValueError(f'Archive integrity failure: {bad}')
            for entry in zipped.infolist():
                inside(extracted/entry.filename,extracted)
            zipped.extractall(extracted)
        package=extracted/name
        if read_version(package)!=version:raise ValueError('ZIP version mismatch')
        if not (package/'_internal/python312.dll').is_file():
            raise ValueError('Embedded Python runtime missing from ZIP')
        if not list((package/'_internal').rglob('vcruntime140*.dll')):
            raise ValueError('Microsoft C runtime missing from ZIP')
        expected={}
        for line in (package/'SHA256SUMS.txt').read_text().splitlines():
            digest,relative=line.split('  ',1)
            file=inside(package/relative,package)
            if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
                raise ValueError(f'ZIP payload checksum mismatch: {relative}')
            expected[relative]=digest
        actual={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
        if actual!=set(expected)|{'SHA256SUMS.txt'}:
            raise ValueError('Unexpected or missing ZIP payload files')
        for asset in release_assets():
            if (package/asset).read_bytes()!=(ROOT/asset).read_bytes():
                raise ValueError(f'ZIP runtime asset mismatch: {asset}')
        verify_branding(package/(APP_NAME+'.exe'),version)
        standalone=dict(env)
        for key in list(standalone):
            if key.upper().startswith('PYTHON') or key.upper() in ('VIRTUAL_ENV','CONDA_PREFIX'):
                standalone.pop(key,None)
        standalone['PATH']=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32')
        standalone['LOONA_DATA_DIR']=str(extracted/'user data')
        for option in ('--self-test','--smoke-test','--memory-test'):
            run([package/(APP_NAME+'.exe'),option],standalone,cwd=extracted,timeout=120)
        print('PASS: extracted ZIP starts without project files or Python on PATH',flush=True)

def check():
    version=read_version(ROOT)
    prepare_icon()
    assets=release_assets()
    BUILD.mkdir(exist_ok=True)
    # Stage the actual allowlist and verify the content, without making an executable.
    with tempfile.TemporaryDirectory(prefix='package-check-',dir=BUILD) as temporary:
        staged=Path(temporary)
        stage_assets(staged)
        for relative in assets:
            if (ROOT/relative).read_bytes()!=(staged/relative).read_bytes():
                raise ValueError(f'Staging mismatch: {relative}')
        if len(list(staged.rglob('*.*')))!=len(assets):
            raise ValueError('Unexpected files in staged assets')
    env=dict(local_build_environment(),LOONA_DATA_DIR=str(BUILD/'check-user-data'),LOONA_TEST_GIT='0')
    run([sys.executable,'-m','unittest','discover','-s','tests'],env)
    run([sys.executable,'main.py','--self-test'],env)
    run([sys.executable,'main.py','--smoke-test'],env)
    print(f'PASS: build inputs for {version}; {len(assets)} runtime asset files; no user state or dev artifacts',flush=True)
    return version

def version_resource(version):
    numeric=tuple(int(n) for n in version.split('-')[0].split('.'))+(0,)
    fields={'CompanyName':APP_TITLE,'FileDescription':APP_TITLE,
            'FileVersion':version,'InternalName':APP_NAME,'OriginalFilename':APP_NAME+'.exe',
            'ProductName':APP_TITLE,'ProductVersion':version}
    entries=',\n'.join(f'StringStruct({key!r}, {value!r})' for key,value in fields.items())
    return f"VSVersionInfo(ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r}, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0', [{entries}])]), VarFileInfo([VarStruct('Translation', [1033,1200])])])\n"

def build():
    if sys.platform!='win32' or platform.machine().upper() not in ('AMD64','X86_64'):
        raise RuntimeError('Build on Windows x64; PyInstaller is not a cross-compiler')
    if sys.version_info[:2]!=(3,12):raise RuntimeError('Use Python 3.12 for the verified build environment')
    version=read_version(ROOT)
    name=f'{APP_NAME}-{version}-windows-x64'
    destination=inside(DIST/name,DIST)
    archive=inside(DIST/(name+'.zip'),DIST)
    if destination.exists() or archive.exists():
        raise FileExistsError('This version already has a local build in dist; move it away before rebuilding')
    environment=inside(ROOT/'.build-venv',ROOT)
    python=environment/'Scripts/python.exe'
    env=local_build_environment()
    env['PYTHONNOUSERSITE']='1'
    env.pop('PYTHONPATH',None)
    if not python.exists():run([sys.executable,'-m','venv',environment],env)
    configuration=(environment/'pyvenv.cfg').read_text().lower()
    if 'include-system-site-packages = false' not in configuration:
        raise RuntimeError('.build-venv must not inherit system packages')
    # Recover an interrupted venv bootstrap without touching the development environment.
    probe=subprocess.run([str(python),'-m','pip','--version'],env=env,capture_output=True)
    if probe.returncode:run([python,'-m','ensurepip','--upgrade','--default-pip'],env)
    run([python,'-m','pip','install','--disable-pip-version-check','-r','requirements-build.txt'],env)
    # All checks run in the same clean environment that compiles the application.
    run([python,'build.py','--check'],env)
    BUILD.mkdir(exist_ok=True);DIST.mkdir(exist_ok=True)
    resource=BUILD/'windows-version.txt'
    resource.write_text(version_resource(version),encoding='utf-8')
    run([python,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
         '--noupx','--name',APP_NAME,'--paths',ROOT,'--version-file',resource,
         '--icon',ROOT/'assets/app-icon.ico',
         '--distpath',BUILD/'pyinstaller-dist','--workpath',BUILD/'pyinstaller-work',
         '--specpath',BUILD/'spec','main.py'],env)
    raw=inside(BUILD/'pyinstaller-dist'/APP_NAME,BUILD)
    if not (raw/(APP_NAME+'.exe')).is_file():raise FileNotFoundError('PyInstaller produced no executable')
    verify_branding(raw/(APP_NAME+'.exe'),version)
    # Keep the last build intact: packaging uses a new temporary directory.
    with tempfile.TemporaryDirectory(prefix='package-',dir=BUILD) as temporary:
        package=Path(temporary)/name
        shutil.copytree(raw,package)
        assets=stage_assets(package)
        for document in ('VERSION','CHANGELOG.md'):
            shutil.copy2(ROOT/document,package/document)
        shutil.copy2(ROOT/'packaging/README.txt',package/'README.txt')
        metadata=json.loads(subprocess.check_output([str(python),'-m','pip','list','--format=json'],env=env))
        (package/'BUILD-INFO.json').write_text(json.dumps({'version':version,'platform':'windows-x64',
            'python':platform.python_version(),'runtime_asset_files':len(assets),'dependencies':metadata},indent=2))
        test_env=dict(env,LOONA_DATA_DIR=str(BUILD/'frozen-check-user-data'))
        run([package/(APP_NAME+'.exe'),'--self-test'],test_env)
        run([package/(APP_NAME+'.exe'),'--smoke-test'],test_env)
        forbidden={'settings.json','desktop-pet.log','tests','backups','.venv','.idea','sources'}
        if any(p.name in forbidden for p in package.rglob('*')):
            raise ValueError('Development or user files leaked into package')
        # SHA256SUMS describes every payload file, including all third-party runtime DLLs.
        hashes=[]
        for file in sorted(p for p in package.rglob('*') if p.is_file()):
            hashes.append(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.relative_to(package).as_posix())
        (package/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n')
        temporary_zip=Path(temporary)/(name+'.zip')
        with zipfile.ZipFile(temporary_zip,'w',compression=zipfile.ZIP_DEFLATED) as zipped:
            for file in sorted(p for p in package.rglob('*') if p.is_file()):
                zipped.write(file,arcname=name+'/'+file.relative_to(package).as_posix())
        verify_archive(temporary_zip,name,version,env)
        shutil.move(str(package),str(destination))
        shutil.move(str(temporary_zip),str(archive))
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    (DIST/(name+'.zip.sha256')).write_text(checksum+'  '+archive.name+'\n')
    (DIST/'RELEASE-ARTIFACTS.json').write_text(json.dumps({'version':version,
        'platform':'windows-x64','publish':[archive.name,name+'.zip.sha256'],
        'zip_sha256':checksum,'zip_bytes':archive.stat().st_size,
        'validation':'extracted ZIP: checksums, bundled runtimes, assets, self-test, native smoke-test and bounded-cache stress test',
        'requires_installed_python':False},indent=2)+'\n',encoding='utf-8')
    print(f'PASS: local build validated: {archive}\nNothing was tagged, uploaded or published.')

def main():
    parser=argparse.ArgumentParser(description='Validate or build Loona locally; never publish')
    parser.add_argument('--check',action='store_true',help='Validate files and tests without compiling or downloading dependencies')
    args=parser.parse_args()
    try:
        check() if args.check else build()
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
        print(f'Build failed: {error}',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
