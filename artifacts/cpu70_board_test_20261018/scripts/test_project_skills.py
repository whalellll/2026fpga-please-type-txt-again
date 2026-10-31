"""Portable skills: installation, migration, and delivery integrity checks."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('project_skills', ROOT / 'skills/manage.py')
skills = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skills)


class SkillsTest(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix='fpga_skills_test_')).resolve()
        assert self.temp.parent == Path(tempfile.gettempdir()).resolve()
        self.library = self.temp / 'original project' / 'skills'
        shutil.copytree(ROOT / 'skills', self.library,
                        ignore=shutil.ignore_patterns('manifest.json', '__pycache__'))
        skills.review(self.library, 'test fixture', '2026-10-08')

    def tearDown(self):
        assert self.temp.parent == Path(tempfile.gettempdir()).resolve()
        assert self.temp.name.startswith('fpga_skills_test_')
        shutil.rmtree(self.temp)

    def edit(self, root=None):
        path = (root or self.library) / 'accelerator-performance/references/lessons.md'
        path.write_text(path.read_text(encoding='utf-8') + '\nNew measured lesson.\n', encoding='utf-8')

    def project_and_stage(self):
        project, stage = self.temp / 'project B', self.temp / 'unpacked' / 'soc_linux'
        for name in skills.DELIVERY_SOURCES:
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture ' + name, encoding='utf-8')
            dest = stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        skills.stage(self.library, project, stage)
        return project, stage

    def test_standard_entrypoints_and_self_contained_resources(self):
        manifest = skills.verify(self.library)
        self.assertEqual(set(manifest['skills']), set(skills.CORE_SKILLS))
        for name in manifest['skills']:
            self.assertTrue((self.library / name / 'agents/openai.yaml').is_file())

    def test_migrate_and_install_in_independent_path(self):
        moved = self.temp / 'different drive like folder' / 'skills'
        skills.sync(self.library, moved)
        target = self.temp / 'other user' / '.agents' / 'skills'
        skills.install(moved, target)
        for name in skills.CORE_SKILLS:
            self.assertEqual((moved/name/'SKILL.md').read_bytes(), (target/name/'SKILL.md').read_bytes())
            self.assertTrue((target/name/'references/lessons.md').is_file())
        skills.install(moved, target)  # repeated install is safe

    def test_unreviewed_edit_rejected_by_verify_and_pack(self):
        self.edit()
        with self.assertRaises(skills.SkillError): skills.verify(self.library)
        with self.assertRaises(skills.SkillError): skills.pack(self.library, self.temp/'bad.zip')

    def test_review_refreshes_revision_and_hashes(self):
        first = skills.verify(self.library)
        self.edit()
        second = skills.review(self.library, 'new measured lesson', '2026-10-08')
        self.assertEqual(second['revision'], first['revision'] + 1)
        skills.verify(self.library)

    def test_missing_core_skill_rejected(self):
        (self.library/'fpga-timing-optimization/SKILL.md').unlink()
        with self.assertRaises(skills.SkillError): skills.verify(self.library)

    def test_external_resource_link_rejected(self):
        path = self.library/'accelerator-performance/SKILL.md'
        path.write_text(path.read_text(encoding='utf-8') + '\n[dependency](../other/SKILL.md)\n', encoding='utf-8')
        with self.assertRaises(skills.SkillError): skills.review(self.library, 'bad link', '2026-10-08')

    def test_unsafe_manifest_path_rejected(self):
        path = self.library/'manifest.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        value['files']['../outside'] = '0'*64
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(skills.SkillError): skills.verify(self.library)

    def test_sync_preserves_local_edits(self):
        target = self.temp/'mirror'
        skills.sync(self.library, target)
        self.edit(target)
        before = (target/'accelerator-performance/references/lessons.md').read_bytes()
        with self.assertRaises(skills.SkillError): skills.sync(self.library, target)
        self.assertEqual(before, (target/'accelerator-performance/references/lessons.md').read_bytes())

    def test_unmanaged_installed_skill_not_overwritten(self):
        target = self.temp/'user skills'
        existing = target/'accelerator-performance/SKILL.md'
        existing.parent.mkdir(parents=True)
        existing.write_text('user owned skill', encoding='utf-8')
        with self.assertRaises(skills.SkillError): skills.install(self.library, target)
        self.assertEqual(existing.read_text(encoding='utf-8'), 'user owned skill')

    def test_installed_edit_not_overwritten(self):
        target = self.temp/'user skills'
        skills.install(self.library, target)
        self.edit(target)
        with self.assertRaises(skills.SkillError): skills.install(self.library, target)

    def test_managed_install_can_upgrade(self):
        target = self.temp/'user skills'
        skills.install(self.library, target)
        self.edit()
        skills.review(self.library, 'upgrade', '2026-10-08')
        skills.install(self.library, target)
        self.assertEqual((target/'accelerator-performance/references/lessons.md').read_bytes(),
                         (self.library/'accelerator-performance/references/lessons.md').read_bytes())

    def test_delivery_snapshot_and_stale_source_rejection(self):
        _, stage = self.project_and_stage()
        skills.verify_delivery(stage, self.library)
        self.edit()
        skills.review(self.library, 'next delivery', '2026-10-08')
        with self.assertRaises(skills.SkillError): skills.verify_delivery(stage, self.library)

    def test_mixed_delivery_metadata_rejected(self):
        _, stage = self.project_and_stage()
        (stage/'README.md').write_text('changed after stage', encoding='utf-8')
        with self.assertRaises(skills.SkillError): skills.verify_delivery(stage, self.library)

    def test_missing_delivery_helper_rejected(self):
        _, stage = self.project_and_stage()
        (stage/'scripts/invoke_project_skills.ps1').unlink()
        with self.assertRaises(skills.SkillError): skills.verify_delivery(stage, self.library)

    def test_archive_portable_and_complete(self):
        archive = self.temp/'skills.zip'
        skills.pack(self.library, archive)
        extracted = self.temp/'new machine'
        with zipfile.ZipFile(archive) as z:
            self.assertTrue(all(name.startswith('skills/') and '\\' not in name for name in z.namelist()))
            z.extractall(extracted)
        skills.verify(extracted/'skills')
        skills.install(extracted/'skills', self.temp/'new machine user'/'skills')


if __name__ == '__main__':
    unittest.main()
