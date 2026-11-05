import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import fixtures
from avatars import avatar


class AvatarTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dir = self.root / "a"
        fixtures.avatar(self.dir)
        self.profile = self.root / "profile.md"
        self.profile.write_text("# Profile\n")

    def tearDown(self):
        self._tmp.cleanup()

    def problems(self):
        return avatar.check(self.dir, self.profile)

    def assertOneProblem(self, needle):
        problems = self.problems()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(needle, problems[0])

    def edit_toml(self, old, new):
        path = self.dir / "avatar.toml"
        path.write_text(path.read_text().replace(old, new))

    def test_valid_avatar_passes(self):
        self.assertEqual(self.problems(), [])

    def test_unreferenced_file_fails(self):
        (self.dir / "sprite" / "old.webp").write_bytes(fixtures.webp_lossless(8, 12))
        self.assertOneProblem("sprite/old.webp")

    def test_missing_referenced_file_fails(self):
        (self.dir / "vrm" / "idle.vrma").unlink()
        self.assertOneProblem("vrm/idle.vrma")

    def test_sprite_sizes_differ_fails(self):
        (self.dir / "sprite" / "idle-happy.webp").write_bytes(fixtures.webp_lossless(8, 13))
        self.assertOneProblem("canvas")

    def test_bad_expression_key_fails(self):
        self.edit_toml("happy =", "smug =")
        problems = self.problems()
        self.assertTrue(any("smug" in p for p in problems), problems)

    def test_default_pose_missing_fails(self):
        self.edit_toml('default_pose = "idle"', 'default_pose = "wave"')
        self.assertOneProblem("default_pose")

    def test_path_with_dotdot_fails(self):
        self.edit_toml('"vrm/idle.vrma"', '"vrm/../vrm/idle.vrma"')
        problems = self.problems()
        self.assertTrue(any(".." in p for p in problems), problems)

    def test_unknown_extension_fails(self):
        (self.dir / "sprite" / "idle-happy.webp").rename(self.dir / "sprite" / "idle-happy.gif")
        self.edit_toml("idle-happy.webp", "idle-happy.gif")
        self.assertOneProblem(".gif")

    def test_embedded_metadata_fails(self):
        (self.dir / "sprite" / "idle.webp").write_bytes(fixtures.webp_lossless(8, 12, [(b"EXIF", b"x")], vp8x_flags=0x08))
        self.assertOneProblem("EXIF")

    def test_total_over_cap_fails(self):
        with mock.patch.object(avatar, "MAX_AVATAR_TOTAL", 100):
            self.assertOneProblem("total")

    def test_file_over_cap_fails(self):
        with mock.patch.object(avatar, "MAX_FILE", 50):
            self.assertTrue(any("vrm/model.vrm" in p for p in self.problems()))

    def test_profile_not_utf8_fails(self):
        self.profile.write_bytes(b"\xff\xfe")
        self.assertOneProblem("UTF-8")

    def test_unparseable_toml_fails(self):
        (self.dir / "avatar.toml").write_text("[sprite\n")
        self.assertOneProblem("avatar.toml")


if __name__ == "__main__":
    unittest.main()
