import tempfile
import unittest
from pathlib import Path

from tests import fixtures
from avatars import catalog

REPO = "https://github.com/example/avatars"


def release(tag, size=100):
    name = f"{tag}.tar"
    return {
        "tag_name": tag,
        "assets": [
            {"name": name, "size": size, "browser_download_url": f"{REPO}/releases/download/{tag}/{name}"},
            {"name": f"{name}.sha256", "size": 80, "browser_download_url": f"{REPO}/releases/download/{tag}/{name}.sha256"},
        ],
    }


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.root = fixtures.repo(tmp / "repo", ids=("default-regular", "default-chibi", "santa-chibi"))
        self.sums = tmp / "sums"
        self.sums.mkdir()
        for tag in ("default-chibi-v1", "default-chibi-v2", "default-regular-v1"):
            (self.sums / f"{tag}.tar.sha256").write_text(f"{tag[:1] * 64}  {tag}.tar\n")
        self.releases = [
            release("default-chibi-v1", 10),
            release("default-chibi-v2", 20),
            release("default-regular-v1", 30),
            {"tag_name": "catalog", "assets": [{"name": "catalog.json", "size": 1, "browser_download_url": "x"}]},
        ]

    def tearDown(self):
        self._tmp.cleanup()

    def build(self):
        return catalog.build(self.root, self.releases, self.sums, REPO)

    def test_catalog_picks_highest_version(self):
        chibi = next(a for a in self.build()["avatars"] if a["id"] == "default-chibi")
        self.assertEqual(chibi["version"], 2)
        self.assertEqual(chibi["size"], 20)
        self.assertEqual(chibi["url"], f"{REPO}/releases/download/default-chibi-v2/default-chibi-v2.tar")
        self.assertEqual(chibi["sha256"], "d" * 64)

    def test_catalog_keeps_catalog_order_and_omits_unreleased(self):
        self.assertEqual([a["id"] for a in self.build()["avatars"]], ["default-regular", "default-chibi"])

    def test_catalog_shape(self):
        out = self.build()
        self.assertEqual(out["schema"], 1)
        entry = out["avatars"][0]
        self.assertEqual(
            set(entry),
            {"id", "outfit", "proportion", "title", "version", "url", "sha256", "size", "thumbnail"},
        )
        self.assertEqual(entry["title"], {"en": "default-regular", "ja": "default-regular"})
        self.assertEqual(entry["thumbnail"], f"{REPO}/releases/download/catalog/default-regular.webp")

    def test_catalog_requires_sum_file(self):
        (self.sums / "default-chibi-v2.tar.sha256").unlink()
        with self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()
