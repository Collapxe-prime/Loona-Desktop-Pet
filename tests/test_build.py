"""Packaging contract: version source, user-state separation and Git filtering."""
from pathlib import Path
import os,shutil,subprocess,tempfile,unittest,zipfile
from unittest.mock import patch
from app_metadata import read_version,user_data_directory
from build import release_assets,version_resource,verify_archive,BUILD

ROOT=Path(__file__).resolve().parents[1]

class BuildTests(unittest.TestCase):
    def test_version_file_drives_application_and_windows_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'VERSION').write_text('1.2.3\n')
            self.assertEqual(read_version(root),'1.2.3')
            self.assertIn("filevers=(1, 2, 3, 0)",version_resource(read_version(root)))
            (root/'VERSION').write_text('version unknown')
            with self.assertRaises(ValueError):read_version(root)

    def test_frozen_data_uses_user_directory_and_development_keeps_current_settings(self):
        with patch.dict(os.environ,{'LOCALAPPDATA':str(ROOT/'build/test-localappdata')},clear=True):
            self.assertEqual(user_data_directory(ROOT),ROOT)
            self.assertEqual(user_data_directory(ROOT,True),ROOT/'build/test-localappdata/LoonaDesktopPet')
        with patch.dict(os.environ,{'LOONA_DATA_DIR':str(ROOT/'build/override-state')},clear=True):
            self.assertEqual(user_data_directory(ROOT,True),ROOT/'build/override-state')

    def test_release_allowlist_has_no_local_settings_or_development_artifacts(self):
        files=release_assets(ROOT)
        self.assertEqual(len(files),len(set(files)))
        self.assertIn(Path('assets/revamp/hq/walking-right/07.png'),files)
        self.assertIn(Path('assets/petting-smile/hq/07.png'),files)
        for path in files:
            self.assertNotIn('sources',path.parts)
            self.assertNotIn('backups',path.parts)
            self.assertNotEqual(path.name,'settings.json')
            self.assertNotEqual(path.suffix,'.gif')

    @unittest.skipUnless(shutil.which('git') and os.environ.get('LOONA_TEST_GIT')=='1',
                         'Git fixture is opt-in only; normal builds never run Git commands')
    def test_gitignore_filters_dev_files_but_keeps_every_required_runtime_asset(self):
        ignored=['settings.json','settings.json.tmp','desktop-pet.log','.venv/pyvenv.cfg',
                 '.build-venv/pyvenv.cfg','.idea/workspace.xml','__pycache__/main.pyc',
                 'build/temporary.spec','dist/app.exe','backups/example/main.py',
                 'assets/revamp/walk-import.json','assets/petting-smile/sources/smile.png',
                 'assets/revamp/walking-right.gif','assets/revamp-before-trial/frame.png',
                 'assets/revamp/hq/trial/00.png','assets/revamp/hq/idle/preview.png',
                 'assets/revamp/idle/contact.png','assets/petting-smile/frames/preview.png',
                 'assets/revamp/idle/notes.json','assets/revamp/hq/idle/notes.json']
        required=[str(p).replace('\\','/') for p in release_assets(ROOT)]
        required+=['main.py','app_metadata.py','build.py','VERSION','CHANGELOG.md',
                   'requirements-build.txt','tests/fixtures/greeting-timings.json','packaging/README.txt']
        with tempfile.TemporaryDirectory() as tmp:
            # This isolated fixture has no commits and never touches the actual project Git state.
            subprocess.run(['git','init','--quiet',tmp],check=True,capture_output=True)
            shutil.copy2(ROOT/'.gitignore',Path(tmp)/'.gitignore')
            result=subprocess.run(['git','-C',tmp,'check-ignore','--no-index','--stdin','-z'],
                input=('\0'.join(ignored+required)+'\0').encode(),capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(set(result.stdout.decode().rstrip('\0').split('\0')),set(ignored))

    def test_downloadable_zip_without_embedded_python_is_rejected(self):
        BUILD.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
            archive=Path(tmp)/'broken.zip'
            with zipfile.ZipFile(archive,'w') as zipped:
                zipped.writestr('app/VERSION','1.0.0')
            with self.assertRaisesRegex(ValueError,'Embedded Python runtime missing'):
                verify_archive(archive,'app','1.0.0',{})

    def test_downloadable_zip_with_corrupt_payload_is_rejected_before_launch(self):
        BUILD.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
            archive=Path(tmp)/'corrupt.zip'
            with zipfile.ZipFile(archive,'w') as zipped:
                zipped.writestr('app/VERSION','1.0.0')
                zipped.writestr('app/_internal/python312.dll','fixture')
                zipped.writestr('app/_internal/vcruntime140.dll','fixture')
                zipped.writestr('app/SHA256SUMS.txt','0'*64+'  VERSION\n')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                verify_archive(archive,'app','1.0.0',{})

if __name__=='__main__':unittest.main()
