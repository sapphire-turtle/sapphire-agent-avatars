import copy
import unittest

from tests.fixtures import glb, png
from avatars import glb as glb_mod

META = dict(glb_mod.EXPECTED_META, name="Sample", version="1")


def vrm(png_bytes=None, **asset_extra):
    """A minimal VRM 1.0 glb with one embedded PNG texture."""
    img = png_bytes if png_bytes is not None else png(2, 2)
    gltf = {
        "asset": {"version": "2.0", "generator": glb_mod.GENERATOR, **asset_extra},
        "buffers": [{"byteLength": len(img) + (-len(img) % 4)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(img)}],
        "images": [{"name": "body_tex", "bufferView": 0, "mimeType": "image/png"}],
        "textures": [{"name": "body", "source": 0}],
        "materials": [{"name": "Body_Skin"}],
        "nodes": [{"name": "J_Bip_C_Hips"}],
        "extensionsUsed": ["VRMC_vrm"],
        "extensions": {"VRMC_vrm": {"specVersion": "1.0", "meta": copy.deepcopy(META)}},
    }
    return gltf, img


def vrma():
    return {
        "asset": {"version": "2.0", "generator": glb_mod.GENERATOR},
        "nodes": [{"name": "hips"}],
        "animations": [{"name": "wave", "channels": [], "samplers": []}],
        "extensionsUsed": ["VRMC_vrm_animation"],
        "extensions": {"VRMC_vrm_animation": {"specVersion": "1.0"}},
    }


def build(gltf, img=b""):
    return glb(gltf, img)


class GlbTest(unittest.TestCase):
    def test_glb_clean_vrm_passes(self):
        self.assertEqual(glb_mod.check(build(*vrm()), "vrm"), [])

    def test_glb_clean_vrma_passes(self):
        self.assertEqual(glb_mod.check(build(vrma()), "vrma"), [])

    def test_glb_rejects_wrong_generator(self):
        gltf, img = vrm()
        gltf["asset"]["generator"] = "Some Exporter 4.2"
        problems = glb_mod.check(build(gltf, img), "vrm")
        self.assertEqual(len(problems), 1)
        self.assertIn("generator", problems[0])

    def test_glb_rejects_copyright(self):
        gltf, img = vrm(copyright="someone")
        self.assertTrue(any("copyright" in p for p in glb_mod.check(build(gltf, img), "vrm")))

    def test_glb_rejects_extras_anywhere(self):
        gltf, img = vrm()
        gltf["materials"][0]["extras"] = {"note": "x"}
        problems = glb_mod.check(build(gltf, img), "vrm")
        self.assertEqual(len(problems), 1)
        self.assertIn("extras", problems[0])
        self.assertIn("materials", problems[0])

    def test_glb_rejects_image_uri(self):
        for uri in ("tex.png", "data:image/png;base64,AAAA"):
            with self.subTest(uri=uri):
                gltf, img = vrm()
                gltf["images"][0] = {"name": "body_tex", "uri": uri}
                self.assertTrue(any("uri" in p for p in glb_mod.check(build(gltf, img), "vrm")))

    def test_glb_rejects_embedded_png_with_text(self):
        gltf, img = vrm(png(2, 2, [(b"tEXt", b"Software\x00x")]))
        problems = glb_mod.check(build(gltf, img), "vrm")
        self.assertEqual(len(problems), 1)
        self.assertIn("tEXt", problems[0])

    def test_glb_rejects_bad_name(self):
        for name in ("Body.001", "a" * 65, "体"):
            with self.subTest(name=name):
                gltf, img = vrm()
                gltf["nodes"][0]["name"] = name
                problems = glb_mod.check(build(gltf, img), "vrm")
                self.assertEqual(len(problems), 1)
                self.assertIn("nodes[0]", problems[0])

    def test_glb_rejects_meta_mismatch(self):
        gltf, img = vrm()
        gltf["extensions"]["VRMC_vrm"]["meta"]["allowRedistribution"] = False
        problems = glb_mod.check(build(gltf, img), "vrm")
        self.assertEqual(len(problems), 1)
        self.assertIn("allowRedistribution", problems[0])

    def test_glb_rejects_extra_meta_key(self):
        gltf, img = vrm()
        gltf["extensions"]["VRMC_vrm"]["meta"]["contactInformation"] = "x@example.com"
        problems = glb_mod.check(build(gltf, img), "vrm")
        self.assertEqual(len(problems), 1)
        self.assertIn("contactInformation", problems[0])

    def test_vrm_without_vrmc_vrm_fails(self):
        gltf, img = vrm()
        del gltf["extensions"]
        self.assertTrue(any("VRMC_vrm" in p for p in glb_mod.check(build(gltf, img), "vrm")))

    def test_vrma_without_extension_fails(self):
        gltf = vrma()
        del gltf["extensions"]
        self.assertTrue(any("VRMC_vrm_animation" in p for p in glb_mod.check(build(gltf), "vrma")))

    def test_strip_glb_rewrites_generator_and_keeps_bin(self):
        gltf, img = vrm()
        gltf["asset"]["generator"] = "Exporter v1.23 (x)"
        dirty = build(gltf, img)
        clean = glb_mod.strip(dirty)
        new_json, new_bin = glb_mod.read(clean)
        old_json, old_bin = glb_mod.read(dirty)
        self.assertEqual(new_json["asset"]["generator"], glb_mod.GENERATOR)
        old_json["asset"]["generator"] = glb_mod.GENERATOR
        self.assertEqual(new_json, old_json)
        self.assertEqual(new_bin, old_bin)
        self.assertEqual(len(clean) % 4, 0)
        self.assertEqual(glb_mod.check(clean, "vrm"), [])

    def test_read_rejects_garbage(self):
        with self.assertRaises(ValueError):
            glb_mod.read(b"glTF\x01\x00\x00\x00\x0c\x00\x00\x00")
        with self.assertRaises(ValueError):
            glb_mod.read(build(*vrm())[:-8])


if __name__ == "__main__":
    unittest.main()
