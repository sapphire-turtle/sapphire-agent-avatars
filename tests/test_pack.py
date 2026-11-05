import hashlib
import tarfile
import tempfile
import unittest
from pathlib import Path

from tests import fixtures
from avatars import pack


class PackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = fixtures.repo(Path(self._tmp.name) / "repo")
        self.out = Path(self._tmp.name) / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def test_parse_tag_ok(self):
        self.assertEqual(pack.parse_tag("santa-chibi-v12"), ("santa-chibi", 12))
        self.assertEqual(pack.parse_tag("default-regular-v1"), ("default-regular", 1))

    def test_parse_tag_rejects(self):
        for tag in ("catalog", "default-chibi-v0", "Default-chibi-v1", "default-tall-v1", "default-chibi-v1x"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                pack.parse_tag(tag)

    def test_pack_is_reproducible(self):
        a = pack.build(self.root, "default-chibi", 1, self.out / "a").read_bytes()
        (self.root / "avatars" / "default-chibi" / "avatar.toml").touch()
        b = pack.build(self.root, "default-chibi", 1, self.out / "b").read_bytes()
        self.assertEqual(a, b)

    def test_pack_layout_and_headers(self):
        path = pack.build(self.root, "default-chibi", 3, self.out)
        self.assertEqual(path.name, "default-chibi-v3.tar")
        with tarfile.open(path) as tar:
            members = tar.getmembers()
        names = [m.name for m in members]
        self.assertEqual(names, sorted(names))
        self.assertIn("avatar", names)
        self.assertIn("avatar/profile.md", names)
        self.assertIn("avatar/avatar.toml", names)
        self.assertIn("avatar/sprite/idle.webp", names)
        self.assertTrue(all(n == "avatar" or n.startswith("avatar/") for n in names))
        for m in members:
            self.assertEqual((m.uid, m.gid, m.uname, m.gname, m.mtime), (0, 0, "", "", 0))
            self.assertEqual(m.mode, 0o755 if m.isdir() else 0o644)
            self.assertTrue(m.isdir() or m.isfile())

    def test_sha256_file_format(self):
        path = pack.build(self.root, "default-chibi", 1, self.out)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual((self.out / "default-chibi-v1.tar.sha256").read_text(), f"{digest}  default-chibi-v1.tar\n")

    def test_pack_rejects_unknown_id(self):
        fixtures.avatar(self.root / "avatars" / "santa-chibi")
        with self.assertRaises(ValueError):
            pack.build(self.root, "santa-chibi", 1, self.out)
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_pack_rejects_failing_check(self):
        (self.root / "avatars" / "default-chibi" / "stray.webp").write_bytes(b"x")
        with self.assertRaises(ValueError):
            pack.build(self.root, "default-chibi", 1, self.out)


if __name__ == "__main__":
    unittest.main()
