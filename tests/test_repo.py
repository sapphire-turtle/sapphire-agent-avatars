import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import fixtures
from avatars import repo

ROOT = Path(__file__).resolve().parent.parent


class RepoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = fixtures.repo(Path(self._tmp.name), ids=("default-chibi", "default-regular"))

    def tearDown(self):
        self._tmp.cleanup()

    def assertProblem(self, needle):
        problems = repo.check(self.root)
        self.assertTrue(any(needle in p for p in problems), problems)

    def test_valid_repo_passes(self):
        self.assertEqual(repo.check(self.root), [])
        self.assertEqual([e["id"] for e in repo.load_catalog(self.root)], ["default-chibi", "default-regular"])

    def test_dir_without_catalog_entry_fails(self):
        fixtures.avatar(self.root / "avatars" / "santa-chibi")
        self.assertProblem("santa-chibi")

    def test_catalog_entry_without_dir_fails(self):
        import shutil

        shutil.rmtree(self.root / "avatars" / "default-regular")
        self.assertProblem("default-regular")

    def test_id_proportion_mismatch_fails(self):
        path = self.root / "catalog.toml"
        path.write_text(path.read_text().replace('proportion = "regular"', 'proportion = "chibi"'))
        self.assertProblem("proportion")

    def test_bad_id_fails(self):
        (self.root / "avatars" / "default-chibi").rename(self.root / "avatars" / "Default-tall")
        path = self.root / "catalog.toml"
        path.write_text(path.read_text().replace('id = "default-chibi"', 'id = "Default-tall"'))
        self.assertProblem("Default-tall")

    def test_duplicate_id_fails(self):
        path = self.root / "catalog.toml"
        path.write_text(path.read_text().replace('id = "default-regular"', 'id = "default-chibi"'))
        self.assertProblem("duplicate")

    def test_missing_thumbnail_fails(self):
        (self.root / "thumbnails" / "default-chibi.webp").unlink()
        self.assertProblem("thumbnail")

    def test_only_limits_avatar_checks(self):
        (self.root / "avatars" / "default-regular" / "stray.webp").write_bytes(b"x")
        self.assertEqual(repo.check(self.root, only="default-chibi"), [])
        self.assertProblem("default-regular")

    def test_check_script_exit_codes(self):
        ok = subprocess.run([sys.executable, str(ROOT / "scripts" / "check"), "--root", str(self.root)], capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        (self.root / "avatars" / "default-chibi" / "stray.webp").write_bytes(b"x")
        bad = subprocess.run([sys.executable, str(ROOT / "scripts" / "check"), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("stray.webp", bad.stdout)

    def test_strip_script_cleans_in_place(self):
        target = self.root / "x.webp"
        target.write_bytes(fixtures.webp_lossless(4, 4, [(b"XMP ", b"<x/>")], vp8x_flags=0x04))
        run = subprocess.run([sys.executable, str(ROOT / "scripts" / "strip"), str(target)], capture_output=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(target.read_bytes(), fixtures.webp_lossless(4, 4, vp8x_flags=0))
        other = self.root / "x.txt"
        other.write_text("x")
        self.assertNotEqual(subprocess.run([sys.executable, str(ROOT / "scripts" / "strip"), str(other)], capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
