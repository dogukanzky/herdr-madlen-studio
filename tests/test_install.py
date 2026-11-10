import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('installer',Path(__file__).resolve().parents[1]/'install.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.src=self.root/'source';self.home=self.root/'home'
        (self.src/'mods/demo').mkdir(parents=True);(self.src/'mods/demo/main.js').write_text('version1')
        self.home.mkdir();(self.home/'settings.json').write_text('untouched')
    def install(self,**kw):return m.install(self.src,self.home,activate=False,check=False,**kw)
    def test_install_and_update_preserve_unrelated(self):
        self.install();(self.src/'mods/demo/main.js').write_text('version2');self.install()
        self.assertEqual((self.home/'mods/demo/main.js').read_text(),'version2')
        self.assertEqual((self.home/'settings.json').read_text(),'untouched')
        self.assertTrue(list((self.home/'backups').rglob('main.js')))
    def test_collision_makes_no_changes(self):
        (self.home/'mods/demo').mkdir(parents=True);(self.home/'mods/demo/main.js').write_text('personal')
        with self.assertRaisesRegex(RuntimeError,'kişisel'):self.install()
        self.assertEqual((self.home/'mods/demo/main.js').read_text(),'personal')
    def test_modified_requires_explicit_flag(self):
        self.install();(self.home/'mods/demo/main.js').write_text('custom')
        with self.assertRaisesRegex(RuntimeError,'Yerel'):self.install()
        self.install(replace_modified=True)
        self.assertTrue(any(p.read_text()=='custom' for p in (self.home/'backups').rglob('main.js')))
    def test_failed_activation_restores_files(self):
        self.install();(self.src/'mods/demo/main.js').write_text('version2')
        with patch.object(m,'run',side_effect=RuntimeError('offline')):
            with self.assertRaisesRegex(RuntimeError,'offline'):m.install(self.src,self.home,activate=True,check=False)
        self.assertEqual((self.home/'mods/demo/main.js').read_text(),'version1')
    def test_symlink_refused(self):
        other=self.root/'other';other.mkdir();(self.home/'mods').symlink_to(other)
        with self.assertRaisesRegex(RuntimeError,'Sembolik'):self.install()
        self.assertEqual(list(other.iterdir()),[])
