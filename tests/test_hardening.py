"""Tests for the final review's findings: allowlists over denylists, and no tracebacks on bad input."""

import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path

from tests import fixtures
from tests.fixtures import glb, png, riff_chunk, webp_lossless
from tests.test_glb import build, vrm, vrma
from avatars import avatar, catalog, glb as glb_mod, repo, webp


def raw_glb(chunks):
    out = b"".join(struct.pack("<I", len(p)) + k + p for k, p in chunks)
    return b"glTF" + struct.pack("<II", 2, 12 + len(out)) + out


def json_bytes(obj):
    js = json.dumps(obj).encode()
    return js + b" " * (-len(js) % 4)


class GlbAllowlistTest(unittest.TestCase):
    def assertProblem(self, data, needle, kind="vrm"):
        problems = glb_mod.check(data, kind)
        self.assertTrue(any(needle in p for p in problems), problems)

    def test_rejects_unknown_extension_anywhere(self):
        gltf = vrma()
        gltf["extensions"]["KHR_xmp_json_ld"] = {"packets": [{"dc:creator": ["Jane"]}]}
        self.assertProblem(build(gltf), "KHR_xmp_json_ld", "vrma")
        gltf = vrma()
        gltf["asset"]["extensions"] = {"KHR_xmp_json_ld": {"packet": 0}}
        self.assertProblem(build(gltf), "KHR_xmp_json_ld", "vrma")
        gltf = vrma()
        gltf["extensionsUsed"] = ["VRMC_vrm_animation", "KHR_xmp_json_ld"]
        self.assertProblem(build(gltf), "KHR_xmp_json_ld", "vrma")

    def test_allowed_extensions_pass(self):
        gltf, img = vrm()
        gltf["materials"][0]["extensions"] = {"VRMC_materials_mtoon": {"specVersion": "1.0"}}
        gltf["extensions"]["VRMC_springBone"] = {"specVersion": "1.0"}
        self.assertEqual(glb_mod.check(build(gltf, img), "vrm"), [])

    def test_rejects_unknown_asset_key(self):
        gltf = vrma()
        gltf["asset"]["author"] = "Jane"
        self.assertProblem(build(gltf), "asset.author", "vrma")

    def test_rejects_unknown_chunk(self):
        data = raw_glb([(b"JSON", json_bytes(vrma())), (b"XTRA", b"Jane")])
        with self.assertRaises(ValueError):
            glb_mod.read(data)

    def test_rejects_json_not_first_and_duplicate_bin(self):
        with self.assertRaises(ValueError):
            glb_mod.read(raw_glb([(b"BIN\x00", b"\x00" * 4), (b"JSON", json_bytes(vrma()))]))
        with self.assertRaises(ValueError):
            glb_mod.read(raw_glb([(b"JSON", json_bytes(vrma())), (b"BIN\x00", b"\x00" * 4), (b"BIN\x00", b"\x00" * 4)]))

    def test_rejects_buffer_uri(self):
        gltf = vrma()
        gltf["buffers"] = [{"byteLength": 4, "uri": "data:application/octet-stream;base64,AAAAAA=="}]
        self.assertProblem(build(gltf), "buffers[0]", "vrma")

    def test_image_must_live_in_the_bin_buffer(self):
        gltf, img = vrm()
        gltf["buffers"].append({"byteLength": 4})
        gltf["bufferViews"][0]["buffer"] = 1
        self.assertProblem(build(gltf, img), "images[0]")

    def test_names_checked_at_any_depth(self):
        for section in ("scenes", "accessors", "cameras"):
            with self.subTest(section=section):
                gltf = vrma()
                gltf[section] = [{"name": "C:\\Users\\jane"}]
                self.assertProblem(build(gltf), section, "vrma")
        gltf, img = vrm()
        gltf["extensions"]["VRMC_springBone"] = {"specVersion": "1.0", "springs": [{"name": "Jane's hair.001"}]}
        self.assertProblem(build(gltf, img), "springs")

    def test_meta_name_is_free_text(self):
        gltf, img = vrm()
        gltf["extensions"]["VRMC_vrm"]["meta"]["name"] = "サンプル (Sample)"
        self.assertEqual(glb_mod.check(build(gltf, img), "vrm"), [])

    def test_malformed_json_shapes_are_reported(self):
        for gltf in ([], {"asset": "x"}, {"asset": {"generator": glb_mod.GENERATOR}, "nodes": [{"name": 3}]},
                     {"asset": {"generator": glb_mod.GENERATOR}, "extensions": {"VRMC_vrm": "x"}}):
            with self.subTest(gltf=gltf):
                self.assertNotEqual(glb_mod.check(raw_glb([(b"JSON", json_bytes(gltf))]), "vrm"), [])


class WebpNestedTest(unittest.TestCase):
    def test_rejects_metadata_inside_anmf(self):
        frame = b"\x00" * 16 + riff_chunk(b"XMP ", b"<x/>") + riff_chunk(b"VP8L", fixtures.vp8l(2, 2))
        data = webp_lossless(4, 3, [(b"ANMF", frame)], vp8x_flags=0x02)
        problems = webp.check(data)
        self.assertTrue(any("XMP" in p for p in problems), problems)

    def test_short_vp8x_is_a_value_error(self):
        data = b"RIFF" + struct.pack("<I", 4 + 8 + 2) + b"WEBP" + riff_chunk(b"VP8X", b"\x00\x00")
        with self.assertRaises(ValueError):
            webp.chunks(data)


class AvatarRobustnessTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "a"
        fixtures.avatar(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def problems_for(self, toml):
        (self.dir / "avatar.toml").write_text(toml)
        return avatar.check(self.dir)

    def test_wrong_shapes_are_reported(self):
        for toml in ('vrm = "x"\n', "[vrm]\nmodel = 1\n", '[vrm]\nmodel = "vrm/model.vrm"\nactions = "x"\n',
                     '[sprite]\ndefault_pose = "a"\nposes = "x"\n', '[sprite]\ndefault_pose = "a"\n[sprite.poses]\na = 1\n'):
            with self.subTest(toml=toml):
                self.assertNotEqual(self.problems_for(toml), [])

    def test_roles_require_their_extensions(self):
        problems = self.problems_for(fixtures.AVATAR_TOML.replace('base = "sprite/idle.webp"', 'base = "vrm/model.vrm"'))
        self.assertTrue(any("vrm/model.vrm" in p for p in problems), problems)
        problems = self.problems_for(fixtures.AVATAR_TOML.replace('model = "vrm/model.vrm"', 'model = "sprite/idle.webp"'))
        self.assertTrue(any("sprite/idle.webp" in p for p in problems), problems)
        problems = self.problems_for(fixtures.AVATAR_TOML.replace('idle = "vrm/idle.vrma"', 'idle = "vrm/model.vrm"'))
        self.assertTrue(any("vrm/model.vrm" in p for p in problems), problems)

    def test_sprite_without_image_chunk_is_reported(self):
        bad = b"RIFF" + struct.pack("<I", 4 + 8 + 4) + b"WEBP" + riff_chunk(b"ANIM", b"\x00" * 4)
        (self.dir / "sprite" / "idle.webp").write_bytes(bad)
        problems = avatar.check(self.dir)
        self.assertTrue(any("idle.webp" in p for p in problems), problems)


class RepoHardeningTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = fixtures.repo(Path(self._tmp.name) / "r")

    def tearDown(self):
        self._tmp.cleanup()

    def test_extra_thumbnail_fails(self):
        (self.root / "thumbnails" / "secret.webp").write_bytes(webp_lossless(2, 2))
        problems = repo.check(self.root)
        self.assertTrue(any("secret.webp" in p for p in problems), problems)
        (self.root / "thumbnails" / "secret.webp").unlink()
        (self.root / "thumbnails" / ".gitkeep").write_text("")
        self.assertEqual(repo.check(self.root), [])

    def test_bad_catalog_shapes_are_reported(self):
        for toml in ('[[avatar]]\nid = 1\n', '[[avatar]]\nid = "default-chibi"\noutfit = "default"\nproportion = "chibi"\ntitle = "x"\n', 'avatar = 3\n'):
            with self.subTest(toml=toml):
                (self.root / "catalog.toml").write_text(toml)
                self.assertNotEqual(repo.check(self.root), [])


class CatalogHardeningTest(unittest.TestCase):
    def test_drafts_and_prereleases_are_skipped(self):
        from tests.test_catalog import REPO, release

        with tempfile.TemporaryDirectory() as tmp:
            root = fixtures.repo(Path(tmp) / "r")
            sums = Path(tmp) / "s"
            sums.mkdir()
            for tag in ("default-chibi-v1", "default-chibi-v2", "default-chibi-v3"):
                (sums / f"{tag}.tar.sha256").write_text("a" * 64 + f"  {tag}.tar\n")
            rels = [release("default-chibi-v1"), dict(release("default-chibi-v2"), draft=True), dict(release("default-chibi-v3"), prerelease=True)]
            out = catalog.build(root, rels, sums, REPO)
            self.assertEqual(out["avatars"][0]["version"], 1)

    def test_thumbnails_copied_only_for_listed_avatars(self):
        from tests.test_catalog import REPO, release

        with tempfile.TemporaryDirectory() as tmp:
            root = fixtures.repo(Path(tmp) / "r", ids=("default-chibi", "default-regular"))
            sums = Path(tmp) / "s"
            sums.mkdir()
            (sums / "default-chibi-v1.tar.sha256").write_text("a" * 64 + "  default-chibi-v1.tar\n")
            out_dir = Path(tmp) / "o"
            out = catalog.build(root, [release("default-chibi-v1")], sums, REPO)
            catalog.copy_thumbnails(root, out, out_dir)
            self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["default-chibi.webp"])


if __name__ == "__main__":
    unittest.main()
