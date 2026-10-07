"""Mirror deletions and preservation without running any Git commands."""
from pathlib import Path
import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch
from build import BUILD
from sync_git_version import synchronize,managed_files,source_files,preserved_snapshot

class SyncTests(unittest.TestCase):
    def setUp(self):
        BUILD.mkdir(exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(dir=BUILD)
        self.addCleanup(self.temporary.cleanup)
        root=Path(self.temporary.name)
        self.source=root/'Dev';self.target=root/'Git'
        for base in (self.source,self.target):base.mkdir()
        self.write(self.source,'main.py','new main')
        self.write(self.source,'VERSION','1.0.0')
        self.write(self.source,'assets/current/00.png','current frame')
        self.write(self.source,'tests/fixtures/data.txt','fixture')
        self.write(self.source,'packaging/README.txt','instructions')
        self.write(self.target,'main.py','old main')
        for name in ('obsolete.py','README.txt','assets/old/00.png','tests/old.py','packaging/old.txt'):
            self.write(self.target,name,'stale')
        for name in ('.git/config','.github/workflows/release.yml','dist/release.zip',
                     'social-preview.jpg','release_manager.py','LICENSE','README.md'):
            self.write(self.target,name,'preserve '+name)
        self.assets=patch('sync_git_version.release_assets',return_value=[Path('assets/current/00.png')])
        self.assets.start();self.addCleanup(self.assets.stop)

    def write(self,base,name,text):
        path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)

    def sync(self,apply):
        with contextlib.redirect_stdout(io.StringIO()):
            return synchronize(self.source,self.target,apply)

    def test_preview_does_not_modify_and_apply_removes_stale_files_preserving_release_state(self):
        preserved=preserved_snapshot(self.target)
        before={p.relative_to(self.target):p.read_bytes() for p in self.target.rglob('*') if p.is_file()}
        plan=self.sync(False)
        self.assertIn(Path('obsolete.py'),plan['removed'])
        self.assertEqual(before,{p.relative_to(self.target):p.read_bytes() for p in self.target.rglob('*') if p.is_file()})
        self.sync(True)
        self.assertEqual(managed_files(self.target),set(source_files(self.source)))
        self.assertEqual(preserved_snapshot(self.target),preserved)
        self.assertFalse((self.target/'assets/old').exists())
        self.assertEqual(self.sync(False),{'added':[],'updated':[],'removed':[]})
        (self.source/'tests/fixtures/data.txt').unlink()
        self.sync(True)
        self.assertFalse((self.target/'tests/fixtures/data.txt').exists())

    def test_invalid_source_fails_before_destination_changes(self):
        before=(self.target/'main.py').read_bytes()
        (self.source/'assets/current/00.png').unlink()
        with self.assertRaises(FileNotFoundError):self.sync(True)
        self.assertEqual((self.target/'main.py').read_bytes(),before)
        self.assertTrue((self.target/'obsolete.py').exists())

    def test_failed_replacement_rolls_back_old_managed_files(self):
        before={p.relative_to(self.target):p.read_bytes() for p in self.target.rglob('*') if p.is_file()}
        original=Path.rename
        def fail_new_main(path,target):
            if path.name=='main.py' and path.parent.name=='new':raise OSError('simulated locked file')
            return original(path,target)
        with patch.object(Path,'rename',fail_new_main):
            with self.assertRaisesRegex(OSError,'simulated locked'):self.sync(True)
        self.assertEqual(before,{p.relative_to(self.target):p.read_bytes() for p in self.target.rglob('*') if p.is_file()})

    def test_overlapping_or_non_sibling_destination_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'sibling'):
            synchronize(self.source,self.source/'nested',True)

if __name__=='__main__':unittest.main()
